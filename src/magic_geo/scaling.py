from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


HACK_FIT_MINIMUM_BASIN_AREA_KM2 = 1_000_000.0


@dataclass(frozen=True)
class PowerLawFit:
    observation_count: int
    exponent: float
    coefficient: float
    log_rmse: float


def fit_power_law(
    observations: Iterable[tuple[float, float]],
    *,
    fallback_exponent: float = 0.6,
) -> PowerLawFit:
    """Fit y = coefficient * x**exponent by ordinary least squares in log space."""
    if not math.isfinite(fallback_exponent):
        raise ValueError("power-law fallback exponent must be finite")

    logged: list[tuple[float, float]] = []
    for x_value, y_value in observations:
        x = float(x_value)
        y = float(y_value)
        if not math.isfinite(x) or not math.isfinite(y) or x <= 0.0 or y <= 0.0:
            raise ValueError("power-law observations must be finite and positive")
        logged.append((math.log(x), math.log(y)))

    if not logged:
        return PowerLawFit(0, fallback_exponent, 0.0, 0.0)

    count = len(logged)
    mean_x = sum(item[0] for item in logged) / count
    mean_y = sum(item[1] for item in logged) / count
    variance_x = sum((item[0] - mean_x) ** 2 for item in logged)
    if count >= 2 and variance_x > 1.0e-12:
        covariance = sum((item[0] - mean_x) * (item[1] - mean_y) for item in logged)
        exponent = covariance / variance_x
    else:
        exponent = fallback_exponent
    intercept = mean_y - exponent * mean_x
    try:
        coefficient = math.exp(intercept)
    except OverflowError as exc:
        raise ValueError("power-law fitted coefficient is not finite") from exc
    residual_square_sum = sum(
        (log_y - (intercept + exponent * log_x)) ** 2
        for log_x, log_y in logged
    )
    log_rmse = math.sqrt(max(0.0, residual_square_sum / count))
    if not all(math.isfinite(value) for value in (exponent, coefficient, log_rmse)):
        raise ValueError("power-law fit is not finite")
    return PowerLawFit(count, exponent, coefficient, log_rmse)
