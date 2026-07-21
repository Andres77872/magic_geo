from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.api import generate_geo_world
from magic_geo.config import WorldConfig, load_config
from magic_geo.plate_boundary_edge_validation import validate_plate_boundary_edges
from magic_geo.plate_boundary_edge_validation import _enumerate_mesh_segments


def _config(
    *,
    threads: int = 1,
    mesh_backend: str = "fibonacci_sphere",
    cell_count: int = 128,
) -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(mode="python")
    data["mesh"]["backend"] = mesh_backend
    data["mesh"]["cell_count"] = cell_count
    data["tectonics"]["plate_count"] = 8
    data["erosion"]["iterations"] = 1
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = threads
    return WorldConfig.model_validate(data)


class PlateBoundaryEdgeValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(_config())

    def test_generated_boundary_segments_replay_exact_mesh_and_kinematics(self) -> None:
        result = validate_plate_boundary_edges(self.world)

        self.assertTrue(result["passed"], result["failures"])
        metrics = result["metrics"]
        self.assertTrue(
            metrics["authoritative_reciprocal_control_volume_geometry_replayed"]
        )
        self.assertTrue(metrics["direct_unsmoothed_euler_kinematics_replayed"])
        self.assertTrue(
            metrics["opening_crust_state_and_polarity_candidate_replayed"]
        )
        self.assertTrue(metrics["explicit_unknown_physical_polarity_replayed"])
        self.assertTrue(metrics["top_level_euler_parameters_cross_checked"])
        self.assertTrue(metrics["step_rotations_replayed"])
        self.assertTrue(metrics["plate_center_history_replayed"])
        self.assertTrue(metrics["cell_plate_assignments_replayed"])
        self.assertFalse(metrics["smoothed_cell_boundary_fields_used"])
        self.assertFalse(metrics["subduction_polarity_resolved"])
        self.assertGreater(metrics["mesh_reciprocal_segment_count"], 0)
        self.assertGreater(metrics["total_boundary_segment_count"], 0)
        # The canonical enumeration preserves repeated cell-pair segments when
        # a mesh contains them; this particular seed need not contain one.
        self.assertGreaterEqual(
            metrics["duplicate_neighbor_pair_segment_count"], 0
        )
        for step in self.world["plate_motion_history"]:
            for record in step["boundary_segments"]:
                self.assertEqual(record["physical_polarity_source"], "none")
                self.assertEqual(record["physical_polarity_confidence"], 0.0)
                if record["convergence_active"]:
                    self.assertEqual(
                        record["physical_polarity_status"],
                        "unknown_unresolved",
                    )
                    self.assertEqual(record["physical_subducting_side"], "unknown")
                    self.assertEqual(record["physical_overriding_side"], "unknown")
                else:
                    self.assertEqual(
                        record["physical_polarity_status"],
                        "not_applicable_no_active_convergence",
                    )
                    self.assertEqual(record["physical_subducting_side"], "none")
                    self.assertEqual(record["physical_overriding_side"], "none")

    def test_duplicate_geodesic_segments_between_one_cell_pair_are_preserved(
        self,
    ) -> None:
        x = (1.0, 0.0, 0.0)
        y = (0.0, 1.0, 0.0)
        z = (0.0, 0.0, 1.0)

        segments = _enumerate_mesh_segments(
            [[x, y, z], [x, z, y]],
            [[1, 1, 1], [0, 0, 0]],
        )

        self.assertEqual(len(segments), 3)
        self.assertEqual([segment.mesh_segment_id for segment in segments], [0, 1, 2])
        self.assertEqual(
            [(segment.left_cell_id, segment.right_cell_id) for segment in segments],
            [(0, 1), (0, 1), (0, 1)],
        )
        self.assertEqual(
            [segment.right_edge_index for segment in segments], [2, 1, 0]
        )

    def test_transform_dominant_oblique_convergence_remains_unknown(self) -> None:
        oblique = [
            record
            for step in self.world["plate_motion_history"]
            for record in step["boundary_segments"]
            if record["direct_boundary_class"] == "transform"
            and record["direct_convergent_strength"] >= 0.08
        ]
        self.assertTrue(oblique, "fixture needs transform-dominant convergence")
        for record in oblique:
            self.assertTrue(record["convergence_active"])
            self.assertNotEqual(
                record["polarity_candidate_status"],
                "no_active_convergence",
            )
            self.assertEqual(
                record["physical_polarity_status"], "unknown_unresolved"
            )
            self.assertEqual(record["physical_subducting_side"], "unknown")
            self.assertEqual(record["physical_overriding_side"], "unknown")

    def test_smoothed_cell_boundary_fields_are_not_replay_inputs(self) -> None:
        altered = deepcopy(self.world)
        for cell in altered["cells"]:
            cell["boundary_convergent"] = 999.0
            cell["boundary_divergent"] = -999.0
            cell["boundary_transform"] = float("nan")
            cell["boundary_type"] = "tampered"

        result = validate_plate_boundary_edges(altered)

        self.assertTrue(result["passed"], result["failures"])
        self.assertFalse(result["metrics"]["smoothed_cell_boundary_fields_used"])

    def test_geometry_and_mesh_identity_mutations_fail(self) -> None:
        for mutation in ("geometry", "identity", "omission"):
            with self.subTest(mutation=mutation):
                altered = deepcopy(self.world)
                records = altered["plate_motion_history"][0]["boundary_segments"]
                self.assertTrue(records)
                if mutation == "geometry":
                    records[0]["midpoint_unit_x"] += 1.0e-5
                elif mutation == "identity":
                    records[0]["mesh_segment_id"] += 1
                else:
                    records.pop(0)
                result = validate_plate_boundary_edges(altered)
                self.assertFalse(result["passed"])
                self.assertTrue(result["failures"])

    def test_colluding_intrinsic_class_and_rate_mutations_fail_euler_replay(self) -> None:
        altered = deepcopy(self.world)
        record = altered["plate_motion_history"][0]["boundary_segments"][0]
        record["signed_opening_index"] += 0.25
        record["signed_convergence_index"] -= 0.25
        record["direct_convergent_strength"] = 1.0
        record["direct_divergent_strength"] = 0.0
        record["direct_boundary_class"] = "convergent"
        record["polarity_candidate_status"] = (
            "left_oceanic_only"
            if record["left_opening_oceanic_like"]
            and not record["right_opening_oceanic_like"]
            else "ambiguous_both_oceanic"
        )

        result = validate_plate_boundary_edges(altered)

        self.assertFalse(result["passed"])
        self.assertTrue(result["failures"])

    def test_coherent_snapshot_speed_and_record_rescaling_fails_top_level_link(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        factor = 0.5
        vector_fields = (
            "left_euler_velocity_x_km_per_ma",
            "left_euler_velocity_y_km_per_ma",
            "left_euler_velocity_z_km_per_ma",
            "right_euler_velocity_x_km_per_ma",
            "right_euler_velocity_y_km_per_ma",
            "right_euler_velocity_z_km_per_ma",
            "relative_velocity_x_km_per_ma",
            "relative_velocity_y_km_per_ma",
            "relative_velocity_z_km_per_ma",
            "signed_opening_rate_km_per_ma",
            "signed_convergence_rate_km_per_ma",
            "signed_slip_rate_km_per_ma",
            "signed_opening_index",
            "signed_convergence_index",
            "signed_slip_index",
        )
        for step in altered["plate_motion_history"]:
            for snapshot in step["plates"]:
                snapshot["intrinsic_angular_speed"] *= factor
                snapshot["step_rotation_deg"] *= factor
            for record in step["boundary_segments"]:
                for field in vector_fields:
                    record[field] *= factor
                convergence = max(
                    0.0, min(1.0, record["signed_convergence_index"] * 1.25)
                )
                divergence = max(
                    0.0, min(1.0, record["signed_opening_index"] * 1.25)
                )
                transform = max(
                    0.0,
                    min(
                        1.0,
                        (
                            abs(record["signed_slip_index"])
                            - abs(record["signed_opening_index"]) * 0.35
                        )
                        * 1.05,
                    ),
                )
                record["direct_convergent_strength"] = convergence
                record["direct_divergent_strength"] = divergence
                record["direct_transform_strength"] = transform
                convergence_active = convergence >= 0.08
                record["convergence_active"] = convergence_active
                maximum = max(convergence, divergence, transform)
                if maximum < 0.08:
                    boundary_class = "inactive"
                elif convergence == maximum:
                    boundary_class = "convergent"
                elif divergence == maximum:
                    boundary_class = "divergent"
                else:
                    boundary_class = "transform"
                record["direct_boundary_class"] = boundary_class
                if not convergence_active:
                    status = "no_active_convergence"
                elif not record["left_opening_crust_state_available"] or not record[
                    "right_opening_crust_state_available"
                ]:
                    status = "unresolved_missing_opening_crust_state"
                elif record["left_opening_oceanic_like"] and not record[
                    "right_opening_oceanic_like"
                ]:
                    status = "left_oceanic_only"
                elif record["right_opening_oceanic_like"] and not record[
                    "left_opening_oceanic_like"
                ]:
                    status = "right_oceanic_only"
                elif record["left_opening_oceanic_like"]:
                    status = "ambiguous_both_oceanic"
                else:
                    status = "unresolved_no_oceanic_side"
                record["polarity_candidate_status"] = status
                record["candidate_subducting_side"] = (
                    "left"
                    if status == "left_oceanic_only"
                    else "right"
                    if status == "right_oceanic_only"
                    else "none"
                )
                record["candidate_overriding_side"] = (
                    "right"
                    if status == "left_oceanic_only"
                    else "left"
                    if status == "right_oceanic_only"
                    else "none"
                )
                record["physical_polarity_status"] = (
                    "unknown_unresolved"
                    if convergence_active
                    else "not_applicable_no_active_convergence"
                )
                record["physical_subducting_side"] = (
                    "unknown" if convergence_active else "none"
                )
                record["physical_overriding_side"] = (
                    "unknown" if convergence_active else "none"
                )

        result = validate_plate_boundary_edges(altered)

        self.assertFalse(result["passed"])
        self.assertTrue(
            any("top-level plate speed" in failure for failure in result["failures"]),
            result["failures"],
        )

    def test_snapshot_axis_must_mirror_top_level_plate_axis(self) -> None:
        altered = deepcopy(self.world)
        for step in altered["plate_motion_history"]:
            step["plates"][0]["rotation_axis"] = [
                -component for component in step["plates"][0]["rotation_axis"]
            ]

        result = validate_plate_boundary_edges(altered)

        self.assertFalse(result["passed"])
        self.assertTrue(
            any("top-level plate axis" in failure for failure in result["failures"]),
            result["failures"],
        )

    def test_cell_plate_assignment_must_replay_nearest_snapshot_center(self) -> None:
        altered = deepcopy(self.world)
        step = altered["plate_motion_history"][0]
        step["cell_plate_ids"][0] = (step["cell_plate_ids"][0] + 1) % step[
            "plate_count"
        ]

        result = validate_plate_boundary_edges(altered)

        self.assertFalse(result["passed"])
        self.assertTrue(
            any("cell_plate_ids do not replay" in failure for failure in result["failures"]),
            result["failures"],
        )

    def test_snapshot_center_must_replay_from_top_level_center_history(self) -> None:
        altered = deepcopy(self.world)
        center = altered["plate_motion_history"][0]["plates"][0]["center"]
        altered["plate_motion_history"][0]["plates"][0]["center"] = [
            -component for component in center
        ]

        result = validate_plate_boundary_edges(altered)

        self.assertFalse(result["passed"])
        self.assertTrue(
            any("center does not replay" in failure for failure in result["failures"]),
            result["failures"],
        )

    def test_opening_crust_and_nonfinite_mutations_fail(self) -> None:
        source_record = self.world["plate_motion_history"][0]["boundary_segments"][0]
        mutations = (
            (
                "left_opening_crust_type",
                (int(source_record["left_opening_crust_type"]) + 1) % 9,
            ),
            (
                "left_opening_crust_state_available",
                not bool(source_record["left_opening_crust_state_available"]),
            ),
            (
                "left_opening_oceanic_like",
                not bool(source_record["left_opening_oceanic_like"]),
            ),
            ("signed_slip_rate_km_per_ma", float("inf")),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                altered = deepcopy(self.world)
                record = altered["plate_motion_history"][0]["boundary_segments"][0]
                record[field] = value
                result = validate_plate_boundary_edges(altered)
                self.assertFalse(result["passed"])
                self.assertTrue(result["failures"])

    def test_partial_unavailable_opening_crust_state_fails_closed(self) -> None:
        altered = deepcopy(self.world)
        ledger = altered["plate_motion_history"][0]["crust_overlap_ledger"]
        ledger["remapped_crust_age_ma_by_cell"][0] = 1.0
        ledger["remapped_crust_thickness_km_by_cell"][0] = 0.0

        result = validate_plate_boundary_edges(altered)

        self.assertFalse(result["passed"])
        self.assertTrue(result["failures"])

    def test_canonical_unavailable_opening_state_replays_missing_status(self) -> None:
        altered = deepcopy(self.world)
        step = altered["plate_motion_history"][0]
        first = step["boundary_segments"][0]
        cell_id = int(first["left_cell_id"])
        ledger = step["crust_overlap_ledger"]
        ledger["remapped_crust_age_ma_by_cell"][cell_id] = 0.0
        ledger["remapped_crust_thickness_km_by_cell"][cell_id] = 0.0
        affected = 0
        for record in step["boundary_segments"]:
            side = None
            if record["left_cell_id"] == cell_id:
                side = "left"
            elif record["right_cell_id"] == cell_id:
                side = "right"
            if side is None:
                continue
            affected += 1
            record[f"{side}_opening_crust_age_ma"] = 0.0
            record[f"{side}_opening_crust_thickness_km"] = 0.0
            record[f"{side}_opening_crust_state_available"] = False
            record[f"{side}_opening_oceanic_like"] = False
            record["polarity_candidate_status"] = (
                "unresolved_missing_opening_crust_state"
                if record["convergence_active"]
                else "no_active_convergence"
            )
            record["candidate_subducting_side"] = "none"
            record["candidate_overriding_side"] = "none"

        result = validate_plate_boundary_edges(altered)

        self.assertGreater(affected, 0)
        self.assertTrue(result["passed"], result["failures"])

    def test_model_cannot_claim_resolved_physical_polarity_or_slabs(self) -> None:
        for field in (
            "physical_subduction_polarity_resolved",
            "physical_slab_geometry_resolved",
            "slab_selection_resolved",
            "slab_transfer_resolved",
            "physical_material_fate_resolved",
            "boundary_segments_drive_smoothed_cell_boundary_forcing",
            "boundary_segments_drive_slab_transfers",
        ):
            with self.subTest(field=field):
                altered = deepcopy(self.world)
                altered["plate_boundary_segment_model"][field] = True
                result = validate_plate_boundary_edges(altered)
                self.assertFalse(result["passed"])
                self.assertTrue(result["failures"])

        altered = deepcopy(self.world)
        altered["plate_boundary_segment_model"][
            "polarity_candidate_is_physical_decision"
        ] = True
        result = validate_plate_boundary_edges(altered)
        self.assertFalse(result["passed"])
        self.assertTrue(result["failures"])

        altered = deepcopy(self.world)
        altered["plate_boundary_segment_model"][
            "physical_polarity_unknown_state_explicit"
        ] = False
        result = validate_plate_boundary_edges(altered)
        self.assertFalse(result["passed"])
        self.assertTrue(result["failures"])

    def test_candidate_sides_cannot_be_promoted_to_physical_polarity(self) -> None:
        source = next(
            record
            for step in self.world["plate_motion_history"]
            for record in step["boundary_segments"]
            if record["convergence_active"]
        )
        self.assertEqual(source["physical_polarity_status"], "unknown_unresolved")
        mutations = {
            "physical_polarity_status": "resolved",
            "physical_polarity_source": "oceanic_side_candidate",
            "physical_subducting_side": source["candidate_subducting_side"],
            "physical_overriding_side": source["candidate_overriding_side"],
            "physical_polarity_confidence": 1.0e-13,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                altered = deepcopy(self.world)
                record = next(
                    item
                    for step in altered["plate_motion_history"]
                    for item in step["boundary_segments"]
                    if item["segment_id"] == source["segment_id"]
                    and item["mesh_segment_id"] == source["mesh_segment_id"]
                    and item["convergence_active"]
                )
                record[field] = value
                result = validate_plate_boundary_edges(altered)
                self.assertFalse(result["passed"])
                self.assertTrue(result["failures"])

    def test_algorithm_constants_require_exact_canonical_literals(self) -> None:
        mutations = {
            "reciprocal_endpoint_match_tolerance_chord": 1.01e-10,
            "direct_boundary_class_inactive_threshold": 0.08000000000000002,
            "euler_axis_unit_tolerance": 2.9e-12,
            "unit_sphere_vector_norm_tolerance": 3.1e-12,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                altered = deepcopy(self.world)
                altered["plate_boundary_segment_model"][field] = value

                result = validate_plate_boundary_edges(altered)

                self.assertFalse(result["passed"])
                self.assertTrue(result["failures"])

    def test_malformed_payload_fails_closed(self) -> None:
        for payload in ({}, {"cells": "invalid"}, {"cells": []}):
            with self.subTest(payload=payload):
                result = validate_plate_boundary_edges(payload)
                self.assertFalse(result["passed"])
                self.assertTrue(result["failures"])

    def test_local_edge_resource_cap_fails_before_segment_enumeration(self) -> None:
        altered = deepcopy(self.world)
        for cell in altered["cells"]:
            vertex = cell["control_volume_vertices_3d"][0]
            neighbor = cell["control_volume_edge_neighbor_ids"][0]
            cell["control_volume_vertices_3d"] = [vertex] * 64
            cell["control_volume_edge_neighbor_ids"] = [neighbor] * 64

        result = validate_plate_boundary_edges(altered)

        self.assertFalse(result["passed"])
        self.assertTrue(
            any("local edge count cap" in failure for failure in result["failures"]),
            result["failures"],
        )


class GeodesicDuplicateBoundaryEdgeValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(
            _config(
                mesh_backend="geodesic_icosahedron",
                cell_count=162,
            )
        )

    def test_generated_geodesic_duplicate_segments_replay_end_to_end(self) -> None:
        result = validate_plate_boundary_edges(self.world)

        self.assertTrue(result["passed"], result["failures"])
        self.assertGreater(
            result["metrics"]["duplicate_neighbor_pair_segment_count"], 0
        )
        self.assertGreater(
            result["metrics"]["mesh_reciprocal_segment_count"], 0
        )
        self.assertGreater(
            result["metrics"]["total_boundary_segment_count"], 0
        )
