from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.config import WorldConfig, config_to_native, load_config
from magic_geo.crust_process_validation import (
    CRUST_PROCESS_REASON_ORDER,
    validate_crust_process_reason_ledger,
)
from magic_geo.crust_transport_validation import (
    _dominant_crust_category_pair,
    _validate_coverage_membership_area_classes,
    validate_crust_overlap_transport,
)
from magic_geo.geo_validation_physics import validate_physics_replays
from magic_geo.io import write_summary_markdown
from magic_geo.native import generate_geo_world
from magic_geo.oceanic_age_depth_validation import validate_oceanic_age_depth


def _moving_geodesic_config(
    threads: int = 1,
    *,
    output_precision: int = 8,
) -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["run"]["seed"] = 20260711
    data["mesh"]["backend"] = "geodesic_icosahedron"
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    data["erosion"]["iterations"] = 1
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = threads
    data["output"]["float_precision"] = output_precision
    return WorldConfig.model_validate(data)


def _three_term_partition_max_regression_config() -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["run"]["seed"] = 18491
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 4
    data["erosion"]["iterations"] = 6
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    data["output"]["float_precision"] = 4
    return WorldConfig.model_validate(data)


def _extreme_rotation_config(
    mesh_backend: str,
    cell_count: int,
) -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["mesh"]["backend"] = mesh_backend
    data["mesh"]["cell_count"] = cell_count
    data["tectonics"]["plate_count"] = 32
    data["tectonics"]["min_angular_speed"] = 18.0
    data["tectonics"]["max_angular_speed"] = 18.0
    data["tectonics"]["plate_motion_scale_deg_per_step"] = 10.0
    data["erosion"]["iterations"] = 1
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    data["output"]["float_precision"] = 8
    return WorldConfig.model_validate(data)


def _different_id(value: int, cell_count: int) -> int:
    return (value + 1) % cell_count


class ConservativeCrustTransportValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(
            config_to_native(_moving_geodesic_config())
        )
        cls.zero_precision_world = generate_geo_world(
            config_to_native(_moving_geodesic_config(output_precision=0))
        )

    def test_initial_overlap_plan_is_exact_identity(self) -> None:
        cell_areas = [float(cell["area_km2"]) for cell in self.world["cells"]]
        cell_count = len(cell_areas)
        initial = self.world["plate_motion_history"][0]
        ledger = initial["crust_overlap_ledger"]

        self.assertEqual(ledger["destination_offsets"], list(range(cell_count + 1)))
        self.assertEqual(ledger["source_cell_ids"], list(range(cell_count)))
        self.assertEqual(ledger["overlap_area_km2"], cell_areas)
        self.assertEqual(ledger["remap_residual_distance_km"], [0.0] * cell_count)
        self.assertEqual(ledger["source_kinematic_distance_km"], [0.0] * cell_count)
        self.assertEqual(ledger["dominant_source_cell_ids"], list(range(cell_count)))
        self.assertEqual(initial["crust_source_cell_ids"], list(range(cell_count)))
        self.assertEqual(ledger["contributor_count_by_cell"], [1] * cell_count)
        self.assertEqual(
            ledger["dominant_source_volume_fraction_by_cell"],
            [1.0] * cell_count,
        )
        self.assertEqual(ledger["coverage_area_sum_km2_by_cell"], cell_areas)
        self.assertEqual(ledger["covered_union_area_km2_by_cell"], cell_areas)
        self.assertEqual(ledger["uncovered_gap_area_km2_by_cell"], [0.0] * cell_count)
        self.assertEqual(ledger["overlap_excess_area_km2_by_cell"], [0.0] * cell_count)
        self.assertEqual(
            ledger["maximum_coverage_multiplicity_by_cell"],
            [1] * cell_count,
        )
        self.assertEqual(
            ledger["coverage_arrangement_line_count_by_cell"],
            [0] * cell_count,
        )
        self.assertEqual(
            ledger["coverage_arrangement_fragment_count_by_cell"],
            [1] * cell_count,
        )
        self.assertEqual(ledger["total_coverage_arrangement_line_count"], 0)
        self.assertEqual(
            ledger["total_coverage_arrangement_fragment_count"],
            cell_count,
        )
        self.assertEqual(
            ledger["global_coverage_area_km2_by_multiplicity"][0],
            0.0,
        )
        self.assertAlmostEqual(
            ledger["global_coverage_area_km2_by_multiplicity"][1],
            math.fsum(cell_areas),
            delta=1.0e-5,
        )
        self.assertEqual(ledger["maximum_coverage_arrangement_line_count"], 0)
        self.assertEqual(
            ledger["maximum_coverage_arrangement_fragment_count"],
            1,
        )
        self.assertEqual(
            ledger["coverage_membership_area_class_count_by_cell"],
            [1] * cell_count,
        )
        self.assertEqual(
            ledger["total_coverage_membership_area_class_count"],
            cell_count,
        )
        self.assertEqual(
            ledger["maximum_coverage_membership_area_class_count"],
            1,
        )
        class_ledger = ledger["coverage_membership_area_class_ledger"]
        self.assertEqual(
            class_ledger["destination_offsets"],
            list(range(cell_count + 1)),
        )
        self.assertEqual(class_ledger["area_km2"], cell_areas)
        self.assertEqual(class_ledger["multiplicity"], [1] * cell_count)
        self.assertEqual(
            class_ledger["representative_unit_x"],
            [float(cell["position_3d"][0]) for cell in self.world["cells"]],
        )
        self.assertEqual(
            class_ledger["representative_unit_y"],
            [float(cell["position_3d"][1]) for cell in self.world["cells"]],
        )
        self.assertEqual(
            class_ledger["representative_unit_z"],
            [float(cell["position_3d"][2]) for cell in self.world["cells"]],
        )
        self.assertEqual(
            class_ledger["representative_available"], [1] * cell_count
        )
        self.assertEqual(
            class_ledger["contributor_offsets"],
            list(range(cell_count + 1)),
        )
        self.assertEqual(class_ledger["source_cell_ids"], list(range(cell_count)))
        self.assertEqual(class_ledger["source_plate_ids"], initial["cell_plate_ids"])
        self.assertEqual(ledger["source_inventory"], ledger["transported_inventory"])
        self.assertEqual(ledger["source_inventory"], ledger["post_process_inventory"])
        self.assertEqual(ledger["maximum_source_area_closure_error_km2"], 0.0)
        self.assertEqual(ledger["maximum_source_area_relative_closure_error"], 0.0)
        self.assertEqual(
            ledger["maximum_destination_partition_closure_error_km2"],
            0.0,
        )
        self.assertEqual(ledger["global_uncovered_gap_area_km2"], 0.0)
        self.assertEqual(ledger["global_overlap_excess_area_km2"], 0.0)
        self.assertEqual(ledger["global_gap_overlap_balance_residual_km2"], 0.0)

        replay = validate_crust_overlap_transport(self.world)
        self.assertTrue(replay["passed"], replay["failures"])

    def test_unexported_third_partition_term_does_not_create_false_negative(
        self,
    ) -> None:
        world = generate_geo_world(
            config_to_native(_three_term_partition_max_regression_config())
        )
        step = world["plate_motion_history"][2]
        ledger = step["crust_overlap_ledger"]
        replayable_two_term_max = max(
            max(
                abs(union + gap - cell["area_km2"]),
                abs(union + excess - coverage),
            )
            for cell, union, gap, excess, coverage in zip(
                world["cells"],
                ledger["covered_union_area_km2_by_cell"],
                ledger["uncovered_gap_area_km2_by_cell"],
                ledger["overlap_excess_area_km2_by_cell"],
                ledger["coverage_area_sum_km2_by_cell"],
                strict=True,
            )
        )
        self.assertNotEqual(
            ledger["maximum_destination_partition_closure_error_km2"],
            replayable_two_term_max,
        )
        replay = validate_crust_overlap_transport(world)
        self.assertTrue(replay["passed"], replay["failures"])

        inflated = deepcopy(world)
        inflated["plate_motion_history"][2]["crust_overlap_ledger"][
            "maximum_destination_partition_closure_error_km2"
        ] = 0.001
        inflated_replay = validate_crust_overlap_transport(inflated)
        self.assertFalse(inflated_replay["passed"], inflated_replay)

    def test_geodesic_moving_step_extensives_replay_independently(self) -> None:
        self.assertEqual(self.world["mesh_backend"], "geodesic_icosahedron")
        self.assertEqual(len(self.world["plate_motion_history"]), 2)
        initial, moving = self.world["plate_motion_history"]
        ledger = moving["crust_overlap_ledger"]
        cell_areas = [float(cell["area_km2"]) for cell in self.world["cells"]]
        cell_count = len(cell_areas)

        previous_ages = [
            remapped + process
            for remapped, process in zip(
                initial["crust_overlap_ledger"]["remapped_crust_age_ma_by_cell"],
                initial["crust_age_process_change_ma_by_cell"],
                strict=True,
            )
        ]
        previous_thicknesses = [
            remapped + process
            for remapped, process in zip(
                initial["crust_overlap_ledger"][
                    "remapped_crust_thickness_km_by_cell"
                ],
                initial["crust_thickness_process_change_km_by_cell"],
                strict=True,
            )
        ]
        previous_densities = [
            remapped + process
            for remapped, process in zip(
                initial["crust_overlap_ledger"]["remapped_crust_density_by_cell"],
                initial["crust_density_process_change_by_cell"],
                strict=True,
            )
        ]
        previous_types = initial["crust_type_by_cell"]
        previous_lithologies = initial["lithology_by_cell"]
        offsets = ledger["destination_offsets"]
        source_ids = ledger["source_cell_ids"]
        overlap_areas = ledger["overlap_area_km2"]

        self.assertGreater(max(ledger["source_kinematic_distance_km"]), 0.0)
        self.assertGreater(len(source_ids), cell_count)
        self.assertTrue(any(count > 1 for count in ledger["contributor_count_by_cell"]))
        self.assertGreater(ledger["global_uncovered_gap_area_km2"], 0.0)
        self.assertGreater(ledger["global_overlap_excess_area_km2"], 0.0)

        source_area_sums = [0.0] * cell_count
        transported_volume = 0.0
        transported_density_volume = 0.0
        transported_age_moment = 0.0
        for destination in range(cell_count):
            begin, end = offsets[destination], offsets[destination + 1]
            destination_volume = 0.0
            destination_density_volume = 0.0
            destination_age_moment = 0.0
            category_pair_volumes = [[0.0] * 7 for _ in range(9)]
            donor_volumes: list[tuple[float, int]] = []
            for edge_index in range(begin, end):
                source = source_ids[edge_index]
                overlap_area = overlap_areas[edge_index]
                source_area_sums[source] += overlap_area
                volume = overlap_area * previous_thicknesses[source]
                destination_volume += volume
                destination_density_volume += volume * previous_densities[source]
                destination_age_moment += volume * previous_ages[source]
                category_pair_volumes[previous_types[source]][
                    previous_lithologies[source]
                ] += volume
                donor_volumes.append((volume, source))

            expected_thickness = destination_volume / cell_areas[destination]
            expected_density = destination_density_volume / destination_volume
            expected_age = destination_age_moment / destination_volume
            dominant_volume, dominant_source = max(
                donor_volumes,
                key=lambda item: (item[0], -item[1]),
            )
            self.assertAlmostEqual(
                ledger["remapped_crust_thickness_km_by_cell"][destination],
                expected_thickness,
                delta=max(1.0e-10, abs(expected_thickness) * 2.0e-9),
            )
            self.assertAlmostEqual(
                ledger["remapped_crust_density_by_cell"][destination],
                expected_density,
                delta=max(1.0e-10, abs(expected_density) * 2.0e-9),
            )
            self.assertAlmostEqual(
                ledger["remapped_crust_age_ma_by_cell"][destination],
                expected_age,
                delta=max(1.0e-10, abs(expected_age) * 2.0e-9),
            )
            self.assertEqual(
                ledger["dominant_source_cell_ids"][destination],
                dominant_source,
            )
            self.assertEqual(
                moving["crust_source_cell_ids"][destination],
                dominant_source,
            )
            self.assertAlmostEqual(
                ledger["dominant_source_volume_fraction_by_cell"][destination],
                dominant_volume / destination_volume,
                delta=2.0e-9,
            )
            expected_type, expected_lithology = _dominant_crust_category_pair(
                category_pair_volumes
            )
            self.assertEqual(
                ledger["remapped_crust_type_by_cell"][destination],
                expected_type,
            )
            self.assertEqual(
                ledger["remapped_lithology_by_cell"][destination],
                expected_lithology,
            )
            transported_volume += destination_volume
            transported_density_volume += destination_density_volume
            transported_age_moment += destination_age_moment

        for actual, expected in zip(source_area_sums, cell_areas, strict=True):
            self.assertAlmostEqual(
                actual,
                expected,
                delta=max(1.0e-7, expected * 2.0e-10),
            )
        source_volume = math.fsum(
            area * thickness
            for area, thickness in zip(
                cell_areas, previous_thicknesses, strict=True
            )
        )
        source_density_volume = math.fsum(
            area * thickness * density
            for area, thickness, density in zip(
                cell_areas,
                previous_thicknesses,
                previous_densities,
                strict=True,
            )
        )
        source_age_moment = math.fsum(
            area * thickness * age
            for area, thickness, age in zip(
                cell_areas,
                previous_thicknesses,
                previous_ages,
                strict=True,
            )
        )
        for actual, expected in (
            (transported_volume, source_volume),
            (transported_density_volume, source_density_volume),
            (transported_age_moment, source_age_moment),
        ):
            self.assertAlmostEqual(
                actual,
                expected,
                delta=max(1.0e-6, abs(expected) * 2.0e-9),
            )

        replay = validate_crust_overlap_transport(self.world)
        self.assertTrue(replay["passed"], replay["failures"])
        self.assertLess(replay["metrics"]["maximum_source_relative_closure_error"], 2.0e-10)
        self.assertLess(replay["metrics"]["maximum_inventory_relative_closure_error"], 2.0e-9)

    def test_membership_area_classes_reconstruct_every_coverage_witness(
        self,
    ) -> None:
        expected_model_metadata = {
            "crust_transport_positive_area_serialization_model": (
                "general_format_max_digits10_binary64_round_trip_v1"
            ),
            "crust_transport_coverage_membership_area_class_model": (
                "coalesced_destination_source_membership_area_classes_v1"
            ),
            "crust_transport_coverage_membership_area_class_ledger_format": (
                "destination_membership_area_class_csr_with_class_contributor_csr_v1"
            ),
            "crust_transport_coverage_membership_area_class_order": (
                "destination_id_then_multiplicity_then_source_cell_ids"
            ),
            "crust_transport_coverage_membership_area_class_coalescing_key": (
                "sorted_contributing_source_cell_ids"
            ),
            "crust_transport_coverage_membership_area_class_representative_model": (
                "largest_atomic_arrangement_piece_unprojected_vertex_mean_"
                "lowest_xyz_tie_v1"
            ),
            "crust_transport_coverage_membership_area_class_source_plate_id_semantics": (
                "source_cell_plate_id_at_transport_source_snapshot"
            ),
            "crust_transport_coverage_membership_area_class_edge_area_reconstruction_tolerance_basis": (
                "max_1e-7_km2_or_destination_control_volume_area_km2_times_5e-10"
            ),
            "crust_transport_coverage_membership_area_class_source_membership_resolved": True,
            "crust_transport_coverage_membership_area_class_connected_fragment_topology_resolved": False,
            "crust_transport_coverage_membership_area_class_physical_fate_resolved": False,
            "crust_transport_coverage_membership_area_class_slab_selection_resolved": False,
            "crust_transport_coverage_membership_area_class_local_kinematics_resolved": False,
        }
        model = self.world["plate_kinematic_model"]
        for field, expected in expected_model_metadata.items():
            self.assertEqual(model[field], expected)

        expected_class_keys = {
            "format",
            "model",
            "class_order",
            "coalescing_key",
            "representative_model",
            "representative_available_semantics",
            "source_plate_id_semantics",
            "edge_area_reconstruction_tolerance_basis",
            "raw_arrangement_fragment_count_location",
            "area_unit",
            "destination_offsets",
            "area_km2",
            "multiplicity",
            "representative_unit_x",
            "representative_unit_y",
            "representative_unit_z",
            "representative_available",
            "contributor_offsets",
            "source_cell_ids",
            "source_plate_ids",
            "source_membership_resolved",
            "connected_fragment_topology_resolved",
            "physical_fate_resolved",
            "slab_selection_resolved",
            "local_kinematics_resolved",
        }
        cell_areas = [float(cell["area_km2"]) for cell in self.world["cells"]]
        cell_count = len(cell_areas)
        history = self.world["plate_motion_history"]
        observed_coalescing = False
        for step_index, step in enumerate(history):
            ledger = step["crust_overlap_ledger"]
            classes = ledger["coverage_membership_area_class_ledger"]
            self.assertEqual(set(classes), expected_class_keys)
            class_counts = ledger[
                "coverage_membership_area_class_count_by_cell"
            ]
            raw_fragment_counts = ledger[
                "coverage_arrangement_fragment_count_by_cell"
            ]
            self.assertEqual(
                ledger["total_coverage_membership_area_class_count"],
                sum(class_counts),
            )
            self.assertEqual(
                ledger["maximum_coverage_membership_area_class_count"],
                max(class_counts),
            )
            self.assertTrue(
                all(
                    1 <= class_count <= raw_count
                    for class_count, raw_count in zip(
                        class_counts, raw_fragment_counts, strict=True
                    )
                )
            )
            if step_index > 0:
                observed_coalescing = observed_coalescing or any(
                    class_count < raw_count
                    for class_count, raw_count in zip(
                        class_counts, raw_fragment_counts, strict=True
                    )
                )

            class_offsets = classes["destination_offsets"]
            contributor_offsets = classes["contributor_offsets"]
            class_areas = classes["area_km2"]
            multiplicities = classes["multiplicity"]
            source_ids = classes["source_cell_ids"]
            source_plate_ids = classes["source_plate_ids"]
            expected_source_plate_ids = (
                step["cell_plate_ids"]
                if step_index == 0
                else history[step_index - 1]["cell_plate_ids"]
            )
            edge_offsets = ledger["destination_offsets"]
            edge_source_ids = ledger["source_cell_ids"]
            edge_areas = ledger["overlap_area_km2"]
            reconstructed_histogram = [
                0.0
                for _ in ledger[
                    "global_coverage_area_km2_by_multiplicity"
                ]
            ]
            for destination in range(cell_count):
                begin = class_offsets[destination]
                end = class_offsets[destination + 1]
                self.assertEqual(end - begin, class_counts[destination])
                edge_begin = edge_offsets[destination]
                edge_end = edge_offsets[destination + 1]
                edge_row = edge_source_ids[edge_begin:edge_end]
                reconstructed_edges = {source_id: 0.0 for source_id in edge_row}
                previous_order: tuple[int, tuple[int, ...]] | None = None
                partition_terms: list[float] = []
                coverage_terms: list[float] = []
                union_terms: list[float] = []
                gap_terms: list[float] = []
                excess_terms: list[float] = []
                for area_class in range(begin, end):
                    contributor_begin = contributor_offsets[area_class]
                    contributor_end = contributor_offsets[area_class + 1]
                    contributors = tuple(
                        source_ids[contributor_begin:contributor_end]
                    )
                    plates = source_plate_ids[
                        contributor_begin:contributor_end
                    ]
                    multiplicity = multiplicities[area_class]
                    area = class_areas[area_class]
                    self.assertEqual(multiplicity, len(contributors))
                    self.assertEqual(contributors, tuple(sorted(set(contributors))))
                    self.assertTrue(set(contributors).issubset(edge_row))
                    self.assertEqual(
                        plates,
                        [
                            expected_source_plate_ids[source_id]
                            for source_id in contributors
                        ],
                    )
                    order = multiplicity, contributors
                    if previous_order is not None:
                        self.assertLess(previous_order, order)
                    previous_order = order
                    representative = (
                        classes["representative_unit_x"][area_class],
                        classes["representative_unit_y"][area_class],
                        classes["representative_unit_z"][area_class],
                    )
                    self.assertEqual(
                        classes["representative_available"][area_class], 1
                    )
                    self.assertAlmostEqual(
                        math.sqrt(
                            math.fsum(value * value for value in representative)
                        ),
                        1.0,
                        delta=2.0e-12,
                    )
                    for source_id in contributors:
                        reconstructed_edges[source_id] += area
                    partition_terms.append(area)
                    coverage_terms.append(multiplicity * area)
                    if multiplicity == 0:
                        gap_terms.append(area)
                    else:
                        union_terms.append(area)
                    if multiplicity >= 2:
                        excess_terms.append((multiplicity - 1) * area)
                    reconstructed_histogram[multiplicity] += area

                tolerance = max(1.0e-7, cell_areas[destination] * 5.0e-10)
                self.assertAlmostEqual(
                    math.fsum(partition_terms),
                    cell_areas[destination],
                    delta=tolerance,
                )
                for edge_index in range(edge_begin, edge_end):
                    self.assertAlmostEqual(
                        reconstructed_edges[edge_source_ids[edge_index]],
                        edge_areas[edge_index],
                        delta=tolerance,
                    )
                for reconstructed, recorded in (
                    (
                        math.fsum(coverage_terms),
                        ledger["coverage_area_sum_km2_by_cell"][destination],
                    ),
                    (
                        math.fsum(union_terms),
                        ledger["covered_union_area_km2_by_cell"][destination],
                    ),
                    (
                        math.fsum(gap_terms),
                        ledger["uncovered_gap_area_km2_by_cell"][destination],
                    ),
                    (
                        math.fsum(excess_terms),
                        ledger["overlap_excess_area_km2_by_cell"][destination],
                    ),
                ):
                    self.assertAlmostEqual(
                        reconstructed, recorded, delta=tolerance
                    )

            for reconstructed, recorded in zip(
                reconstructed_histogram,
                ledger["global_coverage_area_km2_by_multiplicity"],
                strict=True,
            ):
                self.assertAlmostEqual(
                    reconstructed,
                    recorded,
                    delta=max(
                        1.0e-6,
                        max(abs(reconstructed), abs(recorded)) * 5.0e-10,
                    ),
                )
        self.assertTrue(observed_coalescing)

    def test_round_trip_tiny_area_is_positive_and_zero_is_rejected(self) -> None:
        payload = deepcopy(
            self.world["plate_motion_history"][1]["crust_overlap_ledger"][
                "coverage_membership_area_class_ledger"
            ]
        )
        payload.update(
            {
                "destination_offsets": [0, 2],
                "area_km2": [4.0e-18, 1.0],
                "multiplicity": [0, 1],
                "representative_unit_x": [1.0, 1.0],
                "representative_unit_y": [0.0, 0.0],
                "representative_unit_z": [0.0, 0.0],
                "representative_available": [1, 1],
                "contributor_offsets": [0, 0, 1],
                "source_cell_ids": [0],
                "source_plate_ids": [0],
            }
        )
        arguments = {
            "cell_areas": [1.0],
            "destination_offsets": [0, 1],
            "destination_source_ids": [0],
            "overlap_areas": [1.0],
            "expected_source_plate_ids": [0],
            "membership_area_class_counts": [2],
            "coverage_sums": [1.0],
            "union_areas": [1.0],
            "gap_areas": [4.0e-18],
            "excess_areas": [0.0],
            "maximum_multiplicities": [1],
            "coverage_histogram": [4.0e-18, 1.0],
        }

        replay = _validate_coverage_membership_area_classes(
            payload,
            **arguments,
        )
        self.assertEqual(replay["class_count"], 2)
        self.assertEqual(
            replay["membership_area_by_destination"],
            [{(): 4.0e-18, (0,): 1.0}],
        )

        zeroed = deepcopy(payload)
        zeroed["area_km2"][0] = 0.0
        with self.assertRaisesRegex(ValueError, "nonpositive area"):
            _validate_coverage_membership_area_classes(
                zeroed,
                **arguments,
            )

        negative = deepcopy(payload)
        negative["area_km2"][0] = -1.0e-18
        with self.assertRaisesRegex(ValueError, "nonpositive area"):
            _validate_coverage_membership_area_classes(
                negative,
                **arguments,
            )

    def test_transition_summary_observability_replays_and_is_in_markdown(self) -> None:
        summary = self.world["summary"]
        moving_ledger = self.world["plate_motion_history"][1][
            "crust_overlap_ledger"
        ]
        replay = validate_crust_overlap_transport(self.world)
        self.assertTrue(replay["passed"], replay["failures"])

        count_fields = {
            "total_crust_overlap_sparse_edge_count": len(
                moving_ledger["source_cell_ids"]
            ),
            "total_crust_mixed_destination_count": sum(
                count > 1
                for count in moving_ledger["contributor_count_by_cell"]
            ),
            "maximum_crust_coverage_multiplicity": max(
                moving_ledger["maximum_coverage_multiplicity_by_cell"]
            ),
            "maximum_crust_coverage_arrangement_line_count": moving_ledger[
                "maximum_coverage_arrangement_line_count"
            ],
            "maximum_crust_coverage_arrangement_fragment_count": moving_ledger[
                "maximum_coverage_arrangement_fragment_count"
            ],
            "total_tectonic_process_reason_record_count": len(
                moving_ledger["process_inventory_attribution"]["reasons"]
            ),
            "active_tectonic_process_reason_record_count": sum(
                record["triggered_cell_count"] > 0
                for record in moving_ledger["process_inventory_attribution"][
                    "reasons"
                ]
            ),
        }
        for field, expected in count_fields.items():
            self.assertEqual(summary[field], expected)
            self.assertEqual(replay["metrics"][field], expected)

        transported = moving_ledger["transported_inventory"]
        post_process = moving_ledger["post_process_inventory"]
        process_delta = {
            "volume": post_process["crust_volume_km3"]
            - transported["crust_volume_km3"],
            "density_volume": post_process["density_weighted_crust_volume"]
            - transported["density_weighted_crust_volume"],
            "age_moment": post_process["crust_age_volume_moment_km3_ma"]
            - transported["crust_age_volume_moment_km3_ma"],
        }
        scalar_fields = {
            "maximum_crust_source_area_closure_error_km2": moving_ledger[
                "maximum_source_area_closure_error_km2"
            ],
            "maximum_crust_source_area_relative_closure_error": moving_ledger[
                "maximum_source_area_relative_closure_error"
            ],
            "maximum_crust_destination_partition_closure_error_km2": (
                moving_ledger[
                    "maximum_destination_partition_closure_error_km2"
                ]
            ),
            "total_crust_uncovered_gap_area_km2": moving_ledger[
                "global_uncovered_gap_area_km2"
            ],
            "total_crust_overlap_excess_area_km2": moving_ledger[
                "global_overlap_excess_area_km2"
            ],
            "maximum_crust_transport_inventory_relative_closure_error": replay[
                "metrics"
            ]["maximum_crust_transport_inventory_relative_closure_error"],
            "cumulative_absolute_tectonic_process_crust_volume_change_km3": abs(
                process_delta["volume"]
            ),
            "net_tectonic_process_crust_volume_change_km3": process_delta[
                "volume"
            ],
            "cumulative_absolute_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3": abs(
                process_delta["density_volume"]
            ),
            "net_tectonic_process_density_weighted_crust_volume_change_g_cm3_km3": (
                process_delta["density_volume"]
            ),
            "cumulative_absolute_tectonic_process_crust_age_volume_moment_change_km3_ma": abs(
                process_delta["age_moment"]
            ),
            "net_tectonic_process_crust_age_volume_moment_change_km3_ma": (
                process_delta["age_moment"]
            ),
            "maximum_tectonic_process_attribution_relative_closure_residual": max(
                abs(
                    moving_ledger["process_inventory_attribution"][
                        "numerical_closure_residual"
                    ][field]
                )
                / max(
                    1.0,
                    abs(moving_ledger["process_inventory_delta"][field]),
                )
                for field in (
                    "crust_volume_km3",
                    "density_weighted_crust_volume",
                    "crust_age_volume_moment_km3_ma",
                )
            ),
        }
        for field, expected in scalar_fields.items():
            self.assertTrue(
                math.isclose(
                    float(summary[field]),
                    float(expected),
                    rel_tol=2.0e-9,
                    abs_tol=1.0e-8,
                ),
                (field, summary[field], expected),
            )

        with TemporaryDirectory() as directory:
            summary_path = Path(directory) / "summary.md"
            write_summary_markdown(summary_path, self.world)
            markdown = summary_path.read_text(encoding="utf-8")
        for field in count_fields | scalar_fields:
            self.assertIn(f"- `{field}`:", markdown)
        shadow_summary_fields = {
            "crust_material_shadow_history_step_count",
            "total_crust_material_shadow_packet_count",
            "maximum_crust_material_shadow_packet_count_per_table",
            "total_crust_material_shadow_opening_packet_count",
            "total_crust_material_shadow_transported_packet_count",
            "total_crust_material_shadow_closing_packet_count",
            "maximum_crust_material_shadow_opening_packet_count_per_step",
            "maximum_crust_material_shadow_transported_packet_count_per_step",
            "maximum_crust_material_shadow_closing_packet_count_per_step",
            "total_crust_material_shadow_adjustment_count",
            "maximum_crust_material_shadow_adjustment_count_per_table",
            "total_crust_material_shadow_unresolved_source_adjustment_count",
            "total_crust_material_shadow_unresolved_sink_adjustment_count",
            "cumulative_crust_material_shadow_unresolved_source_mass_kg",
            "cumulative_crust_material_shadow_unresolved_sink_mass_kg",
            "maximum_absolute_crust_material_shadow_transport_raw_residual_kg",
            "maximum_crust_material_shadow_closing_scalar_relative_residual",
            "maximum_absolute_crust_material_shadow_adjustment_reconciliation_residual_kg",
        }
        for field in shadow_summary_fields:
            self.assertIn(field, summary)
            self.assertIn(f"- `{field}`:", markdown)

    def test_reason_ledger_replays_and_is_thread_deterministic(self) -> None:
        model = self.world["plate_kinematic_model"]
        self.assertTrue(
            model["tectonic_process_rule_state_source_sink_accounting_resolved"]
        )
        self.assertFalse(model["tectonic_process_source_sink_attribution_resolved"])
        self.assertFalse(model["tectonic_process_material_provenance_resolved"])
        self.assertEqual(
            model["tectonic_process_inventory_reason_order"],
            list(CRUST_PROCESS_REASON_ORDER),
        )
        self.assertEqual(
            model["tectonic_process_boundary_input_locations"],
            [
                "plate_motion_history[].boundary_convergent_by_cell",
                "plate_motion_history[].boundary_divergent_by_cell",
                "plate_motion_history[].boundary_transform_by_cell",
            ],
        )
        self.assertEqual(
            model["crust_categorical_remap_model"],
            "joint_crust_type_lithology_dominant_incoming_volume_v1",
        )
        self.assertEqual(
            model["transitional_oceanic_provenance_rule"],
            "crust_type_2_is_oceanic_iff_lithology_0_basalt",
        )
        self.assertEqual(
            model["oceanic_convergence_subduction_proxy_semantics"],
            "rule_adds_thickness_and_reduces_age_not_a_crust_removal_flux",
        )
        self.assertEqual(
            model["plate_crossing_accretion_proxy_semantics"],
            "extra_continental_convergence_thickening_not_external_reservoir_provenance",
        )

        initial, moving = self.world["plate_motion_history"]
        initial_reasons = initial["crust_overlap_ledger"][
            "process_inventory_attribution"
        ]["reasons"]
        self.assertEqual(
            [record["reason"] for record in initial_reasons],
            list(CRUST_PROCESS_REASON_ORDER),
        )
        for record in initial_reasons:
            self.assertEqual(record["triggered_cell_count"], 0)
            self.assertEqual(record["extensive_state_changed_cell_count"], 0)
            for delta_field in (
                "positive_delta",
                "negative_delta_magnitude",
                "net_delta",
            ):
                self.assertEqual(set(record[delta_field].values()), {0.0})

        attribution = moving["crust_overlap_ledger"][
            "process_inventory_attribution"
        ]
        self.assertTrue(
            any(record["triggered_cell_count"] > 0 for record in attribution["reasons"])
        )
        extensive_fields = (
            "crust_volume_km3",
            "density_weighted_crust_volume",
            "crust_age_volume_moment_km3_ma",
        )
        for record in attribution["reasons"]:
            self.assertLessEqual(
                record["extensive_state_changed_cell_count"],
                record["triggered_cell_count"],
            )
            for field in extensive_fields:
                self.assertEqual(
                    record["net_delta"][field],
                    record["positive_delta"][field]
                    - record["negative_delta_magnitude"][field],
                )
        for field in extensive_fields:
            attributed = math.fsum(
                record["net_delta"][field] for record in attribution["reasons"]
            )
            self.assertTrue(
                math.isclose(
                    attribution["attributed_inventory_delta"][field],
                    attributed,
                    rel_tol=5.0e-10,
                    abs_tol=1.0e-8,
                )
            )
            self.assertEqual(
                attribution["reconciled_inventory_delta"][field],
                moving["crust_overlap_ledger"]["process_inventory_delta"][field],
            )

        replay = validate_crust_process_reason_ledger(self.world)
        self.assertTrue(replay["passed"], replay["failures"])
        self.assertEqual(replay["metrics"]["replayed_crust_process_step_count"], 1)

        parallel_world = generate_geo_world(
            config_to_native(_moving_geodesic_config(threads=4))
        )
        for serial_step, parallel_step in zip(
            self.world["plate_motion_history"],
            parallel_world["plate_motion_history"],
            strict=True,
        ):
            self.assertEqual(
                serial_step["boundary_convergent_by_cell"],
                parallel_step["boundary_convergent_by_cell"],
            )
            self.assertEqual(
                serial_step["boundary_divergent_by_cell"],
                parallel_step["boundary_divergent_by_cell"],
            )
            self.assertEqual(
                serial_step["crust_overlap_ledger"][
                    "process_inventory_attribution"
                ],
                parallel_step["crust_overlap_ledger"][
                    "process_inventory_attribution"
                ],
            )

    def test_joint_category_mode_never_synthesizes_marginal_pair_and_ties_low(
        self,
    ) -> None:
        pair_volumes = [[0.0] * 7 for _ in range(9)]
        pair_volumes[0][0] = 6.0
        pair_volumes[1][1] = 4.0
        pair_volumes[2][1] = 4.0
        pair_volumes[3][2] = 6.0

        type_volumes = [sum(row) for row in pair_volumes]
        lithology_volumes = [
            sum(row[lithology] for row in pair_volumes)
            for lithology in range(7)
        ]
        marginal_pair = (
            max(range(9), key=lambda value: (type_volumes[value], -value)),
            max(
                range(7),
                key=lambda value: (lithology_volumes[value], -value),
            ),
        )

        self.assertEqual(marginal_pair, (0, 1))
        self.assertEqual(pair_volumes[marginal_pair[0]][marginal_pair[1]], 0.0)
        self.assertEqual(pair_volumes[0][0], pair_volumes[3][2])
        self.assertEqual(_dominant_crust_category_pair(pair_volumes), (0, 0))

    def test_process_replay_rejects_ulp_visible_and_final_cell_mutations(
        self,
    ) -> None:
        def mutate_process_age(world: dict) -> None:
            world["plate_motion_history"][1][
                "crust_age_process_change_ma_by_cell"
            ][0] += 1.0e-6

        def mutate_final_crust_type(world: dict) -> None:
            cell = world["cells"][0]
            cell["crust_type"] = (
                "continental"
                if cell["crust_type"] != "continental"
                else "oceanic"
            )

        def mutate_final_lithology(world: dict) -> None:
            cell = world["cells"][0]
            cell["lithology"] = (
                "granite" if cell["lithology"] != "granite" else "basalt"
            )

        def mutate_final_age(world: dict) -> None:
            world["cells"][0]["crust_age_ma"] += 1.0e-6

        def mutate_final_thickness(world: dict) -> None:
            world["cells"][0]["crust_thickness_km"] += 1.0e-6

        def mutate_final_density(world: dict) -> None:
            world["cells"][0]["crust_density"] += 1.0e-6

        for name, mutate in {
            "process_age_1e-6_ma": mutate_process_age,
            "final_crust_type": mutate_final_crust_type,
            "final_lithology": mutate_final_lithology,
            "final_crust_age": mutate_final_age,
            "final_crust_thickness": mutate_final_thickness,
            "final_crust_density": mutate_final_density,
        }.items():
            with self.subTest(mutation=name):
                altered = deepcopy(self.world)
                mutate(altered)
                replay = validate_crust_process_reason_ledger(altered)
                self.assertFalse(replay["passed"], replay)
                self.assertTrue(replay["failures"])

    def test_round_trip_final_aliases_ignore_zero_display_precision(self) -> None:
        validators = (
            validate_crust_process_reason_ledger,
            validate_crust_overlap_transport,
            validate_oceanic_age_depth,
        )
        self.assertEqual(
            self.zero_precision_world["summary"]["output_float_precision"],
            0,
        )
        for validator in validators:
            with self.subTest(validator=validator.__name__, mutation="none"):
                replay = validator(self.zero_precision_world)
                self.assertTrue(replay["passed"], replay["failures"])

        for field in (
            "crust_age_ma",
            "crust_thickness_km",
            "crust_density",
        ):
            altered = deepcopy(self.zero_precision_world)
            altered["cells"][0][field] += 1.0e-5
            for validator in validators:
                with self.subTest(
                    validator=validator.__name__,
                    mutation=f"{field}_plus_1e-5",
                ):
                    replay = validator(altered)
                    self.assertFalse(replay["passed"], replay)
                    self.assertTrue(replay["failures"])

    def test_proxy_semantics_metadata_mutations_fail_all_validator_surfaces(
        self,
    ) -> None:
        fields = (
            "oceanic_convergence_subduction_proxy_semantics",
            "plate_crossing_accretion_proxy_semantics",
        )
        runner = CliRunner()
        with TemporaryDirectory() as directory:
            world_path = Path(directory) / "world.json"
            for field in fields:
                with self.subTest(field=field):
                    altered = deepcopy(self.world)
                    altered["plate_kinematic_model"][field] = "dishonest_proxy"

                    replay = validate_crust_overlap_transport(altered)
                    self.assertFalse(replay["passed"], replay)

                    physics_check = next(
                        check
                        for check in validate_physics_replays(altered)
                        if check["name"] == "conservative_crust_overlap_replay"
                    )
                    self.assertFalse(physics_check["passed"], physics_check)

                    world_path.write_text(
                        json.dumps(altered),
                        encoding="utf-8",
                    )
                    result = runner.invoke(
                        app,
                        ["validate", "--world", str(world_path)],
                    )
                    self.assertNotEqual(result.exit_code, 0, result.output)
                    self.assertIn(
                        "plate kinematic model or motion history invalid",
                        result.output,
                    )

    def test_extreme_rotation_stays_sparse_bounded_and_conservative(self) -> None:
        cases = (
            (
                "fibonacci_sphere",
                512,
                {
                    "sparse_edges": 2279,
                    "maximum_contributors": 17,
                    "maximum_multiplicity": 5,
                    "maximum_lines": 92,
                    "maximum_fragments": 1844,
                    "histogram_bins": 6,
                },
            ),
            (
                "geodesic_icosahedron",
                642,
                {
                    "sparse_edges": 2692,
                    "maximum_contributors": 24,
                    "maximum_multiplicity": 7,
                    "maximum_lines": 132,
                    "maximum_fragments": 3835,
                    "histogram_bins": 8,
                },
            ),
        )
        for mesh_backend, requested_cells, expected in cases:
            with self.subTest(mesh_backend=mesh_backend):
                world = generate_geo_world(
                    config_to_native(
                        _extreme_rotation_config(mesh_backend, requested_cells)
                    )
                )
                self.assertEqual(world["mesh_backend"], mesh_backend)
                self.assertEqual(len(world["plate_motion_history"]), 2)
                moving = world["plate_motion_history"][1]
                ledger = moving["crust_overlap_ledger"]
                actual_cell_count = len(world["cells"])

                self.assertEqual(actual_cell_count, requested_cells)
                self.assertTrue(
                    all(
                        math.isclose(
                            abs(float(plate["step_rotation_deg"])),
                            180.0,
                            rel_tol=0.0,
                            abs_tol=1.0e-12,
                        )
                        for plate in moving["plates"]
                    )
                )
                self.assertEqual(
                    len(ledger["source_cell_ids"]),
                    expected["sparse_edges"],
                )
                self.assertEqual(
                    max(ledger["contributor_count_by_cell"]),
                    expected["maximum_contributors"],
                )
                self.assertEqual(
                    max(ledger["maximum_coverage_multiplicity_by_cell"]),
                    expected["maximum_multiplicity"],
                )
                self.assertEqual(
                    ledger["maximum_coverage_arrangement_line_count"],
                    expected["maximum_lines"],
                )
                self.assertEqual(
                    ledger["maximum_coverage_arrangement_fragment_count"],
                    expected["maximum_fragments"],
                )
                self.assertEqual(
                    len(ledger["global_coverage_area_km2_by_multiplicity"]),
                    expected["histogram_bins"],
                )
                self.assertLess(
                    expected["sparse_edges"],
                    actual_cell_count * actual_cell_count // 100,
                )
                self.assertLessEqual(
                    max(ledger["coverage_arrangement_fragment_count_by_cell"]),
                    16384,
                )
                self.assertEqual(
                    ledger["total_coverage_arrangement_line_count"],
                    sum(ledger["coverage_arrangement_line_count_by_cell"]),
                )
                self.assertEqual(
                    ledger["total_coverage_arrangement_fragment_count"],
                    sum(ledger["coverage_arrangement_fragment_count_by_cell"]),
                )
                self.assertLess(
                    ledger["maximum_source_area_relative_closure_error"],
                    2.0e-10,
                )
                self.assertLess(
                    ledger["maximum_destination_partition_closure_error_km2"],
                    1.0e-4,
                )
                replay = validate_crust_overlap_transport(world)
                self.assertTrue(replay["passed"], replay["failures"])
                self.assertEqual(
                    world["backend"][
                        "cpu_conservative_crust_overlap_transition_count"
                    ],
                    1,
                )

    def test_membership_area_class_schema_and_reconstruction_mutations_fail(
        self,
    ) -> None:
        cell_count = len(self.world["cells"])

        def moving_ledger(world: dict) -> dict:
            return world["plate_motion_history"][1]["crust_overlap_ledger"]

        def class_ledger(world: dict) -> dict:
            return moving_ledger(world)[
                "coverage_membership_area_class_ledger"
            ]

        def delete_class_ledger(world: dict) -> None:
            del moving_ledger(world)["coverage_membership_area_class_ledger"]

        def add_unknown_class_field(world: dict) -> None:
            class_ledger(world)["unknown_field"] = 0

        def mutate_class_format(world: dict) -> None:
            class_ledger(world)["format"] = "destination_fragment_csr_v0"

        def mutate_nested_topology_flag(world: dict) -> None:
            class_ledger(world)["connected_fragment_topology_resolved"] = True

        def mutate_model_literal(world: dict) -> None:
            world["plate_kinematic_model"][
                "crust_transport_coverage_membership_area_class_model"
            ] = "atomic_fragments_v0"

        def mutate_model_topology_flag(world: dict) -> None:
            world["plate_kinematic_model"][
                "crust_transport_coverage_membership_area_class_connected_fragment_topology_resolved"
            ] = True

        def mutate_fractional_class_offset(world: dict) -> None:
            class_ledger(world)["destination_offsets"][1] += 0.5

        def mutate_class_offset_terminal(world: dict) -> None:
            class_ledger(world)["destination_offsets"][-1] -= 1

        def mutate_string_class_area(world: dict) -> None:
            classes = class_ledger(world)
            classes["area_km2"][0] = str(classes["area_km2"][0])

        def mutate_class_area_closure(world: dict) -> None:
            class_ledger(world)["area_km2"][0] += 1.0

        def mutate_fractional_multiplicity(world: dict) -> None:
            class_ledger(world)["multiplicity"][0] += 0.5

        def mutate_multiplicity_membership_mismatch(world: dict) -> None:
            class_ledger(world)["multiplicity"][0] += 1

        def mutate_representative_availability(world: dict) -> None:
            class_ledger(world)["representative_available"][0] = 0

        def mutate_representative_norm(world: dict) -> None:
            classes = class_ledger(world)
            classes["representative_unit_x"][0] = 2.0
            classes["representative_unit_y"][0] = 0.0
            classes["representative_unit_z"][0] = 0.0

        def mutate_fractional_contributor_offset(world: dict) -> None:
            class_ledger(world)["contributor_offsets"][1] += 0.5

        def mutate_source_outside_destination_row(world: dict) -> None:
            ledger = moving_ledger(world)
            classes = class_ledger(world)
            class_offsets = classes["destination_offsets"]
            contributor_offsets = classes["contributor_offsets"]
            for destination in range(cell_count):
                edge_row = set(
                    ledger["source_cell_ids"][
                        ledger["destination_offsets"][destination]
                        : ledger["destination_offsets"][destination + 1]
                    ]
                )
                replacement = next(
                    (source for source in range(cell_count) if source not in edge_row),
                    None,
                )
                for area_class in range(
                    class_offsets[destination], class_offsets[destination + 1]
                ):
                    begin = contributor_offsets[area_class]
                    if begin < contributor_offsets[area_class + 1] and replacement is not None:
                        classes["source_cell_ids"][begin] = replacement
                        previous_plate_ids = world["plate_motion_history"][0][
                            "cell_plate_ids"
                        ]
                        classes["source_plate_ids"][begin] = previous_plate_ids[
                            replacement
                        ]
                        return
            raise AssertionError("fixture has no replaceable membership contributor")

        def mutate_duplicate_class_contributor(world: dict) -> None:
            classes = class_ledger(world)
            offsets = classes["contributor_offsets"]
            for area_class, multiplicity in enumerate(classes["multiplicity"]):
                if multiplicity >= 2:
                    begin = offsets[area_class]
                    classes["source_cell_ids"][begin + 1] = classes[
                        "source_cell_ids"
                    ][begin]
                    classes["source_plate_ids"][begin + 1] = classes[
                        "source_plate_ids"
                    ][begin]
                    return
            raise AssertionError("fixture has no multiplicity-two area class")

        def mutate_source_plate_linkage(world: dict) -> None:
            classes = class_ledger(world)
            classes["source_plate_ids"][0] = (
                classes["source_plate_ids"][0] + 1
            ) % len(world["plates"])

        def swap_adjacent_classes_out_of_order(world: dict) -> None:
            classes = class_ledger(world)
            class_offsets = classes["destination_offsets"]
            contributor_offsets = classes["contributor_offsets"]
            scalar_fields = (
                "area_km2",
                "multiplicity",
                "representative_unit_x",
                "representative_unit_y",
                "representative_unit_z",
                "representative_available",
            )
            for destination in range(cell_count):
                for left in range(
                    class_offsets[destination],
                    class_offsets[destination + 1] - 1,
                ):
                    right = left + 1
                    if classes["multiplicity"][left] != classes["multiplicity"][right]:
                        continue
                    for field in scalar_fields:
                        classes[field][left], classes[field][right] = (
                            classes[field][right],
                            classes[field][left],
                        )
                    left_begin = contributor_offsets[left]
                    left_end = contributor_offsets[left + 1]
                    right_begin = contributor_offsets[right]
                    right_end = contributor_offsets[right + 1]
                    self.assertEqual(left_end - left_begin, right_end - right_begin)
                    for field in ("source_cell_ids", "source_plate_ids"):
                        left_values = classes[field][left_begin:left_end]
                        classes[field][left_begin:left_end] = classes[field][
                            right_begin:right_end
                        ]
                        classes[field][right_begin:right_end] = left_values
                    return
            raise AssertionError("fixture has no same-multiplicity adjacent classes")

        def mutate_fractional_class_count(world: dict) -> None:
            moving_ledger(world)[
                "coverage_membership_area_class_count_by_cell"
            ][0] += 0.5

        def mutate_class_count_mirror(world: dict) -> None:
            moving_ledger(world)[
                "coverage_membership_area_class_count_by_cell"
            ][0] += 1

        def mutate_total_class_count(world: dict) -> None:
            moving_ledger(world)[
                "total_coverage_membership_area_class_count"
            ] += 1

        def mutate_maximum_class_count(world: dict) -> None:
            moving_ledger(world)[
                "maximum_coverage_membership_area_class_count"
            ] += 1

        def mutate_identity_representative(world: dict) -> None:
            classes = world["plate_motion_history"][0]["crust_overlap_ledger"][
                "coverage_membership_area_class_ledger"
            ]
            replacement = world["cells"][1]["position_3d"]
            classes["representative_unit_x"][0] = replacement[0]
            classes["representative_unit_y"][0] = replacement[1]
            classes["representative_unit_z"][0] = replacement[2]

        def set_model_field(field: str, value: object):
            def mutate(world: dict) -> None:
                world["plate_kinematic_model"][field] = value

            return mutate

        def set_nested_field(field: str, value: object):
            def mutate(world: dict) -> None:
                class_ledger(world)[field] = value

            return mutate

        mutations = {
            "missing_class_ledger": delete_class_ledger,
            "unknown_class_field": add_unknown_class_field,
            "class_format": mutate_class_format,
            "nested_topology_flag": mutate_nested_topology_flag,
            "model_literal": mutate_model_literal,
            "model_topology_flag": mutate_model_topology_flag,
            "model_membership_flag": set_model_field(
                "crust_transport_coverage_membership_area_class_source_membership_resolved",
                False,
            ),
            "model_positive_area_serialization": set_model_field(
                "crust_transport_positive_area_serialization_model",
                "fixed_decimal_quantized",
            ),
            "model_physical_fate_flag": set_model_field(
                "crust_transport_coverage_membership_area_class_physical_fate_resolved",
                True,
            ),
            "model_slab_selection_flag": set_model_field(
                "crust_transport_coverage_membership_area_class_slab_selection_resolved",
                True,
            ),
            "model_local_kinematics_flag": set_model_field(
                "crust_transport_coverage_membership_area_class_local_kinematics_resolved",
                True,
            ),
            "nested_membership_flag": set_nested_field(
                "source_membership_resolved", False
            ),
            "nested_physical_fate_flag": set_nested_field(
                "physical_fate_resolved", True
            ),
            "nested_slab_selection_flag": set_nested_field(
                "slab_selection_resolved", True
            ),
            "nested_local_kinematics_flag": set_nested_field(
                "local_kinematics_resolved", True
            ),
            "nested_coalescing_key": set_nested_field(
                "coalescing_key", "unsorted_source_ids"
            ),
            "nested_edge_tolerance": set_nested_field(
                "edge_area_reconstruction_tolerance_basis",
                "edge_relative_tolerance",
            ),
            "fractional_class_offset": mutate_fractional_class_offset,
            "class_offset_terminal": mutate_class_offset_terminal,
            "string_class_area": mutate_string_class_area,
            "class_area_closure": mutate_class_area_closure,
            "fractional_multiplicity": mutate_fractional_multiplicity,
            "multiplicity_membership_mismatch": (
                mutate_multiplicity_membership_mismatch
            ),
            "representative_availability": mutate_representative_availability,
            "representative_norm": mutate_representative_norm,
            "fractional_contributor_offset": mutate_fractional_contributor_offset,
            "source_outside_destination_row": (
                mutate_source_outside_destination_row
            ),
            "duplicate_class_contributor": mutate_duplicate_class_contributor,
            "source_plate_linkage": mutate_source_plate_linkage,
            "noncanonical_class_order": swap_adjacent_classes_out_of_order,
            "fractional_class_count": mutate_fractional_class_count,
            "class_count_mirror": mutate_class_count_mirror,
            "total_class_count": mutate_total_class_count,
            "maximum_class_count": mutate_maximum_class_count,
            "identity_representative": mutate_identity_representative,
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                altered = deepcopy(self.world)
                mutate(altered)
                replay = validate_crust_overlap_transport(altered)
                self.assertFalse(replay["passed"], replay)
                self.assertTrue(replay["failures"])

    def test_serialized_overlap_ledger_mutations_are_rejected(self) -> None:
        cell_count = len(self.world["cells"])

        def mutate_csr_offset(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "destination_offsets"
            ][0] = 1

        def mutate_fractional_csr_offset(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "destination_offsets"
            ][0] += 0.5

        def mutate_fractional_source_id(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "source_cell_ids"
            ][0] += 0.5

        def mutate_string_dominant_id(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["dominant_source_cell_ids"][0] = str(
                ledger["dominant_source_cell_ids"][0]
            )

        def mutate_initial_crust_age_alias(world: dict) -> None:
            world["cells"][0]["initial_crust_age_ma"] += 10.0

        def mutate_initial_crust_thickness_alias(world: dict) -> None:
            world["cells"][0]["initial_crust_thickness_km"] += 1.0

        def mutate_initial_crust_density_alias(world: dict) -> None:
            world["cells"][0]["initial_crust_density"] += 0.1

        def mutate_out_of_range_initial_type(world: dict) -> None:
            world["plate_motion_history"][0]["crust_type_by_cell"][0] = 99

        def delete_global_gap_scalar(world: dict) -> None:
            del world["plate_motion_history"][1]["crust_overlap_ledger"][
                "global_uncovered_gap_area_km2"
            ]

        def append_zero_histogram_bin(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "global_coverage_area_km2_by_multiplicity"
            ].append(0.0)

        def mutate_overlap_weight(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["overlap_area_km2"][0] *= 1.01

        def mutate_transported_inventory(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["transported_inventory"]["crust_volume_km3"] *= 1.01

        def mutate_source_absolute_closure(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["maximum_source_area_closure_error_km2"] += 1.0

        def mutate_source_relative_closure(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["maximum_source_area_relative_closure_error"] += 0.5

        def mutate_destination_closure(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["maximum_destination_partition_closure_error_km2"] += 1.0

        def mutate_global_balance(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["global_gap_overlap_balance_residual_km2"] += 1.0

        def mutate_coverage_histogram(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["global_coverage_area_km2_by_multiplicity"][0] += 1.0

        def mutate_legacy_dominant_alias(world: dict) -> None:
            step = world["plate_motion_history"][1]
            step["crust_source_cell_ids"][0] = _different_id(
                step["crust_source_cell_ids"][0], cell_count
            )

        def mutate_canonical_dominant_alias(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["dominant_source_cell_ids"][0] = _different_id(
                ledger["dominant_source_cell_ids"][0], cell_count
            )

        def mutate_remapped_category(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["remapped_crust_type_by_cell"][0] = (
                ledger["remapped_crust_type_by_cell"][0] + 1
            ) % 9

        def mutate_process_inventory_delta(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["process_inventory_delta"]["crust_volume_km3"] += 1.0e6

        def mutate_summary_count(world: dict) -> None:
            world["summary"]["total_crust_overlap_sparse_edge_count"] += 1

        def mutate_fractional_summary_count(world: dict) -> None:
            world["summary"]["total_crust_overlap_sparse_edge_count"] += 0.75

        def mutate_summary_scalar(world: dict) -> None:
            world["summary"][
                "maximum_crust_source_area_closure_error_km2"
            ] += 1.0

        def mutate_transport_backend_metadata(world: dict) -> None:
            world["plate_kinematic_model"][
                "crust_transport_execution_backend"
            ] = "cuda"

        def mutate_backend_execution_metadata(world: dict) -> None:
            world["backend"]["crust_transport_execution_backend"] = "cuda"

        def mutate_backend_cpu_transition_count(world: dict) -> None:
            world["backend"][
                "cpu_conservative_crust_overlap_transition_count"
            ] += 1

        def mutate_legacy_accelerator_dispatch_count(world: dict) -> None:
            world["backend"]["opencl_crust_source_remap_dispatch_count"] += 1

        def mutate_arrangement_fragment_count(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["coverage_arrangement_fragment_count_by_cell"][0] = 0

        def mutate_arrangement_maximum(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["maximum_coverage_arrangement_line_count"] += 1

        def mutate_arrangement_nonmaximum_count(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["coverage_arrangement_line_count_by_cell"][0] += 1

        def mutate_fractional_arrangement_count(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["coverage_arrangement_fragment_count_by_cell"][0] += 0.75

        def mutate_transport_distance(world: dict) -> None:
            world["plate_motion_history"][1][
                "crust_transport_distance_km_by_cell"
            ][0] += 1000.0

        def mutate_source_kinematic_distance(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "source_kinematic_distance_km"
            ][0] += 1000.0

        def mutate_edge_residual_distance(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "remap_residual_distance_km"
            ][0] += 1000.0

        def mutate_transport_scalar_mirror(world: dict) -> None:
            world["plate_motion_history"][1][
                "mean_crust_transport_distance_km"
            ] += 1.0

        def mutate_rotation_axis_witness(world: dict) -> None:
            axis = world["plate_motion_history"][1]["plates"][0][
                "rotation_axis"
            ]
            replacement = [1.0, 0.0, 0.0]
            if abs(axis[0] - 1.0) < 1.0e-6:
                replacement = [0.0, 1.0, 0.0]
            axis[:] = replacement

        def mutate_process_inventory_metadata(world: dict) -> None:
            world["plate_kinematic_model"][
                "tectonic_process_inventory_changes_separately_ledgered"
            ] = False

        def mutate_crust_advection_metadata(world: dict) -> None:
            world["plate_kinematic_model"]["crust_advection_resolved"] = False

        def delete_process_reason(world: dict) -> None:
            del world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"][0]

        def swap_process_reasons(world: dict) -> None:
            reasons = world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"]
            reasons[0], reasons[1] = reasons[1], reasons[0]

        def mutate_process_reason_name(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"][0]["reason"] = "unknown_process"

        def mutate_fractional_reason_count(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"][0]["triggered_cell_count"] += 0.5

        def mutate_reason_changed_count(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"][0]["extensive_state_changed_cell_count"] += 1

        def mutate_reason_positive_delta(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"][0]["positive_delta"]["crust_volume_km3"] += 1.0e6

        def mutate_reason_negative_delta(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"][0]["negative_delta_magnitude"][
                "crust_volume_km3"
            ] += 1.0e6

        def mutate_reason_net_delta(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"][0]["net_delta"]["crust_volume_km3"] += 1.0e6

        def mutate_attributed_delta(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["attributed_inventory_delta"]["crust_volume_km3"] += 1.0e6

        def mutate_attribution_residual(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["numerical_closure_residual"]["crust_volume_km3"] += 1.0e-4

        def mutate_reconciled_delta(world: dict) -> None:
            world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reconciled_inventory_delta"]["crust_volume_km3"] += 1.0e-4

        def mutate_boundary_input(world: dict) -> None:
            world["plate_motion_history"][1]["boundary_convergent_by_cell"][0] = 1.0

        def mutate_rule_accounting_metadata(world: dict) -> None:
            world["plate_kinematic_model"][
                "tectonic_process_rule_state_source_sink_accounting_resolved"
            ] = False

        def mutate_material_provenance_metadata(world: dict) -> None:
            world["plate_kinematic_model"][
                "tectonic_process_material_provenance_resolved"
            ] = True

        def mutate_categorical_remap_metadata(world: dict) -> None:
            world["plate_kinematic_model"]["crust_categorical_remap_model"] = (
                "independent_marginal_modes"
            )

        def mutate_oceanic_classification_metadata(world: dict) -> None:
            world["plate_kinematic_model"][
                "oceanic_state_classification_model"
            ] = "numeric_threshold_only"

        def mutate_subduction_proxy_semantics(world: dict) -> None:
            world["plate_kinematic_model"][
                "oceanic_convergence_subduction_proxy_semantics"
            ] = "physical_crust_removal_flux"

        def mutate_accretion_proxy_semantics(world: dict) -> None:
            world["plate_kinematic_model"][
                "plate_crossing_accretion_proxy_semantics"
            ] = "external_reservoir_provenance"

        mutations = {
            "csr_offset": mutate_csr_offset,
            "fractional_csr_offset": mutate_fractional_csr_offset,
            "fractional_source_id": mutate_fractional_source_id,
            "string_dominant_id": mutate_string_dominant_id,
            "initial_crust_age_alias": mutate_initial_crust_age_alias,
            "initial_crust_thickness_alias": mutate_initial_crust_thickness_alias,
            "initial_crust_density_alias": mutate_initial_crust_density_alias,
            "out_of_range_initial_type": mutate_out_of_range_initial_type,
            "missing_global_gap_scalar": delete_global_gap_scalar,
            "trailing_zero_histogram_bin": append_zero_histogram_bin,
            "overlap_weight": mutate_overlap_weight,
            "transported_inventory": mutate_transported_inventory,
            "source_absolute_closure": mutate_source_absolute_closure,
            "source_relative_closure": mutate_source_relative_closure,
            "destination_closure": mutate_destination_closure,
            "global_gap_overlap_balance": mutate_global_balance,
            "coverage_histogram": mutate_coverage_histogram,
            "legacy_dominant_alias": mutate_legacy_dominant_alias,
            "canonical_dominant_alias": mutate_canonical_dominant_alias,
            "remapped_category": mutate_remapped_category,
            "process_inventory_delta": mutate_process_inventory_delta,
            "summary_count": mutate_summary_count,
            "fractional_summary_count": mutate_fractional_summary_count,
            "summary_scalar": mutate_summary_scalar,
            "transport_backend_metadata": mutate_transport_backend_metadata,
            "backend_execution_metadata": mutate_backend_execution_metadata,
            "backend_cpu_transition_count": mutate_backend_cpu_transition_count,
            "legacy_accelerator_dispatch_count": (
                mutate_legacy_accelerator_dispatch_count
            ),
            "arrangement_fragment_count": mutate_arrangement_fragment_count,
            "arrangement_maximum": mutate_arrangement_maximum,
            "arrangement_nonmaximum_count": (
                mutate_arrangement_nonmaximum_count
            ),
            "fractional_arrangement_count": mutate_fractional_arrangement_count,
            "transport_distance": mutate_transport_distance,
            "source_kinematic_distance": mutate_source_kinematic_distance,
            "edge_residual_distance": mutate_edge_residual_distance,
            "transport_scalar_mirror": mutate_transport_scalar_mirror,
            "rotation_axis_witness": mutate_rotation_axis_witness,
            "process_inventory_metadata": mutate_process_inventory_metadata,
            "crust_advection_metadata": mutate_crust_advection_metadata,
            "missing_process_reason": delete_process_reason,
            "swapped_process_reasons": swap_process_reasons,
            "process_reason_name": mutate_process_reason_name,
            "fractional_reason_count": mutate_fractional_reason_count,
            "reason_changed_count": mutate_reason_changed_count,
            "reason_positive_delta": mutate_reason_positive_delta,
            "reason_negative_delta": mutate_reason_negative_delta,
            "reason_net_delta": mutate_reason_net_delta,
            "attributed_delta": mutate_attributed_delta,
            "attribution_residual": mutate_attribution_residual,
            "reconciled_delta": mutate_reconciled_delta,
            "boundary_input": mutate_boundary_input,
            "rule_accounting_metadata": mutate_rule_accounting_metadata,
            "material_provenance_metadata": mutate_material_provenance_metadata,
            "categorical_remap_metadata": mutate_categorical_remap_metadata,
            "oceanic_classification_metadata": (
                mutate_oceanic_classification_metadata
            ),
            "subduction_proxy_semantics": mutate_subduction_proxy_semantics,
            "accretion_proxy_semantics": mutate_accretion_proxy_semantics,
        }

        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                altered = deepcopy(self.world)
                mutate(altered)
                replay = validate_crust_overlap_transport(altered)
                self.assertFalse(replay["passed"], replay)
                self.assertTrue(replay["failures"])
