#include "layered_ice_owner.hpp"

#include <algorithm>
#include <iomanip>
#include <iostream>
#include <locale>
#include <memory>
#include <numeric>
#include <string>
#include <vector>

namespace {
using namespace magic_geo::detail;
using Phase=cryosphere_prototype::Phase;
constexpr std::uint64_t geographic_revision=418;
constexpr std::size_t cells_count=64;
int checks=0,failures=0,captures=0,constructors=0,prepares=0;
void check(bool ok,const std::string& name) {
    ++checks;if(!ok)++failures;
    std::cout<<"{\"kind\":\"check\",\"name\":"<<std::quoted(name)
             <<",\"passed\":"<<(ok?"true":"false")<<"}\n";
}
LayeredIceInput input() {
    LayeredIceInput in;in.id="new_storage_budget_source";in.complete_horizontal_coverage_declared=true;
    in.bottom_boundary=LayeredIceBottomBoundary::insulated;in.water={10,1,2,4};
    for(std::size_t i=0;i<cells_count;++i)
        in.columns.push_back({static_cast<int>(i),1,LayeredIceTopClosure::prescribed_nonwater_top_capacity,
                              1,0,0,{{0,1,1,1,1}},std::nullopt});
    return in;
}
std::vector<Cell> geography() {
    std::vector<Cell> out(cells_count);
    for(std::size_t i=0;i<out.size();++i) {
        auto& c=out[i];c.id=static_cast<int>(i);c.area_km2=1e-6;
        c.elevation_m=c.filled_elevation_m=c.hydrologic_surface_elevation_m=1;
        c.hydrologic_surface_conditioned=true;c.flow_to=-1;
    }
    return out;
}
LayeredIceOwnerRequest empty_request(const std::string& id) {LayeredIceOwnerRequest q;q.id=id;return q;}
LayeredIceOwnerRequest export_request() {
    auto q=empty_request("oversized_material_diagnostic");
    q.movements={{"oversized_liquid_export",{0,0},{-1,-1},Phase::liquid,100,0}};return q;
}
LayeredIceOwnerWork work(std::uint64_t builds=0,std::uint64_t materials=0) {
    LayeredIceOwnerWork w;w.prepare_attempts=1;w.graph_builds_started=builds;w.material_calls_started=materials;return w;
}
LayeredIceOwnerReceipt stripped_receipt(const LayeredIceOwnerLimits& limits) {
    LayeredIceOwnerReceipt r;r.limits=limits;r.maximum_joint_energy_error_j=1;r.work=work(1,1);
    r.failure_code="receipt_cap";r.detail="unaccepted rich diagnostic exceeds retention; no state published";return r;
}
std::size_t empty_record_bytes(const LayeredIceOwnerLimits& limits,const LayeredIceOwnerRequest& q) {
    // Size-only substitution of the normalized initial reference avoids
    // constructing any graph or owner. This object is not an actual receipt.
    LayeredIceOwnerReceipt r;r.limits=limits;r.maximum_joint_energy_error_j=1;r.request=q;
    r.work=work();r.failure_code="empty_transition";r.detail="empty_transition: no physical transition requested";
    auto encoded=layered_ice_owner_record_json(r,layered_ice_owner_request_json(q));
    const std::string old="\"initial\":null",replacement=
        "\"initial\":{\"owner_id\":\"private_byte_owner\",\"snapshot_revision\":0}";
    const auto position=encoded.find(old);
    if(position==std::string::npos || position!=encoded.rfind(old))
        throw std::runtime_error("size-only initial reference token is not unique");
    encoded.replace(position,old.size(),replacement);return encoded.size();
}
std::size_t next_power_two(std::size_t n) {
    std::size_t p=1;while(p<n) {if(p>67108864)throw std::runtime_error("size-only fixture bound overflow");p*=2;}return p;
}
struct Plan {
    LayeredIceOwnerLimits roomy,tight,seed_refusal;
    std::size_t source_bytes=0,export_key_bytes=0,roomy_empty_a=0,roomy_empty_b=0;
    std::size_t roomy_stripped_bytes=0,tight_stripped_bytes=0,tight_full_metadata_bytes=0;
};
Plan plan() {
    Plan p;p.source_bytes=layered_ice_input_json(input()).size();
    const auto q=export_request();p.export_key_bytes=layered_ice_owner_request_json(q).size();
    LayeredIceOwnerLimits defaults;defaults.max_retained_preparations=8;
    const auto prototype=std::max({empty_record_bytes(defaults,empty_request("private_a")),
        empty_record_bytes(defaults,empty_request("private_b")),
        layered_ice_owner_record_json(stripped_receipt(defaults),{}).size(),p.export_key_bytes});
    const auto R=next_power_two(prototype);
    p.roomy=defaults;p.roomy.max_receipt_bytes=R;p.roomy.max_private_receipt_bytes=R;
    p.roomy.max_history_bytes=next_power_two(64*p.source_bytes+8*R);
    p.tight=p.roomy;p.tight.max_receipt_bytes=p.export_key_bytes;p.tight.max_private_receipt_bytes=p.export_key_bytes;
    p.seed_refusal=p.roomy;p.seed_refusal.max_receipt_bytes=1;p.seed_refusal.max_private_receipt_bytes=1;
    p.seed_refusal.max_history_bytes=p.source_bytes-1;
    p.roomy_empty_a=empty_record_bytes(p.roomy,empty_request("private_a"));
    p.roomy_empty_b=empty_record_bytes(p.roomy,empty_request("private_b"));
    p.roomy_stripped_bytes=layered_ice_owner_record_json(stripped_receipt(p.roomy),{}).size();
    p.tight_stripped_bytes=layered_ice_owner_record_json(stripped_receipt(p.tight),{}).size();
    auto minimal=stripped_receipt(p.tight);
    minimal.detail="rich payload unavailable; fixed refusal metadata only; no state published";
    p.tight_full_metadata_bytes=layered_ice_owner_receipt_json(minimal).size();
    if(!(p.source_bytes>R && p.roomy_empty_a<=R && p.roomy_empty_b<=R && p.roomy_stripped_bytes<=R &&
         p.tight_stripped_bytes>p.tight.max_receipt_bytes && p.tight_full_metadata_bytes>p.tight.max_receipt_bytes &&
         R<=67108864 && p.roomy.max_history_bytes<=134217728))
        throw std::runtime_error("fixed serializer-only budget inequalities do not hold");
    return p;
}
std::string limits_json(const LayeredIceOwnerLimits& limits) {
    auto r=stripped_receipt(limits);return layered_ice_owner_receipt_json(r);
}
template<class S> std::string storage_json(const S& s) {
    return "{\"committed_history_bytes\":"+std::to_string(s.committed_history_bytes)+
        ",\"reserved_history_bytes\":"+std::to_string(s.reserved_history_bytes)+
        ",\"private_receipt_bytes\":"+std::to_string(s.private_receipt_bytes)+
        ",\"retained_preparations\":"+std::to_string(s.retained_preparations)+
        ",\"in_flight_preparations\":"+std::to_string(s.in_flight_preparations)+'}';
}
std::string state(const LayeredIceOwner& owner) {return layered_ice_owner_snapshot_json(*owner.snapshot());}
bool no_physics(const LayeredIceOwnerWork& w,std::uint64_t attempts,std::uint64_t builds,std::uint64_t materials) {
    auto expected=work(builds,materials);expected.prepare_attempts=attempts;
    return layered_ice_owner_work_json(w)==layered_ice_owner_work_json(expected);
}
bool metadata_only(const LayeredIceOwnerReceipt& r) {
    return !r.prepared && !r.request && !r.initial && !r.final && !r.material && !r.remap && !r.thermal &&
        !r.absorption && !r.topology && !r.thermal_ledger && !r.thermal_error_charge &&
        r.initial_domain.empty() && r.final_domain.empty();
}
LayeredIceOwnerSeed seed(const std::string& id,const SeasonalLiquidRoutingGraph& graph) {
    std::vector<int> mapping(cells_count);std::iota(mapping.begin(),mapping.end(),0);
    return {id,input(),0,.25,graph,std::move(mapping),{},{},{}};
}
std::unique_ptr<LayeredIceOwner> construct(const std::string& id,const SeasonalLiquidRoutingGraph& graph,
                                        const LayeredIceOwnerLimits& limits,bool accepted) {
    ++constructors;std::unique_ptr<LayeredIceOwner> owner;std::string failure;
    try {owner=std::make_unique<LayeredIceOwner>(seed(id,graph),1,limits);}
    catch(const LayeredIceError& e) {failure=e.code;}
    std::cout<<"{\"kind\":\"constructor\",\"owner_id\":"<<std::quoted(id)
        <<",\"limits_witness\":"<<limits_json(limits)<<",\"accepted\":"<<(owner?"true":"false")
        <<",\"failure_code\":"<<std::quoted(failure)<<",\"snapshot\":"<<(owner?state(*owner):"null")
        <<",\"storage\":"<<(owner?storage_json(owner->storage()):"null")<<"}\n";
    check(accepted ? static_cast<bool>(owner) : !owner && failure=="history_cap",id+"_constructor_route");return owner;
}
LayeredIceOwnerPreparation prepare(LayeredIceOwner& owner,const std::string& name,const LayeredIceOwnerRequest& q,
                                  const std::vector<Cell>& cells) {
    const auto before=state(owner),storage_before=storage_json(owner.storage());++prepares;
    auto result=owner.prepare(q,cells,geographic_revision);
    std::cout<<"{\"kind\":\"prepare\",\"name\":"<<std::quoted(name)<<",\"request\":"
        <<layered_ice_owner_request_json(q)<<",\"before\":"<<before<<",\"after\":"<<state(owner)
        <<",\"storage_before\":"<<storage_before<<",\"storage_after\":"<<storage_json(owner.storage())
        <<",\"receipt\":"<<layered_ice_owner_receipt_json(*result.diagnostic)<<",\"current_work\":"
        <<layered_ice_owner_work_json(owner.work())<<"}\n";
    check(before==state(owner),name+"_preserves_accepted_state");
    check(owner.storage().in_flight_preparations==0,name+"_releases_inflight_work");return result;
}
void inventory() {
    const auto p=plan();
    std::cout<<"{\"kind\":\"inventory\",\"scope\":\"new_source_only_storage_budget_controls\",\"execution\":\"none\","
        <<"\"source\":"<<layered_ice_input_json(input())<<",\"geography\":"
        <<seasonal_liquid_routing_input_json(geography(),geographic_revision,{})
        <<",\"initial_E\":0.25,\"joint_budget\":1,\"roomy_limits_witness\":"<<limits_json(p.roomy)
        <<",\"tight_limits_witness\":"<<limits_json(p.tight)<<",\"seed_refusal_limits_witness\":"<<limits_json(p.seed_refusal)
        <<",\"source_bytes\":"<<p.source_bytes<<",\"export_key_bytes\":"<<p.export_key_bytes
        <<",\"roomy_empty_a_bytes\":"<<p.roomy_empty_a<<",\"roomy_empty_b_bytes\":"<<p.roomy_empty_b
        <<",\"roomy_stripped_bytes\":"<<p.roomy_stripped_bytes<<",\"tight_stripped_bytes\":"<<p.tight_stripped_bytes
        <<",\"tight_full_metadata_bytes\":"<<p.tight_full_metadata_bytes<<",\"requests\":["
        <<layered_ice_owner_request_json(empty_request("private_a"))<<','
        <<layered_ice_owner_request_json(empty_request("private_b"))<<','
        <<layered_ice_owner_request_json(empty_request("private_b"))<<','
        <<layered_ice_owner_request_json(export_request())<<','<<layered_ice_owner_request_json(export_request())
        <<"],\"planned_checks\":31,\"planned_captures\":1,\"planned_constructors\":3,\"planned_prepares\":5,\"planned_commits\":0,"
        <<"\"planned_builders\":5,\"planned_material_calls\":2,\"calorimeter_calls\":0,\"thermal_calls\":0,"
        <<"\"calendar_calls\":0,\"world_calls\":0,\"historical_calls\":0}\n";
}
int run() {
    const auto p=plan();const auto cells=geography();++captures;
    const auto graph=capture_seasonal_liquid_routing_graph(cells,geographic_revision);
    auto owner=construct("private_byte_owner",graph,p.roomy,true);if(!owner)return 1;
    const auto initial=owner->storage();
    check(initial.committed_history_bytes==owner->journal_json().size() && initial.committed_history_bytes>p.source_bytes,
          "expanded_seed_and_empty_frame_charged");
    auto a=prepare(*owner,"private_a",empty_request("private_a"),cells);
    check(!a.candidate && a.diagnostic->failure_code=="empty_transition" && a.diagnostic->initial &&
          no_physics(a.diagnostic->work,1,0,0),"small_refusal_keeps_source_reference_without_physics");
    const auto occupied=owner->storage();
    check(occupied.retained_preparations==1 && occupied.retained_preparations<p.roomy.max_retained_preparations &&
          occupied.private_receipt_bytes==p.roomy_empty_a && occupied.reserved_history_bytes==0,
          "one_small_diagnostic_charged_with_seven_free_count_slots");
    auto blocked=prepare(*owner,"private_b_blocked",empty_request("private_b"),cells);
    check(!blocked.candidate && blocked.diagnostic->failure_code=="private_receipt_cap" &&
          metadata_only(*blocked.diagnostic) && no_physics(blocked.diagnostic->work,1,0,0),
          "whole_private_byte_reservation_refuses_independently_of_count");
    check(storage_json(owner->storage())==storage_json(occupied),"private_cap_metadata_is_unleased");
    a.diagnostic.reset();
    check(owner->storage().private_receipt_bytes==0 && owner->storage().retained_preparations==0,
          "small_diagnostic_release_restores_private_capacity");
    auto b=prepare(*owner,"private_b_retry",empty_request("private_b"),cells);
    check(!b.candidate && b.diagnostic->failure_code=="empty_transition" &&
          owner->storage().private_receipt_bytes==p.roomy_empty_b,"same_request_admitted_after_private_release");
    b.diagnostic.reset();
    check(owner->storage().retained_preparations==0 && owner->storage().private_receipt_bytes==0,
          "retry_diagnostic_release_restores_empty_private_state");
    auto rich=prepare(*owner,"oversized_rich_leased_metadata",export_request(),cells);
    check(!rich.candidate && rich.diagnostic->failure_code=="receipt_cap" && metadata_only(*rich.diagnostic) &&
          rich.diagnostic->detail=="unaccepted rich diagnostic exceeds retention; no state published",
          "oversized_rich_refusal_replaced_by_fitting_fixed_metadata");
    check(no_physics(rich.diagnostic->work,1,1,1),"leased_metadata_preserves_actual_source_work");
    check(owner->storage().retained_preparations==1 && owner->storage().private_receipt_bytes==p.roomy_stripped_bytes &&
          owner->storage().reserved_history_bytes==0,"fitting_fixed_metadata_keeps_only_its_exact_private_charge");
    rich.diagnostic.reset();
    check(storage_json(owner->storage())==storage_json(initial),"stripped_metadata_release_restores_seed_only_storage");

    auto tight=construct("tiny_metadata_owner",graph,p.tight,true);if(!tight)return 1;
    const auto tight_initial=storage_json(tight->storage());
    auto exempt=prepare(*tight,"oversized_rich_exempt_metadata",export_request(),cells);
    check(!exempt.candidate && exempt.diagnostic->failure_code=="receipt_cap" && metadata_only(*exempt.diagnostic) &&
          exempt.diagnostic->detail=="rich payload unavailable; fixed refusal metadata only; no state published",
          "tiny_record_budget_returns_exempt_fixed_metadata");
    check(no_physics(exempt.diagnostic->work,1,1,1),"exempt_metadata_preserves_actual_source_work");
    check(layered_ice_owner_receipt_json(*exempt.diagnostic).size()==p.tight_full_metadata_bytes &&
          p.tight_full_metadata_bytes>p.tight.max_receipt_bytes,"exempt_metadata_is_explicitly_outside_rich_byte_cap");
    check(storage_json(tight->storage())==tight_initial,"oversized_fixed_metadata_releases_all_private_and_journal_reservations");

    const auto refused=construct("seed_history_refusal",graph,p.seed_refusal,false);
    check(!refused && p.seed_refusal.max_history_bytes<p.source_bytes,"seed_input_alone_exceeds_constructor_history_cap");
    const auto primary_work=owner->work(),tight_work=tight->work();
    check(captures==1 && constructors==3 && prepares==5 && no_physics(primary_work,4,2,1) &&
          no_physics(tight_work,1,2,1),"fixed_source_only_budget_envelope");
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<checks<<",\"failures\":"<<failures
        <<",\"captures\":"<<captures<<",\"constructors\":"<<constructors<<",\"prepares\":"<<prepares
        <<",\"commits\":0,\"primary_work\":"<<layered_ice_owner_work_json(primary_work)
        <<",\"tight_work\":"<<layered_ice_owner_work_json(tight_work)
        <<",\"refused_constructor_builds_inferred_from_source_route\":1,\"planned_total_builders\":5,"
        <<"\"thermal_calls\":0,\"calendar_calls\":0,\"world_calls\":0,\"historical_calls\":0}\n";
    return failures?1:0;
}
} // namespace
int main(int argc,char** argv) {
    std::cout.imbue(std::locale::classic());std::cout<<std::setprecision(17);
    try {
        if(argc==2 && std::string(argv[1])=="--inventory"){inventory();return 0;}
        if(argc!=2 || std::string(argv[1])!="--run")return 2;
        return run();
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 2;}
}
