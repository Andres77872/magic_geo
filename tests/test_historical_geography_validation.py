"""Replay validation for the historical geography (causal event timeline) model.

:func:`magic_geo.historical_geography_validation.validate_historical_geography_replay`
recomputes the whole deterministic event timeline from the political, cultural,
linguistic, trade and site records of a generated world and compares it record by
record with the timeline the payload carries. It returns an empty list when the
replay agrees and one fixed failure string otherwise, swallowing malformed payloads
instead of raising.

Building a passing payload by hand is infeasible, so the happy path runs against a
generated world and every failure case starts from a private deep copy of that same
world with exactly one tampered field. Where the canonical world leaves a branch of
the replay unexercised (it carries no borders), a record is injected instead, and
the injection is first shown to keep the replay clean so that the tamper applied to
it stays the only explanation for the failure.
"""

from __future__ import annotations

import copy
from typing import Any, Callable
from unittest import TestCase

from support import worlds

from magic_geo.historical_geography_validation import (
    _replay_valid,
    validate_historical_geography_replay,
)

FAILURE = ["historical geography model or causal replay invalid"]


class HistoricalGeographyReplayValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = worlds.cached_world_readonly("replay_128")

    def _tampered(self, mutate: Callable[[dict[str, Any]], None]) -> list[str]:
        """Apply ``mutate`` to a private copy of the canonical world and validate it."""
        payload = worlds.cached_world("replay_128")
        mutate(payload)
        return validate_historical_geography_replay(payload)

    def test_canonical_world_replays_clean(self) -> None:
        self.assertEqual(validate_historical_geography_replay(self.world), [])

        # Every failure case below tampers a private deep copy. Prove the copy is
        # itself clean and that tampering it cannot corrupt the shared world, so a
        # reported failure can only come from the tamper.
        first_event = copy.deepcopy(self.world["historical_events"][0])
        payload = worlds.cached_world("replay_128")
        self.assertEqual(validate_historical_geography_replay(payload), [])
        payload["historical_events"][0]["type"] = "bogus"
        self.assertEqual(validate_historical_geography_replay(payload), FAILURE)
        self.assertEqual(self.world["historical_events"][0], first_event)
        self.assertEqual(validate_historical_geography_replay(self.world), [])

    def test_malformed_payloads_fail_without_raising(self) -> None:
        def without(key: str) -> dict[str, Any]:
            return {name: value for name, value in self.world.items() if name != key}

        cases: dict[str, dict[str, Any]] = {
            "empty payload": {},
            "summary only": {"summary": {}},
            "summary is not a mapping": {**without("summary"), "summary": []},
            "missing event collection": without("historical_events"),
            "event collection is not a list": {
                **without("historical_events"),
                "historical_events": {},
            },
            "event record is not a mapping": {
                **without("historical_events"),
                "historical_events": ["not-a-record"],
            },
            "missing model declaration": without("historical_event_model"),
        }
        for label, payload in cases.items():
            with self.subTest(payload=label):
                self.assertEqual(validate_historical_geography_replay(payload), FAILURE)

    def test_replay_errors_are_swallowed_into_the_failure_string(self) -> None:
        # The malformed payloads above are all rejected by an explicit guard and
        # never reach the ``except`` clause of the public entry point. These do:
        # each one makes the replay itself raise, so the case first asserts the
        # exact exception (proving the swallow is what produces the result) and
        # then asserts the swallowed failure string.
        cases: dict[str, tuple[Callable[[dict[str, Any]], None], type, str]] = {
            "settlement id is not numeric": (
                lambda payload: payload["settlements"][0].__setitem__("id", "one"),
                ValueError,
                r"invalid literal for int\(\) with base 10: 'one'",
            ),
            "region id is None": (
                lambda payload: payload["political_regions"][0].__setitem__("id", None),
                TypeError,
                r"int\(\) argument must be",
            ),
            "culture continuity index is not numeric": (
                lambda payload: payload["cultures"][0].__setitem__(
                    "continuity_index", "warm"
                ),
                ValueError,
                r"could not convert string to float: 'warm'",
            ),
            "trade flow volume is not numeric": (
                lambda payload: payload["trade_flows"][0].__setitem__(
                    "volume_index", "brisk"
                ),
                ValueError,
                r"could not convert string to float: 'brisk'",
            ),
        }
        for label, (mutate, exception, message) in cases.items():
            with self.subTest(payload=label):
                payload = worlds.cached_world("replay_128")
                mutate(payload)
                with self.assertRaisesRegex(exception, message):
                    _replay_valid(payload)
                self.assertEqual(validate_historical_geography_replay(payload), FAILURE)

    def test_border_records_are_replayed_into_state_foundation_pressure(self) -> None:
        # replay_128 has no borders, so the border barrier term of the state
        # foundation pressure is otherwise never exercised. A border of zero
        # length contributes no weighted pressure and no length, so injecting one
        # must leave the replay clean: that clean baseline is what makes each
        # failure below attributable to the single field that differs from it.
        self.assertEqual(self.world["borders"], [])
        neutral = {"region_a": 0, "region_b": 0, "length_km": 0.0, "barrier_score": 0.0}
        self.assertEqual(
            self._tampered(
                lambda payload: payload.__setitem__(
                    "borders", [{"id": 0, **neutral}, {"id": 1, **neutral}]
                )
            ),
            [],
        )
        # Borders are an indexed source family like settlements or ruins, and the
        # two records are otherwise identical, so only record["id"] == index can
        # separate this payload from the clean one above.
        self.assertEqual(
            self._tampered(
                lambda payload: payload.__setitem__(
                    "borders", [{"id": 1, **neutral}, {"id": 0, **neutral}]
                )
            ),
            FAILURE,
        )

        # A long border with no barrier is still neutral: mean barrier pressure
        # is a length-weighted mean of barrier_score, so it stays 0.0.
        long_border = {"id": 0, "region_a": 0, "region_b": 0, "length_km": 400.0}
        self.assertEqual(
            self._tampered(
                lambda payload: payload.__setitem__(
                    "borders", [{**long_border, "barrier_score": 0.0}]
                )
            ),
            [],
        )
        # Raising only barrier_score moves the replayed pressure index by
        # 0.28 * 0.9, far outside the 0.002 tolerance, and is detected.
        self.assertEqual(
            self._tampered(
                lambda payload: payload.__setitem__(
                    "borders", [{**long_border, "barrier_score": 0.9}]
                )
            ),
            FAILURE,
        )

    def test_event_record_tampers_are_detected(self) -> None:
        def set_field(field: str, value: Any) -> Callable[[dict[str, Any]], None]:
            def mutate(payload: dict[str, Any]) -> None:
                payload["historical_events"][0][field] = value

            return mutate

        first = self.world["historical_events"][0]

        def bumped(field: str) -> Callable[[dict[str, Any]], None]:
            # Shifting an identifier by three cannot land back on the replayed
            # value, and every one of these fields is compared exactly.
            return set_field(field, int(first[field]) + 3)

        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            # One case per exactly-compared key, so no key can stop being checked
            # without a red test.
            "id": bumped("id"),
            "era_id": set_field("era_id", (int(first["era_id"]) + 1) % 4),
            # "bogus" is not one of the seven replayed event types.
            "type": set_field("type", "bogus"),
            "region_id": bumped("region_id"),
            "related_region_id": bumped("related_region_id"),
            "culture_region_id": bumped("culture_region_id"),
            "related_culture_region_id": bumped("related_culture_region_id"),
            "language_region_id": bumped("language_region_id"),
            "related_language_region_id": bumped("related_language_region_id"),
            "cell_id": bumped("cell_id"),
            # year_bp is compared with a 0.20 year tolerance.
            "year_bp": set_field("year_bp", float(first["year_bp"]) + 5.0),
            # pressure_index and continuity_index carry a 0.002 tolerance.
            "pressure_index": set_field(
                "pressure_index", round(float(first["pressure_index"]) + 0.05, 6)
            ),
            "continuity_index": set_field(
                "continuity_index", round(float(first["continuity_index"]) + 0.05, 6)
            ),
            # The timeline is stored in descending-year, then event-enum order;
            # exchanging two adjacent records breaks the positional comparison.
            "reordered timeline": lambda payload: payload[
                "historical_events"
            ].__setitem__(
                slice(0, 2),
                [payload["historical_events"][1], payload["historical_events"][0]],
            ),
            "dropped trailing event": lambda payload: payload["historical_events"].pop(),
            "emptied timeline": lambda payload: payload.__setitem__(
                "historical_events", []
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(event_field=label):
                self.assertEqual(self._tampered(mutate), FAILURE)

    def test_indexed_source_records_must_be_positionally_identified(self) -> None:
        def swap_ids(collection: str) -> Callable[[dict[str, Any]], None]:
            def mutate(payload: dict[str, Any]) -> None:
                first, second = payload[collection][0], payload[collection][1]
                first["id"], second["id"] = second["id"], first["id"]

            return mutate

        # Swapping two ids leaves every other field untouched, so only the
        # record["id"] == index invariant can catch it.
        for collection in ("settlements", "trade_flows", "sacred_areas", "ruins"):
            with self.subTest(collection=collection):
                self.assertGreaterEqual(len(self.world[collection]), 2)
                self.assertEqual(self._tampered(swap_ids(collection)), FAILURE)

        with self.subTest(collection="political_regions"):
            self.assertEqual(
                self._tampered(
                    lambda payload: payload["political_regions"][0].__setitem__("id", 7)
                ),
                FAILURE,
            )

    def test_era_model_and_summary_aggregate_tampers_are_detected(self) -> None:
        bogus_era = {
            "id": 4,
            "dominant_process": "aftermath",
            "start_year_bp": 0.0,
            "end_year_bp": 0.0,
            "event_count": 0,
            "state_event_count": 0,
            "migration_event_count": 0,
            "language_event_count": 0,
            "mean_instability": 0.0,
            "mean_connectivity": 0.0,
        }
        eras = self.world["historical_eras"]
        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "fifth era appended": lambda payload: payload["historical_eras"].append(
                bogus_era
            ),
            "era dropped": lambda payload: payload["historical_eras"].pop(),
            "era renamed": lambda payload: payload["historical_eras"][0].__setitem__(
                "dominant_process", "bogus"
            ),
            "era event_count inflated": lambda payload: payload["historical_eras"][
                3
            ].__setitem__("event_count", 999),
            "era mean_instability shifted": lambda payload: payload["historical_eras"][
                3
            ].__setitem__(
                "mean_instability", round(float(eras[3]["mean_instability"]) + 0.05, 6)
            ),
            "era state_event_count inflated": lambda payload: payload[
                "historical_eras"
            ][1].__setitem__("state_event_count", 99),
            "era language_event_count inflated": lambda payload: payload[
                "historical_eras"
            ][1].__setitem__("language_event_count", 99),
            "era mean_connectivity shifted": lambda payload: payload["historical_eras"][
                1
            ].__setitem__(
                "mean_connectivity",
                round(float(eras[1]["mean_connectivity"]) + 0.05, 6),
            ),
            "era boundary moved": lambda payload: payload["historical_eras"][
                1
            ].__setitem__("start_year_bp", 2500.0),
            "era end boundary moved": lambda payload: payload["historical_eras"][
                0
            ].__setitem__("end_year_bp", 2000.0),
            "model replaced": lambda payload: payload.__setitem__(
                "historical_event_model", {"model_type": "bogus"}
            ),
            "model parameter edited": lambda payload: payload[
                "historical_event_model"
            ].__setitem__("trade_boom_maximum_events", 11),
            "summary model name": lambda payload: payload["summary"].__setitem__(
                "historical_event_model", "bogus_timeline_v9"
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(tamper=label):
                self.assertEqual(self._tampered(mutate), FAILURE)

        summary = self.world["summary"]
        summary_cases = {
            "historical_era_count": 3,
            "historical_event_count": int(summary["historical_event_count"]) + 1,
            "migration_event_count": int(summary["migration_event_count"]) + 1,
            "dynastic_change_count": int(summary["dynastic_change_count"]) + 1,
        }
        for key, value in summary_cases.items():
            with self.subTest(summary_key=key):
                self.assertNotEqual(summary[key], value)
                self.assertEqual(
                    self._tampered(
                        lambda payload, key=key, value=value: payload[
                            "summary"
                        ].__setitem__(key, value)
                    ),
                    FAILURE,
                )

    def test_source_records_feeding_the_replay_are_recomputed(self) -> None:
        # These fields are inputs to the replay, not outputs: editing one changes
        # the expected timeline while the stored timeline stays put.
        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "culture continuity_index": lambda payload: payload["cultures"][
                0
            ].__setitem__("continuity_index", 0.123456),
            "culture migration_pressure": lambda payload: payload["cultures"][
                0
            ].__setitem__("migration_pressure", 0.0),
            "trade flow volume_index": lambda payload: payload["trade_flows"][
                0
            ].__setitem__("volume_index", 0.0),
            "sacred site significance": lambda payload: payload["sacred_areas"][
                0
            ].__setitem__("significance", 0.999),
            "ruin significance": lambda payload: payload["ruins"][0].__setitem__(
                "significance", 0.999
            ),
            "emptied political regions": lambda payload: payload.__setitem__(
                "political_regions", []
            ),
            "emptied cultures": lambda payload: payload.__setitem__("cultures", []),
            "emptied trade flows": lambda payload: payload.__setitem__(
                "trade_flows", []
            ),
            "emptied sacred areas": lambda payload: payload.__setitem__(
                "sacred_areas", []
            ),
            "emptied ruins": lambda payload: payload.__setitem__("ruins", []),
        }
        for label, mutate in cases.items():
            with self.subTest(source=label):
                self.assertEqual(self._tampered(mutate), FAILURE)
