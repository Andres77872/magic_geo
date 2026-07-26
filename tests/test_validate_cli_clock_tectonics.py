"""Public ``validate`` CLI violations for clocks, cells, and plate motion.

Every case here drives the public Typer application through ``CliRunner`` on a
world that differs from a healthy generated world by exactly one tampered
field, and pins the whole ``FAIL <message>`` line the corresponding check
emits.  The untampered control run is asserted to exit ``0`` alongside every
tamper, so a red case always means the tamper produced the failure rather than
a broken fixture, and ``Traceback`` is asserted absent so a check that starts
crashing instead of reporting is caught.  Every tamper is additionally proved
to have changed the world, so a hand-written tamper value that happens to
equal the generated one cannot leave a silently passing case.

The slice covers the climate-model metadata gate, the simulation clock and
earth-system feedback history, the per-cell orientation vectors, the spherical
control-volume area closure, the plate summary records, and the plate kinematic
model together with the plate motion history.
"""

from __future__ import annotations

import copy
import itertools
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.io import write_json

from support import worlds

from support.cli import assert_no_cli_crash
import pytest

# Exhaustive branch coverage of ``validate``: every case invokes the full CLI
# over a generated world. Deselect locally with -m "not slow".
pytestmark = pytest.mark.slow

#: The smallest canonical world that carries a full simulation clock, feedback
#: history, plate kinematic model, and plate motion history.
WORLD_KEY = "replay_128"

#: The untampered ``validate`` run, shared by every class below. All twelve
#: slices tamper copies of the same world, so re-running the control per class
#: would repeat one identical serialization and one identical full validation
#: pass twelve times over.
_CONTROL: tuple[int, str] | None = None


def _control_run() -> tuple[int, str]:
    global _CONTROL
    if _CONTROL is None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "control.json"
            write_json(path, worlds.cached_world_readonly(WORLD_KEY))
            result = CliRunner().invoke(app, ["validate", "--world", str(path)])
        _CONTROL = (result.exit_code, result.output)
    return _CONTROL

Tamper = Callable[[dict[str, Any]], None]


class _TamperCase:
    """Shared baseline world, control run, and single-tamper CLI driver."""

    baseline: dict[str, Any]
    control_output: str
    control_exit_code: int

    @classmethod
    def setUpClass(cls) -> None:
        cls._tempdir = TemporaryDirectory()
        cls._root = Path(cls._tempdir.name)
        cls._counter = itertools.count()
        cls.baseline = worlds.cached_world(WORLD_KEY)
        cls.control_exit_code, cls.control_output = _control_run()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tempdir.cleanup()

    def assert_control_passes(self) -> None:
        """The untampered baseline must validate cleanly."""
        self.assertEqual(self.control_exit_code, 0, self.control_output)
        self.assertNotIn("FAIL", self.control_output)

    def run_tampered(self, tamper: Tamper) -> Any:
        world = copy.deepcopy(self.baseline)
        tamper(world)
        # A tamper that writes back the value the generator already produced
        # would leave a silently passing test, so prove the world moved.
        self.assertNotEqual(
            world,
            self.baseline,
            "tamper left the world byte-identical to the baseline",
        )
        path = self._root / f"tampered_{next(self._counter)}.json"
        write_json(path, world)
        try:
            return CliRunner().invoke(app, ["validate", "--world", str(path)])
        finally:
            # Each serialised world is tens of megabytes; drop it immediately
            # rather than letting a whole class worth of them pile up.
            path.unlink(missing_ok=True)

    def assert_tamper_fails(self, tamper: Tamper, message: str) -> str:
        """Assert ``tamper`` makes ``validate`` report exactly ``message``."""
        self.assert_control_passes()
        result = self.run_tampered(tamper)
        assert_no_cli_crash(self, result)
        self.assertEqual(result.exit_code, 1, result.output)
        # Pin the whole reported line, not a substring of it: a longer message
        # that merely starts with ``message`` must not satisfy the assertion.
        self.assertIn(f"FAIL {message}", result.output.splitlines(), result.output)
        return result.output


CLIMATE_FAILURE = "climate model metadata invalid"


class ClimateModelMetadataTest(_TamperCase, TestCase):
    """The ``climate model metadata invalid`` gate."""

    def test_non_numeric_climate_model_field_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["climate_model"]["lapse_rate_c_per_km"] = "not-a-number"

        self.assert_tamper_fails(tamper, CLIMATE_FAILURE)

    def test_non_positive_stellar_luminosity_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["planet_parameters"]["stellar_luminosity"] = -1.0

        self.assert_tamper_fails(tamper, CLIMATE_FAILURE)

    def test_missing_planet_temperature_control_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            del world["planet_parameters"]["greenhouse_factor"]

        self.assert_tamper_fails(tamper, CLIMATE_FAILURE)

    def test_inconsistent_thermal_moisture_anomaly_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            climate_model = world["climate_model"]
            climate_model["thermal_moisture_capacity_temperature_anomaly_c"] = (
                float(climate_model["thermal_moisture_capacity_temperature_anomaly_c"])
                + 1.0
            )

        self.assert_tamper_fails(tamper, CLIMATE_FAILURE)

    def test_declared_model_type_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["climate_model"]["model_type"] = "hand_written_climate_v0"

        self.assert_tamper_fails(tamper, CLIMATE_FAILURE)


CLOCK_STRUCTURE_FAILURE = "simulation_clock missing or incomplete"
HISTORY_STRUCTURE_FAILURE = "earth_system_feedback_history missing"
CLOCK_SUMMARY_FAILURE = "simulation clock summary metrics missing"
FEEDBACK_FAILURE = "simulation clock or earth-system feedback history invalid"


class SimulationClockStructureTest(_TamperCase, TestCase):
    """Structural gates around ``simulation_clock`` and the feedback history."""

    def test_incomplete_simulation_clock_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            del world["simulation_clock"]["clock_type"]

        self.assert_tamper_fails(tamper, CLOCK_STRUCTURE_FAILURE)

    def test_non_list_feedback_history_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["earth_system_feedback_history"] = {}

        self.assert_tamper_fails(tamper, HISTORY_STRUCTURE_FAILURE)

    def test_missing_clock_summary_metric_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            del world["summary"]["simulation_clock_stage_count"]

        self.assert_tamper_fails(tamper, CLOCK_SUMMARY_FAILURE)


class SimulationClockContentTest(_TamperCase, TestCase):
    """Numeric and declarative content of ``simulation_clock``."""

    def test_non_numeric_clock_counter_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["simulation_clock"]["stage_count"] = "eight"

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_declared_clock_fields_are_pinned(self) -> None:
        cases = {
            "clock_type": "hand_written_clock_v0",
            "time_unit": "seconds",
            "nominal_time_unit": "ka",
            "nominal_time_direction": "backward_from_present",
        }
        for field, value in cases.items():
            with self.subTest(field=field):

                def tamper(world: dict[str, Any], field: str = field, value: str = value) -> None:
                    world["simulation_clock"][field] = value

                self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_clock_water_budget_recompute_count_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["simulation_clock"]["hydrologic_water_budget_recompute_count"] = 999

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_summary_stage_count_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["summary"]["simulation_clock_stage_count"] = 999

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_summary_feedback_value_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["summary"]["final_feedback_mean_abs_runoff_change_mm_y"] = 999.0

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_non_numeric_ocean_inventory_breaks_feedback_volume_target(self) -> None:
        """The feedback history needs a numeric ocean-water inventory target."""

        def tamper(world: dict[str, Any]) -> None:
            world["planet_parameters"]["ocean_water_inventory_km3"] = "an ocean"

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)


class FeedbackStepTest(_TamperCase, TestCase):
    """Per-step records of ``earth_system_feedback_history``."""

    def test_incomplete_feedback_step_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            del world["earth_system_feedback_history"][0]["cell_count"]

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_non_numeric_feedback_counter_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["earth_system_feedback_history"][0]["sea_level_recompute_count"] = "one"

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_unexpected_feedback_stage_label_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["earth_system_feedback_history"][0]["stage"] = "erosion_iteration"

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_initial_step_with_change_from_previous_stage_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            step = world["earth_system_feedback_history"][0]
            step["mean_abs_temperature_change_c_from_previous_stage"] = 5.0

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_fluvial_volume_outside_erosion_step_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            step = world["earth_system_feedback_history"][0]
            step["fluvial_sediment_local_source_volume_km3"] = 5.0

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_glacial_volume_outside_cryosphere_step_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            step = world["earth_system_feedback_history"][0]
            step["glacial_sediment_production_volume_km3"] = 5.0

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_broken_cumulative_sediment_mass_balance_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            step = world["earth_system_feedback_history"][-1]
            step["cumulative_sediment_production_volume_km3"] = (
                float(step["cumulative_sediment_production_volume_km3"]) + 100_000.0
            )

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)


class FinalFeedbackStepTest(_TamperCase, TestCase):
    """The final feedback step must mirror the emitted cell payload."""

    def test_final_integer_metric_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            step = world["earth_system_feedback_history"][-1]
            emitted = sum(1 for cell in world["cells"] if bool(cell.get("is_river", False)))
            step["river_cell_count"] = 0 if emitted else 1

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_final_ocean_area_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            step = world["earth_system_feedback_history"][-1]
            step["ocean_area_km2"] = float(step["ocean_area_km2"]) + 1.0

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_final_ocean_volume_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            step = world["earth_system_feedback_history"][-1]
            step["ocean_volume_km3"] = float(step["ocean_volume_km3"]) + 1000.0

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_final_cumulative_sediment_volume_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            step = world["earth_system_feedback_history"][-1]
            offset = 100_000.0
            step["cumulative_sediment_production_volume_km3"] = (
                float(step["cumulative_sediment_production_volume_km3"]) + offset
            )
            step["cumulative_sediment_deposition_volume_km3"] = (
                float(step["cumulative_sediment_deposition_volume_km3"]) + offset
            )

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)

    def test_final_mean_temperature_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            step = world["earth_system_feedback_history"][-1]
            step["mean_temperature_c"] = float(step["mean_temperature_c"]) + 5.0

        self.assert_tamper_fails(tamper, FEEDBACK_FAILURE)


CELL_VECTOR_FAILURE = "cell position_3d/normal_3d fields invalid"


class CellOrientationVectorTest(_TamperCase, TestCase):
    """Per-cell ``position_3d``/``normal_3d`` consistency."""

    def test_wrong_length_position_vector_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["cells"][0]["position_3d"] = [1.0, 0.0]

        self.assert_tamper_fails(tamper, CELL_VECTOR_FAILURE)

    def test_non_numeric_position_component_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["cells"][0]["position_3d"] = ["a", "b", "c"]

        self.assert_tamper_fails(tamper, CELL_VECTOR_FAILURE)

    def test_non_unit_position_vector_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            cell = world["cells"][0]
            cell["position_3d"] = [
                float(component) * 2.0 for component in cell["position_3d"]
            ]

        self.assert_tamper_fails(tamper, CELL_VECTOR_FAILURE)

    def test_degenerate_position_vector_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["cells"][0]["position_3d"] = [0.0, 0.0, 0.0]

        self.assert_tamper_fails(tamper, CELL_VECTOR_FAILURE)


AREA_FAILURE = "native cell area model or spherical area closure invalid"


class CellAreaClosureTest(_TamperCase, TestCase):
    """The declared cell-area model and the spherical area closure."""

    def test_unknown_cell_area_model_is_reported(self) -> None:
        """A model the mesh backend does not mandate is rejected on its own.

        The summary mirror is moved with the payload so that the summary
        agreement check cannot be what reports this world: only the
        ``cell_area_model`` against the backend comparison can fire.
        """

        def tamper(world: dict[str, Any]) -> None:
            world["cell_area_model"] = "hand_written_area_model_v0"
            world["summary"]["cell_area_model"] = "hand_written_area_model_v0"

        self.assert_tamper_fails(tamper, AREA_FAILURE)

    def test_summary_cell_area_model_disagreement_is_reported(self) -> None:
        """The summary must mirror the payload's declared cell-area model."""

        def tamper(world: dict[str, Any]) -> None:
            world["summary"]["cell_area_model"] = "hand_written_area_model_v0"

        self.assert_tamper_fails(tamper, AREA_FAILURE)

    def test_missing_area_summary_metric_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            del world["summary"]["cell_area_coefficient_of_variation"]

        self.assert_tamper_fails(tamper, AREA_FAILURE)

    def test_summary_mean_cell_area_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["summary"]["mean_cell_area_km2"] = (
                float(world["summary"]["mean_cell_area_km2"]) + 1000.0
            )

        self.assert_tamper_fails(tamper, AREA_FAILURE)

    def test_non_numeric_ocean_inventory_breaks_area_closure(self) -> None:
        """The area closure needs a numeric ocean-water inventory target."""

        def tamper(world: dict[str, Any]) -> None:
            world["planet_parameters"]["ocean_water_inventory_km3"] = "an ocean"

        self.assert_tamper_fails(tamper, AREA_FAILURE)

    def test_degenerate_control_volume_polygon_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            cell = world["cells"][0]
            cell["control_volume_vertices_3d"] = cell["control_volume_vertices_3d"][:2]
            cell["control_volume_edge_neighbor_ids"] = cell[
                "control_volume_edge_neighbor_ids"
            ][:2]

        self.assert_tamper_fails(tamper, AREA_FAILURE)


PLATES_MISSING_FAILURE = "plates missing"
PLATE_COUNT_FAILURE = "plate_count does not match plates length"
PLATE_SUMMARY_FAILURE = "plate summary fields invalid"


class PlateRecordTest(_TamperCase, TestCase):
    """The ``plates`` payload and its per-plate summary fields."""

    def test_non_list_plates_payload_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["plates"] = {}

        self.assert_tamper_fails(tamper, PLATES_MISSING_FAILURE)

    def test_plate_count_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["summary"]["plate_count"] = 99

        self.assert_tamper_fails(tamper, PLATE_COUNT_FAILURE)

    def test_incomplete_plate_record_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            del world["plates"][0]["thermal_state"]

        self.assert_tamper_fails(tamper, PLATE_SUMMARY_FAILURE)

    def test_non_numeric_plate_field_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["plates"][0]["cumulative_rotation_deg"] = "twenty"

        self.assert_tamper_fails(tamper, PLATE_SUMMARY_FAILURE)

    def test_unknown_plate_kind_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["plates"][0]["kind"] = "metallic"

        self.assert_tamper_fails(tamper, PLATE_SUMMARY_FAILURE)

    def test_wrong_thermal_state_label_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["plates"][0]["thermal_state"] = "molten"

        self.assert_tamper_fails(tamper, PLATE_SUMMARY_FAILURE)

    def test_cell_pointing_at_unknown_plate_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["cells"][0]["plate_id"] = 999

        self.assert_tamper_fails(tamper, PLATE_SUMMARY_FAILURE)


MOTION_FAILURE = "plate kinematic model or motion history invalid"
CRUST_AGE_FAILURE = "crust ages exceed configured geological age"


class PlateKinematicModelTest(_TamperCase, TestCase):
    """The ``plate_kinematic_model`` record."""

    def test_incomplete_kinematic_model_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            del world["plate_kinematic_model"]["model_type"]

        self.assert_tamper_fails(tamper, MOTION_FAILURE)

    def test_non_numeric_kinematic_field_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["plate_kinematic_model"]["motion_scale_deg_per_step"] = "four"

        self.assert_tamper_fails(tamper, MOTION_FAILURE)

    def test_declared_kinematic_time_unit_is_pinned(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["plate_kinematic_model"]["time_unit"] = "seconds"

        self.assert_tamper_fails(tamper, MOTION_FAILURE)

    def test_initial_continental_cell_count_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            model = world["plate_kinematic_model"]
            model["initial_continental_crust_cell_count"] = (
                int(model["initial_continental_crust_cell_count"]) + 1
            )

        self.assert_tamper_fails(tamper, MOTION_FAILURE)

    def test_missing_motion_summary_metric_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            del world["summary"]["plate_motion_transition_count"]

        self.assert_tamper_fails(tamper, MOTION_FAILURE)


class PlateMotionHistoryTest(_TamperCase, TestCase):
    """The ``plate_motion_history`` steps and their crust overlap ledgers."""

    def test_non_list_motion_history_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["plate_motion_history"] = {}

        self.assert_tamper_fails(tamper, MOTION_FAILURE)

    def test_initial_crust_type_column_length_mismatch_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["plate_motion_history"][0]["crust_type_by_cell"] = []

        self.assert_tamper_fails(tamper, MOTION_FAILURE)

    def test_incomplete_motion_step_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            del world["plate_motion_history"][0]["plates"]

        self.assert_tamper_fails(tamper, MOTION_FAILURE)

    def test_non_numeric_motion_step_field_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["plate_motion_history"][0]["cell_count"] = "many"

        self.assert_tamper_fails(tamper, MOTION_FAILURE)

    def test_unexpected_motion_stage_label_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            world["plate_motion_history"][0]["stage"] = "plate_motion_iteration"

        self.assert_tamper_fails(tamper, MOTION_FAILURE)

    def test_missing_initial_overlap_ledger_column_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            del world["plate_motion_history"][0]["crust_overlap_ledger"][
                "remapped_crust_age_ma_by_cell"
            ]

        self.assert_tamper_fails(tamper, MOTION_FAILURE)

    def test_missing_transition_overlap_ledger_column_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            del world["plate_motion_history"][1]["crust_overlap_ledger"][
                "remapped_crust_type_by_cell"
            ]

        self.assert_tamper_fails(tamper, MOTION_FAILURE)


class MotionHistoryCrustAgeTest(_TamperCase, TestCase):
    """Crust ages replayed through the motion history stay inside the budget."""

    def test_initial_ledger_age_beyond_geological_age_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            ledger = world["plate_motion_history"][0]["crust_overlap_ledger"]
            ledger["remapped_crust_age_ma_by_cell"][0] = 1.0e9

        self.assert_tamper_fails(tamper, CRUST_AGE_FAILURE)

    def test_replayed_transition_age_beyond_geological_age_is_reported(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            step = world["plate_motion_history"][1]
            step["crust_age_change_ma_by_cell"][0] = (
                float(step["crust_age_change_ma_by_cell"][0]) + 1.0e9
            )

        self.assert_tamper_fails(tamper, CRUST_AGE_FAILURE)
