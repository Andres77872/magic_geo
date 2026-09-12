"""Top-of-atmosphere sunlight on a rapidly rotating spherical planet.

Daily geometry follows Berger (1978). Equal-time month boundaries follow
Kepler's equation; integrating in true anomaly analytically cancels the
inverse-square distance factor against the time Jacobian (Paillard, 2026).
See docs/simulation_coherence_research.md for equations and scope.
"""

from __future__ import annotations

import math
from functools import lru_cache

SOLAR_CONSTANT_W_M2 = 1361.0
# Angular resolution is independent of eccentricity. A near-parabolic orbit
# traverses almost all true anomalies in the periapsis month, which must receive
# most of the samples rather than a fixed allocation in elapsed time.
ORBITAL_ANGULAR_SAMPLES = 768
MAXIMUM_TRUE_ANOMALY_STEP_RAD = 2.0 * math.pi / ORBITAL_ANGULAR_SAMPLES
# The configuration has no precession angle. Preserve the circular-calendar
# northern summer peak at month index 5.5; periapsis is at index zero.
SOLAR_LONGITUDE_AT_PERIAPSIS_RAD = math.radians(-75.0)


def daily_mean_insolation(
    latitude_rad: float, declination_rad: float, irradiance_w_m2: float
) -> float:
    """Integrate positive solar zenith cosine over a complete rotation."""
    a = math.sin(latitude_rad) * math.sin(declination_rad)
    b = max(0.0, math.cos(latitude_rad) * math.cos(declination_rad))
    if a >= b:  # Includes the exact-pole limit without tan(latitude).
        return irradiance_w_m2 * max(0.0, a)
    if a <= -b:
        return 0.0
    sunset = math.acos(-a / b)
    return irradiance_w_m2 * (sunset * a + b * math.sin(sunset)) / math.pi


@lru_cache(maxsize=128)
def _orbital_samples(
    axial_tilt_deg: float, eccentricity: float, months: int
) -> tuple[tuple[tuple[float, float], ...], ...]:
    tilt = math.radians(axial_tilt_deg)
    result = []
    mean_month_duration = 2.0 * math.pi / months
    eccentricity_complement = math.sqrt((1.0 - eccentricity) * (1.0 + eccentricity))
    boundaries = [
        _true_anomaly_at_mean_anomaly(
            mean_month_duration * (month - 0.5), eccentricity
        )
        for month in range(months + 1)
    ]
    for month in range(months):
        start, end = boundaries[month], boundaries[month + 1]
        span = end - start
        count = max(1, math.ceil(span / MAXIMUM_TRUE_ANOMALY_STEP_RAD - 1.0e-10))
        # (a/r)^2 dM = dν / sqrt(1-e²). The mean distance factor
        # is exact for these month boundaries, even as eccentricity approaches 1.
        mean_distance_factor = span / (mean_month_duration * eccentricity_complement)
        samples = []
        for sample in range(count):
            true_anomaly = start + span * (sample + 0.5) / count
            longitude = true_anomaly + SOLAR_LONGITUDE_AT_PERIAPSIS_RAD
            declination = math.asin(math.sin(tilt) * math.sin(longitude))
            samples.append((declination, mean_distance_factor))
        result.append(tuple(samples))
    return tuple(result)


def _true_anomaly_at_mean_anomaly(mean_anomaly: float, eccentricity: float) -> float:
    """Invert the strictly monotone Kepler equation without Newton divergence."""
    revolutions = math.floor((mean_anomaly + math.pi) / (2.0 * math.pi))
    mean = mean_anomaly - revolutions * 2.0 * math.pi
    lower, upper = -math.pi, math.pi
    for _ in range(60):
        anomaly = (lower + upper) / 2.0
        if anomaly - eccentricity * math.sin(anomaly) < mean:
            lower = anomaly
        else:
            upper = anomaly
    anomaly = (lower + upper) / 2.0
    # Half-angle form avoids subtracting cos(E)-e near periapsis.
    true_anomaly = 2.0 * math.atan2(
        math.sqrt(1.0 + eccentricity) * math.sin(anomaly / 2.0),
        math.sqrt(1.0 - eccentricity) * math.cos(anomaly / 2.0),
    )
    return true_anomaly + revolutions * 2.0 * math.pi


def seasonal_insolation_series(
    lat_rad: float,
    stellar_luminosity: float,
    axial_tilt_deg: float,
    orbital_eccentricity: float,
    months: int,
) -> tuple[list[float], list[float]]:
    """Return equal-time monthly means in W/m² and dimensionless (a/r)².

    Luminosity multiplies irradiance at the implicit 1 AU semimajor axis.
    These are monthly means of daily means, not instantaneous monthly samples.
    """
    if not math.isfinite(orbital_eccentricity) or not 0.0 <= orbital_eccentricity < 1.0:
        raise ValueError("orbital_eccentricity must be finite and in [0, 1)")
    samples = _orbital_samples(
        max(0.0, min(90.0, axial_tilt_deg)),
        orbital_eccentricity,
        max(1, months),
    )
    monthly, factors = [], []
    for month in samples:
        monthly.append(math.fsum(
            daily_mean_insolation(lat_rad, declination, SOLAR_CONSTANT_W_M2 * stellar_luminosity * factor)
            for declination, factor in month
        ) / len(month))
        factors.append(month[0][1])
    return monthly, factors
