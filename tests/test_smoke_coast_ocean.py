"""Coasts, landmasses, and ocean circulation assertions for the generated world.

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
from magic_geo.scaling import HACK_FIT_MINIMUM_BASIN_AREA_KM2, fit_power_law

from support import worlds


class SmokeCoastOceanTests(TestCase):
    def test_sea_level_model(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        small = worlds.canonical_config("small_smoke")
        summary = world["summary"]
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
    def test_coastal_features(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
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
    def test_landmasses(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
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
    def test_landmasses_2(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        first_cell = world["cells"][0]
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
    def test_landmasses_3(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        first_cell = world["cells"][0]
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
        self.assertAlmostEqual(mean_land_precipitation, 808.9624364881694)
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
        self.assertEqual(world["summary"]["numeric_depression_correction_pass_count"], 8)
        self.assertEqual(world["summary"]["numeric_depression_correction_event_count"], 423)
        for retired_field in (
            "numeric_depression_fill_event_count",
            "numeric_depression_fill_cell_application_count",
            "numeric_depression_filled_unique_cell_count",
            "numeric_depression_fill_volume_km3",
            "max_numeric_depression_fill_depth_m",
        ):
            self.assertNotIn(retired_field, world["summary"])
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
            for event in world["numeric_depression_correction_history"]
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
