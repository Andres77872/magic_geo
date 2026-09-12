#include "finalized_enthalpy_context.hpp"
#include "internal.hpp"
#include "world.hpp"

#include <bit>
#include <fstream>
#include <iostream>
#include <limits>

using namespace magic_geo;
using namespace magic_geo::detail;
namespace {
int checks=0;
void require(bool ok,const char* message) { ++checks; if(!ok) throw std::runtime_error(message); }
bool same(double x,double y) { return std::bit_cast<std::uint64_t>(x)==std::bit_cast<std::uint64_t>(y); }
template<class F> void refuses(F f,const char* code) {
    try { f(); }
    catch(const TerrestrialWaterError& e) { require(e.code==code,e.what()); return; }
    throw std::runtime_error(std::string("missing refusal: ")+code);
}
template<class F> void invalid_geometry(F f) {
    try { f(); } catch(const std::runtime_error&) { ++checks; return; }
    throw std::runtime_error("malformed geometry accepted");
}
Params params() {
    Params p; p.name="finalized_enthalpy_context_integration"; p.cell_count=128;
    p.plate_count=8; p.erosion_iterations=0; p.threads=1; p.float_precision=8;
    return p;
}
void emit(const char* name,const FinalizedEnthalpyContext& c) {
    std::cout<<"{\"case\":\""<<name<<"\",\"context\":"<<finalized_enthalpy_context_json(c)<<"}\n";
}
void lake(Cell& c,int sink,int component,double bed,double spill,double fill,double diagnostic) {
    c.is_water=false; c.is_lake=true; c.water_body=4; c.depression_component_id=component;
    c.depression_sink_cell_id=sink; c.elevation_m=bed; c.spill_elevation_m=spill;
    c.lake_fill_fraction=fill; c.water_depth_m=diagnostic;
}
void controls() {
    auto p=params(); auto cells=build_mesh(p);
    for (auto& c:cells) { c.elevation_m=100; c.temperature_c=5; c.precipitation_mm_y=120; }
    FinalizedEnthalpyOptions o;
    auto dry=build_finalized_enthalpy_context(cells,p,o,17);
    emit("dry_uniform",dry);
    require(dry.lakes().empty() && !dry.properties().edges.empty(),"dry graph missing");
    for(std::size_t i=0;i<cells.size();++i) {
        require(same(dry.properties().columns[i].area_m2,cells[i].area_km2*1e6),"noncanonical owner area");
        require(dry.physical_columns().surface_pressure_pa[i]==100000,"uniform pressure changed");
    }
    // One deep clipped lake, one shallower than the display floor, a marine
    // column and a correctly dry saline basin on actual production geometry.
    lake(cells[0],0,8,100,1100,.5,240);
    lake(cells[1],0,8,599.95,1100,.5,.2);
    cells[2].is_water=true; cells[2].water_body=1; cells[2].elevation_m=-1000; cells[2].water_depth_m=1000;
    cells[3].water_body=5;
    cells[4].depression_component_id=8; cells[4].depression_sink_cell_id=0;
    cells[4].lake_fill_fraction=.5; cells[4].elevation_m=700;
    refuses([&]{(void)build_finalized_enthalpy_context(cells,p,o);},"lake_depth_policy_required");
    o.lake_mixed_layer_depth_m=300;
    auto c=build_finalized_enthalpy_context(cells,p,o,18); emit("mixed_clipped_lakes",c);
    require(c.lakes().size()==2 && c.lakes()[0].reconstructed_depth_m==500,"deep lake was clipped");
    require(c.lakes()[0].mixed_layer_depth_m==300,"lake cap uses clipped diagnostic");
    require(c.lakes()[1].reconstructed_depth_m<.2 && c.lakes()[1].mixed_layer_depth_m<.2,"display floor created storage");
    require(c.surfaces()[0].interface_elevation_m==600 && c.surfaces()[1].interface_elevation_m==600,"lake free surface mismatch");
    require(c.surfaces()[2].interface_elevation_m==0,"marine pressure datum mismatch");
    require(c.surfaces()[3].surface_heat_capacity_j_m2_k==4e6,"dry saline basin made wet");
    require(c.physical_columns().surface_pressure_pa[8]!=dry.physical_columns().surface_pressure_pa[8],"global pressure normalization stayed stale");
    require(c.physical_columns().columns[8].heat_capacity_j_m2_k!=dry.physical_columns().columns[8].heat_capacity_j_m2_k,"global atmospheric capacity stayed stale");
    require(c.matches(cells,p),"fresh context mismatch");
    auto x=cells; x[0].lake_fill_fraction=.6;
    require(terrestrial_surface_matches(c.surface(),x) && !c.matches(x,p),"extended fill guard missing");
    x=cells; x[0].spill_elevation_m+=1; require(!c.matches(x,p),"spill guard missing");
    x=cells; x[1].depression_sink_cell_id=1; require(!c.matches(x,p),"sink guard missing");
    x=cells; x[1].depression_component_id=9; require(!c.matches(x,p),"component guard missing");
    x=cells; x[0].hydrologic_surface_elevation_m+=10000;
    auto routing=build_finalized_enthalpy_context(x,p,o); require(c.matches(x,p),"unused routing surface bound as a lake head");
    require(routing.surfaces()[0].interface_elevation_m==600,"conditioned routing surface changed pressure");
    auto changed=p; changed.atmosphere_pressure_bar=2; require(!c.matches(cells,changed),"pressure guard missing");
    changed=p; changed.gravity_g=2; require(!c.matches(cells,changed),"gravity guard missing");
    changed=p; changed.radius_km+=1; require(!c.matches(cells,changed),"radius guard missing");
    changed=p; changed.greenhouse_factor=2; require(!c.matches(cells,changed),"greenhouse guard missing");
    changed=p; changed.reference_infrared_optical_depth=2; require(!c.matches(cells,changed),"optical depth guard missing");
    changed=p; changed.mesh_backend=1; require(!c.matches(cells,changed),"backend guard missing");
    for(int kind=0;kind<8;++kind) {
        x=cells;
        if(kind==0) x[0].water_depth_m=239;
        if(kind==1) x[1].lake_fill_fraction=.25;
        if(kind==2) x[1].is_lake=false;
        if(kind==3) x[4].depression_component_id=9;
        if(kind==4) x[0].depression_sink_cell_id=-1;
        if(kind==5) x[0].spill_elevation_m=std::numeric_limits<double>::infinity();
        if(kind==6) x[0].lake_fill_fraction=std::numeric_limits<double>::quiet_NaN();
        if(kind==7) x[1].water_body=5;
        refuses([&]{(void)build_finalized_enthalpy_context(x,p,o);},"invalid_finalized_lake");
    }
    x=cells; x[1].is_lake=false; x[1].water_body=0; x[1].water_depth_m=0;
    x[0].lake_fill_fraction=0; x[1].lake_fill_fraction=0; x[4].lake_fill_fraction=0; x[0].water_depth_m=.2;
    refuses([&]{(void)build_finalized_enthalpy_context(x,p,o);},"invalid_finalized_lake");
    auto bad_options=o; bad_options.lake_mixed_layer_depth_m=0;
    refuses([&]{(void)build_finalized_enthalpy_context(cells,p,bad_options);},"invalid_finalized_context");
    x=cells; x[2].water_depth_m=999;
    refuses([&]{(void)build_finalized_enthalpy_context(x,p,o);},"invalid_finalized_surface");
    x=cells; x[3].water_depth_m=.2;
    refuses([&]{(void)build_finalized_enthalpy_context(x,p,o);},"invalid_finalized_surface");
    x=cells; x[3].lat+=.1;
    refuses([&]{(void)build_finalized_enthalpy_context(x,p,o);},"invalid_finalized_geometry");
    x=cells; x[3].control_volume_vertices[0].x+=.1;
    invalid_geometry([&]{(void)build_finalized_enthalpy_context(x,p,o);});
    x=cells; x[3].neighbors.resize(4*EnthalpyMeshOwnerLimits{}.max_edges+1,0);
    refuses([&]{(void)build_finalized_enthalpy_context(x,p,o);},"invalid_finalized_context");
    changed=p; changed.radius_km*=2;
    refuses([&]{(void)build_finalized_enthalpy_context(cells,changed,o);},"invalid_finalized_geometry");
    // No atmosphere is still a validated geometric context, with positive
    // surface storage and no transport. Also exercise the other native mesh.
    changed=p; changed.atmosphere_pressure_bar=0;
    auto vacuum=build_finalized_enthalpy_context(cells,changed,o); emit("vacuum",vacuum);
    require(vacuum.properties().edges.empty(),"vacuum atmospheric heat transport");
    changed=p; changed.mesh_backend=1; changed.cell_count=12;
    auto geodesic=build_mesh(changed);
    auto g=build_finalized_enthalpy_context(geodesic,changed,{}); emit("geodesic",g);
    require(!g.properties().edges.empty(),"geodesic transport missing");
    std::cout<<"{\"case\":\"controls_summary\",\"checks\":"<<checks<<",\"thermal_calls\":0}\n";
}

void production(const char* output) {
    const auto p=params(); validate_params(p); ScopedThreadConfiguration threads(p.threads);
    auto world=simulate_world(p); auto& earth=world.earth;
    require(earth.terrestrial_surface_finalized && earth.finalized_enthalpy_planet.has_value(),"generation did not finalize provenance");
    const auto baseline=serialize_world(p,world);
    std::ofstream file(output,std::ios::binary); file<<baseline; file.close(); require(bool(file),"world evidence write failed");
    FinalizedEnthalpyOptions o; o.lake_mixed_layer_depth_m=10; // Explicit qualification parameter, not a universal recommendation.
    const auto initial_context=build_finalized_enthalpy_context(earth.cells,p,o,29);
    emit("production_finalized",initial_context);
    require(initial_context.lakes().size()==2,"healthy retained case lake count changed");
    EnthalpyMeshRestart restart; restart.state.resize(earth.cells.size());
    int first_land=-1;
    for(std::size_t i=0;i<earth.cells.size();++i) {
        const auto& c=earth.cells[i];
        if(!c.is_water && !c.is_lake) { restart.state[i].water_mass_kg_m2=1; if(first_land<0) first_land=static_cast<int>(i); }
    }
    require(first_land>=0,"no exposed source cell");
    const double area=initial_context.physical_columns().total_area_m2;
    const double budget=area*.01; // Global J: a declared area-mean .01 J/m2 budget.
    auto mismatch=p; mismatch.gravity_g=2;
    refuses([&]{(void)begin_finalized_enthalpy_epoch(earth,mismatch,o,restart,budget);},"finalized_planet_mismatch");
    require(!earth.terrestrial_surface_epoch,"failed planet binding published an epoch");
    auto invalid=restart; invalid.state.pop_back();
    refuses([&]{(void)begin_finalized_enthalpy_epoch(earth,p,o,invalid,budget);},"invalid_restart");
    require(!earth.terrestrial_surface_epoch,"failed restart published an epoch");
    earth.terrestrial_surface_finalized=false;
    refuses([&]{(void)begin_finalized_enthalpy_epoch(earth,p,o,restart,budget);},"surface_not_finalized");
    earth.terrestrial_surface_finalized=true;
    auto epoch=begin_finalized_enthalpy_epoch(earth,p,o,restart,budget,29);
    require(earth.terrestrial_owner_mode==TerrestrialOwnerMode::combined_enthalpy,"wrong owner mode");
    refuses([&]{(void)begin_finalized_enthalpy_epoch(earth,p,o,restart,budget);},"epoch_already_started");
    EnthalpyMeshIntervalRequest request; request.end_seconds=1;
    request.forcing={"prescribed-prefix",0,2,std::vector<double>(earth.cells.size(),400)};
    request.options.maximum_step_seconds=1; request.options.maximum_attempts=4; request.options.maximum_accepted_steps=4;
    request.options.maximum_stage_error_j=area*1e-8; request.options.maximum_sweeps=32;
    request.options.maximum_scalar_evaluations=131072;
    request.imports.push_back({"explicit-snow",first_land,cryosphere_prototype::Phase::solid,
        initial_context.surfaces()[static_cast<std::size_t>(first_land)].area_m2*.001,273.15});
    std::cout<<"{\"case\":\"production_before_first_prepare\",\"owner\":"<<enthalpy_mesh_owner_context_json(epoch.owner())<<"}\n";
    const auto prepared=prepare_finalized_enthalpy_interval(earth,p,epoch,request);
    std::cout<<"{\"case\":\"production_after_first_prepare\",\"owner\":"<<enthalpy_mesh_owner_context_json(epoch.owner())<<"}\n";
    std::cout<<"{\"case\":\"production_first\",\"receipt\":"<<enthalpy_mesh_owner_receipt_json(*prepared.diagnostic)<<"}\n";
    require(prepared.candidate.has_value(),prepared.diagnostic->failure_code.c_str());
    require(epoch.owner().restart().revision==0,"prepare committed a state");
    const int lake_id=epoch.context().lakes().front().cell_id;
    auto& lake_cell=earth.cells[static_cast<std::size_t>(lake_id)]; const double fill=lake_cell.lake_fill_fraction;
    lake_cell.lake_fill_fraction=std::nextafter(fill,std::numeric_limits<double>::infinity());
    refuses([&]{commit_finalized_enthalpy_interval(earth,p,epoch,*prepared.candidate);},"finalized_context_changed");
    refuses([&]{(void)prepare_finalized_enthalpy_interval(earth,p,epoch,request);},"finalized_context_changed");
    lake_cell.lake_fill_fraction=fill;
    refuses([&]{commit_finalized_enthalpy_interval(earth,mismatch,epoch,*prepared.candidate);},"finalized_context_changed");
    earth.finalized_enthalpy_planet->gravity_g=2;
    refuses([&]{commit_finalized_enthalpy_interval(earth,p,epoch,*prepared.candidate);},"finalized_planet_mismatch");
    earth.finalized_enthalpy_planet=finalized_enthalpy_planet_inputs(p);
    EarthSystemState other; other.cells=earth.cells; other.terrestrial_surface_finalized=true;
    other.finalized_enthalpy_planet=earth.finalized_enthalpy_planet;
    other.terrestrial_owner_mode=earth.terrestrial_owner_mode;
    other.terrestrial_surface_epoch=capture_terrestrial_surface(other.cells,29);
    refuses([&]{commit_finalized_enthalpy_interval(other,p,epoch,*prepared.candidate);},"epoch_mismatch");
    require(epoch.owner().work_meter().prepare_attempts==1,"context refusal entered the owner");
    commit_finalized_enthalpy_interval(earth,p,epoch,*prepared.candidate);
    std::cout<<"{\"case\":\"production_after_first_commit\",\"owner\":"<<enthalpy_mesh_owner_context_json(epoch.owner())<<"}\n";
    const double carried_error=epoch.owner().restart().canonical_energy_error_j;
    require(epoch.owner().restart().revision==1 && carried_error>0,"first commit error/clock missing");
    require(epoch.owner().work_meter().mass_calls_started==1,"snow source not consumed exactly once");
    refuses([&]{commit_finalized_enthalpy_interval(earth,p,epoch,*prepared.candidate);},"stale_candidate");
    request.expected_revision=1; request.end_seconds=2; request.imports.clear();
    std::cout<<"{\"case\":\"production_before_second_prepare\",\"owner\":"<<enthalpy_mesh_owner_context_json(epoch.owner())<<"}\n";
    const auto second=prepare_finalized_enthalpy_interval(earth,p,epoch,request);
    std::cout<<"{\"case\":\"production_after_second_prepare\",\"owner\":"<<enthalpy_mesh_owner_context_json(epoch.owner())<<"}\n";
    std::cout<<"{\"case\":\"production_second\",\"receipt\":"<<enthalpy_mesh_owner_receipt_json(*second.diagnostic)<<"}\n";
    require(second.candidate.has_value(),second.diagnostic->failure_code.c_str());
    require(second.diagnostic->initial.canonical_energy_error_j==carried_error,"global error did not carry to successor");
    commit_finalized_enthalpy_interval(earth,p,epoch,*second.candidate);
    require(epoch.owner().restart().elapsed_seconds==2 && epoch.owner().restart().revision==2,"physical prefix clock did not commit");
    require(epoch.owner().work_meter().mass_calls_started==1,"empty successor repeated the mass event");
    require(epoch.owner().restart().canonical_energy_error_j>=carried_error &&
        epoch.owner().restart().canonical_energy_error_j<=budget,"successor error reset or over budget");
    for(const auto& lake:epoch.context().lakes()) {
        const auto& state=epoch.owner().restart().state[static_cast<std::size_t>(lake.cell_id)];
        require(state.water_mass_kg_m2==0 && state.enthalpy_j_m2>0,"lake lost sensible heat participation");
    }
    require(serialize_world(p,world)==baseline,"opt-in epoch changed generated descendants");
    std::cout<<"{\"case\":\"production_committed\",\"epoch\":"<<finalized_enthalpy_epoch_json(epoch)<<"}\n";
    std::cout<<"{\"case\":\"production_summary\",\"checks\":"<<checks<<",\"world_generations\":1,\"duration_seconds\":2,\"thermal_calls\":"
        <<epoch.owner().work_meter().thermal_calls_started<<",\"mass_calls\":"<<epoch.owner().work_meter().mass_calls_started<<"}\n";
}
}
int main(int argc,char** argv) {
    try {
        if(argc==2 && std::string(argv[1])=="controls") controls();
        else if(argc==3 && std::string(argv[1])=="production") {
            if(!terrestrial_water_capability().available) {
                std::cout<<"{\"production_available\":false,\"world_generations\":0}\n";
                return 77;
            }
            production(argv[2]);
        }
        else throw std::runtime_error("expected controls or production WORLD_OUTPUT_PATH");
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
