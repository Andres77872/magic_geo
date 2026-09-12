#include "layered_ice_topology.hpp"
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
using Phase = cryosphere_prototype::Phase;
namespace b = phase_segment_prototype::bounds;
int checks = 0, failures = 0, calls = 0, source_builds = 0, output_builds = 0;
void check(bool ok, const std::string& name) {
    ++checks; if (!ok) ++failures;
    std::cout << "{\"kind\":\"check\",\"name\":" << std::quoted(name)
              << ",\"passed\":" << (ok ? "true" : "false") << "}\n";
}
LayeredIceTopologyRequest base() {
    LayeredIceTopologyRequest q; q.id = "manufactured_whole_inventory_topology_v1";
    q.source.id = "declared_topology_fixture"; q.source.complete_horizontal_coverage_declared = true;
    q.source.bottom_boundary = LayeredIceBottomBoundary::insulated; q.source.water = {10, 2, 4, 20};
    q.source.columns = {{0, 1, LayeredIceTopClosure::prescribed_nonwater_top_capacity, 6, .5, 3,
                        {{0, 2, 68, 2, 1}, {1, 2, -8, 4, 2}, {2, 4, 100, 4, 2}}, std::nullopt}};
    q.inherited_global_energy_error_j = .125; q.maximum_final_energy_error_j = 1;
    q.targets = {{0, {{0, 2, 1}, {1, 4, 2}}, std::nullopt}};
    q.donors = {{0, {false, 0}, {{{false, 0}, 1}}}, {0, {false, 1}, {{{false, 1}, 1}}}};
    q.exports = {{"full_liquid", {0, 2}, Phase::liquid}};
    return q;
}
LayeredIceTopologyRequest top(double H, bool promote) {
    auto q = base(); q.source.columns[0].layers.resize(promote ? 2 : 1);
    q.source.columns[0].layers[0].enthalpy_j_m2 = H;
    q.targets[0].layers.resize(1); q.donors.clear();
    if (promote) q.donors = {{0, {false, 1}, {{{false, 0}, 1}}}};
    q.exports = {{"whole_top_water", {0, 0}, H <= 0 ? Phase::solid : Phase::liquid}};
    return q;
}
struct Case {
    std::string name;
    LayeredIceTopologyRequest request;
    std::string failure;
    int source_builds = 1, output_builds = 0;
};
std::vector<Case> plan() {
    std::vector<Case> cases;
    const auto accept = [&](const std::string& name, LayeredIceTopologyRequest q) {
        cases.push_back({name, std::move(q), "", 1, 1});
    };
    accept("full_hot_interior_liquid_with_positive_E", base());
    auto q = base(); q.exports = {{"full_cold", {0, 1}, Phase::solid}};
    q.donors[1] = {0, {false, 2}, {{{false, 1}, 1}}};
    accept("full_cold_interior_negative_J", q);
    accept("cold_top_nonwater_retained_on_promoted_water", top(-20, true));
    accept("hot_top_nonwater_retained_on_promoted_water", top(68, true));
    accept("cold_top_water_exhaustion_leaves_dry_capacity", top(-20, false));
    accept("hot_top_water_exhaustion_leaves_dry_capacity", top(68, false));
    q = top(40, false); q.inherited_global_energy_error_j = 0;
    accept("exact_liquid_endpoint_with_zero_E", q);
    q = top(68, false); q.source.columns[0].deep_inventory = LayeredIceDeepInventoryInput{6, -12, 4};
    q.targets[0].deep_density_kg_m3 = 5;
    q.donors = {{0, {true, -1}, {{{false, 0}, 1}, {{true, -1}, 2}}}};
    accept("explicit_finite_deep_refill_during_top_export", q);
    q = base(); q.source.columns[0].layers.resize(1);
    q.source.columns[0].deep_inventory = LayeredIceDeepInventoryInput{6, -12, 4};
    q.targets[0].layers.resize(1); q.targets[0].deep_density_kg_m3 = 4; q.donors.resize(1);
    q.exports = {{"whole_deep", {0, -1}, Phase::solid}};
    accept("entire_deep_export_leaves_constrained_zero", q);
    q = base(); auto second = q.source.columns[0]; second.cell_id = 1; second.area_m2 = 2;
    second.top_closure = LayeredIceTopClosure::coarse_combined_surface_atmosphere;
    second.top_absorbed_shortwave_w_m2 = 5; q.source.columns.push_back(second);
    q.source.horizontal_climate_edges = {{0, 1, .25}};
    auto target = q.targets[0]; target.cell_id = 1; q.targets.push_back(target);
    q.donors.push_back({1, {false, 0}, {{{false, 0}, 1}}});
    q.donors.push_back({1, {false, 1}, {{{false, 1}, 1}}});
    q.exports.push_back({"second_full_liquid", {1, 2}, Phase::liquid});
    accept("unequal_areas_preserved_climate_and_grouped_exports", q);
    q = top(-20, false); q.exports.clear(); q.targets[0].layers.push_back({1, 4, 2});
    q.donors = {{0, {false, 0}, {{{false, 0}, 1}, {{false, 1}, 3}}}};
    accept("homogeneous_fractional_map_without_export", q);
    q = base(); q.exports.clear(); q.targets[0].layers.push_back({2, 4, 2});
    q.donors.push_back({0, {false, 2}, {{{false, 2}, 4294967296ULL}}});
    q.maximum_final_energy_error_j = q.inherited_global_energy_error_j;
    accept("complete_identity_zero_projection", q);
    q = top(68, true); q.source.columns[0].top_nonwater_heat_capacity_j_m2_k = 0;
    q.source.columns[0].top_closure = LayeredIceTopClosure::prescribed_top_energy;
    accept("pure_top_removal_promotes_existing_pure_water", q);

    const auto reject = [&](const std::string& name, const std::function<void(LayeredIceTopologyRequest&)>& mutate,
                            const std::string& failure, int source = 1, int output = 0) {
        auto item = base(); mutate(item); cases.push_back({name, std::move(item), failure, source, output});
    };
    q = top(68, false); q.source.columns[0].area_m2 = .1; q.source.columns[0].layers[0].water_mass_kg_m2 = .1;
    cases.push_back({"inexact_normal_full_mass_product", q, "unrepresentable_whole_export_mass", 1, 0});
    q = top(40, false);
    cases.push_back({"phase_endpoint_uncertain_with_positive_E", q, "uncertain_whole_export_phase", 1, 0});
    q = top(20, false); q.inherited_global_energy_error_j = 0;
    cases.push_back({"mixed_phase_whole_liquid_refuses", q, "uncertain_whole_export_phase", 1, 0});
    reject("wrong_full_phase", [](auto& x) { x.exports[0].phase = Phase::solid; }, "uncertain_whole_export_phase");
    reject("missing_positive_donor", [](auto& x) { x.donors.pop_back(); }, "invalid_allocation");
    reject("donor_allocation_and_export_overlap", [](auto& x) {
        x.exports[0].donor.layer_id = 1;
    }, "invalid_export");
    reject("duplicate_export_donor", [](auto& x) { x.exports.push_back(x.exports[0]); }, "invalid_export");
    reject("duplicate_export_id", [](auto& x) {
        x.donors.pop_back(); x.exports.push_back({x.exports[0].id, {0, 1}, Phase::solid});
    }, "invalid_export");
    reject("invalid_export_phase", [](auto& x) { x.exports[0].phase = static_cast<Phase>(7); }, "invalid_export");
    reject("invalid_export_cell", [](auto& x) { x.exports[0].donor.cell_id = 1; }, "invalid_export");
    reject("invalid_export_layer", [](auto& x) { x.exports[0].donor.layer_id = 9; }, "invalid_allocation");
    q = top(0, false); q.source.columns[0].layers[0].water_mass_kg_m2 = 0;
    cases.push_back({"massless_store_cannot_export", q, "invalid_export", 1, 0});
    q = top(68, false); q.source.columns[0].top_nonwater_heat_capacity_j_m2_k = 0;
    q.source.columns[0].top_closure = LayeredIceTopClosure::prescribed_top_energy;
    cases.push_back({"fully_empty_pure_column_still_refuses", q, "invalid_input", 1, 1});
    q = top(68, false); q.source.columns[0].deep_inventory = LayeredIceDeepInventoryInput{6, -12, 4};
    q.targets[0].deep_density_kg_m3 = 4; q.donors = {{0, {true, -1}, {{{true, -1}, 1}}}};
    cases.push_back({"existing_dry_top_positive_deep_policy_preserved", q, "invalid_input", 1, 1});
    reject("target_layer_must_be_canonical", [](auto& x) { x.targets[0].layers[1].layer_id = 8; }, "invalid_input");
    reject("explicit_density_required", [](auto& x) { x.targets[0].layers[0].density_kg_m3 = 0; }, "invalid_input");
    reject("zero_allocation_weight", [](auto& x) { x.donors[0].allocations[0].weight = 0; }, "invalid_allocation");
    reject("weight_total_exceeds_exact_cap", [](auto& x) {
        x.donors[0].allocations = {{{false, 0}, 4294967296ULL}, {{false, 1}, 1}};
    }, "invalid_allocation");
    reject("target_coverage_missing", [](auto& x) { x.targets.clear(); }, "invalid_input");
    reject("source_ball_crosses_floor", [](auto& x) {
        x.inherited_global_energy_error_j = 40; x.maximum_final_energy_error_j = 41;
    }, "physical_domain_refusal");
    // The tiny retained interior has a positive canonical mass, but cannot
    // contain the full unchanged marginal radius after the prescribed split.
    q = base(); q.targets[0].layers = {{0, 2, 1}, {1, 4, 2}};
    q.donors[1].allocations = {{{false, 0}, 4294967295ULL}, {{false, 1}, 1}};
    cases.push_back({"final_full_ball_crosses_thin_retained_floor", q, "physical_domain_refusal", 1, 1});
    reject("projection_exhausts_unchanged_budget", [](auto& x) {
        x.maximum_final_energy_error_j = x.inherited_global_energy_error_j;
    }, "energy_budget_refusal");
    reject("negative_inherited_error", [](auto& x) { x.inherited_global_energy_error_j = -1; }, "invalid_input", 0);
    reject("nonfinite_budget", [](auto& x) { x.maximum_final_energy_error_j = std::numeric_limits<double>::infinity(); }, "invalid_input", 0);
    reject("export_id_cap", [](auto& x) { x.exports[0].id.assign(97, 'x'); }, "invalid_export", 0);
    reject("export_retention_cap", [](auto& x) { x.limits.max_exports = 0; }, "invalid_input", 0);
    reject("invalid_hard_limits", [](auto& x) { x.limits.max_exports = 4097; }, "invalid_limits", 0);
    reject("active_node_retention_cap", [](auto& x) { x.limits.max_active_nodes = 2; }, "invalid_input", 0);
    reject("allocation_retention_cap", [](auto& x) { x.limits.max_allocations = 1; }, "invalid_input", 0);
    reject("arithmetic_group_cap", [](auto& x) { x.limits.max_arithmetic_groups = 1; }, "work_cap");
    return cases;
}
void inventory() {
    const auto cases = plan();
    std::cout << "{\"schema\":\"layered_ice_topology_inventory_v1\",\"execution\":\"none\",\"topology_call_cap\":" << cases.size()
              << ",\"builder_call_cap\":" << 2 * cases.size() << ",\"calorimeter_calls\":0,\"remap_calls\":0,\"thermal_calls\":0,\"world_calls\":0,\"cases\":[";
    bool first = true;
    for (const auto& item : cases) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\"name\":" << std::quoted(item.name) << ",\"request\":" << layered_ice_topology_request_json(item.request)
                  << ",\"expected_failure\":" << std::quoted(item.failure) << ",\"source_builds\":" << item.source_builds
                  << ",\"output_builds\":" << item.output_builds << '}';
    }
    std::cout << "]}\n";
}
void accepted_checks(const Case& item, const LayeredIceTopologyReceipt& r) {
    const auto& f = *r.final; const auto& output = f.graph.input();
    check(f.parcels.size() == item.request.exports.size(), item.name + "_complete_new_outbox_coverage");
    check(f.final_global_energy_error_j >= item.request.inherited_global_energy_error_j &&
          f.final_global_energy_error_j <= item.request.maximum_final_energy_error_j, item.name + "_joint_budget");
    bool stationary = output.columns.size() == item.request.source.columns.size();
    for (std::size_t i = 0; i < output.columns.size(); ++i) {
        const auto& a = output.columns[i]; const auto& z = item.request.source.columns[i];
        stationary = stationary && a.area_m2 == z.area_m2 && a.top_closure == z.top_closure &&
            a.top_nonwater_heat_capacity_j_m2_k == z.top_nonwater_heat_capacity_j_m2_k &&
            a.top_longwave_emissivity == z.top_longwave_emissivity &&
            a.top_absorbed_shortwave_w_m2 == z.top_absorbed_shortwave_w_m2;
    }
    check(stationary, item.name + "_geographic_top_capacity_and_forcing_stay");
    EnthalpyMeshInterval mass_projection{}, energy_projection{};
    for (const auto& p : r.projections) {
        const auto area = b::point(output.columns[static_cast<std::size_t>(p.cell_id)].area_m2);
        mass_projection = b::add(mass_projection, b::mul(area, p.mass_projection_difference_kg_m2));
        energy_projection = b::add(energy_projection, b::mul(area, p.enthalpy_projection_difference_j_m2));
    }
    for (const auto& p : f.parcels) energy_projection = b::add(energy_projection, p.energy_projection_j);
    const auto overlaps = [](auto x, auto y) { return x.lower <= y.upper && y.lower <= x.upper; };
    check(overlaps(r.mass_balance_residual_kg, mass_projection) && overlaps(r.energy_balance_residual_j, energy_projection),
          item.name + "_owned_totals_match_direct_projection");
    const auto& c = output.columns[0];
    if (item.name == "full_hot_interior_liquid_with_positive_E")
        check(c.layers.size() == 2 && f.graph.vertical_edges().size() == 1 && f.parcels[0].movement.mass_kg == 4 &&
              f.parcels[0].carried_enthalpy_j == 100, "hot_whole_donor_removed_with_saved_mass_and_J");
    else if (item.name == "full_cold_interior_negative_J")
        check(c.layers[1].water_mass_kg_m2 == 4 && c.layers[1].enthalpy_j_m2 == 100 &&
              f.parcels[0].carried_enthalpy_j == -8, "cold_middle_removed_survivor_compacted");
    else if (item.name == "cold_top_nonwater_retained_on_promoted_water")
        check(c.layers[0].water_mass_kg_m2 == 2 && c.layers[0].enthalpy_j_m2 == -20 &&
              f.parcels[0].carried_enthalpy_j == -8, "cold_nonwater_minus12_plus_survivor_minus8");
    else if (item.name == "hot_top_nonwater_retained_on_promoted_water")
        check(c.layers[0].water_mass_kg_m2 == 2 && c.layers[0].enthalpy_j_m2 == 4 &&
              f.parcels[0].carried_enthalpy_j == 56, "hot_nonwater12_plus_survivor_minus8");
    else if (item.name == "cold_top_water_exhaustion_leaves_dry_capacity" || item.name == "hot_top_water_exhaustion_leaves_dry_capacity")
        check(c.layers[0].water_mass_kg_m2 == 0 && c.layers[0].enthalpy_j_m2 ==
              (item.name.front() == 'c' ? -12 : 12) && f.graph.vertical_edges().empty(), item.name + "_dry_top_keeps_nonwater_energy");
    else if (item.name == "exact_liquid_endpoint_with_zero_E")
        check(c.layers[0].water_mass_kg_m2 == 0 && c.layers[0].enthalpy_j_m2 == 0 &&
              f.parcels[0].carried_enthalpy_j == 40, "liquid_endpoint_complete_latent_energy_exported");
    else if (item.name == "explicit_finite_deep_refill_during_top_export")
        check(c.layers[0].water_mass_kg_m2 == 2 && c.layers[0].enthalpy_j_m2 == 8 &&
              c.deep_inventory->water_mass_kg_m2 == 4 && c.deep_inventory->enthalpy_j_m2 == -8,
              "refill_reallocates_finite_deep_mass_and_cold_content");
    else if (item.name == "entire_deep_export_leaves_constrained_zero")
        check(c.deep_inventory->water_mass_kg_m2 == 0 && c.deep_inventory->enthalpy_j_m2 == 0 &&
              f.parcels[0].carried_enthalpy_j == -12, "empty_deep_structural_zero_saved_energy_retained");
    else if (item.name == "unequal_areas_preserved_climate_and_grouped_exports")
        check(f.parcels[0].movement.mass_kg == 4 && f.parcels[1].movement.mass_kg == 8 &&
              f.parcels[0].carried_enthalpy_j == 100 && f.parcels[1].carried_enthalpy_j == 200 &&
              output.horizontal_climate_edges[0].conductance_w_k == .25, "unequal_areas_apply_to_complete_extensive_exports");
    else if (item.name == "homogeneous_fractional_map_without_export")
        check(c.layers[0].water_mass_kg_m2 == .5 && c.layers[1].water_mass_kg_m2 == 1.5 &&
              c.layers[0].enthalpy_j_m2 == -14 && c.layers[1].enthalpy_j_m2 == -6, "homogeneous_allocation_keeps_nonwater_top");
    else if (item.name == "complete_identity_zero_projection")
        check(f.retained_energy_defect_upper_j == 0 && f.outbox_energy_defect_upper_j == 0 &&
              f.final_global_energy_error_j == item.request.inherited_global_energy_error_j &&
              layered_ice_input_json(output) == layered_ice_input_json(item.request.source), "identity_has_zero_new_error_and_bit_preservation");
    else if (item.name == "pure_top_removal_promotes_existing_pure_water")
        check(c.layers[0].water_mass_kg_m2 == 2 && c.layers[0].enthalpy_j_m2 == -8 &&
              c.top_nonwater_heat_capacity_j_m2_k == 0 && f.parcels[0].carried_enthalpy_j == 68,
              "pure_top_energy_all_transferred_without_nonwater");
}
int run() {
    const auto cases = plan();
    for (const auto& item : cases) {
        ++calls; const auto r = apply_layered_ice_topology(item.request);
        source_builds += r.work.source_builder_calls_started; output_builds += r.work.output_builder_calls_started;
        std::cout << "{\"kind\":\"topology\",\"name\":" << std::quoted(item.name)
                  << ",\"receipt\":" << layered_ice_topology_receipt_json(r) << "}\n";
        check(r.accepted == item.failure.empty() && r.failure_code == item.failure, item.name + "_expected_outcome");
        check(r.work.source_builder_calls_started == item.source_builds && r.work.output_builder_calls_started == item.output_builds,
              item.name + "_exact_builder_calls");
        check(r.final.has_value() == r.accepted, item.name + "_publication_only_on_acceptance");
        if (r.accepted && r.final) accepted_checks(item, r);
    }
    check(calls == static_cast<int>(cases.size()) && source_builds + output_builds <= calls * 2, "fixed_component_envelope");
    std::cout << "{\"kind\":\"summary\",\"checks\":" << checks << ",\"failures\":" << failures << ",\"topology_calls\":" << calls
              << ",\"source_builder_calls\":" << source_builds << ",\"output_builder_calls\":" << output_builds
              << ",\"calorimeter_calls\":0,\"remap_calls\":0,\"thermal_calls\":0,\"world_calls\":0}\n";
    return failures ? 1 : 0;
}
} // namespace
int main(int argc, char** argv) {
    std::cout.imbue(std::locale::classic()); std::cout << std::setprecision(17);
    if (argc == 2 && std::string(argv[1]) == "--inventory") { inventory(); return 0; }
    if (argc == 2 && std::string(argv[1]) == "--run") return run();
    return 2;
}
