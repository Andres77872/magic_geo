#include "layered_ice_owner.hpp"

#include <algorithm>
#include <array>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

namespace {
using namespace magic_geo::detail;
namespace a = cryosphere_prototype;
constexpr std::uint64_t geographic_revision = 73;
constexpr const char* retained_path = "runs/layered-ice-owner-review/evidence/layered-owner-qualification/qualification.stdout";
constexpr const char* retained_sha = "10d8e3f38ef3293e332e733809957fe61afa8fa3d3d2532bc1b16ff1eb30f8ce";
int checks = 0, misses = 0, captures = 0, constructors = 0, prepares = 0, commits = 0;

std::string quoted(const std::string& x) { std::ostringstream o; o << std::quoted(x); return o.str(); }
std::string numeric(double x) { std::ostringstream o; o << std::setprecision(17) << x; return o.str(); }
template<class Range, class F> std::string array(const Range& values, F encode) {
    std::string out = "[";
    for (const auto& x : values) { if (out.size() > 1) out += ','; out += encode(x); }
    return out + ']';
}
void check(bool ok, const std::string& name) {
    ++checks; if (!ok) ++misses;
    std::cout << "{\"kind\":\"check\",\"name\":" << quoted(name)
              << ",\"passed\":" << (ok ? "true" : "false") << "}\n";
}
bool contains(EnthalpyMeshInterval x, double value) { return x.lower <= value && value <= x.upper; }

// Plain inputs only. Inventory never captures geography, builds a graph,
// constructs an owner, prepares a candidate, or calls any physics producer.
struct SeedSpec {
    std::string owner_id;
    LayeredIceInput input;
    double elapsed_seconds = 0, joint_energy_error_j = 0, budget_j = 0;
    LayeredIceOwnerLimits limits;
    std::vector<int> geographic_cell_ids;
    std::vector<LayeredIceOwnedParcel> pending_outboxes;
    std::vector<std::string> consumed_event_ids;
    std::vector<LayeredIceOwnerForcing> forcing_history;
};
std::vector<Cell> geography(bool changed_receiver = false) {
    std::vector<Cell> cells(2);
    for (int i = 0; i < 2; ++i) {
        auto& c = cells[static_cast<std::size_t>(i)];
        c.id = i; c.area_km2 = i == 0 ? 1e-6 : 2e-6;
        c.neighbors = {1-i}; c.elevation_m = i == 0 ? 2 : 1;
        c.filled_elevation_m = c.elevation_m;
        c.hydrologic_surface_elevation_m = c.elevation_m;
        c.hydrologic_surface_conditioned = true;
        c.hydrologic_flow_slope = i == 0 ? .001 : 0;
        c.flow_to = i == 0 && !changed_receiver ? 1 : -1;
    }
    return cells;
}
LayeredIceOwnerLimits limits() {
    LayeredIceOwnerLimits x;
    x.max_prepare_attempts = 24; x.max_commits = 8; x.max_concurrent_preparations = 2;
    x.max_events_per_transition = 2; x.max_consumed_events = 16; x.max_pending_outboxes = 3;
    x.max_thermal_nodes = 8; x.max_thermal_edges = 7; x.max_node_leaves = 64;
    x.max_receipt_bytes = 4194304; x.max_history_bytes = 33554432;
    return x;
}
SeedSpec science_seed(std::string name) {
    SeedSpec s; s.owner_id = std::move(name); s.limits = limits();
    s.elapsed_seconds = 2700; s.joint_energy_error_j = 73.213726022026734;
    s.budget_j = 3340; s.geographic_cell_ids = {0,1};
    auto& in = s.input; in.id = "retained_900_second_layered_endpoint";
    in.complete_horizontal_coverage_declared = true;
    in.bottom_boundary = LayeredIceBottomBoundary::insulated;
    in.water = {273.15,2100,4186,334000};
    const std::array<double,8> H = {235662.1362658024,-205130.99537095171,
        -215932.10159911698,-4190107.9767496069,640662.13626580243,
        -205387.73003349357,-215932.10159911698,-4190107.9767496069};
    for (int i = 0; i < 2; ++i) {
        LayeredIceColumnInput c; c.cell_id = i; c.area_m2 = i+1;
        c.top_closure = LayeredIceTopClosure::coarse_combined_surface_atmosphere;
        c.top_nonwater_heat_capacity_j_m2_k = 1e7; c.top_longwave_emissivity = .6;
        c.top_absorbed_shortwave_w_m2 = i == 0 ? 300 : 450;
        c.layers = {{0,50.9,H[4*i],300,.3},{1,i == 0 ? 99.875 : 100,H[4*i+1],917,2.29},
            {2,100,H[4*i+2],917,2.29},{3,1000,H[4*i+3],917,2.29}};
        c.deep_inventory = LayeredIceDeepInventoryInput{99999,-2099979000,917};
        in.columns.push_back(c);
        LayeredMaterialParcelCertificate p;
        p.movement = {"drain_"+std::to_string(i),{i,0},{-1,-1},a::Phase::liquid,i == 0 ? .1 : .2,0};
        p.donor_temperature_k = 273.15; p.specific_enthalpy_j_kg = 334000;
        p.carried_enthalpy_j = i == 0 ? 33400 : 66800;
        p.ideal_specific_enthalpy_j_kg = {334000,334000};
        p.ideal_carried_enthalpy_j = i == 0
            ? EnthalpyMeshInterval{33399.999999999993,33400.000000000007}
            : EnthalpyMeshInterval{66799.999999999985,66800.000000000015};
        p.energy_projection_j = i == 0
            ? EnthalpyMeshInterval{-7.2759576141834275e-12,7.2759576141834275e-12}
            : EnthalpyMeshInterval{-1.4551915228366855e-11,1.4551915228366855e-11};
        p.external_outbox = true;
        s.pending_outboxes.push_back({"retained_material_900s",0,p,i});
    }
    in.horizontal_climate_edges = {{0,1,.1}};
    LayeredMaterialParcelCertificate cold;
    cold.movement = {"cold_export",{0,1},{-1,-1},a::Phase::solid,.125,0};
    cold.donor_temperature_k = 272.17196319031666;
    cold.specific_enthalpy_j_kg = -2053.8773003349356;
    cold.carried_enthalpy_j = -256.73466254186695;
    cold.ideal_specific_enthalpy_j_kg = {-2053.877300334937,-2053.8773003349343};
    cold.ideal_carried_enthalpy_j = {-256.73466254186718,-256.73466254186673};
    cold.energy_projection_j = {-2.2737367544323211e-13,2.2737367544323211e-13};
    cold.external_outbox = true;
    s.pending_outboxes.push_back({"material_only_cold_export",1,cold,0});
    s.consumed_event_ids = {"cold_export","drain_0","drain_1","refill_0","refill_1"};
    s.forcing_history = {{"retained_0_900_forcing",0,900,{300,450}},
        {"retained_900_1800_forcing",900,1800,{300,450}},
        {"forcing_1800_2700",1800,2700,{300,450}}};
    return s;
}
SeedSpec toy_seed() {
    SeedSpec s; s.owner_id = "toy"; s.limits = limits(); s.budget_j = 128;
    s.geographic_cell_ids = {0,1};
    auto& in = s.input; in.id = "fixed_absorption_projection_deep_floor";
    in.complete_horizontal_coverage_declared = true;
    in.bottom_boundary = LayeredIceBottomBoundary::insulated; in.water = {1,1,1,4};
    for (int i = 0; i < 2; ++i) {
        LayeredIceColumnInput c; c.cell_id = i; c.area_m2 = i+1;
        c.top_closure = LayeredIceTopClosure::prescribed_nonwater_top_capacity;
        c.top_nonwater_heat_capacity_j_m2_k = 1;
        c.layers = {{0,i == 0 ? 1. : 0.,i == 0 ? 1. : 0.,1,1}};
        if (i == 0) c.deep_inventory = LayeredIceDeepInventoryInput{1,0,1};
        in.columns.push_back(c);
    }
    LayeredMaterialParcelCertificate p;
    p.movement = {"toy_hot",{0,0},{-1,-1},a::Phase::liquid,1,0};
    p.donor_temperature_k = 18014398509481980.;
    p.specific_enthalpy_j_kg = 18014398509481984.; p.carried_enthalpy_j = 18014398509481984.;
    p.ideal_specific_enthalpy_j_kg = {18014398509481984.,18014398509481984.};
    p.ideal_carried_enthalpy_j = p.ideal_specific_enthalpy_j_kg;
    p.energy_projection_j = {0,0}; p.external_outbox = true;
    s.pending_outboxes = {{"trusted_toy_saved",0,p,0}}; s.consumed_event_ids = {"toy_hot"};
    return s;
}
std::string forcing_json(const LayeredIceOwnerForcing& f) {
    return "{\"id\":"+quoted(f.id)+",\"begin_seconds\":"+numeric(f.begin_seconds)+
        ",\"end_seconds\":"+numeric(f.end_seconds)+",\"absorbed_shortwave_w_m2\":"+
        array(f.absorbed_shortwave_w_m2,numeric)+'}';
}
std::string seed_json(const SeedSpec& s) {
    LayeredIceOwnerReceipt policy; policy.limits = s.limits; policy.maximum_joint_energy_error_j = s.budget_j;
    return "{\"owner_id\":"+quoted(s.owner_id)+",\"input\":"+layered_ice_input_json(s.input)+
        ",\"elapsed_seconds\":"+numeric(s.elapsed_seconds)+",\"joint_energy_error_j\":"+
        numeric(s.joint_energy_error_j)+",\"policy_container\":"+layered_ice_owner_receipt_json(policy)+
        ",\"geographic_cell_ids\":"+array(s.geographic_cell_ids,[](int i){return std::to_string(i);})+
        ",\"pending_outboxes\":"+array(s.pending_outboxes,layered_ice_owned_parcel_json)+
        ",\"consumed_event_ids\":"+array(s.consumed_event_ids,quoted)+
        ",\"forcing_history\":"+array(s.forcing_history,forcing_json)+'}';
}
LayeredIceOwnerRequest liquid_request() {
    LayeredIceOwnerRequest q; q.id = "receive_saved_liquid"; q.end_seconds = 2700;
    q.absorptions = {{"retained_material_900s","drain_0",{1,1}}}; return q;
}
LayeredIceOwnerRequest group_request() {
    LayeredIceOwnerRequest q; q.id = "receive_saved_liquid_and_cold_deep";
    q.expected_revision = 1; q.end_seconds = 2700;
    q.absorptions = {{"retained_material_900s","drain_1",{1,-1}},
        {"material_only_cold_export","cold_export",{1,-1}}}; return q;
}
struct Operation {
    std::string name, owner, candidate_name, expected, component_failure;
    std::optional<LayeredIceOwnerRequest> request;
    bool changed_receiver = false;
    std::uint64_t observed_revision = geographic_revision;
};
std::vector<Operation> operations() {
    std::vector<Operation> v;
    auto prep = [&](const std::string& name, LayeredIceOwnerRequest q, const std::string& expected,
                    const std::string& component = "", bool changed = false,
                    std::uint64_t revision = geographic_revision, const std::string& owner = "science") {
        v.push_back({name,owner,{},expected,component,std::move(q),changed,revision});
    };
    auto commit = [&](const std::string& name, const std::string& candidate, const std::string& expected,
                      bool changed = false, std::uint64_t revision = geographic_revision,
                      const std::string& owner = "science") {
        v.push_back({name,owner,candidate,expected,{},std::nullopt,changed,revision});
    };
    auto q = liquid_request();
    prep("stale_receiver_prepare",q,"stale_geography","",true);
    prep("stale_geographic_revision_prepare",q,"stale_geography","",false,74);
    q.id = "stale_request"; q.expected_revision = 1; prep("stale_request",q,"stale_revision");
    q = liquid_request(); q.id = "duplicate_selection"; q.absorptions.push_back(q.absorptions[0]);
    prep("duplicate_selection",q,"duplicate_absorption");
    q = liquid_request(); q.id = "unknown_event"; q.absorptions[0].event_id = "unknown";
    prep("unknown_event",q,"unknown_absorption");
    q = liquid_request(); q.id = "unknown_source_transaction"; q.absorptions[0].transaction_id = "altered_source";
    prep("unknown_source_transaction",q,"unknown_absorption");
    q = liquid_request(); q.id = "unknown_recipient"; q.absorptions[0].recipient = {2,0};
    prep("unknown_recipient",q,"invalid_absorption_recipient");
    q = liquid_request(); q.id = "selection_cap";
    q.absorptions.insert(q.absorptions.end(),{{"retained_material_900s","drain_1",{1,1}},
        {"material_only_cold_export","cold_export",{1,1}}});
    prep("selection_cap",q,"event_cap");
    q = liquid_request(); q.id = "mixed_material";
    q.movements = {{"forbidden_new_export",{0,1},{-1,-1},a::Phase::solid,.125,0}};
    prep("mixed_material",q,"mixed_absorption");
    q = liquid_request(); q.id = "mixed_remap"; q.remap = LayeredIceOwnerRemap{}; q.remap->id = "forbidden_remap";
    prep("mixed_remap",q,"mixed_absorption");
    q = liquid_request(); q.id = "mixed_thermal";
    q.forcing = LayeredIceOwnerForcing{"forbidden_forcing",2700,2701,{300,450}};
    q.thermal = EnthalpyMeshOptions{1,1e-6,1,128,64,32768,8,true};
    prep("mixed_thermal",q,"mixed_absorption");
    q = liquid_request(); q.id = "nonzero_absorption_clock"; q.end_seconds = 2701;
    prep("nonzero_absorption_clock",q,"clock_refusal");
    prep("liquid_prepare",liquid_request(),"prepared");
    q = liquid_request(); q.id = "sibling_liquid"; q.absorptions[0].recipient = {1,2};
    prep("sibling_prepare",q,"prepared");
    commit("foreign_candidate","liquid_prepare","foreign_candidate",false,73,"foreign");
    commit("stale_receiver_commit","liquid_prepare","stale_geography",true);
    commit("stale_geographic_revision_commit","liquid_prepare","stale_geography",false,74);
    commit("liquid_commit","liquid_prepare","committed");
    commit("liquid_commit_replay","liquid_prepare","replayed");
    commit("stale_sibling_commit","sibling_prepare","stale_candidate");
    prep("liquid_prepare_replay",liquid_request(),"replayed");
    q = liquid_request(); q.absorptions[0].recipient = {1,2};
    prep("committed_target_conflict",q,"transaction_id_conflict");
    q = liquid_request(); q.id = "receive_again_under_new_id"; q.expected_revision = 1;
    prep("consumed_parcel_under_new_id",q,"unknown_absorption");
    prep("group_prepare",group_request(),"prepared");
    commit("group_commit","group_prepare","committed");
    prep("old_prepare_replay_after_group",liquid_request(),"replayed");
    commit("old_commit_replay_after_group","liquid_prepare","replayed");
    q = liquid_request(); q.id = "foreign_cap_prime"; q.absorptions[0].event_id = "unknown";
    prep("foreign_cap_prime",q,"unknown_absorption","",false,73,"foreign");
    q.id = "foreign_work_cap"; prep("foreign_work_cap",q,"work_cap","",false,73,"foreign");
    q = {}; q.id = "toy_empty_active"; q.absorptions = {{"trusted_toy_saved","toy_hot",{1,0}}};
    prep("toy_empty_active",q,"invalid_absorption_recipient","",false,73,"toy");
    q.id = "toy_missing_deep"; q.absorptions[0].recipient = {1,-1};
    prep("toy_missing_deep",q,"invalid_absorption_recipient","",false,73,"toy");
    q.id = "toy_final_deep_floor"; q.absorptions[0].recipient = {0,0};
    prep("toy_final_deep_floor",q,"absorption_refusal","uncertain_physical_domain",false,73,"toy");
    return v;
}
std::string observed(const Operation& op) {
    return seasonal_liquid_routing_input_json(geography(op.changed_receiver),op.observed_revision,{});
}
std::string operation_json(const Operation& op) {
    return "{\"name\":"+quoted(op.name)+",\"kind\":"+quoted(op.request ? "prepare" : "commit")+
        ",\"owner\":"+quoted(op.owner)+",\"candidate_name\":"+quoted(op.candidate_name)+
        ",\"expected\":"+quoted(op.expected)+",\"component_failure\":"+quoted(op.component_failure)+
        ",\"request\":"+(op.request ? layered_ice_owner_request_json(*op.request) : "null")+
        ",\"observed_routing_input\":"+observed(op)+'}';
}
std::vector<std::string> check_names(const std::vector<Operation>& ops) {
    std::vector<std::string> names = {"construct_science","construct_foreign","construct_toy"};
    for (const auto& op : ops) {
        names.push_back(op.name+":outcome");
        if (op.request) names.push_back(op.name+":accepted_unchanged");
    }
    for (const char* name : {"liquid_exact_saved_operands","surviving_outboxes_and_history",
         "grouped_cold_and_liquid_exact_saved_operands","grouped_joint_error_once",
         "final_owned_inventory_and_topology","whole_domain_deep_floor_rollback","fixed_call_counts"})
        names.emplace_back(name);
    return names;
}
bool same_outboxes(const std::vector<LayeredIceOwnedParcel>& x, const std::vector<LayeredIceOwnedParcel>& y) {
    return array(x,layered_ice_owned_parcel_json) == array(y,layered_ice_owned_parcel_json);
}
bool same_work(const LayeredIceOwnerWork& x, const LayeredIceOwnerWork& y) {
    return layered_ice_owner_work_json(x) == layered_ice_owner_work_json(y);
}
bool only_prepare_advanced(LayeredIceOwnerWork before, const LayeredIceOwnerWork& after) {
    ++before.prepare_attempts; return same_work(before,after);
}
bool same_history(const LayeredIceOwnerSnapshot& x, const SeedSpec& s) {
    return x.elapsed_seconds == s.elapsed_seconds && x.consumed_event_ids == s.consumed_event_ids &&
        array(x.forcing_history,forcing_json) == array(s.forcing_history,forcing_json);
}
LayeredIceOwnerWork total_work(const std::map<std::string,std::unique_ptr<LayeredIceOwner>>& owners) {
    LayeredIceOwnerWork total;
    for (const auto& [name,owner] : owners) {
        (void)name; const auto w = owner->work();
#define ADD(field) total.field += w.field
        ADD(prepare_attempts); ADD(graph_builds_started); ADD(absorption_calls_started);
        ADD(material_calls_started); ADD(calorimeter_calls_started); ADD(remap_calls_started);
        ADD(thermal_calls_started); ADD(internal_be_calls_started); ADD(scalar_evaluations);
#undef ADD
        total.observed_counts_complete = total.observed_counts_complete && w.observed_counts_complete;
    }
    return total;
}
} // namespace

int main(int argc, char** argv) {
    const bool inventory = argc == 2 && std::string(argv[1]) == "--inventory";
    const bool run = argc == 2 && std::string(argv[1]) == "--run";
    if (!inventory && !run) return 2;
    std::cout << std::setprecision(17);
    auto foreign = science_seed("foreign"); foreign.limits.max_prepare_attempts = 1;
    const std::vector<SeedSpec> seeds = {science_seed("science"),foreign,toy_seed()};
    const auto ops = operations(); const auto names = check_names(ops);
    std::cout << "{\"kind\":\"inventory\",\"retained_path\":" << quoted(retained_path)
        << ",\"retained_sha256\":" << quoted(retained_sha)
        << ",\"retained_record\":{\"kind\":\"commit\",\"name\":\"remap_a_commit\",\"field\":\"after\"}"
        << ",\"source_evidence_scope\":\"trusted_canonical_retained_2700s_new_owner_lifetime_not_authenticated_restart\""
        << ",\"seed_geography\":" << seasonal_liquid_routing_input_json(geography(),geographic_revision,{})
        << ",\"seeds\":" << array(seeds,seed_json) << ",\"operations\":" << array(ops,operation_json)
        << ",\"check_names\":" << array(names,quoted)
        << ",\"expected_calls\":{\"routing_captures\":1,\"owner_constructors\":3,\"owner_prepares\":24,\"owner_commits\":8,"
           "\"metered_prepares\":23,\"graph_builds\":11,\"absorption\":4,\"material\":0,\"calorimeter\":0,\"remap\":0,"
           "\"thermal\":0,\"internal_be\":0,\"scalar_evaluations\":0,\"world\":0,\"routing_mass\":0,\"historical_thermal_reruns\":0}}\n";
    if (inventory) return 0;
    std::map<std::string,std::unique_ptr<LayeredIceOwner>> owners;
    std::map<std::string,LayeredIceOwnerPreparation> prepared;
    std::map<std::string,std::shared_ptr<const LayeredIceOwnerSnapshot>> committed;
    try {
        ++captures;
        const auto epoch = capture_seasonal_liquid_routing_graph(geography(),geographic_revision);
        std::cout << "{\"kind\":\"routing_capture\",\"input\":"
            << seasonal_liquid_routing_input_json(geography(),geographic_revision,{})
            << ",\"graph\":" << seasonal_liquid_routing_graph_json(epoch) << "}\n";
        for (const auto& s : seeds) {
            LayeredIceOwnerSeed seed{s.owner_id,s.input,s.elapsed_seconds,s.joint_energy_error_j,epoch,
                s.geographic_cell_ids,s.pending_outboxes,s.consumed_event_ids,s.forcing_history};
            ++constructors;
            auto owner = std::make_unique<LayeredIceOwner>(std::move(seed),s.budget_j,s.limits);
            const auto state = owner->snapshot();
            std::cout << "{\"kind\":\"construct\",\"name\":" << quoted(s.owner_id)
                << ",\"seed\":" << seed_json(s) << ",\"geographic_epoch\":" << seasonal_liquid_routing_graph_json(epoch)
                << ",\"snapshot\":" << layered_ice_owner_snapshot_json(*state)
                << ",\"work\":" << layered_ice_owner_work_json(owner->work()) << "}\n";
            check(state->owner_id == s.owner_id && state->revision == 0 &&
                state->joint_energy_error_j == s.joint_energy_error_j && same_history(*state,s) &&
                state->geographic_cell_ids == s.geographic_cell_ids &&
                layered_ice_input_json(state->graph.input()) == layered_ice_input_json(s.input) &&
                same_outboxes(state->pending_outboxes,s.pending_outboxes),"construct_"+s.owner_id);
            owners.emplace(s.owner_id,std::move(owner));
        }
        for (const auto& op : ops) {
            auto& owner = *owners.at(op.owner);
            const auto before = owner.snapshot(); const auto before_json = layered_ice_owner_snapshot_json(*before);
            const auto work_before = owner.work();
            if (op.request) {
                ++prepares;
                auto result = owner.prepare(*op.request,geography(op.changed_receiver),op.observed_revision);
                const auto after_json = layered_ice_owner_snapshot_json(*owner.snapshot());
                const auto work_after = owner.work();
                std::cout << "{\"kind\":\"prepare\",\"name\":" << quoted(op.name) << ",\"owner\":" << quoted(op.owner)
                    << ",\"observed_routing_input\":" << observed(op) << ",\"observed_geographic_revision\":" << op.observed_revision
                    << ",\"request\":" << layered_ice_owner_request_json(*op.request) << ",\"before\":" << before_json
                    << ",\"after\":" << after_json << ",\"receipt\":" << layered_ice_owner_receipt_json(*result.diagnostic)
                    << ",\"candidate_available\":" << (result.candidate ? "true" : "false")
                    << ",\"replayed_committed_transaction\":" << (result.replayed_committed_transaction ? "true" : "false")
                    << ",\"work_before\":" << layered_ice_owner_work_json(work_before)
                    << ",\"work_after\":" << layered_ice_owner_work_json(work_after) << "}\n";
                bool ok = false;
                if (op.expected == "prepared") ok = result.candidate && result.diagnostic->prepared && !result.replayed_committed_transaction;
                else if (op.expected == "replayed") ok = !result.candidate && result.replayed_committed_transaction &&
                    result.diagnostic == prepared.at("liquid_prepare").diagnostic && only_prepare_advanced(work_before,work_after);
                else ok = !result.candidate && !result.replayed_committed_transaction && !result.diagnostic->prepared &&
                    !result.diagnostic->final && result.diagnostic->failure_code == op.expected;
                if (!op.component_failure.empty()) ok = ok && result.diagnostic->absorption &&
                    !result.diagnostic->absorption->accepted && !result.diagnostic->absorption->final &&
                    result.diagnostic->absorption->failure_code == op.component_failure;
                if (op.expected != "replayed") {
                    ok = ok && !result.diagnostic->material && !result.diagnostic->remap &&
                        !result.diagnostic->thermal && !result.diagnostic->thermal_ledger;
                    if (op.expected == "prepared") ok = ok && result.diagnostic->absorption && result.diagnostic->absorption->accepted;
                    else if (op.component_failure.empty()) ok = ok && !result.diagnostic->absorption;
                }
                check(ok,op.name+":outcome"); check(before_json == after_json,op.name+":accepted_unchanged");
                prepared.emplace(op.name,std::move(result));
            } else {
                const auto& candidate = prepared.at(op.candidate_name).candidate;
                LayeredIceOwnerCommit result{false,false,"missing_candidate"};
                if (candidate) { ++commits; result = owner.commit(*candidate,geography(op.changed_receiver),op.observed_revision); }
                const auto after = owner.snapshot(); const auto after_json = layered_ice_owner_snapshot_json(*after);
                std::cout << "{\"kind\":\"commit\",\"name\":" << quoted(op.name) << ",\"owner\":" << quoted(op.owner)
                    << ",\"candidate_name\":" << quoted(op.candidate_name) << ",\"invoked\":" << (candidate ? "true" : "false")
                    << ",\"observed_routing_input\":" << observed(op) << ",\"observed_geographic_revision\":" << op.observed_revision
                    << ",\"before\":" << before_json << ",\"after\":" << after_json << ",\"receipt\":"
                    << (candidate ? layered_ice_owner_receipt_json(candidate->receipt()) : "null")
                    << ",\"accepted\":" << (result.accepted ? "true" : "false") << ",\"replayed\":" << (result.replayed ? "true" : "false")
                    << ",\"failure_code\":" << quoted(result.failure_code)
                    << ",\"work_before\":" << layered_ice_owner_work_json(work_before)
                    << ",\"work_after\":" << layered_ice_owner_work_json(owner.work()) << "}\n";
                bool ok = candidate.has_value() && same_work(work_before,owner.work());
                if (op.expected == "committed") ok = ok && result.accepted && !result.replayed && candidate->receipt().final &&
                    after_json == layered_ice_owner_snapshot_json(*candidate->receipt().final);
                else if (op.expected == "replayed") ok = ok && result.accepted && result.replayed && before_json == after_json;
                else ok = ok && !result.accepted && !result.replayed && result.failure_code == op.expected && before_json == after_json;
                check(ok,op.name+":outcome"); committed.emplace(op.name,after);
            }
        }
        const auto& first = *prepared.at("liquid_prepare").diagnostic;
        const auto liquid = committed.at("liquid_commit");
        const auto& original = seeds[0];
        check(first.absorption && first.absorption->accepted && first.absorption->request && first.absorption->final &&
            same_outboxes(first.absorption->request->pending_outboxes,original.pending_outboxes) &&
            first.absorption->request->inherited_joint_energy_error_j == original.joint_energy_error_j &&
            contains(first.absorption->absorbed_mass_kg,.1) && contains(first.absorption->absorbed_energy_j,33400) &&
            liquid->graph.input().columns[1].layers[1].enthalpy_j_m2 > original.input.columns[1].layers[1].enthalpy_j_m2 &&
            liquid->graph.input().columns[1].layers[1].water_mass_kg_m2 > 100,
            "liquid_exact_saved_operands");
        check(liquid->revision == 1 && same_history(*liquid,original) &&
            same_outboxes(liquid->pending_outboxes,{original.pending_outboxes[1],original.pending_outboxes[2]}),
            "surviving_outboxes_and_history");
        const auto& grouped = *prepared.at("group_prepare").diagnostic;
        const auto final = committed.at("group_commit");
        bool group_ok = grouped.absorption && grouped.absorption->accepted && grouped.absorption->request && grouped.absorption->final;
        if (group_ok) {
            const auto& in = *grouped.absorption->request;
            group_ok = same_outboxes(in.pending_outboxes,liquid->pending_outboxes) && in.selections.size() == 2 &&
                in.pending_outboxes[1].parcel.carried_enthalpy_j == -256.73466254186695 &&
                contains(grouped.absorption->absorbed_mass_kg,.325) &&
                contains(grouped.absorption->absorbed_energy_j,66800-256.73466254186695) &&
                final->graph.input().columns[1].deep_inventory->water_mass_kg_m2 > 99999 &&
                final->graph.input().columns[1].deep_inventory->enthalpy_j_m2 > -2099979000 &&
                grouped.absorption->work.parcels_absorbed == 2 && grouped.absorption->work.nodes_updated == 1;
        }
        check(group_ok,"grouped_cold_and_liquid_exact_saved_operands");
        check(group_ok && grouped.absorption->request->inherited_joint_energy_error_j == liquid->joint_energy_error_j &&
            final->joint_energy_error_j == grouped.absorption->final->final_joint_energy_error_j &&
            final->joint_energy_error_j >= liquid->joint_energy_error_j &&
            final->joint_energy_error_j < 2*original.joint_energy_error_j,
            "grouped_joint_error_once");
        bool topology = final->revision == 2 && final->pending_outboxes.empty() && same_history(*final,original) &&
            final->geographic_cell_ids == original.geographic_cell_ids && final->graph.nodes().size() == 8 &&
            final->graph.deep_inventories().size() == 2;
        auto restored = final->graph.input();
        for (std::size_t i = 0; i < restored.columns.size(); ++i) {
            auto& c = restored.columns[i]; const auto& old = original.input.columns[i];
            for (std::size_t j = 0; j < c.layers.size(); ++j) {
                if (i == 1 && j == 1) { c.layers[j].water_mass_kg_m2 = old.layers[j].water_mass_kg_m2;
                    c.layers[j].enthalpy_j_m2 = old.layers[j].enthalpy_j_m2; }
            }
            if (i == 1) c.deep_inventory = old.deep_inventory;
        }
        topology = topology && layered_ice_input_json(restored) == layered_ice_input_json(original.input);
        check(topology,"final_owned_inventory_and_topology");
        const auto& toy = *prepared.at("toy_final_deep_floor").diagnostic;
        bool crossed = false;
        if (toy.absorption) for (const auto& n : toy.absorption->nodes)
            if (n.address.cell_id == 0 && n.address.layer_id == -1)
                crossed = n.after_H.lower < n.after_floor.upper;
        check(toy.failure_code == "absorption_refusal" && toy.absorption &&
            toy.absorption->failure_code == "uncertain_physical_domain" && !toy.final && !toy.absorption->final &&
            toy.absorption->energy_projection_defect_upper_j > 1 && crossed &&
            owners.at("toy")->snapshot()->joint_energy_error_j == 0 &&
            same_outboxes(owners.at("toy")->snapshot()->pending_outboxes,seeds[2].pending_outboxes),
            "whole_domain_deep_floor_rollback");
        const auto work = total_work(owners);
        check(captures == 1 && constructors == 3 && prepares == 24 && commits == 8 && work.prepare_attempts == 23 &&
            work.graph_builds_started == 11 && work.absorption_calls_started == 4 && work.material_calls_started == 0 &&
            work.calorimeter_calls_started == 0 && work.remap_calls_started == 0 && work.thermal_calls_started == 0 &&
            work.internal_be_calls_started == 0 && work.scalar_evaluations == 0 && work.observed_counts_complete,
            "fixed_call_counts");
        std::cout << "{\"kind\":\"summary\",\"checks\":" << checks << ",\"misses\":" << misses
            << ",\"routing_captures\":" << captures << ",\"owner_constructors\":" << constructors
            << ",\"owner_prepares\":" << prepares << ",\"owner_commits\":" << commits
            << ",\"work\":" << layered_ice_owner_work_json(work)
            << ",\"world_calls\":0,\"routing_mass_calls\":0,\"historical_thermal_reruns\":0}\n";
    } catch (const std::exception& e) {
        std::cout << "{\"kind\":\"fatal\",\"detail\":" << quoted(e.what()) << "}\n"; return 1;
    }
    return misses ? 1 : 0;
}
