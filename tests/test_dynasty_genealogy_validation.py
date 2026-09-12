from __future__ import annotations

from typing import Any, Callable
from unittest import TestCase

from magic_geo.dynasty_genealogy_validation import validate_dynasty_genealogy_replay
from support import worlds

FAILURE = "ruler genealogy model or causal replay invalid"

RULER_GENEALOGY_MODEL = (
    "causal_dynasty_economy_conflict_named_ruler_alliance_cadet_genealogy_v1"
)

EXPECTED_MODEL = {
    "model_type": RULER_GENEALOGY_MODEL,
    "deterministic": True,
    "ruler_count_model": "dynasty_duration_pressure_bounded_two_to_six_rulers_v1",
    "reign_model": "equal_dynasty_duration_partition_v1",
    "ruler_attribute_model": "dynasty_continuity_pressure_economy_treasury_conflict_v1",
    "succession_model": "ordered_predecessor_successor_and_parent_links_v1",
    "cadet_branch_model": "second_ruler_founder_with_next_three_heirs_v1",
    "marriage_model": (
        "sorted_dynasty_first_available_cross_region_second_ruler_pair_v1"
    ),
    "name_model": "deterministic_root_and_regnal_number_v1",
    "model_limitation": (
        "synthetic_regnal_genealogy_without_age_consistent_reproduction_"
        "competing_heirs_gender_demography_or_observed_calibration"
    ),
}


class DynastyGenealogyReplayValidationTests(TestCase):
    """Causal replay of :func:`validate_dynasty_genealogy_replay`.

    The validator recomputes the whole deterministic genealogy from the
    dynasties, economy histories and conflicts in the payload. The control is
    an actual generated current-model world. Failure cases start from a private
    deep copy of that world and apply exactly one
    tamper, and every tamper is checked against the untampered copy so that
    a silently ignored mutation cannot masquerade as a passing test.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.world = worlds.cached_world_readonly("replay_128")

    def _tampered(self, mutate: Callable[[dict[str, Any]], None]) -> list[str]:
        """Validate a fresh deep copy of the canonical world after ``mutate``."""
        world = worlds.cached_world("replay_128")
        self.assertEqual(
            validate_dynasty_genealogy_replay(world),
            [],
            "the untampered deep copy must replay before it is tampered with",
        )
        mutate(world)
        return validate_dynasty_genealogy_replay(world)

    def test_canonical_world_replays_and_exposes_named_ruler_genealogy(self) -> None:
        self.assertEqual(validate_dynasty_genealogy_replay(self.world), [])
        self.assertEqual(self.world["ruler_genealogy_model"], EXPECTED_MODEL)
        self.assertEqual(self.world["climate_model"]["model_type"], "prescribed_seasonal_surface_energy_v1")

        # Preserve the intended one-dynasty, five-reign, no-conflict branch.
        # Its physical/economic inputs now come from the current seasonal world;
        # old climate-derived duration and treasury snapshots are not constants
        # of the genealogy model. Recompute every expectation from those inputs
        # and the declared genealogy equations, without producer/replay helpers.
        self.assertEqual(len(self.world["dynasties"]), 1)
        dynasty = self.world["dynasties"][0]
        self.assertEqual(dynasty["id"], 0)
        self.assertEqual(dynasty["region_id"], 0)
        self.assertEqual(dynasty["lineage_depth"], 0)
        duration = float(dynasty["duration_years"])
        pressure = float(dynasty["succession_pressure"])
        continuity = float(dynasty["dynastic_continuity_index"])
        self.assertGreaterEqual(duration, 1260.0)
        self.assertLess(duration, 1680.0)
        self.assertGreaterEqual(pressure, 0.0)
        self.assertLess(pressure, 0.55)
        self.assertEqual(dynasty["start_year_bp"], duration)
        self.assertEqual(dynasty["end_year_bp"], 0.0)
        self.assertEqual(int(duration // 420) + 2, 5)

        economies = self.world["economy_histories"]
        self.assertEqual(len(economies), 1)
        economy = economies[0]
        self.assertEqual(economy["region_id"], 0)
        self.assertEqual(self.world["conflicts"], [])
        self.assertGreater(economy["peak_gross_output_index"], 0.0)
        self.assertLess(economy["peak_gross_output_index"], 1200.0)
        self.assertGreater(economy["peak_treasury_index"], 0.0)
        self.assertLess(economy["peak_treasury_index"], 250.0)
        self.assertGreater(economy["max_army_capacity_population"], 0.0)
        self.assertLess(economy["max_army_capacity_population"], 60_000_000.0)
        economic_strength = economy["peak_gross_output_index"] / 1200.0
        treasury_strength = economy["peak_treasury_index"] / 250.0
        legitimacy = (0.45 * dynasty["legitimacy_index"] + 0.24 * continuity
                      + 0.12 * economic_strength + 0.07 * treasury_strength
                      + 0.12 * (1.0 - pressure))
        claim = round(0.72 * legitimacy + 0.28 * continuity, 6)
        prestige = 0.32 * economy["max_army_capacity_population"] / 60_000_000.0 + 0.20 * pressure
        patronage = 0.50 * economic_strength + 0.30 * treasury_strength + 0.20 * continuity
        succession_risks = [0.42 * pressure + 0.24 * (1.0 - legitimacy) + 0.10 * i / 4 for i in range(5)]

        rulers = self.world["rulers"]
        self.assertEqual(len(rulers), 5)
        self.assertEqual(self.world["marriage_alliances"], [])
        self.assertEqual([ruler["name"] for ruler in rulers],
                         ["Aren I", "Daren II", "Galen III", "Joren IV", "Maren V"])
        self.assertEqual([ruler["regnal_number"] for ruler in rulers], [1, 2, 3, 4, 5])
        self.assertEqual([ruler["predecessor_ruler_id"] for ruler in rulers], [-1, 0, 1, 2, 3])
        self.assertEqual([ruler["successor_ruler_id"] for ruler in rulers], [1, 2, 3, 4, -1])
        self.assertEqual([ruler["parent_ruler_id"] for ruler in rulers], [-1, 0, 0, 1, 2])
        self.assertEqual([ruler["ruler_lineage_depth"] for ruler in rulers], [0, 1, 2, 3, 4])

        # Five equal reigns; derive the date values from duration, never from
        # another exported ruler record. The final endpoint is exactly present.
        span = duration / 5
        expected_starts = [round(duration - i * span, 6) for i in range(5)]
        expected_ends = [round(duration - (i + 1) * span, 6) for i in range(4)] + [0.0]
        self.assertEqual([ruler["reign_start_year_bp"] for ruler in rulers], expected_starts)
        self.assertEqual([ruler["reign_end_year_bp"] for ruler in rulers], expected_ends)
        self.assertEqual([ruler["reign_length_years"] for ruler in rulers], [round(span, 6)] * 5)
        self.assertEqual(rulers[0]["birth_year_bp"], round(duration + 24.0 + 18.0 * pressure, 6))
        for key, expected in (
            ("legitimacy_index", round(legitimacy, 6)),
            ("succession_claim_strength", claim),
            ("military_prestige_index", round(prestige, 6)),
            ("economic_patronage_index", round(patronage, 6)),
        ):
            with self.subTest(field=key):
                self.assertEqual([ruler[key] for ruler in rulers], [expected] * 5)
        self.assertEqual([ruler["succession_crisis_risk"] for ruler in rulers],
                         [round(value, 6) for value in succession_risks])

        # The cadet stage consumes the already published six-decimal ruler
        # attributes. Keep that quantization visible in its independent replay.
        cadet_claim = round(0.72 * claim + 0.28 * pressure, 6)
        cadet_legitimacy = round(0.80 * round(legitimacy, 6) + 0.20 * continuity, 6)
        branches = self.world["cadet_branches"]
        self.assertEqual(len(branches), 1)
        self.assertEqual(branches[0]["founder_ruler_id"], 1)
        self.assertEqual(branches[0]["heir_ruler_ids"], [2, 3, 4])
        self.assertEqual(branches[0]["branch_start_year_bp"], expected_starts[1])
        self.assertEqual(branches[0]["branch_end_year_bp"], 0.0)
        self.assertEqual(branches[0]["claim_strength"], cadet_claim)
        self.assertEqual(branches[0]["cadet_legitimacy_index"], cadet_legitimacy)
        self.assertEqual([ruler["cadet_branch_id"] for ruler in rulers], [-1, 0, 0, 0, 0])
        self.assertEqual(dynasty["founder_ruler_id"], 0)
        self.assertEqual(dynasty["ruler_count"], 5)
        self.assertEqual(dynasty["cadet_branch_count"], 1)
        self.assertEqual(dynasty["marriage_alliance_count"], 0)

        summary = self.world["summary"]
        self.assertEqual(summary["ruler_genealogy_model"], RULER_GENEALOGY_MODEL)
        self.assertEqual(summary["ruler_count"], 5)
        self.assertEqual(summary["named_ruler_dynasty_count"], 1)
        self.assertEqual(summary["ruler_marriage_alliance_count"], 0)
        self.assertEqual(summary["cadet_branch_count"], 1)
        self.assertEqual(summary["married_ruler_count"], 0)
        self.assertEqual(summary["max_ruler_lineage_depth"], 4)
        self.assertEqual(summary["mean_ruler_legitimacy_index"], round(legitimacy, 6))
        self.assertEqual(summary["mean_succession_crisis_risk"], round(sum(succession_risks) / 5, 6))
        self.assertEqual(summary["mean_marriage_alliance_strength"], 0.0)
        self.assertEqual(summary["mean_cadet_branch_claim_strength"], cadet_claim)

    def test_malformed_payloads_return_the_failure_without_raising(self) -> None:
        without_summary = {
            key: value for key, value in self.world.items() if key != "summary"
        }
        cases: dict[str, dict[str, Any]] = {
            "empty_payload": {},
            "missing_summary": without_summary,
            "summary_is_a_list": {**self.world, "summary": []},
            "dynasties_is_none": {**self.world, "dynasties": None},
            "rulers_is_a_string": {**self.world, "rulers": "nope"},
            "dynasties_hold_scalars": {**self.world, "dynasties": [1, 2, 3]},
            "model_is_a_string": {**self.world, "ruler_genealogy_model": "v1"},
        }
        for name, payload in cases.items():
            with self.subTest(payload=name):
                self.assertEqual(validate_dynasty_genealogy_replay(payload), [FAILURE])

    def test_ruler_record_tampering_returns_the_failure(self) -> None:
        def rename_founder(world: dict[str, Any]) -> None:
            world["rulers"][0]["name"] = "Bob"

        def break_succession_link(world: dict[str, Any]) -> None:
            world["rulers"][0]["successor_ruler_id"] = 3

        def nudge_legitimacy(world: dict[str, Any]) -> None:
            world["rulers"][1]["legitimacy_index"] = 0.5

        def drop_cadet_membership(world: dict[str, Any]) -> None:
            world["rulers"][2]["cadet_branch_id"] = -1

        def shift_reign_start(world: dict[str, Any]) -> None:
            world["rulers"][0]["reign_start_year_bp"] = 1200.0

        def inflate_military_prestige(world: dict[str, Any]) -> None:
            world["rulers"][3]["military_prestige_index"] = 0.9

        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "founder_name_is_not_the_derived_regnal_name": rename_founder,
            "successor_link_skips_a_reign": break_succession_link,
            "legitimacy_index_is_not_the_replayed_value": nudge_legitimacy,
            "cadet_branch_membership_is_cleared": drop_cadet_membership,
            "reign_start_breaks_the_equal_duration_partition": shift_reign_start,
            "military_prestige_is_not_the_replayed_value": inflate_military_prestige,
        }
        for name, mutate in cases.items():
            with self.subTest(tamper=name):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_genealogy_model_metadata_tampering_returns_the_failure(self) -> None:
        def drop_model(world: dict[str, Any]) -> None:
            world["ruler_genealogy_model"] = None

        def drop_name_model_key(world: dict[str, Any]) -> None:
            del world["ruler_genealogy_model"]["name_model"]

        def soften_limitation(world: dict[str, Any]) -> None:
            world["ruler_genealogy_model"]["model_limitation"] = "none"

        def claim_nondeterminism(world: dict[str, Any]) -> None:
            world["ruler_genealogy_model"]["deterministic"] = False

        def rename_summary_model(world: dict[str, Any]) -> None:
            world["summary"]["ruler_genealogy_model"] = "named_ruler_genealogy_v2"

        def add_undeclared_model_key(world: dict[str, Any]) -> None:
            # The model block is compared with ``==``, not by subset, so an
            # extra key must fail too. Without this case the suite would still
            # pass if the check were relaxed to a containment test.
            world["ruler_genealogy_model"]["heir_selection_model"] = "primogeniture_v1"

        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "model_block_is_none": drop_model,
            "name_model_key_removed": drop_name_model_key,
            "model_limitation_understated": soften_limitation,
            "determinism_flag_flipped": claim_nondeterminism,
            "summary_model_tag_renamed": rename_summary_model,
            "undeclared_model_key_added": add_undeclared_model_key,
        }
        for name, mutate in cases.items():
            with self.subTest(tamper=name):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_dynasty_annotation_and_summary_tampering_returns_the_failure(self) -> None:
        def inflate_dynasty_ruler_count(world: dict[str, Any]) -> None:
            world["dynasties"][0]["ruler_count"] = 99

        def move_founder(world: dict[str, Any]) -> None:
            world["dynasties"][0]["founder_ruler_id"] = 7

        def inflate_dynasty_cadet_count(world: dict[str, Any]) -> None:
            world["dynasties"][0]["cadet_branch_count"] = 3

        def invent_dynasty_marriage(world: dict[str, Any]) -> None:
            world["dynasties"][0]["marriage_alliance_count"] = 2

        def shrink_summary_ruler_count(world: dict[str, Any]) -> None:
            world["summary"]["ruler_count"] = 4

        def invent_married_rulers(world: dict[str, Any]) -> None:
            world["summary"]["married_ruler_count"] = 2

        def skew_mean_succession_risk(world: dict[str, Any]) -> None:
            world["summary"]["mean_succession_crisis_risk"] = 0.5

        def deepen_lineage(world: dict[str, Any]) -> None:
            world["summary"]["max_ruler_lineage_depth"] = 9

        def skew_mean_cadet_claim(world: dict[str, Any]) -> None:
            world["summary"]["mean_cadet_branch_claim_strength"] = 0.9

        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "dynasty_ruler_count": inflate_dynasty_ruler_count,
            "dynasty_founder_ruler_id": move_founder,
            "dynasty_cadet_branch_count": inflate_dynasty_cadet_count,
            "dynasty_marriage_alliance_count": invent_dynasty_marriage,
            "summary_ruler_count": shrink_summary_ruler_count,
            "summary_married_ruler_count": invent_married_rulers,
            "summary_mean_succession_crisis_risk": skew_mean_succession_risk,
            "summary_max_ruler_lineage_depth": deepen_lineage,
            "summary_mean_cadet_branch_claim_strength": skew_mean_cadet_claim,
        }
        for name, mutate in cases.items():
            with self.subTest(tamper=name):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_cadet_branch_record_tampering_returns_the_failure(self) -> None:
        def drop_an_heir(world: dict[str, Any]) -> None:
            world["cadet_branches"][0]["heir_ruler_ids"] = [2, 3]

        def move_branch_founder(world: dict[str, Any]) -> None:
            world["cadet_branches"][0]["founder_ruler_id"] = 0

        def end_branch_early(world: dict[str, Any]) -> None:
            # The replayed branch ends with the last heir's reign, at 0.0.
            world["cadet_branches"][0]["branch_end_year_bp"] = 100.0

        def inflate_branch_claim(world: dict[str, Any]) -> None:
            world["cadet_branches"][0]["claim_strength"] = 0.9

        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "heir_list_truncated": drop_an_heir,
            "branch_founder_is_the_dynasty_founder": move_branch_founder,
            "branch_end_year_is_not_the_last_heirs_reign_end": end_branch_early,
            "claim_strength_is_not_the_replayed_value": inflate_branch_claim,
        }
        for name, mutate in cases.items():
            with self.subTest(tamper=name):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_record_list_and_causal_input_changes_return_the_failure(self) -> None:
        def append_bogus_alliance(world: dict[str, Any]) -> None:
            # No cross-region partner exists at 128 cells, so the replayed
            # alliance list is empty and any record is a length mismatch.
            world["marriage_alliances"].append(
                {
                    "id": 0,
                    "dynasty_a_id": 0,
                    "dynasty_b_id": 0,
                    "ruler_a_id": 1,
                    "ruler_b_id": 1,
                }
            )

        def empty_rulers(world: dict[str, Any]) -> None:
            world["rulers"] = []

        def empty_cadet_branches(world: dict[str, Any]) -> None:
            world["cadet_branches"] = []

        def append_bogus_conflict(world: dict[str, Any]) -> None:
            # A conflict on region 0 changes the replayed conflict pressure and
            # therefore every ruler's military prestige and succession risk.
            world["conflicts"].append(
                {"region_a": 0, "region_b": 0, "intensity": 0.9}
            )

        def stretch_dynasty_duration(world: dict[str, Any]) -> None:
            # Crossing the 420-year band adds a ruler to the replayed dynasty.
            world["dynasties"][0]["duration_years"] = 2000.0

        def raise_succession_pressure(world: dict[str, Any]) -> None:
            # Crossing the 0.55 threshold is the other arm of the ruler-count
            # model and adds a sixth ruler to the replayed dynasty.
            world["dynasties"][0]["succession_pressure"] = 0.9

        def zero_peak_output(world: dict[str, Any]) -> None:
            world["economy_histories"][0]["peak_gross_output_index"] = 0.0

        def unjoin_economy_region(world: dict[str, Any]) -> None:
            # Re-keying the history to a region no dynasty holds drops the
            # economy out of the replay, zeroing every output-derived weight.
            world["economy_histories"][0]["region_id"] = 5

        cases: dict[str, Callable[[dict[str, Any]], None]] = {
            "marriage_alliance_appended": append_bogus_alliance,
            "rulers_emptied": empty_rulers,
            "cadet_branches_emptied": empty_cadet_branches,
            "conflict_appended": append_bogus_conflict,
            "dynasty_duration_stretched": stretch_dynasty_duration,
            "dynasty_succession_pressure_raised": raise_succession_pressure,
            "economy_peak_output_zeroed": zero_peak_output,
            "economy_history_region_rekeyed": unjoin_economy_region,
        }
        for name, mutate in cases.items():
            with self.subTest(tamper=name):
                self.assertEqual(self._tampered(mutate), [FAILURE])
