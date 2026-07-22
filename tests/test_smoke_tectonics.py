"""Plate tectonics, crust, and faults assertions for the generated world.

Split out of the former single-method smoke test: each method re-derives
what it needs from the shared world, so they no longer depend on order.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.api import generate_world
from magic_geo.cli import app
from magic_geo.config import load_config

from support import worlds


class SmokeTectonicsTests(TestCase):
    def test_plate_motion_history(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        kinematic_model = world["plate_kinematic_model"]
        motion_history = world["plate_motion_history"]
        self.assertEqual(kinematic_model["model_type"], "rotating_voronoi_plate_domains_v3")
        self.assertFalse(kinematic_model["physical_time_resolved"])
        self.assertTrue(kinematic_model["crust_advection_resolved"])
        self.assertTrue(kinematic_model["mass_conserving_crust_transport"])
        self.assertEqual(
            kinematic_model["initial_crust_partition_model"],
            "ranked_graph_coherent_plate_biased_continental_mask_v2",
        )
        self.assertEqual(kinematic_model["continental_crust_fraction_target"], 0.34)
        self.assertEqual(kinematic_model["initial_crust_coherence_smoothing_steps"], 1)
        self.assertEqual(kinematic_model["initial_crust_coherence_self_weight"], 0.77)
        self.assertEqual(kinematic_model["secondary_relief_smoothing_steps"], 4)
        self.assertEqual(kinematic_model["secondary_relief_self_weight"], 0.58)
        self.assertEqual(
            kinematic_model["initial_relief_model"],
            "causal_isostasy_quadratic_convergence_relief_v2",
        )
        self.assertEqual(kinematic_model["convergence_relief_exponent"], 2.0)
        self.assertEqual(
            kinematic_model["transitional_crust_margin_model"],
            "one_hop_graph_margin_v1",
        )
        self.assertTrue(kinematic_model["sea_level_inventory_separate_from_crust_partition"])
        self.assertEqual(kinematic_model["history_step_count"], len(motion_history))
        self.assertEqual(len(motion_history), 3)
        initial_crust_types = motion_history[0]["crust_type_by_cell"]
        initial_continental_ids = {
            cell_id
            for cell_id, crust_type in enumerate(initial_crust_types)
            if crust_type in {1, 4, 5, 6, 7}
        }
        self.assertEqual(len(initial_continental_ids), round(0.34 * len(world["cells"])))
        self.assertEqual(
            kinematic_model["initial_continental_crust_cell_count"],
            len(initial_continental_ids),
        )
        self.assertGreaterEqual(kinematic_model["initial_continental_crust_component_count"], 1)
        self.assertGreater(
            kinematic_model["initial_continental_crust_largest_component_cell_count"],
            0,
        )
        self.assertGreater(kinematic_model["initial_continental_crust_boundary_edge_count"], 0)
        self.assertAlmostEqual(
            kinematic_model["initial_continental_crust_fraction"],
            len(initial_continental_ids) / len(world["cells"]),
            delta=0.000002,
        )
        for cell_id, crust_type in enumerate(initial_crust_types):
            if crust_type == 2:
                self.assertTrue(
                    any(
                        neighbor_id in initial_continental_ids
                        for neighbor_id in world["cells"][cell_id]["neighbors"]
                    )
                )
        self.assertEqual(
            [step["stage"] for step in motion_history],
            ["initial_plate_domains", "plate_motion_iteration", "plate_motion_iteration"],
        )
        self.assertEqual([step["erosion_iteration"] for step in motion_history], [-1, 1, 2])
        self.assertTrue(all(step["mean_plate_rotation_deg"] > 0.0 for step in motion_history[1:]))
        self.assertTrue(
            all(
                -4200.0 <= delta <= 5.0
                for step in motion_history[1:]
                for delta in step["crust_age_process_change_ma_by_cell"]
            )
        )
        self.assertTrue(
            all(
                abs(delta) <= 76.0
                for step in motion_history[1:]
                for delta in step["crust_thickness_process_change_km_by_cell"]
            )
        )
        self.assertTrue(
            all(
                -180.0 <= delta <= 220.0
                for step in motion_history[1:]
                for delta in step["bounded_dynamic_relief_change_m"]
            )
        )
        self.assertTrue(
            any(
                abs(delta) > 220.0
                for step in motion_history[1:]
                for delta in step["tectonic_elevation_change_m_by_cell"]
            )
        )
        self.assertEqual(
            motion_history[-1]["cell_plate_ids"],
            [cell["plate_id"] for cell in world["cells"]],
        )
        self.assertEqual(
            sum(step["reassigned_cell_count"] for step in motion_history[1:]),
            summary["total_plate_reassignment_event_count"],
        )
        self.assertTrue(all(step["mean_crust_transport_distance_km"] > 0.0 for step in motion_history[1:]))
    def test_plates(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertEqual(len(world["plates"]), summary["plate_count"])
        first_plate = world["plates"][0]
        first_plate_cells = [cell for cell in world["cells"] if cell["plate_id"] == first_plate["id"]]
        first_plate_area = sum(cell["area_km2"] for cell in first_plate_cells)
        lithology_area: dict[str, float] = {}
        for cell in first_plate_cells:
            lithology_area[cell["lithology"]] = lithology_area.get(cell["lithology"], 0.0) + cell["area_km2"]
        self.assertEqual(first_plate["cell_count"], len(first_plate_cells))
        self.assertEqual(len(first_plate["initial_center"]), 3)
        self.assertEqual(len(first_plate["center"]), 3)
        self.assertGreater(first_plate["cumulative_rotation_deg"], 0.0)
        self.assertAlmostEqual(first_plate["area_km2"], first_plate_area, delta=max(1.0, first_plate_area * 0.0001))
        self.assertGreater(first_plate["mean_crust_age_ma"], 0.0)
        self.assertGreater(first_plate["mean_crust_density"], 0.0)
        self.assertGreater(first_plate["mean_crust_thickness_km"], 0.0)
        self.assertAlmostEqual(
            lithology_area[first_plate["dominant_lithology"]],
            max(lithology_area.values()),
            delta=0.001,
        )
        self.assertGreaterEqual(first_plate["mean_boundary_activity"], 0.0)
        self.assertLessEqual(first_plate["mean_boundary_activity"], 1.0)
        self.assertGreaterEqual(first_plate["mean_heat_flow_mw_m2"], 18.0)
        self.assertLessEqual(first_plate["mean_heat_flow_mw_m2"], 240.0)
        self.assertIn(first_plate["thermal_state"], {"cool_stable", "warm_active", "hot_active"})
        self.assertTrue(world["cells"][0]["neighbors"])
        first_cell = world["cells"][0]
        self.assertGreater(first_cell["crust_density"], 0.0)
        relief_component_keys = [
            "initial_isostatic_elevation_m",
            "initial_ridge_uplift_m",
            "initial_orogenic_uplift_m",
            "initial_volcanic_uplift_m",
            "initial_trench_subsidence_m",
            "initial_rift_subsidence_m",
            "initial_transform_fault_relief_m",
            "initial_secondary_roughness_m",
        ]
        for key in relief_component_keys:
            self.assertIn(key, first_cell)
        initial_thermal_subsidence_m = world["plate_motion_history"][0][
            "post_process_local_thermal_subsidence_target_m"
        ][int(first_cell["id"])]
        relief_component_sum = (
            sum(first_cell[key] for key in relief_component_keys)
            + initial_thermal_subsidence_m
        )
        self.assertAlmostEqual(first_cell["initial_elevation_m"], relief_component_sum, delta=0.05)
        self.assertGreaterEqual(first_cell["tectonic_uplift_rate_m_per_step"], 0.0)
        self.assertGreaterEqual(first_cell["volcanic_potential_index"], 0.0)
        self.assertLessEqual(first_cell["volcanic_potential_index"], 1.0)
        self.assertEqual(
            summary["high_volcanic_potential_cell_count"],
            sum(1 for cell in world["cells"] if cell["volcanic_potential_index"] >= 0.65),
        )
        self.assertAlmostEqual(
            summary["mean_volcanic_potential_index"],
            sum(cell["volcanic_potential_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        first_position = first_cell["position_3d"]
        first_normal = first_cell["normal_3d"]
        self.assertEqual(len(first_position), 3)
        self.assertEqual(len(first_normal), 3)
        self.assertAlmostEqual(sum(component * component for component in first_position), 1.0, delta=0.001)
        self.assertEqual(first_position, first_normal)
        expected_x = math.cos(math.radians(first_cell["lat_deg"])) * math.cos(math.radians(first_cell["lon_deg"]))
        expected_y = math.cos(math.radians(first_cell["lat_deg"])) * math.sin(math.radians(first_cell["lon_deg"]))
        expected_z = math.sin(math.radians(first_cell["lat_deg"]))
        for actual, expected in zip(first_position, (expected_x, expected_y, expected_z)):
            self.assertAlmostEqual(actual, expected, delta=0.001)
    def test_collision_zones(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        first_cell = world["cells"][0]
        self.assertEqual(summary["collision_zone_count"], len(world["collision_zones"]))
        self.assertEqual(summary["subduction_zone_count"], len(world["subduction_zones"]))
        self.assertEqual(summary["rift_zone_count"], len(world["rift_zones"]))
        self.assertEqual(
            summary["tectonic_zone_count"],
            len(world["collision_zones"]) + len(world["subduction_zones"]) + len(world["rift_zones"]),
        )
        self.assertEqual(summary["tectonic_zone_count"], len(world["tectonic_zones"]))
        self.assertEqual(
            summary["collision_zone_cell_count"],
            sum(zone["cell_count"] for zone in world["collision_zones"]),
        )
        self.assertEqual(
            summary["subduction_zone_cell_count"],
            sum(zone["cell_count"] for zone in world["subduction_zones"]),
        )
        self.assertEqual(
            summary["rift_zone_cell_count"],
            sum(zone["cell_count"] for zone in world["rift_zones"]),
        )
        self.assertAlmostEqual(
            summary["tectonic_zone_total_area_km2"],
            sum(zone["area_km2"] for zone in world["tectonic_zones"]),
            delta=max(1.0, summary["tectonic_zone_total_area_km2"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["tectonic_zone_boundary_length_km"],
            sum(zone["boundary_length_km"] for zone in world["tectonic_zones"]),
            delta=max(0.001, summary["tectonic_zone_boundary_length_km"] * 0.0001),
        )
        self.assertEqual(summary["fault_system_count"], len(world["fault_systems"]))
        self.assertEqual(
            summary["fault_system_cell_count"],
            sum(1 for cell in world["cells"] if cell["fault_system_id"] >= 0),
        )
        self.assertGreater(summary["fault_system_count"], 0)
        self.assertGreater(summary["fault_system_total_area_km2"], 0.0)
        self.assertGreater(summary["fault_system_boundary_length_km"], 0.0)
        self.assertGreaterEqual(summary["mean_fault_slip_rate_index"], 0.0)
        self.assertLessEqual(summary["mean_fault_slip_rate_index"], 1.0)
        self.assertGreaterEqual(summary["mean_seismic_hazard_index"], 0.0)
        self.assertLessEqual(summary["mean_seismic_hazard_index"], 1.0)
        self.assertEqual(
            summary["high_seismic_hazard_cell_count"],
            sum(1 for cell in world["cells"] if cell["seismic_hazard_index"] >= 0.55),
        )
        self.assertGreaterEqual(summary["mean_earthquake_recurrence_interval_y"], 0.0)
        for key in [
            "collision_zone_id",
            "subduction_zone_id",
            "rift_zone_id",
            "dominant_tectonic_zone_type",
            "tectonic_zone_strength",
            "fault_slip_rate_index",
            "seismic_hazard_index",
            "earthquake_recurrence_interval_y",
            "fault_system_id",
        ]:
            self.assertIn(key, first_cell)
        self.assertIn(first_cell["dominant_tectonic_zone_type"], {"none", "collision", "subduction", "rift"})
        self.assertGreaterEqual(first_cell["tectonic_zone_strength"], 0.0)
        self.assertLessEqual(first_cell["tectonic_zone_strength"], 1.0)
        self.assertGreaterEqual(first_cell["fault_slip_rate_index"], 0.0)
        self.assertLessEqual(first_cell["fault_slip_rate_index"], 1.0)
        self.assertGreaterEqual(first_cell["seismic_hazard_index"], 0.0)
        self.assertLessEqual(first_cell["seismic_hazard_index"], 1.0)
        self.assertGreaterEqual(first_cell["earthquake_recurrence_interval_y"], 0.0)
        self.assertGreaterEqual(first_cell["fault_system_id"], -1)
        for zone_type, zones in [
            ("collision", world["collision_zones"]),
            ("subduction", world["subduction_zones"]),
            ("rift", world["rift_zones"]),
        ]:
            if not zones:
                continue
            zone = zones[0]
            self.assertEqual(zone["id"], 0)
            self.assertEqual(zone["zone_type"], zone_type)
            self.assertEqual(zone["cell_count"], len(zone["cell_ids"]))
            self.assertGreater(zone["area_km2"], 0.0)
            self.assertIn(zone["representative_cell_id"], zone["cell_ids"])
            self.assertGreaterEqual(zone["mean_zone_strength"], 0.0)
            self.assertLessEqual(zone["mean_zone_strength"], 1.0)
            self.assertGreaterEqual(zone["max_zone_strength"], zone["mean_zone_strength"])
            self.assertIn("formation_evidence", zone)
            self.assertEqual(zone["boundary_edge_count"], len(zone["boundary_edge_ids"]))
            for edge_id in zone["boundary_edge_ids"]:
                self.assertTrue(world["cell_adjacency_edges"][edge_id]["plate_boundary"])
        first_fault_system = world["fault_systems"][0]
        self.assertEqual(first_fault_system["id"], 0)
        self.assertEqual(first_fault_system["cell_count"], len(first_fault_system["cell_ids"]))
        self.assertGreater(first_fault_system["area_km2"], 0.0)
        self.assertIn(first_fault_system["representative_cell_id"], first_fault_system["cell_ids"])
        self.assertGreaterEqual(first_fault_system["mean_fault_slip_rate_index"], 0.0)
        self.assertLessEqual(first_fault_system["mean_fault_slip_rate_index"], 1.0)
        self.assertGreaterEqual(first_fault_system["max_fault_slip_rate_index"], first_fault_system["mean_fault_slip_rate_index"])
        self.assertGreaterEqual(first_fault_system["mean_seismic_hazard_index"], 0.0)
        self.assertLessEqual(first_fault_system["mean_seismic_hazard_index"], 1.0)
        self.assertGreaterEqual(first_fault_system["max_seismic_hazard_index"], first_fault_system["mean_seismic_hazard_index"])
        self.assertGreaterEqual(first_fault_system["mean_earthquake_recurrence_interval_y"], 0.0)
        self.assertEqual(first_fault_system["boundary_edge_count"], len(first_fault_system["boundary_edge_ids"]))
        self.assertTrue(first_fault_system["dominant_boundary_type"])
        self.assertTrue(first_fault_system["dominant_crust_type"])
        self.assertTrue(first_fault_system["dominant_landform"])
    def test_geology_realism_checks(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertEqual(summary["geology_realism_check_count"], len(world["geology_realism_checks"]))
        self.assertGreaterEqual(summary["geology_realism_check_count"], 6)
        self.assertEqual(
            summary["geology_realism_pass_count"],
            sum(1 for check in world["geology_realism_checks"] if check["passed"]),
        )
        self.assertGreaterEqual(summary["geology_realism_pass_fraction"], 0.0)
        self.assertLessEqual(summary["geology_realism_pass_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_geology_realism_score"], 0.0)
        self.assertLessEqual(summary["mean_geology_realism_score"], 1.0)
        for key in (
            "mountain_convergent_alignment",
            "trench_convergent_alignment",
            "oceanic_ridge_divergent_alignment",
            "volcanic_arc_trench_pairing",
            "transform_fault_linearity",
            "hypsometry_bimodality_index",
        ):
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        geology_names = {check["name"] for check in world["geology_realism_checks"]}
        self.assertTrue(
            {
                "mountain_convergent_alignment",
                "trench_convergent_alignment",
                "oceanic_ridge_divergent_alignment",
                "volcanic_arc_trench_pairing",
                "transform_fault_linearity",
                "hypsometry_bimodality",
            }.issubset(geology_names)
        )
        first_geology_check = world["geology_realism_checks"][0]
        for key in ("domain", "question", "metric", "value", "target_min", "target_max", "score", "passed", "evidence"):
            self.assertIn(key, first_geology_check)
        self.assertEqual(first_geology_check["domain"], "geology")
        self.assertGreaterEqual(first_geology_check["score"], 0.0)
        self.assertLessEqual(first_geology_check["score"], 1.0)
        self.assertEqual(summary["calibration_check_count"], len(world["calibration_checks"]))
        self.assertGreaterEqual(summary["calibration_check_count"], 10)
        self.assertEqual(
            summary["calibration_pass_count"],
            sum(1 for check in world["calibration_checks"] if check["passed"]),
        )
        self.assertIn("calibration_pass_fraction", summary)
        self.assertGreaterEqual(summary["calibration_pass_fraction"], 0.0)
        self.assertLessEqual(summary["calibration_pass_fraction"], 1.0)
        self.assertIn("mean_calibration_score", summary)
        self.assertGreaterEqual(summary["mean_calibration_score"], 0.0)
        self.assertLessEqual(summary["mean_calibration_score"], 1.0)
        self.assertEqual(summary["sacred_area_count"], len(world["sacred_areas"]))
        self.assertEqual(summary["ruin_count"], len(world["ruins"]))
    def test_zero_erosion_simulation_clock_smoke(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 0
        zero_erosion_config = type(config).model_validate(data)

        world = generate_world(zero_erosion_config)
        clock = world["simulation_clock"]
        history = world["earth_system_feedback_history"]

        self.assertEqual(clock["configured_erosion_iteration_count"], 0)
        self.assertEqual(clock["configured_cryosphere_coupling_stage_count"], 1)
        self.assertEqual(clock["cryosphere_coupling_stage_count"], 1)
        self.assertEqual(clock["feedback_recompute_count"], 1)
        self.assertEqual(clock["stage_count"], 2)
        self.assertEqual(clock["final_cryosphere_stage_id"], 1)
        self.assertFalse(clock["physical_time_resolved"])
        self.assertEqual(
            [step["stage"] for step in history],
            ["initial_climate_hydrology", "cryosphere_coupling"],
        )
        self.assertFalse(any(step["erosion_applied"] for step in history))
        self.assertEqual([step["cryosphere_applied"] for step in history], [False, True])
        self.assertFalse(any(step["plate_motion_applied"] for step in history))
        self.assertFalse(any(step["crust_transport_applied"] for step in history))
        self.assertFalse(any(step["crust_evolution_applied"] for step in history))
        self.assertEqual([step["plate_motion_history_id"] for step in history], [0, 0])
        self.assertEqual(world["plate_kinematic_model"]["configured_motion_step_count"], 0)
        self.assertEqual(world["plate_kinematic_model"]["history_step_count"], 1)
        self.assertTrue(world["plate_kinematic_model"]["crust_advection_resolved"])
        self.assertTrue(world["plate_kinematic_model"]["mass_conserving_crust_transport"])
        motion_history = world["plate_motion_history"]
        self.assertEqual([step["stage"] for step in motion_history], ["initial_plate_domains"])
        self.assertEqual(
            motion_history[0]["cell_plate_ids"],
            [cell["initial_plate_id"] for cell in world["cells"]],
        )
        self.assertEqual(
            motion_history[0]["cell_plate_ids"],
            [cell["plate_id"] for cell in world["cells"]],
        )
        self.assertEqual(
            motion_history[0]["crust_overlap_ledger"]["dominant_source_cell_ids"],
            list(range(len(world["cells"]))),
        )
        self.assertTrue(all(value == 0.0 for value in motion_history[0]["crust_transport_distance_km_by_cell"]))
        self.assertTrue(
            all(
                value == 0.0
                for key in (
                    "crust_age_change_ma_by_cell",
                    "crust_thickness_change_km_by_cell",
                    "crust_density_change_by_cell",
                    "tectonic_elevation_change_m_by_cell",
                )
                for value in motion_history[0][key]
            )
        )
        self.assertTrue(all(plate["initial_center"] == plate["center"] for plate in world["plates"]))
        self.assertEqual(world["summary"]["simulation_clock_erosion_iteration_count"], 0)
        self.assertEqual(
            world["summary"]["simulation_clock_cryosphere_coupling_stage_count"],
            1,
        )
        self.assertEqual(len(world["glacial_sediment_transport_history"]), 1)
        self.assertEqual(world["summary"]["mean_erosion_iteration_elevation_change_m"], 0.0)
        self.assertEqual(world["summary"]["plate_motion_transition_count"], 0)
        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "zero-erosion.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            self.assertEqual(result.exit_code, 0, result.output)
    def test_zero_plate_motion_keeps_identity_overlap_transport(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["tectonics"]["plate_motion_scale_deg_per_step"] = 0.0
        data["erosion"]["iterations"] = 2
        stationary = type(config).model_validate(data)

        world = generate_world(stationary)
        expected_sources = list(range(len(world["cells"])))
        for step in world["plate_motion_history"]:
            self.assertEqual(
                step["crust_overlap_ledger"]["dominant_source_cell_ids"],
                expected_sources,
            )
            self.assertTrue(all(distance == 0.0 for distance in step["crust_transport_distance_km_by_cell"]))
            self.assertTrue(all(delta == 0.0 for delta in step["crust_age_transport_change_ma_by_cell"]))
        self.assertTrue(all(plate["initial_center"] == plate["center"] for plate in world["plates"]))
        self.assertEqual(world["summary"]["max_crust_transport_distance_km"], 0.0)

        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "stationary-plates.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            self.assertEqual(result.exit_code, 0, result.output)
