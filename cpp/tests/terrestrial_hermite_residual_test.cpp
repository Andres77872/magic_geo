#include "terrestrial_coupled.hpp"
#include "terrestrial_thermal/outward.hpp"
#include "terrestrial_thermal/hermite_residual.hpp"
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>
using namespace magic_geo::detail;
namespace p = phase_segment_prototype;
namespace b = p::bounds;
namespace {
int checks=0, failures=0, calls=0, stages=0, fluxes=0, leaves=0;
int helper_calls=0;
void check(bool ok,const char* why) {
    ++checks;
    if (!ok) { ++failures; std::cerr<<why<<'\n'; }
}
p::Input realistic(const std::string& id,bool melt,bool residual) {
    p::Input x{};
    x.segment_id=id; x.physical_boundary_id="constant-six-hour";
    x.water={273.15,2100,4186,334000}; x.column={1,1e7,1e7,.5,10,.2};
    x.water_mass_kg_m2=melt?10:0; x.incident_shortwave_w_m2=melt?600:300;
    x.initial={melt?2.5e6:1e8,0}; x.maximum_duration_seconds=21600; x.physical_boundary_seconds=43200;
    x.incoming_branch=melt?p::Branch::mixed:p::Branch::dry; x.goal=p::Goal::fixed_duration;
    x.proposed_tube=melt?p::StateBox{{2e6,11e6},{-5e6,1e6}}:p::StateBox{{96e6,101e6},{-2e6,1e6}};
    x.budgets={1e-4,1e-8,1,3340}; x.limits={1,16,2,1024}; x.stage_options={1e-10,1e-12,30,12};
    if(residual){x.endpoint_certificate=p::EndpointCertificate::hermite_residual;x.reconstruction_leaves=64;}
    return x;
}
p::Input small(const std::string& id,int kind) {
    auto x=realistic(id,false,true); x.water={1,1,1,1.1}; x.column={1,1,0,0,0,0};
    x.water_mass_kg_m2=1.1; x.incident_shortwave_w_m2=4;
    x.initial={1.2100000000000002,0}; x.maximum_duration_seconds=.0625; x.physical_boundary_seconds=1;
    x.incoming_branch=p::Branch::mixed; x.proposed_tube={{1.20,1.48},{0,0}};
    x.budgets={1e-9,1e-8,.001,.01}; x.stage_options={1e-12,1e-12,20,8};
    if(kind==1){x.initial={-.01,0};x.maximum_duration_seconds=.015625;x.incoming_branch=p::Branch::solid;x.proposed_tube={{-.02,.08},{0,0}};}
    if(kind==2){x.water={1,1,1,1};x.water_mass_kg_m2=1;x.initial={1,0};x.incident_shortwave_w_m2=higher_order_thermal_prototype::sigma_w_m2_k4;x.proposed_tube={{.9,1.1},{0,0}};}
    return x;
}
std::vector<p::Input> inputs() {
    std::vector<p::Input> xs={realistic("dry-direct",false,false),realistic("dry-residual",false,true),
      realistic("melt-direct",true,false),realistic("melt-residual",true,true),
      small("raw-upper-residual",0),small("lower-crossing-residual",1),small("equilibrium-residual",2)};
    auto x=realistic("tiny-budget",false,true);x.budgets.maximum_physical_event_state_error_j_m2=1e-30;xs.push_back(x);
    x=realistic("unknown-policy",false,true);x.endpoint_certificate=static_cast<p::EndpointCertificate>(99);xs.push_back(x);
    x=realistic("nondyadic-leaves",false,true);x.reconstruction_leaves=3;xs.push_back(x);
    x=realistic("old-goal",false,true);x.goal=p::Goal::within_branch;xs.push_back(x);
    x=realistic("unused-leaves",false,false);x.reconstruction_leaves=16;xs.push_back(x);
    x=realistic("zero-leaves",false,true);x.reconstruction_leaves=0;xs.push_back(x);
    return xs;
}
p::Input undershoot() {
    auto x=small("helper-domain-undershoot",0);
    x.water_mass_kg_m2=0;x.incoming_branch=p::Branch::dry;x.initial={1,0};
    x.incident_shortwave_w_m2=0;x.maximum_duration_seconds=1e8;x.physical_boundary_seconds=1e8;
    return x;
}
CoupledIntervalPlan owner_plan() {
    const auto in=realistic("owner-first",false,true);
    CoupledSegmentPlan first{in.segment_id,in.incoming_branch,in.goal,21600,in.proposed_tube,
        in.budgets,in.limits,in.stage_options,false,in.endpoint_certificate,in.reconstruction_leaves};
    auto second=first;second.id="owner-second";second.latest_end_seconds=43200;second.tube={{94e6,101e6},{-4e6,1e6}};
    return {0,43200,{"constant-six-hour",0,43200,{300}},{},{},{{0,{first,second}}}};
}
TerrestrialCoupledOwner owner(std::size_t leafcap=128) {
    Cell c{};c.id=0;c.p={1,0,0};c.area_km2=1e-6;c.temperature_c=10;c.precipitation_mm_y=120;
    CoupledProperties props{{273.15,2100,4186,334000},1000,31557600,{{1e7,1e7,.5,10,.2}}};
    CoupledRestart r;r.state={{0,1e8,0}};r.canonical_energy_error_j_m2={7};
    CoupledLimits limits;limits.max_reconstruction_leaves=leafcap;
    return TerrestrialCoupledOwner(capture_terrestrial_surface({c},31),props,r,{3340},limits);
}
void meter(const p::Receipt& r) { ++calls;stages+=r.stage_calls_started;fluxes+=r.total_flux_evaluations;leaves+=r.reconstruction.leaves_started; }
void tamper(const p::Receipt& r,int kind) {
    auto x=r;
    if(kind==0)x.reconstruction.available=false;
    if(kind==1)--x.reconstruction.leaves_started;
    if(kind==2)x.reconstruction.leaves[0].surface_residual_integral_j_m2={-1,-1};
    if(kind==3)x.physical_event_state_error_j_m2={0,0};
    if(kind==4)x.final_state.surface_enthalpy_j_m2+=1;
    if(kind==5)x.selected_duration_seconds/=2;
    if(kind==6)x.request.endpoint_certificate=p::EndpointCertificate::direct_tube;
    const auto result=certify_coupled_segment(x,7,3340);
    check(!result.accepted,"corrupted helper copy accepted");
    std::cout<<"{\"kind\":\"helper_tamper\",\"case\":"<<kind<<",\"accepted\":"<<(result.accepted?"true":"false")<<",\"failure_code\":"<<std::quoted(result.failure_code)<<"}\n";
}
}
int main(int argc,char**argv) {
    const auto xs=inputs();
    if(argc==2&&std::string(argv[1])=="--inventory") {
        std::cout<<"{\"schema\":\"native_residual_inventory_v1\",\"phase_requests\":[";
        for(std::size_t i=0;i<xs.size();++i){if(i)std::cout<<',';std::cout<<p::phase_segment_input_json(xs[i]);}
        std::cout<<"],\"owner_plan\":"<<coupled_interval_plan_json(owner_plan())
          <<",\"helper_domain_request\":"<<p::phase_segment_input_json(undershoot())
          <<",\"helper_domain_endpoint\":{\"surface_enthalpy_j_m2\":1.0,\"atmospheric_energy_j_m2\":0.0},\"helper_reconstruction_calls\":1"
          <<",\"owner_prepares\":2,\"owner_commits\":2,\"helper_copies\":7,\"maximum_phase_calls\":15,\"maximum_stage_calls\":30,\"maximum_scalar_flux_calls\":15360,\"maximum_reconstruction_leaves\":704}\n";
        return 0;
    }
    try {
        std::vector<p::Receipt> receipts;
        for(std::size_t i=0;i<xs.size();++i) {
            const auto r=p::advance_phase_segment(xs[i]);meter(r);receipts.push_back(r);
            std::cout<<"{\"kind\":\"phase\",\"receipt\":"<<p::phase_segment_receipt_json(r)<<"}\n";
            const bool accepted=(i==1||i==3||i==4||i==5||i==6);
            check(r.accepted==accepted,"phase outcome differs from predeclared qualification target");
            if(i>=8)check(r.failure_code=="invalid_input"&&r.stage_calls_started==0&&!r.reconstruction.started,"invalid certificate spent physical work");
            if(i==0||i==2||i==7)check(r.failure_code=="physical_budget_refusal"&&r.numerical_candidate_available,"expected physical-budget refusal missing");
            if(accepted&&r.accepted) {
                check(r.reconstruction.available&&r.reconstruction.leaves.size()==64,"incomplete accepted reconstruction");
                check(r.physical_time_error_seconds.upper==0&&!r.guard.first_physical_hit_proved&&!r.guard.no_physical_hit_proved,"reconstruction invented event timing");
                check(certify_coupled_segment(r,i<4?7:0,3340).accepted,"native residual rejected by consumer");
                if(i==3||i==4||i==5) {
                    bool global=false;for(const auto& leaf:r.reconstruction.leaves)global=global||!leaf.polynomial;
                    check(global,"phase-crossing control missed the global fallback");
                }
            }
        }
        for(int i:{1,3}) {
            const auto &old=receipts[i-1],&fresh=receipts[i];
            check(old.numerical_candidate_available&&fresh.numerical_candidate_available,"policy comparison missing endpoint");
            if(old.numerical_candidate_available&&fresh.numerical_candidate_available) {
                check(old.trials[0].endpoint.surface_enthalpy_j_m2==fresh.trials[0].endpoint.surface_enthalpy_j_m2&&old.trials[0].endpoint.atmospheric_energy_j_m2==fresh.trials[0].endpoint.atmospheric_energy_j_m2,"certificate changed raw numerical state");
                check(fresh.reconstruction.available&&fresh.physical_event_state_error_j_m2.upper<old.physical_event_state_error_j_m2.upper,"certificate failed to improve six-hour enclosure");
            }
        }
        if(receipts[1].accepted)for(int j=0;j<7;++j)tamper(receipts[1],j);
        {
            const auto in=undershoot();p::ResidualCertificate proof;std::string error;
            try{++helper_calls;p::build_hermite_residual(in,{1,0},1e8,proof);}catch(const std::exception&e){error=e.what();}
            leaves+=proof.leaves_started;
            check(!error.empty()&&proof.started&&!proof.available&&proof.leaves_started==static_cast<int>(proof.leaves.size())+1,"nonphysical reconstruction or partial availability accepted");
            std::cout<<"{\"kind\":\"helper_domain_refusal\",\"request\":"<<p::phase_segment_input_json(in)
              <<",\"endpoint\":{\"surface_enthalpy_j_m2\":1.0,\"atmospheric_energy_j_m2\":0.0},\"reconstruction\":"<<p::residual_certificate_json(proof)<<",\"error\":"<<std::quoted(error)<<"}\n";
        }
        auto limited=owner(127); const auto refused=limited.prepare(owner_plan());
        std::cout<<"{\"kind\":\"owner_reservation\",\"receipt\":"<<coupled_attempt_receipt_json(*refused.diagnostic)<<"}\n";
        check(!refused.candidate&&refused.diagnostic->failure_code=="work_cap"&&limited.work_meter().segment_calls_started==0&&limited.work_meter().mass_calls_started==0,"full leaf reservation failed before physical work");
        auto actual=owner();const auto result=actual.prepare(owner_plan());
        for(const auto& seg:result.diagnostic->segments)if(seg.receipt_available)meter(seg.receipt);
        std::cout<<"{\"kind\":\"owner\",\"receipt\":"<<coupled_attempt_receipt_json(*result.diagnostic)<<"}\n";
        check(result.candidate.has_value(),"two-step source-free owner preparation failed");
        check(actual.restart().elapsed_seconds==0&&actual.restart().state[0].surface_enthalpy_j_m2==1e8,"prepare mutated restart");
        if(result.candidate) {
            const auto &one=result.diagnostic->segments[0],&two=result.diagnostic->segments[1];
            check(two.generated_input.initial.surface_enthalpy_j_m2==one.receipt.final_state.surface_enthalpy_j_m2&&two.generated_input.initial.atmospheric_energy_j_m2==one.receipt.final_state.atmospheric_energy_j_m2,"raw endpoint carry changed");
            check(two.error.inherited_error_j_m2==one.error.final_error_j_m2&&two.error.final_error_j_m2>=one.error.final_error_j_m2,"inherited physical error reset");
            actual.commit(*result.candidate);
            check(actual.restart().revision==1&&actual.restart().elapsed_seconds==43200,"atomic common endpoint commit failed");
            check(actual.work_meter().mass_calls_started==0&&actual.work_meter().reserved_reconstruction_leaves==128&&actual.work_meter().reconstruction_leaves_started==128,"owner work accounting mismatch");
            bool stale=false;try{actual.commit(*result.candidate);}catch(const TerrestrialWaterError&e){stale=e.code=="stale_candidate";}
            check(stale,"stale candidate replay accepted");
            std::cout<<"{\"kind\":\"committed\",\"stale_replay_refused\":"<<(stale?"true":"false")<<",\"restart\":"<<coupled_restart_json(actual.restart())<<",\"work\":"<<coupled_work_meter_json(actual.work_meter())<<"}\n";
        }
    } catch(const std::exception&e) {check(false,e.what());}
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<checks<<",\"failures\":"<<failures<<",\"phase_calls\":"<<calls<<",\"stages\":"<<stages<<",\"scalar_flux_evaluations\":"<<fluxes<<",\"reconstruction_leaves\":"<<leaves<<",\"helper_reconstruction_calls\":"<<helper_calls<<"}\n";
    return failures?1:0;
}
