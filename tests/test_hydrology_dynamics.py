from __future__ import annotations

from typing import Any
from unittest import TestCase

from magic_geo.hydrology_dynamics import (
    _annual_evaporation_loss_km3,
    _normalized_overflow_pressure,
    _overflow_stage,
    enrich_world_with_lake_overflow_history,
)


class HydrologyDynamicsTests(TestCase):
    def test_native_overflow_index_uses_quarter_scale_pressure(self) -> None:
        self.assertEqual(_normalized_overflow_pressure(-1.0), 0.0)
        self.assertEqual(_normalized_overflow_pressure(0.0), 0.0)
        self.assertEqual(_normalized_overflow_pressure(3.0), 0.75)
        self.assertEqual(_normalized_overflow_pressure(4.0), 1.0)
        self.assertEqual(_normalized_overflow_pressure(50.0), 1.0)


def _planet_parameters() -> dict[str, Any]:
    return {"radius_km": 6371.0}


def _cells() -> list[dict[str, Any]]:
    """Four cells one degree apart along the equator, the first three dropping 120 m to 10 m.

    Cell 3 sits off every overflow path, so it must keep the reset channel
    annotations no matter what the routed cells receive.
    """

    return [
        {"id": 0, "lat_deg": 0.0, "lon_deg": 0.0, "elevation_m": 120.0},
        {"id": 1, "lat_deg": 0.0, "lon_deg": 1.0, "elevation_m": 60.0},
        {"id": 2, "lat_deg": 0.0, "lon_deg": 2.0, "elevation_m": 10.0},
        {"id": 3, "lat_deg": 0.0, "lon_deg": 3.0, "elevation_m": 5.0},
    ]


def _overflowing_basin() -> dict[str, Any]:
    """Basin 0: 90 % full, spills every year, and drives an avulsing channel."""

    return {
        "id": 0,
        "lake_cell_count": 3,
        "depression_policy": "overflow",
        "storage_capacity_km3": 10.0,
        "annual_runoff_km3": 6.0,
        "fill_fraction": 0.9,
        "overflow_stage_count": 3,
        "overflows": True,
        "avulsion_risk": 0.9,
        "lake_area_km2": 100.0,
        "mean_water_depth_m": 50.0,
        "overflow_index": 8.0,
        "overflow_path_cell_ids": [0, 1, 2],
        "spill_elevation_m": 130.0,
        "max_depression_depth_m": 80.0,
    }


def _closed_basin() -> dict[str, Any]:
    """Basin 1: already full, endorheic, so every inflow year leaves via the sink."""

    return {
        "id": 1,
        "lake_cell_count": 4,
        "depression_policy": "sink",
        "storage_capacity_km3": 10.0,
        "annual_runoff_km3": 2.0,
        "fill_fraction": 1.0,
        "overflow_stage_count": 2,
        "overflows": False,
        "avulsion_risk": 0.2,
        "overflow_path_cell_ids": [],
    }


def _dry_basin() -> dict[str, Any]:
    """Basin 2: no lake cells, so it must never be simulated."""

    return {
        "id": 2,
        "lake_cell_count": 0,
        "depression_policy": "overflow",
        "storage_capacity_km3": 5.0,
        "annual_runoff_km3": 4.0,
        "fill_fraction": 0.5,
        "overflows": True,
        "overflow_stage_count": 2,
        "overflow_path_cell_ids": [0, 1],
        "spill_elevation_m": 200.0,
        "max_depression_depth_m": 40.0,
    }


def _synthetic_world() -> dict[str, Any]:
    return {
        "planet_parameters": _planet_parameters(),
        "cells": _cells(),
        "lake_basins": [_overflowing_basin(), _closed_basin(), _dry_basin()],
    }


def _simulated_world(years: int = 3) -> dict[str, Any]:
    return enrich_world_with_lake_overflow_history(_synthetic_world(), simulation_years=years)


def _history(world: dict[str, Any], lake_basin_id: int) -> dict[str, Any]:
    for history in world["lake_overflow_histories"]:
        if history["lake_basin_id"] == lake_basin_id:
            return history
    raise AssertionError(f"no lake overflow history for basin {lake_basin_id}")


def _cell(world: dict[str, Any], cell_id: int) -> dict[str, Any]:
    for cell in world["cells"]:
        if cell["id"] == cell_id:
            return cell
    raise AssertionError(f"no cell {cell_id}")


class LakeOverflowSimulationTests(TestCase):
    def test_first_step_balances_inflow_evaporation_and_spill(self) -> None:
        history = _history(_simulated_world(), 0)
        step = history["steps"][0]

        self.assertEqual(step["year"], 1)
        self.assertEqual(step["start_volume_km3"], 9.0)
        self.assertEqual(step["inflow_km3"], 6.0)
        self.assertEqual(step["evaporation_loss_km3"], 0.037)
        self.assertEqual(step["spill_volume_km3"], 4.963)
        self.assertEqual(step["sink_loss_km3"], 0.0)
        self.assertEqual(step["end_volume_km3"], 10.0)
        self.assertEqual(step["fill_fraction"], 1.0)
        self.assertEqual(step["overflow_stage"], 3)
        self.assertEqual(step["avulsion_risk"], 0.845557)
        self.assertIs(step["avulsion_triggered"], True)

        # Years 2 and 3 start full, so each spills a whole year of runoff minus
        # the evaporated 0.037 km3.
        self.assertEqual(
            [round(other["spill_volume_km3"], 6) for other in history["steps"][1:]],
            [5.963, 5.963],
        )

        self.assertEqual(history["depression_policy"], "overflow")
        self.assertIs(history["overflows"], True)
        self.assertEqual(history["first_overflow_year"], 1)
        self.assertEqual(history["total_spill_km3"], 16.889)
        self.assertEqual(history["total_sink_loss_km3"], 0.0)
        self.assertEqual(history["total_inflow_km3"], 18.0)
        self.assertEqual(history["time_step_count"], 3)
        self.assertEqual(history["simulation_year_count"], 3)
        self.assertEqual(history["max_fill_fraction"], 1.0)
        # Years 2 and 3 spill 5.963 of 6.0 km3 of runoff: 0.9 * (0.65 + 0.35 * 0.993833).
        self.assertEqual(history["max_avulsion_risk"], 0.898057)
        self.assertEqual(history["overflow_path_cell_ids"], [0, 1, 2])

    def test_every_simulated_year_conserves_its_water_budget(self) -> None:
        world = _simulated_world()

        # The invariants below are only meaningful over a world that actually
        # simulated two basins for three years and moved water both ways.
        self.assertEqual(
            [
                (history["lake_basin_id"], len(history["steps"]))
                for history in world["lake_overflow_histories"]
            ],
            [(0, 3), (1, 3)],
        )
        self.assertGreater(world["summary"]["lake_overflow_total_spill_km3"], 0.0)
        self.assertGreater(world["summary"]["lake_overflow_total_sink_loss_km3"], 0.0)

        for history in world["lake_overflow_histories"]:
            previous_end_km3: float | None = None
            for step in history["steps"]:
                with self.subTest(basin=history["lake_basin_id"], year=step["year"]):
                    # Each field is rounded to 6 decimals, so the identity can only
                    # drift by a few units in the sixth decimal place.
                    self.assertAlmostEqual(
                        step["start_volume_km3"]
                        + step["inflow_km3"]
                        - step["evaporation_loss_km3"]
                        - step["spill_volume_km3"]
                        - step["sink_loss_km3"],
                        step["end_volume_km3"],
                        delta=5e-06,
                    )
                    self.assertGreaterEqual(step["end_volume_km3"], 0.0)
                    self.assertLessEqual(
                        step["end_volume_km3"], history["storage_capacity_km3"]
                    )
                    if previous_end_km3 is not None:
                        self.assertEqual(step["start_volume_km3"], previous_end_km3)
                    previous_end_km3 = step["end_volume_km3"]

            with self.subTest(basin=history["lake_basin_id"], total="spill"):
                self.assertEqual(
                    history["total_spill_km3"],
                    round(sum(step["spill_volume_km3"] for step in history["steps"]), 6),
                )
            with self.subTest(basin=history["lake_basin_id"], total="sink"):
                self.assertEqual(
                    history["total_sink_loss_km3"],
                    round(sum(step["sink_loss_km3"] for step in history["steps"]), 6),
                )

    def test_closed_basin_routes_excess_to_the_sink_and_never_spills(self) -> None:
        history = _history(_simulated_world(), 1)

        self.assertEqual(history["depression_policy"], "sink")
        self.assertIs(history["overflows"], False)
        self.assertEqual(history["total_sink_loss_km3"], 6.0)
        self.assertEqual(history["total_spill_km3"], 0.0)
        self.assertEqual(history["first_overflow_year"], -1)
        self.assertIs(history["avulsion_triggered"], False)
        self.assertEqual(history["max_fill_fraction"], 1.0)
        # A dry spillway still reports the static risk damped to 65 %: 0.2 * 0.65.
        self.assertEqual(history["max_avulsion_risk"], 0.13)

        for step in history["steps"]:
            with self.subTest(year=step["year"]):
                self.assertEqual(step["avulsion_risk"], 0.13)
                self.assertEqual(step["sink_loss_km3"], 2.0)
                self.assertEqual(step["spill_volume_km3"], 0.0)
                self.assertEqual(step["overflow_stage"], 0)
                self.assertEqual(step["start_volume_km3"], 10.0)
                self.assertEqual(step["end_volume_km3"], 10.0)
                self.assertIs(step["avulsion_triggered"], False)

    def test_zero_capacity_basin_loses_every_inflow_year_to_the_sink(self) -> None:
        world = {
            "planet_parameters": _planet_parameters(),
            "cells": _cells(),
            "lake_basins": [
                {
                    "id": 7,
                    "lake_cell_count": 2,
                    "storage_capacity_km3": 0.0,
                    "annual_runoff_km3": 4.0,
                    "fill_fraction": 0.8,
                    "overflows": True,
                    "overflow_stage_count": 3,
                    "overflow_path_cell_ids": [],
                }
            ],
        }

        history = _history(
            enrich_world_with_lake_overflow_history(world, simulation_years=3), 7
        )

        self.assertEqual(history["storage_capacity_km3"], 0.0)
        self.assertEqual(history["depression_policy"], "unknown")
        self.assertEqual(history["total_inflow_km3"], 12.0)
        self.assertEqual(history["total_sink_loss_km3"], 12.0)
        self.assertEqual(history["total_spill_km3"], 0.0)
        self.assertEqual(history["max_fill_fraction"], 0.0)
        for step in history["steps"]:
            with self.subTest(year=step["year"]):
                self.assertEqual(step["start_volume_km3"], 0.0)
                self.assertEqual(step["inflow_km3"], 4.0)
                self.assertEqual(step["sink_loss_km3"], 4.0)
                self.assertEqual(step["spill_volume_km3"], 0.0)
                self.assertEqual(step["end_volume_km3"], 0.0)
                self.assertEqual(step["fill_fraction"], 0.0)

    def test_starting_volume_is_capped_at_the_storage_capacity(self) -> None:
        # fill_fraction 1.5 is nonsense; the lake may still only hold 10 km3.
        world = {
            "planet_parameters": _planet_parameters(),
            "lake_basins": [
                {
                    "id": 4,
                    "lake_cell_count": 1,
                    "depression_policy": "overflow",
                    "storage_capacity_km3": 10.0,
                    "annual_runoff_km3": 0.0,
                    "fill_fraction": 1.5,
                    "overflows": True,
                    "overflow_stage_count": 2,
                    "overflow_path_cell_ids": [],
                }
            ],
        }

        history = _history(
            enrich_world_with_lake_overflow_history(world, simulation_years=3), 4
        )

        # An uncapped 15 km3 start would immediately spill the 5 km3 of overfill.
        self.assertEqual(history["total_spill_km3"], 0.0)
        self.assertEqual(history["total_sink_loss_km3"], 0.0)
        self.assertEqual(history["max_fill_fraction"], 1.0)
        self.assertEqual(history["first_overflow_year"], -1)
        for step in history["steps"]:
            with self.subTest(year=step["year"]):
                self.assertEqual(step["start_volume_km3"], 10.0)
                self.assertEqual(step["end_volume_km3"], 10.0)
                self.assertEqual(step["fill_fraction"], 1.0)

    def test_evaporation_never_removes_more_than_the_water_present(self) -> None:
        # The lake would evaporate 0.037 km3 a year but only ever holds 0.01 km3.
        world = {
            "planet_parameters": _planet_parameters(),
            "lake_basins": [
                {
                    "id": 5,
                    "lake_cell_count": 1,
                    "depression_policy": "overflow",
                    "storage_capacity_km3": 10.0,
                    "annual_runoff_km3": 0.01,
                    "fill_fraction": 0.0,
                    "overflows": True,
                    "overflow_stage_count": 2,
                    "lake_area_km2": 100.0,
                    "mean_water_depth_m": 50.0,
                    "overflow_path_cell_ids": [],
                }
            ],
        }

        history = _history(
            enrich_world_with_lake_overflow_history(world, simulation_years=3), 5
        )

        self.assertEqual(history["total_inflow_km3"], 0.03)
        self.assertEqual(history["total_spill_km3"], 0.0)
        self.assertEqual(history["max_fill_fraction"], 0.0)
        for step in history["steps"]:
            with self.subTest(year=step["year"]):
                self.assertEqual(step["inflow_km3"], 0.01)
                self.assertEqual(step["evaporation_loss_km3"], 0.01)
                self.assertEqual(step["start_volume_km3"], 0.0)
                self.assertEqual(step["end_volume_km3"], 0.0)

    def test_basin_without_lake_cells_is_excluded_from_the_simulation(self) -> None:
        world = _simulated_world()

        simulated_ids = [history["lake_basin_id"] for history in world["lake_overflow_histories"]]
        self.assertEqual(simulated_ids, [0, 1])
        self.assertEqual(world["summary"]["simulated_lake_basin_count"], 2)
        self.assertEqual(world["summary"]["lake_overflow_history_count"], 2)
        self.assertEqual(world["summary"]["lake_overflow_history_step_count"], 6)
        self.assertEqual(world["summary"]["lake_overflow_simulation_years"], 3)
        self.assertEqual(world["summary"]["lake_overflow_active_history_count"], 1)
        self.assertEqual(world["summary"]["lake_overflow_avulsion_trigger_count"], 1)
        self.assertEqual(world["summary"]["lake_overflow_total_spill_km3"], 16.889)
        self.assertEqual(world["summary"]["lake_overflow_total_sink_loss_km3"], 6.0)
        self.assertEqual(world["summary"]["max_lake_overflow_fill_fraction"], 1.0)
        # The dry basin carries a two-cell overflow path, so it would have produced a
        # channel history had it been simulated.
        channel_basin_ids = [
            channel["lake_basin_id"] for channel in world["lake_overflow_channel_histories"]
        ]
        self.assertEqual(channel_basin_ids, [0])

    def test_overflow_channel_annotates_path_cells_and_counts_the_avulsion(self) -> None:
        world = _simulated_world()

        channels = world["lake_overflow_channel_histories"]
        self.assertEqual(len(channels), 1)
        channel = channels[0]
        self.assertEqual(channel["lake_basin_id"], 0)
        self.assertEqual(channel["overflow_path_cell_ids"], [0, 1, 2])
        self.assertEqual(channel["channel_segment_count"], 2)
        # Two one-degree hops along the equator: 2 * 6371 km * pi / 180.
        self.assertAlmostEqual(channel["channel_length_km"], 222.389853, places=6)
        # The 130 m spill lip stands 120 m above the 10 m outlet cell.
        self.assertEqual(channel["path_drop_m"], 120.0)
        self.assertEqual(channel["bed_slope"], 0.00053959)
        self.assertEqual(channel["time_step_count"], 3)
        self.assertEqual(channel["total_spill_km3"], 16.889)
        # The channel starts 0.8 m incised (1 % of the 80 m depression) and deepens
        # by 0.695214 m over the three spill years.
        self.assertEqual(channel["steps"][0]["start_incision_depth_m"], 0.8)
        self.assertAlmostEqual(channel["total_incision_m"], 0.695214, places=6)
        self.assertAlmostEqual(channel["final_incision_depth_m"], 1.495214, places=6)
        self.assertAlmostEqual(channel["max_avulsion_risk"], 0.664968, places=6)
        self.assertIs(channel["avulsion_triggered"], True)
        self.assertEqual(channel["first_avulsion_year"], 1)
        self.assertEqual(
            [step["dominant_process"] for step in channel["steps"]],
            ["avulsion", "avulsion", "avulsion"],
        )

        summary = world["summary"]
        self.assertEqual(summary["lake_overflow_channel_history_count"], 1)
        self.assertEqual(summary["lake_overflow_channel_cell_count"], 3)
        self.assertEqual(summary["lake_overflow_channel_step_count"], 3)
        self.assertEqual(summary["active_lake_overflow_channel_count"], 1)
        self.assertEqual(summary["lake_overflow_channel_avulsion_count"], 1)
        self.assertAlmostEqual(
            summary["max_lake_overflow_channel_incision_m"], 1.495214, places=6
        )

        for cell_id in (0, 1, 2):
            cell = _cell(world, cell_id)
            with self.subTest(cell_id=cell_id, routed=True):
                self.assertIs(cell["overflow_channel_active"], True)
                self.assertAlmostEqual(
                    cell["overflow_channel_incision_m"], 1.495214, places=6
                )
                self.assertAlmostEqual(
                    cell["overflow_channel_avulsion_risk"], 0.664968, places=6
                )
                self.assertAlmostEqual(
                    cell["overflow_channel_sediment_evacuated_km3"], 0.000445, places=6
                )

        # Cell 3 is not on the path and must keep the reset annotations.
        off_path = _cell(world, 3)
        self.assertIs(off_path["overflow_channel_active"], False)
        self.assertEqual(off_path["overflow_channel_incision_m"], 0.0)
        self.assertEqual(off_path["overflow_channel_avulsion_risk"], 0.0)
        self.assertEqual(off_path["overflow_channel_sediment_evacuated_km3"], 0.0)

    def test_path_drop_falls_back_to_a_fraction_of_the_depression_depth(self) -> None:
        basin = _overflowing_basin()
        # Head and tail sit at the same hydrologic surface (40 m) and the spill lip is
        # below the tail, so neither head-to-tail relief nor spill relief is positive.
        basin["spill_elevation_m"] = 30.0
        world = {
            "planet_parameters": _planet_parameters(),
            "cells": [
                # ``filled_elevation_m`` outranks the 60 m bare-earth elevation.
                {
                    "id": 0,
                    "lat_deg": 0.0,
                    "lon_deg": 0.0,
                    "elevation_m": 60.0,
                    "filled_elevation_m": 40.0,
                },
                {"id": 1, "lat_deg": 0.0, "lon_deg": 1.0, "elevation_m": 25.0},
                # ``hydrologic_surface_elevation_m`` outranks both other keys.
                {
                    "id": 2,
                    "lat_deg": 0.0,
                    "lon_deg": 2.0,
                    "elevation_m": 5.0,
                    "filled_elevation_m": 8.0,
                    "hydrologic_surface_elevation_m": 40.0,
                },
            ],
            "lake_basins": [basin],
        }

        channel = enrich_world_with_lake_overflow_history(world, simulation_years=3)[
            "lake_overflow_channel_histories"
        ][0]

        self.assertEqual(channel["path_drop_m"], 80.0 * 0.15)
        self.assertEqual(channel["path_drop_m"], 12.0)
        self.assertAlmostEqual(channel["channel_length_km"], 222.389853, places=6)
        self.assertEqual(channel["bed_slope"], 5.396e-05)

    def test_channel_length_falls_back_to_the_reported_path_length(self) -> None:
        world = {
            "planet_parameters": _planet_parameters(),
            "cells": _cells(),
            "lake_basins": [
                {
                    "id": 20,
                    "lake_cell_count": 1,
                    "depression_policy": "overflow",
                    "storage_capacity_km3": 5.0,
                    "annual_runoff_km3": 5.0,
                    "fill_fraction": 1.0,
                    "overflows": True,
                    "overflow_stage_count": 2,
                    # Neither cell exists in the mesh, so no great-circle hop is measurable.
                    "overflow_path_cell_ids": [90, 91],
                    "overflow_path_length_km": 50.0,
                    "spill_elevation_m": 50.0,
                    "max_depression_depth_m": 40.0,
                }
            ],
        }

        result = enrich_world_with_lake_overflow_history(world, simulation_years=3)
        channel = result["lake_overflow_channel_histories"][0]

        self.assertEqual(channel["channel_segment_count"], 1)
        self.assertEqual(channel["channel_length_km"], 50.0)
        # The missing tail cell counts as 0 m, so the whole 50 m spill lip is the drop
        # and the 15 % of 40 m depression fallback stays unused.
        self.assertEqual(channel["path_drop_m"], 50.0)
        self.assertEqual(channel["bed_slope"], 0.001)
        self.assertEqual(channel["total_spill_km3"], 15.0)
        # The path cells are unknown, so no mesh cell may be annotated.
        self.assertEqual(result["summary"]["lake_overflow_channel_cell_count"], 0)
        for cell in result["cells"]:
            with self.subTest(cell_id=cell["id"]):
                self.assertIs(cell["overflow_channel_active"], False)
                self.assertEqual(cell["overflow_channel_incision_m"], 0.0)

    def test_overflow_path_shorter_than_two_cells_yields_no_channel(self) -> None:
        world = {
            "planet_parameters": _planet_parameters(),
            "cells": _cells(),
            "lake_basins": [
                {
                    "id": 10,
                    "lake_cell_count": 1,
                    "depression_policy": "overflow",
                    "storage_capacity_km3": 5.0,
                    "annual_runoff_km3": 5.0,
                    "fill_fraction": 1.0,
                    "overflows": True,
                    "overflow_stage_count": 2,
                    "overflow_path_cell_ids": [0],
                },
                {
                    "id": 11,
                    "lake_cell_count": 1,
                    "depression_policy": "overflow",
                    "storage_capacity_km3": 5.0,
                    "annual_runoff_km3": 5.0,
                    "fill_fraction": 1.0,
                    "overflows": True,
                    "overflow_stage_count": 2,
                    "overflow_path_cell_ids": [],
                },
            ],
        }

        result = enrich_world_with_lake_overflow_history(world, simulation_years=3)

        # Both basins were simulated and both spilled, so an empty channel list can
        # only come from the two-cell minimum on the path.
        self.assertEqual(
            [history["lake_basin_id"] for history in result["lake_overflow_histories"]],
            [10, 11],
        )
        self.assertEqual(_history(result, 10)["total_spill_km3"], 15.0)
        self.assertEqual(_history(result, 10)["overflow_path_cell_ids"], [0])
        self.assertEqual(_history(result, 11)["total_spill_km3"], 15.0)

        self.assertEqual(result["lake_overflow_channel_histories"], [])
        self.assertEqual(result["summary"]["lake_overflow_channel_history_count"], 0)
        self.assertEqual(result["summary"]["lake_overflow_channel_cell_count"], 0)
        self.assertEqual(result["summary"]["lake_overflow_channel_step_count"], 0)
        self.assertEqual(result["summary"]["active_lake_overflow_channel_count"], 0)
        self.assertEqual(result["summary"]["lake_overflow_channel_avulsion_count"], 0)
        for cell in result["cells"]:
            with self.subTest(cell_id=cell["id"]):
                self.assertIs(cell["overflow_channel_active"], False)

    def test_non_list_lake_basins_returns_the_world_untouched(self) -> None:
        world: dict[str, Any] = {"lake_basins": "bogus"}

        result = enrich_world_with_lake_overflow_history(world, simulation_years=3)

        self.assertIs(result, world)
        self.assertEqual(sorted(result), ["lake_basins"])
        self.assertEqual(result["lake_basins"], "bogus")
        self.assertNotIn("summary", result)
        self.assertNotIn("lake_overflow_histories", result)
        self.assertNotIn("lake_overflow_channel_histories", result)

    def test_overflow_path_without_planet_parameters_is_rejected(self) -> None:
        world = {"cells": _cells(), "lake_basins": [_overflowing_basin()]}

        with self.assertRaisesRegex(ValueError, r"^world must provide planet_parameters$"):
            enrich_world_with_lake_overflow_history(world, simulation_years=3)


class EvaporationAndOverflowStageTests(TestCase):
    def test_evaporation_loss_is_zero_without_surface_area_or_depth(self) -> None:
        cases = [
            ("no area", {"lake_area_km2": 0.0, "mean_water_depth_m": 50.0}),
            ("no depth", {"lake_area_km2": 100.0, "mean_water_depth_m": 0.0}),
            ("no keys", {}),
            ("negative area", {"lake_area_km2": -5.0, "mean_water_depth_m": 50.0}),
            ("negative depth", {"lake_area_km2": 100.0, "mean_water_depth_m": -50.0}),
        ]
        for label, basin in cases:
            with self.subTest(case=label):
                self.assertEqual(_annual_evaporation_loss_km3(basin), 0.0)

    def test_evaporation_depth_factor_is_clamped_between_the_floor_and_cap(self) -> None:
        # 1000 km2 of surface makes the returned volume equal the depth factor in metres.
        deep = _annual_evaporation_loss_km3(
            {"lake_area_km2": 1000.0, "mean_water_depth_m": 10000.0}
        )
        self.assertAlmostEqual(deep, 1.20, places=9)

        # The cap binds from 2125 m down: 0.35 + 2125 / 2500 == 1.20 exactly.
        just_at_cap = _annual_evaporation_loss_km3(
            {"lake_area_km2": 1000.0, "mean_water_depth_m": 2125.0}
        )
        self.assertAlmostEqual(just_at_cap, 1.20, places=9)
        below_cap = _annual_evaporation_loss_km3(
            {"lake_area_km2": 1000.0, "mean_water_depth_m": 2000.0}
        )
        self.assertAlmostEqual(below_cap, 1.15, places=9)

        # The 0.35 floor is unreachable: the factor tends to it from above as the
        # depth tends to zero, and depth <= 0 short-circuits to no loss at all.
        shallow = _annual_evaporation_loss_km3(
            {"lake_area_km2": 1000.0, "mean_water_depth_m": 1e-06}
        )
        self.assertAlmostEqual(shallow, 0.35, places=8)
        self.assertGreater(shallow, 0.35)

        # Between the bounds the factor is 0.35 + depth / 2500 m.
        self.assertAlmostEqual(
            _annual_evaporation_loss_km3(
                {"lake_area_km2": 100.0, "mean_water_depth_m": 50.0}
            ),
            0.037,
            places=9,
        )

    def test_overflow_stage_is_zero_without_spill_or_stages(self) -> None:
        cases = [
            ("no spill", 0.0, 6.0, 3),
            ("negative spill", -2.0, 6.0, 3),
            ("no stages", 5.0, 6.0, 0),
            ("negative stages", 5.0, 6.0, -1),
        ]
        for label, spill, runoff, stage_count in cases:
            with self.subTest(case=label):
                self.assertEqual(_overflow_stage(spill, runoff, stage_count), 0)

    def test_overflow_stage_ceils_runoff_pressure_and_caps_at_stage_count(self) -> None:
        cases = [
            ("tiny spill still reaches stage one", 0.001, 6.0, 3, 1),
            ("one sixth of runoff", 1.0, 6.0, 3, 1),
            ("one third of runoff", 2.0, 6.0, 3, 1),
            ("half of runoff", 3.0, 6.0, 3, 2),
            ("quarter of runoff over four stages", 2.0, 8.0, 4, 1),
            ("first simulated year", 4.963, 6.0, 3, 3),
            ("a full year of runoff", 6.0, 6.0, 3, 3),
            ("capped far above the top stage", 100.0, 6.0, 3, 3),
            ("runoff below one is floored at one", 0.5, 0.1, 4, 2),
        ]
        for label, spill, runoff, stage_count, expected in cases:
            with self.subTest(case=label):
                self.assertEqual(_overflow_stage(spill, runoff, stage_count), expected)
