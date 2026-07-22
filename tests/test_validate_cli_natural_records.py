"""Public ``validate`` CLI violations for natural record contracts.

Every case below tampers with exactly one aspect of an otherwise healthy
generated world, writes it out and drives the real ``validate`` command through
``CliRunner``.  A single untampered control run per class proves the fixture is
healthy, so a ``FAIL`` line can only come from the tamper.  Each assertion pins
the reported message as a whole output line: a crash and a clean validation
failure both exit non-zero, so ``exit_code == 1`` alone would not distinguish
them, and every run additionally asserts no traceback reached the output.

Three structural safeguards keep the cases from going quietly vacuous as the
generator evolves:

* every tamper factory refuses to write a value the fixture already holds, so a
  hardcoded tamper that happens to match the generated value fails loudly
  instead of silently validating nothing;
* batched tampers are verified to touch disjoint parts of the world before the
  run, so one tamper can never be credited with another's message;
* messages are matched against whole ``FAIL`` lines, so a check that grows a
  longer message sharing the same prefix stops satisfying the assertion.
"""

from __future__ import annotations

import copy
import itertools
import tempfile
import unittest
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from magic_geo.cli import app
from magic_geo.io import write_json
from support import worlds
from typer.testing import CliRunner

from support.cli import assert_no_cli_crash
import pytest

# Exhaustive branch coverage of ``validate``: every case invokes the full CLI
# over a generated world. Deselect locally with -m "not slow".
pytestmark = pytest.mark.slow

Mutation = Callable[[dict[str, Any]], None]

_PAYLOAD_COUNTER = itertools.count()


def _changed_paths(
    before: Any,
    after: Any,
    path: str = "",
    out: set[str] | None = None,
) -> set[str]:
    """Every dotted path at which ``after`` differs from ``before``."""
    if out is None:
        out = set()
    if type(before) is not type(after):
        out.add(path)
        return out
    if isinstance(before, dict):
        for key in set(before) | set(after):
            child = f"{path}.{key}"
            if key not in before or key not in after:
                out.add(child)
            else:
                _changed_paths(before[key], after[key], child, out)
    elif isinstance(before, list):
        if len(before) != len(after):
            out.add(f"{path}[len]")
            return out
        for index, (left, right) in enumerate(zip(before, after)):
            _changed_paths(left, right, f"{path}[{index}]", out)
    elif before != after:
        out.add(path)
    return out


def _require(condition: bool, message: str) -> None:
    """Reject a tamper that would not actually change the fixture."""
    if not condition:
        raise AssertionError(f"ineffective tamper: {message}")


# --------------------------------------------------------------------------
# tamper factories
# --------------------------------------------------------------------------
def bump(key: str, delta: float = 1) -> Mutation:
    """Offset an integral summary counter so it no longer matches the records."""

    def mutate(world: dict[str, Any]) -> None:
        summary = world["summary"]
        _require(key in summary, f"summary[{key!r}] is absent")
        before = summary[key]
        after = before + delta
        _require(after != before, f"summary[{key!r}] would keep the value {before!r}")
        summary[key] = after

    return mutate


def skew(key: str) -> Mutation:
    """Move a floating summary metric far outside every relative tolerance."""

    def mutate(world: dict[str, Any]) -> None:
        summary = world["summary"]
        _require(key in summary, f"summary[{key!r}] is absent")
        before = summary[key]
        after = abs(float(before)) * 2.0 + 100.0
        _require(after != before, f"summary[{key!r}] would keep the value {before!r}")
        summary[key] = after

    return mutate


def set_summary(key: str, value: Any) -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        summary = world["summary"]
        _require(key in summary, f"summary[{key!r}] is absent")
        _require(summary[key] != value, f"summary[{key!r}] already holds {value!r}")
        summary[key] = value

    return mutate


def drop_summary(key: str) -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        _require(key in world["summary"], f"summary[{key!r}] is already absent")
        world["summary"].pop(key)

    return mutate


def pollute_counts(key: str) -> Mutation:
    """Add a bogus bucket to a summary histogram."""

    def mutate(world: dict[str, Any]) -> None:
        counts = world["summary"].get(key)
        _require(isinstance(counts, dict), f"summary[{key!r}] is not a histogram")
        _require("tampered_bucket" not in counts, f"summary[{key!r}] already has the bogus bucket")
        polluted = dict(counts)
        polluted["tampered_bucket"] = 1
        world["summary"][key] = polluted

    return mutate


def set_record(collection: str, field: str, value: Any, index: int = 0) -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        record = _record(world, collection, index)
        _require(field in record, f"{collection}[{index}][{field!r}] is absent")
        _require(record[field] != value, f"{collection}[{index}][{field!r}] already holds {value!r}")
        record[field] = value

    return mutate


def drop_record(collection: str, field: str, index: int = 0) -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        record = _record(world, collection, index)
        _require(field in record, f"{collection}[{index}][{field!r}] is already absent")
        record.pop(field)

    return mutate


def duplicate_record(collection: str, index: int = 0) -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        record = _record(world, collection, index)
        world[collection].append(copy.deepcopy(record))

    return mutate


def not_a_list(collection: str) -> Mutation:
    """Replace a record list with a mapping: not a ``list``, still safe to iterate."""

    def mutate(world: dict[str, Any]) -> None:
        _require(isinstance(world.get(collection), list), f"{collection} is not a list to begin with")
        world[collection] = {}

    return mutate


def set_cell(field: str, value: Any, index: int = 0) -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        cell = world["cells"][index]
        _require(field in cell, f"cells[{index}][{field!r}] is absent")
        _require(cell[field] != value, f"cells[{index}][{field!r}] already holds {value!r}")
        cell[field] = value

    return mutate


def drop_cell_field(field: str, index: int = 0) -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        cell = world["cells"][index]
        _require(field in cell, f"cells[{index}][{field!r}] is already absent")
        cell.pop(field)

    return mutate


def _record(world: dict[str, Any], collection: str, index: int) -> dict[str, Any]:
    records = world.get(collection)
    _require(isinstance(records, list), f"{collection} is not a list")
    _require(len(records) > index, f"{collection} has no record at index {index}")
    return records[index]


# --------------------------------------------------------------------------
# base case
# --------------------------------------------------------------------------
class _ValidateViolationCase(unittest.TestCase):
    """Shared plumbing: one baseline world on disk, one control run per class."""

    WORLD_KEY = "replay_128"

    @classmethod
    def setUpClass(cls) -> None:
        cls._tempdir = tempfile.TemporaryDirectory()
        cls._workdir = Path(cls._tempdir.name)
        cls._runner = CliRunner()
        cls._world = worlds.cached_world(cls.WORLD_KEY)
        control = cls._workdir / "control.json"
        write_json(control, cls._world)
        cls._control = cls._runner.invoke(app, ["validate", "--world", str(control)])
        control.unlink()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tempdir.cleanup()

    def setUp(self) -> None:
        # Proof carried by every tamper: the untampered fixture validates clean.
        assert_no_cli_crash(self, self._control)
        self.assertNotIn("FAIL ", self._control.output)
        self.assertEqual(self._control.exit_code, 0, self._control.output[:4000])

    def _run(self, world: dict[str, Any]) -> list[str]:
        """Validate ``world`` and return the reported messages, one per line."""
        path = self._workdir / f"tampered_{next(_PAYLOAD_COUNTER)}.json"
        write_json(path, world)
        try:
            result = self._runner.invoke(app, ["validate", "--world", str(path)])
        finally:
            path.unlink(missing_ok=True)
        # A crash also exits non-zero, so rule one out three ways before the
        # message assertions: no traceback text, no captured exception (Typer's
        # own ``Exit`` is a ``SystemExit``, not an ``Exception``), and at least
        # one reported violation line.
        assert_no_cli_crash(self, result)
        self.assertNotIsInstance(result.exception, Exception)
        self.assertEqual(result.exit_code, 1, result.output[:4000])
        reported = [
            line[len("FAIL ") :] for line in result.output.splitlines() if line.startswith("FAIL ")
        ]
        self.assertTrue(reported, result.output[:4000])
        return reported

    def _tampered(self, mutate: Mutation) -> dict[str, Any]:
        world = copy.deepcopy(self._world)
        mutate(world)
        return world

    def assert_reports(self, mutate: Mutation, *messages: str) -> None:
        """One tamper, one run, one or more exact messages."""
        reported = self._run(self._tampered(mutate))
        for message in messages:
            with self.subTest(message=message):
                self.assertIn(message, reported)

    def assert_batch(self, cases: Sequence[tuple[str, Mutation]]) -> None:
        """Independent tampers sharing one run; each pins its own message.

        Sharing a run is only sound while the tampers are independent, so each
        one must touch a part of the world none of its predecessors touched.
        Without that guard a tamper repeated under two messages would look like
        two passing cases while only one of them was ever exercised.
        """
        messages = [message for message, _ in cases]
        self.assertEqual(len(set(messages)), len(messages), "batched messages must be distinct")
        world = copy.deepcopy(self._world)
        touched: set[str] = set()
        for message, mutate in cases:
            mutate(world)
            changed = _changed_paths(self._world, world)
            self.assertTrue(
                changed - touched,
                f"{message}: tamper changed nothing an earlier tamper in the batch had not",
            )
            touched = changed
        reported = self._run(world)
        for message in messages:
            with self.subTest(message=message):
                self.assertIn(message, reported)

    def assert_table(self, cases: Sequence[tuple[str, Mutation]], strip_label: bool = False) -> None:
        """One run per tamper, for tampers that must not be mixed.

        With ``strip_label`` the ``" [...]"`` suffix names the guard clause under
        test in the subTest label and is dropped from the expected message, so
        several clauses reporting one message stay individually identifiable.
        """
        for message, mutate in cases:
            with self.subTest(message=message):
                reported = self._run(self._tampered(mutate))
                expected = message.split(" [")[0] if strip_label else message
                self.assertIn(expected, reported)


# --------------------------------------------------------------------------
# summary bookkeeping: counters that must agree with the records
# --------------------------------------------------------------------------
class ValidateSummaryCounterTest(_ValidateViolationCase):
    def test_hydrologic_budget_and_wetland_counters(self) -> None:
        self.assert_batch(
            [
                (
                    "hydrologic_budget_region_count does not match records",
                    bump("hydrologic_budget_region_count"),
                ),
                (
                    "runoff_surplus_region_count does not match records",
                    bump("runoff_surplus_region_count"),
                ),
                (
                    "water_deficit_region_count does not match records",
                    bump("water_deficit_region_count"),
                ),
                ("wetland_cell_count does not match cells", bump("wetland_cell_count")),
                ("wetland_system_count does not match records", bump("wetland_system_count")),
                ("wetland_type_counts does not match cells", pollute_counts("wetland_type_counts")),
                (
                    "mangrove_wetland_cell_count does not match wetland cells",
                    bump("mangrove_wetland_cell_count"),
                ),
                ("wetland_area_km2 does not match wetland cells", skew("wetland_area_km2")),
                ("wetland summary metrics missing", drop_summary("mean_wetland_connectivity_index")),
            ]
        )

    def test_river_network_evolution_counters(self) -> None:
        self.assert_batch(
            [
                (
                    "river_capture_candidate_count does not match cells",
                    bump("river_capture_candidate_count"),
                ),
                (
                    "high_river_capture_risk_cell_count does not match cells",
                    bump("high_river_capture_risk_cell_count"),
                ),
                ("mean_river_capture_risk does not match cells", skew("mean_river_capture_risk")),
                ("max_river_capture_risk does not match cells", skew("max_river_capture_risk")),
                (
                    "river_avulsion_candidate_count does not match cells",
                    bump("river_avulsion_candidate_count"),
                ),
                (
                    "high_river_avulsion_risk_cell_count does not match cells",
                    bump("high_river_avulsion_risk_cell_count"),
                ),
                ("mean_river_avulsion_risk does not match cells", skew("mean_river_avulsion_risk")),
                ("max_river_avulsion_risk does not match cells", skew("max_river_avulsion_risk")),
                (
                    "river_network_instability_cell_count does not match cells",
                    bump("river_network_instability_cell_count"),
                ),
                (
                    "high_river_network_instability_cell_count does not match cells",
                    bump("high_river_network_instability_cell_count"),
                ),
                (
                    "mean_river_network_instability_index does not match cells",
                    skew("mean_river_network_instability_index"),
                ),
                (
                    "max_river_network_instability_index does not match cells",
                    skew("max_river_network_instability_index"),
                ),
                (
                    "mean_river_reorganization_risk_index does not match river reorganization histories",
                    skew("mean_river_reorganization_risk_index"),
                ),
                (
                    "total_river_divide_lowering_m does not match river reorganization histories",
                    skew("total_river_divide_lowering_m"),
                ),
                (
                    "total_river_sediment_reworked_m does not match river reorganization histories",
                    skew("total_river_sediment_reworked_m"),
                ),
                (
                    "high_river_reorganization_pressure_count does not match river reorganization histories",
                    bump("high_river_reorganization_pressure_count"),
                ),
                (
                    "river_network_evolution_event_count does not match events length",
                    bump("river_network_evolution_event_count"),
                ),
                (
                    "river_reorganization_history_count does not match histories length",
                    bump("river_reorganization_history_count"),
                ),
                (
                    "river_reorganization_step_count does not match histories",
                    bump("river_reorganization_step_count"),
                ),
                (
                    "river network evolution summary metrics missing",
                    drop_summary("mean_river_diversion_probability_index"),
                ),
            ]
        )

    def test_coastal_and_reef_counters(self) -> None:
        self.assert_batch(
            [
                (
                    "coastal_feature_count does not match coastal_features length",
                    bump("coastal_feature_count"),
                ),
                (
                    "coastal_bar_feature_count does not match coastal bar features",
                    bump("coastal_bar_feature_count"),
                ),
                (
                    "prograding_coastal_feature_count does not match coastal trends",
                    bump("prograding_coastal_feature_count"),
                ),
                (
                    "eroding_coastal_feature_count does not match coastal trends",
                    bump("eroding_coastal_feature_count"),
                ),
                (
                    "reef_system_count does not match reef_systems length",
                    bump("reef_system_count"),
                ),
                ("reef_cell_count does not match cells", bump("reef_cell_count")),
                ("reef_total_area_km2 does not match reef systems", skew("reef_total_area_km2")),
                ("mean_reef_growth_index does not match reef cells", skew("mean_reef_growth_index")),
                ("reef_type_counts does not match reef systems", pollute_counts("reef_type_counts")),
                (
                    "fringing_reef_system_count does not match reef type counts",
                    bump("fringing_reef_system_count"),
                ),
                (
                    "barrier_reef_system_count does not match reef type counts",
                    bump("barrier_reef_system_count"),
                ),
                (
                    "atoll_reef_system_count does not match reef type counts",
                    bump("atoll_reef_system_count"),
                ),
                (
                    "patch_reef_system_count does not match reef type counts",
                    bump("patch_reef_system_count"),
                ),
                (
                    "cold_water_reef_system_count does not match reef type counts",
                    bump("cold_water_reef_system_count"),
                ),
            ]
        )

    def test_sediment_transport_and_routing_counters(self) -> None:
        self.assert_batch(
            [
                (
                    "sedimentary_basin_count does not match sedimentary_basins length",
                    bump("sedimentary_basin_count"),
                ),
                (
                    "active_sedimentary_basin_count does not match active sedimentary basins",
                    bump("active_sedimentary_basin_count"),
                ),
                (
                    "sediment_transport_history_count does not match histories length",
                    bump("sediment_transport_history_count"),
                ),
                (
                    "sediment_transport_history_step_count does not match histories",
                    bump("sediment_transport_history_step_count"),
                ),
                (
                    "active_sediment_transport_history_count does not match histories",
                    bump("active_sediment_transport_history_count"),
                ),
                (
                    "sediment_transport_total_input_m does not match histories",
                    skew("sediment_transport_total_input_m"),
                ),
                (
                    "sediment_transport_total_deposition_m does not match histories",
                    skew("sediment_transport_total_deposition_m"),
                ),
                (
                    "sediment_transport_total_export_m does not match histories",
                    skew("sediment_transport_total_export_m"),
                ),
                (
                    "sediment_transport_total_compaction_m does not match histories",
                    skew("sediment_transport_total_compaction_m"),
                ),
                (
                    "sediment_transport_mean_final_fill_fraction does not match histories",
                    skew("sediment_transport_mean_final_fill_fraction"),
                ),
                (
                    "sediment_transport_max_progradation_distance_km does not match histories",
                    skew("sediment_transport_max_progradation_distance_km"),
                ),
                (
                    "sediment_routing_history_count does not match histories length",
                    bump("sediment_routing_history_count"),
                ),
                (
                    "sediment_routing_step_count does not match histories",
                    bump("sediment_routing_step_count"),
                ),
                (
                    "sediment_routing_cell_count does not match cells",
                    bump("sediment_routing_cell_count"),
                ),
                (
                    "sediment_routing_total_local_supply_m does not match histories",
                    skew("sediment_routing_total_local_supply_m"),
                ),
                (
                    "sediment_routing_total_deposition_m does not match histories",
                    skew("sediment_routing_total_deposition_m"),
                ),
                (
                    "sediment_routing_total_export_m does not match histories",
                    skew("sediment_routing_total_export_m"),
                ),
                (
                    "sediment_routing_total_sink_loss_m does not match histories",
                    skew("sediment_routing_total_sink_loss_m"),
                ),
                (
                    "sediment_routing_total_path_length_km does not match histories",
                    skew("sediment_routing_total_path_length_km"),
                ),
                (
                    "sediment_routing_mean_path_length_km does not match histories",
                    skew("sediment_routing_mean_path_length_km"),
                ),
                (
                    "sediment_routing_max_final_load_m does not match histories",
                    skew("sediment_routing_max_final_load_m"),
                ),
                (
                    "sediment_routing_max_delivery_ratio does not match histories",
                    skew("sediment_routing_max_delivery_ratio"),
                ),
            ]
        )

    def test_stratigraphy_and_sequence_counters(self) -> None:
        self.assert_batch(
            [
                (
                    "stratigraphic_column_count does not match stratigraphic_columns length",
                    bump("stratigraphic_column_count"),
                ),
                (
                    "stratigraphic_layer_count does not match stratigraphic column layers",
                    bump("stratigraphic_layer_count"),
                ),
                (
                    "active_stratigraphic_column_count does not match active stratigraphic columns",
                    bump("active_stratigraphic_column_count"),
                ),
                (
                    "sequence_stratigraphy_history_count does not match histories",
                    bump("sequence_stratigraphy_history_count"),
                ),
                (
                    "sequence_stratigraphy_step_count does not match histories",
                    bump("sequence_stratigraphy_step_count"),
                ),
                (
                    "sequence_stratigraphy_event_count does not match histories",
                    bump("sequence_stratigraphy_event_count"),
                ),
                ("sequence_boundary_count does not match histories", bump("sequence_boundary_count")),
                (
                    "transgressive_surface_count does not match histories",
                    bump("transgressive_surface_count"),
                ),
                (
                    "maximum_flooding_surface_count does not match histories",
                    bump("maximum_flooding_surface_count"),
                ),
                (
                    "regressive_surface_count does not match histories",
                    bump("regressive_surface_count"),
                ),
                (
                    "mean_sequence_accommodation_to_deposition_ratio does not match histories",
                    skew("mean_sequence_accommodation_to_deposition_ratio"),
                ),
                (
                    "mean_sequence_flooding_index does not match histories",
                    skew("mean_sequence_flooding_index"),
                ),
                (
                    "systems_tract_counts does not match histories",
                    pollute_counts("systems_tract_counts"),
                ),
                (
                    "shoreline_trajectory_counts does not match histories",
                    pollute_counts("shoreline_trajectory_counts"),
                ),
            ]
        )

    def test_landmass_marine_shelf_and_chokepoint_counters(self) -> None:
        self.assert_batch(
            [
                ("landmass_count does not match landmasses length", bump("landmass_count")),
                ("marine_region_count does not match marine_regions length", bump("marine_region_count")),
                (
                    "continental_shelf_count does not match continental_shelves length",
                    bump("continental_shelf_count"),
                ),
                (
                    "marine_chokepoint_count does not match marine_chokepoints length",
                    bump("marine_chokepoint_count"),
                ),
                ("continent_landmass_count does not match landmasses", bump("continent_landmass_count")),
                ("island_landmass_count does not match landmasses", bump("island_landmass_count")),
                ("largest_landmass_area_km2 does not match landmasses", skew("largest_landmass_area_km2")),
                ("mean_landmass_area_km2 does not match landmasses", skew("mean_landmass_area_km2")),
                (
                    "open_ocean_marine_region_count does not match marine regions",
                    bump("open_ocean_marine_region_count"),
                ),
                (
                    "inland_sea_marine_region_count does not match marine regions",
                    bump("inland_sea_marine_region_count"),
                ),
                (
                    "continental_shelf_marine_region_count does not match marine regions",
                    bump("continental_shelf_marine_region_count"),
                ),
                (
                    "largest_marine_region_area_km2 does not match marine regions",
                    skew("largest_marine_region_area_km2"),
                ),
                (
                    "continental_shelf_cell_count does not match shelves",
                    bump("continental_shelf_cell_count"),
                ),
                (
                    "continental_shelf_total_area_km2 does not match shelves",
                    skew("continental_shelf_total_area_km2"),
                ),
                (
                    "largest_continental_shelf_area_km2 does not match shelves",
                    skew("largest_continental_shelf_area_km2"),
                ),
                (
                    "mean_continental_shelf_depth_m does not match shelves",
                    skew("mean_continental_shelf_depth_m"),
                ),
                (
                    "continental_shelf_shoreline_edge_count does not match shelves",
                    bump("continental_shelf_shoreline_edge_count"),
                ),
                (
                    "continental_shelf_break_edge_count does not match shelves",
                    bump("continental_shelf_break_edge_count"),
                ),
                (
                    "strait_chokepoint_count does not match marine chokepoints",
                    bump("strait_chokepoint_count"),
                ),
                (
                    "mean_marine_chokepoint_constriction_index does not match marine chokepoints",
                    skew("mean_marine_chokepoint_constriction_index"),
                ),
            ]
        )

    def test_channel_hydraulic_navigability_and_port_counters(self) -> None:
        self.assert_batch(
            [
                ("river_channel_cell_count does not match cells", bump("river_channel_cell_count")),
                ("river_channel_system_count does not match systems", bump("river_channel_system_count")),
                (
                    "channel_morphology_class_counts does not match cells",
                    pollute_counts("channel_morphology_class_counts"),
                ),
                (
                    "total_river_channel_length_km does not match systems",
                    skew("total_river_channel_length_km"),
                ),
                (
                    "navigable_channel_depth_cell_count does not match cells",
                    bump("navigable_channel_depth_cell_count"),
                ),
                ("mean_river_channel_width_m does not match cells", skew("mean_river_channel_width_m")),
                ("river_hydraulic_cell_count does not match cells", bump("river_hydraulic_cell_count")),
                ("river_hydraulic_reach_count does not match reaches", bump("river_hydraulic_reach_count")),
                (
                    "hydraulic_flow_regime_counts does not match cells",
                    pollute_counts("hydraulic_flow_regime_counts"),
                ),
                ("mean_hydraulic_radius_m does not match cells", skew("mean_hydraulic_radius_m")),
                (
                    "hydraulically_navigable_cell_count does not match cells",
                    bump("hydraulically_navigable_cell_count"),
                ),
                (
                    "navigable_waterway_count does not match navigable_waterways length",
                    bump("navigable_waterway_count"),
                ),
                ("navigable_cell_count does not match candidate cells", bump("navigable_cell_count")),
                (
                    "high_harbor_suitability_cell_count does not match cells",
                    bump("high_harbor_suitability_cell_count"),
                ),
                (
                    "transport_chokepoint_cell_count does not match cells",
                    bump("transport_chokepoint_cell_count"),
                ),
                (
                    "navigability_class_counts does not match cells",
                    pollute_counts("navigability_class_counts"),
                ),
                ("mean_navigability_index does not match cells", skew("mean_navigability_index")),
                ("port_site_count does not match port_sites length", bump("port_site_count")),
                (
                    "port_candidate_cell_count does not match candidate cells",
                    bump("port_candidate_cell_count"),
                ),
                ("mean_port_suitability_index does not match cells", skew("mean_port_suitability_index")),
            ]
        )

    def test_navigable_waterway_area_is_checked_against_cells_and_records(self) -> None:
        # The one summary metric reconciled twice: against candidate cells and
        # against the waterway records.
        self.assert_reports(
            skew("navigable_waterway_total_area_km2"),
            "navigable_waterway_total_area_km2 does not match candidate cells",
            "navigable_waterway_total_area_km2 does not match waterways",
        )


# --------------------------------------------------------------------------
# missing summary blocks
# --------------------------------------------------------------------------
class ValidateSummaryMetricsMissingTest(_ValidateViolationCase):
    def test_subsystem_summary_blocks_must_be_complete(self) -> None:
        self.assert_table(
            [
                ("river channel summary metrics missing", drop_summary("river_channel_morphology_model")),
                ("river hydraulic summary metrics missing", drop_summary("river_hydraulics_model")),
                ("navigability summary metrics missing", drop_summary("navigability_model")),
                ("port site summary metrics missing", drop_summary("port_site_model")),
                ("sediment budget summary metrics missing", drop_summary("sediment_budget_closure_model")),
                ("priority-flood depression metrics missing", drop_summary("spill_corrected_cell_count")),
                ("water_body_counts missing", set_summary("water_body_counts", {})),
            ]
        )


# --------------------------------------------------------------------------
# record collections that must be lists
# --------------------------------------------------------------------------
class ValidateRecordCollectionsMissingTest(_ValidateViolationCase):
    def test_record_collections_must_be_lists(self) -> None:
        self.assert_table(
            [
                ("wetland_systems missing", not_a_list("wetland_systems")),
                ("river_network_evolution_events missing", not_a_list("river_network_evolution_events")),
                ("river_reorganization_histories missing", not_a_list("river_reorganization_histories")),
                ("reef_systems missing or invalid", not_a_list("reef_systems")),
                ("sequence_stratigraphy_histories missing", not_a_list("sequence_stratigraphy_histories")),
                ("river_channel_systems missing", not_a_list("river_channel_systems")),
                ("river_hydraulic_reaches missing", not_a_list("river_hydraulic_reaches")),
                ("navigable_waterways missing", not_a_list("navigable_waterways")),
                ("port_sites missing", not_a_list("port_sites")),
            ]
        )

    def test_record_collection_lengths_must_agree_with_their_parents(self) -> None:
        self.assert_table(
            [
                (
                    "river_reorganization_histories length does not match river network events",
                    duplicate_record("river_reorganization_histories"),
                ),
                (
                    "sediment_transport_histories length does not match sedimentary_basins length",
                    duplicate_record("sediment_transport_histories"),
                ),
                (
                    "sequence_stratigraphy_histories length does not match stratigraphic columns",
                    duplicate_record("sequence_stratigraphy_histories"),
                ),
            ]
        )


# --------------------------------------------------------------------------
# record schemas
# --------------------------------------------------------------------------
class ValidateRecordFieldsMissingTest(_ValidateViolationCase):
    def test_record_field_sets_must_be_complete(self) -> None:
        self.assert_table(
            [
                (
                    "river reorganization history fields missing",
                    drop_record("river_reorganization_histories", "risk_index"),
                ),
                ("landmass fields missing", drop_record("landmasses", "island_class")),
                ("marine region fields missing", drop_record("marine_regions", "region_class")),
                ("marine chokepoint fields missing", drop_record("marine_chokepoints", "constriction_index")),
                ("stratigraphic column fields missing", drop_record("stratigraphic_columns", "dominant_facies")),
                (
                    "sequence stratigraphy column fields missing",
                    drop_record("stratigraphic_columns", "dominant_systems_tract"),
                ),
                ("river channel system fields missing", drop_record("river_channel_systems", "channel_type")),
                ("river hydraulic reach fields missing", drop_record("river_hydraulic_reaches", "length_km")),
                ("navigable waterway fields missing", drop_record("navigable_waterways", "route_ids")),
                ("port site fields missing", drop_record("port_sites", "route_ids")),
                ("coastal migration fields missing", drop_record("coastal_features", "shoreline_trend")),
            ]
        )

    def test_stratigraphic_layer_fields_must_be_complete(self) -> None:
        def mutate(world: dict[str, Any]) -> None:
            layer = world["stratigraphic_columns"][0]["layers"][0]
            _require("facies" in layer, "the first stratigraphic layer has no facies to drop")
            layer.pop("facies")

        self.assert_reports(mutate, "stratigraphic layer fields missing")


class ValidateCellFieldsMissingTest(_ValidateViolationCase):
    def test_cell_field_sets_must_be_complete(self) -> None:
        self.assert_table(
            [
                ("river network evolution cell fields missing", drop_cell_field("river_capture_risk")),
                ("sediment routing cell fields missing", drop_cell_field("sediment_routing_load_m")),
                ("sediment budget cell fields missing", drop_cell_field("sediment_net_budget_m")),
                ("river channel cell fields missing", drop_cell_field("river_channel_width_m")),
                ("river hydraulic cell fields missing", drop_cell_field("hydraulic_radius_m")),
                ("navigability cell fields missing", drop_cell_field("river_navigability_index")),
                ("port site cell fields missing", drop_cell_field("protected_bay_index")),
            ]
        )


# --------------------------------------------------------------------------
# per-cell diagnostics
# --------------------------------------------------------------------------
class ValidateCellDiagnosticsTest(_ValidateViolationCase):
    def test_out_of_range_cell_diagnostics_are_reported(self) -> None:
        self.assert_table(
            [
                ("wetland cell fields invalid", set_cell("wetland_extent_index", 1.5)),
                ("river network evolution cell diagnostics invalid", set_cell("river_capture_risk", 1.5)),
                ("reef cell fields invalid", set_cell("reef_growth_index", 1.5)),
                ("river channel cell fields invalid", set_cell("river_channel_width_m", -1.0)),
                ("river hydraulic cell fields invalid", set_cell("froude_number", -1.0)),
                ("navigability cell fields invalid", set_cell("navigability_index", 2.0)),
                ("port site cell fields invalid", set_cell("port_suitability_index", 2.0)),
            ]
        )


# --------------------------------------------------------------------------
# sediment budget closure
# --------------------------------------------------------------------------
class ValidateSedimentBudgetTest(_ValidateViolationCase):
    def test_budget_metadata_and_range_violations(self) -> None:
        self.assert_batch(
            [
                (
                    "sediment budget values must be non-negative",
                    set_summary("sediment_budget_production_m", -1.0),
                ),
                (
                    "sediment volume budget metadata or values invalid",
                    set_summary("sediment_budget_closure_model", "tampered_model"),
                ),
                ("sediment_delivery_ratio out of range", set_summary("sediment_delivery_ratio", 2.0)),
                ("sediment budget residual too large", set_summary("sediment_budget_residual_km3", 5.0)),
            ]
        )

    def test_each_volume_term_is_reconciled_against_the_cells_and_the_closure(self) -> None:
        # The three volume terms cannot share a run: inflating two of them can
        # cancel in ``production - deposition - export`` and hide the closure
        # failure, and the reconciliation loop reports only its first mismatch.
        for key in (
            "sediment_budget_production_km3",
            "sediment_budget_deposition_km3",
            "sediment_budget_export_km3",
        ):
            with self.subTest(key=key):
                # Comfortably past the quantization tolerance the closure allows.
                self.assert_reports(
                    _inflate_summary(key, 1000.0),
                    "sediment budget does not close",
                    f"{key} does not match cell volumes",
                )

    def test_zero_area_cell_is_rejected_before_provenance_reconstruction(self) -> None:
        # "sediment provenance cell area invalid" itself is unreachable through
        # the CLI: the provenance block is guarded by the fluvial/hillslope/
        # glacial routing validators, and any non-positive cell area trips those
        # first, so the guarded branch never runs. Pin what is actually reported.
        self.assert_reports(
            set_cell("area_km2", 0.0),
            "sediment interface replay invalid: cell area must be positive",
            "sediment_budget_production_km3 does not match cell volumes",
        )

    def test_cell_provenance_must_reconstruct_the_budget(self) -> None:
        self.assert_reports(
            set_cell("sediment_export_m", 12345.0),
            "sediment production/deposition/export provenance invalid",
        )


def _inflate_summary(key: str, delta: float) -> Mutation:
    """Raise a floating summary volume by a fixed, tolerance-clearing amount."""

    def mutate(world: dict[str, Any]) -> None:
        summary = world["summary"]
        _require(key in summary, f"summary[{key!r}] is absent")
        before = float(summary[key])
        _require(delta != 0.0, f"summary[{key!r}] would keep the value {before!r}")
        summary[key] = before + delta

    return mutate


# --------------------------------------------------------------------------
# record-level consistency
# --------------------------------------------------------------------------
class ValidateRecordConsistencyTest(_ValidateViolationCase):
    def test_geographic_record_violations(self) -> None:
        self.assert_table(
            [
                ("landmass records invalid", set_record("landmasses", "island_class", "tampered_class")),
                ("marine region records invalid", set_record("marine_regions", "cell_count", 99999)),
                (
                    "marine chokepoint records invalid",
                    set_record("marine_chokepoints", "constriction_index", 2.0),
                ),
                ("wetland system records invalid", set_record("wetland_systems", "area_km2", -1.0)),
                (
                    "river channel system records invalid",
                    set_record("river_channel_systems", "channel_type", "tampered_channel"),
                ),
                (
                    "river hydraulic reach records invalid",
                    set_record("river_hydraulic_reaches", "cell_ids", "not-a-list"),
                ),
                (
                    "navigable waterway records invalid",
                    set_record("navigable_waterways", "waterway_type", "tampered_waterway"),
                ),
            ]
        )

    def test_record_ids_must_be_present_and_unique(self) -> None:
        self.assert_table(
            [
                ("landmass ids invalid", set_record("landmasses", "id", -1)),
                ("marine region ids invalid", set_record("marine_regions", "id", -1)),
                ("marine chokepoint ids invalid", set_record("marine_chokepoints", "id", -1)),
                ("river channel system ids are not unique", _clone_id("river_channel_systems")),
                ("river hydraulic reach ids are not unique", _clone_id("river_hydraulic_reaches")),
                ("navigable waterway ids are not unique", _clone_id("navigable_waterways")),
            ]
        )

    def test_record_membership_must_match_the_cell_assignments(self) -> None:
        self.assert_table(
            [
                (
                    "river channel system membership does not match cells",
                    _orphan_cell_assignment("river_channel_system_id", "river_channel_systems"),
                ),
                (
                    "navigable waterway membership does not match cells",
                    _orphan_cell_assignment("navigable_waterway_id", "navigable_waterways"),
                ),
            ]
        )

    def test_history_record_violations(self) -> None:
        self.assert_table(
            [
                (
                    "sediment transport history fields invalid",
                    set_record("sediment_transport_histories", "time_step_count", 999),
                ),
                (
                    "sediment routing history fields invalid",
                    set_record("sediment_routing_histories", "time_step_count", 999),
                ),
                (
                    "sequence stratigraphy diagnostics invalid",
                    set_record("sequence_stratigraphy_histories", "time_step_count", 999),
                ),
                (
                    "river reorganization history records invalid",
                    set_record("river_reorganization_histories", "risk_index", 2.0),
                ),
            ]
        )

    def test_history_aggregates_must_match_their_own_steps(self) -> None:
        # Each aggregate is reconciled by its own guard clause inside the same
        # record loop, so they need one run apiece.
        self.assert_table(
            [
                (f"sediment transport history fields invalid [{field}]", _skew_record(collection, field))
                for collection, field in (
                    ("sediment_transport_histories", "total_sediment_input_m"),
                    ("sediment_transport_histories", "total_deposition_m"),
                    ("sediment_transport_histories", "total_export_m"),
                    ("sediment_transport_histories", "total_compaction_loss_m"),
                    ("sediment_transport_histories", "total_progradation_distance_km"),
                    ("sediment_transport_histories", "final_sediment_thickness_m"),
                    ("sediment_transport_histories", "final_accommodation_fill_fraction"),
                )
            ],
            strip_label=True,
        )

    def test_routing_history_aggregates_must_match_their_own_steps(self) -> None:
        self.assert_table(
            [
                (f"sediment routing history fields invalid [{field}]", _skew_record(collection, field))
                for collection, field in (
                    ("sediment_routing_histories", "total_local_supply_m"),
                    ("sediment_routing_histories", "total_deposition_m"),
                    ("sediment_routing_histories", "total_routed_export_m"),
                    ("sediment_routing_histories", "total_sink_loss_m"),
                    ("sediment_routing_histories", "path_length_km"),
                    ("sediment_routing_histories", "final_sediment_load_m"),
                )
            ],
            strip_label=True,
        )

    def test_dangling_and_mistyped_member_lists(self) -> None:
        self.assert_table(
            [
                (
                    "river channel system records invalid [cell_ids not a list]",
                    set_record("river_channel_systems", "cell_ids", {}),
                ),
                (
                    "river channel system records invalid [dangling cell id]",
                    set_record("river_channel_systems", "cell_ids", [999999]),
                ),
                (
                    "navigable waterway records invalid [watershed_ids not a list]",
                    set_record("navigable_waterways", "watershed_ids", {}),
                ),
                (
                    "navigable waterway records invalid [dangling cell id]",
                    set_record("navigable_waterways", "cell_ids", [999999]),
                ),
                (
                    "river hydraulic reach records invalid [dangling cell id]",
                    set_record("river_hydraulic_reaches", "cell_ids", [999999]),
                ),
                (
                    "wetland system records invalid [dangling cell id]",
                    set_record("wetland_systems", "cell_ids", [999999]),
                ),
                (
                    "wetland system records invalid [aggregate mismatch]",
                    set_record("wetland_systems", "mean_wetland_extent_index", 0.987654),
                ),
                (
                    "wetland system records invalid [non-numeric area]",
                    set_record("wetland_systems", "area_km2", "not-a-number"),
                ),
            ],
            strip_label=True,
        )

    def test_sequence_stratigraphy_step_and_aggregate_violations(self) -> None:
        def tamper_step(world: dict[str, Any]) -> None:
            step = world["sequence_stratigraphy_histories"][0]["steps"][0]
            _require(step.get("systems_tract") != "tampered_tract", "the step already carries the bogus tract")
            step["systems_tract"] = "tampered_tract"

        def tamper_aggregate(world: dict[str, Any]) -> None:
            history = world["sequence_stratigraphy_histories"][0]
            _require(history.get("sequence_event_count") != 987, "the history already reports 987 events")
            history["sequence_event_count"] = 987

        self.assert_table(
            [
                ("sequence stratigraphy diagnostics invalid [step]", tamper_step),
                ("sequence stratigraphy diagnostics invalid [aggregate]", tamper_aggregate),
            ],
            strip_label=True,
        )

    # The ``except (TypeError, ValueError)`` guards around the wetland and reef
    # cell scans are unreachable through the CLI: a non-numeric cell field
    # raises out of an earlier validator, so validate never reaches them.

    def test_river_capture_target_links_must_resolve(self) -> None:
        self.assert_table(
            [
                (
                    "river network evolution cell diagnostics invalid [dangling target]",
                    set_cell("river_capture_target_cell_id", 999999),
                ),
                (
                    "river network evolution cell diagnostics invalid [basin without target]",
                    _capture_basin_without_target(),
                ),
            ],
            strip_label=True,
        )

    def test_river_network_event_violations(self) -> None:
        self.assert_table(
            [
                (
                    "river network evolution event invalid",
                    set_record("river_network_evolution_events", "type", "tampered_event"),
                ),
                (
                    "river network evolution event ids are not unique",
                    _duplicate_first_event_id(),
                ),
                (
                    "river capture event does not match source cell",
                    _capture_event_basin_mismatch(),
                ),
                ("river avulsion event target invalid", _avulsion_event_target_missing()),
                (
                    "river avulsion event does not match source cell",
                    _avulsion_event_risk_mismatch(),
                ),
            ]
        )

    def test_river_reorganization_history_cross_links(self) -> None:
        self.assert_table(
            [
                (
                    "river reorganization histories do not match events",
                    set_record("river_reorganization_histories", "river_network_evolution_event_id", 9999),
                ),
                (
                    "river reorganization history ids are not unique",
                    _duplicate_second_history_id(),
                ),
            ]
        )


def _skew_record(collection: str, field: str, index: int = 0) -> Mutation:
    """Move a record aggregate far outside every relative tolerance."""

    def mutate(world: dict[str, Any]) -> None:
        record = _record(world, collection, index)
        _require(field in record, f"{collection}[{index}][{field!r}] is absent")
        before = record[field]
        after = abs(float(before)) * 2.0 + 100.0
        _require(after != before, f"{collection}[{index}][{field!r}] would keep the value {before!r}")
        record[field] = after

    return mutate


def _capture_basin_without_target() -> Mutation:
    """Name a capture target basin on a cell that has no capture target cell."""

    def mutate(world: dict[str, Any]) -> None:
        for cell in world["cells"]:
            if int(cell.get("river_capture_target_cell_id", -1)) < 0:
                _require(
                    int(cell.get("river_capture_target_basin_id", -1)) != 5,
                    "the cell already names basin 5 as its capture target",
                )
                cell["river_capture_target_basin_id"] = 5
                return
        raise AssertionError("fixture has no cell without a capture target")

    return mutate


def _clone_id(collection: str) -> Mutation:
    """Give the second record the first record's id."""

    def mutate(world: dict[str, Any]) -> None:
        first = _record(world, collection, 0)
        second = _record(world, collection, 1)
        _require(second["id"] != first["id"], f"{collection}[0] and [1] already share an id")
        second["id"] = first["id"]

    return mutate


def _orphan_cell_assignment(field: str, collection: str) -> Mutation:
    """Detach the first member cell of the first record from that record."""

    def mutate(world: dict[str, Any]) -> None:
        record = _record(world, collection, 0)
        _require(bool(record["cell_ids"]), f"{collection}[0] has no member cells")
        member_id = int(record["cell_ids"][0])
        for cell in world["cells"]:
            if int(cell.get("id", -1)) == member_id:
                _require(int(cell.get(field, -1)) != -1, f"cell {member_id} already has no {field}")
                cell[field] = -1
                return
        raise AssertionError(f"fixture has no cell {member_id}")

    return mutate


def _event_of_type(world: dict[str, Any], event_type: str) -> dict[str, Any]:
    for event in world["river_network_evolution_events"]:
        if str(event.get("type", "")) == event_type:
            return event
    raise AssertionError(f"fixture has no {event_type} event")


def _capture_event_basin_mismatch() -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        event = _event_of_type(world, "river_capture_candidate")
        _require(event.get("target_basin_id") != 987654, "the event already targets basin 987654")
        event["target_basin_id"] = 987654

    return mutate


def _avulsion_event_target_missing() -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        event = _event_of_type(world, "river_avulsion_candidate")
        _require(event.get("target_cell_id") != 987654, "the event already targets cell 987654")
        event["target_cell_id"] = 987654

    return mutate


def _avulsion_event_risk_mismatch() -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        event = _event_of_type(world, "river_avulsion_candidate")
        before = float(event.get("risk", 0.0))
        after = 0.25 if before > 0.5 else 0.75
        _require(after != before, f"the event risk is already {after}")
        event["risk"] = after

    return mutate


def _duplicate_first_event_id() -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        events = world["river_network_evolution_events"]
        _require(len(events) > 1, "fixture has fewer than two river network events")
        _require(events[1]["id"] != events[0]["id"], "the first two events already share an id")
        events[1]["id"] = events[0]["id"]

    return mutate


def _duplicate_second_history_id() -> Mutation:
    def mutate(world: dict[str, Any]) -> None:
        histories = world["river_reorganization_histories"]
        _require(len(histories) > 1, "fixture has fewer than two reorganization histories")
        _require(histories[1]["id"] != histories[0]["id"], "the first two histories already share an id")
        histories[1]["id"] = histories[0]["id"]

    return mutate


# --------------------------------------------------------------------------
# records that only exist in a larger world
# --------------------------------------------------------------------------
class ValidateReefAndShelfRecordTest(_ValidateViolationCase):
    """Reef systems and continental shelves are empty at 128 cells."""

    WORLD_KEY = "mid_512"

    def test_baseline_world_contains_reefs_and_shelves(self) -> None:
        self.assertTrue(self._world["reef_systems"])
        self.assertTrue(self._world["continental_shelves"])

    def test_reef_and_shelf_record_violations(self) -> None:
        self.assert_table(
            [
                ("reef system fields missing", drop_record("reef_systems", "reef_type")),
                ("reef system records invalid", set_record("reef_systems", "reef_type", "tampered_reef")),
                ("continental shelf fields missing", drop_record("continental_shelves", "cell_ids")),
                (
                    "continental shelf records invalid",
                    set_record("continental_shelves", "cell_ids", []),
                ),
                ("continental shelf ids invalid", set_record("continental_shelves", "id", -1)),
                (
                    "reef system cell membership does not match cell reef_system_id fields",
                    _reef_membership_mismatch(),
                ),
            ]
        )


def _reef_membership_mismatch() -> Mutation:
    """Let the last reef claim a cell that another reef owns.

    The cell records stay untouched, so the reef-cell scan still sees every reef
    cell while the record scan aborts before crediting the last reef.
    """

    def mutate(world: dict[str, Any]) -> None:
        reefs = world["reef_systems"]
        _require(len(reefs) > 1, "fixture has fewer than two reef systems")
        borrowed = int(reefs[0]["cell_ids"][0])
        last = reefs[-1]
        _require(borrowed not in [int(cid) for cid in last["cell_ids"]], "the last reef already owns that cell")
        last["cell_ids"] = list(last["cell_ids"]) + [borrowed]
        last["cell_count"] = int(last["cell_count"]) + 1

    return mutate


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
