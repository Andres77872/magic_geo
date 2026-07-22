"""Causal-replay validation of the logistics network and market exchange model.

``validate_logistics_exchange_replay`` recomputes every logistics network and
market exchange from the political regions, routes, trade flows, settlements,
economy histories, conflicts and borders of a generated world, so a passing
payload that describes any traffic at all cannot be hand-built: the happy path
runs against a generated world and every failure case starts from that world and
applies exactly one tamper.

The one payload that *can* be hand-built is the degenerate empty one — every
recomputation is vacuously satisfied when there is nothing to recompute — which
``test_empty_payload_is_accepted_vacuously`` pins down as a limitation.

Two kinds of tamper are exercised, because only the second one proves the
validator is a *replay* rather than an internal consistency check:

* a stored ``logistics_networks`` / ``market_exchanges`` / ``summary`` value is
  overwritten, so it no longer matches what the inputs imply;
* an *input* (route, trade flow, economy history, region) is changed, so the
  recomputed value no longer matches the untouched stored record.

The validator only compares the keys it recomputes, so some plausible-looking
tampers are silently ignored and are deliberately *not* used as cases:

* ``settlements[0]["region_id"] = 7`` and ``settlements[0]["id"] = 99`` both
  replay cleanly. This world has a single political region, and every route
  binds to region 0 through its other endpoint, so the route-to-region map is
  unchanged.
* ``market_exchanges[0]["region_from"] = 0`` is a no-op because the stored
  value is already 0.
* Extra keys are ignored by design: generated ``market_exchanges`` records also
  carry ``market_clearing_record_id``, ``cleared_volume_index`` and friends from
  the downstream market-clearing stage, which this validator never recomputes.

Every tamper below therefore goes through :meth:`_tamper`, which asserts the
write actually changed the stored value before making it.
"""

from __future__ import annotations

from typing import Any
from unittest import TestCase

from support import worlds

from magic_geo.logistics_exchange_validation import (
    LOGISTICS_EXCHANGE_MODEL,
    validate_logistics_exchange_replay,
)

WORLD = "replay_128"

FAILURE = ["logistics exchange model or causal replay invalid"]

REQUIRED_LISTS = (
    "political_regions",
    "routes",
    "trade_flows",
    "economy_histories",
    "settlements",
    "conflicts",
    "borders",
    "logistics_networks",
    "market_exchanges",
)

#: Every key the validator recomputes for a logistics network, with a value
#: that is wrong for the replay world.
NETWORK_TAMPERS: tuple[tuple[str, Any], ...] = (
    ("id", 9),
    ("region_id", 4),
    ("route_ids", []),
    ("trade_flow_ids", []),
    ("border_ids", [0]),
    ("route_count", 0),
    ("trade_flow_count", 0),
    ("border_count", 3),
    ("total_route_distance_km", 1.0),
    ("total_route_cost", 1.0),
    ("total_trade_volume_index", 0.0),
    ("interregional_trade_volume_index", 5.0),
    ("army_capacity_population", 0.0),
    ("supply_capacity_index", 0.0),
    ("transport_efficiency_index", 1.0),
    ("logistics_resilience_index", 0.0),
    ("chokepoint_exposure_index", 1.0),
)

#: Every key the validator recomputes for a market exchange.
EXCHANGE_TAMPERS: tuple[tuple[str, Any], ...] = (
    ("id", 9),
    ("trade_flow_id", 9),
    ("route_id", 9),
    ("from_settlement_id", 9),
    ("to_settlement_id", 9),
    ("region_from", 5),
    ("region_to", 5),
    ("primary_good", "unobtainium"),
    ("interregional", True),
    ("distance_km", 1.0),
    ("volume_index", 0.0),
    ("friction", 0.25),
    ("supply_index", 0.0),
    ("demand_index", 1.0),
    ("price_spread_index", 0.0),
    ("market_access_index", 0.0),
    ("tax_revenue_index", 0.0),
    ("food_security_link_index", 0.0),
    ("disruption_risk_index", 1.0),
)

#: Every summary key the validator recomputes.
SUMMARY_TAMPERS: tuple[tuple[str, Any], ...] = (
    ("logistics_network_count", 99),
    ("logistics_route_link_count", 0),
    ("market_exchange_count", 99),
    ("interregional_market_exchange_count", 7),
    ("total_market_exchange_volume_index", 0.0),
    ("mean_logistics_transport_efficiency_index", 0.5),
    ("mean_logistics_resilience_index", 0.5),
    ("mean_market_access_index", 0.5),
    ("mean_market_disruption_risk_index", 0.5),
)

#: Every key of the model descriptor, which is compared as a whole dict.
MODEL_TAMPERS: tuple[tuple[str, Any], ...] = (
    ("model_type", "not_the_model"),
    ("deterministic", False),
    ("region_order", "descending_political_region_id_v1"),
    ("network_model", "other_network_model"),
    ("transport_model", "other_transport_model"),
    ("capacity_model", "other_capacity_model"),
    ("exchange_model", "other_exchange_model"),
    ("model_limitation", "no_limitations"),
)


class LogisticsExchangeReplayValidationTests(TestCase):
    def tearDown(self) -> None:
        """No tamper may leak into the world shared with every later test.

        The tamper helpers below copy on write instead of deep copying, so this
        is the guard that turns an accidental in-place mutation of the shared
        world into a loud failure here rather than a mystery failure elsewhere.
        """
        self.assertEqual(
            validate_logistics_exchange_replay(worlds.cached_world_readonly(WORLD)),
            [],
            "a test mutated the shared world",
        )

    def _payload(self) -> dict[str, Any]:
        """A copy-on-write overlay over the shared 128-cell replay world.

        Only the top-level mapping is copied. Tamper helpers replace the list
        and the record they touch, so nested objects shared with the cached
        world are never mutated (``tearDown`` proves it). The validator only
        reads its payload, so the overlay replays identically to a deep copy —
        :meth:`test_generated_world_replays_cleanly` asserts exactly that.
        """
        return dict(worlds.cached_world_readonly(WORLD))

    def _record(
        self, payload: dict[str, Any], family: str, index: int
    ) -> dict[str, Any]:
        """Replace ``payload[family][index]`` with a private copy and return it."""
        records = list(payload[family])
        record = dict(records[index])
        records[index] = record
        payload[family] = records
        return record

    def _mapping(self, payload: dict[str, Any], name: str) -> dict[str, Any]:
        """Replace the ``payload[name]`` mapping with a private copy."""
        mapping = dict(payload[name])
        payload[name] = mapping
        return mapping

    def _tamper(self, mapping: dict[str, Any], key: str, value: Any) -> None:
        """Overwrite ``mapping[key]``, proving the write is not a no-op."""
        self.assertIn(key, mapping)
        self.assertNotEqual(
            mapping[key], value, f"tamper for {key!r} did not change the payload"
        )
        mapping[key] = value

    def test_generated_world_replays_cleanly(self) -> None:
        world = worlds.cached_world_readonly(WORLD)

        self.assertEqual(validate_logistics_exchange_replay(world), [])
        self.assertEqual(
            world["summary"]["logistics_exchange_model"], LOGISTICS_EXCHANGE_MODEL
        )
        model = world["logistics_exchange_model"]
        self.assertEqual(model["model_type"], LOGISTICS_EXCHANGE_MODEL)
        self.assertIs(model["deterministic"], True)

        # Every tamper case below starts from one of these two untampered
        # copies, so both must replay cleanly: otherwise a tamper test could
        # pass because the copy itself is broken.
        self.assertEqual(validate_logistics_exchange_replay(self._payload()), [])
        self.assertEqual(
            validate_logistics_exchange_replay(worlds.cached_world(WORLD)), []
        )

    def test_networks_and_exchanges_cover_their_inputs(self) -> None:
        """One network per political region, one exchange per trade flow."""
        world = worlds.cached_world_readonly(WORLD)
        regions = world["political_regions"]
        trade_flows = world["trade_flows"]
        networks = world["logistics_networks"]
        exchanges = world["market_exchanges"]

        self.assertTrue(regions, "world has no political regions to replay")
        self.assertTrue(trade_flows, "world has no trade flows to replay")

        self.assertEqual(
            [network["region_id"] for network in networks],
            sorted(int(region["id"]) for region in regions),
        )
        self.assertEqual(
            [network["id"] for network in networks], list(range(len(regions)))
        )
        self.assertEqual(
            [exchange["trade_flow_id"] for exchange in exchanges],
            sorted(int(trade["id"]) for trade in trade_flows),
        )
        self.assertEqual(
            [exchange["id"] for exchange in exchanges], list(range(len(trade_flows)))
        )
        for network in networks:
            with self.subTest(network=network["id"]):
                self.assertEqual(network["route_count"], len(network["route_ids"]))
                self.assertEqual(
                    network["trade_flow_count"], len(network["trade_flow_ids"])
                )
                self.assertEqual(network["border_count"], len(network["border_ids"]))

    def test_summary_aggregates_agree_with_the_stored_records(self) -> None:
        """The summary is recomputed from the same records, so it must match them."""
        world = worlds.cached_world_readonly(WORLD)
        summary = world["summary"]
        networks = world["logistics_networks"]
        exchanges = world["market_exchanges"]

        self.assertTrue(networks)
        self.assertTrue(exchanges)

        self.assertEqual(summary["logistics_network_count"], len(networks))
        self.assertEqual(summary["market_exchange_count"], len(exchanges))
        self.assertEqual(
            summary["logistics_route_link_count"],
            sum(network["route_count"] for network in networks),
        )
        self.assertEqual(
            summary["interregional_market_exchange_count"],
            sum(1 for exchange in exchanges if exchange["interregional"]),
        )
        aggregates: tuple[tuple[str, float], ...] = (
            (
                "total_market_exchange_volume_index",
                sum(exchange["volume_index"] for exchange in exchanges),
            ),
            (
                "mean_logistics_transport_efficiency_index",
                sum(network["transport_efficiency_index"] for network in networks)
                / len(networks),
            ),
            (
                "mean_logistics_resilience_index",
                sum(network["logistics_resilience_index"] for network in networks)
                / len(networks),
            ),
            (
                "mean_market_access_index",
                sum(exchange["market_access_index"] for exchange in exchanges)
                / len(exchanges),
            ),
            (
                "mean_market_disruption_risk_index",
                sum(exchange["disruption_risk_index"] for exchange in exchanges)
                / len(exchanges),
            ),
        )
        for key, expected in aggregates:
            with self.subTest(summary=key):
                self.assertAlmostEqual(summary[key], expected, places=6)

    def test_empty_payload_is_accepted_vacuously(self) -> None:
        """A world with nothing in it replays cleanly. Documented limitation.

        With no political regions there are no networks, with no trade flows no
        exchanges, and the validator defines every mean over an empty family as
        ``0.0``, so all nine summary aggregates are zero and both recomputed
        lists are empty. Nothing here is a fact about the generator: emptiness
        has to be ruled out by whichever validator owns those families.
        """
        payload = self._payload()
        for name in REQUIRED_LISTS:
            payload[name] = []
        summary = self._mapping(payload, "summary")
        for key, _ in SUMMARY_TAMPERS:
            summary[key] = 0

        self.assertEqual(validate_logistics_exchange_replay(payload), [])

        # ... and it is still the tags that carry the model identity.
        self._tamper(summary, "logistics_exchange_model", "not_the_model")

        self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

    def test_malformed_or_incomplete_payloads_are_rejected_without_raising(
        self,
    ) -> None:
        cases: tuple[tuple[str, dict[str, Any]], ...] = (
            ("empty", {}),
            ("summary_only", {"summary": {}}),
            ("summary_not_a_dict", {"summary": None}),
            (
                "lists_not_lists",
                {"summary": {}, **{name: None for name in REQUIRED_LISTS}},
            ),
            (
                "empty_lists",
                {"summary": {}, **{name: [] for name in REQUIRED_LISTS}},
            ),
        )
        for label, payload in cases:
            with self.subTest(payload=label):
                self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        for name in REQUIRED_LISTS:
            with self.subTest(missing=name):
                payload = self._payload()
                self.assertIsInstance(payload.pop(name), list)

                self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

    def test_tampered_logistics_network_record_is_rejected(self) -> None:
        for key, value in NETWORK_TAMPERS:
            with self.subTest(field=key):
                payload = self._payload()
                self._tamper(self._record(payload, "logistics_networks", 0), key, value)

                self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(field="supply_capacity_index", tamper="dropped"):
            payload = self._payload()
            self._record(payload, "logistics_networks", 0).pop("supply_capacity_index")

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(field="logistics_networks", tamper="emptied"):
            payload = self._payload()
            payload["logistics_networks"] = []

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(field="logistics_networks", tamper="record_duplicated"):
            payload = self._payload()
            networks = payload["logistics_networks"]
            payload["logistics_networks"] = [*networks, *networks]

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

    def test_tampered_market_exchange_record_is_rejected(self) -> None:
        for key, value in EXCHANGE_TAMPERS:
            with self.subTest(field=key):
                payload = self._payload()
                self._tamper(self._record(payload, "market_exchanges", 0), key, value)

                self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(field="market_access_index", tamper="dropped"):
            payload = self._payload()
            self._record(payload, "market_exchanges", 0).pop("market_access_index")

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(field="market_exchanges", tamper="record_dropped"):
            payload = self._payload()
            payload["market_exchanges"] = payload["market_exchanges"][:-1]

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(field="market_exchanges", tamper="record_duplicated"):
            payload = self._payload()
            payload["market_exchanges"] = [
                *payload["market_exchanges"],
                payload["market_exchanges"][0],
            ]

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

    def test_tampered_summary_counts_are_rejected(self) -> None:
        for key, value in SUMMARY_TAMPERS:
            with self.subTest(summary=key):
                payload = self._payload()
                self._tamper(self._mapping(payload, "summary"), key, value)

                self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(summary="logistics_network_count", tamper="dropped"):
            payload = self._payload()
            self._mapping(payload, "summary").pop("logistics_network_count")

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(summary="logistics_exchange_model"):
            payload = self._payload()
            self._tamper(
                self._mapping(payload, "summary"),
                "logistics_exchange_model",
                "not_the_model",
            )

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

    def test_tampered_model_descriptor_is_rejected(self) -> None:
        for key, value in MODEL_TAMPERS:
            with self.subTest(model=key):
                payload = self._payload()
                self._tamper(
                    self._mapping(payload, "logistics_exchange_model"), key, value
                )

                self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(model="deterministic", tamper="dropped"):
            payload = self._payload()
            self._mapping(payload, "logistics_exchange_model").pop("deterministic")

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(model="extra_key"):
            payload = self._payload()
            self._mapping(payload, "logistics_exchange_model")["extra_model"] = "x"

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(model="missing"):
            payload = self._payload()
            self.assertIsInstance(payload.pop("logistics_exchange_model"), dict)

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

    def test_tampered_inputs_break_the_replay(self) -> None:
        """Changing an input invalidates the untouched stored records."""
        input_cases: tuple[tuple[str, str, int, str, Any], ...] = (
            ("route_id", "routes", 0, "id", 77),
            ("route_distance", "routes", 0, "distance_km", 1.0),
            ("route_cost", "routes", 0, "cost", 1.0),
            ("trade_volume", "trade_flows", 0, "volume_index", 0.0),
            ("trade_friction", "trade_flows", 0, "friction", 0.25),
            ("trade_distance", "trade_flows", 0, "distance_km", 1.0),
            ("trade_interregional", "trade_flows", 0, "interregional", True),
            ("trade_primary_good", "trade_flows", 0, "primary_good", "unobtainium"),
            ("economy_region", "economy_histories", 0, "region_id", 5),
            (
                "economy_army",
                "economy_histories",
                0,
                "max_army_capacity_population",
                0.0,
            ),
            ("economy_output", "economy_histories", 0, "peak_gross_output_index", 0.0),
            ("economy_treasury", "economy_histories", 0, "peak_treasury_index", 0.0),
            ("economy_steps", "economy_histories", 0, "steps", []),
        )
        for label, family, index, key, value in input_cases:
            with self.subTest(input=label):
                payload = self._payload()
                self._tamper(self._record(payload, family, index), key, value)

                self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        for family in ("routes", "trade_flows", "political_regions"):
            with self.subTest(input=family, tamper="truncated"):
                payload = self._payload()
                self.assertTrue(payload[family])
                payload[family] = payload[family][:-1]

                self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(input="economy_step", tamper="final_prosperity"):
            payload = worlds.cached_world(WORLD)
            final_step = payload["economy_histories"][0]["steps"][-1]
            self._tamper(final_step, "prosperity_index", 0.0)

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

    def test_bogus_records_in_empty_families_are_rejected(self) -> None:
        world = worlds.cached_world_readonly(WORLD)
        self.assertEqual(world["borders"], [])
        self.assertEqual(world["conflicts"], [])

        with self.subTest(family="borders"):
            payload = self._payload()
            payload["borders"] = [{"id": 0, "region_a": 0, "region_b": 0}]

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)

        with self.subTest(family="conflicts"):
            payload = self._payload()
            payload["conflicts"] = [
                {
                    "id": 0,
                    "region_a": 0,
                    "region_b": 0,
                    "intensity": 1.0,
                    "economic_disruption_index": 1.0,
                    "logistics_strain_index": 1.0,
                }
            ]

            self.assertEqual(validate_logistics_exchange_replay(payload), FAILURE)
