#include "thermal_stage.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace higher_order_thermal_prototype {
namespace {
using W=long double;
struct Refusal:std::runtime_error { std::string code; Refusal(std::string c,const char* m):std::runtime_error(m),code(std::move(c)){} };
void require(bool b,const char* m) { if(!b) throw Refusal("invalid_input",m); }
double rep(W x) { double d=static_cast<double>(x); if(!std::isfinite(d)||(d==0&&x!=0)) throw Refusal("representation_failure","unrepresentable diagnostic/state"); return d; }
struct Eval { Flux f; W rs,ra,ts,ta,qs,qa,rounds,rounda,ds,ls,la,ab,sensible,asr; };
Eval evaluate(const StageInput& in,Energy x) {
 const auto& c=in.column; const auto& p=in.water;
 Eval e{};
 e.f.surface=cryosphere_prototype::phase_state(p,{c.area_m2,c.dry_heat_capacity_j_m2_k},{in.water_mass_kg_m2,x.surface_enthalpy_j_m2});
 const W ts=e.f.surface.temperature_k;
 const bool air=c.atmospheric_heat_capacity_j_m2_k>0;
 W ta=0;
 if(air) ta=cryosphere_prototype::phase_state(p,{c.area_m2,c.atmospheric_heat_capacity_j_m2_k},{0,x.atmospheric_energy_j_m2}).temperature_k;
 else if(x.atmospheric_energy_j_m2!=0) throw Refusal("domain_failure","airless energy is not zero");
 const W a=c.atmospheric_longwave_absorptivity,k=c.sensible_exchange_w_m2_k,sigma=sigma_w_m2_k4;
 e.ls=sigma*ts*ts*ts*ts; e.la=a*sigma*ta*ta*ta*ta; e.ab=a*e.ls;
 e.sensible=k*(ts-ta); e.asr=(1-W(c.surface_shortwave_albedo))*in.incident_shortwave_w_m2;
 const W fs=e.asr+e.la-e.ls-e.sensible,fa=e.ab-2*e.la+e.sensible;
 const W d=in.effective_duration_seconds;
 const W storageS=(W(x.surface_enthalpy_j_m2)-in.reference.surface_enthalpy_j_m2)/d;
 const W storageA=(W(x.atmospheric_energy_j_m2)-in.reference.atmospheric_energy_j_m2)/d;
 e.rs=storageS-fs; e.ra=air?storageA-fa:0;
 const W termsS=std::abs(e.asr)+e.la+e.ls+std::abs(e.sensible);
 const W termsA=e.ab+2*e.la+std::abs(e.sensible);
 e.qs=in.options.absolute_tolerance_w_m2+in.options.relative_tolerance*std::max(std::abs(storageS),termsS);
 e.qa=air?in.options.absolute_tolerance_w_m2+in.options.relative_tolerance*std::max(std::abs(storageA),termsA):0;
 const W ep=std::numeric_limits<double>::epsilon();
 e.rounds=32*ep*(std::abs(W(x.surface_enthalpy_j_m2))+std::abs(W(in.reference.surface_enthalpy_j_m2))+d*(termsS+4*(e.ls+e.la)+k*(ts+ta)));
 e.rounda=air?32*ep*(std::abs(W(x.atmospheric_energy_j_m2))+std::abs(W(in.reference.atmospheric_energy_j_m2))+d*(termsA+4*(e.ab+2*e.la)+k*(ts+ta))):0;
 e.ts=ts;e.ta=ta;
 if(in.water_mass_kg_m2==0) e.ds=1/W(c.dry_heat_capacity_j_m2_k);
 else if(x.surface_enthalpy_j_m2<0) e.ds=1/(W(c.dry_heat_capacity_j_m2_k)+W(in.water_mass_kg_m2)*p.solid_heat_capacity_j_kg_k);
 else if(W(x.surface_enthalpy_j_m2)>W(in.water_mass_kg_m2)*p.latent_heat_j_kg) e.ds=1/(W(c.dry_heat_capacity_j_m2_k)+W(in.water_mass_kg_m2)*p.liquid_heat_capacity_j_kg_k);
 else e.ds=0;
 e.f.atmosphere_present=air;e.f.atmospheric_temperature_k=rep(ta);
 e.f.incident_shortwave_w_m2=in.incident_shortwave_w_m2;
 e.f.reflected_shortwave_w_m2=rep(W(c.surface_shortwave_albedo)*in.incident_shortwave_w_m2);
 e.f.absorbed_shortwave_w_m2=rep(e.asr);e.f.surface_longwave_w_m2=rep(e.ls);
 e.f.atmospheric_absorbed_longwave_w_m2=rep(e.ab);
 e.f.atmospheric_upward_longwave_w_m2=rep(e.la);e.f.atmospheric_downward_longwave_w_m2=rep(e.la);
 e.f.sensible_surface_to_air_w_m2=rep(e.sensible);
 e.f.outgoing_longwave_w_m2=rep((1-a)*e.ls+e.la);
 return e;
}
bool converged(const Eval& e,W d) { return std::abs(e.rs)<=e.qs+e.rounds/d&&std::abs(e.ra)<=e.qa+e.rounda/d; }
void record(Receipt& r,Energy x,const Eval& e) {
 Receipt next=r;
 next.candidate=x;next.flux=e.f;
 next.surface_residual_w_m2=rep(e.rs);next.atmospheric_residual_w_m2=rep(e.ra);
 next.surface_solver_tolerance_w_m2=rep(e.qs);next.atmospheric_solver_tolerance_w_m2=rep(e.qa);
 next.surface_roundoff_allowance_j_m2=rep(e.rounds);next.atmospheric_roundoff_allowance_j_m2=rep(e.rounda);
 next.candidate_available=true;
 r=std::move(next);
}
}
Receipt solve_stage(const StageInput& in) {
 Receipt r;
 try {
 const auto& c=in.column;const auto& p=in.water;
 for(double v:std::array<double,19>{p.freezing_temperature_k,p.solid_heat_capacity_j_kg_k,p.liquid_heat_capacity_j_kg_k,p.latent_heat_j_kg,c.area_m2,c.dry_heat_capacity_j_m2_k,c.atmospheric_heat_capacity_j_m2_k,c.atmospheric_longwave_absorptivity,c.sensible_exchange_w_m2_k,c.surface_shortwave_albedo,in.water_mass_kg_m2,in.incident_shortwave_w_m2,in.effective_duration_seconds,in.reference.surface_enthalpy_j_m2,in.reference.atmospheric_energy_j_m2,in.guess.surface_enthalpy_j_m2,in.guess.atmospheric_energy_j_m2,in.options.absolute_tolerance_w_m2,in.options.relative_tolerance}) require(std::isfinite(v),"nonfinite input");
 require(!in.stage_id.empty()&&in.stage_id.size()<=64,"invalid stage identity");
 require(p.freezing_temperature_k>0&&p.solid_heat_capacity_j_kg_k>0&&p.liquid_heat_capacity_j_kg_k>0&&p.latent_heat_j_kg>0,"water properties must be positive");
 require(c.area_m2>0&&c.dry_heat_capacity_j_m2_k>0&&c.atmospheric_heat_capacity_j_m2_k>=0,"invalid capacities/area");
 require(c.atmospheric_longwave_absorptivity>=0&&c.atmospheric_longwave_absorptivity<=1&&c.sensible_exchange_w_m2_k>=0&&c.surface_shortwave_albedo>=0&&c.surface_shortwave_albedo<=1,"invalid physical coefficients");
 require(in.water_mass_kg_m2>=0&&in.incident_shortwave_w_m2>=0&&in.effective_duration_seconds>0,"invalid mass/forcing/duration");
 require(in.options.absolute_tolerance_w_m2>0&&in.options.relative_tolerance>=0&&in.options.relative_tolerance<=1&&in.options.maximum_newton_iterations>=0&&in.options.maximum_newton_iterations<=10000&&in.options.maximum_backtracks>=0&&in.options.maximum_backtracks<=10000,"invalid work/tolerance");
 require(c.atmospheric_heat_capacity_j_m2_k!=0||(c.atmospheric_longwave_absorptivity==0&&c.sensible_exchange_w_m2_k==0&&in.reference.atmospheric_energy_j_m2==0&&in.guess.atmospheric_energy_j_m2==0),"airless requires a=k=referenceEa=guessEa=0");
 Energy x=in.guess;
 ++r.flux_evaluations;Eval e=evaluate(in,x);record(r,x,e);
 const W d=in.effective_duration_seconds;
 const W scale=std::max({W(1),std::abs(e.asr),e.ls,e.la,std::abs(e.sensible)});
 for(;;) {
  if(converged(e,d)){r.accepted=true;return r;}
  if(r.newton_iterations>=in.options.maximum_newton_iterations) throw Refusal("nonconvergence","Newton iteration cap");
  const W k=c.sensible_exchange_w_m2_k,a=c.atmospheric_longwave_absorptivity;
  const W s=4*W(sigma_w_m2_k4)*e.ts*e.ts*e.ts,t=4*a*W(sigma_w_m2_k4)*e.ta*e.ta*e.ta;
  const W j00=1/d+(s+k)*e.ds;
  W dx=-e.rs/j00,de=0;
  if(c.atmospheric_heat_capacity_j_m2_k>0) {
   const W ca=c.atmospheric_heat_capacity_j_m2_k;
   const W j01=-(t+k)/ca,j10=-(a*s+k)*e.ds,j11=1/d+(2*t+k)/ca;
   const W det=j00*j11-j01*j10;
   if(!(det>0&&std::isfinite(det)))throw Refusal("representation_failure","Jacobian determinant");
   dx=(-e.rs*j11+j01*e.ra)/det;de=(j10*e.rs-j00*e.ra)/det;
  }
  ++r.newton_iterations;bool found=false;W fraction=1;
  const W merit=std::max(std::abs(e.rs),std::abs(e.ra))/scale;
  for(int b=0;b<=in.options.maximum_backtracks;++b) {
   try {
    Energy next{rep(W(x.surface_enthalpy_j_m2)+fraction*dx),rep(W(x.atmospheric_energy_j_m2)+fraction*de)};
    ++r.flux_evaluations;Eval ne=evaluate(in,next);
    const W nm=std::max(std::abs(ne.rs),std::abs(ne.ra))/scale;
    if(converged(ne,d)||nm<=(1-W(1e-4)*fraction)*merit){x=next;e=ne;record(r,x,e);found=true;break;}
   } catch(const cryosphere_prototype::Error&) {} catch(const Refusal& err) { if(err.code!="domain_failure"&&err.code!="representation_failure")throw; }
   if(b<in.options.maximum_backtracks){fraction*=W(0.5);++r.backtracks;}
  }
  if(!found)throw Refusal("nonconvergence","bounded admissible line search failed");
 }
 } catch(const Refusal& e){r.failure_code=e.code;r.detail=e.what();}
 catch(const cryosphere_prototype::Error& e){r.failure_code="domain_failure";r.detail=e.what();}
 catch(const std::exception& e){r.failure_code="internal_failure";r.detail=e.what();}
 return r;
}
} // namespace higher_order_thermal_prototype
