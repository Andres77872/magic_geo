import copy
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from typer.testing import CliRunner

from magic_geo.api import generate_world
from magic_geo.campaign_operations_validation import validate_campaign_operations_replay
from magic_geo.cell_geometry import enrich_world_with_cell_geometry
from magic_geo.cli import _validate_route_corridors, app
from magic_geo.config import WorldConfig, load_config
from magic_geo.logistics_history import enrich_world_with_logistics_history
from magic_geo.planet_parameters import (
    EARTH_STANDARD_GRAVITY_M_S2,
    planet_gravity_g,
    planet_parameter_snapshot,
    planet_radius_km,
)
from magic_geo.planet_realism import enrich_world_with_planet_realism
from magic_geo.river_hydraulics import enrich_world_with_river_hydraulics
from magic_geo.route_corridors import enrich_world_with_route_corridors


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
                return_value={
                    "cells": [],
                    "summary": {},
                    "planet_parameters": planet_parameter_snapshot(config.planet),
                },
            ),
            patch(
                "magic_geo.api.enrich_world_with_mesh_lod",
                side_effect=inspect_first_enricher,
            ),
            self.assertRaises(FirstEnricherObserved),
        ):
            generate_world(config)

    def test_planet_realism_rejects_native_config_snapshot_mismatch(self) -> None:
        config = WorldConfig.model_validate(
            {"planet": {"radius_km": 4200.123456789, "gravity_g": 0.55}}
        )
        world = {
            "cells": [],
            "planet_parameters": planet_parameter_snapshot(config.planet),
        }
        self.assertIs(enrich_world_with_planet_realism(world, config.planet), world)

        world["planet_parameters"]["radius_km"] += 1.0
        with self.assertRaisesRegex(ValueError, "must match the configured planet"):
            enrich_world_with_planet_realism(world, config.planet)

    def test_api_rejects_native_planet_snapshot_mismatch_before_enrichment(
        self,
    ) -> None:
        config = WorldConfig.model_validate(
            {"planet": {"radius_km": 4200.0, "gravity_g": 0.55}}
        )
        native_parameters = planet_parameter_snapshot(config.planet)
        native_parameters["radius_km"] = 4201.0

        with (
            patch(
                "magic_geo.native.generate_world",
                return_value={
                    "cells": [],
                    "summary": {},
                    "planet_parameters": native_parameters,
                },
            ),
            patch("magic_geo.api.enrich_world_with_mesh_lod") as first_enricher,
            self.assertRaisesRegex(RuntimeError, "do not match the configured planet"),
        ):
            generate_world(config)
        first_enricher.assert_not_called()

    def test_planet_scale_accessors_reject_invalid_world_parameters(self) -> None:
        for accessor, key in (
            (planet_radius_km, "radius_km"),
            (planet_gravity_g, "gravity_g"),
        ):
            invalid_cases = (
                ({}, "world must provide planet_parameters"),
                ({"planet_parameters": []}, "planet_parameters must be an object"),
                (
                    {"planet_parameters": {}},
                    rf"planet_parameters\.{key} is required",
                ),
                (
                    {"planet_parameters": {key: "1.0"}},
                    rf"planet_parameters\.{key} must be numeric",
                ),
                (
                    {"planet_parameters": {key: None}},
                    rf"planet_parameters\.{key} must be numeric",
                ),
                (
                    {"planet_parameters": {key: True}},
                    rf"planet_parameters\.{key} must be numeric",
                ),
                (
                    {"planet_parameters": {key: math.nan}},
                    rf"planet_parameters\.{key} must be finite and positive",
                ),
                (
                    {"planet_parameters": {key: math.inf}},
                    rf"planet_parameters\.{key} must be finite and positive",
                ),
                (
                    {"planet_parameters": {key: 0.0}},
                    rf"planet_parameters\.{key} must be finite and positive",
                ),
                (
                    {"planet_parameters": {key: -1.0}},
                    rf"planet_parameters\.{key} must be finite and positive",
                ),
            )
            for world, message in invalid_cases:
                with self.subTest(parameter=key, world=world):
                    with self.assertRaisesRegex(ValueError, message):
                        accessor(world)

    def test_cell_geometry_scales_with_configured_radius_and_rejects_missing_parameters(
        self,
    ) -> None:
        cells = [
            {"id": 0, "lat_deg": 35.26439, "lon_deg": 45.0, "neighbors": [1, 2, 3]},
            {"id": 1, "lat_deg": 35.26439, "lon_deg": -135.0, "neighbors": [0, 2, 3]},
            {"id": 2, "lat_deg": -35.26439, "lon_deg": 135.0, "neighbors": [0, 1, 3]},
            {"id": 3, "lat_deg": -35.26439, "lon_deg": -45.0, "neighbors": [0, 1, 2]},
        ]

        def world_for_radius(radius_km: float) -> dict:
            world = {
                "cells": copy.deepcopy(cells),
                "summary": {},
                "planet_parameters": {"radius_km": radius_km},
            }
            area_km2 = 4.0 * math.pi * radius_km**2 / len(cells)
            for cell in world["cells"]:
                cell["area_km2"] = area_km2
            return world

        small = world_for_radius(3000.0)
        large = world_for_radius(6000.0)
        for world in (small, large):
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
        missing_parameters = world_for_radius(6371.0)
        missing_parameters.pop("planet_parameters")
        with self.assertRaisesRegex(ValueError, "world must provide planet_parameters"):
            enrich_world_with_cell_geometry(missing_parameters)

    def test_route_corridors_scale_from_small_to_super_earth_and_replay(self) -> None:
        def world_for_radius(
            radius_km: float,
        ) -> dict:
            angular_distance = math.radians(12.0)
            world = {
                "cells": [
                    {
                        "id": 0,
                        "lat_deg": 0.0,
                        "lon_deg": 0.0,
                        "neighbors": [1],
                        "is_water": False,
                        "water_body_type": "land",
                    },
                    {
                        "id": 1,
                        "lat_deg": 0.0,
                        "lon_deg": 12.0,
                        "neighbors": [0],
                        "is_water": False,
                        "water_body_type": "land",
                    },
                ],
                "settlements": [
                    {"id": 0, "cell_id": 0, "region_id": 0},
                    {"id": 1, "cell_id": 1, "region_id": 1},
                ],
                "routes": [
                    {
                        "id": 0,
                        "from": 0,
                        "to": 1,
                        "type": "overland",
                        "distance_km": radius_km * angular_distance,
                    }
                ],
                "summary": {},
                "planet_parameters": {"radius_km": radius_km},
            }
            return world

        small = world_for_radius(3000.0)
        super_earth = world_for_radius(9000.0)
        for world in (small, super_earth):
            enrich_world_with_route_corridors(world)
            cells_by_id = {cell["id"]: cell for cell in world["cells"]}
            self.assertEqual(
                _validate_route_corridors(world, world["summary"], cells_by_id),
                [],
            )

        self.assertEqual(small["route_corridor_model"]["planet_radius_km"], 3000.0)
        self.assertEqual(
            super_earth["route_corridor_model"]["planet_radius_km"],
            9000.0,
        )
        self.assertAlmostEqual(
            super_earth["route_corridors"][0]["path_length_km"]
            / small["route_corridors"][0]["path_length_km"],
            3.0,
            places=5,
        )
        missing_parameters = world_for_radius(6371.0)
        missing_parameters.pop("planet_parameters")
        with self.assertRaisesRegex(ValueError, "world must provide planet_parameters"):
            enrich_world_with_route_corridors(missing_parameters)

    def test_campaign_distances_scale_from_small_to_super_earth_and_replay(
        self,
    ) -> None:
        def world_for_radius(
            radius_km: float,
        ) -> dict:
            angular_distance = math.radians(12.0)
            distance_km = radius_km * angular_distance
            world = {
                "political_regions": [
                    {"id": 0, "capital_settlement_id": 0},
                    {"id": 1, "capital_settlement_id": 1},
                ],
                "settlements": [
                    {"id": 0, "cell_id": 0, "region_id": 0},
                    {"id": 1, "cell_id": 1, "region_id": 1},
                ],
                "routes": [
                    {
                        "id": 0,
                        "from": 0,
                        "to": 1,
                        "type": "overland",
                        "distance_km": distance_km,
                        "cost": distance_km * 1.2,
                    }
                ],
                "trade_flows": [
                    {
                        "id": 0,
                        "route_id": 0,
                        "from": 0,
                        "to": 1,
                        "region_from": 0,
                        "region_to": 1,
                        "distance_km": distance_km,
                        "volume_index": 20.0,
                        "friction": 0.2,
                        "interregional": True,
                    }
                ],
                "conflicts": [
                    {
                        "id": 0,
                        "region_a": 0,
                        "region_b": 1,
                        "region_a_force_estimate": 12000.0,
                        "region_b_force_estimate": 9000.0,
                        "outcome": "region_a_victory",
                        "contested_cell_id": 1,
                        "intensity": 0.4,
                        "war_duration_years": 2.0,
                    }
                ],
                "cells": [
                    {
                        "id": 0,
                        "lat_deg": 0.0,
                        "lon_deg": 0.0,
                        "neighbors": [1],
                        "political_region_id": 0,
                        "is_water": False,
                        "elevation_m": 100.0,
                    },
                    {
                        "id": 1,
                        "lat_deg": 0.0,
                        "lon_deg": 12.0,
                        "neighbors": [0],
                        "political_region_id": 1,
                        "is_water": False,
                        "elevation_m": 100.0,
                    },
                ],
                "borders": [
                    {
                        "id": 0,
                        "region_a": 0,
                        "region_b": 1,
                        "barrier_score": 0.2,
                        "length_km": distance_km,
                    }
                ],
                "economy_histories": [],
                "summary": {},
                "planet_parameters": {"radius_km": radius_km},
            }
            return world

        small = world_for_radius(3000.0)
        super_earth = world_for_radius(9000.0)
        for world in (small, super_earth):
            enrich_world_with_logistics_history(world)
            self.assertEqual(validate_campaign_operations_replay(world), [])

        self.assertAlmostEqual(
            super_earth["campaign_movements"][0]["path_length_km"]
            / small["campaign_movements"][0]["path_length_km"],
            3.0,
            places=5,
        )
        self.assertAlmostEqual(
            super_earth["campaign_path_segments"][0]["distance_km"]
            / small["campaign_path_segments"][0]["distance_km"],
            3.0,
            places=5,
        )
        missing_parameters = copy.deepcopy(small)
        missing_parameters.pop("planet_parameters")
        self.assertEqual(
            validate_campaign_operations_replay(missing_parameters),
            [
                "campaign operations replay rejected: world must provide "
                "planet_parameters"
            ],
        )
        with self.assertRaisesRegex(ValueError, "world must provide planet_parameters"):
            enrich_world_with_logistics_history(missing_parameters)

    def test_river_hydraulics_uses_configured_gravity_and_rejects_missing_parameters(
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
        earth = copy.deepcopy(base_world)
        earth["planet_parameters"] = {"gravity_g": 1.0}
        low_gravity = copy.deepcopy(base_world)
        low_gravity["planet_parameters"] = {"gravity_g": 0.25}
        for world in (earth, low_gravity):
            enrich_world_with_river_hydraulics(world)

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
        with self.assertRaisesRegex(ValueError, "world must provide planet_parameters"):
            enrich_world_with_river_hydraulics(copy.deepcopy(base_world))

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
