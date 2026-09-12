#include "finalized_layered_state.hpp"
#include "internal.hpp"
#include "world.hpp"
#include "../src/opencl_compute.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <optional>

using namespace magic_geo;
using namespace magic_geo::detail;
namespace {
int checks=0,failures=0,initializations=0;
void check(bool ok,const std::string& name) {
    ++checks;if(!ok)++failures;
    std::cout<<"{\"kind\":\"check\",\"name\":"<<std::quoted(name)<<",\"passed\":"<<(ok?"true":"false")<<"}\n";
}
FinalizedLayeredStateValue direct(double h) {
    return {FinalizedLayeredStateEncoding::direct_enthalpy,h,std::nullopt,std::nullopt};
}
FinalizedLayeredStateValue equilibrium(double t,double liquid) {
    return {FinalizedLayeredStateEncoding::equilibrium_temperature,std::nullopt,t,liquid};
}
FinalizedLayeredActiveInput active(int id,double w,FinalizedLayeredStateValue state) {
    return {id,w,917,2,std::move(state)};
}
FinalizedLayeredProfile& profile(FinalizedLayeredStateRequest& q,int id) {
    const auto p=std::find_if(q.profiles.begin(),q.profiles.end(),[&](const auto& x){return x.geographic_cell_id==id;});
    if(p==q.profiles.end())throw std::runtime_error("fixture profile not found");
    return *p;
}
FinalizedLayeredStateRequest base_request() {
    FinalizedLayeredStateRequest q;q.policy=FinalizedLayeredStatePolicy::supplied_canonical_layers_v1;
    q.owner_id="new_supplied_state_owner";q.input_id="new_supplied_state_input";
    q.complete_horizontal_coverage_declared=true;q.bottom_boundary=LayeredIceBottomBoundary::insulated;
    q.inherited_energy_error_j=.25;q.maximum_joint_energy_error_j=1e12;
    for(int i=0;i<12;++i)q.profiles.push_back({(5*i+1)%12,{active(0,0,equilibrium(8,0))},std::nullopt});
    profile(q,0).layers={active(0,0,equilibrium(12,0))};
    profile(q,1).layers={active(0,0,equilibrium(12,0))};
    profile(q,2).layers={active(0,2,equilibrium(8,0)),active(1,3,equilibrium(12,3))};
    profile(q,2).deep_inventory=FinalizedLayeredDeepInput{4,917,equilibrium(10,1)};
    profile(q,3).layers={active(0,2,equilibrium(10,.5))};
    profile(q,3).deep_inventory=FinalizedLayeredDeepInput{2,917,equilibrium(8,0)};
    profile(q,4).layers={active(0,1.5,direct(-7.5))};
    profile(q,5).layers={active(0,1,direct(4))};
    profile(q,6).layers={active(0,0,direct(-0.0))};
    return q;
}
struct Case {
    std::string name;
    FinalizedLayeredStateRequest request;
    bool accepted;
    std::string source_change;
};
std::vector<Case> cases() {
    std::vector<Case> out;
    const auto add=[&](const std::string& name,bool accepted,const std::function<void(FinalizedLayeredStateRequest&)>& mutate,
                       const std::string& change="") {
        auto q=base_request();mutate(q);out.push_back({name,std::move(q),accepted,change});
    };
    const auto unchanged=[](auto&){};
    add("mixed_permuted",true,unchanged);
    add("mixed_identity",true,[](auto& q){std::sort(q.profiles.begin(),q.profiles.end(),[](const auto& a,const auto& b){return a.geographic_cell_id<b.geographic_cell_id;});});
    const auto all_direct=[](auto& q){for(auto& p:q.profiles){for(auto& l:p.layers)l.state=direct(-0.0);if(p.deep_inventory)p.deep_inventory->state=direct(0);}};
    add("all_direct_nonzero_E",true,all_direct);
    add("all_direct_zero_E",true,[&](auto& q){all_direct(q);q.inherited_energy_error_j=0;});
    // The initializer retains the underflow defect; the graph's separate
    // reciprocal-capacity evaluation cannot represent this tiny deep state.
    add("deep_sensible_underflow_refused_by_graph",false,[&](auto& q){
        all_direct(q);q.inherited_energy_error_j=0;
        const double tiny=std::numeric_limits<double>::denorm_min();
        profile(q,2).deep_inventory=FinalizedLayeredDeepInput{tiny,1,equilibrium(std::nextafter(10.0,11.0),tiny)};
    });
    add("explicit_empty_deep",true,[](auto& q){profile(q,2).deep_inventory=FinalizedLayeredDeepInput{0,917,direct(0)};});
    add("dry_sole_sensible",true,[](auto& q){auto& p=profile(q,2);p.layers={active(0,0,equilibrium(8,0))};p.deep_inventory.reset();});
    add("freezing_all_solid",true,[](auto& q){profile(q,3).layers[0].state=equilibrium(10,0);});
    add("freezing_all_liquid",true,[](auto& q){profile(q,3).layers[0].state=equilibrium(10,2);});
    add("warm_all_liquid",true,[](auto& q){profile(q,3).layers[0].state=equilibrium(12,2);});
    add("nonbinary_conversion",true,[](auto& q){profile(q,2).layers[1]=active(1,.7,equilibrium(12.3,.7));});
    add("diagnostic_ice_and_basin_annotations",true,unchanged,"diagnostics");
    add("missing_profile",false,[](auto& q){q.profiles.pop_back();});
    add("duplicate_geographic_id",false,[](auto& q){q.profiles[1].geographic_cell_id=q.profiles[0].geographic_cell_id;});
    add("out_of_range_geographic_id",false,[](auto& q){q.profiles[0].geographic_cell_id=12;});
    add("missing_layer",false,[](auto& q){profile(q,2).layers.clear();});
    add("noncanonical_layer_id",false,[](auto& q){profile(q,2).layers[1].layer_id=0;});
    add("unspecified_policy",false,[](auto& q){q.policy=FinalizedLayeredStatePolicy::unspecified;});
    add("coverage_not_declared",false,[](auto& q){q.complete_horizontal_coverage_declared=false;});
    add("unspecified_bottom",false,[](auto& q){q.bottom_boundary=LayeredIceBottomBoundary::unspecified;});
    add("missing_state_tag",false,[](auto& q){profile(q,4).layers[0].state.encoding=FinalizedLayeredStateEncoding::unspecified;});
    add("direct_with_temperature",false,[](auto& q){profile(q,4).layers[0].state.temperature_k=8;});
    add("temperature_with_enthalpy",false,[](auto& q){profile(q,2).layers[0].state.enthalpy_j_m2=0;});
    add("missing_liquid_at_freezing",false,[](auto& q){profile(q,3).layers[0].state.liquid_water_mass_kg_m2.reset();});
    add("missing_direct_H",false,[](auto& q){profile(q,4).layers[0].state.enthalpy_j_m2.reset();});
    add("missing_W",false,[](auto& q){auto& l=profile(q,4).layers[0];l.water_mass_kg_m2=FinalizedLayeredActiveInput{}.water_mass_kg_m2;});
    add("negative_W",false,[](auto& q){profile(q,4).layers[0].water_mass_kg_m2=-1;});
    add("nonfinite_H",false,[](auto& q){profile(q,4).layers[0].state.enthalpy_j_m2=std::numeric_limits<double>::infinity();});
    add("negative_temperature",false,[](auto& q){profile(q,2).layers[0].state.temperature_k=-1;});
    add("nonfinite_temperature",false,[](auto& q){profile(q,2).layers[0].state.temperature_k=std::numeric_limits<double>::quiet_NaN();});
    add("cold_with_liquid",false,[](auto& q){profile(q,2).layers[0].state.liquid_water_mass_kg_m2=.1;});
    add("warm_with_solid",false,[](auto& q){profile(q,2).layers[1].state.liquid_water_mass_kg_m2=2;});
    add("negative_liquid",false,[](auto& q){profile(q,3).layers[0].state.liquid_water_mass_kg_m2=-1;});
    add("too_much_liquid",false,[](auto& q){profile(q,3).layers[0].state.liquid_water_mass_kg_m2=3;});
    add("near_freezing_is_not_plateau",false,[](auto& q){profile(q,3).layers[0].state.temperature_k=std::nextafter(10.0,11.0);});
    add("zero_density",false,[](auto& q){profile(q,4).layers[0].density_kg_m3=0;});
    add("zero_conductivity",false,[](auto& q){profile(q,4).layers[0].conductivity_w_m_k=0;});
    add("lake_retained_water",false,[](auto& q){profile(q,0).layers[0]=active(0,1,equilibrium(12,1));});
    add("marine_retained_water",false,[](auto& q){profile(q,1).layers[0]=active(0,1,equilibrium(12,1));});
    add("wet_extra_layer",false,[](auto& q){profile(q,0).layers.push_back(active(1,1,direct(0)));});
    add("wet_deep_water",false,[](auto& q){profile(q,0).deep_inventory=FinalizedLayeredDeepInput{1,917,direct(0)};});
    add("empty_deep_has_no_temperature",false,[](auto& q){profile(q,2).deep_inventory=FinalizedLayeredDeepInput{0,917,equilibrium(10,0)};});
    add("empty_deep_nonzero_H",false,[](auto& q){profile(q,2).deep_inventory=FinalizedLayeredDeepInput{0,917,direct(1)};});
    add("dry_top_over_deep",false,[](auto& q){profile(q,3).layers={active(0,0,direct(0))};});
    add("empty_pure_active",false,[](auto& q){profile(q,2).layers[1]=active(1,0,direct(0));});
    add("negative_inherited_E",false,[](auto& q){q.inherited_energy_error_j=-1;});
    add("inherited_E_exceeds_budget",false,[](auto& q){q.maximum_joint_energy_error_j=.1;});
    add("conversion_exceeds_budget",false,[](auto& q){q.inherited_energy_error_j=0;q.maximum_joint_energy_error_j=0;});
    add("whole_E_crosses_deep_floor",false,[](auto& q){
        q.inherited_energy_error_j=1e15;q.maximum_joint_energy_error_j=1e16;
        profile(q,3).deep_inventory->state=direct(-4);
    });
    add("absolute_zero_conversion",false,[](auto& q){profile(q,2).layers[1]=active(1,3,equilibrium(0,0));});
    add("direct_below_floor",false,[](auto& q){profile(q,2).layers[1]=active(1,3,direct(-31));});
    add("conversion_overflow",false,[](auto& q){profile(q,2).layers[0].state.temperature_k=std::numeric_limits<double>::max();profile(q,2).layers[0].state.liquid_water_mass_kg_m2=2;});
    add("profile_cap",false,[](auto& q){q.limits.max_profiles=11;});
    add("active_layer_cap",false,[](auto& q){q.limits.max_active_layers=12;});
    add("identifier_cap",false,[](auto& q){q.owner_id=std::string(97,'a');});
    add("tiny_receipt_cap",false,[](auto& q){q.limits.max_receipt_bytes=1;});
    add("owner_seed_history_cap",false,[](auto& q){q.owner_limits.max_receipt_bytes=1;q.owner_limits.max_private_receipt_bytes=1;q.owner_limits.max_history_bytes=1;});
    add("changed_planet",false,unchanged,"planet");
    add("changed_observed_revision",false,unchanged,"revision");
    add("changed_routing_only",false,unchanged,"routing");
    add("changed_geographic_elevation",false,unchanged,"elevation");
    add("changed_original_climate",false,unchanged,"climate");
    add("changed_lake_spill",false,unchanged,"lake_spill");
    return out;
}
Params control_params() {
    Params p;p.name="new_supplied_layer_controls";p.seed=424283;p.mesh_backend=1;p.cell_count=12;p.plate_count=4;
    p.erosion_iterations=0;p.threads=1;p.float_precision=17;return p;
}
Params foundation_params() {
    Params p;p.name="new_supplied_layer_foundation";p.seed=424289;p.cell_count=128;p.plate_count=8;
    p.erosion_iterations=0;p.threads=1;p.float_precision=8;return p;
}
std::vector<Cell> control_cells(const Params& p) {
    auto cells=build_mesh(p);
    for(auto& c:cells){c.elevation_m=100;c.filled_elevation_m=100;c.hydrologic_surface_elevation_m=100;
        c.hydrologic_surface_conditioned=true;c.flow_to=-1;c.temperature_c=-42;c.precipitation_mm_y=123;}
    auto& lake=cells[0];lake.elevation_m=4;lake.filled_elevation_m=8;lake.hydrologic_surface_elevation_m=8;
    lake.is_lake=true;lake.water_body=4;lake.depression_component_id=10;lake.depression_sink_cell_id=0;
    lake.spill_elevation_m=8;lake.lake_fill_fraction=.5;lake.water_depth_m=2;
    auto& marine=cells[1];marine.elevation_m=-17;marine.filled_elevation_m=0;marine.hydrologic_surface_elevation_m=0;
    marine.is_water=true;marine.water_body=1;marine.water_depth_m=17;
    return cells;
}
void inventory() {
    const auto all=cases();std::cout<<"{\"kind\":\"inventory\",\"execution\":\"none\",\"controls\":[";
    bool first=true;for(const auto& c:all){if(!first)std::cout<<',';first=false;
        std::cout<<"{\"name\":"<<std::quoted(c.name)<<",\"accepted\":"<<(c.accepted?"true":"false")
            <<",\"source_change\":"<<std::quoted(c.source_change)<<",\"request\":"<<finalized_layered_state_request_json(c.request)<<'}';}
    std::cout<<"],\"control_mesh\":{\"backend\":1,\"cells\":12,\"seed\":424283},"
        "\"control_water\":{\"Tf\":10,\"ci\":1,\"cl\":2,\"Lf\":4},\"control_lake_slab_cap_m\":1,\"control_revision\":431,"
        "\"foundation\":{\"seed\":424289,\"cells\":128,\"plates\":8,\"erosion_iterations\":0,\"threads\":1,\"float_precision\":8,\"revision\":439,\"lake_slab_cap_m\":7,"
        "\"supplied_land_W\":[2,3],\"supplied_land_T\":[250,255],\"land_liquid_W\":[0,0],\"wet_W\":0,\"wet_T\":280,\"wet_liquid_W\":0,\"rho\":917,\"k\":2,\"inherited_E\":1,\"joint_budget\":1000000000000},"
        "\"thermal_calls\":0,\"material_calls\":0,\"calendar_calls\":0,\"completed_world_calls\":0}\n";
}
void controls() {
    const auto params=control_params();const auto cells=control_cells(params);
    FinalizedEnthalpyOptions options;options.water={10,1,2,4};options.lake_mixed_layer_depth_m=1;
    const auto context=build_finalized_enthalpy_context(cells,params,options,431);
    const auto routing=capture_seasonal_liquid_routing_graph(cells,431);
    const auto source=finalized_layered_state_observed_json(cells,params,431);
    std::cout<<"{\"kind\":\"source\",\"context\":"<<finalized_enthalpy_context_json(context)<<",\"routing\":"
        <<seasonal_liquid_routing_graph_json(routing)<<",\"observed\":"<<source<<"}\n";
    const auto all=cases();int accepted=0;std::uint64_t ctor_started=0,ctor_completed=0;
    for(const auto& c:all) {
        auto observed=cells;auto p=params;std::uint64_t revision=431;
        if(c.source_change=="planet")p.gravity_g=2;
        if(c.source_change=="revision")++revision;
        if(c.source_change=="routing")observed[4].hydrologic_surface_elevation_m+=1;
        if(c.source_change=="elevation")observed[4].elevation_m+=1;
        if(c.source_change=="climate")observed[4].temperature_c-=1;
        if(c.source_change=="lake_spill")observed[0].spill_elevation_m+=1;
        if(c.source_change=="diagnostics"){observed[4].ice_thickness_m=987;observed[4].basin_id=77;}
        const auto before=finalized_layered_state_observed_json(observed,p,revision);
        ++initializations;auto result=initialize_finalized_layered_state(context,routing,observed,p,revision,c.request);
        const auto& r=result.receipt;accepted+=r.accepted;ctor_started+=r.work.owner_constructions_started;
        ctor_completed+=r.work.owner_constructions_completed;
        std::cout<<"{\"kind\":\"initialization\",\"name\":"<<std::quoted(c.name)<<",\"invocation\":"
            <<finalized_layered_state_request_json(c.request)<<",\"observed_before\":"<<before
            <<",\"observed_after\":"<<finalized_layered_state_observed_json(observed,p,revision)
            <<",\"receipt\":"<<finalized_layered_state_receipt_json(r)<<"}\n";
        check(r.accepted==c.accepted && static_cast<bool>(result.owner)==c.accepted && static_cast<bool>(r.final)==c.accepted,
              c.name+"_expected_atomic_result");
        check(before==finalized_layered_state_observed_json(observed,p,revision),c.name+"_observed_source_unchanged");
        if(r.accepted) {
            check(r.failure_code.empty() && r.work.owner_constructions_started==1 && r.work.owner_constructions_completed==1 &&
                  r.work.observed_owner_work && r.work.observed_owner_work->graph_builds_started==1 &&
                  r.work.observed_owner_work->prepare_attempts==0,c.name+"_one_constructor_no_evolution");
            check(layered_ice_owner_snapshot_json(*result.owner->snapshot())==layered_ice_owner_snapshot_json(*r.final) &&
                  r.final->revision==0 && r.final->forcing_history.empty() && r.final->consumed_event_ids.empty() &&
                  r.final->pending_outboxes.empty(),c.name+"_fresh_owned_state_matches_receipt");
        } else check(!r.failure_code.empty(),c.name+"_typed_refusal");
        if(c.name=="tiny_receipt_cap")check(r.minimal_refusal_metadata && r.failure_code=="receipt_cap" &&
            r.work.owner_constructions_started==1 && r.work.owner_constructions_completed==1 && r.work.observed_owner_work &&
            r.work.observed_owner_work->graph_builds_started==1,"receipt_cap_discards_constructed_owner_preserving_work");
        if(c.name=="owner_seed_history_cap")check(r.failure_code=="history_cap" &&
            r.work.owner_constructions_started==1 && r.work.owner_constructions_completed==0 && !r.work.observed_owner_work,
            "failed_constructor_does_not_invent_observed_work");
        if(c.name=="whole_E_crosses_deep_floor")check(r.failure_code=="uncertain_physical_domain" &&
            r.work.owner_constructions_started==1 && r.work.owner_constructions_completed==0,
            "full_initial_E_reaches_actual_owner_domain_gate");
    }
    check(source==finalized_layered_state_observed_json(cells,params,431),"shared_control_source_unchanged");
    std::cout<<"{\"kind\":\"summary\",\"scope\":\"controls\",\"checks\":"<<checks<<",\"failures\":"<<failures
        <<",\"initializations\":"<<initializations<<",\"accepted\":"<<accepted<<",\"owner_constructions_started\":"<<ctor_started
        <<",\"owner_constructions_completed\":"<<ctor_completed<<",\"mesh_builds\":1,\"context_builds\":1,\"routing_captures\":1,"
        "\"foundation_calls\":0,\"thermal_calls\":0,\"material_calls\":0,\"calendar_calls\":0,\"completed_world_calls\":0}\n";
}
void foundation() {
    auto p=foundation_params();ComputeOptions cpu;cpu.compute_backend=1;
    validate_params(p);validate_compute_options(cpu);ScopedThreadConfiguration threads(1);ComputeSession compute(p,cpu);
    std::optional<GeographicFoundation> source;source.emplace(prepare_geographic_foundation(p));
    const auto& cells=source->earth().cells;
    FinalizedLayeredStateRequest q;q.policy=FinalizedLayeredStatePolicy::supplied_canonical_layers_v1;
    q.owner_id="new_foundation_supplied_owner";q.input_id="new_foundation_supplied_input";
    q.complete_horizontal_coverage_declared=true;q.bottom_boundary=LayeredIceBottomBoundary::insulated;
    q.inherited_energy_error_j=1;q.maximum_joint_energy_error_j=1e12;
    for(std::size_t local=0;local<cells.size();++local) {
        const auto geo=cells.size()-1-local;const auto& c=cells[geo];
        auto layers=(c.is_water||c.is_lake)?std::vector{active(0,0,equilibrium(280,0))}:
            std::vector{active(0,2,equilibrium(250,0)),active(1,3,equilibrium(255,0))};
        q.profiles.push_back({static_cast<int>(geo),std::move(layers),std::nullopt});
    }
    const auto before=finalized_layered_state_observed_json(cells,p,439);
    FinalizedEnthalpyOptions options;options.lake_mixed_layer_depth_m=7;
    std::cout<<"{\"kind\":\"foundation_before\",\"request\":"<<finalized_layered_state_request_json(q)
        <<",\"observed\":"<<before<<"}\n";
    ++initializations;auto result=source->initialize_layered_state(options,q,439);
    std::cout<<"{\"kind\":\"foundation_initialization\",\"receipt\":"<<finalized_layered_state_receipt_json(result.receipt)<<"}\n";
    check(result.receipt.accepted && result.owner && result.receipt.final,"foundation_supplied_owner_accepted");
    check(before==finalized_layered_state_observed_json(source->earth().cells,p,439),"foundation_source_unchanged");
    check(!source->earth().terrestrial_surface_finalized && !source->earth().terrestrial_surface_epoch &&
          !source->earth().finalized_enthalpy_planet && source->earth().terrestrial_owner_mode==TerrestrialOwnerMode::none,
          "initializer_does_not_publish_descendants_or_epoch");
    if(!result.owner)return;
    const auto retained=finalized_layered_state_receipt_json(result.receipt);source.reset();
    check(finalized_layered_state_receipt_json(result.receipt)==retained,"receipt_survives_foundation_destruction");
    check(layered_ice_owner_snapshot_json(*result.owner->snapshot())==layered_ice_owner_snapshot_json(*result.receipt.final),
          "owner_survives_foundation_destruction");
    check(result.owner->work().graph_builds_started==1 && result.owner->work().prepare_attempts==0,
          "foundation_owner_only_constructed_once");
    std::cout<<"{\"kind\":\"summary\",\"scope\":\"foundation\",\"checks\":"<<checks<<",\"failures\":"<<failures
        <<",\"initializations\":1,\"foundation_calls\":1,\"context_builds\":1,\"routing_captures\":1,\"cells\":"
        <<result.receipt.context->surface().cells().size()<<",\"lakes\":"<<result.receipt.context->lakes().size()
        <<",\"thermal_calls\":0,\"material_calls\":0,\"calendar_calls\":0,\"completed_world_calls\":0}\n";
}
}
int main(int argc,char** argv) {
    std::cout.imbue(std::locale::classic());std::cout<<std::setprecision(17);
    try {
        if(argc==2 && std::string(argv[1])=="--inventory"){inventory();return 0;}
        if(argc==2 && std::string(argv[1])=="--controls")controls();
        else if(argc==2 && std::string(argv[1])=="--foundation")foundation();
        else return 2;
        return failures?1:0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
