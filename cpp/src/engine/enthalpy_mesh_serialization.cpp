#include "enthalpy_mesh.hpp"

#include <bit>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>

namespace magic_geo::detail {
namespace {
std::string quote(const std::string& s) {
    std::ostringstream out;out<<'"';
    for(unsigned char c:s) {
        if(c=='"' || c=='\\')out<<'\\'<<c;
        else if(c<32 || c>126)out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<int(c);
        else out<<c;
    }
    out<<'"';return out.str();
}
std::string number(double x) {
    std::ostringstream out;out.imbue(std::locale::classic());
    if(std::isfinite(x))out<<std::setprecision(std::numeric_limits<double>::max_digits10)<<x;
    else out<<"{\"nonfinite_binary64_bits\":\""<<std::hex<<std::bit_cast<std::uint64_t>(x)<<"\"}";
    return out.str();
}
struct Object {
    std::string s="{";
    void add(const char* key,const std::string& value) {if(s.size()>1)s+=',';s+=quote(key)+':'+value;}
    void num(const char* key,double x) {add(key,number(x));}
    void flag(const char* key,bool x) {add(key,x?"true":"false");}
    std::string finish()const{return s+'}';}
};
template<class T,class F> std::string array(const std::vector<T>& xs,F f) {
    std::string s="[";for(const auto& x:xs){if(s.size()>1)s+=',';s+=f(x);}return s+']';
}
std::string interval(EnthalpyMeshInterval x) {Object o;o.num("lower",x.lower);o.num("upper",x.upper);return o.finish();}
std::string field(const EnthalpyMeshField& x) {
    Object o;
#define FIELD(name) o.add(#name,array(x.name,interval))
    FIELD(temperature_k);FIELD(emitted_longwave_w_m2);FIELD(edge_heat_w);
    FIELD(heat_convergence_w_m2);FIELD(net_heating_w_m2);
#undef FIELD
    return o.finish();
}
} // namespace
std::string enthalpy_mesh_request_json(const EnthalpyMeshRequest& q) {
    Object o,w,opt;
    w.num("freezing_temperature_k",q.water.freezing_temperature_k);
    w.num("solid_heat_capacity_j_kg_k",q.water.solid_heat_capacity_j_kg_k);
    w.num("liquid_heat_capacity_j_kg_k",q.water.liquid_heat_capacity_j_kg_k);
    w.num("latent_heat_j_kg",q.water.latent_heat_j_kg);o.add("water",w.finish());
    o.add("columns",array(q.columns,[](const auto& c){Object x;x.num("area_m2",c.area_m2);
        x.num("heat_capacity_j_m2_k",c.heat_capacity_j_m2_k);x.num("longwave_emissivity",c.longwave_emissivity);return x.finish();}));
    o.add("edges",array(q.edges,[](const auto& e){Object x;x.add("first_cell",std::to_string(e.first_cell));
        x.add("second_cell",std::to_string(e.second_cell));x.num("conductance_w_k",e.conductance_w_k);return x.finish();}));
    o.add("water_mass_kg_m2",array(q.water_mass_kg_m2,number));
    o.add("initial_enthalpy_j_m2",array(q.initial_enthalpy_j_m2,number));
    o.add("absorbed_shortwave_w_m2",array(q.absorbed_shortwave_w_m2,number));
    const auto& a=q.options;
    opt.num("duration_seconds",a.duration_seconds);opt.num("maximum_stage_error_j",a.maximum_stage_error_j);
    opt.num("maximum_endpoint_error_j",a.maximum_endpoint_error_j);
    opt.add("maximum_sweeps",std::to_string(a.maximum_sweeps));
    opt.add("maximum_coordinate_iterations",std::to_string(a.maximum_coordinate_iterations));
    opt.add("maximum_scalar_evaluations",std::to_string(a.maximum_scalar_evaluations));
    opt.add("reconstruction_leaves",std::to_string(a.reconstruction_leaves));
    if(a.allow_pure_water_columns) opt.flag("allow_pure_water_columns",true);
    o.add("options",opt.finish());
    return o.finish();
}
std::string enthalpy_mesh_receipt_json(const EnthalpyMeshReceipt& r) {
    Object o;
    o.add("model",quote(r.request && r.request->options.allow_pure_water_columns ?
        "enthalpy_mesh_backward_euler_pure_water_v2" : "combined_temperature_enthalpy_mesh_backward_euler_v1"));
    o.add("error_scope",quote("canonical_point_fixed_W_area_weighted_L1_joules_v1"));
    o.add("curve",quote("exact_raw_endpoint_line_uniform_dyadic_v1"));
    o.flag("original_source_accuracy_certified",false);o.flag("ordinary_generation_changed",false);
    o.flag("accepted",r.accepted);o.add("failure_code",quote(r.failure_code));o.add("detail",quote(r.detail));
    o.add("request",r.request?enthalpy_mesh_request_json(*r.request):"null");
    o.flag("physical_domain_proved",r.physical_domain_proved);
    o.add("physical_temperature_upper_k",r.physical_domain_proved?number(r.physical_temperature_upper_k):"null");
    o.add("physical_floor_j_m2",r.physical_domain_proved?array(r.physical_floor_j_m2,interval):"null");
    o.flag("candidate_available",r.candidate_available);o.add("candidate_enthalpy_j_m2",r.candidate_available?array(r.candidate_enthalpy_j_m2,number):"null");
    o.flag("stage_error_available",r.stage_error_available);
    o.add("candidate_field",r.stage_error_available?field(r.candidate_field):"null");
    o.add("stage_residual_j_m2",r.stage_error_available?array(r.stage_residual_j_m2,interval):"null");
    o.add("stage_error_upper_j",r.stage_error_available?number(r.stage_error_upper_j):"null");o.flag("stage_accepted",r.stage_accepted);
    o.add("sweeps",array(r.sweeps,[](const auto& s){Object x;x.add("completed_sweeps",std::to_string(s.completed_sweeps));
        x.add("scalar_evaluations",std::to_string(s.scalar_evaluations));x.num("stage_error_upper_j",s.stage_error_upper_j);return x.finish();}));
    o.add("leaves",array(r.leaves,[](const auto& l){Object x;x.add("index",std::to_string(l.index));x.flag("complete",l.complete);
        x.add("enthalpy_range_j_m2",l.complete?array(l.enthalpy_range_j_m2,interval):"null");x.add("field",l.complete?field(l.field):"null");
        x.add("residual_integral_j_m2",l.complete?array(l.residual_integral_j_m2,interval):"null");
        x.add("weighted_residual_upper_j",l.complete?number(l.weighted_residual_upper_j):"null");return x.finish();}));
    o.flag("endpoint_error_available",r.endpoint_error_available);o.add("local_endpoint_error_upper_j",r.endpoint_error_available?number(r.local_endpoint_error_upper_j):"null");
    o.add("final_enthalpy_j_m2",r.final_enthalpy_j_m2?array(*r.final_enthalpy_j_m2,number):"null");
    o.add("scalar_evaluations",std::to_string(r.scalar_evaluations));o.add("field_evaluations",std::to_string(r.field_evaluations));
    o.add("sweeps_started",std::to_string(r.sweeps_started));o.add("coordinate_solves_started",std::to_string(r.coordinate_solves_started));
    o.add("leaves_started",std::to_string(r.leaves_started));return o.finish();
}
} // namespace magic_geo::detail
