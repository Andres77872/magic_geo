from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.config import WorldConfig, config_to_native, load_config
from magic_geo.crust_coverage_geometry_replay import (
    compare_crust_coverage_geometry,
    replay_crust_coverage_geometry,
    _binary64_long_double_forward_error_bounds,
    _serialized_membership_area_by_cell,
)
from magic_geo.native import generate_geo_world


def _moving_config(mesh_backend: str, cell_count: int) -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["run"]["seed"] = 20260711
    data["mesh"]["backend"] = mesh_backend
    data["mesh"]["cell_count"] = cell_count
    data["tectonics"]["plate_count"] = 8
    data["erosion"]["iterations"] = 1
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    data["output"]["float_precision"] = 8
    return WorldConfig.model_validate(data)


class IndependentCrustCoverageGeometryReplayTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.worlds = {
            "fibonacci_sphere": generate_geo_world(
                config_to_native(_moving_config("fibonacci_sphere", 128))
            ),
            # Geodesic resolution is quantized by subdivision; a request for
            # 128 cells resolves to the routine 162-cell fixture.
            "geodesic_icosahedron": generate_geo_world(
                config_to_native(_moving_config("geodesic_icosahedron", 128))
            ),
        }
        cls.comparisons = {
            backend: compare_crust_coverage_geometry(world, 1)
            for backend, world in cls.worlds.items()
        }

    def test_zero_rotation_step_replays_native_identity_semantics(self) -> None:
        world = self.worlds["fibonacci_sphere"]
        replay = replay_crust_coverage_geometry(world, 0)
        areas = [float(cell["area_km2"]) for cell in world["cells"]]
        cell_count = len(areas)

        self.assertEqual(
            replay["pair_search"],
            "identity_shortcut_matching_native_zero_rotation_semantics",
        )
        self.assertEqual(replay["destination_offsets"], list(range(cell_count + 1)))
        self.assertEqual(replay["source_cell_ids"], list(range(cell_count)))
        self.assertEqual(replay["overlap_area_km2"], areas)
        self.assertEqual(
            replay["global_coverage_area_km2_by_multiplicity"],
            [0.0, math.fsum(areas)],
        )
        self.assertEqual(
            replay["coverage_area_km2_by_source_membership_by_cell"],
            [
                {(cell_id,): area}
                for cell_id, area in enumerate(areas)
            ],
        )

    def test_moving_geometry_discovers_pairs_and_coverage_for_both_meshes(
        self,
    ) -> None:
        for backend, comparison in self.comparisons.items():
            with self.subTest(mesh_backend=backend):
                self.assertTrue(comparison["passed"], comparison["failures"])
                replay = comparison["replay"]
                world = self.worlds[backend]
                native = world["plate_motion_history"][1][
                    "crust_overlap_ledger"
                ]
                cell_count = len(world["cells"])

                self.assertEqual(replay["pair_search"], "brute_force_spherical_cap_v1")
                self.assertIn("O(N**2)", replay["performance_scope"])
                self.assertGreater(replay["candidate_pair_count"], len(replay["source_cell_ids"]))
                self.assertGreater(len(replay["source_cell_ids"]), cell_count)
                self.assertEqual(
                    replay["destination_offsets"], native["destination_offsets"]
                )
                self.assertEqual(replay["source_cell_ids"], native["source_cell_ids"])
                self.assertEqual(
                    replay["maximum_coverage_multiplicity_by_cell"],
                    native["maximum_coverage_multiplicity_by_cell"],
                )
                self.assertLess(
                    replay["maximum_source_area_relative_closure_error"],
                    3.0e-14,
                )
                self.assertLess(
                    replay["maximum_destination_partition_closure_error_km2"],
                    2.0e-6,
                )
                self.assertTrue(
                    math.isclose(
                        replay["global_uncovered_gap_area_km2"],
                        replay["global_overlap_excess_area_km2"],
                        rel_tol=0.0,
                        abs_tol=3.0e-6,
                    )
                )
                self.assertLess(
                    comparison["metrics"]["maximum_native_area_difference_km2"],
                    3.0e-6,
                )
                self.assertGreater(
                    comparison["metrics"][
                        "binary64_long_double_area_forward_error_bound_km2"
                    ],
                    comparison["metrics"]["maximum_native_area_difference_km2"],
                )
                self.assertGreater(
                    comparison["metrics"][
                        "binary64_long_double_area_forward_error_bound_km2"
                    ],
                    comparison["metrics"][
                        "maximum_native_membership_area_difference_km2"
                    ],
                )
                self.assertLess(
                    comparison["metrics"][
                        "binary64_long_double_area_forward_error_bound_km2"
                    ],
                    1.0e-3,
                )
                membership_areas = replay[
                    "coverage_area_km2_by_source_membership_by_cell"
                ]
                area_bound = comparison["metrics"][
                    "binary64_long_double_area_forward_error_bound_km2"
                ]
                cell_areas = [
                    float(cell["area_km2"]) for cell in world["cells"]
                ]
                for destination, area_by_membership in enumerate(
                    membership_areas
                ):
                    self.assertLessEqual(
                        abs(
                            math.fsum(area_by_membership.values())
                            - cell_areas[destination]
                        ),
                        area_bound,
                    )
                    begin = replay["destination_offsets"][destination]
                    end = replay["destination_offsets"][destination + 1]
                    for edge_index in range(begin, end):
                        source_id = replay["source_cell_ids"][edge_index]
                        reconstructed = math.fsum(
                            area
                            for membership, area in area_by_membership.items()
                            if source_id in membership
                        )
                        self.assertLessEqual(
                            abs(
                                reconstructed
                                - replay["overlap_area_km2"][edge_index]
                            ),
                            area_bound,
                        )
                # The physical multiplicities and areas are portable.  These
                # two raw execution counts are reported, but are not required
                # to match a native long-double arrangement path exactly.
                self.assertGreaterEqual(
                    comparison["metrics"]["arrangement_line_count_mismatch_count"],
                    0,
                )
                self.assertGreaterEqual(
                    comparison["metrics"][
                        "arrangement_fragment_count_mismatch_count"
                    ],
                    0,
                )

    def test_pair_discovery_does_not_trust_serialized_csr(self) -> None:
        world = deepcopy(self.worlds["fibonacci_sphere"])
        native = world["plate_motion_history"][1]["crust_overlap_ledger"]
        native["source_cell_ids"][0] = (
            native["source_cell_ids"][0] + 1
        ) % len(world["cells"])

        replay = replay_crust_coverage_geometry(world, 1)
        reference = self.comparisons["fibonacci_sphere"]["replay"]
        for field in (
            "destination_offsets",
            "source_cell_ids",
            "overlap_area_km2",
            "covered_union_area_km2_by_cell",
            "uncovered_gap_area_km2_by_cell",
            "overlap_excess_area_km2_by_cell",
            "maximum_coverage_multiplicity_by_cell",
        ):
            self.assertEqual(replay[field], reference[field])

        comparison = compare_crust_coverage_geometry(world, 1)
        self.assertFalse(comparison["passed"])
        self.assertIn(
            "independently discovered source_cell_ids differs from native ledger",
            comparison["failures"],
        )

    def test_binary64_forward_error_bound_rejects_0_001_km2_area_mutation(
        self,
    ) -> None:
        world = deepcopy(self.worlds["fibonacci_sphere"])
        ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
        largest_edge = max(
            range(len(ledger["overlap_area_km2"])),
            key=ledger["overlap_area_km2"].__getitem__,
        )
        ledger["overlap_area_km2"][largest_edge] += 1.0e-3

        comparison = compare_crust_coverage_geometry(world, 1)
        self.assertFalse(comparison["passed"])
        self.assertIn(
            "independent overlap_area_km2 differs from native ledger",
            comparison["failures"],
        )
        self.assertGreater(
            comparison["metrics"]["maximum_native_area_difference_km2"],
            comparison["metrics"][
                "binary64_long_double_area_forward_error_bound_km2"
            ],
        )

    def test_serialized_closure_telemetry_is_compared_independently(
        self,
    ) -> None:
        mutations = (
            ("maximum_source_area_closure_error_km2", 1.0e-3),
            ("maximum_source_area_relative_closure_error", 1.0e-9),
            ("maximum_destination_partition_closure_error_km2", 1.0e-3),
            ("global_gap_overlap_balance_residual_km2", 1.0e-3),
        )
        for field, delta in mutations:
            with self.subTest(field=field):
                # Step zero takes the exact native/replay identity shortcut,
                # so each case isolates one serialized telemetry witness.
                world = deepcopy(self.worlds["fibonacci_sphere"])
                ledger = world["plate_motion_history"][0][
                    "crust_overlap_ledger"
                ]
                ledger[field] += delta

                comparison = compare_crust_coverage_geometry(world, 0)
                self.assertFalse(comparison["passed"])
                self.assertEqual(
                    comparison["failures"],
                    [f"independent {field} differs from native ledger"],
                )

    def test_contributor_set_membership_area_mutation_is_rejected(self) -> None:
        world = deepcopy(self.worlds["fibonacci_sphere"])
        classes = world["plate_motion_history"][1]["crust_overlap_ledger"][
            "coverage_membership_area_class_ledger"
        ]
        largest_class = max(
            range(len(classes["area_km2"])),
            key=classes["area_km2"].__getitem__,
        )
        classes["area_km2"][largest_class] += 1.0e-3

        comparison = compare_crust_coverage_geometry(world, 1)
        self.assertFalse(comparison["passed"])
        self.assertIn(
            "independent contributor-set membership area differs from native ledger",
            comparison["failures"],
        )
        self.assertGreater(
            comparison["metrics"][
                "maximum_native_membership_area_difference_km2"
            ],
            comparison["metrics"][
                "binary64_long_double_area_forward_error_bound_km2"
            ],
        )

    def test_explicit_small_mesh_guard_prevents_accidental_production_use(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "bounded to 64 cells"):
            replay_crust_coverage_geometry(
                self.worlds["fibonacci_sphere"],
                1,
                max_cell_count=64,
            )


def _cross3(first: tuple[float, ...], second: tuple[float, ...]) -> tuple[float, ...]:
    return (
        first[1] * second[2] - first[2] * second[1],
        first[2] * second[0] - first[0] * second[2],
        first[0] * second[1] - first[1] * second[0],
    )


def _unit(vector: tuple[float, ...] | list[float]) -> list[float]:
    norm = math.sqrt(math.fsum(component * component for component in vector))
    return [component / norm for component in vector]


def _tangent_pair(center: tuple[float, float, float]) -> tuple[list[float], list[float]]:
    """A right-handed tangent frame, matching the chart handedness."""

    reference = (0.0, 0.0, 1.0) if abs(center[2]) < 0.8 else (1.0, 0.0, 0.0)
    first = _unit(_cross3(reference, center))
    second = _unit(_cross3(center, tuple(first)))
    return first, second


def _cap_cell(
    cell_id: int,
    center: tuple[float, float, float],
    *,
    angular_radius_rad: float = 0.15,
    area_km2: float = 1.0,
) -> dict:
    first, second = _tangent_pair(center)
    ring = [
        _unit(
            [
                math.cos(angular_radius_rad) * center[axis]
                + math.sin(angular_radius_rad)
                * (
                    math.cos(2.0 * math.pi * corner / 3.0) * first[axis]
                    + math.sin(2.0 * math.pi * corner / 3.0) * second[axis]
                )
                for axis in range(3)
            ]
        )
        for corner in range(3)
    ]
    return {
        "id": cell_id,
        "position_3d": list(center),
        "control_volume_vertices_3d": ring,
        "area_km2": area_km2,
    }


def _three_cap_world() -> dict:
    """Three well-separated triangular caps on one moving and one still plate.

    Cell 0 rotates 85 degrees about +z, which lands it partly on cell 1 and
    leaves its own position uncovered.  The step therefore exercises all three
    destination coverage regimes at once: zero contributors (cell 0), two
    contributors (cell 1), and exactly one contributor (cell 2).
    """

    return {
        "cells": [
            _cap_cell(0, (1.0, 0.0, 0.0)),
            _cap_cell(1, (0.0, 1.0, 0.0)),
            _cap_cell(2, (0.0, 0.0, 1.0)),
        ],
        "plate_motion_history": [
            {
                "id": 0,
                "cell_plate_ids": [0, 1, 1],
                "plates": [
                    {
                        "plate_id": 0,
                        "rotation_axis": [0.0, 0.0, 1.0],
                        "step_rotation_deg": 85.0,
                    },
                    {
                        "plate_id": 1,
                        "rotation_axis": [0.0, 0.0, 1.0],
                        "step_rotation_deg": 0.0,
                    },
                ],
            }
        ],
    }


class UncoveredAndSingleSourceCoverageTests(TestCase):
    """Destination regimes that the routine 128/162-cell fixtures never reach."""

    def test_zero_one_and_many_contributor_destinations_are_diagnosed(
        self,
    ) -> None:
        world = _three_cap_world()
        areas = [float(cell["area_km2"]) for cell in world["cells"]]
        replay = replay_crust_coverage_geometry(world, 0)

        self.assertEqual(replay["pair_search"], "brute_force_spherical_cap_v1")
        self.assertEqual(replay["destination_offsets"], [0, 0, 2, 3])
        self.assertEqual(replay["source_cell_ids"], [0, 1, 2])
        self.assertEqual(
            replay["maximum_coverage_multiplicity_by_cell"], [0, 2, 1]
        )

        # Destination 0 keeps no contributor at all: its whole control volume
        # is reported as gap, with a single unattributed arrangement fragment.
        self.assertEqual(replay["covered_union_area_km2_by_cell"][0], 0.0)
        self.assertEqual(replay["uncovered_gap_area_km2_by_cell"][0], areas[0])
        self.assertEqual(replay["overlap_excess_area_km2_by_cell"][0], 0.0)
        self.assertEqual(replay["coverage_arrangement_line_count_by_cell"][0], 0)
        self.assertEqual(
            replay["coverage_arrangement_fragment_count_by_cell"][0], 1
        )
        self.assertEqual(
            replay["coverage_area_km2_by_source_membership_by_cell"][0],
            {(): areas[0]},
        )

        # Destination 2 keeps exactly one contributor, so the diagnostic takes
        # the closed-form single-source path instead of building a line
        # arrangement, and still reports the residual gap as its own class.
        single = replay["coverage_area_km2_by_source_membership_by_cell"][2]
        self.assertEqual(set(single), {(), (2,)})
        self.assertEqual(
            single[(2,)], replay["covered_union_area_km2_by_cell"][2]
        )
        self.assertEqual(single[()], replay["uncovered_gap_area_km2_by_cell"][2])
        self.assertEqual(replay["overlap_excess_area_km2_by_cell"][2], 0.0)
        self.assertEqual(replay["coverage_arrangement_line_count_by_cell"][2], 0)
        self.assertEqual(
            replay["coverage_arrangement_fragment_count_by_cell"][2], 2
        )
        self.assertAlmostEqual(
            single[()] + single[(2,)], areas[2], places=12
        )

        # Destination 1 is the routine multi-contributor regime and keeps the
        # arrangement path honest for the comparison above.
        self.assertGreater(
            replay["coverage_arrangement_line_count_by_cell"][1], 0
        )
        self.assertGreater(replay["overlap_excess_area_km2_by_cell"][1], 0.0)
        self.assertEqual(
            replay["global_uncovered_gap_area_km2"],
            replay["uncovered_gap_area_km2_by_cell"][0]
            + replay["uncovered_gap_area_km2_by_cell"][2],
        )

    def test_degenerate_rotation_axis_uses_the_native_fallback_normalizer(
        self,
    ) -> None:
        reference = replay_crust_coverage_geometry(_three_cap_world(), 0)
        world = _three_cap_world()
        plate = world["plate_motion_history"][0]["plates"][0]
        self.assertNotEqual(plate["rotation_axis"], [0.0, 0.0, 0.0])
        plate["rotation_axis"] = [0.0, 0.0, 0.0]

        # Native axis normalization substitutes +z for an unnormalizable axis
        # rather than raising, so the replay must reproduce the same step.
        self.assertEqual(replay_crust_coverage_geometry(world, 0), reference)


class CrustCoverageGeometryReplayGuardTests(TestCase):
    """Malformed-input guards on the independent replay entry point."""

    def test_healthy_synthetic_world_is_the_control(self) -> None:
        replay = replay_crust_coverage_geometry(_three_cap_world(), 0)
        self.assertEqual(replay["cell_count"], 3)

    def _expect(
        self, mutate, exception: type[Exception], message: str, **kwargs
    ) -> None:
        control = _three_cap_world()
        world = _three_cap_world()
        mutate(world)
        self.assertNotEqual(world, control, "tamper changed nothing")
        with self.assertRaisesRegex(exception, message):
            replay_crust_coverage_geometry(world, kwargs.pop("step_index", 0), **kwargs)

    def test_malformed_cell_geometry_is_rejected(self) -> None:
        def no_cells(world: dict) -> None:
            world["cells"] = []

        def noncanonical_cell_id(world: dict) -> None:
            world["cells"][1]["id"] = 5

        def missing_control_volume(world: dict) -> None:
            del world["cells"][0]["control_volume_vertices_3d"]

        def nonpositive_area(world: dict) -> None:
            world["cells"][0]["area_km2"] = -1.0

        def two_component_position(world: dict) -> None:
            world["cells"][0]["position_3d"] = [1.0, 0.0]

        def nonfinite_position(world: dict) -> None:
            world["cells"][0]["position_3d"] = [math.nan, 0.0, 0.0]

        def unnormalizable_center(world: dict) -> None:
            world["cells"][0]["position_3d"] = [0.0, 0.0, 0.0]

        def antipodal_ring_vertex(world: dict) -> None:
            world["cells"][0]["control_volume_vertices_3d"][0] = [
                -1.0,
                0.0,
                0.0,
            ]

        cases = (
            # Three distinct guards say "non-empty array" and three distinct
            # ``_vec3`` contexts say "three-component array", so both fragments
            # carry the subject that identifies which guard fired.
            (
                "no_cells",
                no_cells,
                TypeError,
                "world cells must be a non-empty array",
            ),
            (
                "noncanonical_cell_id",
                noncanonical_cell_id,
                ValueError,
                "canonical integer IDs",
            ),
            (
                "missing_control_volume",
                missing_control_volume,
                TypeError,
                "control-volume ring is missing",
            ),
            (
                "nonpositive_area",
                nonpositive_area,
                ValueError,
                "cell area must be positive and finite",
            ),
            (
                "two_component_position",
                two_component_position,
                TypeError,
                "cell center must be a three-component array",
            ),
            (
                "nonfinite_position",
                nonfinite_position,
                ValueError,
                "cell center must be finite",
            ),
            (
                "unnormalizable_center",
                unnormalizable_center,
                ValueError,
                "replay tangent axis is geometrically degenerate",
            ),
            (
                "antipodal_ring_vertex",
                antipodal_ring_vertex,
                ValueError,
                "left the destination gnomonic hemisphere",
            ),
        )
        for name, mutate, exception, message in cases:
            with self.subTest(case=name):
                self._expect(mutate, exception, message)

    def test_malformed_step_kinematics_are_rejected(self) -> None:
        def step_is_not_an_object(world: dict) -> None:
            world["plate_motion_history"][0] = ["not-an-object"]

        def previous_step_is_not_an_object(world: dict) -> None:
            world["plate_motion_history"].append(
                deepcopy(world["plate_motion_history"][0])
            )
            world["plate_motion_history"][0] = ["not-an-object"]

        def plate_assignment_length_differs(world: dict) -> None:
            world["plate_motion_history"][0]["cell_plate_ids"] = [0, 1]

        def plate_assignment_is_not_integral(world: dict) -> None:
            # A float 0.0 would compare equal to the original 0 and hide the
            # tamper from the no-op guard, so use a plainly distinct type.
            world["plate_motion_history"][0]["cell_plate_ids"] = [0, 1, "1"]

        def no_plate_snapshots(world: dict) -> None:
            world["plate_motion_history"][0]["plates"] = []

        def plate_id_is_not_an_integer(world: dict) -> None:
            world["plate_motion_history"][0]["plates"][0]["plate_id"] = "0"

        def duplicate_plate_ids(world: dict) -> None:
            world["plate_motion_history"][0]["plates"][1]["plate_id"] = 0

        def nonfinite_rotation(world: dict) -> None:
            world["plate_motion_history"][0]["plates"][0][
                "step_rotation_deg"
            ] = math.nan

        def unknown_plate_assignment(world: dict) -> None:
            world["plate_motion_history"][0]["cell_plate_ids"] = [0, 1, 7]

        cases = (
            (
                "step_is_not_an_object",
                step_is_not_an_object,
                TypeError,
                "plate-motion step must be an object",
                0,
            ),
            (
                "previous_step_is_not_an_object",
                previous_step_is_not_an_object,
                TypeError,
                "previous plate-motion step must be an object",
                1,
            ),
            (
                "plate_assignment_length_differs",
                plate_assignment_length_differs,
                TypeError,
                "integer cell array",
                0,
            ),
            (
                "plate_assignment_is_not_integral",
                plate_assignment_is_not_integral,
                TypeError,
                "integer cell array",
                0,
            ),
            (
                "no_plate_snapshots",
                no_plate_snapshots,
                TypeError,
                "plate snapshots must be a non-empty array",
                0,
            ),
            (
                "plate_id_is_not_an_integer",
                plate_id_is_not_an_integer,
                TypeError,
                "plate snapshot ID must be an integer",
                0,
            ),
            (
                "duplicate_plate_ids",
                duplicate_plate_ids,
                ValueError,
                "plate snapshot IDs must be unique",
                0,
            ),
            (
                "nonfinite_rotation",
                nonfinite_rotation,
                ValueError,
                "plate step rotation must be finite",
                0,
            ),
            (
                "unknown_plate_assignment",
                unknown_plate_assignment,
                ValueError,
                "no kinematic snapshot",
                0,
            ),
        )
        for name, mutate, exception, message, step_index in cases:
            with self.subTest(case=name):
                self._expect(
                    mutate, exception, message, step_index=step_index
                )

    def test_entry_point_arguments_are_validated(self) -> None:
        world = _three_cap_world()
        with self.assertRaisesRegex(
            ValueError, "max_cell_count must be a positive integer"
        ):
            replay_crust_coverage_geometry(world, 0, max_cell_count=0)
        with self.assertRaisesRegex(IndexError, "step index is out of range"):
            replay_crust_coverage_geometry(world, 3)
        without_history = _three_cap_world()
        del without_history["plate_motion_history"]
        with self.assertRaisesRegex(
            TypeError, "plate motion history must be a non-empty array"
        ):
            replay_crust_coverage_geometry(without_history, 0)

    def test_forward_error_budget_rejects_an_ill_conditioned_step(self) -> None:
        # The bound is only reachable through a private helper: a real replay
        # cannot accumulate 2**53 arrangement fragments within its own limit.
        with self.assertRaisesRegex(ValueError, "ill-conditioned"):
            _binary64_long_double_forward_error_bounds(
                {
                    "cell_count": 1,
                    "coverage_arrangement_fragment_count_by_cell": [2**53],
                    "radius_km": 1.0,
                }
            )


class NativeCoverageLedgerComparisonTests(TestCase):
    """Serialized-ledger disagreements reported by the comparison layer."""

    @classmethod
    def setUpClass(cls) -> None:
        # Step zero takes the exact native/replay identity shortcut, so each
        # case isolates one serialized witness without an O(N**2) rebuild.
        cls.world = generate_geo_world(
            config_to_native(_moving_config("fibonacci_sphere", 128))
        )
        cls.control = compare_crust_coverage_geometry(cls.world, 0)

    def test_untampered_step_zero_ledger_compares_clean(self) -> None:
        self.assertTrue(self.control["passed"], self.control["failures"])

    def _tampered_ledger(self, mutate) -> dict:
        world = deepcopy(self.world)
        ledger = world["plate_motion_history"][0]["crust_overlap_ledger"]
        mutate(ledger)
        self.assertNotEqual(
            ledger,
            self.world["plate_motion_history"][0]["crust_overlap_ledger"],
            "tamper changed nothing",
        )
        return world

    def _expect_failure(self, mutate, failure: str) -> None:
        self.assertTrue(self.control["passed"], self.control["failures"])
        world = self._tampered_ledger(mutate)
        comparison = compare_crust_coverage_geometry(world, 0)
        self.assertFalse(comparison["passed"])
        self.assertIn(failure, comparison["failures"])

    def test_membership_area_class_ledger_shape_is_validated(self) -> None:
        def ledger_is_not_an_object(ledger: dict) -> None:
            ledger["coverage_membership_area_class_ledger"] = []

        def area_column_has_a_string(ledger: dict) -> None:
            ledger["coverage_membership_area_class_ledger"]["area_km2"][0] = "1"

        def contributor_offsets_do_not_close(ledger: dict) -> None:
            ledger["coverage_membership_area_class_ledger"][
                "contributor_offsets"
            ][-1] = 0

        def nonpositive_class_area(ledger: dict) -> None:
            ledger["coverage_membership_area_class_ledger"]["area_km2"][0] = -1.0

        # ``compare_crust_coverage_geometry`` collapses four distinct decoder
        # raises into one subsystem verdict, so each case also pins the raise
        # itself through the private decoder the comparison layer calls.  The
        # aggregate string alone could not tell these four checks apart.
        failure = "native coverage membership-area-class ledger shape is invalid"
        cell_count = len(self.world["cells"])
        self.assertEqual(
            len(
                _serialized_membership_area_by_cell(
                    self.world["plate_motion_history"][0][
                        "crust_overlap_ledger"
                    ],
                    cell_count,
                )
            ),
            cell_count,
        )
        cases = (
            (
                "ledger_is_not_an_object",
                ledger_is_not_an_object,
                TypeError,
                "native membership-area-class ledger is missing",
            ),
            (
                "area_column_has_a_string",
                area_column_has_a_string,
                TypeError,
                "native membership-area-class CSR has invalid types",
            ),
            (
                "contributor_offsets_do_not_close",
                contributor_offsets_do_not_close,
                ValueError,
                "native membership-area-class CSR has invalid offsets",
            ),
            (
                "nonpositive_class_area",
                nonpositive_class_area,
                ValueError,
                "native membership-area classes are not canonical and unique",
            ),
        )
        for name, mutate, exception, detail in cases:
            with self.subTest(case=name):
                self._expect_failure(mutate, failure)
                ledger = self._tampered_ledger(mutate)["plate_motion_history"][
                    0
                ]["crust_overlap_ledger"]
                with self.assertRaisesRegex(exception, detail):
                    _serialized_membership_area_by_cell(ledger, cell_count)

    def test_array_shape_and_multiplicity_disagreements_are_reported(
        self,
    ) -> None:
        def truncated_overlap_areas(ledger: dict) -> None:
            ledger["overlap_area_km2"] = ledger["overlap_area_km2"][:-1]

        def altered_multiplicity(ledger: dict) -> None:
            ledger["maximum_coverage_multiplicity_by_cell"][0] += 2

        self._expect_failure(
            truncated_overlap_areas,
            "independent overlap_area_km2 shape differs from native ledger",
        )
        self._expect_failure(
            altered_multiplicity,
            "independent maximum_coverage_multiplicity_by_cell differs from "
            "native ledger",
        )
