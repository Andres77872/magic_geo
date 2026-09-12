#include "layered_ice_owner.hpp"

#include <iomanip>
#include <iostream>
#include <locale>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace {
using namespace magic_geo::detail;
using Phase=cryosphere_prototype::Phase;
constexpr std::uint64_t geographic_revision=417;
int checks=0,failures=0,captures=0,constructors=0,prepares=0,commits=0;
void check(bool ok,const std::string& name) {
    ++checks;if(!ok)++failures;
    std::cout<<"{\"kind\":\"check\",\"name\":"<<std::quoted(name)
             <<",\"passed\":"<<(ok?"true":"false")<<"}\n";
}
std::vector<Cell> geography() {
    std::vector<Cell> out(1);auto& c=out[0];c.id=0;c.area_km2=1e-6;
    c.elevation_m=c.filled_elevation_m=c.hydrologic_surface_elevation_m=1;
    c.hydrologic_surface_conditioned=true;c.flow_to=-1;return out;
}
LayeredIceInput input() {
    LayeredIceInput in;in.id="new_storage_lifetime_source";
    in.complete_horizontal_coverage_declared=true;in.bottom_boundary=LayeredIceBottomBoundary::insulated;
    in.water={10,1,2,4};
    in.columns={{0,1,LayeredIceTopClosure::prescribed_nonwater_top_capacity,1,0,0,
                 {{0,1,1,1,1}},std::nullopt}};return in;
}
LayeredIceOwnerLimits limits() {
    LayeredIceOwnerLimits l;l.max_retained_preparations=2;
    l.max_receipt_bytes=1048576;l.max_history_bytes=16777216;l.max_private_receipt_bytes=2097152;
    return l;
}
LayeredIceOwnerRequest request(const std::string& name,std::uint64_t revision,Phase phase=Phase::solid) {
    LayeredIceOwnerRequest q;q.id=name;q.expected_revision=revision;q.end_seconds=0;
    q.movements={{"event_"+name,{-1,-1},{0,0},phase,1,10}};return q;
}
LayeredIceOwnerRequest thermal_request() {
    LayeredIceOwnerRequest q;q.id="thermal";q.expected_revision=2;q.end_seconds=1;
    q.forcing=LayeredIceOwnerForcing{"new_storage_thermal_window",0,1,{1}};
    EnthalpyMeshOptions o;o.duration_seconds=1;o.maximum_stage_error_j=1e-8;o.maximum_endpoint_error_j=1e-6;
    o.maximum_sweeps=16;o.maximum_coordinate_iterations=32;o.maximum_scalar_evaluations=4096;
    o.reconstruction_leaves=1;o.allow_pure_water_columns=true;q.thermal=o;q.maximum_thermal_error_increment_j=1e-6;
    return q;
}
std::vector<LayeredIceOwnerRequest> requests() {
    auto out=std::vector<LayeredIceOwnerRequest>{request("a",0),request("b",0,Phase::liquid),
        request("cap_1",0),request("cap_2",0),request("c",0),request("d",1,Phase::liquid),
        request("b",0,Phase::liquid),request("b",0,Phase::liquid),request("rich_refusal",2),
        request("e",2),request("cap_3",2),thermal_request(),thermal_request(),request("f",3)};
    out[7].movements[0].mass_kg=2;
    out[8].movements={{"event_rich_refusal",{0,0},{-1,-1},Phase::liquid,100,0}};
    out[13].end_seconds=1;
    return out;
}
template<class S> std::string storage_json(const S& s) {
    return "{\"committed_history_bytes\":"+std::to_string(s.committed_history_bytes)+
        ",\"reserved_history_bytes\":"+std::to_string(s.reserved_history_bytes)+
        ",\"private_receipt_bytes\":"+std::to_string(s.private_receipt_bytes)+
        ",\"retained_preparations\":"+std::to_string(s.retained_preparations)+
        ",\"in_flight_preparations\":"+std::to_string(s.in_flight_preparations)+'}';
}
std::string state(const LayeredIceOwner& owner) {return layered_ice_owner_snapshot_json(*owner.snapshot());}
void observe(const std::string& name,const LayeredIceOwner& owner) {
    std::cout<<"{\"kind\":\"storage\",\"name\":"<<std::quoted(name)<<",\"storage\":"
             <<storage_json(owner.storage())<<",\"current_work\":"<<layered_ice_owner_work_json(owner.work())<<"}\n";
}
void journal(const std::string& name,const LayeredIceOwner& owner) {
    const auto encoded=owner.journal_json();const auto history=owner.history();
    std::cout<<"{\"kind\":\"journal\",\"name\":"<<std::quoted(name)<<",\"journal\":"<<encoded
             <<",\"journal_bytes\":"<<encoded.size()<<",\"storage\":"<<storage_json(owner.storage())
             <<",\"current_snapshot\":"<<state(owner)<<",\"history\":[";
    bool first=true;for(const auto& receipt:history){if(!first)std::cout<<',';first=false;
        std::cout<<layered_ice_owner_receipt_json(*receipt);}
    std::cout<<"]}\n";
    check(encoded.size()==owner.storage().committed_history_bytes,name+"_journal_bytes_equal_owned_charge");
}
LayeredIceOwnerPreparation prepare(LayeredIceOwner& owner,const std::string& name,
    const LayeredIceOwnerRequest& q,const std::vector<Cell>& cells) {
    const auto before=state(owner);const auto storage_before=storage_json(owner.storage());
    ++prepares;auto result=owner.prepare(q,cells,geographic_revision);
    std::cout<<"{\"kind\":\"prepare\",\"name\":"<<std::quoted(name)<<",\"request\":"
             <<layered_ice_owner_request_json(q)<<",\"observed\":"
             <<seasonal_liquid_routing_input_json(cells,geographic_revision,{})<<",\"before\":"<<before
             <<",\"after\":"<<state(owner)<<",\"storage_before\":"<<storage_before
             <<",\"storage_after\":"<<storage_json(owner.storage())<<",\"replayed\":"
             <<(result.replayed_committed_transaction?"true":"false")<<",\"receipt\":"
             <<layered_ice_owner_receipt_json(*result.diagnostic)<<",\"current_work\":"
             <<layered_ice_owner_work_json(owner.work())<<"}\n";
    check(before==state(owner),name+"_prepare_preserves_accepted_state");
    check(owner.storage().in_flight_preparations==0,name+"_returned_without_inflight_work");return result;
}
LayeredIceOwnerCommit commit(LayeredIceOwner& owner,const std::string& name,
    const LayeredIceOwnerCandidate& candidate,const std::vector<Cell>& cells) {
    const auto before=state(owner);const auto storage_before=storage_json(owner.storage());++commits;
    const auto result=owner.commit(candidate,cells,geographic_revision);
    std::cout<<"{\"kind\":\"commit\",\"name\":"<<std::quoted(name)<<",\"transaction_id\":"
             <<std::quoted(candidate.receipt().request->id)<<",\"observed\":"
             <<seasonal_liquid_routing_input_json(cells,geographic_revision,{})<<",\"before\":"<<before
             <<",\"after\":"<<state(owner)<<",\"storage_before\":"<<storage_before
             <<",\"storage_after\":"<<storage_json(owner.storage())<<",\"accepted\":"
             <<(result.accepted?"true":"false")<<",\"replayed\":"<<(result.replayed?"true":"false")
             <<",\"failure_code\":"<<std::quoted(result.failure_code)<<"}\n";return result;
}
void cap_refusal(const LayeredIceOwnerPreparation& result,const std::string& name) {
    const auto& r=*result.diagnostic;
    check(!result.candidate && r.failure_code=="retained_preparation_cap" && !r.request && !r.initial && !r.final &&
          !r.material && !r.thermal && !r.remap && !r.absorption && !r.topology && !r.thermal_ledger &&
          !r.thermal_error_charge && r.work.prepare_attempts==1 && r.work.graph_builds_started==0 &&
          r.work.material_calls_started==0 && r.work.calorimeter_calls_started==0 && r.work.remap_calls_started==0 &&
          r.work.thermal_calls_started==0 && r.work.internal_be_calls_started==0 && r.work.scalar_evaluations==0 &&
          r.work.absorption_calls_started==0 && r.work.topology_calls_started==0 && r.work.observed_counts_complete,
          name+"_refuses_before_physics");
}
void inventory() {
    const auto q=requests();const auto l=limits();
    std::cout<<"{\"kind\":\"inventory\",\"scope\":\"new_owner_retained_payload_lifetime_controls\",\"execution\":\"none\","
             <<"\"planned_captures\":1,\"planned_constructors\":1,\"planned_prepares\":14,\"planned_commits\":6,"
             <<"\"planned_builders\":16,\"planned_material_calls\":7,\"planned_calorimeter_calls\":6,"
             <<"\"planned_thermal_calls\":1,\"planned_internal_be_calls\":2,\"maximum_scalar_evaluations\":4096,"
             <<"\"planned_checks\":72,\"planned_journal_rows\":3,"
             <<"\"calendar_calls\":0,\"world_calls\":0,\"historical_calls\":0,"
             <<"\"geography\":"<<seasonal_liquid_routing_input_json(geography(),geographic_revision,{})
             <<",\"source\":"<<layered_ice_input_json(input())<<",\"initial_E\":0.25,\"joint_budget\":1,"
             <<"\"storage_limits\":{\"max_retained_preparations\":"<<l.max_retained_preparations
             <<",\"max_receipt_bytes\":"<<l.max_receipt_bytes<<",\"max_history_bytes\":"<<l.max_history_bytes
             <<",\"max_private_receipt_bytes\":"<<l.max_private_receipt_bytes<<"},\"requests\":[";
    bool first=true;for(const auto& x:q){if(!first)std::cout<<',';first=false;std::cout<<layered_ice_owner_request_json(x);}
    std::cout<<"]}\n";
}
int run() {
    const auto cells=geography();const auto q=requests();++captures;
    const auto graph=capture_seasonal_liquid_routing_graph(cells,geographic_revision);
    LayeredIceOwnerSeed seed{"storage_owner",input(),0,.25,graph,{0},{},{},{}};
    ++constructors;auto owner=std::make_unique<LayeredIceOwner>(std::move(seed),1,limits());
    const auto original_view=owner->snapshot();const auto original_json=layered_ice_owner_snapshot_json(*original_view);
    const auto initial_storage=owner->storage();observe("constructed",*owner);
    check(initial_storage.retained_preparations==0 && initial_storage.in_flight_preparations==0 &&
          initial_storage.private_receipt_bytes==0 && initial_storage.reserved_history_bytes==0 &&
          initial_storage.committed_history_bytes>0,"construction_charges_seed_with_no_private_payload");
    journal("constructed",*owner);

    auto a=prepare(*owner,"a",q[0],cells);auto b=prepare(*owner,"b",q[1],cells);
    check(a.candidate && b.candidate,"two_private_candidates_prepared");if(!a.candidate || !b.candidate)return 1;
    const auto two=owner->storage();
    check(two.retained_preparations==2 && two.private_receipt_bytes>0 && two.reserved_history_bytes>0 &&
          two.committed_history_bytes==initial_storage.committed_history_bytes,"returned_candidates_hold_two_leases");
    auto blocked1=prepare(*owner,"cap_1",q[2],cells);cap_refusal(blocked1,"cap_1");
    check(storage_json(owner->storage())==storage_json(two),"unleased_cap_diagnostic_does_not_consume_storage");

    std::optional<LayeredIceOwnerCandidate> a_copy=*a.candidate;auto a_diagnostic=a.diagnostic;
    a.candidate.reset();a.diagnostic.reset();observe("copied_a_survives_original",*owner);
    check(storage_json(owner->storage())==storage_json(two),"copied_handles_share_one_lease");
    a_copy.reset();observe("only_a_diagnostic_survives",*owner);
    check(storage_json(owner->storage())==storage_json(two),"diagnostic_alone_keeps_private_lease");
    auto blocked2=prepare(*owner,"cap_2",q[3],cells);cap_refusal(blocked2,"cap_2");
    a_diagnostic.reset();observe("last_a_alias_released",*owner);
    check(owner->storage().retained_preparations==1 && owner->storage().private_receipt_bytes<two.private_receipt_bytes &&
          owner->storage().reserved_history_bytes<two.reserved_history_bytes,"last_alias_releases_one_private_payload");

    auto c=prepare(*owner,"c",q[4],cells);check(c.candidate.has_value(),"replacement_private_slot_reused");if(!c.candidate)return 1;
    const auto before_b=owner->storage();const auto b_receipt=layered_ice_owner_receipt_json(*b.diagnostic);
    const auto committed_b=commit(*owner,"b",*b.candidate,cells);const auto after_b=owner->storage();
    check(committed_b.accepted && !committed_b.replayed && owner->snapshot()->revision==1,
          "fresh_commit_publishes_first_liquid_import");
    check(after_b.retained_preparations==1 && before_b.private_receipt_bytes>after_b.private_receipt_bytes &&
          after_b.committed_history_bytes-before_b.committed_history_bytes==
              before_b.private_receipt_bytes-after_b.private_receipt_bytes &&
          after_b.reserved_history_bytes<before_b.reserved_history_bytes,"commit_transfers_exact_charge_once_while_handles_survive");
    const auto before_stale=state(*owner);const auto stale_storage=storage_json(owner->storage());
    const auto stale=commit(*owner,"stale_c",*c.candidate,cells);
    check(!stale.accepted && stale.failure_code=="stale_candidate" && before_stale==state(*owner) &&
          stale_storage==storage_json(owner->storage()),"stale_sibling_preserves_state_and_private_lease");

    auto d=prepare(*owner,"d",q[5],cells);check(d.candidate.has_value(),"second_revision_candidate_prepared");if(!d.candidate)return 1;
    const auto full=storage_json(owner->storage());const auto work_before_replay=owner->work();
    check(owner->storage().retained_preparations==2,"stale_sibling_and_new_candidate_fill_slots");
    auto replay=prepare(*owner,"b_replay",q[6],cells);auto replay_work=owner->work();
    check(replay.replayed_committed_transaction && !replay.candidate &&
          layered_ice_owner_receipt_json(*replay.diagnostic)==b_receipt && full==storage_json(owner->storage()),
          "exact_prepare_replay_works_with_private_slots_full");
    check(replay_work.prepare_attempts==work_before_replay.prepare_attempts+1,"replay_attempt_is_metered");
    replay_work.prepare_attempts=work_before_replay.prepare_attempts;
    check(layered_ice_owner_work_json(replay_work)==layered_ice_owner_work_json(work_before_replay),"replay_starts_no_new_physics");
    auto conflict=prepare(*owner,"b_conflict",q[7],cells);
    check(!conflict.candidate && !conflict.replayed_committed_transaction &&
          conflict.diagnostic->failure_code=="retained_preparation_cap" &&
          full==storage_json(owner->storage()),"changed_payload_is_not_replay_at_full_capacity");
    const auto replay_commit=commit(*owner,"b_replay",*b.candidate,cells);
    check(replay_commit.accepted && replay_commit.replayed && full==storage_json(owner->storage()),
          "commit_replay_does_not_transfer_charge_again");
    const auto before_d=owner->storage();const auto committed_d=commit(*owner,"d",*d.candidate,cells);
    check(committed_d.accepted && !committed_d.replayed && owner->snapshot()->revision==2 &&
          owner->storage().retained_preparations==1 && owner->storage().committed_history_bytes>before_d.committed_history_bytes,
          "second_commit_leaves_only_stale_sibling_private");
    c.candidate.reset();c.diagnostic.reset();observe("stale_c_released",*owner);
    check(owner->storage().retained_preparations==0 && owner->storage().private_receipt_bytes==0 &&
          owner->storage().reserved_history_bytes==0,"stale_last_alias_releases_remaining_private_charge");
    check(layered_ice_owner_snapshot_json(*original_view)==original_json &&
          owner->snapshot()->graph.input().columns[0].layers[0].water_mass_kg_m2==3 &&
          owner->snapshot()->consumed_event_ids.size()==2,"old_snapshot_is_immutable_and_only_committed_imports_apply");

    auto rich=prepare(*owner,"rich_refusal",q[8],cells);const auto rich_storage=owner->storage();
    check(!rich.candidate && rich.diagnostic->failure_code=="material_refusal" && rich.diagnostic->material &&
          rich.diagnostic->material->failure_code=="uncertain_liquid_inventory" &&
          rich.diagnostic->material->initial_graph && !rich.diagnostic->final,"rich_material_refusal_retains_source_witness");
    check(rich_storage.retained_preparations==1 && rich_storage.private_receipt_bytes>0 &&
          rich_storage.reserved_history_bytes==0,"rich_failure_keeps_private_charge_but_releases_journal_reservation");
    auto rich_copy=rich.diagnostic;rich.diagnostic.reset();observe("rich_copy_only",*owner);
    check(storage_json(owner->storage())==storage_json(rich_storage),"rich_diagnostic_copy_keeps_single_lease");
    auto e=prepare(*owner,"e",q[9],cells);check(e.candidate.has_value(),"fresh_candidate_can_coexist_with_rich_refusal");if(!e.candidate)return 1;
    auto blocked3=prepare(*owner,"cap_3",q[10],cells);cap_refusal(blocked3,"cap_3");
    rich_copy.reset();observe("rich_last_alias_released",*owner);
    check(owner->storage().retained_preparations==1,"rich_last_alias_releases_its_slot");
    e.candidate.reset();e.diagnostic.reset();observe("e_abandoned",*owner);
    check(owner->storage().retained_preparations==0 && owner->storage().private_receipt_bytes==0 &&
          owner->storage().reserved_history_bytes==0 && owner->snapshot()->revision==2,
          "abandoned_successful_prepare_releases_without_publication");

    auto thermal=prepare(*owner,"thermal",q[11],cells);
    check(thermal.candidate && thermal.diagnostic->thermal && thermal.diagnostic->thermal->accepted,
          "one_new_short_thermal_witness_prepared");if(!thermal.candidate)return 1;
    const auto thermal_receipt=layered_ice_owner_receipt_json(*thermal.diagnostic);
    const auto committed_thermal=commit(*owner,"thermal",*thermal.candidate,cells);
    check(committed_thermal.accepted && !committed_thermal.replayed && owner->snapshot()->revision==3 &&
          owner->snapshot()->elapsed_seconds==1 && owner->snapshot()->forcing_history.size()==1 &&
          owner->storage().retained_preparations==0 && owner->storage().private_receipt_bytes==0,
          "thermal_commit_publishes_one_forcing_and_transfers_private_lease");
    const auto thermal_storage=storage_json(owner->storage());const auto before_thermal_replay=owner->work();
    auto thermal_replay=prepare(*owner,"thermal_replay",q[12],cells);auto after_thermal_replay=owner->work();
    check(thermal_replay.replayed_committed_transaction && !thermal_replay.candidate &&
          layered_ice_owner_receipt_json(*thermal_replay.diagnostic)==thermal_receipt &&
          thermal_storage==storage_json(owner->storage()),"thermal_replay_retains_full_original_witness_without_storage_charge");
    check(after_thermal_replay.prepare_attempts==before_thermal_replay.prepare_attempts+1,"thermal_replay_attempt_is_metered");
    after_thermal_replay.prepare_attempts=before_thermal_replay.prepare_attempts;
    check(layered_ice_owner_work_json(after_thermal_replay)==layered_ice_owner_work_json(before_thermal_replay),
          "thermal_replay_starts_no_new_thermal_or_source_work");
    const auto replayed_thermal_commit=commit(*owner,"thermal_replay",*thermal.candidate,cells);
    check(replayed_thermal_commit.accepted && replayed_thermal_commit.replayed &&
          thermal_storage==storage_json(owner->storage()),"thermal_commit_replay_preserves_single_owned_charge");
    journal("after_thermal_replay",*owner);
    check(owner->history().size()==3,"journal_contains_three_fresh_commits_only");

    auto f=prepare(*owner,"f",q[13],cells);check(f.candidate.has_value(),"final_private_candidate_prepared");if(!f.candidate)return 1;
    const auto accepted_view=owner->snapshot();const auto accepted_json=layered_ice_owner_snapshot_json(*accepted_view);
    const auto f_json=layered_ice_owner_receipt_json(*f.diagnostic);const auto final_work=owner->work();
    observe("before_owner_destruction",*owner);journal("before_owner_destruction",*owner);owner.reset();
    check(layered_ice_owner_snapshot_json(*original_view)==original_json &&
          layered_ice_owner_snapshot_json(*accepted_view)==accepted_json,"snapshot_views_survive_owner_destruction");
    check(layered_ice_owner_receipt_json(f.candidate->receipt())==f_json &&
          layered_ice_owner_receipt_json(*b.diagnostic)==b_receipt &&
          layered_ice_owner_receipt_json(*thermal.diagnostic)==thermal_receipt,"private_and_committed_receipts_survive_owner_destruction");
    f.candidate.reset();f.diagnostic.reset();b.candidate.reset();b.diagnostic.reset();
    d.candidate.reset();d.diagnostic.reset();replay.diagnostic.reset();
    thermal.candidate.reset();thermal.diagnostic.reset();thermal_replay.diagnostic.reset();
    check(captures==1 && constructors==1 && prepares==14 && commits==6 && final_work.prepare_attempts==14 &&
          final_work.graph_builds_started==16 && final_work.material_calls_started==7 && final_work.calorimeter_calls_started==6 &&
          final_work.thermal_calls_started==1 && final_work.internal_be_calls_started==2 && final_work.scalar_evaluations<=4096 &&
          final_work.remap_calls_started==0 && final_work.absorption_calls_started==0 && final_work.topology_calls_started==0,
          "fixed_one_new_thermal_lifetime_envelope");
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<checks<<",\"failures\":"<<failures
             <<",\"captures\":"<<captures<<",\"constructors\":"<<constructors<<",\"prepares\":"<<prepares
             <<",\"commits\":"<<commits<<",\"work\":"<<layered_ice_owner_work_json(final_work)
             <<",\"calendar_calls\":0,\"world_calls\":0,\"historical_calls\":0}\n";return failures?1:0;
}
} // namespace
int main(int argc,char** argv) {
    std::cout.imbue(std::locale::classic());std::cout<<std::setprecision(17);
    if(argc==2 && std::string(argv[1])=="--inventory"){inventory();return 0;}
    if(argc!=2 || std::string(argv[1])!="--run")return 2;
    try{return run();}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
