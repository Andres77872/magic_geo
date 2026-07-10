from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.api import (
    NATIVE_CIVILIZATION_CELL_FIELDS,
    NATIVE_CIVILIZATION_SUMMARY_FIELDS,
    NATIVE_CIVILIZATION_TOP_LEVEL_FIELDS,
    generate_geo_world,
    generate_world,
)
from magic_geo.config import WorldConfig, load_config
from magic_geo.cli import app
from magic_geo.geo_validation import extract_geo_metrics, validate_geo_world
from magic_geo.geo_validation_suite import (
    CIVILIZATION_TOP_LEVEL_FIELDS,
    GeoValidationSuiteError,
    evaluate_geo_validation_suite,
    geo_fingerprint,
    load_geo_validation_manifest,
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


def _load_manifest(text: str) -> dict:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "geo-validation.yaml"
        path.write_text(text, encoding="utf-8")
        return load_geo_validation_manifest(path)


def _check(report: dict, domain: str, name: str) -> dict:
    return next(
        check
        for check in report["checks"]
        if check["domain"] == domain and check["name"] == name
    )


class GeoWorldValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _small_earth_config()
        cls.world = generate_geo_world(cls.config)

    def test_geo_factory_omits_civilization_and_retains_natural_pipeline(
        self,
    ) -> None:
        self.assertEqual(self.world["generation_scope"], "geo_only")
        self.assertFalse(
            NATIVE_CIVILIZATION_TOP_LEVEL_FIELDS.intersection(self.world)
        )
        self.assertFalse(CIVILIZATION_TOP_LEVEL_FIELDS.intersection(self.world))
        self.assertFalse(
            NATIVE_CIVILIZATION_SUMMARY_FIELDS.intersection(
                self.world["summary"]
            )
        )
        for cell in self.world["cells"]:
            self.assertFalse(
                NATIVE_CIVILIZATION_CELL_FIELDS.intersection(cell)
            )

        required_natural_outputs = {
            "aquifer_systems",
            "biome_diagnostics",
            "cells",
            "climate_model",
            "commodity_occurrences",
            "fault_systems",
            "groundwater_flow_systems",
            "ice_sheet_histories",
            "ore_genesis_systems",
            "planet_parameters",
            "plate_graph",
            "plates",
            "reef_systems",
            "resource_deposits",
            "river_graph",
            "sea_level_model",
            "sediment_transport_histories",
            "soil_profiles",
            "species_range_records",
            "watershed_boundary_segments",
            "watershed_graph",
            "watersheds",
            "wetland_systems",
            "wildfire_spread_histories",
        }
        self.assertFalse(required_natural_outputs.difference(self.world))
        for field in (
            "political_region_graph",
            "territorial_boundary_segments",
            "trade_route_graph",
        ):
            self.assertNotIn(field, self.world)

        self.assertEqual(
            self.world["planet_parameters"]["radius_km"],
            self.config.planet.radius_km,
        )
        for deposit in self.world["resource_deposits"]:
            self.assertEqual(deposit["political_region_id"], -1)
            self.assertEqual(deposit["culture_region_id"], -1)
        for reef in self.world["reef_systems"]:
            self.assertEqual(reef["settlement_ids"], [])
            self.assertEqual(reef["port_site_ids"], [])

    def test_small_generated_earth_world_passes_deep_validation(self) -> None:
        report = validate_geo_world(self.world, profile="earthlike")

        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["error_failure_count"], 0)
        self.assertEqual(report["metrics"]["cell_count"], 128)
        self.assertEqual(
            report["summary"]["domains"]["earthlike_profile"]["failed_count"],
            0,
        )

    def test_civilization_layers_do_not_affect_geo_verdict_metrics_or_fingerprint(
        self,
    ) -> None:
        baseline_report = validate_geo_world(self.world, profile="earthlike")
        baseline_fingerprint = geo_fingerprint(self.world)
        altered = deepcopy(self.world)

        for field in (
            "settlements",
            "political_regions",
            "cultures",
            "routes",
            "trade_flows",
            "population_histories",
            "dynasties",
            "market_exchanges",
            "historical_events",
            "worldbuilding_realism_checks",
        ):
            altered.pop(field, None)
        altered["settlements"] = {"deliberately": "not a settlement payload"}
        altered["population_histories"] = [None, float("nan")]
        for cell in altered["cells"]:
            for field in (
                "settlement_score",
                "political_region_id",
                "culture_region_id",
                "language_region_id",
            ):
                cell.pop(field, None)
            cell["population"] = {"invalid": "and ignored by geo validation"}

        altered_report = validate_geo_world(altered, profile="earthlike")

        self.assertEqual(altered_report["passed"], baseline_report["passed"])
        self.assertEqual(altered_report["metrics"], baseline_report["metrics"])
        self.assertEqual(altered_report["checks"], baseline_report["checks"])
        self.assertEqual(geo_fingerprint(altered), baseline_fingerprint)

    def test_area_water_budget_and_drainage_mutations_are_rejected(self) -> None:
        land_cell_index = next(
            index
            for index, cell in enumerate(self.world["cells"])
            if not cell["is_water"]
        )

        cases = (
            (
                "surface area",
                "mesh",
                "spherical_surface_area_closure",
                lambda world: world["cells"][land_cell_index].__setitem__(
                    "area_km2", world["cells"][land_cell_index]["area_km2"] * 2.0
                ),
            ),
            (
                "water budget",
                "hydrology",
                "land_water_budget_closure",
                lambda world: world["cells"][land_cell_index].__setitem__(
                    "runoff_mm_y",
                    world["cells"][land_cell_index]["runoff_mm_y"] + 25.0,
                ),
            ),
            (
                "drainage",
                "hydrology",
                "acyclic_downhill_drainage",
                lambda world: world["cells"][land_cell_index].__setitem__(
                    "flow_to", len(world["cells"]) + 1000
                ),
            ),
        )
        for label, domain, check_name, mutate in cases:
            with self.subTest(label=label):
                altered = deepcopy(self.world)
                mutate(altered)

                report = validate_geo_world(altered, profile="generic")

                self.assertFalse(report["passed"])
                self.assertEqual(_check(report, domain, check_name)["status"], "failed")

    def test_zero_candidate_realism_claim_is_not_applicable_not_a_pass(self) -> None:
        altered = deepcopy(self.world)
        record = next(
            record
            for record in altered["hydrology_realism_checks"]
            if record["name"] == "river_downhill_flow"
        )
        self.assertTrue(record["passed"])
        self.assertGreater(record["evidence"]["river_edge_count"], 0)
        record["evidence"]["river_edge_count"] = 0

        report = validate_geo_world(altered, profile="generic")
        check = _check(
            report,
            "realism_evidence",
            "hydrology_realism_checks.river_downhill_flow",
        )

        self.assertEqual(check["status"], "not_applicable")
        self.assertFalse(check["passed"])
        self.assertIn("vacuous", check["message"])
        self.assertTrue(report["passed"])
        self.assertGreater(
            extract_geo_metrics(self.world)["realism_evidence_coverage_fraction"],
            report["metrics"]["realism_evidence_coverage_fraction"],
        )

    def test_geo_fingerprint_is_deterministic_for_repeated_generation(self) -> None:
        repeated_world = generate_geo_world(self.config)

        self.assertEqual(geo_fingerprint(repeated_world), geo_fingerprint(self.world))

    def test_natural_summary_is_fingerprinted_but_not_trusted_for_paired_metrics(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        baseline_metrics = extract_geo_metrics(self.world)
        altered["summary"]["simulation_clock_stage_count"] = 999999
        altered["summary"]["mean_plate_cumulative_rotation_deg"] = -999999.0
        altered["summary"]["sediment_gross_mobilization_volume_km3"] = -999999.0

        self.assertNotEqual(geo_fingerprint(altered), geo_fingerprint(self.world))
        self.assertEqual(extract_geo_metrics(altered), baseline_metrics)

    def test_malformed_optional_payloads_return_failed_reports(self) -> None:
        cases = (
            lambda world: world["cells"][0].__setitem__("soil_depth_m", "bad"),
            lambda world: world["cells"][0].__setitem__("plate_id", float("inf")),
            lambda world: world["summary"].__setitem__("output_float_precision", "bad"),
            lambda world: world["commodity_occurrences"][0].__setitem__("cell_id", {}),
        )
        for mutate in cases:
            with self.subTest(mutation=mutate):
                altered = deepcopy(self.world)
                mutate(altered)

                report = validate_geo_world(altered, profile="generic")

                self.assertFalse(report["passed"])
                self.assertGreater(report["summary"]["error_failure_count"], 0)

    def test_biome_label_and_mirrored_diagnostic_do_not_bypass_replay(self) -> None:
        altered = deepcopy(self.world)
        original = str(altered["cells"][0]["biome"])
        replacement = "hot_desert" if original != "hot_desert" else "tundra"
        altered["cells"][0]["biome"] = replacement
        altered["biome_diagnostics"][0]["biome"] = replacement

        report = validate_geo_world(altered, profile="generic")

        self.assertFalse(report["passed"])
        self.assertEqual(
            _check(
                report,
                "soil_biome",
                "biome_diagnostic_causal_replay",
            )["status"],
            "failed",
        )

    def test_duplicate_physical_graph_node_is_rejected(self) -> None:
        altered = deepcopy(self.world)
        altered["plate_graph"]["nodes"][1] = deepcopy(
            altered["plate_graph"]["nodes"][0]
        )

        report = validate_geo_world(altered, profile="generic")

        self.assertFalse(report["passed"])
        self.assertEqual(
            _check(report, "natural_graphs", "physical_graph_coverage")["status"],
            "failed",
        )

    def test_validate_geo_cli_warning_policy_is_written_and_enforced(self) -> None:
        altered = deepcopy(self.world)
        record = altered["planet_realism_checks"][0]
        record["value"] = 0.325
        record["score"] = 0.5
        record["passed"] = False
        altered["summary"]["global_liquid_water_temperature_index"] = 0.325
        altered["summary"]["planet_realism_pass_count"] = 3
        altered["summary"]["planet_realism_pass_fraction"] = 0.75
        altered["summary"]["mean_planet_realism_score"] = 0.875

        with TemporaryDirectory() as directory:
            root = Path(directory)
            world_path = root / "world.json"
            allowed_path = root / "allowed.json"
            strict_path = root / "strict.json"
            world_path.write_text(json.dumps(altered), encoding="utf-8")
            runner = CliRunner()

            allowed = runner.invoke(
                app,
                [
                    "validate-geo",
                    "--world",
                    str(world_path),
                    "--output",
                    str(allowed_path),
                    "--allow-warnings",
                ],
            )
            strict = runner.invoke(
                app,
                [
                    "validate-geo",
                    "--world",
                    str(world_path),
                    "--output",
                    str(strict_path),
                    "--fail-on-warnings",
                ],
            )
            allowed_report = json.loads(allowed_path.read_text(encoding="utf-8"))
            strict_report = json.loads(strict_path.read_text(encoding="utf-8"))

        self.assertEqual(allowed.exit_code, 0, allowed.output)
        self.assertEqual(strict.exit_code, 1, strict.output)
        self.assertTrue(allowed_report["passed"])
        self.assertTrue(allowed_report["requested_policy"]["policy_passed"])
        self.assertFalse(strict_report["requested_policy"]["policy_passed"])
        self.assertEqual(strict_report["summary"]["warning_failure_count"], 1)

    def test_geo_generation_does_not_change_legacy_earth_generation(self) -> None:
        legacy_before = generate_world(self.config)

        generate_geo_world(self.config)
        legacy_after = generate_world(self.config)

        self.assertEqual(legacy_after, legacy_before)
        self.assertNotIn("generation_scope", legacy_after)
        self.assertTrue(legacy_after["settlements"])
        self.assertTrue(legacy_after["political_regions"])
        self.assertIn("trade_route_graph", legacy_after)
        self.assertIn("political_region_graph", legacy_after)
        self.assertIn("settlement_score", legacy_after["cells"][0])


class GeoValidationSuiteTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = _small_earth_config()
        cls.earth_world = generate_geo_world(cls.config)

    def test_manifest_applies_nested_overrides_without_replacing_siblings(self) -> None:
        manifest = _load_manifest(
            """
schema_version: 1
name: nested overrides
scenarios:
  - id: compact
    profile: generic
    overrides:
      run:
        seed: 9123
      planet:
        radius_km: 3200.0
        gravity_g: 0.4
"""
        )
        seen_configs: list[WorldConfig] = []

        def world_factory(config: WorldConfig) -> dict:
            seen_configs.append(config)
            return deepcopy(self.earth_world)

        report = evaluate_geo_validation_suite(
            self.config,
            manifest,
            world_factory=world_factory,
        )

        self.assertTrue(report["passed"])
        self.assertEqual(seen_configs[0].run.seed, 9123)
        self.assertEqual(seen_configs[0].planet.radius_km, 3200.0)
        self.assertEqual(seen_configs[0].planet.gravity_g, 0.4)
        self.assertEqual(
            seen_configs[0].planet.ocean_water_inventory_km3,
            self.config.planet.ocean_water_inventory_km3,
        )
        self.assertEqual(seen_configs[0].mesh.cell_count, self.config.mesh.cell_count)

    def test_manifest_rejects_unknown_nested_config_override(self) -> None:
        manifest = _load_manifest(
            """
schema_version: 1
name: invalid override
scenarios:
  - id: typo
    overrides:
      planet:
        raduis_km: 3200.0
"""
        )

        with self.assertRaisesRegex(
            GeoValidationSuiteError,
            r"unknown config override 'planet\.raduis_km'",
        ):
            evaluate_geo_validation_suite(
                self.config,
                manifest,
                world_factory=lambda _config: deepcopy(self.earth_world),
            )

    def test_small_earth_and_compact_planet_paired_suite_passes(self) -> None:
        manifest = _load_manifest(
            """
schema_version: 1
name: small diverse planets
scenarios:
  - id: earth
    profile: earthlike
    repeat: 2
    expectations:
      surface_area_km2: {min: 500000000, max: 520000000}
  - id: compact
    profile: generic
    overrides:
      planet:
        radius_km: 3200.0
        gravity_g: 0.4
        ocean_water_inventory_km3: 337600000.0
    expectations:
      surface_area_km2: {min: 128000000, max: 130000000}
relations:
  - id: radius_controls_surface_area
    left: earth
    right: compact
    metric: surface_area_km2
    operator: gt
    minimum_difference: 300000000
"""
        )

        report = evaluate_geo_validation_suite(self.config, manifest)

        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["scenario_pass_count"], 2)
        self.assertEqual(report["summary"]["relation_pass_count"], 1)
        self.assertTrue(report["relations"][0]["passed"])
        members = {member["id"]: member for member in report["members"]}
        self.assertTrue(members["earth"]["deterministic"])
        self.assertNotEqual(
            members["earth"]["geo_fingerprint_sha256"],
            members["compact"]["geo_fingerprint_sha256"],
        )
        self.assertGreater(
            members["earth"]["metrics"]["surface_area_km2"],
            members["compact"]["metrics"]["surface_area_km2"],
        )
