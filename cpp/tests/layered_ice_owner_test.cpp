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
constexpr const char* retained_sha = "068e66c8dafae5c0127c4ca5e4b4c600185b19d7bdf26862cdf6ac31c50680db";
constexpr const char* retained_path = "runs/layered-material-evolution-review/evidence/layered-material-successor-qualification/qualification.stdout";
int checks = 0, misses = 0, captures = 0, constructors = 0, prepares = 0, commits = 0;

std::string quoted(const std::string& value) {
    std::ostringstream out; out << std::quoted(value); return out.str();
}
std::string numeric(double value) {
    std::ostringstream out; out << std::setprecision(17) << value; return out.str();
}
template<class T, class F> std::string array(const std::vector<T>& values, F encode) {
    std::string out = "[";
    for (const auto& value : values) { if (out.size() > 1) out += ','; out += encode(value); }
    return out + ']';
}
void check(bool ok, const std::string& name) {
    ++checks; if (!ok) ++misses;
    std::cout << "{\"kind\":\"check\",\"name\":" << quoted(name)
              << ",\"passed\":" << (ok ? "true" : "false") << "}\n";
}

// Plain input-only description: inventory never constructs a geographic or
// thermal graph, an owner, or a candidate.
struct SeedSpec {
    std::string owner_id;
    LayeredIceInput input;
    double elapsed_seconds = 0, joint_energy_error_j = 0, budget_j = 0;
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
    x.max_prepare_attempts = 32; x.max_commits = 8; x.max_concurrent_preparations = 2;
    x.max_events_per_transition = 4; x.max_consumed_events = 16; x.max_pending_outboxes = 3;
    x.max_thermal_nodes = 8; x.max_thermal_edges = 7; x.max_node_leaves = 64;
    x.max_receipt_bytes = 4194304; x.max_history_bytes = 33554432;
    return x;
}

SeedSpec science_seed(std::string owner_id) {
    SeedSpec seed; seed.owner_id = std::move(owner_id);
    seed.elapsed_seconds = 1800; seed.joint_energy_error_j = 40.19708134661563;
    seed.budget_j = 3340; seed.geographic_cell_ids = {0,1};
    auto& input = seed.input;
    input.id = "retained_900_second_layered_endpoint"; // Retained component input identity.
    input.complete_horizontal_coverage_declared = true;
    input.bottom_boundary = LayeredIceBottomBoundary::insulated;
    input.water = {273.15,2100,4186,334000};
    const std::array<double,8> H = {139003.15943006135,-207535.01130570527,
        -213323.87891207094,-4193454.7172865495,409003.15943006135,
        -207535.01130570527,-213323.87891207094,-4193454.7172865495};
    for (int i = 0; i < 2; ++i) {
        LayeredIceColumnInput c; c.cell_id = i; c.area_m2 = i+1;
        c.top_closure = LayeredIceTopClosure::coarse_combined_surface_atmosphere;
        c.top_nonwater_heat_capacity_j_m2_k = 1e7; c.top_longwave_emissivity = .6;
        c.top_absorbed_shortwave_w_m2 = i == 0 ? 300 : 450;
        c.layers = {{0,50.9,H[4*i],300,.3},{1,100,H[4*i+1],917,2.29},
            {2,100,H[4*i+2],917,2.29},{3,1000,H[4*i+3],917,2.29}};
        c.deep_inventory = LayeredIceDeepInventoryInput{99999,-2099979000,917};
        input.columns.push_back(c);
        LayeredMaterialParcelCertificate p;
        p.movement = {"drain_"+std::to_string(i),{i,0},{-1,-1},a::Phase::liquid,i == 0 ? .1 : .2,0};
        p.donor_temperature_k = 273.15; p.specific_enthalpy_j_kg = 334000;
        p.carried_enthalpy_j = i == 0 ? 33400 : 66800;
        p.ideal_specific_enthalpy_j_kg = {334000,334000};
        p.ideal_carried_enthalpy_j = i == 0
            ? EnthalpyMeshInterval{33399.99999999999,33400.00000000001}
            : EnthalpyMeshInterval{66799.99999999999,66800.00000000001};
        p.energy_projection_j = i == 0
            ? EnthalpyMeshInterval{-7.275957614183428e-12,7.275957614183428e-12}
            : EnthalpyMeshInterval{-1.4551915228366855e-11,1.4551915228366855e-11};
        p.external_outbox = true;
        seed.pending_outboxes.push_back({"retained_material_900s",0,p,i});
    }
    input.horizontal_climate_edges = {{0,1,.1}};
    seed.consumed_event_ids = {"drain_0","drain_1","refill_0","refill_1"};
    // These are declared canonical seed-history labels, not prior owner IDs.
    seed.forcing_history = {{"retained_0_900_forcing",0,900,{300,450}},
        {"retained_900_1800_forcing",900,1800,{300,450}}};
    return seed;
}

SeedSpec permuted_deep_seed() {
    SeedSpec seed; seed.owner_id = "permuted_deep";
    seed.joint_energy_error_j = 1; seed.budget_j = 4;
    seed.geographic_cell_ids = {1,0};
    auto& input = seed.input; input.id = "dyadic_final_deep_floor_control";
    input.complete_horizontal_coverage_declared = true;
    input.bottom_boundary = LayeredIceBottomBoundary::insulated;
    input.water = {1,1,1,4};
    for (int i = 0; i < 2; ++i) {
        LayeredIceColumnInput c; c.cell_id = i; c.area_m2 = i == 0 ? 2 : 1;
        c.top_closure = LayeredIceTopClosure::prescribed_nonwater_top_capacity;
        c.top_nonwater_heat_capacity_j_m2_k = 1; c.top_longwave_emissivity = 1;
        c.top_absorbed_shortwave_w_m2 = i == 0 ? 2 : 1;
        c.layers = {{0,1,-.5,1,1}};
        if (i == 1) c.deep_inventory = LayeredIceDeepInventoryInput{1,0,1};
        input.columns.push_back(c);
    }
    return seed;
}

std::string parcel_json(const LayeredMaterialParcelCertificate& p) {
    // The complete component serializer is used without invoking its producer.
    LayeredMaterialReceipt receipt; receipt.parcels.push_back(p);
    return layered_material_receipt_json(receipt);
}
std::string seeded_outbox_json(const LayeredIceOwnedParcel& p) {
    return "{\"transaction_id\":"+quoted(p.transaction_id)+",\"source_revision\":"+
        std::to_string(p.source_revision)+",\"geographic_cell_id\":"+std::to_string(p.geographic_cell_id)+
        ",\"certificate_container\":"+parcel_json(p.parcel)+'}';
}
std::string forcing_json(const LayeredIceOwnerForcing& f) {
    return "{\"id\":"+quoted(f.id)+",\"begin_seconds\":"+numeric(f.begin_seconds)+
        ",\"end_seconds\":"+numeric(f.end_seconds)+",\"absorbed_shortwave_w_m2\":"+
        array(f.absorbed_shortwave_w_m2,numeric)+'}';
}
std::string seed_json(const SeedSpec& seed) {
    LayeredIceOwnerReceipt policy; policy.limits = limits(); policy.maximum_joint_energy_error_j = seed.budget_j;
    return "{\"owner_id\":"+quoted(seed.owner_id)+",\"input\":"+layered_ice_input_json(seed.input)+
        ",\"elapsed_seconds\":"+numeric(seed.elapsed_seconds)+",\"joint_energy_error_j\":"+
        numeric(seed.joint_energy_error_j)+",\"policy_container\":"+layered_ice_owner_receipt_json(policy)+
        ",\"geographic_cell_ids\":"+array(seed.geographic_cell_ids,[](int x){return std::to_string(x);})+
        ",\"pending_outboxes\":"+array(seed.pending_outboxes,seeded_outbox_json)+
        ",\"consumed_event_ids\":"+array(seed.consumed_event_ids,quoted)+
        ",\"forcing_history\":"+array(seed.forcing_history,forcing_json)+'}';
}

LayeredIceOwnerRemap identity_remap(std::string id) {
    LayeredIceOwnerRemap r; r.id = std::move(id);
    r.limits = {2,8,10,10,128};
    for (int i = 0; i < 2; ++i) {
        r.targets.push_back({i,{{0,300,.3},{1,917,2.29},{2,917,2.29},{3,917,2.29}},917});
        for (int layer = 0; layer < 4; ++layer)
            r.donors.push_back({i,{false,layer},{{{false,layer},1}}});
        r.donors.push_back({i,{true,-1},{{{true,-1},1}}});
    }
    return r;
}
LayeredIceOwnerRequest thermal_request() {
    LayeredIceOwnerRequest q; q.id = "scientific_1800_2700"; q.end_seconds = 2700;
    q.forcing = LayeredIceOwnerForcing{"forcing_1800_2700",1800,2700,{300,450}};
    q.thermal = EnthalpyMeshOptions{900,.001,3340,128,64,32768,8,true};
    return q;
}
LayeredIceOwnerRequest cold_request(std::string id, std::uint64_t revision, double end,
                                    std::string event) {
    LayeredIceOwnerRequest q; q.id = std::move(id); q.expected_revision = revision; q.end_seconds = end;
    q.movements = {{std::move(event),{0,1},{-1,-1},a::Phase::solid,.125,0}};
    return q;
}
struct Operation {
    std::string name, owner, candidate_name, expected;
    std::optional<LayeredIceOwnerRequest> request;
    bool changed_receiver = false;
    std::uint64_t observed_revision = geographic_revision;
};
std::vector<Operation> operations() {
    std::vector<Operation> v;
    auto prep = [&](const std::string& name, LayeredIceOwnerRequest q, const std::string& expected,
                    bool changed = false, std::uint64_t revision = geographic_revision,
                    const std::string& owner = "science") {
        v.push_back({name,owner,{},expected,std::move(q),changed,revision});
    };
    auto commit = [&](const std::string& name, const std::string& candidate, const std::string& expected,
                      bool changed = false, std::uint64_t revision = geographic_revision,
                      const std::string& owner = "science") {
        v.push_back({name,owner,candidate,expected,std::nullopt,changed,revision});
    };
    auto q = thermal_request();
    prep("stale_receiver_prepare",q,"stale_geography",true);
    prep("stale_geographic_revision_prepare",q,"stale_geography",false,74);
    q.id = "stale_request_initial"; q.expected_revision = 1;
    prep("stale_request_initial",q,"stale_revision");
    q = cold_request("duplicate_consumed_event",0,1800,"drain_0");
    prep("duplicate_consumed_event",q,"duplicate_event");
    q = cold_request("cold_liquid_refusal",0,1800,"cold_liquid"); q.movements[0].phase = a::Phase::liquid;
    prep("material_refusal",q,"material_refusal");
    q = cold_request("private_material_then_bad_remap",0,1800,"prefix_export");
    q.remap = identity_remap("incomplete_private_remap"); q.remap->donors.pop_back();
    prep("material_prefix_remap_refusal",q,"remap_refusal");
    prep("scientific_prepare",thermal_request(),"prepared");
    commit("foreign_candidate","scientific_prepare","foreign_candidate",false,73,"foreign");
    commit("changed_receiver_commit","scientific_prepare","stale_geography",true);
    commit("changed_revision_commit","scientific_prepare","stale_geography",false,74);
    commit("scientific_commit","scientific_prepare","committed");
    commit("scientific_commit_replay","scientific_prepare","replayed");
    prep("scientific_prepare_replay",thermal_request(),"replayed");
    q = thermal_request(); q.end_seconds = 2701;
    prep("conflicting_transaction_clock",q,"transaction_id_conflict");
    q = thermal_request(); ++q.thermal->maximum_scalar_evaluations;
    prep("conflicting_transaction_option",q,"transaction_id_conflict");
    q = cold_request("stale_after_commit",0,2700,"stale_cold_export");
    prep("stale_after_commit",q,"stale_revision");
    q = cold_request("material_only_cold_export",1,2700,"cold_export");
    prep("cold_export_prepare",q,"prepared");
    commit("cold_export_commit","cold_export_prepare","committed");
    prep("scientific_replay_after_later_commit",thermal_request(),"replayed");
    q = {}; q.id = "identity_remap_a"; q.expected_revision = 2; q.end_seconds = 2700;
    q.remap = identity_remap("identity_plan_a"); prep("remap_a_prepare",q,"prepared");
    q.id = "identity_remap_b"; q.remap->id = "identity_plan_b";
    prep("remap_b_prepare",q,"prepared");
    commit("remap_a_commit","remap_a_prepare","committed");
    commit("stale_remap_b_commit","remap_b_prepare","stale_candidate");
    commit("old_candidate_replay_after_later_commit","scientific_prepare","replayed");
    q = cold_request("outbox_cap_request",3,2700,"one_too_many_outboxes");
    prep("outbox_cap_refusal",q,"outbox_cap");
    q = thermal_request(); q.id = "conflicting_forcing_window"; q.expected_revision = 3;
    q.end_seconds = 3600; q.forcing->begin_seconds = 2700; q.forcing->end_seconds = 3600;
    prep("forcing_identity_refusal",q,"forcing_identity_refusal");
    q = {}; q.id = "permuted_final_deep_floor"; q.end_seconds = 1;
    q.forcing = LayeredIceOwnerForcing{"toy_geographic_forcing",0,1,{1,2}};
    q.thermal = EnthalpyMeshOptions{1,1e-6,1,128,64,32768,8,true};
    prep("permuted_final_deep_floor",q,"uncertain_physical_domain",false,73,"permuted_deep");
    return v;
}
std::string operation_json(const Operation& op) {
    return "{\"name\":"+quoted(op.name)+",\"kind\":"+quoted(op.request ? "prepare" : "commit")+
        ",\"owner\":"+quoted(op.owner)+",\"candidate_name\":"+quoted(op.candidate_name)+
        ",\"expected\":"+quoted(op.expected)+",\"request\":"+
        (op.request ? layered_ice_owner_request_json(*op.request) : "null")+
        ",\"observed_routing_input\":"+seasonal_liquid_routing_input_json(geography(op.changed_receiver),op.observed_revision,{})+'}';
}
std::vector<std::string> check_names(const std::vector<Operation>& ops) {
    std::vector<std::string> names = {"construct_science","construct_foreign","construct_permuted_deep"};
    for (const auto& op : ops) {
        names.push_back(op.name+":outcome");
        if (op.request) names.push_back(op.name+":accepted_unchanged");
    }
    for (const char* name : {"science_endpoint_preserves_deep_and_outboxes","science_actual_thermal_request_bound",
         "cold_export_retains_prior_outboxes_and_ids","identity_remap_preserves_state",
         "permuted_forcing_and_final_deep_floor","fixed_call_counts"}) names.emplace_back(name);
    return names;
}
std::string observed(const Operation& op) {
    return seasonal_liquid_routing_input_json(geography(op.changed_receiver),op.observed_revision,{});
}
bool same_outboxes(const std::vector<LayeredIceOwnedParcel>& a, const std::vector<LayeredIceOwnedParcel>& b) {
    return array(a,seeded_outbox_json) == array(b,seeded_outbox_json);
}
bool same_work(const LayeredIceOwnerWork& a, const LayeredIceOwnerWork& b) {
    return layered_ice_owner_work_json(a) == layered_ice_owner_work_json(b);
}
bool only_prepare_meter_advanced(LayeredIceOwnerWork before, const LayeredIceOwnerWork& after) {
    ++before.prepare_attempts;
    return same_work(before,after);
}
LayeredIceOwnerWork total_work(const std::map<std::string,std::unique_ptr<LayeredIceOwner>>& owners) {
    LayeredIceOwnerWork total;
    for (const auto& [name,owner] : owners) {
        (void)name; const auto w = owner->work();
#define ADD(field) total.field += w.field
        ADD(prepare_attempts); ADD(graph_builds_started); ADD(material_calls_started); ADD(calorimeter_calls_started);
        ADD(remap_calls_started); ADD(thermal_calls_started); ADD(internal_be_calls_started); ADD(scalar_evaluations);
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
    const std::vector<SeedSpec> seeds = {science_seed("science"),science_seed("foreign"),permuted_deep_seed()};
    const auto ops = operations(); const auto names = check_names(ops);
    std::cout << "{\"kind\":\"inventory\",\"retained_path\":" << quoted(retained_path)
        << ",\"retained_sha256\":" << quoted(retained_sha)
        << ",\"source_evidence_scope\":\"trusted_canonical_retained_endpoint_not_authenticated_restart\""
        << ",\"seed_geography\":" << seasonal_liquid_routing_input_json(geography(),geographic_revision,{})
        << ",\"seeds\":" << array(seeds,seed_json) << ",\"operations\":" << array(ops,operation_json)
        << ",\"check_names\":" << array(names,quoted)
        << ",\"expected_calls\":{\"routing_captures\":1,\"owner_constructors\":3,\"owner_prepares\":18,\"owner_commits\":9,"
           "\"metered_prepares\":18,\"graph_builds\":17,\"material\":3,\"calorimeter\":2,\"remap\":3,\"thermal\":2,"
           "\"internal_be\":4,\"scalar_evaluation_ceiling\":65536,\"world\":0,\"routing_mass\":0,\"historical_thermal_reruns\":0}}\n";
    if (inventory) return 0;
    std::map<std::string,std::unique_ptr<LayeredIceOwner>> owners;
    std::map<std::string,LayeredIceOwnerPreparation> prepared;
    std::map<std::string,std::shared_ptr<const LayeredIceOwnerSnapshot>> committed;
    try {
        ++captures;
        const auto epoch = capture_seasonal_liquid_routing_graph(geography(),geographic_revision);
        std::cout << "{\"kind\":\"routing_capture\",\"input\":" << seasonal_liquid_routing_input_json(geography(),geographic_revision,{})
            << ",\"graph\":" << seasonal_liquid_routing_graph_json(epoch) << "}\n";
        for (const auto& s : seeds) {
            LayeredIceOwnerSeed seed{s.owner_id,s.input,s.elapsed_seconds,s.joint_energy_error_j,epoch,
                s.geographic_cell_ids,s.pending_outboxes,s.consumed_event_ids,s.forcing_history};
            ++constructors;
            auto owner = std::make_unique<LayeredIceOwner>(std::move(seed),s.budget_j,limits());
            const auto state = owner->snapshot();
            std::cout << "{\"kind\":\"construct\",\"name\":" << quoted(s.owner_id) << ",\"seed\":" << seed_json(s)
                << ",\"geographic_epoch\":" << seasonal_liquid_routing_graph_json(epoch)
                << ",\"snapshot\":" << layered_ice_owner_snapshot_json(*state)
                << ",\"work\":" << layered_ice_owner_work_json(owner->work()) << "}\n";
            check(state->owner_id == s.owner_id && state->revision == 0 && state->elapsed_seconds == s.elapsed_seconds &&
                state->joint_energy_error_j == s.joint_energy_error_j && state->geographic_cell_ids == s.geographic_cell_ids &&
                layered_ice_input_json(state->graph.input()) == layered_ice_input_json(s.input) &&
                same_outboxes(state->pending_outboxes,s.pending_outboxes) && state->consumed_event_ids == s.consumed_event_ids,
                "construct_"+s.owner_id);
            owners.emplace(s.owner_id,std::move(owner));
        }
        for (const auto& op : ops) {
            auto& owner = *owners.at(op.owner);
            const auto before = owner.snapshot(); const auto before_json = layered_ice_owner_snapshot_json(*before);
            const auto work_before = owner.work();
            if (op.request) {
                ++prepares;
                auto result = owner.prepare(*op.request,geography(op.changed_receiver),op.observed_revision);
                const auto after = owner.snapshot(); const auto after_json = layered_ice_owner_snapshot_json(*after);
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
                    result.diagnostic == prepared.at("scientific_prepare").diagnostic && only_prepare_meter_advanced(work_before,work_after);
                else ok = !result.candidate && !result.replayed_committed_transaction && !result.diagnostic->prepared &&
                    !result.diagnostic->final && result.diagnostic->failure_code == op.expected;
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
                    << ",\"accepted\":" << (result.accepted ? "true" : "false")
                    << ",\"replayed\":" << (result.replayed ? "true" : "false") << ",\"failure_code\":" << quoted(result.failure_code)
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
        const auto science = committed.at("scientific_commit");
        bool preserved = science->revision == 1 && science->elapsed_seconds == 2700 && science->joint_energy_error_j >= seeds[0].joint_energy_error_j &&
            science->joint_energy_error_j <= seeds[0].budget_j && same_outboxes(science->pending_outboxes,seeds[0].pending_outboxes) &&
            science->consumed_event_ids == seeds[0].consumed_event_ids && science->forcing_history.size() == 3;
        for (int i = 0; i < 2; ++i) {
            const auto& c = science->graph.input().columns[i]; const auto& old = seeds[0].input.columns[i];
            preserved = preserved && c.deep_inventory && c.deep_inventory->water_mass_kg_m2 == 99999 &&
                c.deep_inventory->enthalpy_j_m2 == -2099979000;
            for (int j = 0; j < 4; ++j) preserved = preserved && c.layers[j].water_mass_kg_m2 == old.layers[j].water_mass_kg_m2;
        }
        check(preserved,"science_endpoint_preserves_deep_and_outboxes");
        const auto& scientific = *prepared.at("scientific_prepare").diagnostic;
        bool bound = scientific.thermal && scientific.thermal->accepted && scientific.thermal->request;
        if (bound) {
            const auto& q = *scientific.thermal->request;
            bound = q.columns.size() == 8 && q.edges.size() == 7 && q.initial_enthalpy_j_m2.size() == 8 &&
                q.water_mass_kg_m2.size() == 8 && q.absorbed_shortwave_w_m2 == std::vector<double>{300,0,0,0,450,0,0,0};
            if (bound) for (int i = 0; i < 8; ++i) {
                const auto& old = seeds[0].input.columns[i/4].layers[i%4];
                bound = bound && q.initial_enthalpy_j_m2[i] == old.enthalpy_j_m2 && q.water_mass_kg_m2[i] == old.water_mass_kg_m2;
            }
        }
        check(bound,"science_actual_thermal_request_bound");
        const auto cold = committed.at("cold_export_commit");
        bool old_boxes = cold->pending_outboxes.size() == 3;
        if (old_boxes) old_boxes = same_outboxes({cold->pending_outboxes[0],cold->pending_outboxes[1]},seeds[0].pending_outboxes) &&
            cold->pending_outboxes[2].parcel.carried_enthalpy_j < 0 && cold->pending_outboxes[2].geographic_cell_id == 0;
        check(old_boxes && cold->elapsed_seconds == 2700 && cold->revision == 2 && cold->consumed_event_ids.size() == 5 &&
            std::find(cold->consumed_event_ids.begin(),cold->consumed_event_ids.end(),"cold_export") != cold->consumed_event_ids.end(),
            "cold_export_retains_prior_outboxes_and_ids");
        const auto remapped = committed.at("remap_a_commit");
        check(remapped->revision == 3 && remapped->elapsed_seconds == cold->elapsed_seconds &&
            remapped->joint_energy_error_j == cold->joint_energy_error_j &&
            layered_ice_graph_json(remapped->graph) == layered_ice_graph_json(cold->graph) &&
            same_outboxes(remapped->pending_outboxes,cold->pending_outboxes),"identity_remap_preserves_state");
        const auto& toy = *prepared.at("permuted_final_deep_floor").diagnostic;
        check(toy.failure_code == "uncertain_physical_domain" && !toy.final && toy.thermal && toy.thermal->accepted &&
            toy.thermal->request && toy.thermal->request->absorbed_shortwave_w_m2 == std::vector<double>{2,1} &&
            toy.thermal->local_endpoint_error_upper_j > 0 && owners.at("permuted_deep")->snapshot()->joint_energy_error_j == 1,
            "permuted_forcing_and_final_deep_floor");
        const auto work = total_work(owners);
        check(captures == 1 && constructors == 3 && prepares == 18 && commits == 9 && work.prepare_attempts == 18 &&
            work.graph_builds_started == 17 && work.material_calls_started == 3 && work.calorimeter_calls_started == 2 &&
            work.remap_calls_started == 3 && work.thermal_calls_started == 2 && work.internal_be_calls_started == 4 &&
            work.scalar_evaluations <= 65536 && work.observed_counts_complete,"fixed_call_counts");
        std::cout << "{\"kind\":\"summary\",\"checks\":" << checks << ",\"misses\":" << misses
            << ",\"routing_captures\":" << captures << ",\"owner_constructors\":" << constructors
            << ",\"owner_prepares\":" << prepares << ",\"owner_commits\":" << commits
            << ",\"work\":" << layered_ice_owner_work_json(work)
            << ",\"world_calls\":0,\"routing_mass_calls\":0,\"historical_thermal_reruns\":0}\n";
    } catch (const std::exception& e) {
        std::cout << "{\"kind\":\"fatal\",\"detail\":" << quoted(e.what()) << "}\n";
        return 1;
    }
    return misses ? 1 : 0;
}
