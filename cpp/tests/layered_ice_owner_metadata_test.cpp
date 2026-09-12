#include "engine/layered_ice_owner_metadata.hpp"
#include "engine/enthalpy_mesh_proof_codec.hpp"

#include <algorithm>
#include <bit>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

// Newly manufactured format fixtures. Exactly one captured two-cell geography
// and one layered graph are built; every owner/component receipt is fabricated.
// No owner, calendar, thermal or material evolution is invoked.
using namespace magic_geo::detail;
namespace {
using I=EnthalpyMeshInterval;
using Shape=LayeredIceOwnerMetadataShape;
using Limits=LayeredIceOwnerMetadataLimits;
using Context=LayeredIceOwnerMetadataContext;
using Receipt=LayeredIceOwnerReceipt;
using Snapshot=LayeredIceOwnerSnapshot;
using Phase=cryosphere_prototype::Phase;
std::uint64_t checks=0,failures=0,captures=0,builders=0,encodes=0;
double next_value=1;
double value(){return next_value++;}
I interval(){const auto v=value();return {v,v+.25};}
double special(std::uint64_t bits){return std::bit_cast<double>(bits);}
std::string odd(){return std::string("quote\" slash\\ newline\n tab\t nul")+char(0)+char(0xff)+char(0x80);}
std::string quote(std::string_view value) {
    std::ostringstream out;out<<'"';
    for(unsigned char c:value) {
        if(c=='"'||c=='\\')out<<'\\'<<static_cast<char>(c);
        else if(c<32||c>126)out<<"\\u00"<<std::hex<<std::setw(2)<<std::setfill('0')<<int(c);
        else out<<static_cast<char>(c);
    }
    out<<'"';return out.str();
}
void check(const std::string& name,bool okay){
    ++checks;if(!okay)++failures;
    std::cout<<"{\"type\":\"check\",\"name\":"<<quote(name)<<",\"passed\":"<<okay<<"}\n";
}
void save(const std::filesystem::path& path,std::string_view bytes){
    if(std::filesystem::exists(path))throw std::runtime_error("output path already exists");
    std::ofstream out(path,std::ios::binary);out.write(bytes.data(),static_cast<std::streamsize>(bytes.size()));
    out.close();if(!out)throw std::runtime_error("fixture output failed");
}
std::string size_json(const LayeredIceOwnerMetadataSize& s){
    return "{\"json_bytes\":"+std::to_string(s.json_bytes)+",\"visited_vector_elements\":"+
        std::to_string(s.visited_vector_elements)+",\"visited_string_bytes\":"+std::to_string(s.visited_string_bytes)+"}";
}
Shape shape(){
    Shape s;s.max_columns=2;s.max_layers_per_column=2;s.max_nodes=3;s.max_edges=2;s.max_deep_inventories=2;
    s.max_geographic_nodes=2;s.max_neighbors_per_node=1;s.max_movements=2;s.max_pending_outboxes=2;
    s.max_consumed_event_ids=2;s.max_forcing_records=2;s.max_forcing_values_per_record=2;
    s.max_donors=2;s.max_allocations_per_donor=2;s.max_transfers=2;s.max_targets=2;
    s.max_target_layers_per_column=2;s.max_domain_coordinates=2;s.max_node_certificates=2;
    s.max_export_certificates=2;s.max_parcel_certificates=2;s.max_absorption_selections=2;
    s.max_identifier_bytes=96;s.max_diagnostic_bytes=4096;s.max_replay_key_bytes=16384;return s;
}
std::string shape_json(const Shape& s){
    std::ostringstream out;out<<'{';bool first=true;
#define FIELD(k) do { if(!first){out<<',';}first=false;out<<"\"" #k "\":"<<s.k; } while(false)
    FIELD(max_columns);FIELD(max_layers_per_column);FIELD(max_nodes);FIELD(max_edges);FIELD(max_deep_inventories);
    FIELD(max_geographic_nodes);FIELD(max_neighbors_per_node);FIELD(max_movements);FIELD(max_pending_outboxes);
    FIELD(max_consumed_event_ids);FIELD(max_forcing_records);FIELD(max_forcing_values_per_record);FIELD(max_donors);
    FIELD(max_allocations_per_donor);FIELD(max_transfers);FIELD(max_targets);FIELD(max_target_layers_per_column);
    FIELD(max_domain_coordinates);FIELD(max_node_certificates);FIELD(max_export_certificates);FIELD(max_parcel_certificates);
    FIELD(max_absorption_selections);FIELD(max_identifier_bytes);FIELD(max_diagnostic_bytes);FIELD(max_replay_key_bytes);
#undef FIELD
    out<<'}';return out.str();
}
std::string context_json(const Context& c){
    std::ostringstream out;out<<"{\"current_attempt\":"<<c.current_attempt<<",\"seed_attempt\":"<<c.seed_attempt
        <<",\"initial_head\":{\"owner_id\":"<<quote(c.initial_head.owner_id)
        <<",\"snapshot_revision\":"<<c.initial_head.snapshot_revision
        <<",\"committed_sequence\":"<<c.initial_head.committed_sequence
        <<",\"committed_attempt\":"<<c.initial_head.committed_attempt<<"},\"thermal_section\":";
    if(c.thermal_section)out<<"{\"payload_offset\":"<<c.thermal_section->payload_offset
        <<",\"frame_bytes\":"<<c.thermal_section->frame_bytes<<",\"codec_version\":"<<c.thermal_section->codec_version<<'}';
    else out<<"null";
    out<<'}';return out.str();
}
std::vector<Cell> geography(){
    std::vector<Cell> cells(2);
    for(int n=0;n<2;++n){auto& c=cells[static_cast<std::size_t>(n)];c.id=n;c.area_km2=(n+1)*1e-6;
        c.neighbors={1-n};c.elevation_m=c.filled_elevation_m=c.hydrologic_surface_elevation_m=2+n;
        c.hydrologic_surface_conditioned=true;c.flow_to=-1;}
    return cells;
}
LayeredIceInput input(){
    LayeredIceInput q;q.id="new_metadata_source";q.complete_horizontal_coverage_declared=true;
    q.bottom_boundary=LayeredIceBottomBoundary::insulated;q.water={10,2,4,100};
    q.columns={{0,2,LayeredIceTopClosure::prescribed_nonwater_top_capacity,4,.25,0,
        {{0,2,0,1000,1},{1,1,-1,900,.5}},LayeredIceDeepInventoryInput{4,-5,1000}},
        {1,1,LayeredIceTopClosure::prescribed_top_energy,3,.75,0,
        {{0,3,1,917,2}},LayeredIceDeepInventoryInput{0,0,1000}}};
    q.horizontal_climate_edges={{0,1,.125}};return q;
}
LayeredMaterialMovement movement(){
    return {odd(),{0,1},{-1,-1},Phase::liquid,special(UINT64_C(0x7ff8123456789abc)),-0.0};
}
LayeredMaterialParcelCertificate parcel(){
    LayeredMaterialParcelCertificate p;p.movement=movement();p.donor_temperature_k=value();
    p.specific_enthalpy_j_kg=special(UINT64_C(0xfff0000000000000));p.carried_enthalpy_j=-0.0;
    p.ideal_specific_enthalpy_j_kg=interval();p.ideal_carried_enthalpy_j=interval();p.energy_projection_j=interval();
    p.external_outbox=true;return p;
}
LayeredIceOwnedParcel owned(){return {odd(),17,parcel(),1};}
LayeredIceRemapTargetColumn target(){return {0,{{0,800,.25},{1,900,.75}},917};}
LayeredIceRemapDonor donor(){return {0,{false,1},{{{false,0},3},{{true,-1},5}}};}
LayeredIceRemapDecomposition decomposition(){
    LayeredIceRemapDecomposition d;d.cell_id=0;d.source={true,-1};
#define F(k) d.k=value()
    F(initial_water_mass_kg_m2);F(initial_complete_enthalpy_j_m2);F(nonwater_capacity_j_m2_k);
    F(represented_water_enthalpy_j_m2);F(represented_stationary_nonwater_enthalpy_j_m2);
#undef F
    d.ideal_water_enthalpy_j_m2=interval();d.ideal_stationary_nonwater_enthalpy_j_m2=interval();return d;
}
LayeredIceRemapTransfer transfer(){
    LayeredIceRemapTransfer t;t.cell_id=1;t.source={false,0};t.destination={true,-1};t.weight=3;t.total_weight=7;
    t.represented_fraction=value();t.ideal_fraction=interval();t.represented_water_mass_kg_m2=value();
    t.represented_water_enthalpy_j_m2=value();t.ideal_water_mass_kg_m2=interval();t.ideal_water_enthalpy_j_m2=interval();return t;
}
LayeredIceRemapProjection projection(){
    LayeredIceRemapProjection p;p.cell_id=1;p.destination={true,-1};p.represented_water_mass_kg_m2=value();
    p.represented_complete_enthalpy_j_m2=value();p.ideal_water_mass_kg_m2=interval();p.ideal_complete_enthalpy_j_m2=interval();
    p.mass_projection_difference_kg_m2=interval();p.enthalpy_projection_difference_j_m2=interval();p.exact_identity_used=true;return p;
}
LayeredIceTopologyDomain domain(){
    LayeredIceTopologyDomain d;d.address={1,-1};d.area_m2=value();d.water_mass_kg_m2=value();d.enthalpy_j_m2=value();
    d.nonwater_capacity_j_m2_k=value();d.global_energy_error_j=value();d.enthalpy_ball_j_m2=interval();
    d.physical_floor_j_m2=interval();d.constrained_empty_deep=true;d.proved=true;return d;
}
LayeredIceOwnerRequest request(){
    LayeredIceOwnerRequest q;q.id=odd();q.expected_revision=0;q.end_seconds=-0.0;q.movements={movement()};
    q.remap=LayeredIceOwnerRemap{odd(),{target()},{donor()},{}};
    q.forcing=LayeredIceOwnerForcing{odd(),-0.0,1,{1.2345678901234567,special(UINT64_C(0x7ff0000000000000))}};
    EnthalpyMeshOptions o;o.duration_seconds=-0.0;o.maximum_stage_error_j=special(UINT64_C(0x7ff8123456789abc));
    o.maximum_endpoint_error_j=std::numeric_limits<double>::denorm_min();o.maximum_sweeps=-7;
    o.maximum_coordinate_iterations=13;o.maximum_scalar_evaluations=UINT64_MAX;o.reconstruction_leaves=5;
    o.allow_pure_water_columns=true;q.thermal=o;q.absorptions={{odd(),odd(),{1,-1}}};
    q.topology=LayeredIceOwnerTopology{odd(),{target()},{donor()},{{odd(),{1,-1},Phase::solid}},{}};
    q.maximum_thermal_error_increment_j=special(UINT64_C(0xfff8123456789abc));return q;
}
Receipt complete(const std::shared_ptr<const Snapshot>& initial,const LayeredIceGraph& graph){
    Receipt r;r.prepared=true;r.failure_code=odd();r.detail=std::string(4096,char(0xff));r.request=request();r.initial=initial;
    auto last=std::make_shared<Snapshot>(*initial);last->revision=1;last->elapsed_seconds=1;
    last->joint_energy_error_j=value();last->forcing_history=initial->forcing_history.appended({odd(),0,1,{-0.0,7}});
    last->pending_outboxes={owned()};last->consumed_event_ids={odd(),"second"};r.final=last;
    r.maximum_joint_energy_error_j=special(UINT64_C(0x7ff0000000000000));
    LayeredMaterialReceipt m;m.accepted=true;m.failure_code=odd();m.detail=r.detail;
    m.graph_builds_started=2;m.mass_calls_started=3;m.request=LayeredMaterialRequest{graph.input(),value(),value(),{movement()}};
    m.initial_graph=graph;m.final_graph=graph;LayeredMaterialNodeCertificate n;n.address={1,-1};
#define F(k) n.k=value()
    F(area_m2);F(nonwater_capacity_j_m2_k);F(initial_W);F(initial_H);F(final_W);F(final_H);
#undef F
#define F(k) n.k=interval()
    F(before_H);F(before_floor);F(after_H);F(after_floor);F(gross_solid_kg);F(gross_liquid_kg);
    F(ideal_final_W);F(ideal_final_H);F(mass_projection_kg_m2);F(energy_projection_j_m2);
#undef F
    n.initial_H=-0.0;n.after_H={special(UINT64_C(0xfff8123456789abc)),special(UINT64_C(0x7ff0000000000000))};
    m.nodes={n};m.parcels={parcel()};m.retained_energy_defect_upper_j=value();m.outbox_energy_defect_upper_j=value();
    m.joint_final_energy_error_upper_j=value();
#define F(k) m.k=interval()
    F(retained_mass_change_kg);F(external_net_mass_kg);F(mass_balance_residual_kg);
    F(retained_energy_change_j);F(external_net_energy_j);F(energy_balance_residual_j);
#undef F
    m.gross_initial_phase_inventory_proved=true;m.joint_nonexpansion_proved=true;r.material=m;
    LayeredIceRemapReceipt rem;rem.accepted=true;rem.failure_code=odd();rem.detail=r.detail;
    rem.request=LayeredIceRemapRequest{odd(),graph.input(),value(),value(),{target()},{donor()},{}};
    rem.work={1,2,3,4,5,6};rem.source_graph=graph;
    rem.final=LayeredIceRemapFinal{graph,value(),value(),interval(),interval(),{decomposition()},{transfer()},{projection()}};r.remap=rem;
    LayeredIceTopologyReceipt top;top.accepted=true;top.failure_code=odd();top.detail=r.detail;
    top.request=LayeredIceTopologyRequest{odd(),graph.input(),value(),value(),{target()},{donor()},{{odd(),{0,1},Phase::solid}},{}};
    top.work={1,2,3,4,5,6,7};top.source_graph=graph;top.source_domain={domain()};top.final_domain={domain()};
    top.decompositions={decomposition()};top.transfers={transfer()};top.projections={projection()};
    LayeredIceTopologyExportCertificate e;e.selection={odd(),{0,1},Phase::liquid};
#define F(k) e.k=value()
    F(source_area_m2);F(source_water_mass_kg_m2);F(source_complete_enthalpy_j_m2);F(source_nonwater_capacity_j_m2_k);F(represented_full_mass_kg);
#undef F
    e.exact_full_mass_kg=interval();e.source_complete_energy_ball_j=interval();e.full_latent_energy_j=interval();
    e.exact_mass_representable=true;e.whole_phase_proved=true;e.parcel=parcel();top.export_certificates={e};
    top.retained_energy_defect_upper_j=value();top.outbox_energy_defect_upper_j=value();top.final_global_energy_error_j=value();
#define F(k) top.k=interval()
    F(retained_mass_change_kg);F(exported_mass_kg);F(mass_balance_residual_kg);F(retained_energy_change_j);F(exported_energy_j);F(energy_balance_residual_j);
#undef F
    top.final=LayeredIceTopologyFinal{graph,{parcel()},value(),value(),value()};r.topology=top;
    LayeredIceAbsorptionReceipt a;a.accepted=true;a.failure_code=odd();a.detail=r.detail;
    a.request=LayeredIceAbsorptionRequest{graph.input(),{owned()},{{odd(),odd(),{1,-1}}},value(),value()};
    a.source_graph=graph;a.final=LayeredIceAbsorptionResult{graph,{owned()},value()};
    LayeredIceAbsorptionNode an;an.address={1,-1};
#define F(k) an.k=value()
    F(area_m2);F(nonwater_capacity_j_m2_k);F(initial_W);F(initial_H);F(final_W);F(final_H);
#undef F
#define F(k) an.k=interval()
    F(absorbed_mass_kg);F(absorbed_energy_j);F(ideal_final_W);F(ideal_final_H);F(mass_projection_kg_m2);F(energy_projection_j_m2);
    F(before_H);F(before_floor);F(after_H);F(after_floor);
#undef F
    a.nodes={an};a.work={1,2,3,4};a.energy_projection_defect_upper_j=value();
#define F(k) a.k=interval()
    F(absorbed_mass_kg);F(absorbed_energy_j);F(retained_mass_change_kg);F(retained_energy_change_j);F(mass_balance_residual_kg);F(energy_balance_residual_j);
#undef F
    r.absorption=a;r.thermal=EnthalpyMeshSdirk2Receipt{};
    LayeredIceOwnerThermalLedger l;
#define F(k) l.k=interval()
    F(storage_change_j);F(weighted_shortwave_j);F(weighted_emission_j);F(physical_duration_shortwave_j);
    F(shortwave_duration_bridge_j);F(balance_residual_j);F(assembled_defect_j);
#undef F
    l.weighted_edge_transfer_j={interval(),interval()};l.first_field_conversion_defect_j_m2={interval(),interval(),interval()};r.thermal_ledger=l;
    r.thermal_error_charge=LayeredIceOwnerThermalErrorCharge{value(),value(),value(),interval(),value(),true};
    r.initial_domain={{{0,0},interval(),interval()}};r.final_domain={{{1,-1},interval(),interval()}};
    r.work={1,2,3,4,5,6,7,8,9,10,false};return r;
}

struct Streamed {std::string bytes;std::size_t calls=0,largest=0;};
template<class F>Streamed collect(F action){
    Streamed out;action([&](std::span<const std::byte> bytes){++out.calls;out.largest=std::max(out.largest,bytes.size());
        if(out.bytes.size()+bytes.size()>8388608)throw std::runtime_error("test collector cap");
        out.bytes.append(reinterpret_cast<const char*>(bytes.data()),bytes.size());});return out;
}
const std::vector<std::pair<std::string,std::string>>& errors(){
    static const std::vector<std::pair<std::string,std::string>> list={
        {"record_byte_cap","metadata_cap"},{"diagnostic_cap","metadata_cap"},{"node_shape_cap","metadata_cap"},
        {"key_cap","metadata_cap"},{"target_layer_cap","metadata_cap"},{"reference_owner","metadata_reference"},
        {"reference_revision","metadata_reference"},{"reference_thermal_absence","metadata_reference"},
        {"reference_thermal_overflow","metadata_reference"},{"reference_final_prefix","metadata_reference"},
        {"reference_attempt","metadata_reference"},{"symbolic_string_overflow","metadata_overflow"},
        {"symbolic_vector_overflow","metadata_overflow"},{"seed_byte_cap","metadata_cap"},
        {"request_byte_cap","metadata_cap"},{"request_movement_cap","metadata_cap"}};return list;
}
std::vector<std::string> check_names(){
    std::vector<std::string> out={"seed.exact_legacy","seed.maximum_bound"};
    for(const std::string name:{"complete","partial_refusal","empty_refusal"}){
        if(name=="complete")out.push_back(name+".thermal_frame_bytes");
        out.push_back(name+".exact_size");out.push_back(name+".bounded_stream");out.push_back(name+".maximum_bound");
        if(name!="empty_refusal"){
            out.push_back(name+".exact_request_key");out.push_back(name+".request_maximum_bound");
        }
    }
    for(const auto& [name,code]:errors()){
        (void)code;out.push_back(name+".typed");out.push_back(name+".before_sink");
    }
    out.push_back("fixed_physical_call_counts");return out;
}
template<class F>void rejected(const std::string& name,const std::string& expected,F action){
    std::size_t calls=0;std::string code="no_exception";
    try{action([&](std::span<const std::byte>){++calls;});}
    catch(const LayeredIceOwnerMetadataError& e){code=e.code;}
    std::cout<<"{\"type\":\"error\",\"name\":"<<quote(name)<<",\"code\":"<<quote(code)
        <<",\"expected_code\":"<<quote(expected)<<",\"sink_calls\":"<<calls<<"}\n";
    check(name+".typed",code==expected);check(name+".before_sink",calls==0);
}
void plan(const char* mode){
    std::cout<<"{\"type\":\"plan\",\"schema\":\"owner_metadata_qualification_v1\",\"mode\":"<<quote(mode)
        <<",\"fabricated_receipts\":true,\"physical_acceptance_claim\":false,\"shape\":"<<shape_json(shape())
        <<",\"maximum_json_bytes\":8388608,\"planned_routing_captures\":1,\"planned_graph_builds\":1,"
        "\"planned_thermal_codec_encodes\":1,\"planned_physical_evolution_calls\":0}\n";
}
void fixture(const std::string& name,const Receipt& r,Context c,const Limits& limits,const std::filesystem::path& dir){
    const auto key=r.request?layered_ice_owner_request_json(*r.request):std::string{};
    std::string thermal;
    if(r.thermal){
        EnthalpyMeshProofCodecLimits codec;const auto count=enthalpy_mesh_proof_codec_size(*r.thermal,codec);
        c.thermal_section=LayeredIceOwnerThermalSection{64,count.frame_bytes,1};++encodes;
        thermal=collect([&](const auto& sink){encode_enthalpy_mesh_proof(*r.thermal,sink,codec);}).bytes;
        save(dir/(name+".thermal.bin"),thermal);check(name+".thermal_frame_bytes",thermal.size()==count.frame_bytes);
    }
    const auto size=layered_ice_owner_metadata_size(r,key,c,limits);
    const auto output=collect([&](const auto& sink){stream_layered_ice_owner_metadata(r,key,c,sink,limits);});
    const auto legacy=layered_ice_owner_record_json(r,key);save(dir/(name+".legacy-record.json"),legacy);
    save(dir/(name+".metadata.json"),output.bytes);
    check(name+".exact_size",output.bytes.size()==size.json_bytes);
    check(name+".bounded_stream",output.calls>0&&output.largest<=65536&&(name!="complete"||output.calls>1));
    check(name+".maximum_bound",size.json_bytes<=layered_ice_owner_metadata_max_size(limits.shape).json_bytes);
    std::cout<<"{\"type\":\"fixture\",\"name\":"<<quote(name)<<",\"context\":"<<context_json(c)
        <<",\"metadata_size\":"<<size_json(size)<<",\"legacy_record_bytes\":"<<legacy.size()
        <<",\"stream_calls\":"<<output.calls<<",\"maximum_span_bytes\":"<<output.largest
        <<",\"thermal_bytes\":"<<thermal.size()<<",\"request_size\":";
    if(r.request){
        const auto qsize=layered_ice_owner_metadata_request_size(*r.request,limits);
        const auto qout=collect([&](const auto& sink){stream_layered_ice_owner_metadata_request(*r.request,sink,limits);});
        save(dir/(name+".legacy-request.json"),key);save(dir/(name+".request.json"),qout.bytes);
        std::cout<<size_json(qsize)<<"}\n";
        check(name+".exact_request_key",qout.bytes==key&&qout.bytes.size()==qsize.json_bytes);
        check(name+".request_maximum_bound",qsize.json_bytes<=layered_ice_owner_metadata_request_max_size(limits.shape).json_bytes);
    }else std::cout<<"null}\n";
}

int run(const std::filesystem::path& dir){
    if(!std::filesystem::create_directory(dir))throw std::runtime_error("new exclusive output directory required");
    plan("run");const Limits limits{shape(),8388608};const auto cells=geography();++captures;
    const auto route=capture_seasonal_liquid_routing_graph(cells,739,{});++builders;const auto graph=build_layered_ice_graph(input());
    auto seed=std::make_shared<Snapshot>(Snapshot{odd(),0,-0.0,0,graph,route,{1,0},{owned()},{odd()},
        LayeredIceForcingHistory(std::vector<LayeredIceOwnerForcing>{{odd(),-1,0,{2,3}}})});
    const auto ssize=layered_ice_owner_metadata_seed_size(*seed,limits);
    const auto sout=collect([&](const auto& sink){stream_layered_ice_owner_metadata_seed(*seed,sink,limits);});
    const auto slegacy=layered_ice_owner_journal_seed_json(*seed);save(dir/"seed.legacy.json",slegacy);save(dir/"seed.metadata.json",sout.bytes);
    check("seed.exact_legacy",sout.bytes==slegacy&&sout.bytes.size()==ssize.json_bytes);
    check("seed.maximum_bound",ssize.json_bytes<=layered_ice_owner_metadata_seed_max_size(limits.shape).json_bytes);
    std::cout<<"{\"type\":\"seed\",\"metadata_size\":"<<size_json(ssize)<<",\"legacy_bytes\":"<<slegacy.size()
        <<",\"stream_calls\":"<<sout.calls<<",\"maximum_span_bytes\":"<<sout.largest<<"}\n";
    auto full=complete(seed,graph);Context context{2,1,{seed->owner_id,0,0,0},LayeredIceOwnerThermalSection{64,160,1}};
    fixture("complete",full,context,limits,dir);
    auto partial=full;partial.prepared=false;partial.failure_code="manufactured_refusal";partial.final.reset();
    partial.thermal.reset();partial.thermal_ledger.reset();partial.thermal_error_charge.reset();partial.remap.reset();
    partial.topology.reset();partial.absorption.reset();partial.final_domain.clear();partial.material->accepted=false;
    partial.material->final_graph.reset();Context partial_context=context;partial_context.current_attempt=3;partial_context.thermal_section.reset();
    fixture("partial_refusal",partial,partial_context,limits,dir);
    Receipt empty;empty.failure_code=odd();empty.detail="manufactured no-prefix refusal";empty.work.observed_counts_complete=false;
    Context empty_context=partial_context;empty_context.current_attempt=4;fixture("empty_refusal",empty,empty_context,limits,dir);
    const auto key=layered_ice_owner_request_json(*full.request);
    const auto full_size=layered_ice_owner_metadata_size(full,key,context,limits);
    const auto qsize=layered_ice_owner_metadata_request_size(*full.request,limits);
    for(const auto& [name,code]:errors())rejected(name,code,[&](const auto& sink){
        auto l=limits;auto c=context;auto r=full;
        if(name=="record_byte_cap")l.maximum_json_bytes=full_size.json_bytes-1;
        if(name=="diagnostic_cap")l.shape.max_diagnostic_bytes=4095;
        if(name=="node_shape_cap")l.shape.max_nodes=2;
        if(name=="key_cap")l.shape.max_replay_key_bytes=key.size()-1;
        if(name=="target_layer_cap")l.shape.max_target_layers_per_column=0;
        if(name=="reference_owner")c.initial_head.owner_id="different_owner";
        if(name=="reference_revision")c.initial_head.snapshot_revision=1;
        if(name=="reference_thermal_absence")c.thermal_section.reset();
        if(name=="reference_thermal_overflow")c.thermal_section->payload_offset=UINT64_MAX;
        if(name=="reference_final_prefix"){
            auto wrong=std::make_shared<Snapshot>(*r.final);wrong->geographic_cell_ids={0,1};r.final=wrong;
        }
        if(name=="reference_attempt")c.current_attempt=0;
        if(name=="symbolic_string_overflow"){
            l.shape.max_identifier_bytes=UINT64_MAX;(void)layered_ice_owner_metadata_max_size(l.shape);return;
        }
        if(name=="symbolic_vector_overflow"){
            l.shape.max_columns=UINT64_MAX;(void)layered_ice_owner_metadata_max_size(l.shape);return;
        }
        if(name=="seed_byte_cap"){
            l.maximum_json_bytes=ssize.json_bytes-1;stream_layered_ice_owner_metadata_seed(*seed,sink,l);return;
        }
        if(name=="request_byte_cap"){
            l.maximum_json_bytes=qsize.json_bytes-1;stream_layered_ice_owner_metadata_request(*full.request,sink,l);return;
        }
        if(name=="request_movement_cap"){
            l.shape.max_movements=0;stream_layered_ice_owner_metadata_request(*full.request,sink,l);return;
        }
        stream_layered_ice_owner_metadata(r,key,c,sink,l);
    });
    std::cout<<"{\"type\":\"max_size\",\"shape\":"<<shape_json(limits.shape)
        <<",\"record\":"<<size_json(layered_ice_owner_metadata_max_size(limits.shape))
        <<",\"request\":"<<size_json(layered_ice_owner_metadata_request_max_size(limits.shape))
        <<",\"seed\":"<<size_json(layered_ice_owner_metadata_seed_max_size(limits.shape))<<"}\n";
    check("fixed_physical_call_counts",captures==1&&builders==1&&encodes==1&&checks==48);
    std::cout<<"{\"type\":\"summary\",\"checks\":"<<checks<<",\"failures\":"<<failures
        <<",\"fixtures\":3,\"typed_errors\":16,\"routing_captures\":"<<captures<<",\"graph_builds\":"<<builders
        <<",\"thermal_codec_encodes\":"<<encodes<<",\"owner_calls\":0,\"physical_evolution_calls\":0}\n";
    return failures?1:0;
}
void inventory(){
    plan("inventory");std::cout<<"{\"type\":\"inventory\",\"fixtures\":[\"complete\",\"partial_refusal\",\"empty_refusal\"],\"errors\":[";
    bool first=true;for(const auto& [name,code]:errors()){
        if(!first)std::cout<<',';
        first=false;std::cout<<"{\"name\":"<<quote(name)<<",\"code\":"<<quote(code)<<'}';
    }
    std::cout<<"],\"check_names\":[";first=true;
    for(const auto& name:check_names()){
        if(!first)std::cout<<',';
        first=false;std::cout<<quote(name);
    }
    const auto owner=odd();Context c{2,1,{owner,0,0,0},LayeredIceOwnerThermalSection{64,160,1}};
    std::cout<<"],\"fixture_contexts\":{\"complete\":"<<context_json(c);
    c.current_attempt=3;c.thermal_section.reset();std::cout<<",\"partial_refusal\":"<<context_json(c);
    c.current_attempt=4;std::cout<<",\"empty_refusal\":"<<context_json(c);
    std::cout<<"},\"production_calls\":0,\"physical_calls\":0,\"planned_checks\":49,\"planned_files\":["
        "\"seed.legacy.json\",\"seed.metadata.json\",\"complete.legacy-record.json\",\"complete.metadata.json\","
        "\"complete.legacy-request.json\",\"complete.request.json\",\"complete.thermal.bin\","
        "\"partial_refusal.legacy-record.json\",\"partial_refusal.metadata.json\","
        "\"partial_refusal.legacy-request.json\",\"partial_refusal.request.json\","
        "\"empty_refusal.legacy-record.json\",\"empty_refusal.metadata.json\"]}\n";
}
} // namespace
int main(int argc,char** argv){
    std::cout<<std::boolalpha;
    try{
        if(argc==2&&std::string_view(argv[1])=="--inventory"){inventory();return 0;}
        if(argc==3&&std::string_view(argv[1])=="--run")return run(argv[2]);
        return 2;
    }catch(const std::exception& e){std::cout<<"{\"type\":\"fatal\",\"detail\":"<<quote(e.what())<<"}\n";return 1;}
}
