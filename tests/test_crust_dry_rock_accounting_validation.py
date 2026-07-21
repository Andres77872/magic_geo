from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from magic_geo.config import WorldConfig, config_to_native, load_config
from magic_geo.crust_dry_rock_accounting_validation import (
    MODEL_LITERAL_VALUES,
    MAX_LIVE_RESERVOIR_PACKETS,
    MAX_PROXY_TRANSFERS_PER_STEP,
    MAX_SURFACE_PACKETS_PER_OWNER,
    PacketKey,
    replay_crust_dry_rock_accounting_step,
    validate_crust_dry_rock_accounting,
)
from magic_geo.crust_process_validation import CRUST_PROCESS_REASON_ORDER
from magic_geo.native import generate_geo_world


def _config(
    *,
    threads: int = 1,
    radius_km: float = 6371.0,
    mesh_backend: str = "geodesic_icosahedron",
    cell_count: int = 162,
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


def _zero_requests(cell_count: int) -> list[list[float]]:
    return [[0.0] * cell_count for _ in CRUST_PROCESS_REASON_ORDER]


class CrustDryRockReplayUnitTests(TestCase):
    def test_exact_exhaustion_then_later_reseed_is_explicit(self) -> None:
        surface_key = PacketKey(0, 0, 0)
        exchange_key = PacketKey(1, -1, -1)
        source = _zero_requests(1)
        sink = _zero_requests(1)
        sink[2][0] = 100.0
        source[3][0] = 25.0

        replay = replay_crust_dry_rock_accounting_step(
            opening_surface_packets=[{surface_key: 100.0}],
            opening_upper_mantle_packets={exchange_key: 10.0},
            opening_subducted_slab_packets=[{}],
            destination_offsets=[0, 1],
            source_cell_ids=[0],
            overlap_area_km2=[1.0],
            source_requests_kg_by_reason_cell=source,
            sink_requests_kg_by_reason_cell=sink,
        )

        self.assertEqual(
            replay["closing_surface_packets"],
            [{exchange_key: 10.0, surface_key: 15.0}],
        )
        self.assertEqual(
            [(item.process_reason_id, item.source_reservoir_id,
              item.destination_reservoir_id, item.key,
              item.dry_rock_mass_kg) for item in replay["transfers"]],
            [
                (2, 0, 1, surface_key, 100.0),
                (3, 1, 0, surface_key, 15.0),
                (3, 1, 0, exchange_key, 10.0),
            ],
        )
        self.assertEqual(
            replay["closing_upper_mantle_packets"],
            {surface_key: 85.0},
        )

    def test_mantle_withdrawal_is_reserve_first_then_largest_low_key(self) -> None:
        exchange = PacketKey(1, -1, -1)
        low = PacketKey(0, 0, 0)
        high = PacketKey(0, 1, 0)
        source = _zero_requests(1)
        source[2][0] = 35.0
        replay = replay_crust_dry_rock_accounting_step(
            opening_surface_packets=[{low: 1.0}],
            opening_upper_mantle_packets={low: 20.0, high: 20.0, exchange: 5.0},
            opening_subducted_slab_packets=[{}],
            destination_offsets=[0, 1],
            source_cell_ids=[0],
            overlap_area_km2=[1.0],
            source_requests_kg_by_reason_cell=source,
            sink_requests_kg_by_reason_cell=_zero_requests(1),
        )
        source_transfers = replay["transfers"]
        # Native normalizes the withdrawal before append, so transfer rows are
        # origin-key sorted even though the exchange-origin packet was selected first.
        self.assertEqual([item.key for item in source_transfers], [low, high, exchange])
        self.assertEqual(
            [item.dry_rock_mass_kg for item in source_transfers],
            [20.0, 10.0, 5.0],
        )

    def test_insufficient_exchange_fails_without_mutating_inputs(self) -> None:
        key = PacketKey(0, 0, 0)
        surface = [{key: 10.0}]
        mantle = {PacketKey(1, -1, -1): 2.0}
        source = _zero_requests(1)
        source[2][0] = 3.0
        with self.assertRaisesRegex(ValueError, "reserve exhausted"):
            replay_crust_dry_rock_accounting_step(
                opening_surface_packets=surface,
                opening_upper_mantle_packets=mantle,
                opening_subducted_slab_packets=[{}],
                destination_offsets=[0, 1],
                source_cell_ids=[0],
                overlap_area_km2=[1.0],
                source_requests_kg_by_reason_cell=source,
                sink_requests_kg_by_reason_cell=_zero_requests(1),
            )
        self.assertEqual(surface, [{key: 10.0}])
        self.assertEqual(mantle, {PacketKey(1, -1, -1): 2.0})

    def test_operational_caps_fail_closed_without_mutating_inputs(self) -> None:
        low = PacketKey(0, 0, 0)
        high = PacketKey(0, 1, 0)
        surface = [{low: 10.0, high: 5.0}]
        mantle = {PacketKey(1, -1, -1): 2.0}
        common = {
            "opening_surface_packets": surface,
            "opening_upper_mantle_packets": mantle,
            "opening_subducted_slab_packets": [{}],
            "destination_offsets": [0, 1],
            "source_cell_ids": [0],
            "overlap_area_km2": [1.0],
            "source_requests_kg_by_reason_cell": _zero_requests(1),
            "sink_requests_kg_by_reason_cell": _zero_requests(1),
        }
        with patch(
            "magic_geo.crust_dry_rock_accounting_validation."
            "MAX_SURFACE_PACKETS_PER_OWNER",
            1,
        ):
            with self.assertRaisesRegex(ValueError, "surface owner|surface-owner"):
                replay_crust_dry_rock_accounting_step(**common)
        with patch(
            "magic_geo.crust_dry_rock_accounting_validation."
            "MAX_LIVE_RESERVOIR_PACKETS",
            2,
        ):
            with self.assertRaisesRegex(ValueError, "live reservoir"):
                replay_crust_dry_rock_accounting_step(**common)

        # Opening live state is exactly at the patched cap (two surface
        # packets plus one mantle packet), but normalized two-way mixing would
        # create four surface keys.  The transport check must reserve the
        # mantle packet's headroom on every insertion, not discover it only
        # after the transported surface has already been allocated.
        mixing_case = {
            "opening_surface_packets": [{low: 10.0}, {high: 5.0}],
            "opening_upper_mantle_packets": {PacketKey(1, -1, -1): 2.0},
            "opening_subducted_slab_packets": [{}],
            "destination_offsets": [0, 2, 4],
            "source_cell_ids": [0, 1, 0, 1],
            "overlap_area_km2": [0.5, 0.5, 0.5, 0.5],
            "source_requests_kg_by_reason_cell": _zero_requests(2),
            "sink_requests_kg_by_reason_cell": _zero_requests(2),
        }
        with patch(
            "magic_geo.crust_dry_rock_accounting_validation."
            "MAX_LIVE_RESERVOIR_PACKETS",
            3,
        ):
            with self.assertRaisesRegex(ValueError, "live reservoir"):
                replay_crust_dry_rock_accounting_step(**mixing_case)

        source = _zero_requests(1)
        source[2][0] = 3.0
        transfer_case = dict(common)
        transfer_case["opening_surface_packets"] = [{low: 10.0}]
        transfer_case["opening_upper_mantle_packets"] = {
            high: 2.0,
            PacketKey(1, -1, -1): 1.0,
        }
        transfer_case["source_requests_kg_by_reason_cell"] = source
        with patch(
            "magic_geo.crust_dry_rock_accounting_validation."
            "MAX_PROXY_TRANSFERS_PER_STEP",
            1,
        ):
            with self.assertRaisesRegex(ValueError, "transfer safety limit"):
                replay_crust_dry_rock_accounting_step(**transfer_case)
        self.assertEqual(surface, [{low: 10.0, high: 5.0}])
        self.assertEqual(mantle, {PacketKey(1, -1, -1): 2.0})


class CrustDryRockGeneratedValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.serial = generate_geo_world(config_to_native(_config(threads=1)))
        cls.parallel = generate_geo_world(config_to_native(_config(threads=4)))

    def test_generated_history_replays_with_strict_nonphysical_metadata(self) -> None:
        result = validate_crust_dry_rock_accounting(self.serial)
        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(
            self.serial["crust_dry_rock_accounting_model"],
            MODEL_LITERAL_VALUES,
        )
        model = self.serial["crust_dry_rock_accounting_model"]
        self.assertEqual(
            model["maximum_surface_packets_per_owner"],
            MAX_SURFACE_PACKETS_PER_OWNER,
        )
        self.assertEqual(
            model["maximum_live_reservoir_packets"],
            MAX_LIVE_RESERVOIR_PACKETS,
        )
        self.assertEqual(
            model["maximum_proxy_transfers_per_step"],
            MAX_PROXY_TRANSFERS_PER_STEP,
        )
        self.assertFalse(
            model["operational_safety_limits_are_physical_flux_limits"]
        )
        self.assertTrue(
            MODEL_LITERAL_VALUES["instantaneous_global_mantle_mixing_assumed"]
        )
        self.assertFalse(
            MODEL_LITERAL_VALUES["mantle_origin_packets_homogenized"]
        )
        self.assertFalse(
            MODEL_LITERAL_VALUES["mantle_spatial_transport_resolved"]
        )
        history = self.serial["crust_dry_rock_accounting_history"]
        self.assertTrue(history)
        for record in history:
            self.assertEqual(
                record["opening_subducted_slab_packets"]["owner_offsets"],
                [0] * (record["plate_count"] + 1),
            )
            self.assertEqual(
                record["closing_subducted_slab_packets"]["owner_offsets"],
                [0] * (record["plate_count"] + 1),
            )
            self.assertTrue(
                all(
                    transaction["physical_source_sink_resolved"] is False
                    for transaction in record["ordered_reason_transactions"]
                )
            )

    def test_thread_count_is_bit_identical(self) -> None:
        for world in (self.serial, self.parallel):
            replay = validate_crust_dry_rock_accounting(world)
            self.assertTrue(replay["passed"], replay["failures"])
        self.assertEqual(
            self.serial["crust_dry_rock_accounting_history"],
            self.parallel["crust_dry_rock_accounting_history"],
        )

    def test_coherent_and_malformed_mutations_are_rejected(self) -> None:
        base = self.serial

        def physical_claim(world: dict) -> None:
            world["crust_dry_rock_accounting_model"][
                "upper_mantle_exchange_reservoir_resolved"
            ] = True

        def break_exact_opening_link(world: dict) -> None:
            record = world["crust_dry_rock_accounting_history"][1]
            record["opening_surface_packets"]["dry_rock_mass_kg"][0] += 1.0e12

        def corrupt_bool_column(world: dict) -> None:
            transfers = world["crust_dry_rock_accounting_history"][1][
                "proxy_compensation_transfers"
            ]
            self.assertTrue(transfers["physical_basis_resolved"])
            transfers["physical_basis_resolved"][0] = 0

        def coherent_origin_redistribution(world: dict) -> None:
            table = world["crust_dry_rock_accounting_history"][-1][
                "closing_surface_packets"
            ]
            offsets = table["owner_offsets"]
            pair: tuple[int, int] | None = None
            for cell in range(len(offsets) - 1):
                if offsets[cell + 1] - offsets[cell] >= 2:
                    pair = (offsets[cell], offsets[cell] + 1)
                    break
            self.assertIsNotNone(pair)
            first, second = pair or (0, 1)
            shift = min(table["dry_rock_mass_kg"][second] * 0.01, 1.0e14)
            table["dry_rock_mass_kg"][first] += shift
            table["dry_rock_mass_kg"][second] -= shift

        def coherent_initial_shadow_accounting_key(world: dict) -> None:
            shadow = world["crust_material_shadow_history"][0]
            accounting = world["crust_dry_rock_accounting_history"][0]
            original = shadow["opening_packets"]["origin_kind_ids"][0]
            replacement = (original + 1) % 9
            for table_name in (
                "opening_packets", "transported_packets", "closing_packets",
            ):
                shadow[table_name]["origin_kind_ids"][0] = replacement
            for table_name in (
                "opening_surface_packets", "transported_surface_packets",
                "closing_surface_packets",
            ):
                accounting[table_name]["origin_kind_ids"][0] = replacement

        def corrupt_area_mirror(world: dict) -> None:
            world["crust_dry_rock_accounting_history"][0][
                "total_control_volume_area_km2"
            ] += 1.0

        def replace_numeric_with_string(world: dict) -> None:
            record = world["crust_dry_rock_accounting_history"][0]
            record["surface_state_envelope_capacity_kg"] = str(
                record["surface_state_envelope_capacity_kg"]
            )

        def inflate_cell_scalar_residual(world: dict) -> None:
            record = world["crust_dry_rock_accounting_history"][1]
            record[
                "maximum_absolute_cell_closing_scalar_mass_residual_kg"
            ] = abs(record["closing_scalar_mass_kg"]) * 1.0e-6 + 1.0

        def reorder_transfer_rows_preserving_all_totals(world: dict) -> None:
            table = world["crust_dry_rock_accounting_history"][1][
                "proxy_compensation_transfers"
            ]
            self.assertGreaterEqual(len(table["sequence_ids"]), 2)
            for field, values in table.items():
                if field != "sequence_ids":
                    values[0], values[1] = values[1], values[0]

        def corrupt_age_only_request(world: dict) -> None:
            transaction = world["crust_dry_rock_accounting_history"][1][
                "ordered_reason_transactions"
            ][0]
            transaction["requested_surface_source_mass_kg"] = 1.0e15

        def corrupt_summary(world: dict) -> None:
            world["summary"]["total_crust_dry_rock_proxy_transfer_count"] += 1

        def corrupt_model_cap(world: dict) -> None:
            world["crust_dry_rock_accounting_model"][
                "maximum_surface_packets_per_owner"
            ] += 1

        def restore_retired_proxy_mechanism(world: dict) -> None:
            world["crust_dry_rock_accounting_model"][
                "proxy_transfer_mechanism"
            ] = "legacy_rule_mass_compensation_v1"

        def corrupt_peak_telemetry_coherently(world: dict) -> None:
            record = world["crust_dry_rock_accounting_history"][1]
            record["maximum_surface_packet_count_per_owner"] = (
                MAX_SURFACE_PACKETS_PER_OWNER + 1
            )
            world["summary"][
                "maximum_crust_dry_rock_surface_packet_count_per_owner"
            ] = MAX_SURFACE_PACKETS_PER_OWNER + 1

        def corrupt_dimensionless_summary(world: dict) -> None:
            world["summary"][
                "maximum_crust_dry_rock_closing_scalar_relative_residual"
            ] = 1.0e-6

        mutations = {
            "physical_claim": physical_claim,
            "opening_link": break_exact_opening_link,
            "bool_not_json_bool": corrupt_bool_column,
            "coherent_origin_redistribution": coherent_origin_redistribution,
            "coherent_initial_key": coherent_initial_shadow_accounting_key,
            "area_mirror": corrupt_area_mirror,
            "numeric_string": replace_numeric_with_string,
            "cell_scalar_residual": inflate_cell_scalar_residual,
            "transfer_order": reorder_transfer_rows_preserving_all_totals,
            "age_only_request": corrupt_age_only_request,
            "summary": corrupt_summary,
            "model_cap": corrupt_model_cap,
            "retired_proxy_mechanism": restore_retired_proxy_mechanism,
            "coherent_peak_cap": corrupt_peak_telemetry_coherently,
            "dimensionless_summary": corrupt_dimensionless_summary,
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                world = deepcopy(base)
                mutation(world)
                result = validate_crust_dry_rock_accounting(world)
                self.assertFalse(result["passed"], result)

    def test_capacity_and_every_packet_mass_scale_with_radius_squared(self) -> None:
        small = generate_geo_world(
            config_to_native(_config(radius_km=3200.0, threads=1))
        )
        large = generate_geo_world(
            config_to_native(_config(radius_km=6400.0, threads=1))
        )
        for world in (small, large):
            replay = validate_crust_dry_rock_accounting(world)
            self.assertTrue(replay["passed"], replay["failures"])
        for small_record, large_record in zip(
            small["crust_dry_rock_accounting_history"],
            large["crust_dry_rock_accounting_history"],
            strict=True,
        ):
            self.assertTrue(math.isclose(
                large_record["surface_state_envelope_capacity_kg"],
                4.0 * small_record["surface_state_envelope_capacity_kg"],
                rel_tol=2.0e-12,
                abs_tol=128.0 * math.ulp(
                    large_record["surface_state_envelope_capacity_kg"]
                ),
            ))
            for table_name in (
                "opening_surface_packets", "transported_surface_packets",
                "closing_surface_packets", "opening_upper_mantle_packets",
                "closing_upper_mantle_packets",
            ):
                small_table = small_record[table_name]
                large_table = large_record[table_name]
                for key in (
                    "owner_offsets", "origin_domain_ids", "origin_kind_ids",
                    "origin_plate_ids",
                ):
                    self.assertEqual(small_table[key], large_table[key])
                for small_mass, large_mass in zip(
                    small_table["dry_rock_mass_kg"],
                    large_table["dry_rock_mass_kg"],
                    strict=True,
                ):
                    self.assertTrue(math.isclose(
                        large_mass, 4.0 * small_mass, rel_tol=2.0e-12,
                        abs_tol=max(1.0e-3, 128.0 * math.ulp(large_mass)),
                    ))

    def test_180_degree_full_gap_reseeds_accounting_surface(self) -> None:
        cases = (("fibonacci_sphere", 128), ("geodesic_icosahedron", 162))
        for backend, cell_count in cases:
            with self.subTest(backend=backend):
                world = generate_geo_world(config_to_native(_config(
                    mesh_backend=backend,
                    cell_count=cell_count,
                    extreme_rotation=True,
                )))
                replay = validate_crust_dry_rock_accounting(world)
                self.assertTrue(replay["passed"], replay["failures"])
                shadow = world["crust_material_shadow_history"][1]
                accounting = world["crust_dry_rock_accounting_history"][1]
                transported = accounting["transported_surface_packets"][
                    "owner_offsets"
                ]
                closing = accounting["closing_surface_packets"]["owner_offsets"]
                shadow_transported = shadow["transported_packets"]["cell_offsets"]
                empty = [
                    cell for cell in range(len(world["cells"]))
                    if shadow_transported[cell] == shadow_transported[cell + 1]
                ]
                self.assertTrue(empty)
                self.assertTrue(all(
                    transported[cell] == transported[cell + 1]
                    and closing[cell] < closing[cell + 1]
                    for cell in empty
                ))
