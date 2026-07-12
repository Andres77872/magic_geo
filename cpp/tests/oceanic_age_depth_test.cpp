#include "engine/internal.hpp"

#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "check failed at line " << __LINE__ << ": "          \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

double expected_thermal_subsidence_m(double age_ma) {
    if (age_ma <= 70.0) {
        return age_ma == 0.0 ? 0.0 : -350.0 * std::sqrt(age_ma);
    }
    return -(
        350.0 * std::sqrt(70.0) +
        3200.0 * (
            std::exp(-70.0 / 62.8) - std::exp(-age_ma / 62.8)
        )
    );
}

double positive_ulp(double value) {
    const double magnitude = std::abs(value);
    return std::nextafter(
        magnitude,
        std::numeric_limits<double>::infinity()
    ) - magnitude;
}

bool analytic_checkpoints_match() {
    using magic_geo::detail::oceanic_age_depth_thermal_subsidence_m;
    const double below_70 = std::nextafter(70.0, 0.0);
    const double above_70 = std::nextafter(
        70.0,
        std::numeric_limits<double>::infinity()
    );
    for (double age_ma : {0.0, 20.0, below_70, 70.0, above_70, 100.0, 320.0}) {
        const double actual = oceanic_age_depth_thermal_subsidence_m(
            age_ma,
            true
        );
        CHECK(std::isfinite(actual));
        // The independent expression deliberately uses the same documented
        // binary64 operation order. Exact equality catches a coefficient,
        // branch, or continuity-offset change without a blanket tolerance.
        CHECK(actual == expected_thermal_subsidence_m(age_ma));
    }
    CHECK(oceanic_age_depth_thermal_subsidence_m(0.0, true) == 0.0);
    CHECK(!std::signbit(oceanic_age_depth_thermal_subsidence_m(0.0, true)));
    return true;
}

bool transition_is_c0_continuous_and_monotone() {
    using magic_geo::detail::oceanic_age_depth_thermal_subsidence_m;
    const double below_70 = std::nextafter(70.0, 0.0);
    const double at_70 = oceanic_age_depth_thermal_subsidence_m(70.0, true);
    const double above_70 = std::nextafter(
        70.0,
        std::numeric_limits<double>::infinity()
    );
    const double below_value = oceanic_age_depth_thermal_subsidence_m(
        below_70,
        true
    );
    const double above_value = oceanic_age_depth_thermal_subsidence_m(
        above_70,
        true
    );
    CHECK(below_value >= at_70);
    CHECK(at_70 >= above_value);
    const double young_derivative_envelope_m_per_ma =
        175.0 / std::sqrt(below_70);
    const double old_derivative_envelope_m_per_ma =
        (3200.0 / 62.8) * std::exp(-70.0 / 62.8);
    // A one-input-ULP derivative envelope bounds the true value change on
    // either side. Eight output ULPs cover the young sqrt/multiply path;
    // sixteen cover both exponentials, their subtraction, scaling, and sum.
    const double below_continuity_bound_m =
        young_derivative_envelope_m_per_ma * (70.0 - below_70) +
        8.0 * positive_ulp(at_70);
    const double above_continuity_bound_m =
        old_derivative_envelope_m_per_ma * (above_70 - 70.0) +
        16.0 * positive_ulp(at_70);
    CHECK(std::abs(below_value - at_70) <= below_continuity_bound_m);
    CHECK(std::abs(above_value - at_70) <= above_continuity_bound_m);

    double previous = oceanic_age_depth_thermal_subsidence_m(0.0, true);
    for (int age_quarters = 1; age_quarters <= 1280; ++age_quarters) {
        const double age_ma = static_cast<double>(age_quarters) / 4.0;
        const double current = oceanic_age_depth_thermal_subsidence_m(
            age_ma,
            true
        );
        CHECK(std::isfinite(current));
        CHECK(current <= previous);
        previous = current;
    }
    return true;
}

bool non_oceanic_and_domain_guards_are_exact() {
    using magic_geo::detail::oceanic_age_depth_thermal_subsidence_m;
    for (double age_ma : {0.0, 20.0, 70.0, 100.0, 320.0}) {
        const double value = oceanic_age_depth_thermal_subsidence_m(
            age_ma,
            false
        );
        CHECK(value == 0.0);
        CHECK(!std::signbit(value));
    }
    const double maximum_age_value = oceanic_age_depth_thermal_subsidence_m(
        std::numeric_limits<double>::max(),
        true
    );
    CHECK(std::isfinite(maximum_age_value));
    CHECK(maximum_age_value < 0.0);

    for (double invalid_age : {
            -1.0,
            std::numeric_limits<double>::infinity(),
            -std::numeric_limits<double>::infinity(),
            std::numeric_limits<double>::quiet_NaN(),
        }) {
        bool threw = false;
        try {
            static_cast<void>(oceanic_age_depth_thermal_subsidence_m(
                invalid_age,
                false
            ));
        } catch (const std::invalid_argument&) {
            threw = true;
        }
        CHECK(threw);
    }
    return true;
}

}  // namespace

int main() {
    if (!analytic_checkpoints_match() ||
        !transition_is_c0_continuous_and_monotone() ||
        !non_oceanic_and_domain_guards_are_exact()) {
        return 1;
    }
    return 0;
}
