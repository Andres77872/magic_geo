#include "terrestrial_coupled.hpp"

#include <cfloat>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace magic_geo::detail;
namespace p = phase_segment_prototype;
namespace t = higher_order_thermal_prototype;

namespace {
constexpr const char *retained_sha =
    "0a0fd189844b3a7bfc00fa8abf366f4a1228100ea1585e0fa8c0d8cf6e021f4c";
constexpr double retained_time = 0.17750000251544407;
constexpr double retained_H = 1.2100000000000002;
constexpr double retained_error = 9.832600483208303e-9;
[[maybe_unused]] constexpr int prepare_cap = 16, commit_cap = 4;
[[maybe_unused]] constexpr std::uint64_t segment_cap = 16, stage_cap = 64,
                                         flux_cap = 16384;
[[maybe_unused]] int checks = 0, prepares = 0, commits = 0;
[[maybe_unused]] std::uint64_t segments = 0, stages = 0, fluxes = 0,
                               mass_calls = 0;
std::vector<std::string> observations;
std::vector<std::string> consumer_controls;

[[maybe_unused]] void check(bool ok, const char *message) {
  ++checks;
  if (!ok)
    throw std::runtime_error(message);
}
std::string json_quote(const std::string &text) {
  std::string result = "\"";
  for (unsigned char ch : text) {
    if (ch == '\\' || ch == '"')
      result += '\\';
    if (ch == '\n')
      result += "\\n";
    else if (ch == '\r')
      result += "\\r";
    else if (ch == '\t')
      result += "\\t";
    else
      result += static_cast<char>(ch);
  }
  return result + '"';
}
std::string join(const std::vector<std::string> &values) {
  std::string result = "[";
  for (const auto &value : values) {
    if (result.size() > 1)
      result += ',';
    result += value;
  }
  return result + ']';
}
struct Fixture {
  std::string id;
  std::string origin;
  std::vector<Cell> cells;
  CoupledProperties properties;
  CoupledRestart initial;
  CoupledAcceptancePolicy policy{0.01};
  CoupledLimits limits;
  CoupledIntervalPlan plan;
};
CoupledSegmentPlan fixed_plan(const std::string &id, p::Branch branch,
                              double end, p::StateBox tube) {
  return {id,
          branch,
          p::Goal::fixed_duration,
          end,
          tube,
          {1e-9, 1e-8, 0.001, 0.01},
          {1, 16, 2, 1024},
          {1e-12, 1e-12, 20, 8},
          false};
}
Fixture prefix(const std::string &id) {
  Fixture f;
  f.id = id;
  f.origin = "synthetic restart from retained accepted component state, error "
             "and coverage clock; "
             "the original refused owner bundle is not promoted";
  f.cells.resize(3);
  for (int i = 0; i < 3; ++i) {
    f.cells[i].id = i;
    f.cells[i].p = {1, 0, 0};
    f.cells[i].area_km2 = (i == 1 ? 4 : 2) * 1e-6;
    f.cells[i].temperature_c = -20;
    f.cells[i].precipitation_mm_y = 120;
  }
  f.cells[1].is_lake = true;
  f.cells[1].water_depth_m = 2;
  f.cells[2].is_water = true;
  f.cells[2].water_depth_m = 100;
  f.properties = {{1, 1, 1, 1.1}, 1000, 8, {{1, 0, 0, 0, 0}, {}, {}}};
  f.initial.elapsed_seconds = retained_time;
  f.initial.state = {{1.1, retained_H, 0}, {}, {}};
  f.initial.canonical_energy_error_j_m2 = {retained_error, 0, 0};
  f.plan = {0,
            0.25,
            {"nonrepresentable_source", 0, 1, {4, 0, 0}},
            {},
            {},
            {{0,
              {fixed_plan("raw_global_handoff", p::Branch::mixed, 0.25,
                          {{1.1, 1.8}, {0, 0}})}}}};
  return f;
}
Fixture original_full_plan() {
  auto f = prefix("original_event_then_global_continuation");
  f.origin = "new full plan from original retained initial state; second "
             "segment mode and raw "
             "initial-branch annotation changed; original event, forcing, "
             "tubes and budgets held";
  f.initial.elapsed_seconds = 0;
  f.initial.state[0].surface_enthalpy_j_m2 = 0.5;
  f.initial.canonical_energy_error_j_m2[0] = 0;
  const CoupledSegmentPlan event{"rounded_upper",
                                 p::Branch::mixed,
                                 p::Goal::next_phase_boundary,
                                 0.25,
                                 {{0.4, 1.6}, {0, 0}},
                                 {1e-9, 1e-11, 0.001, 1e-7},
                                 {48, 16, 48, 8192},
                                 {1e-12, 1e-12, 20, 8},
                                 false};
  f.plan.columns[0].segments.insert(f.plan.columns[0].segments.begin(), event);
  return f;
}
CoupledIntervalPlan later_liquid_plan() {
  auto plan = prefix("unused").plan;
  plan.expected_revision = 1;
  plan.end_seconds = 0.3125;
  auto step = fixed_plan("later_liquid", p::Branch::liquid, 0.3125,
                         {{1.4, 1.9}, {0, 0}});
  step.goal = p::Goal::within_branch;
  plan.columns[0].segments = {step};
  return plan;
}
std::vector<Fixture> refusal_fixtures() {
  std::vector<Fixture> result;
  auto f = prefix("fixed_physical_budget_refusal");
  f.plan.columns[0]
      .segments[0]
      .budgets.maximum_physical_event_state_error_j_m2 = 1e-30;
  result.push_back(f);
  f = prefix("fixed_incomplete_common_end");
  f.plan.columns[0].segments[0].latest_end_seconds = 0.1875;
  result.push_back(f);
  f = prefix("fixed_zero_budget_preflight");
  f.plan.columns[0]
      .segments[0]
      .budgets.maximum_physical_event_state_error_j_m2 = 0;
  result.push_back(f);
  f = prefix("unknown_goal_preflight");
  f.plan.columns[0].segments[0].goal = static_cast<p::Goal>(999);
  result.push_back(f);
  f = prefix("fixed_late_projection_refusal");
  f.cells[0].temperature_c = 1e308;
  result.push_back(f);
  f = prefix("fixed_source_boundary_preflight");
  f.plan.forcing.end_seconds = 0.2;
  result.push_back(f);
  f = prefix("fixed_complete_work_preflight");
  f.limits.max_stage_calls = 1;
  result.push_back(f);
  return result;
}
Fixture lower_crossing() {
  auto f = prefix("fixed_lower_zero_crossing");
  f.origin = "prescribed synthetic lower-boundary crossing; no retained "
             "trajectory claim";
  f.initial.elapsed_seconds = 0;
  f.initial.state[0].surface_enthalpy_j_m2 = -0.01;
  f.initial.canonical_energy_error_j_m2[0] = 0;
  f.plan.end_seconds = 0.015625;
  f.plan.columns[0].segments = {fixed_plan("lower_crossing", p::Branch::solid,
                                           0.015625, {{-0.02, 0.08}, {0, 0}})};
  return f;
}
Fixture nonmonotone_equilibrium() {
  auto f = prefix("fixed_nonmonotone_latent_equilibrium");
  f.origin = "prescribed synthetic exact latent equilibrium and nonmonotone "
             "flux enclosure";
  f.properties.water.latent_heat_j_kg = 1;
  f.initial.elapsed_seconds = 0;
  f.initial.state[0] = {1, 1, 0};
  f.initial.canonical_energy_error_j_m2[0] = 0;
  f.plan.forcing = {"equilibrium_source", 0, 1, {t::sigma_w_m2_k4, 0, 0}};
  f.plan.end_seconds = 0.0625;
  f.plan.columns[0].segments = {fixed_plan(
      "latent_equilibrium", p::Branch::mixed, 0.0625, {{0.9, 1.1}, {0, 0}})};
  return f;
}
Fixture retained_coupled_dry() {
  auto f = prefix("fixed_retained_radiative_sensible_dry");
  f.origin = "retained radiative_sensible_dry inputs and budgets; only goal "
             "changes from "
             "within_branch to fixed_duration";
  f.properties.water = {1, 1, 1, 1};
  f.properties.columns[0] = {10, 10, 0.5, 1, 0};
  f.initial.elapsed_seconds = 0;
  f.initial.state[0] = {0, 1, 0.5};
  f.initial.canonical_energy_error_j_m2[0] = 0;
  f.policy = {0.02};
  f.plan.forcing = {"dry_constant_source", 0, 1, {1, 0, 0}};
  f.plan.end_seconds = 0.0625;
  f.plan.columns[0].segments = {fixed_plan("dry_0", p::Branch::dry, 0.0625,
                                           {{0.99, 1.07}, {0.499, 0.505}})};
  return f;
}
std::string fixture_json(const Fixture &f) {
  CoupledAttemptReceipt description;
  description.surface_cells = f.cells;
  description.properties = f.properties;
  description.limits = f.limits;
  description.acceptance_policy = f.policy;
  description.initial = f.initial;
  description.observed_accepted_after = f.initial;
  description.private_prefix = f.initial;
  description.request_available = true;
  description.request = f.plan;
  description.observed_request_after = f.plan;
  return "{\"id\":" + json_quote(f.id) + ",\"origin\":" + json_quote(f.origin) +
         ",\"unexecuted_context_and_request\":" +
         coupled_attempt_receipt_json(description) + '}';
}
std::string inventory() {
  std::vector<std::string> entries;
  auto f = prefix("retained_liquid_annotation_refusal");
  f.plan.columns[0].segments[0].incoming_branch = p::Branch::liquid;
  f.plan.columns[0].segments[0].goal = p::Goal::within_branch;
  entries.push_back(fixture_json(f));
  f.id = "fixed_wrong_initial_branch_refusal";
  f.plan.columns[0].segments[0].goal = p::Goal::fixed_duration;
  entries.push_back(fixture_json(f));
  entries.push_back(fixture_json(original_full_plan()));
  for (const auto &item : refusal_fixtures())
    entries.push_back(fixture_json(item));
  entries.push_back(fixture_json(lower_crossing()));
  entries.push_back(fixture_json(nonmonotone_equilibrium()));
  entries.push_back(fixture_json(retained_coupled_dry()));
  return "{\"schema\":\"coupled_fixed_duration_inventory_v1\",\"execution\":"
         "\"none\","
         "\"retained_owner_stdout_sha256\":" +
         json_quote(retained_sha) +
         ",\"retained_observation_id\":\"round_down_upper_boundary_refusal\","
         "\"planned_prepare_calls\":14,\"planned_commit_attempts\":3,"
         "\"prepare_cap\":16,\"commit_cap\":4,\"segment_cap\":16,\"stage_cap\":"
         "64,"
         "\"flux_cap\":16384,\"mass_calls_expected\":0,\"helper_mutation_"
         "calls\":5,\"fixtures\":" +
         join(entries) + ",\"later_liquid_request\":" +
         coupled_interval_plan_json(later_liquid_plan()) +
         ",\"fixed_commit_sequence\":[\"full_plan_commit\",\"later_liquid_"
         "commit\","
         "\"first_candidate_replay_refusal\"]}";
}

#if !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) &&                     \
    LDBL_MANT_DIG >= 64 && LDBL_MAX_EXP >= 16384
TerrestrialCoupledOwner owner(const Fixture &f) {
  return TerrestrialCoupledOwner(capture_terrestrial_surface(f.cells, 17),
                                 f.properties, f.initial, f.policy, f.limits);
}
std::string physical(const TerrestrialCoupledOwner &x) {
  return "{\"context\":" + coupled_owner_context_json(x) +
         ",\"restart\":" + coupled_restart_json(x.restart()) +
         ",\"last_receipt\":" +
         (x.last_receipt() ? coupled_attempt_receipt_json(*x.last_receipt())
                           : "null") +
         '}';
}
CoupledPreparation prepare(const std::string &id, TerrestrialCoupledOwner &x,
                           const CoupledIntervalPlan &request,
                           const char *failure = nullptr) {
  check(prepares < prepare_cap, "prepare cap");
  std::uint64_t reserve_segments = 0, reserve_stages = 0, reserve_flux = 0;
  for (const auto &cell : request.columns) {
    for (const auto &step : cell.segments) {
      check(step.work.maximum_stage_calls >= 0 &&
                step.work.maximum_total_flux_evaluations >= 0,
            "negative fixed test reservation");
      ++reserve_segments;
      reserve_stages +=
          static_cast<std::uint64_t>(step.work.maximum_stage_calls);
      reserve_flux +=
          static_cast<std::uint64_t>(step.work.maximum_total_flux_evaluations);
    }
  }
  check(reserve_segments <= segment_cap - segments &&
            reserve_stages <= stage_cap - stages &&
            reserve_flux <= flux_cap - fluxes,
        "full prepare lacks test reservation");
  const auto before = physical(x);
  const auto request_before = coupled_interval_plan_json(request);
  const auto prior = x.work_meter();
  ++prepares;
  auto result = x.prepare(request);
  const auto after = physical(x);
  const auto request_after = coupled_interval_plan_json(request);
  const auto next = x.work_meter();
  segments += next.segment_calls_started - prior.segment_calls_started;
  stages += next.stage_calls_started - prior.stage_calls_started;
  fluxes += next.scalar_flux_evaluations - prior.scalar_flux_evaluations;
  mass_calls += next.mass_calls_started - prior.mass_calls_started;
  observations.push_back(
      "{\"id\":" + json_quote(id) + ",\"action\":\"prepare\",\"before\":" +
      before + ",\"after\":" + after + ",\"request_before\":" + request_before +
      ",\"request_after\":" + request_after +
      ",\"diagnostic\":" + coupled_attempt_receipt_json(*result.diagnostic) +
      ",\"candidate_available\":" + (result.candidate ? "true" : "false") +
      '}');
  check(before == after && request_before == request_after,
        "prepare changed state or request");
  check(next.prepare_attempts == prior.prepare_attempts + 1 &&
            next.observed_work_counts_complete,
        "prepare work counters");
  check(mass_calls == 0 && segments <= segment_cap && stages <= stage_cap &&
            fluxes <= flux_cap,
        "source-free or aggregate work contract");
  if (failure) {
    check(!result.candidate && !result.diagnostic->final &&
              result.diagnostic->failure_code == failure,
          "wrong prepare refusal");
  } else {
    check(result.candidate && result.diagnostic->prepared &&
              result.diagnostic->final,
          "expected complete candidate");
    for (const auto &c : result.diagnostic->coverage)
      check(c.complete && c.completed_end_seconds == request.end_seconds,
            "common endpoint");
  }
  return result;
}
void commit(const std::string &id, TerrestrialCoupledOwner &x,
            const CoupledIntervalCandidate &candidate,
            const char *expected = nullptr) {
  check(commits < commit_cap, "commit cap");
  const auto before = physical(x),
             meter = coupled_work_meter_json(x.work_meter());
  ++commits;
  std::string error;
  try {
    x.commit(candidate);
  } catch (const TerrestrialWaterError &e) {
    error = e.code;
  }
  observations.push_back("{\"id\":" + json_quote(id) +
                         ",\"action\":\"commit\",\"before\":" + before +
                         ",\"after\":" + physical(x) + ",\"error\":" +
                         (error.empty() ? "null" : json_quote(error)) + '}');
  check(coupled_work_meter_json(x.work_meter()) == meter,
        "commit spent solver work");
  if (expected)
    check(error == expected && physical(x) == before,
          "commit refusal not atomic");
  else
    check(error.empty() && coupled_restart_json(x.restart()) ==
                               coupled_restart_json(*candidate.receipt().final),
          "prepared bundle not published");
}
void fixed_semantics(const CoupledSegmentObservation &observation) {
  const auto &r = observation.receipt;
  check(r.accepted && r.guard.fixed_time_endpoint_proved &&
            !r.guard.first_physical_hit_proved &&
            !r.guard.no_physical_hit_proved,
        "fixed-duration proof claims");
  check(r.selected_duration_seconds == r.request.maximum_duration_seconds &&
            r.remaining_duration_seconds == 0 &&
            r.physical_time_error_seconds.upper == 0,
        "fixed-duration clock");
  check(r.stage_calls_started == 2 && r.duration_trials_started == 1,
        "fixed-duration work shape");
}
void check_consumer_rejections(const CoupledSegmentObservation &actual) {
  const std::vector<const char *> names = {
      "missing_fixed_endpoint", "forged_first_hit", "forged_no_hit",
      "nonzero_time_bound", "shortened_duration"};
  for (std::size_t i = 0; i < names.size(); ++i) {
    auto changed = actual.receipt;
    if (i == 0)
      changed.guard.fixed_time_endpoint_proved = false;
    if (i == 1)
      changed.guard.first_physical_hit_proved = true;
    if (i == 2)
      changed.guard.no_physical_hit_proved = true;
    if (i == 3)
      changed.physical_time_error_seconds.upper = 0.01;
    if (i == 4)
      changed.selected_duration_seconds *= 0.5;
    const auto result = certify_coupled_segment(
        changed, actual.error.inherited_error_j_m2, 0.01);
    consumer_controls.push_back(
        "{\"id\":" + json_quote(names[i]) +
        ",\"accepted\":" + (result.accepted ? "true" : "false") +
        ",\"failure_code\":" + json_quote(result.failure_code) + '}');
    check(!result.accepted &&
              result.failure_code == "thermal_certificate_refused",
          "fixed error consumer accepted forged certificate semantics");
  }
}
void run() {
  auto f = prefix("retained_liquid_annotation_refusal");
  f.plan.columns[0].segments[0].incoming_branch = p::Branch::liquid;
  f.plan.columns[0].segments[0].goal = p::Goal::within_branch;
  auto old = owner(f);
  auto rejected = prepare(f.id, old, f.plan, "thermal_refused");
  check(rejected.diagnostic->segments[0].receipt.failure_code ==
                "branch_refusal" &&
            old.work_meter().stage_calls_started == 0,
        "old raw latent handoff changed");
  f.id = "fixed_wrong_initial_branch_refusal";
  f.plan.columns[0].segments[0].goal = p::Goal::fixed_duration;
  auto wrong = owner(f);
  rejected = prepare(f.id, wrong, f.plan, "thermal_refused");
  check(rejected.diagnostic->segments[0].receipt.failure_code ==
                "branch_refusal" &&
            wrong.work_meter().stage_calls_started == 0,
        "fixed mode accepted false initial branch");

  f = original_full_plan();
  auto actual = owner(f);
  const auto full = prepare(f.id, actual, f.plan);
  const auto &event = full.diagnostic->segments[0];
  const auto &global = full.diagnostic->segments[1];
  check(event.receipt.accepted && event.receipt.guard.first_physical_hit_proved,
        "new full plan event did not qualify");
  check(global.generated_input.initial == event.receipt.final_state &&
            global.generated_input.start_seconds ==
                event.receipt.selected_end_seconds &&
            global.generated_input.water_mass_kg_m2 ==
                f.initial.state[0].water_mass_kg_m2,
        "event-to-fixed raw carry changed");
  check(global.generated_input.initial.surface_enthalpy_j_m2 == retained_H &&
            global.generated_input.start_seconds == retained_time,
        "unchanged original event differs from retained component");
  fixed_semantics(global);
  check_consumer_rejections(global);
  check(!global.receipt.selected_first_stage_in_incoming_branch &&
            global.receipt.final_state.surface_enthalpy_j_m2 > retained_H,
        "fixed continuation did not cross global phases");
  check(full.diagnostic->private_liquid_outbox.empty() &&
            full.diagnostic->final->canonical_energy_error_j_m2[0] >=
                event.error.final_error_j_m2,
        "source-free error carry or outbox");
  commit("full_plan_commit", actual, *full.candidate);
  const auto later =
      prepare("later_liquid_interval", actual, later_liquid_plan());
  check(later.diagnostic->segments[0].generated_input.initial ==
                global.receipt.final_state &&
            later.diagnostic->final->state[0].water_mass_kg_m2 == 1.1,
        "committed fixed state not carried to liquid segment");
  commit("later_liquid_commit", actual, *later.candidate);
  commit("first_candidate_replay_refusal", actual, *full.candidate,
         "stale_candidate");

  const auto fixtures = refusal_fixtures();
  const std::vector<const char *> failures = {
      "thermal_refused",    "incomplete_plan", "invalid_input", "invalid_plan",
      "projection_refusal", "forcing_refusal", "work_cap"};
  for (std::size_t i = 0; i < fixtures.size(); ++i) {
    auto x = owner(fixtures[i]);
    const auto result =
        prepare(fixtures[i].id, x, fixtures[i].plan, failures[i]);
    if (i == 0)
      check(result.diagnostic->segments[0].receipt.failure_code ==
                    "physical_budget_refusal" &&
                result.diagnostic->segments[0]
                    .receipt.numerical_candidate_available,
            "fixed physical refusal lost numerical candidate");
    if (i == 1)
      check(result.diagnostic->segments[0].receipt.accepted &&
                !result.diagnostic->coverage[0].complete &&
                result.diagnostic->coverage[0].completed_end_seconds == 0.1875,
            "incomplete fixed prefix not retained");
    if (i == 4)
      check(result.diagnostic->coverage[0].complete &&
                result.diagnostic->segments[0].receipt.accepted,
            "late projection failure occurred before fixed evolution");
    if (i == 2 || i == 3 || i == 5 || i == 6)
      check(x.work_meter().segment_calls_started == 0,
            "invalid plan spent physical calls");
  }
  f = lower_crossing();
  auto lower = owner(f);
  const auto lower_result = prepare(f.id, lower, f.plan);
  fixed_semantics(lower_result.diagnostic->segments[0]);
  check(lower_result.diagnostic->final->state[0].surface_enthalpy_j_m2 > 0 &&
            lower_result.diagnostic->final->state[0].surface_enthalpy_j_m2 <
                1.1,
        "lower boundary not crossed into mixed state");
  f = nonmonotone_equilibrium();
  auto equilibrium = owner(f);
  const auto equilibrium_result = prepare(f.id, equilibrium, f.plan);
  fixed_semantics(equilibrium_result.diagnostic->segments[0]);
  check(!equilibrium_result.diagnostic->segments[0]
                .receipt.guard.transverse_monotonicity_proved &&
            equilibrium_result.diagnostic->final->state[0]
                    .surface_enthalpy_j_m2 == 1,
        "nonmonotone equilibrium manufactured a crossing");
  f = retained_coupled_dry();
  auto coupled = owner(f);
  const auto coupled_result = prepare(f.id, coupled, f.plan);
  fixed_semantics(coupled_result.diagnostic->segments[0]);
  check(coupled_result.diagnostic->final->state[0].atmospheric_energy_j_m2 >
                0.5 &&
            coupled_result.diagnostic->final->state[0].surface_enthalpy_j_m2 >
                1,
        "retained radiative/sensible fixed mode did not advance both energies");
  check(prepares == 14 && commits == 3, "fixed inventory completeness");
}
#endif
} // namespace

int main(int argc, char **argv) {
  if (argc == 2 && std::string(argv[1]) == "--inventory") {
    std::cout << inventory() << '\n';
    return 0;
  }
#if !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) &&                     \
    LDBL_MANT_DIG >= 64 && LDBL_MAX_EXP >= 16384
  std::string error;
  try {
    run();
  } catch (const std::exception &e) {
    error = e.what();
  }
  std::cout << "{\"schema\":\"coupled_fixed_duration_controls_v1\",\"passed\":"
            << (error.empty() ? "true" : "false") << ",\"checks\":" << checks
            << ",\"prepare_calls\":" << prepares
            << ",\"commit_calls\":" << commits
            << ",\"mass_calls_started\":" << mass_calls
            << ",\"segment_calls_started\":" << segments
            << ",\"stage_calls_started\":" << stages
            << ",\"scalar_flux_evaluations\":" << fluxes
            << ",\"observations\":" << join(observations)
            << ",\"consumer_controls\":" << join(consumer_controls)
            << ",\"error\":" << (error.empty() ? "null" : json_quote(error))
            << "}\n";
  return error.empty() ? 0 : 1;
#else
  std::cout << "{\"schema\":\"coupled_fixed_duration_controls_v1\","
               "\"status\":\"unsupported_backend_skipped\",\"prepare_calls\":0,"
               "\"segment_calls_started\":0}\n";
  return 0;
#endif
}
