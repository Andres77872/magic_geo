#pragma once

#include "finalized_enthalpy_context.hpp"
#include "layered_ice_owner.hpp"
#include <limits>

namespace magic_geo::detail {

enum class FinalizedLayeredStatePolicy { unspecified, supplied_canonical_layers_v1 };
enum class FinalizedLayeredStateEncoding { unspecified, direct_enthalpy, equilibrium_temperature };
struct FinalizedLayeredStateValue {
    FinalizedLayeredStateEncoding encoding = FinalizedLayeredStateEncoding::unspecified;
    // Exactly the direct H, or exactly both T and liquid mass, must be present.
    // H is whole-node enthalpy relative to Tf, including top Cbase once.
    std::optional<double> enthalpy_j_m2;
    std::optional<double> temperature_k, liquid_water_mass_kg_m2;
};
struct FinalizedLayeredActiveInput {
    int layer_id = -1;
    double water_mass_kg_m2 = std::numeric_limits<double>::quiet_NaN();
    double density_kg_m3 = 0, conductivity_w_m_k = 0;
    FinalizedLayeredStateValue state;
};
struct FinalizedLayeredDeepInput {
    double water_mass_kg_m2 = std::numeric_limits<double>::quiet_NaN();
    double density_kg_m3 = 0;
    FinalizedLayeredStateValue state;
};
struct FinalizedLayeredProfile {
    int geographic_cell_id = -1;
    std::vector<FinalizedLayeredActiveInput> layers;
    std::optional<FinalizedLayeredDeepInput> deep_inventory;
};
struct FinalizedLayeredStateLimits {
    std::size_t max_profiles = 4096, max_layers_per_profile = 32;
    std::size_t max_active_layers = 16384, max_identifier_bytes = 96;
    // Each of observed neighbors, face IDs and vertices is bounded separately.
    std::size_t max_observed_geometry_entries = 131072;
    // Complete retained receipt JSON, not RSS, workspace, or caller copies.
    // Fixed refusal metadata and work counters are exempt if rich data cannot
    // fit. No accepted receipt is truncated; its private owner is discarded.
    std::size_t max_receipt_bytes = 67108864;
};
struct FinalizedLayeredStateRequest {
    FinalizedLayeredStatePolicy policy = FinalizedLayeredStatePolicy::unspecified;
    std::string owner_id, input_id;
    bool complete_horizontal_coverage_declared = false;
    LayeredIceBottomBoundary bottom_boundary = LayeredIceBottomBoundary::unspecified;
    // A new lifetime with no restored transactions, parcels or forcing history.
    // Ein is conditional on supplied canonical W/H accuracy; it does not bound
    // W, density, geometry or an original mass trajectory.
    double elapsed_seconds = 0, inherited_energy_error_j = 0;
    double maximum_joint_energy_error_j = 0;
    // Input order defines local column IDs; geographic IDs form a permutation.
    std::vector<FinalizedLayeredProfile> profiles;
    LayeredIceLimits layered_limits;
    LayeredIceOwnerLimits owner_limits;
    FinalizedLayeredStateLimits limits;
};
struct FinalizedLayeredStateConversion {
    int geographic_cell_id = -1, local_cell_id = -1, layer_id = -1;
    bool deep = false;
    FinalizedLayeredStateValue supplied_state;
    std::string branch;
    double area_m2 = 0, water_mass_kg_m2 = 0, nonwater_heat_capacity_j_m2_k = 0;
    cryosphere_prototype::WaterProperties water{};
    double represented_temperature_offset_k = 0, represented_capacity_j_m2_k = 0;
    double represented_sensible_enthalpy_j_m2 = 0, represented_latent_enthalpy_j_m2 = 0;
    double represented_enthalpy_j_m2 = 0;
    EnthalpyMeshInterval ideal_enthalpy_j_m2{}, enthalpy_projection_difference_j_m2{};
    EnthalpyMeshInterval area_weighted_projection_bound_j{};
};
struct FinalizedLayeredStateWork {
    std::uint64_t owner_constructions_started = 0, owner_constructions_completed = 0;
    // Only available after a constructor returns. A failed constructor can
    // refuse before or after graph construction, so no exact build count is
    // inferred for it from this factory's attempt counter.
    std::optional<LayeredIceOwnerWork> observed_owner_work;
};
struct FinalizedLayeredStateReceipt {
    bool accepted = false, minimal_refusal_metadata = false;
    std::string failure_code, detail;
    FinalizedLayeredStateLimits limits;
    std::optional<FinalizedLayeredStateRequest> request;
    std::optional<FinalizedEnthalpyContext> context;
    std::optional<SeasonalLiquidRoutingGraph> geographic_epoch;
    // Complete matcher operands from the observed source, serialized without
    // copying unrelated Cell descendants. Present after raw-shape admission.
    std::string observed_source_json;
    std::uint64_t observed_geographic_revision = 0;
    bool context_matches = false, routing_matches = false, revisions_match = false;
    std::vector<FinalizedLayeredStateConversion> conversions;
    // Complete proposed canonical graph input, retained before constructor
    // admission so refused initial-domain checks remain independently replayable.
    std::optional<LayeredIceInput> canonical_input;
    EnthalpyMeshInterval conversion_error_sum_j{};
    double conversion_error_upper_j = 0, final_joint_energy_error_j = 0;
    std::shared_ptr<const LayeredIceOwnerSnapshot> final;
    FinalizedLayeredStateWork work;
};
struct FinalizedLayeredStateInitialization {
    FinalizedLayeredStateReceipt receipt;
    std::unique_ptr<LayeredIceOwner> owner;
};

// No capture, geographic mutation or advancement. Both independently captured
// authorities must match the same observed Cells/revision. Initial S=0 is an
// explicit unforced placeholder; a later thermal interval requires forcing.
FinalizedLayeredStateInitialization initialize_finalized_layered_state(
    const FinalizedEnthalpyContext&, const SeasonalLiquidRoutingGraph&,
    const std::vector<Cell>& observed, const Params&, std::uint64_t observed_revision,
    const FinalizedLayeredStateRequest&);

// Nonvalidating serializers support preexecution inventories. Observed-source
// serialization is bounded by initialize() before it is retained there.
std::string finalized_layered_state_observed_json(
    const std::vector<Cell>&, const Params&, std::uint64_t observed_revision);
std::string finalized_layered_state_request_json(const FinalizedLayeredStateRequest&);
std::string finalized_layered_state_receipt_json(const FinalizedLayeredStateReceipt&);

} // namespace magic_geo::detail
