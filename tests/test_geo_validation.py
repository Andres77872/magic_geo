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
    _strip_native_civilization_outputs,
    generate_geo_world,
    generate_world,
)
from magic_geo.config import WorldConfig, config_to_native, load_config
from magic_geo.control_volume_geometry import inspect_control_volume_geometry
from magic_geo.geo_evolution_provenance import (
    DIAGNOSTIC_TRAJECTORY_FAMILIES,
    NATIVE_STATE_HISTORY_FAMILIES,
    NOMINAL_TIME_BASIS,
    SOIL_LINKED_TIME_BASIS,
)
from magic_geo.cli import app
from magic_geo.geo_validation import extract_geo_metrics, validate_geo_world
from magic_geo.geo_validation_suite import (
    CIVILIZATION_TOP_LEVEL_FIELDS,
    GeoValidationSuiteError,
    evaluate_geo_validation_suite,
    geo_fingerprint,
    load_geo_validation_manifest,
)
from magic_geo.native import (
    generate_geo_world as generate_native_geo_world,
    generate_world as generate_native_world,
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
            "geo_evolution_provenance",
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

    def test_native_control_volumes_close_and_share_exact_reciprocal_edges(
        self,
    ) -> None:
        inspection = inspect_control_volume_geometry(self.world)

        self.assertTrue(inspection["passed"], inspection["failures"])
        metrics = inspection["metrics"]
        self.assertLess(metrics["surface_closure_error_km2"], 0.01)
        self.assertLess(metrics["maximum_area_replay_error_km2"], 0.001)
        self.assertLess(metrics["maximum_shared_endpoint_error"], 1.0e-9)
        self.assertEqual(
            metrics["control_volume_edge_pair_count"],
            3 * len(self.world["cells"]) - 6,
        )

    def test_control_volume_replay_rejects_edge_and_area_corruption(self) -> None:
        altered = deepcopy(self.world)
        altered["cells"][0]["control_volume_vertices_3d"][0][0] += 0.01

        inspection = inspect_control_volume_geometry(altered)
        report = validate_geo_world(altered, profile="generic")

        self.assertFalse(inspection["passed"])
        self.assertTrue(inspection["failures"])
        self.assertFalse(report["passed"])
        self.assertFalse(
            _check(report, "mesh", "native_cell_area_model_replay")["passed"]
        )

    def test_geo_factory_rejects_cell_omission(self) -> None:
        data = self.config.model_dump(mode="python")
        data["output"]["include_cells"] = False

        with self.assertRaisesRegex(
            ValueError,
            r"generate_geo_world requires output\.include_cells=true",
        ):
            generate_geo_world(WorldConfig.model_validate(data))

    def test_native_geo_path_skips_society_without_changing_natural_state(
        self,
    ) -> None:
        native_config = config_to_native(self.config)
        full = generate_native_world(native_config)
        geo = generate_native_geo_world(native_config)

        self.assertIsInstance(full["settlements"], list)
        self.assertIsInstance(full["routes"], list)
        for field in NATIVE_CIVILIZATION_TOP_LEVEL_FIELDS:
            self.assertEqual(geo.get(field), [])

        _strip_native_civilization_outputs(full)
        _strip_native_civilization_outputs(geo)
        self.assertEqual(geo, full)

    def test_generate_cli_exposes_geo_only_scope(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "geo-world.json"
            result = CliRunner().invoke(
                app,
                [
                    "generate",
                    "--config",
                    "configs/earthlike_seed.yaml",
                    "--cells",
                    "128",
                    "--geo-only",
                    "--output",
                    str(output),
                ],
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("scope=geo_only", result.output)
        self.assertEqual(payload["generation_scope"], "geo_only")
        self.assertIn("geo_evolution_provenance", payload)
        self.assertNotIn("settlements", payload)
        self.assertNotIn("historical_eras", payload)

    def test_small_generated_earth_world_passes_generic_deep_validation(
        self,
    ) -> None:
        report = validate_geo_world(self.world, profile="generic")

        self.assertTrue(report["passed"])
        self.assertEqual(report["summary"]["error_failure_count"], 0)
        self.assertEqual(report["metrics"]["cell_count"], 128)

    def test_small_generated_earth_world_passes_earthlike_internal_calibration(
        self,
    ) -> None:
        report = validate_geo_world(self.world, profile="earthlike")
        calibration = _check(
            report,
            "earthlike_profile",
            "calibration_pass_fraction",
        )

        self.assertTrue(report["passed"])
        self.assertTrue(calibration["passed"])
        self.assertGreaterEqual(
            calibration["observed"],
            calibration["expected"]["minimum"],
        )

    def test_each_natural_layer_has_direct_contract_evidence(self) -> None:
        report = validate_geo_world(self.world, profile="generic")
        audit = report["layer_contracts"]
        layers = audit["layers"]

        self.assertEqual(audit["report_type"], "geo_layer_contract_audit_v1")
        self.assertEqual(audit["layer_count"], 14)
        self.assertEqual(audit["passed_layer_count"], 14)
        self.assertTrue(audit["all_layer_contracts_passed"])
        self.assertEqual(
            [layer["phase"] for layer in layers],
            list(range(len(layers))),
        )
        self.assertEqual(
            {layer["id"] for layer in layers},
            {
                "planet_parameters",
                "spherical_mesh",
                "plate_tectonics",
                "crust_lithology",
                "relief_bathymetry",
                "sea_level_ocean",
                "climate_atmosphere",
                "hydrology",
                "erosion_sediment",
                "cryosphere",
                "soils_pedogenesis",
                "biomes_ecosystems",
                "natural_resources",
                "coupled_maturation",
            },
        )
        ids = {layer["id"] for layer in layers}
        for layer in layers:
            self.assertTrue(layer["contract_passed"], layer)
            self.assertFalse(layer["missing_or_invalid_outputs"], layer)
            self.assertGreater(layer["validation_check_count"], 0, layer)
            self.assertEqual(layer["validation_error_failure_count"], 0, layer)
            self.assertFalse(layer["missing_validation_domains"], layer)
            self.assertTrue(
                all(
                    count > 0
                    for count in layer["validation_domain_coverage"].values()
                ),
                layer,
            )
            self.assertFalse(layer["failed_dependencies"], layer)
            self.assertTrue(set(layer["dependencies"]).issubset(ids), layer)
            self.assertFalse(layer["empirical_realism_proven"])

        maturation = next(
            layer for layer in layers if layer["id"] == "coupled_maturation"
        )
        self.assertEqual(
            maturation["temporal_class"],
            "reference_scaled_nominal_maturation_intervals_without_physical_time",
        )
        self.assertIn("no_physical_calibration", maturation["evidence_class"])
        self.assertEqual(report["summary"]["layer_contract_failure_count"], 0)

    def test_history_families_distinguish_native_mutation_from_diagnostics(
        self,
    ) -> None:
        provenance = self.world["geo_evolution_provenance"]
        records = {
            record["family"]: record for record in provenance["families"]
        }

        self.assertFalse(provenance["physical_time_resolved"])
        self.assertTrue(provenance["nominal_time_coordinate_available"])
        self.assertFalse(provenance["nominal_time_calibrated"])
        self.assertFalse(self.world["simulation_clock"]["physical_time_resolved"])
        self.assertEqual(
            provenance["native_state_history_families"],
            list(NATIVE_STATE_HISTORY_FAMILIES),
        )
        self.assertEqual(
            provenance["diagnostic_trajectory_families"],
            list(DIAGNOSTIC_TRAJECTORY_FAMILIES),
        )
        self.assertFalse(
            set(NATIVE_STATE_HISTORY_FAMILIES).intersection(
                DIAGNOSTIC_TRAJECTORY_FAMILIES
            )
        )
        self.assertEqual(
            records["plate_motion_history"]["state_mutation_evidence"], "yes"
        )
        self.assertEqual(
            records["soil_profile_histories"]["state_mutation_evidence"], "no"
        )
        self.assertTrue(
            records["soil_profile_histories"][
                "nominal_time_coordinate_available"
            ]
        )
        self.assertEqual(
            records["soil_profile_histories"]["time_basis"],
            SOIL_LINKED_TIME_BASIS,
        )
        self.assertEqual(
            records["numeric_depression_fill_history"][
                "state_mutation_evidence"
            ],
            "mixed",
        )
        self.assertEqual(
            records["climate_seasonal_histories"]["time_basis"],
            "monthly_climatology",
        )
        self.assertEqual(
            records["plate_motion_history"]["time_basis"],
            NOMINAL_TIME_BASIS,
        )
        for family, record in records.items():
            self.assertEqual(record["record_count"], len(self.world[family]))
            self.assertFalse(record["physical_time_resolved"])
            self.assertFalse(record["nominal_time_calibrated"])
            if family in NATIVE_STATE_HISTORY_FAMILIES:
                self.assertTrue(record["nominal_time_coordinate_available"])
                for native_step in self.world[family]:
                    self.assertEqual(
                        native_step["nominal_time_basis"], NOMINAL_TIME_BASIS
                    )
                    self.assertFalse(native_step["physical_time_resolved"])
                    self.assertFalse(native_step["nominal_time_calibrated"])

        self.assertTrue(
            self.world["soil_pedogenesis_model"][
                "linked_nominal_time_coordinate_available"
            ]
        )
        soil_steps = self.world["soil_profile_histories"][0]["steps"]
        self.assertTrue(all(step["nominal_time_link_available"] for step in soil_steps))
        self.assertTrue(all(step["start_year_bp"] is None for step in soil_steps))

        report = validate_geo_world(self.world, profile="generic")
        self.assertEqual(
            _check(
                report,
                "evolution_provenance",
                "history_family_temporal_semantics",
            )["status"],
            "passed",
        )

    def test_false_temporal_provenance_claim_is_rejected(self) -> None:
        altered = deepcopy(self.world)
        altered["geo_evolution_provenance"]["physical_time_resolved"] = True
        diagnostic = next(
            record
            for record in altered["geo_evolution_provenance"]["families"]
            if record["family"] == "soil_profile_histories"
        )
        diagnostic["state_mutation_evidence"] = "yes"
        diagnostic["time_basis"] = "calibrated_geological_years"

        report = validate_geo_world(altered, profile="generic")
        check = _check(
            report,
            "evolution_provenance",
            "history_family_temporal_semantics",
        )
        maturation = next(
            layer
            for layer in report["layer_contracts"]["layers"]
            if layer["id"] == "coupled_maturation"
        )

        self.assertFalse(report["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertIn(
            "physical_time_resolved must be false", check["evidence"]["violations"]
        )
        self.assertIn(
            "soil_profile_histories: state_mutation_evidence",
            check["evidence"]["violations"],
        )
        self.assertIn(
            "soil_profile_histories: time_basis",
            check["evidence"]["violations"],
        )
        self.assertFalse(maturation["contract_passed"])

    def test_mutated_nominal_history_interval_is_rejected(self) -> None:
        altered = deepcopy(self.world)
        altered["plate_motion_history"][1]["nominal_interval_end_ma"] += 0.5

        report = validate_geo_world(altered, profile="generic")
        provenance = _check(
            report,
            "evolution_provenance",
            "history_family_temporal_semantics",
        )
        clock = _check(report, "simulation", "coupled_stage_feedback_replay")

        self.assertFalse(report["passed"])
        self.assertEqual(provenance["status"], "failed")
        self.assertEqual(clock["status"], "failed")

    def test_controlled_model_steps_create_a_replayable_maturation_trajectory(
        self,
    ) -> None:
        zero_data = self.config.model_dump(mode="python")
        zero_data["erosion"]["iterations"] = 0
        initial_only = generate_geo_world(WorldConfig.model_validate(zero_data))
        matured = self.world

        self.assertEqual(
            initial_only["plate_motion_history"][0],
            matured["plate_motion_history"][0],
        )
        self.assertEqual(
            initial_only["earth_system_feedback_history"][0],
            matured["earth_system_feedback_history"][0],
        )
        self.assertEqual(
            [step["stage"] for step in initial_only["earth_system_feedback_history"]],
            ["initial_climate_hydrology", "cryosphere_coupling"],
        )
        self.assertEqual(
            [step["stage"] for step in matured["earth_system_feedback_history"]],
            ["initial_climate_hydrology"]
            + ["erosion_iteration" for _ in range(self.config.erosion.iterations)]
            + ["cryosphere_coupling"],
        )
        self.assertEqual(
            len(initial_only["plate_motion_history"]), 1
        )
        self.assertEqual(
            len(matured["plate_motion_history"]),
            self.config.erosion.iterations + 1,
        )
        self.assertEqual(
            len(matured["earth_system_feedback_history"]),
            self.config.erosion.iterations + 2,
        )

        for plate in initial_only["plates"]:
            self.assertEqual(plate["cumulative_rotation_deg"], 0.0)
        for plate in matured["plates"]:
            expected_rotation = (
                plate["angular_speed"]
                * self.config.tectonics.plate_motion_scale_deg_per_step
                * self.config.erosion.maturation_timestep_ma
                / 5.0
                * self.config.erosion.iterations
            )
            self.assertAlmostEqual(
                plate["cumulative_rotation_deg"], expected_rotation, delta=0.002
            )

        self.assertEqual(
            sum(
                cell["plate_assignment_change_count"]
                for cell in initial_only["cells"]
            ),
            0,
        )
        self.assertGreater(
            sum(
                cell["plate_assignment_change_count"]
                for cell in matured["cells"]
            ),
            0,
        )
        self.assertFalse(
            any(
                abs(cell["crust_age_ma"] - cell["initial_crust_age_ma"])
                > 1.0e-6
                for cell in initial_only["cells"]
            )
        )
        self.assertTrue(
            any(
                abs(cell["crust_age_ma"] - cell["initial_crust_age_ma"])
                > 1.0e-6
                for cell in matured["cells"]
            )
        )
        self.assertGreater(
            matured["sediment_inventory_model"]["gross_mobilization_volume_km3"],
            initial_only["sediment_inventory_model"][
                "gross_mobilization_volume_km3"
            ],
        )
        self.assertTrue(validate_geo_world(initial_only, profile="generic")["passed"])
        self.assertTrue(validate_geo_world(matured, profile="generic")["passed"])

    def test_missing_layer_artifact_fails_its_contract(self) -> None:
        altered = deepcopy(self.world)
        altered.pop("climate_classification")

        report = validate_geo_world(altered, profile="generic")
        climate = next(
            layer
            for layer in report["layer_contracts"]["layers"]
            if layer["id"] == "climate_atmosphere"
        )

        self.assertFalse(report["passed"])
        self.assertFalse(climate["contract_passed"])
        self.assertEqual(
            climate["missing_or_invalid_outputs"], ["climate_classification"]
        )
        self.assertGreaterEqual(
            report["summary"]["layer_contract_failure_count"], 1
        )

    def test_layer_contract_failures_propagate_to_dependents(self) -> None:
        altered = deepcopy(self.world)
        altered.pop("planet_parameters")

        report = validate_geo_world(altered, profile="generic")
        layers = {
            layer["id"]: layer for layer in report["layer_contracts"]["layers"]
        }

        self.assertFalse(layers["planet_parameters"]["contract_passed"])
        self.assertFalse(layers["spherical_mesh"]["contract_passed"])
        self.assertEqual(
            layers["spherical_mesh"]["failed_dependencies"],
            ["planet_parameters"],
        )
        self.assertFalse(layers["plate_tectonics"]["contract_passed"])

    def test_dry_boundary_passes_complete_geo_validation(self) -> None:
        data = self.config.model_dump(mode="python")
        data["climate"]["precipitation_scale"] = 0.0
        data["erosion"]["iterations"] = 0
        dry_world = generate_geo_world(WorldConfig.model_validate(data))

        report = validate_geo_world(dry_world, profile="generic")

        self.assertTrue(report["passed"], report["checks"])
        drainage = _check(report, "hydrology", "acyclic_downhill_drainage")
        self.assertEqual(drainage["status"], "passed")
        self.assertEqual(drainage["observed"]["land_basin_count"], 0)
        self.assertEqual(drainage["observed"]["watershed_basin_count"], 0)

        altered = deepcopy(dry_world)
        altered["resource_deposit_model"]["flow_accumulation_scale"] = 3.0
        altered["ore_genesis_model"]["flow_accumulation_scale"] = 3.0
        altered_report = validate_geo_world(altered, profile="generic")
        self.assertFalse(altered_report["passed"])
        self.assertEqual(
            _check(
                altered_report,
                "geologic_resources",
                "resource_deposit_sources_and_ranges",
            )["status"],
            "failed",
        )
        self.assertEqual(
            _check(
                altered_report,
                "geologic_resources",
                "ore_system_membership_and_formation_sources",
            )["status"],
            "failed",
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

    def test_crust_material_shadow_failure_surfaces_in_report_and_cli(self) -> None:
        altered = deepcopy(self.world)
        altered["crust_material_shadow_model"][
            "physical_source_sink_resolved"
        ] = True

        report = validate_geo_world(altered, profile="generic")
        check = _check(
            report,
            "tectonics",
            "persistent_crust_material_shadow_replay",
        )

        self.assertFalse(report["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertTrue(check["evidence"]["violations"])
        self.assertTrue(
            any(
                "finite surface/exchange/empty-slab counter-model" in limitation
                for limitation in report["model_limitations"]
            )
        )

        with TemporaryDirectory() as directory:
            world_path = Path(directory) / "world.json"
            world_path.write_text(json.dumps(altered), encoding="utf-8")
            result = CliRunner().invoke(
                app,
                ["validate-geo", "--world", str(world_path)],
            )

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn(
            "FAIL tectonics.persistent_crust_material_shadow_replay",
            result.output,
        )

    def test_finite_crust_accounting_failure_surfaces_in_report_and_cli(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["crust_dry_rock_accounting_model"][
            "material_provenance_resolved"
        ] = True

        report = validate_geo_world(altered, profile="generic")
        check = _check(
            report,
            "tectonics",
            "finite_crust_dry_rock_accounting_replay",
        )

        self.assertFalse(report["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertTrue(check["evidence"]["violations"])

        with TemporaryDirectory() as directory:
            world_path = Path(directory) / "world.json"
            world_path.write_text(json.dumps(altered), encoding="utf-8")
            result = CliRunner().invoke(
                app,
                ["validate-geo", "--world", str(world_path)],
            )

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn(
            "FAIL tectonics.finite_crust_dry_rock_accounting_replay",
            result.output,
        )

    def test_sediment_partition_failure_surfaces_in_report_and_cli(self) -> None:
        altered = deepcopy(self.world)
        altered["glacial_sediment_transport_model"][
            "source_partition_audit_is_provenance_claim"
        ] = True

        report = validate_geo_world(altered, profile="generic")
        check = _check(
            report,
            "sediment",
            "sediment_alluvium_bedrock_source_partition_replay",
        )

        self.assertFalse(report["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertTrue(check["evidence"]["violations"])

        with TemporaryDirectory() as directory:
            world_path = Path(directory) / "world.json"
            world_path.write_text(json.dumps(altered), encoding="utf-8")
            result = CliRunner().invoke(
                app,
                ["validate-geo", "--world", str(world_path)],
            )

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn(
            "FAIL sediment.sediment_alluvium_bedrock_source_partition_replay",
            result.output,
        )

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

    def test_validate_geo_cli_rejects_contract_only_failure(self) -> None:
        altered = deepcopy(self.world)
        altered.pop("groundwater_flow_model")

        with TemporaryDirectory() as directory:
            world_path = Path(directory) / "world.json"
            report_path = Path(directory) / "report.json"
            world_path.write_text(json.dumps(altered), encoding="utf-8")
            result = CliRunner().invoke(
                app,
                [
                    "validate-geo",
                    "--world",
                    str(world_path),
                    "--output",
                    str(report_path),
                ],
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("FAIL geo", result.output)
        self.assertIn("FAIL layer_contract.hydrology", result.output)
        self.assertFalse(report["passed"])
        self.assertFalse(report["requested_policy"]["policy_passed"])

    def test_geo_generation_does_not_change_legacy_earth_generation(self) -> None:
        legacy_before = generate_world(self.config)

        legacy_geo_report = validate_geo_world(legacy_before, profile="generic")
        self.assertTrue(legacy_geo_report["passed"])
        self.assertNotIn(
            "evolution_provenance",
            legacy_geo_report["summary"]["domains"],
        )

        generate_geo_world(self.config)
        legacy_after = generate_world(self.config)

        self.assertEqual(legacy_after, legacy_before)
        self.assertNotIn("generation_scope", legacy_after)
        self.assertIsInstance(legacy_after["settlements"], list)
        self.assertIsInstance(legacy_after["political_regions"], list)
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
    profile: generic
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

    def test_checked_matrix_isolates_iteration_driven_maturation(self) -> None:
        complete = load_geo_validation_manifest(
            Path("configs/geo_validation_matrix.yaml")
        )
        selected_ids = {"maturation_initial", "maturation_evolved"}
        manifest = {
            **complete,
            "name": "isolated maturation integration",
            "scenarios": [
                scenario
                for scenario in complete["scenarios"]
                if scenario["id"] in selected_ids
            ],
            "relations": [
                relation
                for relation in complete["relations"]
                if relation["left"] in selected_ids
                and relation["right"] in selected_ids
            ],
        }

        report = evaluate_geo_validation_suite(self.config, manifest)
        members = {member["id"]: member for member in report["members"]}

        self.assertTrue(report["passed"], report)
        self.assertEqual(report["summary"]["scenario_pass_count"], 2)
        self.assertEqual(report["summary"]["relation_pass_count"], 5)
        self.assertEqual(
            members["maturation_initial"]["metrics"][
                "crust_evolved_cell_fraction"
            ],
            0.0,
        )
        self.assertGreaterEqual(
            members["maturation_evolved"]["metrics"][
                "crust_evolved_cell_fraction"
            ],
            0.50,
        )
        self.assertEqual(
            members["maturation_evolved"]["metrics"][
                "simulation_stage_count"
            ],
            8,
        )
