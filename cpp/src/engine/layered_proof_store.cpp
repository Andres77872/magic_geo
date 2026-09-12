#include "layered_proof_store.hpp"

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstring>
#include <limits>
#include <mutex>
#include <utility>
#include <vector>

#ifdef __linux__
#include <fcntl.h>
#include <linux/magic.h>
#include <sys/stat.h>
#include <sys/vfs.h>
#include <unistd.h>
#endif

namespace magic_geo::detail {
namespace {
constexpr std::uint64_t header_bytes = 256, frame_bytes = 128;
constexpr std::uint64_t crc_polynomial = UINT64_C(0x42f0e1eba9ea3693);
constexpr auto crc_table() {
    std::array<std::uint64_t, 256> table{};
    for (std::size_t i = 0; i < table.size(); ++i) {
        auto value = static_cast<std::uint64_t>(i) << 56;
        for (int bit = 0; bit < 8; ++bit)
            value = (value & (UINT64_C(1) << 63)) ? (value << 1) ^ crc_polynomial : value << 1;
        table[i] = value;
    }
    return table;
}
constexpr auto table = crc_table();
std::uint64_t checksum(std::uint64_t crc, std::span<const std::byte> bytes) {
    for (const auto byte : bytes)
        crc = (crc << 8) ^ table[static_cast<unsigned char>(crc >> 56) ^ std::to_integer<unsigned char>(byte)];
    return crc;
}
void put(std::span<std::byte> bytes, std::size_t at, std::uint64_t value) {
    for (unsigned i = 0; i < 8; ++i) bytes[at + i] = std::byte((value >> (8 * i)) & 255);
}
void magic(std::span<std::byte> bytes, const char* value) {
    for (std::size_t i = 0; i < 8; ++i) bytes[i] = std::byte(static_cast<unsigned char>(value[i]));
}
void require(bool condition, const char* code, const char* detail) {
    if (!condition) throw LayeredProofStoreError(code, detail);
}
std::uint64_t add(std::uint64_t a, std::uint64_t b) {
    require(b <= UINT64_MAX - a, "invalid_policy", "store size addition overflows");
    return a + b;
}
std::uint64_t multiply(std::uint64_t a, std::uint64_t b) {
    require(a == 0 || b <= UINT64_MAX / a, "invalid_policy", "store size product overflows");
    return a * b;
}
enum class SlotStatus { unused, open, sealed, aborted, indeterminate };
struct Slot {
    SlotStatus status = SlotStatus::unused;
    std::uint64_t length = 0, crc = 0, logical_length = 0, commit_sequence = 0;
    LayeredProofCommitRequest commit{};
};
} // namespace

LayeredProofStoreError::LayeredProofStoreError(std::string c, const char* detail, bool f, bool i)
    : std::runtime_error(detail), code(std::move(c)), fenced(f), commit_indeterminate(i) {}

struct LayeredProofStoreState {
    mutable std::mutex mutex;
    int fd = -1, directory_fd = -1;
    LayeredProofStorePolicy policy;
    LayeredProofStoreIdentity identity;
    LayeredProofIoHook hook;
    LayeredProofStoreStats stats;
    std::vector<Slot> slots;
    ~LayeredProofStoreState() {
#ifdef __linux__
        if (fd >= 0) (void)::close(fd);
        if (directory_fd >= 0) (void)::close(directory_fd);
#endif
    }
    std::uint64_t start(std::uint64_t attempt) const {
        return header_bytes + (attempt - 1) * (policy.maximum_payload_bytes + 3 * frame_bytes);
    }
    std::uint64_t footer(std::uint64_t attempt) const {
        return start(attempt) + frame_bytes + policy.maximum_payload_bytes;
    }
    void usable() const {
        if (stats.fenced)
            throw LayeredProofStoreError("store_fenced", "store is fenced; recovery is not implemented",
                                        true, stats.commit_indeterminate);
    }
    [[noreturn]] void fence(const char* code, const char* detail, bool committing = false) {
        stats.fenced = true;
        stats.commit_indeterminate = stats.commit_indeterminate || committing;
        for (auto& slot : slots) if (slot.status == SlotStatus::open) {
            slot.status = SlotStatus::indeterminate;
            ++stats.indeterminate_attempts;
        }
        throw LayeredProofStoreError(code, detail, true, stats.commit_indeterminate);
    }
    LayeredProofIoDirective operation(LayeredProofIoKind kind, std::uint64_t offset,
                                     std::uint64_t bytes, bool committing) {
        if (stats.io_operations >= policy.maximum_io_operations)
            fence("io_work_cap", "bounded I/O operation allowance exhausted", committing);
        const LayeredProofIoOperation op{kind, offset, bytes, ++stats.io_operations};
        if (!hook) return {};
        try { return hook(op); }
        catch (...) { fence("io_hook_failure", "I/O fault hook threw; no operation assumed complete", committing); }
    }
    void write_all(LayeredProofIoKind kind, std::uint64_t offset,
                   std::span<const std::byte> bytes, Slot* payload = nullptr, bool committing = false) {
#ifdef __linux__
        std::size_t done = 0;
        while (done < bytes.size()) {
            const auto directive = operation(kind, offset + done, bytes.size() - done, committing);
            if (directive.error_number == EINTR) continue;
            if (directive.error_number != 0)
                fence("io_write_failure", "injected write failure; retained prefix is incomplete", committing);
            const auto count = static_cast<std::size_t>(std::min<std::uint64_t>(
                bytes.size() - done, directive.maximum_bytes));
            if (!count) fence("io_no_progress", "write hook allowed no progress", committing);
            const auto n = ::pwrite(fd, bytes.data() + done, count, static_cast<off_t>(offset + done));
            if (n < 0) {
                if (errno == EINTR) continue; // Counted; cannot retry beyond the I/O cap.
                fence("io_write_failure", "pwrite failed; store contents may be incomplete", committing);
            }
            if (!n) fence("io_no_progress", "pwrite returned zero", committing);
            const auto written = static_cast<std::size_t>(n);
            stats.total_bytes_written += written;
            if (payload) {
                payload->crc = checksum(payload->crc, bytes.subspan(done, written));
                payload->length += written;
                stats.payload_bytes_written += written;
            }
            done += written;
        }
#else
        (void)kind; (void)offset; (void)bytes; (void)payload; (void)committing;
        fence("capability_unavailable", "Linux positional file backend required");
#endif
    }
    void read_all(std::uint64_t offset, std::span<std::byte> bytes) {
#ifdef __linux__
        std::size_t done = 0;
        while (done < bytes.size()) {
            const auto directive = operation(LayeredProofIoKind::read, offset + done, bytes.size() - done, false);
            if (directive.error_number == EINTR) continue;
            if (directive.error_number != 0) fence("io_read_failure", "injected read failure");
            const auto count = static_cast<std::size_t>(std::min<std::uint64_t>(bytes.size() - done, directive.maximum_bytes));
            if (!count) fence("io_no_progress", "read hook allowed no progress");
            const auto n = ::pread(fd, bytes.data() + done, count, static_cast<off_t>(offset + done));
            if (n < 0) {
                if (errno == EINTR) continue;
                fence("io_read_failure", "pread failed");
            }
            if (!n) fence("integrity_failure", "unexpected end of retained proof");
            stats.total_bytes_read += static_cast<std::uint64_t>(n);
            done += static_cast<std::size_t>(n);
        }
#else
        (void)offset; (void)bytes;
        fence("capability_unavailable", "Linux positional file backend required");
#endif
    }
    void flush(bool directory = false, bool committing = false) {
#ifdef __linux__
        for (;;) {
            const auto d = operation(directory ? LayeredProofIoKind::directory_flush : LayeredProofIoKind::flush,
                                     0, 0, committing);
            if (d.error_number == EINTR) continue;
            if (d.error_number != 0) fence("io_flush_failure", "injected fsync failure", committing);
            if (::fsync(directory ? directory_fd : fd) == 0) return;
            if (errno != EINTR) fence("io_flush_failure", "fsync failed; persistence is unresolved", committing);
        }
#else
        (void)directory; (void)committing;
        fence("capability_unavailable", "Linux file sync backend required");
#endif
    }
    std::array<std::byte, 256> header() const {
        std::array<std::byte, 256> out{};
        magic(out, "LYRPRF01");
        put(out, 8, 1); // Schema version.
        put(out, 16, header_bytes); put(out, 24, frame_bytes);
        put(out, 32, policy.provisioned_bytes); put(out, 40, policy.maximum_attempts);
        put(out, 48, policy.maximum_payload_bytes); put(out, 56, policy.maximum_io_operations);
        put(out, 64, policy.maximum_writers); put(out, 72, policy.maximum_readers);
        put(out, 80, policy.io_buffer_bytes); put(out, 88, identity.initial_revision);
        std::copy(identity.store.begin(), identity.store.end(), out.begin() + 96);
        std::copy(identity.source.begin(), identity.source.end(), out.begin() + 128);
        put(out, 160, stats.filesystem_type); put(out, 168, stats.known_volatile_filesystem ? 1 : 0);
        put(out, 176, 1); // CRC64-ECMA-182, init=0, xorout=0, nonreflected.
        put(out, 184, 1); // fsync protocol only, not power-loss certification.
        put(out, 248, checksum(0, std::span<const std::byte>(out).first(248)));
        return out;
    }
    std::array<std::byte, 128> frame(std::uint64_t attempt, std::uint64_t kind,
                                     std::uint32_t reason = 0) const {
        std::array<std::byte, 128> out{};
        const auto& slot = slots[static_cast<std::size_t>(attempt - 1)];
        magic(out, "LYRFRM01"); put(out, 8, kind); put(out, 16, attempt);
        put(out, 24, policy.maximum_payload_bytes);
        if (kind != 1) { put(out, 32, slot.length); put(out, 40, slot.crc); }
        put(out, 48, reason);
        std::copy(identity.store.begin(), identity.store.end(), out.begin() + 56);
        put(out, 120, checksum(0, std::span<const std::byte>(out).first(120)));
        return out;
    }
    void buffer_acquired() {
        stats.io_buffer_bytes_live += policy.io_buffer_bytes;
        stats.io_buffer_bytes_peak = std::max(stats.io_buffer_bytes_peak, stats.io_buffer_bytes_live);
    }
    void buffer_released() { stats.io_buffer_bytes_live -= policy.io_buffer_bytes; }
};

struct LayeredProofWriter::Impl {
    std::shared_ptr<LayeredProofStoreState> state;
    std::unique_ptr<std::byte[]> buffer;
    std::uint64_t attempt = 0;
    std::size_t used = 0;
    bool active = false;
    std::atomic<std::uint64_t> written{0}, appended{0};
    void release_locked() {
        if (!active) return;
        --state->stats.active_writers; state->buffer_released(); active = false;
        buffer.reset();
    }
    void flush_locked() {
        if (!used) return;
        auto& slot = state->slots[static_cast<std::size_t>(attempt - 1)];
        try { state->write_all(LayeredProofIoKind::payload,
            state->start(attempt) + frame_bytes + slot.length, {buffer.get(), used}, &slot); }
        catch (...) { written.store(slot.length); throw; }
        written.store(slot.length); used = 0;
    }
    void abort_locked(std::uint32_t reason) {
        if (!active) return;
        state->usable();
        flush_locked();
        const auto record = state->frame(attempt, 3, reason);
        state->write_all(LayeredProofIoKind::abort, state->footer(attempt), record);
        state->flush();
        state->slots[static_cast<std::size_t>(attempt - 1)].status = SlotStatus::aborted;
        ++state->stats.aborted_attempts;
        release_locked();
    }
    ~Impl() {
        if (!active) return;
        std::lock_guard lock(state->mutex);
        try { abort_locked(2); }
        catch (...) { release_locked(); } // I/O already fences; destructor cannot report by throwing.
    }
};

struct LayeredProofReader::Impl {
    std::shared_ptr<LayeredProofStoreState> state;
    std::unique_ptr<std::byte[]> buffer;
    std::uint64_t attempt = 0, size = 0, expected_crc = 0, position = 0, crc = 0;
    bool active = false;
    std::atomic<bool> complete{false};
    void release_locked() {
        if (!active) return;
        --state->stats.active_readers; state->buffer_released(); active = false; buffer.reset();
    }
    ~Impl() {
        if (!active) return;
        std::lock_guard lock(state->mutex); release_locked();
    }
};

LayeredProofHandle::LayeredProofHandle(std::shared_ptr<LayeredProofStoreState> s,
    std::uint64_t a, std::uint64_t n, std::uint64_t crc)
    : state_(std::move(s)), attempt_(a), size_(n), checksum_(crc) {}
LayeredProofWriter::LayeredProofWriter(std::unique_ptr<Impl> p) : impl_(std::move(p)) {}
LayeredProofWriter::~LayeredProofWriter() = default;
LayeredProofWriter::LayeredProofWriter(LayeredProofWriter&&) noexcept = default;
LayeredProofWriter& LayeredProofWriter::operator=(LayeredProofWriter&&) noexcept = default;
void LayeredProofWriter::append(std::span<const std::byte> bytes) {
    require(static_cast<bool>(impl_), "invalid_writer", "moved-from writer");
    auto& p = *impl_; std::lock_guard lock(p.state->mutex);
    p.state->usable(); require(p.active, "closed_writer", "writer is already terminal");
    auto& slot = p.state->slots[static_cast<std::size_t>(p.attempt - 1)];
    if (bytes.size() > p.state->policy.maximum_payload_bytes - slot.logical_length) {
        p.abort_locked(1);
        throw LayeredProofStoreError("payload_limit", "whole append exceeds admitted payload; attempt aborted");
    }
    while (!bytes.empty()) {
        const auto count = std::min(bytes.size(), p.state->policy.io_buffer_bytes - p.used);
        std::copy_n(bytes.data(), count, p.buffer.get() + p.used);
        p.used += count; slot.logical_length += count; p.appended.store(slot.logical_length);
        p.state->stats.payload_bytes_appended += count;
        bytes = bytes.subspan(count);
        if (p.used == p.state->policy.io_buffer_bytes) p.flush_locked();
    }
}
LayeredProofHandle LayeredProofWriter::seal() {
    require(static_cast<bool>(impl_), "invalid_writer", "moved-from writer");
    auto& p = *impl_; std::lock_guard lock(p.state->mutex);
    p.state->usable(); require(p.active, "closed_writer", "writer is already terminal");
    p.flush_locked();
    auto& slot = p.state->slots[static_cast<std::size_t>(p.attempt - 1)];
    const auto record = p.state->frame(p.attempt, 2);
    p.state->write_all(LayeredProofIoKind::seal, p.state->footer(p.attempt), record);
    p.state->flush();
    slot.status = SlotStatus::sealed; ++p.state->stats.sealed_attempts;
    const LayeredProofHandle result(p.state, p.attempt, slot.length, slot.crc);
    p.release_locked(); return result;
}
void LayeredProofWriter::abort(std::uint32_t reason) {
    require(static_cast<bool>(impl_), "invalid_writer", "moved-from writer");
    auto& p = *impl_; std::lock_guard lock(p.state->mutex);
    require(p.active, "closed_writer", "writer is already terminal"); p.abort_locked(reason);
}
std::uint64_t LayeredProofWriter::bytes_written() const noexcept { return impl_ ? impl_->written.load() : 0; }
std::uint64_t LayeredProofWriter::bytes_appended() const noexcept { return impl_ ? impl_->appended.load() : 0; }

LayeredProofReader::LayeredProofReader(std::unique_ptr<Impl> p) : impl_(std::move(p)) {}
LayeredProofReader::~LayeredProofReader() = default;
LayeredProofReader::LayeredProofReader(LayeredProofReader&&) noexcept = default;
LayeredProofReader& LayeredProofReader::operator=(LayeredProofReader&&) noexcept = default;
std::size_t LayeredProofReader::read(std::span<std::byte> output) {
    require(static_cast<bool>(impl_), "invalid_reader", "moved-from reader");
    auto& p = *impl_; std::lock_guard lock(p.state->mutex); p.state->usable();
    if (p.complete.load()) return 0;
    require(!output.empty(), "invalid_read_buffer", "nonempty output buffer required before EOF");
    const auto count = static_cast<std::size_t>(std::min<std::uint64_t>(
        std::min(output.size(), p.state->policy.io_buffer_bytes), p.size - p.position));
    p.state->read_all(p.state->start(p.attempt) + frame_bytes + p.position, {p.buffer.get(), count});
    p.crc = checksum(p.crc, {p.buffer.get(), count}); p.position += count;
    if (p.position == p.size) {
        if (p.crc != p.expected_crc) p.state->fence("integrity_failure", "payload CRC64 mismatch");
        p.complete.store(true);
    }
    std::copy_n(p.buffer.get(), count, output.data());
    return count;
}
bool LayeredProofReader::verified() const noexcept { return impl_ && impl_->complete.load(); }

LayeredProofStore::LayeredProofStore(std::shared_ptr<LayeredProofStoreState> p) : state_(std::move(p)) {}
bool LayeredProofStore::capability_available() noexcept {
#ifdef __linux__
    return sizeof(off_t) >= 8;
#else
    return false;
#endif
}
std::uint64_t LayeredProofStore::required_bytes(const LayeredProofStorePolicy& p) {
    require(p.provisioned_bytes > 0 && p.maximum_attempts > 0 && p.maximum_attempts <= 1048576 &&
        p.maximum_payload_bytes > 0 && p.maximum_payload_bytes <= UINT64_C(1073741824) &&
        p.maximum_io_operations > 0 && p.maximum_io_operations <= UINT64_C(1099511627776) &&
        p.maximum_writers > 0 && p.maximum_writers <= 64 && p.maximum_readers > 0 && p.maximum_readers <= 64 &&
        p.maximum_writers <= p.maximum_attempts && p.io_buffer_bytes > 0 && p.io_buffer_bytes <= 1048576,
        "invalid_policy", "finite explicit policy exceeds supported structural limits");
    const auto required = add(header_bytes, multiply(p.maximum_attempts, add(p.maximum_payload_bytes, 3 * frame_bytes)));
    require(p.provisioned_bytes >= required && p.provisioned_bytes <= static_cast<std::uint64_t>(INT64_MAX),
        "capacity_refusal", "complete attempt extents are not provisioned");
    return required;
}
LayeredProofStore LayeredProofStore::create(const std::string& path, const LayeredProofStorePolicy& policy,
    const LayeredProofStoreIdentity& identity, LayeredProofIoHook hook) {
    require(capability_available(), "capability_unavailable", "Linux large-file preallocation backend required");
    const auto required = required_bytes(policy);
    require(std::any_of(identity.store.begin(), identity.store.end(), [](std::byte x) { return x != std::byte{0}; }) &&
        std::any_of(identity.source.begin(), identity.source.end(), [](std::byte x) { return x != std::byte{0}; }),
        "invalid_identity", "explicit nonzero store and source identities required");
    require(!path.empty() && path.size() <= 4096 && path.find('\0') == std::string::npos,
        "invalid_path", "bounded nonempty path without embedded NUL required");
    auto state = std::make_shared<LayeredProofStoreState>();
    state->policy = policy; state->identity = identity; state->hook = std::move(hook);
    state->slots.resize(static_cast<std::size_t>(policy.maximum_attempts));
    state->stats.provisioned_bytes = policy.provisioned_bytes; state->stats.required_bytes = required;
    state->stats.index_payload_bytes = state->slots.capacity() * sizeof(Slot);
    state->stats.committed_revision = identity.initial_revision;
#ifdef __linux__
    const auto slash = path.find_last_of('/');
    const auto parent = slash == std::string::npos ? "." : (slash == 0 ? "/" : path.substr(0, slash));
    const auto name = slash == std::string::npos ? path : path.substr(slash + 1);
    require(!name.empty() && name != "." && name != "..", "invalid_path", "regular new basename required");
    state->directory_fd = ::open(parent.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    require(state->directory_fd >= 0, "open_failure", "cannot open parent directory");
    state->fd = ::openat(state->directory_fd, name.c_str(), O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    require(state->fd >= 0, "open_failure", "exclusive file creation refused; existing path not replaced");
    // posix_fallocate returns its error number directly, not through errno.
    const int allocated = ::posix_fallocate(state->fd, 0, static_cast<off_t>(policy.provisioned_bytes));
    require(allocated == 0, "preallocation_failure", "complete backing reservation failed; new path retained");
    struct stat file_info{};
    require(::fstat(state->fd, &file_info) == 0 && S_ISREG(file_info.st_mode) &&
        static_cast<std::uint64_t>(file_info.st_size) == policy.provisioned_bytes,
        "preallocation_failure", "preallocated regular file extent could not be verified");
    struct statfs filesystem{};
    require(::fstatfs(state->fd, &filesystem) == 0, "filesystem_query_failure", "filesystem identity unavailable");
    state->stats.filesystem_type = static_cast<std::uint64_t>(filesystem.f_type);
    state->stats.known_volatile_filesystem = filesystem.f_type == TMPFS_MAGIC || filesystem.f_type == RAMFS_MAGIC;
    const auto header = state->header();
    state->write_all(LayeredProofIoKind::header, 0, header);
    state->flush(); state->flush(true); state->stats.directory_sync_completed = true;
#endif
    return LayeredProofStore(std::move(state));
}
LayeredProofWriter LayeredProofStore::begin() {
    require(static_cast<bool>(state_), "invalid_store", "moved-from store");
    std::lock_guard lock(state_->mutex); state_->usable();
    require(state_->stats.attempts_started < state_->policy.maximum_attempts,
        "attempt_limit", "all admitted attempt slots are consumed");
    require(state_->stats.active_writers < state_->policy.maximum_writers,
        "writer_limit", "concurrent writer reservation unavailable");
    auto p = std::make_unique<LayeredProofWriter::Impl>();
    p->buffer = std::make_unique<std::byte[]>(state_->policy.io_buffer_bytes);
    p->state = state_; p->attempt = ++state_->stats.attempts_started; p->active = true;
    ++state_->stats.active_writers; state_->buffer_acquired();
    state_->stats.reserved_payload_bytes += state_->policy.maximum_payload_bytes;
    state_->slots[static_cast<std::size_t>(p->attempt - 1)].status = SlotStatus::open;
    try {
        const auto frame = state_->frame(p->attempt, 1);
        state_->write_all(LayeredProofIoKind::begin, state_->start(p->attempt), frame);
        state_->flush(); // Retain the begun attempt before any caller work.
    } catch (...) { p->release_locked(); throw; }
    return LayeredProofWriter(std::move(p));
}
LayeredProofReader LayeredProofStore::open_reader(const LayeredProofHandle& handle) {
    require(static_cast<bool>(state_), "invalid_store", "moved-from store");
    std::lock_guard lock(state_->mutex); state_->usable();
    require(handle.state_ == state_ && handle.attempt_ > 0 && handle.attempt_ <= state_->stats.attempts_started,
        "foreign_handle", "handle does not belong to this live store generation");
    const auto& slot = state_->slots[static_cast<std::size_t>(handle.attempt_ - 1)];
    require(slot.status == SlotStatus::sealed && slot.length == handle.size_ && slot.crc == handle.checksum_,
        "invalid_handle", "handle does not identify a sealed immutable payload");
    require(state_->stats.active_readers < state_->policy.maximum_readers,
        "reader_limit", "concurrent reader reservation unavailable");
    auto p = std::make_unique<LayeredProofReader::Impl>();
    p->buffer = std::make_unique<std::byte[]>(state_->policy.io_buffer_bytes);
    p->state = state_; p->attempt = handle.attempt_; p->size = slot.length; p->expected_crc = slot.crc; p->active = true;
    ++state_->stats.active_readers; state_->buffer_acquired();
    try {
        std::array<std::byte, 256> header{}; state_->read_all(0, header);
        if (header != state_->header()) state_->fence("integrity_failure", "immutable store header changed");
        std::array<std::byte, 128> frame{}; state_->read_all(state_->start(p->attempt), frame);
        if (frame != state_->frame(p->attempt, 1)) state_->fence("integrity_failure", "attempt begin frame changed");
        state_->read_all(state_->footer(p->attempt), frame);
        if (frame != state_->frame(p->attempt, 2)) state_->fence("integrity_failure", "seal frame changed");
        if (!p->size) {
            if (p->expected_crc != 0) state_->fence("integrity_failure", "empty payload has nonempty CRC");
            p->complete.store(true);
        }
    } catch (...) { p->release_locked(); throw; }
    return LayeredProofReader(std::move(p));
}
LayeredProofCommitResult LayeredProofStore::commit(const LayeredProofHandle& handle,
    const LayeredProofCommitRequest& request) {
    require(static_cast<bool>(state_), "invalid_store", "moved-from store");
    std::lock_guard lock(state_->mutex); state_->usable();
    require(handle.state_ == state_ && handle.attempt_ > 0 && handle.attempt_ <= state_->stats.attempts_started,
        "foreign_handle", "commit handle belongs to another live store generation");
    auto& slot = state_->slots[static_cast<std::size_t>(handle.attempt_ - 1)];
    require(slot.status == SlotStatus::sealed && handle.size_ == slot.length && handle.checksum_ == slot.crc,
        "invalid_handle", "commit requires an immutable sealed payload");
    if (slot.commit_sequence) {
        require(slot.commit == request, "commit_conflict", "committed handle replay has different linkage");
        return {true, slot.commit_sequence};
    }
    require(request.previous_commit_sequence == state_->stats.commit_sequence &&
        request.base_revision == state_->stats.committed_revision && request.base_revision != UINT64_MAX &&
        request.final_revision == request.base_revision + 1,
        "stale_commit", "commit does not extend the exact stored head");
    const auto sequence = state_->stats.commit_sequence + 1;
    std::array<std::byte, 128> marker{};
    magic(marker, "LYRCMT01"); put(marker, 8, handle.attempt_); put(marker, 16, sequence);
    put(marker, 24, request.previous_commit_sequence); put(marker, 32, request.base_revision);
    put(marker, 40, request.final_revision); put(marker, 48, slot.length); put(marker, 56, slot.crc);
    std::copy(state_->identity.store.begin(), state_->identity.store.end(), marker.begin() + 64);
    put(marker, 120, checksum(0, std::span<const std::byte>(marker).first(120)));
    state_->write_all(LayeredProofIoKind::commit, state_->footer(handle.attempt_) + frame_bytes, marker, nullptr, true);
    state_->flush(false, true);
    // All allocation and all fallible I/O precede these scalar publications.
    slot.commit = request; slot.commit_sequence = sequence;
    state_->stats.commit_sequence = sequence; state_->stats.committed_revision = request.final_revision;
    ++state_->stats.committed_records;
    return {false, sequence};
}
LayeredProofStoreStats LayeredProofStore::stats() const {
    require(static_cast<bool>(state_), "invalid_store", "moved-from store");
    std::lock_guard lock(state_->mutex); return state_->stats;
}
LayeredProofStoreIdentity LayeredProofStore::identity() const {
    require(static_cast<bool>(state_), "invalid_store", "moved-from store");
    std::lock_guard lock(state_->mutex); return state_->identity;
}
LayeredProofReader LayeredProofHandle::open_reader() const {
    require(static_cast<bool>(state_), "invalid_handle", "empty proof handle");
    return LayeredProofStore(state_).open_reader(*this);
}
} // namespace magic_geo::detail
