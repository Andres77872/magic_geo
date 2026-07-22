"""Public ``validate`` CLI violations for climate, ocean, and cryosphere.

``magic-geo validate`` accumulates every complaint into one list and prints it
as ``FAIL <message>`` lines before exiting 1, so a healthy generated world never
reaches the reporting code. Each case here takes the 128-cell replay world,
disturbs exactly one derived quantity, and asserts the CLI answers with the one
message that check owns.

Independent checks live behind the same reporting gate, so a case group applies
several unrelated tampers -- one per record family -- in a single invocation and
pins each expected message separately. Every group first asserts the untampered
control run of the same world exits 0 and prints no ``FAIL`` line at all, so a
message can only come from the tamper.

Two habits keep a case from passing for the wrong reason. The tamper builders
refuse to write a value the world already holds, so a hardcoded replacement that
collides with the generated one is an error rather than a silent no-op. And a
rejected run is checked for more than its exit code: a command that raises
reaches the runner as exit code 1 with an empty report, indistinguishable from a
clean verdict until you look at the exception it caught, so every run insists on
``SystemExit``, on at least one ``FAIL`` line, and on the expected message
opening a line of its own.

The slice covered here is the port-site, atmospheric circulation, seasonal wind,
vapour budget, ocean circulation, continentality, seasonal-climate, climate
energy, planet/climate realism, permafrost, ice sheet, ice flowline, glacial
landform and soil-profile reporting of ``magic_geo.cli.commands.validate``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, NamedTuple, Sequence
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

WORLD_KEY = "replay_128"

MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}

Tamper = Callable[[dict[str, Any]], None]


class Case(NamedTuple):
    """One tamper and the single ``FAIL`` message it must provoke."""

    name: str
    message: str
    tamper: Tamper


_base_world_cache: dict[str, Any] | None = None
_control_cache: tuple[int, str] | None = None


def _base_world() -> dict[str, Any]:
    """The pristine generated world, generated at most once per process."""
    global _base_world_cache
    if _base_world_cache is None:
        _base_world_cache = worlds.cached_world(WORLD_KEY)
    return _base_world_cache


def _control_run() -> tuple[int, str]:
    """Exit code and output of ``validate`` on the untampered world."""
    global _control_cache
    if _control_cache is None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "control.json"
            write_json(path, _base_world())
            result = CliRunner().invoke(app, ["validate", "--world", str(path)])
        _control_cache = (result.exit_code, result.output)
    return _control_cache


# --------------------------------------------------------------------------
# tamper builders
#
# Every builder refuses to write a value the world already holds: a tamper that
# leaves the payload untouched would make its case pass for no reason, and a
# hardcoded replacement can silently collide with the generated value.
# --------------------------------------------------------------------------


def _replacement(before: Any, after: Any, what: str) -> Any:
    """``after``, unless writing it over ``before`` would change nothing."""
    if before == after:
        raise AssertionError(f"tamper is a no-op: {what} already is {after!r}")
    return after


def _existing(container: Any, key: Any, what: str) -> Any:
    """The current value at ``key``, insisting the world really has one."""
    if key not in container:
        raise AssertionError(f"tamper has nothing to work on: {what} is absent")
    return container[key]


def summary_scaled(key: str, factor: float = 1.01) -> Tamper:
    """Scale a summary metric whose tolerance is relative to its magnitude."""

    def tamper(payload: dict[str, Any]) -> None:
        summary = payload["summary"]
        before = float(_existing(summary, key, f"summary[{key!r}]"))
        summary[key] = _replacement(before, before * factor, f"summary[{key!r}]")

    return tamper


def summary_shifted(key: str, delta: float) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        summary = payload["summary"]
        before = float(_existing(summary, key, f"summary[{key!r}]"))
        summary[key] = _replacement(before, before + delta, f"summary[{key!r}]")

    return tamper


def summary_counted(key: str, delta: int = 1) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        summary = payload["summary"]
        before = int(_existing(summary, key, f"summary[{key!r}]"))
        summary[key] = _replacement(before, before + delta, f"summary[{key!r}]")

    return tamper


def summary_set(key: str, value: Any) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        summary = payload["summary"]
        before = _existing(summary, key, f"summary[{key!r}]")
        summary[key] = _replacement(before, value, f"summary[{key!r}]")

    return tamper


def summary_dropped(key: str) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        _existing(payload["summary"], key, f"summary[{key!r}]")
        del payload["summary"][key]

    return tamper


def summary_bucket(key: str, bucket: str, delta: int = 1) -> Tamper:
    """Move one entry of a summary histogram away from the records."""

    def tamper(payload: dict[str, Any]) -> None:
        histogram = _existing(payload["summary"], key, f"summary[{key!r}]")
        what = f"summary[{key!r}][{bucket!r}]"
        before = int(_existing(histogram, bucket, what))
        histogram[bucket] = _replacement(before, before + delta, what)

    return tamper


def summary_bucket_added(key: str, bucket: str, value: int = 0) -> Tamper:
    """Give a summary histogram a bucket the records know nothing about."""

    def tamper(payload: dict[str, Any]) -> None:
        histogram = _existing(payload["summary"], key, f"summary[{key!r}]")
        if bucket in histogram:
            raise AssertionError(f"tamper is a no-op: summary[{key!r}] already has {bucket!r}")
        histogram[bucket] = value

    return tamper


def first_cell_field_dropped(field: str) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        _existing(payload["cells"][0], field, f"cells[0][{field!r}]")
        del payload["cells"][0][field]

    return tamper


def first_cell_field_set(field: str, value: Any) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        cell = payload["cells"][0]
        what = f"cells[0][{field!r}]"
        cell[field] = _replacement(_existing(cell, field, what), value, what)

    return tamper


def record_field_dropped(collection: str, field: str, index: int = 0) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        record = payload[collection][index]
        _existing(record, field, f"{collection}[{index}][{field!r}]")
        del record[field]

    return tamper


def record_field_set(collection: str, field: str, value: Any, index: int = 0) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        record = payload[collection][index]
        what = f"{collection}[{index}][{field!r}]"
        record[field] = _replacement(_existing(record, field, what), value, what)

    return tamper


def record_field_shifted(collection: str, field: str, delta: float, index: int = 0) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        record = payload[collection][index]
        what = f"{collection}[{index}][{field!r}]"
        before = float(_existing(record, field, what))
        record[field] = _replacement(before, before + delta, what)

    return tamper


def nested_field_set(path: Sequence[Any], field: Any, value: Any) -> Tamper:
    """Overwrite one leaf reached by walking ``path`` from the payload root."""

    def tamper(payload: dict[str, Any]) -> None:
        node: Any = payload
        for step in path:
            node = node[step]
        what = "".join(f"[{step!r}]" for step in (*path, field))
        node[field] = _replacement(_existing(node, field, what), value, what)

    return tamper


def nested_key_dropped(path: Sequence[Any], key: Any) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        node: Any = payload
        for step in path:
            node = node[step]
        _existing(node, key, "".join(f"[{step!r}]" for step in (*path, key)))
        del node[key]

    return tamper


def record_id_duplicated(collection: str) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        records = payload[collection]
        if len(records) < 2:
            raise AssertionError(f"{collection} has fewer than two records to collide")
        records[1]["id"] = _replacement(records[1]["id"], records[0]["id"], f"{collection}[1]['id']")

    return tamper


def last_record_dropped(collection: str) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        records = payload[collection]
        if not records:
            raise AssertionError(f"{collection} is empty, so dropping its last record changes nothing")
        records.pop()

    return tamper


def collection_replaced(collection: str, value: Any) -> Tamper:
    def tamper(payload: dict[str, Any]) -> None:
        before = _existing(payload, collection, collection)
        payload[collection] = _replacement(before, value, collection)

    return tamper


def promote_land_cell_to_port_candidate(payload: dict[str, Any]) -> None:
    """Make one ice-free land cell port-worthy without giving it a port site."""
    for cell in payload["cells"]:
        if (
            not cell.get("is_water", False)
            and float(cell.get("port_suitability_index", 0.0)) < 0.58
            and float(cell.get("ice_thickness_m", 0.0)) < 80.0
            and str(cell.get("biome", "")) != "ice_cap"
            and int(cell.get("port_site_id", -1)) < 0
        ):
            cell["port_suitability_index"] = 0.9
            return
    raise AssertionError("world has no ice-free land cell below the port threshold")


def slow_one_marine_current(payload: dict[str, Any]) -> None:
    """Break the speed a marine cell's own current vector implies."""
    for cell in payload["cells"]:
        if (
            str(cell.get("water_body_type", "land")) in MARINE_WATER_TYPES
            and int(cell.get("ocean_current_system_id", -1)) >= 0
            and float(cell.get("ocean_current_speed_index", 0.0)) != 0.9
        ):
            cell["ocean_current_speed_index"] = 0.9
            return
    raise AssertionError("world has no marine cell inside an ocean current system")


def repoint_energy_record_at_another_cell(payload: dict[str, Any]) -> None:
    records = payload["climate_energy_balance_records"]
    records[0]["cell_id"] = _replacement(
        int(records[0]["cell_id"]),
        int(records[1]["cell_id"]),
        "climate_energy_balance_records[0]['cell_id']",
    )


def _reported(output: str, message: str) -> list[str]:
    """The report lines that belong to the check owning ``message``."""
    return [line for line in output.splitlines() if line.startswith(f"FAIL {message}")]


class _ValidateTamperCase(TestCase):
    """Machinery shared by the tamper groups. Declares no tests of its own."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = TemporaryDirectory()
        cls._world_path = Path(cls._directory.name) / "tampered.json"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()

    def assert_control_passes(self) -> str:
        """The untampered world validates cleanly; returns its output."""
        exit_code, output = _control_run()
        self.assertEqual(exit_code, 0, output)
        self.assertNotIn("FAIL", output)
        return output

    def _rejected_output(self, tampers: Sequence[Tamper]) -> str:
        payload = copy.deepcopy(_base_world())
        for tamper in tampers:
            tamper(payload)
        write_json(self._world_path, payload)
        result = CliRunner().invoke(app, ["validate", "--world", str(self._world_path)])
        assert_no_cli_crash(self, result)
        # A command that raises reaches the caller as exit code 1 with nothing on
        # stdout, exactly like a reported violation, so the exception the runner
        # caught is the only thing that separates a crash from a clean verdict:
        # ``typer.Exit`` leaves a ``SystemExit`` behind, a bug leaves its own type.
        raised = result.exc_info[0] if result.exc_info is not None else None
        self.assertIs(raised, SystemExit, f"validate raised {result.exception!r} instead of reporting")
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertTrue(
            [line for line in result.output.splitlines() if line.startswith("FAIL ")],
            f"validate exited 1 without reporting anything: {result.output!r}",
        )
        return result.output

    def assert_message(self, output: str, message: str) -> None:
        """The report opens a line with ``message``; matching mid-line will not do."""
        self.assertTrue(
            _reported(output, message),
            f"no FAIL line begins with {message!r}; the run reported:\n{output}",
        )

    def assert_rejects(self, cases: Sequence[Case]) -> None:
        """Apply every tamper to one copy of the world and check each message."""
        control_output = self.assert_control_passes()
        output = self._rejected_output([case.tamper for case in cases])
        for case in cases:
            with self.subTest(case=case.name):
                self.assertFalse(_reported(control_output, case.message))
                self.assert_message(output, case.message)

    def assert_reports(self, tamper: Tamper, messages: Sequence[str]) -> None:
        """One tamper whose single defect several checks are meant to notice."""
        control_output = self.assert_control_passes()
        output = self._rejected_output([tamper])
        for message in messages:
            with self.subTest(message=message):
                self.assertFalse(_reported(control_output, message))
                self.assert_message(output, message)


class UntamperedWorld(TestCase):
    """The fixture every tamper is measured against."""

    def test_validate_accepts_the_generated_world(self) -> None:
        exit_code, output = _control_run()
        self.assertEqual(exit_code, 0, output)
        self.assertNotIn("FAIL", output)
        self.assertIn("OK", output)


class PortSiteReporting(_ValidateTamperCase):
    """Port site records, their summary counters and their cell membership."""

    def test_summary_counters_must_match_port_records(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "port_settlement_count",
                    "port_settlement_count does not match settlements",
                    summary_counted("port_settlement_count"),
                ),
                Case(
                    "port_settlement_with_site_count",
                    "port_settlement_with_site_count does not match settlements",
                    summary_counted("port_settlement_with_site_count"),
                ),
                Case(
                    "port_site_total_area_km2",
                    "port_site_total_area_km2 does not match records",
                    summary_shifted("port_site_total_area_km2", 1000.0),
                ),
                Case(
                    "port_site_type_counts",
                    "port_site_type_counts does not match records",
                    summary_bucket("port_site_type_counts", "strait_port"),
                ),
                Case(
                    "strait_port_site_count",
                    "strait_port_site_count does not match records",
                    summary_counted("strait_port_site_count"),
                ),
            ]
        )

    def test_duplicate_port_site_id_is_reported(self) -> None:
        self.assert_rejects(
            [Case("duplicate_id", "port site ids are not unique", record_id_duplicated("port_sites"))]
        )

    def test_port_site_area_must_match_its_cell(self) -> None:
        self.assert_rejects(
            [Case("area", "port site records invalid", record_field_shifted("port_sites", "area_km2", 5.0))]
        )

    def test_port_candidate_without_a_site_is_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "membership",
                    "port site membership does not match cells",
                    promote_land_cell_to_port_candidate,
                )
            ]
        )


class MissingSummaryMetrics(_ValidateTamperCase):
    """Every domain's "summary metrics missing" guard, one key removed each."""

    def test_dropped_summary_keys_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case("landform", "landform_counts missing", summary_set("landform_counts", {})),
                Case(
                    "orographic",
                    "orographic/rain-shadow summary metrics missing",
                    summary_dropped("mean_orographic_factor"),
                ),
                Case(
                    "wind_path",
                    "wind-path humidity summary metrics missing",
                    summary_dropped("mean_humidity_transport_index"),
                ),
                Case(
                    "atmospheric",
                    "atmospheric circulation summary metrics missing",
                    summary_dropped("ascending_air_fraction"),
                ),
                Case(
                    "seasonal_wind",
                    "seasonal wind summary metrics missing",
                    summary_dropped("mean_seasonal_wind_reversal_index"),
                ),
                Case(
                    "vapor_budget",
                    "vapor-budget summary metrics missing",
                    summary_dropped("mean_vapor_evaporation_mm_y"),
                ),
                Case(
                    "ocean_current",
                    "ocean-current summary metrics missing",
                    summary_dropped("mean_ocean_current_strength"),
                ),
                Case(
                    "ocean_circulation",
                    "ocean circulation summary metrics missing",
                    summary_dropped("ocean_current_cell_count"),
                ),
                Case(
                    "continentality",
                    "climate continentality summary metrics missing",
                    summary_dropped("mean_continentality_index"),
                ),
                Case(
                    "climate_energy",
                    "climate energy summary metrics missing",
                    summary_dropped("mean_surface_albedo_index"),
                ),
                Case(
                    "planet_realism",
                    "planet realism summary metrics missing",
                    summary_dropped("mean_planet_realism_score"),
                ),
                Case(
                    "climate_realism",
                    "climate realism summary metrics missing",
                    summary_dropped("orographic_rain_shadow_index"),
                ),
                Case("cryosphere", "cryosphere summary metrics missing", summary_dropped("mean_ice_thickness_m")),
                Case(
                    "cryosphere_dynamic",
                    "cryosphere dynamic summary metrics missing",
                    summary_dropped("mean_basal_sliding_index"),
                ),
                Case("permafrost", "permafrost summary metrics missing", summary_dropped("mean_active_layer_depth_m")),
                Case(
                    "glacial",
                    "glacial landform summary metrics missing",
                    summary_dropped("mean_glacial_meltwater_index"),
                ),
                Case("soil", "soil diagnostic summary metrics missing", summary_dropped("mean_soil_ph")),
            ]
        )


class MissingCellFields(_ValidateTamperCase):
    """Each domain probes the first cell for its own derived fields."""

    def test_dropped_cell_fields_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "atmospheric",
                    "atmospheric circulation cell fields missing",
                    first_cell_field_dropped("vertical_velocity_index"),
                ),
                Case(
                    "vapor_budget",
                    "vapor-budget cell fields missing",
                    first_cell_field_dropped("moisture_convergence_mm_y"),
                ),
                Case(
                    "ocean_circulation",
                    "ocean circulation cell fields missing",
                    first_cell_field_dropped("ocean_upwelling_index"),
                ),
                Case(
                    "seasonal_climate",
                    "seasonal climate cell fields missing",
                    first_cell_field_dropped("cell_monsoon_index"),
                ),
                Case(
                    "cryosphere",
                    "cryosphere dynamic cell fields missing",
                    first_cell_field_dropped("basal_sliding_index"),
                ),
                Case(
                    "permafrost",
                    "permafrost cell fields missing",
                    first_cell_field_dropped("ground_ice_content_index"),
                ),
                Case(
                    "ice_flowline",
                    "ice flowline cell fields missing",
                    first_cell_field_dropped("ice_flowline_driving_stress_kpa"),
                ),
                Case(
                    "glacial",
                    "glacial landform cell fields missing",
                    first_cell_field_dropped("glacial_meltwater_index"),
                ),
                Case("soil", "soil diagnostic cell fields missing", first_cell_field_dropped("soil_ph")),
            ]
        )


class InvalidCellFields(_ValidateTamperCase):
    """Per-cell replays reject values their own inputs cannot produce."""

    def test_out_of_range_cell_values_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "seasonal_wind",
                    "seasonal wind cell fields invalid",
                    first_cell_field_set("wind_monthly_east", [0.0] * 11),
                ),
                Case(
                    "continentality",
                    "climate continentality cell fields invalid",
                    first_cell_field_set("continentality_index", 1.5),
                ),
                Case(
                    "permafrost",
                    "permafrost cell fields invalid",
                    first_cell_field_set("permafrost_extent_index", 1.5),
                ),
                Case(
                    "glacial",
                    "glacial landform cell fields invalid",
                    first_cell_field_set("glacial_landform_index", 1.5),
                ),
                Case("ocean_current", "ocean circulation cell fields invalid", slow_one_marine_current),
            ]
        )


class AtmosphericAndWindRanges(_ValidateTamperCase):
    """Summary metrics whose physical range the command polices."""

    def test_out_of_range_summary_metrics_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "pressure",
                    "mean_surface_pressure_anomaly_hpa out of range",
                    summary_set("mean_surface_pressure_anomaly_hpa", 25.0),
                ),
                Case(
                    "vertical_velocity",
                    "mean_vertical_velocity_index out of range",
                    summary_set("mean_vertical_velocity_index", 2.0),
                ),
                Case(
                    "wind_divergence",
                    "mean_wind_divergence_index out of range",
                    summary_set("mean_wind_divergence_index", -2.0),
                ),
                Case(
                    "ascending_air",
                    "ascending_air_fraction out of range",
                    summary_set("ascending_air_fraction", 1.5),
                ),
                Case(
                    "wind_speed",
                    "mean_seasonal_wind_speed out of range",
                    summary_set("mean_seasonal_wind_speed", 1.6),
                ),
                Case(
                    "wind_reversal",
                    "mean_seasonal_wind_reversal_index out of range",
                    summary_set("mean_seasonal_wind_reversal_index", 1.4),
                ),
                Case(
                    "atmospheric_counts",
                    "atmospheric_cell_counts does not match cell_count",
                    summary_bucket("atmospheric_cell_counts", "polar_cell"),
                ),
            ]
        )

    def test_in_range_but_wrong_wind_means_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "wind_speed",
                    "mean_seasonal_wind_speed does not match cells",
                    summary_shifted("mean_seasonal_wind_speed", 0.01),
                ),
                Case(
                    "wind_reversal",
                    "mean_seasonal_wind_reversal_index does not match cells",
                    summary_shifted("mean_seasonal_wind_reversal_index", 0.01),
                ),
                Case(
                    "vapor_residual",
                    "vapor-budget residual too large",
                    summary_set("mean_abs_vapor_budget_residual_mm_y", 2.0),
                ),
            ]
        )


class OceanCirculationSummary(_ValidateTamperCase):
    """Ocean circulation aggregates recomputed from cells and systems."""

    def test_summary_aggregates_must_match_records(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "warm_cells",
                    "warm_ocean_current_cell_count does not match ocean circulation records",
                    summary_counted("warm_ocean_current_cell_count"),
                ),
                Case(
                    "upwelling",
                    "mean_ocean_upwelling_index does not match ocean circulation cells",
                    summary_shifted("mean_ocean_upwelling_index", 0.01),
                ),
                Case(
                    "regime_counts",
                    "ocean_current_regime_counts does not match cells",
                    summary_bucket("ocean_current_regime_counts", "non_marine"),
                ),
                Case(
                    "system_class_counts",
                    "ocean_current_system_class_counts does not match systems",
                    summary_bucket("ocean_current_system_class_counts", "cold_poleward_current"),
                ),
            ]
        )


class OceanCirculationRecords(_ValidateTamperCase):
    """Ocean current systems and their transport edges."""

    def test_non_list_collections_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "systems",
                    "ocean_current_systems missing",
                    collection_replaced("ocean_current_systems", {}),
                ),
                Case(
                    "edges",
                    "ocean_current_transport_edges missing",
                    collection_replaced("ocean_current_transport_edges", 5),
                ),
            ]
        )

    def test_dropped_record_fields_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "system",
                    "ocean current system fields missing",
                    record_field_dropped("ocean_current_systems", "hemisphere"),
                ),
                Case(
                    "edge",
                    "ocean current transport edge fields missing",
                    record_field_dropped("ocean_current_transport_edges", "alignment"),
                ),
            ]
        )

    def test_record_values_must_match_their_cells(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "system_cell_count",
                    "ocean current system records invalid",
                    record_field_set("ocean_current_systems", "cell_count", 99),
                ),
                Case(
                    "edge_distance",
                    "ocean current transport edge records invalid",
                    record_field_shifted("ocean_current_transport_edges", "great_circle_distance_km", 5.0),
                ),
            ]
        )

    def test_dropped_system_loses_a_regime_component(self) -> None:
        self.assert_reports(
            last_record_dropped("ocean_current_systems"),
            [
                "ocean current systems do not match canonical regime components",
                "ocean current system membership does not match marine cells",
            ],
        )

    def test_dropped_transport_edge_is_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "edges",
                    "ocean current transport edges do not match cell targets",
                    last_record_dropped("ocean_current_transport_edges"),
                )
            ]
        )


class ClimateContinentality(_ValidateTamperCase):
    """Distance-to-marine-water diagnostics and their regions."""

    def test_summary_aggregates_must_match_cells(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "max_index",
                    "max_continentality_index does not match climate continentality cells",
                    summary_shifted("max_continentality_index", 0.01),
                ),
                Case(
                    "high_cells",
                    "high_continentality_cell_count does not match cells",
                    summary_counted("high_continentality_cell_count"),
                ),
                Case(
                    "low_humidity_cells",
                    "low_oceanic_humidity_availability_cell_count does not match cells",
                    summary_counted("low_oceanic_humidity_availability_cell_count"),
                ),
                Case(
                    "class_counts",
                    "marine_influence_class_counts does not match cells",
                    summary_bucket("marine_influence_class_counts", "interior"),
                ),
                Case(
                    "region_count",
                    "climate_continentality_region_count does not match records",
                    summary_counted("climate_continentality_region_count"),
                ),
                Case(
                    "core_regions",
                    "continental_core_region_count does not match records",
                    summary_counted("continental_core_region_count"),
                ),
                Case(
                    "maritime_regions",
                    "maritime_influence_region_count does not match records",
                    summary_counted("maritime_influence_region_count"),
                ),
            ]
        )

    def test_non_list_region_collection_is_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "regions",
                    "climate_continentality_regions missing",
                    collection_replaced("climate_continentality_regions", None),
                )
            ]
        )

    def test_region_cell_count_must_match_its_members(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "cell_count",
                    "climate continentality region records invalid",
                    record_field_set("climate_continentality_regions", "cell_count", 999),
                )
            ]
        )


class ClimateSeasonalHistories(_ValidateTamperCase):
    """Monthly humidity budgets per atmospheric cell group."""

    def test_summary_counters_must_match_histories(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "history_count",
                    "climate_seasonal_history_count does not match histories length",
                    summary_counted("climate_seasonal_history_count"),
                ),
                Case(
                    "groups",
                    "climate seasonal histories do not match atmospheric cell groups",
                    summary_bucket_added("atmospheric_cell_counts", "ghost_cell"),
                ),
                Case(
                    "step_count",
                    "climate_seasonal_step_count does not match histories",
                    summary_counted("climate_seasonal_step_count"),
                ),
                Case(
                    "regime_counts",
                    "seasonal_humidity_regime_counts does not match cell_count",
                    summary_bucket("seasonal_humidity_regime_counts", "humid_stable"),
                ),
                Case(
                    "aridity_fraction",
                    "seasonal_aridity_cell_fraction out of range",
                    summary_set("seasonal_aridity_cell_fraction", 1.5),
                ),
                Case(
                    "aridity_index",
                    "mean_cell_seasonal_aridity_index out of range",
                    summary_set("mean_cell_seasonal_aridity_index", 2.0),
                ),
                Case(
                    "residual",
                    "climate seasonal humidity residual too large",
                    summary_set("climate_seasonal_mean_abs_residual_mm", 0.5),
                ),
            ]
        )

    def test_annual_totals_must_match_histories(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "precipitation",
                    "climate_seasonal_total_precipitation_mm does not match histories",
                    summary_shifted("climate_seasonal_total_precipitation_mm", 50.0),
                ),
                Case(
                    "evaporation",
                    "climate_seasonal_total_evaporation_mm does not match histories",
                    summary_shifted("climate_seasonal_total_evaporation_mm", 50.0),
                ),
                Case(
                    "convergence",
                    "climate_seasonal_total_moisture_convergence_mm does not match histories",
                    summary_shifted("climate_seasonal_total_moisture_convergence_mm", 50.0),
                ),
                Case(
                    "export",
                    "climate_seasonal_total_humidity_export_mm does not match histories",
                    summary_shifted("climate_seasonal_total_humidity_export_mm", 50.0),
                ),
                Case(
                    "deficit",
                    "climate_seasonal_total_vapor_deficit_mm does not match histories",
                    summary_shifted("climate_seasonal_total_vapor_deficit_mm", 50.0),
                ),
                Case(
                    "residual",
                    "climate_seasonal_mean_abs_residual_mm does not match histories",
                    summary_set("climate_seasonal_mean_abs_residual_mm", 0.002),
                ),
                Case(
                    "storage",
                    "max_climate_humidity_storage_mm does not match histories",
                    summary_shifted("max_climate_humidity_storage_mm", 50.0),
                ),
                Case(
                    "monsoon",
                    "max_climate_monsoon_index does not match histories",
                    summary_shifted("max_climate_monsoon_index", 0.01),
                ),
            ]
        )

    def test_history_steps_must_run_month_by_month(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "month",
                    "climate seasonal history fields invalid",
                    nested_field_set(("climate_seasonal_histories", 0, "steps", 0), "month", 7),
                )
            ]
        )

    def test_classification_metadata_must_describe_the_scheme(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "class_count",
                    "climate classification invalid",
                    nested_field_set(("climate_classification",), "available_class_count", 3),
                )
            ]
        )


class ClimateEnergyBalance(_ValidateTamperCase):
    """Per-cell radiative balance records."""

    def test_summary_aggregates_must_match_records(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "record_count",
                    "climate_energy_balance_record_count does not match records length",
                    summary_counted("climate_energy_balance_record_count"),
                ),
                Case(
                    "albedo_counts",
                    "surface_albedo_regime_counts does not match climate energy records",
                    summary_bucket("surface_albedo_regime_counts", "open_ocean"),
                ),
                Case(
                    "greenhouse_mean",
                    "mean_greenhouse_trapping_w_m2 does not match climate energy records",
                    summary_shifted("mean_greenhouse_trapping_w_m2", 1.0),
                ),
                Case(
                    "stress_count",
                    "high_climate_energy_stress_cell_count does not match records",
                    summary_counted("high_climate_energy_stress_cell_count"),
                ),
            ]
        )

    def test_non_list_record_collection_is_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "records",
                    "climate_energy_balance_records missing",
                    collection_replaced("climate_energy_balance_records", None),
                )
            ]
        )

    def test_dropped_record_leaves_a_cell_uncovered(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "length",
                    "climate_energy_balance_records length does not match cells",
                    last_record_dropped("climate_energy_balance_records"),
                )
            ]
        )

    def test_dropped_record_field_is_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "biome",
                    "climate energy record fields missing",
                    record_field_dropped("climate_energy_balance_records", "biome"),
                )
            ]
        )

    def test_albedo_must_match_its_cell(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "albedo",
                    "climate energy records invalid",
                    record_field_shifted("climate_energy_balance_records", "surface_albedo_index", 0.05),
                )
            ]
        )

    def test_duplicate_record_id_is_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "duplicate_id",
                    "climate energy record ids are not unique",
                    record_id_duplicated("climate_energy_balance_records"),
                )
            ]
        )

    def test_records_must_cover_every_cell(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "cell_ids",
                    "climate energy records do not match cells",
                    repoint_energy_record_at_another_cell,
                )
            ]
        )


class PlanetAndClimateRealism(_ValidateTamperCase):
    """Planet parameters plus the planet and climate realism check tables."""

    def test_summary_counters_must_match_checks(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "planet_check_count",
                    "planet_realism_check_count does not match planet_realism_checks length",
                    summary_counted("planet_realism_check_count"),
                ),
                Case(
                    "planet_pass_count",
                    "planet_realism_pass_count does not match planet realism checks",
                    summary_counted("planet_realism_pass_count"),
                ),
                Case(
                    "planet_pass_fraction",
                    "planet_realism_pass_fraction does not match checks",
                    summary_shifted("planet_realism_pass_fraction", -0.1),
                ),
                Case(
                    "planet_mean_score",
                    "mean_planet_realism_score does not match checks",
                    summary_shifted("mean_planet_realism_score", -0.1),
                ),
                Case(
                    "planet_index",
                    "global_liquid_water_temperature_index does not match planet realism check",
                    summary_shifted("global_liquid_water_temperature_index", 0.1),
                ),
                Case(
                    "climate_check_count",
                    "climate_realism_check_count does not match climate_realism_checks length",
                    summary_counted("climate_realism_check_count"),
                ),
                Case(
                    "climate_pass_count",
                    "climate_realism_pass_count does not match climate realism checks",
                    summary_counted("climate_realism_pass_count"),
                ),
                Case(
                    "climate_pass_fraction",
                    "climate_realism_pass_fraction does not match checks",
                    summary_shifted("climate_realism_pass_fraction", -0.1),
                ),
                Case(
                    "climate_mean_score",
                    "mean_climate_realism_score does not match checks",
                    summary_shifted("mean_climate_realism_score", -0.1),
                ),
                Case(
                    "climate_index",
                    "subtropical_dry_belt_index does not match climate realism check",
                    summary_shifted("subtropical_dry_belt_index", 0.1),
                ),
            ]
        )

    def test_incomplete_planet_parameters_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "internal_heat",
                    "planet_parameters missing or incomplete",
                    nested_key_dropped(("planet_parameters",), "internal_heat"),
                )
            ]
        )

    def test_out_of_range_planet_parameter_is_reported(self) -> None:
        # An age of zero is numeric, so the range test itself rejects it. The
        # non-numeric case below shares this message -- the command prints the
        # same constant from its range branch and from its conversion guard --
        # but only one of the two can be reached by a given tamper.
        self.assert_rejects(
            [
                Case(
                    "geological_age",
                    "planet_parameters values invalid",
                    nested_field_set(("planet_parameters",), "geological_age_ga", 0.0),
                )
            ]
        )

    def test_non_numeric_planet_parameter_is_reported(self) -> None:
        # Every other parameter stays in range, so the report can only come from
        # the conversion of "hot" raising rather than from the range test.
        self.assert_rejects(
            [
                Case(
                    "internal_heat",
                    "planet_parameters values invalid",
                    nested_field_set(("planet_parameters",), "internal_heat", "hot"),
                )
            ]
        )

    def test_dropped_check_fields_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "planet",
                    "planet realism check fields missing",
                    record_field_dropped("planet_realism_checks", "evidence"),
                ),
                Case(
                    "climate",
                    "climate realism check fields missing",
                    record_field_dropped("climate_realism_checks", "evidence"),
                ),
            ]
        )

    def test_out_of_range_check_values_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "planet_score",
                    "planet realism check records invalid",
                    record_field_set("planet_realism_checks", "score", 1.5),
                ),
                Case(
                    "climate_value",
                    "climate realism checks invalid",
                    record_field_set("climate_realism_checks", "value", 1.5),
                ),
            ]
        )


class CryosphereAndPermafrost(_ValidateTamperCase):
    """Ice-sheet dynamics summary ranges and the permafrost diagnostics."""

    def test_out_of_range_cryosphere_metrics_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "mass_balance",
                    "mean_ice_surface_mass_balance_m_y out of range",
                    summary_set("mean_ice_surface_mass_balance_m_y", 5.0),
                ),
                Case(
                    "basal_sliding",
                    "mean_basal_sliding_index out of range",
                    summary_set("mean_basal_sliding_index", 1.5),
                ),
                Case(
                    "velocity",
                    "mean_ice_velocity_m_y out of range",
                    summary_set("mean_ice_velocity_m_y", -1.0),
                ),
                Case(
                    "retreat_rate",
                    "mean_ice_sheet_retreat_rate_m_y out of range",
                    summary_set("mean_ice_sheet_retreat_rate_m_y", -1.0),
                ),
            ]
        )

    def test_permafrost_summary_must_match_cells(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "class_counts",
                    "permafrost_class_counts does not match cells",
                    summary_bucket("permafrost_class_counts", "no_permafrost"),
                ),
                Case(
                    "cell_count",
                    "permafrost_cell_count does not match cells",
                    summary_counted("permafrost_cell_count"),
                ),
                Case(
                    "region_count",
                    "permafrost_region_count does not match regions",
                    summary_counted("permafrost_region_count"),
                ),
                Case(
                    "continuous",
                    "continuous_permafrost_cell_count does not match cells",
                    summary_counted("continuous_permafrost_cell_count"),
                ),
                Case(
                    "ice_cemented",
                    "ice_cemented_permafrost_cell_count does not match cells",
                    summary_counted("ice_cemented_permafrost_cell_count"),
                ),
                Case(
                    "mean_extent",
                    "mean_permafrost_extent_index does not match cells",
                    summary_shifted("mean_permafrost_extent_index", 0.01),
                ),
            ]
        )

    def test_non_list_permafrost_regions_are_reported(self) -> None:
        self.assert_rejects(
            [Case("regions", "permafrost_regions missing", collection_replaced("permafrost_regions", None))]
        )

    def test_dropped_permafrost_region_field_is_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "frost_months",
                    "permafrost region fields missing",
                    record_field_dropped("permafrost_regions", "mean_frost_months"),
                )
            ]
        )

    def test_permafrost_region_cell_count_must_match(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "cell_count",
                    "permafrost region records invalid",
                    record_field_set("permafrost_regions", "cell_count", 99),
                )
            ]
        )

    def test_duplicate_permafrost_region_id_is_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "duplicate_id",
                    "permafrost region ids are not unique",
                    record_id_duplicated("permafrost_regions"),
                )
            ]
        )

    def test_dropped_permafrost_region_loses_its_cells(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "membership",
                    "permafrost region membership does not match cells",
                    last_record_dropped("permafrost_regions"),
                )
            ]
        )


class IceSheetHistories(_ValidateTamperCase):
    """Ice sheet mass-balance and stability histories."""

    def test_summary_totals_must_match_histories(self) -> None:
        self.assert_rejects(
            [
                Case("sheet_count", "ice_sheet_count does not match ice_sheets length", summary_counted("ice_sheet_count")),
                Case(
                    "history_count",
                    "ice_sheet_history_count does not match ice_sheet_histories length",
                    summary_counted("ice_sheet_history_count"),
                ),
                Case(
                    "history_steps",
                    "ice_sheet_history_step_count does not match ice sheet histories",
                    summary_counted("ice_sheet_history_step_count"),
                ),
                Case(
                    "surface_balance",
                    "ice_sheet_history_total_surface_balance_km3 does not match histories",
                    summary_scaled("ice_sheet_history_total_surface_balance_km3"),
                ),
                Case(
                    "dynamic_loss",
                    "ice_sheet_history_total_dynamic_loss_km3 does not match histories",
                    summary_scaled("ice_sheet_history_total_dynamic_loss_km3"),
                ),
                Case(
                    "retreat_loss",
                    "ice_sheet_history_total_retreat_loss_km3 does not match histories",
                    summary_shifted("ice_sheet_history_total_retreat_loss_km3", 500.0),
                ),
                Case(
                    "retreat_distance",
                    "ice_sheet_history_total_retreat_distance_km does not match histories",
                    summary_shifted("ice_sheet_history_total_retreat_distance_km", 5.0),
                ),
                Case(
                    "peak_volume",
                    "ice_sheet_history_peak_volume_km3 does not match histories",
                    summary_scaled("ice_sheet_history_peak_volume_km3"),
                ),
                Case(
                    "final_volume",
                    "ice_sheet_history_final_volume_km3 does not match histories",
                    summary_scaled("ice_sheet_history_final_volume_km3"),
                ),
                Case(
                    "stability_count",
                    "ice_sheet_stability_history_count does not match histories",
                    summary_counted("ice_sheet_stability_history_count"),
                ),
                Case(
                    "stability_steps",
                    "ice_sheet_stability_step_count does not match histories",
                    summary_counted("ice_sheet_stability_step_count"),
                ),
                Case(
                    "threshold_events",
                    "ice_sheet_retreat_threshold_event_count does not match histories",
                    summary_counted("ice_sheet_retreat_threshold_event_count"),
                ),
                Case(
                    "high_instability",
                    "high_ice_sheet_instability_count does not match histories",
                    summary_counted("high_ice_sheet_instability_count"),
                ),
                Case(
                    "mean_stability",
                    "mean_ice_sheet_stability_index does not match histories",
                    summary_shifted("mean_ice_sheet_stability_index", 0.01),
                ),
                Case(
                    "max_stability",
                    "max_ice_sheet_stability_index does not match histories",
                    summary_shifted("max_ice_sheet_stability_index", 0.01),
                ),
                Case(
                    "mean_calving",
                    "mean_calving_susceptibility_index does not match histories",
                    summary_shifted("mean_calving_susceptibility_index", 0.01),
                ),
                Case(
                    "mean_grounding",
                    "mean_grounding_line_instability_index does not match histories",
                    summary_shifted("mean_grounding_line_instability_index", 0.01),
                ),
                Case(
                    "projected_calving",
                    "ice_sheet_total_projected_calving_loss_km3 does not match histories",
                    summary_scaled("ice_sheet_total_projected_calving_loss_km3"),
                ),
                Case(
                    "projected_grounding",
                    "ice_sheet_total_projected_grounding_line_retreat_km does not match histories",
                    summary_shifted("ice_sheet_total_projected_grounding_line_retreat_km", 10.0),
                ),
                Case(
                    "stability_classes",
                    "ice_sheet_stability_class_counts does not match histories",
                    summary_bucket("ice_sheet_stability_class_counts", "stable"),
                ),
            ]
        )

    def test_dropped_sheet_fields_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "dynamic",
                    "ice sheet dynamic fields missing",
                    record_field_dropped("ice_sheets", "retreat_rate_m_y"),
                ),
                Case(
                    "stability",
                    "ice sheet stability fields missing",
                    record_field_dropped("ice_sheets", "calving_susceptibility_index"),
                ),
            ]
        )

    def test_out_of_range_sheet_dynamics_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "basal_sliding",
                    "ice sheet dynamic fields out of range",
                    record_field_set("ice_sheets", "mean_basal_sliding_index", 1.5),
                )
            ]
        )

    def test_dropped_histories_no_longer_cover_the_sheets(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "mass_balance",
                    "ice_sheet_histories length does not match ice_sheets length",
                    last_record_dropped("ice_sheet_histories"),
                ),
                Case(
                    "stability",
                    "ice_sheet_stability_histories length does not match ice_sheets length",
                    last_record_dropped("ice_sheet_stability_histories"),
                ),
            ]
        )

    def test_history_step_fields_are_replayed(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "mass_balance_step",
                    "ice sheet history fields invalid",
                    nested_field_set(("ice_sheet_histories", 0, "steps", 0), "step", 5),
                ),
                Case(
                    "stability_step",
                    "ice sheet stability history fields invalid",
                    nested_field_set(("ice_sheet_stability_histories", 0, "steps", 0), "duration_years", 0.0),
                ),
            ]
        )

    def test_non_list_stability_histories_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "stability",
                    "ice_sheet_stability_histories missing",
                    collection_replaced("ice_sheet_stability_histories", None),
                )
            ]
        )


class IceFlowlineHistories(_ValidateTamperCase):
    """Flowline flux budgets and the summary totals derived from them."""

    def test_summary_totals_must_match_histories(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "history_count",
                    "ice_flowline_history_count does not match ice_flowline_histories length",
                    summary_counted("ice_flowline_history_count"),
                ),
                Case(
                    "step_count",
                    "ice_flowline_step_count does not match ice flowline histories",
                    summary_counted("ice_flowline_step_count"),
                ),
                Case(
                    "cell_count",
                    "ice_flowline_cell_count does not match cells",
                    summary_counted("ice_flowline_cell_count"),
                ),
                Case(
                    "dynamic_flux",
                    "ice_flowline_total_dynamic_flux_km3_y does not match histories",
                    summary_scaled("ice_flowline_total_dynamic_flux_km3_y"),
                ),
                Case(
                    "dynamic_loss",
                    "ice_flowline_total_dynamic_loss_km3_y does not match histories",
                    summary_scaled("ice_flowline_total_dynamic_loss_km3_y"),
                ),
                Case(
                    "melt_loss",
                    "ice_flowline_total_melt_loss_km3_y does not match histories",
                    summary_shifted("ice_flowline_total_melt_loss_km3_y", 5.0),
                ),
                Case(
                    "erosion",
                    "ice_flowline_total_glacial_erosion_m does not match histories",
                    summary_shifted("ice_flowline_total_glacial_erosion_m", 5.0),
                ),
                Case(
                    "path_length",
                    "ice_flowline_total_path_length_km does not match histories",
                    summary_shifted("ice_flowline_total_path_length_km", 5.0),
                ),
                Case(
                    "mean_path_length",
                    "ice_flowline_mean_path_length_km does not match histories",
                    summary_shifted("ice_flowline_mean_path_length_km", 5.0),
                ),
                Case(
                    "driving_stress",
                    "ice_flowline_max_driving_stress_kpa does not match histories",
                    summary_shifted("ice_flowline_max_driving_stress_kpa", 5.0),
                ),
                Case(
                    "final_flux",
                    "ice_flowline_max_final_flux_km3_y does not match histories",
                    summary_shifted("ice_flowline_max_final_flux_km3_y", 5.0),
                ),
                Case(
                    "strain_heating",
                    "ice_flowline_max_strain_heating_index does not match histories",
                    summary_shifted("ice_flowline_max_strain_heating_index", 0.01),
                ),
                Case(
                    "moraine_cells",
                    "moraine_deposition_cell_count does not match cells with moraine deposition",
                    summary_counted("moraine_deposition_cell_count"),
                ),
            ]
        )

    def test_history_steps_follow_the_flowline_path(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "step",
                    "ice flowline history fields invalid",
                    nested_field_set(("ice_flowline_histories", 0, "steps", 0), "step", 9),
                )
            ]
        )


class GlacialLandforms(_ValidateTamperCase):
    """Glacial landform cells and the systems grouping them."""

    def test_summary_aggregates_must_match_cells(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "type_counts",
                    "glacial_landform_type_counts does not match cells",
                    summary_bucket("glacial_landform_type_counts", "none"),
                ),
                Case(
                    "cell_count",
                    "glacial_landform_cell_count does not match cells",
                    summary_counted("glacial_landform_cell_count"),
                ),
                Case(
                    "system_count",
                    "glacial_landform_system_count does not match records",
                    summary_counted("glacial_landform_system_count"),
                ),
                Case(
                    "area",
                    "glacial_landform_area_km2 does not match cells",
                    summary_scaled("glacial_landform_area_km2"),
                ),
                Case(
                    "mean_index",
                    "mean_glacial_landform_index does not match cells",
                    summary_shifted("mean_glacial_landform_index", 0.01),
                ),
                Case(
                    "ice_cap_cells",
                    "ice_cap_landform_cell_count does not match cells",
                    summary_counted("ice_cap_landform_cell_count"),
                ),
            ]
        )

    def test_non_list_system_collection_is_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "systems",
                    "glacial_landform_systems missing",
                    collection_replaced("glacial_landform_systems", None),
                )
            ]
        )

    def test_dropped_system_field_is_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "dominant_biome",
                    "glacial landform system fields missing",
                    record_field_dropped("glacial_landform_systems", "dominant_biome"),
                )
            ]
        )

    def test_system_cell_count_must_match_its_members(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "cell_count",
                    "glacial landform system records invalid",
                    record_field_set("glacial_landform_systems", "cell_count", 99),
                )
            ]
        )

    def test_duplicate_system_id_is_reported(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "duplicate_id",
                    "glacial landform system ids are not unique",
                    record_id_duplicated("glacial_landform_systems"),
                )
            ]
        )

    def test_dropped_system_loses_its_cells(self) -> None:
        self.assert_rejects(
            [
                Case(
                    "membership",
                    "glacial landform system membership does not match cells",
                    last_record_dropped("glacial_landform_systems"),
                )
            ]
        )


class SoilProfiles(_ValidateTamperCase):
    """Soil profile, horizon and pedogenesis-history record shapes."""

    def test_dropped_record_fields_are_reported(self) -> None:
        self.assert_rejects(
            [
                Case("profile", "soil profile fields missing", record_field_dropped("soil_profiles", "lithology")),
                Case("horizon", "soil horizon fields missing", record_field_dropped("soil_horizons", "carbonate_index")),
                Case(
                    "history",
                    "soil profile history fields missing",
                    record_field_dropped("soil_profile_histories", "high_erosion_pressure"),
                ),
            ]
        )

    def test_duplicate_profile_id_is_reported(self) -> None:
        self.assert_rejects(
            [Case("duplicate_id", "soil profile identifiers invalid", record_id_duplicated("soil_profiles"))]
        )
