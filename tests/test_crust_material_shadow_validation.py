from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest import TestCase

from magic_geo.crust_material_shadow_validation import (
    DENSITY_VOLUME_TO_MASS_KG,
    MODEL_LITERAL_VALUES,
    UNRESOLVED_ORIGIN_KIND_ID,
    PacketKey,
    initial_crust_material_shadow_packets,
    replay_crust_material_shadow_step,
    validate_crust_material_shadow,
    _adjustment_cells,
    _operation_mass_tolerance,
    _snapshot_cells,
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
    area_km2: float = 1.0,
    overlap_area_km2: float = 1.0,
) -> dict:
    transported_density_volume = area_km2 * thickness_km * density
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
            "overlap_area_km2": [overlap_area_km2],
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


def _history_record(step: dict, replay: dict, area_km2: float = 1.0) -> dict:
    overlap = step["crust_overlap_ledger"]
    final_thickness = (
        overlap["remapped_crust_thickness_km_by_cell"][0]
        + step["crust_thickness_process_change_km_by_cell"][0]
    )
    final_density = (
        overlap["remapped_crust_density_by_cell"][0]
        + step["crust_density_process_change_by_cell"][0]
    )
    scalar_mass = (
        area_km2 * final_thickness * final_density * DENSITY_VOLUME_TO_MASS_KG
    )
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


def _sequential_world(
    *,
    mass_neutral_state_change: bool = False,
    area_km2: float = 1.0,
    overlap_area_km2: float = 1.0,
    second_thickness_km: float = 10.0,
    second_density: float = 3.0,
) -> dict:
    cells = [{"id": 0, "area_km2": area_km2}]
    opening = initial_crust_material_shadow_packets(
        areas_km2=[area_km2],
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
        overlap_area_km2=[overlap_area_km2],
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
        area_km2=area_km2,
        overlap_area_km2=overlap_area_km2,
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
        overlap_area_km2=[overlap_area_km2],
        current_plate_ids=[0],
        ordered_reason_mass_delta_kg_by_cell=second_deltas,
    )
    second_step = _plate_step(
        step_id=1,
        thickness_km=second_thickness_km,
        density=second_density,
        thickness_process_change_km=thickness_change,
        density_process_change=density_change,
        reason_mass_delta_kg=reason_totals,
        area_km2=area_km2,
        overlap_area_km2=overlap_area_km2,
    )
    history = [
        _history_record(initial_step, initial_replay, area_km2),
        _history_record(second_step, second_replay, area_km2),
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


def _set_field(container: Any, key: Any, value: Any) -> None:
    """Assign ``value``, refusing a tamper that would change nothing.

    A hardcoded tamper value that already equals what the fixture produced
    would make its case silently inert, so the guard lives in the helper
    rather than in each individual mutation.
    """

    current = container[key]
    if current == value and type(current) is type(value):
        raise AssertionError(
            f"tamper is a no-op: {key!r} is already {value!r}"
        )
    container[key] = value


class CrustMaterialShadowToleranceOperandTests(TestCase):
    def test_tolerance_operands_must_be_finite_and_nonnegative(self) -> None:
        cases = (
            ("negative_term_sum", {"absolute_term_sum": -1.0, "operation_count": 1}),
            (
                "nonfinite_term_sum",
                {"absolute_term_sum": math.inf, "operation_count": 1},
            ),
            (
                "negative_operation_count",
                {"absolute_term_sum": 1.0, "operation_count": -1},
            ),
        )
        for name, overrides in cases:
            with self.subTest(case=name):
                with self.assertRaisesRegex(
                    ValueError, "finite and nonnegative"
                ):
                    _operation_mass_tolerance(1.0, 1.0, **overrides)

    def test_infinite_tolerance_is_rejected_without_an_overflow_error(
        self,
    ) -> None:
        # 10**300 is representable, so the product silently reaches infinity
        # instead of raising OverflowError as the 10**400 bound does.
        with self.assertRaisesRegex(
            ValueError, "mass tolerance overflowed"
        ) as caught:
            _operation_mass_tolerance(
                1.0,
                1.0,
                absolute_term_sum=1.0e308,
                operation_count=10**300,
            )
        # Two raises share that message.  Only the OverflowError guard chains
        # a cause, so a null cause is what proves this reached the separate
        # nonfinite-product raise rather than the bound-overflow one.
        self.assertIsNone(caught.exception.__cause__)


class InitialCrustMaterialShadowPacketTests(TestCase):
    def _packets(self, **overrides: Any) -> list[dict[PacketKey, float]]:
        arguments: dict[str, Any] = {
            "areas_km2": [1.0],
            "crust_thickness_km": [10.0],
            "crust_density_g_cm3": [3.0],
            "crust_type_ids": [0],
            "plate_ids": [0],
        }
        arguments.update(overrides)
        return initial_crust_material_shadow_packets(**arguments)

    def test_healthy_inputs_produce_one_typed_packet_per_cell(self) -> None:
        self.assertEqual(
            self._packets(),
            [{PacketKey(0, 0, -1): 3.0e13}],
        )

    def test_input_length_and_emptiness_are_rejected(self) -> None:
        cases = (
            ("length_mismatch", {"plate_ids": [0, 0]}),
            ("all_empty", {
                "areas_km2": [],
                "crust_thickness_km": [],
                "crust_density_g_cm3": [],
                "crust_type_ids": [],
                "plate_ids": [],
            }),
        )
        for name, overrides in cases:
            with self.subTest(case=name):
                with self.assertRaisesRegex(
                    ValueError, "lengths differ or are empty"
                ):
                    self._packets(**overrides)

    def test_nonphysical_initial_state_is_rejected(self) -> None:
        cases = (
            ("zero_area", {"areas_km2": [0.0]}),
            ("zero_thickness", {"crust_thickness_km": [0.0]}),
            ("negative_density", {"crust_density_g_cm3": [-3.0]}),
            ("unresolved_crust_type", {"crust_type_ids": [9]}),
            ("negative_plate", {"plate_ids": [-1]}),
        )
        for name, overrides in cases:
            with self.subTest(case=name):
                with self.assertRaisesRegex(
                    ValueError, "initial shadow packet state is invalid"
                ):
                    self._packets(**overrides)


class CrustMaterialShadowStepGuardTests(TestCase):
    """Fail-closed guards inside the independent single-step replay."""

    def _replay(self, **overrides: Any) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "opening_packets": [{PacketKey(0, 0, -1): 100.0}],
            "destination_offsets": [0, 1],
            "source_cell_ids": [0],
            "overlap_area_km2": [1.0],
            "current_plate_ids": [0],
            "ordered_reason_mass_delta_kg_by_cell": _zero_reason_deltas(1),
        }
        arguments.update(overrides)
        return replay_crust_material_shadow_step(**arguments)

    def test_healthy_single_cell_step_is_the_control(self) -> None:
        replay = self._replay()
        self.assertEqual(replay["global_closing_mass_kg"], 100.0)
        self.assertEqual(replay["closing_packet_count"], 1)

    def test_malformed_step_inputs_are_rejected(self) -> None:
        two_cell_deltas = _zero_reason_deltas(2)
        sink_deltas = _zero_reason_deltas(1)
        sink_deltas[0][0] = -1.0e6
        empty_cell_deltas = _zero_reason_deltas(1)
        empty_cell_deltas[0][0] = -1.0
        short_row_deltas = _zero_reason_deltas(1)
        short_row_deltas[3] = [0.0, 0.0]
        cases = (
            (
                "empty_cell_arrays",
                {"opening_packets": [], "current_plate_ids": []},
                "equal nonempty cell arrays",
            ),
            (
                "plate_array_length_mismatch",
                {"current_plate_ids": [0, 0]},
                "equal nonempty cell arrays",
            ),
            (
                "nonpositive_overlap_area",
                {"overlap_area_km2": [0.0]},
                "overlap CSR is invalid",
            ),
            (
                "source_out_of_range",
                {"source_cell_ids": [1]},
                "overlap CSR is invalid",
            ),
            (
                "repeated_source_in_one_row",
                {
                    "destination_offsets": [0, 2],
                    "source_cell_ids": [0, 0],
                    "overlap_area_km2": [1.0, 1.0],
                },
                "overlap CSR is not canonical",
            ),
            (
                "wrong_reason_row_count",
                {"ordered_reason_mass_delta_kg_by_cell": [[0.0]]},
                "one mass-delta row per reason",
            ),
            (
                "wrong_reason_row_length",
                {"ordered_reason_mass_delta_kg_by_cell": short_row_deltas},
                "reason-delta rows have invalid length",
            ),
            (
                "nonpositive_opening_mass",
                {"opening_packets": [{PacketKey(0, 0, -1): 0.0}]},
                "opening shadow packets are invalid",
            ),
            (
                "untyped_opening_key",
                {"opening_packets": [{(0, 0, -1): 100.0}]},
                "opening shadow packets are invalid",
            ),
            (
                "source_without_transport_edge",
                {
                    "opening_packets": [
                        {PacketKey(0, 0, -1): 100.0},
                        {PacketKey(0, 0, -1): 100.0},
                    ],
                    "destination_offsets": [0, 1, 2],
                    "source_cell_ids": [0, 0],
                    "overlap_area_km2": [1.0, 1.0],
                    "current_plate_ids": [0, 0],
                    "ordered_reason_mass_delta_kg_by_cell": two_cell_deltas,
                },
                "every shadow source must have a transport edge",
            ),
            (
                "overflowing_source_overlap_area",
                {
                    "opening_packets": [
                        {PacketKey(0, 0, -1): 100.0},
                        {PacketKey(0, 0, -1): 100.0},
                    ],
                    "destination_offsets": [0, 1, 3],
                    "source_cell_ids": [0, 0, 1],
                    "overlap_area_km2": [1.0e308, 1.0e308, 1.0],
                    "current_plate_ids": [0, 0],
                    "ordered_reason_mass_delta_kg_by_cell": two_cell_deltas,
                },
                "shadow source overlap area is invalid",
            ),
            (
                "underflowing_transport_contribution",
                {
                    "opening_packets": [
                        {PacketKey(0, 0, -1): 1.0e-300},
                        {PacketKey(0, 0, -1): 100.0},
                    ],
                    "destination_offsets": [0, 1, 3],
                    "source_cell_ids": [0, 0, 1],
                    "overlap_area_km2": [5.0e-324, 1.0, 1.0],
                    "current_plate_ids": [0, 0],
                    "ordered_reason_mass_delta_kg_by_cell": two_cell_deltas,
                },
                "transport underflowed or overflowed",
            ),
            (
                "exhausted_final_edge_remainder",
                {
                    "opening_packets": [
                        {PacketKey(0, 0, -1): 100.0},
                        {PacketKey(0, 0, -1): 100.0},
                    ],
                    "destination_offsets": [0, 1, 3],
                    "source_cell_ids": [0, 0, 1],
                    "overlap_area_km2": [1.0, 5.0e-324, 1.0],
                    "current_plate_ids": [0, 0],
                    "ordered_reason_mass_delta_kg_by_cell": two_cell_deltas,
                },
                "final-edge remainder is invalid",
            ),
            (
                "sink_on_an_empty_cell",
                {
                    "opening_packets": [{}],
                    "ordered_reason_mass_delta_kg_by_cell": empty_cell_deltas,
                },
                "sink cannot draw from an empty cell",
            ),
            (
                "sink_exceeds_available_mass",
                {"ordered_reason_mass_delta_kg_by_cell": sink_deltas},
                "sink exceeds available packet mass",
            ),
        )
        for name, overrides, message in cases:
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, message):
                    self._replay(**overrides)


class CrustMaterialShadowViolationTests(TestCase):
    """Every serialized-ledger check that reports a violation.

    Each case tampers with exactly one field of an otherwise healthy
    sequential world.  :meth:`_expect_single_failure` first proves the
    untampered copy replays clean and then proves the tampered copy differs
    from it, so the reported violation can only come from the tamper.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.base = _sequential_world()

    def _expect_single_failure(self, mutate: Any, fragment: str) -> None:
        control = deepcopy(self.base)
        control_result = validate_crust_material_shadow(control)
        self.assertTrue(control_result["passed"], control_result["failures"])

        world = deepcopy(self.base)
        mutate(world)
        self.assertNotEqual(world, control, "tamper changed nothing")
        result = validate_crust_material_shadow(world)
        self.assertFalse(result["passed"], result)
        self.assertEqual(len(result["failures"]), 1, result["failures"])
        self.assertIn(fragment, result["failures"][0])

    def _run_cases(self, cases: tuple[tuple[str, Any, str], ...]) -> None:
        for name, mutate, fragment in cases:
            with self.subTest(case=name):
                self._expect_single_failure(mutate, fragment)

    def test_missing_or_misaligned_top_level_structures_are_reported(
        self,
    ) -> None:
        def drop_history(world: dict) -> None:
            del world["crust_material_shadow_history"]

        def misalign_history_lengths(world: dict) -> None:
            world["plate_motion_history"].append(
                deepcopy(world["plate_motion_history"][1])
            )

        def nonpositive_cell_area(world: dict) -> None:
            _set_field(world["cells"][0], "area_km2", 0.0)

        def no_plate_snapshots(world: dict) -> None:
            for step in world["plate_motion_history"]:
                _set_field(step, "plates", [])

        def drop_summary(world: dict) -> None:
            del world["summary"]

        self._run_cases(
            (
                (
                    "missing_history",
                    drop_history,
                    "crust material shadow model or aligned histories are missing",
                ),
                (
                    "history_length_mismatch",
                    misalign_history_lengths,
                    "crust material shadow model or aligned histories are missing",
                ),
                (
                    "nonpositive_cell_area",
                    nonpositive_cell_area,
                    "crust material shadow geometry is invalid",
                ),
                (
                    "no_plate_snapshots",
                    no_plate_snapshots,
                    "crust material shadow geometry is invalid",
                ),
                (
                    "missing_summary",
                    drop_summary,
                    "crust material shadow summary mirrors do not replay",
                ),
            )
        )

    def test_malformed_records_and_packet_tables_are_reported(self) -> None:
        def record_is_not_a_dict(world: dict) -> None:
            _set_field(world["crust_material_shadow_history"], 1, [])

        def record_has_an_extra_key(world: dict) -> None:
            world["crust_material_shadow_history"][1]["unexpected"] = 1

        def boolean_packet_mass(world: dict) -> None:
            _set_field(
                world["crust_material_shadow_history"][1]["closing_packets"][
                    "dry_rock_mass_kg"
                ],
                0,
                True,
            )

        def packet_column_is_not_a_list(world: dict) -> None:
            table = world["crust_material_shadow_history"][1]["opening_packets"]
            _set_field(table, "cell_offsets", tuple(table["cell_offsets"]))

        def packet_offsets_do_not_close(world: dict) -> None:
            _set_field(
                world["crust_material_shadow_history"][1]["opening_packets"][
                    "cell_offsets"
                ],
                -1,
                5,
            )

        def origin_kind_out_of_range(world: dict) -> None:
            _set_field(
                world["crust_material_shadow_history"][1]["opening_packets"][
                    "origin_kind_ids"
                ],
                0,
                42,
            )

        def origin_plate_out_of_range(world: dict) -> None:
            _set_field(
                world["crust_material_shadow_history"][1]["opening_packets"][
                    "origin_plate_ids"
                ],
                0,
                7,
            )

        def adjustment_column_is_missing(world: dict) -> None:
            del world["crust_material_shadow_history"][1][
                "unresolved_sink_adjustments"
            ]["process_reason_ids"]

        def adjustment_column_is_not_a_list(world: dict) -> None:
            table = world["crust_material_shadow_history"][1][
                "unresolved_sink_adjustments"
            ]
            _set_field(
                table,
                "process_reason_ids",
                tuple(table["process_reason_ids"]),
            )

        def adjustment_offsets_do_not_close(world: dict) -> None:
            _set_field(
                world["crust_material_shadow_history"][1][
                    "unresolved_sink_adjustments"
                ]["cell_offsets"],
                -1,
                9,
            )

        def contributor_count_out_of_range(world: dict) -> None:
            _set_field(
                world["plate_motion_history"][1]["crust_overlap_ledger"][
                    "contributor_count_by_cell"
                ],
                0,
                5,
            )

        def reason_adjustment_row_is_missing(world: dict) -> None:
            world["crust_material_shadow_history"][1][
                "ordered_reason_adjustments"
            ].pop()

        schema_failure = "crust material shadow history 1 schema is invalid"
        field_failure = "crust material shadow history 1 fields are invalid"
        self._run_cases(
            (
                ("record_is_not_a_dict", record_is_not_a_dict, schema_failure),
                ("record_extra_key", record_has_an_extra_key, schema_failure),
                ("boolean_packet_mass", boolean_packet_mass, field_failure),
                (
                    "packet_column_not_a_list",
                    packet_column_is_not_a_list,
                    field_failure,
                ),
                (
                    "packet_offsets_do_not_close",
                    packet_offsets_do_not_close,
                    field_failure,
                ),
                (
                    "origin_kind_out_of_range",
                    origin_kind_out_of_range,
                    field_failure,
                ),
                (
                    "origin_plate_out_of_range",
                    origin_plate_out_of_range,
                    field_failure,
                ),
                (
                    "adjustment_column_missing",
                    adjustment_column_is_missing,
                    field_failure,
                ),
                (
                    "adjustment_column_not_a_list",
                    adjustment_column_is_not_a_list,
                    field_failure,
                ),
                (
                    "adjustment_offsets_do_not_close",
                    adjustment_offsets_do_not_close,
                    field_failure,
                ),
                (
                    "contributor_count_out_of_range",
                    contributor_count_out_of_range,
                    field_failure,
                ),
                (
                    "reason_adjustment_row_missing",
                    reason_adjustment_row_is_missing,
                    field_failure,
                ),
            )
        )

    def test_step_replay_disagreements_are_reported(self) -> None:
        def nonphysical_initial_thickness(world: dict) -> None:
            _set_field(
                world["plate_motion_history"][0]["crust_overlap_ledger"][
                    "remapped_crust_thickness_km_by_cell"
                ],
                0,
                0.0,
            )

        def initial_packets_do_not_replay(world: dict) -> None:
            table = world["crust_material_shadow_history"][0]["opening_packets"]
            _set_field(
                table,
                "dry_rock_mass_kg",
                [2.0 * table["dry_rock_mass_kg"][0]],
            )

        def transport_replay_raises(world: dict) -> None:
            _set_field(
                world["plate_motion_history"][1]["crust_overlap_ledger"][
                    "overlap_area_km2"
                ],
                0,
                -1.0,
            )

        def transported_packet_key_differs(world: dict) -> None:
            _set_field(
                world["crust_material_shadow_history"][1][
                    "transported_packets"
                ]["origin_kind_ids"],
                0,
                1,
            )

        def source_area_does_not_close(world: dict) -> None:
            _set_field(
                world["plate_motion_history"][1]["crust_overlap_ledger"][
                    "overlap_area_km2"
                ],
                0,
                2.0,
            )

        def source_and_sink_share_a_reason(world: dict) -> None:
            table = world["crust_material_shadow_history"][1][
                "unresolved_sink_adjustments"
            ]
            _set_field(table, "process_reason_ids", [0, 0])

        def two_source_records_for_one_reason(world: dict) -> None:
            world["plate_motion_history"][1]["plates"].append({"plate_id": 1})
            table = world["crust_material_shadow_history"][1][
                "unresolved_source_adjustments"
            ]
            table["origin_kind_ids"].append(UNRESOLVED_ORIGIN_KIND_ID)
            table["origin_plate_ids"].append(1)
            table["origin_reason_ids"].append(0)
            table["process_reason_ids"].append(0)
            table["dry_rock_mass_kg"].append(1.0e6)
            table["cell_offsets"][-1] += 1

        def source_record_names_another_plate(world: dict) -> None:
            world["plate_motion_history"][1]["plates"].append({"plate_id": 1})
            _set_field(
                world["crust_material_shadow_history"][1][
                    "unresolved_source_adjustments"
                ]["origin_plate_ids"],
                0,
                1,
            )

        def sink_exceeds_available_mass(world: dict) -> None:
            table = world["crust_material_shadow_history"][1][
                "unresolved_sink_adjustments"
            ]
            _set_field(
                table,
                "dry_rock_mass_kg",
                [value + 1.0e14 for value in table["dry_rock_mass_kg"]],
            )

        def nonfinite_final_scalar(world: dict) -> None:
            _set_field(
                world["plate_motion_history"][1]["crust_overlap_ledger"][
                    "remapped_crust_thickness_km_by_cell"
                ],
                0,
                1.0e300,
            )

        def final_scalar_residual(world: dict) -> None:
            _set_field(
                world["plate_motion_history"][1]["crust_overlap_ledger"][
                    "remapped_crust_thickness_km_by_cell"
                ],
                0,
                11.0,
            )

        # The four ordered-adjustment conditions below share one subsystem
        # verdict, so the case name records which condition each tamper hits.
        ordered_failure = (
            "crust material shadow ordered adjustments failed at step 1"
        )
        self._run_cases(
            (
                (
                    "nonphysical_initial_thickness",
                    nonphysical_initial_thickness,
                    "initial crust material shadow state is invalid",
                ),
                (
                    "initial_packets_do_not_replay",
                    initial_packets_do_not_replay,
                    "initial crust material shadow packets do not replay",
                ),
                (
                    "transport_replay_raises",
                    transport_replay_raises,
                    "crust material shadow transport replay failed at step 1",
                ),
                (
                    "transported_packet_key_differs",
                    transported_packet_key_differs,
                    "crust material shadow transported packets differ at step 1",
                ),
                (
                    "source_area_does_not_close",
                    source_area_does_not_close,
                    "crust material shadow source-area closure failed at "
                    "step 1, source 0",
                ),
                (
                    "source_and_sink_share_a_reason",
                    source_and_sink_share_a_reason,
                    ordered_failure,
                ),
                (
                    "two_source_records_for_one_reason",
                    two_source_records_for_one_reason,
                    ordered_failure,
                ),
                (
                    "source_record_names_another_plate",
                    source_record_names_another_plate,
                    ordered_failure,
                ),
                (
                    "sink_exceeds_available_mass",
                    sink_exceeds_available_mass,
                    ordered_failure,
                ),
                (
                    "nonfinite_final_scalar",
                    nonfinite_final_scalar,
                    "crust material shadow final scalar is nonfinite at "
                    "step 1, cell 0",
                ),
                (
                    "final_scalar_residual",
                    final_scalar_residual,
                    "crust material shadow final scalar failed at step 1, cell 0",
                ),
            )
        )

    def test_serialized_mirror_disagreements_are_reported(self) -> None:
        def nonfinite_global_scalar(world: dict) -> None:
            _set_field(
                world["crust_material_shadow_history"][1],
                "global_closing_mass_kg",
                math.nan,
            )

        def stale_packet_count(world: dict) -> None:
            record = world["crust_material_shadow_history"][1]
            _set_field(
                record,
                "closing_packet_count",
                record["closing_packet_count"] + 1,
            )

        def reason_record_has_an_extra_key(world: dict) -> None:
            world["crust_material_shadow_history"][1][
                "ordered_reason_adjustments"
            ][0]["unexpected"] = 1

        def process_reason_delta_overflows(world: dict) -> None:
            _set_field(
                world["plate_motion_history"][1]["crust_overlap_ledger"][
                    "process_inventory_attribution"
                ]["reasons"][0]["net_delta"],
                "density_weighted_crust_volume",
                1.0e300,
            )

        def changed_cell_count_out_of_range(world: dict) -> None:
            reason = world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"][0]
            self.assertNotIn("extensive_state_changed_cell_count", reason)
            reason["extensive_state_changed_cell_count"] = 7

        reason_failure = "crust material shadow reason record 0 is invalid"
        self._run_cases(
            (
                (
                    "nonfinite_global_scalar",
                    nonfinite_global_scalar,
                    "crust material shadow scalar global_closing_mass_kg is invalid",
                ),
                (
                    "stale_packet_count",
                    stale_packet_count,
                    "crust material shadow packet counts failed at step 1",
                ),
                (
                    "reason_record_extra_key",
                    reason_record_has_an_extra_key,
                    reason_failure,
                ),
                (
                    "process_reason_delta_overflows",
                    process_reason_delta_overflows,
                    reason_failure,
                ),
                (
                    "changed_cell_count_out_of_range",
                    changed_cell_count_out_of_range,
                    reason_failure,
                ),
            )
        )

    def test_ill_conditioned_source_geometry_fails_closed_on_tolerance(
        self,
    ) -> None:
        """The composite final-scalar tolerance is reported, not swallowed.

        ``source_geometry_relative_error`` is bounded by ``closure_error /
        source_area``, and the closure guard only requires an absolute error
        under ``1e-6``.  A cell whose area is far below that floor therefore
        passes closure with a relative error near ``1e293``, and the tolerance
        term ``4 * relative_error * (1 + local_mass_terms)`` overflows as soon
        as the cell's scalar mass is large.  The validator must turn that into
        a failure rather than an unbounded (fail-open) tolerance.
        """

        # Same geometry, benign step-1 scalar state: still a clean replay, so
        # the failure below is attributable to the mass scale alone.
        control = _sequential_world(
            mass_neutral_state_change=True,
            area_km2=1.0e-300,
            overlap_area_km2=1.0e-7,
        )
        control_result = validate_crust_material_shadow(control)
        self.assertTrue(control_result["passed"], control_result["failures"])

        world = _sequential_world(
            mass_neutral_state_change=True,
            area_km2=1.0e-300,
            overlap_area_km2=1.0e-7,
            second_thickness_km=1.0e300,
            second_density=1.0e8,
        )
        ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
        self.assertNotEqual(
            ledger["remapped_crust_thickness_km_by_cell"],
            control["plate_motion_history"][1]["crust_overlap_ledger"][
                "remapped_crust_thickness_km_by_cell"
            ],
        )
        # The scalar mass itself stays finite; only the tolerance overflows.
        self.assertTrue(
            math.isfinite(
                world["crust_material_shadow_history"][1][
                    "closing_scalar_mass_kg"
                ]
            )
        )
        result = validate_crust_material_shadow(world)
        self.assertFalse(result["passed"], result)
        self.assertEqual(result["failures"], [
            "crust material shadow final scalar tolerance is invalid at "
            "step 1, cell 0"
        ])


class CrustMaterialShadowTableParserTests(TestCase):
    """Per-check discrimination behind one aggregated subsystem verdict.

    ``validate_crust_material_shadow`` collapses every packet- and
    adjustment-table guard into ``history N fields are invalid``, so these
    cases drive the private parsers that raise underneath it and pin the
    individual message.  The aggregate verdict alone cannot tell a schema
    error from a shape error from a non-canonical key.
    """

    @classmethod
    def setUpClass(cls) -> None:
        record = _sequential_world()["crust_material_shadow_history"][1]
        cls.packets = record["closing_packets"]
        cls.adjustments = record["unresolved_sink_adjustments"]

    def _snapshot(self, table: dict) -> list[dict[PacketKey, float]]:
        return _snapshot_cells(
            table, cell_count=1, plate_count=1, field="closing_packets"
        )

    def _adjustment(self, table: dict) -> list[list[Any]]:
        return _adjustment_cells(
            table,
            cell_count=1,
            plate_count=1,
            field="unresolved_sink_adjustments",
            source=False,
        )

    def test_untampered_tables_parse_as_the_control(self) -> None:
        self.assertEqual(
            self._snapshot(deepcopy(self.packets)),
            [{PacketKey(0, 0, -1): 2.25e13, PacketKey(9, 0, 0): 4.5e12}],
        )
        self.assertEqual(len(self._adjustment(deepcopy(self.adjustments))[0]), 2)

    def test_each_packet_table_guard_reports_its_own_message(self) -> None:
        def extra_column(table: dict) -> None:
            table["unexpected"] = []

        def column_is_a_tuple(table: dict) -> None:
            _set_field(table, "cell_offsets", tuple(table["cell_offsets"]))

        def boolean_mass(table: dict) -> None:
            _set_field(table["dry_rock_mass_kg"], 0, True)

        def offsets_do_not_close(table: dict) -> None:
            _set_field(table["cell_offsets"], -1, 5)

        def origin_kind_out_of_range(table: dict) -> None:
            _set_field(table["origin_kind_ids"], 0, 42)

        cases = (
            (
                "extra_column",
                extra_column,
                TypeError,
                "closing_packets has an invalid schema",
            ),
            (
                "column_is_a_tuple",
                column_is_a_tuple,
                TypeError,
                "closing_packets arrays must be lists",
            ),
            (
                "boolean_mass",
                boolean_mass,
                TypeError,
                r"closing_packets\.dry_rock_mass_kg must be numeric",
            ),
            (
                "offsets_do_not_close",
                offsets_do_not_close,
                ValueError,
                "closing_packets has an invalid sparse shape",
            ),
            (
                "origin_kind_out_of_range",
                origin_kind_out_of_range,
                ValueError,
                "closing_packets packet keys or masses are not canonical",
            ),
        )
        for name, mutate, exception, message in cases:
            with self.subTest(case=name):
                table = deepcopy(self.packets)
                mutate(table)
                self.assertNotEqual(table, self.packets, "tamper changed nothing")
                with self.assertRaisesRegex(exception, message):
                    self._snapshot(table)

    def test_each_adjustment_table_guard_reports_its_own_message(self) -> None:
        def missing_column(table: dict) -> None:
            del table["process_reason_ids"]

        def column_is_a_tuple(table: dict) -> None:
            _set_field(
                table, "process_reason_ids", tuple(table["process_reason_ids"])
            )

        def offsets_do_not_close(table: dict) -> None:
            _set_field(table["cell_offsets"], -1, 9)

        def process_reason_out_of_range(table: dict) -> None:
            _set_field(table["process_reason_ids"], 0, 99)

        cases = (
            (
                "missing_column",
                missing_column,
                TypeError,
                "unresolved_sink_adjustments has an invalid schema",
            ),
            (
                "column_is_a_tuple",
                column_is_a_tuple,
                TypeError,
                "unresolved_sink_adjustments arrays must be lists",
            ),
            (
                "offsets_do_not_close",
                offsets_do_not_close,
                ValueError,
                "unresolved_sink_adjustments has an invalid sparse shape",
            ),
            (
                "process_reason_out_of_range",
                process_reason_out_of_range,
                ValueError,
                "unresolved_sink_adjustments adjustment keys or masses are "
                "not canonical",
            ),
        )
        for name, mutate, exception, message in cases:
            with self.subTest(case=name):
                table = deepcopy(self.adjustments)
                mutate(table)
                self.assertNotEqual(
                    table, self.adjustments, "tamper changed nothing"
                )
                with self.assertRaisesRegex(exception, message):
                    self._adjustment(table)
