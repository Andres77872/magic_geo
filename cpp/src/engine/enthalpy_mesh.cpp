#include "enthalpy_mesh.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <algorithm>
#include <cfenv>
#include <cmath>
#include <limits>
#include <set>
#include <stdexcept>
#include <utility>

namespace magic_geo::detail {
namespace {
namespace b = phase_segment_prototype::bounds;
using I = EnthalpyMeshInterval;
constexpr double sigma = 5.670374419e-8;
constexpr std::size_t cell_cap = 16384, edge_cap = 131072;
struct Refusal : std::runtime_error {
    std::string code;
    Refusal(const char* c,const char* why) : std::runtime_error(why),code(c) {}
};
void need(bool ok,const char* code,const char* why) { if(!ok) throw Refusal(code,why); }
bool finite(double x) { return std::isfinite(x); }
void arithmetic() {
    need(std::numeric_limits<double>::is_iec559 && std::numeric_limits<double>::digits==53 &&
         std::fegetround()==FE_TONEAREST,"capability_unavailable","nearest binary64 arithmetic required");
    volatile double normal=std::numeric_limits<double>::min(), tiny=std::numeric_limits<double>::denorm_min();
    volatile double tenth=.1, one=1;
    volatile double a=normal*tenth, z=tiny*one;
    need(a>0 && z>0,"capability_unavailable","gradual underflow required");
}
I capacity(const EnthalpyMeshRequest& q,std::size_t i,bool liquid) {
    return b::add(b::point(q.columns[i].heat_capacity_j_m2_k),b::mul(b::point(q.water_mass_kg_m2[i]),
        b::point(liquid?q.water.liquid_heat_capacity_j_kg_k:q.water.solid_heat_capacity_j_kg_k)));
}
I latent(const EnthalpyMeshRequest& q,std::size_t i) {
    return b::mul(b::point(q.water_mass_kg_m2[i]),b::point(q.water.latent_heat_j_kg));
}
I temperature(const EnthalpyMeshRequest& q,std::size_t i,I H) {
    const I cold{std::min(0.0,H.lower),std::min(0.0,H.upper)};
    const I excess=b::sub(H,latent(q,i));
    const I warm{std::max(0.0,excess.lower),std::max(0.0,excess.upper)};
    const I value=b::add(b::point(q.water.freezing_temperature_k),
        b::add(b::div(cold,capacity(q,i,false)),b::div(warm,capacity(q,i,true))));
    // Called only for a proved physical point, or an enclosure of the declared
    // linear curve between two proved physical points. Intersect the *range*,
    // without changing the raw state or assuming every rounded box point exists.
    need(value.upper>=0,"physical_domain_refusal","temperature enclosure has no physical value");
    return b::checked(std::max(0.0,value.lower),value.upper);
}
EnthalpyMeshField field(const EnthalpyMeshRequest& q,const std::vector<I>& H,EnthalpyMeshReceipt& r) {
    ++r.field_evaluations;
    EnthalpyMeshField f;
    const auto n=q.columns.size();
    f.temperature_k.resize(n); f.emitted_longwave_w_m2.resize(n);
    f.heat_convergence_w_m2.assign(n,b::point(0)); f.net_heating_w_m2.resize(n);
    for(std::size_t i=0;i<n;++i) {
        f.temperature_k[i]=temperature(q,i,H[i]);
        f.emitted_longwave_w_m2[i]=b::mul(b::point(q.columns[i].longwave_emissivity),
            b::mul(b::point(sigma),b::fourth(f.temperature_k[i])));
    }
    for(const auto& e:q.edges) {
        const I watts=b::mul(b::point(e.conductance_w_k),
            b::sub(f.temperature_k[e.second_cell],f.temperature_k[e.first_cell]));
        f.edge_heat_w.push_back(watts);
        // A single ideal exchange occurs with opposite signs. Interval node
        // sums can have aggregation width; no cancellation or balancing heat
        // is used to reduce the absolute residual certificate.
        f.heat_convergence_w_m2[e.first_cell]=b::add(f.heat_convergence_w_m2[e.first_cell],watts);
        f.heat_convergence_w_m2[e.second_cell]=b::sub(f.heat_convergence_w_m2[e.second_cell],watts);
    }
    for(std::size_t i=0;i<n;++i) {
        f.heat_convergence_w_m2[i]=b::div(f.heat_convergence_w_m2[i],b::point(q.columns[i].area_m2));
        f.net_heating_w_m2[i]=b::add(b::sub(b::point(q.absorbed_shortwave_w_m2[i]),f.emitted_longwave_w_m2[i]),
            f.heat_convergence_w_m2[i]);
    }
    return f;
}
std::vector<I> points(const std::vector<double>& xs) {
    std::vector<I> out; out.reserve(xs.size());
    for(double x:xs) out.push_back(b::point(x));
    return out;
}
double weighted_bound(const EnthalpyMeshRequest& q,const std::vector<I>& residual) {
    I sum=b::point(0);
    for(std::size_t i=0;i<residual.size();++i)
        sum=b::add(sum,b::mul(b::point(q.columns[i].area_m2),b::point(b::absmax(residual[i]))));
    return sum.upper;
}
void evaluate_stage(const EnthalpyMeshRequest& q,EnthalpyMeshReceipt& r) {
    r.candidate_field=field(q,points(r.candidate_enthalpy_j_m2),r);
    r.stage_residual_j_m2.resize(q.columns.size());
    for(std::size_t i=0;i<q.columns.size();++i)
        r.stage_residual_j_m2[i]=b::sub(b::sub(b::point(r.candidate_enthalpy_j_m2[i]),b::point(q.initial_enthalpy_j_m2[i])),
            b::mul(b::point(q.options.duration_seconds),r.candidate_field.net_heating_w_m2[i]));
    r.stage_error_upper_j=weighted_bound(q,r.stage_residual_j_m2);
    r.stage_error_available=true;
    r.stage_accepted=r.stage_error_upper_j<=q.options.maximum_stage_error_j;
    r.sweeps.push_back({r.sweeps_started,r.scalar_evaluations,r.stage_error_upper_j});
}
long double proposal_temperature(const EnthalpyMeshRequest& q,std::size_t i,long double H) {
    const long double W=q.water_mass_kg_m2[i], C=q.columns[i].heat_capacity_j_m2_k;
    return q.water.freezing_temperature_k+std::min(H,0.0L)/(C+W*q.water.solid_heat_capacity_j_kg_k)+
        std::max(H-W*q.water.latent_heat_j_kg,0.0L)/(C+W*q.water.liquid_heat_capacity_j_kg_k);
}
struct Scalar { long double residual,derivative; };
double coordinate(const EnthalpyMeshRequest& q,std::size_t i,long double neighbors,long double degree,
                  double low,double high,double guess,EnthalpyMeshReceipt& r) {
    ++r.coordinate_solves_started;
    const long double h=q.options.duration_seconds, area=q.columns[i].area_m2;
    const long double right=q.initial_enthalpy_j_m2[i]+h*q.absorbed_shortwave_w_m2[i]+h*neighbors/area;
    const auto evaluate=[&](double H) {
        need(r.scalar_evaluations<q.options.maximum_scalar_evaluations,"work_cap","scalar evaluation cap exhausted");
        ++r.scalar_evaluations;
        const long double T=proposal_temperature(q,i,H), square=T*T;
        const long double W=q.water_mass_kg_m2[i], C=q.columns[i].heat_capacity_j_m2_k;
        const long double slope=W==0 ? 1/C : H<0 ? 1/(C+W*q.water.solid_heat_capacity_j_kg_k) :
            static_cast<long double>(H)>W*q.water.latent_heat_j_kg ? 1/(C+W*q.water.liquid_heat_capacity_j_kg_k) : 0;
        const long double radiation=q.columns[i].longwave_emissivity*static_cast<long double>(sigma);
        const Scalar value{H+h*(radiation*square*square+degree*T/area)-right,
            1+h*(4*radiation*T*square+degree/area)*slope};
        need(std::isfinite(value.residual) && std::isfinite(value.derivative) && value.derivative>=1,
             "proposal_refusal","nonfinite scalar proposal");
        return value;
    };
    double x=std::clamp(guess,low,high), best=x;
    long double best_abs=std::numeric_limits<long double>::infinity();
    for(int k=0;k<q.options.maximum_coordinate_iterations;++k) {
        const Scalar v=evaluate(x);
        if(std::abs(v.residual)<best_abs) {best=x;best_abs=std::abs(v.residual);}
        if(v.residual==0) break;
        if(v.residual<0) low=x; else high=x;
        if(std::nextafter(low,high)>=high) break;
        const long double newton=static_cast<long double>(x)-v.residual/v.derivative;
        double next=static_cast<double>(newton);
        if(!finite(next) || next<=low || next>=high || next==x)
            next=static_cast<double>(static_cast<long double>(low)+(static_cast<long double>(high)-low)/2);
        if(next<=low || next>=high || next==x) break;
        x=next;
    }
    return best;
}
void reconstruction(const EnthalpyMeshRequest& q,EnthalpyMeshReceipt& r) {
    const auto n=q.columns.size(); const int N=q.options.reconstruction_leaves;
    const I leaf_duration=b::div(b::point(q.options.duration_seconds),b::point(N));
    std::vector<I> change(n), derivative(n);
    for(std::size_t i=0;i<n;++i) {
        change[i]=b::sub(b::point(r.candidate_enthalpy_j_m2[i]),b::point(q.initial_enthalpy_j_m2[i]));
        derivative[i]=b::div(change[i],b::point(N));
    }
    I total=b::point(0);
    for(int j=0;j<N;++j) {
        ++r.leaves_started;
        r.leaves.emplace_back();auto& leaf=r.leaves.back();leaf.index=j;
        leaf.enthalpy_range_j_m2.resize(n);leaf.residual_integral_j_m2.resize(n);
        // j/N and (j+1)/N are exact binary dyadics. These are enclosures of
        // ONE exact raw-endpoint line, not independently rounded curve nodes.
        for(std::size_t i=0;i<n;++i) {
            const I left=b::add(b::point(q.initial_enthalpy_j_m2[i]),b::mul(change[i],b::point(static_cast<double>(j)/N)));
            const I right=b::add(b::point(q.initial_enthalpy_j_m2[i]),b::mul(change[i],b::point(static_cast<double>(j+1)/N)));
            leaf.enthalpy_range_j_m2[i]=b::hull(left,right);
        }
        leaf.field=field(q,leaf.enthalpy_range_j_m2,r);
        for(std::size_t i=0;i<n;++i)
            leaf.residual_integral_j_m2[i]=b::sub(derivative[i],b::mul(leaf_duration,leaf.field.net_heating_w_m2[i]));
        leaf.weighted_residual_upper_j=weighted_bound(q,leaf.residual_integral_j_m2);
        leaf.complete=true;
        total=b::add(total,b::point(leaf.weighted_residual_upper_j));
    }
    r.local_endpoint_error_upper_j=total.upper;r.endpoint_error_available=true;
}
} // namespace

EnthalpyMeshReceipt advance_enthalpy_mesh(const EnthalpyMeshRequest& q) {
    EnthalpyMeshReceipt r;
    try {
        const auto n=q.columns.size();
        need(n>0 && n<=cell_cap && q.edges.size()<=edge_cap && q.water_mass_kg_m2.size()<=cell_cap &&
             q.initial_enthalpy_j_m2.size()<=cell_cap && q.absorbed_shortwave_w_m2.size()<=cell_cap,
             "invalid_input","request retention cap");
        r.request=q;arithmetic();
        need(q.water_mass_kg_m2.size()==n && q.initial_enthalpy_j_m2.size()==n && q.absorbed_shortwave_w_m2.size()==n,
             "invalid_input","complete column/state/source coverage required");
        for(double x:{q.water.freezing_temperature_k,q.water.solid_heat_capacity_j_kg_k,
                      q.water.liquid_heat_capacity_j_kg_k,q.water.latent_heat_j_kg})
            need(finite(x) && x>0,"invalid_input","positive finite water parameters required");
        const auto& o=q.options;
        for(double x:{o.duration_seconds,o.maximum_stage_error_j,o.maximum_endpoint_error_j})
            need(finite(x) && x>0,"invalid_input","positive finite duration and independent budgets required");
        need(o.maximum_sweeps>=0 && o.maximum_sweeps<=512 && o.maximum_coordinate_iterations>0 &&
             o.maximum_coordinate_iterations<=64 && o.maximum_scalar_evaluations>0 && o.maximum_scalar_evaluations<=16777216 &&
             o.reconstruction_leaves>0 && o.reconstruction_leaves<=64 &&
             (o.reconstruction_leaves&(o.reconstruction_leaves-1))==0,
             "work_cap","finite sweep/scalar/dyadic reconstruction caps required");
        std::set<std::pair<int,int>> seen;
        std::vector<std::vector<std::pair<std::size_t,double>>> adjacency(n);
        std::vector<long double> degrees(n,0);
        for(const auto& e:q.edges) {
            need(e.first_cell>=0 && e.second_cell>e.first_cell && static_cast<std::size_t>(e.second_cell)<n &&
                 finite(e.conductance_w_k) && e.conductance_w_k>0 && seen.insert({e.first_cell,e.second_cell}).second,
                 "invalid_input","invalid or repeated canonical positive exchange edge");
            adjacency[e.first_cell].push_back({static_cast<std::size_t>(e.second_cell),e.conductance_w_k});
            adjacency[e.second_cell].push_back({static_cast<std::size_t>(e.first_cell),e.conductance_w_k});
            degrees[e.first_cell]+=e.conductance_w_k;degrees[e.second_cell]+=e.conductance_w_k;
        }
        r.physical_floor_j_m2.resize(n);
        double initial_max=q.water.freezing_temperature_k, heating_max=0;
        for(std::size_t i=0;i<n;++i) {
            const auto& c=q.columns[i];
            need(finite(c.area_m2) && c.area_m2>0 && finite(c.heat_capacity_j_m2_k) &&
                 (c.heat_capacity_j_m2_k>0 || (o.allow_pure_water_columns && c.heat_capacity_j_m2_k==0)) &&
                 finite(c.longwave_emissivity) && c.longwave_emissivity>=0 && c.longwave_emissivity<=1 &&
                 finite(q.water_mass_kg_m2[i]) && q.water_mass_kg_m2[i]>=0 && finite(q.initial_enthalpy_j_m2[i]) &&
                 finite(q.absorbed_shortwave_w_m2[i]) && q.absorbed_shortwave_w_m2[i]>=0,
                 "invalid_input","invalid physical column, fixed water, initial enthalpy or sunlight");
            I heating_capacity=b::point(c.heat_capacity_j_m2_k);
            if(o.allow_pure_water_columns) {
                need(c.heat_capacity_j_m2_k>0 || q.water_mass_kg_m2[i]>0,
                     "invalid_input","empty zero-capacity thermal node must be removed by its owner");
                const I solid=capacity(q,i,false), liquid=capacity(q,i,true);
                need(solid.lower>0 && liquid.lower>0,"physical_domain_refusal",
                     "positive effective sensible capacities not representably proved");
                heating_capacity=b::checked(std::min(solid.lower,liquid.lower),std::min(solid.upper,liquid.upper));
            }
            r.physical_floor_j_m2[i]=b::neg(b::mul(capacity(q,i,false),b::point(q.water.freezing_temperature_k)));
            need(q.initial_enthalpy_j_m2[i]>=r.physical_floor_j_m2[i].upper,
                 "physical_domain_refusal","initial canonical enthalpy below provable physical floor");
            initial_max=std::max(initial_max,temperature(q,i,b::point(q.initial_enthalpy_j_m2[i])).upper);
            heating_max=std::max(heating_max,b::div(b::point(q.absorbed_shortwave_w_m2[i]),heating_capacity).upper);
        }
        r.physical_temperature_upper_k=b::add(b::point(initial_max),b::mul(b::point(o.duration_seconds),b::point(heating_max))).upper;
        r.physical_domain_proved=true;
        std::vector<double> upper(n);
        for(std::size_t i=0;i<n;++i)
            upper[i]=b::add(latent(q,i),b::mul(capacity(q,i,true),
                b::sub(b::point(r.physical_temperature_upper_k),b::point(q.water.freezing_temperature_k)))).upper;
        r.candidate_enthalpy_j_m2=q.initial_enthalpy_j_m2;r.candidate_available=true;
        evaluate_stage(q,r);
        std::vector<long double> temperatures(n);
        for(std::size_t i=0;i<n;++i) temperatures[i]=proposal_temperature(q,i,r.candidate_enthalpy_j_m2[i]);
        while(!r.stage_accepted && r.sweeps_started<o.maximum_sweeps) {
            ++r.sweeps_started;
            const auto previous=r.candidate_enthalpy_j_m2;
            // A refusal during a partial sweep must not attach the previous
            // full sweep's field/certificate to changed diagnostic raw H.
            r.stage_error_available=false; r.stage_error_upper_j=0;
            r.candidate_field={}; r.stage_residual_j_m2.clear();
            for(std::size_t i=0;i<n;++i) {
                long double neighbors=0;
                for(const auto& [j,K]:adjacency[i]) neighbors+=K*temperatures[j];
                r.candidate_enthalpy_j_m2[i]=coordinate(q,i,neighbors,degrees[i],r.physical_floor_j_m2[i].upper,
                    upper[i],r.candidate_enthalpy_j_m2[i],r);
                need(r.candidate_enthalpy_j_m2[i]>=r.physical_floor_j_m2[i].upper,"physical_domain_refusal","proposal left physical domain");
                temperatures[i]=proposal_temperature(q,i,r.candidate_enthalpy_j_m2[i]);
            }
            evaluate_stage(q,r);
            need(r.stage_accepted || previous!=r.candidate_enthalpy_j_m2,"stage_stagnation_refusal","raw iterate stagnated above algebraic budget");
        }
        need(r.stage_accepted,"stage_budget_refusal","bounded sweeps did not prove algebraic stage target");
        reconstruction(q,r);
        need(r.local_endpoint_error_upper_j<=o.maximum_endpoint_error_j,"endpoint_budget_refusal","linear residual exceeds same-time endpoint target");
        r.final_enthalpy_j_m2=r.candidate_enthalpy_j_m2;r.accepted=true;
    } catch(const std::bad_alloc&) {throw;
    } catch(const Refusal& e) {r.failure_code=e.code;r.detail=e.what();
    } catch(const std::exception& e) {r.failure_code="enclosure_refusal";r.detail=e.what();}
    return r;
}
} // namespace magic_geo::detail
