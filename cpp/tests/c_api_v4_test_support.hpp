#pragma once

#include "magic_geo/native.hpp"

#include <bit>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <map>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

// Independent layout inventory, including all 43 published fields. Keep the
// offsets explicit: neither the binding nor the production adapter generates it.
#define MAGIC_GEO_V4_FIELDS(X) \
    X(std::uint64_t, seed, 0) \
    X(const char*, name, 8) \
    X(double, radius_km, 16) \
    X(double, gravity_g, 24) \
    X(double, day_length_hours, 32) \
    X(double, axial_tilt_deg, 40) \
    X(double, orbital_eccentricity, 48) \
    X(double, stellar_luminosity, 56) \
    X(double, atmosphere_pressure_bar, 64) \
    X(double, greenhouse_factor, 72) \
    X(double, ocean_fraction_target, 80) \
    X(double, ocean_water_inventory_km3, 88) \
    X(double, internal_heat, 96) \
    X(double, geological_age_ga, 104) \
    X(std::int32_t, cell_count, 112) \
    X(std::int32_t, mesh_backend, 116) \
    X(std::int32_t, neighbor_count, 120) \
    X(std::int32_t, plate_count, 124) \
    X(double, continental_plate_fraction, 128) \
    X(double, continental_crust_fraction_target, 136) \
    X(double, min_angular_speed, 144) \
    X(double, max_angular_speed, 152) \
    X(std::int32_t, boundary_smoothing_steps, 160) \
    X(double, plate_motion_scale_deg_per_step, 168) \
    X(double, oceanic_crust_aging_ma_per_step, 176) \
    X(std::int32_t, months, 184) \
    X(double, reference_infrared_optical_depth, 192) \
    X(double, precipitation_scale, 200) \
    X(double, subtropical_drying_strength, 208) \
    X(std::int32_t, preserve_geologic_depressions, 216) \
    X(double, river_percentile, 224) \
    X(std::int32_t, erosion_iterations, 232) \
    X(double, stream_power_coefficient, 240) \
    X(double, drainage_exponent, 248) \
    X(double, slope_exponent, 256) \
    X(double, hillslope_diffusion, 264) \
    X(double, tectonic_uplift_scale, 272) \
    X(std::int32_t, threads, 280) \
    X(std::int32_t, include_cells, 284) \
    X(std::int32_t, float_precision, 288) \
    X(double, maturation_timestep_ma, 296) \
    X(std::int32_t, compute_backend, 304) \
    X(std::int32_t, opencl_prefer_gpu, 308)

namespace v4_test {
inline void require(bool condition, std::string_view message) {
    if (!condition) throw std::runtime_error(std::string(message));
}

// Small independent readers for the finite JSON/MessagePack types the native
// writer emits. Maps compare by key, and integer/double encodings compare by
// their decoded binary64 value when their wire types differ.
struct Value {
    using Array = std::vector<Value>;
    using Map = std::map<std::string, Value>;
    std::variant<std::nullptr_t, bool, std::uint64_t, std::int64_t, double, std::string, Array, Map> data;
    const Value& at(const std::string& key) const { return std::get<Map>(data).at(key); }
    const Array& array() const { return std::get<Array>(data); }
    const std::string& string() const { return std::get<std::string>(data); }
    bool numeric() const { return data.index() >= 2 && data.index() <= 4; }
    double number() const {
        if (auto v = std::get_if<double>(&data)) return *v;
        if (auto v = std::get_if<std::uint64_t>(&data)) return static_cast<double>(*v);
        return static_cast<double>(std::get<std::int64_t>(data));
    }
    bool operator==(const Value& other) const {
        if (numeric() && other.numeric() && data.index() != other.data.index()) return number() == other.number();
        return data == other.data;
    }
};

class JsonReader {
    std::string_view text_;
    std::size_t pos_ = 0;
    char take() { require(pos_ < text_.size(), "truncated JSON"); return text_[pos_++]; }
    void spaces() { while (pos_ < text_.size() && std::string_view(" \n\r\t").find(text_[pos_]) != std::string_view::npos) ++pos_; }
    std::string string() {
        require(take() == '"', "expected JSON string");
        std::string result;
        for (;;) {
            char c = take();
            if (c == '"') return result;
            if (c == '\\') {
                c = take();
                switch (c) {
                    case '"': case '\\': case '/': break;
                    case 'b': c = '\b'; break; case 'f': c = '\f'; break;
                    case 'n': c = '\n'; break; case 'r': c = '\r'; break; case 't': c = '\t'; break;
                    case 'u': {
                        unsigned code = 0;
                        for (int i = 0; i < 4; ++i) {
                            const char digit = take();
                            const auto p = std::string_view("0123456789abcdef").find(digit);
                            require(p != std::string_view::npos, "unsupported JSON unicode escape");
                            code = (code << 4U) | static_cast<unsigned>(p);
                        }
                        if (code < 0x80) result += static_cast<char>(code);
                        else if (code < 0x800) { result += static_cast<char>(0xc0U | (code >> 6U)); result += static_cast<char>(0x80U | (code & 63U)); }
                        else { require(code < 0xd800 || code > 0xdfff, "unexpected surrogate in native test data"); result += static_cast<char>(0xe0U | (code >> 12U)); result += static_cast<char>(0x80U | ((code >> 6U) & 63U)); result += static_cast<char>(0x80U | (code & 63U)); }
                        continue;
                    }
                    default: throw std::runtime_error("invalid JSON escape");
                }
            }
            result += c;
        }
    }
    Value value() {
        spaces(); require(pos_ < text_.size(), "missing JSON value");
        if (text_[pos_] == '"') return {string()};
        if (text_[pos_] == '{') {
            ++pos_; Value::Map map; spaces();
            if (text_[pos_] == '}') { ++pos_; return {map}; }
            for (;;) {
                spaces(); auto key = string(); spaces(); require(take() == ':', "missing JSON colon");
                require(map.emplace(std::move(key), value()).second, "duplicate JSON key"); spaces();
                const char c = take(); if (c == '}') return {map}; require(c == ',', "missing JSON comma");
            }
        }
        if (text_[pos_] == '[') {
            ++pos_; Value::Array array; spaces();
            if (text_[pos_] == ']') { ++pos_; return {array}; }
            for (;;) { array.push_back(value()); spaces(); const char c = take(); if (c == ']') return {array}; require(c == ',', "missing JSON comma"); }
        }
        for (auto literal : {std::string_view("true"), std::string_view("false"), std::string_view("null")}) {
            if (text_.substr(pos_, literal.size()) == literal) {
                pos_ += literal.size(); if (literal == "null") return {nullptr}; return {literal == "true"};
            }
        }
        const auto start = pos_;
        while (pos_ < text_.size() && std::string_view("0123456789.eE+-").find(text_[pos_]) != std::string_view::npos) ++pos_;
        const auto token = text_.substr(start, pos_ - start);
        require(!token.empty(), "invalid JSON number");
        if (token.find_first_of(".eE") != std::string_view::npos) {
            double n = 0; const auto r = std::from_chars(token.data(), token.data() + token.size(), n);
            require(r.ec == std::errc{} && r.ptr == token.data() + token.size() && std::isfinite(n), "invalid JSON double"); return {n};
        }
        if (token.front() == '-') { std::int64_t n = 0; const auto r = std::from_chars(token.data(), token.data() + token.size(), n); require(r.ec == std::errc{} && r.ptr == token.data() + token.size(), "invalid JSON signed integer"); return {n}; }
        std::uint64_t n = 0; const auto r = std::from_chars(token.data(), token.data() + token.size(), n); require(r.ec == std::errc{} && r.ptr == token.data() + token.size(), "invalid JSON unsigned integer"); return {n};
    }
public:
    explicit JsonReader(std::string_view text) : text_(text) {}
    Value read() { auto result = value(); spaces(); require(pos_ == text_.size(), "trailing JSON input"); return result; }
};

class MessagePackReader {
    const std::vector<std::uint8_t>& bytes_;
    std::size_t pos_ = 0;
    std::uint64_t unsigned_n(unsigned n) { require(n <= bytes_.size() - pos_, "truncated MessagePack"); std::uint64_t result = 0; while (n--) result = (result << 8U) | bytes_[pos_++]; return result; }
    std::string string(std::size_t n) { require(n <= bytes_.size() - pos_, "truncated MessagePack string"); std::string result(reinterpret_cast<const char*>(bytes_.data() + pos_), n); pos_ += n; return result; }
    Value array(std::size_t n) { Value::Array result; while (n--) result.push_back(value()); return {result}; }
    Value map(std::size_t n) { Value::Map result; while (n--) { auto key = value().string(); require(result.emplace(std::move(key), value()).second, "duplicate MessagePack key"); } return {result}; }
    Value value() {
        const auto code = unsigned_n(1);
        if (code <= 0x7f) return {code};
        if (code >= 0xe0) return {static_cast<std::int64_t>(code) - 256};
        if ((code & 0xe0) == 0xa0) return {string(code & 31U)};
        if ((code & 0xf0) == 0x90) return array(code & 15U);
        if ((code & 0xf0) == 0x80) return map(code & 15U);
        switch (code) {
            case 0xc0: return {nullptr}; case 0xc2: return {false}; case 0xc3: return {true};
            case 0xcc: return {unsigned_n(1)}; case 0xcd: return {unsigned_n(2)}; case 0xce: return {unsigned_n(4)}; case 0xcf: return {unsigned_n(8)};
            case 0xd0: { auto n = unsigned_n(1); return {static_cast<std::int64_t>(n < 128 ? n : n - 256)}; }
            case 0xd1: { auto n = unsigned_n(2); return {static_cast<std::int64_t>(n < 32768 ? n : n - 65536)}; }
            case 0xd2: { auto n = unsigned_n(4); return {static_cast<std::int64_t>(n < 2147483648ULL ? n : n - 4294967296ULL)}; }
            case 0xd3: return {std::bit_cast<std::int64_t>(unsigned_n(8))};
            case 0xcb: { const auto n = std::bit_cast<double>(unsigned_n(8)); require(std::isfinite(n), "nonfinite MessagePack double"); return {n}; }
            case 0xd9: return {string(unsigned_n(1))}; case 0xda: return {string(unsigned_n(2))}; case 0xdb: return {string(unsigned_n(4))};
            case 0xdc: return array(unsigned_n(2)); case 0xdd: return array(unsigned_n(4));
            case 0xde: return map(unsigned_n(2)); case 0xdf: return map(unsigned_n(4));
            default: throw std::runtime_error("unexpected native MessagePack type");
        }
    }
public:
    explicit MessagePackReader(const std::vector<std::uint8_t>& bytes) : bytes_(bytes) {}
    Value read() { auto result = value(); require(pos_ == bytes_.size(), "trailing MessagePack input"); return result; }
};
}  // namespace v4_test
