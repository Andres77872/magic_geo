#include "layered_ice_column.hpp"

#include <cfenv>
#include <cmath>
#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <string>
#include <vector>

namespace {
using namespace magic_geo::detail;
int checks = 0, misses = 0, builds = 0;
void check(bool ok, const std::string& label) {
    ++checks; if (!ok) ++misses;
    std::cout << "{\"kind\":\"check\",\"name\":" << std::quoted(label)
              << ",\"passed\":" << (ok ? "true" : "false") << "}\n";
}
LayeredIceInput baseline() {
    LayeredIceInput q;
    q.id = "layered-mixed-prescribed";
    q.complete_horizontal_coverage_declared = true;
    q.bottom_boundary = LayeredIceBottomBoundary::insulated;
    q.water = {273.15, 2100, 4186, 334000};
    q.columns = {
        {0, 2, LayeredIceTopClosure::coarse_combined_surface_atmosphere, 10, .6, 300,
         {{0, 10, -200, 500, .5}, {1, 50, -1000, 900, 2}, {2, 100, 0, 900, 2}},
         LayeredIceDeepInventoryInput{900000, -900000000, 917}},
        {1, 3, LayeredIceTopClosure::prescribed_nonwater_top_capacity, 20, .4, 100,
         {{0, 0, 600, 1000, .6}}, std::nullopt},
        {2, 5, LayeredIceTopClosure::prescribed_top_energy, 0, .7, 200,
         {{0, 20, 3340000, 1000, .6}, {1, 40, 0, 1000, .6}},
         LayeredIceDeepInventoryInput{0, 0, 917}}
    };
    q.horizontal_climate_edges = {{0, 1, .25}, {0, 2, .5}, {1, 2, .125}};
    return q;
}
struct Case {
    std::string name;
    LayeredIceInput input;
    std::string expected_failure;
};
std::vector<Case> fixed_plan() {
    std::vector<Case> plan;
    const auto original = baseline();
    plan.push_back({"mixed_top_closures_and_insulated_deep_inventory", original, ""});
    auto q = original;
    q.id = "nonbinary-material-conversions";
    q.columns[0].area_m2 = .3;
    q.columns[0].layers[0] = {0, .1, -.2, .7, .11};
    q.columns[0].layers[1] = {1, .4, -.5, .9, .13};
    q.columns[0].layers[2] = {2, .6, .7, 1.1, .17};
    q.columns[0].deep_inventory = LayeredIceDeepInventoryInput{.8, -.9, 1.3};
    plan.push_back({"nonbinary_original_operand_conversion_enclosures", q, ""});
    q = original;
    q.id = "one-pure-layer";
    q.columns.resize(1); q.columns[0].layers.resize(1); q.columns[0].deep_inventory.reset();
    q.columns[0].top_closure = LayeredIceTopClosure::prescribed_top_energy;
    q.columns[0].top_nonwater_heat_capacity_j_m2_k = 0;
    q.horizontal_climate_edges.clear();
    plan.push_back({"single_pure_water_node_no_invented_deep_storage", q, ""});
    const auto reject = [&](const std::string& name, const std::function<void(LayeredIceInput&)>& change,
                            const std::string& expected = "invalid_input") {
        auto item = original; change(item); plan.push_back({name, std::move(item), expected});
    };
    reject("missing_horizontal_coverage", [](auto& x) { x.complete_horizontal_coverage_declared = false; });
    reject("unspecified_bottom_boundary", [](auto& x) { x.bottom_boundary = LayeredIceBottomBoundary::unspecified; });
    reject("unknown_bottom_boundary", [](auto& x) { x.bottom_boundary = static_cast<LayeredIceBottomBoundary>(7); });
    reject("empty_identifier", [](auto& x) { x.id.clear(); });
    reject("identifier_space", [](auto& x) { x.id = "bad id"; });
    reject("identifier_cap", [](auto& x) { x.limits.max_identifier_bytes = 1; });
    reject("empty_columns", [](auto& x) { x.columns.clear(); });
    reject("column_cap", [](auto& x) { x.limits.max_columns = 2; });
    reject("empty_layers", [](auto& x) { x.columns[0].layers.clear(); });
    reject("per_column_layer_cap", [](auto& x) { x.limits.max_layers_per_column = 2; });
    reject("thermal_node_cap", [](auto& x) { x.limits.max_thermal_nodes = 5; });
    reject("combined_edge_cap", [](auto& x) { x.limits.max_edges = 5; });
    reject("horizontal_edge_cap", [](auto& x) { x.limits.max_edges = 2; });
    reject("invalid_limits", [](auto& x) { x.limits.max_thermal_nodes = 16385; }, "invalid_limits");
    reject("invalid_water_constant", [](auto& x) { x.water.solid_heat_capacity_j_kg_k = 0; });
    reject("nan_water_constant", [](auto& x) { x.water.latent_heat_j_kg = std::numeric_limits<double>::quiet_NaN(); });
    reject("noncanonical_horizontal_id", [](auto& x) { x.columns[1].cell_id = 0; });
    reject("noncanonical_layer_id", [](auto& x) { x.columns[0].layers[1].layer_id = 7; });
    reject("zero_area", [](auto& x) { x.columns[0].area_m2 = 0; });
    reject("negative_top_capacity", [](auto& x) { x.columns[0].top_nonwater_heat_capacity_j_m2_k = -1; });
    reject("unspecified_top_closure", [](auto& x) { x.columns[0].top_closure = LayeredIceTopClosure::unspecified; });
    reject("unknown_top_closure", [](auto& x) { x.columns[0].top_closure = static_cast<LayeredIceTopClosure>(7); });
    reject("pure_closure_nonwater_capacity", [](auto& x) { x.columns[0].top_closure = LayeredIceTopClosure::prescribed_top_energy; });
    reject("combined_closure_zero_capacity", [](auto& x) { x.columns[0].top_nonwater_heat_capacity_j_m2_k = 0; });
    reject("invalid_emissivity", [](auto& x) { x.columns[0].top_longwave_emissivity = 1.1; });
    reject("negative_sunlight", [](auto& x) { x.columns[0].top_absorbed_shortwave_w_m2 = -1; });
    reject("negative_layer_mass", [](auto& x) { x.columns[0].layers[1].water_mass_kg_m2 = -1; });
    reject("nonfinite_layer_enthalpy", [](auto& x) { x.columns[0].layers[1].enthalpy_j_m2 = std::numeric_limits<double>::infinity(); });
    reject("zero_mass_interior_node", [](auto& x) { x.columns[0].layers[1].water_mass_kg_m2 = 0; });
    reject("zero_mass_top_with_deeper_nodes", [](auto& x) { x.columns[0].layers[0].water_mass_kg_m2 = 0; });
    reject("empty_sensible_storage", [](auto& x) {
        x.columns[1].top_closure = LayeredIceTopClosure::prescribed_top_energy;
        x.columns[1].top_nonwater_heat_capacity_j_m2_k = 0;
    });
    reject("zero_density", [](auto& x) { x.columns[0].layers[0].density_kg_m3 = 0; });
    reject("zero_conductivity", [](auto& x) { x.columns[0].layers[1].conductivity_w_m_k = 0; });
    reject("negative_deep_mass", [](auto& x) { x.columns[0].deep_inventory->water_mass_kg_m2 = -1; });
    reject("zero_deep_density", [](auto& x) { x.columns[0].deep_inventory->density_kg_m3 = 0; });
    reject("zero_deep_mass_nonzero_enthalpy", [](auto& x) { x.columns[0].deep_inventory->water_mass_kg_m2 = 0; });
    reject("zero_surface_hiding_deep_ice", [](auto& x) {
        x.columns[1].deep_inventory = LayeredIceDeepInventoryInput{1, 0, 917};
    });
    reject("unphysical_layer_enthalpy", [](auto& x) { x.columns[0].layers[1].enthalpy_j_m2 = -1e12; }, "physical_domain_refusal");
    reject("unphysical_deep_enthalpy", [](auto& x) { x.columns[0].deep_inventory->enthalpy_j_m2 = -1e18; }, "physical_domain_refusal");
    reject("horizontal_self_edge", [](auto& x) { x.horizontal_climate_edges[0].second_cell = 0; });
    reject("reversed_horizontal_edge", [](auto& x) { x.horizontal_climate_edges[0] = {1, 0, .25}; });
    reject("out_of_range_horizontal_edge", [](auto& x) { x.horizontal_climate_edges[0].second_cell = 3; });
    reject("duplicate_horizontal_edge", [](auto& x) { x.horizontal_climate_edges.push_back(x.horizontal_climate_edges[0]); });
    reject("negative_horizontal_conductance", [](auto& x) { x.horizontal_climate_edges[0].conductance_w_k = -1; });
    reject("positive_thickness_underflow", [](auto& x) {
        x.columns[0].layers[0].water_mass_kg_m2 = std::numeric_limits<double>::denorm_min();
        x.columns[0].layers[0].enthalpy_j_m2 = 0;
        x.columns[0].layers[0].density_kg_m3 = 2;
    }, "arithmetic_refusal");
    reject("absolute_mass_overflow", [](auto& x) { x.columns[0].area_m2 = std::numeric_limits<double>::max(); }, "arithmetic_refusal");
    reject("absolute_enthalpy_overflow", [](auto& x) {
        x.columns[0].layers[0].enthalpy_j_m2 = std::numeric_limits<double>::max() * .75;
    }, "arithmetic_refusal");
    reject("half_resistance_underflow", [](auto& x) {
        x.columns[0].layers[0].water_mass_kg_m2 = 1e-200;
        x.columns[0].layers[0].enthalpy_j_m2 = 0;
        x.columns[0].layers[0].density_kg_m3 = 1;
        x.columns[0].layers[0].conductivity_w_m_k = 1e200;
    }, "arithmetic_refusal");
    reject("effective_capacity_underflow", [](auto& x) {
        x.water.solid_heat_capacity_j_kg_k = std::numeric_limits<double>::denorm_min();
        x.water.liquid_heat_capacity_j_kg_k = std::numeric_limits<double>::denorm_min();
        for (auto& c : x.columns) {
            for (auto& layer : c.layers) layer.enthalpy_j_m2 = 0;
            if (c.deep_inventory) c.deep_inventory->enthalpy_j_m2 = 0;
        }
        x.columns[2].layers[0].water_mass_kg_m2 = std::numeric_limits<double>::denorm_min();
    }, "arithmetic_refusal");
    reject("latent_storage_overflow", [](auto& x) {
        x.water.latent_heat_j_kg = std::numeric_limits<double>::max();
    }, "arithmetic_refusal");
    reject("initial_hot_temperature_overflow", [](auto& x) {
        x.columns.resize(1); x.horizontal_climate_edges.clear();
        auto& c = x.columns[0];
        c.top_closure = LayeredIceTopClosure::prescribed_top_energy;
        c.top_nonwater_heat_capacity_j_m2_k = 0;
        c.layers = {{0, 1, 1e100, 1, 1}};
        c.deep_inventory.reset();
        x.water.liquid_heat_capacity_j_kg_k = 1e-300;
    }, "arithmetic_refusal");
    return plan;
}
void inventory() {
    const auto plan = fixed_plan();
    std::cout << "{\"schema\":\"layered_ice_column_qualification_inventory_v1\",\"execution\":\"none\","
              << "\"maximum_build_attempts\":" << plan.size() + 1
              << ",\"thermal_calls\":0,\"world_calls\":0,\"cases\":[";
    bool first = true;
    for (const auto& item : plan) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\"name\":" << std::quoted(item.name) << ",\"input\":" << layered_ice_input_json(item.input)
                  << ",\"expected_failure\":" << std::quoted(item.expected_failure) << '}';
    }
    std::cout << "],\"extra_controls\":[\"non_nearest_rounding_refused_then_restored\"]}\n";
}
void accepted_checks(const LayeredIceGraph& graph, const std::string& label) {
    const auto mesh = graph.make_mesh_request({});
    check(mesh.options.allow_pure_water_columns, label + "_explicit_generalized_node_admission");
    check(mesh.columns.size() == graph.nodes().size(), label + "_all_thermal_nodes_mapped");
    for (const auto& node : graph.nodes()) {
        const auto id = static_cast<std::size_t>(node.thermal_node_id);
        const auto& c = graph.input().columns[static_cast<std::size_t>(node.cell_id)];
        const auto& l = c.layers[static_cast<std::size_t>(node.layer_id)];
        check(mesh.water_mass_kg_m2[id] == l.water_mass_kg_m2 && mesh.initial_enthalpy_j_m2[id] == l.enthalpy_j_m2,
              label + "_retained_state_node_" + std::to_string(id));
        check(mesh.columns[id].area_m2 == c.area_m2, label + "_same_area_node_" + std::to_string(id));
        if (node.layer_id > 0)
            check(mesh.columns[id].heat_capacity_j_m2_k == 0 && mesh.columns[id].longwave_emissivity == 0 &&
                  mesh.absorbed_shortwave_w_m2[id] == 0, label + "_interior_no_repeated_atmosphere_or_radiation_" + std::to_string(id));
    }
    check(mesh.edges.size() == graph.vertical_edges().size() + graph.input().horizontal_climate_edges.size(),
          label + "_one_edge_per_exchange");
    for (const auto& e : graph.input().horizontal_climate_edges) {
        const int a = graph.top_thermal_node_ids()[static_cast<std::size_t>(e.first_cell)];
        const int z = graph.top_thermal_node_ids()[static_cast<std::size_t>(e.second_cell)];
        int count = 0;
        for (const auto& x : mesh.edges)
            if (x.first_cell == a && x.second_cell == z && x.conductance_w_k == e.conductance_w_k) ++count;
        check(count == 1, label + "_horizontal_top_only_" + std::to_string(a) + "_" + std::to_string(z));
    }
    if (label == "mixed_top_closures_and_insulated_deep_inventory") {
        check(graph.top_thermal_node_ids() == std::vector<int>{0, 3, 4}, "column_major_distinct_thermal_ids");
        check(graph.nodes().size() == 6 && graph.vertical_edges().size() == 3, "finite_depth_node_and_exchange_counts");
        check(graph.deep_inventories().size() == 2, "zero_and_positive_deep_inventories_retained");
        check(graph.inventories().active.represented_mass_kg == 620 &&
              graph.inventories().deep.represented_mass_kg == 1800000 &&
              graph.inventories().combined.represented_mass_kg == 1800620, "active_and_deep_mass_separated");
        check(graph.inventories().active.represented_enthalpy_j == 16699400 &&
              graph.inventories().deep.represented_enthalpy_j == -1800000000,
              "active_and_deep_energy_separated");
    }
}
void run() {
    const auto plan = fixed_plan();
    for (const auto& item : plan) {
        ++builds;
        std::string failure, detail;
        try {
            const auto graph = build_layered_ice_graph(item.input);
            std::cout << "{\"kind\":\"graph\",\"name\":" << std::quoted(item.name)
                      << ",\"graph\":" << layered_ice_graph_json(graph) << "}\n";
            if (item.expected_failure.empty()) accepted_checks(graph, item.name);
        } catch (const LayeredIceError& error) { failure = error.code; detail = error.what(); }
        std::cout << "{\"kind\":\"outcome\",\"name\":" << std::quoted(item.name)
                  << ",\"failure_code\":" << std::quoted(failure) << ",\"detail\":" << std::quoted(detail) << "}\n";
        check(failure == item.expected_failure, item.name + "_expected_outcome");
    }
    const int prior = std::fegetround();
    const bool changed = std::fesetround(FE_UPWARD) == 0;
    std::string failure;
    if (changed) {
        try { ++builds; build_layered_ice_graph(baseline()); }
        catch (const LayeredIceError& error) { failure = error.code; }
    }
    const bool restored = std::fesetround(prior) == 0;
    check(changed && restored && failure == "capability_unavailable", "non_nearest_rounding_refused_then_restored");
    check(builds <= static_cast<int>(plan.size() + 1), "fixed_build_attempt_bound");
}
} // namespace

int main(int argc, char** argv) {
    std::cout.imbue(std::locale::classic());
    std::cout << std::setprecision(17);
    if (argc == 2 && std::string(argv[1]) == "--inventory") { inventory(); return 0; }
    if (argc != 2 || std::string(argv[1]) != "--run") return 2;
    run();
    std::cout << "{\"kind\":\"summary\",\"checks\":" << checks << ",\"misses\":" << misses
              << ",\"build_attempts\":" << builds << ",\"thermal_calls\":0,\"world_calls\":0}\n";
    return misses ? 1 : 0;
}
