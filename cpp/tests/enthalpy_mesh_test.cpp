#include "enthalpy_mesh.hpp"

#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

namespace {
using namespace magic_geo::detail;
struct Case { std::string name; EnthalpyMeshRequest request; std::string refusal; };
int checks=0, misses=0;
void check(bool ok,const std::string& name) {
    ++checks; if(!ok) ++misses;
    std::cout<<"{\"kind\":\"check\",\"name\":\""<<name<<"\",\"passed\":"<<(ok?"true":"false")<<"}\n";
}
EnthalpyMeshRequest unit(std::vector<double> W,std::vector<double> H) {
    EnthalpyMeshRequest q; q.water={1,1,1,1};
    q.water_mass_kg_m2=std::move(W);q.initial_enthalpy_j_m2=std::move(H);
    q.columns.assign(q.initial_enthalpy_j_m2.size(),{1,1,0});
    q.absorbed_shortwave_w_m2.assign(q.columns.size(),0);
    q.options={1,1e-11,1,128,64,32768,64};return q;
}
std::vector<Case> inventory() {
    std::vector<Case> all;
    auto q=unit({0},{-1});all.push_back({"stationary_absolute_zero",q,""});
    q=unit({1},{-1});q.options.duration_seconds=.25;q.absorbed_shortwave_w_m2={1};
    all.push_back({"solid_warming",q,""});
    q.initial_enthalpy_j_m2={.25};all.push_back({"latent_warming",q,""});
    q.initial_enthalpy_j_m2={-.25};q.options.duration_seconds=.75;q.absorbed_shortwave_w_m2={2};
    all.push_back({"complete_melt_crossing",q,""});
    q=unit({1,0},{.1,-.5});q.edges={{0,1,1}};
    all.push_back({"mesh_refreeze_crossing",q,""});
    q=unit({1,0},{.25,1});q.edges={{0,1,1}};q.options.duration_seconds=.25;
    all.push_back({"mesh_latent_exchange",q,""});
    q=unit({0,0},{1,0});q.columns[1].area_m2=2;q.edges={{0,1,1}};
    all.push_back({"unequal_area_rational_root",q,""});
    q.options.maximum_endpoint_error_j=.1;
    all.push_back({"accurate_stage_temporal_refusal",q,"endpoint_budget_refusal"});
    q.options.maximum_endpoint_error_j=1;q.options.maximum_sweeps=0;
    all.push_back({"zero_sweep_refusal",q,"stage_budget_refusal"});
    q.options.maximum_sweeps=128;q.options.maximum_scalar_evaluations=2;
    all.push_back({"partial_sweep_work_refusal",q,"work_cap"});
    q=unit({1,1,0},{-1e6,1e6,8e6});q.water={273.15,2100,4186,334000};
    q.water_mass_kg_m2={10,10,0};q.columns={{1,1e7,.75},{2,1.2e7,.8},{3,2e7,.7}};
    q.edges={{0,1,100},{1,2,50}};q.absorbed_shortwave_w_m2={300,600,100};
    q.options={60,.001,3340,128,64,32768,64};
    all.push_back({"physical_three_column_mesh",q,""});
    q.water_mass_kg_m2={0,0,0};
    q.initial_enthalpy_j_m2={1e7*(270-273.15),0,2e7*(285-273.15)};
    all.push_back({"dry_sensible_equivalence",q,""});
    auto bad=q;bad.absorbed_shortwave_w_m2[0]=-1;all.push_back({"negative_sunlight",bad,"invalid_input"});
    bad=q;bad.edges.push_back(bad.edges[0]);all.push_back({"duplicate_edge",bad,"invalid_input"});
    bad=q;bad.edges[0]={1,0,100};all.push_back({"reversed_edge",bad,"invalid_input"});
    bad=q;bad.water_mass_kg_m2.pop_back();all.push_back({"incomplete_water_coverage",bad,"invalid_input"});
    bad=q;bad.initial_enthalpy_j_m2[0]=-1e20;all.push_back({"below_physical_floor",bad,"physical_domain_refusal"});
    bad=q;bad.options.reconstruction_leaves=3;all.push_back({"nondyadic_leaf_cap",bad,"work_cap"});
    bad=q;bad.columns[0].area_m2=std::numeric_limits<double>::infinity();
    all.push_back({"nonfinite_area",bad,"invalid_input"});
    return all;
}
void near(double actual,double expected,double tolerance,const std::string& label) {
    check(std::isfinite(actual) && std::abs(actual-expected)<=tolerance,label);
}
void details(const Case& c,const EnthalpyMeshReceipt& r) {
    const auto& name=c.name;const auto& q=c.request;
    if(name=="partial_sweep_work_refusal") {
        check(r.scalar_evaluations==2 && r.coordinate_solves_started==2,name+".exact_work_prefix");
        check(r.candidate_available && r.candidate_enthalpy_j_m2!=q.initial_enthalpy_j_m2,name+".partial_candidate_retained");
        check(!r.stage_error_available && r.stage_residual_j_m2.empty(),name+".stale_proof_cleared");
    }
    if(name=="accurate_stage_temporal_refusal") {
        check(r.stage_accepted && r.endpoint_error_available,name+".separate_gates");
        check(r.local_endpoint_error_upper_j>.1,name+".nonzero_time_defect");
    }
    if(!r.accepted) return;
    const auto& H=*r.final_enthalpy_j_m2;
    if(name=="stationary_absolute_zero") check(H==q.initial_enthalpy_j_m2,name+".unchanged");
    if(name=="solid_warming") near(H[0],-.75,1e-11,name+".energy");
    if(name=="latent_warming") {
        near(H[0],.5,1e-11,name+".energy");
        check(r.candidate_field.temperature_k[0].lower<=1 && r.candidate_field.temperature_k[0].upper>=1,name+".melting_temperature");
    }
    if(name=="complete_melt_crossing") {
        near(H[0],1.25,1e-11,name+".energy");
        check(H[0]>1 && r.candidate_field.temperature_k[0].lower>1,name+".liquid_warming");
    }
    if(name=="mesh_refreeze_crossing") {
        near(H[0],-.12,1e-11,name+".solid_endpoint");near(H[1],-.28,1e-11,name+".neighbor_endpoint");
        check(H[0]<0 && r.candidate_field.temperature_k[0].upper<1,name+".frozen");
    }
    if(name=="mesh_latent_exchange") {
        near(H[0],.45,1e-11,name+".latent_gain");near(H[1],.8,1e-11,name+".sensible_loss");
        near(H[0]+H[1],1.25,1e-11,name+".closed_energy");
        check(H[0]>.25 && H[0]<1 && r.candidate_field.temperature_k[0].lower<=1 &&
              r.candidate_field.temperature_k[0].upper>=1,name+".melt_at_fixed_temperature");
    }
    if(name=="unequal_area_rational_root") {
        near(H[0],.6,1e-11,name+".first_root");near(H[1],.2,1e-11,name+".second_root");
        near(H[0]+2*H[1],1,1e-11,name+".area_weighted_conservation");
        check(r.local_endpoint_error_upper_j>.6 && r.local_endpoint_error_upper_j<.62,name+".linear_curve_defect");
        // Analytic continuous solution is distinct from the BE root. This is
        // an ordinary libm comparison, not authority for the rigorous bound.
        const double d=std::exp(-1.5);
        const double error=std::abs(H[0]-(1.0/3+2.0/3*d))+2*std::abs(H[1]-(1.0/3-1.0/3*d));
        check(error>.2 && error<=r.local_endpoint_error_upper_j,name+".true_flow_comparison");
    }
    if(name=="physical_three_column_mesh")
        check(H[0]<0 && H[1]>0 && H[1]<3340000,name+".solid_and_mixed_columns");
}
} // namespace
int main(int argc,char** argv) {
    const bool only_inventory=argc==2 && std::string(argv[1])=="--inventory";
    if(argc>1 && !only_inventory) return 2;
    std::cout<<std::setprecision(17);
    const auto cases=inventory();
    for(const auto& c:cases) {
        std::cout<<"{\"kind\":\"inventory\",\"name\":\""<<c.name<<"\",\"expected_refusal\":\""<<c.refusal
                 <<"\",\"request\":"<<enthalpy_mesh_request_json(c.request)<<"}\n";
    }
    if(only_inventory) return 0; // No numerical producer has run above.
    int mesh_calls=0,sensible_calls=0,accepted=0;
    for(const auto& c:cases) {
        const auto before=enthalpy_mesh_request_json(c.request);
        ++mesh_calls;const auto r=advance_enthalpy_mesh(c.request);
        accepted+=r.accepted?1:0;
        std::cout<<"{\"kind\":\"receipt\",\"name\":\""<<c.name<<"\",\"request\":"<<before
                 <<",\"receipt\":"<<enthalpy_mesh_receipt_json(r)<<"}\n";
        check(enthalpy_mesh_request_json(c.request)==before,c.name+".input_unchanged");
        check(c.refusal.empty()?r.accepted:(!r.accepted && r.failure_code==c.refusal),c.name+".expected_outcome");
        check(r.final_enthalpy_j_m2.has_value()==r.accepted,c.name+".final_publication");
        check(r.scalar_evaluations<=c.request.options.maximum_scalar_evaluations,c.name+".scalar_cap");
        if(r.accepted) {
            check(r.physical_domain_proved && r.candidate_available && r.stage_error_available && r.stage_accepted &&
                  r.endpoint_error_available,c.name+".all_proofs_available");
            check(r.stage_error_upper_j<=c.request.options.maximum_stage_error_j &&
                  r.local_endpoint_error_upper_j<=c.request.options.maximum_endpoint_error_j,c.name+".both_budgets");
            check(r.leaves.size()==static_cast<std::size_t>(c.request.options.reconstruction_leaves),c.name+".full_curve");
        }
        details(c,r);
        if(c.name=="dry_sensible_equivalence") {
            std::vector<double> initial;
            for(std::size_t i=0;i<c.request.columns.size();++i)
                initial.push_back(c.request.water.freezing_temperature_k+c.request.initial_enthalpy_j_m2[i]/c.request.columns[i].heat_capacity_j_m2_k);
            SurfaceEnergyStepOptions o;o.duration_seconds=c.request.options.duration_seconds;
            ++sensible_calls;const auto s=SurfaceEnergySystem(c.request.columns,c.request.edges).advance(initial,c.request.absorbed_shortwave_w_m2,o);
            std::cout<<"{\"kind\":\"sensible_comparison\",\"name\":\""<<c.name<<"\",\"initial_temperature_k\":[";
            for(std::size_t i=0;i<initial.size();++i){if(i)std::cout<<',';std::cout<<initial[i];}
            std::cout<<"],\"temperature_k\":[";
            for(std::size_t i=0;i<s.temperature_k.size();++i){if(i)std::cout<<',';std::cout<<s.temperature_k[i];}
            std::cout<<"],\"maximum_balance_residual_w_m2\":"<<s.maximum_balance_residual_w_m2<<"}\n";
            check(r.accepted,c.name+".mesh_available_for_comparison");
            if(r.accepted) for(std::size_t i=0;i<initial.size();++i)
                near(c.request.water.freezing_temperature_k+(*r.final_enthalpy_j_m2)[i]/c.request.columns[i].heat_capacity_j_m2_k,
                     s.temperature_k[i],1e-8,c.name+".temperature_"+std::to_string(i));
        }
    }
    // Serialization-only synthetic unavailable suffix: no physical claim.
    EnthalpyMeshReceipt incomplete;incomplete.leaves.emplace_back();
    const auto unavailable=enthalpy_mesh_receipt_json(incomplete);
    std::cout<<"{\"kind\":\"serialization_control\",\"receipt\":"<<unavailable<<"}\n";
    for(const char* key:{"physical_temperature_upper_k","physical_floor_j_m2","candidate_enthalpy_j_m2",
                        "candidate_field","stage_residual_j_m2","stage_error_upper_j","local_endpoint_error_upper_j",
                        "enthalpy_range_j_m2","field","residual_integral_j_m2","weighted_residual_upper_j"})
        check(unavailable.find(std::string("\"")+key+"\":null")!=std::string::npos,std::string("unavailable.")+key);
    check(mesh_calls==19 && sensible_calls==1,"declared_producer_counts");
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<checks<<",\"misses\":"<<misses
             <<",\"mesh_calls\":"<<mesh_calls<<",\"sensible_calls\":"<<sensible_calls<<",\"accepted\":"<<accepted<<"}\n";
    return misses==0?0:1;
}
