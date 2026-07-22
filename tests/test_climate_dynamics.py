"""Behavioural tests for :mod:`magic_geo.climate_dynamics`.

Every case here is hand-built: no world generation, no fixtures. The module is a
pure function over cell dictionaries, so the cheapest way to pin it down is to
feed it monthly climatologies whose Koppen code / seasonality regime / humidity
ledger can be derived by hand and asserted exactly.

``tests/test_climate_classification.py`` pins a set of headline Koppen codes
(Af/Am/Aw/BWh/BSk/Csa/Dfb/ET/EF); the headline table here deliberately picks the
ones it does not (BWk/BSh/Cwa/Cwb/Dfd/Csb), plus the enrichment entry point. The
boundary tables below reuse whatever code lands on the far side of the constant
under test, so they do overlap with that file by construction.

Where a branch turns on a numeric constant the tests use *matched pairs* that
straddle it by the smallest amount the arithmetic allows, so that nudging the
constant in the module flips an assertion. The constants that are provably
unreachable or redundant are called out in comments rather than asserted.
"""

from __future__ import annotations

from typing import Any
from unittest import TestCase

from magic_geo.climate_dynamics import (
    CLIMATE_CLASSIFICATION_LIMITATION,
    CLIMATE_CLASSIFICATION_TYPE,
    CLIMATE_CLASS_NAMES,
    _cell_seasonality,
    classify_koppen_geiger,
    enrich_world_with_seasonal_climate_history,
)


# The Koppen codes this classifier can emit, spelled out independently of the
# module: three A codes, the B grid (desert/steppe x hot/cold), the C grid
# (dry-summer/dry-winter/humid x hot/warm/cold summer), the D grid (same plus
# the "very cold winter" sub-code, which the classifier only allows for D), and
# the two E codes. 3 + 4 + 9 + 12 + 2 = 30.
EXPECTED_CLIMATE_CODES = frozenset(
    {"Af", "Am", "Aw", "ET", "EF"}
    | {f"B{moisture}{temperature}" for moisture in "WS" for temperature in "hk"}
    | {f"C{precipitation}{temperature}" for precipitation in "swf" for temperature in "abc"}
    | {f"D{precipitation}{temperature}" for precipitation in "swf" for temperature in "abcd"}
)

# A monsoonal, winter-dry, hot-summer northern profile -> "Cwa".
CWA_TEMPERATURE_C = [10.0, 12.0, 16.0, 20.0, 24.0, 28.0, 30.0, 29.0, 25.0, 20.0, 14.0, 11.0]
CWA_PRECIPITATION_MM = [5.0, 5.0, 10.0, 50.0, 150.0, 250.0, 300.0, 250.0, 150.0, 10.0, 5.0, 5.0]

# A mediterranean profile written in *calendar* order: wet in Apr-Sep, warm in
# Dec-Feb. On the southern hemisphere that is a dry-summer C climate ("Csb");
# feeding the identical arrays in at a northern latitude flips the summer/winter
# month sets and yields a dry-*winter* code instead ("Cwb").
MEDITERRANEAN_TEMPERATURE_C = [20.0, 19.0, 17.0, 13.0, 9.0, 6.0, 5.0, 7.0, 10.0, 13.0, 16.0, 19.0]
MEDITERRANEAN_PRECIPITATION_MM = [10.0, 10.0, 20.0, 100.0, 120.0, 150.0, 150.0, 120.0, 100.0, 20.0, 10.0, 10.0]

# Subarctic continental: three months above 10 C, coldest month at -45 C, which
# is the "d" (very cold winter) temperature sub-code.
DFD_TEMPERATURE_C = [-45.0, -42.0, -35.0, -20.0, -2.0, 12.0, 16.0, 12.0, 2.0, -18.0, -35.0, -43.0]

WINTER_WET_PRECIPITATION_MM = [150.0, 150.0, 100.0, 50.0, 30.0, 20.0, 20.0, 20.0, 30.0, 50.0, 100.0, 150.0]
# The same shape rolled by six months: the peak moves from January to June.
SUMMER_WET_PRECIPITATION_MM = [20.0, 20.0, 30.0, 50.0, 100.0, 150.0, 150.0, 150.0, 100.0, 50.0, 30.0, 20.0]

# The ferrel group is the single "Cwa" cell, so its monthly evaporation is the
# 600 mm/y annual total split by the temperature weight max(0.05, 1 + T/35).
# Normalising that weight collapses the 35s: 600 * (35 + T_m) / (420 + sum(T)).
FERREL_EVAPORATION_MM = [
    600.0 * (35.0 + temperature) / (420.0 + sum(CWA_TEMPERATURE_C))
    for temperature in CWA_TEMPERATURE_C
]


def _cell(
    temperature_monthly_c: list[float],
    precipitation_monthly_mm: list[float],
    lat_deg: float = 45.0,
) -> dict[str, Any]:
    return {
        "temperature_monthly_c": list(temperature_monthly_c),
        "precipitation_monthly_mm": list(precipitation_monthly_mm),
        "lat_deg": lat_deg,
    }


def _seasonal_profile(summer_mm: float, winter_mm: float) -> list[float]:
    """Northern-hemisphere profile: ``summer_mm`` in Apr-Sep, ``winter_mm`` else."""

    return [winter_mm] * 3 + [summer_mm] * 6 + [winter_mm] * 3


def _winter_peaked_profile(base_mm: float, amplitude_mm: float) -> list[float]:
    """Flat ``base_mm`` everywhere with ``amplitude_mm`` added to Dec/Jan/Feb."""

    profile = [base_mm] * 12
    for month_index in (0, 1, 11):
        profile[month_index] += amplitude_mm
    return profile


def _synthetic_cells() -> list[dict[str, Any]]:
    """Three cells, two of which share the ``hadley`` atmospheric cell.

    Cell 0 is a wet tropical cell (Af / humid_stable), cell 1 a hot desert
    (BWh / arid_seasonal) and cell 2 a winter-dry monsoon cell (Cwa /
    monsoonal). Cell 1 exercises the ``wind_monthly_*`` component arrays while
    cells 0 and 2 exercise the scalar ``wind_east`` / ``wind_north`` fallback.
    """

    return [
        {
            "id": 0,
            "atmospheric_cell": "hadley",
            "lat_deg": 10.0,
            "temperature_monthly_c": [26.0] * 12,
            "precipitation_monthly_mm": [100.0] * 12,
            "vapor_evaporation_mm_y": 900.0,
            "moisture_convergence_mm_y": 300.0,
            "wind_east": 3.0,
            "wind_north": -1.0,
            "vertical_velocity_index": 0.4,
            "wind_divergence_index": -0.2,
        },
        {
            "id": 1,
            "atmospheric_cell": "hadley",
            "lat_deg": 20.0,
            "temperature_monthly_c": [30.0] * 12,
            "precipitation_monthly_mm": [5.0] * 12,
            "vapor_evaporation_mm_y": 1800.0,
            "moisture_convergence_mm_y": 0.0,
            "wind_monthly_east": [2.0] * 12,
            "wind_monthly_north": [0.5] * 12,
            "vertical_velocity_index": -0.6,
            "wind_divergence_index": 0.5,
        },
        {
            "id": 2,
            "atmospheric_cell": "ferrel",
            "lat_deg": 45.0,
            "temperature_monthly_c": list(CWA_TEMPERATURE_C),
            "precipitation_monthly_mm": list(CWA_PRECIPITATION_MM),
            "vapor_evaporation_mm_y": 600.0,
            "moisture_convergence_mm_y": 120.0,
            "wind_east": 6.0,
            "wind_north": 2.0,
            "vertical_velocity_index": 0.1,
            "wind_divergence_index": 0.3,
        },
    ]


def _enriched_world() -> dict[str, Any]:
    return enrich_world_with_seasonal_climate_history({"cells": _synthetic_cells()})


class KoppenGeigerClassificationTests(TestCase):
    def test_koppen_table_covers_verified_profiles(self) -> None:
        cases = [
            # Cold desert: 60 mm/y against a 240 mm threshold (20*5 + 140),
            # below half the threshold, mean annual temperature under 18 C.
            ("BWk", _cell([5.0] * 12, [5.0] * 12)),
            # Hot steppe: 540 mm/y sits between half of and all of the 640 mm
            # threshold, and 25 C mean annual temperature gives the "h" suffix.
            ("BSh", _cell([25.0] * 12, [45.0] * 12)),
            ("Cwa", _cell(CWA_TEMPERATURE_C, CWA_PRECIPITATION_MM)),
            ("Dfd", _cell(DFD_TEMPERATURE_C, [15.0] * 12)),
            ("Csb", _cell(MEDITERRANEAN_TEMPERATURE_C, MEDITERRANEAN_PRECIPITATION_MM, lat_deg=-40.0)),
        ]
        for expected, cell in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_koppen_geiger(cell), expected)

    def test_arid_threshold_branch_selection(self) -> None:
        # Same 10 C year and the same annual total in each pair; only the
        # *distribution* moves, which selects a different aridity threshold:
        # 20T + 280 when >= 70% falls in summer, 20T when >= 70% falls in
        # winter, 20T + 140 otherwise. At 10 C that is 480 / 200 / 340 mm.
        cases = [
            # 402 mm/y is under 480 but over 340.
            ("BSk", _seasonal_profile(62.0, 5.0)),
            ("Cfc", [33.5] * 12),
            # 270 mm/y is under 340 but over 200.
            ("BSk", [22.5] * 12),
            ("Csc", _seasonal_profile(5.0, 40.0)),
        ]
        for expected, precipitation in cases:
            with self.subTest(expected=expected, annual_mm=sum(precipitation)):
                self.assertEqual(
                    classify_koppen_geiger(_cell([10.0] * 12, precipitation)),
                    expected,
                )

        # The two seasonal thresholds, pinned to the millimetre. Summer-dominant
        # is 20*10 + 280 = 480; winter-dominant is 20*10 + 0 = 200.
        boundaries = [
            ("Cfc", _seasonal_profile(70.0, 10.0), 480.0),
            ("BSk", [10.0, 10.0, 9.0] + [70.0] * 6 + [10.0] * 3, 479.0),
            ("Csc", [30.0] * 3 + [3.0, 3.0, 3.0, 3.0, 4.0, 4.0] + [30.0] * 3, 200.0),
            ("BSk", [30.0] * 3 + [3.0] * 5 + [4.0] + [30.0] * 3, 199.0),
        ]
        for expected, precipitation, annual_mm in boundaries:
            with self.subTest(expected=expected, annual_mm=annual_mm):
                self.assertEqual(sum(precipitation), annual_mm)
                self.assertEqual(
                    classify_koppen_geiger(_cell([10.0] * 12, precipitation)),
                    expected,
                )

    def test_arid_threshold_constants_are_exact(self) -> None:
        # Every profile below is flat enough that the "otherwise" threshold
        # 20 * 10 + 140 = 340 mm applies, and the arid/steppe split sits at
        # exactly half of it, 170 mm. Each pair straddles a constant by 1-2 mm,
        # and the boundary member pins the comparison as strict (``<``).
        cases = [
            ("BSk", [28.25] * 12, 339.0),  # just below the 340 mm threshold
            ("Cfc", [28.0] * 11 + [32.0], 340.0),  # exactly at it -> not arid
            ("BWk", [14.0] * 12, 168.0),  # just below half -> desert
            ("BSk", [14.0] * 11 + [16.0], 170.0),  # exactly half -> steppe
        ]
        for expected, precipitation, annual_mm in cases:
            with self.subTest(expected=expected, annual_mm=annual_mm):
                self.assertEqual(sum(precipitation), annual_mm)
                self.assertEqual(
                    classify_koppen_geiger(_cell([10.0] * 12, precipitation)),
                    expected,
                )
        # The h/k suffix splits at a mean annual temperature of exactly 18 C.
        self.assertEqual(classify_koppen_geiger(_cell([18.0] * 12, [10.0] * 12)), "BWh")
        self.assertEqual(classify_koppen_geiger(_cell([17.9] * 12, [10.0] * 12)), "BWk")

    def test_precipitation_subcode_boundaries(self) -> None:
        # All six cells are 15 C year-round, so the temperate sub-code is always
        # "b" and only the s/w/f letter moves. Northern hemisphere: summer is
        # Apr-Sep, winter is Oct-Mar.
        dry_winter = [10.0] * 3 + [100.0] * 6 + [10.0] * 3
        cases = [
            # "w" needs min(winter) < max(summer) / 10 == 10.0, strictly.
            ("Cfb", list(dry_winter)),
            ("Cwb", [9.9] + dry_winter[1:]),
            # "s" needs min(summer) < 40.0, strictly.
            ("Cfb", _seasonal_profile(40.0, 150.0)),
            ("Csb", _seasonal_profile(39.9, 150.0)),
            # ... and min(summer) < max(winter) / 3 == 39.0, strictly.
            ("Cfb", _seasonal_profile(39.0, 117.0)),
            ("Csb", _seasonal_profile(39.0, 117.3)),
        ]
        for index, (expected, precipitation) in enumerate(cases):
            with self.subTest(case=index, expected=expected):
                self.assertEqual(
                    classify_koppen_geiger(_cell([15.0] * 12, precipitation)),
                    expected,
                )

    def test_temperature_subcode_boundaries(self) -> None:
        # 600 mm/y flat keeps every one of these out of the B classes and makes
        # the precipitation sub-code "f", so only the trailing letter moves.
        cases = [
            # "a" needs a hottest month of at least 22 C, inclusive.
            ("Cfa", [5.0] * 11 + [22.0]),
            ("Cfc", [5.0] * 11 + [21.9]),
            # "b" needs four months strictly above 10 C; three is not enough.
            ("Dfb", [0.0] * 8 + [11.0] * 4),
            ("Dfc", [0.0] * 9 + [11.0] * 3),
            # "d" needs a D class with a coldest month at or below -38 C.
            ("Dfd", [-38.0] * 9 + [11.0] * 3),
            ("Dfc", [-37.9] * 9 + [11.0] * 3),
        ]
        for index, (expected, temperature) in enumerate(cases):
            with self.subTest(case=index, expected=expected):
                self.assertEqual(
                    classify_koppen_geiger(_cell(temperature, [50.0] * 12)),
                    expected,
                )

        # The C/D main class splits on a coldest month strictly above 0 C, so a
        # coldest month of exactly 0 C is still continental.
        self.assertEqual(classify_koppen_geiger(_cell([0.0] * 8 + [11.0] * 4, [50.0] * 12)), "Dfb")
        self.assertEqual(classify_koppen_geiger(_cell([0.1] * 8 + [11.0] * 4, [50.0] * 12)), "Cfb")

    def test_southern_hemisphere_flips_summer_and_winter_months(self) -> None:
        southern = _cell(MEDITERRANEAN_TEMPERATURE_C, MEDITERRANEAN_PRECIPITATION_MM, lat_deg=-40.0)
        northern = _cell(MEDITERRANEAN_TEMPERATURE_C, MEDITERRANEAN_PRECIPITATION_MM, lat_deg=40.0)
        # Identical arrays; only the sign of the latitude differs. Apr-Sep is
        # the wet half, which reads as a dry summer south of the equator and a
        # dry winter north of it.
        self.assertEqual(classify_koppen_geiger(southern), "Csb")
        self.assertEqual(classify_koppen_geiger(northern), "Cwb")

    def test_equator_counts_as_northern_hemisphere(self) -> None:
        # ``lat_deg >= 0.0`` takes the northern branch, so lat 0.0 must agree
        # with lat +40.0 rather than with lat -40.0.
        equatorial = _cell(MEDITERRANEAN_TEMPERATURE_C, MEDITERRANEAN_PRECIPITATION_MM, lat_deg=0.0)
        self.assertEqual(classify_koppen_geiger(equatorial), "Cwb")

    def test_scalar_fallbacks_are_spread_across_twelve_months(self) -> None:
        # ``temperature_c`` is an annual *mean*: it is multiplied by 12 on the
        # way in and divided by 12 on the way out, so each of the three cases
        # below flips to a different code if either half of that round trip is
        # dropped. ``precipitation_mm_y`` is an annual *total* and is only
        # divided.
        cases = [
            # 2 C every month -> under the 10 C hottest-month bar. Without the
            # /12 it would read as 24 C every month, i.e. "Af".
            ("ET", {"temperature_c": 2.0, "precipitation_mm_y": 800.0, "lat_deg": 50.0}),
            # 20 C every month and 125 mm every month -> tropical rainforest.
            # Without the *12 it would read as 1.67 C every month, i.e. "ET".
            ("Af", {"temperature_c": 20.0, "precipitation_mm_y": 1500.0, "lat_deg": 50.0}),
            # 200 mm/y at 10 C is under the 340 mm arid threshold but over half
            # of it. Without the /12 it would be 2400 mm/y, i.e. "Cfc".
            (
                "BSk",
                {
                    "temperature_monthly_c": [10.0] * 12,
                    "precipitation_mm_y": 200.0,
                    "lat_deg": 50.0,
                },
            ),
        ]
        for expected, cell in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_koppen_geiger(cell), expected)

    def test_every_legend_code_has_a_name(self) -> None:
        # Assert the whole key set, not just its size: a mistyped code would
        # keep the count at 30 and would still round-trip through the legend,
        # which is built from this same mapping.
        self.assertEqual(len(EXPECTED_CLIMATE_CODES), 30)
        self.assertEqual(set(CLIMATE_CLASS_NAMES), set(EXPECTED_CLIMATE_CODES))
        self.assertEqual(len(set(CLIMATE_CLASS_NAMES.values())), 30)
        self.assertEqual(CLIMATE_CLASS_NAMES["BWk"], "cold_desert")
        self.assertEqual(CLIMATE_CLASS_NAMES["Csb"], "temperate_dry_warm_summer")
        self.assertEqual(CLIMATE_CLASS_NAMES["Dfd"], "cold_humid_very_cold_winter")

    def test_every_emitted_code_is_a_known_code(self) -> None:
        # Sweep the classifier over a grid of climates and check it can never
        # emit a code the legend does not carry.
        emitted = set()
        for mean_temperature in (-40.0, -20.0, -5.0, 0.5, 12.0, 19.0, 26.0):
            for amplitude in (0.0, 15.0, 30.0):
                temperature = [
                    mean_temperature + amplitude * (1.0 if 3 <= month <= 8 else -1.0)
                    for month in range(12)
                ]
                for summer_mm, winter_mm in ((1.0, 1.0), (60.0, 3.0), (3.0, 60.0), (90.0, 90.0)):
                    for latitude in (-45.0, 45.0):
                        cell = _cell(temperature, _seasonal_profile(summer_mm, winter_mm), latitude)
                        emitted.add(classify_koppen_geiger(cell))
        self.assertTrue(emitted)
        self.assertEqual(emitted - EXPECTED_CLIMATE_CODES, set())


class SeasonalityRegimeTests(TestCase):
    def _regime(self, precipitation_monthly_mm: list[float], lat_deg: float = 45.0) -> str:
        cell = _cell([15.0] * 12, precipitation_monthly_mm, lat_deg=lat_deg)
        return _cell_seasonality(cell)[3]

    def test_seasonality_regime_table(self) -> None:
        cases = [
            # 60 mm/y total, at or under the 150 mm arid cutoff.
            ("arid_seasonal", [5.0] * 12),
            # 990 mm/y, monsoon index 0.293 (>= 0.22) and a 300 mm peak well
            # above 1.65x the 82.5 mm monthly mean.
            ("monsoonal", [10.0] * 6 + [300.0] * 3 + [10.0] * 3),
            # Peak in January -> a winter month north of the equator.
            ("winter_wet", WINTER_WET_PRECIPITATION_MM),
            # Same shape rolled six months -> peak in June.
            ("summer_wet", SUMMER_WET_PRECIPITATION_MM),
            # Perfectly flat: monsoon index 0.0, so no wet regime applies.
            ("humid_stable", [80.0] * 12),
        ]
        for expected, precipitation in cases:
            with self.subTest(expected=expected):
                self.assertEqual(self._regime(precipitation), expected)

    def test_arid_precipitation_cutoff_is_exactly_150_mm(self) -> None:
        at_cutoff = [12.5] * 12
        above_cutoff = [12.6] * 12
        self.assertEqual(sum(at_cutoff), 150.0)
        # ``<= 150.0``: the boundary itself is arid.
        self.assertEqual(self._regime(at_cutoff), "arid_seasonal")
        # 151.2 mm/y with a flat profile has nowhere else to go but humid.
        self.assertEqual(self._regime(above_cutoff), "humid_stable")

    def test_monsoon_index_cutoff_is_exactly_0_22(self) -> None:
        # 1000 mm/y with a 285 mm December peak over an otherwise flat 65 mm:
        # (285 - 65) / 1000 = 0.22 exactly, which is inclusive.
        at_cutoff = [65.0] * 11 + [285.0]
        below_cutoff = [65.1] * 11 + [285.0]
        self.assertEqual(sum(at_cutoff), 1000.0)
        self.assertEqual(_cell_seasonality(_cell([15.0] * 12, at_cutoff))[2], 0.22)
        self.assertEqual(self._regime(at_cutoff), "monsoonal")
        # A hair below, and the same December peak falls through to the winter
        # branch instead.
        self.assertLess(_cell_seasonality(_cell([15.0] * 12, below_cutoff))[2], 0.22)
        self.assertEqual(self._regime(below_cutoff), "winter_wet")

    def test_monsoon_index_threshold_gates_the_wet_regimes(self) -> None:
        # Both profiles peak in December/January/February, so only the 0.12
        # monsoon-index floor decides between winter_wet and humid_stable.
        below = _winter_peaked_profile(100.0, 170.0)
        above = _winter_peaked_profile(100.0, 250.0)
        self.assertAlmostEqual(_cell_seasonality(_cell([15.0] * 12, below))[2], 0.099415, places=6)
        self.assertAlmostEqual(_cell_seasonality(_cell([15.0] * 12, above))[2], 0.128205, places=6)
        self.assertEqual(self._regime(below), "humid_stable")
        self.assertEqual(self._regime(above), "winter_wet")

        # The floor itself: an amplitude of 225 mm gives 225 / 1875 == 0.12
        # exactly, and the comparison is inclusive.
        at_floor = _winter_peaked_profile(100.0, 225.0)
        below_floor = _winter_peaked_profile(100.0, 224.9)
        self.assertEqual(_cell_seasonality(_cell([15.0] * 12, at_floor))[2], 0.12)
        self.assertLess(_cell_seasonality(_cell([15.0] * 12, below_floor))[2], 0.12)
        self.assertEqual(self._regime(at_floor), "winter_wet")
        self.assertEqual(self._regime(below_floor), "humid_stable")

    def test_flat_winter_peaked_profile_collapses_to_humid_stable(self) -> None:
        flat = [100.0, 100.0, 90.0, 80.0, 75.0, 70.0, 70.0, 70.0, 75.0, 80.0, 90.0, 100.0]
        self.assertAlmostEqual(_cell_seasonality(_cell([15.0] * 12, flat))[2], 0.03, places=6)
        self.assertEqual(self._regime(flat), "humid_stable")

    def test_southern_hemisphere_flips_the_wet_season_regime(self) -> None:
        self.assertEqual(self._regime(WINTER_WET_PRECIPITATION_MM, lat_deg=45.0), "winter_wet")
        self.assertEqual(self._regime(WINTER_WET_PRECIPITATION_MM, lat_deg=-45.0), "summer_wet")

    def test_evaporation_deficit_forces_arid_seasonal(self) -> None:
        wet = _cell([15.0] * 12, [80.0] * 12)
        self.assertEqual(_cell_seasonality(wet)[3], "humid_stable")
        self.assertEqual(_cell_seasonality(wet)[1], 0.0)
        parched = dict(wet, vapor_evaporation_mm_y=6000.0)
        precipitation_range, aridity, monsoon_index, regime = _cell_seasonality(parched)
        self.assertEqual(precipitation_range, 0.0)
        self.assertEqual(monsoon_index, 0.0)
        # (6000/12 - 80) * 12 deficit over (960 + 6000) of throughput.
        self.assertAlmostEqual(aridity, (500.0 - 80.0) * 12.0 / 6960.0, places=9)
        self.assertGreaterEqual(aridity, 0.65)
        self.assertEqual(regime, "arid_seasonal")

    def test_evaporation_weight_floor_applies_to_very_cold_months(self) -> None:
        # The monthly evaporation weight is max(0.05, 1 + T/35), so the floor
        # only binds below -33.25 C. Six months at -40 C sit under it and six at
        # +20 C do not, which makes the weights 0.05 and 1.571429.
        temperature = [-40.0] * 6 + [20.0] * 6
        weights = [max(0.05, 1.0 + value / 35.0) for value in temperature]
        self.assertEqual(weights[:6], [0.05] * 6)
        self.assertNotEqual(weights[6], 0.05)
        evaporation = [1200.0 * weight / sum(weights) for weight in weights]
        precipitation = [50.0] * 12
        expected_aridity = sum(
            max(0.0, month_evaporation - month_precipitation)
            for month_evaporation, month_precipitation in zip(evaporation, precipitation)
        ) / (sum(precipitation) + 1200.0)

        cell = _cell(temperature, precipitation) | {"vapor_evaporation_mm_y": 1200.0}
        _, aridity, _, regime = _cell_seasonality(cell)
        self.assertAlmostEqual(aridity, expected_aridity, places=9)
        self.assertAlmostEqual(aridity, 0.479442, places=6)
        self.assertEqual(regime, "humid_stable")

    def test_aridity_cutoff_is_exactly_0_65(self) -> None:
        # 700 mm/y of rain against 3300 mm/y of evaporation: the deficit is
        # 2600 mm over a throughput of 4000 mm, i.e. exactly 0.65. The profile
        # is nearly flat (monsoon index 0.0057) so nothing but the aridity
        # branch can make it arid.
        precipitation = [58.0] * 11 + [62.0]
        self.assertEqual(sum(precipitation), 700.0)
        at_cutoff = _cell(
            [15.0] * 12, precipitation
        ) | {"vapor_evaporation_mm_y": 3300.0}
        below_cutoff = _cell(
            [15.0] * 12, precipitation
        ) | {"vapor_evaporation_mm_y": 3299.0}
        _, aridity_at, _, regime_at = _cell_seasonality(at_cutoff)
        _, aridity_below, _, regime_below = _cell_seasonality(below_cutoff)
        self.assertAlmostEqual(aridity_at, 0.65, places=12)
        self.assertGreaterEqual(aridity_at, 0.65)
        self.assertLess(aridity_below, 0.65)
        self.assertEqual(regime_at, "arid_seasonal")
        self.assertEqual(regime_below, "humid_stable")


class SeasonalClimateEnrichmentTests(TestCase):
    CLIMATE_KEYS = (
        "climate_seasonal_histories",
        "climate_classification",
    )

    def test_enrich_empty_world_is_a_noop(self) -> None:
        world: dict[str, Any] = {"cells": []}
        result = enrich_world_with_seasonal_climate_history(world)
        self.assertIs(result, world)
        self.assertEqual(sorted(result), ["cells"])
        for key in self.CLIMATE_KEYS:
            self.assertNotIn(key, result)
        self.assertNotIn("summary", result)

    def test_enrich_world_without_cells_key_is_a_noop(self) -> None:
        world: dict[str, Any] = {}
        result = enrich_world_with_seasonal_climate_history(world)
        self.assertIs(result, world)
        self.assertEqual(result, {})

    def test_enrich_mutates_the_world_and_its_cells_in_place(self) -> None:
        world: dict[str, Any] = {"cells": _synthetic_cells()}
        original_cell = world["cells"][0]
        result = enrich_world_with_seasonal_climate_history(world)
        self.assertIs(result, world)
        self.assertIs(result["cells"][0], original_cell)
        self.assertEqual(original_cell["climate_class"], "Af")

    def test_enrich_groups_cells_into_atmospheric_cell_histories(self) -> None:
        world = _enriched_world()
        histories = world["climate_seasonal_histories"]
        self.assertEqual(len(histories), 2)
        # Groups are emitted in sorted key order: "ferrel" before "hadley".
        self.assertEqual([history["atmospheric_cell"] for history in histories], ["ferrel", "hadley"])
        self.assertEqual([history["id"] for history in histories], [0, 1])
        self.assertEqual([history["cell_count"] for history in histories], [1, 2])
        for history in histories:
            with self.subTest(atmospheric_cell=history["atmospheric_cell"]):
                self.assertEqual(history["time_step_count"], 12)
                self.assertEqual(len(history["steps"]), 12)
                self.assertEqual([step["month"] for step in history["steps"]], list(range(1, 13)))
        self.assertEqual(world["summary"]["climate_seasonal_history_count"], 2)
        self.assertEqual(world["summary"]["climate_seasonal_step_count"], 24)

    def test_enrich_annotates_every_cell_with_climate_fields(self) -> None:
        world = _enriched_world()
        expected = {
            0: ("Af", "humid_stable", 0.0, 0.0, 0.0),
            1: ("BWh", "arid_seasonal", 0.0, 0.935484, 0.0),
            2: ("Cwa", "monsoonal", 0.247899, 0.126728, 295.0),
        }
        for cell in world["cells"]:
            with self.subTest(cell=cell["id"]):
                climate_class, regime, monsoon_index, aridity, precipitation_range = expected[cell["id"]]
                self.assertEqual(cell["climate_class"], climate_class)
                self.assertEqual(cell["seasonal_humidity_regime"], regime)
                self.assertEqual(cell["cell_monsoon_index"], monsoon_index)
                self.assertEqual(cell["seasonal_aridity_index"], aridity)
                self.assertEqual(cell["seasonal_precipitation_range_mm"], precipitation_range)

        # Cell 1: 1800 mm/y of evaporation against 5 mm/month of rain leaves a
        # 1740 mm deficit over 1860 mm of throughput.
        self.assertAlmostEqual(world["cells"][1]["seasonal_aridity_index"], 1740.0 / 1860.0, places=6)
        # Cell 2: the deficit is temperature-weighted, so it is the sum of the
        # months where the weighted evaporation beats the rain, over 1790 mm.
        cell_two_deficit = sum(
            max(0.0, evaporation - precipitation)
            for evaporation, precipitation in zip(FERREL_EVAPORATION_MM, CWA_PRECIPITATION_MM)
        )
        self.assertAlmostEqual(
            world["cells"][2]["seasonal_aridity_index"],
            cell_two_deficit / (sum(CWA_PRECIPITATION_MM) + 600.0),
            places=6,
        )

    def test_summary_counts_match_the_annotated_cells(self) -> None:
        world = _enriched_world()
        cells = world["cells"]
        summary = world["summary"]

        observed_classes: dict[str, int] = {}
        observed_regimes: dict[str, int] = {}
        for cell in cells:
            observed_classes[cell["climate_class"]] = observed_classes.get(cell["climate_class"], 0) + 1
            regime = cell["seasonal_humidity_regime"]
            observed_regimes[regime] = observed_regimes.get(regime, 0) + 1

        self.assertEqual(summary["climate_class_counts"], observed_classes)
        self.assertEqual(summary["climate_class_counts"], {"Af": 1, "BWh": 1, "Cwa": 1})
        self.assertEqual(summary["seasonal_humidity_regime_counts"], observed_regimes)
        self.assertEqual(
            summary["seasonal_humidity_regime_counts"],
            {"arid_seasonal": 1, "humid_stable": 1, "monsoonal": 1},
        )
        self.assertEqual(summary["climate_class_count"], 3)
        self.assertEqual(summary["climate_main_class_counts"], {"A": 1, "B": 1, "C": 1})
        # Only cell 1 clears the 0.45 aridity bar.
        self.assertEqual(summary["seasonal_aridity_cell_fraction"], round(1 / 3, 6))
        self.assertEqual(summary["mean_cell_monsoon_index"], round(0.247899 / 3, 6))
        self.assertEqual(
            summary["mean_cell_seasonal_aridity_index"],
            round((0.0 + 0.935484 + 0.126728) / 3, 6),
        )
        self.assertEqual(summary["max_climate_monsoon_index"], 0.247899)

    def test_humidity_budget_residual_is_exactly_zero_every_step(self) -> None:
        world = _enriched_world()
        steps = [step for history in world["climate_seasonal_histories"] for step in history["steps"]]
        self.assertEqual(len(steps), 24)
        for history in world["climate_seasonal_histories"]:
            for step in history["steps"]:
                with self.subTest(atmospheric_cell=history["atmospheric_cell"], month=step["month"]):
                    self.assertEqual(step["humidity_budget_residual_mm"], 0.0)
                    recomputed = (
                        step["start_humidity_storage_mm"]
                        + step["evaporation_mm"]
                        + step["moisture_convergence_mm"]
                        + step["vapor_deficit_mm"]
                        - step["precipitation_mm"]
                        - step["humidity_export_mm"]
                        - step["end_humidity_storage_mm"]
                    )
                    # Seven fields, each rounded to 6 decimals, so the closed
                    # ledger can only be reconstructed to within 7 * 5e-7.
                    self.assertAlmostEqual(recomputed, 0.0, delta=4e-6)
        self.assertEqual(world["summary"]["climate_seasonal_mean_abs_residual_mm"], 0.0)
        # The identity is not vacuous: both the deficit and the storage branches
        # of the ledger fire somewhere in these 24 steps, and each branch is
        # exclusive of the other.
        self.assertEqual(sum(1 for step in steps if step["vapor_deficit_mm"] > 0.0), 5)
        self.assertEqual(sum(1 for step in steps if step["end_humidity_storage_mm"] > 0.0), 19)
        for step in steps:
            with self.subTest(month=step["month"]):
                self.assertEqual(
                    step["vapor_deficit_mm"] > 0.0 and step["humidity_export_mm"] > 0.0,
                    False,
                )

    def test_storage_carries_from_one_month_into_the_next(self) -> None:
        world = _enriched_world()
        for history in world["climate_seasonal_histories"]:
            steps = history["steps"]
            self.assertEqual(steps[0]["start_humidity_storage_mm"], 0.0)
            for previous, current in zip(steps, steps[1:]):
                with self.subTest(atmospheric_cell=history["atmospheric_cell"], month=current["month"]):
                    self.assertEqual(
                        current["start_humidity_storage_mm"],
                        previous["end_humidity_storage_mm"],
                    )

    def test_history_step_averages_over_the_group_members(self) -> None:
        world = _enriched_world()
        histories = {history["atmospheric_cell"]: history for history in world["climate_seasonal_histories"]}
        january = histories["hadley"]["steps"][0]
        # Two members with uniform monthly temperatures, so the evaporation
        # weights are flat: (900 + 1800)/12/2 = 112.5 mm.
        self.assertEqual(january["mean_temperature_c"], 28.0)
        self.assertEqual(january["precipitation_mm"], 52.5)
        self.assertEqual(january["evaporation_mm"], 112.5)
        self.assertEqual(january["moisture_convergence_mm"], 12.5)
        self.assertEqual(january["mean_wind_east"], 2.5)
        self.assertEqual(january["mean_wind_north"], -0.25)
        self.assertEqual(january["mean_wind_speed_index"], 2.611915)
        self.assertEqual(january["mean_vertical_motion_index"], -0.1)
        self.assertEqual(january["mean_divergence_index"], 0.15)
        # 112.5 + 12.5 - 52.5 = 72.5 mm surplus, exported at
        # clamp(0.42 + 0.15*0.22 + 2.611915*0.08) = 0.6619532.
        self.assertEqual(january["vapor_deficit_mm"], 0.0)
        self.assertEqual(january["humidity_export_mm"], 47.991608)
        self.assertEqual(january["end_humidity_storage_mm"], 24.508392)
        self.assertEqual(january["drying_risk"], 0.0)
        # The wind speed index is the mean of the per-cell speeds, not the speed
        # of the mean wind: sqrt(2.5^2 + 0.25^2) would be 2.512469.
        self.assertEqual(
            january["mean_wind_speed_index"],
            round(((3.0**2 + 1.0**2) ** 0.5 + (2.0**2 + 0.5**2) ** 0.5) / 2.0, 6),
        )

    def test_evaporation_follows_the_monthly_temperature_weights(self) -> None:
        # The ferrel group is the lone Cwa cell, whose monthly temperatures span
        # 10-30 C. Splitting its 600 mm/y evenly would give 50 mm every month;
        # the max(0.05, 1 + T/35) weighting tilts it from 40.97 in January to
        # 59.18 in July while still summing to 600.
        world = _enriched_world()
        histories = {history["atmospheric_cell"]: history for history in world["climate_seasonal_histories"]}
        steps = histories["ferrel"]["steps"]
        self.assertAlmostEqual(sum(FERREL_EVAPORATION_MM), 600.0, places=9)
        for step, expected in zip(steps, FERREL_EVAPORATION_MM):
            with self.subTest(month=step["month"]):
                self.assertEqual(step["evaporation_mm"], round(expected, 6))
        self.assertEqual(steps[0]["evaporation_mm"], 40.971168)
        self.assertEqual(steps[6]["evaporation_mm"], 59.180577)
        self.assertNotEqual(steps[0]["evaporation_mm"], steps[6]["evaporation_mm"])

    def test_export_fraction_is_clamped_at_its_upper_bound(self) -> None:
        # The ferrel cell has a divergence index of 0.3 and a wind speed of
        # sqrt(6^2 + 2^2) = 6.324555, so the raw export fraction would be
        # 0.42 + 0.3*0.22 + 6.324555*0.08 = 0.991964 -- above the 0.82 cap.
        world = _enriched_world()
        histories = {history["atmospheric_cell"]: history for history in world["climate_seasonal_histories"]}
        january = histories["ferrel"]["steps"][0]
        raw_fraction = 0.42 + 0.3 * 0.22 + (6.0**2 + 2.0**2) ** 0.5 * 0.08
        self.assertGreater(raw_fraction, 0.82)
        # January: no carry-in, 40.971168 mm of evaporation and 10 mm of
        # convergence against 5 mm of rain -> a 45.971168 mm surplus.
        surplus = FERREL_EVAPORATION_MM[0] + 10.0 - CWA_PRECIPITATION_MM[0]
        self.assertEqual(january["humidity_export_mm"], round(surplus * 0.82, 6))
        self.assertEqual(january["end_humidity_storage_mm"], round(surplus * 0.18, 6))
        self.assertEqual(january["humidity_export_mm"], 37.696358)
        self.assertEqual(january["end_humidity_storage_mm"], 8.27481)

    def test_negative_inputs_are_floored_at_zero(self) -> None:
        # A standalone one-cell world with a negative moisture convergence, a
        # negative divergence index and one negative rainfall month. All three
        # are floored at zero rather than allowed to drain the ledger.
        cell = {
            "id": 0,
            "atmospheric_cell": "polar",
            "lat_deg": 70.0,
            "temperature_monthly_c": [10.0] * 12,
            "precipitation_monthly_mm": [10.0, -20.0] + [10.0] * 10,
            "vapor_evaporation_mm_y": 1200.0,
            "moisture_convergence_mm_y": -600.0,
            "wind_east": 0.0,
            "wind_north": 0.0,
            "vertical_velocity_index": 0.0,
            "wind_divergence_index": -0.5,
        }
        world = enrich_world_with_seasonal_climate_history({"cells": [cell]})
        history = world["climate_seasonal_histories"][0]
        january, february = history["steps"][0], history["steps"][1]

        # -600 mm/y of convergence contributes nothing, so the whole year runs
        # on the flat 100 mm/month of evaporation.
        self.assertEqual(january["moisture_convergence_mm"], 0.0)
        self.assertEqual(history["annual_moisture_convergence_mm"], 0.0)
        self.assertEqual(january["evaporation_mm"], 100.0)
        # The negative rainfall month reads as a dry month, not as a -20 mm one.
        self.assertEqual(february["precipitation_mm"], 0.0)
        self.assertEqual(history["annual_precipitation_mm"], 110.0)
        # Zero wind and a negative divergence leave the bare 0.42 export base:
        # 90 mm of surplus in January, of which 42% leaves.
        self.assertEqual(january["mean_divergence_index"], -0.5)
        self.assertEqual(january["humidity_export_mm"], round(90.0 * 0.42, 6))
        self.assertEqual(january["end_humidity_storage_mm"], round(90.0 * 0.58, 6))
        self.assertEqual(january["humidity_export_mm"], 37.8)

    def test_drying_risk_tracks_the_vapor_deficit(self) -> None:
        world = _enriched_world()
        histories = {history["atmospheric_cell"]: history for history in world["climate_seasonal_histories"]}
        ferrel = histories["ferrel"]
        july = ferrel["steps"][6]
        # July: 300 mm of rain against 59.180577 mm of evaporation, no carry-in
        # (June already ran dry) and 10 mm of convergence.
        self.assertEqual(july["start_humidity_storage_mm"], 0.0)
        deficit = 300.0 - (FERREL_EVAPORATION_MM[6] + 10.0)
        self.assertEqual(july["vapor_deficit_mm"], round(deficit, 6))
        self.assertEqual(
            july["drying_risk"],
            round(deficit / (300.0 + FERREL_EVAPORATION_MM[6]), 6),
        )
        self.assertEqual(july["drying_risk"], 0.642628)
        self.assertEqual(ferrel["max_drying_risk"], 0.642628)
        # The dry months are exactly May-September.
        self.assertEqual(
            [step["month"] for step in ferrel["steps"] if step["vapor_deficit_mm"] > 0.0],
            [5, 6, 7, 8, 9],
        )

    def test_history_annual_aggregates(self) -> None:
        world = _enriched_world()
        histories = {history["atmospheric_cell"]: history for history in world["climate_seasonal_histories"]}
        ferrel = histories["ferrel"]
        self.assertEqual(ferrel["annual_precipitation_mm"], sum(CWA_PRECIPITATION_MM))
        self.assertEqual(ferrel["annual_evaporation_mm"], 600.0)
        self.assertEqual(ferrel["annual_moisture_convergence_mm"], 120.0)
        self.assertEqual(ferrel["wettest_month"], 7)
        self.assertEqual(ferrel["driest_month"], 1)
        self.assertEqual(ferrel["seasonal_precipitation_range_mm"], 295.0)
        self.assertEqual(ferrel["monsoon_index"], 0.247899)
        self.assertEqual(ferrel["mean_temperature_c"], 19.916667)
        # Replaying the ledger by hand over the twelve months.
        self.assertEqual(ferrel["annual_vapor_deficit_mm"], 763.198602)
        self.assertEqual(ferrel["annual_humidity_export_mm"], 282.860402)
        self.assertEqual(ferrel["max_humidity_storage_mm"], 10.552807)

        hadley = histories["hadley"]
        self.assertEqual(hadley["annual_precipitation_mm"], 630.0)
        self.assertEqual(hadley["annual_evaporation_mm"], 1350.0)
        self.assertEqual(hadley["annual_moisture_convergence_mm"], 150.0)
        self.assertEqual(hadley["annual_vapor_deficit_mm"], 0.0)
        self.assertEqual(hadley["monsoon_index"], 0.0)
        self.assertEqual(hadley["max_drying_risk"], 0.0)
        self.assertEqual(hadley["max_humidity_storage_mm"], 37.024274)

        summary = world["summary"]
        self.assertEqual(summary["climate_seasonal_total_precipitation_mm"], 1820.0)
        self.assertEqual(summary["climate_seasonal_total_evaporation_mm"], 1950.0)
        self.assertEqual(summary["climate_seasonal_total_moisture_convergence_mm"], 270.0)
        self.assertEqual(summary["climate_seasonal_total_vapor_deficit_mm"], 763.198602)
        self.assertEqual(summary["climate_seasonal_total_humidity_export_mm"], 1115.836128)
        self.assertEqual(summary["max_climate_humidity_storage_mm"], 37.024274)
        self.assertEqual(
            summary["climate_seasonal_total_vapor_deficit_mm"],
            ferrel["annual_vapor_deficit_mm"] + hadley["annual_vapor_deficit_mm"],
        )

    def test_classification_metadata_and_legend(self) -> None:
        world = _enriched_world()
        classification = world["climate_classification"]
        self.assertEqual(classification["classification_type"], "koppen_geiger_beck_2018_v0")
        self.assertEqual(classification["classification_type"], CLIMATE_CLASSIFICATION_TYPE)
        self.assertEqual(
            classification["classification_limitation"],
            "single_generated_monthly_climatology_without_observational_ensemble",
        )
        self.assertEqual(classification["classification_limitation"], CLIMATE_CLASSIFICATION_LIMITATION)
        self.assertEqual(classification["monthly_temperature_field"], "temperature_monthly_c")
        self.assertEqual(classification["monthly_precipitation_field"], "precipitation_monthly_mm")
        self.assertEqual(classification["temperate_cold_threshold_c"], 0.0)
        self.assertIs(classification["arid_class_precedence"], True)
        self.assertIs(classification["includes_water_cells"], True)
        self.assertIs(classification["confidence_resolved"], False)

        self.assertEqual(classification["classified_cell_count"], len(world["cells"]))
        self.assertEqual(classification["classified_cell_count"], 3)
        self.assertEqual(classification["generated_class_count"], 3)
        self.assertEqual(classification["available_class_count"], 30)

        legend = classification["legend"]
        self.assertEqual(len(legend), 30)
        self.assertEqual([entry["code"] for entry in legend], sorted(EXPECTED_CLIMATE_CODES))
        self.assertEqual(
            {entry["code"]: entry["name"] for entry in legend},
            dict(CLIMATE_CLASS_NAMES),
        )
        # Every class a cell can be assigned is in the legend.
        for cell in world["cells"]:
            with self.subTest(cell=cell["id"]):
                self.assertIn(cell["climate_class"], {entry["code"] for entry in legend})
