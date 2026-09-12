#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>

namespace magic_geo::detail {

struct LayeredProofStorePolicy {
    // All resource limits are explicit. No default disk or memory admission.
    std::uint64_t provisioned_bytes = 0, maximum_attempts = 0;
    std::uint64_t maximum_payload_bytes = 0, maximum_io_operations = 0;
    std::size_t maximum_writers = 0, maximum_readers = 0, io_buffer_bytes = 0;
};
struct LayeredProofStoreIdentity {
    std::array<std::byte, 32> store{}, source{};
    std::uint64_t initial_revision = 0;
};
enum class LayeredProofIoKind { header, begin, payload, seal, abort, commit, read, flush, directory_flush };
struct LayeredProofIoOperation {
    LayeredProofIoKind kind;
    std::uint64_t offset = 0, requested_bytes = 0, operation_number = 0;
};
struct LayeredProofIoDirective {
    // A hook can reduce a real system call or inject an errno. It cannot
    // provide alternate bytes, successful writes, or successful flushes.
    std::uint64_t maximum_bytes = UINT64_MAX;
    int error_number = 0;
};
using LayeredProofIoHook = std::function<LayeredProofIoDirective(const LayeredProofIoOperation&)>;
struct LayeredProofStoreStats {
    std::uint64_t provisioned_bytes = 0, required_bytes = 0, reserved_payload_bytes = 0;
    std::uint64_t attempts_started = 0, sealed_attempts = 0, aborted_attempts = 0;
    std::uint64_t indeterminate_attempts = 0, committed_records = 0;
    std::uint64_t payload_bytes_written = 0, total_bytes_written = 0, total_bytes_read = 0;
    std::uint64_t payload_bytes_appended = 0;
    std::uint64_t io_operations = 0, commit_sequence = 0, committed_revision = 0;
    std::size_t active_writers = 0, active_readers = 0;
    std::size_t io_buffer_bytes_live = 0, io_buffer_bytes_peak = 0, index_payload_bytes = 0;
    bool fenced = false, commit_indeterminate = false;
    bool directory_sync_completed = false, known_volatile_filesystem = false;
    std::uint64_t filesystem_type = 0;
};
struct LayeredProofStoreError : std::runtime_error {
    std::string code;
    bool fenced, commit_indeterminate;
    LayeredProofStoreError(std::string, const char*, bool = false, bool = false);
};
struct LayeredProofStoreState;
class LayeredProofWriter;
class LayeredProofReader;
class LayeredProofStore;

class LayeredProofHandle {
    std::shared_ptr<LayeredProofStoreState> state_;
    std::uint64_t attempt_ = 0, size_ = 0, checksum_ = 0;
    LayeredProofHandle(std::shared_ptr<LayeredProofStoreState>, std::uint64_t,
                       std::uint64_t, std::uint64_t);
    friend class LayeredProofWriter;
    friend class LayeredProofStore;
public:
    LayeredProofHandle() = default;
    bool valid() const noexcept { return static_cast<bool>(state_); }
    std::uint64_t attempt() const noexcept { return attempt_; }
    std::uint64_t payload_bytes() const noexcept { return size_; }
    std::uint64_t checksum_crc64_ecma182() const noexcept { return checksum_; }
    LayeredProofReader open_reader() const; // Works after the store wrapper is destroyed.
};

class LayeredProofWriter {
    struct Impl;
    std::unique_ptr<Impl> impl_;
    explicit LayeredProofWriter(std::unique_ptr<Impl>);
    friend class LayeredProofStore;
public:
    ~LayeredProofWriter();
    LayeredProofWriter(LayeredProofWriter&&) noexcept;
    LayeredProofWriter& operator=(LayeredProofWriter&&) noexcept;
    LayeredProofWriter(const LayeredProofWriter&) = delete;
    LayeredProofWriter& operator=(const LayeredProofWriter&) = delete;
    void append(std::span<const std::byte>);
    LayeredProofHandle seal(); // Flushes proof only; never commits physical state.
    void abort(std::uint32_t reason = 0); // Retains prefix and explicit abort footer.
    std::uint64_t bytes_written() const noexcept;
    std::uint64_t bytes_appended() const noexcept;
};
class LayeredProofReader {
    struct Impl;
    std::unique_ptr<Impl> impl_;
    explicit LayeredProofReader(std::unique_ptr<Impl>);
    friend class LayeredProofStore;
public:
    ~LayeredProofReader();
    LayeredProofReader(LayeredProofReader&&) noexcept;
    LayeredProofReader& operator=(LayeredProofReader&&) noexcept;
    LayeredProofReader(const LayeredProofReader&) = delete;
    LayeredProofReader& operator=(const LayeredProofReader&) = delete;
    // Returns at most one admitted buffer. Full-payload CRC is verified only
    // when the final bytes are read; an abandoned prefix is not verified.
    std::size_t read(std::span<std::byte>);
    bool verified() const noexcept;
};
struct LayeredProofCommitRequest {
    std::uint64_t previous_commit_sequence = 0, base_revision = 0, final_revision = 0;
    bool operator==(const LayeredProofCommitRequest&) const = default;
};
struct LayeredProofCommitResult {
    bool replayed = false;
    std::uint64_t commit_sequence = 0;
};

class LayeredProofStore {
    std::shared_ptr<LayeredProofStoreState> state_;
    explicit LayeredProofStore(std::shared_ptr<LayeredProofStoreState>);
    friend class LayeredProofHandle;
public:
    static bool capability_available() noexcept;
    static std::uint64_t required_bytes(const LayeredProofStorePolicy&);
    // Linux O_CREAT|O_EXCL and posix_fallocate of the complete provisioned
    // range precede all hooks. Existing paths are never replaced or removed.
    static LayeredProofStore create(const std::string& path, const LayeredProofStorePolicy&,
        const LayeredProofStoreIdentity&, LayeredProofIoHook = {});
    LayeredProofStore(LayeredProofStore&&) noexcept = default;
    LayeredProofStore& operator=(LayeredProofStore&&) noexcept = default;
    LayeredProofStore(const LayeredProofStore&) = delete;
    LayeredProofStore& operator=(const LayeredProofStore&) = delete;
    LayeredProofWriter begin();
    LayeredProofReader open_reader(const LayeredProofHandle&);
    // Persist/flush marker before the caller's physical publication. Any
    // write/flush ambiguity fences this store; no recovery API is implemented.
    LayeredProofCommitResult commit(const LayeredProofHandle&, const LayeredProofCommitRequest&);
    LayeredProofStoreStats stats() const;
    LayeredProofStoreIdentity identity() const;
};

// Fixed preallocated extents are single-assignment, not a sparse-file promise.
// Descriptors and leases survive wrapper destruction; the last reference closes
// the file. Hooks run serialized under the store lock and must not reenter it.
// CRC64-ECMA-182 is error detection, not hostile-writer authentication. No
// physical model/callback, automatic retry, durable recovery or RSS claim.
// Durability means file+directory fsync protocol only. In particular tmpfs
// cannot survive reboot. Filesystem identity is reported, not certified.
} // namespace magic_geo::detail
