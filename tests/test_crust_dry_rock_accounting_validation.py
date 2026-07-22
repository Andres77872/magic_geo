from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from magic_geo.config import WorldConfig, config_to_native, load_config
from magic_geo.crust_dry_rock_accounting_validation import (
    MASS_FACTOR_KG,
    MODEL_LITERAL_VALUES,
    MAX_LIVE_RESERVOIR_PACKETS,
    MAX_PROXY_TRANSFERS_PER_STEP,
    MAX_SURFACE_PACKETS_PER_OWNER,
    PacketKey,
    replay_crust_dry_rock_accounting_step,
    validate_crust_dry_rock_accounting,
)
from magic_geo.crust_process_validation import (
    CRUST_PROCESS_REASON_ORDER,
    replay_ordered_crust_process,
    validate_crust_process_reason_ledger,
)
from magic_geo.native import generate_geo_world
from support import worlds

#: Smallest canonical world whose accounting and process ledgers are non-empty.
WORLD_KEY = "replay_128"

_ACCOUNTING_MODULE = "magic_geo.crust_dry_rock_accounting_validation"


def _swap(container: object, key: object, value: object) -> object:
    """Overwrite one field, proving the write is not a silent no-op.

    A tamper that happens to write back the value the generator already
    produced would leave the test inert, so every tamper goes through here.
    """

    previous = container[key]  # type: ignore[index]
    if type(previous) is type(value) and previous == value:
        raise AssertionError(f"tamper on {key!r} is a no-op: {previous!r}")
    container[key] = value  # type: ignore[index]
    return previous


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


class CrustDryRockStepFailClosedTests(TestCase):
    """Fail-closed branches of the public step replay, on synthetic inputs."""

    def _payload(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "opening_surface_packets": [{PacketKey(0, 0, 0): 10.0}],
            "opening_upper_mantle_packets": {PacketKey(1, -1, -1): 5.0},
            "opening_subducted_slab_packets": [{}],
            "destination_offsets": [0, 1],
            "source_cell_ids": [0],
            "overlap_area_km2": [1.0],
            "source_requests_kg_by_reason_cell": _zero_requests(1),
            "sink_requests_kg_by_reason_cell": _zero_requests(1),
        }
        payload.update(overrides)
        return payload

    def _request(
        self, cell_count: int, reason: int, cell: int, mass: float
    ) -> list[list[float]]:
        requests = _zero_requests(cell_count)
        requests[reason][cell] = mass
        return requests

    def test_healthy_synthetic_step_replays_cleanly(self) -> None:
        # Control for every malformed case below: the same shape, untampered,
        # replays without raising and conserves the opening inventory.
        replay = replay_crust_dry_rock_accounting_step(**self._payload())
        self.assertEqual(
            replay["closing_surface_packets"], [{PacketKey(0, 0, 0): 10.0}]
        )
        self.assertEqual(
            replay["closing_upper_mantle_packets"], {PacketKey(1, -1, -1): 5.0}
        )
        self.assertEqual(replay["transfers"], [])

    def test_malformed_request_matrices_and_transport_csr_fail_closed(self) -> None:
        two_cell = {
            "opening_surface_packets": [
                {PacketKey(0, 0, 0): 1.0}, {PacketKey(0, 1, 0): 1.0},
            ],
            "source_requests_kg_by_reason_cell": _zero_requests(2),
            "sink_requests_kg_by_reason_cell": _zero_requests(2),
        }
        cases = {
            "reason_row_count": (
                {"source_requests_kg_by_reason_cell": [[0.0]]},
                "one request row is required for every process reason",
            ),
            "row_width": (
                {"sink_requests_kg_by_reason_cell": [
                    [0.0, 0.0] for _ in CRUST_PROCESS_REASON_ORDER
                ]},
                "request matrix is invalid",
            ),
            "negative_request": (
                {"sink_requests_kg_by_reason_cell": self._request(1, 2, 0, -1.0)},
                "request matrix is invalid",
            ),
            "both_signs": (
                {
                    "source_requests_kg_by_reason_cell": self._request(1, 2, 0, 1.0),
                    "sink_requests_kg_by_reason_cell": self._request(1, 2, 0, 1.0),
                },
                "a cell/reason cannot request both signs",
            ),
            "nonpositive_overlap_area": (
                {"overlap_area_km2": [-1.0]},
                "transport CSR is invalid",
            ),
            "unsorted_csr_row": (
                {
                    **two_cell,
                    "destination_offsets": [0, 2, 3],
                    "source_cell_ids": [1, 0, 1],
                    "overlap_area_km2": [1.0, 1.0, 1.0],
                },
                "transport CSR rows are not canonical",
            ),
            "orphan_source_cell": (
                {
                    **two_cell,
                    "destination_offsets": [0, 1, 2],
                    "source_cell_ids": [0, 0],
                    "overlap_area_km2": [1.0, 1.0],
                },
                "a source cell has no outgoing overlap",
            ),
            "transport_accumulation_overflow": (
                {
                    "opening_surface_packets": [
                        {PacketKey(0, 0, 0): 1.7e308},
                        {PacketKey(0, 0, 0): 1.7e308},
                    ],
                    "source_requests_kg_by_reason_cell": _zero_requests(2),
                    "sink_requests_kg_by_reason_cell": _zero_requests(2),
                    "destination_offsets": [0, 2, 3],
                    "source_cell_ids": [0, 1, 1],
                    "overlap_area_km2": [1.0, 1.0, 1.0],
                },
                "transport packet accumulation overflowed",
            ),
        }
        for name, (overrides, message) in cases.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, message):
                    replay_crust_dry_rock_accounting_step(**self._payload(**overrides))

    def test_surface_sink_withdrawal_boundaries(self) -> None:
        with self.subTest(case="empty_owner"):
            with self.assertRaisesRegex(
                ValueError, "invalid or unavailable surface withdrawal"
            ):
                replay_crust_dry_rock_accounting_step(**self._payload(
                    opening_surface_packets=[{}],
                    sink_requests_kg_by_reason_cell=self._request(1, 2, 0, 1.0),
                ))

        with self.subTest(case="request_far_above_available"):
            with self.assertRaisesRegex(
                ValueError, "surface withdrawal exceeds available mass"
            ):
                replay_crust_dry_rock_accounting_step(**self._payload(
                    sink_requests_kg_by_reason_cell=self._request(1, 2, 0, 100.0),
                ))

        with self.subTest(case="request_above_available_within_bound"):
            # A request that overshoots the owner by less than the forward-error
            # bound is fulfilled to exactly the available mass, never beyond it.
            replay = replay_crust_dry_rock_accounting_step(**self._payload(
                sink_requests_kg_by_reason_cell=self._request(
                    1, 2, 0, 10.0 + 1.0e-9
                ),
            ))
            self.assertEqual(replay["fulfilled_sinks"][2], 10.0)
            self.assertEqual(replay["closing_surface_packets"], [{}])
            self.assertEqual(
                replay["closing_upper_mantle_packets"],
                {PacketKey(0, 0, 0): 10.0, PacketKey(1, -1, -1): 5.0},
            )

    def test_proportional_withdrawal_drops_an_exactly_emptied_packet(self) -> None:
        # binary64 constants chosen so the proportional share of the smaller
        # packet rounds to exactly its own mass while the request still stays
        # strictly below the owner total: the emptied packet must disappear
        # instead of surviving as a zero-mass row.
        large = 1.8839713091135475
        small = 3.969448889242061e-15
        available = math.fsum((large, small))
        request = math.nextafter(available, 0.0)
        self.assertLess(request, available)

        replay = replay_crust_dry_rock_accounting_step(**self._payload(
            opening_surface_packets=[{
                PacketKey(0, 0, 0): large, PacketKey(0, 1, 0): small,
            }],
            sink_requests_kg_by_reason_cell=self._request(1, 2, 0, request),
        ))
        closing = replay["closing_surface_packets"][0]
        self.assertNotIn(PacketKey(0, 1, 0), closing)
        self.assertEqual(
            [transfer.dry_rock_mass_kg for transfer in replay["transfers"]][1],
            small,
        )
        self.assertTrue(all(mass > 0.0 for mass in closing.values()))

    def test_ordered_mantle_withdrawal_can_exhaust_the_reserve(self) -> None:
        # "upper-mantle exchange reserve exhausted" is raised from three sites:
        # the reason-level total guard, the withdrawal entry guard and the
        # ordered per-packet drain.  Both guards compare ``requested`` against
        # ``math.fsum(mantle.values())`` with ``>``, and the assertion below
        # makes the two sides exactly equal, so neither guard can fire and the
        # raise can only come from the drain running out of packets while a
        # rounding remainder survives.
        mantle = {PacketKey(0, 0, 0): 0.1, PacketKey(0, 1, 0): 0.2}
        request = 0.1 + 0.2
        self.assertEqual(math.fsum(mantle.values()), request)
        with self.assertRaisesRegex(
            ValueError, "upper-mantle exchange reserve exhausted"
        ):
            replay_crust_dry_rock_accounting_step(**self._payload(
                opening_surface_packets=[{PacketKey(0, 2, 0): 5.0}],
                opening_upper_mantle_packets=mantle,
                source_requests_kg_by_reason_cell=self._request(1, 2, 0, request),
            ))
        self.assertEqual(
            mantle, {PacketKey(0, 0, 0): 0.1, PacketKey(0, 1, 0): 0.2}
        )

        # Discriminating control: the identical request against a reserve that
        # holds the same total in a single packet is fulfilled, so the failure
        # above came from the per-packet drain order and not from the request
        # exceeding the reserve.
        replay = replay_crust_dry_rock_accounting_step(**self._payload(
            opening_surface_packets=[{PacketKey(0, 2, 0): 5.0}],
            opening_upper_mantle_packets={PacketKey(1, -1, -1): request},
            source_requests_kg_by_reason_cell=self._request(1, 2, 0, request),
        ))
        self.assertEqual(replay["closing_upper_mantle_packets"], {})
        self.assertEqual(replay["fulfilled_sources"][2], request)

    def test_incremental_memory_caps_fail_closed_on_every_insertion_site(self) -> None:
        # Three failure strings are shared by nine raise sites, so the string
        # alone cannot name the site.  Each case therefore also pins the exact
        # cap boundary: the payload must fail at ``value`` and replay at
        # ``value + 1``, and that threshold is the packet count reached at the
        # one insertion site the payload can reach.
        sink = self._request(1, 2, 0, 5.0)
        source = self._request(1, 2, 0, 3.0)
        cases = {
            "transport_owner_cap": (
                "MAX_SURFACE_PACKETS_PER_OWNER", 1,
                {
                    "opening_surface_packets": [
                        {PacketKey(0, 0, 0): 1.0}, {PacketKey(0, 1, 0): 1.0},
                    ],
                    "source_requests_kg_by_reason_cell": _zero_requests(2),
                    "sink_requests_kg_by_reason_cell": _zero_requests(2),
                    "destination_offsets": [0, 2, 3],
                    "source_cell_ids": [0, 1, 1],
                    "overlap_area_km2": [1.0, 1.0, 1.0],
                },
                "surface-owner packet safety limit exceeded",
            ),
            "sink_merge_live_cap": (
                "MAX_LIVE_RESERVOIR_PACKETS", 2,
                {"sink_requests_kg_by_reason_cell": sink},
                "live reservoir packet safety limit exceeded",
            ),
            "sink_transfer_cap": (
                "MAX_PROXY_TRANSFERS_PER_STEP", 0,
                {"sink_requests_kg_by_reason_cell": sink},
                "per-step transfer safety limit exceeded",
            ),
            "source_merge_owner_cap": (
                "MAX_SURFACE_PACKETS_PER_OWNER", 2,
                {
                    "opening_upper_mantle_packets": {
                        PacketKey(0, 1, 0): 2.0, PacketKey(1, -1, -1): 1.0,
                    },
                    "source_requests_kg_by_reason_cell": source,
                },
                "surface-owner packet safety limit exceeded",
            ),
            "source_merge_live_cap": (
                "MAX_LIVE_RESERVOIR_PACKETS", 2,
                {"source_requests_kg_by_reason_cell": source},
                "live reservoir packet safety limit exceeded",
            ),
        }
        for name, (constant, value, overrides, message) in cases.items():
            with self.subTest(case=name):
                payload = self._payload(**overrides)
                with patch(f"{_ACCOUNTING_MODULE}.{constant}", value):
                    with self.assertRaisesRegex(ValueError, message):
                        replay_crust_dry_rock_accounting_step(**payload)
                # One unit of extra headroom is enough: the payload replays,
                # which pins the boundary to this site's packet count and
                # proves the raise came from the cap and not from the inputs.
                with patch(f"{_ACCOUNTING_MODULE}.{constant}", value + 1):
                    replay_crust_dry_rock_accounting_step(**payload)
                replay_crust_dry_rock_accounting_step(**payload)


class CrustDryRockLedgerTamperTests(TestCase):
    """Single-field tampers of a healthy generated accounting ledger.

    ``validate_crust_dry_rock_accounting`` reports one aggregated verdict per
    subsystem, so several distinct checks share a failure string.  Every case
    therefore pins the finest text the validator emits (the offending step, the
    offending table and, where present, the parser detail), and every case runs
    against the untampered control asserted in :meth:`test_control_world_passes`.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.clean = validate_crust_dry_rock_accounting(
            worlds.cached_world_readonly(WORLD_KEY)
        )

    def _assert_tamper(self, mutate, expected: str) -> None:
        self.assertEqual(self.clean["failures"], [])
        world = worlds.cached_world(WORLD_KEY)
        mutate(world)
        result = validate_crust_dry_rock_accounting(world)
        self.assertFalse(result["passed"], result["failures"])
        self.assertTrue(
            any(expected in failure for failure in result["failures"]),
            result["failures"],
        )

    def _assert_table(self, cases: dict[str, tuple[object, str]]) -> None:
        for name, (mutate, expected) in cases.items():
            with self.subTest(case=name):
                self._assert_tamper(mutate, expected)

    def test_control_world_passes(self) -> None:
        self.assertTrue(self.clean["passed"], self.clean["failures"])
        self.assertEqual(self.clean["failures"], [])
        self.assertEqual(
            self.clean["metrics"]["history_step_count"],
            len(
                worlds.cached_world_readonly(WORLD_KEY)[
                    "crust_dry_rock_accounting_history"
                ]
            ),
        )

    def test_missing_or_misaligned_histories_are_rejected(self) -> None:
        def empty_history(world: dict) -> None:
            _swap(world, "crust_dry_rock_accounting_history", [])

        def shadow_history_is_not_a_list(world: dict) -> None:
            _swap(world, "crust_material_shadow_history", {})

        def truncated_plate_history(world: dict) -> None:
            _swap(
                world,
                "plate_motion_history",
                world["plate_motion_history"][:-1],
            )

        self._assert_table({
            "empty_history": (
                empty_history, "aligned accounting histories are missing"
            ),
            "shadow_history_type": (
                shadow_history_is_not_a_list,
                "aligned accounting histories are missing",
            ),
            "plate_history_length": (
                truncated_plate_history,
                "aligned accounting histories are missing",
            ),
        })

    def test_geometry_and_initial_schema_tampers_are_rejected(self) -> None:
        message = "accounting geometry or initial schema is invalid"

        def renumbered_cell(world: dict) -> None:
            _swap(world["cells"][3], "id", 99)

        def negative_area(world: dict) -> None:
            _swap(world["cells"][0], "area_km2", -1.0)

        def non_finite_area(world: dict) -> None:
            _swap(world["cells"][0], "area_km2", float("inf"))

        def missing_record_field(world: dict) -> None:
            world["crust_dry_rock_accounting_history"][0].pop("stage")

        def nonpositive_plate_count(world: dict) -> None:
            _swap(world["crust_dry_rock_accounting_history"][0], "plate_count", 0)

        def plate_count_is_not_an_integer(world: dict) -> None:
            record = world["crust_dry_rock_accounting_history"][0]
            _swap(record, "plate_count", str(record["plate_count"]))

        self._assert_table({
            "cell_id": (renumbered_cell, message),
            "negative_area": (negative_area, message),
            "non_finite_area": (non_finite_area, message),
            "record_key_set": (missing_record_field, message),
            "plate_count_value": (nonpositive_plate_count, message),
            "plate_count_type": (plate_count_is_not_an_integer, message),
        })

    def test_history_record_field_tampers_are_rejected(self) -> None:
        def record_is_not_a_full_record(world: dict) -> None:
            _swap(world["crust_dry_rock_accounting_history"], 1, {"id": 1})

        def broken_step_link(world: dict) -> None:
            _swap(world["crust_dry_rock_accounting_history"][1], "id", 5)

        def cell_count_is_a_float(world: dict) -> None:
            record = world["crust_dry_rock_accounting_history"][1]
            _swap(record, "cell_count", float(record["cell_count"]))

        def packet_table_schema(world: dict) -> None:
            _swap(
                world["crust_dry_rock_accounting_history"][1],
                "opening_surface_packets",
                {"unexpected": []},
            )

        def packet_column_is_a_tuple(world: dict) -> None:
            table = world["crust_dry_rock_accounting_history"][1][
                "opening_surface_packets"
            ]
            _swap(table, "dry_rock_mass_kg", tuple(table["dry_rock_mass_kg"]))

        def packet_offsets_are_short(world: dict) -> None:
            table = world["crust_dry_rock_accounting_history"][1][
                "closing_surface_packets"
            ]
            _swap(table, "owner_offsets", table["owner_offsets"][:-1])

        def unknown_origin_domain(world: dict) -> None:
            table = world["crust_dry_rock_accounting_history"][1][
                "opening_surface_packets"
            ]
            _swap(table["origin_domain_ids"], 0, 2)

        def transfer_table_schema(world: dict) -> None:
            _swap(
                world["crust_dry_rock_accounting_history"][1],
                "proxy_compensation_transfers",
                {},
            )

        def transfer_column_is_a_tuple(world: dict) -> None:
            table = world["crust_dry_rock_accounting_history"][1][
                "proxy_compensation_transfers"
            ]
            _swap(table, "cell_ids", tuple(table["cell_ids"]))

        def transfer_column_length(world: dict) -> None:
            table = world["crust_dry_rock_accounting_history"][1][
                "proxy_compensation_transfers"
            ]
            _swap(table, "mechanism_ids", table["mechanism_ids"][:-1])

        def adjustment_table_schema(world: dict) -> None:
            _swap(
                world["crust_material_shadow_history"][1],
                "unresolved_source_adjustments",
                {},
            )

        def adjustment_column_is_a_tuple(world: dict) -> None:
            table = world["crust_material_shadow_history"][1][
                "unresolved_sink_adjustments"
            ]
            _swap(table, "dry_rock_mass_kg", tuple(table["dry_rock_mass_kg"]))

        def adjustment_offsets_are_short(world: dict) -> None:
            table = world["crust_material_shadow_history"][1][
                "unresolved_sink_adjustments"
            ]
            _swap(table, "cell_offsets", table["cell_offsets"][:-1])

        def unknown_adjustment_reason(world: dict) -> None:
            table = world["crust_material_shadow_history"][1][
                "unresolved_sink_adjustments"
            ]
            _swap(table["process_reason_ids"], 0, 99)

        def adjustment_accumulation_overflows(world: dict) -> None:
            table = world["crust_material_shadow_history"][1][
                "unresolved_sink_adjustments"
            ]
            # The first two sink records share cell 0 and one process reason,
            # so their masses are summed into a single request.
            self.assertEqual(table["cell_offsets"][0], 0)
            self.assertGreaterEqual(table["cell_offsets"][1], 2)
            self.assertEqual(
                table["process_reason_ids"][0], table["process_reason_ids"][1]
            )
            _swap(table["dry_rock_mass_kg"], 0, 1.7e308)
            _swap(table["dry_rock_mass_kg"], 1, 1.7e308)

        def non_empty_slab_reservoir(world: dict) -> None:
            record = world["crust_dry_rock_accounting_history"][1]
            plate_count = record["plate_count"]
            _swap(record, "opening_subducted_slab_packets", {
                "owner_offsets": [0] + [1] * plate_count,
                "origin_domain_ids": [0],
                "origin_kind_ids": [0],
                "origin_plate_ids": [0],
                "dry_rock_mass_kg": [1.0],
            })

        prefix = "crust dry-rock accounting history 1"
        self._assert_table({
            "record_shape": (
                record_is_not_a_full_record, f"{prefix} schema is invalid"
            ),
            "step_link": (broken_step_link, f"{prefix} fields are invalid"),
            "cell_count_type": (
                cell_count_is_a_float,
                # The record, plate-step and shadow-record cell counts are all
                # parsed in one boolean chain, and the plate and shadow details
                # ("plate cell count ...", "shadow cell count ...") contain the
                # record detail as a substring, so pin the whole failure.
                "crust dry-rock accounting history 1 fields are invalid: "
                "cell count must be an integer",
            ),
            "packet_schema": (
                packet_table_schema,
                "opening_surface_packets has an invalid schema",
            ),
            "packet_column_type": (
                packet_column_is_a_tuple,
                "opening_surface_packets columns must be lists",
            ),
            "packet_offsets": (
                packet_offsets_are_short,
                "closing_surface_packets has invalid sparse dimensions",
            ),
            "packet_key_domain": (
                unknown_origin_domain,
                "opening_surface_packets packets are not canonical",
            ),
            "transfer_schema": (
                transfer_table_schema,
                "proxy transfer table schema is invalid",
            ),
            "transfer_column_type": (
                transfer_column_is_a_tuple,
                "proxy transfer columns must be lists",
            ),
            "transfer_column_length": (
                transfer_column_length,
                "proxy transfer columns differ in length",
            ),
            "adjustment_schema": (
                adjustment_table_schema,
                "shadow adjustment table schema is invalid",
            ),
            "adjustment_column_type": (
                adjustment_column_is_a_tuple,
                "shadow adjustment columns must be lists",
            ),
            "adjustment_offsets": (
                adjustment_offsets_are_short,
                "shadow adjustment table shape is invalid",
            ),
            "adjustment_reason_id": (
                unknown_adjustment_reason,
                "shadow adjustment record is invalid",
            ),
            "adjustment_overflow": (
                adjustment_accumulation_overflows,
                "shadow adjustment accumulation overflowed",
            ),
            "slab_reservoir": (
                non_empty_slab_reservoir,
                "phase-2 slab reservoirs must remain empty",
            ),
        })

    def test_initial_step_origin_state_tampers_are_rejected(self) -> None:
        origin_message = "initial accounting origin state is invalid"

        def shadow_opening_schema(world: dict) -> None:
            _swap(world["crust_material_shadow_history"][0], "opening_packets", {})

        def shadow_opening_offsets(world: dict) -> None:
            table = world["crust_material_shadow_history"][0]["opening_packets"]
            _swap(table, "cell_offsets", table["cell_offsets"][:-1])

        def shadow_opening_key(world: dict) -> None:
            table = world["crust_material_shadow_history"][0]["opening_packets"]
            _swap(table["origin_kind_ids"], 0, 12)

        def two_packets_for_one_cell(world: dict) -> None:
            table = world["crust_material_shadow_history"][0]["opening_packets"]
            offsets = table["cell_offsets"]
            self.assertEqual(offsets, list(range(len(offsets))))
            _swap(table, "cell_offsets", offsets[:-1] + [offsets[-1] + 1])
            # A process-origin key sorts after every crust-kind key, so the
            # final cell now owns two canonically ordered packets.
            table["origin_kind_ids"].append(9)
            table["origin_plate_ids"].append(0)
            table["origin_reason_ids"].append(0)
            table["dry_rock_mass_kg"].append(1.0)
            # The table itself stays well formed - the offsets still close over
            # every mass and all columns keep one row per packet - so the only
            # property left broken is the one-packet-per-cell rule.
            widths = {
                len(table[column])
                for column in (
                    "origin_kind_ids", "origin_plate_ids",
                    "origin_reason_ids", "dry_rock_mass_kg",
                )
            }
            self.assertEqual(widths, {table["cell_offsets"][-1]})
            self.assertEqual(
                table["cell_offsets"],
                sorted(table["cell_offsets"]),
            )

        def short_initial_state_array(world: dict) -> None:
            step = world["plate_motion_history"][0]
            _swap(step, "crust_type_by_cell", step["crust_type_by_cell"][:-1])

        def out_of_range_initial_kind(world: dict) -> None:
            _swap(world["plate_motion_history"][0]["crust_type_by_cell"], 0, 9)

        def surface_mass_above_capacity(world: dict) -> None:
            # Scale the initial thickness and the shadow packet masses by the
            # same factor so the per-cell origin check still agrees; only the
            # capacity envelope is then violated.
            overlap = world["plate_motion_history"][0]["crust_overlap_ledger"]
            shadow = world["crust_material_shadow_history"][0]["opening_packets"]
            self.assertEqual(
                shadow["cell_offsets"], list(range(len(world["cells"]) + 1))
            )
            thickness = [
                value * 1000.0
                for value in overlap["remapped_crust_thickness_km_by_cell"]
            ]
            density = overlap["remapped_crust_density_by_cell"]
            _swap(overlap, "remapped_crust_thickness_km_by_cell", thickness)
            _swap(shadow, "dry_rock_mass_kg", [
                cell["area_km2"] * thickness[index] * density[index]
                * MASS_FACTOR_KG
                for index, cell in enumerate(world["cells"])
            ])

        def closing_surface_does_not_mirror_opening(world: dict) -> None:
            table = world["crust_dry_rock_accounting_history"][0][
                "closing_surface_packets"
            ]
            _swap(
                table["dry_rock_mass_kg"], 0, table["dry_rock_mass_kg"][0] * 2.0
            )

        self._assert_table({
            "shadow_opening_schema": (shadow_opening_schema, origin_message),
            "shadow_opening_offsets": (shadow_opening_offsets, origin_message),
            "shadow_opening_key": (shadow_opening_key, origin_message),
            "packets_per_cell": (two_packets_for_one_cell, origin_message),
            "initial_array_length": (short_initial_state_array, origin_message),
            "initial_crust_kind": (out_of_range_initial_kind, origin_message),
            "capacity_envelope": (surface_mass_above_capacity, origin_message),
            "initial_closing_mirror": (
                closing_surface_does_not_mirror_opening,
                "initial accounting reservoirs do not replay",
            ),
        })

    def test_replayed_step_and_scalar_mirror_tampers_are_rejected(self) -> None:
        def broken_transport_geometry(world: dict) -> None:
            overlap = world["plate_motion_history"][1]["crust_overlap_ledger"]
            _swap(overlap["overlap_area_km2"], 0, -1.0)

        def missing_reason_records(world: dict) -> None:
            _swap(
                world["crust_dry_rock_accounting_history"][1],
                "ordered_reason_transactions",
                [],
            )

        def reason_record_schema(world: dict) -> None:
            transaction = world["crust_dry_rock_accounting_history"][1][
                "ordered_reason_transactions"
            ][0]
            transaction.pop("process_reason")

        def short_scalar_replay_array(world: dict) -> None:
            step = world["plate_motion_history"][1]
            _swap(
                step,
                "crust_thickness_process_change_km_by_cell",
                step["crust_thickness_process_change_km_by_cell"][:-1],
            )

        def non_numeric_scalar_replay_input(world: dict) -> None:
            step = world["plate_motion_history"][1]
            _swap(step["crust_density_process_change_by_cell"], 0, "0.0")

        self._assert_table({
            "transport_geometry": (
                broken_transport_geometry,
                # The step-replay verdict interpolates the raised detail, which
                # is the only thing separating this failure from every other
                # way the replay can reject a step.
                "accounting transaction replay failed at step 1: "
                "transport CSR is invalid",
            ),
            "reason_record_count": (
                missing_reason_records,
                "accounting reason records are invalid at step 1",
            ),
            "reason_record_schema": (
                reason_record_schema,
                "accounting reason transactions differ at step 1",
            ),
            "scalar_input_length": (
                short_scalar_replay_array,
                "accounting scalar replay inputs are invalid at step 1",
            ),
            "scalar_input_type": (
                non_numeric_scalar_replay_input,
                "accounting scalar replay inputs are invalid at step 1",
            ),
        })

    def test_summary_mirror_tampers_are_rejected(self) -> None:
        message = "crust dry-rock accounting summary mirrors are invalid"

        def summary_is_not_a_mapping(world: dict) -> None:
            _swap(world, "summary", None)

        def cumulative_mass_mirror(world: dict) -> None:
            field = (
                "cumulative_crust_dry_rock_requested_surface_source_mass_kg"
            )
            _swap(world["summary"], field, world["summary"][field] + 1.0e18)

        self._assert_table({
            "summary_type": (summary_is_not_a_mapping, message),
            "cumulative_mass": (cumulative_mass_mirror, message),
        })

    def test_operational_safety_limits_reject_an_oversized_ledger(self) -> None:
        world = worlds.cached_world(WORLD_KEY)
        with patch(f"{_ACCOUNTING_MODULE}.MAX_LIVE_RESERVOIR_PACKETS", 8):
            result = validate_crust_dry_rock_accounting(world)
        self.assertFalse(result["passed"], result["failures"])
        self.assertTrue(any(
            "accounting history exceeds an operational safety limit" in failure
            for failure in result["failures"]
        ), result["failures"])

        with patch(f"{_ACCOUNTING_MODULE}.MAX_SURFACE_PACKETS_PER_OWNER", 0):
            result = validate_crust_dry_rock_accounting(world)
        self.assertFalse(result["passed"], result["failures"])
        self.assertTrue(any(
            "opening_surface_packets exceeds its per-owner safety limit"
            in failure
            for failure in result["failures"]
        ), result["failures"])

        # Same world, unpatched caps: the ledger is clean, so both failures
        # above came from the caps alone.
        control = validate_crust_dry_rock_accounting(world)
        self.assertEqual(control["failures"], [])
        self.assertTrue(control["passed"])

    def test_summary_mass_field_registry_drift_is_rejected(self) -> None:
        # The registry constant and the locally built mirror table must stay in
        # lockstep; this guard only fires if a future edit lets them drift.
        world = worlds.cached_world(WORLD_KEY)
        with patch(f"{_ACCOUNTING_MODULE}.SUMMARY_MASS_FIELDS", frozenset()):
            result = validate_crust_dry_rock_accounting(world)
        self.assertFalse(result["passed"], result["failures"])
        self.assertIn(
            "crust dry-rock accounting summary mirrors are invalid",
            result["failures"],
        )


class CrustProcessScaledStepReplayTests(TestCase):
    """Sub-reference timestep branches of the ordered crust-rule replay."""

    def _replay(self, *, timestep_scale: float, **overrides: object) -> dict:
        payload: dict[str, object] = {
            "areas_km2": [1.0],
            "remapped_crust_type_by_cell": [0],
            "remapped_lithology_by_cell": [0],
            "remapped_crust_age_ma_by_cell": [100.0],
            "remapped_crust_thickness_km_by_cell": [8.0],
            "remapped_crust_density_by_cell": [2.9],
            "previous_plate_ids": [0],
            "current_plate_ids": [0],
            "boundary_convergent_by_cell": [0.0],
            "boundary_divergent_by_cell": [0.0],
            "timestep_scale": timestep_scale,
            "reference_oceanic_crust_aging_ma_per_reference_step": 5.0,
            "internal_heat": 1.0,
            "geological_age_ga": 4.5,
        }
        payload.update(overrides)
        return replay_ordered_crust_process(**payload)

    def test_half_step_divergence_uses_survival_fraction_composition(self) -> None:
        # A sub-reference step applies the reference fraction as a survival
        # power, ``1 - f_scaled = (1 - f_reference) ** scale``, and composes the
        # plate-crossing impulse on top of it.  Cell 2 drives the reference
        # fraction past one so the saturated branch is exercised too.
        replay = self._replay(
            timestep_scale=0.5,
            areas_km2=[1.0, 1.0, 1.0],
            remapped_crust_type_by_cell=[0, 1, 0],
            remapped_lithology_by_cell=[0, 2, 0],
            remapped_crust_age_ma_by_cell=[100.0, 100.0, 200.0],
            remapped_crust_thickness_km_by_cell=[8.0, 35.0, 8.0],
            remapped_crust_density_by_cell=[2.9, 2.72, 2.9],
            previous_plate_ids=[0, 0, 0],
            current_plate_ids=[1, 1, 1],
            boundary_convergent_by_cell=[0.0, 0.0, 0.0],
            boundary_divergent_by_cell=[0.5, 0.5, 5.0],
        )

        survival = math.sqrt(1.0 - 0.275)
        crossing = (0.36 - 0.275) / (1.0 - 0.275)
        self.assertAlmostEqual(
            replay["crust_age_ma_by_cell"][0],
            100.0 * survival * (1.0 - crossing),
            places=11,
        )
        self.assertAlmostEqual(
            replay["crust_thickness_km_by_cell"][0],
            8.0 + (7.0 - 8.0) * (1.0 - math.sqrt(1.0 - 0.34 * 0.5)),
            places=12,
        )
        self.assertAlmostEqual(
            replay["crust_density_by_cell"][0],
            2.9 + (3.0 - 2.9) * (1.0 - math.sqrt(1.0 - 0.24 * 0.5)),
            places=12,
        )

        # Continental rifting splits into a scaled background term and an
        # unscaled plate-crossing term.
        self.assertAlmostEqual(
            replay["crust_thickness_km_by_cell"][1],
            35.0 - 0.45 * 0.5 * 0.5 - 0.20 * 0.5,
            places=12,
        )
        self.assertAlmostEqual(
            replay["crust_density_by_cell"][1], 2.72 + 0.004 * 0.5 * 0.5,
            places=12,
        )
        self.assertEqual(replay["crust_type_by_cell"][1], 6)
        self.assertEqual(replay["lithology_by_cell"][1], 3)

        # A reference fraction at or above one saturates to a full transition.
        self.assertAlmostEqual(
            replay["crust_age_ma_by_cell"][2],
            200.0 * math.sqrt(1.0 - 0.85),
            places=11,
        )
        self.assertAlmostEqual(replay["crust_thickness_km_by_cell"][2], 7.0)
        self.assertAlmostEqual(replay["crust_density_by_cell"][2], 3.0)

        reasons = {reason["reason"]: reason for reason in replay["reasons"]}
        self.assertEqual(
            reasons["oceanic_ridge_rejuvenation"]["triggered_cell_count"], 2
        )
        self.assertEqual(
            reasons["divergent_continental_rifting"]["triggered_cell_count"], 1
        )

    def test_zero_length_timestep_changes_no_state(self) -> None:
        replay = self._replay(
            timestep_scale=0.0, boundary_divergent_by_cell=[0.5]
        )
        self.assertEqual(replay["crust_age_ma_by_cell"], [100.0])
        self.assertEqual(replay["crust_thickness_km_by_cell"], [8.0])
        self.assertEqual(replay["crust_density_by_cell"], [2.9])
        for reason in replay["reasons"]:
            self.assertEqual(
                reason["net_delta"]["crust_volume_km3"], 0.0, reason["reason"]
            )
            self.assertEqual(
                reason["extensive_state_changed_cell_count"], 0, reason["reason"]
            )

    def test_malformed_replay_inputs_are_rejected(self) -> None:
        cases = {
            "no_cells": (
                {
                    "areas_km2": [],
                    "remapped_crust_type_by_cell": [],
                    "remapped_lithology_by_cell": [],
                    "remapped_crust_age_ma_by_cell": [],
                    "remapped_crust_thickness_km_by_cell": [],
                    "remapped_crust_density_by_cell": [],
                    "previous_plate_ids": [],
                    "current_plate_ids": [],
                    "boundary_convergent_by_cell": [],
                    "boundary_divergent_by_cell": [],
                },
                ValueError, "requires at least one cell",
            ),
            "boolean_float": (
                {"areas_km2": [True]}, TypeError, r"areas_km2\[0\] must be numeric",
            ),
            "non_finite_float": (
                {"areas_km2": [float("nan")]},
                ValueError, r"areas_km2\[0\] must be finite",
            ),
            "non_integer_category": (
                {"remapped_crust_type_by_cell": [1.0]},
                TypeError, r"remapped_crust_type_by_cell\[0\] must be an integer",
            ),
            "nonpositive_area": (
                {"areas_km2": [0.0]}, ValueError, "areas_km2 values must be positive",
            ),
            "non_finite_scalar": (
                {"internal_heat": float("inf")},
                ValueError, "crust process scalar inputs must be finite",
            ),
            "negative_timestep_scale": (
                {"timestep_scale": -1.0},
                ValueError, "timestep_scale must be nonnegative",
            ),
            "negative_geological_age": (
                {"geological_age_ga": -1.0},
                ValueError, "geological_age_ga must be nonnegative",
            ),
        }
        for name, (overrides, error, message) in cases.items():
            with self.subTest(case=name):
                scale = overrides.pop("timestep_scale", 1.0)
                with self.assertRaisesRegex(error, message):
                    self._replay(timestep_scale=scale, **overrides)


class CrustProcessLedgerTamperTests(TestCase):
    """Single-field tampers of a healthy generated crust-process ledger."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.clean = validate_crust_process_reason_ledger(
            worlds.cached_world_readonly(WORLD_KEY)
        )

    def _assert_tamper(self, mutate, expected: str) -> None:
        self.assertEqual(self.clean["failures"], [])
        world = worlds.cached_world(WORLD_KEY)
        mutate(world)
        result = validate_crust_process_reason_ledger(world)
        self.assertFalse(result["passed"], result["failures"])
        self.assertTrue(
            any(expected in failure for failure in result["failures"]),
            result["failures"],
        )

    def _assert_table(self, cases: dict[str, tuple[object, str]]) -> None:
        for name, (mutate, expected) in cases.items():
            with self.subTest(case=name):
                self._assert_tamper(mutate, expected)

    def test_control_world_passes(self) -> None:
        self.assertTrue(self.clean["passed"], self.clean["failures"])
        self.assertEqual(self.clean["failures"], [])
        # Every history step after the initial one is replayed, so a silently
        # skipped step would break this equality rather than hide behind a
        # positive count.
        self.assertEqual(
            self.clean["metrics"]["replayed_crust_process_step_count"],
            len(
                worlds.cached_world_readonly(WORLD_KEY)["plate_motion_history"]
            ) - 1,
        )

    def test_missing_replay_inputs_are_rejected(self) -> None:
        result = validate_crust_process_reason_ledger({})
        self.assertFalse(result["passed"])
        self.assertEqual(
            result["failures"],
            ["crust process model, history, or cells are missing"],
        )

        def missing_scale(world: dict) -> None:
            world["plate_kinematic_model"].pop("maturation_timestep_scale")

        def step_is_not_an_object(world: dict) -> None:
            _swap(world["plate_motion_history"], 1, "not-a-step")

        def initial_reason_is_triggered(world: dict) -> None:
            reason = world["plate_motion_history"][0]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"][0]
            _swap(reason, "triggered_cell_count", 1)

        def non_integer_remapped_type(world: dict) -> None:
            ledger = world["plate_motion_history"][1]["crust_overlap_ledger"]
            _swap(ledger["remapped_crust_type_by_cell"], 0, 1.5)

        self._assert_table({
            "model_field": (
                missing_scale,
                "crust process replay inputs are missing or invalid",
            ),
            "step_type": (step_is_not_an_object, "step 1 is not an object"),
            "initial_reason_counts": (
                initial_reason_is_triggered,
                "initial reason 0 counts are not zero",
            ),
            "replay_input_type": (
                non_integer_remapped_type,
                # This verdict interpolates the rejecting input's name, which
                # is what separates it from every other malformed replay input.
                "step 1 replay inputs are invalid: "
                "remapped_crust_type_by_cell[0] must be an integer",
            ),
        })

    def test_process_change_array_tampers_are_rejected(self) -> None:
        def short_process_change(world: dict) -> None:
            step = world["plate_motion_history"][1]
            _swap(
                step,
                "crust_age_process_change_ma_by_cell",
                step["crust_age_process_change_ma_by_cell"][:-1],
            )

        def boolean_process_change(world: dict) -> None:
            step = world["plate_motion_history"][1]
            _swap(step["crust_thickness_process_change_km_by_cell"], 0, True)

        def shifted_process_change(world: dict) -> None:
            step = world["plate_motion_history"][1]
            values = step["crust_density_process_change_by_cell"]
            _swap(values, 0, values[0] + 1.0)

        self._assert_table({
            "array_shape": (
                short_process_change,
                "step 1 crust_age_process_change_ma_by_cell shape is invalid",
            ),
            "element_type": (
                boolean_process_change,
                "step 1 crust_thickness_process_change_km_by_cell[0] is not "
                "numeric",
            ),
            "element_value": (
                shifted_process_change,
                "step 1 crust_density_process_change_by_cell[0] does not replay",
            ),
        })

    def test_reason_delta_payload_tampers_are_rejected(self) -> None:
        def delta_schema(world: dict) -> None:
            reasons = world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"]
            _swap(reasons[2], "net_delta", {})

        def delta_component_type(world: dict) -> None:
            reasons = world["plate_motion_history"][1]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"]
            _swap(reasons[3]["positive_delta"], "crust_volume_km3", None)

        def initial_delta_schema(world: dict) -> None:
            reasons = world["plate_motion_history"][0]["crust_overlap_ledger"][
                "process_inventory_attribution"
            ]["reasons"]
            _swap(reasons[1], "negative_delta_magnitude", [])

        self._assert_table({
            "reason_delta_schema": (
                delta_schema, "step 1 reason 2.net_delta has an invalid schema"
            ),
            "reason_delta_component": (
                delta_component_type,
                "step 1 reason 3.positive_delta.crust_volume_km3 is not numeric",
            ),
            "initial_reason_delta_schema": (
                initial_delta_schema,
                "initial reason 1.negative_delta_magnitude has an invalid "
                "schema",
            ),
        })

    def test_final_cell_state_tampers_are_rejected(self) -> None:
        def final_ledger_missing(world: dict) -> None:
            _swap(world["plate_motion_history"][-1], "crust_overlap_ledger", None)

        def final_categories_invalid(world: dict) -> None:
            _swap(world["plate_motion_history"][-1], "crust_type_by_cell", [])

        def final_numeric_arrays_invalid(world: dict) -> None:
            ledger = world["plate_motion_history"][-1]["crust_overlap_ledger"]
            _swap(ledger, "remapped_crust_age_ma_by_cell", [])

        def final_cell_value_is_boolean(world: dict) -> None:
            _swap(world["cells"][0], "crust_age_ma", True)

        def final_cell_value_is_non_finite(world: dict) -> None:
            _swap(world["cells"][0], "crust_density", float("inf"))

        self._assert_table({
            "final_ledger": (
                final_ledger_missing,
                "final crust state replay metadata is invalid",
            ),
            "final_categories": (
                final_categories_invalid,
                "final crust categorical history is invalid",
            ),
            "final_numeric_arrays": (
                final_numeric_arrays_invalid,
                "final crust_age_ma history arrays are invalid",
            ),
            "final_cell_type": (
                final_cell_value_is_boolean,
                "final cell 0 crust_age_ma is invalid",
            ),
            "final_cell_non_finite": (
                final_cell_value_is_non_finite,
                "final cell 0 crust_density does not match the last history "
                "step",
            ),
        })
