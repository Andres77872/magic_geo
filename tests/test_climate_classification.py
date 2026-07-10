from unittest import TestCase

from magic_geo.climate_dynamics import classify_koppen_geiger


def _cell(temperatures: list[float], precipitation: list[float], latitude: float = 45.0) -> dict[str, object]:
    return {
        "temperature_monthly_c": temperatures,
        "precipitation_monthly_mm": precipitation,
        "lat_deg": latitude,
    }


class ClimateClassificationTests(TestCase):
    def test_koppen_geiger_representative_classes(self) -> None:
        cases = {
            "Af": _cell([25.0] * 12, [100.0] * 12),
            "Am": _cell([25.0] * 12, [40.0] + [160.0] * 11),
            "Aw": _cell([25.0] * 12, [10.0] + [100.0] * 11),
            "BWh": _cell([25.0] * 12, [10.0] * 12),
            "BSk": _cell([10.0] * 12, [20.0] * 12),
            "Csa": _cell(
                [5.0, 7.0, 10.0, 14.0, 18.0, 23.0, 26.0, 25.0, 20.0, 15.0, 10.0, 6.0],
                [100.0, 100.0, 100.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 100.0, 100.0, 100.0],
            ),
            "Dfb": _cell(
                [-15.0, -10.0, -2.0, 6.0, 12.0, 18.0, 21.0, 19.0, 12.0, 6.0, -2.0, -10.0],
                [60.0] * 12,
            ),
            "ET": _cell([-15.0, -12.0, -8.0, -3.0, 1.0, 4.0, 5.0, 4.0, 1.0, -4.0, -9.0, -13.0], [30.0] * 12),
            "EF": _cell([-25.0, -22.0, -18.0, -12.0, -8.0, -4.0, -2.0, -3.0, -7.0, -13.0, -19.0, -23.0], [20.0] * 12),
        }

        for expected, cell in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(classify_koppen_geiger(cell), expected)
