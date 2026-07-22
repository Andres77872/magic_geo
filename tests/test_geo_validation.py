from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from unittest import TestCase

from typer.testing import CliRunner

from support import worlds

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

    def test_geo_validation_rejects_prior_world_schema(self) -> None:
        for schema_version in (1, 2.0, True, None):
            with self.subTest(schema_version=schema_version):
                altered = deepcopy(self.world)
                altered["schema_version"] = schema_version

                report = validate_geo_world(altered, profile="generic")

                self.assertFalse(report["passed"])
                schema_check = _check(report, "contract", "world_schema_version")
                self.assertFalse(schema_check["passed"])
                self.assertEqual(schema_check["expected"], 2)

    def test_geo_validation_requires_current_climate_contract(self) -> None:
        mutations = {
            "model_type": "equilibrium_latitude_circulation_climate_v4",
            "precipitation_model": (
                "bounded_thermal_moisture_circulation_orography_wind_transport_v2"
            ),
            "negative_precipitation_behavior": "retired",
            "zero_precipitation_scale_behavior": "retired",
        }
        for field, retired_value in mutations.items():
            with self.subTest(field=field):
                altered = deepcopy(self.world)
                altered["climate_model"][field] = retired_value

                report = validate_geo_world(altered, profile="generic")

                self.assertFalse(report["passed"])
                climate_check = _check(
                    report,
                    "contract",
                    "current_climate_model",
                )
                self.assertFalse(climate_check["passed"])
                self.assertEqual(
                    climate_check["observed"][field],
                    retired_value,
                )

    def test_geo_validation_rejects_retired_world_fields(self) -> None:
        altered = deepcopy(self.world)
        altered["simulation_clock"][
            "legacy_mean_erosion_rate_field_semantics"
        ] = "retired"
        for step in altered["earth_system_feedback_history"]:
            step["mean_erosion_rate_m_per_step"] = 0.0
        altered["plate_kinematic_model"][
            "accelerator_crust_source_remap_kernel_used"
        ] = False
        altered["backend"]["opencl_crust_source_remap_dispatch_count"] = 0
        altered["climate_model"][
            "positive_precipitation_pre_thermal_annual_floor_mm"
        ] = 20.0
        altered["oceanic_age_depth_model"][
            "thermal_target_difference_tendency_formula"
        ] = "retired"
        for step in altered["plate_motion_history"]:
            step["thermal_target_difference_tendency_m"] = []
        altered["numeric_depression_fill_history"] = []
        altered["summary"]["numeric_depression_fill_event_count"] = 0
        altered["cells"][0]["cumulative_numeric_depression_fill_m"] = 0.0
        for step in altered["earth_system_feedback_history"]:
            step["numeric_depression_fill_pass_count"] = 0

        report = validate_geo_world(altered, profile="generic")

        self.assertFalse(report["passed"])
        retired_check = _check(report, "contract", "retired_world_schema_fields")
        self.assertFalse(retired_check["passed"])
        self.assertGreaterEqual(len(retired_check["observed"]), 11)

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
            records["numeric_depression_correction_history"][
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
        initial_only_ages = initial_only["plate_motion_history"][0][
            "crust_overlap_ledger"
        ]["remapped_crust_age_ma_by_cell"]
        matured_initial_ages = matured["plate_motion_history"][0][
            "crust_overlap_ledger"
        ]["remapped_crust_age_ma_by_cell"]
        self.assertFalse(
            any(
                abs(cell["crust_age_ma"] - initial_age) > 1.0e-6
                for cell, initial_age in zip(
                    initial_only["cells"], initial_only_ages, strict=True
                )
            )
        )
        self.assertTrue(
            any(
                abs(cell["crust_age_ma"] - initial_age) > 1.0e-6
                for cell, initial_age in zip(
                    matured["cells"], matured_initial_ages, strict=True
                )
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

    def test_geo_generation_does_not_change_full_world_generation(self) -> None:
        full_world_before = generate_world(self.config)

        full_world_geo_report = validate_geo_world(
            full_world_before,
            profile="generic",
        )
        self.assertTrue(full_world_geo_report["passed"])
        self.assertNotIn(
            "evolution_provenance",
            full_world_geo_report["summary"]["domains"],
        )

        generate_geo_world(self.config)
        full_world_after = generate_world(self.config)

        self.assertEqual(full_world_after, full_world_before)
        self.assertNotIn("generation_scope", full_world_after)
        self.assertIsInstance(full_world_after["settlements"], list)
        self.assertIsInstance(full_world_after["political_regions"], list)
        self.assertIn("trade_route_graph", full_world_after)
        self.assertIn("political_region_graph", full_world_after)
        self.assertIn("settlement_score", full_world_after["cells"][0])


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


class GeoValidationViolationBranchTests(TestCase):
    """The reporting branches a healthy generated world never reaches.

    ``validate_geo_world`` takes the passing path through every check when the
    world is well formed, so the branches that report a violation only run on a
    deliberately damaged payload.  Each case here changes exactly one field,
    proves the field held a different value beforehand, and is paired with the
    untampered verdict for the same check so a broken fixture cannot masquerade
    as a detected violation.
    """

    WORLD_KEY = "coupled_128"

    @classmethod
    def setUpClass(cls) -> None:
        cls.control = validate_geo_world(worlds.cached_world_readonly(cls.WORLD_KEY))

    def world(self) -> dict:
        return worlds.cached_world(self.WORLD_KEY)

    def assign(self, container: dict, key: str, value: Any) -> None:
        """Write ``value`` after proving it is not what the generator produced."""
        self.assertIn(key, container)
        self.assertNotEqual(
            container[key], value, f"inert tamper: {key} already holds {value!r}"
        )
        container[key] = value

    def append(self, sequence: list, value: Any) -> None:
        self.assertNotIn(value, sequence)
        sequence.append(value)

    def replace_at(self, sequence: list, index: int, value: Any) -> None:
        """Overwrite one element after proving it held something else."""
        self.assertNotEqual(sequence[index], value)
        sequence[index] = value

    def report_for(self, mutate: Callable[[dict], None], **kwargs: Any) -> dict:
        world = self.world()
        mutate(world)
        return validate_geo_world(world, **kwargs)

    def assert_flipped(self, report: dict, domain: str, name: str) -> dict:
        """Assert ``domain.name`` passes untampered and failed in ``report``."""
        self.assertEqual(
            _check(self.control, domain, name)["status"],
            "passed",
            f"{domain}.{name} is not clean before the tamper",
        )
        check = _check(report, domain, name)
        self.assertEqual(check["status"], "failed", check)
        self.assertFalse(report["passed"])
        return check

    def assert_newly_reported(self, report: dict, domain: str, name: str) -> dict:
        """Assert ``domain.name`` is emitted only because of the tamper."""
        self.assertFalse(
            any(
                check["domain"] == domain and check["name"] == name
                for check in self.control["checks"]
            ),
            f"{domain}.{name} already exists before the tamper",
        )
        check = _check(report, domain, name)
        self.assertEqual(check["status"], "failed", check)
        self.assertFalse(report["passed"])
        return check

    def assert_only_plate_graph_broke(
        self, check: dict, *, invalid_edge_semantics: int
    ) -> None:
        """Pin the damaged graph, its cause, and the two graphs left alone.

        ``physical_graph_coverage`` reports one verdict per graph and exposes no
        per-condition counter for shape damage, so ``valid`` alone cannot say
        which graph broke.  Asserting the sibling graphs stay valid, and whether
        the edge-semantics counter moved, separates a shape defect in
        ``plate_graph`` from a semantic one and from a world-wide collapse.
        """
        observed = check["observed"]
        self.assertFalse(observed["plate_graph"]["valid"])
        self.assertEqual(
            observed["plate_graph"]["invalid_edge_semantics_count"],
            invalid_edge_semantics,
        )
        self.assertTrue(observed["river_graph"]["valid"])
        self.assertTrue(observed["watershed_graph"]["valid"])

    def run_cases(self, cases: tuple) -> None:
        for label, mutate, domain, name, assertion in cases:
            with self.subTest(case=label):
                report = self.report_for(mutate)
                assertion(self.assert_flipped(report, domain, name))

    def test_untampered_world_reports_a_clean_verdict(self) -> None:
        failed = [
            (check["domain"], check["name"])
            for check in self.control["checks"]
            if check["status"] == "failed"
        ]

        self.assertTrue(self.control["passed"], failed)
        self.assertEqual(failed, [])
        self.assertEqual(self.control["profile"], "generic")
        self.assertTrue(self.control["layer_contracts"]["all_layer_contracts_passed"])

    def test_mesh_geometry_violations_are_reported_per_defect(self) -> None:
        self.run_cases(
            (
                (
                    "position vector is not a 3-component point",
                    lambda world: self.assign(
                        world["cells"][0], "position_3d", [0.0, 0.0]
                    ),
                    "mesh",
                    "unit_sphere_positions",
                    lambda check: self.assertEqual(check["observed"], math.inf),
                ),
                (
                    "latitude outside the polar range",
                    lambda world: self.assign(world["cells"][0], "lat_deg", 95.0),
                    "mesh",
                    "coordinate_position_consistency",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_coordinate_count"], 1
                    ),
                ),
                (
                    "neighbor list replaced by a mapping",
                    lambda world: self.assign(world["cells"][0], "neighbors", {}),
                    "mesh",
                    "adjacency_graph_integrity",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_links"], 1
                    ),
                ),
                (
                    "neighbor id outside the mesh",
                    lambda world: self.assign(
                        world["cells"][0],
                        "neighbors",
                        list(world["cells"][0]["neighbors"]) + [99999],
                    ),
                    "mesh",
                    "adjacency_graph_integrity",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_links"], 1
                    ),
                ),
                (
                    "cell listed as its own neighbor",
                    lambda world: self.assign(
                        world["cells"][0],
                        "neighbors",
                        list(world["cells"][0]["neighbors"])
                        + [int(world["cells"][0]["id"])],
                    ),
                    "mesh",
                    "adjacency_graph_integrity",
                    lambda check: self.assertEqual(check["observed"]["self_links"], 1),
                ),
                (
                    "adjacency edge record is not an object",
                    lambda world: self.append(
                        world["cell_adjacency_edges"], "not-an-edge"
                    ),
                    "mesh",
                    "configured_radius_distance_scaling",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_edge_count"], 1
                    ),
                ),
                (
                    "adjacency edge endpoint outside the mesh",
                    lambda world: self.assign(
                        world["cell_adjacency_edges"][0], "cell_a_id", 99999
                    ),
                    "mesh",
                    "configured_radius_distance_scaling",
                    lambda check: self.assertEqual(
                        check["observed"]["missing_edge_count"], 1
                    ),
                ),
                (
                    "great-circle distance no longer uses the planet radius",
                    lambda world: self.assign(
                        world["cell_adjacency_edges"][0],
                        "great_circle_distance_km",
                        world["cell_adjacency_edges"][0]["great_circle_distance_km"]
                        + 500.0,
                    ),
                    "mesh",
                    "configured_radius_distance_scaling",
                    lambda check: self.assertGreater(
                        check["observed"]["maximum_distance_error_km"], 499.0
                    ),
                ),
                (
                    "edge ledger replaced by a mapping",
                    lambda world: self.assign(world, "cell_adjacency_edges", {}),
                    "mesh",
                    "configured_radius_distance_scaling",
                    lambda check: self.assertIsNone(check["observed"]["edge_count"]),
                ),
            )
        )

    def test_tectonic_and_sea_level_violations_are_reported(self) -> None:
        def drain_the_ocean(world: dict) -> None:
            marine = [cell for cell in world["cells"] if cell["is_water"]]
            self.assertTrue(marine)
            for cell in marine:
                cell["is_water"] = False

        self.run_cases(
            (
                (
                    "plate id is not coercible to an integer",
                    lambda world: self.assign(world["cells"][0], "plate_id", {}),
                    "tectonics",
                    "plate_assignment_coverage",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_cell_count"], 1
                    ),
                ),
                (
                    "plate id names no exported plate",
                    lambda world: self.assign(world["cells"][0], "plate_id", 99999),
                    "tectonics",
                    "plate_assignment_coverage",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_cell_count"], 1
                    ),
                ),
                (
                    "every marine cell relabelled as land",
                    drain_the_ocean,
                    "sea_level",
                    "single_connected_ocean",
                    lambda check: self.assertEqual(
                        check["observed"],
                        {"connected_water_cell_count": 0, "water_cell_count": 0},
                    ),
                ),
            )
        )

    def test_climate_and_hydrology_violations_are_reported(self) -> None:
        def break_groundwater_link(world: dict) -> None:
            cell = next(
                cell
                for cell in world["cells"]
                if cell["groundwater_internal_lateral_outflow_km3_y"] > 1.0e-10
            )
            self.assign(cell, "groundwater_flow_to_cell_id", -1)

        def wet_the_seafloor(world: dict) -> None:
            cell = next(cell for cell in world["cells"] if cell["is_water"])
            self.assign(cell, "groundwater_recharge_mm_y", 5.0)

        def flow_from_the_sea(world: dict) -> None:
            cell = next(cell for cell in world["cells"] if cell["is_water"])
            self.assign(cell, "flow_to", int(cell["neighbors"][0]))

        def flow_to_a_stranger(world: dict) -> None:
            cell = next(
                cell
                for cell in world["cells"]
                if not cell["is_water"] and cell["flow_to"] >= 0
            )
            neighbors = set(cell["neighbors"]) | {int(cell["id"])}
            stranger = next(
                other["id"] for other in world["cells"] if other["id"] not in neighbors
            )
            self.assign(cell, "flow_to", int(stranger))

        def flow_uphill(world: dict) -> None:
            cell = next(
                cell
                for cell in world["cells"]
                if not cell["is_water"] and cell["flow_to"] >= 0
            )
            self.assign(cell, "hydrologic_surface_elevation_m", -9999.0)

        def claim_a_dry_river(world: dict) -> None:
            cell = next(
                cell
                for cell in world["cells"]
                if not cell["is_water"]
                and not cell["is_river"]
                and cell["runoff_mm_y"] <= 10.0
            )
            self.assign(cell, "is_river", True)

        self.run_cases(
            (
                (
                    "monthly climate array is not twelve values",
                    lambda world: self.assign(
                        world["cells"][0], "temperature_monthly_c", [1.0]
                    ),
                    "climate",
                    "monthly_annual_climate_closure",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_cell_count"], 1
                    ),
                ),
                (
                    "energy record is not an object",
                    lambda world: self.append(
                        world["climate_energy_balance_records"], "not-a-record"
                    ),
                    "climate",
                    "climate_energy_record_coverage",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_record_count"], 1
                    ),
                ),
                (
                    "energy record cell id is not coercible",
                    lambda world: self.assign(
                        world["climate_energy_balance_records"][0], "cell_id", {}
                    ),
                    "climate",
                    "climate_energy_record_coverage",
                    lambda check: self.assertEqual(
                        check["observed"]["unique_cell_count"], 127
                    ),
                ),
                (
                    "energy record temperature drifts from its cell",
                    lambda world: self.assign(
                        world["climate_energy_balance_records"][0],
                        "temperature_c",
                        world["climate_energy_balance_records"][0]["temperature_c"]
                        + 5.0,
                    ),
                    "climate",
                    "climate_energy_record_coverage",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_record_count"], 1
                    ),
                ),
                (
                    "energy ledger replaced by a mapping",
                    lambda world: self.assign(
                        world, "climate_energy_balance_records", {}
                    ),
                    "climate",
                    "climate_energy_record_coverage",
                    lambda check: self.assertIsNone(check["observed"]["record_count"]),
                ),
                (
                    "groundwater outflow has no valid receiver",
                    break_groundwater_link,
                    "hydrology",
                    "groundwater_partition_closure",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_groundwater_link_count"], 1
                    ),
                ),
                (
                    "marine cell carries groundwater recharge",
                    wet_the_seafloor,
                    "hydrology",
                    "groundwater_partition_closure",
                    lambda check: self.assertEqual(
                        check["observed"]["marine_nonzero_groundwater_count"], 1
                    ),
                ),
                (
                    "flow target is not an integer",
                    lambda world: self.assign(world["cells"][0], "flow_to", "downhill"),
                    "hydrology",
                    "acyclic_downhill_drainage",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_target_count"], 1
                    ),
                ),
                (
                    "marine cell routes surface flow",
                    flow_from_the_sea,
                    "hydrology",
                    "acyclic_downhill_drainage",
                    lambda check: self.assertEqual(
                        (
                            check["observed"]["invalid_target_count"],
                            check["observed"]["cycle_cell_count"],
                        ),
                        (1, 2),
                    ),
                ),
                (
                    "flow target is not adjacent",
                    flow_to_a_stranger,
                    "hydrology",
                    "acyclic_downhill_drainage",
                    lambda check: self.assertEqual(
                        check["observed"]["nonneighbor_link_count"], 1
                    ),
                ),
                (
                    "flow target is not downhill",
                    flow_uphill,
                    "hydrology",
                    "acyclic_downhill_drainage",
                    lambda check: self.assertEqual(
                        check["observed"]["uphill_link_count"], 1
                    ),
                ),
                (
                    "river flag on a cell without river runoff",
                    claim_a_dry_river,
                    "hydrology",
                    "acyclic_downhill_drainage",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_river_cell_count"], 1
                    ),
                ),
            )
        )

    def test_sediment_ledger_violations_are_reported(self) -> None:
        def assert_nan_residual(check: dict, key: str) -> None:
            self.assertTrue(
                math.isnan(check["evidence"]["reconstructed_residuals"][key]),
                check["evidence"]["reconstructed_residuals"][key],
            )

        self.run_cases(
            (
                (
                    "transport model is not an object",
                    lambda world: self.assign(
                        world, "hillslope_sediment_transport_model", "gone"
                    ),
                    "sediment",
                    "sediment_mass_conservation",
                    lambda check: self.assertEqual(
                        check["observed"]["missing_required_residuals"],
                        [
                            "hillslope_sediment_transport_model."
                            "total_mass_balance_residual_km3"
                        ],
                    ),
                ),
                (
                    "stage history volume is not a number",
                    lambda world: self.assign(
                        world["hillslope_sediment_transport_history"][0],
                        "production_volume_km3",
                        None,
                    ),
                    "sediment",
                    "sediment_mass_conservation",
                    lambda check: assert_nan_residual(
                        check,
                        "hillslope_sediment_transport_history.production_volume_km3",
                    ),
                ),
                (
                    "numeric breach history replaced by a mapping",
                    lambda world: self.assign(
                        world, "numeric_depression_correction_history", {}
                    ),
                    "sediment",
                    "sediment_mass_conservation",
                    lambda check: assert_nan_residual(check, "numeric_history_gross"),
                ),
            )
        )

    def test_cryosphere_soil_and_biome_violations_are_reported(self) -> None:
        def unassigned_ice(world: dict) -> None:
            cell = next(
                cell
                for cell in world["cells"]
                if not cell["is_water"]
                and cell["ice_thickness_m"] <= 25.0
                and int(cell["ice_sheet_id"]) == -1
            )
            self.assign(cell, "ice_thickness_m", 400.0)

        def glacier_without_ice(world: dict) -> None:
            cell = next(
                cell for cell in world["cells"] if cell["ice_thickness_m"] <= 0.0
            )
            self.assign(cell, "glacier_flow_to", int(cell["neighbors"][0]))

        self.run_cases(
            (
                (
                    "thick ice belongs to no ice sheet",
                    unassigned_ice,
                    "cryosphere",
                    "ice_sheet_and_flow_coherence",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_ice_cell_count"], 1
                    ),
                ),
                (
                    "glacier target is not an integer",
                    lambda world: self.assign(
                        world["cells"][0], "glacier_flow_to", "downhill"
                    ),
                    "cryosphere",
                    "ice_sheet_and_flow_coherence",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_glacier_link_count"], 1
                    ),
                ),
                (
                    "glacier flows from a cell holding no ice",
                    glacier_without_ice,
                    "cryosphere",
                    "ice_sheet_and_flow_coherence",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_glacier_link_count"], 1
                    ),
                ),
                (
                    "ice sheet aggregate contradicts its member cells",
                    lambda world: self.assign(
                        world["ice_sheets"][0],
                        "cell_count",
                        int(world["ice_sheets"][0]["cell_count"]) + 7,
                    ),
                    "cryosphere",
                    "ice_sheet_and_flow_coherence",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_ice_sheet_record_count"], 1
                    ),
                ),
                (
                    "soil profile record is not an object",
                    lambda world: self.append(world["soil_profiles"], "not-a-profile"),
                    "soil_biome",
                    "soil_profile_coverage_and_bounds",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_profile_count"], 1
                    ),
                ),
                (
                    "soil profile cell id is not coercible",
                    lambda world: self.assign(
                        world["soil_profiles"][0], "cell_id", {}
                    ),
                    "soil_biome",
                    "soil_profile_coverage_and_bounds",
                    lambda check: self.assertEqual(
                        check["observed"]["profile_cell_count"], 46
                    ),
                ),
                (
                    "soil pH outside the physical scale",
                    lambda world: self.assign(world["soil_profiles"][0], "ph", 20.0),
                    "soil_biome",
                    "soil_profile_coverage_and_bounds",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_profile_count"], 1
                    ),
                ),
                (
                    "soil profile ledger replaced by a mapping",
                    lambda world: self.assign(world, "soil_profiles", {}),
                    "soil_biome",
                    "soil_profile_coverage_and_bounds",
                    lambda check: self.assertEqual(
                        check["observed"]["profile_cell_count"], 0
                    ),
                ),
                (
                    "biome diagnostic is not an object",
                    lambda world: self.append(
                        world["biome_diagnostics"], "not-a-diagnostic"
                    ),
                    "soil_biome",
                    "biome_diagnostic_coverage",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_diagnostic_count"], 1
                    ),
                ),
                (
                    "biome diagnostic cell id is not coercible",
                    lambda world: self.assign(
                        world["biome_diagnostics"][0], "cell_id", {}
                    ),
                    "soil_biome",
                    "biome_diagnostic_coverage",
                    lambda check: self.assertEqual(
                        check["observed"]["diagnostic_cell_count"], 127
                    ),
                ),
                (
                    "biome confidence outside the unit interval",
                    lambda world: self.assign(
                        world["biome_diagnostics"][0], "biome_confidence_index", 2.0
                    ),
                    "soil_biome",
                    "biome_diagnostic_coverage",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_diagnostic_count"], 1
                    ),
                ),
                (
                    "biome diagnostic ledger replaced by a mapping",
                    lambda world: self.assign(world, "biome_diagnostics", {}),
                    "soil_biome",
                    "biome_diagnostic_coverage",
                    lambda check: self.assertEqual(
                        check["observed"]["diagnostic_cell_count"], 0
                    ),
                ),
            )
        )

    def test_resource_graph_and_boundary_violations_are_reported(self) -> None:
        self.run_cases(
            (
                (
                    "deposit record is not an object",
                    lambda world: self.append(
                        world["resource_deposits"], "not-a-deposit"
                    ),
                    "natural_resources",
                    "deposit_and_commodity_linkage",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_deposit_count"], 1
                    ),
                ),
                (
                    "deposit index outside the unit interval",
                    lambda world: self.assign(
                        world["resource_deposits"][0], "reserve_potential_index", 2.0
                    ),
                    "natural_resources",
                    "deposit_and_commodity_linkage",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_deposit_count"], 1
                    ),
                ),
                (
                    "deposit ledger replaced by a mapping",
                    lambda world: self.assign(world, "resource_deposits", {}),
                    "natural_resources",
                    "deposit_and_commodity_linkage",
                    lambda check: self.assertEqual(
                        check["observed"]["deposit_count"], 0
                    ),
                ),
                (
                    "commodity ledger replaced by a mapping",
                    lambda world: self.assign(world, "commodity_occurrences", {}),
                    "natural_resources",
                    "deposit_and_commodity_linkage",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_commodity_link_count"], 1
                    ),
                ),
                (
                    "graph node is not an object",
                    lambda world: self.append(
                        world["plate_graph"]["nodes"], "not-a-node"
                    ),
                    "natural_graphs",
                    "physical_graph_coverage",
                    lambda check: self.assert_only_plate_graph_broke(
                        check, invalid_edge_semantics=0
                    ),
                ),
                (
                    "graph node id is not coercible",
                    lambda world: self.assign(
                        world["plate_graph"]["nodes"][0], "id", {}
                    ),
                    "natural_graphs",
                    "physical_graph_coverage",
                    lambda check: self.assert_only_plate_graph_broke(
                        check, invalid_edge_semantics=0
                    ),
                ),
                (
                    "graph edge is not an object",
                    lambda world: self.append(
                        world["plate_graph"]["edges"], "not-an-edge"
                    ),
                    "natural_graphs",
                    "physical_graph_coverage",
                    lambda check: self.assert_only_plate_graph_broke(
                        check, invalid_edge_semantics=0
                    ),
                ),
                (
                    "graph edge endpoint is not coercible",
                    lambda world: self.assign(
                        world["plate_graph"]["edges"][0], "plate_a", {}
                    ),
                    "natural_graphs",
                    "physical_graph_coverage",
                    lambda check: self.assert_only_plate_graph_broke(
                        check, invalid_edge_semantics=0
                    ),
                ),
                (
                    "graph edge joins a node to itself",
                    lambda world: self.assign(
                        world["plate_graph"]["edges"][0],
                        "plate_b",
                        world["plate_graph"]["edges"][0]["plate_a"],
                    ),
                    "natural_graphs",
                    "physical_graph_coverage",
                    lambda check: self.assertEqual(
                        check["observed"]["plate_graph"]["invalid_edge_semantics_count"],
                        1,
                    ),
                ),
                (
                    "boundary segment is not an object",
                    lambda world: self.append(
                        world["watershed_boundary_segments"], "not-a-segment"
                    ),
                    "natural_graphs",
                    "watershed_boundary_ledger",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_segment_count"], 2
                    ),
                ),
                (
                    "boundary segment length is not coercible",
                    lambda world: self.assign(
                        world["watershed_boundary_segments"][0], "length_km", {}
                    ),
                    "natural_graphs",
                    "watershed_boundary_ledger",
                    lambda check: self.assertEqual(
                        (
                            check["observed"]["recorded_segment_count"],
                            check["observed"]["invalid_segment_count"],
                        ),
                        (132, 2),
                    ),
                ),
                (
                    "boundary segment quality outside the unit interval",
                    lambda world: self.assign(
                        world["watershed_boundary_segments"][0],
                        "boundary_segment_quality",
                        2.0,
                    ),
                    "natural_graphs",
                    "watershed_boundary_ledger",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_segment_count"], 1
                    ),
                ),
                (
                    "boundary segment ids are not a dense range",
                    lambda world: self.assign(
                        world["watershed_boundary_segments"][0], "id", 99999
                    ),
                    "natural_graphs",
                    "watershed_boundary_ledger",
                    lambda check: self.assertEqual(
                        check["observed"]["invalid_segment_count"], 1
                    ),
                ),
                (
                    "boundary segment ledger replaced by a mapping",
                    lambda world: self.assign(
                        world, "watershed_boundary_segments", {}
                    ),
                    "natural_graphs",
                    "watershed_boundary_ledger",
                    lambda check: self.assertEqual(
                        (
                            check["observed"]["recorded_segment_count"],
                            check["observed"]["invalid_segment_count"],
                        ),
                        (0, 1),
                    ),
                ),
            )
        )

    def test_calibration_and_realism_evidence_violations_are_reported(self) -> None:
        self.run_cases(
            (
                (
                    "calibration record is not an object",
                    lambda world: self.replace_at(
                        world["calibration_checks"], 0, "not-a-record"
                    ),
                    "earth_calibration",
                    "built_in_calibration_integrity",
                    lambda check: self.assertEqual(
                        check["observed"]["metrics"],
                        _check(
                            self.control,
                            "earth_calibration",
                            "built_in_calibration_integrity",
                        )["observed"]["metrics"][1:],
                    ),
                ),
                (
                    "calibration ledger is empty",
                    lambda world: self.assign(world, "calibration_checks", []),
                    "earth_calibration",
                    "built_in_calibration_integrity",
                    lambda check: self.assertEqual(check["observed"]["metrics"], []),
                ),
            )
        )

    def test_damaged_realism_family_reports_a_check_a_clean_world_never_emits(
        self,
    ) -> None:
        empty_family = self.report_for(
            lambda world: self.assign(world, "biome_realism_checks", [])
        )
        text_record = self.report_for(
            lambda world: self.replace_at(
                world["planet_realism_checks"], 0, "not-a-record"
            )
        )

        missing = self.assert_newly_reported(
            empty_family, "realism_evidence_integrity", "biome_realism_checks_records"
        )
        self.assertEqual(missing["observed"], 0)
        self.assertEqual(missing["expected"], "non-empty list")
        self.assertFalse(
            any(
                check["name"].startswith("biome_realism_checks.")
                for check in empty_family["checks"]
            )
        )

        shape = self.assert_newly_reported(
            text_record, "realism_evidence_integrity", "planet_realism_checks.record_shape"
        )
        self.assertEqual(shape["observed"], "str")
        self.assertEqual(
            _check(
                text_record, "realism_evidence_integrity", "planet_realism_checks.registry"
            )["status"],
            "failed",
        )

    def test_empty_calibration_ledger_zeroes_the_reported_pass_fraction(self) -> None:
        self.assertGreater(self.control["metrics"]["calibration_pass_fraction"], 0.0)

        report = self.report_for(
            lambda world: self.assign(world, "calibration_checks", [])
        )
        mapping_report = self.report_for(
            lambda world: self.assign(world, "calibration_checks", {})
        )

        self.assertEqual(report["metrics"]["calibration_pass_fraction"], 0.0)
        self.assertEqual(mapping_report["metrics"]["calibration_pass_fraction"], 0.0)

    def test_realism_claim_without_object_evidence_is_not_applicable(self) -> None:
        name = "hydrology_realism_checks.river_terminal_sink_validity"

        report = self.report_for(
            lambda world: self.assign(
                world["hydrology_realism_checks"][0], "evidence", []
            )
        )

        integrity = self.assert_flipped(report, "realism_evidence_integrity", name)
        self.assertEqual(integrity["observed"]["declared_passed"], True)
        claim = _check(report, "realism_evidence", name)
        self.assertEqual(_check(self.control, "realism_evidence", name)["status"], "passed")
        self.assertEqual(claim["status"], "not_applicable")
        self.assertFalse(claim["passed"])
        self.assertIn("vacuous", claim["message"])

    def test_non_world_payload_shapes_fail_before_deep_validation(self) -> None:
        schema_version = worlds.cached_world_readonly(self.WORLD_KEY)["schema_version"]

        root = validate_geo_world("not-a-world")
        self.assertFalse(root["passed"])
        self.assertEqual(_check(root, "contract", "world_object")["observed"], "str")

        shell = validate_geo_world(
            {"schema_version": schema_version, "summary": [], "cells": []}
        )
        self.assertFalse(shell["passed"])
        self.assertEqual(
            _check(shell, "contract", "summary_object")["observed"], "list"
        )
        self.assertEqual(
            _check(shell, "contract", "cell_payload_available")["observed"], 0
        )
        self.assertEqual(
            _check(shell, "contract", "world_schema_version")["status"], "passed"
        )

        text_ids = validate_geo_world(
            {
                "schema_version": schema_version,
                "summary": {"cell_count": {}},
                "cells": [{"id": "first"}],
            }
        )
        self.assertFalse(text_ids["passed"])
        self.assertEqual(
            _check(text_ids, "contract", "cell_count")["observed"],
            {"summary": {}, "payload": 1},
        )
        self.assertEqual(
            _check(text_ids, "mesh", "unique_cell_ids")["observed"]["unique_id_count"],
            None,
        )
        self.assertFalse(
            any(check["domain"] == "hydrology" for check in text_ids["checks"])
        )

        missing_fields = validate_geo_world(
            {
                "schema_version": schema_version,
                "summary": {"cell_count": 1},
                "cells": [{"id": 0}],
            }
        )
        finite = _check(missing_fields, "contract", "finite_core_geo_fields")
        self.assertEqual(finite["status"], "failed")
        self.assertEqual(finite["observed"]["area_km2"], 1)
        self.assertEqual(
            _check(missing_fields, "mesh", "unique_cell_ids")["status"], "passed"
        )
        self.assertFalse(
            any(check["domain"] == "climate" for check in missing_fields["checks"])
        )

    def test_malformed_optional_payloads_are_reported_not_raised(self) -> None:
        cases = (
            (
                "planet parameters replaced by text",
                lambda world: self.assign(world, "planet_parameters", "nope"),
                "AttributeError",
            ),
            (
                "adjacency edge endpoint replaced by a mapping",
                lambda world: self.assign(
                    world["cell_adjacency_edges"][0], "cell_a_id", {}
                ),
                "TypeError",
            ),
            (
                "neighbor list replaced by text",
                lambda world: self.assign(
                    world["cells"][0], "neighbors", "not-a-list"
                ),
                "ValueError",
            ),
        )
        self.assertFalse(
            any(
                check["name"] == "malformed_optional_payload"
                for check in self.control["checks"]
            )
        )
        for label, mutate, exception_type in cases:
            with self.subTest(case=label):
                report = self.report_for(mutate)
                check = _check(report, "contract", "malformed_optional_payload")

                self.assertFalse(report["passed"])
                self.assertEqual(check["status"], "failed")
                self.assertEqual(check["observed"]["exception_type"], exception_type)
                self.assertTrue(check["observed"]["detail"])
                self.assertEqual(
                    check["expected"],
                    "all exported natural fields are type-safe and internally coherent",
                )

    def test_uncoercible_planet_parameter_falls_back_to_the_declared_default(
        self,
    ) -> None:
        world = self.world()
        self.assign(world["planet_parameters"], "radius_km", "wide")
        report = validate_geo_world(world)

        check = self.assert_flipped(
            report, "contract", "explicit_planet_and_physics_models"
        )
        # The key is still present and both physics models are still declared,
        # so the uncoercible value is the only clause left that can fail.
        self.assertTrue(check["observed"]["climate_model_present"])
        self.assertTrue(check["observed"]["sea_level_model_present"])
        self.assertIn("radius_km", check["observed"]["planet_parameter_keys"])
        # The radius reader still hands the declared 6371.0 km default to the
        # area closure instead of raising or reporting the text it was given.
        area = _check(report, "mesh", "spherical_surface_area_closure")
        self.assertEqual(world["planet_parameters"]["radius_km"], "wide")
        self.assertEqual(area["observed"]["radius_km"], 6371.0)
        self.assertEqual(area["status"], "passed")

    def test_earthlike_profile_adds_gates_a_generic_run_skips(self) -> None:
        def drain_the_ocean(world: dict) -> None:
            marine = [cell for cell in world["cells"] if cell["is_water"]]
            self.assertTrue(marine)
            for cell in marine:
                cell["is_water"] = False

        earthlike_control = validate_geo_world(
            worlds.cached_world_readonly(self.WORLD_KEY), profile="earthlike"
        )
        report = self.report_for(drain_the_ocean, profile="earthlike")

        self.assertFalse(
            any(check["domain"] == "earthlike_profile" for check in self.control["checks"])
        )
        self.assertEqual(
            _check(earthlike_control, "earthlike_profile", "ocean_fraction")["status"],
            "passed",
        )
        gate = _check(report, "earthlike_profile", "ocean_fraction")
        self.assertEqual(gate["status"], "failed")
        self.assertEqual(gate["observed"], 0.0)
        self.assertEqual(gate["expected"], {"minimum": 0.55, "maximum": 0.85})
        self.assertEqual(report["profile"], "earthlike")

    def test_unknown_profile_is_reported_as_a_failed_contract(self) -> None:
        report = validate_geo_world(
            worlds.cached_world_readonly(self.WORLD_KEY), profile="martian"
        )
        check = _check(report, "contract", "known_validation_profile")

        self.assertFalse(report["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertEqual(check["observed"], "martian")
        self.assertEqual(check["expected"], ["generic", "earthlike"])
        self.assertEqual(report["profile"], "martian")
        self.assertFalse(
            any(check["domain"] == "earthlike_profile" for check in report["checks"])
        )

    def test_extract_geo_metrics_degrades_on_partial_worlds(self) -> None:
        self.assertEqual(extract_geo_metrics({}), {"cell_count": 0})
        self.assertEqual(
            extract_geo_metrics({"cells": ["not-a-cell"]}), {"cell_count": 0}
        )

        partial = {
            "cells": [
                {"id": 0, "area_km2": 0.0, "elevation_m": 0.0, "temperature_c": 3.0},
                {"id": 1, "area_km2": 0.0, "elevation_m": 1.0, "temperature_c": 4.0},
            ],
            "geology_realism_checks": {"not": "a list"},
            "calibration_checks": ["not-a-record"],
        }
        ledgers = {
            "absent step-zero ledger": {},
            "step-zero record without a ledger": {"plate_motion_history": [{}]},
            "step-zero ledger with a truncated column": {
                "plate_motion_history": [
                    {"crust_overlap_ledger": {"remapped_crust_age_ma_by_cell": [1.0]}}
                ]
            },
        }
        for label, extra in ledgers.items():
            with self.subTest(case=label):
                metrics = extract_geo_metrics({**partial, **extra})

                self.assertEqual(metrics["cell_count"], 2)
                self.assertEqual(metrics["surface_area_km2"], 0.0)
                self.assertEqual(metrics["global_mean_temperature_c"], 0.0)
                self.assertEqual(metrics["crust_evolved_cell_fraction"], 0.0)
                self.assertEqual(metrics["mountain_convergent_alignment"], 0.0)
                self.assertEqual(metrics["calibration_pass_fraction"], 0.0)

        self.assertEqual(
            extract_geo_metrics({**partial, "calibration_checks": {}})[
                "calibration_pass_fraction"
            ],
            0.0,
        )
