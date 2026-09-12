"""Causal-replay validation for the human-geography models.

``validate_human_geography_replay`` is the only replay validator that reports
more than one message. It runs three independent families in a fixed order --
land use zones, natural frontiers, worldbuilding realism -- and appends one
fixed string per failing family. Each test therefore asserts the *exact* list
that comes back, so a tamper that leaks across family boundaries fails here.

Every payload recomputes the whole deterministic model from the raw cells, so a
passing payload can only come from a real generated world: the tests start from
the canonical 128-cell world, apply exactly one tamper, and compare lists.
``_tampered_world`` re-validates the pristine copy before handing it over, which
is what makes every tamper below provably non-vacuous -- the same payload
returns ``[]`` one line earlier.

Two shapes of tamper are used deliberately. Rewriting a *published* field (a
serialized cell index, a zone record, a summary counter) proves the validator
compares the payload against the model; rewriting the *upstream evidence* a
model is defined over (cell fertility, deposit viability, settlement score,
route cost) proves it recomputes that model instead of merely cross-checking
its own outputs.

Trap: the canonical 128-cell world draws no political borders, so
``payload["borders"]`` and ``payload["natural_frontiers"]`` are both empty and
``payload["borders"] = []`` is a silent no-op that returns ``[]``. The frontier
family is exercised by *injecting* a synthetic border instead.

Second trap: because a family answers with one fixed string, "this payload
fails" cannot say *which* branch of that family answered, and a case expecting
``[]`` cannot say whether the record was skipped or the injection never
happened. Three devices close that gap and every such case uses one of them:

* the expected message *list* -- a tamper confined to one family must leave the
  other two silent, which is what separates the cases in the tables below;
* a companion leg on the same payload that differs in exactly one field and
  produces a different list (the discarded-border, skipped-waterway and
  deposit-evidence cases);
* the frontier *producer*, :func:`enrich_world_with_natural_frontiers`, a
  separate implementation of the same model: running it over a tampered payload
  names the frontier rung outright and must silence the frontier family.
"""

from __future__ import annotations

from typing import Any
from unittest import TestCase

from support import worlds
from support.legacy_land_use_worlds import legacy_land_use_world

from magic_geo.human_geography_validation import validate_human_geography_replay
from magic_geo.land_use_availability_validation import validate_land_use_availability
from magic_geo.natural_frontiers import enrich_world_with_natural_frontiers

LAND_USE_FAILURE = "land use zone model or causal replay invalid"
FRONTIER_FAILURE = "natural frontier model or causal replay invalid"
WORLDBUILDING_FAILURE = "worldbuilding realism model or causal replay invalid"
ALL_FAILURES = [LAND_USE_FAILURE, FRONTIER_FAILURE, WORLDBUILDING_FAILURE]

#: The smallest canonical world that draws political borders, and therefore the
#: only one whose payload carries natural frontier records.
BORDERED_WORLD = "mid_512"

NATURAL_FRONTIER_MODEL_TYPE = "causal_border_terrain_connected_natural_frontiers_v1"
#: The frontier model only takes a border as a candidate when its type is not
#: ``open_lowland`` or its barrier score reaches this threshold.
NATURAL_FRONTIER_THRESHOLD = 0.45


class HumanGeographyReplayValidationTests(TestCase):
    def _legacy_world(self) -> dict[str, Any]:
        """An intact historical v1 world, independently validated by its loader."""
        world = legacy_land_use_world()
        self.assertEqual(
            world["worldbuilding_realism_model"]["model_type"],
            "causal_upstream_evidence_worldbuilding_realism_checks_v1",
        )
        return world

    def _tampered_world(self) -> dict[str, Any]:
        """A private copy of the canonical world, proven clean before tampering."""
        world = worlds.cached_world("replay_128")
        self.assertEqual(
            validate_human_geography_replay(world),
            [],
            "the untampered copy must replay clean, otherwise the tamper proves nothing",
        )
        return world

    def _world_with_injected_border(self, **overrides: Any) -> dict[str, Any]:
        """The canonical world plus one fabricated border segment.

        The base segment is an ``open_lowland`` border with no barrier, which the
        frontier model discards; overrides turn it into a candidate.
        """
        world = self._tampered_world()
        self.assertEqual(world["borders"], [], "the injected segment must be the only border")
        border: dict[str, Any] = {
            "id": 0,
            "cell_a": int(world["cells"][0]["id"]),
            "cell_b": int(world["cells"][1]["id"]),
            "region_a": 0,
            "region_b": 1,
            "type": "open_lowland",
            "barrier_score": 0.0,
            "length_km": 100.0,
        }
        border.update(overrides)
        world["borders"].append(border)
        return world

    def _zero_the_fertility_of_the_best_farmland(self, world: dict[str, Any]) -> None:
        cell = max(world["cells"], key=lambda item: float(item["agricultural_potential_index"]))
        self.assertGreater(float(cell["fertility"]), 0.0, "zeroing a zero is not a tamper")
        self.assertGreater(float(cell["agricultural_potential_index"]), 0.0)
        cell["fertility"] = 0.0

    def _zero_the_viability_of_the_first_deposit(self, world: dict[str, Any]) -> None:
        deposit = world["resource_deposits"][0]
        self.assertGreater(float(deposit["economic_viability_index"]), 0.0)
        cell = next(item for item in world["cells"] if int(item["id"]) == int(deposit["cell_id"]))
        self.assertGreater(
            float(cell["mining_potential_index"]),
            0.0,
            "the deposit must actually drive its cell's mining index",
        )
        deposit["economic_viability_index"] = 0.0

    def _zero_the_first_settlement_score(self, world: dict[str, Any]) -> None:
        settlement = world["settlements"][0]
        self.assertGreater(float(settlement["score"]), 0.0)
        settlement["score"] = 0.0

    def _double_the_first_route_cost(self, world: dict[str, Any]) -> None:
        route = world["routes"][0]
        self.assertGreater(float(route["cost"]), 0.0)
        self.assertGreater(float(route["distance_km"]), 0.0)
        route["cost"] = float(route["cost"]) * 2.0

    def test_generated_world_replays_clean(self) -> None:
        world = worlds.cached_world_readonly("replay_128")

        self.assertEqual(validate_human_geography_replay(world), [])

    def test_canonical_world_shape_makes_every_tamper_a_real_change(self) -> None:
        # Guards every tamper below against writing back a value the world already
        # holds: emptying an empty list or storing an index that is already there
        # would leave a test that cannot fail.
        world = self._tampered_world()
        summary = world["summary"]

        self.assertEqual(len(world["cells"]), 128)
        self.assertEqual(len(world["agricultural_zones"]), 9)
        self.assertEqual(len(world["mining_zones"]), 5)
        self.assertEqual(len(world["resource_deposits"]), 120)
        self.assertEqual(len(world["worldbuilding_realism_checks"]), 5)
        self.assertEqual(len(world["settlements"]), 3)
        self.assertEqual(len(world["routes"]), 3)
        self.assertEqual(world["natural_frontier_model"]["model_type"], NATURAL_FRONTIER_MODEL_TYPE)

        self.assertNotEqual(float(world["cells"][0]["agricultural_potential_index"]), 0.987654)
        self.assertNotEqual(float(world["cells"][1]["mining_potential_index"]), 0.5)
        self.assertEqual(summary["natural_frontier_count"], 0)
        # A pass count can never exceed the number of checks, which is exactly why
        # 999 is a tamper no generated world can produce.
        self.assertLessEqual(
            summary["worldbuilding_realism_pass_count"],
            len(world["worldbuilding_realism_checks"]),
        )

        # No political border is drawn at 128 cells, so ``borders = []`` would be a
        # silent no-op; the frontier family is tampered with an injected segment.
        self.assertEqual(world["borders"], [])
        self.assertEqual(world["natural_frontiers"], [])

        self.assertEqual(
            validate_human_geography_replay(world),
            [],
            "reading the shape must not have mutated the payload",
        )

    def test_single_family_tampers_report_exactly_one_message(self) -> None:
        # The point of this validator is per-family granularity: a tamper in one
        # family must never disturb the report of the other two.
        cases: dict[str, tuple[Any, list[str]]] = {
            "cell_agricultural_potential_index": (
                lambda world: world["cells"][0].__setitem__("agricultural_potential_index", 0.987654),
                [LAND_USE_FAILURE],
            ),
            "cell_mining_potential_index": (
                lambda world: world["cells"][1].__setitem__("mining_potential_index", 0.5),
                [LAND_USE_FAILURE],
            ),
            "agricultural_zones_emptied": (
                lambda world: world.__setitem__("agricultural_zones", []),
                [LAND_USE_FAILURE],
            ),
            "mining_zones_emptied": (
                lambda world: world.__setitem__("mining_zones", []),
                [LAND_USE_FAILURE],
            ),
            "natural_frontier_model_blanked": (
                lambda world: world.__setitem__("natural_frontier_model", {}),
                [FRONTIER_FAILURE],
            ),
            "summary_natural_frontier_count": (
                lambda world: world["summary"].__setitem__("natural_frontier_count", 7),
                [FRONTIER_FAILURE],
            ),
            "cell_natural_frontier_type": (
                lambda world: world["cells"][0].__setitem__("natural_frontier_type", "mountain"),
                [FRONTIER_FAILURE],
            ),
            "worldbuilding_check_score": (
                lambda world: world["worldbuilding_realism_checks"][0].__setitem__("score", 0.0),
                [WORLDBUILDING_FAILURE],
            ),
            "summary_worldbuilding_pass_count": (
                lambda world: world["summary"].__setitem__("worldbuilding_realism_pass_count", 999),
                [WORLDBUILDING_FAILURE],
            ),
            "worldbuilding_checks_emptied": (
                lambda world: world.__setitem__("worldbuilding_realism_checks", []),
                [WORLDBUILDING_FAILURE],
            ),
        }
        for name, (tamper, expected) in cases.items():
            with self.subTest(tamper=name):
                world = self._tampered_world()
                tamper(world)

                self.assertEqual(validate_human_geography_replay(world), expected)

    def test_legacy_upstream_evidence_tampers_report_exactly_one_message(self) -> None:
        # These rewrite model *inputs*, not published outputs, so they only fail if
        # the family recomputes its model from the raw payload. Fertility feeds the
        # agricultural index and deposit viability feeds the mining index (land
        # use); settlement score and route cost feed the water-access and
        # barrier-avoidance realism checks (worldbuilding). None of the four is an
        # input to the frontier model, which reads borders and terrain only.
        cases: dict[str, tuple[Any, list[str]]] = {
            "best_farmland_fertility": (self._zero_the_fertility_of_the_best_farmland, [LAND_USE_FAILURE]),
            "deposit_economic_viability": (self._zero_the_viability_of_the_first_deposit, [LAND_USE_FAILURE]),
            "settlement_score": (self._zero_the_first_settlement_score, [WORLDBUILDING_FAILURE]),
            "route_cost": (self._double_the_first_route_cost, [WORLDBUILDING_FAILURE]),
        }
        for name, (tamper, expected) in cases.items():
            with self.subTest(tamper=name):
                world = self._legacy_world()
                tamper(world)

                self.assertEqual(validate_human_geography_replay(world), expected)

    def test_current_upstream_evidence_reports_every_affected_family(self) -> None:
        # Current worldbuilding v3 verifies the resource parents used by its fishery
        # context. Changing fertility or viability invalidates that evidence as
        # well as the independently replayed land-use potential.
        cases = {
            "best_farmland_fertility": (
                self._zero_the_fertility_of_the_best_farmland,
                [LAND_USE_FAILURE, WORLDBUILDING_FAILURE],
            ),
            "deposit_economic_viability": (
                self._zero_the_viability_of_the_first_deposit,
                [LAND_USE_FAILURE, WORLDBUILDING_FAILURE],
            ),
            "settlement_score": (self._zero_the_first_settlement_score, [WORLDBUILDING_FAILURE]),
            "route_cost": (self._double_the_first_route_cost, [WORLDBUILDING_FAILURE]),
        }
        for name, (tamper, expected) in cases.items():
            with self.subTest(tamper=name):
                world = self._tampered_world()
                self.assertEqual(world["worldbuilding_realism_model"]["model_type"],
                                 "causal_upstream_evidence_worldbuilding_realism_checks_v3")
                tamper(world)
                self.assertEqual(validate_human_geography_replay(world), expected)

    def test_extra_natural_frontier_record_reports_only_the_frontier_message(self) -> None:
        # ``natural_frontiers`` is empty at 128 cells (no political borders are
        # drawn), so an extra record is a pure length mismatch.
        world = self._tampered_world()
        self.assertEqual(world["natural_frontiers"], [])
        world["natural_frontiers"].append({"id": 99})

        self.assertEqual(validate_human_geography_replay(world), [FRONTIER_FAILURE])

    def test_injected_border_reaches_the_frontier_family_only_when_it_qualifies(self) -> None:
        # Every injected segment changes the worldbuilding border-alignment
        # evidence (``border_segment_count`` and the length-weighted index), so the
        # worldbuilding message is constant here and the frontier message is the
        # discriminator. A qualifying border makes the frontier model expect a
        # non-empty frontier record and non-zero cell frontier indices, neither of
        # which the payload carries; a discarded one leaves the model unchanged.
        cases: dict[str, tuple[dict[str, Any], list[str]]] = {
            "mountain_barrier": (
                {"type": "mountain", "barrier_score": 0.9},
                [FRONTIER_FAILURE, WORLDBUILDING_FAILURE],
            ),
            "open_lowland_at_threshold": (
                {"barrier_score": NATURAL_FRONTIER_THRESHOLD},
                [FRONTIER_FAILURE, WORLDBUILDING_FAILURE],
            ),
            "open_lowland_just_below_threshold": (
                {"barrier_score": NATURAL_FRONTIER_THRESHOLD - 0.01},
                [WORLDBUILDING_FAILURE],
            ),
            "open_lowland_without_barrier": (
                {"barrier_score": 0.0},
                [WORLDBUILDING_FAILURE],
            ),
            "barrier_between_unknown_cells": (
                {"type": "mountain", "barrier_score": 0.9, "cell_a": 10_000, "cell_b": 10_001},
                [WORLDBUILDING_FAILURE],
            ),
        }
        for name, (overrides, expected) in cases.items():
            with self.subTest(border=name):
                world = self._world_with_injected_border(**overrides)

                self.assertEqual(validate_human_geography_replay(world), expected)

    def test_tamper_shared_by_two_families_reports_both_messages_in_order(self) -> None:
        # ``resource_deposits`` feeds the mining-potential replay and the
        # resource/geology realism check, but nothing in the frontier family.
        world = self._tampered_world()
        self.assertEqual(len(world["resource_deposits"]), 120)
        world["resource_deposits"] = []

        self.assertEqual(
            validate_human_geography_replay(world),
            [LAND_USE_FAILURE, WORLDBUILDING_FAILURE],
        )

    def test_duplicate_cell_id_reports_all_three_messages(self) -> None:
        # Every family indexes cells by id and rejects a payload whose ids are not
        # unique, so this one structural tamper trips all three at once.
        world = self._tampered_world()
        world["cells"].append(dict(world["cells"][0]))

        self.assertEqual(validate_human_geography_replay(world), ALL_FAILURES)

    def test_malformed_payloads_report_all_three_messages_without_raising(self) -> None:
        cases: dict[str, dict[str, Any]] = {
            "empty": {},
            "summary_only": {"summary": {}},
            "cells_nulled": {"cells": None, "summary": None},
            "cells_not_a_list": {"cells": "nope", "summary": {}, "borders": "nope"},
            "summary_not_a_mapping": {"cells": [{"id": 0}], "summary": []},
        }
        for name, payload in cases.items():
            with self.subTest(payload=name):
                self.assertEqual(validate_human_geography_replay(payload), ALL_FAILURES)

    def test_each_family_reports_only_the_collections_it_reads(self) -> None:
        # Every family re-reads the payload itself, so a collection replaced by
        # something it cannot index has to be caught by that family's own guard.
        # The expected message list is therefore a map of which family reads
        # what: only the frontier model reads the waterways, only it and the
        # land use model own a zone model descriptor, and the deposits are
        # shared by the land use and worldbuilding models.
        cases: dict[str, tuple[Any, list[str]]] = {
            "land_use_model_blanked": (
                lambda world: world.__setitem__("land_use_zone_model", {}),
                [LAND_USE_FAILURE],
            ),
            "resource_deposits_not_a_list": (
                lambda world: world.__setitem__("resource_deposits", {}),
                [LAND_USE_FAILURE, WORLDBUILDING_FAILURE],
            ),
            "navigable_waterways_not_a_list": (
                lambda world: world.__setitem__("navigable_waterways", {}),
                [FRONTIER_FAILURE],
            ),
            "settlements_not_a_list": (
                lambda world: world.__setitem__("settlements", {}),
                ALL_FAILURES,
            ),
            "routes_not_a_list": (
                lambda world: world.__setitem__("routes", {}),
                ALL_FAILURES,
            ),
        }
        for name, (tamper, expected) in cases.items():
            with self.subTest(collection=name):
                world = self._tampered_world()
                tamper(world)

                self.assertEqual(validate_human_geography_replay(world), expected)

    def test_cells_whose_neighbour_list_is_unusable_form_single_cell_zones(self) -> None:
        # Historical v1 zones are mesh components, so a cell whose neighbour list is not a list
        # cannot be walked from; the model treats it as isolated. Doing that to
        # every member of the agricultural zones splits them into one zone per
        # cell, which the stored zone ids contradict.
        world = self._legacy_world()
        members = [
            cell for cell in world["cells"] if int(cell.get("agricultural_zone_id", -1)) >= 0
        ]
        self.assertGreater(len(members), len(world["agricultural_zones"]))
        for cell in members:
            cell["neighbors"] = None

        self.assertEqual(validate_human_geography_replay(world), [LAND_USE_FAILURE])

    def test_a_route_with_an_unknown_endpoint_is_dropped_from_the_link_maps(self) -> None:
        # Historical v1 land use and the frontier family index routes by the
        # settlements they join, and skip a route whose endpoint is not a known
        # settlement. The land use family notices, because the zone records
        # publish the routes that touch them.
        world = self._legacy_world()
        route = world["routes"][0]
        self.assertNotEqual(int(route["from"]), 10**9)
        route["from"] = 10**9

        self.assertEqual(validate_human_geography_replay(world), [LAND_USE_FAILURE])

    def test_current_land_use_rejects_unusable_graph_inputs(self) -> None:
        cases = {
            "unusable_neighbours": lambda world: world["cells"][0].__setitem__("neighbors", None),
            "unknown_route_endpoint": lambda world: world["routes"][0].__setitem__("from", 10**9),
        }
        for name, tamper in cases.items():
            with self.subTest(tamper=name):
                world = self._tampered_world()
                self.assertEqual(validate_land_use_availability(world), [])
                tamper(world)
                errors = validate_land_use_availability(world)
                self.assertTrue(errors, "current inputs must be rejected before numerical replay")
                # Current worldbuilding also requires complete reciprocal cell
                # neighbors and known route endpoints before evaluating checks.
                self.assertEqual(validate_human_geography_replay(world),
                                 [LAND_USE_FAILURE, WORLDBUILDING_FAILURE])

    def test_records_the_frontier_family_skips_leave_it_silent(self) -> None:
        # Two skip branches whose whole point is that nothing downstream moves.
        # The waterway case stands alone; the border case needs a companion
        # tamper because the worldbuilding family reads ``borders`` too and would
        # raise on a non-dict record, so its model descriptor is blanked to make
        # it bail out first. Its message is therefore constant across the control
        # below, and the frontier message is the discriminator.
        with self.subTest(skipped="waterway_without_an_id"):
            world = self._tampered_world()
            waterway = world["navigable_waterways"][0]
            self.assertGreaterEqual(int(waterway["id"]), 0)
            waterway["id"] = -1

            self.assertEqual(validate_human_geography_replay(world), [])

        with self.subTest(control="waterway_without_an_id_on_a_world_with_frontiers"):
            # The clean result above cannot by itself tell "the record was
            # skipped" from "the waterways are never read": at 128 cells there
            # is no frontier record to link them to. On the smallest canonical
            # world that has frontier records the very same tamper drops the
            # waterway from the link map, so the stored record's
            # ``navigable_waterway_ids`` no longer match and only the frontier
            # family reports.
            world = worlds.cached_world(BORDERED_WORLD)
            self.assertEqual(validate_human_geography_replay(world), [])
            linked = {int(value) for value in world["natural_frontiers"][0]["navigable_waterway_ids"]}
            self.assertTrue(linked, "the first frontier must link a waterway")
            waterway = next(
                record for record in world["navigable_waterways"] if int(record["id"]) in linked
            )
            original = int(waterway["id"])
            waterway["id"] = -1

            self.assertEqual(validate_human_geography_replay(world), [FRONTIER_FAILURE])

            waterway["id"] = original
            self.assertEqual(
                validate_human_geography_replay(world),
                [],
                "restoring the waterway id must replay clean again",
            )

        with self.subTest(skipped="non_dict_border"):
            world = self._tampered_world()
            world["worldbuilding_realism_model"] = {}
            world["borders"].append("not-a-border")

            self.assertEqual(validate_human_geography_replay(world), [WORLDBUILDING_FAILURE])

        with self.subTest(control="blanked_worldbuilding_model_only"):
            world = self._tampered_world()
            world["worldbuilding_realism_model"] = {}

            self.assertEqual(validate_human_geography_replay(world), [WORLDBUILDING_FAILURE])

    def test_deposit_geology_evidence_falls_back_to_the_cell_it_sits_on(self) -> None:
        # The historical v1 resource realism check reads each deposit's formation evidence and
        # falls back to the host cell when it is not a mapping, so a corrupted
        # evidence block is tolerated; an unmodelled resource is not, because it
        # drops to the generic confidence rule and loses its support.
        with self.subTest(deposit="evidence_not_a_mapping"):
            world = self._legacy_world()
            for deposit in world["resource_deposits"]:
                self.assertIsInstance(deposit["formation_evidence"], dict)
                deposit["formation_evidence"] = "not-a-mapping"

            self.assertEqual(validate_human_geography_replay(world), [])

        with self.subTest(deposit="the_cell_answers_only_once_the_evidence_is_gone"):
            # The pair that proves *which* source answered. ``salinity_index``
            # is read from the evidence with the host cell's
            # ``soil_salinity_index`` as the fallback, and nothing but the
            # evaporite rule reads it, so raising it on every cell:
            #   * leaves the resource check untouched while the evidence block
            #     is intact -- the evidence wins, the cell is not consulted;
            #   * flips the evaporite support once the evidence is unusable --
            #     the cell answered in its place.
            # Both legs also move the land use replay, so that message is the
            # constant here and the worldbuilding message is the discriminator.
            world = self._legacy_world()
            for cell in world["cells"]:
                self.assertLess(float(cell["soil_salinity_index"]), 0.9)
                cell["soil_salinity_index"] = 0.9

            self.assertEqual(validate_human_geography_replay(world), [LAND_USE_FAILURE])

            for deposit in world["resource_deposits"]:
                deposit["formation_evidence"] = "not-a-mapping"

            self.assertEqual(
                validate_human_geography_replay(world),
                [LAND_USE_FAILURE, WORLDBUILDING_FAILURE],
                "with the evidence unusable the host cell's salinity must decide "
                "the evaporite rule",
            )

        with self.subTest(deposit="unmodelled_resource"):
            world = self._legacy_world()
            deposit = world["resource_deposits"][0]
            self.assertNotEqual(str(deposit["resource"]), "unobtainium")
            deposit["resource"] = "unobtainium"

            self.assertEqual(validate_human_geography_replay(world), [WORLDBUILDING_FAILURE])

    def test_current_worldbuilding_rejects_corrupted_resource_parent_evidence(self) -> None:
        # The current v3 fishery context audits the actual resource chain before the
        # historical material-geology fallback could hide stale parent evidence.
        for field in ("formation_evidence", "soil_salinity_index"):
            with self.subTest(field=field):
                world = self._tampered_world()
                self.assertEqual(world["worldbuilding_realism_model"]["model_type"],
                                 "causal_upstream_evidence_worldbuilding_realism_checks_v3")
                if field == "formation_evidence":
                    for deposit in world["resource_deposits"]:
                        self.assertIsInstance(deposit[field], dict)
                        deposit[field] = "not-a-mapping"
                    expected = [WORLDBUILDING_FAILURE]
                else:
                    for cell in world["cells"]:
                        self.assertLess(float(cell[field]), 0.9)
                        cell[field] = 0.9
                    expected = [LAND_USE_FAILURE, WORLDBUILDING_FAILURE]
                self.assertEqual(validate_human_geography_replay(world), expected)

    def test_region_capital_and_settlement_membership_drive_connectivity(self) -> None:
        # The connectivity check walks the route graph from each region's
        # capital. A region with no settlements counts as fully connected
        # without walking anything, which changes the published evidence; a
        # capital that is not one of the region's settlements is replaced by a
        # member, which for this world reaches the same settlements as before.
        with self.subTest(region="without_settlements"):
            world = self._tampered_world()
            region = world["political_regions"][0]
            self.assertTrue(region["settlement_ids"])
            region["settlement_ids"] = []

            self.assertEqual(validate_human_geography_replay(world), [WORLDBUILDING_FAILURE])

        with self.subTest(region="capital_outside_the_region"):
            world = self._tampered_world()
            region = world["political_regions"][0]
            self.assertNotIn(9999, region["settlement_ids"])
            # The replacement is only load-bearing where the walk has somewhere
            # to go: with a single settlement an unreplaced capital would still
            # score 1.0 and this case could not fail.
            self.assertGreater(len(region["settlement_ids"]), 1)
            region["capital_settlement_id"] = 9999

            self.assertEqual(validate_human_geography_replay(world), [])

    def _inject_open_border_between_rewritten_cells(
        self, world: dict[str, Any], **terrain: Any
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Give the two cells of one injected open-lowland border a terrain.

        The frontier model only classifies the endpoints of a border it accepts,
        and it accepts an ``open_lowland`` segment once its barrier score reaches
        the threshold, so this is the shortest path to the terrain ladder.
        Returns the two endpoint cells so the caller can read what the model
        named them.
        """
        self.assertEqual(world["borders"], [], "the injected segment must be the only border")
        first, second = world["cells"][0], world["cells"][1]
        for cell in (first, second):
            # Neutralise the ice rung, which answers before every rung below it.
            cell.update({"ice_thickness_m": 0.0, "permafrost_class": "none", "elevation_m": 100.0})
            cell.update(terrain)
        world["borders"].append(
            {
                "id": 0,
                "cell_a": int(first["id"]),
                "cell_b": int(second["id"]),
                "region_a": 0,
                "region_b": 1,
                "type": "open_lowland",
                "barrier_score": NATURAL_FRONTIER_THRESHOLD,
                "length_km": 100.0,
            }
        )
        return first, second

    def test_the_cell_terrain_names_the_frontier_a_border_runs_along(self) -> None:
        self._assert_terrain_frontier_replay(legacy=False)

    def test_legacy_cell_terrain_names_the_frontier_a_border_runs_along(self) -> None:
        self._assert_terrain_frontier_replay(legacy=True)

    def _assert_terrain_frontier_replay(self, *, legacy: bool) -> None:
        # The same eight terrain witnesses retain the historical equations and
        # test current availability. These current endpoints are cold exposed
        # land: unsupported agriculture stays zero when their terrain changes.
        # Coastal water also invalidates their published mining applicability.
        # Running the separate frontier producer must name the expected rung
        # and remove exactly the frontier replay failure in both versions.
        cases: dict[str, tuple[str, dict[str, Any]]] = {
            "river": ("river", {"is_river": True}),
            "coastal": ("coastal", {"is_river": False, "water_body_type": "ocean"}),
            "mountain": (
                "mountain",
                {"is_river": False, "water_body_type": "land", "landform": "mountain_range"},
            ),
            "desert": (
                "desert",
                {
                    "is_river": False,
                    "water_body_type": "land",
                    "landform": "plain",
                    "biome": "hot_desert",
                },
            ),
            "dense_forest": (
                "dense_forest",
                {
                    "is_river": False,
                    "water_body_type": "land",
                    "landform": "plain",
                    "biome": "tropical_rainforest",
                    "seasonal_aridity_index": 0.0,
                },
            ),
            "wetland": (
                "wetland",
                {
                    "is_river": False,
                    "water_body_type": "land",
                    "landform": "plain",
                    "biome": "wetland",
                    "seasonal_aridity_index": 0.0,
                },
            ),
            # Nothing at all: both endpoints are plain lowland, so the counter
            # the model votes with is empty and it falls back to the generic
            # "terrain_barrier" name.
            "open_lowland_fallback": (
                "terrain_barrier",
                {
                    "is_river": False,
                    "water_body_type": "land",
                    "landform": "plain",
                    "biome": "steppe",
                    "seasonal_aridity_index": 0.0,
                },
            ),
            # A permafrost class alone raises the ice score even where the ice
            # thickness is zero.
            "permafrost": ("ice", {"permafrost_class": "continuous"}),
        }
        self.assertEqual(
            len({expected for expected, _ in cases.values()}),
            len(cases),
            "two cases expecting the same name could not tell their rungs apart",
        )
        for name, (expected_type, terrain) in cases.items():
            with self.subTest(frontier_terrain=name):
                world = self._legacy_world() if legacy else self._tampered_world()
                if not legacy:
                    for cell in world["cells"][:2]:
                        self.assertTrue(cell["agricultural_habitat_applicable"])
                        self.assertFalse(cell["agricultural_climate_supported"])
                        self.assertFalse(cell["agricultural_potential_supported"])
                        self.assertEqual(cell["agricultural_potential_index"], 0.0)
                        self.assertTrue(cell["mining_surface_applicable"])
                land_errors = [LAND_USE_FAILURE] if legacy or name == "coastal" else []
                first, second = self._inject_open_border_between_rewritten_cells(world, **terrain)
                self.assertEqual(str(first["natural_frontier_type"]), "none")

                self.assertEqual(
                    validate_human_geography_replay(world),
                    land_errors + [FRONTIER_FAILURE, WORLDBUILDING_FAILURE],
                )

                enrich_world_with_natural_frontiers(world)

                self.assertEqual(str(first["natural_frontier_type"]), expected_type)
                self.assertEqual(str(second["natural_frontier_type"]), expected_type)
                self.assertEqual(
                    validate_human_geography_replay(world),
                    land_errors + [WORLDBUILDING_FAILURE],
                    f"the validator must replay the {expected_type!r} rung the producer wrote",
                )

    def test_natural_frontier_records_are_rebuilt_from_the_border_components(self) -> None:
        # The canonical 128-cell world draws no borders, so its frontier record
        # list is empty and the record builder never runs. The existing 512-cell
        # control carries four frontier records. Waterways
        # and settlements touch different components in the current seasonal
        # world, so each membership tamper selects an actual linked record.
        world = worlds.cached_world(BORDERED_WORLD)
        self.assertEqual(
            validate_human_geography_replay(world),
            [],
            "the untampered bordered world must replay clean",
        )
        records = world["natural_frontiers"]
        self.assertEqual(len(records), 4)
        self.assertEqual(world["summary"]["natural_frontier_count"], 4)
        record = records[0]
        self.assertEqual(record["region_ids"], [0, 1])
        self.assertTrue(record["route_ids"], "the first frontier must link routes")
        self.assertTrue(record["navigable_waterway_ids"], "the first frontier must link a waterway")
        settlement_records = [item for item in records if item["settlement_ids"]]
        self.assertTrue(settlement_records, "a frontier must link a real settlement")

        cases: dict[str, Any] = {
            "frontier_type": "river",
            "cell_count": 99,
            "border_segment_count": 1,
            "border_ids": [],
            "region_ids": [0],
            "route_ids": [],
            "route_crossing_count": 0,
            "settlement_ids": [],
            "navigable_waterway_ids": [],
            "dominant_landform": "plain",
            "dominant_biome": "steppe",
            "area_km2": 1.0,
            "total_border_length_km": 1.0,
            "mean_barrier_score": 0.5,
            "mean_frontier_index": 0.5,
        }
        for field, value in cases.items():
            with self.subTest(frontier_field=field):
                record = settlement_records[0] if field == "settlement_ids" else records[0]
                original = record[field]
                self.assertNotEqual(original, value, f"{field} already holds {value!r}")
                record[field] = value

                self.assertEqual(validate_human_geography_replay(world), [FRONTIER_FAILURE])

                record[field] = original
                self.assertEqual(
                    validate_human_geography_replay(world),
                    [],
                    f"undoing the {field!r} tamper must replay clean again",
                )

    def test_every_resource_class_has_its_own_geologic_support_rule(self) -> None:
        # The resource realism check asks a different question of each resource
        # class, so relabelling every deposit routes the whole payload through
        # one rule that this world's geology was never built to satisfy. The
        # deposits are otherwise untouched, so only the rule changes.
        world = worlds.cached_world_readonly("replay_128")
        present = {str(deposit["resource"]) for deposit in world["resource_deposits"]}
        for resource in (
            "volcanic_arc_metals",
            "craton_iron_gold",
            "sedimentary_fuels",
            "evaporites",
            "placer_metals",
            "geothermal",
            "fertile_alluvium",
            "coastal_fisheries",
        ):
            with self.subTest(resource=resource):
                tampered = self._tampered_world()
                self.assertNotEqual(
                    {resource},
                    present,
                    "every deposit already carries this resource",
                )
                for deposit in tampered["resource_deposits"]:
                    deposit["resource"] = resource

                self.assertEqual(
                    validate_human_geography_replay(tampered), [WORLDBUILDING_FAILURE]
                )
