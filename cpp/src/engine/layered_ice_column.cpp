#include "layered_ice_column.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <algorithm>
#include <bit>
#include <cfenv>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <set>
#include <sstream>
#include <utility>

namespace magic_geo::detail {
namespace {
namespace b = phase_segment_prototype::bounds;
using I = EnthalpyMeshInterval;
void need(bool ok, const char* code, const std::string& detail) {
    if (!ok) throw LayeredIceError(code, detail);
}
bool finite(double x) { return std::isfinite(x); }
double positive(double x) {
    need(finite(x) && x > 0, "arithmetic_refusal", "positive conversion overflow or underflow");
    return x;
}
double signed_product(double x, double y) {
    const double value = x * y;
    need(finite(value) && (x == 0 || y == 0 || value != 0),
         "arithmetic_refusal", "inventory product overflow or underflow");
    return value;
}
double sum(double x, double y) {
    const double value = x + y;
    need(finite(value), "arithmetic_refusal", "represented inventory/depth sum overflow");
    return value;
}
void limits_ok(const LayeredIceLimits& l) {
    need(l.max_columns > 0 && l.max_columns <= 4096 && l.max_layers_per_column > 0 &&
         l.max_layers_per_column <= 32 && l.max_thermal_nodes > 0 && l.max_thermal_nodes <= 16384 &&
         l.max_edges <= 131072 && l.max_identifier_bytes > 0 && l.max_identifier_bytes <= 96,
         "invalid_limits", "layered graph bounds exceed fixed implementation limits");
}
void physical_state(double W, double H, double C, const cryosphere_prototype::WaterProperties& w) {
    need(finite(W) && W >= 0 && finite(H), "invalid_input", "invalid layer mass or enthalpy");
    need(C > 0 || W > 0, "invalid_input", "thermal node has no sensible storage");
    const I solid_capacity = b::add(b::point(C), b::mul(b::point(W), b::point(w.solid_heat_capacity_j_kg_k)));
    const I liquid_capacity = b::add(b::point(C), b::mul(b::point(W), b::point(w.liquid_heat_capacity_j_kg_k)));
    need(solid_capacity.lower > 0 && liquid_capacity.lower > 0,
         "arithmetic_refusal", "strictly positive effective capacities must be outward-proved");
    const I floor = b::neg(b::mul(solid_capacity, b::point(w.freezing_temperature_k)));
    need(H >= floor.upper, "physical_domain_refusal", "initial enthalpy not proved above absolute-zero floor");
    const I latent = b::mul(b::point(W), b::point(w.latent_heat_j_kg));
    const I excess = b::sub(b::point(H), latent);
    const I cold{std::min(0.0, H), std::min(0.0, H)};
    const I warm{std::max(0.0, excess.lower), std::max(0.0, excess.upper)};
    // Evaluating the actual law at the initial state also rejects overflow in
    // latent storage or a hot state divided by an extremely small capacity.
    // The floor above proves physicality; no enthalpy/temperature is clipped.
    const I initial_temperature = b::add(b::point(w.freezing_temperature_k),
        b::add(b::div(cold, solid_capacity), b::div(warm, liquid_capacity)));
    need(initial_temperature.upper >= 0, "physical_domain_refusal", "initial temperature enclosure has no physical value");
}
LayeredIceInventoryConversion inventory(double area, double W, double H) {
    LayeredIceInventoryConversion x;
    x.represented_mass_kg = signed_product(area, W);
    x.represented_enthalpy_j = signed_product(area, H);
    x.exact_mass_kg = b::mul(b::point(area), b::point(W));
    x.exact_enthalpy_j = b::mul(b::point(area), b::point(H));
    x.mass_conversion_difference_kg = b::sub(b::point(x.represented_mass_kg), x.exact_mass_kg);
    x.enthalpy_conversion_difference_j = b::sub(b::point(x.represented_enthalpy_j), x.exact_enthalpy_j);
    return x;
}
void accumulate(LayeredIceInventoryConversion& x, const LayeredIceInventoryConversion& item) {
    x.represented_mass_kg = sum(x.represented_mass_kg, item.represented_mass_kg);
    x.represented_enthalpy_j = sum(x.represented_enthalpy_j, item.represented_enthalpy_j);
    x.exact_mass_kg = b::add(x.exact_mass_kg, item.exact_mass_kg);
    x.exact_enthalpy_j = b::add(x.exact_enthalpy_j, item.exact_enthalpy_j);
    x.mass_conversion_difference_kg = b::sub(b::point(x.represented_mass_kg), x.exact_mass_kg);
    x.enthalpy_conversion_difference_j = b::sub(b::point(x.represented_enthalpy_j), x.exact_enthalpy_j);
}
LayeredIceGeometryConversion geometry(double W, double rho) {
    LayeredIceGeometryConversion x;
    x.represented_thickness_m = W == 0 ? 0 : positive(W / rho);
    x.exact_thickness_m = b::div(b::point(W), b::point(rho));
    x.thickness_conversion_difference_m = b::sub(b::point(x.represented_thickness_m), x.exact_thickness_m);
    x.thickness_mass_reconstruction_difference_kg_m2 =
        b::sub(b::mul(b::point(rho), b::point(x.represented_thickness_m)), b::point(W));
    return x;
}
LayeredIceVerticalEdge vertical(const LayeredIceColumnInput& c,
                               const LayeredIceNode& first, const LayeredIceNode& second) {
    LayeredIceVerticalEdge x;
    x.first_thermal_node = first.thermal_node_id;
    x.second_thermal_node = second.thermal_node_id;
    x.area_m2 = c.area_m2;
    x.first_thickness_m = first.geometry.represented_thickness_m;
    x.second_thickness_m = second.geometry.represented_thickness_m;
    x.first_conductivity_w_m_k = c.layers[static_cast<std::size_t>(first.layer_id)].conductivity_w_m_k;
    x.second_conductivity_w_m_k = c.layers[static_cast<std::size_t>(second.layer_id)].conductivity_w_m_k;
    x.represented_first_half_resistance_m2_k_w = positive((x.first_thickness_m / 2) / x.first_conductivity_w_m_k);
    x.represented_second_half_resistance_m2_k_w = positive((x.second_thickness_m / 2) / x.second_conductivity_w_m_k);
    x.represented_total_resistance_m2_k_w = positive(
        x.represented_first_half_resistance_m2_k_w + x.represented_second_half_resistance_m2_k_w);
    x.represented_conductance_w_k = positive(x.area_m2 / x.represented_total_resistance_m2_k_w);
    x.exact_first_half_resistance_m2_k_w = b::div(
        b::mul(first.geometry.exact_thickness_m, b::point(.5)), b::point(x.first_conductivity_w_m_k));
    x.exact_second_half_resistance_m2_k_w = b::div(
        b::mul(second.geometry.exact_thickness_m, b::point(.5)), b::point(x.second_conductivity_w_m_k));
    x.exact_total_resistance_m2_k_w = b::add(
        x.exact_first_half_resistance_m2_k_w, x.exact_second_half_resistance_m2_k_w);
    x.exact_conductance_w_k = b::div(b::point(x.area_m2), x.exact_total_resistance_m2_k_w);
    x.first_half_resistance_difference_m2_k_w = b::sub(
        b::point(x.represented_first_half_resistance_m2_k_w), x.exact_first_half_resistance_m2_k_w);
    x.second_half_resistance_difference_m2_k_w = b::sub(
        b::point(x.represented_second_half_resistance_m2_k_w), x.exact_second_half_resistance_m2_k_w);
    x.total_resistance_difference_m2_k_w = b::sub(
        b::point(x.represented_total_resistance_m2_k_w), x.exact_total_resistance_m2_k_w);
    x.conductance_difference_w_k = b::sub(b::point(x.represented_conductance_w_k), x.exact_conductance_w_k);
    return x;
}
std::string quote(const std::string& text) {
    std::ostringstream o; o.imbue(std::locale::classic()); o << '"';
    for (unsigned char c : text) {
        if (c == '"' || c == '\\') o << '\\' << static_cast<char>(c);
        else if (c < 32 || c >= 127)
            o << "\\u00" << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(c);
        else o << static_cast<char>(c);
    }
    o << '"'; return o.str();
}
std::string number(double value) {
    std::ostringstream o; o.imbue(std::locale::classic());
    if (finite(value)) o << std::setprecision(17) << value;
    else o << "{\"nonfinite_binary64_bits\":\"" << std::hex << std::setw(16) << std::setfill('0')
           << std::bit_cast<std::uint64_t>(value) << "\"}";
    return o.str();
}
std::string interval(I x) { return "{\"lower\":" + number(x.lower) + ",\"upper\":" + number(x.upper) + '}'; }
template<class T, class F> std::string array(const std::vector<T>& xs, F f) {
    std::string out = "["; bool first = true;
    for (const auto& x : xs) { if (!first) out += ','; first = false; out += f(x); }
    return out + ']';
}
struct Object {
    std::string text = "{"; bool first = true;
    void add(const std::string& key, const std::string& value) {
        if (!first) text += ',';
        first = false; text += quote(key) + ':' + value;
    }
    void value(const std::string& key, double value) { add(key, number(value)); }
    std::string finish() { return text + '}'; }
};
std::string closure_name(LayeredIceTopClosure value) {
    switch (value) {
        case LayeredIceTopClosure::unspecified: return "unspecified";
        case LayeredIceTopClosure::prescribed_top_energy: return "prescribed_top_energy";
        case LayeredIceTopClosure::prescribed_nonwater_top_capacity: return "prescribed_nonwater_top_capacity";
        case LayeredIceTopClosure::coarse_combined_surface_atmosphere: return "coarse_combined_surface_atmosphere";
    }
    return "unknown_enum_" + std::to_string(static_cast<int>(value));
}
std::string boundary_name(LayeredIceBottomBoundary value) {
    switch (value) {
        case LayeredIceBottomBoundary::unspecified: return "unspecified";
        case LayeredIceBottomBoundary::insulated: return "insulated";
    }
    return "unknown_enum_" + std::to_string(static_cast<int>(value));
}
std::string inventory_json(const LayeredIceInventoryConversion& x) {
    Object o;
    o.value("represented_mass_kg", x.represented_mass_kg);
    o.value("represented_enthalpy_j", x.represented_enthalpy_j);
    o.add("exact_mass_kg", interval(x.exact_mass_kg));
    o.add("exact_enthalpy_j", interval(x.exact_enthalpy_j));
    o.add("mass_conversion_difference_kg", interval(x.mass_conversion_difference_kg));
    o.add("enthalpy_conversion_difference_j", interval(x.enthalpy_conversion_difference_j));
    return o.finish();
}
std::string geometry_json(const LayeredIceGeometryConversion& x) {
    Object o; o.value("represented_thickness_m", x.represented_thickness_m);
    o.add("exact_thickness_m", interval(x.exact_thickness_m));
    o.add("thickness_conversion_difference_m", interval(x.thickness_conversion_difference_m));
    o.add("thickness_mass_reconstruction_difference_kg_m2", interval(x.thickness_mass_reconstruction_difference_kg_m2));
    return o.finish();
}
} // namespace

LayeredIceError::LayeredIceError(std::string c, std::string detail)
    : std::runtime_error(c + ": " + detail), code(std::move(c)) {}
LayeredIceCapability layered_ice_capability() {
#if defined(__FAST_MATH__)
    return {false, "fast_math_unsupported"};
#else
    if (!(std::numeric_limits<double>::is_iec559 && std::numeric_limits<double>::radix == 2 &&
          std::numeric_limits<double>::digits == 53 && sizeof(double) == 8 && std::fegetround() == FE_TONEAREST))
        return {false, "requires_binary64_round_to_nearest"};
    volatile double normal = std::numeric_limits<double>::min(), tiny = std::numeric_limits<double>::denorm_min();
    volatile double half = .5, one = 1;
    const double subnormal = normal * half, retained = tiny * one;
    if (!(subnormal > 0 && subnormal < normal && retained == std::numeric_limits<double>::denorm_min()))
        return {false, "requires_gradual_underflow"};
    return {true, "binary64_nearest_gradual_underflow"};
#endif
}
struct LayeredIceGraph::Data {
    LayeredIceInput input;
    EnthalpyMeshRequest mesh;
    std::vector<LayeredIceNode> nodes;
    std::vector<int> top_ids;
    std::vector<LayeredIceVerticalEdge> vertical_edges;
    std::vector<LayeredIceDeepInventory> deep;
    LayeredIceInventories inventories;
};
LayeredIceGraph::LayeredIceGraph(std::shared_ptr<const Data> d) : data_(std::move(d)) {}
const LayeredIceInput& LayeredIceGraph::input() const { return data_->input; }
const std::vector<LayeredIceNode>& LayeredIceGraph::nodes() const { return data_->nodes; }
const std::vector<int>& LayeredIceGraph::top_thermal_node_ids() const { return data_->top_ids; }
const std::vector<LayeredIceVerticalEdge>& LayeredIceGraph::vertical_edges() const { return data_->vertical_edges; }
const std::vector<LayeredIceDeepInventory>& LayeredIceGraph::deep_inventories() const { return data_->deep; }
const LayeredIceInventories& LayeredIceGraph::inventories() const { return data_->inventories; }
const EnthalpyMeshRequest& LayeredIceGraph::mesh_request() const { return data_->mesh; }
EnthalpyMeshRequest LayeredIceGraph::make_mesh_request(const EnthalpyMeshOptions& options) const {
    auto q = data_->mesh; q.options = options; q.options.allow_pure_water_columns = true; return q;
}

LayeredIceGraph build_layered_ice_graph(const LayeredIceInput& input) {
    try {
        limits_ok(input.limits);
        const auto& limits = input.limits;
        need(!input.id.empty() && input.id.size() <= limits.max_identifier_bytes,
             "invalid_input", "invalid graph identifier length");
        for (unsigned char c : input.id)
            need(c >= 33 && c <= 126, "invalid_input", "graph identifier must be visible ASCII");
        need(input.complete_horizontal_coverage_declared, "invalid_input", "complete horizontal coverage declaration required");
        need(input.bottom_boundary == LayeredIceBottomBoundary::insulated,
             "invalid_input", "explicit insulated lower boundary required");
        const auto n = input.columns.size();
        need(n > 0 && n <= limits.max_columns, "invalid_input", "horizontal column count cap");
        need(input.horizontal_climate_edges.size() <= limits.max_edges, "invalid_input", "horizontal edge count cap");
        std::size_t nodes = 0, edges = input.horizontal_climate_edges.size();
        for (const auto& c : input.columns) {
            need(!c.layers.empty() && c.layers.size() <= limits.max_layers_per_column,
                 "invalid_input", "complete nonempty per-column layer coverage required");
            need(c.layers.size() <= limits.max_thermal_nodes - nodes, "invalid_input", "thermal node count cap");
            nodes += c.layers.size();
            need(c.layers.size() - 1 <= limits.max_edges - edges, "invalid_input", "combined edge count cap");
            edges += c.layers.size() - 1;
        }
        const auto capability = layered_ice_capability();
        need(capability.available, "capability_unavailable", capability.reason);
        for (double x : {input.water.freezing_temperature_k, input.water.solid_heat_capacity_j_kg_k,
                         input.water.liquid_heat_capacity_j_kg_k, input.water.latent_heat_j_kg})
            need(finite(x) && x > 0, "invalid_input", "explicit positive water properties required");
        std::set<std::pair<int, int>> edge_ids;
        for (const auto& e : input.horizontal_climate_edges) {
            need(e.first_cell >= 0 && e.second_cell > e.first_cell && static_cast<std::size_t>(e.second_cell) < n &&
                 finite(e.conductance_w_k) && e.conductance_w_k > 0 && edge_ids.insert({e.first_cell, e.second_cell}).second,
                 "invalid_input", "invalid, duplicate or noncanonical horizontal edge");
        }
        // Validate all supplied physical records before retaining/copying them.
        for (std::size_t i = 0; i < n; ++i) {
            const auto& c = input.columns[i];
            need(c.cell_id == static_cast<int>(i), "invalid_input", "canonical complete horizontal IDs required");
            need(finite(c.area_m2) && c.area_m2 > 0 && finite(c.top_nonwater_heat_capacity_j_m2_k) &&
                 c.top_nonwater_heat_capacity_j_m2_k >= 0, "invalid_input", "invalid area or top capacity");
            need(finite(c.top_longwave_emissivity) && c.top_longwave_emissivity >= 0 && c.top_longwave_emissivity <= 1 &&
                 finite(c.top_absorbed_shortwave_w_m2) && c.top_absorbed_shortwave_w_m2 >= 0,
                 "invalid_input", "invalid prescribed top radiation");
            const bool pure = c.top_closure == LayeredIceTopClosure::prescribed_top_energy;
            const bool capacity = c.top_closure == LayeredIceTopClosure::prescribed_nonwater_top_capacity ||
                                  c.top_closure == LayeredIceTopClosure::coarse_combined_surface_atmosphere;
            need((pure && c.top_nonwater_heat_capacity_j_m2_k == 0) ||
                 (capacity && c.top_nonwater_heat_capacity_j_m2_k > 0),
                 "invalid_input", "top closure must explicitly describe the supplied nonwater capacity");
            for (std::size_t j = 0; j < c.layers.size(); ++j) {
                const auto& layer = c.layers[j];
                need(layer.layer_id == static_cast<int>(j), "invalid_input", "canonical complete ordered layer IDs required");
                need(finite(layer.density_kg_m3) && layer.density_kg_m3 > 0 &&
                     finite(layer.conductivity_w_m_k) && layer.conductivity_w_m_k > 0,
                     "invalid_input", "explicit positive density and conductivity required");
                need(layer.water_mass_kg_m2 > 0 || (j == 0 && c.layers.size() == 1),
                     "invalid_input", "zero-water nodes cannot conduct to deeper layers");
                physical_state(layer.water_mass_kg_m2, layer.enthalpy_j_m2,
                               j == 0 ? c.top_nonwater_heat_capacity_j_m2_k : 0, input.water);
            }
            if (c.deep_inventory) {
                const auto& deep = *c.deep_inventory;
                need(finite(deep.water_mass_kg_m2) && deep.water_mass_kg_m2 >= 0 && finite(deep.enthalpy_j_m2) &&
                     finite(deep.density_kg_m3) && deep.density_kg_m3 > 0,
                     "invalid_input", "invalid explicit deep inventory");
                need(deep.water_mass_kg_m2 > 0 || deep.enthalpy_j_m2 == 0,
                     "invalid_input", "empty deep inventory must have zero enthalpy");
                need(c.layers.front().water_mass_kg_m2 > 0 || deep.water_mass_kg_m2 == 0,
                     "invalid_input", "zero-water surface cannot hide a deep ice inventory");
                if (deep.water_mass_kg_m2 > 0)
                    physical_state(deep.water_mass_kg_m2, deep.enthalpy_j_m2, 0, input.water);
            }
        }
        auto d = std::make_shared<LayeredIceGraph::Data>();
        d->input = input; d->mesh.water = input.water;
        d->nodes.reserve(nodes); d->top_ids.reserve(n); d->vertical_edges.reserve(edges - input.horizontal_climate_edges.size());
        d->mesh.columns.reserve(nodes); d->mesh.edges.reserve(edges);
        d->mesh.water_mass_kg_m2.reserve(nodes); d->mesh.initial_enthalpy_j_m2.reserve(nodes);
        d->mesh.absorbed_shortwave_w_m2.reserve(nodes);
        for (const auto& c : input.columns) {
            d->top_ids.push_back(static_cast<int>(d->nodes.size()));
            double depth = 0; I exact_depth{};
            for (const auto& layer : c.layers) {
                LayeredIceNode node;
                node.thermal_node_id = static_cast<int>(d->nodes.size());
                node.cell_id = c.cell_id; node.layer_id = layer.layer_id;
                node.geometry = geometry(layer.water_mass_kg_m2, layer.density_kg_m3);
                node.inventory = inventory(c.area_m2, layer.water_mass_kg_m2, layer.enthalpy_j_m2);
                node.represented_depth_begin_m = depth; node.exact_depth_begin_m = exact_depth;
                depth = sum(depth, node.geometry.represented_thickness_m);
                exact_depth = b::add(exact_depth, node.geometry.exact_thickness_m);
                node.represented_depth_end_m = depth; node.exact_depth_end_m = exact_depth;
                node.depth_begin_difference_m = b::sub(b::point(node.represented_depth_begin_m), node.exact_depth_begin_m);
                node.depth_end_difference_m = b::sub(b::point(node.represented_depth_end_m), node.exact_depth_end_m);
                accumulate(d->inventories.active, node.inventory);
                d->nodes.push_back(node);
                const bool top = layer.layer_id == 0;
                d->mesh.columns.push_back({c.area_m2, top ? c.top_nonwater_heat_capacity_j_m2_k : 0,
                                           top ? c.top_longwave_emissivity : 0});
                d->mesh.water_mass_kg_m2.push_back(layer.water_mass_kg_m2);
                d->mesh.initial_enthalpy_j_m2.push_back(layer.enthalpy_j_m2);
                d->mesh.absorbed_shortwave_w_m2.push_back(top ? c.top_absorbed_shortwave_w_m2 : 0);
                if (!top) {
                    const auto edge = vertical(c, d->nodes[d->nodes.size() - 2], node);
                    d->vertical_edges.push_back(edge);
                    d->mesh.edges.push_back({edge.first_thermal_node, edge.second_thermal_node, edge.represented_conductance_w_k});
                }
            }
            if (c.deep_inventory) {
                const auto& deep = *c.deep_inventory;
                LayeredIceDeepInventory item;
                item.cell_id = c.cell_id;
                item.geometry = geometry(deep.water_mass_kg_m2, deep.density_kg_m3);
                item.inventory = inventory(c.area_m2, deep.water_mass_kg_m2, deep.enthalpy_j_m2);
                accumulate(d->inventories.deep, item.inventory);
                d->deep.push_back(item);
            }
        }
        for (const auto& edge : input.horizontal_climate_edges)
            d->mesh.edges.push_back({d->top_ids[static_cast<std::size_t>(edge.first_cell)],
                                    d->top_ids[static_cast<std::size_t>(edge.second_cell)], edge.conductance_w_k});
        // Stable canonical order makes the retained thermal graph independently
        // replayable without depending on the input edge order.
        std::sort(d->mesh.edges.begin(), d->mesh.edges.end(), [](const auto& x, const auto& y) {
            return std::pair{x.first_cell, x.second_cell} < std::pair{y.first_cell, y.second_cell};
        });
        accumulate(d->inventories.combined, d->inventories.active);
        accumulate(d->inventories.combined, d->inventories.deep);
        return LayeredIceGraph(std::move(d));
    } catch (const LayeredIceError&) { throw; }
      catch (const std::runtime_error& e) { throw LayeredIceError("arithmetic_refusal", e.what()); }
}

std::string layered_ice_input_json(const LayeredIceInput& input) {
    Object o; o.add("id", quote(input.id));
    o.add("complete_horizontal_coverage_declared", input.complete_horizontal_coverage_declared ? "true" : "false");
    o.add("bottom_boundary", quote(boundary_name(input.bottom_boundary)));
    Object water;
    water.value("freezing_temperature_k", input.water.freezing_temperature_k);
    water.value("solid_heat_capacity_j_kg_k", input.water.solid_heat_capacity_j_kg_k);
    water.value("liquid_heat_capacity_j_kg_k", input.water.liquid_heat_capacity_j_kg_k);
    water.value("latent_heat_j_kg", input.water.latent_heat_j_kg);
    o.add("water", water.finish());
    Object limits;
    limits.add("max_columns", std::to_string(input.limits.max_columns));
    limits.add("max_layers_per_column", std::to_string(input.limits.max_layers_per_column));
    limits.add("max_thermal_nodes", std::to_string(input.limits.max_thermal_nodes));
    limits.add("max_edges", std::to_string(input.limits.max_edges));
    limits.add("max_identifier_bytes", std::to_string(input.limits.max_identifier_bytes));
    o.add("limits", limits.finish());
    o.add("columns", array(input.columns, [](const auto& c) {
        Object x; x.add("cell_id", std::to_string(c.cell_id)); x.value("area_m2", c.area_m2);
        x.add("top_closure", quote(closure_name(c.top_closure)));
        x.value("top_nonwater_heat_capacity_j_m2_k", c.top_nonwater_heat_capacity_j_m2_k);
        x.value("top_longwave_emissivity", c.top_longwave_emissivity);
        x.value("top_absorbed_shortwave_w_m2", c.top_absorbed_shortwave_w_m2);
        x.add("layers", array(c.layers, [](const auto& l) {
            Object y; y.add("layer_id", std::to_string(l.layer_id));
            y.value("water_mass_kg_m2", l.water_mass_kg_m2); y.value("enthalpy_j_m2", l.enthalpy_j_m2);
            y.value("density_kg_m3", l.density_kg_m3); y.value("conductivity_w_m_k", l.conductivity_w_m_k);
            return y.finish();
        }));
        if (c.deep_inventory) {
            Object deep;
            deep.value("water_mass_kg_m2", c.deep_inventory->water_mass_kg_m2);
            deep.value("enthalpy_j_m2", c.deep_inventory->enthalpy_j_m2);
            deep.value("density_kg_m3", c.deep_inventory->density_kg_m3);
            x.add("deep_inventory", deep.finish());
        } else x.add("deep_inventory", "null");
        return x.finish();
    }));
    o.add("horizontal_climate_edges", array(input.horizontal_climate_edges, [](const auto& edge) {
        Object x; x.add("first_cell", std::to_string(edge.first_cell));
        x.add("second_cell", std::to_string(edge.second_cell)); x.value("conductance_w_k", edge.conductance_w_k);
        return x.finish();
    }));
    return o.finish();
}
std::string layered_ice_graph_json(const LayeredIceGraph& graph) {
    Object o; o.add("model", quote("fixed_geometry_layered_ice_thermal_graph_v1"));
    o.add("input", layered_ice_input_json(graph.input()));
    o.add("mesh", enthalpy_mesh_request_json(graph.make_mesh_request({})));
    o.add("geometry_scope", quote("prescribed_fixed_mass_density_conductivity_v1"));
    o.add("mass_area_scope", quote("full_horizontal_footprint_coverage_fraction_one_v1"));
    o.add("conductance_scope", quote("equal_area_center_to_center_series_resistance_v1"));
    o.add("conversion_scope", quote("canonical_binary64_operands_outward_bounds_v1"));
    o.add("active_enthalpy_scope", quote("thermal_nodes_including_declared_top_nonwater_capacity_v1"));
    o.add("deep_enthalpy_scope", quote("pure_water_relative_to_solid_at_freezing_temperature_v1"));
    o.add("combined_enthalpy_scope", quote("active_thermal_nodes_plus_isolated_deep_water_not_ice_only_v1"));
    o.add("original_source_accuracy_certified", "false");
    o.add("geometry_conversion_error_in_thermal_certificate", "false");
    o.add("source_operations_supported", "false");
    o.add("deep_reservoir_thermally_coupled", "false");
    o.add("geothermal_flux_resolved", "false");
    o.add("water_percolation_resolved", "false");
    o.add("material_remapping_supported", "false");
    o.add("ordinary_generation_changed", "false");
    o.add("world_horizontal_coverage_authenticated", "false");
    o.add("top_thermal_node_ids", array(graph.top_thermal_node_ids(), [](int id) { return std::to_string(id); }));
    o.add("nodes", array(graph.nodes(), [](const auto& node) {
        Object x; x.add("thermal_node_id", std::to_string(node.thermal_node_id));
        x.add("cell_id", std::to_string(node.cell_id)); x.add("layer_id", std::to_string(node.layer_id));
        x.add("geometry", geometry_json(node.geometry)); x.add("inventory", inventory_json(node.inventory));
        x.value("represented_depth_begin_m", node.represented_depth_begin_m);
        x.value("represented_depth_end_m", node.represented_depth_end_m);
        x.add("exact_depth_begin_m", interval(node.exact_depth_begin_m));
        x.add("exact_depth_end_m", interval(node.exact_depth_end_m));
        x.add("depth_begin_difference_m", interval(node.depth_begin_difference_m));
        x.add("depth_end_difference_m", interval(node.depth_end_difference_m));
        return x.finish();
    }));
    o.add("vertical_edges", array(graph.vertical_edges(), [](const auto& edge) {
        Object x; x.add("first_thermal_node", std::to_string(edge.first_thermal_node));
        x.add("second_thermal_node", std::to_string(edge.second_thermal_node));
#define V(k) x.value(#k, edge.k)
        V(area_m2); V(first_thickness_m); V(second_thickness_m);
        V(first_conductivity_w_m_k); V(second_conductivity_w_m_k);
        V(represented_first_half_resistance_m2_k_w); V(represented_second_half_resistance_m2_k_w);
        V(represented_total_resistance_m2_k_w); V(represented_conductance_w_k);
#undef V
#define B(k) x.add(#k, interval(edge.k))
        B(exact_first_half_resistance_m2_k_w); B(exact_second_half_resistance_m2_k_w);
        B(exact_total_resistance_m2_k_w); B(exact_conductance_w_k);
        B(first_half_resistance_difference_m2_k_w); B(second_half_resistance_difference_m2_k_w);
        B(total_resistance_difference_m2_k_w); B(conductance_difference_w_k);
#undef B
        return x.finish();
    }));
    o.add("deep_inventories", array(graph.deep_inventories(), [](const auto& deep) {
        Object x; x.add("cell_id", std::to_string(deep.cell_id));
        x.add("geometry", geometry_json(deep.geometry)); x.add("inventory", inventory_json(deep.inventory));
        return x.finish();
    }));
    Object totals;
    totals.add("active", inventory_json(graph.inventories().active));
    totals.add("deep", inventory_json(graph.inventories().deep));
    totals.add("combined", inventory_json(graph.inventories().combined));
    o.add("inventories", totals.finish());
    return o.finish();
}

} // namespace magic_geo::detail
