#include "layered_ice_material.hpp"
#include "terrestrial_thermal/outward.hpp"
#include <algorithm>
#include <bit>
#include <cmath>
#include <cfloat>
#include <iomanip>
#include <limits>
#include <locale>
#include <map>
#include <set>
#include <sstream>
#include <tuple>

namespace magic_geo::detail {
namespace {
namespace a = cryosphere_prototype;
namespace b = phase_segment_prototype::bounds;
using I = EnthalpyMeshInterval;
using Key = std::pair<int,int>;
void need(bool ok, const char* code, const char* why) { if (!ok) throw LayeredIceError(code,why); }
Key key(LayeredMaterialAddress x) { return {x.cell_id,x.layer_id}; }
bool external(LayeredMaterialAddress x) { return x.cell_id == -1 && x.layer_id == -1; }
I total_mass(double area, double W) {
    const double raw=area*W;
    if (area==0 || W==0) return b::point(0);
    int ea=0,ew=0;std::frexp(area,&ea);std::frexp(W,&ew);
    // Product operands lie on grids 2^(e-53). When their product grid is
    // no finer than 2^-1074, a nonzero exact FMA residual cannot underflow
    // to zero. Only under that guard does zero residual prove raw exact.
    constexpr int digits=std::numeric_limits<double>::digits;
    if(std::isfinite(raw) && ea+ew-2*digits>=std::numeric_limits<double>::min_exponent-digits &&
       std::fma(area,W,-raw)==0) return b::point(raw);
    return b::mul(b::point(area),b::point(W));
}
I cap(const LayeredMaterialNodeCertificate& n, const a::WaterProperties& w, bool liquid, bool final = false) {
    return b::add(b::point(n.nonwater_capacity_j_m2_k),b::mul(b::point(final ? n.final_W : n.initial_W),
        b::point(liquid ? w.liquid_heat_capacity_j_kg_k : w.solid_heat_capacity_j_kg_k)));
}
I domain(LayeredMaterialNodeCertificate& n, const a::WaterProperties& w, double E, bool final) {
    const auto cs=cap(n,w,false,final),cl=cap(n,w,true,final);
    need(cs.lower>0 && cl.lower>0,"physical_domain_refusal","nonempty positive sensible capacities required");
    const auto radius=b::div(b::point(E),b::point(n.area_m2));
    const auto H=b::add(b::point(final ? n.final_H : n.initial_H),{-radius.upper,radius.upper});
    const auto floor=b::neg(b::mul(cs,b::point(w.freezing_temperature_k)));
    need(H.lower>=floor.upper,"uncertain_physical_domain","whole energy domain crosses absolute-zero floor");
    if(final) { n.after_H=H;n.after_floor=floor; } else { n.before_H=H;n.before_floor=floor; }
    return H;
}
I specific(const LayeredMaterialNodeCertificate& n, const a::WaterProperties& w, a::Phase phase) {
    if(phase==a::Phase::solid) return b::mul(b::point(w.solid_heat_capacity_j_kg_k),
        b::div(b::point(std::min(n.initial_H,0.0)),cap(n,w,false)));
    const auto excess=b::sub(b::point(n.initial_H),b::mul(b::point(n.initial_W),b::point(w.latent_heat_j_kg)));
    return b::add(b::point(w.latent_heat_j_kg),b::mul(b::point(w.liquid_heat_capacity_j_kg_k),
        b::div({std::max(0.0,excess.lower),std::max(0.0,excess.upper)},cap(n,w,true))));
}
I import_specific(const LayeredMaterialMovement& m,const a::WaterProperties& w) {
    const auto offset=b::sub(b::point(m.import_temperature_k),b::point(w.freezing_temperature_k));
    if(m.phase==a::Phase::solid) return b::mul(offset,b::point(w.solid_heat_capacity_j_kg_k));
    return b::add(b::point(w.latent_heat_j_kg),b::mul(offset,b::point(w.liquid_heat_capacity_j_kg_k)));
}
bool same(const a::Movement& m,const LayeredMaterialMovement& q,int donor,int recipient) {
    return m.donor==donor && m.recipient==recipient && m.phase==q.phase && m.mass_kg==q.mass_kg &&
        (donor>=0 || m.temperature_k==q.import_temperature_k);
}
std::string number(double x) {
    std::ostringstream s;s.imbue(std::locale::classic());
    if(std::isfinite(x))s<<std::setprecision(17)<<x;
    else s<<"{\"binary64_bits\":\""<<std::hex<<std::bit_cast<std::uint64_t>(x)<<"\"}";
    return s.str();
}
std::string quote(const std::string& x) {
    std::ostringstream s;s<<'"';for(unsigned char c:x) {
        if(c=='"'||c=='\\')s<<'\\'<<c;
        else if(c<32)s<<"\\u00"<<std::hex<<std::setw(2)<<std::setfill('0')<<static_cast<int>(c)<<std::dec;
        else s<<c;
    }s<<'"';return s.str();
}
struct Object {
    std::string x="{";bool first=true;
    void add(const char* k,const std::string& v) { if(!first)x+=',';first=false;x+=quote(k)+":"+v; }
    void num(const char* k,double v) { add(k,number(v)); }
    void flag(const char* k,bool v) { add(k,v ? "true" : "false"); }
    std::string finish() { return x+"}"; }
};
std::string interval(I v) { Object o;o.num("lower",v.lower);o.num("upper",v.upper);return o.finish(); }
std::string address(LayeredMaterialAddress v) { Object o;o.add("cell_id",std::to_string(v.cell_id));o.add("layer_id",std::to_string(v.layer_id));return o.finish(); }
std::string movement(const LayeredMaterialMovement& m) {
    Object o;o.add("id",quote(m.id));o.add("donor",address(m.donor));o.add("recipient",address(m.recipient));
    o.add("phase",std::to_string(static_cast<int>(m.phase)));o.num("mass_kg",m.mass_kg);o.num("import_temperature_k",m.import_temperature_k);return o.finish();
}
template<class T,class Fn> std::string array(const T& list,Fn fn) {
    std::string s="[";bool first=true;for(const auto& x:list){if(!first)s+=',';first=false;s+=fn(x);}return s+"]";
}
} // namespace

LayeredMaterialReceipt apply_layered_material_events(const LayeredMaterialRequest& q) {
    LayeredMaterialReceipt r;
    try {
        need(q.movements.size()<=4096,"work_cap","at most 4096 simultaneous movements");
        for(const auto& x:q.movements)need(!x.id.empty() && x.id.size()<=96,"invalid_request","bounded nonempty movement identifiers required");
        need(std::isfinite(q.inherited_energy_error_j) && q.inherited_energy_error_j>=0 &&
            std::isfinite(q.maximum_final_energy_error_j) && q.maximum_final_energy_error_j>0 &&
            q.inherited_energy_error_j<=q.maximum_final_energy_error_j,"invalid_request","invalid energy policy");
        ++r.graph_builds_started;r.initial_graph=build_layered_ice_graph(q.initial);r.request=q;
        std::map<Key,int> indices;std::vector<a::Column> columns;std::vector<a::State> initial;
        auto append=[&](int cell,int layer,double W,double H,double C) {
            const auto A=q.initial.columns[static_cast<std::size_t>(cell)].area_m2;
            indices[{cell,layer}]=static_cast<int>(r.nodes.size());columns.push_back({A,C});initial.push_back({W,H});
            LayeredMaterialNodeCertificate n;n.address={cell,layer};n.area_m2=A;n.nonwater_capacity_j_m2_k=C;
            n.initial_W=W;n.initial_H=H;domain(n,q.initial.water,q.inherited_energy_error_j,false);r.nodes.push_back(n);
        };
        for(const auto& c:q.initial.columns) {
            for(const auto& l:c.layers)append(c.cell_id,l.layer_id,l.water_mass_kg_m2,l.enthalpy_j_m2,l.layer_id==0 ? c.top_nonwater_heat_capacity_j_m2_k : 0);
            if(c.deep_inventory && c.deep_inventory->water_mass_kg_m2>0)append(c.cell_id,-1,c.deep_inventory->water_mass_kg_m2,c.deep_inventory->enthalpy_j_m2,0);
        }
        auto index=[&](LayeredMaterialAddress x) {
            if(external(x))return -1;
            const auto it=indices.find(key(x));need(it!=indices.end(),"invalid_address","unknown or empty material reservoir");return it->second;
        };
        std::vector<LayeredMaterialMovement> ordered=q.movements;
        std::sort(ordered.begin(),ordered.end(),[](const auto& x,const auto& y){return x.id<y.id;});
        a::MassEventInput event;std::set<std::string> ids;
        for(const auto& m:ordered) {
            need(ids.insert(m.id).second,"duplicate_movement","movement id repeated in batch");
            const int d=index(m.donor),t=index(m.recipient);
            need(d>=0 || t>=0,"invalid_address","both endpoints external");
            need(d<0 || t<0 || (d!=t && m.donor.cell_id==m.recipient.cell_id),"invalid_address","internal movement must join distinct stores in one column");
            need(m.phase==a::Phase::solid || m.phase==a::Phase::liquid,"invalid_request","invalid phase");
            need(std::isfinite(m.mass_kg) && m.mass_kg>0,"invalid_request","positive finite parcel mass required");
            if(d<0) {
                need(std::isfinite(m.import_temperature_k) && m.import_temperature_k>=0 &&
                    (m.phase==a::Phase::solid ? m.import_temperature_k<=q.initial.water.freezing_temperature_k :
                        m.import_temperature_k>=q.initial.water.freezing_temperature_k),"invalid_request","import phase/temperature mismatch");
                event.imports.push_back({static_cast<std::size_t>(t),m.phase,m.mass_kg,m.import_temperature_k});
            } else {
                need(m.import_temperature_k==0,"invalid_request","donor temperature cannot be overridden");
                auto& n=r.nodes[static_cast<std::size_t>(d)];auto& gross=m.phase==a::Phase::solid ? n.gross_solid_kg : n.gross_liquid_kg;
                gross=b::add(gross,b::point(m.mass_kg));
                if(t<0)event.exports.push_back({static_cast<std::size_t>(d),m.phase,m.mass_kg});
                else event.transfers.push_back({static_cast<std::size_t>(d),static_cast<std::size_t>(t),m.phase,m.mass_kg});
            }
        }
        for(const auto& n:r.nodes) {
            const auto M=total_mass(n.area_m2,n.initial_W);
            if(!b::zero(n.gross_liquid_kg)) {
                need(n.gross_liquid_kg.upper<=M.lower &&
                    b::mul(n.gross_liquid_kg,b::point(q.initial.water.latent_heat_j_kg)).upper<=
                    b::mul(b::point(n.area_m2),b::point(n.before_H.lower)).lower,
                    "uncertain_liquid_inventory","gross initial liquid unavailable throughout error domain");
            }
            if(!b::zero(n.gross_solid_kg)) {
                need(n.gross_solid_kg.upper<=M.lower &&
                    b::mul(b::point(n.area_m2),b::point(n.before_H.upper)).upper<=
                    b::mul(b::sub(M,n.gross_solid_kg),b::point(q.initial.water.latent_heat_j_kg)).lower,
                    "uncertain_solid_inventory","gross initial solid unavailable throughout error domain");
            }
        }
        r.gross_initial_phase_inventory_proved=true;r.joint_nonexpansion_proved=true;
        a::MassEventResult result;
#if !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) && LDBL_MANT_DIG >= 64 && LDBL_MAX_EXP >= 16384
        ++r.mass_calls_started;result=a::apply_mass_events_pure_water(q.initial.water,columns,initial,event);
#else
        throw LayeredIceError("capability_unavailable","extended-range calorimeter backend unavailable");
#endif
        need(result.state.size()==r.nodes.size() && result.movements.size()==ordered.size(),"mass_protocol_refusal","mass producer coverage changed");
        std::vector<bool> used(result.movements.size());std::vector<I> deltaM(r.nodes.size()),idealJ(r.nodes.size());
        I retained_defect{},outbox_defect{};LayeredIceInput after=q.initial;
        for(const auto& m:ordered) {
            const int d=index(m.donor),t=index(m.recipient);std::size_t found=result.movements.size();
            for(std::size_t j=0;j<result.movements.size();++j)if(!used[j] && same(result.movements[j],m,d,t)){found=j;break;}
            need(found<result.movements.size(),"mass_protocol_refusal","parcel identity missing");used[found]=true;const auto& raw=result.movements[found];
            LayeredMaterialParcelCertificate p;p.movement=m;p.donor_temperature_k=raw.temperature_k;
            p.specific_enthalpy_j_kg=raw.specific_enthalpy_j_kg;p.carried_enthalpy_j=raw.carried_enthalpy_j;
            p.ideal_specific_enthalpy_j_kg=d<0 ? import_specific(m,q.initial.water) : specific(r.nodes[static_cast<std::size_t>(d)],q.initial.water,m.phase);
            p.ideal_carried_enthalpy_j=b::mul(b::point(m.mass_kg),p.ideal_specific_enthalpy_j_kg);
            p.energy_projection_j=b::sub(b::point(p.carried_enthalpy_j),p.ideal_carried_enthalpy_j);p.external_outbox=t<0;
            if(d>=0){deltaM[static_cast<std::size_t>(d)]=b::sub(deltaM[static_cast<std::size_t>(d)],b::point(m.mass_kg));idealJ[static_cast<std::size_t>(d)]=b::sub(idealJ[static_cast<std::size_t>(d)],p.ideal_carried_enthalpy_j);}
            else {r.external_net_mass_kg=b::add(r.external_net_mass_kg,b::point(m.mass_kg));r.external_net_energy_j=b::add(r.external_net_energy_j,b::point(p.carried_enthalpy_j));}
            if(t>=0){deltaM[static_cast<std::size_t>(t)]=b::add(deltaM[static_cast<std::size_t>(t)],b::point(m.mass_kg));idealJ[static_cast<std::size_t>(t)]=b::add(idealJ[static_cast<std::size_t>(t)],p.ideal_carried_enthalpy_j);}
            else {r.external_net_mass_kg=b::sub(r.external_net_mass_kg,b::point(m.mass_kg));r.external_net_energy_j=b::sub(r.external_net_energy_j,b::point(p.carried_enthalpy_j));outbox_defect=b::add(outbox_defect,b::point(b::absmax(p.energy_projection_j)));}
            r.parcels.push_back(p);
        }
        for(std::size_t i=0;i<r.nodes.size();++i) {
            auto& n=r.nodes[i];n.final_W=result.state[i].water_mass_kg_m2;n.final_H=result.state[i].enthalpy_j_m2;const auto A=b::point(n.area_m2);
            n.ideal_final_W=b::add(b::point(n.initial_W),b::div(deltaM[i],A));
            n.ideal_final_H=b::add(b::point(n.initial_H),b::div(idealJ[i],A));
            n.mass_projection_kg_m2=b::sub(b::point(n.final_W),n.ideal_final_W);
            n.energy_projection_j_m2=b::sub(b::point(n.final_H),n.ideal_final_H);
            retained_defect=b::add(retained_defect,b::mul(A,b::point(b::absmax(n.energy_projection_j_m2))));
            r.retained_mass_change_kg=b::add(r.retained_mass_change_kg,b::mul(A,b::sub(b::point(n.final_W),b::point(n.initial_W))));
            r.retained_energy_change_j=b::add(r.retained_energy_change_j,b::mul(A,b::sub(b::point(n.final_H),b::point(n.initial_H))));
            auto& c=after.columns[static_cast<std::size_t>(n.address.cell_id)];
            if(n.address.layer_id<0){c.deep_inventory->water_mass_kg_m2=n.final_W;c.deep_inventory->enthalpy_j_m2=n.final_H;}
            else {auto& l=c.layers[static_cast<std::size_t>(n.address.layer_id)];l.water_mass_kg_m2=n.final_W;l.enthalpy_j_m2=n.final_H;}
        }
        r.retained_energy_defect_upper_j=retained_defect.upper;r.outbox_energy_defect_upper_j=outbox_defect.upper;
        r.joint_final_energy_error_upper_j=b::add(b::point(q.inherited_energy_error_j),b::add(retained_defect,outbox_defect)).upper;
        r.mass_balance_residual_kg=b::sub(r.retained_mass_change_kg,r.external_net_mass_kg);
        r.energy_balance_residual_j=b::sub(r.retained_energy_change_j,r.external_net_energy_j);
        need(r.joint_final_energy_error_upper_j<=q.maximum_final_energy_error_j,"cumulative_error_budget","joint retained and outbox error exceeds budget");
        for(auto& n:r.nodes)domain(n,q.initial.water,r.joint_final_energy_error_upper_j,true);
        ++r.graph_builds_started;r.final_graph=build_layered_ice_graph(after);r.accepted=true;
    } catch(const LayeredIceError& e) {r.failure_code=e.code;r.detail=e.what();}
      catch(const a::Error& e) {r.failure_code="mass_operation_refusal";r.detail=e.what();}
      catch(const std::exception& e) {r.failure_code="arithmetic_refusal";r.detail=e.what();}
    return r;
}
std::string layered_material_request_json(const LayeredMaterialRequest& q) {
    Object o;o.add("initial",layered_ice_input_json(q.initial));o.num("inherited_energy_error_j",q.inherited_energy_error_j);
    o.num("maximum_final_energy_error_j",q.maximum_final_energy_error_j);o.add("movements",array(q.movements,movement));return o.finish();
}
std::string layered_material_receipt_json(const LayeredMaterialReceipt& r) {
    Object o;o.add("model",quote("layered_initial_phase_material_event_v1"));
    o.add("energy_error_scope",quote("canonical_projected_W_joint_retained_new_outbox_L1_joules_v1"));
    for(const char* k:{"original_mass_trajectory_certified","original_source_accuracy_certified","geometry_error_certified","automatic_drainage_policy","owner_commit_available","ordinary_generation_changed"})o.flag(k,false);
    o.flag("accepted",r.accepted);o.add("failure_code",quote(r.failure_code));o.add("detail",quote(r.detail));
    o.add("graph_builds_started",std::to_string(r.graph_builds_started));o.add("mass_calls_started",std::to_string(r.mass_calls_started));
    o.add("request",r.request ? layered_material_request_json(*r.request) : "null");
    o.add("initial_graph",r.initial_graph ? layered_ice_graph_json(*r.initial_graph) : "null");
    o.add("final_graph",r.final_graph ? layered_ice_graph_json(*r.final_graph) : "null");
    o.add("nodes",array(r.nodes,[](const auto& n){Object x;x.add("address",address(n.address));
#define N(k) x.num(#k,n.k)
        N(area_m2);N(nonwater_capacity_j_m2_k);N(initial_W);N(initial_H);N(final_W);N(final_H);
#undef N
#define B(k) x.add(#k,interval(n.k))
        B(before_H);B(before_floor);B(after_H);B(after_floor);B(gross_solid_kg);B(gross_liquid_kg);
        B(ideal_final_W);B(ideal_final_H);B(mass_projection_kg_m2);B(energy_projection_j_m2);
#undef B
        return x.finish();}));
    o.add("parcels",array(r.parcels,[](const auto& p){Object x;x.add("movement",movement(p.movement));x.num("donor_temperature_k",p.donor_temperature_k);
        x.num("specific_enthalpy_j_kg",p.specific_enthalpy_j_kg);x.num("carried_enthalpy_j",p.carried_enthalpy_j);
        x.add("ideal_specific_enthalpy_j_kg",interval(p.ideal_specific_enthalpy_j_kg));x.add("ideal_carried_enthalpy_j",interval(p.ideal_carried_enthalpy_j));
        x.add("energy_projection_j",interval(p.energy_projection_j));x.flag("external_outbox",p.external_outbox);return x.finish();}));
#define N(k) o.num(#k,r.k)
    N(retained_energy_defect_upper_j);N(outbox_energy_defect_upper_j);N(joint_final_energy_error_upper_j);
#undef N
#define B(k) o.add(#k,interval(r.k))
    B(retained_mass_change_kg);B(external_net_mass_kg);B(mass_balance_residual_kg);B(retained_energy_change_j);B(external_net_energy_j);B(energy_balance_residual_j);
#undef B
    o.flag("gross_initial_phase_inventory_proved",r.gross_initial_phase_inventory_proved);o.flag("joint_nonexpansion_proved",r.joint_nonexpansion_proved);return o.finish();
}
} // namespace magic_geo::detail
