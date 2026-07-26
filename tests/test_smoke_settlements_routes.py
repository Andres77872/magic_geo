"""Settlements, routes, ports, and politics assertions for the generated world.

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

from magic_geo.api import generate_world
from magic_geo.cli import app
from magic_geo.config import load_config

from support import worlds
from support.cli import assert_no_cli_crash


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
    def test_validate_reports_every_river_and_coastal_replay_verdict(self) -> None:
        """``validate`` reaches and reports all five river/coastal replays.

        The 128-cell topology is too coarse to guarantee a port and a corridor
        witness, so this fixture is generated at 256 cells; that regime, and the
        wiring of these five replays into the public command, are what only this
        test proves. The field-by-field tamper tables live in
        ``test_water_validators`` (channel morphology, hydraulics, navigability)
        and ``test_human_validators`` (port sites, route corridors), which call
        the validators directly and can name the field that diverged.
        """

        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 256
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        data["climate"]["lapse_rate_c_per_km"] = 4.0
        world = generate_world(type(config).model_validate(data))

        self.assertTrue(
            [cell for cell in world["cells"] if cell["is_river"] and not cell["is_water"]]
        )
        for model_key, model_type in (
            (
                "river_channel_morphology_model",
                "causal_flow_sediment_wetland_baseflow_channel_morphology_v1",
            ),
            ("river_hydraulics_model", "manning_blended_diagnostic_river_hydraulics_v1"),
            (
                "navigability_model",
                "causal_channel_hydraulic_coastal_navigability_v1",
            ),
            (
                "port_site_model",
                "causal_navigability_coastal_port_site_selection_v1",
            ),
            (
                "route_corridor_model",
                "causal_feature_weighted_dijkstra_route_corridors_v1",
            ),
        ):
            with self.subTest(model=model_key):
                self.assertEqual(world[model_key]["model_type"], model_type)

        runner = CliRunner()
        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"

            def validate_current() -> Result:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            control = validate_current()
            assert_no_cli_crash(self, control, command="validate")
            self.assertEqual(control.exit_code, 0, control.output)

            world["river_channel_morphology_model"]["slope_normalization"] += 0.001
            world["river_hydraulics_model"]["gravity_m_s2"] += 0.1
            world["navigability_model"]["navigable_threshold"] += 0.01
            world["port_site_model"]["port_site_threshold"] += 0.01
            world["route_corridor_model"]["feature_threshold"] += 0.01

            result = validate_current()

        assert_no_cli_crash(self, result, command="validate")
        self.assertEqual(result.exit_code, 1, result.output)
        for message in (
            "river channel morphology model or causal replay invalid",
            "river hydraulics model or causal replay invalid",
            "navigability model or causal replay invalid",
            "port site model or causal replay invalid",
            "route corridor model or causal replay invalid",
        ):
            with self.subTest(message=message):
                self.assertIn(message, result.output)

    def test_two_settlement_regime_generates_a_valid_settlement_and_route_network(
        self,
    ) -> None:
        """A 256-cell seed above the two-settlement threshold validates end to end.

        Both replays this fixture reaches are already driven through the public
        command by
        ``test_human_validators.test_public_validate_wires_every_extracted_human_validator``,
        which tampers every human model descriptor in one pass and asserts each
        verdict line. What is left for this test is the regime itself: a mesh
        coarse enough to be cheap yet fine enough to select more than one
        settlement and route between them.
        """

        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 256
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        # Keep this fixture above the two-settlement threshold. Earth
        # calibration is covered independently by the canonical matrix.
        data["climate"]["lapse_rate_c_per_km"] = 2.0
        world = generate_world(type(config).model_validate(data))

        self.assertEqual(
            world["settlement_selection_model"]["model_type"],
            "causal_native_score_local_max_separated_settlement_selection_v1",
        )
        self.assertEqual(world["settlement_selection_model"]["selection_score_precision"], 8)
        self.assertEqual(
            world["route_network_model"]["model_type"],
            "causal_endpoint_barrier_ranked_route_network_v1",
        )
        self.assertGreater(len(world["settlements"]), 1)
        self.assertTrue(world["routes"])

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])

        assert_no_cli_crash(self, result, command="validate")
        self.assertEqual(result.exit_code, 0, result.output)

    def test_political_models_declare_their_documented_identities(self) -> None:
        """Region, border and trade-flow models name their documented replays.

        Every verdict these three replays can report is driven through the public
        command by
        ``test_human_validators.test_public_validate_wires_every_extracted_human_validator``,
        and each replay's tamper table lives in ``test_human_validators`` beside
        it, so nothing here needs to re-run the command.
        """

        world = worlds.cached_world_readonly("mid_512")

        for model_key, model_type in (
            (
                "political_region_model",
                "causal_capital_barrier_partition_political_regions_v1",
            ),
            (
                "political_border_model",
                "causal_adjacent_region_terrain_border_segments_v1",
            ),
            ("trade_flow_model", "causal_route_endpoint_complement_trade_flows_v1"),
        ):
            with self.subTest(model=model_key):
                self.assertEqual(world[model_key]["model_type"], model_type)

        for family in ("political_regions", "borders", "trade_flows"):
            with self.subTest(family=family):
                self.assertTrue(world[family], family)
