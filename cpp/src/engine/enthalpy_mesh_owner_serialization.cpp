#include "enthalpy_mesh_owner.hpp"

#include <bit>
#include <cmath>
#include <iomanip>
#include <locale>
#include <sstream>

namespace magic_geo::detail {
namespace {
namespace a = cryosphere_prototype;
namespace p = phase_segment_prototype;
std::string json_quote(const std::string& text) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << '"';
    for (unsigned char ch : text) {
        if (ch == '"' || ch == '\\') out << '\\' << ch;
        else if (ch < 32 || ch > 126)
            out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << int(ch);
        else out << ch;
    }
    out << '"';
    return out.str();
}
std::string num(double value) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    if (std::isfinite(value)) out << std::setprecision(17) << value;
    else out << "{\"nonfinite_binary64_bits\":\"" << std::hex
             << std::bit_cast<std::uint64_t>(value) << "\"}";
    return out.str();
}
struct Object {
    std::string value = "{";
    void add(const char* name,const std::string& json) {
        if (value.size() > 1) value += ',';
        value += json_quote(name)+':'+json;
    }
    void number(const char* name,double x) { add(name,num(x)); }
    void flag(const char* name,bool x) { add(name,x ? "true" : "false"); }
    std::string finish() const { return value+'}'; }
};
template<class T,class F> std::string array(const std::vector<T>& values,F encode) {
    std::string result = "[";
    for (const auto& x : values) {
        if (result.size() > 1) result += ',';
        result += encode(x);
    }
    return result+']';
}
std::string vector3(const Vec3& x) { return '['+num(x.x)+','+num(x.y)+','+num(x.z)+']'; }
std::string surface_json(const Cell& c) {
    Object o;
    o.add("cell_id",std::to_string(c.id));
    o.flag("is_water",c.is_water); o.flag("is_lake",c.is_lake);
    o.add("water_body",std::to_string(c.water_body));
    o.number("area_km2",c.area_km2); o.number("canonical_area_m2",c.area_km2*1e6);
    o.number("elevation_m",c.elevation_m); o.number("lat",c.lat); o.number("lon",c.lon);
    o.add("position",vector3(c.p)); o.number("water_depth_m",c.water_depth_m);
    o.add("neighbors",array(c.neighbors,[](int x){return std::to_string(x);}));
    o.add("control_volume_vertices",array(c.control_volume_vertices,vector3));
    o.add("control_volume_edge_neighbor_ids",array(c.control_volume_edge_neighbor_ids,[](int x){return std::to_string(x);}));
    o.number("temperature_c",c.temperature_c); o.number("original_precipitation_mm_y",c.precipitation_mm_y);
    o.number("sediment_thickness_m",c.sediment_thickness_m); o.add("lithology",std::to_string(c.lithology));
    return o.finish();
}
std::string water_json(const a::WaterProperties& w) {
    Object o;
    o.number("freezing_temperature_k",w.freezing_temperature_k);
    o.number("solid_heat_capacity_j_kg_k",w.solid_heat_capacity_j_kg_k);
    o.number("liquid_heat_capacity_j_kg_k",w.liquid_heat_capacity_j_kg_k);
    o.number("latent_heat_j_kg",w.latent_heat_j_kg);
    return o.finish();
}
std::string interval_json(p::Interval x) {
    return "{\"lower\":"+num(x.lower)+",\"upper\":"+num(x.upper)+'}';
}
std::string box_json(const p::StateBox& box) {
    return "{\"surface_enthalpy_j_m2\":"+interval_json(box.surface_enthalpy_j_m2)+
        ",\"atmospheric_energy_j_m2\":"+interval_json(box.atmospheric_energy_j_m2)+'}';
}
std::string domain_json(const CoupledDomainCertificate& x) {
    Object o;
    o.flag("accepted",x.accepted); o.add("failure_code",json_quote(x.failure_code)); o.add("detail",json_quote(x.detail));
    o.add("uncertainty_box",box_json(x.uncertainty_box));
    o.add("surface_floor_j_m2",interval_json(x.surface_floor_j_m2));
    o.add("air_floor_j_m2",interval_json(x.air_floor_j_m2));
    return o.finish();
}
std::string jump_json(const CoupledJumpCertificate& x) {
    Object o;
    o.flag("accepted",x.accepted); o.add("failure_code",json_quote(x.failure_code)); o.add("detail",json_quote(x.detail));
    o.add("before_domain",domain_json(x.before_domain)); o.add("after_domain",domain_json(x.after_domain));
    o.add("withdrawal_density_kg_m2",interval_json(x.withdrawal_density_kg_m2));
    o.add("import_energy_j_m2",interval_json(x.import_energy_j_m2));
    o.add("canonical_mass_projection_kg_m2",interval_json(x.canonical_mass_projection_kg_m2));
    o.add("ideal_jump_j_m2",interval_json(x.ideal_jump_j_m2));
    o.add("state_projection_j_m2",interval_json(x.state_projection_j_m2));
    o.add("export_bridge_j_m2",interval_json(x.export_bridge_j_m2));
    o.flag("liquid_feasibility_proved",x.liquid_feasibility_proved);
    o.number("inherited_error_j_m2",x.inherited_error_j_m2);
    o.number("jump_defect_upper_j_m2",x.jump_defect_upper_j_m2);
    o.number("final_error_j_m2",x.final_error_j_m2);
    o.number("outbox_error_upper_j",x.outbox_error_upper_j);
    o.add("per_withdrawal_error_upper_j",array(x.per_withdrawal_error_upper_j,num));
    return o.finish();
}
std::string import_json(const TerrestrialPrecipitationImport& x) {
    Object o;
    o.add("id",json_quote(x.id)); o.add("cell_id",std::to_string(x.cell_id)); o.add("phase",std::to_string(static_cast<int>(x.phase)));
    o.number("mass_kg",x.mass_kg); o.number("temperature_k",x.temperature_k); return o.finish();
}
std::string withdrawal_json(const TerrestrialLiquidWithdrawal& x) {
    Object o;
    o.add("id",json_quote(x.id)); o.add("cell_id",std::to_string(x.cell_id)); o.number("mass_kg",x.mass_kg); return o.finish();
}
std::string a_state(const a::State& x) {
    return "{\"water_mass_kg_m2\":"+num(x.water_mass_kg_m2)+",\"enthalpy_j_m2\":"+num(x.enthalpy_j_m2)+'}';
}
std::string a_column(const a::Column& x) {
    return "{\"area_m2\":"+num(x.area_m2)+",\"dry_heat_capacity_j_m2_k\":"+num(x.dry_heat_capacity_j_m2_k)+'}';
}
std::string mass_request_json(const a::MassEventInput& x) {
    Object o;
    o.add("imports",array(x.imports,[](const a::Import& m){
        Object z; z.add("recipient",std::to_string(m.recipient)); z.add("phase",std::to_string(static_cast<int>(m.phase)));
        z.number("mass_kg",m.mass_kg); z.number("temperature_k",m.temperature_k); return z.finish();
    }));
    o.add("exports",array(x.exports,[](const a::Export& m){
        Object z; z.add("donor",std::to_string(m.donor)); z.add("phase",std::to_string(static_cast<int>(m.phase)));
        z.number("mass_kg",m.mass_kg); return z.finish();
    }));
    o.add("transfers",array(x.transfers,[](const a::Transfer& m){
        Object z; z.add("donor",std::to_string(m.donor)); z.add("recipient",std::to_string(m.recipient));
        z.add("phase",std::to_string(static_cast<int>(m.phase))); z.number("mass_kg",m.mass_kg); return z.finish();
    }));
    return o.finish();
}
std::string mass_receipt_json(const a::MassEventResult& r) {
    Object o;
    o.add("state",array(r.state,a_state));
    o.add("phase",array(r.phase,[](const a::PhaseState& x){
        Object z; z.number("temperature_k",x.temperature_k); z.number("solid_mass_kg_m2",x.solid_mass_kg_m2);
        z.number("liquid_mass_kg_m2",x.liquid_mass_kg_m2); return z.finish();
    }));
    o.add("movements",array(r.movements,[](const a::Movement& x){
        Object z; z.add("donor",std::to_string(x.donor)); z.add("recipient",std::to_string(x.recipient));
        z.add("phase",std::to_string(static_cast<int>(x.phase))); z.number("mass_kg",x.mass_kg);
        z.number("temperature_k",x.temperature_k); z.number("specific_enthalpy_j_kg",x.specific_enthalpy_j_kg);
        z.number("carried_enthalpy_j",x.carried_enthalpy_j); return z.finish();
    }));
    o.add("ledger",array(r.ledger,[](const a::MassEventLedger& x){
        Object z;
#define L(name) z.number(#name,x.name)
        L(imported_mass_kg_m2); L(exported_mass_kg_m2); L(imported_enthalpy_j_m2); L(exported_enthalpy_j_m2);
        L(mass_residual_kg_m2); L(energy_residual_j_m2); L(mass_roundoff_allowance_kg_m2); L(energy_roundoff_allowance_j_m2);
#undef L
        return z.finish();
    }));
#define G(name) o.number(#name,r.name)
    G(global_mass_change_kg); G(external_net_mass_kg); G(global_mass_residual_kg); G(global_mass_roundoff_allowance_kg);
    G(global_energy_change_j); G(external_net_enthalpy_j); G(global_energy_residual_j); G(global_energy_roundoff_allowance_j);
#undef G
    return o.finish();
}
std::string outbox_json(const TerrestrialLiquidHandoff& x) {
    Object o;
    o.add("id",json_quote(x.id)); o.add("cell_id",std::to_string(x.cell_id)); o.number("mass_kg",x.mass_kg);
    o.number("carried_enthalpy_j",x.carried_enthalpy_j); o.add("kernel_movement_index",std::to_string(x.kernel_movement_index));
    return o.finish();
}
std::string projection_json(const TerrestrialLiquidSupplyProjection& x) {
    Object o;
    o.add("cells",array(x.cells,[](const TerrestrialLiquidSupplyCell& c){
        Object z; z.add("cell_id",std::to_string(c.cell_id)); z.flag("applicable",c.applicable);
#define V(name) z.number(#name,c.name)
        V(original_precipitation_mm_y); V(delivered_liquid_mass_kg); V(delivered_liquid_enthalpy_j);
        V(delivered_liquid_depth_mm); V(liquid_supply_mm_y); V(actual_evapotranspiration_mm);
        V(infiltration_mm); V(runoff_mm); V(partition_residual_mm);
#undef V
        return z.finish();
    }));
    o.add("projected_cells",array(x.projected_cells,[](const Cell& c){
        Object z; z.add("cell_id",std::to_string(c.id));
#define V(name) z.number(#name,c.name)
        V(hydrologic_potential_evapotranspiration_mm_y); V(actual_evapotranspiration_mm_y);
        V(infiltration_capacity_index); V(infiltration_mm_y); V(hydrologic_water_balance_mm_y);
        V(water_budget_runoff_mm_y); V(runoff_mm_y); V(runoff_budget_residual_mm_y);
        V(runoff_budget_consistency_index); V(hydrologic_deficit_mm_y); V(runoff_generation_fraction);
#undef V
        return z.finish();
    }));
    o.add("scope",json_quote("ordered_binary64_annualized_liquid_partition_no_downstream_energy_certificate"));
    return o.finish();
}
void identity(Object& o) {
    o.add("model",json_quote("combined_temperature_enthalpy_mesh_owner_v1"));
    o.add("error_scope",json_quote("canonical_projected_W_prescribed_import_J_global_area_L1_v1"));
    o.add("policy",json_quote("post_source_global_allowance_exact_tick_share_v1"));
    o.flag("original_source_accuracy_certified",false);
    o.flag("ordinary_generation_changed",false);
    o.flag("external_delivery_acknowledged",false);
}
std::string owner_limits_json(const EnthalpyMeshOwnerLimits& x) {
    Object o;
#define LIMIT(name) o.add(#name,std::to_string(x.name))
    LIMIT(max_cells); LIMIT(max_edges); LIMIT(max_prepare_attempts); LIMIT(max_committed_intervals);
    LIMIT(max_events_per_interval); LIMIT(max_consumed_event_ids); LIMIT(max_identifier_bytes);
    LIMIT(max_thermal_attempts); LIMIT(max_accepted_steps);
    LIMIT(max_scalar_evaluations_per_prepare); LIMIT(max_field_evaluations_per_prepare);
    LIMIT(max_retained_cell_leaves); LIMIT(max_retained_edge_leaves);
    LIMIT(max_stored_forcing_values);
#undef LIMIT
    return o.finish();
}
std::string mesh_forcing_json(const EnthalpyMeshForcing& x) {
    Object o;
    o.add("id",json_quote(x.id)); o.number("begin_seconds",x.begin_seconds); o.number("end_seconds",x.end_seconds);
    o.add("absorbed_shortwave_w_m2",array(x.absorbed_shortwave_w_m2,num));
    return o.finish();
}
std::string restart_json(const EnthalpyMeshRestart& x, bool error_available) {
    Object o;
    o.add("revision",std::to_string(x.revision)); o.number("elapsed_seconds",x.elapsed_seconds);
    o.add("state",array(x.state,a_state));
    o.add("canonical_energy_error_j",error_available?num(x.canonical_energy_error_j):"null");
    o.add("consumed_event_ids",array(x.consumed_event_ids,json_quote));
    o.add("forcing_history",array(x.forcing_history,mesh_forcing_json));
    return o.finish();
}
std::string automatic_options_json(const EnthalpyMeshAutomaticOptions& x) {
    Object o;
    o.number("maximum_step_seconds",x.maximum_step_seconds); o.number("minimum_step_seconds",x.minimum_step_seconds);
    o.number("maximum_stage_error_j",x.maximum_stage_error_j);
#define OPTION(name) o.add(#name,std::to_string(x.name))
    OPTION(maximum_attempts); OPTION(maximum_accepted_steps); OPTION(maximum_sweeps);
    OPTION(maximum_coordinate_iterations); OPTION(maximum_scalar_evaluations); OPTION(reconstruction_leaves);
#undef OPTION
    return o.finish();
}
std::string reference_domain_json(const EnthalpyMeshReferenceDomain& x) {
    if (!x.attempted) return "null";
    Object o;
    o.flag("attempted",x.attempted); o.flag("proved",x.proved);
    o.add("failure_code",json_quote(x.failure_code)); o.add("detail",json_quote(x.detail));
    o.number("inherited_error_j",x.inherited_error_j); o.number("duration_seconds",x.duration_seconds);
    o.add("component_radius_j_m2",x.proved?array(x.component_radius_j_m2,num):"null");
    o.add("enthalpy_box_j_m2",x.proved?array(x.enthalpy_box_j_m2,interval_json):"null");
    o.add("physical_floor_j_m2",x.proved?array(x.physical_floor_j_m2,interval_json):"null");
    o.add("reference_temperature_upper_k",x.proved?num(x.reference_temperature_upper_k):"null");
    return o.finish();
}
std::string source_jump_json(const EnthalpyMeshSourceJump& x) {
    Object o;
    o.flag("available",x.available);
    o.add("cell_ids",array(x.cell_ids,[](int i){return std::to_string(i);}));
    // Preserve the old helper's whole observed certificate, including a refused
    // scalar prefix. Its local radii/final errors are not summed as global E.
    o.add("scalar_certificates",array(x.scalar_certificates,jump_json));
    o.add("scalar_certificate_scope",json_quote("airless_combined_capacity_local_domain_radius_not_additive_global_error_v1"));
    o.number("inherited_error_j",x.inherited_error_j);
    o.add("weighted_jump_defect_upper_j",x.available?num(x.weighted_jump_defect_upper_j):"null");
    o.add("final_error_j",x.available?num(x.final_error_j):"null");
    o.add("after_domain",reference_domain_json(x.after_domain));
    return o.finish();
}
std::string trial_json(const EnthalpyMeshTrial& x) {
    Object o;
#define TICK(name) o.add(#name,std::to_string(x.name))
    TICK(begin_tick); TICK(duration_ticks); TICK(interval_ticks);
#undef TICK
    o.number("start_seconds",x.start_seconds); o.number("end_seconds",x.end_seconds);
    o.number("interval_initial_error_j",x.interval_initial_error_j);
    o.number("headroom_lower_j",x.headroom_lower_j); o.number("offered_error_j",x.offered_error_j);
    o.number("inherited_error_j",x.inherited_error_j);
    o.add("before_domain",reference_domain_json(x.before_domain));
    o.add("after_domain",reference_domain_json(x.after_domain));
    o.flag("call_started",x.call_started);
    o.add("receipt",x.receipt?enthalpy_mesh_receipt_json(*x.receipt):"null");
    o.flag("charged_increment_available",x.charged_increment_available);
    o.add("proposed_final_error_j",x.charged_increment_available?num(x.proposed_final_error_j):"null");
    o.add("charged_increment_j",x.charged_increment_available?interval_json(x.charged_increment_j):"null");
    o.flag("accepted_for_private_carry",x.accepted_for_private_carry);
    o.add("refusal_code",json_quote(x.refusal_code));
    return o.finish();
}
std::string discrete_ledger_json(const EnthalpyMeshDiscreteLedger& x) {
    Object o;
#define VALUE(name) o.add(#name,interval_json(x.name))
    VALUE(total_mass_change_kg); VALUE(external_mass_kg); VALUE(mass_projection_residual_kg);
    VALUE(total_storage_j); VALUE(external_enthalpy_j); VALUE(source_storage_j); VALUE(source_projection_residual_j);
    VALUE(thermal_storage_j); VALUE(absorbed_shortwave_j); VALUE(backward_euler_emission_j); VALUE(balance_residual_j);
#undef VALUE
    o.add("scope",json_quote("outward_represented_state_and_recorded_movements_BE_endpoint_quadrature_not_true_flow_v1"));
    return o.finish();
}
} // namespace

std::string enthalpy_mesh_properties_json(const EnthalpyMeshProperties& x) {
    Object o;
    o.add("water",water_json(x.water));
    o.number("reference_water_density_kg_m3",x.reference_water_density_kg_m3);
    o.number("year_duration_seconds",x.year_duration_seconds);
    o.add("columns",array(x.columns,[](const SurfaceEnergyColumn& c){
        Object z; z.number("area_m2",c.area_m2); z.number("heat_capacity_j_m2_k",c.heat_capacity_j_m2_k);
        z.number("longwave_emissivity",c.longwave_emissivity); return z.finish();
    }));
    o.add("edges",array(x.edges,[](const EnergyTransportEdge& e){
        Object z; z.add("first_cell",std::to_string(e.first_cell)); z.add("second_cell",std::to_string(e.second_cell));
        z.number("conductance_w_k",e.conductance_w_k); return z.finish();
    }));
    return o.finish();
}
std::string enthalpy_mesh_restart_json(const EnthalpyMeshRestart& x) {
    return restart_json(x,true);
}
std::string enthalpy_mesh_interval_request_json(const EnthalpyMeshIntervalRequest& x) {
    Object o;
    o.add("expected_revision",std::to_string(x.expected_revision)); o.number("end_seconds",x.end_seconds);
    o.add("forcing",mesh_forcing_json(x.forcing));
    o.add("imports",array(x.imports,import_json));
    o.add("initial_liquid_withdrawals",array(x.initial_liquid_withdrawals,withdrawal_json));
    o.add("options",automatic_options_json(x.options));
    if(x.maximum_thermal_error_increment_j)
        o.number("maximum_thermal_error_increment_j",*x.maximum_thermal_error_increment_j);
    return o.finish();
}
std::string enthalpy_mesh_owner_work_json(const EnthalpyMeshOwnerWork& x) {
    Object o;
#define COUNT(name) o.add(#name,std::to_string(x.name))
    COUNT(prepare_attempts); COUNT(mass_calls_started); COUNT(mass_calls_returned);
    COUNT(thermal_calls_started); COUNT(thermal_calls_returned);
    COUNT(scalar_evaluations); COUNT(field_evaluations); COUNT(sweeps_started);
    COUNT(coordinate_solves_started); COUNT(reconstruction_leaves_started);
    COUNT(reserved_scalar_evaluations); COUNT(reserved_field_evaluations);
#undef COUNT
    o.flag("observed_counts_complete",x.observed_counts_complete);
    return o.finish();
}
std::string enthalpy_mesh_owner_receipt_json(const EnthalpyMeshOwnerReceipt& r) {
    Object o; identity(o);
    o.flag("prepared",r.prepared); o.add("failure_code",json_quote(r.failure_code)); o.add("detail",json_quote(r.detail));
    o.add("surface_revision",std::to_string(r.surface_revision));
    o.add("surface_cells",array(r.surface_cells,surface_json));
    o.add("properties",enthalpy_mesh_properties_json(r.properties)); o.add("limits",owner_limits_json(r.limits));
    o.number("maximum_cumulative_error_j",r.maximum_cumulative_error_j);
    o.add("initial",enthalpy_mesh_restart_json(r.initial));
    o.add("observed_accepted_after",enthalpy_mesh_restart_json(r.observed_accepted_after));
    o.flag("private_prefix_error_available",r.private_prefix_error_available);
    o.add("private_prefix",restart_json(r.private_prefix,r.private_prefix_error_available));
    o.add("request",r.request?enthalpy_mesh_interval_request_json(*r.request):"null");
    o.add("observed_request_after",r.observed_request_after?enthalpy_mesh_interval_request_json(*r.observed_request_after):"null");
    o.number("clock_quantum_seconds",r.clock_quantum_seconds);
    o.flag("mass_call_started",r.mass_call_started);
    o.add("kernel_column_cell_ids",array(r.kernel_column_cell_ids,[](int i){return std::to_string(i);}));
    o.add("kernel_columns",array(r.kernel_columns,a_column)); o.add("kernel_initial",array(r.kernel_initial,a_state));
    o.add("mass_request",r.mass_request?mass_request_json(*r.mass_request):"null");
    o.add("mass_receipt",r.mass_receipt?mass_receipt_json(*r.mass_receipt):"null");
    o.add("jump",source_jump_json(r.jump));
    o.add("thermal_initial",r.thermal_initial?enthalpy_mesh_restart_json(*r.thermal_initial):"null");
    o.add("trials",array(r.trials,trial_json));
    o.add("private_liquid_outbox",array(r.private_liquid_outbox,outbox_json));
    o.add("projection",r.projection?projection_json(*r.projection):"null");
    o.add("discrete_ledger",r.discrete_ledger?discrete_ledger_json(*r.discrete_ledger):"null");
    o.add("final",r.final?enthalpy_mesh_restart_json(*r.final):"null");
    o.add("work_before",enthalpy_mesh_owner_work_json(r.work_before));
    o.add("work_after",enthalpy_mesh_owner_work_json(r.work_after));
    return o.finish();
}
std::string enthalpy_mesh_owner_context_json(const EnthalpyMeshOwner& owner) {
    Object o; identity(o);
    o.add("surface_revision",std::to_string(owner.surface().surface_revision()));
    o.add("surface_cells",array(owner.surface().cells(),surface_json));
    o.add("properties",enthalpy_mesh_properties_json(owner.properties()));
    o.add("restart",enthalpy_mesh_restart_json(owner.restart()));
    o.add("limits",owner_limits_json(owner.limits()));
    o.number("maximum_cumulative_error_j",owner.maximum_cumulative_error_j());
    o.add("work",enthalpy_mesh_owner_work_json(owner.work_meter()));
    o.flag("last_receipt_available",owner.last_receipt()!=nullptr);
    return o.finish();
}
} // namespace magic_geo::detail
