from __future__ import annotations

from unittest import TestCase

from magic_geo.hydrology_dynamics import _normalized_overflow_pressure


class HydrologyDynamicsTests(TestCase):
    def test_native_overflow_index_uses_quarter_scale_pressure(self) -> None:
        self.assertEqual(_normalized_overflow_pressure(-1.0), 0.0)
        self.assertEqual(_normalized_overflow_pressure(0.0), 0.0)
        self.assertEqual(_normalized_overflow_pressure(3.0), 0.75)
        self.assertEqual(_normalized_overflow_pressure(4.0), 1.0)
        self.assertEqual(_normalized_overflow_pressure(50.0), 1.0)
