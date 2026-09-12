#include "layered_ice_topology.hpp"
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
    need(finite(x), "arithmetic_refusal", "nonfinite represented topology arithmetic");
    return x;
}
double product(double x, double y) {
    const double value = checked(x * y);
    need(x == 0 || y == 0 || value != 0, "arithmetic_refusal", "nonzero topology product underflow");
    return value;
}
void count(const LayeredIceTopologyRequest& q, LayeredIceTopologyReceipt& r) {
    need(r.work.arithmetic_groups_started < q.limits.max_arithmetic_groups,
         "work_cap", "topology arithmetic group cap");
    ++r.work.arithmetic_groups_started;
}
void limits_ok(const LayeredIceTopologyRequest& q) {
    const auto& l = q.limits;
    need(l.max_columns > 0 && l.max_columns <= 4096 && l.max_active_nodes > 0 && l.max_active_nodes <= 16384 &&
         l.max_donors <= 20480 && l.max_allocations <= 131072 && l.max_exports <= 4096 && l.max_arithmetic_groups > 0 &&
         l.max_arithmetic_groups <= 1048576, "invalid_limits", "topology limits exceed implementation bounds");
    need(!q.id.empty() && q.id.size() <= 96 && q.source.id.size() <= 96,
         "invalid_input", "topology identifier length cap");
    for (unsigned char c : q.id) need(c >= 33 && c <= 126, "invalid_input", "topology identifier must be visible ASCII");
    need(!q.source.columns.empty() && q.source.columns.size() <= l.max_columns &&
         q.targets.size() <= l.max_columns && q.donors.size() <= l.max_donors && q.exports.size() <= l.max_exports &&
         q.source.horizontal_climate_edges.size() <= 131072,
         "invalid_input", "topology request retention cap");
    for (const auto& e : q.exports) {
        need(!e.id.empty() && e.id.size() <= 96, "invalid_export", "export identifier length cap");
        for (unsigned char c : e.id) need(c >= 33 && c <= 126, "invalid_export", "export identifier must be visible ASCII");
    }
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
void physical_ball(const LayeredIceTopologyRequest& q, LayeredIceTopologyReceipt& r,
                   const LayeredIceInput& graph, double E, bool final) {
    auto& records = final ? r.final_domain : r.source_domain;
    const auto test = [&](const LayeredIceColumnInput& c, int layer, double W, double H, double C) {
        count(q, r);
        records.push_back({{c.cell_id, layer}, c.area_m2, W, H, C, E, {}, {}, layer < 0 && W == 0, false});
        auto& record = records.back();
        if (record.constrained_empty_deep) {
            need(H == 0, "physical_domain_refusal", "massless deep energy is constrained to zero");
            record.proved = true;
            return;
        }
        const I capacity = b::add(b::point(C), b::mul(b::point(W), b::point(graph.water.solid_heat_capacity_j_kg_k)));
        record.physical_floor_j_m2 = b::neg(b::mul(capacity, b::point(graph.water.freezing_temperature_k)));
        const I radius = b::div(b::point(E), b::point(c.area_m2));
        record.enthalpy_ball_j_m2 = b::add(b::point(H), {-radius.upper, radius.upper});
        need(record.enthalpy_ball_j_m2.lower >= record.physical_floor_j_m2.upper,
             "physical_domain_refusal", "whole global energy ball crosses an absolute-zero floor");
        record.proved = true;
    };
    for (const auto& c : graph.columns) {
        for (const auto& layer : c.layers)
            test(c, layer.layer_id, layer.water_mass_kg_m2, layer.enthalpy_j_m2,
                 layer.layer_id == 0 ? c.top_nonwater_heat_capacity_j_m2_k : 0);
        if (c.deep_inventory)
            test(c, -1, c.deep_inventory->water_mass_kg_m2, c.deep_inventory->enthalpy_j_m2, 0);
    }
}
// A zero FMA residual proves the product only when its exact binary64 product
// grid cannot extend below the minimum subnormal. This is deliberately a
// sufficient test: extreme exactly representable products may still refuse.
bool exact_product(double x, double y, double raw) {
    if (!finite(raw)) return false;
    if (x == 0 || y == 0) return true;
    if (x == 1 || y == 1) return true;
    int ex = 0, ey = 0;
    (void)std::frexp(x, &ex); (void)std::frexp(y, &ey);
    return ex + ey - 2 * std::numeric_limits<double>::digits >=
           std::numeric_limits<double>::min_exponent - std::numeric_limits<double>::digits &&
           std::fma(x, y, -raw) == 0;
}
I exact_or_outward_product(double x, double y) {
    const double raw = checked(x * y);
    return exact_product(x, y, raw) ? b::point(raw) : b::mul(b::point(x), b::point(y));
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
std::string address_json(LayeredMaterialAddress a) {
    Object o; o.add("cell_id", std::to_string(a.cell_id)); o.add("layer_id", std::to_string(a.layer_id)); return o.finish();
}
std::string selection_json(const LayeredIceWholeInventoryExport& e) {
    Object o; o.add("id", quote(e.id)); o.add("donor", address_json(e.donor));
    o.add("phase", std::to_string(static_cast<int>(e.phase))); return o.finish();
}
std::string parcel_json(const LayeredMaterialParcelCertificate& p) {
    Object m; m.add("id", quote(p.movement.id)); m.add("donor", address_json(p.movement.donor));
    m.add("recipient", address_json(p.movement.recipient)); m.add("phase", std::to_string(static_cast<int>(p.movement.phase)));
    m.value("mass_kg", p.movement.mass_kg); m.value("import_temperature_k", p.movement.import_temperature_k);
    Object o; o.add("movement", m.finish()); o.value("donor_temperature_k", p.donor_temperature_k);
    o.value("specific_enthalpy_j_kg", p.specific_enthalpy_j_kg); o.value("carried_enthalpy_j", p.carried_enthalpy_j);
    o.add("ideal_specific_enthalpy_j_kg", interval(p.ideal_specific_enthalpy_j_kg));
    o.add("ideal_carried_enthalpy_j", interval(p.ideal_carried_enthalpy_j));
    o.add("energy_projection_j", interval(p.energy_projection_j)); o.add("external_outbox", p.external_outbox ? "true" : "false");
    return o.finish();
}
std::string domain_json(const LayeredIceTopologyDomain& d) {
    Object o; o.add("address", address_json(d.address));
    o.value("area_m2", d.area_m2); o.value("water_mass_kg_m2", d.water_mass_kg_m2); o.value("enthalpy_j_m2", d.enthalpy_j_m2);
    o.value("nonwater_capacity_j_m2_k", d.nonwater_capacity_j_m2_k); o.value("global_energy_error_j", d.global_energy_error_j);
    o.add("enthalpy_ball_j_m2", interval(d.enthalpy_ball_j_m2)); o.add("physical_floor_j_m2", interval(d.physical_floor_j_m2));
    o.add("constrained_empty_deep", d.constrained_empty_deep ? "true" : "false"); o.add("proved", d.proved ? "true" : "false");
    return o.finish();
}
} // namespace

LayeredIceTopologyReceipt apply_layered_ice_topology(const LayeredIceTopologyRequest& q) {
    LayeredIceTopologyReceipt r;
    try {
        limits_ok(q); r.request = q;
        need(finite(q.inherited_global_energy_error_j) && q.inherited_global_energy_error_j >= 0 &&
             finite(q.maximum_final_energy_error_j) && q.maximum_final_energy_error_j >= q.inherited_global_energy_error_j,
             "invalid_input", "finite nonnegative inherited error and sufficient budget required");
        ++r.work.source_builder_calls_started;
        r.source_graph = build_layered_ice_graph(q.source);
        physical_ball(q, r, q.source, q.inherited_global_energy_error_j, false);
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
        std::map<Key, const LayeredIceWholeInventoryExport*> exports;
        std::set<std::string> export_ids;
        for (const auto& e : q.exports) {
            need(e.donor.cell_id >= 0 && static_cast<std::size_t>(e.donor.cell_id) < q.source.columns.size() &&
                 e.donor.layer_id >= -1, "invalid_export", "export donor outside source coverage");
            const auto& c = q.source.columns[static_cast<std::size_t>(e.donor.cell_id)];
            valid_location(location(e.donor.layer_id), c.layers.size(), c.deep_inventory.has_value());
            const double W = e.donor.layer_id < 0 ? c.deep_inventory->water_mass_kg_m2 :
                c.layers[static_cast<std::size_t>(e.donor.layer_id)].water_mass_kg_m2;
            const Key source{e.donor.cell_id, e.donor.layer_id};
            need(W > 0 && !donors.contains(source) && exports.emplace(source, &e).second && export_ids.insert(e.id).second,
                 "invalid_export", "exports must uniquely own positive donors absent from allocation rows");
            need(e.phase == cryosphere_prototype::Phase::solid || e.phase == cryosphere_prototype::Phase::liquid,
                 "invalid_export", "export phase must be solid or liquid");
        }
        I outbox_defect{};
        std::vector<LayeredMaterialParcelCertificate> parcels;
        bool identity = q.exports.empty();
        for (std::size_t i = 0; i < q.source.columns.size(); ++i) {
            const auto& c = q.source.columns[i];
            const auto& t = q.targets[i];
            if (c.layers.size() != t.layers.size() || c.deep_inventory.has_value() != t.deep_density_kg_m3.has_value())
                identity = false;
            const auto process = [&](LayeredIceRemapLocation source) {
                count(q, r);
                const auto d = decompose(c, source, q.source.water);
                r.decompositions.push_back(d);
                if (!source.deep && source.layer_id == 0) {
                    auto& top = target.at({c.cell_id, 0});
                    top.H = d.represented_stationary_nonwater_enthalpy_j_m2;
                    top.ideal_H = d.ideal_stationary_nonwater_enthalpy_j_m2;
                }
                if (d.initial_water_mass_kg_m2 == 0) return;
                const auto exported = exports.find(key(c.cell_id, source));
                if (exported != exports.end()) {
                    count(q, r);
                    r.export_certificates.push_back({});
                    auto& certificate = r.export_certificates.back();
                    certificate.selection = *exported->second;
                    certificate.source_area_m2 = c.area_m2;
                    certificate.source_water_mass_kg_m2 = d.initial_water_mass_kg_m2;
                    certificate.source_complete_enthalpy_j_m2 = d.initial_complete_enthalpy_j_m2;
                    certificate.source_nonwater_capacity_j_m2_k = d.nonwater_capacity_j_m2_k;
                    const double mass = checked(c.area_m2 * d.initial_water_mass_kg_m2);
                    certificate.represented_full_mass_kg = mass;
                    certificate.exact_full_mass_kg = exact_or_outward_product(c.area_m2, d.initial_water_mass_kg_m2);
                    certificate.exact_mass_representable = mass > 0 && exact_product(c.area_m2, d.initial_water_mass_kg_m2, mass);
                    need(certificate.exact_mass_representable, "unrepresentable_whole_export_mass",
                         "entire donor A*W must be positive finite and provably exactly binary64-representable");
                    const I Q = exact_or_outward_product(c.area_m2, d.initial_complete_enthalpy_j_m2);
                    certificate.source_complete_energy_ball_j = b::add(Q, {-q.inherited_global_energy_error_j, q.inherited_global_energy_error_j});
                    certificate.full_latent_energy_j = exact_or_outward_product(mass, q.source.water.latent_heat_j_kg);
                    certificate.whole_phase_proved = certificate.selection.phase == cryosphere_prototype::Phase::solid ?
                        certificate.source_complete_energy_ball_j.upper <= 0 :
                        certificate.source_complete_energy_ball_j.lower >= certificate.full_latent_energy_j.upper;
                    need(certificate.whole_phase_proved, "uncertain_whole_export_phase", "full donor error ball does not have the selected phase");
                    auto& p = certificate.parcel;
                    p.movement = {certificate.selection.id, certificate.selection.donor, {-1, -1},
                                  certificate.selection.phase, mass, 0};
                    p.external_outbox = true;
                    p.ideal_specific_enthalpy_j_kg = b::div(d.ideal_water_enthalpy_j_m2, b::point(d.initial_water_mass_kg_m2));
                    p.specific_enthalpy_j_kg = checked(d.represented_water_enthalpy_j_m2 / d.initial_water_mass_kg_m2);
                    p.ideal_carried_enthalpy_j = b::mul(b::point(c.area_m2), d.ideal_water_enthalpy_j_m2);
                    p.carried_enthalpy_j = checked(c.area_m2 * d.represented_water_enthalpy_j_m2);
                    p.energy_projection_j = b::sub(b::point(p.carried_enthalpy_j), p.ideal_carried_enthalpy_j);
                    // Temperature is diagnostic. Saved J is the direct A*qw
                    // projection above and is never reconstructed from it.
                    const long double W = d.initial_water_mass_kg_m2, H = d.initial_complete_enthalpy_j_m2;
                    const long double C = d.nonwater_capacity_j_m2_k;
                    const auto& water = q.source.water;
                    const long double offset = certificate.selection.phase == cryosphere_prototype::Phase::solid ?
                        H / (C + W * water.solid_heat_capacity_j_kg_k) :
                        (H - W * water.latent_heat_j_kg) / (C + W * water.liquid_heat_capacity_j_kg_k);
                    p.donor_temperature_k = checked(static_cast<double>(static_cast<long double>(water.freezing_temperature_k) + offset));
                    need(p.donor_temperature_k >= 0, "arithmetic_refusal", "nonphysical represented donor diagnostic temperature");
                    outbox_defect = b::add(outbox_defect, b::point(b::absmax(p.energy_projection_j)));
                    r.exported_mass_kg = b::add(r.exported_mass_kg, b::point(mass));
                    r.exported_energy_j = b::add(r.exported_energy_j, b::point(p.carried_enthalpy_j));
                    parcels.push_back(p); ++r.work.exports_completed;
                    return;
                }
                const auto found = donors.find(key(c.cell_id, source));
                need(found != donors.end(), "invalid_allocation", "positive donor missing from complete allocation/export map");
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
                    r.transfers.push_back(transfer); ++r.work.allocations_completed;
                }
                ++r.work.donors_completed;
            };
            for (const auto& layer : c.layers) process({false, layer.layer_id});
            if (c.deep_inventory) process({true, -1});
        }
        need(r.work.donors_completed == q.donors.size() && r.work.exports_completed == q.exports.size(), "invalid_allocation", "allocation donor coverage mismatch");
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
        I output_mass{}, output_energy{};
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
            output_mass = b::add(output_mass, b::mul(b::point(area), b::point(x.W)));
            output_energy = b::add(output_energy, b::mul(b::point(area), b::point(x.H)));
            r.projections.push_back(p); ++r.work.targets_completed;
        }
        r.retained_energy_defect_upper_j = defect.upper;
        r.outbox_energy_defect_upper_j = outbox_defect.upper;
        r.retained_mass_change_kg = identity ? I{} : b::sub(output_mass, r.source_graph->inventories().combined.exact_mass_kg);
        r.retained_energy_change_j = identity ? I{} : b::sub(output_energy, r.source_graph->inventories().combined.exact_enthalpy_j);
        r.mass_balance_residual_kg = b::add(r.retained_mass_change_kg, r.exported_mass_kg);
        r.energy_balance_residual_j = b::add(r.retained_energy_change_j, r.exported_energy_j);
        const double E = b::add(b::add(b::point(q.inherited_global_energy_error_j),
                                      b::point(defect.upper)), b::point(outbox_defect.upper)).upper;
        r.final_global_energy_error_j = E;
        need(E <= q.maximum_final_energy_error_j, "energy_budget_refusal", "joint final projection exhausts global error budget");
        ++r.work.output_builder_calls_started;
        auto graph = build_layered_ice_graph(output);
        physical_ball(q, r, output, E, true);
        r.final = LayeredIceTopologyFinal{std::move(graph), std::move(parcels), defect.upper, outbox_defect.upper, E};
        r.accepted = true;
    } catch (const Refusal& error) { r.failure_code = error.code; r.detail = error.what(); }
      catch (const LayeredIceError& error) { r.failure_code = error.code; r.detail = error.what(); }
      catch (const std::runtime_error& error) { r.failure_code = "arithmetic_refusal"; r.detail = error.what(); }
    return r;
}

std::string layered_ice_topology_request_json(const LayeredIceTopologyRequest& q) {
    Object o; o.add("id", quote(q.id)); o.add("source", layered_ice_input_json(q.source));
    o.value("inherited_global_energy_error_j", q.inherited_global_energy_error_j);
    o.value("maximum_final_energy_error_j", q.maximum_final_energy_error_j);
    Object limits;
    limits.add("max_columns", std::to_string(q.limits.max_columns));
    limits.add("max_active_nodes", std::to_string(q.limits.max_active_nodes));
    limits.add("max_donors", std::to_string(q.limits.max_donors));
    limits.add("max_allocations", std::to_string(q.limits.max_allocations));
    limits.add("max_arithmetic_groups", std::to_string(q.limits.max_arithmetic_groups));
    limits.add("max_exports", std::to_string(q.limits.max_exports));
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
    o.add("exports", array(q.exports, [](const auto& e) {
        Object x; x.add("id", quote(e.id));
        Object address; address.add("cell_id", std::to_string(e.donor.cell_id)); address.add("layer_id", std::to_string(e.donor.layer_id));
        x.add("donor", address.finish()); x.add("phase", std::to_string(static_cast<int>(e.phase))); return x.finish();
    }));
    return o.finish();
}
std::string layered_ice_topology_receipt_json(const LayeredIceTopologyReceipt& r) {
    Object o; o.add("model", quote("fixed_canonical_whole_donor_export_and_homogeneous_topology_v1"));
    o.add("accepted", r.accepted ? "true" : "false"); o.add("failure_code", quote(r.failure_code)); o.add("detail", quote(r.detail));
    o.add("request", r.request ? layered_ice_topology_request_json(*r.request) : "null");
    o.add("source_graph", r.source_graph ? layered_ice_graph_json(*r.source_graph) : "null");
    o.add("allocation_scope", quote("complete_initial_positive_donors_owned_once_by_same_column_exact_weight_rows_or_whole_exports_v1"));
    o.add("energy_error_scope", quote("global_retained_and_old_outbox_l1_inherited_once_plus_direct_final_retained_and_new_outbox_projection_v1"));
    o.add("nonwater_energy_scope", quote("stationary_geographic_top_capacity_and_energy_v1"));
    o.add("deleted_coordinate_scope", quote("ideal_structural_zero_after_complete_water_allocation_not_unchecked_raw_subtraction_v1"));
    o.add("empty_deep_error_scope", quote("zero_mass_deep_energy_exactly_zero_not_independent_error_coordinate_v1"));
    o.add("export_mass_scope", quote("exact_representable_source_area_times_entire_canonical_donor_W_or_refusal_v1"));
    o.add("export_energy_scope", quote("saved_J_direct_projection_of_area_times_water_enthalpy_not_rounded_temperature_v1"));
    o.add("export_phase_scope", quote("entire_initial_marginal_global_error_ball_declared_solid_or_liquid_v1"));
    o.add("mass_scope", quote("canonical_represented_output_water_with_separate_projection_bounds_v1"));
    o.add("target_material_scope", quote("explicit_density_conductivity_geometry_replacement_not_volume_conservation_v1"));
    o.add("target_layer_id_scope", quote("explicit_complete_canonical_target_order_old_parcel_layer_ids_remain_historical_v1"));
    o.add("builder_scope", quote("existing_nonempty_active_graph_and_dry_top_deep_policy_unchanged_v1"));
    o.add("old_pending_outbox_scope", quote("identity_coordinates_retained_by_joint_owner_v1"));
    o.add("original_mass_trajectory_certified", "false"); o.add("imported_source_accuracy_certified", "false");
    o.add("geometry_conversion_error_certified", "false"); o.add("spatial_discretization_error_certified", "false");
    o.add("external_imports", "false"); o.add("autonomous_ablation_policy", "false");
    o.add("ordinary_generation_changed", "false"); o.add("thermal_or_calorimeter_calls", "0");
    Object work;
#define W(k) work.add(#k, std::to_string(r.work.k))
    W(source_builder_calls_started); W(output_builder_calls_started); W(donors_completed);
    W(allocations_completed); W(exports_completed); W(targets_completed); W(arithmetic_groups_started);
#undef W
    o.add("work", work.finish());
    o.add("source_domain", array(r.source_domain, domain_json)); o.add("final_domain", array(r.final_domain, domain_json));
    o.value("retained_energy_defect_upper_j", r.retained_energy_defect_upper_j);
    o.value("outbox_energy_defect_upper_j", r.outbox_energy_defect_upper_j);
    o.value("final_global_energy_error_j", r.final_global_energy_error_j);
#define IVAL(k) o.add(#k, interval(r.k))
    IVAL(retained_mass_change_kg); IVAL(exported_mass_kg); IVAL(mass_balance_residual_kg);
    IVAL(retained_energy_change_j); IVAL(exported_energy_j); IVAL(energy_balance_residual_j);
#undef IVAL
    o.add("export_certificates", array(r.export_certificates, [](const auto& c) {
        Object x; x.add("selection", selection_json(c.selection));
        x.value("source_area_m2", c.source_area_m2); x.value("source_water_mass_kg_m2", c.source_water_mass_kg_m2);
        x.value("source_complete_enthalpy_j_m2", c.source_complete_enthalpy_j_m2);
        x.value("source_nonwater_capacity_j_m2_k", c.source_nonwater_capacity_j_m2_k);
        x.value("represented_full_mass_kg", c.represented_full_mass_kg); x.add("exact_full_mass_kg", interval(c.exact_full_mass_kg));
        x.add("source_complete_energy_ball_j", interval(c.source_complete_energy_ball_j));
        x.add("full_latent_energy_j", interval(c.full_latent_energy_j));
        x.add("exact_mass_representable", c.exact_mass_representable ? "true" : "false");
        x.add("whole_phase_proved", c.whole_phase_proved ? "true" : "false");
        x.add("parcel", parcel_json(c.parcel)); return x.finish();
    }));
    o.add("decompositions", array(r.decompositions, [](const auto& d) {
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
    o.add("transfers", array(r.transfers, [](const auto& t) {
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
    o.add("projections", array(r.projections, [](const auto& p) {
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
    if (!r.final) { o.add("final", "null"); return o.finish(); }
    const auto& result = *r.final;
    Object f; f.add("graph", layered_ice_graph_json(result.graph)); f.add("parcels", array(result.parcels, parcel_json));
    f.value("retained_energy_defect_upper_j", result.retained_energy_defect_upper_j);
    f.value("outbox_energy_defect_upper_j", result.outbox_energy_defect_upper_j);
    f.value("final_global_energy_error_j", result.final_global_energy_error_j);
    o.add("final", f.finish()); return o.finish();
}

} // namespace magic_geo::detail
