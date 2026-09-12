// Research benchmark only: this is not the native world's climate producer.
// A prescribed spherical-cap ocean mask exercises real native mesh geometry,
// gray radiation, mixed column storage, conservative transport and astronomical
// forcing. Pressure scales atmospheric storage and transport, not opacity.
// The mask, coefficients and calendar are intentionally independent of the
// native terrain, hydrology, lake, ice, biome and society systems.
// Compile and interpretation: docs/seasonal_energy_balance_model_research.md §9.

#include "engine/adaptive_energy_balance.hpp"
#include "engine/climate_transport.hpp"
#include "engine/internal.hpp"
#include "engine/periodic_energy_balance.hpp"
#include "engine/solar_insolation.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <optional>
#include <stdexcept>
#include <string>

using namespace magic_geo::detail;
using Clock = std::chrono::steady_clock;
double elapsed(Clock::time_point since) { return std::chrono::duration<double>(Clock::now()-since).count(); }

const char* help = R"HELP(Usage: periodic_climate_benchmark [options]

Run one prescribed-coefficient research climate on a real native sphere mesh.
Print one compact JSON object with coefficients, geometry, timings, convergence,
temperatures and energy checks. Exit 0 on convergence, 1 on model/solver failure,
or 2 on invalid arguments. No native world or production climate is generated.

  --backend fibonacci|geodesic   Mesh backend (default fibonacci)
  --case mesh|polar-land        Cap-mask mesh (default), or the isolated polar
                                land column from the original refinement probe
  --cells N                     Requested cell count, >=12 (default 128)
                                Geodesic generation may round the count upward.
  --pressure-bar P              Nonnegative pressure for C_atm and transport only
                                (default 1); opacity remains fixed at tau=1.
  --eccentricity E              Orbital eccentricity in [0,1) (default 0.016)
  --forcing actual|monthly360   Actual orbital intervals (default), or repeated
                                monthly means in 360 steps for performance only
  --forcing-refinement L        Recompute astronomical quadrature with angular
                                and elapsed-time bounds divided by 2^L (0..10)
  --initial-temperature-k T    Nonnegative initial iterate (default 288.15)
  --method be|tr-bdf2           Time integration method (default be)
  --adaptive                   Resolve local errors and reconverged monthly
                                refinements (default remains fixed stepping)
  --local-tolerance-k T         Adaptive local absolute tolerance (default 1e-4)
  --monthly-tolerance-k T       Monthly temperature gate (default .01)
  --monthly-flux-tolerance F    Monthly OLR/transport gate in W/m^2 (default .05)
  --uniform-subdivisions N      Fixed subdivisions per forcing interval, power
                                of two (default 1; adaptive starts at least 2)
  --reference-subdivisions N    Additionally compare against independently
                                converged uniform TR-BDF2 N and 2N partitions
  --reference-forcing-refinement L
                                Use independently recomputed astronomical
                                forcing at level L for those reference solves;
                                requires --reference-subdivisions (default same L)
  --warm-replay                 Also time a solve initialized at the converged
                                cycle boundary, with exactly unchanged inputs
  --help                       Show this help

Prescribed model: radius 6371 km; tilt 23.5 degrees; luminosity 1; implicit 1 AU;
year 365.2422*86400 s; alpha=0.3; effective gray emissivity=1/1.75;
C_atm=1004*P*1e5/9.80665 J/m^2/K; land adds 4e6, water adds 2.09065e8 J/m^2/K;
integrated conductivity=2.2e6 m^2/s*C_atm. Ocean is the cap position.x > -0.4
(70% of the continuous sphere). No lake/ice, phase-change, or opacity feedback.
Numerical convergence does not establish physical validity at extreme inputs.
The polar-land case has latitude 90 degrees, area 2e12 m^2, C 1.42377e7 J/m^2/K,
no transport, year 365.25*86400 s and initial 288 K unless explicitly overridden.
It requires pressure 1 bar; its original rounded capacity is retained exactly.
)HELP";

double number(const std::string& text) {
    std::size_t used=0;
    const double value=std::stod(text,&used);
    if (used!=text.size() || !std::isfinite(value)) throw std::invalid_argument("expected a finite number");
    return value;
}

std::string json_string(const std::string& value) {
    std::string result="\"";
    for (const char c:value) {
        if (c=='\"' || c=='\\') result+='\\';
        if (c=='\n') result+="\\n";
        else if (c=='\r') result+="\\r";
        else if (c=='\t') result+="\\t";
        else result+=c;
    }
    return result+'\"';
}

struct MonthlyDifference {
    double mean_temperature_k = 0.0;
    double radiative_temperature_k = 0.0;
    double flux_w_m2 = 0.0;
    double absorbed_shortwave_w_m2 = 0.0;
};

MonthlyDifference compare_months(const PeriodicSurfaceEnergyYear& first, const PeriodicSurfaceEnergyYear& second) {
    MonthlyDifference difference;
    for (std::size_t month=0;month<12;++month) {
        const auto& x=first.months[month];
        const auto& y=second.months[month];
        for (std::size_t i=0;i<x.mean_temperature_k.size();++i) {
            difference.mean_temperature_k=std::max(difference.mean_temperature_k,
                std::abs(x.mean_temperature_k[i]-y.mean_temperature_k[i]));
            difference.radiative_temperature_k=std::max(difference.radiative_temperature_k,
                std::abs(std::sqrt(std::sqrt(x.mean_fourth_power_temperature_k4[i]))-
                    std::sqrt(std::sqrt(y.mean_fourth_power_temperature_k4[i]))));
            difference.flux_w_m2=std::max({difference.flux_w_m2,
                std::abs(x.emitted_longwave_w_m2[i]-y.emitted_longwave_w_m2[i]),
                std::abs(x.horizontal_heat_convergence_w_m2[i]-y.horizontal_heat_convergence_w_m2[i])});
            difference.absorbed_shortwave_w_m2=std::max(difference.absorbed_shortwave_w_m2,
                std::abs(x.absorbed_shortwave_w_m2[i]-y.absorbed_shortwave_w_m2[i]));
        }
    }
    return difference;
}

double area_mean_c(const PeriodicSurfaceEnergyYear& year, const SurfaceEnergySystem& system) {
    long double weighted=0.0L,area=0.0L;
    for (std::size_t i=0;i<system.columns().size();++i) {
        area+=system.columns()[i].area_m2;
        for (const auto& month:year.months) weighted+=static_cast<long double>(system.columns()[i].area_m2)*
            month.duration_seconds/year.duration_seconds*month.mean_temperature_k[i];
    }
    return static_cast<double>(weighted/area)-273.15;
}

int main(int argc, char** argv) {
    int backend=0, requested=128, forcing_refinement=0;
    std::optional<int> reference_forcing_refinement;
    double pressure=1.0, eccentricity=0.016, initial_k=288.15;
    bool monthly360=false, warm_replay=false, adaptive=false, polar_land=false, initial_explicit=false;
    SurfaceEnergyTimeMethod method=SurfaceEnergyTimeMethod::backward_euler;
    AdaptivePeriodicSurfaceEnergyOptions adaptive_options;
    std::size_t uniform_subdivisions=1, reference_subdivisions=0;
    try {
        for (int index=1;index<argc;++index) {
            const std::string option=argv[index];
            if (option=="--help") { std::cout << help; return 0; }
            if (option=="--warm-replay") { warm_replay=true; continue; }
            if (option=="--adaptive") { adaptive=true; continue; }
            if (index+1==argc) throw std::invalid_argument("missing value for "+option);
            const std::string value=argv[++index];
            if (option=="--case") {
                if (value=="mesh") polar_land=false;
                else if (value=="polar-land") polar_land=true;
                else throw std::invalid_argument("case must be mesh or polar-land");
            } else if (option=="--method") {
                if (value=="be") method=SurfaceEnergyTimeMethod::backward_euler;
                else if (value=="tr-bdf2") method=SurfaceEnergyTimeMethod::tr_bdf2;
                else throw std::invalid_argument("method must be be or tr-bdf2");
            } else if (option=="--local-tolerance-k" || option=="--monthly-tolerance-k" || option=="--monthly-flux-tolerance") {
                const double tolerance=number(value);
                if (tolerance<=0.0) throw std::invalid_argument("tolerance must be positive");
                if (option=="--local-tolerance-k") adaptive_options.local_absolute_tolerance_k=tolerance;
                if (option=="--monthly-tolerance-k") adaptive_options.monthly_temperature_tolerance_k=tolerance;
                if (option=="--monthly-flux-tolerance") adaptive_options.monthly_flux_tolerance_w_m2=tolerance;
            } else if (option=="--uniform-subdivisions" || option=="--reference-subdivisions") {
                std::size_t used=0;
                const auto count=std::stoull(value,&used);
                if (used!=value.size() || value.front()=='-' || count==0 || (count&(count-1))!=0 ||
                    count>std::numeric_limits<std::size_t>::max()/2) {
                    throw std::invalid_argument("subdivision count must be a positive representable power of two");
                }
                if (option=="--uniform-subdivisions") uniform_subdivisions=static_cast<std::size_t>(count);
                else reference_subdivisions=static_cast<std::size_t>(count);
            } else if (option=="--forcing-refinement" || option=="--reference-forcing-refinement") {
                std::size_t used=0;
                const int level=std::stoi(value,&used);
                if (used!=value.size() || level<0 || level>SolarOrbitForcing::maximum_integration_refinement_level) {
                    throw std::invalid_argument("forcing refinement level must be an integer in [0,10]");
                }
                if (option=="--forcing-refinement") forcing_refinement=level;
                else reference_forcing_refinement=level;
            } else if (option=="--backend") {
                if (value=="fibonacci") backend=0;
                else if (value=="geodesic") backend=1;
                else throw std::invalid_argument("backend must be fibonacci or geodesic");
            } else if (option=="--cells") {
                std::size_t used=0;
                requested=std::stoi(value,&used);
                if (used!=value.size() || requested<12) throw std::invalid_argument("cells must be an integer >=12");
            } else if (option=="--pressure-bar") {
                pressure=number(value);
                if (pressure<0.0) throw std::invalid_argument("pressure must be nonnegative");
            } else if (option=="--eccentricity") {
                eccentricity=number(value);
                if (eccentricity<0.0 || eccentricity>=1.0) throw std::invalid_argument("eccentricity must lie in [0,1)");
            } else if (option=="--initial-temperature-k") {
                initial_k=number(value);
                initial_explicit=true;
                if (initial_k<0.0) throw std::invalid_argument("initial temperature must be nonnegative");
            } else if (option=="--forcing") {
                if (value=="monthly360") monthly360=true;
                else if (value=="actual") monthly360=false;
                else throw std::invalid_argument("forcing must be actual or monthly360");
            } else throw std::invalid_argument("unknown option "+option);
        }
        if (polar_land && pressure!=1.0) throw std::invalid_argument("polar-land retains its original fixed 1-bar capacity");
        if (reference_forcing_refinement && !reference_subdivisions) {
            throw std::invalid_argument("reference forcing refinement requires reference subdivisions");
        }
        if (monthly360 && (forcing_refinement!=0 || reference_forcing_refinement)) {
            throw std::invalid_argument("astronomical forcing refinement requires actual forcing");
        }
    } catch (const std::exception& error) {
        std::cerr << "Argument error: " << error.what() << "\nUse --help for usage.\n";
        return 2;
    }
    if (polar_land && !initial_explicit) initial_k=288.0;
    const double year_seconds=(polar_land?365.25:365.2422)*86400.0;
    const double atmospheric_capacity=1004.0*pressure*1e5/9.80665;
    const double conductivity=2.2e6*atmospheric_capacity;
    if (!std::isfinite(atmospheric_capacity) || !std::isfinite(conductivity)) {
        std::cerr << "Argument error: derived storage/transport coefficient is not finite.\n";
        return 2;
    }
    const auto start=Clock::now();
    std::cout << std::setprecision(16);
    std::cout << "{\"benchmark_model\":" << json_string(polar_land?"isolated_polar_land_column_v1":"prescribed_gray_column_with_cap_mask_v1")
              << ",\"backend\":" << backend << ",\"requested_cells\":" << requested
              << ",\"pressure_bar\":" << pressure << ",\"eccentricity\":" << eccentricity
              << ",\"forcing\":\"" << (monthly360?"monthly_means_360_steps":"actual_orbital_intervals")
              << "\",\"initial_k\":" << initial_k << ",\"alpha\":0.3,\"epsilon\":" << 1.0/1.75
              << ",\"year_seconds\":" << year_seconds << ",\"atmospheric_capacity\":" << atmospheric_capacity
              << ",\"conductivity_w_k\":" << conductivity
              << ",\"radius_km\":6371,\"tilt_degrees\":23.5,\"stellar_luminosity\":1"
              << ",\"surface_mask\":" << json_string(polar_land?"isolated_polar_land":"water_where_position_x_greater_than_minus_0_4")
              << ",\"method\":" << json_string(method==SurfaceEnergyTimeMethod::backward_euler?"be":"tr-bdf2")
              << ",\"adaptive\":" << (adaptive?"true":"false")
              << ",\"uniform_subdivisions\":" << uniform_subdivisions
              << ",\"forcing_refinement_level\":" << forcing_refinement
              << ",\"local_absolute_tolerance_k\":" << adaptive_options.local_absolute_tolerance_k
              << ",\"monthly_temperature_tolerance_k\":" << adaptive_options.monthly_temperature_tolerance_k
              << ",\"monthly_flux_tolerance_w_m2\":" << adaptive_options.monthly_flux_tolerance_w_m2
              << ",\"required_monthly_refinement_confirmations\":" << adaptive_options.required_monthly_refinement_confirmations
              << std::flush;
    bool converged=false;
    try {
        magic_geo::Params params;
        params.mesh_backend=backend; params.cell_count=requested; params.threads=1;
        auto stamp=Clock::now();
        std::vector<Cell> cells;
        if (polar_land) {
            Cell cell;
            cell.id=0; cell.lat=std::numbers::pi/2.0; cell.p={0.0,0.0,1.0}; cell.area_km2=2.0e6;
            cells.push_back(cell);
        } else cells=build_mesh(params);
        const double mesh_seconds=elapsed(stamp);
        std::vector<SurfaceEnergyColumn> columns;
        long double total_area=0.0L, water_area=0.0L;
        for (const auto& cell:cells) {
            const bool water=!polar_land && cell.p.x > -0.4; // 70% ocean in the continuum mesh case.
            const double area=cell.area_km2*1e6;
            columns.push_back({area,polar_land?1.42377e7:atmospheric_capacity+(water?2.09065e8:4e6),1.0/1.75});
            total_area+=area;
            if (water) water_area+=area;
        }
        stamp=Clock::now();
        auto edges=polar_land?std::vector<EnergyTransportEdge>{}:build_climate_heat_transport_edges(backend,cells,conductivity);
        const auto edge_count=edges.size();
        SurfaceEnergySystem system(std::move(columns),std::move(edges));
        double minimum_capacity=std::numeric_limits<double>::max(), maximum_capacity=0.0;
        for (const auto& column:system.columns()) {
            minimum_capacity=std::min(minimum_capacity,column.heat_capacity_j_m2_k);
            maximum_capacity=std::max(maximum_capacity,column.heat_capacity_j_m2_k);
        }
        const double transport_seconds=elapsed(stamp);
        stamp=Clock::now();
        const auto make_intervals = [&](int refinement_level) {
            SolarOrbitForcing solar(23.5,eccentricity,1.0,refinement_level);
            std::vector<SurfaceEnergyForcingInterval> result;
            if (monthly360) {
                std::vector<std::array<double,12>> monthly;
                for (const auto& cell:cells) monthly.push_back(solar.monthly_insolation_w_m2(cell.lat));
                for (int month=0;month<12;++month) for(int day=0;day<30;++day) {
                    SurfaceEnergyForcingInterval interval;
                    interval.month_index=month; interval.duration_seconds=year_seconds/360.0;
                    for(std::size_t i=0;i<cells.size();++i) interval.absorbed_shortwave_w_m2.push_back(0.7*monthly[i][month]);
                    result.push_back(std::move(interval));
                }
            } else {
                for(std::size_t index=0;index<solar.integration_intervals().size();++index) {
                    const auto& orbital=solar.integration_intervals()[index];
                    SurfaceEnergyForcingInterval interval;
                    interval.month_index=static_cast<int>(orbital.month_index);
                    interval.duration_seconds=year_seconds*orbital.duration_fraction_of_year;
                    for(const auto& cell:cells) interval.absorbed_shortwave_w_m2.push_back(0.7*solar.interval_mean_insolation_w_m2(cell.lat,index));
                    result.push_back(std::move(interval));
                }
            }
            return result;
        };
        const auto intervals=make_intervals(forcing_refinement);
        const double forcing_seconds=elapsed(stamp);
        std::cout << ",\"cells\":" << cells.size() << ",\"edges\":" << edge_count
                  << ",\"minimum_column_capacity_j_m2_k\":" << minimum_capacity
                  << ",\"maximum_column_capacity_j_m2_k\":" << maximum_capacity
                  << ",\"ocean_area_fraction\":" << static_cast<double>(water_area/total_area)
                  << ",\"intervals\":" << intervals.size() << ",\"mesh_seconds\":" << mesh_seconds
                  << ",\"transport_seconds\":" << transport_seconds << ",\"forcing_seconds\":" << forcing_seconds << std::flush;
        PeriodicSurfaceEnergyOptions options;
        options.time_method=method;
        if (uniform_subdivisions>1) options.thermal_subdivisions.assign(intervals.size(),uniform_subdivisions);
        std::optional<AdaptivePeriodicSurfaceEnergyYear> adaptive_result;
        stamp=Clock::now();
        PeriodicSurfaceEnergyYear year;
        if (adaptive) {
            adaptive_options.periodic=options;
            adaptive_result=solve_adaptive_periodic_surface_energy_balance(system,intervals,std::vector<double>(cells.size(),initial_k),adaptive_options);
            options=adaptive_result->accepted_periodic_options;
            year=std::move(adaptive_result->year);
        } else year=solve_periodic_surface_energy_balance(system,intervals,std::vector<double>(cells.size(),initial_k),options);
        const double solve_seconds=elapsed(stamp);
        long double mean_temperature=0.0L, absorbed=0.0L, emitted=0.0L, storage=0.0L, transport=0.0L, residual=0.0L;
        double minimum_annual=1e300,maximum_annual=-1e300,minimum_month=1e300,maximum_month=-1e300;
        double maximum_month_global_transport=0.0,maximum_monthly_residual=0.0;
        for(std::size_t i=0;i<cells.size();++i) {
            long double annual=0.0L;
            const long double area=system.columns()[i].area_m2;
            for(const auto& month:year.months) {
                const long double weight=month.duration_seconds/year.duration_seconds;
                annual+=weight*month.mean_temperature_k[i];
                absorbed+=weight*area*month.absorbed_shortwave_w_m2[i];
                emitted+=weight*area*month.emitted_longwave_w_m2[i];
                storage+=weight*area*month.heat_storage_tendency_w_m2[i];
                transport+=weight*area*month.horizontal_heat_convergence_w_m2[i];
                residual+=weight*area*month.balance_residual_w_m2[i];
                minimum_month=std::min(minimum_month,month.mean_temperature_k[i]-273.15);
                maximum_month=std::max(maximum_month,month.mean_temperature_k[i]-273.15);
                maximum_monthly_residual=std::max(maximum_monthly_residual,std::abs(month.balance_residual_w_m2[i]));
            }
            mean_temperature+=area*annual;
            minimum_annual=std::min(minimum_annual,static_cast<double>(annual)-273.15);
            maximum_annual=std::max(maximum_annual,static_cast<double>(annual)-273.15);
        }
        for(const auto& month:year.months) {
            long double watts=0.0L;
            for(std::size_t i=0;i<cells.size();++i) watts+=system.columns()[i].area_m2*static_cast<long double>(month.horizontal_heat_convergence_w_m2[i]);
            maximum_month_global_transport=std::max(maximum_month_global_transport,std::abs(static_cast<double>(watts/total_area)));
        }
        std::cout << ",\"solve_seconds\":" << solve_seconds
                  << ",\"accepted_solver_absolute_tolerance_w_m2\":" << options.step.absolute_tolerance_w_m2
                  << ",\"accepted_solver_relative_tolerance\":" << options.step.relative_tolerance
                  << ",\"periodic_iterations\":" << year.periodic_iterations << ",\"year_evaluations\":" << year.year_evaluations
                  << ",\"integration_step_count\":" << year.integration_step_count
                  << ",\"final_partition_periodic_total_steps\":" << year.total_integration_steps
                  << ",\"year_newton_iterations\":" << year.year_newton_iterations
                  << ",\"year_linear_iterations\":" << year.year_linear_iterations
                  << ",\"maximum_step_balance_residual_w_m2\":" << year.maximum_step_balance_residual_w_m2
                  << ",\"maximum_phase_difference_k\":" << year.maximum_phase_difference_k
                  << ",\"maximum_annual_net_heating_w_m2\":" << year.maximum_annual_net_heating_w_m2
                  << ",\"global_annual_net_heating_w_m2\":" << static_cast<double>(year.global_annual_net_heating_w/total_area)
                  << ",\"mean_temperature_c\":" << static_cast<double>(mean_temperature/total_area)-273.15
                  << ",\"minimum_annual_temperature_c\":" << minimum_annual << ",\"maximum_annual_temperature_c\":" << maximum_annual
                  << ",\"minimum_monthly_temperature_c\":" << minimum_month << ",\"maximum_monthly_temperature_c\":" << maximum_month
                  << ",\"global_absorbed_w_m2\":" << static_cast<double>(absorbed/total_area)
                  << ",\"global_emitted_w_m2\":" << static_cast<double>(emitted/total_area)
                  << ",\"global_asr_minus_olr_w_m2\":" << static_cast<double>((absorbed-emitted)/total_area)
                  << ",\"global_storage_w_m2\":" << static_cast<double>(storage/total_area)
                  << ",\"global_transport_w_m2\":" << static_cast<double>(transport/total_area)
                  << ",\"global_balance_residual_w_m2\":" << static_cast<double>(residual/total_area)
                  << ",\"maximum_month_global_transport_w_m2\":" << maximum_month_global_transport
                  << ",\"maximum_month_cell_balance_residual_w_m2\":" << maximum_monthly_residual;
        if (polar_land) {
            std::cout << ",\"monthly_mean_temperature_k\":[";
            for (std::size_t month=0;month<12;++month) {
                if (month) std::cout << ',';
                std::cout << year.months[month].mean_temperature_k[0];
            }
            std::cout << ']';
        }
        const auto partition=options.thermal_subdivisions.empty()?std::vector<std::size_t>(intervals.size(),1):options.thermal_subdivisions;
        std::map<std::size_t,std::size_t> histogram;
        for (const auto count:partition) ++histogram[count];
        std::cout << ",\"accepted_partition_step_count\":" << std::accumulate(partition.begin(),partition.end(),std::size_t{0})
                  << ",\"accepted_subdivision_histogram\":{";
        bool first_histogram=true;
        for (const auto& [count,frequency]:histogram) {
            if (!first_histogram) std::cout << ',';
            first_histogram=false;
            std::cout << json_string(std::to_string(count)) << ':' << frequency;
        }
        std::cout << '}';
        if (adaptive_result) {
            const auto& state=*adaptive_result;
            std::cout << ",\"maximum_local_error_ratio\":" << state.maximum_local_error_ratio
                      << ",\"maximum_numerical_error_ratio\":" << state.maximum_numerical_error_ratio
                      << ",\"maximum_endpoint_numerical_uncertainty_k\":" << state.maximum_endpoint_numerical_uncertainty_k
                      << ",\"maximum_monthly_temperature_change_k\":" << state.maximum_monthly_temperature_change_k
                      << ",\"maximum_monthly_flux_change_w_m2\":" << state.maximum_monthly_flux_change_w_m2
                      << ",\"monthly_refinement_confirmations\":" << state.monthly_refinement_confirmations
                      << ",\"partition_refinements\":" << state.partition_refinements
                      << ",\"solver_tightenings\":" << state.solver_tightenings
                      << ",\"estimator_trials\":" << state.estimator_trials
                      << ",\"failed_estimator_trials\":" << state.failed_estimator_trials
                      << ",\"total_periodic_year_evaluations\":" << state.total_periodic_year_evaluations
                      << ",\"total_step_attempts\":" << state.total_step_attempts;
        } else {
            std::cout << ",\"total_periodic_year_evaluations\":" << year.year_evaluations
                      << ",\"total_step_attempts\":" << year.total_integration_steps;
        }
        if (reference_subdivisions) {
            const int reference_level=reference_forcing_refinement.value_or(forcing_refinement);
            const auto reference_intervals=make_intervals(reference_level);
            PeriodicSurfaceEnergyOptions reference_options;
            reference_options.time_method=SurfaceEnergyTimeMethod::tr_bdf2;
            reference_options.thermal_subdivisions.assign(reference_intervals.size(),reference_subdivisions);
            stamp=Clock::now();
            const auto coarse_reference=solve_periodic_surface_energy_balance(system,reference_intervals,std::vector<double>(cells.size(),initial_k),reference_options);
            reference_options.thermal_subdivisions.assign(reference_intervals.size(),2*reference_subdivisions);
            const auto fine_reference=solve_periodic_surface_energy_balance(system,reference_intervals,std::vector<double>(cells.size(),initial_k),reference_options);
            const double reference_seconds=elapsed(stamp);
            const auto difference=compare_months(year,fine_reference);
            const auto refinement=compare_months(coarse_reference,fine_reference);
            std::cout << ",\"reference_method\":\"uniform_tr_bdf2\",\"reference_subdivisions\":" << reference_subdivisions
                      << ",\"reference_fine_subdivisions\":" << 2*reference_subdivisions
                      << ",\"reference_forcing_refinement_level\":" << reference_level
                      << ",\"reference_forcing_intervals\":" << reference_intervals.size()
                      << ",\"reference_solve_seconds\":" << reference_seconds
                      << ",\"reference_mean_temperature_c\":" << area_mean_c(fine_reference,system)
                      << ",\"reference_max_monthly_mean_temperature_error_k\":" << difference.mean_temperature_k
                      << ",\"reference_max_monthly_radiative_temperature_error_k\":" << difference.radiative_temperature_k
                      << ",\"reference_max_monthly_flux_error_w_m2\":" << difference.flux_w_m2
                      << ",\"reference_max_monthly_absorbed_shortwave_error_w_m2\":" << difference.absorbed_shortwave_w_m2
                      << ",\"reference_uniform_refinement_temperature_change_k\":" << std::max(refinement.mean_temperature_k,refinement.radiative_temperature_k)
                      << ",\"reference_uniform_refinement_flux_change_w_m2\":" << refinement.flux_w_m2
                      << ",\"reference_total_integration_steps\":" << coarse_reference.total_integration_steps+fine_reference.total_integration_steps;
        }
        if (warm_replay) {
            stamp=Clock::now();
            const auto replay=solve_periodic_surface_energy_balance(system,intervals,year.initial_temperature_k,options);
            std::cout << ",\"unchanged_coefficients_warm_replay_seconds\":" << elapsed(stamp)
                      << ",\"warm_replay_year_evaluations\":" << replay.year_evaluations
                      << ",\"warm_replay_max_phase_difference_k\":" << replay.maximum_phase_difference_k;
        }
        converged=true;
        std::cout << ",\"status\":\"converged\"";
    } catch(const std::exception& error) {
        std::cout << ",\"status\":\"failed\",\"error\":" << json_string(error.what());
    }
    std::cout << ",\"total_seconds\":" << elapsed(start) << "}\n";
    return converged?0:1;
}
