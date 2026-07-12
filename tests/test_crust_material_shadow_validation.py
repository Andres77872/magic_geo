from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.crust_material_shadow_validation import (
    DENSITY_VOLUME_TO_MASS_KG,
    MODEL_LITERAL_VALUES,
    PacketKey,
    initial_crust_material_shadow_packets,
    replay_crust_material_shadow_step,
    validate_crust_material_shadow,
    _operation_mass_tolerance,
)
from magic_geo.crust_process_validation import CRUST_PROCESS_REASON_ORDER
from magic_geo.config import WorldConfig, config_to_native, load_config
from magic_geo.native import generate_geo_world


def _zero_reason_deltas(cell_count: int) -> list[list[float]]:
    return [[0.0] * cell_count for _ in CRUST_PROCESS_REASON_ORDER]


def _generated_config(
    *,
    threads: int = 1,
    radius_km: float = 6371.0,
    mesh_backend: str = "geodesic_icosahedron",
    cell_count: int = 128,
    extreme_rotation: bool = False,
) -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["run"]["seed"] = 20260711
    data["planet"]["radius_km"] = radius_km
    data["mesh"]["backend"] = mesh_backend
    data["mesh"]["cell_count"] = cell_count
    data["tectonics"]["plate_count"] = 32 if extreme_rotation else 8
    if extreme_rotation:
        data["tectonics"]["min_angular_speed"] = 18.0
        data["tectonics"]["max_angular_speed"] = 18.0
        data["tectonics"]["plate_motion_scale_deg_per_step"] = 10.0
    data["erosion"]["iterations"] = 1
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = threads
    data["output"]["float_precision"] = 8
    return WorldConfig.model_validate(data)


def _refined_matrix_config() -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["run"]["seed"] = 20260711
    data["mesh"]["backend"] = "fibonacci_sphere"
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    data["erosion"]["iterations"] = 4
    data["erosion"]["maturation_timestep_ma"] = 2.5
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    return WorldConfig.model_validate(data)


def _packet_cells(table: dict) -> list[dict[PacketKey, float]]:
    offsets = table["cell_offsets"]
    result: list[dict[PacketKey, float]] = []
    for cell in range(len(offsets) - 1):
        result.append(
            {
                PacketKey(
                    table["origin_kind_ids"][index],
                    table["origin_plate_ids"][index],
                    table["origin_reason_ids"][index],
                ): table["dry_rock_mass_kg"][index]
                for index in range(offsets[cell], offsets[cell + 1])
            }
        )
    return result


def _reason_payload(reason_mass_delta_kg: list[float]) -> list[dict]:
    return [
        {
            "reason": reason,
            "net_delta": {
                "density_weighted_crust_volume": (
                    reason_mass_delta_kg[reason_id]
                    / DENSITY_VOLUME_TO_MASS_KG
                )
            },
        }
        for reason_id, reason in enumerate(CRUST_PROCESS_REASON_ORDER)
    ]


def _plate_step(
    *,
    step_id: int,
    thickness_km: float,
    density: float,
    thickness_process_change_km: float,
    density_process_change: float,
    reason_mass_delta_kg: list[float],
) -> dict:
    transported_density_volume = thickness_km * density
    return {
        "id": step_id,
        "stage": "initial_plate_domains" if step_id == 0 else "erosion_tectonics_0",
        "erosion_iteration": -1 if step_id == 0 else 0,
        "plates": [{"plate_id": 0}],
        "cell_plate_ids": [0],
        "crust_type_by_cell": [0],
        "crust_thickness_process_change_km_by_cell": [
            thickness_process_change_km
        ],
        "crust_density_process_change_by_cell": [density_process_change],
        "crust_overlap_ledger": {
            "destination_offsets": [0, 1],
            "source_cell_ids": [0],
            "overlap_area_km2": [1.0],
            "contributor_count_by_cell": [1],
            "remapped_crust_thickness_km_by_cell": [thickness_km],
            "remapped_crust_density_by_cell": [density],
            "transported_inventory": {
                "density_weighted_crust_volume": transported_density_volume
            },
            "process_inventory_attribution": {
                "reasons": _reason_payload(reason_mass_delta_kg)
            },
        },
    }


def _history_record(step: dict, replay: dict) -> dict:
    overlap = step["crust_overlap_ledger"]
    final_thickness = (
        overlap["remapped_crust_thickness_km_by_cell"][0]
        + step["crust_thickness_process_change_km_by_cell"][0]
    )
    final_density = (
        overlap["remapped_crust_density_by_cell"][0]
        + step["crust_density_process_change_by_cell"][0]
    )
    scalar_mass = final_thickness * final_density * DENSITY_VOLUME_TO_MASS_KG
    closing_cells = _packet_cells(replay["closing_packets"])
    closing_cell_mass = math.fsum(closing_cells[0].values())
    raw_mass = (
        overlap["transported_inventory"]["density_weighted_crust_volume"]
        * DENSITY_VOLUME_TO_MASS_KG
    )
    return {
        "id": step["id"],
        "plate_motion_history_id": step["id"],
        "stage": step["stage"],
        "erosion_iteration": step["erosion_iteration"],
        "cell_count": 1,
        "opening_packets": replay["opening_packets"],
        "transported_packets": replay["transported_packets"],
        "unresolved_source_adjustments": replay[
            "unresolved_source_adjustments"
        ],
        "unresolved_sink_adjustments": replay[
            "unresolved_sink_adjustments"
        ],
        "closing_packets": replay["closing_packets"],
        "global_opening_mass_kg": replay["global_opening_mass_kg"],
        "global_transported_mass_kg": replay["global_transported_mass_kg"],
        "global_unresolved_source_mass_kg": replay[
            "global_unresolved_source_mass_kg"
        ],
        "global_unresolved_sink_mass_kg": replay[
            "global_unresolved_sink_mass_kg"
        ],
        "global_closing_mass_kg": replay["global_closing_mass_kg"],
        "raw_transported_scalar_mass_kg": raw_mass,
        "shadow_minus_raw_transport_residual_kg": (
            replay["global_transported_mass_kg"] - raw_mass
        ),
        "source_to_transport_residual_kg": replay[
            "source_to_transport_residual_kg"
        ],
        "closing_scalar_mass_kg": scalar_mass,
        "closing_scalar_mass_residual_kg": closing_cell_mass - scalar_mass,
        "maximum_absolute_cell_closing_scalar_mass_residual_kg": abs(
            closing_cell_mass - scalar_mass
        ),
        "ordered_adjustment_reconciliation_residual_kg": replay[
            "ordered_adjustment_reconciliation_residual_kg"
        ],
        "opening_packet_count": replay["opening_packet_count"],
        "transported_packet_count": replay["transported_packet_count"],
        "unresolved_source_adjustment_count": replay[
            "unresolved_source_adjustment_count"
        ],
        "unresolved_sink_adjustment_count": replay[
            "unresolved_sink_adjustment_count"
        ],
        "closing_packet_count": replay["closing_packet_count"],
        "ordered_reason_adjustments": replay["ordered_reason_adjustments"],
    }


def _sequential_world(*, mass_neutral_state_change: bool = False) -> dict:
    cells = [{"id": 0, "area_km2": 1.0}]
    opening = initial_crust_material_shadow_packets(
        areas_km2=[1.0],
        crust_thickness_km=[10.0],
        crust_density_g_cm3=[3.0],
        crust_type_ids=[0],
        plate_ids=[0],
    )
    initial_deltas = _zero_reason_deltas(1)
    initial_replay = replay_crust_material_shadow_step(
        opening_packets=opening,
        destination_offsets=[0, 1],
        source_cell_ids=[0],
        overlap_area_km2=[1.0],
        current_plate_ids=[0],
        ordered_reason_mass_delta_kg_by_cell=initial_deltas,
    )
    initial_step = _plate_step(
        step_id=0,
        thickness_km=10.0,
        density=3.0,
        thickness_process_change_km=0.0,
        density_process_change=0.0,
        reason_mass_delta_kg=[0.0] * len(CRUST_PROCESS_REASON_ORDER),
    )

    opening_second = _packet_cells(initial_replay["closing_packets"])
    second_deltas = _zero_reason_deltas(1)
    if mass_neutral_state_change:
        thickness_change = 2.0
        density_change = -0.5
        reason_totals = [0.0] * len(CRUST_PROCESS_REASON_ORDER)
    else:
        second_deltas[0][0] = 6.0e12
        second_deltas[1][0] = -9.0e12
        thickness_change = 0.0
        density_change = -0.3
        reason_totals = [6.0e12, -9.0e12] + [0.0] * 8
    second_replay = replay_crust_material_shadow_step(
        opening_packets=opening_second,
        destination_offsets=[0, 1],
        source_cell_ids=[0],
        overlap_area_km2=[1.0],
        current_plate_ids=[0],
        ordered_reason_mass_delta_kg_by_cell=second_deltas,
    )
    second_step = _plate_step(
        step_id=1,
        thickness_km=10.0,
        density=3.0,
        thickness_process_change_km=thickness_change,
        density_process_change=density_change,
        reason_mass_delta_kg=reason_totals,
    )
    history = [
        _history_record(initial_step, initial_replay),
        _history_record(second_step, second_replay),
    ]
    opening_counts = [record["opening_packet_count"] for record in history]
    transported_counts = [
        record["transported_packet_count"] for record in history
    ]
    closing_counts = [record["closing_packet_count"] for record in history]
    source_counts = [
        record["unresolved_source_adjustment_count"] for record in history
    ]
    sink_counts = [
        record["unresolved_sink_adjustment_count"] for record in history
    ]
    return {
        "cells": cells,
        "crust_material_shadow_model": deepcopy(MODEL_LITERAL_VALUES),
        "plate_motion_history": [initial_step, second_step],
        "crust_material_shadow_history": history,
        "summary": {
            "crust_material_shadow_history_step_count": len(history),
            "total_crust_material_shadow_packet_count": sum(opening_counts)
            + sum(transported_counts)
            + sum(closing_counts),
            "maximum_crust_material_shadow_packet_count_per_table": max(
                opening_counts + transported_counts + closing_counts
            ),
            "total_crust_material_shadow_opening_packet_count": sum(opening_counts),
            "total_crust_material_shadow_transported_packet_count": sum(
                transported_counts
            ),
            "total_crust_material_shadow_closing_packet_count": sum(closing_counts),
            "maximum_crust_material_shadow_opening_packet_count_per_step": max(
                opening_counts
            ),
            "maximum_crust_material_shadow_transported_packet_count_per_step": max(
                transported_counts
            ),
            "maximum_crust_material_shadow_closing_packet_count_per_step": max(
                closing_counts
            ),
            "total_crust_material_shadow_adjustment_count": sum(source_counts)
            + sum(sink_counts),
            "maximum_crust_material_shadow_adjustment_count_per_table": max(
                source_counts + sink_counts
            ),
            "total_crust_material_shadow_unresolved_source_adjustment_count": sum(
                source_counts
            ),
            "total_crust_material_shadow_unresolved_sink_adjustment_count": sum(
                sink_counts
            ),
            "cumulative_crust_material_shadow_unresolved_source_mass_kg": sum(
                record["global_unresolved_source_mass_kg"] for record in history
            ),
            "cumulative_crust_material_shadow_unresolved_sink_mass_kg": sum(
                record["global_unresolved_sink_mass_kg"] for record in history
            ),
            "maximum_absolute_crust_material_shadow_transport_raw_residual_kg": max(
                abs(record["shadow_minus_raw_transport_residual_kg"])
                for record in history
            ),
            "maximum_crust_material_shadow_closing_scalar_relative_residual": max(
                abs(record["closing_scalar_mass_residual_kg"])
                / max(1.0, abs(record["closing_scalar_mass_kg"]))
                for record in history
            ),
            "maximum_absolute_crust_material_shadow_adjustment_reconciliation_residual_kg": max(
                abs(record["ordered_adjustment_reconciliation_residual_kg"])
                for record in history
            ),
        },
    }


class CrustMaterialShadowReplayTests(TestCase):
    def test_source_normalized_sparse_mixing_preserves_every_origin(self) -> None:
        key_a = PacketKey(0, 0, -1)
        key_b = PacketKey(1, 0, -1)
        key_c = PacketKey(2, 1, -1)
        replay = replay_crust_material_shadow_step(
            opening_packets=[
                {key_a: 60.0, key_b: 40.0},
                {key_c: 80.0},
            ],
            destination_offsets=[0, 2, 4],
            source_cell_ids=[0, 1, 0, 1],
            overlap_area_km2=[0.75, 0.25, 0.25, 0.75],
            current_plate_ids=[0, 1],
            ordered_reason_mass_delta_kg_by_cell=_zero_reason_deltas(2),
        )

        transported = _packet_cells(replay["transported_packets"])
        self.assertEqual(
            transported,
            [
                {key_a: 45.0, key_b: 30.0, key_c: 20.0},
                {key_a: 15.0, key_b: 10.0, key_c: 60.0},
            ],
        )
        self.assertEqual(replay["global_opening_mass_kg"], 180.0)
        self.assertEqual(replay["global_transported_mass_kg"], 180.0)
        self.assertEqual(replay["source_to_transport_residual_kg"], 0.0)

    def test_ordered_source_then_sink_does_not_cancel_provenance(self) -> None:
        initial_key = PacketKey(0, 0, -1)
        deltas = _zero_reason_deltas(1)
        deltas[0][0] = 25.0
        deltas[1][0] = -50.0
        replay = replay_crust_material_shadow_step(
            opening_packets=[{initial_key: 100.0}],
            destination_offsets=[0, 1],
            source_cell_ids=[0],
            overlap_area_km2=[1.0],
            current_plate_ids=[1],
            ordered_reason_mass_delta_kg_by_cell=deltas,
        )

        unresolved = PacketKey(9, 1, 0)
        self.assertEqual(
            _packet_cells(replay["closing_packets"]),
            [{initial_key: 60.0, unresolved: 15.0}],
        )
        sources = replay["unresolved_source_adjustments"]
        sinks = replay["unresolved_sink_adjustments"]
        self.assertEqual(sources["process_reason_ids"], [0])
        self.assertEqual(sources["dry_rock_mass_kg"], [25.0])
        self.assertEqual(sinks["process_reason_ids"], [1, 1])
        self.assertEqual(sinks["dry_rock_mass_kg"], [40.0, 10.0])
        self.assertEqual(replay["global_closing_mass_kg"], 75.0)
        self.assertEqual(
            replay["ordered_adjustment_reconciliation_residual_kg"], 0.0
        )

    def test_exact_sink_exhaustion_can_be_reseeded_by_later_rule(self) -> None:
        initial_key = PacketKey(0, 0, -1)
        deltas = _zero_reason_deltas(1)
        deltas[0][0] = -100.0
        deltas[1][0] = 40.0

        replay = replay_crust_material_shadow_step(
            opening_packets=[{initial_key: 100.0}],
            destination_offsets=[0, 1],
            source_cell_ids=[0],
            overlap_area_km2=[1.0],
            current_plate_ids=[1],
            ordered_reason_mass_delta_kg_by_cell=deltas,
        )

        self.assertEqual(
            _packet_cells(replay["closing_packets"]),
            [{PacketKey(9, 1, 1): 40.0}],
        )
        self.assertEqual(
            replay["unresolved_sink_adjustments"]["dry_rock_mass_kg"],
            [100.0],
        )
        self.assertEqual(
            replay["unresolved_source_adjustments"]["dry_rock_mass_kg"],
            [40.0],
        )

    def test_mass_neutral_density_thickness_change_needs_no_adjustment(self) -> None:
        world = _sequential_world(mass_neutral_state_change=True)
        replay = validate_crust_material_shadow(world)

        self.assertTrue(replay["passed"], replay["failures"])
        moving = world["crust_material_shadow_history"][1]
        self.assertEqual(moving["global_unresolved_source_mass_kg"], 0.0)
        self.assertEqual(moving["global_unresolved_sink_mass_kg"], 0.0)
        self.assertEqual(moving["opening_packets"], moving["closing_packets"])
        model = world["crust_material_shadow_model"]
        self.assertFalse(model["authoritative_for_cell_state"])
        self.assertFalse(model["physical_source_sink_resolved"])
        self.assertFalse(model["solid_volume_resolved"])
        self.assertFalse(model["phase_resolved"])
        self.assertFalse(model["upper_mantle_exchange_reservoir_resolved"])
        self.assertFalse(model["subducted_slab_reservoir_resolved"])
        self.assertFalse(model["global_crust_cycle_mass_conservation_resolved"])

    def test_complete_sequential_history_replays(self) -> None:
        world = _sequential_world()
        replay = validate_crust_material_shadow(world)

        self.assertTrue(replay["passed"], replay["failures"])
        self.assertEqual(replay["metrics"]["history_step_count"], 2)
        self.assertEqual(
            replay["metrics"]["cumulative_unresolved_source_mass_kg"],
            6.0e12,
        )
        self.assertEqual(
            replay["metrics"]["cumulative_unresolved_sink_mass_kg"],
            9.0e12,
        )

    def test_generated_history_replays_and_is_thread_bit_deterministic(
        self,
    ) -> None:
        serial = generate_geo_world(
            config_to_native(_generated_config(threads=1))
        )
        parallel = generate_geo_world(
            config_to_native(_generated_config(threads=4))
        )

        serial_replay = validate_crust_material_shadow(serial)
        parallel_replay = validate_crust_material_shadow(parallel)
        self.assertTrue(serial_replay["passed"], serial_replay["failures"])
        self.assertTrue(parallel_replay["passed"], parallel_replay["failures"])
        self.assertEqual(
            serial["crust_material_shadow_history"],
            parallel["crust_material_shadow_history"],
        )

    def test_operation_count_bound_overflow_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "overflowed"):
            _operation_mass_tolerance(
                1.0,
                1.0,
                absolute_term_sum=1.0,
                operation_count=10**400,
            )

    def test_refined_matrix_rounding_paths_are_bounded_but_not_fail_open(
        self,
    ) -> None:
        world = generate_geo_world(config_to_native(_refined_matrix_config()))
        replay = validate_crust_material_shadow(world)
        self.assertTrue(replay["passed"], replay["failures"])

        shadow_reason = world["crust_material_shadow_history"][3][
            "ordered_reason_adjustments"
        ][8]
        process_reason = world["plate_motion_history"][3][
            "crust_overlap_ledger"
        ]["process_inventory_attribution"]["reasons"][8]
        shadow_net = (
            shadow_reason["source_mass_kg"] - shadow_reason["sink_mass_kg"]
        )
        process_net = (
            process_reason["net_delta"]["density_weighted_crust_volume"]
            * DENSITY_VOLUME_TO_MASS_KG
        )
        # The independent paths deliberately round at different boundaries:
        # shadow mass converts each cell before subtraction, while the process
        # ledger reduces density-volume in long double and converts afterward.
        # The exact residual is geometry- and reduction-path-dependent.  A
        # nonzero residual proves the two independently rounded paths remain
        # distinct; the successful replay above proves the value is inside
        # the operand-derived bound.
        self.assertGreater(abs(shadow_net - process_net), 0.0)

        corrupted = deepcopy(world)
        corrupted_reason = corrupted["plate_motion_history"][3][
            "crust_overlap_ledger"
        ]["process_inventory_attribution"]["reasons"][8]
        corrupted_reason["net_delta"]["density_weighted_crust_volume"] += 1.0e-3
        corrupted_replay = validate_crust_material_shadow(corrupted)
        self.assertFalse(corrupted_replay["passed"], corrupted_replay)
        self.assertTrue(
            any(
                "reason totals failed at step 3, reason 8" in failure
                for failure in corrupted_replay["failures"]
            ),
            corrupted_replay,
        )

    def test_non_earth_radius_shadow_mass_scales_with_surface_area(self) -> None:
        small = generate_geo_world(
            config_to_native(_generated_config(radius_km=3200.0))
        )
        large = generate_geo_world(
            config_to_native(_generated_config(radius_km=6400.0))
        )
        for world in (small, large):
            replay = validate_crust_material_shadow(world)
            self.assertTrue(replay["passed"], replay["failures"])

        for small_step, large_step in zip(
            small["crust_material_shadow_history"],
            large["crust_material_shadow_history"],
            strict=True,
        ):
            for table in (
                "opening_packets",
                "transported_packets",
                "unresolved_source_adjustments",
                "unresolved_sink_adjustments",
                "closing_packets",
            ):
                for key in (
                    "cell_offsets",
                    "origin_kind_ids",
                    "origin_plate_ids",
                    "origin_reason_ids",
                ):
                    self.assertEqual(
                        small_step[table][key],
                        large_step[table][key],
                    )
                if "process_reason_ids" in small_step[table]:
                    self.assertEqual(
                        small_step[table]["process_reason_ids"],
                        large_step[table]["process_reason_ids"],
                    )
                for small_mass, large_mass in zip(
                    small_step[table]["dry_rock_mass_kg"],
                    large_step[table]["dry_rock_mass_kg"],
                    strict=True,
                ):
                    self.assertTrue(
                        math.isclose(
                            large_mass,
                            4.0 * small_mass,
                            rel_tol=2.0e-12,
                            abs_tol=max(1.0e-3, math.ulp(large_mass) * 128.0),
                        ),
                        (table, small_mass, large_mass),
                    )
            for field in (
                "global_opening_mass_kg",
                "global_transported_mass_kg",
                "global_unresolved_source_mass_kg",
                "global_unresolved_sink_mass_kg",
                "global_closing_mass_kg",
                "raw_transported_scalar_mass_kg",
            ):
                self.assertTrue(
                    math.isclose(
                        large_step[field],
                        4.0 * small_step[field],
                        rel_tol=2.0e-12,
                        abs_tol=max(
                            1.0e-3,
                            math.ulp(max(1.0, abs(large_step[field]))) * 128.0,
                        ),
                    ),
                    field,
                )

    def test_180_degree_motion_reseeds_fully_uncovered_destinations(self) -> None:
        cases = (
            ("fibonacci_sphere", 128),
            ("geodesic_icosahedron", 162),
        )
        for mesh_backend, cell_count in cases:
            with self.subTest(mesh_backend=mesh_backend):
                world = generate_geo_world(
                    config_to_native(
                        _generated_config(
                            mesh_backend=mesh_backend,
                            cell_count=cell_count,
                            extreme_rotation=True,
                        )
                    )
                )
                replay = validate_crust_material_shadow(world)
                self.assertTrue(replay["passed"], replay["failures"])
                moving_plate = world["plate_motion_history"][1]
                moving_shadow = world["crust_material_shadow_history"][1]
                self.assertTrue(
                    all(
                        math.isclose(
                            abs(float(plate["step_rotation_deg"])),
                            180.0,
                            rel_tol=0.0,
                            abs_tol=1.0e-12,
                        )
                        for plate in moving_plate["plates"]
                    )
                )
                self.assertEqual(
                    min(
                        moving_plate["crust_overlap_ledger"][
                            "contributor_count_by_cell"
                        ]
                    ),
                    0,
                )
                transported_offsets = moving_shadow["transported_packets"][
                    "cell_offsets"
                ]
                closing_offsets = moving_shadow["closing_packets"][
                    "cell_offsets"
                ]
                fully_uncovered = [
                    cell
                    for cell in range(len(world["cells"]))
                    if transported_offsets[cell]
                    == transported_offsets[cell + 1]
                ]
                self.assertTrue(fully_uncovered)
                self.assertTrue(
                    all(
                        closing_offsets[cell] < closing_offsets[cell + 1]
                        for cell in fully_uncovered
                    )
                )
                self.assertGreater(
                    moving_shadow["global_unresolved_source_mass_kg"],
                    0.0,
                )

    def test_malformed_and_coherently_corrupted_ledgers_are_rejected(self) -> None:
        base = _sequential_world()

        def fractional_offset(world: dict) -> None:
            world["crust_material_shadow_history"][1]["opening_packets"][
                "cell_offsets"
            ][0] = 0.5

        def invalid_origin_reason(world: dict) -> None:
            world["crust_material_shadow_history"][0]["opening_packets"][
                "origin_reason_ids"
            ][0] = 0

        def nonfinite_mass(world: dict) -> None:
            world["crust_material_shadow_history"][1]["closing_packets"][
                "dry_rock_mass_kg"
            ][0] = math.inf

        def boolean_origin_kind(world: dict) -> None:
            world["crust_material_shadow_history"][0]["opening_packets"][
                "origin_kind_ids"
            ][0] = True

        def duplicate_packet_key(world: dict) -> None:
            table = world["crust_material_shadow_history"][1][
                "closing_packets"
            ]
            for field in (
                "origin_kind_ids",
                "origin_plate_ids",
                "origin_reason_ids",
                "dry_rock_mass_kg",
            ):
                table[field].append(table[field][-1])
            table["cell_offsets"][-1] += 1

        def invalid_source_origin_kind(world: dict) -> None:
            world["crust_material_shadow_history"][1][
                "unresolved_source_adjustments"
            ]["origin_kind_ids"][0] = 0

        def mismatched_source_process_reason(world: dict) -> None:
            world["crust_material_shadow_history"][1][
                "unresolved_source_adjustments"
            ]["process_reason_ids"][0] = 1

        def physical_claim(world: dict) -> None:
            world["crust_material_shadow_model"][
                "physical_source_sink_resolved"
            ] = True

        def break_opening_link(world: dict) -> None:
            world["crust_material_shadow_history"][1]["opening_packets"][
                "dry_rock_mass_kg"
            ][0] += 1.0e9

        def coherent_source_and_closing_increase(world: dict) -> None:
            record = world["crust_material_shadow_history"][1]
            record["unresolved_source_adjustments"]["dry_rock_mass_kg"][0] += 1.0e9
            # The unresolved packet is the second canonical closing packet.
            record["closing_packets"]["dry_rock_mass_kg"][1] += 1.0e9
            record["global_unresolved_source_mass_kg"] += 1.0e9
            record["global_closing_mass_kg"] += 1.0e9
            record["ordered_reason_adjustments"][0]["source_mass_kg"] += 1.0e9

        def nonproportional_sink_with_preserved_totals(world: dict) -> None:
            record = world["crust_material_shadow_history"][1]
            sink = record["unresolved_sink_adjustments"]["dry_rock_mass_kg"]
            closing = record["closing_packets"]["dry_rock_mass_kg"]
            shift = 1.0e9
            sink[0] += shift
            sink[1] -= shift
            closing[0] -= shift
            closing[1] += shift

        def corrupt_reason_total_only(world: dict) -> None:
            world["crust_material_shadow_history"][1][
                "ordered_reason_adjustments"
            ][1]["sink_mass_kg"] += 1.0e9

        def corrupt_global_mass_mirror(world: dict) -> None:
            world["crust_material_shadow_history"][1][
                "global_transported_mass_kg"
            ] += 1.0e9

        def corrupt_history_link(world: dict) -> None:
            world["crust_material_shadow_history"][1][
                "plate_motion_history_id"
            ] = 0

        def missing_packet_column(world: dict) -> None:
            del world["crust_material_shadow_history"][1][
                "transported_packets"
            ]["origin_reason_ids"]

        def corrupt_summary_mirror(world: dict) -> None:
            world["summary"][
                "total_crust_material_shadow_packet_count"
            ] += 1

        def corrupt_relative_summary_mirror(world: dict) -> None:
            world["summary"][
                "maximum_crust_material_shadow_closing_scalar_relative_residual"
            ] += 1.0e-9

        mutations = {
            "fractional_offset": fractional_offset,
            "invalid_origin_reason": invalid_origin_reason,
            "nonfinite_mass": nonfinite_mass,
            "boolean_origin_kind": boolean_origin_kind,
            "duplicate_packet_key": duplicate_packet_key,
            "invalid_source_origin_kind": invalid_source_origin_kind,
            "source_process_reason": mismatched_source_process_reason,
            "physical_claim": physical_claim,
            "opening_link": break_opening_link,
            "coherent_source_closing": coherent_source_and_closing_increase,
            "nonproportional_sink": nonproportional_sink_with_preserved_totals,
            "reason_total": corrupt_reason_total_only,
            "global_mass_mirror": corrupt_global_mass_mirror,
            "history_link": corrupt_history_link,
            "missing_packet_column": missing_packet_column,
            "summary_mirror": corrupt_summary_mirror,
            "relative_summary_mirror": corrupt_relative_summary_mirror,
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                world = deepcopy(base)
                mutate(world)
                replay = validate_crust_material_shadow(world)
                self.assertFalse(replay["passed"], replay)
                self.assertTrue(replay["failures"])
