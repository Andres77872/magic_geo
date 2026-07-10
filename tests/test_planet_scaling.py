import copy
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from typer.testing import CliRunner

from magic_geo.api import generate_world
from magic_geo.cell_geometry import enrich_world_with_cell_geometry
from magic_geo.cli import app
from magic_geo.config import WorldConfig, load_config
from magic_geo.planet_parameters import EARTH_RADIUS_KM, EARTH_STANDARD_GRAVITY_M_S2
from magic_geo.river_hydraulics import enrich_world_with_river_hydraulics


class PlanetScalingTests(TestCase):
    def test_api_exposes_configured_planet_before_first_enricher(self) -> None:
        config = WorldConfig.model_validate(
            {"planet": {"radius_km": 4200.0, "gravity_g": 0.55}}
        )

        class FirstEnricherObserved(Exception):
            pass

        def inspect_first_enricher(world: dict) -> None:
            self.assertEqual(world["planet_parameters"]["radius_km"], 4200.0)
            self.assertEqual(world["planet_parameters"]["gravity_g"], 0.55)
            raise FirstEnricherObserved

        with (
            patch(
                "magic_geo.native.generate_world",
                return_value={"cells": [], "summary": {}},
            ),
            patch(
                "magic_geo.api.enrich_world_with_mesh_lod",
                side_effect=inspect_first_enricher,
            ),
            self.assertRaises(FirstEnricherObserved),
        ):
            generate_world(config)

    def test_cell_geometry_scales_with_configured_radius_and_legacy_defaults_to_earth(
        self,
    ) -> None:
        cells = [
            {"id": 0, "lat_deg": 35.26439, "lon_deg": 45.0, "neighbors": [1, 2, 3]},
            {"id": 1, "lat_deg": 35.26439, "lon_deg": -135.0, "neighbors": [0, 2, 3]},
            {"id": 2, "lat_deg": -35.26439, "lon_deg": 135.0, "neighbors": [0, 1, 3]},
            {"id": 3, "lat_deg": -35.26439, "lon_deg": -45.0, "neighbors": [0, 1, 2]},
        ]

        def world_for_radius(radius_km: float, *, expose_parameters: bool = True) -> dict:
            world = {
                "cells": copy.deepcopy(cells),
                "summary": {},
            }
            area_km2 = 4.0 * math.pi * radius_km**2 / len(cells)
            for cell in world["cells"]:
                cell["area_km2"] = area_km2
            if expose_parameters:
                world["planet_parameters"] = {"radius_km": radius_km}
            return world

        small = world_for_radius(3000.0)
        large = world_for_radius(6000.0)
        legacy = world_for_radius(EARTH_RADIUS_KM, expose_parameters=False)
        explicit_earth = world_for_radius(EARTH_RADIUS_KM)
        for world in (small, large, legacy, explicit_earth):
            enrich_world_with_cell_geometry(world)

        self.assertAlmostEqual(
            large["cell_adjacency_edges"][0]["great_circle_distance_km"]
            / small["cell_adjacency_edges"][0]["great_circle_distance_km"],
            2.0,
            places=5,
        )
        self.assertAlmostEqual(
            large["cells"][0]["cell_polygon_area_km2"]
            / small["cells"][0]["cell_polygon_area_km2"],
            4.0,
            places=5,
        )
        self.assertEqual(legacy["cell_adjacency_edges"], explicit_earth["cell_adjacency_edges"])
        self.assertEqual(
            legacy["summary"]["cell_geometry_total_area_km2"],
            explicit_earth["summary"]["cell_geometry_total_area_km2"],
        )

    def test_river_hydraulics_uses_configured_gravity_and_legacy_defaults_to_earth(
        self,
    ) -> None:
        base_world = {
            "cells": [
                {
                    "id": 0,
                    "is_river": True,
                    "is_water": False,
                    "river_channel_width_m": 90.0,
                    "river_channel_depth_m": 3.5,
                    "bankfull_discharge_m3_s": 620.0,
                    "channel_slope_index": 0.18,
                    "channel_morphology_class": "deep_alluvial_channel",
                    "river_channel_system_id": -1,
                }
            ],
            "river_channel_systems": [],
            "summary": {},
        }
        legacy = copy.deepcopy(base_world)
        earth = copy.deepcopy(base_world)
        earth["planet_parameters"] = {"gravity_g": 1.0}
        low_gravity = copy.deepcopy(base_world)
        low_gravity["planet_parameters"] = {"gravity_g": 0.25}
        for world in (legacy, earth, low_gravity):
            enrich_world_with_river_hydraulics(world)

        self.assertEqual(legacy["cells"], earth["cells"])
        self.assertEqual(
            legacy["river_hydraulics_model"],
            earth["river_hydraulics_model"],
        )
        self.assertEqual(legacy["summary"], earth["summary"])
        self.assertAlmostEqual(
            low_gravity["river_hydraulics_model"]["gravity_m_s2"],
            EARTH_STANDARD_GRAVITY_M_S2 * 0.25,
        )
        self.assertAlmostEqual(
            low_gravity["cells"][0]["froude_number"]
            / earth["cells"][0]["froude_number"],
            2.0,
            places=5,
        )
        self.assertAlmostEqual(
            low_gravity["cells"][0]["bed_shear_stress_pa"]
            / earth["cells"][0]["bed_shear_stress_pa"],
            0.25,
            places=5,
        )

    def test_non_earth_generation_passes_strict_natural_model_replays(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1
        data["planet"]["radius_km"] = 3200.0
        data["planet"]["gravity_g"] = 0.4
        world = generate_world(type(config).model_validate(data))

        self.assertEqual(world["river_channel_morphology_model"]["planet_radius_km"], 3200.0)
        self.assertAlmostEqual(
            world["river_hydraulics_model"]["gravity_m_s2"],
            EARTH_STANDARD_GRAVITY_M_S2 * 0.4,
        )
        first_edge = world["cell_adjacency_edges"][0]
        first = world["cells"][first_edge["cell_a_id"]]
        second = world["cells"][first_edge["cell_b_id"]]
        first_lat = math.radians(first["lat_deg"])
        second_lat = math.radians(second["lat_deg"])
        delta_lon = math.radians(second["lon_deg"] - first["lon_deg"])
        expected_edge_distance = 3200.0 * math.acos(
            max(
                -1.0,
                min(
                    1.0,
                    math.sin(first_lat) * math.sin(second_lat)
                    + math.cos(first_lat) * math.cos(second_lat) * math.cos(delta_lon),
                ),
            )
        )
        self.assertAlmostEqual(
            first_edge["great_circle_distance_km"],
            expected_edge_distance,
            delta=max(0.001, expected_edge_distance * 0.0001),
        )

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "non_earth_world.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
        self.assertEqual(result.exit_code, 0, result.output)
