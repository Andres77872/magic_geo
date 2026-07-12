from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.api import generate_geo_world
from magic_geo.config import WorldConfig, load_config
from magic_geo.crust_overlap_candidate_fate_validation import (
    _expected_pair_record,
    validate_crust_overlap_candidate_fate,
)
from magic_geo.crust_transport_validation import validate_crust_overlap_transport


def _small_earth_config() -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    # Exercise the candidate-bearing overlap regime explicitly; the checked
    # Earth default is not itself a stable witness for every diagnostic role.
    data["tectonics"]["plate_motion_scale_deg_per_step"] = 10.0
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    return WorldConfig.model_validate(data)


def _all_class_candidates(world: dict) -> list[tuple[dict, dict]]:
    return [
        (step, candidate)
        for step in world["plate_motion_history"]
        for candidate in step["crust_overlap_candidate_fate_ledger"][
            "overlap_class_candidates"
        ]
    ]


def _pair_by_id(step: dict, pair_id: int) -> dict:
    return next(
        pair
        for pair in step["crust_overlap_candidate_fate_ledger"][
            "boundary_pair_evidence"
        ]
        if pair["pair_id"] == pair_id
    )


class CrustOverlapCandidateFateValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(_small_earth_config())

    def test_generated_crosswalk_replays_every_pair_class_and_area_partition(
        self,
    ) -> None:
        replay = validate_crust_overlap_candidate_fate(self.world)

        self.assertTrue(replay["passed"], replay["failures"])
        metrics = replay["metrics"]
        self.assertTrue(metrics["independent_boundary_root_replay_passed"])
        self.assertTrue(metrics["independent_membership_root_replay_passed"])
        self.assertTrue(metrics["every_boundary_pair_consensus_replayed"])
        self.assertTrue(metrics["every_overlap_excess_class_candidate_replayed"])
        self.assertTrue(metrics["overlap_excess_partition_closed"])
        self.assertFalse(metrics["physical_material_fate_resolved"])
        self.assertFalse(metrics["slab_selection_resolved"])
        self.assertFalse(metrics["slab_transfer_resolved"])
        self.assertFalse(metrics["state_mutation_performed"])
        self.assertTrue(metrics["deterministic_crosswalk_authoritative"])
        self.assertTrue(metrics["pair_wide_consensus_only"])
        for field in (
            "candidate_allocation_authoritative",
            "local_segment_link_resolved",
            "connected_atom_topology_resolved",
            "local_fragment_topology_resolved",
            "swept_area_calculated",
            "crust_material_shadow_mutation_performed",
            "crust_reservoir_mutation_performed",
        ):
            self.assertIs(metrics[field], False, field)

        model = self.world["crust_overlap_candidate_fate_model"]
        self.assertTrue(model["deterministic_crosswalk_authoritative"])
        self.assertTrue(model["pair_wide_consensus_only"])
        self.assertTrue(model["destination_endpoint_incidence_resolved"])
        self.assertTrue(
            model[
                "upstream_segment_physical_source_and_confidence_required_for_interpretation"
            ]
        )
        for field in (
            "candidate_allocation_authoritative",
            "pair_evidence_standalone_physical_provenance_complete",
            "physical_polarity_authoritative",
            "physical_polarity_resolved",
            "physical_material_fate_authoritative",
            "physical_material_fate_resolved",
            "slab_selection_authoritative",
            "slab_selection_resolved",
            "slab_transfer_authoritative",
            "slab_transfer_resolved",
            "state_mutation_performed",
            "crust_material_shadow_mutation_performed",
            "crust_reservoir_mutation_performed",
            "swept_area_calculated",
            "local_segment_link_resolved",
            "connected_atom_topology_resolved",
            "local_fragment_topology_resolved",
        ):
            self.assertIs(model[field], False, field)

        for step_id, step in enumerate(self.world["plate_motion_history"]):
            fate = step["crust_overlap_candidate_fate_ledger"]
            self.assertEqual(
                fate["source_plate_assignment_step_id"],
                0 if step_id == 0 else step_id - 1,
            )
            self.assertEqual(fate["boundary_plate_assignment_step_id"], step_id)
            pairs = fate["boundary_pair_evidence"]
            self.assertEqual(
                [(pair["plate_low_id"], pair["plate_high_id"]) for pair in pairs],
                sorted(
                    (pair["plate_low_id"], pair["plate_high_id"])
                    for pair in pairs
                ),
            )
            self.assertEqual(
                sorted(
                    segment_id
                    for pair in pairs
                    for segment_id in pair["segment_ids"]
                ),
                list(range(len(step["boundary_segments"]))),
            )

            membership = step["crust_overlap_ledger"][
                "coverage_membership_area_class_ledger"
            ]
            expected_class_ids = [
                class_id
                for class_id, multiplicity in enumerate(
                    membership["multiplicity"]
                )
                if multiplicity >= 2
            ]
            self.assertEqual(
                [
                    candidate["membership_area_class_id"]
                    for candidate in fate["overlap_class_candidates"]
                ],
                expected_class_ids,
            )

    def test_generated_multiplicity_above_two_and_ambiguous_classes_fail_closed(
        self,
    ) -> None:
        candidates = [candidate for _, candidate in _all_class_candidates(self.world)]

        above_two = [candidate for candidate in candidates if candidate["multiplicity"] > 2]
        self.assertTrue(above_two)
        self.assertTrue(
            all(
                candidate["assignment_status"] == "unknown_nonbinary_membership"
                and candidate["candidate_subducting_contributor_id"] == -1
                and candidate["candidate_overriding_contributor_id"] == -1
                for candidate in above_two
            )
        )
        self.assertTrue(
            any(
                candidate["assignment_status"]
                == "unknown_no_uniform_pair_polarity_evidence"
                for candidate in candidates
            )
        )
        self.assertTrue(
            any(
                candidate["assignment_status"]
                == "unknown_no_same_step_endpoint_incidence"
                for candidate in candidates
            )
        )

    def test_candidate_role_ids_are_global_contributor_csr_indices(self) -> None:
        located: tuple[dict, dict, dict, int] | None = None
        for step, candidate in _all_class_candidates(self.world):
            contributor_id = candidate["candidate_subducting_contributor_id"]
            if contributor_id < 0:
                continue
            membership = step["crust_overlap_ledger"][
                "coverage_membership_area_class_ledger"
            ]
            class_id = candidate["membership_area_class_id"]
            begin = membership["contributor_offsets"][class_id]
            end = membership["contributor_offsets"][class_id + 1]
            self.assertIn(contributor_id, range(begin, end))
            if membership["source_cell_ids"][contributor_id] != contributor_id:
                located = (step, candidate, membership, contributor_id)
                break
        self.assertIsNotNone(located)

        altered = deepcopy(self.world)
        original_step, original_candidate, membership, contributor_id = located  # type: ignore[misc]
        step_id = original_step["id"]
        class_id = original_candidate["membership_area_class_id"]
        mutated = next(
            candidate
            for candidate in altered["plate_motion_history"][step_id][
                "crust_overlap_candidate_fate_ledger"
            ]["overlap_class_candidates"]
            if candidate["membership_area_class_id"] == class_id
        )
        mutated["candidate_subducting_contributor_id"] = membership[
            "source_cell_ids"
        ][contributor_id]

        replay = validate_crust_overlap_candidate_fate(altered)

        self.assertFalse(replay["passed"])
        self.assertTrue(
            any("candidate_subducting_contributor_id" in failure for failure in replay["failures"]),
            replay["failures"],
        )

    def test_pair_roles_and_class_roles_cannot_collude(self) -> None:
        altered = deepcopy(self.world)
        step, candidate = next(
            (step, candidate)
            for step, candidate in _all_class_candidates(altered)
            if candidate["assignment_status"]
            == "uniform_oceanic_side_heuristic_candidate"
        )
        pair = _pair_by_id(step, candidate["boundary_pair_evidence_id"])
        pair["heuristic_subducting_plate_id"], pair[
            "heuristic_overriding_plate_id"
        ] = (
            pair["heuristic_overriding_plate_id"],
            pair["heuristic_subducting_plate_id"],
        )
        for other in step["crust_overlap_candidate_fate_ledger"][
            "overlap_class_candidates"
        ]:
            if (
                other["boundary_pair_evidence_id"] == pair["pair_id"]
                and other["assignment_status"]
                == "uniform_oceanic_side_heuristic_candidate"
            ):
                other["candidate_subducting_contributor_id"], other[
                    "candidate_overriding_contributor_id"
                ] = (
                    other["candidate_overriding_contributor_id"],
                    other["candidate_subducting_contributor_id"],
                )

        replay = validate_crust_overlap_candidate_fate(altered)

        self.assertFalse(replay["passed"])
        self.assertTrue(
            any("heuristic_subducting_plate_id" in failure for failure in replay["failures"]),
            replay["failures"],
        )

    def test_omission_duplication_reordering_and_step_linkage_are_rejected(self) -> None:
        mutations = {}

        def omit_class(world: dict) -> None:
            del world["plate_motion_history"][1][
                "crust_overlap_candidate_fate_ledger"
            ]["overlap_class_candidates"][0]

        mutations["omitted class"] = omit_class

        def duplicate_pair(world: dict) -> None:
            pairs = world["plate_motion_history"][1][
                "crust_overlap_candidate_fate_ledger"
            ]["boundary_pair_evidence"]
            pairs.insert(0, deepcopy(pairs[0]))

        mutations["duplicated pair"] = duplicate_pair

        def reorder_classes(world: dict) -> None:
            classes = world["plate_motion_history"][1][
                "crust_overlap_candidate_fate_ledger"
            ]["overlap_class_candidates"]
            classes[0], classes[1] = classes[1], classes[0]

        mutations["reordered classes"] = reorder_classes

        def stale_step_link(world: dict) -> None:
            world["plate_motion_history"][2][
                "crust_overlap_candidate_fate_ledger"
            ]["source_plate_assignment_step_id"] = 2

        mutations["stale step link"] = stale_step_link

        for label, mutation in mutations.items():
            with self.subTest(label=label):
                altered = deepcopy(self.world)
                mutation(altered)
                replay = validate_crust_overlap_candidate_fate(altered)
                self.assertFalse(replay["passed"], label)

    def test_colluding_area_headlines_and_model_claims_are_rejected(self) -> None:
        altered = deepcopy(self.world)
        fate = altered["plate_motion_history"][1][
            "crust_overlap_candidate_fate_ledger"
        ]
        fate["unresolved_candidate_excess_area_km2"] += 1.0
        fate["accounted_overlap_excess_area_km2"] += 1.0
        fate["candidate_partition_residual_km2"] += 1.0

        replay = validate_crust_overlap_candidate_fate(altered)

        self.assertFalse(replay["passed"])
        self.assertTrue(
            any("membership-class assignments" in failure for failure in replay["failures"]),
            replay["failures"],
        )

        for field in (
            "physical_material_fate_resolved",
            "slab_selection_resolved",
            "slab_transfer_resolved",
            "state_mutation_performed",
            "candidate_allocation_authoritative",
            "local_segment_link_resolved",
            "connected_atom_topology_resolved",
        ):
            with self.subTest(field=field):
                altered = deepcopy(self.world)
                altered["crust_overlap_candidate_fate_model"][field] = True
                self.assertFalse(
                    validate_crust_overlap_candidate_fate(altered)["passed"]
                )

    def test_colluding_root_global_and_candidate_residual_shift_is_rejected(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        step = altered["plate_motion_history"][1]
        overlap = step["crust_overlap_ledger"]
        fate = step["crust_overlap_candidate_fate_ledger"]
        delta = overlap["global_overlap_excess_area_km2"] * 1.0e-9
        overlap["global_overlap_excess_area_km2"] += delta
        fate["candidate_partition_residual_km2"] -= delta

        replay = validate_crust_overlap_candidate_fate(altered)

        self.assertFalse(replay["passed"])
        self.assertTrue(
            any("global overlap-excess rows" in failure for failure in replay["failures"]),
            replay["failures"],
        )

    def test_coherent_per_cell_root_shift_fails_fragment_to_class_gamma_proof(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        step = altered["plate_motion_history"][1]
        overlap = step["crust_overlap_ledger"]
        fate = step["crust_overlap_candidate_fate_ledger"]
        rows = overlap["overlap_excess_area_km2_by_cell"]
        destination = max(range(len(rows)), key=rows.__getitem__)
        self.assertGreater(rows[destination], 0.0)
        rows[destination] += 1.0e-4
        replayed_global = 0.0
        for row in rows:
            replayed_global += row
        overlap["global_overlap_excess_area_km2"] = replayed_global
        overlap["global_gap_overlap_balance_residual_km2"] += 1.0e-4
        areas = [cell["area_km2"] for cell in altered["cells"]]
        overlap["maximum_destination_partition_closure_error_km2"] = max(
            max(
                abs(union + gap - area),
                abs(union + excess - coverage),
            )
            for union, gap, area, excess, coverage in zip(
                overlap["covered_union_area_km2_by_cell"],
                overlap["uncovered_gap_area_km2_by_cell"],
                areas,
                rows,
                overlap["coverage_area_sum_km2_by_cell"],
                strict=True,
            )
        )
        altered["summary"][
            "maximum_crust_destination_partition_closure_error_km2"
        ] = max(
            motion_step["crust_overlap_ledger"][
                "maximum_destination_partition_closure_error_km2"
            ]
            for motion_step in altered["plate_motion_history"][1:]
        )
        fate["candidate_partition_residual_km2"] = (
            fate["accounted_overlap_excess_area_km2"] - replayed_global
        )

        root_replay = validate_crust_overlap_transport(altered)
        self.assertTrue(root_replay["passed"], root_replay["failures"])
        replay = validate_crust_overlap_candidate_fate(altered)

        self.assertFalse(replay["passed"])
        self.assertTrue(
            any("fragment-to-class" in failure for failure in replay["failures"]),
            replay["failures"],
        )

    def test_pair_segment_reference_resource_cap_is_checked_before_replay(self) -> None:
        altered = deepcopy(self.world)
        step = altered["plate_motion_history"][1]
        pair = step["crust_overlap_candidate_fate_ledger"][
            "boundary_pair_evidence"
        ][0]
        pair["segment_ids"] = list(range(len(step["boundary_segments"]) + 1))

        replay = validate_crust_overlap_candidate_fate(altered)

        self.assertFalse(replay["passed"])
        self.assertTrue(
            any("resource cap" in failure for failure in replay["failures"]),
            replay["failures"],
        )

    def test_pair_consensus_helper_handles_future_resolved_and_mixed_evidence(
        self,
    ) -> None:
        def record(
            segment_id: int,
            *,
            left_plate: int,
            right_plate: int,
            physical: str,
        ) -> dict:
            payload = {
                "segment_id": segment_id,
                "left_plate_id": left_plate,
                "right_plate_id": right_plate,
                "convergence_active": True,
                "polarity_candidate_status": "left_oceanic_only",
                "candidate_subducting_side": "left",
                "candidate_overriding_side": "right",
            }
            if physical == "unknown":
                payload.update(
                    {
                        "physical_polarity_status": "unknown_unresolved",
                        "physical_polarity_source": "none",
                        "physical_subducting_side": "unknown",
                        "physical_overriding_side": "unknown",
                        "physical_polarity_confidence": 0.0,
                    }
                )
            else:
                payload.update(
                    {
                        "physical_polarity_status": "resolved",
                        "physical_polarity_source": "supplied_constraint",
                        "physical_subducting_side": physical,
                        "physical_overriding_side": (
                            "right" if physical == "left" else "left"
                        ),
                        "physical_polarity_confidence": 0.75,
                    }
                )
            return payload

        uniform = _expected_pair_record(
            (2, 5),
            [
                record(0, left_plate=2, right_plate=5, physical="left"),
                record(1, left_plate=5, right_plate=2, physical="right"),
            ],
        )
        self.assertEqual(
            uniform["physical_consensus_status"],
            "all_active_resolved_polarity_uniform",
        )
        self.assertEqual(
            (
                uniform["physical_subducting_plate_id"],
                uniform["physical_overriding_plate_id"],
            ),
            (2, 5),
        )

        mixed = _expected_pair_record(
            (2, 5),
            [
                record(0, left_plate=2, right_plate=5, physical="left"),
                record(1, left_plate=2, right_plate=5, physical="unknown"),
            ],
        )
        self.assertEqual(
            mixed["physical_consensus_status"],
            "all_active_mixed_resolved_and_unknown",
        )
        self.assertEqual(mixed["physical_subducting_plate_id"], -1)

    def test_candidate_area_serialization_is_not_blanket_tolerant(self) -> None:
        altered = deepcopy(self.world)
        fate = next(
            step["crust_overlap_candidate_fate_ledger"]
            for step in altered["plate_motion_history"]
            if step["crust_overlap_candidate_fate_ledger"][
                "unresolved_candidate_excess_area_km2"
            ]
            > 0.0
        )
        value = fate["unresolved_candidate_excess_area_km2"]
        fate["unresolved_candidate_excess_area_km2"] = value + max(
            1.0e-6, 4096.0 * math.ulp(value)
        )

        self.assertFalse(validate_crust_overlap_candidate_fate(altered)["passed"])


if __name__ == "__main__":
    import unittest

    unittest.main()
