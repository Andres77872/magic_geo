"""Settlements, routes, ports, and politics assertions for the generated world.

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

from support import worlds


class SmokeSettlementsRoutesTests(TestCase):
    def test_borders(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
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
    def test_navigable_waterways(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        navigable_candidate_ids = {cell["id"] for cell in world["cells"] if cell["navigability_index"] >= 0.52}
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
    def test_port_sites(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        first_cell = world["cells"][0]
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
        self.assertNotIn("sediment_production_m", first_cell)
        self.assertIn("sediment_deposition_m", first_cell)
        self.assertIn("sediment_export_m", first_cell)
        self.assertIn("sediment_net_budget_m", first_cell)
        self.assertIn("sediment_alluvium_entrainment_m", first_cell)
        self.assertIn("sediment_bedrock_erosion_m", first_cell)
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
        world = worlds.cached_world("mid_512")
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
