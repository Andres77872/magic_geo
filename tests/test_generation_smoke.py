import csv
import json
import math
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.api import backend_info, generate_world
from magic_geo.calibration import (
    derive_calibration_targets,
    evaluate_calibration_targets,
    load_calibration_sources,
)
from magic_geo.config import config_to_native, load_config
from magic_geo.cli import app
from magic_geo.io import write_cells_csv, write_raster_map, write_summary_markdown, write_svg_map
from magic_geo.navigability_diagnostics import enrich_world_with_navigability_diagnostics
from magic_geo.native import generate_world as generate_native_world
from magic_geo.port_sites import enrich_world_with_port_sites
from magic_geo.river_channel_morphology import enrich_world_with_river_channel_morphology
from magic_geo.river_hydraulics import enrich_world_with_river_hydraulics
from magic_geo.route_corridors import enrich_world_with_route_corridors
from magic_geo.scaling import HACK_FIT_MINIMUM_BASIN_AREA_KM2, fit_power_law
from magic_geo.sediment_interface_validation import validate_sediment_interfaces


class GenerationSmokeTests(TestCase):
    def test_backend_info_has_native_core(self) -> None:
        info = backend_info()

        self.assertEqual(info["native_core"], "c++20")
        self.assertIn("opencl_loader_found", info)

    def test_geodynamic_diagnostics_are_exported(self) -> None:
        world = {
            "name": "export probe",
            "backend": {},
            "cells": [
                {
                    "id": 0,
                    "plate_id": 2,
                    "initial_plate_id": 1,
                    "plate_assignment_change_count": 1,
                    "last_plate_assignment_change_iteration": 2,
                    "crust_age_ma": 40.0,
                    "initial_crust_age_ma": 55.0,
                    "crust_thickness_km": 7.0,
                    "initial_crust_thickness_km": 7.5,
                    "crust_density": 3.0,
                    "initial_crust_density": 2.98,
                    "cumulative_tectonic_elevation_change_m": 18.5,
                    "last_crust_source_cell_id": 4,
                    "crust_source_remap_event_count": 2,
                    "oceanic_crust_aging_event_count": 1,
                    "oceanic_crust_rejuvenation_event_count": 2,
                    "oceanic_crust_subduction_event_count": 1,
                    "cumulative_crust_transport_distance_km": 314.5,
                    "hydrologic_surface_elevation_m": 412.125,
                    "hydrologic_flow_drop_m": 0.001,
                    "hydrologic_flow_slope": 0.0000000025,
                    "hydrologic_surface_conditioned": True,
                    "cumulative_numeric_depression_fill_m": 128.75,
                    "numeric_depression_fill_event_count": 2,
                    "cumulative_numeric_depression_breach_excavation_m": 12.5,
                    "cumulative_numeric_depression_breach_deposition_m": 4.25,
                    "numeric_depression_breach_event_count": 3,
                    "numeric_depression_temporary_lake_event_count": 4,
                    "hillslope_sediment_production_m": 9.5,
                    "hillslope_sediment_deposition_m": 7.25,
                    "hillslope_sediment_net_m": -2.25,
                    "hillslope_sediment_outgoing_edge_count": 6,
                    "hillslope_sediment_incoming_edge_count": 5,
                    "glacial_sediment_production_m": 3.5,
                    "glacial_sediment_net_m": 0.75,
                    "glacial_sediment_outgoing_transfer_count": 2,
                    "glacial_sediment_incoming_transfer_count": 3,
                    "sediment_alluvium_entrainment_m": 14.25,
                    "sediment_bedrock_erosion_m": 8.75,
                    "hydrologic_potential_evapotranspiration_mm_y": 512.5,
                    "groundwater_recharge_source_infiltration_mm_y": 80.0,
                    "groundwater_recharge_fraction": 0.4,
                    "vadose_zone_retention_mm_y": 48.0,
                    "vadose_zone_retention_km3_y": 0.25,
                    "groundwater_recharge_mass_balance_residual_mm_y": 0.0,
                    "groundwater_lateral_inflow_km3_y": 0.125,
                    "groundwater_available_volume_km3_y": 0.625,
                    "groundwater_internal_lateral_outflow_km3_y": 0.2,
                    "groundwater_retained_storage_km3_y": 0.3,
                    "groundwater_flow_mass_balance_residual_km3_y": 0.0,
                }
            ],
            "summary": {
                "plate_motion_history_step_count": 3,
                "plate_motion_transition_count": 2,
                "total_plate_reassignment_event_count": 1,
                "total_crust_source_remap_event_count": 2,
                "mean_plate_cumulative_rotation_deg": 3.25,
                "numeric_depression_correction_model": (
                    "bounded_mass_conserving_breach_or_zero_material_temporary_lake_with_coupled_recomputation_v3"
                ),
                "numeric_depression_correction_selection_model": (
                    "lower_volume_full_cell_breach_with_50m_depth_bound_else_temporary_lake_v3"
                ),
                "numeric_depression_fill_event_count": 2,
                "numeric_depression_breach_lower_volume_event_count": 1,
                "simulation_clock_cryosphere_coupling_stage_count": 1,
                "glacial_sediment_transport_stage_count": 1,
                "glacial_sediment_transfer_count": 12,
            },
        }
        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "cells.csv"
            summary_path = Path(temp_dir) / "summary.md"
            write_cells_csv(csv_path, world)
            write_summary_markdown(summary_path, world)

            with csv_path.open(encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                row = next(reader)
                fieldnames = reader.fieldnames or []
            self.assertEqual(row["initial_plate_id"], "1")
            self.assertEqual(row["plate_assignment_change_count"], "1")
            self.assertEqual(row["initial_crust_age_ma"], "55.0")
            self.assertEqual(row["cumulative_tectonic_elevation_change_m"], "18.5")
            self.assertEqual(row["last_crust_source_cell_id"], "4")
            self.assertEqual(row["crust_source_remap_event_count"], "2")
            self.assertEqual(row["cumulative_crust_transport_distance_km"], "314.5")
            self.assertEqual(row["hydrologic_surface_elevation_m"], "412.125")
            self.assertEqual(row["hydrologic_flow_drop_m"], "0.001")
            self.assertEqual(row["hydrologic_flow_slope"], "2.5e-09")
            self.assertEqual(row["hydrologic_surface_conditioned"], "True")
            self.assertEqual(row["cumulative_numeric_depression_fill_m"], "128.75")
            self.assertEqual(row["numeric_depression_fill_event_count"], "2")
            self.assertEqual(
                row["cumulative_numeric_depression_breach_excavation_m"],
                "12.5",
            )
            self.assertEqual(
                row["cumulative_numeric_depression_breach_deposition_m"],
                "4.25",
            )
            self.assertEqual(row["numeric_depression_breach_event_count"], "3")
            self.assertEqual(
                row["numeric_depression_temporary_lake_event_count"], "4"
            )
            self.assertEqual(row["hillslope_sediment_production_m"], "9.5")
            self.assertEqual(row["hillslope_sediment_deposition_m"], "7.25")
            self.assertEqual(row["hillslope_sediment_net_m"], "-2.25")
            self.assertEqual(row["hillslope_sediment_outgoing_edge_count"], "6")
            self.assertEqual(row["hillslope_sediment_incoming_edge_count"], "5")
            self.assertEqual(row["glacial_sediment_production_m"], "3.5")
            self.assertEqual(row["glacial_sediment_net_m"], "0.75")
            self.assertEqual(row["glacial_sediment_outgoing_transfer_count"], "2")
            self.assertEqual(row["glacial_sediment_incoming_transfer_count"], "3")
            self.assertEqual(row["sediment_alluvium_entrainment_m"], "14.25")
            self.assertEqual(row["sediment_bedrock_erosion_m"], "8.75")
            self.assertEqual(
                row["hydrologic_potential_evapotranspiration_mm_y"], "512.5"
            )
            self.assertEqual(
                row["groundwater_recharge_source_infiltration_mm_y"], "80.0"
            )
            self.assertEqual(row["groundwater_recharge_fraction"], "0.4")
            self.assertEqual(row["vadose_zone_retention_mm_y"], "48.0")
            self.assertEqual(row["groundwater_lateral_inflow_km3_y"], "0.125")
            self.assertEqual(row["groundwater_available_volume_km3_y"], "0.625")
            self.assertEqual(
                row["groundwater_internal_lateral_outflow_km3_y"],
                "0.2",
            )
            self.assertEqual(row["groundwater_retained_storage_km3_y"], "0.3")
            self.assertEqual(fieldnames.index("glacial_sediment_deposition_m"), 371)
            self.assertEqual(fieldnames.index("fluvial_sediment_local_source_m"), 373)
            self.assertEqual(fieldnames.index("fluvial_sediment_routing_event_count"), 382)
            self.assertEqual(fieldnames.index("hillslope_sediment_production_m"), 383)
            self.assertEqual(fieldnames.index("hillslope_sediment_deposition_m"), 384)
            self.assertEqual(fieldnames.index("hillslope_sediment_net_m"), 385)
            self.assertEqual(
                fieldnames.index("hillslope_sediment_outgoing_edge_count"), 386
            )
            self.assertEqual(
                fieldnames.index("hillslope_sediment_incoming_edge_count"), 387
            )
            self.assertEqual(fieldnames.index("glacial_sediment_production_m"), 388)
            self.assertEqual(fieldnames.index("glacial_sediment_net_m"), 389)
            self.assertEqual(
                fieldnames.index("glacial_sediment_outgoing_transfer_count"),
                390,
            )
            self.assertEqual(
                fieldnames.index("glacial_sediment_incoming_transfer_count"),
                391,
            )
            self.assertEqual(
                fieldnames.index("sediment_alluvium_entrainment_m"), 392
            )
            self.assertEqual(fieldnames.index("sediment_bedrock_erosion_m"), 393)
            self.assertEqual(
                fieldnames.index(
                    "hydrologic_potential_evapotranspiration_mm_y"
                ),
                394,
            )
            self.assertEqual(
                fieldnames.index(
                    "groundwater_recharge_source_infiltration_mm_y"
                ),
                395,
            )
            self.assertEqual(
                fieldnames.index("groundwater_recharge_fraction"), 396
            )
            self.assertEqual(
                fieldnames.index("vadose_zone_retention_mm_y"), 397
            )
            self.assertEqual(
                fieldnames.index("vadose_zone_retention_km3_y"), 398
            )
            self.assertEqual(
                fieldnames.index(
                    "groundwater_recharge_mass_balance_residual_mm_y"
                ),
                399,
            )
            self.assertEqual(
                fieldnames.index("groundwater_lateral_inflow_km3_y"),
                400,
            )
            self.assertEqual(
                fieldnames.index("groundwater_available_volume_km3_y"),
                401,
            )
            self.assertEqual(
                fieldnames.index(
                    "groundwater_internal_lateral_outflow_km3_y"
                ),
                402,
            )
            self.assertEqual(
                fieldnames.index("groundwater_retained_storage_km3_y"),
                403,
            )
            self.assertEqual(
                fieldnames.index(
                    "groundwater_flow_mass_balance_residual_km3_y"
                ),
                404,
            )
            summary_text = summary_path.read_text(encoding="utf-8")
            self.assertIn("`plate_motion_history_step_count`: 3", summary_text)
            self.assertIn("`total_crust_source_remap_event_count`: 2", summary_text)
            self.assertIn("`mean_plate_cumulative_rotation_deg`: 3.25", summary_text)
            self.assertIn("`numeric_depression_fill_event_count`: 2", summary_text)
            self.assertIn(
                "`numeric_depression_breach_lower_volume_event_count`: 1",
                summary_text,
            )
            self.assertIn(
                "`simulation_clock_cryosphere_coupling_stage_count`: 1",
                summary_text,
            )
            self.assertIn("`glacial_sediment_transfer_count`: 12", summary_text)

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
        self.assertEqual(motion_history[0]["crust_source_cell_ids"], list(range(len(world["cells"]))))
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

    def test_zero_plate_motion_keeps_identity_crust_sources(self) -> None:
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
            self.assertEqual(step["crust_source_cell_ids"], expected_sources)
            self.assertEqual(step["crust_source_remap_cell_count"], 0)
            self.assertEqual(step["crust_source_reuse_count"], 0)
            self.assertTrue(all(distance == 0.0 for distance in step["crust_transport_distance_km_by_cell"]))
            self.assertTrue(all(delta == 0.0 for delta in step["crust_age_transport_change_ma_by_cell"]))
        self.assertTrue(all(plate["initial_center"] == plate["center"] for plate in world["plates"]))
        self.assertEqual(world["summary"]["total_crust_source_remap_event_count"], 0)
        self.assertEqual(world["summary"]["max_crust_transport_distance_km"], 0.0)

        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "stationary-plates.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            self.assertEqual(result.exit_code, 0, result.output)

    def test_zero_ocean_inventory_produces_no_marine_water(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 0
        data["planet"]["ocean_water_inventory_km3"] = 0.0
        dry_config = type(config).model_validate(data)

        world = generate_world(dry_config)

        self.assertFalse(any(cell["is_water"] for cell in world["cells"]))
        self.assertEqual(world["sea_level_model"]["selected_ocean_cell_count"], 0)
        self.assertEqual(world["sea_level_model"]["selected_ocean_volume_km3"], 0.0)
        self.assertEqual(world["summary"]["ocean_volume_km3"], 0.0)
        self.assertTrue(
            all(
                step["ocean_volume_km3"] == 0.0
                for step in world["earth_system_feedback_history"]
            )
        )

        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "dry-world.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            self.assertEqual(result.exit_code, 0, result.output)

    def test_ocean_connectivity_jump_uses_closest_volume_interval(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 0
        data["planet"]["ocean_water_inventory_km3"] = 500_000_000.0
        jump_config = type(config).model_validate(data)

        world = generate_world(jump_config)
        sea_level_model = world["sea_level_model"]

        self.assertGreater(sea_level_model["ocean_water_inventory_error_km3"], 1.0)
        self.assertEqual(sea_level_model["selected_ocean_cell_count"], 45)
        self.assertAlmostEqual(
            sea_level_model["selected_ocean_volume_km3"],
            sum(
                cell["area_km2"] * cell["water_depth_m"] / 1000.0
                for cell in world["cells"]
                if cell["is_water"]
            ),
            delta=0.05,
        )

        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "connectivity-jump.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            self.assertEqual(result.exit_code, 0, result.output)

    def test_high_ocean_inventory_can_produce_a_water_world(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 0
        data["planet"]["ocean_water_inventory_km3"] = 10_000_000_000.0
        water_world_config = type(config).model_validate(data)

        world = generate_world(water_world_config)

        self.assertTrue(all(cell["is_water"] for cell in world["cells"]))
        self.assertEqual(world["summary"]["ocean_fraction"], 1.0)
        self.assertEqual(world["summary"]["basin_count"], 0)
        self.assertAlmostEqual(
            world["sea_level_model"]["selected_ocean_volume_km3"],
            water_world_config.planet.ocean_water_inventory_km3,
            delta=1.0,
        )

        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "water-world.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            self.assertEqual(result.exit_code, 0, result.output)

    def test_underresolved_plate_domains_fail_explicitly(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 64
        data["erosion"]["iterations"] = 6
        underresolved = type(config).model_validate(data)

        with self.assertRaisesRegex(RuntimeError, "nearest-center plate domain became empty"):
            generate_world(underresolved)

    def test_strict_validation_rejects_coupling_and_climate_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        data["planet"]["ocean_fraction_target"] = 0.33203125
        coupled_config = type(config).model_validate(data)
        world = generate_world(coupled_config)

        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "world.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            runner = CliRunner()

            valid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            original_ocean_count = world["sea_level_model"]["selected_ocean_cell_count"]
            world["sea_level_model"]["selected_ocean_cell_count"] += 1
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("sea level model metadata or connectivity invalid", invalid_result.output)
            world["sea_level_model"]["selected_ocean_cell_count"] = original_ocean_count

            original_ocean_area = world["sea_level_model"]["selected_ocean_area_km2"]
            world["sea_level_model"]["selected_ocean_area_km2"] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("sea level model metadata or connectivity invalid", invalid_result.output)
            world["sea_level_model"]["selected_ocean_area_km2"] = original_ocean_area

            original_ocean_volume = world["sea_level_model"]["selected_ocean_volume_km3"]
            world["sea_level_model"]["selected_ocean_volume_km3"] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("sea level model metadata or connectivity invalid", invalid_result.output)
            world["sea_level_model"]["selected_ocean_volume_km3"] = original_ocean_volume

            original_flow_cycle_count = world["summary"]["flow_cycle_cell_count"]
            world["summary"]["flow_cycle_cell_count"] += 1
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrology flow routing or accumulation invalid",
                invalid_result.output,
            )
            world["summary"]["flow_cycle_cell_count"] = original_flow_cycle_count

            flow_cell = next(cell for cell in world["cells"] if cell["flow_to"] >= 0)
            original_filled_elevation = flow_cell["filled_elevation_m"]
            flow_cell["filled_elevation_m"] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrology flow routing or accumulation invalid",
                invalid_result.output,
            )
            flow_cell["filled_elevation_m"] = original_filled_elevation

            original_hydrologic_surface = flow_cell[
                "hydrologic_surface_elevation_m"
            ]
            flow_cell["hydrologic_surface_elevation_m"] += 0.1
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrology flow routing or accumulation invalid",
                invalid_result.output,
            )
            flow_cell[
                "hydrologic_surface_elevation_m"
            ] = original_hydrologic_surface

            flow_cell["is_river"] = not flow_cell["is_river"]
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrology flow routing or accumulation invalid",
                invalid_result.output,
            )
            flow_cell["is_river"] = not flow_cell["is_river"]

            if world["lake_basins"]:
                original_depression_cell_count = world["lake_basins"][0][
                    "depression_cell_count"
                ]
                world["lake_basins"][0]["depression_cell_count"] += 1
                world_path.write_text(json.dumps(world), encoding="utf-8")
                invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
                self.assertNotEqual(invalid_result.exit_code, 0)
                self.assertIn(
                    "hydrology depression components or lake basin aggregation invalid",
                    invalid_result.output,
                )
                world["lake_basins"][0][
                    "depression_cell_count"
                ] = original_depression_cell_count

                component_counts = Counter(
                    cell["depression_component_id"]
                    for cell in world["cells"]
                    if cell["depression_component_id"] >= 0
                )
                multi_cell_component_id = next(
                    (
                        component_id
                        for component_id, count in component_counts.items()
                        if count > 1
                    ),
                    None,
                )
                if multi_cell_component_id is not None:
                    mutated_cell = next(
                        cell
                        for cell in world["cells"]
                        if cell["depression_component_id"] == multi_cell_component_id
                    )
                    original_policy = mutated_cell["depression_policy"]
                    mutated_cell["depression_policy"] = (
                        "dry_closed"
                        if original_policy != "dry_closed"
                        else "corrected_numeric"
                    )
                    world_path.write_text(json.dumps(world), encoding="utf-8")
                    invalid_result = runner.invoke(
                        app, ["validate", "--world", str(world_path)]
                    )
                    self.assertNotEqual(invalid_result.exit_code, 0)
                    self.assertIn(
                        "hydrology depression components or lake basin aggregation invalid",
                        invalid_result.output,
                    )
                    mutated_cell["depression_policy"] = original_policy

            original_feedback_ocean_area = world["earth_system_feedback_history"][-1][
                "ocean_area_km2"
            ]
            world["earth_system_feedback_history"][-1]["ocean_area_km2"] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "simulation clock or earth-system feedback history invalid",
                invalid_result.output,
            )
            world["earth_system_feedback_history"][-1][
                "ocean_area_km2"
            ] = original_feedback_ocean_area

            original_feedback_ocean_volume = world["earth_system_feedback_history"][-1][
                "ocean_volume_km3"
            ]
            world["earth_system_feedback_history"][-1]["ocean_volume_km3"] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "simulation clock or earth-system feedback history invalid",
                invalid_result.output,
            )
            world["earth_system_feedback_history"][-1][
                "ocean_volume_km3"
            ] = original_feedback_ocean_volume

            cells_by_id = {cell["id"]: cell for cell in world["cells"]}
            coastal_land = next(
                cell
                for cell in world["cells"]
                if not cell["is_water"]
                and cell["elevation_m"] >= 0.0
                and any(cells_by_id[neighbor_id]["is_water"] for neighbor_id in cell["neighbors"])
            )
            original_coastal_elevation = coastal_land["elevation_m"]
            coastal_land["elevation_m"] = -0.0001
            world["sea_level_model"]["below_sea_level_land_cell_count"] += 1
            world["sea_level_model"]["below_sea_level_land_area_km2"] += coastal_land["area_km2"]
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("sea level model metadata or connectivity invalid", invalid_result.output)
            coastal_land["elevation_m"] = original_coastal_elevation
            world["sea_level_model"]["below_sea_level_land_cell_count"] -= 1
            world["sea_level_model"]["below_sea_level_land_area_km2"] -= coastal_land["area_km2"]

            original_climate_offset = world["climate_model"][
                "latitude_temperature_area_mean_offset_c"
            ]
            world["climate_model"]["latitude_temperature_area_mean_offset_c"] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("climate model metadata invalid", invalid_result.output)
            world["climate_model"][
                "latitude_temperature_area_mean_offset_c"
            ] = original_climate_offset

            world["climate_model"]["marine_annual_temperature_offset_c"] = 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("climate model metadata invalid", invalid_result.output)
            world["climate_model"]["marine_annual_temperature_offset_c"] = 0.0

            original_thermal_moisture_factor = world["climate_model"][
                "thermal_moisture_capacity_factor"
            ]
            world["climate_model"]["thermal_moisture_capacity_factor"] += 0.1
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("climate model metadata invalid", invalid_result.output)
            world["climate_model"][
                "thermal_moisture_capacity_factor"
            ] = original_thermal_moisture_factor

            original_fitted_hack_exponent = world["summary"]["watershed_hack_fitted_exponent"]
            world["summary"]["watershed_hack_fitted_exponent"] += 0.1
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("watershed_hack_fitted_exponent does not match watersheds", invalid_result.output)
            world["summary"]["watershed_hack_fitted_exponent"] = original_fitted_hack_exponent

            original_continental_count = world["plate_kinematic_model"][
                "initial_continental_crust_cell_count"
            ]
            world["plate_kinematic_model"]["initial_continental_crust_cell_count"] += 1
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("plate kinematic model or motion history invalid", invalid_result.output)
            world["plate_kinematic_model"][
                "initial_continental_crust_cell_count"
            ] = original_continental_count

            initial_age_ledger = world["initial_oceanic_crust_age_ledger"]
            oceanic_initial_age_cell_id = next(
                cell_id
                for cell_id, status_id in enumerate(
                    initial_age_ledger["status_id_by_cell"]
                )
                if status_id != 0
            )
            original_initial_oceanic_age = initial_age_ledger[
                "age_ma_by_cell"
            ][oceanic_initial_age_cell_id]
            initial_age_ledger["age_ma_by_cell"][
                oceanic_initial_age_cell_id
            ] += 0.01
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(
                app, ["validate", "--world", str(world_path)]
            )
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "initial oceanic crust age replay invalid:",
                invalid_result.output,
            )
            initial_age_ledger["age_ma_by_cell"][
                oceanic_initial_age_cell_id
            ] = original_initial_oceanic_age

            world["plate_kinematic_model"]["continental_orogen_uplift_scale_m"] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("plate kinematic model or motion history invalid", invalid_result.output)
            world["plate_kinematic_model"]["continental_orogen_uplift_scale_m"] -= 1.0

            original_initial_crust_type = world["plate_motion_history"][0][
                "crust_type_by_cell"
            ][0]
            world["plate_motion_history"][0]["crust_type_by_cell"][0] = "invalid"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("plate kinematic model or motion history invalid", invalid_result.output)
            world["plate_motion_history"][0]["crust_type_by_cell"][0] = (
                original_initial_crust_type
            )

            world["plate_kinematic_model"]["mass_conserving_crust_transport"] = False
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("plate kinematic model or motion history invalid", invalid_result.output)
            world["plate_kinematic_model"]["mass_conserving_crust_transport"] = True

            shadow_masses = world["crust_material_shadow_history"][0][
                "opening_packets"
            ]["dry_rock_mass_kg"]
            original_shadow_mass = shadow_masses[0]
            shadow_masses[0] += max(1.0, abs(original_shadow_mass) * 1.0e-8)
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("crust material shadow:", invalid_result.output)
            shadow_masses[0] = original_shadow_mass

            original_source = world["plate_motion_history"][1]["crust_source_cell_ids"][0]
            world["plate_motion_history"][1]["crust_source_cell_ids"][0] = (
                original_source + 1
            ) % len(world["cells"])
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("plate kinematic model or motion history invalid", invalid_result.output)
            world["plate_motion_history"][1]["crust_source_cell_ids"][0] = original_source

            original_distance = world["plate_motion_history"][1][
                "crust_transport_distance_km_by_cell"
            ][0]
            world["plate_motion_history"][1]["crust_transport_distance_km_by_cell"][0] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("plate kinematic model or motion history invalid", invalid_result.output)
            world["plate_motion_history"][1]["crust_transport_distance_km_by_cell"][
                0
            ] = original_distance

            original_remap_count = world["cells"][0]["crust_source_remap_event_count"]
            world["cells"][0]["crust_source_remap_event_count"] += 1
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("plate kinematic model or motion history invalid", invalid_result.output)
            world["cells"][0]["crust_source_remap_event_count"] = original_remap_count

            original_center = world["plate_motion_history"][1]["plates"][0]["center"][0]
            world["plate_motion_history"][1]["plates"][0]["center"][0] += 0.05
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("plate kinematic model or motion history invalid", invalid_result.output)
            world["plate_motion_history"][1]["plates"][0]["center"][0] = original_center

            original_delta = world["plate_motion_history"][1]["crust_age_change_ma_by_cell"][0]
            world["plate_motion_history"][1]["crust_age_change_ma_by_cell"][0] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("plate kinematic model or motion history invalid", invalid_result.output)
            world["plate_motion_history"][1]["crust_age_change_ma_by_cell"][0] = original_delta

            world["earth_system_feedback_history"][1]["climate_recomputed"] = False
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("simulation clock or earth-system feedback history invalid", invalid_result.output)

            world["earth_system_feedback_history"][1]["climate_recomputed"] = True
            world["cells"][0]["climate_class"] = "invalid"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("climate classification invalid", invalid_result.output)

    def test_fluvial_sediment_routing_provenance(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        routed_config = type(config).model_validate(data)
        world = generate_world(routed_config)

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
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        routed_config = type(config).model_validate(data)
        world = generate_world(routed_config)
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

    def test_glacial_sediment_transport_provenance_and_terrain_coupling(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        coupled_config = type(config).model_validate(data)
        world = generate_world(coupled_config)

        model = world["glacial_sediment_transport_model"]
        history = world["glacial_sediment_transport_history"]
        cells = world["cells"]
        self.assertEqual(
            model["model_type"],
            "downhill_area_conserving_glacial_sediment_transport_v2",
        )
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
        self.assertEqual(stage["feedback_stage_id"], 2)
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

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            transfer = stage["transfers"][0]
            transfer["target_deposition_depth_m"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "glacial sediment transport transfer replay invalid",
                invalid_result.output,
            )
            transfer["target_deposition_depth_m"] -= 1.0

            removed_transfer = stage["transfers"].pop()
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "glacial sediment transport transfer coverage invalid",
                invalid_result.output,
            )
            stage["transfers"].append(removed_transfer)

            source_id = transfer["source_cell_id"]
            stage["post_transport_elevation_m_by_cell"][source_id] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "glacial sediment terrain coupling snapshot invalid",
                invalid_result.output,
            )
            stage["post_transport_elevation_m_by_cell"][source_id] -= 1.0

            cells[source_id]["glacial_sediment_production_m"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "glacial sediment transport cumulative cell fields invalid",
                invalid_result.output,
            )
            cells[source_id]["glacial_sediment_production_m"] -= 1.0

    def test_causal_hydrologic_water_budget_replay_and_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        budget_config = type(config).model_validate(data)
        world = generate_world(budget_config)
        model = world["hydrologic_water_budget_model"]
        recharge_model = world["groundwater_recharge_model"]
        aquifer_model = world["aquifer_resource_model"]
        flow_model = world["groundwater_flow_model"]
        history = world["hydrologic_water_budget_history"]
        feedback = world["earth_system_feedback_history"]
        cells = world["cells"]

        self.assertEqual(
            model["model_type"],
            "causal_land_climate_loss_partition_v1",
        )
        self.assertTrue(model["runoff_computed_before_flow_routing"])
        self.assertEqual(
            len(history),
            sum(
                step["hydrologic_water_budget_recompute_count"]
                for step in feedback
            ),
        )
        self.assertEqual(
            world["simulation_clock"][
                "hydrologic_water_budget_recompute_count"
            ],
            len(history),
        )
        final_stage = history[-1]
        self.assertEqual(final_stage["cell_count"], len(cells))
        self.assertEqual(
            final_stage["land_cell_count"] + final_stage["marine_cell_count"],
            len(cells),
        )
        land_position = next(
            index
            for index, is_marine in enumerate(final_stage["is_marine_by_cell"])
            if not is_marine
        )
        precipitation = final_stage["precipitation_mm_y_by_cell"][land_position]
        pet = final_stage[
            "potential_evapotranspiration_mm_y_by_cell"
        ][land_position]
        climate_loss = min(precipitation, 0.68 * pet)
        actual_et = final_stage[
            "actual_evapotranspiration_mm_y_by_cell"
        ][land_position]
        infiltration = final_stage["infiltration_mm_y_by_cell"][land_position]
        runoff = final_stage["runoff_mm_y_by_cell"][land_position]
        self.assertAlmostEqual(actual_et + infiltration, climate_loss, places=7)
        self.assertAlmostEqual(
            runoff,
            max(0.0, precipitation - actual_et - infiltration),
            places=7,
        )
        self.assertTrue(
            all(
                cell["actual_evapotranspiration_mm_y"] == 0.0
                and cell["infiltration_mm_y"] == 0.0
                and cell["runoff_mm_y"] == 0.0
                for cell in cells
                if cell["is_water"]
            )
        )
        self.assertEqual(
            recharge_model["model_type"],
            "infiltration_bounded_aquifer_recharge_v1",
        )
        self.assertEqual(
            aquifer_model["model_type"],
            "finite_recharge_causal_aquifer_resources_v1",
        )
        self.assertEqual(
            aquifer_model["system_eligible_cell_count"],
            sum(system["cell_count"] for system in world["aquifer_systems"]),
        )
        self.assertAlmostEqual(
            recharge_model["total_source_infiltration_volume_km3_y"],
            recharge_model["total_groundwater_recharge_volume_km3_y"]
            + recharge_model["total_vadose_zone_retention_volume_km3_y"],
            delta=0.000001,
        )
        self.assertLessEqual(
            world["summary"]["total_groundwater_discharge_km3_y"],
            world["summary"]["total_groundwater_recharge_km3_y"] + 0.001,
        )
        self.assertEqual(
            flow_model["model_type"],
            "descending_head_recharge_conserving_groundwater_flow_v1",
        )
        self.assertAlmostEqual(
            flow_model["total_source_recharge_volume_km3_y"],
            flow_model["total_groundwater_discharge_volume_km3_y"]
            + flow_model["total_retained_storage_volume_km3_y"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            flow_model["total_internal_lateral_inflow_volume_km3_y"],
            flow_model["total_internal_lateral_outflow_volume_km3_y"],
            delta=0.001,
        )
        self.assertEqual(flow_model["mass_balance_residual_km3_y"], 0.0)
        self.assertTrue(
            all(
                cell["groundwater_recharge_mm_y"]
                <= cell["groundwater_recharge_source_infiltration_mm_y"]
                + 0.000001
                for cell in cells
            )
        )
        self.assertTrue(
            all(
                abs(
                    cell["groundwater_available_volume_km3_y"]
                    - cell["groundwater_recharge_km3_y"]
                    - cell["groundwater_lateral_inflow_km3_y"]
                )
                <= 0.000003
                and abs(
                    cell["groundwater_available_volume_km3_y"]
                    - cell["groundwater_internal_lateral_outflow_km3_y"]
                    - cell["groundwater_discharge_km3_y"]
                    - cell["groundwater_retained_storage_km3_y"]
                    - cell["groundwater_flow_mass_balance_residual_km3_y"]
                )
                <= 0.000004
                for cell in cells
                if cell["aquifer_class"] != "marine_excluded"
            )
        )

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            final_stage["temperature_c_by_cell"][land_position] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrologic water budget model or replay invalid",
                invalid_result.output,
            )
            final_stage["temperature_c_by_cell"][land_position] -= 1.0

            final_stage[
                "actual_evapotranspiration_mm_y_by_cell"
            ][land_position] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrologic water budget model or replay invalid",
                invalid_result.output,
            )
            final_stage[
                "actual_evapotranspiration_mm_y_by_cell"
            ][land_position] -= 1.0

            feedback[-1]["hydrologic_infiltration_volume_km3_y"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrologic water budget model or replay invalid",
                invalid_result.output,
            )
            feedback[-1]["hydrologic_infiltration_volume_km3_y"] -= 1.0

            land_cell_id = final_stage["cell_ids"][land_position]
            land_cell = cells[land_cell_id]
            land_cell["infiltration_mm_y"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrologic water budget model or replay invalid",
                invalid_result.output,
            )
            land_cell["infiltration_mm_y"] -= 1.0

            model["final_runoff_volume_km3_y"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrologic water budget model or replay invalid",
                invalid_result.output,
            )
            model["final_runoff_volume_km3_y"] -= 1.0

            marine_cell = next(cell for cell in cells if cell["is_water"])
            marine_cell["infiltration_mm_y"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrologic water budget model or replay invalid",
                invalid_result.output,
            )
            marine_cell["infiltration_mm_y"] -= 1.0

            land_cell["groundwater_recharge_fraction"] += 0.1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "groundwater recharge model or source partition invalid",
                invalid_result.output,
            )
            land_cell["groundwater_recharge_fraction"] -= 0.1

            recharge_model["total_groundwater_recharge_volume_km3_y"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "groundwater recharge model or source partition invalid",
                invalid_result.output,
            )
            recharge_model["total_groundwater_recharge_volume_km3_y"] -= 1.0

            original_storage = land_cell["aquifer_storage_index"]
            land_cell["aquifer_storage_index"] = original_storage + 0.1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "aquifer resource model or causal replay invalid",
                invalid_result.output,
            )
            land_cell["aquifer_storage_index"] = original_storage

            original_class = land_cell["aquifer_class"]
            land_cell["aquifer_class"] = "tampered_aquifer"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "aquifer resource model or causal replay invalid",
                invalid_result.output,
            )
            land_cell["aquifer_class"] = original_class

            aquifer_model["minimum_system_productivity_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "aquifer resource model or causal replay invalid",
                invalid_result.output,
            )
            aquifer_model["minimum_system_productivity_index"] -= 0.01

            if world["aquifer_systems"]:
                first_system = world["aquifer_systems"][0]
                original_lithology = first_system["primary_lithology"]
                first_system["primary_lithology"] = "tampered"
                invalid_result = validate_current()
                self.assertNotEqual(invalid_result.exit_code, 0)
                self.assertIn(
                    "aquifer resource model or causal replay invalid",
                    invalid_result.output,
                )
                first_system["primary_lithology"] = original_lithology

            original_head = land_cell["groundwater_hydraulic_head_m"]
            land_cell["groundwater_hydraulic_head_m"] = original_head + 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "groundwater flow model or routing replay invalid",
                invalid_result.output,
            )
            land_cell["groundwater_hydraulic_head_m"] = original_head

            original_available = land_cell[
                "groundwater_available_volume_km3_y"
            ]
            original_retained = land_cell[
                "groundwater_retained_storage_km3_y"
            ]
            land_cell["groundwater_available_volume_km3_y"] = (
                original_available + 1.0
            )
            land_cell["groundwater_retained_storage_km3_y"] = (
                original_retained + 1.0
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "groundwater flow model or routing replay invalid",
                invalid_result.output,
            )
            land_cell["groundwater_available_volume_km3_y"] = (
                original_available
            )
            land_cell["groundwater_retained_storage_km3_y"] = (
                original_retained
            )

            flow_model["total_retained_storage_volume_km3_y"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "groundwater flow model or routing replay invalid",
                invalid_result.output,
            )
            flow_model["total_retained_storage_volume_km3_y"] -= 1.0

    def test_downstream_hydrology_diagnostics_are_topologically_ordered(
        self,
    ) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        ordered_config = type(config).model_validate(data)
        world = generate_world(ordered_config)
        river_cells = [
            cell
            for cell in world["cells"]
            if cell["is_river"] and not cell["is_water"]
        ]

        self.assertTrue(river_cells)
        self.assertTrue(
            any(cell["sediment_routing_load_m"] > 0.0 for cell in river_cells)
        )
        self.assertTrue(
            any(cell["baseflow_support_index"] > 0.0 for cell in river_cells)
        )
        self.assertTrue(
            any(cell["wetland_extent_index"] > 0.0 for cell in river_cells)
        )

        before = json.dumps(world, sort_keys=True)
        enrich_world_with_river_channel_morphology(world)
        enrich_world_with_river_hydraulics(world)
        enrich_world_with_navigability_diagnostics(world)
        enrich_world_with_port_sites(world)
        enrich_world_with_route_corridors(world)
        self.assertEqual(before, json.dumps(world, sort_keys=True))

    def test_river_channel_hydraulic_and_navigability_causal_replay_mutations(
        self,
    ) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        # This mutation suite requires an actual port/corridor witness; the
        # 128-cell topology is too coarse to guarantee one.
        data["mesh"]["cell_count"] = 256
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        data["climate"]["lapse_rate_c_per_km"] = 4.0
        world = generate_world(type(config).model_validate(data))
        summary = world["summary"]
        channel_model = world["river_channel_morphology_model"]
        hydraulic_model = world["river_hydraulics_model"]
        navigability_model = world["navigability_model"]
        port_model = world["port_site_model"]
        route_model = world["route_corridor_model"]
        channel_cells = [
            cell
            for cell in world["cells"]
            if cell["is_river"] and not cell["is_water"]
        ]

        self.assertTrue(channel_cells)
        self.assertEqual(
            channel_model["model_type"],
            "causal_flow_sediment_wetland_baseflow_channel_morphology_v1",
        )
        self.assertEqual(
            hydraulic_model["model_type"],
            "manning_blended_diagnostic_river_hydraulics_v1",
        )
        self.assertEqual(
            navigability_model["model_type"],
            "causal_channel_hydraulic_coastal_navigability_v1",
        )
        self.assertEqual(
            port_model["model_type"],
            "causal_navigability_coastal_port_site_selection_v1",
        )
        self.assertEqual(
            route_model["model_type"],
            "causal_feature_weighted_dijkstra_route_corridors_v1",
        )

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            channel_cell = channel_cells[0]
            channel_system = world["river_channel_systems"][
                channel_cell["river_channel_system_id"]
            ]
            discharge_delta = 1.0
            original_cell_discharge = channel_cell["bankfull_discharge_m3_s"]
            original_summary_discharge = summary["mean_bankfull_discharge_m3_s"]
            original_system_discharge = channel_system[
                "mean_bankfull_discharge_m3_s"
            ]
            channel_cell["bankfull_discharge_m3_s"] += discharge_delta
            summary["mean_bankfull_discharge_m3_s"] += (
                discharge_delta / len(channel_cells)
            )
            channel_system["mean_bankfull_discharge_m3_s"] += (
                discharge_delta / channel_system["cell_count"]
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "river channel morphology model or causal replay invalid",
                invalid_result.output,
            )
            channel_cell["bankfull_discharge_m3_s"] = original_cell_discharge
            summary["mean_bankfull_discharge_m3_s"] = original_summary_discharge
            channel_system[
                "mean_bankfull_discharge_m3_s"
            ] = original_system_discharge

            multi_cell_system = next(
                system
                for system in world["river_channel_systems"]
                if system["cell_count"] > 1
            )
            reach = world["river_hydraulic_reaches"][multi_cell_system["id"]]
            original_source = multi_cell_system["source_cell_id"]
            replacement_source = next(
                cell_id
                for cell_id in multi_cell_system["cell_ids"]
                if cell_id != original_source
            )
            multi_cell_system["source_cell_id"] = replacement_source
            reach["source_cell_id"] = replacement_source
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "river channel morphology model or causal replay invalid",
                invalid_result.output,
            )
            multi_cell_system["source_cell_id"] = original_source
            reach["source_cell_id"] = original_source

            channel_model["slope_normalization"] += 0.001
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "river channel morphology model or causal replay invalid",
                invalid_result.output,
            )
            channel_model["slope_normalization"] -= 0.001

            hydraulic_reach = world["river_hydraulic_reaches"][
                channel_cell["river_hydraulic_reach_id"]
            ]
            velocity_delta = 0.1
            original_cell_velocity = channel_cell["flow_velocity_m_s"]
            original_summary_velocity = summary["mean_flow_velocity_m_s"]
            original_reach_velocity = hydraulic_reach["mean_flow_velocity_m_s"]
            channel_cell["flow_velocity_m_s"] += velocity_delta
            summary["mean_flow_velocity_m_s"] += (
                velocity_delta / len(channel_cells)
            )
            hydraulic_reach["mean_flow_velocity_m_s"] += (
                velocity_delta / hydraulic_reach["cell_count"]
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "river hydraulics model or causal replay invalid",
                invalid_result.output,
            )
            channel_cell["flow_velocity_m_s"] = original_cell_velocity
            summary["mean_flow_velocity_m_s"] = original_summary_velocity
            hydraulic_reach["mean_flow_velocity_m_s"] = original_reach_velocity

            hydraulic_model["gravity_m_s2"] += 0.1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "river hydraulics model or causal replay invalid",
                invalid_result.output,
            )
            hydraulic_model["gravity_m_s2"] -= 0.1

            navigable_cell = next(
                cell
                for cell in world["cells"]
                if cell["navigable_waterway_id"] >= 0
                and cell["navigability_index"]
                - cell["river_navigability_index"]
                > 0.05
                and cell["river_navigability_index"] < 0.50
            )
            waterway = world["navigable_waterways"][
                navigable_cell["navigable_waterway_id"]
            ]
            river_delta = 0.01
            original_river = navigable_cell["river_navigability_index"]
            original_summary_river = summary["mean_river_navigability_index"]
            original_waterway_river = waterway[
                "mean_river_navigability_index"
            ]
            navigable_cell["river_navigability_index"] += river_delta
            summary["mean_river_navigability_index"] += (
                river_delta / len(world["cells"])
            )
            waterway["mean_river_navigability_index"] += (
                river_delta / waterway["cell_count"]
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "navigability model or causal replay invalid",
                invalid_result.output,
            )
            navigable_cell["river_navigability_index"] = original_river
            summary["mean_river_navigability_index"] = original_summary_river
            waterway["mean_river_navigability_index"] = original_waterway_river

            original_waterway_type = waterway["waterway_type"]
            waterway["waterway_type"] = (
                "coastal_corridor"
                if original_waterway_type != "coastal_corridor"
                else "river_corridor"
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "navigability model or causal replay invalid",
                invalid_result.output,
            )
            waterway["waterway_type"] = original_waterway_type

            navigability_model["navigable_threshold"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "navigability model or causal replay invalid",
                invalid_result.output,
            )
            navigability_model["navigable_threshold"] -= 0.01

            port_site = world["port_sites"][0]
            port_cell = world["cells"][port_site["cell_id"]]
            port_delta = 0.01
            original_cell_bay = port_cell["protected_bay_index"]
            original_record_bay = port_site["protected_bay_index"]
            original_summary_bay = summary["mean_protected_bay_index"]
            port_cell["protected_bay_index"] += port_delta
            port_site["protected_bay_index"] += port_delta
            summary["mean_protected_bay_index"] += port_delta / len(
                world["cells"]
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "port site model or causal replay invalid",
                invalid_result.output,
            )
            port_cell["protected_bay_index"] = original_cell_bay
            port_site["protected_bay_index"] = original_record_bay
            summary["mean_protected_bay_index"] = original_summary_bay

            original_port_threshold = port_model["port_site_threshold"]
            port_model["port_site_threshold"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "port site model or causal replay invalid",
                invalid_result.output,
            )
            port_model["port_site_threshold"] = original_port_threshold

            non_corridor_cell = next(
                cell
                for cell in world["cells"]
                if cell["route_corridor_id"] < 0
            )
            route_feature_delta = 0.01
            original_mountain_feature = non_corridor_cell[
                "mountain_pass_route_index"
            ]
            original_summary_mountain = summary[
                "mean_mountain_pass_route_index"
            ]
            non_corridor_cell[
                "mountain_pass_route_index"
            ] += route_feature_delta
            summary["mean_mountain_pass_route_index"] += (
                route_feature_delta / len(world["cells"])
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "route corridor model or causal replay invalid",
                invalid_result.output,
            )
            non_corridor_cell[
                "mountain_pass_route_index"
            ] = original_mountain_feature
            summary[
                "mean_mountain_pass_route_index"
            ] = original_summary_mountain

            original_route_threshold = route_model["feature_threshold"]
            route_model["feature_threshold"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "route corridor model or causal replay invalid",
                invalid_result.output,
            )
            route_model["feature_threshold"] = original_route_threshold

    def test_settlement_selection_and_route_network_causal_replay_mutations(
        self,
    ) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 256
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        # Keep this causal-replay fixture above the two-settlement threshold.
        # Earth calibration is covered independently by the canonical matrix.
        data["climate"]["lapse_rate_c_per_km"] = 2.0
        world = generate_world(type(config).model_validate(data))
        settlement_model = world["settlement_selection_model"]
        route_model = world["route_network_model"]

        self.assertEqual(
            settlement_model["model_type"],
            "causal_native_score_local_max_separated_settlement_selection_v1",
        )
        self.assertEqual(settlement_model["selection_score_precision"], 8)
        self.assertEqual(
            route_model["model_type"],
            "causal_endpoint_barrier_ranked_route_network_v1",
        )
        self.assertTrue(world["settlements"])
        self.assertTrue(world["routes"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            settlement_cell_ids = {
                settlement["cell_id"] for settlement in world["settlements"]
            }
            score_cell = next(
                cell
                for cell in world["cells"]
                if cell["id"] not in settlement_cell_ids
                and not cell["is_water"]
                and cell["port_site_id"] < 0
                and cell["settlement_score"] < 0.40
            )
            original_score = score_cell["settlement_score"]
            score_cell["settlement_score"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "settlement selection model or causal replay invalid",
                invalid_result.output,
            )
            score_cell["settlement_score"] = original_score

            non_port_settlement = next(
                settlement
                for settlement in world["settlements"]
                if settlement["type"] != "port"
            )
            original_settlement_type = non_port_settlement["type"]
            non_port_settlement["type"] = (
                "frontier_town"
                if original_settlement_type != "frontier_town"
                else "agricultural_town"
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "settlement selection model or causal replay invalid",
                invalid_result.output,
            )
            non_port_settlement["type"] = original_settlement_type

            original_score_threshold = settlement_model["score_threshold"]
            settlement_model["score_threshold"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "settlement selection model or causal replay invalid",
                invalid_result.output,
            )
            settlement_model["score_threshold"] = original_score_threshold

            route = world["routes"][0]
            original_route_cost = route["cost"]
            route["cost"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "route network model or causal replay invalid",
                invalid_result.output,
            )
            route["cost"] = original_route_cost

            barrier_parameters = route_model["barrier_parameters"]
            original_mountain_weight = barrier_parameters["mountain_weight"]
            barrier_parameters["mountain_weight"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "route network model or causal replay invalid",
                invalid_result.output,
            )
            barrier_parameters["mountain_weight"] = original_mountain_weight

    def test_political_region_border_and_trade_flow_causal_replay_mutations(
        self,
    ) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        region_model = world["political_region_model"]
        border_model = world["political_border_model"]
        trade_model = world["trade_flow_model"]

        self.assertEqual(
            region_model["model_type"],
            "causal_capital_barrier_partition_political_regions_v1",
        )
        self.assertEqual(
            border_model["model_type"],
            "causal_adjacent_region_terrain_border_segments_v1",
        )
        self.assertEqual(
            trade_model["model_type"],
            "causal_route_endpoint_complement_trade_flows_v1",
        )
        self.assertTrue(world["political_regions"])
        self.assertTrue(world["borders"])
        self.assertTrue(world["trade_flows"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            capital_ids = {
                region["capital_settlement_id"]
                for region in world["political_regions"]
            }
            noncapital = next(
                settlement
                for settlement in world["settlements"]
                if settlement["id"] not in capital_ids
            )
            original_region_id = noncapital["region_id"]
            noncapital["region_id"] = (
                original_region_id + 1
            ) % len(world["political_regions"])
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "political region model or causal replay invalid",
                invalid_result.output,
            )
            noncapital["region_id"] = original_region_id

            region = world["political_regions"][0]
            original_region_type = region["type"]
            region["type"] = (
                "frontier_territory"
                if original_region_type != "frontier_territory"
                else "agrarian_state"
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "political region model or causal replay invalid",
                invalid_result.output,
            )
            region["type"] = original_region_type

            original_capital_separation = region_model[
                "capital_minimum_angular_separation_rad"
            ]
            region_model["capital_minimum_angular_separation_rad"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "political region model or causal replay invalid",
                invalid_result.output,
            )
            region_model[
                "capital_minimum_angular_separation_rad"
            ] = original_capital_separation

            border = world["borders"][0]
            original_border_score = border["barrier_score"]
            border["barrier_score"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "political border model or causal replay invalid",
                invalid_result.output,
            )
            border["barrier_score"] = original_border_score

            border_parameters = border_model["barrier_parameters"]
            original_hard_bonus = border_parameters["hard_type_bonus"]
            border_parameters["hard_type_bonus"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "political border model or causal replay invalid",
                invalid_result.output,
            )
            border_parameters["hard_type_bonus"] = original_hard_bonus

            trade_flow = next(
                flow for flow in world["trade_flows"] if flow["volume_index"] < 99.0
            )
            original_trade_volume = trade_flow["volume_index"]
            trade_flow["volume_index"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "trade flow model or causal replay invalid",
                invalid_result.output,
            )
            trade_flow["volume_index"] = original_trade_volume

            volume_parameters = trade_model["volume_parameters"]
            original_region_bonus = volume_parameters["interregional_bonus"]
            volume_parameters["interregional_bonus"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "trade flow model or causal replay invalid",
                invalid_result.output,
            )
            volume_parameters["interregional_bonus"] = original_region_bonus

    def test_land_use_frontier_and_worldbuilding_causal_replay_mutations(
        self,
    ) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        land_use_model = world["land_use_zone_model"]
        frontier_model = world["natural_frontier_model"]
        realism_model = world["worldbuilding_realism_model"]

        self.assertEqual(
            land_use_model["model_type"],
            "causal_soil_climate_resource_connected_land_use_zones_v1",
        )
        self.assertEqual(
            frontier_model["model_type"],
            "causal_border_terrain_connected_natural_frontiers_v1",
        )
        self.assertEqual(
            realism_model["model_type"],
            "causal_upstream_evidence_worldbuilding_realism_checks_v1",
        )
        self.assertTrue(world["agricultural_zones"])
        self.assertTrue(world["mining_zones"])
        self.assertTrue(world["natural_frontiers"])
        self.assertEqual(len(world["worldbuilding_realism_checks"]), 5)

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            low_potential_cell = next(
                cell
                for cell in world["cells"]
                if not cell["is_water"]
                and cell["agricultural_potential_index"] < 0.50
            )
            original_potential = low_potential_cell["agricultural_potential_index"]
            original_mean = world["summary"]["mean_agricultural_potential_index"]
            low_potential_cell["agricultural_potential_index"] += 0.01
            world["summary"]["mean_agricultural_potential_index"] += 0.01 / len(
                world["cells"]
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "land use zone model or causal replay invalid",
                invalid_result.output,
            )
            low_potential_cell["agricultural_potential_index"] = original_potential
            world["summary"]["mean_agricultural_potential_index"] = original_mean

            agricultural_zone = world["agricultural_zones"][0]
            original_dominant_biome = agricultural_zone["dominant_biome"]
            agricultural_zone["dominant_biome"] = "unsupported_biome"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "land use zone model or causal replay invalid",
                invalid_result.output,
            )
            agricultural_zone["dominant_biome"] = original_dominant_biome

            original_agricultural_threshold = land_use_model[
                "agricultural_threshold"
            ]
            land_use_model["agricultural_threshold"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "land use zone model or causal replay invalid",
                invalid_result.output,
            )
            land_use_model[
                "agricultural_threshold"
            ] = original_agricultural_threshold

            frontier = world["natural_frontiers"][0]
            original_frontier_landform = frontier["dominant_landform"]
            frontier["dominant_landform"] = "unsupported_landform"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "natural frontier model or causal replay invalid",
                invalid_result.output,
            )
            frontier["dominant_landform"] = original_frontier_landform

            frontier_parameters = frontier_model["frontier_index_parameters"]
            original_border_weight = frontier_parameters["border_weight"]
            frontier_parameters["border_weight"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "natural frontier model or causal replay invalid",
                invalid_result.output,
            )
            frontier_parameters["border_weight"] = original_border_weight

            realism_check = world["worldbuilding_realism_checks"][0]
            evidence = realism_check["evidence"]
            original_top_count = evidence["top_settlement_count"]
            evidence["top_settlement_count"] += 1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "worldbuilding realism model or causal replay invalid",
                invalid_result.output,
            )
            evidence["top_settlement_count"] = original_top_count

            original_water_threshold = realism_model[
                "water_access_runoff_threshold_mm_y"
            ]
            realism_model["water_access_runoff_threshold_mm_y"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "worldbuilding realism model or causal replay invalid",
                invalid_result.output,
            )
            realism_model[
                "water_access_runoff_threshold_mm_y"
            ] = original_water_threshold

    def test_culture_language_and_site_causal_replay_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        culture_model = world["culture_region_model"]
        language_model = world["language_region_model"]
        site_model = world["cultural_site_model"]

        self.assertEqual(
            culture_model["model_type"],
            "causal_political_homeland_barrier_trade_culture_regions_v1",
        )
        self.assertEqual(
            language_model["model_type"],
            "causal_trade_union_family_lineage_phonology_v1",
        )
        self.assertEqual(
            site_model["model_type"],
            "causal_terrain_culture_ranked_sacred_ruin_sites_v1",
        )
        self.assertTrue(world["cultures"])
        self.assertTrue(world["language_regions"])
        self.assertTrue(world["sacred_areas"])
        self.assertTrue(world["ruins"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            culture = world["cultures"][0]
            original_culture_type = culture["type"]
            culture["type"] = (
                "agrarian_lowland"
                if original_culture_type != "agrarian_lowland"
                else "river_valley"
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "cultural geography model or causal replay invalid",
                invalid_result.output,
            )
            culture["type"] = original_culture_type

            language = world["language_regions"][0]
            original_inventory = language["phoneme_inventory_size"]
            language["phoneme_inventory_size"] += 1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "cultural geography model or causal replay invalid",
                invalid_result.output,
            )
            language["phoneme_inventory_size"] = original_inventory

            sacred_area = world["sacred_areas"][0]
            original_sacred_type = sacred_area["type"]
            sacred_area["type"] = (
                "sacred_grove"
                if original_sacred_type != "sacred_grove"
                else "mountain_shrine"
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "cultural geography model or causal replay invalid",
                invalid_result.output,
            )
            sacred_area["type"] = original_sacred_type

            ruin = world["ruins"][0]
            original_abandonment = ruin["abandonment_reason"]
            ruin["abandonment_reason"] = (
                "frontier_isolation"
                if original_abandonment != "frontier_isolation"
                else "trade_decline"
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "cultural geography model or causal replay invalid",
                invalid_result.output,
            )
            ruin["abandonment_reason"] = original_abandonment

            original_union_threshold = language_model["union_volume_threshold"]
            language_model["union_volume_threshold"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "cultural geography model or causal replay invalid",
                invalid_result.output,
            )
            language_model["union_volume_threshold"] = original_union_threshold

            original_site_threshold = site_model["sacred_candidate_threshold"]
            site_model["sacred_candidate_threshold"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "cultural geography model or causal replay invalid",
                invalid_result.output,
            )
            site_model["sacred_candidate_threshold"] = original_site_threshold

    def test_historical_geography_causal_replay_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        model = world["historical_event_model"]

        self.assertEqual(
            model["model_type"],
            "causal_region_culture_language_trade_site_timeline_v1",
        )
        self.assertEqual(len(world["historical_eras"]), 4)
        self.assertTrue(world["historical_events"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            event = world["historical_events"][0]
            original_year = event["year_bp"]
            event["year_bp"] += 2.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "historical geography model or causal replay invalid",
                invalid_result.output,
            )
            event["year_bp"] = original_year

            original_cell_id = event["cell_id"]
            event["cell_id"] = original_cell_id + 1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "historical geography model or causal replay invalid",
                invalid_result.output,
            )
            event["cell_id"] = original_cell_id

            era = world["historical_eras"][0]
            original_instability = era["mean_instability"]
            era["mean_instability"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "historical geography model or causal replay invalid",
                invalid_result.output,
            )
            era["mean_instability"] = original_instability

            parameters = model["dynastic_change_parameters"]
            original_threshold = parameters["pressure_threshold"]
            parameters["pressure_threshold"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "historical geography model or causal replay invalid",
                invalid_result.output,
            )
            parameters["pressure_threshold"] = original_threshold

    def test_population_and_conflict_causal_replay_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        population_model = world["population_region_model"]
        conflict_model = world["conflict_model"]
        dynasty_model = world["dynasty_model"]

        self.assertEqual(
            population_model["model_type"],
            "causal_area_weighted_capacity_occupancy_population_regions_v1",
        )
        self.assertEqual(
            conflict_model["model_type"],
            "causal_border_pair_pressure_trade_conflict_selection_v1",
        )
        self.assertEqual(
            dynasty_model["model_type"],
            "causal_foundation_continuity_pressure_dynasty_lineages_v1",
        )
        self.assertTrue(world["population_regions"])
        self.assertTrue(world["conflicts"])
        self.assertTrue(world["dynasties"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            population = world["population_regions"][0]
            original_population = population["estimated_population"]
            population["estimated_population"] *= 1.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population, conflict, or dynasty model causal replay invalid",
                invalid_result.output,
            )
            population["estimated_population"] = original_population

            original_water_security = population["water_security_index"]
            population["water_security_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population, conflict, or dynasty model causal replay invalid",
                invalid_result.output,
            )
            population["water_security_index"] = original_water_security

            conflict = world["conflicts"][0]
            original_contested_cell = conflict["contested_cell_id"]
            conflict["contested_cell_id"] = original_contested_cell + 1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population, conflict, or dynasty model causal replay invalid",
                invalid_result.output,
            )
            conflict["contested_cell_id"] = original_contested_cell

            original_outcome = conflict["outcome"]
            conflict["outcome"] = (
                "stalemate" if original_outcome != "stalemate" else "exhaustion"
            )
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population, conflict, or dynasty model causal replay invalid",
                invalid_result.output,
            )
            conflict["outcome"] = original_outcome

            density_parameters = population_model["density_capacity_parameters"]
            original_density = density_parameters["base_people_per_km2"]
            density_parameters["base_people_per_km2"] += 0.1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population, conflict, or dynasty model causal replay invalid",
                invalid_result.output,
            )
            density_parameters["base_people_per_km2"] = original_density

            original_candidate_threshold = conflict_model["minimum_candidate_score"]
            conflict_model["minimum_candidate_score"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population, conflict, or dynasty model causal replay invalid",
                invalid_result.output,
            )
            conflict_model["minimum_candidate_score"] = original_candidate_threshold

            dynasty = world["dynasties"][0]
            original_succession_pressure = dynasty["succession_pressure"]
            dynasty["succession_pressure"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population, conflict, or dynasty model causal replay invalid",
                invalid_result.output,
            )
            dynasty["succession_pressure"] = original_succession_pressure

            original_dynasty_thresholds = dynasty_model["dynasty_count_thresholds"][:]
            dynasty_model["dynasty_count_thresholds"][0] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population, conflict, or dynasty model causal replay invalid",
                invalid_result.output,
            )
            dynasty_model["dynasty_count_thresholds"] = original_dynasty_thresholds

    def test_territorial_snapshot_causal_replay_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        model = world["territorial_snapshot_model"]

        self.assertEqual(
            model["model_type"],
            "causal_era_scaled_spherical_region_territorial_snapshots_v1",
        )
        self.assertEqual(len(world["territorial_snapshots"]), 4)
        self.assertTrue(world["territorial_snapshots"][0]["regions"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            snapshot = world["territorial_snapshots"][0]
            region = snapshot["regions"][0]
            original_boundary_cell = region["boundary_cell_ids"][0]
            region["boundary_cell_ids"][0] = original_boundary_cell + 1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "territorial snapshot model or causal replay invalid",
                invalid_result.output,
            )
            region["boundary_cell_ids"][0] = original_boundary_cell

            original_ring_latitude = region["boundary_ring"][0][0]
            region["boundary_ring"][0][0] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "territorial snapshot model or causal replay invalid",
                invalid_result.output,
            )
            region["boundary_ring"][0][0] = original_ring_latitude

            original_dissolved_area = region["dissolved_polygon_area_km2"]
            region["dissolved_polygon_area_km2"] *= 1.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "territorial snapshot model or causal replay invalid",
                invalid_result.output,
            )
            region["dissolved_polygon_area_km2"] = original_dissolved_area

            original_fragmentation = snapshot["fragmentation_index"]
            snapshot["fragmentation_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "territorial snapshot model or causal replay invalid",
                invalid_result.output,
            )
            snapshot["fragmentation_index"] = original_fragmentation

            original_area_factors = model["era_area_factors"][:]
            model["era_area_factors"][0] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "territorial snapshot model or causal replay invalid",
                invalid_result.output,
            )
            model["era_area_factors"] = original_area_factors

    def test_population_and_economy_history_causal_replay_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        population_model = world["population_history_model"]
        economy_model = world["economy_history_model"]

        self.assertEqual(
            population_model["model_type"],
            "causal_era_snapshot_logistic_migration_conflict_population_history_v1",
        )
        self.assertEqual(
            economy_model["model_type"],
            "causal_population_trade_conflict_treasury_economy_history_v1",
        )
        self.assertTrue(world["population_histories"])
        self.assertTrue(world["economy_histories"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            population_step = world["population_histories"][0]["steps"][0]
            original_end_population = population_step["end_population"]
            population_step["end_population"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population or economy history model causal replay invalid",
                invalid_result.output,
            )
            population_step["end_population"] = original_end_population

            original_migration_delta = population_step["migration_delta"]
            population_step["migration_delta"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population or economy history model causal replay invalid",
                invalid_result.output,
            )
            population_step["migration_delta"] = original_migration_delta

            economy_step = world["economy_histories"][0]["steps"][0]
            original_gross_output = economy_step["gross_output_index"]
            economy_step["gross_output_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population or economy history model causal replay invalid",
                invalid_result.output,
            )
            economy_step["gross_output_index"] = original_gross_output

            original_treasury = economy_step["treasury_end_index"]
            economy_step["treasury_end_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population or economy history model causal replay invalid",
                invalid_result.output,
            )
            economy_step["treasury_end_index"] = original_treasury

            original_growth_model = population_model["growth_model"]
            population_model["growth_model"] = "unsupported_growth_model"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population or economy history model causal replay invalid",
                invalid_result.output,
            )
            population_model["growth_model"] = original_growth_model

            original_treasury_model = economy_model["treasury_model"]
            economy_model["treasury_model"] = "unsupported_treasury_model"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "population or economy history model causal replay invalid",
                invalid_result.output,
            )
            economy_model["treasury_model"] = original_treasury_model

    def test_demographic_agent_and_life_event_causal_replay_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        demographic_model = world["demographic_agent_model"]
        life_event_model = world["individual_life_event_model"]

        self.assertEqual(
            demographic_model["model_type"],
            "causal_population_economy_logistics_household_firm_demographic_history_v1",
        )
        self.assertEqual(
            life_event_model["model_type"],
            "causal_household_firm_era_sampled_individual_life_event_graph_v1",
        )
        self.assertTrue(world["household_cohorts"])
        self.assertTrue(world["firm_agents"])
        self.assertTrue(world["demographic_agent_histories"])
        self.assertTrue(world["individual_agents"])
        self.assertTrue(world["individual_life_events"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            household = world["household_cohorts"][0]
            original_vulnerability = household["vulnerability_index"]
            household["vulnerability_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "demographic agent or individual life-event causal replay invalid",
                invalid_result.output,
            )
            household["vulnerability_index"] = original_vulnerability

            firm = world["firm_agents"][0]
            original_employment = firm["employment_capacity"]
            firm["employment_capacity"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "demographic agent or individual life-event causal replay invalid",
                invalid_result.output,
            )
            firm["employment_capacity"] = original_employment

            demographic_step = world["demographic_agent_histories"][0]["steps"][0]
            original_working_population = demographic_step["working_population"]
            demographic_step["working_population"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "demographic agent or individual life-event causal replay invalid",
                invalid_result.output,
            )
            demographic_step["working_population"] = original_working_population

            person = world["individual_agents"][0]
            original_name = person["name"]
            person["name"] = f"{original_name}x"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "demographic agent or individual life-event causal replay invalid",
                invalid_result.output,
            )
            person["name"] = original_name

            event = world["individual_life_events"][0]
            original_event_year = event["year_bp"]
            event["year_bp"] += 1.0
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "demographic agent or individual life-event causal replay invalid",
                invalid_result.output,
            )
            event["year_bp"] = original_event_year

            original_household_model = demographic_model["household_model"]
            demographic_model["household_model"] = "unsupported_household_model"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "demographic agent or individual life-event causal replay invalid",
                invalid_result.output,
            )
            demographic_model["household_model"] = original_household_model

            original_sampling_model = life_event_model["sampling_model"]
            life_event_model["sampling_model"] = "unsupported_sampling_model"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "demographic agent or individual life-event causal replay invalid",
                invalid_result.output,
            )
            life_event_model["sampling_model"] = original_sampling_model

    def test_ruler_genealogy_causal_replay_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        model = world["ruler_genealogy_model"]

        self.assertEqual(
            model["model_type"],
            "causal_dynasty_economy_conflict_named_ruler_alliance_cadet_genealogy_v1",
        )
        self.assertTrue(world["rulers"])
        self.assertTrue(world["marriage_alliances"])
        self.assertTrue(world["cadet_branches"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            ruler = world["rulers"][0]
            original_legitimacy = ruler["legitimacy_index"]
            ruler["legitimacy_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "ruler genealogy model or causal replay invalid",
                invalid_result.output,
            )
            ruler["legitimacy_index"] = original_legitimacy

            alliance = world["marriage_alliances"][0]
            original_alliance_strength = alliance["alliance_strength"]
            alliance["alliance_strength"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "ruler genealogy model or causal replay invalid",
                invalid_result.output,
            )
            alliance["alliance_strength"] = original_alliance_strength

            branch = world["cadet_branches"][0]
            original_claim_strength = branch["claim_strength"]
            branch["claim_strength"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "ruler genealogy model or causal replay invalid",
                invalid_result.output,
            )
            branch["claim_strength"] = original_claim_strength

            dynasty = world["dynasties"][0]
            original_founder = dynasty["founder_ruler_id"]
            dynasty["founder_ruler_id"] = original_founder + 1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "ruler genealogy model or causal replay invalid",
                invalid_result.output,
            )
            dynasty["founder_ruler_id"] = original_founder

            original_reign_model = model["reign_model"]
            model["reign_model"] = "unsupported_reign_model"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "ruler genealogy model or causal replay invalid",
                invalid_result.output,
            )
            model["reign_model"] = original_reign_model

    def test_logistics_exchange_and_campaign_causal_replay_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        logistics_model = world["logistics_exchange_model"]
        campaign_model = world["campaign_operations_model"]

        self.assertEqual(
            logistics_model["model_type"],
            "causal_region_route_trade_economy_logistics_exchange_v1",
        )
        self.assertEqual(
            campaign_model["model_type"],
            "causal_conflict_cell_path_front_tactical_strategic_campaign_operations_v1",
        )
        self.assertTrue(world["logistics_networks"])
        self.assertTrue(world["market_exchanges"])
        self.assertTrue(world["campaign_movements"])
        self.assertTrue(world["campaign_path_segments"])
        self.assertTrue(world["campaign_front_histories"])
        self.assertTrue(world["tactical_engagements"])
        self.assertTrue(world["strategic_campaign_plans"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            network = world["logistics_networks"][0]
            original_efficiency = network["transport_efficiency_index"]
            network["transport_efficiency_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "logistics exchange model or causal replay invalid",
                invalid_result.output,
            )
            network["transport_efficiency_index"] = original_efficiency

            exchange = world["market_exchanges"][0]
            original_market_access = exchange["market_access_index"]
            exchange["market_access_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "logistics exchange model or causal replay invalid",
                invalid_result.output,
            )
            exchange["market_access_index"] = original_market_access

            segment = world["campaign_path_segments"][0]
            original_segment_attrition = segment["attrition_index"]
            segment["attrition_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "campaign operations model or causal replay invalid",
                invalid_result.output,
            )
            segment["attrition_index"] = original_segment_attrition

            front_step = world["campaign_front_histories"][0]["steps"][0]
            original_supply_integrity = front_step["supply_integrity_index"]
            front_step["supply_integrity_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "campaign operations model or causal replay invalid",
                invalid_result.output,
            )
            front_step["supply_integrity_index"] = original_supply_integrity

            tactical_step = world["tactical_engagements"][0]["steps"][0]
            original_counter = tactical_step["counter_maneuver_index"]
            tactical_step["counter_maneuver_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "campaign operations model or causal replay invalid",
                invalid_result.output,
            )
            tactical_step["counter_maneuver_index"] = original_counter

            strategic_plan = world["strategic_campaign_plans"][0]
            original_reserve = strategic_plan["reserve_fraction"]
            strategic_plan["reserve_fraction"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "campaign operations model or causal replay invalid",
                invalid_result.output,
            )
            strategic_plan["reserve_fraction"] = original_reserve

            original_network_model = logistics_model["network_model"]
            logistics_model["network_model"] = "unsupported_network_model"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "logistics exchange model or causal replay invalid",
                invalid_result.output,
            )
            logistics_model["network_model"] = original_network_model

            original_path_model = campaign_model["path_model"]
            campaign_model["path_model"] = "unsupported_path_model"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "campaign operations model or causal replay invalid",
                invalid_result.output,
            )
            campaign_model["path_model"] = original_path_model

    def test_market_clearing_causal_replay_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        model = world["market_clearing_model"]

        self.assertEqual(
            model["model_type"],
            "causal_route_capacity_agent_orders_price_iteration_inventory_learning_market_clearing_v1",
        )
        self.assertTrue(world["route_capacity_constraints"])
        self.assertTrue(world["market_clearing_records"])
        self.assertTrue(world["market_agent_orders"])
        self.assertTrue(world["market_price_iterations"])
        self.assertTrue(world["market_inventory_histories"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            constraint = world["route_capacity_constraints"][0]
            original_capacity = constraint["capacity_volume_index"]
            constraint["capacity_volume_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "market clearing model or causal replay invalid",
                invalid_result.output,
            )
            constraint["capacity_volume_index"] = original_capacity

            clearing = world["market_clearing_records"][0]
            original_price = clearing["equilibrium_price_index"]
            clearing["equilibrium_price_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "market clearing model or causal replay invalid",
                invalid_result.output,
            )
            clearing["equilibrium_price_index"] = original_price

            order = world["market_agent_orders"][0]
            original_order_volume = order["requested_volume_index"]
            order["requested_volume_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "market clearing model or causal replay invalid",
                invalid_result.output,
            )
            order["requested_volume_index"] = original_order_volume

            iteration = world["market_price_iterations"][0]
            original_imbalance = iteration["imbalance_index"]
            iteration["imbalance_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "market clearing model or causal replay invalid",
                invalid_result.output,
            )
            iteration["imbalance_index"] = original_imbalance

            inventory_step = world["market_inventory_histories"][0]["steps"][0]
            original_learning_rate = inventory_step["learning_rate_index"]
            inventory_step["learning_rate_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "market clearing model or causal replay invalid",
                invalid_result.output,
            )
            inventory_step["learning_rate_index"] = original_learning_rate

            route = world["routes"][constraint["route_id"]]
            original_constraint_id = route["route_capacity_constraint_id"]
            route["route_capacity_constraint_id"] = original_constraint_id + 1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "market clearing model or causal replay invalid",
                invalid_result.output,
            )
            route["route_capacity_constraint_id"] = original_constraint_id

            original_inventory_model = model["inventory_model"]
            model["inventory_model"] = "unsupported_inventory_model"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "market clearing model or causal replay invalid",
                invalid_result.output,
            )
            model["inventory_model"] = original_inventory_model

    def test_phonology_history_causal_replay_mutations(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        world = generate_world(type(config).model_validate(data))
        model = world["phonology_history_model"]

        self.assertEqual(
            model["model_type"],
            "causal_language_era_sound_rule_lexical_diffusion_speaker_history_v1",
        )
        self.assertTrue(world["phonological_rules"])
        self.assertTrue(world["phonological_histories"])
        self.assertTrue(world["lexical_correspondences"])
        self.assertTrue(world["lexical_diffusion_histories"])
        self.assertTrue(world["speaker_population_histories"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            runner = CliRunner()

            def validate_current() -> object:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            valid_result = validate_current()
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            rule = world["phonological_rules"][0]
            original_probability = rule["probability_index"]
            rule["probability_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "phonology history model or causal replay invalid",
                invalid_result.output,
            )
            rule["probability_index"] = original_probability

            history_step = world["phonological_histories"][0]["steps"][0]
            original_inventory = history_step["inventory_size"]
            history_step["inventory_size"] += 1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "phonology history model or causal replay invalid",
                invalid_result.output,
            )
            history_step["inventory_size"] = original_inventory

            correspondence = world["lexical_correspondences"][0]
            original_form = correspondence["derived_form"]
            correspondence["derived_form"] = f"{original_form}a"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "phonology history model or causal replay invalid",
                invalid_result.output,
            )
            correspondence["derived_form"] = original_form

            diffusion_step = world["lexical_diffusion_histories"][0]["steps"][0]
            original_adoption = diffusion_step["adoption_fraction"]
            diffusion_step["adoption_fraction"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "phonology history model or causal replay invalid",
                invalid_result.output,
            )
            diffusion_step["adoption_fraction"] = original_adoption

            speaker_step = world["speaker_population_histories"][0]["steps"][0]
            original_allophony = speaker_step["allophonic_variation_index"]
            speaker_step["allophonic_variation_index"] += 0.01
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "phonology history model or causal replay invalid",
                invalid_result.output,
            )
            speaker_step["allophonic_variation_index"] = original_allophony

            language = world["language_regions"][0]
            original_history_id = language["phonological_history_id"]
            language["phonological_history_id"] = original_history_id + 1
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "phonology history model or causal replay invalid",
                invalid_result.output,
            )
            language["phonological_history_id"] = original_history_id

            original_rule_model = model["rule_model"]
            model["rule_model"] = "unsupported_rule_model"
            invalid_result = validate_current()
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "phonology history model or causal replay invalid",
                invalid_result.output,
            )
            model["rule_model"] = original_rule_model

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
                for event in world["numeric_depression_fill_history"]
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
                for event in world["numeric_depression_fill_history"]
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

    def test_disabled_depression_preservation_keeps_geologic_evidence(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["hydrology"]["preserve_geologic_depressions"] = False
        routed_config = type(config).model_validate(data)

        world = generate_world(routed_config)
        fill_history = world["numeric_depression_fill_history"]
        self.assertTrue(fill_history)
        self.assertTrue(world["lake_basins"])
        self.assertEqual(world["summary"]["preserved_geologic_depression_count"], 0)
        self.assertEqual(world["summary"]["corrected_numeric_depression_count"], 0)
        self.assertEqual(
            world["summary"]["temporary_numeric_lake_depression_count"],
            len(world["lake_basins"]),
        )
        self.assertTrue(any(event["sink_is_geologic"] for event in fill_history))
        for event in fill_history:
            expected_geologic = (
                event["sink_crust_type"] in {"rift_basin", "sedimentary_basin"}
                or event["sink_boundary_divergent"] > 0.28
                or event["sink_boundary_convergent"] > 0.42
            )
            self.assertEqual(event["sink_is_geologic"], expected_geologic)
            self.assertEqual(event["source_depression_policy"], "corrected_numeric")
        self.assertTrue(
            all(
                basin["depression_policy"] == "temporary_numeric_lake"
                for basin in world["lake_basins"]
            )
        )

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            runner = CliRunner()
            result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertEqual(result.exit_code, 0, result.output)

            first_event = fill_history[0]
            first_event["fill_depth_m_by_cell"][0] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(
                app, ["validate", "--world", str(world_path)]
            )
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "numeric depression correction provenance invalid",
                invalid_result.output,
            )
            first_event["fill_depth_m_by_cell"][0] -= 1.0

            first_event["breach_target_elevation_m_by_cell"][1] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(
                app, ["validate", "--world", str(world_path)]
            )
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "numeric depression correction provenance invalid",
                invalid_result.output,
            )
            first_event["breach_target_elevation_m_by_cell"][1] -= 1.0

            original_correction_method = first_event["selected_correction_method"]
            first_event["selected_correction_method"] = "breach"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(
                app, ["validate", "--world", str(world_path)]
            )
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "numeric depression correction provenance invalid",
                invalid_result.output,
            )
            first_event["selected_correction_method"] = original_correction_method

            first_event["temporary_numeric_lake_selected"] = not first_event[
                "temporary_numeric_lake_selected"
            ]
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(
                app, ["validate", "--world", str(world_path)]
            )
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "numeric depression correction provenance invalid",
                invalid_result.output,
            )
            first_event["temporary_numeric_lake_selected"] = not first_event[
                "temporary_numeric_lake_selected"
            ]

            world["numeric_depression_fill_history"] = None
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(
                app, ["validate", "--world", str(world_path)]
            )
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "numeric depression correction provenance invalid",
                invalid_result.output,
            )
            world["numeric_depression_fill_history"] = fill_history

            filled_cell = world["cells"][first_event["cell_ids"][0]]
            filled_cell["cumulative_numeric_depression_fill_m"] += 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(
                app, ["validate", "--world", str(world_path)]
            )
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "numeric depression correction provenance invalid",
                invalid_result.output,
            )
            filled_cell["cumulative_numeric_depression_fill_m"] -= 1.0

            deferred_event = next(
                event
                for event in fill_history
                if event["selected_correction_method"] == "temporary_numeric_lake"
            )
            deferred_cell = world["cells"][deferred_event["cell_ids"][0]]
            deferred_cell["numeric_depression_temporary_lake_event_count"] += 1
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(
                app, ["validate", "--world", str(world_path)]
            )
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "numeric depression correction provenance invalid",
                invalid_result.output,
            )
            deferred_cell["numeric_depression_temporary_lake_event_count"] -= 1

            selected_event = next(
                (
                    event
                    for event in fill_history
                    if event["selected_correction_method"]
                    == "mass_conserving_breach"
                ),
                None,
            )
            if selected_event is not None:
                selected_event["breach_deposition_depth_m_by_cell"][0] += 1.0
                world_path.write_text(json.dumps(world), encoding="utf-8")
                invalid_result = runner.invoke(
                    app, ["validate", "--world", str(world_path)]
                )
                self.assertNotEqual(invalid_result.exit_code, 0)
                self.assertIn(
                    "numeric depression correction provenance invalid",
                    invalid_result.output,
                )
                selected_event["breach_deposition_depth_m_by_cell"][0] -= 1.0

                excavated_index = next(
                    index
                    for index, depth in enumerate(
                        selected_event["breach_excavation_depth_m_by_cell"]
                    )
                    if depth > 1.0e-9
                )
                excavated_cell = world["cells"][
                    selected_event["breach_path_cell_ids"][excavated_index]
                ]
                excavated_cell[
                    "cumulative_numeric_depression_breach_excavation_m"
                ] += 1.0
                world_path.write_text(json.dumps(world), encoding="utf-8")
                invalid_result = runner.invoke(
                    app, ["validate", "--world", str(world_path)]
                )
                self.assertNotEqual(invalid_result.exit_code, 0)
                self.assertIn(
                    "numeric depression correction provenance invalid",
                    invalid_result.output,
                )
                excavated_cell[
                    "cumulative_numeric_depression_breach_excavation_m"
                ] -= 1.0

    def test_small_generation_smoke(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 256
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 2
        small = type(config).model_validate(data)

        world = generate_world(small)
        summary = world["summary"]

        climate_model = world["climate_model"]
        self.assertEqual(
            climate_model["model_type"],
            "equilibrium_latitude_circulation_climate_v4",
        )
        self.assertEqual(climate_model["marine_annual_temperature_offset_c"], 0.0)
        self.assertTrue(climate_model["latitude_temperature_area_normalized"])
        self.assertTrue(climate_model["local_temperature_adjustments_area_centered"])
        self.assertFalse(climate_model["mass_conserving_atmosphere"])
        self.assertFalse(climate_model["transient_climate_resolved"])
        self.assertAlmostEqual(
            climate_model["latitude_temperature_area_mean_offset_c"],
            climate_model["latitude_temperature_gradient_c"]
            / (climate_model["latitude_temperature_exponent"] + 1.0),
            delta=0.00001,
        )
        self.assertEqual(climate_model["subtropical_drying_strength"], 0.65)
        self.assertEqual(climate_model["seasonal_monsoon_precipitation_strength"], 1.6)
        self.assertEqual(climate_model["thermal_moisture_capacity_factor"], 1.0)
        self.assertEqual(
            climate_model["thermal_moisture_capacity_temperature_anomaly_c"],
            0.0,
        )

        sea_level_model = world["sea_level_model"]
        self.assertEqual(
            sea_level_model["model_type"],
            "volume_constrained_connectivity_ocean_flood_v3",
        )
        self.assertEqual(sea_level_model["area_basis"], "native_cell_area_km2")
        self.assertEqual(
            sea_level_model["volume_basis"],
            "sum_native_cell_area_times_water_depth",
        )
        self.assertTrue(sea_level_model["ocean_connectivity_enforced"])
        self.assertTrue(sea_level_model["disconnected_below_sea_level_cells_remain_land"])
        self.assertEqual(sea_level_model["connected_ocean_component_count"], 1)
        self.assertEqual(
            sea_level_model["selected_ocean_cell_count"],
            sum(1 for cell in world["cells"] if cell["is_water"]),
        )
        total_surface_area = sum(cell["area_km2"] for cell in world["cells"])
        selected_ocean_area = sum(
            cell["area_km2"] for cell in world["cells"] if cell["is_water"]
        )
        selected_ocean_volume = sum(
            cell["area_km2"] * cell["water_depth_m"] / 1000.0
            for cell in world["cells"]
            if cell["is_water"]
        )
        self.assertAlmostEqual(
            sea_level_model["selected_ocean_area_km2"],
            selected_ocean_area,
            delta=max(0.001, selected_ocean_area * 0.000001),
        )
        self.assertAlmostEqual(
            sea_level_model["selected_ocean_fraction"],
            selected_ocean_area / total_surface_area,
            delta=0.000001,
        )
        self.assertAlmostEqual(
            sea_level_model["selected_ocean_volume_km3"],
            selected_ocean_volume,
            delta=max(0.001, selected_ocean_volume * 0.0000000001),
        )
        self.assertAlmostEqual(
            sea_level_model["selected_ocean_volume_km3"],
            small.planet.ocean_water_inventory_km3,
            delta=max(0.001, small.planet.ocean_water_inventory_km3 * 0.0000000001),
        )
        self.assertAlmostEqual(
            summary["ocean_volume_km3"],
            selected_ocean_volume,
            delta=max(0.001, selected_ocean_volume * 0.0000000001),
        )
        self.assertEqual(
            sea_level_model["below_sea_level_land_cell_count"],
            sum(
                1
                for cell in world["cells"]
                if not cell["is_water"] and cell["elevation_m"] < 0.0
            ),
        )

        clock = world["simulation_clock"]
        feedback_history = world["earth_system_feedback_history"]
        self.assertEqual(clock["clock_type"], "coupled_geodynamic_stage_clock_v12")
        self.assertEqual(clock["time_unit"], "model_step")
        self.assertFalse(clock["physical_time_resolved"])
        self.assertFalse(clock["nominal_time_calibrated"])
        self.assertFalse(clock["time_step_convergence_demonstrated"])
        self.assertEqual(clock["nominal_time_unit"], "Ma")
        self.assertEqual(clock["nominal_timestep_ma"], 5.0)
        self.assertEqual(clock["reference_timestep_ma"], 5.0)
        self.assertEqual(clock["maturation_timestep_scale"], 1.0)
        self.assertEqual(clock["final_nominal_elapsed_time_ma"], 10.0)
        self.assertEqual(
            clock["iteration_process_order"],
            "{plate_motion->crust_transport->crust_evolution->precommit_tendency_evaluation[tectonic_elevation+hillslope_sediment+stream_power_incision;prior_stabilized_surface_hydrology]->provisional_terrain_composition->fluvial_sediment_routing[prior_flow_graph+provisional_accommodation]->finite_alluvium_bedrock_inventory_and_terrain_commit->(sea_level->climate->causal_water_budget->hydrology->numeric_depression_correction)*until_stable}*configured_erosion_iterations->cryosphere_state->glacial_sediment_transport->finite_alluvium_bedrock_inventory_and_terrain_commit->(sea_level->climate->causal_water_budget->hydrology->numeric_depression_correction)*until_stable->cryosphere_state_recompute",
        )
        self.assertEqual(
            clock["erosion_transition_coupling_semantics"],
            "hillslope_and_stream_use_prior_stabilized_surface_and_hydrology_with_updated_crust_state;tectonic_hillslope_stream_tendencies_are_combined_before_terrain_commit;fluvial_routing_uses_prior_flow_graph_and_provisional_terrain_accommodation",
        )
        self.assertEqual(
            clock["legacy_mean_erosion_rate_field_semantics"],
            "mean_erosion_rate_m_per_step_is_a_reference_step_response_alias_not_applied_transition_depth",
        )
        self.assertEqual(clock["configured_erosion_iteration_count"], 2)
        self.assertEqual(clock["configured_cryosphere_coupling_stage_count"], 1)
        self.assertEqual(clock["cryosphere_coupling_stage_count"], 1)
        self.assertEqual(clock["feedback_recompute_count"], 3)
        self.assertEqual(clock["stage_count"], 4)
        self.assertEqual(clock["current_stage_id"], 3)
        self.assertEqual(clock["final_cryosphere_stage_id"], 3)
        self.assertEqual(len(feedback_history), 4)
        self.assertEqual(
            [step["stage"] for step in feedback_history],
            [
                "initial_climate_hydrology",
                "erosion_iteration",
                "erosion_iteration",
                "cryosphere_coupling",
            ],
        )
        self.assertEqual([step["id"] for step in feedback_history], list(range(4)))
        self.assertTrue(
            all(
                step["mean_erosion_rate_m_per_step"]
                == step["mean_stream_power_response_m_per_reference_step"]
                for step in feedback_history
            )
        )
        self.assertEqual(
            [step["erosion_iteration"] for step in feedback_history],
            [-1, 1, 2, -1],
        )
        erosion_steps = feedback_history[1:3]
        cryosphere_step = feedback_history[-1]
        self.assertTrue(all(step["erosion_applied"] and step["hydrology_recomputed"] for step in erosion_steps))
        self.assertTrue(all(step["climate_recomputed"] and step["sea_level_recomputed"] for step in erosion_steps))
        self.assertTrue(all(step["plate_motion_applied"] and step["crust_evolution_applied"] for step in erosion_steps))
        self.assertTrue(all(step["crust_transport_applied"] for step in erosion_steps))
        self.assertTrue(
            all(
                step["sea_level_recompute_count"]
                == step["climate_recompute_count"]
                == step["hydrologic_water_budget_recompute_count"]
                == step["hydrology_recompute_count"]
                == step["numeric_depression_fill_pass_count"] + 1
                for step in feedback_history
            )
        )
        self.assertTrue(
            all(
                abs(step["ocean_volume_km3"] - small.planet.ocean_water_inventory_km3)
                <= max(0.001, small.planet.ocean_water_inventory_km3 * 0.0000000001)
                for step in feedback_history
            )
        )
        self.assertEqual(
            [step["plate_motion_history_id"] for step in feedback_history],
            [0, 1, 2, 2],
        )
        self.assertTrue(all(step["mean_abs_elevation_change_m_from_previous_stage"] > 0.0 for step in erosion_steps))
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
        planet_radius_km = world["planet_parameters"]["radius_km"]
        for step in motion_history[1:]:
            max_rotation_arc_km = (
                math.radians(max(plate["step_rotation_deg"] for plate in step["plates"]))
                * planet_radius_km
            )
            self.assertLessEqual(
                step["max_crust_transport_distance_km"],
                max_rotation_arc_km + 0.01,
            )
        self.assertEqual(
            sum(step["crust_source_remap_cell_count"] for step in motion_history[1:]),
            summary["total_crust_source_remap_event_count"],
        )
        for step in motion_history[1:]:
            for total, transported, processed in zip(
                step["crust_age_change_ma_by_cell"],
                step["crust_age_transport_change_ma_by_cell"],
                step["crust_age_process_change_ma_by_cell"],
            ):
                self.assertAlmostEqual(total, transported + processed, delta=0.00001)
        self.assertEqual(
            summary["simulation_clock_stage_count"],
            len(feedback_history),
        )
        self.assertEqual(summary["simulation_clock_erosion_iteration_count"], len(erosion_steps))
        self.assertEqual(summary["simulation_clock_cryosphere_coupling_stage_count"], 1)
        self.assertAlmostEqual(
            summary["mean_erosion_iteration_elevation_change_m"],
            sum(step["mean_abs_elevation_change_m_from_previous_stage"] for step in erosion_steps) / len(erosion_steps),
            delta=0.01,
        )
        final_feedback = feedback_history[-1]
        self.assertTrue(final_feedback["sea_level_recomputed"])
        self.assertTrue(final_feedback["climate_recomputed"])
        self.assertTrue(final_feedback["hydrology_recomputed"])
        self.assertFalse(final_feedback["erosion_applied"])
        self.assertTrue(final_feedback["cryosphere_applied"])
        self.assertIs(final_feedback, cryosphere_step)
        self.assertAlmostEqual(
            final_feedback["mean_temperature_c"],
            sum(cell["temperature_c"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.01,
        )
        self.assertAlmostEqual(
            final_feedback["mean_precipitation_mm_y"],
            sum(cell["precipitation_mm_y"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.01,
        )
        self.assertAlmostEqual(
            summary["final_feedback_mean_abs_temperature_change_c"],
            final_feedback["mean_abs_temperature_change_c_from_previous_stage"],
            delta=0.01,
        )

        self.assertEqual(world["mesh_backend"], "fibonacci_sphere")
        self.assertEqual(summary["mesh_backend"], "fibonacci_sphere")
        self.assertEqual(summary["cell_count"], 256)
        self.assertEqual(len(world["cells"]), 256)
        self.assertGreaterEqual(summary["ocean_fraction"], 0.60)
        self.assertLessEqual(summary["ocean_fraction"], 0.80)
        self.assertGreaterEqual(summary["river_downhill_fraction"], 0.98)
        self.assertEqual(summary["plate_count"], 8)
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
            "initial_thermal_subsidence_m",
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
        relief_component_sum = sum(first_cell[key] for key in relief_component_keys)
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
        self.assertEqual(world["mesh_lod"]["index"], "cube_quadtree_v0")
        self.assertEqual(summary["mesh_lod_index"], "cube_quadtree_v0")
        self.assertGreaterEqual(summary["mesh_lod_max_level"], 1)
        self.assertEqual(summary["mesh_lod_level_count"], summary["mesh_lod_max_level"] + 1)
        self.assertEqual(summary["mesh_lod_tile_count"], len(world["mesh_lod"]["tiles"]))
        self.assertEqual(len(world["mesh_lod"]["level_summaries"]), summary["mesh_lod_level_count"])
        self.assertEqual(
            summary["mesh_lod_finest_tile_count"],
            world["mesh_lod"]["level_summaries"][-1]["occupied_tile_count"],
        )
        for level_summary in world["mesh_lod"]["level_summaries"]:
            level = level_summary["level"]
            level_tiles = [tile for tile in world["mesh_lod"]["tiles"] if tile["level"] == level]
            self.assertEqual(level_summary["occupied_tile_count"], len(level_tiles))
            self.assertEqual(level_summary["cell_count"], len(world["cells"]))
            self.assertGreater(level_summary["mean_cells_per_tile"], 0.0)
        lod_tiles_by_key = {
            (tile["level"], tile["tile_id"]): tile
            for tile in world["mesh_lod"]["tiles"]
        }
        for tile in world["mesh_lod"]["tiles"]:
            if tile["level"] == 0:
                self.assertEqual(tile["parent_tile_id"], -1)
            else:
                self.assertIn((tile["level"] - 1, tile["parent_tile_id"]), lod_tiles_by_key)
        child_counts: dict[tuple[int, int], int] = {}
        for tile in world["mesh_lod"]["tiles"]:
            if tile["level"] > 0:
                parent_key = (tile["level"] - 1, tile["parent_tile_id"])
                child_counts[parent_key] = child_counts.get(parent_key, 0) + 1
        for key, tile in lod_tiles_by_key.items():
            self.assertEqual(tile["child_tile_count"], child_counts.get(key, 0))
        self.assertEqual(len(world["cells"][0]["mesh_lod_tile_ids"]), summary["mesh_lod_level_count"])
        self.assertEqual(len(world["cells"][0]["mesh_lod_codes"]), summary["mesh_lod_level_count"])
        self.assertEqual(world["cells"][0]["mesh_lod_finest_tile_id"], world["cells"][0]["mesh_lod_tile_ids"][-1])
        spherical_index = world["spherical_spatial_index"]
        self.assertEqual(spherical_index["index"], "healpix_s2_compat_v0")
        self.assertEqual(summary["spherical_spatial_index"], spherical_index["index"])
        healpix_nside = spherical_index["healpix_like_nside"]
        self.assertGreaterEqual(healpix_nside, 1)
        self.assertEqual(healpix_nside & (healpix_nside - 1), 0)
        self.assertEqual(spherical_index["healpix_like_ring_count"], 3 * healpix_nside)
        self.assertEqual(spherical_index["healpix_like_lon_bin_count"], 4 * healpix_nside)
        self.assertEqual(spherical_index["healpix_like_pixel_count"], 12 * healpix_nside * healpix_nside)
        self.assertEqual(
            summary["healpix_like_occupied_pixel_count"],
            len(spherical_index["healpix_like_pixels"]),
        )
        self.assertEqual(
            sum(record["cell_count"] for record in spherical_index["healpix_like_pixels"]),
            len(world["cells"]),
        )
        self.assertAlmostEqual(
            summary["healpix_like_mean_cells_per_occupied_pixel"],
            len(world["cells"]) / len(spherical_index["healpix_like_pixels"]),
            delta=0.000001,
        )
        s2_level = spherical_index["s2_like_level"]
        s2_scale = 1 << s2_level
        self.assertEqual(spherical_index["s2_like_cell_count"], 6 * s2_scale * s2_scale)
        self.assertEqual(summary["s2_like_cell_level"], s2_level)
        self.assertEqual(summary["s2_like_occupied_cell_count"], len(spherical_index["s2_like_cells"]))
        self.assertEqual(
            sum(record["cell_count"] for record in spherical_index["s2_like_cells"]),
            len(world["cells"]),
        )
        self.assertAlmostEqual(
            summary["s2_like_mean_cells_per_occupied_cell"],
            len(world["cells"]) / len(spherical_index["s2_like_cells"]),
            delta=0.000001,
        )
        self.assertEqual(len(spherical_index["s2_like_face_summaries"]), 6)
        self.assertEqual(
            sum(face["cell_count"] for face in spherical_index["s2_like_face_summaries"]),
            len(world["cells"]),
        )
        self.assertEqual(first_cell["healpix_like_nside"], healpix_nside)
        self.assertEqual(
            first_cell["healpix_like_pixel_id"],
            first_cell["healpix_like_ring"] * spherical_index["healpix_like_lon_bin_count"]
            + first_cell["healpix_like_lon_bin"],
        )
        self.assertEqual(
            first_cell["healpix_like_pixel_code"],
            f"H{healpix_nside}R{first_cell['healpix_like_ring']}C{first_cell['healpix_like_lon_bin']}",
        )
        self.assertEqual(first_cell["s2_like_cell_level"], s2_level)
        self.assertIn(first_cell["s2_like_face"], {"+x", "-x", "+y", "-y", "+z", "-z"})
        self.assertEqual(
            first_cell["s2_like_cell_id"],
            first_cell["s2_like_face_id"] * s2_scale * s2_scale
            + first_cell["s2_like_y"] * s2_scale
            + first_cell["s2_like_x"],
        )
        self.assertIn(
            first_cell["healpix_like_pixel_id"],
            {record["pixel_id"] for record in spherical_index["healpix_like_pixels"]},
        )
        self.assertIn(
            first_cell["s2_like_cell_id"],
            {record["cell_id"] for record in spherical_index["s2_like_cells"]},
        )
        self.assertEqual(
            summary["cell_geometry_index"],
            "native_spherical_control_volume_v1",
        )
        self.assertEqual(summary["cell_geometry_ring_count"], len(world["cells"]))
        self.assertGreater(summary["cell_geometry_total_area_km2"], 0.0)
        self.assertGreater(summary["cell_geometry_reference_area_km2"], 0.0)
        self.assertGreaterEqual(summary["cell_geometry_mean_vertex_count"], 3.0)
        self.assertGreater(summary["cell_geometry_mean_perimeter_km"], 0.0)
        self.assertGreaterEqual(summary["cell_geometry_mean_area_error_fraction"], 0.0)
        self.assertGreaterEqual(summary["cell_geometry_max_area_error_fraction"], summary["cell_geometry_mean_area_error_fraction"])
        self.assertGreaterEqual(summary["cell_geometry_mean_quality"], 0.0)
        self.assertLessEqual(summary["cell_geometry_mean_quality"], 1.0)
        expected_edge_pairs = {
            (min(cell["id"], neighbor_id), max(cell["id"], neighbor_id))
            for cell in world["cells"]
            for neighbor_id in cell["neighbors"]
            if neighbor_id != cell["id"]
        }
        self.assertEqual(summary["cell_adjacency_edge_count"], len(world["cell_adjacency_edges"]))
        self.assertEqual(summary["cell_adjacency_edge_count"], len(expected_edge_pairs))
        self.assertEqual(sum(summary["cell_adjacency_edge_class_counts"].values()), summary["cell_adjacency_edge_count"])
        self.assertGreater(summary["mean_cell_adjacency_edge_length_km"], 0.0)
        self.assertGreaterEqual(summary["max_cell_adjacency_edge_length_km"], summary["mean_cell_adjacency_edge_length_km"])
        self.assertEqual(summary["cell_boundary_segment_geometry"], "approx_neighbor_sector_v0")
        self.assertEqual(summary["cell_boundary_segment_count"], summary["cell_adjacency_edge_count"])
        self.assertGreater(summary["mean_cell_boundary_segment_length_km"], 0.0)
        self.assertGreaterEqual(summary["max_cell_boundary_segment_length_km"], summary["mean_cell_boundary_segment_length_km"])
        self.assertGreaterEqual(summary["mean_cell_boundary_segment_mismatch_km"], 0.0)
        self.assertGreaterEqual(summary["mean_cell_boundary_segment_quality"], 0.0)
        self.assertLessEqual(summary["mean_cell_boundary_segment_quality"], 1.0)
        self.assertEqual(
            summary["tectonic_adjacency_edge_count"],
            sum(1 for edge in world["cell_adjacency_edges"] if edge["plate_boundary"]),
        )
        self.assertEqual(
            summary["land_water_adjacency_edge_count"],
            sum(1 for edge in world["cell_adjacency_edges"] if edge["land_water_transition"]),
        )
        self.assertEqual(
            summary["biome_transition_adjacency_edge_count"],
            sum(1 for edge in world["cell_adjacency_edges"] if edge["biome_transition"]),
        )
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
        for edge_id in first_fault_system["boundary_edge_ids"]:
            self.assertTrue(world["cell_adjacency_edges"][edge_id]["plate_boundary"])
        first_cell_ring = world["cells"][0]["boundary_ring"]
        self.assertEqual(world["cells"][0]["boundary_vertex_count"], len(first_cell_ring))
        self.assertGreaterEqual(len(first_cell_ring), 3)
        self.assertGreater(world["cells"][0]["cell_boundary_perimeter_km"], 0.0)
        self.assertGreater(world["cells"][0]["cell_polygon_area_km2"], 0.0)
        self.assertGreaterEqual(world["cells"][0]["cell_polygon_area_error_fraction"], 0.0)
        self.assertGreaterEqual(world["cells"][0]["cell_geometry_quality"], 0.0)
        self.assertLessEqual(world["cells"][0]["cell_geometry_quality"], 1.0)
        for lat, lon in first_cell_ring:
            self.assertGreaterEqual(lat, -90.0)
            self.assertLessEqual(lat, 90.0)
            self.assertGreaterEqual(lon, -180.0)
            self.assertLessEqual(lon, 180.0)
        first_edge = world["cell_adjacency_edges"][0]
        self.assertEqual(first_edge["id"], 0)
        self.assertLess(first_edge["cell_a_id"], first_edge["cell_b_id"])
        self.assertIn(first_edge["cell_b_id"], world["cells"][first_edge["cell_a_id"]]["neighbors"])
        self.assertGreater(first_edge["great_circle_distance_km"], 0.0)
        self.assertGreaterEqual(first_edge["midpoint_lat_deg"], -90.0)
        self.assertLessEqual(first_edge["midpoint_lat_deg"], 90.0)
        self.assertGreaterEqual(first_edge["midpoint_lon_deg"], -180.0)
        self.assertLessEqual(first_edge["midpoint_lon_deg"], 180.0)
        self.assertGreaterEqual(first_edge["bearing_a_to_b_deg"], 0.0)
        self.assertLessEqual(first_edge["bearing_a_to_b_deg"], 360.0)
        self.assertGreaterEqual(first_edge["bearing_b_to_a_deg"], 0.0)
        self.assertLessEqual(first_edge["bearing_b_to_a_deg"], 360.0)
        self.assertGreaterEqual(first_edge["boundary_segment_start_lat_deg"], -90.0)
        self.assertLessEqual(first_edge["boundary_segment_start_lat_deg"], 90.0)
        self.assertGreaterEqual(first_edge["boundary_segment_start_lon_deg"], -180.0)
        self.assertLessEqual(first_edge["boundary_segment_start_lon_deg"], 180.0)
        self.assertGreaterEqual(first_edge["boundary_segment_end_lat_deg"], -90.0)
        self.assertLessEqual(first_edge["boundary_segment_end_lat_deg"], 90.0)
        self.assertGreaterEqual(first_edge["boundary_segment_end_lon_deg"], -180.0)
        self.assertLessEqual(first_edge["boundary_segment_end_lon_deg"], 180.0)
        self.assertGreater(first_edge["boundary_segment_length_km"], 0.0)
        self.assertGreater(first_edge["cell_a_boundary_segment_length_km"], 0.0)
        self.assertGreater(first_edge["cell_b_boundary_segment_length_km"], 0.0)
        self.assertGreaterEqual(first_edge["boundary_segment_mismatch_km"], 0.0)
        self.assertGreaterEqual(first_edge["boundary_segment_quality"], 0.0)
        self.assertLessEqual(first_edge["boundary_segment_quality"], 1.0)
        self.assertTrue(first_edge["edge_class"])
        first_cell_edges = world["cells"][0]["cell_adjacency_edge_ids"]
        self.assertEqual(world["cells"][0]["cell_edge_count"], len(first_cell_edges))
        self.assertGreater(world["cells"][0]["mean_neighbor_edge_length_km"], 0.0)
        self.assertGreaterEqual(world["cells"][0]["max_neighbor_edge_length_km"], world["cells"][0]["mean_neighbor_edge_length_km"])
        self.assertGreater(world["cells"][0]["mean_neighbor_boundary_segment_length_km"], 0.0)
        self.assertGreaterEqual(
            world["cells"][0]["max_neighbor_boundary_segment_length_km"],
            world["cells"][0]["mean_neighbor_boundary_segment_length_km"],
        )
        self.assertGreaterEqual(world["cells"][0]["mean_neighbor_boundary_segment_mismatch_km"], 0.0)
        self.assertGreaterEqual(world["cells"][0]["mean_neighbor_boundary_segment_quality"], 0.0)
        self.assertLessEqual(world["cells"][0]["mean_neighbor_boundary_segment_quality"], 1.0)
        self.assertGreaterEqual(world["cells"][0]["tectonic_neighbor_edge_count"], 0)
        self.assertGreaterEqual(world["cells"][0]["land_water_neighbor_edge_count"], 0)
        self.assertGreaterEqual(world["cells"][0]["biome_transition_neighbor_edge_count"], 0)
        self.assertEqual(
            summary["hydrologic_surface_model"],
            "priority_flood_fill_with_deterministic_flat_gradient_v1",
        )
        self.assertEqual(
            summary["river_extraction_model"],
            "flow_accumulation_percentile_on_conditioned_hydrologic_surface_v1",
        )
        self.assertAlmostEqual(summary["hydrologic_flat_gradient_step_m"], 0.001)
        flow_cells = [cell for cell in world["cells"] if cell["flow_to"] >= 0]
        cells_by_id = {cell["id"]: cell for cell in world["cells"]}
        for cell in flow_cells:
            receiver = cells_by_id[cell["flow_to"]]
            self.assertGreater(
                cell["hydrologic_surface_elevation_m"],
                receiver["hydrologic_surface_elevation_m"],
            )
            self.assertAlmostEqual(
                cell["hydrologic_flow_drop_m"],
                cell["hydrologic_surface_elevation_m"]
                - receiver["hydrologic_surface_elevation_m"],
                delta=0.0000002,
            )
            self.assertGreater(cell["hydrologic_flow_slope"], 0.0)
        self.assertEqual(
            summary["hydrologic_surface_conditioned_cell_count"],
            sum(cell["hydrologic_surface_conditioned"] for cell in world["cells"]),
        )
        self.assertEqual(
            summary["non_downhill_hydrologic_flow_edge_count"],
            0,
        )
        self.assertEqual(summary["lake_basin_count"], len(world["lake_basins"]))
        self.assertEqual(summary["depression_component_count"], len(world["lake_basins"]))
        self.assertEqual(
            summary["depression_component_cell_count"],
            sum(1 for cell in world["cells"] if cell["depression_component_id"] >= 0),
        )
        self.assertEqual(
            summary["closed_depression_count"],
            sum(
                1
                for basin in world["lake_basins"]
                if basin["depression_policy"] in {"preserved_geologic", "dry_closed"}
                or (
                    basin["depression_policy"] == "temporary_numeric_lake"
                    and not basin["overflows"]
                )
            ),
        )
        self.assertIn("overflowing_lake_basin_count", summary)
        self.assertEqual(
            summary["overflowing_lake_basin_count"],
            sum(1 for basin in world["lake_basins"] if basin["overflows"]),
        )
        self.assertIn("staged_overflow_lake_basin_count", summary)
        self.assertEqual(
            summary["staged_overflow_lake_basin_count"],
            sum(1 for basin in world["lake_basins"] if basin["overflow_stage_count"] > 0),
        )
        self.assertIn("high_avulsion_risk_lake_basin_count", summary)
        self.assertEqual(
            summary["high_avulsion_risk_lake_basin_count"],
            sum(1 for basin in world["lake_basins"] if basin["avulsion_risk"] >= 0.65),
        )
        self.assertIn("preserved_geologic_depression_count", summary)
        self.assertEqual(
            summary["preserved_geologic_depression_count"],
            sum(
                1
                for basin in world["lake_basins"]
                if basin["is_geologic"]
                and basin["depression_policy"]
                not in {"corrected_numeric", "temporary_numeric_lake"}
            ),
        )
        self.assertIn("corrected_numeric_depression_count", summary)
        self.assertEqual(
            summary["corrected_numeric_depression_count"],
            sum(1 for basin in world["lake_basins"] if basin["depression_policy"] == "corrected_numeric"),
        )
        self.assertEqual(summary["corrected_numeric_depression_count"], 0)
        self.assertEqual(
            summary["temporary_numeric_lake_depression_count"],
            sum(
                1
                for basin in world["lake_basins"]
                if basin["depression_policy"] == "temporary_numeric_lake"
            ),
        )
        self.assertEqual(
            summary["numeric_depression_correction_model"],
            "bounded_mass_conserving_breach_or_zero_material_temporary_lake_with_coupled_recomputation_v3",
        )
        self.assertEqual(
            summary["numeric_depression_correction_selection_model"],
            "lower_volume_full_cell_breach_with_50m_depth_bound_else_temporary_lake_v3",
        )
        self.assertEqual(
            summary["numeric_depression_breach_diagnostic_model"],
            "weighted_graph_excavation_proxy_monotone_lower_outlet_v1",
        )
        self.assertEqual(summary["numeric_depression_selected_breach_max_depth_m"], 50.0)
        self.assertEqual(summary["numeric_depression_fill_max_pass_count"], 16)
        self.assertAlmostEqual(
            summary["numeric_depression_fill_depth_tolerance_m"], 1.0e-9
        )
        fill_history = world["numeric_depression_fill_history"]
        self.assertTrue(fill_history)
        selected_breaches = [
            event
            for event in fill_history
            if event["selected_correction_method"] == "mass_conserving_breach"
        ]
        temporary_lake_deferrals = [
            event
            for event in fill_history
            if event["selected_correction_method"] == "temporary_numeric_lake"
        ]
        self.assertEqual(
            summary["numeric_depression_correction_event_count"],
            len(fill_history),
        )
        self.assertEqual(
            summary["numeric_depression_breach_selected_event_count"],
            len(selected_breaches),
        )
        self.assertEqual(
            summary["numeric_depression_breach_feasible_event_count"],
            sum(event["breach_feasible"] for event in fill_history),
        )
        self.assertEqual(
            summary["numeric_depression_breach_lower_volume_event_count"],
            sum(
                event["breach_has_lower_adjustment_volume"]
                for event in fill_history
            ),
        )
        expected_hybrid_adjustment_volume_km3 = sum(
            event["breach_excavation_volume_km3"]
            if event["breach_has_lower_adjustment_volume"]
            else event["fill_volume_km3"]
            for event in fill_history
        )
        self.assertAlmostEqual(
            summary["numeric_depression_lower_volume_hybrid_adjustment_volume_km3"],
            expected_hybrid_adjustment_volume_km3,
            delta=max(0.000001, expected_hybrid_adjustment_volume_km3 * 1.0e-10),
        )
        self.assertEqual(
            summary["numeric_depression_fill_event_count"], 0
        )
        self.assertEqual(
            summary["numeric_depression_temporary_lake_event_count"],
            len(temporary_lake_deferrals),
        )
        self.assertEqual(
            summary["numeric_depression_fill_pass_count"],
            len(
                {
                    (event["feedback_stage_id"], event["stabilization_pass"])
                    for event in fill_history
                }
            ),
        )
        self.assertEqual(
            summary["numeric_depression_fill_cell_application_count"],
            0,
        )
        temporary_lake_cell_ids = {
            cell_id
            for event in temporary_lake_deferrals
            for cell_id in event["cell_ids"]
        }
        self.assertEqual(
            summary["numeric_depression_filled_unique_cell_count"],
            0,
        )
        self.assertEqual(
            summary["numeric_depression_temporary_lake_cell_application_count"],
            sum(event["cell_count"] for event in temporary_lake_deferrals),
        )
        self.assertEqual(
            summary["numeric_depression_temporary_lake_unique_cell_count"],
            len(temporary_lake_cell_ids),
        )
        expected_fill_depth_by_cell = Counter()
        expected_fill_event_count_by_cell = Counter()
        expected_breach_excavation_by_cell = Counter()
        expected_breach_deposition_by_cell = Counter()
        expected_breach_event_count_by_cell = Counter()
        expected_temporary_lake_event_count_by_cell = Counter()
        for event in fill_history:
            self.assertEqual(event["cell_count"], len(event["cell_ids"]))
            self.assertEqual(
                event["cell_count"], len(event["fill_depth_m_by_cell"])
            )
            for cell_id, before, depth, after in zip(
                event["cell_ids"],
                event["elevation_before_fill_m_by_cell"],
                event["fill_depth_m_by_cell"],
                event["elevation_after_fill_m_by_cell"],
                strict=True,
            ):
                self.assertGreater(depth, 0.0)
                self.assertAlmostEqual(after, before + depth, delta=0.000000005)
                if event["selected_correction_method"] == "temporary_numeric_lake":
                    expected_temporary_lake_event_count_by_cell[cell_id] += 1
            self.assertFalse(event["fill_candidate_applied"])
            self.assertAlmostEqual(event["applied_fill_volume_km3"], 0.0)
            if event["selected_correction_method"] == "mass_conserving_breach":
                self.assertLessEqual(event["max_breach_excavation_depth_m"], 50.0)
                self.assertAlmostEqual(
                    event["applied_breach_excavation_volume_km3"],
                    event["applied_breach_deposition_volume_km3"],
                    delta=0.000001,
                )
                self.assertAlmostEqual(
                    event["correction_mass_balance_residual_km3"],
                    0.0,
                    delta=0.000001,
                )
                for cell_id, depth in zip(
                    event["breach_path_cell_ids"],
                    event["breach_excavation_depth_m_by_cell"],
                    strict=True,
                ):
                    if depth > 1.0e-9:
                        expected_breach_excavation_by_cell[cell_id] += depth
                        expected_breach_event_count_by_cell[cell_id] += 1
                for cell_id, depth in zip(
                    event["breach_deposition_cell_ids"],
                    event["breach_deposition_depth_m_by_cell"],
                    strict=True,
                ):
                    expected_breach_deposition_by_cell[cell_id] += depth
                    expected_breach_event_count_by_cell[cell_id] += 1
            else:
                self.assertTrue(event["temporary_numeric_lake_selected"])
                self.assertAlmostEqual(
                    event["correction_mass_balance_residual_km3"], 0.0
                )
        for cell in world["cells"]:
            self.assertAlmostEqual(
                cell["cumulative_numeric_depression_fill_m"],
                expected_fill_depth_by_cell[cell["id"]],
                delta=0.0000001,
            )
            self.assertEqual(
                cell["numeric_depression_fill_event_count"],
                expected_fill_event_count_by_cell[cell["id"]],
            )
            self.assertAlmostEqual(
                cell["cumulative_numeric_depression_breach_excavation_m"],
                expected_breach_excavation_by_cell[cell["id"]],
                delta=0.0000001,
            )
            self.assertAlmostEqual(
                cell["cumulative_numeric_depression_breach_deposition_m"],
                expected_breach_deposition_by_cell[cell["id"]],
                delta=0.0000001,
            )
            self.assertEqual(
                cell["numeric_depression_breach_event_count"],
                expected_breach_event_count_by_cell[cell["id"]],
            )
            self.assertEqual(
                cell["numeric_depression_temporary_lake_event_count"],
                expected_temporary_lake_event_count_by_cell[cell["id"]],
            )
        self.assertEqual(summary["numeric_depression_fill_volume_km3"], 0.0)
        self.assertEqual(
            summary["numeric_depression_correction_mass_balance_residual_km3"],
            0.0,
        )
        self.assertEqual(
            summary["numeric_depression_unbalanced_fill_event_count"], 0
        )
        self.assertEqual(
            summary["numeric_depression_mass_conserving_event_count"],
            len(fill_history),
        )
        self.assertAlmostEqual(
            summary["numeric_depression_avoided_unsourced_fill_volume_km3"],
            summary["numeric_depression_fill_candidate_volume_km3"],
        )
        self.assertIn("mean_lake_fill_fraction", summary)
        self.assertIn("lake_storage_capacity_km3", summary)
        self.assertIn("lake_annual_runoff_km3", summary)
        self.assertIn("mean_lake_overflow_path_length_km", summary)
        self.assertIn("mean_lake_avulsion_risk", summary)
        simulated_lake_basin_ids = {
            basin["id"]
            for basin in world["lake_basins"]
            if basin["lake_cell_count"] > 0
        }
        self.assertEqual(
            summary["simulated_lake_basin_count"], len(simulated_lake_basin_ids)
        )
        self.assertEqual(summary["lake_overflow_history_count"], len(world["lake_overflow_histories"]))
        self.assertEqual(
            {history["lake_basin_id"] for history in world["lake_overflow_histories"]},
            simulated_lake_basin_ids,
        )
        self.assertEqual(
            summary["lake_overflow_history_step_count"],
            sum(history["time_step_count"] for history in world["lake_overflow_histories"]),
        )
        self.assertGreaterEqual(summary["lake_overflow_simulation_years"], 1)
        self.assertEqual(
            summary["lake_overflow_active_history_count"],
            sum(1 for history in world["lake_overflow_histories"] if history["total_spill_km3"] > 0.0),
        )
        self.assertEqual(
            summary["lake_overflow_avulsion_trigger_count"],
            sum(1 for history in world["lake_overflow_histories"] if history["avulsion_triggered"]),
        )
        self.assertEqual(summary["lake_overflow_channel_history_count"], len(world["lake_overflow_channel_histories"]))
        self.assertEqual(
            len(world["lake_overflow_channel_histories"]),
            sum(1 for basin in world["lake_basins"] if len(basin["overflow_path_cell_ids"]) >= 2),
        )
        self.assertEqual(
            summary["lake_overflow_channel_step_count"],
            sum(history["time_step_count"] for history in world["lake_overflow_channel_histories"]),
        )
        self.assertEqual(
            summary["active_lake_overflow_channel_count"],
            sum(1 for history in world["lake_overflow_channel_histories"] if history["total_spill_km3"] > 0.0),
        )
        self.assertEqual(
            summary["lake_overflow_channel_cell_count"],
            sum(1 for cell in world["cells"] if cell["overflow_channel_active"]),
        )
        self.assertIn("lake_overflow_total_channel_incision_m", summary)
        self.assertIn("max_lake_overflow_channel_incision_m", summary)
        self.assertIn("lake_overflow_total_channel_sediment_evacuated_km3", summary)
        self.assertIn("mean_lake_overflow_channel_stream_power_index", summary)
        self.assertGreaterEqual(summary["lake_overflow_total_channel_incision_m"], 0.0)
        self.assertGreaterEqual(summary["max_lake_overflow_channel_incision_m"], 0.0)
        self.assertGreaterEqual(summary["lake_overflow_total_channel_sediment_evacuated_km3"], 0.0)
        self.assertGreaterEqual(summary["mean_lake_overflow_channel_stream_power_index"], 0.0)
        self.assertLessEqual(summary["mean_lake_overflow_channel_stream_power_index"], 1.0)
        self.assertGreater(summary["basin_count"], 0)
        self.assertEqual(summary["watershed_count"], len(world["watersheds"]))
        self.assertGreater(summary["watershed_count"], 0)
        self.assertIn("endorheic_watershed_count", summary)
        self.assertIn("largest_watershed_area_km2", summary)
        self.assertIn("watershed_geometry_count", summary)
        self.assertIn("largest_watershed_boundary_cell_count", summary)
        self.assertIn("watershed_polygon_count", summary)
        self.assertEqual(
            summary["watershed_polygon_count"],
            sum(1 for watershed in world["watersheds"] if watershed["dissolved_polygon_area_km2"] > 0.0),
        )
        self.assertIn("largest_watershed_polygon_area_km2", summary)
        self.assertIn("mean_watershed_polygon_area_error_fraction", summary)
        self.assertIn("mean_watershed_compactness_index", summary)
        self.assertIn("mean_watershed_geometry_quality", summary)
        self.assertGreaterEqual(summary["mean_watershed_geometry_quality"], 0.0)
        self.assertLessEqual(summary["mean_watershed_geometry_quality"], 1.0)
        self.assertIn("mean_watershed_boundary_perimeter_km", summary)
        self.assertIn("watershed_main_channel_count", summary)
        self.assertEqual(
            summary["watershed_main_channel_count"],
            sum(1 for watershed in world["watersheds"] if watershed["main_channel_length_km"] > 0.0),
        )
        self.assertAlmostEqual(
            summary["watershed_total_river_length_km"],
            sum(watershed["total_river_length_km"] for watershed in world["watersheds"]),
            delta=max(0.001, summary["watershed_total_river_length_km"] * 0.0001),
        )
        self.assertGreaterEqual(summary["watershed_mean_main_channel_length_km"], 0.0)
        self.assertGreaterEqual(summary["watershed_max_main_channel_length_km"], 0.0)
        self.assertGreaterEqual(summary["watershed_mean_drainage_density_km_per_1000_km2"], 0.0)
        self.assertAlmostEqual(summary["watershed_hack_exponent"], 0.6, delta=0.0001)
        self.assertGreaterEqual(summary["watershed_hack_fit_coefficient"], 0.0)
        self.assertGreaterEqual(summary["watershed_mean_hack_coefficient"], 0.0)
        self.assertGreaterEqual(summary["watershed_mean_abs_hack_residual_fraction"], 0.0)
        self.assertEqual(
            summary["watershed_hack_fitted_observation_count"],
            summary["watershed_main_channel_count"],
        )
        self.assertTrue(math.isfinite(summary["watershed_hack_fitted_exponent"]))
        self.assertGreaterEqual(summary["watershed_hack_fitted_coefficient"], 0.0)
        self.assertGreaterEqual(summary["watershed_hack_fitted_log_rmse"], 0.0)
        self.assertEqual(sum(summary["watershed_outlet_type_counts"].values()), len(world["watersheds"]))
        self.assertEqual(
            summary["watershed_cell_edge_boundary_segment_count"],
            len(world["watershed_boundary_segments"]),
        )
        self.assertEqual(
            summary["watershed_cell_edge_boundary_directed_segment_count"],
            sum(watershed["cell_edge_boundary_segment_count"] for watershed in world["watersheds"]),
        )
        self.assertEqual(
            summary["watershed_with_cell_edge_boundary_count"],
            sum(1 for watershed in world["watersheds"] if watershed["cell_edge_boundary_segment_count"] > 0),
        )
        self.assertAlmostEqual(
            summary["watershed_cell_edge_boundary_length_km"],
            sum(segment["length_km"] for segment in world["watershed_boundary_segments"]),
            delta=max(0.001, summary["watershed_cell_edge_boundary_length_km"] * 0.0001),
        )
        self.assertGreaterEqual(summary["mean_watershed_cell_edge_boundary_length_km"], 0.0)
        self.assertGreaterEqual(summary["mean_watershed_cell_edge_boundary_segment_quality"], 0.0)
        self.assertLessEqual(summary["mean_watershed_cell_edge_boundary_segment_quality"], 1.0)
        self.assertEqual(summary["hydrology_realism_check_count"], len(world["hydrology_realism_checks"]))
        self.assertGreaterEqual(summary["hydrology_realism_check_count"], 5)
        self.assertEqual(
            summary["hydrology_realism_pass_count"],
            sum(1 for check in world["hydrology_realism_checks"] if check["passed"]),
        )
        self.assertGreaterEqual(summary["hydrology_realism_pass_fraction"], 0.0)
        self.assertLessEqual(summary["hydrology_realism_pass_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_hydrology_realism_score"], 0.0)
        self.assertLessEqual(summary["mean_hydrology_realism_score"], 1.0)
        for key in [
            "valid_river_sink_fraction",
            "river_downhill_realism_index",
            "tributary_merge_coherence_index",
            "delta_lowland_sediment_terminal_water_index",
            "watershed_divide_alignment_index",
        ]:
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        hydrology_names = {check["name"] for check in world["hydrology_realism_checks"]}
        self.assertTrue(
            {
                "river_terminal_sink_validity",
                "river_downhill_flow",
                "tributary_merge_coherence",
                "delta_lowland_sediment_terminal_water",
                "watershed_divide_alignment",
            }.issubset(hydrology_names)
        )
        first_hydrology_check = world["hydrology_realism_checks"][0]
        self.assertEqual(first_hydrology_check["domain"], "hydrology")
        self.assertIn("evidence", first_hydrology_check)
        self.assertGreaterEqual(first_hydrology_check["score"], 0.0)
        self.assertLessEqual(first_hydrology_check["score"], 1.0)
        self.assertEqual(summary["hydrologic_budget_region_count"], len(world["hydrologic_budget_regions"]))
        self.assertEqual(sum(summary["hydrologic_budget_class_counts"].values()), summary["cell_count"])
        for key in [
            "mean_actual_evapotranspiration_mm_y",
            "mean_infiltration_mm_y",
            "mean_infiltration_capacity_index",
            "mean_hydrologic_water_balance_mm_y",
            "mean_water_budget_runoff_mm_y",
            "mean_hydrologic_deficit_mm_y",
            "mean_abs_runoff_budget_residual_mm_y",
            "mean_runoff_budget_consistency_index",
            "mean_runoff_generation_fraction",
            "total_infiltration_km3_y",
            "total_water_budget_runoff_km3_y",
        ]:
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
        self.assertGreaterEqual(summary["mean_infiltration_capacity_index"], 0.0)
        self.assertLessEqual(summary["mean_infiltration_capacity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_runoff_budget_consistency_index"], 0.0)
        self.assertLessEqual(summary["mean_runoff_budget_consistency_index"], 1.0)
        self.assertGreaterEqual(summary["mean_runoff_generation_fraction"], 0.0)
        self.assertLessEqual(summary["mean_runoff_generation_fraction"], 1.0)
        self.assertEqual(
            summary["high_runoff_generation_cell_count"],
            sum(1 for cell in world["cells"] if cell["runoff_generation_fraction"] >= 0.35),
        )
        self.assertEqual(
            summary["water_budget_deficit_cell_count"],
            sum(1 for cell in world["cells"] if cell["hydrologic_deficit_mm_y"] >= 250.0),
        )
        self.assertEqual(
            summary["low_runoff_budget_consistency_cell_count"],
            sum(1 for cell in world["cells"] if cell["runoff_budget_consistency_index"] < 0.60),
        )
        if world["hydrologic_budget_regions"]:
            first_budget_region = world["hydrologic_budget_regions"][0]
            self.assertEqual(first_budget_region["id"], 0)
            self.assertIn(
                first_budget_region["region_class"],
                {
                    "marine_budget",
                    "water_deficit",
                    "runoff_surplus",
                    "infiltration_dominated",
                    "evapotranspiration_dominated",
                    "balanced_budget",
                },
            )
            self.assertEqual(first_budget_region["cell_count"], len(first_budget_region["cell_ids"]))
            self.assertGreater(first_budget_region["area_km2"], 0.0)
            self.assertIn("mean_actual_evapotranspiration_mm_y", first_budget_region)
            self.assertIn("mean_infiltration_mm_y", first_budget_region)
            self.assertIn("mean_water_budget_runoff_mm_y", first_budget_region)
        self.assertEqual(summary["wetland_system_count"], len(world["wetland_systems"]))
        self.assertEqual(sum(summary["wetland_type_counts"].values()), summary["cell_count"])
        self.assertEqual(
            summary["wetland_cell_count"],
            sum(1 for cell in world["cells"] if cell["wetland_system_type"] != "none"),
        )
        for key in [
            "wetland_area_km2",
            "wetland_area_fraction",
            "mean_wetland_extent_index",
            "mean_wetland_hydrology_index",
            "mean_wetland_soil_saturation_index",
            "mean_wetland_ecotone_index",
            "mean_wetland_connectivity_index",
            "mean_wetland_extent_index_over_wetlands",
        ]:
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
        for key in [
            "wetland_area_fraction",
            "mean_wetland_extent_index",
            "mean_wetland_hydrology_index",
            "mean_wetland_soil_saturation_index",
            "mean_wetland_ecotone_index",
            "mean_wetland_connectivity_index",
            "mean_wetland_extent_index_over_wetlands",
        ]:
            self.assertLessEqual(summary[key], 1.0)
        self.assertEqual(summary["mangrove_wetland_cell_count"], summary["wetland_type_counts"].get("mangrove", 0))
        self.assertEqual(summary["tidal_marsh_wetland_cell_count"], summary["wetland_type_counts"].get("tidal_marsh", 0))
        self.assertEqual(summary["delta_wetland_cell_count"], summary["wetland_type_counts"].get("delta_wetland", 0))
        self.assertEqual(
            summary["floodplain_wetland_cell_count"],
            summary["wetland_type_counts"].get("floodplain_wetland", 0),
        )
        self.assertEqual(
            summary["freshwater_swamp_cell_count"],
            summary["wetland_type_counts"].get("freshwater_swamp", 0),
        )
        if world["wetland_systems"]:
            first_wetland = world["wetland_systems"][0]
            self.assertEqual(first_wetland["id"], 0)
            self.assertIn(
                first_wetland["wetland_type"],
                {
                    "mangrove",
                    "tidal_marsh",
                    "delta_wetland",
                    "floodplain_wetland",
                    "lacustrine_wetland",
                    "peatland",
                    "freshwater_swamp",
                },
            )
            self.assertEqual(first_wetland["cell_count"], len(first_wetland["cell_ids"]))
            self.assertGreater(first_wetland["area_km2"], 0.0)
            self.assertIn("mean_wetland_extent_index", first_wetland)
            self.assertIn("linked_basin_ids", first_wetland)
        self.assertEqual(summary["river_network_evolution_event_count"], len(world["river_network_evolution_events"]))
        self.assertEqual(
            summary["river_capture_candidate_count"],
            sum(1 for cell in world["cells"] if cell["river_capture_risk"] > 0.0),
        )
        self.assertEqual(
            summary["high_river_capture_risk_cell_count"],
            sum(1 for cell in world["cells"] if cell["river_capture_risk"] >= 0.65),
        )
        self.assertAlmostEqual(
            summary["mean_river_capture_risk"],
            sum(cell["river_capture_risk"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.0001,
        )
        self.assertGreaterEqual(summary["max_river_capture_risk"], 0.0)
        self.assertLessEqual(summary["max_river_capture_risk"], 1.0)
        self.assertEqual(
            summary["river_avulsion_candidate_count"],
            sum(1 for cell in world["cells"] if cell["river_avulsion_risk"] > 0.0),
        )
        self.assertEqual(
            summary["high_river_avulsion_risk_cell_count"],
            sum(1 for cell in world["cells"] if cell["river_avulsion_risk"] >= 0.65),
        )
        self.assertAlmostEqual(
            summary["mean_river_avulsion_risk"],
            sum(cell["river_avulsion_risk"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.0001,
        )
        self.assertGreaterEqual(summary["max_river_avulsion_risk"], 0.0)
        self.assertLessEqual(summary["max_river_avulsion_risk"], 1.0)
        self.assertEqual(
            summary["river_network_instability_cell_count"],
            sum(1 for cell in world["cells"] if cell["river_network_instability_index"] > 0.0),
        )
        self.assertEqual(
            summary["high_river_network_instability_cell_count"],
            sum(1 for cell in world["cells"] if cell["river_network_instability_index"] >= 0.65),
        )
        self.assertAlmostEqual(
            summary["mean_river_network_instability_index"],
            sum(cell["river_network_instability_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.0001,
        )
        self.assertGreaterEqual(summary["max_river_network_instability_index"], 0.0)
        self.assertLessEqual(summary["max_river_network_instability_index"], 1.0)
        self.assertEqual(summary["river_reorganization_history_count"], len(world["river_reorganization_histories"]))
        self.assertEqual(summary["river_reorganization_history_count"], len(world["river_network_evolution_events"]))
        self.assertEqual(
            summary["river_reorganization_step_count"],
            sum(history["step_count"] for history in world["river_reorganization_histories"]),
        )
        self.assertGreaterEqual(summary["mean_river_reorganization_risk_index"], 0.0)
        self.assertLessEqual(summary["mean_river_reorganization_risk_index"], 1.0)
        self.assertGreaterEqual(summary["mean_river_diversion_probability_index"], 0.0)
        self.assertLessEqual(summary["mean_river_diversion_probability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_river_reorganization_confidence_index"], 0.0)
        self.assertLessEqual(summary["mean_river_reorganization_confidence_index"], 1.0)
        self.assertGreaterEqual(summary["total_river_divide_lowering_m"], 0.0)
        self.assertGreaterEqual(summary["total_river_sediment_reworked_m"], 0.0)
        if world["river_reorganization_histories"]:
            self.assertAlmostEqual(
                summary["mean_river_reorganization_risk_index"],
                sum(history["risk_index"] for history in world["river_reorganization_histories"])
                / len(world["river_reorganization_histories"]),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["total_river_divide_lowering_m"],
                sum(history["total_divide_lowering_m"] for history in world["river_reorganization_histories"]),
                delta=0.001,
            )
            self.assertEqual(
                summary["high_river_reorganization_pressure_count"],
                sum(1 for history in world["river_reorganization_histories"] if history["high_reorganization_pressure"]),
            )
        self.assertEqual(summary["coastal_feature_count"], len(world["coastal_features"]))
        self.assertIn("coastal_bar_feature_count", summary)
        self.assertEqual(
            summary["coastal_bar_feature_count"],
            sum(1 for feature in world["coastal_features"] if feature["type"] in {"barrier_bar", "barrier_island"}),
        )
        self.assertIn("prograding_coastal_feature_count", summary)
        self.assertEqual(
            summary["prograding_coastal_feature_count"],
            sum(
                1
                for feature in world["coastal_features"]
                if feature["shoreline_trend"] in {"prograding", "delta_switching"}
            ),
        )
        self.assertIn("eroding_coastal_feature_count", summary)
        self.assertEqual(
            summary["eroding_coastal_feature_count"],
            sum(
                1
                for feature in world["coastal_features"]
                if feature["shoreline_trend"] in {"eroding", "landward_migration"}
            ),
        )
        self.assertIn("mean_coastal_migration_rate_m_y", summary)
        self.assertEqual(summary["reef_system_count"], len(world["reef_systems"]))
        reef_cell_ids = {cell["id"] for cell in world["cells"] if cell["reef_system_id"] >= 0}
        reef_record_cell_ids = {cell_id for reef in world["reef_systems"] for cell_id in reef["cell_ids"]}
        self.assertEqual(summary["reef_cell_count"], len(reef_cell_ids))
        self.assertEqual(reef_record_cell_ids, reef_cell_ids)
        self.assertAlmostEqual(
            summary["reef_total_area_km2"],
            sum(reef["area_km2"] for reef in world["reef_systems"]),
            delta=max(0.001, summary["reef_total_area_km2"] * 0.0001),
        )
        reef_type_counts: dict[str, int] = {}
        for reef in world["reef_systems"]:
            reef_type_counts[reef["reef_type"]] = reef_type_counts.get(reef["reef_type"], 0) + 1
        self.assertEqual(summary["reef_type_counts"], dict(sorted(reef_type_counts.items())))
        self.assertEqual(sum(summary["reef_type_counts"].values()), summary["reef_system_count"])
        self.assertEqual(summary["fringing_reef_system_count"], reef_type_counts.get("fringing_reef", 0))
        self.assertEqual(summary["barrier_reef_system_count"], reef_type_counts.get("barrier_reef", 0))
        self.assertEqual(summary["atoll_reef_system_count"], reef_type_counts.get("atoll_reef", 0))
        self.assertEqual(summary["patch_reef_system_count"], reef_type_counts.get("patch_reef", 0))
        self.assertEqual(summary["cold_water_reef_system_count"], reef_type_counts.get("cold_water_reef", 0))
        for key in [
            "reef_growth_index",
            "reef_sediment_stress_index",
            "reef_wave_exposure_index",
            "reef_island_support_index",
            "reef_bleaching_risk_index",
        ]:
            summary_key = f"mean_{key}"
            self.assertIn(summary_key, summary)
            self.assertAlmostEqual(
                summary[summary_key],
                sum(cell[key] for cell in world["cells"]) / len(world["cells"]),
                delta=0.001,
            )
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
            "cell_area_weighted_hillslope_glacial_and_routed_deposition_terminal_export_volume_v4",
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
        self.assertEqual(summary["landmass_count"], len(world["landmasses"]))
        self.assertEqual(summary["marine_region_count"], len(world["marine_regions"]))
        self.assertEqual(summary["marine_chokepoint_count"], len(world["marine_chokepoints"]))
        self.assertEqual(
            summary["continent_landmass_count"],
            sum(1 for landmass in world["landmasses"] if landmass["island_class"] == "continent"),
        )
        self.assertEqual(
            summary["island_landmass_count"],
            sum(1 for landmass in world["landmasses"] if landmass["island_class"] != "continent"),
        )
        self.assertAlmostEqual(
            summary["largest_landmass_area_km2"],
            max((landmass["area_km2"] for landmass in world["landmasses"]), default=0.0),
            delta=max(0.001, summary["largest_landmass_area_km2"] * 0.0001),
        )
        self.assertEqual(
            summary["open_ocean_marine_region_count"],
            sum(1 for region in world["marine_regions"] if region["region_class"] == "open_ocean"),
        )
        self.assertEqual(
            summary["strait_chokepoint_count"],
            sum(1 for chokepoint in world["marine_chokepoints"] if chokepoint["type"] == "strait"),
        )
        self.assertIn("landform_counts", summary)
        self.assertEqual(sum(summary["landform_counts"].values()), summary["cell_count"])
        self.assertIn("mean_orographic_factor", summary)
        self.assertIn("mean_rain_shadow_factor", summary)
        self.assertIn("rain_shadowed_land_fraction", summary)
        self.assertIn("mean_humidity_transport_index", summary)
        self.assertIn("mean_upwind_ocean_fetch_km", summary)
        self.assertIn("mean_advected_moisture_factor", summary)
        self.assertIn("atmospheric_cell_counts", summary)
        self.assertEqual(sum(summary["atmospheric_cell_counts"].values()), summary["cell_count"])
        self.assertIn("mean_surface_pressure_anomaly_hpa", summary)
        self.assertGreaterEqual(summary["mean_surface_pressure_anomaly_hpa"], -22.0)
        self.assertLessEqual(summary["mean_surface_pressure_anomaly_hpa"], 22.0)
        self.assertIn("mean_vertical_velocity_index", summary)
        self.assertGreaterEqual(summary["mean_vertical_velocity_index"], -1.0)
        self.assertLessEqual(summary["mean_vertical_velocity_index"], 1.0)
        self.assertIn("mean_wind_divergence_index", summary)
        self.assertGreaterEqual(summary["mean_wind_divergence_index"], -1.0)
        self.assertLessEqual(summary["mean_wind_divergence_index"], 1.0)
        self.assertIn("mean_seasonal_wind_speed", summary)
        self.assertIn("mean_seasonal_wind_reversal_index", summary)
        self.assertGreaterEqual(summary["mean_seasonal_wind_speed"], 0.0)
        self.assertLessEqual(summary["mean_seasonal_wind_speed"], 1.5)
        self.assertGreaterEqual(summary["mean_seasonal_wind_reversal_index"], 0.0)
        self.assertLessEqual(summary["mean_seasonal_wind_reversal_index"], 1.0)
        self.assertIn("ascending_air_fraction", summary)
        self.assertGreaterEqual(summary["ascending_air_fraction"], 0.0)
        self.assertLessEqual(summary["ascending_air_fraction"], 1.0)
        self.assertIn("mean_vapor_evaporation_mm_y", summary)
        self.assertIn("mean_moisture_convergence_mm_y", summary)
        self.assertIn("mean_orographic_rainout_mm_y", summary)
        self.assertIn("mean_precipitation_recycling_fraction", summary)
        self.assertIn("mean_vapor_deficit_mm_y", summary)
        self.assertIn("mean_abs_vapor_budget_residual_mm_y", summary)
        self.assertLessEqual(summary["mean_abs_vapor_budget_residual_mm_y"], 1.0)
        self.assertIn("mean_ocean_current_strength", summary)
        self.assertIn("mean_ocean_current_temperature_c", summary)
        self.assertIn("mean_ocean_current_moisture_factor", summary)
        marine_current_cells = [
            cell
            for cell in world["cells"]
            if cell["water_body_type"] in {"ocean", "continental_shelf", "inland_sea"}
        ]
        self.assertEqual(summary["ocean_current_cell_count"], len(marine_current_cells))
        self.assertEqual(summary["ocean_current_system_count"], len(world["ocean_current_systems"]))
        self.assertEqual(
            summary["ocean_current_transport_edge_count"],
            len(world["ocean_current_transport_edges"]),
        )
        self.assertEqual(sum(summary["ocean_current_regime_counts"].values()), summary["cell_count"])
        self.assertEqual(
            sum(summary["ocean_current_system_class_counts"].values()),
            summary["ocean_current_system_count"],
        )
        self.assertEqual(
            {cell_id for system in world["ocean_current_systems"] for cell_id in system["cell_ids"]},
            {cell["id"] for cell in marine_current_cells},
        )
        self.assertEqual(
            {edge["source_cell_id"] for edge in world["ocean_current_transport_edges"]},
            {
                cell["id"]
                for cell in marine_current_cells
                if cell["ocean_current_transport_target_cell_id"] >= 0
            },
        )
        self.assertAlmostEqual(
            summary["ocean_current_total_area_km2"],
            sum(cell["area_km2"] for cell in marine_current_cells),
            delta=max(0.001, summary["ocean_current_total_area_km2"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["ocean_current_total_transport_length_km"],
            sum(edge["great_circle_distance_km"] for edge in world["ocean_current_transport_edges"]),
            delta=max(0.001, summary["ocean_current_total_transport_length_km"] * 0.0001),
        )
        self.assertGreaterEqual(summary["ocean_current_transport_coverage_fraction"], 0.0)
        self.assertLessEqual(summary["ocean_current_transport_coverage_fraction"], 1.0)
        for key in (
            "mean_ocean_circulation_speed_index",
            "mean_ocean_current_transport_alignment",
            "mean_ocean_upwelling_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.5 if key == "mean_ocean_circulation_speed_index" else 1.0)
        for key in (
            "mean_ocean_current_poleward_index",
            "mean_ocean_heat_transport_index",
            "mean_ocean_current_convergence_index",
        ):
            self.assertGreaterEqual(summary[key], -1.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertEqual(
            summary["warm_ocean_current_cell_count"],
            sum(1 for cell in marine_current_cells if cell["ocean_current_temperature_c"] >= 0.5),
        )
        self.assertEqual(
            summary["cold_ocean_current_cell_count"],
            sum(1 for cell in marine_current_cells if cell["ocean_current_temperature_c"] <= -0.5),
        )
        self.assertEqual(
            summary["poleward_ocean_current_cell_count"],
            sum(1 for cell in marine_current_cells if cell["ocean_current_poleward_index"] >= 0.08),
        )
        self.assertEqual(
            summary["equatorward_ocean_current_cell_count"],
            sum(1 for cell in marine_current_cells if cell["ocean_current_poleward_index"] <= -0.08),
        )
        self.assertEqual(
            summary["high_ocean_upwelling_cell_count"],
            sum(1 for cell in marine_current_cells if cell["ocean_upwelling_index"] >= 0.55),
        )
        current_cells_by_id = {cell["id"]: cell for cell in world["cells"]}
        for current_system in world["ocean_current_systems"]:
            self.assertEqual(current_system["cell_ids"], sorted(current_system["cell_ids"]))
        for cell in marine_current_cells:
            for neighbor_id in cell["neighbors"]:
                neighbor = current_cells_by_id[neighbor_id]
                if (
                    neighbor["water_body_type"] in {"ocean", "continental_shelf", "inland_sea"}
                    and neighbor["ocean_current_regime"] == cell["ocean_current_regime"]
                ):
                    self.assertEqual(neighbor["ocean_current_system_id"], cell["ocean_current_system_id"])
        if world["ocean_current_systems"]:
            first_current_system = world["ocean_current_systems"][0]
            self.assertEqual(first_current_system["id"], 0)
            self.assertEqual(first_current_system["cell_count"], len(first_current_system["cell_ids"]))
            self.assertGreater(first_current_system["area_km2"], 0.0)
            self.assertIn(first_current_system["system_class"], summary["ocean_current_regime_counts"])
            self.assertEqual(
                first_current_system["transport_edge_count"],
                first_current_system["internal_transport_edge_count"]
                + first_current_system["external_transport_edge_count"],
            )
            first_system_cells = [current_cells_by_id[cell_id] for cell_id in first_current_system["cell_ids"]]
            centroid_x = centroid_y = centroid_z = centroid_weight = 0.0
            for cell in first_system_cells:
                weight = cell["area_km2"] or 1.0
                latitude = math.radians(cell["lat_deg"])
                longitude = math.radians(cell["lon_deg"])
                centroid_x += math.cos(latitude) * math.cos(longitude) * weight
                centroid_y += math.cos(latitude) * math.sin(longitude) * weight
                centroid_z += math.sin(latitude) * weight
                centroid_weight += weight
            expected_centroid_lat = math.degrees(math.atan2(centroid_z, math.hypot(centroid_x, centroid_y)))
            expected_centroid_lon = math.degrees(math.atan2(centroid_y, centroid_x))
            self.assertAlmostEqual(first_current_system["centroid_lat_deg"], expected_centroid_lat, delta=0.001)
            self.assertAlmostEqual(first_current_system["centroid_lon_deg"], expected_centroid_lon, delta=0.001)
        if world["ocean_current_transport_edges"]:
            self.assertEqual(
                [edge["source_cell_id"] for edge in world["ocean_current_transport_edges"]],
                sorted(edge["source_cell_id"] for edge in world["ocean_current_transport_edges"]),
            )
            first_current_edge = world["ocean_current_transport_edges"][0]
            self.assertEqual(first_current_edge["id"], 0)
            self.assertIn(first_current_edge["target_cell_id"], world["cells"][first_current_edge["source_cell_id"]]["neighbors"])
            self.assertGreater(first_current_edge["great_circle_distance_km"], 0.0)
            self.assertGreater(first_current_edge["alignment"], 0.0)
            self.assertLessEqual(first_current_edge["alignment"], 1.0)
        self.assertIn("mean_distance_to_marine_water_km", summary)
        self.assertIn("mean_continentality_index", summary)
        self.assertIn("max_continentality_index", summary)
        self.assertIn("mean_oceanic_humidity_availability_index", summary)
        self.assertIn("marine_influence_class_counts", summary)
        self.assertEqual(sum(summary["marine_influence_class_counts"].values()), summary["cell_count"])
        self.assertEqual(summary["climate_continentality_region_count"], len(world["climate_continentality_regions"]))
        self.assertEqual(
            summary["high_continentality_cell_count"],
            sum(1 for cell in world["cells"] if cell["continentality_index"] >= 0.65),
        )
        self.assertEqual(
            summary["low_oceanic_humidity_availability_cell_count"],
            sum(1 for cell in world["cells"] if cell["oceanic_humidity_availability_index"] <= 0.25),
        )
        self.assertGreaterEqual(summary["mean_distance_to_marine_water_km"], 0.0)
        self.assertGreaterEqual(summary["mean_continentality_index"], 0.0)
        self.assertLessEqual(summary["mean_continentality_index"], 1.0)
        self.assertGreaterEqual(summary["max_continentality_index"], summary["mean_continentality_index"])
        self.assertLessEqual(summary["max_continentality_index"], 1.0)
        self.assertGreaterEqual(summary["mean_oceanic_humidity_availability_index"], 0.0)
        self.assertLessEqual(summary["mean_oceanic_humidity_availability_index"], 1.0)
        if world["climate_continentality_regions"]:
            first_continentality_region = world["climate_continentality_regions"][0]
            self.assertEqual(first_continentality_region["id"], 0)
            self.assertIn(
                first_continentality_region["region_class"],
                {"marine", "coastal", "maritime_influenced", "interior", "continental_core"},
            )
            self.assertEqual(first_continentality_region["cell_count"], len(first_continentality_region["cell_ids"]))
            self.assertGreater(first_continentality_region["area_km2"], 0.0)
            self.assertGreaterEqual(first_continentality_region["mean_continentality_index"], 0.0)
            self.assertLessEqual(first_continentality_region["mean_continentality_index"], 1.0)
            self.assertGreaterEqual(first_continentality_region["mean_oceanic_humidity_availability_index"], 0.0)
            self.assertLessEqual(first_continentality_region["mean_oceanic_humidity_availability_index"], 1.0)
        self.assertEqual(summary["climate_seasonal_history_count"], len(world["climate_seasonal_histories"]))
        self.assertEqual(summary["climate_seasonal_history_count"], len(summary["atmospheric_cell_counts"]))
        self.assertEqual(
            summary["climate_seasonal_step_count"],
            sum(history["time_step_count"] for history in world["climate_seasonal_histories"]),
        )
        self.assertEqual(sum(summary["seasonal_humidity_regime_counts"].values()), summary["cell_count"])
        self.assertEqual(world["climate_classification"]["classification_type"], "koppen_geiger_beck_2018_v0")
        self.assertEqual(world["climate_classification"]["available_class_count"], 30)
        self.assertFalse(world["climate_classification"]["confidence_resolved"])
        self.assertEqual(world["climate_classification"]["classified_cell_count"], summary["cell_count"])
        self.assertEqual(sum(summary["climate_class_counts"].values()), summary["cell_count"])
        self.assertEqual(sum(summary["climate_main_class_counts"].values()), summary["cell_count"])
        self.assertEqual(summary["climate_class_count"], len(summary["climate_class_counts"]))
        self.assertTrue(all(cell["climate_class"] in summary["climate_class_counts"] for cell in world["cells"]))
        self.assertGreaterEqual(summary["seasonal_aridity_cell_fraction"], 0.0)
        self.assertLessEqual(summary["seasonal_aridity_cell_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_cell_monsoon_index"], 0.0)
        self.assertLessEqual(summary["mean_cell_monsoon_index"], 1.0)
        self.assertGreaterEqual(summary["mean_cell_seasonal_aridity_index"], 0.0)
        self.assertLessEqual(summary["mean_cell_seasonal_aridity_index"], 1.0)
        self.assertAlmostEqual(
            summary["climate_seasonal_total_precipitation_mm"],
            sum(history["annual_precipitation_mm"] for history in world["climate_seasonal_histories"]),
            delta=max(0.001, summary["climate_seasonal_total_precipitation_mm"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["climate_seasonal_total_evaporation_mm"],
            sum(history["annual_evaporation_mm"] for history in world["climate_seasonal_histories"]),
            delta=max(0.001, summary["climate_seasonal_total_evaporation_mm"] * 0.0001),
        )
        self.assertLessEqual(summary["climate_seasonal_mean_abs_residual_mm"], 0.001)
        self.assertGreaterEqual(summary["max_climate_humidity_storage_mm"], 0.0)
        self.assertGreaterEqual(summary["max_climate_monsoon_index"], 0.0)
        self.assertLessEqual(summary["max_climate_monsoon_index"], 1.0)
        self.assertEqual(summary["climate_energy_balance_record_count"], len(world["climate_energy_balance_records"]))
        self.assertEqual(summary["climate_energy_balance_record_count"], len(world["cells"]))
        self.assertEqual(sum(summary["surface_albedo_regime_counts"].values()), summary["cell_count"])
        self.assertGreater(summary["mean_top_of_atmosphere_insolation_w_m2"], 0.0)
        self.assertGreaterEqual(summary["mean_seasonal_insolation_range_w_m2"], 0.0)
        self.assertGreaterEqual(summary["mean_orbital_insolation_variability_index"], 0.0)
        self.assertLessEqual(summary["mean_orbital_insolation_variability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_peak_seasonal_insolation_w_m2"], summary["mean_low_seasonal_insolation_w_m2"])
        self.assertGreaterEqual(summary["mean_low_seasonal_insolation_w_m2"], 0.0)
        self.assertGreater(summary["mean_orbital_distance_factor"], 0.0)
        self.assertAlmostEqual(summary["orbital_eccentricity"], small.planet.orbital_eccentricity, delta=0.001)
        self.assertGreaterEqual(summary["mean_surface_albedo_index"], 0.0)
        self.assertLessEqual(summary["mean_surface_albedo_index"], 1.0)
        self.assertGreaterEqual(summary["mean_absorbed_shortwave_w_m2"], 0.0)
        self.assertGreater(summary["mean_outgoing_longwave_w_m2"], 0.0)
        self.assertGreaterEqual(summary["mean_greenhouse_trapping_w_m2"], 0.0)
        self.assertGreaterEqual(summary["mean_abs_energy_balance_residual_c"], 0.0)
        self.assertGreaterEqual(summary["mean_climate_energy_stress_index"], 0.0)
        self.assertLessEqual(summary["mean_climate_energy_stress_index"], 1.0)
        self.assertEqual(
            summary["high_climate_energy_stress_cell_count"],
            sum(1 for record in world["climate_energy_balance_records"] if record["climate_energy_stress_index"] >= 0.65),
        )
        self.assertAlmostEqual(
            summary["mean_absorbed_shortwave_w_m2"],
            sum(record["absorbed_shortwave_w_m2"] for record in world["climate_energy_balance_records"])
            / len(world["climate_energy_balance_records"]),
            delta=0.001,
        )
        self.assertIn("planet_parameters", world)
        self.assertEqual(world["planet_parameters"]["gravity_g"], small.planet.gravity_g)
        self.assertEqual(world["planet_parameters"]["day_length_hours"], small.planet.day_length_hours)
        self.assertEqual(summary["planet_realism_check_count"], len(world["planet_realism_checks"]))
        self.assertGreaterEqual(summary["planet_realism_check_count"], 4)
        self.assertEqual(
            summary["planet_realism_pass_count"],
            sum(1 for check in world["planet_realism_checks"] if check["passed"]),
        )
        self.assertGreaterEqual(summary["planet_realism_pass_fraction"], 0.0)
        self.assertLessEqual(summary["planet_realism_pass_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_planet_realism_score"], 0.0)
        self.assertLessEqual(summary["mean_planet_realism_score"], 1.0)
        for key in [
            "global_liquid_water_temperature_index",
            "atmosphere_gravity_stability_index",
            "rotation_circulation_plausibility_index",
            "surface_water_inventory_index",
        ]:
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        planet_check_names = {check["name"] for check in world["planet_realism_checks"]}
        self.assertTrue(
            {
                "liquid_water_temperature_window",
                "atmosphere_gravity_stability",
                "rotation_circulation_plausibility",
                "surface_water_inventory",
            }.issubset(planet_check_names)
        )
        first_planet_check = world["planet_realism_checks"][0]
        self.assertEqual(first_planet_check["domain"], "planet")
        self.assertIn("evidence", first_planet_check)
        self.assertGreaterEqual(first_planet_check["score"], 0.0)
        self.assertLessEqual(first_planet_check["score"], 1.0)
        self.assertEqual(summary["climate_realism_check_count"], len(world["climate_realism_checks"]))
        self.assertGreaterEqual(summary["climate_realism_check_count"], 6)
        self.assertEqual(
            summary["climate_realism_pass_count"],
            sum(1 for check in world["climate_realism_checks"] if check["passed"]),
        )
        self.assertGreaterEqual(summary["climate_realism_pass_fraction"], 0.0)
        self.assertLessEqual(summary["climate_realism_pass_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_climate_realism_score"], 0.0)
        self.assertLessEqual(summary["mean_climate_realism_score"], 1.0)
        for key in (
            "subtropical_dry_belt_index",
            "equatorial_ocean_humidity_index",
            "orographic_rain_shadow_index",
            "continentality_temperature_range_index",
            "cold_current_coastal_drying_index",
            "warm_current_moderation_index",
        ):
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        climate_names = {check["name"] for check in world["climate_realism_checks"]}
        self.assertTrue(
            {
                "subtropical_dry_belt",
                "equatorial_ocean_humidity",
                "orographic_rain_shadow",
                "continental_interior_extremes",
                "cold_current_coastal_drying",
                "warm_current_climate_moderation",
            }.issubset(climate_names)
        )
        first_climate_check = world["climate_realism_checks"][0]
        for key in ("domain", "question", "metric", "value", "target_min", "target_max", "score", "passed", "evidence"):
            self.assertIn(key, first_climate_check)
        self.assertEqual(first_climate_check["domain"], "climate")
        self.assertGreaterEqual(first_climate_check["score"], 0.0)
        self.assertLessEqual(first_climate_check["score"], 1.0)
        self.assertIn("mean_ice_thickness_m", summary)
        self.assertIn("mean_glacial_erosion_m", summary)
        self.assertIn("mean_ice_surface_mass_balance_m_y", summary)
        self.assertGreaterEqual(summary["mean_ice_surface_mass_balance_m_y"], -4.0)
        self.assertLessEqual(summary["mean_ice_surface_mass_balance_m_y"], 3.2)
        self.assertIn("mean_basal_sliding_index", summary)
        self.assertGreaterEqual(summary["mean_basal_sliding_index"], 0.0)
        self.assertLessEqual(summary["mean_basal_sliding_index"], 1.0)
        self.assertIn("mean_ice_velocity_m_y", summary)
        self.assertGreaterEqual(summary["mean_ice_velocity_m_y"], 0.0)
        self.assertIn("glaciated_land_fraction", summary)
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
        self.assertEqual(summary["biome_diagnostic_count"], len(world["biome_diagnostics"]))
        self.assertEqual(summary["biome_diagnostic_count"], len(world["cells"]))
        self.assertEqual(
            sum(summary["biome_limiting_factor_counts"].values()),
            summary["biome_diagnostic_count"],
        )
        self.assertEqual(
            summary["biome_transition_zone_count"],
            sum(1 for diagnostic in world["biome_diagnostics"] if diagnostic["biome_transition_zone"]),
        )
        self.assertEqual(
            summary["high_fire_frequency_biome_count"],
            sum(1 for diagnostic in world["biome_diagnostics"] if diagnostic["fire_frequency_index"] >= 0.65),
        )
        self.assertGreaterEqual(summary["water_stressed_biome_cell_fraction"], 0.0)
        self.assertLessEqual(summary["water_stressed_biome_cell_fraction"], 1.0)
        self.assertGreaterEqual(summary["biome_expected_match_fraction"], 0.0)
        self.assertLessEqual(summary["biome_expected_match_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_potential_evapotranspiration_mm_y"], 0.0)
        self.assertGreaterEqual(summary["mean_climatic_water_deficit_mm_y"], 0.0)
        self.assertGreaterEqual(summary["mean_growing_season_months"], 0.0)
        self.assertLessEqual(summary["mean_growing_season_months"], 12.0)
        for key in ("mean_fire_frequency_index", "mean_biome_confidence_index", "mean_ecotone_index"):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertAlmostEqual(
            summary["mean_fire_frequency_index"],
            sum(diagnostic["fire_frequency_index"] for diagnostic in world["biome_diagnostics"])
            / len(world["biome_diagnostics"]),
            delta=0.001,
        )
        self.assertAlmostEqual(
            summary["mean_potential_evapotranspiration_mm_y"],
            sum(diagnostic["potential_evapotranspiration_mm_y"] for diagnostic in world["biome_diagnostics"])
            / len(world["biome_diagnostics"]),
            delta=0.001,
        )
        ecotone_cells = [cell for cell in world["cells"] if cell["biome_ecotone_type"] != "none"]
        self.assertEqual(summary["biome_ecotone_cell_count"], len(ecotone_cells))
        self.assertEqual(summary["biome_ecotone_region_count"], len(world["biome_ecotone_regions"]))
        self.assertEqual(sum(summary["biome_ecotone_type_counts"].values()), summary["cell_count"])
        self.assertEqual(
            summary["mangrove_ecotone_cell_count"],
            sum(1 for cell in world["cells"] if cell["biome_ecotone_type"] == "mangrove"),
        )
        self.assertEqual(
            summary["cloud_forest_ecotone_cell_count"],
            sum(1 for cell in world["cells"] if cell["biome_ecotone_type"] == "cloud_forest"),
        )
        self.assertEqual(
            summary["alpine_paramo_ecotone_cell_count"],
            sum(1 for cell in world["cells"] if cell["biome_ecotone_type"] == "alpine_paramo"),
        )
        self.assertGreater(summary["biome_ecotone_cell_count"], 0)
        self.assertGreaterEqual(summary["mean_biome_ecotone_confidence"], 0.0)
        self.assertLessEqual(summary["mean_biome_ecotone_confidence"], 1.0)
        self.assertEqual(
            {cell_id for region in world["biome_ecotone_regions"] for cell_id in region["cell_ids"]},
            {cell["id"] for cell in ecotone_cells},
        )
        self.assertEqual(summary["biome_realism_check_count"], len(world["biome_realism_checks"]))
        self.assertGreaterEqual(summary["biome_realism_check_count"], 5)
        self.assertEqual(
            summary["biome_realism_pass_count"],
            sum(1 for check in world["biome_realism_checks"] if check["passed"]),
        )
        self.assertGreaterEqual(summary["biome_realism_pass_fraction"], 0.0)
        self.assertLessEqual(summary["biome_realism_pass_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_biome_realism_score"], 0.0)
        self.assertLessEqual(summary["mean_biome_realism_score"], 1.0)
        for key in [
            "desert_water_deficit_alignment_index",
            "forest_water_availability_index",
            "tundra_cold_altitude_index",
            "savanna_seasonality_index",
            "mangrove_warm_wet_coast_index",
        ]:
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        biome_realism_names = {check["name"] for check in world["biome_realism_checks"]}
        self.assertTrue(
            {
                "desert_water_deficit_alignment",
                "forest_water_availability_alignment",
                "tundra_cold_altitude_alignment",
                "savanna_seasonality_alignment",
                "mangrove_warm_wet_coast_constraint",
            }.issubset(biome_realism_names)
        )
        first_biome_check = world["biome_realism_checks"][0]
        self.assertEqual(first_biome_check["domain"], "biomes")
        self.assertIn("evidence", first_biome_check)
        self.assertGreaterEqual(first_biome_check["score"], 0.0)
        self.assertLessEqual(first_biome_check["score"], 1.0)
        aquifer_cells = [cell for cell in world["cells"] if cell["aquifer_class"] != "marine_excluded"]
        self.assertEqual(summary["aquifer_cell_count"], len(aquifer_cells))
        self.assertEqual(summary["aquifer_system_count"], len(world["aquifer_systems"]))
        self.assertEqual(sum(summary["aquifer_class_counts"].values()), summary["cell_count"])
        self.assertEqual(
            summary["groundwater_recharge_cell_count"],
            sum(1 for cell in aquifer_cells if cell["groundwater_recharge_mm_y"] >= 50.0),
        )
        self.assertEqual(
            summary["high_productivity_aquifer_cell_count"],
            sum(1 for cell in aquifer_cells if cell["aquifer_productivity_index"] >= 0.65),
        )
        self.assertEqual(
            summary["groundwater_stressed_cell_count"],
            sum(1 for cell in aquifer_cells if cell["aquifer_extraction_risk_index"] >= 0.65),
        )
        self.assertGreaterEqual(summary["total_groundwater_recharge_km3_y"], 0.0)
        for key in (
            "mean_aquifer_storage_index",
            "mean_aquifer_quality_index",
            "mean_aquifer_productivity_index",
            "mean_aquifer_extraction_risk_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        if aquifer_cells:
            self.assertAlmostEqual(
                summary["mean_groundwater_recharge_mm_y"],
                sum(cell["groundwater_recharge_mm_y"] for cell in aquifer_cells) / len(aquifer_cells),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["total_groundwater_recharge_km3_y"],
                sum(cell["groundwater_recharge_km3_y"] for cell in aquifer_cells),
                delta=max(0.001, summary["total_groundwater_recharge_km3_y"] * 0.0001),
            )
        groundwater_flow_cells = [cell for cell in aquifer_cells if cell["groundwater_flow_system_id"] >= 0]
        self.assertEqual(summary["groundwater_flow_cell_count"], len(groundwater_flow_cells))
        self.assertEqual(summary["groundwater_flow_system_count"], len(world["groundwater_flow_systems"]))
        self.assertEqual(
            summary["groundwater_flow_model"],
            "descending_head_recharge_conserving_groundwater_flow_v1",
        )
        self.assertEqual(sum(summary["groundwater_flow_regime_counts"].values()), summary["cell_count"])
        self.assertEqual(
            summary["groundwater_discharge_cell_count"],
            sum(1 for cell in aquifer_cells if cell["groundwater_discharge_mm_y"] >= 25.0),
        )
        self.assertEqual(
            summary["spring_candidate_cell_count"],
            sum(1 for cell in aquifer_cells if cell["spring_discharge_index"] >= 0.45),
        )
        self.assertEqual(
            summary["baseflow_supported_river_cell_count"],
            sum(1 for cell in aquifer_cells if cell["is_river"] and cell["baseflow_support_index"] >= 0.35),
        )
        self.assertGreaterEqual(summary["total_groundwater_discharge_km3_y"], 0.0)
        self.assertGreaterEqual(summary["total_groundwater_lateral_flow_km3_y"], 0.0)
        self.assertGreaterEqual(
            summary["total_groundwater_internal_lateral_flow_km3_y"],
            0.0,
        )
        self.assertGreaterEqual(
            summary["total_groundwater_retained_storage_km3_y"],
            0.0,
        )
        self.assertEqual(
            summary["groundwater_flow_mass_balance_residual_km3_y"],
            0.0,
        )
        for key in (
            "mean_groundwater_gradient_index",
            "mean_spring_discharge_index",
            "mean_baseflow_support_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        if aquifer_cells:
            self.assertAlmostEqual(
                summary["mean_groundwater_gradient_index"],
                sum(cell["groundwater_gradient_index"] for cell in aquifer_cells) / len(aquifer_cells),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["mean_groundwater_discharge_mm_y"],
                sum(cell["groundwater_discharge_mm_y"] for cell in aquifer_cells) / len(aquifer_cells),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["total_groundwater_discharge_km3_y"],
                sum(cell["groundwater_discharge_km3_y"] for cell in aquifer_cells),
                delta=max(0.001, summary["total_groundwater_discharge_km3_y"] * 0.0001),
            )
            self.assertAlmostEqual(
                summary["total_groundwater_flow_balance_residual_km3_y"],
                sum(cell["groundwater_recharge_km3_y"] for cell in aquifer_cells)
                - sum(cell["groundwater_discharge_km3_y"] for cell in aquifer_cells),
                delta=max(0.001, abs(summary["total_groundwater_flow_balance_residual_km3_y"]) * 0.0001),
            )
            self.assertAlmostEqual(
                summary["total_groundwater_recharge_km3_y"],
                summary["total_groundwater_discharge_km3_y"]
                + summary["total_groundwater_retained_storage_km3_y"],
                delta=0.001,
            )
        karst_cells = [cell for cell in world["cells"] if cell["karst_potential_index"] >= 0.45]
        limestone_land_cells = [
            cell for cell in world["cells"] if cell["lithology"] == "limestone" and not cell["is_water"]
        ]
        self.assertEqual(summary["karst_cell_count"], len(karst_cells))
        self.assertEqual(summary["karst_system_count"], len(world["karst_systems"]))
        self.assertGreaterEqual(summary["mean_karst_potential_index"], 0.0)
        self.assertLessEqual(summary["mean_karst_potential_index"], 1.0)
        self.assertGreaterEqual(summary["mean_cave_development_index"], 0.0)
        self.assertLessEqual(summary["mean_cave_development_index"], 1.0)
        self.assertGreaterEqual(summary["mean_subterranean_drainage_fraction"], 0.0)
        self.assertLessEqual(summary["mean_subterranean_drainage_fraction"], 1.0)
        self.assertGreaterEqual(summary["limestone_karst_cell_fraction"], 0.0)
        self.assertLessEqual(summary["limestone_karst_cell_fraction"], 1.0)
        self.assertAlmostEqual(
            summary["mean_karst_potential_index"],
            sum(cell["karst_potential_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        if limestone_land_cells:
            self.assertAlmostEqual(
                summary["limestone_karst_cell_fraction"],
                sum(1 for cell in limestone_land_cells if cell["karst_potential_index"] >= 0.45)
                / len(limestone_land_cells),
                delta=0.001,
            )
        self.assertEqual(
            {cell_id for system in world["karst_systems"] for cell_id in system["cell_ids"]},
            {cell["id"] for cell in karst_cells},
        )
        self.assertEqual(summary["vegetation_succession_history_count"], len(world["vegetation_succession_histories"]))
        self.assertEqual(
            summary["vegetation_succession_step_count"],
            sum(history["step_count"] for history in world["vegetation_succession_histories"]),
        )
        self.assertEqual(sum(summary["vegetation_succession_stage_counts"].values()), summary["cell_count"])
        for key in (
            "mean_primary_productivity_index",
            "mean_vegetation_biomass_index",
            "mean_species_richness_index",
            "mean_wildfire_spread_risk_index",
            "mean_ecosystem_disturbance_pressure_index",
            "mature_vegetation_cell_fraction",
            "mean_forest_growth_index",
            "mean_fishery_productivity_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertEqual(
            summary["high_wildfire_spread_risk_cell_count"],
            sum(1 for cell in world["cells"] if cell["wildfire_spread_risk_index"] >= 0.65),
        )
        self.assertEqual(summary["renewable_resource_record_count"], len(world["renewable_resource_records"]))
        self.assertEqual(
            summary["forest_growth_resource_count"],
            sum(1 for record in world["renewable_resource_records"] if record["resource_type"] == "forest_growth"),
        )
        self.assertEqual(
            summary["fishery_productivity_resource_count"],
            sum(1 for record in world["renewable_resource_records"] if record["resource_type"] == "fishery_productivity"),
        )
        self.assertEqual(
            sum(summary["renewable_resource_type_counts"].values()),
            summary["renewable_resource_record_count"],
        )
        self.assertAlmostEqual(
            summary["mean_primary_productivity_index"],
            sum(cell["primary_productivity_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        self.assertEqual(summary["species_range_record_count"], len(world["species_range_records"]))
        species_range_cell_ids = {
            cell_id for record in world["species_range_records"] for cell_id in record["cell_ids"]
        }
        self.assertEqual(summary["species_range_cell_count"], len(species_range_cell_ids))
        self.assertEqual(
            sum(summary["species_guild_type_counts"].values()),
            summary["species_range_record_count"],
        )
        self.assertEqual(
            sum(summary["species_habitat_class_counts"].values()),
            summary["species_range_record_count"],
        )
        self.assertEqual(
            sum(summary["dominant_species_guild_counts"].values()),
            summary["cell_count"],
        )
        self.assertEqual(
            summary["terrestrial_species_range_count"],
            sum(1 for record in world["species_range_records"] if record["habitat_class"] in {"terrestrial", "arid", "alpine"}),
        )
        self.assertEqual(
            summary["aquatic_species_range_count"],
            sum(1 for record in world["species_range_records"] if record["habitat_class"] in {"freshwater", "marine", "reef"}),
        )
        self.assertEqual(
            summary["wetland_species_range_count"],
            sum(1 for record in world["species_range_records"] if record["habitat_class"] == "wetland"),
        )
        for key in (
            "mean_species_habitat_suitability_index",
            "mean_species_endemism_index",
            "mean_species_composition_confidence_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertAlmostEqual(
            summary["mean_species_habitat_suitability_index"],
            sum(cell["species_habitat_suitability_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        self.assertGreaterEqual(summary["species_range_total_area_km2"], 0.0)
        self.assertEqual(summary["wildfire_spread_history_count"], len(world["wildfire_spread_histories"]))
        wildfire_cell_ids = {
            cell_id for history in world["wildfire_spread_histories"] for cell_id in history["cell_ids"]
        }
        self.assertEqual(summary["wildfire_disturbance_cell_count"], len(wildfire_cell_ids))
        self.assertEqual(
            summary["wildfire_spread_step_count"],
            sum(history["spread_step_count"] for history in world["wildfire_spread_histories"]),
        )
        self.assertEqual(
            summary["high_wildfire_ignition_potential_cell_count"],
            sum(1 for cell in world["cells"] if cell["wildfire_ignition_potential_index"] >= 0.28),
        )
        self.assertEqual(
            summary["high_wildfire_fuel_continuity_cell_count"],
            sum(1 for cell in world["cells"] if cell["wildfire_fuel_continuity_index"] >= 0.35),
        )
        self.assertEqual(
            summary["high_wildfire_firebreak_cell_count"],
            sum(1 for cell in world["cells"] if cell["wildfire_firebreak_index"] >= 0.55),
        )
        self.assertEqual(sum(summary["wildfire_disturbance_regime_counts"].values()), summary["cell_count"])
        for key in (
            "mean_wildfire_ignition_potential_index",
            "mean_wildfire_fuel_continuity_index",
            "mean_wildfire_wind_alignment_index",
            "mean_wildfire_firebreak_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertGreaterEqual(summary["wildfire_total_burned_area_km2"], 0.0)
        resource_cells = [cell for cell in world["cells"] if cell["resource"] != "none"]
        self.assertEqual(summary["resource_deposit_count"], len(world["resource_deposits"]))
        self.assertEqual(summary["resource_deposit_count"], len(resource_cells))
        self.assertEqual(
            sum(summary["resource_deposit_class_counts"].values()),
            summary["resource_deposit_count"],
        )
        self.assertEqual(
            summary["metal_resource_deposit_count"],
            sum(1 for deposit in world["resource_deposits"] if deposit["deposit_class"] == "metal"),
        )
        self.assertEqual(
            summary["energy_resource_deposit_count"],
            sum(1 for deposit in world["resource_deposits"] if deposit["deposit_class"] == "energy"),
        )
        self.assertEqual(
            summary["agricultural_resource_deposit_count"],
            sum(1 for deposit in world["resource_deposits"] if deposit["deposit_class"] == "bioproductive"),
        )
        self.assertEqual(
            summary["high_viability_resource_deposit_count"],
            sum(1 for deposit in world["resource_deposits"] if deposit["economic_viability_index"] >= 0.65),
        )
        self.assertGreaterEqual(summary["resource_deposit_total_area_km2"], 0.0)
        self.assertGreaterEqual(summary["mean_resource_reserve_potential_index"], 0.0)
        self.assertLessEqual(summary["mean_resource_reserve_potential_index"], 1.0)
        self.assertGreaterEqual(summary["mean_resource_economic_viability_index"], 0.0)
        self.assertLessEqual(summary["mean_resource_economic_viability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_resource_geologic_confidence_index"], 0.0)
        self.assertLessEqual(summary["mean_resource_geologic_confidence_index"], 1.0)
        if world["resource_deposits"]:
            self.assertAlmostEqual(
                summary["mean_resource_reserve_potential_index"],
                sum(deposit["reserve_potential_index"] for deposit in world["resource_deposits"])
                / len(world["resource_deposits"]),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["resource_deposit_total_area_km2"],
                sum(deposit["area_km2"] for deposit in world["resource_deposits"]),
                delta=max(0.001, summary["resource_deposit_total_area_km2"] * 0.0001),
            )
        ore_type_counts: dict[str, int] = {}
        for system in world["ore_genesis_systems"]:
            ore_type_counts[system["system_type"]] = ore_type_counts.get(system["system_type"], 0) + 1
        self.assertEqual(summary["ore_genesis_system_count"], len(world["ore_genesis_systems"]))
        self.assertEqual(summary["ore_genesis_system_type_counts"], dict(sorted(ore_type_counts.items())))
        self.assertEqual(sum(summary["ore_genesis_system_type_counts"].values()), summary["ore_genesis_system_count"])
        self.assertEqual(
            summary["ore_genesis_cell_count"],
            len({cell_id for system in world["ore_genesis_systems"] for cell_id in system["cell_ids"]}),
        )
        ore_resources = {"volcanic_arc_metals", "craton_iron_gold", "placer_metals", "geothermal"}
        self.assertEqual(
            summary["ore_resource_deposit_count"],
            sum(1 for deposit in world["resource_deposits"] if deposit["resource"] in ore_resources),
        )
        self.assertEqual(
            summary["high_ore_genesis_potential_cell_count"],
            sum(1 for cell in world["cells"] if cell["ore_genesis_potential_index"] >= 0.50),
        )
        self.assertEqual(
            summary["high_hydrothermal_alteration_cell_count"],
            sum(1 for cell in world["cells"] if cell["hydrothermal_alteration_index"] >= 0.34),
        )
        self.assertEqual(
            summary["high_metallogenic_fertility_cell_count"],
            sum(1 for cell in world["cells"] if cell["metallogenic_fertility_index"] >= 0.42),
        )
        self.assertEqual(
            summary["high_placer_concentration_cell_count"],
            sum(1 for cell in world["cells"] if cell["placer_concentration_index"] >= 0.32),
        )
        self.assertAlmostEqual(
            summary["ore_genesis_total_area_km2"],
            sum(system["area_km2"] for system in world["ore_genesis_systems"]),
            delta=max(0.001, summary["ore_genesis_total_area_km2"] * 0.0001),
        )
        for key in (
            "mean_ore_genesis_potential_index",
            "mean_hydrothermal_alteration_index",
            "mean_metallogenic_fertility_index",
            "mean_ore_structural_control_index",
            "mean_placer_concentration_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertAlmostEqual(
            summary["mean_ore_genesis_potential_index"],
            sum(cell["ore_genesis_potential_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
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
        for system in world["petroleum_migration_systems"]:
            petroleum_migration_type_counts[system["system_type"]] = (
                petroleum_migration_type_counts.get(system["system_type"], 0) + 1
            )
        self.assertEqual(summary["petroleum_migration_system_count"], len(world["petroleum_migration_systems"]))
        self.assertEqual(
            summary["petroleum_migration_system_type_counts"],
            dict(sorted(petroleum_migration_type_counts.items())),
        )
        self.assertEqual(
            sum(summary["petroleum_migration_system_type_counts"].values()),
            summary["petroleum_migration_system_count"],
        )
        self.assertEqual(
            summary["petroleum_migration_cell_count"],
            len({cell_id for system in world["petroleum_migration_systems"] for cell_id in system["cell_ids"]}),
        )
        self.assertEqual(
            summary["petroleum_source_rock_cell_count"],
            sum(1 for cell in world["cells"] if cell["petroleum_source_rock_index"] >= 0.42),
        )
        self.assertEqual(
            summary["petroleum_mature_source_cell_count"],
            sum(
                1
                for cell in world["cells"]
                if cell["petroleum_source_rock_index"] >= 0.42 and cell["petroleum_maturation_index"] >= 0.42
            ),
        )
        self.assertEqual(
            summary["petroleum_trap_cell_count"],
            sum(1 for cell in world["cells"] if cell["petroleum_trap_integrity_index"] >= 0.34),
        )
        self.assertEqual(
            summary["high_petroleum_accumulation_cell_count"],
            sum(1 for cell in world["cells"] if cell["petroleum_accumulation_index"] >= 0.50),
        )
        self.assertAlmostEqual(
            summary["petroleum_migration_total_area_km2"],
            sum(system["area_km2"] for system in world["petroleum_migration_systems"]),
            delta=max(0.001, summary["petroleum_migration_total_area_km2"] * 0.0001),
        )
        for key in (
            "mean_petroleum_source_rock_index",
            "mean_petroleum_maturation_index",
            "mean_petroleum_migration_path_index",
            "mean_petroleum_trap_integrity_index",
            "mean_petroleum_accumulation_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertAlmostEqual(
            summary["mean_petroleum_accumulation_index"],
            sum(cell["petroleum_accumulation_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        allowed_commodities_by_resource = {
            "volcanic_arc_metals": {"copper", "gold", "silver", "sulfide_ore"},
            "craton_iron_gold": {"iron", "gold", "diamond"},
            "sedimentary_fuels": {"coal", "petroleum", "natural_gas"},
            "evaporites": {"salt", "gypsum", "potash"},
            "placer_metals": {"placer_gold", "tin"},
            "geothermal": {"geothermal_heat", "sulfur", "obsidian"},
            "fertile_alluvium": {"fertile_soils"},
            "coastal_fisheries": {"fishery_biomass"},
        }
        commodity_type_counts: dict[str, int] = {}
        commodity_group_counts: dict[str, int] = {}
        for occurrence in world["commodity_occurrences"]:
            commodity_type_counts[occurrence["commodity"]] = commodity_type_counts.get(occurrence["commodity"], 0) + 1
            commodity_group_counts[occurrence["commodity_group"]] = (
                commodity_group_counts.get(occurrence["commodity_group"], 0) + 1
            )
        self.assertEqual(summary["commodity_occurrence_count"], len(world["commodity_occurrences"]))
        self.assertEqual(
            summary["commodity_occurrence_count"],
            sum(len(allowed_commodities_by_resource.get(deposit["resource"], set())) for deposit in world["resource_deposits"]),
        )
        self.assertEqual(summary["commodity_occurrence_type_counts"], dict(sorted(commodity_type_counts.items())))
        self.assertEqual(summary["commodity_occurrence_group_counts"], dict(sorted(commodity_group_counts.items())))
        self.assertEqual(sum(summary["commodity_occurrence_type_counts"].values()), summary["commodity_occurrence_count"])
        self.assertEqual(sum(summary["commodity_occurrence_group_counts"].values()), summary["commodity_occurrence_count"])
        self.assertEqual(
            summary["metallic_commodity_occurrence_count"],
            sum(commodity_group_counts.get(group, 0) for group in ("base_metal", "ferrous_metal", "precious_metal")),
        )
        self.assertEqual(summary["fuel_commodity_occurrence_count"], commodity_group_counts.get("fuel", 0))
        self.assertEqual(
            summary["industrial_mineral_commodity_occurrence_count"],
            commodity_group_counts.get("industrial_mineral", 0),
        )
        self.assertEqual(summary["gemstone_commodity_occurrence_count"], commodity_group_counts.get("gemstone", 0))
        self.assertEqual(summary["geothermal_commodity_occurrence_count"], commodity_group_counts.get("geothermal", 0))
        self.assertEqual(
            summary["bioproductive_commodity_occurrence_count"],
            commodity_group_counts.get("agricultural", 0) + commodity_group_counts.get("fishery", 0),
        )
        self.assertEqual(
            summary["high_potential_commodity_occurrence_count"],
            sum(1 for occurrence in world["commodity_occurrences"] if occurrence["occurrence_potential_index"] >= 0.62),
        )
        self.assertAlmostEqual(
            summary["commodity_occurrence_total_area_km2"],
            sum(occurrence["area_km2"] for occurrence in world["commodity_occurrences"]),
            delta=max(0.001, summary["commodity_occurrence_total_area_km2"] * 0.0001),
        )
        for key in ("mean_commodity_occurrence_potential_index", "mean_commodity_occurrence_confidence_index"):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        if world["commodity_occurrences"]:
            self.assertAlmostEqual(
                summary["mean_commodity_occurrence_potential_index"],
                sum(occurrence["occurrence_potential_index"] for occurrence in world["commodity_occurrences"])
                / len(world["commodity_occurrences"]),
                delta=0.001,
            )
        agricultural_candidate_ids = {
            cell["id"] for cell in world["cells"] if cell["agricultural_potential_index"] >= 0.58
        }
        mining_candidate_ids = {cell["id"] for cell in world["cells"] if cell["mining_potential_index"] >= 0.52}
        self.assertEqual(summary["agricultural_zone_count"], len(world["agricultural_zones"]))
        self.assertEqual(summary["mining_zone_count"], len(world["mining_zones"]))
        self.assertEqual(summary["agricultural_zone_cell_count"], len(agricultural_candidate_ids))
        self.assertEqual(summary["mining_zone_cell_count"], len(mining_candidate_ids))
        self.assertEqual(
            {cell_id for zone in world["agricultural_zones"] for cell_id in zone["cell_ids"]},
            agricultural_candidate_ids,
        )
        self.assertEqual(
            {cell_id for zone in world["mining_zones"] for cell_id in zone["cell_ids"]},
            mining_candidate_ids,
        )
        self.assertAlmostEqual(
            summary["agricultural_zone_total_area_km2"],
            sum(zone["area_km2"] for zone in world["agricultural_zones"]),
            delta=max(0.001, summary["agricultural_zone_total_area_km2"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["mining_zone_total_area_km2"],
            sum(zone["area_km2"] for zone in world["mining_zones"]),
            delta=max(0.001, summary["mining_zone_total_area_km2"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["mean_agricultural_potential_index"],
            sum(cell["agricultural_potential_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        self.assertAlmostEqual(
            summary["mean_mining_potential_index"],
            sum(cell["mining_potential_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        natural_frontier_candidate_ids = {
            cell["id"] for cell in world["cells"] if cell["natural_frontier_index"] >= 0.45
        }
        self.assertEqual(summary["natural_frontier_count"], len(world["natural_frontiers"]))
        self.assertEqual(summary["natural_frontier_cell_count"], len(natural_frontier_candidate_ids))
        self.assertEqual(
            {cell_id for frontier in world["natural_frontiers"] for cell_id in frontier["cell_ids"]},
            natural_frontier_candidate_ids,
        )
        self.assertEqual(
            summary["natural_frontier_border_segment_count"],
            sum(frontier["border_segment_count"] for frontier in world["natural_frontiers"]),
        )
        self.assertAlmostEqual(
            summary["natural_frontier_total_area_km2"],
            sum(frontier["area_km2"] for frontier in world["natural_frontiers"]),
            delta=max(0.001, summary["natural_frontier_total_area_km2"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["natural_frontier_total_length_km"],
            sum(frontier["total_border_length_km"] for frontier in world["natural_frontiers"]),
            delta=max(0.001, summary["natural_frontier_total_length_km"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["mean_natural_frontier_index"],
            sum(cell["natural_frontier_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        self.assertEqual(sum(summary["natural_frontier_type_counts"].values()), summary["natural_frontier_count"])
        for key in (
            "mountain_frontier_count",
            "river_frontier_count",
            "desert_frontier_count",
            "coastal_frontier_count",
            "ice_frontier_count",
            "dense_forest_frontier_count",
            "wetland_frontier_count",
        ):
            self.assertIn(key, summary)
        self.assertEqual(summary["worldbuilding_realism_check_count"], len(world["worldbuilding_realism_checks"]))
        self.assertGreaterEqual(summary["worldbuilding_realism_check_count"], 5)
        self.assertEqual(
            summary["worldbuilding_realism_pass_count"],
            sum(1 for check in world["worldbuilding_realism_checks"] if check["passed"]),
        )
        self.assertGreaterEqual(summary["worldbuilding_realism_pass_fraction"], 0.0)
        self.assertLessEqual(summary["worldbuilding_realism_pass_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_worldbuilding_realism_score"], 0.0)
        self.assertLessEqual(summary["mean_worldbuilding_realism_score"], 1.0)
        for key in [
            "large_settlement_water_access_index",
            "route_barrier_avoidance_index",
            "political_region_connectivity_index",
            "natural_border_alignment_index",
            "resource_geology_dependency_index",
        ]:
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        worldbuilding_check_names = {check["name"] for check in world["worldbuilding_realism_checks"]}
        self.assertTrue(
            {
                "large_settlement_water_access",
                "route_barrier_avoidance",
                "political_region_connectivity",
                "natural_border_alignment",
                "resource_geology_dependency",
            }.issubset(worldbuilding_check_names)
        )
        first_worldbuilding_check = world["worldbuilding_realism_checks"][0]
        self.assertEqual(first_worldbuilding_check["domain"], "worldbuilding")
        self.assertIn("evidence", first_worldbuilding_check)
        self.assertGreaterEqual(first_worldbuilding_check["score"], 0.0)
        self.assertLessEqual(first_worldbuilding_check["score"], 1.0)
        self.assertEqual(summary["settlement_count"], len(world["settlements"]))
        self.assertEqual(summary["route_count"], len(world["routes"]))
        self.assertEqual(summary["trade_flow_count"], len(world["trade_flows"]))
        self.assertIn("trade_total_volume_index", summary)
        self.assertIn("interregional_trade_fraction", summary)
        self.assertIn("mean_trade_friction", summary)
        self.assertEqual(summary["political_region_count"], len(world["political_regions"]))
        self.assertGreater(summary["political_region_count"], 0)
        self.assertEqual(summary["plate_graph_node_count"], len(world["plate_graph"]["nodes"]))
        self.assertEqual(summary["plate_graph_node_count"], len(world["plates"]))
        self.assertEqual(summary["plate_graph_edge_count"], len(world["plate_graph"]["edges"]))
        self.assertEqual(summary["plate_graph_boundary_cell_edge_count"], world["plate_graph"]["boundary_cell_edge_count"])
        self.assertEqual(summary["river_graph_node_count"], len(world["river_graph"]["nodes"]))
        self.assertEqual(
            summary["river_graph_node_count"],
            sum(1 for cell in world["cells"] if cell["is_river"]),
        )
        self.assertEqual(summary["river_graph_edge_count"], len(world["river_graph"]["edges"]))
        self.assertAlmostEqual(
            summary["river_graph_total_channel_length_km"],
            sum(edge["length_km"] for edge in world["river_graph"]["edges"]),
            delta=max(0.001, summary["river_graph_total_channel_length_km"] * 0.0001),
        )
        self.assertEqual(summary["watershed_graph_node_count"], len(world["watershed_graph"]["nodes"]))
        self.assertEqual(summary["watershed_graph_node_count"], len(world["watersheds"]))
        self.assertEqual(summary["watershed_graph_edge_count"], len(world["watershed_graph"]["edges"]))
        self.assertEqual(summary["watershed_graph_boundary_edge_count"], world["watershed_graph"]["boundary_edge_count"])
        self.assertEqual(summary["trade_route_graph_node_count"], len(world["trade_route_graph"]["nodes"]))
        self.assertEqual(summary["trade_route_graph_node_count"], len(world["settlements"]))
        self.assertEqual(summary["trade_route_graph_edge_count"], len(world["trade_route_graph"]["edges"]))
        self.assertEqual(summary["trade_route_graph_edge_count"], len(world["routes"]))
        self.assertEqual(
            summary["interregional_trade_route_graph_edge_count"],
            sum(1 for edge in world["trade_route_graph"]["edges"] if edge["interregional"]),
        )
        self.assertAlmostEqual(
            summary["trade_route_graph_total_volume_index"],
            sum(edge["volume_index"] for edge in world["trade_route_graph"]["edges"]),
            delta=max(0.001, summary["trade_route_graph_total_volume_index"] * 0.0001),
        )
        self.assertEqual(summary["political_region_graph_node_count"], len(world["political_region_graph"]["nodes"]))
        self.assertEqual(summary["political_region_graph_node_count"], len(world["political_regions"]))
        self.assertEqual(summary["political_region_graph_edge_count"], len(world["political_region_graph"]["edges"]))
        self.assertEqual(summary["political_region_graph_border_segment_count"], len(world["borders"]))
        self.assertEqual(
            summary["political_region_graph_trade_edge_count"],
            sum(1 for edge in world["political_region_graph"]["edges"] if edge["trade_flow_ids"]),
        )
        self.assertEqual(summary["culture_region_count"], len(world["cultures"]))
        self.assertGreater(summary["culture_region_count"], 0)
        self.assertEqual(summary["language_region_count"], len(world["language_regions"]))
        self.assertGreater(summary["language_region_count"], 0)
        self.assertEqual(summary["historical_era_count"], len(world["historical_eras"]))
        self.assertGreater(summary["historical_era_count"], 0)
        self.assertEqual(summary["historical_event_count"], len(world["historical_events"]))
        self.assertGreater(summary["historical_event_count"], 0)
        self.assertIn("migration_event_count", summary)
        self.assertEqual(
            summary["migration_event_count"],
            sum(1 for event in world["historical_events"] if event["type"] == "migration"),
        )
        self.assertIn("dynastic_change_count", summary)
        self.assertEqual(
            summary["dynastic_change_count"],
            sum(1 for event in world["historical_events"] if event["type"] == "dynastic_change"),
        )
        self.assertIn("language_lineage_count", summary)
        self.assertEqual(
            summary["language_lineage_count"],
            sum(1 for language in world["language_regions"] if language["parent_language_region_id"] >= 0),
        )
        if summary["language_region_count"] > 1:
            self.assertGreater(summary["language_lineage_count"], 0)
        self.assertIn("mean_historical_instability", summary)
        self.assertIn("mean_cultural_continuity", summary)
        self.assertIn("mean_language_change_rate", summary)
        self.assertIn("mean_phonological_complexity", summary)
        self.assertIn("mean_sound_shift_index", summary)
        self.assertIn("mean_inherited_phonology_fraction", summary)
        self.assertGreaterEqual(summary["mean_phonological_complexity"], 0.0)
        self.assertLessEqual(summary["mean_phonological_complexity"], 1.0)
        self.assertGreaterEqual(summary["mean_sound_shift_index"], 0.0)
        self.assertLessEqual(summary["mean_sound_shift_index"], 1.0)
        self.assertGreaterEqual(summary["mean_inherited_phonology_fraction"], 0.0)
        self.assertLessEqual(summary["mean_inherited_phonology_fraction"], 1.0)
        self.assertEqual(summary["phonological_history_count"], len(world["phonological_histories"]))
        self.assertEqual(summary["phonological_history_count"], len(world["language_regions"]))
        self.assertEqual(
            summary["phonological_history_step_count"],
            sum(history["step_count"] for history in world["phonological_histories"]),
        )
        self.assertEqual(summary["phonological_rule_count"], len(world["phonological_rules"]))
        self.assertGreater(summary["phonological_rule_count"], 0)
        self.assertEqual(summary["lexical_correspondence_count"], len(world["lexical_correspondences"]))
        self.assertGreater(summary["lexical_correspondence_count"], 0)
        self.assertEqual(summary["lexical_diffusion_history_count"], len(world["lexical_diffusion_histories"]))
        self.assertEqual(summary["lexical_diffusion_history_count"], len(world["language_regions"]))
        self.assertEqual(
            summary["lexical_diffusion_step_count"],
            sum(history["step_count"] for history in world["lexical_diffusion_histories"]),
        )
        self.assertEqual(summary["speaker_population_history_count"], len(world["speaker_population_histories"]))
        self.assertEqual(summary["speaker_population_history_count"], len(world["language_regions"]))
        self.assertEqual(
            summary["speaker_population_step_count"],
            sum(history["step_count"] for history in world["speaker_population_histories"]),
        )
        self.assertEqual(
            summary["lexical_correspondence_language_count"],
            sum(1 for language in world["language_regions"] if language["lexical_correspondence_count"] > 0),
        )
        self.assertEqual(
            summary["lexical_diffusion_language_count"],
            sum(1 for language in world["language_regions"] if language["lexical_diffusion_history_id"] >= 0),
        )
        self.assertEqual(
            summary["phonological_rule_language_count"],
            sum(1 for language in world["language_regions"] if language["sound_change_rule_count"] > 0),
        )
        self.assertEqual(
            summary["max_phonological_shift_stage"],
            max((rule["stage_index"] for rule in world["phonological_rules"]), default=0),
        )
        self.assertGreaterEqual(summary["mean_phonological_rule_probability_index"], 0.0)
        self.assertLessEqual(summary["mean_phonological_rule_probability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_phonological_rule_regularity_index"], 0.0)
        self.assertLessEqual(summary["mean_phonological_rule_regularity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_lexical_replacement_index"], 0.0)
        self.assertLessEqual(summary["mean_lexical_replacement_index"], 1.0)
        self.assertGreaterEqual(summary["mean_phonological_contact_influence_index"], 0.0)
        self.assertLessEqual(summary["mean_phonological_contact_influence_index"], 1.0)
        self.assertGreaterEqual(summary["mean_phonological_drift_index"], 0.0)
        self.assertLessEqual(summary["mean_phonological_drift_index"], 1.0)
        self.assertGreaterEqual(summary["mean_language_prosodic_complexity_index"], 0.0)
        self.assertLessEqual(summary["mean_language_prosodic_complexity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_phonotactic_complexity_index"], 0.0)
        self.assertLessEqual(summary["mean_phonotactic_complexity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_regular_correspondence_fraction"], 0.0)
        self.assertLessEqual(summary["mean_regular_correspondence_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_lexical_correspondence_replacement_index"], 0.0)
        self.assertLessEqual(summary["mean_lexical_correspondence_replacement_index"], 1.0)
        self.assertGreaterEqual(summary["mean_lexical_prosodic_weight_index"], 0.0)
        self.assertLessEqual(summary["mean_lexical_prosodic_weight_index"], 1.0)
        self.assertGreaterEqual(summary["mean_lexical_diffusion_adoption_index"], 0.0)
        self.assertLessEqual(summary["mean_lexical_diffusion_adoption_index"], 1.0)
        self.assertGreaterEqual(summary["mean_lexical_innovation_index"], 0.0)
        self.assertLessEqual(summary["mean_lexical_innovation_index"], 1.0)
        self.assertGreaterEqual(summary["mean_semantic_shift_index"], 0.0)
        self.assertLessEqual(summary["mean_semantic_shift_index"], 1.0)
        self.assertGreater(summary["total_estimated_speaker_population"], 0.0)
        self.assertGreaterEqual(summary["mean_speaker_allophonic_variation_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_allophonic_variation_index"], 1.0)
        self.assertGreaterEqual(summary["mean_speaker_syllable_pressure_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_syllable_pressure_index"], 1.0)
        self.assertGreaterEqual(summary["mean_speaker_contact_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_contact_index"], 1.0)
        self.assertGreaterEqual(summary["mean_speaker_population_adoption_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_population_adoption_index"], 1.0)
        self.assertGreaterEqual(summary["mean_speaker_phonetic_reduction_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_phonetic_reduction_index"], 1.0)
        self.assertGreaterEqual(summary["mean_speaker_lexical_diffusion_pressure_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_lexical_diffusion_pressure_index"], 1.0)
        self.assertAlmostEqual(
            summary["mean_phonological_rule_probability_index"],
            sum(rule["probability_index"] for rule in world["phonological_rules"]) / len(world["phonological_rules"]),
            delta=0.0001,
        )
        self.assertAlmostEqual(
            summary["mean_regular_correspondence_fraction"],
            sum(record["regular_correspondence_fraction"] for record in world["lexical_correspondences"])
            / len(world["lexical_correspondences"]),
            delta=0.0001,
        )
        self.assertAlmostEqual(
            summary["mean_lexical_diffusion_adoption_index"],
            sum(history["mean_diffusion_adoption_index"] for history in world["lexical_diffusion_histories"])
            / len(world["lexical_diffusion_histories"]),
            delta=0.0001,
        )
        self.assertAlmostEqual(
            summary["mean_speaker_allophonic_variation_index"],
            sum(history["mean_allophonic_variation_index"] for history in world["speaker_population_histories"])
            / len(world["speaker_population_histories"]),
            delta=0.0001,
        )
        self.assertAlmostEqual(
            summary["total_estimated_speaker_population"],
            sum(history["estimated_speaker_population"] for history in world["speaker_population_histories"]),
            delta=0.001,
        )
        self.assertEqual(
            summary["high_contact_speaker_history_count"],
            sum(1 for history in world["speaker_population_histories"] if history["high_contact_speaker_history"]),
        )
        self.assertEqual(summary["population_region_count"], len(world["population_regions"]))
        self.assertIn("estimated_world_population", summary)
        self.assertGreater(summary["estimated_world_population"], 0.0)
        self.assertIn("mean_population_pressure", summary)
        self.assertEqual(summary["population_history_count"], len(world["population_histories"]))
        self.assertEqual(len(world["population_histories"]), len(world["population_regions"]))
        self.assertEqual(
            summary["population_history_step_count"],
            sum(history["time_step_count"] for history in world["population_histories"]),
        )
        self.assertAlmostEqual(
            summary["historical_final_population"],
            sum(history["final_population"] for history in world["population_histories"]),
            delta=max(1.0, summary["historical_final_population"] * 0.0001),
        )
        self.assertGreaterEqual(summary["historical_peak_population_pressure"], 0.0)
        self.assertGreaterEqual(summary["max_population_decline_fraction"], 0.0)
        self.assertEqual(summary["economy_history_count"], len(world["economy_histories"]))
        self.assertEqual(len(world["economy_histories"]), len(world["population_histories"]))
        self.assertEqual(
            summary["economy_history_step_count"],
            sum(history["time_step_count"] for history in world["economy_histories"]),
        )
        self.assertAlmostEqual(
            summary["historical_final_gross_output_index"],
            sum(history["final_gross_output_index"] for history in world["economy_histories"]),
            delta=max(0.001, summary["historical_final_gross_output_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["historical_final_treasury_index"],
            sum(history["final_treasury_index"] for history in world["economy_histories"]),
            delta=max(0.001, summary["historical_final_treasury_index"] * 0.0001),
        )
        self.assertGreaterEqual(summary["historical_total_tax_revenue_index"], 0.0)
        self.assertGreaterEqual(summary["historical_total_trade_revenue_index"], 0.0)
        self.assertGreaterEqual(summary["historical_total_war_cost_index"], 0.0)
        self.assertGreaterEqual(summary["historical_peak_army_capacity_population"], 0.0)
        self.assertGreaterEqual(summary["mean_historical_prosperity_index"], 0.0)
        self.assertLessEqual(summary["mean_historical_prosperity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_historical_trade_dependency_index"], 0.0)
        self.assertLessEqual(summary["mean_historical_trade_dependency_index"], 1.0)
        self.assertGreaterEqual(summary["mean_historical_military_burden_index"], 0.0)
        self.assertLessEqual(summary["mean_historical_military_burden_index"], 1.0)
        self.assertEqual(
            summary["high_military_burden_economy_step_count"],
            sum(
                1
                for history in world["economy_histories"]
                for step in history["steps"]
                if step["military_burden_index"] >= 0.65
            ),
        )
        self.assertEqual(summary["household_cohort_count"], len(world["household_cohorts"]))
        self.assertEqual(summary["household_cohort_count"], sum(region["household_cohort_count"] for region in world["population_regions"]))
        self.assertEqual(summary["firm_agent_count"], len(world["firm_agents"]))
        self.assertEqual(summary["firm_agent_count"], sum(region["firm_agent_count"] for region in world["political_regions"]))
        self.assertEqual(summary["demographic_agent_history_count"], len(world["demographic_agent_histories"]))
        self.assertEqual(summary["demographic_agent_history_count"], len(world["population_regions"]))
        self.assertEqual(
            summary["demographic_agent_step_count"],
            sum(history["step_count"] for history in world["demographic_agent_histories"]),
        )
        self.assertEqual(summary["individual_agent_count"], len(world["individual_agents"]))
        self.assertEqual(
            summary["individual_agent_count"],
            sum(region["individual_agent_count"] for region in world["population_regions"]),
        )
        self.assertEqual(summary["individual_life_event_count"], len(world["individual_life_events"]))
        self.assertEqual(
            summary["individual_life_event_count"],
            sum(person["event_count"] for person in world["individual_agents"]),
        )
        self.assertEqual(
            summary["individual_birth_event_count"],
            sum(1 for event in world["individual_life_events"] if event["event_type"] == "birth"),
        )
        self.assertEqual(
            summary["individual_death_event_count"],
            sum(1 for event in world["individual_life_events"] if event["event_type"] == "death"),
        )
        self.assertEqual(
            summary["individual_marriage_event_count"],
            sum(1 for event in world["individual_life_events"] if event["event_type"] == "marriage"),
        )
        self.assertEqual(
            summary["property_transfer_event_count"],
            sum(1 for event in world["individual_life_events"] if event["event_type"] == "property_transfer"),
        )
        self.assertAlmostEqual(
            summary["total_household_cohort_population"],
            sum(cohort["population"] for cohort in world["household_cohorts"]),
            delta=max(1.0, summary["total_household_cohort_population"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_firm_employment_capacity"],
            sum(firm["employment_capacity"] for firm in world["firm_agents"]),
            delta=max(1.0, summary["total_firm_employment_capacity"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_property_transfer_value_index"],
            sum(event["property_value_index"] for event in world["individual_life_events"] if event["event_type"] == "property_transfer"),
            delta=max(0.001, summary["total_property_transfer_value_index"] * 0.0001),
        )
        self.assertGreaterEqual(summary["mean_household_resilience_index"], 0.0)
        self.assertLessEqual(summary["mean_household_resilience_index"], 1.0)
        self.assertGreaterEqual(summary["mean_household_migration_propensity_index"], 0.0)
        self.assertLessEqual(summary["mean_household_migration_propensity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_household_consumption_pressure_index"], 0.0)
        self.assertLessEqual(summary["mean_household_consumption_pressure_index"], 1.0)
        self.assertGreaterEqual(summary["mean_firm_productivity_index"], 0.0)
        self.assertLessEqual(summary["mean_firm_productivity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_firm_market_dependency_index"], 0.0)
        self.assertLessEqual(summary["mean_firm_market_dependency_index"], 1.0)
        self.assertGreaterEqual(summary["mean_firm_supply_chain_risk_index"], 0.0)
        self.assertLessEqual(summary["mean_firm_supply_chain_risk_index"], 1.0)
        self.assertGreaterEqual(summary["mean_demographic_vulnerability_index"], 0.0)
        self.assertLessEqual(summary["mean_demographic_vulnerability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_individual_lifespan_years"], 0.0)
        self.assertEqual(
            summary["high_vulnerability_household_count"],
            sum(1 for cohort in world["household_cohorts"] if cohort["vulnerability_index"] >= 0.65),
        )
        self.assertEqual(summary["conflict_count"], len(world["conflicts"]))
        self.assertIn("high_intensity_conflict_count", summary)
        self.assertEqual(
            summary["high_intensity_conflict_count"],
            sum(1 for conflict in world["conflicts"] if conflict["intensity"] >= 0.65),
        )
        self.assertIn("mean_conflict_intensity", summary)
        self.assertIn("mean_war_duration_years", summary)
        self.assertGreaterEqual(summary["mean_war_duration_years"], 0.0)
        self.assertIn("total_mobilized_population", summary)
        self.assertGreaterEqual(summary["total_mobilized_population"], 0.0)
        self.assertIn("mean_conflict_logistics_strain_index", summary)
        self.assertGreaterEqual(summary["mean_conflict_logistics_strain_index"], 0.0)
        self.assertLessEqual(summary["mean_conflict_logistics_strain_index"], 1.0)
        self.assertIn("mean_conflict_economic_disruption_index", summary)
        self.assertGreaterEqual(summary["mean_conflict_economic_disruption_index"], 0.0)
        self.assertLessEqual(summary["mean_conflict_economic_disruption_index"], 1.0)
        self.assertIn("high_economic_disruption_conflict_count", summary)
        self.assertEqual(
            summary["high_economic_disruption_conflict_count"],
            sum(1 for conflict in world["conflicts"] if conflict["economic_disruption_index"] >= 0.65),
        )
        self.assertIn("mean_conflict_casualty_rate", summary)
        self.assertGreaterEqual(summary["mean_conflict_casualty_rate"], 0.0)
        self.assertLessEqual(summary["mean_conflict_casualty_rate"], 1.0)
        self.assertIn("max_conflict_casualty_rate", summary)
        self.assertGreaterEqual(summary["max_conflict_casualty_rate"], 0.0)
        self.assertLessEqual(summary["max_conflict_casualty_rate"], 1.0)
        self.assertEqual(summary["logistics_network_count"], len(world["logistics_networks"]))
        self.assertEqual(summary["logistics_network_count"], len(world["political_regions"]))
        self.assertEqual(
            summary["logistics_route_link_count"],
            sum(network["route_count"] for network in world["logistics_networks"]),
        )
        self.assertEqual(summary["market_exchange_count"], len(world["market_exchanges"]))
        self.assertEqual(summary["market_exchange_count"], len(world["trade_flows"]))
        self.assertEqual(
            summary["interregional_market_exchange_count"],
            sum(1 for market in world["market_exchanges"] if market["interregional"]),
        )
        self.assertEqual(summary["route_capacity_constraint_count"], len(world["route_capacity_constraints"]))
        self.assertEqual(
            summary["route_capacity_constraint_count"],
            len({market["route_id"] for market in world["market_exchanges"]}),
        )
        self.assertEqual(summary["market_clearing_record_count"], len(world["market_clearing_records"]))
        self.assertEqual(summary["market_clearing_record_count"], len(world["market_exchanges"]))
        self.assertEqual(summary["market_agent_order_count"], len(world["market_agent_orders"]))
        self.assertEqual(
            summary["market_agent_order_count"],
            sum(record["agent_order_count"] for record in world["market_clearing_records"]),
        )
        self.assertEqual(summary["market_price_iteration_count"], len(world["market_price_iterations"]))
        self.assertEqual(
            summary["market_price_iteration_count"],
            sum(record["price_iteration_count"] for record in world["market_clearing_records"]),
        )
        self.assertEqual(summary["market_inventory_history_count"], len(world["market_inventory_histories"]))
        self.assertEqual(summary["market_inventory_history_count"], len(world["market_clearing_records"]))
        self.assertEqual(
            summary["market_inventory_step_count"],
            sum(history["step_count"] for history in world["market_inventory_histories"]),
        )
        self.assertEqual(
            summary["constrained_market_exchange_count"],
            sum(1 for record in world["market_clearing_records"] if record["unmet_demand_index"] > 0.0),
        )
        self.assertEqual(
            summary["producer_market_order_count"],
            sum(1 for order in world["market_agent_orders"] if order["order_side"] == "supply"),
        )
        self.assertEqual(
            summary["consumer_market_order_count"],
            sum(1 for order in world["market_agent_orders"] if order["order_side"] == "demand"),
        )
        self.assertEqual(summary["campaign_movement_count"], len(world["campaign_movements"]))
        self.assertEqual(summary["campaign_path_segment_count"], len(world["campaign_path_segments"]))
        self.assertEqual(
            summary["campaign_path_segment_count"],
            sum(campaign["path_segment_count"] for campaign in world["campaign_movements"]),
        )
        self.assertEqual(summary["campaign_front_history_count"], len(world["campaign_front_histories"]))
        self.assertEqual(summary["campaign_front_history_count"], len(world["campaign_movements"]))
        self.assertEqual(
            summary["campaign_front_step_count"],
            sum(history["step_count"] for history in world["campaign_front_histories"]),
        )
        self.assertEqual(summary["tactical_engagement_count"], len(world["tactical_engagements"]))
        self.assertEqual(summary["tactical_engagement_count"], len(world["campaign_movements"]))
        self.assertEqual(
            summary["tactical_engagement_step_count"],
            sum(engagement["step_count"] for engagement in world["tactical_engagements"]),
        )
        self.assertEqual(summary["strategic_campaign_plan_count"], len(world["strategic_campaign_plans"]))
        self.assertEqual(summary["strategic_campaign_plan_count"], len(world["campaign_movements"]))
        self.assertEqual(
            summary["strategic_decision_point_count"],
            sum(plan["decision_point_count"] for plan in world["strategic_campaign_plans"]),
        )
        cells_by_id = {int(cell["id"]): cell for cell in world["cells"]}
        for campaign in world["campaign_movements"]:
            path_cell_ids = [int(cell_id) for cell_id in campaign["path_cell_ids"]]
            self.assertNotEqual(campaign["origin_cell_id"], campaign["target_cell_id"])
            self.assertGreaterEqual(len(path_cell_ids), 2)
            self.assertEqual(campaign["path_segment_count"], len(path_cell_ids) - 1)
            self.assertEqual(len(path_cell_ids), len(set(path_cell_ids)))
            for first_id, second_id in zip(path_cell_ids, path_cell_ids[1:]):
                self.assertIn(second_id, {int(neighbor_id) for neighbor_id in cells_by_id[first_id]["neighbors"]})
        self.assertAlmostEqual(
            summary["total_market_exchange_volume_index"],
            sum(market["volume_index"] for market in world["market_exchanges"]),
            delta=max(0.001, summary["total_market_exchange_volume_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_market_requested_volume_index"],
            sum(constraint["requested_volume_index"] for constraint in world["route_capacity_constraints"]),
            delta=max(0.001, summary["total_market_requested_volume_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_market_cleared_volume_index"],
            sum(constraint["cleared_volume_index"] for constraint in world["route_capacity_constraints"]),
            delta=max(0.001, summary["total_market_cleared_volume_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_market_unmet_demand_index"],
            sum(constraint["unmet_volume_index"] for constraint in world["route_capacity_constraints"]),
            delta=max(0.001, summary["total_market_unmet_demand_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_endogenous_market_supply_index"],
            sum(record["endogenous_supply_index"] for record in world["market_clearing_records"]),
            delta=max(0.001, summary["total_endogenous_market_supply_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_endogenous_market_demand_index"],
            sum(record["endogenous_demand_index"] for record in world["market_clearing_records"]),
            delta=max(0.001, summary["total_endogenous_market_demand_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_campaign_mobilized_population"],
            sum(campaign["force_estimate"] for campaign in world["campaign_movements"]),
            delta=max(1.0, summary["total_campaign_mobilized_population"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_campaign_path_length_km"],
            sum(campaign["path_length_km"] for campaign in world["campaign_movements"]),
            delta=max(0.001, summary["total_campaign_path_length_km"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_campaign_front_attrition_loss_population"],
            sum(
                step["attrition_loss_population"]
                for history in world["campaign_front_histories"]
                for step in history["steps"]
            ),
            delta=max(1.0, summary["total_campaign_front_attrition_loss_population"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["tactical_total_attrition_loss_population"],
            sum(engagement["total_attrition_loss_population"] for engagement in world["tactical_engagements"]),
            delta=max(1.0, summary["tactical_total_attrition_loss_population"] * 0.0001),
        )
        self.assertGreaterEqual(summary["mean_logistics_transport_efficiency_index"], 0.0)
        self.assertLessEqual(summary["mean_logistics_transport_efficiency_index"], 1.0)
        self.assertGreaterEqual(summary["mean_logistics_resilience_index"], 0.0)
        self.assertLessEqual(summary["mean_logistics_resilience_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_access_index"], 0.0)
        self.assertLessEqual(summary["mean_market_access_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_disruption_risk_index"], 0.0)
        self.assertLessEqual(summary["mean_market_disruption_risk_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_clearance_fraction"], 0.0)
        self.assertLessEqual(summary["mean_market_clearance_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_route_capacity_utilization_index"], 0.0)
        self.assertLessEqual(summary["mean_route_capacity_utilization_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_price_adjustment_index"], 0.0)
        self.assertLessEqual(summary["mean_market_price_adjustment_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_rationing_index"], 0.0)
        self.assertLessEqual(summary["mean_market_rationing_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_equilibrium_residual_index"], 0.0)
        self.assertLessEqual(summary["mean_market_equilibrium_residual_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_inventory_gap_index"], 0.0)
        self.assertLessEqual(summary["mean_market_inventory_gap_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_learning_rate_index"], 0.0)
        self.assertLessEqual(summary["mean_market_learning_rate_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_inventory_pressure_index"], 0.0)
        self.assertLessEqual(summary["mean_market_inventory_pressure_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_travel_time_days"], 0.0)
        self.assertGreaterEqual(summary["mean_campaign_attrition_risk_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_attrition_risk_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_operational_reach_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_operational_reach_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_path_length_km"], 0.0)
        self.assertGreaterEqual(summary["mean_campaign_path_terrain_cost_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_path_terrain_cost_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_path_supply_loss_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_path_supply_loss_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_path_attrition_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_path_attrition_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_front_supply_integrity_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_front_supply_integrity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_front_control_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_front_control_index"], 1.0)
        self.assertGreaterEqual(summary["mean_tactical_counter_maneuver_index"], 0.0)
        self.assertLessEqual(summary["mean_tactical_counter_maneuver_index"], 1.0)
        self.assertGreaterEqual(summary["mean_tactical_front_pressure_index"], 0.0)
        self.assertLessEqual(summary["mean_tactical_front_pressure_index"], 1.0)
        self.assertGreaterEqual(summary["mean_tactical_supply_contest_index"], 0.0)
        self.assertLessEqual(summary["mean_tactical_supply_contest_index"], 1.0)
        self.assertGreaterEqual(summary["mean_counter_campaign_viability_index"], 0.0)
        self.assertLessEqual(summary["mean_counter_campaign_viability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_strategic_plan_confidence_index"], 0.0)
        self.assertLessEqual(summary["mean_strategic_plan_confidence_index"], 1.0)
        self.assertGreaterEqual(summary["mean_strategic_force_reserve_fraction"], 0.0)
        self.assertLessEqual(summary["mean_strategic_force_reserve_fraction"], 1.0)
        self.assertEqual(
            summary["high_attrition_campaign_count"],
            sum(1 for campaign in world["campaign_movements"] if campaign["attrition_risk_index"] >= 0.65),
        )
        self.assertEqual(
            summary["high_attrition_campaign_path_segment_count"],
            sum(1 for segment in world["campaign_path_segments"] if segment["attrition_index"] >= 0.65),
        )
        self.assertEqual(
            summary["high_pressure_tactical_step_count"],
            sum(
                1
                for engagement in world["tactical_engagements"]
                for step in engagement["steps"]
                if step["front_pressure_index"] >= 0.65
            ),
        )
        self.assertEqual(
            summary["independent_counter_campaign_plan_count"],
            sum(1 for plan in world["strategic_campaign_plans"] if plan["independent_counter_campaign_planned"]),
        )
        self.assertEqual(
            summary["high_escalation_strategic_plan_count"],
            sum(1 for plan in world["strategic_campaign_plans"] if plan["escalation_risk_index"] >= 0.65),
        )
        self.assertEqual(
            summary["high_inventory_stress_market_count"],
            sum(1 for history in world["market_inventory_histories"] if history["high_inventory_stress"]),
        )
        self.assertEqual(summary["dynasty_count"], len(world["dynasties"]))
        self.assertGreater(summary["dynasty_count"], 0)
        self.assertIn("dynastic_lineage_count", summary)
        self.assertEqual(
            summary["dynastic_lineage_count"],
            sum(1 for dynasty in world["dynasties"] if dynasty["parent_dynasty_id"] >= 0),
        )
        self.assertIn("dynasty_root_count", summary)
        self.assertEqual(
            summary["dynasty_root_count"],
            sum(1 for dynasty in world["dynasties"] if dynasty["parent_dynasty_id"] < 0),
        )
        self.assertIn("dynasty_successor_link_count", summary)
        self.assertEqual(
            summary["dynasty_successor_link_count"],
            sum(1 for dynasty in world["dynasties"] if dynasty["successor_dynasty_id"] >= 0),
        )
        self.assertIn("max_dynasty_lineage_depth", summary)
        self.assertEqual(
            summary["max_dynasty_lineage_depth"],
            max((dynasty["lineage_depth"] for dynasty in world["dynasties"]), default=0),
        )
        self.assertIn("mean_dynastic_continuity_index", summary)
        self.assertGreaterEqual(summary["mean_dynastic_continuity_index"], 0.0)
        self.assertLessEqual(summary["mean_dynastic_continuity_index"], 1.0)
        self.assertEqual(summary["ruler_count"], len(world["rulers"]))
        self.assertGreater(summary["ruler_count"], 0)
        self.assertEqual(
            summary["named_ruler_dynasty_count"],
            sum(1 for dynasty in world["dynasties"] if dynasty["ruler_count"] > 0),
        )
        self.assertEqual(summary["ruler_marriage_alliance_count"], len(world["marriage_alliances"]))
        self.assertEqual(summary["cadet_branch_count"], len(world["cadet_branches"]))
        self.assertEqual(
            summary["married_ruler_count"],
            sum(1 for ruler in world["rulers"] if ruler["spouse_ruler_id"] >= 0),
        )
        self.assertEqual(
            summary["max_ruler_lineage_depth"],
            max((ruler["ruler_lineage_depth"] for ruler in world["rulers"]), default=0),
        )
        self.assertGreaterEqual(summary["mean_ruler_legitimacy_index"], 0.0)
        self.assertLessEqual(summary["mean_ruler_legitimacy_index"], 1.0)
        self.assertGreaterEqual(summary["mean_succession_crisis_risk"], 0.0)
        self.assertLessEqual(summary["mean_succession_crisis_risk"], 1.0)
        self.assertGreaterEqual(summary["mean_marriage_alliance_strength"], 0.0)
        self.assertLessEqual(summary["mean_marriage_alliance_strength"], 1.0)
        self.assertGreaterEqual(summary["mean_cadet_branch_claim_strength"], 0.0)
        self.assertLessEqual(summary["mean_cadet_branch_claim_strength"], 1.0)
        self.assertAlmostEqual(
            summary["mean_ruler_legitimacy_index"],
            sum(ruler["legitimacy_index"] for ruler in world["rulers"]) / len(world["rulers"]),
            delta=0.0001,
        )
        self.assertAlmostEqual(
            summary["mean_succession_crisis_risk"],
            sum(ruler["succession_crisis_risk"] for ruler in world["rulers"]) / len(world["rulers"]),
            delta=0.0001,
        )
        if world["marriage_alliances"]:
            self.assertAlmostEqual(
                summary["mean_marriage_alliance_strength"],
                sum(alliance["alliance_strength"] for alliance in world["marriage_alliances"]) / len(world["marriage_alliances"]),
                delta=0.0001,
            )
        if world["cadet_branches"]:
            self.assertAlmostEqual(
                summary["mean_cadet_branch_claim_strength"],
                sum(branch["claim_strength"] for branch in world["cadet_branches"]) / len(world["cadet_branches"]),
                delta=0.0001,
            )
        self.assertEqual(summary["territorial_snapshot_count"], len(world["territorial_snapshots"]))
        self.assertGreater(summary["territorial_snapshot_count"], 0)
        self.assertEqual(
            summary["snapshot_region_record_count"],
            sum(len(snapshot["regions"]) for snapshot in world["territorial_snapshots"]),
        )
        self.assertEqual(
            summary["snapshot_polygon_region_count"],
            sum(
                1
                for snapshot in world["territorial_snapshots"]
                for region in snapshot["regions"]
                if region["dissolved_polygon_area_km2"] > 0.0
            ),
        )
        self.assertIn("mean_snapshot_fragmentation_index", summary)
        self.assertIn("mean_snapshot_polygon_area_error_fraction", summary)
        self.assertIn("mean_snapshot_compactness_index", summary)
        self.assertIn("mean_snapshot_geometry_quality", summary)
        self.assertGreaterEqual(summary["mean_snapshot_geometry_quality"], 0.0)
        self.assertLessEqual(summary["mean_snapshot_geometry_quality"], 1.0)
        self.assertIn("mean_snapshot_boundary_perimeter_km", summary)
        self.assertEqual(
            summary["territorial_cell_edge_boundary_segment_count"],
            len(world["territorial_boundary_segments"]),
        )
        self.assertAlmostEqual(
            summary["territorial_cell_edge_boundary_length_km"],
            sum(segment["length_km"] for segment in world["territorial_boundary_segments"]),
            delta=max(0.001, summary["territorial_cell_edge_boundary_length_km"] * 0.0001),
        )
        self.assertEqual(
            summary["snapshot_region_with_cell_edge_boundary_count"],
            sum(
                1
                for snapshot in world["territorial_snapshots"]
                for region in snapshot["regions"]
                if region["cell_edge_boundary_segment_count"] > 0
            ),
        )
        self.assertGreaterEqual(summary["mean_snapshot_cell_edge_boundary_segment_count"], 0.0)
        self.assertGreaterEqual(summary["mean_snapshot_cell_edge_boundary_length_km"], 0.0)
        self.assertGreaterEqual(summary["mean_snapshot_cell_edge_boundary_quality"], 0.0)
        self.assertLessEqual(summary["mean_snapshot_cell_edge_boundary_quality"], 1.0)
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
        self.assertEqual(summary["border_segment_count"], len(world["borders"]))
        self.assertIn("border_total_length_km", summary)
        self.assertIn("natural_border_fraction", summary)
        self.assertIn("largest_region_area_km2", summary)
        self.assertIn("largest_culture_area_km2", summary)
        self.assertIn("politically_assigned_land_fraction", summary)
        self.assertIn("culturally_assigned_land_fraction", summary)
        self.assertIn("linguistically_assigned_land_fraction", summary)
        self.assertIn("soil_diagnostic_cell_count", summary)
        self.assertIn("soil_texture_counts", summary)
        self.assertEqual(sum(summary["soil_texture_counts"].values()), summary["cell_count"])
        soil_cells = [cell for cell in world["cells"] if cell["soil_texture_class"] != "none"]
        self.assertEqual(summary["soil_diagnostic_cell_count"], len(soil_cells))
        self.assertEqual(summary["soil_profile_count"], len(world["soil_profiles"]))
        self.assertEqual(summary["soil_profile_count"], len(soil_cells))
        self.assertEqual(summary["soil_horizon_count"], len(world["soil_horizons"]))
        self.assertEqual(summary["soil_horizon_count"], sum(profile["horizon_count"] for profile in world["soil_profiles"]))
        self.assertEqual(summary["soil_profile_history_count"], len(world["soil_profile_histories"]))
        self.assertEqual(summary["soil_profile_history_count"], len(world["soil_profiles"]))
        self.assertEqual(
            summary["soil_pedogenesis_step_count"],
            sum(history["step_count"] for history in world["soil_profile_histories"]),
        )
        self.assertEqual(sum(summary["soil_profile_class_counts"].values()), summary["soil_profile_count"])
        self.assertIn("mean_soil_drainage_index", summary)
        self.assertIn("mean_soil_moisture_index", summary)
        self.assertIn("mean_soil_ph", summary)
        self.assertIn("mean_soil_organic_matter_fraction", summary)
        self.assertIn("mean_soil_salinity_index", summary)
        self.assertIn("mean_soil_erodibility_index", summary)
        self.assertIn("mean_soil_profile_development_index", summary)
        self.assertIn("saline_soil_cell_fraction", summary)
        self.assertIn("high_erodibility_soil_fraction", summary)
        self.assertIn("waterlogged_soil_cell_fraction", summary)
        self.assertIn("mean_soil_profile_depth_m", summary)
        self.assertIn("mean_soil_horizon_count", summary)
        self.assertIn("mean_topsoil_organic_matter_fraction", summary)
        self.assertIn("mean_soil_weathering_index", summary)
        self.assertIn("mean_soil_leaching_index", summary)
        self.assertIn("mean_soil_bioturbation_index", summary)
        self.assertIn("mature_soil_profile_fraction", summary)
        self.assertIn("shallow_soil_profile_fraction", summary)
        self.assertIn("total_soil_production_m", summary)
        self.assertIn("total_soil_erosion_loss_m", summary)
        self.assertIn("mean_pedogenic_weathering_index", summary)
        self.assertIn("mean_pedogenic_leaching_index", summary)
        self.assertIn("mean_pedogenic_bioturbation_index", summary)
        self.assertIn("mean_horizon_differentiation_index", summary)
        self.assertIn("mean_pedogenic_flux_index", summary)
        self.assertIn("high_erosion_pedogenesis_count", summary)
        self.assertGreaterEqual(summary["mean_soil_drainage_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_drainage_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_moisture_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_moisture_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_ph"], 3.5)
        self.assertLessEqual(summary["mean_soil_ph"], 9.5)
        self.assertGreaterEqual(summary["mean_soil_organic_matter_fraction"], 0.0)
        self.assertLessEqual(summary["mean_soil_organic_matter_fraction"], 0.5)
        self.assertGreaterEqual(summary["mean_soil_salinity_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_salinity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_erodibility_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_erodibility_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_profile_development_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_profile_development_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_profile_depth_m"], 0.0)
        self.assertGreaterEqual(summary["mean_soil_horizon_count"], 0.0)
        self.assertGreaterEqual(summary["mean_topsoil_organic_matter_fraction"], 0.0)
        self.assertLessEqual(summary["mean_topsoil_organic_matter_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_weathering_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_weathering_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_leaching_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_leaching_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_bioturbation_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_bioturbation_index"], 1.0)
        self.assertGreaterEqual(summary["mature_soil_profile_fraction"], 0.0)
        self.assertLessEqual(summary["mature_soil_profile_fraction"], 1.0)
        self.assertGreaterEqual(summary["shallow_soil_profile_fraction"], 0.0)
        self.assertLessEqual(summary["shallow_soil_profile_fraction"], 1.0)
        self.assertGreaterEqual(summary["total_soil_production_m"], 0.0)
        self.assertGreaterEqual(summary["total_soil_erosion_loss_m"], 0.0)
        self.assertGreaterEqual(summary["mean_pedogenic_weathering_index"], 0.0)
        self.assertLessEqual(summary["mean_pedogenic_weathering_index"], 1.0)
        self.assertGreaterEqual(summary["mean_pedogenic_leaching_index"], 0.0)
        self.assertLessEqual(summary["mean_pedogenic_leaching_index"], 1.0)
        self.assertGreaterEqual(summary["mean_pedogenic_bioturbation_index"], 0.0)
        self.assertLessEqual(summary["mean_pedogenic_bioturbation_index"], 1.0)
        self.assertGreaterEqual(summary["mean_horizon_differentiation_index"], 0.0)
        self.assertLessEqual(summary["mean_horizon_differentiation_index"], 1.0)
        self.assertGreaterEqual(summary["mean_pedogenic_flux_index"], 0.0)
        self.assertLessEqual(summary["mean_pedogenic_flux_index"], 1.0)
        if soil_cells:
            self.assertAlmostEqual(
                summary["mean_soil_drainage_index"],
                sum(cell["soil_drainage_index"] for cell in soil_cells) / len(soil_cells),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["mean_soil_ph"],
                sum(cell["soil_ph"] for cell in soil_cells) / len(soil_cells),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["mean_soil_profile_depth_m"],
                sum(profile["total_depth_m"] for profile in world["soil_profiles"]) / len(world["soil_profiles"]),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["total_soil_production_m"],
                sum(history["total_soil_production_m"] for history in world["soil_profile_histories"]),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["mean_pedogenic_flux_index"],
                sum(history["mean_pedogenic_flux_index"] for history in world["soil_profile_histories"])
                / len(world["soil_profile_histories"]),
                delta=0.001,
            )
            self.assertEqual(
                summary["high_erosion_pedogenesis_count"],
                sum(1 for history in world["soil_profile_histories"] if history["high_erosion_pressure"]),
            )
        self.assertGreater(summary["settlement_count"], 0)

        first_cell = world["cells"][0]
        self.assertEqual(len(first_cell["temperature_monthly_c"]), 12)
        self.assertEqual(len(first_cell["precipitation_monthly_mm"]), 12)
        self.assertIn("political_region_id", first_cell)
        self.assertIn("culture_region_id", first_cell)
        self.assertIn("language_region_id", first_cell)
        self.assertIn("water_body_type", first_cell)
        self.assertIn("landmass_id", first_cell)
        self.assertIn("island_class", first_cell)
        self.assertIn("marine_region_id", first_cell)
        self.assertIn("marine_chokepoint_id", first_cell)
        self.assertIn("river_navigability_index", first_cell)
        self.assertIn("coastal_navigability_index", first_cell)
        self.assertIn("harbor_suitability_index", first_cell)
        self.assertIn("transport_chokepoint_index", first_cell)
        self.assertIn("navigability_index", first_cell)
        self.assertIn("navigability_class", first_cell)
        self.assertIn("navigable_waterway_id", first_cell)
        for key in (
            "river_channel_width_m",
            "river_channel_depth_m",
            "bankfull_discharge_m3_s",
            "channel_slope_index",
            "stream_power_index",
            "floodplain_connectivity_index",
            "channel_morphology_class",
            "river_channel_system_id",
        ):
            self.assertIn(key, first_cell)
        self.assertIn("basin_id", first_cell)
        self.assertIn("spill_to", first_cell)
        self.assertIn("depression_component_id", first_cell)
        self.assertIn("depression_sink_cell_id", first_cell)
        self.assertIn("lake_basin_id", first_cell)
        self.assertIn("depression_policy", first_cell)
        self.assertIn("filled_elevation_m", first_cell)
        self.assertIn("hydrologic_surface_elevation_m", first_cell)
        self.assertIn("hydrologic_flow_drop_m", first_cell)
        self.assertIn("hydrologic_flow_slope", first_cell)
        self.assertIn("hydrologic_surface_conditioned", first_cell)
        self.assertIn("depression_depth_m", first_cell)
        self.assertIn("spill_elevation_m", first_cell)
        self.assertIn("lake_fill_fraction", first_cell)
        self.assertIn("is_closed_basin", first_cell)
        self.assertIn("lake_overflows", first_cell)
        self.assertIn("overflow_channel_active", first_cell)
        self.assertIn("overflow_channel_incision_m", first_cell)
        self.assertIn("overflow_channel_sediment_evacuated_km3", first_cell)
        self.assertIn("overflow_channel_avulsion_risk", first_cell)
        self.assertGreaterEqual(first_cell["overflow_channel_incision_m"], 0.0)
        self.assertGreaterEqual(first_cell["overflow_channel_sediment_evacuated_km3"], 0.0)
        self.assertGreaterEqual(first_cell["overflow_channel_avulsion_risk"], 0.0)
        self.assertLessEqual(first_cell["overflow_channel_avulsion_risk"], 1.0)
        land_cells = [cell for cell in world["cells"] if not cell["is_water"]]
        marine_cells = [
            cell
            for cell in world["cells"]
            if cell["water_body_type"] in {"ocean", "continental_shelf", "inland_sea"}
        ]
        landmass_ids = {landmass["id"] for landmass in world["landmasses"]}
        marine_region_ids = {region["id"] for region in world["marine_regions"]}
        self.assertTrue(world["landmasses"])
        self.assertTrue(world["marine_regions"])
        self.assertEqual(
            {cell_id for landmass in world["landmasses"] for cell_id in landmass["cell_ids"]},
            {cell["id"] for cell in land_cells},
        )
        self.assertTrue(all(cell["landmass_id"] in landmass_ids for cell in land_cells))
        self.assertTrue(all(cell["island_class"] in {"continent", "large_island", "island", "islet"} for cell in land_cells))
        self.assertTrue(all(cell["landmass_id"] == -1 and cell["island_class"] == "water" for cell in world["cells"] if cell["is_water"]))
        self.assertTrue(all(cell["marine_region_id"] in marine_region_ids for cell in marine_cells))
        self.assertEqual(
            {cell_id for region in world["marine_regions"] for cell_id in region["cell_ids"]},
            {cell["id"] for cell in marine_cells},
        )
        self.assertTrue(
            all(
                cell["marine_region_id"] == -1
                for cell in world["cells"]
                if cell["water_body_type"] not in {"ocean", "continental_shelf", "inland_sea"}
            )
        )
        for key in (
            "river_navigability_index",
            "coastal_navigability_index",
            "harbor_suitability_index",
            "transport_chokepoint_index",
            "navigability_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertEqual(
            first_cell["navigability_index"],
            max(
                first_cell["river_navigability_index"],
                first_cell["coastal_navigability_index"],
                first_cell["harbor_suitability_index"],
                first_cell["transport_chokepoint_index"],
            ),
        )
        self.assertIn(
            first_cell["navigability_class"],
            {
                "non_navigable",
                "river_corridor",
                "coastal_corridor",
                "river_mouth",
                "harbor",
                "transport_chokepoint",
            },
        )
        self.assertGreaterEqual(first_cell["navigable_waterway_id"], -1)
        for key in (
            "river_channel_width_m",
            "river_channel_depth_m",
            "bankfull_discharge_m3_s",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
        for key in (
            "channel_slope_index",
            "stream_power_index",
            "floodplain_connectivity_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertIn(
            first_cell["channel_morphology_class"],
            {
                "non_channel",
                "small_headwater",
                "incised_bedrock_channel",
                "braided_sediment_rich_channel",
                "deep_alluvial_channel",
                "navigable_lowland_channel",
                "ephemeral_wadi",
                "glacial_outwash_channel",
            },
        )
        self.assertGreaterEqual(first_cell["river_channel_system_id"], -1)
        for key in (
            "hydraulic_radius_m",
            "flow_velocity_m_s",
            "froude_number",
            "bed_shear_stress_pa",
            "manning_roughness_n",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
        for key in (
            "channel_capacity_index",
            "hydraulic_navigability_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertIn(
            first_cell["hydraulic_flow_regime"],
            {
                "non_channel",
                "subcritical",
                "swift_subcritical",
                "transitional",
                "supercritical",
            },
        )
        self.assertGreaterEqual(first_cell["river_hydraulic_reach_id"], -1)
        river_channel_cells = [cell for cell in world["cells"] if cell["is_river"] and not cell["is_water"]]
        self.assertEqual(summary["river_channel_cell_count"], len(river_channel_cells))
        self.assertEqual(summary["river_channel_system_count"], len(world["river_channel_systems"]))
        self.assertEqual(sum(summary["channel_morphology_class_counts"].values()), summary["cell_count"])
        self.assertEqual(
            summary["navigable_channel_depth_cell_count"],
            sum(1 for cell in river_channel_cells if cell["river_channel_depth_m"] >= 1.8 and cell["river_channel_width_m"] >= 35.0),
        )
        self.assertEqual(
            summary["floodplain_connected_channel_cell_count"],
            sum(1 for cell in river_channel_cells if cell["floodplain_connectivity_index"] >= 0.45),
        )
        self.assertEqual(
            summary["high_stream_power_channel_cell_count"],
            sum(1 for cell in river_channel_cells if cell["stream_power_index"] >= 0.62),
        )
        self.assertAlmostEqual(
            summary["total_river_channel_length_km"],
            sum(system["length_km"] for system in world["river_channel_systems"]),
            delta=max(0.001, summary["total_river_channel_length_km"] * 0.0001),
        )
        river_hydraulic_cells = river_channel_cells
        self.assertEqual(summary["river_hydraulic_cell_count"], len(river_hydraulic_cells))
        self.assertEqual(summary["river_hydraulic_reach_count"], len(world["river_hydraulic_reaches"]))
        self.assertEqual(sum(summary["hydraulic_flow_regime_counts"].values()), summary["cell_count"])
        self.assertEqual(
            summary["hydraulically_navigable_cell_count"],
            sum(1 for cell in river_hydraulic_cells if cell["hydraulic_navigability_index"] >= 0.55),
        )
        self.assertEqual(
            summary["supercritical_flow_cell_count"],
            sum(1 for cell in river_hydraulic_cells if cell["hydraulic_flow_regime"] == "supercritical"),
        )
        self.assertEqual(
            summary["high_shear_stress_cell_count"],
            sum(1 for cell in river_hydraulic_cells if cell["bed_shear_stress_pa"] >= 120.0),
        )
        if river_channel_cells:
            for summary_key, cell_key in (
                ("mean_river_channel_width_m", "river_channel_width_m"),
                ("mean_river_channel_depth_m", "river_channel_depth_m"),
                ("mean_bankfull_discharge_m3_s", "bankfull_discharge_m3_s"),
                ("mean_stream_power_index", "stream_power_index"),
                ("mean_channel_slope_index", "channel_slope_index"),
            ):
                self.assertAlmostEqual(
                    summary[summary_key],
                    sum(cell[cell_key] for cell in river_channel_cells) / len(river_channel_cells),
                    delta=0.001,
                )
            for summary_key, cell_key in (
                ("mean_hydraulic_radius_m", "hydraulic_radius_m"),
                ("mean_flow_velocity_m_s", "flow_velocity_m_s"),
                ("mean_froude_number", "froude_number"),
                ("mean_bed_shear_stress_pa", "bed_shear_stress_pa"),
                ("mean_manning_roughness_n", "manning_roughness_n"),
                ("mean_channel_capacity_index", "channel_capacity_index"),
                ("mean_hydraulic_navigability_index", "hydraulic_navigability_index"),
            ):
                self.assertAlmostEqual(
                    summary[summary_key],
                    sum(cell[cell_key] for cell in river_hydraulic_cells) / len(river_hydraulic_cells),
                    delta=0.001,
                )
        if world["river_hydraulic_reaches"]:
            first_reach = world["river_hydraulic_reaches"][0]
            self.assertEqual(first_reach["id"], 0)
            self.assertEqual(first_reach["river_channel_system_id"], first_reach["id"])
            self.assertEqual(first_reach["cell_count"], len(first_reach["cell_ids"]))
            self.assertIn(first_reach["source_cell_id"], first_reach["cell_ids"])
            self.assertIn(first_reach["outlet_cell_id"], first_reach["cell_ids"])
            self.assertGreaterEqual(first_reach["length_km"], 0.0)
            self.assertGreaterEqual(first_reach["area_km2"], 0.0)
            self.assertIn(
                first_reach["dominant_hydraulic_flow_regime"],
                {
                    "non_channel",
                    "subcritical",
                    "swift_subcritical",
                    "transitional",
                    "supercritical",
                },
            )
            self.assertEqual(sum(first_reach["hydraulic_flow_regime_counts"].values()), first_reach["cell_count"])
            for key in (
                "mean_hydraulic_radius_m",
                "mean_flow_velocity_m_s",
                "mean_froude_number",
                "mean_bed_shear_stress_pa",
                "mean_manning_roughness_n",
            ):
                self.assertGreaterEqual(first_reach[key], 0.0)
            for key in (
                "mean_channel_capacity_index",
                "mean_hydraulic_navigability_index",
            ):
                self.assertGreaterEqual(first_reach[key], 0.0)
                self.assertLessEqual(first_reach[key], 1.0)
            for key in (
                "hydraulically_navigable_cell_count",
                "supercritical_flow_cell_count",
                "high_shear_stress_cell_count",
            ):
                self.assertGreaterEqual(first_reach[key], 0)
        navigable_candidate_ids = {cell["id"] for cell in world["cells"] if cell["navigability_index"] >= 0.52}
        self.assertEqual(summary["navigable_cell_count"], len(navigable_candidate_ids))
        self.assertEqual(summary["navigable_waterway_count"], len(world["navigable_waterways"]))
        self.assertEqual(sum(summary["navigability_class_counts"].values()), summary["cell_count"])
        self.assertEqual(
            summary["high_harbor_suitability_cell_count"],
            sum(1 for cell in world["cells"] if cell["harbor_suitability_index"] >= 0.62),
        )
        self.assertEqual(
            summary["transport_chokepoint_cell_count"],
            sum(1 for cell in world["cells"] if cell["transport_chokepoint_index"] >= 0.55),
        )
        self.assertEqual(
            {cell_id for waterway in world["navigable_waterways"] for cell_id in waterway["cell_ids"]},
            navigable_candidate_ids,
        )
        self.assertAlmostEqual(
            summary["navigable_waterway_total_area_km2"],
            sum(waterway["area_km2"] for waterway in world["navigable_waterways"]),
            delta=max(0.001, summary["navigable_waterway_total_area_km2"] * 0.0001),
        )
        for summary_key, cell_key in (
            ("mean_navigability_index", "navigability_index"),
            ("mean_river_navigability_index", "river_navigability_index"),
            ("mean_coastal_navigability_index", "coastal_navigability_index"),
            ("mean_harbor_suitability_index", "harbor_suitability_index"),
            ("mean_transport_chokepoint_index", "transport_chokepoint_index"),
        ):
            self.assertAlmostEqual(
                summary[summary_key],
                sum(cell[cell_key] for cell in world["cells"]) / len(world["cells"]),
                delta=0.001,
            )
        port_settlement_cell_ids = {
            settlement["cell_id"] for settlement in world["settlements"] if settlement["type"] == "port"
        }
        port_candidate_ids = {
            cell["id"]
            for cell in world["cells"]
            if not cell["is_water"]
            and (
                (
                    cell["port_suitability_index"] >= 0.58
                    and cell["ice_thickness_m"] < 80.0
                    and cell["biome"] != "ice_cap"
                )
                or cell["id"] in port_settlement_cell_ids
            )
        }
        self.assertEqual(summary["port_site_count"], len(world["port_sites"]))
        self.assertEqual(summary["port_candidate_cell_count"], len(port_candidate_ids))
        self.assertEqual({site["cell_id"] for site in world["port_sites"]}, port_candidate_ids)
        self.assertEqual(
            summary["port_settlement_count"],
            sum(1 for settlement in world["settlements"] if settlement["type"] == "port"),
        )
        self.assertEqual(
            summary["port_settlement_with_site_count"],
            sum(1 for settlement in world["settlements"] if settlement["type"] == "port" and settlement["cell_id"] in port_candidate_ids),
        )
        self.assertAlmostEqual(
            summary["port_site_total_area_km2"],
            sum(site["area_km2"] for site in world["port_sites"]),
            delta=max(0.001, summary["port_site_total_area_km2"] * 0.0001),
        )
        for summary_key, cell_key in (
            ("mean_port_suitability_index", "port_suitability_index"),
            ("mean_protected_bay_index", "protected_bay_index"),
            ("mean_river_mouth_port_index", "river_mouth_port_index"),
            ("mean_strait_access_index", "strait_access_index"),
        ):
            self.assertAlmostEqual(
                summary[summary_key],
                sum(cell[cell_key] for cell in world["cells"]) / len(world["cells"]),
                delta=0.001,
            )
        self.assertEqual(sum(summary["port_site_type_counts"].values()), summary["port_site_count"])
        first_landmass = world["landmasses"][0]
        self.assertIn("cell_ids", first_landmass)
        self.assertIn("island_class", first_landmass)
        self.assertIn("shoreline_neighbor_edge_count", first_landmass)
        self.assertEqual(first_landmass["cell_count"], len(first_landmass["cell_ids"]))
        self.assertIn(first_landmass["island_class"], {"continent", "large_island", "island", "islet"})
        first_marine_region = world["marine_regions"][0]
        self.assertIn("cell_ids", first_marine_region)
        self.assertIn("region_class", first_marine_region)
        self.assertIn("adjacent_landmass_ids", first_marine_region)
        self.assertEqual(first_marine_region["cell_count"], len(first_marine_region["cell_ids"]))
        self.assertIn(first_marine_region["region_class"], {"open_ocean", "inland_sea", "continental_shelf"})
        shelf_cells = [cell for cell in world["cells"] if cell["water_body_type"] == "continental_shelf"]
        self.assertEqual(summary["continental_shelf_count"], len(world["continental_shelves"]))
        self.assertEqual(summary["continental_shelf_cell_count"], len(shelf_cells))
        self.assertEqual(
            summary["continental_shelf_marine_region_count"],
            sum(1 for region in world["marine_regions"] if region["region_class"] == "continental_shelf"),
        )
        self.assertAlmostEqual(
            summary["continental_shelf_total_area_km2"],
            sum(shelf["area_km2"] for shelf in world["continental_shelves"]),
            delta=max(0.001, summary["continental_shelf_total_area_km2"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["largest_continental_shelf_area_km2"],
            max((shelf["area_km2"] for shelf in world["continental_shelves"]), default=0.0),
            delta=max(0.001, summary["largest_continental_shelf_area_km2"] * 0.0001),
        )
        if world["continental_shelves"]:
            first_shelf = world["continental_shelves"][0]
            self.assertEqual(first_shelf["id"], 0)
            self.assertEqual(first_shelf["cell_count"], len(first_shelf["cell_ids"]))
            self.assertGreater(first_shelf["area_km2"], 0.0)
            self.assertIn("adjacent_landmass_ids", first_shelf)
            self.assertIn("marine_region_ids", first_shelf)
            self.assertIn("shoreline_neighbor_edge_count", first_shelf)
            self.assertIn("shelf_break_neighbor_edge_count", first_shelf)
            self.assertGreaterEqual(first_shelf["mean_water_depth_m"], 0.0)
            self.assertGreaterEqual(first_shelf["max_water_depth_m"], first_shelf["mean_water_depth_m"])
            for cell_id in first_shelf["cell_ids"]:
                self.assertEqual(world["cells"][cell_id]["continental_shelf_id"], first_shelf["id"])
        if world["marine_chokepoints"]:
            first_chokepoint = world["marine_chokepoints"][0]
            self.assertIn("cell_id", first_chokepoint)
            self.assertIn("adjacent_landmass_ids", first_chokepoint)
            self.assertIn("adjacent_marine_region_ids", first_chokepoint)
            self.assertIn(first_chokepoint["type"], {"strait", "marine_narrows"})
            self.assertGreaterEqual(first_chokepoint["constriction_index"], 0.0)
            self.assertLessEqual(first_chokepoint["constriction_index"], 1.0)
            self.assertGreaterEqual(first_chokepoint["width_proxy_km"], 0.0)
            self.assertEqual(
                world["cells"][first_chokepoint["cell_id"]]["marine_chokepoint_id"],
                first_chokepoint["id"],
            )
        if world["navigable_waterways"]:
            first_waterway = world["navigable_waterways"][0]
            self.assertEqual(first_waterway["id"], 0)
            self.assertIn(
                first_waterway["waterway_type"],
                {
                    "transport_chokepoint",
                    "river_mouth_corridor",
                    "harbor_cluster",
                    "river_corridor",
                    "coastal_corridor",
                },
            )
            self.assertGreater(first_waterway["cell_count"], 0)
            self.assertEqual(first_waterway["cell_count"], len(first_waterway["cell_ids"]))
            self.assertGreaterEqual(first_waterway["area_km2"], 0.0)
            self.assertGreaterEqual(first_waterway["mean_navigability_index"], 0.52)
            self.assertLessEqual(first_waterway["mean_navigability_index"], 1.0)
            self.assertGreaterEqual(first_waterway["mean_river_navigability_index"], 0.0)
            self.assertLessEqual(first_waterway["mean_river_navigability_index"], 1.0)
            self.assertGreaterEqual(first_waterway["mean_coastal_navigability_index"], 0.0)
            self.assertLessEqual(first_waterway["mean_coastal_navigability_index"], 1.0)
            self.assertGreaterEqual(first_waterway["max_harbor_suitability_index"], 0.0)
            self.assertLessEqual(first_waterway["max_harbor_suitability_index"], 1.0)
            self.assertIn("settlement_ids", first_waterway)
            self.assertIn("route_ids", first_waterway)
            self.assertIn("marine_region_ids", first_waterway)
            self.assertIn("watershed_ids", first_waterway)
        if world["river_channel_systems"]:
            first_channel_system = world["river_channel_systems"][0]
            self.assertEqual(first_channel_system["id"], 0)
            self.assertGreater(first_channel_system["cell_count"], 0)
            self.assertEqual(first_channel_system["cell_count"], len(first_channel_system["cell_ids"]))
            self.assertIn(first_channel_system["source_cell_id"], first_channel_system["cell_ids"])
            self.assertIn(first_channel_system["outlet_cell_id"], first_channel_system["cell_ids"])
            self.assertGreaterEqual(first_channel_system["length_km"], 0.0)
            self.assertGreaterEqual(first_channel_system["area_km2"], 0.0)
            self.assertEqual(
                sum(first_channel_system["channel_morphology_class_counts"].values()),
                first_channel_system["cell_count"],
            )
            for key in (
                "mean_channel_width_m",
                "mean_channel_depth_m",
                "mean_bankfull_discharge_m3_s",
                "mean_stream_power_index",
                "mean_channel_slope_index",
                "mean_floodplain_connectivity_index",
            ):
                self.assertGreaterEqual(first_channel_system[key], 0.0)
            for key in (
                "mean_stream_power_index",
                "mean_channel_slope_index",
                "mean_floodplain_connectivity_index",
            ):
                self.assertLessEqual(first_channel_system[key], 1.0)
        for key in (
            "protected_bay_index",
            "river_mouth_port_index",
            "strait_access_index",
            "port_suitability_index",
            "port_site_type",
            "port_site_id",
        ):
            self.assertIn(key, first_cell)
        for key in (
            "protected_bay_index",
            "river_mouth_port_index",
            "strait_access_index",
            "port_suitability_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertGreaterEqual(first_cell["port_site_id"], -1)
        if first_cell["port_site_id"] == -1:
            self.assertEqual(first_cell["port_site_type"], "none")
        else:
            self.assertNotEqual(first_cell["port_site_type"], "none")
        if world["port_sites"]:
            first_port_site = world["port_sites"][0]
            self.assertEqual(first_port_site["id"], 0)
            self.assertIn(
                first_port_site["site_type"],
                {
                    "protected_bay_port",
                    "river_mouth_port",
                    "strait_port",
                    "harbor_port",
                    "coastal_port",
                    "port_settlement",
                },
            )
            self.assertGreaterEqual(first_port_site["area_km2"], 0.0)
            for key in (
                "port_suitability_index",
                "protected_bay_index",
                "river_mouth_port_index",
                "strait_access_index",
                "harbor_suitability_index",
                "navigability_index",
            ):
                self.assertGreaterEqual(first_port_site[key], 0.0)
                self.assertLessEqual(first_port_site[key], 1.0)
            self.assertIn("settlement_ids", first_port_site)
            self.assertIn("port_settlement_ids", first_port_site)
            self.assertIn("route_ids", first_port_site)
            self.assertIn("marine_region_ids", first_port_site)
            self.assertIn("marine_chokepoint_ids", first_port_site)
            self.assertIn("navigable_waterway_ids", first_port_site)
        route_corridor_cells = {
            cell_id for corridor in world["route_corridors"] for cell_id in corridor["cell_ids"]
        }
        self.assertEqual(summary["route_corridor_count"], len(world["route_corridors"]))
        self.assertEqual(summary["route_corridor_count"], len(world["routes"]))
        self.assertEqual(summary["route_corridor_cell_count"], len(route_corridor_cells))
        self.assertAlmostEqual(
            summary["route_corridor_total_path_length_km"],
            sum(corridor["path_length_km"] for corridor in world["route_corridors"]),
            delta=max(0.001, summary["route_corridor_total_path_length_km"] * 0.0001),
        )
        for summary_key, cell_key in (
            ("mean_route_corridor_index", "route_corridor_index"),
            ("mean_mountain_pass_route_index", "mountain_pass_route_index"),
            ("mean_river_valley_route_index", "river_valley_route_index"),
            ("mean_coastal_route_index", "coastal_route_index"),
            ("mean_oasis_route_index", "oasis_route_index"),
        ):
            self.assertAlmostEqual(
                summary[summary_key],
                sum(cell[cell_key] for cell in world["cells"]) / len(world["cells"]),
                delta=0.001,
            )
        self.assertEqual(sum(summary["route_corridor_type_counts"].values()), summary["route_corridor_count"])
        self.assertGreaterEqual(summary["route_feature_coverage_index"], 0.0)
        self.assertLessEqual(summary["route_feature_coverage_index"], 1.0)
        for key in (
            "mountain_pass_route_index",
            "river_valley_route_index",
            "coastal_route_index",
            "oasis_route_index",
            "route_corridor_index",
            "route_corridor_type",
            "route_corridor_id",
        ):
            self.assertIn(key, first_cell)
        for key in (
            "mountain_pass_route_index",
            "river_valley_route_index",
            "coastal_route_index",
            "oasis_route_index",
            "route_corridor_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        if first_cell["route_corridor_id"] == -1:
            self.assertEqual(first_cell["route_corridor_type"], "none")
            self.assertEqual(first_cell["route_corridor_index"], 0.0)
        else:
            self.assertNotEqual(first_cell["route_corridor_type"], "none")
        if world["route_corridors"]:
            first_corridor = world["route_corridors"][0]
            first_route = next(route for route in world["routes"] if route["id"] == first_corridor["route_id"])
            self.assertEqual(first_corridor["id"], 0)
            self.assertEqual(first_route["route_corridor_id"], first_corridor["id"])
            self.assertEqual(first_route["route_corridor_type"], first_corridor["corridor_type"])
            self.assertEqual(first_route["path_cell_ids"], first_corridor["cell_ids"])
            self.assertEqual(first_corridor["route_ids"], [first_route["id"]])
            self.assertEqual(first_corridor["cell_count"], len(first_corridor["cell_ids"]))
            self.assertEqual(first_corridor["start_cell_id"], first_corridor["cell_ids"][0])
            self.assertEqual(first_corridor["end_cell_id"], first_corridor["cell_ids"][-1])
            self.assertGreater(first_corridor["path_length_km"], 0.0)
            self.assertGreaterEqual(first_corridor["detour_ratio"], 0.0)
            self.assertIn(
                first_corridor["corridor_type"],
                {
                    "mountain_pass_corridor",
                    "river_valley_corridor",
                    "coastal_corridor",
                    "oasis_corridor",
                    "overland_corridor",
                },
            )
            self.assertLessEqual(first_corridor["named_feature_cell_count"], first_corridor["cell_count"])
            self.assertGreaterEqual(
                first_corridor["named_feature_cell_count"],
                max(
                    first_corridor["mountain_pass_cell_count"],
                    first_corridor["river_valley_cell_count"],
                    first_corridor["coastal_cell_count"],
                    first_corridor["oasis_cell_count"],
                ),
            )
            for key in (
                "mean_route_corridor_index",
                "max_route_corridor_index",
                "mean_mountain_pass_route_index",
                "mean_river_valley_route_index",
                "mean_coastal_route_index",
                "mean_oasis_route_index",
            ):
                self.assertGreaterEqual(first_corridor[key], 0.0)
                self.assertLessEqual(first_corridor[key], 1.0)
        self.assertIn("river_capture_risk", first_cell)
        self.assertIn("river_capture_target_cell_id", first_cell)
        self.assertIn("river_capture_target_basin_id", first_cell)
        self.assertIn("river_capture_divide_relief_m", first_cell)
        self.assertIn("river_capture_target_distance_km", first_cell)
        self.assertIn("river_avulsion_risk", first_cell)
        self.assertIn("river_network_instability_index", first_cell)
        self.assertGreaterEqual(first_cell["river_capture_risk"], 0.0)
        self.assertLessEqual(first_cell["river_capture_risk"], 1.0)
        self.assertGreaterEqual(first_cell["river_capture_divide_relief_m"], 0.0)
        self.assertGreaterEqual(first_cell["river_capture_target_distance_km"], 0.0)
        self.assertGreaterEqual(first_cell["river_avulsion_risk"], 0.0)
        self.assertLessEqual(first_cell["river_avulsion_risk"], 1.0)
        self.assertEqual(
            first_cell["river_network_instability_index"],
            max(first_cell["river_capture_risk"], first_cell["river_avulsion_risk"]),
        )
        self.assertIn("sediment_thickness_m", first_cell)
        self.assertIn("sediment_production_m", first_cell)
        self.assertIn("sediment_deposition_m", first_cell)
        self.assertIn("sediment_export_m", first_cell)
        self.assertIn("sediment_net_budget_m", first_cell)
        self.assertIn("fluvial_sediment_local_source_m", first_cell)
        self.assertIn("fluvial_sediment_routed_incoming_m", first_cell)
        self.assertIn("fluvial_sediment_routed_outgoing_m", first_cell)
        self.assertIn("fluvial_sediment_local_deposition_m", first_cell)
        self.assertIn("fluvial_sediment_terminal_land_deposition_m", first_cell)
        self.assertIn("fluvial_sediment_marine_deposition_m", first_cell)
        self.assertIn("fluvial_sediment_depression_fill_m", first_cell)
        self.assertIn("fluvial_sediment_terminal_export_m", first_cell)
        self.assertIn("fluvial_sediment_terminal_capture_volume_km3", first_cell)
        self.assertIn("fluvial_sediment_routing_event_count", first_cell)
        self.assertIn("hillslope_sediment_production_m", first_cell)
        self.assertIn("hillslope_sediment_deposition_m", first_cell)
        self.assertIn("hillslope_sediment_net_m", first_cell)
        self.assertIn("hillslope_sediment_outgoing_edge_count", first_cell)
        self.assertIn("hillslope_sediment_incoming_edge_count", first_cell)
        self.assertIn("sediment_routing_load_m", first_cell)
        self.assertIn("sediment_routing_deposition_m", first_cell)
        self.assertIn("sediment_routing_export_m", first_cell)
        self.assertIn("sediment_routing_path_count", first_cell)
        self.assertGreaterEqual(first_cell["sediment_routing_load_m"], 0.0)
        self.assertGreaterEqual(first_cell["sediment_routing_deposition_m"], 0.0)
        self.assertGreaterEqual(first_cell["sediment_routing_export_m"], 0.0)
        self.assertGreaterEqual(first_cell["sediment_routing_path_count"], 0)
        self.assertIn("landform", first_cell)
        self.assertIn("soil_texture_class", first_cell)
        self.assertIn("soil_drainage_index", first_cell)
        self.assertIn("soil_moisture_index", first_cell)
        self.assertIn("soil_ph", first_cell)
        self.assertIn("soil_organic_matter_fraction", first_cell)
        self.assertIn("soil_salinity_index", first_cell)
        self.assertIn("soil_erodibility_index", first_cell)
        self.assertIn("soil_profile_development_index", first_cell)
        self.assertIn("soil_profile_id", first_cell)
        self.assertIn("soil_horizon_count", first_cell)
        self.assertGreaterEqual(first_cell["soil_drainage_index"], 0.0)
        self.assertLessEqual(first_cell["soil_drainage_index"], 1.0)
        self.assertGreaterEqual(first_cell["soil_moisture_index"], 0.0)
        self.assertLessEqual(first_cell["soil_moisture_index"], 1.0)
        self.assertGreaterEqual(first_cell["soil_ph"], 3.5)
        self.assertLessEqual(first_cell["soil_ph"], 9.5)
        self.assertGreaterEqual(first_cell["soil_organic_matter_fraction"], 0.0)
        self.assertLessEqual(first_cell["soil_organic_matter_fraction"], 0.5)
        self.assertGreaterEqual(first_cell["soil_salinity_index"], 0.0)
        self.assertLessEqual(first_cell["soil_salinity_index"], 1.0)
        self.assertGreaterEqual(first_cell["soil_erodibility_index"], 0.0)
        self.assertLessEqual(first_cell["soil_erodibility_index"], 1.0)
        self.assertGreaterEqual(first_cell["soil_profile_development_index"], 0.0)
        self.assertLessEqual(first_cell["soil_profile_development_index"], 1.0)
        self.assertGreaterEqual(first_cell["soil_horizon_count"], 0)
        if world["soil_profiles"]:
            first_profile = world["soil_profiles"][0]
            self.assertIn("cell_id", first_profile)
            self.assertIn("horizon_ids", first_profile)
            self.assertIn("horizon_count", first_profile)
            self.assertIn("total_depth_m", first_profile)
            self.assertIn("parent_material", first_profile)
            self.assertIn("profile_class", first_profile)
            self.assertIn("soil_profile_history_id", first_profile)
            self.assertIn("weathering_index", first_profile)
            self.assertIn("leaching_index", first_profile)
            self.assertIn("bioturbation_index", first_profile)
            self.assertEqual(first_profile["horizon_count"], len(first_profile["horizon_ids"]))
            self.assertGreater(first_profile["total_depth_m"], 0.0)
            for key in ("drainage_index", "moisture_index", "salinity_index", "erodibility_index", "development_index", "weathering_index", "leaching_index", "bioturbation_index"):
                self.assertGreaterEqual(first_profile[key], 0.0)
                self.assertLessEqual(first_profile[key], 1.0)
            first_soil_history = world["soil_profile_histories"][first_profile["soil_profile_history_id"]]
            self.assertEqual(first_soil_history["soil_profile_id"], first_profile["id"])
            self.assertEqual(first_soil_history["cell_id"], first_profile["cell_id"])
            self.assertEqual(first_soil_history["horizon_count"], len(first_soil_history["horizon_ids"]))
            self.assertEqual(first_soil_history["horizon_ids"], first_profile["horizon_ids"])
            self.assertEqual(first_soil_history["parent_material"], first_profile["parent_material"])
            self.assertEqual(first_soil_history["profile_class"], first_profile["profile_class"])
            self.assertEqual(first_soil_history["step_count"], len(first_soil_history["steps"]))
            self.assertGreaterEqual(first_soil_history["initial_depth_m"], 0.0)
            self.assertGreater(first_soil_history["final_depth_m"], 0.0)
            self.assertAlmostEqual(first_soil_history["final_depth_m"], first_profile["total_depth_m"], delta=0.001)
            self.assertAlmostEqual(first_soil_history["final_profile_age_ka"], first_profile["profile_age_ka"], delta=0.001)
            self.assertGreaterEqual(first_soil_history["total_soil_production_m"], 0.0)
            self.assertGreaterEqual(first_soil_history["total_erosion_loss_m"], 0.0)
            self.assertIsInstance(first_soil_history["high_erosion_pressure"], bool)
            for key in (
                "mean_weathering_index",
                "mean_leaching_index",
                "mean_bioturbation_index",
                "mean_horizon_differentiation_index",
                "mean_pedogenic_flux_index",
            ):
                self.assertGreaterEqual(first_soil_history[key], 0.0)
                self.assertLessEqual(first_soil_history[key], 1.0)
            previous_end_depth = first_soil_history["initial_depth_m"]
            for index, step in enumerate(first_soil_history["steps"]):
                self.assertEqual(step["stage_index"], index + 1)
                self.assertIn("era_id", step)
                self.assertGreaterEqual(step["start_year_bp"], step["end_year_bp"])
                self.assertAlmostEqual(step["start_depth_m"], previous_end_depth, delta=0.001)
                self.assertGreaterEqual(step["end_depth_m"], 0.0)
                self.assertGreaterEqual(step["soil_production_m"], 0.0)
                self.assertGreaterEqual(step["erosion_loss_m"], 0.0)
                for key in (
                    "weathering_index",
                    "leaching_index",
                    "bioturbation_index",
                    "organic_accumulation_index",
                    "horizon_differentiation_index",
                    "clay_translocation_index",
                    "carbonate_mobilization_index",
                    "salinization_index",
                    "erosion_pressure_index",
                    "pedogenic_flux_index",
                ):
                    self.assertGreaterEqual(step[key], 0.0)
                    self.assertLessEqual(step[key], 1.0)
                previous_end_depth = step["end_depth_m"]
            self.assertAlmostEqual(
                first_soil_history["steps"][-1]["end_depth_m"],
                first_soil_history["final_depth_m"],
                delta=max(0.001, first_soil_history["final_depth_m"] * 0.0001),
            )
            first_horizon = world["soil_horizons"][first_profile["horizon_ids"][0]]
            self.assertEqual(first_horizon["soil_profile_id"], first_profile["id"])
            self.assertEqual(first_horizon["cell_id"], first_profile["cell_id"])
            self.assertGreater(first_horizon["thickness_m"], 0.0)
            self.assertAlmostEqual(
                first_horizon["bottom_depth_m"] - first_horizon["top_depth_m"],
                first_horizon["thickness_m"],
                delta=max(0.001, first_horizon["thickness_m"] * 0.0001),
            )
            self.assertAlmostEqual(
                first_horizon["sand_fraction"] + first_horizon["silt_fraction"] + first_horizon["clay_fraction"],
                1.0,
                delta=0.001,
            )
            for key in ("organic_matter_fraction", "carbonate_index", "salinity_index", "root_density_index", "weathering_index"):
                self.assertGreaterEqual(first_horizon[key], 0.0)
                self.assertLessEqual(first_horizon[key], 1.0)
        first_biome_diagnostic = world["biome_diagnostics"][0]
        self.assertEqual(first_biome_diagnostic["id"], 0)
        self.assertEqual(first_biome_diagnostic["cell_id"], first_cell["id"])
        self.assertEqual(first_biome_diagnostic["biome"], first_cell["biome"])
        self.assertTrue(first_biome_diagnostic["expected_biome"])
        self.assertTrue(first_biome_diagnostic["limiting_factor"])
        self.assertGreaterEqual(first_biome_diagnostic["potential_evapotranspiration_mm_y"], 0.0)
        self.assertGreaterEqual(first_biome_diagnostic["climatic_water_deficit_mm_y"], 0.0)
        self.assertGreaterEqual(first_biome_diagnostic["climatic_water_surplus_mm_y"], 0.0)
        self.assertGreaterEqual(first_biome_diagnostic["growing_season_months"], 0)
        self.assertLessEqual(first_biome_diagnostic["growing_season_months"], 12)
        self.assertGreaterEqual(first_biome_diagnostic["frost_months"], 0)
        self.assertLessEqual(first_biome_diagnostic["frost_months"], 12)
        self.assertGreaterEqual(first_biome_diagnostic["dry_season_months"], 0)
        self.assertLessEqual(first_biome_diagnostic["dry_season_months"], 12)
        self.assertGreaterEqual(first_biome_diagnostic["wet_season_months"], 0)
        self.assertLessEqual(first_biome_diagnostic["wet_season_months"], 12)
        for key in (
            "soil_moisture_index",
            "seasonal_aridity_index",
            "fire_frequency_index",
            "ecotone_index",
            "biome_confidence_index",
        ):
            self.assertGreaterEqual(first_biome_diagnostic[key], 0.0)
            self.assertLessEqual(first_biome_diagnostic[key], 1.0)
        self.assertIsInstance(first_biome_diagnostic["biome_transition_zone"], bool)
        self.assertAlmostEqual(
            first_biome_diagnostic["potential_evapotranspiration_mm_y"],
            first_cell["potential_evapotranspiration_mm_y"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            first_biome_diagnostic["climatic_water_deficit_mm_y"],
            first_cell["climatic_water_deficit_mm_y"],
            delta=0.001,
        )
        for key in (
            "biome_ecotone_type",
            "biome_ecotone_confidence",
            "biome_ecotone_region_id",
        ):
            self.assertIn(key, first_cell)
        self.assertTrue(first_cell["biome_ecotone_type"])
        self.assertGreaterEqual(first_cell["biome_ecotone_confidence"], 0.0)
        self.assertLessEqual(first_cell["biome_ecotone_confidence"], 1.0)
        self.assertGreaterEqual(first_cell["biome_ecotone_region_id"], -1)
        for key in (
            "groundwater_recharge_mm_y",
            "groundwater_recharge_km3_y",
            "aquifer_storage_index",
            "aquifer_quality_index",
            "aquifer_productivity_index",
            "aquifer_extraction_risk_index",
            "aquifer_class",
            "aquifer_system_id",
            "groundwater_hydraulic_head_m",
            "groundwater_gradient_index",
            "groundwater_lateral_flow_km3_y",
            "groundwater_lateral_inflow_km3_y",
            "groundwater_available_volume_km3_y",
            "groundwater_internal_lateral_outflow_km3_y",
            "groundwater_discharge_mm_y",
            "groundwater_discharge_km3_y",
            "groundwater_retained_storage_km3_y",
            "groundwater_flow_mass_balance_residual_km3_y",
            "groundwater_flow_to_cell_id",
            "spring_discharge_index",
            "baseflow_support_index",
            "groundwater_flow_regime",
            "groundwater_flow_system_id",
            "actual_evapotranspiration_mm_y",
            "infiltration_capacity_index",
            "infiltration_mm_y",
            "hydrologic_water_balance_mm_y",
            "water_budget_runoff_mm_y",
            "runoff_budget_residual_mm_y",
            "runoff_budget_consistency_index",
            "hydrologic_deficit_mm_y",
            "runoff_generation_fraction",
            "hydrologic_budget_class",
            "hydrologic_budget_region_id",
            "wetland_extent_index",
            "wetland_hydrology_index",
            "wetland_soil_saturation_index",
            "wetland_ecotone_index",
            "wetland_connectivity_index",
            "wetland_coastal_flag",
            "wetland_system_type",
            "wetland_system_id",
            "karst_potential_index",
            "cave_development_index",
            "subterranean_drainage_fraction",
            "karst_system_id",
        ):
            self.assertIn(key, first_cell)
        self.assertGreaterEqual(first_cell["groundwater_recharge_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["groundwater_recharge_km3_y"], 0.0)
        for key in (
            "aquifer_storage_index",
            "aquifer_quality_index",
            "aquifer_productivity_index",
            "aquifer_extraction_risk_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertTrue(first_cell["aquifer_class"])
        self.assertGreaterEqual(first_cell["aquifer_system_id"], -1)
        self.assertIsInstance(first_cell["groundwater_hydraulic_head_m"], (int, float))
        self.assertGreaterEqual(first_cell["groundwater_gradient_index"], 0.0)
        self.assertLessEqual(first_cell["groundwater_gradient_index"], 1.0)
        self.assertGreaterEqual(first_cell["groundwater_lateral_flow_km3_y"], 0.0)
        self.assertGreaterEqual(first_cell["groundwater_lateral_inflow_km3_y"], 0.0)
        self.assertGreaterEqual(first_cell["groundwater_available_volume_km3_y"], 0.0)
        self.assertGreaterEqual(
            first_cell["groundwater_internal_lateral_outflow_km3_y"],
            0.0,
        )
        self.assertGreaterEqual(first_cell["groundwater_discharge_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["groundwater_discharge_km3_y"], 0.0)
        self.assertGreaterEqual(
            first_cell["groundwater_retained_storage_km3_y"],
            0.0,
        )
        self.assertGreaterEqual(first_cell["groundwater_flow_to_cell_id"], -1)
        self.assertGreaterEqual(first_cell["spring_discharge_index"], 0.0)
        self.assertLessEqual(first_cell["spring_discharge_index"], 1.0)
        self.assertGreaterEqual(first_cell["baseflow_support_index"], 0.0)
        self.assertLessEqual(first_cell["baseflow_support_index"], 1.0)
        self.assertIn(
            first_cell["groundwater_flow_regime"],
            {
                "excluded",
                "recharge_mound",
                "recharge_throughflow",
                "throughflow",
                "discharge_zone",
                "lowland_discharge",
                "stagnant_or_low_yield",
            },
        )
        self.assertGreaterEqual(first_cell["groundwater_flow_system_id"], -1)
        self.assertGreaterEqual(first_cell["actual_evapotranspiration_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["infiltration_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["water_budget_runoff_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["hydrologic_deficit_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["infiltration_capacity_index"], 0.0)
        self.assertLessEqual(first_cell["infiltration_capacity_index"], 1.0)
        self.assertGreaterEqual(first_cell["runoff_budget_consistency_index"], 0.0)
        self.assertLessEqual(first_cell["runoff_budget_consistency_index"], 1.0)
        self.assertGreaterEqual(first_cell["runoff_generation_fraction"], 0.0)
        self.assertLessEqual(first_cell["runoff_generation_fraction"], 1.0)
        self.assertIn(
            first_cell["hydrologic_budget_class"],
            {
                "marine_budget",
                "water_deficit",
                "runoff_surplus",
                "infiltration_dominated",
                "evapotranspiration_dominated",
                "balanced_budget",
            },
        )
        self.assertGreaterEqual(first_cell["hydrologic_budget_region_id"], -1)
        for key in (
            "wetland_extent_index",
            "wetland_hydrology_index",
            "wetland_soil_saturation_index",
            "wetland_ecotone_index",
            "wetland_connectivity_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertIn(
            first_cell["wetland_system_type"],
            {
                "none",
                "mangrove",
                "tidal_marsh",
                "delta_wetland",
                "floodplain_wetland",
                "lacustrine_wetland",
                "peatland",
                "freshwater_swamp",
            },
        )
        self.assertGreaterEqual(first_cell["wetland_system_id"], -1)
        for key in (
            "karst_potential_index",
            "cave_development_index",
            "subterranean_drainage_fraction",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertGreaterEqual(first_cell["karst_system_id"], -1)
        if world["aquifer_systems"]:
            first_aquifer = world["aquifer_systems"][0]
            self.assertEqual(first_aquifer["id"], 0)
            self.assertGreater(first_aquifer["cell_count"], 0)
            self.assertEqual(first_aquifer["cell_count"], len(first_aquifer["cell_ids"]))
            self.assertTrue(first_aquifer["aquifer_class"])
            self.assertTrue(first_aquifer["primary_lithology"])
            self.assertTrue(first_aquifer["dominant_landform"])
            self.assertGreaterEqual(first_aquifer["area_km2"], 0.0)
            self.assertGreaterEqual(first_aquifer["total_groundwater_recharge_km3_y"], 0.0)
            self.assertEqual(sum(first_aquifer["aquifer_class_counts"].values()), first_aquifer["cell_count"])
            for key in (
                "mean_aquifer_storage_index",
                "mean_aquifer_quality_index",
                "mean_aquifer_productivity_index",
                "mean_aquifer_extraction_risk_index",
                "closed_basin_fraction",
            ):
                self.assertGreaterEqual(first_aquifer[key], 0.0)
                self.assertLessEqual(first_aquifer[key], 1.0)
        if world["groundwater_flow_systems"]:
            first_flow_system = world["groundwater_flow_systems"][0]
            self.assertEqual(first_flow_system["id"], 0)
            self.assertGreater(first_flow_system["cell_count"], 0)
            self.assertEqual(first_flow_system["cell_count"], len(first_flow_system["cell_ids"]))
            self.assertGreaterEqual(first_flow_system["aquifer_system_id"], 0)
            self.assertIn(first_flow_system["outlet_cell_id"], first_flow_system["cell_ids"])
            self.assertEqual(sum(first_flow_system["flow_regime_counts"].values()), first_flow_system["cell_count"])
            self.assertGreaterEqual(first_flow_system["area_km2"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_recharge_km3_y"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_lateral_inflow_km3_y"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_internal_lateral_outflow_km3_y"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_discharge_km3_y"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_lateral_flow_km3_y"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_retained_storage_km3_y"], 0.0)
            self.assertAlmostEqual(
                first_flow_system["total_groundwater_recharge_km3_y"]
                + first_flow_system["total_groundwater_lateral_inflow_km3_y"],
                first_flow_system["total_groundwater_internal_lateral_outflow_km3_y"]
                + first_flow_system["total_groundwater_discharge_km3_y"]
                + first_flow_system["total_groundwater_retained_storage_km3_y"]
                + first_flow_system["groundwater_flow_mass_balance_residual_km3_y"],
                delta=0.001,
            )
            self.assertGreaterEqual(first_flow_system["discharge_to_recharge_ratio"], 0.0)
            for key in (
                "mean_groundwater_gradient_index",
                "mean_spring_discharge_index",
                "mean_baseflow_support_index",
                "mean_aquifer_extraction_risk_index",
            ):
                self.assertGreaterEqual(first_flow_system[key], 0.0)
                self.assertLessEqual(first_flow_system[key], 1.0)
        if world["karst_systems"]:
            first_karst = world["karst_systems"][0]
            self.assertEqual(first_karst["id"], 0)
            self.assertGreater(first_karst["cell_count"], 0)
            self.assertEqual(first_karst["cell_count"], len(first_karst["cell_ids"]))
            self.assertTrue(first_karst["dominant_lithology"])
            self.assertTrue(first_karst["primary_aquifer_class"])
            self.assertIsInstance(first_karst["aquifer_system_ids"], list)
            self.assertGreaterEqual(first_karst["area_km2"], 0.0)
            for key in (
                "mean_karst_potential_index",
                "mean_cave_development_index",
                "mean_subterranean_drainage_fraction",
                "limestone_cell_fraction",
            ):
                self.assertGreaterEqual(first_karst[key], 0.0)
                self.assertLessEqual(first_karst[key], 1.0)
        if world["biome_ecotone_regions"]:
            first_ecotone = world["biome_ecotone_regions"][0]
            self.assertEqual(first_ecotone["id"], 0)
            self.assertTrue(first_ecotone["ecotone_type"])
            self.assertNotEqual(first_ecotone["ecotone_type"], "none")
            self.assertGreater(first_ecotone["cell_count"], 0)
            self.assertEqual(first_ecotone["cell_count"], len(first_ecotone["cell_ids"]))
            self.assertGreaterEqual(first_ecotone["area_km2"], 0.0)
            self.assertTrue(first_ecotone["dominant_biome"])
            self.assertGreaterEqual(first_ecotone["mean_ecotone_confidence"], 0.0)
            self.assertLessEqual(first_ecotone["mean_ecotone_confidence"], 1.0)
            self.assertGreaterEqual(first_ecotone["mean_precipitation_mm_y"], 0.0)
            self.assertGreaterEqual(first_ecotone["coastal_cell_count"], 0)
        for key in (
            "primary_productivity_index",
            "vegetation_biomass_index",
            "species_richness_index",
            "wildfire_spread_risk_index",
            "ecosystem_disturbance_pressure_index",
            "vegetation_succession_stage",
            "vegetation_recovery_years",
            "forest_growth_index",
            "fishery_productivity_index",
        ):
            self.assertIn(key, first_cell)
        for key in (
            "primary_productivity_index",
            "vegetation_biomass_index",
            "species_richness_index",
            "wildfire_spread_risk_index",
            "ecosystem_disturbance_pressure_index",
            "forest_growth_index",
            "fishery_productivity_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertTrue(first_cell["vegetation_succession_stage"])
        self.assertGreaterEqual(first_cell["vegetation_recovery_years"], 1)
        if world["vegetation_succession_histories"]:
            first_succession = world["vegetation_succession_histories"][0]
            self.assertEqual(first_succession["id"], 0)
            self.assertGreater(first_succession["step_count"], 0)
            self.assertEqual(first_succession["step_count"], len(first_succession["steps"]))
            self.assertTrue(first_succession["initial_succession_stage"])
            self.assertTrue(first_succession["final_succession_stage"])
            self.assertGreaterEqual(first_succession["recovery_years"], 1)
            for key in (
                "mean_biomass_index",
                "mean_canopy_closure_index",
                "mean_disturbance_pressure_index",
                "max_wildfire_spread_risk_index",
            ):
                self.assertGreaterEqual(first_succession[key], 0.0)
                self.assertLessEqual(first_succession[key], 1.0)
            first_step = first_succession["steps"][0]
            self.assertTrue(first_step["phase"])
            self.assertGreaterEqual(first_step["years_since_start"], 0)
            self.assertTrue(first_step["succession_stage"])
            for key in (
                "biomass_index",
                "canopy_closure_index",
                "primary_productivity_index",
                "disturbance_pressure_index",
                "wildfire_spread_risk_index",
                "recovery_fraction",
            ):
                self.assertGreaterEqual(first_step[key], 0.0)
                self.assertLessEqual(first_step[key], 1.0)
        if world["renewable_resource_records"]:
            first_renewable = world["renewable_resource_records"][0]
            renewable_cell = world["cells"][first_renewable["cell_id"]]
            self.assertEqual(first_renewable["id"], 0)
            self.assertIn(first_renewable["resource_type"], {"forest_growth", "fishery_productivity"})
            self.assertEqual(first_renewable["biome"], renewable_cell["biome"])
            self.assertEqual(first_renewable["water_body_type"], renewable_cell["water_body_type"])
            self.assertGreaterEqual(first_renewable["productivity_index"], 0.0)
            self.assertLessEqual(first_renewable["productivity_index"], 1.0)
            self.assertGreaterEqual(first_renewable["sustainable_yield_index"], 0.0)
            self.assertLessEqual(first_renewable["sustainable_yield_index"], 1.0)
            self.assertGreaterEqual(first_renewable["regeneration_years"], 1)
            self.assertGreaterEqual(first_renewable["climate_dependency_index"], 0.0)
            self.assertLessEqual(first_renewable["climate_dependency_index"], 1.0)
            self.assertGreaterEqual(first_renewable["water_dependency_index"], 0.0)
            self.assertLessEqual(first_renewable["water_dependency_index"], 1.0)
            self.assertAlmostEqual(
                first_renewable["disturbance_risk_index"],
                renewable_cell["ecosystem_disturbance_pressure_index"],
                delta=0.001,
            )
            self.assertIn("primary_productivity_index", first_renewable["formation_evidence"])
        for key in (
            "dominant_species_guild",
            "species_habitat_suitability_index",
            "species_endemism_index",
            "species_range_fragmentation_index",
            "species_composition_confidence_index",
            "species_guild_richness_count",
            "species_range_record_ids",
        ):
            self.assertIn(key, first_cell)
        self.assertTrue(first_cell["dominant_species_guild"])
        for key in (
            "species_habitat_suitability_index",
            "species_endemism_index",
            "species_range_fragmentation_index",
            "species_composition_confidence_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertGreaterEqual(first_cell["species_guild_richness_count"], 0)
        self.assertIsInstance(first_cell["species_range_record_ids"], list)
        if world["species_range_records"]:
            first_species_range = world["species_range_records"][0]
            self.assertEqual(first_species_range["id"], 0)
            self.assertIn(
                first_species_range["guild_type"],
                {
                    "canopy_tree",
                    "grassland_grazer",
                    "desert_specialist",
                    "alpine_tundra_specialist",
                    "wetland_amphibian",
                    "large_predator",
                    "freshwater_fish",
                    "marine_fish",
                    "reef_builder",
                    "mangrove_coastal_bird",
                },
            )
            self.assertIn(
                first_species_range["habitat_class"],
                {"terrestrial", "arid", "alpine", "wetland", "freshwater", "marine", "reef"},
            )
            self.assertTrue(first_species_range["trophic_role"])
            self.assertGreater(first_species_range["cell_count"], 0)
            self.assertEqual(first_species_range["cell_count"], len(first_species_range["cell_ids"]))
            self.assertGreaterEqual(first_species_range["area_km2"], 0.0)
            for key in (
                "mean_habitat_suitability_index",
                "max_habitat_suitability_index",
                "mean_species_richness_index",
                "mean_primary_productivity_index",
                "mean_disturbance_pressure_index",
                "mean_composition_confidence_index",
                "range_fragmentation_index",
                "endemism_index",
                "conservation_stress_index",
            ):
                self.assertGreaterEqual(first_species_range[key], 0.0)
                self.assertLessEqual(first_species_range[key], 1.0)
            self.assertIn("mean_temperature_c", first_species_range["climate_envelope"])
            self.assertIn("mean_precipitation_mm_y", first_species_range["climate_envelope"])
            self.assertIn("mean_wetland_extent_index", first_species_range["habitat_evidence"])
            species_cell = world["cells"][first_species_range["cell_ids"][0]]
            self.assertIn(first_species_range["id"], species_cell["species_range_record_ids"])
        for key in (
            "wildfire_ignition_potential_index",
            "wildfire_fuel_continuity_index",
            "wildfire_wind_alignment_index",
            "wildfire_firebreak_index",
            "wildfire_disturbance_regime",
            "wildfire_spread_history_ids",
        ):
            self.assertIn(key, first_cell)
        for key in (
            "wildfire_ignition_potential_index",
            "wildfire_fuel_continuity_index",
            "wildfire_wind_alignment_index",
            "wildfire_firebreak_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertTrue(first_cell["wildfire_disturbance_regime"])
        self.assertIsInstance(first_cell["wildfire_spread_history_ids"], list)
        if world["wildfire_spread_histories"]:
            first_wildfire = world["wildfire_spread_histories"][0]
            self.assertEqual(first_wildfire["id"], 0)
            self.assertIn(first_wildfire["ignition_cell_id"], first_wildfire["cell_ids"])
            self.assertGreater(first_wildfire["cell_count"], 0)
            self.assertEqual(first_wildfire["cell_count"], len(first_wildfire["cell_ids"]))
            self.assertGreaterEqual(first_wildfire["area_km2"], 0.0)
            self.assertTrue(first_wildfire["dominant_biome"])
            self.assertTrue(first_wildfire["dominant_disturbance_regime"])
            for key in (
                "mean_wildfire_spread_risk_index",
                "mean_ignition_potential_index",
                "mean_fuel_continuity_index",
                "mean_wind_alignment_index",
                "mean_firebreak_index",
                "mean_ecosystem_disturbance_pressure_index",
                "max_spread_probability_index",
                "containment_index",
            ):
                self.assertGreaterEqual(first_wildfire[key], 0.0)
                self.assertLessEqual(first_wildfire[key], 1.0)
            self.assertEqual(first_wildfire["spread_step_count"], len(first_wildfire["steps"]))
            self.assertGreater(first_wildfire["spread_step_count"], 0)
            self.assertEqual(sum(first_wildfire["disturbance_regime_counts"].values()), first_wildfire["cell_count"])
            first_fire_step = first_wildfire["steps"][0]
            self.assertEqual(first_fire_step["step_index"], 0)
            self.assertGreater(first_fire_step["cumulative_burned_cell_count"], 0)
            self.assertGreaterEqual(first_fire_step["burned_area_km2"], 0.0)
            self.assertGreaterEqual(first_fire_step["mean_spread_probability_index"], 0.0)
            self.assertLessEqual(first_fire_step["mean_spread_probability_index"], 1.0)
            fire_cell = world["cells"][first_wildfire["cell_ids"][0]]
            self.assertIn(first_wildfire["id"], fire_cell["wildfire_spread_history_ids"])
        for key in (
            "petroleum_source_rock_index",
            "petroleum_maturation_index",
            "petroleum_migration_path_index",
            "petroleum_trap_integrity_index",
            "petroleum_accumulation_index",
            "petroleum_system_id",
        ):
            self.assertIn(key, first_cell)
        for key in (
            "petroleum_source_rock_index",
            "petroleum_maturation_index",
            "petroleum_migration_path_index",
            "petroleum_trap_integrity_index",
            "petroleum_accumulation_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertGreaterEqual(first_cell["petroleum_system_id"], -1)
        for key in (
            "ore_genesis_potential_index",
            "hydrothermal_alteration_index",
            "metallogenic_fertility_index",
            "ore_structural_control_index",
            "placer_concentration_index",
            "ore_genesis_system_id",
        ):
            self.assertIn(key, first_cell)
        for key in (
            "ore_genesis_potential_index",
            "hydrothermal_alteration_index",
            "metallogenic_fertility_index",
            "ore_structural_control_index",
            "placer_concentration_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertGreaterEqual(first_cell["ore_genesis_system_id"], -1)
        if world["resource_deposits"]:
            first_deposit = world["resource_deposits"][0]
            deposit_cell = world["cells"][first_deposit["cell_id"]]
            self.assertEqual(first_deposit["id"], 0)
            self.assertEqual(first_deposit["resource"], deposit_cell["resource"])
            self.assertNotEqual(first_deposit["resource"], "none")
            self.assertIn(first_deposit["deposit_class"], {"metal", "energy", "industrial_mineral", "bioproductive", "other"})
            self.assertTrue(first_deposit["formation_process"])
            self.assertEqual(first_deposit["host_crust_type"], deposit_cell["crust_type"])
            self.assertEqual(first_deposit["host_lithology"], deposit_cell["lithology"])
            self.assertEqual(first_deposit["landform"], deposit_cell["landform"])
            self.assertEqual(first_deposit["basin_id"], deposit_cell["basin_id"])
            self.assertEqual(first_deposit["political_region_id"], deposit_cell["political_region_id"])
            self.assertEqual(first_deposit["culture_region_id"], deposit_cell["culture_region_id"])
            self.assertAlmostEqual(first_deposit["latitude_deg"], deposit_cell["lat_deg"], delta=0.001)
            self.assertAlmostEqual(first_deposit["longitude_deg"], deposit_cell["lon_deg"], delta=0.001)
            self.assertAlmostEqual(first_deposit["area_km2"], deposit_cell["area_km2"], delta=0.001)
            for key in (
                "reserve_potential_index",
                "accessibility_index",
                "extraction_hazard_index",
                "economic_viability_index",
                "renewability_index",
                "geologic_confidence_index",
            ):
                self.assertGreaterEqual(first_deposit[key], 0.0)
                self.assertLessEqual(first_deposit[key], 1.0)
            evidence = first_deposit["formation_evidence"]
            self.assertEqual(evidence["boundary_type"], deposit_cell["boundary_type"])
            self.assertIn("crust_age_ma", evidence)
            self.assertIn("sediment_thickness_m", evidence)
            self.assertIn("flow_accumulation", evidence)
            self.assertIn("fertility", evidence)
        if world["ore_genesis_systems"]:
            first_ore = world["ore_genesis_systems"][0]
            cells_by_id = {cell["id"]: cell for cell in world["cells"]}
            deposits_by_id = {deposit["id"]: deposit for deposit in world["resource_deposits"]}
            self.assertEqual(first_ore["id"], 0)
            self.assertIn(
                first_ore["system_type"],
                {
                    "subduction_arc_hydrothermal",
                    "ancient_craton_metallogenic",
                    "fluvial_placer_system",
                    "rift_geothermal_hydrothermal",
                    "mixed_metallogenic_province",
                },
            )
            self.assertEqual(first_ore["cell_count"], len(first_ore["cell_ids"]))
            self.assertGreater(first_ore["cell_count"], 0)
            self.assertIn(first_ore["representative_cell_id"], first_ore["cell_ids"])
            self.assertEqual(first_ore["resource_deposit_count"], len(first_ore["resource_deposit_ids"]))
            for deposit_id in first_ore["resource_deposit_ids"]:
                self.assertIn(deposit_id, deposits_by_id)
                self.assertIn(
                    deposits_by_id[deposit_id]["resource"],
                    {"volcanic_arc_metals", "craton_iron_gold", "placer_metals", "geothermal"},
                )
                self.assertIn(deposits_by_id[deposit_id]["cell_id"], first_ore["cell_ids"])
            for key in (
                "mean_ore_genesis_potential_index",
                "max_ore_genesis_potential_index",
                "mean_hydrothermal_alteration_index",
                "mean_metallogenic_fertility_index",
                "mean_ore_structural_control_index",
                "mean_placer_concentration_index",
                "mean_resource_viability_index",
                "ore_genesis_confidence_index",
            ):
                self.assertGreaterEqual(first_ore[key], 0.0)
                self.assertLessEqual(first_ore[key], 1.0)
            self.assertTrue(first_ore["dominant_resource"])
            self.assertTrue(first_ore["dominant_lithology"])
            self.assertTrue(first_ore["dominant_landform"])
            self.assertTrue(first_ore["dominant_tectonic_context"])
            self.assertEqual(first_ore["formation_step_count"], len(first_ore["formation_steps"]))
            self.assertGreater(first_ore["formation_step_count"], 0)
            first_ore_step = first_ore["formation_steps"][0]
            self.assertEqual(first_ore_step["step_index"], 0)
            self.assertTrue(first_ore_step["process"])
            self.assertEqual(first_ore_step["active_cell_count"], len(first_ore_step["active_cell_ids"]))
            self.assertTrue(set(first_ore_step["active_cell_ids"]).issubset(first_ore["cell_ids"]))
            for key in ("mean_ore_genesis_potential_index", "mean_process_intensity_index"):
                self.assertGreaterEqual(first_ore_step[key], 0.0)
                self.assertLessEqual(first_ore_step[key], 1.0)
            ore_cell = cells_by_id[first_ore["cell_ids"][0]]
            self.assertEqual(ore_cell["ore_genesis_system_id"], first_ore["id"])
        if world["sedimentary_resource_systems"]:
            first_system = world["sedimentary_resource_systems"][0]
            cells_by_id = {cell["id"]: cell for cell in world["cells"]}
            deposits_by_id = {deposit["id"]: deposit for deposit in world["resource_deposits"]}
            self.assertEqual(first_system["id"], 0)
            self.assertIn(
                first_system["system_type"],
                {
                    "petroleum_system",
                    "gas_system",
                    "coal_basin",
                    "evaporite_salt_system",
                    "mixed_sedimentary_resource",
                },
            )
            self.assertEqual(first_system["cell_count"], len(first_system["cell_ids"]))
            self.assertGreater(first_system["cell_count"], 0)
            self.assertEqual(
                {cells_by_id[cell_id]["basin_id"] for cell_id in first_system["cell_ids"]},
                {first_system["basin_id"]},
            )
            self.assertEqual(first_system["resource_deposit_count"], len(first_system["resource_deposit_ids"]))
            for deposit_id in first_system["resource_deposit_ids"]:
                self.assertIn(deposit_id, deposits_by_id)
                self.assertIn(deposits_by_id[deposit_id]["resource"], {"sedimentary_fuels", "evaporites"})
                self.assertEqual(deposits_by_id[deposit_id]["basin_id"], first_system["basin_id"])
            for key in (
                "source_rock_index",
                "reservoir_quality_index",
                "seal_quality_index",
                "structural_trap_index",
                "coal_potential_index",
                "petroleum_potential_index",
                "gas_potential_index",
                "evaporite_salt_potential_index",
                "system_confidence_index",
            ):
                self.assertGreaterEqual(first_system[key], 0.0)
                self.assertLessEqual(first_system[key], 1.0)
            self.assertTrue(first_system["dominant_lithology"])
            self.assertTrue(first_system["dominant_landform"])
        if world["petroleum_migration_systems"]:
            first_petroleum = world["petroleum_migration_systems"][0]
            cells_by_id = {cell["id"]: cell for cell in world["cells"]}
            sedimentary_systems_by_id = {system["id"]: system for system in world["sedimentary_resource_systems"]}
            self.assertEqual(first_petroleum["id"], 0)
            self.assertIn(first_petroleum["sedimentary_resource_system_id"], sedimentary_systems_by_id)
            source_system = sedimentary_systems_by_id[first_petroleum["sedimentary_resource_system_id"]]
            self.assertEqual(first_petroleum["basin_id"], source_system["basin_id"])
            self.assertIn(
                first_petroleum["system_type"],
                {
                    "oil_migration_fairway",
                    "gas_migration_fairway",
                    "mixed_hydrocarbon_fairway",
                    "immature_source_basin",
                    "breached_trap_complex",
                },
            )
            self.assertEqual(first_petroleum["cell_count"], len(first_petroleum["cell_ids"]))
            self.assertGreater(first_petroleum["cell_count"], 0)
            self.assertTrue(set(first_petroleum["source_cell_ids"]).issubset(first_petroleum["cell_ids"]))
            self.assertTrue(set(first_petroleum["migration_cell_ids"]).issubset(first_petroleum["cell_ids"]))
            self.assertTrue(set(first_petroleum["reservoir_cell_ids"]).issubset(first_petroleum["cell_ids"]))
            self.assertTrue(set(first_petroleum["seal_cell_ids"]).issubset(first_petroleum["cell_ids"]))
            self.assertTrue(set(first_petroleum["trap_cell_ids"]).issubset(first_petroleum["cell_ids"]))
            self.assertEqual(first_petroleum["path_step_count"], len(first_petroleum["migration_steps"]))
            self.assertGreater(first_petroleum["path_step_count"], 0)
            for key in (
                "mean_source_rock_index",
                "mean_maturation_index",
                "mean_migration_path_index",
                "mean_reservoir_quality_index",
                "mean_seal_quality_index",
                "mean_trap_integrity_index",
                "mean_accumulation_index",
                "petroleum_potential_index",
                "gas_potential_index",
                "migration_efficiency_index",
                "leakage_risk_index",
                "confidence_index",
            ):
                self.assertGreaterEqual(first_petroleum[key], 0.0)
                self.assertLessEqual(first_petroleum[key], 1.0)
            first_petroleum_step = first_petroleum["migration_steps"][0]
            self.assertEqual(first_petroleum_step["step_index"], 0)
            self.assertEqual(first_petroleum_step["path_cell_ids"][0], first_petroleum_step["source_cell_id"])
            self.assertEqual(first_petroleum_step["path_cell_ids"][-1], first_petroleum_step["target_trap_cell_id"])
            self.assertEqual(first_petroleum_step["path_length_cell_count"], len(first_petroleum_step["path_cell_ids"]))
            self.assertGreaterEqual(first_petroleum_step["migration_distance_km"], 0.0)
            for key in (
                "mean_path_migration_index",
                "mean_path_trap_integrity_index",
                "hydrocarbon_charge_index",
                "leakage_risk_index",
                "accumulation_probability_index",
            ):
                self.assertGreaterEqual(first_petroleum_step[key], 0.0)
                self.assertLessEqual(first_petroleum_step[key], 1.0)
            petroleum_cell = cells_by_id[first_petroleum["cell_ids"][0]]
            self.assertEqual(petroleum_cell["petroleum_system_id"], first_petroleum["id"])
        if world["commodity_occurrences"]:
            first_commodity = world["commodity_occurrences"][0]
            deposits_by_id = {deposit["id"]: deposit for deposit in world["resource_deposits"]}
            cells_by_id = {cell["id"]: cell for cell in world["cells"]}
            source_deposit = deposits_by_id[first_commodity["resource_deposit_id"]]
            source_cell = cells_by_id[first_commodity["cell_id"]]
            self.assertEqual(first_commodity["id"], 0)
            self.assertEqual(first_commodity["cell_id"], source_deposit["cell_id"])
            self.assertEqual(first_commodity["source_resource"], source_deposit["resource"])
            self.assertEqual(first_commodity["host_crust_type"], source_deposit["host_crust_type"])
            self.assertEqual(first_commodity["host_lithology"], source_deposit["host_lithology"])
            self.assertEqual(first_commodity["landform"], source_deposit["landform"])
            self.assertEqual(first_commodity["basin_id"], source_deposit["basin_id"])
            self.assertAlmostEqual(first_commodity["area_km2"], source_deposit["area_km2"], delta=0.001)
            self.assertTrue(first_commodity["commodity"])
            self.assertTrue(first_commodity["commodity_group"])
            for key in (
                "occurrence_potential_index",
                "market_value_index",
                "accessibility_index",
                "extraction_hazard_index",
                "geologic_confidence_index",
            ):
                self.assertGreaterEqual(first_commodity[key], 0.0)
                self.assertLessEqual(first_commodity[key], 1.0)
            commodity_evidence = first_commodity["formation_evidence"]
            self.assertEqual(commodity_evidence["boundary_type"], source_cell["boundary_type"])
            self.assertIn("crust_age_ma", commodity_evidence)
            self.assertIn("sediment_thickness_m", commodity_evidence)
            self.assertIn("flow_accumulation", commodity_evidence)
            self.assertIn("salinity_index", commodity_evidence)
        for key in (
            "agricultural_potential_index",
            "mining_potential_index",
            "agricultural_zone_id",
            "mining_zone_id",
        ):
            self.assertIn(key, first_cell)
        self.assertGreaterEqual(first_cell["agricultural_potential_index"], 0.0)
        self.assertLessEqual(first_cell["agricultural_potential_index"], 1.0)
        self.assertGreaterEqual(first_cell["mining_potential_index"], 0.0)
        self.assertLessEqual(first_cell["mining_potential_index"], 1.0)
        self.assertGreaterEqual(first_cell["agricultural_zone_id"], -1)
        self.assertGreaterEqual(first_cell["mining_zone_id"], -1)
        if first_cell["is_water"]:
            self.assertEqual(first_cell["agricultural_potential_index"], 0.0)
            self.assertEqual(first_cell["mining_potential_index"], 0.0)
            self.assertEqual(first_cell["agricultural_zone_id"], -1)
            self.assertEqual(first_cell["mining_zone_id"], -1)
        if world["agricultural_zones"]:
            first_agricultural_zone = world["agricultural_zones"][0]
            self.assertEqual(first_agricultural_zone["id"], 0)
            self.assertEqual(first_agricultural_zone["zone_type"], "agricultural")
            self.assertGreater(first_agricultural_zone["cell_count"], 0)
            self.assertEqual(first_agricultural_zone["cell_count"], len(first_agricultural_zone["cell_ids"]))
            self.assertGreaterEqual(first_agricultural_zone["area_km2"], 0.0)
            self.assertGreaterEqual(first_agricultural_zone["mean_potential_index"], 0.58)
            self.assertLessEqual(first_agricultural_zone["mean_potential_index"], 1.0)
            self.assertGreaterEqual(first_agricultural_zone["mean_fertility_index"], 0.0)
            self.assertLessEqual(first_agricultural_zone["mean_fertility_index"], 1.0)
            self.assertTrue(first_agricultural_zone["dominant_landform"])
            self.assertTrue(first_agricultural_zone["dominant_biome"])
            self.assertIn("settlement_ids", first_agricultural_zone)
            self.assertIn("route_ids", first_agricultural_zone)
            self.assertIn("resource_deposit_ids", first_agricultural_zone)
        if world["mining_zones"]:
            first_mining_zone = world["mining_zones"][0]
            self.assertEqual(first_mining_zone["id"], 0)
            self.assertEqual(first_mining_zone["zone_type"], "mining")
            self.assertGreater(first_mining_zone["cell_count"], 0)
            self.assertEqual(first_mining_zone["cell_count"], len(first_mining_zone["cell_ids"]))
            self.assertGreaterEqual(first_mining_zone["area_km2"], 0.0)
            self.assertGreaterEqual(first_mining_zone["mean_potential_index"], 0.52)
            self.assertLessEqual(first_mining_zone["mean_potential_index"], 1.0)
            self.assertGreaterEqual(first_mining_zone["mean_fertility_index"], 0.0)
            self.assertLessEqual(first_mining_zone["mean_fertility_index"], 1.0)
            self.assertTrue(first_mining_zone["dominant_resource"])
            self.assertTrue(first_mining_zone["dominant_landform"])
            self.assertIn("settlement_ids", first_mining_zone)
            self.assertIn("route_ids", first_mining_zone)
            self.assertIn("resource_deposit_ids", first_mining_zone)
        for key in (
            "natural_frontier_index",
            "natural_frontier_type",
            "natural_frontier_id",
        ):
            self.assertIn(key, first_cell)
        self.assertGreaterEqual(first_cell["natural_frontier_index"], 0.0)
        self.assertLessEqual(first_cell["natural_frontier_index"], 1.0)
        self.assertGreaterEqual(first_cell["natural_frontier_id"], -1)
        if first_cell["natural_frontier_id"] == -1:
            self.assertEqual(first_cell["natural_frontier_index"], 0.0)
            self.assertEqual(first_cell["natural_frontier_type"], "none")
        else:
            self.assertGreaterEqual(first_cell["natural_frontier_index"], 0.45)
            self.assertNotEqual(first_cell["natural_frontier_type"], "none")
        if world["natural_frontiers"]:
            first_frontier = world["natural_frontiers"][0]
            self.assertEqual(first_frontier["id"], 0)
            self.assertTrue(first_frontier["frontier_type"])
            self.assertNotEqual(first_frontier["frontier_type"], "none")
            self.assertGreater(first_frontier["cell_count"], 0)
            self.assertEqual(first_frontier["cell_count"], len(first_frontier["cell_ids"]))
            self.assertEqual(first_frontier["border_segment_count"], len(first_frontier["border_ids"]))
            self.assertGreater(first_frontier["border_segment_count"], 0)
            self.assertGreaterEqual(first_frontier["area_km2"], 0.0)
            self.assertGreaterEqual(first_frontier["total_border_length_km"], 0.0)
            self.assertGreaterEqual(first_frontier["mean_barrier_score"], 0.0)
            self.assertLessEqual(first_frontier["mean_barrier_score"], 1.0)
            self.assertGreaterEqual(first_frontier["mean_frontier_index"], 0.45)
            self.assertLessEqual(first_frontier["mean_frontier_index"], 1.0)
            self.assertTrue(first_frontier["dominant_landform"])
            self.assertTrue(first_frontier["dominant_biome"])
            self.assertIn("region_ids", first_frontier)
            self.assertIn("settlement_ids", first_frontier)
            self.assertIn("route_ids", first_frontier)
            self.assertEqual(first_frontier["route_crossing_count"], len(first_frontier["route_ids"]))
            self.assertIn("navigable_waterway_ids", first_frontier)
        self.assertIn("wind_east", first_cell)
        self.assertIn("wind_north", first_cell)
        self.assertIn("wind_monthly_east", first_cell)
        self.assertIn("wind_monthly_north", first_cell)
        self.assertIn("mean_seasonal_wind_speed", first_cell)
        self.assertIn("seasonal_wind_reversal_index", first_cell)
        self.assertIn("atmospheric_cell", first_cell)
        self.assertIn("surface_pressure_anomaly_hpa", first_cell)
        self.assertIn("vertical_velocity_index", first_cell)
        self.assertIn("wind_divergence_index", first_cell)
        self.assertEqual(len(first_cell["wind_monthly_east"]), 12)
        self.assertEqual(len(first_cell["wind_monthly_north"]), 12)
        for east, north in zip(first_cell["wind_monthly_east"], first_cell["wind_monthly_north"]):
            self.assertGreaterEqual(east, -1.0)
            self.assertLessEqual(east, 1.0)
            self.assertGreaterEqual(north, -1.0)
            self.assertLessEqual(north, 1.0)
        self.assertGreaterEqual(first_cell["mean_seasonal_wind_speed"], 0.0)
        self.assertLessEqual(first_cell["mean_seasonal_wind_speed"], 1.5)
        self.assertGreaterEqual(first_cell["seasonal_wind_reversal_index"], 0.0)
        self.assertLessEqual(first_cell["seasonal_wind_reversal_index"], 1.0)
        self.assertGreaterEqual(first_cell["surface_pressure_anomaly_hpa"], -22.0)
        self.assertLessEqual(first_cell["surface_pressure_anomaly_hpa"], 22.0)
        self.assertGreaterEqual(first_cell["vertical_velocity_index"], -1.0)
        self.assertLessEqual(first_cell["vertical_velocity_index"], 1.0)
        self.assertGreaterEqual(first_cell["wind_divergence_index"], -1.0)
        self.assertLessEqual(first_cell["wind_divergence_index"], 1.0)
        self.assertIn("ocean_current_east", first_cell)
        self.assertIn("ocean_current_north", first_cell)
        self.assertIn("ocean_current_temperature_c", first_cell)
        self.assertIn("ocean_current_moisture_factor", first_cell)
        for key in (
            "ocean_current_speed_index",
            "ocean_current_poleward_index",
            "ocean_heat_transport_index",
            "ocean_current_transport_alignment",
            "ocean_current_transport_target_cell_id",
            "ocean_current_transport_distance_km",
            "ocean_current_convergence_index",
            "ocean_upwelling_index",
            "ocean_current_regime",
            "ocean_current_system_id",
        ):
            self.assertIn(key, first_cell)
        self.assertGreaterEqual(first_cell["ocean_current_speed_index"], 0.0)
        self.assertGreaterEqual(first_cell["ocean_current_poleward_index"], -1.0)
        self.assertLessEqual(first_cell["ocean_current_poleward_index"], 1.0)
        self.assertGreaterEqual(first_cell["ocean_heat_transport_index"], -1.0)
        self.assertLessEqual(first_cell["ocean_heat_transport_index"], 1.0)
        self.assertGreaterEqual(first_cell["ocean_current_transport_alignment"], 0.0)
        self.assertLessEqual(first_cell["ocean_current_transport_alignment"], 1.0)
        self.assertGreaterEqual(first_cell["ocean_current_transport_target_cell_id"], -1)
        self.assertGreaterEqual(first_cell["ocean_current_transport_distance_km"], 0.0)
        self.assertGreaterEqual(first_cell["ocean_current_convergence_index"], -1.0)
        self.assertLessEqual(first_cell["ocean_current_convergence_index"], 1.0)
        self.assertGreaterEqual(first_cell["ocean_upwelling_index"], 0.0)
        self.assertLessEqual(first_cell["ocean_upwelling_index"], 1.0)
        self.assertIn(first_cell["ocean_current_regime"], summary["ocean_current_regime_counts"])
        if first_cell["water_body_type"] in {"ocean", "continental_shelf", "inland_sea"}:
            self.assertGreaterEqual(first_cell["ocean_current_system_id"], 0)
            if first_cell["ocean_current_transport_target_cell_id"] >= 0:
                self.assertIn(first_cell["ocean_current_transport_target_cell_id"], first_cell["neighbors"])
        else:
            self.assertEqual(first_cell["ocean_current_regime"], "non_marine")
            self.assertEqual(first_cell["ocean_current_system_id"], -1)
        self.assertIn("humidity_transport_index", first_cell)
        self.assertIn("upwind_ocean_fetch_km", first_cell)
        self.assertIn("advected_moisture_factor", first_cell)
        self.assertIn("distance_to_marine_water_km", first_cell)
        self.assertIn("continentality_index", first_cell)
        self.assertIn("oceanic_humidity_availability_index", first_cell)
        self.assertIn("marine_influence_class", first_cell)
        self.assertIn("climate_continentality_region_id", first_cell)
        self.assertGreaterEqual(first_cell["distance_to_marine_water_km"], 0.0)
        self.assertGreaterEqual(first_cell["continentality_index"], 0.0)
        self.assertLessEqual(first_cell["continentality_index"], 1.0)
        self.assertGreaterEqual(first_cell["oceanic_humidity_availability_index"], 0.0)
        self.assertLessEqual(first_cell["oceanic_humidity_availability_index"], 1.0)
        self.assertIn(first_cell["marine_influence_class"], {"marine", "coastal", "maritime_influenced", "interior", "continental_core"})
        self.assertIn("orographic_factor", first_cell)
        self.assertIn("rain_shadow_factor", first_cell)
        self.assertIn("vapor_evaporation_mm_y", first_cell)
        self.assertIn("moisture_convergence_mm_y", first_cell)
        self.assertIn("orographic_rainout_mm_y", first_cell)
        self.assertIn("precipitation_recycling_fraction", first_cell)
        self.assertIn("vapor_deficit_mm_y", first_cell)
        self.assertIn("vapor_budget_residual_mm_y", first_cell)
        self.assertIn("seasonal_precipitation_range_mm", first_cell)
        self.assertIn("seasonal_aridity_index", first_cell)
        self.assertIn("cell_monsoon_index", first_cell)
        self.assertIn("seasonal_humidity_regime", first_cell)
        self.assertGreaterEqual(first_cell["seasonal_precipitation_range_mm"], 0.0)
        self.assertGreaterEqual(first_cell["seasonal_aridity_index"], 0.0)
        self.assertLessEqual(first_cell["seasonal_aridity_index"], 1.0)
        self.assertGreaterEqual(first_cell["cell_monsoon_index"], 0.0)
        self.assertLessEqual(first_cell["cell_monsoon_index"], 1.0)
        for key in (
            "top_of_atmosphere_insolation_w_m2",
            "seasonal_insolation_range_w_m2",
            "orbital_insolation_variability_index",
            "peak_seasonal_insolation_w_m2",
            "low_seasonal_insolation_w_m2",
            "surface_albedo_index",
            "surface_albedo_regime",
            "absorbed_shortwave_w_m2",
            "outgoing_longwave_w_m2",
            "greenhouse_trapping_w_m2",
            "net_radiative_balance_w_m2",
            "no_greenhouse_equilibrium_temperature_c",
            "radiative_equilibrium_temperature_c",
            "energy_balance_residual_c",
            "climate_energy_stress_index",
        ):
            self.assertIn(key, first_cell)
        self.assertGreater(first_cell["top_of_atmosphere_insolation_w_m2"], 0.0)
        self.assertGreaterEqual(first_cell["seasonal_insolation_range_w_m2"], 0.0)
        self.assertGreaterEqual(first_cell["orbital_insolation_variability_index"], 0.0)
        self.assertLessEqual(first_cell["orbital_insolation_variability_index"], 1.0)
        self.assertGreaterEqual(first_cell["peak_seasonal_insolation_w_m2"], first_cell["low_seasonal_insolation_w_m2"])
        self.assertGreaterEqual(first_cell["low_seasonal_insolation_w_m2"], 0.0)
        self.assertGreaterEqual(first_cell["surface_albedo_index"], 0.0)
        self.assertLessEqual(first_cell["surface_albedo_index"], 1.0)
        self.assertGreaterEqual(first_cell["absorbed_shortwave_w_m2"], 0.0)
        self.assertGreater(first_cell["outgoing_longwave_w_m2"], 0.0)
        self.assertGreaterEqual(first_cell["greenhouse_trapping_w_m2"], 0.0)
        self.assertGreaterEqual(first_cell["climate_energy_stress_index"], 0.0)
        self.assertLessEqual(first_cell["climate_energy_stress_index"], 1.0)
        self.assertIn("ice_thickness_m", first_cell)
        self.assertIn("ice_sheet_id", first_cell)
        self.assertIn("glacier_flow_to", first_cell)
        self.assertIn("ice_surface_mass_balance_m_y", first_cell)
        self.assertIn("basal_sliding_index", first_cell)
        self.assertIn("ice_velocity_m_y", first_cell)
        self.assertGreaterEqual(first_cell["basal_sliding_index"], 0.0)
        self.assertLessEqual(first_cell["basal_sliding_index"], 1.0)
        self.assertGreaterEqual(first_cell["ice_velocity_m_y"], 0.0)
        self.assertIn("glacial_erosion_m", first_cell)
        self.assertIn("glacial_sediment_production_m", first_cell)
        self.assertIn("glacial_sediment_deposition_m", first_cell)
        self.assertIn("glacial_sediment_net_m", first_cell)
        self.assertIn("glacial_sediment_outgoing_transfer_count", first_cell)
        self.assertIn("glacial_sediment_incoming_transfer_count", first_cell)
        self.assertIn("moraine_deposition_m", first_cell)
        self.assertIn("deglaciation_age_ka", first_cell)
        self.assertIn("ice_flowline_flux_km3_y", first_cell)
        self.assertIn("ice_flowline_driving_stress_kpa", first_cell)
        self.assertIn("ice_flowline_strain_heating_index", first_cell)
        self.assertIn("ice_flowline_path_count", first_cell)
        self.assertIn("permafrost_extent_index", first_cell)
        self.assertIn("active_layer_depth_m", first_cell)
        self.assertIn("ground_ice_content_index", first_cell)
        self.assertIn("permafrost_class", first_cell)
        self.assertIn("permafrost_region_id", first_cell)
        self.assertIn("glacial_landform_index", first_cell)
        self.assertIn("glacial_erosion_intensity_index", first_cell)
        self.assertIn("glacial_deposition_index", first_cell)
        self.assertIn("glacial_meltwater_index", first_cell)
        self.assertIn("glacial_landform_type", first_cell)
        self.assertIn("glacial_landform_system_id", first_cell)
        self.assertGreaterEqual(first_cell["ice_flowline_flux_km3_y"], 0.0)
        self.assertGreaterEqual(first_cell["ice_flowline_driving_stress_kpa"], 0.0)
        self.assertGreaterEqual(first_cell["ice_flowline_strain_heating_index"], 0.0)
        self.assertLessEqual(first_cell["ice_flowline_strain_heating_index"], 1.0)
        self.assertGreaterEqual(first_cell["ice_flowline_path_count"], 0)
        self.assertGreaterEqual(first_cell["permafrost_extent_index"], 0.0)
        self.assertLessEqual(first_cell["permafrost_extent_index"], 1.0)
        self.assertGreaterEqual(first_cell["active_layer_depth_m"], 0.0)
        self.assertLessEqual(first_cell["active_layer_depth_m"], 4.5)
        self.assertGreaterEqual(first_cell["ground_ice_content_index"], 0.0)
        self.assertLessEqual(first_cell["ground_ice_content_index"], 1.0)
        self.assertTrue(first_cell["permafrost_class"])
        self.assertGreaterEqual(first_cell["permafrost_region_id"], -1)
        for key in (
            "glacial_landform_index",
            "glacial_erosion_intensity_index",
            "glacial_deposition_index",
            "glacial_meltwater_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertIn(
            first_cell["glacial_landform_type"],
            {"none", "ice_cap", "mountain_glacier", "fjord", "glacial_valley", "glacial_lake", "moraine"},
        )
        self.assertGreaterEqual(first_cell["glacial_landform_system_id"], -1)

        first_climate_history = world["climate_seasonal_histories"][0]
        self.assertIn("atmospheric_cell", first_climate_history)
        self.assertIn("annual_precipitation_mm", first_climate_history)
        self.assertIn("annual_evaporation_mm", first_climate_history)
        self.assertIn("annual_moisture_convergence_mm", first_climate_history)
        self.assertIn("annual_humidity_export_mm", first_climate_history)
        self.assertIn("annual_vapor_deficit_mm", first_climate_history)
        self.assertIn("max_humidity_storage_mm", first_climate_history)
        self.assertIn("monsoon_index", first_climate_history)
        self.assertEqual(first_climate_history["time_step_count"], 12)
        self.assertEqual(len(first_climate_history["steps"]), 12)
        self.assertGreater(first_climate_history["cell_count"], 0)
        self.assertGreaterEqual(first_climate_history["monsoon_index"], 0.0)
        self.assertLessEqual(first_climate_history["monsoon_index"], 1.0)
        previous_storage = None
        for index, step in enumerate(first_climate_history["steps"]):
            self.assertEqual(step["month"], index + 1)
            self.assertGreaterEqual(step["precipitation_mm"], 0.0)
            self.assertGreaterEqual(step["start_humidity_storage_mm"], 0.0)
            self.assertGreaterEqual(step["evaporation_mm"], 0.0)
            self.assertGreaterEqual(step["moisture_convergence_mm"], 0.0)
            self.assertGreaterEqual(step["vapor_deficit_mm"], 0.0)
            self.assertGreaterEqual(step["humidity_export_mm"], 0.0)
            self.assertGreaterEqual(step["end_humidity_storage_mm"], 0.0)
            self.assertIn("mean_wind_east", step)
            self.assertIn("mean_wind_north", step)
            self.assertGreaterEqual(step["mean_wind_east"], -1.0)
            self.assertLessEqual(step["mean_wind_east"], 1.0)
            self.assertGreaterEqual(step["mean_wind_north"], -1.0)
            self.assertLessEqual(step["mean_wind_north"], 1.0)
            self.assertGreaterEqual(step["drying_risk"], 0.0)
            self.assertLessEqual(step["drying_risk"], 1.0)
            self.assertAlmostEqual(
                step["start_humidity_storage_mm"]
                + step["evaporation_mm"]
                + step["moisture_convergence_mm"]
                + step["vapor_deficit_mm"]
                - step["precipitation_mm"]
                - step["humidity_export_mm"]
                - step["end_humidity_storage_mm"],
                step["humidity_budget_residual_mm"],
                delta=0.001,
            )
            self.assertLessEqual(abs(step["humidity_budget_residual_mm"]), 0.001)
            if previous_storage is not None:
                self.assertAlmostEqual(
                    step["start_humidity_storage_mm"],
                    previous_storage,
                    delta=max(0.001, previous_storage * 0.0001),
                )
            previous_storage = step["end_humidity_storage_mm"]

        first_energy_record = world["climate_energy_balance_records"][0]
        self.assertEqual(first_energy_record["id"], 0)
        self.assertEqual(first_energy_record["cell_id"], first_cell["id"])
        self.assertEqual(first_energy_record["biome"], first_cell["biome"])
        self.assertEqual(first_energy_record["water_body_type"], first_cell["water_body_type"])
        self.assertEqual(first_energy_record["surface_albedo_regime"], first_cell["surface_albedo_regime"])
        self.assertGreater(first_energy_record["stellar_luminosity_factor"], 0.0)
        self.assertGreaterEqual(first_energy_record["planetary_greenhouse_factor"], 0.0)
        self.assertGreaterEqual(first_energy_record["atmosphere_pressure_bar"], 0.0)
        self.assertAlmostEqual(first_energy_record["orbital_eccentricity"], small.planet.orbital_eccentricity, delta=0.001)
        self.assertGreater(first_energy_record["mean_orbital_distance_factor"], 0.0)
        monthly_insolation = first_energy_record["monthly_top_of_atmosphere_insolation_w_m2"]
        self.assertEqual(len(monthly_insolation), len(first_cell["temperature_monthly_c"]))
        self.assertTrue(all(value >= 0.0 for value in monthly_insolation))
        self.assertAlmostEqual(
            first_energy_record["top_of_atmosphere_insolation_w_m2"],
            sum(monthly_insolation) / len(monthly_insolation),
            delta=0.001,
        )
        self.assertAlmostEqual(first_energy_record["peak_seasonal_insolation_w_m2"], max(monthly_insolation), delta=0.001)
        self.assertAlmostEqual(first_energy_record["low_seasonal_insolation_w_m2"], min(monthly_insolation), delta=0.001)
        self.assertAlmostEqual(
            first_energy_record["seasonal_insolation_range_w_m2"],
            first_energy_record["peak_seasonal_insolation_w_m2"] - first_energy_record["low_seasonal_insolation_w_m2"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            first_energy_record["orbital_insolation_variability_index"],
            min(
                1.0,
                first_energy_record["seasonal_insolation_range_w_m2"]
                / max(1.0, first_energy_record["top_of_atmosphere_insolation_w_m2"]),
            ),
            delta=0.001,
        )
        for key in (
            "seasonal_insolation_range_w_m2",
            "orbital_insolation_variability_index",
            "peak_seasonal_insolation_w_m2",
            "low_seasonal_insolation_w_m2",
        ):
            self.assertAlmostEqual(first_energy_record[key], first_cell[key], delta=0.001)
        self.assertAlmostEqual(
            first_energy_record["absorbed_shortwave_w_m2"],
            first_energy_record["top_of_atmosphere_insolation_w_m2"] * (1.0 - first_energy_record["surface_albedo_index"]),
            delta=0.001,
        )
        self.assertAlmostEqual(
            first_energy_record["net_radiative_balance_w_m2"],
            first_energy_record["absorbed_shortwave_w_m2"]
            + first_energy_record["greenhouse_trapping_w_m2"]
            - first_energy_record["outgoing_longwave_w_m2"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            first_energy_record["energy_balance_residual_c"],
            first_energy_record["temperature_c"] - first_energy_record["radiative_equilibrium_temperature_c"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            first_energy_record["climate_energy_stress_index"],
            first_cell["climate_energy_stress_index"],
            delta=0.001,
        )

        first_settlement = world["settlements"][0]
        self.assertIn("cell_id", first_settlement)
        self.assertIn("region_id", first_settlement)
        self.assertIn("culture_region_id", first_settlement)
        self.assertIn("language_region_id", first_settlement)
        self.assertIn("type", first_settlement)
        self.assertIn("score", first_settlement)

        first_watershed = world["watersheds"][0]
        self.assertIn("basin_id", first_watershed)
        self.assertIn("outlet_cell_id", first_watershed)
        self.assertIn("outlet_type", first_watershed)
        self.assertIn("area_km2", first_watershed)
        self.assertIn("centroid_lat_deg", first_watershed)
        self.assertIn("centroid_lon_deg", first_watershed)
        self.assertIn("boundary_cell_ids", first_watershed)
        self.assertIn("boundary_ring", first_watershed)
        self.assertIn("lon_span_deg", first_watershed)
        self.assertIn("crosses_antimeridian", first_watershed)
        self.assertIn("boundary_perimeter_km", first_watershed)
        self.assertIn("dissolved_polygon_area_km2", first_watershed)
        self.assertIn("polygon_area_error_fraction", first_watershed)
        self.assertIn("compactness_index", first_watershed)
        self.assertIn("geometry_quality", first_watershed)
        self.assertIn("main_channel_cell_ids", first_watershed)
        self.assertIn("main_channel_source_cell_id", first_watershed)
        self.assertIn("main_channel_outlet_cell_id", first_watershed)
        self.assertIn("main_channel_length_km", first_watershed)
        self.assertIn("main_channel_drop_m", first_watershed)
        self.assertIn("main_channel_gradient", first_watershed)
        self.assertIn("main_channel_sinuosity_index", first_watershed)
        self.assertIn("total_river_length_km", first_watershed)
        self.assertIn("drainage_density_km_per_1000_km2", first_watershed)
        self.assertIn("hack_coefficient", first_watershed)
        self.assertIn("hack_expected_main_channel_length_km", first_watershed)
        self.assertIn("hack_residual_fraction", first_watershed)
        self.assertIn("cell_edge_boundary_segment_ids", first_watershed)
        self.assertIn("cell_edge_boundary_segment_count", first_watershed)
        self.assertIn("cell_edge_boundary_length_km", first_watershed)
        self.assertIn("mean_cell_edge_boundary_segment_quality", first_watershed)
        self.assertIn("neighbor_watershed_ids", first_watershed)
        self.assertGreaterEqual(first_watershed["main_channel_length_km"], 0.0)
        self.assertGreaterEqual(first_watershed["main_channel_drop_m"], 0.0)
        self.assertGreaterEqual(first_watershed["main_channel_gradient"], 0.0)
        self.assertGreaterEqual(first_watershed["main_channel_sinuosity_index"], 1.0)
        self.assertGreaterEqual(first_watershed["total_river_length_km"], 0.0)
        self.assertGreaterEqual(first_watershed["drainage_density_km_per_1000_km2"], 0.0)
        self.assertGreaterEqual(first_watershed["hack_coefficient"], 0.0)
        self.assertGreaterEqual(first_watershed["hack_expected_main_channel_length_km"], 0.0)
        self.assertGreaterEqual(first_watershed["hack_residual_fraction"], 0.0)
        self.assertEqual(first_watershed["cell_edge_boundary_segment_count"], len(first_watershed["cell_edge_boundary_segment_ids"]))
        self.assertGreaterEqual(first_watershed["cell_edge_boundary_length_km"], 0.0)
        self.assertGreaterEqual(first_watershed["mean_cell_edge_boundary_segment_quality"], 0.0)
        self.assertLessEqual(first_watershed["mean_cell_edge_boundary_segment_quality"], 1.0)
        if first_watershed["main_channel_cell_ids"]:
            self.assertEqual(
                first_watershed["main_channel_source_cell_id"],
                first_watershed["main_channel_cell_ids"][0],
            )
            self.assertEqual(
                first_watershed["main_channel_outlet_cell_id"],
                first_watershed["main_channel_cell_ids"][-1],
            )

        if world["watershed_boundary_segments"]:
            first_watershed_segment = world["watershed_boundary_segments"][0]
            self.assertEqual(first_watershed_segment["id"], 0)
            self.assertIn("source_edge_id", first_watershed_segment)
            self.assertIn("watershed_a_id", first_watershed_segment)
            self.assertIn("watershed_b_id", first_watershed_segment)
            self.assertIn("length_km", first_watershed_segment)
            self.assertIn("boundary_segment_quality", first_watershed_segment)
            self.assertGreater(first_watershed_segment["length_km"], 0.0)
            self.assertGreaterEqual(first_watershed_segment["boundary_segment_quality"], 0.0)
            self.assertLessEqual(first_watershed_segment["boundary_segment_quality"], 1.0)

        if world["river_network_evolution_events"]:
            first_event = world["river_network_evolution_events"][0]
            self.assertIn(first_event["type"], {"river_capture_candidate", "river_avulsion_candidate"})
            self.assertIn("source_cell_id", first_event)
            self.assertIn("target_cell_id", first_event)
            self.assertIn("source_basin_id", first_event)
            self.assertIn("target_basin_id", first_event)
            self.assertIn("risk", first_event)
            self.assertIn("flow_accumulation", first_event)
            self.assertIn("dominant_driver", first_event)
            self.assertEqual(first_event["id"], 0)
            self.assertGreaterEqual(first_event["risk"], 0.0)
            self.assertLessEqual(first_event["risk"], 1.0)
            first_reorganization = world["river_reorganization_histories"][0]
            self.assertEqual(first_reorganization["river_network_evolution_event_id"], first_event["id"])
            self.assertEqual(first_reorganization["event_type"], first_event["type"])
            self.assertEqual(first_reorganization["source_cell_id"], first_event["source_cell_id"])
            self.assertEqual(first_reorganization["target_cell_id"], first_event["target_cell_id"])
            self.assertEqual(first_reorganization["source_basin_id"], first_event["source_basin_id"])
            self.assertEqual(first_reorganization["target_basin_id"], first_event["target_basin_id"])
            self.assertEqual(first_reorganization["risk_index"], first_event["risk"])
            self.assertIn("source_flow_to_cell_id", first_reorganization)
            self.assertIn("projected_flow_to_cell_id", first_reorganization)
            self.assertGreaterEqual(first_reorganization["source_flow_accumulation"], 0.0)
            self.assertGreaterEqual(first_reorganization["target_flow_accumulation"], 0.0)
            self.assertGreaterEqual(first_reorganization["initial_divide_relief_m"], 0.0)
            self.assertGreaterEqual(first_reorganization["final_divide_relief_m"], 0.0)
            self.assertLessEqual(
                first_reorganization["final_divide_relief_m"],
                first_reorganization["initial_divide_relief_m"] + 0.001,
            )
            self.assertGreaterEqual(first_reorganization["initial_channel_gradient"], 0.0)
            self.assertLessEqual(first_reorganization["initial_channel_gradient"], 0.08)
            self.assertGreaterEqual(first_reorganization["final_channel_gradient"], 0.0)
            self.assertLessEqual(first_reorganization["final_channel_gradient"], 0.08)
            self.assertGreaterEqual(first_reorganization["total_divide_lowering_m"], 0.0)
            self.assertGreaterEqual(first_reorganization["total_sediment_reworked_m"], 0.0)
            self.assertGreaterEqual(first_reorganization["mean_channelization_index"], 0.0)
            self.assertLessEqual(first_reorganization["mean_channelization_index"], 1.0)
            self.assertGreaterEqual(first_reorganization["final_diversion_probability_index"], 0.0)
            self.assertLessEqual(first_reorganization["final_diversion_probability_index"], 1.0)
            self.assertGreaterEqual(first_reorganization["final_reorganization_confidence_index"], 0.0)
            self.assertLessEqual(first_reorganization["final_reorganization_confidence_index"], 1.0)
            self.assertIsInstance(first_reorganization["high_reorganization_pressure"], bool)
            self.assertEqual(first_reorganization["step_count"], len(first_reorganization["steps"]))
            previous_relief = first_reorganization["initial_divide_relief_m"]
            for index, step in enumerate(first_reorganization["steps"]):
                self.assertEqual(step["stage_index"], index + 1)
                self.assertGreaterEqual(step["elapsed_years"], 0)
                self.assertTrue(step["active_process"])
                self.assertGreaterEqual(step["divide_relief_m"], 0.0)
                self.assertLessEqual(step["divide_relief_m"], previous_relief + 0.001)
                self.assertGreaterEqual(step["divide_lowering_m"], 0.0)
                self.assertGreaterEqual(step["channel_gradient"], 0.0)
                self.assertLessEqual(step["channel_gradient"], 0.08)
                self.assertGreaterEqual(step["sediment_reworking_m"], 0.0)
                for key in (
                    "channelization_index",
                    "diversion_probability_index",
                    "capture_headward_erosion_index",
                    "avulsion_belt_width_index",
                    "basin_connectivity_change_index",
                    "reorganization_confidence_index",
                ):
                    self.assertGreaterEqual(step[key], 0.0)
                    self.assertLessEqual(step[key], 1.0)
                previous_relief = step["divide_relief_m"]

        if world["lake_basins"]:
            first_lake_basin = world["lake_basins"][0]
            self.assertIn("outlet_cell_id", first_lake_basin)
            self.assertIn("depression_component_id", first_lake_basin)
            self.assertIn("spill_to_cell_id", first_lake_basin)
            self.assertIn("depression_policy", first_lake_basin)
            self.assertIn("overflows", first_lake_basin)
            self.assertIn("depression_cell_count", first_lake_basin)
            self.assertIn("depression_area_km2", first_lake_basin)
            self.assertIn("geologic_area_fraction", first_lake_basin)
            self.assertIn("storage_capacity_km3", first_lake_basin)
            self.assertIn("annual_runoff_km3", first_lake_basin)
            self.assertIn("overflow_index", first_lake_basin)
            self.assertIn("overflow_stage_count", first_lake_basin)
            self.assertIn("overflow_path_length_km", first_lake_basin)
            self.assertIn("avulsion_risk", first_lake_basin)
            self.assertIn("overflow_path_cell_ids", first_lake_basin)
            self.assertEqual(
                first_lake_basin["overflow_stage_count"],
                max(0, len(first_lake_basin["overflow_path_cell_ids"]) - 1),
            )
            self.assertGreaterEqual(first_lake_basin["avulsion_risk"], 0.0)
            self.assertLessEqual(first_lake_basin["avulsion_risk"], 1.0)

        if world["coastal_features"]:
            first_coast = world["coastal_features"][0]
            self.assertIn("cell_id", first_coast)
            self.assertIn("type", first_coast)
            self.assertIn("sediment_supply_index", first_coast)
            self.assertIn("wave_energy_index", first_coast)
            self.assertIn("progradation_index", first_coast)
            self.assertIn("shoreline_trend", first_coast)
            self.assertIn("migration_rate_m_y", first_coast)
            self.assertIn("longshore_transport_index", first_coast)

        for key in [
            "reef_growth_index",
            "reef_sediment_stress_index",
            "reef_wave_exposure_index",
            "reef_island_support_index",
            "reef_bleaching_risk_index",
        ]:
            self.assertIn(key, first_cell)
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertIn("reef_type", first_cell)
        self.assertIn("reef_system_id", first_cell)
        self.assertIn(
            first_cell["reef_type"],
            {"none", "fringing_reef", "barrier_reef", "atoll_reef", "patch_reef", "cold_water_reef"},
        )
        if first_cell["reef_growth_index"] >= 0.46:
            self.assertGreaterEqual(first_cell["reef_system_id"], 0)
            self.assertNotEqual(first_cell["reef_type"], "none")
        else:
            self.assertEqual(first_cell["reef_system_id"], -1)
            self.assertEqual(first_cell["reef_type"], "none")

        if world["reef_systems"]:
            first_reef = world["reef_systems"][0]
            for key in [
                "id",
                "reef_type",
                "cell_count",
                "cell_ids",
                "area_km2",
                "centroid_lat_deg",
                "centroid_lon_deg",
                "mean_reef_growth_index",
                "mean_reef_sediment_stress_index",
                "mean_reef_wave_exposure_index",
                "mean_reef_island_support_index",
                "mean_reef_bleaching_risk_index",
                "mean_water_depth_m",
                "mean_temperature_c",
                "mean_fishery_productivity_index",
                "adjacent_landmass_ids",
                "marine_region_ids",
                "coastal_feature_ids",
                "settlement_ids",
                "port_site_ids",
                "fishery_resource_record_ids",
                "adjacent_volcanic_land_cell_count",
                "reef_type_counts",
            ]:
                self.assertIn(key, first_reef)
            self.assertEqual(first_reef["id"], 0)
            self.assertEqual(first_reef["cell_count"], len(first_reef["cell_ids"]))
            self.assertGreater(first_reef["area_km2"], 0.0)
            self.assertIn(
                first_reef["reef_type"],
                {"fringing_reef", "barrier_reef", "atoll_reef", "patch_reef", "cold_water_reef"},
            )
            self.assertEqual(sum(first_reef["reef_type_counts"].values()), first_reef["cell_count"])
            self.assertGreaterEqual(first_reef["mean_reef_growth_index"], 0.46)
            self.assertLessEqual(first_reef["mean_reef_growth_index"], 1.0)

        if world["sedimentary_basins"]:
            first_basin_history = world["sedimentary_basins"][0]
            self.assertIn("basin_id", first_basin_history)
            self.assertIn("type", first_basin_history)
            self.assertIn("mean_sediment_thickness_m", first_basin_history)
            self.assertIn("mean_subsidence_index", first_basin_history)
            self.assertIn("depositional_age_ma", first_basin_history)

        if world["sediment_transport_histories"]:
            first_sediment_history = world["sediment_transport_histories"][0]
            self.assertIn("sedimentary_basin_id", first_sediment_history)
            self.assertIn("basin_id", first_sediment_history)
            self.assertIn("time_step_count", first_sediment_history)
            self.assertIn("final_sediment_thickness_m", first_sediment_history)
            self.assertIn("total_sediment_input_m", first_sediment_history)
            self.assertIn("total_deposition_m", first_sediment_history)
            self.assertIn("total_export_m", first_sediment_history)
            self.assertIn("total_compaction_loss_m", first_sediment_history)
            self.assertIn("total_progradation_distance_km", first_sediment_history)
            self.assertIn("final_accommodation_fill_fraction", first_sediment_history)
            self.assertEqual(first_sediment_history["time_step_count"], len(first_sediment_history["steps"]))
            self.assertGreater(first_sediment_history["time_step_count"], 0)
            first_sediment_step = first_sediment_history["steps"][0]
            self.assertIn("facies", first_sediment_step)
            self.assertIn("sequence_phase", first_sediment_step)
            self.assertIn("sediment_input_m", first_sediment_step)
            self.assertIn("deposited_m", first_sediment_step)
            self.assertIn("exported_m", first_sediment_step)
            self.assertIn("compaction_loss_m", first_sediment_step)
            self.assertIn("end_sediment_thickness_m", first_sediment_step)
            self.assertIn("accommodation_fill_fraction", first_sediment_step)
            self.assertIn("progradation_distance_km", first_sediment_step)
            self.assertAlmostEqual(
                first_sediment_step["sediment_input_m"],
                first_sediment_step["deposited_m"] + first_sediment_step["exported_m"],
                delta=max(0.001, first_sediment_step["sediment_input_m"] * 0.0001),
            )
            self.assertAlmostEqual(
                first_sediment_step["start_sediment_thickness_m"]
                + first_sediment_step["deposited_m"]
                - first_sediment_step["compaction_loss_m"],
                first_sediment_step["end_sediment_thickness_m"],
                delta=max(0.001, first_sediment_step["end_sediment_thickness_m"] * 0.0001),
            )
            self.assertAlmostEqual(
                first_sediment_history["final_sediment_thickness_m"],
                first_sediment_history["steps"][-1]["end_sediment_thickness_m"],
                delta=max(0.001, first_sediment_history["final_sediment_thickness_m"] * 0.0001),
            )
            self.assertAlmostEqual(
                first_sediment_history["final_accommodation_fill_fraction"],
                first_sediment_history["steps"][-1]["accommodation_fill_fraction"],
                delta=0.001,
            )

        if world["sequence_stratigraphy_histories"]:
            first_sequence = world["sequence_stratigraphy_histories"][0]
            self.assertIn("stratigraphic_column_id", first_sequence)
            self.assertIn("basin_id", first_sequence)
            self.assertIn("time_step_count", first_sequence)
            self.assertIn("sequence_event_count", first_sequence)
            self.assertIn("dominant_systems_tract", first_sequence)
            self.assertIn("dominant_shoreline_trajectory", first_sequence)
            self.assertIn("systems_tract_counts", first_sequence)
            self.assertIn("shoreline_trajectory_counts", first_sequence)
            self.assertEqual(first_sequence["time_step_count"], len(first_sequence["steps"]))
            self.assertEqual(
                first_sequence["sequence_event_count"],
                sum(1 for step in first_sequence["steps"] if step["sequence_surface"] != "none"),
            )
            first_sequence_step = first_sequence["steps"][0]
            self.assertIn("systems_tract", first_sequence_step)
            self.assertIn("sequence_surface", first_sequence_step)
            self.assertIn("shoreline_trajectory", first_sequence_step)
            self.assertIn("accommodation_to_deposition_ratio", first_sequence_step)
            self.assertIn("sediment_supply_index", first_sequence_step)
            self.assertIn("relative_sea_level_index", first_sequence_step)
            self.assertIn("flooding_index", first_sequence_step)
            self.assertGreaterEqual(first_sequence_step["accommodation_to_deposition_ratio"], 0.0)
            self.assertGreaterEqual(first_sequence_step["sediment_supply_index"], 0.0)
            self.assertLessEqual(first_sequence_step["sediment_supply_index"], 1.0)
            self.assertGreaterEqual(first_sequence_step["relative_sea_level_index"], 0.0)
            self.assertLessEqual(first_sequence_step["relative_sea_level_index"], 1.0)
            self.assertGreaterEqual(first_sequence_step["flooding_index"], 0.0)
            self.assertLessEqual(first_sequence_step["flooding_index"], 1.0)

        if world["sediment_routing_histories"]:
            first_route = world["sediment_routing_histories"][0]
            self.assertIn("source_cell_id", first_route)
            self.assertIn("basin_id", first_route)
            self.assertIn("flow_path_cell_ids", first_route)
            self.assertIn("path_length_km", first_route)
            self.assertIn("total_local_supply_m", first_route)
            self.assertIn("total_deposition_m", first_route)
            self.assertIn("total_routed_export_m", first_route)
            self.assertIn("total_sink_loss_m", first_route)
            self.assertIn("final_sediment_load_m", first_route)
            self.assertEqual(first_route["time_step_count"], len(first_route["steps"]))
            self.assertEqual(len(first_route["flow_path_cell_ids"]), len(first_route["steps"]))
            self.assertGreaterEqual(first_route["path_length_km"], 0.0)
            previous_load = None
            for index, step in enumerate(first_route["steps"]):
                self.assertEqual(step["step"], index + 1)
                self.assertEqual(step["cell_id"], first_route["flow_path_cell_ids"][index])
                self.assertGreaterEqual(step["segment_length_km"], 0.0)
                self.assertGreaterEqual(step["start_load_m"], 0.0)
                self.assertGreaterEqual(step["local_supply_m"], 0.0)
                self.assertGreaterEqual(step["deposited_m"], 0.0)
                self.assertGreaterEqual(step["routed_export_m"], 0.0)
                self.assertGreaterEqual(step["sink_loss_m"], 0.0)
                self.assertGreaterEqual(step["end_load_m"], 0.0)
                self.assertGreaterEqual(step["transport_capacity_index"], 0.0)
                self.assertLessEqual(step["transport_capacity_index"], 1.0)
                self.assertGreaterEqual(step["delivery_ratio"], 0.0)
                self.assertLessEqual(step["delivery_ratio"], 1.0)
                self.assertAlmostEqual(
                    step["start_load_m"]
                    + step["local_supply_m"]
                    - step["deposited_m"]
                    - step["routed_export_m"]
                    - step["sink_loss_m"],
                    step["local_balance_m"],
                    delta=max(0.001, abs(step["local_balance_m"]) * 0.0001),
                )
                if previous_load is not None:
                    self.assertAlmostEqual(
                        step["start_load_m"],
                        previous_load,
                        delta=max(0.001, previous_load * 0.0001),
                    )
                previous_load = step["end_load_m"]

        if world["stratigraphic_columns"]:
            first_column = world["stratigraphic_columns"][0]
            self.assertIn("basin_id", first_column)
            self.assertIn("representative_cell_id", first_column)
            self.assertIn("dominant_facies", first_column)
            self.assertIn("sequence_phase", first_column)
            self.assertIn("sediment_flux_index", first_column)
            self.assertIn("preservation_potential", first_column)
            self.assertIn("dominant_systems_tract", first_column)
            self.assertIn("dominant_shoreline_trajectory", first_column)
            self.assertIn("sequence_boundary_count", first_column)
            self.assertIn("maximum_flooding_surface_count", first_column)
            self.assertIn("stratigraphic_sequence_event_count", first_column)
            self.assertIn("mean_accommodation_to_deposition_ratio", first_column)
            self.assertGreaterEqual(first_column["sequence_boundary_count"], 0)
            self.assertGreaterEqual(first_column["maximum_flooding_surface_count"], 0)
            self.assertGreaterEqual(first_column["stratigraphic_sequence_event_count"], 0)
            self.assertGreaterEqual(first_column["mean_accommodation_to_deposition_ratio"], 0.0)
            self.assertIn("layers", first_column)
            self.assertEqual(first_column["layer_count"], len(first_column["layers"]))
            self.assertGreater(first_column["layer_count"], 0)
            first_layer = first_column["layers"][0]
            self.assertIn("facies", first_layer)
            self.assertIn("thickness_m", first_layer)
            self.assertIn("age_top_ma", first_layer)
            self.assertIn("age_base_ma", first_layer)
            self.assertIn("reservoir_quality", first_layer)
            self.assertIn("seal_quality", first_layer)

        if world["permafrost_regions"]:
            first_permafrost = world["permafrost_regions"][0]
            self.assertEqual(first_permafrost["id"], 0)
            self.assertGreater(first_permafrost["cell_count"], 0)
            self.assertEqual(first_permafrost["cell_count"], len(first_permafrost["cell_ids"]))
            self.assertTrue(first_permafrost["dominant_permafrost_class"])
            self.assertTrue(first_permafrost["dominant_biome"])
            self.assertGreaterEqual(first_permafrost["area_km2"], 0.0)
            self.assertEqual(
                sum(first_permafrost["permafrost_class_counts"].values()),
                first_permafrost["cell_count"],
            )
            for key in (
                "mean_permafrost_extent_index",
                "mean_ground_ice_content_index",
            ):
                self.assertGreaterEqual(first_permafrost[key], 0.0)
                self.assertLessEqual(first_permafrost[key], 1.0)
            self.assertGreaterEqual(first_permafrost["mean_active_layer_depth_m"], 0.0)
            self.assertLessEqual(first_permafrost["mean_active_layer_depth_m"], 4.5)
            self.assertGreaterEqual(first_permafrost["mean_frost_months"], 0.0)
            self.assertLessEqual(first_permafrost["mean_frost_months"], 12.0)
            self.assertGreaterEqual(first_permafrost["ice_covered_cell_count"], 0)

        if world["glacial_landform_systems"]:
            first_glacial_system = world["glacial_landform_systems"][0]
            self.assertEqual(first_glacial_system["id"], 0)
            self.assertIn(
                first_glacial_system["glacial_landform_type"],
                {"ice_cap", "mountain_glacier", "fjord", "glacial_valley", "glacial_lake", "moraine"},
            )
            self.assertGreater(first_glacial_system["cell_count"], 0)
            self.assertEqual(first_glacial_system["cell_count"], len(first_glacial_system["cell_ids"]))
            self.assertGreaterEqual(first_glacial_system["area_km2"], 0.0)
            self.assertGreaterEqual(first_glacial_system["centroid_lat_deg"], -90.0)
            self.assertLessEqual(first_glacial_system["centroid_lat_deg"], 90.0)
            self.assertGreaterEqual(first_glacial_system["centroid_lon_deg"], -180.0)
            self.assertLessEqual(first_glacial_system["centroid_lon_deg"], 180.0)
            for key in (
                "mean_glacial_landform_index",
                "mean_glacial_erosion_intensity_index",
                "mean_glacial_deposition_index",
                "mean_glacial_meltwater_index",
                "mean_permafrost_extent_index",
            ):
                self.assertGreaterEqual(first_glacial_system[key], 0.0)
                self.assertLessEqual(first_glacial_system[key], 1.0)
            self.assertGreaterEqual(first_glacial_system["mean_ice_thickness_m"], 0.0)
            self.assertGreaterEqual(first_glacial_system["mean_glacial_erosion_m"], 0.0)
            self.assertGreaterEqual(first_glacial_system["mean_moraine_deposition_m"], 0.0)
            self.assertGreaterEqual(first_glacial_system["mean_deglaciation_age_ka"], 0.0)
            self.assertGreaterEqual(first_glacial_system["mean_runoff_mm_y"], 0.0)
            for key in (
                "ice_covered_cell_count",
                "river_cell_count",
                "lake_cell_count",
                "coastal_cell_count",
                "permafrost_cell_count",
                "tundra_cell_count",
            ):
                self.assertGreaterEqual(first_glacial_system[key], 0)
            self.assertIsInstance(first_glacial_system["linked_ice_sheet_ids"], list)
            self.assertIsInstance(first_glacial_system["linked_basin_ids"], list)
            self.assertTrue(first_glacial_system["dominant_biome"])
            self.assertTrue(first_glacial_system["dominant_landform"])

        if world["ice_sheets"]:
            first_ice_sheet = world["ice_sheets"][0]
            self.assertIn("retreat_stage", first_ice_sheet)
            self.assertIn("mean_ice_thickness_m", first_ice_sheet)
            self.assertIn("accumulation_area_fraction", first_ice_sheet)
            self.assertIn("mean_surface_mass_balance_m_y", first_ice_sheet)
            self.assertIn("mean_basal_sliding_index", first_ice_sheet)
            self.assertIn("mean_ice_velocity_m_y", first_ice_sheet)
            self.assertIn("retreat_rate_m_y", first_ice_sheet)
            self.assertGreaterEqual(first_ice_sheet["mean_basal_sliding_index"], 0.0)
            self.assertLessEqual(first_ice_sheet["mean_basal_sliding_index"], 1.0)
            self.assertGreaterEqual(first_ice_sheet["mean_ice_velocity_m_y"], 0.0)
            self.assertGreaterEqual(first_ice_sheet["retreat_rate_m_y"], 0.0)
            self.assertIn("mean_deglaciation_age_ka", first_ice_sheet)
            self.assertIn("mean_moraine_deposition_m", first_ice_sheet)
            self.assertIn("ice_sheet_stability_index", first_ice_sheet)
            self.assertIn("ice_sheet_stability_class", first_ice_sheet)
            self.assertIn("calving_susceptibility_index", first_ice_sheet)
            self.assertIn("grounding_line_instability_index", first_ice_sheet)
            self.assertIn("equilibrium_line_offset_m", first_ice_sheet)
            self.assertIn("retreat_threshold_event_count", first_ice_sheet)
            self.assertIn("first_retreat_threshold_step", first_ice_sheet)
            self.assertGreaterEqual(first_ice_sheet["ice_sheet_stability_index"], 0.0)
            self.assertLessEqual(first_ice_sheet["ice_sheet_stability_index"], 1.0)
            self.assertGreaterEqual(first_ice_sheet["calving_susceptibility_index"], 0.0)
            self.assertLessEqual(first_ice_sheet["calving_susceptibility_index"], 1.0)
            self.assertGreaterEqual(first_ice_sheet["grounding_line_instability_index"], 0.0)
            self.assertLessEqual(first_ice_sheet["grounding_line_instability_index"], 1.0)
            self.assertGreaterEqual(first_ice_sheet["retreat_threshold_event_count"], 0)

            first_ice_history = world["ice_sheet_histories"][0]
            self.assertIn("ice_sheet_id", first_ice_history)
            self.assertIn("time_step_count", first_ice_history)
            self.assertIn("final_volume_km3", first_ice_history)
            self.assertIn("total_surface_balance_km3", first_ice_history)
            self.assertIn("total_dynamic_loss_km3", first_ice_history)
            self.assertEqual(first_ice_history["ice_sheet_id"], first_ice_sheet["id"])
            self.assertEqual(first_ice_history["time_step_count"], len(first_ice_history["steps"]))
            self.assertGreater(first_ice_history["time_step_count"], 0)
            previous_end_volume = None
            previous_end_area = None
            for index, step in enumerate(first_ice_history["steps"]):
                self.assertEqual(step["step"], index + 1)
                self.assertGreaterEqual(step["start_volume_km3"], 0.0)
                self.assertGreaterEqual(step["end_volume_km3"], 0.0)
                self.assertGreaterEqual(step["dynamic_loss_km3"], 0.0)
                self.assertGreaterEqual(step["retreat_loss_km3"], 0.0)
                self.assertGreaterEqual(step["retreat_distance_km"], 0.0)
                self.assertGreaterEqual(step["start_area_km2"], 0.0)
                self.assertGreaterEqual(step["end_area_km2"], 0.0)
                self.assertGreaterEqual(step["basal_sliding_index"], 0.0)
                self.assertLessEqual(step["basal_sliding_index"], 1.0)
                self.assertGreaterEqual(step["accumulation_area_fraction"], 0.0)
                self.assertLessEqual(step["accumulation_area_fraction"], 1.0)
                self.assertAlmostEqual(
                    step["start_volume_km3"]
                    + step["surface_balance_km3"]
                    - step["dynamic_loss_km3"]
                    - step["retreat_loss_km3"]
                    + step["stabilization_adjustment_km3"],
                    step["end_volume_km3"],
                    delta=max(1.0, step["end_volume_km3"] * 0.0001),
                )
                if previous_end_volume is not None:
                    self.assertAlmostEqual(
                        step["start_volume_km3"],
                        previous_end_volume,
                        delta=max(1.0, previous_end_volume * 0.0001),
                    )
                if previous_end_area is not None:
                    self.assertAlmostEqual(
                        step["start_area_km2"],
                        previous_end_area,
                        delta=max(1.0, previous_end_area * 0.0001),
                    )
                previous_end_volume = step["end_volume_km3"]
                previous_end_area = step["end_area_km2"]
            self.assertAlmostEqual(
                first_ice_history["final_volume_km3"],
                first_ice_history["steps"][-1]["end_volume_km3"],
                delta=max(1.0, first_ice_history["final_volume_km3"] * 0.0001),
            )

            first_stability_history = world["ice_sheet_stability_histories"][0]
            self.assertEqual(first_stability_history["ice_sheet_id"], first_ice_sheet["id"])
            self.assertEqual(first_stability_history["time_step_count"], len(first_stability_history["steps"]))
            self.assertIn("stability_class", first_stability_history)
            self.assertIn("mean_stability_index", first_stability_history)
            self.assertIn("max_stability_index", first_stability_history)
            self.assertIn("calving_susceptibility_index", first_stability_history)
            self.assertIn("grounding_line_instability_index", first_stability_history)
            self.assertIn("marine_margin_fraction", first_stability_history)
            self.assertIn("years_to_retreat_threshold", first_stability_history)
            self.assertIn("total_projected_calving_loss_km3", first_stability_history)
            self.assertIn("total_projected_grounding_line_retreat_km", first_stability_history)
            self.assertEqual(
                first_stability_history["retreat_threshold_event_count"],
                sum(1 for step in first_stability_history["steps"] if step["retreat_threshold_crossed"]),
            )
            self.assertGreaterEqual(first_stability_history["mean_stability_index"], 0.0)
            self.assertLessEqual(first_stability_history["mean_stability_index"], 1.0)
            self.assertGreaterEqual(first_stability_history["max_stability_index"], 0.0)
            self.assertLessEqual(first_stability_history["max_stability_index"], 1.0)
            self.assertGreaterEqual(first_stability_history["marine_margin_fraction"], 0.0)
            self.assertLessEqual(first_stability_history["marine_margin_fraction"], 1.0)
            for index, step in enumerate(first_stability_history["steps"]):
                self.assertEqual(step["step"], index + 1)
                self.assertGreater(step["duration_years"], 0.0)
                self.assertGreaterEqual(step["balance_deficit_index"], 0.0)
                self.assertLessEqual(step["balance_deficit_index"], 1.0)
                self.assertGreaterEqual(step["retreat_pace_index"], 0.0)
                self.assertLessEqual(step["retreat_pace_index"], 1.0)
                self.assertGreaterEqual(step["calving_susceptibility_index"], 0.0)
                self.assertLessEqual(step["calving_susceptibility_index"], 1.0)
                self.assertGreaterEqual(step["grounding_line_instability_index"], 0.0)
                self.assertLessEqual(step["grounding_line_instability_index"], 1.0)
                self.assertGreaterEqual(step["retreat_threshold_index"], 0.0)
                self.assertLessEqual(step["retreat_threshold_index"], 1.0)
                self.assertEqual(step["retreat_threshold_crossed"], step["retreat_threshold_index"] >= 0.65)
                self.assertGreaterEqual(step["projected_calving_loss_km3"], 0.0)
                self.assertGreaterEqual(step["projected_grounding_line_retreat_km"], 0.0)

        if world["ice_flowline_histories"]:
            first_flowline = world["ice_flowline_histories"][0]
            self.assertIn("source_cell_id", first_flowline)
            self.assertIn("ice_sheet_id", first_flowline)
            self.assertIn("flowline_cell_ids", first_flowline)
            self.assertIn("time_step_count", first_flowline)
            self.assertIn("final_ice_flux_km3_y", first_flowline)
            self.assertEqual(first_flowline["time_step_count"], len(first_flowline["steps"]))
            self.assertEqual(len(first_flowline["flowline_cell_ids"]), len(first_flowline["steps"]))
            self.assertGreaterEqual(first_flowline["time_step_count"], 2)
            previous_end_flux = None
            for index, step in enumerate(first_flowline["steps"]):
                self.assertEqual(step["step"], index + 1)
                self.assertEqual(step["cell_id"], first_flowline["flowline_cell_ids"][index])
                if index < len(first_flowline["steps"]) - 1:
                    self.assertEqual(step["flow_to_cell_id"], first_flowline["flowline_cell_ids"][index + 1])
                self.assertGreaterEqual(step["segment_length_km"], 0.0)
                self.assertGreaterEqual(step["surface_slope"], 0.0)
                self.assertGreaterEqual(step["ice_thickness_m"], 0.0)
                self.assertGreaterEqual(step["start_flux_km3_y"], 0.0)
                self.assertGreaterEqual(step["accumulation_flux_km3_y"], 0.0)
                self.assertGreaterEqual(step["dynamic_flux_km3_y"], 0.0)
                self.assertGreaterEqual(step["dynamic_loss_km3_y"], 0.0)
                self.assertGreaterEqual(step["melt_loss_km3_y"], 0.0)
                self.assertGreaterEqual(step["end_flux_km3_y"], 0.0)
                self.assertGreaterEqual(step["driving_stress_kpa"], 0.0)
                self.assertGreaterEqual(step["basal_sliding_index"], 0.0)
                self.assertLessEqual(step["basal_sliding_index"], 1.0)
                self.assertGreaterEqual(step["ice_velocity_m_y"], 0.0)
                self.assertGreaterEqual(step["strain_heating_index"], 0.0)
                self.assertLessEqual(step["strain_heating_index"], 1.0)
                self.assertGreaterEqual(step["glacial_erosion_m"], 0.0)
                self.assertAlmostEqual(
                    step["start_flux_km3_y"]
                    + step["accumulation_flux_km3_y"]
                    - step["dynamic_loss_km3_y"]
                    - step["melt_loss_km3_y"]
                    - step["end_flux_km3_y"],
                    step["balance_residual_km3_y"],
                    delta=0.001,
                )
                self.assertAlmostEqual(step["balance_residual_km3_y"], 0.0, delta=0.001)
                if previous_end_flux is not None:
                    self.assertAlmostEqual(
                        step["start_flux_km3_y"],
                        previous_end_flux,
                        delta=max(0.001, previous_end_flux * 0.0001),
                    )
                previous_end_flux = step["end_flux_km3_y"]
            self.assertAlmostEqual(
                first_flowline["final_ice_flux_km3_y"],
                first_flowline["steps"][-1]["end_flux_km3_y"],
                delta=0.001,
            )

        first_region = world["political_regions"][0]
        self.assertIn("capital_settlement_id", first_region)
        self.assertIn("settlement_ids", first_region)
        self.assertIn("type", first_region)
        self.assertIn("area_km2", first_region)

        first_culture = world["cultures"][0]
        self.assertIn("language_region_id", first_culture)
        self.assertIn("homeland_region_id", first_culture)
        self.assertIn("type", first_culture)
        self.assertIn("agricultural_area_km2", first_culture)
        self.assertIn("mining_area_km2", first_culture)
        self.assertIn("migration_pressure", first_culture)
        self.assertIn("continuity_index", first_culture)
        self.assertIn("estimated_age_years", first_culture)

        first_language = world["language_regions"][0]
        self.assertIn("family", first_language)
        self.assertIn("culture_ids", first_language)
        self.assertIn("trade_contact_index", first_language)
        self.assertIn("parent_language_region_id", first_language)
        self.assertIn("lineage_depth", first_language)
        self.assertIn("divergence_age_years", first_language)
        self.assertIn("change_rate", first_language)
        self.assertIn("phoneme_inventory_size", first_language)
        self.assertIn("phonological_complexity", first_language)
        self.assertIn("sound_shift_index", first_language)
        self.assertIn("inherited_phonology_fraction", first_language)
        self.assertIn("phonological_history_id", first_language)
        self.assertIn("sound_change_rule_ids", first_language)
        self.assertIn("sound_change_rule_count", first_language)
        self.assertIn("final_phoneme_inventory_size", first_language)
        self.assertIn("phonological_drift_index", first_language)
        self.assertIn("lexical_correspondence_ids", first_language)
        self.assertIn("lexical_correspondence_count", first_language)
        self.assertIn("lexical_diffusion_history_id", first_language)
        self.assertIn("speaker_population_history_id", first_language)
        self.assertIn("syllable_template", first_language)
        self.assertIn("stress_system", first_language)
        self.assertIn("allowed_coda_count", first_language)
        self.assertIn("prosodic_complexity_index", first_language)
        self.assertIn("phonotactic_complexity_index", first_language)
        self.assertGreaterEqual(first_language["phoneme_inventory_size"], 16)
        self.assertLessEqual(first_language["phoneme_inventory_size"], 58)
        self.assertGreaterEqual(first_language["phonological_complexity"], 0.0)
        self.assertLessEqual(first_language["phonological_complexity"], 1.0)
        self.assertGreaterEqual(first_language["sound_shift_index"], 0.0)
        self.assertLessEqual(first_language["sound_shift_index"], 1.0)
        self.assertGreaterEqual(first_language["inherited_phonology_fraction"], 0.0)
        self.assertLessEqual(first_language["inherited_phonology_fraction"], 1.0)
        self.assertEqual(first_language["sound_change_rule_count"], len(first_language["sound_change_rule_ids"]))
        self.assertEqual(first_language["lexical_correspondence_count"], len(first_language["lexical_correspondence_ids"]))
        self.assertEqual(first_language["final_phoneme_inventory_size"], first_language["phoneme_inventory_size"])
        self.assertGreaterEqual(first_language["phonological_drift_index"], 0.0)
        self.assertLessEqual(first_language["phonological_drift_index"], 1.0)
        self.assertGreaterEqual(first_language["allowed_coda_count"], 1)
        self.assertTrue(first_language["syllable_template"])
        self.assertTrue(first_language["stress_system"])
        self.assertGreaterEqual(first_language["prosodic_complexity_index"], 0.0)
        self.assertLessEqual(first_language["prosodic_complexity_index"], 1.0)
        self.assertGreaterEqual(first_language["phonotactic_complexity_index"], 0.0)
        self.assertLessEqual(first_language["phonotactic_complexity_index"], 1.0)

        first_phonology_history = world["phonological_histories"][0]
        self.assertIn("language_region_id", first_phonology_history)
        self.assertIn("parent_language_region_id", first_phonology_history)
        self.assertIn("initial_phoneme_inventory_size", first_phonology_history)
        self.assertIn("final_phoneme_inventory_size", first_phonology_history)
        self.assertIn("sound_change_rule_ids", first_phonology_history)
        self.assertIn("sound_change_rule_count", first_phonology_history)
        self.assertIn("step_count", first_phonology_history)
        self.assertIn("cumulative_sound_shift_index", first_phonology_history)
        self.assertIn("phonological_drift_index", first_phonology_history)
        self.assertIn("syllable_template", first_phonology_history)
        self.assertIn("stress_system", first_phonology_history)
        self.assertIn("allowed_coda_count", first_phonology_history)
        self.assertIn("prosodic_complexity_index", first_phonology_history)
        self.assertIn("phonotactic_complexity_index", first_phonology_history)
        self.assertEqual(first_phonology_history["step_count"], len(first_phonology_history["steps"]))
        self.assertEqual(first_phonology_history["sound_change_rule_count"], len(first_phonology_history["sound_change_rule_ids"]))
        self.assertEqual(first_phonology_history["final_phoneme_inventory_size"], first_language["phoneme_inventory_size"])
        self.assertGreaterEqual(first_phonology_history["initial_phoneme_inventory_size"], 1)
        self.assertGreaterEqual(first_phonology_history["cumulative_sound_shift_index"], 0.0)
        self.assertLessEqual(first_phonology_history["cumulative_sound_shift_index"], 1.0)
        self.assertGreaterEqual(first_phonology_history["phonological_drift_index"], 0.0)
        self.assertLessEqual(first_phonology_history["phonological_drift_index"], 1.0)
        self.assertEqual(first_phonology_history["syllable_template"], first_language["syllable_template"])
        self.assertEqual(first_phonology_history["stress_system"], first_language["stress_system"])
        self.assertGreaterEqual(first_phonology_history["allowed_coda_count"], 1)
        self.assertGreaterEqual(first_phonology_history["prosodic_complexity_index"], 0.0)
        self.assertLessEqual(first_phonology_history["prosodic_complexity_index"], 1.0)
        self.assertGreaterEqual(first_phonology_history["phonotactic_complexity_index"], 0.0)
        self.assertLessEqual(first_phonology_history["phonotactic_complexity_index"], 1.0)
        for index, step in enumerate(first_phonology_history["steps"]):
            self.assertEqual(step["stage_index"], index + 1)
            self.assertIn("era_id", step)
            self.assertIn("rule_ids", step)
            self.assertEqual(step["rule_count"], len(step["rule_ids"]))
            self.assertGreaterEqual(step["start_year_bp"], step["end_year_bp"])
            self.assertGreaterEqual(step["inventory_size"], 1)
            self.assertEqual(step["syllable_template"], first_language["syllable_template"])
            self.assertEqual(step["stress_system"], first_language["stress_system"])
            self.assertGreaterEqual(step["cumulative_sound_shift_index"], 0.0)
            self.assertLessEqual(step["cumulative_sound_shift_index"], 1.0)
            self.assertGreaterEqual(step["inherited_phonology_fraction"], 0.0)
            self.assertLessEqual(step["inherited_phonology_fraction"], 1.0)
            self.assertGreaterEqual(step["contact_influence_index"], 0.0)
            self.assertLessEqual(step["contact_influence_index"], 1.0)
            self.assertGreaterEqual(step["phonotactic_complexity_index"], 0.0)
            self.assertLessEqual(step["phonotactic_complexity_index"], 1.0)
            self.assertGreaterEqual(step["prosodic_weight_index"], 0.0)
            self.assertLessEqual(step["prosodic_weight_index"], 1.0)
        self.assertEqual(
            first_phonology_history["steps"][-1]["inventory_size"],
            first_phonology_history["final_phoneme_inventory_size"],
        )

        first_rule = world["phonological_rules"][0]
        self.assertIn("language_region_id", first_rule)
        self.assertIn("parent_language_region_id", first_rule)
        self.assertIn("era_id", first_rule)
        self.assertIn("stage_index", first_rule)
        self.assertIn("rule_type", first_rule)
        self.assertIn("source_segment", first_rule)
        self.assertIn("target_segment", first_rule)
        self.assertIn("source_features", first_rule)
        self.assertIn("target_features", first_rule)
        self.assertIn("articulatory_shift", first_rule)
        self.assertIn("environment", first_rule)
        self.assertIn("conditioned_by", first_rule)
        self.assertIn("prosodic_domain", first_rule)
        self.assertIn("probability_index", first_rule)
        self.assertIn("regularity_index", first_rule)
        self.assertIn("lexical_replacement_index", first_rule)
        self.assertIn("contact_influence_index", first_rule)
        self.assertIn("inventory_delta", first_rule)
        self.assertGreater(first_rule["stage_index"], 0)
        self.assertIsInstance(first_rule["source_features"], dict)
        self.assertIsInstance(first_rule["target_features"], dict)
        self.assertTrue(first_rule["articulatory_shift"])
        self.assertTrue(first_rule["prosodic_domain"])
        self.assertNotEqual(first_rule["source_segment"], first_rule["target_segment"])
        self.assertGreaterEqual(first_rule["start_year_bp"], first_rule["end_year_bp"])
        self.assertGreaterEqual(first_rule["probability_index"], 0.0)
        self.assertLessEqual(first_rule["probability_index"], 1.0)
        self.assertGreaterEqual(first_rule["regularity_index"], 0.0)
        self.assertLessEqual(first_rule["regularity_index"], 1.0)
        self.assertGreaterEqual(first_rule["lexical_replacement_index"], 0.0)
        self.assertLessEqual(first_rule["lexical_replacement_index"], 1.0)
        self.assertGreaterEqual(first_rule["contact_influence_index"], 0.0)
        self.assertLessEqual(first_rule["contact_influence_index"], 1.0)

        first_correspondence = world["lexical_correspondences"][0]
        self.assertIn("language_region_id", first_correspondence)
        self.assertIn("parent_language_region_id", first_correspondence)
        self.assertIn("meaning", first_correspondence)
        self.assertIn("semantic_domain", first_correspondence)
        self.assertIn("proto_form", first_correspondence)
        self.assertIn("inherited_form", first_correspondence)
        self.assertIn("derived_form", first_correspondence)
        self.assertIn("applied_rule_ids", first_correspondence)
        self.assertIn("applied_rule_count", first_correspondence)
        self.assertIn("replacement_count", first_correspondence)
        self.assertIn("regular_correspondence_fraction", first_correspondence)
        self.assertIn("lexical_replacement_index", first_correspondence)
        self.assertIn("stress_pattern", first_correspondence)
        self.assertIn("syllable_count", first_correspondence)
        self.assertIn("syllable_pattern", first_correspondence)
        self.assertIn("mora_count", first_correspondence)
        self.assertIn("prosodic_weight_index", first_correspondence)
        self.assertIn("diffusion_stage_index", first_correspondence)
        self.assertIn("diffusion_adoption_index", first_correspondence)
        self.assertIn("semantic_shift_index", first_correspondence)
        self.assertIn("borrowed", first_correspondence)
        self.assertEqual(first_correspondence["language_region_id"], first_language["id"])
        self.assertEqual(first_correspondence["applied_rule_count"], len(first_correspondence["applied_rule_ids"]))
        self.assertGreaterEqual(first_correspondence["replacement_count"], 0)
        self.assertGreater(first_correspondence["syllable_count"], 0)
        self.assertGreater(first_correspondence["mora_count"], 0)
        self.assertTrue(first_correspondence["meaning"])
        self.assertTrue(first_correspondence["derived_form"])
        self.assertTrue(first_correspondence["syllable_pattern"])
        self.assertGreaterEqual(first_correspondence["regular_correspondence_fraction"], 0.0)
        self.assertLessEqual(first_correspondence["regular_correspondence_fraction"], 1.0)
        self.assertGreaterEqual(first_correspondence["lexical_replacement_index"], 0.0)
        self.assertLessEqual(first_correspondence["lexical_replacement_index"], 1.0)
        self.assertAlmostEqual(
            first_correspondence["regular_correspondence_fraction"] + first_correspondence["lexical_replacement_index"],
            1.0,
            delta=0.001,
        )
        self.assertGreaterEqual(first_correspondence["prosodic_weight_index"], 0.0)
        self.assertLessEqual(first_correspondence["prosodic_weight_index"], 1.0)
        self.assertGreater(first_correspondence["diffusion_stage_index"], 0)
        self.assertGreaterEqual(first_correspondence["diffusion_adoption_index"], 0.0)
        self.assertLessEqual(first_correspondence["diffusion_adoption_index"], 1.0)
        self.assertGreaterEqual(first_correspondence["semantic_shift_index"], 0.0)
        self.assertLessEqual(first_correspondence["semantic_shift_index"], 1.0)
        self.assertIsInstance(first_correspondence["borrowed"], bool)

        first_diffusion = world["lexical_diffusion_histories"][0]
        self.assertIn("language_region_id", first_diffusion)
        self.assertIn("parent_language_region_id", first_diffusion)
        self.assertIn("phonological_history_id", first_diffusion)
        self.assertIn("lexical_correspondence_ids", first_diffusion)
        self.assertIn("lexical_correspondence_count", first_diffusion)
        self.assertIn("step_count", first_diffusion)
        self.assertIn("syllable_template", first_diffusion)
        self.assertIn("stress_system", first_diffusion)
        self.assertIn("mean_diffusion_adoption_index", first_diffusion)
        self.assertIn("mean_lexical_innovation_index", first_diffusion)
        self.assertIn("mean_semantic_shift_index", first_diffusion)
        self.assertIn("contact_borrowing_index", first_diffusion)
        self.assertIn("steps", first_diffusion)
        self.assertEqual(first_language["lexical_diffusion_history_id"], first_diffusion["id"])
        self.assertEqual(first_diffusion["language_region_id"], first_language["id"])
        self.assertEqual(first_diffusion["phonological_history_id"], first_language["phonological_history_id"])
        self.assertEqual(first_diffusion["lexical_correspondence_count"], len(first_diffusion["lexical_correspondence_ids"]))
        self.assertEqual(first_diffusion["step_count"], len(first_diffusion["steps"]))
        self.assertEqual(set(first_diffusion["lexical_correspondence_ids"]), set(first_language["lexical_correspondence_ids"]))
        self.assertEqual(first_diffusion["syllable_template"], first_language["syllable_template"])
        self.assertEqual(first_diffusion["stress_system"], first_language["stress_system"])
        self.assertGreaterEqual(first_diffusion["mean_diffusion_adoption_index"], 0.0)
        self.assertLessEqual(first_diffusion["mean_diffusion_adoption_index"], 1.0)
        self.assertGreaterEqual(first_diffusion["mean_lexical_innovation_index"], 0.0)
        self.assertLessEqual(first_diffusion["mean_lexical_innovation_index"], 1.0)
        self.assertGreaterEqual(first_diffusion["mean_semantic_shift_index"], 0.0)
        self.assertLessEqual(first_diffusion["mean_semantic_shift_index"], 1.0)
        self.assertGreaterEqual(first_diffusion["contact_borrowing_index"], 0.0)
        self.assertLessEqual(first_diffusion["contact_borrowing_index"], 1.0)
        for index, step in enumerate(first_diffusion["steps"]):
            self.assertEqual(step["stage_index"], index + 1)
            self.assertIn("era_id", step)
            self.assertIn("affected_correspondence_ids", step)
            self.assertIn("affected_meanings", step)
            self.assertEqual(step["affected_correspondence_count"], len(step["affected_correspondence_ids"]))
            self.assertEqual(len(step["affected_meanings"]), len(step["affected_correspondence_ids"]))
            self.assertGreaterEqual(step["start_year_bp"], step["end_year_bp"])
            self.assertGreaterEqual(step["affected_domain_count"], 0)
            self.assertGreaterEqual(step["adoption_fraction"], 0.0)
            self.assertLessEqual(step["adoption_fraction"], 1.0)
            self.assertGreaterEqual(step["innovation_fraction"], 0.0)
            self.assertLessEqual(step["innovation_fraction"], 1.0)
            self.assertGreaterEqual(step["contact_borrowing_index"], 0.0)
            self.assertLessEqual(step["contact_borrowing_index"], 1.0)
            self.assertGreaterEqual(step["regularization_index"], 0.0)
            self.assertLessEqual(step["regularization_index"], 1.0)
            self.assertGreaterEqual(step["semantic_shift_index"], 0.0)
            self.assertLessEqual(step["semantic_shift_index"], 1.0)

        first_speaker_history = world["speaker_population_histories"][0]
        self.assertIn("language_region_id", first_speaker_history)
        self.assertIn("parent_language_region_id", first_speaker_history)
        self.assertIn("population_region_id", first_speaker_history)
        self.assertIn("population_region_ids", first_speaker_history)
        self.assertIn("population_region_count", first_speaker_history)
        self.assertIn("phonological_history_id", first_speaker_history)
        self.assertIn("lexical_diffusion_history_id", first_speaker_history)
        self.assertIn("initial_speaker_population", first_speaker_history)
        self.assertIn("final_speaker_population", first_speaker_history)
        self.assertIn("estimated_speaker_population", first_speaker_history)
        self.assertIn("mean_allophonic_variation_index", first_speaker_history)
        self.assertIn("mean_syllable_pressure_index", first_speaker_history)
        self.assertIn("mean_speaker_contact_index", first_speaker_history)
        self.assertIn("mean_population_adoption_index", first_speaker_history)
        self.assertIn("mean_phonetic_reduction_index", first_speaker_history)
        self.assertIn("mean_lexical_diffusion_pressure_index", first_speaker_history)
        self.assertIn("high_contact_speaker_history", first_speaker_history)
        self.assertIn("steps", first_speaker_history)
        self.assertEqual(first_language["speaker_population_history_id"], first_speaker_history["id"])
        self.assertEqual(first_speaker_history["language_region_id"], first_language["id"])
        self.assertEqual(first_speaker_history["phonological_history_id"], first_language["phonological_history_id"])
        self.assertEqual(first_speaker_history["lexical_diffusion_history_id"], first_language["lexical_diffusion_history_id"])
        self.assertEqual(first_speaker_history["population_region_count"], len(first_speaker_history["population_region_ids"]))
        if first_speaker_history["population_region_ids"]:
            self.assertIn(first_speaker_history["population_region_id"], first_speaker_history["population_region_ids"])
        self.assertEqual(first_speaker_history["step_count"], len(first_speaker_history["steps"]))
        self.assertGreaterEqual(first_speaker_history["initial_speaker_population"], 0.0)
        self.assertGreaterEqual(first_speaker_history["final_speaker_population"], 0.0)
        self.assertGreaterEqual(first_speaker_history["estimated_speaker_population"], 0.0)
        self.assertAlmostEqual(
            first_speaker_history["final_speaker_population"],
            first_speaker_history["estimated_speaker_population"],
            delta=0.001,
        )
        self.assertGreaterEqual(first_speaker_history["mean_allophonic_variation_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_allophonic_variation_index"], 1.0)
        self.assertGreaterEqual(first_speaker_history["mean_syllable_pressure_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_syllable_pressure_index"], 1.0)
        self.assertGreaterEqual(first_speaker_history["mean_speaker_contact_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_speaker_contact_index"], 1.0)
        self.assertGreaterEqual(first_speaker_history["mean_population_adoption_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_population_adoption_index"], 1.0)
        self.assertGreaterEqual(first_speaker_history["mean_phonetic_reduction_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_phonetic_reduction_index"], 1.0)
        self.assertGreaterEqual(first_speaker_history["mean_lexical_diffusion_pressure_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_lexical_diffusion_pressure_index"], 1.0)
        self.assertIsInstance(first_speaker_history["high_contact_speaker_history"], bool)
        for index, step in enumerate(first_speaker_history["steps"]):
            self.assertEqual(step["stage_index"], index + 1)
            self.assertIn("era_id", step)
            self.assertGreaterEqual(step["start_year_bp"], step["end_year_bp"])
            self.assertGreaterEqual(step["speaker_population"], 0.0)
            self.assertGreaterEqual(step["speaker_fraction_index"], 0.0)
            self.assertLessEqual(step["speaker_fraction_index"], 1.0)
            self.assertGreaterEqual(step["allophonic_variation_index"], 0.0)
            self.assertLessEqual(step["allophonic_variation_index"], 1.0)
            self.assertGreaterEqual(step["syllable_pressure_index"], 0.0)
            self.assertLessEqual(step["syllable_pressure_index"], 1.0)
            self.assertGreaterEqual(step["phonetic_reduction_index"], 0.0)
            self.assertLessEqual(step["phonetic_reduction_index"], 1.0)
            self.assertGreaterEqual(step["contact_pressure_index"], 0.0)
            self.assertLessEqual(step["contact_pressure_index"], 1.0)
            self.assertGreaterEqual(step["lexical_diffusion_pressure_index"], 0.0)
            self.assertLessEqual(step["lexical_diffusion_pressure_index"], 1.0)
            self.assertGreaterEqual(step["population_adoption_index"], 0.0)
            self.assertLessEqual(step["population_adoption_index"], 1.0)
            self.assertGreaterEqual(step["register_divergence_index"], 0.0)
            self.assertLessEqual(step["register_divergence_index"], 1.0)
            self.assertGreaterEqual(step["pronunciation_regularization_index"], 0.0)
            self.assertLessEqual(step["pronunciation_regularization_index"], 1.0)
        self.assertAlmostEqual(
            first_speaker_history["steps"][-1]["speaker_population"],
            first_speaker_history["final_speaker_population"],
            delta=max(0.001, first_speaker_history["final_speaker_population"] * 0.000001),
        )

        first_era = world["historical_eras"][0]
        self.assertIn("dominant_process", first_era)
        self.assertIn("start_year_bp", first_era)
        self.assertIn("end_year_bp", first_era)
        self.assertIn("event_count", first_era)
        self.assertIn("mean_instability", first_era)

        first_event = world["historical_events"][0]
        self.assertIn("era_id", first_event)
        self.assertIn("type", first_event)
        self.assertIn("year_bp", first_event)
        self.assertIn("region_id", first_event)
        self.assertIn("culture_region_id", first_event)
        self.assertIn("language_region_id", first_event)
        self.assertIn("pressure_index", first_event)
        self.assertIn("continuity_index", first_event)

        first_population = world["population_regions"][0]
        self.assertIn("region_id", first_population)
        self.assertIn("estimated_population", first_population)
        self.assertIn("carrying_capacity", first_population)
        self.assertIn("water_security_index", first_population)
        self.assertIn("growth_rate_per_year", first_population)
        self.assertIn("population_pressure", first_population)
        self.assertIn("household_cohort_ids", first_population)
        self.assertIn("household_cohort_count", first_population)
        self.assertIn("representative_household_population", first_population)
        self.assertIn("demographic_agent_history_id", first_population)
        self.assertIn("individual_agent_ids", first_population)
        self.assertIn("individual_agent_count", first_population)
        self.assertEqual(first_population["household_cohort_count"], len(first_population["household_cohort_ids"]))
        self.assertEqual(first_population["individual_agent_count"], len(first_population["individual_agent_ids"]))
        self.assertGreaterEqual(first_population["representative_household_population"], 0.0)

        first_population_history = world["population_histories"][0]
        self.assertIn("population_region_id", first_population_history)
        self.assertIn("region_id", first_population_history)
        self.assertIn("time_step_count", first_population_history)
        self.assertIn("final_population", first_population_history)
        self.assertIn("peak_pressure_index", first_population_history)
        self.assertEqual(first_population_history["time_step_count"], len(world["historical_eras"]))
        self.assertEqual(len(first_population_history["steps"]), len(world["historical_eras"]))
        previous_end = None
        for index, step in enumerate(first_population_history["steps"]):
            self.assertEqual(step["era_id"], world["historical_eras"][index]["id"])
            self.assertIn("start_population", step)
            self.assertIn("end_population", step)
            self.assertIn("population_change", step)
            self.assertIn("migration_delta", step)
            self.assertIn("conflict_loss", step)
            self.assertIn("carrying_capacity_used_fraction", step)
            self.assertGreaterEqual(step["start_population"], 0.0)
            self.assertGreaterEqual(step["end_population"], 0.0)
            self.assertAlmostEqual(
                step["population_change"],
                step["end_population"] - step["start_population"],
                delta=max(1.0, step["end_population"] * 0.0001),
            )
            if previous_end is not None:
                self.assertAlmostEqual(step["start_population"], previous_end, delta=max(1.0, previous_end * 0.0001))
            previous_end = step["end_population"]
        self.assertAlmostEqual(
            first_population_history["final_population"],
            first_population_history["steps"][-1]["end_population"],
            delta=max(1.0, first_population_history["final_population"] * 0.0001),
        )

        first_household = world["household_cohorts"][0]
        self.assertIn("population_region_id", first_household)
        self.assertIn("region_id", first_household)
        self.assertIn("cohort_type", first_household)
        self.assertIn("population", first_household)
        self.assertIn("household_count", first_household)
        self.assertIn("average_household_size", first_household)
        self.assertIn("income_index", first_household)
        self.assertIn("consumption_pressure_index", first_household)
        self.assertIn("vulnerability_index", first_household)
        self.assertIn("migration_propensity_index", first_household)
        self.assertIn("fertility_rate_per_year", first_household)
        self.assertIn("mortality_risk_index", first_household)
        self.assertIn("labor_participation_index", first_household)
        self.assertGreaterEqual(first_household["population"], 0.0)
        self.assertGreaterEqual(first_household["household_count"], 0.0)
        self.assertGreater(first_household["average_household_size"], 0.0)
        self.assertAlmostEqual(
            first_household["household_count"] * first_household["average_household_size"],
            first_household["population"],
            delta=max(1.0, first_household["population"] * 0.0001),
        )
        for key in (
            "income_index",
            "consumption_pressure_index",
            "vulnerability_index",
            "migration_propensity_index",
            "mortality_risk_index",
            "labor_participation_index",
        ):
            self.assertGreaterEqual(first_household[key], 0.0)
            self.assertLessEqual(first_household[key], 1.0)
        self.assertGreaterEqual(first_household["fertility_rate_per_year"], 0.0)

        first_economy_history = world["economy_histories"][0]
        self.assertIn("region_id", first_economy_history)
        self.assertIn("dominant_resource", first_economy_history)
        self.assertIn("time_step_count", first_economy_history)
        self.assertIn("final_gross_output_index", first_economy_history)
        self.assertIn("final_treasury_index", first_economy_history)
        self.assertIn("max_army_capacity_population", first_economy_history)
        self.assertEqual(first_economy_history["time_step_count"], len(world["historical_eras"]))
        self.assertEqual(len(first_economy_history["steps"]), len(world["historical_eras"]))
        previous_treasury = None
        for index, step in enumerate(first_economy_history["steps"]):
            self.assertEqual(step["era_id"], world["historical_eras"][index]["id"])
            self.assertGreaterEqual(step["population"], 0.0)
            self.assertGreaterEqual(step["gross_output_index"], 0.0)
            self.assertGreaterEqual(step["agricultural_output_index"], 0.0)
            self.assertGreaterEqual(step["resource_output_index"], 0.0)
            self.assertGreaterEqual(step["trade_output_index"], 0.0)
            self.assertGreaterEqual(step["urban_services_index"], 0.0)
            self.assertGreaterEqual(step["tax_revenue_index"], 0.0)
            self.assertGreaterEqual(step["trade_revenue_index"], 0.0)
            self.assertGreaterEqual(step["administration_cost_index"], 0.0)
            self.assertGreaterEqual(step["army_maintenance_cost_index"], 0.0)
            self.assertGreaterEqual(step["war_cost_index"], 0.0)
            self.assertGreaterEqual(step["treasury_end_index"], 0.0)
            self.assertGreaterEqual(step["army_capacity_population"], 0.0)
            self.assertGreaterEqual(step["mobilized_force_population"], 0.0)
            self.assertGreaterEqual(step["prosperity_index"], 0.0)
            self.assertLessEqual(step["prosperity_index"], 1.0)
            self.assertGreaterEqual(step["food_security_index"], 0.0)
            self.assertLessEqual(step["food_security_index"], 1.0)
            self.assertGreaterEqual(step["trade_dependency_index"], 0.0)
            self.assertLessEqual(step["trade_dependency_index"], 1.0)
            self.assertGreaterEqual(step["military_burden_index"], 0.0)
            self.assertLessEqual(step["military_burden_index"], 1.0)
            self.assertAlmostEqual(
                step["treasury_start_index"]
                + step["tax_revenue_index"]
                + step["trade_revenue_index"]
                + step["insolvency_adjustment_index"]
                - step["administration_cost_index"]
                - step["army_maintenance_cost_index"]
                - step["war_cost_index"]
                - step["treasury_end_index"],
                step["balance_residual_index"],
                delta=0.001,
            )
            self.assertAlmostEqual(step["balance_residual_index"], 0.0, delta=0.001)
            if previous_treasury is not None:
                self.assertAlmostEqual(
                    step["treasury_start_index"],
                    previous_treasury,
                    delta=max(0.001, previous_treasury * 0.0001),
                )
            previous_treasury = step["treasury_end_index"]
        self.assertAlmostEqual(
            first_economy_history["final_gross_output_index"],
            first_economy_history["steps"][-1]["gross_output_index"],
            delta=max(0.001, first_economy_history["final_gross_output_index"] * 0.0001),
        )

        first_firm = world["firm_agents"][0]
        self.assertIn("region_id", first_firm)
        self.assertIn("population_region_id", first_firm)
        self.assertIn("settlement_id", first_firm)
        self.assertIn("sector", first_firm)
        self.assertIn("output_index", first_firm)
        self.assertIn("employment_capacity", first_firm)
        self.assertIn("wage_index", first_firm)
        self.assertIn("productivity_index", first_firm)
        self.assertIn("market_dependency_index", first_firm)
        self.assertIn("capital_stock_index", first_firm)
        self.assertIn("supply_chain_risk_index", first_firm)
        self.assertIn("tax_contribution_index", first_firm)
        self.assertGreaterEqual(first_firm["output_index"], 0.0)
        self.assertGreaterEqual(first_firm["employment_capacity"], 0.0)
        self.assertGreaterEqual(first_firm["tax_contribution_index"], 0.0)
        for key in (
            "wage_index",
            "productivity_index",
            "market_dependency_index",
            "capital_stock_index",
            "supply_chain_risk_index",
        ):
            self.assertGreaterEqual(first_firm[key], 0.0)
            self.assertLessEqual(first_firm[key], 1.0)

        first_agent_history = world["demographic_agent_histories"][0]
        self.assertIn("population_region_id", first_agent_history)
        self.assertIn("region_id", first_agent_history)
        self.assertIn("household_cohort_ids", first_agent_history)
        self.assertIn("firm_agent_ids", first_agent_history)
        self.assertIn("final_agent_population", first_agent_history)
        self.assertIn("mean_labor_participation_index", first_agent_history)
        self.assertEqual(first_agent_history["step_count"], len(first_agent_history["steps"]))
        self.assertGreaterEqual(first_agent_history["final_agent_population"], 0.0)
        self.assertGreaterEqual(first_agent_history["mean_labor_participation_index"], 0.0)
        self.assertLessEqual(first_agent_history["mean_labor_participation_index"], 1.0)
        for index, step in enumerate(first_agent_history["steps"]):
            self.assertEqual(step["stage_index"], index + 1)
            self.assertIn("era_id", step)
            self.assertGreaterEqual(step["start_year_bp"], step["end_year_bp"])
            self.assertGreaterEqual(step["start_population"], 0.0)
            self.assertGreaterEqual(step["end_population"], 0.0)
            self.assertGreaterEqual(step["working_population"], 0.0)
            self.assertGreaterEqual(step["dependent_population"], 0.0)
            self.assertAlmostEqual(
                step["working_population"] + step["dependent_population"],
                step["end_population"],
                delta=max(1.0, step["end_population"] * 0.0001),
            )
            for key in (
                "migration_propensity_index",
                "consumption_pressure_index",
                "vulnerability_index",
                "labor_participation_index",
            ):
                self.assertGreaterEqual(step[key], 0.0)
                self.assertLessEqual(step[key], 1.0)

        first_individual = world["individual_agents"][0]
        self.assertIn("population_region_id", first_individual)
        self.assertIn("region_id", first_individual)
        self.assertIn("household_cohort_id", first_individual)
        self.assertIn("culture_region_id", first_individual)
        self.assertIn("language_region_id", first_individual)
        self.assertIn("name", first_individual)
        self.assertIn("role", first_individual)
        self.assertIn("birth_year_bp", first_individual)
        self.assertIn("death_year_bp", first_individual)
        self.assertIn("lifespan_years", first_individual)
        self.assertIn("married_person_id", first_individual)
        self.assertIn("parent_person_ids", first_individual)
        self.assertIn("child_person_ids", first_individual)
        self.assertIn("property_value_index", first_individual)
        self.assertIn("mobility_index", first_individual)
        self.assertIn("vulnerability_index", first_individual)
        self.assertIn("event_ids", first_individual)
        self.assertIn("event_count", first_individual)
        self.assertTrue(first_individual["name"])
        self.assertTrue(first_individual["role"])
        self.assertGreaterEqual(first_individual["birth_year_bp"], first_individual["death_year_bp"])
        self.assertAlmostEqual(
            first_individual["lifespan_years"],
            first_individual["birth_year_bp"] - first_individual["death_year_bp"],
            delta=max(0.001, first_individual["lifespan_years"] * 0.0001),
        )
        self.assertEqual(first_individual["event_count"], len(first_individual["event_ids"]))
        self.assertGreaterEqual(first_individual["property_value_index"], 0.0)
        self.assertGreaterEqual(first_individual["mobility_index"], 0.0)
        self.assertLessEqual(first_individual["mobility_index"], 1.0)
        self.assertGreaterEqual(first_individual["vulnerability_index"], 0.0)
        self.assertLessEqual(first_individual["vulnerability_index"], 1.0)

        first_life_event = world["individual_life_events"][0]
        self.assertIn("person_id", first_life_event)
        self.assertIn("related_person_id", first_life_event)
        self.assertIn("population_region_id", first_life_event)
        self.assertIn("region_id", first_life_event)
        self.assertIn("household_cohort_id", first_life_event)
        self.assertIn("era_id", first_life_event)
        self.assertIn("event_type", first_life_event)
        self.assertIn("year_bp", first_life_event)
        self.assertIn("property_value_index", first_life_event)
        self.assertIn("demographic_pressure_index", first_life_event)
        self.assertIn("mortality_risk_index", first_life_event)
        self.assertIn("inheritance_fraction", first_life_event)
        self.assertIn(first_life_event["event_type"], {"birth", "death", "marriage", "property_transfer"})
        self.assertEqual(first_life_event["person_id"], first_individual["id"])
        self.assertGreaterEqual(first_life_event["year_bp"], 0.0)
        self.assertGreaterEqual(first_life_event["property_value_index"], 0.0)
        self.assertGreaterEqual(first_life_event["demographic_pressure_index"], 0.0)
        self.assertLessEqual(first_life_event["demographic_pressure_index"], 1.0)
        self.assertGreaterEqual(first_life_event["mortality_risk_index"], 0.0)
        self.assertLessEqual(first_life_event["mortality_risk_index"], 1.0)
        self.assertGreaterEqual(first_life_event["inheritance_fraction"], 0.0)
        self.assertLessEqual(first_life_event["inheritance_fraction"], 1.0)

        if world["conflicts"]:
            first_conflict = world["conflicts"][0]
            self.assertIn("era_id", first_conflict)
            self.assertIn("region_a", first_conflict)
            self.assertIn("region_b", first_conflict)
            self.assertIn("cause", first_conflict)
            self.assertIn("outcome", first_conflict)
            self.assertIn("intensity", first_conflict)
            self.assertIn("war_duration_years", first_conflict)
            self.assertIn("region_a_force_estimate", first_conflict)
            self.assertIn("region_b_force_estimate", first_conflict)
            self.assertIn("mobilized_population", first_conflict)
            self.assertIn("casualty_rate", first_conflict)
            self.assertIn("logistics_strain_index", first_conflict)
            self.assertIn("economic_disruption_index", first_conflict)
            self.assertIn("estimated_casualties", first_conflict)
            self.assertGreaterEqual(first_conflict["war_duration_years"], 0.0)
            self.assertGreaterEqual(first_conflict["mobilized_population"], 0.0)
            self.assertGreaterEqual(first_conflict["casualty_rate"], 0.0)
            self.assertLessEqual(first_conflict["casualty_rate"], 1.0)
            self.assertGreaterEqual(first_conflict["logistics_strain_index"], 0.0)
            self.assertLessEqual(first_conflict["logistics_strain_index"], 1.0)
            self.assertGreaterEqual(first_conflict["economic_disruption_index"], 0.0)
            self.assertLessEqual(first_conflict["economic_disruption_index"], 1.0)

        first_dynasty = world["dynasties"][0]
        self.assertIn("region_id", first_dynasty)
        self.assertIn("parent_dynasty_id", first_dynasty)
        self.assertIn("founder_dynasty_id", first_dynasty)
        self.assertIn("successor_dynasty_id", first_dynasty)
        self.assertIn("collapse_reason", first_dynasty)
        self.assertIn("lineage_depth", first_dynasty)
        self.assertIn("child_dynasty_count", first_dynasty)
        self.assertIn("child_dynasty_ids", first_dynasty)
        self.assertIn("duration_years", first_dynasty)
        self.assertIn("legitimacy_index", first_dynasty)
        self.assertIn("succession_pressure", first_dynasty)
        self.assertIn("dynastic_continuity_index", first_dynasty)
        self.assertIn("founder_ruler_id", first_dynasty)
        self.assertIn("ruler_count", first_dynasty)
        self.assertIn("marriage_alliance_count", first_dynasty)
        self.assertIn("cadet_branch_count", first_dynasty)
        self.assertEqual(first_dynasty["founder_dynasty_id"], first_dynasty["id"])
        self.assertEqual(first_dynasty["child_dynasty_count"], len(first_dynasty["child_dynasty_ids"]))
        self.assertGreaterEqual(first_dynasty["dynastic_continuity_index"], 0.0)
        self.assertLessEqual(first_dynasty["dynastic_continuity_index"], 1.0)

        first_ruler = world["rulers"][0]
        self.assertIn("dynasty_id", first_ruler)
        self.assertIn("name", first_ruler)
        self.assertIn("regnal_number", first_ruler)
        self.assertIn("parent_ruler_id", first_ruler)
        self.assertIn("predecessor_ruler_id", first_ruler)
        self.assertIn("successor_ruler_id", first_ruler)
        self.assertIn("spouse_ruler_id", first_ruler)
        self.assertIn("marriage_alliance_id", first_ruler)
        self.assertIn("cadet_branch_id", first_ruler)
        self.assertIn("birth_year_bp", first_ruler)
        self.assertIn("reign_start_year_bp", first_ruler)
        self.assertIn("reign_end_year_bp", first_ruler)
        self.assertIn("reign_length_years", first_ruler)
        self.assertIn("ruler_lineage_depth", first_ruler)
        self.assertIn("legitimacy_index", first_ruler)
        self.assertIn("succession_claim_strength", first_ruler)
        self.assertIn("military_prestige_index", first_ruler)
        self.assertIn("economic_patronage_index", first_ruler)
        self.assertIn("succession_crisis_risk", first_ruler)
        self.assertGreater(first_ruler["regnal_number"], 0)
        self.assertGreaterEqual(first_ruler["reign_start_year_bp"], first_ruler["reign_end_year_bp"])
        self.assertAlmostEqual(
            first_ruler["reign_length_years"],
            first_ruler["reign_start_year_bp"] - first_ruler["reign_end_year_bp"],
            delta=0.001,
        )
        self.assertGreaterEqual(first_ruler["legitimacy_index"], 0.0)
        self.assertLessEqual(first_ruler["legitimacy_index"], 1.0)
        self.assertGreaterEqual(first_ruler["succession_claim_strength"], 0.0)
        self.assertLessEqual(first_ruler["succession_claim_strength"], 1.0)
        self.assertGreaterEqual(first_ruler["military_prestige_index"], 0.0)
        self.assertLessEqual(first_ruler["military_prestige_index"], 1.0)
        self.assertGreaterEqual(first_ruler["economic_patronage_index"], 0.0)
        self.assertLessEqual(first_ruler["economic_patronage_index"], 1.0)
        self.assertGreaterEqual(first_ruler["succession_crisis_risk"], 0.0)
        self.assertLessEqual(first_ruler["succession_crisis_risk"], 1.0)

        if world["marriage_alliances"]:
            first_alliance = world["marriage_alliances"][0]
            self.assertIn("dynasty_a_id", first_alliance)
            self.assertIn("dynasty_b_id", first_alliance)
            self.assertIn("ruler_a_id", first_alliance)
            self.assertIn("ruler_b_id", first_alliance)
            self.assertIn("region_a_id", first_alliance)
            self.assertIn("region_b_id", first_alliance)
            self.assertIn("alliance_year_bp", first_alliance)
            self.assertIn("alliance_strength", first_alliance)
            self.assertIn("trade_pact_index", first_alliance)
            self.assertIn("succession_dispute_risk", first_alliance)
            self.assertGreaterEqual(first_alliance["alliance_strength"], 0.0)
            self.assertLessEqual(first_alliance["alliance_strength"], 1.0)
            self.assertGreaterEqual(first_alliance["trade_pact_index"], 0.0)
            self.assertLessEqual(first_alliance["trade_pact_index"], 1.0)
            self.assertGreaterEqual(first_alliance["succession_dispute_risk"], 0.0)
            self.assertLessEqual(first_alliance["succession_dispute_risk"], 1.0)

        if world["cadet_branches"]:
            first_branch = world["cadet_branches"][0]
            self.assertIn("dynasty_id", first_branch)
            self.assertIn("parent_dynasty_id", first_branch)
            self.assertIn("founder_ruler_id", first_branch)
            self.assertIn("heir_ruler_ids", first_branch)
            self.assertIn("branch_start_year_bp", first_branch)
            self.assertIn("branch_end_year_bp", first_branch)
            self.assertIn("claim_strength", first_branch)
            self.assertIn("cadet_legitimacy_index", first_branch)
            self.assertGreaterEqual(first_branch["branch_start_year_bp"], first_branch["branch_end_year_bp"])
            self.assertGreaterEqual(first_branch["claim_strength"], 0.0)
            self.assertLessEqual(first_branch["claim_strength"], 1.0)
            self.assertGreaterEqual(first_branch["cadet_legitimacy_index"], 0.0)
            self.assertLessEqual(first_branch["cadet_legitimacy_index"], 1.0)

        first_snapshot = world["territorial_snapshots"][0]
        self.assertIn("era_id", first_snapshot)
        self.assertIn("dominant_process", first_snapshot)
        self.assertIn("assigned_land_fraction", first_snapshot)
        self.assertIn("fragmentation_index", first_snapshot)
        self.assertEqual(first_snapshot["region_count"], len(first_snapshot["regions"]))
        self.assertGreater(first_snapshot["region_count"], 0)
        self.assertIn("boundary_cell_ids", first_snapshot["regions"][0])
        self.assertIn("boundary_ring", first_snapshot["regions"][0])
        self.assertIn("crosses_antimeridian", first_snapshot["regions"][0])
        self.assertIn("boundary_perimeter_km", first_snapshot["regions"][0])
        self.assertIn("dissolved_polygon_area_km2", first_snapshot["regions"][0])
        self.assertIn("polygon_area_error_fraction", first_snapshot["regions"][0])
        self.assertIn("compactness_index", first_snapshot["regions"][0])
        self.assertIn("geometry_quality", first_snapshot["regions"][0])
        self.assertIn("stability_index", first_snapshot["regions"][0])
        self.assertIn("estimated_population", first_snapshot["regions"][0])
        self.assertIn("cell_edge_boundary_segment_ids", first_snapshot["regions"][0])
        self.assertIn("cell_edge_boundary_segment_count", first_snapshot["regions"][0])
        self.assertIn("cell_edge_boundary_length_km", first_snapshot["regions"][0])
        self.assertIn("mean_cell_edge_boundary_segment_quality", first_snapshot["regions"][0])
        self.assertIn("neighbor_region_ids", first_snapshot["regions"][0])
        self.assertIn("cell_edge_dissolved_area_km2", first_snapshot["regions"][0])
        self.assertEqual(
            first_snapshot["regions"][0]["cell_edge_boundary_segment_count"],
            len(first_snapshot["regions"][0]["cell_edge_boundary_segment_ids"]),
        )
        self.assertGreaterEqual(first_snapshot["regions"][0]["cell_edge_boundary_length_km"], 0.0)
        self.assertGreaterEqual(first_snapshot["regions"][0]["mean_cell_edge_boundary_segment_quality"], 0.0)
        self.assertLessEqual(first_snapshot["regions"][0]["mean_cell_edge_boundary_segment_quality"], 1.0)
        self.assertGreaterEqual(first_snapshot["regions"][0]["cell_edge_dissolved_area_km2"], 0.0)

        if world["territorial_boundary_segments"]:
            first_territorial_segment = world["territorial_boundary_segments"][0]
            self.assertEqual(first_territorial_segment["id"], 0)
            self.assertIn("source_edge_id", first_territorial_segment)
            self.assertIn("region_a_id", first_territorial_segment)
            self.assertIn("region_b_id", first_territorial_segment)
            self.assertIn("length_km", first_territorial_segment)
            self.assertIn("boundary_segment_quality", first_territorial_segment)
            self.assertIn("natural_boundary", first_territorial_segment)
            self.assertGreater(first_territorial_segment["length_km"], 0.0)
            self.assertGreaterEqual(first_territorial_segment["boundary_segment_quality"], 0.0)
            self.assertLessEqual(first_territorial_segment["boundary_segment_quality"], 1.0)

        if world["borders"]:
            first_border = world["borders"][0]
            self.assertIn("region_a", first_border)
            self.assertIn("region_b", first_border)
            self.assertIn("type", first_border)
            self.assertIn("length_km", first_border)

        if world["sacred_areas"]:
            first_site = world["sacred_areas"][0]
            self.assertIn("culture_region_id", first_site)
            self.assertIn("language_region_id", first_site)
            self.assertIn("type", first_site)
            self.assertIn("significance", first_site)

        if world["ruins"]:
            first_ruin = world["ruins"][0]
            self.assertIn("culture_region_id", first_ruin)
            self.assertIn("language_region_id", first_ruin)
            self.assertIn("type", first_ruin)
            self.assertIn("abandonment_reason", first_ruin)
            self.assertIn("preservation_score", first_ruin)

        if world["trade_flows"]:
            first_trade = world["trade_flows"][0]
            self.assertIn("route_id", first_trade)
            self.assertIn("primary_good", first_trade)
            self.assertIn("volume_index", first_trade)
            self.assertIn("friction", first_trade)
            self.assertIn("interregional", first_trade)

        first_plate_graph_node = world["plate_graph"]["nodes"][0]
        self.assertIn("plate_id", first_plate_graph_node)
        self.assertIn("degree", first_plate_graph_node)
        self.assertIn("edge_ids", first_plate_graph_node)
        if world["plate_graph"]["edges"]:
            first_plate_graph_edge = world["plate_graph"]["edges"][0]
            self.assertIn("plate_a", first_plate_graph_edge)
            self.assertIn("plate_b", first_plate_graph_edge)
            self.assertIn("cell_edge_count", first_plate_graph_edge)
            self.assertIn("dominant_boundary_type", first_plate_graph_edge)

        if world["river_graph"]["nodes"]:
            first_river_graph_node = world["river_graph"]["nodes"][0]
            self.assertIn("cell_id", first_river_graph_node)
            self.assertIn("flow_to_cell_id", first_river_graph_node)
            self.assertIn("upstream_cell_ids", first_river_graph_node)
        if world["river_graph"]["edges"]:
            first_river_graph_edge = world["river_graph"]["edges"][0]
            self.assertIn("from_cell_id", first_river_graph_edge)
            self.assertIn("to_cell_id", first_river_graph_edge)
            self.assertIn("length_km", first_river_graph_edge)

        first_watershed_graph_node = world["watershed_graph"]["nodes"][0]
        self.assertIn("watershed_id", first_watershed_graph_node)
        self.assertIn("basin_id", first_watershed_graph_node)
        self.assertIn("edge_ids", first_watershed_graph_node)
        if world["watershed_graph"]["edges"]:
            first_watershed_graph_edge = world["watershed_graph"]["edges"][0]
            self.assertIn("watershed_a", first_watershed_graph_edge)
            self.assertIn("watershed_b", first_watershed_graph_edge)
            self.assertIn("boundary_edge_count", first_watershed_graph_edge)

        first_trade_graph_node = world["trade_route_graph"]["nodes"][0]
        self.assertIn("settlement_id", first_trade_graph_node)
        self.assertIn("region_id", first_trade_graph_node)
        self.assertIn("edge_ids", first_trade_graph_node)
        if world["trade_route_graph"]["edges"]:
            first_trade_graph_edge = world["trade_route_graph"]["edges"][0]
            self.assertIn("route_id", first_trade_graph_edge)
            self.assertIn("trade_flow_id", first_trade_graph_edge)
            self.assertIn("route_corridor_id", first_trade_graph_edge)
            self.assertIn("volume_index", first_trade_graph_edge)

        first_political_graph_node = world["political_region_graph"]["nodes"][0]
        self.assertIn("region_id", first_political_graph_node)
        self.assertIn("capital_settlement_id", first_political_graph_node)
        self.assertIn("edge_ids", first_political_graph_node)
        if world["political_region_graph"]["edges"]:
            first_political_graph_edge = world["political_region_graph"]["edges"][0]
            self.assertIn("region_a", first_political_graph_edge)
            self.assertIn("region_b", first_political_graph_edge)
            self.assertIn("border_ids", first_political_graph_edge)
            self.assertIn("trade_flow_ids", first_political_graph_edge)

        first_logistics = world["logistics_networks"][0]
        self.assertIn("region_id", first_logistics)
        self.assertIn("route_ids", first_logistics)
        self.assertIn("trade_flow_ids", first_logistics)
        self.assertIn("border_ids", first_logistics)
        self.assertIn("total_route_distance_km", first_logistics)
        self.assertIn("total_trade_volume_index", first_logistics)
        self.assertIn("supply_capacity_index", first_logistics)
        self.assertIn("transport_efficiency_index", first_logistics)
        self.assertIn("logistics_resilience_index", first_logistics)
        self.assertIn("chokepoint_exposure_index", first_logistics)
        self.assertEqual(first_logistics["route_count"], len(first_logistics["route_ids"]))
        self.assertEqual(first_logistics["trade_flow_count"], len(first_logistics["trade_flow_ids"]))
        self.assertEqual(first_logistics["border_count"], len(first_logistics["border_ids"]))
        self.assertGreaterEqual(first_logistics["total_route_distance_km"], 0.0)
        self.assertGreaterEqual(first_logistics["total_trade_volume_index"], 0.0)
        self.assertGreaterEqual(first_logistics["supply_capacity_index"], 0.0)
        self.assertLessEqual(first_logistics["supply_capacity_index"], 1.0)
        self.assertGreaterEqual(first_logistics["transport_efficiency_index"], 0.0)
        self.assertLessEqual(first_logistics["transport_efficiency_index"], 1.0)
        self.assertGreaterEqual(first_logistics["logistics_resilience_index"], 0.0)
        self.assertLessEqual(first_logistics["logistics_resilience_index"], 1.0)
        self.assertGreaterEqual(first_logistics["chokepoint_exposure_index"], 0.0)
        self.assertLessEqual(first_logistics["chokepoint_exposure_index"], 1.0)

        if world["market_exchanges"]:
            first_market = world["market_exchanges"][0]
            self.assertIn("trade_flow_id", first_market)
            self.assertIn("route_id", first_market)
            self.assertIn("region_from", first_market)
            self.assertIn("region_to", first_market)
            self.assertIn("supply_index", first_market)
            self.assertIn("demand_index", first_market)
            self.assertIn("price_spread_index", first_market)
            self.assertIn("market_access_index", first_market)
            self.assertIn("tax_revenue_index", first_market)
            self.assertIn("food_security_link_index", first_market)
            self.assertIn("disruption_risk_index", first_market)
            self.assertIn("market_clearing_record_id", first_market)
            self.assertIn("cleared_volume_index", first_market)
            self.assertIn("unmet_demand_index", first_market)
            self.assertIn("clearance_fraction", first_market)
            self.assertGreaterEqual(first_market["volume_index"], 0.0)
            self.assertGreaterEqual(first_market["tax_revenue_index"], 0.0)
            self.assertGreaterEqual(first_market["cleared_volume_index"], 0.0)
            self.assertGreaterEqual(first_market["unmet_demand_index"], 0.0)
            for key in (
                "supply_index",
                "demand_index",
                "price_spread_index",
                "market_access_index",
                "food_security_link_index",
                "disruption_risk_index",
                "clearance_fraction",
            ):
                self.assertGreaterEqual(first_market[key], 0.0)
                self.assertLessEqual(first_market[key], 1.0)

            self.assertTrue(world["route_capacity_constraints"])
            first_constraint = world["route_capacity_constraints"][0]
            self.assertIn("route_id", first_constraint)
            self.assertIn("route_type", first_constraint)
            self.assertIn("market_exchange_ids", first_constraint)
            self.assertIn("market_exchange_count", first_constraint)
            self.assertIn("requested_volume_index", first_constraint)
            self.assertIn("capacity_volume_index", first_constraint)
            self.assertIn("cleared_volume_index", first_constraint)
            self.assertIn("unmet_volume_index", first_constraint)
            self.assertIn("utilization_index", first_constraint)
            self.assertIn("congestion_index", first_constraint)
            self.assertIn("shortage_index", first_constraint)
            self.assertIn("spoilage_loss_index", first_constraint)
            self.assertEqual(first_constraint["market_exchange_count"], len(first_constraint["market_exchange_ids"]))
            self.assertGreaterEqual(first_constraint["requested_volume_index"], 0.0)
            self.assertGreaterEqual(first_constraint["capacity_volume_index"], 0.0)
            self.assertGreaterEqual(first_constraint["cleared_volume_index"], 0.0)
            self.assertGreaterEqual(first_constraint["unmet_volume_index"], 0.0)
            self.assertAlmostEqual(
                first_constraint["cleared_volume_index"] + first_constraint["unmet_volume_index"],
                first_constraint["requested_volume_index"],
                delta=max(0.001, first_constraint["requested_volume_index"] * 0.0001),
            )
            for key in ("utilization_index", "congestion_index", "shortage_index", "spoilage_loss_index"):
                self.assertGreaterEqual(first_constraint[key], 0.0)
                self.assertLessEqual(first_constraint[key], 1.0)
            constraint_route = next(route for route in world["routes"] if route["id"] == first_constraint["route_id"])
            self.assertEqual(constraint_route["route_capacity_constraint_id"], first_constraint["id"])
            self.assertIn("market_capacity_volume_index", constraint_route)
            self.assertIn("market_capacity_utilization_index", constraint_route)

            self.assertTrue(world["market_clearing_records"])
            first_clearing = world["market_clearing_records"][0]
            self.assertIn("market_exchange_id", first_clearing)
            self.assertIn("trade_flow_id", first_clearing)
            self.assertIn("route_id", first_clearing)
            self.assertIn("route_capacity_constraint_id", first_clearing)
            self.assertIn("primary_good", first_clearing)
            self.assertIn("requested_volume_index", first_clearing)
            self.assertIn("cleared_volume_index", first_clearing)
            self.assertIn("unmet_demand_index", first_clearing)
            self.assertIn("clearance_fraction", first_clearing)
            self.assertIn("route_utilization_index", first_clearing)
            self.assertIn("price_adjustment_index", first_clearing)
            self.assertIn("rationing_index", first_clearing)
            self.assertIn("producer_surplus_index", first_clearing)
            self.assertIn("consumer_welfare_index", first_clearing)
            self.assertIn("agent_order_ids", first_clearing)
            self.assertIn("agent_order_count", first_clearing)
            self.assertIn("price_iteration_ids", first_clearing)
            self.assertIn("price_iteration_count", first_clearing)
            self.assertIn("endogenous_supply_index", first_clearing)
            self.assertIn("endogenous_demand_index", first_clearing)
            self.assertIn("equilibrium_price_index", first_clearing)
            self.assertIn("price_residual_index", first_clearing)
            self.assertGreaterEqual(first_clearing["requested_volume_index"], 0.0)
            self.assertGreaterEqual(first_clearing["cleared_volume_index"], 0.0)
            self.assertGreaterEqual(first_clearing["unmet_demand_index"], 0.0)
            self.assertGreaterEqual(first_clearing["endogenous_supply_index"], 0.0)
            self.assertGreaterEqual(first_clearing["endogenous_demand_index"], 0.0)
            self.assertEqual(first_clearing["agent_order_count"], len(first_clearing["agent_order_ids"]))
            self.assertEqual(first_clearing["price_iteration_count"], len(first_clearing["price_iteration_ids"]))
            self.assertAlmostEqual(
                first_clearing["cleared_volume_index"] + first_clearing["unmet_demand_index"],
                first_clearing["requested_volume_index"],
                delta=max(0.001, first_clearing["requested_volume_index"] * 0.0001),
            )
            for key in (
                "clearance_fraction",
                "route_utilization_index",
                "price_adjustment_index",
                "rationing_index",
                "producer_surplus_index",
                "consumer_welfare_index",
                "equilibrium_price_index",
                "price_residual_index",
            ):
                self.assertGreaterEqual(first_clearing[key], 0.0)
                self.assertLessEqual(first_clearing[key], 1.0)
            clearing_market = next(
                market for market in world["market_exchanges"] if market["id"] == first_clearing["market_exchange_id"]
            )
            self.assertEqual(clearing_market["market_clearing_record_id"], first_clearing["id"])
            self.assertEqual(clearing_market["route_id"], first_clearing["route_id"])
            self.assertAlmostEqual(
                clearing_market["cleared_volume_index"],
                first_clearing["cleared_volume_index"],
                delta=max(0.001, first_clearing["cleared_volume_index"] * 0.0001),
            )
            self.assertTrue(world["market_agent_orders"])
            first_order = next(
                order for order in world["market_agent_orders"] if order["id"] in first_clearing["agent_order_ids"]
            )
            self.assertIn("agent_type", first_order)
            self.assertIn("order_side", first_order)
            self.assertIn("order_kind", first_order)
            self.assertIn("limit_price_index", first_order)
            self.assertIn("price_acceptance_index", first_order)
            self.assertIn("rationing_index", first_order)
            self.assertIn("inventory_change_index", first_order)
            self.assertEqual(first_order["market_exchange_id"], first_clearing["market_exchange_id"])
            self.assertEqual(first_order["market_clearing_record_id"], first_clearing["id"])
            self.assertIn(first_order["agent_type"], {"firm", "household_cohort", "state"})
            self.assertIn(first_order["order_side"], {"supply", "demand"})
            self.assertGreaterEqual(first_order["requested_volume_index"], 0.0)
            self.assertGreaterEqual(first_order["cleared_volume_index"], 0.0)
            self.assertLessEqual(first_order["cleared_volume_index"], first_order["requested_volume_index"] + 0.001)
            self.assertGreaterEqual(first_order["inventory_change_index"], -1.0)
            self.assertLessEqual(first_order["inventory_change_index"], 1.0)
            for key in ("limit_price_index", "price_acceptance_index", "rationing_index"):
                self.assertGreaterEqual(first_order[key], 0.0)
                self.assertLessEqual(first_order[key], 1.0)

            self.assertTrue(world["market_price_iterations"])
            first_iteration = next(
                iteration
                for iteration in world["market_price_iterations"]
                if iteration["id"] in first_clearing["price_iteration_ids"]
            )
            self.assertEqual(first_iteration["market_exchange_id"], first_clearing["market_exchange_id"])
            self.assertEqual(first_iteration["market_clearing_record_id"], first_clearing["id"])
            self.assertGreater(first_iteration["iteration_index"], 0)
            self.assertEqual(first_iteration["order_count"], len(first_iteration["order_ids"]))
            self.assertGreaterEqual(first_iteration["supply_volume_index"], 0.0)
            self.assertGreaterEqual(first_iteration["demand_volume_index"], 0.0)
            self.assertAlmostEqual(
                first_iteration["demand_volume_index"] - first_iteration["supply_volume_index"],
                first_iteration["imbalance_index"],
                delta=max(0.001, abs(first_iteration["imbalance_index"]) * 0.0001),
            )
            for order_id in first_iteration["order_ids"]:
                self.assertIn(order_id, first_clearing["agent_order_ids"])
            for key in ("price_index", "excess_demand_index", "price_adjustment_index"):
                self.assertGreaterEqual(first_iteration[key], 0.0)
                self.assertLessEqual(first_iteration[key], 1.0)

            self.assertTrue(world["market_inventory_histories"])
            first_inventory = next(
                history
                for history in world["market_inventory_histories"]
                if history["id"] == first_clearing["market_inventory_history_id"]
            )
            self.assertIn("initial_inventory_index", first_inventory)
            self.assertIn("target_inventory_index", first_inventory)
            self.assertIn("final_inventory_index", first_inventory)
            self.assertIn("inventory_gap_index", first_inventory)
            self.assertIn("learning_rate_index", first_inventory)
            self.assertIn("mean_inventory_pressure_index", first_inventory)
            self.assertIn("mean_price_expectation_index", first_inventory)
            self.assertIn("mean_supply_response_index", first_inventory)
            self.assertIn("mean_demand_adjustment_index", first_inventory)
            self.assertIn("high_inventory_stress", first_inventory)
            self.assertIn("steps", first_inventory)
            self.assertEqual(first_inventory["market_clearing_record_id"], first_clearing["id"])
            self.assertEqual(first_inventory["market_exchange_id"], first_clearing["market_exchange_id"])
            self.assertEqual(first_inventory["route_id"], first_clearing["route_id"])
            self.assertEqual(first_inventory["step_count"], len(first_inventory["steps"]))
            self.assertEqual(first_inventory["step_count"], first_clearing["price_iteration_count"])
            self.assertAlmostEqual(
                first_inventory["inventory_gap_index"],
                abs(first_inventory["final_inventory_index"] - first_inventory["target_inventory_index"]),
                delta=0.001,
            )
            self.assertIsInstance(first_inventory["high_inventory_stress"], bool)
            for key in (
                "initial_inventory_index",
                "target_inventory_index",
                "final_inventory_index",
                "inventory_gap_index",
                "learning_rate_index",
                "mean_inventory_pressure_index",
                "mean_price_expectation_index",
                "mean_supply_response_index",
                "mean_demand_adjustment_index",
            ):
                self.assertGreaterEqual(first_inventory[key], 0.0)
                self.assertLessEqual(first_inventory[key], 1.0)
            first_inventory_step = first_inventory["steps"][0]
            self.assertIn("price_iteration_id", first_inventory_step)
            self.assertIn("inventory_index", first_inventory_step)
            self.assertIn("target_inventory_index", first_inventory_step)
            self.assertIn("inventory_gap_index", first_inventory_step)
            self.assertIn("supply_response_index", first_inventory_step)
            self.assertIn("demand_adjustment_index", first_inventory_step)
            self.assertIn("learning_rate_index", first_inventory_step)
            self.assertIn("producer_expectation_index", first_inventory_step)
            self.assertIn("consumer_expectation_index", first_inventory_step)
            self.assertIn("rationing_memory_index", first_inventory_step)
            self.assertIn("clearance_memory_index", first_inventory_step)
            self.assertEqual(first_inventory_step["sequence_index"], 0)
            self.assertEqual(first_inventory_step["price_iteration_id"], first_clearing["price_iteration_ids"][0])
            self.assertAlmostEqual(
                first_inventory_step["inventory_gap_index"],
                abs(first_inventory_step["inventory_index"] - first_inventory_step["target_inventory_index"]),
                delta=0.001,
            )
            for key in (
                "price_index",
                "inventory_index",
                "target_inventory_index",
                "inventory_gap_index",
                "supply_response_index",
                "demand_adjustment_index",
                "learning_rate_index",
                "producer_expectation_index",
                "consumer_expectation_index",
                "rationing_memory_index",
                "clearance_memory_index",
            ):
                self.assertGreaterEqual(first_inventory_step[key], 0.0)
                self.assertLessEqual(first_inventory_step[key], 1.0)

        if world["campaign_movements"]:
            first_campaign = world["campaign_movements"][0]
            self.assertIn("conflict_id", first_campaign)
            self.assertIn("origin_region_id", first_campaign)
            self.assertIn("target_region_id", first_campaign)
            self.assertIn("origin_cell_id", first_campaign)
            self.assertIn("target_cell_id", first_campaign)
            self.assertIn("route_id", first_campaign)
            self.assertIn("border_id", first_campaign)
            self.assertIn("path_cell_ids", first_campaign)
            self.assertIn("path_segment_ids", first_campaign)
            self.assertIn("path_length_km", first_campaign)
            self.assertIn("path_terrain_cost_index", first_campaign)
            self.assertIn("path_supply_loss_index", first_campaign)
            self.assertIn("path_attrition_index", first_campaign)
            self.assertIn("campaign_front_history_id", first_campaign)
            self.assertIn("travel_time_days", first_campaign)
            self.assertIn("force_estimate", first_campaign)
            self.assertIn("supply_required_index", first_campaign)
            self.assertIn("attrition_risk_index", first_campaign)
            self.assertIn("operational_reach_index", first_campaign)
            self.assertIn("campaign_success_index", first_campaign)
            self.assertGreaterEqual(first_campaign["start_year_bp"], first_campaign["end_year_bp"])
            self.assertGreater(first_campaign["distance_km"], 0.0)
            self.assertGreater(first_campaign["path_length_km"], 0.0)
            self.assertAlmostEqual(
                first_campaign["distance_km"],
                first_campaign["path_length_km"],
                delta=max(0.001, first_campaign["path_length_km"] * 0.0001),
            )
            self.assertEqual(first_campaign["path_cell_count"], len(first_campaign["path_cell_ids"]))
            self.assertEqual(first_campaign["path_segment_count"], len(first_campaign["path_segment_ids"]))
            self.assertEqual(first_campaign["path_segment_count"], max(0, first_campaign["path_cell_count"] - 1))
            self.assertEqual(first_campaign["path_cell_ids"][0], first_campaign["origin_cell_id"])
            self.assertEqual(first_campaign["path_cell_ids"][-1], first_campaign["target_cell_id"])
            self.assertGreater(first_campaign["travel_time_days"], 0.0)
            self.assertGreaterEqual(first_campaign["force_estimate"], 0.0)
            for key in (
                "supply_required_index",
                "attrition_risk_index",
                "logistics_strain_index",
                "operational_reach_index",
                "campaign_success_index",
                "path_terrain_cost_index",
                "path_supply_loss_index",
                "path_attrition_index",
            ):
                self.assertGreaterEqual(first_campaign[key], 0.0)
                self.assertLessEqual(first_campaign[key], 1.0)
            self.assertTrue(world["campaign_path_segments"])
            first_segment = world["campaign_path_segments"][0]
            self.assertIn("campaign_movement_id", first_segment)
            self.assertIn("sequence_index", first_segment)
            self.assertIn("from_cell_id", first_segment)
            self.assertIn("to_cell_id", first_segment)
            self.assertIn("route_mode", first_segment)
            self.assertIn("distance_km", first_segment)
            self.assertIn("elapsed_days", first_segment)
            self.assertIn("terrain_cost_index", first_segment)
            self.assertIn("barrier_cost_index", first_segment)
            self.assertIn("supply_loss_index", first_segment)
            self.assertIn("attrition_index", first_segment)
            self.assertIn("elevation_gain_m", first_segment)
            self.assertIn("water_crossing", first_segment)
            self.assertEqual(first_segment["campaign_movement_id"], first_campaign["id"])
            self.assertEqual(first_segment["sequence_index"], 0)
            self.assertEqual(first_segment["from_cell_id"], first_campaign["path_cell_ids"][0])
            self.assertEqual(first_segment["to_cell_id"], first_campaign["path_cell_ids"][1])
            self.assertGreater(first_segment["distance_km"], 0.0)
            self.assertGreater(first_segment["elapsed_days"], 0.0)
            self.assertGreaterEqual(first_segment["elevation_gain_m"], 0.0)
            for key in ("terrain_cost_index", "barrier_cost_index", "supply_loss_index", "attrition_index"):
                self.assertGreaterEqual(first_segment[key], 0.0)
                self.assertLessEqual(first_segment[key], 1.0)

            self.assertTrue(world["campaign_front_histories"])
            first_front = world["campaign_front_histories"][0]
            self.assertIn("campaign_movement_id", first_front)
            self.assertIn("conflict_id", first_front)
            self.assertIn("attacking_force_initial", first_front)
            self.assertIn("defending_force_initial", first_front)
            self.assertIn("final_attacking_force_estimate", first_front)
            self.assertIn("final_defending_force_estimate", first_front)
            self.assertIn("path_cell_ids", first_front)
            self.assertIn("path_segment_ids", first_front)
            self.assertIn("step_count", first_front)
            self.assertIn("captured_cell_count", first_front)
            self.assertIn("final_occupied_cell_id", first_front)
            self.assertIn("max_supply_line_length_km", first_front)
            self.assertIn("mean_supply_integrity_index", first_front)
            self.assertIn("mean_occupation_control_index", first_front)
            self.assertIn("outcome_projection", first_front)
            self.assertIn("steps", first_front)
            self.assertEqual(first_campaign["campaign_front_history_id"], first_front["id"])
            self.assertEqual(first_front["campaign_movement_id"], first_campaign["id"])
            self.assertEqual(first_front["path_cell_ids"], first_campaign["path_cell_ids"])
            self.assertEqual(first_front["path_segment_ids"], first_campaign["path_segment_ids"])
            self.assertEqual(first_front["step_count"], len(first_front["steps"]))
            self.assertEqual(first_front["captured_cell_count"], len(first_front["path_cell_ids"]))
            self.assertEqual(first_front["final_occupied_cell_id"], first_front["path_cell_ids"][-1])
            self.assertGreaterEqual(first_front["attacking_force_initial"], first_front["final_attacking_force_estimate"])
            self.assertGreaterEqual(first_front["defending_force_initial"], first_front["final_defending_force_estimate"])
            self.assertGreaterEqual(first_front["max_supply_line_length_km"], 0.0)
            self.assertGreaterEqual(first_front["mean_supply_integrity_index"], 0.0)
            self.assertLessEqual(first_front["mean_supply_integrity_index"], 1.0)
            self.assertGreaterEqual(first_front["mean_occupation_control_index"], 0.0)
            self.assertLessEqual(first_front["mean_occupation_control_index"], 1.0)
            first_front_step = first_front["steps"][0]
            self.assertIn("sequence_index", first_front_step)
            self.assertIn("cell_id", first_front_step)
            self.assertIn("days_elapsed", first_front_step)
            self.assertIn("occupied_cell_ids", first_front_step)
            self.assertIn("occupied_cell_count", first_front_step)
            self.assertIn("front_line_cell_ids", first_front_step)
            self.assertIn("front_line_cell_count", first_front_step)
            self.assertIn("supply_line_length_km", first_front_step)
            self.assertIn("supply_integrity_index", first_front_step)
            self.assertIn("attacking_force_estimate", first_front_step)
            self.assertIn("defending_force_estimate", first_front_step)
            self.assertIn("attrition_loss_population", first_front_step)
            self.assertIn("local_attrition_index", first_front_step)
            self.assertIn("occupation_control_index", first_front_step)
            self.assertIn("front_width_index", first_front_step)
            self.assertIn("contested", first_front_step)
            self.assertEqual(first_front_step["sequence_index"], 0)
            self.assertEqual(first_front_step["cell_id"], first_front["path_cell_ids"][0])
            self.assertEqual(first_front_step["occupied_cell_count"], len(first_front_step["occupied_cell_ids"]))
            self.assertEqual(first_front_step["front_line_cell_count"], len(first_front_step["front_line_cell_ids"]))
            self.assertGreaterEqual(first_front_step["days_elapsed"], 0.0)
            self.assertGreaterEqual(first_front_step["supply_line_length_km"], 0.0)
            self.assertGreaterEqual(first_front_step["attrition_loss_population"], 0.0)
            for key in ("supply_integrity_index", "local_attrition_index", "occupation_control_index", "front_width_index"):
                self.assertGreaterEqual(first_front_step[key], 0.0)
                self.assertLessEqual(first_front_step[key], 1.0)

            self.assertTrue(world["tactical_engagements"])
            first_engagement = world["tactical_engagements"][0]
            self.assertIn("conflict_id", first_engagement)
            self.assertIn("campaign_movement_id", first_engagement)
            self.assertIn("campaign_front_history_id", first_engagement)
            self.assertIn("region_a", first_engagement)
            self.assertIn("region_b", first_engagement)
            self.assertIn("battle_cell_ids", first_engagement)
            self.assertIn("step_count", first_engagement)
            self.assertIn("steps", first_engagement)
            self.assertIn("tactical_outcome", first_engagement)
            self.assertIn("max_front_pressure_index", first_engagement)
            self.assertIn("mean_counter_maneuver_index", first_engagement)
            self.assertIn("mean_supply_contest_index", first_engagement)
            self.assertIn("total_attrition_loss_population", first_engagement)
            self.assertEqual(first_engagement["campaign_movement_id"], first_campaign["id"])
            self.assertEqual(first_engagement["campaign_front_history_id"], first_front["id"])
            self.assertEqual(first_engagement["battle_cell_ids"], first_campaign["path_cell_ids"])
            self.assertEqual(first_engagement["battle_cell_count"], len(first_engagement["battle_cell_ids"]))
            self.assertEqual(first_engagement["step_count"], len(first_engagement["steps"]))
            self.assertGreaterEqual(first_engagement["initial_region_a_force"], first_engagement["final_region_a_force"])
            self.assertGreaterEqual(first_engagement["initial_region_b_force"], first_engagement["final_region_b_force"])
            self.assertGreaterEqual(first_engagement["total_attrition_loss_population"], 0.0)
            for key in ("max_front_pressure_index", "mean_counter_maneuver_index", "mean_supply_contest_index"):
                self.assertGreaterEqual(first_engagement[key], 0.0)
                self.assertLessEqual(first_engagement[key], 1.0)
            first_tactical_step = first_engagement["steps"][0]
            self.assertIn("region_a_force_estimate", first_tactical_step)
            self.assertIn("region_b_force_estimate", first_tactical_step)
            self.assertIn("region_a_supply_integrity_index", first_tactical_step)
            self.assertIn("region_b_supply_integrity_index", first_tactical_step)
            self.assertIn("front_pressure_index", first_tactical_step)
            self.assertIn("counter_maneuver_index", first_tactical_step)
            self.assertIn("supply_contest_index", first_tactical_step)
            self.assertIn("encirclement_risk_index", first_tactical_step)
            self.assertIn("withdrawal_pressure_index", first_tactical_step)
            self.assertIn("control_region_id", first_tactical_step)
            self.assertIn("control_balance_index", first_tactical_step)
            self.assertEqual(first_tactical_step["sequence_index"], 0)
            self.assertEqual(first_tactical_step["cell_id"], first_engagement["battle_cell_ids"][0])
            self.assertIn(first_tactical_step["control_region_id"], {first_engagement["region_a"], first_engagement["region_b"]})
            self.assertGreaterEqual(first_tactical_step["region_a_force_estimate"], 0.0)
            self.assertGreaterEqual(first_tactical_step["region_b_force_estimate"], 0.0)
            self.assertGreaterEqual(first_tactical_step["attrition_loss_population"], 0.0)
            for key in (
                "region_a_supply_integrity_index",
                "region_b_supply_integrity_index",
                "front_pressure_index",
                "counter_maneuver_index",
                "supply_contest_index",
                "encirclement_risk_index",
                "withdrawal_pressure_index",
                "control_balance_index",
            ):
                self.assertGreaterEqual(first_tactical_step[key], 0.0)
                self.assertLessEqual(first_tactical_step[key], 1.0)

            self.assertTrue(world["strategic_campaign_plans"])
            first_plan = world["strategic_campaign_plans"][0]
            self.assertIn("conflict_id", first_plan)
            self.assertIn("campaign_movement_id", first_plan)
            self.assertIn("campaign_front_history_id", first_plan)
            self.assertIn("tactical_engagement_id", first_plan)
            self.assertIn("primary_region_id", first_plan)
            self.assertIn("counter_region_id", first_plan)
            self.assertIn("primary_axis_cell_ids", first_plan)
            self.assertIn("counter_axis_cell_ids", first_plan)
            self.assertIn("decisive_cell_ids", first_plan)
            self.assertIn("decision_points", first_plan)
            self.assertEqual(first_plan["campaign_movement_id"], first_campaign["id"])
            self.assertEqual(first_plan["campaign_front_history_id"], first_front["id"])
            self.assertEqual(first_plan["tactical_engagement_id"], first_engagement["id"])
            self.assertEqual(first_plan["primary_axis_cell_ids"], first_campaign["path_cell_ids"])
            self.assertEqual(first_plan["counter_axis_cell_ids"], list(reversed(first_campaign["path_cell_ids"])))
            self.assertEqual(first_plan["primary_axis_cell_count"], len(first_plan["primary_axis_cell_ids"]))
            self.assertEqual(first_plan["counter_axis_cell_count"], len(first_plan["counter_axis_cell_ids"]))
            self.assertEqual(first_plan["decisive_cell_count"], len(first_plan["decisive_cell_ids"]))
            self.assertEqual(first_plan["decision_point_count"], len(first_plan["decision_points"]))
            self.assertGreaterEqual(first_plan["primary_force_allocation_population"], 0.0)
            self.assertGreaterEqual(first_plan["counter_force_allocation_population"], 0.0)
            self.assertGreaterEqual(first_plan["reserve_force_population"], 0.0)
            self.assertGreaterEqual(first_plan["expected_campaign_duration_days"], 0.0)
            self.assertGreaterEqual(first_plan["counter_mobilization_days"], 0.0)
            self.assertTrue(first_plan["strategic_posture"])
            self.assertIsInstance(first_plan["independent_counter_campaign_planned"], bool)
            for key in (
                "reserve_fraction",
                "primary_logistics_score",
                "counter_logistics_score",
                "counter_campaign_viability_index",
                "strategic_initiative_index",
                "escalation_risk_index",
                "operational_complexity_index",
                "plan_confidence_index",
            ):
                self.assertGreaterEqual(first_plan[key], 0.0)
                self.assertLessEqual(first_plan[key], 1.0)
            first_decision = first_plan["decision_points"][0]
            self.assertIn("path_index", first_decision)
            self.assertIn("plan_phase", first_decision)
            self.assertIn("trigger_pressure_index", first_decision)
            self.assertIn("counter_maneuver_priority_index", first_decision)
            self.assertIn("supply_risk_index", first_decision)
            self.assertEqual(first_decision["sequence_index"], 0)
            self.assertEqual(first_decision["cell_id"], first_plan["primary_axis_cell_ids"][first_decision["path_index"]])
            self.assertTrue(first_decision["plan_phase"])
            for key in ("trigger_pressure_index", "counter_maneuver_priority_index", "supply_risk_index"):
                self.assertGreaterEqual(first_decision[key], 0.0)
                self.assertLessEqual(first_decision[key], 1.0)

        first_calibration = world["calibration_checks"][0]
        self.assertIn("dataset", first_calibration)
        self.assertIn("layer", first_calibration)
        self.assertIn("metric", first_calibration)
        self.assertIn("value", first_calibration)
        self.assertIn("target_min", first_calibration)
        self.assertIn("target_max", first_calibration)
        self.assertIn("score", first_calibration)
        self.assertIn("passed", first_calibration)

        external_report = evaluate_calibration_targets(
            world,
            [
                {
                    "dataset": "custom_etopo",
                    "layer": "relief_bathymetry",
                    "metric": "ocean_fraction",
                    "target_min": 0.60,
                    "target_max": 0.80,
                    "source": "unit_test_range",
                },
                {
                    "dataset": "custom_worldclim",
                    "layer": "climate",
                    "metric": "not_exported_metric",
                    "target_min": 0.0,
                    "target_max": 1.0,
                },
            ],
        )
        self.assertEqual(external_report["summary"]["external_calibration_check_count"], 2)
        self.assertEqual(external_report["summary"]["external_calibration_evaluated_metric_count"], 1)
        self.assertEqual(external_report["summary"]["external_calibration_pass_count"], 1)
        self.assertEqual(external_report["summary"]["external_calibration_missing_metric_count"], 1)
        self.assertEqual(external_report["summary"]["external_calibration_metric_coverage_fraction"], 0.5)
        self.assertEqual(external_report["summary"]["external_calibration_evaluated_pass_fraction"], 1.0)
        self.assertFalse(external_report["summary"]["external_calibration_complete"])
        self.assertEqual(external_report["missing_world_metrics"], ["not_exported_metric"])
        self.assertTrue(external_report["checks"][0]["passed"])
        self.assertTrue(external_report["checks"][1]["missing_metric"])

        contract_targets = derive_calibration_targets(
            load_calibration_sources(Path("configs/calibration_sources.example.json"))
        )["targets"]
        contract_report = evaluate_calibration_targets(world, contract_targets)
        self.assertEqual(contract_report["summary"]["external_calibration_check_count"], 4)
        self.assertEqual(contract_report["summary"]["external_calibration_evaluated_metric_count"], 4)
        self.assertEqual(contract_report["summary"]["external_calibration_missing_metric_count"], 0)
        self.assertEqual(contract_report["summary"]["external_calibration_metric_coverage_fraction"], 1.0)
        self.assertTrue(contract_report["summary"]["external_calibration_complete"])
        self.assertFalse(contract_report["missing_world_metrics"])

        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "world.svg"
            write_svg_map(output, world, width=640, height=320, projection="mollweide", labels=True, max_cells=160)
            svg = output.read_text(encoding="utf-8")
            self.assertIn("<svg", svg)
            self.assertIn('data-projection="mollweide"', svg)
            self.assertIn('data-renderer="terrain-v1"', svg)
            self.assertIn('data-contours="true"', svg)

            raster_output = Path(tmpdir) / "world.ppm"
            write_raster_map(
                raster_output,
                world,
                width=320,
                height=160,
                projection="mollweide",
                max_cells=160,
                texture=True,
            )
            ppm = raster_output.read_bytes()
            self.assertTrue(ppm.startswith(b"P6\n# magic-geo raster-terrain-v1"))
            header_end = ppm.index(b"\n255\n") + len(b"\n255\n")
            self.assertIn(b"320 160", ppm[:header_end])
            self.assertEqual(len(ppm) - header_end, 320 * 160 * 3)
            self.assertIn('class="terrain-cell"', svg)
            self.assertIn('class="terrain-contours"', svg)
            self.assertIn('class="terrain-contour ', svg)
            self.assertIn("terrain-soften", svg)
            self.assertIn("<circle", svg)
            self.assertIn("<text", svg)
            if world["sacred_areas"]:
                self.assertIn("<polygon", svg)

    def test_lake_overflow_history_smoke(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["run"]["seed"] = 424200
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 10
        data["erosion"]["iterations"] = 1
        overflow_config = type(config).model_validate(data)

        world = generate_world(overflow_config)
        summary = world["summary"]

        self.assertGreater(len(world["lake_basins"]), 0)
        simulated_lake_basins = [
            basin for basin in world["lake_basins"] if basin["lake_cell_count"] > 0
        ]
        self.assertTrue(simulated_lake_basins)
        self.assertEqual(
            summary["simulated_lake_basin_count"], len(simulated_lake_basins)
        )
        self.assertEqual(summary["lake_overflow_history_count"], len(world["lake_overflow_histories"]))
        self.assertEqual(
            {history["lake_basin_id"] for history in world["lake_overflow_histories"]},
            {basin["id"] for basin in simulated_lake_basins},
        )
        self.assertEqual(
            summary["lake_overflow_history_step_count"],
            len(world["lake_overflow_histories"]) * summary["lake_overflow_simulation_years"],
        )
        self.assertAlmostEqual(
            summary["lake_overflow_total_spill_km3"],
            sum(history["total_spill_km3"] for history in world["lake_overflow_histories"]),
            delta=max(1.0, summary["lake_overflow_total_spill_km3"] * 0.0001),
        )
        first_history = world["lake_overflow_histories"][0]
        self.assertEqual(first_history["time_step_count"], summary["lake_overflow_simulation_years"])
        self.assertEqual(len(first_history["steps"]), summary["lake_overflow_simulation_years"])
        self.assertIn("overflow_path_cell_ids", first_history)
        previous_end = None
        for index, step in enumerate(first_history["steps"]):
            self.assertEqual(step["year"], index + 1)
            self.assertGreaterEqual(step["start_volume_km3"], 0.0)
            self.assertGreaterEqual(step["inflow_km3"], 0.0)
            self.assertGreaterEqual(step["evaporation_loss_km3"], 0.0)
            self.assertGreaterEqual(step["spill_volume_km3"], 0.0)
            self.assertGreaterEqual(step["sink_loss_km3"], 0.0)
            self.assertGreaterEqual(step["end_volume_km3"], 0.0)
            self.assertGreaterEqual(step["fill_fraction"], 0.0)
            self.assertGreaterEqual(step["avulsion_risk"], 0.0)
            self.assertLessEqual(step["avulsion_risk"], 1.0)
            self.assertAlmostEqual(
                step["start_volume_km3"]
                + step["inflow_km3"]
                - step["evaporation_loss_km3"]
                - step["spill_volume_km3"]
                - step["sink_loss_km3"],
                step["end_volume_km3"],
                delta=max(1.0, step["end_volume_km3"] * 0.0001),
            )
            if previous_end is not None:
                self.assertAlmostEqual(step["start_volume_km3"], previous_end, delta=max(1.0, previous_end * 0.0001))
            previous_end = step["end_volume_km3"]

        self.assertGreater(len(world["lake_overflow_channel_histories"]), 0)
        self.assertEqual(
            summary["lake_overflow_channel_history_count"],
            len(world["lake_overflow_channel_histories"]),
        )
        self.assertEqual(
            summary["lake_overflow_channel_step_count"],
            sum(history["time_step_count"] for history in world["lake_overflow_channel_histories"]),
        )
        self.assertAlmostEqual(
            summary["lake_overflow_total_channel_incision_m"],
            sum(history["total_incision_m"] for history in world["lake_overflow_channel_histories"]),
            delta=max(0.001, summary["lake_overflow_total_channel_incision_m"] * 0.0001),
        )
        first_channel = world["lake_overflow_channel_histories"][0]
        self.assertIn("lake_basin_id", first_channel)
        self.assertIn("overflow_path_cell_ids", first_channel)
        self.assertIn("channel_segment_count", first_channel)
        self.assertIn("channel_length_km", first_channel)
        self.assertIn("path_drop_m", first_channel)
        self.assertIn("bed_slope", first_channel)
        self.assertIn("total_incision_m", first_channel)
        self.assertIn("final_incision_depth_m", first_channel)
        self.assertIn("total_sediment_evacuated_km3", first_channel)
        self.assertIn("max_stream_power_index", first_channel)
        self.assertEqual(first_channel["channel_segment_count"], len(first_channel["overflow_path_cell_ids"]) - 1)
        self.assertEqual(first_channel["time_step_count"], len(first_channel["steps"]))
        self.assertGreater(first_channel["channel_length_km"], 0.0)
        self.assertGreaterEqual(first_channel["bed_slope"], 0.0)
        previous_incision = None
        for index, step in enumerate(first_channel["steps"]):
            self.assertEqual(step["year"], index + 1)
            self.assertGreaterEqual(step["start_incision_depth_m"], 0.0)
            self.assertGreaterEqual(step["spill_volume_km3"], 0.0)
            self.assertGreaterEqual(step["stream_power_index"], 0.0)
            self.assertLessEqual(step["stream_power_index"], 1.0)
            self.assertGreaterEqual(step["incision_m"], 0.0)
            self.assertGreaterEqual(step["bank_widening_m"], 0.0)
            self.assertGreaterEqual(step["sediment_evacuated_km3"], 0.0)
            self.assertGreaterEqual(step["end_incision_depth_m"], 0.0)
            self.assertGreaterEqual(step["avulsion_risk"], 0.0)
            self.assertLessEqual(step["avulsion_risk"], 1.0)
            self.assertAlmostEqual(
                step["start_incision_depth_m"] + step["incision_m"],
                step["end_incision_depth_m"],
                delta=max(0.001, step["end_incision_depth_m"] * 0.0001),
            )
            if previous_incision is not None:
                self.assertAlmostEqual(
                    step["start_incision_depth_m"],
                    previous_incision,
                    delta=max(0.001, previous_incision * 0.0001),
                )
            previous_incision = step["end_incision_depth_m"]

        non_lake_basin = next(
            basin for basin in world["lake_basins"] if basin["lake_cell_count"] == 0
        )
        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "world.json"
            runner = CliRunner()

            world_path.write_text(json.dumps(world), encoding="utf-8")
            valid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            simulated_lake_basins[0]["lake_cell_count"] += 1
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrology depression components or lake basin aggregation invalid",
                invalid_result.output,
            )
            simulated_lake_basins[0]["lake_cell_count"] -= 1

            contributing_cell = next(
                cell
                for cell in world["cells"]
                if cell["lake_basin_id"] >= 0
                and cell["depression_component_id"] < 0
            )
            original_lake_basin_id = contributing_cell["lake_basin_id"]
            contributing_cell["lake_basin_id"] = -1
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "hydrology depression components or lake basin aggregation invalid",
                invalid_result.output,
            )
            contributing_cell["lake_basin_id"] = original_lake_basin_id

            summary["simulated_lake_basin_count"] += 1
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "simulated_lake_basin_count does not match basins with lake cells",
                invalid_result.output,
            )
            summary["simulated_lake_basin_count"] -= 1

            original_history_basin_id = first_history["lake_basin_id"]
            first_history["lake_basin_id"] = non_lake_basin["id"]
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "lake_overflow_histories do not match basins with lake cells",
                invalid_result.output,
            )
            first_history["lake_basin_id"] = original_history_basin_id

    def test_orbital_eccentricity_affects_insolation_variability(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        circular_data = config.model_dump(mode="python")
        circular_data["mesh"]["cell_count"] = 128
        circular_data["tectonics"]["plate_count"] = 6
        circular_data["erosion"]["iterations"] = 1
        circular_data["planet"]["orbital_eccentricity"] = 0.0
        circular = type(config).model_validate(circular_data)

        eccentric_data = config.model_dump(mode="python")
        eccentric_data["mesh"]["cell_count"] = 128
        eccentric_data["tectonics"]["plate_count"] = 6
        eccentric_data["erosion"]["iterations"] = 1
        eccentric_data["planet"]["orbital_eccentricity"] = 0.20
        eccentric = type(config).model_validate(eccentric_data)

        circular_world = generate_world(circular)
        eccentric_world = generate_world(eccentric)

        self.assertAlmostEqual(circular_world["summary"]["orbital_eccentricity"], 0.0, delta=0.001)
        self.assertAlmostEqual(eccentric_world["summary"]["orbital_eccentricity"], 0.20, delta=0.001)
        self.assertGreater(
            eccentric_world["summary"]["mean_orbital_distance_factor"],
            circular_world["summary"]["mean_orbital_distance_factor"],
        )
        self.assertGreater(
            eccentric_world["summary"]["mean_orbital_insolation_variability_index"],
            circular_world["summary"]["mean_orbital_insolation_variability_index"],
        )
        self.assertAlmostEqual(circular_world["climate_energy_balance_records"][0]["orbital_eccentricity"], 0.0, delta=0.001)
        self.assertAlmostEqual(eccentric_world["climate_energy_balance_records"][0]["orbital_eccentricity"], 0.20, delta=0.001)

    def test_native_thermal_forcing_scales_moisture_temperature_and_runoff(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))

        def forced_world(stellar_luminosity: float, greenhouse_factor: float) -> dict:
            data = config.model_dump(mode="python")
            data["mesh"]["cell_count"] = 128
            data["tectonics"]["plate_count"] = 8
            data["erosion"]["iterations"] = 0
            data["planet"]["stellar_luminosity"] = stellar_luminosity
            data["planet"]["greenhouse_factor"] = greenhouse_factor
            forced = type(config).model_validate(data)
            return generate_native_world(config_to_native(forced))

        cold_world = forced_world(0.55, 0.55)
        earth_world = forced_world(1.0, 1.0)
        hot_world = forced_world(1.45, 1.45)
        minimum_capacity_world = forced_world(0.011, 0.0)
        maximum_capacity_world = forced_world(100.0, 10.0)

        def area_mean(world: dict, field: str, *, land_only: bool = False) -> float:
            cells = [
                cell
                for cell in world["cells"]
                if not land_only or not cell["is_water"]
            ]
            total_area = sum(cell["area_km2"] for cell in cells)
            return sum(cell[field] * cell["area_km2"] for cell in cells) / total_area

        cold_temperature = area_mean(cold_world, "temperature_c")
        earth_temperature = area_mean(earth_world, "temperature_c")
        hot_temperature = area_mean(hot_world, "temperature_c")
        cold_precipitation = area_mean(
            cold_world, "precipitation_mm_y", land_only=True
        )
        earth_precipitation = area_mean(
            earth_world, "precipitation_mm_y", land_only=True
        )
        hot_precipitation = area_mean(
            hot_world, "precipitation_mm_y", land_only=True
        )
        cold_runoff = area_mean(cold_world, "runoff_mm_y", land_only=True)
        earth_runoff = area_mean(earth_world, "runoff_mm_y", land_only=True)

        self.assertLess(cold_temperature, earth_temperature - 8.0)
        self.assertGreater(hot_temperature, earth_temperature + 7.0)
        self.assertLess(cold_precipitation, earth_precipitation * 0.80)
        self.assertGreater(hot_precipitation, earth_precipitation * 1.20)
        self.assertLess(cold_runoff, earth_runoff * 0.85)

        cold_model = cold_world["climate_model"]
        earth_model = earth_world["climate_model"]
        hot_model = hot_world["climate_model"]
        self.assertEqual(
            earth_model["thermal_moisture_capacity_model"],
            "bounded_exponential_global_temperature_anomaly_v1",
        )
        self.assertEqual(earth_model["thermal_moisture_capacity_factor"], 1.0)
        self.assertLess(
            cold_model["thermal_moisture_capacity_factor"],
            earth_model["thermal_moisture_capacity_factor"],
        )
        self.assertGreater(
            hot_model["thermal_moisture_capacity_factor"],
            earth_model["thermal_moisture_capacity_factor"],
        )
        self.assertEqual(
            minimum_capacity_world["climate_model"]["thermal_moisture_capacity_factor"],
            earth_model["thermal_moisture_capacity_min_factor"],
        )
        self.assertEqual(
            maximum_capacity_world["climate_model"]["thermal_moisture_capacity_factor"],
            earth_model["thermal_moisture_capacity_max_factor"],
        )
        for world in (cold_world, earth_world, hot_world):
            model = world["climate_model"]
            self.assertGreaterEqual(
                model["thermal_moisture_capacity_factor"],
                model["thermal_moisture_capacity_min_factor"],
            )
            self.assertLessEqual(
                model["thermal_moisture_capacity_factor"],
                model["thermal_moisture_capacity_max_factor"],
            )
            for cell in world["cells"]:
                self.assertAlmostEqual(
                    cell["precipitation_mm_y"],
                    sum(cell["precipitation_monthly_mm"]),
                    delta=0.002,
                )

    def test_native_uses_atmosphere_pressure_parameter(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 256
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1

        low_pressure = type(config).model_validate(data)
        high_pressure_data = config.model_dump(mode="python")
        high_pressure_data["mesh"]["cell_count"] = 256
        high_pressure_data["tectonics"]["plate_count"] = 8
        high_pressure_data["erosion"]["iterations"] = 1
        high_pressure_data["planet"]["atmosphere_pressure_bar"] = 2.0
        high_pressure = type(config).model_validate(high_pressure_data)

        low_world = generate_world(low_pressure)
        high_world = generate_world(high_pressure)

        low_mean_temp = sum(cell["temperature_c"] for cell in low_world["cells"]) / len(low_world["cells"])
        high_mean_temp = sum(cell["temperature_c"] for cell in high_world["cells"]) / len(high_world["cells"])

        self.assertGreater(high_mean_temp, low_mean_temp)

    def test_base_temperature_is_area_mean_normalized(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        baseline_data = config.model_dump(mode="python")
        baseline_data["mesh"]["cell_count"] = 256
        baseline_data["tectonics"]["plate_count"] = 8
        baseline_data["erosion"]["iterations"] = 0
        baseline = type(config).model_validate(baseline_data)

        warmer_data = config.model_dump(mode="python")
        warmer_data["mesh"]["cell_count"] = 256
        warmer_data["tectonics"]["plate_count"] = 8
        warmer_data["erosion"]["iterations"] = 0
        warmer_data["climate"]["base_temperature_c"] = 20.0
        warmer = type(config).model_validate(warmer_data)

        baseline_world = generate_world(baseline)
        warmer_world = generate_world(warmer)
        baseline_mean = sum(cell["temperature_c"] for cell in baseline_world["cells"]) / len(
            baseline_world["cells"]
        )
        warmer_mean = sum(cell["temperature_c"] for cell in warmer_world["cells"]) / len(
            warmer_world["cells"]
        )

        self.assertAlmostEqual(baseline_mean, baseline.climate.base_temperature_c, delta=0.02)
        self.assertAlmostEqual(warmer_mean - baseline_mean, 5.0, delta=0.01)
        self.assertEqual(
            baseline_world["climate_model"]["base_temperature_interpretation"],
            "post_centered_local_adjustment_global_area_mean_c",
        )

    def test_zero_precipitation_scale_is_a_true_dry_boundary(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 0
        data["climate"]["precipitation_scale"] = 0.0

        world = generate_world(type(config).model_validate(data))
        land = [cell for cell in world["cells"] if not cell["is_water"]]

        self.assertTrue(land)
        self.assertEqual(
            world["climate_model"]["zero_precipitation_scale_behavior"],
            "exact_zero_monthly_and_annual_precipitation",
        )
        self.assertEqual(
            world["climate_model"][
                "positive_precipitation_pre_thermal_annual_floor_mm"
            ],
            20.0,
        )
        self.assertAlmostEqual(
            world["climate_model"][
                "positive_precipitation_effective_annual_floor_mm"
            ],
            20.0
            * world["climate_model"]["thermal_moisture_capacity_factor"],
        )
        self.assertTrue(
            all(cell["precipitation_mm_y"] == 0.0 for cell in world["cells"])
        )
        self.assertTrue(
            all(
                monthly == 0.0
                for cell in world["cells"]
                for monthly in cell["precipitation_monthly_mm"]
            )
        )
        self.assertTrue(all(cell["runoff_mm_y"] == 0.0 for cell in land))
        self.assertTrue(
            all(cell["actual_evapotranspiration_mm_y"] == 0.0 for cell in land)
        )
        self.assertTrue(all(cell["infiltration_mm_y"] == 0.0 for cell in land))

    def test_subtropical_drying_strength_reduces_horse_latitude_rainfall(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        dry_data = config.model_dump(mode="python")
        dry_data["mesh"]["cell_count"] = 256
        dry_data["tectonics"]["plate_count"] = 8
        dry_data["erosion"]["iterations"] = 0
        dry = type(config).model_validate(dry_data)

        no_drying_data = config.model_dump(mode="python")
        no_drying_data["mesh"]["cell_count"] = 256
        no_drying_data["tectonics"]["plate_count"] = 8
        no_drying_data["erosion"]["iterations"] = 0
        no_drying_data["climate"]["subtropical_drying_strength"] = 0.0
        no_drying = type(config).model_validate(no_drying_data)

        dry_world = generate_world(dry)
        no_drying_world = generate_world(no_drying)

        def mean_land_precipitation(world: dict, minimum_lat: float, maximum_lat: float) -> float:
            values = [
                cell["precipitation_mm_y"]
                for cell in world["cells"]
                if not cell["is_water"] and minimum_lat <= abs(cell["lat_deg"]) <= maximum_lat
            ]
            self.assertTrue(values)
            return sum(values) / len(values)

        dry_subtropical = mean_land_precipitation(dry_world, 20.0, 40.0)
        wet_subtropical = mean_land_precipitation(no_drying_world, 20.0, 40.0)
        dry_equatorial = mean_land_precipitation(dry_world, 0.0, 10.0)
        wet_equatorial = mean_land_precipitation(no_drying_world, 0.0, 10.0)

        self.assertLess(dry_subtropical, wet_subtropical * 0.75)
        self.assertGreater(dry_equatorial, wet_equatorial * 0.95)
        seasonal_tropical_land = [
            cell
            for cell in dry_world["cells"]
            if not cell["is_water"] and 10.0 <= abs(cell["lat_deg"]) <= 25.0
        ]
        self.assertTrue(
            any(
                max(cell["precipitation_monthly_mm"])
                - min(cell["precipitation_monthly_mm"])
                >= 100.0
                and cell["dry_season_months"] >= 2
                and cell["wet_season_months"] >= 3
                for cell in seasonal_tropical_land
            )
        )
        self.assertEqual(dry_world["climate_model"]["subtropical_drying_strength"], 0.65)
        self.assertEqual(no_drying_world["climate_model"]["subtropical_drying_strength"], 0.0)

    def test_earthlike_reference_closes_ocean_and_snapshot_ledgers(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        world = generate_world(config)

        coast_check = next(
            check
            for check in world["calibration_checks"]
            if check["metric"] == "coastal_land_fraction"
        )
        land_cells = [cell for cell in world["cells"] if not cell["is_water"]]
        cells_by_id = {cell["id"]: cell for cell in world["cells"]}
        coastal_land_cells = [
            cell
            for cell in land_cells
            if any(cells_by_id[neighbor_id]["is_water"] for neighbor_id in cell["neighbors"])
        ]
        continental_landmasses = [
            landmass
            for landmass in world["landmasses"]
            if landmass["island_class"] == "continent"
        ]
        eligible_watersheds = [
            watershed
            for watershed in world["watersheds"]
            if watershed["centroid_lat_deg"] >= -60.0
        ]
        eligible_endorheic = [
            watershed
            for watershed in eligible_watersheds
            if watershed["is_endorheic"]
        ]
        endorheic_count_fraction = len(eligible_endorheic) / len(eligible_watersheds)
        endorheic_area_fraction = sum(
            watershed["area_km2"] for watershed in eligible_endorheic
        ) / sum(watershed["area_km2"] for watershed in eligible_watersheds)
        elevations = [cell["elevation_m"] for cell in world["cells"]]
        nonnegative_elevations = [elevation for elevation in elevations if elevation >= 0.0]
        below_sea_level_fraction = sum(elevation < 0.0 for elevation in elevations) / len(elevations)
        mean_nonnegative_elevation = sum(nonnegative_elevations) / len(nonnegative_elevations)
        surface_elevation_span = max(elevations) - min(elevations)
        mean_land_temperature = sum(
            sum(cell["temperature_monthly_c"]) / 12.0 for cell in land_cells
        ) / len(land_cells)
        mean_land_temperature_range = sum(
            max(cell["temperature_monthly_c"]) - min(cell["temperature_monthly_c"])
            for cell in land_cells
        ) / len(land_cells)
        mean_land_precipitation = sum(
            cell["precipitation_mm_y"] for cell in land_cells
        ) / len(land_cells)
        exorheic_backbone_hack_relation = fit_power_law(
            (
                (watershed["area_km2"], watershed["main_channel_length_km"])
                for watershed in world["watersheds"]
                if not watershed["is_endorheic"]
                and watershed["outlet_type"] == "ocean"
                and watershed["area_km2"] >= HACK_FIT_MINIMUM_BASIN_AREA_KM2
                and watershed["main_channel_length_km"] > 0.0
            )
        )
        ocean_volume_km3 = sum(
            cell["area_km2"] * cell["water_depth_m"] / 1000.0
            for cell in world["cells"]
            if cell["is_water"]
        )

        self.assertTrue(coast_check["passed"])
        self.assertAlmostEqual(coast_check["value"], 0.3506, places=4)
        self.assertEqual(coast_check["value"], round(len(coastal_land_cells) / len(land_cells), 4))
        self.assertAlmostEqual(
            ocean_volume_km3,
            config.planet.ocean_water_inventory_km3,
            delta=max(0.001, config.planet.ocean_water_inventory_km3 * 0.0000000001),
        )
        self.assertAlmostEqual(
            world["summary"]["ocean_volume_km3"],
            config.planet.ocean_water_inventory_km3,
            delta=max(0.001, config.planet.ocean_water_inventory_km3 * 0.0000000001),
        )
        self.assertGreater(len(land_cells) - len(coastal_land_cells), len(coastal_land_cells))
        self.assertEqual(len(continental_landmasses), 1)
        self.assertEqual(world["summary"]["marine_region_count"], 1)
        self.assertEqual(world["summary"]["inland_sea_marine_region_count"], 0)
        self.assertGreater(world["sea_level_model"]["below_sea_level_land_cell_count"], 0)
        self.assertAlmostEqual(below_sea_level_fraction, 0.610595703125)
        self.assertAlmostEqual(mean_nonnegative_elevation, 1191.352558191878)
        self.assertAlmostEqual(surface_elevation_span, 17443.550462964195)
        self.assertAlmostEqual(mean_land_temperature, 6.834819370070568)
        self.assertAlmostEqual(mean_land_temperature_range, 16.894286363636365)
        self.assertAlmostEqual(mean_land_precipitation, 808.9630832503113)
        self.assertAlmostEqual(endorheic_count_fraction, 0.09872611464968153)
        self.assertAlmostEqual(endorheic_area_fraction, 0.27494236382566906)
        self.assertEqual(
            world["summary"]["equal_filled_raw_downhill_reroute_count"],
            sum(
                1
                for cell in world["cells"]
                if cell["equal_filled_raw_downhill_rerouted"]
            ),
        )
        self.assertEqual(
            world["summary"]["equal_filled_raw_downhill_reroute_count"],
            37,
        )
        self.assertEqual(world["summary"]["hydrologic_surface_conditioned_cell_count"], 159)
        self.assertEqual(world["summary"]["equal_filled_flow_edge_count"], 159)
        self.assertEqual(world["summary"]["raw_uphill_flow_edge_count"], 61)
        self.assertEqual(world["summary"]["non_downhill_hydrologic_flow_edge_count"], 0)
        self.assertAlmostEqual(
            world["summary"]["max_hydrologic_surface_adjustment_m"],
            0.009,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["max_raw_uphill_flow_step_m"],
            294.194115,
            places=6,
        )
        self.assertEqual(world["summary"]["river_count"], 90)
        self.assertEqual(world["summary"]["terminal_land_sink_count"], 31)
        self.assertEqual(world["summary"]["depression_component_count"], 67)
        self.assertEqual(world["summary"]["depression_component_cell_count"], 190)
        self.assertEqual(world["summary"]["preserved_geologic_depression_count"], 24)
        self.assertEqual(world["summary"]["corrected_numeric_depression_count"], 0)
        self.assertEqual(world["summary"]["temporary_numeric_lake_depression_count"], 43)
        self.assertEqual(world["summary"]["numeric_depression_fill_pass_count"], 8)
        self.assertEqual(world["summary"]["numeric_depression_correction_event_count"], 423)
        self.assertEqual(world["summary"]["numeric_depression_fill_event_count"], 0)
        self.assertEqual(
            world["summary"]["numeric_depression_fill_cell_application_count"],
            0,
        )
        self.assertEqual(
            world["summary"]["numeric_depression_filled_unique_cell_count"],
            0,
        )
        self.assertAlmostEqual(
            world["summary"]["numeric_depression_fill_volume_km3"],
            0.0,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["max_numeric_depression_fill_depth_m"],
            0.0,
            places=6,
        )
        self.assertEqual(
            world["summary"]["numeric_depression_temporary_lake_event_count"],
            414,
        )
        self.assertEqual(
            world["summary"][
                "numeric_depression_temporary_lake_cell_application_count"
            ],
            1319,
        )
        self.assertEqual(
            world["summary"]["numeric_depression_temporary_lake_unique_cell_count"],
            364,
        )
        self.assertAlmostEqual(
            world["summary"][
                "numeric_depression_temporary_lake_candidate_volume_km3"
            ],
            160279744.39471412,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["numeric_depression_fill_candidate_volume_km3"],
            160324045.20873812,
            places=6,
        )
        self.assertEqual(
            world["summary"]["numeric_depression_breach_feasible_event_count"],
            423,
        )
        self.assertEqual(
            world["summary"]["numeric_depression_breach_lower_volume_event_count"],
            200,
        )
        self.assertEqual(
            world["summary"]["numeric_depression_breach_selected_event_count"],
            9,
        )
        self.assertAlmostEqual(
            world["summary"][
                "numeric_depression_selected_breach_excavation_volume_km3"
            ],
            44280.1606333465,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"][
                "numeric_depression_selected_breach_deposition_volume_km3"
            ],
            44280.1606333465,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["numeric_depression_correction_mass_balance_residual_km3"],
            0.0,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"][
                "numeric_depression_lower_volume_hybrid_adjustment_volume_km3"
            ],
            107274976.53566435,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["numeric_depression_lower_volume_hybrid_saved_fraction"],
            0.3308865405,
            places=9,
        )
        self.assertAlmostEqual(
            world["summary"]["max_lower_volume_breach_excavation_depth_m"],
            7373.4943361403,
            places=6,
        )
        self.assertEqual(
            world["fluvial_sediment_routing_model"]["stage_count"],
            6,
        )
        self.assertEqual(
            world["summary"]["fluvial_sediment_active_cell_step_count"],
            8255,
        )
        self.assertEqual(
            world["summary"]["fluvial_sediment_routed_edge_count"],
            5853,
        )
        self.assertEqual(
            world["summary"]["fluvial_sediment_terminal_allocation_count"],
            562,
        )
        self.assertAlmostEqual(
            world["summary"]["fluvial_sediment_local_source_volume_km3"],
            3596043.7381699905,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["fluvial_sediment_routed_throughput_volume_km3"],
            4229456.213875525,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["fluvial_sediment_total_deposition_volume_km3"],
            1289535.3066713898,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["fluvial_sediment_terminal_export_volume_km3"],
            2306508.4314986006,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"][
                "fluvial_sediment_depression_fill_deposition_volume_km3"
            ],
            687110.1119446529,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"][
                "fluvial_sediment_terminal_land_deposition_volume_km3"
            ],
            124191.6245509268,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["fluvial_sediment_marine_deposition_volume_km3"],
            330887.026547524,
            places=6,
        )
        self.assertLessEqual(
            world["summary"]["fluvial_sediment_mass_balance_residual_km3"],
            0.000001,
        )
        self.assertEqual(world["summary"]["hillslope_sediment_transport_stage_count"], 6)
        self.assertEqual(world["summary"]["hillslope_sediment_transport_edge_count"], 40643)
        self.assertEqual(world["summary"]["hillslope_sediment_source_cell_stage_count"], 8822)
        self.assertEqual(world["summary"]["hillslope_sediment_target_cell_stage_count"], 11915)
        self.assertEqual(world["summary"]["hillslope_sediment_land_to_land_edge_count"], 31468)
        self.assertEqual(world["summary"]["hillslope_sediment_land_to_marine_edge_count"], 9175)
        self.assertEqual(world["summary"]["hillslope_sediment_unique_source_cell_count"], 1716)
        self.assertEqual(world["summary"]["hillslope_sediment_unique_target_cell_count"], 2280)
        self.assertAlmostEqual(
            world["summary"]["hillslope_sediment_production_volume_km3"],
            70141984.2713684,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["hillslope_sediment_deposition_volume_km3"],
            70141984.2713684,
            places=6,
        )
        self.assertLessEqual(
            world["summary"]["hillslope_sediment_mass_balance_residual_km3"],
            0.000001,
        )
        self.assertEqual(world["summary"]["glacial_sediment_transport_stage_count"], 1)
        self.assertEqual(world["summary"]["glacial_sediment_transfer_count"], 182)
        self.assertEqual(world["summary"]["glacial_sediment_source_cell_count"], 182)
        self.assertEqual(world["summary"]["glacial_sediment_target_cell_count"], 115)
        self.assertEqual(
            world["summary"]["glacial_sediment_land_target_transfer_count"],
            130,
        )
        self.assertEqual(
            world["summary"]["glacial_sediment_marine_target_transfer_count"],
            52,
        )
        self.assertAlmostEqual(
            world["summary"]["glacial_sediment_production_volume_km3"],
            155651.0453599108,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["glacial_sediment_deposition_volume_km3"],
            155651.0453599108,
            places=6,
        )
        self.assertLessEqual(
            world["summary"]["glacial_sediment_mass_balance_residual_km3"],
            0.000001,
        )
        self.assertLessEqual(
            world["summary"][
                "glacial_sediment_terrain_volume_change_residual_km3"
            ],
            0.000001,
        )
        self.assertAlmostEqual(
            world["summary"]["sediment_budget_production_km3"],
            73937959.21553165,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["sediment_budget_deposition_km3"],
            71631450.78403312,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["sediment_budget_export_km3"],
            2306508.4314986,
            places=6,
        )
        self.assertLessEqual(
            world["summary"]["sediment_budget_residual_km3"],
            0.000001,
        )
        inventory_model = world["sediment_inventory_model"]
        self.assertEqual(
            inventory_model["model_type"],
            "finite_alluvium_bedrock_sediment_inventory_v1",
        )
        self.assertAlmostEqual(
            inventory_model["alluvium_entrainment_volume_km3"],
            11970592.382508822,
            places=6,
        )
        self.assertAlmostEqual(
            inventory_model["bedrock_erosion_volume_km3"],
            61967366.83302281,
            places=6,
        )
        self.assertAlmostEqual(
            inventory_model["final_mobile_sediment_inventory_volume_km3"],
            59660858.401524164,
            places=6,
        )
        self.assertLess(
            inventory_model["source_partition_residual_km3"], 0.000001
        )
        self.assertLess(
            inventory_model["inventory_mass_balance_residual_km3"], 0.000001
        )
        self.assertAlmostEqual(
            inventory_model["bedrock_erosion_volume_km3"],
            inventory_model["final_mobile_sediment_inventory_volume_km3"]
            + inventory_model["terminal_export_volume_km3"],
            delta=0.000001,
        )
        self.assertAlmostEqual(
            world["summary"]["sediment_final_inventory_volume_km3"],
            inventory_model["final_mobile_sediment_inventory_volume_km3"],
            delta=0.000001,
        )
        selected_breaches = [
            event
            for event in world["numeric_depression_fill_history"]
            if event["selected_correction_method"] == "mass_conserving_breach"
        ]
        self.assertEqual(len(selected_breaches), 9)
        for event in selected_breaches:
            for before_m, excavation_m, alluvium_m, bedrock_m in zip(
                event[
                    "breach_sediment_thickness_before_excavation_m_by_cell"
                ],
                event["breach_excavation_depth_m_by_cell"],
                event["breach_alluvium_entrainment_depth_m_by_cell"],
                event["breach_bedrock_erosion_depth_m_by_cell"],
                strict=True,
            ):
                self.assertAlmostEqual(
                    alluvium_m, min(before_m, excavation_m), places=8
                )
                self.assertAlmostEqual(
                    bedrock_m, excavation_m - alluvium_m, places=8
                )
        numeric_partition = inventory_model["process_source_partition"][
            "numeric_breach"
        ]
        self.assertAlmostEqual(
            numeric_partition["alluvium_entrainment_volume_km3"],
            23632.306551864,
            places=6,
        )
        self.assertAlmostEqual(
            numeric_partition["bedrock_erosion_volume_km3"],
            20647.8540814825,
            places=6,
        )
        self.assertEqual(world["summary"]["simulation_clock_stage_count"], 8)
        self.assertEqual(
            world["summary"]["simulation_clock_cryosphere_coupling_stage_count"],
            1,
        )
        self.assertEqual(world["summary"]["closed_depression_count"], 31)
        self.assertEqual(world["summary"]["simulated_lake_basin_count"], 44)
        self.assertEqual(world["summary"]["lake_overflow_history_count"], 44)
        self.assertEqual(world["summary"]["lake_overflow_history_step_count"], 528)
        self.assertEqual(world["summary"]["lake_overflow_channel_history_count"], 36)
        self.assertEqual(
            sum(basin["lake_cell_count"] for basin in world["lake_basins"]),
            113,
        )
        self.assertAlmostEqual(
            world["summary"]["lake_overflow_total_spill_km3"],
            381404.844533,
            places=6,
        )
        self.assertAlmostEqual(
            world["summary"]["lake_overflow_total_sink_loss_km3"],
            21242.471257,
            places=6,
        )
        self.assertEqual(
            world["summary"]["avoidable_equal_filled_raw_downhill_sink_count"],
            0,
        )
        self.assertEqual(world["summary"]["flow_cycle_cell_count"], 0)
        self.assertEqual(exorheic_backbone_hack_relation.observation_count, 19)
        self.assertAlmostEqual(
            exorheic_backbone_hack_relation.exponent,
            0.6135353290176452,
        )
        self.assertAlmostEqual(
            exorheic_backbone_hack_relation.log_rmse,
            0.16266273810550289,
        )
        self.assertEqual(
            world["summary"]["calibration_pass_count"],
            sum(check["passed"] for check in world["calibration_checks"]),
        )

    def test_geodesic_mesh_backend_smoke(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["backend"] = "geodesic_icosahedron"
        data["mesh"]["cell_count"] = 162
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        geodesic = type(config).model_validate(data)

        world = generate_world(geodesic)
        summary = world["summary"]

        self.assertEqual(world["mesh_backend"], "geodesic_icosahedron")
        self.assertEqual(summary["mesh_backend"], "geodesic_icosahedron")
        self.assertEqual(
            world["cell_area_model"],
            "spherical_barycentric_control_volume_v2",
        )
        self.assertEqual(
            summary["cell_area_model"],
            "spherical_barycentric_control_volume_v2",
        )
        self.assertEqual(summary["cell_count"], 162)
        self.assertEqual(len(world["cells"]), 162)
        cell_areas = [cell["area_km2"] for cell in world["cells"]]
        expected_surface_area = 4.0 * math.pi * data["planet"]["radius_km"] ** 2
        self.assertAlmostEqual(sum(cell_areas), expected_surface_area, delta=1.0)
        self.assertGreater(max(cell_areas), min(cell_areas) * 1.1)
        self.assertGreater(summary["cell_area_coefficient_of_variation"], 0.1)
        self.assertAlmostEqual(summary["surface_area_km2"], sum(cell_areas), delta=1.0)
        self.assertAlmostEqual(
            summary["ocean_fraction"],
            sum(
                cell["area_km2"] for cell in world["cells"] if cell["is_water"]
            )
            / sum(cell_areas),
            delta=0.0001,
        )
        self.assertAlmostEqual(
            summary["ocean_cell_fraction"],
            sum(1 for cell in world["cells"] if cell["is_water"]) / len(world["cells"]),
            delta=0.0001,
        )
        self.assertEqual(
            world["sea_level_model"]["model_type"],
            "volume_constrained_connectivity_ocean_flood_v3",
        )
        self.assertEqual(world["simulation_clock"]["configured_erosion_iteration_count"], 1)
        self.assertEqual(world["simulation_clock"]["stage_count"], 3)
        self.assertEqual(world["plate_kinematic_model"]["configured_motion_step_count"], 1)
        self.assertEqual(world["plate_kinematic_model"]["history_step_count"], 2)
        self.assertEqual(len(world["plate_motion_history"]), 2)
        self.assertTrue(world["earth_system_feedback_history"][1]["plate_motion_applied"])
        self.assertTrue(world["earth_system_feedback_history"][1]["crust_transport_applied"])
        self.assertTrue(world["earth_system_feedback_history"][1]["crust_evolution_applied"])
        self.assertEqual(len(world["fluvial_sediment_routing_history"]), 1)
        fluvial_model = world["fluvial_sediment_routing_model"]
        self.assertAlmostEqual(
            fluvial_model["total_local_source_volume_km3"],
            fluvial_model["total_deposition_volume_km3"]
            + fluvial_model["total_terminal_export_volume_km3"],
            delta=max(
                0.000001,
                fluvial_model["total_local_source_volume_km3"] * 1.0e-10,
            ),
        )
        routed_incoming_volume = sum(
            cell["fluvial_sediment_routed_incoming_m"]
            * cell["area_km2"]
            / 1000.0
            for cell in world["cells"]
        )
        routed_outgoing_volume = sum(
            cell["fluvial_sediment_routed_outgoing_m"]
            * cell["area_km2"]
            / 1000.0
            for cell in world["cells"]
        )
        self.assertAlmostEqual(
            routed_incoming_volume,
            routed_outgoing_volume,
            delta=0.001,
        )
        hillslope_model = world["hillslope_sediment_transport_model"]
        self.assertEqual(len(world["hillslope_sediment_transport_history"]), 1)
        self.assertGreater(hillslope_model["total_transport_edge_count"], 0)
        self.assertAlmostEqual(
            hillslope_model["total_production_volume_km3"],
            hillslope_model["total_deposition_volume_km3"],
            delta=max(
                0.000001,
                hillslope_model["total_production_volume_km3"] * 1.0e-10,
            ),
        )
        self.assertAlmostEqual(
            sum(
                cell["hillslope_sediment_production_m"]
                * cell["area_km2"]
                / 1000.0
                for cell in world["cells"]
            ),
            hillslope_model["total_production_volume_km3"],
            delta=0.01,
        )
        self.assertAlmostEqual(
            sum(
                cell["hillslope_sediment_deposition_m"]
                * cell["area_km2"]
                / 1000.0
                for cell in world["cells"]
            ),
            hillslope_model["total_deposition_volume_km3"],
            delta=0.01,
        )
        glacial_model = world["glacial_sediment_transport_model"]
        glacial_stage = world["glacial_sediment_transport_history"][0]
        self.assertGreater(glacial_stage["transfer_count"], 0)
        self.assertTrue(
            any(
                abs(transfer["source_area_km2"] - transfer["target_area_km2"])
                > 1.0
                for transfer in glacial_stage["transfers"]
            )
        )
        self.assertTrue(
            any(
                abs(
                    transfer["source_production_depth_m"]
                    - transfer["target_deposition_depth_m"]
                )
                > 0.000001
                for transfer in glacial_stage["transfers"]
                if abs(transfer["source_area_km2"] - transfer["target_area_km2"])
                > 1.0
            )
        )
        self.assertAlmostEqual(
            glacial_model["total_production_volume_km3"],
            glacial_model["total_deposition_volume_km3"],
            delta=max(
                0.000001,
                glacial_model["total_production_volume_km3"] * 1.0e-10,
            ),
        )
        inventory_model = world["sediment_inventory_model"]
        self.assertAlmostEqual(
            inventory_model["gross_mobilization_volume_km3"],
            inventory_model["alluvium_entrainment_volume_km3"]
            + inventory_model["bedrock_erosion_volume_km3"],
            delta=0.1,
        )
        self.assertAlmostEqual(
            inventory_model["bedrock_erosion_volume_km3"],
            inventory_model["final_mobile_sediment_inventory_volume_km3"]
            + inventory_model["terminal_export_volume_km3"],
            delta=0.1,
        )
        self.assertLess(inventory_model["inventory_mass_balance_residual_km3"], 0.1)
        for transfer in glacial_stage["transfers"]:
            self.assertAlmostEqual(
                transfer["source_production_depth_m"]
                * transfer["source_area_km2"],
                transfer["target_deposition_depth_m"]
                * transfer["target_area_km2"],
                delta=max(
                    0.001,
                    transfer["transfer_volume_km3"] * 1000.0 * 1.0e-7,
                ),
            )
        self.assertTrue(world["plate_kinematic_model"]["crust_advection_resolved"])
        self.assertTrue(world["plate_kinematic_model"]["mass_conserving_crust_transport"])
        self.assertEqual(
            [step["stage"] for step in world["earth_system_feedback_history"]],
            [
                "initial_climate_hydrology",
                "erosion_iteration",
                "cryosphere_coupling",
            ],
        )
        self.assertEqual(world["mesh_lod"]["index"], "cube_quadtree_v0")
        self.assertEqual(summary["mesh_lod_tile_count"], len(world["mesh_lod"]["tiles"]))
        self.assertEqual(len(world["cells"][0]["mesh_lod_tile_ids"]), summary["mesh_lod_level_count"])
        self.assertEqual(world["spherical_spatial_index"]["index"], "healpix_s2_compat_v0")
        self.assertEqual(summary["spherical_spatial_index"], "healpix_s2_compat_v0")
        self.assertEqual(
            summary["s2_like_occupied_cell_count"],
            len(world["spherical_spatial_index"]["s2_like_cells"]),
        )

        neighbor_sets = {cell["id"]: set(cell["neighbors"]) for cell in world["cells"]}
        self.assertTrue(all(5 <= len(neighbors) <= 6 for neighbors in neighbor_sets.values()))
        for cell_id, neighbors in neighbor_sets.items():
            for neighbor_id in neighbors:
                self.assertIn(cell_id, neighbor_sets[neighbor_id])
        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "geodesic.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            self.assertEqual(result.exit_code, 0, result.output)

            world["cell_area_model"] = "spherical_voronoi_control_volume_v1"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn(
                "native cell area model or spherical area closure invalid",
                result.output,
            )
