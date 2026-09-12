#include "finalized_layered_state.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <iomanip>
#include <locale>
#include <sstream>
#include <utility>

namespace magic_geo::detail {
namespace {
namespace b = phase_segment_prototype::bounds;
using I = EnthalpyMeshInterval;
struct Refusal : std::runtime_error {
    std::string code;
    Refusal(std::string c, std::string d) : std::runtime_error(std::move(d)), code(std::move(c)) {}
};
void need(bool ok, const char* code, const char* detail) {
    if (!ok) throw Refusal(code, detail);
}
double checked(double value) {
    need(std::isfinite(value), "arithmetic_refusal", "nonfinite represented initialization arithmetic");
    return value;
}
std::string quote(const std::string& value) {
    std::ostringstream out;
    out.imbue(std::locale::classic()); out << '"';
    for (unsigned char c : value) {
        if (c == '"' || c == '\\') out << '\\' << c;
        else if (c < 32 || c > 126)
            out << "\\u00" << std::hex << std::setw(2) << std::setfill('0') << static_cast<unsigned int>(c);
        else out << c;
    }
    out << '"'; return out.str();
}
std::string number(double value) {
    std::ostringstream out; out.imbue(std::locale::classic());
    const auto bits = std::bit_cast<std::uint64_t>(value);
    if ((bits & UINT64_C(0x7ff0000000000000)) == UINT64_C(0x7ff0000000000000))
        out << "{\"nonfinite_binary64_bits\":\"" << std::hex << std::setw(16)
            << std::setfill('0') << bits << "\"}";
    else out << std::setprecision(std::numeric_limits<double>::max_digits10) << value;
    return out.str();
}
struct Object {
    std::string value = "{";
    void add(const char* key, const std::string& encoded) {
        if (value.size() > 1) value += ',';
        value += quote(key) + ':' + encoded;
    }
    void num(const char* key, double x) { add(key, number(x)); }
    void flag(const char* key, bool x) { add(key, x ? "true" : "false"); }
    std::string finish() const { return value + '}'; }
};
template<class Range, class F> std::string array(const Range& values, F encode) {
    std::string result = "[";
    for (const auto& value : values) {
        if (result.size() > 1) result += ',';
        result += encode(value);
    }
    return result + ']';
}
std::string interval(I value) {
    Object out; out.num("lower", value.lower); out.num("upper", value.upper); return out.finish();
}
std::string state_json(const FinalizedLayeredStateValue& value) {
    Object out;
    out.add("encoding", std::to_string(static_cast<int>(value.encoding)));
    out.add("enthalpy_j_m2", value.enthalpy_j_m2 ? number(*value.enthalpy_j_m2) : "null");
    out.add("temperature_k", value.temperature_k ? number(*value.temperature_k) : "null");
    out.add("liquid_water_mass_kg_m2", value.liquid_water_mass_kg_m2 ? number(*value.liquid_water_mass_kg_m2) : "null");
    return out.finish();
}
std::string limits_json(const FinalizedLayeredStateLimits& value) {
    Object out;
#define LIMIT(name) out.add(#name, std::to_string(value.name))
    LIMIT(max_profiles); LIMIT(max_layers_per_profile); LIMIT(max_active_layers);
    LIMIT(max_identifier_bytes); LIMIT(max_observed_geometry_entries); LIMIT(max_receipt_bytes);
#undef LIMIT
    return out.finish();
}
std::string layered_limits_json(const LayeredIceLimits& value) {
    Object out;
#define LIMIT(name) out.add(#name, std::to_string(value.name))
    LIMIT(max_columns); LIMIT(max_layers_per_column); LIMIT(max_thermal_nodes);
    LIMIT(max_edges); LIMIT(max_identifier_bytes);
#undef LIMIT
    return out.finish();
}
std::string owner_limits_json(const LayeredIceOwnerLimits& value) {
    Object out;
#define LIMIT(name) out.add(#name, std::to_string(value.name))
    LIMIT(max_prepare_attempts); LIMIT(max_commits); LIMIT(max_concurrent_preparations);
    LIMIT(max_events_per_transition); LIMIT(max_consumed_events); LIMIT(max_pending_outboxes);
    LIMIT(max_thermal_nodes); LIMIT(max_thermal_edges); LIMIT(max_node_leaves);
    LIMIT(max_receipt_bytes); LIMIT(max_history_bytes); LIMIT(max_private_receipt_bytes);
    LIMIT(max_retained_preparations); LIMIT(max_stored_forcing_values);
#undef LIMIT
    return out.finish();
}
std::string water_json(const cryosphere_prototype::WaterProperties& value) {
    Object out;
    out.num("freezing_temperature_k", value.freezing_temperature_k);
    out.num("solid_heat_capacity_j_kg_k", value.solid_heat_capacity_j_kg_k);
    out.num("liquid_heat_capacity_j_kg_k", value.liquid_heat_capacity_j_kg_k);
    out.num("latent_heat_j_kg", value.latent_heat_j_kg);
    return out.finish();
}
void identity(Object& out) {
    out.add("model", quote("finalized_supplied_layered_state_v1"));
    Object scope;
    scope.add("initialization_policy", quote("explicit_supplied_canonical_layers"));
    scope.add("initial_shortwave_policy", quote("zero_unforced_placeholder_no_timestep"));
    scope.add("top_closure", quote("context_combined_surface_atmosphere_capacity_once"));
    scope.add("enthalpy_scope", quote("complete_thermal_node_relative_to_freezing_temperature"));
    scope.add("inherited_error_scope", quote("conditional_supplied_state_energy_only_at_canonical_water_mass"));
    scope.add("receipt_cap_scope", quote("complete_retained_json_wire_bytes_not_RSS_or_transient_allocations"));
    scope.flag("fixed_refusal_metadata_exempt_from_receipt_cap", true);
    scope.flag("new_owner_lifetime", true);
    scope.flag("prior_transaction_replay_restored", false);
    scope.flag("annual_temperature_or_thickness_initialization", false);
    scope.flag("thermal_advancement", false);
    scope.flag("world_publication", false);
    scope.flag("geometry_or_spatial_error_certified", false);
    scope.flag("original_mass_trajectory_certified", false);
    scope.flag("imported_source_accuracy_certified", false);
    scope.flag("annual_or_equilibrated_glacier_accuracy_certified", false);
    scope.add("dry_surface_positive_deep_policy", quote("existing_builder_refusal_is_a_v1_representation_limit"));
    scope.add("empty_deep_policy", quote("direct_zero_enthalpy_constrained_coordinate_without_temperature"));
    out.add("scope", scope.finish());
}
void identifier(const std::string& value, std::size_t cap) {
    need(!value.empty() && value.size() <= cap, "invalid_identifier", "initializer identifier length");
    for (unsigned char c : value)
        need(c >= 33 && c <= 126, "invalid_identifier", "visible ASCII initializer identifier required");
}
void shape(const FinalizedLayeredStateRequest& q, const std::vector<Cell>& observed,
           const FinalizedEnthalpyContext& context, const SeasonalLiquidRoutingGraph& route) {
    const auto& l = q.limits;
    need(l.max_profiles > 0 && l.max_profiles <= 4096 &&
         l.max_layers_per_profile > 0 && l.max_layers_per_profile <= 32 &&
         l.max_active_layers > 0 && l.max_active_layers <= 16384 &&
         l.max_identifier_bytes > 0 && l.max_identifier_bytes <= 96 &&
         l.max_observed_geometry_entries <= 131072 && l.max_receipt_bytes > 0 &&
         l.max_receipt_bytes <= 67108864,
         "invalid_limits", "initializer limits exceed fixed implementation caps");
    need(q.owner_id.size() <= l.max_identifier_bytes && q.input_id.size() <= l.max_identifier_bytes,
         "shape_cap", "raw identifier retention cap");
    need(q.profiles.size() <= l.max_profiles && observed.size() <= l.max_profiles &&
         context.surface().cells().size() <= l.max_profiles && route.nodes().size() <= l.max_profiles,
         "shape_cap", "profile or geographic source retention cap");
    std::size_t layers = 0;
    for (const auto& p : q.profiles) {
        need(p.layers.size() <= l.max_layers_per_profile && p.layers.size() <= l.max_active_layers - layers,
             "shape_cap", "active layer retention cap");
        layers += p.layers.size();
    }
    const auto geometry_shape = [&](const std::vector<Cell>& cells) {
        std::size_t neighbors = 0, faces = 0, vertices = 0;
        for (const auto& c : cells) {
            need(c.neighbors.size() <= l.max_observed_geometry_entries - neighbors &&
                 c.control_volume_edge_neighbor_ids.size() <= l.max_observed_geometry_entries - faces &&
                 c.control_volume_vertices.size() <= l.max_observed_geometry_entries - vertices,
                 "shape_cap", "geographic geometry retention cap");
            neighbors += c.neighbors.size(); faces += c.control_volume_edge_neighbor_ids.size();
            vertices += c.control_volume_vertices.size();
        }
    };
    geometry_shape(observed); geometry_shape(context.surface().cells());
    std::size_t route_neighbors = 0;
    for (const auto& n : route.nodes()) {
        need(n.neighbors.size() <= l.max_observed_geometry_entries - route_neighbors,
             "shape_cap", "routing geometry retention cap");
        route_neighbors += n.neighbors.size();
    }
}
FinalizedLayeredStateConversion convert(int geo, int local, int layer, bool deep,
    const FinalizedLayeredStateValue& value, double A, double W, double C,
    const cryosphere_prototype::WaterProperties& water) {
    FinalizedLayeredStateConversion out;
    out.geographic_cell_id = geo; out.local_cell_id = local; out.layer_id = layer; out.deep = deep;
    out.supplied_state = value; out.area_m2 = A; out.water_mass_kg_m2 = W;
    out.nonwater_heat_capacity_j_m2_k = C; out.water = water;
    need(std::isfinite(W) && W >= 0, "invalid_water_mass", "explicit finite nonnegative water mass required");
    if (value.encoding == FinalizedLayeredStateEncoding::direct_enthalpy) {
        need(value.enthalpy_j_m2 && !value.temperature_k && !value.liquid_water_mass_kg_m2,
             "invalid_state_encoding", "direct enthalpy requires exactly H and no equilibrium operands");
        need(std::isfinite(*value.enthalpy_j_m2), "invalid_state", "direct enthalpy must be finite");
        out.branch = "direct_enthalpy_identity";
        out.represented_enthalpy_j_m2 = *value.enthalpy_j_m2;
        out.ideal_enthalpy_j_m2 = b::point(*value.enthalpy_j_m2);
        // Identity has exact zero conversion defect, including literal zero.
        return out;
    }
    need(value.encoding == FinalizedLayeredStateEncoding::equilibrium_temperature &&
         !value.enthalpy_j_m2 && value.temperature_k && value.liquid_water_mass_kg_m2,
         "invalid_state_encoding", "equilibrium encoding requires exactly T and explicit liquid mass");
    need(!(deep && W == 0), "undefined_empty_deep_temperature", "massless deep bookkeeping has no temperature");
    const double T = *value.temperature_k, liquid = *value.liquid_water_mass_kg_m2;
    const double Tf = water.freezing_temperature_k;
    need(std::isfinite(T) && T >= 0 && std::isfinite(liquid) && liquid >= 0 && liquid <= W,
         "invalid_state", "equilibrium temperature or liquid mass is outside its domain");
    need((T < Tf && liquid == 0) || (T > Tf && liquid == W) || T == Tf,
         "phase_inconsistent", "equilibrium liquid mass disagrees with supplied temperature branch");
    out.represented_temperature_offset_k = checked(T - Tf);
    const I offset = b::sub(b::point(T), b::point(Tf));
    if (T == Tf) {
        out.branch = "equilibrium_phase_plateau";
        out.represented_latent_enthalpy_j_m2 = checked(liquid * water.latent_heat_j_kg);
        out.represented_enthalpy_j_m2 = out.represented_latent_enthalpy_j_m2;
        out.ideal_enthalpy_j_m2 = b::mul(b::point(liquid), b::point(water.latent_heat_j_kg));
    } else {
        const bool cold = T < Tf;
        const double cp = cold ? water.solid_heat_capacity_j_kg_k : water.liquid_heat_capacity_j_kg_k;
        out.branch = cold ? "equilibrium_solid" : "equilibrium_liquid";
        out.represented_capacity_j_m2_k = checked(C + checked(W * cp));
        out.represented_sensible_enthalpy_j_m2 =
            checked(out.represented_capacity_j_m2_k * out.represented_temperature_offset_k);
        const I sensible = b::mul(b::add(b::point(C), b::mul(b::point(W), b::point(cp))), offset);
        if (cold) {
            out.represented_enthalpy_j_m2 = out.represented_sensible_enthalpy_j_m2;
            out.ideal_enthalpy_j_m2 = sensible;
        } else {
            out.represented_latent_enthalpy_j_m2 = checked(W * water.latent_heat_j_kg);
            out.represented_enthalpy_j_m2 =
                checked(out.represented_latent_enthalpy_j_m2 + out.represented_sensible_enthalpy_j_m2);
            out.ideal_enthalpy_j_m2 =
                b::add(b::mul(b::point(W), b::point(water.latent_heat_j_kg)), sensible);
        }
    }
    out.enthalpy_projection_difference_j_m2 =
        b::sub(b::point(out.represented_enthalpy_j_m2), out.ideal_enthalpy_j_m2);
    // Bound one coordinate's exact projection magnitude at the canonical area.
    // Underflowed represented energy is allowed only with this retained defect.
    out.area_weighted_projection_bound_j =
        b::mul(b::point(A), b::point(b::absmax(out.enthalpy_projection_difference_j_m2)));
    return out;
}
} // namespace

std::string finalized_layered_state_observed_json(const std::vector<Cell>& cells,
    const Params& params, std::uint64_t revision) {
    Object out, planet;
    out.add("revision", std::to_string(revision));
    const auto p = finalized_enthalpy_planet_inputs(params);
    planet.add("mesh_backend", std::to_string(p.mesh_backend));
    planet.num("radius_km", p.radius_km); planet.num("gravity_g", p.gravity_g);
    planet.num("atmosphere_pressure_bar", p.atmosphere_pressure_bar);
    planet.num("reference_infrared_optical_depth", p.reference_infrared_optical_depth);
    planet.num("greenhouse_factor", p.greenhouse_factor);
    out.add("planet_inputs", planet.finish());
    // Union of FinalizedEnthalpyContext::matches and routing::node_matches raw
    // operands. Old climate fields here are binding provenance, not H inputs.
    out.add("cells", array(cells, [](const Cell& c) {
        Object o;
#define INT(name) o.add(#name, std::to_string(c.name))
#define NUM(name) o.num(#name, c.name)
#define FLAG(name) o.flag(#name, c.name)
        INT(id); NUM(area_km2); NUM(elevation_m); NUM(lat); NUM(lon);
        Object p; p.num("x", c.p.x); p.num("y", c.p.y); p.num("z", c.p.z); o.add("p", p.finish());
        FLAG(is_water); FLAG(is_lake); INT(water_body); NUM(water_depth_m);
        NUM(temperature_c); NUM(precipitation_mm_y); NUM(sediment_thickness_m); INT(lithology);
        INT(depression_component_id); INT(depression_sink_cell_id); NUM(spill_elevation_m); NUM(lake_fill_fraction);
        INT(flow_to); FLAG(is_closed_basin); FLAG(lake_overflows); FLAG(hydrologic_surface_conditioned);
        NUM(filled_elevation_m); NUM(hydrologic_surface_elevation_m); NUM(hydrologic_flow_slope);
#undef INT
#undef NUM
#undef FLAG
        o.add("neighbors", array(c.neighbors, [](int v) { return std::to_string(v); }));
        o.add("control_volume_edge_neighbor_ids", array(c.control_volume_edge_neighbor_ids, [](int v) { return std::to_string(v); }));
        o.add("control_volume_vertices", array(c.control_volume_vertices, [](const Vec3& v) {
            Object p; p.num("x", v.x); p.num("y", v.y); p.num("z", v.z); return p.finish();
        }));
        return o.finish();
    }));
    return out.finish();
}

std::string finalized_layered_state_request_json(const FinalizedLayeredStateRequest& q) {
    Object out;
    out.add("policy", std::to_string(static_cast<int>(q.policy)));
    out.add("owner_id", quote(q.owner_id)); out.add("input_id", quote(q.input_id));
    out.flag("complete_horizontal_coverage_declared", q.complete_horizontal_coverage_declared);
    out.add("bottom_boundary", std::to_string(static_cast<int>(q.bottom_boundary)));
    out.num("elapsed_seconds", q.elapsed_seconds); out.num("inherited_energy_error_j", q.inherited_energy_error_j);
    out.num("maximum_joint_energy_error_j", q.maximum_joint_energy_error_j);
    out.add("profiles", array(q.profiles, [](const FinalizedLayeredProfile& p) {
        Object o; o.add("geographic_cell_id", std::to_string(p.geographic_cell_id));
        o.add("layers", array(p.layers, [](const FinalizedLayeredActiveInput& v) {
            Object l; l.add("layer_id", std::to_string(v.layer_id));
            l.num("water_mass_kg_m2", v.water_mass_kg_m2); l.num("density_kg_m3", v.density_kg_m3);
            l.num("conductivity_w_m_k", v.conductivity_w_m_k); l.add("state", state_json(v.state)); return l.finish();
        }));
        if (p.deep_inventory) {
            Object d; d.num("water_mass_kg_m2", p.deep_inventory->water_mass_kg_m2);
            d.num("density_kg_m3", p.deep_inventory->density_kg_m3);
            d.add("state", state_json(p.deep_inventory->state)); o.add("deep_inventory", d.finish());
        } else o.add("deep_inventory", "null");
        return o.finish();
    }));
    out.add("layered_limits", layered_limits_json(q.layered_limits));
    out.add("owner_limits", owner_limits_json(q.owner_limits));
    out.add("limits", limits_json(q.limits));
    return out.finish();
}

std::string finalized_layered_state_receipt_json(const FinalizedLayeredStateReceipt& r) {
    Object out; identity(out);
    out.flag("accepted", r.accepted); out.flag("minimal_refusal_metadata", r.minimal_refusal_metadata);
    out.add("failure_code", quote(r.failure_code)); out.add("detail", quote(r.detail));
    out.add("limits", limits_json(r.limits));
    out.add("request", r.request ? finalized_layered_state_request_json(*r.request) : "null");
    out.add("context", r.context ? finalized_enthalpy_context_json(*r.context) : "null");
    out.add("geographic_epoch", r.geographic_epoch ? seasonal_liquid_routing_graph_json(*r.geographic_epoch) : "null");
    out.add("observed_source", r.observed_source_json.empty() ? "null" : r.observed_source_json);
    out.add("observed_geographic_revision", std::to_string(r.observed_geographic_revision));
    out.flag("context_matches", r.context_matches); out.flag("routing_matches", r.routing_matches);
    out.flag("revisions_match", r.revisions_match);
    out.add("conversions", array(r.conversions, [](const FinalizedLayeredStateConversion& c) {
        Object o;
        o.add("geographic_cell_id", std::to_string(c.geographic_cell_id));
        o.add("local_cell_id", std::to_string(c.local_cell_id)); o.add("layer_id", std::to_string(c.layer_id));
        o.flag("deep", c.deep); o.add("supplied_state", state_json(c.supplied_state)); o.add("branch", quote(c.branch));
        o.add("water", water_json(c.water));
#define NUM(name) o.num(#name, c.name)
        NUM(area_m2); NUM(water_mass_kg_m2); NUM(nonwater_heat_capacity_j_m2_k);
        NUM(represented_temperature_offset_k); NUM(represented_capacity_j_m2_k);
        NUM(represented_sensible_enthalpy_j_m2); NUM(represented_latent_enthalpy_j_m2); NUM(represented_enthalpy_j_m2);
#undef NUM
        o.add("ideal_enthalpy_j_m2", interval(c.ideal_enthalpy_j_m2));
        o.add("enthalpy_projection_difference_j_m2", interval(c.enthalpy_projection_difference_j_m2));
        o.add("area_weighted_projection_bound_j", interval(c.area_weighted_projection_bound_j));
        return o.finish();
    }));
    out.add("canonical_input", r.canonical_input ? layered_ice_input_json(*r.canonical_input) : "null");
    out.add("conversion_error_sum_j", interval(r.conversion_error_sum_j));
    out.num("conversion_error_upper_j", r.conversion_error_upper_j);
    out.num("final_joint_energy_error_j", r.final_joint_energy_error_j);
    out.add("final", r.final ? layered_ice_owner_snapshot_json(*r.final) : "null");
    Object work;
    work.add("owner_constructions_started", std::to_string(r.work.owner_constructions_started));
    work.add("owner_constructions_completed", std::to_string(r.work.owner_constructions_completed));
    work.add("observed_owner_work", r.work.observed_owner_work ? layered_ice_owner_work_json(*r.work.observed_owner_work) : "null");
    out.add("work", work.finish());
    return out.finish();
}

FinalizedLayeredStateInitialization initialize_finalized_layered_state(
    const FinalizedEnthalpyContext& context, const SeasonalLiquidRoutingGraph& route,
    const std::vector<Cell>& observed, const Params& params, std::uint64_t revision,
    const FinalizedLayeredStateRequest& q) {
    FinalizedLayeredStateInitialization result;
    auto& r = result.receipt;
    r.limits = q.limits; r.observed_geographic_revision = revision;
    bool shape_admitted = false;
    try {
        shape(q, observed, context, route); shape_admitted = true;
        r.request = q; r.context = context; r.geographic_epoch = route;
        r.observed_source_json = finalized_layered_state_observed_json(observed, params, revision);
        r.context_matches = context.matches(observed, params);
        r.routing_matches = route.matches(observed);
        r.revisions_match = context.surface().surface_revision() == revision && route.revision() == revision;
        need(r.revisions_match, "source_revision_mismatch", "context, routing and observed revisions must agree");
        need(r.context_matches, "context_mismatch", "observed source or planet differs from finalized context");
        need(r.routing_matches, "routing_mismatch", "observed source differs from independently captured routing epoch");
        need(q.policy == FinalizedLayeredStatePolicy::supplied_canonical_layers_v1,
             "invalid_policy", "explicit supplied canonical layers policy required");
        identifier(q.owner_id, q.limits.max_identifier_bytes); identifier(q.input_id, q.limits.max_identifier_bytes);
        need(q.complete_horizontal_coverage_declared && q.bottom_boundary == LayeredIceBottomBoundary::insulated,
             "invalid_declaration", "complete footprint coverage and insulated bottom must be declared");
        need(std::isfinite(q.elapsed_seconds) && q.elapsed_seconds >= 0 &&
             std::isfinite(q.inherited_energy_error_j) && q.inherited_energy_error_j >= 0 &&
             std::isfinite(q.maximum_joint_energy_error_j) && q.maximum_joint_energy_error_j >= 0 &&
             q.inherited_energy_error_j <= q.maximum_joint_energy_error_j,
             "invalid_budget", "finite initial clock and admitted inherited energy allowance required");
        const std::size_t n = context.properties().columns.size();
        need(n > 0 && q.profiles.size() == n && route.nodes().size() == n,
             "profile_coverage", "profiles must cover every geographic cell exactly once");
        const auto capability = layered_ice_capability();
        need(capability.available, "capability_unavailable", "layered binary64 capability is unavailable");
        std::vector<int> geo_to_local(n, -1), mapping;
        mapping.reserve(n);
        for (std::size_t i = 0; i < n; ++i) {
            const int geo = q.profiles[i].geographic_cell_id;
            need(geo >= 0 && static_cast<std::size_t>(geo) < n && geo_to_local[geo] < 0,
                 "profile_coverage", "geographic profile IDs must form a complete permutation");
            geo_to_local[geo] = static_cast<int>(i); mapping.push_back(geo);
        }
        LayeredIceInput canonical;
        canonical.id = q.input_id; canonical.complete_horizontal_coverage_declared = q.complete_horizontal_coverage_declared;
        canonical.bottom_boundary = q.bottom_boundary; canonical.water = context.properties().water;
        canonical.limits = q.layered_limits; canonical.columns.reserve(n);
        for (std::size_t i = 0; i < n; ++i) {
            const auto& p = q.profiles[i]; const int geo = p.geographic_cell_id;
            const auto& physical = context.properties().columns[geo];
            const auto& source = context.surface().cells()[geo];
            need(!p.layers.empty(), "profile_coverage", "each geographic profile requires its top layer");
            need(!(source.is_water || source.is_lake) ||
                 (p.layers.size() == 1 && p.layers[0].water_mass_kg_m2 == 0 &&
                  (!p.deep_inventory || p.deep_inventory->water_mass_kg_m2 == 0)),
                 "wet_grounded_water", "marine/lake profiles are sole sensible zero-water slabs without positive deep water");
            LayeredIceColumnInput column;
            column.cell_id = static_cast<int>(i); column.area_m2 = physical.area_m2;
            column.top_closure = LayeredIceTopClosure::coarse_combined_surface_atmosphere;
            column.top_nonwater_heat_capacity_j_m2_k = physical.heat_capacity_j_m2_k;
            column.top_longwave_emissivity = physical.longwave_emissivity;
            column.top_absorbed_shortwave_w_m2 = 0;
            for (std::size_t j = 0; j < p.layers.size(); ++j) {
                const auto& layer = p.layers[j];
                need(layer.layer_id == static_cast<int>(j), "profile_coverage", "layer IDs must be complete canonical top-to-bottom order");
                need(std::isfinite(layer.density_kg_m3) && layer.density_kg_m3 > 0 &&
                     std::isfinite(layer.conductivity_w_m_k) && layer.conductivity_w_m_k > 0,
                     "invalid_material", "active density and conductivity must be explicitly positive and finite");
                r.conversions.push_back(convert(geo, static_cast<int>(i), static_cast<int>(j), false,
                    layer.state, physical.area_m2, layer.water_mass_kg_m2,
                    j == 0 ? physical.heat_capacity_j_m2_k : 0, canonical.water));
                const auto& conversion = r.conversions.back();
                r.conversion_error_sum_j = b::add(r.conversion_error_sum_j, conversion.area_weighted_projection_bound_j);
                column.layers.push_back({layer.layer_id, layer.water_mass_kg_m2, conversion.represented_enthalpy_j_m2,
                                         layer.density_kg_m3, layer.conductivity_w_m_k});
            }
            if (p.deep_inventory) {
                const auto& deep = *p.deep_inventory;
                need(std::isfinite(deep.density_kg_m3) && deep.density_kg_m3 > 0,
                     "invalid_material", "deep density must be explicitly positive and finite");
                r.conversions.push_back(convert(geo, static_cast<int>(i), -1, true,
                    deep.state, physical.area_m2, deep.water_mass_kg_m2, 0, canonical.water));
                const auto& conversion = r.conversions.back();
                r.conversion_error_sum_j = b::add(r.conversion_error_sum_j, conversion.area_weighted_projection_bound_j);
                column.deep_inventory = LayeredIceDeepInventoryInput{
                    deep.water_mass_kg_m2, conversion.represented_enthalpy_j_m2, deep.density_kg_m3};
            }
            canonical.columns.push_back(std::move(column));
        }
        canonical.horizontal_climate_edges.reserve(context.properties().edges.size());
        for (const auto& edge : context.properties().edges) {
            int a = geo_to_local[edge.first_cell], z = geo_to_local[edge.second_cell];
            if (a > z) std::swap(a, z);
            canonical.horizontal_climate_edges.push_back({a, z, edge.conductance_w_k});
        }
        // Sorting fixes canonical representation under a caller permutation;
        // neither conductance nor its captured geographic operands change.
        std::sort(canonical.horizontal_climate_edges.begin(), canonical.horizontal_climate_edges.end(),
                  [](const auto& a, const auto& z) {
                      return a.first_cell < z.first_cell || (a.first_cell == z.first_cell && a.second_cell < z.second_cell);
                  });
        r.canonical_input = canonical;
        r.conversion_error_upper_j = r.conversion_error_sum_j.upper;
        r.final_joint_energy_error_j =
            b::add(b::point(q.inherited_energy_error_j), b::point(r.conversion_error_upper_j)).upper;
        need(r.final_joint_energy_error_j <= q.maximum_joint_energy_error_j,
             "conversion_budget", "outward conversion charge exceeds joint energy allowance");
        LayeredIceOwnerSeed seed{q.owner_id, std::move(canonical), q.elapsed_seconds,
            r.final_joint_energy_error_j, route, std::move(mapping), {}, {}, {}};
        ++r.work.owner_constructions_started;
        result.owner = std::make_unique<LayeredIceOwner>(std::move(seed), q.maximum_joint_energy_error_j, q.owner_limits);
        ++r.work.owner_constructions_completed;
        r.work.observed_owner_work = result.owner->work();
        r.final = result.owner->snapshot(); r.accepted = true;
    } catch (const std::bad_alloc&) { throw;
    } catch (const Refusal& e) { r.failure_code = e.code; r.detail = e.what();
    } catch (const LayeredIceError& e) { r.failure_code = e.code; r.detail = e.what();
    } catch (const std::exception& e) { r.failure_code = "arithmetic_refusal"; r.detail = e.what(); }
    if (!r.accepted) { result.owner.reset(); r.final.reset(); }
    // The shape gate precedes raw input retention. The cap measures actual
    // complete standalone receipt spelling after encoding, not peak memory.
    // Even when a constructor succeeded, cap refusal discards that new owner.
    if (!shape_admitted || finalized_layered_state_receipt_json(r).size() > q.limits.max_receipt_bytes) {
        FinalizedLayeredStateReceipt small;
        small.minimal_refusal_metadata = true; small.limits = q.limits;
        small.observed_geographic_revision = revision; small.work = r.work;
        small.failure_code = shape_admitted ? "receipt_cap" : r.failure_code;
        small.detail = shape_admitted ? "complete initializer receipt exceeds retained wire cap; private owner discarded" : r.detail;
        result.owner.reset(); r = std::move(small);
    }
    return result;
}

} // namespace magic_geo::detail
