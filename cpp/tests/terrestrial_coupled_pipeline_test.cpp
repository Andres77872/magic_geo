#include "world.hpp"
#include <iostream>
#include <stdexcept>

using namespace magic_geo::detail;
namespace p = phase_segment_prototype;
namespace {
int checks=0;
void require(bool x,const char *why) {++checks;if(!x)throw std::runtime_error(why);}
template<class F> void refuses(F f,const char *code) {
    try {f();} catch(const TerrestrialWaterError &e) {require(e.code==code,e.what());return;}
    throw std::runtime_error(std::string("missing refusal ")+code);
}
EarthSystemState fixture() {
    EarthSystemState x;x.cells.resize(3);
    for(int i=0;i<3;++i) {auto &c=x.cells[i];c.id=i;c.area_km2=1e-6;c.p={1,0,0};
        c.temperature_c=-20;c.precipitation_mm_y=120;}
    x.cells[1].is_water=true;x.cells[2].is_lake=true;return x;
}
CoupledProperties props() {return {{1,1,1,1},1000,8,{{10,10,.5,0,.3},{},{}}};}
CoupledRestart initial() {
    CoupledRestart x;x.state={{0,1,1},{},{}};x.canonical_energy_error_j_m2={0,0,0};return x;
}
CoupledIntervalPlan plan() {
    CoupledSegmentPlan segment{"remainder",p::Branch::dry,p::Goal::within_branch,.0625,
        {{.5,1.5},{.5,1.5}},{1e-8,1e-10,.001,1e-4},{},{},false};
    return {0,.0625,{"sun",0,1,{1,0,0}},{},{},{{0,{segment}}}};
}
}
int main() {
    try {
        auto x=fixture();
        refuses([&]{(void)begin_terrestrial_coupled_epoch(x,props(),initial(),{.01});},"surface_not_finalized");
        require(!x.terrestrial_surface_epoch,"premature epoch");
        x.terrestrial_surface_finalized=true;
        if(!terrestrial_water_capability().available) {
            refuses([&]{(void)begin_terrestrial_coupled_epoch(x,props(),initial(),{.01});},"capability_unavailable");
            require(!x.terrestrial_surface_epoch&&x.terrestrial_owner_mode==TerrestrialOwnerMode::none,"unavailable published epoch");
            auto r=p::advance_phase_segment({});
            require(!r.accepted&&r.failure_code=="capability_unavailable","unavailable phase stub");
            std::cout<<"coupled unavailable: "<<checks<<" checks; 0 solver stages\n";return 0;
        }
        auto owner=begin_terrestrial_coupled_epoch(x,props(),initial(),{.01},9);
        require(x.terrestrial_owner_mode==TerrestrialOwnerMode::coupled_energy,"wrong owner mode");
        refuses([&]{(void)begin_terrestrial_coupled_epoch(x,props(),initial(),{.01});},"epoch_already_started");
        TerrestrialWaterProperties wp{{1,1,1,1},1000,8,{10,0,0}};
        TerrestrialWaterRestart wr;wr.state={{0,1},{},{}};
        refuses([&]{(void)begin_terrestrial_water_epoch(x,wp,wr);},"epoch_already_started");
        // A manually constructed opposite-mode owner cannot bypass the epoch claim.
        TerrestrialWaterOwner opposite(owner.surface(),wp,wr);
        refuses([&]{(void)prepare_terrestrial_water_interval(x,opposite,{0,1,{0,0,0},{},{}});},"owner_mode_mismatch");
        auto prepared=prepare_terrestrial_coupled_interval(x,owner,plan());
        if(!prepared.candidate) throw std::runtime_error(prepared.diagnostic->failure_code+": "+prepared.diagnostic->detail);
        require(owner.restart().revision==0,"prepare committed");
        auto other=fixture();other.terrestrial_surface_finalized=true;
        auto foreign=begin_terrestrial_coupled_epoch(other,props(),initial(),{.01},9);
        refuses([&]{commit_terrestrial_coupled_interval(other,owner,*prepared.candidate);},"epoch_mismatch");
        x.cells[0].is_lake=true;
        refuses([&]{commit_terrestrial_coupled_interval(x,owner,*prepared.candidate);},"surface_changed");
        x.cells[0].is_lake=false;
        x.cells[0].temperature_c+=1;
        refuses([&]{(void)prepare_terrestrial_coupled_interval(x,owner,plan());},"surface_changed");
        x.cells[0].temperature_c-=1;
        require(owner.restart().revision==0,"refusal changed revision");
        commit_terrestrial_coupled_interval(x,owner,*prepared.candidate);
        require(owner.restart().revision==1&&owner.restart().elapsed_seconds==.0625,"clock commit");
        require(owner.restart().state[0].surface_enthalpy_j_m2>1,"solar heating missing");
        require(owner.restart().state[0].atmospheric_energy_j_m2<1,"air cooling missing");
        require(terrestrial_surface_matches(owner.surface(),x.cells),"generated fields changed");
        require(x.cells[0].precipitation_mm_y==120&&x.cells[0].temperature_c==-20&&x.cells[0].runoff_mm_y==0,"generated climate/hydrology changed");
        require(foreign.restart().revision==0,"foreign state changed");
        refuses([&]{commit_terrestrial_coupled_interval(x,owner,*prepared.candidate);},"stale_candidate");
        std::cout<<"coupled pipeline: "<<checks<<" checks; "<<owner.work_meter().segment_calls_started<<" segment calls\n";
        std::cout<<coupled_attempt_receipt_json(*prepared.diagnostic)<<'\n';
    }catch(const std::exception &e) {std::cerr<<e.what()<<'\n';return 1;}
}
