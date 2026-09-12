"""Mesh, schema, and planet-scale assertions for the generated world.

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

from magic_geo.api import backend_info, generate_world
from magic_geo.cli import app
from magic_geo.config import load_config

from support import cryosphere_worlds, worlds
from support.cli import assert_no_cli_crash


class SmokeCoreMeshTests(TestCase):
    def test_schema_version(self) -> None:
        world = worlds.cached_world("small_smoke")
        small = worlds.canonical_config("small_smoke")
        world = worlds.cached_world("small_smoke")
        self.assertEqual(world["schema_version"], 2)
        summary = world["summary"]
    def test_simulation_clock(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        small = worlds.canonical_config("small_smoke")
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
                "mean_erosion_rate_m_per_step" not in step
                for step in feedback_history
            )
        )
        self.assertNotIn("legacy_mean_erosion_rate_field_semantics", clock)
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
                == step["numeric_depression_correction_pass_count"] + 1
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
    def test_planet_parameters(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        feedback_history = world["earth_system_feedback_history"]
        erosion_steps = feedback_history[1:3]
        cryosphere_step = feedback_history[-1]
        motion_history = world["plate_motion_history"]
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
    def test_mesh_lod(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        first_cell = world["cells"][0]
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
    def test_cell_adjacency_edges(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        first_fault_system = world["fault_systems"][0]
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
    def test_backend_info_has_native_core(self) -> None:
        info = backend_info()

        self.assertEqual(info["native_core"], "c++20")
        self.assertIn("opencl_loader_found", info)
    def test_underresolved_plate_domains_fail_explicitly(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 64
        data["erosion"]["iterations"] = 6
        underresolved = type(config).model_validate(data)

        with self.assertRaisesRegex(RuntimeError, "nearest-center plate domain became empty"):
            generate_world(underresolved)
    def test_coupled_ocean_fraction_configuration_validates_end_to_end(self) -> None:
        """A tectonics/climate-coupled seed still passes the whole ``validate`` gate.

        The tampered side of every check this configuration reaches is asserted
        through the same command by the exhaustive ``validate`` tier
        (``test_validate_cli_core_hydrology``, ``_clock_tectonics``,
        ``_climate_cryosphere`` and ``_natural_systems``), which matches whole
        ``FAIL`` lines and guards against a check raising instead of reporting.
        What only this configuration proves is that the coupled regime itself --
        a non-default ocean fraction target with a single erosion iteration --
        generates a world the command accepts.
        """

        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        data["planet"]["ocean_fraction_target"] = 0.33203125
        world = generate_world(type(config).model_validate(data))

        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "world.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])

        self.assertIsNone(result.exception)
        self.assertEqual(result.exit_code, 0, result.output)

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
        # The current seasonal Earthlike witness has no mobilized glacial
        # sediment. Keep that zero control separate from the cold positive case.
        self.assertEqual(glacial_stage["transfer_count"], 0)
        self.assertEqual(glacial_stage["transfers"], [])
        for key in ("production_volume_km3", "deposition_volume_km3"):
            self.assertEqual(glacial_stage[key], 0.0)
            self.assertEqual(glacial_model["total_" + key], 0.0)
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

    def test_cold_geodesic_glacial_transport_conserves_unequal_area_volumes(self) -> None:
        # The shipped cryogenic forcing supplies actual ice; one erosion
        # iteration preserves the coupled terrain/clock branch on unequal cells.
        world = cryosphere_worlds.cached_cold_geodesic_world_readonly("full_world")
        self.assertEqual(world["mesh_backend"], "geodesic_icosahedron")
        self.assertEqual(len(world["cells"]), 162)
        self.assertEqual(world["simulation_clock"]["configured_erosion_iteration_count"], 1)
        self.assertGreater(world["summary"]["cell_area_coefficient_of_variation"], 0.1)
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
        self.assertEqual(glacial_stage["feedback_stage_id"], 2)
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
        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "cold-geodesic.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            assert_no_cli_crash(self, result, command="validate")
            self.assertEqual(result.exit_code, 0, result.output)
