"""Policy, comparison, and provenance behaviour of the geo validation suite.

``tests/test_geo_validation.py`` covers the happy paths of manifest loading and
suite evaluation; this file covers the refusal and failure paths: scenarios that
violate their envelope, paired relations in the violating direction, the
determinism rerun gate, malformed manifests and target bundles, and the
stability contract of :func:`geo_fingerprint`. It also pins the report envelope
(declared scope, model limitations, member record) and the Markdown rendering of
each verdict column, which no other suite covers.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from unittest import TestCase

from magic_geo.config import WorldConfig
from magic_geo.geo_validation import (
    GEO_MODEL_LIMITATIONS,
    GEO_VALIDATION_SCOPE,
    extract_geo_metrics,
    validate_geo_world,
)
from magic_geo.geo_validation_suite import (
    SETON_SUPPLEMENTAL_TOOL,
    GeoValidationSuiteError,
    evaluate_geo_validation_suite,
    geo_fingerprint,
    load_geo_validation_manifest,
    write_geo_validation_suite_markdown,
)

from support import worlds

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = REPO_ROOT / "configs"

MATRIX_TEMPLATE = """
schema_version: 1
name: bundle fixture
scenarios:
  - id: earth
    profile: generic
    empirical_calibration:
      target_bundle: {bundle_name}
"""


def _load_manifest_text(text: str) -> dict[str, Any]:
    """Normalize ``text`` as a manifest file, as the CLI would."""
    with TemporaryDirectory() as directory:
        path = Path(directory) / "geo-validation.yaml"
        path.write_text(text, encoding="utf-8")
        return load_geo_validation_manifest(path)


def _minimal_bundle() -> dict[str, Any]:
    """A valid, self-contained empirical target bundle with one target."""
    return {
        "schema_version": 1,
        "name": "minimal_fixture_targets_v1",
        "description": "Minimal external-fit fixture.",
        "derivation": {"runtime_requires_raw_sources": False},
        "sources": {
            "fixture": {
                "dataset": "fixture dataset",
                "layer": "fixture layer",
                "source": "fixture-raw-source.bin",
            }
        },
        "targets": [
            {
                "source_id": "fixture",
                "metric": "below_sea_level_surface_fraction",
                "source_metric": "observed_ocean_fraction",
                "source_value": 0.7,
                "target_min": 0.0,
                "target_max": 1.0,
            }
        ],
    }


def _load_bundle_manifest(
    root: Path,
    bundle: Any,
    *,
    bundle_name: str = "targets.json",
) -> dict[str, Any]:
    """Write ``bundle`` plus a one-scenario matrix into ``root`` and load it."""
    payload = bundle if isinstance(bundle, str) else json.dumps(bundle)
    (root / "targets.json").write_text(payload, encoding="utf-8")
    matrix = root / "matrix.yaml"
    matrix.write_text(
        MATRIX_TEMPLATE.format(bundle_name=bundle_name), encoding="utf-8"
    )
    return load_geo_validation_manifest(matrix)


def _seton_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    """The checked-in Earth bundle plus its Seton witness, path-absolutized."""
    bundle = json.loads(
        (CONFIG_ROOT / "geo_validation_earth_empirical_targets.json").read_text(
            encoding="utf-8"
        )
    )
    for record in bundle["derivation"]["source_manifests"]:
        record["path"] = str((CONFIG_ROOT / record["path"]).resolve())
    witness = bundle["derivation"]["supplemental_target_derivations"][0]
    artifact_path = (CONFIG_ROOT / witness["path"]).resolve()
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    witness["path"] = str(artifact_path)
    return bundle, artifact


def _seton_target(bundle: dict[str, Any], metric: str) -> dict[str, Any]:
    return next(
        target for target in bundle["targets"] if target["metric"] == metric
    )


def _scenario_row(
    metrics: dict[str, Any],
    *,
    scenario_id: str,
    profile: str,
    verdict: str,
    internal: str,
    empirical: str,
    deviations: int,
    determinism: str,
) -> str:
    """The documented Markdown scenario row: column order, verdicts, precision."""
    return (
        f"| {scenario_id} | {profile} | {verdict} | {internal} | {empirical} | "
        f"{metrics['cell_count']} | "
        f"{metrics['ocean_fraction']:.3f} | "
        f"{metrics['global_mean_temperature_c']:.2f} C | "
        f"{metrics['mean_land_precipitation_mm_y']:.1f} mm/y | "
        f"{metrics['realism_evidence_coverage_fraction']:.3f} | "
        f"{metrics['calibration_pass_fraction']:.3f} | "
        f"{deviations} | {determinism} |"
    )


class GeoFingerprintTests(TestCase):
    """:func:`geo_fingerprint` must be stable, natural-only, and sensitive."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.world = worlds.cached_world_readonly("coupled_128")
        cls.digest = geo_fingerprint(cls.world)

    def test_same_world_yields_the_same_fingerprint_regardless_of_key_order(
        self,
    ) -> None:
        duplicate = deepcopy(self.world)
        reordered = {
            key: duplicate[key] for key in sorted(duplicate, reverse=True)
        }

        self.assertRegex(self.digest, r"^[0-9a-f]{64}$")
        self.assertEqual(geo_fingerprint(duplicate), self.digest)
        self.assertEqual(geo_fingerprint(reordered), self.digest)
        self.assertNotEqual(list(reordered), list(self.world))

    def test_single_changed_natural_field_changes_the_fingerprint(self) -> None:
        def bump_elevation(world: dict[str, Any]) -> None:
            world["cells"][0]["elevation_m"] = (
                float(world["cells"][0]["elevation_m"]) + 1.0
            )

        def flip_water_flag(world: dict[str, Any]) -> None:
            world["cells"][3]["is_water"] = not bool(
                world["cells"][3]["is_water"]
            )

        def retitle_world(world: dict[str, Any]) -> None:
            world["name"] = str(world["name"]) + "-variant"

        def shrink_planet(world: dict[str, Any]) -> None:
            world["planet_parameters"]["radius_km"] = (
                float(world["planet_parameters"]["radius_km"]) - 1.0
            )

        cases = (
            ("cell_elevation", bump_elevation),
            ("cell_water_flag", flip_water_flag),
            ("world_name", retitle_world),
            ("planet_radius", shrink_planet),
        )
        for name, mutate in cases:
            with self.subTest(field=name):
                mutated = deepcopy(self.world)
                mutate(mutated)
                twin = deepcopy(self.world)
                mutate(twin)

                self.assertNotEqual(mutated, self.world)
                self.assertNotEqual(geo_fingerprint(mutated), self.digest)
                self.assertEqual(geo_fingerprint(mutated), geo_fingerprint(twin))

    def test_civilization_layers_do_not_participate_in_the_fingerprint(
        self,
    ) -> None:
        mutated = worlds.cached_world("coupled_128")
        self.assertIn("settlements", mutated)
        self.assertIn("settlement_score", mutated["cells"][0])

        mutated["settlements"] = []
        mutated["political_regions"] = []
        for cell in mutated["cells"]:
            cell["settlement_score"] = -1.0
            cell["port_suitability_index"] = -1.0

        self.assertNotEqual(mutated["cells"][0], self.world["cells"][0])
        self.assertEqual(geo_fingerprint(mutated), self.digest)

    def test_nonfinite_floats_are_encoded_instead_of_breaking_json(
        self,
    ) -> None:
        finite = geo_fingerprint({"cells": [{"elevation_m": 1.0}]})
        not_a_number = geo_fingerprint(
            {"cells": [{"elevation_m": float("nan")}]}
        )
        infinite = geo_fingerprint({"cells": [{"elevation_m": float("inf")}]})
        negative_infinite = geo_fingerprint(
            {"cells": [{"elevation_m": float("-inf")}]}
        )

        self.assertEqual(
            not_a_number,
            geo_fingerprint({"cells": [{"elevation_m": float("nan")}]}),
        )
        self.assertEqual(
            len({finite, not_a_number, infinite, negative_infinite}), 4
        )
        self.assertEqual(
            infinite,
            hashlib.sha256(
                json.dumps(
                    {"cells": [{"elevation_m": {"nonfinite_float": "inf"}}]},
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        )


class GeoValidationSuiteScenarioPolicyTests(TestCase):
    """Scenario-level gates: expectations, determinism reruns, and refusals."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = worlds.canonical_config("coupled_128")
        cls.world = worlds.cached_world_readonly("coupled_128")
        cls.metrics = extract_geo_metrics(cls.world)
        cls.digest = geo_fingerprint(cls.world)

    def _stub_factory(self) -> Callable[[WorldConfig], dict[str, Any]]:
        return lambda _config: deepcopy(self.world)

    def test_violated_expectation_fails_the_scenario_with_observed_values(
        self,
    ) -> None:
        manifest = _load_manifest_text(
            """
schema_version: 1
name: envelope policy
scenarios:
  - id: in_envelope
    profile: generic
    overrides: {run: {seed: 101}}
    expectations:
      cell_count: {min: 128, max: 128}
  - id: out_of_envelope
    profile: generic
    overrides: {run: {seed: 202}}
    expectations:
      cell_count: {min: 129}
      ocean_fraction: {max: 0.0}
      unobserved_metric: {min: 0.0}
"""
        )

        report = evaluate_geo_validation_suite(
            self.config, manifest, world_factory=self._stub_factory()
        )
        members = {member["id"]: member for member in report["members"]}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            write_geo_validation_suite_markdown(path, report)
            rendered = path.read_text(encoding="utf-8")

        self.assertEqual(
            members["in_envelope"]["expectation_checks"],
            [
                {
                    "id": 0,
                    "scenario_id": "in_envelope",
                    "metric": "cell_count",
                    "passed": True,
                    "observed": 128,
                    "expected": {"min": 128.0, "max": 128.0},
                    "message": (
                        "scenario metric is within its regime-specific envelope"
                    ),
                }
            ],
        )
        self.assertTrue(members["in_envelope"]["internal_validation_passed"])
        self.assertTrue(members["in_envelope"]["passed"])

        failing = {
            check["metric"]: check
            for check in members["out_of_envelope"]["expectation_checks"]
        }
        self.assertEqual(
            sorted(failing), ["cell_count", "ocean_fraction", "unobserved_metric"]
        )
        for metric, check in failing.items():
            with self.subTest(metric=metric):
                self.assertFalse(check["passed"])
                self.assertEqual(
                    check["message"],
                    "scenario metric violates its regime-specific envelope",
                )
        self.assertEqual(failing["cell_count"]["observed"], 128)
        self.assertEqual(failing["cell_count"]["expected"], {"min": 129.0})
        self.assertEqual(
            failing["ocean_fraction"]["observed"],
            self.metrics["ocean_fraction"],
        )
        self.assertIsNone(failing["unobserved_metric"]["observed"])
        self.assertFalse(
            members["out_of_envelope"]["internal_validation_passed"]
        )
        self.assertFalse(members["out_of_envelope"]["passed"])

        self.assertFalse(report["passed"])
        self.assertEqual(report["summary"]["scenario_count"], 2)
        self.assertEqual(report["summary"]["scenario_pass_count"], 1)
        self.assertEqual(report["summary"]["scenario_pass_fraction"], 0.5)
        self.assertEqual(report["summary"]["internal_scenario_pass_count"], 1)
        self.assertFalse(report["summary"]["all_internal_scenarios_passed"])
        self.assertEqual(report["summary"]["relation_count"], 0)
        self.assertIsNone(report["summary"]["relation_pass_fraction"])
        self.assertIsNone(report["summary"]["all_relations_passed"])
        self.assertFalse(report["summary"]["response_validation_performed"])
        self.assertIsNone(
            report["summary"]["all_empirical_calibrations_passed"]
        )
        self.assertEqual(
            report["summary"]["empirical_calibration_scenario_count"], 0
        )

        # The rendered table must separate the passing row from the failing one,
        # and the failure section must exist on expectation failures alone: no
        # scenario here has a structural validation failure or a relation.
        self.assertEqual(members["in_envelope"]["metrics"], self.metrics)
        self.assertIn(
            _scenario_row(
                self.metrics,
                scenario_id="in_envelope",
                profile="generic",
                verdict="PASS",
                internal="PASS",
                empirical="not configured",
                deviations=0,
                determinism="not tested",
            ),
            rendered,
        )
        self.assertIn(
            _scenario_row(
                self.metrics,
                scenario_id="out_of_envelope",
                profile="generic",
                verdict="FAIL",
                internal="FAIL",
                empirical="not configured",
                deviations=0,
                determinism="not tested",
            ),
            rendered,
        )
        self.assertEqual(members["out_of_envelope"]["validation_failures"], [])
        self.assertIn("## Internal Validation and Response Failures", rendered)
        self.assertIn(
            "- `out_of_envelope` / `cell_count`: observed `128`, "
            "expected `{'min': 129.0}`",
            rendered,
        )
        self.assertIn(
            "- `out_of_envelope` / `ocean_fraction`: observed "
            f"`{self.metrics['ocean_fraction']}`, expected `{{'max': 0.0}}`",
            rendered,
        )
        self.assertIn(
            "- `out_of_envelope` / `unobserved_metric`: observed `None`, "
            "expected `{'min': 0.0}`",
            rendered,
        )
        self.assertNotIn("- `in_envelope`", rendered)
        self.assertNotIn("## Nonfatal Realism Deviations", rendered)
        self.assertNotIn("## External Empirical Calibration", rendered)

    def test_report_republishes_the_declared_geo_scope_and_member_record(
        self,
    ) -> None:
        manifest = _load_manifest_text(
            """
schema_version: 1
name: scope declaration
scenarios:
  - id: only
    description: '  the single scenario  '
    profile: generic
    tags: [coastal, arid]
    overrides: {run: {seed: 77}}
"""
        )

        report = evaluate_geo_validation_suite(
            self.config, manifest, world_factory=self._stub_factory()
        )
        member = report["members"][0]
        validation = validate_geo_world(self.world, profile="generic")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            write_geo_validation_suite_markdown(path, report)
            rendered = path.read_text(encoding="utf-8")

        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(
            report["report_type"], "geo_pipeline_validation_suite_v1"
        )
        self.assertEqual(report["name"], "scope declaration")
        self.assertEqual(report["scope"], GEO_VALIDATION_SCOPE)
        self.assertEqual(
            report["excluded_scope"],
            "civilization and all settlement, political, cultural, historical, "
            "demographic, economic, market, campaign, and language layers",
        )
        self.assertEqual(
            report["model_limitations"], list(GEO_MODEL_LIMITATIONS)
        )
        self.assertIn(
            "the simulation clock orders procedural stages but has no "
            "calibrated physical duration",
            report["model_limitations"],
        )

        # The member record must carry the normalized manifest entry, the
        # merged configuration, and the validation result unmodified.
        self.assertEqual(member["id"], "only")
        self.assertEqual(member["description"], "the single scenario")
        self.assertEqual(member["tags"], ["arid", "coastal"])
        self.assertEqual(member["profile"], "generic")
        self.assertEqual(member["repeat"], 1)
        self.assertEqual(member["config"]["run"]["seed"], 77)
        self.assertEqual(member["config"]["mesh"]["cell_count"], 128)
        self.assertEqual(member["validation_summary"], validation["summary"])
        self.assertEqual(member["validation_summary"]["error_failure_count"], 0)
        self.assertEqual(
            member["not_applicable_realism_checks"],
            [
                check["name"]
                for check in validation["checks"]
                if check["domain"] == "realism_evidence"
                and check["status"] == "not_applicable"
            ],
        )
        # A 128-cell world has no warm wet coastal sample, so that realism
        # check is reported as not applicable rather than as a pass.
        self.assertIn(
            "biome_realism_checks.mangrove_warm_wet_coast_constraint",
            member["not_applicable_realism_checks"],
        )

        self.assertIn(f"Scope: {GEO_VALIDATION_SCOPE}.", rendered)
        self.assertIn(
            "Excluded scope: civilization and all settlement, political, "
            "cultural, historical, demographic, economic, market, campaign, "
            "and language layers.",
            rendered,
        )
        self.assertIn("# Geo Pipeline Validation: scope declaration", rendered)
        self.assertIn("## Declared Model Limitations", rendered)
        self.assertIn(
            "- the simulation clock orders procedural stages but has no "
            "calibrated physical duration.",
            rendered,
        )
        self.assertIn("Scenarios: 1/1 passed.", rendered)
        self.assertIn("Internal geo gates: 1/1 scenarios passed.", rendered)

    def test_determinism_rerun_compares_natural_state_only(self) -> None:
        manifest = _load_manifest_text(
            """
schema_version: 1
name: determinism policy
scenarios:
  - id: stable
    profile: generic
    repeat: 3
    overrides: {run: {seed: 11}}
  - id: drifting
    profile: generic
    repeat: 2
    overrides: {run: {seed: 22}}
  - id: untested
    profile: generic
    repeat: 1
    overrides: {run: {seed: 33}}
"""
        )
        call_counts: dict[int, int] = {}

        def world_factory(config: WorldConfig) -> dict[str, Any]:
            seed = int(config.run.seed)
            index = call_counts.get(seed, 0)
            call_counts[seed] = index + 1
            world = deepcopy(self.world)
            if seed == 11 and index > 0:
                # Civilization layers must not enter the fingerprint.
                world["settlements"] = []
                world["cells"][0]["settlement_score"] = -1.0
            if seed == 22 and index > 0:
                world["cells"][0]["elevation_m"] = (
                    float(world["cells"][0]["elevation_m"]) + 1.0
                )
            return world

        report = evaluate_geo_validation_suite(
            self.config, manifest, world_factory=world_factory
        )
        members = {member["id"]: member for member in report["members"]}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            write_geo_validation_suite_markdown(path, report)
            rendered = path.read_text(encoding="utf-8")

        self.assertEqual(call_counts, {11: 3, 22: 2, 33: 1})
        self.assertTrue(members["stable"]["determinism_tested"])
        self.assertTrue(members["stable"]["deterministic"])
        self.assertEqual(
            members["stable"]["geo_fingerprint_sha256_by_repeat"],
            [self.digest] * 3,
        )
        self.assertTrue(members["stable"]["internal_validation_passed"])

        self.assertTrue(members["drifting"]["determinism_tested"])
        self.assertFalse(members["drifting"]["deterministic"])
        drifted = members["drifting"]["geo_fingerprint_sha256_by_repeat"]
        self.assertEqual(len(drifted), 2)
        self.assertEqual(drifted[0], self.digest)
        self.assertNotEqual(drifted[1], self.digest)
        self.assertEqual(
            members["drifting"]["geo_fingerprint_sha256"], self.digest
        )
        self.assertFalse(members["drifting"]["internal_validation_passed"])
        self.assertFalse(members["drifting"]["passed"])

        self.assertFalse(members["untested"]["determinism_tested"])
        self.assertIsNone(members["untested"]["deterministic"])
        self.assertEqual(
            members["untested"]["geo_fingerprint_sha256_by_repeat"],
            [self.digest],
        )
        self.assertTrue(members["untested"]["internal_validation_passed"])

        self.assertEqual(
            report["summary"]["determinism_tested_scenario_count"], 2
        )
        self.assertEqual(
            report["summary"]["deterministic_scenario_count"], 1
        )
        self.assertEqual(report["summary"]["scenario_pass_count"], 2)
        self.assertFalse(report["passed"])

        # Every repeat reports the first world's metrics, so the three rows
        # differ only in the verdict and the determinism cell.
        for scenario_id, verdict, determinism in (
            ("stable", "PASS", "PASS"),
            ("drifting", "FAIL", "FAIL"),
            ("untested", "PASS", "not tested"),
        ):
            with self.subTest(scenario=scenario_id):
                self.assertEqual(
                    members[scenario_id]["metrics"], self.metrics
                )
                self.assertIn(
                    _scenario_row(
                        self.metrics,
                        scenario_id=scenario_id,
                        profile="generic",
                        verdict=verdict,
                        internal=verdict,
                        empirical="not configured",
                        deviations=0,
                        determinism=determinism,
                    ),
                    rendered,
                )

    def test_progress_callback_runs_before_each_scenario_generation(
        self,
    ) -> None:
        manifest = _load_manifest_text(
            """
schema_version: 1
name: progress
scenarios:
  - id: first
    profile: generic
    tags: [b, a, a]
    overrides: {run: {seed: 101}}
  - id: second
    profile: earthlike
    repeat: 2
    overrides: {run: {seed: 202}}
"""
        )
        # One interleaved log, so the ordering of the two callbacks is asserted
        # rather than assumed.
        events: list[tuple[Any, ...]] = []

        def progress(index: int, total: int, scenario: dict[str, Any]) -> None:
            events.append(
                (
                    "progress",
                    index,
                    total,
                    scenario["id"],
                    scenario["profile"],
                    scenario["repeat"],
                    tuple(scenario["tags"]),
                )
            )

        def world_factory(config: WorldConfig) -> dict[str, Any]:
            events.append(("generate", int(config.run.seed)))
            return deepcopy(self.world)

        report = evaluate_geo_validation_suite(
            self.config,
            manifest,
            world_factory=world_factory,
            progress=progress,
        )

        self.assertEqual(
            events,
            [
                ("progress", 0, 2, "first", "generic", 1, ("a", "b")),
                ("generate", 101),
                ("progress", 1, 2, "second", "earthlike", 2, ()),
                ("generate", 202),
                ("generate", 202),
            ],
        )
        self.assertEqual(
            [member["profile"] for member in report["members"]],
            ["generic", "earthlike"],
        )
        self.assertEqual(
            [member["repeat"] for member in report["members"]], [1, 2]
        )

    def test_suite_refuses_manifests_that_were_not_normalized(self) -> None:
        cases = (
            (
                "raw_schema_version",
                {"schema_version": 0, "name": "x", "scenarios": [{"id": "a"}]},
                "geo validation manifest was not loaded or normalized",
            ),
            (
                "missing_scenarios",
                {"schema_version": 1, "name": "x"},
                "geo validation manifest has no scenarios",
            ),
            (
                "empty_scenarios",
                {"schema_version": 1, "name": "x", "scenarios": []},
                "geo validation manifest has no scenarios",
            ),
        )
        for name, manifest, expected in cases:
            with self.subTest(case=name):
                with self.assertRaisesRegex(
                    GeoValidationSuiteError, expected
                ):
                    evaluate_geo_validation_suite(
                        self.config,
                        manifest,
                        world_factory=self._stub_factory(),
                    )

    def test_scenario_setup_failures_are_reported_per_scenario(self) -> None:
        def manifest_for(overrides: str) -> dict[str, Any]:
            return _load_manifest_text(
                "schema_version: 1\n"
                "name: setup failures\n"
                "scenarios:\n"
                "  - id: subject\n"
                f"    overrides: {overrides}\n"
            )

        cases = (
            (
                "include_cells_disabled",
                "{output: {include_cells: false}}",
                (
                    r"scenario 'subject' must keep output\.include_cells=true "
                    r"for deep validation"
                ),
            ),
            (
                "invalid_config_value",
                "{planet: {radius_km: 50.0}}",
                r"scenario 'subject' config is invalid: "
                r"1 validation error for WorldConfig",
            ),
            (
                "override_expects_object",
                "{planet: 5}",
                r"config override 'planet' must be an object",
            ),
            (
                "override_rejects_object",
                "{run: {seed: {value: 7}}}",
                r"config override 'run\.seed' cannot be an object",
            ),
        )
        for name, overrides, expected in cases:
            with self.subTest(case=name):
                with self.assertRaisesRegex(
                    GeoValidationSuiteError, expected
                ):
                    evaluate_geo_validation_suite(
                        manifest=manifest_for(overrides),
                        base_config=self.config,
                        world_factory=self._stub_factory(),
                    )

    def test_generation_runtime_error_names_the_failing_scenario(self) -> None:
        manifest = _load_manifest_text(
            """
schema_version: 1
name: generation failure
scenarios:
  - id: boom
    profile: generic
"""
        )

        def world_factory(_config: WorldConfig) -> dict[str, Any]:
            raise RuntimeError("native core refused the mesh")

        with self.assertRaisesRegex(
            GeoValidationSuiteError,
            r"scenario 'boom' generation failed: native core refused the mesh",
        ):
            evaluate_geo_validation_suite(
                self.config, manifest, world_factory=world_factory
            )

    def test_nonfatal_realism_deviation_does_not_fail_the_scenario(
        self,
    ) -> None:
        deviated = deepcopy(self.world)
        record = deviated["planet_realism_checks"][0]
        self.assertEqual(record["name"], "liquid_water_temperature_window")
        record["value"] = 0.2
        record["score"] = 0.0
        record["passed"] = False
        deviated["summary"]["planet_realism_pass_count"] = 3
        deviated["summary"]["planet_realism_pass_fraction"] = 0.75
        deviated["summary"]["mean_planet_realism_score"] = 0.75

        manifest = _load_manifest_text(
            """
schema_version: 1
name: nonfatal deviations
scenarios:
  - id: deviating
    profile: generic
"""
        )
        report = evaluate_geo_validation_suite(
            self.config,
            manifest,
            world_factory=lambda _config: deepcopy(deviated),
        )
        member = report["members"][0]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.md"
            write_geo_validation_suite_markdown(path, report)
            rendered = path.read_text(encoding="utf-8")

        self.assertEqual(member["validation_failures"], [])
        self.assertEqual(len(member["realism_deviations"]), 1)
        deviation = member["realism_deviations"][0]
        self.assertEqual(
            deviation["name"],
            "planet_realism_checks.liquid_water_temperature_window",
        )
        self.assertEqual(deviation["severity"], "warning")
        self.assertEqual(deviation["observed"], 0.2)
        self.assertEqual(
            deviation["expected"], {"target_min": 0.55, "target_max": 1.0}
        )
        self.assertTrue(member["internal_validation_passed"])
        self.assertTrue(member["passed"])
        self.assertTrue(report["passed"])
        self.assertIn("Overall verdict: **PASS**", rendered)
        self.assertIn(
            _scenario_row(
                member["metrics"],
                scenario_id="deviating",
                profile="generic",
                verdict="PASS",
                internal="PASS",
                empirical="not configured",
                deviations=1,
                determinism="not tested",
            ),
            rendered,
        )
        self.assertIn("Paired response gates: not run.", rendered)
        self.assertIn("## Nonfatal Realism Deviations", rendered)
        self.assertIn(
            "- `deviating` / "
            "`planet_realism_checks.liquid_water_temperature_window`: "
            "observed `0.2`, expected "
            "`{'target_min': 0.55, 'target_max': 1.0}`",
            rendered,
        )
        self.assertNotIn(
            "## Internal Validation and Response Failures", rendered
        )

    def test_calibration_failure_is_raised_against_the_scenario(self) -> None:
        broken = deepcopy(self.world)
        self.assertIn("initial_oceanic_crust_age_ledger", broken)
        broken["initial_oceanic_crust_age_ledger"][
            "area_weighted_cdf_le_threshold"
        ][1] += 0.01

        with TemporaryDirectory() as directory:
            manifest = _load_bundle_manifest(
                Path(directory), _minimal_bundle()
            )
            with self.assertRaisesRegex(
                GeoValidationSuiteError,
                r"scenario 'earth' external empirical calibration failed: "
                r"world initial oceanic crust age ledger summaries conflict "
                r"with cell-derived values$",
            ):
                evaluate_geo_validation_suite(
                    self.config,
                    manifest,
                    world_factory=lambda _config: deepcopy(broken),
                )


class GeoValidationSuiteRelationTests(TestCase):
    """Paired-response relations in the passing and the violating direction."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = worlds.canonical_config("coupled_128")
        cls.cool = worlds.cached_world_readonly("coupled_128")
        warm = deepcopy(cls.cool)
        for cell in warm["cells"]:
            cell["temperature_c"] = float(cell["temperature_c"]) + 4.0
        cls.warm = warm
        cls.cool_temperature = extract_geo_metrics(cls.cool)[
            "global_mean_temperature_c"
        ]
        cls.warm_temperature = extract_geo_metrics(cls.warm)[
            "global_mean_temperature_c"
        ]

    def _world_factory(self, config: WorldConfig) -> dict[str, Any]:
        return deepcopy(self.warm if int(config.run.seed) == 202 else self.cool)

    def test_relations_are_directional_and_honour_minimum_difference(
        self,
    ) -> None:
        self.assertAlmostEqual(
            self.warm_temperature - self.cool_temperature, 4.0, places=5
        )
        manifest = _load_manifest_text(
            """
schema_version: 1
name: paired responses
scenarios:
  - id: cooler
    profile: generic
    overrides: {run: {seed: 101}}
  - id: warmer
    profile: generic
    overrides: {run: {seed: 202}}
relations:
  - id: warmer_gt_cooler
    left: warmer
    right: cooler
    metric: global_mean_temperature_c
    operator: gt
    minimum_difference: 3.0
  - id: cooler_gt_warmer
    left: cooler
    right: warmer
    metric: global_mean_temperature_c
    operator: gt
  - id: warmer_gt_cooler_by_six
    left: warmer
    right: cooler
    metric: global_mean_temperature_c
    operator: gt
    minimum_difference: 6.0
  - id: cooler_lt_warmer
    left: cooler
    right: warmer
    metric: global_mean_temperature_c
    operator: lt
    minimum_difference: 3.0
  - id: warmer_lt_cooler
    left: warmer
    right: cooler
    metric: global_mean_temperature_c
    operator: lt
  - id: warmer_ge_cooler
    left: warmer
    right: cooler
    metric: global_mean_temperature_c
    operator: ge
    minimum_difference: 3.0
  - id: cooler_le_warmer
    left: cooler
    right: warmer
    metric: global_mean_temperature_c
    operator: le
    minimum_difference: 3.0
  - id: cooler_lt_warmer_by_six
    left: cooler
    right: warmer
    metric: global_mean_temperature_c
    operator: lt
    minimum_difference: 6.0
  - id: cooler_le_warmer_by_six
    left: cooler
    right: warmer
    metric: global_mean_temperature_c
    operator: le
    minimum_difference: 6.0
  - id: warmer_ge_cooler_by_six
    left: warmer
    right: cooler
    metric: global_mean_temperature_c
    operator: ge
    minimum_difference: 6.0
  - id: eq_within_wide_tolerance
    left: warmer
    right: cooler
    metric: global_mean_temperature_c
    operator: eq
    tolerance: 10.0
  - id: eq_within_tight_tolerance
    left: warmer
    right: cooler
    metric: global_mean_temperature_c
    operator: eq
    tolerance: 0.5
  - id: unobserved_metric_relation
    left: warmer
    right: cooler
    metric: unobserved_metric
    operator: gt
"""
        )

        report = evaluate_geo_validation_suite(
            self.config, manifest, world_factory=self._world_factory
        )
        relations = {
            relation["id"]: relation for relation in report["relations"]
        }

        self.assertEqual(
            {
                relation_id: relation["passed"]
                for relation_id, relation in relations.items()
            },
            {
                "warmer_gt_cooler": True,
                "cooler_gt_warmer": False,
                "warmer_gt_cooler_by_six": False,
                "cooler_lt_warmer": True,
                "warmer_lt_cooler": False,
                "warmer_ge_cooler": True,
                "cooler_le_warmer": True,
                "cooler_lt_warmer_by_six": False,
                "cooler_le_warmer_by_six": False,
                "warmer_ge_cooler_by_six": False,
                "eq_within_wide_tolerance": True,
                "eq_within_tight_tolerance": False,
                "unobserved_metric_relation": False,
            },
        )
        self.assertEqual(
            relations["warmer_gt_cooler"]["left_value"], self.warm_temperature
        )
        self.assertEqual(
            relations["warmer_gt_cooler"]["right_value"], self.cool_temperature
        )
        self.assertEqual(
            relations["warmer_gt_cooler"]["difference"],
            self.warm_temperature - self.cool_temperature,
        )
        self.assertEqual(
            relations["warmer_gt_cooler"]["message"],
            "paired scenario response is coherent",
        )
        self.assertEqual(
            relations["cooler_gt_warmer"]["difference"],
            self.cool_temperature - self.warm_temperature,
        )
        self.assertEqual(
            relations["cooler_gt_warmer"]["message"],
            "paired scenario response is missing or incoherent",
        )
        self.assertIsNone(
            relations["unobserved_metric_relation"]["left_value"]
        )
        self.assertIsNone(
            relations["unobserved_metric_relation"]["right_value"]
        )
        self.assertIsNone(relations["unobserved_metric_relation"]["difference"])

        self.assertFalse(report["passed"])
        self.assertEqual(report["summary"]["relation_count"], 13)
        self.assertEqual(report["summary"]["relation_pass_count"], 5)
        self.assertEqual(
            report["summary"]["relation_pass_fraction"], 0.384615
        )
        self.assertTrue(report["summary"]["response_validation_performed"])
        self.assertFalse(report["summary"]["all_relations_passed"])

    def test_failed_relation_alone_fails_the_whole_report(self) -> None:
        manifest = _load_manifest_text(
            """
schema_version: 1
name: relation gate
scenarios:
  - id: left_twin
    profile: generic
    overrides: {run: {seed: 101}}
  - id: right_twin
    profile: generic
    overrides: {run: {seed: 303}}
relations:
  - id: twins_differ
    left: left_twin
    right: right_twin
    metric: global_mean_temperature_c
    operator: gt
    minimum_difference: 1.0
"""
        )

        # Both scenarios generate the same world, so every scenario gate passes
        # and only the paired relation can fail the report.
        report = evaluate_geo_validation_suite(
            self.config,
            manifest,
            world_factory=lambda _config: deepcopy(self.cool),
        )
        members = {member["id"]: member for member in report["members"]}
        relation = report["relations"][0]

        self.assertTrue(members["left_twin"]["passed"])
        self.assertTrue(members["right_twin"]["passed"])
        self.assertEqual(report["summary"]["scenario_pass_count"], 2)
        self.assertTrue(report["summary"]["all_scenarios_passed"])
        self.assertTrue(report["summary"]["all_internal_scenarios_passed"])
        self.assertFalse(relation["passed"])
        self.assertEqual(relation["left_value"], self.cool_temperature)
        self.assertEqual(relation["difference"], 0.0)
        self.assertEqual(report["summary"]["relation_pass_count"], 0)
        self.assertFalse(report["summary"]["all_relations_passed"])
        self.assertFalse(report["passed"])

    def test_markdown_report_lists_failed_relations_and_expectations(
        self,
    ) -> None:
        manifest = _load_manifest_text(
            """
schema_version: 1
name: rendered failures
scenarios:
  - id: cooler
    profile: generic
    overrides: {run: {seed: 101}}
    expectations:
      global_mean_temperature_c: {min: 90.0}
  - id: warmer
    profile: generic
    overrides: {run: {seed: 202}}
relations:
  - id: cooler_gt_warmer
    left: cooler
    right: warmer
    metric: global_mean_temperature_c
    operator: gt
    minimum_difference: 2.0
"""
        )

        report = evaluate_geo_validation_suite(
            self.config, manifest, world_factory=self._world_factory
        )
        members = {member["id"]: member for member in report["members"]}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "report.md"
            write_geo_validation_suite_markdown(path, report)
            rendered = path.read_text(encoding="utf-8")

        difference = self.cool_temperature - self.warm_temperature
        self.assertIn("Overall verdict: **FAIL**", rendered)
        self.assertIn("Paired response gates: 0/1 passed.", rendered)
        self.assertIn("External empirical calibration: not configured.", rendered)
        self.assertIn(
            "| cooler_gt_warmer | global_mean_temperature_c | "
            f"cooler gt warmer | {difference:.6f} | FAIL |",
            rendered,
        )
        self.assertIn(
            "## Internal Validation and Response Failures", rendered
        )
        self.assertIn(
            "- `cooler` / `global_mean_temperature_c`: observed "
            f"`{self.cool_temperature}`, expected `{{'min': 90.0}}`",
            rendered,
        )
        self.assertIn(
            "- `cooler_gt_warmer`: "
            f"`{self.cool_temperature}` gt `{self.warm_temperature}` "
            "with minimum difference `2.0`",
            rendered,
        )
        self.assertNotIn("## External Empirical Calibration Failures", rendered)

        # Shifting every cell by +4 C without re-running the climate model
        # breaks the configured temperature response, so the same section must
        # also carry the structural failure of the `warmer` scenario.
        temperature_failure = next(
            failure
            for failure in members["warmer"]["validation_failures"]
            if failure["name"] == "configured_global_temperature_response"
        )
        self.assertEqual(temperature_failure["severity"], "error")
        self.assertEqual(temperature_failure["domain"], "climate")
        self.assertFalse(members["warmer"]["internal_validation_passed"])
        # Error-severity failures must not also be reported as nonfatal
        # realism deviations.
        self.assertEqual(members["warmer"]["realism_deviations"], [])
        self.assertNotIn("## Nonfatal Realism Deviations", rendered)
        self.assertIn(
            "- `warmer` / `climate.configured_global_temperature_response`: "
            f"{temperature_failure['message']}",
            rendered,
        )


class GeoValidationManifestInputTests(TestCase):
    """Malformed and partial matrix input must be refused with a reason."""

    def test_manifest_loading_rejects_malformed_documents(self) -> None:
        crowded = "schema_version: 1\nname: too many\nscenarios: [" + ", ".join(
            "{id: s%d}" % index for index in range(65)
        ) + "]\n"
        cases = (
            (
                "unparsable_yaml",
                "name: [unclosed\n",
                r"invalid geo validation manifest",
            ),
            (
                "root_not_object",
                "- one\n- two\n",
                r"geo validation manifest root must be an object",
            ),
            (
                "unknown_root_field",
                "schema_version: 1\nname: m\nscenarios: [{id: a}]\nextra: 1\n",
                r"geo validation manifest has unknown fields: extra",
            ),
            (
                "wrong_schema_version",
                "schema_version: 2\nname: m\nscenarios: [{id: a}]\n",
                r"geo validation manifest schema_version must be 1",
            ),
            (
                "blank_name",
                "schema_version: 1\nname: '   '\nscenarios: [{id: a}]\n",
                r"geo validation manifest name must be a non-empty string",
            ),
            (
                "scenarios_not_a_list",
                "schema_version: 1\nname: m\nscenarios: 5\n",
                r"requires a non-empty scenarios list",
            ),
            (
                "no_scenarios",
                "schema_version: 1\nname: m\nscenarios: []\n",
                r"requires a non-empty scenarios list",
            ),
            (
                "too_many_scenarios",
                crowded,
                r"cannot exceed 64 scenarios",
            ),
            (
                "scenario_not_an_object",
                "schema_version: 1\nname: m\nscenarios: ['a']\n",
                r"geo validation scenario 0 must be an object",
            ),
            (
                "scenario_unknown_field",
                "schema_version: 1\nname: m\nscenarios: [{id: a, spelling: x}]\n",
                r"geo validation scenario 0 has unknown fields: spelling",
            ),
            (
                "scenario_missing_id",
                "schema_version: 1\nname: m\nscenarios: [{profile: generic}]\n",
                r"geo validation scenario 0 id must be a non-empty string",
            ),
            (
                "duplicate_scenario_id",
                "schema_version: 1\nname: m\nscenarios: [{id: a}, {id: a}]\n",
                r"duplicates scenario id 'a'",
            ),
            (
                "unknown_profile",
                "schema_version: 1\nname: m\nscenarios: [{id: a, profile: tropical}]\n",
                r"geo validation scenario 0 profile must be generic or earthlike",
            ),
            (
                "overrides_not_an_object",
                "schema_version: 1\nname: m\nscenarios: [{id: a, overrides: 5}]\n",
                r"geo validation scenario 0 overrides must be an object",
            ),
            (
                "repeat_out_of_range",
                "schema_version: 1\nname: m\nscenarios: [{id: a, repeat: 4}]\n",
                r"geo validation scenario 0 repeat must be an integer from 1 to 3",
            ),
            (
                "repeat_is_boolean",
                "schema_version: 1\nname: m\nscenarios: [{id: a, repeat: true}]\n",
                r"geo validation scenario 0 repeat must be an integer from 1 to 3",
            ),
            (
                "tags_not_a_list",
                "schema_version: 1\nname: m\nscenarios: [{id: a, tags: coastal}]\n",
                r"geo validation scenario 0 tags must be a list",
            ),
            (
                "blank_tag",
                "schema_version: 1\nname: m\nscenarios: [{id: a, tags: ['']}]\n",
                r"geo validation scenario 0 tag must be a non-empty string",
            ),
            (
                "expectations_not_an_object",
                "schema_version: 1\nname: m\nscenarios: [{id: a, expectations: 5}]\n",
                r"geo validation scenario 0 expectations must be an object",
            ),
            (
                "expectation_bounds_not_an_object",
                "schema_version: 1\nname: m\n"
                "scenarios: [{id: a, expectations: {ocean_fraction: 0.5}}]\n",
                r"expectation 'ocean_fraction' must define min and/or max",
            ),
            (
                "expectation_bounds_empty",
                "schema_version: 1\nname: m\n"
                "scenarios: [{id: a, expectations: {ocean_fraction: {}}}]\n",
                r"expectation 'ocean_fraction' must define min and/or max",
            ),
            (
                "expectation_unknown_bound",
                "schema_version: 1\nname: m\n"
                "scenarios: [{id: a, expectations: {ocean_fraction: {mid: 1, top: 2}}}]\n",
                r"expectation 'ocean_fraction' has unknown bounds: mid, top",
            ),
            (
                "expectation_metric_not_text",
                "schema_version: 1\nname: m\n"
                "scenarios: [{id: a, expectations: {5: {min: 1}}}]\n",
                r"geo validation scenario 0 expectation metric must be a "
                r"non-empty string",
            ),
            (
                "expectation_range_inverted",
                "schema_version: 1\nname: m\n"
                "scenarios: [{id: a, expectations: {ocean_fraction: {min: 2, max: 1}}}]\n",
                r"expectation 'ocean_fraction' range is inverted",
            ),
            (
                "expectation_bound_not_finite",
                "schema_version: 1\nname: m\n"
                "scenarios: [{id: a, expectations: {ocean_fraction: {min: .inf}}}]\n",
                r"expectation 'ocean_fraction' min must be a finite number",
            ),
            (
                "expectation_bound_is_boolean",
                "schema_version: 1\nname: m\n"
                "scenarios: [{id: a, expectations: {ocean_fraction: {max: true}}}]\n",
                r"expectation 'ocean_fraction' max must be a finite number",
            ),
            (
                "expectation_bound_not_numeric",
                "schema_version: 1\nname: m\n"
                "scenarios: [{id: a, expectations: {ocean_fraction: {min: high}}}]\n",
                r"expectation 'ocean_fraction' min must be a finite number",
            ),
            (
                "empirical_calibration_not_an_object",
                "schema_version: 1\nname: m\n"
                "scenarios: [{id: a, empirical_calibration: 5}]\n",
                r"empirical_calibration must be an object",
            ),
            (
                "empirical_calibration_unknown_field",
                "schema_version: 1\nname: m\n"
                "scenarios: [{id: a, empirical_calibration: {target_bundle: t.json, "
                "require_everything: true}}]\n",
                r"empirical_calibration has unknown fields: require_everything",
            ),
            (
                "empirical_calibration_missing_bundle",
                "schema_version: 1\nname: m\n"
                "scenarios: [{id: a, empirical_calibration: {}}]\n",
                r"empirical_calibration target_bundle must be a non-empty string",
            ),
            (
                "relations_not_a_list",
                "schema_version: 1\nname: m\nscenarios: [{id: a}]\nrelations: 5\n",
                r"geo validation manifest relations must be a list",
            ),
            (
                "relation_not_an_object",
                "schema_version: 1\nname: m\nscenarios: [{id: a}]\nrelations: ['x']\n",
                r"geo validation relation 0 must be an object",
            ),
            (
                "relation_unknown_field",
                "schema_version: 1\nname: m\nscenarios: [{id: a}, {id: b}]\n"
                "relations: [{id: r, left: a, right: b, metric: m, operator: gt, "
                "opperator: gt}]\n",
                r"geo validation relation 0 has unknown fields: opperator",
            ),
            (
                "duplicate_relation_id",
                "schema_version: 1\nname: m\nscenarios: [{id: a}, {id: b}]\n"
                "relations: [{id: r, left: a, right: b, metric: m, operator: gt}, "
                "{id: r, left: b, right: a, metric: m, operator: gt}]\n",
                r"duplicates relation id 'r'",
            ),
            (
                "relation_unknown_scenario",
                "schema_version: 1\nname: m\nscenarios: [{id: a}, {id: b}]\n"
                "relations: [{id: r, left: a, right: ghost, metric: m, operator: gt}]\n",
                r"geo validation relation 0 references an unknown scenario",
            ),
            (
                "relation_self_comparison",
                "schema_version: 1\nname: m\nscenarios: [{id: a}, {id: b}]\n"
                "relations: [{id: r, left: a, right: a, metric: m, operator: gt}]\n",
                r"geo validation relation 0 must compare two different scenarios",
            ),
            (
                "relation_unknown_operator",
                "schema_version: 1\nname: m\nscenarios: [{id: a}, {id: b}]\n"
                "relations: [{id: r, left: a, right: b, metric: m, operator: ne}]\n",
                r"geo validation relation 0 operator must be one of "
                r"eq, ge, gt, le, lt",
            ),
            (
                "relation_negative_minimum_difference",
                "schema_version: 1\nname: m\nscenarios: [{id: a}, {id: b}]\n"
                "relations: [{id: r, left: a, right: b, metric: m, operator: gt, "
                "minimum_difference: -1.0}]\n",
                r"geo validation relation 0 minimum_difference must be non-negative",
            ),
            (
                "relation_minimum_difference_not_numeric",
                "schema_version: 1\nname: m\nscenarios: [{id: a}, {id: b}]\n"
                "relations: [{id: r, left: a, right: b, metric: m, operator: gt, "
                "minimum_difference: wide}]\n",
                r"geo validation relation 0 minimum_difference must be a finite number",
            ),
            (
                "relation_equality_with_minimum_difference",
                "schema_version: 1\nname: m\nscenarios: [{id: a}, {id: b}]\n"
                "relations: [{id: r, left: a, right: b, metric: m, operator: eq, "
                "minimum_difference: 1.0}]\n",
                r"geo validation relation 0 equality relations require "
                r"minimum_difference=0",
            ),
            (
                "relation_negative_tolerance",
                "schema_version: 1\nname: m\nscenarios: [{id: a}, {id: b}]\n"
                "relations: [{id: r, left: a, right: b, metric: m, operator: gt, "
                "tolerance: -1.0}]\n",
                r"geo validation relation 0 tolerance must be non-negative",
            ),
            (
                "relation_tolerance_not_finite",
                "schema_version: 1\nname: m\nscenarios: [{id: a}, {id: b}]\n"
                "relations: [{id: r, left: a, right: b, metric: m, operator: gt, "
                "tolerance: .inf}]\n",
                r"geo validation relation 0 tolerance must be a finite number",
            ),
        )
        for name, text, expected in cases:
            with self.subTest(case=name):
                with self.assertRaisesRegex(
                    GeoValidationSuiteError, expected
                ):
                    _load_manifest_text(text)

    def test_manifest_file_that_cannot_be_read_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.yaml"
            with self.assertRaisesRegex(
                GeoValidationSuiteError,
                r"invalid geo validation manifest: .*absent\.yaml",
            ):
                load_geo_validation_manifest(missing)

    def test_normalized_manifest_defaults_and_ordering_are_explicit(
        self,
    ) -> None:
        manifest = _load_manifest_text(
            """
schema_version: 1
name: defaults
scenarios:
  - id: only
    description: '  spaced description  '
    tags: [zulu, alpha, alpha]
relations: []
"""
        )
        scenario = manifest["scenarios"][0]

        self.assertEqual(manifest["name"], "defaults")
        self.assertEqual(manifest["relations"], [])
        self.assertEqual(scenario["description"], "spaced description")
        self.assertEqual(scenario["profile"], "generic")
        self.assertEqual(scenario["repeat"], 1)
        self.assertEqual(scenario["tags"], ["alpha", "zulu"])
        self.assertEqual(scenario["overrides"], {})
        self.assertEqual(scenario["expectations"], {})
        self.assertIsNone(scenario["empirical_calibration"])


class EmpiricalTargetBundleInputTests(TestCase):
    """Target bundles and their derivation witnesses are validated fail-closed."""

    def test_bundle_documents_are_validated_field_by_field(self) -> None:
        def unknown_root(bundle: dict[str, Any]) -> None:
            bundle["extra"] = 1

        def wrong_schema(bundle: dict[str, Any]) -> None:
            bundle["schema_version"] = 2

        def blank_name(bundle: dict[str, Any]) -> None:
            bundle["name"] = "  "

        def derivation_not_object(bundle: dict[str, Any]) -> None:
            bundle["derivation"] = "derived by hand"

        def no_sources(bundle: dict[str, Any]) -> None:
            bundle["sources"] = {}

        def source_not_object(bundle: dict[str, Any]) -> None:
            bundle["sources"]["fixture"] = 5

        def source_unknown_field(bundle: dict[str, Any]) -> None:
            bundle["sources"]["fixture"]["dataset_name"] = "fixture"

        def source_missing_dataset(bundle: dict[str, Any]) -> None:
            bundle["sources"]["fixture"].pop("dataset")

        def source_blank_optional(bundle: dict[str, Any]) -> None:
            bundle["sources"]["fixture"]["source_version"] = ""

        def source_bad_digest(bundle: dict[str, Any]) -> None:
            bundle["sources"]["fixture"]["source_sha256"] = "abc123"

        def no_targets(bundle: dict[str, Any]) -> None:
            bundle["targets"] = []

        def target_not_object(bundle: dict[str, Any]) -> None:
            bundle["targets"] = [5]

        def target_unknown_field(bundle: dict[str, Any]) -> None:
            bundle["targets"][0]["metrics"] = "ocean"

        def target_unknown_source(bundle: dict[str, Any]) -> None:
            bundle["targets"][0]["source_id"] = "other"

        def duplicate_metric(bundle: dict[str, Any]) -> None:
            bundle["targets"].append(deepcopy(bundle["targets"][0]))

        def inverted_range(bundle: dict[str, Any]) -> None:
            bundle["targets"][0]["target_min"] = 1.0
            bundle["targets"][0]["target_max"] = 0.0

        def source_value_not_numeric(bundle: dict[str, Any]) -> None:
            bundle["targets"][0]["source_value"] = "seven tenths"

        def sample_count_not_numeric(bundle: dict[str, Any]) -> None:
            bundle["targets"][0]["source_sample_cell_count"] = "many"

        def tolerance_basis_not_text(bundle: dict[str, Any]) -> None:
            bundle["targets"][0]["tolerance_basis"] = 5

        cases = (
            ("unknown_root_field", unknown_root, r"target bundle has unknown fields: extra"),
            ("wrong_schema_version", wrong_schema, r"target bundle schema_version must be 1"),
            ("blank_name", blank_name, r"target bundle name must be a non-empty string"),
            (
                "derivation_not_object",
                derivation_not_object,
                r"target bundle derivation must be an object",
            ),
            ("no_sources", no_sources, r"target bundle requires non-empty sources"),
            ("source_not_object", source_not_object, r"source 'fixture' must be an object"),
            (
                "source_unknown_field",
                source_unknown_field,
                r"source 'fixture' has unknown fields: dataset_name",
            ),
            (
                "source_missing_dataset",
                source_missing_dataset,
                r"source 'fixture' dataset must be a non-empty string",
            ),
            (
                "source_blank_optional_field",
                source_blank_optional,
                r"source 'fixture' source_version must be a non-empty string",
            ),
            (
                "source_bad_digest",
                source_bad_digest,
                r"source 'fixture' source_sha256 must be a SHA-256 digest",
            ),
            ("no_targets", no_targets, r"target bundle requires non-empty targets"),
            ("target_not_object", target_not_object, r"target 0 must be an object"),
            (
                "target_unknown_field",
                target_unknown_field,
                r"target 0 has unknown fields: metrics",
            ),
            (
                "target_unknown_source",
                target_unknown_source,
                r"target 0 references unknown source 'other'",
            ),
            (
                "duplicate_metric",
                duplicate_metric,
                r"duplicates world metric 'below_sea_level_surface_fraction'",
            ),
            ("inverted_range", inverted_range, r"target 0 range is inverted"),
            (
                "source_value_not_numeric",
                source_value_not_numeric,
                r"target 0 source_value must be a finite number",
            ),
            (
                "sample_count_not_numeric",
                sample_count_not_numeric,
                r"target 0 source_sample_cell_count must be a finite number",
            ),
            (
                "tolerance_basis_not_text",
                tolerance_basis_not_text,
                r"target 0 tolerance_basis must be a non-empty string",
            ),
        )
        for name, mutate, expected in cases:
            with self.subTest(case=name), TemporaryDirectory() as directory:
                bundle = _minimal_bundle()
                mutate(bundle)
                with self.assertRaisesRegex(
                    GeoValidationSuiteError, expected
                ):
                    _load_bundle_manifest(Path(directory), bundle)

    def test_unreadable_or_non_object_bundles_are_refused(self) -> None:
        cases = (
            ("not_json", "{", "targets.json", r"target bundle is invalid: .*targets\.json"),
            (
                "root_is_a_list",
                "[]",
                "targets.json",
                r"target bundle root must be an object",
            ),
            (
                "missing_file",
                json.dumps(_minimal_bundle()),
                "absent.json",
                r"target bundle is invalid: .*absent\.json",
            ),
        )
        for name, payload, bundle_name, expected in cases:
            with self.subTest(case=name), TemporaryDirectory() as directory:
                with self.assertRaisesRegex(
                    GeoValidationSuiteError, expected
                ):
                    _load_bundle_manifest(
                        Path(directory), payload, bundle_name=bundle_name
                    )

    def test_derivation_witness_records_are_validated_and_hashed(self) -> None:
        def digest_of(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        def not_a_bool(bundle: dict[str, Any], witness: Path) -> None:
            bundle["derivation"]["runtime_requires_raw_sources"] = 1

        def tool_not_text(bundle: dict[str, Any], witness: Path) -> None:
            bundle["derivation"]["tool"] = 5

        def empty_records(bundle: dict[str, Any], witness: Path) -> None:
            bundle["derivation"]["source_manifests"] = []

        def record_field_mismatch(bundle: dict[str, Any], witness: Path) -> None:
            bundle["derivation"]["source_manifests"] = [
                {"path": witness.name}
            ]

        def duplicate_paths(bundle: dict[str, Any], witness: Path) -> None:
            bundle["derivation"]["source_manifests"] = [
                {"path": witness.name, "sha256": digest_of(witness)},
                {"path": witness.name, "sha256": digest_of(witness)},
            ]

        def bad_digest(bundle: dict[str, Any], witness: Path) -> None:
            bundle["derivation"]["source_manifests"] = [
                {"path": witness.name, "sha256": "not-a-digest"}
            ]

        def missing_artifact(bundle: dict[str, Any], witness: Path) -> None:
            bundle["derivation"]["source_manifests"] = [
                {"path": "absent-witness.json", "sha256": digest_of(witness)}
            ]

        def supplemental_missing_tool(
            bundle: dict[str, Any], witness: Path
        ) -> None:
            bundle["derivation"]["supplemental_target_derivations"] = [
                {"path": witness.name, "sha256": digest_of(witness)}
            ]

        def supplemental_blank_tool(
            bundle: dict[str, Any], witness: Path
        ) -> None:
            bundle["derivation"]["supplemental_target_derivations"] = [
                {
                    "path": witness.name,
                    "sha256": digest_of(witness),
                    "tool": "  ",
                }
            ]

        def seton_metric_without_source(
            bundle: dict[str, Any], witness: Path
        ) -> None:
            bundle["targets"][0]["metric"] = (
                "initial_oceanic_crust_age_area_weighted_mean_ma"
            )

        def seton_source_without_witness(
            bundle: dict[str, Any], witness: Path
        ) -> None:
            bundle["sources"]["seton_2020_oceanic_age"] = bundle["sources"].pop(
                "fixture"
            )
            bundle["targets"][0]["source_id"] = "seton_2020_oceanic_age"

        cases = (
            (
                "runtime_flag_not_boolean",
                not_a_bool,
                r"derivation runtime_requires_raw_sources must be a boolean",
            ),
            ("tool_not_text", tool_not_text, r"derivation tool must be a non-empty string"),
            (
                "empty_record_list",
                empty_records,
                r"derivation source_manifests must be a non-empty array",
            ),
            (
                "record_field_mismatch",
                record_field_mismatch,
                r"derivation source_manifests\[0\] fields must be path, sha256",
            ),
            (
                "duplicate_record_paths",
                duplicate_paths,
                r"derivation source_manifests duplicates witness\.json",
            ),
            (
                "record_digest_malformed",
                bad_digest,
                r"derivation source_manifests\[0\] sha256 must be a SHA-256 digest",
            ),
            (
                "artifact_unavailable",
                missing_artifact,
                r"derivation source_manifests\[0\] artifact is unavailable: "
                r".*absent-witness\.json",
            ),
            (
                "supplemental_missing_tool",
                supplemental_missing_tool,
                r"derivation supplemental_target_derivations\[0\] fields must be "
                r"path, sha256, tool",
            ),
            (
                "supplemental_blank_tool",
                supplemental_blank_tool,
                r"derivation supplemental_target_derivations\[0\] tool must be a "
                r"non-empty string",
            ),
            (
                "seton_metric_without_source",
                seton_metric_without_source,
                r"Seton targets require source id 'seton_2020_oceanic_age'",
            ),
            (
                "seton_source_without_witness",
                seton_source_without_witness,
                r"derivation must declare exactly one checked Seton supplemental "
                r"target derivation",
            ),
        )
        for name, mutate, expected in cases:
            with self.subTest(case=name), TemporaryDirectory() as directory:
                root = Path(directory)
                witness = root / "witness.json"
                witness.write_text('{"evidence": true}\n', encoding="utf-8")
                bundle = _minimal_bundle()
                mutate(bundle, witness)
                with self.assertRaisesRegex(
                    GeoValidationSuiteError, expected
                ):
                    _load_bundle_manifest(root, bundle)

    def test_valid_witnesses_are_normalized_with_their_digests(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            witness = root / "witness.json"
            witness.write_text('{"evidence": true}\n', encoding="utf-8")
            digest = hashlib.sha256(witness.read_bytes()).hexdigest()
            bundle = _minimal_bundle()
            bundle["derivation"]["tool"] = "  fixture-derivation.py  "
            bundle["derivation"]["source_manifests"] = [
                {"path": witness.name, "sha256": digest.upper()}
            ]
            manifest = _load_bundle_manifest(root, bundle)
            loaded = manifest["scenarios"][0]["empirical_calibration"]
            target_bundle = loaded["target_bundle"]

            self.assertTrue(loaded["require_complete"])
            self.assertTrue(loaded["require_all_passed"])
            self.assertEqual(target_bundle["name"], "minimal_fixture_targets_v1")
            self.assertEqual(target_bundle["source_count"], 1)
            self.assertEqual(target_bundle["target_count"], 1)
            self.assertEqual(
                target_bundle["sha256"],
                hashlib.sha256(
                    (root / "targets.json").read_bytes()
                ).hexdigest(),
            )
            self.assertEqual(
                target_bundle["derivation"]["tool"], "fixture-derivation.py"
            )
            self.assertEqual(
                target_bundle["derivation"]["source_manifests"],
                [{"path": "witness.json", "sha256": digest}],
            )
            self.assertEqual(
                target_bundle["targets"][0]["dataset"], "fixture dataset"
            )


class SetonSupplementalWitnessTests(TestCase):
    """The Seton oceanic-age witness must substantiate every bundle target."""

    def _load_seton(
        self,
        root: Path,
        mutate: Callable[[dict[str, Any], dict[str, Any]], bytes | None],
    ) -> dict[str, Any]:
        bundle, artifact = _seton_fixture()
        raw = mutate(bundle, artifact)
        artifact_path = root / "seton-targets.json"
        if raw is None:
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        else:
            artifact_path.write_bytes(raw)
        witness = bundle["derivation"]["supplemental_target_derivations"][0]
        witness["path"] = str(artifact_path)
        witness["sha256"] = hashlib.sha256(
            artifact_path.read_bytes()
        ).hexdigest()
        return _load_bundle_manifest(root, bundle)

    def test_unmutated_seton_bundle_is_accepted(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self._load_seton(root, lambda bundle, artifact: None)
            target_bundle = manifest["scenarios"][0]["empirical_calibration"][
                "target_bundle"
            ]
            witness = target_bundle["derivation"][
                "supplemental_target_derivations"
            ][0]

            self.assertEqual(
                target_bundle["name"], "canonical_earth_empirical_targets_v2"
            )
            self.assertEqual(witness["tool"], SETON_SUPPLEMENTAL_TOOL)
            self.assertEqual(
                witness["sha256"],
                hashlib.sha256(
                    (root / "seton-targets.json").read_bytes()
                ).hexdigest(),
            )
            self.assertEqual(
                target_bundle["path"], str(root / "targets.json")
            )

    def test_witness_artifact_semantics_are_fail_closed(self) -> None:
        def not_json(bundle: dict[str, Any], artifact: dict[str, Any]) -> bytes:
            return b"{not json at all"

        def missing_and_extra_fields(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact.pop("description")
            artifact["provenance"] = "hand written"

        def statistics_not_object(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["statistics"] = "computed elsewhere"

        def wrong_schema(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["schema_version"] = 2

        def wrong_name(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["name"] = "seton_targets_v2"

        def wrong_accumulation(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["derivation"]["accumulation"] = "naive_left_to_right_sum"

        def blank_derived_on(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["derivation"]["derived_on"] = "   "

        def wrong_grid(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["source"]["source_grid_dimensions"] = [1801, 3600]

        def node_count_not_integer(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["source"]["source_total_node_count"] = 6485401.5

        def node_count_conflicts(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["source"]["source_total_node_count"] = 6485400

        def finite_nodes_out_of_range(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["source"]["source_finite_node_count"] = 0

        def negative_minimum_age(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["source"]["source_finite_minimum_age_ma"] = -1.0

        def wrong_units(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["source"]["source_variable_units"] = "Myr"

        def wrong_processing(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["source"]["source_processing"] = "Averaged the grid."

        def malformed_source_digest(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["source"]["source_sha256"] = "not-a-digest"

        def thresholds_not_a_list(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["statistics"]["cdf_thresholds_ma"] = "20,40"

        def threshold_not_integer(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["statistics"]["cdf_thresholds_ma"][0] = 20.5

        def cdf_values_not_a_list(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["statistics"]["area_weighted_cdf_le_threshold"] = 0.5

        def cdf_length_mismatch(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["statistics"]["area_weighted_cdf_le_threshold"].pop()

        def cdf_not_monotone(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            values = artifact["statistics"]["area_weighted_cdf_le_threshold"]
            values[0], values[1] = values[1], values[0]

        def cdf_above_one(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["statistics"]["area_weighted_cdf_le_threshold"][-1] = 1.5

        def mean_outside_source_range(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            artifact["statistics"]["area_weighted_mean_age_ma"] = 1000.0

        cases = (
            (
                "artifact_not_json",
                not_json,
                r"Seton supplemental target derivation is not a readable JSON "
                r"object: .*seton-targets\.json",
            ),
            (
                "artifact_field_set_mismatch",
                missing_and_extra_fields,
                r"fields do not match the canonical schema: missing description; "
                r"extra provenance",
            ),
            (
                "statistics_not_an_object",
                statistics_not_object,
                r"Seton supplemental target derivation statistics must be an object",
            ),
            (
                "wrong_schema_version",
                wrong_schema,
                r"Seton supplemental target derivation schema_version must be 1",
            ),
            (
                "wrong_artifact_name",
                wrong_name,
                r"Seton supplemental target derivation name must be "
                r"seton_2020_oceanic_crust_age_targets_v1",
            ),
            (
                "wrong_accumulation_rule",
                wrong_accumulation,
                r"derivation metadata 'accumulation' does not match the canonical "
                r"Seton derivation",
            ),
            (
                "blank_derived_on",
                blank_derived_on,
                r"derivation derived_on must be a non-empty string",
            ),
            (
                "wrong_grid_dimensions",
                wrong_grid,
                r"source_grid_dimensions must be \[1801, 3601\]",
            ),
            (
                "node_count_not_an_integer",
                node_count_not_integer,
                r"source_total_node_count must be an integer",
            ),
            (
                "node_count_conflicts_with_grid",
                node_count_conflicts,
                r"source_total_node_count conflicts with the grid",
            ),
            (
                "finite_node_count_out_of_range",
                finite_nodes_out_of_range,
                r"source_finite_node_count is out of range",
            ),
            (
                "negative_minimum_age",
                negative_minimum_age,
                r"finite source-age range is invalid",
            ),
            ("wrong_units", wrong_units, r"source_variable_units must be Ma"),
            (
                "wrong_source_processing",
                wrong_processing,
                r"source_processing does not match the canonical Seton derivation",
            ),
            (
                "malformed_source_digest",
                malformed_source_digest,
                r"source source_sha256 must be a SHA-256 digest",
            ),
            (
                "thresholds_not_an_array",
                thresholds_not_a_list,
                r"cdf_thresholds_ma must be an array",
            ),
            (
                "threshold_not_an_integer",
                threshold_not_integer,
                r"cdf_thresholds_ma\[0\] must be an integer",
            ),
            (
                "cdf_values_not_an_array",
                cdf_values_not_a_list,
                r"area_weighted_cdf_le_threshold must be an array",
            ),
            (
                "cdf_length_mismatch",
                cdf_length_mismatch,
                r"CDF values do not map one-to-one to thresholds",
            ),
            (
                "cdf_not_monotone",
                cdf_not_monotone,
                r"CDF values must be monotone fractions",
            ),
            (
                "cdf_above_one",
                cdf_above_one,
                r"CDF values must be monotone fractions",
            ),
            (
                "mean_outside_source_range",
                mean_outside_source_range,
                r"area_weighted_mean_age_ma is outside the source range",
            ),
        )
        for name, mutate, expected in cases:
            with self.subTest(case=name), TemporaryDirectory() as directory:
                with self.assertRaisesRegex(
                    GeoValidationSuiteError, expected
                ):
                    self._load_seton(Path(directory), mutate)

    def test_bundle_targets_must_match_the_witness_statistics(self) -> None:
        mean_metric = "initial_oceanic_crust_age_area_weighted_mean_ma"

        def drop_source_field(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            bundle["sources"]["seton_2020_oceanic_age"].pop("source_doi")

        def diverging_source_url(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            bundle["sources"]["seton_2020_oceanic_age"]["source_url"] = (
                "https://example.invalid/age-grid.xyz"
            )

        def missing_statistic(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            bundle["targets"] = [
                target
                for target in bundle["targets"]
                if target["metric"]
                != "initial_oceanic_crust_age_area_weighted_cdf_le_200_ma"
            ]

        def extra_statistic(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            extra = deepcopy(
                _seton_target(
                    bundle,
                    "initial_oceanic_crust_age_area_weighted_cdf_le_200_ma",
                )
            )
            extra["metric"] = (
                "initial_oceanic_crust_age_area_weighted_cdf_le_220_ma"
            )
            bundle["targets"].append(extra)

        def wrong_source_metric(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            _seton_target(bundle, mean_metric)["source_metric"] = "mean_age"

        def wrong_statistic(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            _seton_target(bundle, mean_metric)["source_statistic"] = (
                "arithmetic_mean"
            )

        def wrong_target_processing(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            _seton_target(bundle, mean_metric)["source_processing"] = (
                "Averaged every node without area weighting"
            )

        def wrong_target_units(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            _seton_target(bundle, mean_metric)["source_variable_units"] = (
                "fraction"
            )

        def wrong_sample_count(
            bundle: dict[str, Any], artifact: dict[str, Any]
        ) -> None:
            _seton_target(bundle, mean_metric)[
                "source_sample_record_count"
            ] = 12

        cases = (
            (
                "bundle_source_field_dropped",
                drop_source_field,
                r"cannot exactly substantiate the Seton bundle source metadata "
                r"fields",
            ),
            (
                "bundle_source_url_diverges",
                diverging_source_url,
                r"source metadata 'source_url' does not match the canonical bundle",
            ),
            (
                "missing_statistic_target",
                missing_statistic,
                r"missing or extra Seton statistics \(missing="
                r"\['initial_oceanic_crust_age_area_weighted_cdf_le_200_ma'\], "
                r"extra=\[\]\)",
            ),
            (
                "extra_statistic_target",
                extra_statistic,
                r"missing or extra Seton statistics \(missing=\[\], extra="
                r"\['initial_oceanic_crust_age_area_weighted_cdf_le_220_ma'\]\)",
            ),
            (
                "wrong_source_metric",
                wrong_source_metric,
                r"bundle target '" + mean_metric + r"' source_metric does not "
                r"match its statistic",
            ),
            (
                "wrong_source_statistic",
                wrong_statistic,
                r"source_statistic does not match its statistic",
            ),
            (
                "wrong_source_processing",
                wrong_target_processing,
                r"source_processing does not match its statistic",
            ),
            (
                "wrong_source_units",
                wrong_target_units,
                r"source_variable_units does not match the source",
            ),
            (
                "wrong_sample_record_count",
                wrong_sample_count,
                r"source_sample_record_count does not match the source",
            ),
        )
        for name, mutate, expected in cases:
            with self.subTest(case=name), TemporaryDirectory() as directory:
                with self.assertRaisesRegex(
                    GeoValidationSuiteError, expected
                ):
                    self._load_seton(Path(directory), mutate)
