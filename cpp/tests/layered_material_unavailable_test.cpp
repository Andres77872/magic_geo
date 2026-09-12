#include "layered_ice_material.hpp"
#include <iostream>
#include <string>
#ifndef MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER
#error This control must be linked without the calorimeter backend.
#endif
int main(int argc,char** argv){
    using namespace magic_geo::detail;
    LayeredMaterialRequest q;q.initial.id="disabled_backend_control";q.initial.water={10,2,4,100};
    q.initial.complete_horizontal_coverage_declared=true;q.initial.bottom_boundary=LayeredIceBottomBoundary::insulated;
    q.initial.columns={{0,1,LayeredIceTopClosure::prescribed_top_energy,0,0,0,{{0,2,-4,2,1}},std::nullopt}};
    q.maximum_final_energy_error_j=1;
    std::cout<<"{\"kind\":\"inventory\",\"request\":"<<layered_material_request_json(q)<<"}\n";
    if(argc==2 && std::string(argv[1])=="--inventory")return 0;
    if(argc>1)return 2;
    const auto r=apply_layered_material_events(q);
    std::cout<<"{\"kind\":\"receipt\",\"receipt\":"<<layered_material_receipt_json(r)<<"}\n";
    const bool passed=!r.accepted && r.failure_code=="capability_unavailable" && r.graph_builds_started==1 && r.mass_calls_started==0;
    std::cout<<"{\"kind\":\"summary\",\"checks\":1,\"misses\":"<<(passed?0:1)<<",\"material_calls\":1,\"graph_builds\":1,\"mass_calls\":0,\"thermal_calls\":0,\"world_calls\":0}\n";
    return passed?0:1;
}
