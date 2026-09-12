#include "layered_ice_column.hpp"
#include "enthalpy_mesh_sdirk2.hpp"

#include <cmath>
#include <iomanip>
#include <iostream>
#include <optional>
#include <string>

namespace {
using namespace magic_geo::detail;
int checks = 0, failures = 0;
void check(bool ok, const std::string& name) {
    ++checks; if (!ok) ++failures;
    std::cout << "{\"kind\":\"check\",\"name\":\"" << name << "\",\"passed\":" << (ok ? "true" : "false") << "}\n";
}
LayeredIceInput input(bool more_deep) {
    LayeredIceInput q; q.id = more_deep ? "larger_deep_inventory" : "baseline_deep_inventory";
    q.complete_horizontal_coverage_declared = true;
    q.bottom_boundary = LayeredIceBottomBoundary::insulated;
    q.water = {273.15,2100,4186,334000};
    for (int i = 0; i < 2; ++i) {
        LayeredIceColumnInput c; c.cell_id = i; c.area_m2 = i+1;
        c.top_closure = LayeredIceTopClosure::coarse_combined_surface_atmosphere;
        c.top_nonwater_heat_capacity_j_m2_k = 1e7; c.top_longwave_emissivity = .6;
        c.top_absorbed_shortwave_w_m2 = i == 0 ? 300 : 450;
        c.layers = {{0,50,0,300,.3},{1,200,-420000,917,2.29},{2,1000,-4200000,917,2.29}};
        c.deep_inventory = LayeredIceDeepInventoryInput{more_deep ? 1e6 : 1e5, more_deep ? -2.1e10 : -2.1e9,917};
        q.columns.push_back(c);
    }
    q.horizontal_climate_edges = {{0,1,.1}};
    return q;
}
EnthalpyMeshOptions options() { return {900,.001,3340,128,64,32768,8,true}; }
} // namespace
int main(int argc, char** argv) {
    const bool only_inventory = argc == 2 && std::string(argv[1]) == "--inventory";
    if (argc > 1 && !only_inventory) return 2;
    std::cout << std::setprecision(17);
    for (bool more_deep : {false,true}) {
        const auto q = input(more_deep);
        std::cout << "{\"kind\":\"inventory\",\"name\":\"" << q.id << "\",\"input\":" << layered_ice_input_json(q)
                  << ",\"options\":{\"duration_seconds\":900,\"maximum_stage_error_j\":0.001,\"maximum_endpoint_error_j\":3340,"
                     "\"maximum_sweeps\":128,\"maximum_coordinate_iterations\":64,\"maximum_scalar_evaluations\":32768,"
                     "\"reconstruction_leaves\":8,\"allow_pure_water_columns\":true}}\n";
    }
    if (only_inventory) return 0;
    int builds = 0, thermal_calls = 0, stages = 0;
    std::optional<std::string> original_request, original_thermal;
    std::optional<LayeredIceInventories> original_inventories;
    for (bool more_deep : {false,true}) {
        const auto initial = input(more_deep); const auto raw = layered_ice_input_json(initial);
        check(builds < 2, "build_precall_cap"); if (builds >= 2) return 2;
        ++builds;
        try {
            const auto graph = build_layered_ice_graph(initial); const auto graph_before = layered_ice_graph_json(graph);
            const auto q = graph.make_mesh_request(options()); const auto serialized = enthalpy_mesh_request_json(q);
            std::cout << "{\"kind\":\"prepared\",\"name\":\"" << initial.id << "\",\"graph\":" << graph_before
                      << ",\"request\":" << serialized << "}\n";
            check(thermal_calls < 2, "thermal_precall_cap"); if (thermal_calls >= 2) return 2;
            ++thermal_calls; const auto r = advance_enthalpy_mesh_sdirk2(q); stages += r.stage_calls_started;
            std::cout << "{\"kind\":\"receipt\",\"name\":\"" << initial.id << "\",\"receipt\":" << enthalpy_mesh_sdirk2_receipt_json(r) << "}\n";
            check(r.accepted, initial.id+".thermal_accepted");
            check(layered_ice_input_json(initial) == raw && layered_ice_graph_json(graph) == graph_before,
                  initial.id+".input_and_graph_unchanged");
            check(q.columns.size() == 6 && q.edges.size() == 5 && graph.deep_inventories().size() == 2,
                  initial.id+".explicit_active_and_deep_coverage");
            check(q.columns[1].heat_capacity_j_m2_k == 0 && q.columns[2].heat_capacity_j_m2_k == 0 &&
                  q.columns[4].heat_capacity_j_m2_k == 0 && q.columns[5].heat_capacity_j_m2_k == 0,
                  initial.id+".no_duplicated_atmospheric_capacity");
            if (r.accepted) {
                const auto& H = *r.final_enthalpy_j_m2;
                check(H[0] > 0 && H[0] < 50*334000 && H[3] > H[0] && H[3] < 50*334000,
                      initial.id+".surface_liquid_under_prescribed_heat");
                check(H[1] < 0 && H[2] < 0 && H[4] < 0 && H[5] < 0, initial.id+".subsurface_remains_cold");
                check(r.local_endpoint_error_upper_j <= 3340 && r.physical_curve_proved,
                      initial.id+".canonical_active_mesh_error_bound");
            }
            if (!more_deep) {
                original_request = serialized; original_thermal = enthalpy_mesh_sdirk2_receipt_json(r);
                original_inventories = graph.inventories();
            } else {
                check(original_request && *original_request == serialized, "deep_change_preserves_actual_thermal_request");
                check(original_thermal && *original_thermal == enthalpy_mesh_sdirk2_receipt_json(r), "deep_change_preserves_actual_thermal_receipt");
                check(original_inventories && graph.inventories().active.represented_mass_kg == original_inventories->active.represented_mass_kg &&
                      graph.inventories().deep.represented_mass_kg == 10*original_inventories->deep.represented_mass_kg,
                      "deep_change_retains_all_distinct_mass");
                check(original_inventories && graph.inventories().deep.represented_enthalpy_j == 10*original_inventories->deep.represented_enthalpy_j,
                      "deep_change_retains_distinct_cold_content");
            }
        } catch (const LayeredIceError& error) {
            std::cout << "{\"kind\":\"builder_failure\",\"name\":\"" << initial.id << "\",\"code\":\"" << error.code << "\"}\n";
            check(false, initial.id+".unexpected_builder_refusal");
        }
    }
    check(builds == 2 && thermal_calls == 2 && stages == 4, "fixed_producer_counts");
    std::cout << "{\"kind\":\"summary\",\"checks\":" << checks << ",\"misses\":" << failures << ",\"graph_builds\":" << builds
              << ",\"thermal_calls\":" << thermal_calls << ",\"internal_be_calls\":" << stages
              << ",\"source_calls\":0,\"world_calls\":0,\"parameter_retries\":0}\n";
    return failures == 0 ? 0 : 1;
}
