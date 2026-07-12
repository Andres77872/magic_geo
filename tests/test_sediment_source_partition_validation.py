from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.api import generate_geo_world
from magic_geo.config import WorldConfig, load_config
from magic_geo.sediment_source_partition_validation import (
    COMMON_AUDIT_METADATA,
    FLUVIAL_ACTIVE_VOLUME_THRESHOLD_KM3,
    MODEL_METADATA,
    validate_sediment_source_partitions,
)


def _config(*, threads: int = 1) -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["run"]["seed"] = 20260711
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    data["erosion"]["iterations"] = 2
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = threads
    data["output"]["float_precision"] = 8
    return WorldConfig.model_validate(data)


class SedimentSourcePartitionGeneratedTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(_config(threads=1))
        cls.parallel = generate_geo_world(_config(threads=4))

    def assert_rejected(self, world: dict) -> None:
        result = validate_sediment_source_partitions(world)
        self.assertFalse(result["passed"])
        self.assertTrue(result["failures"])

    def test_generated_models_and_all_histories_replay(self) -> None:
        result = validate_sediment_source_partitions(self.world)

        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["metrics"]["cell_count"], 128)
        self.assertEqual(result["metrics"]["hillslope_stage_count"], 2)
        self.assertEqual(result["metrics"]["fluvial_stage_count"], 2)
        self.assertEqual(result["metrics"]["glacial_stage_count"], 1)
        self.assertLessEqual(
            result["metrics"]["fluvial_threshold_omitted_volume_km3"],
            result["metrics"]["fluvial_threshold_omitted_cell_count"]
            * FLUVIAL_ACTIVE_VOLUME_THRESHOLD_KM3,
        )
        for metadata in MODEL_METADATA.values():
            model = self.world[metadata["model_key"]]
            for key, expected in COMMON_AUDIT_METADATA.items():
                self.assertEqual(model[key], expected)

    def test_thread_count_keeps_partition_evidence_bit_identical(self) -> None:
        for world in (self.world, self.parallel):
            result = validate_sediment_source_partitions(world)
            self.assertTrue(result["passed"], result["failures"])
        for key in (
            "hillslope_sediment_transport_history",
            "fluvial_sediment_routing_history",
            "glacial_sediment_transport_history",
        ):
            self.assertEqual(self.world[key], self.parallel[key])

    def test_metadata_shape_link_and_numeric_mutations_are_rejected(self) -> None:
        mutations = []

        def false_mass_claim(world: dict) -> None:
            world["hillslope_sediment_transport_model"][
                "source_partition_audit_is_mass_claim"
            ] = True

        mutations.append(false_mass_claim)

        def false_provenance_claim(world: dict) -> None:
            world["glacial_sediment_transport_model"][
                "source_partition_audit_is_provenance_claim"
            ] = True

        mutations.append(false_provenance_claim)

        def wrong_demand_field(world: dict) -> None:
            world["fluvial_sediment_routing_model"][
                "source_partition_audit_demand_field"
            ] = "partition_sum"

        mutations.append(wrong_demand_field)

        def ambiguous_mass_semantics(world: dict) -> None:
            world["fluvial_sediment_routing_model"][
                "mass_conserving_semantics"
            ] = "physical_dry_rock_mass"

        mutations.append(ambiguous_mass_semantics)

        def bad_cell_count(world: dict) -> None:
            world["hillslope_sediment_transport_history"][0]["cell_count"] += 1

        mutations.append(bad_cell_count)

        def noncanonical_input_cell(world: dict) -> None:
            world["glacial_sediment_transport_history"][0]["input_cells"][0][
                "cell_id"
            ] = 1

        mutations.append(noncanonical_input_cell)

        def bad_feedback_link(world: dict) -> None:
            world["fluvial_sediment_routing_history"][0][
                "feedback_stage_id"
            ] += 1

        mutations.append(bad_feedback_link)

        def shortened_array(world: dict) -> None:
            world["hillslope_sediment_transport_history"][0][
                "alluvium_entrainment_depth_m_by_cell"
            ].pop()

        mutations.append(shortened_array)

        def negative_depth(world: dict) -> None:
            world["glacial_sediment_transport_history"][0][
                "bedrock_erosion_depth_m_by_cell"
            ][0] = -1.0

        mutations.append(negative_depth)

        def nonfinite_depth(world: dict) -> None:
            world["fluvial_sediment_routing_history"][0][
                "source_production_depth_m_by_cell"
            ][0] = math.inf

        mutations.append(nonfinite_depth)

        def numeric_string_depth(world: dict) -> None:
            world["hillslope_sediment_transport_history"][0][
                "source_production_depth_m_by_cell"
            ][0] = "0.0"

        mutations.append(numeric_string_depth)

        for mutation in mutations:
            with self.subTest(mutation=mutation.__name__):
                altered = deepcopy(self.world)
                mutation(altered)
                self.assert_rejected(altered)

    def test_partition_and_area_aggregate_mutations_are_rejected(self) -> None:
        altered = deepcopy(self.world)
        stage = altered["hillslope_sediment_transport_history"][0]
        source_id = next(
            index
            for index, value in enumerate(
                stage["source_production_depth_m_by_cell"]
            )
            if value > 0.0
        )
        stage["bedrock_erosion_depth_m_by_cell"][source_id] += 0.01
        self.assert_rejected(altered)

        altered = deepcopy(self.world)
        altered["fluvial_sediment_routing_history"][0][
            "alluvium_entrainment_volume_km3"
        ] += 1.0
        self.assert_rejected(altered)

    def test_coherent_array_and_aggregate_mutation_still_fails_route_replay(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        stage = altered["hillslope_sediment_transport_history"][0]
        source_id = int(stage["edges"][0]["source_cell_id"])
        depth_delta = 0.01
        volume_delta = (
            altered["cells"][source_id]["area_km2"] * depth_delta / 1000.0
        )
        stage["source_production_depth_m_by_cell"][source_id] += depth_delta
        stage["bedrock_erosion_depth_m_by_cell"][source_id] += depth_delta
        stage["production_volume_km3"] += volume_delta
        stage["bedrock_erosion_volume_km3"] += volume_delta
        model = altered["hillslope_sediment_transport_model"]
        model["total_production_volume_km3"] += volume_delta
        model["total_bedrock_erosion_volume_km3"] += volume_delta

        self.assert_rejected(altered)

    def test_sub_old_tolerance_route_mutations_are_rejected(self) -> None:
        altered = deepcopy(self.world)
        altered["hillslope_sediment_transport_history"][0]["edges"][0][
            "source_production_depth_m"
        ] += 1.0e-9
        self.assert_rejected(altered)

        altered = deepcopy(self.world)
        transfers = altered["glacial_sediment_transport_history"][0][
            "transfers"
        ]
        if transfers:
            transfers[0]["source_production_depth_m"] += 1.0e-9
            self.assert_rejected(altered)

    def test_volume_preserving_alluvium_bedrock_swap_fails_alluvium_first(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        stage = altered["hillslope_sediment_transport_history"][1]
        alluvium = stage["alluvium_entrainment_depth_m_by_cell"]
        bedrock = stage["bedrock_erosion_depth_m_by_cell"]
        first = next(index for index, value in enumerate(alluvium) if value > 0.0)
        second = next(
            index
            for index, value in enumerate(bedrock)
            if value > 0.0 and index != first
        )
        first_area = float(altered["cells"][first]["area_km2"])
        second_area = float(altered["cells"][second]["area_km2"])
        shifted_volume = min(
            alluvium[first] * first_area,
            bedrock[second] * second_area,
        ) / 1000.0 * 0.05
        first_depth = shifted_volume * 1000.0 / first_area
        second_depth = shifted_volume * 1000.0 / second_area
        alluvium[first] -= first_depth
        bedrock[first] += first_depth
        alluvium[second] += second_depth
        bedrock[second] -= second_depth

        self.assert_rejected(altered)

    def test_coherent_glacial_partition_mutation_fails_alluvium_first(self) -> None:
        altered = deepcopy(self.world)
        stage = altered["glacial_sediment_transport_history"][0]
        alluvium = stage["alluvium_entrainment_depth_m_by_cell"]
        bedrock = stage["bedrock_erosion_depth_m_by_cell"]
        cell_id = next(index for index, value in enumerate(alluvium) if value > 0.0)
        depth_delta = alluvium[cell_id] * 0.05
        volume_delta = (
            altered["cells"][cell_id]["area_km2"] * depth_delta / 1000.0
        )
        alluvium[cell_id] -= depth_delta
        bedrock[cell_id] += depth_delta
        stage["alluvium_entrainment_volume_km3"] -= volume_delta
        stage["bedrock_erosion_volume_km3"] += volume_delta
        model = altered["glacial_sediment_transport_model"]
        model["total_alluvium_entrainment_volume_km3"] -= volume_delta
        model["total_bedrock_erosion_volume_km3"] += volume_delta

        self.assert_rejected(altered)

    def test_coherent_fluvial_partition_mutation_fails_alluvium_first(self) -> None:
        altered = deepcopy(self.world)
        stage = altered["fluvial_sediment_routing_history"][1]
        alluvium = stage["alluvium_entrainment_depth_m_by_cell"]
        bedrock = stage["bedrock_erosion_depth_m_by_cell"]
        cell_id = next(index for index, value in enumerate(alluvium) if value > 0.0)
        depth_delta = alluvium[cell_id] * 0.05
        volume_delta = (
            altered["cells"][cell_id]["area_km2"] * depth_delta / 1000.0
        )
        alluvium[cell_id] -= depth_delta
        bedrock[cell_id] += depth_delta
        stage["alluvium_entrainment_volume_km3"] -= volume_delta
        stage["bedrock_erosion_volume_km3"] += volume_delta
        model = altered["fluvial_sediment_routing_model"]
        model["total_alluvium_entrainment_volume_km3"] -= volume_delta
        model["total_bedrock_erosion_volume_km3"] += volume_delta

        self.assert_rejected(altered)

    def test_fluvial_unserialized_source_is_allowed_only_below_threshold(
        self,
    ) -> None:
        stage = self.world["fluvial_sediment_routing_history"][0]
        active_ids = {int(step["cell_id"]) for step in stage["cell_steps"]}
        cell_id = next(
            index
            for index, depth in enumerate(
                stage["source_production_depth_m_by_cell"]
            )
            if index not in active_ids and depth == 0.0
        )
        area = float(self.world["cells"][cell_id]["area_km2"])

        below = deepcopy(self.world)
        below_stage = below["fluvial_sediment_routing_history"][0]
        below_depth = 0.5 * FLUVIAL_ACTIVE_VOLUME_THRESHOLD_KM3 * 1000.0 / area
        below_stage["source_production_depth_m_by_cell"][cell_id] = below_depth
        below_stage["bedrock_erosion_depth_m_by_cell"][cell_id] = below_depth
        result = validate_sediment_source_partitions(below)
        self.assertTrue(result["passed"], result["failures"])
        self.assertGreaterEqual(
            result["metrics"]["fluvial_threshold_omitted_cell_count"], 1
        )

        above = deepcopy(self.world)
        above_stage = above["fluvial_sediment_routing_history"][0]
        above_depth = 2.0 * FLUVIAL_ACTIVE_VOLUME_THRESHOLD_KM3 * 1000.0 / area
        above_stage["source_production_depth_m_by_cell"][cell_id] = above_depth
        above_stage["bedrock_erosion_depth_m_by_cell"][cell_id] = above_depth
        self.assert_rejected(above)

    def test_malformed_root_is_reported_not_raised(self) -> None:
        result = validate_sediment_source_partitions({"cells": "bad"})
        self.assertFalse(result["passed"])
        self.assertTrue(result["failures"])
