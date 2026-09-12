#include "internal.hpp"
#include <fstream>
#include <iostream>
using namespace magic_geo;
using namespace magic_geo::detail;
namespace {
int checks = 0;
void check(bool v, const char* why) { ++checks; if (!v) throw std::runtime_error(why); }
std::vector<Cell> fixture(int n) {
    std::vector<Cell> cells(static_cast<std::size_t>(n));
    for (int i=0; i<n; ++i) {
        auto& c=cells[i]; c.id=i; c.p={std::cos(i*.01), std::sin(i*.01), 0};
        c.area_km2=100; c.lat=70.0/DEG; c.temperature_c=-20; c.precipitation_mm_y=1000;
        c.elevation_m=2000-100*i; c.bedrock_surface_elevation_m=c.elevation_m-2;
        c.sediment_thickness_m=2; c.water_body=0;
    }
    return cells;
}
void edge(std::vector<Cell>& c,int a,int b) { c[a].neighbors.push_back(b); c[b].neighbors.push_back(a); }
void inactive(const Cell& c) {
    check(c.ice_thickness_m==0,"wet thickness must be zero");
    check(c.glacier_flow_to==-1,"wet flow must be absent");
    check(c.ice_surface_mass_balance_m_y==0,"wet SMB must be zero");
    check(c.basal_sliding_index==0 && c.ice_velocity_m_y==0 && c.glacial_erosion_m==0,"wet dynamics must be zero");
#ifndef LEGACY_BASELINE
    check(!c.grounded_ice_surface_applicable,"wet applicability false");
#endif
}
void reset_domain() {
    auto c=fixture(3); edge(c,0,1); edge(c,1,2);
    c[1].is_lake=true; c[1].water_body=4; c[1].water_depth_m=174.43631760163492;
    c[2].is_water=true; c[2].water_body=1;
    for (auto& x:c) {x.ice_thickness_m=123; x.glacier_flow_to=0; x.ice_surface_mass_balance_m_y=2; x.basal_sliding_index=1; x.ice_velocity_m_y=100; x.glacial_erosion_m=20;}
    derive_cryosphere_state(Params{},c); check(c[0].ice_thickness_m>25,"dry positive control");
    inactive(c[1]); inactive(c[2]);
    // A later lake classification must not inherit the previous grounded state.
    c[0].is_lake=true; derive_cryosphere_state(Params{},c); inactive(c[0]);
}
void dry_formula() {
    auto c=fixture(1); derive_cryosphere_state(Params{},c);
    const double lat=clamp((std::abs(c[0].lat)*DEG-50)/32,0.,1.25);
    const double elev=clamp((c[0].elevation_m-1250)/2500,0.,1.25);
    const double cold=clamp((-c[0].temperature_c-3)/22,0.,1.25);
    const double moisture=clamp((c[0].precipitation_mm_y-140)/1500,.05,1.15);
    const double ice=clamp((cold*moisture*(.42+std::max(lat,elev))-.16)*1350,0.,3200.);
    check(c[0].ice_thickness_m==ice,"dry thickness operation order unchanged");
    const double smb=clamp((1000./1000)*clamp(21./18,0.,1.4),0.,3.2);
    check(c[0].ice_surface_mass_balance_m_y==smb,"dry SMB unchanged");
    check(c[0].basal_sliding_index==clamp(.12+.30*clamp(ice/1800,0.,1.)+.18*clamp(-12./10,0.,1.),0.,1.),"dry sliding unchanged");
    check(c[0].ice_velocity_m_y==clamp(2.+52*c[0].basal_sliding_index,0.,120.),"dry velocity unchanged");
}
void lake_bridge() {
    auto c=fixture(3); edge(c,0,1); edge(c,1,2);
    for(auto& x:c)x.ice_thickness_m=300;
    c[0].area_km2=200; c[1].is_lake=true; c[1].water_body=4; c[1].landform=19;
    auto s=generate_ice_sheets(c);
    check(s.size()==2,"lake cannot bridge two active components");
    check(s[0].cell_count==1 && s[0].area_km2==200 && s[1].cell_count==1,"sheet counts/areas include only active dry members");
    check(c[0].ice_sheet_id==0 && c[2].ice_sheet_id==1,"area ordering preserved");
    check(c[1].ice_sheet_id==0,"lake can retain one direct context"); inactive(c[1]);
}
void contextual_margins() {
    auto c=fixture(7); for(int i=1;i<7;++i)edge(c,0,i); c[0].ice_thickness_m=300;
    c[1].is_lake=true;c[1].water_body=4;c[1].landform=19;
    c[2].is_water=true;c[2].water_body=2;c[2].landform=16;
    c[3].is_water=true;c[3].water_body=1;c[3].landform=0;c[3].water_depth_m=5000;
    c[4].is_lake=true;c[4].water_body=4;c[4].landform=3;
    c[5].is_lake=true;c[5].water_body=5;c[5].landform=19;
    c[6].landform=17;
    auto s=generate_ice_sheets(c);check(s.size()==1 && s[0].cell_count==1,"contexts not active members");
    for(int i:{1,2,5,6}) {
        check(c[i].ice_sheet_id==0,"explicit glacial context retained");
        check(c[i].deglaciation_age_ka==82,"cold memory coefficient preserved");
        check(c[i].moraine_deposition_m==.18+1.4*(2./2.5),"moraine coefficient preserved");
    }
    for(int i:{3,4})check(c[i].ice_sheet_id==-1 && c[i].moraine_deposition_m==0 && c[i].deglaciation_age_ka==0,"ordinary water unassociated");
}
void no_cascade() {
    auto c=fixture(4);edge(c,0,1);edge(c,1,2);edge(c,2,3);c[0].ice_thickness_m=300;
    for(int i=1;i<4;++i)c[i].landform=18;
    generate_ice_sheets(c);check(c[1].ice_sheet_id==0,"one-edge context");
    check(c[2].ice_sheet_id==-1 && c[3].ice_sheet_id==-1,"no context cascade along ID order");
    auto reversed=fixture(4);edge(reversed,3,2);edge(reversed,2,1);edge(reversed,1,0);reversed[3].ice_thickness_m=300;
    for(int i=0;i<3;++i)reversed[i].landform=18;
    generate_ice_sheets(reversed);
    for(int i=0;i<4;++i)check(c[i].ice_sheet_id==reversed[3-i].ice_sheet_id,"context eligibility index-order independent");
}
void strict_threshold() {
    auto c=fixture(3);edge(c,0,1);edge(c,1,2);c[0].ice_thickness_m=25.;c[1].ice_thickness_m=0.;
    check(!has_glacier_neighbor(c,1,25),"25m does not donate an active association");
    c[2].is_lake=true;c[2].ice_thickness_m=2000;
    check(!has_glacier_neighbor(c,1,25),"stale lake thickness is never an active donor");
    c[0].ice_thickness_m=std::nextafter(25.,26.);check(has_glacier_neighbor(c,1,25),"strict nextafter threshold");
    auto s=generate_ice_sheets(c);check(s.size()==1 && s[0].cell_count==1,"exact active threshold");
#ifndef LEGACY_BASELINE
    auto raw=cells_json(c,0);
    check(raw.find("\"ice_thickness_m\":25")!=std::string::npos,"display remains configured precision");
    check(raw.find("\"grounded_ice_diagnostic_thickness_m\":25.000000000000004")!=std::string::npos,"raw threshold evidence survives display rounding");
#endif
}
GlacialSedimentTransportStage wet_target(bool marine) {
    auto c=fixture(2);edge(c,0,1);c[1].is_water=marine;c[1].is_lake=!marine;c[1].water_body=marine?1:4;
    c[0].ice_thickness_m=300;c[0].glacier_flow_to=1;c[0].glacial_erosion_m=10;
    auto stage=transport_glacial_sediment(0,Params{}.erosion_iterations+1,c);
    check(stage.transfer_count==1 && stage.production_volume_km3==stage.deposition_volume_km3,"wet destination receives conservative bulk volume");
    check(c[1].glacial_sediment_deposition_m>0 && c[0].glacial_sediment_production_m>0,"source/destination material changes retained");
    check(stage.land_target_transfer_count==(!marine?1:0),"legacy land count means nonmarine including lake");
#ifndef LEGACY_BASELINE
    check(stage.input_cells[1].is_lake==!marine,"snapshot preserves pretransport lake flag");
#endif
    return stage;
}
void wet_destination() {wet_target(false);wet_target(true);}
void wet_source() {
    for(bool marine:{false,true}){
        auto c=fixture(2);edge(c,0,1);c[0].is_water=marine;c[0].is_lake=!marine;
        c[0].ice_thickness_m=300;c[0].glacier_flow_to=1;c[0].glacial_erosion_m=10;
        bool refused=false;try{transport_glacial_sediment(0,1,c);}catch(const std::runtime_error&){refused=true;}
        check(refused,"wet source transport refused");
        check(c[0].glacial_sediment_production_m==0 && c[1].glacial_sediment_deposition_m==0,"wet first-source refusal before material writes");
    }
}
#ifndef LEGACY_BASELINE
void serialization() {
    auto s=wet_target(false);
    auto m=grounded_ice_model_json();
    check(m.find("exposed_land_annual_grounded_ice_diagnostic_v1")!=std::string::npos,"grounded model identity");
    auto transport=glacial_sediment_transport_model_json({s},4);
    check(transport.find("downhill_area_conserving_glacial_sediment_transport_v3")!=std::string::npos,"transport v3");
    check(transport.find("complete_cell_cryosphere_terrain_and_sediment_inventory_before_transport_v3")!=std::string::npos,"snapshot v3");
    check(transport.find("\"source_grounded_ice_model\":\"exposed_land_annual_grounded_ice_diagnostic_v1\"")!=std::string::npos,"exact model source link");
    auto h=glacial_sediment_transport_history_json(Params{},{s},4);
    check(h.find("\"is_lake\":true")!=std::string::npos && h.find("\"is_lake\":false")!=std::string::npos,"complete boolean lake snapshot");
}
#endif
}
int main(int argc,char** argv) {
    int failed=0;
    const std::vector<std::pair<const char*,void(*)()>> cases={
        {"wet_reset",reset_domain},{"dry_formula",dry_formula},{"lake_bridge",lake_bridge},
        {"contextual_margins",contextual_margins},{"no_cascade",no_cascade},{"strict_threshold",strict_threshold},
        {"wet_destination",wet_destination},{"wet_source",wet_source},
#ifndef LEGACY_BASELINE
        {"serialization",serialization},
#endif
    };
    for(const auto& item:cases){try{item.second();std::cout<<"PASS "<<item.first<<'\n';}catch(const std::exception& e){++failed;std::cout<<"FAIL "<<item.first<<": "<<e.what()<<'\n';}}
#ifndef LEGACY_BASELINE
    if(argc==2){auto c=fixture(2);edge(c,0,1);c[1].is_lake=true;c[1].water_body=4;derive_cryosphere_state(Params{},c);
        auto stage=transport_glacial_sediment(0,Params{}.erosion_iterations+1,c);auto sheets=generate_ice_sheets(c);
        std::ofstream f(argv[1]);f<<"{\"fixture_scope\":\"synthetic_native_domain_unit_not_generated_world\",\"grounded_ice_model\":"<<grounded_ice_model_json()<<",\"cells\":"<<cells_json(c,4)<<",\"ice_sheets\":"<<ice_sheets_json(sheets,4)<<",\"glacial_sediment_transport_model\":"<<glacial_sediment_transport_model_json({stage},4)<<",\"glacial_sediment_transport_history\":"<<glacial_sediment_transport_history_json(Params{},{stage},4)<<"}\n";
        if(!f) return 2;
    }
#else
    (void)argc;(void)argv;
#endif
    std::cout<<"cases="<<cases.size()<<" checks="<<checks<<" failures="<<failed<<'\n';
    return failed?1:0;
}
