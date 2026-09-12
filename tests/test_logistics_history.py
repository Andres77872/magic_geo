"""Degenerate-input coverage of the logistics/campaign enricher and its replay validator.

``magic_geo.logistics_history.enrich_world_with_logistics_history`` builds the
logistics networks, market exchanges, campaign movements, path segments, front
histories, tactical engagements and strategic plans of a world.
``magic_geo.campaign_operations_validation.validate_campaign_operations_replay``
is a *second, independent copy* of the campaign half of that model: it recomputes
every campaign record from the same inputs and reports
``"campaign operations model or causal replay invalid"`` when a stored record
disagrees.

That duality drives the two kinds of test here:

* **input tampers** (``SyntheticCampaignWorldTests``,
  ``GeneratedCampaignWorldTests``) change an *input* — a route type, a
  settlement cell, a conflict outcome, a record id — then re-run the enricher
  and assert the specific record it now produces. Every one of those tests also
  asserts the validator replays the re-enriched world cleanly, which is the only
  thing that can catch the two copies drifting apart on a degenerate input;
* **stored-output tampers and malformed payloads**
  (``CampaignOperationsReplayValidationTests``) leave the inputs alone and
  assert the validator reports rather than accepts — or, for a malformed
  payload, reports rather than raises.

The validator emits a single message for every failure, so a stored-output
tamper cannot be identified by its message. Those tests therefore pin the
*input* they tampered instead, and each one starts from a control that replays
cleanly, so a green result cannot come from a broken fixture.

The generated world is ``mid_512`` rather than the usual ``replay_128``
because ``replay_128`` and ``small_smoke`` each have a single political region
and therefore no conflict, campaign, path or front. ``mid_512`` has two regions,
and its one exhaustion conflict runs region 0 (the stronger attacker) against
region 1. Its campaign advances across multiple cells and border segments.

Tampers already covered elsewhere are deliberately absent: the campaign path
segment / front step / tactical step / strategic plan / model-descriptor
mutations live in ``test_smoke_society_economy`` (through the CLI), and the
missing ``planet_parameters`` rejection lives in ``test_planet_scaling``.
"""

from __future__ import annotations

import copy
from typing import Any
from unittest import TestCase

from support import worlds

from magic_geo.campaign_operations_validation import (
    CAMPAIGN_OPERATIONS_MODEL,
    validate_campaign_operations_replay,
)
from magic_geo.logistics_history import (
    LOGISTICS_EXCHANGE_MODEL,
    enrich_world_with_logistics_history,
)

#: Two regions, one exhaustion conflict, and a campaign led by region 0.
CAMPAIGN_WORLD = "mid_512"

#: The smallest canonical world of all: one region, so no conflicts.
QUIET_WORLD = "replay_128"

FAILURE = ["campaign operations model or causal replay invalid"]

#: Every list of campaign records the enricher writes.
CAMPAIGN_FAMILIES = (
    "campaign_movements",
    "campaign_path_segments",
    "campaign_front_histories",
    "tactical_engagements",
    "strategic_campaign_plans",
)

LINEAR_CELL_COUNT = 6


def _linear_campaign_world(route_type: str = "overland") -> dict[str, Any]:
    """A hand-built world whose cell graph is a straight six-cell chain.

    Cell ``i`` sits at longitude ``i`` degrees on the equator and neighbours
    only ``i - 1`` and ``i + 1``, so every campaign path through it is forced
    and can be written down exactly. Cells 0-1 belong to political region 0,
    cells 4-5 to region 1 and cells 2-3 to neither. Region 0 holds settlement 0
    on cell 0 (its capital), region 1 holds settlement 1 on cell 5 (its
    capital), and the single conflict runs region 0 against region 1 with the
    contested cell on 5.

    The cells are deliberately flat, dry and ice-free so that
    ``terrain_cost_index`` reduces to the constant 0.18 base plus whatever the
    route mode contributes — see
    :meth:`SyntheticCampaignWorldTests.test_river_route_mode_discounts_water_and_river_cells`.

    There are no economy histories, so the origin region has zero army capacity;
    that is asserted rather than worked around.
    """

    cells = [
        {
            "id": index,
            "lat_deg": 0.0,
            "lon_deg": float(index),
            "neighbors": [
                neighbor
                for neighbor in (index - 1, index + 1)
                if 0 <= neighbor < LINEAR_CELL_COUNT
            ],
            "political_region_id": 0 if index < 2 else (1 if index > 3 else -1),
            "is_water": False,
            "is_river": False,
            "elevation_m": 0.0,
            "seasonal_aridity_index": 0.0,
            "ice_thickness_m": 0.0,
            "landform": "plain",
            "biome": "grassland",
        }
        for index in range(LINEAR_CELL_COUNT)
    ]
    return {
        "political_regions": [
            {"id": 0, "capital_settlement_id": 0},
            {"id": 1, "capital_settlement_id": 1},
        ],
        "settlements": [
            {"id": 0, "cell_id": 0, "region_id": 0},
            {"id": 1, "cell_id": 5, "region_id": 1},
        ],
        "routes": [
            {
                "id": 0,
                "from": 0,
                "to": 1,
                "type": route_type,
                "distance_km": 560.0,
                "cost": 700.0,
            }
        ],
        "trade_flows": [
            {
                "id": 0,
                "route_id": 0,
                "from": 0,
                "to": 1,
                "region_from": 0,
                "region_to": 1,
                "distance_km": 560.0,
                "volume_index": 20.0,
                "friction": 0.2,
                "interregional": True,
            }
        ],
        "conflicts": [
            {
                "id": 0,
                "region_a": 0,
                "region_b": 1,
                "region_a_force_estimate": 12000.0,
                "region_b_force_estimate": 9000.0,
                "outcome": "exhaustion",
                "contested_cell_id": 5,
                "intensity": 0.4,
                "war_duration_years": 2.0,
            }
        ],
        "cells": cells,
        "borders": [
            {
                "id": 0,
                "region_a": 0,
                "region_b": 1,
                "barrier_score": 0.3,
                "length_km": 300.0,
            }
        ],
        "economy_histories": [],
        "summary": {},
        "planet_parameters": {"radius_km": 6371.0},
    }


class _TamperMixin:
    """Shared helpers that make a silently inert tamper impossible."""

    def _tamper(self, mapping: dict[str, Any], key: str, value: Any) -> None:
        """Overwrite ``mapping[key]``, proving the write changes something."""

        self.assertIn(key, mapping)
        self.assertNotEqual(
            mapping[key], value, f"tamper for {key!r} did not change the payload"
        )
        mapping[key] = value

    def _enriched(self, world: dict[str, Any]) -> dict[str, Any]:
        """Run the enricher and assert the validator accepts what it wrote.

        The validator is a second implementation of the same campaign model, so
        a clean replay of a re-enriched world is the assertion that the two
        copies still agree about this input — including the degenerate inputs
        the generated worlds never produce.
        """

        enriched = enrich_world_with_logistics_history(world)
        self.assertEqual(validate_campaign_operations_replay(enriched), [])
        return enriched

    def _only_movement(self, world: dict[str, Any]) -> dict[str, Any]:
        """The single campaign movement of a one-conflict world."""

        movements = world["campaign_movements"]
        self.assertEqual(len(movements), 1)
        return movements[0]


class SyntheticCampaignWorldTests(_TamperMixin, TestCase):
    """Endpoint selection, path search and terrain costing on a known graph."""

    def _world_without_preferred_targets(self) -> dict[str, Any]:
        """The linear world with every named target endpoint removed.

        The endpoint election prefers, in order: the contested cell, a
        target-region neighbour of the origin, the route's target-region
        settlement and the target region's capital. Cell 0 has no region-1
        neighbour, so removing the other three leaves nothing to elect and the
        geometric fallbacks take over.
        """

        world = _linear_campaign_world()
        self._tamper(world["routes"][0], "to", 0)
        self._tamper(world["political_regions"][1], "capital_settlement_id", -1)
        self._tamper(world["conflicts"][0], "contested_cell_id", -1)
        return world

    def test_linear_world_enriches_and_replays_cleanly(self) -> None:
        """The control every other case in this class is a departure from."""

        world = self._enriched(_linear_campaign_world())

        movement = self._only_movement(world)
        self.assertEqual(movement["origin_region_id"], 0)
        self.assertEqual(movement["target_region_id"], 1)
        self.assertEqual(movement["origin_cell_id"], 0)
        # The contested cell belongs to the target region, so it wins the
        # endpoint election ahead of every fallback.
        self.assertEqual(movement["target_cell_id"], 5)
        self.assertEqual(movement["path_cell_ids"], [0, 1, 2, 3, 4, 5])
        self.assertEqual(movement["path_segment_count"], 5)
        self.assertEqual(movement["route_id"], 0)
        self.assertEqual(movement["border_id"], 0)

        segments = world["campaign_path_segments"]
        self.assertEqual([segment["route_mode"] for segment in segments], ["overland"] * 5)
        # 0.18 base cost, minus the 0.04 dry-overland discount, on every hop:
        # flat, dry, ice-free cells contribute nothing else.
        self.assertEqual([segment["terrain_cost_index"] for segment in segments], [0.14] * 5)

        # No economy history means no army capacity at all, which saturates the
        # supply requirement rather than dividing by zero.
        self.assertEqual(world["logistics_networks"][0]["army_capacity_population"], 0.0)
        self.assertEqual(movement["supply_required_index"], 1.0)

        self.assertEqual(len(world["campaign_front_histories"][0]["steps"]), 6)
        self.assertEqual(world["tactical_engagements"][0]["step_count"], 6)
        self.assertEqual(world["strategic_campaign_plans"][0]["decisive_cell_ids"], [0, 3, 5])

    def test_neighbour_id_off_the_mesh_is_skipped_by_the_path_search(self) -> None:
        """A dangling neighbour id is stepped over, not followed and not fatal.

        The dangling id comes *first* in the list on purpose: a search that
        stopped at it, rather than skipping it and reading on, would never
        expand cells 2..5 through cell 1. The second half of the test takes the
        real neighbours away as well, which pins what the dangling id is worth
        on its own — nothing.
        """

        world = _linear_campaign_world()
        self._tamper(world["cells"][1], "neighbors", [99, 0, 2])

        world = self._enriched(world)

        movement = self._only_movement(world)
        self.assertEqual(movement["path_cell_ids"], [0, 1, 2, 3, 4, 5])
        self.assertNotIn(99, movement["path_cell_ids"])
        # Skipped by the search, not scrubbed out of the input.
        self.assertEqual(world["cells"][1]["neighbors"], [99, 0, 2])

        stranded = _linear_campaign_world()
        self._tamper(stranded["cells"][1], "neighbors", [99])

        stranded_movement = self._only_movement(self._enriched(stranded))

        # Cell 1 now has nowhere to go, so the target on cell 5 is unreachable
        # and the campaign collapses onto the single-step fallback — where the
        # same world with 99 *plus* the real neighbours walks the whole chain.
        self.assertEqual(stranded_movement["path_cell_ids"], [0, 1])
        self.assertEqual(stranded_movement["target_cell_id"], 1)

    def test_unreachable_target_falls_back_to_a_single_neighbour_step(self) -> None:
        """When no path exists the campaign becomes one step into a neighbour."""

        world = _linear_campaign_world()
        # Cut the chain between cells 2 and 3: cell 5 is still elected as the
        # target, but Dijkstra can no longer reach it from cell 0.
        self._tamper(world["cells"][2], "neighbors", [1])
        self._tamper(world["cells"][3], "neighbors", [4])

        world = self._enriched(world)

        movement = self._only_movement(world)
        self.assertEqual(movement["target_cell_id"], 1)
        self.assertEqual(movement["path_cell_ids"], [0, 1])
        self.assertEqual(movement["path_cell_count"], 2)
        self.assertEqual(len(world["campaign_path_segments"]), 1)

    def test_campaign_without_preferred_target_uses_nearest_target_region_cell(
        self,
    ) -> None:
        """With every named target gone the nearest target-region cell wins."""

        world = self._world_without_preferred_targets()

        movement = self._only_movement(self._enriched(world))

        # Cells 4 and 5 are the only region-1 cells; cell 4 is the closer of the
        # two to the origin on cell 0, so the geometric fallback picks it over
        # the cell 5 the control elects from the contested cell.
        self.assertEqual(movement["target_cell_id"], 4)
        self.assertEqual(movement["path_cell_ids"], [0, 1, 2, 3, 4])

    def test_target_region_neighbour_outranks_the_nearest_cell_fallback(self) -> None:
        """A target-region neighbour of the origin is elected before geometry."""

        world = self._world_without_preferred_targets()
        # Cell 1 neighbours the origin on cell 0. Cells 4 and 5 stay in region 1,
        # so the geometric fallback is still available and would elect cell 4 —
        # which is what test_campaign_without_preferred_target_uses_nearest_
        # target_region_cell pins for this same world.
        self._tamper(world["cells"][1], "political_region_id", 1)

        movement = self._only_movement(self._enriched(world))

        self.assertEqual(movement["target_cell_id"], 1)
        self.assertEqual(movement["path_cell_ids"], [0, 1])

    def test_campaign_without_any_target_region_cell_uses_a_start_neighbour(
        self,
    ) -> None:
        """With no target-region cell left, a neighbour of the origin is used."""

        world = self._world_without_preferred_targets()
        for cell in world["cells"][4:]:
            self._tamper(cell, "political_region_id", -1)

        world = self._enriched(world)

        movement = self._only_movement(world)
        self.assertEqual(movement["target_cell_id"], 1)
        self.assertEqual(movement["path_cell_ids"], [0, 1])
        self.assertEqual(world["campaign_front_histories"][0]["step_count"], 2)

    def test_malformed_cell_political_region_id_reads_as_unassigned(self) -> None:
        """A non-integer ``political_region_id`` drops the cell from its region."""

        # The same world, untampered: the nearest region-1 cell to the origin
        # is cell 4. Every case below differs from this one by the single write
        # that makes cell 4 unreadable, so a target of 5 can only come from
        # cell 4 having dropped out of region 1.
        baseline = self._only_movement(
            self._enriched(self._world_without_preferred_targets())
        )
        self.assertEqual(baseline["target_cell_id"], 4)

        for malformed in ("north", None, [1]):
            with self.subTest(political_region_id=malformed):
                world = self._world_without_preferred_targets()
                self.assertEqual(world["cells"][4]["political_region_id"], 1)
                self._tamper(world["cells"][4], "political_region_id", malformed)

                world = self._enriched(world)

                movement = self._only_movement(world)
                self.assertEqual(movement["target_cell_id"], 5)
                self.assertEqual(movement["path_cell_ids"], [0, 1, 2, 3, 4, 5])
                # Read as unassigned, not rewritten: the malformed value is
                # still on the cell the campaign walked straight through.
                self.assertEqual(world["cells"][4]["political_region_id"], malformed)

    def test_river_route_mode_discounts_water_and_river_cells(self) -> None:
        """Route mode changes what water costs the campaign, cell by cell.

        The first hop enters a cell that is both water and river, the second a
        cell that is only water. ``river`` and ``coastal_sea`` agree on the
        first hop by coincidence — 0.18 + 0.28 - 0.10 == 0.18 + 0.18 — so the
        second hop is what actually separates the river water cost from the
        coastal one.
        """

        for route_type, expected in (
            ("river", [0.36, 0.46]),
            ("river_corridor", [0.36, 0.46]),
            ("coastal_sea", [0.36, 0.36]),
            ("border_crossing", [0.8, 0.8]),
            ("overland", [0.8, 0.8]),
        ):
            with self.subTest(route_type=route_type):
                world = _linear_campaign_world(route_type=route_type)
                self.assertEqual(world["routes"][0]["type"], route_type)
                self._tamper(world["cells"][1], "is_water", True)
                self._tamper(world["cells"][1], "is_river", True)
                self._tamper(world["cells"][2], "is_water", True)

                world = self._enriched(world)

                segments = world["campaign_path_segments"]
                self.assertEqual(
                    [segment["terrain_cost_index"] for segment in segments[:2]], expected
                )
                self.assertEqual(segments[0]["route_mode"], route_type)
                self.assertTrue(segments[0]["water_crossing"])

    def test_world_without_routes_starts_the_campaign_at_the_region_capital(
        self,
    ) -> None:
        """No route means no route endpoint, so the capital cell is the origin."""

        world = _linear_campaign_world()
        self.assertTrue(world["routes"])
        self.assertTrue(world["trade_flows"])
        world["routes"] = []
        world["trade_flows"] = []

        world = self._enriched(world)

        network = world["logistics_networks"][0]
        self.assertEqual(network["route_count"], 0)
        self.assertEqual(network["total_route_distance_km"], 0.0)
        self.assertEqual(network["transport_efficiency_index"], 0.0)

        movement = self._only_movement(world)
        self.assertEqual(movement["route_id"], -1)
        # Settlement 0 is region 0's capital and sits on cell 0.
        self.assertEqual(movement["origin_cell_id"], 0)
        self.assertEqual(movement["target_cell_id"], 5)
        # Without a trade flow the route mode falls back to the border crossing,
        # which forfeits the dry-overland discount of the control.
        self.assertEqual(world["campaign_path_segments"][0]["route_mode"], "border_crossing")
        self.assertEqual(world["campaign_path_segments"][0]["terrain_cost_index"], 0.18)


class GeneratedCampaignWorldTests(_TamperMixin, TestCase):
    """Scoped campaign-stage input mutations from a genuine generated world."""

    control: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        """A re-enriched copy of the campaign world. Read-only: never mutated."""

        cls.control = enrich_world_with_logistics_history(
            worlds.cached_world(CAMPAIGN_WORLD)
        )

    def _world(self) -> dict[str, Any]:
        return worlds.cached_world(CAMPAIGN_WORLD)

    def _networks_by_region(self, world: dict[str, Any]) -> dict[int, dict[str, Any]]:
        return {network["region_id"]: network for network in world["logistics_networks"]}

    def test_re_enriching_the_generated_world_reproduces_every_record(self) -> None:
        """The control: enrichment is a pure function of the world's inputs."""

        world = self._world()
        stored = {family: copy.deepcopy(world[family]) for family in CAMPAIGN_FAMILIES}
        stored["logistics_networks"] = copy.deepcopy(world["logistics_networks"])

        world = self._enriched(world)

        for family, records in stored.items():
            with self.subTest(family=family):
                self.assertEqual(world[family], records)
        self.assertTrue(world["campaign_movements"])
        self.assertEqual(world["summary"]["campaign_operations_model"], CAMPAIGN_OPERATIONS_MODEL)
        self.assertEqual(world["summary"]["logistics_exchange_model"], LOGISTICS_EXCHANGE_MODEL)

        movement = self._only_movement(world)
        self.assertEqual(movement["origin_region_id"], 0)
        self.assertEqual(movement["target_region_id"], 1)

    def test_region_b_victory_reverses_the_campaign_axis(self) -> None:
        """A victorious region B attacks, and every per-region field swaps."""

        world = self._world()
        self._tamper(world["conflicts"][0], "outcome", "region_b_victory")

        world = self._enriched(world)

        movement = self._only_movement(world)
        self.assertEqual(movement["origin_region_id"], 1)
        self.assertEqual(movement["target_region_id"], 0)
        self.assertEqual(
            movement["force_estimate"],
            round(world["conflicts"][0]["region_b_force_estimate"], 6),
        )

        # Region A is now the defender: its tactical force reads the defending
        # column of the front step, and the attacker's supply integrity is
        # reported for region B. The control asserts the mirror image below.
        front_step = world["campaign_front_histories"][0]["steps"][0]
        tactical_step = world["tactical_engagements"][0]["steps"][0]
        self.assertEqual(
            tactical_step["region_a_force_estimate"], front_step["defending_force_estimate"]
        )
        self.assertEqual(
            tactical_step["region_b_force_estimate"], front_step["attacking_force_estimate"]
        )
        self.assertEqual(
            tactical_step["region_b_supply_integrity_index"],
            front_step["supply_integrity_index"],
        )

        control_front_step = self.control["campaign_front_histories"][0]["steps"][0]
        control_tactical_step = self.control["tactical_engagements"][0]["steps"][0]
        self.assertEqual(
            control_tactical_step["region_a_force_estimate"],
            control_front_step["attacking_force_estimate"],
        )
        self.assertEqual(
            control_tactical_step["region_a_supply_integrity_index"],
            control_front_step["supply_integrity_index"],
        )

    def test_region_a_victory_keeps_the_axis_and_raises_campaign_success(self) -> None:
        """A decided war raises the success baseline without moving the axis."""

        world = self._world()
        self._tamper(world["conflicts"][0], "outcome", "region_a_victory")

        world = self._enriched(world)

        movement = self._only_movement(world)
        control_movement = self._only_movement(self.control)
        self.assertEqual(movement["outcome"], "region_a_victory")
        # Region A already had the larger force, so only the success baseline
        # (0.70 for a decided war against 0.50 for the control's exhaustion)
        # can have moved.
        self.assertEqual(movement["origin_region_id"], control_movement["origin_region_id"])
        self.assertEqual(movement["path_cell_ids"], control_movement["path_cell_ids"])
        self.assertGreater(
            movement["campaign_success_index"], control_movement["campaign_success_index"]
        )

    def test_stronger_region_b_attacks_when_the_war_ends_without_a_victor(self) -> None:
        """With no victor the larger force is the attacker."""

        world = self._world()
        self._tamper(world["conflicts"][0], "region_b_force_estimate", 60_000_000.0)

        world = self._enriched(world)

        conflict = world["conflicts"][0]
        # Nothing decided this war, so only the force comparison can have
        # flipped the axis.
        self.assertNotIn(conflict["outcome"], {"region_a_victory", "region_b_victory"})
        self.assertGreater(
            conflict["region_b_force_estimate"], conflict["region_a_force_estimate"]
        )
        self.assertEqual(self._only_movement(world)["origin_region_id"], 1)
        self.assertEqual(self._only_movement(self.control)["origin_region_id"], 0)

    def test_conflict_inside_one_region_produces_no_campaign(self) -> None:
        """A conflict whose two sides are the same region is not a campaign."""

        world = self._world()
        self._tamper(world["conflicts"][0], "region_b", world["conflicts"][0]["region_a"])

        world = self._enriched(world)

        for family in CAMPAIGN_FAMILIES:
            with self.subTest(family=family):
                self.assertEqual(world[family], [])
        summary = world["summary"]
        self.assertEqual(summary["campaign_movement_count"], 0)
        self.assertEqual(summary["tactical_engagement_count"], 0)
        self.assertEqual(summary["strategic_campaign_plan_count"], 0)
        self.assertEqual(summary["campaign_front_step_count"], 0)
        self.assertEqual(summary["mean_campaign_travel_time_days"], 0.0)
        self.assertEqual(summary["mean_tactical_front_pressure_index"], 0.0)
        # The logistics half of the enricher is untouched by the conflict.
        self.assertEqual(len(world["logistics_networks"]), 2)
        self.assertEqual(self.control["summary"]["campaign_movement_count"], 1)

    def test_border_folded_into_one_region_drops_out_of_the_pair_map(self) -> None:
        """A border whose two sides are equal cannot be a campaign's border."""

        world = self._world()
        control_border_id = self._only_movement(self.control)["border_id"]
        border = next(
            item for item in world["borders"] if item["id"] == control_border_id
        )
        self._tamper(border, "region_b", border["region_a"])

        world = self._enriched(world)

        movement = self._only_movement(world)
        self.assertNotEqual(movement["border_id"], control_border_id)
        remaining = [
            item
            for item in world["borders"]
            if {item["region_a"], item["region_b"]} == {0, 1}
        ]
        # The campaign uses the least resistant border of the pair, so the
        # replacement must be the lowest barrier score still on offer.
        self.assertEqual(
            movement["border_id"],
            min(remaining, key=lambda item: item["barrier_score"])["id"],
        )

    def test_records_without_an_id_drop_out_of_every_region_network(self) -> None:
        """Route, trade flow and border records need an id to be counted."""

        for family, count_key, ids_key in (
            ("routes", "route_count", "route_ids"),
            ("trade_flows", "trade_flow_count", "trade_flow_ids"),
            ("borders", "border_count", "border_ids"),
        ):
            with self.subTest(family=family):
                world = self._world()
                dropped_id = world[family][0]["id"]
                self._tamper(world[family][0], "id", -1)

                world = self._enriched(world)

                networks = self._networks_by_region(world)
                control_networks = self._networks_by_region(self.control)
                self.assertEqual(sorted(networks), sorted(control_networks))
                for region_id, network in networks.items():
                    expected = [
                        record_id
                        for record_id in control_networks[region_id][ids_key]
                        if record_id != dropped_id
                    ]
                    self.assertEqual(network[ids_key], expected)
                    self.assertEqual(network[count_key], len(expected))

    def test_region_without_an_id_gets_no_logistics_network(self) -> None:
        """An unidentified region is skipped, but conflicts still target it."""

        world = self._world()
        self._tamper(world["political_regions"][1], "id", -1)

        world = self._enriched(world)

        self.assertEqual([network["region_id"] for network in world["logistics_networks"]], [0])
        self.assertEqual(world["summary"]["logistics_network_count"], 1)
        self.assertEqual(len(self.control["logistics_networks"]), 2)
        # The campaign is driven by the conflict, not by the region record, so
        # it still runs against region 1 with no network of its own.
        self.assertEqual(self._only_movement(world)["target_region_id"], 1)

    def test_route_origin_remains_usable_when_capital_cell_is_off_the_mesh(self) -> None:
        """The selected trade-route origin takes precedence over the capital."""

        world = self._world()
        movement = self._only_movement(world)
        region = next(item for item in world["political_regions"] if item["id"] == movement["origin_region_id"])
        capital = next(item for item in world["settlements"] if item["id"] == region["capital_settlement_id"])
        self.assertNotEqual(capital["cell_id"], movement["origin_cell_id"])
        self._tamper(capital, "cell_id", 9999)

        world = self._enriched(world)

        self.assertEqual(self._only_movement(world)["origin_cell_id"], movement["origin_cell_id"])
        self.assertEqual(self._only_movement(world)["path_cell_ids"], movement["path_cell_ids"])

    def test_route_origin_and_capital_off_the_mesh_produce_no_campaign(self) -> None:
        """No origin cell means no path, and a conflict without a path is skipped."""

        world = self._world()
        movement = self._only_movement(world)
        region = next(item for item in world["political_regions"] if item["id"] == movement["origin_region_id"])
        capital = next(item for item in world["settlements"] if item["id"] == region["capital_settlement_id"])
        route = next(item for item in world["routes"] if item["id"] == movement["route_id"])
        origin = next(item for item in world["settlements"]
                      if item["id"] in (route["from"], route["to"])
                      and item["cell_id"] == movement["origin_cell_id"])
        self.assertNotEqual(origin["id"], capital["id"])
        # The current witness uses a noncapital route endpoint. Remove both
        # sources so the producer really reaches its missing-origin branch.
        self._tamper(origin, "cell_id", 9999)
        self._tamper(capital, "cell_id", 9999)

        world = self._enriched(world)

        for family in CAMPAIGN_FAMILIES:
            with self.subTest(family=family):
                self.assertEqual(world[family], [])
        self.assertEqual(world["summary"]["campaign_movement_count"], 0)
        # Limitation, pinned rather than worked around: the enricher writes the
        # campaign ids back onto each conflict but never clears them, so the
        # conflict keeps the annotation of the campaign it no longer has — and
        # the validator, which compares only the annotations it recomputes,
        # accepts the world anyway (asserted by ``_enriched`` above).
        self.assertEqual(world["conflicts"][0]["campaign_movement_id"], 0)

    def test_non_list_political_regions_returns_the_world_untouched(self) -> None:
        """A malformed region list aborts enrichment instead of emptying it."""

        world = self._world()
        stored_networks = copy.deepcopy(world["logistics_networks"])
        stored_movements = copy.deepcopy(world["campaign_movements"])
        world["political_regions"] = {}

        result = enrich_world_with_logistics_history(world)

        self.assertIs(result, world)
        # Recomputing over an empty region mapping would have emptied both
        # lists; they are untouched, so the enricher returned early.
        self.assertEqual(world["logistics_networks"], stored_networks)
        self.assertEqual(world["campaign_movements"], stored_movements)
        self.assertTrue(stored_networks)
        # The model descriptors are stamped before the guard runs.
        self.assertEqual(world["logistics_exchange_model"]["model_type"], LOGISTICS_EXCHANGE_MODEL)
        self.assertEqual(world["campaign_operations_model"]["model_type"], CAMPAIGN_OPERATIONS_MODEL)

    def test_world_without_conflicts_reports_zero_campaign_counters(self) -> None:
        """The one-region world has nothing to fight over, and says so."""

        world = worlds.cached_world(QUIET_WORLD)
        self.assertEqual(world["conflicts"], [])
        stored_networks = copy.deepcopy(world["logistics_networks"])

        world = self._enriched(world)

        for family in CAMPAIGN_FAMILIES:
            with self.subTest(family=family):
                self.assertEqual(world[family], [])
        summary = world["summary"]
        for key in (
            "campaign_movement_count",
            "campaign_path_segment_count",
            "campaign_front_step_count",
            "tactical_engagement_step_count",
            "strategic_decision_point_count",
        ):
            with self.subTest(summary_key=key):
                self.assertEqual(summary[key], 0)
        for key in (
            "mean_campaign_travel_time_days",
            "mean_campaign_path_terrain_cost_index",
            "mean_campaign_front_control_index",
            "mean_tactical_counter_maneuver_index",
            "mean_counter_campaign_viability_index",
        ):
            with self.subTest(summary_key=key):
                self.assertEqual(summary[key], 0.0)
        # The logistics half of the same world is unaffected by the silence.
        self.assertEqual(world["logistics_networks"], stored_networks)
        self.assertTrue(stored_networks)


class CampaignOperationsReplayValidationTests(_TamperMixin, TestCase):
    """What the replay validator rejects, and what it refuses to raise on."""

    def _world(self) -> dict[str, Any]:
        return worlds.cached_world(CAMPAIGN_WORLD)

    def test_generated_world_replays_cleanly(self) -> None:
        """The control every rejection below is measured against."""

        world = self._world()

        self.assertEqual(validate_campaign_operations_replay(world), [])
        self.assertEqual(world["summary"]["campaign_operations_model"], CAMPAIGN_OPERATIONS_MODEL)
        model = world["campaign_operations_model"]
        self.assertEqual(model["model_type"], CAMPAIGN_OPERATIONS_MODEL)
        self.assertIs(model["deterministic"], True)
        self.assertTrue(world["campaign_movements"])

    def test_stored_campaign_movement_tampers_are_reported(self) -> None:
        """A stored movement that no longer follows from the inputs is invalid."""

        for key, value in (
            ("origin_cell_id", 7),
            ("target_cell_id", 7),
            ("path_cell_ids", [0, 1]),
            ("path_segment_count", 99),
            ("travel_time_days", 1.0),
            ("campaign_success_index", 0.5),
            ("outcome", "region_a_victory"),
        ):
            with self.subTest(key=key):
                world = self._world()
                self._tamper(world["campaign_movements"][0], key, value)

                self.assertEqual(validate_campaign_operations_replay(world), FAILURE)

    def test_dropping_the_stored_campaign_movements_is_reported(self) -> None:
        """An emptied record list is a length mismatch, not a vacuous pass."""

        world = self._world()
        self.assertTrue(world["campaign_movements"])
        world["campaign_movements"] = []

        self.assertEqual(validate_campaign_operations_replay(world), FAILURE)

    def test_stored_summary_counter_tamper_is_reported(self) -> None:
        """Every recomputed summary counter is compared, not just the records."""

        for key, value in (
            ("campaign_movement_count", 99),
            ("campaign_front_step_count", 0),
            ("strategic_decision_point_count", 7),
            ("total_campaign_path_length_km", 1.0),
            ("high_attrition_campaign_count", 5),
        ):
            with self.subTest(key=key):
                world = self._world()
                self._tamper(world["summary"], key, value)

                self.assertEqual(validate_campaign_operations_replay(world), FAILURE)

    def test_conflict_annotation_tamper_is_reported(self) -> None:
        """The ids written back onto each conflict are replayed too."""

        for key, value in (
            ("campaign_movement_id", 7),
            ("tactical_engagement_id", 7),
            ("strategic_campaign_plan_id", 7),
        ):
            with self.subTest(key=key):
                world = self._world()
                self._tamper(world["conflicts"][0], key, value)

                self.assertEqual(validate_campaign_operations_replay(world), FAILURE)

    def test_missing_required_list_is_reported(self) -> None:
        """A required record list that is gone is reported, not stepped around."""

        for name in ("routes", "cells", "conflicts", "campaign_movements"):
            with self.subTest(missing=name):
                world = self._world()
                self.assertIsInstance(world[name], list)
                del world[name]

                self.assertEqual(validate_campaign_operations_replay(world), FAILURE)

    def test_malformed_payload_is_reported_rather_than_raised(self) -> None:
        """A payload that makes the recomputation raise comes back as a failure.

        Every one of these keeps all of the payload's top-level record lists —
        that is asserted below — so the validator's "is every required list a
        list" guard cannot be what reports them, unlike
        :meth:`test_missing_required_list_is_reported`. The only remaining way
        out is the exception guard around the recomputation.

        Which exception it swallowed is pinned through the enricher: the two
        modules share the model, so what the enricher raises on a copy of the
        very same payload names what the validator caught. That is also the
        assertion that the enricher is *not* silently tolerating these — it
        raises where the validator reports.
        """

        def non_numeric_conflict_region(world: dict[str, Any]) -> None:
            self._tamper(world["conflicts"][0], "region_a", "north")

        def unusable_neighbour_list(world: dict[str, Any]) -> None:
            origin_cell_id = world["campaign_movements"][0]["origin_cell_id"]
            cell = next(item for item in world["cells"] if item["id"] == origin_cell_id)
            self._tamper(cell, "neighbors", None)

        def non_mapping_political_region(world: dict[str, Any]) -> None:
            self.assertIsInstance(world["political_regions"][0], dict)
            world["political_regions"][0] = "region_zero"

        def non_mapping_cell(world: dict[str, Any]) -> None:
            self.assertIsInstance(world["cells"][0], dict)
            world["cells"][0] = None

        list_keys = sorted(
            key for key, value in self._world().items() if isinstance(value, list)
        )
        self.assertIn("political_regions", list_keys)

        for name, tamper, exception, message in (
            (
                "non-numeric conflict region",
                non_numeric_conflict_region,
                ValueError,
                r"invalid literal for int\(\) with base 10: 'north'",
            ),
            (
                "unusable neighbour list",
                unusable_neighbour_list,
                TypeError,
                r"'NoneType' object is not iterable",
            ),
            (
                "political region that is not a mapping",
                non_mapping_political_region,
                AttributeError,
                r"'str' object has no attribute 'get'",
            ),
            (
                "cell that is not a mapping",
                non_mapping_cell,
                AttributeError,
                r"'NoneType' object has no attribute 'get'",
            ),
        ):
            with self.subTest(payload=name):
                world = self._world()
                tamper(world)
                for key in list_keys:
                    self.assertIsInstance(world.get(key), list, key)

                with self.assertRaisesRegex(exception, message):
                    enrich_world_with_logistics_history(copy.deepcopy(world))

                self.assertEqual(validate_campaign_operations_replay(world), FAILURE)
