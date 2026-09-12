#include "layered_proof_record.hpp"

#include <algorithm>
#include <array>
#include <exception>
#include <limits>
#include <utility>

namespace magic_geo::detail {
namespace {
void need(bool okay, const char* code, const char* detail) {
    if (!okay) throw LayeredProofRecordError(code, detail);
}
std::uint64_t add(std::uint64_t a, std::uint64_t b) {
    need(b <= UINT64_MAX - a, "record_extent", "record extent overflows");
    return a + b;
}
void validate_limits(const LayeredProofRecordLimits& limits) {
    need(limits.maximum_payload_bytes >= layered_proof_record_header_bytes &&
         limits.maximum_metadata_bytes > 0 &&
         limits.maximum_metadata_bytes <= limits.maximum_payload_bytes,
         "record_limits", "complete record and metadata extents must be supplied");
}
template<std::size_t N>
void put(std::array<std::byte, N>& out, std::size_t at, std::uint64_t value, unsigned bytes) {
    for (unsigned i = 0; i < bytes; ++i) out[at + i] = std::byte((value >> (8 * i)) & 255);
}
std::uint64_t get(std::span<const std::byte> in, std::size_t at, unsigned bytes) {
    std::uint64_t value = 0;
    for (unsigned i = 0; i < bytes; ++i)
        value |= std::uint64_t(std::to_integer<unsigned char>(in[at + i])) << (8 * i);
    return value;
}
constexpr std::array<std::byte, 8> magic = {
    std::byte{'L'}, std::byte{'Y'}, std::byte{'R'}, std::byte{'R'},
    std::byte{'E'}, std::byte{'C'}, std::byte{'0'}, std::byte{'1'}};
std::array<std::byte, 64> header(const LayeredProofRecordLayout& layout) {
    std::array<std::byte, 64> out{};
    std::copy(magic.begin(), magic.end(), out.begin());
    put(out, 8, 1, 4); put(out, 12, static_cast<std::uint32_t>(layout.kind), 4);
    put(out, 16, layout.thermal_offset, 8); put(out, 24, layout.thermal_bytes, 8);
    put(out, 32, layout.metadata_offset, 8); put(out, 40, layout.metadata_bytes, 8);
    put(out, 48, layout.payload_bytes, 8); // Last eight bytes are reserved zero.
    return out;
}
void exact_read(LayeredProofReader& reader, std::span<std::byte> destination) {
    while (!destination.empty()) {
        const auto n = reader.read(destination);
        need(n > 0 && n <= destination.size(), "record_truncated", "stored section ended before its extent");
        destination = destination.subspan(n);
    }
}
} // namespace

LayeredProofRecordError::LayeredProofRecordError(std::string c, const char* detail)
    : std::runtime_error(detail), code(std::move(c)) {}

LayeredProofRecordLayout layered_proof_record_layout(LayeredProofRecordKind kind,
    std::uint64_t thermal_bytes, std::uint64_t metadata_bytes, const LayeredProofRecordLimits& limits) {
    validate_limits(limits);
    need(kind == LayeredProofRecordKind::seed || kind == LayeredProofRecordKind::transaction,
         "record_kind", "unknown layered record kind");
    need(kind != LayeredProofRecordKind::seed || thermal_bytes == 0,
         "record_kind", "seed cannot contain a thermal transition");
    need(thermal_bytes == 0 || (thermal_bytes >= enthalpy_mesh_proof_codec_header_bytes &&
         thermal_bytes <= limits.thermal.max_frame_bytes), "record_thermal_extent", "thermal frame extent refused");
    need(metadata_bytes > 0 && metadata_bytes <= limits.maximum_metadata_bytes,
         "record_metadata_extent", "complete metadata extent refused");
    const auto metadata_offset = add(layered_proof_record_header_bytes, thermal_bytes);
    const auto total = add(metadata_offset, metadata_bytes);
    need(total <= limits.maximum_payload_bytes, "record_payload_extent", "complete record exceeds admitted extent");
    return {kind, layered_proof_record_header_bytes, thermal_bytes, metadata_offset, metadata_bytes, total};
}

LayeredProofHandle seal_layered_proof_record(LayeredProofWriter& writer, LayeredProofRecordKind kind,
    const EnthalpyMeshSdirk2Receipt* thermal, std::uint64_t metadata_bytes,
    const LayeredProofMetadataProducer& produce_metadata, const LayeredProofRecordLimits& limits) {
    // Reject use on a nonfresh writer without modifying another record's prefix.
    need(writer.bytes_appended() == 0 && writer.bytes_written() == 0,
         "record_writer", "record writer already contains a prefix");
    try {
        need(static_cast<bool>(produce_metadata), "record_metadata_source", "metadata source is absent");
        const auto thermal_bytes = thermal ? enthalpy_mesh_proof_codec_size(*thermal, limits.thermal).frame_bytes : 0;
        const auto layout = layered_proof_record_layout(kind, thermal_bytes, metadata_bytes, limits);
        writer.append(header(layout));
        if (thermal) encode_enthalpy_mesh_proof(*thermal,
            [&](std::span<const std::byte> bytes) { writer.append(bytes); }, limits.thermal);
        need(writer.bytes_appended() == layout.metadata_offset,
             "record_thermal_extent", "encoded thermal size differs from exact reservation");
        std::uint64_t emitted = 0;
        bool metadata_callback_failed = false;
        produce_metadata([&](std::span<const std::byte> bytes) {
            try {
                need(!metadata_callback_failed, "record_metadata_source", "metadata callback already failed");
                need(bytes.size() <= metadata_bytes - emitted,
                     "record_metadata_extent", "metadata source exceeds declared section");
                emitted += bytes.size();
                while (!bytes.empty()) {
                    const auto n = std::min(bytes.size(), enthalpy_mesh_proof_codec_io_buffer_bytes);
                    writer.append(bytes.first(n)); bytes = bytes.subspan(n);
                }
            } catch (...) {
                metadata_callback_failed = true;
                throw;
            }
        });
        need(!metadata_callback_failed, "record_metadata_source", "metadata producer swallowed a callback failure");
        need(emitted == metadata_bytes && writer.bytes_appended() == layout.payload_bytes,
             "record_metadata_extent", "metadata source did not fill the declared section");
        return writer.seal();
    } catch (...) {
        const auto error = std::current_exception();
        try { writer.abort(3); } catch (...) { /* Store remains authoritative for fencing. */ }
        std::rethrow_exception(error);
    }
}

LayeredProofRecordRead read_layered_proof_record(const LayeredProofHandle& handle,
    const EnthalpyMeshProofSink& metadata_sink, const LayeredProofRecordLimits& limits) {
    validate_limits(limits);
    need(static_cast<bool>(metadata_sink), "record_metadata_sink", "metadata sink is absent");
    need(handle.valid() && handle.payload_bytes() >= layered_proof_record_header_bytes &&
         handle.payload_bytes() <= limits.maximum_payload_bytes,
         "record_payload_extent", "stored record extent refused");
    auto reader = handle.open_reader();
    std::array<std::byte, 64> raw{}; exact_read(reader, raw);
    need(std::equal(magic.begin(), magic.end(), raw.begin()) && get(raw, 8, 4) == 1,
         "record_schema", "unknown layered record schema");
    const auto layout = layered_proof_record_layout(static_cast<LayeredProofRecordKind>(get(raw, 12, 4)),
        get(raw, 24, 8), get(raw, 40, 8), limits);
    need(raw == header(layout) && layout.payload_bytes == handle.payload_bytes(),
         "record_extent", "record offsets, length or reserved header fields differ");
    LayeredProofRecordRead result; result.layout = layout;
    if (layout.thermal_bytes) {
        std::uint64_t consumed = 0;
        result.thermal = decode_enthalpy_mesh_proof([&](std::span<std::byte> destination) {
            need(destination.size() <= layout.thermal_bytes - consumed,
                 "record_thermal_extent", "codec exceeded the isolated thermal section");
            exact_read(reader, destination); consumed += destination.size();
        }, layout.thermal_bytes, limits.thermal);
        need(consumed == layout.thermal_bytes, "record_thermal_extent", "codec left thermal bytes unread");
    }
    std::array<std::byte, enthalpy_mesh_proof_codec_io_buffer_bytes> buffer{};
    std::uint64_t remaining = layout.metadata_bytes;
    while (remaining) {
        const auto n = static_cast<std::size_t>(std::min<std::uint64_t>(remaining, buffer.size()));
        exact_read(reader, std::span<std::byte>(buffer).first(n));
        metadata_sink(std::span<const std::byte>(buffer).first(n)); remaining -= n;
    }
    need(reader.verified(), "record_integrity", "complete store payload was not verified");
    result.integrity_verified = true;
    return result;
}
} // namespace magic_geo::detail
