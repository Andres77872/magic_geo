"""Guard, degenerate, and violation paths of two geo replay enrichers.

``tests/test_geo_validation.py`` drives both modules down their healthy path on a
generated world and flips a handful of registry fields.  This file takes the
other side: every branch that *reports* a defect, classifies a missing or
malformed collection, or refuses to classify at all.

Two devices keep the cases honest.  The provenance registry is exercised on a
hand-built world (:func:`_synthetic_geo_world`) so history payloads can be empty,
absent, or malformed at will; one generated geo world proves that fixture is
faithful, field for field, to what the pipeline actually emits.  The control
volume replay is exercised on the canonical 128-cell Fibonacci world, a 162-cell
geodesic world, and a synthetic spherical cube whose control volumes have exact
analytic areas (``4 pi r^2 / 6`` per face), so the replayed area is checked
against theory rather than against the emitted number it is meant to audit.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Callable
from unittest import TestCase

from support import worlds

from magic_geo.api import generate_geo_world
from magic_geo.control_volume_geometry import (
    CONTROL_VOLUME_AREA_MODELS,
    inspect_control_volume_geometry,
)
from magic_geo.geo_evolution_provenance import (
    DIAGNOSTIC_TRAJECTORY_FAMILIES,
    EVOLUTION_PROVENANCE_MODEL_TYPE,
    NATIVE_STATE_HISTORY_FAMILIES,
    NATIVE_STATE_MUTATION_EVIDENCE,
    NOMINAL_TIME_BASIS,
    NOMINAL_TIME_MODEL,
    NOMINAL_TIME_SOURCE_PARAMETER,
    SOIL_LINKED_TIME_BASIS,
    enrich_world_with_geo_evolution_provenance,
    validate_geo_evolution_provenance,
)

ALL_FAMILIES: tuple[str, ...] = (
    NATIVE_STATE_HISTORY_FAMILIES + DIAGNOSTIC_TRAJECTORY_FAMILIES
)

#: Fields the validator checks on every family record, native or diagnostic.
SHARED_RECORD_FIELDS: tuple[str, ...] = (
    "record_count",
    "state_mutation_evidence",
    "temporal_role",
    "physical_time_resolved",
    "nominal_time_calibrated",
    "nominal_time_coordinate_available",
    "time_basis",
)

TIMESTEP_MA = 5.0
NATIVE_STEP_COUNT = 2


def _native_step(index: int) -> dict[str, Any]:
    """One native nominal-time ledger entry; index 0 is the initial snapshot."""
    start = 0.0 if index == 0 else (index - 1) * TIMESTEP_MA
    end = 0.0 if index == 0 else index * TIMESTEP_MA
    return {
        "nominal_time_model": NOMINAL_TIME_MODEL,
        "nominal_time_basis": NOMINAL_TIME_BASIS,
        "nominal_time_source_parameter": NOMINAL_TIME_SOURCE_PARAMETER,
        "nominal_time_unit": "Ma",
        "nominal_time_calibrated": False,
        "physical_time_resolved": False,
        "nominal_interval_start_ma": start,
        "nominal_interval_end_ma": end,
        "nominal_interval_duration_ma": end - start,
        "nominal_elapsed_time_ma": end,
        "advances_nominal_time": end > start,
    }


def _synthetic_geo_world(*, soil_linked: bool = True) -> dict[str, Any]:
    """An enriched geo-only world with hand-built history payloads.

    Every diagnostic family gets a different record count so a mirrored counter
    cannot pass by coincidence, and one native family stays empty because the
    generator really does emit an empty depression-correction ledger.
    """
    world: dict[str, Any] = {
        "generation_scope": "geo_only",
        "simulation_clock": {
            "physical_time_resolved": False,
            "nominal_time_calibrated": False,
            "nominal_time_model": NOMINAL_TIME_MODEL,
            "nominal_time_basis": NOMINAL_TIME_BASIS,
            "nominal_time_source_parameter": NOMINAL_TIME_SOURCE_PARAMETER,
            "nominal_timestep_ma": TIMESTEP_MA,
            "final_nominal_elapsed_time_ma": TIMESTEP_MA * NATIVE_STEP_COUNT,
        },
    }
    if soil_linked:
        world["soil_pedogenesis_model"] = {
            "linked_nominal_time_coordinate_available": True
        }
    for family in NATIVE_STATE_HISTORY_FAMILIES:
        world[family] = [
            _native_step(index) for index in range(NATIVE_STEP_COUNT + 1)
        ]
    world["numeric_depression_correction_history"] = []
    for index, family in enumerate(DIAGNOSTIC_TRAJECTORY_FAMILIES):
        world[family] = [{"steps": []} for _ in range(index)]
    return enrich_world_with_geo_evolution_provenance(world)


def _provenance(world: dict[str, Any]) -> dict[str, Any]:
    return world["geo_evolution_provenance"]


def _record(world: dict[str, Any], family: str) -> dict[str, Any]:
    return next(
        record
        for record in _provenance(world)["families"]
        if record["family"] == family
    )


def _every_family_record_violation() -> set[str]:
    """Violations reported when no usable family record survives lookup."""
    expected: set[str] = set()
    for family in ALL_FAMILIES:
        expected.update(f"{family}: {field}" for field in SHARED_RECORD_FIELDS)
        if family in DIAGNOSTIC_TRAJECTORY_FAMILIES:
            expected.add(f"{family}: nominal_time_linkage")
    return expected


def _registry_header_violations() -> set[str]:
    """Violations reported when the registry object itself is unusable."""
    return {
        "model_type",
        "generation_scope",
        "physical_time_resolved must be false",
        "nominal_time_coordinate_available",
        "nominal_time_calibrated must be false",
        "nominal_time_model",
        "nominal_time_basis",
        "nominal_time_source_parameter",
        "native family registry",
        "diagnostic family registry",
        "family records",
        "family record coverage/uniqueness",
        "family_count",
        "native_state_history_family_count",
        "diagnostic_trajectory_family_count",
    }


class GeoEvolutionProvenanceEnrichmentTests(TestCase):
    """Classification of absent, malformed, and unlinked history payloads."""

    def test_empty_world_is_classified_as_a_fully_absent_registry(self) -> None:
        world: dict[str, Any] = {}

        enriched = enrich_world_with_geo_evolution_provenance(world)
        registry = enriched["geo_evolution_provenance"]
        records = {record["family"]: record for record in registry["families"]}

        self.assertIs(enriched, world)
        self.assertEqual(registry["model_type"], EVOLUTION_PROVENANCE_MODEL_TYPE)
        self.assertEqual(registry["generation_scope"], "unknown")
        self.assertIsNone(registry["nominal_timestep_ma"])
        self.assertIsNone(registry["final_nominal_elapsed_time_ma"])
        self.assertEqual(registry["family_count"], len(ALL_FAMILIES))
        self.assertEqual(sorted(records), sorted(ALL_FAMILIES))
        self.assertEqual(
            sorted(record["record_count"] for record in records.values()),
            [-1] * len(ALL_FAMILIES),
        )
        self.assertFalse(
            records["soil_profile_histories"][
                "nominal_time_coordinate_available"
            ]
        )
        self.assertEqual(
            records["soil_profile_histories"]["time_basis"],
            "diagnostic_index_step",
        )
        self.assertEqual(
            records["soil_profile_histories"]["nominal_time_linkage"], "none"
        )

    def test_non_list_history_payloads_are_counted_as_absent(self) -> None:
        for label, payload in (
            ("mapping", {"steps": []}),
            ("text", "history"),
            ("null", None),
            ("integer", 3),
        ):
            with self.subTest(payload=label):
                world = enrich_world_with_geo_evolution_provenance(
                    {
                        "plate_motion_history": payload,
                        "ice_sheet_histories": [{}, {}],
                    }
                )
                records = {
                    record["family"]: record
                    for record in _provenance(world)["families"]
                }

                self.assertEqual(records["plate_motion_history"]["record_count"], -1)
                self.assertEqual(records["ice_sheet_histories"]["record_count"], 2)

    def test_soil_linkage_requires_the_flag_to_be_exactly_true(self) -> None:
        for label, model in (
            ("absent", None),
            ("not_a_mapping", ["linked"]),
            ("flag_missing", {}),
            ("flag_false", {"linked_nominal_time_coordinate_available": False}),
            ("flag_text", {"linked_nominal_time_coordinate_available": "true"}),
            ("flag_one", {"linked_nominal_time_coordinate_available": 1}),
        ):
            with self.subTest(model=label):
                world: dict[str, Any] = {"soil_profile_histories": []}
                if model is not None:
                    world["soil_pedogenesis_model"] = model
                enrich_world_with_geo_evolution_provenance(world)
                record = _record(world, "soil_profile_histories")

                self.assertFalse(record["nominal_time_coordinate_available"])
                self.assertEqual(record["time_basis"], "diagnostic_index_step")
                self.assertEqual(record["nominal_time_linkage"], "none")

        linked = enrich_world_with_geo_evolution_provenance(
            {
                "soil_profile_histories": [],
                "soil_pedogenesis_model": {
                    "linked_nominal_time_coordinate_available": True
                },
            }
        )
        record = _record(linked, "soil_profile_histories")
        self.assertTrue(record["nominal_time_coordinate_available"])
        self.assertEqual(record["time_basis"], SOIL_LINKED_TIME_BASIS)
        self.assertEqual(
            record["nominal_time_linkage"],
            "contextual_native_stage_link_without_state_mutation",
        )

    def test_clock_mirror_ignores_a_non_mapping_simulation_clock(self) -> None:
        for label, clock in (
            ("text", "clock"),
            ("list", [5.0]),
            ("null", None),
        ):
            with self.subTest(clock=label):
                world = enrich_world_with_geo_evolution_provenance(
                    {"simulation_clock": clock, "generation_scope": 42}
                )
                registry = _provenance(world)

                self.assertIsNone(registry["nominal_timestep_ma"])
                self.assertIsNone(registry["final_nominal_elapsed_time_ma"])
                self.assertEqual(registry["generation_scope"], "42")

    def test_family_roles_split_native_ledgers_from_diagnostics(self) -> None:
        world = _synthetic_geo_world()
        records = {
            record["family"]: record for record in _provenance(world)["families"]
        }

        for family in NATIVE_STATE_HISTORY_FAMILIES:
            with self.subTest(family=family):
                record = records[family]
                self.assertEqual(
                    record["state_mutation_evidence"],
                    NATIVE_STATE_MUTATION_EVIDENCE[family],
                )
                self.assertTrue(record["nominal_time_coordinate_available"])
                self.assertEqual(record["time_basis"], NOMINAL_TIME_BASIS)
                self.assertNotIn("nominal_time_linkage", record)
        for family in DIAGNOSTIC_TRAJECTORY_FAMILIES:
            with self.subTest(family=family):
                record = records[family]
                self.assertEqual(record["state_mutation_evidence"], "no")
                self.assertEqual(
                    record["temporal_role"], "posthoc_diagnostic_trajectory"
                )
                self.assertEqual(record["record_count"], len(world[family]))
        self.assertEqual(
            records["numeric_depression_correction_history"]["temporal_role"],
            "native_mixed_mutation_and_counterfactual_event_ledger",
        )
        self.assertEqual(
            records["climate_seasonal_histories"]["time_basis"],
            "monthly_climatology",
        )


class GeoEvolutionProvenanceGeneratedWorldTests(TestCase):
    """The synthetic registry fixture has to match a generated geo world."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(worlds.canonical_config("replay_128"))
        cls.synthetic = _synthetic_geo_world()

    def test_generated_registry_passes_and_matches_the_fixture(self) -> None:
        result = validate_geo_evolution_provenance(self.world)
        generated = {
            record["family"]: record
            for record in _provenance(self.world)["families"]
        }
        built = {
            record["family"]: record
            for record in _provenance(self.synthetic)["families"]
        }

        self.assertEqual(result["status"], "passed", result["evidence"])
        self.assertEqual(result["observed"]["violation_count"], 0)
        self.assertEqual(
            sorted(_provenance(self.world)), sorted(_provenance(self.synthetic))
        )
        self.assertEqual(sorted(generated), sorted(built))
        for family, record in generated.items():
            with self.subTest(family=family):
                self.assertEqual(
                    {
                        key: value
                        for key, value in record.items()
                        if key != "record_count"
                    },
                    {
                        key: value
                        for key, value in built[family].items()
                        if key != "record_count"
                    },
                )
                self.assertEqual(record["record_count"], len(self.world[family]))


class GeoEvolutionProvenanceViolationTests(TestCase):
    """One tamper at a time against the registry, its clock, and its payloads."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.control = validate_geo_evolution_provenance(_synthetic_geo_world())

    def setUp(self) -> None:
        self.assertEqual(
            self.control["status"], "passed", self.control["evidence"]
        )

    def assign(self, container: dict, key: str, value: Any) -> None:
        """Write ``value`` after proving the fixture held something else."""
        self.assertIn(key, container)
        self.assertNotEqual(
            container[key], value, f"inert tamper: {key} already holds {value!r}"
        )
        container[key] = value

    def violations_for(self, mutate: Callable[[Any, dict], None]) -> list[str]:
        world = _synthetic_geo_world()
        mutate(self, world)
        result = validate_geo_evolution_provenance(world)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["passed"])
        self.assertEqual(
            result["message"],
            "Natural history temporal roles, counts, or physical-time claims"
            " are inconsistent.",
        )
        violations = result["evidence"]["violations"]
        self.assertEqual(result["observed"]["violation_count"], len(violations))
        return sorted(violations)

    def run_cases(self, cases: tuple) -> None:
        for label, mutate, expected in cases:
            with self.subTest(case=label):
                self.assertEqual(self.violations_for(mutate), sorted(expected))

    def test_registry_header_fields_are_reported_one_by_one(self) -> None:
        self.run_cases(
            (
                (
                    "model_type",
                    lambda test, world: test.assign(
                        _provenance(world), "model_type", "legacy_registry_v1"
                    ),
                    ["model_type"],
                ),
                (
                    "generation_scope",
                    lambda test, world: test.assign(
                        _provenance(world), "generation_scope", "full"
                    ),
                    ["generation_scope"],
                ),
                (
                    "physical_time_resolved",
                    lambda test, world: test.assign(
                        _provenance(world), "physical_time_resolved", True
                    ),
                    ["physical_time_resolved must be false"],
                ),
                (
                    "nominal_time_coordinate_available",
                    lambda test, world: test.assign(
                        _provenance(world),
                        "nominal_time_coordinate_available",
                        False,
                    ),
                    ["nominal_time_coordinate_available"],
                ),
                (
                    "nominal_time_calibrated",
                    lambda test, world: test.assign(
                        _provenance(world), "nominal_time_calibrated", True
                    ),
                    ["nominal_time_calibrated must be false"],
                ),
                (
                    "nominal_time_model",
                    lambda test, world: test.assign(
                        _provenance(world), "nominal_time_model", "wall_clock"
                    ),
                    ["nominal_time_model"],
                ),
                (
                    "nominal_time_basis",
                    lambda test, world: test.assign(
                        _provenance(world), "nominal_time_basis", "years"
                    ),
                    ["nominal_time_basis"],
                ),
                (
                    "nominal_time_source_parameter",
                    lambda test, world: test.assign(
                        _provenance(world),
                        "nominal_time_source_parameter",
                        "erosion.iterations",
                    ),
                    ["nominal_time_source_parameter"],
                ),
                (
                    "family_count",
                    lambda test, world: test.assign(
                        _provenance(world), "family_count", len(ALL_FAMILIES) - 1
                    ),
                    ["family_count"],
                ),
                (
                    "native_state_history_family_count",
                    lambda test, world: test.assign(
                        _provenance(world),
                        "native_state_history_family_count",
                        len(NATIVE_STATE_HISTORY_FAMILIES) - 1,
                    ),
                    ["native_state_history_family_count"],
                ),
                (
                    "diagnostic_trajectory_family_count",
                    lambda test, world: test.assign(
                        _provenance(world),
                        "diagnostic_trajectory_family_count",
                        len(DIAGNOSTIC_TRAJECTORY_FAMILIES) - 1,
                    ),
                    ["diagnostic_trajectory_family_count"],
                ),
                (
                    "native_family_registry",
                    lambda test, world: _provenance(world)[
                        "native_state_history_families"
                    ].pop(),
                    ["native family registry"],
                ),
                (
                    "diagnostic_family_registry",
                    lambda test, world: test.assign(
                        _provenance(world),
                        "diagnostic_trajectory_families",
                        list(reversed(DIAGNOSTIC_TRAJECTORY_FAMILIES)),
                    ),
                    ["diagnostic family registry"],
                ),
            )
        )

    def test_simulation_clock_mirrors_are_reported_per_defect(self) -> None:
        reset = [
            "simulation_clock physical-time mirror",
            "simulation_clock nominal-time mirror",
            "nominal_timestep_ma mirror",
            "final_nominal_elapsed_time_ma mirror",
        ]
        self.run_cases(
            (
                (
                    "clock_absent",
                    lambda test, world: world.pop("simulation_clock"),
                    reset,
                ),
                (
                    "clock_not_a_mapping",
                    lambda test, world: test.assign(
                        world, "simulation_clock", "coupled_stage_clock"
                    ),
                    reset,
                ),
                (
                    "clock_claims_physical_time",
                    lambda test, world: test.assign(
                        world["simulation_clock"], "physical_time_resolved", True
                    ),
                    reset,
                ),
                (
                    "clock_claims_calibration",
                    lambda test, world: test.assign(
                        world["simulation_clock"], "nominal_time_calibrated", True
                    ),
                    ["simulation_clock nominal-time mirror"],
                ),
                (
                    "clock_time_model",
                    lambda test, world: test.assign(
                        world["simulation_clock"], "nominal_time_model", "wall"
                    ),
                    ["simulation_clock nominal-time mirror"],
                ),
                (
                    "clock_time_basis",
                    lambda test, world: test.assign(
                        world["simulation_clock"], "nominal_time_basis", "years"
                    ),
                    ["simulation_clock nominal-time mirror"],
                ),
                (
                    "clock_source_parameter",
                    lambda test, world: test.assign(
                        world["simulation_clock"],
                        "nominal_time_source_parameter",
                        "erosion.iterations",
                    ),
                    ["simulation_clock nominal-time mirror"],
                ),
                (
                    "clock_timestep_drift",
                    lambda test, world: test.assign(
                        world["simulation_clock"],
                        "nominal_timestep_ma",
                        TIMESTEP_MA + 2.5,
                    ),
                    ["nominal_timestep_ma mirror"],
                ),
                (
                    "registry_timestep_drift",
                    lambda test, world: test.assign(
                        _provenance(world),
                        "nominal_timestep_ma",
                        TIMESTEP_MA + 2.5,
                    ),
                    ["nominal_timestep_ma mirror"],
                ),
                (
                    "clock_elapsed_drift",
                    lambda test, world: test.assign(
                        world["simulation_clock"],
                        "final_nominal_elapsed_time_ma",
                        99.0,
                    ),
                    ["final_nominal_elapsed_time_ma mirror"],
                ),
                (
                    "registry_elapsed_drift",
                    lambda test, world: test.assign(
                        _provenance(world), "final_nominal_elapsed_time_ma", 99.0
                    ),
                    ["final_nominal_elapsed_time_ma mirror"],
                ),
            )
        )

    def test_family_record_collection_defects_are_distinguished(self) -> None:
        unusable = _every_family_record_violation() | {
            "family records",
            "family record coverage/uniqueness",
        }
        dropped_native = {
            f"plate_motion_history: {field}" for field in SHARED_RECORD_FIELDS
        } | {"family record coverage/uniqueness"}
        self.run_cases(
            (
                (
                    "families_not_a_list",
                    lambda test, world: test.assign(
                        _provenance(world), "families", "twenty families"
                    ),
                    unusable,
                ),
                (
                    "families_hold_a_non_mapping",
                    lambda test, world: _provenance(world)["families"].append(
                        "plate_motion_history"
                    ),
                    unusable,
                ),
                (
                    "duplicate_family_record",
                    lambda test, world: _provenance(world)["families"].append(
                        dict(_record(world, "ice_sheet_histories"))
                    ),
                    ["family record coverage/uniqueness"],
                ),
                (
                    "missing_family_record",
                    lambda test, world: _provenance(world)["families"].remove(
                        _record(world, "plate_motion_history")
                    ),
                    dropped_native,
                ),
            )
        )

    def test_family_classification_fields_are_reported_per_family(self) -> None:
        self.run_cases(
            (
                (
                    "record_count",
                    lambda test, world: test.assign(
                        _record(world, "ice_sheet_histories"), "record_count", 99
                    ),
                    ["ice_sheet_histories: record_count"],
                ),
                (
                    "payload_grew_after_enrichment",
                    lambda test, world: world[
                        "vegetation_succession_histories"
                    ].append({"steps": []}),
                    ["vegetation_succession_histories: record_count"],
                ),
                (
                    "diagnostic_claims_mutation",
                    lambda test, world: test.assign(
                        _record(world, "soil_profile_histories"),
                        "state_mutation_evidence",
                        "yes",
                    ),
                    ["soil_profile_histories: state_mutation_evidence"],
                ),
                (
                    "mixed_ledger_claims_pure_mutation",
                    lambda test, world: test.assign(
                        _record(world, "numeric_depression_correction_history"),
                        "temporal_role",
                        "native_state_mutation_ledger",
                    ),
                    ["numeric_depression_correction_history: temporal_role"],
                ),
                (
                    "native_ledger_claims_diagnostic_role",
                    lambda test, world: test.assign(
                        _record(world, "plate_motion_history"),
                        "temporal_role",
                        "posthoc_diagnostic_trajectory",
                    ),
                    ["plate_motion_history: temporal_role"],
                ),
                (
                    "record_claims_physical_time",
                    lambda test, world: test.assign(
                        _record(world, "wildfire_spread_histories"),
                        "physical_time_resolved",
                        True,
                    ),
                    ["wildfire_spread_histories: physical_time_resolved"],
                ),
                (
                    "record_claims_calibration",
                    lambda test, world: test.assign(
                        _record(world, "wildfire_spread_histories"),
                        "nominal_time_calibrated",
                        True,
                    ),
                    ["wildfire_spread_histories: nominal_time_calibrated"],
                ),
                (
                    "native_record_drops_nominal_coordinate",
                    lambda test, world: test.assign(
                        _record(world, "plate_motion_history"),
                        "nominal_time_coordinate_available",
                        False,
                    ),
                    ["plate_motion_history: nominal_time_coordinate_available"],
                ),
                (
                    "diagnostic_record_claims_nominal_coordinate",
                    lambda test, world: test.assign(
                        _record(world, "ice_flowline_histories"),
                        "nominal_time_coordinate_available",
                        True,
                    ),
                    ["ice_flowline_histories: nominal_time_coordinate_available"],
                ),
                (
                    "climatology_basis_downgraded",
                    lambda test, world: test.assign(
                        _record(world, "climate_seasonal_histories"),
                        "time_basis",
                        "diagnostic_index_step",
                    ),
                    ["climate_seasonal_histories: time_basis"],
                ),
                (
                    "diagnostic_claims_native_linkage",
                    lambda test, world: test.assign(
                        _record(world, "ice_flowline_histories"),
                        "nominal_time_linkage",
                        "contextual_native_stage_link_without_state_mutation",
                    ),
                    ["ice_flowline_histories: nominal_time_linkage"],
                ),
            )
        )

    def test_soil_linkage_downgrade_reports_the_three_linked_fields(self) -> None:
        linked = [
            "soil_profile_histories: nominal_time_coordinate_available",
            "soil_profile_histories: time_basis",
            "soil_profile_histories: nominal_time_linkage",
        ]
        self.run_cases(
            (
                (
                    "flag_cleared",
                    lambda test, world: test.assign(
                        world["soil_pedogenesis_model"],
                        "linked_nominal_time_coordinate_available",
                        False,
                    ),
                    linked,
                ),
                (
                    "model_removed",
                    lambda test, world: world.pop("soil_pedogenesis_model"),
                    linked,
                ),
                (
                    "model_not_a_mapping",
                    lambda test, world: test.assign(
                        world, "soil_pedogenesis_model", "linked"
                    ),
                    linked,
                ),
            )
        )

    def test_native_linkage_field_is_not_part_of_the_native_contract(
        self,
    ) -> None:
        world = _synthetic_geo_world()
        _record(world, "plate_motion_history")["nominal_time_linkage"] = (
            "contextual_native_stage_link_without_state_mutation"
        )

        result = validate_geo_evolution_provenance(world)

        self.assertEqual(result["status"], "passed", result["evidence"])
        self.assertEqual(result["evidence"]["violations"], [])

    def test_missing_and_malformed_payloads_are_reported_per_family(self) -> None:
        self.run_cases(
            (
                (
                    "payload_is_a_mapping",
                    lambda test, world: test.assign(
                        world, "lake_overflow_histories", {"steps": []}
                    ),
                    ["lake_overflow_histories: payload is not a list"],
                ),
                (
                    "payload_absent",
                    lambda test, world: world.pop("ice_sheet_histories"),
                    ["ice_sheet_histories: payload is not a list"],
                ),
                (
                    "native_payload_absent",
                    lambda test, world: world.pop("plate_motion_history"),
                    ["plate_motion_history: payload is not a list"],
                ),
            )
        )

    def test_native_ledger_entries_are_audited_by_index(self) -> None:
        self.run_cases(
            (
                (
                    "entry_not_a_mapping",
                    lambda test, world: world["plate_motion_history"].__setitem__(
                        1, "second step"
                    ),
                    ["plate_motion_history[1]: record"],
                ),
                (
                    "wrong_time_unit",
                    lambda test, world: test.assign(
                        world["plate_motion_history"][1], "nominal_time_unit", "yr"
                    ),
                    ["plate_motion_history[1]: nominal metadata"],
                ),
                (
                    "entry_claims_physical_time",
                    lambda test, world: test.assign(
                        world["plate_motion_history"][1],
                        "physical_time_resolved",
                        True,
                    ),
                    ["plate_motion_history[1]: nominal metadata"],
                ),
                (
                    "interval_key_missing",
                    lambda test, world: world["plate_motion_history"][1].pop(
                        "nominal_interval_end_ma"
                    ),
                    ["plate_motion_history[1]: nominal interval"],
                ),
                (
                    "interval_not_numeric",
                    lambda test, world: test.assign(
                        world["plate_motion_history"][1],
                        "nominal_interval_duration_ma",
                        "five",
                    ),
                    ["plate_motion_history[1]: nominal interval"],
                ),
                (
                    "interval_is_null",
                    lambda test, world: test.assign(
                        world["plate_motion_history"][1],
                        "nominal_interval_start_ma",
                        None,
                    ),
                    ["plate_motion_history[1]: nominal interval"],
                ),
                (
                    "duration_disagrees_with_endpoints",
                    lambda test, world: test.assign(
                        world["plate_motion_history"][1],
                        "nominal_interval_end_ma",
                        TIMESTEP_MA + 0.5,
                    ),
                    ["plate_motion_history[1]: nominal interval consistency"],
                ),
                (
                    "negative_interval_start",
                    lambda test, world: test.assign(
                        world["plate_motion_history"][2],
                        "nominal_interval_start_ma",
                        -1.0,
                    ),
                    ["plate_motion_history[2]: nominal interval consistency"],
                ),
                (
                    "interval_runs_backwards",
                    lambda test, world: [
                        test.assign(
                            world["plate_motion_history"][1],
                            "nominal_interval_start_ma",
                            TIMESTEP_MA,
                        ),
                        test.assign(
                            world["plate_motion_history"][1],
                            "nominal_interval_end_ma",
                            0.0,
                        ),
                    ],
                    ["plate_motion_history[1]: nominal interval consistency"],
                ),
                (
                    "non_finite_elapsed_time",
                    lambda test, world: test.assign(
                        world["plate_motion_history"][1],
                        "nominal_elapsed_time_ma",
                        float("nan"),
                    ),
                    ["plate_motion_history[1]: nominal interval consistency"],
                ),
                (
                    "snapshot_claims_to_advance_time",
                    lambda test, world: test.assign(
                        world["plate_motion_history"][0],
                        "advances_nominal_time",
                        True,
                    ),
                    ["plate_motion_history[0]: nominal interval consistency"],
                ),
                (
                    "step_denies_advancing_time",
                    lambda test, world: test.assign(
                        world["plate_motion_history"][2],
                        "advances_nominal_time",
                        False,
                    ),
                    ["plate_motion_history[2]: nominal interval consistency"],
                ),
            )
        )

    def test_absent_registry_reports_every_registry_and_payload_defect(
        self,
    ) -> None:
        expected = _registry_header_violations() | _every_family_record_violation()
        expected |= {
            "geo_evolution_provenance must be an object",
            "nominal_timestep_ma mirror",
            "final_nominal_elapsed_time_ma mirror",
        }
        self.run_cases(
            (
                (
                    "registry_is_text",
                    lambda test, world: test.assign(
                        world, "geo_evolution_provenance", "registry"
                    ),
                    expected,
                ),
                (
                    "registry_absent",
                    lambda test, world: world.pop("geo_evolution_provenance"),
                    expected,
                ),
            )
        )

    def test_non_mapping_world_is_reported_without_raising(self) -> None:
        expected = _registry_header_violations() | {
            "geo_evolution_provenance must be an object",
            "simulation_clock physical-time mirror",
            "simulation_clock nominal-time mirror",
        }
        expected |= {
            f"{family}: payload is not a list" for family in ALL_FAMILIES
        }

        for label, payload in (("null", None), ("text", "world"), ("list", [])):
            with self.subTest(world=label):
                result = validate_geo_evolution_provenance(payload)

                self.assertEqual(result["status"], "failed")
                self.assertEqual(
                    sorted(result["evidence"]["violations"]), sorted(expected)
                )
                self.assertEqual(result["observed"]["family_record_count"], 0)
                self.assertEqual(
                    result["observed"]["violation_count"], len(expected)
                )

    def test_report_envelope_is_stable_across_both_verdicts(self) -> None:
        failed = validate_geo_evolution_provenance(None)

        for result in (self.control, failed):
            with self.subTest(status=result["status"]):
                self.assertEqual(result["id"], 0)
                self.assertEqual(result["domain"], "evolution_provenance")
                self.assertEqual(
                    result["name"], "history_family_temporal_semantics"
                )
                self.assertEqual(result["severity"], "error")
                self.assertEqual(
                    result["expected"],
                    {
                        "native_state_history_family_count": len(
                            NATIVE_STATE_HISTORY_FAMILIES
                        ),
                        "diagnostic_trajectory_family_count": len(
                            DIAGNOSTIC_TRAJECTORY_FAMILIES
                        ),
                        "physical_time_resolved": False,
                        "nominal_time_coordinate_available": True,
                        "nominal_time_calibrated": False,
                    },
                )
        self.assertEqual(self.control["status"], "passed")
        self.assertTrue(self.control["passed"])
        self.assertEqual(self.control["observed"]["family_record_count"], 20)
        self.assertEqual(
            self.control["message"],
            "Every natural history family declares whether it records native state"
            " mutation or a post-hoc diagnostic trajectory.",
        )
        self.assertEqual(failed["status"], "failed")
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["observed"]["family_record_count"], 0)
        self.assertEqual(
            failed["message"],
            "Natural history temporal roles, counts, or physical-time claims"
            " are inconsistent.",
        )


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(component * component for component in vector))
    return [component / norm for component in vector]


def _cube_control_volume_world(radius_km: float = 6371.0) -> dict[str, Any]:
    """A six-cell world whose control volumes are the faces of a cube.

    The spherical cube is the Voronoi diagram of the six octahedron vertices, so
    it satisfies every Fibonacci-backend contract the replay checks: 3n-6 edges,
    2n-4 vertices of degree three, edges on the bisectors of their two sites, and
    an exact analytic area of ``4 pi r^2 / 6`` per face.
    """
    axes = (
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
        ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
        ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
        ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)),
    )
    sites = [axis[0] for axis in axes]
    cells = []
    for index, (normal, first, second) in enumerate(axes):
        vertices = [
            _unit(
                [
                    normal[axis] + sign_first * first[axis] + sign_second * second[axis]
                    for axis in range(3)
                ]
            )
            for sign_first, sign_second in ((1, 1), (-1, 1), (-1, -1), (1, -1))
        ]
        neighbors = [
            sites.index(second),
            sites.index(tuple(-value for value in first)),
            sites.index(tuple(-value for value in second)),
            sites.index(first),
        ]
        cells.append(
            {
                "id": index,
                "position_3d": list(normal),
                "control_volume_vertices_3d": vertices,
                "control_volume_edge_neighbor_ids": neighbors,
                "neighbors": list(neighbors),
                "area_km2": 4.0 * math.pi * radius_km * radius_km / 6.0,
            }
        )
    return {
        "mesh_backend": "fibonacci_sphere",
        "cell_area_model": CONTROL_VOLUME_AREA_MODELS["fibonacci_sphere"],
        "planet_parameters": {"radius_km": radius_km},
        "cells": cells,
    }


class SyntheticCubeControlVolumeTests(TestCase):
    """The replay accepts an exactly known mesh and reports its true metrics."""

    def test_spherical_cube_replays_its_analytic_areas(self) -> None:
        radius_km = 6371.0
        world = _cube_control_volume_world(radius_km)

        result = inspect_control_volume_geometry(world)
        metrics = result["metrics"]

        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["failures"], [])
        self.assertEqual(metrics["cell_count"], 6)
        self.assertEqual(metrics["control_volume_vertex_count"], 24)
        self.assertEqual(metrics["control_volume_segment_count"], 12)
        self.assertEqual(metrics["control_volume_edge_pair_count"], 12)
        self.assertEqual(metrics["maximum_unit_norm_error"], 0.0)
        self.assertEqual(metrics["maximum_shared_endpoint_error"], 0.0)
        self.assertEqual(metrics["maximum_voronoi_bisector_error"], 0.0)
        self.assertEqual(metrics["maximum_nearest_site_violation"], 0.0)
        self.assertLess(metrics["maximum_area_replay_error_km2"], 1.0e-5)
        self.assertLess(metrics["surface_closure_error_km2"], 1.0e-5)
        self.assertLess(metrics["replayed_surface_closure_error_km2"], 1.0e-5)

    def test_cube_topology_matches_the_fibonacci_euler_identities(self) -> None:
        world = _cube_control_volume_world()
        metrics = inspect_control_volume_geometry(world)["metrics"]
        cell_count = metrics["cell_count"]

        self.assertEqual(
            metrics["control_volume_edge_pair_count"], 3 * cell_count - 6
        )
        self.assertEqual(
            metrics["control_volume_vertex_count"] // 3, 2 * cell_count - 4
        )


class ControlVolumeGeometryGuardTests(TestCase):
    """Backend, cell-collection, and planet-radius guards."""

    WORLD_KEY = "replay_128"

    @classmethod
    def setUpClass(cls) -> None:
        cls.control = inspect_control_volume_geometry(
            worlds.cached_world_readonly(cls.WORLD_KEY)
        )

    def setUp(self) -> None:
        self.assertTrue(self.control["passed"], self.control["failures"])

    def world(self) -> dict[str, Any]:
        return worlds.cached_world(self.WORLD_KEY)

    def assign(self, container: dict, key: str, value: Any) -> None:
        self.assertIn(key, container)
        self.assertNotEqual(
            container[key], value, f"inert tamper: {key} already holds {value!r}"
        )
        container[key] = value

    def test_generated_backends_declare_their_own_area_model(self) -> None:
        world = worlds.cached_world_readonly(self.WORLD_KEY)

        self.assertEqual(
            world["cell_area_model"],
            CONTROL_VOLUME_AREA_MODELS[world["mesh_backend"]],
        )

    def test_area_model_must_match_the_declared_backend(self) -> None:
        for label, key, value in (
            (
                "area_model_swapped",
                "cell_area_model",
                CONTROL_VOLUME_AREA_MODELS["geodesic_icosahedron"],
            ),
            ("unknown_backend", "mesh_backend", "quad_sphere"),
        ):
            with self.subTest(case=label):
                world = self.world()
                self.assign(world, key, value)

                result = inspect_control_volume_geometry(world)

                self.assertFalse(result["passed"])
                self.assertEqual(
                    result["failures"],
                    ["mesh backend and control-volume area model do not match"],
                )

    def test_absent_cells_stop_the_replay_before_any_metric(self) -> None:
        for label, mutate in (
            ("empty_list", lambda world: world.__setitem__("cells", [])),
            ("not_a_list", lambda world: world.__setitem__("cells", "cells")),
            ("key_absent", lambda world: world.pop("cells")),
        ):
            with self.subTest(case=label):
                world = self.world()
                mutate(world)

                result = inspect_control_volume_geometry(world)

                self.assertFalse(result["passed"])
                self.assertEqual(result["failures"], ["cells are missing"])
                self.assertEqual(result["metrics"], {})

    def test_planet_radius_defects_are_reported_and_never_raise(self) -> None:
        closure = "control-volume areas do not close to the spherical surface"
        for label, radius, expected in (
            ("text", "6371 km", ["planet radius is invalid", closure]),
            ("null", None, ["planet radius is invalid", closure]),
            ("not_a_number", float("nan"), ["planet radius is invalid", closure]),
            (
                "zero",
                0.0,
                [
                    "planet radius is invalid",
                    "per-cell control-volume geometry is invalid",
                ],
            ),
            ("negative", -6371.0, ["planet radius is invalid"]),
        ):
            with self.subTest(radius=label):
                world = self.world()
                self.assign(world["planet_parameters"], "radius_km", radius)

                result = inspect_control_volume_geometry(world)

                self.assertFalse(result["passed"])
                self.assertEqual(result["failures"], expected)


class ControlVolumeCellReplayTests(TestCase):
    """Per-cell field, vector, and area-replay rejections.

    Every case damages cell ``0`` so the replay aborts before recording any
    geometry: the reported failures are then exactly the per-cell verdict plus
    the surface-closure verdict that an empty replay necessarily fails.
    """

    WORLD_KEY = "replay_128"
    EXPECTED = [
        "per-cell control-volume geometry is invalid",
        "control-volume areas do not close to the spherical surface",
    ]

    @classmethod
    def setUpClass(cls) -> None:
        cls.control = inspect_control_volume_geometry(
            worlds.cached_world_readonly(cls.WORLD_KEY)
        )

    def setUp(self) -> None:
        self.assertTrue(self.control["passed"], self.control["failures"])

    def inspect_damaged(self, mutate: Callable[[dict, dict], None]) -> dict:
        world = worlds.cached_world(self.WORLD_KEY)
        mutate(world["cells"][0], world)
        result = inspect_control_volume_geometry(world)

        self.assertFalse(result["passed"])
        self.assertEqual(result["failures"], self.EXPECTED)
        self.assertEqual(result["metrics"]["cell_count"], len(world["cells"]))
        self.assertEqual(result["metrics"]["control_volume_vertex_count"], 0)
        return result

    def test_malformed_cell_fields_abort_the_replay(self) -> None:
        cases = (
            (
                "cell_not_a_mapping",
                lambda cell, world: world["cells"].__setitem__(0, "cell"),
            ),
            ("id_out_of_order", lambda cell, world: cell.__setitem__("id", 7)),
            (
                "fewer_than_three_vertices",
                lambda cell, world: cell.__setitem__(
                    "control_volume_vertices_3d",
                    cell["control_volume_vertices_3d"][:2],
                ),
            ),
            (
                "vertices_not_a_list",
                lambda cell, world: cell.__setitem__(
                    "control_volume_vertices_3d", "vertices"
                ),
            ),
            (
                "neighbors_not_a_list",
                lambda cell, world: cell.__setitem__(
                    "control_volume_edge_neighbor_ids", "neighbors"
                ),
            ),
            (
                "neighbor_count_mismatch",
                lambda cell, world: cell["control_volume_edge_neighbor_ids"].pop(),
            ),
            (
                "neighbor_id_not_numeric",
                lambda cell, world: cell[
                    "control_volume_edge_neighbor_ids"
                ].__setitem__(0, "north"),
            ),
            (
                "area_not_positive",
                lambda cell, world: cell.__setitem__("area_km2", 0.0),
            ),
            (
                "area_not_finite",
                lambda cell, world: cell.__setitem__("area_km2", float("nan")),
            ),
            (
                "position_has_two_components",
                lambda cell, world: cell.__setitem__("position_3d", [1.0, 0.0]),
            ),
            (
                "position_not_finite",
                lambda cell, world: cell.__setitem__(
                    "position_3d", [float("inf"), 0.0, 0.0]
                ),
            ),
            (
                "vertex_not_numeric",
                lambda cell, world: cell[
                    "control_volume_vertices_3d"
                ].__setitem__(0, ["north", "east", "up"]),
            ),
        )
        for label, mutate in cases:
            with self.subTest(case=label):
                self.inspect_damaged(mutate)

    def test_off_sphere_position_is_measured_before_it_is_rejected(self) -> None:
        result = self.inspect_damaged(
            lambda cell, world: cell.__setitem__("position_3d", [2.0, 0.0, 0.0])
        )

        self.assertEqual(result["metrics"]["maximum_unit_norm_error"], 1.0)

    def test_area_replay_error_is_measured_before_it_is_rejected(self) -> None:
        emitted: list[float] = []

        def double_area(cell: dict, world: dict) -> None:
            emitted.append(float(cell["area_km2"]))
            cell["area_km2"] = emitted[0] * 2.0

        result = self.inspect_damaged(double_area)

        self.assertAlmostEqual(
            result["metrics"]["maximum_area_replay_error_km2"],
            emitted[0],
            delta=0.001,
        )
        self.assertLess(result["metrics"]["maximum_unit_norm_error"], 5.0e-9)


class ControlVolumeTopologyTests(TestCase):
    """Orientation, bisector, reciprocity, and mesh-model topology verdicts."""

    WORLD_KEY = "replay_128"

    @classmethod
    def setUpClass(cls) -> None:
        cls.control = inspect_control_volume_geometry(
            worlds.cached_world_readonly(cls.WORLD_KEY)
        )
        cls.geodesic = generate_geo_world(
            worlds.build_config(
                **{
                    "mesh.backend": "geodesic_icosahedron",
                    "mesh.cell_count": 162,
                    "tectonics.plate_count": 8,
                    "erosion.iterations": 1,
                }
            )
        )
        cls.geodesic_control = inspect_control_volume_geometry(cls.geodesic)

    def setUp(self) -> None:
        self.assertTrue(self.control["passed"], self.control["failures"])
        self.assertTrue(
            self.geodesic_control["passed"], self.geodesic_control["failures"]
        )
        self.assertEqual(
            self.geodesic["mesh_backend"], "geodesic_icosahedron"
        )

    def world(self) -> dict[str, Any]:
        return worlds.cached_world(self.WORLD_KEY)

    def geodesic_world(self) -> dict[str, Any]:
        return copy.deepcopy(self.geodesic)

    def test_globally_reversed_winding_is_the_only_reported_defect(self) -> None:
        """Reversing every cell keeps areas, pairings, and endpoints intact.

        Only the winding changes, so the counter-clockwise verdict is the sole
        failure; reversing a single cell would also break its shared endpoints.
        """
        world = self.world()
        before = copy.deepcopy(world["cells"][0]["control_volume_vertices_3d"])
        for cell in world["cells"]:
            vertices = cell["control_volume_vertices_3d"]
            neighbors = cell["control_volume_edge_neighbor_ids"]
            count = len(vertices)
            cell["control_volume_vertices_3d"] = list(reversed(vertices))
            cell["control_volume_edge_neighbor_ids"] = [
                neighbors[(count - 2 - index) % count] for index in range(count)
            ]
        self.assertNotEqual(
            world["cells"][0]["control_volume_vertices_3d"], before
        )

        result = inspect_control_volume_geometry(world)

        self.assertFalse(result["passed"])
        self.assertEqual(
            result["failures"],
            ["control-volume vertices are not counter-clockwise"],
        )
        self.assertLess(result["metrics"]["maximum_shared_endpoint_error"], 5.0e-9)

    def test_displaced_site_breaks_both_fibonacci_voronoi_verdicts(self) -> None:
        """A moved site keeps every polygon but stops bisecting its edges.

        The replayed area is independent of which interior point the triangle fan
        starts from, so the cell still replays; the vertex is simply no longer
        equidistant from the two sites that share it, which is also what makes it
        fall outside its nearest-site cell.
        """
        world = self.world()
        position = list(world["cells"][0]["position_3d"])
        world["cells"][0]["position_3d"] = _unit(
            [position[0] + 1.0e-6, position[1], position[2]]
        )
        self.assertNotEqual(world["cells"][0]["position_3d"], position)

        result = inspect_control_volume_geometry(world)

        self.assertFalse(result["passed"])
        self.assertEqual(
            result["failures"],
            [
                "Fibonacci control-volume edges are not Voronoi bisectors",
                "Fibonacci control-volume vertex is outside its nearest-site cell",
            ],
        )
        self.assertGreater(
            result["metrics"]["maximum_voronoi_bisector_error"], 2.0e-9
        )
        self.assertGreater(
            result["metrics"]["maximum_nearest_site_violation"], 2.0e-9
        )
        self.assertLess(result["metrics"]["maximum_area_replay_error_km2"], 0.001)

    def test_unpaired_edge_neighbor_ids_are_rejected(self) -> None:
        for label, neighbor_id in (
            ("unknown_cell", 10_000),
            ("self_reference", 0),
        ):
            with self.subTest(case=label):
                world = self.world()
                neighbors = world["cells"][0]["control_volume_edge_neighbor_ids"]
                self.assertNotEqual(neighbors[0], neighbor_id)
                neighbors[0] = neighbor_id

                result = inspect_control_volume_geometry(world)

                self.assertFalse(result["passed"])
                self.assertEqual(
                    result["failures"],
                    [
                        "control-volume edge-neighbor topology is invalid",
                        "control-volume topology does not match its declared mesh model",
                    ],
                )

    def test_repeated_fibonacci_neighbor_breaks_topology_and_reciprocity(
        self,
    ) -> None:
        world = self.world()
        neighbors = world["cells"][0]["control_volume_edge_neighbor_ids"]
        self.assertNotEqual(neighbors[0], neighbors[1])
        neighbors[1] = neighbors[0]

        result = inspect_control_volume_geometry(world)

        self.assertFalse(result["passed"])
        self.assertEqual(
            result["failures"],
            [
                "control-volume edge-neighbor topology is invalid",
                "reciprocal control-volume edge endpoints do not match",
                "Fibonacci control-volume edges are not Voronoi bisectors",
                "control-volume topology does not match its declared mesh model",
            ],
        )

    def test_geodesic_world_replays_its_barycentric_control_volumes(self) -> None:
        metrics = self.geodesic_control["metrics"]

        self.assertEqual(self.geodesic_control["failures"], [])
        self.assertEqual(
            self.geodesic["cell_area_model"],
            CONTROL_VOLUME_AREA_MODELS["geodesic_icosahedron"],
        )
        self.assertEqual(metrics["cell_count"], len(self.geodesic["cells"]))
        self.assertLess(metrics["maximum_shared_endpoint_error"], 5.0e-9)
        self.assertEqual(metrics["maximum_voronoi_bisector_error"], 0.0)
        self.assertEqual(metrics["maximum_nearest_site_violation"], 0.0)

    def test_swapped_geodesic_edge_neighbors_break_only_reciprocity(self) -> None:
        """The dual edges keep their multiset, so only the endpoints disagree."""
        world = self.geodesic_world()
        neighbors = world["cells"][0]["control_volume_edge_neighbor_ids"]
        other = next(
            index
            for index, value in enumerate(neighbors)
            if value != neighbors[0]
        )
        neighbors[0], neighbors[other] = neighbors[other], neighbors[0]

        result = inspect_control_volume_geometry(world)

        self.assertFalse(result["passed"])
        self.assertEqual(
            result["failures"],
            ["reciprocal control-volume edge endpoints do not match"],
        )
        self.assertGreater(
            result["metrics"]["maximum_shared_endpoint_error"], 5.0e-9
        )

    def test_geodesic_dual_must_cover_each_primal_neighbor_twice(self) -> None:
        for label, mutate in (
            (
                "extra_primal_neighbor",
                lambda cell: cell.__setitem__(
                    "neighbors", list(cell["neighbors"]) + [161]
                ),
            ),
            (
                "primal_neighbor_dropped",
                lambda cell: cell.__setitem__(
                    "neighbors", list(cell["neighbors"])[:-1]
                ),
            ),
        ):
            with self.subTest(case=label):
                world = self.geodesic_world()
                before = list(world["cells"][0]["neighbors"])
                mutate(world["cells"][0])
                self.assertNotEqual(world["cells"][0]["neighbors"], before)

                result = inspect_control_volume_geometry(world)

                self.assertFalse(result["passed"])
                self.assertEqual(
                    result["failures"],
                    [
                        "control-volume topology does not match its declared mesh model"
                    ],
                )

    def test_unbalanced_geodesic_dual_edges_are_rejected(self) -> None:
        world = self.geodesic_world()
        neighbors = world["cells"][0]["control_volume_edge_neighbor_ids"]
        other = next(
            index
            for index, value in enumerate(neighbors)
            if value != neighbors[0]
        )
        neighbors[other] = neighbors[0]

        result = inspect_control_volume_geometry(world)

        self.assertFalse(result["passed"])
        self.assertEqual(
            result["failures"],
            [
                "control-volume edge-neighbor topology is invalid",
                "reciprocal control-volume edge endpoints do not match",
                "control-volume topology does not match its declared mesh model",
            ],
        )
