#include "solar_insolation.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace magic_geo::detail {
namespace {

constexpr double PI = std::numbers::pi;
constexpr double RADIANS_PER_DEGREE = PI / 180.0;

void require_latitude(double latitude_rad) {
    if (!std::isfinite(latitude_rad) || latitude_rad < -PI / 2.0 || latitude_rad > PI / 2.0) {
        throw std::invalid_argument("latitude_rad must be finite and in [-pi/2, pi/2]");
    }
}

double daily_mean_from_trigonometry(
    double latitude_sine,
    double latitude_cosine,
    double declination_sine,
    double declination_cosine,
    double irradiance_w_m2
) {
    const double a = latitude_sine * declination_sine;
    const double b = std::max(0.0, latitude_cosine * declination_cosine);
    // This branch order includes the exact-pole limit without tan(latitude).
    if (a >= b) {
        return irradiance_w_m2 * std::max(0.0, a);
    }
    if (a <= -b) {
        return 0.0;
    }
    const double sunset = std::acos(-a / b);
    return irradiance_w_m2 * (sunset * a + b * std::sin(sunset)) / PI;
}

double principal_eccentric_anomaly(double mean, double eccentricity) {
    if (mean == 0.0 || mean == -PI) {
        return mean;
    }
    double lower = -PI;
    double upper = PI;
    // Kepler's equation is strictly monotone for every accepted e < 1.
    // Bisection avoids Newton divergence near a highly eccentric periapsis.
    for (int iteration = 0; iteration < 60; ++iteration) {
        const double anomaly = (lower + upper) / 2.0;
        if (anomaly - eccentricity * std::sin(anomaly) < mean) {
            lower = anomaly;
        } else {
            upper = anomaly;
        }
    }
    return (lower + upper) / 2.0;
}

double true_anomaly_at_mean_anomaly(double mean_anomaly, double eccentricity) {
    const double revolutions = std::floor((mean_anomaly + PI) / (2.0 * PI));
    const double mean = mean_anomaly - revolutions * 2.0 * PI;
    if (mean == 0.0 || mean == -PI) {
        return mean + revolutions * 2.0 * PI;
    }
    const double anomaly = principal_eccentric_anomaly(mean, eccentricity);
    const double true_anomaly = 2.0 * std::atan2(
        std::sqrt(1.0 + eccentricity) * std::sin(anomaly / 2.0),
        std::sqrt(1.0 - eccentricity) * std::cos(anomaly / 2.0)
    );
    return true_anomaly + revolutions * 2.0 * PI;
}

double short_true_anomaly_span(double mean_start, double mean_end, double eccentricity) {
    const auto eccentric_anomaly = [eccentricity](double mean) {
        const double revolutions = std::floor((mean + PI) / (2.0 * PI));
        return principal_eccentric_anomaly(mean - revolutions * 2.0 * PI, eccentricity);
    };
    const double first = eccentric_anomaly(mean_start);
    const double second = eccentric_anomaly(mean_end);
    const double eccentric_span = second >= first ? second - first : (PI - first) + (second + PI);
    const double complement = std::sqrt((1.0 - eccentricity) * (1.0 + eccentricity));
    // atan2(cross,dot) avoids subtracting true anomalies that both round
    // nearly to pi in the slow part of a near-parabolic orbit. Form the cross
    // product through half-angle identities to avoid a second cancellation.
    const double half_span = eccentric_span / 2.0;
    const double cross = 2.0 * complement * std::sin(half_span) *
        (std::cos(half_span) - eccentricity * std::cos(first + half_span));
    const double first_x = std::cos(first) - eccentricity;
    const double second_x = std::cos(second) - eccentricity;
    const double dot = first_x * second_x + complement * complement * std::sin(first) * std::sin(second);
    const double span = std::atan2(cross, dot);
    if (!std::isfinite(span) || span <= 0.0 || span >= PI) {
        throw std::runtime_error("short solar anomaly interval is not representable");
    }
    return span;
}

double anomaly_minus_sine(double anomaly) {
    if (std::abs(anomaly) >= 0.1) {
        return anomaly - std::sin(anomaly);
    }
    // E-sin(E) = E^3/3! - E^5/5! + ... . The direct subtraction
    // loses the entire cubic term when E is tiny near e -> 1.
    const double squared = anomaly * anomaly;
    double term = anomaly * squared / 6.0;
    double sum = term;
    for (int degree = 5; degree <= 17; degree += 2) {
        term *= -squared / static_cast<double>(degree * (degree - 1));
        sum += term;
    }
    return sum;
}

double mean_anomaly_at_true_anomaly(double true_anomaly, double eccentricity) {
    const double revolutions = std::floor((true_anomaly + PI) / (2.0 * PI));
    const double angle = true_anomaly - revolutions * 2.0 * PI;
    const double anomaly = 2.0 * std::atan2(
        std::sqrt(1.0 - eccentricity) * std::sin(angle / 2.0),
        std::sqrt(1.0 + eccentricity) * std::cos(angle / 2.0)
    );
    return (1.0 - eccentricity) * anomaly + eccentricity * anomaly_minus_sine(anomaly) +
        revolutions * 2.0 * PI;
}

}  // namespace

double daily_mean_solar_insolation_w_m2(
    double latitude_rad,
    double declination_rad,
    double irradiance_w_m2
) {
    require_latitude(latitude_rad);
    if (!std::isfinite(declination_rad) || declination_rad < -PI / 2.0 || declination_rad > PI / 2.0) {
        throw std::invalid_argument("declination_rad must be finite and in [-pi/2, pi/2]");
    }
    if (!std::isfinite(irradiance_w_m2) || irradiance_w_m2 < 0.0) {
        throw std::invalid_argument("irradiance_w_m2 must be finite and nonnegative");
    }
    return daily_mean_from_trigonometry(
        std::sin(latitude_rad), std::cos(latitude_rad),
        std::sin(declination_rad), std::cos(declination_rad),
        irradiance_w_m2
    );
}

SolarOrbitForcing::SolarOrbitForcing(
    double tilt_degrees,
    double eccentricity,
    double stellar_luminosity,
    int integration_refinement_level
) {
    if (!std::isfinite(tilt_degrees) || tilt_degrees < 0.0 || tilt_degrees > 90.0) {
        throw std::invalid_argument("tilt_degrees must be finite and in [0, 90]");
    }
    if (!std::isfinite(eccentricity) || eccentricity < 0.0 || eccentricity >= 1.0) {
        throw std::invalid_argument("orbital_eccentricity must be finite and in [0, 1)");
    }
    if (!std::isfinite(stellar_luminosity) || stellar_luminosity < 0.0) {
        throw std::invalid_argument("stellar_luminosity must be finite and nonnegative");
    }
    if (integration_refinement_level < 0 || integration_refinement_level > maximum_integration_refinement_level) {
        throw std::invalid_argument("solar integration refinement level must be in [0, 10]");
    }
    integration_refinement_level_ = integration_refinement_level;

    const double tilt = tilt_degrees * RADIANS_PER_DEGREE;
    const double mean_month_duration = 2.0 * PI / static_cast<double>(month_count);
    const double complement = std::sqrt((1.0 - eccentricity) * (1.0 + eccentricity));
    const double periapsis_longitude = solar_longitude_at_periapsis_deg * RADIANS_PER_DEGREE;
    std::array<double, month_count + 1> boundaries{};
    for (std::size_t boundary = 0; boundary <= month_count; ++boundary) {
        boundaries[boundary] = true_anomaly_at_mean_anomaly(
            mean_month_duration * (static_cast<double>(boundary) - 0.5),
            eccentricity
        );
    }
    for (std::size_t month = 0; month < month_count; ++month) {
        const double start = boundaries[month];
        const double span = boundaries[month + 1] - start;
        const std::size_t count = static_cast<std::size_t>(std::max(
            1.0, std::ceil(span / maximum_true_anomaly_step_rad - 1.0e-10)
        ));
        // (a/r)^2 dM = dnu / sqrt(1-e^2). These time weights remain
        // resolved when almost the entire orbit lies in the periapsis month.
        distance_factors_[month] = span / (mean_month_duration * complement);
        irradiance_w_m2_[month] = solar_constant_w_m2 * stellar_luminosity * distance_factors_[month];
        if (!std::isfinite(irradiance_w_m2_[month])) {
            throw std::overflow_error("monthly solar irradiance is not representable");
        }
        samples_[month].reserve(count);
        for (std::size_t sample = 0; sample < count; ++sample) {
            const double true_anomaly = start + span * (static_cast<double>(sample) + 0.5) /
                static_cast<double>(count);
            const double longitude = true_anomaly + periapsis_longitude;
            // Preserve the Python angle/trigonometric convention while doing
            // these operations only once for the whole planet.
            const double declination = std::asin(std::sin(tilt) * std::sin(longitude));
            samples_[month].push_back({std::sin(declination), std::cos(declination)});
        }
        sample_count_ += count;
    }

    // Resolve elapsed time at apoapsis as well as true anomaly at periapsis.
    // The monthly export quadrature above remains unchanged for Python parity.
    const std::size_t refinement_factor = std::size_t{1} << integration_refinement_level;
    const std::size_t time_subdivisions_per_month = 30 * refinement_factor;
    const double maximum_integration_angle = maximum_true_anomaly_step_rad / static_cast<double>(refinement_factor);
    const std::size_t reserved_intervals = (minimum_samples_per_orbit + 360) * refinement_factor;
    integration_intervals_.reserve(reserved_intervals);
    integration_declinations_.reserve(reserved_intervals);
    integration_irradiance_w_m2_.reserve(reserved_intervals);
    for (std::size_t month = 0; month < month_count; ++month) {
        const double mean_month_start = mean_month_duration * (static_cast<double>(month) - 0.5);
        const double mean_month_end = mean_month_duration * (static_cast<double>(month) + 0.5);
        for (std::size_t time_part = 0; time_part < time_subdivisions_per_month; ++time_part) {
            const double mean_start = mean_month_start + mean_month_duration *
                (static_cast<double>(time_part) / time_subdivisions_per_month);
            const double mean_end = time_part + 1 == time_subdivisions_per_month ? mean_month_end :
                mean_month_start + mean_month_duration *
                    (static_cast<double>(time_part + 1) / time_subdivisions_per_month);
            const double start = time_part == 0 ? boundaries[month] :
                true_anomaly_at_mean_anomaly(mean_start, eccentricity);
            const double end = time_part + 1 == time_subdivisions_per_month ? boundaries[month + 1] :
                true_anomaly_at_mean_anomaly(mean_end, eccentricity);
            const double span = end - start;
            const std::size_t count = static_cast<std::size_t>(std::max(
                1.0, std::ceil(span / maximum_integration_angle - 1.0e-10)
            ));
            double previous_angle = start;
            double previous_mean = mean_start;
            for (std::size_t part = 0; part < count; ++part) {
                const double next_angle = part + 1 == count ? end :
                    start + span * static_cast<double>(part + 1) / static_cast<double>(count);
                // Exact elapsed-time boundaries avoid inverting nearly
                // coincident true anomalies in the slow apoapsis portion.
                const double next_mean = part + 1 == count ? mean_end :
                    mean_anomaly_at_true_anomaly(next_angle, eccentricity);
                const double mean_span = next_mean - previous_mean;
                const double angular_span = count == 1 ?
                    short_true_anomaly_span(mean_start, mean_end, eccentricity) : next_angle - previous_angle;
                if (!(mean_span > 0.0) || !(angular_span > 0.0)) {
                    throw std::runtime_error("solar integration interval is not strictly increasing");
                }
                const double factor = angular_span / (mean_span * complement);
                const double longitude = previous_angle + angular_span / 2.0 + periapsis_longitude;
                const double declination = std::asin(std::sin(tilt) * std::sin(longitude));
                integration_intervals_.push_back({
                    month, mean_span / (2.0 * PI), declination, factor,
                    previous_mean, next_mean,
                    time_part + 1 == time_subdivisions_per_month && part + 1 == count
                        ? static_cast<double>(month + 1) / month_count
                        : (next_mean + mean_month_duration / 2.0) / (2.0 * PI)
                });
                integration_declinations_.push_back({std::sin(declination), std::cos(declination)});
                integration_irradiance_w_m2_.push_back(solar_constant_w_m2 * stellar_luminosity * factor);
                if (!std::isfinite(integration_irradiance_w_m2_.back())) {
                    throw std::overflow_error("submonthly solar irradiance is not representable");
                }
                previous_angle = next_angle;
                previous_mean = next_mean;
            }
        }
    }
}

std::array<double, SolarOrbitForcing::month_count> SolarOrbitForcing::monthly_insolation_w_m2(
    double latitude_rad
) const {
    require_latitude(latitude_rad);
    const double latitude_sine = std::sin(latitude_rad);
    const double latitude_cosine = std::cos(latitude_rad);
    std::array<double, month_count> monthly{};
    for (std::size_t month = 0; month < month_count; ++month) {
        // Neumaier compensation retains small contributions beside the large
        // periapsis samples and closely matches Python's math.fsum.
        double sum = 0.0;
        double correction = 0.0;
        for (const DeclinationSample& sample : samples_[month]) {
            const double value = daily_mean_from_trigonometry(
                latitude_sine, latitude_cosine, sample.sine, sample.cosine,
                irradiance_w_m2_[month]
            );
            const double updated = sum + value;
            correction += std::abs(sum) >= std::abs(value) ?
                (sum - updated) + value : (value - updated) + sum;
            sum = updated;
        }
        monthly[month] = (sum + correction) / static_cast<double>(samples_[month].size());
    }
    return monthly;
}

const std::array<double, SolarOrbitForcing::month_count>&
SolarOrbitForcing::monthly_inverse_square_distance_factors() const noexcept {
    return distance_factors_;
}

std::size_t SolarOrbitForcing::sample_count() const noexcept {
    return sample_count_;
}

int SolarOrbitForcing::integration_refinement_level() const noexcept {
    return integration_refinement_level_;
}

const std::vector<SolarOrbitInterval>& SolarOrbitForcing::integration_intervals() const noexcept {
    return integration_intervals_;
}

double SolarOrbitForcing::interval_mean_insolation_w_m2(
    double latitude_rad,
    std::size_t interval_index
) const {
    require_latitude(latitude_rad);
    const DeclinationSample& declination = integration_declinations_.at(interval_index);
    return daily_mean_from_trigonometry(
        std::sin(latitude_rad), std::cos(latitude_rad), declination.sine, declination.cosine,
        integration_irradiance_w_m2_[interval_index]
    );
}

}  // namespace magic_geo::detail
