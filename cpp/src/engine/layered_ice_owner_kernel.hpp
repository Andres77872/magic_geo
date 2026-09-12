#pragma once

#include "layered_ice_owner.hpp"

namespace magic_geo::detail::layered_ice_owner_kernel {

// Shared internal physical admission and preparation. Storage/replay/commit
// policy stays with the caller; this kernel never publishes accepted state.
// These helpers preserve the legacy owner's validation order and error codes.
void validate_limits(const LayeredIceOwnerLimits&);
void validate_request_shape(const LayeredIceOwnerRequest&, const LayeredIceOwnerLimits&);

// A trusted canonical seed starts a new lifetime at revision zero. This runs
// the existing single graph build and all physical/mapping/history checks;
// it does not allocate a journal, restore replay records or publish a world.
// Failed construction retains the legacy exception/work-observability scope.
std::shared_ptr<const LayeredIceOwnerSnapshot> initialize_snapshot(
    LayeredIceOwnerSeed, double maximum_joint_energy_error_j,
    const LayeredIceOwnerLimits&);

std::vector<LayeredIceOwnerDomainCoordinate> graph_domain(const LayeredIceGraph&, double joint_energy_error_j);
bool geographic_matches(const LayeredIceOwnerSnapshot&,
    const std::vector<Cell>& observed_geography, std::uint64_t observed_geographic_revision);

// The caller first validates raw request shape, fixes the immutable initial
// snapshot/request/limits/budget in this fresh receipt, meters its prepare,
// checks source/version/replay identity and reserves all required resources.
// The input request and snapshot must remain immutable during the operation.
// This function fills the exact rich physical prefix and returns the same
// receipt; prepared/final are set only after every physical gate succeeds.
// Exceptions propagate with reached components and work still in the caller's
// receipt, including observed_counts_complete=false on component exceptions.
// Catch/classification, diagnostic byte bounds and exceptional incomplete-
// evidence handling remain caller policy. No producer retry occurs here.
LayeredIceOwnerReceipt& prepare_physical(LayeredIceOwnerReceipt&);

} // namespace magic_geo::detail::layered_ice_owner_kernel
