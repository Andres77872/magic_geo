#include "layered_ice_absorption.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <tuple>

namespace magic_geo::detail {
namespace {
namespace b = phase_segment_prototype::bounds;
using I = EnthalpyMeshInterval;
using Address = std::pair<int,int>;
using Parcel = std::pair<std::string,std::string>;
void need(bool ok,const char* code,const char* detail) {
    if(!ok) throw LayeredIceError(code,detail);
}
void identifier(const std::string& s) {
    need(!s.empty() && s.size()<=96,"invalid_absorption","bounded identifier required");
    for(unsigned char c:s) need(c>=33 && c<=126,"invalid_absorption","visible ASCII identifier required");
}
void domain(LayeredIceAbsorptionNode& n,const cryosphere_prototype::WaterProperties& w,double E,bool final) {
    const double W=final?n.final_W:n.initial_W,H=final?n.final_H:n.initial_H;
    const auto capacity=b::add(b::point(n.nonwater_capacity_j_m2_k),
        b::mul(b::point(W),b::point(w.solid_heat_capacity_j_kg_k)));
    const auto radius=b::div(b::point(E),b::point(n.area_m2));
    const auto box=b::add(b::point(H),{-radius.upper,radius.upper});
    const auto floor=b::neg(b::mul(capacity,b::point(w.freezing_temperature_k)));
    if(final) {n.after_H=box;n.after_floor=floor;} else {n.before_H=box;n.before_floor=floor;}
    need(box.lower>=floor.upper,"uncertain_physical_domain","whole retained error ball crosses absolute-zero floor");
}
double represented(long double x) {
    const auto y=static_cast<double>(x);
    need(std::isfinite(x) && std::isfinite(y),"absorption_arithmetic_refusal","nonfinite receiving candidate");
    return y;
}
} // namespace

LayeredIceAbsorptionReceipt absorb_layered_owned_parcels(const LayeredIceAbsorptionRequest& q) {
    LayeredIceAbsorptionReceipt r;
    try {
        need(!q.selections.empty() && q.selections.size()<=4096 && q.pending_outboxes.size()<=4096,
            "absorption_cap","nonempty bounded whole-parcel selection required");
        need(std::isfinite(q.inherited_joint_energy_error_j) && q.inherited_joint_energy_error_j>=0 &&
             std::isfinite(q.maximum_final_energy_error_j) && q.maximum_final_energy_error_j>=0 &&
             q.inherited_joint_energy_error_j<=q.maximum_final_energy_error_j,
             "invalid_absorption","invalid joint energy allowance");
        r.request=q;
        std::map<Parcel,std::size_t> parcels;
        std::set<std::string> events;
        for(std::size_t i=0;i<q.pending_outboxes.size();++i) {
            const auto& p=q.pending_outboxes[i];identifier(p.transaction_id);identifier(p.parcel.movement.id);
            const auto& m=p.parcel.movement;
            need(parcels.emplace(Parcel{p.transaction_id,m.id},i).second && events.insert(m.id).second,
                "invalid_absorption","duplicate pending parcel identity");
            need(p.parcel.external_outbox && m.recipient.cell_id==-1 && m.recipient.layer_id==-1 &&
                 std::isfinite(m.mass_kg) && m.mass_kg>0 && std::isfinite(p.parcel.carried_enthalpy_j),
                 "invalid_absorption","invalid canonical pending parcel");
        }
        auto ordered=q.selections;
        std::sort(ordered.begin(),ordered.end(),[](const auto& a,const auto& c) {
            return std::tie(a.transaction_id,a.event_id)<std::tie(c.transaction_id,c.event_id);
        });
        std::set<Parcel> selected;
        for(const auto& s:ordered) {
            identifier(s.transaction_id);identifier(s.event_id);
            const Parcel key{s.transaction_id,s.event_id};
            need(selected.insert(key).second,"duplicate_absorption","pending parcel selected twice");
            need(parcels.contains(key),"unknown_absorption","selected pending parcel is absent");
        }
        ++r.work.source_builder_calls_started;
        r.source_graph=build_layered_ice_graph(q.initial);
        auto output=q.initial;
        std::map<Address,std::size_t> addresses;
        auto append=[&](const LayeredIceColumnInput& c,int layer,double W,double H,double C) {
            addresses.emplace(Address{c.cell_id,layer},r.nodes.size());
            LayeredIceAbsorptionNode n;n.address={c.cell_id,layer};n.area_m2=c.area_m2;
            n.nonwater_capacity_j_m2_k=C;n.initial_W=n.final_W=W;n.initial_H=n.final_H=H;
            n.ideal_final_W=b::point(W);n.ideal_final_H=b::point(H);
            domain(n,q.initial.water,q.inherited_joint_energy_error_j,false);r.nodes.push_back(n);
        };
        for(const auto& c:q.initial.columns) {
            for(const auto& l:c.layers) append(c,l.layer_id,l.water_mass_kg_m2,l.enthalpy_j_m2,
                l.layer_id==0?c.top_nonwater_heat_capacity_j_m2_k:0);
            if(c.deep_inventory && c.deep_inventory->water_mass_kg_m2>0)
                append(c,-1,c.deep_inventory->water_mass_kg_m2,c.deep_inventory->enthalpy_j_m2,0);
        }
        std::vector<long double> mass(r.nodes.size(),0),energy(r.nodes.size(),0);
        std::vector<bool> updated(r.nodes.size(),false);
        // Validate every recipient before applying even private arithmetic.
        for(const auto& s:ordered) {
            const auto found=addresses.find({s.recipient.cell_id,s.recipient.layer_id});
            need(found!=addresses.end() && r.nodes[found->second].initial_W>0,
                "invalid_absorption_recipient","recipient must be an existing positive-water store");
        }
        for(const auto& s:ordered) {
            const auto i=addresses.at({s.recipient.cell_id,s.recipient.layer_id});
            const auto& p=q.pending_outboxes[parcels.at({s.transaction_id,s.event_id})].parcel;
            const double m=p.movement.mass_kg,J=p.carried_enthalpy_j;
            mass[i]+=static_cast<long double>(m);energy[i]+=static_cast<long double>(J);
            auto& n=r.nodes[i];n.absorbed_mass_kg=b::add(n.absorbed_mass_kg,b::point(m));
            n.absorbed_energy_j=b::add(n.absorbed_energy_j,b::point(J));
            r.absorbed_mass_kg=b::add(r.absorbed_mass_kg,b::point(m));
            r.absorbed_energy_j=b::add(r.absorbed_energy_j,b::point(J));
            updated[i]=true;++r.work.parcels_absorbed;
        }
        I defect{};
        for(std::size_t i=0;i<r.nodes.size();++i) {
            if(!updated[i]) continue;
            auto& n=r.nodes[i];const auto A=b::point(n.area_m2);
            // Long-double candidates are not claimed correctly rounded exact
            // rational sums. The independent interval difference covers all
            // summation, division and final conversion errors.
            n.final_W=represented(static_cast<long double>(n.initial_W)+mass[i]/n.area_m2);
            n.final_H=represented(static_cast<long double>(n.initial_H)+energy[i]/n.area_m2);
            need(n.final_W>0,"absorption_arithmetic_refusal","receiving mass is not positive");
            n.ideal_final_W=b::add(b::point(n.initial_W),b::div(n.absorbed_mass_kg,A));
            n.ideal_final_H=b::add(b::point(n.initial_H),b::div(n.absorbed_energy_j,A));
            n.mass_projection_kg_m2=b::sub(b::point(n.final_W),n.ideal_final_W);
            n.energy_projection_j_m2=b::sub(b::point(n.final_H),n.ideal_final_H);
            defect=b::add(defect,b::mul(A,b::point(b::absmax(n.energy_projection_j_m2))));
            r.retained_mass_change_kg=b::add(r.retained_mass_change_kg,b::mul(A,b::sub(b::point(n.final_W),b::point(n.initial_W))));
            r.retained_energy_change_j=b::add(r.retained_energy_change_j,b::mul(A,b::sub(b::point(n.final_H),b::point(n.initial_H))));
            auto& c=output.columns[n.address.cell_id];
            if(n.address.layer_id<0) {c.deep_inventory->water_mass_kg_m2=n.final_W;c.deep_inventory->enthalpy_j_m2=n.final_H;}
            else {c.layers[n.address.layer_id].water_mass_kg_m2=n.final_W;c.layers[n.address.layer_id].enthalpy_j_m2=n.final_H;}
            ++r.work.nodes_updated;
        }
        r.energy_projection_defect_upper_j=defect.upper;
        r.mass_balance_residual_kg=b::sub(r.retained_mass_change_kg,r.absorbed_mass_kg);
        r.energy_balance_residual_j=b::sub(r.retained_energy_change_j,r.absorbed_energy_j);
        const double E=b::add(b::point(q.inherited_joint_energy_error_j),defect).upper;
        need(E<=q.maximum_final_energy_error_j,"cumulative_error_budget","receiving projection exceeds joint budget");
        ++r.work.output_builder_calls_started;
        auto graph=build_layered_ice_graph(output);
        for(auto& n:r.nodes) domain(n,q.initial.water,E,true);
        std::vector<LayeredIceOwnedParcel> remaining;
        for(const auto& p:q.pending_outboxes)
            if(!selected.contains({p.transaction_id,p.parcel.movement.id})) remaining.push_back(p);
        r.final=LayeredIceAbsorptionResult{std::move(graph),std::move(remaining),E};r.accepted=true;
    } catch(const LayeredIceError& e) {r.failure_code=e.code;r.detail=e.what();
    } catch(const std::exception& e) {r.failure_code="absorption_arithmetic_refusal";r.detail=e.what();}
    return r;
}
} // namespace magic_geo::detail
