#pragma once

#include <cmath>

namespace magic_geo::detail {

// Domain of the existing annual settlement suitability response centered at
// 17 C with width 31 C. This is not a human-survival or universal biology law.
// Compare the input itself: evaluating the triangle can round to zero for a
// representable temperature immediately inside its mathematical support.
inline bool settlement_annual_climate_supported(double temperature_c) {
    return std::isfinite(temperature_c) && temperature_c > -14.0 && temperature_c < 48.0;
}

}  // namespace magic_geo::detail
