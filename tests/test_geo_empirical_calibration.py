from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from magic_geo.api import generate_geo_world
from magic_geo.calibration import (
    CalibrationError,
    evaluate_calibration_targets,
)
from magic_geo.config import WorldConfig, load_config
from magic_geo.geo_validation_suite import (
    GeoValidationSuiteError,
    evaluate_geo_validation_suite,
    load_geo_validation_manifest,
    write_geo_validation_suite_markdown,
)


def _small_earth_config() -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    return WorldConfig.model_validate(data)


def _canonical_empirical_bundle_fixture() -> tuple[dict, dict]:
    bundle_path = Path(
        "configs/geo_validation_earth_empirical_targets.json"
    ).resolve()
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    for field in (
        "source_manifests",
        "supplemental_target_derivations",
    ):
        for record in bundle["derivation"][field]:
            record["path"] = str(
                (bundle_path.parent / record["path"]).resolve()
            )
    supplemental_path = Path(
        bundle["derivation"]["supplemental_target_derivations"][0]["path"]
    )
    supplemental = json.loads(supplemental_path.read_text(encoding="utf-8"))
    return bundle, supplemental


def _write_empirical_bundle_fixture(root: Path, bundle: dict) -> Path:
    target_path = root / "targets.json"
    target_path.write_text(json.dumps(bundle), encoding="utf-8")
    matrix = root / "matrix.yaml"
    matrix.write_text(
        """
schema_version: 1
name: Seton semantic provenance fixture
scenarios:
  - id: earth
    profile: generic
    empirical_calibration:
      target_bundle: targets.json
      require_complete: true
      require_all_passed: true
""",
        encoding="utf-8",
    )
    return matrix


class GeoEmpiricalCalibrationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _small_earth_config()
        cls.world = generate_geo_world(cls.config)

    def test_checked_in_matrix_loads_precomputed_authoritative_targets(self) -> None:
        manifest = load_geo_validation_manifest(
            Path("configs/geo_validation_matrix.yaml")
        )
        canonical = next(
            scenario
            for scenario in manifest["scenarios"]
            if scenario["id"] == "earthlike_reference"
        )
        definition = canonical["empirical_calibration"]
        self.assertIsNotNone(definition)
        bundle = definition["target_bundle"]

        self.assertEqual(bundle["name"], "canonical_earth_empirical_targets_v2")
        self.assertEqual(bundle["target_count"], 22)
        self.assertEqual(bundle["source_count"], 7)
        self.assertFalse(bundle["derivation"]["runtime_requires_raw_sources"])
        self.assertEqual(
            {target["dataset"] for target in bundle["targets"]},
            {
                "Natural Earth",
                "NOAA ETOPO 2022",
                "WorldClim 2.1",
                "HydroBASINS",
                "HydroRIVERS",
                "Seton et al. 2020 present-day oceanic crustal age",
            },
        )
        targets = {target["metric"]: target for target in bundle["targets"]}
        self.assertEqual(
            targets["coastal_land_fraction"]["target_min"],
            0.434033613445,
        )
        self.assertEqual(
            targets["non_antarctic_endorheic_watershed_area_fraction"][
                "target_max"
            ],
            0.254952444749,
        )
        self.assertEqual(
            targets[
                "exorheic_watershed_backbone_hack_fitted_exponent"
            ]["target_min"],
            0.255213509131,
        )
        self.assertEqual(
            targets["initial_oceanic_crust_age_area_weighted_mean_ma"][
                "source_value"
            ],
            62.84149091327,
        )
        self.assertEqual(
            targets[
                "initial_oceanic_crust_age_area_weighted_cdf_le_40_ma"
            ]["target_max"],
            0.454644471212,
        )

    def test_empirical_derivation_artifact_digest_is_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            witness = root / "witness.json"
            witness.write_text('{"evidence":true}\n', encoding="utf-8")
            bundle = {
                "schema_version": 1,
                "name": "derivation digest fixture",
                "description": "Exercises local derivation provenance.",
                "derivation": {
                    "runtime_requires_raw_sources": False,
                    "source_manifests": [
                        {
                            "path": witness.name,
                            "sha256": "0" * 64,
                        }
                    ],
                    "supplemental_target_derivations": [
                        {
                            "path": witness.name,
                            "sha256": hashlib.sha256(
                                witness.read_bytes()
                            ).hexdigest(),
                            "tool": "fixture-derivation.py",
                        }
                    ],
                },
                "sources": {
                    "fixture": {
                        "dataset": "fixture",
                        "layer": "fixture",
                        "source": "raw.bin",
                    }
                },
                "targets": [
                    {
                        "source_id": "fixture",
                        "metric": "below_sea_level_surface_fraction",
                        "source_metric": "fixture",
                        "source_value": 0.5,
                        "target_min": 0.0,
                        "target_max": 1.0,
                    }
                ],
            }
            target_path = root / "targets.json"
            target_path.write_text(json.dumps(bundle), encoding="utf-8")
            matrix = root / "matrix.yaml"
            matrix.write_text(
                """
schema_version: 1
name: derivation digest fixture
scenarios:
  - id: earth
    profile: generic
    empirical_calibration:
      target_bundle: targets.json
      require_complete: true
      require_all_passed: true
""",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                GeoValidationSuiteError, "SHA-256 mismatch"
            ):
                load_geo_validation_manifest(matrix)

            bundle["derivation"]["source_manifests"][0]["sha256"] = (
                hashlib.sha256(witness.read_bytes()).hexdigest()
            )
            target_path.write_text(json.dumps(bundle), encoding="utf-8")
            manifest = load_geo_validation_manifest(matrix)
            self.assertEqual(
                manifest["scenarios"][0]["empirical_calibration"][
                    "target_bundle"
                ]["derivation"]["source_manifests"][0]["sha256"],
                hashlib.sha256(witness.read_bytes()).hexdigest(),
            )

    def test_seton_source_value_requires_semantic_witness(self) -> None:
        bundle, _ = _canonical_empirical_bundle_fixture()
        witness_records = bundle["derivation"][
            "supplemental_target_derivations"
        ]
        original_witnesses = deepcopy(witness_records)
        mean_target = next(
            target
            for target in bundle["targets"]
            if target["metric"]
            == "initial_oceanic_crust_age_area_weighted_mean_ma"
        )
        mean_target["source_value"] += 0.001
        self.assertEqual(witness_records, original_witnesses)

        with TemporaryDirectory() as directory:
            matrix = _write_empirical_bundle_fixture(
                Path(directory), bundle
            )
            with self.assertRaisesRegex(
                GeoValidationSuiteError,
                "source_value is not substantiated",
            ):
                load_geo_validation_manifest(matrix)

    def test_seton_supplemental_semantics_are_fail_closed(self) -> None:
        def missing_threshold(artifact: dict) -> None:
            artifact["statistics"]["cdf_thresholds_ma"].pop()
            artifact["statistics"][
                "area_weighted_cdf_le_threshold"
            ].pop()

        def extra_threshold(artifact: dict) -> None:
            artifact["statistics"]["cdf_thresholds_ma"].append(220)
            artifact["statistics"][
                "area_weighted_cdf_le_threshold"
            ].append(1.0)

        def duplicate_threshold(artifact: dict) -> None:
            artifact["statistics"]["cdf_thresholds_ma"].append(200)
            artifact["statistics"][
                "area_weighted_cdf_le_threshold"
            ].append(
                artifact["statistics"][
                    "area_weighted_cdf_le_threshold"
                ][-1]
            )

        def mismatched_threshold(artifact: dict) -> None:
            artifact["statistics"]["cdf_thresholds_ma"][0] = 21

        def mismatched_value(artifact: dict) -> None:
            artifact["statistics"][
                "area_weighted_cdf_le_threshold"
            ][0] += 0.001

        def mismatched_raw_sha(artifact: dict) -> None:
            artifact["source"]["source_sha256"] = "0" * 64

        cases = (
            ("missing_threshold", missing_threshold, "missing or extra thresholds"),
            ("extra_threshold", extra_threshold, "missing or extra thresholds"),
            ("duplicate_threshold", duplicate_threshold, "duplicate thresholds"),
            ("mismatched_threshold", mismatched_threshold, "missing or extra thresholds"),
            ("mismatched_value", mismatched_value, "source_value is not substantiated"),
            ("mismatched_raw_sha", mismatched_raw_sha, "source metadata 'source_sha256'"),
        )
        for name, mutate, expected_error in cases:
            with self.subTest(name=name), TemporaryDirectory() as directory:
                root = Path(directory)
                bundle, supplemental = _canonical_empirical_bundle_fixture()
                mutate(supplemental)
                supplemental_path = root / "seton-targets.json"
                supplemental_path.write_text(
                    json.dumps(supplemental), encoding="utf-8"
                )
                record = bundle["derivation"][
                    "supplemental_target_derivations"
                ][0]
                record["path"] = str(supplemental_path)
                record["sha256"] = hashlib.sha256(
                    supplemental_path.read_bytes()
                ).hexdigest()
                matrix = _write_empirical_bundle_fixture(root, bundle)
                with self.assertRaisesRegex(
                    GeoValidationSuiteError, expected_error
                ):
                    load_geo_validation_manifest(matrix)

    def test_initial_oceanic_age_empirical_metrics_rederive_from_ledger(self) -> None:
        ledger = self.world["initial_oceanic_crust_age_ledger"]
        targets = [
            {
                "dataset": "Seton fixture",
                "layer": "age",
                "metric": "initial_oceanic_crust_age_area_weighted_mean_ma",
                "source_metric": "mean",
                "source_value": 62.0,
                "target_min": 0.0,
                "target_max": 200.0,
            },
            {
                "dataset": "Seton fixture",
                "layer": "age",
                "metric": (
                    "initial_oceanic_crust_age_area_weighted_cdf_le_40_ma"
                ),
                "source_metric": "cdf40",
                "source_value": 0.4,
                "target_min": 0.0,
                "target_max": 1.0,
            },
        ]
        report = evaluate_calibration_targets(self.world, targets)
        checks = {check["metric"]: check for check in report["checks"]}
        self.assertEqual(
            checks[
                "initial_oceanic_crust_age_area_weighted_mean_ma"
            ]["value"],
            ledger["area_weighted_mean_age_ma"],
        )
        self.assertAlmostEqual(
            checks[
                "initial_oceanic_crust_age_area_weighted_cdf_le_40_ma"
            ]["value"],
            ledger["area_weighted_cdf_le_threshold"][1],
            delta=1.0e-15,
        )

        altered = deepcopy(self.world)
        altered["initial_oceanic_crust_age_ledger"][
            "area_weighted_cdf_le_threshold"
        ][1] += 0.01
        with self.assertRaisesRegex(
            CalibrationError,
            "summaries conflict",
        ):
            evaluate_calibration_targets(altered, targets)

    def test_external_fit_is_independent_fatal_gate_and_reports_failed_metric(
        self,
    ) -> None:
        target_bundle = {
            "schema_version": 1,
            "name": "synthetic_external_fit",
            "description": "External-fit contract fixture.",
            "derivation": {"runtime_requires_raw_sources": False},
            "sources": {
                "fixture": {
                    "dataset": "external fixture",
                    "layer": "ocean mask",
                    "source": "raw-source-is-deliberately-absent.bin",
                    "source_version": "1",
                }
            },
            "targets": [
                {
                    "source_id": "fixture",
                    "metric": "below_sea_level_surface_fraction",
                    "source_metric": "observed_ocean_fraction",
                    "source_value": 0.0,
                    "target_min": 0.0,
                    "target_max": 0.0,
                    "tolerance_basis": "Exact fixture range.",
                }
            ],
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "targets.json").write_text(
                json.dumps(target_bundle), encoding="utf-8"
            )
            matrix = root / "matrix.yaml"
            matrix.write_text(
                """
schema_version: 1
name: empirical fit contract
scenarios:
  - id: earth
    profile: generic
    empirical_calibration:
      target_bundle: targets.json
      require_complete: true
      require_all_passed: true
""",
                encoding="utf-8",
            )
            manifest = load_geo_validation_manifest(matrix)
            report = evaluate_geo_validation_suite(
                self.config,
                manifest,
                world_factory=lambda _config: deepcopy(self.world),
            )
            markdown = root / "report.md"
            write_geo_validation_suite_markdown(markdown, report)
            rendered = markdown.read_text(encoding="utf-8")

        member = report["members"][0]
        self.assertTrue(member["internal_validation_passed"])
        self.assertFalse(member["empirical_calibration_passed"])
        self.assertFalse(member["passed"])
        self.assertFalse(report["passed"])
        self.assertEqual(report["summary"]["internal_scenario_pass_count"], 1)
        self.assertEqual(report["summary"]["scenario_pass_count"], 0)
        self.assertEqual(
            report["summary"]["empirical_calibration_metric_coverage_fraction"],
            1.0,
        )
        self.assertEqual(
            report["summary"]["empirical_calibration_pass_fraction"], 0.0
        )
        failed = report["empirical_calibration"]["failed_checks"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["scenario_id"], "earth")
        self.assertEqual(
            failed[0]["metric"], "below_sea_level_surface_fraction"
        )
        self.assertIn("External Empirical Calibration Failures", rendered)
        self.assertIn("below_sea_level_surface_fraction", rendered)
        self.assertIn("Internal geo gates: 1/1 scenarios passed", rendered)
