"""Calibration and artifact exports assertions for the generated world.

Split out of the former single-method smoke test: each method re-derives
what it needs from the shared world, so they no longer depend on order.
"""

from __future__ import annotations

import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from magic_geo.calibration import (
    derive_calibration_targets,
    evaluate_calibration_targets,
    load_calibration_sources,
)
from magic_geo.io import (
    write_cells_csv,
    write_raster_map,
    write_summary_markdown,
    write_svg_map,
)

from support import worlds


class SmokeExportsTests(TestCase):
    def test_calibration_checks(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
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
                    "crust_thickness_km": 7.0,
                    "crust_density": 3.0,
                    "cumulative_tectonic_elevation_change_m": 18.5,
                    "oceanic_crust_aging_event_count": 1,
                    "oceanic_crust_rejuvenation_event_count": 2,
                    "oceanic_crust_subduction_event_count": 1,
                    "cumulative_crust_transport_distance_km": 314.5,
                    "hydrologic_surface_elevation_m": 412.125,
                    "hydrologic_flow_drop_m": 0.001,
                    "hydrologic_flow_slope": 0.0000000025,
                    "hydrologic_surface_conditioned": True,
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
                "mean_plate_cumulative_rotation_deg": 3.25,
                "numeric_depression_correction_model": (
                    "bounded_mass_conserving_breach_or_zero_material_temporary_lake_with_coupled_recomputation_v3"
                ),
                "numeric_depression_correction_selection_model": (
                    "lower_volume_full_cell_breach_with_50m_depth_bound_else_temporary_lake_v3"
                ),
                "numeric_depression_correction_event_count": 2,
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
            self.assertEqual(row["cumulative_tectonic_elevation_change_m"], "18.5")
            self.assertNotIn("initial_crust_age_ma", fieldnames)
            self.assertNotIn("initial_crust_thickness_km", fieldnames)
            self.assertNotIn("initial_crust_density", fieldnames)
            self.assertNotIn("initial_thermal_subsidence_m", fieldnames)
            self.assertNotIn("last_crust_source_cell_id", fieldnames)
            self.assertNotIn("crust_source_remap_event_count", fieldnames)
            self.assertEqual(row["cumulative_crust_transport_distance_km"], "314.5")
            self.assertEqual(row["hydrologic_surface_elevation_m"], "412.125")
            self.assertEqual(row["hydrologic_flow_drop_m"], "0.001")
            self.assertEqual(row["hydrologic_flow_slope"], "2.5e-09")
            self.assertEqual(row["hydrologic_surface_conditioned"], "True")
            self.assertNotIn("cumulative_numeric_depression_fill_m", fieldnames)
            self.assertNotIn("numeric_depression_fill_event_count", fieldnames)
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
            self.assertNotIn("sediment_production_m", fieldnames)
            self.assertEqual(fieldnames.index("glacial_sediment_deposition_m"), 362)
            self.assertEqual(fieldnames.index("fluvial_sediment_local_source_m"), 364)
            self.assertEqual(fieldnames.index("fluvial_sediment_routing_event_count"), 373)
            self.assertEqual(fieldnames.index("hillslope_sediment_production_m"), 374)
            self.assertEqual(fieldnames.index("hillslope_sediment_deposition_m"), 375)
            self.assertEqual(fieldnames.index("hillslope_sediment_net_m"), 376)
            self.assertEqual(
                fieldnames.index("hillslope_sediment_outgoing_edge_count"), 377
            )
            self.assertEqual(
                fieldnames.index("hillslope_sediment_incoming_edge_count"), 378
            )
            self.assertEqual(fieldnames.index("glacial_sediment_production_m"), 379)
            self.assertEqual(fieldnames.index("glacial_sediment_net_m"), 380)
            self.assertEqual(
                fieldnames.index("glacial_sediment_outgoing_transfer_count"),
                381,
            )
            self.assertEqual(
                fieldnames.index("glacial_sediment_incoming_transfer_count"),
                382,
            )
            self.assertEqual(
                fieldnames.index("sediment_alluvium_entrainment_m"), 383
            )
            self.assertEqual(fieldnames.index("sediment_bedrock_erosion_m"), 384)
            self.assertEqual(
                fieldnames.index(
                    "hydrologic_potential_evapotranspiration_mm_y"
                ),
                385,
            )
            self.assertEqual(
                fieldnames.index(
                    "groundwater_recharge_source_infiltration_mm_y"
                ),
                386,
            )
            self.assertEqual(
                fieldnames.index("groundwater_recharge_fraction"), 387
            )
            self.assertEqual(
                fieldnames.index("vadose_zone_retention_mm_y"), 388
            )
            self.assertEqual(
                fieldnames.index("vadose_zone_retention_km3_y"), 389
            )
            self.assertEqual(
                fieldnames.index(
                    "groundwater_recharge_mass_balance_residual_mm_y"
                ),
                390,
            )
            self.assertEqual(
                fieldnames.index("groundwater_lateral_inflow_km3_y"),
                391,
            )
            self.assertEqual(
                fieldnames.index("groundwater_available_volume_km3_y"),
                392,
            )
            self.assertEqual(
                fieldnames.index(
                    "groundwater_internal_lateral_outflow_km3_y"
                ),
                393,
            )
            self.assertEqual(
                fieldnames.index("groundwater_retained_storage_km3_y"),
                394,
            )
            self.assertEqual(
                fieldnames.index(
                    "groundwater_flow_mass_balance_residual_km3_y"
                ),
                395,
            )
            summary_text = summary_path.read_text(encoding="utf-8")
            self.assertIn("`plate_motion_history_step_count`: 3", summary_text)
            self.assertIn("`mean_plate_cumulative_rotation_deg`: 3.25", summary_text)
            self.assertIn(
                "`numeric_depression_correction_event_count`: 2", summary_text
            )
            self.assertIn(
                "`numeric_depression_breach_lower_volume_event_count`: 1",
                summary_text,
            )
            self.assertIn(
                "`simulation_clock_cryosphere_coupling_stage_count`: 1",
                summary_text,
            )
            self.assertIn("`glacial_sediment_transfer_count`: 12", summary_text)
