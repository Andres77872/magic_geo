#include "solar_calendar.hpp"
#include <bit>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <tuple>

namespace {
using namespace magic_geo::detail;
int checks=0,misses=0,prepares=0,commits=0;
void check(bool ok,const std::string& name){
    ++checks;if(!ok)++misses;
    std::cout<<"{\"kind\":\"check\",\"name\":\""<<name<<"\",\"passed\":"<<(ok?"true":"false")<<"}\n";
}
template<class F> void refusal(F f,const std::string& name,const std::string& expected="solar_calendar_refusal"){
    std::string code,detail;try{f();}catch(const TerrestrialWaterError& e){code=e.code;detail=e.what();}
    std::cout<<"{\"kind\":\"refusal\",\"name\":"<<std::quoted(name)<<",\"failure_code\":"<<std::quoted(code)
        <<",\"expected_failure_code\":"<<std::quoted(expected)<<",\"detail\":"<<std::quoted(detail)<<"}\n";
    check(code==expected,name);
}
SolarCalendarOptions options(){SolarCalendarOptions o;o.thermal_error_budget_j=10020;return o;}
void controls(){
    // Fixed integer stream, unrelated to world seeds or thermal integration.
    std::uint64_t stream=0x914f2ab7c05533e1ULL;
    const auto next=[&](){stream^=stream<<13;stream^=stream>>7;stream^=stream<<17;return stream;};
    for(int i=0;i<512;++i){
        const auto mantissa=next()&0xfffffffffffffULL;
        const auto exponent=next()%1023;
        const double f=std::bit_cast<double>((exponent<<52)|mantissa);
        const auto n=(next()&0xfffffffffffffULL)+4503599627370496ULL;
        const auto k=round_solar_calendar_tick(f,n);
        std::cout<<"{\"kind\":\"round\",\"fraction\":"<<f<<",\"year_ticks\":"<<n<<",\"tick\":"<<k<<"}\n";
        check(k<=n,"round_range_"+std::to_string(i));
    }
    for(const auto& [f,n,k]:std::vector<std::tuple<double,std::uint64_t,std::uint64_t>>{
        {0,1,0},{1,9007199254740992ULL,9007199254740992ULL},{.5,1,0},{.5,3,2},{.5,5,2},
        {std::numeric_limits<double>::denorm_min(),9007199254740992ULL,0},
        {std::nextafter(.5,1.),1,1},{std::nextafter(.5,0.),1,0}}){
        const auto actual=round_solar_calendar_tick(f,n);
        std::cout<<"{\"kind\":\"round\",\"fraction\":"<<f<<",\"year_ticks\":"<<n<<",\"tick\":"<<actual<<"}\n";
        check(actual==k,"round_boundary");
    }
    refusal([]{round_solar_calendar_tick(-.1,1);},"negative_fraction");
    refusal([]{round_solar_calendar_tick(1.1,1);},"excess_fraction");
    refusal([]{round_solar_calendar_tick(.5,0);},"zero_ticks");
    refusal([]{round_solar_calendar_tick(.5,9007199254740993ULL);},"excess_ticks");
    refusal([]{round_solar_calendar_tick(std::numeric_limits<double>::quiet_NaN(),1);},"nan_fraction");
    const std::vector<double> latitudes={-std::numbers::pi/2,-1,-.2,0,.4,1,std::numbers::pi/2};
    std::size_t calendar_index=0;
    for(const auto& [tilt,e]:std::vector<std::pair<double,double>>{{0,0},{23.5,.016},{90,.8},{40,.99}}){
        auto o=options();o.axial_tilt_deg=tilt;o.orbital_eccentricity=e;
        const auto c=build_solar_calendar(latitudes,o);
        std::cout<<"{\"kind\":\"calendar\",\"calendar_index\":"<<calendar_index<<",\"calendar\":"<<solar_calendar_json(c)<<"}\n";
        const SolarOrbitForcing original(tilt,e,o.stellar_luminosity,o.forcing_refinement_level);
        std::cout<<"{\"kind\":\"orbital_reference\",\"calendar_index\":"<<calendar_index++<<",\"intervals\":[";
        for(std::size_t j=0;j<original.integration_intervals().size();++j){
            if(j)std::cout<<',';
            const auto& a=original.integration_intervals()[j];
            std::cout<<"{\"month_index\":"<<a.month_index<<",\"duration_fraction_of_year\":"<<a.duration_fraction_of_year
                <<",\"declination_rad\":"<<a.declination_rad<<",\"inverse_square_distance_factor\":"<<a.inverse_square_distance_factor
                <<",\"mean_anomaly_begin_rad\":"<<a.mean_anomaly_begin_rad<<",\"mean_anomaly_end_rad\":"<<a.mean_anomaly_end_rad
                <<",\"end_fraction_of_year\":"<<a.end_fraction_of_year<<",\"absorbed_shortwave_w_m2\":[";
            for(std::size_t k=0;k<latitudes.size();++k){if(k)std::cout<<',';
                std::cout<<(1-o.top_of_atmosphere_albedo)*original.interval_mean_insolation_w_m2(latitudes[k],j);}
            std::cout<<"]}";
        }
        std::cout<<"]}\n";
        check(c.windows().size()>=360 && c.windows().size()<=1128,"whole_orbit_window_count");
        check(c.windows().front().begin_tick==0 && c.windows().back().end_tick==c.year_ticks(),"whole_orbit_endpoints");
        refusal([&]{c.require_owner_capacity({});},"legacy_owner_capacity_refused");
        EnthalpyMeshOwnerLimits limits;limits.max_committed_intervals=2048;limits.max_prepare_attempts=4096;
        c.require_owner_capacity(limits);check(true,"explicit_owner_capacity_admitted");
        limits.max_identifier_bytes=1;
        refusal([&]{c.require_owner_capacity(limits);},"forcing_identifier_capacity_refused");
        limits.max_identifier_bytes=96;
        limits.max_stored_forcing_values=1;
        refusal([&]{c.require_owner_capacity(limits);},"forcing_value_capacity_refused");
    }
    auto o=options();o.maximum_windows=1;
    refusal([&]{build_solar_calendar(latitudes,o);},"orbital_reservation_before_work");
    o=options();o.forcing_refinement_level=1;
    refusal([&]{build_solar_calendar(latitudes,o);},"refinement_reservation_refused");
    o=options();o.thermal_error_budget_j=0;
    refusal([&]{build_solar_calendar(latitudes,o);},"zero_annual_budget");
    o=options();o.year_duration_seconds=std::numeric_limits<double>::denorm_min();
    refusal([&]{build_solar_calendar(latitudes,o);},"collapsed_clock_refused");
    o=options();o.id="bad id";
    refusal([&]{build_solar_calendar(latitudes,o);},"calendar_identifier_refused");
    o=options();refusal([&]{build_solar_calendar({},o);},"empty_latitudes");
    refusal([&]{build_solar_calendar({2},o);},"invalid_latitude");
    o=options();o.stellar_luminosity=std::numeric_limits<double>::denorm_min();o.top_of_atmosphere_albedo=std::nextafter(1.,0.);
    refusal([&]{build_solar_calendar({0},o);},"positive_absorbed_underflow_refused");
}
struct Fixture {
    std::vector<Cell> cells;
    EnthalpyMeshProperties properties;
    EnthalpyMeshRestart initial;
    EnthalpyMeshIntervalRequest request;
};
Fixture fixture(){
    Fixture f;f.cells.resize(2);
    for(int i=0;i<2;++i){auto& c=f.cells[i];c.id=i;c.p={1,0,0};c.area_km2=(i+1)*1e-6;
        c.temperature_c=10;c.precipitation_mm_y=120;c.neighbors={1-i};}
    f.properties={{1,1,1,1},1000,31557600,{{1,3,0},{2,2,0}},{{0,1,.125}}};
    f.initial.state={{1,3},{0,-.5}};f.initial.canonical_energy_error_j=.01;
    f.request.end_seconds=.125;f.request.forcing={"quota-0",0,.125,{1,.25}};
    f.request.imports={{"quota-snow",0,cryosphere_prototype::Phase::solid,.125,1}};
    f.request.options={.125,0,8,8,1e-11,128,64,32768,32};
    f.request.maximum_thermal_error_increment_j=.005;return f;
}
void inventory(){
    std::cout<<"{\"schema\":\"solar_calendar_quota_inventory_v1\",\"execution\":\"none\",\"calendars\":[";
    std::size_t index=0;
    for(const auto& [tilt,e]:std::vector<std::pair<double,double>>{{0,0},{23.5,.016},{90,.8},{40,.99}}){
        if(index)std::cout<<',';
        const auto o=options();
        std::cout<<"{\"calendar_index\":"<<index++<<",\"options\":{\"id\":\"solar-year-0\",\"axial_tilt_deg\":"<<tilt
            <<",\"orbital_eccentricity\":"<<e<<",\"stellar_luminosity\":"<<o.stellar_luminosity
            <<",\"year_duration_seconds\":"<<o.year_duration_seconds<<",\"top_of_atmosphere_albedo\":"<<o.top_of_atmosphere_albedo
            <<",\"thermal_error_budget_j\":"<<o.thermal_error_budget_j<<",\"forcing_refinement_level\":"<<o.forcing_refinement_level
            <<",\"maximum_windows\":"<<o.maximum_windows<<",\"maximum_stored_forcing_values\":"<<o.maximum_stored_forcing_values
            <<"},\"latitudes_rad\":["<<-std::numbers::pi/2<<",-1,-0.20000000000000001,0,0.40000000000000002,1,"<<std::numbers::pi/2<<"]}";
    }
    std::cout<<"],\"fixtures\":[";
    for(int i=0;i<5;++i){
        if(i)std::cout<<',';
        auto f=fixture();EnthalpyMeshOwnerReceipt d;d.surface_revision=71;d.surface_cells=f.cells;d.properties=f.properties;
        d.maximum_cumulative_error_j=.1;d.initial=f.initial;d.observed_accepted_after=f.initial;d.private_prefix=f.initial;
        std::string id="first",owner_id="main",binding,expected;
        if(i==1){id="second";binding="first";d.initial={};d.observed_accepted_after={};d.private_prefix={};
            f.request.expected_revision=1;f.request.end_seconds=.25;f.request.forcing={"quota-1",.125,.25,{.5,0}};f.request.imports.clear();}
        if(i==2){id="strict_quota";owner_id=id;expected="work_cap";f.request.imports.clear();
            f.request.maximum_thermal_error_increment_j=1e-30;f.request.options.maximum_attempts=1;}
        if(i==3){id="invalid_quota";owner_id=id;expected="invalid_input";f.request.maximum_thermal_error_increment_j=0;}
        if(i==4){id="history_cap";owner_id=id;expected="forcing_refusal";d.limits.max_stored_forcing_values=1;}
        d.request=f.request;
        std::cout<<"{\"id\":\""<<id<<"\",\"owner_id\":\""<<owner_id<<"\",\"initial_binding\":\""<<binding
            <<"\",\"expected_failure\":\""<<expected<<"\",\"unexecuted_context_and_request\":"<<enthalpy_mesh_owner_receipt_json(d)<<'}';
    }
    std::cout<<"],\"prepare_cap\":5,\"commit_cap\":2,\"thermal_call_cap\":17,\"mass_call_cap\":1}\n";
}
EnthalpyMeshPreparation prepare(EnthalpyMeshOwner& owner,const EnthalpyMeshIntervalRequest& q,const std::string& id){
    if(++prepares>5)throw std::runtime_error("prepare cap");
    const auto before=enthalpy_mesh_owner_context_json(owner);const auto result=owner.prepare(q);
    std::cout<<"{\"kind\":\"prepare\",\"id\":\""<<id<<"\",\"owner_id\":\""<<((id=="first" || id=="second")?"main":id)<<"\",\"context_before\":"<<before
        <<",\"request\":"<<enthalpy_mesh_interval_request_json(q)<<",\"receipt\":"<<enthalpy_mesh_owner_receipt_json(*result.diagnostic)
        <<",\"context_after\":"<<enthalpy_mesh_owner_context_json(owner)<<"}\n";
    check(enthalpy_mesh_restart_json(result.diagnostic->initial)==enthalpy_mesh_restart_json(owner.restart()),id+"_prepare_atomic");
    check(result.candidate.has_value()==result.diagnostic->prepared,id+"_candidate");
    return result;
}
void commit(EnthalpyMeshOwner& owner,const EnthalpyMeshIntervalCandidate& candidate,const std::string& id){
    if(++commits>2)throw std::runtime_error("commit cap");
    const auto before=enthalpy_mesh_owner_context_json(owner);owner.commit(candidate);
    std::cout<<"{\"kind\":\"commit\",\"id\":\""<<id<<"\",\"owner_id\":\"main\",\"candidate_id\":\""<<id
        <<"\",\"success\":true,\"failure_code\":\"\",\"before\":"<<before
        <<",\"after\":"<<enthalpy_mesh_owner_context_json(owner)<<"}\n";
    check(enthalpy_mesh_restart_json(owner.restart())==enthalpy_mesh_restart_json(*candidate.receipt().final),id+"_whole_bundle");
}
void ownership(){
    auto f=fixture();EnthalpyMeshOwnerLimits limits;
    {auto raised=limits;raised.max_committed_intervals=2048;raised.max_prepare_attempts=4096;raised.max_stored_forcing_values=2097152;
        EnthalpyMeshOwner admitted(capture_terrestrial_surface(f.cells,71),f.properties,f.initial,.1,raised);
        check(admitted.limits().max_committed_intervals==2048,"explicit_owner_hard_caps_admitted");
        raised.max_committed_intervals=2049;
        refusal([&]{EnthalpyMeshOwner rejected(capture_terrestrial_surface(f.cells,71),f.properties,f.initial,.1,raised);},"owner_hard_cap_refused","invalid_limits");}
    EnthalpyMeshOwner owner(capture_terrestrial_surface(f.cells,71),f.properties,f.initial,.1,limits);
    const auto first=prepare(owner,f.request,"first");check(first.candidate.has_value(),"first_accepted");
    if(first.candidate){
        check(first.diagnostic->trials.front().headroom_lower_j==.005,"first_fixed_thermal_quota");
        commit(owner,*first.candidate,"first");
        auto q=f.request;q.expected_revision=1;q.end_seconds=.25;q.forcing={"quota-1",.125,.25,{.5,0}};q.imports.clear();
        const auto second=prepare(owner,q,"second");check(second.candidate.has_value(),"second_accepted");
        if(second.candidate){
            check(second.diagnostic->trials.front().headroom_lower_j==.005,"second_fixed_thermal_quota");
            check(second.diagnostic->initial.canonical_energy_error_j==first.diagnostic->final->canonical_energy_error_j,"error_carried");
            commit(owner,*second.candidate,"second");
            check(owner.restart().forcing_history.size()==2 && owner.restart().consumed_event_ids==std::vector<std::string>{"quota-snow"},"complete_history");
        }
    }
    {EnthalpyMeshOwner strict(capture_terrestrial_surface(f.cells,71),f.properties,f.initial,.1,limits);
        auto q=f.request;q.imports.clear();q.maximum_thermal_error_increment_j=1e-30;q.options.maximum_attempts=1;
        const auto r=prepare(strict,q,"strict_quota");check(!r.candidate && r.diagnostic->failure_code=="work_cap" && r.diagnostic->trials.size()==1,"strict_quota_one_trial_refusal");}
    {EnthalpyMeshOwner invalid(capture_terrestrial_surface(f.cells,71),f.properties,f.initial,.1,limits);
        auto q=f.request;q.maximum_thermal_error_increment_j=0;const auto r=prepare(invalid,q,"invalid_quota");
        check(!r.candidate && r.diagnostic->failure_code=="invalid_input" && !r.diagnostic->mass_call_started && r.diagnostic->trials.empty(),"invalid_quota_before_physics");}
    {limits.max_stored_forcing_values=1;
        EnthalpyMeshOwner small(capture_terrestrial_surface(f.cells,71),f.properties,f.initial,.1,limits);
        const auto r=prepare(small,f.request,"history_cap");
        check(!r.candidate && r.diagnostic->failure_code=="forcing_refusal" && !r.diagnostic->mass_call_started && r.diagnostic->trials.empty(),"history_cap_before_physics");}
    check(prepares==5 && commits==2,"bounded_owner_invocations");
}
}
int main(int argc,char** argv){
    if(argc!=2)return 2;
    std::cout<<std::setprecision(17);
    try{const std::string mode=argv[1];if(mode=="--inventory"){inventory();return 0;}else if(mode=="controls")controls();else if(mode=="owner")ownership();else return 2;}
    catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 3;}
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<checks<<",\"misses\":"<<misses<<",\"prepares\":"<<prepares<<",\"commits\":"<<commits<<"}\n";
    return misses?1:0;
}
