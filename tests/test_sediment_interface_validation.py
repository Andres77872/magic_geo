from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.api import generate_geo_world
from magic_geo.config import WorldConfig, load_config
from magic_geo.sediment_interface_validation import (
    MODEL_LITERAL_VALUES,
    validate_sediment_interfaces,
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


class SedimentInterfaceGeneratedTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(_config(threads=1))
        cls.parallel = generate_geo_world(_config(threads=4))

    def assert_rejected(self, world: object) -> None:
        result = validate_sediment_interfaces(world)
        self.assertFalse(result["passed"])
        self.assertTrue(result["failures"])

    def test_generated_interface_geometry_replays(self) -> None:
        result = validate_sediment_interfaces(self.world)

        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["metrics"]["cell_count"], 128)
        self.assertEqual(result["metrics"]["erosion_stage_count"], 2)
        self.assertEqual(result["metrics"]["glacial_stage_count"], 1)
        self.assertTrue(
            result["metrics"]["authoritative_interface_geometry"]
        )
        self.assertFalse(result["metrics"]["dry_rock_mass_resolved"])
        self.assertFalse(result["metrics"]["porosity_resolved"])
        self.assertFalse(result["metrics"]["grain_provenance_resolved"])
        model = self.world["sediment_interface_model"]
        for field, expected in MODEL_LITERAL_VALUES.items():
            self.assertEqual(model[field], expected)

    def test_thread_count_keeps_interface_state_bit_identical(self) -> None:
        for world in (self.world, self.parallel):
            result = validate_sediment_interfaces(world)
            self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(
            self.world["sediment_interface_model"],
            self.parallel["sediment_interface_model"],
        )
        self.assertEqual(
            [
                cell["bedrock_surface_elevation_m"]
                for cell in self.world["cells"]
            ],
            [
                cell["bedrock_surface_elevation_m"]
                for cell in self.parallel["cells"]
            ],
        )

    def test_zero_erosion_iterations_still_close_initial_and_glacial_paths(
        self,
    ) -> None:
        data = _config(threads=1).model_dump(mode="python")
        data["erosion"]["iterations"] = 0
        world = generate_geo_world(WorldConfig.model_validate(data))

        result = validate_sediment_interfaces(world)

        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["metrics"]["erosion_stage_count"], 0)
        self.assertEqual(result["metrics"]["glacial_stage_count"], 1)
        self.assertEqual(world["hillslope_sediment_transport_history"], [])
        self.assertEqual(world["fluvial_sediment_routing_history"], [])

    def test_zero_ocean_unclassified_land_sink_fallback_replays(self) -> None:
        data = _config(threads=1).model_dump(mode="python")
        data["planet"]["ocean_fraction_target"] = 0.0
        data["planet"]["ocean_water_inventory_km3"] = 0.0
        data["climate"]["precipitation_scale"] = 0.12
        world = generate_geo_world(WorldConfig.model_validate(data))

        fallback_allocations = []
        for stage in world["fluvial_sediment_routing_history"]:
            routing_input_by_id = {
                cell["cell_id"]: cell for cell in stage["input_cells"]
            }
            for allocation in stage["terminal_allocations"]:
                target = routing_input_by_id[allocation["target_cell_id"]]
                if allocation["depression_component_id"] == -1:
                    fallback_allocations.append((allocation, target))

        self.assertTrue(
            fallback_allocations,
            "fixture needs an unclassified dry terminal fallback",
        )
        for allocation, target in fallback_allocations:
            self.assertEqual(
                allocation["target_cell_id"], allocation["sink_cell_id"]
            )
            self.assertFalse(target["is_water"])
            self.assertEqual(target["flow_to_cell_id"], -1)
            self.assertEqual(target["depression_component_id"], -1)
            self.assertEqual(target["depression_sink_cell_id"], -1)

        result = validate_sediment_interfaces(world)
        self.assertTrue(result["passed"], result["failures"])

        altered = deepcopy(world)
        altered_fallback = next(
            allocation
            for stage in altered["fluvial_sediment_routing_history"]
            for allocation in stage["terminal_allocations"]
            if allocation["depression_component_id"] == -1
        )
        altered_fallback["depression_component_id"] = 0
        self.assert_rejected(altered)

    def test_zero_general_output_precision_does_not_weaken_interface_replay(
        self,
    ) -> None:
        data = _config(threads=1).model_dump(mode="python")
        data["output"]["float_precision"] = 0
        world = generate_geo_world(WorldConfig.model_validate(data))

        result = validate_sediment_interfaces(world)
        self.assertTrue(result["passed"], result["failures"])

        altered = deepcopy(world)
        altered["cells"][0]["bedrock_surface_elevation_m"] += 0.0001
        altered["cells"][0]["elevation_m"] += 0.0001
        self.assert_rejected(altered)

    def test_model_claim_and_schema_mutations_are_rejected(self) -> None:
        for mutation in (
            lambda world: world["sediment_interface_model"].__setitem__(
                "dry_rock_mass_resolved", True
            ),
            lambda world: world["sediment_interface_model"].__setitem__(
                "interface_equation", "surface=bedrock"
            ),
            lambda world: world["sediment_interface_model"].__setitem__(
                "unexpected_claim", True
            ),
            lambda world: world["sediment_interface_model"].__setitem__(
                "maximum_final_closure_residual_m", 1.0
            ),
        ):
            altered = deepcopy(self.world)
            mutation(altered)
            self.assert_rejected(altered)

    def test_final_state_and_coherent_surface_mirror_mutations_are_rejected(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["cells"][0]["bedrock_surface_elevation_m"] += 0.01
        self.assert_rejected(altered)

        colluding = deepcopy(self.world)
        colluding["cells"][0]["bedrock_surface_elevation_m"] += 0.01
        colluding["cells"][0]["elevation_m"] += 0.01
        self.assert_rejected(colluding)

    def test_coherent_final_mobile_and_surface_mutation_is_rejected(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["cells"][0]["sediment_thickness_m"] += 1.0
        altered["cells"][0]["elevation_m"] += 1.0

        self.assert_rejected(altered)

    def test_initial_and_final_interface_collusion_is_rejected(self) -> None:
        altered = deepcopy(self.world)
        altered["cells"][0]["initial_elevation_m"] += 1.0
        altered["cells"][0]["bedrock_surface_elevation_m"] += 1.0
        altered["cells"][0]["elevation_m"] += 1.0

        self.assert_rejected(altered)

    def test_tectonic_history_and_final_interface_collusion_is_rejected(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        erosion_feedback = next(
            record
            for record in altered["earth_system_feedback_history"]
            if record["stage"] == "erosion_iteration"
        )
        motion_id = erosion_feedback["plate_motion_history_id"]
        motion = next(
            record
            for record in altered["plate_motion_history"]
            if record["id"] == motion_id
        )
        cell_id = 0
        motion["tectonic_elevation_change_m_by_cell"][cell_id] += 1.0
        altered["cells"][cell_id][
            "cumulative_tectonic_elevation_change_m"
        ] += 1.0
        altered["cells"][cell_id]["bedrock_surface_elevation_m"] += 1.0
        altered["cells"][cell_id]["elevation_m"] += 1.0

        self.assert_rejected(altered)

    def test_nonfinite_sea_level_adjustment_is_rejected(self) -> None:
        altered = deepcopy(self.world)
        altered["earth_system_feedback_history"][0][
            "sea_level_adjustment_m"
        ] = float("inf")

        self.assert_rejected(altered)

    def test_fluvial_deposition_and_mobile_snapshot_collusion_is_rejected(
        self,
    ) -> None:
        # Select a positive capacity-deposition witness that is not touched by
        # a later numeric depression correction.  That keeps the adversarial
        # offset present through every later opening snapshot and final state.
        numeric_cells_by_feedback: dict[int, set[int]] = {}
        for event in self.world["numeric_depression_fill_history"]:
            event_cells = numeric_cells_by_feedback.setdefault(
                event["feedback_stage_id"], set()
            )
            for field in (
                "cell_ids",
                "breach_path_cell_ids",
                "breach_deposition_cell_ids",
            ):
                event_cells.update(event.get(field, []))

        candidates: list[tuple[int, int, int, int]] = []
        fluvial_history = self.world["fluvial_sediment_routing_history"]
        for stage_index, stage in enumerate(fluvial_history):
            feedback_id = stage["feedback_stage_id"]
            if numeric_cells_by_feedback:
                later_numeric_cells = set().union(
                    *(
                        cells
                        for event_feedback, cells in (
                            numeric_cells_by_feedback.items()
                        )
                        if event_feedback >= feedback_id
                    )
                )
            else:
                later_numeric_cells = set()
            for step_index, step in enumerate(stage["cell_steps"]):
                cell_id = step["cell_id"]
                if (
                    step["capacity_deposition_volume_km3"] > 0.0
                    and cell_id not in later_numeric_cells
                ):
                    candidates.append(
                        (feedback_id, cell_id, stage_index, step_index)
                    )

        self.assertTrue(candidates, "fixture needs a positive fluvial deposit")
        feedback_id, cell_id, stage_index, step_index = max(
            candidates,
            key=lambda candidate: (candidate[0], -candidate[1]),
        )
        altered = deepcopy(self.world)
        delta_volume_km3 = 1.0
        delta_depth_m = (
            delta_volume_km3 * 1000.0 / altered["cells"][cell_id]["area_km2"]
        )
        altered["fluvial_sediment_routing_history"][stage_index][
            "cell_steps"
        ][step_index]["capacity_deposition_volume_km3"] += delta_volume_km3

        for history_name in (
            "hillslope_sediment_transport_history",
            "glacial_sediment_transport_history",
        ):
            for stage in altered[history_name]:
                if stage["feedback_stage_id"] <= feedback_id:
                    continue
                input_cell = next(
                    item
                    for item in stage["input_cells"]
                    if item["cell_id"] == cell_id
                )
                input_cell["sediment_thickness_m"] += delta_depth_m

        altered["cells"][cell_id][
            "sediment_thickness_m"
        ] += delta_depth_m
        altered["cells"][cell_id]["elevation_m"] += delta_depth_m

        self.assert_rejected(altered)

    def test_fluvial_stage_aggregates_and_inactive_step_are_rejected(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["fluvial_sediment_routing_history"][0][
            "local_source_volume_km3"
        ] += 1.0
        self.assert_rejected(altered)

        fabricated = deepcopy(self.world)
        stage = fabricated["fluvial_sediment_routing_history"][0]
        active_ids = {step["cell_id"] for step in stage["cell_steps"]}
        inactive_id = next(
            cell["id"]
            for cell in fabricated["cells"]
            if cell["id"] not in active_ids
        )
        zero_step = deepcopy(stage["cell_steps"][0])
        zero_step.update(
            {
                "cell_id": inactive_id,
                "flow_to_cell_id": -1,
                "depression_component_id": -1,
                "depression_sink_cell_id": -1,
                "water_body_type": "land",
                "is_water": False,
                "is_river": False,
                "is_lake": False,
                "lake_overflows": False,
                "is_land_terminal": True,
                "is_marine_terminal": False,
                "cell_area_km2": fabricated["cells"][inactive_id][
                    "area_km2"
                ],
                "flow_accumulation": 0.0,
                "runoff_mm_y": 0.0,
                "hydrologic_flow_slope": 0.0,
                "routing_base_elevation_m": 0.0,
                "spill_elevation_m": 0.0,
                "local_source_volume_km3": 0.0,
                "incoming_volume_km3": 0.0,
                "available_volume_km3": 0.0,
                "transport_capacity_fraction": 0.0,
                "depression_accommodation_volume_km3": 0.0,
                "capacity_deposition_volume_km3": 0.0,
                "depression_fill_deposition_volume_km3": 0.0,
                "lake_trap_deposition_volume_km3": 0.0,
                "marine_deposition_volume_km3": 0.0,
                "routed_outgoing_volume_km3": 0.0,
                "terminal_land_storage_volume_km3": 0.0,
                "terminal_export_volume_km3": 0.0,
                "local_mass_balance_residual_km3": 0.0,
            }
        )
        stage["cell_steps"].append(zero_step)
        stage["active_cell_step_count"] += 1
        stage["land_terminal_count"] += 1
        self.assert_rejected(fabricated)

    def test_fluvial_routing_snapshot_and_terminal_footprint_are_binding(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        stage = altered["fluvial_sediment_routing_history"][0]
        step = stage["cell_steps"][0]
        step["water_body_type"] = (
            "continental_shelf"
            if step["water_body_type"] != "continental_shelf"
            else "ocean"
        )
        self.assert_rejected(altered)

        altered = deepcopy(self.world)
        stage = altered["fluvial_sediment_routing_history"][0]
        input_cell = stage["input_cells"][0]
        input_cell["flow_to_cell_id"] = input_cell["cell_id"]
        self.assert_rejected(altered)

        altered = deepcopy(self.world)
        altered["fluvial_sediment_routing_model"][
            "stage_input_snapshot_used_for_replay"
        ] = False
        self.assert_rejected(altered)

    def test_history_link_shape_and_numeric_type_mutations_are_rejected(
        self,
    ) -> None:
        mutations = []

        def wrong_feedback_link(world: dict) -> None:
            world["hillslope_sediment_transport_history"][0][
                "feedback_stage_id"
            ] += 1

        mutations.append(wrong_feedback_link)

        def string_depth(world: dict) -> None:
            world["fluvial_sediment_routing_history"][0][
                "bedrock_erosion_depth_m_by_cell"
            ][0] = "0.0"

        mutations.append(string_depth)

        def string_datum_shift(world: dict) -> None:
            world["earth_system_feedback_history"][0][
                "sea_level_adjustment_m"
            ] = "0.0"

        mutations.append(string_datum_shift)

        def short_glacial_array(world: dict) -> None:
            world["glacial_sediment_transport_history"][0][
                "bedrock_erosion_depth_m_by_cell"
            ].pop()

        mutations.append(short_glacial_array)

        for mutation in mutations:
            altered = deepcopy(self.world)
            mutation(altered)
            self.assert_rejected(altered)

    def test_malformed_payloads_return_failures_instead_of_raising(self) -> None:
        for payload in (
            None,
            {},
            {"sediment_interface_model": []},
            {"sediment_interface_model": {}, "cells": "invalid"},
        ):
            self.assert_rejected(payload)


if __name__ == "__main__":
    import unittest

    unittest.main()
