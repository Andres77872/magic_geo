"""An economy's opening balance participates in its historical treasury peak."""

from __future__ import annotations

import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.api import generate_world
from magic_geo.cli import app
from magic_geo.history_economy_validation import validate_history_economy_replay
from magic_geo.io import write_json
from support.cli import assert_no_cli_crash
from support.worlds import build_legacy_config, cached_world_readonly


class EconomyOpeningTreasuryValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # This regression originally used the pre-seasonal Earth YAML. Its
        # economy declines at every step; the current seasonal Earth economy
        # grows and is a separate full-CLI control below. Keep the original
        # physical inputs explicit instead of adjusting current temperatures.
        cls.world = generate_world(build_legacy_config(**{
            "mesh.cell_count": 128,
            "tectonics.plate_count": 8,
            "erosion.iterations": 0,
            "tectonics.plate_motion_scale_deg_per_step": 4.0,
            "climate.precipitation_scale": 0.8,
        }))

    def _validate(self, world):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "world.json"
            write_json(path, world)
            result = CliRunner().invoke(app, ["validate", "--world", str(path)])
        assert_no_cli_crash(self, result, command="validate")
        return result

    def test_declining_treasury_keeps_its_opening_peak(self) -> None:
        self.assertEqual(
            self.world["climate_model"]["model_type"],
            "equilibrium_latitude_circulation_climate_v5",
        )
        self.assertEqual(validate_history_economy_replay(self.world), [])
        self.assertTrue(self.world["economy_histories"])
        history = self.world["economy_histories"][0]
        self.assertTrue(history["steps"])
        opening = history["steps"][0]["treasury_start_index"]
        self.assertGreater(opening, 0.0)
        self.assertEqual(history["peak_treasury_index"], opening)
        self.assertTrue(all(
            step["treasury_end_index"] < step["treasury_start_index"]
            for step in history["steps"]
        ))
        result = self._validate(self.world)
        self.assertEqual(result.exit_code, 0, result.output)

    def test_peak_that_omits_the_opening_balance_is_rejected(self) -> None:
        world = copy.deepcopy(self.world)
        history = world["economy_histories"][0]
        ending_peak = max(step["treasury_end_index"] for step in history["steps"])
        self.assertLess(ending_peak, history["peak_treasury_index"])
        history["peak_treasury_index"] = ending_peak
        result = self._validate(world)
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("FAIL economy history fields invalid", result.output)

    def test_current_seasonal_world_passes_full_validation(self) -> None:
        world = cached_world_readonly("replay_128")
        self.assertEqual(
            world["climate_model"]["model_type"],
            "prescribed_seasonal_surface_energy_v1",
        )
        self.assertTrue(world["economy_histories"])
        self.assertEqual(validate_history_economy_replay(world), [])
        result = self._validate(world)
        self.assertEqual(result.exit_code, 0, result.output)
