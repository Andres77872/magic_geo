"""Cross-layer invariants at the native hydrology/environment/society boundary."""

from __future__ import annotations

from unittest import TestCase

from magic_geo.config import config_to_native
from magic_geo.native import generate_world
from magic_geo.settlement_routes import _candidate_count

from support.worlds import build_config


class NativeSurfaceCoherenceTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.worlds = [
            generate_world(
                config_to_native(
                    build_config(
                        **{
                            "run.seed": seed,
                            "mesh.cell_count": 512,
                            "tectonics.plate_count": 8,
                            "erosion.iterations": 1,
                            "climate.precipitation_scale": precipitation_scale,
                        }
                    )
                )
            )
            for seed, precipitation_scale in (
                (1234, 0.8), (3003, 0.8), (42, 0.6), (1234, 0.6)
            )
        ]

    def test_lakes_keep_hydrology_classification_and_aquatic_surface(self) -> None:
        lake_count = 0
        saline_count = 0
        river_lake_count = 0
        for world in self.worlds:
            cells = world["cells"]
            components: dict[int, list[dict]] = {}
            for cell in cells:
                component_id = cell["depression_component_id"]
                if component_id >= 0:
                    components.setdefault(component_id, []).append(cell)
            for cell in cells:
                if not cell["is_lake"]:
                    continue
                lake_count += 1
                river_lake_count += cell["is_river"]
                component = components[cell["depression_component_id"]]
                sink = cells[cell["depression_sink_cell_id"]]
                area = sum(member["area_km2"] for member in component)
                precipitation = sum(
                    member["precipitation_mm_y"] * member["area_km2"]
                    for member in component
                ) / area
                pet = sum(
                    member["hydrologic_potential_evapotranspiration_mm_y"]
                    * member["area_km2"]
                    for member in component
                ) / area
                expected_water_body = (
                    "saline_basin"
                    if not sink["lake_overflows"] and precipitation / max(1.0, pet) < 0.5
                    else "fresh_lake"
                )
                saline_count += expected_water_body == "saline_basin"
                with self.subTest(seed=world["summary"]["seed"], cell=cell["id"]):
                    self.assertEqual(cell["water_body_type"], expected_water_body)
                    self.assertEqual(cell["biome"], "lake")
                    self.assertEqual(
                        cell["soil_type"],
                        "saline" if expected_water_body == "saline_basin" else "wetland",
                    )
                    self.assertIn(cell["landform"], {"lacustrine_basin", "glacial_lake"})
                    self.assertEqual(cell["soil_depth_m"], 0.0)
                    self.assertEqual(cell["fertility"], 0.0)
                    self.assertEqual(cell["settlement_score"], 0.0)
        self.assertGreater(lake_count, 0)
        self.assertGreater(saline_count, 0)
        self.assertGreater(river_lake_count, 0)

    def test_dry_saline_basins_remain_exposed_salt_flats(self) -> None:
        salt_flats = [
            cell for world in self.worlds for cell in world["cells"]
            if not cell["is_lake"] and cell["water_body_type"] == "saline_basin"
        ]
        self.assertTrue(salt_flats)
        for cell in salt_flats:
            self.assertEqual(cell["landform"], "salt_flat")
            self.assertEqual(cell["soil_type"], "saline")
            self.assertEqual(cell["water_depth_m"], 0.0)

    def test_generated_settlements_never_occupy_standing_lakes(self) -> None:
        for world in self.worlds:
            self.assertTrue(world["settlements"])
            for settlement in world["settlements"]:
                cell = world["cells"][settlement["cell_id"]]
                self.assertFalse(cell["is_water"])
                self.assertFalse(cell["is_lake"])

    def test_lake_scores_cannot_enter_or_suppress_candidate_count(self) -> None:
        cells = [
            {"id": 0, "is_water": False, "is_lake": True,
             "settlement_score": 1.0, "neighbors": [1]},
            {"id": 1, "is_water": False, "is_lake": False,
             "settlement_score": 0.8, "neighbors": [0]},
        ]
        self.assertEqual(_candidate_count(cells), 1)
