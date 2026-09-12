"""Reproduce the independent near-parabolic native solar test fixtures.

Run with any Python 3 interpreter; only the standard library is used. The
eccentricity is exactly 1 - 2**-53, the largest binary64 number below one.
Calendar boundaries use mathematical pi and twelve equal-time months, with
periapsis at the center of month zero. Native binary64 calendar rounding is
therefore subject to the test's separate floating-point tolerance.

Gauss-Legendre pi, Taylor sine/cosine, half-angle-reduced arctangent, and a
400-iteration Kepler bisection provide an implementation independent of the
production double-precision angle-difference formula. Repeating at 80 and
100 decimal digits verifies at least 60 significant digits of the fixtures.
This is a research oracle, not a production forcing replay implementation.
"""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_FLOOR, localcontext


def pi_decimal() -> Decimal:
    a = Decimal(1)
    b = 1 / Decimal(2).sqrt()
    t = Decimal(1) / 4
    p = Decimal(1)
    for _ in range(9):
        next_a = (a + b) / 2
        b = (a * b).sqrt()
        t -= p * (a - next_a) ** 2
        a = next_a
        p *= 2
    return (a + b) ** 2 / (4 * t)


def sine(x: Decimal) -> Decimal:
    squared = x * x
    term = total = x
    for k in range(1, 300):
        term *= -squared / ((2 * k) * (2 * k + 1))
        previous = total
        total += term
        if previous == total:
            return total
    raise ArithmeticError("sine series did not converge")


def cosine(x: Decimal) -> Decimal:
    squared = x * x
    term = total = Decimal(1)
    for k in range(1, 300):
        term *= -squared / ((2 * k - 1) * (2 * k))
        previous = total
        total += term
        if previous == total:
            return total
    raise ArithmeticError("cosine series did not converge")


def arctangent(x: Decimal, pi: Decimal) -> Decimal:
    if x < 0:
        return -arctangent(-x, pi)
    if x > 1:
        return pi / 2 - arctangent(1 / x, pi)
    scale = 1
    for _ in range(5):
        x /= 1 + (1 + x * x).sqrt()
        scale *= 2
    total = term = x
    for k in range(1, 300):
        term *= -x * x
        previous = total
        total += term / (2 * k + 1)
        if total == previous:
            return scale * total
    raise ArithmeticError("arctangent series did not converge")


def eccentric_at_mean(mean: Decimal, e: Decimal, pi: Decimal) -> Decimal:
    revolutions = ((mean + pi) / (2 * pi)).to_integral_value(rounding=ROUND_FLOOR)
    mean -= 2 * pi * revolutions
    lower, upper = -pi, pi
    for _ in range(400):
        midpoint = (lower + upper) / 2
        if midpoint - e * sine(midpoint) < mean:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2 + revolutions * 2 * pi


def true_at_mean(mean: Decimal, e: Decimal, pi: Decimal) -> Decimal:
    eccentric = eccentric_at_mean(mean, e, pi)
    revolutions = ((eccentric + pi) / (2 * pi)).to_integral_value(rounding=ROUND_FLOOR)
    eccentric -= 2 * pi * revolutions
    if eccentric == 0:
        return revolutions * 2 * pi
    ratio = ((1 - e) / (1 + e)).sqrt() * cosine(eccentric / 2) / abs(sine(eccentric / 2))
    anomaly = pi - 2 * arctangent(ratio, pi)
    return (anomaly if eccentric > 0 else -anomaly) + revolutions * 2 * pi


def reference(precision: int) -> dict[str, object]:
    with localcontext() as context:
        context.prec = precision
        pi = pi_decimal()
        e = 1 - Decimal(2) ** -53
        complement = ((1 - e) * (1 + e)).sqrt()
        boundaries = [
            true_at_mean(pi / 6 * (Decimal(month) - Decimal("0.5")), e, pi)
            for month in range(13)
        ]
        factors = [
            (end - start) / (pi / 6 * complement)
            for start, end in zip(boundaries, boundaries[1:])
        ]
        apoapsis = {}
        for level in (0, 3, 6, 10):
            start = pi
            end = pi + 2 * pi / (360 * 2**level)
            apoapsis[str(level)] = str(
                (true_at_mean(end, e, pi) - true_at_mean(start, e, pi))
                / ((end - start) * complement)
            )
        return {
            "eccentricity": str(e),
            "monthly_mean_inverse_square_distance": [str(value) for value in factors],
            "annual_mean_inverse_square_distance": str(sum(factors) / 12),
            "first_interval_after_apoapsis_by_refinement_level": apoapsis,
            "physical_minimum_inverse_square_distance": str(1 / (1 + e) ** 2),
        }


def numeric_leaves(value: object) -> list[Decimal]:
    if isinstance(value, dict):
        return [number for child in value.values() for number in numeric_leaves(child)]
    if isinstance(value, list):
        return [number for child in value for number in numeric_leaves(child)]
    return [Decimal(str(value))]


def main() -> None:
    lower = reference(80)
    higher = reference(100)
    with localcontext() as context:
        context.prec = 100
        for first, second in zip(numeric_leaves(lower), numeric_leaves(higher), strict=True):
            if abs(first - second) > Decimal("1e-60") * abs(second):
                raise ArithmeticError("80- and 100-digit oracles disagree")
    print(json.dumps({"verified_decimal_digits": 60, **higher}, indent=2))


if __name__ == "__main__":
    main()
