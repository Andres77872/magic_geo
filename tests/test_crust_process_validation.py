from __future__ import annotations

from unittest import TestCase

from magic_geo.crust_process_validation import (
    CRUST_PROCESS_REASON_ORDER,
    replay_ordered_crust_process,
)


def _single_continental_collision(timestep_scale: float) -> dict[str, object]:
    return replay_ordered_crust_process(
        areas_km2=[1.0],
        remapped_crust_type_by_cell=[1],
        remapped_lithology_by_cell=[2],
        remapped_crust_age_ma_by_cell=[100.0],
        remapped_crust_thickness_km_by_cell=[35.0],
        remapped_crust_density_by_cell=[2.72],
        previous_plate_ids=[0],
        current_plate_ids=[1],
        boundary_convergent_by_cell=[0.2],
        boundary_divergent_by_cell=[0.0],
        timestep_scale=timestep_scale,
        reference_oceanic_crust_aging_ma_per_reference_step=5.0,
        internal_heat=1.0,
        geological_age_ga=4.5,
    )


class CrustProcessReplayTests(TestCase):
    def test_divergent_rifting_cannot_make_an_uncovered_row_negative(self) -> None:
        replay = replay_ordered_crust_process(
            areas_km2=[1.0],
            remapped_crust_type_by_cell=[1],
            remapped_lithology_by_cell=[2],
            remapped_crust_age_ma_by_cell=[0.0],
            remapped_crust_thickness_km_by_cell=[0.0],
            remapped_crust_density_by_cell=[2.7],
            previous_plate_ids=[0],
            current_plate_ids=[1],
            boundary_convergent_by_cell=[0.0],
            boundary_divergent_by_cell=[0.5],
            timestep_scale=1.0,
            reference_oceanic_crust_aging_ma_per_reference_step=5.0,
            internal_heat=1.0,
            geological_age_ga=4.5,
        )
        reasons = {reason["reason"]: reason for reason in replay["reasons"]}

        self.assertEqual(replay["crust_thickness_km_by_cell"], [16.0])
        self.assertGreater(replay["crust_density_by_cell"][0], 2.7)
        self.assertEqual(
            reasons["divergent_continental_rifting"]["net_delta"][
                "crust_volume_km3"
            ],
            0.0,
        )
        self.assertEqual(
            reasons["thickness_bound_enforcement"]["net_delta"][
                "crust_volume_km3"
            ],
            16.0,
        )

    def test_transitional_basalt_and_sandstone_preserve_distinct_provenance(
        self,
    ) -> None:
        replay = replay_ordered_crust_process(
            areas_km2=[1.0, 1.0],
            remapped_crust_type_by_cell=[2, 2],
            remapped_lithology_by_cell=[0, 3],
            remapped_crust_age_ma_by_cell=[400.0, 400.0],
            remapped_crust_thickness_km_by_cell=[8.0, 8.0],
            remapped_crust_density_by_cell=[3.0, 3.0],
            previous_plate_ids=[0, 0],
            current_plate_ids=[0, 0],
            boundary_convergent_by_cell=[0.0, 0.0],
            boundary_divergent_by_cell=[0.0, 0.0],
            timestep_scale=1.0,
            reference_oceanic_crust_aging_ma_per_reference_step=5.0,
            internal_heat=1.0,
            geological_age_ga=4.5,
        )

        self.assertEqual(replay["crust_age_ma_by_cell"], [320.0, 400.0])
        self.assertEqual(replay["crust_thickness_km_by_cell"], [8.0, 16.0])
        reasons = {record["reason"]: record for record in replay["reasons"]}
        self.assertEqual(
            reasons["quiet_oceanic_aging"]["triggered_cell_count"],
            1,
        )
        self.assertEqual(
            reasons["age_bound_enforcement"]["triggered_cell_count"],
            1,
        )
        self.assertEqual(
            reasons["thickness_bound_enforcement"]["triggered_cell_count"],
            1,
        )

    def test_exact_reference_step_splits_collision_and_crossing_impulse(self) -> None:
        replay = _single_continental_collision(1.0)
        reasons = {reason["reason"]: reason for reason in replay["reasons"]}

        self.assertAlmostEqual(replay["crust_thickness_km_by_cell"][0], 35.22)
        self.assertAlmostEqual(replay["crust_density_by_cell"][0], 2.7188)
        self.assertEqual(replay["crust_type_by_cell"], [8])
        self.assertEqual(replay["lithology_by_cell"], [6])
        self.assertAlmostEqual(
            reasons["continental_collision_orogeny"]["net_delta"][
                "crust_volume_km3"
            ],
            0.144,
        )
        self.assertAlmostEqual(
            reasons["plate_crossing_accretion_proxy"]["net_delta"][
                "crust_volume_km3"
            ],
            0.076,
        )

    def test_non_reference_step_scales_background_but_not_crossing_impulse(
        self,
    ) -> None:
        replay = _single_continental_collision(0.5)
        reasons = {reason["reason"]: reason for reason in replay["reasons"]}

        self.assertAlmostEqual(replay["crust_thickness_km_by_cell"][0], 35.148)
        self.assertAlmostEqual(
            reasons["continental_collision_orogeny"]["net_delta"][
                "crust_volume_km3"
            ],
            0.072,
        )
        self.assertAlmostEqual(
            reasons["plate_crossing_accretion_proxy"]["net_delta"][
                "crust_volume_km3"
            ],
            0.076,
        )

    def test_thresholds_bounds_and_reason_order_are_replayed(self) -> None:
        replay = replay_ordered_crust_process(
            areas_km2=[2.0] * 7,
            remapped_crust_type_by_cell=[0, 0, 1, 0, 1, 0, 1],
            remapped_lithology_by_cell=[0, 0, 2, 0, 2, 0, 2],
            remapped_crust_age_ma_by_cell=[
                100.0,
                100.0,
                100.0,
                100.0,
                100.0,
                500.0,
                100.0,
            ],
            remapped_crust_thickness_km_by_cell=[
                7.0,
                7.0,
                35.0,
                7.0,
                35.0,
                3.0,
                35.0,
            ],
            remapped_crust_density_by_cell=[
                3.0,
                3.0,
                2.72,
                3.0,
                2.72,
                3.2,
                2.72,
            ],
            previous_plate_ids=[0] * 7,
            current_plate_ids=[0, 1, 1, 0, 0, 0, 1],
            boundary_convergent_by_cell=[
                0.099,
                0.0,
                0.18,
                0.26,
                0.28,
                0.0,
                0.179,
            ],
            boundary_divergent_by_cell=[
                0.099,
                0.28,
                0.24,
                0.0,
                0.0,
                0.0,
                0.179,
            ],
            timestep_scale=1.0,
            reference_oceanic_crust_aging_ma_per_reference_step=5.0,
            internal_heat=1.0,
            geological_age_ga=4.5,
        )
        reasons = replay["reasons"]

        self.assertEqual(
            [reason["reason"] for reason in reasons],
            list(CRUST_PROCESS_REASON_ORDER),
        )
        self.assertEqual(replay["crust_type_by_cell"], [0, 0, 8, 3, 5, 0, 2])
        self.assertEqual(replay["lithology_by_cell"], [0, 0, 6, 5, 6, 0, 3])
        self.assertEqual(replay["crust_age_ma_by_cell"][5], 320.0)
        self.assertEqual(replay["crust_thickness_km_by_cell"][5], 4.5)
        self.assertEqual(replay["crust_density_by_cell"][5], 3.08)

        by_name = {reason["reason"]: reason for reason in reasons}
        self.assertEqual(
            by_name["oceanic_ridge_creation_relaxation"][
                "triggered_cell_count"
            ],
            1,
        )
        self.assertEqual(
            by_name["oceanic_ridge_creation_relaxation"][
                "extensive_state_changed_cell_count"
            ],
            0,
        )
        for bound_reason in (
            "age_bound_enforcement",
            "thickness_bound_enforcement",
            "density_bound_enforcement",
        ):
            self.assertEqual(by_name[bound_reason]["triggered_cell_count"], 1)
            self.assertEqual(
                by_name[bound_reason]["extensive_state_changed_cell_count"],
                1,
            )

        for field, residual in replay["numerical_closure_residual"].items():
            self.assertLess(abs(residual), 1.0e-10, field)

    def test_mismatched_cell_arrays_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "input lengths differ"):
            replay_ordered_crust_process(
                areas_km2=[1.0],
                remapped_crust_type_by_cell=[0, 0],
                remapped_lithology_by_cell=[0],
                remapped_crust_age_ma_by_cell=[1.0],
                remapped_crust_thickness_km_by_cell=[7.0],
                remapped_crust_density_by_cell=[3.0],
                previous_plate_ids=[0],
                current_plate_ids=[0],
                boundary_convergent_by_cell=[0.0],
                boundary_divergent_by_cell=[0.0],
                timestep_scale=1.0,
                reference_oceanic_crust_aging_ma_per_reference_step=5.0,
                internal_heat=1.0,
                geological_age_ga=4.5,
            )
