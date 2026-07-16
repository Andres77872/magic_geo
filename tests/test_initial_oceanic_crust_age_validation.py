from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.config import WorldConfig, config_to_native, load_config
from magic_geo.initial_oceanic_crust_age_validation import (
    CONFIGURED_MAXIMUM_AGE_MA,
    MODEL_LITERAL_VALUES,
    STATUS_NOT_OCEANIC_LIKE,
    STATUS_UNRESOLVED_NO_ACTIVE_RIDGE_PATH_CEILING,
    validate_initial_oceanic_crust_age,
)
from magic_geo.native import generate_geo_world


def _config(
    *,
    zero_motion: bool = False,
    low_rate_motion: bool = False,
) -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["run"]["seed"] = 20260711
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    data["tectonics"]["plate_motion_scale_deg_per_step"] = (
        0.0 if zero_motion else 4.0
    )
    if low_rate_motion:
        data["tectonics"]["min_angular_speed"] = 1.0e-15
        data["tectonics"]["max_angular_speed"] = 1.0e-15
    data["erosion"]["iterations"] = 1
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    data["output"]["float_precision"] = 8
    return WorldConfig.model_validate(data)


def _mutated_value(value: object) -> object:
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if type(value) is float:
        return value + max(1.0e-5, abs(value) * 1.0e-8)
    if isinstance(value, str):
        return f"tampered_{value}"
    if isinstance(value, list):
        if not value:
            return [0]
        altered = list(value)
        altered[0] = _mutated_value(altered[0])
        return altered
    raise AssertionError(f"unsupported mutation value {value!r}")


class InitialOceanicCrustAgeValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(config_to_native(_config()))
        cls.zero_motion_world = generate_geo_world(
            config_to_native(_config(zero_motion=True))
        )
        cls.low_rate_motion_world = generate_geo_world(
            config_to_native(_config(low_rate_motion=True))
        )

    def assert_rejected(self, world: object) -> None:
        result = validate_initial_oceanic_crust_age(world)
        self.assertFalse(result["passed"])
        self.assertTrue(result["failures"])

    def test_generated_world_replays_every_age_path_and_history_alias(self) -> None:
        result = validate_initial_oceanic_crust_age(self.world)

        self.assertTrue(result["passed"], result["failures"])
        metrics = result["metrics"]
        self.assertEqual(metrics["cell_count"], len(self.world["cells"]))
        self.assertGreater(metrics["oceanic_like_cell_count"], 0)
        self.assertGreater(metrics["eligible_ridge_segment_count"], 0)
        self.assertGreater(metrics["ridge_seed_cell_count"], 0)
        for field in (
            "provisional_oceanic_mask_replayed",
            "eligible_ridge_segments_replayed",
            "representative_spreading_rates_replayed",
            "ridge_seed_cells_replayed",
            "dijkstra_unclamped_ages_replayed",
            "dijkstra_path_witness_replayed",
            "clamped_ages_and_status_replayed",
            "summary_statistics_replayed",
            "cdf_replayed",
            "oceanic_history_aliases_replayed",
            "procedural_authority",
        ):
            self.assertTrue(metrics[field], field)
        for field in (
            "physical_seafloor_creation_resolved",
            "spreading_rate_calibrated",
            "local_spreading_rates_resolved",
            "ridge_flowlines_resolved",
            "subduction_sink_history_resolved",
            "convergence_history_resolved",
            "seton_2020_age_grid_used_as_generation_input",
        ):
            self.assertFalse(metrics[field], field)
        self.assertEqual(
            set(self.world["initial_oceanic_crust_age_model"]),
            set(MODEL_LITERAL_VALUES) | {"effective_maximum_age_ma"},
        )

    def test_zero_motion_assigns_every_oceanic_component_the_ceiling(self) -> None:
        result = validate_initial_oceanic_crust_age(self.zero_motion_world)

        self.assertTrue(result["passed"], result["failures"])
        metrics = result["metrics"]
        self.assertEqual(metrics["eligible_ridge_segment_count"], 0)
        self.assertEqual(metrics["ridge_seed_cell_count"], 0)
        self.assertEqual(metrics["reachable_oceanic_like_cell_count"], 0)
        self.assertEqual(
            metrics["unreachable_oceanic_like_cell_count"],
            metrics["oceanic_like_cell_count"],
        )
        ledger = self.zero_motion_world["initial_oceanic_crust_age_ledger"]
        for age, unclamped, status in zip(
            ledger["age_ma_by_cell"],
            ledger["unclamped_graph_age_ma_by_cell"],
            ledger["status_id_by_cell"],
            strict=True,
        ):
            if status == STATUS_NOT_OCEANIC_LIKE:
                self.assertEqual(age, 0.0)
            else:
                self.assertEqual(
                    status,
                    STATUS_UNRESOLVED_NO_ACTIVE_RIDGE_PATH_CEILING,
                )
                self.assertEqual(age, CONFIGURED_MAXIMUM_AGE_MA)
                self.assertEqual(unclamped, -1.0)

    def test_low_rate_boundary_operands_round_trip_for_exact_replay(self) -> None:
        segments = self.low_rate_motion_world["plate_motion_history"][0][
            "boundary_segments"
        ]
        self.assertTrue(segments)
        self.assertTrue(
            any(
                0.0 < abs(segment["signed_opening_rate_km_per_ma"]) < 1.0e-12
                for segment in segments
            )
        )
        result = validate_initial_oceanic_crust_age(self.low_rate_motion_world)
        self.assertTrue(result["passed"], result["failures"])

    def test_every_model_field_and_schema_mutation_is_rejected(self) -> None:
        model = self.world["initial_oceanic_crust_age_model"]
        for field in model:
            with self.subTest(field=field):
                altered = deepcopy(self.world)
                altered["initial_oceanic_crust_age_model"][field] = (
                    _mutated_value(model[field])
                )
                self.assert_rejected(altered)

        altered = deepcopy(self.world)
        altered["initial_oceanic_crust_age_model"]["unexpected_claim"] = True
        self.assert_rejected(altered)
        altered = deepcopy(self.world)
        altered["initial_oceanic_crust_age_model"].pop("model_type")
        self.assert_rejected(altered)

    def test_every_ledger_field_and_schema_mutation_is_rejected(self) -> None:
        ledger = self.world["initial_oceanic_crust_age_ledger"]
        for field in ledger:
            with self.subTest(field=field):
                altered = deepcopy(self.world)
                altered["initial_oceanic_crust_age_ledger"][field] = (
                    _mutated_value(ledger[field])
                )
                self.assert_rejected(altered)

        altered = deepcopy(self.world)
        altered["initial_oceanic_crust_age_ledger"]["unexpected_claim"] = 0
        self.assert_rejected(altered)
        altered = deepcopy(self.world)
        altered["initial_oceanic_crust_age_ledger"].pop("cell_count")
        self.assert_rejected(altered)

    def test_independent_root_and_oceanic_alias_mutation_matrix(self) -> None:
        ledger = self.world["initial_oceanic_crust_age_ledger"]
        oceanic_id = next(
            cell_id
            for cell_id, status in enumerate(ledger["status_id_by_cell"])
            if status != STATUS_NOT_OCEANIC_LIKE
        )
        eligible_segment_id = ledger["eligible_ridge_segment_ids"][0]

        def mutate_position(world: dict) -> None:
            world["cells"][oceanic_id]["position_3d"][0] += 0.01

        def mutate_area(world: dict) -> None:
            world["cells"][oceanic_id]["area_km2"] *= 1.01

        def mutate_neighbor(world: dict) -> None:
            world["cells"][oceanic_id]["neighbors"][0] = oceanic_id

        def mutate_planet_radius(world: dict) -> None:
            world["plate_boundary_segment_model"]["radius_km"] += 1.0

        def mutate_planet_age(world: dict) -> None:
            world["plate_kinematic_model"][
                "tectonic_process_geological_age_ga_input"
            ] = 0.1

        def mutate_provisional_type(world: dict) -> None:
            world["plate_motion_history"][0]["crust_overlap_ledger"][
                "remapped_crust_type_by_cell"
            ][oceanic_id] = 1

        def mutate_provisional_lithology(world: dict) -> None:
            world["plate_motion_history"][0]["crust_overlap_ledger"][
                "remapped_lithology_by_cell"
            ][oceanic_id] = 1

        def mutate_provisional_thickness(world: dict) -> None:
            world["plate_motion_history"][0]["crust_overlap_ledger"][
                "remapped_crust_thickness_km_by_cell"
            ][oceanic_id] += 0.1

        def mutate_provisional_density(world: dict) -> None:
            world["plate_motion_history"][0]["crust_overlap_ledger"][
                "remapped_crust_density_by_cell"
            ][oceanic_id] += 0.01

        def mutate_history_alias(world: dict) -> None:
            world["plate_motion_history"][0]["crust_overlap_ledger"][
                "remapped_crust_age_ma_by_cell"
            ][oceanic_id] += 0.01

        def segment(world: dict) -> dict:
            return world["plate_motion_history"][0]["boundary_segments"][
                eligible_segment_id
            ]

        mutations = {
            "cell_position": mutate_position,
            "cell_area": mutate_area,
            "cell_neighbor": mutate_neighbor,
            "planet_radius": mutate_planet_radius,
            "planet_geological_age": mutate_planet_age,
            "provisional_type": mutate_provisional_type,
            "provisional_lithology": mutate_provisional_lithology,
            "provisional_thickness": mutate_provisional_thickness,
            "provisional_density": mutate_provisional_density,
            "history_age_alias": mutate_history_alias,
            "segment_class": lambda world: segment(world).__setitem__(
                "direct_boundary_class", "transform"
            ),
            "segment_length": lambda world: segment(world).__setitem__(
                "length_km", segment(world)["length_km"] + 1.0
            ),
            "segment_rate": lambda world: segment(world).__setitem__(
                "signed_opening_rate_km_per_ma",
                segment(world)["signed_opening_rate_km_per_ma"] + 0.01,
            ),
            "segment_relative_velocity": lambda world: segment(world).__setitem__(
                "relative_velocity_x_km_per_ma",
                segment(world)["relative_velocity_x_km_per_ma"] + 0.01,
            ),
            "segment_normal": lambda world: segment(world).__setitem__(
                "left_to_right_normal_unit_x",
                segment(world)["left_to_right_normal_unit_x"] + 0.01,
            ),
            "segment_opening_flag": lambda world: segment(world).__setitem__(
                "left_opening_oceanic_like", False
            ),
            "segment_opening_type": lambda world: segment(world).__setitem__(
                "left_opening_crust_type",
                segment(world)["left_opening_crust_type"] + 1,
            ),
            "segment_opening_lithology": lambda world: segment(world).__setitem__(
                "left_opening_lithology",
                segment(world)["left_opening_lithology"] + 1,
            ),
            "segment_opening_age": lambda world: segment(world).__setitem__(
                "left_opening_crust_age_ma",
                segment(world)["left_opening_crust_age_ma"] + 0.01,
            ),
            "segment_opening_thickness": lambda world: segment(world).__setitem__(
                "left_opening_crust_thickness_km",
                segment(world)["left_opening_crust_thickness_km"] + 0.01,
            ),
            "segment_opening_density": lambda world: segment(world).__setitem__(
                "left_opening_crust_density_g_cm3",
                segment(world)["left_opening_crust_density_g_cm3"] + 0.01,
            ),
            "segment_opening_availability": lambda world: segment(world).__setitem__(
                "left_opening_crust_state_available", False
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                altered = deepcopy(self.world)
                mutate(altered)
                self.assert_rejected(altered)

    def test_malformed_payloads_fail_closed_before_unbounded_work(self) -> None:
        for payload in (
            None,
            {},
            {"cells": []},
            {"cells": [{}] * 200_001, "plate_motion_history": [{}]},
        ):
            with self.subTest(payload_type=type(payload).__name__):
                self.assert_rejected(payload)
