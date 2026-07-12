#include "engine/internal.hpp"
#include "engine/messagepack.hpp"

#include <bit>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using namespace magic_geo::detail;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "check failed at line " << __LINE__ << ": "          \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

bool strictly_positive_area_arrays_round_trip_binary64() {
    const std::vector<double> values = {
        std::numeric_limits<double>::denorm_min(),
        4.0e-18,
        std::numeric_limits<double>::min(),
        1.0e-7,
        1.0e-9,
        2.0322308988775575e-7,
        123456.78901234567,
        std::numeric_limits<double>::max(),
    };
    const std::string encoded = roundtrip_double_array_json(values);
    CHECK(encoded.size() >= 2);
    CHECK(encoded.front() == '[');
    CHECK(encoded.back() == ']');

    const char* cursor = encoded.c_str() + 1;
    for (std::size_t index = 0; index < values.size(); ++index) {
        errno = 0;
        char* end = nullptr;
        const double decoded = std::strtod(cursor, &end);
        CHECK(end != cursor);
        CHECK(errno != ERANGE || decoded != 0.0);
        CHECK(std::bit_cast<std::uint64_t>(decoded) ==
            std::bit_cast<std::uint64_t>(values[index]));
        CHECK(decoded > 0.0);
        cursor = end;
        if (index + 1 < values.size()) {
            CHECK(*cursor == ',');
            ++cursor;
        }
    }
    CHECK(*cursor == ']');
    CHECK(*(cursor + 1) == '\0');
    return true;
}

bool positive_area_scalars_round_trip_binary64() {
    for (double value : {1.0e-9, 2.0322308988775575e-7}) {
        const std::string encoded = roundtrip_num(value);
        errno = 0;
        char* end = nullptr;
        const double decoded = std::strtod(encoded.c_str(), &end);
        CHECK(end == encoded.c_str() + encoded.size());
        CHECK(errno != ERANGE || decoded != 0.0);
        CHECK(std::bit_cast<std::uint64_t>(decoded) ==
            std::bit_cast<std::uint64_t>(value));
    }
    return true;
}

bool nonfinite_values_remain_fail_closed() {
    try {
        (void)roundtrip_double_array_json({
            1.0,
            std::numeric_limits<double>::infinity(),
        });
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

bool messagepack_scalars_use_lossless_standard_encodings() {
    CHECK(json_to_messagepack("null") == std::vector<std::uint8_t>({0xc0}));
    CHECK(json_to_messagepack("true") == std::vector<std::uint8_t>({0xc3}));
    CHECK(json_to_messagepack("false") == std::vector<std::uint8_t>({0xc2}));
    CHECK(json_to_messagepack("127") == std::vector<std::uint8_t>({0x7f}));
    CHECK(json_to_messagepack("128") ==
        std::vector<std::uint8_t>({0xcc, 0x80}));
    CHECK(json_to_messagepack("-32") == std::vector<std::uint8_t>({0xe0}));
    CHECK(json_to_messagepack("-33") ==
        std::vector<std::uint8_t>({0xd0, 0xdf}));
    CHECK(json_to_messagepack("65536") ==
        std::vector<std::uint8_t>({0xce, 0x00, 0x01, 0x00, 0x00}));
    CHECK(json_to_messagepack("18446744073709551615") ==
        std::vector<std::uint8_t>({
            0xcf, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
        }));
    CHECK(json_to_messagepack("-9223372036854775808") ==
        std::vector<std::uint8_t>({
            0xd3, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        }));
    CHECK(json_to_messagepack("1.5") ==
        std::vector<std::uint8_t>({
            0xcb, 0x3f, 0xf8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        }));
    CHECK(json_to_messagepack("-0.0") ==
        std::vector<std::uint8_t>({
            0xcb, 0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        }));
    // The preserved Python JSON boundary interprets roundtrip_num(-0.0)'s
    // lexical "-0" as integer zero, so the optimized transport must do the
    // same rather than silently changing downstream Python types.
    CHECK(roundtrip_num(-0.0) == "-0");
    CHECK(json_to_messagepack(roundtrip_num(-0.0)) ==
        std::vector<std::uint8_t>({0x00}));
    return true;
}

bool messagepack_strings_and_containers_are_valid() {
    CHECK(json_to_messagepack(R"("hello")") ==
        std::vector<std::uint8_t>({0xa5, 'h', 'e', 'l', 'l', 'o'}));
    CHECK(json_to_messagepack(R"("\u20ac")") ==
        std::vector<std::uint8_t>({0xa3, 0xe2, 0x82, 0xac}));
    CHECK(json_to_messagepack(R"("\ud83c\udf0d")") ==
        std::vector<std::uint8_t>({0xa4, 0xf0, 0x9f, 0x8c, 0x8d}));
    CHECK(json_to_messagepack(R"([1,"x",true])") ==
        std::vector<std::uint8_t>({
            0xdd, 0x00, 0x00, 0x00, 0x03,
            0x01, 0xa1, 'x', 0xc3,
        }));
    CHECK(json_to_messagepack(R"({"a":1,"b":[]})") ==
        std::vector<std::uint8_t>({
            0xdf, 0x00, 0x00, 0x00, 0x02,
            0xa1, 'a', 0x01,
            0xa1, 'b', 0xdd, 0x00, 0x00, 0x00, 0x00,
        }));
    return true;
}

bool malformed_json_to_messagepack_fails_closed() {
    const std::vector<std::string> malformed = {
        "",
        "[1,]",
        "{\"a\":1,}",
        "01",
        "1e",
        "18446744073709551616",
        "-9223372036854775809",
        "1e9999",
        R"("\ud800")",
        R"("\udc00")",
        "true false",
    };
    for (const std::string& input : malformed) {
        bool failed = false;
        try {
            (void)json_to_messagepack(input);
        } catch (const std::runtime_error&) {
            failed = true;
        }
        CHECK(failed);
    }

    std::string too_deep(258, '[');
    too_deep += "0";
    too_deep.append(258, ']');
    bool failed = false;
    try {
        (void)json_to_messagepack(too_deep);
    } catch (const std::runtime_error&) {
        failed = true;
    }
    CHECK(failed);
    return true;
}

bool ffi_diagnostic_utf8_is_preserved_or_sanitized() {
    const std::string valid = "caf\xc3\xa9 \xf0\x9f\x8c\x8d";
    CHECK(sanitize_utf8(valid) == valid);

    const std::string malformed = std::string("bad ") +
        static_cast<char>(0xff) + " truncated \xe2\x82";
    CHECK(sanitize_utf8(malformed) ==
        "bad \xef\xbf\xbd truncated \xef\xbf\xbd\xef\xbf\xbd");
    return true;
}

}  // namespace

int main() {
    if (!strictly_positive_area_arrays_round_trip_binary64() ||
        !positive_area_scalars_round_trip_binary64() ||
        !nonfinite_values_remain_fail_closed() ||
        !messagepack_scalars_use_lossless_standard_encodings() ||
        !messagepack_strings_and_containers_are_valid() ||
        !malformed_json_to_messagepack_fails_closed() ||
        !ffi_diagnostic_utf8_is_preserved_or_sanitized()) {
        return 1;
    }
    return 0;
}
