#pragma once

#include "enthalpy_mesh_sdirk2.hpp"

#include <cstddef>
#include <functional>
#include <span>
#include <stdexcept>

namespace magic_geo::detail {

struct EnthalpyMeshProofCodecError : std::runtime_error {
    std::string code;
    EnthalpyMeshProofCodecError(std::string code, std::string detail);
};
struct EnthalpyMeshProofCodecShape {
    // Independent vector caps, not a claim that lengths are physically valid.
    std::uint32_t max_nodes = 4096, max_edges = 32768;
    std::uint32_t max_sweeps_per_stage = 129;
    std::uint32_t max_backward_euler_leaves_per_stage = 32;
    std::uint32_t max_outer_leaves = 32, max_polynomial_coefficients = 9;
    std::uint32_t max_string_bytes = 4096;
    std::uint32_t max_temperature_branch_bytes = 11;
};
struct EnthalpyMeshProofCodecLimits {
    EnthalpyMeshProofCodecShape shape;
    std::uint64_t max_frame_bytes = 134217728;
    // sizeof(root) + requested vector element storage + string bytes including
    // terminators. This is decoded payload accounting, not vector capacity,
    // allocator overhead, temporary workspaces, arbitrary copies or RSS.
    std::uint64_t max_decoded_payload_bytes = 134217728;
    std::uint64_t max_total_vector_elements = 8388608;
    std::uint64_t max_legacy_json_bytes = 536870912;
};
struct EnthalpyMeshProofCodecSize {
    std::uint64_t frame_bytes = 0, decoded_payload_bytes = 0;
    std::uint64_t total_vector_elements = 0, total_string_bytes = 0;
};
// Each callback must transfer every supplied byte or throw. Spans are valid
// only during the callback. No seeking, retries or numerical callbacks occur.
using EnthalpyMeshProofSink = std::function<void(std::span<const std::byte>)>;
using EnthalpyMeshProofSource = std::function<void(std::span<std::byte>)>;

inline constexpr std::uint32_t enthalpy_mesh_proof_codec_version = 1;
inline constexpr std::uint64_t enthalpy_mesh_proof_codec_header_bytes = 24;
inline constexpr std::size_t enthalpy_mesh_proof_codec_io_buffer_bytes = 65536;

// All receipt fields are traversed, including unavailable backing operands.
// No serializer or physical validation runs. Caller keeps the input immutable
// throughout each operation. Overflow or a selected shape/payload cap refuses.
EnthalpyMeshProofCodecSize enthalpy_mesh_proof_codec_size(
    const EnthalpyMeshSdirk2Receipt&, const EnthalpyMeshProofCodecLimits&);
// Complete worst-case schema bound, with all optional objects present and
// independent vectors at their shape caps. Does not silently restrict itself
// to current aggregate budgets; compare its returned requirements explicitly.
EnthalpyMeshProofCodecSize enthalpy_mesh_proof_codec_max_size(
    const EnthalpyMeshProofCodecShape&);
void encode_enthalpy_mesh_proof(const EnthalpyMeshSdirk2Receipt&,
    const EnthalpyMeshProofSink&, const EnthalpyMeshProofCodecLimits&);
// frame_bytes is the exact isolated frame extent. Unknown header/booleans,
// truncation, trailing bytes and lengths exceeding budgets refuse. Every count
// is checked against remaining wire and decoded budgets before allocation.
EnthalpyMeshSdirk2Receipt decode_enthalpy_mesh_proof(
    const EnthalpyMeshProofSource&, std::uint64_t frame_bytes,
    const EnthalpyMeshProofCodecLimits&);

// Stream exactly the current legacy receipt JSON spelling/availability rules,
// without materializing the full JSON string or calling the old serializers.
// Binary retains hidden values even though their legacy projection is null.
std::uint64_t enthalpy_mesh_proof_legacy_json_size(
    const EnthalpyMeshSdirk2Receipt&, const EnthalpyMeshProofCodecLimits&);
void stream_enthalpy_mesh_proof_legacy_json(const EnthalpyMeshSdirk2Receipt&,
    const EnthalpyMeshProofSink&, const EnthalpyMeshProofCodecLimits&);
// Decodes one bounded structured receipt, then streams its legacy projection.
// It does not claim constant memory independent of the decoded payload.
void expand_enthalpy_mesh_proof_legacy_json(const EnthalpyMeshProofSource&,
    std::uint64_t frame_bytes, const EnthalpyMeshProofSink&,
    const EnthalpyMeshProofCodecLimits&);

} // namespace magic_geo::detail
