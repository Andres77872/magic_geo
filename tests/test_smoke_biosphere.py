"""Soils, biomes, ecosystems, and disturbance assertions for the generated world.

Split out of the former single-method smoke test: each method re-derives
what it needs from the shared world, so they no longer depend on order.
"""

from __future__ import annotations

from unittest import TestCase

from magic_geo.natural_water_validation_dispatch import validate_public_natural_water_chain
from support import worlds


class SmokeBiosphereTests(TestCase):
    def test_biome_diagnostics(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertEqual(summary["biome_diagnostic_count"], len(world["biome_diagnostics"]))
        self.assertEqual(summary["biome_diagnostic_count"], len(world["cells"]))
        self.assertEqual(
            sum(summary["biome_limiting_factor_counts"].values()),
            summary["biome_diagnostic_count"],
        )
        self.assertEqual(
            summary["biome_transition_zone_count"],
            sum(1 for diagnostic in world["biome_diagnostics"] if diagnostic["biome_transition_zone"]),
        )
        self.assertEqual(
            summary["high_fire_frequency_biome_count"],
            sum(1 for diagnostic in world["biome_diagnostics"] if diagnostic["fire_frequency_index"] >= 0.65),
        )
        self.assertGreaterEqual(summary["water_stressed_biome_cell_fraction"], 0.0)
        self.assertLessEqual(summary["water_stressed_biome_cell_fraction"], 1.0)
        self.assertGreaterEqual(summary["biome_expected_match_fraction"], 0.0)
        self.assertLessEqual(summary["biome_expected_match_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_potential_evapotranspiration_mm_y"], 0.0)
        self.assertGreaterEqual(summary["mean_climatic_water_deficit_mm_y"], 0.0)
        self.assertGreaterEqual(summary["mean_growing_season_months"], 0.0)
        self.assertLessEqual(summary["mean_growing_season_months"], 12.0)
        for key in ("mean_fire_frequency_index", "mean_biome_confidence_index", "mean_ecotone_index"):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertAlmostEqual(
            summary["mean_fire_frequency_index"],
            sum(diagnostic["fire_frequency_index"] for diagnostic in world["biome_diagnostics"])
            / len(world["biome_diagnostics"]),
            delta=0.001,
        )
        self.assertAlmostEqual(
            summary["mean_potential_evapotranspiration_mm_y"],
            sum(diagnostic["potential_evapotranspiration_mm_y"] for diagnostic in world["biome_diagnostics"])
            / len(world["biome_diagnostics"]),
            delta=0.001,
        )
        ecotone_cells = [cell for cell in world["cells"] if cell["biome_ecotone_type"] != "none"]
        self.assertEqual(summary["biome_ecotone_cell_count"], len(ecotone_cells))
        self.assertEqual(summary["biome_ecotone_region_count"], len(world["biome_ecotone_regions"]))
        self.assertEqual(sum(summary["biome_ecotone_type_counts"].values()), summary["cell_count"])
        self.assertEqual(
            summary["mangrove_ecotone_cell_count"],
            sum(1 for cell in world["cells"] if cell["biome_ecotone_type"] == "mangrove"),
        )
        self.assertEqual(
            summary["cloud_forest_ecotone_cell_count"],
            sum(1 for cell in world["cells"] if cell["biome_ecotone_type"] == "cloud_forest"),
        )
        self.assertEqual(
            summary["alpine_paramo_ecotone_cell_count"],
            sum(1 for cell in world["cells"] if cell["biome_ecotone_type"] == "alpine_paramo"),
        )
        self.assertGreater(summary["biome_ecotone_cell_count"], 0)
        self.assertGreaterEqual(summary["mean_biome_ecotone_confidence"], 0.0)
        self.assertLessEqual(summary["mean_biome_ecotone_confidence"], 1.0)
        self.assertEqual(
            {cell_id for region in world["biome_ecotone_regions"] for cell_id in region["cell_ids"]},
            {cell["id"] for cell in ecotone_cells},
        )
        self.assertEqual(summary["biome_realism_check_count"], len(world["biome_realism_checks"]))
        self.assertGreaterEqual(summary["biome_realism_check_count"], 5)
        self.assertEqual(
            summary["biome_realism_pass_count"],
            sum(1 for check in world["biome_realism_checks"] if check["passed"]),
        )
        self.assertGreaterEqual(summary["biome_realism_pass_fraction"], 0.0)
        self.assertLessEqual(summary["biome_realism_pass_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_biome_realism_score"], 0.0)
        self.assertLessEqual(summary["mean_biome_realism_score"], 1.0)
        for key in [
            "desert_water_deficit_alignment_index",
            "forest_water_availability_index",
            "tundra_cold_altitude_index",
            "savanna_seasonality_index",
            "mangrove_warm_wet_coast_index",
        ]:
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        biome_realism_names = {check["name"] for check in world["biome_realism_checks"]}
        self.assertTrue(
            {
                "desert_water_deficit_alignment",
                "forest_water_availability_alignment",
                "tundra_cold_altitude_alignment",
                "savanna_seasonality_alignment",
                "mangrove_warm_wet_coast_constraint",
            }.issubset(biome_realism_names)
        )
        first_biome_check = world["biome_realism_checks"][0]
        self.assertEqual(first_biome_check["domain"], "biomes")
        self.assertIn("evidence", first_biome_check)
        self.assertGreaterEqual(first_biome_check["score"], 0.0)
        self.assertLessEqual(first_biome_check["score"], 1.0)
        aquifer_cells = [cell for cell in world["cells"] if cell["aquifer_class"] != "marine_excluded"]
        self.assertEqual(summary["aquifer_cell_count"], len(aquifer_cells))
    def test_vegetation_succession_histories(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertEqual(summary["vegetation_succession_history_count"], len(world["vegetation_succession_histories"]))
        self.assertEqual(
            summary["vegetation_succession_step_count"],
            sum(history["step_count"] for history in world["vegetation_succession_histories"]),
        )
        self.assertEqual(sum(summary["vegetation_succession_stage_counts"].values()), summary["cell_count"])
        for key in (
            "mean_primary_productivity_index",
            "mean_vegetation_biomass_index",
            "mean_species_richness_index",
            "mean_wildfire_spread_risk_index",
            "mean_ecosystem_disturbance_pressure_index",
            "mature_vegetation_cell_fraction",
            "mean_forest_growth_index",
            "mean_fishery_productivity_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertEqual(
            summary["high_wildfire_spread_risk_cell_count"],
            sum(1 for cell in world["cells"] if cell["wildfire_spread_risk_index"] >= 0.65),
        )
        self.assertEqual(summary["renewable_resource_record_count"], len(world["renewable_resource_records"]))
        self.assertEqual(
            summary["forest_growth_resource_count"],
            sum(1 for record in world["renewable_resource_records"] if record["resource_type"] == "forest_growth"),
        )
        self.assertEqual(
            summary["fishery_productivity_resource_count"],
            sum(1 for record in world["renewable_resource_records"] if record["resource_type"] == "fishery_productivity"),
        )
        self.assertEqual(
            sum(summary["renewable_resource_type_counts"].values()),
            summary["renewable_resource_record_count"],
        )
        self.assertAlmostEqual(
            summary["mean_primary_productivity_index"],
            sum(cell["primary_productivity_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        self.assertEqual(summary["species_range_record_count"], len(world["species_range_records"]))
        species_range_cell_ids = {
            cell_id for record in world["species_range_records"] for cell_id in record["cell_ids"]
        }
        self.assertEqual(summary["species_range_cell_count"], len(species_range_cell_ids))
        self.assertEqual(
            sum(summary["species_guild_type_counts"].values()),
            summary["species_range_record_count"],
        )
        self.assertEqual(
            sum(summary["species_habitat_class_counts"].values()),
            summary["species_range_record_count"],
        )
        self.assertEqual(
            sum(summary["dominant_species_guild_counts"].values()),
            summary["cell_count"],
        )
        self.assertEqual(
            summary["terrestrial_species_range_count"],
            sum(1 for record in world["species_range_records"] if record["habitat_class"] in {"terrestrial", "arid", "alpine"}),
        )
        self.assertEqual(
            summary["aquatic_species_range_count"],
            sum(1 for record in world["species_range_records"] if record["habitat_class"] in {"freshwater", "marine", "reef"}),
        )
        self.assertEqual(
            summary["wetland_species_range_count"],
            sum(1 for record in world["species_range_records"] if record["habitat_class"] == "wetland"),
        )
        for key in (
            "mean_species_habitat_suitability_index",
            "mean_species_endemism_index",
            "mean_species_composition_confidence_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertAlmostEqual(
            summary["mean_species_habitat_suitability_index"],
            sum(cell["species_habitat_suitability_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        self.assertGreaterEqual(summary["species_range_total_area_km2"], 0.0)
        self.assertEqual(summary["wildfire_spread_history_count"], len(world["wildfire_spread_histories"]))
        wildfire_cell_ids = {
            cell_id for history in world["wildfire_spread_histories"] for cell_id in history["cell_ids"]
        }
        self.assertEqual(summary["wildfire_disturbance_cell_count"], len(wildfire_cell_ids))
        self.assertEqual(
            summary["wildfire_spread_step_count"],
            sum(history["spread_step_count"] for history in world["wildfire_spread_histories"]),
        )
        self.assertEqual(
            summary["high_wildfire_ignition_potential_cell_count"],
            sum(1 for cell in world["cells"] if cell["wildfire_ignition_potential_index"] >= 0.28),
        )
        self.assertEqual(
            summary["high_wildfire_fuel_continuity_cell_count"],
            sum(1 for cell in world["cells"] if cell["wildfire_fuel_continuity_index"] >= 0.35),
        )
        self.assertEqual(
            summary["high_wildfire_firebreak_cell_count"],
            sum(1 for cell in world["cells"] if cell["wildfire_firebreak_index"] >= 0.55),
        )
        self.assertEqual(sum(summary["wildfire_disturbance_regime_counts"].values()), summary["cell_count"])
        for key in (
            "mean_wildfire_ignition_potential_index",
            "mean_wildfire_fuel_continuity_index",
            "mean_wildfire_wind_alignment_index",
            "mean_wildfire_firebreak_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertGreaterEqual(summary["wildfire_total_burned_area_km2"], 0.0)
        resource_cells = [cell for cell in world["cells"] if cell["resource"] != "none"]
    def test_soil_profiles(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        soil_cells = [cell for cell in world["cells"] if cell["soil_texture_class"] != "none"]
        self.assertEqual(summary["soil_profile_count"], len(world["soil_profiles"]))
        self.assertEqual(summary["soil_profile_count"], len(soil_cells))
        self.assertEqual(summary["soil_horizon_count"], len(world["soil_horizons"]))
        self.assertEqual(summary["soil_horizon_count"], sum(profile["horizon_count"] for profile in world["soil_profiles"]))
        self.assertEqual(summary["soil_profile_history_count"], len(world["soil_profile_histories"]))
        self.assertEqual(summary["soil_profile_history_count"], len(world["soil_profiles"]))
        self.assertEqual(
            summary["soil_pedogenesis_step_count"],
            sum(history["step_count"] for history in world["soil_profile_histories"]),
        )
        self.assertEqual(sum(summary["soil_profile_class_counts"].values()), summary["soil_profile_count"])
        self.assertIn("mean_soil_drainage_index", summary)
        self.assertIn("mean_soil_moisture_index", summary)
        self.assertIn("mean_soil_ph", summary)
        self.assertIn("mean_soil_organic_matter_fraction", summary)
        self.assertIn("mean_soil_salinity_index", summary)
        self.assertIn("mean_soil_erodibility_index", summary)
        self.assertIn("mean_soil_profile_development_index", summary)
        self.assertIn("saline_soil_cell_fraction", summary)
        self.assertIn("high_erodibility_soil_fraction", summary)
        self.assertIn("waterlogged_soil_cell_fraction", summary)
        self.assertIn("mean_soil_profile_depth_m", summary)
        self.assertIn("mean_soil_horizon_count", summary)
        self.assertIn("mean_topsoil_organic_matter_fraction", summary)
        self.assertIn("mean_soil_weathering_index", summary)
        self.assertIn("mean_soil_leaching_index", summary)
        self.assertIn("mean_soil_bioturbation_index", summary)
        self.assertIn("mature_soil_profile_fraction", summary)
        self.assertIn("shallow_soil_profile_fraction", summary)
        self.assertIn("total_soil_production_m", summary)
        self.assertIn("total_soil_erosion_loss_m", summary)
        self.assertIn("mean_pedogenic_weathering_index", summary)
        self.assertIn("mean_pedogenic_leaching_index", summary)
        self.assertIn("mean_pedogenic_bioturbation_index", summary)
        self.assertIn("mean_horizon_differentiation_index", summary)
        self.assertIn("mean_pedogenic_flux_index", summary)
        self.assertIn("high_erosion_pedogenesis_count", summary)
        self.assertGreaterEqual(summary["mean_soil_drainage_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_drainage_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_moisture_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_moisture_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_ph"], 3.5)
        self.assertLessEqual(summary["mean_soil_ph"], 9.5)
        self.assertGreaterEqual(summary["mean_soil_organic_matter_fraction"], 0.0)
        self.assertLessEqual(summary["mean_soil_organic_matter_fraction"], 0.5)
        self.assertGreaterEqual(summary["mean_soil_salinity_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_salinity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_erodibility_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_erodibility_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_profile_development_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_profile_development_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_profile_depth_m"], 0.0)
        self.assertGreaterEqual(summary["mean_soil_horizon_count"], 0.0)
        self.assertGreaterEqual(summary["mean_topsoil_organic_matter_fraction"], 0.0)
        self.assertLessEqual(summary["mean_topsoil_organic_matter_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_weathering_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_weathering_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_leaching_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_leaching_index"], 1.0)
        self.assertGreaterEqual(summary["mean_soil_bioturbation_index"], 0.0)
        self.assertLessEqual(summary["mean_soil_bioturbation_index"], 1.0)
        self.assertGreaterEqual(summary["mature_soil_profile_fraction"], 0.0)
        self.assertLessEqual(summary["mature_soil_profile_fraction"], 1.0)
        self.assertGreaterEqual(summary["shallow_soil_profile_fraction"], 0.0)
        self.assertLessEqual(summary["shallow_soil_profile_fraction"], 1.0)
        self.assertGreaterEqual(summary["total_soil_production_m"], 0.0)
        self.assertGreaterEqual(summary["total_soil_erosion_loss_m"], 0.0)
        self.assertGreaterEqual(summary["mean_pedogenic_weathering_index"], 0.0)
        self.assertLessEqual(summary["mean_pedogenic_weathering_index"], 1.0)
        self.assertGreaterEqual(summary["mean_pedogenic_leaching_index"], 0.0)
        self.assertLessEqual(summary["mean_pedogenic_leaching_index"], 1.0)
        self.assertGreaterEqual(summary["mean_pedogenic_bioturbation_index"], 0.0)
        self.assertLessEqual(summary["mean_pedogenic_bioturbation_index"], 1.0)
        self.assertGreaterEqual(summary["mean_horizon_differentiation_index"], 0.0)
        self.assertLessEqual(summary["mean_horizon_differentiation_index"], 1.0)
        self.assertGreaterEqual(summary["mean_pedogenic_flux_index"], 0.0)
        self.assertLessEqual(summary["mean_pedogenic_flux_index"], 1.0)
        if soil_cells:
            self.assertAlmostEqual(
                summary["mean_soil_drainage_index"],
                sum(cell["soil_drainage_index"] for cell in soil_cells) / len(soil_cells),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["mean_soil_ph"],
                sum(cell["soil_ph"] for cell in soil_cells) / len(soil_cells),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["mean_soil_profile_depth_m"],
                sum(profile["total_depth_m"] for profile in world["soil_profiles"]) / len(world["soil_profiles"]),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["total_soil_production_m"],
                sum(history["total_soil_production_m"] for history in world["soil_profile_histories"]),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["mean_pedogenic_flux_index"],
                sum(history["mean_pedogenic_flux_index"] for history in world["soil_profile_histories"])
                / len(world["soil_profile_histories"]),
                delta=0.001,
            )
            self.assertEqual(
                summary["high_erosion_pedogenesis_count"],
                sum(1 for history in world["soil_profile_histories"] if history["high_erosion_pressure"]),
            )
        self.assertGreater(summary["settlement_count"], 0)

        first_cell = world["cells"][0]
        self.assertEqual(len(first_cell["temperature_monthly_c"]), 12)
        self.assertEqual(len(first_cell["precipitation_monthly_mm"]), 12)
        self.assertIn("political_region_id", first_cell)
        self.assertIn("culture_region_id", first_cell)
        self.assertIn("language_region_id", first_cell)
        self.assertIn("water_body_type", first_cell)
        self.assertIn("landmass_id", first_cell)
        self.assertIn("island_class", first_cell)
        self.assertIn("marine_region_id", first_cell)
        self.assertIn("marine_chokepoint_id", first_cell)
        self.assertIn("river_navigability_index", first_cell)
        self.assertIn("coastal_navigability_index", first_cell)
        self.assertIn("harbor_suitability_index", first_cell)
        self.assertIn("transport_chokepoint_index", first_cell)
        self.assertIn("navigability_index", first_cell)
        self.assertIn("navigability_class", first_cell)
        self.assertIn("navigable_waterway_id", first_cell)
        for key in (
            "river_channel_width_m",
            "river_channel_depth_m",
            "bankfull_discharge_m3_s",
            "channel_slope_index",
            "stream_power_index",
            "floodplain_connectivity_index",
            "channel_morphology_class",
            "river_channel_system_id",
        ):
            self.assertIn(key, first_cell)
        self.assertIn("basin_id", first_cell)
        self.assertIn("spill_to", first_cell)
        self.assertIn("depression_component_id", first_cell)
        self.assertIn("depression_sink_cell_id", first_cell)
        self.assertIn("lake_basin_id", first_cell)
        self.assertIn("depression_policy", first_cell)
        self.assertIn("filled_elevation_m", first_cell)
        self.assertIn("hydrologic_surface_elevation_m", first_cell)
        self.assertIn("hydrologic_flow_drop_m", first_cell)
        self.assertIn("hydrologic_flow_slope", first_cell)
        self.assertIn("hydrologic_surface_conditioned", first_cell)
        self.assertIn("depression_depth_m", first_cell)
        self.assertIn("spill_elevation_m", first_cell)
        self.assertIn("lake_fill_fraction", first_cell)
        self.assertIn("is_closed_basin", first_cell)
        self.assertIn("lake_overflows", first_cell)
        self.assertIn("overflow_channel_active", first_cell)
        self.assertIn("overflow_channel_incision_m", first_cell)
        self.assertIn("overflow_channel_sediment_evacuated_km3", first_cell)
        self.assertIn("overflow_channel_avulsion_risk", first_cell)
        self.assertGreaterEqual(first_cell["overflow_channel_incision_m"], 0.0)
        self.assertGreaterEqual(first_cell["overflow_channel_sediment_evacuated_km3"], 0.0)
        self.assertGreaterEqual(first_cell["overflow_channel_avulsion_risk"], 0.0)
        self.assertLessEqual(first_cell["overflow_channel_avulsion_risk"], 1.0)
        land_cells = [cell for cell in world["cells"] if not cell["is_water"]]
        marine_cells = [
            cell
            for cell in world["cells"]
            if cell["water_body_type"] in {"ocean", "continental_shelf", "inland_sea"}
        ]
    def test_soil_profiles_2(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        self.assertEqual(validate_public_natural_water_chain(world), (True, []))
        self.assertTrue(all("aquifer_extraction_risk_index" not in cell for cell in world["cells"]))
        self.assertNotIn("mean_aquifer_extraction_risk_index", world["summary"])
        self.assertNotIn("groundwater_stressed_cell_count", world["summary"])
        first_cell = world["cells"][0]
        if world["soil_profiles"]:
            first_profile = world["soil_profiles"][0]
            self.assertIn("cell_id", first_profile)
            self.assertIn("horizon_ids", first_profile)
            self.assertIn("horizon_count", first_profile)
            self.assertIn("total_depth_m", first_profile)
            self.assertIn("parent_material", first_profile)
            self.assertIn("profile_class", first_profile)
            self.assertIn("soil_profile_history_id", first_profile)
            self.assertIn("weathering_index", first_profile)
            self.assertIn("leaching_index", first_profile)
            self.assertIn("bioturbation_index", first_profile)
            self.assertEqual(first_profile["horizon_count"], len(first_profile["horizon_ids"]))
            self.assertGreater(first_profile["total_depth_m"], 0.0)
            for key in ("drainage_index", "moisture_index", "salinity_index", "erodibility_index", "development_index", "weathering_index", "leaching_index", "bioturbation_index"):
                self.assertGreaterEqual(first_profile[key], 0.0)
                self.assertLessEqual(first_profile[key], 1.0)
            first_soil_history = world["soil_profile_histories"][first_profile["soil_profile_history_id"]]
            self.assertEqual(first_soil_history["soil_profile_id"], first_profile["id"])
            self.assertEqual(first_soil_history["cell_id"], first_profile["cell_id"])
            self.assertEqual(first_soil_history["horizon_count"], len(first_soil_history["horizon_ids"]))
            self.assertEqual(first_soil_history["horizon_ids"], first_profile["horizon_ids"])
            self.assertEqual(first_soil_history["parent_material"], first_profile["parent_material"])
            self.assertEqual(first_soil_history["profile_class"], first_profile["profile_class"])
            self.assertEqual(first_soil_history["step_count"], len(first_soil_history["steps"]))
            self.assertGreaterEqual(first_soil_history["initial_depth_m"], 0.0)
            self.assertGreater(first_soil_history["final_depth_m"], 0.0)
            self.assertAlmostEqual(first_soil_history["final_depth_m"], first_profile["total_depth_m"], delta=0.001)
            self.assertAlmostEqual(first_soil_history["final_profile_age_ka"], first_profile["profile_age_ka"], delta=0.001)
            self.assertGreaterEqual(first_soil_history["total_soil_production_m"], 0.0)
            self.assertGreaterEqual(first_soil_history["total_erosion_loss_m"], 0.0)
            self.assertIsInstance(first_soil_history["high_erosion_pressure"], bool)
            for key in (
                "mean_weathering_index",
                "mean_leaching_index",
                "mean_bioturbation_index",
                "mean_horizon_differentiation_index",
                "mean_pedogenic_flux_index",
            ):
                self.assertGreaterEqual(first_soil_history[key], 0.0)
                self.assertLessEqual(first_soil_history[key], 1.0)
            previous_end_depth = first_soil_history["initial_depth_m"]
            for index, step in enumerate(first_soil_history["steps"]):
                self.assertEqual(step["stage_index"], index + 1)
                self.assertIn("era_id", step)
                self.assertGreaterEqual(step["start_year_bp"], step["end_year_bp"])
                self.assertAlmostEqual(step["start_depth_m"], previous_end_depth, delta=0.001)
                self.assertGreaterEqual(step["end_depth_m"], 0.0)
                self.assertGreaterEqual(step["soil_production_m"], 0.0)
                self.assertGreaterEqual(step["erosion_loss_m"], 0.0)
                for key in (
                    "weathering_index",
                    "leaching_index",
                    "bioturbation_index",
                    "organic_accumulation_index",
                    "horizon_differentiation_index",
                    "clay_translocation_index",
                    "carbonate_mobilization_index",
                    "salinization_index",
                    "erosion_pressure_index",
                    "pedogenic_flux_index",
                ):
                    self.assertGreaterEqual(step[key], 0.0)
                    self.assertLessEqual(step[key], 1.0)
                previous_end_depth = step["end_depth_m"]
            self.assertAlmostEqual(
                first_soil_history["steps"][-1]["end_depth_m"],
                first_soil_history["final_depth_m"],
                delta=max(0.001, first_soil_history["final_depth_m"] * 0.0001),
            )
            first_horizon = world["soil_horizons"][first_profile["horizon_ids"][0]]
            self.assertEqual(first_horizon["soil_profile_id"], first_profile["id"])
            self.assertEqual(first_horizon["cell_id"], first_profile["cell_id"])
            self.assertGreater(first_horizon["thickness_m"], 0.0)
            self.assertAlmostEqual(
                first_horizon["bottom_depth_m"] - first_horizon["top_depth_m"],
                first_horizon["thickness_m"],
                delta=max(0.001, first_horizon["thickness_m"] * 0.0001),
            )
            self.assertAlmostEqual(
                first_horizon["sand_fraction"] + first_horizon["silt_fraction"] + first_horizon["clay_fraction"],
                1.0,
                delta=0.001,
            )
            for key in ("organic_matter_fraction", "carbonate_index", "salinity_index", "root_density_index", "weathering_index"):
                self.assertGreaterEqual(first_horizon[key], 0.0)
                self.assertLessEqual(first_horizon[key], 1.0)
        first_biome_diagnostic = world["biome_diagnostics"][0]
        self.assertEqual(first_biome_diagnostic["id"], 0)
        self.assertEqual(first_biome_diagnostic["cell_id"], first_cell["id"])
        self.assertEqual(first_biome_diagnostic["biome"], first_cell["biome"])
        self.assertTrue(first_biome_diagnostic["expected_biome"])
        self.assertTrue(first_biome_diagnostic["limiting_factor"])
        self.assertGreaterEqual(first_biome_diagnostic["potential_evapotranspiration_mm_y"], 0.0)
        self.assertGreaterEqual(first_biome_diagnostic["climatic_water_deficit_mm_y"], 0.0)
        self.assertGreaterEqual(first_biome_diagnostic["climatic_water_surplus_mm_y"], 0.0)
        self.assertGreaterEqual(first_biome_diagnostic["growing_season_months"], 0)
        self.assertLessEqual(first_biome_diagnostic["growing_season_months"], 12)
        self.assertGreaterEqual(first_biome_diagnostic["frost_months"], 0)
        self.assertLessEqual(first_biome_diagnostic["frost_months"], 12)
        self.assertGreaterEqual(first_biome_diagnostic["dry_season_months"], 0)
        self.assertLessEqual(first_biome_diagnostic["dry_season_months"], 12)
        self.assertGreaterEqual(first_biome_diagnostic["wet_season_months"], 0)
        self.assertLessEqual(first_biome_diagnostic["wet_season_months"], 12)
        for key in (
            "soil_moisture_index",
            "seasonal_aridity_index",
            "fire_frequency_index",
            "ecotone_index",
            "biome_confidence_index",
        ):
            self.assertGreaterEqual(first_biome_diagnostic[key], 0.0)
            self.assertLessEqual(first_biome_diagnostic[key], 1.0)
        self.assertIsInstance(first_biome_diagnostic["biome_transition_zone"], bool)
        self.assertAlmostEqual(
            first_biome_diagnostic["potential_evapotranspiration_mm_y"],
            first_cell["potential_evapotranspiration_mm_y"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            first_biome_diagnostic["climatic_water_deficit_mm_y"],
            first_cell["climatic_water_deficit_mm_y"],
            delta=0.001,
        )
        for key in (
            "biome_ecotone_type",
            "biome_ecotone_confidence",
            "biome_ecotone_region_id",
        ):
            self.assertIn(key, first_cell)
        self.assertTrue(first_cell["biome_ecotone_type"])
        self.assertGreaterEqual(first_cell["biome_ecotone_confidence"], 0.0)
        self.assertLessEqual(first_cell["biome_ecotone_confidence"], 1.0)
        self.assertGreaterEqual(first_cell["biome_ecotone_region_id"], -1)
        for key in (
            "groundwater_recharge_mm_y",
            "groundwater_recharge_km3_y",
            "aquifer_storage_index",
            "aquifer_quality_index",
            "aquifer_productivity_index",
            "aquifer_natural_limitation_index",
            "aquifer_class",
            "aquifer_system_id",
            "groundwater_hydraulic_head_m",
            "groundwater_gradient_index",
            "groundwater_lateral_flow_km3_y",
            "groundwater_lateral_inflow_km3_y",
            "groundwater_available_volume_km3_y",
            "groundwater_internal_lateral_outflow_km3_y",
            "groundwater_discharge_mm_y",
            "groundwater_discharge_km3_y",
            "groundwater_retained_storage_km3_y",
            "groundwater_flow_mass_balance_residual_km3_y",
            "groundwater_flow_to_cell_id",
            "spring_discharge_index",
            "baseflow_support_index",
            "groundwater_flow_regime",
            "groundwater_flow_system_id",
            "actual_evapotranspiration_mm_y",
            "infiltration_capacity_index",
            "infiltration_mm_y",
            "hydrologic_water_balance_mm_y",
            "water_budget_runoff_mm_y",
            "runoff_budget_residual_mm_y",
            "runoff_budget_consistency_index",
            "hydrologic_deficit_mm_y",
            "runoff_generation_fraction",
            "hydrologic_budget_class",
            "hydrologic_budget_region_id",
            "wetland_extent_index",
            "wetland_hydrology_index",
            "wetland_soil_saturation_index",
            "wetland_ecotone_index",
            "wetland_connectivity_index",
            "wetland_coastal_flag",
            "wetland_system_type",
            "wetland_system_id",
            "karst_potential_index",
            "cave_development_index",
            "subterranean_drainage_fraction",
            "karst_system_id",
        ):
            self.assertIn(key, first_cell)
        self.assertGreaterEqual(first_cell["groundwater_recharge_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["groundwater_recharge_km3_y"], 0.0)
        for key in (
            "aquifer_storage_index",
            "aquifer_quality_index",
            "aquifer_productivity_index",
            "aquifer_natural_limitation_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertTrue(first_cell["aquifer_class"])
        self.assertGreaterEqual(first_cell["aquifer_system_id"], -1)
        self.assertIsInstance(first_cell["groundwater_hydraulic_head_m"], (int, float))
        self.assertGreaterEqual(first_cell["groundwater_gradient_index"], 0.0)
        self.assertLessEqual(first_cell["groundwater_gradient_index"], 1.0)
        self.assertGreaterEqual(first_cell["groundwater_lateral_flow_km3_y"], 0.0)
        self.assertGreaterEqual(first_cell["groundwater_lateral_inflow_km3_y"], 0.0)
        self.assertGreaterEqual(first_cell["groundwater_available_volume_km3_y"], 0.0)
        self.assertGreaterEqual(
            first_cell["groundwater_internal_lateral_outflow_km3_y"],
            0.0,
        )
        self.assertGreaterEqual(first_cell["groundwater_discharge_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["groundwater_discharge_km3_y"], 0.0)
        self.assertGreaterEqual(
            first_cell["groundwater_retained_storage_km3_y"],
            0.0,
        )
        self.assertGreaterEqual(first_cell["groundwater_flow_to_cell_id"], -1)
        self.assertGreaterEqual(first_cell["spring_discharge_index"], 0.0)
        self.assertLessEqual(first_cell["spring_discharge_index"], 1.0)
        self.assertGreaterEqual(first_cell["baseflow_support_index"], 0.0)
        self.assertLessEqual(first_cell["baseflow_support_index"], 1.0)
        self.assertIn(
            first_cell["groundwater_flow_regime"],
            {
                "excluded",
                "recharge_mound",
                "recharge_throughflow",
                "throughflow",
                "discharge_zone",
                "lowland_discharge",
                "stagnant_or_low_yield",
            },
        )
        self.assertGreaterEqual(first_cell["groundwater_flow_system_id"], -1)
        self.assertGreaterEqual(first_cell["actual_evapotranspiration_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["infiltration_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["water_budget_runoff_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["hydrologic_deficit_mm_y"], 0.0)
        self.assertGreaterEqual(first_cell["infiltration_capacity_index"], 0.0)
        self.assertLessEqual(first_cell["infiltration_capacity_index"], 1.0)
        self.assertGreaterEqual(first_cell["runoff_budget_consistency_index"], 0.0)
        self.assertLessEqual(first_cell["runoff_budget_consistency_index"], 1.0)
        self.assertGreaterEqual(first_cell["runoff_generation_fraction"], 0.0)
        self.assertLessEqual(first_cell["runoff_generation_fraction"], 1.0)
        self.assertIn(
            first_cell["hydrologic_budget_class"],
            {
                "marine_budget",
                "water_deficit",
                "runoff_surplus",
                "infiltration_dominated",
                "evapotranspiration_dominated",
                "balanced_budget",
            },
        )
        self.assertGreaterEqual(first_cell["hydrologic_budget_region_id"], -1)
        for key in (
            "wetland_extent_index",
            "wetland_hydrology_index",
            "wetland_soil_saturation_index",
            "wetland_ecotone_index",
            "wetland_connectivity_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertIn(
            first_cell["wetland_system_type"],
            {
                "none",
                "mangrove",
                "tidal_marsh",
                "delta_wetland",
                "floodplain_wetland",
                "lacustrine_wetland",
                "peatland",
                "freshwater_swamp",
            },
        )
        self.assertGreaterEqual(first_cell["wetland_system_id"], -1)
        for key in (
            "karst_potential_index",
            "cave_development_index",
            "subterranean_drainage_fraction",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertGreaterEqual(first_cell["karst_system_id"], -1)
        if world["aquifer_systems"]:
            first_aquifer = world["aquifer_systems"][0]
            self.assertEqual(first_aquifer["id"], 0)
            self.assertGreater(first_aquifer["cell_count"], 0)
            self.assertEqual(first_aquifer["cell_count"], len(first_aquifer["cell_ids"]))
            self.assertTrue(first_aquifer["aquifer_class"])
            self.assertTrue(first_aquifer["primary_lithology"])
            self.assertTrue(first_aquifer["dominant_landform"])
            self.assertGreaterEqual(first_aquifer["area_km2"], 0.0)
            self.assertGreaterEqual(first_aquifer["total_groundwater_recharge_km3_y"], 0.0)
            self.assertEqual(sum(first_aquifer["aquifer_class_counts"].values()), first_aquifer["cell_count"])
            for key in (
                "mean_aquifer_storage_index",
                "mean_aquifer_quality_index",
                "mean_aquifer_productivity_index",
                "mean_aquifer_natural_limitation_index",
                "closed_basin_fraction",
            ):
                self.assertGreaterEqual(first_aquifer[key], 0.0)
                self.assertLessEqual(first_aquifer[key], 1.0)
        if world["groundwater_flow_systems"]:
            first_flow_system = world["groundwater_flow_systems"][0]
            self.assertEqual(first_flow_system["id"], 0)
            self.assertGreater(first_flow_system["cell_count"], 0)
            self.assertEqual(first_flow_system["cell_count"], len(first_flow_system["cell_ids"]))
            self.assertGreaterEqual(first_flow_system["aquifer_system_id"], 0)
            self.assertIn(first_flow_system["outlet_cell_id"], first_flow_system["cell_ids"])
            self.assertEqual(sum(first_flow_system["flow_regime_counts"].values()), first_flow_system["cell_count"])
            self.assertGreaterEqual(first_flow_system["area_km2"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_recharge_km3_y"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_lateral_inflow_km3_y"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_internal_lateral_outflow_km3_y"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_discharge_km3_y"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_lateral_flow_km3_y"], 0.0)
            self.assertGreaterEqual(first_flow_system["total_groundwater_retained_storage_km3_y"], 0.0)
            self.assertAlmostEqual(
                first_flow_system["total_groundwater_recharge_km3_y"]
                + first_flow_system["total_groundwater_lateral_inflow_km3_y"],
                first_flow_system["total_groundwater_internal_lateral_outflow_km3_y"]
                + first_flow_system["total_groundwater_discharge_km3_y"]
                + first_flow_system["total_groundwater_retained_storage_km3_y"]
                + first_flow_system["groundwater_flow_mass_balance_residual_km3_y"],
                delta=0.001,
            )
            self.assertGreaterEqual(first_flow_system["discharge_to_recharge_ratio"], 0.0)
            for key in (
                "mean_groundwater_gradient_index",
                "mean_spring_discharge_index",
                "mean_baseflow_support_index",
                "mean_aquifer_natural_limitation_index",
            ):
                self.assertGreaterEqual(first_flow_system[key], 0.0)
                self.assertLessEqual(first_flow_system[key], 1.0)
        if world["karst_systems"]:
            first_karst = world["karst_systems"][0]
            self.assertEqual(first_karst["id"], 0)
            self.assertGreater(first_karst["cell_count"], 0)
            self.assertEqual(first_karst["cell_count"], len(first_karst["cell_ids"]))
            self.assertTrue(first_karst["dominant_lithology"])
            self.assertTrue(first_karst["primary_aquifer_class"])
            self.assertIsInstance(first_karst["aquifer_system_ids"], list)
            self.assertGreaterEqual(first_karst["area_km2"], 0.0)
            for key in (
                "mean_karst_potential_index",
                "mean_cave_development_index",
                "mean_subterranean_drainage_fraction",
                "limestone_cell_fraction",
            ):
                self.assertGreaterEqual(first_karst[key], 0.0)
                self.assertLessEqual(first_karst[key], 1.0)
    def test_biome_ecotone_regions(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        first_cell = world["cells"][0]
        if world["biome_ecotone_regions"]:
            first_ecotone = world["biome_ecotone_regions"][0]
            self.assertEqual(first_ecotone["id"], 0)
            self.assertTrue(first_ecotone["ecotone_type"])
            self.assertNotEqual(first_ecotone["ecotone_type"], "none")
            self.assertGreater(first_ecotone["cell_count"], 0)
            self.assertEqual(first_ecotone["cell_count"], len(first_ecotone["cell_ids"]))
            self.assertGreaterEqual(first_ecotone["area_km2"], 0.0)
            self.assertTrue(first_ecotone["dominant_biome"])
            self.assertGreaterEqual(first_ecotone["mean_ecotone_confidence"], 0.0)
            self.assertLessEqual(first_ecotone["mean_ecotone_confidence"], 1.0)
            self.assertGreaterEqual(first_ecotone["mean_precipitation_mm_y"], 0.0)
            self.assertGreaterEqual(first_ecotone["coastal_cell_count"], 0)
        for key in (
            "primary_productivity_index",
            "vegetation_biomass_index",
            "species_richness_index",
            "wildfire_spread_risk_index",
            "ecosystem_disturbance_pressure_index",
            "vegetation_succession_stage",
            "vegetation_recovery_years",
            "forest_growth_index",
            "fishery_productivity_index",
        ):
            self.assertIn(key, first_cell)
        for key in (
            "primary_productivity_index",
            "vegetation_biomass_index",
            "species_richness_index",
            "wildfire_spread_risk_index",
            "ecosystem_disturbance_pressure_index",
            "forest_growth_index",
            "fishery_productivity_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertTrue(first_cell["vegetation_succession_stage"])
        self.assertGreaterEqual(first_cell["vegetation_recovery_years"], 1)
        if world["vegetation_succession_histories"]:
            first_succession = world["vegetation_succession_histories"][0]
            self.assertEqual(first_succession["id"], 0)
            self.assertGreater(first_succession["step_count"], 0)
            self.assertEqual(first_succession["step_count"], len(first_succession["steps"]))
            self.assertTrue(first_succession["initial_succession_stage"])
            self.assertTrue(first_succession["final_succession_stage"])
            self.assertGreaterEqual(first_succession["recovery_years"], 1)
            for key in (
                "mean_biomass_index",
                "mean_canopy_closure_index",
                "mean_disturbance_pressure_index",
                "max_wildfire_spread_risk_index",
            ):
                self.assertGreaterEqual(first_succession[key], 0.0)
                self.assertLessEqual(first_succession[key], 1.0)
            first_step = first_succession["steps"][0]
            self.assertTrue(first_step["phase"])
            self.assertGreaterEqual(first_step["years_since_start"], 0)
            self.assertTrue(first_step["succession_stage"])
            for key in (
                "biomass_index",
                "canopy_closure_index",
                "primary_productivity_index",
                "disturbance_pressure_index",
                "wildfire_spread_risk_index",
                "recovery_fraction",
            ):
                self.assertGreaterEqual(first_step[key], 0.0)
                self.assertLessEqual(first_step[key], 1.0)
        if world["renewable_resource_records"]:
            first_renewable = world["renewable_resource_records"][0]
            renewable_cell = world["cells"][first_renewable["cell_id"]]
            self.assertEqual(first_renewable["id"], 0)
            self.assertIn(first_renewable["resource_type"], {"forest_growth", "fishery_productivity"})
            self.assertEqual(first_renewable["biome"], renewable_cell["biome"])
            self.assertEqual(first_renewable["water_body_type"], renewable_cell["water_body_type"])
            self.assertGreaterEqual(first_renewable["productivity_index"], 0.0)
            self.assertLessEqual(first_renewable["productivity_index"], 1.0)
            self.assertGreaterEqual(first_renewable["sustainable_yield_index"], 0.0)
            self.assertLessEqual(first_renewable["sustainable_yield_index"], 1.0)
            self.assertGreaterEqual(first_renewable["regeneration_years"], 1)
            self.assertGreaterEqual(first_renewable["climate_dependency_index"], 0.0)
            self.assertLessEqual(first_renewable["climate_dependency_index"], 1.0)
            self.assertGreaterEqual(first_renewable["water_dependency_index"], 0.0)
            self.assertLessEqual(first_renewable["water_dependency_index"], 1.0)
            self.assertAlmostEqual(
                first_renewable["disturbance_risk_index"],
                renewable_cell["ecosystem_disturbance_pressure_index"],
                delta=0.001,
            )
            self.assertIn("primary_productivity_index", first_renewable["formation_evidence"])
        for key in (
            "dominant_species_guild",
            "species_habitat_suitability_index",
            "species_endemism_index",
            "species_range_fragmentation_index",
            "species_composition_confidence_index",
            "species_guild_richness_count",
            "species_range_record_ids",
        ):
            self.assertIn(key, first_cell)
        self.assertTrue(first_cell["dominant_species_guild"])
        for key in (
            "species_habitat_suitability_index",
            "species_endemism_index",
            "species_range_fragmentation_index",
            "species_composition_confidence_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertGreaterEqual(first_cell["species_guild_richness_count"], 0)
        self.assertIsInstance(first_cell["species_range_record_ids"], list)
        if world["species_range_records"]:
            first_species_range = world["species_range_records"][0]
            self.assertEqual(first_species_range["id"], 0)
            self.assertIn(
                first_species_range["guild_type"],
                {
                    "canopy_tree",
                    "grassland_grazer",
                    "desert_specialist",
                    "alpine_tundra_specialist",
                    "wetland_amphibian",
                    "large_predator",
                    "freshwater_fish",
                    "marine_fish",
                    "reef_builder",
                    "mangrove_coastal_bird",
                },
            )
            self.assertIn(
                first_species_range["habitat_class"],
                {"terrestrial", "arid", "alpine", "wetland", "freshwater", "marine", "reef"},
            )
            self.assertTrue(first_species_range["trophic_role"])
            self.assertGreater(first_species_range["cell_count"], 0)
            self.assertEqual(first_species_range["cell_count"], len(first_species_range["cell_ids"]))
            self.assertGreaterEqual(first_species_range["area_km2"], 0.0)
            for key in (
                "mean_habitat_suitability_index",
                "max_habitat_suitability_index",
                "mean_species_richness_index",
                "mean_primary_productivity_index",
                "mean_disturbance_pressure_index",
                "mean_composition_confidence_index",
                "range_fragmentation_index",
                "endemism_index",
                "conservation_stress_index",
            ):
                self.assertGreaterEqual(first_species_range[key], 0.0)
                self.assertLessEqual(first_species_range[key], 1.0)
            self.assertIn("mean_temperature_c", first_species_range["climate_envelope"])
            self.assertIn("mean_precipitation_mm_y", first_species_range["climate_envelope"])
            self.assertIn("mean_wetland_extent_index", first_species_range["habitat_evidence"])
            species_cell = world["cells"][first_species_range["cell_ids"][0]]
            self.assertIn(first_species_range["id"], species_cell["species_range_record_ids"])
        for key in (
            "wildfire_ignition_potential_index",
            "wildfire_fuel_continuity_index",
            "wildfire_wind_alignment_index",
            "wildfire_firebreak_index",
            "wildfire_disturbance_regime",
            "wildfire_spread_history_ids",
        ):
            self.assertIn(key, first_cell)
        for key in (
            "wildfire_ignition_potential_index",
            "wildfire_fuel_continuity_index",
            "wildfire_wind_alignment_index",
            "wildfire_firebreak_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertTrue(first_cell["wildfire_disturbance_regime"])
        self.assertIsInstance(first_cell["wildfire_spread_history_ids"], list)
        if world["wildfire_spread_histories"]:
            first_wildfire = world["wildfire_spread_histories"][0]
            self.assertEqual(first_wildfire["id"], 0)
            self.assertIn(first_wildfire["ignition_cell_id"], first_wildfire["cell_ids"])
            self.assertGreater(first_wildfire["cell_count"], 0)
            self.assertEqual(first_wildfire["cell_count"], len(first_wildfire["cell_ids"]))
            self.assertGreaterEqual(first_wildfire["area_km2"], 0.0)
            self.assertTrue(first_wildfire["dominant_biome"])
            self.assertTrue(first_wildfire["dominant_disturbance_regime"])
            for key in (
                "mean_wildfire_spread_risk_index",
                "mean_ignition_potential_index",
                "mean_fuel_continuity_index",
                "mean_wind_alignment_index",
                "mean_firebreak_index",
                "mean_ecosystem_disturbance_pressure_index",
                "max_spread_probability_index",
                "containment_index",
            ):
                self.assertGreaterEqual(first_wildfire[key], 0.0)
                self.assertLessEqual(first_wildfire[key], 1.0)
            self.assertEqual(first_wildfire["spread_step_count"], len(first_wildfire["steps"]))
            self.assertGreater(first_wildfire["spread_step_count"], 0)
            self.assertEqual(sum(first_wildfire["disturbance_regime_counts"].values()), first_wildfire["cell_count"])
            first_fire_step = first_wildfire["steps"][0]
            self.assertEqual(first_fire_step["step_index"], 0)
            self.assertGreater(first_fire_step["cumulative_burned_cell_count"], 0)
            self.assertGreaterEqual(first_fire_step["burned_area_km2"], 0.0)
            self.assertGreaterEqual(first_fire_step["mean_spread_probability_index"], 0.0)
            self.assertLessEqual(first_fire_step["mean_spread_probability_index"], 1.0)
            fire_cell = world["cells"][first_wildfire["cell_ids"][0]]
            self.assertIn(first_wildfire["id"], fire_cell["wildfire_spread_history_ids"])
        for key in (
            "petroleum_source_rock_index",
            "petroleum_maturation_index",
            "petroleum_migration_path_index",
            "petroleum_trap_integrity_index",
            "petroleum_accumulation_index",
            "petroleum_system_id",
        ):
            self.assertIn(key, first_cell)
        for key in (
            "petroleum_source_rock_index",
            "petroleum_maturation_index",
            "petroleum_migration_path_index",
            "petroleum_trap_integrity_index",
            "petroleum_accumulation_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertGreaterEqual(first_cell["petroleum_system_id"], -1)
        for key in (
            "ore_genesis_potential_index",
            "hydrothermal_alteration_index",
            "metallogenic_fertility_index",
            "ore_structural_control_index",
            "placer_concentration_index",
            "ore_genesis_system_id",
        ):
            self.assertIn(key, first_cell)
        for key in (
            "ore_genesis_potential_index",
            "hydrothermal_alteration_index",
            "metallogenic_fertility_index",
            "ore_structural_control_index",
            "placer_concentration_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertGreaterEqual(first_cell["ore_genesis_system_id"], -1)
        if world["resource_deposits"]:
            first_deposit = world["resource_deposits"][0]
            deposit_cell = world["cells"][first_deposit["cell_id"]]
            self.assertEqual(first_deposit["id"], 0)
            self.assertEqual(first_deposit["resource"], deposit_cell["resource"])
            self.assertNotEqual(first_deposit["resource"], "none")
            self.assertIn(first_deposit["deposit_class"], {"metal", "energy", "industrial_mineral", "bioproductive", "other"})
            self.assertTrue(first_deposit["formation_process"])
            self.assertEqual(first_deposit["host_crust_type"], deposit_cell["crust_type"])
            self.assertEqual(first_deposit["host_lithology"], deposit_cell["lithology"])
            self.assertEqual(first_deposit["landform"], deposit_cell["landform"])
            self.assertEqual(first_deposit["basin_id"], deposit_cell["basin_id"])
            self.assertEqual(first_deposit["political_region_id"], deposit_cell["political_region_id"])
            self.assertEqual(first_deposit["culture_region_id"], deposit_cell["culture_region_id"])
            self.assertAlmostEqual(first_deposit["latitude_deg"], deposit_cell["lat_deg"], delta=0.001)
            self.assertAlmostEqual(first_deposit["longitude_deg"], deposit_cell["lon_deg"], delta=0.001)
            self.assertAlmostEqual(first_deposit["area_km2"], deposit_cell["area_km2"], delta=0.001)
            for key in (
                "reserve_potential_index",
                "accessibility_index",
                "extraction_hazard_index",
                "economic_viability_index",
                "renewability_index",
                "geologic_confidence_index",
            ):
                self.assertGreaterEqual(first_deposit[key], 0.0)
                self.assertLessEqual(first_deposit[key], 1.0)
            evidence = first_deposit["formation_evidence"]
            self.assertEqual(evidence["boundary_type"], deposit_cell["boundary_type"])
            self.assertIn("crust_age_ma", evidence)
            self.assertIn("sediment_thickness_m", evidence)
            self.assertIn("flow_accumulation", evidence)
            self.assertIn("fertility", evidence)
        if world["ore_genesis_systems"]:
            first_ore = world["ore_genesis_systems"][0]
            cells_by_id = {cell["id"]: cell for cell in world["cells"]}
            deposits_by_id = {deposit["id"]: deposit for deposit in world["resource_deposits"]}
            self.assertEqual(first_ore["id"], 0)
            self.assertIn(
                first_ore["system_type"],
                {
                    "subduction_arc_hydrothermal",
                    "ancient_craton_metallogenic",
                    "fluvial_placer_system",
                    "rift_geothermal_hydrothermal",
                    "mixed_metallogenic_province",
                },
            )
            self.assertEqual(first_ore["cell_count"], len(first_ore["cell_ids"]))
            self.assertGreater(first_ore["cell_count"], 0)
            self.assertIn(first_ore["representative_cell_id"], first_ore["cell_ids"])
            self.assertEqual(first_ore["resource_deposit_count"], len(first_ore["resource_deposit_ids"]))
            for deposit_id in first_ore["resource_deposit_ids"]:
                self.assertIn(deposit_id, deposits_by_id)
                self.assertIn(
                    deposits_by_id[deposit_id]["resource"],
                    {"volcanic_arc_metals", "craton_iron_gold", "placer_metals", "geothermal"},
                )
                self.assertIn(deposits_by_id[deposit_id]["cell_id"], first_ore["cell_ids"])
            for key in (
                "mean_ore_genesis_potential_index",
                "max_ore_genesis_potential_index",
                "mean_hydrothermal_alteration_index",
                "mean_metallogenic_fertility_index",
                "mean_ore_structural_control_index",
                "mean_placer_concentration_index",
                "mean_resource_viability_index",
                "ore_genesis_confidence_index",
            ):
                self.assertGreaterEqual(first_ore[key], 0.0)
                self.assertLessEqual(first_ore[key], 1.0)
            self.assertTrue(first_ore["dominant_resource"])
            self.assertTrue(first_ore["dominant_lithology"])
            self.assertTrue(first_ore["dominant_landform"])
            self.assertTrue(first_ore["dominant_tectonic_context"])
            self.assertEqual(first_ore["formation_step_count"], len(first_ore["formation_steps"]))
            self.assertGreater(first_ore["formation_step_count"], 0)
            first_ore_step = first_ore["formation_steps"][0]
            self.assertEqual(first_ore_step["step_index"], 0)
            self.assertTrue(first_ore_step["process"])
            self.assertEqual(first_ore_step["active_cell_count"], len(first_ore_step["active_cell_ids"]))
            self.assertTrue(set(first_ore_step["active_cell_ids"]).issubset(first_ore["cell_ids"]))
            for key in ("mean_ore_genesis_potential_index", "mean_process_intensity_index"):
                self.assertGreaterEqual(first_ore_step[key], 0.0)
                self.assertLessEqual(first_ore_step[key], 1.0)
            ore_cell = cells_by_id[first_ore["cell_ids"][0]]
            self.assertEqual(ore_cell["ore_genesis_system_id"], first_ore["id"])
        if world["sedimentary_resource_systems"]:
            first_system = world["sedimentary_resource_systems"][0]
            cells_by_id = {cell["id"]: cell for cell in world["cells"]}
            deposits_by_id = {deposit["id"]: deposit for deposit in world["resource_deposits"]}
            self.assertEqual(first_system["id"], 0)
            self.assertIn(
                first_system["system_type"],
                {
                    "petroleum_system",
                    "gas_system",
                    "coal_basin",
                    "evaporite_salt_system",
                    "mixed_sedimentary_resource",
                },
            )
            self.assertEqual(first_system["cell_count"], len(first_system["cell_ids"]))
            self.assertGreater(first_system["cell_count"], 0)
            self.assertEqual(
                {cells_by_id[cell_id]["basin_id"] for cell_id in first_system["cell_ids"]},
                {first_system["basin_id"]},
            )
            self.assertEqual(first_system["resource_deposit_count"], len(first_system["resource_deposit_ids"]))
            for deposit_id in first_system["resource_deposit_ids"]:
                self.assertIn(deposit_id, deposits_by_id)
                self.assertIn(deposits_by_id[deposit_id]["resource"], {"sedimentary_fuels", "evaporites"})
                self.assertEqual(deposits_by_id[deposit_id]["basin_id"], first_system["basin_id"])
            for key in (
                "source_rock_index",
                "reservoir_quality_index",
                "seal_quality_index",
                "structural_trap_index",
                "coal_potential_index",
                "petroleum_potential_index",
                "gas_potential_index",
                "evaporite_salt_potential_index",
                "system_confidence_index",
            ):
                self.assertGreaterEqual(first_system[key], 0.0)
                self.assertLessEqual(first_system[key], 1.0)
            self.assertTrue(first_system["dominant_lithology"])
            self.assertTrue(first_system["dominant_landform"])
