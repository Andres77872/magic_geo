#pragma once

#include "layered_ice_owner.hpp"
#include <cstddef>
#include <cstdint>
#include <functional>
#include <optional>
#include <span>
#include <stdexcept>
#include <string_view>

namespace magic_geo::detail {

struct LayeredIceOwnerMetadataError : std::runtime_error {
    std::string code;
    LayeredIceOwnerMetadataError(std::string code, const char* detail);
};

// Each independent vector is bounded, including prefixes retained on refusal.
// Nested maxima multiply: columns*layers_per_column and donors*allocations_per_donor
// are deliberately conservative, not silently reduced by physical acceptance.
struct LayeredIceOwnerMetadataShape {
    std::uint64_t max_columns = 0, max_layers_per_column = 0;
    std::uint64_t max_nodes = 0, max_edges = 0, max_deep_inventories = 0;
    std::uint64_t max_geographic_nodes = 0, max_neighbors_per_node = 0;
    std::uint64_t max_movements = 0, max_pending_outboxes = 0, max_consumed_event_ids = 0;
    std::uint64_t max_forcing_records = 0, max_forcing_values_per_record = 0;
    std::uint64_t max_donors = 0, max_allocations_per_donor = 0, max_transfers = 0;
    std::uint64_t max_targets = 0, max_target_layers_per_column = 0;
    std::uint64_t max_domain_coordinates = 0, max_node_certificates = 0;
    std::uint64_t max_export_certificates = 0, max_parcel_certificates = 0;
    std::uint64_t max_absorption_selections = 0;
    std::uint64_t max_identifier_bytes = 96, max_diagnostic_bytes = 4096;
    std::uint64_t max_replay_key_bytes = 0;
};
struct LayeredIceOwnerMetadataLimits {
    LayeredIceOwnerMetadataShape shape;
    // A complete pre-work max-size result must fit this independently admitted
    // extent. An exact post-work check is an integrity guard, not admission.
    std::uint64_t maximum_json_bytes = 0;
};
struct LayeredIceOwnerMetadataHead {
    std::string_view owner_id;
    std::uint64_t snapshot_revision = 0;
    std::uint64_t committed_sequence = 0, committed_attempt = 0;
};
struct LayeredIceOwnerThermalSection {
    // Offset is relative to the containing store payload, not the file.
    std::uint64_t payload_offset = 0, frame_bytes = 0;
    std::uint32_t codec_version = 1;
};
struct LayeredIceOwnerMetadataContext {
    std::uint64_t current_attempt = 0, seed_attempt = 0;
    LayeredIceOwnerMetadataHead initial_head;
    // Present exactly when receipt.thermal is present. Root binds this to the
    // complete separate binary section; no thermal backing field is discarded.
    std::optional<LayeredIceOwnerThermalSection> thermal_section;
};
struct LayeredIceOwnerMetadataSize {
    std::uint64_t json_bytes = 0, visited_vector_elements = 0;
    std::uint64_t visited_string_bytes = 0;
};
using LayeredIceOwnerMetadataSink = std::function<void(std::span<const std::byte>)>;
inline constexpr std::size_t layered_ice_owner_metadata_buffer_bytes = 65536;

// Exact deterministic normalized JSON. All nonthermal legacy fields remain;
// initial/final geographic and forcing prefixes reference the committed head.
// Source strings preserve bytes and doubles preserve binary64/nonfinite bits.
// No old serializer, graph builder, numerical callback or full JSON allocation
// is invoked. Input objects and borrowed graph views must remain immutable.
LayeredIceOwnerMetadataSize layered_ice_owner_metadata_size(
    const LayeredIceOwnerReceipt&, std::string_view replay_key,
    const LayeredIceOwnerMetadataContext&, const LayeredIceOwnerMetadataLimits&);
void stream_layered_ice_owner_metadata(
    const LayeredIceOwnerReceipt&, std::string_view replay_key,
    const LayeredIceOwnerMetadataContext&, const LayeredIceOwnerMetadataSink&,
    const LayeredIceOwnerMetadataLimits&);

// Complete symbolic schema traversal, with all optional objects present and
// every vector/string at its declared independent maximum. No source object,
// generated graph, serializer, model or size-proportional allocation is used.
LayeredIceOwnerMetadataSize layered_ice_owner_metadata_max_size(const LayeredIceOwnerMetadataShape&);

// A new lifetime retains its complete seed once, including full geography and
// forcing values. Later references must resolve through the committed head.
LayeredIceOwnerMetadataSize layered_ice_owner_metadata_seed_size(
    const LayeredIceOwnerSnapshot&, const LayeredIceOwnerMetadataLimits&);
void stream_layered_ice_owner_metadata_seed(const LayeredIceOwnerSnapshot&,
    const LayeredIceOwnerMetadataSink&, const LayeredIceOwnerMetadataLimits&);
LayeredIceOwnerMetadataSize layered_ice_owner_metadata_seed_max_size(const LayeredIceOwnerMetadataShape&);

// Request-only encoding is the exact bounded replay-key representation; it
// has no dependency on max_replay_key_bytes and invokes no physical callback.
LayeredIceOwnerMetadataSize layered_ice_owner_metadata_request_size(
    const LayeredIceOwnerRequest&, const LayeredIceOwnerMetadataLimits&);
void stream_layered_ice_owner_metadata_request(const LayeredIceOwnerRequest&,
    const LayeredIceOwnerMetadataSink&, const LayeredIceOwnerMetadataLimits&);
LayeredIceOwnerMetadataSize layered_ice_owner_metadata_request_max_size(const LayeredIceOwnerMetadataShape&);

} // namespace magic_geo::detail
