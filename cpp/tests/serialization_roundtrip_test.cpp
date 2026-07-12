#include "engine/internal.hpp"

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

}  // namespace

int main() {
    if (!strictly_positive_area_arrays_round_trip_binary64() ||
        !positive_area_scalars_round_trip_binary64() ||
        !nonfinite_values_remain_fail_closed()) {
        return 1;
    }
    return 0;
}
