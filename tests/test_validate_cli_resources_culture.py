"""Public ``validate`` CLI violations for resources, culture, and population.

This module audits the economic geology records (ore genesis systems,
sedimentary resource systems, petroleum migration systems, commodity
occurrences), the land-use zones and natural
frontiers, the worldbuilding realism checks, the route corridors, the
historical-linguistics stack (phonological rules, histories, lexical
correspondences, lexical diffusion, speaker populations) and the population
history / conflict counters.

A healthy generated world walks the passing path through every one of those
checks, so the uncovered code is the reporting side.  Each test therefore takes
a private deep copy of a canonical world, tampers with exactly one field (or a
batch of mutually independent fields), writes it to a temporary file and runs
``validate`` over it through :class:`typer.testing.CliRunner`.

``validate`` accumulates into a single ``failures`` list that is flushed at one
gate near the end of the command, so independent summary counters can be
tampered together and asserted in one invocation; checks that share a
``for ... else break`` reporting loop are always split across invocations so no
tamper can mask another.

Exit code alone never decides a case.  ``CliRunner`` reports ``exit_code == 1``
for an uncaught exception just as it does for ``typer.Exit(1)``, so every
assertion pins the ``FAIL <message>`` text as a whole output line, requires the
command to have left through ``SystemExit`` and requires ``Traceback`` to be
absent from the output.  Whole-line matching matters: a substring match would
also accept a longer failure message that merely starts with the expected text.
Every assertion also re-checks an untampered control run of the same world, so a
failure can never be blamed on a broken fixture.

Branches in this module that no CLI input can pin, and therefore have no test:

* the ``except (TypeError, ValueError)`` guard around the route-corridor *cell*
  parse.  The guard itself does run for a non-numeric cell field, but every
  field it parses is re-read later by a bare ``float()``/``int()`` over all
  cells, so the command dies before the reporting gate and no ``FAIL`` line is
  ever printed.  The sibling guards over the petroleum
  cell parse and the route-corridor *record* parse do not have that problem and
  are covered below.
* the "member id belongs to another language" guards inside the lexical
  diffusion step loop and the language loop.  Each is preceded in the very same
  condition by a set-equality test against the map those ids were derived from,
  so only a world with a duplicated record id can reach them, and a duplicated
  lexical-correspondence id trips an earlier arm of the same flag first.  (The
  matching guard in the phonological *history* loop is reachable that way and is
  covered by
  ``PhonologyRecordCase.test_history_rule_must_belong_to_its_language``.)
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterable
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.io import write_json

from support import worlds

from support.cli import assert_no_cli_crash
import pytest

# Exhaustive branch coverage of ``validate``: every case invokes the full CLI
# over a generated world. Deselect locally with -m "not slow".
pytestmark = pytest.mark.slow

World = dict[str, Any]
Tamper = Callable[[World], None]

#: ``(case name, tamper, expected message or messages)``.  A tamper that trips
#: two checks at once lists both messages rather than being split into a second
#: case with an empty tamper, so every case in a table owns a real mutation.
Case = tuple[str, Tamper, "str | tuple[str, ...]"]

#: 256 cells.  The smallest canonical world that carries natural frontiers,
#: borders and conflicts; the 128-cell world leaves those families empty.
BASE_WORLD = "small_smoke"

#: 128 cells, where ``natural_frontiers`` is empty -- the only way to reach the
#: "no frontier borders" arm of the barrier-score check.
EMPTY_FRONTIER_WORLD = "replay_128"

_CONTROL: dict[str, tuple[Any, bytes]] = {}


def _run_world(world: World) -> tuple[Any, bytes]:
    """Write ``world`` to a temporary file and invoke ``validate`` on it.

    The serialized bytes come back with the result so that callers can prove a
    tamper actually changed what the command reads.
    """

    with TemporaryDirectory() as directory:
        path = Path(directory) / "world.json"
        write_json(path, world)
        serialized = path.read_bytes()
        result = CliRunner().invoke(app, ["validate", "--world", str(path)])
    return result, serialized


def _control(key: str) -> tuple[Any, bytes]:
    """The untampered ``validate`` run for ``key``, computed once per process."""

    if key not in _CONTROL:
        _CONTROL[key] = _run_world(worlds.cached_world(key))
    return _CONTROL[key]


def _messages(message: str | tuple[str, ...]) -> tuple[str, ...]:
    return (message,) if isinstance(message, str) else message


def set_summary(key: str, value: Any) -> Tamper:
    def tamper(world: World) -> None:
        world["summary"][key] = value

    return tamper


def offset_summary(key: str, delta: float = 0.5) -> Tamper:
    def tamper(world: World) -> None:
        world["summary"][key] = float(world["summary"][key]) + delta

    return tamper


def inflate_summary(key: str) -> Tamper:
    """Push a summed quantity far outside its relative tolerance."""

    def tamper(world: World) -> None:
        world["summary"][key] = float(world["summary"][key]) * 2.0 + 1000.0

    return tamper


def drop_summary(key: str) -> Tamper:
    def tamper(world: World) -> None:
        world["summary"].pop(key, None)

    return tamper


def set_record(collection: str, field: str, value: Any, index: int = 0) -> Tamper:
    def tamper(world: World) -> None:
        world[collection][index][field] = value

    return tamper


def drop_record_field(collection: str, field: str, index: int = 0) -> Tamper:
    def tamper(world: World) -> None:
        world[collection][index].pop(field, None)

    return tamper


def set_cell(field: str, value: Any, index: int = 0) -> Tamper:
    def tamper(world: World) -> None:
        world["cells"][index][field] = value

    return tamper


def drop_cell_field(field: str, index: int = 0) -> Tamper:
    def tamper(world: World) -> None:
        world["cells"][index].pop(field, None)

    return tamper


class ValidateTamperCase(TestCase):
    """Shared tamper-then-validate driver for the CLI-reachable branches."""

    world_key = BASE_WORLD

    def assert_control_clean(self, world_key: str) -> None:
        """The untampered world must validate cleanly.

        Without this every ``FAIL`` assertion below would also pass against a
        world that was already broken before the tamper.
        """

        control, _ = _control(world_key)
        self.assertEqual(control.exit_code, 0, control.output)
        self.assertNotIn("FAIL", control.output)
        self.assertIsNone(control.exception, repr(control.exception))

    def assert_clean_failure(self, result: Any, world_key: str) -> None:
        """``validate`` reached its reporting gate rather than crashing."""

        self.assert_control_clean(world_key)
        assert_no_cli_crash(self, result)
        self.assertIsInstance(result.exception, SystemExit, repr(result.exception))
        self.assertEqual(result.exit_code, 1, result.output)

    def assert_fail_lines(self, result: Any, messages: Iterable[str]) -> None:
        """Every message must appear as a whole ``FAIL`` line of the output.

        Whole-line rather than substring matching, so a check whose message
        merely starts with the expected text cannot satisfy the assertion.
        """

        printed = result.output.splitlines()
        for message in messages:
            self.assertIn(f"FAIL {message}", printed, result.output)

    def tampered(self, tampers: Iterable[Tamper], world_key: str | None = None) -> Any:
        """Apply ``tampers`` to a private copy of the world and validate it.

        The serialized world is compared with the control's, so a tamper that
        happens to write back the value the generator already produced fails
        here instead of silently turning its test into a control run.
        """

        key = world_key or self.world_key
        world = worlds.cached_world(key)
        for tamper in tampers:
            tamper(world)
        result, serialized = _run_world(world)
        self.assertTrue(
            serialized != _control(key)[1], "the tamper left the world unchanged"
        )
        return result

    def assert_reports(
        self,
        tampers: Iterable[Tamper],
        *messages: str,
        world_key: str | None = None,
    ) -> None:
        key = world_key or self.world_key
        result = self.tampered(tampers, key)
        self.assert_clean_failure(result, key)
        self.assert_fail_lines(result, messages)

    def assert_batch(self, cases: list[Case], world_key: str | None = None) -> None:
        """Apply every tamper in one run and pin every expected message."""

        key = world_key or self.world_key
        result = self.tampered([tamper for _, tamper, _ in cases], key)
        self.assert_clean_failure(result, key)
        for name, _, message in cases:
            with self.subTest(name):
                self.assert_fail_lines(result, _messages(message))

    def assert_each(self, cases: list[Case], world_key: str | None = None) -> None:
        """One invocation per tamper, for checks that share a reporting loop."""

        key = world_key or self.world_key
        for name, tamper, message in cases:
            with self.subTest(name):
                self.assert_reports([tamper], *_messages(message), world_key=key)


class GeologySummaryCase(ValidateTamperCase):
    """Summary counters over ore genesis and sedimentary resource systems."""

    def test_ore_and_sedimentary_summary_mismatches(self) -> None:
        self.assert_batch(
            [
                (
                    "ore_system_count",
                    set_summary("ore_genesis_system_count", 999_999),
                    "ore_genesis_system_count does not match records",
                ),
                (
                    "ore_cell_count",
                    set_summary("ore_genesis_cell_count", 999_999),
                    "ore_genesis_cell_count does not match records",
                ),
                (
                    "ore_type_counts",
                    set_summary("ore_genesis_system_type_counts", {"invented": 1}),
                    "ore_genesis_system_type_counts does not match records",
                ),
                (
                    "ore_area",
                    inflate_summary("ore_genesis_total_area_km2"),
                    "ore_genesis_total_area_km2 does not match records",
                ),
                (
                    "sedimentary_count",
                    set_summary("sedimentary_resource_system_count", 999_999),
                    "sedimentary_resource_system_count does not match records",
                ),
                (
                    "sedimentary_cell_count",
                    set_summary("sedimentary_resource_system_cell_count", 999_999),
                    "sedimentary_resource_system_cell_count does not match records",
                ),
                (
                    "sedimentary_area",
                    inflate_summary("sedimentary_resource_system_total_area_km2"),
                    "sedimentary_resource_system_total_area_km2 does not match records",
                ),
                (
                    "sedimentary_type_counts",
                    set_summary(
                        "sedimentary_resource_system_type_counts", {"invented": 1}
                    ),
                    "sedimentary_resource_system_type_counts does not match records",
                ),
                (
                    "petroleum_system_count",
                    set_summary("petroleum_system_count", 999_999),
                    "petroleum_system_count does not match sedimentary resource systems",
                ),
                (
                    "mean_petroleum_potential",
                    offset_summary("mean_petroleum_potential_index"),
                    "mean_petroleum_potential_index does not match sedimentary "
                    "resource systems",
                ),
            ]
        )

    def test_petroleum_and_commodity_summary_mismatches(self) -> None:
        self.assert_batch(
            [
                (
                    "migration_system_count",
                    set_summary("petroleum_migration_system_count", 999_999),
                    "petroleum_migration_system_count does not match records",
                ),
                (
                    "migration_cell_count",
                    set_summary("petroleum_migration_cell_count", 999_999),
                    "petroleum_migration_cell_count does not match records",
                ),
                (
                    "migration_type_counts",
                    set_summary(
                        "petroleum_migration_system_type_counts", {"invented": 1}
                    ),
                    "petroleum_migration_system_type_counts does not match records",
                ),
                (
                    "migration_area",
                    inflate_summary("petroleum_migration_total_area_km2"),
                    "petroleum_migration_total_area_km2 does not match records",
                ),
                (
                    "petroleum_cell_mean",
                    offset_summary("mean_petroleum_source_rock_index"),
                    "mean_petroleum_source_rock_index does not match cells",
                ),
                (
                    "petroleum_trap_cell_count",
                    set_summary("petroleum_trap_cell_count", 999_999),
                    "petroleum_trap_cell_count does not match cells",
                ),
                (
                    "commodity_count",
                    set_summary("commodity_occurrence_count", 999_999),
                    "commodity_occurrence_count does not match records",
                ),
                (
                    "commodity_type_counts",
                    set_summary("commodity_occurrence_type_counts", {"invented": 1}),
                    "commodity_occurrence_type_counts does not match records",
                ),
                (
                    "commodity_group_counts",
                    set_summary("commodity_occurrence_group_counts", {"invented": 1}),
                    "commodity_occurrence_group_counts does not match records",
                ),
                (
                    "commodity_area",
                    inflate_summary("commodity_occurrence_total_area_km2"),
                    "commodity_occurrence_total_area_km2 does not match records",
                ),
                (
                    "gemstone_commodity_count",
                    set_summary("gemstone_commodity_occurrence_count", 999_999),
                    "gemstone_commodity_occurrence_count does not match commodity "
                    "occurrences",
                ),
                (
                    "commodity_confidence_mean",
                    offset_summary("mean_commodity_occurrence_confidence_index"),
                    "mean_commodity_occurrence_confidence_index does not match "
                    "commodity occurrences",
                ),
            ]
        )

    def test_commodity_records_do_not_match_resource_deposits(self) -> None:
        def drop_last_occurrence(world: World) -> None:
            world["commodity_occurrences"].pop()

        self.assert_reports(
            [drop_last_occurrence],
            "commodity occurrence records do not match resource deposits",
            "commodity_occurrence_count does not match records",
        )


class LandUseFrontierSummaryCase(ValidateTamperCase):
    """Summary counters over land-use zones, frontiers and realism checks."""

    def test_land_use_and_frontier_summary_mismatches(self) -> None:
        self.assert_batch(
            [
                (
                    "agricultural_zone_count",
                    set_summary("agricultural_zone_count", 999_999),
                    "agricultural_zone_count does not match agricultural_zones length",
                ),
                (
                    "mining_zone_count",
                    set_summary("mining_zone_count", 999_999),
                    "mining_zone_count does not match mining_zones length",
                ),
                (
                    "agricultural_zone_cell_count",
                    set_summary("agricultural_zone_cell_count", 999_999),
                    "agricultural_zone_cell_count does not match candidate cells",
                ),
                (
                    "mining_zone_cell_count",
                    set_summary("mining_zone_cell_count", 999_999),
                    "mining_zone_cell_count does not match candidate cells",
                ),
                (
                    "mean_agricultural_potential",
                    offset_summary("mean_agricultural_potential_index"),
                    "mean_agricultural_potential_index does not match cells",
                ),
                (
                    "mean_mining_potential",
                    offset_summary("mean_mining_potential_index"),
                    "mean_mining_potential_index does not match cells",
                ),
                # One summary key, two independent expectations: the candidate
                # cell area and the summed zone areas.  Both are equal in a
                # healthy world, so no single value can trip one alone -- the
                # one tamper therefore owns both messages.
                (
                    "agricultural_area",
                    inflate_summary("agricultural_zone_total_area_km2"),
                    (
                        "agricultural_zone_total_area_km2 does not match "
                        "candidate cells",
                        "agricultural_zone_total_area_km2 does not match zones",
                    ),
                ),
                (
                    "mining_area",
                    inflate_summary("mining_zone_total_area_km2"),
                    (
                        "mining_zone_total_area_km2 does not match candidate cells",
                        "mining_zone_total_area_km2 does not match zones",
                    ),
                ),
                (
                    "frontier_count",
                    set_summary("natural_frontier_count", 999_999),
                    "natural_frontier_count does not match natural_frontiers length",
                ),
                (
                    "frontier_cell_count",
                    set_summary("natural_frontier_cell_count", 999_999),
                    "natural_frontier_cell_count does not match candidate cells",
                ),
                (
                    "mean_frontier_index",
                    offset_summary("mean_natural_frontier_index"),
                    "mean_natural_frontier_index does not match cells",
                ),
                (
                    "frontier_border_segments",
                    set_summary("natural_frontier_border_segment_count", 999_999),
                    "natural_frontier_border_segment_count does not match records",
                ),
                (
                    "frontier_area",
                    inflate_summary("natural_frontier_total_area_km2"),
                    "natural_frontier_total_area_km2 does not match records",
                ),
                (
                    "frontier_length",
                    inflate_summary("natural_frontier_total_length_km"),
                    "natural_frontier_total_length_km does not match records",
                ),
                (
                    "frontier_type_counts",
                    set_summary("natural_frontier_type_counts", {"invented": 1}),
                    "natural_frontier_type_counts does not match records",
                ),
                (
                    "river_frontier_count",
                    set_summary("river_frontier_count", 999_999),
                    "river_frontier_count does not match records",
                ),
                (
                    "frontier_barrier_score",
                    offset_summary("mean_natural_frontier_barrier_score"),
                    "mean_natural_frontier_barrier_score does not match borders",
                ),
            ]
        )

    def test_barrier_score_must_be_zero_without_frontier_borders(self) -> None:
        self.assert_reports(
            [set_summary("mean_natural_frontier_barrier_score", 0.5)],
            "mean_natural_frontier_barrier_score should be zero without frontier "
            "borders",
            world_key=EMPTY_FRONTIER_WORLD,
        )

    def test_realism_and_route_summary_mismatches(self) -> None:
        self.assert_batch(
            [
                (
                    "realism_check_count",
                    set_summary("worldbuilding_realism_check_count", 999_999),
                    "worldbuilding_realism_check_count does not match "
                    "worldbuilding_realism_checks length",
                ),
                (
                    "realism_pass_count",
                    set_summary("worldbuilding_realism_pass_count", 999_999),
                    "worldbuilding_realism_pass_count does not match worldbuilding "
                    "realism checks",
                ),
                (
                    "realism_pass_fraction",
                    offset_summary("worldbuilding_realism_pass_fraction"),
                    "worldbuilding_realism_pass_fraction does not match checks",
                ),
                (
                    "realism_mean_score",
                    offset_summary("mean_worldbuilding_realism_score"),
                    "mean_worldbuilding_realism_score does not match checks",
                ),
                (
                    "realism_named_index",
                    offset_summary("route_barrier_avoidance_index"),
                    "route_barrier_avoidance_index does not match worldbuilding "
                    "realism check",
                ),
                (
                    "settlement_count",
                    set_summary("settlement_count", 999_999),
                    "settlement_count does not match settlements length",
                ),
                (
                    "route_count",
                    set_summary("route_count", 999_999),
                    "route_count does not match routes length",
                ),
                # The corridor count is checked against both the corridor
                # records and the route records, which match each other in a
                # healthy world, so the single tamper owns both messages.
                (
                    "corridor_count",
                    set_summary("route_corridor_count", 999_999),
                    (
                        "route_corridor_count does not match route_corridors length",
                        "route_corridor_count should match route count",
                    ),
                ),
                (
                    "corridor_cell_count",
                    set_summary("route_corridor_cell_count", 999_999),
                    "route_corridor_cell_count does not match exported route paths",
                ),
                (
                    "corridor_path_length",
                    inflate_summary("route_corridor_total_path_length_km"),
                    "route_corridor_total_path_length_km does not match corridor "
                    "records",
                ),
                (
                    "corridor_cell_mean",
                    offset_summary("mean_coastal_route_index"),
                    "mean_coastal_route_index does not match route corridor cells",
                ),
                (
                    "corridor_feature_coverage",
                    offset_summary("route_feature_coverage_index"),
                    "route_feature_coverage_index does not match corridor records",
                ),
                (
                    "corridor_type_counts",
                    set_summary("route_corridor_type_counts", {"invented": 1}),
                    "route_corridor_type_counts does not match route corridors",
                ),
                (
                    "coastal_corridor_count",
                    set_summary("coastal_route_corridor_count", 999_999),
                    "coastal_route_corridor_count does not match route corridor type "
                    "counts",
                ),
            ]
        )


class CultureHistorySummaryCase(ValidateTamperCase):
    """Summary counters over regions, history, phonology and populations."""

    def test_region_history_and_phonology_summary_mismatches(self) -> None:
        self.assert_batch(
            [
                (
                    "trade_flow_count",
                    set_summary("trade_flow_count", 999_999),
                    "trade_flow_count does not match trade_flows length",
                ),
                (
                    "political_region_count",
                    set_summary("political_region_count", 999_999),
                    "political_region_count does not match political_regions length",
                ),
                (
                    "culture_region_count",
                    set_summary("culture_region_count", 999_999),
                    "culture_region_count does not match cultures length",
                ),
                (
                    "language_region_count",
                    set_summary("language_region_count", 999_999),
                    "language_region_count does not match language_regions length",
                ),
                (
                    "language_lineage_count",
                    set_summary("language_lineage_count", 999_999),
                    "language_lineage_count does not match language parent links",
                ),
                (
                    "phonology_index_out_of_range",
                    set_summary("mean_sound_shift_index", 5.0),
                    "mean_sound_shift_index out of range",
                ),
                (
                    "historical_era_count",
                    set_summary("historical_era_count", 999_999),
                    "historical_era_count does not match historical_eras length",
                ),
                (
                    "historical_event_count",
                    set_summary("historical_event_count", 999_999),
                    "historical_event_count does not match historical_events length",
                ),
                (
                    "migration_event_count",
                    set_summary("migration_event_count", 999_999),
                    "migration_event_count does not match historical events",
                ),
                (
                    "dynastic_change_count",
                    set_summary("dynastic_change_count", 999_999),
                    "dynastic_change_count does not match historical events",
                ),
                (
                    "phonological_rule_count",
                    set_summary("phonological_rule_count", 999_999),
                    "phonological_rule_count does not match phonological_rules length",
                ),
                (
                    "phonological_history_count",
                    set_summary("phonological_history_count", 999_999),
                    "phonological_history_count does not match "
                    "phonological_histories length",
                ),
                (
                    "lexical_correspondence_count",
                    set_summary("lexical_correspondence_count", 999_999),
                    "lexical_correspondence_count does not match "
                    "lexical_correspondences length",
                ),
                (
                    "lexical_diffusion_history_count",
                    set_summary("lexical_diffusion_history_count", 999_999),
                    "lexical_diffusion_history_count does not match "
                    "lexical_diffusion_histories length",
                ),
                (
                    "speaker_population_history_count",
                    set_summary("speaker_population_history_count", 999_999),
                    "speaker_population_history_count does not match "
                    "speaker_population_histories length",
                ),
                (
                    "phonological_history_step_count",
                    set_summary("phonological_history_step_count", 999_999),
                    "phonological_history_step_count does not match phonological "
                    "histories",
                ),
                (
                    "lexical_diffusion_step_count",
                    set_summary("lexical_diffusion_step_count", 999_999),
                    "lexical_diffusion_step_count does not match lexical diffusion "
                    "histories",
                ),
                (
                    "speaker_population_step_count",
                    set_summary("speaker_population_step_count", 999_999),
                    "speaker_population_step_count does not match speaker population "
                    "histories",
                ),
                (
                    "phonological_rule_language_count",
                    set_summary("phonological_rule_language_count", 999_999),
                    "phonological_rule_language_count does not match languages",
                ),
                (
                    "max_phonological_shift_stage",
                    set_summary("max_phonological_shift_stage", 999_999),
                    "max_phonological_shift_stage does not match phonological rules",
                ),
                (
                    "lexical_correspondence_language_count",
                    set_summary("lexical_correspondence_language_count", 999_999),
                    "lexical_correspondence_language_count does not match lexical "
                    "correspondences",
                ),
                (
                    "lexical_diffusion_language_count",
                    set_summary("lexical_diffusion_language_count", 999_999),
                    "lexical_diffusion_language_count does not match lexical "
                    "diffusion histories",
                ),
                (
                    "phonology_mean",
                    offset_summary("mean_speaker_contact_index"),
                    "mean_speaker_contact_index does not match phonological history",
                ),
                (
                    "total_speaker_population",
                    inflate_summary("total_estimated_speaker_population"),
                    "total_estimated_speaker_population does not match speaker "
                    "population histories",
                ),
                (
                    "high_contact_history_count",
                    set_summary("high_contact_speaker_history_count", 999_999),
                    "high_contact_speaker_history_count does not match speaker "
                    "population histories",
                ),
            ]
        )

    def test_population_and_conflict_summary_mismatches(self) -> None:
        self.assert_batch(
            [
                (
                    "population_region_count",
                    set_summary("population_region_count", 999_999),
                    "population_region_count does not match population_regions length",
                ),
                (
                    "population_history_count",
                    set_summary("population_history_count", 999_999),
                    "population_history_count does not match population_histories "
                    "length",
                ),
                (
                    "population_history_step_count",
                    set_summary("population_history_step_count", 999_999),
                    "population_history_step_count does not match history steps",
                ),
                (
                    "historical_final_population",
                    inflate_summary("historical_final_population"),
                    "historical_final_population does not match population histories",
                ),
                (
                    "peak_population_pressure",
                    offset_summary("historical_peak_population_pressure"),
                    "historical_peak_population_pressure does not match population "
                    "histories",
                ),
                (
                    "max_population_decline",
                    offset_summary("max_population_decline_fraction"),
                    "max_population_decline_fraction does not match population "
                    "histories",
                ),
                (
                    "conflict_count",
                    set_summary("conflict_count", 999_999),
                    "conflict_count does not match conflicts length",
                ),
                (
                    "high_intensity_conflict_count",
                    set_summary("high_intensity_conflict_count", 999_999),
                    "high_intensity_conflict_count does not match conflicts",
                ),
                (
                    "high_disruption_conflict_count",
                    set_summary("high_economic_disruption_conflict_count", 999_999),
                    "high_economic_disruption_conflict_count does not match conflicts",
                ),
            ]
        )


class HistoryCollectionLengthCase(ValidateTamperCase):
    """Per-region history collections must be one record per region."""

    def test_history_collections_must_cover_every_region(self) -> None:
        def drop_speaker_history(world: World) -> None:
            world["speaker_population_histories"].pop()

        def drop_population_history(world: World) -> None:
            world["population_histories"].pop()

        self.assert_each(
            [
                (
                    "speaker_population_histories",
                    drop_speaker_history,
                    "speaker_population_histories length does not match "
                    "language_regions length",
                ),
                (
                    "population_histories",
                    drop_population_history,
                    "population_histories length does not match population_regions "
                    "length",
                ),
            ]
        )


class MissingSummaryMetricCase(ValidateTamperCase):
    """The ``... summary metrics missing`` guards, one deleted key each."""

    def test_summary_metric_groups_report_when_incomplete(self) -> None:
        self.assert_each(
            [
                (
                    "sedimentary",
                    drop_summary("mean_sedimentary_resource_confidence_index"),
                    "sedimentary resource system summary metrics missing",
                ),
                (
                    "petroleum_migration",
                    drop_summary("mean_petroleum_accumulation_index"),
                    "petroleum migration summary metrics missing",
                ),
                (
                    "commodity",
                    drop_summary("mean_commodity_occurrence_confidence_index"),
                    "commodity occurrence summary metrics missing",
                ),
                (
                    "land_use",
                    drop_summary("mining_zone_cell_count"),
                    "land use zone summary metrics missing",
                ),
                (
                    "natural_frontier",
                    drop_summary("dense_forest_frontier_count"),
                    "natural frontier summary metrics missing",
                ),
                (
                    "worldbuilding_realism",
                    drop_summary("natural_border_alignment_index"),
                    "worldbuilding realism summary metrics missing",
                ),
                (
                    "language_phonology",
                    drop_summary("mean_inherited_phonology_fraction"),
                    "language phonology summary metrics missing",
                ),
                (
                    "phonological_rule",
                    drop_summary("mean_phonological_drift_index"),
                    "phonological rule summary metrics missing",
                ),
                (
                    "population",
                    drop_summary("estimated_world_population"),
                    "population summary metrics missing",
                ),
            ]
        )


class MissingRecordFieldCase(ValidateTamperCase):
    """The ``... fields missing`` guards, one deleted record key each."""

    def test_record_field_groups_report_when_incomplete(self) -> None:
        self.assert_each(
            [
                (
                    "sedimentary_resource",
                    drop_record_field("sedimentary_resource_systems", "seal_quality_index"),
                    "sedimentary resource system fields missing",
                ),
                (
                    "petroleum_migration",
                    drop_record_field(
                        "petroleum_migration_systems", "migration_efficiency_index"
                    ),
                    "petroleum migration system fields missing",
                ),
                (
                    "commodity",
                    drop_record_field("commodity_occurrences", "market_value_index"),
                    "commodity occurrence fields missing",
                ),
                (
                    "agricultural_zone",
                    drop_record_field("agricultural_zones", "mean_fertility_index"),
                    "agricultural zone fields missing",
                ),
                (
                    "natural_frontier",
                    drop_record_field("natural_frontiers", "mean_barrier_score"),
                    "natural frontier fields missing",
                ),
                (
                    "worldbuilding_realism",
                    drop_record_field("worldbuilding_realism_checks", "metric"),
                    "worldbuilding realism check fields missing",
                ),
                (
                    "route_corridor",
                    drop_record_field("route_corridors", "detour_ratio"),
                    "route corridor fields missing",
                ),
                (
                    "language_phonology",
                    drop_record_field("language_regions", "sound_shift_index"),
                    "language phonology fields missing",
                ),
                (
                    "language_lineage",
                    drop_record_field("language_regions", "divergence_age_years"),
                    "language lineage fields missing",
                ),
                (
                    "historical_era",
                    drop_record_field("historical_eras", "dominant_process"),
                    "historical era fields missing",
                ),
                (
                    "historical_event",
                    drop_record_field("historical_events", "pressure_index"),
                    "historical event fields missing",
                ),
                (
                    "phonological_rule",
                    drop_record_field("phonological_rules", "prosodic_domain"),
                    "phonological rule fields missing",
                ),
                (
                    "phonological_history",
                    drop_record_field("phonological_histories", "stress_system"),
                    "phonological history fields missing",
                ),
                (
                    "lexical_correspondence",
                    drop_record_field("lexical_correspondences", "stress_pattern"),
                    "lexical correspondence fields missing",
                ),
                (
                    "lexical_diffusion",
                    drop_record_field(
                        "lexical_diffusion_histories", "contact_borrowing_index"
                    ),
                    "lexical diffusion history fields missing",
                ),
                (
                    "speaker_population",
                    drop_record_field(
                        "speaker_population_histories", "mean_speaker_contact_index"
                    ),
                    "speaker population history fields missing",
                ),
                (
                    "population_region",
                    drop_record_field("population_regions", "carrying_capacity"),
                    "population region fields missing",
                ),
            ]
        )

    def test_cell_field_groups_report_when_incomplete(self) -> None:
        self.assert_each(
            [
                (
                    "petroleum",
                    drop_cell_field("petroleum_maturation_index"),
                    "petroleum migration cell fields missing",
                ),
                (
                    "land_use",
                    drop_cell_field("mining_potential_index"),
                    "land use zone cell fields missing",
                ),
                (
                    "natural_frontier",
                    drop_cell_field("natural_frontier_id"),
                    "natural frontier cell fields missing",
                ),
            ]
        )


class MissingCollectionCase(ValidateTamperCase):
    """Whole record collections replaced by a non-list."""

    def test_non_list_collections_are_reported(self) -> None:
        self.assert_each(
            [
                (
                    "sedimentary_resource_systems",
                    lambda world: world.update({"sedimentary_resource_systems": None}),
                    "sedimentary_resource_systems missing",
                ),
                (
                    "petroleum_migration_systems",
                    lambda world: world.update({"petroleum_migration_systems": None}),
                    "petroleum_migration_systems missing",
                ),
                (
                    "commodity_occurrences",
                    lambda world: world.update({"commodity_occurrences": None}),
                    "commodity_occurrences missing",
                ),
                (
                    "agricultural_zones",
                    lambda world: world.update({"agricultural_zones": None}),
                    "agricultural_zones missing",
                ),
                (
                    "mining_zones",
                    lambda world: world.update({"mining_zones": None}),
                    "mining_zones missing",
                ),
                (
                    "natural_frontiers",
                    lambda world: world.update({"natural_frontiers": None}),
                    "natural_frontiers missing",
                ),
                (
                    "route_corridors",
                    lambda world: world.update({"route_corridors": None}),
                    "route_corridors missing or invalid",
                ),
            ]
        )


class OreGenesisRecordCase(ValidateTamperCase):
    """Every ``ore_system_invalid`` arm of the ore genesis record audit."""

    message = "ore genesis systems invalid"

    def _ore_step(self, field: str, value: Any, step: int = 0) -> Tamper:
        def tamper(world: World) -> None:
            world["ore_genesis_systems"][0]["formation_steps"][step][field] = value

        return tamper

    def test_ore_genesis_record_violations(self) -> None:
        def duplicate_cell_between_systems(world: World) -> None:
            systems = world["ore_genesis_systems"]
            borrowed = int(systems[0]["cell_ids"][0])
            systems[1]["cell_ids"] = sorted({*systems[1]["cell_ids"], borrowed})

        def drop_step_key(world: World) -> None:
            world["ore_genesis_systems"][0]["formation_steps"][0].pop("process_metric")

        self.assert_each(
            [
                (
                    "id_not_numeric",
                    set_record("ore_genesis_systems", "id", "not-a-number"),
                    self.message,
                ),
                (
                    "plate_ids_not_a_list",
                    set_record("ore_genesis_systems", "plate_ids", "not-a-list"),
                    self.message,
                ),
                (
                    "plate_ids_not_numeric",
                    set_record("ore_genesis_systems", "plate_ids", ["not-a-number"]),
                    self.message,
                ),
                ("cell_shared_between_systems", duplicate_cell_between_systems, self.message),
                (
                    "cell_count_mismatch",
                    set_record("ore_genesis_systems", "cell_count", 999_999),
                    self.message,
                ),
                (
                    "dominant_lithology_mismatch",
                    set_record("ore_genesis_systems", "dominant_lithology", "invented"),
                    self.message,
                ),
                (
                    "record_mean_mismatch",
                    set_record(
                        "ore_genesis_systems", "mean_hydrothermal_alteration_index", 0.0
                    ),
                    self.message,
                ),
                (
                    "viability_mean_mismatch",
                    set_record(
                        "ore_genesis_systems", "mean_resource_viability_index", 0.0
                    ),
                    self.message,
                ),
                ("step_key_missing", drop_step_key, self.message),
                (
                    "step_metric_not_numeric",
                    self._ore_step("mean_process_intensity_index", "not-a-number"),
                    self.message,
                ),
                (
                    "step_active_cell_count_mismatch",
                    self._ore_step("active_cell_count", 999_999),
                    self.message,
                ),
                (
                    "step_mean_mismatch",
                    self._ore_step("mean_ore_genesis_potential_index", 0.0),
                    self.message,
                ),
            ]
        )

    def test_step_linked_deposit_must_sit_on_an_active_cell(self) -> None:
        def relink_deposit(world: World) -> None:
            system = world["ore_genesis_systems"][0]
            deposits = {
                int(deposit["id"]): int(deposit["cell_id"])
                for deposit in world["resource_deposits"]
            }
            for step in system["formation_steps"]:
                active = {int(cell_id) for cell_id in step["active_cell_ids"]}
                offsite = sorted(
                    deposit_id
                    for deposit_id in system["resource_deposit_ids"]
                    if deposits.get(int(deposit_id), -1) not in active
                )
                if offsite:
                    step["linked_resource_deposit_ids"] = offsite
                    return
            raise AssertionError(
                "fixture has no ore formation step with an off-site linkable deposit"
            )

        self.assert_reports([relink_deposit], self.message)

    def test_ore_genesis_identity_and_membership_counters(self) -> None:
        def duplicate_system_id(world: World) -> None:
            world["ore_genesis_systems"][1]["id"] = int(
                world["ore_genesis_systems"][0]["id"]
            )

        self.assert_reports(
            [duplicate_system_id],
            "ore genesis system ids are not unique",
        )

    def test_ore_genesis_cell_membership_must_match_cells(self) -> None:
        def unassign_cell(world: World) -> None:
            member = int(world["ore_genesis_systems"][0]["cell_ids"][0])
            for cell in world["cells"]:
                if int(cell["id"]) == member:
                    cell["ore_genesis_system_id"] = -1
                    return
            raise AssertionError("ore genesis system has no exported member cell")

        self.assert_reports(
            [unassign_cell],
            "ore genesis cell membership does not match systems",
        )


class SedimentaryAndPetroleumRecordCase(ValidateTamperCase):
    """Record audits for sedimentary resource and petroleum migration systems."""

    def test_sedimentary_resource_record_violations(self) -> None:
        self.assert_each(
            [
                (
                    "cell_count_mismatch",
                    set_record("sedimentary_resource_systems", "cell_count", 999_999),
                    "sedimentary resource system records invalid",
                ),
                (
                    "duplicate_id",
                    set_record("sedimentary_resource_systems", "id", 0, index=1),
                    "sedimentary resource system ids are not unique",
                ),
            ]
        )

    def test_petroleum_cell_violations(self) -> None:
        # Both arms report the same message, so they are split into their own
        # invocations and their distinctness rests on the tamper: a float field
        # out of range takes the comparison arm, while a non-numeric
        # ``petroleum_system_id`` takes the ``except (TypeError, ValueError)``
        # arm.  The id is the only field of that parse not re-read by a bare
        # ``float()`` further down, so it is the only one whose run survives to
        # the reporting gate.
        self.assert_each(
            [
                (
                    "index_out_of_range",
                    set_cell("petroleum_accumulation_index", 5.0),
                    "petroleum migration cell fields invalid",
                ),
                (
                    "system_id_not_numeric",
                    set_cell("petroleum_system_id", "not-a-number"),
                    "petroleum migration cell fields invalid",
                ),
            ]
        )

    def test_petroleum_migration_record_violations(self) -> None:
        message = "petroleum migration systems invalid"

        def duplicate_cell_between_systems(world: World) -> None:
            systems = world["petroleum_migration_systems"]
            borrowed = int(systems[0]["cell_ids"][0])
            systems[1]["cell_ids"] = sorted({*systems[1]["cell_ids"], borrowed})

        def drop_step_key(world: World) -> None:
            world["petroleum_migration_systems"][0]["migration_steps"][0].pop(
                "hydrocarbon_charge_index"
            )

        def break_path_adjacency(world: World) -> None:
            system = world["petroleum_migration_systems"][0]
            step = system["migration_steps"][0]
            path = [int(cell_id) for cell_id in step["path_cell_ids"]]
            members = [int(cell_id) for cell_id in system["cell_ids"]]
            cells_by_id = {int(cell["id"]): cell for cell in world["cells"]}
            neighbours = {
                int(neighbour) for neighbour in cells_by_id[path[0]]["neighbors"]
            }
            for candidate in members:
                if candidate not in neighbours and candidate not in path:
                    path[1] = candidate
                    step["path_cell_ids"] = path
                    return
            raise AssertionError("no non-adjacent member cell available for the path")

        self.assert_each(
            [
                (
                    "id_not_numeric",
                    set_record("petroleum_migration_systems", "id", "not-a-number"),
                    message,
                ),
                (
                    "seal_cell_ids_not_a_list",
                    set_record("petroleum_migration_systems", "seal_cell_ids", "no"),
                    message,
                ),
                (
                    "seal_cell_ids_not_numeric",
                    set_record(
                        "petroleum_migration_systems", "seal_cell_ids", ["not-a-number"]
                    ),
                    message,
                ),
                ("cell_shared_between_systems", duplicate_cell_between_systems, message),
                (
                    "cell_count_mismatch",
                    set_record("petroleum_migration_systems", "cell_count", 999_999),
                    message,
                ),
                (
                    "record_mean_mismatch",
                    set_record(
                        "petroleum_migration_systems", "mean_maturation_index", 0.0
                    ),
                    message,
                ),
                ("step_key_missing", drop_step_key, message),
                ("step_path_not_adjacent", break_path_adjacency, message),
                (
                    "efficiency_mismatch",
                    set_record(
                        "petroleum_migration_systems", "migration_efficiency_index", 0.0
                    ),
                    message,
                ),
            ]
        )

    def test_migration_cells_must_be_the_union_of_the_step_paths(self) -> None:
        def shrink_migration_cells(world: World) -> None:
            system = world["petroleum_migration_systems"][0]
            migration_ids = [int(cell_id) for cell_id in system["migration_cell_ids"]]
            if len(migration_ids) < 2:
                raise AssertionError("migration fairway is a single cell")
            system["migration_cell_ids"] = migration_ids[:-1]
            system["migration_cell_count"] = len(migration_ids) - 1

        self.assert_reports([shrink_migration_cells], "petroleum migration systems invalid")

    def test_petroleum_migration_step_violations(self) -> None:
        message = "petroleum migration systems invalid"

        def step_field(field: str, value: Any) -> Tamper:
            def tamper(world: World) -> None:
                world["petroleum_migration_systems"][0]["migration_steps"][0][field] = value

            return tamper

        self.assert_each(
            [
                (
                    "step_metric_not_numeric",
                    step_field("leakage_risk_index", "not-a-number"),
                    message,
                ),
                ("step_index_mismatch", step_field("step_index", 999_999), message),
                (
                    "step_distance_mismatch",
                    step_field("migration_distance_km", 0.0),
                    message,
                ),
            ]
        )

    def test_petroleum_migration_identity_counters(self) -> None:
        def duplicate_system_id(world: World) -> None:
            world["petroleum_migration_systems"][1]["id"] = int(
                world["petroleum_migration_systems"][0]["id"]
            )

        def unassign_cell(world: World) -> None:
            member = int(world["petroleum_migration_systems"][0]["cell_ids"][0])
            for cell in world["cells"]:
                if int(cell["id"]) == member:
                    cell["petroleum_system_id"] = -1
                    return
            raise AssertionError(
                "petroleum migration system has no exported member cell"
            )

        self.assert_each(
            [
                (
                    "duplicate_id",
                    duplicate_system_id,
                    "petroleum migration system ids are not unique",
                ),
                (
                    "cell_membership",
                    unassign_cell,
                    "petroleum migration cell membership does not match systems",
                ),
            ]
        )


class CommodityOccurrenceRecordCase(ValidateTamperCase):
    """Record audits for commodity occurrences."""

    def test_commodity_record_violations(self) -> None:
        def duplicate_pair(world: World) -> None:
            occurrences = world["commodity_occurrences"]
            occurrences[1]["resource_deposit_id"] = occurrences[0][
                "resource_deposit_id"
            ]
            occurrences[1]["commodity"] = occurrences[0]["commodity"]

        self.assert_each(
            [
                (
                    "potential_out_of_range",
                    set_record("commodity_occurrences", "occurrence_potential_index", 5.0),
                    "commodity occurrence records invalid",
                ),
                (
                    "duplicate_id",
                    set_record("commodity_occurrences", "id", 0, index=1),
                    "commodity occurrence ids are not unique",
                ),
                (
                    "duplicate_deposit_commodity_pair",
                    duplicate_pair,
                    "commodity occurrence deposit/commodity pairs are not unique",
                ),
            ]
        )


class LandUseZoneRecordCase(ValidateTamperCase):
    """Record audits for agricultural and mining zones."""

    def test_land_use_cell_violations(self) -> None:
        self.assert_reports(
            [set_cell("mining_potential_index", 5.0)],
            "land use zone cell fields invalid",
        )

    def test_land_use_zone_record_violations(self) -> None:
        self.assert_each(
            [
                (
                    "settlement_ids_not_a_list",
                    set_record("agricultural_zones", "settlement_ids", "not-a-list"),
                    "land use zone records invalid",
                ),
                (
                    "cell_ids_unknown",
                    set_record("agricultural_zones", "cell_ids", [999_999]),
                    "land use zone records invalid",
                ),
                (
                    "agricultural_cell_count_mismatch",
                    set_record("agricultural_zones", "cell_count", 999_999),
                    "agricultural zone membership does not match cells",
                ),
                (
                    "mining_cell_count_mismatch",
                    set_record("mining_zones", "cell_count", 999_999),
                    "mining zone membership does not match cells",
                ),
                (
                    "duplicate_agricultural_zone_id",
                    set_record("agricultural_zones", "id", 0, index=1),
                    "agricultural zone ids are not unique",
                ),
                (
                    "duplicate_mining_zone_id",
                    set_record("mining_zones", "id", 0, index=1),
                    "mining zone ids are not unique",
                ),
            ]
        )


class NaturalFrontierRecordCase(ValidateTamperCase):
    """Record audits for natural frontiers."""

    def test_frontier_cell_violations(self) -> None:
        self.assert_reports(
            [set_cell("natural_frontier_index", 5.0)],
            "natural frontier cell fields invalid",
        )

    def test_frontier_record_violations(self) -> None:
        self.assert_each(
            [
                (
                    "region_ids_not_a_list",
                    set_record("natural_frontiers", "region_ids", "not-a-list"),
                    "natural frontier records invalid",
                ),
                (
                    "border_ids_unknown",
                    set_record("natural_frontiers", "border_ids", [999_999]),
                    "natural frontier records invalid",
                ),
                (
                    "cell_count_mismatch",
                    set_record("natural_frontiers", "cell_count", 999_999),
                    "natural frontier membership does not match cells",
                ),
            ]
        )


class WorldbuildingRealismRecordCase(ValidateTamperCase):
    """Record audit for the worldbuilding realism checks."""

    def test_realism_check_record_violations(self) -> None:
        self.assert_reports(
            [set_record("worldbuilding_realism_checks", "score", 5.0)],
            "worldbuilding realism check records invalid",
        )


class RouteCorridorRecordCase(ValidateTamperCase):
    """Record audits for route corridors."""

    def test_route_corridor_cell_violations(self) -> None:
        # As above, the ``except (TypeError, ValueError)`` arm is unreachable
        # through the CLI: a non-numeric corridor index dies in an earlier
        # bare ``float()`` before this guard is consulted.
        self.assert_reports(
            [set_cell("mountain_pass_route_index", 5.0)],
            "route corridor cell fields invalid",
        )

    def test_route_corridor_record_violations(self) -> None:
        # ``route_id`` is the one field of the corridor parse that survives to
        # the reporting gate when it is non-numeric: ``id`` dies inside
        # ``_validate_route_corridors``, which runs first, and ``cell_ids`` dies
        # in a later bare ``int()`` over every corridor.
        def retype_route(route_type: str) -> Tamper:
            def tamper(world: World) -> None:
                corridor = world["route_corridors"][0]
                route_id = int(corridor["route_id"])
                corridor["route_type"] = route_type
                corridor["detour_ratio"] = float(corridor["detour_ratio"]) + 1.0
                for route in world["routes"]:
                    if int(route["id"]) == route_id:
                        route["type"] = route_type
                        return
                raise AssertionError(
                    "route corridor does not reference an exported route"
                )

            return tamper

        self.assert_each(
            [
                (
                    "route_id_not_numeric",
                    set_record("route_corridors", "route_id", "not-a-number"),
                    "route corridor records invalid",
                ),
                (
                    "cell_count_mismatch",
                    set_record("route_corridors", "cell_count", 999_999),
                    "route corridor records invalid",
                ),
                (
                    "detour_ratio_mismatch",
                    set_record("route_corridors", "detour_ratio", 99.0),
                    "route corridor records invalid",
                ),
                (
                    "river_corridor_route_type",
                    retype_route("river_corridor"),
                    "route corridor records invalid",
                ),
                (
                    "fallback_route_type",
                    retype_route("coastal_sea"),
                    "route corridor records invalid",
                ),
            ]
        )

    def test_route_corridor_path_must_be_adjacent(self) -> None:
        def divert_path(world: World) -> None:
            corridor = world["route_corridors"][0]
            path = [int(cell_id) for cell_id in corridor["cell_ids"]]
            if len(path) < 3:
                raise AssertionError("shortest corridor is too short to divert")
            cells_by_id = {int(cell["id"]): cell for cell in world["cells"]}
            neighbours = {
                int(neighbour) for neighbour in cells_by_id[path[0]]["neighbors"]
            }
            for candidate in sorted(cells_by_id):
                if candidate not in neighbours and candidate not in path:
                    path[1] = candidate
                    break
            else:  # pragma: no cover - a sphere always has non-adjacent cells
                raise AssertionError("no non-adjacent cell available")
            corridor["cell_ids"] = path
            route_id = int(corridor["route_id"])
            for route in world["routes"]:
                if int(route["id"]) == route_id:
                    route["path_cell_ids"] = path
                    return
            raise AssertionError("route corridor does not reference an exported route")

        self.assert_reports(
            [divert_path],
            "route corridor records invalid",
            "route corridor cell id references invalid",
        )


class PhonologyRecordCase(ValidateTamperCase):
    """Every ``phonology_invalid`` arm reachable through the CLI."""

    message = "phonological history records invalid"

    def _foreign_rule_id(self, world: World) -> int:
        """A phonological rule id that belongs to a different language."""

        first = int(world["phonological_rules"][0]["language_region_id"])
        for rule in world["phonological_rules"]:
            if int(rule["language_region_id"]) != first:
                return int(rule["id"])
        raise AssertionError("world has only one language with phonological rules")

    def test_rule_and_correspondence_violations(self) -> None:
        def foreign_applied_rule(world: World) -> None:
            record = world["lexical_correspondences"][0]
            record["applied_rule_ids"] = [self._foreign_rule_id(world)]
            record["applied_rule_count"] = 1

        self.assert_each(
            [
                (
                    "rule_stage_index",
                    set_record("phonological_rules", "stage_index", 0),
                    self.message,
                ),
                (
                    "correspondence_syllable_count",
                    set_record("lexical_correspondences", "syllable_count", 0),
                    self.message,
                ),
                ("correspondence_foreign_rule", foreign_applied_rule, self.message),
            ]
        )

    def test_phonological_history_violations(self) -> None:
        def foreign_rule_set(world: World) -> None:
            history = world["phonological_histories"][0]
            foreign = self._foreign_rule_id(world)
            rule_ids = list(history["sound_change_rule_ids"])
            rule_ids[0] = foreign
            history["sound_change_rule_ids"] = rule_ids

        def foreign_step_rule(world: World) -> None:
            history = world["phonological_histories"][0]
            step = history["steps"][0]
            step["rule_ids"] = [self._foreign_rule_id(world)]
            step["rule_count"] = 1

        self.assert_each(
            [
                (
                    "allowed_coda_count",
                    set_record("phonological_histories", "allowed_coda_count", 0),
                    self.message,
                ),
                ("rule_set_mismatch", foreign_rule_set, self.message),
                (
                    "step_stage_index",
                    lambda world: world["phonological_histories"][0]["steps"][0].update(
                        {"stage_index": 999}
                    ),
                    self.message,
                ),
                ("step_foreign_rule", foreign_step_rule, self.message),
                (
                    "final_inventory_size",
                    set_record(
                        "phonological_histories", "final_phoneme_inventory_size", 99
                    ),
                    self.message,
                ),
            ]
        )

    def test_history_rule_must_belong_to_its_language(self) -> None:
        """A history rule id that resolves to another language's rule fails.

        The guard sits behind a set-equality test against ``rules_by_language``,
        which is grouped from the very records the ids come from, so it is only
        reachable when two rules share an id: the dict comprehension that builds
        ``phonological_rule_by_id`` keeps the last record for a duplicated id,
        which then belongs to the wrong language.
        """

        def duplicate_rule_id_across_languages(world: World) -> None:
            rules = world["phonological_rules"]
            owner = int(rules[0]["language_region_id"])
            target = int(rules[0]["id"])
            for rule in rules[1:]:
                if int(rule["language_region_id"]) != owner:
                    self.assertNotEqual(int(rule["id"]), target)
                    rule["id"] = target
                    return
            raise AssertionError("world has only one language with phonological rules")

        self.assert_reports([duplicate_rule_id_across_languages], self.message)

    def test_lexical_diffusion_violations(self) -> None:
        self.assert_each(
            [
                (
                    "step_count_mismatch",
                    set_record("lexical_diffusion_histories", "step_count", 99),
                    self.message,
                ),
                (
                    "step_domain_count",
                    lambda world: world["lexical_diffusion_histories"][0]["steps"][
                        0
                    ].update({"affected_domain_count": -1}),
                    self.message,
                ),
                (
                    "mean_adoption_mismatch",
                    set_record(
                        "lexical_diffusion_histories", "mean_diffusion_adoption_index", 0.0
                    ),
                    self.message,
                ),
            ]
        )

    def test_speaker_population_violations(self) -> None:
        def raise_step_contact(world: World) -> None:
            world["speaker_population_histories"][0]["steps"][0][
                "contact_pressure_index"
            ] = 0.9

        self.assert_each(
            [
                (
                    "step_count_mismatch",
                    set_record("speaker_population_histories", "step_count", 99),
                    self.message,
                ),
                (
                    "step_stage_index",
                    lambda world: world["speaker_population_histories"][0]["steps"][
                        0
                    ].update({"stage_index": 999}),
                    self.message,
                ),
                ("step_high_contact", raise_step_contact, self.message),
                (
                    "high_contact_flag",
                    set_record(
                        "speaker_population_histories",
                        "high_contact_speaker_history",
                        True,
                    ),
                    self.message,
                ),
                (
                    "language_allowed_coda_count",
                    set_record("language_regions", "allowed_coda_count", 0),
                    self.message,
                ),
            ]
        )


class PopulationHistoryRecordCase(ValidateTamperCase):
    """Record audit for population histories."""

    message = "population history fields invalid"

    def test_population_history_violations(self) -> None:
        def break_step_continuity(world: World) -> None:
            step = world["population_histories"][0]["steps"][0]
            step["end_population"] = float(step["end_population"]) + 1.0e9
            step["population_change"] = float(step["population_change"]) + 1.0e9

        def inflate_final_population(world: World) -> None:
            history = world["population_histories"][0]
            history["final_population"] = float(history["final_population"]) + 1.0e9

        self.assert_each(
            [
                (
                    "time_step_count",
                    set_record("population_histories", "time_step_count", 99),
                    self.message,
                ),
                (
                    "step_era_id",
                    lambda world: world["population_histories"][0]["steps"][0].update(
                        {"era_id": 999}
                    ),
                    self.message,
                ),
                (
                    "step_carrying_capacity",
                    lambda world: world["population_histories"][0]["steps"][0].update(
                        {"carrying_capacity": 0.0}
                    ),
                    self.message,
                ),
                ("step_continuity", break_step_continuity, self.message),
                ("final_population", inflate_final_population, self.message),
            ]
        )
