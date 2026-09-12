#include "engine/solar_insolation.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <limits>
#include <numbers>
#include <stdexcept>
#include <utility>

namespace {

using magic_geo::detail::SolarOrbitForcing;
using magic_geo::detail::daily_mean_solar_insolation_w_m2;
constexpr double PI = std::numbers::pi;
constexpr double SOLAR = 1361.0;
constexpr double RADIANS = PI / 180.0;

// Independent 100-digit Decimal Kepler solutions for e=1-2^-53 and exact
// equal-time calendar boundaries. Reproduce with
// scripts/research/solar_orbit_reference.py; these are not legacy monthly
// quadrature outputs (whose near-apoapsis angle subtraction loses precision).
constexpr std::array<double, 12> NEAR_PARABOLIC_MONTHLY_DISTANCE{
    805306362.3580156077313537344, 1.25232335725528311582,
    0.53243006851106944840, 0.36052785171224632487,
    0.29064288357701106661, 0.25970938147712671680,
    0.25071732955491471138, 0.25970938147712671680,
    0.29064288357701106661, 0.36052785171224632487,
    0.53243006851106944840, 1.25232335725528311582
};

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "check failed at line " << __LINE__ << ": "             \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

bool close(double actual, double expected, double relative = 2.0e-14, double absolute = 1.0e-10) {
    if (!std::isfinite(actual) || std::abs(actual - expected) > absolute + relative * std::abs(expected)) {
        std::cerr << "actual " << actual << ", expected " << expected
                  << ", difference " << actual - expected << '\n';
        return false;
    }
    return true;
}

double mean(const std::array<double, 12>& values) {
    long double total = 0.0L;
    for (double value : values) {
        total += value;
    }
    return static_cast<double>(total / 12.0L);
}

template <typename Function>
bool rejects_invalid_argument(Function&& function) {
    try {
        function();
    } catch (const std::invalid_argument&) {
        return true;
    }
    return false;
}

bool daily_analytic_and_independent_rotation_checks() {
    CHECK(close(daily_mean_solar_insolation_w_m2(0.0, 0.0, SOLAR), SOLAR / PI));
    CHECK(close(daily_mean_solar_insolation_w_m2(PI / 3.0, 0.0, SOLAR), SOLAR / (2.0 * PI)));
    CHECK(close(daily_mean_solar_insolation_w_m2(PI / 2.0, 23.5 * RADIANS, SOLAR),
        SOLAR * std::sin(23.5 * RADIANS)));
    CHECK(daily_mean_solar_insolation_w_m2(PI / 2.0, -23.5 * RADIANS, SOLAR) == 0.0);
    CHECK(daily_mean_solar_insolation_w_m2(-PI / 2.0, 23.5 * RADIANS, SOLAR) == 0.0);

    for (const auto& [latitude, declination] : std::array<std::pair<double, double>, 5>{
            {{0.0, 90.0}, {70.0, 23.5}, {-70.0, 23.5}, {43.0, -14.0}, {-20.0, 70.0}}}) {
        const double phi = latitude * RADIANS;
        const double delta = declination * RADIANS;
        constexpr int rotations = 20000;
        long double total = 0.0L;
        // Independent rotating unit normal dot a fixed sun direction, with
        // no sunrise/sunset or polar branch formula from the producer.
        for (int sample = 0; sample < rotations; ++sample) {
            const double hour_angle = 2.0 * PI * (static_cast<double>(sample) + 0.5) / rotations;
            total += std::max(0.0,
                std::cos(phi) * std::cos(hour_angle) * std::cos(delta) +
                std::sin(phi) * std::sin(delta));
        }
        const double numeric = SOLAR * static_cast<double>(total / rotations);
        CHECK(close(daily_mean_solar_insolation_w_m2(phi, delta, SOLAR), numeric, 0.0, 2.0e-5));
    }
    return true;
}

bool kepler_annual_distance_and_sampling_bounds() {
    for (double eccentricity : {0.0, 0.016, 0.2, 0.8, 0.95, 0.99, 0.999, std::nextafter(1.0, 0.0)}) {
        const SolarOrbitForcing forcing(23.5, eccentricity, 1.0);
        const double expected = 1.0 / std::sqrt((1.0 - eccentricity) * (1.0 + eccentricity));
        CHECK(close(mean(forcing.monthly_inverse_square_distance_factors()), expected, 2.0e-15, 0.0));
        CHECK(forcing.sample_count() >= 768);
        CHECK(forcing.sample_count() <= 779);
        for (double factor : forcing.monthly_inverse_square_distance_factors()) {
            CHECK(std::isfinite(factor));
            CHECK(factor > 0.0);
        }
    }
    CHECK(SolarOrbitForcing(0.0, 0.0, 1.0).sample_count() == 768);
    return true;
}

bool intercepted_global_solar_power() {
    for (const auto& [tilt, eccentricity] : std::array<std::pair<double, double>, 6>{
            {{0.0, 0.0}, {23.5, 0.016}, {60.0, 0.2}, {90.0, 0.8}, {23.5, 0.95}, {90.0, 0.99}}}) {
        const SolarOrbitForcing forcing(tilt, eccentricity, 1.0);
        constexpr int strips = 512;
        std::array<long double, 12> global_monthly{};
        // Equal spacing in sin(latitude) gives equal-area surface strips.
        for (int strip = 0; strip < strips; ++strip) {
            const double latitude = std::asin(-1.0 + 2.0 * (static_cast<double>(strip) + 0.5) / strips);
            const auto monthly = forcing.monthly_insolation_w_m2(latitude);
            for (std::size_t month = 0; month < monthly.size(); ++month) {
                global_monthly[month] += monthly[month];
            }
        }
        long double annual_total = 0.0L;
        for (std::size_t month = 0; month < global_monthly.size(); ++month) {
            const double monthly = static_cast<double>(global_monthly[month] / strips);
            // Sphere intercepts a disk area: instantaneous and monthly global
            // means are one quarter of the normal incident solar irradiance.
            const double expected = SOLAR * forcing.monthly_inverse_square_distance_factors()[month] / 4.0;
            CHECK(close(monthly, expected, 8.0e-5, 0.001));
            annual_total += global_monthly[month];
        }
        const double annual = static_cast<double>(annual_total / (12.0L * strips));
        const double expected = SOLAR / (4.0 * std::sqrt((1.0 - eccentricity) * (1.0 + eccentricity)));
        CHECK(close(annual, expected, 0.0, 0.015));
    }
    return true;
}

bool seasons_and_high_obliquity() {
    const SolarOrbitForcing earth_tilt(23.5, 0.0, 1.0);
    const SolarOrbitForcing high_tilt(60.0, 0.0, 1.0);
    CHECK(mean(earth_tilt.monthly_insolation_w_m2(0.0)) > mean(earth_tilt.monthly_insolation_w_m2(PI / 2.0)));
    CHECK(mean(high_tilt.monthly_insolation_w_m2(PI / 2.0)) > mean(high_tilt.monthly_insolation_w_m2(0.0)));
    const auto north = earth_tilt.monthly_insolation_w_m2(PI / 2.0);
    const auto south = earth_tilt.monthly_insolation_w_m2(-PI / 2.0);
    for (std::size_t month = 0; month < north.size(); ++month) {
        CHECK(close(north[month], south[(month + 6) % 12], 0.0, 1.0e-10));
    }
    CHECK(north[0] == 0.0 && north[1] == 0.0 && north[10] == 0.0 && north[11] == 0.0);
    const auto peak = std::max_element(north.begin(), north.end());
    CHECK(peak - north.begin() == 5 || peak - north.begin() == 6);

    const SolarOrbitForcing no_tilt(0.0, 0.0, 1.0);
    for (double latitude : {-80.0, -35.0, 0.0, 35.0, 80.0}) {
        const auto monthly = no_tilt.monthly_insolation_w_m2(latitude * RADIANS);
        for (double value : monthly) {
            CHECK(close(value, SOLAR * std::cos(latitude * RADIANS) / PI));
        }
    }
    return true;
}

bool extreme_eccentricity_polar_annual_integral() {
    // At 90-degree obliquity the pole's positive zenith factor integrates
    // exactly to two over an orbit in true anomaly, at any periapsis phase.
    for (double eccentricity : {0.0, 0.8, 0.95, 0.99, 0.999, std::nextafter(1.0, 0.0)}) {
        const SolarOrbitForcing forcing(90.0, eccentricity, 1.0);
        const double expected = SOLAR / (PI * std::sqrt((1.0 - eccentricity) * (1.0 + eccentricity)));
        for (double latitude : {-PI / 2.0, PI / 2.0}) {
            const auto monthly = forcing.monthly_insolation_w_m2(latitude);
            for (double value : monthly) {
                CHECK(std::isfinite(value) && value >= 0.0);
            }
            CHECK(close(mean(monthly), expected, 4.0e-6, 0.0));
        }
    }
    return true;
}

bool luminosity_scales_power_only_and_instances_are_reusable() {
    const SolarOrbitForcing reference(48.0, 0.51, 1.0);
    const SolarOrbitForcing dim(48.0, 0.51, 0.05);
    const SolarOrbitForcing bright(48.0, 0.51, 100.0);
    const SolarOrbitForcing dark(48.0, 0.51, 0.0);
    CHECK(reference.monthly_inverse_square_distance_factors() == dim.monthly_inverse_square_distance_factors());
    CHECK(reference.monthly_inverse_square_distance_factors() == bright.monthly_inverse_square_distance_factors());
    CHECK(reference.sample_count() == dim.sample_count());
    const auto baseline = reference.monthly_insolation_w_m2(0.47);
    const auto reduced = dim.monthly_insolation_w_m2(0.47);
    const auto increased = bright.monthly_insolation_w_m2(0.47);
    for (std::size_t month = 0; month < baseline.size(); ++month) {
        CHECK(close(reduced[month], baseline[month] * 0.05));
        CHECK(close(increased[month], baseline[month] * 100.0));
        CHECK(dark.monthly_insolation_w_m2(0.47)[month] == 0.0);
    }
    static_cast<void>(reference.monthly_insolation_w_m2(-1.3));
    CHECK(reference.monthly_insolation_w_m2(0.47) == baseline);
    return true;
}

struct PythonParityFixture {
    double latitude_degrees;
    double tilt_degrees;
    double eccentricity;
    double luminosity;
    std::size_t samples;
    std::array<double, 12> monthly;
    std::array<double, 12> factors;
};

bool python_calendar_and_quadrature_parity() {
    // Generated 2026-09-09 from the current magic_geo.insolation:
    // seasonal_insolation_series(radians(latitude), luminosity, tilt, e, 12).
    // Analytical tests above independently assess physics; these fixtures
    // establish the cross-language calendar and algorithm contract.
    const std::array<PythonParityFixture, 4> fixtures{{
        {37.25, 23.5, 0.016, 1.0, 772,
            {183.66779687950162, 232.69977765591037, 311.00610894087225, 390.3342985251362,
             449.44003898285564, 478.82130019668006, 476.3632992944945, 443.33197192316527,
             383.6585279126401, 306.70014376542457, 231.37279464756776, 183.62021963439787},
            {1.0323901696292364, 1.027833451363998, 1.0156297117532787, 0.9995170812235774,
             0.9840149291430061, 0.9730335409112919, 0.9690886965553881, 0.9730335409112919,
             0.984014929143007, 0.9995170812235762, 1.0156297117532804, 1.0278334513639975}},
        {-58.5, 67.0, 0.73, 0.4, 776,
            {2485.09923241357, 12.681699997980072, 0.0, 0.0, 0.0, 0.0,
             0.0, 0.0, 0.0, 0.0, 0.5026432526191204, 139.0727281523075},
            {8.92063960630991, 2.1056274893386417, 0.7937585595193704, 0.5066325020656912,
             0.3962633009589251, 0.3488210253087713, 0.3352058915531753, 0.34882102530877007,
             0.3962633009589251, 0.50663250206569, 0.7937585595193716, 2.1056274893386373}},
        {89.9, 90.0, 0.99, 2.3, 774,
            {67532.67745185907, 3993.129646651305, 1668.475196148892, 1119.929819318696,
             897.0617355537174, 797.2244508274333, 765.716275504468, 789.1291447970767,
             878.2227287722963, 1082.1682158938536, 1583.389113217769, 3652.731682280121},
            {79.325345256022, 1.2821593700863623, 0.5403334187981393, 0.3649030071212237,
             0.2938033716529184, 0.262376970098148, 0.25324706946468273, 0.26237697009815397,
             0.2938033716529184, 0.36490300712121765, 0.5403334187981453, 1.2821593700863563}},
        {30.0, 23.5, std::nextafter(1.0, 0.0), 100.0, 779,
            {29402589969844.613, 61036.554636505636, 25949.922773463928, 17571.643828572698,
             14165.542300697945, 12657.88379857671, 12219.625783453159, 12657.883796004307,
             14165.542294715171, 17571.643816595708, 25949.92274655027, 61036.55452982997},
            {805306362.3580157, 1.252323380548842, 0.5324300366842036, 0.36052789257156576,
             0.29064287685831547, 0.25970934853502925, 0.2507173475744644, 0.25970934853502925,
             0.29064287685831547, 0.36052789257156576, 0.5324300366842036, 1.252323380548842}},
    }};
    for (const auto& fixture : fixtures) {
        const SolarOrbitForcing forcing(fixture.tilt_degrees, fixture.eccentricity, fixture.luminosity);
        const auto monthly = forcing.monthly_insolation_w_m2(fixture.latitude_degrees * RADIANS);
        CHECK(forcing.sample_count() == fixture.samples);
        for (std::size_t month = 0; month < monthly.size(); ++month) {
            CHECK(close(monthly[month], fixture.monthly[month], 2.0e-13, 1.0e-10));
            CHECK(close(forcing.monthly_inverse_square_distance_factors()[month], fixture.factors[month], 2.0e-14, 1.0e-14));
        }
    }
    return true;
}

bool orbit_integration_partitions_time_and_angle() {
    std::vector<double> eccentricities{0.0, 0.016, 0.2, 0.8, 0.95, 0.99, std::nextafter(1.0, 0.0)};
    for (int exponent = 1; exponent <= 15; ++exponent) {
        eccentricities.push_back(1.0 - std::pow(10.0, -exponent));
    }
    for (double eccentricity : eccentricities) {
        const SolarOrbitForcing forcing(23.5, eccentricity, 1.0);
        const auto& intervals = forcing.integration_intervals();
        const double complement = std::sqrt((1.0 - eccentricity) * (1.0 + eccentricity));
        CHECK(intervals.size() >= 768);
        CHECK(intervals.size() <= 1127);
        std::array<long double, 12> monthly_duration{};
        std::array<long double, 12> monthly_distance_integral{};
        std::size_t previous_month = 0;
        for (std::size_t index = 0; index < intervals.size(); ++index) {
            const auto& interval = intervals[index];
            CHECK(interval.month_index < 12);
            CHECK(interval.month_index >= previous_month);
            CHECK(interval.month_index <= previous_month + 1);
            previous_month = interval.month_index;
            CHECK(std::isfinite(interval.duration_fraction_of_year));
            CHECK(interval.duration_fraction_of_year > 0.0);
            CHECK(interval.duration_fraction_of_year <= 1.0 / 360.0 + 2.0e-15);
            CHECK(std::isfinite(interval.declination_rad));
            CHECK(std::abs(interval.declination_rad) <= 23.5 * RADIANS + 1.0e-15);
            CHECK(std::isfinite(interval.inverse_square_distance_factor));
            CHECK(interval.inverse_square_distance_factor > 0.0);
            // Recover angular width through the exact Kepler fluence identity.
            const double angular_width = interval.inverse_square_distance_factor *
                interval.duration_fraction_of_year * 2.0 * PI * complement;
            CHECK(angular_width > 0.0);
            CHECK(angular_width <= 2.0 * PI / 768.0 + 2.0e-14);
            monthly_duration[interval.month_index] += interval.duration_fraction_of_year;
            monthly_distance_integral[interval.month_index] +=
                static_cast<long double>(interval.inverse_square_distance_factor) *
                interval.duration_fraction_of_year;
            CHECK(close(forcing.interval_mean_insolation_w_m2(0.49, index),
                daily_mean_solar_insolation_w_m2(0.49, interval.declination_rad,
                    SOLAR * interval.inverse_square_distance_factor)));
        }
        for (std::size_t month = 0; month < monthly_duration.size(); ++month) {
            CHECK(close(static_cast<double>(monthly_duration[month]), 1.0 / 12.0, 0.0, 3.0e-16));
            if (eccentricity <= 0.99) {
                CHECK(close(static_cast<double>(monthly_distance_integral[month] * 12.0L),
                    forcing.monthly_inverse_square_distance_factors()[month], 3.0e-15, 1.0e-14));
            }
        }
        long double annual_distance = 0.0L;
        for (long double value : monthly_distance_integral) annual_distance += value;
        CHECK(close(static_cast<double>(annual_distance), 1.0 / complement, 3.0e-15, 0.0));
    }
    return true;
}

bool submonthly_analytic_fluences_and_near_parabolic_durations() {
    for (double eccentricity : {0.0, 0.4, 0.99, std::nextafter(1.0, 0.0)}) {
        const SolarOrbitForcing equatorial(0.0, eccentricity, 1.0);
        std::array<long double, 12> monthly{};
        for (std::size_t index = 0; index < equatorial.integration_intervals().size(); ++index) {
            const auto& interval = equatorial.integration_intervals()[index];
            monthly[interval.month_index] += static_cast<long double>(
                equatorial.interval_mean_insolation_w_m2(0.4, index)) * interval.duration_fraction_of_year;
        }
        for (std::size_t month = 0; month < monthly.size(); ++month) {
            const double distance = eccentricity == std::nextafter(1.0, 0.0) ?
                NEAR_PARABOLIC_MONTHLY_DISTANCE[month] : equatorial.monthly_inverse_square_distance_factors()[month];
            const double expected = SOLAR * std::cos(0.4) / PI *
                distance;
            CHECK(close(static_cast<double>(12.0L * monthly[month]), expected, 5.0e-15, 1.0e-10));
        }
        const SolarOrbitForcing oblique(90.0, eccentricity, 1.0);
        long double annual = 0.0L;
        for (std::size_t index = 0; index < oblique.integration_intervals().size(); ++index) {
            annual += static_cast<long double>(oblique.interval_mean_insolation_w_m2(PI / 2.0, index)) *
                oblique.integration_intervals()[index].duration_fraction_of_year;
        }
        const double expected = SOLAR / (PI * std::sqrt((1.0 - eccentricity) * (1.0 + eccentricity)));
        CHECK(close(static_cast<double>(annual), expected, 4.0e-6, 0.0));
    }
    const SolarOrbitForcing extreme(23.5, std::nextafter(1.0, 0.0), 100.0);
    double minimum_duration = 1.0;
    double largest_flux = 0.0;
    for (std::size_t index = 0; index < extreme.integration_intervals().size(); ++index) {
        minimum_duration = std::min(minimum_duration,
            extreme.integration_intervals()[index].duration_fraction_of_year);
        largest_flux = std::max(largest_flux, extreme.interval_mean_insolation_w_m2(0.0, index));
    }
    CHECK(minimum_duration < 1.0e-25);
    CHECK(largest_flux > 1.0e30);
    return true;
}

double reference_true_anomaly(double unwrapped_mean, double eccentricity) {
    const double revolution = std::floor((unwrapped_mean + PI) / (2.0 * PI));
    const double mean_anomaly = unwrapped_mean - revolution * 2.0 * PI;
    double lower = -PI;
    double upper = PI;
    double eccentric_anomaly = mean_anomaly;
    // Independently solve with safeguarded Newton and a direct atan2 anomaly
    // transformation instead of the producer's fixed bisection/half-angle.
    for (int iteration = 0; iteration < 90; ++iteration) {
        const double residual = eccentric_anomaly - eccentricity * std::sin(eccentric_anomaly) - mean_anomaly;
        if (residual < 0.0) {
            lower = eccentric_anomaly;
        } else {
            upper = eccentric_anomaly;
        }
        double next = eccentric_anomaly - residual / (1.0 - eccentricity * std::cos(eccentric_anomaly));
        if (!(next > lower && next < upper)) {
            next = (lower + upper) / 2.0;
        }
        if (next == eccentric_anomaly) {
            break;
        }
        eccentric_anomaly = next;
    }
    return std::atan2(
        std::sqrt((1.0 - eccentricity) * (1.0 + eccentricity)) * std::sin(eccentric_anomaly),
        std::cos(eccentric_anomaly) - eccentricity
    ) + revolution * 2.0 * PI;
}

double reference_monthly_insolation(double latitude, double tilt, double eccentricity, std::size_t month) {
    const double mean_width = 2.0 * PI / 12.0;
    const double start = reference_true_anomaly(mean_width * (static_cast<double>(month) - 0.5), eccentricity);
    const double end = reference_true_anomaly(mean_width * (static_cast<double>(month) + 0.5), eccentricity);
    // Much finer angular quadrature has no dependency on the producer's
    // time partitions, cached declinations, or interval flux routine.
    const int samples = std::max(1, static_cast<int>(std::ceil((end - start) / (2.0 * PI / 65536.0))));
    long double integral = 0.0L;
    for (int sample = 0; sample < samples; ++sample) {
        const double angle = start + (end - start) * (static_cast<double>(sample) + 0.5) / samples;
        const double delta = std::asin(std::sin(tilt) * std::sin(angle - 75.0 * RADIANS));
        const double hour_angle = std::acos(std::clamp(-std::tan(latitude) * std::tan(delta), -1.0, 1.0));
        integral += std::max(0.0,
            hour_angle * std::sin(latitude) * std::sin(delta) +
            std::sin(hour_angle) * std::cos(latitude) * std::cos(delta)) / PI;
    }
    const double factor = (end - start) /
        (mean_width * std::sqrt((1.0 - eccentricity) * (1.0 + eccentricity)));
    return SOLAR * factor * static_cast<double>(integral / samples);
}

bool submonthly_matches_refined_independent_solar_fluences() {
    struct Case { double latitude; double tilt; double eccentricity; };
    for (const auto& test : std::array<Case, 4>{{
            {37.25, 23.5, 0.016}, {-58.5, 67.0, 0.73}, {43.0, 90.0, 0.99},
            {30.0, 23.5, std::nextafter(1.0, 0.0)}}}) {
        const SolarOrbitForcing forcing(test.tilt, test.eccentricity, 1.0);
        std::array<long double, 12> monthly{};
        for (std::size_t index = 0; index < forcing.integration_intervals().size(); ++index) {
            const auto& interval = forcing.integration_intervals()[index];
            monthly[interval.month_index] += static_cast<long double>(
                forcing.interval_mean_insolation_w_m2(test.latitude * RADIANS, index)) *
                interval.duration_fraction_of_year;
        }
        for (std::size_t month = 0; month < monthly.size(); ++month) {
            const double expected = reference_monthly_insolation(test.latitude * RADIANS,
                test.tilt * RADIANS, test.eccentricity, month);
            // Angular midpoint quadrature is approximate, particularly for a
            // short positive daylight interval at the polar-night boundary.
            // The absolute allowance resolves weak twilight-month fluences;
            // the relative allowance scales the intense periapsis month.
            if (!close(static_cast<double>(12.0L * monthly[month]), expected, 2.0e-5, 0.005)) {
                std::cerr << "latitude " << test.latitude << ", tilt " << test.tilt
                          << ", eccentricity " << test.eccentricity << ", month " << month << '\n';
                return false;
            }
        }
    }
    return true;
}

bool astronomical_refinement_preserves_calendar_and_resolves_fluence() {
    for (double eccentricity : {0.0, 0.016, 0.73, 0.99, std::nextafter(1.0, 0.0)}) {
        const SolarOrbitForcing original(23.5, eccentricity, 1.0);
        for (int level : {1, 2, 3}) {
            const SolarOrbitForcing refined(23.5, eccentricity, 1.0, level);
            const double factor = std::ldexp(1.0, level);
            CHECK(refined.integration_refinement_level() == level);
            CHECK(refined.sample_count() == original.sample_count());
            CHECK(refined.monthly_insolation_w_m2(0.49) == original.monthly_insolation_w_m2(0.49));
            CHECK(refined.monthly_inverse_square_distance_factors() == original.monthly_inverse_square_distance_factors());
            CHECK(refined.integration_intervals().size() > original.integration_intervals().size());
            std::array<long double, 12> duration{}, distance_integral{};
            for (const auto& interval : refined.integration_intervals()) {
                CHECK(interval.duration_fraction_of_year > 0.0);
                CHECK(interval.duration_fraction_of_year <= 1.0 / (360.0 * factor) + 2.0e-15);
                const double angle = interval.inverse_square_distance_factor * interval.duration_fraction_of_year *
                    2.0 * PI * std::sqrt((1.0 - eccentricity) * (1.0 + eccentricity));
                CHECK(angle > 0.0 && angle <= 2.0 * PI / (768.0 * factor) + 2.0e-14);
                duration[interval.month_index] += interval.duration_fraction_of_year;
                distance_integral[interval.month_index] += static_cast<long double>(interval.duration_fraction_of_year) *
                    interval.inverse_square_distance_factor;
            }
            for (std::size_t month = 0; month < 12; ++month) {
                CHECK(close(static_cast<double>(duration[month]), 1.0 / 12.0, 0.0, 3.0e-16));
                const double expected = eccentricity == std::nextafter(1.0, 0.0) ?
                    NEAR_PARABOLIC_MONTHLY_DISTANCE[month] : original.monthly_inverse_square_distance_factors()[month];
                CHECK(close(static_cast<double>(distance_integral[month] * 12.0L),
                    expected, 4.0e-15, 1.0e-14));
            }
        }
    }

    // Circular orbit, a pole, and 90-degree tilt: the fourth month's mean
    // sunlight is an exact sine integral over solar longitude [0,pi/6].
    // Recomputed astronomical nodes must converge; copying each parent's
    // average into smaller children would leave this error unchanged.
    const double expected = SOLAR * (1.0 - std::cos(PI / 6.0)) / (PI / 6.0);
    double previous_error = 0.0;
    for (int level = 0; level <= 3; ++level) {
        const SolarOrbitForcing refined(90.0, 0.0, 1.0, level);
        long double total = 0.0L;
        for (std::size_t i = 0; i < refined.integration_intervals().size(); ++i) {
            const auto& interval = refined.integration_intervals()[i];
            if (interval.month_index == 3) {
                total += static_cast<long double>(interval.duration_fraction_of_year) *
                    refined.interval_mean_insolation_w_m2(PI / 2.0, i);
            }
        }
        const double error = std::abs(static_cast<double>(12.0L * total) - expected);
        CHECK(error > 0.0);
        if (level > 0) CHECK(previous_error / error > 3.95 && previous_error / error < 4.05);
        previous_error = error;
    }
    return true;
}

bool refined_near_parabolic_distance_matches_independent_oracle() {
    // First equal-time interval after apoapsis, computed independently at
    // 80 and 100 decimal digits. Absolute angular widths here can be ~1e-13
    // radians, so subtracting two rounded angles near pi fails this test.
    constexpr std::array<int, 4> levels{0, 3, 6, 10};
    constexpr std::array<double, 4> apoapsis_factor{
        0.25000317316457684646, 0.25000004957967441991,
        0.25000000077468219060, 0.25000000000302612994
    };
    const double eccentricity = std::nextafter(1.0, 0.0);
    for (std::size_t test = 0; test < levels.size(); ++test) {
        const int level = levels[test];
        const SolarOrbitForcing forcing(0.0, eccentricity, 1.0, level);
        std::array<long double, 12> monthly_distance{};
        std::size_t month_six_count = 0;
        bool checked_apoapsis = false;
        for (std::size_t index = 0; index < forcing.integration_intervals().size(); ++index) {
            const auto& interval = forcing.integration_intervals()[index];
            monthly_distance[interval.month_index] +=
                static_cast<long double>(interval.duration_fraction_of_year) * interval.inverse_square_distance_factor;
            if (interval.month_index == 6) {
                if (month_six_count == (std::size_t{15} << level)) {
                    CHECK(close(interval.inverse_square_distance_factor, apoapsis_factor[test], 2.0e-10, 0.0));
                    CHECK(close(forcing.interval_mean_insolation_w_m2(0.0, index),
                        SOLAR / PI * apoapsis_factor[test], 2.0e-10, 0.0));
                    checked_apoapsis = true;
                }
                ++month_six_count;
            }
        }
        CHECK(checked_apoapsis);
        CHECK(month_six_count == (std::size_t{30} << level));
        for (std::size_t month = 0; month < 12; ++month) {
            CHECK(close(static_cast<double>(12.0L * monthly_distance[month]),
                NEAR_PARABOLIC_MONTHLY_DISTANCE[month], 4.0e-15, 1.0e-14));
        }
    }
    return true;
}

bool refined_interval_distance_stays_within_physical_orbit_bounds() {
    // An interval average lies between the periapsis and apoapsis extrema.
    // 2e-10 admits endpoint subtraction roundoff at the maximum supported
    // refinement (including circular-orbit angular partitions), while
    // rejecting the old near-parabolic ~0.7 percent local error.
    for (double eccentricity : {0.0, 0.5, 0.9, 0.999999, std::nextafter(1.0, 0.0)}) {
        const SolarOrbitForcing forcing(23.5, eccentricity, 1.0, 10);
        const double minimum = 1.0 / ((1.0 + eccentricity) * (1.0 + eccentricity));
        const double maximum = 1.0 / ((1.0 - eccentricity) * (1.0 - eccentricity));
        for (const auto& interval : forcing.integration_intervals()) {
            CHECK(interval.inverse_square_distance_factor >= minimum * (1.0 - 2.0e-10));
            CHECK(interval.inverse_square_distance_factor <= maximum * (1.0 + 2.0e-10));
        }
    }
    return true;
}

bool invalid_domains_are_rejected_without_clipping() {
    const double infinity = std::numeric_limits<double>::infinity();
    const double nan = std::numeric_limits<double>::quiet_NaN();
    for (int level : {-1, SolarOrbitForcing::maximum_integration_refinement_level + 1}) {
        CHECK(rejects_invalid_argument([&] { SolarOrbitForcing forcing(23.5, 0.1, 1.0, level); }));
    }
    bool overflow_rejected = false;
    try {
        SolarOrbitForcing excessive(23.5, 0.1, std::numeric_limits<double>::max());
    } catch (const std::overflow_error&) {
        overflow_rejected = true;
    }
    CHECK(overflow_rejected);
    for (double eccentricity : {-0.01, 1.0, infinity, -infinity, nan}) {
        CHECK(rejects_invalid_argument([&] { SolarOrbitForcing forcing(23.5, eccentricity, 1.0); }));
    }
    for (double tilt : {-0.01, 90.01, infinity, nan}) {
        CHECK(rejects_invalid_argument([&] { SolarOrbitForcing forcing(tilt, 0.1, 1.0); }));
    }
    for (double luminosity : {-0.01, infinity, nan}) {
        CHECK(rejects_invalid_argument([&] { SolarOrbitForcing forcing(23.5, 0.1, luminosity); }));
    }
    const SolarOrbitForcing forcing(23.5, 0.1, 1.0);
    for (double angle : {-PI, PI, infinity, nan}) {
        CHECK(rejects_invalid_argument([&] { static_cast<void>(forcing.monthly_insolation_w_m2(angle)); }));
        CHECK(rejects_invalid_argument([&] { static_cast<void>(forcing.interval_mean_insolation_w_m2(angle, 0)); }));
        CHECK(rejects_invalid_argument([&] { static_cast<void>(daily_mean_solar_insolation_w_m2(angle, 0.0, SOLAR)); }));
        CHECK(rejects_invalid_argument([&] { static_cast<void>(daily_mean_solar_insolation_w_m2(0.0, angle, SOLAR)); }));
    }
    bool index_rejected = false;
    try {
        static_cast<void>(forcing.interval_mean_insolation_w_m2(0.0, forcing.integration_intervals().size()));
    } catch (const std::out_of_range&) {
        index_rejected = true;
    }
    CHECK(index_rejected);
    for (double irradiance : {-1.0, infinity, nan}) {
        CHECK(rejects_invalid_argument([&] { static_cast<void>(daily_mean_solar_insolation_w_m2(0.0, 0.0, irradiance)); }));
    }
    return true;
}

}  // namespace

int main() {
    if (!daily_analytic_and_independent_rotation_checks() ||
        !kepler_annual_distance_and_sampling_bounds() ||
        !intercepted_global_solar_power() ||
        !seasons_and_high_obliquity() ||
        !extreme_eccentricity_polar_annual_integral() ||
        !luminosity_scales_power_only_and_instances_are_reusable() ||
        !python_calendar_and_quadrature_parity() ||
        !orbit_integration_partitions_time_and_angle() ||
        !submonthly_analytic_fluences_and_near_parabolic_durations() ||
        !submonthly_matches_refined_independent_solar_fluences() ||
        !astronomical_refinement_preserves_calendar_and_resolves_fluence() ||
        !refined_near_parabolic_distance_matches_independent_oracle() ||
        !refined_interval_distance_stays_within_physical_orbit_bounds() ||
        !invalid_domains_are_rejected_without_clipping()) {
        return 1;
    }
    return 0;
}
