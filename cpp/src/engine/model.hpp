#pragma once

#include "constants.hpp"
#include "schema_names.hpp"
#include "types/core.hpp"
#include "types/earth_system.hpp"
#include "types/world.hpp"

#include "magic_geo/native.hpp"

#include <algorithm>

namespace magic_geo::detail {

template <typename T>
constexpr T clamp(T value, T low, T high) {
    return std::max(low, std::min(high, value));
}

}  // namespace magic_geo::detail
