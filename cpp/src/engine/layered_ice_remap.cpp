#include "layered_ice_remap.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace magic_geo::detail {
namespace {
namespace b = phase_segment_prototype::bounds;
using I = EnthalpyMeshInterval;
constexpr std::uint64_t weight_cap = 4294967296ULL;
struct Refusal : std::runtime_error {
    std::string code;
    Refusal(std::string c, std::string d) : std::runtime_error(std::move(d)), code(std::move(c)) {}
};
void need(bool ok, const char* code, const std::string& detail) {
    if (!ok) throw Refusal(code, detail);
}
bool finite(double x) { return std::isfinite(x); }
double checked(double x) {
    need(finite(x), "arithmetic_refusal", "nonfinite represented remap arithmetic");
    return x;
}
double product(double x, double y) {
    const double value = checked(x * y);
    need(x == 0 || y == 0 || value != 0, "arithmetic_refusal", "nonzero remap product underflow");
    return value;
}
void count(const LayeredIceRemapRequest& q, LayeredIceRemapReceipt& r) {
    need(r.work.arithmetic_groups_started < q.limits.max_arithmetic_groups,
         "work_cap", "remap arithmetic group cap");
    ++r.work.arithmetic_groups_started;
}
void limits_ok(const LayeredIceRemapRequest& q) {
    const auto& l = q.limits;
    need(l.max_columns > 0 && l.max_columns <= 4096 && l.max_active_nodes > 0 && l.max_active_nodes <= 16384 &&
         l.max_donors <= 20480 && l.max_allocations <= 131072 && l.max_arithmetic_groups > 0 &&
         l.max_arithmetic_groups <= 1048576, "invalid_limits", "remap limits exceed implementation bounds");
    need(!q.id.empty() && q.id.size() <= 96 && q.source.id.size() <= 96,
         "invalid_input", "remap identifier length cap");
    for (unsigned char c : q.id) need(c >= 33 && c <= 126, "invalid_input", "remap identifier must be visible ASCII");
    need(!q.source.columns.empty() && q.source.columns.size() <= l.max_columns &&
         q.targets.size() <= l.max_columns && q.donors.size() <= l.max_donors &&
         q.source.horizontal_climate_edges.size() <= 131072,
         "invalid_input", "remap request retention cap");
    std::size_t source_nodes = 0, target_nodes = 0, allocations = 0;
    for (const auto& c : q.source.columns) {
        need(c.layers.size() <= 32 && c.layers.size() <= l.max_active_nodes - source_nodes,
             "invalid_input", "source layer retention cap");
        source_nodes += c.layers.size();
    }
    for (const auto& c : q.targets) {
        need(!c.layers.empty() && c.layers.size() <= 32 && c.layers.size() <= l.max_active_nodes - target_nodes,
             "invalid_input", "target layer retention cap");
        target_nodes += c.layers.size();
    }
    for (const auto& row : q.donors) {
        need(row.allocations.size() <= l.max_allocations - allocations,
             "invalid_input", "allocation retention cap");
        allocations += row.allocations.size();
    }
}
using Key = std::pair<int, int>;
Key key(int cell, LayeredIceRemapLocation location) { return {cell, location.deep ? -1 : location.layer_id}; }
LayeredIceRemapLocation location(int layer) { return {layer < 0, layer}; }
void valid_location(LayeredIceRemapLocation x, std::size_t layers, bool deep) {
    need(x.deep ? x.layer_id == -1 && deep : x.layer_id >= 0 && static_cast<std::size_t>(x.layer_id) < layers,
         "invalid_allocation", "invalid active/deep location");
}
void physical_ball(const LayeredIceRemapRequest& q, LayeredIceRemapReceipt& r,
                   const LayeredIceInput& graph, double E) {
    const auto test = [&](double W, double H, double C, double area, bool constrained_empty) {
        count(q, r);
        if (constrained_empty && W == 0) {
            need(H == 0, "physical_domain_refusal", "massless deep energy is constrained to zero");
            return;
        }
        const I capacity = b::add(b::point(C), b::mul(b::point(W), b::point(graph.water.solid_heat_capacity_j_kg_k)));
        const I floor = b::neg(b::mul(capacity, b::point(graph.water.freezing_temperature_k)));
        const I radius = b::div(b::point(E), b::point(area));
        const I bottom = b::sub(b::point(H), radius);
        need(bottom.lower >= floor.upper, "physical_domain_refusal", "whole global energy ball crosses an absolute-zero floor");
    };
    for (const auto& c : graph.columns) {
        for (const auto& layer : c.layers)
            test(layer.water_mass_kg_m2, layer.enthalpy_j_m2,
                 layer.layer_id == 0 ? c.top_nonwater_heat_capacity_j_m2_k : 0, c.area_m2, false);
        if (c.deep_inventory)
            test(c.deep_inventory->water_mass_kg_m2, c.deep_inventory->enthalpy_j_m2, 0, c.area_m2, true);
    }
}
LayeredIceRemapDecomposition decompose(const LayeredIceColumnInput& c, LayeredIceRemapLocation source,
                                     const cryosphere_prototype::WaterProperties& water) {
    LayeredIceRemapDecomposition d;
    d.cell_id = c.cell_id; d.source = source;
    if (source.deep) {
        d.initial_water_mass_kg_m2 = c.deep_inventory->water_mass_kg_m2;
        d.initial_complete_enthalpy_j_m2 = c.deep_inventory->enthalpy_j_m2;
    } else {
        const auto& layer = c.layers[static_cast<std::size_t>(source.layer_id)];
        d.initial_water_mass_kg_m2 = layer.water_mass_kg_m2;
        d.initial_complete_enthalpy_j_m2 = layer.enthalpy_j_m2;
        if (source.layer_id == 0) d.nonwater_capacity_j_m2_k = c.top_nonwater_heat_capacity_j_m2_k;
    }
    const double W = d.initial_water_mass_kg_m2, H = d.initial_complete_enthalpy_j_m2;
    const double C = d.nonwater_capacity_j_m2_k;
    if (C == 0) {
        d.represented_water_enthalpy_j_m2 = H;
        d.ideal_water_enthalpy_j_m2 = b::point(H);
        return d;
    }
    if (W == 0) {
        d.represented_stationary_nonwater_enthalpy_j_m2 = H;
        d.ideal_stationary_nonwater_enthalpy_j_m2 = b::point(H);
        return d;
    }
    const I solid = b::mul(b::point(W), b::point(water.solid_heat_capacity_j_kg_k));
    const I liquid = b::mul(b::point(W), b::point(water.liquid_heat_capacity_j_kg_k));
    const I Cs = b::add(b::point(C), solid), Cl = b::add(b::point(C), liquid);
    const I latent = b::mul(b::point(W), b::point(water.latent_heat_j_kg));
    const I cold = b::point(std::min(H, 0.0));
    const I excess = b::sub(b::point(H), latent);
    const I warm{std::max(0.0, excess.lower), std::max(0.0, excess.upper)};
    const double positive_H = std::max(0.0, H);
    const I phase{std::min(positive_H, latent.lower), std::min(positive_H, latent.upper)};
    d.ideal_water_enthalpy_j_m2 = b::add(b::add(b::mul(solid, b::div(cold, Cs)), phase),
                                        b::mul(liquid, b::div(warm, Cl)));
    d.ideal_stationary_nonwater_enthalpy_j_m2 = b::mul(b::point(C), b::add(b::div(cold, Cs), b::div(warm, Cl)));
    const double ws = checked(W * water.solid_heat_capacity_j_kg_k);
    const double wl = checked(W * water.liquid_heat_capacity_j_kg_k);
    const double latent_raw = checked(W * water.latent_heat_j_kg);
    const double cold_offset = checked(std::min(H, 0.0) / checked(C + ws));
    const double warm_offset = checked(std::max(0.0, checked(H - latent_raw)) / checked(C + wl));
    d.represented_water_enthalpy_j_m2 = checked(checked(checked(ws * cold_offset) + std::min(positive_H, latent_raw)) +
                                                    checked(wl * warm_offset));
    d.represented_stationary_nonwater_enthalpy_j_m2 = checked(C * checked(cold_offset + warm_offset));
    return d;
}
struct Target {
    double W = 0, H = 0;
    I ideal_W{}, ideal_H{};
};
std::string quote(const std::string& s) {
    std::ostringstream o; o.imbue(std::locale::classic()); o << '"';
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') o << '\\' << static_cast<char>(c);
        else if (c < 32 || c >= 127) o << "\\u00" << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(c);
        else o << static_cast<char>(c);
    }
    o << '"'; return o.str();
}
std::string number(double x) {
    std::ostringstream o; o.imbue(std::locale::classic());
    if (finite(x)) o << std::setprecision(17) << x;
    else o << "{\"nonfinite_binary64_bits\":\"" << std::hex << std::setw(16) << std::setfill('0')
           << std::bit_cast<std::uint64_t>(x) << "\"}";
    return o.str();
}
std::string interval(I x) { return "{\"lower\":" + number(x.lower) + ",\"upper\":" + number(x.upper) + '}'; }
template<class T, class F> std::string array(const std::vector<T>& values, F f) {
    std::string out = "["; bool first = true;
    for (const auto& value : values) { if (!first) out += ','; first = false; out += f(value); }
    return out + ']';
}
struct Object {
    std::string text = "{"; bool first = true;
    void add(const std::string& k, const std::string& v) {
        if (!first) text += ',';
        first = false; text += quote(k) + ':' + v;
    }
    void value(const std::string& k, double v) { add(k, number(v)); }
    std::string finish() { return text + '}'; }
};
std::string location_json(LayeredIceRemapLocation x) {
    Object o; o.add("deep", x.deep ? "true" : "false"); o.add("layer_id", std::to_string(x.layer_id)); return o.finish();
}
} // namespace

LayeredIceRemapReceipt remap_layered_ice(const LayeredIceRemapRequest& q) {
    LayeredIceRemapReceipt r;
    try {
        limits_ok(q); r.request = q;
        need(finite(q.inherited_global_energy_error_j) && q.inherited_global_energy_error_j >= 0 &&
             finite(q.maximum_final_energy_error_j) && q.maximum_final_energy_error_j >= q.inherited_global_energy_error_j,
             "invalid_input", "finite nonnegative inherited error and sufficient budget required");
        ++r.work.source_builder_calls_started;
        r.source_graph = build_layered_ice_graph(q.source);
        physical_ball(q, r, q.source, q.inherited_global_energy_error_j);
        need(q.targets.size() == q.source.columns.size(), "invalid_input", "complete target column coverage required");
        std::map<Key, Target> target;
        LayeredIceInput output = q.source;
        for (std::size_t i = 0; i < q.targets.size(); ++i) {
            const auto& t = q.targets[i];
            need(t.cell_id == static_cast<int>(i), "invalid_input", "canonical target cell IDs required");
            auto& c = output.columns[i]; c.layers.clear(); c.deep_inventory.reset();
            for (std::size_t j = 0; j < t.layers.size(); ++j) {
                const auto& layer = t.layers[j];
                need(layer.layer_id == static_cast<int>(j) && finite(layer.density_kg_m3) && layer.density_kg_m3 > 0 &&
                     finite(layer.conductivity_w_m_k) && layer.conductivity_w_m_k > 0,
                     "invalid_input", "explicit canonical target layer material required");
                c.layers.push_back({layer.layer_id, 0, 0, layer.density_kg_m3, layer.conductivity_w_m_k});
                target.emplace(Key{t.cell_id, layer.layer_id}, Target{});
            }
            if (t.deep_density_kg_m3) {
                need(finite(*t.deep_density_kg_m3) && *t.deep_density_kg_m3 > 0,
                     "invalid_input", "explicit positive target deep density required");
                c.deep_inventory = LayeredIceDeepInventoryInput{0, 0, *t.deep_density_kg_m3};
                target.emplace(Key{t.cell_id, -1}, Target{});
            }
        }
        std::map<Key, const LayeredIceRemapDonor*> donors;
        for (const auto& row : q.donors) {
            need(row.cell_id >= 0 && static_cast<std::size_t>(row.cell_id) < q.source.columns.size(),
                 "invalid_allocation", "donor cell outside source coverage");
            const auto& c = q.source.columns[static_cast<std::size_t>(row.cell_id)];
            const auto& t = q.targets[static_cast<std::size_t>(row.cell_id)];
            valid_location(row.source, c.layers.size(), c.deep_inventory.has_value());
            const double W = row.source.deep ? c.deep_inventory->water_mass_kg_m2 :
                c.layers[static_cast<std::size_t>(row.source.layer_id)].water_mass_kg_m2;
            need(W > 0 && !row.allocations.empty() && donors.emplace(key(row.cell_id, row.source), &row).second,
                 "invalid_allocation", "donor rows must uniquely cover positive water stores");
            std::set<Key> destinations;
            std::uint64_t sum = 0;
            for (const auto& a : row.allocations) {
                valid_location(a.destination, t.layers.size(), t.deep_density_kg_m3.has_value());
                need(a.weight > 0 && a.weight <= weight_cap - sum && destinations.insert(key(row.cell_id, a.destination)).second,
                     "invalid_allocation", "allocation weights must be positive, unique and total at most 2^32");
                sum += a.weight;
            }
        }
        std::vector<LayeredIceRemapDecomposition> decompositions;
        std::vector<LayeredIceRemapTransfer> transfers;
        bool identity = true;
        for (std::size_t i = 0; i < q.source.columns.size(); ++i) {
            const auto& c = q.source.columns[i];
            const auto& t = q.targets[i];
            if (c.layers.size() != t.layers.size() || c.deep_inventory.has_value() != t.deep_density_kg_m3.has_value())
                identity = false;
            const auto process = [&](LayeredIceRemapLocation source) {
                count(q, r);
                const auto d = decompose(c, source, q.source.water);
                decompositions.push_back(d);
                if (!source.deep && source.layer_id == 0) {
                    auto& top = target.at({c.cell_id, 0});
                    top.H = d.represented_stationary_nonwater_enthalpy_j_m2;
                    top.ideal_H = d.ideal_stationary_nonwater_enthalpy_j_m2;
                }
                if (d.initial_water_mass_kg_m2 == 0) return;
                const auto found = donors.find(key(c.cell_id, source));
                need(found != donors.end(), "invalid_allocation", "positive donor missing from complete allocation map");
                const auto& row = *found->second;
                std::uint64_t total = 0;
                for (const auto& a : row.allocations) total += a.weight;
                if (row.allocations.size() != 1 || !(row.allocations.front().destination == source)) identity = false;
                auto allocations = row.allocations;
                std::sort(allocations.begin(), allocations.end(), [](const auto& a, const auto& z) {
                    return std::pair{a.destination.deep, a.destination.layer_id} < std::pair{z.destination.deep, z.destination.layer_id};
                });
                for (const auto& a : allocations) {
                    count(q, r);
                    LayeredIceRemapTransfer transfer;
                    transfer.cell_id = c.cell_id; transfer.source = source; transfer.destination = a.destination;
                    transfer.weight = a.weight; transfer.total_weight = total;
                    const bool whole = a.weight == total;
                    transfer.represented_fraction = whole ? 1 : static_cast<double>(a.weight) / static_cast<double>(total);
                    transfer.ideal_fraction = whole ? b::point(1) : b::div(b::point(static_cast<double>(a.weight)), b::point(static_cast<double>(total)));
                    transfer.represented_water_mass_kg_m2 = whole ? d.initial_water_mass_kg_m2 :
                        product(d.initial_water_mass_kg_m2, transfer.represented_fraction);
                    transfer.represented_water_enthalpy_j_m2 = whole ? d.represented_water_enthalpy_j_m2 :
                        checked(d.represented_water_enthalpy_j_m2 * transfer.represented_fraction);
                    transfer.ideal_water_mass_kg_m2 = b::mul(b::point(d.initial_water_mass_kg_m2), transfer.ideal_fraction);
                    transfer.ideal_water_enthalpy_j_m2 = b::mul(d.ideal_water_enthalpy_j_m2, transfer.ideal_fraction);
                    auto& destination = target.at(key(c.cell_id, a.destination));
                    destination.W = checked(destination.W + transfer.represented_water_mass_kg_m2);
                    destination.H = checked(destination.H + transfer.represented_water_enthalpy_j_m2);
                    destination.ideal_W = b::add(destination.ideal_W, transfer.ideal_water_mass_kg_m2);
                    destination.ideal_H = b::add(destination.ideal_H, transfer.ideal_water_enthalpy_j_m2);
                    transfers.push_back(transfer); ++r.work.allocations_completed;
                }
                ++r.work.donors_completed;
            };
            for (const auto& layer : c.layers) process({false, layer.layer_id});
            if (c.deep_inventory) process({true, -1});
        }
        need(r.work.donors_completed == q.donors.size(), "invalid_allocation", "allocation donor coverage mismatch");
        // For a whole-location identity, qw+qC equals the original complete H
        // exactly. Preserve that mathematical identity without summation noise.
        // Geometry descriptors may change; this shortcut concerns state only.
        if (identity) {
            for (const auto& c : q.source.columns) {
                for (const auto& layer : c.layers) {
                    auto& x = target.at({c.cell_id, layer.layer_id});
                    x = {layer.water_mass_kg_m2, layer.enthalpy_j_m2,
                         b::point(layer.water_mass_kg_m2), b::point(layer.enthalpy_j_m2)};
                }
                if (c.deep_inventory) {
                    const auto& deep = *c.deep_inventory;
                    target.at({c.cell_id, -1}) = {deep.water_mass_kg_m2, deep.enthalpy_j_m2,
                                                 b::point(deep.water_mass_kg_m2), b::point(deep.enthalpy_j_m2)};
                }
            }
        }
        I defect{};
        std::vector<LayeredIceRemapProjection> projections;
        for (const auto& [id, x] : target) {
            count(q, r);
            LayeredIceRemapProjection p;
            p.cell_id = id.first; p.destination = location(id.second);
            p.represented_water_mass_kg_m2 = x.W; p.represented_complete_enthalpy_j_m2 = x.H;
            p.ideal_water_mass_kg_m2 = x.ideal_W; p.ideal_complete_enthalpy_j_m2 = x.ideal_H;
            p.mass_projection_difference_kg_m2 = b::sub(b::point(x.W), x.ideal_W);
            p.enthalpy_projection_difference_j_m2 = b::sub(b::point(x.H), x.ideal_H);
            p.exact_identity_used = identity;
            const double area = output.columns[static_cast<std::size_t>(id.first)].area_m2;
            defect = b::add(defect, b::mul(b::point(area), b::point(b::absmax(p.enthalpy_projection_difference_j_m2))));
            auto& c = output.columns[static_cast<std::size_t>(id.first)];
            if (id.second < 0) { c.deep_inventory->water_mass_kg_m2 = x.W; c.deep_inventory->enthalpy_j_m2 = x.H; }
            else {
                auto& layer = c.layers[static_cast<std::size_t>(id.second)];
                layer.water_mass_kg_m2 = x.W; layer.enthalpy_j_m2 = x.H;
            }
            projections.push_back(p); ++r.work.targets_completed;
        }
        const double E = b::add(b::point(q.inherited_global_energy_error_j), b::point(defect.upper)).upper;
        need(E <= q.maximum_final_energy_error_j, "energy_budget_refusal", "energy projection exhausts final global error budget");
        ++r.work.output_builder_calls_started;
        auto graph = build_layered_ice_graph(output);
        physical_ball(q, r, output, E);
        LayeredIceRemapFinal result{std::move(graph), 0, 0, {}, {}, {}, {}, {}};
        result.energy_projection_defect_upper_j = defect.upper; result.final_global_energy_error_j = E;
        result.represented_total_mass_change_kg = identity ? I{} : b::sub(result.graph.inventories().combined.exact_mass_kg,
                                                                         r.source_graph->inventories().combined.exact_mass_kg);
        result.represented_total_enthalpy_change_j = identity ? I{} : b::sub(result.graph.inventories().combined.exact_enthalpy_j,
                                                                            r.source_graph->inventories().combined.exact_enthalpy_j);
        result.decompositions = std::move(decompositions); result.transfers = std::move(transfers);
        result.projections = std::move(projections); r.final = std::move(result); r.accepted = true;
    } catch (const Refusal& error) { r.failure_code = error.code; r.detail = error.what(); }
      catch (const LayeredIceError& error) { r.failure_code = error.code; r.detail = error.what(); }
      catch (const std::runtime_error& error) { r.failure_code = "arithmetic_refusal"; r.detail = error.what(); }
    return r;
}

std::string layered_ice_remap_request_json(const LayeredIceRemapRequest& q) {
    Object o; o.add("id", quote(q.id)); o.add("source", layered_ice_input_json(q.source));
    o.value("inherited_global_energy_error_j", q.inherited_global_energy_error_j);
    o.value("maximum_final_energy_error_j", q.maximum_final_energy_error_j);
    Object limits;
    limits.add("max_columns", std::to_string(q.limits.max_columns));
    limits.add("max_active_nodes", std::to_string(q.limits.max_active_nodes));
    limits.add("max_donors", std::to_string(q.limits.max_donors));
    limits.add("max_allocations", std::to_string(q.limits.max_allocations));
    limits.add("max_arithmetic_groups", std::to_string(q.limits.max_arithmetic_groups));
    o.add("limits", limits.finish());
    o.add("targets", array(q.targets, [](const auto& t) {
        Object x; x.add("cell_id", std::to_string(t.cell_id));
        x.add("layers", array(t.layers, [](const auto& layer) {
            Object l; l.add("layer_id", std::to_string(layer.layer_id));
            l.value("density_kg_m3", layer.density_kg_m3); l.value("conductivity_w_m_k", layer.conductivity_w_m_k);
            return l.finish();
        }));
        x.add("deep_density_kg_m3", t.deep_density_kg_m3 ? number(*t.deep_density_kg_m3) : "null");
        return x.finish();
    }));
    o.add("donors", array(q.donors, [](const auto& donor) {
        Object d; d.add("cell_id", std::to_string(donor.cell_id)); d.add("source", location_json(donor.source));
        d.add("allocations", array(donor.allocations, [](const auto& a) {
            Object x; x.add("destination", location_json(a.destination)); x.add("weight", std::to_string(a.weight));
            return x.finish();
        }));
        return d.finish();
    }));
    return o.finish();
}
std::string layered_ice_remap_receipt_json(const LayeredIceRemapReceipt& r) {
    Object o; o.add("model", quote("fixed_canonical_water_homogeneous_layer_remap_v1"));
    o.add("accepted", r.accepted ? "true" : "false"); o.add("failure_code", quote(r.failure_code)); o.add("detail", quote(r.detail));
    o.add("request", r.request ? layered_ice_remap_request_json(*r.request) : "null");
    o.add("source_graph", r.source_graph ? layered_ice_graph_json(*r.source_graph) : "null");
    o.add("allocation_scope", quote("same_column_complete_exact_integer_normalized_water_allocations_v1"));
    o.add("energy_error_scope", quote("global_area_weighted_enthalpy_l1_inherited_once_plus_projection_v1"));
    o.add("nonwater_energy_scope", quote("stationary_geographic_top_capacity_and_energy_v1"));
    o.add("empty_deep_error_scope", quote("zero_mass_deep_energy_exactly_zero_not_independent_error_coordinate_v1"));
    o.add("mass_scope", quote("canonical_represented_output_water_with_separate_projection_bounds_v1"));
    o.add("target_material_scope", quote("explicit_density_conductivity_geometry_replacement_not_volume_conservation_v1"));
    o.add("original_mass_trajectory_certified", "false"); o.add("imported_source_accuracy_certified", "false");
    o.add("geometry_conversion_error_certified", "false"); o.add("spatial_discretization_error_certified", "false");
    o.add("external_water_source_or_sink", "false"); o.add("phase_selective_drainage", "false");
    o.add("ordinary_generation_changed", "false");
    Object work;
#define W(k) work.add(#k, std::to_string(r.work.k))
    W(source_builder_calls_started); W(output_builder_calls_started); W(donors_completed);
    W(allocations_completed); W(targets_completed); W(arithmetic_groups_started);
#undef W
    o.add("work", work.finish());
    if (!r.final) { o.add("final", "null"); return o.finish(); }
    const auto& result = *r.final;
    Object f; f.add("graph", layered_ice_graph_json(result.graph));
    f.value("energy_projection_defect_upper_j", result.energy_projection_defect_upper_j);
    f.value("final_global_energy_error_j", result.final_global_energy_error_j);
    f.add("represented_total_mass_change_kg", interval(result.represented_total_mass_change_kg));
    f.add("represented_total_enthalpy_change_j", interval(result.represented_total_enthalpy_change_j));
    f.add("decompositions", array(result.decompositions, [](const auto& d) {
        Object x; x.add("cell_id", std::to_string(d.cell_id)); x.add("source", location_json(d.source));
        x.value("initial_water_mass_kg_m2", d.initial_water_mass_kg_m2);
        x.value("initial_complete_enthalpy_j_m2", d.initial_complete_enthalpy_j_m2);
        x.value("nonwater_capacity_j_m2_k", d.nonwater_capacity_j_m2_k);
        x.value("represented_water_enthalpy_j_m2", d.represented_water_enthalpy_j_m2);
        x.value("represented_stationary_nonwater_enthalpy_j_m2", d.represented_stationary_nonwater_enthalpy_j_m2);
        x.add("ideal_water_enthalpy_j_m2", interval(d.ideal_water_enthalpy_j_m2));
        x.add("ideal_stationary_nonwater_enthalpy_j_m2", interval(d.ideal_stationary_nonwater_enthalpy_j_m2));
        return x.finish();
    }));
    f.add("transfers", array(result.transfers, [](const auto& t) {
        Object x; x.add("cell_id", std::to_string(t.cell_id)); x.add("source", location_json(t.source));
        x.add("destination", location_json(t.destination)); x.add("weight", std::to_string(t.weight));
        x.add("total_weight", std::to_string(t.total_weight)); x.value("represented_fraction", t.represented_fraction);
        x.add("ideal_fraction", interval(t.ideal_fraction));
        x.value("represented_water_mass_kg_m2", t.represented_water_mass_kg_m2);
        x.value("represented_water_enthalpy_j_m2", t.represented_water_enthalpy_j_m2);
        x.add("ideal_water_mass_kg_m2", interval(t.ideal_water_mass_kg_m2));
        x.add("ideal_water_enthalpy_j_m2", interval(t.ideal_water_enthalpy_j_m2));
        return x.finish();
    }));
    f.add("projections", array(result.projections, [](const auto& p) {
        Object x; x.add("cell_id", std::to_string(p.cell_id)); x.add("destination", location_json(p.destination));
        x.value("represented_water_mass_kg_m2", p.represented_water_mass_kg_m2);
        x.value("represented_complete_enthalpy_j_m2", p.represented_complete_enthalpy_j_m2);
        x.add("ideal_water_mass_kg_m2", interval(p.ideal_water_mass_kg_m2));
        x.add("ideal_complete_enthalpy_j_m2", interval(p.ideal_complete_enthalpy_j_m2));
        x.add("mass_projection_difference_kg_m2", interval(p.mass_projection_difference_kg_m2));
        x.add("enthalpy_projection_difference_j_m2", interval(p.enthalpy_projection_difference_j_m2));
        x.add("exact_identity_used", p.exact_identity_used ? "true" : "false");
        return x.finish();
    }));
    o.add("final", f.finish()); return o.finish();
}

} // namespace magic_geo::detail
