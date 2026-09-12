#pragma once

#include <array>
#include <cstddef>
#include <numbers>
#include <vector>

namespace magic_geo::detail {

// Mean of the positive solar zenith cosine over a complete rotation. Angles
// are radians; irradiance is the flux perpendicular to the incident sunlight.
double daily_mean_solar_insolation_w_m2(
    double latitude_rad,
    double declination_rad,
    double irradiance_w_m2
);

struct SolarOrbitInterval {
    std::size_t month_index = 0;
    double duration_fraction_of_year = 0.0;
    // Angular midpoint node. The interval-mean insolation uses midpoint
    // quadrature in true anomaly and the exact Kepler time Jacobian.
    double declination_rad = 0.0;
    double inverse_square_distance_factor = 0.0;
    // Original binary64 orbital operands and an absolute calendar coordinate.
    // These supplement (and do not alter) the existing duration/flux formula.
    double mean_anomaly_begin_rad = 0.0;
    double mean_anomaly_end_rad = 0.0;
    double end_fraction_of_year = 0.0;
};

// Reusable orbital quadrature for a rapidly rotating sphere at an implicit
// semimajor axis of 1 AU. Months have equal elapsed duration; periapsis is at
// the center of month zero and its solar longitude is -75 degrees. These
// conventions and the quadrature match magic_geo.insolation in Python.
// Numerical support for e approaching one does not validate daily averaging
// when orbital motion during one rotation is appreciable.
class SolarOrbitForcing {
public:
    static constexpr std::size_t month_count = 12;
    static constexpr std::size_t minimum_samples_per_orbit = 768;
    static constexpr double solar_constant_w_m2 = 1361.0;
    static constexpr double solar_longitude_at_periapsis_deg = -75.0;
    static constexpr double maximum_true_anomaly_step_rad =
        2.0 * std::numbers::pi / static_cast<double>(minimum_samples_per_orbit);
    static constexpr double maximum_interval_fraction_of_year = 1.0 / 360.0;
    static constexpr int maximum_integration_refinement_level = 10;

    // Finite tilt in [0,90], eccentricity in [0,1), nonnegative luminosity.
    // Integration refinement halves both the angular and elapsed-time limits
    // per level, recomputing astronomical fluences. It does not change the
    // Python-compatible monthly API. Levels outside [0,10] fail explicitly;
    // this is a work bound, not an orbital or physical applicability bound.
    // Invalid values throw std::invalid_argument; inputs are never clipped.
    SolarOrbitForcing(
        double tilt_degrees,
        double eccentricity,
        double stellar_luminosity,
        int integration_refinement_level = 0
    );

    std::array<double, month_count> monthly_insolation_w_m2(double latitude_rad) const;
    const std::array<double, month_count>& monthly_inverse_square_distance_factors() const noexcept;
    // Count for the Python-compatible monthly quadrature, not integration_intervals().
    std::size_t sample_count() const noexcept;
    int integration_refinement_level() const noexcept;

    // Ordered, immutable submonthly intervals spanning the same year as the
    // monthly API. Every month has duration 1/12 year. Each interval respects
    // both the true-anomaly angular bound and a maximum duration of 1/360 year.
    // Exact solar time weights do not guarantee nonlinear thermal accuracy:
    // the climate solver must still assess timestep/refinement convergence.
    const std::vector<SolarOrbitInterval>& integration_intervals() const noexcept;
    double interval_mean_insolation_w_m2(double latitude_rad, std::size_t interval_index) const;

private:
    struct DeclinationSample {
        double sine = 0.0;
        double cosine = 0.0;
    };

    std::array<std::vector<DeclinationSample>, month_count> samples_;
    std::array<double, month_count> distance_factors_{};
    std::array<double, month_count> irradiance_w_m2_{};
    std::size_t sample_count_ = 0;
    int integration_refinement_level_ = 0;
    std::vector<SolarOrbitInterval> integration_intervals_;
    std::vector<DeclinationSample> integration_declinations_;
    std::vector<double> integration_irradiance_w_m2_;
};

}  // namespace magic_geo::detail
