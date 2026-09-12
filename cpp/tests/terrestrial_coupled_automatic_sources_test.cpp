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
namespace a = cryosphere_prototype;
namespace p = phase_segment_prototype;
namespace b = p::bounds;
namespace {
constexpr std::uint64_t prepare_cap = 20, thermal_cap = 256;

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
struct Fixture {
    std::string id, expected_failure;
    std::vector<Cell> cells;
    CoupledProperties properties;
    CoupledRestart initial;
    CoupledLimits limits;
    CoupledAutomaticRequest request;
    bool expect_candidate = false, expect_late_prefix = false, expect_no_calls = false;
    bool expect_mass_refusal = false, expect_jump_refusal = false;
    std::string initial_binding;
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
    f.limits.max_cells = 3; f.limits.max_prepare_attempts = 8;
    // This is the separate manual-plan limit, not the automatic step budget.
    f.limits.max_committed_intervals = 4; f.limits.max_segments_per_cell = 1;
    f.limits.max_segment_calls = attempts; f.limits.max_duration_trials = attempts;
    f.limits.max_stage_calls = attempts*2; f.limits.max_flux_evaluations = attempts*1024;
    f.limits.max_reconstruction_leaves = attempts*64;
    return f;
}
std::vector<Fixture> fixtures() {
    std::vector<Fixture> fs;
    auto main = base("sourced_six_hour",64);
    main.request.imports = {{"snow-0",0,a::Phase::solid,1,263.15},
                            {"rain-0",1,a::Phase::liquid,.25,273.15}};
    main.request.initial_liquid_withdrawals = {{"runoff-0",1,.1}};
    main.expect_candidate = true; fs.push_back(main);
    auto f=main; f.id="duplicate_import_id"; f.expect_candidate=false; f.expect_no_calls=true;
    f.request.imports.push_back(f.request.imports.front()); f.expected_failure="duplicate_event"; fs.push_back(f);
    f=main; f.id="cross_kind_duplicate_id"; f.expect_candidate=false; f.expect_no_calls=true;
    f.request.initial_liquid_withdrawals[0].id="snow-0"; f.expected_failure="duplicate_event"; fs.push_back(f);
    f=main; f.id="wet_source_refused"; f.expect_candidate=false; f.expect_no_calls=true;
    f.request.imports[0].cell_id=2; f.expected_failure="invalid_event"; fs.push_back(f);
    f=main; f.id="wrong_phase_temperature"; f.expect_candidate=false; f.expect_no_calls=true;
    f.request.imports[0].temperature_k=274; f.expected_failure="invalid_event"; fs.push_back(f);
    f=main; f.id="event_capacity"; f.expect_candidate=false; f.expect_no_calls=true;
    f.limits.max_events_per_interval=2; f.expected_failure="event_cap"; fs.push_back(f);
    f=main; f.id="retained_id_capacity"; f.expect_candidate=false; f.expect_no_calls=true;
    f.limits.max_consumed_event_ids=3; f.initial.consumed_event_ids={"old"}; f.expected_failure="event_cap"; fs.push_back(f);
    f=main; f.id="work_reservation_before_A"; f.expect_candidate=false; f.expect_no_calls=true;
    f.limits.max_stage_calls=1; f.expected_failure="work_cap"; fs.push_back(f);
    f=base("same_batch_rain_cannot_fund_withdrawal",2); f.expect_mass_refusal=true;
    f.request.imports={{"rain",0,a::Phase::liquid,1,273.15}};
    f.request.initial_liquid_withdrawals={{"unfunded",0,.5}}; f.expected_failure="mass_refused"; fs.push_back(f);
    f=base("uncertain_initial_liquid_refused",2); f.expect_jump_refusal=true;
    f.initial.state[0]={1,1,0}; f.request.initial_liquid_withdrawals={{"uncertain",0,1e-6}};
    f.expected_failure="error_budget_refused"; fs.push_back(f);
    f=base("late_thermal_refusal_after_A",8); f.initial.canonical_energy_error_j_m2[1]=global_error;
    f.request.imports={{"snow-late",0,a::Phase::solid,1,263.15}};
    f.expect_late_prefix=true; f.expected_failure="error_allocation_refused"; fs.push_back(f);
    // Small preflight reservations still cover both exposed cells; no solver
    // work is expected in these cases, but the suite counts all declared caps.
    for (std::size_t i=1;i<8;++i) {
        auto& o=fs[i].request.options; o.maximum_total_attempts=2;
        o.maximum_attempts_per_cell=2; o.maximum_total_accepted_steps=2;
        o.maximum_accepted_steps_per_cell=2; o.maximum_total_tube_passes=16;
    }
    return fs;
}
std::vector<Fixture> calendar_templates() {
    auto main=fixtures().front();
    auto stale=main; stale.id="stale_after_commit"; stale.expect_candidate=false;
    stale.expect_no_calls=true; stale.expected_failure="stale_revision";
    stale.initial_binding="committed_sourced_six_hour";
    auto repeated=stale; repeated.id="consumed_after_commit";
    repeated.request.expected_revision=1; repeated.request.end_seconds=21660;
    repeated.request.forcing={"next-minute",21600,21660,{300,600,0}};
    repeated.expected_failure="duplicate_event";
    auto next=repeated; next.id="nonzero_start_next_sources"; next.expect_candidate=true;
    next.expect_no_calls=false; next.expected_failure="";
    next.request.imports={{"snow-1",0,a::Phase::solid,.125,268.15}};
    next.request.initial_liquid_withdrawals={{"runoff-1",1,.2}};
    for (auto* f : {&stale,&repeated,&next}) {
        f->request.options.maximum_total_attempts=8;
        f->request.options.maximum_attempts_per_cell=8;
        f->request.options.maximum_total_accepted_steps=8;
        f->request.options.maximum_accepted_steps_per_cell=8;
        f->request.options.maximum_total_tube_passes=64;
    }
    return {stale,repeated,next};
}
std::string fixture_inventory(const Fixture& f) {
    // A serializer-only descriptor, explicitly unexecuted: no owner construction,
    // prepare, tube proposal, stage, calorimeter or projection is called here.
    CoupledAttemptReceipt d{}; d.surface_revision = 41; d.surface_cells = f.cells;
    d.properties = f.properties; d.acceptance_policy = {global_error}; d.limits = f.limits;
    d.initial = f.initial; d.observed_accepted_after = f.initial; d.private_prefix = f.initial;
    if (!f.initial_binding.empty()) {
        d.initial = {}; d.observed_accepted_after = {}; d.private_prefix = {};
    }
    d.automatic_mode = true; d.automatic_request = f.request;
    d.observed_automatic_request_after = f.request;
    return "{\"id\":" + quote(f.id) + ",\"expected_candidate\":" + (f.expect_candidate?"true":"false")
        + ",\"expected_failure\":" + quote(f.expected_failure)
        + ",\"initial_binding\":" + quote(f.initial_binding)
        + ",\"expect_late_private_prefix\":" + (f.expect_late_prefix?"true":"false")
        + ",\"expect_no_physical_calls\":" + (f.expect_no_calls?"true":"false")
        + ",\"expect_mass_refusal\":" + (f.expect_mass_refusal?"true":"false")
        + ",\"expect_jump_refusal\":" + (f.expect_jump_refusal?"true":"false")
        + ",\"unexecuted_context_and_request\":" + coupled_attempt_receipt_json(d) + '}';
}
std::string inventory(const std::vector<Fixture>& fs, const std::vector<Fixture>& sequence) {
    std::string out="{\"schema\":\"coupled_automatic_sources_inventory_v1\",\"execution\":\"none\","
        "\"planned_prepares\":14,\"prepare_cap\":20,\"thermal_call_cap\":256,"
        "\"planned_attempt_reservation\":114,\"maximum_commit_attempts\":6,"
        "\"mass_call_cap\":5,\"fixtures\":[";
    for (std::size_t i=0;i<fs.size();++i) {if(i)out+=',';out+=fixture_inventory(fs[i]);}
    out+="],\"after_first_commit\":[";
    for (std::size_t i=0;i<sequence.size();++i) {if(i)out+=',';out+=fixture_inventory(sequence[i]);}
    return out+"]}";
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
    if (!r.thermal_initial) { check(r.segments.empty(),"thermal work without certified post-A anchor"); return; }
    const auto& anchor=*r.thermal_initial;
    check(anchor.revision==f.initial.revision && exact(anchor.elapsed_seconds,f.initial.elapsed_seconds) &&
          anchor.consumed_event_ids==f.initial.consumed_event_ids &&
          anchor.forcing_history.size()==f.initial.forcing_history.size(),"post-A anchor published clock or IDs");
    auto states = anchor.state;
    auto errors = anchor.canonical_energy_error_j_m2;
    for (std::size_t i=0;i<2;++i) {
        check(r.mass_error[i].accepted && exact(errors[i],r.mass_error[i].final_error_j_m2),"post-A error differs from jump");
        check(exact(states[i].atmospheric_energy_j_m2,f.initial.state[i].atmospheric_energy_j_m2),"A changed Ea");
        check(errors[i]>=f.initial.canonical_energy_error_j_m2[i],"A reset inherited error");
    }
    const auto first_tick=static_cast<std::uint64_t>(f.initial.elapsed_seconds/r.clock_quantum_seconds);
    std::vector<std::uint64_t> ticks(states.size(),first_tick);
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
        check(exact(obs.interval_initial_error_j_m2,anchor.canonical_energy_error_j_m2[i]),"allocation anchor changed");
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
        for (const auto& c : r.coverage) check(c.complete && exact(c.completed_end_seconds,f.request.end_seconds),"cell missed common endpoint");
        check(exact(static_cast<double>(ticks[0])*r.clock_quantum_seconds,f.request.end_seconds) &&
              exact(static_cast<double>(ticks[1])*r.clock_quantum_seconds,f.request.end_seconds),"accepted partitions do not span macro");
        if (f.id=="sourced_six_hour") check(melt_rejection && melt_halved && accepted[1] > 1,"main qualification did not exercise automatic melt halving");
    }
    if (f.expect_late_prefix) {
        check(accepted[0] > 0 && exact(static_cast<double>(ticks[0])*r.clock_quantum_seconds,f.request.end_seconds),"late-cell refusal lost completed dry prefix");
        check(ticks[1] == first_tick && !r.final.has_value(),"late-cell refusal published incomplete macro");
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
    check(owner.restart().revision == f.initial.revision+1 && exact(owner.restart().elapsed_seconds,f.request.end_seconds),"valid commit missed atomic endpoint");
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
CoupledPreparation run_fixture(const Fixture& f, TerrestrialCoupledOwner& owner) {
    require(count.prepares < prepare_cap && count.reserved_attempts + f.request.options.maximum_total_attempts <= thermal_cap,
            "global prepare/thermal reservation cap");
    const auto last=owner.last_receipt();
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
    check(before == coupled_restart_json(owner.restart()) && owner.last_receipt() == last,"prepare changed public owner");
    check(context == coupled_owner_context_json(owner) && request == coupled_automatic_request_json(f.request),"prepare mutated context or request");
    check(prepared.candidate.has_value() == f.expect_candidate,"predeclared automatic qualification target missed");
    check(r.prepared == prepared.candidate.has_value() && r.final.has_value() == prepared.candidate.has_value(),"candidate/publication flags contradict");
    check(!r.original_source_accuracy_certified,"canonical receipt invented source accuracy");
    if (r.thermal_initial) check(r.mass_call_started && r.mass_receipt_available,"post-source anchor lacks actual A");
    if (f.expect_mass_refusal) check(r.mass_call_started && !r.mass_receipt_available &&
        !r.thermal_initial && r.segments.empty(),"mass refusal invented downstream state");
    if (f.expect_jump_refusal) check(r.mass_receipt_available && !r.thermal_initial &&
        r.segments.empty(),"jump refusal started thermal work");
    if (f.expect_late_prefix) check(r.mass_receipt_available && r.thermal_initial && !r.projection_available,
        "late thermal refusal lost source diagnostic or published projection");
    if (r.prepared) {
        check(r.projection_available && r.energy_ledger_available && r.mass_receipt_available,"complete source interval lacks ledger");
        check(r.private_liquid_outbox.size()==f.request.initial_liquid_withdrawals.size(),"outbox source coverage");
        check(exact(r.energy_ledger.canonical_external_enthalpy_j,r.mass_receipt.external_net_enthalpy_j),"source ledger differs from A");
        auto ids=f.initial.consumed_event_ids;
        for(const auto& x:f.request.imports)ids.push_back(x.id);
        for(const auto& x:f.request.initial_liquid_withdrawals)ids.push_back(x.id);
        std::sort(ids.begin(),ids.end());
        check(r.final->consumed_event_ids==ids,"final source IDs differ");
        if(f.id=="sourced_six_hour") check(r.thermal_initial->canonical_energy_error_j_m2[1]>
            f.initial.canonical_energy_error_j_m2[1],"decimal movement did not exercise nonzero jump charge");
    }
    if (!f.expected_failure.empty()) check(!r.prepared && r.failure_code == f.expected_failure,"expected refusal differs");
    if (f.expect_no_calls) check(r.work_after.automatic_attempts_started == work_before.automatic_attempts_started &&
        r.work_after.segment_calls_started == work_before.segment_calls_started &&
        r.work_after.mass_calls_started == work_before.mass_calls_started,"preflight refusal spent physical work");
    inspect_chain(f,r);
    return prepared;
}
} // namespace
int main(int argc,char** argv) {
    std::cout.imbue(std::locale::classic());
    const auto fs=fixtures(); const auto sequence=calendar_templates();
    if(argc==2 && std::string(argv[1])=="--inventory") {std::cout<<inventory(fs,sequence)<<'\n';return 0;}
    if(argc!=1)return 2;
    for(const auto& f:fs) {
        try {
            auto owner=make_owner(f); auto prepared=run_fixture(f,owner);
            if(f.expect_candidate && prepared.candidate) {
                commit_checks(owner,f,*prepared.candidate);
                for(auto next:sequence) {
                    next.initial=owner.restart();
                    auto continuation=run_fixture(next,owner);
                    if(next.expect_candidate && continuation.candidate)commit_checks(owner,next,*continuation.candidate);
                }
            }
        } catch(const std::exception& e) {
            check(false,e.what());std::cout<<"{\"kind\":\"fixture_exception\",\"id\":"<<quote(f.id)<<",\"detail\":"<<quote(e.what())<<"}\n";
        }
    }
    check(count.prepares==14 && count.reserved_attempts==114 && count.commits==6,"predeclared calendar inventory missed");
    check(count.thermal<=thermal_cap && count.stages<=thermal_cap*2 && count.flux<=thermal_cap*1024 &&
        count.leaves<=thermal_cap*64 && count.tube_passes<=114*8 && count.mass==5,"work or source call inventory changed");
    check(count.work_observed,"work counts unavailable");
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<count.checks<<",\"failures\":"<<count.failures
        <<",\"prepares\":"<<count.prepares<<",\"commit_attempts\":"<<count.commits
        <<",\"reserved_thermal_attempts\":"<<count.reserved_attempts<<",\"thermal_calls_started\":"<<count.thermal
        <<",\"stages_started\":"<<count.stages<<",\"scalar_flux_evaluations\":"<<count.flux
        <<",\"reconstruction_leaves_started\":"<<count.leaves<<",\"automatic_attempts_started\":"<<count.automatic_attempts
        <<",\"owner_tube_passes_started\":"<<count.tube_passes<<",\"mass_calls_started\":"<<count.mass
        <<",\"work_counts_complete\":"<<(count.work_observed?"true":"false")<<"}\n";
    return count.failures?1:0;
}
