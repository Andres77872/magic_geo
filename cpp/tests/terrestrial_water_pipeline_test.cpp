#include "world.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

using namespace magic_geo::detail;
namespace {
int assertions = 0;
void require(bool ok, const char* message) {
    ++assertions;
    if (!ok) throw std::runtime_error(message);
}
template<class F> void rejects(F fn, const char* code) {
    try { fn(); }
    catch (const TerrestrialWaterError& error) {
        require(error.code == code, "unexpected refusal code");
        return;
    }
    throw std::runtime_error(std::string("missing refusal: ") + code);
}
EarthSystemState fixture() {
    EarthSystemState earth;
    earth.cells.resize(3);
    for (int i=0; i<3; ++i) {
        auto& c=earth.cells[i]; c.id=i; c.area_km2=2e-6;
        c.p={1.0,0.0,0.0}; c.temperature_c=-20; c.precipitation_mm_y=120;
    }
    earth.cells[1].is_water=true;
    earth.cells[2].is_lake=true;
    return earth;
}
TerrestrialWaterProperties properties() {
    return {{8,2,4,16},1000,8,{1,0,0}};
}
TerrestrialWaterRestart restart() {
    TerrestrialWaterRestart value; value.state.resize(3); return value;
}
TerrestrialIntervalRequest pulse() {
    return {0,1,{16,0,0},{{"snow-1",0,cryosphere_prototype::Phase::solid,4,8}}, {}};
}
}
int main() {
    try {
        auto earth=fixture();
        rejects([&] { (void)begin_terrestrial_water_epoch(earth,properties(),restart()); },"surface_not_finalized");
        require(!earth.terrestrial_surface_epoch,"premature start published epoch");
        earth.terrestrial_surface_finalized=true;
        if (!terrestrial_water_capability().available) {
            rejects([&] { (void)begin_terrestrial_water_epoch(earth,properties(),restart()); },"capability_unavailable");
            require(!earth.terrestrial_surface_epoch,"unavailable initialization published epoch");
            std::cout << "pipeline capability refusal: " << assertions << " assertions\n";
            return 0;
        }
        auto bad=restart(); bad.state[2].water_mass_kg_m2=1;
        rejects([&] { (void)begin_terrestrial_water_epoch(earth,properties(),bad); },"invalid_restart");
        require(!earth.terrestrial_surface_epoch,"invalid restart published epoch");
        auto owner=begin_terrestrial_water_epoch(earth,properties(),restart(),7);
        require(earth.terrestrial_surface_epoch.has_value(),"epoch was not retained");
        require(owner.surface().surface_revision()==7,"context revision changed");
        rejects([&] { (void)begin_terrestrial_water_epoch(earth,properties(),restart()); },"epoch_already_started");
        const auto candidate=prepare_terrestrial_water_interval(earth,owner,pulse());
        require(owner.restart().revision==0,"prepare published restart");
        require(candidate.receipt().liquid_outbox.empty(),"melting generated an unrequested withdrawal");
        auto other=fixture(); other.terrestrial_surface_finalized=true;
        auto other_owner=begin_terrestrial_water_epoch(other,properties(),restart(),7);
        rejects([&] { (void)prepare_terrestrial_water_interval(other,owner,pulse()); },"epoch_mismatch");
        rejects([&] { commit_terrestrial_water_interval(other,owner,candidate); },"epoch_mismatch");
        require(owner.restart().revision==0&&other_owner.restart().revision==0,"foreign epoch changed restart");
        earth.cells[0].is_lake=true;
        rejects([&] { (void)prepare_terrestrial_water_interval(earth,owner,pulse()); },"surface_changed");
        rejects([&] { commit_terrestrial_water_interval(earth,owner,candidate); },"surface_changed");
        require(owner.restart().revision==0,"changed domain committed candidate");
        earth.cells[0].is_lake=false;
        earth.cells[0].temperature_c+=1;
        rejects([&] { commit_terrestrial_water_interval(earth,owner,candidate); },"surface_changed");
        earth.cells[0].temperature_c-=1;
        commit_terrestrial_water_interval(earth,owner,candidate);
        require(owner.restart().revision==1&&owner.restart().elapsed_seconds==1,"commit clock failed");
        require(owner.restart().state[0].water_mass_kg_m2==2&&owner.restart().state[0].enthalpy_j_m2==16,"committed W/H changed");
        require(earth.cells[0].precipitation_mm_y==120&&earth.cells[0].temperature_c==-20&&earth.cells[0].runoff_mm_y==0,"interval overwrote generated climate/hydrology");
        rejects([&] { commit_terrestrial_water_interval(earth,owner,candidate); },"stale_candidate");
        require(owner.restart().revision==1,"replay advanced restart");
        std::cout << "pipeline epoch entry: " << assertions << " assertions\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
