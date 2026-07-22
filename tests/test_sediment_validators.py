"""Focused tests for the pure sediment replay validators.

The public ``validate`` command has its own integration and exhaustive tiers.
These branch cases call the extracted validators directly so 123 mutations do
not repeatedly serialize a generated world and rerun every unrelated domain.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest import TestCase

from magic_geo.cli.validators import (
    _validate_fluvial_sediment_routing,
    _validate_glacial_sediment_transport,
    _validate_hillslope_sediment_transport,
    _validate_sediment_inventory,
)
from support import worlds

WORLD_KEY = "replay_128"

FLUVIAL_MODEL = "fluvial_sediment_routing_model"
FLUVIAL_HISTORY = "fluvial_sediment_routing_history"
HILLSLOPE_MODEL = "hillslope_sediment_transport_model"
HILLSLOPE_HISTORY = "hillslope_sediment_transport_history"
GLACIAL_MODEL = "glacial_sediment_transport_model"
GLACIAL_HISTORY = "glacial_sediment_transport_history"
INVENTORY_MODEL = "sediment_inventory_model"
FEEDBACK_HISTORY = "earth_system_feedback_history"
NUMERIC_HISTORY = "numeric_depression_correction_history"

Tamper = Callable[[dict[str, Any]], None]
Validator = Callable[..., tuple[Any, ...]]


def _numeric_breach_event(**overrides: Any) -> dict[str, Any]:
    """A no-op numeric depression event pinned to the pre-erosion stage.

    ``feedback_stage_id`` 0 runs before any erosion stage, so the replayed
    inventory is still zero everywhere and the event below is consistent with
    it. Overriding one field is enough to trip a single breach check.
    """

    event: dict[str, Any] = {
        "id": 0,
        "feedback_stage_id": 0,
        "cell_ids": [0],
        "sediment_thickness_before_correction_m_by_cell": [0.0],
        "breach_path_cell_ids": [0],
        "breach_sediment_thickness_before_excavation_m_by_cell": [0.0],
        "breach_excavation_depth_m_by_cell": [0.0],
        "breach_alluvium_entrainment_depth_m_by_cell": [0.0],
        "breach_bedrock_erosion_depth_m_by_cell": [0.0],
        "breach_deposition_cell_ids": [],
        "breach_deposition_depth_m_by_cell": [],
        "selected_correction_method": "sink_fill",
        "applied_alluvium_entrainment_volume_km3": 0.0,
        "applied_bedrock_erosion_volume_km3": 0.0,
    }
    event.update(overrides)
    return event


def _append_mass_conserving_breach_event(world: dict[str, Any]) -> None:
    """Append a self-consistent mass-conserving breach at the pre-erosion stage.

    The event replays cleanly on its own terms — the excavated metre comes out
    of bedrock because the inventory is still empty — but the bedrock volume it
    mobilises is absent from the feedback stage it claims to belong to.
    """

    area_km2 = float(world["cells"][0]["area_km2"])
    world[NUMERIC_HISTORY].append(
        _numeric_breach_event(
            selected_correction_method="mass_conserving_breach",
            breach_excavation_depth_m_by_cell=[1.0],
            breach_bedrock_erosion_depth_m_by_cell=[1.0],
            breach_deposition_cell_ids=[1],
            breach_deposition_depth_m_by_cell=[0.5],
            applied_bedrock_erosion_volume_km3=area_km2 / 1000.0,
        )
    )


def _drop_marine_terminal_step(world: dict[str, Any]) -> None:
    """Delete a marine terminal step that other steps route sediment into.

    A marine terminal has no outgoing volume, so removing its step leaves the
    volume routed into that cell unaccounted for without disturbing any other
    step's incoming balance.
    """

    steps = world[FLUVIAL_HISTORY][0]["cell_steps"]
    for index, step in enumerate(steps):
        if step["is_marine_terminal"] and step["incoming_volume_km3"] > 0.001:
            del steps[index]
            return
    raise AssertionError("no marine terminal step receives routed sediment")


def _drop_first_allocation_group(world: dict[str, Any]) -> None:
    """Remove every terminal allocation belonging to the first land sink."""

    allocations = world[FLUVIAL_HISTORY][0]["terminal_allocations"]
    dropped_sink = allocations[0]["sink_cell_id"]
    world[FLUVIAL_HISTORY][0]["terminal_allocations"] = [
        allocation
        for allocation in allocations
        if allocation["sink_cell_id"] != dropped_sink
    ]


def _inflate_allocation_group_total(world: dict[str, Any]) -> None:
    """Deposit more than the sink stored, keeping the per-record sum honest."""

    allocation = world[FLUVIAL_HISTORY][0]["terminal_allocations"][0]
    allocation["excess_aggradation_volume_km3"] += 5.0
    allocation["total_deposition_volume_km3"] += 5.0


def _rewrite_allocation_prior_deposition(world: dict[str, Any]) -> None:
    """Claim a prior local deposition the replayed stage never produced.

    Every other field of the record stays self-consistent — the group still sums
    to the sink's storage and the split still matches — so the record has to be
    rejected on its own terms rather than through a group total.
    """

    allocation = world[FLUVIAL_HISTORY][0]["terminal_allocations"][0]
    allocation["prior_local_deposition_volume_km3"] += 7.0


def _zero_area_of_unrouted_cell(world: dict[str, Any]) -> None:
    """Zero the area of a cell the fluvial replay never touches.

    The cell is neither stepped, nor a flow target, nor an allocation sink or
    target, so every stage still replays and the zero area is first noticed by
    the cumulative cell-field check, which converts volumes to depths by
    dividing by it.
    """

    referenced: set[int] = set()
    for stage in world[FLUVIAL_HISTORY]:
        for step in stage["cell_steps"]:
            referenced.add(int(step["cell_id"]))
            referenced.add(int(step["flow_to_cell_id"]))
        for allocation in stage["terminal_allocations"]:
            referenced.add(int(allocation["sink_cell_id"]))
            referenced.add(int(allocation["target_cell_id"]))
    for cell in world["cells"]:
        if int(cell["id"]) not in referenced:
            cell["area_km2"] = 0.0
            return
    raise AssertionError("every cell takes part in fluvial sediment routing")


def _shift_allocation_split(world: dict[str, Any]) -> None:
    """Move volume from excess aggradation into accommodation deposition.

    The record still sums to the same total deposition, so only the
    accommodation-versus-excess split disagrees with the replay.
    """

    allocation = world[FLUVIAL_HISTORY][0]["terminal_allocations"][0]
    allocation["accommodation_deposition_volume_km3"] += 1000.0
    allocation["excess_aggradation_volume_km3"] -= 1000.0


def _duplicate_first_neighbor(world: dict[str, Any]) -> None:
    neighbors = world["cells"][0]["neighbors"]
    world["cells"][0]["neighbors"] = list(neighbors) + [neighbors[0]]


def _break_neighbor_symmetry(world: dict[str, Any]) -> None:
    neighbor_id = world["cells"][0]["neighbors"][0]
    neighbor = world["cells"][neighbor_id]
    neighbor["neighbors"] = [
        other for other in neighbor["neighbors"] if other != 0
    ]


def _truncate_glacial_target_position(world: dict[str, Any]) -> None:
    """Truncate the position of a downhill glacial target reached from below.

    The source cell is visited first, so the replay trips on the *target's*
    position rather than on the target's own iteration.
    """

    for transfer in world[GLACIAL_HISTORY][0]["transfers"]:
        if transfer["source_cell_id"] < transfer["target_cell_id"]:
            world["cells"][transfer["target_cell_id"]]["position_3d"] = [1.0, 0.0]
            return
    raise AssertionError("no glacial transfer runs from a lower cell id")


def _put_ice_on_water_cell(world: dict[str, Any]) -> None:
    for input_cell in world[GLACIAL_HISTORY][0]["input_cells"]:
        if input_cell["is_water"]:
            input_cell["ice_thickness_m"] = 5.0
            return
    raise AssertionError("no water cell in the glacial input snapshot")


class _SedimentValidatorCase(TestCase):
    """Shared plumbing for one pure sediment validator."""

    validator: Validator

    @classmethod
    def setUpClass(cls) -> None:
        cls.pristine = worlds.cached_world_readonly(WORLD_KEY)

    def failures(self, world: dict[str, Any]) -> list[str]:
        cells_by_id = {int(cell["id"]): cell for cell in world["cells"]}
        result = self.validator(world, world["summary"], cells_by_id)
        return result[0]

    def assert_tamper_reports(self, tamper: Tamper, message: str) -> None:
        world = worlds.cached_world(WORLD_KEY)
        tamper(world)
        self.assertIn(message, self.failures(world))

    def assert_table(self, cases: tuple[tuple[str, Tamper, str], ...]) -> None:
        for name, tamper, message in cases:
            with self.subTest(case=name):
                self.assert_tamper_reports(tamper, message)


def _bump(container: Any, key: Any, delta: float) -> None:
    container[key] = container[key] + delta


class SedimentValidatorControlTests(TestCase):
    def test_untampered_world_passes_every_sediment_validator(self) -> None:
        world = worlds.cached_world_readonly(WORLD_KEY)
        cells_by_id = {int(cell["id"]): cell for cell in world["cells"]}
        for name, validator in (
            ("fluvial", _validate_fluvial_sediment_routing),
            ("hillslope", _validate_hillslope_sediment_transport),
            ("glacial", _validate_glacial_sediment_transport),
            ("inventory", _validate_sediment_inventory),
        ):
            with self.subTest(validator=name):
                self.assertEqual(
                    validator(world, world["summary"], cells_by_id)[0], []
                )


class FluvialSedimentRoutingValidationTests(_SedimentValidatorCase):
    validator = staticmethod(_validate_fluvial_sediment_routing)

    def test_model_metadata_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "model_removed",
                    lambda world: world.pop(FLUVIAL_MODEL),
                    "fluvial sediment routing model or history missing",
                ),
                (
                    "stage_count_not_numeric",
                    lambda world: world[FLUVIAL_MODEL].__setitem__(
                        "stage_count", "not-a-number"
                    ),
                    "fluvial sediment routing metadata values invalid",
                ),
                (
                    "model_type_renamed",
                    lambda world: world[FLUVIAL_MODEL].__setitem__(
                        "model_type", "hand_waved_routing_v0"
                    ),
                    "fluvial sediment routing metadata invalid",
                ),
            )
        )

    def test_stage_sequence_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "stage_field_removed",
                    lambda world: world[FLUVIAL_HISTORY][0].pop(
                        "accumulation_scale"
                    ),
                    "fluvial sediment routing stage missing fields",
                ),
                (
                    "accumulation_scale_not_numeric",
                    lambda world: world[FLUVIAL_HISTORY][0].__setitem__(
                        "accumulation_scale", "not-a-number"
                    ),
                    "fluvial sediment routing stage identifiers invalid",
                ),
                (
                    "stage_id_renumbered",
                    lambda world: world[FLUVIAL_HISTORY][0].__setitem__("id", 9),
                    "fluvial sediment routing stage sequence invalid",
                ),
            )
        )

    def test_cell_step_replay_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "step_field_removed",
                    lambda world: world[FLUVIAL_HISTORY][0]["cell_steps"][0].pop(
                        "water_body_type"
                    ),
                    "fluvial sediment routing stage 0 provenance invalid",
                ),
                (
                    "step_area_not_numeric",
                    lambda world: world[FLUVIAL_HISTORY][0]["cell_steps"][
                        0
                    ].__setitem__("cell_area_km2", "not-a-number"),
                    "fluvial sediment routing stage 0 provenance invalid",
                ),
                (
                    "step_local_source_rewritten",
                    lambda world: world[FLUVIAL_HISTORY][0]["cell_steps"][
                        0
                    ].__setitem__("local_source_volume_km3", 5.0),
                    "fluvial sediment routing stage 0 provenance invalid",
                ),
                (
                    "step_capacity_deposition_inflated",
                    lambda world: _bump(
                        world[FLUVIAL_HISTORY][0]["cell_steps"][0],
                        "capacity_deposition_volume_km3",
                        1.0,
                    ),
                    "fluvial sediment routing stage 0 provenance invalid",
                ),
                (
                    "routed_volume_left_unconsumed",
                    _drop_marine_terminal_step,
                    "fluvial sediment routing stage 0 provenance invalid",
                ),
            )
        )

    def test_terminal_allocation_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "allocation_field_removed",
                    lambda world: world[FLUVIAL_HISTORY][0][
                        "terminal_allocations"
                    ][0].pop("sink_cell_id"),
                    "fluvial sediment routing stage 0 provenance invalid",
                ),
                (
                    "allocation_area_not_numeric",
                    lambda world: world[FLUVIAL_HISTORY][0][
                        "terminal_allocations"
                    ][0].__setitem__("target_area_km2", "not-a-number"),
                    "fluvial sediment routing stage 0 provenance invalid",
                ),
                (
                    "allocation_prior_deposition_rewritten",
                    _rewrite_allocation_prior_deposition,
                    "fluvial sediment routing stage 0 provenance invalid",
                ),
                (
                    "allocation_group_dropped",
                    _drop_first_allocation_group,
                    "fluvial sediment routing stage 0 provenance invalid",
                ),
                (
                    "allocation_group_total_inflated",
                    _inflate_allocation_group_total,
                    "fluvial sediment routing stage 0 provenance invalid",
                ),
                (
                    "allocation_split_shifted",
                    _shift_allocation_split,
                    "fluvial sediment routing stage 0 provenance invalid",
                ),
            )
        )

    def test_stage_total_and_feedback_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "stage_routed_edge_count_inflated",
                    lambda world: _bump(
                        world[FLUVIAL_HISTORY][0], "routed_edge_count", 1
                    ),
                    "fluvial sediment routing stage 0 totals invalid",
                ),
                (
                    "feedback_stage_replaced_by_list",
                    lambda world: world[FEEDBACK_HISTORY].__setitem__(1, []),
                    "fluvial sediment routing feedback link invalid",
                ),
                (
                    "feedback_edge_count_inflated",
                    lambda world: _bump(
                        world[FEEDBACK_HISTORY][1],
                        "fluvial_sediment_routed_edge_count",
                        1,
                    ),
                    "fluvial sediment routing feedback metrics invalid",
                ),
                (
                    "feedback_edge_count_not_numeric",
                    lambda world: world[FEEDBACK_HISTORY][1].__setitem__(
                        "fluvial_sediment_routed_edge_count", "not-a-number"
                    ),
                    "fluvial sediment routing feedback metrics invalid",
                ),
            )
        )

    def test_aggregate_and_cell_field_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "model_total_inflated",
                    lambda world: _bump(
                        world[FLUVIAL_MODEL], "total_routed_edge_count", 1
                    ),
                    "fluvial sediment routing aggregate metadata invalid",
                ),
                (
                    "model_total_not_numeric",
                    lambda world: world[FLUVIAL_MODEL].__setitem__(
                        "total_routed_edge_count", "not-a-number"
                    ),
                    "fluvial sediment routing aggregate metadata invalid",
                ),
                (
                    "summary_routed_cell_count_inflated",
                    lambda world: _bump(
                        world["summary"], "fluvial_sediment_routed_cell_count", 1
                    ),
                    "fluvial sediment routing summary metrics invalid",
                ),
                (
                    "summary_routed_edge_count_not_numeric",
                    lambda world: world["summary"].__setitem__(
                        "fluvial_sediment_routed_edge_count", "not-a-number"
                    ),
                    "fluvial sediment routing summary metrics invalid",
                ),
                (
                    "summary_routed_edge_count_removed",
                    lambda world: world["summary"].pop(
                        "fluvial_sediment_routed_edge_count"
                    ),
                    "fluvial sediment routing summary metrics invalid",
                ),
                (
                    "cell_local_source_depth_inflated",
                    lambda world: _bump(
                        world["cells"][0], "fluvial_sediment_local_source_m", 1.0
                    ),
                    "fluvial sediment routing cumulative cell fields invalid",
                ),
                (
                    "cell_local_source_depth_not_numeric",
                    lambda world: world["cells"][0].__setitem__(
                        "fluvial_sediment_local_source_m", "not-a-number"
                    ),
                    "fluvial sediment routing cumulative cell fields invalid",
                ),
                (
                    "cell_terminal_capture_inflated",
                    lambda world: _bump(
                        world["cells"][0],
                        "fluvial_sediment_terminal_capture_volume_km3",
                        1.0,
                    ),
                    "fluvial sediment routing cumulative cell fields invalid",
                ),
                (
                    "cell_routing_event_count_not_numeric",
                    lambda world: world["cells"][0].__setitem__(
                        "fluvial_sediment_routing_event_count", "not-a-number"
                    ),
                    "fluvial sediment routing cumulative cell fields invalid",
                ),
                (
                    "unrouted_cell_area_zeroed",
                    _zero_area_of_unrouted_cell,
                    "fluvial sediment routing cumulative cell fields invalid",
                ),
            )
        )


class HillslopeSedimentTransportValidationTests(_SedimentValidatorCase):
    validator = staticmethod(_validate_hillslope_sediment_transport)

    def test_model_metadata_and_topology_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "model_removed",
                    lambda world: world.pop(HILLSLOPE_MODEL),
                    "hillslope sediment transport model or history missing",
                ),
                (
                    "diffusivity_not_numeric",
                    lambda world: world[HILLSLOPE_MODEL].__setitem__(
                        "configured_hillslope_diffusivity", "not-a-number"
                    ),
                    "hillslope sediment transport metadata values invalid",
                ),
                (
                    "model_type_renamed",
                    lambda world: world[HILLSLOPE_MODEL].__setitem__(
                        "model_type", "hand_waved_diffusion_v0"
                    ),
                    "hillslope sediment transport metadata invalid",
                ),
                (
                    "duplicated_neighbor",
                    _duplicate_first_neighbor,
                    "hillslope sediment transport mesh topology invalid",
                ),
                (
                    "asymmetric_neighbor",
                    _break_neighbor_symmetry,
                    "hillslope sediment transport mesh topology invalid",
                ),
            )
        )

    def test_stage_and_snapshot_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "stage_field_removed",
                    lambda world: world[HILLSLOPE_HISTORY][0].pop(
                        "mean_effective_diffusivity"
                    ),
                    "hillslope sediment transport stage missing fields",
                ),
                (
                    "input_cell_count_not_numeric",
                    lambda world: world[HILLSLOPE_HISTORY][0].__setitem__(
                        "input_cell_count", "not-a-number"
                    ),
                    "hillslope sediment transport stage values invalid",
                ),
                (
                    "stage_id_renumbered",
                    lambda world: world[HILLSLOPE_HISTORY][0].__setitem__(
                        "id", 9
                    ),
                    "hillslope sediment transport stage sequence invalid",
                ),
                (
                    "input_lithology_unknown",
                    lambda world: world[HILLSLOPE_HISTORY][0]["input_cells"][
                        0
                    ].__setitem__("lithology", "unobtainium"),
                    "hillslope sediment transport input snapshot invalid",
                ),
                (
                    "input_cell_replaced_by_null",
                    lambda world: world[HILLSLOPE_HISTORY][0][
                        "input_cells"
                    ].__setitem__(0, None),
                    "hillslope sediment transport input snapshot invalid",
                ),
                (
                    "input_elevation_not_numeric",
                    lambda world: world[HILLSLOPE_HISTORY][0]["input_cells"][
                        0
                    ].__setitem__("elevation_m", "not-a-number"),
                    "hillslope sediment transport input snapshot invalid",
                ),
            )
        )

    def test_edge_replay_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "edge_dropped",
                    lambda world: world[HILLSLOPE_HISTORY][0]["edges"].pop(),
                    "hillslope sediment transport edge coverage invalid",
                ),
                (
                    "edge_replaced_by_null",
                    lambda world: world[HILLSLOPE_HISTORY][0][
                        "edges"
                    ].__setitem__(0, None),
                    "hillslope sediment transport edge replay invalid",
                ),
                (
                    "edge_area_not_numeric",
                    lambda world: world[HILLSLOPE_HISTORY][0]["edges"][
                        0
                    ].__setitem__("source_area_km2", "not-a-number"),
                    "hillslope sediment transport edge replay invalid",
                ),
                (
                    "edge_transfer_volume_rewritten",
                    lambda world: world[HILLSLOPE_HISTORY][0]["edges"][
                        0
                    ].__setitem__("transfer_volume_km3", 5.0),
                    "hillslope sediment transport edge replay invalid",
                ),
                (
                    "edge_source_cell_unknown",
                    lambda world: world[HILLSLOPE_HISTORY][0]["edges"][
                        0
                    ].__setitem__("source_cell_id", 999999),
                    "hillslope sediment transport edge replay invalid",
                ),
            )
        )

    def test_aggregate_feedback_and_cell_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "stage_edge_count_inflated",
                    lambda world: _bump(
                        world[HILLSLOPE_HISTORY][0], "transport_edge_count", 1
                    ),
                    "hillslope sediment transport stage aggregates invalid",
                ),
                (
                    "feedback_stage_replaced_by_list",
                    lambda world: world[FEEDBACK_HISTORY].__setitem__(1, []),
                    "hillslope sediment transport feedback link invalid",
                ),
                (
                    "feedback_edge_count_inflated",
                    lambda world: _bump(
                        world[FEEDBACK_HISTORY][1],
                        "hillslope_sediment_transport_edge_count",
                        1,
                    ),
                    "hillslope sediment transport feedback metrics invalid",
                ),
                (
                    "feedback_edge_count_not_numeric",
                    lambda world: world[FEEDBACK_HISTORY][1].__setitem__(
                        "hillslope_sediment_transport_edge_count",
                        "not-a-number",
                    ),
                    "hillslope sediment transport feedback metrics invalid",
                ),
                (
                    "model_total_inflated",
                    lambda world: _bump(
                        world[HILLSLOPE_MODEL], "total_transport_edge_count", 1
                    ),
                    "hillslope sediment transport model aggregates invalid",
                ),
                (
                    "model_total_not_numeric",
                    lambda world: world[HILLSLOPE_MODEL].__setitem__(
                        "total_transport_edge_count", "not-a-number"
                    ),
                    "hillslope sediment transport model aggregates invalid",
                ),
                (
                    "summary_unique_source_count_inflated",
                    lambda world: _bump(
                        world["summary"],
                        "hillslope_sediment_unique_source_cell_count",
                        1,
                    ),
                    "hillslope sediment transport summary metrics invalid",
                ),
                (
                    "summary_edge_count_not_numeric",
                    lambda world: world["summary"].__setitem__(
                        "hillslope_sediment_transport_edge_count", "not-a-number"
                    ),
                    "hillslope sediment transport summary metrics invalid",
                ),
                (
                    "cell_net_depth_inflated",
                    lambda world: _bump(
                        world["cells"][0], "hillslope_sediment_net_m", 1.0
                    ),
                    "hillslope sediment transport cumulative cell fields invalid",
                ),
                (
                    "cell_production_depth_not_numeric",
                    lambda world: world["cells"][0].__setitem__(
                        "hillslope_sediment_production_m", "not-a-number"
                    ),
                    "hillslope sediment transport cumulative cell fields invalid",
                ),
            )
        )


class GlacialSedimentTransportValidationTests(_SedimentValidatorCase):
    validator = staticmethod(_validate_glacial_sediment_transport)

    def test_model_metadata_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "model_removed",
                    lambda world: world.pop(GLACIAL_MODEL),
                    "glacial sediment transport model or history missing",
                ),
                (
                    "mobile_fraction_not_numeric",
                    lambda world: world[GLACIAL_MODEL].__setitem__(
                        "mobile_sediment_fraction", "not-a-number"
                    ),
                    "glacial sediment transport metadata values invalid",
                ),
                (
                    "model_type_renamed",
                    lambda world: world[GLACIAL_MODEL].__setitem__(
                        "model_type", "hand_waved_ice_v0"
                    ),
                    "glacial sediment transport metadata invalid",
                ),
            )
        )

    def test_stage_and_snapshot_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "stage_field_removed",
                    lambda world: world[GLACIAL_HISTORY][0].pop(
                        "max_source_production_depth_m"
                    ),
                    "glacial sediment transport stage missing fields",
                ),
                (
                    "input_cell_count_not_numeric",
                    lambda world: world[GLACIAL_HISTORY][0].__setitem__(
                        "input_cell_count", "not-a-number"
                    ),
                    "glacial sediment transport stage values invalid",
                ),
                (
                    "stage_id_renumbered",
                    lambda world: world[GLACIAL_HISTORY][0].__setitem__("id", 3),
                    "glacial sediment transport stage sequence invalid",
                ),
                (
                    "negative_ice_thickness",
                    lambda world: world[GLACIAL_HISTORY][0]["input_cells"][
                        0
                    ].__setitem__("ice_thickness_m", -1.0),
                    "glacial sediment transport input snapshot invalid",
                ),
                (
                    "input_cell_replaced_by_null",
                    lambda world: world[GLACIAL_HISTORY][0][
                        "input_cells"
                    ].__setitem__(0, None),
                    "glacial sediment transport input snapshot invalid",
                ),
                (
                    "input_elevation_not_numeric",
                    lambda world: world[GLACIAL_HISTORY][0]["input_cells"][
                        0
                    ].__setitem__("elevation_m", "not-a-number"),
                    "glacial sediment transport input snapshot invalid",
                ),
            )
        )

    def test_topology_and_source_state_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "position_truncated",
                    lambda world: world["cells"][0].__setitem__(
                        "position_3d", [1.0, 0.0]
                    ),
                    "glacial sediment transport topology invalid",
                ),
                (
                    "position_not_numeric",
                    lambda world: world["cells"][0].__setitem__(
                        "position_3d", ["not-a-number", 0.0, 0.0]
                    ),
                    "glacial sediment transport topology invalid",
                ),
                (
                    "downhill_target_position_truncated",
                    _truncate_glacial_target_position,
                    "glacial sediment transport topology invalid",
                ),
                (
                    "asymmetric_neighbor",
                    _break_neighbor_symmetry,
                    "glacial sediment transport topology invalid",
                ),
                (
                    "ice_on_water_cell",
                    _put_ice_on_water_cell,
                    "glacial sediment transport source-state replay invalid",
                ),
            )
        )

    def test_transfer_replay_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "transfer_dropped",
                    lambda world: world[GLACIAL_HISTORY][0]["transfers"].pop(),
                    "glacial sediment transport transfer coverage invalid",
                ),
                (
                    "transfer_replaced_by_null",
                    lambda world: world[GLACIAL_HISTORY][0][
                        "transfers"
                    ].__setitem__(0, None),
                    "glacial sediment transport transfer replay invalid",
                ),
                (
                    "transfer_area_not_numeric",
                    lambda world: world[GLACIAL_HISTORY][0]["transfers"][
                        0
                    ].__setitem__("source_area_km2", "not-a-number"),
                    "glacial sediment transport transfer replay invalid",
                ),
                (
                    "transfer_volume_rewritten",
                    lambda world: world[GLACIAL_HISTORY][0]["transfers"][
                        0
                    ].__setitem__("transfer_volume_km3", 7.0),
                    "glacial sediment transport transfer replay invalid",
                ),
                (
                    "post_transport_elevation_shifted",
                    lambda world: _bump(
                        world[GLACIAL_HISTORY][0][
                            "post_transport_elevation_m_by_cell"
                        ],
                        0,
                        10.0,
                    ),
                    "glacial sediment terrain coupling snapshot invalid",
                ),
                (
                    "post_transport_elevation_not_numeric",
                    lambda world: world[GLACIAL_HISTORY][0][
                        "post_transport_elevation_m_by_cell"
                    ].__setitem__(0, "not-a-number"),
                    "glacial sediment terrain coupling snapshot invalid",
                ),
            )
        )

    def test_aggregate_feedback_and_cell_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "stage_transfer_count_inflated",
                    lambda world: _bump(
                        world[GLACIAL_HISTORY][0], "transfer_count", 1
                    ),
                    "glacial sediment transport stage aggregates invalid",
                ),
                (
                    "model_total_inflated",
                    lambda world: _bump(
                        world[GLACIAL_MODEL], "total_transfer_count", 1
                    ),
                    "glacial sediment transport model aggregates invalid",
                ),
                (
                    "model_total_not_numeric",
                    lambda world: world[GLACIAL_MODEL].__setitem__(
                        "total_transfer_count", "not-a-number"
                    ),
                    "glacial sediment transport model aggregates invalid",
                ),
                (
                    "feedback_stage_replaced_by_list",
                    lambda world: world[FEEDBACK_HISTORY].__setitem__(7, []),
                    "glacial sediment transport feedback link invalid",
                ),
                (
                    "feedback_transfer_count_inflated",
                    lambda world: _bump(
                        world[FEEDBACK_HISTORY][7],
                        "glacial_sediment_transfer_count",
                        1,
                    ),
                    "glacial sediment transport feedback metrics invalid",
                ),
                (
                    "feedback_production_volume_removed",
                    lambda world: world[FEEDBACK_HISTORY][7].pop(
                        "glacial_sediment_production_volume_km3"
                    ),
                    "glacial sediment transport feedback metrics invalid",
                ),
                (
                    "summary_target_cell_count_inflated",
                    lambda world: _bump(
                        world["summary"], "glacial_sediment_target_cell_count", 1
                    ),
                    "glacial sediment transport summary metrics invalid",
                ),
                (
                    "summary_transfer_count_not_numeric",
                    lambda world: world["summary"].__setitem__(
                        "glacial_sediment_transfer_count", "not-a-number"
                    ),
                    "glacial sediment transport summary metrics invalid",
                ),
                (
                    "cell_net_depth_inflated",
                    lambda world: _bump(
                        world["cells"][0], "glacial_sediment_net_m", 1.0
                    ),
                    "glacial sediment transport cumulative cell fields invalid",
                ),
                (
                    "cell_production_depth_not_numeric",
                    lambda world: world["cells"][0].__setitem__(
                        "glacial_sediment_production_m", "not-a-number"
                    ),
                    "glacial sediment transport cumulative cell fields invalid",
                ),
            )
        )


class SedimentInventoryValidationTests(_SedimentValidatorCase):
    validator = staticmethod(_validate_sediment_inventory)

    def test_model_metadata_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "model_removed",
                    lambda world: world.pop(INVENTORY_MODEL),
                    "sediment inventory model or provenance missing",
                ),
                (
                    "model_type_renamed",
                    lambda world: world[INVENTORY_MODEL].__setitem__(
                        "model_type", "hand_waved_inventory_v0"
                    ),
                    "sediment inventory metadata invalid",
                ),
                (
                    "stage_count_not_numeric",
                    lambda world: world[INVENTORY_MODEL].__setitem__(
                        "stage_count", "not-a-number"
                    ),
                    "sediment inventory metadata values invalid",
                ),
                (
                    "stage_count_mismatched",
                    lambda world: world[INVENTORY_MODEL].__setitem__(
                        "stage_count", 99
                    ),
                    "sediment inventory stage metadata invalid",
                ),
            )
        )

    def test_process_history_link_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "hillslope_stage_replaced_by_null",
                    lambda world: world[HILLSLOPE_HISTORY].__setitem__(0, None),
                    "hillslope inventory stage is not an object",
                ),
                (
                    "hillslope_feedback_link_removed",
                    lambda world: world[HILLSLOPE_HISTORY][0].pop(
                        "feedback_stage_id"
                    ),
                    "hillslope inventory feedback link invalid",
                ),
                (
                    "hillslope_feedback_link_duplicated",
                    lambda world: world[HILLSLOPE_HISTORY][1].__setitem__(
                        "feedback_stage_id", 1
                    ),
                    "hillslope inventory feedback link duplicated",
                ),
                (
                    "fluvial_feedback_link_removed",
                    lambda world: world[FLUVIAL_HISTORY][0].pop(
                        "feedback_stage_id"
                    ),
                    "fluvial inventory feedback link invalid",
                ),
                (
                    "glacial_feedback_link_removed",
                    lambda world: world[GLACIAL_HISTORY][0].pop(
                        "feedback_stage_id"
                    ),
                    "glacial inventory feedback link invalid",
                ),
                (
                    "glacial_history_emptied",
                    lambda world: world[GLACIAL_HISTORY].clear(),
                    "sediment inventory process stage coverage invalid",
                ),
                (
                    "feedback_stage_renumbered",
                    lambda world: world[FEEDBACK_HISTORY][0].__setitem__("id", 5),
                    "sediment inventory feedback stage sequence invalid",
                ),
            )
        )

    def test_inventory_snapshot_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "hillslope_snapshot_cell_dropped",
                    lambda world: world[HILLSLOPE_HISTORY][0][
                        "input_cells"
                    ].pop(),
                    "hillslope sediment inventory snapshot coverage invalid",
                ),
                (
                    "hillslope_snapshot_thickness_rewritten",
                    lambda world: world[HILLSLOPE_HISTORY][0]["input_cells"][
                        0
                    ].__setitem__("sediment_thickness_m", 5.0),
                    "hillslope sediment inventory snapshot replay invalid",
                ),
                (
                    "hillslope_snapshot_cell_replaced_by_null",
                    lambda world: world[HILLSLOPE_HISTORY][0][
                        "input_cells"
                    ].__setitem__(0, None),
                    "hillslope sediment inventory snapshot replay invalid",
                ),
                (
                    "glacial_snapshot_thickness_rewritten",
                    lambda world: world[GLACIAL_HISTORY][0]["input_cells"][
                        0
                    ].__setitem__("sediment_thickness_m", 5000.0),
                    "glacial sediment inventory snapshot replay invalid",
                ),
            )
        )

    def test_source_partition_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "hillslope_entrainment_inflated",
                    lambda world: _bump(
                        world[HILLSLOPE_HISTORY][0],
                        "alluvium_entrainment_volume_km3",
                        50.0,
                    ),
                    "hillslope source partition invalid",
                ),
                (
                    "fluvial_bedrock_erosion_inflated",
                    lambda world: _bump(
                        world[FLUVIAL_HISTORY][0],
                        "bedrock_erosion_volume_km3",
                        50.0,
                    ),
                    "fluvial source partition invalid",
                ),
                (
                    "glacial_entrainment_inflated",
                    lambda world: _bump(
                        world[GLACIAL_HISTORY][0],
                        "alluvium_entrainment_volume_km3",
                        50.0,
                    ),
                    "glacial source partition invalid",
                ),
                (
                    "feedback_inventory_volume_rewritten",
                    lambda world: world[FEEDBACK_HISTORY][0].__setitem__(
                        "sediment_inventory_volume_km3", 500.0
                    ),
                    "sediment inventory feedback replay invalid",
                ),
                (
                    "hillslope_edge_source_id_removed",
                    lambda world: world[HILLSLOPE_HISTORY][0]["edges"][0].pop(
                        "source_cell_id"
                    ),
                    "sediment inventory provenance values invalid",
                ),
            )
        )

    def test_numeric_breach_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "event_id_out_of_order",
                    lambda world: world[NUMERIC_HISTORY].append(
                        _numeric_breach_event(id=9)
                    ),
                    "sediment inventory numeric event order invalid",
                ),
                (
                    "event_replaced_by_string",
                    lambda world: world[NUMERIC_HISTORY].append("not-an-event"),
                    "sediment inventory numeric event order invalid",
                ),
                (
                    "component_snapshot_length_mismatch",
                    lambda world: world[NUMERIC_HISTORY].append(
                        _numeric_breach_event(cell_ids=[0, 1])
                    ),
                    "numeric breach component inventory snapshot invalid",
                ),
                (
                    "breach_path_length_mismatch",
                    lambda world: world[NUMERIC_HISTORY].append(
                        _numeric_breach_event(breach_path_cell_ids=[0, 1])
                    ),
                    "numeric breach path inventory snapshot invalid",
                ),
                (
                    "unselected_event_claims_entrainment",
                    lambda world: world[NUMERIC_HISTORY].append(
                        _numeric_breach_event(
                            breach_alluvium_entrainment_depth_m_by_cell=[1.0]
                        )
                    ),
                    "numeric breach source partition invalid",
                ),
                (
                    "applied_bedrock_volume_inflated",
                    lambda world: world[NUMERIC_HISTORY].append(
                        _numeric_breach_event(
                            applied_bedrock_erosion_volume_km3=500.0
                        )
                    ),
                    "numeric breach source partition totals invalid",
                ),
                (
                    "unrecorded_mass_conserving_breach",
                    _append_mass_conserving_breach_event,
                    "sediment inventory feedback replay invalid",
                ),
            )
        )

    def test_aggregate_and_cell_field_violations_are_reported(self) -> None:
        self.assert_table(
            (
                (
                    "cell_entrainment_field_removed",
                    lambda world: world["cells"][0].pop(
                        "sediment_alluvium_entrainment_m"
                    ),
                    "sediment inventory cumulative cell fields missing",
                ),
                (
                    "cell_bedrock_erosion_inflated",
                    lambda world: _bump(
                        world["cells"][0], "sediment_bedrock_erosion_m", 1.0
                    ),
                    "sediment inventory cumulative cell fields invalid",
                ),
                (
                    "model_deposition_inflated",
                    lambda world: _bump(
                        world[INVENTORY_MODEL], "deposition_volume_km3", 500.0
                    ),
                    "sediment inventory model aggregates invalid",
                ),
                (
                    "process_partition_entry_removed",
                    lambda world: world[INVENTORY_MODEL][
                        "process_source_partition"
                    ].pop("glacial"),
                    "sediment inventory process partition missing",
                ),
                (
                    "process_partition_value_inflated",
                    lambda world: _bump(
                        world[INVENTORY_MODEL]["process_source_partition"][
                            "glacial"
                        ],
                        "bedrock_erosion_volume_km3",
                        500.0,
                    ),
                    "sediment inventory process partition invalid",
                ),
                (
                    "model_gross_volume_not_numeric",
                    lambda world: world[INVENTORY_MODEL].__setitem__(
                        "gross_mobilization_volume_km3", "not-a-number"
                    ),
                    "sediment inventory model values invalid",
                ),
                (
                    "summary_model_name_renamed",
                    lambda world: world["summary"].__setitem__(
                        "sediment_inventory_model", "hand_waved_inventory_v0"
                    ),
                    "sediment inventory summary metadata invalid",
                ),
                (
                    "summary_final_inventory_inflated",
                    lambda world: _bump(
                        world["summary"],
                        "sediment_final_inventory_volume_km3",
                        500.0,
                    ),
                    "sediment inventory summary metrics invalid",
                ),
                (
                    "summary_gross_volume_not_numeric",
                    lambda world: world["summary"].__setitem__(
                        "sediment_gross_mobilization_volume_km3", "not-a-number"
                    ),
                    "sediment inventory summary values invalid",
                ),
            )
        )
