#include "enthalpy_mesh_sdirk2.hpp"

#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

namespace {
using namespace magic_geo::detail;
struct Case { std::string name; EnthalpyMeshRequest request; std::string refusal; };
int checks = 0, misses = 0;
void check(bool ok, const std::string& name) {
    ++checks; if (!ok) ++misses;
    std::cout << "{\"kind\":\"check\",\"name\":\"" << name << "\",\"passed\":" << (ok ? "true" : "false") << "}\n";
}
EnthalpyMeshRequest unit(std::vector<double> W, std::vector<double> H) {
    EnthalpyMeshRequest q; q.water = {1,1,1,1}; q.water_mass_kg_m2 = std::move(W);
    q.initial_enthalpy_j_m2 = std::move(H); q.columns.assign(q.initial_enthalpy_j_m2.size(), {1,1,0});
    q.absorbed_shortwave_w_m2.assign(q.columns.size(), 0); q.options = {1,1e-12,1,128,64,32768,8}; return q;
}
std::vector<Case> inventory() {
    std::vector<Case> cases;
    auto q = unit({0,0}, {-.25,.5}); q.columns[1].area_m2 = 2; q.edges = {{0,1,.125}};
    cases.push_back({"unequal_area_exchange_one_second",q,""});
    q.options.duration_seconds = .5; cases.push_back({"unequal_area_exchange_half_second",q,""});
    q.options.duration_seconds = .25; cases.push_back({"unequal_area_exchange_quarter_second",q,""});
    q.options.maximum_endpoint_error_j = 1e-30; cases.push_back({"tight_endpoint_refusal",q,"endpoint_budget_refusal"});
    q = unit({0}, {1e7*(280-273.15)}); q.water = {273.15,2100,4186,334000}; q.columns = {{1,1e7,.6}};
    q.options = {3600,.001,3340,128,64,32768,8}; cases.push_back({"radiative_cooling_hour",q,""});
    q = unit({1}, {.25}); q.absorbed_shortwave_w_m2 = {.125}; q.options.duration_seconds = .5;
    cases.push_back({"latent_constant_heat",q,""});
    q = unit({1}, {-.5}); q.absorbed_shortwave_w_m2 = {.5}; q.options.duration_seconds = .5;
    cases.push_back({"solid_constant_heat",q,""});
    q = unit({1}, {-.25}); q.absorbed_shortwave_w_m2 = {2}; q.options.duration_seconds = .75;
    cases.push_back({"full_phase_crossing_constant_heat",q,""});
    q = unit({0}, {0}); q.columns[0].longwave_emissivity = 1; q.options.duration_seconds = 1e9;
    cases.push_back({"nonphysical_second_stage_base",q,"second_stage_refusal"});
    q = unit({0,0}, {-.25,.5}); q.columns[1].area_m2 = 2; q.edges = {{0,1,.125}};
    q.options.maximum_sweeps = 0; cases.push_back({"zero_shared_sweeps",q,"first_stage_refusal"});
    q.options.maximum_sweeps = 128; q.options.maximum_scalar_evaluations = 2;
    cases.push_back({"partial_first_stage_scalar_cap",q,"first_stage_refusal"});
    q = unit({0}, {0}); q.absorbed_shortwave_w_m2[0] = -1;
    cases.push_back({"negative_sunlight",q,"first_stage_refusal"});
    q = unit({0}, {0}); q.options.reconstruction_leaves = 3;
    cases.push_back({"nondyadic_leaf_count",q,"work_cap"});
    q = unit({0}, {0}); q.options.duration_seconds = std::numeric_limits<double>::denorm_min();
    cases.push_back({"stage_duration_underflow",q,"invalid_input"});
    q = unit({0}, {-1}); cases.push_back({"stationary_absolute_zero",q,""});
    return cases;
}
} // namespace
int main(int argc, char** argv) {
    const bool only_inventory = argc == 2 && std::string(argv[1]) == "--inventory";
    if (argc > 1 && !only_inventory) return 2;
    std::cout << std::setprecision(17); const auto cases = inventory();
    for (const auto& c : cases)
        std::cout << "{\"kind\":\"inventory\",\"name\":\"" << c.name << "\",\"expected_refusal\":\"" << c.refusal
                  << "\",\"request\":" << enthalpy_mesh_request_json(c.request) << "}\n";
    if (only_inventory) return 0;
    int calls = 0, be_calls = 0, stages = 0, accepted = 0;
    double previous_exchange_bound = 0;
    for (const auto& c : cases) {
        const auto before = enthalpy_mesh_request_json(c.request);
        ++calls; const auto r = advance_enthalpy_mesh_sdirk2(c.request); stages += r.stage_calls_started;
        accepted += r.accepted ? 1 : 0;
        std::cout << "{\"kind\":\"receipt\",\"name\":\"" << c.name << "\",\"receipt\":" << enthalpy_mesh_sdirk2_receipt_json(r) << "}\n";
        check(enthalpy_mesh_request_json(c.request) == before, c.name+".input_unchanged");
        check(c.refusal.empty() ? r.accepted : (!r.accepted && r.failure_code == c.refusal), c.name+".expected_outcome");
        check(r.final_enthalpy_j_m2.has_value() == r.accepted, c.name+".publication");
        check(r.scalar_evaluations <= c.request.options.maximum_scalar_evaluations &&
              r.sweeps_started <= c.request.options.maximum_sweeps, c.name+".shared_work_caps");
        if (r.accepted) {
            check(r.first_stage && r.first_stage->accepted && r.second_stage && r.second_stage->accepted &&
                  r.physical_curve_proved && r.endpoint_error_available, c.name+".physical_stages_and_curve");
            check(r.local_endpoint_error_upper_j <= c.request.options.maximum_endpoint_error_j, c.name+".endpoint_budget");
            check(r.leaves.size() == static_cast<std::size_t>(c.request.options.reconstruction_leaves), c.name+".complete_curve");
            check(r.backward_euler_leaves_started == 2 && r.certificate_leaves_started == c.request.options.reconstruction_leaves,
                  c.name+".internal_work_retained");
        }
        if (c.name.starts_with("unequal_area_exchange") && r.accepted) {
            const auto& H = *r.final_enthalpy_j_m2;
            check(std::abs(H[0]+2*H[1]-.75) < 1e-10, c.name+".weighted_energy");
            // Ordinary libm comparison only; portable rational replay is the
            // independent enclosure authority for these analytic references.
            const double d = std::exp(-.1875*c.request.options.duration_seconds);
            const double error = std::abs(H[0]-(.25-.5*d))+2*std::abs(H[1]-(.25+.25*d));
            check(error <= r.local_endpoint_error_upper_j, c.name+".continuous_solution");
            if (previous_exchange_bound > 0)
                check(r.local_endpoint_error_upper_j < .2*previous_exchange_bound, c.name+".fixed_leaf_cubic_scaling");
            previous_exchange_bound = r.local_endpoint_error_upper_j;
        }
        if (c.name == "radiative_cooling_hour") {
            auto q = c.request; q.options.maximum_endpoint_error_j = 1e100;
            ++be_calls; const auto be = advance_enthalpy_mesh(q);
            std::cout << "{\"kind\":\"be_comparison\",\"name\":\"radiative_cooling_hour\",\"receipt\":" << enthalpy_mesh_receipt_json(be) << "}\n";
            check(r.accepted && be.accepted && r.local_endpoint_error_upper_j < .1*be.local_endpoint_error_upper_j,
                  c.name+".smaller_same_time_bound");
        }
        if (c.name == "full_phase_crossing_constant_heat" && r.accepted) {
            check(std::abs((*r.final_enthalpy_j_m2)[0]-1.25) < 1e-11, c.name+".known_energy");
            bool fallback = false;
            for (const auto& leaf : r.leaves) for (const auto& branch : leaf.temperature_branch) fallback |= branch == "phase_range";
            check(fallback, c.name+".nonsmooth_fallback_used");
        }
        if (c.name == "nonphysical_second_stage_base")
            check(r.first_stage && r.first_stage->accepted && r.second_stage &&
                  r.second_stage->failure_code == "physical_domain_refusal" && r.leaves.empty(), c.name+".refused_before_reconstruction");
    }
    check(calls == 15 && be_calls == 1, "declared_producer_counts");
    std::cout << "{\"kind\":\"summary\",\"checks\":" << checks << ",\"misses\":" << misses << ",\"sdirk2_calls\":" << calls
              << ",\"internal_be_calls\":" << stages << ",\"comparison_be_calls\":" << be_calls << ",\"accepted\":" << accepted << "}\n";
    return misses == 0 ? 0 : 1;
}
