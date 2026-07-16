from __future__ import annotations

from unittest import TestCase

from magic_geo.hydrology_realism import (
    VALID_WATERSHED_OUTLET_TYPES,
    enrich_world_with_hydrology_realism,
)


def _realism_check(world: dict, name: str) -> dict:
    return next(
        check
        for check in world["hydrology_realism_checks"]
        if check["name"] == name
    )


def _closed_land_river_world(watershed: dict) -> dict:
    return {
        "cells": [
            {
                "id": 0,
                "basin_id": 1,
                "flow_to": 1,
                "flow_accumulation": 10.0,
                "is_river": True,
                "elevation_m": 100.0,
                "neighbors": [1],
                "water_body_type": "land",
            },
            {
                "id": 1,
                "basin_id": 1,
                "flow_to": -1,
                "flow_accumulation": 12.0,
                "is_closed_basin": False,
                "is_lake": False,
                "is_river": False,
                "is_water": False,
                "elevation_m": 50.0,
                "neighbors": [0],
                "water_body_type": "land",
            },
        ],
        "watersheds": [
            {
                "basin_id": 1,
                "boundary_cell_ids": [],
                "outlet_cell_id": 1,
                **watershed,
            }
        ],
        "summary": {},
    }


def _marine_and_lacustrine_delta_world() -> dict:
    return {
        "cells": [
            {
                "id": 0,
                "basin_id": 1,
                "flow_to": 1,
                "flow_accumulation": 10.0,
                "is_river": True,
                "is_water": False,
                "is_lake": False,
                "landform": "delta",
                "elevation_m": 50.0,
                "sediment_thickness_m": 1.0,
                "sediment_deposition_m": 0.0,
                "runoff_mm_y": 100.0,
                "neighbors": [1],
                "water_body_type": "land",
            },
            {
                "id": 1,
                "basin_id": 1,
                "flow_to": -1,
                "flow_accumulation": 12.0,
                "is_river": False,
                "is_water": False,
                "is_lake": True,
                "landform": "lacustrine_basin",
                "elevation_m": 40.0,
                "neighbors": [0],
                "water_body_type": "fresh_lake",
            },
            {
                "id": 2,
                "basin_id": 3,
                "flow_to": 3,
                "flow_accumulation": 20.0,
                "is_river": True,
                "is_water": False,
                "is_lake": False,
                "landform": "delta",
                "elevation_m": 20.0,
                "sediment_thickness_m": 0.0,
                "sediment_deposition_m": 2.0,
                "runoff_mm_y": 200.0,
                "neighbors": [3],
                "water_body_type": "land",
            },
            {
                "id": 3,
                "basin_id": 3,
                "flow_to": -1,
                "flow_accumulation": 24.0,
                "is_river": False,
                "is_water": True,
                "is_lake": False,
                "landform": "ocean",
                "elevation_m": 0.0,
                "neighbors": [2],
                "water_body_type": "ocean",
            },
        ],
        "watersheds": [],
        "summary": {},
    }


class HydrologyRealismRegressionTests(TestCase):
    def test_watershed_outlet_vocabulary_is_canonical(self) -> None:
        expected_outlet_types = {
            "ocean",
            "lake",
            "saline_basin",
            "inland_sea",
            "closed_land",
        }
        self.assertEqual(VALID_WATERSHED_OUTLET_TYPES, expected_outlet_types)

        for outlet_type in sorted(expected_outlet_types):
            with self.subTest(outlet_type=outlet_type):
                world = _closed_land_river_world(
                    {
                        "outlet_type": outlet_type,
                        "is_endorheic": outlet_type != "ocean",
                    }
                )

                enrich_world_with_hydrology_realism(world)

                check = _realism_check(world, "river_terminal_sink_validity")
                self.assertEqual(check["value"], 1.0)
                self.assertTrue(check["passed"])
                self.assertEqual(
                    check["evidence"]["valid_sink_reason_counts"],
                    {f"watershed_outlet:{outlet_type}": 1},
                )

    def test_legacy_watershed_outlet_aliases_are_rejected(self) -> None:
        for outlet_type in ("fresh_lake", "endorheic"):
            with self.subTest(outlet_type=outlet_type):
                world = _closed_land_river_world(
                    {
                        "outlet_type": outlet_type,
                        "is_endorheic": False,
                    }
                )

                enrich_world_with_hydrology_realism(world)

                check = _realism_check(world, "river_terminal_sink_validity")
                self.assertEqual(check["value"], 0.0)
                self.assertFalse(check["passed"])
                self.assertEqual(
                    check["evidence"]["valid_sink_reason_counts"],
                    {},
                )

    def test_closed_land_and_endorheic_watershed_terminals_are_valid(self) -> None:
        cases = (
            (
                {"outlet_type": "closed_land", "is_endorheic": False},
                "watershed_outlet:closed_land",
            ),
            (
                {"outlet_type": "unknown", "is_endorheic": True},
                "watershed:is_endorheic",
            ),
        )
        for watershed, expected_reason in cases:
            with self.subTest(watershed=watershed):
                world = _closed_land_river_world(watershed)

                enrich_world_with_hydrology_realism(world)

                check = _realism_check(world, "river_terminal_sink_validity")
                self.assertEqual(check["value"], 1.0)
                self.assertTrue(check["passed"])
                self.assertEqual(check["evidence"]["valid_sink_river_cell_count"], 1)
                self.assertEqual(
                    check["evidence"]["valid_sink_reason_counts"],
                    {expected_reason: 1},
                )

    def test_unknown_open_land_terminal_remains_invalid(self) -> None:
        world = _closed_land_river_world(
            {"outlet_type": "unknown", "is_endorheic": False}
        )

        enrich_world_with_hydrology_realism(world)

        check = _realism_check(world, "river_terminal_sink_validity")
        self.assertEqual(check["value"], 0.0)
        self.assertFalse(check["passed"])
        self.assertEqual(check["evidence"]["valid_sink_reason_counts"], {})

    def test_lacustrine_and_marine_terminal_deltas_are_distinguished_and_valid(
        self,
    ) -> None:
        world = _marine_and_lacustrine_delta_world()

        enrich_world_with_hydrology_realism(world)

        check = _realism_check(
            world,
            "delta_lowland_sediment_terminal_water",
        )
        self.assertEqual(
            check["metric"],
            "fraction_delta_cells_low_sediment_river_at_marine_or_lacustrine_terminal",
        )
        self.assertEqual(check["value"], 1.0)
        self.assertTrue(check["passed"])
        self.assertIn("marine coast or lake", check["question"])
        self.assertEqual(check["evidence"]["delta_cell_count"], 2)
        self.assertEqual(check["evidence"]["marine_terminal_delta_count"], 1)
        self.assertEqual(check["evidence"]["lacustrine_terminal_delta_count"], 1)
        self.assertEqual(
            check["evidence"]["lowland_sediment_terminal_water_delta_count"],
            2,
        )
        self.assertEqual(
            world["summary"]["delta_lowland_sediment_terminal_water_index"],
            1.0,
        )

    def test_delta_without_a_recognized_terminal_water_body_is_not_accepted(
        self,
    ) -> None:
        world = _marine_and_lacustrine_delta_world()
        world["cells"][1].update(
            {
                "is_lake": False,
                "water_body_type": "land",
            }
        )

        enrich_world_with_hydrology_realism(world)

        check = _realism_check(
            world,
            "delta_lowland_sediment_terminal_water",
        )
        self.assertEqual(check["value"], 0.5)
        self.assertFalse(check["passed"])
        self.assertEqual(check["evidence"]["unrecognized_terminal_delta_count"], 1)
