#include "layered_ice_remap.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <functional>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <string>
#include <utility>
#include <vector>

namespace {
using namespace magic_geo::detail;
int checks = 0, misses = 0, calls = 0, source_builds = 0, output_builds = 0;
void check(bool ok, const std::string& name) {
    ++checks; if (!ok) ++misses;
    std::cout << "{\"kind\":\"check\",\"name\":" << std::quoted(name)
              << ",\"passed\":" << (ok ? "true" : "false") << "}\n";
}
LayeredIceRemapRequest one_top(double C, double W, double H) {
    LayeredIceRemapRequest q; q.id = "fixed-layer-remap";
    q.source.id = "declared-material-column"; q.source.complete_horizontal_coverage_declared = true;
    q.source.bottom_boundary = LayeredIceBottomBoundary::insulated;
    q.source.water = {10, 2, 4, 20};
    q.source.columns = {{0, 1, C == 0 ? LayeredIceTopClosure::prescribed_top_energy :
        LayeredIceTopClosure::prescribed_nonwater_top_capacity, C, .5, 3,
        {{0, W, H, 2, 1}}, std::nullopt}};
    q.inherited_global_energy_error_j = .01; q.maximum_final_energy_error_j = .1;
    q.targets = {{0, {{0, 2, 1}, {1, 3, 2}}, std::nullopt}};
    q.donors = {{0, {false, 0}, {{{false, 0}, 1}, {{false, 1}, 1}}}};
    return q;
}
LayeredIceRemapRequest pure_split() {
    auto q = one_top(0, 6, -12);
    q.targets[0].layers.push_back({2, 4, 3});
    q.donors[0].allocations = {{{false, 0}, 1}, {{false, 1}, 2}, {{false, 2}, 3}};
    return q;
}
struct Case {
    std::string name;
    LayeredIceRemapRequest request;
    std::string failure;
    int source_builds = 1, output_builds = 0;
};
std::vector<Case> plan() {
    std::vector<Case> out;
    out.push_back({"pure_water_split", pure_split(), "", 1, 1});
    auto q = one_top(0, 1, -2);
    q.source.columns[0].layers = {{0, 1, -2, 2, 1}, {1, 2, 4, 3, 2}, {2, 3, -6, 4, 3}};
    q.targets[0].layers.resize(1);
    q.donors = {{0, {false, 0}, {{{false, 0}, 1}}}, {0, {false, 1}, {{{false, 0}, 1}}},
                {0, {false, 2}, {{{false, 0}, 1}}}};
    out.push_back({"pure_water_merge", q, "", 1, 1});
    out.push_back({"cold_top_nonwater_stationary", one_top(6, 2, -20), "", 1, 1});
    out.push_back({"latent_top_nonwater_stationary", one_top(6, 2, 20), "", 1, 1});
    out.push_back({"hot_top_nonwater_stationary", one_top(6, 2, 68), "", 1, 1});
    q = one_top(6, 2, -20); q.source.columns[0].deep_inventory = LayeredIceDeepInventoryInput{6, -12, 4};
    q.targets[0].layers.resize(1); q.targets[0].deep_density_kg_m3 = 5;
    q.donors = {{0, {false, 0}, {{{true, -1}, 1}}},
                {0, {true, -1}, {{{false, 0}, 1}, {{true, -1}, 2}}}};
    out.push_back({"deep_water_refills_active_layer", q, "", 1, 1});
    q.donors = {{0, {false, 0}, {{{false, 0}, 1}}}, {0, {true, -1}, {{{false, 0}, 1}}}};
    out.push_back({"deep_fully_emptied_exact_zero_constraint", q, "", 1, 1});
    q = one_top(6, 2, -20);
    q.source.columns.push_back({1, 2, LayeredIceTopClosure::coarse_combined_surface_atmosphere,
                                6, .7, 5, {{0, 2, 68, 2, 1}}, std::nullopt});
    q.source.horizontal_climate_edges = {{0, 1, .25}};
    q.targets.push_back({1, {{0, 3, 1}, {1, 4, 2}}, std::nullopt});
    q.donors.push_back({1, {false, 0}, {{{false, 0}, 1}, {{false, 1}, 1}}});
    out.push_back({"unequal_area_global_error_and_climate_preserved", q, "", 1, 1});
    q = one_top(.3, .1, -.2); q.donors[0].allocations[1].weight = 2;
    out.push_back({"nonbinary_three_way_denominator_projection", q, "", 1, 1});
    q = one_top(6, 2, -20); q.targets[0].layers.resize(1);
    q.donors[0].allocations = {{{false, 0}, 4294967296ULL}};
    q.maximum_final_energy_error_j = q.inherited_global_energy_error_j;
    out.push_back({"complete_noop_exact_zero_projection", q, "", 1, 1});
    q.targets[0].layers[0].density_kg_m3 = 7; q.targets[0].layers[0].conductivity_w_m_k = .25;
    out.push_back({"state_identity_declared_geometry_replacement", q, "", 1, 1});
    q = one_top(6, 0, 12); q.targets[0].layers.resize(1); q.donors.clear();
    q.maximum_final_energy_error_j = q.inherited_global_energy_error_j;
    out.push_back({"dry_top_no_invented_water", q, "", 1, 1});

    const auto reject = [&](const std::string& name, const std::function<void(LayeredIceRemapRequest&)>& change,
                            const std::string& failure, int source = 1, int output = 0) {
        auto item = pure_split(); change(item); out.push_back({name, std::move(item), failure, source, output});
    };
    reject("missing_donor", [](auto& x) { x.donors.clear(); }, "invalid_allocation");
    reject("duplicate_donor", [](auto& x) { x.donors.push_back(x.donors[0]); }, "invalid_allocation");
    reject("empty_donor_allocations", [](auto& x) { x.donors[0].allocations.clear(); }, "invalid_allocation");
    reject("zero_weight", [](auto& x) { x.donors[0].allocations[0].weight = 0; }, "invalid_allocation");
    reject("exact_weight_total_exceeds_2_to_32", [](auto& x) { x.donors[0].allocations[0].weight = 4294967296ULL; }, "invalid_allocation");
    reject("duplicate_destination", [](auto& x) { x.donors[0].allocations[1].destination = {false, 0}; }, "invalid_allocation");
    reject("undeclared_deep_destination", [](auto& x) { x.donors[0].allocations[0].destination = {true, -1}; }, "invalid_allocation");
    reject("invalid_deep_location_tag", [](auto& x) { x.donors[0].source = {true, 0}; }, "invalid_allocation");
    reject("invalid_source_layer", [](auto& x) { x.donors[0].source.layer_id = 7; }, "invalid_allocation");
    reject("invalid_destination_layer", [](auto& x) { x.donors[0].allocations[0].destination.layer_id = 7; }, "invalid_allocation");
    reject("invalid_donor_cell", [](auto& x) { x.donors[0].cell_id = 1; }, "invalid_allocation");
    reject("target_coverage_missing", [](auto& x) { x.targets.clear(); }, "invalid_input");
    reject("target_cell_id_noncanonical", [](auto& x) { x.targets[0].cell_id = 1; }, "invalid_input");
    reject("target_layer_id_noncanonical", [](auto& x) { x.targets[0].layers[0].layer_id = 7; }, "invalid_input");
    reject("target_density_missing", [](auto& x) { x.targets[0].layers[0].density_kg_m3 = 0; }, "invalid_input");
    reject("target_conductivity_nonfinite", [](auto& x) { x.targets[0].layers[0].conductivity_w_m_k = std::numeric_limits<double>::infinity(); }, "invalid_input");
    reject("target_deep_density_missing", [](auto& x) { x.targets[0].deep_density_kg_m3 = 0; }, "invalid_input");
    reject("empty_pure_water_target", [](auto& x) { x.donors[0].allocations = {{{false, 0}, 1}}; }, "invalid_input", 1, 1);
    reject("output_exceeds_source_builder_layer_cap", [](auto& x) { x.source.limits.max_layers_per_column = 1; }, "invalid_input", 1, 1);
    reject("input_whole_energy_ball_crosses_floor", [](auto& x) {
        x.inherited_global_energy_error_j = 109; x.maximum_final_energy_error_j = 110;
    }, "physical_domain_refusal");
    reject("output_whole_energy_ball_crosses_floor", [](auto& x) {
        x.targets[0].layers.resize(2);
        x.donors[0].allocations = {{{false, 0}, 1}, {{false, 1}, 4294967295ULL}};
    }, "physical_domain_refusal", 1, 1);
    reject("projection_exhausts_budget", [](auto& x) { x.maximum_final_energy_error_j = x.inherited_global_energy_error_j; }, "energy_budget_refusal");
    reject("negative_inherited_error", [](auto& x) { x.inherited_global_energy_error_j = -1; }, "invalid_input", 0);
    reject("budget_below_inherited_error", [](auto& x) { x.maximum_final_energy_error_j = 0; }, "invalid_input", 0);
    reject("nonfinite_budget", [](auto& x) { x.maximum_final_energy_error_j = std::numeric_limits<double>::infinity(); }, "invalid_input", 0);
    reject("invalid_source_physical_graph", [](auto& x) { x.source.columns[0].layers[0].enthalpy_j_m2 = -1000; }, "physical_domain_refusal");
    reject("identifier_limit", [](auto& x) { x.id.assign(97, 'x'); }, "invalid_input", 0);
    reject("invalid_hard_limits", [](auto& x) { x.limits.max_active_nodes = 16385; }, "invalid_limits", 0);
    reject("active_node_retention_cap", [](auto& x) { x.limits.max_active_nodes = 2; }, "invalid_input", 0);
    reject("donor_retention_cap", [](auto& x) { x.limits.max_donors = 0; }, "invalid_input", 0);
    reject("allocation_retention_cap", [](auto& x) { x.limits.max_allocations = 2; }, "invalid_input", 0);
    reject("arithmetic_group_cap", [](auto& x) { x.limits.max_arithmetic_groups = 1; }, "work_cap");
    q = one_top(6, 0, 12); q.targets[0].layers.resize(1); q.donors[0].allocations.resize(1);
    out.push_back({"allocation_row_for_massless_store", q, "invalid_allocation", 1, 0});
    q = one_top(0, std::numeric_limits<double>::denorm_min(), 0);
    q.source.columns[0].layers[0].density_kg_m3 = 1;
    q.inherited_global_energy_error_j = 0;
    out.push_back({"positive_allocated_mass_underflow", q, "arithmetic_refusal", 1, 0});
    return out;
}
void inventory() {
    const auto cases = plan();
    std::cout << "{\"schema\":\"layered_ice_remap_qualification_inventory_v1\",\"execution\":\"none\","
              << "\"remap_call_cap\":" << cases.size() << ",\"builder_call_cap\":" << cases.size() * 2
              << ",\"thermal_calls\":0,\"world_calls\":0,\"cases\":[";
    bool first = true;
    for (const auto& item : cases) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\"name\":" << std::quoted(item.name) << ",\"request\":" << layered_ice_remap_request_json(item.request)
                  << ",\"expected_failure\":" << std::quoted(item.failure)
                  << ",\"expected_source_builder_calls\":" << item.source_builds
                  << ",\"expected_output_builder_calls\":" << item.output_builds << '}';
    }
    std::cout << "]}\n";
}
void accepted_checks(const Case& item, const LayeredIceRemapReceipt& r) {
    const auto& f = *r.final;
    const auto& output = f.graph.input();
    check(f.final_global_energy_error_j >= item.request.inherited_global_energy_error_j &&
          f.final_global_energy_error_j <= item.request.maximum_final_energy_error_j, item.name + "_global_budget");
    bool whole_energy = true;
    for (const auto& d : f.decompositions) {
        const long double lo = static_cast<long double>(d.ideal_water_enthalpy_j_m2.lower) +
                               d.ideal_stationary_nonwater_enthalpy_j_m2.lower;
        const long double hi = static_cast<long double>(d.ideal_water_enthalpy_j_m2.upper) +
                               d.ideal_stationary_nonwater_enthalpy_j_m2.upper;
        whole_energy = whole_energy && lo <= d.initial_complete_enthalpy_j_m2 && d.initial_complete_enthalpy_j_m2 <= hi;
    }
    check(whole_energy, item.name + "_water_plus_stationary_energy_encloses_whole_donor_H");
    namespace b = phase_segment_prototype::bounds;
    EnthalpyMeshInterval mass_projection{}, energy_projection{};
    for (const auto& p : f.projections) {
        const auto area = b::point(output.columns[static_cast<std::size_t>(p.cell_id)].area_m2);
        mass_projection = b::add(mass_projection, b::mul(area, p.mass_projection_difference_kg_m2));
        energy_projection = b::add(energy_projection, b::mul(area, p.enthalpy_projection_difference_j_m2));
    }
    const auto overlaps = [](EnthalpyMeshInterval a, EnthalpyMeshInterval z) {
        return a.lower <= z.upper && z.lower <= a.upper;
    };
    check(overlaps(f.represented_total_mass_change_kg, mass_projection) &&
          overlaps(f.represented_total_enthalpy_change_j, energy_projection) &&
          b::absmax(energy_projection) <= f.energy_projection_defect_upper_j,
          item.name + "_total_changes_match_bounded_canonical_projection");
    check(output.columns.size() == item.request.source.columns.size() &&
          output.horizontal_climate_edges.size() == item.request.source.horizontal_climate_edges.size(), item.name + "_geographic_coverage");
    for (std::size_t i = 0; i < output.columns.size(); ++i) {
        const auto& a = output.columns[i]; const auto& z = item.request.source.columns[i];
        check(a.area_m2 == z.area_m2 && a.top_closure == z.top_closure &&
              a.top_nonwater_heat_capacity_j_m2_k == z.top_nonwater_heat_capacity_j_m2_k &&
              a.top_longwave_emissivity == z.top_longwave_emissivity &&
              a.top_absorbed_shortwave_w_m2 == z.top_absorbed_shortwave_w_m2, item.name + "_stationary_climate_" + std::to_string(i));
    }
    if (item.name == "pure_water_split") {
        check(output.columns[0].layers[0].water_mass_kg_m2 == 1 && output.columns[0].layers[1].water_mass_kg_m2 == 2 &&
              output.columns[0].layers[2].water_mass_kg_m2 == 3, "pure_split_prescribed_mass_weights");
    }
    if (item.name == "pure_water_merge")
        check(output.columns[0].layers[0].water_mass_kg_m2 == 6 && output.columns[0].layers[0].enthalpy_j_m2 == -4,
              "pure_merge_mass_and_energy");
    if (item.name == "cold_top_nonwater_stationary")
        check(output.columns[0].layers[0].enthalpy_j_m2 == -16 && output.columns[0].layers[1].enthalpy_j_m2 == -4,
              "cold_top_nonwater_energy_stays_geographic_top");
    if (item.name == "latent_top_nonwater_stationary")
        check(output.columns[0].layers[0].enthalpy_j_m2 == 10 && output.columns[0].layers[1].enthalpy_j_m2 == 10,
              "latent_top_has_zero_nonwater_offset");
    if (item.name == "hot_top_nonwater_stationary")
        check(output.columns[0].layers[0].enthalpy_j_m2 == 40 && output.columns[0].layers[1].enthalpy_j_m2 == 28,
              "hot_top_nonwater_energy_stays_geographic_top");
    if (item.name == "deep_water_refills_active_layer")
        check(output.columns[0].layers[0].water_mass_kg_m2 == 2 && output.columns[0].deep_inventory->water_mass_kg_m2 == 6,
              "deep_refill_reallocates_existing_mass");
    if (item.name == "deep_fully_emptied_exact_zero_constraint")
        check(output.columns[0].deep_inventory->water_mass_kg_m2 == 0 && output.columns[0].deep_inventory->enthalpy_j_m2 == 0,
              "empty_deep_has_no_independent_energy_error_coordinate");
    if (item.name == "complete_noop_exact_zero_projection" || item.name == "state_identity_declared_geometry_replacement" ||
        item.name == "dry_top_no_invented_water") {
        check(f.energy_projection_defect_upper_j == 0 && f.final_global_energy_error_j == item.request.inherited_global_energy_error_j,
              item.name + "_zero_projection_and_no_error_recharge");
        check(output.columns[0].layers[0].water_mass_kg_m2 == item.request.source.columns[0].layers[0].water_mass_kg_m2 &&
              output.columns[0].layers[0].enthalpy_j_m2 == item.request.source.columns[0].layers[0].enthalpy_j_m2,
              item.name + "_complete_state_retained");
    }
}
void run() {
    const auto cases = plan();
    for (const auto& item : cases) {
        ++calls;
        const auto r = remap_layered_ice(item.request);
        source_builds += r.work.source_builder_calls_started; output_builds += r.work.output_builder_calls_started;
        std::cout << "{\"kind\":\"remap\",\"name\":" << std::quoted(item.name)
                  << ",\"receipt\":" << layered_ice_remap_receipt_json(r) << "}\n";
        check(r.failure_code == item.failure && r.accepted == item.failure.empty(), item.name + "_expected_outcome");
        check(r.work.source_builder_calls_started == item.source_builds && r.work.output_builder_calls_started == item.output_builds,
              item.name + "_exact_builder_calls");
        if (r.accepted && r.final) accepted_checks(item, r);
    }
    check(calls == static_cast<int>(cases.size()) && source_builds + output_builds <= calls * 2, "fixed_operation_envelope");
}
} // namespace
int main(int argc, char** argv) {
    std::cout.imbue(std::locale::classic()); std::cout << std::setprecision(17);
    if (argc == 2 && std::string(argv[1]) == "--inventory") { inventory(); return 0; }
    if (argc != 2 || std::string(argv[1]) != "--run") return 2;
    run();
    std::cout << "{\"kind\":\"summary\",\"checks\":" << checks << ",\"misses\":" << misses
              << ",\"remap_calls\":" << calls << ",\"source_builder_calls\":" << source_builds
              << ",\"output_builder_calls\":" << output_builds << ",\"thermal_calls\":0,\"world_calls\":0}\n";
    return misses ? 1 : 0;
}
