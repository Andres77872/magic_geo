#include "terrestrial_coupled.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace magic_geo::detail;
namespace p = phase_segment_prototype;
namespace b = p::bounds;
namespace {
constexpr std::uint64_t prepare_cap = 10, thermal_cap = 128;
constexpr std::uint64_t planned_attempt_reservation = 90;
constexpr double final_time = 21600, global_error = 3340;
struct Counts {
    std::uint64_t checks = 0, failures = 0, prepares = 0, commits = 0;
    std::uint64_t reserved_attempts = 0, thermal = 0, stages = 0, flux = 0;
    std::uint64_t leaves = 0, automatic_attempts = 0, tube_passes = 0;
    std::uint64_t mass = 0, helper_calls = 0, helper_passes = 0;
    bool work_observed = true;
} count;
void check(bool ok, const char* message) {
    ++count.checks;
    if (!ok) { ++count.failures; std::cerr << message << '\n'; }
}
void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
bool exact(double a, double z) { return std::memcmp(&a, &z, sizeof(double)) == 0; }
std::string quote(const std::string& s) {
    std::string r = "\"";
    const char* hex = "0123456789abcdef";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { r += '\\'; r += static_cast<char>(c); }
        else if (c < 32) { r += "\\u00"; r += hex[c >> 4]; r += hex[c & 15]; }
        else r += static_cast<char>(c);
    }
    return r + '"';
}
std::string number(double x) {
    require(std::isfinite(x), "nonfinite test observation");
    std::ostringstream out; out.imbue(std::locale::classic());
    out << std::setprecision(std::numeric_limits<double>::max_digits10) << x;
    auto s = out.str();
    if (s.find_first_of(".eE") == std::string::npos) s += ".0";
    return s;
}
std::string interval(p::Interval x) {
    return "{\"lower\":" + number(x.lower) + ",\"upper\":" + number(x.upper) + '}';
}
struct Fixture {
    std::string id, expected_failure;
    std::vector<Cell> cells;
    CoupledProperties properties;
    CoupledRestart initial;
    CoupledLimits limits;
    CoupledAutomaticRequest request;
    bool expect_candidate = false, expect_late_prefix = false, expect_no_calls = false;
};
Fixture base(const std::string& id, std::size_t attempts) {
    Fixture f; f.id = id; f.cells.resize(3);
    for (int i = 0; i < 3; ++i) {
        auto& c = f.cells[static_cast<std::size_t>(i)];
        c.id = i; c.p = {1,0,0}; c.area_km2 = 1e-6;
        c.temperature_c = 10; c.precipitation_mm_y = 120;
    }
    f.cells[2].is_lake = true; f.cells[2].water_depth_m = 2;
    f.properties = {{273.15,2100,4186,334000},1000,31557600,
                    {{1e7,1e7,.5,10,.2},{1e7,1e7,.5,10,.2},{}}};
    f.initial.state = {{0,1e8,0},{10,2.5e6,0},{}};
    f.initial.canonical_energy_error_j_m2 = {7,7,0};
    f.request.end_seconds = final_time;
    f.request.forcing = {"constant-six-hour",0,final_time,{300,600,0}};
    auto& o = f.request.options;
    o.maximum_step_seconds = final_time; o.minimum_step_seconds = 0;
    o.maximum_attempts_per_cell = attempts; o.maximum_total_attempts = attempts;
    o.maximum_accepted_steps_per_cell = attempts; o.maximum_total_accepted_steps = attempts;
    o.maximum_tube_passes_per_attempt = 8; o.maximum_total_tube_passes = attempts*8;
    o.maximum_numerical_equation_defect_j_m2 = 1e-4;
    o.work = {1,16,2,1024}; o.stage_options = {1e-10,1e-12,30,12};
    o.reconstruction_leaves = 64;
    f.limits.max_cells = 3; f.limits.max_prepare_attempts = 1;
    // This is the separate manual-plan limit, not the automatic step budget.
    f.limits.max_committed_intervals = 2; f.limits.max_segments_per_cell = 1;
    f.limits.max_segment_calls = attempts; f.limits.max_duration_trials = attempts;
    f.limits.max_stage_calls = attempts*2; f.limits.max_flux_evaluations = attempts*1024;
    f.limits.max_reconstruction_leaves = attempts*64;
    return f;
}
std::vector<Fixture> fixtures() {
    std::vector<Fixture> fs;
    auto f = base("automatic_dry_melt_wet_complete",64); f.expect_candidate = true; fs.push_back(f);
    f = base("per_cell_attempt_cap",2); f.request.options.maximum_attempts_per_cell = 1;
    f.expected_failure = "work_cap"; fs.push_back(f);
    f = base("minimum_step_cannot_halve",8); f.request.options.minimum_step_seconds = final_time;
    f.expected_failure = "minimum_step_refusal"; fs.push_back(f);
    f = base("late_melt_no_error_headroom",8); f.initial.canonical_energy_error_j_m2[1] = global_error;
    f.expected_failure = "error_allocation_refused"; f.expect_late_prefix = true; fs.push_back(f);
    f = base("forcing_ends_before_macro",2); f.request.forcing.end_seconds = final_time/2;
    f.expected_failure = "forcing_refusal"; f.expect_no_calls = true; fs.push_back(f);
    f = base("invalid_nondyadic_leaf_policy",2); f.request.options.reconstruction_leaves = 3;
    f.expected_failure = "invalid_plan"; f.expect_no_calls = true; fs.push_back(f);
    f = base("stale_expected_revision",2); f.request.expected_revision = 1;
    f.expected_failure = "stale_revision"; f.expect_no_calls = true; fs.push_back(f);
    f = base("forcing_identity_changed",2); f.initial.forcing_history = {f.request.forcing};
    f.request.forcing.incident_shortwave_w_m2[1] = 601;
    f.expected_failure = "forcing_identity_refusal"; f.expect_no_calls = true; fs.push_back(f);
    return fs;
}
std::vector<p::Input> tube_inputs() {
    std::vector<p::Input> xs;
    for (int i = 0; i < 3; ++i) {
        p::Input x{}; x.segment_id = "raw-branch-" + std::to_string(i);
        x.physical_boundary_id = "helper-constant"; x.water = {1,1,1,1.1};
        x.column = {1,1,0,0,0,0}; x.water_mass_kg_m2 = 1.1;
        x.incident_shortwave_w_m2 = 4; x.maximum_duration_seconds = .015625;
        x.physical_boundary_seconds = 1; x.goal = p::Goal::fixed_duration;
        x.initial = {i == 0 ? -.01 : i == 1 ? 1.2100000000000002
            : std::nextafter(1.2100000000000002,std::numeric_limits<double>::infinity()),0};
        // Deliberately wrong metadata; raw state, not these hints, must govern.
        x.incoming_branch = p::Branch::dry; x.proposed_tube = {{99,100},{9,10}};
        x.budgets = {1e-9,1e-8,.001,.01}; x.limits = {1,16,2,1024};
        x.stage_options = {1e-12,1e-12,20,8};
        x.endpoint_certificate = p::EndpointCertificate::hermite_residual;
        x.reconstruction_leaves = 64; xs.push_back(x);
    }
    return xs;
}
std::string fixture_inventory(const Fixture& f) {
    // A serializer-only descriptor, explicitly unexecuted: no owner construction,
    // prepare, tube proposal, stage, calorimeter or projection is called here.
    CoupledAttemptReceipt d{}; d.surface_revision = 41; d.surface_cells = f.cells;
    d.properties = f.properties; d.acceptance_policy = {global_error}; d.limits = f.limits;
    d.initial = f.initial; d.observed_accepted_after = f.initial; d.private_prefix = f.initial;
    d.automatic_mode = true; d.automatic_request = f.request;
    d.observed_automatic_request_after = f.request;
    return "{\"id\":" + quote(f.id) + ",\"expected_candidate\":" + (f.expect_candidate?"true":"false")
        + ",\"expected_failure\":" + quote(f.expected_failure)
        + ",\"expect_late_private_prefix\":" + (f.expect_late_prefix?"true":"false")
        + ",\"expect_no_physical_calls\":" + (f.expect_no_calls?"true":"false")
        + ",\"unexecuted_context_and_request\":" + coupled_attempt_receipt_json(d) + '}';
}
std::string inventory(const std::vector<Fixture>& fs, const std::vector<p::Input>& ts) {
    std::string result = "{\"schema\":\"coupled_automatic_inventory_v1\",\"execution\":\"none\","
        "\"planned_prepares\":8,\"prepare_cap\":10,\"planned_attempt_reservation\":90,"
        "\"thermal_call_cap\":128,\"stage_cap\":256,\"scalar_flux_cap\":131072,"
        "\"reconstruction_leaf_cap\":8192,\"owner_tube_pass_cap\":720,"
        "\"helper_tube_calls\":3,\"helper_tube_pass_cap\":24,\"mass_calls_expected\":0,"
        "\"maximum_commit_attempts\":3,\"commit_order_if_candidate\":[\"foreign_refusal\",\"owner_commit\",\"stale_refusal\"],"
        "\"reconstruct_committed_restart_without_prepare\":true,"
        "\"rounding_discriminator\":{\"E0\":1.0,\"E\":1.0,\"B\":1.0000000000000002,\"N\":4,\"n\":1,\"U\":"
        + number(0x1p-55) + ",\"expected\":\"U_fits_but_outward_charge_exceeds_quota\"},\"fixtures\":[";
    for (std::size_t i = 0; i < fs.size(); ++i) { if (i) result += ','; result += fixture_inventory(fs[i]); }
    result += "],\"tube_helpers\":[";
    const char* branches[] = {"solid","mixed","liquid"};
    for (std::size_t i = 0; i < ts.size(); ++i) {
        if (i) result += ',';
        result += "{\"original_skeleton\":" + p::phase_segment_input_json(ts[i])
            + ",\"maximum_passes\":8,\"expected_branch\":" + quote(branches[i]) + '}';
    }
    return result + "]}";
}
void rounding_control() {
    const double E = 1, B = 1 + 0x1p-52, U = 0x1p-55;
    const double headroom = std::max(0.0,b::sub(b::point(B),b::point(E)).lower);
    const double quota = b::mul(b::point(headroom),b::div(b::point(1),b::point(4))).lower;
    const double next = b::add(b::point(E),b::point(U)).upper;
    const auto charge = b::sub(b::point(next),b::point(E));
    check(U <= quota,"rounding fixture local bound should fit");
    check(next <= B,"rounding fixture cumulative bound should fit");
    check(charge.upper > quota,"rounded allocation overspend was not detected");
    check(exact(next,B),"rounding fixture outward sum changed");
    std::cout << "{\"kind\":\"rounding_discriminator\",\"E\":" << number(E)
        << ",\"B\":" << number(B) << ",\"U\":" << number(U)
        << ",\"headroom_lower\":" << number(headroom) << ",\"quota_lower\":" << number(quota)
        << ",\"Eplus\":" << number(next) << ",\"charged_increment\":" << interval(charge)
        << ",\"allocation_accepts\":" << (charge.upper <= quota?"true":"false") << "}\n";
}
void tube_controls(const std::vector<p::Input>& xs) {
    const p::Branch expected[] = {p::Branch::solid,p::Branch::mixed,p::Branch::liquid};
    for (std::size_t i = 0; i < xs.size(); ++i) {
        const auto before = p::phase_segment_input_json(xs[i]);
        require(count.helper_calls < 3,"helper tube call cap"); ++count.helper_calls;
        p::TubeProposalReceipt r;
        try { r = p::propose_fixed_duration_tube(xs[i],8); }
        catch (...) { count.work_observed = false; throw; }
        check(r.passes_started >= 0 && r.passes_started <= 8,"helper tube pass cap");
        if (r.passes_started >= 0) count.helper_passes += static_cast<std::uint64_t>(r.passes_started);
        check(r.accepted && r.input_available,"raw branch helper qualification missed");
        if (r.input_available) {
            check(r.generated_input.incoming_branch == expected[i],"helper trusted wrong incoming branch");
            check(exact(r.generated_input.initial.surface_enthalpy_j_m2,xs[i].initial.surface_enthalpy_j_m2),"helper projected raw H");
        }
        for (const auto& pass : r.passes)
            check(!pass.guard.first_physical_hit_proved && !pass.guard.no_physical_hit_proved,
                  "fixed tube helper invented timing claim");
        check(before == p::phase_segment_input_json(xs[i]),"tube helper mutated input");
        std::cout << "{\"kind\":\"tube_helper\",\"original_skeleton\":" << before
            << ",\"observed_skeleton_after\":" << p::phase_segment_input_json(xs[i])
            << ",\"receipt\":" << p::tube_proposal_receipt_json(r) << "}\n";
    }
}
void account(const CoupledWorkMeter& a, const CoupledWorkMeter& z) {
    count.work_observed = count.work_observed && z.observed_work_counts_complete;
    const auto add = [](std::uint64_t before, std::uint64_t after, std::uint64_t& total) {
        check(after >= before,"work meter moved backwards");
        if (after >= before) total += after-before;
    };
    add(a.segment_calls_started,z.segment_calls_started,count.thermal);
    add(a.stage_calls_started,z.stage_calls_started,count.stages);
    add(a.scalar_flux_evaluations,z.scalar_flux_evaluations,count.flux);
    add(a.reconstruction_leaves_started,z.reconstruction_leaves_started,count.leaves);
    add(a.automatic_attempts_started,z.automatic_attempts_started,count.automatic_attempts);
    add(a.tube_passes_started,z.tube_passes_started,count.tube_passes);
    add(a.mass_calls_started,z.mass_calls_started,count.mass);
}
void inspect_chain(const Fixture& f, const CoupledAttemptReceipt& r) {
    auto states = f.initial.state;
    auto errors = f.initial.canonical_energy_error_j_m2;
    std::vector<std::uint64_t> ticks(states.size(),0);
    std::vector<std::size_t> accepted(states.size(),0);
    const CoupledSegmentObservation* previous = nullptr;
    bool melt_rejection = false, melt_halved = false;
    for (const auto& obs : r.segments) {
        check(obs.automatic_trial && obs.cell_id >= 0 && obs.cell_id < 2,"unexpected automatic cell or wet work");
        if (obs.cell_id < 0 || obs.cell_id >= 2) continue;
        const auto i = static_cast<std::size_t>(obs.cell_id);
        const auto& in = obs.request_available ? obs.generated_input : obs.automatic_skeleton;
        check(r.clock_quantum_seconds > 0 && obs.duration_ticks > 0 && obs.interval_ticks > 0,"missing exact clock");
        check(obs.begin_tick == ticks[i],"accepted tick gap or overlap");
        check(exact(in.water_mass_kg_m2,states[i].water_mass_kg_m2) &&
              exact(in.initial.surface_enthalpy_j_m2,states[i].surface_enthalpy_j_m2) &&
              exact(in.initial.atmospheric_energy_j_m2,states[i].atmospheric_energy_j_m2),"retry or carry changed raw state");
        check(exact(in.start_seconds,static_cast<double>(obs.begin_tick)*r.clock_quantum_seconds) &&
              exact(in.maximum_duration_seconds,static_cast<double>(obs.duration_ticks)*r.clock_quantum_seconds),"tick conversion changed");
        check(in.physical_boundary_id == f.request.forcing.id &&
              exact(in.physical_boundary_seconds,f.request.forcing.end_seconds) &&
              exact(in.incident_shortwave_w_m2,f.request.forcing.incident_shortwave_w_m2[i]),"forcing identity changed");
        check(in.goal == p::Goal::fixed_duration && in.endpoint_certificate == p::EndpointCertificate::hermite_residual,
              "automatic caller changed endpoint policy");
        check(exact(obs.interval_initial_error_j_m2,f.initial.canonical_energy_error_j_m2[i]),"allocation anchor changed");
        if (previous && previous->cell_id == obs.cell_id && !previous->accepted_for_private_carry) {
            check(obs.begin_tick == previous->begin_tick && obs.duration_ticks == previous->duration_ticks/2,
                  "refused step did not floor-halve from unchanged start");
            if (i == 1) melt_halved = true;
        }
        if (i == 1 && !obs.accepted_for_private_carry) melt_rejection = true;
        if (obs.accepted_for_private_carry) {
            check(obs.receipt_available && obs.receipt.accepted && obs.receipt.final_state_available &&
                  obs.error.accepted && obs.charged_increment_available,"private carry lacks accepted evidence");
            check(exact(obs.error.inherited_error_j_m2,errors[i]) && obs.error.final_error_j_m2 >= errors[i] &&
                  obs.error.final_error_j_m2 <= global_error,"inherited cumulative error changed");
            check(obs.charged_increment_j_m2.upper <= obs.offered_error_j_m2,"actual rounded charge exceeds fixed quota");
            check(obs.receipt.physical_time_error_seconds.upper == 0 &&
                  !obs.receipt.guard.first_physical_hit_proved && !obs.receipt.guard.no_physical_hit_proved,
                  "fixed-time continuation invented event timing");
            states[i].surface_enthalpy_j_m2 = obs.receipt.final_state.surface_enthalpy_j_m2;
            states[i].atmospheric_energy_j_m2 = obs.receipt.final_state.atmospheric_energy_j_m2;
            errors[i] = obs.error.final_error_j_m2; ticks[i] += obs.duration_ticks; ++accepted[i];
        }
        previous = &obs;
    }
    for (std::size_t i = 0; i < states.size(); ++i) {
        check(exact(r.private_prefix.state[i].water_mass_kg_m2,states[i].water_mass_kg_m2) &&
              exact(r.private_prefix.state[i].surface_enthalpy_j_m2,states[i].surface_enthalpy_j_m2) &&
              exact(r.private_prefix.state[i].atmospheric_energy_j_m2,states[i].atmospheric_energy_j_m2) &&
              exact(r.private_prefix.canonical_energy_error_j_m2[i],errors[i]),"private prefix differs from accepted-only carry");
    }
    if (r.prepared) {
        check(r.final.has_value() && r.coverage.size() == 3,"complete owner lacks final coverage");
        for (const auto& c : r.coverage) check(c.complete && exact(c.completed_end_seconds,final_time),"cell missed common endpoint");
        check(exact(static_cast<double>(ticks[0])*r.clock_quantum_seconds,final_time) &&
              exact(static_cast<double>(ticks[1])*r.clock_quantum_seconds,final_time),"accepted partitions do not span macro");
        if (f.expect_candidate) check(melt_rejection && melt_halved && accepted[1] > 1,"main qualification did not exercise automatic melt halving");
    }
    if (f.expect_late_prefix) {
        check(accepted[0] > 0 && exact(static_cast<double>(ticks[0])*r.clock_quantum_seconds,final_time),"late-cell refusal lost completed dry prefix");
        check(ticks[1] == 0 && !r.final.has_value(),"late-cell refusal published incomplete macro");
    }
}
TerrestrialCoupledOwner make_owner(const Fixture& f) {
    return TerrestrialCoupledOwner(capture_terrestrial_surface(f.cells,41),f.properties,
                                    f.initial,{global_error},f.limits);
}
void commit_checks(TerrestrialCoupledOwner& owner, const Fixture& f, const CoupledIntervalCandidate& candidate) {
    auto foreign = make_owner(f);
    const auto foreign_before = coupled_restart_json(foreign.restart());
    bool refused = false; ++count.commits;
    try { foreign.commit(candidate); } catch (const TerrestrialWaterError& e) { refused = e.code == "foreign_candidate"; }
    check(refused && coupled_restart_json(foreign.restart()) == foreign_before,"foreign commit mutated other owner");
    const bool foreign_refused = refused;
    ++count.commits; owner.commit(candidate);
    const auto committed = coupled_restart_json(owner.restart());
    check(owner.restart().revision == 1 && exact(owner.restart().elapsed_seconds,final_time),"valid commit missed atomic endpoint");
    check(candidate.receipt().final && committed == coupled_restart_json(*candidate.receipt().final),"commit differs from private candidate");
    TerrestrialCoupledOwner reconstructed(owner.surface(),owner.properties(),owner.restart(),
                                          owner.acceptance_policy(),owner.limits());
    check(coupled_restart_json(reconstructed.restart()) == committed &&
          coupled_owner_context_json(reconstructed) == coupled_owner_context_json(owner),
          "reconstructed owner changed committed restart or context");
    check(reconstructed.work_meter().prepare_attempts == 0 && reconstructed.work_meter().segment_calls_started == 0 &&
          reconstructed.work_meter().mass_calls_started == 0,"restart reconstruction performed physical work");
    refused = false; ++count.commits;
    try { owner.commit(candidate); } catch (const TerrestrialWaterError& e) { refused = e.code == "stale_candidate"; }
    check(refused && coupled_restart_json(owner.restart()) == committed,"stale commit mutated accepted owner");
    std::cout << "{\"kind\":\"commits\",\"fixture\":" << quote(f.id)
        << ",\"foreign_before\":" << foreign_before << ",\"foreign_after\":" << coupled_restart_json(foreign.restart())
        << ",\"foreign_refused\":" << (foreign_refused?"true":"false")
        << ",\"committed_before_stale\":" << committed << ",\"observed_after_stale\":" << coupled_restart_json(owner.restart())
        << ",\"reconstructed_restart\":" << coupled_restart_json(reconstructed.restart())
        << ",\"reconstructed_context\":" << coupled_owner_context_json(reconstructed)
        << ",\"reconstructed_work\":" << coupled_work_meter_json(reconstructed.work_meter())
        << ",\"stale_refused\":" << (refused?"true":"false") << "}\n";
}
void run_fixture(const Fixture& f) {
    require(count.prepares < prepare_cap && count.reserved_attempts + f.request.options.maximum_total_attempts <= thermal_cap,
            "global prepare/thermal reservation cap");
    auto owner = make_owner(f);
    const auto before = coupled_restart_json(owner.restart());
    const auto context = coupled_owner_context_json(owner);
    const auto request = coupled_automatic_request_json(f.request);
    const auto work_before = owner.work_meter();
    std::cout << "{\"kind\":\"before_prepare\",\"id\":" << quote(f.id)
        << ",\"request\":" << request << ",\"context\":" << context << ",\"restart\":" << before << "}\n";
    count.reserved_attempts += f.request.options.maximum_total_attempts; ++count.prepares;
    CoupledPreparation prepared;
    try { prepared = owner.prepare(f.request); }
    catch (...) {
        account(work_before,owner.work_meter());
        std::cout << "{\"kind\":\"prepare_exception_state\",\"id\":" << quote(f.id)
            << ",\"observed_restart\":" << coupled_restart_json(owner.restart())
            << ",\"observed_work\":" << coupled_work_meter_json(owner.work_meter()) << "}\n";
        throw;
    }
    account(work_before,owner.work_meter());
    require(prepared.diagnostic != nullptr,"missing automatic receipt");
    const auto& r = *prepared.diagnostic;
    std::cout << "{\"kind\":\"prepare\",\"id\":" << quote(f.id) << ",\"caller_request_before\":" << request
        << ",\"caller_request_after\":" << coupled_automatic_request_json(f.request)
        << ",\"context_before\":" << context << ",\"context_after\":" << coupled_owner_context_json(owner)
        << ",\"accepted_before\":" << before << ",\"accepted_after\":" << coupled_restart_json(owner.restart())
        << ",\"receipt\":" << coupled_attempt_receipt_json(r) << "}\n";
    check(before == coupled_restart_json(owner.restart()) && owner.last_receipt() == nullptr,"prepare changed public owner");
    check(context == coupled_owner_context_json(owner) && request == coupled_automatic_request_json(f.request),"prepare mutated context or request");
    check(prepared.candidate.has_value() == f.expect_candidate,"predeclared automatic qualification target missed");
    check(r.prepared == prepared.candidate.has_value() && r.final.has_value() == prepared.candidate.has_value(),"candidate/publication flags contradict");
    check(!r.original_source_accuracy_certified && r.private_liquid_outbox.empty() &&
          !r.mass_call_started && !r.mass_receipt_available,"source-free control invented mass/source authority");
    if (!f.expected_failure.empty()) check(!r.prepared && r.failure_code == f.expected_failure,"expected refusal differs");
    if (f.expect_no_calls) check(r.work_after.automatic_attempts_started == 0 &&
        r.work_after.segment_calls_started == 0 && r.work_after.mass_calls_started == 0,"preflight refusal spent physical work");
    inspect_chain(f,r);
    if (f.expect_candidate && prepared.candidate) commit_checks(owner,f,*prepared.candidate);
}
} // namespace
int main(int argc, char** argv) {
    std::cout.imbue(std::locale::classic());
    const auto fs = fixtures(); const auto ts = tube_inputs();
    if (argc == 2 && std::string(argv[1]) == "--inventory") { std::cout << inventory(fs,ts) << '\n'; return 0; }
    if (argc != 1) { std::cerr << "Only --inventory or the fixed control run is supported\n"; return 2; }
    try { rounding_control(); tube_controls(ts); }
    catch (const std::exception& e) { check(false,e.what()); std::cout << "{\"kind\":\"helper_exception\",\"detail\":" << quote(e.what()) << "}\n"; }
    for (const auto& f : fs) {
        try { run_fixture(f); }
        catch (const std::exception& e) { check(false,e.what()); std::cout << "{\"kind\":\"fixture_exception\",\"id\":" << quote(f.id) << ",\"detail\":" << quote(e.what()) << "}\n"; }
    }
    check(count.prepares == 8 && count.reserved_attempts == planned_attempt_reservation && count.commits <= 3,"fixed prepare/commit inventory changed");
    check(count.thermal <= thermal_cap && count.stages <= thermal_cap*2 && count.flux <= thermal_cap*1024 &&
          count.leaves <= thermal_cap*64 && count.tube_passes <= planned_attempt_reservation*8,"global work cap");
    check(count.mass == 0 && count.helper_calls == 3 && count.helper_passes <= 24,"mass/helper inventory changed");
    check(count.work_observed,"work counts unavailable");
    std::cout << "{\"kind\":\"summary\",\"checks\":" << count.checks << ",\"failures\":" << count.failures
        << ",\"prepares\":" << count.prepares << ",\"commit_attempts\":" << count.commits
        << ",\"reserved_thermal_attempts\":" << count.reserved_attempts << ",\"thermal_calls_started\":" << count.thermal
        << ",\"stages_started\":" << count.stages << ",\"scalar_flux_evaluations\":" << count.flux
        << ",\"reconstruction_leaves_started\":" << count.leaves << ",\"automatic_attempts_started\":" << count.automatic_attempts
        << ",\"owner_tube_passes_started\":" << count.tube_passes << ",\"helper_tube_calls_started\":" << count.helper_calls
        << ",\"helper_tube_passes_started\":" << count.helper_passes << ",\"mass_calls_started\":" << count.mass
        << ",\"work_counts_complete\":" << (count.work_observed?"true":"false") << "}\n";
    return count.failures ? 1 : 0;
}
