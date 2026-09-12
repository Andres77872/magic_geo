#include "internal.hpp"
#include "terrestrial_water.hpp"

namespace magic_geo::detail {
namespace {
using namespace cryosphere_prototype;

std::string quoted(const std::string &s) {
    std::string out = "\"";
    for (unsigned char ch : s) {
        if (ch == '"' || ch == '\\')
            out += '\\';
        if (ch < 32 || ch > 126) {
            throw TerrestrialWaterError("serialization_refusal", "non-ASCII identifier");
        }
        out += static_cast<char>(ch);
    }
    return out + "\"";
}
struct Object {
    std::string value = "{";
    void add(const char *name, const std::string &json) {
        if (value.size() > 1)
            value += ',';
        value += quoted(name) + ':' + json;
    }
    void number(const char *name, double x) { add(name, roundtrip_num(x)); }
    std::string finish() const { return value + '}'; }
};
template <class T, class F> std::string array(const std::vector<T> &values, F encode) {
    std::string out = "[";
    for (const auto &value : values) {
        if (out.size() > 1)
            out += ',';
        out += encode(value);
    }
    return out + ']';
}
std::string phase(Phase p) {
    if (p != Phase::solid && p != Phase::liquid) {
        throw TerrestrialWaterError("serialization_refusal", "invalid phase");
    }
    return quoted(p == Phase::solid ? "solid" : "liquid");
}
std::string state(const State &x) {
    Object o;
    o.number("W", x.water_mass_kg_m2);
    o.number("H", x.enthalpy_j_m2);
    return o.finish();
}
std::string vector3(const Vec3 &v) {
    return "[" + roundtrip_num(v.x) + ',' + roundtrip_num(v.y) + ',' + roundtrip_num(v.z) + ']';
}
std::string surface_cell(const Cell &c) {
    Object o;
    o.add("cell_id", std::to_string(c.id));
    o.add("is_water", c.is_water ? "true" : "false");
    o.add("is_lake", c.is_lake ? "true" : "false");
    o.add("water_body", std::to_string(c.water_body));
    o.number("area_km2", c.area_km2);
    o.number("canonical_area_m2", c.area_km2 * 1e6);
    o.number("elevation_m", c.elevation_m);
    o.number("lat", c.lat);
    o.number("lon", c.lon);
    o.add("position", vector3(c.p));
    o.number("water_depth_m", c.water_depth_m);
    o.add("neighbors", array(c.neighbors, [](int v) { return std::to_string(v); }));
    o.add("control_volume_vertices", array(c.control_volume_vertices, vector3));
    o.add("control_volume_edge_neighbor_ids",
          array(c.control_volume_edge_neighbor_ids, [](int v) { return std::to_string(v); }));
    o.number("temperature_c", c.temperature_c);
    o.number("original_precipitation_mm_y", c.precipitation_mm_y);
    o.number("sediment_thickness_m", c.sediment_thickness_m);
    o.add("lithology", std::to_string(c.lithology));
    return o.finish();
}
std::string water_properties(const WaterProperties &p) {
    Object o;
    o.number("freezing_temperature_k", p.freezing_temperature_k);
    o.number("solid_heat_capacity_j_kg_k", p.solid_heat_capacity_j_kg_k);
    o.number("liquid_heat_capacity_j_kg_k", p.liquid_heat_capacity_j_kg_k);
    o.number("latent_heat_j_kg", p.latent_heat_j_kg);
    return o.finish();
}
std::string properties(const TerrestrialWaterProperties &p) {
    Object o;
    o.add("water", water_properties(p.water));
    o.number("reference_water_density_kg_m3", p.reference_water_density_kg_m3);
    o.number("year_duration_seconds", p.year_duration_seconds);
    o.add("dry_heat_capacity_j_m2_k", roundtrip_double_array_json(p.dry_heat_capacity_j_m2_k));
    return o.finish();
}
std::string request(const TerrestrialIntervalRequest &r) {
    Object o;
    o.add("expected_revision", std::to_string(r.expected_revision));
    o.number("duration_seconds", r.duration_seconds);
    o.add("net_heat_flux_w_m2", roundtrip_double_array_json(r.net_heat_flux_w_m2));
    o.add("precipitation_imports", array(r.precipitation_imports, [](const auto &v) {
              Object a;
              a.add("id", quoted(v.id));
              a.add("cell_id", std::to_string(v.cell_id));
              a.add("phase", phase(v.phase));
              a.number("mass_kg", v.mass_kg);
              a.number("temperature_k", v.temperature_k);
              return a.finish();
          }));
    o.add("initial_liquid_withdrawals", array(r.initial_liquid_withdrawals, [](const auto &v) {
              Object a;
              a.add("id", quoted(v.id));
              a.add("cell_id", std::to_string(v.cell_id));
              a.number("mass_kg", v.mass_kg);
              return a.finish();
          }));
    return o.finish();
}
std::string kernel_result(const StepResult &r) {
    Object o;
    o.add("state", array(r.state, [](const State &x) {
              Object a;
              a.number("water_mass_kg_m2", x.water_mass_kg_m2);
              a.number("enthalpy_j_m2", x.enthalpy_j_m2);
              return a.finish();
          }));
    o.add("phase", array(r.phase, [](const PhaseState &x) {
              Object a;
              a.number("temperature_k", x.temperature_k);
              a.number("solid_mass_kg_m2", x.solid_mass_kg_m2);
              a.number("liquid_mass_kg_m2", x.liquid_mass_kg_m2);
              return a.finish();
          }));
    o.add("movements", array(r.movements, [](const Movement &x) {
              Object a;
              a.add("donor", std::to_string(x.donor));
              a.add("recipient", std::to_string(x.recipient));
              a.add("phase", phase(x.phase));
              a.number("mass_kg", x.mass_kg);
              a.number("temperature_k", x.temperature_k);
              a.number("specific_enthalpy_j_kg", x.specific_enthalpy_j_kg);
              a.number("carried_enthalpy_j", x.carried_enthalpy_j);
              return a.finish();
          }));
    o.add("ledger", array(r.ledger, [](const Ledger &x) {
              Object a;
#define FIELD(name) a.number(#name, x.name)
              FIELD(imported_mass_kg_m2);
              FIELD(exported_mass_kg_m2);
              FIELD(imported_enthalpy_j_m2);
              FIELD(exported_enthalpy_j_m2);
              FIELD(prescribed_heat_j_m2);
              FIELD(mass_residual_kg_m2);
              FIELD(energy_residual_j_m2);
              FIELD(mass_roundoff_allowance_kg_m2);
              FIELD(energy_roundoff_allowance_j_m2);
#undef FIELD
              return a.finish();
          }));
#define FIELD(name) o.number(#name, r.name)
    FIELD(global_mass_change_kg);
    FIELD(external_net_mass_kg);
    FIELD(global_mass_residual_kg);
    FIELD(global_mass_roundoff_allowance_kg);
    FIELD(global_energy_change_j);
    FIELD(external_net_enthalpy_j);
    FIELD(prescribed_heat_j);
    FIELD(global_energy_residual_j);
    FIELD(global_energy_roundoff_allowance_j);
#undef FIELD
    return o.finish();
}
std::string handoff(const TerrestrialLiquidHandoff &x) {
    Object o;
    o.add("id", quoted(x.id));
    o.add("cell_id", std::to_string(x.cell_id));
    o.number("mass_kg", x.mass_kg);
    o.number("carried_enthalpy_j", x.carried_enthalpy_j);
    o.add("kernel_movement_index", std::to_string(x.kernel_movement_index));
    return o.finish();
}
std::string projected_rates(const Cell &c) {
    Object o;
#define FIELD(name) o.number(#name, c.name)
    FIELD(hydrologic_potential_evapotranspiration_mm_y);
    FIELD(actual_evapotranspiration_mm_y);
    FIELD(infiltration_capacity_index);
    FIELD(infiltration_mm_y);
    FIELD(hydrologic_water_balance_mm_y);
    FIELD(water_budget_runoff_mm_y);
    FIELD(runoff_mm_y);
    FIELD(runoff_budget_residual_mm_y);
    FIELD(runoff_budget_consistency_index);
    FIELD(hydrologic_deficit_mm_y);
    FIELD(runoff_generation_fraction);
#undef FIELD
    return o.finish();
}
} // namespace

std::string terrestrial_water_model_json() {
    return R"({"model":"explicit_terrestrial_water_interval_owner_v1","domain":"fixed_postclassification_exposed_cells_only","kernel":"frozen_cryosphere_enthalpy_A_v1","input_numbers":"binary64_roundtrip_v1","source_policy":"explicit_initial_phase_temperature_mass_imports","withdrawal_policy":"initial_liquid_inventory_only_no_same_interval_refeed","heat_policy":"prescribed_constant_net_heat_flux_times_positive_duration","clock_policy":"exact_binary64_elapsed_plus_duration","publication_policy":"opaque_owner_and_restart_bound_candidate_single_bundle_swap","projection_model":"delivered_liquid_annualized_legacy_partition_v1","projection_aggregation":"original_withdrawal_order_binary64_mass_and_carried_J_sums","projection_conversion":"mass_div_canonical_area_div_density_times_1000_times_year_div_duration","partition_conversion":"rate_times_duration_div_year","source_representation_error":"not_certified_by_native_receipt_retained_operands_require_independent_audit","projection_representation_error":"not_certified_by_native_receipt_retained_operands_require_independent_audit","energy_scope":"exported_carried_enthalpy_leaves_terrestrial_volume_no_downstream_evaporation_energy_certificate","normal_generation_authority":"unchanged_annual_climate_hydrology_grounded_ice"})";
}
std::string terrestrial_interval_request_json(const TerrestrialIntervalRequest &r) {
    return request(r);
}
std::string terrestrial_water_context_json(const TerrestrialWaterOwner &owner) {
    Object o;
    o.add("surface_revision", std::to_string(owner.surface().surface_revision()));
    o.add("surface_cells", array(owner.surface().cells(), surface_cell));
    o.add("properties", properties(owner.properties()));
    Object limits;
#define LIMIT(name) limits.add(#name, std::to_string(owner.limits().name))
    LIMIT(max_cells);
    LIMIT(max_committed_intervals);
    LIMIT(max_events_per_interval);
    LIMIT(max_consumed_event_ids);
    LIMIT(max_identifier_bytes);
#undef LIMIT
    o.add("limits", limits.finish());
    return o.finish();
}
std::string terrestrial_water_restart_json(const TerrestrialWaterRestart &r) {
    Object o;
    o.add("revision", std::to_string(r.revision));
    o.number("elapsed_seconds", r.elapsed_seconds);
    o.add("state", array(r.state, state));
    o.add("consumed_event_ids", array(r.consumed_event_ids, quoted));
    return o.finish();
}
std::string terrestrial_interval_receipt_json(const TerrestrialIntervalReceipt &r) {
    Object o;
    o.add("schema", quoted("terrestrial_water_interval_receipt_v1"));
    o.add("model", terrestrial_water_model_json());
    o.add("surface_revision", std::to_string(r.surface_revision));
    o.add("surface_cells", array(r.surface_cells, surface_cell));
    o.add("properties", properties(r.properties));
    Object limits;
#define LIMIT(name) limits.add(#name, std::to_string(r.limits.name))
    LIMIT(max_cells);
    LIMIT(max_committed_intervals);
    LIMIT(max_events_per_interval);
    LIMIT(max_consumed_event_ids);
    LIMIT(max_identifier_bytes);
#undef LIMIT
    o.add("limits", limits.finish());
    o.add("initial", terrestrial_water_restart_json(r.initial));
    o.add("request", request(r.request));
    o.add("final", terrestrial_water_restart_json(r.final));
    o.add("kernel_column_cell_ids",
          array(r.kernel_column_cell_ids, [](int v) { return std::to_string(v); }));
    o.add("kernel_result", kernel_result(r.kernel_result));
    o.add("liquid_outbox", array(r.liquid_outbox, handoff));
    if (r.projection.cells.size() != r.projection.projected_cells.size()) {
        throw TerrestrialWaterError("serialization_refusal", "projection coverage mismatch");
    }
    std::size_t index = 0;
    o.add("projection", array(r.projection.cells, [&](const auto &x) {
              Object a;
              a.add("cell_id", std::to_string(x.cell_id));
              a.add("applicable", x.applicable ? "true" : "false");
#define FIELD(name) a.number(#name, x.name)
              FIELD(original_precipitation_mm_y);
              FIELD(delivered_liquid_mass_kg);
              FIELD(delivered_liquid_enthalpy_j);
              FIELD(delivered_liquid_depth_mm);
              FIELD(liquid_supply_mm_y);
              FIELD(actual_evapotranspiration_mm);
              FIELD(infiltration_mm);
              FIELD(runoff_mm);
              FIELD(partition_residual_mm);
#undef FIELD
              a.add("rates", projected_rates(r.projection.projected_cells[index++]));
              return a.finish();
          }));
    return o.finish();
}
} // namespace magic_geo::detail
