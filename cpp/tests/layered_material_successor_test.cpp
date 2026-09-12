#include "layered_ice_material.hpp"
#include "layered_ice_remap.hpp"
#include "enthalpy_mesh_sdirk2.hpp"
#include "terrestrial_thermal/outward.hpp"
#include <iomanip>
#include <iostream>
#include <string>
namespace {
using namespace magic_geo::detail;
namespace a=cryosphere_prototype;
int checks=0,misses=0;
void check(bool ok,const std::string& name){++checks;if(!ok)++misses;std::cout<<"{\"kind\":\"check\",\"name\":"<<std::quoted(name)<<",\"passed\":"<<(ok?"true":"false")<<"}\n";}
LayeredMaterialRequest initial(){
    LayeredMaterialRequest q;q.initial.id="retained_900_second_layered_endpoint";
    q.initial.complete_horizontal_coverage_declared=true;q.initial.bottom_boundary=LayeredIceBottomBoundary::insulated;q.initial.water={273.15,2100,4186,334000};
    q.inherited_energy_error_j=0.05024488296311121;q.maximum_final_energy_error_j=3340;
    for(int i=0;i<2;++i){LayeredIceColumnInput c;c.cell_id=i;c.area_m2=i+1;c.top_closure=LayeredIceTopClosure::coarse_combined_surface_atmosphere;
        c.top_nonwater_heat_capacity_j_m2_k=1e7;c.top_longwave_emissivity=.6;c.top_absorbed_shortwave_w_m2=i==0?300:450;
        c.layers={{0,50,i==0?96777.68496917599:231777.684969176,300,.3},{1,200,-420379.0195143963,917,2.29},{2,1000,-4196853.889497215,917,2.29}};
        c.deep_inventory=LayeredIceDeepInventoryInput{1e5,-2.1e9,917};q.initial.columns.push_back(c);
        q.movements.push_back({"drain_"+std::to_string(i),{i,0},{-1,-1},a::Phase::liquid,i==0?.1:.2,0});
        q.movements.push_back({"refill_"+std::to_string(i),{i,-1},{i,0},a::Phase::solid,static_cast<double>(i+1),0});
    }
    q.initial.horizontal_climate_edges={{0,1,.1}};return q;
}
LayeredIceRemapRequest remap_template(){
    LayeredIceRemapRequest q;q.id="split_cold_middle_layers";q.source=initial().initial;
    q.maximum_final_energy_error_j=3340;
    for(int i=0;i<2;++i){
        q.targets.push_back({i,{{0,300,.3},{1,917,2.29},{2,917,2.29},{3,917,2.29}},917});
        q.donors.push_back({i,{false,0},{{{false,0},1}}});
        q.donors.push_back({i,{false,1},{{{false,1},1},{{false,2},1}}});
        q.donors.push_back({i,{false,2},{{{false,3},1}}});
        q.donors.push_back({i,{true,-1},{{{true,-1},1}}});
    }return q;
}
} // namespace
int main(int argc,char** argv){
    const bool inventory=argc==2 && std::string(argv[1])=="--inventory";if(argc>1 && !inventory)return 2;
    std::cout<<std::setprecision(17);const auto q=initial();const auto templ=remap_template();
    std::cout<<"{\"kind\":\"inventory\",\"material_request\":"<<layered_material_request_json(q)<<",\"remap_template\":"<<layered_ice_remap_request_json(templ)
        <<",\"thermal_options\":{\"duration_seconds\":900,\"maximum_stage_error_j\":0.001,\"maximum_endpoint_error_j\":3340,\"maximum_sweeps\":128,\"maximum_coordinate_iterations\":64,\"maximum_scalar_evaluations\":32768,\"reconstruction_leaves\":8,\"allow_pure_water_columns\":true},\"initial_clock_seconds\":900,\"final_clock_seconds\":1800}\n";
    if(inventory)return 0;
    int material_calls=0,remap_calls=0,thermal_calls=0,stages=0,builds=0,mass_calls=0;
    ++material_calls;const auto m=apply_layered_material_events(q);builds+=m.graph_builds_started;mass_calls+=m.mass_calls_started;
    std::cout<<"{\"kind\":\"material\",\"receipt\":"<<layered_material_receipt_json(m)<<"}\n";check(m.accepted,"material_accepted");
    if(m.accepted){
        auto rq=templ;rq.source=m.final_graph->input();rq.inherited_global_energy_error_j=m.joint_final_energy_error_upper_j;
        ++remap_calls;const auto r=remap_layered_ice(rq);builds+=r.work.source_builder_calls_started+r.work.output_builder_calls_started;
        std::cout<<"{\"kind\":\"remap\",\"receipt\":"<<layered_ice_remap_receipt_json(r)<<"}\n";check(r.accepted,"remap_accepted");
        if(r.accepted){
            const auto request=r.final->graph.make_mesh_request({900,.001,3340,128,64,32768,8,true});
            ++thermal_calls;const auto t=advance_enthalpy_mesh_sdirk2(request);stages+=t.stage_calls_started;
            std::cout<<"{\"kind\":\"thermal\",\"receipt\":"<<enthalpy_mesh_sdirk2_receipt_json(t)<<"}\n";check(t.accepted,"thermal_successor_accepted");
            if(t.accepted){
                const double E=phase_segment_prototype::bounds::add(phase_segment_prototype::bounds::point(r.final->final_global_energy_error_j),phase_segment_prototype::bounds::point(t.local_endpoint_error_upper_j)).upper;
                std::cout<<"{\"kind\":\"joint_endpoint\",\"initial_error_j\":"<<q.inherited_energy_error_j<<",\"after_material_error_j\":"<<m.joint_final_energy_error_upper_j<<",\"after_remap_error_j\":"<<r.final->final_global_energy_error_j<<",\"new_thermal_error_j\":"<<t.local_endpoint_error_upper_j<<",\"joint_retained_and_outbox_error_j\":"<<E<<"}\n";
                check(E<=3340,"joint_error_with_prior_endpoint_and_new_outbox");
                const auto& H=*t.final_enthalpy_j_m2;
                check(H.size()==8 && request.edges.size()==7,"actual_rebuilt_eight_node_graph");
                check(H[0]>0 && H[4]>0 && H[0]<request.water_mass_kg_m2[0]*334000 && H[4]<request.water_mass_kg_m2[4]*334000,"retained_surface_liquid_after_successor");
                check(H[1]<0 && H[2]<0 && H[3]<0 && H[5]<0 && H[6]<0 && H[7]<0,"cold_interior_after_split_and_successor");
                check(r.final->graph.input().columns[0].deep_inventory->water_mass_kg_m2==99999 && r.final->graph.input().columns[1].deep_inventory->water_mass_kg_m2==99999,"finite_deep_refill_debited");
                check(m.parcels.size()==4 && m.parcels[0].external_outbox && m.parcels[1].external_outbox && !m.parcels[2].external_outbox && !m.parcels[3].external_outbox,"two_liquid_parcels_exposed_once");
            }
        }
    }
    check(material_calls==1 && mass_calls==1 && remap_calls==1 && thermal_calls==1 && stages==2 && builds==4,"fixed_composed_call_counts");
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<checks<<",\"misses\":"<<misses<<",\"material_calls\":"<<material_calls<<",\"mass_calls\":"<<mass_calls<<",\"remap_calls\":"<<remap_calls<<",\"thermal_calls\":"<<thermal_calls<<",\"internal_be_calls\":"<<stages<<",\"graph_builds\":"<<builds<<",\"world_calls\":0,\"historical_thermal_reruns\":0}\n";
    return misses?1:0;
}
