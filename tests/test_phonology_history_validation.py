from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest import TestCase

from support import worlds

from magic_geo.phonology_history_validation import (
    PHONOLOGY_HISTORY_MODEL,
    validate_phonology_history_replay,
)

#: The single failure message the validator ever returns.
FAILURE = "phonology history model or causal replay invalid"


class PhonologyHistoryReplayValidationTests(TestCase):
    """``validate_phonology_history_replay`` over the 128-cell replay world.

    The validator recomputes the whole deterministic phonology/lexicon/speaker
    model from ``language_regions``, ``historical_eras`` and
    ``population_regions`` and compares it record by record against the stored
    payload, so the only tractable failure tests start from a generated world
    and apply exactly one tamper.
    """

    def _assert_tamper_is_detected(
        self, mutate: Callable[[dict[str, Any]], None]
    ) -> None:
        """Apply ``mutate`` to a private world copy and demand the failure.

        Asserting ``[]`` on the untampered copy first makes the pair airtight:
        the validator is deterministic, so a tamper that silently mutated
        nothing would have to return both ``[]`` and ``[FAILURE]`` for the same
        payload. A no-op tamper therefore fails the second assertion instead of
        passing vacuously.
        """
        world = worlds.cached_world("replay_128")
        self.assertEqual(
            validate_phonology_history_replay(world),
            [],
            "the untampered copy must replay clean, otherwise the tamper proves nothing",
        )
        mutate(world)
        self.assertEqual(validate_phonology_history_replay(world), [FAILURE])

    def test_generated_world_replays_clean(self) -> None:
        world = worlds.cached_world_readonly("replay_128")

        self.assertEqual(validate_phonology_history_replay(world), [])
        self.assertEqual(
            world["summary"]["phonology_history_model"], PHONOLOGY_HISTORY_MODEL
        )
        # Every tamper below indexes record ``[0]`` of a family, so a clean
        # replay is only meaningful while the families are actually populated.
        for family in (
            "language_regions",
            "historical_eras",
            "population_regions",
            "phonological_rules",
            "phonological_histories",
            "lexical_correspondences",
            "lexical_diffusion_histories",
            "speaker_population_histories",
        ):
            with self.subTest(family=family):
                self.assertGreaterEqual(len(world[family]), 1)

    def test_malformed_payloads_return_the_failure_without_raising(self) -> None:
        # A correct model declaration lifted from the generated world, so the
        # "empty families" case cannot short-circuit on a missing model block
        # and instead has to be rejected by the replay/summary comparison.
        model_block = dict(
            worlds.cached_world_readonly("replay_128")["phonology_history_model"]
        )
        empty_families: dict[str, Any] = {
            "language_regions": [],
            "historical_eras": [],
            "population_regions": [],
            "phonological_rules": [],
            "phonological_histories": [],
            "lexical_correspondences": [],
            "lexical_diffusion_histories": [],
            "speaker_population_histories": [],
        }
        cases = {
            "empty payload": {},
            "summary is not a mapping": {"summary": []},
            "language regions are not a list": {"language_regions": None},
            "non numeric language fields": {
                "summary": {},
                "language_regions": [{"id": 0, "change_rate": "not-a-number"}],
                **{key: [] for key in empty_families if key != "language_regions"},
            },
            "empty record families only": {
                "summary": {"phonology_history_model": PHONOLOGY_HISTORY_MODEL},
                **empty_families,
            },
            "empty record families with a valid model block": {
                "phonology_history_model": model_block,
                "summary": {"phonology_history_model": PHONOLOGY_HISTORY_MODEL},
                **empty_families,
            },
        }
        for label, payload in cases.items():
            with self.subTest(payload=label):
                self.assertEqual(
                    validate_phonology_history_replay(payload), [FAILURE]
                )

    def test_sound_change_rule_tampers_are_detected(self) -> None:
        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "rule type": lambda world: world["phonological_rules"][0].__setitem__(
                "rule_type", "bogus"
            ),
            "source segment features": lambda world: world["phonological_rules"][0][
                "source_features"
            ].__setitem__("place", "uvular"),
            "probability index": lambda world: world["phonological_rules"][
                0
            ].__setitem__("probability_index", 0.123456),
            "era assignment": lambda world: world["phonological_rules"][0].__setitem__(
                "era_id", 99
            ),
            "rule list emptied": lambda world: world.__setitem__(
                "phonological_rules", []
            ),
            "extra rule appended": lambda world: world["phonological_rules"].append(
                dict(world["phonological_rules"][0])
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(tamper=label):
                self._assert_tamper_is_detected(mutate)

    def test_lexical_and_speaker_record_tampers_are_detected(self) -> None:
        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "correspondence list emptied": lambda world: world.__setitem__(
                "lexical_correspondences", []
            ),
            "derived form": lambda world: world["lexical_correspondences"][
                0
            ].__setitem__("derived_form", "zzzz"),
            "borrowed flag flipped": lambda world: world["lexical_correspondences"][
                0
            ].__setitem__(
                "borrowed", not world["lexical_correspondences"][0]["borrowed"]
            ),
            "phonological history step inventory": lambda world: world[
                "phonological_histories"
            ][0]["steps"][0].__setitem__("inventory_size", 999),
            "phonological history step rule backreferences": lambda world: world[
                "phonological_histories"
            ][0]["steps"][0].__setitem__("rule_ids", []),
            "diffusion history stress system": lambda world: world[
                "lexical_diffusion_histories"
            ][0].__setitem__("stress_system", "bogus_stress"),
            "speaker high contact flag flipped": lambda world: world[
                "speaker_population_histories"
            ][0].__setitem__(
                "high_contact_speaker_history",
                not world["speaker_population_histories"][0][
                    "high_contact_speaker_history"
                ],
            ),
            "speaker step population": lambda world: world[
                "speaker_population_histories"
            ][0]["steps"][-1].__setitem__("speaker_population", 1.0),
        }
        for label, mutate in cases.items():
            with self.subTest(tamper=label):
                self._assert_tamper_is_detected(mutate)

    def test_language_region_input_and_annotation_tampers_are_detected(self) -> None:
        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            # Flip to whichever extreme the stored value is not, so the tamper
            # can never degrade into a no-op for a differently seeded world.
            "sound shift index input": lambda world: world["language_regions"][
                0
            ].__setitem__(
                "sound_shift_index",
                0.0 if float(world["language_regions"][0]["sound_shift_index"]) >= 0.5
                else 1.0,
            ),
            "trade contact index input": lambda world: world["language_regions"][
                0
            ].__setitem__(
                "trade_contact_index",
                0.0 if float(world["language_regions"][0]["trade_contact_index"]) >= 0.5
                else 1.0,
            ),
            "phoneme inventory size input": lambda world: world["language_regions"][
                0
            ].__setitem__(
                "phoneme_inventory_size",
                int(world["language_regions"][0]["phoneme_inventory_size"]) + 5,
            ),
            "history backreference removed": lambda world: world["language_regions"][
                0
            ].pop("phonological_history_id", None),
            "lexical correspondence count annotation": lambda world: world[
                "language_regions"
            ][0].__setitem__("lexical_correspondence_count", 3),
            "historical era dropped": lambda world: world["historical_eras"].pop(),
            "historical era start year shifted": lambda world: world[
                "historical_eras"
            ][0].__setitem__(
                "start_year_bp",
                float(world["historical_eras"][0]["start_year_bp"]) + 500.0,
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(tamper=label):
                self._assert_tamper_is_detected(mutate)

    def test_population_region_input_tampers_are_detected(self) -> None:
        """The speaker half of the model is driven by ``population_regions``.

        Nothing above touches that input, so without these cases a validator
        that ignored population sizes, weights or language links entirely would
        still look fully covered.
        """
        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "estimated population": lambda world: world["population_regions"][
                0
            ].__setitem__(
                "estimated_population",
                float(world["population_regions"][0]["estimated_population"]) + 1000.0,
            ),
            "urbanization fraction": lambda world: world["population_regions"][
                0
            ].__setitem__(
                "urbanization_fraction",
                0.0
                if float(world["population_regions"][0]["urbanization_fraction"]) >= 0.5
                else 1.0,
            ),
            "language link detached": lambda world: world["population_regions"][
                0
            ].__setitem__("language_region_id", 987),
            "population list emptied": lambda world: world.__setitem__(
                "population_regions", []
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(tamper=label):
                self._assert_tamper_is_detected(mutate)

    def test_model_declaration_and_summary_tampers_are_detected(self) -> None:
        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "model type": lambda world: world["phonology_history_model"].__setitem__(
                "model_type", "wrong_model_v9"
            ),
            "model determinism flag": lambda world: world[
                "phonology_history_model"
            ].__setitem__("deterministic", False),
            "model key removed": lambda world: world["phonology_history_model"].pop(
                "speaker_model", None
            ),
            "summary model name": lambda world: world["summary"].__setitem__(
                "phonology_history_model", "wrong_model_v9"
            ),
            "summary rule count": lambda world: world["summary"].__setitem__(
                "phonological_rule_count",
                int(world["summary"]["phonological_rule_count"]) + 1,
            ),
            "summary rule count removed": lambda world: world["summary"].pop(
                "phonological_rule_count", None
            ),
            "summary high contact history count": lambda world: world[
                "summary"
            ].__setitem__(
                "high_contact_speaker_history_count",
                int(world["summary"]["high_contact_speaker_history_count"]) + 1,
            ),
            "summary total speaker population": lambda world: world[
                "summary"
            ].__setitem__(
                "total_estimated_speaker_population",
                float(world["summary"]["total_estimated_speaker_population"]) + 1.0,
            ),
        }
        for label, mutate in cases.items():
            with self.subTest(tamper=label):
                self._assert_tamper_is_detected(mutate)
