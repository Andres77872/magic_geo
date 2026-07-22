"""Error, degenerate, and classification paths of three world enrichers.

``enrich_world_with_route_corridors``, ``enrich_world_with_natural_frontiers``,
and ``enrich_world_with_worldbuilding_realism`` all take the happy path through a
generated world: every route resolves, every realism claim clears its target, and
the 128-cell replay world has no political borders at all. The branches that
report a violation, classify an unusual corridor or frontier, or recover from a
malformed payload therefore never run there.

Every case below is a hand-built world small enough to reason about exactly, so
an assertion names the offending record and field rather than a bulk shape. Each
tampered world is paired with an untampered control asserting the same call is
clean, which is what proves a failure came from the tamper.
"""

from __future__ import annotations

from typing import Any
from unittest import TestCase

from magic_geo.natural_frontiers import enrich_world_with_natural_frontiers
from magic_geo.route_corridors import enrich_world_with_route_corridors
from magic_geo.worldbuilding_realism import enrich_world_with_worldbuilding_realism

from support import worlds


PLANET = {"radius_km": 6371.0}


def corridor_cell(cell_id: int, neighbors: list[int], **fields: Any) -> dict[str, Any]:
    """A featureless land cell on the equator, one degree of longitude per id."""
    cell: dict[str, Any] = {
        "id": cell_id,
        "lat_deg": 0.0,
        "lon_deg": float(cell_id),
        "neighbors": list(neighbors),
        "is_water": False,
        "water_body_type": "land",
        "elevation_m": 200.0,
        "landform": "plain",
        "biome": "grassland",
    }
    cell.update(fields)
    return cell


def corridor_chain(count: int, **fields: Any) -> list[dict[str, Any]]:
    """``count`` land cells wired into a single open chain."""
    return mixed_chain([fields] * count)


def mixed_chain(per_cell_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One open chain whose cells each take their own field overrides."""
    count = len(per_cell_fields)
    return [
        corridor_cell(
            index,
            [neighbor for neighbor in (index - 1, index + 1) if 0 <= neighbor < count],
            **fields,
        )
        for index, fields in enumerate(per_cell_fields)
    ]


#: A marine cell whose coastal route index clears the 0.45 feature threshold.
OCEAN_FIELDS = {
    "is_water": True,
    "water_body_type": "ocean",
    "elevation_m": -50.0,
    "coastal_navigability_index": 0.9,
    "water_depth_m": 100.0,
}
#: A navigable floodplain whose river-valley route index clears the threshold.
RIVER_FIELDS = {
    "is_river": True,
    "landform": "floodplain",
    "elevation_m": 50.0,
    "river_navigability_index": 0.8,
}
#: A low mountain cell: a pass between two peaks clears the threshold.
SADDLE_FIELDS = {"landform": "mountain", "elevation_m": 700.0}
#: A high mountain cell, too high above its neighbours to be a pass itself.
PEAK_FIELDS = {"landform": "mountain", "elevation_m": 2200.0}


def corridor_world(
    cells: Any,
    settlements: Any,
    routes: Any,
) -> dict[str, Any]:
    return {
        "cells": cells,
        "settlements": settlements,
        "routes": routes,
        "summary": {},
        "planet_parameters": dict(PLANET),
    }


def two_settlement_route(
    cells: list[dict[str, Any]],
    route_type: str,
) -> dict[str, Any]:
    """One route spanning a whole chain, so the path is the whole chain."""
    last = len(cells) - 1
    return corridor_world(
        cells,
        [
            {"id": 0, "cell_id": 0, "region_id": 0, "type": "town"},
            {"id": 1, "cell_id": last, "region_id": 1, "type": "town"},
        ],
        [
            {
                "id": 0,
                "from": 0,
                "to": 1,
                "type": route_type,
                "distance_km": 111.19 * last,
            }
        ],
    )


class RouteCorridorClassificationTests(TestCase):
    """``corridor_type`` is chosen by route type first, then by feature counts."""

    def test_route_type_preference_selects_matching_corridor_type(self) -> None:
        cases = (
            ("coastal_sea", OCEAN_FIELDS, 5, "coastal_corridor", "coastal_cell_count", 5),
            (
                "river_corridor",
                RIVER_FIELDS,
                5,
                "river_valley_corridor",
                "river_valley_cell_count",
                5,
            ),
        )
        for route_type, fields, count, expected_type, count_key, expected_count in cases:
            with self.subTest(route_type=route_type):
                world = two_settlement_route(corridor_chain(count, **fields), route_type)
                enrich_world_with_route_corridors(world)
                corridors = world["route_corridors"]
                self.assertEqual(len(corridors), 1, corridors)
                record = corridors[0]
                self.assertEqual(record["route_type"], route_type)
                self.assertEqual(record["corridor_type"], expected_type)
                self.assertEqual(record[count_key], expected_count)
                self.assertEqual(record["cell_ids"], list(range(count)))
                self.assertEqual(world["routes"][0]["route_corridor_type"], expected_type)

    def test_route_type_preference_outranks_the_majority_feature_count(self) -> None:
        """The route's own feature wins even when another feature is commoner.

        Each chain carries two features at once, and the commoner one is never
        the one the route type prefers. The ``overland`` control takes the
        lexical-count fall-through and so names the majority feature; only the
        route-type preference can name the minority one.
        """
        cases = (
            (
                "coastal_sea",
                [RIVER_FIELDS] * 4 + [OCEAN_FIELDS] * 2,
                ("coastal_corridor", "coastal_cell_count", 2),
                ("river_valley_corridor", "river_valley_cell_count", 4),
            ),
            (
                "river_corridor",
                [OCEAN_FIELDS] * 4 + [RIVER_FIELDS] * 2,
                ("river_valley_corridor", "river_valley_cell_count", 2),
                ("coastal_corridor", "coastal_cell_count", 4),
            ),
            (
                "mountain_pass",
                [RIVER_FIELDS] * 4 + [SADDLE_FIELDS, PEAK_FIELDS, SADDLE_FIELDS],
                ("mountain_pass_corridor", "mountain_pass_cell_count", 2),
                ("river_valley_corridor", "river_valley_cell_count", 4),
            ),
        )
        for route_type, fields, preferred, majority in cases:
            preferred_type, preferred_key, preferred_count = preferred
            majority_type, majority_key, majority_count = majority
            with self.subTest(route_type=route_type):
                self.assertLess(preferred_count, majority_count)

                control = two_settlement_route(mixed_chain(fields), "overland")
                enrich_world_with_route_corridors(control)
                control_record = control["route_corridors"][0]
                self.assertEqual(control_record["cell_ids"], list(range(len(fields))))
                self.assertEqual(control_record["corridor_type"], majority_type)

                world = two_settlement_route(mixed_chain(fields), route_type)
                enrich_world_with_route_corridors(world)
                record = world["route_corridors"][0]
                self.assertEqual(record["cell_ids"], list(range(len(fields))))
                self.assertEqual(record["corridor_type"], preferred_type)
                self.assertEqual(record[preferred_key], preferred_count)
                self.assertEqual(record[majority_key], majority_count)

    def test_mountain_pass_route_over_saddles_between_peaks(self) -> None:
        cells = mixed_chain(
            [SADDLE_FIELDS, PEAK_FIELDS, SADDLE_FIELDS, PEAK_FIELDS, SADDLE_FIELDS]
        )
        world = two_settlement_route(cells, "mountain_pass")
        enrich_world_with_route_corridors(world)
        record = world["route_corridors"][0]
        self.assertEqual(record["corridor_type"], "mountain_pass_corridor")
        # Only the saddles clear the threshold; the two peaks are too high to pass.
        self.assertEqual(record["mountain_pass_cell_count"], 3)
        self.assertEqual(
            [cell["id"] for cell in world["cells"] if cell["mountain_pass_route_index"] >= 0.45],
            [0, 2, 4],
        )

    def test_route_type_without_matching_features_falls_back_to_feature_counts(self) -> None:
        """A coastal_sea route across an inland river chain classifies by count."""
        control = two_settlement_route(corridor_chain(4, **RIVER_FIELDS), "river_corridor")
        enrich_world_with_route_corridors(control)
        self.assertEqual(control["route_corridors"][0]["corridor_type"], "river_valley_corridor")

        world = two_settlement_route(corridor_chain(4, **RIVER_FIELDS), "coastal_sea")
        enrich_world_with_route_corridors(world)
        record = world["route_corridors"][0]
        self.assertEqual(record["route_type"], "coastal_sea")
        self.assertEqual(record["coastal_cell_count"], 0)
        self.assertEqual(record["river_valley_cell_count"], 4)
        self.assertEqual(record["corridor_type"], "river_valley_corridor")

    def test_overland_desert_route_classifies_as_oasis_corridor(self) -> None:
        plain = two_settlement_route(corridor_chain(4), "overland")
        enrich_world_with_route_corridors(plain)
        plain_record = plain["route_corridors"][0]
        self.assertEqual(plain_record["corridor_type"], "overland_corridor")
        self.assertEqual(plain_record["named_feature_cell_count"], 0)
        self.assertEqual(plain["summary"]["route_feature_coverage_index"], 0.0)

        world = two_settlement_route(
            corridor_chain(4, biome="hot_desert", groundwater_recharge_mm_y=180.0),
            "overland",
        )
        enrich_world_with_route_corridors(world)
        record = world["route_corridors"][0]
        self.assertEqual(record["corridor_type"], "oasis_corridor")
        self.assertEqual(record["oasis_cell_count"], 4)
        self.assertEqual(record["mountain_pass_cell_count"], 0)
        self.assertEqual(record["coastal_cell_count"], 0)
        self.assertEqual(record["river_valley_cell_count"], 0)
        self.assertEqual(record["named_feature_cell_count"], 4)
        self.assertEqual(world["summary"]["route_feature_coverage_index"], 1.0)
        self.assertEqual(world["summary"]["route_corridor_type_counts"], {"oasis_corridor": 1})

    def test_water_cells_and_landlocked_flanks_have_no_mountain_pass_index(self) -> None:
        """Flooding the peak zeroes its own index and both its neighbours'.

        The two guards return the same 0.0 as an ordinary flat cell, so the
        control has to show the very same three cells scoring above zero when
        the middle one is dry land. Only ``is_water``/``water_body_type``
        differ between the two worlds; the elevation stays at 2400 m.
        """

        def build(middle: dict[str, Any]) -> dict[str, Any]:
            cells = [
                corridor_cell(0, [1]),
                corridor_cell(1, [0, 2], **middle),
                corridor_cell(2, [1]),
            ]
            return corridor_world(cells, [], [])

        peak = {"landform": "mountain", "elevation_m": 2400.0}
        control = build(peak)
        enrich_world_with_route_corridors(control)
        control_by_id = {cell["id"]: cell for cell in control["cells"]}
        # A 200 m plain beside a 2400 m peak is itself a pass; the peak is not.
        self.assertEqual(control_by_id[0]["mountain_pass_route_index"], 0.602281)
        self.assertEqual(control_by_id[2]["mountain_pass_route_index"], 0.602281)
        self.assertEqual(control_by_id[1]["mountain_pass_route_index"], 0.3784)

        world = build(dict(peak, is_water=True, water_body_type="ocean"))
        enrich_world_with_route_corridors(world)
        by_id = {cell["id"]: cell for cell in world["cells"]}
        # cell 1 is water, so the water guard fires before any neighbour is read.
        self.assertEqual(by_id[1]["mountain_pass_route_index"], 0.0)
        # cells 0 and 2 now have no land neighbour at all.
        self.assertEqual(by_id[0]["mountain_pass_route_index"], 0.0)
        self.assertEqual(by_id[2]["mountain_pass_route_index"], 0.0)
        # The tamper is visible the other way round too: they gained a coast.
        self.assertEqual(control_by_id[0]["coastal_route_index"], 0.0)
        self.assertEqual(by_id[0]["coastal_route_index"], 0.23)

    def test_flat_land_neighbourhood_has_no_mountain_context(self) -> None:
        world = corridor_world(corridor_chain(3), [], [])
        enrich_world_with_route_corridors(world)
        for cell in world["cells"]:
            with self.subTest(cell_id=cell["id"]):
                self.assertEqual(cell["mountain_pass_route_index"], 0.0)
                self.assertEqual(cell["coastal_route_index"], 0.0)
                self.assertEqual(cell["oasis_route_index"], 0.0)
                # Low relief alone: 0.12 * (1 - 200 / 1900), below the threshold.
                self.assertEqual(cell["river_valley_route_index"], 0.107368)


class RouteCorridorDegenerateTests(TestCase):
    """Routes that cannot be resolved are recorded as absent, not as corridors."""

    def test_missing_or_empty_cells_leaves_world_untouched(self) -> None:
        control = corridor_world(corridor_chain(2), [], [])
        self.assertIs(enrich_world_with_route_corridors(control), control)
        self.assertEqual(control["route_corridors"], [])
        self.assertIn("route_corridor_model", control)

        for label, cells in (("empty_list", []), ("not_a_list", None), ("mapping", {})):
            with self.subTest(cells=label):
                world: dict[str, Any] = {"cells": cells, "summary": {}}
                self.assertIs(enrich_world_with_route_corridors(world), world)
                self.assertNotIn("route_corridors", world)
                self.assertNotIn("route_corridor_model", world)
                self.assertEqual(world["summary"], {})

    def test_non_list_routes_and_settlements_are_coerced_to_empty(self) -> None:
        control = corridor_world(
            corridor_chain(3),
            [{"id": 0, "cell_id": 0, "region_id": 0}, {"id": 1, "cell_id": 2, "region_id": 1}],
            [{"id": 0, "from": 0, "to": 1, "type": "overland", "distance_km": 222.4}],
        )
        enrich_world_with_route_corridors(control)
        self.assertEqual(len(control["route_corridors"]), 1)
        self.assertEqual(control["summary"]["route_feature_coverage_index"], 0.0)

        world = corridor_world(corridor_chain(3), None, "not-a-list")
        enrich_world_with_route_corridors(world)
        self.assertEqual(world["route_corridors"], [])
        self.assertEqual(world["route_corridor_model"]["route_count"], 0)
        self.assertEqual(world["route_corridor_model"]["corridor_count"], 0)
        self.assertEqual(world["summary"]["route_corridor_count"], 0)
        self.assertEqual(world["summary"]["route_corridor_cell_count"], 0)
        # With no corridors at all the coverage index is vacuously perfect.
        self.assertEqual(world["summary"]["route_feature_coverage_index"], 1.0)
        self.assertEqual(world["summary"]["route_corridor_type_counts"], {})

    def test_unresolvable_routes_are_marked_without_a_corridor(self) -> None:
        cells = [
            corridor_cell(0, [1]),
            corridor_cell(1, [0, 2, 99]),  # 99 does not exist: skipped while expanding
            corridor_cell(2, [1]),
            corridor_cell(5, []),  # unreachable island
        ]
        settlements = [
            {"id": 0, "cell_id": 0, "region_id": 0},
            {"id": 1, "cell_id": 2, "region_id": 1},
            {"id": 2, "cell_id": 5, "region_id": 2},
            {"id": 3, "cell_id": 77, "region_id": 3},  # cell 77 does not exist
            {"id": 4, "cell_id": 0, "region_id": 0},  # shares cell 0 with settlement 0
        ]
        routes = [
            {"id": 0, "from": 0, "to": 4, "type": "overland", "distance_km": 0.0},
            {"id": 1, "from": 0, "to": 2, "type": "overland", "distance_km": 400.0},
            {"id": 2, "from": 0, "to": 3, "type": "overland", "distance_km": 400.0},
            {"id": 3, "from": 0, "to": 99, "type": "overland", "distance_km": 400.0},
            {"id": 4, "from": 0, "to": 1, "type": "overland", "distance_km": 222.4},
            {"id": -1, "from": 0, "to": 1, "type": "overland", "distance_km": 222.4},
            "not-a-route",
        ]
        world = corridor_world(cells, settlements, routes)
        enrich_world_with_route_corridors(world)

        by_route_id = {route["id"]: route for route in routes if isinstance(route, dict)}
        for route_id, reason in (
            (1, "unreachable island cell 5"),
            (2, "endpoint cell 77 is absent"),
            (3, "settlement 99 is absent"),
        ):
            with self.subTest(route_id=route_id, reason=reason):
                route = by_route_id[route_id]
                self.assertEqual(route["route_corridor_id"], -1)
                self.assertEqual(route["route_corridor_type"], "none")
                self.assertEqual(route["path_cell_ids"], [])

        # Only routes 0 and 4 produce corridors, numbered in ascending route order.
        self.assertEqual([record["route_id"] for record in world["route_corridors"]], [0, 4])
        self.assertEqual([record["id"] for record in world["route_corridors"]], [0, 1])
        self.assertEqual(world["summary"]["route_corridor_count"], 2)
        # The id == -1 route and the non-dict entry never enter the route table.
        self.assertEqual(world["route_corridor_model"]["route_count"], 5)

        self_route = world["route_corridors"][0]
        self.assertEqual(self_route["cell_ids"], [0])
        self.assertEqual(self_route["cell_count"], 1)
        self.assertEqual(self_route["path_length_km"], 0.0)
        self.assertEqual(self_route["straight_distance_km"], 0.001)
        self.assertEqual(self_route["detour_ratio"], 0.0)
        self.assertEqual(self_route["region_ids"], [0])
        self.assertEqual(self_route["settlement_ids"], [0, 4])

        spanning = world["route_corridors"][1]
        self.assertEqual(spanning["cell_ids"], [0, 1, 2])
        self.assertEqual(spanning["region_ids"], [0, 1])
        # Equal membership ties are won by the later route, so cell 0 belongs to 1.
        by_id = {cell["id"]: cell for cell in world["cells"]}
        self.assertEqual(by_id[0]["route_corridor_id"], 1)
        # Membership is 0.35 plus 0.65 of the strongest feature on the cell; the
        # only non-zero feature on a flat 200 m plain is the river-valley index.
        self.assertEqual(by_id[0]["river_valley_route_index"], 0.107368)
        self.assertEqual(by_id[0]["route_corridor_index"], 0.419789)
        self.assertEqual(by_id[5]["route_corridor_id"], -1)
        self.assertEqual(by_id[5]["route_corridor_type"], "none")
        self.assertEqual(by_id[5]["route_corridor_index"], 0.0)

    def test_generated_world_control_is_clean(self) -> None:
        world = worlds.cached_world("replay_128")
        summary = world["summary"]
        self.assertEqual(summary["route_corridor_count"], len(world["route_corridors"]))
        enrich_world_with_route_corridors(world)
        self.assertEqual(summary["route_corridor_count"], len(world["route_corridors"]))
        self.assertTrue(world["route_corridors"])
        for record in world["route_corridors"]:
            with self.subTest(corridor_id=record["id"]):
                self.assertNotEqual(record["corridor_type"], "none")
                self.assertGreater(record["cell_count"], 0)


def frontier_cell(cell_id: int, neighbors: list[int], **fields: Any) -> dict[str, Any]:
    """A cell whose barrier signals are all off unless a case turns one on."""
    cell: dict[str, Any] = {
        "id": cell_id,
        "neighbors": list(neighbors),
        "elevation_m": 0.0,
        "landform": "plain",
        "biome": "grassland",
        "water_body_type": "land",
        "ice_thickness_m": 0.0,
        "permafrost_class": "none",
        "is_river": False,
        "seasonal_aridity_index": 0.0,
        "area_km2": 100.0,
    }
    cell.update(fields)
    return cell


def frontier_world(cells: Any, borders: Any, **parts: Any) -> dict[str, Any]:
    world: dict[str, Any] = {"cells": cells, "borders": borders, "summary": {}}
    world.update(parts)
    return world


def open_border(**fields: Any) -> dict[str, Any]:
    """An ``open_lowland`` border that qualifies only through its barrier score."""
    border = {
        "id": 0,
        "cell_a": 0,
        "cell_b": 1,
        "region_a": 0,
        "region_b": 1,
        "type": "open_lowland",
        "barrier_score": 0.45,
        "length_km": 10.0,
    }
    border.update(fields)
    return border


class NaturalFrontierClassificationTests(TestCase):
    """Frontier type and index come from the border, then from its two cells."""

    def test_open_border_takes_its_type_and_index_from_the_cells(self) -> None:
        # frontier_index == max(0.45 * 0.72 + local * 0.28, 0.45); the local score
        # is the mean of the two identical cells, so it is the cell score itself.
        cases = (
            ("plain_lowland", {}, "terrain_barrier", 0.45),
            ("mountain_landform", {"landform": "mountain"}, "mountain", 0.5368),
            ("deep_negative_elevation", {"elevation_m": -3100.0}, "mountain", 0.604),
            ("ice_thickness", {"ice_thickness_m": 210.0}, "ice", 0.464),
            ("permafrost_ice_sheet", {"permafrost_class": "ice_sheet"}, "ice", 0.4864),
            ("river_flag", {"is_river": True}, "river", 0.4976),
            ("river_landform", {"landform": "alluvial_fan"}, "river", 0.4976),
            ("marine_water_body", {"water_body_type": "continental_shelf"}, "coastal", 0.4752),
            ("aridity", {"seasonal_aridity_index": 0.8}, "desert", 0.548),
            ("desert_biome", {"biome": "cold_desert"}, "desert", 0.5088),
            ("dense_forest_biome", {"biome": "tropical_rainforest"}, "dense_forest", 0.4864),
            ("wetland_biome", {"biome": "wetland"}, "wetland", 0.4696),
            ("wetland_landform", {"landform": "wetland"}, "wetland", 0.4696),
        )
        for label, fields, expected_type, expected_index in cases:
            with self.subTest(case=label):
                world = frontier_world(
                    [frontier_cell(0, [1], **fields), frontier_cell(1, [0], **fields)],
                    [open_border()],
                )
                enrich_world_with_natural_frontiers(world)
                records = world["natural_frontiers"]
                self.assertEqual(len(records), 1, records)
                record = records[0]
                self.assertEqual(record["frontier_type"], expected_type)
                self.assertEqual(record["cell_ids"], [0, 1])
                self.assertAlmostEqual(record["mean_frontier_index"], expected_index, places=5)
                self.assertEqual(record["mean_barrier_score"], 0.45)
                for cell in world["cells"]:
                    self.assertEqual(cell["natural_frontier_type"], expected_type)
                    self.assertEqual(cell["natural_frontier_id"], 0)
                self.assertEqual(
                    world["summary"]["natural_frontier_type_counts"],
                    {expected_type: 1},
                )

    def test_barrier_type_priority_between_competing_signals(self) -> None:
        """Every neighbouring pair in the priority chain, tested head to head.

        Each cell carries both signals at once, so the expected type is the one
        the earlier ``if`` returns; the loser would win if the order flipped.
        """
        cases = (
            ("ice_over_river", {"ice_thickness_m": 210.0, "is_river": True}, "ice"),
            ("river_over_coastal", {"is_river": True, "water_body_type": "ocean"}, "river"),
            ("coastal_over_mountain", {"water_body_type": "ocean", "landform": "mountain"}, "coastal"),
            ("mountain_over_desert", {"landform": "ridge", "biome": "hot_desert"}, "mountain"),
            # Aridity is the desert signal here, so the biome stays a forest one.
            (
                "desert_over_dense_forest",
                {"biome": "tropical_rainforest", "seasonal_aridity_index": 0.9},
                "desert",
            ),
            # "wetland" is a wetland landform but not one of the river landforms.
            (
                "dense_forest_over_wetland",
                {"biome": "tropical_rainforest", "landform": "wetland"},
                "dense_forest",
            ),
        )
        for label, fields, expected_type in cases:
            with self.subTest(case=label):
                world = frontier_world(
                    [frontier_cell(0, [1], **fields), frontier_cell(1, [0], **fields)],
                    [open_border()],
                )
                enrich_world_with_natural_frontiers(world)
                self.assertEqual(world["natural_frontiers"][0]["frontier_type"], expected_type)

    def test_typed_border_keeps_its_own_type_and_hard_floor(self) -> None:
        world = frontier_world(
            [frontier_cell(0, [1]), frontier_cell(1, [0])],
            [open_border(type="mountain", barrier_score=0.0)],
        )
        enrich_world_with_natural_frontiers(world)
        record = world["natural_frontiers"][0]
        self.assertEqual(record["frontier_type"], "mountain")
        # A non-open border qualifies at zero barrier score and floors at 0.45.
        self.assertEqual(record["mean_barrier_score"], 0.0)
        self.assertEqual(record["mean_frontier_index"], 0.45)
        self.assertEqual(world["summary"]["mountain_frontier_count"], 1)
        self.assertEqual(world["summary"]["river_frontier_count"], 0)


class NaturalFrontierDegenerateTests(TestCase):
    """Borders that do not qualify, do not resolve, or are not borders at all."""

    def test_missing_or_empty_cells_leaves_world_untouched(self) -> None:
        control = frontier_world([frontier_cell(0, [1]), frontier_cell(1, [0])], [open_border()])
        self.assertIs(enrich_world_with_natural_frontiers(control), control)
        self.assertEqual(len(control["natural_frontiers"]), 1)

        for label, cells in (("empty_list", []), ("not_a_list", None)):
            with self.subTest(cells=label):
                world = frontier_world(cells, [open_border()])
                self.assertIs(enrich_world_with_natural_frontiers(world), world)
                self.assertNotIn("natural_frontiers", world)
                self.assertNotIn("natural_frontier_model", world)
                self.assertEqual(world["summary"], {})

    def test_non_qualifying_borders_produce_no_frontier(self) -> None:
        cases = (
            ("borders_not_a_list", None),
            ("open_and_below_threshold", [open_border(barrier_score=0.44)]),
            ("border_is_not_a_mapping", ["not-a-border"]),
            ("cell_a_absent", [open_border(cell_a=99)]),
            ("cell_b_absent", [open_border(cell_b=99)]),
        )
        for label, borders in cases:
            with self.subTest(case=label):
                world = frontier_world(
                    [frontier_cell(0, [1]), frontier_cell(1, [0])],
                    borders,
                )
                enrich_world_with_natural_frontiers(world)
                self.assertEqual(world["natural_frontiers"], [])
                summary = world["summary"]
                self.assertEqual(summary["natural_frontier_count"], 0)
                self.assertEqual(summary["natural_frontier_cell_count"], 0)
                self.assertEqual(summary["natural_frontier_border_segment_count"], 0)
                self.assertEqual(summary["mean_natural_frontier_index"], 0.0)
                self.assertEqual(summary["mean_natural_frontier_barrier_score"], 0.0)
                self.assertEqual(summary["natural_frontier_type_counts"], {})
                for cell in world["cells"]:
                    self.assertEqual(cell["natural_frontier_type"], "none")
                    self.assertEqual(cell["natural_frontier_id"], -1)
                    self.assertEqual(cell["natural_frontier_index"], 0.0)

    def test_unusable_neighbour_list_splits_a_frontier_component(self) -> None:
        def build(middle_neighbors: Any) -> dict[str, Any]:
            cells = [
                frontier_cell(0, [1]),
                frontier_cell(1, [0, 2]),
                frontier_cell(2, [1, 3]),
                frontier_cell(3, [2]),
            ]
            cells[1]["neighbors"] = middle_neighbors
            return frontier_world(
                cells,
                [
                    open_border(id=0, cell_a=0, cell_b=1),
                    open_border(id=1, cell_a=2, cell_b=3),
                ],
            )

        control = build([0, 2])
        enrich_world_with_natural_frontiers(control)
        self.assertEqual([record["cell_ids"] for record in control["natural_frontiers"]], [[0, 1, 2, 3]])

        world = build(None)
        self.assertIsNotNone(control["cells"][1]["neighbors"])
        enrich_world_with_natural_frontiers(world)
        self.assertEqual(
            [record["cell_ids"] for record in world["natural_frontiers"]],
            [[0, 1], [2, 3]],
        )
        self.assertEqual(world["summary"]["natural_frontier_count"], 2)
        self.assertEqual([cell["natural_frontier_id"] for cell in world["cells"]], [0, 0, 1, 1])

    def test_record_links_drop_unusable_settlements_routes_and_waterways(self) -> None:
        def build(**parts: Any) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "settlements": [
                    {"id": 7, "cell_id": 0, "region_id": 0},
                    {"id": 8, "cell_id": 1, "region_id": 1},
                ],
                "routes": [{"id": 3, "from": 7, "to": 8}],
                "navigable_waterways": [{"id": 4, "cell_ids": [0, 1]}],
            }
            payload.update(parts)
            return frontier_world(
                [frontier_cell(0, [1]), frontier_cell(1, [0])],
                [open_border(type="mountain", barrier_score=0.8, length_km=25.0)],
                **payload,
            )

        control = build()
        enrich_world_with_natural_frontiers(control)
        record = control["natural_frontiers"][0]
        self.assertEqual(record["settlement_ids"], [7, 8])
        self.assertEqual(record["route_ids"], [3])
        self.assertEqual(record["route_crossing_count"], 1)
        self.assertEqual(record["navigable_waterway_ids"], [4])
        self.assertEqual(record["region_ids"], [0, 1])
        self.assertEqual(record["border_ids"], [0])
        self.assertEqual(record["total_border_length_km"], 25.0)
        self.assertEqual(record["area_km2"], 200.0)
        self.assertEqual(record["dominant_landform"], "plain")
        self.assertEqual(record["dominant_biome"], "grassland")

        cases = (
            ("settlements_not_a_list", {"settlements": None}, [], []),
            ("routes_not_a_list", {"routes": None}, [7, 8], []),
            (
                "negative_route_id",
                {"routes": [{"id": -1, "from": 7, "to": 8}]},
                [7, 8],
                [],
            ),
            (
                "route_endpoint_absent",
                {"routes": [{"id": 3, "from": 99, "to": 8}]},
                [7, 8],
                [],
            ),
            (
                "intra_region_route",
                {
                    "settlements": [
                        {"id": 7, "cell_id": 0, "region_id": 0},
                        {"id": 8, "cell_id": 1, "region_id": 0},
                    ]
                },
                [7, 8],
                [],
            ),
            (
                "unidentified_settlement",
                {"settlements": [{"id": -1, "cell_id": 0, "region_id": 0}]},
                [],
                [],
            ),
        )
        for label, parts, expected_settlements, expected_routes in cases:
            with self.subTest(case=label):
                world = build(**parts)
                enrich_world_with_natural_frontiers(world)
                record = world["natural_frontiers"][0]
                self.assertEqual(record["settlement_ids"], expected_settlements)
                self.assertEqual(record["route_ids"], expected_routes)
                self.assertEqual(record["route_crossing_count"], len(expected_routes))

        for label, waterways in (
            ("waterways_not_a_list", None),
            ("negative_waterway_id", [{"id": -1, "cell_ids": [0, 1]}]),
        ):
            with self.subTest(case=label):
                world = build(navigable_waterways=waterways)
                enrich_world_with_natural_frontiers(world)
                self.assertEqual(world["natural_frontiers"][0]["navigable_waterway_ids"], [])

    def test_generated_world_control_is_clean(self) -> None:
        world = worlds.cached_world("small_smoke")
        self.assertTrue(world["borders"])
        before = [dict(record) for record in world["natural_frontiers"]]
        enrich_world_with_natural_frontiers(world)
        self.assertEqual(world["natural_frontiers"], before)
        self.assertEqual(world["summary"]["natural_frontier_count"], len(before))
        for record in before:
            with self.subTest(frontier_id=record["id"]):
                self.assertGreater(record["border_segment_count"], 0)
                self.assertNotEqual(record["frontier_type"], "none")


def realism_cell(cell_id: int, neighbors: list[int], **fields: Any) -> dict[str, Any]:
    cell: dict[str, Any] = {
        "id": cell_id,
        "neighbors": list(neighbors),
        "is_river": False,
        "is_lake": False,
        "water_body_type": "land",
        "runoff_mm_y": 0.0,
        "landform": "plain",
        "biome": "grassland",
        "crust_type": "continental_crust",
        "lithology": "granite",
        "boundary_convergent": 0.0,
        "boundary_divergent": 0.0,
        "crust_age_ma": 100.0,
        "sediment_thickness_m": 0.0,
        "flow_accumulation": 0.0,
        "fertility": 0.1,
        "soil_salinity_index": 0.0,
    }
    cell.update(fields)
    return cell


#: Distinguishes "caller passed no cells" from "caller passed ``None`` on purpose".
DEFAULT_CELLS = object()


def realism_world(cells: Any = DEFAULT_CELLS, **parts: Any) -> dict[str, Any]:
    world: dict[str, Any] = {
        "cells": [realism_cell(0, [])] if cells is DEFAULT_CELLS else cells,
        "summary": {},
    }
    world.update(parts)
    return world


def check_by_name(world: dict[str, Any], name: str) -> dict[str, Any]:
    for check in world["worldbuilding_realism_checks"]:
        if check["name"] == name:
            return check
    raise AssertionError(f"no worldbuilding realism check named {name!r}")


class WorldbuildingRealismCheckTests(TestCase):
    """Each realism claim scores against its own target interval."""

    def test_empty_world_passes_every_check_vacuously(self) -> None:
        world = realism_world(
            settlements="nope",
            routes=None,
            political_regions=7,
            borders={},
            resource_deposits="nope",
        )
        enrich_world_with_worldbuilding_realism(world)
        checks = world["worldbuilding_realism_checks"]
        self.assertEqual(
            [check["name"] for check in checks],
            world["worldbuilding_realism_model"]["check_order"],
        )
        for check in checks:
            with self.subTest(check=check["name"]):
                self.assertEqual(check["value"], 1.0)
                self.assertEqual(check["score"], 1.0)
                self.assertTrue(check["passed"])
        self.assertEqual(world["summary"]["worldbuilding_realism_pass_count"], 5)
        self.assertEqual(world["summary"]["worldbuilding_realism_pass_fraction"], 1.0)
        self.assertEqual(world["summary"]["mean_worldbuilding_realism_score"], 1.0)

    def test_missing_or_empty_cells_leaves_world_untouched(self) -> None:
        for label, cells in (("empty_list", []), ("not_a_list", None)):
            with self.subTest(cells=label):
                world = realism_world(cells=cells)
                self.assertIs(enrich_world_with_worldbuilding_realism(world), world)
                self.assertNotIn("worldbuilding_realism_checks", world)
                self.assertNotIn("worldbuilding_realism_model", world)
                self.assertEqual(world["summary"], {})

    def test_large_settlement_water_access_fails_its_evidence_requirement(self) -> None:
        cells = [
            realism_cell(0, [1], is_river=True),
            realism_cell(1, [0]),
        ]
        control = realism_world(
            cells=cells,
            settlements=[
                {"id": 0, "cell_id": 0, "score": 0.9},
                {"id": 1, "cell_id": 0, "score": 0.8},
            ],
        )
        enrich_world_with_worldbuilding_realism(control)
        control_check = check_by_name(control, "large_settlement_water_access")
        self.assertEqual(control_check["value"], 1.0)
        self.assertTrue(control_check["passed"])

        world = realism_world(
            cells=cells,
            settlements=[
                {"id": 0, "cell_id": 0, "score": 0.9},
                {"id": 1, "cell_id": 1, "score": 0.8},
            ],
        )
        enrich_world_with_worldbuilding_realism(world)
        check = check_by_name(world, "large_settlement_water_access")
        self.assertEqual(check["id"], 0)
        self.assertEqual(check["domain"], "worldbuilding")
        self.assertEqual(check["metric"], "fraction_top_settlements_with_water_access")
        self.assertEqual(check["target_min"], 0.85)
        self.assertEqual(check["target_max"], 1.0)
        self.assertEqual(check["value"], 0.5)
        self.assertFalse(check["passed"])
        # Below target the score is the shortfall ratio value / target_min.
        self.assertEqual(check["score"], 0.588235)
        self.assertEqual(check["evidence"]["top_settlement_count"], 2)
        self.assertEqual(check["evidence"]["water_accessible_top_settlement_count"], 1)
        self.assertEqual(check["evidence"]["mean_top_settlement_score"], 0.85)
        self.assertEqual(world["summary"]["large_settlement_water_access_index"], 0.5)
        self.assertEqual(world["summary"]["worldbuilding_realism_pass_count"], 4)
        self.assertEqual(world["summary"]["worldbuilding_realism_pass_fraction"], 0.8)
        self.assertEqual(world["summary"]["mean_worldbuilding_realism_score"], 0.917647)

    def test_every_water_access_signal_satisfies_the_claim(self) -> None:
        cases = (
            ("river", {"is_river": True}, [], 1.0),
            ("lake", {"is_lake": True}, [], 1.0),
            ("fresh_lake_body", {"water_body_type": "fresh_lake"}, [], 1.0),
            ("saline_basin_body", {"water_body_type": "saline_basin"}, [], 1.0),
            ("marine_body", {"water_body_type": "ocean"}, [], 1.0),
            ("runoff_at_threshold", {"runoff_mm_y": 120.0}, [], 1.0),
            ("adjacent_marine_cell", {}, [1], 1.0),
            ("dry_inland", {}, [], 0.0),
            ("runoff_below_threshold", {"runoff_mm_y": 119.0}, [], 0.0),
        )
        for label, fields, neighbors, expected in cases:
            with self.subTest(case=label):
                world = realism_world(
                    cells=[
                        realism_cell(0, neighbors, **fields),
                        realism_cell(1, [0], water_body_type="continental_shelf"),
                    ],
                    settlements=[{"id": 0, "cell_id": 0, "score": 0.9}],
                )
                enrich_world_with_worldbuilding_realism(world)
                check = check_by_name(world, "large_settlement_water_access")
                self.assertEqual(check["value"], expected)
                self.assertIs(check["passed"], expected == 1.0)

    def test_settlement_on_an_absent_cell_has_no_water_access(self) -> None:
        """The lookup falls back to an empty cell, which has no water signal.

        The only cell in the world is a river cell, so the control passes; the
        settlement's cell id is the single difference between the two worlds.
        """

        def build(cell_id: int) -> dict[str, Any]:
            return realism_world(
                cells=[realism_cell(0, [], is_river=True)],
                settlements=[{"id": 0, "cell_id": cell_id, "score": 1.0}],
            )

        control = build(0)
        enrich_world_with_worldbuilding_realism(control)
        control_check = check_by_name(control, "large_settlement_water_access")
        self.assertEqual(control_check["value"], 1.0)
        self.assertTrue(control_check["passed"])

        world = build(404)
        enrich_world_with_worldbuilding_realism(world)
        check = check_by_name(world, "large_settlement_water_access")
        self.assertEqual(check["value"], 0.0)
        self.assertEqual(check["score"], 0.0)
        self.assertFalse(check["passed"])
        self.assertEqual(check["evidence"]["top_settlement_count"], 1)
        self.assertEqual(check["evidence"]["water_accessible_top_settlement_count"], 0)

    def test_route_friction_thresholds_are_route_type_specific(self) -> None:
        thresholds = {
            "coastal_sea": 0.95,
            "river_corridor": 1.10,
            "mountain_pass": 1.75,
            "overland": 1.35,
        }
        for route_type, threshold in thresholds.items():
            for label, friction, expected_low in (
                ("below", threshold - 0.05, 1),
                ("above", threshold + 0.05, 0),
            ):
                with self.subTest(route_type=route_type, side=label):
                    world = realism_world(
                        routes=[
                            {
                                "id": 0,
                                "from": 0,
                                "to": 1,
                                "type": route_type,
                                "distance_km": 100.0,
                                "cost": friction * 100.0,
                            }
                        ]
                    )
                    enrich_world_with_worldbuilding_realism(world)
                    check = check_by_name(world, "route_barrier_avoidance")
                    self.assertEqual(check["evidence"]["route_count"], 1)
                    self.assertEqual(
                        check["evidence"]["low_barrier_route_count"], expected_low
                    )
                    self.assertEqual(check["value"], float(expected_low))
                    self.assertIs(check["passed"], expected_low == 1)
                    self.assertEqual(
                        check["evidence"]["high_cost_route_count"],
                        1 if friction > 1.55 else 0,
                    )
                    self.assertAlmostEqual(
                        check["evidence"]["mean_route_friction"], friction, places=6
                    )

    def test_zero_distance_route_uses_a_one_kilometre_floor(self) -> None:
        world = realism_world(
            routes=[{"id": 0, "from": 0, "to": 1, "type": "overland", "distance_km": 0.0, "cost": 2.0}]
        )
        enrich_world_with_worldbuilding_realism(world)
        check = check_by_name(world, "route_barrier_avoidance")
        self.assertEqual(check["evidence"]["max_route_friction"], 2.0)
        self.assertEqual(check["evidence"]["low_barrier_route_count"], 0)
        self.assertEqual(check["value"], 0.0)
        self.assertEqual(check["score"], 0.0)

    def test_political_connectivity_falls_back_and_fails_on_isolated_settlements(self) -> None:
        connected = realism_world(
            political_regions=[
                {"id": 0, "capital_settlement_id": 0, "settlement_ids": [0, 1, 2]}
            ],
            routes=[
                {"id": 0, "from": 0, "to": 1, "type": "overland", "distance_km": 100.0, "cost": 10.0},
                {"id": 1, "from": 1, "to": 2, "type": "overland", "distance_km": 100.0, "cost": 10.0},
            ],
        )
        enrich_world_with_worldbuilding_realism(connected)
        check = check_by_name(connected, "political_region_connectivity")
        self.assertEqual(check["value"], 1.0)
        self.assertTrue(check["passed"])
        self.assertEqual(check["evidence"]["connected_region_count"], 1)
        self.assertEqual(check["evidence"]["capital_reachable_settlement_count"], 3)

        # No routes at all, and a capital that is not one of the region's members.
        isolated = realism_world(
            political_regions=[
                {"id": 0, "capital_settlement_id": 99, "settlement_ids": [0, 1, 2]}
            ],
            routes=[{"id": 0, "from": -1, "to": 1, "type": "overland", "distance_km": 100.0, "cost": 10.0}],
        )
        enrich_world_with_worldbuilding_realism(isolated)
        check = check_by_name(isolated, "political_region_connectivity")
        self.assertEqual(check["value"], 0.333333)
        self.assertFalse(check["passed"])
        self.assertEqual(check["score"], 0.60606)
        self.assertEqual(check["evidence"]["connected_region_count"], 0)
        self.assertEqual(check["evidence"]["region_settlement_count"], 3)
        self.assertEqual(check["evidence"]["capital_reachable_settlement_count"], 1)
        self.assertEqual(check["evidence"]["mean_region_capital_reachability"], 0.333333)
        self.assertEqual(isolated["summary"]["political_region_connectivity_index"], 0.333333)

    def test_capital_outside_its_region_falls_back_to_a_member_settlement(self) -> None:
        """The fallback is only visible when the members are actually routed.

        With every member reachable from settlement 0, keeping the unusable
        capital 99 as the traversal root would strand it on its own and score
        1/3; the fallback is what makes both capitals score the same 3/3.
        """

        def build(capital_id: int) -> dict[str, Any]:
            return realism_world(
                political_regions=[
                    {
                        "id": 0,
                        "capital_settlement_id": capital_id,
                        "settlement_ids": [0, 1, 2],
                    }
                ],
                routes=[
                    {"id": 0, "from": 0, "to": 1, "type": "overland", "distance_km": 100.0, "cost": 10.0},
                    {"id": 1, "from": 1, "to": 2, "type": "overland", "distance_km": 100.0, "cost": 10.0},
                ],
            )

        for label, capital_id in (("member_capital", 0), ("absent_capital", 99)):
            with self.subTest(case=label):
                world = build(capital_id)
                enrich_world_with_worldbuilding_realism(world)
                check = check_by_name(world, "political_region_connectivity")
                self.assertEqual(check["value"], 1.0)
                self.assertTrue(check["passed"])
                self.assertEqual(check["evidence"]["capital_reachable_settlement_count"], 3)
                self.assertEqual(check["evidence"]["region_settlement_count"], 3)
                self.assertEqual(check["evidence"]["connected_region_count"], 1)

    def test_region_without_settlements_counts_as_connected(self) -> None:
        world = realism_world(
            political_regions=[{"id": 0, "capital_settlement_id": -1, "settlement_ids": []}]
        )
        enrich_world_with_worldbuilding_realism(world)
        check = check_by_name(world, "political_region_connectivity")
        self.assertEqual(check["value"], 1.0)
        self.assertTrue(check["passed"])
        self.assertEqual(check["evidence"]["political_region_count"], 1)
        self.assertEqual(check["evidence"]["connected_region_count"], 1)
        self.assertEqual(check["evidence"]["region_settlement_count"], 0)
        self.assertEqual(check["evidence"]["mean_region_capital_reachability"], 1.0)

    def test_natural_border_alignment_is_length_weighted(self) -> None:
        def build(open_length: float) -> dict[str, Any]:
            return realism_world(
                borders=[
                    {"id": 0, "type": "mountain", "barrier_score": 0.1, "length_km": 100.0},
                    {"id": 1, "type": "open_lowland", "barrier_score": 0.5, "length_km": 100.0},
                    {"id": 2, "type": "open_lowland", "barrier_score": 0.1, "length_km": open_length},
                ]
            )

        control = build(300.0)
        enrich_world_with_worldbuilding_realism(control)
        check = check_by_name(control, "natural_border_alignment")
        self.assertEqual(check["value"], 0.4)
        self.assertTrue(check["passed"])
        self.assertEqual(check["score"], 1.0)
        self.assertEqual(check["evidence"]["natural_border_segment_count"], 2)
        self.assertEqual(check["evidence"]["border_total_length_km"], 500.0)
        self.assertEqual(check["evidence"]["natural_border_length_km"], 200.0)
        self.assertAlmostEqual(check["evidence"]["mean_border_barrier_score"], 0.233333, places=6)

        world = build(400.0)
        enrich_world_with_worldbuilding_realism(world)
        check = check_by_name(world, "natural_border_alignment")
        self.assertEqual(check["value"], 0.333333)
        self.assertFalse(check["passed"])
        self.assertEqual(check["score"], 0.833332)
        self.assertEqual(check["evidence"]["border_segment_count"], 3)
        self.assertEqual(world["summary"]["natural_border_alignment_index"], 0.333333)

    def test_zero_length_borders_score_vacuously(self) -> None:
        world = realism_world(
            borders=[
                {"id": 0, "type": "open_lowland", "barrier_score": 0.0, "length_km": 0.0},
                {"id": 1, "type": "open_lowland", "barrier_score": 0.0, "length_km": -5.0},
            ]
        )
        enrich_world_with_worldbuilding_realism(world)
        check = check_by_name(world, "natural_border_alignment")
        self.assertEqual(check["evidence"]["border_segment_count"], 2)
        self.assertEqual(check["evidence"]["border_total_length_km"], 0.0)
        self.assertEqual(check["evidence"]["natural_border_segment_count"], 0)
        self.assertEqual(check["value"], 1.0)
        self.assertTrue(check["passed"])

    def test_resource_geology_support_is_resource_specific(self) -> None:
        cases = (
            ("volcanic_arc_metals", "host_crust", {}, {"host_crust_type": "volcanic_arc"}, True),
            ("volcanic_arc_metals", "landform", {}, {"landform": "volcanic_arc"}, True),
            (
                "volcanic_arc_metals",
                "convergence_evidence",
                {},
                {"formation_evidence": {"boundary_convergent": 0.28}},
                True,
            ),
            (
                "volcanic_arc_metals",
                "unusable_evidence_falls_back_to_cell",
                {"boundary_convergent": 0.4},
                {"formation_evidence": "not-a-mapping"},
                True,
            ),
            ("volcanic_arc_metals", "unsupported", {}, {}, False),
            ("craton_iron_gold", "host_crust", {}, {"host_crust_type": "craton"}, True),
            (
                "craton_iron_gold",
                "old_crust",
                {},
                {"formation_evidence": {"crust_age_ma": 1800.0}},
                True,
            ),
            ("craton_iron_gold", "unsupported", {}, {}, False),
            ("sedimentary_fuels", "lithology", {}, {"host_lithology": "shale"}, True),
            (
                "sedimentary_fuels",
                "sediment_thickness",
                {},
                {"formation_evidence": {"sediment_thickness_m": 1.0}},
                True,
            ),
            ("sedimentary_fuels", "basin_landform", {}, {"landform": "foreland_basin"}, True),
            ("sedimentary_fuels", "unsupported", {}, {}, False),
            ("evaporites", "salt_flat", {}, {"landform": "salt_flat"}, True),
            (
                "evaporites",
                "salinity",
                {},
                {"formation_evidence": {"salinity_index": 0.45}},
                True,
            ),
            ("evaporites", "saline_basin_cell", {"water_body_type": "saline_basin"}, {}, True),
            ("evaporites", "unsupported", {}, {}, False),
            ("placer_metals", "river_cell", {"is_river": True}, {}, True),
            (
                "placer_metals",
                "flow_accumulation",
                {},
                {"formation_evidence": {"flow_accumulation": 25.0}},
                True,
            ),
            (
                "placer_metals",
                "convergence",
                {},
                {"formation_evidence": {"boundary_convergent": 0.16}},
                True,
            ),
            ("placer_metals", "unsupported", {}, {}, False),
            (
                "geothermal",
                "divergence",
                {},
                {"formation_evidence": {"boundary_divergent": 0.30}},
                True,
            ),
            (
                "geothermal",
                "convergence",
                {},
                {"formation_evidence": {"boundary_convergent": 0.20}},
                True,
            ),
            ("geothermal", "rift_landform", {}, {"landform": "rift_valley"}, True),
            ("geothermal", "rift_crust", {}, {"host_crust_type": "rift_basin"}, True),
            ("geothermal", "unsupported", {}, {}, False),
            ("fertile_alluvium", "delta_landform", {}, {"landform": "delta"}, True),
            ("fertile_alluvium", "river_cell", {"is_river": True}, {}, True),
            (
                "fertile_alluvium",
                "fertility",
                {},
                {"formation_evidence": {"fertility": 0.62}},
                True,
            ),
            ("fertile_alluvium", "unsupported", {}, {}, False),
            ("coastal_fisheries", "marine_cell", {"water_body_type": "ocean"}, {}, True),
            ("coastal_fisheries", "land_cell", {}, {}, False),
            ("timber", "confidence_fallback", {}, {"geologic_confidence_index": 0.25}, True),
            ("timber", "low_confidence", {}, {"geologic_confidence_index": 0.24}, False),
        )
        for resource, label, cell_fields, deposit_fields, supported in cases:
            with self.subTest(resource=resource, case=label):
                deposit: dict[str, Any] = {"id": 0, "cell_id": 0, "resource": resource}
                deposit.update(deposit_fields)
                world = realism_world(
                    cells=[realism_cell(0, [], **cell_fields)],
                    resource_deposits=[deposit],
                )
                enrich_world_with_worldbuilding_realism(world)
                check = check_by_name(world, "resource_geology_dependency")
                self.assertEqual(check["evidence"]["resource_deposit_count"], 1)
                self.assertEqual(check["evidence"]["resource_counts"], {resource: 1})
                self.assertEqual(check["value"], 1.0 if supported else 0.0)
                self.assertIs(check["passed"], supported)
                self.assertEqual(
                    check["evidence"]["geologically_supported_resource_deposit_count"],
                    1 if supported else 0,
                )
                self.assertEqual(
                    check["evidence"]["supported_resource_counts"],
                    {resource: 1} if supported else {},
                )

    def test_deposit_on_an_absent_cell_is_never_supported(self) -> None:
        control = realism_world(
            resource_deposits=[
                {"id": 0, "cell_id": 0, "resource": "placer_metals", "formation_evidence": {"flow_accumulation": 40.0}}
            ]
        )
        enrich_world_with_worldbuilding_realism(control)
        self.assertEqual(check_by_name(control, "resource_geology_dependency")["value"], 1.0)

        world = realism_world(
            resource_deposits=[
                {"id": 0, "cell_id": 404, "resource": "placer_metals", "formation_evidence": {"flow_accumulation": 40.0}}
            ]
        )
        enrich_world_with_worldbuilding_realism(world)
        check = check_by_name(world, "resource_geology_dependency")
        self.assertEqual(check["value"], 0.0)
        self.assertFalse(check["passed"])
        self.assertEqual(check["evidence"]["resource_counts"], {"placer_metals": 1})
        self.assertEqual(check["evidence"]["supported_resource_counts"], {})

    def test_generated_world_control_is_clean(self) -> None:
        world = worlds.cached_world("replay_128")
        before = [dict(check) for check in world["worldbuilding_realism_checks"]]
        enrich_world_with_worldbuilding_realism(world)
        self.assertEqual(world["worldbuilding_realism_checks"], before)
        self.assertEqual(len(before), 5)
        self.assertEqual(
            world["summary"]["worldbuilding_realism_check_count"], len(before)
        )
        self.assertEqual(
            world["summary"]["worldbuilding_realism_pass_count"],
            sum(1 for check in before if check["passed"]),
        )
