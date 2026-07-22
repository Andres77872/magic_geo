"""Replay validation for the deterministic market-clearing model.

``validate_market_clearing_replay`` recomputes the whole route-capacity /
agent-order / price-iteration / inventory-learning chain from the payload and
compares it record by record against what the generator emitted.  A clean world
therefore replays to an empty message list, and any single divergence collapses
to one fixed failure string.

Hand-building a passing payload is infeasible, so the happy path uses the shared
128-cell replay world and every failure case starts from a private deep copy of
that same world with exactly one field tampered.

Two traps this file pins down explicitly, because both make "obvious" tampers
silently vacuous:

* ``firm_agents`` and ``household_cohorts`` are re-derived from the population /
  economy layers rather than read, so emptying or editing them is *not* detected
  here (see ``test_recomputed_agent_layer_is_out_of_scope``).  Only their
  list-ness is gated.
* record comparison is *containment*, not equality, so adding an unknown key to
  an emitted record is ignored.  The ``market_clearing_model`` block is the one
  place compared with ``==``, so an extra key there does fail.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest import TestCase

from support import worlds

from magic_geo.demographic_agents_validation import validate_demographic_agents_replay
from magic_geo.market_clearing_validation import (
    MARKET_CLEARING_MODEL,
    validate_market_clearing_replay,
)

#: The single message every failure mode collapses to.
FAILURE = "market clearing model or causal replay invalid"

#: Payload keys the validator requires to be lists before it replays anything.
REQUIRED_LISTS = (
    "routes",
    "market_exchanges",
    "logistics_networks",
    "firm_agents",
    "household_cohorts",
    "route_capacity_constraints",
    "market_clearing_records",
    "market_agent_orders",
    "market_price_iterations",
    "market_inventory_histories",
)

#: Required lists whose *contents* reach the replay, so emptying them diverges.
#: ``firm_agents`` / ``household_cohorts`` are deliberately absent: they are
#: recomputed, so ``payload[key] = []`` still replays clean.
EMPTYABLE_LISTS = (
    "routes",
    "market_exchanges",
    "logistics_networks",
    "route_capacity_constraints",
    "market_clearing_records",
    "market_agent_orders",
    "market_price_iterations",
    "market_inventory_histories",
)

#: The replayed ledgers hanging off every clearing record, with a numeric field
#: of each that the replay recomputes exactly.
LEDGER_FIELDS = (
    ("route_capacity_constraints", "capacity_volume_index"),
    ("market_agent_orders", "limit_price_index"),
    ("market_price_iterations", "price_index"),
    ("market_inventory_histories", "mean_inventory_pressure_index"),
)

#: Summary aggregates derived from the replayed ledgers.
SUMMARY_AGGREGATES = (
    "route_capacity_constraint_count",
    "market_clearing_record_count",
    "market_agent_order_count",
    "market_price_iteration_count",
    "market_inventory_history_count",
    "market_inventory_step_count",
    "producer_market_order_count",
    "consumer_market_order_count",
    "constrained_market_exchange_count",
    "total_market_requested_volume_index",
    "total_market_cleared_volume_index",
    "total_market_unmet_demand_index",
    "total_endogenous_market_supply_index",
    "total_endogenous_market_demand_index",
    "mean_market_clearance_fraction",
    "mean_route_capacity_utilization_index",
    "mean_market_price_adjustment_index",
    "mean_market_rationing_index",
    "mean_market_equilibrium_residual_index",
    "mean_market_inventory_gap_index",
    "mean_market_learning_rate_index",
    "mean_market_inventory_pressure_index",
    "high_inventory_stress_market_count",
)

#: Clearing annotations the replay writes back onto ``routes``.
ROUTE_ANNOTATIONS = (
    "route_capacity_constraint_id",
    "market_capacity_volume_index",
    "market_capacity_utilization_index",
)

#: Clearing annotations the replay writes back onto ``market_exchanges``.
EXCHANGE_ANNOTATIONS = (
    "market_clearing_record_id",
    "cleared_volume_index",
    "unmet_demand_index",
    "clearance_fraction",
    "market_inventory_history_id",
)

#: The price/inventory loop is a fixed three-round interpolation per exchange.
CLEARING_ROUNDS = 3


class MarketClearingReplayValidationTests(TestCase):
    """``validate_market_clearing_replay`` on the 128-cell replay world."""

    def _tampered(self, mutate: Callable[[dict[str, Any]], None]) -> list[str]:
        """Apply ``mutate`` to a private copy of the replay world and validate."""
        world = worlds.cached_world("replay_128")
        mutate(world)
        return validate_market_clearing_replay(world)

    def test_untampered_replay_world_passes(self) -> None:
        """The generated world replays clean, and copying it changes nothing."""
        shared = worlds.cached_world_readonly("replay_128")
        self.assertEqual(validate_market_clearing_replay(shared), [])
        # Anchors every failure case below: the unmodified deep copy the
        # tampers start from is itself accepted, so a returned FAILURE can only
        # come from the tamper.
        self.assertEqual(
            validate_market_clearing_replay(worlds.cached_world("replay_128")), []
        )
        self.assertEqual(
            shared["summary"]["market_clearing_model"], MARKET_CLEARING_MODEL
        )

    def test_replay_ledgers_are_populated_and_agree_with_the_summary(self) -> None:
        """The fixture the tampers bite on is non-empty and internally consistent.

        Independent of the validator: every ledger the tampers index into must
        exist, the summary counts must equal the ledger lengths they claim to
        count, and the price/inventory loop must run exactly three rounds per
        clearing record (the model is a fixed three-step interpolation).
        """
        world = worlds.cached_world_readonly("replay_128")
        summary = world["summary"]
        counts = {
            "route_capacity_constraint_count": "route_capacity_constraints",
            "market_clearing_record_count": "market_clearing_records",
            "market_agent_order_count": "market_agent_orders",
            "market_price_iteration_count": "market_price_iterations",
            "market_inventory_history_count": "market_inventory_histories",
        }
        for summary_key, ledger in counts.items():
            with self.subTest(ledger=ledger):
                self.assertGreater(len(world[ledger]), 0)
                self.assertEqual(summary[summary_key], len(world[ledger]))

        records = world["market_clearing_records"]
        self.assertEqual(
            len(world["market_price_iterations"]), CLEARING_ROUNDS * len(records)
        )
        self.assertEqual(len(world["market_inventory_histories"]), len(records))
        self.assertEqual(
            summary["market_inventory_step_count"], CLEARING_ROUNDS * len(records)
        )
        for record in records:
            with self.subTest(record=record["id"]):
                self.assertEqual(record["price_iteration_count"], CLEARING_ROUNDS)
                self.assertEqual(len(record["price_iteration_ids"]), CLEARING_ROUNDS)
                self.assertEqual(
                    record["agent_order_count"], len(record["agent_order_ids"])
                )
        by_id = {
            int(item["id"]): item for item in world["market_price_iterations"]
        }
        for record in records:
            rounds = [by_id[i]["iteration_index"] for i in record["price_iteration_ids"]]
            with self.subTest(record=record["id"], field="iteration_index"):
                self.assertEqual(rounds, list(range(1, CLEARING_ROUNDS + 1)))
        for history in world["market_inventory_histories"]:
            with self.subTest(history=history["id"]):
                self.assertEqual(history["step_count"], CLEARING_ROUNDS)
                self.assertEqual(len(history["steps"]), CLEARING_ROUNDS)
                self.assertEqual(
                    [step["sequence_index"] for step in history["steps"]],
                    list(range(CLEARING_ROUNDS)),
                )

    def test_record_ledger_tampers_are_detected(self) -> None:
        """Editing, dropping or adding any replayed record trips the validator."""

        def set_price(world: dict[str, Any]) -> None:
            world["market_clearing_records"][0]["equilibrium_price_index"] = 0.5

        def zero_cleared_volume(world: dict[str, Any]) -> None:
            world["market_clearing_records"][0]["cleared_volume_index"] = 0.0

        def drop_field(world: dict[str, Any]) -> None:
            del world["market_clearing_records"][0]["equilibrium_price_index"]

        def append_record(world: dict[str, Any]) -> None:
            world["market_clearing_records"].append({"id": 9999})

        def clear_records(world: dict[str, Any]) -> None:
            world["market_clearing_records"] = []

        def swap_history_link(world: dict[str, Any]) -> None:
            # Point record 1 at record 0's inventory history.
            records = world["market_clearing_records"]
            self.assertNotEqual(
                records[1]["market_inventory_history_id"],
                records[0]["market_inventory_history_id"],
            )
            records[1]["market_inventory_history_id"] = records[0][
                "market_inventory_history_id"
            ]

        def drop_order_ids(world: dict[str, Any]) -> None:
            world["market_clearing_records"][0]["agent_order_ids"] = []

        def reverse_iteration_ids(world: dict[str, Any]) -> None:
            record = world["market_clearing_records"][0]
            record["price_iteration_ids"] = list(reversed(record["price_iteration_ids"]))

        cases = (
            ("equilibrium_price_index rewritten", set_price),
            ("cleared_volume_index zeroed", zero_cleared_volume),
            ("equilibrium_price_index removed", drop_field),
            ("extra record appended", append_record),
            ("all records removed", clear_records),
            ("market_inventory_history_id cross-linked", swap_history_link),
            ("agent_order_ids emptied", drop_order_ids),
            ("price_iteration_ids reordered", reverse_iteration_ids),
        )
        for label, mutate in cases:
            with self.subTest(tamper=label):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_ledger_identity_tampers_are_detected(self) -> None:
        """Emptying or renumbering any dependent ledger diverges from the replay."""
        ledgers = (
            "route_capacity_constraints",
            "market_agent_orders",
            "market_price_iterations",
            "market_inventory_histories",
        )
        for name in ledgers:
            with self.subTest(ledger=name, tamper="emptied"):
                self.assertEqual(
                    self._tampered(lambda world, n=name: world.__setitem__(n, [])),
                    [FAILURE],
                )
            with self.subTest(ledger=name, tamper="first id renumbered"):
                self.assertEqual(
                    self._tampered(
                        lambda world, n=name: world[n][0].__setitem__("id", 4242)
                    ),
                    [FAILURE],
                )

    def test_ledger_value_tampers_are_detected(self) -> None:
        """Each ledger's recomputed numbers are compared, not just its identity.

        ``+ 1.0`` guarantees the written value differs from the emitted one, so
        none of these tampers can degenerate into a no-op.
        """

        def bump(world: dict[str, Any], ledger: str, field: str) -> None:
            record = world[ledger][0]
            record[field] = float(record[field]) + 1.0

        for ledger, field in LEDGER_FIELDS:
            with self.subTest(ledger=ledger, field=field):
                self.assertEqual(
                    self._tampered(
                        lambda world, le=ledger, fi=field: bump(world, le, fi)
                    ),
                    [FAILURE],
                )

        def nested_step_value(world: dict[str, Any]) -> None:
            step = world["market_inventory_histories"][0]["steps"][1]
            step["learning_rate_index"] = float(step["learning_rate_index"]) + 1.0

        def nested_step_dropped(world: dict[str, Any]) -> None:
            world["market_inventory_histories"][0]["steps"].pop()

        def nested_order_ids(world: dict[str, Any]) -> None:
            world["market_price_iterations"][0]["order_ids"] = []

        def order_side_flipped(world: dict[str, Any]) -> None:
            order = world["market_agent_orders"][0]
            self.assertEqual(order["order_side"], "supply")
            order["order_side"] = "demand"

        def constraint_route_type(world: dict[str, Any]) -> None:
            constraint = world["route_capacity_constraints"][0]
            self.assertNotEqual(constraint["route_type"], "desert_track")
            constraint["route_type"] = "desert_track"

        nested = (
            ("inventory steps[1].learning_rate_index", nested_step_value),
            ("inventory steps truncated", nested_step_dropped),
            ("price iteration order_ids emptied", nested_order_ids),
            ("agent order side flipped", order_side_flipped),
            ("constraint route_type rewritten", constraint_route_type),
        )
        for label, mutate in nested:
            with self.subTest(tamper=label):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_required_list_shape_tampers_are_detected(self) -> None:
        """A missing or non-list required key fails before any replay."""
        for name in REQUIRED_LISTS:
            with self.subTest(key=name, tamper="removed"):
                self.assertEqual(
                    self._tampered(lambda world, n=name: world.pop(n)), [FAILURE]
                )
            with self.subTest(key=name, tamper="not a list"):
                self.assertEqual(
                    self._tampered(lambda world, n=name: world.__setitem__(n, {})),
                    [FAILURE],
                )
        # Emptying a required list only diverges when the replay actually reads
        # it; see ``test_recomputed_agent_layer_is_out_of_scope`` for the two
        # keys missing from ``EMPTYABLE_LISTS``.
        self.assertEqual(len(EMPTYABLE_LISTS), len(REQUIRED_LISTS) - 2)
        for name in EMPTYABLE_LISTS:
            with self.subTest(key=name, tamper="emptied"):
                self.assertEqual(
                    self._tampered(lambda world, n=name: world.__setitem__(n, [])),
                    [FAILURE],
                )

    def test_summary_aggregate_tampers_are_detected(self) -> None:
        """Every summary aggregate the replay derives is compared, and required.

        Rewriting a count to ``count + 1`` and a ratio to ``value + 1.0`` cannot
        collide with the emitted value, and removing the key must fail too since
        the validator compares ``summary.get(key)`` against the expected value.
        """
        world = worlds.cached_world_readonly("replay_128")
        for key in SUMMARY_AGGREGATES:
            emitted = world["summary"][key]
            self.assertIsInstance(emitted, (int, float))
            replacement = (
                int(emitted) + 1 if isinstance(emitted, int) else float(emitted) + 1.0
            )
            with self.subTest(aggregate=key, tamper="rewritten"):
                self.assertEqual(
                    self._tampered(
                        lambda w, k=key, v=replacement: w["summary"].__setitem__(k, v)
                    ),
                    [FAILURE],
                )
        # ``summary.get(key)`` returns ``None`` for a dropped aggregate, which is
        # the same comparison path for every key; one count and one mean cover it.
        for key in ("market_clearing_record_count", "mean_market_clearance_fraction"):
            with self.subTest(aggregate=key, tamper="removed"):
                self.assertEqual(
                    self._tampered(lambda w, k=key: w["summary"].pop(k)), [FAILURE]
                )

    def test_model_declaration_tampers_are_detected(self) -> None:
        """The model block is compared with ``==``: every key and value counts."""

        def summary_model(world: dict[str, Any]) -> None:
            world["summary"]["market_clearing_model"] = "bogus"

        def summary_model_removed(world: dict[str, Any]) -> None:
            del world["summary"]["market_clearing_model"]

        def top_level_model(world: dict[str, Any]) -> None:
            world["market_clearing_model"] = "bogus"

        def model_sub_key(world: dict[str, Any]) -> None:
            world["market_clearing_model"]["clearing_model"] = "bogus"

        def model_flag(world: dict[str, Any]) -> None:
            world["market_clearing_model"]["deterministic"] = False

        def model_key_removed(world: dict[str, Any]) -> None:
            del world["market_clearing_model"]["model_limitation"]

        def model_key_added(world: dict[str, Any]) -> None:
            world["market_clearing_model"]["unexpected_model"] = "extra"

        cases = (
            ("summary.market_clearing_model", summary_model),
            ("summary.market_clearing_model removed", summary_model_removed),
            ("payload.market_clearing_model", top_level_model),
            ("market_clearing_model.clearing_model", model_sub_key),
            ("market_clearing_model.deterministic", model_flag),
            ("market_clearing_model.model_limitation removed", model_key_removed),
            ("market_clearing_model extra key", model_key_added),
        )
        for label, mutate in cases:
            with self.subTest(tamper=label):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_route_and_exchange_backreference_tampers_are_detected(self) -> None:
        """Clearing annotations written back onto routes/exchanges are checked."""

        def rewrite(world: dict[str, Any], collection: str, key: str) -> None:
            record = world[collection][0]
            value = record[key]
            record[key] = value + 1 if isinstance(value, int) else float(value) + 1.0

        def remove(world: dict[str, Any], collection: str, key: str) -> None:
            del world[collection][0][key]

        annotated = (
            ("routes", ROUTE_ANNOTATIONS),
            ("market_exchanges", EXCHANGE_ANNOTATIONS),
        )
        for collection, keys in annotated:
            for key in keys:
                with self.subTest(target=f"{collection}[0].{key}", tamper="rewritten"):
                    self.assertEqual(
                        self._tampered(
                            lambda w, c=collection, k=key: rewrite(w, c, k)
                        ),
                        [FAILURE],
                    )
                with self.subTest(target=f"{collection}[0].{key}", tamper="removed"):
                    self.assertEqual(
                        self._tampered(lambda w, c=collection, k=key: remove(w, c, k)),
                        [FAILURE],
                    )

        def route_id_renumbered(world: dict[str, Any]) -> None:
            # The annotation is looked up by route id, so an unknown id is a
            # missing annotation rather than a mismatched one.
            world["routes"][0]["id"] = 4242

        def exchange_id_renumbered(world: dict[str, Any]) -> None:
            world["market_exchanges"][0]["id"] = 4242

        for label, mutate in (
            ("routes[0].id", route_id_renumbered),
            ("market_exchanges[0].id", exchange_id_renumbered),
        ):
            with self.subTest(target=label, tamper="renumbered"):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_route_inputs_are_replayed_not_trusted(self) -> None:
        """Capacity is recomputed from route geometry, not read back off the route.

        Each of these edits leaves every emitted record untouched; the validator
        can only notice because it re-derives the capacity constraint from the
        route's own mode, distance and cost.
        """

        def distance(world: dict[str, Any]) -> None:
            route = world["routes"][0]
            route["distance_km"] = float(route["distance_km"]) * 2.0 + 1.0

        def cost(world: dict[str, Any]) -> None:
            route = world["routes"][0]
            route["cost"] = float(route["cost"]) * 5.0 + 100.0

        def mode(world: dict[str, Any]) -> None:
            route = world["routes"][0]
            # ``desert_track`` has its own capacity multiplier; guard against a
            # world that already uses it, which would make this a no-op.
            self.assertNotEqual(route["type"], "desert_track")
            route["type"] = "desert_track"

        cases = (
            ("routes[0].distance_km", distance),
            ("routes[0].cost", cost),
            ("routes[0].type", mode),
        )
        for label, mutate in cases:
            with self.subTest(tamper=label):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_recomputed_agent_layer_is_out_of_scope(self) -> None:
        """``firm_agents`` / ``household_cohorts`` are re-derived, so not compared.

        This validator rebuilds the agent layer from the population and economy
        layers, so corrupting the emitted agents cannot make it fail — only the
        ``isinstance(..., list)`` gate looks at those keys at all.  Pinning that
        here stops anyone from writing a silently vacuous "emptied the list"
        tamper for them; the corruption *is* caught, by the demographic-agent
        replay validator, which is asserted alongside.
        """

        def empty_firms(world: dict[str, Any]) -> None:
            world["firm_agents"] = []

        def empty_cohorts(world: dict[str, Any]) -> None:
            world["household_cohorts"] = []

        def edit_firm(world: dict[str, Any]) -> None:
            firm = world["firm_agents"][0]
            firm["output_index"] = float(firm["output_index"]) * 3.0 + 1.0

        def edit_cohort(world: dict[str, Any]) -> None:
            cohort = world["household_cohorts"][0]
            cohort["population"] = float(cohort["population"]) * 3.0 + 1.0

        cases = (
            ("firm_agents emptied", empty_firms),
            ("household_cohorts emptied", empty_cohorts),
            ("firm_agents[0].output_index", edit_firm),
            ("household_cohorts[0].population", edit_cohort),
        )
        for label, mutate in cases:
            with self.subTest(tamper=label):
                self.assertEqual(self._tampered(mutate), [])
                world = worlds.cached_world("replay_128")
                mutate(world)
                self.assertEqual(
                    validate_demographic_agents_replay(world),
                    ["demographic agent or individual life-event causal replay invalid"],
                )

    def test_unknown_record_keys_are_ignored(self) -> None:
        """Record comparison is containment: extra emitted keys do not fail.

        The counterpart of ``test_model_declaration_tampers_are_detected``'s
        extra-key case, which *does* fail because the model block alone is
        compared with ``==``.  Anything asserting FAILURE for an added record
        key would be asserting the opposite of what the validator does.
        """
        for ledger in (
            "market_clearing_records",
            "route_capacity_constraints",
            "market_agent_orders",
            "market_price_iterations",
            "market_inventory_histories",
        ):
            with self.subTest(ledger=ledger):
                self.assertEqual(
                    self._tampered(
                        lambda world, n=ledger: world[n][0].__setitem__(
                            "clearing_price", 1.0
                        )
                    ),
                    [],
                )
        self.assertEqual(
            self._tampered(
                lambda world: world["summary"].__setitem__("clearing_price", 1.0)
            ),
            [],
        )

    def test_malformed_payloads_fail_without_raising(self) -> None:
        """Structurally broken payloads return the failure, never an exception."""
        none_summary = worlds.cached_world("replay_128")
        none_summary["summary"] = None
        no_summary = worlds.cached_world("replay_128")
        del no_summary["summary"]
        list_summary = worlds.cached_world("replay_128")
        list_summary["summary"] = []
        scalar_routes = worlds.cached_world("replay_128")
        scalar_routes["routes"] = [1, 2, 3]
        scalar_exchanges = worlds.cached_world("replay_128")
        scalar_exchanges["market_exchanges"] = [1, 2, 3]

        cases = (
            ("empty dict", {}),
            ("summary only", {"summary": {}}),
            ("model declaration only", {"market_clearing_model": MARKET_CLEARING_MODEL}),
            ("summary is None", none_summary),
            ("summary is a list", list_summary),
            ("summary removed", no_summary),
            ("routes are not records", scalar_routes),
            ("market_exchanges are not records", scalar_exchanges),
        )
        for label, payload in cases:
            with self.subTest(payload=label):
                self.assertEqual(validate_market_clearing_replay(payload), [FAILURE])
