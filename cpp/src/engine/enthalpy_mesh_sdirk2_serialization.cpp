#include "enthalpy_mesh_sdirk2.hpp"

#include <bit>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>

namespace magic_geo::detail {
namespace {
std::string quote(const std::string& s) {
    std::ostringstream out; out << '"';
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') out << '\\' << c;
        else if (c < 32 || c > 126) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << int(c);
        else out << c;
    }
    out << '"'; return out.str();
}
std::string number(double x) {
    std::ostringstream out; out.imbue(std::locale::classic());
    if (std::isfinite(x)) out << std::setprecision(std::numeric_limits<double>::max_digits10) << x;
    else out << "{\"nonfinite_binary64_bits\":\"" << std::hex << std::bit_cast<std::uint64_t>(x) << "\"}";
    return out.str();
}
struct Object {
    std::string s = "{";
    void add(const char* key, const std::string& value) { if (s.size() > 1) s += ','; s += quote(key)+':'+value; }
    void num(const char* key, double x) { add(key, number(x)); }
    void flag(const char* key, bool x) { add(key, x ? "true" : "false"); }
    std::string finish() const { return s+'}'; }
};
template<class T, class F> std::string array(const std::vector<T>& xs, F f) {
    std::string s = "["; for (const auto& x : xs) { if (s.size() > 1) s += ','; s += f(x); } return s+']';
}
std::string interval(EnthalpyMeshInterval x) { Object o; o.num("lower", x.lower); o.num("upper", x.upper); return o.finish(); }
std::string polynomial(const EnthalpyMeshPolynomial& p) { return array(p, interval); }
} // namespace
std::string enthalpy_mesh_sdirk2_receipt_json(const EnthalpyMeshSdirk2Receipt& r) {
    Object o;
    o.add("model", quote(r.request && r.request->options.allow_pure_water_columns ?
        "enthalpy_mesh_represented_sdirk2_pure_water_v2" : "combined_temperature_enthalpy_mesh_represented_sdirk2_v1"));
    o.add("curve", quote("exact_raw_endpoint_initial_tangent_quadratic_bernstein_v1"));
    o.add("error_scope", quote("canonical_point_fixed_W_area_weighted_L1_joules_v1"));
    o.flag("original_source_accuracy_certified", false); o.flag("ordinary_generation_changed", false);
    o.flag("owner_dispatch_available", false); o.flag("exact_irrational_tableau", false);
    o.flag("accepted", r.accepted); o.add("failure_code", quote(r.failure_code)); o.add("detail", quote(r.detail));
    o.add("request", r.request ? enthalpy_mesh_request_json(*r.request) : "null");
    o.num("gamma", r.gamma); o.num("diagonal_duration_seconds", r.diagonal_duration_seconds);
    o.num("off_diagonal_duration_seconds", r.off_diagonal_duration_seconds);
    o.flag("tableau_bridges_available", r.tableau_bridges_available);
    o.add("duration_sum_defect_seconds", r.tableau_bridges_available ? interval(r.duration_sum_defect_seconds) : "null");
    o.add("second_order_coefficient_defect", r.tableau_bridges_available ? interval(r.second_order_coefficient_defect) : "null");
    o.add("initial_heating_w_m2", array(r.initial_heating_w_m2, number));
    o.add("first_stage_heating_w_m2", array(r.first_stage_heating_w_m2, number));
    o.add("second_stage_base_j_m2", array(r.second_stage_base_j_m2, number));
    o.add("second_stage_base_defect_j_m2", array(r.second_stage_base_defect_j_m2, interval));
    o.add("first_stage", r.first_stage ? enthalpy_mesh_receipt_json(*r.first_stage) : "null");
    o.add("second_stage", r.second_stage ? enthalpy_mesh_receipt_json(*r.second_stage) : "null");
    o.flag("physical_curve_proved", r.physical_curve_proved);
    o.add("leaves", array(r.leaves, [](const auto& leaf) {
        Object l; l.add("index", std::to_string(leaf.index)); l.flag("complete", leaf.complete);
        l.add("enthalpy", array(leaf.enthalpy, polynomial)); l.add("temperature", array(leaf.temperature, polynomial));
        l.add("temperature_branch", array(leaf.temperature_branch, quote));
        l.add("residual", leaf.complete ? array(leaf.residual, polynomial) : "null");
        l.add("absolute_residual_integral_upper_j_m2", leaf.complete ? array(leaf.absolute_residual_integral_upper_j_m2, number) : "null");
        l.add("weighted_residual_upper_j", leaf.complete ? number(leaf.weighted_residual_upper_j) : "null"); return l.finish();
    }));
    o.flag("endpoint_error_available", r.endpoint_error_available);
    o.add("local_endpoint_error_upper_j", r.endpoint_error_available ? number(r.local_endpoint_error_upper_j) : "null");
    o.add("final_enthalpy_j_m2", r.final_enthalpy_j_m2 ? array(*r.final_enthalpy_j_m2, number) : "null");
    o.add("scalar_evaluations", std::to_string(r.scalar_evaluations)); o.add("field_evaluations", std::to_string(r.field_evaluations));
    o.add("stage_calls_started", std::to_string(r.stage_calls_started)); o.add("sweeps_started", std::to_string(r.sweeps_started));
    o.add("coordinate_solves_started", std::to_string(r.coordinate_solves_started));
    o.add("backward_euler_leaves_started", std::to_string(r.backward_euler_leaves_started));
    o.add("certificate_leaves_started", std::to_string(r.certificate_leaves_started));
    return o.finish();
}
} // namespace magic_geo::detail
