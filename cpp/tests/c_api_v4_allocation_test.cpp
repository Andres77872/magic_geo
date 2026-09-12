#include "c_api_v4_test_support.hpp"

#include "engine/messagepack.hpp"

#include <cstdlib>
#include <iostream>
#include <new>

// This target compiles the unchanged C boundary with tiny generator stubs.
// Fault injection exists only in this executable: there is no mutable failure
// switch or alternate allocator in the production library.
namespace {
bool fail_new = false;
bool fail_malloc = false;
std::size_t failed_malloc_calls = 0;
enum class Fault { none, standard_exception, unknown_exception, bad_alloc, error_format_bad_alloc, empty_binary };
Fault fault = Fault::none;
int generation_calls = 0;
struct Diagnostic : std::exception {
    const char* what() const noexcept override { return "driver \"quoted\"\ncontrol\x01 invalid UTF-8: \xff"; }
};
void generation() {
    ++generation_calls;
    switch (fault) {
        case Fault::standard_exception: throw Diagnostic{};
        case Fault::unknown_exception: throw 17;
        case Fault::bad_alloc: throw std::bad_alloc{};
        case Fault::error_format_bad_alloc: fail_new = true; throw Diagnostic{};
        default: break;
    }
}
}  // namespace

#ifdef MAGIC_GEO_TEST_WRAP_MALLOC
extern "C" void* __real_malloc(std::size_t);
extern "C" void* __wrap_malloc(std::size_t size) {
    if (fail_malloc) { ++failed_malloc_calls; return nullptr; }
    return __real_malloc(size);
}
#endif
void* operator new(std::size_t size) {
    if (fail_new) throw std::bad_alloc{};
#ifdef MAGIC_GEO_TEST_WRAP_MALLOC
    void* p = __real_malloc(size == 0 ? 1 : size);
#else
    void* p = std::malloc(size == 0 ? 1 : size);
#endif
    if (!p) throw std::bad_alloc{};
    return p;
}
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* ptr) noexcept { std::free(ptr); }
void operator delete[](void* ptr) noexcept { std::free(ptr); }
void operator delete(void* ptr, std::size_t) noexcept { std::free(ptr); }
void operator delete[](void* ptr, std::size_t) noexcept { std::free(ptr); }

namespace magic_geo {
std::string backend_info_json() { return "{}"; }
std::string generate_world_json(const Params&) { generation(); return "{\"result\":\"full\"}"; }
std::string generate_world_json(const Params&, const ComputeOptions&) { generation(); return "{\"result\":\"full\"}"; }
std::string generate_geo_world_json(const Params&, const ComputeOptions&) { generation(); return "{\"result\":\"geo\"}"; }
std::vector<std::uint8_t> generate_world_msgpack(const Params&, const ComputeOptions&) {
    generation(); if (fault == Fault::empty_binary) return {};
    return detail::json_to_messagepack("{\"result\":\"full\"}");
}
std::vector<std::uint8_t> generate_geo_world_msgpack(const Params&, const ComputeOptions&) {
    generation(); if (fault == Fault::empty_binary) return {};
    return detail::json_to_messagepack("{\"result\":\"geo\"}");
}
}  // namespace magic_geo

int main() {
    using namespace v4_test;
    try {
        magic_geo::CConfigV4 cfg{};
        cfg.name = "allocation test";
        const auto json_routes = {magic_geo_generate_json_v4, magic_geo_generate_geo_json_v4};
        const auto binary_routes = {magic_geo_generate_msgpack_v4, magic_geo_generate_geo_msgpack_v4};
        // The full/geography generators deliberately return different values,
        // so forwarding both symbols to one generator cannot pass this test.
        int route_index = 0;
        for (auto route : json_routes) {
            const auto* raw = route(&cfg); require(raw != nullptr, "missing JSON stub result");
            std::string text(raw); magic_geo_free_string(raw);
            require(JsonReader(text).read().at("result").string() == (route_index++ == 0 ? "full" : "geo"), "incorrect JSON generator dispatch");
        }
        route_index = 0;
        for (auto route : binary_routes) {
            std::size_t size = 123; const auto* raw = route(&cfg, &size); require(raw && size, "missing binary stub result");
            std::vector<std::uint8_t> bytes(raw, raw + size); magic_geo_free_buffer(raw);
            require(MessagePackReader(bytes).read().at("result").string() == (route_index++ == 0 ? "full" : "geo"), "incorrect binary generator dispatch");
        }
        for (auto scenario : {Fault::standard_exception, Fault::unknown_exception, Fault::bad_alloc}) {
            fault = scenario;
            for (auto route : json_routes) {
                const char* raw = route(&cfg); require(raw != nullptr, "JSON error was not allocated");
                std::string text(raw); magic_geo_free_string(raw);
                const auto value = JsonReader(text).read();
                const auto& message = value.at("error").string();
                require(!message.empty(), "missing JSON error");
                if (scenario == Fault::standard_exception) require(message == std::string("driver \"quoted\"\ncontrol\x01 invalid UTF-8: ") + "\xef\xbf\xbd", "JSON diagnostic sanitation failed");
            }
            for (auto route : binary_routes) {
                std::size_t size = 123; const auto* raw = route(&cfg, &size);
                require(raw && size, "MessagePack error was not allocated");
                std::vector<std::uint8_t> bytes(raw, raw + size); magic_geo_free_buffer(raw);
                const auto value = MessagePackReader(bytes).read();
                const auto& message = value.at("error").string();
                require(!message.empty(), "missing MessagePack error");
                if (scenario == Fault::standard_exception) require(message == std::string("driver \"quoted\"\ncontrol\x01 invalid UTF-8: ") + "\xef\xbf\xbd", "MessagePack diagnostic sanitation failed");
            }
        }
        fault = Fault::error_format_bad_alloc;
        for (auto route : json_routes) {
            const char* raw = route(&cfg); fail_new = false;
            require(raw == nullptr, "JSON error-format allocation failure escaped or returned output");
        }
        for (auto route : binary_routes) {
            std::size_t size = 123; const auto* raw = route(&cfg, &size); fail_new = false;
            require(raw == nullptr && size == 0, "MessagePack error-format allocation failure escaped or retained size");
        }
        // Fail allocations before the wrapper can build an error, including
        // the null-configuration branch which does not invoke any generator.
        for (auto route : json_routes) {
            fail_new = true; const auto* raw = route(nullptr); fail_new = false;
            require(raw == nullptr, "null-config JSON allocation failure was not contained");
        }
        for (auto route : binary_routes) {
            std::size_t size = 123; fail_new = true; const auto* raw = route(nullptr, &size); fail_new = false;
            require(raw == nullptr && size == 0, "null-config binary allocation failure was not contained");
        }
        cfg.name = "a deliberately long borrowed name requiring an owning allocation";
        for (auto route : json_routes) {
            fail_new = true; const auto* raw = route(&cfg); fail_new = false;
            require(raw == nullptr, "JSON input-copy allocation failure was not contained");
        }
        for (auto route : binary_routes) {
            std::size_t size = 123; fail_new = true; const auto* raw = route(&cfg, &size); fail_new = false;
            require(raw == nullptr && size == 0, "binary input-copy allocation failure was not contained");
        }
        cfg.name = "allocation test";
#ifdef MAGIC_GEO_TEST_WRAP_MALLOC
        for (auto scenario : {Fault::none, Fault::standard_exception}) {
            fault = scenario;
            for (auto route : json_routes) {
                const auto before = failed_malloc_calls; fail_malloc = true;
                const auto* raw = route(&cfg); fail_malloc = false;
                require(raw == nullptr && failed_malloc_calls == before + 1, "JSON result/error copy allocation failure was not contained");
            }
            for (auto route : binary_routes) {
                std::size_t size = 123; const auto before = failed_malloc_calls; fail_malloc = true;
                const auto* raw = route(&cfg, &size); fail_malloc = false;
                require(raw == nullptr && size == 0 && failed_malloc_calls == before + 1, "binary result/error copy allocation failure retained size");
            }
        }
#endif
        fault = Fault::empty_binary;
        for (auto route : binary_routes) {
            std::size_t size = 123; const auto* raw = route(&cfg, &size);
            require(raw != nullptr && size == 0, "empty binary ownership changed"); magic_geo_free_buffer(raw);
        }
        const int before = generation_calls;
        for (auto route : binary_routes) require(route(reinterpret_cast<const magic_geo::CConfigV4*>(std::uintptr_t{1}), nullptr) == nullptr, "missing-size fast path failed");
        require(generation_calls == before, "missing size invoked generator");
        std::cout << "V4 exception and allocation boundaries passed\n";
        return 0;
    } catch (const std::exception& error) {
        fail_new = false; fail_malloc = false;
        std::cerr << error.what() << '\n'; return 1;
    }
}
