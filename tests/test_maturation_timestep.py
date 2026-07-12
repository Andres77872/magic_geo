from __future__ import annotations

import math
from pathlib import Path
from unittest import TestCase

from magic_geo.api import generate_geo_world as generate_enriched_geo_world
from magic_geo.config import WorldConfig, config_to_native, load_config
from magic_geo.native import generate_geo_world as generate_native_geo_world


REFINEMENTS = ((5.0, 2), (2.5, 4), (1.25, 8))
NOMINAL_DURATION_MA = 10.0
REFERENCE_TIMESTEP_MA = 5.0


def _maturation_config(
    timestep_ma: float,
    iterations: int,
    *,
    stationary_plates: bool,
) -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["run"]["seed"] = 20260711
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    if stationary_plates:
        # Keep nonzero kinematic boundary forcing while freezing domain motion;
        # this exercises crust aging/relaxation with an exact identity overlap plan.
        data["tectonics"]["plate_motion_scale_deg_per_step"] = 0.0
    data["erosion"]["iterations"] = iterations
    data["erosion"]["maturation_timestep_ma"] = timestep_ma
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    data["output"]["float_precision"] = 8
    return WorldConfig.model_validate(data)


def _generate(
    timestep_ma: float,
    iterations: int,
    *,
    stationary_plates: bool,
) -> dict:
    config = _maturation_config(
        timestep_ma,
        iterations,
        stationary_plates=stationary_plates,
    )
    return generate_native_geo_world(config_to_native(config))


def _area_weighted_l2(left: dict, right: dict, field: str) -> float:
    left_cells = left["cells"]
    right_cells = right["cells"]
    if len(left_cells) != len(right_cells):
        raise AssertionError("refinement worlds do not share a mesh")

    weighted_squared_error = 0.0
    total_area_km2 = 0.0
    for left_cell, right_cell in zip(left_cells, right_cells, strict=True):
        if left_cell["id"] != right_cell["id"]:
            raise AssertionError("refinement worlds do not share cell ordering")
        if left_cell["area_km2"] != right_cell["area_km2"]:
            raise AssertionError("refinement worlds do not share cell areas")
        area_km2 = float(left_cell["area_km2"])
        difference = float(left_cell[field]) - float(right_cell[field])
        weighted_squared_error += area_km2 * difference * difference
        total_area_km2 += area_km2
    return math.sqrt(weighted_squared_error / total_area_km2)


class MaturationTimestepTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stationary_worlds = [
            _generate(
                timestep_ma,
                iterations,
                stationary_plates=True,
            )
            for timestep_ma, iterations in REFINEMENTS
        ]
        cls.enriched_stationary_worlds = [
            generate_enriched_geo_world(
                _maturation_config(
                    timestep_ma,
                    iterations,
                    stationary_plates=True,
                )
            )
            for timestep_ma, iterations in REFINEMENTS
        ]

    def test_equal_duration_refinement_clock_is_exact_and_nominal(self) -> None:
        for (timestep_ma, iterations), world in zip(
            REFINEMENTS,
            self.stationary_worlds,
            strict=True,
        ):
            with self.subTest(timestep_ma=timestep_ma, iterations=iterations):
                clock = world["simulation_clock"]
                self.assertEqual(
                    clock["clock_type"],
                    "coupled_geodynamic_stage_clock_v12",
                )
                self.assertEqual(clock["nominal_time_unit"], "Ma")
                self.assertEqual(clock["nominal_timestep_ma"], timestep_ma)
                self.assertEqual(
                    clock["reference_timestep_ma"],
                    REFERENCE_TIMESTEP_MA,
                )
                self.assertEqual(
                    clock["maturation_timestep_scale"],
                    timestep_ma / REFERENCE_TIMESTEP_MA,
                )
                self.assertEqual(
                    clock["nominal_timed_transition_count"],
                    iterations,
                )
                self.assertEqual(
                    clock["initial_nominal_elapsed_time_ma"],
                    0.0,
                )
                self.assertEqual(
                    clock["current_nominal_elapsed_time_ma"],
                    NOMINAL_DURATION_MA,
                )
                self.assertEqual(
                    clock["final_nominal_elapsed_time_ma"],
                    NOMINAL_DURATION_MA,
                )
                self.assertFalse(clock["physical_time_resolved"])
                self.assertFalse(clock["nominal_time_calibrated"])
                self.assertFalse(clock["time_step_convergence_demonstrated"])

                feedback = world["earth_system_feedback_history"]
                self.assertEqual(len(feedback), iterations + 2)
                self.assertEqual(
                    (
                        feedback[0]["nominal_interval_start_ma"],
                        feedback[0]["nominal_interval_end_ma"],
                        feedback[0]["nominal_interval_duration_ma"],
                    ),
                    (0.0, 0.0, 0.0),
                )
                self.assertFalse(feedback[0]["advances_nominal_time"])
                for iteration, step in enumerate(
                    feedback[1:-1],
                    start=1,
                ):
                    self.assertEqual(step["erosion_iteration"], iteration)
                    self.assertEqual(
                        step["nominal_interval_start_ma"],
                        (iteration - 1) * timestep_ma,
                    )
                    self.assertEqual(
                        step["nominal_interval_end_ma"],
                        iteration * timestep_ma,
                    )
                    self.assertEqual(
                        step["nominal_interval_duration_ma"],
                        timestep_ma,
                    )
                    self.assertEqual(
                        step["nominal_elapsed_time_ma"],
                        iteration * timestep_ma,
                    )
                    self.assertTrue(step["advances_nominal_time"])
                    self.assertFalse(step["physical_time_resolved"])
                    self.assertFalse(step["nominal_time_calibrated"])

                cryosphere = feedback[-1]
                self.assertEqual(cryosphere["stage"], "cryosphere_coupling")
                self.assertEqual(
                    (
                        cryosphere["nominal_interval_start_ma"],
                        cryosphere["nominal_interval_end_ma"],
                        cryosphere["nominal_interval_duration_ma"],
                        cryosphere["nominal_elapsed_time_ma"],
                    ),
                    (
                        NOMINAL_DURATION_MA,
                        NOMINAL_DURATION_MA,
                        0.0,
                        NOMINAL_DURATION_MA,
                    ),
                )
                self.assertFalse(cryosphere["advances_nominal_time"])
                self.assertFalse(cryosphere["physical_time_resolved"])

    def test_stationary_plate_refinement_errors_decrease(self) -> None:
        coarse, medium, fine = self.stationary_worlds
        for world in self.stationary_worlds:
            self.assertTrue(
                all(
                    plate["cumulative_rotation_deg"] == 0.0
                    for plate in world["plates"]
                )
            )

        convergent_fields = (
            "elevation_m",
            "sediment_thickness_m",
            "sediment_production_m",
            "crust_thickness_km",
        )
        for field in convergent_fields:
            coarse_to_medium = _area_weighted_l2(coarse, medium, field)
            medium_to_fine = _area_weighted_l2(medium, fine, field)
            ratio = medium_to_fine / coarse_to_medium
            observed_order = math.log2(coarse_to_medium / medium_to_fine)
            print(
                f"maturation refinement {field}: "
                f"coarse-medium={coarse_to_medium:.12g}, "
                f"medium-fine={medium_to_fine:.12g}, "
                f"ratio={ratio:.12g}, order={observed_order:.12g}"
            )
            self.assertTrue(math.isfinite(coarse_to_medium))
            self.assertTrue(math.isfinite(medium_to_fine))
            self.assertGreater(coarse_to_medium, 0.0)
            self.assertLess(
                medium_to_fine,
                coarse_to_medium,
                msg=(
                    f"{field} did not reduce its area-weighted L2 error "
                    "under timestep halving"
                ),
            )
            # The gate is a lower-order convergence claim: refinement must be
            # at least near first order. Faster decay is valid (the full
            # quasi-static equilibrium correction removes part of the former
            # first-order error) and must not be rejected by an upper bound.
            self.assertGreaterEqual(observed_order, 0.8)

        # Per-cell export is localized at discrete terminal receivers, so a
        # drainage-capture event can move a conserved volume between two cells
        # and make its cellwise L2 error non-monotone.  The global exported
        # volume remains the topology-independent refinement diagnostic.
        export_volumes = [
            float(world["sediment_inventory_model"]["terminal_export_volume_km3"])
            for world in self.stationary_worlds
        ]
        self.assertLess(
            abs(export_volumes[1] - export_volumes[2]),
            abs(export_volumes[0] - export_volumes[1]),
        )

        # With no domain motion, these reference-scaled relaxation/aging
        # operators compose to the same equal-duration state at all three
        # refinements (to the serialized precision).
        for world in self.stationary_worlds:
            self.assertGreater(
                sum(
                    step["rejuvenated_oceanic_cell_count"]
                    for step in world["plate_motion_history"]
                ),
                0,
            )
            self.assertGreater(
                sum(
                    step["subducted_oceanic_cell_count"]
                    for step in world["plate_motion_history"]
                ),
                0,
            )

        # Exponentially scaled age/density relaxations compose to the same
        # fixed-horizon state within a binary64 operation envelope. Round-trip
        # output intentionally retains the few-ULP difference from using more
        # substeps instead of hiding it through decimal output rounding.
        for field in ("crust_age_ma", "crust_density"):
            scale = max(
                abs(float(cell[field]))
                for world in self.stationary_worlds
                for cell in world["cells"]
            )
            binary64_bound = max(1.0e-15, 128.0 * math.ulp(scale))
            self.assertLessEqual(
                _area_weighted_l2(coarse, medium, field), binary64_bound
            )
            self.assertLessEqual(
                _area_weighted_l2(medium, fine, field), binary64_bound
            )

    def test_refinement_preserves_sediment_mass_closure(self) -> None:
        for world in self.stationary_worlds:
            inventory = world["sediment_inventory_model"]
            gross = float(inventory["gross_mobilization_volume_km3"])
            tolerance = max(1.0e-8, gross * 1.0e-10)
            cell_export_volume_km3 = math.fsum(
                float(cell["sediment_export_m"])
                * float(cell["area_km2"])
                / 1000.0
                for cell in world["cells"]
            )
            self.assertAlmostEqual(
                cell_export_volume_km3,
                float(inventory["terminal_export_volume_km3"]),
                delta=tolerance,
            )
            for key in (
                "gross_throughput_mass_balance_residual_km3",
                "source_partition_residual_km3",
                "inventory_mass_balance_residual_km3",
            ):
                self.assertLessEqual(abs(float(inventory[key])), tolerance)
            for family in (
                "hillslope_sediment_transport_history",
                "fluvial_sediment_routing_history",
                "glacial_sediment_transport_history",
            ):
                for stage in world[family]:
                    self.assertLessEqual(
                        abs(float(stage["mass_balance_residual_km3"])),
                        tolerance,
                    )

    def test_reference_erosion_signal_integrates_to_transition_source(self) -> None:
        for (timestep_ma, _iterations), world in zip(
            REFINEMENTS,
            self.stationary_worlds,
            strict=True,
        ):
            expected_source_volume_km3 = sum(
                float(cell["erosion_rate"])
                * (timestep_ma / REFERENCE_TIMESTEP_MA)
                * float(cell["area_km2"])
                / 1000.0
                for cell in world["cells"]
            )
            actual_source_volume_km3 = float(
                world["fluvial_sediment_routing_history"][-1][
                    "local_source_volume_km3"
                ]
            )
            self.assertAlmostEqual(
                expected_source_volume_km3,
                actual_source_volume_km3,
                delta=0.001,
            )
            self.assertEqual(
                world["simulation_clock"]["cell_erosion_rate_semantics"],
                "stream_power_response_per_reference_step_not_applied_transition_depth",
            )

    def test_enriched_geo_layers_use_reference_signal_and_linked_snapshots(
        self,
    ) -> None:
        for native, enriched in zip(
            self.stationary_worlds,
            self.enriched_stationary_worlds,
            strict=True,
        ):
            self.assertEqual(
                [cell["erosion_rate"] for cell in enriched["cells"]],
                [cell["erosion_rate"] for cell in native["cells"]],
            )
            for field in (
                "soil_erodibility_index",
                "soil_profile_development_index",
                "primary_productivity_index",
            ):
                values = [float(cell[field]) for cell in enriched["cells"]]
                self.assertTrue(all(math.isfinite(value) for value in values))
                self.assertTrue(all(0.0 <= value <= 1.0 for value in values))
            for cell in enriched["cells"]:
                if int(cell["soil_profile_id"]) < 0:
                    self.assertEqual(cell["soil_erodibility_index"], 0.0)
                    self.assertEqual(
                        cell["soil_profile_development_index"], 0.0
                    )

        for world in self.enriched_stationary_worlds:
            self.assertFalse(
                world["simulation_clock"]["time_step_convergence_demonstrated"]
            )
            soil_registry = next(
                record
                for record in world["geo_evolution_provenance"]["families"]
                if record["family"] == "soil_profile_histories"
            )
            self.assertTrue(soil_registry["nominal_time_coordinate_available"])
            self.assertEqual(
                soil_registry["nominal_time_linkage"],
                "contextual_native_stage_link_without_state_mutation",
            )
            for history in world["soil_profile_histories"]:
                for step in history["steps"]:
                    if step["nominal_interval_duration_ma"] == 0.0:
                        self.assertEqual(step["start_depth_m"], step["end_depth_m"])
                        self.assertEqual(step["soil_production_m"], 0.0)
                        self.assertEqual(step["erosion_loss_m"], 0.0)
                        self.assertEqual(step["pedogenic_flux_index"], 0.0)

    def test_nonzero_motion_has_equal_cumulative_rotation_and_clock_intervals(
        self,
    ) -> None:
        moving_worlds = [
            _generate(
                timestep_ma,
                iterations,
                stationary_plates=False,
            )
            for timestep_ma, iterations in REFINEMENTS
        ]
        finest_rotations = {
            plate["id"]: plate["cumulative_rotation_deg"]
            for plate in moving_worlds[-1]["plates"]
        }

        for (timestep_ma, iterations), world in zip(
            REFINEMENTS,
            moving_worlds,
            strict=True,
        ):
            with self.subTest(timestep_ma=timestep_ma, iterations=iterations):
                self.assertEqual(
                    world["simulation_clock"][
                        "final_nominal_elapsed_time_ma"
                    ],
                    NOMINAL_DURATION_MA,
                )
                kinematic_model = world["plate_kinematic_model"]
                self.assertEqual(
                    kinematic_model["nominal_timestep_ma"],
                    timestep_ma,
                )
                self.assertEqual(
                    kinematic_model["maturation_timestep_scale"],
                    timestep_ma / REFERENCE_TIMESTEP_MA,
                )
                self.assertEqual(
                    kinematic_model["effective_motion_scale_deg_per_step"],
                    kinematic_model[
                        "reference_motion_scale_deg_per_reference_step"
                    ]
                    * timestep_ma
                    / REFERENCE_TIMESTEP_MA,
                )
                self.assertFalse(kinematic_model["physical_time_resolved"])
                self.assertFalse(kinematic_model["nominal_time_calibrated"])
                self.assertFalse(
                    kinematic_model["time_step_convergence_demonstrated"]
                )
                self.assertTrue(
                    kinematic_model["mass_conserving_crust_transport"]
                )
                self.assertIn(
                    "conservative_first_order_crust_transport",
                    kinematic_model["model_limitation"],
                )
                history = world["plate_motion_history"]
                self.assertEqual(len(history), iterations + 1)
                self.assertEqual(
                    history[0]["nominal_interval_duration_ma"],
                    0.0,
                )
                self.assertFalse(history[0]["advances_nominal_time"])
                for iteration, step in enumerate(history[1:], start=1):
                    self.assertEqual(
                        (
                            step["nominal_interval_start_ma"],
                            step["nominal_interval_end_ma"],
                            step["nominal_interval_duration_ma"],
                        ),
                        (
                            (iteration - 1) * timestep_ma,
                            iteration * timestep_ma,
                            timestep_ma,
                        ),
                    )
                    self.assertFalse(step["physical_time_resolved"])

                for plate in world["plates"]:
                    expected_rotation = (
                        plate["angular_speed"]
                        * world["plate_kinematic_model"][
                            "reference_motion_scale_deg_per_reference_step"
                        ]
                        * NOMINAL_DURATION_MA
                        / REFERENCE_TIMESTEP_MA
                    )
                    self.assertAlmostEqual(
                        plate["cumulative_rotation_deg"],
                        expected_rotation,
                        delta=2e-7,
                    )
                    self.assertAlmostEqual(
                        plate["cumulative_rotation_deg"],
                        finest_rotations[plate["id"]],
                        delta=2e-7,
                    )


if __name__ == "__main__":
    import unittest

    unittest.main()
