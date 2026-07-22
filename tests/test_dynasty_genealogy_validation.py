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
    dynasties, economy histories and conflicts in the payload, so a passing
    payload can only come from a generated world. Failure cases therefore
    start from a private deep copy of that world and apply exactly one
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

        rulers = self.world["rulers"]
        dynasty = self.world["dynasties"][0]
        branches = self.world["cadet_branches"]

        # The 128-cell world holds a single dynasty. Pin the causal inputs the
        # rest of this test derives its expectations from, so a drift in the
        # upstream generator is reported here rather than silently changing
        # what "the replayed value" means.
        self.assertEqual(len(self.world["dynasties"]), 1)
        self.assertEqual(dynasty["region_id"], 0)
        self.assertEqual(dynasty["duration_years"], 1304.8103)
        self.assertEqual(dynasty["start_year_bp"], 1304.8103)
        self.assertEqual(dynasty["end_year_bp"], 0.0)
        self.assertEqual(dynasty["succession_pressure"], 0.242)
        self.assertEqual(dynasty["dynastic_continuity_index"], 0.8076)
        self.assertEqual(dynasty["legitimacy_index"], 0.5621)
        self.assertEqual(dynasty["lineage_depth"], 0)

        economy = self.world["economy_histories"]
        self.assertEqual(len(economy), 1)
        self.assertEqual(economy[0]["region_id"], 0)
        self.assertEqual(economy[0]["peak_gross_output_index"], 564.55029)
        self.assertEqual(economy[0]["peak_treasury_index"], 63.970702)
        self.assertEqual(self.world["conflicts"], [])

        # ``dynasty_duration_pressure_bounded_two_to_six_rulers_v1``:
        # ``int(1304.8103 // 420) + 2`` is five, and the 0.242 pressure stays
        # under the 0.55 threshold that would add a sixth ruler.
        self.assertEqual(len(rulers), 5)
        self.assertEqual(self.world["marriage_alliances"], [])

        # ``deterministic_root_and_regnal_number_v1``: root index advances by
        # three per reign for dynasty 0 at lineage depth 0, regnal number is
        # the reign index plus one rendered as a Roman numeral.
        self.assertEqual(
            [ruler["name"] for ruler in rulers],
            ["Aren I", "Daren II", "Galen III", "Joren IV", "Maren V"],
        )
        self.assertEqual([ruler["regnal_number"] for ruler in rulers], [1, 2, 3, 4, 5])

        # ``ordered_predecessor_successor_and_parent_links_v1``.
        self.assertEqual(
            [ruler["predecessor_ruler_id"] for ruler in rulers], [-1, 0, 1, 2, 3]
        )
        self.assertEqual(
            [ruler["successor_ruler_id"] for ruler in rulers], [1, 2, 3, 4, -1]
        )
        self.assertEqual(
            [ruler["parent_ruler_id"] for ruler in rulers], [-1, 0, 0, 1, 2]
        )
        self.assertEqual(
            [ruler["ruler_lineage_depth"] for ruler in rulers], [0, 1, 2, 3, 4]
        )

        # ``equal_dynasty_duration_partition_v1``: 1304.8103 / 5 == 260.96206
        # per reign, counting down from ``start_year_bp`` to ``end_year_bp``.
        self.assertEqual(
            [ruler["reign_start_year_bp"] for ruler in rulers],
            [1304.8103, 1043.84824, 782.88618, 521.92412, 260.96206],
        )
        self.assertEqual(
            [ruler["reign_end_year_bp"] for ruler in rulers],
            [1043.84824, 782.88618, 521.92412, 260.96206, 0.0],
        )
        self.assertEqual(
            [ruler["reign_length_years"] for ruler in rulers], [260.96206] * 5
        )
        # ``birth_year_bp`` leads the reign by ``24 + succession_pressure * 18``.
        self.assertEqual(rulers[0]["birth_year_bp"], 1333.1663)

        # ``dynasty_continuity_pressure_economy_treasury_conflict_v1``: the
        # attribute weights do not depend on the reign index, so every ruler
        # shares one legitimacy, prestige and patronage value. Only the
        # succession risk moves, by 0.10 * index / (count - 1).
        self.assertEqual(
            [ruler["legitimacy_index"] for ruler in rulers], [0.612096] * 5
        )
        self.assertEqual(
            [ruler["succession_claim_strength"] for ruler in rulers], [0.666837] * 5
        )
        self.assertEqual(
            [ruler["military_prestige_index"] for ruler in rulers], [0.113819] * 5
        )
        self.assertEqual(
            [ruler["economic_patronage_index"] for ruler in rulers], [0.473514] * 5
        )
        self.assertEqual(
            [ruler["succession_crisis_risk"] for ruler in rulers],
            [0.194737, 0.219737, 0.244737, 0.269737, 0.294737],
        )

        # ``second_ruler_founder_with_next_three_heirs_v1``. The year bounds are
        # pinned as literals rather than compared back to the ruler records:
        # the last reign ends at 0.0, so a ``branch_end_year_bp`` cross-check
        # against ``rulers[4]`` would hold for any rule that also yields zero.
        self.assertEqual(len(branches), 1)
        self.assertEqual(branches[0]["founder_ruler_id"], 1)
        self.assertEqual(branches[0]["heir_ruler_ids"], [2, 3, 4])
        self.assertEqual(branches[0]["branch_start_year_bp"], 1043.84824)
        self.assertEqual(
            branches[0]["branch_start_year_bp"], rulers[1]["reign_start_year_bp"]
        )
        self.assertEqual(branches[0]["branch_end_year_bp"], 0.0)
        self.assertEqual(
            branches[0]["branch_end_year_bp"], rulers[4]["reign_end_year_bp"]
        )
        self.assertEqual(branches[0]["claim_strength"], 0.547883)
        self.assertEqual(branches[0]["cadet_legitimacy_index"], 0.651197)
        self.assertEqual(
            [ruler["cadet_branch_id"] for ruler in rulers], [-1, 0, 0, 0, 0]
        )

        # Dynasty annotations mirror the replayed genealogy.
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
        self.assertEqual(summary["mean_ruler_legitimacy_index"], 0.612096)
        self.assertEqual(summary["mean_succession_crisis_risk"], 0.244737)
        self.assertEqual(summary["mean_marriage_alliance_strength"], 0.0)
        self.assertEqual(summary["mean_cadet_branch_claim_strength"], 0.547883)

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
