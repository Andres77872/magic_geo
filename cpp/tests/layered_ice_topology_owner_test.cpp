#include "layered_ice_owner.hpp"

#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {
using namespace magic_geo::detail;
using Phase = cryosphere_prototype::Phase;
constexpr std::uint64_t epoch = 91;
int checks = 0, failures = 0;
std::string quote(const std::string& s) {std::ostringstream o;o<<std::quoted(s);return o.str();}
void check(bool ok,const std::string& name) {
    ++checks;if(!ok)++failures;
    std::cout<<"{\"kind\":\"check\",\"name\":"<<quote(name)<<",\"passed\":"<<(ok?"true":"false")<<"}\n";
}
std::vector<Cell> geography() {
    std::vector<Cell> cells(2);
    for(int i=0;i<2;++i) {
        auto& c=cells[i];c.id=i;c.area_km2=(i+1)*1e-6;c.neighbors={1-i};
        c.elevation_m=i+1;c.filled_elevation_m=c.elevation_m;
        c.hydrologic_surface_elevation_m=c.elevation_m;c.hydrologic_surface_conditioned=true;
        c.hydrologic_flow_slope=i==1?.001:0;c.flow_to=i==1?0:-1;
    }
    return cells;
}
LayeredIceInput input() {
    LayeredIceInput in;in.id="topology_owner_manufactured_v1";in.water={10,1,2,4};
    in.complete_horizontal_coverage_declared=true;in.bottom_boundary=LayeredIceBottomBoundary::insulated;
    for(int i=0;i<2;++i) {
        LayeredIceColumnInput c;c.cell_id=i;c.area_m2=i==0?2:1;
        c.top_closure=LayeredIceTopClosure::prescribed_nonwater_top_capacity;
        c.top_nonwater_heat_capacity_j_m2_k=2;c.top_longwave_emissivity=.5;
        c.top_absorbed_shortwave_w_m2=20+i;
        if(i==0)c.layers={{0,3,20,2,1},{1,1,-2,2,1},{2,2,16,2,1}};
        else {c.layers={{0,1,-2,2,1}};c.deep_inventory=LayeredIceDeepInventoryInput{4,-8,2};}
        in.columns.push_back(c);
    }
    in.horizontal_climate_edges={{0,1,.25}};return in;
}
LayeredIceOwnedParcel old_parcel() {
    LayeredMaterialParcelCertificate p;
    p.movement={"old_export",{0,7},{-1,-1},Phase::liquid,1,0};
    p.donor_temperature_k=10;p.specific_enthalpy_j_kg=4;p.carried_enthalpy_j=4;
    p.ideal_specific_enthalpy_j_kg={4,4};p.ideal_carried_enthalpy_j={4,4};p.external_outbox=true;
    return {"trusted_earlier_boundary",0,p,1};
}
LayeredIceOwnerSeed seed(const std::string& id,const std::vector<Cell>& cells) {
    return {id,input(),30,.25,capture_seasonal_liquid_routing_graph(cells,epoch),
            {1,0},{old_parcel()},{"old_export"},{}};
}
LayeredIceOwnerRequest request(const std::string& id="remove_layer_two") {
    LayeredIceOwnerRequest q;q.id=id;q.end_seconds=30;LayeredIceOwnerTopology p;p.id="complete_liquid_layer_removal";
    p.targets={{0,{{0,2,1},{1,2,1}},std::nullopt},{1,{{0,2,1}},2}};
    p.donors={{0,{false,0},{{{false,0},1}}},{0,{false,1},{{{false,1},1}}},
              {1,{false,0},{{{false,0},1}}},{1,{true,-1},{{{true,-1},1}}}};
    p.exports={{"whole_layer_two",{0,2},Phase::liquid}};q.topology=p;return q;
}
std::string state(const LayeredIceOwner& owner){return layered_ice_owner_snapshot_json(*owner.snapshot());}
void receipt(const std::string& name,const LayeredIceOwnerPreparation& p) {
    std::cout<<"{\"kind\":\"preparation\",\"name\":"<<quote(name)<<",\"receipt\":"
             <<layered_ice_owner_receipt_json(*p.diagnostic)<<"}\n";
}
void committed(const std::string& name,const LayeredIceOwnerCommit& c,const LayeredIceOwner& owner) {
    std::cout<<"{\"kind\":\"commit\",\"name\":"<<quote(name)<<",\"accepted\":"<<(c.accepted?"true":"false")
             <<",\"replayed\":"<<(c.replayed?"true":"false")<<",\"failure_code\":"<<quote(c.failure_code)
             <<",\"snapshot\":"<<state(owner)<<"}\n";
}
int run() {
    const auto cells=geography();LayeredIceOwner owner(seed("owner",cells),1),foreign(seed("foreign",cells),1);
    const auto initial=state(owner);
    auto refuse=[&](LayeredIceOwnerRequest q,const std::string& code) {
        auto p=owner.prepare(q,cells,epoch);receipt(q.id,p);
        check(!p.candidate && p.diagnostic->failure_code==code,q.id+"_refusal");
        check(state(owner)==initial,q.id+"_rollback");return p;
    };
    auto q=request("nonzero_time");q.end_seconds=31;refuse(q,"clock_refusal");
    q=request("stale_revision");q.expected_revision=1;refuse(q,"stale_revision");
    q=request("mixed_material");q.movements={{"extra",{0,0},{-1,-1},Phase::liquid,.125,0}};refuse(q,"mixed_topology");
    q=request("mixed_absorption");q.absorptions={{"trusted_earlier_boundary","old_export",{1,0}}};refuse(q,"mixed_topology");
    q=request("duplicate_export");q.topology->exports.push_back(q.topology->exports.front());refuse(q,"duplicate_event");
    q=request("consumed_export");q.topology->exports.front().id="old_export";refuse(q,"duplicate_event");
    q=request("uncertain_phase");q.topology->exports.front().phase=Phase::solid;
    auto bad=refuse(q,"topology_refusal");
    check(bad.diagnostic->topology && !bad.diagnostic->topology->accepted,"nested_phase_refusal_retained");
    q=request("missing_donor");q.topology->donors.pop_back();refuse(q,"topology_refusal");
    q=request();auto changed=cells;changed[1].flow_to=-1;
    auto stale=owner.prepare(q,changed,epoch);receipt("changed_geography",stale);
    check(!stale.candidate && stale.diagnostic->failure_code=="stale_geography","changed_geography_refused");
    auto good=owner.prepare(q,cells,epoch);receipt(q.id,good);
    check(good.candidate.has_value(),"complete_layer_candidate");
    if(!good.candidate)return 1;
    check(state(owner)==initial,"prepare_does_not_publish");
    auto sibling=owner.prepare(request("sibling_removal"),cells,epoch);receipt("sibling",sibling);
    check(sibling.candidate.has_value(),"same_base_sibling_prepared");
    const auto& r=good.candidate->receipt();const auto& f=*r.final;
    check(r.work.topology_calls_started==1 && r.work.material_calls_started==0 && r.work.calorimeter_calls_started==0 &&
          r.work.remap_calls_started==0 && r.work.absorption_calls_started==0 && r.work.thermal_calls_started==0,
          "only_topology_operator_started");
    check(f.revision==1 && f.elapsed_seconds==30,"zero_time_revision");
    check(f.graph.input().columns[0].layers.size()==2 && f.graph.nodes().size()==3,"removed_coordinate_absent");
    check(f.pending_outboxes.size()==2 && layered_ice_owned_parcel_json(f.pending_outboxes[0])==layered_ice_owned_parcel_json(old_parcel()),
          "old_historical_outbox_identical");
    const auto& parcel=f.pending_outboxes.back();
    check(parcel.source_revision==0 && parcel.geographic_cell_id==1 && parcel.parcel.movement.donor.layer_id==2 &&
          parcel.parcel.movement.mass_kg==4 && parcel.parcel.carried_enthalpy_j==32,"new_packet_mass_energy_and_historical_address");
    check(f.joint_energy_error_j>=.25 && f.joint_energy_error_j<.250000001,"inherited_joint_bound_once");
    check(f.graph.input().columns[1].deep_inventory->enthalpy_j_m2==-8,"unchanged_deep_preserved");
    auto c=foreign.commit(*good.candidate,cells,epoch);committed("foreign",c,foreign);check(c.failure_code=="foreign_candidate","cross_owner_refused");
    c=owner.commit(*good.candidate,changed,epoch);committed("stale_geography",c,owner);check(c.failure_code=="stale_geography" && state(owner)==initial,"stale_commit_rollback");
    c=owner.commit(*good.candidate,cells,epoch);committed("first",c,owner);check(c.accepted && !c.replayed,"atomic_commit");
    const auto accepted=state(owner);
    c=owner.commit(*good.candidate,cells,epoch);committed("replay_commit",c,owner);check(c.accepted && c.replayed && state(owner)==accepted,"exact_commit_replay");
    auto replay=owner.prepare(q,cells,epoch);receipt("replay_prepare",replay);
    check(replay.replayed_committed_transaction && !replay.candidate && state(owner)==accepted,"exact_prepare_replay");
    q.topology->exports[0].phase=Phase::solid;auto conflict=owner.prepare(q,cells,epoch);receipt("conflict",conflict);
    check(conflict.diagnostic->failure_code=="transaction_id_conflict","topology_operands_bind_replay");
    if(sibling.candidate){c=owner.commit(*sibling.candidate,cells,epoch);committed("stale_sibling",c,owner);check(c.failure_code=="stale_candidate","stale_sibling_refused");}
    q=request("extract_again");q.expected_revision=1;auto twice=owner.prepare(q,cells,epoch);receipt("extract_again",twice);
    check(twice.diagnostic->failure_code=="duplicate_event" && state(owner)==accepted,"consumed_export_cannot_repeat");
    LayeredIceOwnerRequest receive;receive.id="receive_removed_layer";receive.expected_revision=1;receive.end_seconds=30;
    receive.absorptions={{"remove_layer_two","whole_layer_two",{1,0}}};
    auto incoming=owner.prepare(receive,cells,epoch);receipt(receive.id,incoming);
    check(incoming.candidate.has_value(),"removed_donor_address_can_be_received");
    if(incoming.candidate) {
        c=owner.commit(*incoming.candidate,cells,epoch);committed("received",c,owner);
        check(c.accepted && owner.snapshot()->pending_outboxes.size()==1,"new_packet_consumed_once");
        const auto& layer=owner.snapshot()->graph.input().columns[1].layers[0];
        check(layer.water_mass_kg_m2==5 && layer.enthalpy_j_m2==30,"saved_mass_and_j_received");
        check(layered_ice_owned_parcel_json(owner.snapshot()->pending_outboxes[0])==layered_ice_owned_parcel_json(old_parcel()),"old_outbox_survives_receive");
    }
    LayeredIceOwnerLimits cap;cap.max_pending_outboxes=1;LayeredIceOwner capped(seed("capped",cells),1,cap);
    const auto capped_before=state(capped);auto full=capped.prepare(request(),cells,epoch);receipt("outbox_capacity",full);
    check(full.diagnostic->failure_code=="outbox_cap" && full.diagnostic->work.topology_calls_started==0 && state(capped)==capped_before,
          "complete_outbox_reservation_before_work");
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<checks<<",\"failures\":"<<failures<<"}\n";
    return failures?1:0;
}
} // namespace
int main(int argc,char** argv) {
    if(argc==2 && std::string(argv[1])=="--inventory") {
        std::cout<<"{\"kind\":\"inventory\",\"scope\":\"new_manufactured_owner_topology_controls_no_historical_inputs\",\"source\":"
                 <<layered_ice_input_json(input())<<",\"request\":"<<layered_ice_owner_request_json(request())
                 <<",\"old_parcel\":"<<layered_ice_owned_parcel_json(old_parcel())<<"}\n";return 0;
    }
    if(argc!=1 && !(argc==2 && std::string(argv[1])=="--run"))return 2;
    try{return run();}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
