from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from magic_geo.api import generate_geo_world
from magic_geo.config import WorldConfig, load_config
from magic_geo.geo_validation_suite import (
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

        self.assertEqual(bundle["name"], "canonical_earth_empirical_targets_v1")
        self.assertEqual(bundle["target_count"], 11)
        self.assertEqual(bundle["source_count"], 6)
        self.assertFalse(bundle["derivation"]["runtime_requires_raw_sources"])
        self.assertEqual(
            {target["dataset"] for target in bundle["targets"]},
            {
                "Natural Earth",
                "NOAA ETOPO 2022",
                "WorldClim 2.1",
                "HydroBASINS",
                "HydroRIVERS",
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
            targets["watershed_hack_fitted_exponent"]["target_min"],
            0.255213509131,
        )

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

