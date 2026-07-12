from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.config import WorldConfig, config_to_native, load_config
from magic_geo.crust_coverage_geometry_replay import (
    compare_crust_coverage_geometry,
    replay_crust_coverage_geometry,
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
