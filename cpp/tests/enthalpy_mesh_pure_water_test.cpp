#include "enthalpy_mesh_sdirk2.hpp"

#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

namespace {
using namespace magic_geo::detail;
struct Case { std::string name; EnthalpyMeshRequest q; std::string failure, stage_failure; };
int checks = 0, failures = 0;
void check(bool ok, const std::string& name) {
    ++checks; if (!ok) ++failures;
    std::cout << "{\"kind\":\"check\",\"name\":\"" << name << "\",\"passed\":" << (ok ? "true" : "false") << "}\n";
}
EnthalpyMeshRequest pure(std::vector<double> W, std::vector<double> H) {
    EnthalpyMeshRequest q; q.water = {10,2,4,100}; q.water_mass_kg_m2 = std::move(W);
    q.initial_enthalpy_j_m2 = std::move(H); q.columns.assign(q.water_mass_kg_m2.size(), {1,0,0});
    q.absorbed_shortwave_w_m2.assign(q.columns.size(), 0); q.options = {1,1e-10,1,128,64,32768,8,true}; return q;
}
EnthalpyMeshRequest solid_pair() { auto q = pure({1,2},{-4,-4}); q.edges = {{0,1,.125}}; return q; }
std::vector<Case> inventory() {
    std::vector<Case> cases;
    auto q = solid_pair(); cases.push_back({"closed_pure_solid_one_second",q,"",""});
    q.options.duration_seconds = .5; cases.push_back({"closed_pure_solid_half_second",q,"",""});
    q = pure({1,2},{1,-2}); q.water = {10,1,1,10}; q.edges = {{0,1,.125}};
    cases.push_back({"latent_refreeze_into_cold_layer",q,"",""});
    q = pure({2},{-8}); q.absorbed_shortwave_w_m2 = {2};
    cases.push_back({"pure_solid_constant_heat",q,"",""});
    q = pure({1},{-2}); q.absorbed_shortwave_w_m2 = {2}; q.options.duration_seconds = 2;
    cases.push_back({"cold_content_then_melting",q,"",""});
    q = pure({2},{0}); q.absorbed_shortwave_w_m2 = {5}; q.options.duration_seconds = 4;
    cases.push_back({"plateau_latent_energy",q,"",""});
    q = pure({1},{90}); q.absorbed_shortwave_w_m2 = {10}; q.options.duration_seconds = 2;
    cases.push_back({"complete_melting_then_liquid_heat",q,"",""});
    q = pure({1},{101}); q.water = {10,4,1,100}; q.absorbed_shortwave_w_m2 = {8}; q.options.duration_seconds = .5;
    cases.push_back({"smaller_liquid_capacity_supersolution",q,"",""});
    q = pure({1},{-1}); q.water = {1,1,1,1}; cases.push_back({"pure_stationary_absolute_zero",q,"",""});
    q = pure({1},{0}); q.options.allow_pure_water_columns = false;
    cases.push_back({"default_refuses_pure_water",q,"first_stage_refusal","invalid_input"});
    q = pure({0},{0}); cases.push_back({"empty_zero_capacity_node",q,"first_stage_refusal","invalid_input"});
    q = pure({2},{0}); q.columns[0].heat_capacity_j_m2_k = -1;
    cases.push_back({"negative_base_capacity",q,"first_stage_refusal","invalid_input"});
    q = pure({std::numeric_limits<double>::denorm_min()},{0}); q.water = {1,.5,1,1};
    cases.push_back({"unrepresentable_positive_solid_capacity",q,"first_stage_refusal","physical_domain_refusal"});
    q = pure({1},{-21}); cases.push_back({"below_pure_physical_floor",q,"first_stage_refusal","physical_domain_refusal"});
    q = solid_pair(); q.options.maximum_scalar_evaluations = 1;
    cases.push_back({"pure_shared_scalar_cap",q,"first_stage_refusal","work_cap"});
    q = solid_pair(); q.options.maximum_endpoint_error_j = 1e-30;
    cases.push_back({"pure_tight_endpoint_budget",q,"endpoint_budget_refusal",""});
    return cases;
}
} // namespace
int main(int argc, char** argv) {
    const bool only_inventory = argc == 2 && std::string(argv[1]) == "--inventory";
    if (argc > 1 && !only_inventory) return 2;
    std::cout << std::setprecision(17); const auto cases = inventory();
    for (const auto& c : cases)
        std::cout << "{\"kind\":\"inventory\",\"name\":\"" << c.name << "\",\"expected_refusal\":\"" << c.failure
                  << "\",\"expected_stage_refusal\":\"" << c.stage_failure << "\",\"request\":" << enthalpy_mesh_request_json(c.q) << "}\n";
    if (only_inventory) return 0;
    int calls = 0, stages = 0, accepted = 0, certificates = 0;
    double previous_solid_bound = 0;
    for (const auto& c : cases) {
        const auto before = enthalpy_mesh_request_json(c.q);
        check(calls < 16, "precall_outer_cap"); if (calls >= 16) return 2;
        ++calls; const auto r = advance_enthalpy_mesh_sdirk2(c.q);
        stages += r.stage_calls_started; accepted += r.accepted ? 1 : 0; certificates += r.endpoint_error_available ? 1 : 0;
        std::cout << "{\"kind\":\"receipt\",\"name\":\"" << c.name << "\",\"receipt\":" << enthalpy_mesh_sdirk2_receipt_json(r) << "}\n";
        check(before == enthalpy_mesh_request_json(c.q), c.name+".unchanged_request");
        check(c.failure.empty() ? r.accepted : !r.accepted && r.failure_code == c.failure, c.name+".expected_outcome");
        check(r.final_enthalpy_j_m2.has_value() == r.accepted, c.name+".final_availability");
        check(r.scalar_evaluations <= c.q.options.maximum_scalar_evaluations && r.sweeps_started <= c.q.options.maximum_sweeps,
              c.name+".shared_work_caps");
        if (!c.stage_failure.empty())
            check(r.first_stage && r.first_stage->failure_code == c.stage_failure && !r.second_stage, c.name+".typed_first_stage_refusal");
        if (r.accepted) {
            check(r.physical_curve_proved && r.endpoint_error_available && r.first_stage->accepted && r.second_stage->accepted,
                  c.name+".all_domains_and_gates");
            check(r.local_endpoint_error_upper_j <= c.q.options.maximum_endpoint_error_j, c.name+".endpoint_budget");
            check(r.certificate_leaves_started == 8 && r.backward_euler_leaves_started == 2, c.name+".work_retention");
            check(enthalpy_mesh_sdirk2_receipt_json(r).find("enthalpy_mesh_represented_sdirk2_pure_water_v2") != std::string::npos,
                  c.name+".explicit_generalized_model");
            const auto& H = *r.final_enthalpy_j_m2;
            if (c.name.starts_with("closed_pure_solid")) {
                check(std::abs(H[0]+H[1]+8) < 1e-9, c.name+".closed_extensive_energy");
                check(H[0] > -4 && H[1] < -4 && H[0] < 0 && H[1] < 0, c.name+".physical_heat_direction");
                if (previous_solid_bound > 0) check(r.local_endpoint_error_upper_j < .2*previous_solid_bound, c.name+".smooth_bound_scaling");
                previous_solid_bound = r.local_endpoint_error_upper_j;
            } else if (c.name == "latent_refreeze_into_cold_layer") {
                check(H[0] > 0 && H[0] < 1 && H[1] > -2 && H[1] < 0, c.name+".refreeze_and_cold_warming");
                check(std::abs(H[0]+H[1]+1) < 1e-9, c.name+".closed_extensive_energy");
            } else {
                const double expected = c.q.initial_enthalpy_j_m2[0] + c.q.absorbed_shortwave_w_m2[0]*c.q.options.duration_seconds;
                check(std::abs(H[0]-expected) < 1e-9, c.name+".known_constant_energy");
                if (c.name == "plateau_latent_energy") check(std::abs(H[0]/100-.2) < 1e-11, c.name+".latent_mass");
                if (c.name == "complete_melting_then_liquid_heat") check(H[0] > 100, c.name+".finite_mass_exhausted_to_liquid");
            }
        }
    }
    check(calls == 16 && stages == 26 && accepted == 9 && certificates == 10, "fixed_invocations_and_outcomes");
    std::cout << "{\"kind\":\"summary\",\"checks\":" << checks << ",\"misses\":" << failures << ",\"sdirk2_calls\":" << calls
              << ",\"internal_be_calls\":" << stages << ",\"accepted\":" << accepted << ",\"certificates\":" << certificates
              << ",\"world_calls\":0,\"source_calls\":0,\"parameter_retries\":0}\n";
    return failures == 0 ? 0 : 1;
}
