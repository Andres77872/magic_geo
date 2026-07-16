from __future__ import annotations

import csv
import math
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from magic_geo.config import WorldConfig, config_to_native, load_config
from magic_geo.geo_validation import GEO_MODEL_LIMITATIONS
from magic_geo.io import write_cells_csv
from magic_geo.native import generate_geo_world
from magic_geo.oceanic_age_depth_validation import (
    ANALYTICAL_CHECKPOINTS_M,
    KINEMATIC_EQUILIBRIUM_LITERAL_VALUES,
    MAXIMUM_CELL_COUNT,
    MAXIMUM_HISTORY_STEP_COUNT,
    MODEL_LITERAL_VALUES,
    is_oceanic_like_crust_state,
    oceanic_relative_basement_subsidence_m,
    validate_oceanic_age_depth,
)


def _config(
    *,
    full_gap: bool = False,
    active_surface: bool = False,
) -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["run"]["seed"] = 20260711
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    data["erosion"]["iterations"] = 1 if full_gap else 2
    if full_gap:
        data["tectonics"]["min_angular_speed"] = 18.0
        data["tectonics"]["max_angular_speed"] = 18.0
        data["tectonics"]["plate_motion_scale_deg_per_step"] = 10.0
    if active_surface:
        data["run"]["seed"] = 424242
        data["mesh"]["cell_count"] = 512
        data["tectonics"]["plate_count"] = 10
        data["tectonics"]["plate_motion_scale_deg_per_step"] = 4.0
        data["planet"]["internal_heat"] = 1.8
        data["planet"]["geological_age_ga"] = 1.0
        data["erosion"]["iterations"] = 6
        data["erosion"]["tectonic_uplift_scale"] = 1.5
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    data["output"]["float_precision"] = 8
    return WorldConfig.model_validate(data)


class OceanicAgeDepthFormulaTests(TestCase):
    def test_fixed_ages_cover_cutoff_ulps_and_old_branch(self) -> None:
        ages = [age for age, _ in ANALYTICAL_CHECKPOINTS_M]
        self.assertEqual(
            ages,
            [
                0.0,
                20.0,
                math.nextafter(70.0, -math.inf),
                70.0,
                math.nextafter(70.0, math.inf),
                100.0,
                320.0,
            ],
        )
        observed = [
            oceanic_relative_basement_subsidence_m(age) for age in ages
        ]
        self.assertEqual(
            observed,
            [expected for _, expected in ANALYTICAL_CHECKPOINTS_M],
        )
        self.assertEqual(observed, sorted(observed))
        self.assertEqual(observed[0], 0.0)
        self.assertGreater(observed[4], observed[3])

    def test_branches_are_c0_continuous_but_not_claimed_c1(self) -> None:
        cutoff = 350.0 * math.sqrt(70.0)
        old_at_cutoff = cutoff + 3200.0 * (
            math.exp(-70.0 / 62.8) - math.exp(-70.0 / 62.8)
        )
        self.assertEqual(cutoff, old_at_cutoff)
        self.assertTrue(MODEL_LITERAL_VALUES["continuity_at_transition_resolved"])
        self.assertFalse(
            MODEL_LITERAL_VALUES["derivative_continuity_at_transition_resolved"]
        )
        self.assertTrue(
            any(
                "thermal-subsidence target curve" in limitation
                and "does not separately track realized thermal relief"
                in limitation
                for limitation in GEO_MODEL_LIMITATIONS
            )
        )

    def test_oceanic_like_predicate_and_non_oceanic_zero_semantics(self) -> None:
        self.assertTrue(is_oceanic_like_crust_state(0, 0, 100.0, 7.0, 3.0))
        self.assertTrue(is_oceanic_like_crust_state(2, 0, 20.0, 8.0, 2.9))
        self.assertFalse(is_oceanic_like_crust_state(2, 1, 20.0, 8.0, 2.9))
        self.assertTrue(is_oceanic_like_crust_state(3, 5, 320.0, 18.0, 2.84))
        self.assertFalse(
            is_oceanic_like_crust_state(
                3, 5, math.nextafter(320.0, math.inf), 18.0, 2.84
            )
        )
        self.assertFalse(is_oceanic_like_crust_state(1, 0, 100.0, 35.0, 2.7))
        for invalid_type, invalid_lithology in ((True, 0), (9, 0), (0, True), (0, 7)):
            with self.assertRaises(ValueError):
                is_oceanic_like_crust_state(
                    invalid_type, invalid_lithology, 20.0, 7.0, 3.0
                )


class OceanicAgeDepthGeneratedValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(config_to_native(_config()))
        cls.full_gap_world = generate_geo_world(
            config_to_native(_config(full_gap=True))
        )
        cls.active_surface_world = generate_geo_world(
            config_to_native(_config(active_surface=True))
        )

    def assert_rejected(self, world: object) -> None:
        result = validate_oceanic_age_depth(world)
        self.assertFalse(result["passed"])
        self.assertTrue(result["failures"])

    def test_real_generated_world_replays_from_independent_crust_roots(self) -> None:
        result = validate_oceanic_age_depth(self.world)
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(self.world["oceanic_age_depth_model"], MODEL_LITERAL_VALUES)
        for step in self.world["plate_motion_history"]:
            self.assertNotIn("thermal_target_difference_tendency_m", step)
        metrics = result["metrics"]
        cell_count = len(self.world["cells"])
        history_count = len(self.world["plate_motion_history"])
        self.assertTrue(metrics["independent_crust_transport_root_replay_passed"])
        self.assertEqual(metrics["analytical_checkpoint_count"], 7)
        self.assertEqual(metrics["cell_count"], cell_count)
        self.assertEqual(metrics["history_step_count"], history_count)
        self.assertEqual(
            metrics["isostatic_checkpoint_value_count"],
            2 * cell_count * history_count,
        )
        self.assertEqual(
            metrics["thermal_checkpoint_value_count"],
            2 * cell_count * history_count,
        )
        self.assertEqual(
            metrics["tectonic_application_value_count"],
            cell_count * history_count,
        )
        self.assertGreater(metrics["non_oceanic_checkpoint_value_count"], 0)
        final_step = self.world["plate_motion_history"][-1]
        self.assertTrue(
            any(
                crust_type not in (0, 2, 3) and target == 0.0
                for crust_type, target in zip(
                    final_step["crust_type_by_cell"],
                    final_step[
                        "post_process_local_thermal_subsidence_target_m"
                    ],
                    strict=True,
                )
            )
        )
        self.assertTrue(metrics["initial_thermal_checkpoint_replayed"])
        self.assertTrue(metrics["initial_isostatic_targets_replayed"])
        self.assertTrue(metrics["final_thermal_target_replayed"])
        self.assertTrue(metrics["kinematic_equilibrium_metadata_replayed"])
        self.assertTrue(metrics["isostatic_target_application_replayed"])
        self.assertTrue(metrics["dynamic_relief_clamp_replayed"])
        self.assertTrue(
            metrics["tectonic_elevation_change_composition_replayed"]
        )
        self.assertTrue(
            metrics["authoritative_for_relative_thermal_subsidence_target_curve"]
        )
        for field in (
            "authoritative_for_realized_thermal_relief_component",
            "realized_thermal_relief_state_tracked",
            "thermal_relaxation_timescale_calibrated",
            "unapplied_thermal_tendency_residual_carried_forward",
            "absolute_basement_depth_calibrated",
            "physical_crust_creation_age_provenance",
            "ridge_age_distance_consistency",
            "thermal_structure_represented",
            "heat_flow_represented",
            "dynamic_topography_represented",
            "flexure_represented",
            "physical_dynamics_represented",
        ):
            self.assertFalse(metrics[field], field)
        for field in (
            "unapplied_thermal_equilibrium_residual_zero_by_construction",
            "thermal_contribution_outside_bounded_dynamic_relief_clamp_resolved",
            "thermal_contribution_to_tectonic_elevation_change_replayed",
            "thermal_equilibrium_change_application_replayed",
        ):
            self.assertTrue(metrics[field], field)

    def test_fully_uncovered_transport_rows_are_valid_zero_volume_roots(self) -> None:
        moving = self.full_gap_world["plate_motion_history"][1]
        ledger = moving["crust_overlap_ledger"]
        full_gap_ids = [
            cell_id
            for cell_id, (age, thickness) in enumerate(
                zip(
                    ledger["remapped_crust_age_ma_by_cell"],
                    ledger["remapped_crust_thickness_km_by_cell"],
                    strict=True,
                )
            )
            if age == 0.0 and thickness == 0.0
        ]
        self.assertTrue(full_gap_ids, "fixture must contain fully uncovered rows")
        result = validate_oceanic_age_depth(self.full_gap_world)
        self.assertTrue(result["passed"], result["failures"])

    def test_active_surface_rounded_target_differences_telescope(self) -> None:
        history = self.active_surface_world["plate_motion_history"]
        cell_count = len(self.active_surface_world["cells"])
        self.assertTrue(
            any(
                targets[0] == targets[-1]
                and any(target != targets[0] for target in targets[1:-1])
                for targets in (
                    [
                        step["post_process_local_thermal_subsidence_target_m"][
                            cell_id
                        ]
                        for step in history
                    ]
                    for cell_id in range(cell_count)
                )
            ),
            "fixture must exercise a thermal target that leaves and returns",
        )
        result = validate_oceanic_age_depth(self.active_surface_world)
        self.assertTrue(result["passed"], result["failures"])

    def test_full_equilibrium_change_survives_dynamic_relief_clamp(self) -> None:
        survivors: list[tuple[float, float, float]] = []
        for step in self.world["plate_motion_history"][1:]:
            for isostatic, thermal, bounded, total in zip(
                step["isostatic_equilibrium_change_m"],
                step["thermal_equilibrium_change_m"],
                step["bounded_dynamic_relief_change_m"],
                step["tectonic_elevation_change_m_by_cell"],
                strict=True,
            ):
                equilibrium = isostatic + thermal
                self.assertGreaterEqual(bounded, -180.0)
                self.assertLessEqual(bounded, 220.0)
                self.assertAlmostEqual(
                    total,
                    equilibrium + bounded,
                    delta=4.0 * math.ulp(max(abs(total), abs(equilibrium + bounded))),
                )
                if abs(equilibrium) > 220.0 and abs(total) > 220.0:
                    survivors.append((equilibrium, bounded, total))

        self.assertTrue(survivors)
        result = validate_oceanic_age_depth(self.world)
        self.assertTrue(result["passed"], result["failures"])
        metrics = result["metrics"]
        self.assertGreater(
            metrics["equilibrium_change_exceeds_dynamic_clamp_cell_step_count"],
            0,
        )
        self.assertGreater(
            metrics["tectonic_change_exceeds_dynamic_clamp_cell_step_count"],
            0,
        )
        self.assertGreater(metrics["maximum_absolute_equilibrium_change_m"], 220.0)
        self.assertGreater(
            metrics["maximum_absolute_tectonic_elevation_change_m"], 220.0
        )

    def test_public_validator_cannot_bypass_independent_transport_replay(self) -> None:
        altered = deepcopy(self.world)
        altered["plate_motion_history"][1]["crust_overlap_ledger"][
            "overlap_area_km2"
        ][0] *= 1.01
        self.assert_rejected(altered)
        with self.assertRaises(TypeError):
            validate_oceanic_age_depth(  # type: ignore[call-arg]
                altered,
                _validated_crust_transport_replay={"passed": True},
            )

    def test_final_target_is_available_in_the_cell_csv_export(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cells.csv"
            write_cells_csv(path, self.world)
            with path.open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
        self.assertIn("thermal_subsidence_target_m", row)
        self.assertEqual(
            float(row["thermal_subsidence_target_m"]),
            self.world["cells"][0]["thermal_subsidence_target_m"],
        )

    def test_metadata_and_authority_claim_tampering_is_rejected(self) -> None:
        for field, value in (
            ("model", "spoofed"),
            ("old_age_exponential_scale_m", 3200.000001),
            ("authoritative_for_realized_thermal_relief_component", True),
            ("thermal_relaxation_timescale_calibrated", True),
            ("heat_flow_represented", True),
        ):
            with self.subTest(field=field):
                altered = deepcopy(self.world)
                altered["oceanic_age_depth_model"][field] = value
                self.assert_rejected(altered)

        altered = deepcopy(self.world)
        altered["oceanic_age_depth_model"]["unexpected_claim"] = True
        self.assert_rejected(altered)

        for field, expected in KINEMATIC_EQUILIBRIUM_LITERAL_VALUES.items():
            with self.subTest(kinematic_field=field):
                altered = deepcopy(self.world)
                if type(expected) is bool:
                    altered["plate_kinematic_model"][field] = not expected
                elif type(expected) is float:
                    altered["plate_kinematic_model"][field] = expected + 1.0e-6
                elif isinstance(expected, list):
                    altered["plate_kinematic_model"][field] = list(reversed(expected))
                else:
                    altered["plate_kinematic_model"][field] = f"spoofed_{expected}"
                self.assert_rejected(altered)

        for field in (
            "maturation_timestep_scale",
            "tectonic_activity_index",
            "tectonic_uplift_scale_input",
        ):
            with self.subTest(kinematic_operand=field):
                altered = deepcopy(self.world)
                altered["plate_kinematic_model"][field] += 1.0e-6
                self.assert_rejected(altered)

    def test_round_trip_thermal_arrays_and_final_target_tampering_is_rejected(
        self,
    ) -> None:
        mutations = (
            lambda world: world["plate_motion_history"][0][
                "previous_local_thermal_subsidence_target_m"
            ].__setitem__(0, -1.0),
            lambda world: world["plate_motion_history"][-1][
                "post_process_local_thermal_subsidence_target_m"
            ].__setitem__(0, -1.0),
            lambda world: world["cells"][0].__setitem__(
                "thermal_subsidence_target_m",
                world["cells"][0]["thermal_subsidence_target_m"] + 1.0e-6,
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                altered = deepcopy(self.world)
                mutate(altered)
                self.assert_rejected(altered)

    def test_canonical_thermal_equilibrium_change_tampering_is_rejected(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["plate_motion_history"][1]["thermal_equilibrium_change_m"][
            0
        ] += 1.0e-8
        self.assert_rejected(altered)

    def test_every_equilibrium_application_array_tampering_is_rejected(
        self,
    ) -> None:
        fields = (
            "boundary_convergent_by_cell",
            "boundary_divergent_by_cell",
            "boundary_transform_by_cell",
            "previous_local_isostatic_equilibrium_m",
            "post_process_local_isostatic_equilibrium_m",
            "isostatic_equilibrium_change_m",
            "previous_local_thermal_subsidence_target_m",
            "post_process_local_thermal_subsidence_target_m",
            "thermal_equilibrium_change_m",
            "unbounded_dynamic_relief_change_m",
            "bounded_dynamic_relief_change_m",
            "tectonic_elevation_change_m_by_cell",
        )
        for field in fields:
            with self.subTest(field=field):
                altered = deepcopy(self.world)
                altered["plate_motion_history"][1][field][0] += 1.0e-6
                self.assert_rejected(altered)

    def test_colluding_thermal_target_change_and_total_cannot_spoof_formula(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        step = altered["plate_motion_history"][-1]
        cell_id = next(
            index
            for index, value in enumerate(
                step["post_process_local_thermal_subsidence_target_m"]
            )
            if value < 0.0
        )
        previous = step["previous_local_thermal_subsidence_target_m"][cell_id]
        old_change = step["thermal_equilibrium_change_m"][cell_id]
        new_change = 0.0 - previous
        step["post_process_local_thermal_subsidence_target_m"][cell_id] = 0.0
        step["thermal_equilibrium_change_m"][cell_id] = new_change
        step["tectonic_elevation_change_m_by_cell"][cell_id] += (
            new_change - old_change
        )
        altered["cells"][cell_id]["thermal_subsidence_target_m"] = 0.0
        self.assert_rejected(altered)

    def test_colluding_isostatic_target_change_and_total_cannot_spoof_formula(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        step = altered["plate_motion_history"][-1]
        cell_id = 0
        step["post_process_local_isostatic_equilibrium_m"][cell_id] += 100.0
        step["isostatic_equilibrium_change_m"][cell_id] += 100.0
        step["tectonic_elevation_change_m_by_cell"][cell_id] += 100.0
        self.assert_rejected(altered)

    def test_colluding_dynamic_relief_clamp_and_total_cannot_spoof_formula(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        step = altered["plate_motion_history"][1]
        cell_id = 0
        step["unbounded_dynamic_relief_change_m"][cell_id] += 1.0
        step["bounded_dynamic_relief_change_m"][cell_id] += 1.0
        step["tectonic_elevation_change_m_by_cell"][cell_id] += 1.0
        self.assert_rejected(altered)

    def test_predicate_root_tampering_is_rejected(self) -> None:
        altered = deepcopy(self.world)
        step = altered["plate_motion_history"][-1]
        cell_id = next(
            index
            for index, value in enumerate(
                step["post_process_local_thermal_subsidence_target_m"]
            )
            if value < 0.0
        )
        step["crust_type_by_cell"][cell_id] = 1
        self.assert_rejected(altered)

    def test_nonfinite_cardinality_and_resource_overflow_are_rejected(self) -> None:
        altered = deepcopy(self.world)
        altered["plate_motion_history"][0][
            "post_process_local_thermal_subsidence_target_m"
        ][0] = float("nan")
        self.assert_rejected(altered)

        altered = deepcopy(self.world)
        altered["plate_motion_history"][0]["crust_overlap_ledger"][
            "remapped_crust_age_ma_by_cell"
        ][0] = float("nan")
        self.assert_rejected(altered)

        altered = deepcopy(self.world)
        altered["plate_motion_history"][0][
            "post_process_local_thermal_subsidence_target_m"
        ].pop()
        self.assert_rejected(altered)

        for field in (
            "previous_local_isostatic_equilibrium_m",
            "thermal_equilibrium_change_m",
            "boundary_transform_by_cell",
            "unbounded_dynamic_relief_change_m",
            "bounded_dynamic_relief_change_m",
            "tectonic_elevation_change_m_by_cell",
        ):
            with self.subTest(short_array=field):
                altered = deepcopy(self.world)
                altered["plate_motion_history"][0][field].pop()
                self.assert_rejected(altered)

        oversized_cells = dict(self.world)
        oversized_cells["cells"] = [self.world["cells"][0]] * (
            MAXIMUM_CELL_COUNT + 1
        )
        self.assert_rejected(oversized_cells)

        oversized_history = dict(self.world)
        oversized_history["plate_motion_history"] = [
            self.world["plate_motion_history"][0]
        ] * (MAXIMUM_HISTORY_STEP_COUNT + 1)
        self.assert_rejected(oversized_history)
