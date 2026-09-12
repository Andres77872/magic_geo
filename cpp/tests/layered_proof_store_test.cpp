#include "engine/layered_proof_store.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <initializer_list>
#include <iostream>
#include <limits>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#ifdef __linux__
#include <fcntl.h>
#include <sys/resource.h>
#include <unistd.h>
#endif

// This driver exercises a byte store, not a proof producer. In particular it
// does not include or invoke a codec, thermal integrator, owner or world API.
// Every created or deliberately damaged file remains at its exclusive path.
using namespace magic_geo::detail;
namespace {
using Bytes = std::vector<std::byte>;
using Policy = LayeredProofStorePolicy;
using Identity = LayeredProofStoreIdentity;
using Store = LayeredProofStore;
using Writer = LayeredProofWriter;
using Reader = LayeredProofReader;
using Handle = LayeredProofHandle;
using Kind = LayeredProofIoKind;
using Directive = LayeredProofIoDirective;
using Operation = LayeredProofIoOperation;
constexpr std::uint64_t horizon_payload = 3069231, horizon_records = 1080;
constexpr std::uint64_t horizon_extent = 256 + horizon_records * (horizon_payload + 384);
constexpr std::size_t horizon_buffer = 65536;

void quote(std::string_view value) {
    std::cout << '"';
    constexpr char hex[] = "0123456789abcdef";
    for (const unsigned char c : value) {
        if (c == '"' || c == '\\') std::cout << '\\' << static_cast<char>(c);
        else if (c < 32) std::cout << "\\u00" << hex[c >> 4] << hex[c & 15];
        else std::cout << static_cast<char>(c);
    }
    std::cout << '"';
}
Bytes bytes(std::string_view text) {
    Bytes out; out.reserve(text.size());
    for (const unsigned char c : text) out.push_back(std::byte(c));
    return out;
}
std::uint64_t crc(std::span<const std::byte> value) {
    // Independent bitwise implementation; the store uses a generated table.
    std::uint64_t result = 0;
    for (const auto b : value) {
        result ^= std::uint64_t(std::to_integer<unsigned char>(b)) << 56;
        for (int bit = 0; bit != 8; ++bit)
            result = (result & (UINT64_C(1) << 63))
                ? (result << 1) ^ UINT64_C(0x42f0e1eba9ea3693) : result << 1;
    }
    return result;
}
Policy policy(std::uint64_t attempts = 3, std::uint64_t payload = 32,
              std::size_t buffer = 8, std::size_t writers = 1,
              std::size_t readers = 1, std::uint64_t operations = 10000) {
    return {256 + attempts * (payload + 384), attempts, payload, operations,
            writers, readers, buffer};
}
Identity identity() {
    Identity id;
    for (std::size_t i = 0; i < 32; ++i) {
        id.store[i] = std::byte(i + 1); id.source[i] = std::byte(i + 65);
    }
    return id;
}
void policy_json(const Policy& p) {
    std::cout << "{\"provisioned_bytes\":" << p.provisioned_bytes
        << ",\"maximum_attempts\":" << p.maximum_attempts
        << ",\"maximum_payload_bytes\":" << p.maximum_payload_bytes
        << ",\"maximum_io_operations\":" << p.maximum_io_operations
        << ",\"maximum_writers\":" << p.maximum_writers
        << ",\"maximum_readers\":" << p.maximum_readers
        << ",\"io_buffer_bytes\":" << p.io_buffer_bytes << '}';
}
void identity_json(const Identity& id) {
    std::cout << "{\"store\":[";
    for (std::size_t i = 0; i < 32; ++i) {
        if (i) std::cout << ',';
        std::cout << std::to_integer<unsigned>(id.store[i]);
    }
    std::cout << "],\"source\":[";
    for (std::size_t i = 0; i < 32; ++i) {
        if (i) std::cout << ',';
        std::cout << std::to_integer<unsigned>(id.source[i]);
    }
    std::cout << "],\"initial_revision\":" << id.initial_revision << '}';
}
void stats_json(const LayeredProofStoreStats& s) {
#define U(name) std::cout << "\"" #name "\":" << s.name << ','
    std::cout << '{';
    U(provisioned_bytes); U(required_bytes); U(reserved_payload_bytes);
    U(attempts_started); U(sealed_attempts); U(aborted_attempts); U(indeterminate_attempts);
    U(committed_records); U(payload_bytes_written); U(total_bytes_written); U(total_bytes_read);
    U(payload_bytes_appended); U(io_operations); U(commit_sequence); U(committed_revision);
    U(active_writers); U(active_readers); U(io_buffer_bytes_live); U(io_buffer_bytes_peak);
    U(index_payload_bytes); U(fenced); U(commit_indeterminate); U(directory_sync_completed);
    U(known_volatile_filesystem);
#undef U
    std::cout << "\"filesystem_type\":" << s.filesystem_type << '}';
}

struct Calls {
    std::uint64_t create = 0, required = 0, begin = 0, append = 0, seal = 0;
    std::uint64_t abort = 0, commit = 0, open_reader = 0, read = 0;
};
std::vector<std::string> make_check_names(std::string_view mode);
struct Harness {
    std::string mode;
    std::uint64_t checks = 0, failures = 0, errors = 0, cases = 0, stats_rows = 0;
    Calls calls;
    std::vector<std::string> expected_checks;
    explicit Harness(std::string value) : mode(std::move(value)), expected_checks(make_check_names(mode)) {}
    void check(const std::string& name, bool pass) {
        pass = pass && checks < expected_checks.size() && expected_checks[static_cast<std::size_t>(checks)] == name;
        ++checks; if (!pass) ++failures;
        std::cout << "{\"type\":\"check\",\"name\":"; quote(name);
        std::cout << ",\"pass\":" << pass << "}\n";
    }
    template<class F> void error(const std::string& name, const char* expected,
                                bool fenced, bool ambiguous, F&& action) {
        std::string code = "no_exception"; bool actual_fenced = false, actual_ambiguous = false;
        try { action(); }
        catch (const LayeredProofStoreError& e) {
            code = e.code; actual_fenced = e.fenced; actual_ambiguous = e.commit_indeterminate;
        }
        ++errors;
        std::cout << "{\"type\":\"error\",\"name\":"; quote(name);
        std::cout << ",\"expected_code\":"; quote(expected);
        std::cout << ",\"code\":"; quote(code);
        std::cout << ",\"fenced\":" << actual_fenced
            << ",\"commit_indeterminate\":" << actual_ambiguous << "}\n";
        check(name + ".typed", code == expected && actual_fenced == fenced && actual_ambiguous == ambiguous);
    }
    Store create(const std::string& name, const std::filesystem::path& path,
                 const Policy& p, const Identity& id = identity(), LayeredProofIoHook hook = {}) {
        ++cases; ++calls.create;
        std::cout << "{\"type\":\"case\",\"name\":"; quote(name);
        std::cout << ",\"path\":"; quote(path.string());
        std::cout << ",\"policy\":"; policy_json(p);
        std::cout << ",\"identity\":"; identity_json(id); std::cout << "}\n";
        return Store::create(path.string(), p, id, std::move(hook));
    }
    Writer begin(Store& s) { ++calls.begin; return s.begin(); }
    void append(Writer& w, std::span<const std::byte> b) { ++calls.append; w.append(b); }
    Handle seal(Writer& w) { ++calls.seal; return w.seal(); }
    void abort(Writer& w, std::uint32_t reason = 0) { ++calls.abort; w.abort(reason); }
    LayeredProofCommitResult commit(Store& s, const Handle& h, LayeredProofCommitRequest r) {
        ++calls.commit; return s.commit(h, r);
    }
    Reader reader(Store& s, const Handle& h) { ++calls.open_reader; return s.open_reader(h); }
    Reader reader(const Handle& h) { ++calls.open_reader; return h.open_reader(); }
    std::size_t read(Reader& r, std::span<std::byte> b) { ++calls.read; return r.read(b); }
    bool verify(Reader& r, std::span<const std::byte> expected) {
        std::array<std::byte, horizon_buffer> buffer{};
        std::size_t total = 0; bool equal = true;
        for (;;) {
            const auto n = read(r, buffer);
            if (!n) break;
            // Keep draining after a differing prefix: only the last read
            // reaches the store's complete-payload CRC check. No bad prefix
            // may turn a required typed integrity refusal into early success.
            if (n > expected.size() - std::min(total, expected.size())) equal = false;
            else if (!std::equal(buffer.begin(), buffer.begin() + static_cast<std::ptrdiff_t>(n),
                                 expected.begin() + static_cast<std::ptrdiff_t>(total))) equal = false;
            total += n;
        }
        return equal && total == expected.size() && r.verified();
    }
    bool verify(const Handle& h, std::span<const std::byte> expected) {
        auto r = reader(h); return verify(r, expected);
    }
    void stats(const std::string& name, const char* stage, const Store& s) {
        ++stats_rows;
        std::cout << "{\"type\":\"stats\",\"case\":"; quote(name);
        std::cout << ",\"stage\":"; quote(stage);
        std::cout << ",\"value\":"; stats_json(s.stats()); std::cout << "}\n";
    }
    int finish() const {
        std::cout << "{\"type\":\"summary\",\"mode\":"; quote(mode);
        std::cout << ",\"checks\":" << checks << ",\"failures\":" << failures
            << ",\"errors\":" << errors << ",\"cases\":" << cases
            << ",\"stats_rows\":" << stats_rows << ",\"schedule_complete\":"
            << (checks == expected_checks.size()) << ",\"calls\":{";
#define C(name) std::cout << "\"" #name "\":" << calls.name << ','
        C(create); C(required); C(begin); C(append); C(seal); C(abort); C(commit); C(open_reader);
#undef C
        std::cout << "\"read\":" << calls.read
            << "},\"codec_calls\":0,\"owner_calls\":0,\"model_calls\":0}\n";
        return failures || checks != expected_checks.size() ? 1 : 0;
    }
};

void plan(const char* mode) {
    std::cout << "{\"type\":\"plan\",\"schema\":\"layered_proof_store_qualification_v1\",\"mode\":";
    quote(mode);
    std::cout << ",\"data_only\":true,\"files_retained\":true,\"physical_proof_claim\":false,"
        "\"annual_numerical_claim\":false,\"rss_is_not_wire_bytes\":true}\n";
}
std::uint64_t payload_offset(const Policy& p, std::uint64_t attempt) {
    return 256 + (attempt - 1) * (p.maximum_payload_bytes + 384) + 128;
}
Bytes raw_read(const std::filesystem::path& path, std::uint64_t offset, std::size_t n) {
    std::ifstream in(path, std::ios::binary); in.seekg(static_cast<std::streamoff>(offset));
    Bytes out(n);
    if (!in.read(reinterpret_cast<char*>(out.data()), static_cast<std::streamsize>(n)))
        throw std::runtime_error("retained-file read failed");
    return out;
}
void raw_create(const std::filesystem::path& path, std::span<const std::byte> value) {
#ifdef __linux__
    const int fd = ::open(path.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (fd < 0) throw std::runtime_error("exclusive fixture creation failed");
    const auto n = ::write(fd, value.data(), value.size());
    const int closed = ::close(fd);
    if (n < 0 || static_cast<std::size_t>(n) != value.size() || closed != 0)
        throw std::runtime_error("exclusive fixture write failed");
#else
    (void)path; (void)value; throw std::runtime_error("Linux fixture required");
#endif
}
void damage(const std::filesystem::path& path, std::uint64_t offset, bool truncate) {
#ifdef __linux__
    const int fd = ::open(path.c_str(), O_RDWR | O_CLOEXEC);
    if (fd < 0) throw std::runtime_error("cannot open newly created fault fixture");
    bool okay = false;
    if (truncate) okay = ::ftruncate(fd, static_cast<off_t>(offset)) == 0;
    else {
        unsigned char b = 0;
        if (::pread(fd, &b, 1, static_cast<off_t>(offset)) == 1) {
            b ^= 0x80;
            okay = ::pwrite(fd, &b, 1, static_cast<off_t>(offset)) == 1;
        }
    }
    const int closed = ::close(fd);
    if (!okay || closed != 0) throw std::runtime_error("retained fault fixture mutation failed");
#else
    (void)path; (void)offset; (void)truncate; throw std::runtime_error("Linux fixture required");
#endif
}

struct InvalidPolicy { const char* name; Policy value; const char* code; };
std::vector<InvalidPolicy> invalid_policies() {
    std::vector<InvalidPolicy> result;
    auto add = [&](const char* name, auto change, const char* code = "invalid_policy") {
        auto p = policy(); change(p); result.push_back({name, p, code});
    };
    add("capacity_one_short", [](auto& p) { --p.provisioned_bytes; }, "capacity_refusal");
    add("zero_provision", [](auto& p) { p.provisioned_bytes = 0; });
    add("zero_attempts", [](auto& p) { p.maximum_attempts = 0; });
    add("zero_payload", [](auto& p) { p.maximum_payload_bytes = 0; });
    add("zero_io", [](auto& p) { p.maximum_io_operations = 0; });
    add("zero_writers", [](auto& p) { p.maximum_writers = 0; });
    add("zero_readers", [](auto& p) { p.maximum_readers = 0; });
    add("zero_buffer", [](auto& p) { p.io_buffer_bytes = 0; });
    add("overflow_attempts", [](auto& p) { p.maximum_attempts = UINT64_MAX; });
    add("overflow_payload", [](auto& p) { p.maximum_payload_bytes = UINT64_MAX; });
    add("overflow_io", [](auto& p) { p.maximum_io_operations = UINT64_MAX; });
    add("overflow_provision", [](auto& p) { p.provisioned_bytes = UINT64_MAX; }, "capacity_refusal");
    add("writers_above_attempts", [](auto& p) { p.maximum_writers = 4; });
    add("buffer_above_hard", [](auto& p) { p.io_buffer_bytes = 1048577; });
    return result;
}
void admission_controls(Harness& t, const std::filesystem::path& dir) {
    const auto p = policy(); ++t.calls.required;
    t.check("capacity_exact_formula", Store::required_bytes(p) == p.provisioned_bytes);
    for (const auto& c : invalid_policies()) {
        std::uint64_t hooks = 0; const std::string name = c.name;
        const auto path = dir / (name + ".bin");
        t.error(name, c.code, false, false, [&] {
            auto s = t.create(name, path, c.value, identity(), [&](const auto&) { ++hooks; return Directive{}; });
        });
        t.check(name + ".no_hook_or_file", hooks == 0 && !std::filesystem::exists(path));
    }
    for (const std::string name : {"zero_store_identity", "zero_source_identity"}) {
        auto id = identity(); if (name == "zero_store_identity") id.store = {}; else id.source = {};
        std::uint64_t hooks = 0; const auto path = dir / (name + ".bin");
        t.error(name, "invalid_identity", false, false, [&] {
            auto s = t.create(name, path, p, id, [&](const auto&) { ++hooks; return Directive{}; });
        });
        t.check(name + ".no_hook_or_file", hooks == 0 && !std::filesystem::exists(path));
    }
    const auto path = dir / "existing_path.bin"; const auto sentinel = bytes("unchanged-existing-file");
    raw_create(path, sentinel); std::uint64_t hooks = 0;
    t.error("existing_path", "open_failure", false, false, [&] {
        auto s = t.create("existing_path", path, p, identity(), [&](const auto&) { ++hooks; return Directive{}; });
    });
    t.check("existing_path.unchanged", hooks == 0 && std::filesystem::file_size(path) == sentinel.size()
        && raw_read(path, 0, sentinel.size()) == sentinel);
}
void buffered_control(Harness& t, const std::filesystem::path& dir) {
    const auto p = policy(2, 32, 16); const auto path = dir / "buffered_short_crc.bin";
    std::uint64_t interruptions = 0, payload_ops = 0, short_reads = 0;
    auto s = t.create("buffered_short_crc", path, p, identity(), [&](const Operation& op) {
        if (op.kind == Kind::payload) {
            ++payload_ops;
            if (interruptions < 2) { ++interruptions; return Directive{UINT64_MAX, EINTR}; }
            return Directive{3, 0};
        }
        if (op.kind == Kind::read) { ++short_reads; return Directive{3, 0}; }
        return Directive{};
    });
    t.check("buffered_short_crc.capacity", std::filesystem::file_size(path) == p.provisioned_bytes
        && s.stats().required_bytes == p.provisioned_bytes && s.stats().directory_sync_completed);
    t.stats("buffered_short_crc", "created", s);
    auto w = t.begin(s); const auto input = bytes("123456789"); t.append(w, input);
    t.check("buffered_short_crc.logical_before_flush", w.bytes_appended() == 9 && w.bytes_written() == 0
        && s.stats().payload_bytes_appended == 9 && s.stats().payload_bytes_written == 0);
    t.stats("buffered_short_crc", "buffered", s);
    const auto h = t.seal(w);
    t.check("buffered_short_crc.standard_crc", h.checksum_crc64_ecma182() == UINT64_C(0x6c40df5f0b497347)
        && crc(input) == UINT64_C(0x6c40df5f0b497347));
    t.check("buffered_short_crc.real_prefix", w.bytes_written() == 9 && h.payload_bytes() == 9
        && payload_ops == 5 && interruptions == 2 && raw_read(path, payload_offset(p, 1), 9) == input);
    t.check("buffered_short_crc.read", t.verify(h, input) && short_reads == 175
        && s.stats().total_bytes_read == 521 && s.stats().total_bytes_written == 521
        && s.stats().io_operations == 187);
    t.check("buffered_short_crc.released", s.stats().active_writers == 0 && s.stats().active_readers == 0
        && s.stats().io_buffer_bytes_live == 0 && s.stats().io_buffer_bytes_peak == 16);
    t.stats("buffered_short_crc", "final", s);
}
void lease_abort_controls(Harness& t, const std::filesystem::path& dir) {
    const auto p = policy(5, 16, 8, 2); const auto path = dir / "lease_abort.bin";
    auto s = t.create("lease_abort", path, p);
    std::optional<Writer> a(t.begin(s)), b(t.begin(s));
    t.append(*a, bytes("abc")); t.append(*b, bytes("DEF"));
    t.error("lease_abort.writer_cap", "writer_limit", false, false, [&] { auto x = t.begin(s); });
    t.check("lease_abort.writer_cap_no_attempt", s.stats().attempts_started == 2
        && s.stats().active_writers == 2 && s.stats().io_buffer_bytes_live == 16);
    t.abort(*a, 77); a.reset(); b.reset();
    t.check("lease_abort.explicit_destructor_prefix", s.stats().aborted_attempts == 2
        && s.stats().payload_bytes_written == 6 && s.stats().active_writers == 0
        && raw_read(path, payload_offset(p, 1), 3) == bytes("abc")
        && raw_read(path, payload_offset(p, 2), 3) == bytes("DEF"));
    auto c = t.begin(s); t.append(c, bytes("ghij"));
    t.error("lease_abort.payload_cap", "payload_limit", false, false, [&] { t.append(c, bytes("1234567890123")); });
    t.check("lease_abort.payload_cap_prefix", c.bytes_appended() == 4 && c.bytes_written() == 4
        && s.stats().aborted_attempts == 3 && raw_read(path, payload_offset(p, 3), 4) == bytes("ghij"));
    auto d = t.begin(s); const auto empty = t.seal(d);
    t.check("lease_abort.empty_sealed", empty.payload_bytes() == 0 && empty.checksum_crc64_ecma182() == 0);
    const auto commit = t.commit(s, empty, {0, 0, 1});
    t.check("lease_abort.empty_commit", !commit.replayed && commit.commit_sequence == 1);
    auto e = t.begin(s); const auto input = bytes("123456789"); t.append(e, input);
    std::optional<Reader> empty_reader(t.reader(s, empty));
    t.check("lease_abort.empty_verified_and_overlap", empty_reader->verified()
        && t.read(*empty_reader, {}) == 0 && s.stats().active_writers == 1 && s.stats().active_readers == 1);
    const auto h = t.seal(e);
    t.error("lease_abort.reader_cap", "reader_limit", false, false, [&] { auto r = t.reader(s, h); });
    empty_reader.reset();
    {
        auto prefix = t.reader(s, h); std::array<std::byte, 1> one{};
        t.check("lease_abort.abandoned_read_unverified", t.read(prefix, one) == 1 && !prefix.verified());
    }
    t.check("lease_abort.reader_released", t.verify(h, input) && s.stats().active_readers == 0);
    t.error("lease_abort.no_attempt_refund", "attempt_limit", false, false, [&] { auto x = t.begin(s); });
    t.check("lease_abort.final_counts", s.stats().attempts_started == 5 && s.stats().aborted_attempts == 3
        && s.stats().sealed_attempts == 2 && s.stats().committed_records == 1
        && s.stats().reserved_payload_bytes == 80 && s.stats().payload_bytes_written == 19
        && s.stats().payload_bytes_appended == 19 && !s.stats().fenced);
    t.stats("lease_abort", "final", s);
}
void lifetime_commit_controls(Harness& t, const std::filesystem::path& dir) {
    const auto p = policy(3); std::optional<Store> original(t.create("lifetime", dir / "lifetime.bin", p));
    Store moved(std::move(*original));
    t.error("lifetime.moved_store", "invalid_store", false, false, [&] { (void)original->stats(); });
    original.reset();
    const auto input = bytes("123456789"); Handle first, second, sibling;
    {
        auto first_writer = t.begin(moved); Writer moved_writer(std::move(first_writer));
        t.error("lifetime.moved_writer", "invalid_writer", false, false, [&] { t.append(first_writer, {}); });
        t.append(moved_writer, input); first = t.seal(moved_writer);
    }
    const auto c1 = t.commit(moved, first, {0, 0, 1});
    { auto w = t.begin(moved); t.append(w, bytes("second")); second = t.seal(w); }
    { auto w = t.begin(moved); t.append(w, bytes("sibling")); sibling = t.seal(w); }
    const auto c2 = t.commit(moved, second, {1, 1, 2}); const auto before_replay = moved.stats();
    const auto replay = t.commit(moved, first, {0, 0, 1});
    t.check("lifetime.exact_replay_after_later_head", !c1.replayed && !c2.replayed && replay.replayed
        && replay.commit_sequence == 1 && moved.stats().commit_sequence == 2
        && moved.stats().committed_revision == 2 && moved.stats().io_operations == before_replay.io_operations);
    t.error("lifetime.changed_linkage", "commit_conflict", false, false, [&] { (void)t.commit(moved, first, {1, 1, 2}); });
    t.error("lifetime.stale_sibling", "stale_commit", false, false, [&] { (void)t.commit(moved, sibling, {1, 1, 2}); });
    auto foreign = t.create("foreign", dir / "foreign.bin", policy(1));
    t.error("lifetime.foreign_reader", "foreign_handle", false, false, [&] { auto r = t.reader(foreign, first); });
    t.error("lifetime.foreign_commit", "foreign_handle", false, false, [&] { (void)t.commit(foreign, first, {0, 0, 1}); });
    t.error("lifetime.empty_handle", "invalid_handle", false, false, [&] { auto r = t.reader(Handle{}); });
    t.check("lifetime.refusal_no_io", moved.stats().io_operations == before_replay.io_operations
        && foreign.stats().io_operations == 3 && !moved.stats().fenced);
    t.stats("foreign", "final", foreign);
    auto reader_original = t.reader(moved, first); std::optional<Reader> reader(std::move(reader_original));
    t.error("lifetime.moved_reader", "invalid_reader", false, false, [&] { std::array<std::byte, 1> one{}; (void)t.read(reader_original, one); });
    t.error("lifetime.empty_read_buffer", "invalid_read_buffer", false, false, [&] { (void)t.read(*reader, {}); });
    const Handle retained = first;
    // Moving into an optional permits destruction of the final Store wrapper;
    // only reader/handle references then keep the file and quota state alive.
    std::optional<Store> final_wrapper(std::move(moved));
    t.stats("lifetime", "before_wrapper_destruction", *final_wrapper); final_wrapper.reset();
    t.check("lifetime.reader_survives_wrapper", t.verify(*reader, input)); reader.reset();
    t.check("lifetime.handle_survives_wrapper", retained.valid() && t.verify(retained, input));
}

constexpr std::array<const char*, 4> corruption_names = {"corrupt_header", "corrupt_seal", "corrupt_payload", "truncated_file"};
void corruption_controls(Harness& t, const std::filesystem::path& dir) {
    const auto p = policy(1, 16, 8); const auto input = bytes("123456789");
    for (const std::string name : corruption_names) {
        const auto path = dir / (name + ".bin"); auto s = t.create(name, path, p);
        auto w = t.begin(s); t.append(w, input); const auto h = t.seal(w);
        (void)t.commit(s, h, {0, 0, 1});
        std::uint64_t at = 0; bool truncate = false;
        if (name == "corrupt_seal") at = payload_offset(p, 1) + p.maximum_payload_bytes;
        if (name == "corrupt_payload") at = payload_offset(p, 1) + 2;
        if (name == "truncated_file") { at = payload_offset(p, 1) + 4; truncate = true; }
        damage(path, at, truncate);
        std::cout << "{\"type\":\"damage\",\"case\":"; quote(name);
        std::cout << ",\"offset\":" << at << ",\"truncate\":" << truncate << "}\n";
        t.error(name, "integrity_failure", true, false, [&] { (void)t.verify(h, input); });
        t.error(name + ".fenced_again", "store_fenced", true, false, [&] { auto r = t.reader(s, h); });
        t.check(name + ".head_retained_and_lease_released", s.stats().commit_sequence == 1
            && s.stats().committed_revision == 1 && s.stats().committed_records == 1
            && s.stats().active_readers == 0 && s.stats().active_writers == 0
            && s.stats().io_buffer_bytes_live == 0 && !s.stats().commit_indeterminate);
        t.stats(name, "final", s);
    }
}

struct FaultCase { const char* name; Kind kind; int error; bool zero; bool hook_throw; bool committing; };
constexpr std::array<FaultCase, 9> faults = {{
    {"seal_write_error", Kind::seal, EIO, false, false, false},
    {"seal_flush_error", Kind::flush, EIO, false, false, false},
    {"commit_write_error", Kind::commit, EIO, false, false, true},
    {"commit_flush_error", Kind::flush, EIO, false, false, true},
    {"seal_nonprogress", Kind::seal, 0, true, false, false},
    {"commit_nonprogress", Kind::commit, 0, true, false, true},
    {"seal_hook_throw", Kind::seal, 0, false, true, false},
    {"commit_hook_throw", Kind::commit, 0, false, true, true},
    {"payload_nonprogress", Kind::payload, 0, true, false, false}
}};
const char* fault_code(const FaultCase& c) {
    if (c.hook_throw) return "io_hook_failure";
    if (c.zero) return "io_no_progress";
    return c.kind == Kind::flush ? "io_flush_failure" : "io_write_failure";
}
void fault_controls(Harness& t, const std::filesystem::path& dir) {
    const auto p = policy(2, 16, 8);
    for (const auto& c : faults) {
        const std::string name = c.name; bool armed = false; std::uint64_t injected = 0;
        auto s = t.create(name, dir / (name + ".bin"), p, identity(), [&](const Operation& op) {
            if (armed && op.kind == c.kind) {
                ++injected;
                if (c.hook_throw) throw std::runtime_error("fixed hook failure");
                return Directive{c.zero ? 0 : UINT64_MAX, c.error};
            }
            return Directive{};
        });
        std::optional<Writer> w(t.begin(s)); t.append(*w, bytes("abc"));
        std::optional<Handle> h;
        if (c.committing) h = t.seal(*w);
        armed = true;
        t.error(name, fault_code(c), true, c.committing, [&] {
            if (c.committing) (void)t.commit(s, *h, {0, 0, 1}); else (void)t.seal(*w);
        });
        t.check(name + ".fenced_unpublished", injected == 1 && s.stats().fenced
            && s.stats().commit_sequence == 0 && s.stats().committed_revision == 0
            && s.stats().committed_records == 0 && s.stats().commit_indeterminate == c.committing
            && s.stats().indeterminate_attempts == (c.committing ? 0 : 1));
        t.error(name + ".next_begin", "store_fenced", true, c.committing, [&] { auto next = t.begin(s); });
        t.stats(name, "before_writer_destruction", s);
        w.reset();
        t.check(name + ".destructor_releases", s.stats().active_writers == 0 && s.stats().io_buffer_bytes_live == 0);
        t.stats(name, "final", s);
    }
    {
        const std::string name = "payload_prefix_failure"; std::uint64_t payload_calls = 0;
        const auto path = dir / (name + ".bin");
        auto s = t.create(name, path, p, identity(), [&](const Operation& op) {
            if (op.kind != Kind::payload) return Directive{};
            if (++payload_calls == 1) return Directive{3, 0};
            return Directive{UINT64_MAX, EIO};
        });
        std::optional<Writer> w(t.begin(s));
        t.error(name, "io_write_failure", true, false, [&] { t.append(*w, bytes("abcdefgh")); });
        t.check(name + ".positive_three_bytes", w->bytes_written() == 3 && w->bytes_appended() == 8
            && s.stats().payload_bytes_written == 3 && s.stats().payload_bytes_appended == 8
            && raw_read(path, payload_offset(p, 1), 3) == bytes("abc") && payload_calls == 2);
        w.reset();
        t.check(name + ".destructor_releases", s.stats().active_writers == 0
            && s.stats().io_buffer_bytes_live == 0 && s.stats().indeterminate_attempts == 1
            && s.stats().aborted_attempts == 0);
        t.stats(name, "final", s);
    }
    {
        const std::string name = "repeated_eintr"; auto cap = p; cap.maximum_io_operations = 12;
        std::uint64_t interrupted = 0;
        auto s = t.create(name, dir / (name + ".bin"), cap, identity(), [&](const Operation& op) {
            if (op.kind == Kind::payload) { ++interrupted; return Directive{UINT64_MAX, EINTR}; }
            return Directive{};
        });
        std::optional<Writer> w(t.begin(s));
        t.error(name, "io_work_cap", true, false, [&] { t.append(*w, bytes("abcdefgh")); });
        t.check(name + ".bounded_zero_progress", interrupted == 7 && s.stats().io_operations == 12
            && w->bytes_written() == 0 && w->bytes_appended() == 8 && s.stats().payload_bytes_written == 0);
        w.reset();
        t.check(name + ".lease_released", s.stats().active_writers == 0 && s.stats().io_buffer_bytes_live == 0);
        t.stats(name, "final", s);
    }
    for (const std::string name : {"read_nonprogress", "read_error", "read_repeated_eintr"}) {
        auto cap = p; cap.maximum_io_operations = 20; bool armed = false; std::uint64_t injected = 0;
        auto s = t.create(name, dir / (name + ".bin"), cap, identity(), [&](const Operation& op) {
            if (armed && op.kind == Kind::read) {
                ++injected;
                if (name == "read_nonprogress") return Directive{0, 0};
                return Directive{UINT64_MAX, name == "read_error" ? EIO : EINTR};
            }
            return Directive{};
        });
        auto w = t.begin(s); t.append(w, bytes("abc")); const auto h = t.seal(w); armed = true;
        const char* expected = name == "read_nonprogress" ? "io_no_progress"
            : name == "read_error" ? "io_read_failure" : "io_work_cap";
        t.error(name, expected, true, false, [&] { auto r = t.reader(s, h); });
        t.check(name + ".lease_released_and_bounded", s.stats().active_readers == 0
            && s.stats().io_buffer_bytes_live == 0 && s.stats().total_bytes_read == 0
            && injected == (name == "read_repeated_eintr" ? 12 : 1)
            && s.stats().io_operations <= cap.maximum_io_operations);
        t.stats(name, "final", s);
    }
}

struct PlannedCase { std::string name; Policy policy; Identity identity; };
std::vector<PlannedCase> planned_cases() {
    std::vector<PlannedCase> out;
    auto add = [&](std::string name, Policy p, Identity id = identity()) {
        out.push_back({std::move(name), p, id});
    };
    for (const auto& c : invalid_policies()) add(c.name, c.value);
    auto id = identity(); id.store = {}; add("zero_store_identity", policy(), id);
    id = identity(); id.source = {}; add("zero_source_identity", policy(), id);
    add("existing_path", policy()); add("buffered_short_crc", policy(2, 32, 16));
    add("lease_abort", policy(5, 16, 8, 2)); add("lifetime", policy(3)); add("foreign", policy(1));
    for (const auto name : corruption_names) add(name, policy(1, 16, 8));
    for (const auto& c : faults) add(c.name, policy(2, 16, 8));
    add("payload_prefix_failure", policy(2, 16, 8)); add("repeated_eintr", policy(2, 16, 8, 1, 1, 12));
    for (const auto name : {"read_nonprogress", "read_error", "read_repeated_eintr"})
        add(name, policy(2, 16, 8, 1, 1, 20));
    return out;
}
struct PlannedError { std::string name, code; bool fenced, ambiguous; };
std::vector<PlannedError> planned_errors() {
    std::vector<PlannedError> out;
    auto add = [&](std::string name, const char* code, bool fence = false, bool ambiguous = false) {
        out.push_back({std::move(name), code, fence, ambiguous});
    };
    for (const auto& c : invalid_policies()) add(c.name, c.code);
    add("zero_store_identity", "invalid_identity"); add("zero_source_identity", "invalid_identity");
    add("existing_path", "open_failure");
    add("lease_abort.writer_cap", "writer_limit"); add("lease_abort.payload_cap", "payload_limit");
    add("lease_abort.reader_cap", "reader_limit"); add("lease_abort.no_attempt_refund", "attempt_limit");
    add("lifetime.moved_store", "invalid_store"); add("lifetime.moved_writer", "invalid_writer");
    add("lifetime.changed_linkage", "commit_conflict"); add("lifetime.stale_sibling", "stale_commit");
    add("lifetime.foreign_reader", "foreign_handle"); add("lifetime.foreign_commit", "foreign_handle");
    add("lifetime.empty_handle", "invalid_handle"); add("lifetime.moved_reader", "invalid_reader");
    add("lifetime.empty_read_buffer", "invalid_read_buffer");
    for (const std::string name : corruption_names) {
        add(name, "integrity_failure", true); add(name + ".fenced_again", "store_fenced", true);
    }
    for (const auto& c : faults) {
        add(c.name, fault_code(c), true, c.committing);
        add(std::string(c.name) + ".next_begin", "store_fenced", true, c.committing);
    }
    add("payload_prefix_failure", "io_write_failure", true); add("repeated_eintr", "io_work_cap", true);
    add("read_nonprogress", "io_no_progress", true); add("read_error", "io_read_failure", true);
    add("read_repeated_eintr", "io_work_cap", true);
    return out;
}
std::vector<std::pair<std::string, std::string>> planned_stats() {
    std::vector<std::pair<std::string, std::string>> out;
    for (const auto stage : {"created", "buffered", "final"}) out.emplace_back("buffered_short_crc", stage);
    out.emplace_back("lease_abort", "final"); out.emplace_back("foreign", "final");
    out.emplace_back("lifetime", "before_wrapper_destruction");
    for (const auto name : corruption_names) out.emplace_back(name, "final");
    for (const auto& c : faults) {
        out.emplace_back(c.name, "before_writer_destruction"); out.emplace_back(c.name, "final");
    }
    for (const auto name : {"payload_prefix_failure", "repeated_eintr", "read_nonprogress", "read_error", "read_repeated_eintr"})
        out.emplace_back(name, "final");
    return out;
}
std::vector<std::string> make_check_names(std::string_view mode) {
    std::vector<std::string> out;
    auto add = [&](std::initializer_list<const char*> values) { for (const auto value : values) out.emplace_back(value); };
    if (mode == "horizon") {
        add({"horizon.exact_capacity"});
        for (std::uint64_t i = 1; i <= horizon_records; ++i) out.push_back("horizon.record." + std::to_string(i));
        add({"horizon.revisit_first", "horizon.revisit_last", "horizon.wire_and_io_closure",
             "horizon.first_after_wrapper_destruction", "horizon.last_after_wrapper_destruction",
             "horizon.post_destruction_io_closure"});
        return out;
    }
    add({"capacity_exact_formula"});
    for (const auto& c : invalid_policies()) {
        out.push_back(std::string(c.name) + ".typed"); out.push_back(std::string(c.name) + ".no_hook_or_file");
    }
    for (const std::string name : {"zero_store_identity", "zero_source_identity"}) {
        out.push_back(name + ".typed"); out.push_back(name + ".no_hook_or_file");
    }
    add({"existing_path.typed", "existing_path.unchanged", "buffered_short_crc.capacity",
         "buffered_short_crc.logical_before_flush", "buffered_short_crc.standard_crc",
         "buffered_short_crc.real_prefix", "buffered_short_crc.read", "buffered_short_crc.released",
         "lease_abort.writer_cap.typed", "lease_abort.writer_cap_no_attempt",
         "lease_abort.explicit_destructor_prefix", "lease_abort.payload_cap.typed",
         "lease_abort.payload_cap_prefix", "lease_abort.empty_sealed", "lease_abort.empty_commit",
         "lease_abort.empty_verified_and_overlap", "lease_abort.reader_cap.typed",
         "lease_abort.abandoned_read_unverified", "lease_abort.reader_released",
         "lease_abort.no_attempt_refund.typed", "lease_abort.final_counts",
         "lifetime.moved_store.typed", "lifetime.moved_writer.typed", "lifetime.exact_replay_after_later_head",
         "lifetime.changed_linkage.typed", "lifetime.stale_sibling.typed", "lifetime.foreign_reader.typed",
         "lifetime.foreign_commit.typed", "lifetime.empty_handle.typed", "lifetime.refusal_no_io",
         "lifetime.moved_reader.typed", "lifetime.empty_read_buffer.typed", "lifetime.reader_survives_wrapper",
         "lifetime.handle_survives_wrapper"});
    for (const std::string name : corruption_names) {
        out.push_back(name + ".typed"); out.push_back(name + ".fenced_again.typed");
        out.push_back(name + ".head_retained_and_lease_released");
    }
    for (const auto& c : faults) {
        const std::string name = c.name;
        out.push_back(name + ".typed"); out.push_back(name + ".fenced_unpublished");
        out.push_back(name + ".next_begin.typed"); out.push_back(name + ".destructor_releases");
    }
    add({"payload_prefix_failure.typed", "payload_prefix_failure.positive_three_bytes",
         "payload_prefix_failure.destructor_releases", "repeated_eintr.typed",
         "repeated_eintr.bounded_zero_progress", "repeated_eintr.lease_released"});
    for (const std::string name : {"read_nonprogress", "read_error", "read_repeated_eintr"}) {
        out.push_back(name + ".typed"); out.push_back(name + ".lease_released_and_bounded");
    }
    add({"controls.fixed_call_closure"});
    return out;
}

int controls(const std::filesystem::path& dir) {
    // A new directory is part of the guard, including on a failed first run.
    if (!std::filesystem::create_directory(dir)) throw std::runtime_error("controls require a new exclusive directory");
    Harness t("controls"); plan("controls");
    admission_controls(t, dir); buffered_control(t, dir); lease_abort_controls(t, dir);
    lifetime_commit_controls(t, dir); corruption_controls(t, dir); fault_controls(t, dir);
    t.check("controls.fixed_call_closure", t.checks == 127 && t.errors == 61 && t.cases == 39
        && t.stats_rows == 33 && t.calls.create == 39 && t.calls.required == 1
        && t.calls.begin == 38 && t.calls.append == 28 && t.calls.seal == 22
        && t.calls.abort == 1 && t.calls.commit == 15 && t.calls.open_reader == 20 && t.calls.read == 17);
    return t.finish();
}

int horizon(const std::filesystem::path& blob_path, const std::filesystem::path& path) {
    if (std::filesystem::file_size(blob_path) != horizon_payload)
        throw std::runtime_error("horizon requires the fixed 3069231-byte data-only frame");
    const Bytes blob = raw_read(blob_path, 0, static_cast<std::size_t>(horizon_payload));
    const auto expected_crc = crc(blob);
    Harness t("horizon"); plan("horizon");
    const auto p = policy(horizon_records, horizon_payload, horizon_buffer, 1, 1, 500000);
    std::uint64_t last_operation = 0;
    std::optional<Store> s(t.create("horizon", path, p, identity(), [&](const Operation& op) {
        last_operation = op.operation_number; return Directive{};
    }));
    t.check("horizon.exact_capacity", p.provisioned_bytes == horizon_extent
        && std::filesystem::file_size(path) == horizon_extent && s->stats().required_bytes == horizon_extent);
    std::vector<Handle> handles; handles.reserve(horizon_records);
    for (std::uint64_t i = 0; i < horizon_records; ++i) {
        auto writer = t.begin(*s);
        for (std::size_t at = 0; at < blob.size(); at += horizon_buffer)
            t.append(writer, std::span<const std::byte>(blob).subspan(at, std::min(horizon_buffer, blob.size() - at)));
        auto h = t.seal(writer); const auto result = t.commit(*s, h, {i, i, i + 1});
        const bool payload_equal = t.verify(h, blob);
        const auto state = s->stats();
        t.check("horizon.record." + std::to_string(i + 1), payload_equal && h.attempt() == i + 1
            && h.payload_bytes() == horizon_payload && h.checksum_crc64_ecma182() == expected_crc
            && !result.replayed && result.commit_sequence == i + 1 && state.committed_revision == i + 1
            && state.active_readers == 0 && state.active_writers == 0 && state.io_buffer_bytes_live == 0);
        handles.push_back(std::move(h));
        std::cout << "{\"type\":\"record\",\"index\":" << i + 1 << ",\"attempt\":" << handles.back().attempt()
            << ",\"payload_bytes\":" << handles.back().payload_bytes() << ",\"crc64\":"
            << handles.back().checksum_crc64_ecma182() << ",\"stats\":";
        stats_json(state); std::cout << "}\n";
    }
    t.check("horizon.revisit_first", t.verify(handles.front(), blob));
    t.check("horizon.revisit_last", t.verify(handles.back(), blob));
    const auto before = s->stats();
    constexpr std::uint64_t payload_io = (horizon_payload + horizon_buffer - 1) / horizon_buffer;
    constexpr std::uint64_t read_io = 3 + payload_io;
    constexpr std::uint64_t record_io = 6 + payload_io + read_io;
    t.check("horizon.wire_and_io_closure", before.payload_bytes_written == horizon_records * horizon_payload
        && before.payload_bytes_appended == horizon_records * horizon_payload
        && before.total_bytes_written == horizon_extent && before.attempts_started == horizon_records
        && before.sealed_attempts == horizon_records && before.committed_records == horizon_records
        && before.aborted_attempts == 0 && before.indeterminate_attempts == 0 && !before.fenced
        && before.total_bytes_read == (horizon_records + 2) * (512 + horizon_payload)
        && before.io_operations == 3 + horizon_records * record_io + 2 * read_io
        && before.io_buffer_bytes_peak == horizon_buffer && before.io_buffer_bytes_live == 0);
    t.stats("horizon", "before_wrapper_destruction", *s); s.reset();
    t.check("horizon.first_after_wrapper_destruction", t.verify(handles.front(), blob));
    t.check("horizon.last_after_wrapper_destruction", t.verify(handles.back(), blob));
    t.check("horizon.post_destruction_io_closure", last_operation == before.io_operations + 2 * read_io
        && t.checks == 1086 && t.errors == 0 && t.cases == 1 && t.stats_rows == 1
        && t.calls.create == 1 && t.calls.required == 0 && t.calls.begin == 1080
        && t.calls.append == 50760 && t.calls.seal == 1080 && t.calls.abort == 0
        && t.calls.commit == 1080 && t.calls.open_reader == 1084 && t.calls.read == 52032);
    long maximum_rss_kib = 0;
#ifdef __linux__
    struct rusage usage{};
    if (::getrusage(RUSAGE_SELF, &usage) != 0) throw std::runtime_error("getrusage failed");
    maximum_rss_kib = usage.ru_maxrss;
#endif
    std::cout << "{\"type\":\"horizon_resources\",\"payload_bytes\":" << horizon_payload
        << ",\"records\":" << horizon_records << ",\"required_bytes\":" << horizon_extent
        << ",\"actual_file_bytes\":" << std::filesystem::file_size(path)
        << ",\"input_blob_bytes_retained\":" << blob.size() << ",\"handle_count\":" << handles.size()
        << ",\"handle_vector_payload_bytes\":" << handles.capacity() * sizeof(Handle)
        << ",\"store_index_payload_bytes\":" << before.index_payload_bytes
        << ",\"store_io_buffer_peak_bytes\":" << before.io_buffer_bytes_peak
        << ",\"driver_read_buffer_bytes\":" << horizon_buffer
        << ",\"ru_maxrss_kib\":" << maximum_rss_kib
        << ",\"last_observed_stats_io_operations\":" << before.io_operations
        << ",\"final_hook_operation_number\":" << last_operation
        << ",\"post_wrapper_read_bytes\":" << 2 * (512 + horizon_payload)
        << ",\"final_read_bytes_derived\":" << before.total_bytes_read + 2 * (512 + horizon_payload)
        << ",\"crc64\":" << expected_crc << ",\"rss_is_observed_not_a_cap\":true}\n";
    return t.finish();
}

void inventory() {
    // Pure metadata: no Store method, codec, model, filesystem or producer call.
    plan("inventory");
    std::cout << "{\"type\":\"inventory\",\"default_execution\":false,\"store_calls\":0,"
        "\"controls_groups\":[\"admission\",\"buffered_short_crc\",\"lease_abort\",\"lifetime_commit\","
        "\"corruption\",\"faults\"],\"cases\":[";
    bool first = true;
    for (const auto& c : planned_cases()) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\"name\":"; quote(c.name); std::cout << ",\"relative_path\":"; quote(c.name + ".bin");
        std::cout << ",\"policy\":"; policy_json(c.policy);
        std::cout << ",\"identity\":"; identity_json(c.identity); std::cout << '}';
    }
    std::cout << "],\"errors\":["; first = true;
    for (const auto& e : planned_errors()) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\"name\":"; quote(e.name); std::cout << ",\"code\":"; quote(e.code);
        std::cout << ",\"fenced\":" << e.fenced << ",\"commit_indeterminate\":" << e.ambiguous << '}';
    }
    std::cout << "],\"stats_stages\":["; first = true;
    for (const auto& [name, stage] : planned_stats()) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << "{\"case\":"; quote(name); std::cout << ",\"stage\":"; quote(stage); std::cout << '}';
    }
    std::cout << "],\"check_names\":["; first = true;
    for (const auto& name : make_check_names("controls")) {
        if (!first) std::cout << ',';
        first = false; quote(name);
    }
    std::cout << "],\"expected_controls\":{\"checks\":128,\"failures\":0,\"errors\":61,\"cases\":39,"
        "\"stats_rows\":33,\"calls\":{\"create\":39,\"required\":1,\"begin\":38,\"append\":28,"
        "\"seal\":22,\"abort\":1,\"commit\":15,\"open_reader\":20,\"read\":17}}";
    std::cout << ",\"horizon\":{\"payload_bytes\":" << horizon_payload
        << ",\"records\":" << horizon_records << ",\"policy\":";
    policy_json(policy(horizon_records, horizon_payload, horizon_buffer, 1, 1, 500000));
    std::cout << ",\"identity\":"; identity_json(identity());
    std::cout << ",\"check_names\":["; first = true;
    for (const auto& name : make_check_names("horizon")) {
        if (!first) std::cout << ',';
        first = false; quote(name);
    }
    std::cout << "],\"expected_summary\":{\"checks\":1087,\"failures\":0,\"errors\":0,\"cases\":1,"
        "\"stats_rows\":1,\"calls\":{\"create\":1,\"required\":0,\"begin\":1080,\"append\":50760,"
        "\"seal\":1080,\"abort\":0,\"commit\":1080,\"open_reader\":1084,\"read\":52032}},"
        "\"repeated_input_is_data_only\":true,\"compression\":false}}\n";
}
} // namespace

int main(int argc, char** argv) {
    std::cout << std::boolalpha;
    try {
        if (argc == 2 && std::string_view(argv[1]) == "--inventory") { inventory(); return 0; }
        if (argc == 3 && std::string_view(argv[1]) == "--controls") return controls(argv[2]);
        if (argc == 4 && std::string_view(argv[1]) == "--horizon") return horizon(argv[2], argv[3]);
        std::cerr << "explicit --inventory, --controls NEW_DIR, or --horizon BLOB NEW_FILE required\n";
        return 2;
    } catch (const std::exception& e) {
        std::cout << "{\"type\":\"fatal\",\"detail\":"; quote(e.what()); std::cout << "}\n";
        return 1;
    }
}
