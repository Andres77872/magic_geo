#include "layered_ice_material.hpp"
#include <cfenv>
#include <iomanip>
#include <iostream>
#include <string>

namespace {
using namespace magic_geo::detail;
namespace a=cryosphere_prototype;
int checks=0,misses=0,calls=0,mass_calls=0,builds=0;
void check(bool ok,const std::string& name){++checks;if(!ok)++misses;std::cout<<"{\"kind\":\"check\",\"name\":"<<std::quoted(name)<<",\"passed\":"<<(ok?"true":"false")<<"}\n";}
LayeredMaterialRequest base(){
    LayeredMaterialRequest q;q.initial.id="material_fixture";q.initial.complete_horizontal_coverage_declared=true;
    q.initial.bottom_boundary=LayeredIceBottomBoundary::insulated;q.initial.water={10,2,4,100};
    LayeredIceColumnInput c;c.cell_id=0;c.area_m2=2;c.top_closure=LayeredIceTopClosure::prescribed_nonwater_top_capacity;
    c.top_nonwater_heat_capacity_j_m2_k=4;c.layers={{0,4,200,2,1},{1,6,-12,2,1}};
    c.deep_inventory=LayeredIceDeepInventoryInput{10,-100,2};q.initial.columns={c};q.inherited_energy_error_j=.25;q.maximum_final_energy_error_j=10;return q;
}
LayeredMaterialMovement drain(){return {"drain",{0,0},{-1,-1},a::Phase::liquid,2,0};}
LayeredMaterialMovement refill(){return {"refill",{0,-1},{0,0},a::Phase::solid,2,0};}
struct Case{std::string name;LayeredMaterialRequest request;std::string failure;};
std::vector<Case> plan(){
    std::vector<Case> v;auto add=[&](std::string name,auto mutate,std::string failure=""){auto q=base();mutate(q);v.push_back({name,q,failure});};
    add("identity",[](auto&){});
    add("initial_liquid_drain",[](auto& q){q.movements={drain()};});
    add("cold_deep_refill",[](auto& q){q.movements={refill()};});
    add("internal_liquid_refreezes",[](auto& q){auto m=drain();m.recipient={0,1};q.movements={m};});
    add("simultaneous_drain_and_cold_refill",[](auto& q){q.movements={drain(),refill()};});
    add("request_order_reversed",[](auto& q){q.movements={refill(),drain()};});
    add("cold_solid_export",[](auto& q){auto m=refill();m.donor={0,1};m.recipient={-1,-1};q.movements={m};});
    add("warm_liquid_export",[](auto& q){q.initial.columns[0].layers[0].enthalpy_j_m2=500;q.movements={drain()};});
    add("rain_into_pure_ice",[](auto& q){q.movements={{"rain",{-1,-1},{0,1},a::Phase::liquid,1,10}};});
    add("cold_snow_into_pure_ice",[](auto& q){q.movements={{"snow",{-1,-1},{0,1},a::Phase::solid,1,5}};});
    add("nonbinary_mass_and_heat_projection",[](auto& q){q.initial.columns[0].area_m2=.3;auto d=drain();d.mass_kg=.1;auto f=refill();f.mass_kg=.3;q.movements={d,f};});
    add("uncertain_initial_liquid",[](auto& q){q.inherited_energy_error_j=2;auto m=drain();m.mass_kg=3.99;q.movements={m};},"uncertain_liquid_inventory");
    add("uncertain_initial_solid",[](auto& q){q.inherited_energy_error_j=2;auto m=refill();m.donor={0,0};m.recipient={0,1};m.mass_kg=3.99;q.movements={m};},"uncertain_solid_inventory");
    add("incoming_rain_cannot_fund_export",[](auto& q){auto d=drain();d.donor={0,1};q.movements={d,{"rain",{-1,-1},{0,1},a::Phase::liquid,4,10}};},"uncertain_liquid_inventory");
    add("self_transfer",[](auto& q){auto m=refill();m.donor=m.recipient;q.movements={m};},"invalid_address");
    add("cross_column_transfer",[](auto& q){auto c=q.initial.columns[0];c.cell_id=1;c.area_m2=3;q.initial.columns.push_back(c);auto m=refill();m.recipient={1,0};q.movements={m};},"invalid_address");
    add("duplicate_event_id",[](auto& q){auto m=refill();m.id="drain";q.movements={drain(),m};},"duplicate_movement");
    add("donor_temperature_override",[](auto& q){auto m=refill();m.import_temperature_k=1;q.movements={m};},"invalid_request");
    add("invalid_phase",[](auto& q){auto m=drain();m.phase=static_cast<a::Phase>(3);q.movements={m};},"invalid_request");
    add("negative_mass",[](auto& q){auto m=drain();m.mass_kg=-1;q.movements={m};},"invalid_request");
    add("uncertain_absolute_zero",[](auto& q){q.initial.columns[0].layers[1].enthalpy_j_m2=-119;q.inherited_energy_error_j=5;},"uncertain_physical_domain");
    add("empty_pure_water_output",[](auto& q){q.initial.columns[0].layers[1].enthalpy_j_m2=700;auto m=drain();m.donor={0,1};m.mass_kg=12;q.movements={m};},"mass_operation_refusal");
    add("joint_error_budget",[](auto& q){q.inherited_energy_error_j=1;q.maximum_final_energy_error_j=1;q.movements={refill()};},"cumulative_error_budget");
    add("empty_deep_not_existing_receiver",[](auto& q){q.initial.columns[0].deep_inventory=LayeredIceDeepInventoryInput{0,0,2};q.movements={{"snow",{-1,-1},{0,-1},a::Phase::solid,1,5}};},"invalid_address");
    add("finite_movement_cap",[](auto& q){q.movements=std::vector<LayeredMaterialMovement>(4097,drain());},"work_cap");
    return v;
}
} // namespace
int main(int argc,char** argv){
    const bool inventory=argc==2 && std::string(argv[1])=="--inventory";
    if(argc>1 && !inventory)return 2;
    const auto cases=plan();
    for(const auto& x:cases)std::cout<<"{\"kind\":\"inventory\",\"name\":"<<std::quoted(x.name)<<",\"request\":"<<layered_material_request_json(x.request)<<",\"expected_failure\":"<<std::quoted(x.failure)<<"}\n";
    if(inventory)return 0;
    std::string ordered_graph;
    for(const auto& x:cases){
        check(calls<25,"event_precall_cap");if(calls>=25)return 2;++calls;
        const auto before=layered_material_request_json(x.request);const auto r=apply_layered_material_events(x.request);builds+=r.graph_builds_started;mass_calls+=r.mass_calls_started;
        std::cout<<"{\"kind\":\"receipt\",\"name\":"<<std::quoted(x.name)<<",\"receipt\":"<<layered_material_receipt_json(r)<<"}\n";
        check(r.failure_code==x.failure && r.accepted==x.failure.empty(),x.name+".typed_outcome");
        check(before==layered_material_request_json(x.request),x.name+".input_unchanged");
        if(r.accepted){
            check(r.final_graph.has_value() && r.gross_initial_phase_inventory_proved && r.joint_nonexpansion_proved,x.name+".complete_graph_and_proof");
            check(r.joint_final_energy_error_upper_j<=x.request.maximum_final_energy_error_j,x.name+".joint_energy_budget");
            if(x.name=="identity")check(layered_ice_graph_json(*r.initial_graph)==layered_ice_graph_json(*r.final_graph) && r.joint_final_energy_error_upper_j==.25,"bit_preserving_identity");
            if(x.name=="initial_liquid_drain")check(r.nodes[0].final_W==3 && r.nodes[0].final_H==100 && r.parcels[0].carried_enthalpy_j==200,"liquid_leaves_with_latent_energy");
            if(x.name=="cold_deep_refill")check(r.nodes[0].final_W==5 && r.nodes[0].final_H==190 && r.nodes[2].final_W==9 && r.nodes[2].final_H==-90 && r.parcels[0].carried_enthalpy_j==-20,"finite_cold_donor_debit_and_receiver_credit");
            if(x.name=="internal_liquid_refreezes")check(r.nodes[1].final_W==7 && r.nodes[1].final_H==88,"cold_content_refreezes_part_of_incoming_liquid");
            if(x.name=="simultaneous_drain_and_cold_refill")ordered_graph=layered_ice_graph_json(*r.final_graph);
            if(x.name=="request_order_reversed")check(ordered_graph==layered_ice_graph_json(*r.final_graph),"order_independent_physical_result");
            if(x.name=="warm_liquid_export")check(r.nodes[0].final_W==3 && r.nodes[0].final_H==380 && r.parcels[0].carried_enthalpy_j==240,"warm_liquid_carries_sensible_and_latent_energy");
        }
    }
    // New direct compatibility controls; no historical qualification rerun.
    a::MassEventInput e;e.exports={{0,a::Phase::liquid,2}};
    const a::WaterProperties w{10,2,4,100};
    ++mass_calls;const auto old=a::apply_mass_events(w,{{2,4}},{{4,200}},e);
    ++mass_calls;const auto pure=a::apply_mass_events_pure_water(w,{{2,4}},{{4,200}},e);
    check(old.state==pure.state && old.movements[0].carried_enthalpy_j==pure.movements[0].carried_enthalpy_j && old.global_energy_residual_j==pure.global_energy_residual_j,"positive_capacity_legacy_entry_parity");
    bool refused=false;++mass_calls;try{a::apply_mass_events(w,{{2,0}},{{4,200}},e);}catch(const a::Error&){refused=true;}
    check(refused,"legacy_entry_keeps_positive_capacity_requirement");
    check(calls==25 && mass_calls<=28 && builds<=50,"fixed_call_envelope");
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<checks<<",\"misses\":"<<misses<<",\"material_calls\":"<<calls<<",\"mass_calls\":"<<mass_calls<<",\"graph_builds\":"<<builds<<",\"thermal_calls\":0,\"world_calls\":0}\n";
    return misses?1:0;
}
