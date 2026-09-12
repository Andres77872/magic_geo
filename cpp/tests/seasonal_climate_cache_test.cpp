#include "engine/seasonal_climate_cache.hpp"
#include "engine/internal.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <utility>

namespace {
using namespace magic_geo::detail;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

template <typename Callable>
void rejects(Callable&& callable, const char* message) {
    bool rejected=false;
    try { callable(); } catch (const std::exception&) { rejected=true; }
    require(rejected,message);
}

std::vector<Cell> mesh(int backend=0,int count=12) {
    magic_geo::Params params;
    params.mesh_backend=backend; params.cell_count=count;
    auto cells=build_mesh(params);
    for (auto& cell:cells) cell.elevation_m=500.0+200.0*cell.p.z;
    cells[0].is_water=true; cells[0].water_body=2;
    cells[0].elevation_m=-20.0; cells[0].water_depth_m=20.0;
    return cells;
}

void owning_certificate_and_changed_surface() {
    static_assert(!std::is_copy_constructible_v<PrescribedSeasonalClimateCache>);
    static_assert(std::is_nothrow_move_constructible_v<PrescribedSeasonalClimateCache>);
    static_assert(std::is_same_v<decltype(std::declval<PrescribedSeasonalClimateCache&>().solve(
        0,std::declval<const std::vector<Cell>&>())),const PrescribedSeasonalClimate&>);
    PrescribedSeasonalClimateCache cache;
    require(cache.last_result()==nullptr && cache.completed_solve_count()==0,
            "empty cache already owns a certificate");
    auto cells=mesh();
    PrescribedSeasonalClimateOptions options;
    const auto& first=cache.solve(0,cells,options);
    require(cache.completed_solve_count()==1 && !cache.last_solve_was_warm_started(),
            "first cache solve did not use independent initialization");
    require(first.solution.monthly_refinement_confirmations==2,"initial cache result skipped monthly verification");
    const auto original_pressure=first.physical_columns.surface_pressure_pa;
    const auto original_months=first.solution.year.months;
    const auto* original_address=&first;

    // Editing caller-owned cells or a result copy cannot modify the private
    // snapshot/certificate, and irrelevant diagnostics are not cache inputs.
    auto external_copy=first;
    external_copy.solution.year.months[0].mean_temperature_k[0]=-1.0e9;
    external_copy.options.atmosphere.mean_surface_pressure_pa=0;
    cells[0].temperature_c=-999;
    cells[0].temperature_monthly_c.fill(999);
    cells[0].biome=99; cells[0].ice_thickness_m=3200;
    cells[0].precipitation_mm_y=std::numeric_limits<double>::quiet_NaN();
    cells[0].surface_pressure_anomaly_hpa=12345;
    cells[0].neighbors={-123}; // Not consumed by this physical composition.
    cells[0].lon=std::numeric_limits<double>::quiet_NaN();
    const auto& hit=cache.solve(0,cells,options);
    require(&hit==original_address && cache.completed_solve_count()==1,
            "downstream diagnostics or unused neighbors invalidated a verified input");
    require(hit.solution.year.months[0].mean_temperature_k==original_months[0].mean_temperature_k,
            "caller-owned result copy changed the private certificate");

    cells[0].elevation_m=-2.0; cells[0].water_depth_m=2.0;
    require(cache.last_result()->water_depth_m[0]==20.0,
            "mutating caller water depth changed the cached snapshot before solving");
    const auto& changed=cache.solve(0,cells,options);
    require(cache.completed_solve_count()==2 && cache.last_solve_was_warm_started(),
            "changed surface did not fully solve from the preceding phase");
    require(changed.solution.monthly_refinement_confirmations==2,"changed coefficients reused stale accuracy acceptance");
    require(changed.surfaces[0].surface_heat_capacity_j_m2_k==2.0*4.1813e6,
            "changed shallow depth reused old heat storage");
    require(changed.physical_columns.surface_pressure_pa==original_pressure,
            "marine seabed depth incorrectly changed the atmospheric interface");
    double maximum_change=0;
    for (std::size_t m=0;m<12;++m) for (std::size_t i=0;i<cells.size();++i) {
        maximum_change=std::max(maximum_change,std::abs(changed.solution.year.months[m].mean_temperature_k[i]-
                                                      original_months[m].mean_temperature_k[i]));
    }
    require(maximum_change>0.01,"changed shallow-water capacity has no resolved seasonal response");
    require(&cache.solve(0,cells,options)==&changed && cache.completed_solve_count()==2,
            "exact unchanged physical input performed another numerical solve");

    // Both invalid input and a numerical-work failure must leave the old
    // solution and its key available; restoring inputs must still hit it.
    const auto* retained=cache.last_result();
    const auto retained_month=retained->solution.year.months[0].mean_temperature_k;
    cells[0].is_lake=true;
    rejects([&]{cache.solve(0,cells,options);},"stale lake state bypassed validation through a cache hit");
    cells[0].is_lake=false;
    auto insufficient=options;
    insufficient.integration.maximum_total_step_attempts=1;
    rejects([&]{cache.solve(0,cells,insufficient);},"exhausted numerical work budget was accepted");
    require(cache.last_result()==retained && cache.completed_solve_count()==2 &&
            cache.last_result()->solution.year.months[0].mean_temperature_k==retained_month,
            "failed replacement damaged the preceding certificate");
    require(&cache.solve(0,cells,options)==retained && cache.completed_solve_count()==2,
            "failure replaced the preceding exact cache key");
}

void every_consumed_geometry_field_is_checked() {
    auto cells=mesh();
    PrescribedSeasonalClimateOptions options;
    options.top_of_atmosphere_albedo=1.0; // Fast exact dark equilibrium, still fully verified.
    PrescribedSeasonalClimateCache cache;
    cache.solve(0,cells,options);

    const auto reject_change=[&](auto mutate) {
        auto malformed=cells; mutate(malformed);
        const auto* retained=cache.last_result();
        const auto count=cache.completed_solve_count();
        rejects([&]{cache.solve(0,malformed,options);},"changed malformed geometry/source was incorrectly cached");
        require(cache.last_result()==retained && cache.completed_solve_count()==count,
                "rejected geometry invalidated a prior result");
        require(&cache.solve(0,cells,options)==retained,"original geometry no longer hits after failed replacement");
    };
    reject_change([](auto& c){c[0].id=1;});
    reject_change([](auto& c){c[0].p.x+=0.1;});
    reject_change([](auto& c){c[0].area_km2*=2;});
    reject_change([](auto& c){c[0].control_volume_vertices[0].x+=0.1;});
    reject_change([](auto& c){c[0].control_volume_vertices.pop_back();});
    reject_change([](auto& c){c[0].control_volume_edge_neighbor_ids[0]=-1;});
    reject_change([](auto& c){c[0].lat+=0.1;});
    reject_change([](auto& c){c[0].elevation_m=0;});
    reject_change([](auto& c){c[0].water_depth_m=0;});
    reject_change([](auto& c){c[0].is_water=false;});
    reject_change([](auto& c){c[0].water_body=4;});
    reject_change([](auto& c){c[0].is_lake=true;});
    reject_change([](auto& c){c[0].lat=std::numeric_limits<double>::quiet_NaN();});
    rejects([&]{cache.solve(2,cells,options);},"unsupported backend reused a cached supported mesh");

    // Geometry validator tolerance must not become a cache-match tolerance.
    // These one-ulp valid coordinate changes must invoke the numerical solve.
    std::size_t expected=cache.completed_solve_count();
    cells[0].p.x=std::nextafter(cells[0].p.x,std::numeric_limits<double>::infinity());
    cache.solve(0,cells,options);
    require(cache.completed_solve_count()==++expected,"one-ulp primal position change reused a cache certificate");
    cells[0].control_volume_vertices[0].x=std::nextafter(cells[0].control_volume_vertices[0].x,
                                                      std::numeric_limits<double>::infinity());
    cache.solve(0,cells,options);
    require(cache.completed_solve_count()==++expected,"one-ulp control-volume change reused a cache certificate");
    cells[0].lat=std::nextafter(cells[0].lat,std::numeric_limits<double>::infinity());
    cache.solve(0,cells,options);
    require(cache.completed_solve_count()==++expected,"one-ulp latitude change reused a cache certificate");
}

void nested_options_and_changed_shape() {
    auto cells=mesh();
    PrescribedSeasonalClimateOptions options;
    options.top_of_atmosphere_albedo=1;
    PrescribedSeasonalClimateCache cache;
    cache.solve(0,cells,options);
    std::size_t expected=1;
    const auto changed=[&](auto mutate) {
        const auto previous=options;
        mutate(options);
        require(options!=previous,"nested option equality omitted a changed field");
        const auto& result=cache.solve(0,cells,options);
        require(cache.completed_solve_count()==++expected,"changed nested option reused an old accuracy certificate");
        require(result.options==options && result.solution.monthly_refinement_confirmations==2,
                "changed options were not retained and verified");
    };
    changed([](auto& o){o.atmosphere.mean_surface_pressure_pa+=100;});
    changed([](auto& o){o.atmosphere.reference_infrared_optical_depth+=0.1;});
    changed([](auto& o){o.stellar_luminosity*=1.01;});
    changed([](auto& o){o.integration.monthly_temperature_tolerance_k*=0.5;});
    changed([](auto& o){o.integration.periodic.phase_tolerance_k*=0.5;});
    changed([](auto& o){o.integration.periodic.step.absolute_tolerance_w_m2*=0.5;});
    changed([](auto& o){--o.integration.maximum_total_step_attempts;});
    changed([](auto& o){--o.maximum_stored_forcing_values;});
    changed([](auto& o){o.forcing_refinement_level=1;});
    changed([&](auto& o){
        o.integration.periodic.thermal_subdivisions.assign(cache.last_result()->forcing_intervals.size(),2);
    });
    options.integration.periodic.thermal_subdivisions[0]=4;
    require(cache.last_result()->options.integration.periodic.thermal_subdivisions[0]==2,
            "caller-owned subdivision vector mutated the private options snapshot");
    cache.solve(0,cells,options);
    require(cache.completed_solve_count()==++expected,
            "changed subdivision vector reused a preceding temporal accuracy certificate");

    const auto previous_pressure=cache.last_result()->physical_columns.surface_pressure_pa;
    cells[1].elevation_m+=100;
    cache.solve(0,cells,options);
    require(cache.completed_solve_count()==++expected &&
            cache.last_result()->physical_columns.surface_pressure_pa!=previous_pressure,
            "changed exposed height reused the preceding atmospheric coefficients");
    auto different_size=mesh(0,16);
    cache.solve(0,different_size,options);
    require(cache.completed_solve_count()==++expected && !cache.last_solve_was_warm_started(),
            "changed cell count reused a phase vector with incompatible shape");
    auto different_backend=mesh(1,12);
    cache.solve(1,different_backend,options);
    require(cache.completed_solve_count()==++expected && cache.last_result()->mesh_backend==1,
            "changed mesh backend did not rebuild its verified system");

    auto moved=std::move(cache);
    require(cache.last_result()==nullptr && moved.completed_solve_count()==expected,
            "moving the cache did not transfer private certificate ownership");
    require(&moved.solve(1,different_backend,options)==moved.last_result() && moved.completed_solve_count()==expected,
            "moved exact input snapshot no longer hits");

    PrescribedSeasonalClimateCache initially_failing;
    auto invalid=options; invalid.top_of_atmosphere_albedo=2;
    rejects([&]{initially_failing.solve(0,cells,invalid);},"invalid first solve was accepted");
    require(initially_failing.last_result()==nullptr && initially_failing.completed_solve_count()==0,
            "failed first solve published a certificate");
}
}  // namespace

int main() {
    try {
        owning_certificate_and_changed_surface();
        every_consumed_geometry_field_is_checked();
        nested_options_and_changed_shape();
    } catch (const std::exception& error) {
        std::cerr<<error.what()<<'\n'; return 1;
    }
    return 0;
}
