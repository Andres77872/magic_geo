#include "layered_ice_owner.hpp"

#include <bit>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <string>
#include <vector>

namespace {
using namespace magic_geo::detail;
using Phase = cryosphere_prototype::Phase;
constexpr std::uint64_t revision = 117;
int checks=0,failures=0,captures=0,constructors=0,prepares=0,commits=0;
void check(bool ok,const std::string& name) {
    ++checks;if(!ok)++failures;
    std::cout<<"{\"kind\":\"check\",\"name\":"<<std::quoted(name)<<",\"passed\":"<<(ok?"true":"false")<<"}\n";
}
std::vector<Cell> geography() {
    std::vector<Cell> cells(1);auto& c=cells[0];c.id=0;c.area_km2=1e-6;
    c.elevation_m=1;c.filled_elevation_m=1;c.hydrologic_surface_elevation_m=1;
    c.hydrologic_surface_conditioned=true;c.flow_to=-1;return cells;
}
LayeredIceInput input(bool large=false) {
    LayeredIceInput in;in.id=large?"large_inherited_E_rounding_fixture":"short_latent_quota_fixture";
    in.complete_horizontal_coverage_declared=true;in.bottom_boundary=LayeredIceBottomBoundary::insulated;
    in.water={10,1,2,4};
    in.columns={{0,1,LayeredIceTopClosure::prescribed_nonwater_top_capacity,large?0x1p60:1,0,1,
                 {{0,1,1,1,1}},std::nullopt}};return in;
}
LayeredIceOwnerRequest request(const std::string& id,double begin=0) {
    LayeredIceOwnerRequest q;q.id=id;q.expected_revision=static_cast<std::uint64_t>(begin);q.end_seconds=begin+1;
    q.forcing=LayeredIceOwnerForcing{"first_fixed_window",0,2,{1}};
    EnthalpyMeshOptions o;o.duration_seconds=1;o.maximum_stage_error_j=1e-8;o.maximum_endpoint_error_j=1e-6;
    o.maximum_sweeps=16;o.maximum_coordinate_iterations=32;o.maximum_scalar_evaluations=4096;
    o.reconstruction_leaves=1;o.allow_pure_water_columns=true;q.thermal=o;q.maximum_thermal_error_increment_j=1e-6;
    return q;
}
LayeredIceOwnerSeed seed(const std::string& id,const SeasonalLiquidRoutingGraph& graph,bool large=false) {
    return {id,input(large),0,large?0x1p40:.25,graph,{0},{},{},{}};
}
std::string snapshot(const LayeredIceOwner& owner) {return layered_ice_owner_snapshot_json(*owner.snapshot());}
LayeredIceOwnerPreparation prepare(LayeredIceOwner& owner,const std::string& name,const LayeredIceOwnerRequest& q,
                                  const std::vector<Cell>& cells) {
    const auto before=snapshot(owner);++prepares;auto result=owner.prepare(q,cells,revision);
    std::cout<<"{\"kind\":\"prepare\",\"name\":"<<std::quoted(name)<<",\"request\":"<<layered_ice_owner_request_json(q)
             <<",\"observed\":"<<seasonal_liquid_routing_input_json(cells,revision,{})<<",\"before\":"<<before
             <<",\"after\":"<<snapshot(owner)<<",\"receipt\":"<<layered_ice_owner_receipt_json(*result.diagnostic)
             <<",\"current_work\":"<<layered_ice_owner_work_json(owner.work())<<"}\n";
    check(before==snapshot(owner),name+"_prepare_preserves_state");return result;
}
LayeredIceOwnerCommit commit(LayeredIceOwner& owner,const std::string& name,const LayeredIceOwnerCandidate& c,
                            const std::vector<Cell>& cells) {
    const auto before=snapshot(owner);++commits;const auto result=owner.commit(c,cells,revision);
    std::cout<<"{\"kind\":\"commit\",\"name\":"<<std::quoted(name)<<",\"transaction_id\":"
             <<std::quoted(c.receipt().request->id)<<",\"observed\":"<<seasonal_liquid_routing_input_json(cells,revision,{})
             <<",\"before\":"<<before<<",\"after\":"<<snapshot(owner)<<",\"accepted\":"<<(result.accepted?"true":"false")
             <<",\"replayed\":"<<(result.replayed?"true":"false")<<",\"failure_code\":"<<std::quoted(result.failure_code)<<"}\n";
    return result;
}
void constructed(const std::string& name,const LayeredIceOwner& owner) {
    std::cout<<"{\"kind\":\"constructed\",\"name\":"<<std::quoted(name)<<",\"snapshot\":"<<snapshot(owner)
             <<",\"work\":"<<layered_ice_owner_work_json(owner.work())<<"}\n";
}
void inventory() {
    const auto cells=geography();
    std::cout<<"{\"kind\":\"inventory\",\"scope\":\"new_short_manufactured_quota_and_forcing_controls\",\"execution\":\"none\","
             <<"\"planned_captures\":1,\"planned_constructors\":9,\"planned_prepares\":13,\"planned_commits\":5,"
             <<"\"planned_builders\":14,\"planned_thermal_calls\":5,\"planned_BE_calls\":10,\"planned_material_calls\":1,\"planned_calorimeter_calls\":1,"
             <<"\"world_calls\":0,\"historical_calls\":0,\"geography\":"<<seasonal_liquid_routing_input_json(cells,revision,{})
             <<",\"ordinary_source\":"<<layered_ice_input_json(input())<<",\"large_E_source\":"<<layered_ice_input_json(input(true))
             <<",\"ordinary_E\":0.25,\"ordinary_budget\":1,\"large_E\":1099511627776,\"large_budget\":1099511627777,\"requests\":[";
    std::vector<LayeredIceOwnerRequest> requests;
    auto q=request("negative_quota");q.maximum_thermal_error_increment_j=-1;requests.push_back(q);
    q=request("zero_quota");q.maximum_thermal_error_increment_j=0;requests.push_back(q);
    q=request("nan_quota");q.maximum_thermal_error_increment_j=std::bit_cast<double>(UINT64_C(0x7ff8000000000012));requests.push_back(q);
    q=request("infinite_quota");q.maximum_thermal_error_increment_j=std::numeric_limits<double>::infinity();requests.push_back(q);
    q=request("quota_without_thermal");q.thermal.reset();q.forcing.reset();q.end_seconds=0;
    q.movements={{"unused_source",{-1,-1},{0,0},Phase::liquid,1,10}};requests.push_back(q);
    requests.push_back(request("first"));requests.push_back(request("first"));
    q=request("first");q.maximum_thermal_error_increment_j=2e-6;requests.push_back(q);
    requests.push_back(request("same_forcing",1));
    q=request("new_forcing_exceeds_cap",2);q.forcing=LayeredIceOwnerForcing{"new_window",2,3,{1}};requests.push_back(q);
    requests.push_back(request("rounded_quota_refusal"));q=request("same_point_without_quota");q.maximum_thermal_error_increment_j.reset();requests.push_back(q);
    q=request("source_then_quota");q.movements={{"fresh_liquid",{-1,-1},{0,0},Phase::liquid,1,10}};requests.push_back(q);
    bool first=true;for(const auto& x:requests){if(!first)std::cout<<',';first=false;std::cout<<layered_ice_owner_request_json(x);}
    std::cout<<"],\"full_calendar_design\":{\"scope\":\"retained_Earthlike_window_count_only_calendar_not_rebuilt\","
             <<"\"declared_geographic_cells\":128,\"retained_reference_window_count\":1080,\"unique_forcing_values\":138240,"
             <<"\"default_prepare_cap\":256,\"hard_prepare_cap\":4096,\"default_commit_cap\":128,\"hard_commit_cap\":2048,"
             <<"\"default_forcing_value_cap\":524288,\"hard_forcing_value_cap\":2097152,"
             <<"\"full_record_slot_bytes\":67108864,\"complete_history_slot_bytes\":72477573120,\"history_cap_bytes\":134217728,"
             <<"\"counts_and_forcing_can_be_explicitly_admitted\":true,\"complete_full_year_admitted\":false,\"annual_accuracy_certified\":false}}\n";
}
int run() {
    const auto cells=geography();++captures;const auto graph=capture_seasonal_liquid_routing_graph(cells,revision);
    LayeredIceOwnerLimits limits;limits.max_stored_forcing_values=1;
    ++constructors;LayeredIceOwner owner(seed("quota_owner",graph),1,limits);constructed("quota_owner",owner);
    const auto reject=[&](const LayeredIceOwnerRequest& q,const std::string& code) {
        const auto result=prepare(owner,q.id,q,cells);const auto& r=*result.diagnostic;
        check(!result.candidate && r.failure_code==code && r.work.graph_builds_started==0 && r.work.thermal_calls_started==0,
              q.id+"_refuses_before_native_physics");
        check(!r.thermal_error_charge && !r.final,q.id+"_no_uncomputed_charge_or_final");
    };
    auto q=request("negative_quota");q.maximum_thermal_error_increment_j=-1;reject(q,"thermal_quota_refusal");
    q=request("zero_quota");q.maximum_thermal_error_increment_j=0;reject(q,"thermal_quota_refusal");
    q=request("nan_quota");q.maximum_thermal_error_increment_j=std::bit_cast<double>(UINT64_C(0x7ff8000000000012));reject(q,"thermal_quota_refusal");
    check(layered_ice_owner_request_json(q).find("7ff8000000000012")!=std::string::npos,"invalid_quota_payload_is_serialized_losslessly");
    q=request("infinite_quota");q.maximum_thermal_error_increment_j=std::numeric_limits<double>::infinity();reject(q,"thermal_quota_refusal");
    q=request("quota_without_thermal");q.thermal.reset();q.forcing.reset();q.end_seconds=0;
    q.movements={{"unused_source",{-1,-1},{0,0},Phase::liquid,1,10}};reject(q,"thermal_quota_refusal");
    const auto first=prepare(owner,"first",request("first"),cells);
    check(first.candidate.has_value(),"positive_quota_prepared");if(!first.candidate)return 1;
    const auto& charge=*first.diagnostic->thermal_error_charge;
    check(charge.quota_passed && charge.charged_increment_j.upper<=1e-6 && charge.before_global_energy_error_j==.25 &&
          charge.after_global_energy_error_j==first.diagnostic->final->joint_energy_error_j,"accepted_charge_witness_matches_final_E");
    check(commit(owner,"first",*first.candidate,cells).accepted,"first_quota_commit");
    const auto accepted=snapshot(owner);const auto before=owner.work();
    const auto replay=prepare(owner,"first_replay",request("first"),cells);
    check(replay.replayed_committed_transaction && !replay.candidate &&
          layered_ice_owner_receipt_json(*replay.diagnostic)==layered_ice_owner_receipt_json(*first.diagnostic),"exact_replay_retains_original_charge");
    check(owner.work().thermal_calls_started==before.thermal_calls_started && owner.work().prepare_attempts==before.prepare_attempts+1,
          "replay_has_no_new_thermal_charge_or_call");
    const auto replay_commit=commit(owner,"first_replay",*first.candidate,cells);
    check(replay_commit.accepted && replay_commit.replayed && snapshot(owner)==accepted,"commit_replay_does_not_charge_twice");
    q=request("first");q.maximum_thermal_error_increment_j=2e-6;
    const auto conflict=prepare(owner,"changed_quota_same_id",q,cells);
    check(conflict.diagnostic->failure_code=="transaction_id_conflict" && !conflict.candidate,"quota_binds_transaction_identity");
    const auto second=prepare(owner,"same_forcing",request("same_forcing",1),cells);
    check(second.candidate.has_value(),"known_forcing_at_value_cap_allowed");if(!second.candidate)return 1;
    check(commit(owner,"same_forcing",*second.candidate,cells).accepted && owner.snapshot()->forcing_history.size()==1,
          "known_forcing_not_stored_twice");
    q=request("new_forcing_exceeds_cap",2);q.forcing=LayeredIceOwnerForcing{"new_window",2,3,{1}};
    reject(q,"forcing_capacity_refusal");

    ++constructors;LayeredIceOwner large(seed("large_E_owner",graph,true),0x1p40+1);constructed("large_E_owner",large);
    const auto refused=prepare(large,"rounded_quota_refusal",request("rounded_quota_refusal"),cells);
    const auto& rr=*refused.diagnostic;
    check(!refused.candidate && rr.failure_code=="thermal_increment_budget" && rr.thermal && rr.thermal->accepted,
          "local_acceptance_cannot_bypass_rounded_global_quota");
    check(rr.thermal_error_charge.has_value(),"refused_charge_retained");
    if(rr.thermal_error_charge) {
        const auto& x=*rr.thermal_error_charge;
        check(x.local_endpoint_error_upper_j>0 && x.local_endpoint_error_upper_j<=1e-6 &&
              x.after_global_energy_error_j-x.before_global_energy_error_j==0x1p-12 &&
              x.charged_increment_j.lower<=0x1p-12 && x.charged_increment_j.upper>=0x1p-12 &&
              x.charged_increment_j.upper>1e-6 && !x.quota_passed,
              "positive_local_U_rounds_global_E_up_past_quota");
    }
    check(!rr.final && !rr.thermal_ledger && rr.work.graph_builds_started==1,"quota_refusal_stops_before_final_graph_and_ledger");
    q=request("same_point_without_quota");q.maximum_thermal_error_increment_j.reset();
    const auto unrestricted=prepare(large,q.id,q,cells);
    check(unrestricted.candidate.has_value(),"same_point_without_quota_is_still_accepted");if(!unrestricted.candidate)return 1;
    check(unrestricted.diagnostic->thermal_error_charge->quota_passed &&
          !unrestricted.diagnostic->thermal_error_charge->maximum_thermal_error_increment_j,"absent_quota_is_explicit_in_witness");
    check(commit(large,"no_quota",*unrestricted.candidate,cells).accepted,"no_quota_control_commits");

    ++constructors;LayeredIceOwner sourced(seed("source_owner",graph),1);constructed("source_owner",sourced);
    q=request("source_then_quota");q.movements={{"fresh_liquid",{-1,-1},{0,0},Phase::liquid,1,10}};
    const auto source=prepare(sourced,q.id,q,cells);
    check(source.candidate.has_value(),"explicit_source_before_thermal_quota");if(!source.candidate)return 1;
    check(source.diagnostic->material && source.diagnostic->material->accepted && source.diagnostic->thermal_error_charge &&
          source.diagnostic->thermal_error_charge->before_global_energy_error_j==source.diagnostic->material->joint_final_energy_error_upper_j,
          "quota_starts_after_material_error_charge");
    check(commit(sourced,"source_then_quota",*source.candidate,cells).accepted &&
          sourced.snapshot()->graph.input().columns[0].layers[0].water_mass_kg_m2==2,"source_mass_and_thermal_state_commit_atomically");

    LayeredIceOwnerLimits expanded;expanded.max_prepare_attempts=4096;expanded.max_commits=2048;expanded.max_stored_forcing_values=2097152;
    auto prior=seed("explicit_expanded_limits",graph);prior.elapsed_seconds=1;
    prior.forcing_history={{"seed_window",0,2,{1}}};
    ++constructors;LayeredIceOwner expanded_owner(prior,1,expanded);constructed("explicit_expanded_limits",expanded_owner);
    check(expanded_owner.snapshot()->forcing_history.size()==1,"explicit_hard_counts_and_forcing_cap_admit_valid_seed");
    const auto bad_constructor=[&](const std::string& name,LayeredIceOwnerSeed s,LayeredIceOwnerLimits l,const std::string& expected) {
        ++constructors;std::string code;
        try{LayeredIceOwner impossible(std::move(s),1,l);}catch(const LayeredIceError& e){code=e.code;}
        std::cout<<"{\"kind\":\"constructor_refusal\",\"name\":"<<std::quoted(name)<<",\"failure_code\":"<<std::quoted(code)<<"}\n";
        check(code==expected,name);
    };
    auto bad=expanded;bad.max_prepare_attempts=4097;bad_constructor("prepare_hard_cap",prior,bad,"invalid_limits");
    bad=expanded;bad.max_commits=2049;bad_constructor("commit_hard_cap",prior,bad,"invalid_limits");
    bad=expanded;bad.max_stored_forcing_values=2097153;bad_constructor("forcing_hard_cap",prior,bad,"invalid_limits");
    bad=expanded;bad.max_stored_forcing_values=0;bad_constructor("zero_forcing_cap",prior,bad,"invalid_limits");
    auto over=seed("oversized_seed_forcing",graph);over.elapsed_seconds=2;
    over.forcing_history={{"old_0",0,1,{1}},{"old_1",1,2,{1}}};
    bad_constructor("seed_forcing_values_cap",over,limits,"forcing_capacity_refusal");
    const auto a=owner.work(),z=large.work(),s=sourced.work(),e=expanded_owner.work();
    const auto builders=a.graph_builds_started+z.graph_builds_started+s.graph_builds_started+e.graph_builds_started;
    const auto thermal=a.thermal_calls_started+z.thermal_calls_started+s.thermal_calls_started+e.thermal_calls_started;
    const auto be=a.internal_be_calls_started+z.internal_be_calls_started+s.internal_be_calls_started+e.internal_be_calls_started;
    check(captures==1 && constructors==9 && prepares==13 && commits==5 && builders==14 && thermal==5 && be==10 &&
          s.material_calls_started==1 && s.calorimeter_calls_started==1,"fixed_short_qualification_envelope");
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<checks<<",\"failures\":"<<failures<<",\"captures\":"<<captures
             <<",\"constructors\":"<<constructors<<",\"prepares\":"<<prepares<<",\"commits\":"<<commits<<",\"builders\":"<<builders
             <<",\"thermal_calls\":"<<thermal<<",\"BE_calls\":"<<be<<",\"material_calls\":"<<s.material_calls_started
             <<",\"calorimeter_calls\":"<<s.calorimeter_calls_started<<",\"world_calls\":0,\"historical_calls\":0}\n";
    return failures?1:0;
}
} // namespace
int main(int argc,char** argv) {
    std::cout.imbue(std::locale::classic());std::cout<<std::setprecision(17);
    if(argc==2 && std::string(argv[1])=="--inventory"){inventory();return 0;}
    if(argc!=2 || std::string(argv[1])!="--run")return 2;
    try{return run();}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
