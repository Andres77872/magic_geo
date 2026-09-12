#include "terrestrial_water.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <optional>
#include <stdexcept>

using namespace magic_geo::detail;
namespace c = cryosphere_prototype;
namespace {
int checks = 0, prepares = 0, commits = 0;
std::vector<std::string> observations;
void require(bool ok, const char *message) {
    ++checks;
    if (!ok)
        throw std::runtime_error(message);
}
std::vector<Cell> cells(double temperature = -20, double area = 2e-6) {
    std::vector<Cell> x(3);
    for (int i = 0; i < 3; ++i) {
        x[i].id = i;
        x[i].area_km2 = area;
        x[i].p = {1, 0, 0};
        x[i].temperature_c = temperature;
        x[i].precipitation_mm_y = 120;
    }
    x[1].is_water = true;
    x[2].is_lake = true;
    return x;
}
TerrestrialWaterProperties props() { return {{8, 2, 4, 16}, 1000, 8, {1, 0, 0}}; }
TerrestrialWaterRestart empty() {
    TerrestrialWaterRestart x;
    x.state.resize(3);
    return x;
}
TerrestrialIntervalRequest pulse() {
    return {0, 1, {16, 0, 0}, {{"snow-1", 0, c::Phase::solid, 4, 8}}, {}};
}
std::string observed(const TerrestrialWaterOwner &owner) {
    return "{\"context\":" + terrestrial_water_context_json(owner) +
           ",\"restart\":" + terrestrial_water_restart_json(owner.restart()) +
           ",\"surface_revision\":" + std::to_string(owner.surface().surface_revision()) +
           ",\"last_receipt\":" +
           (owner.last_receipt() ? terrestrial_interval_receipt_json(*owner.last_receipt())
                                 : "null") +
           "}";
}
void log(const char *id, const char *operation, const std::string &before,
         const TerrestrialWaterOwner &owner, const char *status,
         const std::string &candidate = "null", const char *code = "none",
         const std::string &request_json = "null") {
    observations.push_back(std::string("{\"id\":\"") + id + "\",\"operation\":\"" + operation +
                           "\",\"status\":\"" + status + "\",\"error_code\":\"" + code +
                           "\",\"before\":" + before + ",\"after\":" + observed(owner) +
                           ",\"candidate_receipt\":" + candidate + ",\"request\":" + request_json +
                           "}");
}
TerrestrialIntervalCandidate prepare(const char *id, TerrestrialWaterOwner &owner,
                                     const TerrestrialIntervalRequest &request) {
    require(prepares < 40, "prepare cap");
    const auto before = observed(owner);
    ++prepares;
    auto candidate = owner.prepare(request);
    log(id, "prepare", before, owner, "accepted",
        terrestrial_interval_receipt_json(candidate.receipt()), "none",
        terrestrial_interval_request_json(request));
    require(observed(owner) == before, "prepare changed accepted owner");
    return candidate;
}
void reject_prepare(const char *id, TerrestrialWaterOwner &owner,
                    const TerrestrialIntervalRequest &request, const char *code) {
    require(prepares < 40, "prepare cap");
    const auto before = observed(owner);
    ++prepares;
    try {
        (void)owner.prepare(request);
    } catch (const TerrestrialWaterError &e) {
        log(id, "prepare", before, owner, "refused", "null", e.code.c_str(),
            terrestrial_interval_request_json(request));
        require(e.code == code, "unexpected prepare refusal");
        require(observed(owner) == before, "failed prepare changed accepted owner");
        return;
    }
    throw std::runtime_error("missing prepare refusal");
}
void commit(const char *id, TerrestrialWaterOwner &owner,
            const TerrestrialIntervalCandidate &candidate, const char *refusal = nullptr) {
    require(commits < 16, "commit cap");
    const auto before = observed(owner);
    ++commits;
    try {
        owner.commit(candidate);
    } catch (const TerrestrialWaterError &e) {
        log(id, "commit", before, owner, "refused",
            terrestrial_interval_receipt_json(candidate.receipt()), e.code.c_str());
        require(refusal && e.code == refusal, "unexpected commit refusal");
        require(observed(owner) == before, "failed commit changed accepted owner");
        return;
    }
    log(id, "commit", before, owner, "accepted",
        terrestrial_interval_receipt_json(candidate.receipt()));
    require(!refusal, "missing commit refusal");
}
} // namespace
int main() {
    try {
        if (!terrestrial_water_capability().available) {
            try {
                TerrestrialWaterOwner owner(capture_terrestrial_surface(cells()), props(), empty());
            } catch (const TerrestrialWaterError &e) {
                require(e.code == "capability_unavailable", "capability refusal code");
                std::cout
                    << "{\"schema\":\"terrestrial_owner_controls_v1\",\"capability_available\":"
                       "false,\"prepares_started\":0,\"commits_started\":0,\"checks\":"
                    << checks << ",\"observations\":[]}\n";
                return 0;
            }
            throw std::runtime_error("unavailable backend constructed owner");
        }
        auto snapshot = capture_terrestrial_surface(cells(), 7);
        TerrestrialWaterOwner owner(snapshot, props(), empty());
        auto first = prepare("retained_melt", owner, pulse());
        require(first.receipt().final.state[0] == c::State{2, 16}, "toy melt W/H");
        require(first.receipt().kernel_result.phase[0].liquid_mass_kg_m2 == 1, "toy melt phase");
        require(first.receipt().liquid_outbox.empty(), "unrequested liquid drainage");
        auto refeed = pulse();
        refeed.initial_liquid_withdrawals.push_back({"too-early", 0, 1});
        reject_prepare("same_interval_refeed", owner, refeed, "kernel_refusal");
        commit("first_commit", owner, first);
        auto stale = pulse();
        reject_prepare("stale_request", owner, stale, "stale_revision");
        stale.expected_revision = 1;
        reject_prepare("consumed_source", owner, stale, "duplicate_event");
        TerrestrialIntervalRequest withdraw{1, 1, {0, 0, 0}, {}, {{"out-1", 0, 1}}};
        auto overdraw = withdraw;
        overdraw.initial_liquid_withdrawals[0].mass_kg = 3;
        reject_prepare("initial_phase_overdraw", owner, overdraw, "kernel_refusal");
        auto second = prepare("later_liquid", owner, withdraw);
        require(second.receipt().final.state[0] == c::State{1.5, 8}, "toy withdrawal W/H");
        require(second.receipt().liquid_outbox[0].carried_enthalpy_j == 16,
                "outbox carried energy");
        require(second.receipt().projection.cells[0].delivered_liquid_depth_mm == .5, "toy depth");
        require(second.receipt().projection.cells[0].runoff_mm == .5, "cold supply runoff");
        TerrestrialWaterOwner restarted(snapshot, props(), owner.restart());
        auto replay = prepare("same_restart", restarted, withdraw);
        require(terrestrial_interval_receipt_json(replay.receipt()) ==
                    terrestrial_interval_receipt_json(second.receipt()),
                "same restart nondeterminism");
        commit("foreign_candidate", restarted, second, "foreign_candidate");
        auto parallel = prepare("parallel_private", owner, withdraw);
        auto moved = std::move(owner);
        commit("moved_owner_commit", moved, second);
        commit("replayed_candidate", moved, second, "stale_candidate");
        commit("stale_parallel_candidate", moved, parallel, "stale_candidate");
        require(moved.restart().consumed_event_ids.size() == 2, "ID consumption");
        auto duplicate = TerrestrialIntervalRequest{
            2, 1, {0, 0, 0}, {{"same", 0, c::Phase::solid, 1, 8}}, {{"same", 0, 1}}};
        reject_prepare("duplicate_namespaces", moved, duplicate, "duplicate_event");
        auto wet =
            TerrestrialIntervalRequest{2, 1, {0, 0, 0}, {{"wet", 2, c::Phase::solid, 1, 8}}, {}};
        reject_prepare("lake_import", moved, wet, "invalid_event");
        wet.precipitation_imports[0].cell_id = 1;
        reject_prepare("marine_import", moved, wet, "invalid_event");
        wet.precipitation_imports.clear();
        wet.net_heat_flux_w_m2[2] = 1;
        reject_prepare("wet_heat", moved, wet, "invalid_request");
        auto clock = empty();
        clock.elapsed_seconds = std::ldexp(1.0, 53);
        TerrestrialWaterOwner clock_owner(snapshot, props(), clock);
        reject_prepare("nonrepresentable_clock", clock_owner, pulse(), "invalid_clock");
        auto limited = TerrestrialWaterLimits{};
        limited.max_committed_intervals = 1;
        TerrestrialWaterOwner cap_owner(snapshot, props(), empty(), limited);
        auto cap_first = prepare("cap_first", cap_owner, pulse());
        commit("cap_commit", cap_owner, cap_first);
        reject_prepare("interval_cap", cap_owner, withdraw, "interval_cap");
        auto liquid = empty();
        liquid.state[0] = {3, 48};
        TerrestrialWaterOwner duplicates(snapshot, props(), liquid);
        auto twins = prepare("duplicate_numeric_exports", duplicates,
                             {0, 1, {0, 0, 0}, {}, {{"a", 0, 1}, {"b", 0, 1}}});
        require(twins.receipt().liquid_outbox[0].kernel_movement_index !=
                    twins.receipt().liquid_outbox[1].kernel_movement_index,
                "duplicate numeric export linkage");
        TerrestrialWaterOwner warm(capture_terrestrial_surface(cells(20), 8), props(), liquid);
        auto warm_out =
            prepare("warm_supply_partition", warm, {0, 1, {0, 0, 0}, {}, {{"warm-out", 0, 1}}});
        require(warm_out.receipt().projection.cells[0].actual_evapotranspiration_mm > 0 &&
                    warm_out.receipt().projection.cells[0].infiltration_mm > 0,
                "actual hydrology loss allocation not used");
        TerrestrialWaterOwner overflow(capture_terrestrial_surface(cells(1e308), 9), props(),
                                       liquid);
        reject_prepare("nonfinite_projection", overflow,
                       {0, 1, {0, 0, 0}, {}, {{"overflow", 0, 1}}}, "projection_refusal");
        auto precision_props = props();
        precision_props.water = {256, std::ldexp(1.0, 100), std::ldexp(1.0, 100), 1024};
        precision_props.dry_heat_capacity_j_m2_k[0] = std::ldexp(1.0, 100);
        TerrestrialWaterOwner precision(capture_terrestrial_surface(cells(-20, 1e-6), 10),
                                        precision_props, empty());
        auto precision_candidate =
            prepare("source_precision_1025_to_1", precision,
                    {0,
                     1,
                     {0, 0, 0},
                     {{"cold", 0, c::Phase::solid, 1, 255},
                      {"warm", 0, c::Phase::liquid, 1, 257},
                      {"latent", 0, c::Phase::liquid, std::ldexp(1.0, -10), 256}},
                     {}});
        require(precision_candidate.receipt().kernel_result.external_net_enthalpy_j == 1,
                "canonical source precision witness changed");
        std::string output = "{\"schema\":\"terrestrial_owner_controls_v1\",\"capability_"
                             "available\":true,\"prepares_started\":" +
                             std::to_string(prepares) +
                             ",\"commits_started\":" + std::to_string(commits) +
                             ",\"checks\":" + std::to_string(checks) + ",\"observations\":[";
        for (std::size_t i = 0; i < observations.size(); ++i) {
            if (i)
                output += ',';
            output += observations[i];
        }
        output += "]}\n";
        require(output.size() <= 10 * 1024 * 1024, "control output cap");
        std::cout << output;
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "ownership control failure: " << e.what() << "; observed prepares=" << prepares
                  << ", commits=" << commits << '\n';
        for (const auto &record : observations)
            std::cout << record << '\n';
        return 1;
    }
}
