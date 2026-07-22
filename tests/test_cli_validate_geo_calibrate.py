"""CLI surface of ``validate-geo``, ``validate-geo-suite``, and the calibration commands.

Every case drives the public Typer application with ``CliRunner`` and pins the
exit code together with a distinctive fragment of the emitted text, so a change
in either the policy gates or the report envelope fails loudly.

The natural-system worlds come from :mod:`support.worlds`; ``coupled_128`` is
the smallest canonical world that passes ``validate-geo`` outright, so the
failing verdicts here are produced by deliberate, schema-valid tampering rather
than by relying on whichever gate a given world happens to trip.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.io import write_json

from support import worlds

from support.cli import assert_no_cli_crash

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_SOURCES = REPO_ROOT / "configs" / "calibration_sources.example.json"

#: Scenario/member overrides that mirror ``worlds.CANONICAL["coupled_128"]``,
#: the cheapest configuration the generator accepts.
SMALL_OVERRIDES_YAML = """      mesh: {cell_count: 128}
      tectonics: {plate_count: 8}
      erosion: {iterations: 1}
"""


def _flatten(output: str) -> str:
    """Collapse Typer's boxed, line-wrapped error rendering into one line."""
    return " ".join(output.replace("│", " ").split())


def _tamper_ocean_inventory(world: dict[str, Any]) -> None:
    """Break the configured ocean inventory so ``sea_level`` fails with an error."""
    world["planet_parameters"]["ocean_water_inventory_km3"] = 1.0


def _tamper_realism_warning(world: dict[str, Any]) -> str:
    """Push one climate realism claim out of range without breaking its integrity.

    ``realism_evidence`` failures are warning severity, so the tampered world
    still passes the default policy and only fails under ``--fail-on-warnings``.
    The family summary is recomputed so the error-severity integrity check that
    mirrors it keeps passing.
    """
    records = world["climate_realism_checks"]
    tampered = records[0]
    tampered["value"] = float(tampered["target_max"]) + 1.0
    tampered["passed"] = False
    tampered["score"] = 0.0
    pass_count = sum(
        1
        for record in records
        if float(record["target_min"]) <= float(record["value"]) <= float(record["target_max"])
    )
    summary = world["summary"]
    summary["climate_realism_pass_count"] = pass_count
    summary["climate_realism_pass_fraction"] = pass_count / len(records)
    summary["mean_climate_realism_score"] = sum(float(record["score"]) for record in records) / len(records)
    return f"climate_realism_checks.{tampered['name']}"


def _calibration_target(metric: str, target_min: float, target_max: float) -> dict[str, Any]:
    return {
        "dataset": "fixture_dataset",
        "layer": "fixture_layer",
        "metric": metric,
        "target_min": target_min,
        "target_max": target_max,
    }


def _write_json_text(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class ValidateGeoCliTests(TestCase):
    """``validate-geo`` input handling, profiles, report output, and policy gates."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = TemporaryDirectory()
        root = Path(cls._directory.name)
        cls.root = root
        cls.runner = CliRunner()

        cls.passing_world = root / "passing.json"
        write_json(cls.passing_world, worlds.cached_world_readonly("coupled_128"))

        failing = worlds.cached_world("coupled_128")
        _tamper_ocean_inventory(failing)
        cls.failing_world = root / "failing.json"
        write_json(cls.failing_world, failing)

        warning = worlds.cached_world("coupled_128")
        cls.warning_check_name = _tamper_realism_warning(warning)
        cls.warning_world = root / "warning.json"
        write_json(cls.warning_world, warning)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()

    def test_validate_geo_refuses_missing_and_corrupt_world_files(self) -> None:
        missing = self.runner.invoke(
            app, ["validate-geo", "--world", str(self.root / "absent.json")]
        )
        self.assertEqual(missing.exit_code, 2, missing.output)
        self.assertIn("does not exist", _flatten(missing.output))

        corrupt = self.root / "corrupt.json"
        corrupt.write_text('{"cells": [', encoding="utf-8")
        result = self.runner.invoke(app, ["validate-geo", "--world", str(corrupt)])
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("Invalid world file:", result.output)
        assert_no_cli_crash(self, result)

    def test_validate_geo_accepts_only_the_two_declared_profiles(self) -> None:
        # ``coupled_128`` is a 128-cell toy world: it satisfies every generic
        # gate, but it cannot satisfy the Earth-calibrated regime envelope the
        # earthlike profile layers on top, so the two profiles must reach
        # opposite verdicts on the very same file.
        cases = (
            ("generic", 0, "OK", []),
            ("earthlike", 1, "FAIL", ["earthlike_profile"]),
        )
        reports: dict[str, dict[str, Any]] = {}
        for profile, expected_exit, verdict, failed_domains in cases:
            with self.subTest(profile=profile):
                output = self.root / f"report_{profile}.json"
                result = self.runner.invoke(
                    app,
                    [
                        "validate-geo",
                        "--world",
                        str(self.passing_world),
                        "--profile",
                        profile,
                        "--output",
                        str(output),
                    ],
                )
                self.assertEqual(result.exit_code, expected_exit, result.output)
                report = json.loads(output.read_text(encoding="utf-8"))
                reports[profile] = report
                self.assertEqual(report["profile"], profile)
                # The earthlike profile adds its own regime gates on top of the
                # generic ones; the generic profile must not evaluate them.
                self.assertEqual(
                    "earthlike_profile" in report["summary"]["domains"],
                    profile == "earthlike",
                )
                failed = [check for check in report["checks"] if check["status"] == "failed"]
                self.assertEqual([check["domain"] for check in failed], failed_domains)
                # Regime gates are fatal, so every failure is echoed and counted
                # as an error under the default policy.
                self.assertEqual(
                    [check["severity"] for check in failed], ["error"] * len(failed_domains)
                )
                self.assertEqual(
                    report["requested_policy"]["policy_passed"], expected_exit == 0
                )
                self.assertIn(
                    f"{verdict} geo | checks={len(report['checks'])} "
                    f"errors={len(failed)} warnings=0",
                    result.output,
                )
                for check in failed:
                    self.assertIn(
                        f"FAIL {check['domain']}.{check['name']}: {check['message']}",
                        result.output,
                    )

        # The profile selects an additive gate set: earthlike evaluates every
        # generic check unchanged and contributes only its own domain.
        generic_ids = {(c["domain"], c["name"]) for c in reports["generic"]["checks"]}
        earthlike_ids = {(c["domain"], c["name"]) for c in reports["earthlike"]["checks"]}
        self.assertEqual(generic_ids - earthlike_ids, set())
        added = earthlike_ids - generic_ids
        self.assertEqual({domain for domain, _ in added}, {"earthlike_profile"})
        self.assertLessEqual(
            {
                "ocean_fraction",
                "global_mean_temperature_c",
                "elevation_span_m",
                "calibration_pass_fraction",
            },
            {name for _, name in added},
        )

        invalid = self.runner.invoke(
            app,
            ["validate-geo", "--world", str(self.passing_world), "--profile", "martian"],
        )
        self.assertEqual(invalid.exit_code, 2, invalid.output)
        self.assertIn("--profile must be generic or earthlike", invalid.output)

    def test_validate_geo_passes_and_writes_a_structured_report(self) -> None:
        output = self.root / "nested" / "report.json"
        result = self.runner.invoke(
            app,
            [
                "validate-geo",
                "--world",
                str(self.passing_world),
                "--output",
                str(output),
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["report_type"], "geo_world_validation_v1")
        self.assertEqual(report["profile"], "generic")
        self.assertTrue(report["passed"])
        self.assertEqual(
            report["requested_policy"],
            {"fail_on_warnings": False, "policy_passed": True},
        )
        summary = report["summary"]
        self.assertEqual(summary["error_failure_count"], 0)
        self.assertEqual(summary["warning_failure_count"], 0)
        self.assertEqual(summary["check_count"], len(report["checks"]))
        self.assertTrue(report["layer_contracts"]["all_layer_contracts_passed"])
        self.assertEqual(
            sorted({check["status"] for check in report["checks"]}),
            ["not_applicable", "passed"],
        )
        # Counted from the checks themselves rather than echoed back from the
        # summary the banner is built from.
        not_applicable = sum(
            1 for check in report["checks"] if check["status"] == "not_applicable"
        )
        self.assertGreater(not_applicable, 0)
        self.assertIn(
            f"OK geo | checks={len(report['checks'])} errors=0 warnings=0 "
            f"not_applicable={not_applicable}",
            result.output,
        )

        # --output is optional: the verdict must be reported identically, and
        # nothing may be written, when it is omitted.
        bare = self.runner.invoke(app, ["validate-geo", "--world", str(self.passing_world)])
        self.assertEqual(bare.exit_code, 0, bare.output)
        self.assertEqual(bare.output, result.output)

    def test_validate_geo_fails_on_an_error_check_and_its_layer_contracts(self) -> None:
        output = self.root / "failing_report.json"
        result = self.runner.invoke(
            app,
            [
                "validate-geo",
                "--world",
                str(self.failing_world),
                "--output",
                str(output),
            ],
        )

        self.assertEqual(result.exit_code, 1, result.output)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertFalse(report["requested_policy"]["policy_passed"])
        self.assertEqual(report["summary"]["error_failure_count"], 1)
        self.assertIn("FAIL geo | ", result.output)
        self.assertIn("errors=1 warnings=0", result.output)
        self.assertIn(
            "FAIL sea_level.ocean_inventory_closure: connected marine columns "
            "must close the configured ocean inventory",
            result.output,
        )
        self.assertIn("FAIL layer_contract.sea_level_ocean:", result.output)
        self.assertIn(
            "required artifacts, validation domains, or dependencies failed",
            result.output,
        )

    def test_validate_geo_warning_policy_is_opt_in(self) -> None:
        allowed_output = self.root / "warning_allowed.json"
        allowed = self.runner.invoke(
            app,
            [
                "validate-geo",
                "--world",
                str(self.warning_world),
                "--allow-warnings",
                "--output",
                str(allowed_output),
            ],
        )
        self.assertEqual(allowed.exit_code, 0, allowed.output)
        self.assertIn("OK geo | ", allowed.output)
        self.assertIn("errors=0 warnings=1", allowed.output)
        allowed_report = json.loads(allowed_output.read_text(encoding="utf-8"))
        self.assertEqual(
            allowed_report["requested_policy"],
            {"fail_on_warnings": False, "policy_passed": True},
        )

        strict_output = self.root / "warning_strict.json"
        strict = self.runner.invoke(
            app,
            [
                "validate-geo",
                "--world",
                str(self.warning_world),
                "--fail-on-warnings",
                "--output",
                str(strict_output),
            ],
        )
        self.assertEqual(strict.exit_code, 1, strict.output)
        self.assertIn("FAIL geo | ", strict.output)
        self.assertIn("errors=0 warnings=1", strict.output)
        self.assertIn(
            f"FAIL realism_evidence.{self.warning_check_name}: realism claim has "
            "eligible evidence but falls outside its declared range",
            strict.output,
        )
        strict_report = json.loads(strict_output.read_text(encoding="utf-8"))
        self.assertEqual(
            strict_report["requested_policy"],
            {"fail_on_warnings": True, "policy_passed": False},
        )
        # The underlying report verdict is unchanged; only the policy differs.
        self.assertTrue(strict_report["passed"])


class ValidateGeoSuiteCliTests(TestCase):
    """``validate-geo-suite`` manifest handling, artifacts, and failure reporting."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = TemporaryDirectory()
        cls.root = Path(cls._directory.name)
        cls.runner = CliRunner()
        cls.config = str(worlds.EARTHLIKE_CONFIG)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()

    def test_validate_geo_suite_refuses_missing_and_malformed_matrices(self) -> None:
        missing = self.runner.invoke(
            app,
            [
                "validate-geo-suite",
                "--config",
                self.config,
                "--matrix",
                str(self.root / "absent.yaml"),
                "--output",
                str(self.root / "unused.json"),
            ],
        )
        self.assertEqual(missing.exit_code, 2, missing.output)
        self.assertIn("does not exist", _flatten(missing.output))

        cases = (
            (
                "unparseable",
                "scenarios: [\n",
                "invalid geo validation manifest:",
            ),
            (
                "wrong_schema",
                "schema_version: 99\nname: x\nscenarios: []\n",
                "geo validation manifest schema_version must be 1",
            ),
            (
                "empty_scenarios",
                "schema_version: 1\nname: x\nscenarios: []\n",
                "geo validation manifest requires a non-empty scenarios list",
            ),
        )
        for name, text, expected in cases:
            with self.subTest(matrix=name):
                matrix = self.root / f"{name}.yaml"
                matrix.write_text(text, encoding="utf-8")
                result = self.runner.invoke(
                    app,
                    [
                        "validate-geo-suite",
                        "--config",
                        self.config,
                        "--matrix",
                        str(matrix),
                        "--output",
                        str(self.root / "unused.json"),
                    ],
                )
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertIn(expected, result.output)
                assert_no_cli_crash(self, result)
                self.assertFalse((self.root / "unused.json").exists())

    def test_validate_geo_suite_writes_report_and_markdown_summary(self) -> None:
        matrix = self.root / "passing_matrix.yaml"
        matrix.write_text(
            "schema_version: 1\n"
            "name: cli suite fixture\n"
            "scenarios:\n"
            "  - id: fixture_control\n"
            "    profile: generic\n"
            "    overrides:\n"
            f"{SMALL_OVERRIDES_YAML}"
            "  - id: fixture_variant\n"
            "    profile: generic\n"
            "    overrides:\n"
            "      run: {seed: 202}\n"
            f"{SMALL_OVERRIDES_YAML}"
            "relations:\n"
            "  - id: fixture_equal_resolution\n"
            "    left: fixture_control\n"
            "    right: fixture_variant\n"
            "    metric: cell_count\n"
            "    operator: eq\n",
            encoding="utf-8",
        )
        output = self.root / "suite" / "report.json"
        summary_path = self.root / "suite" / "report.md"

        result = self.runner.invoke(
            app,
            [
                "validate-geo-suite",
                "--config",
                self.config,
                "--matrix",
                str(matrix),
                "--output",
                str(output),
                "--summary",
                str(summary_path),
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("[1/2] fixture_control", result.output)
        self.assertIn("[2/2] fixture_variant", result.output)
        self.assertIn(
            f"Wrote {output} | scenarios=2/2 relations=1/1 empirical_fit=not-configured",
            result.output,
        )

        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(report["passed"])
        self.assertEqual(report["name"], "cli suite fixture")
        self.assertEqual(
            [member["id"] for member in report["members"]],
            ["fixture_control", "fixture_variant"],
        )
        self.assertEqual([relation["id"] for relation in report["relations"]], ["fixture_equal_resolution"])
        self.assertEqual(report["summary"]["scenario_pass_count"], 2)
        self.assertEqual(report["summary"]["relation_pass_count"], 1)
        self.assertEqual(report["summary"]["empirical_calibration_scenario_count"], 0)

        markdown = summary_path.read_text(encoding="utf-8")
        self.assertIn("# Geo Pipeline Validation: cli suite fixture", markdown)
        self.assertIn("Overall verdict: **PASS**", markdown)
        self.assertIn("| fixture_control | generic | PASS |", markdown)
        self.assertIn("| fixture_variant | generic | PASS |", markdown)
        self.assertIn("External empirical calibration: not configured.", markdown)

    def test_validate_geo_suite_reports_failed_scenarios_relations_and_metrics(self) -> None:
        bundle = {
            "schema_version": 1,
            "name": "cli_fixture_targets_v1",
            "description": "Unreachable external-fit fixture.",
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
                    "target_min": 0.999,
                    "target_max": 1.0,
                }
            ],
        }
        _write_json_text(self.root / "fixture_bundle.json", bundle)
        matrix = self.root / "failing_matrix.yaml"
        matrix.write_text(
            "schema_version: 1\n"
            "name: cli failing suite fixture\n"
            "scenarios:\n"
            "  - id: fixture_control\n"
            "    profile: generic\n"
            "    overrides:\n"
            f"{SMALL_OVERRIDES_YAML}"
            "    expectations:\n"
            "      ocean_fraction: {min: 0.999, max: 1.0}\n"
            "    empirical_calibration:\n"
            "      target_bundle: fixture_bundle.json\n"
            "  - id: fixture_variant\n"
            "    profile: generic\n"
            "    overrides:\n"
            "      run: {seed: 202}\n"
            f"{SMALL_OVERRIDES_YAML}"
            "relations:\n"
            "  - id: fixture_impossible_growth\n"
            "    left: fixture_control\n"
            "    right: fixture_variant\n"
            "    metric: cell_count\n"
            "    operator: gt\n"
            "    minimum_difference: 1000.0\n",
            encoding="utf-8",
        )
        output = self.root / "failing_report.json"

        result = self.runner.invoke(
            app,
            [
                "validate-geo-suite",
                "--config",
                self.config,
                "--matrix",
                str(matrix),
                "--output",
                str(output),
            ],
        )

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("scenarios=1/2 relations=0/1 empirical_fit=0/1 coverage=1/1", result.output)
        self.assertIn("Failed scenarios: fixture_control", result.output)
        self.assertIn("Failed relations: fixture_impossible_growth", result.output)
        self.assertIn(
            "Failed external empirical metrics: "
            "fixture_control:below_sea_level_surface_fraction",
            result.output,
        )

        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertFalse(report["passed"])
        self.assertEqual(
            [member["passed"] for member in report["members"]],
            [False, True],
        )
        self.assertEqual(
            [check["metric"] for check in report["empirical_calibration"]["failed_checks"]],
            ["below_sea_level_surface_fraction"],
        )

    def test_validate_geo_suite_names_only_the_categories_that_failed(self) -> None:
        """A failing category must not drag the other headers into the output."""
        header = (
            "schema_version: 1\n"
            "name: cli isolated failure fixture\n"
            "scenarios:\n"
            "  - id: fixture_control\n"
            "    profile: generic\n"
        )
        variant = (
            "  - id: fixture_variant\n"
            "    profile: generic\n"
            "    overrides:\n"
            "      run: {seed: 202}\n"
            f"{SMALL_OVERRIDES_YAML}"
        )
        cases = (
            (
                "relations_only",
                header
                + "    overrides:\n"
                + SMALL_OVERRIDES_YAML
                + variant
                + "relations:\n"
                "  - id: fixture_impossible_growth\n"
                "    left: fixture_control\n"
                "    right: fixture_variant\n"
                "    metric: cell_count\n"
                "    operator: gt\n"
                "    minimum_difference: 1000.0\n",
                "scenarios=2/2 relations=0/1",
                "Failed relations: fixture_impossible_growth",
                "Failed scenarios:",
            ),
            (
                "scenarios_only",
                header
                + "    overrides:\n"
                + SMALL_OVERRIDES_YAML
                + "    expectations:\n"
                "      ocean_fraction: {min: 0.999, max: 1.0}\n"
                + variant
                + "relations:\n"
                "  - id: fixture_equal_resolution\n"
                "    left: fixture_control\n"
                "    right: fixture_variant\n"
                "    metric: cell_count\n"
                "    operator: eq\n",
                "scenarios=1/2 relations=1/1",
                "Failed scenarios: fixture_control",
                "Failed relations:",
            ),
        )
        for name, matrix_text, banner, expected, forbidden in cases:
            with self.subTest(matrix=name):
                matrix = self.root / f"{name}.yaml"
                matrix.write_text(matrix_text, encoding="utf-8")
                output = self.root / f"{name}.json"
                result = self.runner.invoke(
                    app,
                    [
                        "validate-geo-suite",
                        "--config",
                        self.config,
                        "--matrix",
                        str(matrix),
                        "--output",
                        str(output),
                    ],
                )
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertIn(f"{banner} empirical_fit=not-configured", result.output)
                self.assertIn(expected, result.output)
                self.assertNotIn(forbidden, result.output)
                self.assertNotIn("Failed external empirical metrics:", result.output)
                # The report is written before the policy exit.
                report = json.loads(output.read_text(encoding="utf-8"))
                self.assertFalse(report["passed"])


class CalibrateCliTests(TestCase):
    """``calibrate`` report writing and the two ``--require-*`` policy gates."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = TemporaryDirectory()
        root = Path(cls._directory.name)
        cls.root = root
        cls.runner = CliRunner()
        cls.world = root / "replay.json"
        write_json(cls.world, worlds.cached_world_readonly("replay_128"))

        cls.satisfied_targets = _write_json_text(
            root / "targets_satisfied.json",
            {
                "targets": [
                    _calibration_target("below_sea_level_surface_fraction", 0.0, 1.0),
                    _calibration_target("ocean_fraction", 0.0, 1.0),
                ]
            },
        )
        cls.missing_targets = _write_json_text(
            root / "targets_missing.json",
            {"targets": [_calibration_target("totally_absent_metric", 0.0, 1.0)]},
        )
        cls.unreachable_targets = _write_json_text(
            root / "targets_unreachable.json",
            [_calibration_target("ocean_fraction", -2.0, -1.0)],
        )
        cls.empty_targets = _write_json_text(root / "targets_empty.json", {"targets": []})

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()

    def _invoke(self, name: str, targets: Path, *flags: str, summary: bool = True):
        return self.runner.invoke(
            app,
            [
                "calibrate",
                "--world",
                str(self.world),
                "--targets",
                str(targets),
                "--output",
                str(self.root / f"{name}.json"),
                *(["--summary", str(self.root / f"{name}.md")] if summary else []),
                *flags,
            ],
        )

    def test_calibrate_refuses_missing_inputs_and_malformed_targets(self) -> None:
        missing_world = self.runner.invoke(
            app,
            [
                "calibrate",
                "--world",
                str(self.root / "absent.json"),
                "--targets",
                str(self.satisfied_targets),
                "--output",
                str(self.root / "unused.json"),
            ],
        )
        self.assertEqual(missing_world.exit_code, 2, missing_world.output)
        self.assertIn("does not exist", _flatten(missing_world.output))

        missing_targets = self.runner.invoke(
            app,
            [
                "calibrate",
                "--world",
                str(self.world),
                "--targets",
                str(self.root / "absent_targets.json"),
                "--output",
                str(self.root / "unused.json"),
            ],
        )
        self.assertEqual(missing_targets.exit_code, 2, missing_targets.output)
        self.assertIn("does not exist", _flatten(missing_targets.output))

        cases = (
            (
                "wrong_shape",
                '{"not_targets": []}',
                "calibration targets must be a list or an object with a 'targets' list",
            ),
            ("unparseable", "{oops", "Expecting property name enclosed in double quotes"),
            (
                "inverted_range",
                json.dumps([_calibration_target("ocean_fraction", 1.0, 0.0)]),
                "target range for 'ocean_fraction' is inverted",
            ),
        )
        for name, text, expected in cases:
            with self.subTest(targets=name):
                targets = self.root / f"broken_{name}.json"
                targets.write_text(text, encoding="utf-8")
                result = self._invoke(f"report_{name}", targets)
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertIn(expected, result.output)
                assert_no_cli_crash(self, result)
                self.assertFalse((self.root / f"report_{name}.json").exists())

    def test_calibrate_writes_report_and_markdown_for_satisfied_targets(self) -> None:
        result = self._invoke("satisfied", self.satisfied_targets, "--require-all-metrics", "--require-all-passed")

        self.assertEqual(result.exit_code, 0, result.output)
        report_path = self.root / "satisfied.json"
        self.assertIn(
            f"Wrote {report_path} | checks=2 coverage=1.000 pass_fraction=1.000",
            result.output,
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(report),
            ["available_world_metrics", "checks", "missing_world_metrics", "summary"],
        )
        self.assertEqual(report["missing_world_metrics"], [])
        self.assertTrue(report["summary"]["external_calibration_complete"])
        self.assertEqual(report["summary"]["external_calibration_pass_count"], 2)
        self.assertEqual(
            [check["metric"] for check in report["checks"]],
            ["below_sea_level_surface_fraction", "ocean_fraction"],
        )
        self.assertEqual([check["passed"] for check in report["checks"]], [True, True])
        self.assertEqual([check["score"] for check in report["checks"]], [1.0, 1.0])

        markdown = (self.root / "satisfied.md").read_text(encoding="utf-8")
        self.assertIn("# Calibration Report", markdown)
        self.assertIn("below_sea_level_surface_fraction", markdown)

    def test_calibrate_require_all_metrics_gates_on_coverage(self) -> None:
        allowed = self._invoke("coverage_allowed", self.missing_targets, "--allow-missing-metrics")
        self.assertEqual(allowed.exit_code, 0, allowed.output)
        self.assertIn("checks=1 coverage=0.000 pass_fraction=0.000", allowed.output)

        violated = self._invoke("coverage_violated", self.missing_targets, "--require-all-metrics")
        self.assertEqual(violated.exit_code, 1, violated.output)
        self.assertIn(
            "Calibration coverage incomplete; missing world metrics: totally_absent_metric",
            violated.output,
        )
        report = json.loads((self.root / "coverage_violated.json").read_text(encoding="utf-8"))
        self.assertEqual(report["missing_world_metrics"], ["totally_absent_metric"])
        self.assertFalse(report["summary"]["external_calibration_complete"])

    def test_calibrate_require_all_passed_gates_on_fit(self) -> None:
        # --summary is optional here, so nothing may be written beside the report.
        allowed = self._invoke(
            "fit_allowed", self.unreachable_targets, "--allow-fit-failures", summary=False
        )
        self.assertEqual(allowed.exit_code, 0, allowed.output)
        self.assertIn("checks=1 coverage=1.000 pass_fraction=0.000", allowed.output)
        self.assertTrue((self.root / "fit_allowed.json").exists())
        self.assertFalse((self.root / "fit_allowed.md").exists())

        violated = self._invoke("fit_violated", self.unreachable_targets, "--require-all-passed")
        self.assertEqual(violated.exit_code, 1, violated.output)
        self.assertIn("Calibration fit failed; failed metrics: ocean_fraction", violated.output)
        report = json.loads((self.root / "fit_violated.json").read_text(encoding="utf-8"))
        self.assertEqual(report["summary"]["external_calibration_pass_count"], 0)
        self.assertFalse(report["checks"][0]["passed"])

    def test_calibrate_treats_an_empty_target_bundle_as_a_policy_violation(self) -> None:
        coverage = self._invoke("empty_coverage", self.empty_targets, "--require-all-metrics")
        self.assertEqual(coverage.exit_code, 1, coverage.output)
        self.assertIn(
            "Calibration coverage incomplete; no calibration targets were evaluated",
            coverage.output,
        )

        fit = self._invoke("empty_fit", self.empty_targets, "--require-all-passed")
        self.assertEqual(fit.exit_code, 1, fit.output)
        self.assertIn("Calibration fit failed; no calibration targets", fit.output)
        report = json.loads((self.root / "empty_fit.json").read_text(encoding="utf-8"))
        self.assertEqual(report["checks"], [])
        self.assertEqual(report["summary"]["external_calibration_check_count"], 0)


class CalibrateEnsembleCliTests(TestCase):
    """``calibrate-ensemble`` manifest handling and its two policy gates."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = TemporaryDirectory()
        root = Path(cls._directory.name)
        cls.root = root
        cls.runner = CliRunner()
        cls.config = str(worlds.EARTHLIKE_CONFIG)
        cls.matrix = _write_json_text(
            root / "ensemble.json",
            {
                "schema_version": 1,
                "name": "cli_fixture_ensemble_v1",
                "members": [
                    {
                        "id": "fixture_member",
                        "seed": 11,
                        "cell_count": 128,
                        "groups": ["fixture_group"],
                    }
                ],
            },
        )
        cls.satisfied_targets = _write_json_text(
            root / "targets_satisfied.json",
            {"targets": [_calibration_target("below_sea_level_surface_fraction", 0.0, 1.0)]},
        )
        cls.missing_targets = _write_json_text(
            root / "targets_missing.json",
            {"targets": [_calibration_target("totally_absent_metric", 0.0, 1.0)]},
        )
        cls.unreachable_targets = _write_json_text(
            root / "targets_unreachable.json",
            {"targets": [_calibration_target("ocean_fraction", -2.0, -1.0)]},
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()

    def _invoke(
        self,
        name: str,
        targets: Path,
        *flags: str,
        matrix: Path | None = None,
        summary: bool = True,
    ):
        return self.runner.invoke(
            app,
            [
                "calibrate-ensemble",
                "--config",
                self.config,
                "--matrix",
                str(self.matrix if matrix is None else matrix),
                "--targets",
                str(targets),
                "--output",
                str(self.root / f"{name}.json"),
                *(["--summary", str(self.root / f"{name}.md")] if summary else []),
                *flags,
            ],
        )

    def test_calibrate_ensemble_refuses_missing_and_malformed_manifests(self) -> None:
        missing = self._invoke(
            "unused", self.satisfied_targets, matrix=self.root / "absent.json"
        )
        self.assertEqual(missing.exit_code, 2, missing.output)
        self.assertIn("does not exist", _flatten(missing.output))

        cases = (
            (
                "wrong_schema",
                {"schema_version": 99, "name": "x", "members": []},
                "calibration ensemble schema_version must be 1",
            ),
            (
                "empty_members",
                {"schema_version": 1, "name": "x", "members": []},
                "calibration ensemble manifest requires a non-empty 'members' list",
            ),
            (
                "tiny_member",
                {
                    "schema_version": 1,
                    "name": "x",
                    "members": [{"id": "m", "seed": 1, "cell_count": 8}],
                },
                "calibration ensemble member 0 cell_count must be an integer of at least 128",
            ),
        )
        for name, payload, expected in cases:
            with self.subTest(matrix=name):
                matrix = _write_json_text(self.root / f"broken_{name}.json", payload)
                result = self._invoke(f"report_{name}", self.satisfied_targets, matrix=matrix)
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertIn(expected, result.output)
                assert_no_cli_crash(self, result)
                self.assertFalse((self.root / f"report_{name}.json").exists())

    def test_calibrate_ensemble_reports_a_satisfied_matrix(self) -> None:
        result = self._invoke(
            "satisfied",
            self.satisfied_targets,
            "--require-all-metrics",
            "--require-all-passed",
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("[1/1] fixture_member seed=11 cells=128", result.output)
        report_path = self.root / "satisfied.json"
        self.assertIn(
            f"Wrote {report_path} | members=1 coverage=1.000 all_passed=1.000",
            result.output,
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["name"], "cli_fixture_ensemble_v1")
        self.assertTrue(report["summary"]["reference_matrix_complete"])
        self.assertTrue(report["summary"]["reference_matrix_all_passed"])
        self.assertEqual([member["id"] for member in report["members"]], ["fixture_member"])
        self.assertEqual(report["members"][0]["requested_cell_count"], 128)
        bundles = report["provenance"]["target_bundles"]
        self.assertEqual([bundle["name"] for bundle in bundles], ["targets_satisfied.json"])
        self.assertEqual(bundles[0]["target_count"], 1)

        markdown = (self.root / "satisfied.md").read_text(encoding="utf-8")
        self.assertIn("# Calibration Ensemble Report", markdown)
        self.assertIn("fixture_member", markdown)

    def test_calibrate_ensemble_policy_gates_report_the_offending_members(self) -> None:
        coverage = self._invoke(
            "coverage", self.missing_targets, "--require-all-metrics", summary=False
        )
        self.assertEqual(coverage.exit_code, 1, coverage.output)
        self.assertIn("members=1 coverage=0.000 all_passed=0.000", coverage.output)
        self.assertIn("Calibration ensemble coverage incomplete", coverage.output)
        # The report is written before the policy exit; --summary stays optional.
        coverage_report = json.loads((self.root / "coverage.json").read_text(encoding="utf-8"))
        self.assertFalse(coverage_report["summary"]["reference_matrix_complete"])
        self.assertEqual(
            coverage_report["members"][0]["missing_world_metrics"], ["totally_absent_metric"]
        )
        self.assertFalse((self.root / "coverage.md").exists())

        fit = self._invoke("fit", self.unreachable_targets, "--require-all-passed")
        self.assertEqual(fit.exit_code, 1, fit.output)
        self.assertIn("members=1 coverage=1.000 all_passed=0.000", fit.output)
        self.assertIn(
            "Calibration ensemble fit failed; failed members: fixture_member",
            fit.output,
        )
        report = json.loads((self.root / "fit.json").read_text(encoding="utf-8"))
        self.assertFalse(report["summary"]["reference_matrix_all_passed"])
        self.assertFalse(report["members"][0]["all_targets_passed"])


class DeriveTargetsCliTests(TestCase):
    """``derive-targets`` source-manifest handling and derived artifacts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = TemporaryDirectory()
        cls.root = Path(cls._directory.name)
        cls.runner = CliRunner()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()

    def test_derive_targets_refuses_missing_and_malformed_sources(self) -> None:
        missing = self.runner.invoke(
            app,
            [
                "derive-targets",
                "--sources",
                str(self.root / "absent.json"),
                "--output",
                str(self.root / "unused.json"),
            ],
        )
        self.assertEqual(missing.exit_code, 2, missing.output)
        self.assertIn("does not exist", _flatten(missing.output))

        cases = (
            (
                "wrong_shape",
                '{"not_sources": []}',
                "calibration sources must be a list or an object with a 'sources' list",
            ),
            (
                "missing_path",
                json.dumps({"sources": [{"dataset": "d", "layer": "l", "metric": "m"}]}),
                "calibration target missing 'path'",
            ),
            (
                "absent_raster",
                json.dumps(
                    {
                        "sources": [
                            {
                                "dataset": "d",
                                "layer": "l",
                                "metric": "m",
                                "path": "no_such_grid.asc",
                                "format": "esri_ascii_grid",
                            }
                        ]
                    }
                ),
                "calibration source does not exist:",
            ),
            ("unparseable", "{oops", "Expecting property name enclosed in double quotes"),
        )
        output = self.root / "unwritten.json"
        for name, text, expected in cases:
            with self.subTest(sources=name):
                sources = self.root / f"broken_{name}.json"
                sources.write_text(text, encoding="utf-8")
                result = self.runner.invoke(
                    app,
                    [
                        "derive-targets",
                        "--sources",
                        str(sources),
                        "--output",
                        str(output),
                    ],
                )
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertIn(expected, result.output)
                assert_no_cli_crash(self, result)
                self.assertFalse(output.exists())

    def test_derive_targets_writes_targets_and_markdown_from_the_example_manifest(self) -> None:
        output = self.root / "derived" / "targets.json"
        summary_path = self.root / "derived" / "targets.md"
        result = self.runner.invoke(
            app,
            [
                "derive-targets",
                "--sources",
                str(EXAMPLE_SOURCES),
                "--output",
                str(output),
                "--summary",
                str(summary_path),
            ],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        report = json.loads(output.read_text(encoding="utf-8"))
        manifest = json.loads(EXAMPLE_SOURCES.read_text(encoding="utf-8"))["sources"]
        expected_sources = len(manifest)
        self.assertEqual(report["summary"]["source_count"], expected_sources)
        self.assertEqual(report["summary"]["derived_target_count"], expected_sources)
        self.assertEqual(len(report["targets"]), expected_sources)
        self.assertIn(
            f"Wrote {output} | targets={expected_sources} sources={expected_sources}",
            result.output,
        )

        # Every declared source names a distinct world_metric, so each target is
        # a renamed mapping of its source metric.
        self.assertEqual(report["summary"]["mapped_target_count"], expected_sources)
        self.assertEqual(report["summary"]["unique_world_metric_count"], expected_sources)
        self.assertEqual(
            [target["metric"] for target in report["targets"]],
            [source["world_metric"] for source in manifest],
        )
        self.assertEqual(
            [target["source_metric"] for target in report["targets"]],
            [source["metric"] for source in manifest],
        )
        for source, target in zip(manifest, report["targets"], strict=True):
            with self.subTest(metric=source["world_metric"]):
                # tolerance_abs derives a range centred on the sampled value.
                tolerance = source["tolerance_abs"]
                self.assertAlmostEqual(
                    target["target_min"], target["source_value"] - tolerance, places=9
                )
                self.assertAlmostEqual(
                    target["target_max"], target["source_value"] + tolerance, places=9
                )
                # Relative source paths resolve against the manifest directory,
                # not the working directory.
                self.assertEqual(
                    target["source"], str(EXAMPLE_SOURCES.parent / source["path"])
                )
                self.assertEqual(target["source_format"], source["format"])
                self.assertEqual(target["source_statistic"], source["statistic"])

        self.assertIn("# Calibration Target Derivation", summary_path.read_text(encoding="utf-8"))

        # --summary is optional and changes nothing about the derived targets.
        bare_output = self.root / "derived" / "targets_bare.json"
        bare = self.runner.invoke(
            app,
            ["derive-targets", "--sources", str(EXAMPLE_SOURCES), "--output", str(bare_output)],
        )
        self.assertEqual(bare.exit_code, 0, bare.output)
        self.assertEqual(json.loads(bare_output.read_text(encoding="utf-8")), report)
        self.assertEqual(
            sorted(path.name for path in (self.root / "derived").iterdir()),
            ["targets.json", "targets.md", "targets_bare.json"],
        )
