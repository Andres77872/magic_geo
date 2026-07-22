from __future__ import annotations

import math
from unittest import TestCase

from magic_geo.scaling import fit_power_law


class PowerLawFitTests(TestCase):
    def test_empty_and_degenerate_samples_use_the_fallback_exponent(self) -> None:
        empty = fit_power_law([], fallback_exponent=0.75)
        self.assertEqual(empty.observation_count, 0)
        self.assertEqual(empty.exponent, 0.75)
        self.assertEqual(empty.coefficient, 0.0)
        self.assertEqual(empty.log_rmse, 0.0)

        single = fit_power_law([(4.0, 8.0)], fallback_exponent=0.5)
        self.assertEqual(single.observation_count, 1)
        self.assertEqual(single.exponent, 0.5)
        self.assertAlmostEqual(single.coefficient, 4.0)
        self.assertAlmostEqual(single.log_rmse, 0.0)

    def test_exact_power_law_is_recovered(self) -> None:
        fitted = fit_power_law([(1.0, 3.0), (4.0, 24.0), (9.0, 81.0)])

        self.assertEqual(fitted.observation_count, 3)
        self.assertAlmostEqual(fitted.exponent, 1.5)
        self.assertAlmostEqual(fitted.coefficient, 3.0)
        self.assertAlmostEqual(fitted.log_rmse, 0.0)

    def test_nonfinite_fallback_and_nonpositive_observations_are_rejected(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "fallback exponent must be finite"):
            fit_power_law([], fallback_exponent=math.inf)

        for observations in (
            [(math.nan, 1.0)],
            [(1.0, math.inf)],
            [(0.0, 1.0)],
            [(1.0, -1.0)],
        ):
            with self.subTest(observations=observations):
                with self.assertRaisesRegex(
                    ValueError, "observations must be finite and positive"
                ):
                    fit_power_law(observations)

    def test_unrepresentable_fitted_coefficient_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "coefficient is not finite"):
            fit_power_law([(1.0e-308, 1.0e308)])
