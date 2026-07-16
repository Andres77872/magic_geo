import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.api import generate_world
from magic_geo.cli import app
from magic_geo.config import load_config


class YoungPlanetCrustAgeTests(TestCase):
    def test_initial_and_evolved_crust_never_predate_planet(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["planet"]["geological_age_ga"] = 0.05
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 2
        young_planet = type(config).model_validate(data)

        world = generate_world(young_planet)
        planet_age_ma = young_planet.planet.geological_age_ga * 1000.0
        cells = world["cells"]

        initial_ages = [
            float(age)
            for age in world["plate_motion_history"][0]["crust_overlap_ledger"][
                "remapped_crust_age_ma_by_cell"
            ]
        ]
        final_ages = [float(cell["crust_age_ma"]) for cell in cells]
        self.assertTrue(all(0.0 <= age <= planet_age_ma for age in initial_ages))
        self.assertTrue(all(0.0 <= age <= planet_age_ma for age in final_ages))
        self.assertTrue(
            all(
                0.0 <= float(plate["mean_crust_age_ma"]) <= planet_age_ma
                for plate in world["plates"]
            )
        )

        reconstructed_ages = initial_ages
        for index, step in enumerate(world["plate_motion_history"]):
            if index:
                reconstructed_ages = [
                    age + float(delta)
                    for age, delta in zip(
                        reconstructed_ages,
                        step["crust_age_change_ma_by_cell"],
                    )
                ]
            self.assertTrue(all(math.isfinite(age) for age in reconstructed_ages))
            self.assertTrue(
                all(-0.0001 <= age <= planet_age_ma + 0.0001 for age in reconstructed_ages)
            )

        for reconstructed, final in zip(reconstructed_ages, final_ages):
            self.assertAlmostEqual(reconstructed, final, places=3)

        with TemporaryDirectory() as temp_dir:
            world_path = Path(temp_dir) / "young-planet.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            valid_result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            self.assertEqual(valid_result.exit_code, 0, valid_result.output)

            initial_age_ledger = world["plate_motion_history"][0][
                "crust_overlap_ledger"
            ]["remapped_crust_age_ma_by_cell"]
            original_initial_age = initial_age_ledger[0]
            initial_age_ledger[0] = planet_age_ma + 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "crust ages exceed configured geological age",
                invalid_result.output,
            )

            initial_age_ledger[0] = original_initial_age
            first_transition = world["plate_motion_history"][1]
            first_transition["crust_age_change_ma_by_cell"][0] = planet_age_ma + 1.0
            world_path.write_text(json.dumps(world), encoding="utf-8")
            invalid_result = CliRunner().invoke(app, ["validate", "--world", str(world_path)])
            self.assertNotEqual(invalid_result.exit_code, 0)
            self.assertIn(
                "crust ages exceed configured geological age",
                invalid_result.output,
            )
