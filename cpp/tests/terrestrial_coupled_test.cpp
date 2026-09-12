#include "terrestrial_coupled.hpp"

#include <cfenv>
#include <cfloat>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace magic_geo::detail;
namespace a = cryosphere_prototype;
namespace p = phase_segment_prototype;
namespace t = higher_order_thermal_prototype;
namespace {
[[maybe_unused]] constexpr int prepare_cap = 32;
[[maybe_unused]] constexpr int commit_cap = 12;
[[maybe_unused]] constexpr std::uint64_t segment_cap = 64;
[[maybe_unused]] constexpr std::uint64_t stage_cap = 512;
[[maybe_unused]] constexpr std::uint64_t flux_cap = 32768;
[[maybe_unused]] int checks = 0, prepares = 0, commits = 0;
[[maybe_unused]] std::uint64_t segments = 0, stages = 0, fluxes = 0, mass_calls = 0;
std::vector<std::string> observations;
[[maybe_unused]] void check(bool ok, const char *message) {
    ++checks;
    if (!ok)
        throw std::runtime_error(message);
}
std::string quote(const std::string &value) {
    std::string s = "\"";
    for (char ch : value) {
        if (ch == '\\' || ch == '"')
            s += '\\';
        s += ch;
    }
    return s + '"';
}
std::string join(const std::vector<std::string> &xs) {
    std::string s = "[";
    for (const auto &x : xs) {
        if (s.size() > 1)
            s += ',';
        s += x;
    }
    return s + ']';
}
struct Fixture {
    std::string id;
    std::vector<Cell> cells;
    CoupledProperties properties;
    CoupledRestart initial;
    CoupledAcceptancePolicy policy;
    CoupledLimits limits;
    CoupledIntervalPlan plan;
};
std::vector<Cell> cells(int active) {
    std::vector<Cell> out(static_cast<std::size_t>(active + 2));
    for (std::size_t i = 0; i < out.size(); ++i) {
        out[i].id = static_cast<int>(i);
        out[i].area_km2 = (i == 1 ? 4 : 2) * 1e-6;
        out[i].p = {1, 0, 0};
        out[i].temperature_c = -20;
        out[i].precipitation_mm_y = 120;
    }
    out[active].is_lake = true;
    out[active].water_depth_m = 2;
    out[active + 1].is_water = true;
    out[active + 1].water_depth_m = 100;
    return out;
}
CoupledSegmentPlan segment(const std::string &id, p::Branch branch, p::Goal goal, double end,
                           p::StateBox box, bool event = false) {
    return {id,
            branch,
            goal,
            end,
            box,
            {1e-9, 1e-8, 1e-3, event ? 1e-7 : 0.01},
            {event ? 48 : 1, 16, event ? 48 : 2, event ? 8192 : 1024},
            {1e-12, 1e-12, 20, 8},
            false};
}
Fixture dry(const std::string &id, int active = 1) {
    Fixture f;
    f.id = id;
    f.cells = cells(active);
    f.properties = {{1, 1, 1, 1}, 1000, 8, {}};
    f.properties.columns.resize(f.cells.size());
    f.initial.state.resize(f.cells.size());
    f.initial.canonical_energy_error_j_m2.resize(f.cells.size());
    f.policy = {0.02};
    f.plan = {0, 0.0625, {"dry_constant_source", 0, 1, {}}, {}, {}, {}};
    f.plan.forcing.incident_shortwave_w_m2.resize(f.cells.size());
    for (int i = 0; i < active; ++i) {
        f.properties.columns[i] = {10, 10, 0.5, 1, 0};
        f.initial.state[i] = {0, 1, 0.5};
        f.plan.forcing.incident_shortwave_w_m2[i] = 1;
        f.plan.columns.push_back(
            {i,
             {segment("dry_" + std::to_string(i), p::Branch::dry, p::Goal::within_branch, 0.0625,
                      {{0.99, 1.07}, {0.499, 0.505}})}});
    }
    return f;
}
Fixture plateau(const std::string &id, int active = 1) {
    const double c = t::sigma_w_m2_k4 * 4096;
    Fixture f;
    f.id = id;
    f.cells = cells(active);
    f.properties = {{8, 2, 4, c}, 1000, 8, {}};
    f.properties.columns.resize(f.cells.size());
    f.initial.state.resize(f.cells.size());
    f.initial.canonical_energy_error_j_m2.resize(f.cells.size());
    f.policy = {1e-5};
    f.plan = {0, 1.25, {"plateau_constant_source", 0, 4, {}}, {}, {}, {}};
    f.plan.forcing.incident_shortwave_w_m2.resize(f.cells.size());
    for (int i = 0; i < active; ++i) {
        f.properties.columns[i] = {1, 0, 0, 0, 0};
        f.initial.state[i] = {2, c, 0};
        f.plan.forcing.incident_shortwave_w_m2[i] = 2 * c;
        f.plan.columns.push_back(
            {i,
             {segment("mixed_" + std::to_string(i), p::Branch::mixed, p::Goal::within_branch, 1.25,
                      {{-c / 4, 1.75 * c}, {0, 0}})}});
    }
    return f;
}
Fixture phase_paths() {
    const double c = t::sigma_w_m2_k4 * 4096;
    auto f = plateau("different_phase_subdivisions", 2);
    f.initial.state[1].surface_enthalpy_j_m2 = c / 8;
    f.plan.columns[0].segments = {
        segment("melt_boundary", p::Branch::mixed, p::Goal::next_phase_boundary, 1.25,
                {{-c / 2, 3 * c}, {0, 0}}, true),
        segment("liquid_remainder", p::Branch::liquid, p::Goal::within_branch, 1.25,
                {{1.9 * c, 2.6 * c}, {0, 0}})};
    return f;
}
Fixture source_import() {
    auto f = plateau("initial_snow_retained_melt");
    f.initial.state[0] = {0, 0, 0};
    f.plan.imports = {{"snow_initial", 0, a::Phase::solid, 4, 8}};
    return f;
}
CoupledIntervalPlan withdrawal_plan() {
    const double c = t::sigma_w_m2_k4 * 4096;
    auto r = source_import().plan;
    r.expected_revision = 1;
    r.end_seconds = 1.5;
    r.imports.clear();
    r.initial_liquid_withdrawals = {{"liquid_next_interval", 0, 1}};
    r.columns[0].segments = {segment("mixed_after_withdrawal", p::Branch::mixed,
                                     p::Goal::within_branch, 1.5, {{0.5 * c, 1.4 * c}, {0, 0}})};
    return r;
}
Fixture unrepresentable_handoff() {
    auto f = plateau("round_down_upper_boundary_refusal");
    f.properties.water = {1, 1, 1, 1.1};
    f.properties.columns[0] = {1, 0, 0, 0, 0};
    f.initial.state[0] = {1.1, 0.5, 0};
    f.policy = {0.01};
    f.plan.end_seconds = 0.25;
    f.plan.forcing = {"nonrepresentable_source", 0, 1, {4, 0, 0}};
    f.plan.columns[0].segments = {segment("rounded_upper", p::Branch::mixed,
                                          p::Goal::next_phase_boundary, 0.25, {{0.4, 1.6}, {0, 0}},
                                          true),
                                  segment("raw_liquid_handoff", p::Branch::liquid,
                                          p::Goal::within_branch, 0.25, {{1.1, 1.8}, {0, 0}})};
    f.plan.columns[0].segments[0].budgets.maximum_locator_width_seconds = 1e-11;
    return f;
}
std::string fixture_json(const Fixture &f) {
    // A pure schema specimen: no owner or certificate constructor is invoked.
    CoupledAttemptReceipt r;
    r.properties = f.properties;
    r.acceptance_policy = f.policy;
    r.limits = f.limits;
    r.surface_cells = f.cells;
    r.initial = f.initial;
    r.observed_accepted_after = f.initial;
    r.private_prefix = f.initial;
    r.request_available = true;
    r.request = f.plan;
    r.observed_request_after = f.plan;
    return "{\"id\":" + quote(f.id) +
           ",\"unexecuted_context_and_request\":" + coupled_attempt_receipt_json(r) + '}';
}
std::vector<Fixture> fixed_refusal_fixtures() {
    std::vector<Fixture> out;
    auto f = dry("second_cell_private_prefix_refusal", 2);
    f.plan.columns[1].segments[0].tube.surface_enthalpy_j_m2 = {2, 3};
    out.push_back(f);
    f = source_import();
    f.id = "mass_then_thermal_refusal";
    f.plan.columns[0].segments[0].tube.surface_enthalpy_j_m2 = {10, 11};
    out.push_back(f);
    f = dry("late_projection_refusal");
    f.cells[0].temperature_c = 1e308;
    out.push_back(f);
    f = dry("incomplete_terminal_coverage");
    f.plan.columns[0].segments[0].latest_end_seconds = 0.03125;
    out.push_back(f);
    f = dry("unused_nonterminal_suffix");
    f.plan.columns[0].segments.push_back(f.plan.columns[0].segments[0]);
    f.plan.columns[0].segments[1].id = "unused_second";
    out.push_back(f);
    f = dry("numerical_stage_refusal");
    f.plan.columns[0].segments[0].stage_options.maximum_newton_iterations = 0;
    out.push_back(f);
    f = dry("cumulative_error_budget_refusal");
    f.policy.max_joint_energy_error_j_m2 = 1e-15;
    out.push_back(f);
    f = plateau("uncertain_initial_liquid_refusal");
    f.initial.canonical_energy_error_j_m2[0] = t::sigma_w_m2_k4 * 1024;
    f.policy.max_joint_energy_error_j_m2 = 0.01;
    f.plan.initial_liquid_withdrawals = {{"uncertain_outlet", 0, 1.75}};
    out.push_back(f);
    f = dry("complete_work_reservation_refusal");
    f.limits.max_stage_calls = 1;
    out.push_back(f);
    f = dry("oversized_thermal_id_refusal");
    f.plan.forcing.id = std::string(65, 'x');
    out.push_back(f);
    out.push_back(unrepresentable_handoff());
    return out;
}
std::string inventory() {
    std::vector<std::string> fs = {fixture_json(phase_paths()), fixture_json(source_import()),
                                   fixture_json(dry("radiative_sensible_dry"))};
    for (const auto &f : fixed_refusal_fixtures())
        fs.push_back(fixture_json(f));
    return "{\"schema\":\"coupled_owner_fixed_test_inventory_v1\",\"execution\":\"none\","
           "\"prepare_cap\":32,\"commit_cap\":12,\"segment_call_cap\":64,\"stage_call_cap\":512,"
           "\"flux_evaluation_cap\":32768,\"fixtures\":" +
           join(fs) +
           ",\"later_withdrawal_plan\":" + coupled_interval_plan_json(withdrawal_plan()) +
           ",\"fixed_followups\":[\"duplicate_private_prepare\",\"foreign_candidate\",\"stale_"
           "candidate\","
           "\"replayed_candidate\",\"duplicate_event\",\"altered_forcing_identity\",\"overlapping_"
           "forcing_identity\","
           "\"wet_event\",\"missing_cell_plan\",\"stale_revision\",\"nonexact_clock\",\"terminal_"
           "zero_remainder_skip\","
           "\"nonnearest_all_wet_prepare\",\"nonnearest_constructor\",\"all_wet_identity\","
           "\"invalid_uncertain_restart\"]}";
}
#if !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) && LDBL_MANT_DIG >= 64 &&                  \
    LDBL_MAX_EXP >= 16384
TerrestrialCoupledOwner owner(const Fixture &f) {
    return TerrestrialCoupledOwner(capture_terrestrial_surface(f.cells), f.properties, f.initial,
                                   f.policy, f.limits);
}
std::string physical(const TerrestrialCoupledOwner &x) {
    return "{\"context\":" + coupled_owner_context_json(x) +
           ",\"restart\":" + coupled_restart_json(x.restart()) + ",\"last_receipt\":" +
           (x.last_receipt() ? coupled_attempt_receipt_json(*x.last_receipt()) : "null") + '}';
}
CoupledPreparation prepare(const std::string &id, TerrestrialCoupledOwner &x,
                           const CoupledIntervalPlan &request,
                           const char *expected_failure = nullptr) {
    check(prepares < prepare_cap, "prepare call cap");
    std::uint64_t reserved_segments = 0, reserved_stages = 0, reserved_fluxes = 0;
    for (const auto &cell : request.columns) {
        for (const auto &step : cell.segments) {
            check(step.work.maximum_stage_calls >= 0 && step.work.maximum_total_flux_evaluations >= 0,
                  "test reservation requires nonnegative work");
            ++reserved_segments;
            reserved_stages += static_cast<std::uint64_t>(step.work.maximum_stage_calls);
            reserved_fluxes += static_cast<std::uint64_t>(step.work.maximum_total_flux_evaluations);
        }
    }
    // Admit the entire worst-case prepare before calling it. Unused capacity
    // becomes available again because the counters below retain actual work.
    check(reserved_segments <= segment_cap - segments && reserved_stages <= stage_cap - stages &&
              reserved_fluxes <= flux_cap - fluxes,
          "complete prepare has no aggregate test work reservation");
    const auto before = physical(x);
    const auto input_before = coupled_interval_plan_json(request);
    const auto prior = x.work_meter();
    ++prepares;
    auto result = x.prepare(request);
    const auto after = physical(x);
    const auto input_after = coupled_interval_plan_json(request);
    const auto next = x.work_meter();
    segments += next.segment_calls_started - prior.segment_calls_started;
    stages += next.stage_calls_started - prior.stage_calls_started;
    fluxes += next.scalar_flux_evaluations - prior.scalar_flux_evaluations;
    mass_calls += next.mass_calls_started - prior.mass_calls_started;
    observations.push_back("{\"id\":" + quote(id) + ",\"action\":\"prepare\",\"before\":" + before +
                           ",\"after\":" + after + ",\"request_before\":" + input_before +
                           ",\"request_after\":" + input_after +
                           ",\"diagnostic\":" + coupled_attempt_receipt_json(*result.diagnostic) +
                           ",\"candidate_available\":" + (result.candidate ? "true" : "false") +
                           '}');
    check(before == after && input_before == input_after,
          "prepare mutated physical state or request");
    check(next.prepare_attempts == prior.prepare_attempts + 1 && next.observed_work_counts_complete,
          "attempt work observation");
    check(segments <= segment_cap && stages <= stage_cap && fluxes <= flux_cap,
          "fixed aggregate test work cap");
    if (expected_failure) {
        check(!result.candidate && !result.diagnostic->prepared && !result.diagnostic->final &&
                  result.diagnostic->failure_code == expected_failure,
              "wrong or missing prepare refusal");
    } else {
        check(result.candidate.has_value() && result.diagnostic->prepared &&
                  result.diagnostic->final.has_value(),
              "expected prepared candidate");
        for (const auto &c : result.diagnostic->coverage)
            check(c.complete && c.completed_end_seconds == request.end_seconds,
                  "common endpoint coverage");
    }
    return result;
}
void commit(const std::string &id, TerrestrialCoupledOwner &x,
            const CoupledIntervalCandidate &candidate, const char *expected_failure = nullptr) {
    check(commits < commit_cap, "commit cap");
    const auto before = physical(x);
    const auto meter = coupled_work_meter_json(x.work_meter());
    ++commits;
    std::string error;
    try {
        x.commit(candidate);
    } catch (const TerrestrialWaterError &e) {
        error = e.code;
    }
    observations.push_back("{\"id\":" + quote(id) + ",\"action\":\"commit\",\"before\":" + before +
                           ",\"after\":" + physical(x) +
                           ",\"error\":" + (error.empty() ? "null" : quote(error)) + '}');
    check(coupled_work_meter_json(x.work_meter()) == meter, "commit changed computation meter");
    if (expected_failure)
        check(error == expected_failure && physical(x) == before, "commit refusal atomicity");
    else
        check(error.empty() && coupled_restart_json(x.restart()) ==
                                   coupled_restart_json(*candidate.receipt().final),
              "commit did not publish exact prepared bundle");
}
struct RoundingRestore {
    int old = std::fegetround();
    ~RoundingRestore() { std::fesetround(old); }
};
void run() {
    auto f = phase_paths();
    auto x = owner(f);
    auto hit = prepare(f.id, x, f.plan);
    check(hit.diagnostic->coverage[0].completed_segments == 2 &&
              hit.diagnostic->coverage[1].completed_segments == 1,
          "different phase subdivisions not retained");
    check(hit.diagnostic->segments[0].receipt.guard.first_physical_hit_proved &&
              hit.diagnostic->segments[0].receipt.selected_end_seconds < 1.25,
          "actual intermediate phase hit");
    check(hit.diagnostic->work_after.mass_calls_started == 0, "empty source batch invoked A");
    commit("phase_paths_commit", x, *hit.candidate);
    commit("phase_paths_replay", x, *hit.candidate, "stale_candidate");

    f = source_import();
    auto source = owner(f);
    auto foreign = owner(f);
    const auto first = prepare("source_first_private", source, f.plan);
    const auto competing = prepare("source_second_private", source, f.plan);
    check(coupled_restart_json(*first.diagnostic->final) ==
              coupled_restart_json(*competing.diagnostic->final),
          "same accepted base produced different private result");
    check(first.diagnostic->mass_receipt_available &&
              first.diagnostic->private_liquid_outbox.empty() &&
              first.diagnostic->final->state[0].surface_enthalpy_j_m2 > 0 &&
              first.diagnostic->final->state[0].water_mass_kg_m2 == 2,
          "snow source and retained melt");
    commit("foreign_candidate", foreign, *first.candidate, "foreign_candidate");
    commit("source_commit", source, *first.candidate);
    commit("competing_candidate_stale", source, *competing.candidate, "stale_candidate");
    const auto withdrawal = withdrawal_plan();
    const auto exported = prepare("later_liquid_export", source, withdrawal);
    check(exported.diagnostic->private_liquid_outbox.size() == 1 &&
              exported.diagnostic->private_liquid_outbox[0].mass_kg == 1 &&
              exported.diagnostic->private_liquid_outbox[0].carried_enthalpy_j ==
                  t::sigma_w_m2_k4 * 4096 &&
              exported.diagnostic->projection.cells[0].delivered_liquid_depth_mm == 0.5,
          "once-only canonical liquid handoff");
    commit("withdrawal_commit", source, *exported.candidate);
    auto bad = withdrawal;
    bad.expected_revision = 2;
    bad.end_seconds = 1.75;
    bad.columns[0].segments[0].latest_end_seconds = 1.75;
    prepare("duplicate_event", source, bad, "duplicate_event");
    bad.initial_liquid_withdrawals.clear();
    bad.forcing.incident_shortwave_w_m2[0] *= 2;
    prepare("altered_forcing_identity", source, bad, "forcing_identity_refusal");
    bad.forcing = withdrawal.forcing;
    bad.forcing.id = "overlap_new_id";
    prepare("overlapping_forcing_identity", source, bad, "forcing_identity_refusal");
    bad.forcing = withdrawal.forcing;
    bad.imports = {{"wet_snow", 1, a::Phase::solid, 1, 8}};
    prepare("wet_event", source, bad, "invalid_event");
    bad.imports.clear();
    bad.columns.clear();
    prepare("missing_cell_plan", source, bad, "invalid_plan");
    bad = withdrawal;
    bad.expected_revision = 99;
    prepare("stale_revision", source, bad, "stale_revision");
    bad = withdrawal;
    bad.expected_revision = 2;
    bad.end_seconds = 0x1p53;
    prepare("nonexact_clock", source, bad, "clock_refusal");

    f = dry("radiative_sensible_dry");
    auto air = owner(f);
    const auto coupled = prepare(f.id, air, f.plan);
    check(coupled.diagnostic->final->state[0].atmospheric_energy_j_m2 >
              f.initial.state[0].atmospheric_energy_j_m2,
          "nonzero sensible coupling did not update Ea");
    const auto fixtures = fixed_refusal_fixtures();
    const std::vector<const char *> failures = {
        "thermal_refused",      "thermal_refused",      "projection_refusal",
        "incomplete_plan",      "unused_plan_refusal",  "thermal_refused",
        "error_budget_refused", "error_budget_refused", "work_cap",
        "invalid_identifier",   "thermal_refused"};
    for (std::size_t i = 0; i < fixtures.size(); ++i) {
        auto failed = owner(fixtures[i]);
        const auto observed = prepare(fixtures[i].id, failed, fixtures[i].plan, failures[i]);
        if (i == 0)
            check(observed.diagnostic->coverage[0].complete &&
                      !observed.diagnostic->coverage[1].complete,
                  "second-cell refusal lost completed private prefix");
        if (i == 1)
            check(observed.diagnostic->mass_receipt_available &&
                      failed.restart().consumed_event_ids.empty(),
                  "private successful A consumed sources on later failure");
        if (i == 8 || i == 9)
            check(failed.work_meter().mass_calls_started == 0 &&
                      failed.work_meter().segment_calls_started == 0,
                  "preflight refusal performed physical work");
        if (i == 6)
            check(observed.diagnostic->segments.size() == 1 &&
                      observed.diagnostic->segments[0].receipt.accepted &&
                      !observed.diagnostic->segments[0].error.accepted,
                  "cumulative policy did not reject an otherwise accepted native segment");
        if (i == 10)
            check(observed.diagnostic->segments.size() == 2 &&
                      observed.diagnostic->segments[0].receipt.accepted &&
                      observed.diagnostic->segments[1].receipt.failure_code == "branch_refusal",
                  "unrepresentable latent handoff was shifted or hidden");
    }
    f = dry("terminal_zero_remainder_skip");
    f.plan.columns[0].segments.push_back(f.plan.columns[0].segments[0]);
    f.plan.columns[0].segments[1].id = "explicit_terminal_skip";
    f.plan.columns[0].segments[1].skip_if_at_common_end = true;
    auto terminal = owner(f);
    const auto skipped = prepare(f.id, terminal, f.plan);
    check(skipped.diagnostic->segments.size() == 2 &&
              skipped.diagnostic->segments[1].skipped_at_common_end &&
              skipped.diagnostic->work_after.segment_calls_started == 1,
          "zero remainder made another thermal call");

    f = dry("all_wet_identity", 0);
    auto wet = owner(f);
    const auto wet_ok = prepare(f.id, wet, f.plan);
    check(wet_ok.diagnostic->work_after.segment_calls_started == 0 &&
              wet_ok.diagnostic->work_after.mass_calls_started == 0,
          "all-wet identity performed physical calls");
    {
        RoundingRestore restore;
        check(prepares < prepare_cap, "nonnearest prepare call cap");
        check(std::fesetround(FE_DOWNWARD) == 0, "set nonnearest rounding");
        const auto rejected = wet.prepare(f.plan);
        ++prepares;
        check(std::fesetround(restore.old) == 0, "restore rounding");
        observations.push_back(
            "{\"id\":\"nonnearest_all_wet_prepare\",\"action\":\"prepare\",\"diagnostic\":" +
            coupled_attempt_receipt_json(*rejected.diagnostic) + '}');
        check(!rejected.candidate &&
                  rejected.diagnostic->failure_code == "capability_unavailable" &&
                  wet.work_meter().segment_calls_started == 0 && wet.restart().revision == 0,
              "all-wet arithmetic guard");
    }
    bool rejected_constructor = false;
    {
        RoundingRestore restore;
        check(std::fesetround(FE_DOWNWARD) == 0, "set constructor rounding");
        try {
            auto unused = owner(f);
            (void)unused;
        } catch (const TerrestrialWaterError &e) {
            rejected_constructor = e.code == "capability_unavailable";
        }
    }
    check(rejected_constructor, "nonnearest constructor accepted");
    f = dry("invalid_uncertain_restart");
    f.initial.canonical_energy_error_j_m2[0] = 20;
    f.policy = {21};
    bool domain_refused = false;
    try {
        auto unused = owner(f);
        (void)unused;
    } catch (const TerrestrialWaterError &e) {
        domain_refused = e.code == "invalid_restart";
    }
    check(domain_refused, "invalid inherited full box accepted");
    observations.push_back("{\"id\":\"constructor_controls\",\"nonnearest_refused\":true,"
                           "\"uncertain_domain_refused\":true}");
}
#endif
} // namespace
int main(int argc, char **argv) {
    if (argc == 2 && std::string(argv[1]) == "--inventory") {
        std::cout << inventory() << '\n';
        return 0;
    }
#if !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) && LDBL_MANT_DIG >= 64 &&                  \
    LDBL_MAX_EXP >= 16384
    std::string error;
    try {
        run();
    } catch (const std::exception &e) {
        error = e.what();
    }
    std::cout
        << "{\"schema\":\"coupled_owner_controls_v1\",\"capability_available\":true,\"passed\":"
        << (error.empty() ? "true" : "false") << ",\"checks\":" << checks
        << ",\"prepare_calls\":" << prepares << ",\"commit_calls\":" << commits
        << ",\"mass_calls_started\":" << mass_calls << ",\"segment_calls_started\":" << segments
        << ",\"stage_calls_started\":" << stages << ",\"scalar_flux_evaluations\":" << fluxes
        << ",\"observations\":" << join(observations)
        << ",\"error\":" << (error.empty() ? "null" : quote(error)) << "}\n";
    return error.empty() ? 0 : 1;
#else
    std::cout << "{\"schema\":\"coupled_owner_controls_v1\",\"capability_available\":false,"
                 "\"status\":\"unsupported_backend_skipped\",\"prepare_calls\":0,\"segment_calls_"
                 "started\":0}\n";
    return 0;
#endif
}
