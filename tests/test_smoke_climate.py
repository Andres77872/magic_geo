"""Climate dynamics, energy balance, and realism assertions for the generated world.

Split out of the former single-method smoke test: each method re-derives
what it needs from the shared world, so they no longer depend on order.
"""

from __future__ import annotations

import math
from pathlib import Path
from unittest import TestCase

from magic_geo.api import generate_world
from magic_geo.config import config_to_native, load_config
from magic_geo.native import generate_world as generate_native_world
from magic_geo.native_climate_energy_validation import audit_native_climate_energy
from magic_geo.native_climate_energy_enrichment_validation import validate_native_climate_energy_enrichment

from support import worlds


class SmokeClimateTests(TestCase):
    def test_climate_model(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        climate_model = world["climate_model"]
        self.assertEqual(climate_model["model_type"], "prescribed_seasonal_surface_energy_v1")
        self.assertEqual(climate_model["temperature_model"], "periodic_graybody_storage_conservative_transport_v1")
        self.assertEqual(climate_model["precipitation_model"], "solved_temperature_scaled_empirical_circulation_orography_wind_transport_v1")
        self.assertFalse(climate_model["imposed_mean_temperature"])
        self.assertFalse(climate_model["post_solve_temperature_adjustments"])
        self.assertTrue(climate_model["native_temperature_forcing_coupled"])
        self.assertTrue(climate_model["periodic_seasonal_cycle_resolved"])
        self.assertTrue(climate_model["prescribed_atmospheric_mass_conserved"])
        self.assertFalse(climate_model["mass_conserving_atmospheric_circulation"])
        self.assertFalse(climate_model["transient_climate_resolved"])
        self.assertEqual(climate_model["subtropical_drying_strength"], 0.65)
        self.assertEqual(climate_model["seasonal_monsoon_precipitation_strength"], 1.6)
        expected = min(2.25, max(0.35, math.exp(0.04 * (climate_model["solved_area_time_mean_temperature_c"] - 15.0))))
        self.assertAlmostEqual(climate_model["thermal_moisture_capacity_factor"], expected, delta=1e-12)
        self.assertTrue(audit_native_climate_energy(world)["verified"])
        self.assertEqual(validate_native_climate_energy_enrichment(world), [])

    def test_climate_continentality_regions(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        small = worlds.canonical_config("small_smoke")
        summary = world["summary"]
        self.assertEqual(summary["climate_continentality_region_count"], len(world["climate_continentality_regions"]))
        self.assertEqual(
            summary["high_continentality_cell_count"],
            sum(1 for cell in world["cells"] if cell["continentality_index"] >= 0.65),
        )
        self.assertEqual(
            summary["low_oceanic_humidity_availability_cell_count"],
            sum(1 for cell in world["cells"] if cell["oceanic_humidity_availability_index"] <= 0.25),
        )
        self.assertGreaterEqual(summary["mean_distance_to_marine_water_km"], 0.0)
        self.assertGreaterEqual(summary["mean_continentality_index"], 0.0)
        self.assertLessEqual(summary["mean_continentality_index"], 1.0)
        self.assertGreaterEqual(summary["max_continentality_index"], summary["mean_continentality_index"])
        self.assertLessEqual(summary["max_continentality_index"], 1.0)
        self.assertGreaterEqual(summary["mean_oceanic_humidity_availability_index"], 0.0)
        self.assertLessEqual(summary["mean_oceanic_humidity_availability_index"], 1.0)
        if world["climate_continentality_regions"]:
            first_continentality_region = world["climate_continentality_regions"][0]
            self.assertEqual(first_continentality_region["id"], 0)
            self.assertIn(
                first_continentality_region["region_class"],
                {"marine", "coastal", "maritime_influenced", "interior", "continental_core"},
            )
            self.assertEqual(first_continentality_region["cell_count"], len(first_continentality_region["cell_ids"]))
            self.assertGreater(first_continentality_region["area_km2"], 0.0)
            self.assertGreaterEqual(first_continentality_region["mean_continentality_index"], 0.0)
            self.assertLessEqual(first_continentality_region["mean_continentality_index"], 1.0)
            self.assertGreaterEqual(first_continentality_region["mean_oceanic_humidity_availability_index"], 0.0)
            self.assertLessEqual(first_continentality_region["mean_oceanic_humidity_availability_index"], 1.0)
        self.assertEqual(summary["climate_seasonal_history_count"], len(world["climate_seasonal_histories"]))
        self.assertEqual(summary["climate_seasonal_history_count"], len(summary["atmospheric_cell_counts"]))
        self.assertEqual(
            summary["climate_seasonal_step_count"],
            sum(history["time_step_count"] for history in world["climate_seasonal_histories"]),
        )
        self.assertEqual(sum(summary["seasonal_humidity_regime_counts"].values()), summary["cell_count"])
        self.assertEqual(world["climate_classification"]["classification_type"], "koppen_geiger_beck_2018_v0")
        self.assertEqual(world["climate_classification"]["available_class_count"], 30)
        self.assertFalse(world["climate_classification"]["confidence_resolved"])
        self.assertEqual(world["climate_classification"]["classified_cell_count"], summary["cell_count"])
        self.assertEqual(sum(summary["climate_class_counts"].values()), summary["cell_count"])
        self.assertEqual(sum(summary["climate_main_class_counts"].values()), summary["cell_count"])
        self.assertEqual(summary["climate_class_count"], len(summary["climate_class_counts"]))
        self.assertTrue(all(cell["climate_class"] in summary["climate_class_counts"] for cell in world["cells"]))
        self.assertGreaterEqual(summary["seasonal_aridity_cell_fraction"], 0.0)
        self.assertLessEqual(summary["seasonal_aridity_cell_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_cell_monsoon_index"], 0.0)
        self.assertLessEqual(summary["mean_cell_monsoon_index"], 1.0)
        self.assertGreaterEqual(summary["mean_cell_seasonal_aridity_index"], 0.0)
        self.assertLessEqual(summary["mean_cell_seasonal_aridity_index"], 1.0)
        self.assertAlmostEqual(
            summary["climate_seasonal_total_precipitation_mm"],
            sum(history["annual_precipitation_mm"] for history in world["climate_seasonal_histories"]),
            delta=max(0.001, summary["climate_seasonal_total_precipitation_mm"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["climate_seasonal_total_evaporation_mm"],
            sum(history["annual_evaporation_mm"] for history in world["climate_seasonal_histories"]),
            delta=max(0.001, summary["climate_seasonal_total_evaporation_mm"] * 0.0001),
        )
        self.assertLessEqual(summary["climate_seasonal_mean_abs_residual_mm"], 0.001)
        self.assertGreaterEqual(summary["max_climate_humidity_storage_mm"], 0.0)
        self.assertGreaterEqual(summary["max_climate_monsoon_index"], 0.0)
        self.assertLessEqual(summary["max_climate_monsoon_index"], 1.0)
        self.assertEqual(summary["native_climate_energy_record_count"], len(world["cells"]))
        self.assertEqual(len(world["climate_energy_balance_records"]), len(world["cells"]))
        self.assertGreater(summary["native_climate_energy_total_area_m2"], 0.0)
        self.assertGreater(summary["native_climate_energy_year_duration_seconds"], 0.0)
        self.assertNotIn("mean_climate_energy_stress_index", summary)
        self.assertNotIn("mean_abs_energy_balance_residual_c", summary)
        areas = [record["area_m2"] for record in world["climate_energy_balance_records"]]
        for field in (
            "effective_toa_albedo", "effective_longwave_emissivity",
            "annual_absorbed_shortwave_w_m2", "annual_emitted_longwave_w_m2",
            "annual_horizontal_heat_convergence_w_m2", "annual_heat_storage_tendency_w_m2",
            "annual_energy_balance_residual_w_m2",
        ):
            values = [cell[field] for cell in world["cells"]]
            self.assertAlmostEqual(summary[f"cell_count_mean_{field}"], math.fsum(values) / len(values), delta=1e-10)
            expected = math.fsum(value * area for value, area in zip(values, areas, strict=True)) / math.fsum(areas)
            self.assertAlmostEqual(summary[f"area_weighted_mean_{field}"], expected, delta=1e-10)
        self.assertGreater(summary["area_weighted_mean_annual_absorbed_shortwave_w_m2"], 0.0)
        self.assertGreater(summary["area_weighted_mean_annual_emitted_longwave_w_m2"], 0.0)
        self.assertIn("planet_parameters", world)
        self.assertEqual(world["planet_parameters"]["gravity_g"], small.planet.gravity_g)
        self.assertEqual(world["planet_parameters"]["day_length_hours"], small.planet.day_length_hours)
    def test_planet_realism_checks(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertEqual(summary["planet_realism_check_count"], len(world["planet_realism_checks"]))
        self.assertGreaterEqual(summary["planet_realism_check_count"], 4)
        self.assertEqual(
            summary["planet_realism_pass_count"],
            sum(1 for check in world["planet_realism_checks"] if check["passed"]),
        )
        self.assertGreaterEqual(summary["planet_realism_pass_fraction"], 0.0)
        self.assertLessEqual(summary["planet_realism_pass_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_planet_realism_score"], 0.0)
        self.assertLessEqual(summary["mean_planet_realism_score"], 1.0)
        for key in [
            "global_liquid_water_temperature_index",
            "atmosphere_gravity_stability_index",
            "rotation_circulation_plausibility_index",
            "surface_water_inventory_index",
        ]:
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        planet_check_names = {check["name"] for check in world["planet_realism_checks"]}
        self.assertTrue(
            {
                "liquid_water_temperature_window",
                "atmosphere_gravity_stability",
                "rotation_circulation_plausibility",
                "surface_water_inventory",
            }.issubset(planet_check_names)
        )
        first_planet_check = world["planet_realism_checks"][0]
        self.assertEqual(first_planet_check["domain"], "planet")
        self.assertIn("evidence", first_planet_check)
        self.assertGreaterEqual(first_planet_check["score"], 0.0)
        self.assertLessEqual(first_planet_check["score"], 1.0)
        self.assertEqual(summary["climate_realism_check_count"], len(world["climate_realism_checks"]))
        self.assertGreaterEqual(summary["climate_realism_check_count"], 6)
        self.assertEqual(
            summary["climate_realism_pass_count"],
            sum(1 for check in world["climate_realism_checks"] if check["passed"]),
        )
        self.assertGreaterEqual(summary["climate_realism_pass_fraction"], 0.0)
        self.assertLessEqual(summary["climate_realism_pass_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_climate_realism_score"], 0.0)
        self.assertLessEqual(summary["mean_climate_realism_score"], 1.0)
        for key in (
            "subtropical_dry_belt_index",
            "equatorial_ocean_humidity_index",
            "orographic_rain_shadow_index",
            "continentality_temperature_range_index",
            "cold_current_coastal_drying_index",
            "warm_current_moderation_index",
        ):
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        climate_names = {check["name"] for check in world["climate_realism_checks"]}
        self.assertTrue(
            {
                "subtropical_dry_belt",
                "equatorial_ocean_humidity",
                "orographic_rain_shadow",
                "continental_interior_extremes",
                "cold_current_coastal_drying",
                "warm_current_climate_moderation",
            }.issubset(climate_names)
        )
        first_climate_check = world["climate_realism_checks"][0]
        for key in ("domain", "question", "metric", "value", "target_min", "target_max", "score", "passed", "evidence"):
            self.assertIn(key, first_climate_check)
        self.assertEqual(first_climate_check["domain"], "climate")
        self.assertGreaterEqual(first_climate_check["score"], 0.0)
        self.assertLessEqual(first_climate_check["score"], 1.0)
        self.assertIn("mean_ice_thickness_m", summary)
        self.assertIn("mean_glacial_erosion_m", summary)
        self.assertIn("mean_ice_surface_mass_balance_m_y", summary)
        self.assertGreaterEqual(summary["mean_ice_surface_mass_balance_m_y"], -4.0)
        self.assertLessEqual(summary["mean_ice_surface_mass_balance_m_y"], 3.2)
        self.assertIn("mean_basal_sliding_index", summary)
        self.assertGreaterEqual(summary["mean_basal_sliding_index"], 0.0)
        self.assertLessEqual(summary["mean_basal_sliding_index"], 1.0)
        self.assertIn("mean_ice_velocity_m_y", summary)
        self.assertGreaterEqual(summary["mean_ice_velocity_m_y"], 0.0)
        self.assertIn("glaciated_land_fraction", summary)
    def test_climate_seasonal_histories(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        small = worlds.canonical_config("small_smoke")
        first_cell = world["cells"][0]
        first_climate_history = world["climate_seasonal_histories"][0]
        self.assertIn("atmospheric_cell", first_climate_history)
        self.assertIn("annual_precipitation_mm", first_climate_history)
        self.assertIn("annual_evaporation_mm", first_climate_history)
        self.assertIn("annual_moisture_convergence_mm", first_climate_history)
        self.assertIn("annual_humidity_export_mm", first_climate_history)
        self.assertIn("annual_vapor_deficit_mm", first_climate_history)
        self.assertIn("max_humidity_storage_mm", first_climate_history)
        self.assertIn("monsoon_index", first_climate_history)
        self.assertEqual(first_climate_history["time_step_count"], 12)
        self.assertEqual(len(first_climate_history["steps"]), 12)
        self.assertGreater(first_climate_history["cell_count"], 0)
        self.assertGreaterEqual(first_climate_history["monsoon_index"], 0.0)
        self.assertLessEqual(first_climate_history["monsoon_index"], 1.0)
        previous_storage = None
        for index, step in enumerate(first_climate_history["steps"]):
            self.assertEqual(step["month"], index + 1)
            self.assertGreaterEqual(step["precipitation_mm"], 0.0)
            self.assertGreaterEqual(step["start_humidity_storage_mm"], 0.0)
            self.assertGreaterEqual(step["evaporation_mm"], 0.0)
            self.assertGreaterEqual(step["moisture_convergence_mm"], 0.0)
            self.assertGreaterEqual(step["vapor_deficit_mm"], 0.0)
            self.assertGreaterEqual(step["humidity_export_mm"], 0.0)
            self.assertGreaterEqual(step["end_humidity_storage_mm"], 0.0)
            self.assertIn("mean_wind_east", step)
            self.assertIn("mean_wind_north", step)
            self.assertGreaterEqual(step["mean_wind_east"], -1.0)
            self.assertLessEqual(step["mean_wind_east"], 1.0)
            self.assertGreaterEqual(step["mean_wind_north"], -1.0)
            self.assertLessEqual(step["mean_wind_north"], 1.0)
            self.assertGreaterEqual(step["drying_risk"], 0.0)
            self.assertLessEqual(step["drying_risk"], 1.0)
            self.assertAlmostEqual(
                step["start_humidity_storage_mm"]
                + step["evaporation_mm"]
                + step["moisture_convergence_mm"]
                + step["vapor_deficit_mm"]
                - step["precipitation_mm"]
                - step["humidity_export_mm"]
                - step["end_humidity_storage_mm"],
                step["humidity_budget_residual_mm"],
                delta=0.001,
            )
            self.assertLessEqual(abs(step["humidity_budget_residual_mm"]), 0.001)
            if previous_storage is not None:
                self.assertAlmostEqual(
                    step["start_humidity_storage_mm"],
                    previous_storage,
                    delta=max(0.001, previous_storage * 0.0001),
                )
            previous_storage = step["end_humidity_storage_mm"]

        self.assertTrue(world["climate_energy_balance_records"])
        durations = world["climate_energy_model"]["monthly_duration_seconds"]
        for cell, record in zip(world["cells"], world["climate_energy_balance_records"], strict=True):
            self.assertEqual(record["cell_id"], cell["id"])
            for field in ("monthly_absorbed_shortwave_w_m2", "monthly_emitted_longwave_w_m2"):
                self.assertEqual(len(record[field]), 12)
                self.assertTrue(all(value >= 0.0 for value in record[field]))
            monthly = record["monthly_mean_temperature_k"]
            display_tolerance = 0.5 * 10 ** -small.output.float_precision + 1e-10
            for kelvin, celsius in zip(monthly, cell["temperature_monthly_c"], strict=True):
                self.assertAlmostEqual(kelvin - 273.15, celsius, delta=display_tolerance)
            annual_c = math.fsum(t * d for t, d in zip(monthly, durations, strict=True)) / math.fsum(durations) - 273.15
            self.assertAlmostEqual(cell["temperature_c"], annual_c, delta=display_tolerance)
            for i in range(12):
                net = (record["monthly_absorbed_shortwave_w_m2"][i]
                       - record["monthly_emitted_longwave_w_m2"][i]
                       + record["monthly_horizontal_heat_convergence_w_m2"][i])
                residual = record["monthly_heat_storage_tendency_w_m2"][i] - net
                self.assertAlmostEqual(record["monthly_balance_residual_w_m2"][i], residual, delta=1e-10)
                self.assertLessEqual(abs(residual), record["monthly_balance_tolerance_w_m2"][i])
            self.assertNotIn("energy_balance_residual_c", cell)
            self.assertNotIn("climate_energy_stress_index", cell)

        first_settlement = world["settlements"][0]
        self.assertIn("cell_id", first_settlement)
        self.assertIn("region_id", first_settlement)
        self.assertIn("culture_region_id", first_settlement)
        self.assertIn("language_region_id", first_settlement)
        self.assertIn("type", first_settlement)
        self.assertIn("score", first_settlement)
    def test_orbital_eccentricity_affects_insolation_variability(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        circular_data = config.model_dump(mode="python")
        circular_data["mesh"]["cell_count"] = 128
        circular_data["tectonics"]["plate_count"] = 6
        circular_data["erosion"]["iterations"] = 1
        circular_data["planet"]["orbital_eccentricity"] = 0.0
        circular = type(config).model_validate(circular_data)

        eccentric_data = config.model_dump(mode="python")
        eccentric_data["mesh"]["cell_count"] = 128
        eccentric_data["tectonics"]["plate_count"] = 6
        eccentric_data["erosion"]["iterations"] = 1
        eccentric_data["planet"]["orbital_eccentricity"] = 0.20
        eccentric = type(config).model_validate(eccentric_data)

        circular_world = generate_world(circular)
        eccentric_world = generate_world(eccentric)

        def orbital_distance_mean(world: dict) -> float:
            nodes = world["climate_energy_forcing_intervals"]
            return math.fsum(node["inverse_square_distance_factor"] * node["duration_seconds"] for node in nodes) / math.fsum(node["duration_seconds"] for node in nodes)

        def monthly_absorbed_range(world: dict) -> float:
            records = world["climate_energy_balance_records"]
            return math.fsum(max(record["monthly_absorbed_shortwave_w_m2"]) - min(record["monthly_absorbed_shortwave_w_m2"]) for record in records) / len(records)

        for world, eccentricity in ((circular_world, 0.0), (eccentric_world, 0.20)):
            self.assertEqual(world["climate_energy_model"]["orbital_eccentricity"], eccentricity)
            self.assertAlmostEqual(orbital_distance_mean(world), 1.0 / math.sqrt(1.0 - eccentricity ** 2), delta=2e-12)
            self.assertTrue(audit_native_climate_energy(world)["verified"])
        self.assertGreater(orbital_distance_mean(eccentric_world), orbital_distance_mean(circular_world))
        self.assertGreater(monthly_absorbed_range(eccentric_world), monthly_absorbed_range(circular_world))

    def test_native_thermal_forcing_scales_moisture_temperature_and_runoff(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))

        def forced_world(stellar_luminosity: float, greenhouse_factor: float) -> dict:
            data = config.model_dump(mode="python")
            data["mesh"]["cell_count"] = 128
            data["tectonics"]["plate_count"] = 8
            data["erosion"]["iterations"] = 0
            data["planet"]["stellar_luminosity"] = stellar_luminosity
            data["planet"]["greenhouse_factor"] = greenhouse_factor
            forced = type(config).model_validate(data)
            return generate_native_world(config_to_native(forced))

        cold_world = forced_world(0.55, 0.55)
        earth_world = forced_world(1.0, 1.0)
        hot_world = forced_world(1.45, 1.45)
        minimum_capacity_world = forced_world(0.011, 0.0)
        maximum_capacity_world = forced_world(100.0, 10.0)

        def area_mean(world: dict, field: str, *, land_only: bool = False) -> float:
            cells = [
                cell
                for cell in world["cells"]
                if not land_only or not cell["is_water"]
            ]
            total_area = sum(cell["area_km2"] for cell in cells)
            return sum(cell[field] * cell["area_km2"] for cell in cells) / total_area

        cold_temperature = area_mean(cold_world, "temperature_c")
        earth_temperature = area_mean(earth_world, "temperature_c")
        hot_temperature = area_mean(hot_world, "temperature_c")
        cold_precipitation = area_mean(
            cold_world, "precipitation_mm_y", land_only=True
        )
        earth_precipitation = area_mean(
            earth_world, "precipitation_mm_y", land_only=True
        )
        hot_precipitation = area_mean(
            hot_world, "precipitation_mm_y", land_only=True
        )
        cold_runoff = area_mean(cold_world, "runoff_mm_y", land_only=True)
        earth_runoff = area_mean(earth_world, "runoff_mm_y", land_only=True)

        self.assertLess(cold_temperature, earth_temperature)
        self.assertGreater(hot_temperature, earth_temperature)
        self.assertLess(cold_precipitation, earth_precipitation)
        self.assertGreater(hot_precipitation, earth_precipitation)
        self.assertLess(cold_runoff, earth_runoff)

        cold_model = cold_world["climate_model"]
        earth_model = earth_world["climate_model"]
        hot_model = hot_world["climate_model"]
        self.assertEqual(
            earth_model["thermal_moisture_capacity_model"],
            "bounded_exponential_solved_area_time_mean_temperature_v1",
        )
        self.assertLess(
            cold_model["thermal_moisture_capacity_factor"],
            earth_model["thermal_moisture_capacity_factor"],
        )
        self.assertGreater(
            hot_model["thermal_moisture_capacity_factor"],
            earth_model["thermal_moisture_capacity_factor"],
        )
        self.assertEqual(
            minimum_capacity_world["climate_model"]["thermal_moisture_capacity_factor"],
            earth_model["thermal_moisture_capacity_min_factor"],
        )
        self.assertEqual(
            maximum_capacity_world["climate_model"]["thermal_moisture_capacity_factor"],
            earth_model["thermal_moisture_capacity_max_factor"],
        )
        for world in (cold_world, earth_world, hot_world, minimum_capacity_world, maximum_capacity_world):
            self.assertTrue(audit_native_climate_energy(world)["verified"])
            model = world["climate_model"]
            expected = min(2.25, max(0.35, math.exp(0.04 * (model["solved_area_time_mean_temperature_c"] - 15.0))))
            self.assertAlmostEqual(model["thermal_moisture_capacity_factor"], expected, delta=1e-12)
            self.assertGreaterEqual(
                model["thermal_moisture_capacity_factor"],
                model["thermal_moisture_capacity_min_factor"],
            )
            self.assertLessEqual(
                model["thermal_moisture_capacity_factor"],
                model["thermal_moisture_capacity_max_factor"],
            )
            for cell in world["cells"]:
                self.assertAlmostEqual(
                    cell["precipitation_mm_y"],
                    sum(cell["precipitation_monthly_mm"]),
                    delta=0.002,
                )
    def test_native_uses_atmosphere_pressure_parameter(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 256
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 1

        low_pressure = type(config).model_validate(data)
        high_pressure_data = config.model_dump(mode="python")
        high_pressure_data["mesh"]["cell_count"] = 256
        high_pressure_data["tectonics"]["plate_count"] = 8
        high_pressure_data["erosion"]["iterations"] = 1
        high_pressure_data["planet"]["atmosphere_pressure_bar"] = 2.0
        high_pressure = type(config).model_validate(high_pressure_data)

        low_world = generate_world(low_pressure)
        high_world = generate_world(high_pressure)

        low_mean_temp = sum(cell["temperature_c"] for cell in low_world["cells"]) / len(low_world["cells"])
        high_mean_temp = sum(cell["temperature_c"] for cell in high_world["cells"]) / len(high_world["cells"])

        self.assertGreater(high_mean_temp, low_mean_temp)
    def test_zero_precipitation_scale_is_a_true_dry_boundary(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 0
        data["climate"]["precipitation_scale"] = 0.0

        world = generate_world(type(config).model_validate(data))
        land = [cell for cell in world["cells"] if not cell["is_water"]]

        self.assertTrue(land)
        self.assertEqual(
            world["climate_model"]["zero_precipitation_scale_behavior"],
            "exact_zero_monthly_and_annual_precipitation",
        )
        self.assertEqual(
            world["climate_model"]["negative_precipitation_behavior"],
            "clamped_to_zero_before_thermal_moisture_multiplier",
        )
        self.assertTrue(
            all(cell["precipitation_mm_y"] == 0.0 for cell in world["cells"])
        )
        self.assertTrue(
            all(
                monthly == 0.0
                for cell in world["cells"]
                for monthly in cell["precipitation_monthly_mm"]
            )
        )
        self.assertTrue(all(cell["runoff_mm_y"] == 0.0 for cell in land))
        self.assertTrue(
            all(cell["actual_evapotranspiration_mm_y"] == 0.0 for cell in land)
        )
        self.assertTrue(all(cell["infiltration_mm_y"] == 0.0 for cell in land))
    def test_near_zero_precipitation_scale_preserves_proportional_forcing(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 0
        data["climate"]["precipitation_scale"] = 1.0e-6

        world = generate_world(type(config).model_validate(data))
        precipitation = [
            float(cell["precipitation_mm_y"]) for cell in world["cells"]
        ]

        self.assertTrue(any(value > 0.0 for value in precipitation))
        self.assertLess(max(precipitation), 0.02)
        self.assertTrue(any(0.0 < value < 0.001 for value in precipitation))
    def test_subtropical_drying_strength_reduces_horse_latitude_rainfall(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        dry_data = config.model_dump(mode="python")
        dry_data["mesh"]["cell_count"] = 256
        dry_data["tectonics"]["plate_count"] = 8
        dry_data["erosion"]["iterations"] = 0
        dry = type(config).model_validate(dry_data)

        no_drying_data = config.model_dump(mode="python")
        no_drying_data["mesh"]["cell_count"] = 256
        no_drying_data["tectonics"]["plate_count"] = 8
        no_drying_data["erosion"]["iterations"] = 0
        no_drying_data["climate"]["subtropical_drying_strength"] = 0.0
        no_drying = type(config).model_validate(no_drying_data)

        dry_world = generate_world(dry)
        no_drying_world = generate_world(no_drying)

        def mean_land_precipitation(world: dict, minimum_lat: float, maximum_lat: float) -> float:
            values = [
                cell["precipitation_mm_y"]
                for cell in world["cells"]
                if not cell["is_water"] and minimum_lat <= abs(cell["lat_deg"]) <= maximum_lat
            ]
            self.assertTrue(values)
            return sum(values) / len(values)

        dry_subtropical = mean_land_precipitation(dry_world, 20.0, 40.0)
        wet_subtropical = mean_land_precipitation(no_drying_world, 20.0, 40.0)
        dry_equatorial = mean_land_precipitation(dry_world, 0.0, 10.0)
        wet_equatorial = mean_land_precipitation(no_drying_world, 0.0, 10.0)

        self.assertLess(dry_subtropical, wet_subtropical * 0.75)
        self.assertGreater(dry_equatorial, wet_equatorial * 0.95)
        seasonal_tropical_land = [
            cell
            for cell in dry_world["cells"]
            if not cell["is_water"] and 10.0 <= abs(cell["lat_deg"]) <= 25.0
        ]
        self.assertTrue(
            any(
                max(cell["precipitation_monthly_mm"])
                - min(cell["precipitation_monthly_mm"])
                >= 100.0
                and cell["dry_season_months"] >= 2
                and cell["wet_season_months"] >= 3
                for cell in seasonal_tropical_land
            )
        )
        self.assertEqual(dry_world["climate_model"]["subtropical_drying_strength"], 0.65)
        self.assertEqual(no_drying_world["climate_model"]["subtropical_drying_strength"], 0.0)


class LegacyClimateCompatibilityTests(TestCase):
    """Preserved old controls are selected explicitly, never through defaults."""
    def test_legacy_climate_model(self) -> None:
        world = worlds.cached_legacy_world_readonly("energy_128")
        climate_model = world["climate_model"]
        self.assertEqual(
            climate_model["model_type"],
            "equilibrium_latitude_circulation_climate_v5",
        )
        self.assertEqual(
            climate_model["precipitation_model"],
            "bounded_thermal_moisture_circulation_orography_wind_transport_v3",
        )
        self.assertEqual(climate_model["marine_annual_temperature_offset_c"], 0.0)
        self.assertTrue(climate_model["latitude_temperature_area_normalized"])
        self.assertTrue(climate_model["local_temperature_adjustments_area_centered"])
        self.assertFalse(climate_model["mass_conserving_atmosphere"])
        self.assertFalse(climate_model["transient_climate_resolved"])
        self.assertAlmostEqual(
            climate_model["latitude_temperature_area_mean_offset_c"],
            climate_model["latitude_temperature_gradient_c"]
            / (climate_model["latitude_temperature_exponent"] + 1.0),
            delta=0.00001,
        )
        self.assertEqual(climate_model["subtropical_drying_strength"], 0.65)
        self.assertEqual(climate_model["seasonal_monsoon_precipitation_strength"], 1.6)
        self.assertEqual(climate_model["thermal_moisture_capacity_factor"], 1.0)
        self.assertEqual(
            climate_model["thermal_moisture_capacity_temperature_anomaly_c"],
            0.0,
        )
    def test_legacy_posthoc_energy_summary_and_records(self) -> None:
        world = worlds.cached_legacy_world_readonly("energy_128")
        small = worlds.build_legacy_config(**worlds.LEGACY_CANONICAL["energy_128"])
        summary = world["summary"]
        first_cell = world["cells"][0]
        self.assertEqual(summary["climate_energy_balance_record_count"], len(world["climate_energy_balance_records"]))
        self.assertEqual(summary["climate_energy_balance_record_count"], len(world["cells"]))
        self.assertEqual(sum(summary["surface_albedo_regime_counts"].values()), summary["cell_count"])
        self.assertGreater(summary["mean_top_of_atmosphere_insolation_w_m2"], 0.0)
        self.assertGreaterEqual(summary["mean_seasonal_insolation_range_w_m2"], 0.0)
        self.assertGreaterEqual(summary["mean_orbital_insolation_variability_index"], 0.0)
        self.assertLessEqual(summary["mean_orbital_insolation_variability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_peak_seasonal_insolation_w_m2"], summary["mean_low_seasonal_insolation_w_m2"])
        self.assertGreaterEqual(summary["mean_low_seasonal_insolation_w_m2"], 0.0)
        self.assertGreater(summary["mean_orbital_distance_factor"], 0.0)
        self.assertAlmostEqual(summary["orbital_eccentricity"], small.planet.orbital_eccentricity, delta=0.001)
        self.assertGreaterEqual(summary["mean_surface_albedo_index"], 0.0)
        self.assertLessEqual(summary["mean_surface_albedo_index"], 1.0)
        self.assertGreaterEqual(summary["mean_absorbed_shortwave_w_m2"], 0.0)
        self.assertGreater(summary["mean_outgoing_longwave_w_m2"], 0.0)
        self.assertGreaterEqual(summary["mean_greenhouse_trapping_w_m2"], 0.0)
        self.assertGreaterEqual(summary["mean_abs_energy_balance_residual_c"], 0.0)
        self.assertGreaterEqual(summary["mean_climate_energy_stress_index"], 0.0)
        self.assertLessEqual(summary["mean_climate_energy_stress_index"], 1.0)
        self.assertEqual(
            summary["high_climate_energy_stress_cell_count"],
            sum(1 for record in world["climate_energy_balance_records"] if record["climate_energy_stress_index"] >= 0.65),
        )
        self.assertAlmostEqual(
            summary["mean_absorbed_shortwave_w_m2"],
            sum(record["absorbed_shortwave_w_m2"] for record in world["climate_energy_balance_records"])
            / len(world["climate_energy_balance_records"]),
            delta=0.001,
        )
        first_energy_record = world["climate_energy_balance_records"][0]
        self.assertEqual(first_energy_record["id"], 0)
        self.assertEqual(first_energy_record["cell_id"], first_cell["id"])
        self.assertEqual(first_energy_record["biome"], first_cell["biome"])
        self.assertEqual(first_energy_record["water_body_type"], first_cell["water_body_type"])
        self.assertEqual(first_energy_record["surface_albedo_regime"], first_cell["surface_albedo_regime"])
        self.assertGreater(first_energy_record["stellar_luminosity_factor"], 0.0)
        self.assertGreaterEqual(first_energy_record["planetary_greenhouse_factor"], 0.0)
        self.assertGreaterEqual(first_energy_record["atmosphere_pressure_bar"], 0.0)
        self.assertAlmostEqual(first_energy_record["orbital_eccentricity"], small.planet.orbital_eccentricity, delta=0.001)
        self.assertGreater(first_energy_record["mean_orbital_distance_factor"], 0.0)
        monthly_insolation = first_energy_record["monthly_top_of_atmosphere_insolation_w_m2"]
        self.assertEqual(len(monthly_insolation), len(first_cell["temperature_monthly_c"]))
        self.assertTrue(all(value >= 0.0 for value in monthly_insolation))
        self.assertAlmostEqual(
            first_energy_record["top_of_atmosphere_insolation_w_m2"],
            sum(monthly_insolation) / len(monthly_insolation),
            delta=0.001,
        )
        self.assertAlmostEqual(first_energy_record["peak_seasonal_insolation_w_m2"], max(monthly_insolation), delta=0.001)
        self.assertAlmostEqual(first_energy_record["low_seasonal_insolation_w_m2"], min(monthly_insolation), delta=0.001)
        self.assertAlmostEqual(
            first_energy_record["seasonal_insolation_range_w_m2"],
            first_energy_record["peak_seasonal_insolation_w_m2"] - first_energy_record["low_seasonal_insolation_w_m2"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            first_energy_record["orbital_insolation_variability_index"],
            min(
                1.0,
                first_energy_record["seasonal_insolation_range_w_m2"]
                / max(1.0, first_energy_record["top_of_atmosphere_insolation_w_m2"]),
            ),
            delta=0.001,
        )
        for key in (
            "seasonal_insolation_range_w_m2",
            "orbital_insolation_variability_index",
            "peak_seasonal_insolation_w_m2",
            "low_seasonal_insolation_w_m2",
        ):
            self.assertAlmostEqual(first_energy_record[key], first_cell[key], delta=0.001)
        self.assertAlmostEqual(
            first_energy_record["absorbed_shortwave_w_m2"],
            first_energy_record["top_of_atmosphere_insolation_w_m2"] * (1.0 - first_energy_record["surface_albedo_index"]),
            delta=0.001,
        )
        self.assertAlmostEqual(
            first_energy_record["net_radiative_balance_w_m2"],
            first_energy_record["absorbed_shortwave_w_m2"]
            + first_energy_record["greenhouse_trapping_w_m2"]
            - first_energy_record["outgoing_longwave_w_m2"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            first_energy_record["energy_balance_residual_c"],
            first_energy_record["temperature_c"] - first_energy_record["radiative_equilibrium_temperature_c"],
            delta=0.001,
        )
        self.assertAlmostEqual(
            first_energy_record["climate_energy_stress_index"],
            first_cell["climate_energy_stress_index"],
            delta=0.001,
        )

    def test_legacy_base_temperature_is_area_mean_normalized(self) -> None:
        config = worlds.build_legacy_config()
        baseline_data = config.model_dump(mode="python")
        baseline_data["mesh"]["cell_count"] = 256
        baseline_data["tectonics"]["plate_count"] = 8
        baseline_data["erosion"]["iterations"] = 0
        baseline = type(config).model_validate(baseline_data)

        warmer_data = config.model_dump(mode="python")
        warmer_data["mesh"]["cell_count"] = 256
        warmer_data["tectonics"]["plate_count"] = 8
        warmer_data["erosion"]["iterations"] = 0
        warmer_data["climate"]["base_temperature_c"] = 20.0
        warmer = type(config).model_validate(warmer_data)

        baseline_world = generate_world(baseline)
        warmer_world = generate_world(warmer)
        baseline_mean = sum(cell["temperature_c"] for cell in baseline_world["cells"]) / len(
            baseline_world["cells"]
        )
        warmer_mean = sum(cell["temperature_c"] for cell in warmer_world["cells"]) / len(
            warmer_world["cells"]
        )

        self.assertAlmostEqual(baseline_mean, baseline.climate.base_temperature_c, delta=0.02)
        self.assertAlmostEqual(warmer_mean - baseline_mean, 5.0, delta=0.01)
        self.assertEqual(
            baseline_world["climate_model"]["base_temperature_interpretation"],
            "post_centered_local_adjustment_global_area_mean_c",
        )
