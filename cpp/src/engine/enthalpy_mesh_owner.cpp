#include "enthalpy_mesh_owner.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <algorithm>
#include <bit>
#include <cfloat>
#include <cfenv>
#include <cmath>
#include <limits>
#include <new>
#include <set>
#include <utility>

#if !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) && LDBL_MANT_DIG >= 64 && LDBL_MAX_EXP >= 16384
#define MESH_OWNER_HAS_A 1
#else
#define MESH_OWNER_HAS_A 0
#endif

namespace magic_geo::detail {
namespace {
namespace a = cryosphere_prototype;
namespace p = phase_segment_prototype;
namespace b = p::bounds;
using I = EnthalpyMeshInterval;
void need(bool ok,const char* code,const std::string& detail) {
    if(!ok) throw TerrestrialWaterError(code,detail);
}
bool finite(double x) { return std::isfinite(x); }
bool same(double x,double y) { return std::bit_cast<std::uint64_t>(x)==std::bit_cast<std::uint64_t>(y); }
bool exposed(const Cell& c) { return !c.is_water && !c.is_lake; }
void positive(double x,const char* label) { need(finite(x) && x>0,"invalid_input",label); }
void arithmetic() {
    need(std::numeric_limits<double>::is_iec559 && std::numeric_limits<double>::digits==53 &&
         std::fegetround()==FE_TONEAREST,"capability_unavailable","nearest binary64 arithmetic required");
    volatile double normal=std::numeric_limits<double>::min(),tiny=std::numeric_limits<double>::denorm_min();
    volatile double tenth=.1,one=1;
    volatile double x=normal*tenth,y=tiny*one;
    need(x>0 && y>0,"capability_unavailable","gradual underflow required");
}
void increment(std::uint64_t& x,std::uint64_t n=1) {
    need(n<=std::numeric_limits<std::uint64_t>::max()-x,"work_cap","work counter overflow");x+=n;
}
void identifier(const std::string& id,std::size_t maximum) {
    need(!id.empty() && id.size()<=maximum,"invalid_identifier","identifier length");
    for(unsigned char c:id) need(c>=33 && c<=126,"invalid_identifier","visible ASCII identifier required");
}
bool exact_sum(double x,double y,double result) {
    if(!finite(result) || x+y!=result) return false;
    const double bp=result-x;return (x-(result-bp))+(y-bp)==0;
}
double duration(double start,double end) {
    need(finite(start) && finite(end) && start>=0 && end>start,"clock_refusal","invalid interval endpoints");
    const double h=end-start;
    need(finite(h) && h>0 && exact_sum(start,h,end),"clock_refusal","duration does not close the exact clock");
    return h;
}
std::uint64_t ticks(double value,double quantum) {
    const double n=value/quantum;
    need(finite(n) && n>=0 && n<=9007199254740992.0 && n==std::floor(n) && n*quantum==value,
         "clock_refusal","clock is not on the common endpoint lattice");
    return static_cast<std::uint64_t>(n);
}
p::Column scalar_column(const SurfaceEnergyColumn& c) {
    // Scalar mass/error adapter only. All sensible storage is already in C.
    return {c.area_m2,c.heat_capacity_j_m2_k,0,0,0,0};
}
I temperature(const EnthalpyMeshProperties& p,std::size_t i,double W,I H) {
    const I C=b::point(p.columns[i].heat_capacity_j_m2_k),w=b::point(W);
    const I solid=b::add(C,b::mul(w,b::point(p.water.solid_heat_capacity_j_kg_k)));
    const I liquid=b::add(C,b::mul(w,b::point(p.water.liquid_heat_capacity_j_kg_k)));
    const I above=b::sub(H,b::mul(w,b::point(p.water.latent_heat_j_kg)));
    return b::add(b::point(p.water.freezing_temperature_k),b::add(
        b::div({std::min(0.0,H.lower),std::min(0.0,H.upper)},solid),
        b::div({std::max(0.0,above.lower),std::max(0.0,above.upper)},liquid)));
}
EnthalpyMeshReferenceDomain domain(const EnthalpyMeshProperties& props,
    const std::vector<a::State>& state,double E,const std::vector<double>& S,double h) {
    EnthalpyMeshReferenceDomain r;r.attempted=true;r.inherited_error_j=E;r.duration_seconds=h;
    try {
        need(finite(E) && E>=0 && finite(h) && h>=0,"domain_refusal","invalid reference error or duration");
        need(state.size()==props.columns.size() && S.size()==state.size(),"domain_refusal","reference coverage");
        double Tmax=props.water.freezing_temperature_k,rate=0;
        for(std::size_t i=0;i<state.size();++i) {
            const auto& x=state[i];const auto& c=props.columns[i];
            need(finite(S[i]) && S[i]>=0,"domain_refusal","invalid absorbed source");
            const double e=b::div(b::point(E),b::point(c.area_m2)).upper;
            const I H=b::add(b::point(x.enthalpy_j_m2),{-e,e});
            const I floor=b::neg(b::mul(b::add(b::point(c.heat_capacity_j_m2_k),
                b::mul(b::point(x.water_mass_kg_m2),b::point(props.water.solid_heat_capacity_j_kg_k))),
                b::point(props.water.freezing_temperature_k)));
            r.component_radius_j_m2.push_back(e);r.enthalpy_box_j_m2.push_back(H);r.physical_floor_j_m2.push_back(floor);
            need(H.lower>=floor.upper,"uncertain_physical_domain","global error ball crosses a physical floor");
            Tmax=std::max(Tmax,temperature(props,i,x.water_mass_kg_m2,H).upper);
            rate=std::max(rate,b::div(b::point(S[i]),b::point(c.heat_capacity_j_m2_k)).upper);
        }
        r.reference_temperature_upper_k=b::add(b::point(Tmax),b::mul(b::point(h),b::point(rate))).upper;
        r.proved=true;
    } catch(const std::bad_alloc&) {throw;
    } catch(const TerrestrialWaterError& e) {r.failure_code=e.code;r.detail=e.what();
    } catch(const std::exception& e) {r.failure_code="domain_enclosure_refusal";r.detail=e.what();}
    return r;
}
void require_domain(const EnthalpyMeshReferenceDomain& d) {
    need(d.proved,"uncertain_physical_domain",d.failure_code+": "+d.detail);
}
void limits_valid(const EnthalpyMeshOwnerLimits& x) {
    EnthalpyMeshOwnerLimits cap;
    cap.max_prepare_attempts=4096;cap.max_committed_intervals=2048;
    cap.max_stored_forcing_values=2097152;
#define LIMIT(name) need(x.name>0 && x.name<=cap.name,"invalid_limits",#name)
    LIMIT(max_cells);LIMIT(max_edges);LIMIT(max_prepare_attempts);LIMIT(max_committed_intervals);
    LIMIT(max_events_per_interval);LIMIT(max_consumed_event_ids);LIMIT(max_identifier_bytes);
    LIMIT(max_thermal_attempts);LIMIT(max_accepted_steps);LIMIT(max_scalar_evaluations_per_prepare);
    LIMIT(max_field_evaluations_per_prepare);LIMIT(max_retained_cell_leaves);LIMIT(max_retained_edge_leaves);
    LIMIT(max_stored_forcing_values);
#undef LIMIT
}
void forcing_valid(const EnthalpyMeshForcing& f,std::size_t cells,std::size_t id_cap) {
    identifier(f.id,id_cap);(void)duration(f.begin_seconds,f.end_seconds);
    need(f.absorbed_shortwave_w_m2.size()==cells,"forcing_refusal","complete mesh forcing required");
    for(double S:f.absorbed_shortwave_w_m2) need(finite(S) && S>=0,"forcing_refusal","nonnegative finite absorbed shortwave required");
}
bool same_forcing(const EnthalpyMeshForcing& a,const EnthalpyMeshForcing& b) {
    if(a.id!=b.id || !same(a.begin_seconds,b.begin_seconds) || !same(a.end_seconds,b.end_seconds) ||
       a.absorbed_shortwave_w_m2.size()!=b.absorbed_shortwave_w_m2.size()) return false;
    for(std::size_t i=0;i<a.absorbed_shortwave_w_m2.size();++i)
        if(!same(a.absorbed_shortwave_w_m2[i],b.absorbed_shortwave_w_m2[i])) return false;
    return true;
}
void compare_forcing(const EnthalpyMeshForcing& fresh,const EnthalpyMeshForcing& old) {
    if(fresh.id==old.id) need(same_forcing(fresh,old),"forcing_identity_refusal","forcing ID changed operands");
    else need(std::max(fresh.begin_seconds,old.begin_seconds)>=std::min(fresh.end_seconds,old.end_seconds),
              "forcing_identity_refusal","distinct forcing windows overlap");
}
void apply_sources(const EnthalpyMeshIntervalRequest& request,const TerrestrialSurfaceSnapshot& surface,
                   const EnthalpyMeshProperties& props,double B,EnthalpyMeshOwnerWork& work,EnthalpyMeshOwnerReceipt& r) {
    const auto& initial=r.initial;const auto n=surface.cells().size();
    std::vector<int> map(n,-1);a::MassEventInput mass;
    for(std::size_t i=0;i<n;++i) if(exposed(surface.cells()[i])) {
        map[i]=static_cast<int>(r.kernel_columns.size());r.kernel_column_cell_ids.push_back(static_cast<int>(i));
        r.kernel_columns.push_back({props.columns[i].area_m2,props.columns[i].heat_capacity_j_m2_k});
        r.kernel_initial.push_back(initial.state[i]);
    }
    for(const auto& x:request.imports) mass.imports.push_back({static_cast<std::size_t>(map[x.cell_id]),x.phase,x.mass_kg,x.temperature_k});
    for(const auto& x:request.initial_liquid_withdrawals) mass.exports.push_back({static_cast<std::size_t>(map[x.cell_id]),a::Phase::liquid,x.mass_kg});
    r.mass_request=mass;increment(work.mass_calls_started);r.mass_call_started=true;
#if MESH_OWNER_HAS_A
    try {r.mass_receipt=a::apply_mass_events(props.water,r.kernel_columns,r.kernel_initial,mass);}
    catch(const a::Error& e) {throw TerrestrialWaterError("mass_refused",e.what());}
    catch(...) {work.observed_counts_complete=false;throw;}
#else
    throw TerrestrialWaterError("capability_unavailable","mass-event calorimeter unavailable");
#endif
    increment(work.mass_calls_returned);
    const auto& result=*r.mass_receipt;
    need(result.state.size()==r.kernel_column_cell_ids.size(),"mass_protocol_refusal","mass state coverage");
    r.private_prefix_error_available=false;
    for(std::size_t j=0;j<r.kernel_column_cell_ids.size();++j) r.private_prefix.state[r.kernel_column_cell_ids[j]]=result.state[j];
    std::vector<std::vector<CanonicalMovement>> imports(n),withdrawals(n);
    std::vector<bool> used(result.movements.size(),false);
    for(const auto& x:request.imports) {
        bool found=false;
        for(std::size_t j=0;j<used.size();++j) {
            const auto& m=result.movements[j];
            if(!used[j] && m.donor==-1 && m.recipient==map[x.cell_id] && m.phase==x.phase &&
               same(m.mass_kg,x.mass_kg) && same(m.temperature_k,x.temperature_k)) {
                used[j]=true;found=true;imports[x.cell_id].push_back({m.mass_kg,m.carried_enthalpy_j});break;
            }
        }
        need(found,"mass_protocol_refusal","import-to-movement identity missing");
    }
    for(const auto& x:request.initial_liquid_withdrawals) {
        bool found=false;
        for(std::size_t j=0;j<used.size();++j) {
            const auto& m=result.movements[j];
            if(!used[j] && m.donor==map[x.cell_id] && m.recipient==-1 && m.phase==a::Phase::liquid && same(m.mass_kg,x.mass_kg)) {
                used[j]=true;found=true;withdrawals[x.cell_id].push_back({m.mass_kg,m.carried_enthalpy_j});
                r.private_liquid_outbox.push_back({x.id,x.cell_id,m.mass_kg,m.carried_enthalpy_j,j});break;
            }
        }
        need(found,"mass_protocol_refusal","withdrawal-to-movement identity missing");
    }
    need(std::all_of(used.begin(),used.end(),[](bool v){return v;}),"mass_protocol_refusal","unlinked mass movement");
    auto& jump=r.jump;jump.inherited_error_j=initial.canonical_energy_error_j;I defect=b::point(0);
    for(std::size_t i=0;i<n;++i) if(exposed(surface.cells()[i])) {
        const auto& before=initial.state[i];const auto& after=r.private_prefix.state[i];
        const double e=b::div(b::point(jump.inherited_error_j),b::point(props.columns[i].area_m2)).upper;
        jump.cell_ids.push_back(static_cast<int>(i));
        jump.scalar_certificates.push_back(certify_canonical_jump(props.water,scalar_column(props.columns[i]),
            before.water_mass_kg_m2,{before.enthalpy_j_m2,0},after.water_mass_kg_m2,{after.enthalpy_j_m2,0},
            e,imports[i],withdrawals[i],std::numeric_limits<double>::max()));
        const auto& cert=jump.scalar_certificates.back();
        need(cert.accepted,"source_error_refusal",cert.failure_code+": "+cert.detail);
        // Charge global inherited E once; e_i is only a component domain radius.
        defect=b::add(defect,b::mul(b::point(props.columns[i].area_m2),b::point(cert.jump_defect_upper_j_m2)));
    }
    jump.weighted_jump_defect_upper_j=defect.upper;
    jump.final_error_j=b::add(b::point(jump.inherited_error_j),b::point(defect.upper)).upper;
    need(jump.final_error_j<=B,"cumulative_error_budget","source jump exceeds global error budget");
    jump.after_domain=domain(props,r.private_prefix.state,jump.final_error_j,std::vector<double>(n,0),0);
    require_domain(jump.after_domain);jump.available=true;
    r.private_prefix.canonical_energy_error_j=jump.final_error_j;
    r.private_prefix_error_available=true;
    r.thermal_initial=r.private_prefix;
}
EnthalpyMeshDiscreteLedger ledger(const EnthalpyMeshOwnerReceipt& r) {
    EnthalpyMeshDiscreteLedger x;
    const auto& anchor=r.thermal_initial?*r.thermal_initial:r.initial;
    for(std::size_t i=0;i<r.properties.columns.size();++i) {
        const I area=b::point(r.properties.columns[i].area_m2);
        x.total_mass_change_kg=b::add(x.total_mass_change_kg,b::mul(area,b::sub(
            b::point(r.private_prefix.state[i].water_mass_kg_m2),b::point(r.initial.state[i].water_mass_kg_m2))));
        x.total_storage_j=b::add(x.total_storage_j,b::mul(area,b::sub(
            b::point(r.private_prefix.state[i].enthalpy_j_m2),b::point(r.initial.state[i].enthalpy_j_m2))));
        x.source_storage_j=b::add(x.source_storage_j,b::mul(area,b::sub(
            b::point(anchor.state[i].enthalpy_j_m2),b::point(r.initial.state[i].enthalpy_j_m2))));
        x.thermal_storage_j=b::add(x.thermal_storage_j,b::mul(area,b::sub(
            b::point(r.private_prefix.state[i].enthalpy_j_m2),b::point(anchor.state[i].enthalpy_j_m2))));
    }
    if(r.mass_receipt) for(const auto& m:r.mass_receipt->movements) {
        const double sign=m.donor==-1?1:-1;
        x.external_mass_kg=b::add(x.external_mass_kg,b::point(sign*m.mass_kg));
        x.external_enthalpy_j=b::add(x.external_enthalpy_j,b::point(sign*m.carried_enthalpy_j));
    }
    for(const auto& trial:r.trials) if(trial.accepted_for_private_carry) {
        const auto& step=*trial.receipt;const auto& q=*step.request;
        for(std::size_t i=0;i<r.properties.columns.size();++i) {
            const I area_time=b::mul(b::point(r.properties.columns[i].area_m2),b::point(q.options.duration_seconds));
            x.absorbed_shortwave_j=b::add(x.absorbed_shortwave_j,b::mul(area_time,b::point(q.absorbed_shortwave_w_m2[i])));
            x.backward_euler_emission_j=b::add(x.backward_euler_emission_j,b::mul(area_time,step.candidate_field.emitted_longwave_w_m2[i]));
        }
    }
    x.mass_projection_residual_kg=b::sub(x.total_mass_change_kg,x.external_mass_kg);
    x.source_projection_residual_j=b::sub(x.source_storage_j,x.external_enthalpy_j);
    x.balance_residual_j=b::add(b::sub(b::sub(x.total_storage_j,x.external_enthalpy_j),x.absorbed_shortwave_j),x.backward_euler_emission_j);
    return x;
}
struct Bundle {
    EnthalpyMeshRestart restart;
    std::size_t committed_intervals=0;
    std::shared_ptr<const EnthalpyMeshOwnerReceipt> last;
};
} // namespace

struct EnthalpyMeshIntervalCandidate::Data {
    std::shared_ptr<const int> owner;
    std::shared_ptr<const Bundle> base,replacement;
};
EnthalpyMeshIntervalCandidate::EnthalpyMeshIntervalCandidate(std::shared_ptr<const Data> data):data_(std::move(data)){}
const EnthalpyMeshOwnerReceipt& EnthalpyMeshIntervalCandidate::receipt()const{return *data_->replacement->last;}
struct EnthalpyMeshOwner::Impl {
    TerrestrialSurfaceSnapshot surface;
    EnthalpyMeshProperties properties;
    double budget;
    EnthalpyMeshOwnerLimits limits;
    EnthalpyMeshOwnerWork work;
    std::shared_ptr<const int> anchor=std::make_shared<const int>(0);
    std::shared_ptr<const Bundle> accepted;
    Impl(TerrestrialSurfaceSnapshot s,EnthalpyMeshProperties p,double B,EnthalpyMeshOwnerLimits l)
        :surface(std::move(s)),properties(std::move(p)),budget(B),limits(l){}
};
EnthalpyMeshOwner::EnthalpyMeshOwner(TerrestrialSurfaceSnapshot surface,EnthalpyMeshProperties props,
    EnthalpyMeshRestart initial,double budget,EnthalpyMeshOwnerLimits limits)
    :impl_(std::make_unique<Impl>(std::move(surface),std::move(props),budget,limits)) {
    arithmetic();limits_valid(limits);positive(budget,"positive global error budget required");
    const auto& cs=impl_->surface.cells();const auto& p=impl_->properties;const auto n=cs.size();
    need(n>0 && n<=limits.max_cells && p.columns.size()==n && initial.state.size()==n && p.edges.size()<=limits.max_edges,
         "invalid_restart","bounded complete mesh/state coverage required");
    for(double v:{p.reference_water_density_kg_m3,p.year_duration_seconds,p.water.freezing_temperature_k,
                  p.water.solid_heat_capacity_j_kg_k,p.water.liquid_heat_capacity_j_kg_k,p.water.latent_heat_j_kg})
        positive(v,"positive finite physical properties required");
    need(finite(initial.elapsed_seconds) && initial.elapsed_seconds>=0 && finite(initial.canonical_energy_error_j) &&
         initial.canonical_energy_error_j>=0 && initial.canonical_energy_error_j<=budget,"invalid_restart","clock or global inherited error");
    for(std::size_t i=0;i<n;++i) {
        const auto& c=p.columns[i];const auto& x=initial.state[i];
        need(same(c.area_m2,cs[i].area_km2*1e6) && finite(c.area_m2) && c.area_m2>0 &&
             finite(c.heat_capacity_j_m2_k) && c.heat_capacity_j_m2_k>0 && finite(c.longwave_emissivity) &&
             c.longwave_emissivity>=0 && c.longwave_emissivity<=1,"invalid_restart","physical column or canonical surface area mismatch");
        need(finite(x.water_mass_kg_m2) && x.water_mass_kg_m2>=0 && finite(x.enthalpy_j_m2) &&
             (exposed(cs[i]) || x.water_mass_kg_m2==0),"invalid_restart","invalid retained water or enthalpy; wet retained W must be zero");
    }
    std::set<std::pair<int,int>> edges;
    for(const auto& e:p.edges)
        need(e.first_cell>=0 && e.second_cell>e.first_cell && static_cast<std::size_t>(e.second_cell)<n &&
             finite(e.conductance_w_k) && e.conductance_w_k>0 && edges.insert({e.first_cell,e.second_cell}).second,
             "invalid_restart","invalid canonical positive mesh edge");
    need(initial.consumed_event_ids.size()<=limits.max_consumed_event_ids &&
         initial.forcing_history.size()<=limits.max_committed_intervals &&
         initial.forcing_history.size()<=limits.max_stored_forcing_values/n,"invalid_restart","history limits");
    std::set<std::string> ids;
    for(const auto& id:initial.consumed_event_ids) {identifier(id,limits.max_identifier_bytes);need(ids.insert(id).second,"invalid_restart","duplicate consumed event");}
    ids.clear();
    for(std::size_t i=0;i<initial.forcing_history.size();++i) {
        const auto& f=initial.forcing_history[i];forcing_valid(f,n,limits.max_identifier_bytes);
        need(ids.insert(f.id).second && f.begin_seconds<initial.elapsed_seconds,"invalid_restart","duplicate or unused future forcing history");
        for(std::size_t j=0;j<i;++j) compare_forcing(f,initial.forcing_history[j]);
    }
    require_domain(domain(p,initial.state,initial.canonical_energy_error_j,std::vector<double>(n,0),0));
    impl_->accepted=std::make_shared<const Bundle>(Bundle{std::move(initial),0,{}});
}
EnthalpyMeshOwner::~EnthalpyMeshOwner()=default;
EnthalpyMeshOwner::EnthalpyMeshOwner(EnthalpyMeshOwner&&)noexcept=default;
EnthalpyMeshOwner& EnthalpyMeshOwner::operator=(EnthalpyMeshOwner&&)noexcept=default;
const TerrestrialSurfaceSnapshot& EnthalpyMeshOwner::surface()const{return impl_->surface;}
const EnthalpyMeshProperties& EnthalpyMeshOwner::properties()const{return impl_->properties;}
const EnthalpyMeshRestart& EnthalpyMeshOwner::restart()const{return impl_->accepted->restart;}
const EnthalpyMeshOwnerLimits& EnthalpyMeshOwner::limits()const{return impl_->limits;}
double EnthalpyMeshOwner::maximum_cumulative_error_j()const{return impl_->budget;}
const EnthalpyMeshOwnerWork& EnthalpyMeshOwner::work_meter()const{return impl_->work;}
const EnthalpyMeshOwnerReceipt* EnthalpyMeshOwner::last_receipt()const{return impl_->accepted->last.get();}

EnthalpyMeshPreparation EnthalpyMeshOwner::prepare(const EnthalpyMeshIntervalRequest& request) {
    const auto base=impl_->accepted;const auto& initial=base->restart;const auto& props=impl_->properties;
    const auto& cs=impl_->surface.cells();const auto n=cs.size();const auto& limits=impl_->limits;auto& work=impl_->work;
    const double B=impl_->budget;
    EnthalpyMeshOwnerReceipt r;r.surface_revision=impl_->surface.surface_revision();r.properties=props;r.limits=limits;
    r.maximum_cumulative_error_j=B;r.surface_cells=cs;r.initial=initial;r.private_prefix=initial;r.work_before=work;
    r.private_prefix_error_available=true;
    try {
        increment(work.prepare_attempts);arithmetic();
        need(request.imports.size()<=limits.max_events_per_interval && request.initial_liquid_withdrawals.size()<=limits.max_events_per_interval &&
             request.forcing.absorbed_shortwave_w_m2.size()<=limits.max_cells && request.forcing.id.size()<=limits.max_identifier_bytes,
             "invalid_request","request retention bound");
        for(const auto& x:request.imports) need(x.id.size()<=limits.max_identifier_bytes,"invalid_request","import identifier retention bound");
        for(const auto& x:request.initial_liquid_withdrawals) need(x.id.size()<=limits.max_identifier_bytes,"invalid_request","withdrawal identifier retention bound");
        r.request=request;
        need(work.prepare_attempts<=limits.max_prepare_attempts,"work_cap","prepare attempt cap");
        need(request.expected_revision==initial.revision,"stale_revision","request revision mismatch");
        need(initial.revision<std::numeric_limits<std::uint64_t>::max() && base->committed_intervals<limits.max_committed_intervals,
             "interval_cap","revision or committed interval cap");
        const double dt=duration(initial.elapsed_seconds,request.end_seconds);
        const double quantum=std::nextafter(request.end_seconds,std::numeric_limits<double>::infinity())-request.end_seconds;
        positive(quantum,"positive finite common clock quantum required");
        const auto begin_tick=ticks(initial.elapsed_seconds,quantum),N=ticks(dt,quantum);
        (void)ticks(request.end_seconds,quantum);r.clock_quantum_seconds=quantum;
        forcing_valid(request.forcing,n,limits.max_identifier_bytes);
        need(request.forcing.begin_seconds<=initial.elapsed_seconds && request.end_seconds<=request.forcing.end_seconds,
             "forcing_refusal","interval crosses forcing boundary");
        bool known=false;
        for(const auto& old:initial.forcing_history) {compare_forcing(request.forcing,old);known=known || old.id==request.forcing.id;}
        need(known || initial.forcing_history.size()<limits.max_committed_intervals,"forcing_refusal","forcing history cap");
        need(known || initial.forcing_history.size()<limits.max_stored_forcing_values/n,
             "forcing_refusal","stored full-mesh forcing value cap");
        if(request.maximum_thermal_error_increment_j)
            positive(*request.maximum_thermal_error_increment_j,"positive finite thermal increment allowance required");
        const auto event_count=request.imports.size()+request.initial_liquid_withdrawals.size();
        need(event_count<=limits.max_events_per_interval && event_count<=limits.max_consumed_event_ids-initial.consumed_event_ids.size(),
             "event_cap","event/retained identifier limit");
        std::set<std::string> ids(initial.consumed_event_ids.begin(),initial.consumed_event_ids.end());
        const auto event=[&](const std::string& id,int cell,double mass) {
            identifier(id,limits.max_identifier_bytes);need(ids.insert(id).second,"duplicate_event","event already consumed or repeated");
            need(cell>=0 && static_cast<std::size_t>(cell)<n && exposed(cs[cell]),"invalid_event","wet or unknown source cell");
            positive(mass,"positive finite event mass required");
        };
        for(const auto& x:request.imports) {
            event(x.id,x.cell_id,x.mass_kg);
            need(finite(x.temperature_k) && x.temperature_k>=0 &&
                 ((x.phase==a::Phase::solid && x.temperature_k<=props.water.freezing_temperature_k) ||
                  (x.phase==a::Phase::liquid && x.temperature_k>=props.water.freezing_temperature_k)),
                 "invalid_event","import phase/temperature mismatch");
        }
        for(const auto& x:request.initial_liquid_withdrawals) event(x.id,x.cell_id,x.mass_kg);
        const auto& o=request.options;
        positive(o.maximum_step_seconds,"positive maximum step required");positive(o.maximum_stage_error_j,"positive stage budget required");
        need(finite(o.minimum_step_seconds) && o.minimum_step_seconds>=0,"invalid_request","minimum step");
        const auto max_ticks=static_cast<std::uint64_t>(std::floor(std::min(dt,o.maximum_step_seconds)/quantum));
        const auto min_ticks=o.minimum_step_seconds==0?std::uint64_t{1}:ticks(o.minimum_step_seconds,quantum);
        need(min_ticks>0 && max_ticks>=min_ticks,"clock_refusal","step limits contain no permitted tick");
        need(o.maximum_attempts>0 && o.maximum_attempts<=limits.max_thermal_attempts &&
             o.maximum_accepted_steps>0 && o.maximum_accepted_steps<=limits.max_accepted_steps &&
             o.maximum_sweeps>=0 && o.maximum_sweeps<=512 && o.maximum_coordinate_iterations>0 && o.maximum_coordinate_iterations<=64 &&
             o.maximum_scalar_evaluations>0 && o.maximum_scalar_evaluations<=16777216 && o.reconstruction_leaves>0 &&
             o.reconstruction_leaves<=64 && (o.reconstruction_leaves&(o.reconstruction_leaves-1))==0,"work_cap","thermal work policy");
        const std::uint64_t field_cap=1+o.maximum_sweeps+o.reconstruction_leaves;
        need(o.maximum_attempts*o.maximum_scalar_evaluations<=limits.max_scalar_evaluations_per_prepare &&
             o.maximum_attempts*field_cap<=limits.max_field_evaluations_per_prepare &&
             o.maximum_attempts*n*static_cast<std::size_t>(o.reconstruction_leaves)<=limits.max_retained_cell_leaves &&
             o.maximum_attempts*props.edges.size()*static_cast<std::size_t>(o.reconstruction_leaves)<=limits.max_retained_edge_leaves,
             "work_cap","complete thermal/certificate reservation exceeds interval limits");
        // Validate/reserve the complete potential schedule before an actual A call.
        if(event_count) need(terrestrial_water_capability().available,"capability_unavailable",terrestrial_water_capability().reason);
        r.trials.reserve(o.maximum_attempts);
        if(event_count) apply_sources(request,impl_->surface,props,B,work,r);
        const double E0=r.private_prefix.canonical_energy_error_j;
        const double available=std::max(0.0,b::sub(b::point(B),b::point(E0)).lower);
        const double headroom=request.maximum_thermal_error_increment_j
            ? std::min(available,*request.maximum_thermal_error_increment_j) : available;
        std::uint64_t elapsed=0,proposed=std::min(max_ticks,N);std::size_t accepted_steps=0;
        while(elapsed<N) {
            need(r.trials.size()<o.maximum_attempts && accepted_steps<o.maximum_accepted_steps,"work_cap","thermal attempt or accepted-step cap exhausted");
            const auto count=std::min(proposed,N-elapsed);
            need(count>=min_ticks,"minimum_step_refusal","remaining duration below minimum tick count");
            const double h=static_cast<double>(count)*quantum,start=static_cast<double>(begin_tick+elapsed)*quantum;
            const double end=static_cast<double>(begin_tick+elapsed+count)*quantum;
            need(same(duration(start,end),h),"clock_refusal","derived step does not close exactly");
            const double quota=b::mul(b::point(headroom),b::div(b::point(static_cast<double>(count)),b::point(static_cast<double>(N)))).lower;
            need(finite(quota) && quota>0,"error_allocation_refused","no positive representable global error allocation");
            r.trials.emplace_back();auto& trial=r.trials.back();
            trial.begin_tick=begin_tick+elapsed;trial.duration_ticks=count;trial.interval_ticks=N;trial.start_seconds=start;trial.end_seconds=end;
            trial.interval_initial_error_j=E0;trial.headroom_lower_j=headroom;trial.offered_error_j=quota;
            const double E=r.private_prefix.canonical_energy_error_j;trial.inherited_error_j=E;
            trial.before_domain=domain(props,r.private_prefix.state,E,request.forcing.absorbed_shortwave_w_m2,h);require_domain(trial.before_domain);
            EnthalpyMeshRequest in;in.water=props.water;in.columns=props.columns;in.edges=props.edges;
            for(const auto& x:r.private_prefix.state) {in.water_mass_kg_m2.push_back(x.water_mass_kg_m2);in.initial_enthalpy_j_m2.push_back(x.enthalpy_j_m2);}
            in.absorbed_shortwave_w_m2=request.forcing.absorbed_shortwave_w_m2;
            in.options={h,o.maximum_stage_error_j,quota,o.maximum_sweeps,o.maximum_coordinate_iterations,o.maximum_scalar_evaluations,o.reconstruction_leaves};
            increment(work.reserved_scalar_evaluations,o.maximum_scalar_evaluations);increment(work.reserved_field_evaluations,field_cap);
            increment(work.thermal_calls_started);trial.call_started=true;
            try {trial.receipt=advance_enthalpy_mesh(in);} catch(...) {work.observed_counts_complete=false;throw;}
            increment(work.thermal_calls_returned);const auto& result=*trial.receipt;
            const bool counts=result.scalar_evaluations<=o.maximum_scalar_evaluations && result.field_evaluations<=field_cap &&
                result.sweeps_started>=0 && result.sweeps_started<=o.maximum_sweeps && result.coordinate_solves_started>=0 &&
                static_cast<std::size_t>(result.coordinate_solves_started)<=n*static_cast<std::size_t>(o.maximum_sweeps) &&
                result.leaves_started>=0 && result.leaves_started<=o.reconstruction_leaves;
            if(!counts) work.observed_counts_complete=false;
            need(counts,"thermal_protocol_refusal","observed work exceeds reservation");
            increment(work.scalar_evaluations,result.scalar_evaluations);increment(work.field_evaluations,result.field_evaluations);
            increment(work.sweeps_started,result.sweeps_started);increment(work.coordinate_solves_started,result.coordinate_solves_started);
            increment(work.reconstruction_leaves_started,result.leaves_started);
            if(!result.accepted) {
                trial.refusal_code=result.failure_code;
                need(result.failure_code=="endpoint_budget_refusal" || result.failure_code=="stage_budget_refusal" ||
                     result.failure_code=="stage_stagnation_refusal","thermal_refused",result.failure_code+": "+result.detail);
            } else {
                need(result.request && result.final_enthalpy_j_m2 && result.final_enthalpy_j_m2->size()==n &&
                     result.stage_accepted && result.stage_error_available && result.endpoint_error_available &&
                     result.stage_error_upper_j<=o.maximum_stage_error_j && result.local_endpoint_error_upper_j<=quota &&
                     finite(result.local_endpoint_error_upper_j) && result.local_endpoint_error_upper_j>=0 &&
                     same(result.request->options.duration_seconds,h),"thermal_protocol_refusal","accepted mesh proof or duration missing");
                trial.proposed_final_error_j=b::add(b::point(E),b::point(result.local_endpoint_error_upper_j)).upper;
                trial.charged_increment_j=b::sub(b::point(trial.proposed_final_error_j),b::point(E));
                trial.charged_increment_available=true;
                need(trial.proposed_final_error_j>=E && trial.charged_increment_j.upper>=0,
                     "thermal_protocol_refusal","invalid global error increment");
                if(trial.proposed_final_error_j>B || trial.charged_increment_j.upper>quota) trial.refusal_code="rounded_charge_refusal";
                else {
                    auto next=r.private_prefix.state;
                    for(std::size_t i=0;i<n;++i) next[i].enthalpy_j_m2=(*result.final_enthalpy_j_m2)[i];
                    trial.after_domain=domain(props,next,trial.proposed_final_error_j,std::vector<double>(n,0),0);
                    if(!trial.after_domain.proved) {
                        trial.refusal_code=trial.after_domain.failure_code;
                        need(trial.refusal_code=="uncertain_physical_domain","domain_refusal",trial.after_domain.detail);
                    }
                    else {
                        r.private_prefix.state=std::move(next);r.private_prefix.canonical_energy_error_j=trial.proposed_final_error_j;
                        r.private_prefix.elapsed_seconds=end;elapsed+=count;++accepted_steps;trial.accepted_for_private_carry=true;
                    }
                }
            }
            if(trial.accepted_for_private_carry) proposed=std::min(max_ticks,count*2);
            else {need(count/2>=min_ticks,"minimum_step_refusal","rejected step cannot halve on permitted lattice");proposed=count/2;}
        }
        need(same(r.private_prefix.elapsed_seconds,request.end_seconds),"clock_refusal","mesh did not reach common endpoint");
        r.discrete_ledger=ledger(r);
        r.projection=project_terrestrial_liquid_supply(impl_->surface,r.private_liquid_outbox,dt,props.reference_water_density_kg_m3,props.year_duration_seconds);
        r.private_prefix.revision=initial.revision+1;r.private_prefix.consumed_event_ids.assign(ids.begin(),ids.end());
        if(!known) r.private_prefix.forcing_history.push_back(request.forcing);
        r.final=r.private_prefix;r.prepared=true;
    } catch(const std::bad_alloc&) {throw;
    } catch(const TerrestrialWaterError& e) {r.failure_code=e.code;r.detail=e.what();
    } catch(const std::exception& e) {r.failure_code="preparation_refused";r.detail=e.what();}
    if(!r.prepared) r.final.reset();
    if(r.request) r.observed_request_after=request;
    r.observed_accepted_after=impl_->accepted->restart;r.work_after=work;
    const auto diagnostic=std::make_shared<const EnthalpyMeshOwnerReceipt>(std::move(r));
    if(!diagnostic->prepared) return {diagnostic,std::nullopt};
    const auto replacement=std::make_shared<const Bundle>(Bundle{*diagnostic->final,base->committed_intervals+1,diagnostic});
    const auto data=std::make_shared<const EnthalpyMeshIntervalCandidate::Data>(EnthalpyMeshIntervalCandidate::Data{impl_->anchor,base,replacement});
    return {diagnostic,EnthalpyMeshIntervalCandidate(data)};
}
void EnthalpyMeshOwner::commit(const EnthalpyMeshIntervalCandidate& candidate) {
    need(candidate.data_ && candidate.data_->owner==impl_->anchor,"foreign_candidate","candidate owner mismatch");
    need(candidate.data_->base==impl_->accepted,"stale_candidate","accepted restart changed");
    auto replacement=candidate.data_->replacement;impl_->accepted.swap(replacement);
}
} // namespace magic_geo::detail
