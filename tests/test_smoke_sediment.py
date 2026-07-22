"""Sediment routing, basins, and stratigraphy assertions for the generated world.

Split out of the former single-method smoke test: each method re-derives
what it needs from the shared world, so they no longer depend on order.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.api import generate_world
from magic_geo.cli import app
from magic_geo.config import load_config
from magic_geo.sediment_interface_validation import validate_sediment_interfaces

from support import worlds


class SmokeSedimentTests(TestCase):
    def test_sedimentary_basins(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        small = worlds.canonical_config("small_smoke")
        summary = world["summary"]
        self.assertEqual(summary["sedimentary_basin_count"], len(world["sedimentary_basins"]))
        self.assertIn("active_sedimentary_basin_count", summary)
        self.assertEqual(
            summary["active_sedimentary_basin_count"],
            sum(1 for basin in world["sedimentary_basins"] if basin["is_active"]),
        )
        self.assertIn("sediment_budget_production_m", summary)
        self.assertIn("sediment_budget_deposition_m", summary)
        self.assertIn("sediment_budget_export_m", summary)
        self.assertIn("sediment_budget_residual_m", summary)
        self.assertEqual(
            summary["sediment_budget_closure_model"],
            "cell_area_weighted_hillslope_glacial_and_routed_deposition_terminal_export_volume_v5",
        )
        self.assertIn("sediment_budget_production_km3", summary)
        self.assertIn("sediment_budget_deposition_km3", summary)
        self.assertIn("sediment_budget_export_km3", summary)
        self.assertIn("sediment_budget_residual_km3", summary)
        self.assertIn("sediment_delivery_ratio", summary)
        self.assertGreaterEqual(summary["sediment_budget_production_m"], 0.0)
        self.assertGreaterEqual(summary["sediment_budget_deposition_m"], 0.0)
        self.assertGreaterEqual(summary["sediment_budget_export_m"], 0.0)
        self.assertLessEqual(
            summary["sediment_budget_residual_km3"],
            max(0.000001, summary["sediment_budget_production_km3"] * 1.0e-10),
        )
        self.assertAlmostEqual(
            summary["sediment_budget_production_km3"],
            summary["sediment_budget_deposition_km3"]
            + summary["sediment_budget_export_km3"],
            delta=max(
                0.000001,
                summary["sediment_budget_production_km3"] * 1.0e-10,
            ),
        )
        self.assertGreaterEqual(summary["sediment_delivery_ratio"], 0.0)
        self.assertLessEqual(summary["sediment_delivery_ratio"], 1.25)
        fluvial_model = world["fluvial_sediment_routing_model"]
        fluvial_history = world["fluvial_sediment_routing_history"]
        self.assertEqual(
            fluvial_model["model_type"],
            "topological_capacity_limited_fluvial_sediment_routing_v1",
        )
        self.assertEqual(
            fluvial_model["stage_count"],
            len(fluvial_history),
        )
        self.assertEqual(
            fluvial_model["stage_count"],
            small.erosion.iterations,
        )
        self.assertAlmostEqual(
            fluvial_model["total_local_source_volume_km3"],
            fluvial_model["total_deposition_volume_km3"]
            + fluvial_model["total_terminal_export_volume_km3"],
            delta=max(
                0.000001,
                fluvial_model["total_local_source_volume_km3"] * 1.0e-10,
            ),
        )
        self.assertEqual(
            summary["fluvial_sediment_routing_stage_count"],
            len(fluvial_history),
        )
        self.assertIn("largest_sedimentary_basin_area_km2", summary)
        self.assertIn("mean_sedimentary_basin_thickness_m", summary)
        self.assertEqual(summary["sediment_transport_history_count"], len(world["sediment_transport_histories"]))
        self.assertEqual(len(world["sediment_transport_histories"]), len(world["sedimentary_basins"]))
        self.assertEqual(
            summary["sediment_transport_history_step_count"],
            sum(history["time_step_count"] for history in world["sediment_transport_histories"]),
        )
        self.assertEqual(
            summary["active_sediment_transport_history_count"],
            sum(1 for history in world["sediment_transport_histories"] if history["total_deposition_m"] > 0.0),
        )
        self.assertAlmostEqual(
            summary["sediment_transport_total_input_m"],
            sum(history["total_sediment_input_m"] for history in world["sediment_transport_histories"]),
            delta=max(0.001, summary["sediment_transport_total_input_m"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["sediment_transport_total_deposition_m"],
            sum(history["total_deposition_m"] for history in world["sediment_transport_histories"]),
            delta=max(0.001, summary["sediment_transport_total_deposition_m"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["sediment_transport_total_export_m"],
            sum(history["total_export_m"] for history in world["sediment_transport_histories"]),
            delta=max(0.001, summary["sediment_transport_total_export_m"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["sediment_transport_total_compaction_m"],
            sum(history["total_compaction_loss_m"] for history in world["sediment_transport_histories"]),
            delta=max(0.001, summary["sediment_transport_total_compaction_m"] * 0.0001),
        )
        self.assertGreaterEqual(summary["sediment_transport_mean_final_fill_fraction"], 0.0)
        self.assertLessEqual(summary["sediment_transport_mean_final_fill_fraction"], 2.5)
        self.assertGreaterEqual(summary["sediment_transport_max_progradation_distance_km"], 0.0)
        self.assertEqual(summary["sediment_routing_history_count"], len(world["sediment_routing_histories"]))
        self.assertEqual(
            summary["sediment_routing_step_count"],
            sum(history["time_step_count"] for history in world["sediment_routing_histories"]),
        )
        self.assertEqual(
            summary["sediment_routing_cell_count"],
            sum(1 for cell in world["cells"] if cell["sediment_routing_path_count"] > 0),
        )
        self.assertAlmostEqual(
            summary["sediment_routing_total_local_supply_m"],
            sum(history["total_local_supply_m"] for history in world["sediment_routing_histories"]),
            delta=max(0.001, summary["sediment_routing_total_local_supply_m"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["sediment_routing_total_deposition_m"],
            sum(history["total_deposition_m"] for history in world["sediment_routing_histories"]),
            delta=max(0.001, summary["sediment_routing_total_deposition_m"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["sediment_routing_total_export_m"],
            sum(history["total_routed_export_m"] for history in world["sediment_routing_histories"]),
            delta=max(0.001, summary["sediment_routing_total_export_m"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["sediment_routing_total_sink_loss_m"],
            sum(history["total_sink_loss_m"] for history in world["sediment_routing_histories"]),
            delta=max(0.001, summary["sediment_routing_total_sink_loss_m"] * 0.0001),
        )
        self.assertGreaterEqual(summary["sediment_routing_total_path_length_km"], 0.0)
        self.assertGreaterEqual(summary["sediment_routing_mean_path_length_km"], 0.0)
        self.assertGreaterEqual(summary["sediment_routing_max_final_load_m"], 0.0)
        self.assertGreaterEqual(summary["sediment_routing_max_delivery_ratio"], 0.0)
        self.assertLessEqual(summary["sediment_routing_max_delivery_ratio"], 1.0)
        self.assertEqual(summary["stratigraphic_column_count"], len(world["stratigraphic_columns"]))
        self.assertIn("stratigraphic_layer_count", summary)
        self.assertEqual(
            summary["stratigraphic_layer_count"],
            sum(column["layer_count"] for column in world["stratigraphic_columns"]),
        )
        self.assertIn("active_stratigraphic_column_count", summary)
        self.assertEqual(
            summary["active_stratigraphic_column_count"],
            sum(1 for column in world["stratigraphic_columns"] if column["is_active"]),
        )
        self.assertIn("max_stratigraphic_layer_count", summary)
        self.assertIn("mean_stratigraphic_thickness_m", summary)
        self.assertEqual(summary["sequence_stratigraphy_history_count"], len(world["sequence_stratigraphy_histories"]))
        self.assertEqual(len(world["sequence_stratigraphy_histories"]), len(world["stratigraphic_columns"]))
        self.assertEqual(
            summary["sequence_stratigraphy_step_count"],
            sum(history["time_step_count"] for history in world["sequence_stratigraphy_histories"]),
        )
        self.assertEqual(
            summary["sequence_stratigraphy_event_count"],
            sum(history["sequence_event_count"] for history in world["sequence_stratigraphy_histories"]),
        )
        self.assertEqual(
            summary["sequence_boundary_count"],
            sum(history["sequence_boundary_count"] for history in world["sequence_stratigraphy_histories"]),
        )
        self.assertEqual(
            summary["transgressive_surface_count"],
            sum(history["transgressive_surface_count"] for history in world["sequence_stratigraphy_histories"]),
        )
        self.assertEqual(
            summary["maximum_flooding_surface_count"],
            sum(history["maximum_flooding_surface_count"] for history in world["sequence_stratigraphy_histories"]),
        )
        self.assertEqual(
            summary["regressive_surface_count"],
            sum(history["regressive_surface_count"] for history in world["sequence_stratigraphy_histories"]),
        )
        self.assertGreaterEqual(summary["mean_sequence_accommodation_to_deposition_ratio"], 0.0)
        self.assertGreaterEqual(summary["mean_sequence_flooding_index"], 0.0)
        self.assertLessEqual(summary["mean_sequence_flooding_index"], 1.0)
        self.assertEqual(
            sum(summary["systems_tract_counts"].values()),
            summary["sequence_stratigraphy_step_count"],
        )
        self.assertEqual(
            sum(summary["shoreline_trajectory_counts"].values()),
            summary["sequence_stratigraphy_step_count"],
        )
        self.assertIn("spill_corrected_cell_count", summary)
        self.assertIn("closed_basin_cell_count", summary)
        self.assertIn("max_depression_depth_m", summary)
        self.assertIn("water_body_counts", summary)
    def test_sedimentary_resource_systems(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        sedimentary_resource_type_counts: dict[str, int] = {}
        for system in world["sedimentary_resource_systems"]:
            sedimentary_resource_type_counts[system["system_type"]] = (
                sedimentary_resource_type_counts.get(system["system_type"], 0) + 1
            )
        self.assertEqual(summary["sedimentary_resource_system_count"], len(world["sedimentary_resource_systems"]))
        self.assertEqual(
            summary["sedimentary_resource_system_type_counts"],
            dict(sorted(sedimentary_resource_type_counts.items())),
        )
        self.assertEqual(
            sum(summary["sedimentary_resource_system_type_counts"].values()),
            summary["sedimentary_resource_system_count"],
        )
        self.assertEqual(summary["petroleum_system_count"], sedimentary_resource_type_counts.get("petroleum_system", 0))
        self.assertEqual(summary["coal_system_count"], sedimentary_resource_type_counts.get("coal_basin", 0))
        self.assertEqual(summary["gas_system_count"], sedimentary_resource_type_counts.get("gas_system", 0))
        self.assertEqual(
            summary["evaporite_salt_system_count"],
            sedimentary_resource_type_counts.get("evaporite_salt_system", 0),
        )
        self.assertEqual(
            summary["sedimentary_resource_system_cell_count"],
            len({cell_id for system in world["sedimentary_resource_systems"] for cell_id in system["cell_ids"]}),
        )
        self.assertAlmostEqual(
            summary["sedimentary_resource_system_total_area_km2"],
            sum(system["area_km2"] for system in world["sedimentary_resource_systems"]),
            delta=max(0.001, summary["sedimentary_resource_system_total_area_km2"] * 0.0001),
        )
        for key in (
            "mean_petroleum_potential_index",
            "mean_gas_potential_index",
            "mean_coal_potential_index",
            "mean_evaporite_salt_potential_index",
            "mean_sedimentary_resource_confidence_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        if world["sedimentary_resource_systems"]:
            self.assertAlmostEqual(
                summary["mean_petroleum_potential_index"],
                sum(system["petroleum_potential_index"] for system in world["sedimentary_resource_systems"])
                / len(world["sedimentary_resource_systems"]),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["mean_sedimentary_resource_confidence_index"],
                sum(system["system_confidence_index"] for system in world["sedimentary_resource_systems"])
                / len(world["sedimentary_resource_systems"]),
                delta=0.001,
            )
        petroleum_migration_type_counts: dict[str, int] = {}
    def test_fluvial_sediment_routing_provenance(self) -> None:
        routed_config = worlds.canonical_config("routed_512")
        world = worlds.cached_world("routed_512")

        model = world["fluvial_sediment_routing_model"]
        history = world["fluvial_sediment_routing_history"]
        cells = world["cells"]
        self.assertEqual(
            model["model_type"],
            "topological_capacity_limited_fluvial_sediment_routing_v1",
        )
        self.assertTrue(model["mass_conserving"])
        self.assertFalse(model["grain_size_resolved"])
        self.assertEqual(len(history), routed_config.erosion.iterations)
        self.assertGreater(model["total_routed_edge_count"], 0)
        self.assertGreater(model["total_terminal_allocation_count"], 0)
        for stage in history:
            self.assertAlmostEqual(
                stage["local_source_volume_km3"],
                stage["total_deposition_volume_km3"]
                + stage["terminal_export_volume_km3"],
                delta=max(0.000001, stage["local_source_volume_km3"] * 1.0e-10),
            )
            self.assertLessEqual(
                stage["mass_balance_residual_km3"],
                max(0.000001, stage["local_source_volume_km3"] * 1.0e-10),
            )

        def depth_volume(field: str) -> float:
            return sum(
                cell[field] * cell["area_km2"] / 1000.0 for cell in cells
            )

        self.assertAlmostEqual(
            depth_volume("fluvial_sediment_local_source_m"),
            model["total_local_source_volume_km3"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            depth_volume("fluvial_sediment_routed_incoming_m"),
            depth_volume("fluvial_sediment_routed_outgoing_m"),
            delta=0.001,
        )
        self.assertAlmostEqual(
            depth_volume("fluvial_sediment_routed_outgoing_m"),
            model["total_routed_throughput_volume_km3"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            depth_volume("fluvial_sediment_terminal_land_deposition_m"),
            model["total_terminal_land_deposition_volume_km3"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            depth_volume("fluvial_sediment_marine_deposition_m"),
            model["total_marine_deposition_volume_km3"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            depth_volume("fluvial_sediment_terminal_export_m"),
            model["total_terminal_export_volume_km3"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            sum(cell["fluvial_sediment_terminal_capture_volume_km3"] for cell in cells),
            model["total_terminal_land_deposition_volume_km3"],
            delta=0.001,
        )

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            model["maximum_transport_capacity_fraction"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("fluvial sediment routing metadata invalid", invalid_result.output)
            model["maximum_transport_capacity_fraction"] -= 0.01

            route_step = next(
                step
                for stage in history
                for step in stage["cell_steps"]
                if step["flow_to_cell_id"] >= 0
            )
            route_step["routed_outgoing_volume_km3"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("fluvial sediment routing stage", invalid_result.output)
            route_step["routed_outgoing_volume_km3"] -= 1.0

            allocation = next(
                allocation
                for stage in history
                for allocation in stage["terminal_allocations"]
                if allocation["total_deposition_volume_km3"] > 0.0
            )
            allocation["total_deposition_volume_km3"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("fluvial sediment routing stage", invalid_result.output)
            allocation["total_deposition_volume_km3"] -= 1.0

            routed_cell = next(
                cell
                for cell in cells
                if cell["fluvial_sediment_routed_outgoing_m"] > 0.0
            )
            routed_cell["fluvial_sediment_routed_outgoing_m"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "fluvial sediment routing cumulative cell fields invalid",
                invalid_result.output,
            )
            routed_cell["fluvial_sediment_routed_outgoing_m"] -= 1.0
    def test_hillslope_sediment_transport_provenance(self) -> None:
        routed_config = worlds.canonical_config("routed_512")
        world = worlds.cached_world("routed_512")
        repeat_world = generate_world(routed_config)

        self.assertEqual(world, repeat_world)
        model = world["hillslope_sediment_transport_model"]
        history = world["hillslope_sediment_transport_history"]
        cells = world["cells"]
        self.assertEqual(
            model["model_type"],
            "pairwise_lithology_dependent_volume_conserving_hillslope_transport_v2",
        )
        self.assertEqual(
            model["transport_graph"],
            "one_directed_transfer_per_eligible_undirected_mesh_edge_v1",
        )
        self.assertTrue(model["mass_conserving"])
        self.assertFalse(model["physical_time_resolved"])
        self.assertFalse(model["shared_boundary_geometry_resolved"])
        self.assertTrue(model["regolith_depth_resolved"])
        self.assertEqual(
            model["source_material_partition_model"],
            "available_alluvium_first_then_bedrock_erosion_v1",
        )
        self.assertEqual(
            model["erosion_stage_source_partition_order"],
            "hillslope_before_fluvial",
        )
        self.assertEqual(len(history), routed_config.erosion.iterations)
        self.assertEqual(model["stage_count"], len(history))
        self.assertGreater(model["total_transport_edge_count"], 0)
        self.assertGreater(model["total_land_to_land_edge_count"], 0)
        self.assertGreater(model["total_land_to_marine_edge_count"], 0)
        self.assertAlmostEqual(
            model["total_production_volume_km3"],
            model["total_deposition_volume_km3"],
            delta=max(
                0.000001,
                model["total_production_volume_km3"] * 1.0e-10,
            ),
        )
        self.assertAlmostEqual(
            model["total_production_volume_km3"],
            model["total_alluvium_entrainment_volume_km3"]
            + model["total_bedrock_erosion_volume_km3"],
            delta=0.01,
        )

        effective_diffusivity_by_lithology: dict[str, float] = {}
        for stage_index, stage in enumerate(history):
            self.assertEqual(stage["id"], stage_index)
            self.assertEqual(stage["feedback_stage_id"], stage_index + 1)
            self.assertEqual(stage["erosion_iteration"], stage_index + 1)
            self.assertEqual(stage["input_cell_count"], len(cells))
            self.assertEqual(
                [input_cell["cell_id"] for input_cell in stage["input_cells"]],
                list(range(len(cells))),
            )
            self.assertTrue(
                all(
                    input_cell["sediment_thickness_m"] >= 0.0
                    for input_cell in stage["input_cells"]
                )
            )
            self.assertEqual(stage["transport_edge_count"], len(stage["edges"]))
            self.assertAlmostEqual(
                stage["production_volume_km3"],
                stage["deposition_volume_km3"],
                delta=max(
                    0.000001,
                    stage["production_volume_km3"] * 1.0e-10,
                ),
            )
            self.assertLessEqual(
                stage["mass_balance_residual_km3"],
                max(0.000001, stage["production_volume_km3"] * 1.0e-10),
            )
            self.assertAlmostEqual(
                stage["production_volume_km3"],
                stage["alluvium_entrainment_volume_km3"]
                + stage["bedrock_erosion_volume_km3"],
                delta=0.01,
            )
            for edge in stage["edges"]:
                self.assertLess(
                    edge["mesh_edge_cell_a_id"], edge["mesh_edge_cell_b_id"]
                )
                self.assertFalse(edge["source_is_water"])
                resistance = model["source_lithology_resistance"][
                    edge["source_lithology"]
                ]
                expected_diffusivity = min(
                    model["maximum_effective_diffusivity"],
                    model["configured_hillslope_diffusivity"] / resistance,
                )
                self.assertAlmostEqual(
                    edge["effective_diffusivity"],
                    expected_diffusivity,
                    delta=0.000000001,
                )
                effective_diffusivity_by_lithology[
                    edge["source_lithology"]
                ] = edge["effective_diffusivity"]
        self.assertGreater(len(effective_diffusivity_by_lithology), 1)
        self.assertGreater(
            len(
                {
                    round(value, 10)
                    for value in effective_diffusivity_by_lithology.values()
                }
            ),
            1,
        )

        production_volume_km3 = sum(
            cell["hillslope_sediment_production_m"]
            * cell["area_km2"]
            / 1000.0
            for cell in cells
        )
        deposition_volume_km3 = sum(
            cell["hillslope_sediment_deposition_m"]
            * cell["area_km2"]
            / 1000.0
            for cell in cells
        )
        self.assertAlmostEqual(
            production_volume_km3,
            model["total_production_volume_km3"],
            delta=max(0.01, model["total_production_volume_km3"] * 1.0e-10),
        )
        self.assertAlmostEqual(
            deposition_volume_km3,
            model["total_deposition_volume_km3"],
            delta=max(0.01, model["total_deposition_volume_km3"] * 1.0e-10),
        )
        for cell in cells:
            self.assertAlmostEqual(
                cell["hillslope_sediment_net_m"],
                cell["hillslope_sediment_deposition_m"]
                - cell["hillslope_sediment_production_m"],
                delta=0.000001,
            )

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            edge = history[0]["edges"][0]
            edge["transfer_volume_km3"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hillslope sediment transport edge replay invalid",
                invalid_result.output,
            )
            edge["transfer_volume_km3"] -= 1.0

            edge["effective_diffusivity"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hillslope sediment transport edge replay invalid",
                invalid_result.output,
            )
            edge["effective_diffusivity"] -= 0.01

            removed_edge = history[0]["edges"].pop()
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hillslope sediment transport edge coverage invalid",
                invalid_result.output,
            )
            history[0]["edges"].append(removed_edge)

            source_cell = next(
                cell
                for cell in cells
                if cell["hillslope_sediment_production_m"] > 0.0
            )
            source_cell["hillslope_sediment_production_m"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hillslope sediment transport cumulative cell fields invalid",
                invalid_result.output,
            )
            source_cell["hillslope_sediment_production_m"] -= 1.0
    def test_finite_sediment_inventory_replay_and_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["run"]["seed"] = 20260711
        data["mesh"]["cell_count"] = 512
        inventory_config = type(config).model_validate(data)
        world = generate_world(inventory_config)
        model = world["sediment_inventory_model"]
        summary = world["summary"]
        cells = world["cells"]

        self.assertEqual(
            model["model_type"],
            "finite_alluvium_bedrock_sediment_inventory_v1",
        )
        self.assertEqual(
            model["initial_mobile_sediment_inventory"],
            "zero_depth_all_cells_v1",
        )
        self.assertEqual(
            model["erosion_stage_source_partition_order"],
            "hillslope_then_fluvial",
        )
        self.assertFalse(model["same_stage_deposition_available_for_entrainment"])
        self.assertEqual(
            model["mass_conserving_semantics"],
            "bulk_reference_volume_only_not_dry_rock_mass",
        )
        for unresolved_field in (
            "dry_rock_mass_resolved",
            "sediment_density_resolved",
            "porosity_resolved",
            "compaction_resolved",
            "grain_provenance_resolved",
            "chemical_weathering_resolved",
        ):
            self.assertFalse(model[unresolved_field])
        self.assertAlmostEqual(
            model["gross_mobilization_volume_km3"],
            model["alluvium_entrainment_volume_km3"]
            + model["bedrock_erosion_volume_km3"],
            delta=0.1,
        )
        self.assertAlmostEqual(
            model["gross_mobilization_volume_km3"],
            model["deposition_volume_km3"]
            + model["terminal_export_volume_km3"],
            delta=0.1,
        )
        self.assertAlmostEqual(
            model["bedrock_erosion_volume_km3"],
            model["final_mobile_sediment_inventory_volume_km3"]
            + model["terminal_export_volume_km3"],
            delta=0.1,
        )
        self.assertLess(model["source_partition_residual_km3"], 0.1)
        self.assertLess(model["inventory_mass_balance_residual_km3"], 0.1)
        self.assertAlmostEqual(
            summary["sediment_final_inventory_volume_km3"],
            sum(
                cell["sediment_thickness_m"] * cell["area_km2"] / 1000.0
                for cell in cells
            ),
            delta=30.0,
        )
        self.assertAlmostEqual(
            summary["sediment_alluvium_entrainment_volume_km3"],
            sum(
                cell["sediment_alluvium_entrainment_m"]
                * cell["area_km2"]
                / 1000.0
                for cell in cells
            ),
            delta=0.1,
        )
        self.assertAlmostEqual(
            summary["sediment_bedrock_erosion_volume_km3"],
            sum(
                cell["sediment_bedrock_erosion_m"]
                * cell["area_km2"]
                / 1000.0
                for cell in cells
            ),
            delta=0.1,
        )
        partition_gross_volume_km3 = sum(
            (
                cell["sediment_alluvium_entrainment_m"]
                + cell["sediment_bedrock_erosion_m"]
            )
            * cell["area_km2"]
            / 1000.0
            for cell in cells
        )
        self.assertAlmostEqual(
            summary["sediment_gross_mobilization_volume_km3"],
            partition_gross_volume_km3,
            delta=0.1,
        )
        self.assertAlmostEqual(
            summary["sediment_budget_production_km3"],
            partition_gross_volume_km3,
            delta=0.1,
        )
        cell_depth_output_tolerance_m = (
            1.0001 * 10.0 ** (-int(summary["output_float_precision"]))
        )
        for cell in cells:
            self.assertNotIn("sediment_production_m", cell)
            partition_gross_depth_m = (
                cell["sediment_alluvium_entrainment_m"]
                + cell["sediment_bedrock_erosion_m"]
            )
            independent_process_gross_depth_m = (
                cell["hillslope_sediment_production_m"]
                + cell["fluvial_sediment_local_source_m"]
                + cell["glacial_sediment_production_m"]
                + cell["cumulative_numeric_depression_breach_excavation_m"]
            )
            self.assertAlmostEqual(
                partition_gross_depth_m,
                independent_process_gross_depth_m,
                delta=1.0e-7,
            )
            self.assertAlmostEqual(
                cell["sediment_net_budget_m"],
                cell["sediment_deposition_m"] - partition_gross_depth_m,
                delta=cell_depth_output_tolerance_m,
            )
        process_partition = model["process_source_partition"]
        self.assertEqual(
            set(process_partition),
            {"hillslope", "fluvial", "glacial", "numeric_breach"},
        )
        for process in process_partition.values():
            self.assertAlmostEqual(
                process["gross_mobilization_volume_km3"],
                process["alluvium_entrainment_volume_km3"]
                + process["bedrock_erosion_volume_km3"],
                delta=0.1,
            )
        final_feedback = world["earth_system_feedback_history"][-1]
        self.assertAlmostEqual(
            final_feedback["sediment_inventory_volume_km3"],
            model["final_mobile_sediment_inventory_volume_km3"],
            delta=0.1,
        )

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            interface_result = validate_sediment_interfaces(world)
            self.assertTrue(
                interface_result["passed"], interface_result["failures"]
            )
            selected_breach = next(
                event
                for event in world["numeric_depression_correction_history"]
                if event["selected_correction_method"]
                == "mass_conserving_breach"
            )
            excavation_index = next(
                index
                for index, depth_m in enumerate(
                    selected_breach["breach_excavation_depth_m_by_cell"]
                )
                if depth_m > 1.0e-9
            )
            excavation_depths = selected_breach[
                "breach_excavation_depth_m_by_cell"
            ]
            original_excavation_depth_m = excavation_depths[excavation_index]
            try:
                excavation_depths[excavation_index] += 1.0
                altered_interface_result = validate_sediment_interfaces(world)
                self.assertFalse(altered_interface_result["passed"])
                self.assertTrue(altered_interface_result["failures"])
                self.assertIn(
                    "numeric breach excavation geometry is invalid",
                    "\n".join(altered_interface_result["failures"]),
                )
            finally:
                excavation_depths[excavation_index] = original_excavation_depth_m

            deposition_depths = selected_breach[
                "breach_deposition_depth_m_by_cell"
            ]
            self.assertTrue(deposition_depths)
            original_deposition_depth_m = deposition_depths[0]
            try:
                deposition_depths[0] += 1.0
                altered_interface_result = validate_sediment_interfaces(world)
                self.assertFalse(altered_interface_result["passed"])
                self.assertIn(
                    "numeric breach deposition depth is invalid",
                    "\n".join(altered_interface_result["failures"]),
                )
            finally:
                deposition_depths[0] = original_deposition_depth_m

            allocation_stage = next(
                stage
                for stage in world["fluvial_sediment_routing_history"]
                if stage["terminal_allocations"]
            )
            allocation = allocation_stage["terminal_allocations"][0]
            original_target_id = allocation["target_cell_id"]
            original_target_area_km2 = allocation["target_area_km2"]
            replacement_target_id = (original_target_id + 1) % len(cells)
            try:
                allocation["target_cell_id"] = replacement_target_id
                allocation["target_area_km2"] = cells[replacement_target_id][
                    "area_km2"
                ]
                altered_interface_result = validate_sediment_interfaces(world)
                self.assertFalse(altered_interface_result["passed"])
                self.assertTrue(altered_interface_result["failures"])
            finally:
                allocation["target_cell_id"] = original_target_id
                allocation["target_area_km2"] = original_target_area_km2

            hillslope_input = world["hillslope_sediment_transport_history"][1][
                "input_cells"
            ][0]
            hillslope_input["sediment_thickness_m"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("inventory snapshot replay invalid", invalid_result.output)
            hillslope_input["sediment_thickness_m"] -= 1.0

            hillslope_stage = world["hillslope_sediment_transport_history"][0]
            hillslope_stage["alluvium_entrainment_volume_km3"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("hillslope source partition invalid", invalid_result.output)
            hillslope_stage["alluvium_entrainment_volume_km3"] -= 1.0

            numeric_event = next(
                event
                for event in world["numeric_depression_correction_history"]
                if event["breach_path_cell_ids"]
            )
            numeric_event[
                "breach_alluvium_entrainment_depth_m_by_cell"
            ][0] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("numeric breach source partition invalid", invalid_result.output)
            numeric_event[
                "breach_alluvium_entrainment_depth_m_by_cell"
            ][0] -= 1.0

            source_cell = next(
                cell
                for cell in cells
                if cell["sediment_alluvium_entrainment_m"] > 0.0
            )
            source_cell["sediment_alluvium_entrainment_m"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("cumulative cell fields invalid", invalid_result.output)
            source_cell["sediment_alluvium_entrainment_m"] -= 1.0

            inventory_cell = next(
                cell for cell in cells if cell["sediment_thickness_m"] > 0.0
            )
            inventory_cell["sediment_thickness_m"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("cumulative cell fields invalid", invalid_result.output)
            inventory_cell["sediment_thickness_m"] -= 1.0

            interface_cell = cells[0]
            interface_cell["bedrock_surface_elevation_m"] += 1.0
            interface_cell["elevation_m"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("sediment interface replay invalid", invalid_result.output)
            interface_cell["bedrock_surface_elevation_m"] -= 1.0
            interface_cell["elevation_m"] -= 1.0

            model["inventory_mass_balance_residual_km3"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("model aggregates invalid", invalid_result.output)
            model["inventory_mass_balance_residual_km3"] -= 1.0
