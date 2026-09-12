"""Public ``validate`` CLI violations for biosphere and resource records.

``magic-geo validate`` checks the native certificate and versioned ecology
dependencies before its remaining record checks. Each test takes a generated
world, tampers with one derived quantity, and pins the exact first applicable
diagnostic. Separating mutations prevents an upstream failure from hiding an
unrelated field check.

Four habits keep the assertions honest:

* every rejection asserts the untampered control run of the same world exits 0
  *and* reported no ``FAIL`` line, so a broken fixture cannot make a tamper look
  load-bearing;
* a rejection asserts the pinned message *and* that the output carries no
  traceback, because a crash inside ``validate`` also exits non-zero but reports
  nothing. ``assert_rejects`` therefore refuses an empty ``FAIL`` list;
* every tamper goes through :meth:`~ValidateCliTestCase.tamper`, which refuses to
  invent a field the generator does not emit and refuses to write back a value
  the generator already produced — a renamed field or a coincidental value would
  otherwise turn into a confusing "the check stopped firing" failure; and
* fixture assumptions ("there is a water cell", "there is a soil-free cell") are
  looked up through :meth:`~ValidateCliTestCase.first`, so a world that stops
  generating one says so instead of raising ``StopIteration`` mid-test.

Each current summary/shape mutation has its own CLI invocation. Explicit old
archive coverage is used only where a historical downstream diagnostic is the
subject; current parent preflight is never bypassed.

The 128-cell world carries every record family this span validates except
``karst_systems``, which is empty below 512 cells; those checks use ``mid_512``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.io import write_json

from support import worlds
from support.ecology_worlds import historical_ecology_world_readonly
import pytest

# Exhaustive branch coverage of ``validate``: every case invokes the full CLI
# over a generated world. Deselect locally with -m "not slow".
pytestmark = pytest.mark.slow

#: Control results are identical for every class sharing a world, so the
#: untampered run happens once per world key and each test asserts the result.
_CONTROL: dict[str, tuple[int, str]] = {}

MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}


def _tampered_summary_value(value: Any) -> Any:
    """A value far enough from ``value`` to fail every tolerance in the span.

    Counts are compared exactly, means with an absolute 0.001 tolerance, and
    the area/volume totals with a relative one, so scaling *and* offsetting the
    floats keeps large totals outside their relative band.
    """

    if isinstance(value, dict):
        return {**value, "tampered_bucket": 1}
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    return float(value) * 2.0 + 5.0


class ValidateCliTestCase(TestCase):
    """Baseline world on disk once per class; a private copy per tamper."""

    WORLD_KEY = "replay_128"

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = TemporaryDirectory()
        cls.directory = Path(cls._directory.name)
        cls.baseline = worlds.cached_world(cls.WORLD_KEY)
        if cls.WORLD_KEY not in _CONTROL:
            control_path = cls.directory / "control.json"
            write_json(control_path, cls.baseline)
            result = CliRunner().invoke(app, ["validate", "--world", str(control_path)])
            _CONTROL[cls.WORLD_KEY] = (result.exit_code, result.output)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()

    def world(self) -> dict[str, Any]:
        """A private deep copy of the class baseline, safe to mutate."""

        return copy.deepcopy(self.baseline)

    def assert_control_accepted(self) -> None:
        """The untampered baseline validates, so rejections come from tampers."""

        exit_code, output = _CONTROL[self.WORLD_KEY]
        self.assertEqual(exit_code, 0, output)
        # Not implied by the exit code: a future gate could echo complaints and
        # still fall through to ``OK``, which would make every tamper below
        # look load-bearing when the world was already being rejected.
        self.assertEqual(
            [line for line in output.splitlines() if line.startswith("FAIL ")],
            [],
            output,
        )
        self.assertIn("OK", output)

    def reported_failures(self, world: dict[str, Any], name: str) -> tuple[int, set[str], str]:
        path = self.directory / f"{name}.json"
        write_json(path, world)
        result = CliRunner().invoke(app, ["validate", "--world", str(path)])
        self.assertTrue(result.exception is None or isinstance(result.exception, SystemExit), repr(result.exception))
        reported = {
            line.removeprefix("FAIL ")
            for line in result.output.splitlines()
            if line.startswith("FAIL ")
        }
        return result.exit_code, reported, result.output

    def first(self, candidates: Any, what: str) -> Any:
        """The first generated record matching a fixture assumption.

        A bare ``next()`` would raise ``StopIteration`` from inside the test
        body if the generator stopped producing such a record; naming the
        assumption turns that into a readable failure instead.
        """

        for candidate in candidates:
            return candidate
        raise AssertionError(f"the generated world has no {what}")

    def assert_changed(self, before: Any, after: Any, what: str) -> Any:
        """``after`` is a real change to ``before``, so the tamper cannot be inert.

        A hard-coded tamper value that happens to equal the generated one is a
        silent no-op; without this the only symptom is the confusing
        ``exit_code 0 != 1`` from a world that was never actually damaged.
        """

        self.assertNotEqual(before, after, f"tampering {what} changed nothing")
        return after

    def tamper(self, record: dict[str, Any], field: str, value: Any) -> dict[str, Any]:
        """Overwrite a *generated* ``field`` with a *different* ``value``.

        Both halves matter while the generator is moving. Assigning a renamed
        field would quietly add a new key and leave a healthy world behind, and
        assigning the value the generator already produced would leave the world
        untouched; either way the only symptom would be the tamper failing to
        provoke a rejection, which reads like a broken check rather than a
        broken test.
        """

        self.assertIn(field, record, f"{field} is not a generated field")
        record[field] = self.assert_changed(record[field], value, field)
        return record

    def assert_rejects(self, world: dict[str, Any], name: str, *messages: str) -> set[str]:
        """``validate`` rejected ``world`` and reported each pinned message."""

        self.assert_control_accepted()
        exit_code, reported, output = self.reported_failures(world, name)
        self.assertEqual(exit_code, 1, output)
        self.assertTrue(reported, f"validate exited 1 without reporting a failure: {output!r}")
        for message in messages:
            with self.subTest(message=message):
                self.assertIn(message, reported)
        return reported


# --------------------------------------------------------------------------
# Summary metrics: each derived aggregate is checked independently. Current
# species/fire/resource preflights may stop before the generic summary loops.
# --------------------------------------------------------------------------

SOIL_SUMMARY = {
    "soil_texture_counts": "soil_texture_counts does not match cells",
    "soil_diagnostic_cell_count": "soil_diagnostic_cell_count does not match soil cells",
    "soil_profile_count": "soil_profile_count does not match soil_profiles length",
    "soil_horizon_count": "soil_horizon_count does not match soil_horizons length",
    "soil_profile_history_count": (
        "soil_profile_history_count does not match soil_profile_histories length"
    ),
    "soil_pedogenesis_step_count": (
        "soil_pedogenesis_step_count does not match soil profile histories"
    ),
    "soil_profile_class_counts": "soil_profile_class_counts does not match soil profiles",
    "mean_soil_drainage_index": "mean_soil_drainage_index does not match cells",
    "mean_pedogenic_weathering_index": (
        "mean_pedogenic_weathering_index does not match soil profile histories"
    ),
    "total_soil_production_m": "total_soil_production_m does not match soil profile histories",
    "total_soil_erosion_loss_m": (
        "total_soil_erosion_loss_m does not match soil profile histories"
    ),
    "high_erosion_pedogenesis_count": (
        "high_erosion_pedogenesis_count does not match soil profile histories"
    ),
}

BIOME_SUMMARY = {
    "biome_diagnostic_count": "biome_diagnostic_count does not match diagnostics length",
    "biome_limiting_factor_counts": "biome_limiting_factor_counts does not match diagnostics",
    "mean_potential_evapotranspiration_mm_y": (
        "mean_potential_evapotranspiration_mm_y does not match biome diagnostics"
    ),
    "biome_transition_zone_count": "biome_transition_zone_count does not match diagnostics",
    "high_fire_frequency_biome_count": (
        "high_fire_frequency_biome_count does not match diagnostics"
    ),
    "biome_ecotone_type_counts": "biome_ecotone_type_counts does not match cells",
    "biome_ecotone_cell_count": "biome_ecotone_cell_count does not match cells",
    "biome_ecotone_region_count": "biome_ecotone_region_count does not match regions",
    "mangrove_ecotone_cell_count": "mangrove_ecotone_cell_count does not match cells",
    "cloud_forest_ecotone_cell_count": "cloud_forest_ecotone_cell_count does not match cells",
    "alpine_paramo_ecotone_cell_count": "alpine_paramo_ecotone_cell_count does not match cells",
    "mean_biome_ecotone_confidence": "mean_biome_ecotone_confidence does not match cells",
    "biome_realism_check_count": (
        "biome_realism_check_count does not match biome_realism_checks length"
    ),
    "biome_realism_pass_count": "biome_realism_pass_count does not match biome realism checks",
    "biome_realism_pass_fraction": "biome_realism_pass_fraction does not match checks",
    "mean_biome_realism_score": "mean_biome_realism_score does not match checks",
    "desert_water_deficit_alignment_index": (
        "desert_water_deficit_alignment_index does not match biome realism check"
    ),
}

GROUNDWATER_SUMMARY = {
    "aquifer_class_counts": "aquifer_class_counts does not match cells",
    "aquifer_cell_count": "aquifer_cell_count does not match cells",
    "aquifer_system_count": "aquifer_system_count does not match aquifer cells",
    "mean_groundwater_recharge_mm_y": (
        "mean_groundwater_recharge_mm_y does not match aquifer cells"
    ),
    "total_groundwater_recharge_km3_y": "total_groundwater_recharge_km3_y does not match cells",
    "groundwater_flow_regime_counts": "groundwater_flow_regime_counts does not match cells",
    "groundwater_flow_cell_count": (
        "groundwater_flow_cell_count does not match groundwater flow cells"
    ),
    "mean_groundwater_gradient_index": (
        "mean_groundwater_gradient_index does not match groundwater flow cells"
    ),
    "total_groundwater_discharge_km3_y": (
        "total_groundwater_discharge_km3_y does not match cells"
    ),
    "total_groundwater_lateral_flow_km3_y": (
        "total_groundwater_lateral_flow_km3_y does not match cells"
    ),
    "total_groundwater_flow_balance_residual_km3_y": (
        "total_groundwater_flow_balance_residual_km3_y does not match cells"
    ),
    "karst_cell_count": "karst_cell_count does not match cells",
    "karst_system_count": "karst_system_count does not match systems",
    "mean_karst_potential_index": "mean_karst_potential_index does not match cells",
}

ECOSYSTEM_SUMMARY = {
    "vegetation_succession_stage_counts": (
        "vegetation_succession_stage_counts does not match cells"
    ),
    "mean_primary_productivity_index": "mean_primary_productivity_index does not match cells",
    "high_wildfire_spread_risk_cell_count": (
        "high_wildfire_spread_risk_cell_count does not match cells"
    ),
    "vegetation_succession_history_count": (
        "vegetation_succession_history_count does not match histories"
    ),
    "vegetation_succession_step_count": (
        "vegetation_succession_step_count does not match histories"
    ),
    "renewable_resource_type_counts": "renewable_resource_type_counts does not match records",
    "renewable_resource_record_count": "renewable_resource_record_count does not match records",
    "forest_growth_resource_count": "forest_growth_resource_count does not match records",
    "fishery_productivity_resource_count": (
        "fishery_productivity_resource_count does not match records"
    ),
}

SPECIES_SUMMARY = {
    "dominant_species_guild_counts": "dominant_species_guild_counts does not match cells",
    "mean_species_habitat_suitability_index": (
        "mean_species_habitat_suitability_index does not match cells"
    ),
    "species_range_record_count": "species_range_record_count does not match records",
    "species_range_cell_count": "species_range_cell_count does not match records",
    "species_guild_type_counts": "species_guild_type_counts does not match records",
    "species_habitat_class_counts": "species_habitat_class_counts does not match records",
    "terrestrial_species_range_count": "terrestrial_species_range_count does not match records",
    "aquatic_species_range_count": "aquatic_species_range_count does not match records",
    "wetland_species_range_count": "wetland_species_range_count does not match records",
    "high_endemism_species_range_count": (
        "high_endemism_species_range_count does not match records"
    ),
    "high_conservation_stress_species_range_count": (
        "high_conservation_stress_species_range_count does not match records"
    ),
    "species_range_total_area_km2": "species_range_total_area_km2 does not match records",
}
SPECIES_SUMMARY = {key: f"species parent summary: {key} mismatch" for key in SPECIES_SUMMARY}

WILDFIRE_SUMMARY = {
    "wildfire_disturbance_regime_counts": (
        "wildfire_disturbance_regime_counts does not match cells"
    ),
    "mean_wildfire_ignition_potential_index": (
        "mean_wildfire_ignition_potential_index does not match cells"
    ),
    "high_wildfire_ignition_potential_cell_count": (
        "high_wildfire_ignition_potential_cell_count does not match cells"
    ),
    "high_wildfire_fuel_continuity_cell_count": (
        "high_wildfire_fuel_continuity_cell_count does not match cells"
    ),
    "high_wildfire_firebreak_cell_count": (
        "high_wildfire_firebreak_cell_count does not match cells"
    ),
    "wildfire_spread_history_count": "wildfire_spread_history_count does not match histories",
    "wildfire_disturbance_cell_count": (
        "wildfire_disturbance_cell_count does not match histories"
    ),
    "wildfire_spread_step_count": "wildfire_spread_step_count does not match histories",
    "wildfire_total_burned_area_km2": (
        "wildfire_total_burned_area_km2 does not match histories"
    ),
}
WILDFIRE_SUMMARY = {key: f"wildfire availability: summary {key}" for key in WILDFIRE_SUMMARY}
WILDFIRE_SUMMARY.update({
    "wildfire_disturbance_regime_counts": "wildfire availability: summary regimes",
    "mean_wildfire_ignition_potential_index": "wildfire availability: summary mean wildfire_ignition_potential_index",
    "wildfire_total_burned_area_km2": "wildfire availability: summary burned area",
})

RESOURCE_SUMMARY = {
    "resource_deposit_count": "resource_deposit_count does not match resource_deposits length",
    "resource_deposit_class_counts": "resource_deposit_class_counts does not match deposits",
    "metal_resource_deposit_count": (
        "metal_resource_deposit_count does not match resource deposits"
    ),
    "mean_resource_reserve_potential_index": (
        "mean_resource_reserve_potential_index does not match resource deposits"
    ),
    "resource_deposit_total_area_km2": (
        "resource_deposit_total_area_km2 does not match resource deposits"
    ),
    "mean_ore_genesis_potential_index": "mean_ore_genesis_potential_index does not match cells",
    "high_ore_genesis_potential_cell_count": (
        "high_ore_genesis_potential_cell_count does not match cells"
    ),
    "ore_resource_deposit_count": (
        "ore_resource_deposit_count does not match resource deposits"
    ),
}
RESOURCE_SUMMARY.update({
    "resource_deposit_count": "biological resource summary: resource_deposit_count mismatch",
    "resource_deposit_class_counts": "resource deposit class counts mismatch",
    "metal_resource_deposit_count": "biological resource summary: metal_resource_deposit_count mismatch",
    "mean_resource_reserve_potential_index": "mean_resource_reserve_potential_index: numerical replay mismatch",
    "resource_deposit_total_area_km2": "resource deposit total area: numerical replay mismatch",
})

#: One key per ``<domain> summary metrics missing`` guard. Deleting the key also
#: trips that domain's value comparison, which is why the guards are asserted by
#: name rather than by asserting the complete failure list.
SUMMARY_KEY_GUARDS = {
    "biome_diagnostic_count": "biome diagnostic summary metrics missing",
    "biome_ecotone_cell_count": "biome ecotone summary metrics missing",
    "mean_biome_realism_score": "biome realism summary metrics missing",
    "aquifer_resource_model": "aquifer summary metrics missing",
    "groundwater_flow_cell_count": "groundwater flow summary metrics missing",
    "karst_cell_count": "karst summary metrics missing",
    "mean_forest_growth_index": "ecosystem dynamic summary metrics missing",
    "species_range_record_count": "species range summary metrics missing",
    "wildfire_spread_history_count": "wildfire disturbance summary metrics missing",
    "resource_deposit_count": "resource deposit summary metrics missing",
    "ore_genesis_system_count": "ore genesis summary metrics missing",
}
SUMMARY_KEY_GUARDS.update({
    "species_range_record_count": "species parent summary: species_range_record_count mismatch",
    "wildfire_spread_history_count": "wildfire availability: summary wildfire_spread_history_count",
    "resource_deposit_count": "biological resource summary: resource_deposit_count mismatch",
})


class SummaryMetricsTest(ValidateCliTestCase):
    """Summary aggregates are replayed from the records they summarise."""

    def assert_summary_tamper_rejected(self, table: dict[str, str], name: str) -> None:
        for key, message in table.items():
            with self.subTest(key=key):
                world = self.world()
                summary = world["summary"]
                self.assertIn(key, summary, f"{key} missing from the generated summary")
                summary[key] = self.assert_changed(
                    summary[key], _tampered_summary_value(summary[key]), f"summary[{key!r}]"
                )
                self.assert_rejects(world, name + "_" + key, message)

    def test_soil_summary_metrics_replayed(self) -> None:
        self.assert_summary_tamper_rejected(SOIL_SUMMARY, "summary_soil")

    def test_biome_summary_metrics_replayed(self) -> None:
        self.assert_summary_tamper_rejected(BIOME_SUMMARY, "summary_biome")

    def test_groundwater_summary_metrics_replayed(self) -> None:
        self.assert_summary_tamper_rejected(GROUNDWATER_SUMMARY, "summary_groundwater")

    def test_ecosystem_summary_metrics_replayed(self) -> None:
        self.assert_summary_tamper_rejected(ECOSYSTEM_SUMMARY, "summary_ecosystem")

    def test_species_summary_metrics_replayed(self) -> None:
        self.assert_summary_tamper_rejected(SPECIES_SUMMARY, "summary_species")

    def test_wildfire_summary_metrics_replayed(self) -> None:
        self.assert_summary_tamper_rejected(WILDFIRE_SUMMARY, "summary_wildfire")

    def test_resource_summary_metrics_replayed(self) -> None:
        self.assert_summary_tamper_rejected(RESOURCE_SUMMARY, "summary_resource")

    def test_absent_summary_keys_reported_per_domain(self) -> None:
        for key, message in SUMMARY_KEY_GUARDS.items():
            with self.subTest(key=key):
                world = self.world()
                self.assertIn(key, world["summary"], f"{key} missing from the generated summary")
                del world["summary"][key]
                self.assert_rejects(world, "summary_absent_" + key, message)


# --------------------------------------------------------------------------
# Payload shape: each absent collection, cell field and record field is tested
# separately so an upstream failure cannot hide another guard.
# --------------------------------------------------------------------------

PAYLOAD_COLLECTIONS = [
    "biome_diagnostics",
    "biome_ecotone_regions",
    "aquifer_systems",
    "groundwater_flow_systems",
    "karst_systems",
    "vegetation_succession_histories",
    "renewable_resource_records",
    "species_range_records",
    "wildfire_spread_histories",
    "resource_deposits",
    "ore_genesis_systems",
]

CELL_FIELD_GUARDS = {
    "biome_ecotone_type": "biome ecotone cell fields missing",
    "aquifer_class": "aquifer cell fields missing",
    "groundwater_flow_regime": "groundwater flow cell fields missing",
    "karst_potential_index": "karst cell fields missing",
    "forest_growth_index": "ecosystem dynamic cell fields missing",
    "species_range_record_ids": "species range cell fields missing",
    "wildfire_spread_history_ids": "wildfire disturbance cell fields missing",
    "ore_genesis_system_id": "ore genesis cell fields missing",
}
CELL_FIELD_GUARDS.update({
    "species_range_record_ids": "species parent cell 0: range inverse mismatch",
    "wildfire_spread_history_ids": "wildfire availability: cell 0: inverse histories",
})

RECORD_FIELD_GUARDS = {
    "biome_diagnostics": ("ecotone_index", "biome diagnostic fields missing"),
    "biome_ecotone_regions": ("coastal_cell_count", "biome ecotone region fields missing"),
    "biome_realism_checks": ("evidence", "biome realism check fields missing"),
    "aquifer_systems": ("closed_basin_fraction", "aquifer system fields missing"),
    "groundwater_flow_systems": ("flow_regime_counts", "groundwater flow system fields missing"),
    "vegetation_succession_histories": (
        "max_wildfire_spread_risk_index",
        "vegetation succession history fields missing",
    ),
    "renewable_resource_records": ("formation_evidence", "renewable resource fields missing"),
    "species_range_records": ("habitat_evidence", "species range record fields missing"),
    "wildfire_spread_histories": (
        "disturbance_regime_counts",
        "wildfire spread history fields missing",
    ),
    "resource_deposits": ("formation_evidence", "resource deposit fields missing"),
    "ore_genesis_systems": ("formation_steps", "ore genesis system fields missing"),
}
RECORD_FIELD_GUARDS.update({
    "species_range_records": ("habitat_evidence", "species parent range 0: consumed habitat evidence mismatch"),
    "wildfire_spread_histories": ("disturbance_regime_counts", "wildfire availability: history 0: disturbance_regime_counts"),
})

CURRENT_COLLECTION_ERRORS = {
    "vegetation_succession_histories": "aquatic ecology requires a valid succession history list",
    "renewable_resource_records": "aquatic climate support requires a valid renewable record list",
    "species_range_records": "species parent support requires a valid range record list",
    "wildfire_spread_histories": "wildfire availability: invalid histories",
    "resource_deposits": "biological resources require a resource_deposits list",
}


class PayloadShapeTest(ValidateCliTestCase):
    """Absent collections, cell fields and record fields are named, not crashed on."""

    def test_non_list_record_collections_reported(self) -> None:
        for key in PAYLOAD_COLLECTIONS:
            with self.subTest(collection=key):
                world = self.world()
                self.assertIsInstance(world.get(key), list, f"{key} is not a generated list")
                world[key] = {}
                messages = [CURRENT_COLLECTION_ERRORS.get(key, f"{key} missing")]
                if key == "biome_diagnostics":
                    messages.append("biome_diagnostics length does not match cells")
                self.assert_rejects(world, "collections_absent_" + key, *messages)

    def test_absent_cell_fields_reported_per_domain(self) -> None:
        for field, message in CELL_FIELD_GUARDS.items():
            with self.subTest(field=field):
                world = self.world()
                cell = world["cells"][0]
                self.assertIn(field, cell, f"{field} missing from generated cells")
                del cell[field]
                self.assert_rejects(world, "cell_fields_absent_" + field, message)

    def test_absent_record_fields_reported_per_domain(self) -> None:
        for collection, (field, message) in RECORD_FIELD_GUARDS.items():
            with self.subTest(collection=collection, field=field):
                world = self.world()
                record = world[collection][0]
                self.assertIn(field, record, f"{field} missing from generated {collection}")
                del record[field]
                if collection == "resource_deposits":
                    message = f"resource deposit 0 cell {record['cell_id']}: missing or mismatched formation evidence"
                self.assert_rejects(world, "record_fields_absent_" + collection, message)


# --------------------------------------------------------------------------
# Soil diagnostics, profiles, horizons and pedogenesis histories.
# --------------------------------------------------------------------------

SOIL_CELL_INVALID = "soil diagnostic fields invalid"
SOIL_PROFILE_INVALID = "soil profile or horizon records invalid"
SOIL_HISTORY_INVALID = "soil profile history records invalid"


class SoilRecordTest(ValidateCliTestCase):
    """Soil cell fields, profile/horizon geometry and pedogenesis replay."""

    def soil_cell(self, world: dict[str, Any]) -> dict[str, Any]:
        for cell in world["cells"]:
            if str(cell.get("soil_texture_class", "")) not in {"", "none"}:
                return cell
        raise AssertionError("the generated world has no soil-bearing cell")

    def soil_free_cell(self, world: dict[str, Any]) -> dict[str, Any]:
        for cell in world["cells"]:
            if str(cell.get("soil_texture_class", "")) == "none":
                return cell
        raise AssertionError("the generated world has no soil-free cell")

    def test_soil_cell_diagnostics_are_range_checked(self) -> None:
        world = self.world()
        self.tamper(self.soil_cell(world), "soil_ph", 20.0)
        self.assert_rejects(world, "soil_ph", SOIL_CELL_INVALID)

    def test_soil_free_cell_must_not_claim_a_profile(self) -> None:
        world = self.world()
        self.tamper(self.soil_free_cell(world), "soil_profile_id", 5)
        self.assert_rejects(world, "soil_none_profile", SOIL_CELL_INVALID)

    def test_soil_cell_horizon_count_must_match_its_profile(self) -> None:
        world = self.world()
        cell = self.soil_cell(world)
        self.tamper(cell, "soil_horizon_count", int(cell["soil_horizon_count"]) + 3)
        self.assert_rejects(world, "soil_horizon_count_cell", SOIL_CELL_INVALID)

    def test_soil_profile_scalar_ranges_are_checked(self) -> None:
        for field, value, name in (
            ("profile_age_ka", -1.0, "profile_age"),
            ("weathering_index", 5.0, "profile_weathering"),
            ("ph", 12.0, "profile_ph"),
        ):
            with self.subTest(field=field):
                world = self.world()
                self.tamper(world["soil_profiles"][0], field, value)
                self.assert_rejects(world, f"soil_{name}", SOIL_PROFILE_INVALID)

    def test_soil_profile_horizon_links_are_checked(self) -> None:
        world = self.world()
        horizon_ids = list(world["soil_profiles"][0]["horizon_ids"])
        horizon_ids[0] = 999_999
        self.tamper(world["soil_profiles"][0], "horizon_ids", horizon_ids)
        self.assert_rejects(world, "soil_missing_horizon", SOIL_PROFILE_INVALID)

    def test_soil_horizon_fields_are_range_checked(self) -> None:
        for field, value, name in (
            ("ph", 12.0, "horizon_ph"),
            ("carbonate_index", 5.0, "horizon_carbonate"),
        ):
            with self.subTest(field=field):
                world = self.world()
                horizon_id = int(world["soil_profiles"][0]["horizon_ids"][0])
                horizon = self.first(
                    (
                        record
                        for record in world["soil_horizons"]
                        if int(record["id"]) == horizon_id
                    ),
                    f"soil horizon {horizon_id}",
                )
                self.tamper(horizon, field, value)
                self.assert_rejects(world, f"soil_{name}", SOIL_PROFILE_INVALID)

    def test_soil_profile_horizons_must_reach_the_profile_depth(self) -> None:
        """A shortened bottom horizon leaves the stack shallower than the profile."""

        world = self.world()
        profile = world["soil_profiles"][0]
        last_horizon_id = int(profile["horizon_ids"][-1])
        horizon = self.first(
            (record for record in world["soil_horizons"] if int(record["id"]) == last_horizon_id),
            f"soil horizon {last_horizon_id}",
        )
        # Halving the bottom horizon keeps its own thickness self-consistent, so
        # only the profile-depth reconciliation can object.
        shortfall = float(horizon["thickness_m"]) / 2.0
        horizon["bottom_depth_m"] = self.assert_changed(
            horizon["bottom_depth_m"],
            float(horizon["bottom_depth_m"]) - shortfall,
            "the bottom horizon depth",
        )
        horizon["thickness_m"] = float(horizon["thickness_m"]) - shortfall
        self.assert_rejects(world, "soil_horizon_short", SOIL_PROFILE_INVALID)

    def test_soil_horizons_must_all_belong_to_a_profile(self) -> None:
        """A horizon no profile names is reported, not silently tolerated.

        The horizon is a copy of a valid one under a fresh id, and
        ``soil_horizon_count`` is kept in step with the longer list, so every
        other soil check still passes: the profile-to-horizon reconciliation is
        the only thing left that can object, which the ``assertNotIn`` below
        pins down.
        """

        world = self.world()
        horizons = world["soil_horizons"]
        orphan = copy.deepcopy(horizons[0])
        orphan["id"] = self.assert_changed(
            orphan["id"],
            max(int(record["id"]) for record in horizons) + 1,
            "the orphan horizon id",
        )
        horizons.append(orphan)
        world["summary"]["soil_horizon_count"] = len(horizons)
        reported = self.assert_rejects(
            world, "soil_orphan_horizons", "soil horizons do not match soil profiles"
        )
        self.assertNotIn(SOIL_PROFILE_INVALID, reported)
        self.assertNotIn("soil_horizon_count does not match soil_horizons length", reported)

    def test_soil_profile_history_totals_are_replayed(self) -> None:
        world = self.world()
        self.tamper(world["soil_profile_histories"][0], "initial_depth_m", -1.0)
        self.assert_rejects(
            world,
            "soil_history_depth",
            SOIL_HISTORY_INVALID,
            "soil profile histories do not match soil profiles",
        )

    def test_soil_pedogenesis_steps_are_ordered(self) -> None:
        world = self.world()
        self.tamper(world["soil_profile_histories"][0]["steps"][0], "stage_index", 99)
        self.assert_rejects(world, "soil_history_step", SOIL_HISTORY_INVALID)

    def test_soil_pedogenesis_step_years_must_parse(self) -> None:
        world = self.world()
        self.tamper(world["soil_profile_histories"][0]["steps"][0], "start_year_bp", "not-a-year")
        self.assert_rejects(world, "soil_history_year", SOIL_HISTORY_INVALID)

    def test_soil_history_erosion_pressure_flag_is_replayed_from_steps(self) -> None:
        world = self.world()
        history = world["soil_profile_histories"][0]
        self.tamper(
            history, "high_erosion_pressure", not bool(history.get("high_erosion_pressure", False))
        )
        self.assert_rejects(world, "soil_history_pressure", SOIL_HISTORY_INVALID)

    def test_soil_profile_histories_must_cover_every_profile(self) -> None:
        world = self.world()
        self.assertTrue(world["soil_profile_histories"], "no generated soil profile history to drop")
        world["soil_profile_histories"].pop()
        self.assert_rejects(
            world,
            "soil_history_dropped",
            "soil_profile_histories length does not match soil_profiles length",
            "soil_profile_history_count does not match soil_profile_histories length",
            SOIL_PROFILE_INVALID,
        )

    def test_pedogenesis_steps_without_historical_eras_need_nominal_time(self) -> None:
        """With no historical eras the steps must carry a natural-stage time basis.

        The generated steps are era-stamped, so emptying ``historical_eras``
        routes the replay through the nominal-time branch, which then rejects
        them for still claiming an era.
        """

        world = self.world()
        world["historical_eras"] = self.assert_changed(
            world["historical_eras"], [], "the historical era list"
        )
        self.assert_rejects(world, "soil_history_no_eras", SOIL_HISTORY_INVALID)

    def test_nominal_pedogenesis_intervals_are_replayed_against_the_feedback_history(self) -> None:
        """Parseable nominal intervals still have to match the natural stage record."""

        world = self.world()
        world["historical_eras"] = self.assert_changed(
            world["historical_eras"], [], "the historical era list"
        )
        for history in world["soil_profile_histories"]:
            for step in history["steps"]:
                # Deliberately *added*, not overwritten: the generator stamps its
                # steps with eras and emits no nominal interval at all, so
                # ``tamper`` (which requires an existing field) does not apply.
                self.assertNotIn("nominal_interval_start_ma", step)
                step["nominal_interval_start_ma"] = 1.0
                step["nominal_interval_end_ma"] = 0.5
                step["nominal_interval_duration_ma"] = 0.5
        self.assert_rejects(world, "soil_history_nominal", SOIL_HISTORY_INVALID)


# --------------------------------------------------------------------------
# Biome diagnostics, ecotone cells/regions and realism checks.
# --------------------------------------------------------------------------


class BiomeRecordTest(ValidateCliTestCase):
    """Biome diagnostics, ecotone regions and the biome realism scorecard."""

    def test_biome_diagnostic_records_are_replayed_against_cells(self) -> None:
        world = self.world()
        self.tamper(world["biome_diagnostics"][0], "growing_season_months", 99)
        self.assert_rejects(
            world,
            "biome_diag_months",
            "biome diagnostic records invalid",
            "biome diagnostic ids are not unique",
            "biome diagnostics do not match cells",
        )

    def test_biome_diagnostic_fire_index_must_match_its_cell(self) -> None:
        world = self.world()
        self.tamper(world["biome_diagnostics"][0], "fire_frequency_index", 0.9)
        self.assert_rejects(world, "biome_diag_fire", "biome diagnostic records invalid")

    def test_biome_ecotone_cell_fields_are_range_checked(self) -> None:
        for value, name in ((5.0, "range"), ("not-a-number", "type")):
            with self.subTest(value=value):
                world = self.world()
                self.tamper(world["cells"][0], "biome_ecotone_confidence", value)
                self.assert_rejects(
                    world, f"ecotone_cell_{name}", "biome ecotone cell fields invalid"
                )

    def test_biome_ecotone_region_membership_is_replayed(self) -> None:
        world = self.world()
        self.tamper(world["biome_ecotone_regions"][0], "cell_count", 999)
        self.assert_rejects(
            world,
            "ecotone_region_count",
            "biome ecotone region records invalid",
            "biome ecotone region ids are not unique",
            "biome ecotone region membership does not match cells",
        )

    def test_biome_ecotone_region_cell_ids_must_be_a_list_of_known_cells(self) -> None:
        for value, name in (({}, "mapping"), ([999_999], "unknown")):
            with self.subTest(cell_ids=name):
                world = self.world()
                self.tamper(world["biome_ecotone_regions"][0], "cell_ids", value)
                self.assert_rejects(
                    world, f"ecotone_region_{name}", "biome ecotone region records invalid"
                )

    def test_biome_ecotone_region_counts_inland_cells_as_non_coastal(self) -> None:
        """An inland cell dragged into a region makes the coastal tally disagree."""

        world = self.world()
        cells_by_id = {int(cell["id"]): cell for cell in world["cells"]}
        inland = self.first(
            (
                int(cell["id"])
                for cell in world["cells"]
                if not bool(cell.get("is_water", False))
                and not any(
                    str(cells_by_id[int(neighbor)].get("water_body_type", "")) in MARINE_WATER_TYPES
                    for neighbor in cell.get("neighbors", [])
                    if int(neighbor) in cells_by_id
                )
            ),
            "inland land cell",
        )
        region = world["biome_ecotone_regions"][0]
        region["cell_ids"] = self.assert_changed(
            region["cell_ids"],
            sorted(set(region["cell_ids"]) | {inland}),
            "the region membership",
        )
        self.assert_rejects(
            world,
            "ecotone_region_inland",
            "biome ecotone region records invalid",
            "biome ecotone region membership does not match cells",
        )

    def test_biome_ecotone_region_treats_water_cells_as_non_coastal(self) -> None:
        """A water cell dragged into a region is never counted as coastal land."""

        world = self.world()
        water = self.first(
            (int(cell["id"]) for cell in world["cells"] if bool(cell.get("is_water", False))),
            "water cell",
        )
        region = world["biome_ecotone_regions"][0]
        region["cell_ids"] = self.assert_changed(
            region["cell_ids"],
            sorted(set(region["cell_ids"]) | {water}),
            "the region membership",
        )
        self.assert_rejects(
            world, "ecotone_region_water", "biome ecotone region records invalid"
        )

    def test_biome_ecotone_region_treats_neighbourless_cells_as_non_coastal(self) -> None:
        """Current adjacency preflight precedes the historical ecotone guard."""

        world = self.world()
        cells_by_id = {int(cell["id"]): cell for cell in world["cells"]}
        coastal = self.first(
            (
                cells_by_id[int(region["cell_ids"][0])]
                for region in world["biome_ecotone_regions"]
                if not bool(cells_by_id[int(region["cell_ids"][0])].get("is_water", False))
                and any(
                    str(cells_by_id[int(neighbor)].get("water_body_type", "")) in MARINE_WATER_TYPES
                    for neighbor in cells_by_id[int(region["cell_ids"][0])].get("neighbors", [])
                    if int(neighbor) in cells_by_id
                )
            ),
            "ecotone region led by a coastal land cell",
        )
        coastal["neighbors"] = self.assert_changed(
            coastal["neighbors"], {}, "the coastal cell's neighbour list"
        )
        self.assert_rejects(
            world, "ecotone_region_neighborless",
            f"species parent cell {coastal['id']}: invalid neighbor IDs",
            f"wildfire availability: cell {coastal['id']}: complete neighbor list",
        )

        # Explicit original archive retains the old downstream message. This
        # is a separate legacy control, never a bypass of current preflight.
        historical = copy.deepcopy(historical_ecology_world_readonly())
        code, reported, output = self.reported_failures(historical, "historical_ecotone_control")
        self.assertEqual((code, reported), (0, set()), output)
        by_id = {c["id"]: c for c in historical["cells"]}
        old_coastal = self.first((by_id[r["cell_ids"][0]] for r in historical["biome_ecotone_regions"]
            if not by_id[r["cell_ids"][0]]["is_water"] and any(by_id[n]["water_body_type"] in MARINE_WATER_TYPES
                for n in by_id[r["cell_ids"][0]]["neighbors"])), "historical coastal ecotone source")
        self.tamper(old_coastal, "neighbors", {})
        code, reported, output = self.reported_failures(historical, "historical_ecotone_neighborless")
        self.assertEqual(code, 1, output)
        self.assertIn("biome ecotone region records invalid", reported)

    def test_biome_realism_check_records_are_range_checked(self) -> None:
        world = self.world()
        self.tamper(world["biome_realism_checks"][0], "score", 5.0)
        self.assert_rejects(world, "realism_score", "biome realism check records invalid")


# --------------------------------------------------------------------------
# Aquifers, groundwater flow systems and karst cells.
# --------------------------------------------------------------------------


class GroundwaterRecordTest(ValidateCliTestCase):
    """Aquifer cells/systems, groundwater flow systems and karst cell fields."""

    def test_aquifer_cell_indices_are_range_checked(self) -> None:
        world = self.world()
        self.tamper(world["cells"][0], "aquifer_storage_index", 5.0)
        self.assert_rejects(world, "aquifer_cell", "aquifer cell fields invalid")

    def test_aquifer_system_aggregates_are_replayed(self) -> None:
        world = self.world()
        self.tamper(world["aquifer_systems"][0], "closed_basin_fraction", 5.0)
        self.assert_rejects(
            world,
            "aquifer_system",
            "aquifer system records invalid",
            "aquifer system ids are not unique",
            "aquifer system membership does not match cells",
        )

    def test_aquifer_system_cell_ids_must_be_a_list_of_known_cells(self) -> None:
        for value, name in (({}, "mapping"), ([999_999], "unknown")):
            with self.subTest(cell_ids=name):
                world = self.world()
                self.tamper(world["aquifer_systems"][0], "cell_ids", value)
                self.assert_rejects(
                    world, f"aquifer_system_{name}", "aquifer system records invalid"
                )

    def test_groundwater_flow_cell_indices_are_range_checked(self) -> None:
        world = self.world()
        self.tamper(world["cells"][0], "spring_discharge_index", 5.0)
        self.assert_rejects(world, "gwflow_cell", "groundwater flow cell fields invalid")

    def test_groundwater_flow_system_aggregates_are_replayed(self) -> None:
        world = self.world()
        self.tamper(world["groundwater_flow_systems"][0], "discharge_to_recharge_ratio", 5.0)
        self.assert_rejects(
            world,
            "gwflow_system",
            "groundwater flow system records invalid",
            "groundwater flow system ids are not unique",
            "groundwater flow system membership does not match cells",
        )

    def test_groundwater_flow_system_id_lists_must_be_lists(self) -> None:
        for field, value, name in (
            ("recharge_cell_ids", {}, "recharge_mapping"),
            ("cell_ids", [999_999], "unknown_cell"),
        ):
            with self.subTest(field=field):
                world = self.world()
                self.tamper(world["groundwater_flow_systems"][0], field, value)
                self.assert_rejects(
                    world, f"gwflow_system_{name}", "groundwater flow system records invalid"
                )

    def test_groundwater_discharge_cannot_exceed_the_recharge_source(self) -> None:
        """Discharge is a finite draw on recharge, not a free source term."""

        world = self.world()
        cell = self.first(
            (
                item
                for item in world["cells"]
                if str(item.get("aquifer_class", "")) != "marine_excluded"
            ),
            "non-marine aquifer cell",
        )
        # Raise the depth and the volume together so the per-cell volume identity
        # still holds and only the basin-wide source budget can object.
        area = max(0.0, float(cell.get("area_km2", 0.0)))
        cell["groundwater_discharge_mm_y"] = self.assert_changed(
            cell["groundwater_discharge_mm_y"], 1_000_000.0, "the cell discharge depth"
        )
        cell["groundwater_discharge_km3_y"] = 1_000_000.0 * area * 0.000001
        self.assert_rejects(
            world, "gw_discharge_excess", "groundwater discharge exceeds finite recharge source"
        )

    def test_karst_cell_fields_are_range_checked(self) -> None:
        for value, name in ((5.0, "range"), ("not-a-number", "type")):
            with self.subTest(value=value):
                world = self.world()
                self.tamper(world["cells"][0], "cave_development_index", value)
                self.assert_rejects(world, f"karst_cell_{name}", "karst cell fields invalid")


# --------------------------------------------------------------------------
# Vegetation succession, renewable resources, species ranges and wildfire.
# --------------------------------------------------------------------------

VEGETATION_INVALID = "vegetation succession histories invalid"


class EcosystemRecordTest(ValidateCliTestCase):
    """Ecosystem cell diagnostics and the record families derived from them."""

    def test_ecosystem_cell_fields_are_range_checked(self) -> None:
        world = self.world()
        self.tamper(world["cells"][0], "vegetation_recovery_years", 0)
        self.assert_rejects(world, "ecosystem_cell", "ecosystem parent support cell 0: supported recovery years must be a positive integer")

    def test_vegetation_history_steps_must_be_a_list(self) -> None:
        world = self.world()
        self.tamper(world["vegetation_succession_histories"][0], "steps", {})
        self.assert_rejects(world, "veg_steps_mapping", VEGETATION_INVALID)

    def test_vegetation_history_needs_four_steps(self) -> None:
        world = self.world()
        history = world["vegetation_succession_histories"][0]
        self.tamper(history, "steps", history["steps"][:-1])
        self.tamper(history, "step_count", len(history["steps"]))
        self.assert_rejects(world, "veg_steps_short", VEGETATION_INVALID)

    def test_vegetation_step_fields_are_replayed_against_the_cell(self) -> None:
        for field, value, name in (
            ("recovery_fraction", 5.0, "recovery"),
            ("primary_productivity_index", 5.0, "primary"),
        ):
            with self.subTest(field=field):
                world = self.world()
                self.tamper(
                    world["vegetation_succession_histories"][0]["steps"][0], field, value
                )
                self.assert_rejects(world, f"veg_step_{name}", VEGETATION_INVALID)

    def test_vegetation_history_endpoints_must_match_its_steps(self) -> None:
        for field, name in (
            ("initial_succession_stage", "initial"),
            ("final_succession_stage", "final"),
        ):
            with self.subTest(field=field):
                world = self.world()
                self.tamper(world["vegetation_succession_histories"][0], field, "bogus_stage")
                self.assert_rejects(world, f"veg_stage_{name}", VEGETATION_INVALID)

    def test_vegetation_history_means_are_replayed(self) -> None:
        world = self.world()
        self.tamper(world["vegetation_succession_histories"][0], "mean_canopy_closure_index", 5.0)
        self.assert_rejects(
            world,
            "veg_mean",
            VEGETATION_INVALID,
            "vegetation succession history ids are not unique",
            "vegetation succession histories do not match cells",
        )

    def test_renewable_resource_records_are_replayed_against_cells(self) -> None:
        world = self.world()
        self.tamper(world["renewable_resource_records"][0], "regeneration_years", 0)
        self.assert_rejects(
            world,
            "renewable",
            "renewable resource records invalid",
            "renewable resource record ids are not unique",
            "renewable resource records do not match cells",
        )

    def test_species_range_cell_fields_are_range_checked(self) -> None:
        for field, value, name, message in (
            ("species_guild_richness_count", -1, "richness", "guild richness count mismatch"),
            ("species_endemism_index", "not-a-number", "endemism_type", "species_endemism_index mismatch"),
            ("species_range_record_ids", {}, "ids_mapping", "range inverse mismatch"),
            ("species_range_record_ids", ["not-an-id"], "ids_text", "range inverse mismatch"),
        ):
            with self.subTest(field=field, case=name):
                world = self.world()
                self.tamper(world["cells"][0], field, value)
                self.assert_rejects(
                    world, f"species_cell_{name}", "species parent cell 0: " + message
                )

    def test_species_range_record_identity_fields_are_checked(self) -> None:
        for field, value, name in (
            ("id", "not-an-id", "id_type"),
            ("cell_ids", {}, "cells_mapping"),
            ("cell_ids", ["not-an-id"], "cells_text"),
            ("guild_type", "bogus_guild", "guild"),
        ):
            with self.subTest(field=field, case=name):
                world = self.world()
                self.tamper(world["species_range_records"][0], field, value)
                self.assert_rejects(world, f"species_rec_{name}", "species parent range 0: guild/member/component identity mismatch")

    def test_species_range_record_aggregates_are_replayed(self) -> None:
        world = self.world()
        self.tamper(world["species_range_records"][0], "endemism_index", 5.0)
        self.assert_rejects(
            world,
            "species_rec_endemism",
            "species parent range 0: endemism_index mismatch",
        )

    def test_species_record_duplicates_and_inverse_links_are_independent_mutations(self) -> None:
        world = self.world()
        self.assertGreaterEqual(len(world["species_range_records"]), 2)
        self.tamper(world["species_range_records"][1], "id", world["species_range_records"][0]["id"])
        self.assert_rejects(world, "species_duplicate_id", "species parent range 1: guild/member/component identity mismatch")
        world = self.world()
        cell = self.first((c for c in world["cells"] if c["species_range_record_ids"]), "species member cell")
        self.tamper(cell, "species_range_record_ids", [])
        self.assert_rejects(world, "species_inverse", f"species parent cell {cell['id']}: range inverse mismatch")

    def test_wildfire_cell_fields_are_range_checked(self) -> None:
        for field, value, name, message in (
            ("wildfire_firebreak_index", 5.0, "firebreak", "cell 0: wildfire_firebreak_index"),
            ("wildfire_ignition_potential_index", "not-a-number", "ignition_type", "non-numeric consumed input"),
            ("wildfire_spread_history_ids", {}, "ids_mapping", "cell 0: inverse histories"),
            ("wildfire_spread_history_ids", ["not-an-id"], "ids_text", "cell 0: inverse histories"),
        ):
            with self.subTest(field=field, case=name):
                world = self.world()
                self.tamper(world["cells"][0], field, value)
                self.assert_rejects(
                    world, f"wildfire_cell_{name}", "wildfire availability: " + message
                )

    def test_wildfire_history_identity_fields_are_checked(self) -> None:
        for field, value, name in (
            ("id", "not-an-id", "id_type"),
            ("cell_ids", {}, "cells_mapping"),
            ("cell_ids", ["not-an-id"], "cells_text"),
        ):
            with self.subTest(field=field, case=name):
                world = self.world()
                self.tamper(world["wildfire_spread_histories"][0], field, value)
                self.assert_rejects(world, f"wildfire_hist_{name}", "wildfire availability: history 0: " + field)

    def test_wildfire_history_probability_bounds_are_checked(self) -> None:
        world = self.world()
        self.tamper(world["wildfire_spread_histories"][0], "max_spread_probability_index", 5.0)
        self.assert_rejects(world, "wildfire_hist_probability", "wildfire availability: history 0: max_spread_probability_index")

    def test_wildfire_history_aggregates_are_replayed(self) -> None:
        world = self.world()
        self.tamper(world["wildfire_spread_histories"][0], "mean_firebreak_index", 5.0)
        self.assert_rejects(
            world,
            "wildfire_hist_mean",
            "wildfire availability: history 0: mean_firebreak_index",
        )

    def test_fire_record_duplicates_and_inverse_links_are_independent_mutations(self) -> None:
        world = self.world()
        self.assertGreaterEqual(len(world["wildfire_spread_histories"]), 2)
        self.tamper(world["wildfire_spread_histories"][1], "id", world["wildfire_spread_histories"][0]["id"])
        self.assert_rejects(world, "fire_duplicate_id", "wildfire availability: history 1: id")
        world = self.world()
        cell = self.first((c for c in world["cells"] if c["wildfire_spread_history_ids"]), "fire member cell")
        self.tamper(cell, "wildfire_spread_history_ids", [])
        self.assert_rejects(world, "fire_inverse", f"wildfire availability: cell {cell['id']}: inverse histories")

    def test_wildfire_spread_steps_are_replayed(self) -> None:
        for field, value, name in (
            ("burned_area_km2", "not-a-number", "area_type"),
            ("step_index", 99, "index"),
            ("cumulative_burned_cell_count", 999, "cumulative"),
        ):
            with self.subTest(field=field, case=name):
                world = self.world()
                self.tamper(world["wildfire_spread_histories"][0]["steps"][0], field, value)
                self.assert_rejects(world, f"wildfire_step_{name}", "wildfire availability: history 0: steps")

    def test_wildfire_steps_must_burn_every_cell_of_the_history(self) -> None:
        world = self.world()
        history = world["wildfire_spread_histories"][0]
        self.tamper(history, "steps", history["steps"][:-1])
        self.tamper(history, "spread_step_count", len(history["steps"]))
        self.assert_rejects(world, "wildfire_step_dropped", "wildfire availability: history 0: spread_step_count")


# --------------------------------------------------------------------------
# Resource deposits and ore genesis.
# --------------------------------------------------------------------------


class ResourceRecordTest(ValidateCliTestCase):
    """Resource deposits and the ore-genesis cell diagnostics."""

    def test_resource_deposit_records_are_replayed_against_cells(self) -> None:
        world = self.world()
        self.tamper(world["resource_deposits"][0], "renewability_index", 5.0)
        self.assert_rejects(
            world,
            "deposit",
            f"resource deposit 0 cell {world['resource_deposits'][0]['cell_id']}: renewability_index must be a finite unit index",
        )

    def test_resource_duplicates_and_source_links_are_independent_mutations(self) -> None:
        world = self.world()
        self.assertGreaterEqual(len(world["resource_deposits"]), 2)
        second = world["resource_deposits"][1]
        self.tamper(second, "id", world["resource_deposits"][0]["id"])
        self.assert_rejects(world, "deposit_duplicate_id", f"resource deposit 1 cell {second['cell_id']}: IDs must be dense in cell order")
        world = self.world()
        first, second = world["resource_deposits"][:2]
        original_cell = first["cell_id"]
        self.tamper(first, "cell_id", second["cell_id"])
        self.assert_rejects(world, "deposit_source", f"resource deposit 0 cell {original_cell}: source linkage mismatch")

    def test_resource_deposits_must_cover_every_resource_cell(self) -> None:
        world = self.world()
        self.assertTrue(world["resource_deposits"], "no generated resource deposit to drop")
        world["resource_deposits"].pop()
        self.assert_rejects(
            world,
            "deposit_dropped",
            "resource deposit coverage: missing supported deposit or unexpected unsupported deposit",
        )

    def test_ore_genesis_cell_indices_are_range_checked(self) -> None:
        world = self.world()
        self.tamper(world["cells"][0], "hydrothermal_alteration_index", 5.0)
        self.assert_rejects(world, "ore_cell_range", "ore genesis cell fields invalid")

    def test_ore_genesis_cell_system_id_must_be_an_integer(self) -> None:
        world = self.world()
        self.tamper(world["cells"][0], "ore_genesis_system_id", "not-an-id")
        self.assert_rejects(world, "ore_cell_type", "ore genesis cell fields invalid")


# --------------------------------------------------------------------------
# Karst systems only exist at 512 cells and up.
# --------------------------------------------------------------------------


class KarstSystemTest(ValidateCliTestCase):
    """Karst system records, which the 128-cell world does not generate."""

    WORLD_KEY = "mid_512"

    def test_world_generates_karst_systems(self) -> None:
        self.assert_control_accepted()
        self.assertTrue(
            self.baseline["karst_systems"],
            "mid_512 no longer generates karst systems; the checks below are vacuous",
        )

    def test_karst_system_fields_are_required(self) -> None:
        world = self.world()
        system = world["karst_systems"][0]
        self.assertIn("limestone_cell_fraction", system, "not a generated karst system field")
        del system["limestone_cell_fraction"]
        self.assert_rejects(world, "karst_fields", "karst system fields missing")

    def test_karst_system_aggregates_are_replayed(self) -> None:
        world = self.world()
        self.tamper(world["karst_systems"][0], "cell_count", 999)
        self.assert_rejects(world, "karst_count", "karst system records invalid")

    def test_karst_system_cell_ids_must_be_a_list_of_known_cells(self) -> None:
        for value, name in (({}, "mapping"), ([999_999], "unknown")):
            with self.subTest(cell_ids=name):
                world = self.world()
                self.tamper(world["karst_systems"][0], "cell_ids", value)
                self.assert_rejects(world, f"karst_{name}", "karst system records invalid")

    def test_duplicate_karst_system_ids_are_reported(self) -> None:
        world = self.world()
        world["karst_systems"].append(copy.deepcopy(world["karst_systems"][0]))
        self.assert_rejects(
            world,
            "karst_duplicate",
            "karst system ids are not unique",
            "karst system records invalid",
        )

    def test_karst_system_membership_must_cover_every_karst_cell(self) -> None:
        world = self.world()
        system = world["karst_systems"][0]
        self.tamper(system, "cell_ids", [])
        self.tamper(system, "cell_count", 0)
        self.assert_rejects(
            world,
            "karst_empty",
            "karst system membership does not match cells",
            "karst system records invalid",
        )
