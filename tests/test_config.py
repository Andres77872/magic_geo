from pathlib import Path
from unittest import TestCase

from magic_geo.config import load_config


class ConfigTests(TestCase):
    def test_seed_config_loads(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))

        self.assertEqual(config.run.seed, 424242)
        self.assertEqual(config.mesh.backend, "fibonacci_sphere")
        self.assertEqual(config.mesh.cell_count, 4096)
        self.assertLess(config.tectonics.plate_count, config.mesh.cell_count)
        self.assertEqual(config.tectonics.plate_motion_scale_deg_per_step, 2.0)
        self.assertEqual(config.tectonics.oceanic_crust_aging_ma_per_step, 5.0)
        self.assertEqual(config.tectonics.continental_crust_fraction_target, 0.34)
        self.assertEqual(config.planet.ocean_water_inventory_km3, 1_338_000_000.0)
        self.assertEqual(config.climate.subtropical_drying_strength, 0.65)
        self.assertEqual(config.climate.precipitation_scale, 0.8)
        self.assertIs(config.output.include_cells, True)

    def test_climate_month_count_is_twelve(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["climate"]["months"] = 6

        with self.assertRaises(ValueError):
            type(config).model_validate(data)

    def test_continental_crust_fraction_target_is_bounded(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["tectonics"]["continental_crust_fraction_target"] = 0.96

        with self.assertRaises(ValueError):
            type(config).model_validate(data)

    def test_ocean_water_inventory_is_bounded(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["planet"]["ocean_water_inventory_km3"] = -1.0

        with self.assertRaises(ValueError):
            type(config).model_validate(data)
