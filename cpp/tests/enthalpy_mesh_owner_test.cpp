#include "enthalpy_mesh_owner.hpp"

#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using namespace magic_geo::detail;
namespace a=cryosphere_prototype;
struct Fixture {
    std::string id,expected_failure,initial_binding;
    std::vector<Cell> cells;
    EnthalpyMeshProperties properties;
    EnthalpyMeshRestart initial;
    EnthalpyMeshOwnerLimits limits;
    double budget=.25;
    EnthalpyMeshIntervalRequest request;
};
struct Counts {
    int checks=0,misses=0,prepares=0,commits=0,candidates=0;
    std::uint64_t mass_started=0,mass_returned=0,thermal_started=0,thermal_returned=0;
    std::uint64_t scalar=0,fields=0,sweeps=0,coordinates=0,leaves=0;
} count;
void check(bool ok,const std::string& name) {
    ++count.checks;if(!ok)++count.misses;
    std::cout<<"{\"kind\":\"check\",\"name\":\""<<name<<"\",\"passed\":"<<(ok?"true":"false")<<"}\n";
}
void near(double x,double expected,double tolerance,const std::string& name) {
    check(std::isfinite(x) && std::abs(x-expected)<=tolerance,name);
}
Fixture base(const std::string& id) {
    Fixture f;f.id=id;f.cells.resize(2);
    for(int i=0;i<2;++i) {
        auto& c=f.cells[i];c.id=i;c.p={1,0,0};c.area_km2=(i+1)*1e-6;
        c.temperature_c=10;c.precipitation_mm_y=120;c.neighbors={1-i};
    }
    f.properties={{1,1,1,1},1000,31557600,{{1,3,0},{2,1,0}},{{0,1,1}}};
    f.initial.state={{1,3},{0,0}};f.initial.canonical_energy_error_j=1.0/16;
    f.request.end_seconds=.25;f.request.forcing={"cool-0",0,.25,{0,0}};
    f.request.initial_liquid_withdrawals={{"drain-0",0,.5}};
    f.request.options={.25,0,8,8,1e-11,128,64,32768,32};
    return f;
}
std::vector<Fixture> fixtures() {
    std::vector<Fixture> fs;
    auto f=base("combined_capacity_donor");fs.push_back(f);
    f=base("zero_energy_sources");f.properties.edges.clear();f.initial.state={{0,3},{0,0}};
    f.initial.canonical_energy_error_j=.125;f.budget=.15;
    f.request.initial_liquid_withdrawals.clear();f.request.forcing.id="idle-0";
    f.request.imports={{"zero-0",0,a::Phase::solid,.25,1},{"zero-1",1,a::Phase::solid,.25,1}};fs.push_back(f);
    f=base("wet_sensible_node");f.cells[1].is_lake=true;f.cells[1].water_depth_m=2;
    f.request.forcing.absorbed_shortwave_w_m2[1]=1;fs.push_back(f);
    f=base("adaptive_source");f.properties.columns[0].heat_capacity_j_m2_k=1;f.initial.state={{0,1},{0,0}};
    f.initial.canonical_energy_error_j=.001;f.budget=.1;f.request.end_seconds=1;f.request.forcing={"adapt-0",0,1,{0,0}};
    f.request.initial_liquid_withdrawals.clear();f.request.imports={{"adapt-snow",0,a::Phase::solid,.125,1}};
    f.request.options.maximum_step_seconds=1;f.request.options.maximum_attempts=64;f.request.options.maximum_accepted_steps=64;fs.push_back(f);
    f=base("physical_source_mesh");f.cells.resize(3);
    for(int i=0;i<3;++i) {auto& c=f.cells[i];c.id=i;c.p={1,0,0};c.area_km2=(i+1)*1e-6;c.temperature_c=10;c.precipitation_mm_y=120;}
    f.cells[0].neighbors={1};f.cells[1].neighbors={0,2};f.cells[2].neighbors={1};f.cells[2].is_water=true;f.cells[2].water_depth_m=20;
    f.properties={{273.15,2100,4186,334000},1000,31557600,{{1,1e7,.75},{2,1.2e7,.8},{3,2e7,.7}},{{0,1,100},{1,2,50}}};
    f.initial.state={{10,-1e6},{10,1e6},{0,8e6}};f.initial.canonical_energy_error_j=7;f.budget=3340;
    f.request.end_seconds=60;f.request.forcing={"physical-0",0,60,{300,600,100}};
    f.request.imports={{"physical-snow",0,a::Phase::solid,.5,263.15},{"physical-rain",1,a::Phase::liquid,.25,273.15}};
    f.request.initial_liquid_withdrawals={{"physical-drain",1,.1}};f.request.options.maximum_step_seconds=60;f.request.options.maximum_stage_error_j=.001;fs.push_back(f);
    f=base("late_partial_refusal");f.request.end_seconds=1;f.request.forcing.end_seconds=1;
    f.request.options.maximum_attempts=1;f.expected_failure="work_cap";fs.push_back(f);
    f=base("uncertain_liquid_refusal");f.initial.state[0]={1,.5};f.initial.canonical_energy_error_j=.2;f.budget=1;
    f.request.initial_liquid_withdrawals={{"uncertain",0,.4}};f.expected_failure="source_error_refusal";fs.push_back(f);
    f=base("same_batch_rain_refusal");f.initial.state[0]={0,3};f.request.imports={{"rain",0,a::Phase::liquid,1,1}};
    f.request.initial_liquid_withdrawals={{"unfunded",0,.1}};f.expected_failure="mass_refused";fs.push_back(f);
    f=base("untouched_wet_domain_refusal");f.cells[1].area_km2=1e-6;f.cells[1].is_lake=true;f.cells[1].water_depth_m=2;
    f.properties.columns={{1,1,0},{1,1,0}};f.properties.edges.clear();f.initial.state={{0,9007199254740992.0},{0,0}};
    f.initial.canonical_energy_error_j=.125;f.budget=16;f.request.initial_liquid_withdrawals.clear();
    f.request.imports={{"rounding-rain",0,a::Phase::liquid,1,1}};f.expected_failure="uncertain_physical_domain";fs.push_back(f);
    f.id="global_jump_budget_refusal";f.budget=.25;f.expected_failure="cumulative_error_budget";fs.push_back(f);
    f=base("duplicate_event_refusal");f.request.imports={{"dup",0,a::Phase::solid,.125,1},{"dup",0,a::Phase::solid,.125,1}};
    f.expected_failure="duplicate_event";fs.push_back(f);
    f=base("cross_kind_event_refusal");f.request.imports={{"drain-0",0,a::Phase::solid,.125,1}};
    f.expected_failure="duplicate_event";fs.push_back(f);
    f=base("wet_event_refusal");f.cells[1].is_lake=true;f.cells[1].water_depth_m=2;f.request.imports={{"wet",1,a::Phase::solid,.125,1}};
    f.expected_failure="invalid_event";fs.push_back(f);
    f=base("phase_temperature_refusal");f.request.imports={{"warm-solid",0,a::Phase::solid,.125,2}};
    f.expected_failure="invalid_event";fs.push_back(f);
    f=base("reservation_before_source_refusal");f.limits.max_scalar_evaluations_per_prepare=1;f.expected_failure="work_cap";fs.push_back(f);
    f=base("forcing_coverage_refusal");f.request.forcing.absorbed_shortwave_w_m2.pop_back();f.expected_failure="forcing_refusal";fs.push_back(f);
    f=base("forcing_boundary_refusal");f.request.forcing.end_seconds=.125;f.expected_failure="forcing_refusal";fs.push_back(f);
    f=base("nonexact_clock_refusal");f.initial.elapsed_seconds=.1;f.request.end_seconds=.3;f.request.forcing={"nonexact",.1,.3,{0,0}};
    f.expected_failure="clock_refusal";fs.push_back(f);
    return fs;
}
std::vector<Fixture> sequences() {
    auto f=base("committed_source_successor");f.initial_binding="combined_capacity_donor";
    f.request.expected_revision=1;f.request.end_seconds=.5;f.request.forcing={"cool-1",.25,.5,{0,0}};
    f.request.imports={{"snow-1",0,a::Phase::solid,.25,1}};f.request.initial_liquid_withdrawals={{"drain-1",0,.125}};
    std::vector<Fixture> result{f};
    f.id="consumed_source_refusal";f.initial_binding="committed_source_successor";f.request.expected_revision=2;
    f.request.end_seconds=.75;f.request.forcing={"cool-2",.5,.75,{0,0}};f.request.imports.clear();f.request.initial_liquid_withdrawals={{"drain-0",0,.125}};
    f.expected_failure="duplicate_event";result.push_back(f);
    f.id="stale_revision_refusal";f.request.expected_revision=0;f.expected_failure="stale_revision";result.push_back(f);
    f.id="changed_forcing_refusal";f.request.expected_revision=2;f.request.initial_liquid_withdrawals.clear();
    f.request.forcing.id="cool-0";f.expected_failure="forcing_identity_refusal";result.push_back(f);
    f=fixtures()[1];f.id="empty_source_successor";f.initial_binding="zero_energy_sources";
    f.request.expected_revision=1;f.request.end_seconds=.5;f.request.forcing={"idle-1",.25,.5,{0,0}};f.request.imports.clear();result.push_back(f);
    return result;
}
std::string descriptor(const Fixture& f) {
    // Literal serializer-only descriptor, not an executed owner receipt.
    EnthalpyMeshOwnerReceipt d;d.surface_revision=53;d.surface_cells=f.cells;d.properties=f.properties;d.limits=f.limits;
    d.maximum_cumulative_error_j=f.budget;d.initial=f.initial;d.observed_accepted_after=f.initial;d.private_prefix=f.initial;
    if(!f.initial_binding.empty()) {d.initial={};d.observed_accepted_after={};d.private_prefix={};}
    d.request=f.request;
    return "{\"id\":\""+f.id+"\",\"expected_failure\":\""+f.expected_failure+"\",\"initial_binding\":\""+f.initial_binding+
        "\",\"unexecuted_context_and_request\":"+enthalpy_mesh_owner_receipt_json(d)+'}';
}
std::string inventory(const std::vector<Fixture>& fs,const std::vector<Fixture>& seq) {
    std::string result="{\"schema\":\"enthalpy_mesh_owner_inventory_v1\",\"execution\":\"none\",\"planned_prepares\":23,\"prepare_cap\":23,\"maximum_commit_attempts\":6,\"thermal_call_cap\":240,\"mass_call_cap\":11,\"fixtures\":[";
    for(std::size_t i=0;i<fs.size();++i){if(i)result+=',';result+=descriptor(fs[i]);}result+="],\"successors\":[";
    for(std::size_t i=0;i<seq.size();++i){if(i)result+=',';result+=descriptor(seq[i]);}return result+"]}";
}
EnthalpyMeshOwner owner(const Fixture& f) {
    return EnthalpyMeshOwner(capture_terrestrial_surface(f.cells,53),f.properties,f.initial,f.budget,f.limits);
}
void inspect(const Fixture& f,const EnthalpyMeshOwnerReceipt& r) {
    const auto label=[&](const char* suffix){return f.id+'.'+suffix;};
    check(r.prepared==f.expected_failure.empty() && (r.prepared || r.failure_code==f.expected_failure),label("expected_outcome"));
    check(r.final.has_value()==r.prepared,label("final_availability"));
    check(enthalpy_mesh_restart_json(r.initial)==enthalpy_mesh_restart_json(r.observed_accepted_after),label("accepted_unchanged_during_prepare"));
    check(r.observed_request_after && enthalpy_mesh_interval_request_json(*r.observed_request_after)==enthalpy_mesh_interval_request_json(f.request),label("input_unchanged"));
    const auto& w=r.work_after;const auto& before=r.work_before;
    count.mass_started+=w.mass_calls_started-before.mass_calls_started;count.mass_returned+=w.mass_calls_returned-before.mass_calls_returned;
    count.thermal_started+=w.thermal_calls_started-before.thermal_calls_started;count.thermal_returned+=w.thermal_calls_returned-before.thermal_calls_returned;
    count.scalar+=w.scalar_evaluations-before.scalar_evaluations;count.fields+=w.field_evaluations-before.field_evaluations;
    count.sweeps+=w.sweeps_started-before.sweeps_started;count.coordinates+=w.coordinate_solves_started-before.coordinate_solves_started;
    count.leaves+=w.reconstruction_leaves_started-before.reconstruction_leaves_started;
    check(w.observed_counts_complete && w.prepare_attempts==before.prepare_attempts+1,label("work_observed"));
    check(w.mass_calls_started-before.mass_calls_started<=1,label("source_at_most_once"));
    const bool sourced=!f.request.imports.empty() || !f.request.initial_liquid_withdrawals.empty();
    if(!sourced)check(!r.mass_call_started && !r.mass_receipt && !r.thermal_initial,label("empty_source_identity"));
    if(r.jump.available) {
        check(r.thermal_initial && r.private_prefix_error_available,label("certified_source_anchor"));
        check(r.jump.final_error_j>=r.initial.canonical_energy_error_j && r.jump.final_error_j<=f.budget,label("global_source_budget"));
        check(r.thermal_initial->revision==r.initial.revision && r.thermal_initial->elapsed_seconds==r.initial.elapsed_seconds &&
              r.thermal_initial->consumed_event_ids==r.initial.consumed_event_ids,label("source_not_published_early"));
    }
    auto state=r.thermal_initial?r.thermal_initial->state:r.initial.state;
    double E=r.thermal_initial?r.thermal_initial->canonical_energy_error_j:r.initial.canonical_energy_error_j;
    double clock=r.initial.elapsed_seconds;std::size_t carried=0,refused=0;
    for(const auto& t:r.trials) {
        check(t.start_seconds==clock && t.inherited_error_j==E,label("common_clock_error_anchor"));
        if(t.receipt && t.receipt->request) {
            const auto& q=*t.receipt->request;bool raw=q.initial_enthalpy_j_m2.size()==state.size();
            for(std::size_t i=0;i<state.size() && raw;++i) raw=q.initial_enthalpy_j_m2[i]==state[i].enthalpy_j_m2 && q.water_mass_kg_m2[i]==state[i].water_mass_kg_m2;
            check(raw && q.absorbed_shortwave_w_m2==f.request.forcing.absorbed_shortwave_w_m2,label("whole_mesh_raw_carry"));
        }
        if(t.accepted_for_private_carry) {
            ++carried;check(t.before_domain.proved && t.after_domain.proved && t.receipt && t.receipt->accepted && t.charged_increment_available,label("carry_proofs"));
            check(t.proposed_final_error_j>=E && t.proposed_final_error_j<=f.budget && t.charged_increment_j.upper<=t.offered_error_j,label("charged_global_quota"));
            for(std::size_t i=0;i<state.size();++i)state[i].enthalpy_j_m2=(*t.receipt->final_enthalpy_j_m2)[i];
            E=t.proposed_final_error_j;clock=t.end_seconds;
        } else ++refused;
    }
    if(r.prepared) {
        check(r.final->elapsed_seconds==f.request.end_seconds && r.final->revision==r.initial.revision+1,label("complete_common_endpoint"));
        check(r.final->state==state && r.final->canonical_energy_error_j==E,label("final_raw_carry"));
        check(r.projection && r.discrete_ledger && r.private_prefix_error_available,label("complete_bundle"));
    }
    if(f.id=="combined_capacity_donor" && r.prepared) {
        check(r.kernel_columns[0].dry_heat_capacity_j_m2_k==3,label("combined_capacity_in_A"));
        near(r.private_liquid_outbox[0].carried_enthalpy_j,.75,0,label("donor_carried_energy"));
        near(r.thermal_initial->state[0].water_mass_kg_m2,.5,0,label("post_source_W"));
        near(r.thermal_initial->state[0].enthalpy_j_m2,2.25,0,label("post_source_H"));
        near(r.final->state[0].enthalpy_j_m2,575.0/268,1e-10,label("first_rational_BE_root"));
        near(r.final->state[1].enthalpy_j_m2,7.0/134,1e-10,label("second_rational_BE_root"));
    }
    if(f.id=="zero_energy_sources" && r.prepared) {
        check(r.jump.final_error_j==.125 && r.final->canonical_energy_error_j==.125,label("inherited_global_error_charged_once"));
        check(r.final->state[0].water_mass_kg_m2==.25 && r.final->state[1].water_mass_kg_m2==.125,label("area_scaled_sources"));
    }
    if(f.id=="empty_source_successor" && r.prepared)check(r.final->state==r.initial.state && r.final->canonical_energy_error_j==r.initial.canonical_energy_error_j,label("empty_interval_carries_exact_error"));
    if(f.id=="wet_sensible_node" && r.prepared)check(r.final->state[1].water_mass_kg_m2==0 && r.final->state[1].enthalpy_j_m2>0 && r.kernel_column_cell_ids==std::vector<int>{0},label("wet_thermal_not_source_column"));
    if(f.id=="adaptive_source" && r.prepared)check(refused>0 && carried>1 && w.mass_calls_started-before.mass_calls_started==1,label("bounded_global_adaptation"));
    if(f.id=="late_partial_refusal")check(!r.prepared && r.jump.available && carried==1 && r.private_prefix.elapsed_seconds>r.initial.elapsed_seconds &&
        r.private_prefix.consumed_event_ids==r.initial.consumed_event_ids,label("late_refusal_keeps_private_prefix"));
    if(f.id=="uncertain_liquid_refusal")check(r.mass_receipt && !r.jump.available && !r.private_prefix_error_available && !r.trials.size(),label("nominal_A_not_uncertain_feasibility"));
    if(f.id=="same_batch_rain_refusal")check(r.mass_call_started && !r.mass_receipt && !r.thermal_initial && r.private_prefix_error_available,label("initial_inventory_A_refusal"));
    if(f.id=="untouched_wet_domain_refusal")check(r.mass_receipt && !r.jump.available && r.jump.after_domain.attempted && !r.jump.after_domain.proved && !r.private_prefix_error_available && r.trials.empty(),label("all_cell_post_jump_domain"));
    if(f.id=="global_jump_budget_refusal")check(r.mass_receipt && !r.jump.available && !r.private_prefix_error_available && r.trials.empty(),label("jump_budget_before_thermal"));
    if(f.id.find("event_refusal")!=std::string::npos || f.id=="phase_temperature_refusal" || f.id=="reservation_before_source_refusal" ||
       f.id=="forcing_coverage_refusal" || f.id=="forcing_boundary_refusal" || f.id=="nonexact_clock_refusal" ||
       f.id=="consumed_source_refusal" || f.id=="stale_revision_refusal" || f.id=="changed_forcing_refusal")
        check(!r.mass_call_started && r.trials.empty() && w.mass_calls_started==before.mass_calls_started &&
              w.thermal_calls_started==before.thermal_calls_started,label("preflight_zero_physical_calls"));
}
EnthalpyMeshPreparation prepare(EnthalpyMeshOwner& owner,const Fixture& f,const std::string& owner_id) {
    if(count.prepares>=23)throw std::runtime_error("declared prepare cap");
    const auto before=enthalpy_mesh_owner_context_json(owner);++count.prepares;
    const auto result=owner.prepare(f.request);count.candidates+=result.candidate?1:0;
    std::cout<<"{\"kind\":\"prepare\",\"id\":\""<<f.id<<"\",\"owner_id\":\""<<owner_id<<"\",\"context_before\":"<<before
             <<",\"request\":"<<enthalpy_mesh_interval_request_json(f.request)<<",\"receipt\":"<<enthalpy_mesh_owner_receipt_json(*result.diagnostic)
             <<",\"context_after\":"<<enthalpy_mesh_owner_context_json(owner)<<"}\n";
    check(result.candidate.has_value()==result.diagnostic->prepared,f.id+".candidate_diagnostic_equivalence");
    inspect(f,*result.diagnostic);return result;
}
void commit(EnthalpyMeshOwner& owner,const EnthalpyMeshIntervalCandidate& candidate,const std::string& id,const std::string& owner_id,
            const std::string& candidate_id,const std::string& expected) {
    if(count.commits>=6)throw std::runtime_error("declared commit cap");
    const auto before=enthalpy_mesh_owner_context_json(owner);++count.commits;std::string code;
    try {owner.commit(candidate);}catch(const TerrestrialWaterError& e){code=e.code;}
    const auto after=enthalpy_mesh_owner_context_json(owner);
    std::cout<<"{\"kind\":\"commit\",\"id\":\""<<id<<"\",\"owner_id\":\""<<owner_id<<"\",\"candidate_id\":\""<<candidate_id
             <<"\",\"success\":"<<(code.empty()?"true":"false")<<",\"failure_code\":\""<<code<<"\",\"before\":"<<before<<",\"after\":"<<after<<"}\n";
    check(code==expected,id+".expected_commit");
    check(code.empty()?enthalpy_mesh_restart_json(owner.restart())==enthalpy_mesh_restart_json(*candidate.receipt().final):before==after,id+".atomic_bundle");
}
} // namespace
int main(int argc,char** argv) {
    const bool only_inventory=argc==2 && std::string(argv[1])=="--inventory";
    if(argc>1 && !only_inventory)return 2;
    std::cout<<std::setprecision(17);const auto fs=fixtures(),seq=sequences();const auto inv=inventory(fs,seq);
    if(only_inventory){std::cout<<inv<<'\n';return 0;}
    std::cout<<"{\"kind\":\"inventory\",\"inventory\":"<<inv<<"}\n";
    for(const auto& f:fs) {
        auto owned=owner(f);const auto result=prepare(owned,f,f.id);
        if(f.id=="combined_capacity_donor" && result.candidate) {
            auto other=owner(f);commit(other,*result.candidate,"foreign_commit", "foreign-owner",f.id,"foreign_candidate");
            commit(owned,*result.candidate,"commit_donor",f.id,f.id,"");
            commit(owned,*result.candidate,"duplicate_commit",f.id,f.id,"stale_candidate");
            for(std::size_t i=0;i<4;++i) {
                auto next=seq[i];next.initial=owned.restart();const auto continuation=prepare(owned,next,f.id);
                if(i==0 && continuation.candidate) commit(owned,*continuation.candidate,"commit_successor",f.id,next.id,"");
            }
        }
        if(f.id=="zero_energy_sources" && result.candidate) {
            commit(owned,*result.candidate,"commit_zero_sources",f.id,f.id,"");
            auto next=seq[4];next.initial=owned.restart();const auto continuation=prepare(owned,next,f.id);
            if(continuation.candidate)commit(owned,*continuation.candidate,"commit_empty_successor",f.id,next.id,"");
        }
    }
    check(count.prepares==23 && count.commits==6 && count.candidates==7 && count.prepares-count.candidates==16,"declared_owner_counts");
    check(count.thermal_started<=240 && count.mass_started<=11,"declared_kernel_caps");
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<count.checks<<",\"misses\":"<<count.misses<<",\"prepares\":"<<count.prepares
             <<",\"commits\":"<<count.commits<<",\"candidates\":"<<count.candidates<<",\"mass_started\":"<<count.mass_started
             <<",\"mass_returned\":"<<count.mass_returned<<",\"thermal_started\":"<<count.thermal_started<<",\"thermal_returned\":"<<count.thermal_returned
             <<",\"scalar\":"<<count.scalar<<",\"fields\":"<<count.fields<<",\"sweeps\":"<<count.sweeps<<",\"coordinates\":"<<count.coordinates<<",\"leaves\":"<<count.leaves<<"}\n";
    return count.misses?1:0;
}
