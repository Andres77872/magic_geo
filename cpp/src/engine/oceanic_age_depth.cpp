#include "internal.hpp"

namespace magic_geo::detail {

double oceanic_age_depth_thermal_subsidence_m(
    double crust_age_ma,
    bool oceanic_like
) {
    if (!std::isfinite(crust_age_ma) || crust_age_ma < 0.0) {
        throw std::invalid_argument(
            "oceanic age-depth model requires a finite nonnegative crust age"
        );
    }
    if (!oceanic_like) {
        return 0.0;
    }

    double relative_subsidence_m = 0.0;
    if (crust_age_ma <= OCEANIC_AGE_DEPTH_YOUNG_CUTOFF_MA) {
        relative_subsidence_m =
            OCEANIC_AGE_DEPTH_YOUNG_COEFFICIENT_M_PER_SQRT_MA *
            std::sqrt(crust_age_ma);
    } else {
        const double cutoff_subsidence_m =
            OCEANIC_AGE_DEPTH_YOUNG_COEFFICIENT_M_PER_SQRT_MA *
            std::sqrt(OCEANIC_AGE_DEPTH_YOUNG_CUTOFF_MA);
        relative_subsidence_m = cutoff_subsidence_m +
            OCEANIC_AGE_DEPTH_OLD_EXPONENTIAL_SCALE_M * (
                std::exp(
                    -OCEANIC_AGE_DEPTH_YOUNG_CUTOFF_MA /
                    OCEANIC_AGE_DEPTH_OLD_EFOLDING_TIME_MA
                ) -
                std::exp(
                    -crust_age_ma /
                    OCEANIC_AGE_DEPTH_OLD_EFOLDING_TIME_MA
                )
            );
    }
    if (!std::isfinite(relative_subsidence_m) ||
        relative_subsidence_m < 0.0) {
        throw std::runtime_error(
            "oceanic age-depth model produced invalid relative subsidence"
        );
    }
    if (relative_subsidence_m == 0.0) {
        return 0.0;
    }
    return -relative_subsidence_m;
}

}  // namespace magic_geo::detail
