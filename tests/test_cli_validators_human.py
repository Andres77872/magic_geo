"""Human-geography validator coverage driven through the `validate` CLI.

Every check tampers with exactly one derived quantity of an otherwise valid
generated world, writes it to a temporary file, and asserts that
``magic-geo validate`` rejects it with the specific replay failure text of the
validator under test. Untampered control runs keep the tampered assertions from
passing vacuously.

The validators live in ``magic_geo.cli.validators`` (political, settlement,
ports, corridors) and the CLI is their stable surface. The final test class is
the exception: it calls the validators directly because the branches it covers
guard payload shapes that make the CLI's own accessors raise, so through
``validate`` they are indistinguishable from a crash.

A tamper that only one validator can notice asserts the *complete* failure list;
a tamper that necessarily disturbs neighbouring domains (a cell field feeds many
replays) asserts that the validator under test is among the objectors. Where the
CLI cannot observe which branch a replay took, the check says so rather than
implying more than it proves.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.api import generate_world
from magic_geo.cli import app
from magic_geo.cli.validators import (
    _validate_political_borders,
    _validate_political_regions,
    _validate_port_sites,
    _validate_route_corridors,
    _validate_route_network,
    _validate_settlement_selection,
)
from magic_geo.io import write_json

from support import worlds

REGION_FAILURE = "political region model or causal replay invalid"
BORDER_FAILURE = "political border model or causal replay invalid"
TRADE_FAILURE = "trade flow model or causal replay invalid"
SETTLEMENT_FAILURE = "settlement selection model or causal replay invalid"
ROUTE_FAILURE = "route network model or causal replay invalid"
PORT_FAILURE = "port site model or causal replay invalid"
CORRIDOR_FAILURE = "route corridor model or causal replay invalid"
HYDROLOGY_FAILURE = "hydrologic water budget model or replay invalid"

MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
MOUNTAIN_BORDER_LANDFORMS = {"mountain_belt", "glacial_valley"}
MOUNTAIN_CORRIDOR_LANDFORMS = {
    "mountain",
    "mountain_range",
    "volcanic_arc",
    "highland",
    "ridge",
    "glacial_valley",
}
DESERT_BIOMES = {"cold_desert", "hot_desert"}
MINING_RESOURCES = {
    "volcanic_arc_metals",
    "craton_iron_gold",
    "placer_metals",
    "geothermal",
}

Mutation = Callable[[dict[str, Any], dict[int, dict[str, Any]]], None]


def cells_by_id(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(cell["id"]): cell for cell in world["cells"]}


def marine_neighbours(
    cell: dict[str, Any], cells: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        cells[int(neighbor_id)]
        for neighbor_id in cell["neighbors"]
        if cells[int(neighbor_id)]["water_body_type"] in MARINE_WATER_TYPES
    ]


def first_inland_cell(
    world: dict[str, Any], cells: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    """A land cell with no marine neighbour, so its bay/mouth/strait indices are 0."""

    for cell in world["cells"]:
        if not cell["is_water"] and not marine_neighbours(cell, cells):
            return cell
    raise LookupError("no inland land cell")


def first_coastal_cell(
    world: dict[str, Any], cells: dict[int, dict[str, Any]], minimum_marine: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    for cell in world["cells"]:
        if cell["is_water"] or cell["is_river"]:
            continue
        adjacent = marine_neighbours(cell, cells)
        if len(adjacent) >= minimum_marine:
            return cell, adjacent
    raise LookupError(f"no land cell with {minimum_marine} marine neighbours")


def first_landform_cell(world: dict[str, Any], landform: str) -> dict[str, Any]:
    for cell in world["cells"]:
        if not cell["is_water"] and cell["landform"] == landform:
            return cell
    raise LookupError(f"no land cell with landform {landform}")


def settlement_cell(
    world: dict[str, Any],
    cells: dict[int, dict[str, Any]],
    settlement_type: str,
) -> dict[str, Any]:
    for settlement in world["settlements"]:
        if settlement["type"] == settlement_type:
            return cells[int(settlement["cell_id"])]
    raise LookupError(f"no {settlement_type} settlement")


def lowland_border_candidate(cell: dict[str, Any]) -> bool:
    """True when this cell alone cannot force a river/mountain/desert/ice border."""

    return (
        not cell["is_water"]
        and not cell["is_river"]
        and int(cell["political_region_id"]) >= 0
        and float(cell["elevation_m"]) <= 1400.0
        and cell["landform"] not in MOUNTAIN_BORDER_LANDFORMS
        and cell["landform"] not in {"ice_field", "coastal_plain"}
        and cell["biome"] not in DESERT_BIOMES
        and cell["biome"] != "ice_cap"
    )


def lowland_pair_cell(
    world: dict[str, Any], cells: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    """A cell whose same-region lowland neighbour becomes a non-mountain border."""

    for cell in world["cells"]:
        if not lowland_border_candidate(cell):
            continue
        for neighbor_id in cell["neighbors"]:
            other = cells[int(neighbor_id)]
            if not lowland_border_candidate(other):
                continue
            if other["political_region_id"] == cell["political_region_id"]:
                return cell
    raise LookupError("no same-region lowland adjacency")


class ValidatorCliTestCase(TestCase):
    """Write a world payload to a temporary file and run ``validate`` on it."""

    def run_validate(self, world: dict[str, Any]) -> tuple[int, list[str], str]:
        """The exit code, every replayed ``FAIL`` message, and the raw output.

        A crash inside ``validate`` also exits non-zero, but it aborts before the
        collected failures are echoed, so an empty message list separates a crash
        from a clean rejection.
        """

        with TemporaryDirectory() as directory:
            world_path = Path(directory) / "world.json"
            write_json(world_path, world)
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
        messages = [
            line.removeprefix("FAIL ")
            for line in result.output.splitlines()
            if line.startswith("FAIL ")
        ]
        return result.exit_code, messages, result.output

    def assert_world_valid(self, world: dict[str, Any]) -> None:
        exit_code, messages, output = self.run_validate(world)
        self.assertEqual(exit_code, 0, output)
        self.assertEqual(messages, [])
        self.assertIn("OK", output)

    def assert_world_rejected(self, world: dict[str, Any], *messages: str) -> None:
        """The named validators rejected the world; other domains may too."""

        exit_code, failures, output = self.run_validate(world)
        self.assertEqual(exit_code, 1, output)
        for message in messages:
            self.assertIn(message, failures)

    def assert_world_rejected_only(
        self, world: dict[str, Any], *messages: str
    ) -> None:
        """The named validators are the *only* ones that rejected the world."""

        exit_code, failures, output = self.run_validate(world)
        self.assertEqual(exit_code, 1, output)
        self.assertEqual(sorted(failures), sorted(messages))

    def tampered(self, key: str, mutation: Mutation) -> dict[str, Any]:
        """A private copy of the canonical world ``key`` with one tamper applied."""

        world = worlds.cached_world(key)
        mutation(world, cells_by_id(world))
        return world

    def assert_tamper_rejected(
        self, key: str, mutation: Mutation, *messages: str
    ) -> None:
        self.assert_world_rejected(self.tampered(key, mutation), *messages)

    def assert_tamper_is_sole_failure(
        self, key: str, mutation: Mutation, *messages: str
    ) -> None:
        self.assert_world_rejected_only(self.tampered(key, mutation), *messages)


class ControlWorldTests(ValidatorCliTestCase):
    def test_small_world_passes_validation(self) -> None:
        self.assert_world_valid(worlds.cached_world_readonly("small_smoke"))

    def test_mid_world_passes_validation(self) -> None:
        self.assert_world_valid(worlds.cached_world_readonly("mid_512"))

    def test_large_world_stops_selecting_settlements_at_the_target(self) -> None:
        # The canonical worlds run out of candidates before the settlement
        # target, so only a denser mesh exercises the greedy stop.
        world = generate_world(
            worlds.build_config(
                **{
                    "mesh.cell_count": 1024,
                    "tectonics.plate_count": 8,
                    "erosion.iterations": 1,
                }
            )
        )
        model = world["settlement_selection_model"]
        self.assertGreater(
            int(model["candidate_cell_count"]), int(model["target_count"])
        )
        self.assertEqual(len(world["settlements"]), int(model["target_count"]))
        self.assert_world_valid(world)


class ModelDescriptorTests(ValidatorCliTestCase):
    def test_wrong_model_descriptor_rejects_each_replay(self) -> None:
        """One wrong descriptor must reject exactly one replay and nothing else.

        These tamper with a documentation string that only its own validator
        reads, so the whole run must produce that single failure: pinning the
        complete list also catches a replay that starts rejecting worlds it has
        no business inspecting.
        """

        def wrong_descriptor(model_key: str, field: str) -> Mutation:
            def mutation(world: dict[str, Any], _cells: Any) -> None:
                world[model_key][field] = "not_the_documented_model"

            return mutation

        for name, mutation, message in (
            (
                "port site domain",
                wrong_descriptor("port_site_model", "domain"),
                PORT_FAILURE,
            ),
            (
                "settlement record order",
                wrong_descriptor("settlement_selection_model", "record_order"),
                SETTLEMENT_FAILURE,
            ),
            (
                "route network record order",
                wrong_descriptor("route_network_model", "record_order"),
                ROUTE_FAILURE,
            ),
            (
                "political region record order",
                wrong_descriptor("political_region_model", "record_order"),
                REGION_FAILURE,
            ),
            (
                "political border record order",
                wrong_descriptor("political_border_model", "record_order"),
                BORDER_FAILURE,
            ),
            (
                "trade flow record model",
                wrong_descriptor("trade_flow_model", "record_model"),
                TRADE_FAILURE,
            ),
            (
                "route corridor record order",
                wrong_descriptor("route_corridor_model", "record_order"),
                CORRIDOR_FAILURE,
            ),
        ):
            with self.subTest(name):
                self.assert_tamper_is_sole_failure("small_smoke", mutation, message)


class PortSiteValidatorTests(ValidatorCliTestCase):
    def test_port_site_model_and_record_violations(self) -> None:
        def non_numeric_threshold(world: dict[str, Any], _cells: Any) -> None:
            world["port_site_model"]["port_site_threshold"] = "high"

        def wrong_candidate_count(world: dict[str, Any], _cells: Any) -> None:
            world["port_site_model"]["candidate_cell_count"] += 7

        def drop_site(world: dict[str, Any], _cells: Any) -> None:
            world["port_sites"].pop()

        def wrong_site_landform(world: dict[str, Any], _cells: Any) -> None:
            world["port_sites"][0]["landform"] = "not_a_landform"

        def wrong_summary_count(world: dict[str, Any], _cells: Any) -> None:
            world["summary"]["port_site_count"] += 3

        def chokepoints_not_a_list(world: dict[str, Any], _cells: Any) -> None:
            world["marine_chokepoints"] = {}

        for name, mutation in (
            ("non numeric port_site_threshold", non_numeric_threshold),
            ("candidate_cell_count mismatch", wrong_candidate_count),
            ("dropped port site record", drop_site),
            ("port site landform mismatch", wrong_site_landform),
            ("summary port_site_count mismatch", wrong_summary_count),
            ("marine_chokepoints is not a list", chokepoints_not_a_list),
        ):
            with self.subTest(name):
                self.assert_tamper_rejected("small_smoke", mutation, PORT_FAILURE)

    # The three site-type checks below carry a cell over one rung of the
    # classification ladder. ``validate`` only reports *that* the port replay
    # disagreed with the stored records, never which rung it took, so each one
    # asserts the port rejection and keeps the tamper minimal: every write left
    # in them is one the rung needs (removing any single write drops the run
    # back to the rung below).

    def test_inland_high_harbor_cell_is_classified_as_harbor_port(self) -> None:
        def raise_harbor_index(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            # No marine neighbour keeps bay/mouth/strait at zero, so the harbour
            # threshold alone drives the site type.
            first_inland_cell(world, cells)["harbor_suitability_index"] = 0.90

        self.assert_tamper_rejected("small_smoke", raise_harbor_index, PORT_FAILURE)

    def test_sheltered_shallow_shelf_cell_is_classified_as_protected_bay(self) -> None:
        def shelter_the_coast(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            cell, adjacent = first_coastal_cell(world, cells, 3)
            cell["harbor_suitability_index"] = 0.61
            for neighbor in adjacent:
                neighbor["water_body_type"] = "continental_shelf"

        self.assert_tamper_rejected("small_smoke", shelter_the_coast, PORT_FAILURE)

    def test_exposed_coast_above_the_site_threshold_is_a_coastal_port(self) -> None:
        def expose_the_coast(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            # A floodplain with no runoff holds the river-mouth index below its
            # threshold and the harbour index stays just under the harbour-port
            # cut, so only the raw suitability score can select the site: it
            # needs every remaining term (navigability, settlement, climate) at
            # its maximum and no ice or relief penalty.
            cell, _adjacent = first_coastal_cell(world, cells, 3)
            cell["harbor_suitability_index"] = 0.6199
            cell["coastal_navigability_index"] = 1.0
            cell["settlement_score"] = 1.0
            cell["temperature_c"] = 22.0
            cell["ice_thickness_m"] = 0.0
            cell["elevation_m"] = 100.0
            cell["landform"] = "floodplain"
            cell["runoff_mm_y"] = 0.0

        self.assert_tamper_rejected("small_smoke", expose_the_coast, PORT_FAILURE)


class SettlementSelectionValidatorTests(ValidatorCliTestCase):
    def test_settlement_model_and_score_violations(self) -> None:
        def non_numeric_threshold(world: dict[str, Any], _cells: Any) -> None:
            world["settlement_selection_model"]["score_threshold"] = "low"

        def wrong_candidate_count(world: dict[str, Any], _cells: Any) -> None:
            world["settlement_selection_model"]["candidate_cell_count"] += 11

        def wrong_top_score(world: dict[str, Any], _cells: Any) -> None:
            world["summary"]["top_settlement_score"] = 0.123456

        def non_numeric_record_fertility(world: dict[str, Any], _cells: Any) -> None:
            world["settlements"][0]["fertility"] = "rich"

        def monthly_climate_not_a_list(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            cells[int(world["settlements"][0]["cell_id"])][
                "temperature_monthly_c"
            ] = "warm"

        def alluvial_fan_landform(world: dict[str, Any], _cells: Any) -> None:
            first_landform_cell(world, "stable_lowland")["landform"] = "alluvial_fan"

        def coastal_plain_landform(world: dict[str, Any], _cells: Any) -> None:
            first_landform_cell(world, "stable_lowland")["landform"] = "coastal_plain"

        for name, mutation in (
            ("non numeric score_threshold", non_numeric_threshold),
            ("candidate_cell_count mismatch", wrong_candidate_count),
            ("top_settlement_score mismatch", wrong_top_score),
            ("non numeric settlement fertility", non_numeric_record_fertility),
            ("monthly climate is not a list", monthly_climate_not_a_list),
            ("alluvial fan score adjustment", alluvial_fan_landform),
            ("coastal plain score adjustment", coastal_plain_landform),
        ):
            with self.subTest(name):
                self.assert_tamper_rejected(
                    "small_smoke", mutation, SETTLEMENT_FAILURE
                )

    def test_settlement_type_reclassification_violations(self) -> None:
        def mining_resource(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            # `resource` never feeds the native score, so selection still replays
            # and only the settlement type mirror changes.
            settlement_cell(world, cells, "frontier_town")[
                "resource"
            ] = "placer_metals"

        def desert_oasis(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            settlement_cell(world, cells, "frontier_town")["biome"] = "hot_desert"

        for name, mutation in (
            ("mining resource retypes the settlement", mining_resource),
            ("desert biome retypes the settlement", desert_oasis),
        ):
            with self.subTest(name):
                self.assert_tamper_rejected(
                    "small_smoke", mutation, SETTLEMENT_FAILURE
                )


class RouteNetworkValidatorTests(ValidatorCliTestCase):
    def test_route_network_model_and_record_violations(self) -> None:
        def non_numeric_links(world: dict[str, Any], _cells: Any) -> None:
            world["route_network_model"]["links_per_settlement"] = "two"

        def wrong_route_count(world: dict[str, Any], _cells: Any) -> None:
            world["route_network_model"]["route_count"] += 5

        def duplicate_settlement_id(world: dict[str, Any], _cells: Any) -> None:
            world["settlements"][0]["id"] = 99

        def missing_settlement_cell(world: dict[str, Any], _cells: Any) -> None:
            world["settlements"][0]["cell_id"] = 99999

        def truncated_position(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            cells[int(world["settlements"][0]["cell_id"])]["position_3d"] = [1.0, 0.0]

        for name, mutation in (
            ("non numeric links_per_settlement", non_numeric_links),
            ("route_count mismatch", wrong_route_count),
            ("settlement ids are not 0..n-1", duplicate_settlement_id),
            ("settlement cell does not exist", missing_settlement_cell),
            ("settlement cell position_3d truncated", truncated_position),
        ):
            with self.subTest(name):
                self.assert_tamper_rejected("small_smoke", mutation, ROUTE_FAILURE)

    def test_negative_route_id_is_rejected(self) -> None:
        def negative_route_id(world: dict[str, Any], _cells: Any) -> None:
            world["routes"][0]["id"] = -1

        self.assert_tamper_rejected(
            "small_smoke", negative_route_id, ROUTE_FAILURE, CORRIDOR_FAILURE
        )

    def test_flat_low_hazard_endpoints_reclassify_routes_as_overland(self) -> None:
        def flatten_endpoints(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            for settlement in world["settlements"]:
                cell = cells[int(settlement["cell_id"])]
                cell["elevation_m"] = 100.0
                cell["boundary_convergent"] = 0.0

        self.assert_tamper_rejected("small_smoke", flatten_endpoints, ROUTE_FAILURE)


class PoliticalRegionValidatorTests(ValidatorCliTestCase):
    def test_region_model_and_record_violations(self) -> None:
        def non_numeric_separation(world: dict[str, Any], _cells: Any) -> None:
            world["political_region_model"][
                "capital_minimum_angular_separation_rad"
            ] = "wide"

        def wrong_target_count(world: dict[str, Any], _cells: Any) -> None:
            world["political_region_model"]["target_count"] += 4

        def non_numeric_region_area(world: dict[str, Any], _cells: Any) -> None:
            world["political_regions"][0]["area_km2"] = "large"

        def negative_route_endpoint(world: dict[str, Any], _cells: Any) -> None:
            world["routes"][0]["from"] = -1

        for name, mutation in (
            ("non numeric capital separation", non_numeric_separation),
            ("target_count mismatch", wrong_target_count),
            ("non numeric region area", non_numeric_region_area),
            ("negative route endpoint", negative_route_endpoint),
        ):
            with self.subTest(name):
                self.assert_tamper_rejected("small_smoke", mutation, REGION_FAILURE)

    def assert_capital_type_maps_to(
        self, key: str, settlement_type: str, region_type: str
    ) -> None:
        """Retype a capital, patch its region record, and expect acceptance.

        Asserting only that the region replay *rejects* a retyped capital would
        pass for any disagreement at all. Patching the stored region record to
        the rung the documented ladder assigns instead makes the region replay
        accept again, so the absent region failure is what pins the mapping: a
        replay that derived any other rung would still reject. The settlement
        mirror necessarily disagrees, which also proves the run reached the
        replay gate rather than crashing before it.
        """

        world = worlds.cached_world(key)
        cells = cells_by_id(world)
        region = world["political_regions"][-1]
        capital = world["settlements"][int(region["capital_settlement_id"])]
        cell = cells[int(capital["cell_id"])]
        # Every rung above the one under test must stay shut for this capital.
        self.assertFalse(bool(cell["is_river"]))
        self.assertNotIn(str(cell["resource"]), MINING_RESOURCES)
        if region_type != "mining_domain":
            self.assertLessEqual(float(cell["elevation_m"]), 1200.0)
            self.assertNotIn(str(cell["landform"]), MOUNTAIN_BORDER_LANDFORMS)
        if region_type == "frontier_territory":
            self.assertLessEqual(float(cell["fertility"]), 0.68)
            self.assertNotEqual(str(cell["resource"]), "fertile_alluvium")

        capital["type"] = settlement_type
        region["type"] = region_type
        exit_code, failures, output = self.run_validate(world)
        self.assertEqual(exit_code, 1, output)
        self.assertIn(SETTLEMENT_FAILURE, failures)
        self.assertNotIn(REGION_FAILURE, failures)

    def test_capital_type_drives_region_type(self) -> None:
        # The small world's last capital sits above the mountain-march
        # elevation, so only the mining rung is reachable there.
        with self.subTest("mining capital"):
            self.assert_capital_type_maps_to(
                "small_smoke", "mining_town", "mining_domain"
            )
        # The mid world's last capital sits below the mountain-march elevation,
        # so it reaches the agrarian and frontier tail of the priority ladder.
        for name, settlement_type, region_type in (
            ("agrarian capital", "agricultural_town", "agrarian_state"),
            ("frontier capital", "frontier_town", "frontier_territory"),
        ):
            with self.subTest(name):
                self.assert_capital_type_maps_to(
                    "mid_512", settlement_type, region_type
                )

    def test_capitals_closer_than_the_separation_are_skipped(self) -> None:
        def pull_capitals_together(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            first = cells[int(world["settlements"][0]["cell_id"])]
            second = cells[int(world["settlements"][1]["cell_id"])]
            blended = [
                0.98 * a + 0.02 * b
                for a, b in zip(first["position_3d"], second["position_3d"])
            ]
            norm = sum(value * value for value in blended) ** 0.5
            second["position_3d"] = [value / norm for value in blended]

        self.assert_tamper_rejected(
            "small_smoke", pull_capitals_together, REGION_FAILURE
        )


class PoliticalBorderValidatorTests(ValidatorCliTestCase):
    def test_border_model_and_record_violations(self) -> None:
        def non_numeric_threshold(world: dict[str, Any], _cells: Any) -> None:
            world["political_border_model"]["mountain_elevation_threshold_m"] = "high"

        def drop_border(world: dict[str, Any], _cells: Any) -> None:
            world["borders"].pop()

        def wrong_border_type(world: dict[str, Any], _cells: Any) -> None:
            world["borders"][0]["type"] = "open_lowland"

        def truncated_border_cell_position(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            cells[int(world["borders"][0]["cell_a"])]["position_3d"] = [1.0, 0.0]

        for name, mutation in (
            ("non numeric mountain threshold", non_numeric_threshold),
            ("dropped border segment", drop_border),
            ("border type mismatch", wrong_border_type),
            ("border cell position_3d truncated", truncated_border_cell_position),
        ):
            with self.subTest(name):
                self.assert_tamper_rejected("small_smoke", mutation, BORDER_FAILURE)

    def test_lowland_border_type_ladder(self) -> None:
        """Every rung below `mountain` for a freshly created border segment.

        Both canonical worlds only ever produce river and mountain borders, so
        the desert, ice, coastal and open-lowland rungs are reached by moving one
        lowland cell into its neighbour's region. The new segment already makes
        the border replay disagree on the segment count, so the assertion pins
        that the border replay is the objector, not which rung it chose - no CLI
        output distinguishes the rungs.
        """

        def reassign(
            extra: Callable[[dict[str, Any]], None] | None = None
        ) -> Mutation:
            def mutation(
                world: dict[str, Any], cells: dict[int, dict[str, Any]]
            ) -> None:
                cell = lowland_pair_cell(world, cells)
                region_count = len(world["political_regions"])
                cell["political_region_id"] = (
                    0
                    if int(cell["political_region_id"]) != 0
                    else min(1, region_count - 1)
                )
                if extra is not None:
                    extra(cell)

            return mutation

        def make_desert(cell: dict[str, Any]) -> None:
            cell["biome"] = "hot_desert"

        def make_ice(cell: dict[str, Any]) -> None:
            cell["landform"] = "ice_field"

        def make_coastal(cell: dict[str, Any]) -> None:
            cell["landform"] = "coastal_plain"

        for name, extra in (
            ("open lowland border", None),
            ("desert border", make_desert),
            ("ice border", make_ice),
            ("coastal border", make_coastal),
        ):
            with self.subTest(name):
                self.assert_tamper_rejected("mid_512", reassign(extra), BORDER_FAILURE)


class TradeFlowValidatorTests(ValidatorCliTestCase):
    def test_trade_flow_record_violations(self) -> None:
        def non_numeric_friction(world: dict[str, Any], _cells: Any) -> None:
            world["trade_flows"][0]["friction"] = "slow"

        def wrong_primary_good(world: dict[str, Any], _cells: Any) -> None:
            world["trade_flows"][0]["primary_good"] = "obsidian"

        def unknown_route_endpoint(world: dict[str, Any], _cells: Any) -> None:
            world["routes"][0]["from"] = 999

        for name, mutation in (
            ("non numeric flow friction", non_numeric_friction),
            ("primary good mismatch", wrong_primary_good),
            ("route endpoint is not a settlement", unknown_route_endpoint),
        ):
            with self.subTest(name):
                self.assert_tamper_rejected("small_smoke", mutation, TRADE_FAILURE)

    def test_primary_good_falls_back_when_no_endpoint_resource(self) -> None:
        """Each fallback rung once the endpoints carry no tradeable resource.

        The stripped resource already makes the flow replay disagree, so like the
        border ladder these pin the objecting validator rather than the selected
        good: the good is only visible inside the flow record the replay rebuilds.
        """

        def strip_resources(port_endpoint: bool, fertile: bool) -> Mutation:
            def mutation(
                world: dict[str, Any], cells: dict[int, dict[str, Any]]
            ) -> None:
                for route in world["routes"]:
                    first = world["settlements"][int(route["from"])]
                    second = world["settlements"][int(route["to"])]
                    is_port_route = "port" in {first["type"], second["type"]}
                    if is_port_route is not port_endpoint:
                        continue
                    for settlement in (first, second):
                        cell = cells[int(settlement["cell_id"])]
                        cell["resource"] = "none"
                        if not fertile:
                            cell["fertility"] = 0.5
                    return
                raise LookupError("no matching route")

            return mutation

        for name, mutation in (
            ("coastal fisheries fallback", strip_resources(True, True)),
            ("fertile alluvium fallback", strip_resources(False, True)),
            ("no primary good at all", strip_resources(False, False)),
        ):
            with self.subTest(name):
                self.assert_tamper_rejected("small_smoke", mutation, TRADE_FAILURE)


class RouteCorridorValidatorTests(ValidatorCliTestCase):
    def test_corridor_model_and_record_violations(self) -> None:
        def non_numeric_radius(world: dict[str, Any], _cells: Any) -> None:
            world["route_corridor_model"]["planet_radius_km"] = "wide"

        def drop_corridor(world: dict[str, Any], _cells: Any) -> None:
            world["route_corridors"].pop()

        def wrong_corridor_count(world: dict[str, Any], _cells: Any) -> None:
            world["route_corridor_model"]["corridor_count"] += 6

        def wrong_summary_count(world: dict[str, Any], _cells: Any) -> None:
            world["summary"]["route_corridor_count"] += 6

        def wrong_route_corridor_type(world: dict[str, Any], _cells: Any) -> None:
            world["routes"][0]["route_corridor_type"] = "not_a_corridor"

        for name, mutation in (
            ("non numeric planet_radius_km", non_numeric_radius),
            ("dropped corridor record", drop_corridor),
            ("corridor_count mismatch", wrong_corridor_count),
            ("summary route_corridor_count mismatch", wrong_summary_count),
            ("route corridor type mismatch", wrong_route_corridor_type),
        ):
            with self.subTest(name):
                self.assert_tamper_rejected("small_smoke", mutation, CORRIDOR_FAILURE)

    def test_corridor_path_shape_violations(self) -> None:
        def overland_route_type(world: dict[str, Any], _cells: Any) -> None:
            world["routes"][0]["type"] = "overland"

        def self_looping_route(world: dict[str, Any], _cells: Any) -> None:
            world["routes"][0]["to"] = world["routes"][0]["from"]

        def isolated_endpoint(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            cells[int(world["settlements"][0]["cell_id"])]["neighbors"] = []

        def missing_endpoint_cell(world: dict[str, Any], _cells: Any) -> None:
            world["settlements"][0]["cell_id"] = 99999

        for name, mutation in (
            ("overland movement costs", overland_route_type),
            ("self looping route", self_looping_route),
            ("endpoint with no neighbours", isolated_endpoint),
            ("endpoint cell does not exist", missing_endpoint_cell),
        ):
            with self.subTest(name):
                self.assert_tamper_rejected("small_smoke", mutation, CORRIDOR_FAILURE)

    def test_flat_neighbourhood_has_no_mountain_pass_index(self) -> None:
        def flatten_neighbourhood(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            for cell in world["cells"]:
                if cell["is_water"]:
                    continue
                if cell["landform"] in MOUNTAIN_CORRIDOR_LANDFORMS:
                    continue
                land = [
                    cells[int(neighbor_id)]
                    for neighbor_id in cell["neighbors"]
                    if not cells[int(neighbor_id)]["is_water"]
                ]
                if not land:
                    continue
                cell["boundary_convergent"] = 0.0
                for neighbor in land:
                    neighbor["elevation_m"] = 700.0
                return
            raise LookupError("no land cell with land neighbours")

        self.assert_tamper_rejected(
            "small_smoke", flatten_neighbourhood, CORRIDOR_FAILURE
        )


class NeighbourShapeViolationTests(ValidatorCliTestCase):
    def test_non_list_land_neighbours_reject_every_human_geography_model(self) -> None:
        def mapping_neighbours(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            # A mapping keyed by the same ids still iterates in neighbour order
            # for the rest of the gate, so only the strict list guards fire.
            cell = cells[int(world["settlements"][0]["cell_id"])]
            cell["neighbors"] = {
                str(neighbor_id): 0 for neighbor_id in cell["neighbors"]
            }

        self.assert_tamper_rejected(
            "small_smoke",
            mapping_neighbours,
            REGION_FAILURE,
            BORDER_FAILURE,
            SETTLEMENT_FAILURE,
            PORT_FAILURE,
            CORRIDOR_FAILURE,
        )

    def test_non_list_marine_neighbours_reject_ports_and_corridors(self) -> None:
        def mapping_marine_neighbours(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            for cell in world["cells"]:
                if cell["water_body_type"] not in MARINE_WATER_TYPES:
                    continue
                # A lower-id land neighbour is replayed first, so its enclosure
                # term sees the mapping before the water cell itself fails.
                earlier_land = [
                    cells[int(neighbor_id)]
                    for neighbor_id in cell["neighbors"]
                    if int(neighbor_id) < int(cell["id"])
                    and not cells[int(neighbor_id)]["is_water"]
                ]
                if not earlier_land:
                    continue
                cell["neighbors"] = {
                    str(neighbor_id): 0 for neighbor_id in cell["neighbors"]
                }
                return
            raise LookupError("no marine cell with an earlier land neighbour")

        self.assert_tamper_rejected(
            "small_smoke",
            mapping_marine_neighbours,
            PORT_FAILURE,
            CORRIDOR_FAILURE,
        )

    def test_marine_cell_with_only_unknown_neighbours_rejects_ports(self) -> None:
        """Unresolvable neighbour ids leave a marine cell with no land contact.

        ``validate`` walks the same records with its own accessors, but this one
        survives them: the run reaches the replay gate and prints the port
        failure, so the guard is reachable from the CLI and does not need the
        direct-call escape hatch below.
        """

        def orphan_marine_cell(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            for cell in world["cells"]:
                if cell["water_body_type"] not in MARINE_WATER_TYPES:
                    continue
                if not any(
                    not cells[int(neighbor_id)]["is_water"]
                    for neighbor_id in cell["neighbors"]
                ):
                    continue
                cell["neighbors"] = [99999]
                return
            raise LookupError("no marine cell with a land neighbour")

        self.assert_tamper_rejected("small_smoke", orphan_marine_cell, PORT_FAILURE)


class NominalTimeRecordTests(ValidatorCliTestCase):
    """The nominal-interval helper shared by the maturation history replays.

    It is reached through the hydrologic water budget history, so these assert
    that validator's failure text rather than a human-geography one.
    """

    def test_nominal_interval_record_violations(self) -> None:
        def drop_nominal_field(world: dict[str, Any], _cells: Any) -> None:
            world["hydrologic_water_budget_history"][0].pop("nominal_elapsed_time_ma")

        def wrong_nominal_unit(world: dict[str, Any], _cells: Any) -> None:
            world["hydrologic_water_budget_history"][0]["nominal_time_unit"] = "Myr"

        def non_numeric_interval_start(world: dict[str, Any], _cells: Any) -> None:
            world["hydrologic_water_budget_history"][0][
                "nominal_interval_start_ma"
            ] = "early"

        def shifted_interval_start(world: dict[str, Any], _cells: Any) -> None:
            world["hydrologic_water_budget_history"][0][
                "nominal_interval_start_ma"
            ] = 5.0

        for name, mutation in (
            ("missing nominal interval field", drop_nominal_field),
            ("nominal time unit is not Ma", wrong_nominal_unit),
            ("non numeric nominal interval start", non_numeric_interval_start),
            ("shifted nominal interval start", shifted_interval_start),
        ):
            with self.subTest(name):
                # One history record is wrong, so the water budget replay must
                # be the only domain that objects.
                self.assert_tamper_is_sole_failure(
                    "small_smoke", mutation, HYDROLOGY_FAILURE
                )


class UnreachableThroughCliGuardTests(TestCase):
    """Guards that `validate` can never reach, exercised on the validators.

    ``magic-geo validate`` re-reads the same cells with its own unguarded
    accessors, so every tamper below aborts the command before the collected
    failures are echoed: a non-dict record and an unknown neighbour id raise
    ``AttributeError``/``KeyError``, a non-numeric record or cell field raises
    ``ValueError``, and a non-positive radius is refused by the planet-parameter
    gate with its own message. Through the CLI they would all be indistinguishable
    from a crash, so these call the validators directly and assert the exact
    returned failure list; the payload is still a real generated world with a
    single tamper.
    """

    def world(self) -> tuple[dict[str, Any], dict[str, Any], dict[int, dict[str, Any]]]:
        world = worlds.cached_world("small_smoke")
        return world, world["summary"], cells_by_id(world)

    def assert_replay_failure(
        self, validator: Any, message: str, mutation: Mutation
    ) -> None:
        world, summary, cells = self.world()
        mutation(world, cells)
        self.assertEqual(validator(world, summary, cells), [message])

    def test_untampered_world_replays_cleanly(self) -> None:
        for name, validator in (
            ("ports", _validate_port_sites),
            ("corridors", _validate_route_corridors),
            ("settlement", _validate_settlement_selection),
            ("route network", _validate_route_network),
            ("political regions", _validate_political_regions),
            ("political borders", _validate_political_borders),
        ):
            with self.subTest(name):
                world, summary, cells = self.world()
                self.assertEqual(validator(world, summary, cells), [])

    def test_non_dict_records_are_rejected(self) -> None:
        def replace_settlement(world: dict[str, Any], _cells: Any) -> None:
            world["settlements"][0] = "not a settlement"

        def replace_route(world: dict[str, Any], _cells: Any) -> None:
            world["routes"][0] = "not a route"

        for name, validator, message, mutation in (
            ("ports/settlement", _validate_port_sites, PORT_FAILURE, replace_settlement),
            ("ports/route", _validate_port_sites, PORT_FAILURE, replace_route),
            (
                "corridors/settlement",
                _validate_route_corridors,
                CORRIDOR_FAILURE,
                replace_settlement,
            ),
            (
                "corridors/route",
                _validate_route_corridors,
                CORRIDOR_FAILURE,
                replace_route,
            ),
            (
                "settlement/settlement",
                _validate_settlement_selection,
                SETTLEMENT_FAILURE,
                replace_settlement,
            ),
        ):
            with self.subTest(name):
                self.assert_replay_failure(validator, message, mutation)

    def test_non_numeric_cell_fields_are_rejected(self) -> None:
        def flow_accumulation(world: dict[str, Any], cells: Any) -> None:
            cells[0]["flow_accumulation"] = "torrential"

        def port_site_id(world: dict[str, Any], cells: Any) -> None:
            cells[0]["port_site_id"] = "first"

        def route_corridor_id(world: dict[str, Any], cells: Any) -> None:
            cells[0]["route_corridor_id"] = "first"

        def border_length(world: dict[str, Any], _cells: Any) -> None:
            world["borders"][0]["length_km"] = "far"

        def route_cost(world: dict[str, Any], _cells: Any) -> None:
            world["routes"][0]["cost"] = "expensive"

        def settlement_region(world: dict[str, Any], _cells: Any) -> None:
            world["settlements"][0]["region_id"] = "north"

        for name, validator, message, mutation in (
            ("ports flow", _validate_port_sites, PORT_FAILURE, flow_accumulation),
            ("ports site id", _validate_port_sites, PORT_FAILURE, port_site_id),
            (
                "corridors flow",
                _validate_route_corridors,
                CORRIDOR_FAILURE,
                flow_accumulation,
            ),
            (
                "corridors corridor id",
                _validate_route_corridors,
                CORRIDOR_FAILURE,
                route_corridor_id,
            ),
            (
                "border length",
                _validate_political_borders,
                BORDER_FAILURE,
                border_length,
            ),
            ("route cost", _validate_route_network, ROUTE_FAILURE, route_cost),
            (
                "settlement region id",
                _validate_political_regions,
                REGION_FAILURE,
                settlement_region,
            ),
        ):
            with self.subTest(name):
                self.assert_replay_failure(validator, message, mutation)

    def test_unknown_neighbour_ids_are_rejected(self) -> None:
        def add_unknown_neighbour(
            world: dict[str, Any], cells: dict[int, dict[str, Any]]
        ) -> None:
            for cell in world["cells"]:
                if not cell["is_water"] and int(cell["political_region_id"]) >= 0:
                    cell["neighbors"] = [*cell["neighbors"], 99999]
                    return
            raise LookupError("no land cell in a region")

        for name, validator, message in (
            ("political regions", _validate_political_regions, REGION_FAILURE),
            ("political borders", _validate_political_borders, BORDER_FAILURE),
            ("settlement", _validate_settlement_selection, SETTLEMENT_FAILURE),
        ):
            with self.subTest(name):
                self.assert_replay_failure(validator, message, add_unknown_neighbour)

        # The corridor search simply skips neighbours it cannot resolve.
        world, summary, cells = self.world()
        add_unknown_neighbour(world, cells)
        self.assertEqual(_validate_route_corridors(world, summary, cells), [])

    def test_non_positive_planet_radius_is_rejected(self) -> None:
        def zero_radius(world: dict[str, Any], _cells: Any) -> None:
            world["planet_parameters"]["radius_km"] = 0.0

        for name, validator, message in (
            ("political regions", _validate_political_regions, REGION_FAILURE),
            ("political borders", _validate_political_borders, BORDER_FAILURE),
            ("route network", _validate_route_network, ROUTE_FAILURE),
        ):
            with self.subTest(name):
                self.assert_replay_failure(validator, message, zero_radius)

    def test_empty_cell_table_is_rejected(self) -> None:
        """An empty cell table must be refused rather than divided by.

        Both validators average their indices over the cell count when they
        build the expected summary, so with the guard removed these calls would
        raise ``ZeroDivisionError`` instead of returning a failure list: the
        equality below is what separates the two outcomes. The record and model
        counts are zeroed so that every earlier check passes and the empty table
        is the last disagreement left.
        """

        world, summary, cells = self.world()
        self.assertEqual(_validate_port_sites(world, summary, cells), [])
        world["port_sites"] = []
        world["port_site_model"]["candidate_cell_count"] = 0
        world["port_site_model"]["site_count"] = 0
        cells.clear()
        self.assertEqual(
            _validate_port_sites(world, summary, cells), [PORT_FAILURE]
        )

        world, summary, cells = self.world()
        self.assertEqual(_validate_route_corridors(world, summary, cells), [])
        world["route_corridors"] = []
        world["routes"] = []
        world["route_corridor_model"]["route_count"] = 0
        world["route_corridor_model"]["corridor_count"] = 0
        cells.clear()
        self.assertEqual(
            _validate_route_corridors(world, summary, cells), [CORRIDOR_FAILURE]
        )
