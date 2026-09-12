#pragma once

#include "layered_ice_material.hpp"
#include "layered_ice_absorption.hpp"
#include "layered_ice_remap.hpp"
#include "layered_ice_topology.hpp"
#include "enthalpy_mesh_sdirk2.hpp"
#include "seasonal_liquid_routing.hpp"
#include "layered_ice_forcing_history.hpp"
#include <memory>

namespace magic_geo::detail {

struct LayeredIceOwnerLimits {
    // Defaults remain short-lived; explicit count admission may raise these
    // to 4096 prepares / 2048 commits. This alone cannot admit a full year:
    // complete receipt/history and forcing storage reservations still apply.
    std::size_t max_prepare_attempts = 256, max_commits = 128;
    std::size_t max_concurrent_preparations = 2;
    std::size_t max_events_per_transition = 4096, max_consumed_events = 8192;
    std::size_t max_pending_outboxes = 1024, max_thermal_nodes = 4096;
    std::size_t max_thermal_edges = 32768, max_node_leaves = 131072;
    std::size_t max_receipt_bytes = 67108864, max_history_bytes = 134217728;
    // Normalized retained wire bytes, not vector capacity, temporary encoding
    // storage or process RSS. Private charges follow returned handle lifetime.
    // Fixed refusal metadata (including actual work counters) is exempt when
    // no rich payload can be reserved. No accepted proof is truncated.
    std::size_t max_private_receipt_bytes = 134217728;
    std::size_t max_retained_preparations = 128;
    // Sum of complete geographic forcing vectors in the owned history.
    // Hard limit 2097152. Immutable prefixes share stored values; standalone
    // expanded diagnostic output is separate from normalized journal storage.
    std::size_t max_stored_forcing_values = 524288;
};
struct LayeredIceOwnerSeed {
    // Explicit trusted canonical starting witness for a new owner lifetime.
    // Prior transaction result/replay records are not restored by this seed.
    std::string owner_id;
    LayeredIceInput input;
    double elapsed_seconds = 0, joint_energy_error_j = 0;
    SeasonalLiquidRoutingGraph geographic_epoch;
    std::vector<int> geographic_cell_ids;
    std::vector<LayeredIceOwnedParcel> pending_outboxes;
    std::vector<std::string> consumed_event_ids;
    std::vector<LayeredIceOwnerForcing> forcing_history;
};
struct LayeredIceOwnerRemap {
    std::string id;
    std::vector<LayeredIceRemapTargetColumn> targets;
    std::vector<LayeredIceRemapDonor> donors;
    LayeredIceRemapLimits limits;
};
struct LayeredIceOwnerTopology {
    std::string id;
    std::vector<LayeredIceRemapTargetColumn> targets;
    std::vector<LayeredIceRemapDonor> donors;
    std::vector<LayeredIceWholeInventoryExport> exports;
    LayeredIceTopologyLimits limits;
};
struct LayeredIceOwnerRequest {
    std::string id;
    std::uint64_t expected_revision = 0;
    double end_seconds = 0;
    std::vector<LayeredMaterialMovement> movements;
    std::optional<LayeredIceOwnerRemap> remap;
    // Both are present for a thermal interval, both absent for a zero-time
    // material/remap transaction. Duration must close the exact owned clock.
    std::optional<LayeredIceOwnerForcing> forcing;
    std::optional<EnthalpyMeshOptions> thermal;
    // A separate zero-duration prescribed receiving boundary. Mutually
    // exclusive with movements, remap and thermal forcing. References resolve
    // only to this owner's accepted pending parcels; no caller-supplied J/T.
    std::vector<LayeredIceAbsorptionSelection> absorptions;
    // Separate zero-duration whole-inventory export and layer reconstruction.
    // Uses the accepted source graph and error bound; no intermediate empty
    // pure-water node is admitted. Exclusive with every other operator.
    std::optional<LayeredIceOwnerTopology> topology;
    // Optional prescribed thermal share. It limits the actual outward joint
    // E increase after preceding source operations, not just local SDIRK U.
    // No unused source allowance is borrowed. A horizon scheduler must bind
    // these shares and reserve the entire source/thermal schedule separately.
    std::optional<double> maximum_thermal_error_increment_j;
};
struct LayeredIceOwnerSnapshot {
    std::string owner_id;
    std::uint64_t revision = 0;
    double elapsed_seconds = 0, joint_energy_error_j = 0;
    LayeredIceGraph graph;
    SeasonalLiquidRoutingGraph geographic_epoch;
    std::vector<int> geographic_cell_ids;
    std::vector<LayeredIceOwnedParcel> pending_outboxes;
    std::vector<std::string> consumed_event_ids;
    LayeredIceForcingHistory forcing_history;
};
struct LayeredIceOwnerDomainCoordinate {
    LayeredMaterialAddress address;
    EnthalpyMeshInterval enthalpy_box_j_m2{}, physical_floor_j_m2{};
};
struct LayeredIceOwnerWork {
    std::uint64_t prepare_attempts = 0, graph_builds_started = 0;
    std::uint64_t material_calls_started = 0, calorimeter_calls_started = 0;
    std::uint64_t remap_calls_started = 0, thermal_calls_started = 0;
    std::uint64_t absorption_calls_started = 0;
    std::uint64_t topology_calls_started = 0;
    std::uint64_t internal_be_calls_started = 0, scalar_evaluations = 0;
    bool observed_counts_complete = true;
};
struct LayeredIceOwnerStorage {
    std::size_t committed_history_bytes = 0, reserved_history_bytes = 0;
    std::size_t private_receipt_bytes = 0, retained_preparations = 0;
    std::size_t in_flight_preparations = 0;
};
struct LayeredIceOwnerThermalLedger {
    // Method quadrature uses beta*F1 + a*F2 from the represented tableau.
    // Stage-one and stage-two BE ledgers must not be added together.
    EnthalpyMeshInterval storage_change_j{}, weighted_shortwave_j{}, weighted_emission_j{};
    EnthalpyMeshInterval physical_duration_shortwave_j{}, shortwave_duration_bridge_j{};
    EnthalpyMeshInterval balance_residual_j{}, assembled_defect_j{};
    std::vector<EnthalpyMeshInterval> weighted_edge_transfer_j;
    std::vector<EnthalpyMeshInterval> first_field_conversion_defect_j_m2;
};
struct LayeredIceOwnerThermalErrorCharge {
    double before_global_energy_error_j = 0, local_endpoint_error_upper_j = 0;
    double after_global_energy_error_j = 0;
    EnthalpyMeshInterval charged_increment_j{};
    std::optional<double> maximum_thermal_error_increment_j;
    bool quota_passed = false;
};
struct LayeredIceOwnerReceipt {
    bool prepared = false;
    std::string failure_code, detail;
    LayeredIceOwnerLimits limits;
    double maximum_joint_energy_error_j = 0;
    std::optional<LayeredIceOwnerRequest> request;
    std::shared_ptr<const LayeredIceOwnerSnapshot> initial, final;
    std::optional<LayeredMaterialReceipt> material;
    std::optional<LayeredIceRemapReceipt> remap;
    std::optional<EnthalpyMeshSdirk2Receipt> thermal;
    std::optional<LayeredIceOwnerThermalLedger> thermal_ledger;
    // Present after an accepted thermal result and representable charge
    // formation, even if the quota refuses. Never an extra E charge.
    std::optional<LayeredIceOwnerThermalErrorCharge> thermal_error_charge;
    std::optional<LayeredIceAbsorptionReceipt> absorption;
    std::optional<LayeredIceTopologyReceipt> topology;
    std::vector<LayeredIceOwnerDomainCoordinate> initial_domain, final_domain;
    LayeredIceOwnerWork work;
};
class LayeredIceOwnerCandidate {
    struct Data;
    std::shared_ptr<const Data> data_;
    explicit LayeredIceOwnerCandidate(std::shared_ptr<const Data>);
    friend class LayeredIceOwner;
public:
    const LayeredIceOwnerReceipt& receipt() const;
};
struct LayeredIceOwnerPreparation {
    std::shared_ptr<const LayeredIceOwnerReceipt> diagnostic;
    std::optional<LayeredIceOwnerCandidate> candidate;
    bool replayed_committed_transaction = false;
};
struct LayeredIceOwnerCommit {
    bool accepted = false, replayed = false;
    std::string failure_code;
};
// Owns canonical represented W. Full source/target mass projections remain in
// committed component receipts; this is not an original-mass error bridge.
// Snapshot/prepare/commit are synchronized. Candidate creation does not mutate
// accepted state. Commit replaces state, clock, IDs, receipts and outbox at once.
class LayeredIceOwner {
    struct Impl;
    std::unique_ptr<Impl> impl_;
public:
    LayeredIceOwner(LayeredIceOwnerSeed, double maximum_joint_energy_error_j,
                    LayeredIceOwnerLimits = {});
    ~LayeredIceOwner();
    LayeredIceOwner(const LayeredIceOwner&) = delete;
    LayeredIceOwner& operator=(const LayeredIceOwner&) = delete;
    std::shared_ptr<const LayeredIceOwnerSnapshot> snapshot() const;
    std::vector<std::shared_ptr<const LayeredIceOwnerReceipt>> history() const;
    LayeredIceOwnerWork work() const;
    LayeredIceOwnerStorage storage() const;
    std::string journal_json() const;
    // Caller supplies a synchronized immutable view of the current geography.
    // Both boundaries check its complete captured operands and epoch revision.
    LayeredIceOwnerPreparation prepare(const LayeredIceOwnerRequest&,
        const std::vector<Cell>& observed_geography,std::uint64_t observed_geographic_revision);
    LayeredIceOwnerCommit commit(const LayeredIceOwnerCandidate&,
        const std::vector<Cell>& observed_geography,std::uint64_t observed_geographic_revision);
};

LayeredIceOwnerThermalLedger layered_ice_owner_thermal_ledger(const EnthalpyMeshSdirk2Receipt&);
std::string layered_ice_owner_request_json(const LayeredIceOwnerRequest&);
std::string layered_ice_owner_snapshot_json(const LayeredIceOwnerSnapshot&);
std::string layered_ice_owner_receipt_json(const LayeredIceOwnerReceipt&);
std::string layered_ice_owner_work_json(const LayeredIceOwnerWork&);
std::string layered_ice_owner_record_json(const LayeredIceOwnerReceipt&,const std::string& replay_key);
std::string layered_ice_owner_journal_seed_json(const LayeredIceOwnerSnapshot&);

} // namespace magic_geo::detail
