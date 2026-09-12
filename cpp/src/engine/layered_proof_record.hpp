#pragma once

#include "enthalpy_mesh_proof_codec.hpp"
#include "layered_proof_store.hpp"

namespace magic_geo::detail {

enum class LayeredProofRecordKind : std::uint32_t { seed = 1, transaction = 2 };
struct LayeredProofRecordLimits {
    std::uint64_t maximum_payload_bytes = 0, maximum_metadata_bytes = 0;
    EnthalpyMeshProofCodecLimits thermal;
};
struct LayeredProofRecordLayout {
    LayeredProofRecordKind kind = LayeredProofRecordKind::transaction;
    std::uint64_t thermal_offset = 64, thermal_bytes = 0;
    std::uint64_t metadata_offset = 64, metadata_bytes = 0, payload_bytes = 64;
};
struct LayeredProofRecordError : std::runtime_error {
    std::string code;
    LayeredProofRecordError(std::string, const char*);
};
using LayeredProofMetadataProducer = std::function<void(const EnthalpyMeshProofSink&)>;
inline constexpr std::uint64_t layered_proof_record_header_bytes = 64;

// These are section/framing operations, not owner admission or physics. The
// caller must reserve complete possible shape, disk and live work before its
// physical prepare. Exact post-work sizes below guard that prior reservation.
LayeredProofRecordLayout layered_proof_record_layout(LayeredProofRecordKind,
    std::uint64_t thermal_frame_bytes, std::uint64_t metadata_bytes,
    const LayeredProofRecordLimits&);

// Writer must be fresh. Writes the exact thermal section first, then streams
// exactly metadata_bytes opaque bytes, then seals once. Metadata may refer to
// thermal offset 64 without any self-referential JSON-length calculation.
// Any failure attempts an explicit abort of the admitted prefix, then rethrows
// the original exception. The caller must inspect store.stats() for fencing or
// commit ambiguity even when a codec callback normalizes an underlying error.
LayeredProofHandle seal_layered_proof_record(LayeredProofWriter&,
    LayeredProofRecordKind, const EnthalpyMeshSdirk2Receipt* thermal,
    std::uint64_t metadata_bytes, const LayeredProofMetadataProducer&,
    const LayeredProofRecordLimits&);

struct LayeredProofRecordRead {
    LayeredProofRecordLayout layout;
    std::optional<EnthalpyMeshSdirk2Receipt> thermal;
    bool integrity_verified = false;
};
// Reads the complete stored payload with an exact-fill adapter for the codec.
// Metadata is opaque here: caller parses/binds its schema, owner and committed
// head separately. Sink callbacks receive unverified prefixes until this call
// succeeds with integrity_verified=true; they must not publish physical state.
// The returned thermal object owns one bounded decoded frame. Its lifetime and
// allocator capacity require a separate owner/read-view admission policy.
LayeredProofRecordRead read_layered_proof_record(const LayeredProofHandle&,
    const EnthalpyMeshProofSink& metadata_sink, const LayeredProofRecordLimits&);

} // namespace magic_geo::detail
