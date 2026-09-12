#include "layered_ice_owner_kernel.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <limits>
#include <set>
#include <utility>

namespace magic_geo::detail::layered_ice_owner_kernel {
namespace {
namespace b=phase_segment_prototype::bounds;
void need(bool ok,const char* code,const char* detail) {
    if(!ok) throw LayeredIceError(code,detail);
}
bool same(double x,double y) {return std::bit_cast<std::uint64_t>(x)==std::bit_cast<std::uint64_t>(y);}
void id(const std::string& x) {
    need(!x.empty() && x.size()<=96,"invalid_identifier","identifier length");
    for(unsigned char c:x) need(c>=33 && c<=126,"invalid_identifier","visible ASCII identifier required");
}
template<class Plan>
void plan_shape(const Plan& r,const LayeredIceOwnerLimits& l) {
    id(r.id);
    need(r.targets.size()<=l.max_thermal_nodes && r.donors.size()<=2*l.max_thermal_nodes,
         "remap_cap","remap retention cap");
    std::size_t targets=0,allocations=0;
    for(const auto& c:r.targets) {
        need(c.layers.size()<=32,"remap_cap","layer retention cap");targets+=c.layers.size();
    }
    for(const auto& d:r.donors) {
        need(d.allocations.size()<=l.max_node_leaves-allocations,"remap_cap","allocation retention cap");
        allocations+=d.allocations.size();
    }
    need(targets<=l.max_thermal_nodes,"remap_cap","active target cap");
}
void graph_limits(const LayeredIceGraph& g,const LayeredIceOwnerLimits& l) {
    need(g.nodes().size()<=l.max_thermal_nodes &&
         g.vertical_edges().size()+g.input().horizontal_climate_edges.size()<=l.max_thermal_edges,
         "graph_cap","owned graph exceeds thermal reservation");
}
double exact_duration(double start,double end) {
    need(std::isfinite(start) && std::isfinite(end) && start>=0 && end>start,"clock_refusal","invalid thermal clock");
    const double h=end-start,sum=start+h,bp=sum-start;
    need(std::isfinite(h) && h>0 && same(sum,end) && (start-(sum-bp))+(h-bp)==0,
         "clock_refusal","duration does not close exact clock");
    return h;
}
bool same_forcing(const LayeredIceOwnerForcing& a,const LayeredIceOwnerForcing& c) {
    if(a.id!=c.id || !same(a.begin_seconds,c.begin_seconds) || !same(a.end_seconds,c.end_seconds) ||
       a.absorbed_shortwave_w_m2.size()!=c.absorbed_shortwave_w_m2.size()) return false;
    for(std::size_t i=0;i<a.absorbed_shortwave_w_m2.size();++i)
        if(!same(a.absorbed_shortwave_w_m2[i],c.absorbed_shortwave_w_m2[i])) return false;
    return true;
}
} // namespace

void validate_limits(const LayeredIceOwnerLimits& x) {
    LayeredIceOwnerLimits cap;
    cap.max_prepare_attempts=4096;cap.max_commits=2048;cap.max_stored_forcing_values=2097152;
    cap.max_retained_preparations=4096;
#define LIMIT(n) need(x.n>0 && x.n<=cap.n,"invalid_limits",#n)
    LIMIT(max_prepare_attempts);LIMIT(max_commits);LIMIT(max_concurrent_preparations);
    LIMIT(max_events_per_transition);LIMIT(max_consumed_events);LIMIT(max_pending_outboxes);
    LIMIT(max_thermal_nodes);LIMIT(max_thermal_edges);LIMIT(max_node_leaves);
    LIMIT(max_receipt_bytes);LIMIT(max_history_bytes);
    LIMIT(max_private_receipt_bytes);LIMIT(max_retained_preparations);
    LIMIT(max_stored_forcing_values);
#undef LIMIT
    need(x.max_receipt_bytes<=x.max_history_bytes,"invalid_limits","receipt exceeds history allowance");
    need(x.max_receipt_bytes<=x.max_private_receipt_bytes,"invalid_limits","receipt exceeds private allowance");
}

void validate_request_shape(const LayeredIceOwnerRequest& q,const LayeredIceOwnerLimits& l) {
    id(q.id);
    need(q.movements.size()<=l.max_events_per_transition,"event_cap","movement retention cap");
    for(const auto& m:q.movements) id(m.id);
    need(q.absorptions.size()<=l.max_events_per_transition,"event_cap","absorption retention cap");
    for(const auto& s:q.absorptions) {id(s.transaction_id);id(s.event_id);}
    if(q.forcing) {
        id(q.forcing->id);
        need(q.forcing->absorbed_shortwave_w_m2.size()<=l.max_thermal_nodes,"forcing_refusal","forcing retention cap");
    }
    if(q.remap) plan_shape(*q.remap,l);
    if(q.topology) {
        plan_shape(*q.topology,l);
        need(q.topology->exports.size()<=l.max_events_per_transition,"event_cap","whole export retention cap");
        for(const auto& e:q.topology->exports) id(e.id);
    }
}

std::vector<LayeredIceOwnerDomainCoordinate> graph_domain(const LayeredIceGraph& g,double E) {
    need(std::isfinite(E) && E>=0,"domain_refusal","invalid joint error");
    std::vector<LayeredIceOwnerDomainCoordinate> out;
    const auto& water=g.input().water;
    for(const auto& c:g.input().columns) {
        const double radius=b::div(b::point(E),b::point(c.area_m2)).upper;
        const auto add=[&](int layer,double W,double H,double C) {
            const auto box=b::add(b::point(H),{-radius,radius});
            const auto floor=b::neg(b::mul(b::add(b::point(C),b::mul(b::point(W),
                b::point(water.solid_heat_capacity_j_kg_k))),b::point(water.freezing_temperature_k)));
            out.push_back({{c.cell_id,layer},box,floor});
            need(box.lower>=floor.upper,"uncertain_physical_domain","whole joint ball crosses an active or deep floor");
        };
        for(const auto& layer:c.layers)
            add(layer.layer_id,layer.water_mass_kg_m2,layer.enthalpy_j_m2,
                layer.layer_id==0?c.top_nonwater_heat_capacity_j_m2_k:0);
        if(c.deep_inventory && c.deep_inventory->water_mass_kg_m2>0)
            add(-1,c.deep_inventory->water_mass_kg_m2,c.deep_inventory->enthalpy_j_m2,0);
    }
    return out;
}

bool geographic_matches(const LayeredIceOwnerSnapshot& snapshot,
    const std::vector<Cell>& geography,std::uint64_t geographic_revision) {
    return snapshot.geographic_epoch.revision()==geographic_revision && snapshot.geographic_epoch.matches(geography);
}

std::shared_ptr<const LayeredIceOwnerSnapshot> initialize_snapshot(
    LayeredIceOwnerSeed seed,double budget,const LayeredIceOwnerLimits& limits) {
    id(seed.owner_id);validate_limits(limits);
    need(std::isfinite(seed.elapsed_seconds) && seed.elapsed_seconds>=0 &&
         std::isfinite(budget) && budget>=0 && std::isfinite(seed.joint_energy_error_j) &&
         seed.joint_energy_error_j>=0 && seed.joint_energy_error_j<=budget,"invalid_seed","clock or error allowance");
    need(seed.forcing_history.size()<=limits.max_commits,"invalid_seed","retained seed forcing count cap");
    std::size_t stored_forcing_values=0;
    for(const auto& f:seed.forcing_history) {
        need(f.absorbed_shortwave_w_m2.size()<=limits.max_stored_forcing_values-stored_forcing_values,
             "forcing_capacity_refusal","seed forcing values exceed owned storage cap");
        stored_forcing_values+=f.absorbed_shortwave_w_m2.size();
    }
    auto graph=build_layered_ice_graph(seed.input);graph_limits(graph,limits);(void)graph_domain(graph,seed.joint_energy_error_j);
    const auto& nodes=seed.geographic_epoch.nodes();
    need(seed.geographic_cell_ids.size()==nodes.size() && seed.input.columns.size()==nodes.size(),
         "geographic_mapping_refusal","complete geographic-to-column mapping required");
    std::set<int> mapped;
    for(std::size_t i=0;i<seed.geographic_cell_ids.size();++i) {
        const int cell=seed.geographic_cell_ids[i];
        need(cell>=0 && static_cast<std::size_t>(cell)<nodes.size() && mapped.insert(cell).second,
             "geographic_mapping_refusal","invalid or duplicate geographic cell");
        need(same(seed.input.columns[i].area_m2,nodes[cell].area_m2),
             "geographic_mapping_refusal","thermal and geographic canonical footprints differ");
    }
    for(const auto& e:seed.input.horizontal_climate_edges) {
        const auto& a=nodes[seed.geographic_cell_ids[e.first_cell]];
        const int other=seed.geographic_cell_ids[e.second_cell];
        need(std::find(a.neighbors.begin(),a.neighbors.end(),other)!=a.neighbors.end(),
             "geographic_mapping_refusal","horizontal heat edge is not a geographic adjacency");
    }
    need(seed.pending_outboxes.size()<=limits.max_pending_outboxes && seed.consumed_event_ids.size()<=limits.max_consumed_events &&
         seed.forcing_history.size()<=limits.max_commits,"invalid_seed","retained seed history cap");
    std::set<std::string> consumed,exported,forcing_ids;
    for(const auto& event:seed.consumed_event_ids) {id(event);need(consumed.insert(event).second,"invalid_seed","duplicate seed event");}
    for(const auto& box:seed.pending_outboxes) {
        id(box.transaction_id);id(box.parcel.movement.id);
        const auto& p=box.parcel;const auto& m=p.movement;
        need(p.external_outbox && m.recipient.cell_id==-1 && m.recipient.layer_id==-1 &&
             m.donor.cell_id>=0 && static_cast<std::size_t>(m.donor.cell_id)<nodes.size() &&
             m.donor.layer_id>=-1 && m.import_temperature_k==0 &&
             box.geographic_cell_id==seed.geographic_cell_ids[m.donor.cell_id] &&
             std::isfinite(m.mass_kg) && m.mass_kg>0 && std::isfinite(p.carried_enthalpy_j) &&
             std::isfinite(p.donor_temperature_k) && p.donor_temperature_k>=0 && std::isfinite(p.specific_enthalpy_j_kg) &&
             (m.phase==cryosphere_prototype::Phase::solid || m.phase==cryosphere_prototype::Phase::liquid) &&
             consumed.contains(m.id) && exported.insert(m.id).second,"invalid_seed","invalid or unowned seeded outbox");
        for(const auto interval:{p.ideal_specific_enthalpy_j_kg,p.ideal_carried_enthalpy_j,p.energy_projection_j})
            need(std::isfinite(interval.lower) && std::isfinite(interval.upper) && interval.lower<=interval.upper,
                 "invalid_seed","malformed seeded outbox certificate interval");
    }
    for(std::size_t i=0;i<seed.forcing_history.size();++i) {
        const auto& f=seed.forcing_history[i];id(f.id);
        need(forcing_ids.insert(f.id).second && std::isfinite(f.begin_seconds) && std::isfinite(f.end_seconds) &&
             f.begin_seconds>=0 && f.begin_seconds<f.end_seconds && f.begin_seconds<seed.elapsed_seconds &&
             f.absorbed_shortwave_w_m2.size()==nodes.size(),"invalid_seed","invalid seed forcing history");
        for(double S:f.absorbed_shortwave_w_m2) need(std::isfinite(S) && S>=0,"invalid_seed","invalid seed forcing");
        for(std::size_t j=0;j<i;++j) need(std::max(f.begin_seconds,seed.forcing_history[j].begin_seconds)>=
             std::min(f.end_seconds,seed.forcing_history[j].end_seconds),"invalid_seed","overlapping seed forcing history");
    }
    LayeredIceOwnerSnapshot state{seed.owner_id,0,seed.elapsed_seconds,seed.joint_energy_error_j,
        std::move(graph),std::move(seed.geographic_epoch),std::move(seed.geographic_cell_ids),std::move(seed.pending_outboxes),
        std::move(seed.consumed_event_ids),LayeredIceForcingHistory(std::move(seed.forcing_history))};
    return std::make_shared<const LayeredIceOwnerSnapshot>(std::move(state));
}

LayeredIceOwnerReceipt& prepare_physical(LayeredIceOwnerReceipt& r) {
    need(r.request.has_value() && r.initial,"kernel_protocol_refusal","bound request and initial snapshot required");
    const auto& q=*r.request;const auto& base=r.initial;const auto& l=r.limits;
    need(!q.movements.empty() || q.remap || q.thermal || !q.absorptions.empty() || q.topology,"empty_transition","no physical transition requested");
    need(!q.topology || (q.movements.empty() && !q.remap && !q.thermal && !q.forcing && q.absorptions.empty()),
         "mixed_topology","whole-inventory topology is a separate instantaneous boundary");
    need(q.absorptions.empty() || (q.movements.empty() && !q.remap && !q.thermal && !q.forcing && !q.topology),
         "mixed_absorption","absorption is a separate instantaneous receiving boundary");
    need(q.forcing.has_value()==q.thermal.has_value(),"forcing_refusal","thermal interval requires its complete forcing");
    need(!q.maximum_thermal_error_increment_j || q.thermal,"thermal_quota_refusal","thermal quota requires a thermal interval");
    if(q.maximum_thermal_error_increment_j)
        need(std::isfinite(*q.maximum_thermal_error_increment_j) && *q.maximum_thermal_error_increment_j>0,
             "thermal_quota_refusal","thermal quota must be finite and positive");
    auto next=*base;
    auto input=next.graph.input();
    r.initial_domain=graph_domain(next.graph,next.joint_energy_error_j);
    std::set<std::string> events(next.consumed_event_ids.begin(),next.consumed_event_ids.end());
    need(q.movements.size()<=l.max_consumed_events-events.size(),"event_cap","consumed event history cap");
    std::size_t exports=0;
    for(const auto& m:q.movements) {
        need(events.insert(m.id).second,"duplicate_event","event already consumed or repeated");
        if(m.recipient.cell_id==-1) ++exports;
    }
    if(q.topology) {
        need(q.topology->exports.size()<=l.max_consumed_events-events.size(),"event_cap","consumed whole export history cap");
        for(const auto& e:q.topology->exports) {
            need(events.insert(e.id).second,"duplicate_event","whole export event already consumed or repeated");
            ++exports;
        }
    }
    need(exports<=l.max_pending_outboxes-next.pending_outboxes.size(),"outbox_cap","unresolved outbox retention cap");
    if(q.thermal) {
        const auto& o=*q.thermal;const auto& f=*q.forcing;
        const double h=exact_duration(next.elapsed_seconds,q.end_seconds);
        need(same(h,o.duration_seconds),"clock_refusal","thermal duration differs from exact clock difference");
        need(std::isfinite(f.begin_seconds) && std::isfinite(f.end_seconds) && f.begin_seconds>=0 &&
             f.begin_seconds<=next.elapsed_seconds && f.end_seconds>=q.end_seconds &&
             f.begin_seconds<f.end_seconds && f.absorbed_shortwave_w_m2.size()==input.columns.size(),
             "forcing_refusal","forcing window or coverage");
        bool known=false;
        for(const auto& old:next.forcing_history) {
            if(old.id==f.id) {need(same_forcing(old,f),"forcing_identity_refusal","forcing ID changed operands");known=true;}
            else need(std::max(old.begin_seconds,f.begin_seconds)>=std::min(old.end_seconds,f.end_seconds),
                      "forcing_identity_refusal","distinct forcing windows overlap");
        }
        if(!known) {
            need(next.forcing_history.size()<l.max_commits,"forcing_refusal","retained forcing history cap");
            need(next.forcing_history.size()<l.max_stored_forcing_values/input.columns.size(),
                 "forcing_capacity_refusal","new forcing vector exceeds owned storage cap");
            next.forcing_history=next.forcing_history.appended(f);
        }
        for(std::size_t i=0;i<input.columns.size();++i) {
            need(std::isfinite(f.absorbed_shortwave_w_m2[i]) && f.absorbed_shortwave_w_m2[i]>=0,
                 "forcing_refusal","invalid absorbed forcing");
            input.columns[i].top_absorbed_shortwave_w_m2=f.absorbed_shortwave_w_m2[next.geographic_cell_ids[i]];
        }
        need(o.allow_pure_water_columns && std::isfinite(o.maximum_stage_error_j) && o.maximum_stage_error_j>0 &&
             std::isfinite(o.maximum_endpoint_error_j) && o.maximum_endpoint_error_j>0 &&
             o.maximum_sweeps>=0 && o.maximum_sweeps<=512 && o.maximum_coordinate_iterations>0 &&
             o.maximum_coordinate_iterations<=64 && o.maximum_scalar_evaluations>0 && o.maximum_scalar_evaluations<=16777216 &&
             o.reconstruction_leaves>0 && o.reconstruction_leaves<=64 && (o.reconstruction_leaves&(o.reconstruction_leaves-1))==0,
             "work_cap","thermal option admission");
        std::size_t nodes=next.graph.nodes().size();
        if(q.remap) {nodes=0;for(const auto& c:q.remap->targets) nodes+=c.layers.size();}
        need(nodes<=l.max_node_leaves/static_cast<std::size_t>(o.reconstruction_leaves),"work_cap","complete node-leaf reservation");
    } else need(same(q.end_seconds,next.elapsed_seconds),"clock_refusal","instantaneous material operations must have zero duration");

    bool graph_current=false;
    if(q.topology) {
        const auto& plan=*q.topology;
        LayeredIceTopologyRequest in{plan.id,input,next.joint_energy_error_j,r.maximum_joint_energy_error_j,
            plan.targets,plan.donors,plan.exports,plan.limits};
        ++r.work.topology_calls_started;
        try {r.topology=apply_layered_ice_topology(in);} catch(...) {r.work.observed_counts_complete=false;throw;}
        r.work.graph_builds_started+=r.topology->work.source_builder_calls_started+r.topology->work.output_builder_calls_started;
        need(r.topology->accepted,"topology_refusal","whole-inventory topology component refused; inspect nested receipt");
        const auto& result=*r.topology->final;
        next.graph=result.graph;input=next.graph.input();graph_current=true;
        next.joint_energy_error_j=result.final_global_energy_error_j;
        for(const auto& parcel:result.parcels)
            next.pending_outboxes.push_back({q.id,next.revision,parcel,next.geographic_cell_ids[parcel.movement.donor.cell_id]});
    }
    if(!q.absorptions.empty()) {
        std::set<std::pair<std::string,std::string>> selected;
        for(const auto& s:q.absorptions) {
            need(selected.emplace(s.transaction_id,s.event_id).second,"duplicate_absorption","parcel selected twice");
            const auto found=std::find_if(next.pending_outboxes.begin(),next.pending_outboxes.end(),[&](const auto& p) {
                return p.transaction_id==s.transaction_id && p.parcel.movement.id==s.event_id;
            });
            need(found!=next.pending_outboxes.end(),"unknown_absorption","pending parcel identity is absent");
            const auto a=s.recipient;
            need(a.cell_id>=0 && static_cast<std::size_t>(a.cell_id)<input.columns.size() && a.layer_id>=-1,
                 "invalid_absorption_recipient","unknown receiving address");
            const auto& c=input.columns[a.cell_id];
            const bool valid=a.layer_id==-1 ? c.deep_inventory && c.deep_inventory->water_mass_kg_m2>0 :
                static_cast<std::size_t>(a.layer_id)<c.layers.size() && c.layers[a.layer_id].water_mass_kg_m2>0;
            need(valid,"invalid_absorption_recipient","recipient must be an existing positive-water store");
        }
        ++r.work.absorption_calls_started;
        try {r.absorption=absorb_layered_owned_parcels({input,next.pending_outboxes,q.absorptions,
                next.joint_energy_error_j,r.maximum_joint_energy_error_j});}
        catch(...) {r.work.observed_counts_complete=false;throw;}
        r.work.graph_builds_started+=r.absorption->work.source_builder_calls_started+r.absorption->work.output_builder_calls_started;
        need(r.absorption->accepted,"absorption_refusal","receiving component refused; inspect nested receipt");
        const auto& received=*r.absorption->final;
        next.graph=received.graph;input=next.graph.input();graph_current=true;
        next.pending_outboxes=received.pending_outboxes;next.joint_energy_error_j=received.final_joint_energy_error_j;
    }
    if(!q.movements.empty()) {
        ++r.work.material_calls_started;
        try {r.material=apply_layered_material_events({input,next.joint_energy_error_j,r.maximum_joint_energy_error_j,q.movements});}
        catch(...) {r.work.observed_counts_complete=false;throw;}
        r.work.graph_builds_started+=r.material->graph_builds_started;
        r.work.calorimeter_calls_started+=r.material->mass_calls_started;
        need(r.material->accepted,"material_refusal","material component refused; inspect nested receipt");
        next.graph=*r.material->final_graph;input=next.graph.input();graph_current=true;
        next.joint_energy_error_j=r.material->joint_final_energy_error_upper_j;
        for(const auto& parcel:r.material->parcels) if(parcel.external_outbox)
            next.pending_outboxes.push_back({q.id,next.revision,parcel,next.geographic_cell_ids[parcel.movement.donor.cell_id]});
    }
    if(q.remap) {
        const auto& plan=*q.remap;
        LayeredIceRemapRequest in{plan.id,input,next.joint_energy_error_j,r.maximum_joint_energy_error_j,plan.targets,plan.donors,plan.limits};
        ++r.work.remap_calls_started;
        try {r.remap=remap_layered_ice(in);} catch(...) {r.work.observed_counts_complete=false;throw;}
        r.work.graph_builds_started+=r.remap->work.source_builder_calls_started+r.remap->work.output_builder_calls_started;
        need(r.remap->accepted,"remap_refusal","remap component refused; inspect nested receipt");
        next.graph=r.remap->final->graph;input=next.graph.input();graph_current=true;
        next.joint_energy_error_j=r.remap->final->final_global_energy_error_j;
    }
    if(!graph_current) {++r.work.graph_builds_started;next.graph=build_layered_ice_graph(input);}
    graph_limits(next.graph,l);
    (void)graph_domain(next.graph,next.joint_energy_error_j);
    if(q.thermal) {
        const auto in=next.graph.make_mesh_request(*q.thermal);
        ++r.work.thermal_calls_started;
        try {r.thermal=advance_enthalpy_mesh_sdirk2(in);} catch(...) {r.work.observed_counts_complete=false;throw;}
        const auto& t=*r.thermal;
        r.work.internal_be_calls_started+=t.stage_calls_started;r.work.scalar_evaluations+=t.scalar_evaluations;
        need(t.accepted,"thermal_refusal","thermal component refused; inspect nested receipt");
        need(t.final_enthalpy_j_m2 && t.final_enthalpy_j_m2->size()==next.graph.nodes().size() &&
             t.endpoint_error_available && std::isfinite(t.local_endpoint_error_upper_j) && t.local_endpoint_error_upper_j>=0,
             "thermal_protocol_refusal","accepted endpoint proof missing");
        LayeredIceOwnerThermalErrorCharge charge;
        charge.before_global_energy_error_j=next.joint_energy_error_j;
        charge.local_endpoint_error_upper_j=t.local_endpoint_error_upper_j;
        charge.after_global_energy_error_j=b::add(b::point(next.joint_energy_error_j),b::point(t.local_endpoint_error_upper_j)).upper;
        charge.charged_increment_j=b::sub(b::point(charge.after_global_energy_error_j),b::point(charge.before_global_energy_error_j));
        charge.maximum_thermal_error_increment_j=q.maximum_thermal_error_increment_j;
        charge.quota_passed=!q.maximum_thermal_error_increment_j ||
            charge.charged_increment_j.upper<=*q.maximum_thermal_error_increment_j;
        r.thermal_error_charge=charge;
        need(charge.after_global_energy_error_j>=charge.before_global_energy_error_j && charge.charged_increment_j.upper>=0,
             "thermal_protocol_refusal","invalid outward global thermal charge");
        need(charge.quota_passed,"thermal_increment_budget","rounded joint thermal error increment exceeds prescribed share");
        next.joint_energy_error_j=charge.after_global_energy_error_j;
        need(next.joint_energy_error_j<=r.maximum_joint_energy_error_j,"joint_error_budget","thermal increment exceeds joint budget");
        r.thermal_ledger=layered_ice_owner_thermal_ledger(t);
        for(const auto& node:next.graph.nodes())
            input.columns[node.cell_id].layers[node.layer_id].enthalpy_j_m2=(*t.final_enthalpy_j_m2)[node.thermal_node_id];
        ++r.work.graph_builds_started;next.graph=build_layered_ice_graph(input);
    }
    // The thermal increment enlarged E even for unchanged deep coordinates.
    r.final_domain=graph_domain(next.graph,next.joint_energy_error_j);
    next.elapsed_seconds=q.end_seconds;++next.revision;
    next.consumed_event_ids.assign(events.begin(),events.end());
    r.final=std::make_shared<const LayeredIceOwnerSnapshot>(std::move(next));r.prepared=true;
    return r;
}
} // namespace magic_geo::detail::layered_ice_owner_kernel
