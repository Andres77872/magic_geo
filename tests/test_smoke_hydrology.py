"""Lakes, rivers, groundwater, and water budgets assertions for the generated world.

Split out of the former single-method smoke test: each method re-derives
what it needs from the shared world, so they no longer depend on order.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.api import generate_world
from magic_geo.cli import app
from magic_geo.config import load_config
from magic_geo.navigability_diagnostics import (
    enrich_world_with_navigability_diagnostics,
)
from magic_geo.port_sites import enrich_world_with_port_sites
from magic_geo.river_channel_morphology import (
    enrich_world_with_river_channel_morphology,
)
from magic_geo.river_hydraulics import enrich_world_with_river_hydraulics
from magic_geo.route_corridors import enrich_world_with_route_corridors

from support import worlds


class SmokeHydrologyTests(TestCase):
    def test_lake_basins(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
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
        self.assertEqual(summary["numeric_depression_correction_max_pass_count"], 16)
        self.assertAlmostEqual(
            summary["numeric_depression_fill_depth_tolerance_m"], 1.0e-9
        )
        fill_history = world["numeric_depression_correction_history"]
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
            summary["numeric_depression_temporary_lake_event_count"],
            len(temporary_lake_deferrals),
        )
        self.assertEqual(
            summary["numeric_depression_correction_pass_count"],
            len(
                {
                    (event["feedback_stage_id"], event["stabilization_pass"])
                    for event in fill_history
                }
            ),
        )
        temporary_lake_cell_ids = {
            cell_id
            for event in temporary_lake_deferrals
            for cell_id in event["cell_ids"]
        }
        self.assertEqual(
            summary["numeric_depression_temporary_lake_cell_application_count"],
            sum(event["cell_count"] for event in temporary_lake_deferrals),
        )
        self.assertEqual(
            summary["numeric_depression_temporary_lake_unique_cell_count"],
            len(temporary_lake_cell_ids),
        )
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
            self.assertNotIn("applied_fill_volume_km3", event)
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
            self.assertNotIn("cumulative_numeric_depression_fill_m", cell)
            self.assertNotIn("numeric_depression_fill_event_count", cell)
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
        self.assertEqual(
            summary["numeric_depression_correction_mass_balance_residual_km3"],
            0.0,
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
    def test_aquifer_systems(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        aquifer_cells = [cell for cell in world["cells"] if cell["aquifer_class"] != "marine_excluded"]
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
    def test_river_channel_systems(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        river_channel_cells = [cell for cell in world["cells"] if cell["is_river"] and not cell["is_water"]]
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
    def test_watersheds(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        first_cell = world["cells"][0]
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
    def test_causal_hydrologic_water_budget_replay_and_mutations(self) -> None:
        world = worlds.cached_world("coupled_128")
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
    def test_disabled_depression_preservation_keeps_geologic_evidence(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 512
        data["hydrology"]["preserve_geologic_depressions"] = False
        routed_config = type(config).model_validate(data)

        world = generate_world(routed_config)
        fill_history = world["numeric_depression_correction_history"]
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

            world["numeric_depression_correction_history"] = None
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(
                app, ["validate", "--world", str(world_path)]
            )
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "numeric depression correction provenance invalid",
                invalid_result.output,
            )
            world["numeric_depression_correction_history"] = fill_history

            filled_cell = world["cells"][first_event["cell_ids"][0]]
            self.assertNotIn("cumulative_numeric_depression_fill_m", filled_cell)
            filled_cell["cumulative_numeric_depression_fill_m"] = 0.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = runner.invoke(
                app, ["validate", "--world", str(world_path)]
            )
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn("world schema contains retired fields", invalid_result.output)
            del filled_cell["cumulative_numeric_depression_fill_m"]

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
