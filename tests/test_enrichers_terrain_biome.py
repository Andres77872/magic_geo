"""Behavioural tests for the four terrain/biome enrichers.

``soil_dynamics``, ``glacial_landforms``, ``reef_diagnostics`` and
``sedimentary_resource_systems`` are exercised incidentally by the smoke suite,
which only ever sees the classifications a healthy generated world happens to
produce. These tests drive each classifier from hand-built cells so every soil
texture, glacial landform, reef type and petroleum-system type is reached, and
they pin the guards that early-return on missing or malformed input.

Each table row differs from the ``base`` control row in exactly one field, so a
failure identifies the branch that changed.
"""

from __future__ import annotations

from typing import Any
from unittest import TestCase

from magic_geo.glacial_landforms import enrich_world_with_glacial_landforms
from magic_geo.reef_diagnostics import enrich_world_with_reef_diagnostics
from magic_geo.sedimentary_resource_systems import (
    enrich_world_with_sedimentary_resource_systems,
)
from magic_geo.soil_dynamics import enrich_world_with_soil_diagnostics

from support import worlds


def _cell(cell_id: int, base: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    cell: dict[str, Any] = {
        "id": cell_id,
        "lat_deg": 0.0,
        "lon_deg": 0.0,
        "area_km2": 100.0,
        "neighbors": [],
        "water_body_type": "land",
        "is_water": False,
    }
    cell.update(base)
    cell.update(overrides)
    return cell


# --------------------------------------------------------------------------
# soil_dynamics
# --------------------------------------------------------------------------

#: A temperate mineral soil on unknown bedrock: no salinity, no organic horizon,
#: middling development. Every soil row below is this plus one changed field.
SOIL_BASE: dict[str, Any] = {
    "soil_type": "mineral",
    "soil_depth_m": 1.0,
    "fertility": 0.3,
    "lithology": "unknown",
    "landform": "stable_lowland",
    "elevation_m": 100.0,
    "precipitation_mm_y": 800.0,
    "runoff_mm_y": 0.0,
    "temperature_c": 18.0,
    "sediment_thickness_m": 0.0,
    "seasonal_aridity_index": 0.0,
    "erosion_rate": 0.0,
}


def _soil_cell(cell_id: int, **overrides: Any) -> dict[str, Any]:
    return _cell(cell_id, SOIL_BASE, **overrides)


def _soil_table_world(rows: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """One isolated soil cell per row; returns the world and a label -> cell map."""
    cells: list[dict[str, Any]] = []
    by_label: dict[str, dict[str, Any]] = {}
    for index, (label, overrides) in enumerate(rows.items()):
        cell = _soil_cell(index, **overrides)
        cells.append(cell)
        by_label[label] = cell
    return {"cells": cells}, by_label


def _profiles_by_cell(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(profile["cell_id"]): profile for profile in world["soil_profiles"]}


class SoilDiagnosticsGuardTests(TestCase):
    def test_empty_cell_list_zeroes_every_soil_summary_field(self) -> None:
        world = enrich_world_with_soil_diagnostics({"cells": []})

        self.assertEqual(world["soil_profiles"], [])
        self.assertEqual(world["soil_horizons"], [])
        self.assertEqual(world["soil_profile_histories"], [])
        self.assertEqual(
            world["soil_pedogenesis_model"]["time_basis"], "unavailable_without_cells"
        )
        self.assertEqual(world["soil_pedogenesis_model"]["stage_source"], "none")
        summary = world["summary"]
        self.assertEqual(summary["soil_diagnostic_cell_count"], 0)
        self.assertEqual(summary["soil_texture_counts"], {})
        self.assertEqual(summary["soil_profile_class_counts"], {})
        self.assertEqual(summary["soil_horizon_count"], 0)
        self.assertEqual(summary["soil_pedogenesis_step_count"], 0)
        self.assertEqual(summary["total_soil_production_m"], 0.0)
        self.assertEqual(summary["high_erosion_pedogenesis_count"], 0)

    def test_non_list_cells_takes_the_same_guard(self) -> None:
        world = enrich_world_with_soil_diagnostics({"cells": "not-a-list"})

        self.assertEqual(world["soil_profiles"], [])
        self.assertEqual(world["summary"]["soil_diagnostic_cell_count"], 0)

    def test_cells_without_soil_are_recorded_as_texture_none(self) -> None:
        world, by_label = _soil_table_world(
            {
                "base": {},
                "water": {"water_body_type": "ocean"},
                "no_soil_type": {"soil_type": "none"},
                "zero_depth": {"soil_depth_m": 0.0},
            }
        )
        enrich_world_with_soil_diagnostics(world)

        self.assertNotEqual(by_label["base"]["soil_texture_class"], "none")
        self.assertGreaterEqual(by_label["base"]["soil_profile_id"], 0)
        for label in ("water", "no_soil_type", "zero_depth"):
            with self.subTest(label=label):
                cell = by_label[label]
                self.assertEqual(cell["soil_texture_class"], "none")
                self.assertEqual(cell["soil_profile_id"], -1)
                self.assertEqual(cell["soil_horizon_count"], 0)
                self.assertEqual(cell["soil_ph"], 7.0)
                self.assertEqual(cell["soil_drainage_index"], 0.0)
                self.assertEqual(cell["soil_profile_development_index"], 0.0)
        self.assertEqual(world["summary"]["soil_texture_counts"]["none"], 3)
        self.assertEqual(world["summary"]["soil_diagnostic_cell_count"], 1)


class SoilTextureClassificationTests(TestCase):
    def test_every_texture_class_is_reachable(self) -> None:
        rows = {
            "loam_fallback": {},
            "saline_crust": {
                "depression_policy": "preserve_geologic_sink",
                "is_closed_basin": True,
            },
            "glacial_till_landform": {"landform": "moraine"},
            "glacial_till_tundra": {"soil_type": "tundra"},
            "alluvial_silt": {"landform": "delta", "sediment_thickness_m": 1.0},
            "silt_loam_thin_alluvium": {"landform": "delta"},
            "peat_wetland": {"soil_type": "wetland"},
            "peat_organic": {"temperature_c": -20.0},
            "volcanic_ash": {"lithology": "volcanic"},
            "sand": {"lithology": "sandstone", "seasonal_aridity_index": 1.0, "precipitation_mm_y": 0.0},
            "sandy_loam_sandstone": {"lithology": "sandstone"},
            "clay": {"lithology": "shale"},
            "clay_loam": {"lithology": "limestone", "seasonal_aridity_index": 0.6},
            # Fertile sediment as well, so that the fallthrough below basalt would
            # return "silt_loam": only the basalt branch can answer "loam" here.
            "loam_basalt": {
                "lithology": "basalt",
                "sediment_thickness_m": 1.0,
                "fertility": 0.5,
            },
            "sandy_loam_granite": {"lithology": "granite"},
            "silt_loam_fertile_sediment": {"sediment_thickness_m": 1.2, "fertility": 0.5},
        }
        expected = {
            "loam_fallback": "loam",
            "saline_crust": "saline_crust",
            "glacial_till_landform": "glacial_till",
            "glacial_till_tundra": "glacial_till",
            "alluvial_silt": "alluvial_silt",
            "silt_loam_thin_alluvium": "silt_loam",
            "peat_wetland": "peat",
            "peat_organic": "peat",
            "volcanic_ash": "volcanic_ash",
            "sand": "sand",
            "sandy_loam_sandstone": "sandy_loam",
            "clay": "clay",
            "clay_loam": "clay_loam",
            "loam_basalt": "loam",
            "sandy_loam_granite": "sandy_loam",
            "silt_loam_fertile_sediment": "silt_loam",
        }
        world, by_label = _soil_table_world(rows)
        enrich_world_with_soil_diagnostics(world)

        for label, texture in expected.items():
            with self.subTest(label=label):
                self.assertEqual(by_label[label]["soil_texture_class"], texture)
        self.assertEqual(
            sum(world["summary"]["soil_texture_counts"].values()), len(rows)
        )
        self.assertEqual(world["summary"]["soil_texture_counts"]["peat"], 2)

    def test_texture_drives_the_erodibility_texture_factor(self) -> None:
        world, by_label = _soil_table_world(
            {"sand": {"lithology": "sandstone", "seasonal_aridity_index": 1.0, "precipitation_mm_y": 0.0},
             "clay": {"lithology": "shale"}}
        )
        enrich_world_with_soil_diagnostics(world)

        self.assertEqual(by_label["sand"]["soil_texture_class"], "sand")
        self.assertEqual(by_label["clay"]["soil_texture_class"], "clay")
        self.assertLess(
            by_label["sand"]["soil_erodibility_index"],
            by_label["clay"]["soil_erodibility_index"],
        )


class SoilParentMaterialAndProfileClassTests(TestCase):
    def test_every_parent_material_is_reachable(self) -> None:
        rows = {
            "glacial_till": {"landform": "moraine"},
            "alluvium_landform": {"landform": "river_valley"},
            "alluvium_sediment": {"sediment_thickness_m": 1.5},
            "marine_sediment": {"landform": "coastal_plain"},
            "volcanic_ash": {"lithology": "volcanic"},
            "sedimentary_regolith": {"lithology": "sandstone"},
            "crystalline_regolith": {"lithology": "granite"},
            "mafic_regolith": {"lithology": "basalt"},
            "mixed_regolith": {},
        }
        expected = {
            "glacial_till": "glacial_till",
            "alluvium_landform": "alluvium",
            "alluvium_sediment": "alluvium",
            "marine_sediment": "marine_sediment",
            "volcanic_ash": "volcanic_ash",
            "sedimentary_regolith": "sedimentary_regolith",
            "crystalline_regolith": "crystalline_regolith",
            "mafic_regolith": "mafic_regolith",
            "mixed_regolith": "mixed_regolith",
        }
        world, by_label = _soil_table_world(rows)
        enrich_world_with_soil_diagnostics(world)
        profiles = _profiles_by_cell(world)

        for label, parent_material in expected.items():
            with self.subTest(label=label):
                self.assertEqual(
                    profiles[by_label[label]["id"]]["parent_material"], parent_material
                )

    def test_every_profile_class_is_reachable(self) -> None:
        rows = {
            "saline_arid_profile": {
                "depression_policy": "preserve_geologic_sink",
                "is_closed_basin": True,
            },
            "histic_wetland_profile_soil_type": {"soil_type": "wetland"},
            "histic_wetland_profile_organic": {"temperature_c": -20.0},
            "histic_wetland_profile_waterlogged": {
                "lithology": "shale",
                "precipitation_mm_y": 3000.0,
            },
            "glacial_young_profile": {"landform": "moraine"},
            "alluvial_profile": {"landform": "river_valley"},
            "volcanic_andic_profile": {"lithology": "volcanic"},
            "mature_weathered_profile": {
                "lithology": "granite",
                "soil_depth_m": 5.0,
                "fertility": 1.0,
            },
            "thin_weakly_developed_profile": {"soil_depth_m": 0.1, "fertility": 0.0},
            "moderately_developed_profile": {"soil_depth_m": 2.0, "fertility": 0.1},
        }
        expected = {
            "saline_arid_profile": "saline_arid_profile",
            "histic_wetland_profile_soil_type": "histic_wetland_profile",
            "histic_wetland_profile_organic": "histic_wetland_profile",
            "histic_wetland_profile_waterlogged": "histic_wetland_profile",
            "glacial_young_profile": "glacial_young_profile",
            "alluvial_profile": "alluvial_profile",
            "volcanic_andic_profile": "volcanic_andic_profile",
            "mature_weathered_profile": "mature_weathered_profile",
            "thin_weakly_developed_profile": "thin_weakly_developed_profile",
            "moderately_developed_profile": "moderately_developed_profile",
        }
        world, by_label = _soil_table_world(rows)
        enrich_world_with_soil_diagnostics(world)
        profiles = _profiles_by_cell(world)

        for label, profile_class in expected.items():
            with self.subTest(label=label):
                self.assertEqual(
                    profiles[by_label[label]["id"]]["profile_class"], profile_class
                )
        self.assertEqual(
            world["summary"]["soil_profile_class_counts"]["histic_wetland_profile"], 3
        )

    def test_waterlogged_profile_needs_the_poor_drainage_not_the_lithology(self) -> None:
        world, by_label = _soil_table_world(
            {
                "waterlogged": {"lithology": "shale", "precipitation_mm_y": 3000.0},
                "drained": {"lithology": "shale", "precipitation_mm_y": 800.0},
            }
        )
        enrich_world_with_soil_diagnostics(world)
        profiles = _profiles_by_cell(world)

        wet = profiles[by_label["waterlogged"]["id"]]
        dry = profiles[by_label["drained"]["id"]]
        self.assertEqual(wet["texture_class"], dry["texture_class"])
        self.assertLessEqual(wet["drainage_index"], 0.25)
        self.assertGreaterEqual(wet["moisture_index"], 0.60)
        self.assertEqual(wet["profile_class"], "histic_wetland_profile")
        self.assertLessEqual(dry["drainage_index"], 0.25)
        self.assertLess(dry["moisture_index"], 0.60)
        self.assertEqual(dry["profile_class"], "moderately_developed_profile")
        self.assertEqual(world["summary"]["waterlogged_soil_cell_fraction"], 0.5)


class SoilHorizonTests(TestCase):
    def test_deep_profile_builds_o_a_b_c_horizons_with_depth_trends(self) -> None:
        cell = _soil_cell(
            0,
            lithology="shale",
            soil_depth_m=5.0,
            fertility=0.4,
            precipitation_mm_y=880.0,
            temperature_c=11.0,
        )
        world = enrich_world_with_soil_diagnostics({"cells": [cell]})
        horizons = world["soil_horizons"]

        self.assertEqual([horizon["horizon_name"] for horizon in horizons], ["O", "A", "B", "C"])
        self.assertEqual(cell["soil_texture_class"], "clay")
        self.assertEqual(cell["soil_horizon_count"], 4)
        self.assertEqual(horizons[0]["top_depth_m"], 0.0)
        self.assertAlmostEqual(horizons[-1]["bottom_depth_m"], 5.0, places=6)
        for previous, current in zip(horizons, horizons[1:]):
            self.assertEqual(previous["bottom_depth_m"], current["top_depth_m"])
            self.assertGreaterEqual(previous["organic_matter_fraction"], current["organic_matter_fraction"])
        by_name = {horizon["horizon_name"]: horizon for horizon in horizons}
        self.assertGreater(by_name["B"]["clay_fraction"], by_name["A"]["clay_fraction"])
        self.assertLess(by_name["C"]["clay_fraction"], by_name["A"]["clay_fraction"])
        self.assertGreater(by_name["C"]["sand_fraction"], by_name["A"]["sand_fraction"])
        self.assertLess(by_name["B"]["sand_fraction"], by_name["A"]["sand_fraction"])
        self.assertGreaterEqual(by_name["O"]["silt_fraction"], 0.5)
        self.assertAlmostEqual(by_name["C"]["ph"], round(cell["soil_ph"] + 0.20, 6), places=5)
        self.assertAlmostEqual(by_name["O"]["ph"], round(cell["soil_ph"] - 0.12, 6), places=5)
        for horizon in horizons:
            with self.subTest(horizon=horizon["horizon_name"]):
                self.assertAlmostEqual(
                    horizon["sand_fraction"] + horizon["silt_fraction"] + horizon["clay_fraction"],
                    1.0,
                    places=5,
                )

    def test_very_shallow_wetland_soil_collapses_to_a_single_a_horizon(self) -> None:
        cell = _soil_cell(0, soil_type="wetland", soil_depth_m=0.10)
        world = enrich_world_with_soil_diagnostics({"cells": [cell]})

        self.assertEqual([horizon["horizon_name"] for horizon in world["soil_horizons"]], ["A"])
        self.assertAlmostEqual(world["soil_horizons"][0]["thickness_m"], 0.10, places=6)

    def test_thin_remainder_is_merged_into_the_last_horizon(self) -> None:
        cell = _soil_cell(0, soil_type="wetland", soil_depth_m=0.23, fertility=0.5)
        world = enrich_world_with_soil_diagnostics({"cells": [cell]})
        horizons = world["soil_horizons"]

        self.assertEqual([horizon["horizon_name"] for horizon in horizons], ["O", "A", "B"])
        self.assertAlmostEqual(horizons[-1]["bottom_depth_m"], 0.23, places=6)
        self.assertGreater(horizons[-1]["thickness_m"], 0.0936)

    def test_weak_development_and_relief_skip_the_b_horizon(self) -> None:
        steep = _soil_cell(0, fertility=0.0, elevation_m=2000.0, neighbors=[1, 99])
        valley = _soil_cell(1, fertility=0.0, elevation_m=0.0, neighbors=[0])
        flat = _soil_cell(2, fertility=0.0, elevation_m=2000.0, neighbors=[])
        world = enrich_world_with_soil_diagnostics({"cells": [steep, valley, flat]})
        profiles = _profiles_by_cell(world)
        names = {
            cell_id: [
                horizon["horizon_name"]
                for horizon in world["soil_horizons"]
                if horizon["cell_id"] == cell_id
            ]
            for cell_id in (0, 2)
        }

        self.assertEqual(names[0], ["A", "C"])
        self.assertEqual(names[2], ["A", "B", "C"])
        self.assertLess(profiles[0]["development_index"], 0.22)
        self.assertGreaterEqual(profiles[2]["development_index"], 0.22)
        self.assertGreater(profiles[0]["drainage_index"], profiles[2]["drainage_index"])
        self.assertLess(profiles[0]["organic_matter_fraction"], profiles[2]["organic_matter_fraction"])


class SoilPedogenesisStageTests(TestCase):
    def _world(self, **extra: Any) -> dict[str, Any]:
        world: dict[str, Any] = {"cells": [_soil_cell(0)]}
        world.update(extra)
        return world

    def test_missing_eras_fall_back_to_a_single_undated_stage(self) -> None:
        world = enrich_world_with_soil_diagnostics(self._world())

        model = world["soil_pedogenesis_model"]
        self.assertEqual(model["time_basis"], "undated_diagnostic_step")
        self.assertEqual(model["stage_source"], "synthetic_fallback")
        self.assertEqual(model["stage_count"], 1)
        self.assertFalse(model["linked_nominal_time_coordinate_available"])
        self.assertEqual(model["natural_stage_flux_partition"], "not_applicable")
        history = world["soil_profile_histories"][0]
        self.assertEqual(history["step_count"], 1)
        self.assertEqual(history["steps"][0]["time_basis"], "undated_diagnostic_step")
        self.assertEqual(history["steps"][0]["era_id"], -1)
        self.assertAlmostEqual(history["final_depth_m"], 1.0, places=6)
        self.assertGreater(history["total_soil_production_m"], 0.0)

    def test_historical_eras_drive_year_bp_stages_sorted_oldest_first(self) -> None:
        world = enrich_world_with_soil_diagnostics(
            self._world(
                historical_eras=[
                    {"id": 1, "start_year_bp": 2000.0, "end_year_bp": 1000.0},
                    {"id": 2, "start_year_bp": 9000.0, "end_year_bp": 2000.0},
                ]
            )
        )

        model = world["soil_pedogenesis_model"]
        self.assertEqual(model["time_basis"], "historical_year_bp")
        self.assertEqual(model["stage_source"], "historical_eras")
        self.assertEqual(model["stage_count"], 2)
        steps = world["soil_profile_histories"][0]["steps"]
        self.assertEqual([step["era_id"] for step in steps], [2, 1])
        self.assertEqual([step["start_year_bp"] for step in steps], [9000.0, 2000.0])
        self.assertEqual([step["time_basis"] for step in steps], ["historical_year_bp"] * 2)
        self.assertAlmostEqual(steps[-1]["end_depth_m"], 1.0, places=6)
        self.assertGreater(steps[0]["erosion_loss_m"], steps[1]["erosion_loss_m"])

    def test_geo_only_feedback_history_drives_natural_simulation_stages(self) -> None:
        world = enrich_world_with_soil_diagnostics(
            self._world(
                generation_scope="geo_only",
                historical_eras=[{"id": 1, "start_year_bp": 10.0, "end_year_bp": 0.0}],
                earth_system_feedback_history=[
                    {
                        "id": 0,
                        "stage": "rifting",
                        "nominal_time_basis": "plate_model",
                        "nominal_time_source_parameter": "spreading_rate",
                        "nominal_interval_start_ma": 20.0,
                        "nominal_interval_end_ma": 10.0,
                        "nominal_interval_duration_ma": 10.0,
                    },
                    {
                        "id": 1,
                        "stage": "drift",
                        "nominal_time_basis": "plate_model",
                        "nominal_time_source_parameter": "spreading_rate",
                        "nominal_interval_start_ma": 10.0,
                        "nominal_interval_end_ma": 0.0,
                        "nominal_interval_duration_ma": 10.0,
                    },
                ],
            )
        )

        model = world["soil_pedogenesis_model"]
        self.assertEqual(model["time_basis"], "natural_simulation_stage")
        self.assertEqual(model["stage_source"], "earth_system_feedback_history")
        self.assertTrue(model["linked_nominal_time_coordinate_available"])
        self.assertEqual(
            model["natural_stage_flux_partition"],
            "normalized_across_nominally_advancing_erosion_intervals",
        )
        history = world["soil_profile_histories"][0]
        steps = history["steps"]
        self.assertEqual([step["natural_stage_name"] for step in steps], ["rifting", "drift"])
        self.assertEqual([step["natural_stage_id"] for step in steps], [0, 1])
        self.assertEqual([step["start_year_bp"] for step in steps], [None, None])
        self.assertEqual([step["era_id"] for step in steps], [-1, -1])
        self.assertEqual([step["end_model_step"] for step in steps], [1, 2])
        self.assertTrue(all(step["nominal_time_link_available"] for step in steps))
        self.assertLess(history["initial_depth_m"], history["final_depth_m"])
        self.assertGreater(history["total_erosion_loss_m"], 0.0)
        self.assertGreater(history["mean_pedogenic_flux_index"], 0.0)

    def test_natural_stages_without_nominal_duration_freeze_depth_and_flux(self) -> None:
        world = enrich_world_with_soil_diagnostics(
            self._world(
                generation_scope="geo_only",
                earth_system_feedback_history=[
                    {"id": 0, "stage": "spinup", "nominal_interval_duration_ma": 0.0},
                    {"id": 1, "stage": "hold"},
                ],
            )
        )

        model = world["soil_pedogenesis_model"]
        self.assertEqual(model["time_basis"], "natural_simulation_stage")
        self.assertFalse(model["linked_nominal_time_coordinate_available"])
        history = world["soil_profile_histories"][0]
        self.assertEqual(history["initial_depth_m"], history["final_depth_m"])
        self.assertEqual(history["total_soil_production_m"], 0.0)
        self.assertEqual(history["total_erosion_loss_m"], 0.0)
        self.assertEqual(history["mean_pedogenic_flux_index"], 0.0)
        self.assertEqual(history["mean_weathering_index"], 0.0)
        self.assertFalse(history["high_erosion_pressure"])
        self.assertEqual([step["pedogenic_flux_index"] for step in history["steps"]], [0.0, 0.0])
        self.assertEqual(world["summary"]["total_soil_production_m"], 0.0)

    def test_malformed_feedback_history_falls_through_to_the_era_stages(self) -> None:
        cases = {
            "empty": [],
            "not_a_list": "nope",
            "non_dict_entry": [{"id": 0, "stage": "rifting"}, "broken"],
        }
        for label, feedback in cases.items():
            with self.subTest(label=label):
                world = enrich_world_with_soil_diagnostics(
                    self._world(
                        generation_scope="geo_only",
                        earth_system_feedback_history=feedback,
                        historical_eras=[{"id": 4, "start_year_bp": 100.0, "end_year_bp": 0.0}],
                    )
                )
                model = world["soil_pedogenesis_model"]
                self.assertEqual(model["time_basis"], "historical_year_bp")
                self.assertEqual(model["stage_source"], "historical_eras")
                self.assertEqual(
                    world["soil_profile_histories"][0]["steps"][0]["era_id"], 4
                )

    def test_generation_scope_other_than_geo_only_ignores_feedback_history(self) -> None:
        world = enrich_world_with_soil_diagnostics(
            self._world(
                generation_scope="full",
                earth_system_feedback_history=[{"id": 0, "stage": "rifting"}],
            )
        )

        self.assertEqual(
            world["soil_pedogenesis_model"]["time_basis"], "undated_diagnostic_step"
        )


class SoilDiagnosticsRealWorldControlTests(TestCase):
    def test_rerunning_the_enricher_on_a_generated_world_is_stable(self) -> None:
        world = worlds.cached_world("replay_128")
        before = dict(world["summary"])
        profile_count = len(world["soil_profiles"])

        enrich_world_with_soil_diagnostics(world)

        self.assertEqual(len(world["soil_profiles"]), profile_count)
        for key, value in before.items():
            if key.startswith("soil_") or key.startswith("mean_soil"):
                with self.subTest(key=key):
                    self.assertEqual(world["summary"][key], value)
        self.assertEqual(
            world["summary"]["soil_profile_count"],
            sum(1 for cell in world["cells"] if cell["soil_texture_class"] != "none"),
        )


# --------------------------------------------------------------------------
# glacial_landforms
# --------------------------------------------------------------------------

GLACIAL_BASE: dict[str, Any] = {
    "landform": "stable_lowland",
    "biome": "tundra",
    "elevation_m": 200.0,
    "lat_deg": 45.0,
    "ice_thickness_m": 0.0,
    "moraine_deposition_m": 0.0,
    "deglaciation_age_ka": 0.0,
    "glacial_erosion_m": 0.0,
    "runoff_mm_y": 0.0,
    "flow_accumulation": 0.0,
    "is_lake": False,
    "is_river": False,
}


def _glacial_cell(cell_id: int, **overrides: Any) -> dict[str, Any]:
    return _cell(cell_id, GLACIAL_BASE, **overrides)


class GlacialLandformGuardTests(TestCase):
    def test_empty_cell_list_zeroes_every_glacial_summary_field(self) -> None:
        world = enrich_world_with_glacial_landforms({"cells": []})

        self.assertEqual(world["glacial_landform_systems"], [])
        summary = world["summary"]
        self.assertEqual(summary["glacial_landform_cell_count"], 0)
        self.assertEqual(summary["glacial_landform_system_count"], 0)
        self.assertEqual(summary["glacial_landform_area_km2"], 0.0)
        self.assertEqual(summary["mean_glacial_landform_index"], 0.0)
        self.assertEqual(summary["mean_glacial_erosion_intensity_index"], 0.0)
        self.assertEqual(summary["mean_glacial_deposition_index"], 0.0)
        self.assertEqual(summary["mean_glacial_meltwater_index"], 0.0)
        self.assertEqual(summary["glacial_landform_type_counts"], {})

    def test_non_list_cells_takes_the_same_guard(self) -> None:
        world = enrich_world_with_glacial_landforms({"cells": {"id": 0}})

        self.assertEqual(world["glacial_landform_systems"], [])
        self.assertEqual(world["summary"]["glacial_landform_system_count"], 0)

    def test_non_list_neighbours_are_treated_as_isolated_cells(self) -> None:
        cells = [
            _glacial_cell(0, landform="fjord", neighbors=None),
            _glacial_cell(1, landform="fjord", neighbors=[0]),
        ]
        world = enrich_world_with_glacial_landforms({"cells": cells})

        self.assertEqual(cells[0]["glacial_landform_type"], "fjord")
        self.assertEqual(len(world["glacial_landform_systems"]), 2)
        self.assertEqual(world["glacial_landform_systems"][0]["cell_ids"], [0])
        self.assertEqual(world["glacial_landform_systems"][1]["cell_ids"], [1])

    def test_unknown_neighbour_ids_are_ignored(self) -> None:
        cell = _glacial_cell(0, landform="moraine", neighbors=[404])
        world = enrich_world_with_glacial_landforms({"cells": [cell]})

        self.assertEqual(world["glacial_landform_systems"][0]["cell_ids"], [0])


class GlacialLandformTypeTests(TestCase):
    def test_every_landform_type_is_reachable(self) -> None:
        rows = {
            "none": {},
            "fjord": {"landform": "fjord"},
            "glacial_valley_landform": {"landform": "glacial_valley"},
            "glacial_lake_landform": {"landform": "glacial_lake"},
            "moraine_landform": {"landform": "moraine"},
            "ice_field_polar": {"landform": "ice_field", "ice_thickness_m": 30.0, "lat_deg": 70.0, "elevation_m": 100.0},
            "ice_field_alpine": {"landform": "ice_field", "ice_thickness_m": 30.0, "lat_deg": 30.0, "elevation_m": 3000.0},
            # Floating ice shelf: only the ``landform == "ice_field"`` route can
            # classify it, because every later branch requires ``not is_water``.
            "ice_field_afloat": {
                "landform": "ice_field",
                "ice_thickness_m": 30.0,
                "lat_deg": 70.0,
                "elevation_m": 100.0,
                "is_water": True,
                "water_body_type": "ocean",
            },
            "bare_polar_ice": {"ice_thickness_m": 30.0, "lat_deg": 70.0, "elevation_m": 100.0},
            "thick_subpolar_ice": {"ice_thickness_m": 500.0, "lat_deg": 55.0, "elevation_m": 1000.0},
            "high_polar_ice": {"ice_thickness_m": 30.0, "lat_deg": 70.0, "elevation_m": 2000.0},
            "moraine_deposits": {"moraine_deposition_m": 1.0, "deglaciation_age_ka": 10.0},
            "glacial_lake_deglaciated": {"is_lake": True, "is_water": True, "deglaciation_age_ka": 10.0},
            "glacial_lake_moraine_dammed": {"is_lake": True, "is_water": True, "moraine_deposition_m": 0.4},
            "plain_lake": {"is_lake": True, "is_water": True},
        }
        expected = {
            "none": "none",
            "fjord": "fjord",
            "glacial_valley_landform": "glacial_valley",
            "glacial_lake_landform": "glacial_lake",
            "moraine_landform": "moraine",
            "ice_field_polar": "ice_cap",
            "ice_field_alpine": "mountain_glacier",
            "ice_field_afloat": "ice_cap",
            "bare_polar_ice": "ice_cap",
            "thick_subpolar_ice": "ice_cap",
            "high_polar_ice": "mountain_glacier",
            "moraine_deposits": "moraine",
            "glacial_lake_deglaciated": "glacial_lake",
            "glacial_lake_moraine_dammed": "glacial_lake",
            "plain_lake": "none",
        }
        cells = [_glacial_cell(index, **overrides) for index, overrides in enumerate(rows.values())]
        by_label = dict(zip(rows, cells))
        world = enrich_world_with_glacial_landforms({"cells": cells})

        for label, landform_type in expected.items():
            with self.subTest(label=label):
                self.assertEqual(by_label[label]["glacial_landform_type"], landform_type)
        counts = world["summary"]["glacial_landform_type_counts"]
        self.assertEqual(counts["ice_cap"], 4)
        self.assertEqual(counts["mountain_glacier"], 2)
        self.assertEqual(counts["none"], 2)
        self.assertEqual(world["summary"]["ice_cap_landform_cell_count"], 4)
        self.assertEqual(world["summary"]["mountain_glacier_landform_cell_count"], 2)
        self.assertEqual(world["summary"]["fjord_landform_cell_count"], 1)
        self.assertEqual(world["summary"]["glacial_valley_landform_cell_count"], 1)
        self.assertEqual(world["summary"]["glacial_lake_landform_cell_count"], 3)
        self.assertEqual(world["summary"]["moraine_landform_cell_count"], 2)
        self.assertEqual(world["summary"]["glacial_landform_cell_count"], 13)

    def test_glacial_valley_needs_erosion_relief_and_meltwater(self) -> None:
        cases = {
            "runoff": {"glacial_erosion_m": 10.0, "runoff_mm_y": 500.0},
            "flow_accumulation": {"glacial_erosion_m": 10.0, "flow_accumulation": 2.0e8},
            "no_meltwater": {"glacial_erosion_m": 10.0},
            "no_erosion": {"runoff_mm_y": 500.0},
        }
        expected = {
            "runoff": "glacial_valley",
            "flow_accumulation": "glacial_valley",
            "no_meltwater": "none",
            "no_erosion": "none",
        }
        for label, overrides in cases.items():
            with self.subTest(label=label):
                upland = _glacial_cell(0, elevation_m=1000.0, neighbors=[1], **overrides)
                lowland = _glacial_cell(1, elevation_m=0.0, neighbors=[0])
                enrich_world_with_glacial_landforms({"cells": [upland, lowland]})
                self.assertEqual(upland["glacial_landform_type"], expected[label])

    def test_flat_terrain_denies_the_glacial_valley_relief_test(self) -> None:
        flat = _glacial_cell(0, glacial_erosion_m=10.0, runoff_mm_y=500.0, neighbors=[1])
        neighbor = _glacial_cell(1, neighbors=[0])
        enrich_world_with_glacial_landforms({"cells": [flat, neighbor]})

        self.assertEqual(flat["glacial_landform_type"], "none")

        # Same erosion and same meltwater, but now the neighbour sits 1000 m
        # lower: relief is the only thing that changed.
        incised = _glacial_cell(0, glacial_erosion_m=10.0, runoff_mm_y=500.0, neighbors=[1])
        lower = _glacial_cell(1, elevation_m=GLACIAL_BASE["elevation_m"] - 1000.0, neighbors=[0])
        enrich_world_with_glacial_landforms({"cells": [incised, lower]})

        self.assertEqual(incised["glacial_landform_type"], "glacial_valley")


class GlacialIndexTests(TestCase):
    def test_inert_cell_scores_zero_on_every_index(self) -> None:
        cell = _glacial_cell(0)
        enrich_world_with_glacial_landforms({"cells": [cell]})

        self.assertEqual(cell["glacial_landform_index"], 0.0)
        self.assertEqual(cell["glacial_erosion_intensity_index"], 0.0)
        self.assertEqual(cell["glacial_deposition_index"], 0.0)
        self.assertEqual(cell["glacial_meltwater_index"], 0.0)
        self.assertEqual(cell["glacial_landform_system_id"], -1)

    def test_river_cells_score_meltwater_from_contact_and_channel(self) -> None:
        cell = _glacial_cell(0, is_river=True)
        enrich_world_with_glacial_landforms({"cells": [cell]})

        self.assertAlmostEqual(cell["glacial_meltwater_index"], 0.36, places=6)

    def test_moraine_deposition_saturates_the_deposition_index(self) -> None:
        cell = _glacial_cell(0, moraine_deposition_m=2.2, deglaciation_age_ka=82.0)
        enrich_world_with_glacial_landforms({"cells": [cell]})

        self.assertEqual(cell["glacial_landform_type"], "moraine")
        self.assertAlmostEqual(cell["glacial_deposition_index"], 0.95, places=6)

    def test_marine_contact_raises_meltwater_without_a_river(self) -> None:
        glacier = _glacial_cell(0, landform="fjord", neighbors=[1])
        sea = _glacial_cell(1, water_body_type="ocean", is_water=True, neighbors=[0])
        enrich_world_with_glacial_landforms({"cells": [glacier, sea]})

        self.assertAlmostEqual(glacier["glacial_meltwater_index"], 0.18, places=6)


class GlacialRegionRecordTests(TestCase):
    def test_same_type_neighbours_merge_into_one_system_record(self) -> None:
        cells = [
            _glacial_cell(
                0,
                landform="moraine",
                neighbors=[1],
                lat_deg=60.0,
                lon_deg=10.0,
                ice_sheet_id=3,
                basin_id=7,
                permafrost_extent_index=0.5,
                is_river=True,
            ),
            _glacial_cell(
                1,
                landform="moraine",
                neighbors=[0, 2],
                lat_deg=60.0,
                lon_deg=10.0,
                ice_sheet_id=3,
                basin_id=-1,
                biome="boreal_forest",
                ice_thickness_m=30.0,
            ),
            _glacial_cell(2, landform="fjord", neighbors=[1], lat_deg=60.0, lon_deg=10.0),
        ]
        world = enrich_world_with_glacial_landforms({"cells": cells})
        systems = world["glacial_landform_systems"]

        self.assertEqual(len(systems), 2)
        moraine, fjord = systems
        self.assertEqual(moraine["glacial_landform_type"], "moraine")
        self.assertEqual(moraine["cell_ids"], [0, 1])
        self.assertEqual(moraine["cell_count"], 2)
        self.assertEqual(moraine["area_km2"], 200.0)
        self.assertAlmostEqual(moraine["centroid_lat_deg"], 60.0, places=4)
        self.assertAlmostEqual(moraine["centroid_lon_deg"], 10.0, places=4)
        self.assertEqual(moraine["linked_ice_sheet_ids"], [3])
        self.assertEqual(moraine["linked_basin_ids"], [7])
        self.assertEqual(moraine["river_cell_count"], 1)
        self.assertEqual(moraine["lake_cell_count"], 0)
        self.assertEqual(moraine["coastal_cell_count"], 0)
        self.assertEqual(moraine["permafrost_cell_count"], 1)
        self.assertEqual(moraine["tundra_cell_count"], 1)
        self.assertEqual(moraine["ice_covered_cell_count"], 1)
        self.assertEqual(moraine["dominant_biome"], "boreal_forest")
        self.assertEqual(moraine["dominant_landform"], "moraine")
        self.assertEqual(fjord["glacial_landform_type"], "fjord")
        self.assertEqual(fjord["cell_ids"], [2])
        self.assertEqual([cell["glacial_landform_system_id"] for cell in cells], [0, 0, 1])
        summary = world["summary"]
        self.assertEqual(summary["glacial_landform_system_count"], 2)
        self.assertEqual(summary["glacial_landform_cell_count"], 3)
        self.assertEqual(summary["glacial_landform_area_km2"], 300.0)

    def test_dominant_biome_ties_break_alphabetically(self) -> None:
        cells = [
            _glacial_cell(0, landform="moraine", neighbors=[1], biome="tundra"),
            _glacial_cell(1, landform="moraine", neighbors=[0], biome="boreal_forest"),
        ]
        world = enrich_world_with_glacial_landforms({"cells": cells})

        self.assertEqual(world["glacial_landform_systems"][0]["dominant_biome"], "boreal_forest")


class GlacialLandformRealWorldControlTests(TestCase):
    def test_rerunning_the_enricher_on_a_generated_world_is_stable(self) -> None:
        world = worlds.cached_world("replay_128")
        before = dict(world["summary"])
        systems = len(world["glacial_landform_systems"])

        enrich_world_with_glacial_landforms(world)

        self.assertEqual(len(world["glacial_landform_systems"]), systems)
        for key, value in before.items():
            if "glacial" in key:
                with self.subTest(key=key):
                    self.assertEqual(world["summary"][key], value)
        self.assertEqual(
            world["summary"]["glacial_landform_cell_count"],
            sum(1 for cell in world["cells"] if cell["glacial_landform_type"] != "none"),
        )


# --------------------------------------------------------------------------
# reef_diagnostics
# --------------------------------------------------------------------------

REEF_BASE: dict[str, Any] = {
    "water_body_type": "continental_shelf",
    "is_water": True,
    "water_depth_m": 5.0,
    "temperature_c": 26.0,
    "ice_thickness_m": 0.0,
    "wind_east": 0.0,
    "wind_north": 0.0,
    "sediment_thickness_m": 0.0,
    "fishery_productivity_index": 0.0,
}

LAND_BASE: dict[str, Any] = {
    "water_body_type": "land",
    "is_water": False,
    "landform": "stable_lowland",
    "lithology": "granite",
    "runoff_mm_y": 0.0,
    "is_river": False,
}


def _sea_cell(cell_id: int, **overrides: Any) -> dict[str, Any]:
    return _cell(cell_id, REEF_BASE, **overrides)


def _land_cell(cell_id: int, **overrides: Any) -> dict[str, Any]:
    return _cell(cell_id, LAND_BASE, **overrides)


def _reef_pair(sea: dict[str, Any], land: dict[str, Any], **world_extra: Any) -> dict[str, Any]:
    world: dict[str, Any] = {"cells": [sea, land]}
    world.update(world_extra)
    return enrich_world_with_reef_diagnostics(world)


class ReefDiagnosticsGuardTests(TestCase):
    def test_empty_cell_list_leaves_the_world_untouched(self) -> None:
        world = enrich_world_with_reef_diagnostics({"cells": []})

        self.assertNotIn("reef_systems", world)
        self.assertNotIn("summary", world)

    def test_non_list_cells_takes_the_same_guard(self) -> None:
        world = enrich_world_with_reef_diagnostics({"cells": None})

        self.assertNotIn("reef_systems", world)

    def test_land_and_isolated_marine_cells_score_zero(self) -> None:
        land = _land_cell(0)
        open_sea = _sea_cell(1, neighbors=[2])
        deep = _sea_cell(2, water_body_type="ocean", water_depth_m=4000.0, neighbors=[1])
        world = enrich_world_with_reef_diagnostics({"cells": [land, open_sea, deep]})

        for cell in (land, open_sea, deep):
            with self.subTest(cell=cell["id"]):
                self.assertEqual(cell["reef_growth_index"], 0.0)
                self.assertEqual(cell["reef_type"], "none")
                self.assertEqual(cell["reef_system_id"], -1)
        self.assertEqual(world["reef_systems"], [])
        self.assertEqual(world["summary"]["reef_cell_count"], 0)
        self.assertEqual(world["summary"]["reef_type_counts"], {})
        self.assertEqual(world["summary"]["mean_reef_growth_index"], 0.0)

        # Control: the same shelf cell scores as soon as it touches land, so the
        # zeros above come from the missing land contact, not from the fixture.
        coastal = _sea_cell(1, neighbors=[2])
        _reef_pair(coastal, _land_cell(2, neighbors=[1]))
        self.assertGreaterEqual(coastal["reef_growth_index"], 0.46)

    def test_dry_marine_flag_disqualifies_a_shelf_cell(self) -> None:
        self.assertTrue(REEF_BASE["is_water"])
        dry = _sea_cell(0, is_water=False, neighbors=[1])
        _reef_pair(dry, _land_cell(1, neighbors=[0]))

        self.assertEqual(dry["reef_growth_index"], 0.0)
        self.assertEqual(dry["reef_type"], "none")

        wet = _sea_cell(0, neighbors=[1])
        _reef_pair(wet, _land_cell(1, neighbors=[0]))

        self.assertGreaterEqual(wet["reef_growth_index"], 0.46)
        self.assertEqual(wet["reef_type"], "fringing_reef")

    def test_malformed_side_tables_are_ignored(self) -> None:
        sea = _sea_cell(0, neighbors=[1])
        land = _land_cell(1, neighbors=[0])
        world = _reef_pair(
            sea,
            land,
            coastal_features=None,
            settlements=42,
            renewable_resource_records=1.5,
        )

        record = world["reef_systems"][0]
        self.assertEqual(record["coastal_feature_ids"], [])
        self.assertEqual(record["settlement_ids"], [])
        self.assertEqual(record["fishery_resource_record_ids"], [])

    def test_malformed_side_table_entries_are_skipped(self) -> None:
        sea = _sea_cell(0, neighbors=[1])
        land = _land_cell(1, neighbors=[0])
        world = _reef_pair(
            sea,
            land,
            coastal_features=["broken", {"id": 5, "cell_id": -1, "type": "beach"}],
            settlements=["broken", {"id": -1, "cell_id": 1}, {"id": 6, "cell_id": -1}],
            renewable_resource_records=[
                "broken",
                {"id": 7, "cell_id": 0, "resource_type": "timber_yield"},
                {"id": -1, "cell_id": 0, "resource_type": "fishery_productivity"},
            ],
        )

        record = world["reef_systems"][0]
        self.assertEqual(record["coastal_feature_ids"], [])
        self.assertEqual(record["settlement_ids"], [])
        self.assertEqual(record["fishery_resource_record_ids"], [])


class ReefTypeClassificationTests(TestCase):
    def _reef_type(self, sea_overrides: dict[str, Any], land_cells: list[dict[str, Any]], **world_extra: Any) -> str:
        sea = _sea_cell(0, neighbors=[cell["id"] for cell in land_cells], **sea_overrides)
        world: dict[str, Any] = {"cells": [sea, *land_cells]}
        world.update(world_extra)
        enrich_world_with_reef_diagnostics(world)
        self.assertGreaterEqual(sea["reef_growth_index"], 0.46)
        return str(sea["reef_type"])

    def test_fringing_reef_is_the_default_for_a_plain_coast(self) -> None:
        self.assertEqual(self._reef_type({}, [_land_cell(1)]), "fringing_reef")

    def test_small_island_neighbourhood_yields_an_atoll(self) -> None:
        for island_class in ("islet", "island"):
            with self.subTest(island_class=island_class):
                self.assertEqual(
                    self._reef_type({}, [_land_cell(1, island_class=island_class)]),
                    "atoll_reef",
                )

    def test_large_island_or_crowded_coast_is_not_an_atoll(self) -> None:
        self.assertEqual(
            self._reef_type({}, [_land_cell(1, island_class="large_island")]),
            "fringing_reef",
        )
        crowded = [_land_cell(index, island_class="islet") for index in (1, 2, 3)]
        self.assertEqual(self._reef_type({}, crowded), "fringing_reef")

    def test_barrier_coastal_feature_yields_a_barrier_reef(self) -> None:
        reef_type = self._reef_type(
            {},
            [_land_cell(1)],
            coastal_features=[{"id": 9, "cell_id": 1, "type": "barrier_island"}],
        )

        self.assertEqual(reef_type, "barrier_reef")

    def test_atoll_outranks_a_barrier_feature(self) -> None:
        reef_type = self._reef_type(
            {},
            [_land_cell(1, island_class="islet")],
            coastal_features=[{"id": 9, "cell_id": 1, "type": "barrier_island"}],
        )

        self.assertEqual(reef_type, "atoll_reef")

    def test_cold_water_reef_outranks_every_warm_water_type(self) -> None:
        reef_type = self._reef_type(
            {"temperature_c": 17.0},
            [_land_cell(1, island_class="islet")],
            coastal_features=[{"id": 9, "cell_id": 1, "type": "barrier_island"}],
        )

        self.assertEqual(reef_type, "cold_water_reef")

    def test_temperature_suitability_has_three_regimes(self) -> None:
        growth: dict[float, float] = {}
        for temperature in (1.0, 17.0, 26.0):
            sea = _sea_cell(0, temperature_c=temperature, neighbors=[1])
            land = _land_cell(1, neighbors=[0])
            _reef_pair(sea, land)
            growth[temperature] = sea["reef_growth_index"]

        self.assertAlmostEqual(growth[26.0] - growth[1.0], 0.26, places=6)
        self.assertAlmostEqual(growth[17.0] - growth[1.0], 13.0 / 14.0 * 0.55 * 0.26, places=6)


class ReefIndexTests(TestCase):
    def test_shallow_water_suitability_ranks_the_three_marine_bodies(self) -> None:
        growth: dict[str, float] = {}
        for water_body in ("continental_shelf", "inland_sea", "ocean"):
            sea = _sea_cell(0, water_body_type=water_body, water_depth_m=5.0, neighbors=[1])
            land = _land_cell(1, neighbors=[0])
            _reef_pair(sea, land)
            growth[water_body] = sea["reef_growth_index"]

        self.assertGreater(growth["continental_shelf"], growth["inland_sea"])
        self.assertGreater(growth["inland_sea"], growth["ocean"])
        self.assertGreaterEqual(growth["ocean"], 0.0)

    def test_depth_erodes_shelf_suitability(self) -> None:
        shallow = _sea_cell(0, neighbors=[1])
        deep = _sea_cell(2, water_depth_m=215.0, neighbors=[3])
        world = {
            "cells": [shallow, _land_cell(1, neighbors=[0]), deep, _land_cell(3, neighbors=[2])]
        }
        enrich_world_with_reef_diagnostics(world)

        self.assertAlmostEqual(
            shallow["reef_growth_index"] - deep["reef_growth_index"], 0.25, places=6
        )

    def test_wave_exposure_prefers_the_coastal_feature_over_the_wind_fallback(self) -> None:
        windy = _sea_cell(0, wind_east=3.0, wind_north=4.0, neighbors=[1])
        featured = _sea_cell(2, wind_east=3.0, wind_north=4.0, neighbors=[3])
        world = {
            "cells": [windy, _land_cell(1, neighbors=[0]), featured, _land_cell(3, neighbors=[2])],
            "coastal_features": [
                {"id": 4, "cell_id": 3, "type": "beach", "wave_energy_index": 0.42}
            ],
        }
        enrich_world_with_reef_diagnostics(world)

        self.assertEqual(windy["reef_wave_exposure_index"], 1.0)
        self.assertEqual(featured["reef_wave_exposure_index"], 0.42)
        self.assertGreater(featured["reef_growth_index"], windy["reef_growth_index"])

    def test_each_sediment_stress_term_carries_its_own_weight(self) -> None:
        """The saturating test below cannot see individual terms: once the sum
        exceeds 1.0 the clamp hides any one of them. Each row here stays well
        under the clamp so a single term is responsible for the whole value."""
        cases = {
            "control": ({}, {}, None, 0.0),
            "river": ({}, {"is_river": True}, None, 0.32),
            "delta": ({}, {"landform": "delta"}, None, 0.28),
            "floodplain": ({}, {"landform": "floodplain"}, None, 0.28),
            "half_runoff": ({}, {"runoff_mm_y": 650.0}, None, 0.09),
            "half_export": ({}, {"fluvial_sediment_routed_outgoing_m": 1.0}, None, 0.09),
            "feature_supply": ({}, {}, 0.5, 0.12),
            "local_sediment": ({"sediment_thickness_m": 2.0}, {}, None, 0.05),
        }
        for label, (sea_overrides, land_overrides, supply, expected) in cases.items():
            with self.subTest(label=label):
                sea = _sea_cell(0, neighbors=[1], **sea_overrides)
                land = _land_cell(1, neighbors=[0], **land_overrides)
                extra: dict[str, Any] = {}
                if supply is not None:
                    extra["coastal_features"] = [
                        {"id": 3, "cell_id": 1, "type": "beach", "sediment_supply_index": supply}
                    ]
                _reef_pair(sea, land, **extra)
                self.assertAlmostEqual(
                    sea["reef_sediment_stress_index"], expected, places=6
                )

    def test_sediment_stress_accumulates_every_source(self) -> None:
        muddy = _sea_cell(0, sediment_thickness_m=4.0, neighbors=[1])
        clean = _sea_cell(2, neighbors=[3])
        world = enrich_world_with_reef_diagnostics(
            {
                "cells": [
                    muddy,
                    _land_cell(
                        1,
                        neighbors=[0],
                        is_river=True,
                        landform="delta",
                        runoff_mm_y=1300.0,
                        fluvial_sediment_routed_outgoing_m=2.0,
                    ),
                    clean,
                    _land_cell(3, neighbors=[2]),
                ],
                "coastal_features": [
                    {"id": 3, "cell_id": 1, "sediment_supply_index": 1.0, "type": "beach"}
                ],
            }
        )

        self.assertEqual(muddy["reef_sediment_stress_index"], 1.0)
        self.assertEqual(clean["reef_sediment_stress_index"], 0.0)
        self.assertAlmostEqual(
            clean["reef_growth_index"] - muddy["reef_growth_index"], 0.22, places=6
        )
        self.assertEqual(len(world["reef_systems"]), 2)

    def test_river_alone_contributes_the_river_pressure_term(self) -> None:
        sea = _sea_cell(0, neighbors=[1])
        land = _land_cell(1, neighbors=[0], is_river=True)
        _reef_pair(sea, land)

        self.assertAlmostEqual(sea["reef_sediment_stress_index"], 0.32, places=6)

    def test_routed_sediment_export_overrides_the_legacy_export_field(self) -> None:
        legacy = _sea_cell(0, neighbors=[1])
        routed = _sea_cell(2, neighbors=[3])
        world = {
            "cells": [
                legacy,
                _land_cell(1, neighbors=[0], sediment_export_m=2.0),
                routed,
                _land_cell(3, neighbors=[2], sediment_export_m=2.0, fluvial_sediment_routed_outgoing_m=0.0),
            ]
        }
        enrich_world_with_reef_diagnostics(world)

        self.assertAlmostEqual(legacy["reef_sediment_stress_index"], 0.18, places=6)
        self.assertEqual(routed["reef_sediment_stress_index"], 0.0)

    def test_island_support_sums_landmass_volcanism_and_crust_age(self) -> None:
        cases = {
            "island_class": ({"island_class": "island"}, 0.248),
            "volcanic_landform": ({"landform": "volcanic_arc"}, 0.209),
            "basalt": ({"lithology": "basalt"}, 0.1596),
            "volcanic_potential": ({"volcanic_potential_index": 0.5}, 0.38),
            "young_crust": ({"crust_age_ma": 0.0}, 0.22),
            "half_aged_crust": ({"crust_age_ma": 60.0}, 0.11),
            "old_crust": ({"crust_age_ma": 200.0}, 0.0),
        }
        for label, (overrides, expected) in cases.items():
            with self.subTest(label=label):
                sea = _sea_cell(0, neighbors=[1])
                land = _land_cell(1, neighbors=[0], **overrides)
                _reef_pair(sea, land)
                self.assertAlmostEqual(sea["reef_island_support_index"], expected, places=6)

    def test_bleaching_risk_saturates_under_combined_heat_stress(self) -> None:
        hot = _sea_cell(
            0,
            temperature_c=36.0,
            climate_energy_stress_index=1.0,
            seasonal_aridity_index=1.0,
            ocean_current_temperature_c=5.0,
            neighbors=[1],
        )
        mild = _sea_cell(2, neighbors=[3])
        world = {
            "cells": [hot, _land_cell(1, neighbors=[0]), mild, _land_cell(3, neighbors=[2])]
        }
        enrich_world_with_reef_diagnostics(world)

        self.assertEqual(hot["reef_bleaching_risk_index"], 1.0)
        self.assertEqual(mild["reef_bleaching_risk_index"], 0.0)
        self.assertLess(hot["reef_growth_index"], mild["reef_growth_index"])

    def test_sea_ice_suppresses_reef_growth(self) -> None:
        iced = _sea_cell(0, ice_thickness_m=60.0, neighbors=[1])
        clear = _sea_cell(2, neighbors=[3])
        world = {
            "cells": [iced, _land_cell(1, neighbors=[0]), clear, _land_cell(3, neighbors=[2])]
        }
        enrich_world_with_reef_diagnostics(world)

        self.assertEqual(REEF_BASE["ice_thickness_m"], 0.0)
        self.assertGreaterEqual(clear["reef_growth_index"], 0.46)
        self.assertEqual(clear["reef_type"], "fringing_reef")
        self.assertAlmostEqual(
            clear["reef_growth_index"] - iced["reef_growth_index"], 0.54, places=6
        )
        self.assertLess(iced["reef_growth_index"], 0.46)
        self.assertEqual(iced["reef_type"], "none")

    def test_fishery_productivity_lifts_reef_growth(self) -> None:
        rich = _sea_cell(0, fishery_productivity_index=1.0, neighbors=[1])
        plain = _sea_cell(2, neighbors=[3])
        world = {
            "cells": [rich, _land_cell(1, neighbors=[0]), plain, _land_cell(3, neighbors=[2])]
        }
        enrich_world_with_reef_diagnostics(world)

        self.assertAlmostEqual(
            rich["reef_growth_index"] - plain["reef_growth_index"], 0.08, places=6
        )


class ReefSystemRecordTests(TestCase):
    def _world(self) -> dict[str, Any]:
        cells = [
            _sea_cell(0, neighbors=[1, 2], lat_deg=10.0, lon_deg=20.0, marine_region_id=5, water_depth_m=5.0),
            _sea_cell(1, neighbors=[0, 2, 3], lat_deg=10.0, lon_deg=20.0, marine_region_id=5, water_depth_m=15.0),
            _land_cell(2, neighbors=[0, 1], landmass_id=4, port_site_id=9, lithology="basalt"),
            _sea_cell(3, water_body_type="ocean", water_depth_m=3000.0, neighbors=[1], marine_region_id=6),
        ]
        return {
            "cells": cells,
            "coastal_features": [
                {"id": 11, "cell_id": 2, "type": "beach", "wave_energy_index": 0.42, "sediment_supply_index": 0.0}
            ],
            "settlements": [{"id": 21, "cell_id": 2}],
            "renewable_resource_records": [
                {"id": 31, "cell_id": 0, "resource_type": "fishery_productivity"},
                {"id": 32, "cell_id": 0, "resource_type": "timber_yield"},
                {"id": 33, "cell_id": 3, "resource_type": "fishery_productivity"},
            ],
        }

    def test_adjacent_reef_cells_form_one_linked_system(self) -> None:
        world = enrich_world_with_reef_diagnostics(self._world())
        records = world["reef_systems"]

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["id"], 0)
        self.assertEqual(record["cell_ids"], [0, 1])
        self.assertEqual(record["cell_count"], 2)
        self.assertEqual(record["reef_type"], "fringing_reef")
        self.assertEqual(record["reef_type_counts"], {"fringing_reef": 2})
        self.assertEqual(record["area_km2"], 200.0)
        self.assertAlmostEqual(record["centroid_lat_deg"], 10.0, places=4)
        self.assertAlmostEqual(record["centroid_lon_deg"], 20.0, places=4)
        self.assertEqual(record["adjacent_landmass_ids"], [4])
        self.assertEqual(record["marine_region_ids"], [5, 6])
        self.assertEqual(record["coastal_feature_ids"], [11])
        self.assertEqual(record["settlement_ids"], [21])
        self.assertEqual(record["port_site_ids"], [9])
        self.assertEqual(record["fishery_resource_record_ids"], [31])
        self.assertEqual(record["adjacent_volcanic_land_cell_count"], 2)
        self.assertEqual(record["mean_water_depth_m"], 10.0)
        self.assertEqual(record["mean_temperature_c"], 26.0)
        self.assertEqual(record["mean_fishery_productivity_index"], 0.0)
        self.assertEqual(world["cells"][0]["reef_system_id"], 0)
        self.assertEqual(world["cells"][1]["reef_system_id"], 0)
        self.assertEqual(world["cells"][3]["reef_system_id"], -1)

    def test_summary_counts_follow_the_records(self) -> None:
        world = enrich_world_with_reef_diagnostics(self._world())
        summary = world["summary"]

        self.assertEqual(summary["reef_system_count"], 1)
        self.assertEqual(summary["reef_cell_count"], 2)
        self.assertEqual(summary["reef_total_area_km2"], 200.0)
        self.assertEqual(summary["fringing_reef_system_count"], 1)
        self.assertEqual(summary["barrier_reef_system_count"], 0)
        self.assertEqual(summary["atoll_reef_system_count"], 0)
        self.assertEqual(summary["patch_reef_system_count"], 0)
        self.assertEqual(summary["cold_water_reef_system_count"], 0)
        self.assertEqual(summary["reef_type_counts"], {"fringing_reef": 1})
        self.assertAlmostEqual(
            summary["mean_reef_growth_index"],
            sum(cell["reef_growth_index"] for cell in world["cells"]) / 4.0,
            places=6,
        )

    def test_disconnected_reefs_become_separate_systems(self) -> None:
        cells = [
            _sea_cell(0, neighbors=[1]),
            _land_cell(1, neighbors=[0]),
            _sea_cell(2, neighbors=[3], temperature_c=17.0),
            _land_cell(3, neighbors=[2]),
        ]
        world = enrich_world_with_reef_diagnostics({"cells": cells})
        records = world["reef_systems"]

        self.assertEqual([record["id"] for record in records], [0, 1])
        self.assertEqual([record["cell_ids"] for record in records], [[0], [2]])
        self.assertEqual(
            [record["reef_type"] for record in records], ["fringing_reef", "cold_water_reef"]
        )
        self.assertEqual(world["summary"]["cold_water_reef_system_count"], 1)
        self.assertEqual(
            world["summary"]["reef_type_counts"], {"cold_water_reef": 1, "fringing_reef": 1}
        )

    def test_mixed_type_system_reports_the_alphabetically_first_of_a_tie(self) -> None:
        cells = [
            _sea_cell(0, neighbors=[1, 2]),
            _sea_cell(1, neighbors=[0, 2], temperature_c=17.0),
            _land_cell(2, neighbors=[0, 1]),
        ]
        world = enrich_world_with_reef_diagnostics({"cells": cells})
        record = world["reef_systems"][0]

        self.assertEqual(record["cell_ids"], [0, 1])
        self.assertEqual(record["reef_type_counts"], {"cold_water_reef": 1, "fringing_reef": 1})
        self.assertEqual(record["reef_type"], "cold_water_reef")


class ReefDiagnosticsRealWorldControlTests(TestCase):
    def test_rerunning_the_enricher_on_a_generated_world_is_stable(self) -> None:
        world = worlds.cached_world("replay_128")
        before = dict(world["summary"])
        systems = len(world["reef_systems"])

        enrich_world_with_reef_diagnostics(world)

        self.assertEqual(len(world["reef_systems"]), systems)
        for key, value in before.items():
            if "reef" in key:
                with self.subTest(key=key):
                    self.assertEqual(world["summary"][key], value)
        self.assertEqual(
            world["summary"]["reef_cell_count"],
            sum(1 for cell in world["cells"] if cell["reef_type"] != "none"),
        )


# --------------------------------------------------------------------------
# sedimentary_resource_systems
# --------------------------------------------------------------------------

SEDIMENT_BASE: dict[str, Any] = {
    "basin_id": 5,
    "lithology": "shale",
    "landform": "stable_lowland",
    "biome": "desert",
    "sediment_thickness_m": 2.0,
    "soil_salinity_index": 0.0,
    "is_closed_basin": False,
    "resource": "none",
}


def _sediment_cell(cell_id: int, **overrides: Any) -> dict[str, Any]:
    return _cell(cell_id, SEDIMENT_BASE, **overrides)


def _saline_cells(count: int = 2, **overrides: Any) -> list[dict[str, Any]]:
    """Closed saline cells: the evaporite potential alone keeps the system above
    ``SEDIMENTARY_SYSTEM_THRESHOLD`` regardless of column, history or deposits."""
    return [
        _sediment_cell(
            index,
            soil_salinity_index=1.0,
            is_closed_basin=True,
            landform="salt_flat",
            **overrides,
        )
        for index in range(count)
    ]


def _sediment_world(
    *,
    cells: list[dict[str, Any]] | None = None,
    basins: Any = None,
    basin: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    if cells is None:
        cells = [_sediment_cell(0), _sediment_cell(1)]
    if basins is None:
        default_basin: dict[str, Any] = {
            "id": 0,
            "basin_id": 5,
            "cell_count": 2,
            "mean_sediment_thickness_m": 0.0,
            "mean_subsidence_index": 0.0,
            "depositional_age_ma": 0.0,
            "dominant_resource": "none",
        }
        default_basin.update(basin or {})
        basins = [default_basin]
    world: dict[str, Any] = {"cells": cells, "sedimentary_basins": basins}
    world.update(extra)
    return enrich_world_with_sedimentary_resource_systems(world)


def _column(**overrides: Any) -> dict[str, Any]:
    column: dict[str, Any] = {
        "id": 3,
        "basin_id": 5,
        "preservation_potential": 0.5,
        "mean_accommodation_to_deposition_ratio": 1.0,
        "layers": [],
    }
    column.update(overrides)
    return column


class SedimentaryResourceGuardTests(TestCase):
    def test_missing_cells_or_basins_leave_the_world_untouched(self) -> None:
        cases = {
            "empty_cells": {"cells": [], "sedimentary_basins": []},
            # A non-empty non-list: only the isinstance check can reject it.
            "non_list_cells": {"cells": "ab", "sedimentary_basins": []},
            "non_list_basins": {"cells": [_sediment_cell(0)], "sedimentary_basins": None},
        }
        for label, world in cases.items():
            with self.subTest(label=label):
                result = enrich_world_with_sedimentary_resource_systems(dict(world))
                self.assertNotIn("sedimentary_resource_systems", result)
                self.assertNotIn("summary", result)

    def test_unusable_basins_are_skipped_but_the_summary_is_written(self) -> None:
        world = _sediment_world(
            basins=[
                "not-a-basin",
                {"id": 1, "basin_id": -1},
                {"id": 2, "basin_id": 404},
            ]
        )

        self.assertEqual(world["sedimentary_resource_systems"], [])
        summary = world["summary"]
        self.assertEqual(summary["sedimentary_resource_system_count"], 0)
        self.assertEqual(summary["sedimentary_resource_system_cell_count"], 0)
        self.assertEqual(summary["sedimentary_resource_system_total_area_km2"], 0.0)
        self.assertEqual(summary["mean_petroleum_potential_index"], 0.0)
        self.assertEqual(summary["mean_gas_potential_index"], 0.0)
        self.assertEqual(summary["mean_coal_potential_index"], 0.0)
        self.assertEqual(summary["mean_evaporite_salt_potential_index"], 0.0)
        self.assertEqual(summary["mean_sedimentary_resource_confidence_index"], 0.0)
        self.assertEqual(summary["sedimentary_resource_system_type_counts"], {})

    def test_barren_basin_below_threshold_is_dropped_unless_a_deposit_exists(self) -> None:
        barren = _sediment_world()
        self.assertEqual(barren["sedimentary_resource_systems"], [])

        with_deposit = _sediment_world(
            resource_deposits=[{"id": 8, "basin_id": 5, "resource": "evaporites"}]
        )
        systems = with_deposit["sedimentary_resource_systems"]
        self.assertEqual(len(systems), 1)
        self.assertEqual(systems[0]["resource_deposit_ids"], [8])
        self.assertEqual(systems[0]["evaporite_deposit_count"], 1)
        self.assertEqual(systems[0]["sedimentary_fuel_deposit_count"], 0)
        self.assertLess(systems[0]["petroleum_potential_index"], 0.42)

    def test_malformed_side_tables_fall_back_to_the_defaults(self) -> None:
        world = _sediment_world(
            cells=_saline_cells(),
            stratigraphic_columns=42,
            sediment_transport_histories=1.5,
            resource_deposits=None,
        )
        system = world["sedimentary_resource_systems"][0]

        self.assertEqual(system["stratigraphic_column_id"], -1)
        self.assertEqual(system["sediment_transport_history_id"], -1)
        self.assertEqual(system["resource_deposit_count"], 0)

    def test_malformed_side_table_entries_are_skipped(self) -> None:
        world = _sediment_world(
            cells=_saline_cells(),
            stratigraphic_columns=["broken", {"id": 3, "basin_id": -1}],
            sediment_transport_histories=["broken", {"id": 4, "basin_id": -1}],
            resource_deposits=[
                "broken",
                {"id": 8, "basin_id": -1, "resource": "evaporites"},
                {"id": 9, "basin_id": 5, "resource": "metals"},
            ],
        )
        system = world["sedimentary_resource_systems"][0]

        self.assertEqual(system["stratigraphic_column_id"], -1)
        self.assertEqual(system["sediment_transport_history_id"], -1)
        self.assertEqual(system["resource_deposit_ids"], [])

    def test_degenerate_columns_score_zero_layer_averages(self) -> None:
        cases = {
            "no_layers": _column(layers=[]),
            "non_list_layers": _column(layers="nope"),
            "non_dict_layers": _column(layers=["broken", 7]),
        }
        for label, column in cases.items():
            with self.subTest(label=label):
                world = _sediment_world(
                    cells=_saline_cells(),
                    stratigraphic_columns=[column],
                    basin={"mean_subsidence_index": 1.0},
                )
                system = world["sedimentary_resource_systems"][0]
                self.assertEqual(system["stratigraphic_column_id"], 3)
                self.assertAlmostEqual(system["source_rock_index"], 0.24, places=6)
                self.assertAlmostEqual(system["reservoir_quality_index"], 0.14, places=6)


class SedimentarySystemCellSelectionTests(TestCase):
    def test_only_sedimentary_candidate_cells_join_the_system(self) -> None:
        saline = {"soil_salinity_index": 1.0, "is_closed_basin": True}
        world = _sediment_world(
            cells=[
                _sediment_cell(0, sediment_thickness_m=3.0, lithology="granite", landform="mountain", **saline),
                _sediment_cell(1, sediment_thickness_m=0.0, lithology="sandstone", landform="mountain", **saline),
                _sediment_cell(2, sediment_thickness_m=0.0, lithology="granite", landform="delta", **saline),
                _sediment_cell(3, sediment_thickness_m=0.0, lithology="granite", landform="mountain", resource="evaporites", **saline),
                _sediment_cell(4, sediment_thickness_m=0.0, lithology="granite", landform="mountain", **saline),
                _sediment_cell(5, basin_id=-1, **saline),
            ],
            basin={"cell_count": 5},
        )
        system = world["sedimentary_resource_systems"][0]

        self.assertEqual(system["cell_ids"], [0, 1, 2, 3])
        self.assertEqual(system["cell_count"], 4)
        self.assertEqual(system["area_km2"], 400.0)
        self.assertEqual(world["summary"]["sedimentary_resource_system_cell_count"], 4)

    def test_a_basin_without_candidates_falls_back_to_every_basin_cell(self) -> None:
        world = _sediment_world(
            cells=_saline_cells(2, sediment_thickness_m=0.0, lithology="granite"),
        )
        system = world["sedimentary_resource_systems"][0]

        self.assertEqual(system["cell_ids"], [0, 1])
        self.assertEqual(system["dominant_lithology"], "granite")
        self.assertEqual(system["dominant_landform"], "salt_flat")


class SedimentarySystemTypeTests(TestCase):
    def test_evaporite_salt_system_is_reported_for_a_closed_saline_basin(self) -> None:
        world = _sediment_world(
            cells=[
                _sediment_cell(index, soil_salinity_index=1.0, is_closed_basin=True, landform="salt_flat")
                for index in (0, 1)
            ],
            resource_deposits=[{"id": 8, "basin_id": 5, "resource": "evaporites"}],
        )
        system = world["sedimentary_resource_systems"][0]

        self.assertEqual(system["system_type"], "evaporite_salt_system")
        self.assertGreater(system["evaporite_salt_potential_index"], 0.42)
        self.assertEqual(system["evaporite_deposit_count"], 1)
        self.assertEqual(system["dominant_landform"], "salt_flat")
        self.assertEqual(world["summary"]["evaporite_salt_system_count"], 1)

    def test_coal_basin_is_reported_for_wet_organic_floodplain_fill(self) -> None:
        world = _sediment_world(
            cells=[_sediment_cell(index, biome="wetland", landform="floodplain") for index in (0, 1)],
            stratigraphic_columns=[
                _column(
                    layers=[
                        {
                            "thickness_m": 10.0,
                            "facies": "floodplain_mud",
                            "organic_potential": 1.0,
                            "reservoir_quality": 0.0,
                            "seal_quality": 0.2,
                        }
                    ]
                )
            ],
            resource_deposits=[{"id": 8, "basin_id": 5, "resource": "sedimentary_fuels"}],
        )
        system = world["sedimentary_resource_systems"][0]

        self.assertEqual(system["system_type"], "coal_basin")
        self.assertGreater(system["coal_potential_index"], system["petroleum_potential_index"])
        self.assertEqual(system["sedimentary_fuel_deposit_count"], 1)
        self.assertEqual(system["stratigraphic_column_id"], 3)
        self.assertEqual(world["summary"]["coal_system_count"], 1)

    def test_petroleum_system_is_reported_for_a_reservoir_rich_column(self) -> None:
        world = _sediment_world(
            stratigraphic_columns=[
                _column(
                    layers=[
                        {
                            "thickness_m": 10.0,
                            "facies": "shallow_marine",
                            "organic_potential": 0.5,
                            "reservoir_quality": 1.0,
                            "seal_quality": 0.5,
                        }
                    ]
                )
            ],
            sediment_transport_histories=[
                {"id": 4, "basin_id": 5, "final_accommodation_fill_fraction": 0.8}
            ],
            resource_deposits=[{"id": 8, "basin_id": 5, "resource": "sedimentary_fuels"}],
            basin={
                "mean_sediment_thickness_m": 2.0,
                "mean_subsidence_index": 0.8,
                "depositional_age_ma": 60.0,
                "dominant_resource": "sedimentary_fuels",
            },
        )
        system = world["sedimentary_resource_systems"][0]

        self.assertEqual(system["system_type"], "petroleum_system")
        self.assertGreater(system["petroleum_potential_index"], system["gas_potential_index"] + 0.06)
        self.assertEqual(system["sediment_transport_history_id"], 4)
        self.assertEqual(system["depositional_age_ma"], 60.0)
        self.assertEqual(system["mean_sediment_thickness_m"], 2.0)
        self.assertEqual(world["summary"]["petroleum_system_count"], 1)

    def test_gas_system_is_reported_for_a_deep_mature_sealed_basin(self) -> None:
        world = _sediment_world(
            stratigraphic_columns=[
                _column(
                    preservation_potential=0.9,
                    mean_accommodation_to_deposition_ratio=1.8,
                    layers=[
                        {
                            "thickness_m": 10.0,
                            "facies": "deep_marine",
                            "organic_potential": 0.6,
                            "reservoir_quality": 0.0,
                            "seal_quality": 0.9,
                        }
                    ],
                )
            ],
            sediment_transport_histories=[
                {"id": 4, "basin_id": 5, "final_accommodation_fill_fraction": 1.25}
            ],
            basin={
                "mean_sediment_thickness_m": 8.0,
                "mean_subsidence_index": 0.9,
                "depositional_age_ma": 180.0,
            },
        )
        system = world["sedimentary_resource_systems"][0]

        self.assertEqual(system["system_type"], "gas_system")
        self.assertGreater(system["gas_potential_index"], system["petroleum_potential_index"] + 0.06)
        self.assertGreater(system["seal_quality_index"], 0.7)
        self.assertEqual(world["summary"]["gas_system_count"], 1)

    def test_near_tied_leaders_are_reported_as_a_mixed_system(self) -> None:
        world = _sediment_world(
            stratigraphic_columns=[
                _column(
                    layers=[
                        {
                            "thickness_m": 10.0,
                            "facies": "deltaic_sand",
                            "organic_potential": 0.62,
                            "reservoir_quality": 0.62,
                            "seal_quality": 0.62,
                        }
                    ]
                )
            ],
            basin={
                "mean_sediment_thickness_m": 8.0,
                "mean_subsidence_index": 0.5,
                "depositional_age_ma": 99.0,
            },
        )
        system = world["sedimentary_resource_systems"][0]

        self.assertEqual(system["system_type"], "mixed_sedimentary_resource")
        ranked = sorted(
            (
                system["petroleum_potential_index"],
                system["gas_potential_index"],
                system["coal_potential_index"],
                system["evaporite_salt_potential_index"],
            ),
            reverse=True,
        )
        self.assertGreaterEqual(ranked[1], 0.42)
        self.assertLessEqual(ranked[0] - ranked[1], 0.06)
        self.assertEqual(
            world["summary"]["sedimentary_resource_system_type_counts"],
            {"mixed_sedimentary_resource": 1},
        )

    def test_summary_means_average_the_reported_systems(self) -> None:
        world = _sediment_world(
            cells=[
                _sediment_cell(0, soil_salinity_index=1.0, is_closed_basin=True, landform="salt_flat"),
                _sediment_cell(1, soil_salinity_index=1.0, is_closed_basin=True, landform="salt_flat"),
                _sediment_cell(2, basin_id=6, soil_salinity_index=1.0, is_closed_basin=True, landform="salt_flat"),
            ],
            basins=[
                {"id": 0, "basin_id": 5, "cell_count": 2},
                {"id": 1, "basin_id": 6, "cell_count": 1},
            ],
        )
        systems = world["sedimentary_resource_systems"]
        summary = world["summary"]

        self.assertEqual(len(systems), 2)
        self.assertEqual([system["id"] for system in systems], [0, 1])
        self.assertEqual([system["basin_id"] for system in systems], [5, 6])
        self.assertEqual(summary["sedimentary_resource_system_count"], 2)
        self.assertEqual(summary["sedimentary_resource_system_cell_count"], 3)
        self.assertEqual(summary["sedimentary_resource_system_total_area_km2"], 300.0)
        self.assertAlmostEqual(
            summary["mean_evaporite_salt_potential_index"],
            sum(system["evaporite_salt_potential_index"] for system in systems) / 2.0,
            places=6,
        )
        self.assertAlmostEqual(
            summary["mean_sedimentary_resource_confidence_index"],
            sum(system["system_confidence_index"] for system in systems) / 2.0,
            places=6,
        )
        self.assertGreater(systems[0]["system_confidence_index"], systems[1]["system_confidence_index"])


class SedimentaryResourceRealWorldControlTests(TestCase):
    def test_rerunning_the_enricher_on_a_generated_world_is_stable(self) -> None:
        world = worlds.cached_world("replay_128")
        before = dict(world["summary"])
        systems = len(world["sedimentary_resource_systems"])

        enrich_world_with_sedimentary_resource_systems(world)

        self.assertEqual(len(world["sedimentary_resource_systems"]), systems)
        for key, value in before.items():
            if "sedimentary_resource" in key or key.endswith("_system_count"):
                with self.subTest(key=key):
                    self.assertEqual(world["summary"][key], value)
