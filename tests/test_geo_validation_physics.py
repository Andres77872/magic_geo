from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.api import generate_geo_world
from magic_geo.config import WorldConfig, load_config
from magic_geo.geo_validation_physics import validate_physics_replays


def _small_earth_config() -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    return WorldConfig.model_validate(data)


def _check(checks: list[dict], domain: str, name: str) -> dict:
    return next(
        check
        for check in checks
        if check["domain"] == domain and check["name"] == name
    )


class GeoPhysicsReplayValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(_small_earth_config())

    def test_generated_geo_world_passes_all_physics_replays(self) -> None:
        checks = validate_physics_replays(self.world)

        self.assertEqual(len(checks), 4)
        self.assertTrue(all(check["passed"] for check in checks))
        for index, check in enumerate(checks):
            self.assertEqual(check["id"], index)
            self.assertEqual(check["status"], "passed")
            self.assertEqual(check["severity"], "error")
            self.assertEqual(
                set(check),
                {
                    "id",
                    "domain",
                    "name",
                    "status",
                    "passed",
                    "severity",
                    "message",
                    "observed",
                    "expected",
                    "evidence",
                },
            )

    def test_zero_ocean_final_feedback_uses_numeric_not_count_semantics(self) -> None:
        data = _small_earth_config().model_dump(mode="python")
        data["planet"]["ocean_fraction_target"] = 0.0
        data["planet"]["ocean_water_inventory_km3"] = 0.0
        data["climate"]["precipitation_scale"] = 0.12
        world = generate_geo_world(WorldConfig.model_validate(data))

        check = _check(
            validate_physics_replays(world),
            "simulation",
            "coupled_stage_feedback_replay",
        )

        self.assertTrue(check["passed"], check["evidence"])

    def test_negative_plate_area_and_stale_means_fail_cell_replay(self) -> None:
        altered = deepcopy(self.world)
        altered["plates"][0]["area_km2"] = -1.0
        altered["plates"][0]["mean_crust_density"] = 99.0

        check = _check(
            validate_physics_replays(altered),
            "tectonics",
            "plate_aggregate_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertGreater(check["observed"]["violation_count"], 0)
        self.assertTrue(
            any(
                "area_km2" in violation or "mean_crust_density" in violation
                for violation in check["evidence"]["violations"]
            )
        )

    def test_colluding_negative_energy_mirrors_fail_equation_replay(self) -> None:
        altered = deepcopy(self.world)
        record = altered["climate_energy_balance_records"][0]
        cell_id = record["cell_id"]
        cell = next(cell for cell in altered["cells"] if cell["id"] == cell_id)
        previous = record["absorbed_shortwave_w_m2"]
        record["absorbed_shortwave_w_m2"] = -100.0
        cell["absorbed_shortwave_w_m2"] = -100.0
        altered["summary"]["mean_absorbed_shortwave_w_m2"] += (
            -100.0 - previous
        ) / len(altered["cells"])

        check = _check(
            validate_physics_replays(altered),
            "climate",
            "climate_energy_balance_replay",
        )

        self.assertFalse(check["passed"])
        self.assertTrue(
            any(
                "absorbed_shortwave_w_m2" in violation
                or "negative energy flux" in violation
                for violation in check["evidence"]["violations"]
            )
        )

    def test_incomplete_feedback_record_fails_structure_even_when_length_matches(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["earth_system_feedback_history"][1].pop("stage")

        check = _check(
            validate_physics_replays(altered),
            "simulation",
            "coupled_stage_feedback_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(
            check["observed"]["feedback_record_count"],
            altered["simulation_clock"]["stage_count"],
        )
        self.assertTrue(
            any(
                "missing fields" in violation
                for violation in check["evidence"]["violations"]
            )
        )

    def test_feedback_summary_and_clock_counter_mutations_fail_mirror_replay(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["summary"]["simulation_clock_stage_count"] += 1
        altered["simulation_clock"]["feedback_recompute_count"] += 1

        check = _check(
            validate_physics_replays(altered),
            "simulation",
            "coupled_stage_summary_mirrors",
        )

        self.assertFalse(check["passed"])
        self.assertGreaterEqual(check["observed"]["violation_count"], 2)

    def test_malformed_root_is_reported_without_conversion_errors(self) -> None:
        checks = validate_physics_replays({"cells": "not-a-list"})

        self.assertEqual(len(checks), 4)
        self.assertTrue(all(not check["passed"] for check in checks))
