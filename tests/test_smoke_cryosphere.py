"""Ice sheets, glaciers, and permafrost assertions for the generated world.

Split out of the former single-method smoke test: each method re-derives
what it needs from the shared world, so they no longer depend on order.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from click.testing import Result
from typer.testing import CliRunner

from magic_geo.cli import app

from support import cryosphere_worlds, worlds
from support.cli import assert_no_cli_crash


class SmokeCryosphereTests(TestCase):
    def test_ice_sheets(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertEqual(summary["ice_sheet_count"], len(world["ice_sheets"]))
        self.assertIn("mean_ice_sheet_retreat_rate_m_y", summary)
        self.assertGreaterEqual(summary["mean_ice_sheet_retreat_rate_m_y"], 0.0)
        permafrost_cells = [cell for cell in world["cells"] if cell["permafrost_extent_index"] >= 0.45]
        self.assertEqual(summary["permafrost_cell_count"], len(permafrost_cells))
        self.assertEqual(summary["permafrost_region_count"], len(world["permafrost_regions"]))
        self.assertEqual(sum(summary["permafrost_class_counts"].values()), summary["cell_count"])
        self.assertEqual(
            summary["continuous_permafrost_cell_count"],
            sum(1 for cell in world["cells"] if cell["permafrost_class"] == "continuous_permafrost"),
        )
        self.assertEqual(
            summary["ice_cemented_permafrost_cell_count"],
            sum(1 for cell in world["cells"] if cell["permafrost_class"] == "ice_cemented_permafrost"),
        )
        self.assertGreaterEqual(summary["mean_permafrost_extent_index"], 0.0)
        self.assertLessEqual(summary["mean_permafrost_extent_index"], 1.0)
        self.assertGreaterEqual(summary["mean_active_layer_depth_m"], 0.0)
        self.assertLessEqual(summary["mean_active_layer_depth_m"], 4.5)
        self.assertGreaterEqual(summary["mean_ground_ice_content_index"], 0.0)
        self.assertLessEqual(summary["mean_ground_ice_content_index"], 1.0)
        self.assertEqual(
            {cell_id for region in world["permafrost_regions"] for cell_id in region["cell_ids"]},
            {cell["id"] for cell in permafrost_cells},
        )
        self.assertEqual(summary["ice_sheet_history_count"], len(world["ice_sheet_histories"]))
        self.assertEqual(len(world["ice_sheet_histories"]), len(world["ice_sheets"]))
        self.assertEqual(
            summary["ice_sheet_history_step_count"],
            sum(history["time_step_count"] for history in world["ice_sheet_histories"]),
        )
        self.assertAlmostEqual(
            summary["ice_sheet_history_final_volume_km3"],
            sum(history["final_volume_km3"] for history in world["ice_sheet_histories"]),
            delta=max(1.0, summary["ice_sheet_history_final_volume_km3"] * 0.0001),
        )
        self.assertGreaterEqual(summary["ice_sheet_history_peak_volume_km3"], 0.0)
        self.assertGreaterEqual(summary["ice_sheet_history_final_volume_km3"], 0.0)
        self.assertEqual(summary["ice_sheet_stability_history_count"], len(world["ice_sheet_stability_histories"]))
        self.assertEqual(len(world["ice_sheet_stability_histories"]), len(world["ice_sheets"]))
        self.assertEqual(
            summary["ice_sheet_stability_step_count"],
            sum(history["time_step_count"] for history in world["ice_sheet_stability_histories"]),
        )
        self.assertEqual(
            summary["ice_sheet_retreat_threshold_event_count"],
            sum(history["retreat_threshold_event_count"] for history in world["ice_sheet_stability_histories"]),
        )
        self.assertEqual(
            summary["high_ice_sheet_instability_count"],
            sum(1 for history in world["ice_sheet_stability_histories"] if history["max_stability_index"] >= 0.65),
        )
        self.assertGreaterEqual(summary["mean_ice_sheet_stability_index"], 0.0)
        self.assertLessEqual(summary["mean_ice_sheet_stability_index"], 1.0)
        self.assertGreaterEqual(summary["max_ice_sheet_stability_index"], 0.0)
        self.assertLessEqual(summary["max_ice_sheet_stability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_calving_susceptibility_index"], 0.0)
        self.assertLessEqual(summary["mean_calving_susceptibility_index"], 1.0)
        self.assertGreaterEqual(summary["mean_grounding_line_instability_index"], 0.0)
        self.assertLessEqual(summary["mean_grounding_line_instability_index"], 1.0)
        self.assertAlmostEqual(
            summary["ice_sheet_total_projected_calving_loss_km3"],
            sum(history["total_projected_calving_loss_km3"] for history in world["ice_sheet_stability_histories"]),
            delta=max(0.001, summary["ice_sheet_total_projected_calving_loss_km3"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["ice_sheet_total_projected_grounding_line_retreat_km"],
            sum(history["total_projected_grounding_line_retreat_km"] for history in world["ice_sheet_stability_histories"]),
            delta=max(0.001, summary["ice_sheet_total_projected_grounding_line_retreat_km"] * 0.0001),
        )
        self.assertEqual(sum(summary["ice_sheet_stability_class_counts"].values()), len(world["ice_sheets"]))
        self.assertEqual(summary["ice_flowline_history_count"], len(world["ice_flowline_histories"]))
        self.assertEqual(
            summary["ice_flowline_step_count"],
            sum(history["time_step_count"] for history in world["ice_flowline_histories"]),
        )
        self.assertEqual(
            summary["ice_flowline_cell_count"],
            sum(1 for cell in world["cells"] if cell["ice_flowline_path_count"] > 0),
        )
        self.assertAlmostEqual(
            summary["ice_flowline_total_dynamic_flux_km3_y"],
            sum(history["total_dynamic_flux_km3_y"] for history in world["ice_flowline_histories"]),
            delta=max(0.001, summary["ice_flowline_total_dynamic_flux_km3_y"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["ice_flowline_total_dynamic_loss_km3_y"],
            sum(history["total_dynamic_loss_km3_y"] for history in world["ice_flowline_histories"]),
            delta=max(0.001, summary["ice_flowline_total_dynamic_loss_km3_y"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["ice_flowline_total_melt_loss_km3_y"],
            sum(history["total_melt_loss_km3_y"] for history in world["ice_flowline_histories"]),
            delta=max(0.001, summary["ice_flowline_total_melt_loss_km3_y"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["ice_flowline_total_glacial_erosion_m"],
            sum(history["total_glacial_erosion_m"] for history in world["ice_flowline_histories"]),
            delta=max(0.001, summary["ice_flowline_total_glacial_erosion_m"] * 0.0001),
        )
        flowline_path_total = sum(history["path_length_km"] for history in world["ice_flowline_histories"])
        self.assertAlmostEqual(
            summary["ice_flowline_total_path_length_km"],
            flowline_path_total,
            delta=max(0.001, summary["ice_flowline_total_path_length_km"] * 0.0001),
        )
        expected_flowline_mean = flowline_path_total / len(world["ice_flowline_histories"]) if world["ice_flowline_histories"] else 0.0
        self.assertAlmostEqual(
            summary["ice_flowline_mean_path_length_km"],
            expected_flowline_mean,
            delta=max(0.001, expected_flowline_mean * 0.0001),
        )
        self.assertGreaterEqual(summary["ice_flowline_max_driving_stress_kpa"], 0.0)
        self.assertGreaterEqual(summary["ice_flowline_max_final_flux_km3_y"], 0.0)
        self.assertGreaterEqual(summary["ice_flowline_max_strain_heating_index"], 0.0)
        self.assertLessEqual(summary["ice_flowline_max_strain_heating_index"], 1.0)
        self.assertIn("moraine_deposition_cell_count", summary)
        self.assertEqual(
            summary["moraine_deposition_cell_count"],
            sum(1 for cell in world["cells"] if cell["moraine_deposition_m"] > 0.0),
        )
        self.assertIn("mean_moraine_deposition_m", summary)
        self.assertIn("mean_deglaciation_age_ka", summary)
        glacial_landform_cells = [cell for cell in world["cells"] if cell["glacial_landform_type"] != "none"]
        self.assertEqual(summary["glacial_landform_cell_count"], len(glacial_landform_cells))
        self.assertEqual(summary["glacial_landform_system_count"], len(world["glacial_landform_systems"]))
        self.assertAlmostEqual(
            summary["glacial_landform_area_km2"],
            sum(cell["area_km2"] for cell in glacial_landform_cells),
            delta=max(0.001, summary["glacial_landform_area_km2"] * 0.0001),
        )
        self.assertEqual(sum(summary["glacial_landform_type_counts"].values()), summary["cell_count"])
        self.assertEqual(
            summary["ice_cap_landform_cell_count"],
            sum(1 for cell in world["cells"] if cell["glacial_landform_type"] == "ice_cap"),
        )
        self.assertEqual(
            summary["mountain_glacier_landform_cell_count"],
            sum(1 for cell in world["cells"] if cell["glacial_landform_type"] == "mountain_glacier"),
        )
        self.assertEqual(
            summary["fjord_landform_cell_count"],
            sum(1 for cell in world["cells"] if cell["glacial_landform_type"] == "fjord"),
        )
        self.assertEqual(
            summary["glacial_valley_landform_cell_count"],
            sum(1 for cell in world["cells"] if cell["glacial_landform_type"] == "glacial_valley"),
        )
        self.assertEqual(
            summary["glacial_lake_landform_cell_count"],
            sum(1 for cell in world["cells"] if cell["glacial_landform_type"] == "glacial_lake"),
        )
        self.assertEqual(
            summary["moraine_landform_cell_count"],
            sum(1 for cell in world["cells"] if cell["glacial_landform_type"] == "moraine"),
        )
        for key in (
            "mean_glacial_landform_index",
            "mean_glacial_erosion_intensity_index",
            "mean_glacial_deposition_index",
            "mean_glacial_meltwater_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
    def test_glacial_sediment_transport_provenance_and_terrain_coupling(self) -> None:
        # Positive ice transport needs the shipped cold forcing. The ordinary
        # Earthlike coupled witness is now warm under the seasonal energy model.
        world = cryosphere_worlds.cached_cold_world("full_world")

        model = world["glacial_sediment_transport_model"]
        history = world["glacial_sediment_transport_history"]
        cells = world["cells"]
        self.assertEqual(
            model["model_type"],
            "downhill_area_conserving_glacial_sediment_transport_v3",
        )
        self.assertEqual(model["source_grounded_ice_model"], "exposed_land_annual_grounded_ice_diagnostic_v1")
        self.assertEqual(
            model["routing_graph"],
            "single_steepest_downhill_mesh_neighbor_v1",
        )
        self.assertEqual(model["mobile_sediment_fraction"], 0.28)
        self.assertTrue(model["mass_conserving"])
        self.assertTrue(model["finite_sediment_inventory_resolved"])
        self.assertEqual(
            model["source_material_partition_model"],
            "available_alluvium_first_then_bedrock_erosion_v1",
        )
        self.assertTrue(model["terrain_elevation_coupled"])
        self.assertTrue(model["earth_system_recomputed_after_transport"])
        self.assertFalse(model["physical_time_resolved"])
        self.assertFalse(model["multi_step_ice_dynamics_resolved"])
        self.assertEqual(len(history), 1)

        stage = history[0]
        self.assertEqual(stage["id"], 0)
        self.assertEqual(world["simulation_clock"]["configured_erosion_iteration_count"], 0)
        self.assertEqual(stage["feedback_stage_id"], 1)
        self.assertEqual(stage["input_cell_count"], len(cells))
        self.assertEqual(stage["transfer_count"], len(stage["transfers"]))
        self.assertGreater(stage["transfer_count"], 0)
        self.assertAlmostEqual(
            stage["production_volume_km3"],
            stage["alluvium_entrainment_volume_km3"]
            + stage["bedrock_erosion_volume_km3"],
            delta=0.01,
        )
        self.assertEqual(
            [input_cell["cell_id"] for input_cell in stage["input_cells"]],
            list(range(len(cells))),
        )
        input_by_id = {
            input_cell["cell_id"]: input_cell for input_cell in stage["input_cells"]
        }
        production_depth_by_cell = [0.0] * len(cells)
        deposition_depth_by_cell = [0.0] * len(cells)
        production_volume_km3 = 0.0
        deposition_volume_km3 = 0.0
        for transfer_id, transfer in enumerate(stage["transfers"]):
            source_id = transfer["source_cell_id"]
            target_id = transfer["target_cell_id"]
            source = input_by_id[source_id]
            target = input_by_id[target_id]
            self.assertEqual(transfer["id"], transfer_id)
            self.assertIn(target_id, cells[source_id]["neighbors"])
            self.assertEqual(source["glacier_flow_to_cell_id"], target_id)
            self.assertGreater(source["elevation_m"], target["elevation_m"])
            expected_source_depth_m = source["glacial_erosion_m"] * 0.28
            expected_volume_km3 = (
                expected_source_depth_m * cells[source_id]["area_km2"] / 1000.0
            )
            expected_target_depth_m = (
                expected_volume_km3 * 1000.0 / cells[target_id]["area_km2"]
            )
            self.assertAlmostEqual(
                transfer["source_production_depth_m"],
                expected_source_depth_m,
                delta=0.000001,
            )
            self.assertAlmostEqual(
                transfer["target_deposition_depth_m"],
                expected_target_depth_m,
                delta=0.000001,
            )
            self.assertAlmostEqual(
                transfer["transfer_volume_km3"],
                expected_volume_km3,
                delta=max(0.00001, expected_volume_km3 * 2.0e-7),
            )
            production_depth_by_cell[source_id] += expected_source_depth_m
            deposition_depth_by_cell[target_id] += expected_target_depth_m
            production_volume_km3 += expected_volume_km3
            deposition_volume_km3 += (
                expected_target_depth_m * cells[target_id]["area_km2"] / 1000.0
            )

        self.assertAlmostEqual(
            production_volume_km3,
            deposition_volume_km3,
            delta=max(0.000001, production_volume_km3 * 1.0e-10),
        )
        self.assertAlmostEqual(
            stage["production_volume_km3"],
            production_volume_km3,
            delta=max(0.000001, production_volume_km3 * 1.0e-9),
        )
        changed_cell_count = 0
        for cell_id, cell in enumerate(cells):
            expected_post_elevation_m = (
                input_by_id[cell_id]["elevation_m"]
                - production_depth_by_cell[cell_id]
                + deposition_depth_by_cell[cell_id]
            )
            self.assertAlmostEqual(
                stage["post_transport_elevation_m_by_cell"][cell_id],
                expected_post_elevation_m,
                delta=0.000001,
            )
            changed_cell_count += int(
                abs(expected_post_elevation_m - input_by_id[cell_id]["elevation_m"])
                > 0.000001
            )
            self.assertAlmostEqual(
                cell["glacial_sediment_production_m"],
                production_depth_by_cell[cell_id],
                delta=0.000001,
            )
            self.assertAlmostEqual(
                cell["glacial_sediment_deposition_m"],
                deposition_depth_by_cell[cell_id],
                delta=0.000001,
            )
            self.assertAlmostEqual(
                cell["glacial_sediment_net_m"],
                deposition_depth_by_cell[cell_id]
                - production_depth_by_cell[cell_id],
                delta=0.000001,
            )
        self.assertGreater(changed_cell_count, 0)

        feedback = world["earth_system_feedback_history"][stage["feedback_stage_id"]]
        self.assertEqual(feedback["stage"], "cryosphere_coupling")
        self.assertTrue(feedback["cryosphere_applied"])
        self.assertFalse(feedback["erosion_applied"])
        self.assertTrue(feedback["sea_level_recomputed"])
        self.assertTrue(feedback["climate_recomputed"])
        self.assertTrue(feedback["hydrology_recomputed"])
        self.assertEqual(
            feedback["glacial_sediment_transfer_count"], stage["transfer_count"]
        )
        self.assertAlmostEqual(
            feedback["glacial_sediment_production_volume_km3"],
            stage["production_volume_km3"],
            delta=0.000001,
        )

        # Wiring only: ``validate`` has to reach and report the glacial
        # transport replay at all. Its four verdicts and their tamper tables
        # live in ``test_sediment_validators``, which calls
        # ``_validate_glacial_sediment_transport`` directly and can name the
        # field that diverged; the checks inside that validator break on the
        # first divergence, so driving all four through the command would cost
        # four more full passes to prove one wiring fact.
        runner = CliRunner()
        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"

            def validate_current() -> Result:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            control = validate_current()
            assert_no_cli_crash(self, control, command="validate")
            self.assertEqual(control.exit_code, 0, control.output)

            stage["transfers"][0]["target_deposition_depth_m"] += 1.0

            result = validate_current()

        assert_no_cli_crash(self, result, command="validate")
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn(
            "glacial sediment transport transfer replay invalid", result.output
        )
