#include "c_api_v4_test_support.hpp"
#include "c_api_v1_layout.hpp"

#include <chrono>
#include <fstream>
#include <iostream>
#include <limits>
#include <type_traits>

namespace {
using namespace v4_test;
using magic_geo::CConfigV4;

static_assert(std::is_standard_layout_v<CConfigV4>);
#define TYPE_CHECK(type, name, offset) static_assert(std::is_same_v<decltype(CConfigV4::name), type>);
MAGIC_GEO_V4_FIELDS(TYPE_CHECK)
#undef TYPE_CHECK
#if INTPTR_MAX == INT64_MAX
static_assert(sizeof(CConfigV4) == 312 && alignof(CConfigV4) == 8);
static_assert(sizeof(magic_geo::CConfig) == 304 && sizeof(magic_geo::CConfigV2) == 312 && sizeof(magic_geo::CConfigV3) == 320);
static_assert(offsetof(magic_geo::CConfigV2, base) == 0 && offsetof(magic_geo::CConfigV2, compute_backend) == 304 && offsetof(magic_geo::CConfigV2, opencl_prefer_gpu) == 308);
static_assert(offsetof(magic_geo::CConfigV3, base) == 0 && offsetof(magic_geo::CConfigV3, maturation_timestep_ma) == 312);
#define OFFSET_CHECK(type, name, offset) static_assert(offsetof(CConfigV4, name) == offset);
MAGIC_GEO_V4_FIELDS(OFFSET_CHECK)
#undef OFFSET_CHECK
#define OLD_OFFSET_CHECK(type, name, offset) static_assert(offsetof(magic_geo::CConfig, name) == offset); static_assert(std::is_same_v<decltype(magic_geo::CConfig::name), type>);
MAGIC_GEO_V1_CONFIG_FIELD_LIST(OLD_OFFSET_CHECK)
#undef OLD_OFFSET_CHECK
#endif
static_assert(noexcept(magic_geo_generate_json_v4(nullptr)));
static_assert(noexcept(magic_geo_generate_geo_json_v4(nullptr)));
static_assert(noexcept(magic_geo_generate_msgpack_v4(nullptr, nullptr)));
static_assert(noexcept(magic_geo_generate_geo_msgpack_v4(nullptr, nullptr)));

struct Inputs : magic_geo::Params {
    int compute_backend = 1;
    bool opencl_prefer_gpu = false;
};

CConfigV4 configuration() {
    static const Inputs defaults;
    CConfigV4 cfg{};
    const auto copy = []<class A, class B>(A& target, const B& value) {
        if constexpr (std::is_same_v<A, const char*>) target = value.c_str();
        else target = value;
    };
#define COPY_DEFAULT(type, name, offset) copy(cfg.name, defaults.name);
    MAGIC_GEO_V4_FIELDS(COPY_DEFAULT)
#undef COPY_DEFAULT
    cfg.name = "c_api_v4_\"seasonal\"_é";
    cfg.cell_count = 128;
    cfg.plate_count = 8;
    cfg.erosion_iterations = 0;
    cfg.threads = 1;
    cfg.float_precision = 8;
    return cfg;
}

Inputs converted(const CConfigV4& cfg) {
    Inputs result;
    static_cast<magic_geo::Params&>(result) = magic_geo::params_from_c_config(cfg);
    const auto compute = magic_geo::compute_options_from_c_config(cfg);
    result.compute_backend = compute.compute_backend;
    result.opencl_prefer_gpu = compute.opencl_prefer_gpu;
    return result;
}

void every_field_conversion() {
    auto cfg = configuration();
    const auto distinctive = []<class T>(T& field, int offset) {
        if constexpr (std::is_same_v<T, const char*>) field = "distinctive V4 name";
        else if constexpr (std::is_floating_point_v<T>) field = offset + 0.125;
        else field = offset + 101;
    };
#define DISTINCTIVE(type, name, offset) distinctive(cfg.name, offset);
    MAGIC_GEO_V4_FIELDS(DISTINCTIVE)
#undef DISTINCTIVE
    cfg.seed = std::numeric_limits<std::uint64_t>::max();
    cfg.preserve_geologic_depressions = 1;
    cfg.include_cells = 0;
    cfg.opencl_prefer_gpu = 1;
    auto actual = converted(cfg);
#define VERIFY(type, name, offset) require(actual.name == cfg.name, "V4 conversion: " #name);
    MAGIC_GEO_V4_FIELDS(VERIFY)
#undef VERIFY
    require(actual.temperature_model == magic_geo::ClimateTemperatureModel::prescribed_seasonal, "V4 did not select seasonal model");
    // Conversion must preserve full-width controls; scientific validation,
    // rather than silent narrowing/wrapping, rejects their invalid domains.
    cfg.cell_count = std::numeric_limits<std::int32_t>::min();
    cfg.threads = std::numeric_limits<std::int32_t>::max();
    cfg.compute_backend = std::numeric_limits<std::int32_t>::min();
    cfg.preserve_geologic_depressions = 0; cfg.include_cells = 1; cfg.opencl_prefer_gpu = 0;
    actual = converted(cfg);
    require(actual.cell_count == cfg.cell_count && actual.threads == cfg.threads && actual.compute_backend == cfg.compute_backend, "integer width changed");
    require(!actual.preserve_geologic_depressions && actual.include_cells && !actual.opencl_prefer_gpu, "opposite flag values changed");
    cfg.name = nullptr;
    require(converted(cfg).name == "world", "null name fallback changed");
    char name[] = "owned name"; cfg.name = name; actual = converted(cfg); name[0] = 'X';
    require(actual.name == "owned name", "V4 borrowed the caller's mutable name");
    magic_geo::CConfig old{}; old.include_cells = -7; old.preserve_geologic_depressions = 2;
    const auto old_params = magic_geo::params_from_c_config(old);
    require(old_params.temperature_model == magic_geo::ClimateTemperatureModel::legacy_empirical && old_params.include_cells && old_params.preserve_geologic_depressions, "V1 semantics changed");
    magic_geo::CConfigV3 v3{}; v3.base.opencl_prefer_gpu = -1;
    require(magic_geo::params_from_c_config(v3).temperature_model == magic_geo::ClimateTemperatureModel::legacy_empirical && magic_geo::compute_options_from_c_config(v3.base).opencl_prefer_gpu, "V2/V3 semantics changed");
}

Value consume_json(const char* raw, std::string* text = nullptr) {
    require(raw != nullptr, "unexpected null JSON result");
    std::string owned;
    try { owned = raw; } catch (...) { magic_geo_free_string(raw); throw; }
    magic_geo_free_string(raw);
    if (text) *text = owned;
    return JsonReader(owned).read();
}
Value consume_binary(const std::uint8_t* raw, std::size_t size) {
    require(raw != nullptr && size != 0, "unexpected null/empty MessagePack result");
    std::vector<std::uint8_t> owned;
    try { owned.assign(raw, raw + size); } catch (...) { magic_geo_free_buffer(raw); throw; }
    magic_geo_free_buffer(raw);
    return MessagePackReader(owned).read();
}

void error_routes() {
    const auto json_routes = {magic_geo_generate_json_v4, magic_geo_generate_geo_json_v4};
    const auto binary_routes = {magic_geo_generate_msgpack_v4, magic_geo_generate_geo_msgpack_v4};
    const auto rejects = [&](const CConfigV4* cfg, std::string_view fragment) {
        for (auto route : json_routes) require(consume_json(route(cfg)).at("error").string().find(fragment) != std::string::npos, "wrong JSON V4 error");
        for (auto route : binary_routes) { std::size_t size = 12345; const auto* raw = route(cfg, &size); require(consume_binary(raw, size).at("error").string().find(fragment) != std::string::npos, "wrong MessagePack V4 error"); }
    };
    rejects(nullptr, "null config pointer");
    // If a size is absent, even an unreadable configuration pointer is ignored.
    const auto* unreadable = reinterpret_cast<const CConfigV4*>(std::uintptr_t{1});
    for (auto route : binary_routes) require(route(unreadable, nullptr) == nullptr, "null size pointer inspected config");
    for (auto member : {&CConfigV4::preserve_geologic_depressions, &CConfigV4::include_cells, &CConfigV4::opencl_prefer_gpu}) {
        for (int bad : {-1, 2, std::numeric_limits<std::int32_t>::max()}) { auto cfg = configuration(); cfg.*member = bad; rejects(&cfg, "must be exactly 0 or 1 in CConfigV4"); }
    }
    for (double bad : {-1.0, std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity()}) {
        auto cfg = configuration(); cfg.reference_infrared_optical_depth = bad; rejects(&cfg, "reference_infrared_optical_depth");
    }
    for (double allowed : {0.0, std::numeric_limits<double>::max()}) {
        auto cfg = configuration(); cfg.reference_infrared_optical_depth = allowed; cfg.cell_count = 0;
        rejects(&cfg, "cell_count");
    }
    auto cfg = configuration(); cfg.months = 11; rejects(&cfg, "months");
    cfg = configuration(); cfg.compute_backend = 99; rejects(&cfg, "compute_backend");
    cfg = configuration(); cfg.maturation_timestep_ma = 0; rejects(&cfg, "maturation_timestep_ma");
    magic_geo_free_string(nullptr); magic_geo_free_buffer(nullptr);
}

void energy_identity(const Value& world) {
    require(world.at("schema_version").number() == 2, "wrong world schema");
    require(world.at("climate_model").at("model_type").string() == "prescribed_seasonal_surface_energy_v1", "V4 emitted empirical model");
    const auto& energy = world.at("climate_energy_model");
    require(energy.at("model").string() == "native_prescribed_seasonal_energy_v1", "missing native energy identity");
    require(energy.at("budget_schema_version").number() == 1, "wrong budget schema");
    require(world.at("climate_energy_forcing_intervals").array().size() >= 360, "missing orbital forcing records");
    require(!world.at("climate_energy_transport_edges").array().empty(), "missing transport edges");
    require(energy.at("ownership").string() == "native_temperature_producer", "wrong budget ownership");
    const auto& records = world.at("climate_energy_balance_records").array();
    require(records.size() == 128 && world.at("cells").array().size() == 128, "missing seasonal columns");
    for (const auto& record : records) {
        require(record.at("monthly_mean_temperature_k").array().size() == 12, "missing accepted monthly temperatures");
        const auto& asr = record.at("monthly_absorbed_shortwave_w_m2").array();
        const auto& olr = record.at("monthly_emitted_longwave_w_m2").array();
        const auto& heat = record.at("monthly_horizontal_heat_convergence_w_m2").array();
        const auto& storage = record.at("monthly_heat_storage_tendency_w_m2").array();
        const auto& residual = record.at("monthly_balance_residual_w_m2").array();
        const auto& tolerance = record.at("monthly_balance_tolerance_w_m2").array();
        require(asr.size() == 12 && olr.size() == 12 && heat.size() == 12 && storage.size() == 12 && residual.size() == 12 && tolerance.size() == 12, "incomplete monthly ledger");
        for (std::size_t m = 0; m < 12; ++m) {
            const double recomputed = storage[m].number() - asr[m].number() + olr[m].number() - heat[m].number();
            require(std::abs(recomputed - residual[m].number()) < 1e-9, "decoded monthly ledger changed");
            require(std::abs(residual[m].number()) <= tolerance[m].number(), "accepted monthly ledger failed tolerance");
        }
    }
}

void four_success_routes(const char* artifact) {
    const auto cfg = configuration();
    std::string json;
    const auto full = consume_json(magic_geo_generate_json_v4(&cfg), &json);
    energy_identity(full);
    if (artifact) { std::ofstream out(artifact); out << json; require(out.good(), "could not write V4 artifact"); }
    const auto geo = consume_json(magic_geo_generate_geo_json_v4(&cfg)); energy_identity(geo);
    std::size_t size = 987;
    const auto* raw = magic_geo_generate_msgpack_v4(&cfg, &size);
    const auto full_binary = consume_binary(raw, size); energy_identity(full_binary);
    size = 987; raw = magic_geo_generate_geo_msgpack_v4(&cfg, &size);
    const auto geo_binary = consume_binary(raw, size); energy_identity(geo_binary);
    for (auto key : {"climate_model", "climate_energy_model", "climate_energy_forcing_intervals", "climate_energy_transport_edges", "climate_energy_balance_records", "planet_parameters"}) {
        require(full.at(key) == geo.at(key), std::string("full/geography authoritative mismatch: ") + key);
        require(full.at(key) == full_binary.at(key), std::string("full JSON/MessagePack mismatch: ") + key);
        require(geo.at(key) == geo_binary.at(key), std::string("geography JSON/MessagePack mismatch: ") + key);
    }
    require(full.at("cells") == full_binary.at("cells") && geo.at("cells") == geo_binary.at("cells"), "decoded cell fields changed across transport");
}
}  // namespace

int main(int argc, char** argv) {
    try {
        require(argc <= 2, "usage: magic_geo_c_api_v4_test [artifact.json]");
        const auto start = std::chrono::steady_clock::now();
        every_field_conversion(); error_routes(); four_success_routes(argc == 2 ? argv[1] : nullptr);
        std::cout << "V4 layout, conversions, errors and four decoded seasonal routes passed in "
                  << std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count() << " s\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
