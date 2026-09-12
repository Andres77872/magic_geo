from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.api import generate_geo_world
from magic_geo.config import WorldConfig, load_config
from magic_geo.geo_validation_physics import validate_physics_replays
from support import worlds


def _small_earth_config() -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    return WorldConfig.model_validate(data)


def _check(checks: list[dict], domain: str, name: str) -> dict:
    return next(
        check
        for check in checks
        if check["domain"] == domain and check["name"] == name
    )


class GeoPhysicsReplayValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(_small_earth_config())

    def test_generated_geo_world_passes_all_physics_replays(self) -> None:
        checks = validate_physics_replays(self.world)

        self.assertEqual(len(checks), 13)
        self.assertTrue(all(check["passed"] for check in checks))
        for index, check in enumerate(checks):
            self.assertEqual(check["id"], index)
            self.assertEqual(check["status"], "passed")
            self.assertEqual(check["severity"], "error")
            self.assertEqual(
                set(check),
                {
                    "id",
                    "domain",
                    "name",
                    "status",
                    "passed",
                    "severity",
                    "message",
                    "observed",
                    "expected",
                    "evidence",
                },
            )

    def test_zero_ocean_final_feedback_uses_numeric_not_count_semantics(self) -> None:
        data = _small_earth_config().model_dump(mode="python")
        data["planet"]["ocean_fraction_target"] = 0.0
        data["planet"]["ocean_water_inventory_km3"] = 0.0
        data["climate"]["precipitation_scale"] = 0.12
        world = generate_geo_world(WorldConfig.model_validate(data))

        check = _check(
            validate_physics_replays(world),
            "simulation",
            "coupled_stage_feedback_replay",
        )

        self.assertTrue(check["passed"], check["evidence"])

    def test_negative_plate_area_and_stale_means_fail_cell_replay(self) -> None:
        altered = deepcopy(self.world)
        altered["plates"][0]["area_km2"] = -1.0
        altered["plates"][0]["mean_crust_density"] = 99.0

        check = _check(
            validate_physics_replays(altered),
            "tectonics",
            "plate_aggregate_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertGreater(check["observed"]["violation_count"], 0)
        self.assertTrue(
            any(
                "area_km2" in violation or "mean_crust_density" in violation
                for violation in check["evidence"]["violations"]
            )
        )

    def test_boundary_segment_mutation_is_a_distinct_fatal_replay(self) -> None:
        altered = deepcopy(self.world)
        segment = altered["plate_motion_history"][0]["boundary_segments"][0]
        segment["midpoint_unit_x"] += 0.001

        check = _check(
            validate_physics_replays(altered),
            "tectonics",
            "exact_directed_plate_boundary_segment_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertIn("reciprocal control-volume segment", check["message"])
        self.assertTrue(check["evidence"]["violations"])

    def test_boundary_candidate_cannot_be_promoted_to_physical_polarity(self) -> None:
        altered = deepcopy(self.world)
        segment = next(
            record
            for step in altered["plate_motion_history"]
            for record in step["boundary_segments"]
            if record["direct_boundary_class"] == "convergent"
        )
        segment["physical_polarity_source"] = "oceanic_side_candidate"
        segment["physical_polarity_confidence"] = 1.0e-13

        check = _check(
            validate_physics_replays(altered),
            "tectonics",
            "exact_directed_plate_boundary_segment_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertTrue(check["evidence"]["violations"])

    def test_overlap_candidate_fate_mutation_is_a_distinct_fatal_replay(self) -> None:
        altered = deepcopy(self.world)
        record = next(
            candidate
            for step in altered["plate_motion_history"]
            for candidate in step["crust_overlap_candidate_fate_ledger"][
                "overlap_class_candidates"
            ]
        )
        record["membership_area_class_id"] += 1

        check = _check(
            validate_physics_replays(altered),
            "tectonics",
            "overlap_candidate_fate_crosswalk_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertIn("diagnostic overlap-excess partition", check["message"])
        self.assertTrue(check["evidence"]["violations"])

    def test_oceanic_age_depth_mutation_is_a_distinct_fatal_replay(self) -> None:
        altered = deepcopy(self.world)
        altered["plate_motion_history"][-1][
            "post_process_local_thermal_subsidence_target_m"
        ][0] += 1.0e-6

        check = _check(
            validate_physics_replays(altered),
            "tectonics",
            "oceanic_age_depth_thermal_target_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertIn("equilibrium targets", check["message"])
        self.assertTrue(check["evidence"]["violations"])

    def test_initial_oceanic_age_mutation_is_a_distinct_fatal_replay(self) -> None:
        altered = deepcopy(self.world)
        altered["initial_oceanic_crust_age_ledger"]["age_ma_by_cell"][0] += 0.01

        check = _check(
            validate_physics_replays(altered),
            "tectonics",
            "initial_oceanic_crust_age_graph_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertIn("multi-source Dijkstra path witness", check["message"])
        self.assertTrue(check["evidence"]["violations"])

    def test_colluding_negative_legacy_energy_mirrors_fail_equation_replay(self) -> None:
        # These fields belong to the preserved posthoc graybody model.
        altered = worlds.cached_legacy_world("energy_128")
        record = altered["climate_energy_balance_records"][0]
        cell_id = record["cell_id"]
        cell = next(cell for cell in altered["cells"] if cell["id"] == cell_id)
        previous = record["absorbed_shortwave_w_m2"]
        record["absorbed_shortwave_w_m2"] = -100.0
        cell["absorbed_shortwave_w_m2"] = -100.0
        altered["summary"]["mean_absorbed_shortwave_w_m2"] += (
            -100.0 - previous
        ) / len(altered["cells"])

        check = _check(
            validate_physics_replays(altered),
            "climate",
            "climate_energy_balance_replay",
        )

        self.assertFalse(check["passed"])
        self.assertTrue(
            any(
                "absorbed_shortwave_w_m2" in violation
                or "negative energy flux" in violation
                for violation in check["evidence"]["violations"]
            )
        )

    def test_incomplete_feedback_record_fails_structure_even_when_length_matches(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["earth_system_feedback_history"][1].pop("stage")

        check = _check(
            validate_physics_replays(altered),
            "simulation",
            "coupled_stage_feedback_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(
            check["observed"]["feedback_record_count"],
            altered["simulation_clock"]["stage_count"],
        )
        self.assertTrue(
            any(
                "missing fields" in violation
                for violation in check["evidence"]["violations"]
            )
        )

    def test_feedback_summary_and_clock_counter_mutations_fail_mirror_replay(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["summary"]["simulation_clock_stage_count"] += 1
        altered["simulation_clock"]["feedback_recompute_count"] += 1

        check = _check(
            validate_physics_replays(altered),
            "simulation",
            "coupled_stage_summary_mirrors",
        )

        self.assertFalse(check["passed"])
        self.assertGreaterEqual(check["observed"]["violation_count"], 2)

    def test_process_order_and_reference_erosion_mutations_fail(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["simulation_clock"]["iteration_process_order"] = "tampered"
        altered["simulation_clock"][
            "erosion_transition_coupling_semantics"
        ] = "tampered"
        altered["earth_system_feedback_history"][-1][
            "mean_stream_power_response_m_per_reference_step"
        ] += 1.0

        check = _check(
            validate_physics_replays(altered),
            "simulation",
            "coupled_stage_feedback_replay",
        )

        self.assertFalse(check["passed"])
        self.assertGreaterEqual(check["observed"]["violation_count"], 2)

    def test_crust_material_shadow_mutation_is_a_distinct_fatal_replay(self) -> None:
        altered = deepcopy(self.world)
        masses = altered["crust_material_shadow_history"][0][
            "opening_packets"
        ]["dry_rock_mass_kg"]
        masses[0] += max(1.0, abs(masses[0]) * 1.0e-8)

        check = _check(
            validate_physics_replays(altered),
            "tectonics",
            "persistent_crust_material_shadow_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertIn("diagnostic shadow", check["message"])
        self.assertTrue(check["evidence"]["violations"])

    def test_finite_crust_accounting_mutation_is_a_distinct_fatal_replay(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["crust_dry_rock_accounting_model"][
            "upper_mantle_exchange_reservoir_resolved"
        ] = True

        check = _check(
            validate_physics_replays(altered),
            "tectonics",
            "finite_crust_dry_rock_accounting_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertIn("counter-model", check["message"])
        self.assertTrue(check["evidence"]["violations"])

    def test_sediment_partition_mutation_is_a_distinct_fatal_replay(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["fluvial_sediment_routing_model"][
            "source_partition_audit_is_mass_claim"
        ] = True

        check = _check(
            validate_physics_replays(altered),
            "sediment",
            "sediment_alluvium_bedrock_source_partition_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertIn("non-mass", check["message"])
        self.assertTrue(check["evidence"]["violations"])

    def test_sediment_interface_mutation_is_a_distinct_fatal_replay(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        altered["cells"][0]["bedrock_surface_elevation_m"] += 0.01
        altered["cells"][0]["elevation_m"] += 0.01

        check = _check(
            validate_physics_replays(altered),
            "sediment",
            "bedrock_mobile_sediment_interface_replay",
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["status"], "failed")
        self.assertIn("canonical bedrock surface", check["message"])
        self.assertTrue(check["evidence"]["violations"])

    def test_malformed_root_is_reported_without_conversion_errors(self) -> None:
        checks = validate_physics_replays({"cells": "not-a-list"})

        self.assertEqual(len(checks), 13)
        self.assertTrue(all(not check["passed"] for check in checks))


WORLD_KEY = "replay_128"

PLATE_AGGREGATE = ("tectonics", "plate_aggregate_replay")
CLIMATE_ENERGY = ("climate", "climate_energy_balance_replay")
FEEDBACK_REPLAY = ("simulation", "coupled_stage_feedback_replay")
SUMMARY_MIRRORS = ("simulation", "coupled_stage_summary_mirrors")


class GeoPhysicsReplayViolationTests(TestCase):
    """One tamper at a time, each flipping a single named replay check.

    Every table starts from an untampered control assertion, so a failure is
    always attributable to the tamper rather than to a broken fixture, and every
    tamper goes through :meth:`set_field`/:meth:`pop_field`, which refuse to
    write a value the generator already produced.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.control = validate_physics_replays(worlds.cached_world(WORLD_KEY))

    # ----------------------------------------------------------------- tools
    def set_field(self, container: dict, key: str, value: object) -> None:
        self.assertIn(key, container, f"{key} is not a pre-existing field")
        self.assertNotEqual(
            container[key], value, f"tampering {key} with {value!r} is a no-op"
        )
        container[key] = value

    def pop_field(self, container: dict, key: str) -> None:
        self.assertIn(key, container, f"{key} is not a pre-existing field")
        del container[key]

    def assert_tampers_fail(self, target, cases, *, legacy_energy=False) -> None:
        domain, name = target
        source = (
            lambda: worlds.cached_legacy_world("energy_128")
        ) if legacy_energy else lambda: worlds.cached_world(WORLD_KEY)
        controls = validate_physics_replays(source()) if legacy_energy else self.control
        control = _check(controls, domain, name)
        self.assertTrue(control["passed"], control["evidence"])
        self.assertFalse(control["evidence"]["violations"])

        for label, mutate, fragments in cases:
            with self.subTest(label):
                world = source()
                mutate(world)
                check = _check(validate_physics_replays(world), domain, name)
                self.assertFalse(check["passed"], label)
                self.assertEqual(check["status"], "failed")
                violations = check["evidence"]["violations"]
                for fragment in fragments:
                    self.assertTrue(
                        any(fragment in violation for violation in violations),
                        f"{label}: {fragment!r} missing from {violations}",
                    )

    @staticmethod
    def _ocean_cell(world: dict) -> dict:
        return next(
            cell
            for cell in world["cells"]
            if cell.get("is_water") and cell.get("water_body_type") == "ocean"
        )

    @classmethod
    def _legacy_ocean_record_index(cls) -> tuple[int, int]:
        """``(cell id, energy-record index)`` of the first open-ocean cell.

        Read from the shared world so the tamper table can name the exact
        record the violation must carry; ``energy_128`` is deterministic, and
        the tamper itself still runs against a private deep copy.
        """
        shared = worlds.cached_legacy_world_readonly("energy_128")
        cell_id = cls._ocean_cell(shared)["id"]
        index = next(
            index
            for index, record in enumerate(shared["climate_energy_balance_records"])
            if record["cell_id"] == cell_id
        )
        return cell_id, index

    # ------------------------------------------------- plate aggregate inputs
    def test_cell_level_tampers_fail_plate_aggregate_replay(self) -> None:
        def unknown_plate(world: dict) -> None:
            self.set_field(world["cells"][0], "plate_id", 999)

        def non_finite_input(world: dict) -> None:
            self.set_field(world["cells"][0], "crust_age_ma", None)

        self.assert_tampers_fail(
            PLATE_AGGREGATE,
            [
                (
                    "unknown plate id drops the cell from every aggregate",
                    unknown_plate,
                    (
                        "cell[0] has unknown plate_id 999",
                        "plate areas do not cover the cell surface",
                    ),
                ),
                (
                    "non-finite aggregate input",
                    non_finite_input,
                    ("cell[0] has non-finite plate aggregate inputs",),
                ),
                (
                    "out-of-range boundary fraction",
                    lambda world: self.set_field(
                        world["cells"][0], "boundary_convergent", 1.5
                    ),
                    ("cell[0] has out-of-range plate aggregate inputs",),
                ),
                (
                    "unknown crust type",
                    lambda world: self.set_field(
                        world["cells"][0], "crust_type", "tampered_crust"
                    ),
                    ("cell[0] has unknown crust_type",),
                ),
                (
                    "unknown lithology",
                    lambda world: self.set_field(
                        world["cells"][0], "lithology", "tampered_lithology"
                    ),
                    ("cell[0] has unknown lithology",),
                ),
                (
                    "negative planet internal heat",
                    lambda world: self.set_field(
                        world["planet_parameters"], "internal_heat", -1.0
                    ),
                    ("planet internal_heat is not nonnegative",),
                ),
            ],
        )

    def test_plate_identity_tampers_fail_plate_aggregate_replay(self) -> None:
        def non_integer_id(world: dict) -> None:
            self.set_field(world["plates"][0], "id", "zero")

        def swapped_ids(world: dict) -> None:
            self.set_field(world["plates"][0], "id", 1)
            self.set_field(world["plates"][1], "id", 0)

        self.assert_tampers_fail(
            PLATE_AGGREGATE,
            [
                (
                    "non-integer plate id is unaggregatable",
                    non_integer_id,
                    ("plate[0] id is not an integer", "plate[0] cannot be aggregated"),
                ),
                (
                    "swapped plate ids are no longer sequential",
                    swapped_ids,
                    ("plate[0] id 1 is not sequential",),
                ),
                (
                    "duplicated plate id",
                    lambda world: self.set_field(world["plates"][1], "id", 0),
                    ("plate ids are duplicated",),
                ),
                (
                    "missing plate field",
                    lambda world: self.pop_field(world["plates"][0], "thermal_state"),
                    ("plate[0] is missing fields: thermal_state",),
                ),
            ],
        )

    def test_plate_field_tampers_fail_plate_aggregate_replay(self) -> None:
        self.assert_tampers_fail(
            PLATE_AGGREGATE,
            [
                (
                    "invalid plate kind",
                    lambda world: self.set_field(
                        world["plates"][0], "kind", "tampered_kind"
                    ),
                    ("plate[0] kind is invalid",),
                ),
                (
                    "axis with two components",
                    lambda world: self.set_field(
                        world["plates"][0], "axis", [1.0, 0.0]
                    ),
                    ("plate[0] axis is not a unit vector",),
                ),
                (
                    "axis with a non-numeric component",
                    lambda world: self.set_field(
                        world["plates"][0], "axis", ["x", 0.0, 1.0]
                    ),
                    ("plate[0] axis is not a unit vector",),
                ),
                (
                    "axis that is not normalized",
                    lambda world: self.set_field(
                        world["plates"][0], "axis", [0.0, 0.0, 0.0]
                    ),
                    ("plate[0] axis is not a unit vector",),
                ),
                (
                    "negative cumulative rotation",
                    lambda world: self.set_field(
                        world["plates"][0], "cumulative_rotation_deg", -1.0
                    ),
                    ("plate[0] cumulative_rotation_deg is not finite and nonnegative",),
                ),
                (
                    "mean crust age older than the planet",
                    lambda world: self.set_field(
                        world["plates"][0], "mean_crust_age_ma", 1.0e7
                    ),
                    ("plate[0] mean crust age exceeds planet age",),
                ),
                (
                    "boundary activity above one",
                    lambda world: self.set_field(
                        world["plates"][0], "mean_boundary_activity", 2.0
                    ),
                    ("plate[0] mean boundary activity is out of range",),
                ),
                (
                    "heat flow above the physical clamp",
                    lambda world: self.set_field(
                        world["plates"][0], "mean_heat_flow_mw_m2", 300.0
                    ),
                    ("plate[0] heat flow is out of range",),
                ),
                (
                    "cell count that no longer counts member cells",
                    lambda world: self.set_field(
                        world["plates"][0],
                        "cell_count",
                        world["plates"][0]["cell_count"] + 1,
                    ),
                    ("plate[0] cell_count does not match member cells",),
                ),
                (
                    "dominant crust type that is not the area maximum",
                    lambda world: self.set_field(
                        world["plates"][0], "dominant_crust_type", "craton"
                    ),
                    ("plate[0] dominant crust type is inconsistent",),
                ),
                (
                    "dominant lithology that is not the area maximum",
                    lambda world: self.set_field(
                        world["plates"][0], "dominant_lithology", "shale"
                    ),
                    ("plate[0] dominant lithology is inconsistent",),
                ),
                (
                    "thermal state that does not follow the heat flow",
                    lambda world: self.set_field(
                        world["plates"][0], "thermal_state", "cool_stable"
                    ),
                    ("plate[0] thermal_state is inconsistent",),
                ),
            ],
        )

    # ------------------------------------------------------- climate energy
    def test_cell_tampers_fail_legacy_climate_energy_replay(self) -> None:
        def duplicate_cell_id(world: dict) -> None:
            self.set_field(world["cells"][1], "id", world["cells"][0]["id"])

        def empty_monthly_temperature(world: dict) -> None:
            self.set_field(world["cells"][0], "temperature_monthly_c", [])

        def missing_latitude(world: dict) -> None:
            self.pop_field(world["cells"][0], "lat_deg")

        def lake_water_body(world: dict) -> None:
            self.set_field(self._ocean_cell(world), "water_body_type", "fresh_lake")

        ocean_cell_id, ocean_record_index = self._legacy_ocean_record_index()

        self.assert_tampers_fail(
            CLIMATE_ENERGY,
            [
                (
                    "duplicate cell id",
                    duplicate_cell_id,
                    ("cell[1] has invalid or duplicate id",),
                ),
                (
                    "monthly temperature series of a different length",
                    empty_monthly_temperature,
                    ("cell[0] monthly temperature coverage is inconsistent",),
                ),
                (
                    "missing latitude raises inside the replay",
                    missing_latitude,
                    ("cell 0 has invalid climate-energy inputs",),
                ),
                (
                    "non-finite latitude",
                    lambda world: self.set_field(
                        world["cells"][0], "lat_deg", float("nan")
                    ),
                    ("cell 0 has non-finite climate-energy inputs",),
                ),
                (
                    "ocean cell relabelled as a lake changes its albedo regime",
                    lake_water_body,
                    (
                        f"energy record[{ocean_record_index}] water body type "
                        "is stale",
                        f"energy record[{ocean_record_index}] albedo regime is "
                        "inconsistent",
                        f"cell {ocean_cell_id} surface_albedo_regime is "
                        "inconsistent",
                    ),
                ),
            ],
            legacy_energy=True,
        )

    def test_record_tampers_fail_legacy_climate_energy_replay(self) -> None:
        def non_object_record(world: dict) -> None:
            records = world["climate_energy_balance_records"]
            self.assertIsInstance(records[0], dict)
            records[0] = "not-an-object"

        def duplicate_record_cell_id(world: dict) -> None:
            records = world["climate_energy_balance_records"]
            self.set_field(records[1], "cell_id", records[0]["cell_id"])

        def perturbed_monthly_insolation(world: dict) -> None:
            monthly = world["climate_energy_balance_records"][0][
                "monthly_top_of_atmosphere_insolation_w_m2"
            ]
            before = monthly[0]
            monthly[0] += 1.0
            self.assertNotEqual(monthly[0], before, "perturbation is a no-op")

        def negative_monthly_insolation(world: dict) -> None:
            monthly = world["climate_energy_balance_records"][0][
                "monthly_top_of_atmosphere_insolation_w_m2"
            ]
            # Polar night is physically zero; a negative flux is invalid in
            # either daylight or darkness.
            self.assertGreaterEqual(monthly[0], 0.0)
            monthly[0] = -1.0

        def dropped_record(world: dict) -> None:
            records = world["climate_energy_balance_records"]
            self.assertEqual(len(records), len(world["cells"]))
            records.pop()

        self.assert_tampers_fail(
            CLIMATE_ENERGY,
            [
                (
                    "record that is not an object",
                    non_object_record,
                    ("energy record[0] is not an object",),
                ),
                (
                    "record missing a required field",
                    lambda world: self.pop_field(
                        world["climate_energy_balance_records"][0],
                        "greenhouse_trapping_w_m2",
                    ),
                    ("energy record[0] is missing fields: greenhouse_trapping_w_m2",),
                ),
                (
                    "record id that is not sequential",
                    lambda world: self.set_field(
                        world["climate_energy_balance_records"][0], "id", 99
                    ),
                    ("energy record[0] id is not sequential",),
                ),
                (
                    "duplicate record cell id",
                    duplicate_record_cell_id,
                    ("energy record[1] has invalid or duplicate cell_id",),
                ),
                (
                    "record pointing at no cell",
                    lambda world: self.set_field(
                        world["climate_energy_balance_records"][0], "cell_id", 1000000
                    ),
                    ("energy record[0] does not reference a valid cell",),
                ),
                (
                    "stale biome mirror",
                    lambda world: self.set_field(
                        world["climate_energy_balance_records"][0],
                        "biome",
                        "tampered_biome",
                    ),
                    ("energy record[0] biome is stale",),
                ),
                (
                    "negative monthly insolation",
                    negative_monthly_insolation,
                    ("energy record[0] monthly insolation is invalid",),
                ),
                (
                    "monthly insolation that does not replay",
                    perturbed_monthly_insolation,
                    ("energy record[0] monthly insolation does not replay",),
                ),
                (
                    "albedo index outside the unit interval",
                    lambda world: self.set_field(
                        world["climate_energy_balance_records"][0],
                        "surface_albedo_index",
                        5.0,
                    ),
                    ("energy record[0] surface_albedo_index is out of range",),
                ),
                (
                    "one cell left without a record",
                    dropped_record,
                    (
                        "energy records do not provide exactly one record for "
                        "every cell",
                    ),
                ),
            ],
            legacy_energy=True,
        )

    def test_current_cell_tampers_fail_native_energy_replay(self) -> None:
        self.assert_tampers_fail(
            CLIMATE_ENERGY,
            [
                (
                    "duplicate native cell ID",
                    lambda world: self.set_field(world["cells"][1], "id", world["cells"][0]["id"]),
                    ("cells: noncanonical ID coverage",),
                ),
                (
                    "incomplete native monthly temperature mirror",
                    lambda world: self.set_field(world["cells"][0], "temperature_monthly_c", []),
                    ("cell[0].temperature_monthly_c: expected 12 values",),
                ),
                (
                    "nonfinite native latitude source",
                    lambda world: self.set_field(world["cells"][0], "lat_deg", float("nan")),
                    ("cell[0].lat_deg: nonfinite number",),
                ),
            ],
        )

    def test_current_monthly_energy_cannot_be_replaced_by_colluding_negative_mirrors(self) -> None:
        def colluding_negative_flux(world: dict) -> None:
            record = world["climate_energy_balance_records"][0]
            record["monthly_absorbed_shortwave_w_m2"] = [-100.0] * 12
            cell = next(c for c in world["cells"] if c["id"] == record["cell_id"])
            self.set_field(cell, "annual_absorbed_shortwave_w_m2", -100.0)
            values = [c["annual_absorbed_shortwave_w_m2"] for c in world["cells"]]
            world["summary"]["cell_count_mean_annual_absorbed_shortwave_w_m2"] = sum(values) / len(values)
            areas = [r["area_m2"] for r in world["climate_energy_balance_records"]]
            world["summary"]["area_weighted_mean_annual_absorbed_shortwave_w_m2"] = sum(a*v for a,v in zip(areas, values)) / sum(areas)

        self.assert_tampers_fail(
            CLIMATE_ENERGY,
            [("native source defeats colluding record/cell/summary flux", colluding_negative_flux,
              ("monthly_absorbed_shortwave_w_m2",))],
        )

    # --------------------------------------------------- simulation clock
    def test_clock_tampers_fail_coupled_stage_feedback_replay(self) -> None:
        def elapsed_endpoint_still_shared(world: dict) -> None:
            clock = world["simulation_clock"]
            self.set_field(
                clock,
                "current_nominal_elapsed_time_ma",
                clock["current_nominal_elapsed_time_ma"] + 1.0,
            )

        def shorter_motion_history(world: dict) -> None:
            history = world["plate_motion_history"]
            self.assertGreater(len(history), 1)
            history.pop()

        self.assert_tampers_fail(
            FEEDBACK_REPLAY,
            [
                (
                    "clock missing a required field",
                    lambda world: self.pop_field(
                        world["simulation_clock"], "clock_limitation"
                    ),
                    ("simulation_clock is missing fields: clock_limitation",),
                ),
                (
                    "nominal timestep longer than the reference step",
                    lambda world: self.set_field(
                        world["simulation_clock"], "nominal_timestep_ma", 10.0
                    ),
                    (
                        "simulation clock nominal timestep exceeds the configured "
                        "reference step",
                    ),
                ),
                (
                    "maturation scale that is not the timestep ratio",
                    lambda world: self.set_field(
                        world["simulation_clock"], "maturation_timestep_scale", 0.5
                    ),
                    ("simulation clock maturation timestep scale does not replay",),
                ),
                (
                    "transition count that is not the erosion iteration count",
                    lambda world: self.set_field(
                        world["simulation_clock"], "nominal_timed_transition_count", 99
                    ),
                    (
                        "simulation clock nominal transition count does not match "
                        "erosion iterations",
                    ),
                ),
                (
                    "current elapsed time that is not timestep times transitions",
                    elapsed_endpoint_still_shared,
                    (
                        "simulation clock current_nominal_elapsed_time_ma does not "
                        "replay from timestep and transitions",
                    ),
                ),
                (
                    "motion history shorter than the erosion stages",
                    shorter_motion_history,
                    ("plate motion history length does not match erosion stages",),
                ),
            ],
        )

    def test_kinematic_model_tampers_fail_coupled_stage_feedback_replay(self) -> None:
        def scaled_motion(world: dict) -> None:
            model = world["plate_kinematic_model"]
            self.set_field(
                model,
                "motion_scale_deg_per_step",
                model["motion_scale_deg_per_step"] * 2.0 + 1.0,
            )

        def scaled_aging(world: dict) -> None:
            model = world["plate_kinematic_model"]
            self.set_field(
                model,
                "effective_oceanic_crust_aging_ma_per_step",
                model["effective_oceanic_crust_aging_ma_per_step"] + 1.0,
            )

        def shifted_clock_endpoint(world: dict) -> None:
            clock = world["simulation_clock"]
            self.set_field(
                clock,
                "final_nominal_elapsed_time_ma",
                clock["final_nominal_elapsed_time_ma"] + 1.0,
            )

        def extra_history_step(world: dict) -> None:
            model = world["plate_kinematic_model"]
            self.set_field(
                model, "history_step_count", model["history_step_count"] + 1
            )

        self.assert_tampers_fail(
            FEEDBACK_REPLAY,
            [
                (
                    "kinematic model replaced by a scalar",
                    lambda world: self.set_field(
                        world, "plate_kinematic_model", "not-an-object"
                    ),
                    ("plate_kinematic_model must be an object",),
                ),
                (
                    "kinematic model missing a required field",
                    lambda world: self.pop_field(
                        world["plate_kinematic_model"], "crust_density_unit"
                    ),
                    ("plate_kinematic_model is missing fields: crust_density_unit",),
                ),
                (
                    "kinematic model declaring another density unit",
                    lambda world: self.set_field(
                        world["plate_kinematic_model"], "crust_density_unit", "kg_m3"
                    ),
                    ("plate kinematic time metadata is invalid",),
                ),
                (
                    "kinematic nominal timestep that does not mirror the clock",
                    lambda world: self.set_field(
                        world["plate_kinematic_model"], "nominal_timestep_ma", 4.0
                    ),
                    ("plate kinematic nominal_timestep_ma does not mirror the clock",),
                ),
                (
                    "configured motion steps that do not mirror the clock",
                    lambda world: self.set_field(
                        world["plate_kinematic_model"],
                        "configured_motion_step_count",
                        99,
                    ),
                    (
                        "plate kinematic configured motion steps do not mirror the "
                        "clock",
                    ),
                ),
                (
                    "history step count that does not mirror motion history",
                    extra_history_step,
                    (
                        "plate kinematic history step count does not mirror motion "
                        "history",
                    ),
                ),
                (
                    "motion scale that is not the scaled reference",
                    scaled_motion,
                    (
                        "plate kinematic effective/reference motion scales do not "
                        "replay",
                    ),
                ),
                (
                    "oceanic aging that is not the scaled reference",
                    scaled_aging,
                    (
                        "plate kinematic effective/reference oceanic aging scales do "
                        "not replay",
                    ),
                ),
                (
                    "clock endpoint the process histories no longer share",
                    shifted_clock_endpoint,
                    ("nominal process histories do not share the clock endpoint",),
                ),
            ],
        )

    # --------------------------------------------------- nominal-time records
    def test_nominal_time_tampers_fail_coupled_stage_feedback_replay(self) -> None:
        label = "hillslope_sediment_transport_history[0]"

        def shifted_elapsed(world: dict) -> None:
            record = world["hillslope_sediment_transport_history"][0]
            self.set_field(
                record,
                "nominal_elapsed_time_ma",
                record["nominal_elapsed_time_ma"] + 1.0,
            )

        self.assert_tampers_fail(
            FEEDBACK_REPLAY,
            [
                (
                    "record missing a nominal-time field",
                    lambda world: self.pop_field(
                        world["hillslope_sediment_transport_history"][0],
                        "nominal_time_unit",
                    ),
                    (f"{label} is missing nominal-time fields: nominal_time_unit",),
                ),
                (
                    "record claiming another nominal-time role",
                    lambda world: self.set_field(
                        world["hillslope_sediment_transport_history"][0],
                        "nominal_time_role",
                        "tampered_role",
                    ),
                    (f"{label} nominal-time metadata is invalid",),
                ),
                (
                    "record elapsed time off its configured interval",
                    shifted_elapsed,
                    (
                        f"{label} nominal_elapsed_time_ma does not match its "
                        "configured nominal interval",
                    ),
                ),
                (
                    "advancing record that denies advancing",
                    lambda world: self.set_field(
                        world["hillslope_sediment_transport_history"][0],
                        "advances_nominal_time",
                        False,
                    ),
                    (
                        f"{label} advances_nominal_time does not match its interval "
                        "duration",
                    ),
                ),
                (
                    "record claiming calibrated nominal time",
                    lambda world: self.set_field(
                        world["hillslope_sediment_transport_history"][0],
                        "nominal_time_calibrated",
                        True,
                    ),
                    (f"{label} must not claim calibrated nominal time",),
                ),
                (
                    "record claiming resolved physical time",
                    lambda world: self.set_field(
                        world["hillslope_sediment_transport_history"][0],
                        "physical_time_resolved",
                        True,
                    ),
                    (f"{label} must not claim resolved physical time",),
                ),
            ],
        )

    # ------------------------------------------------- process history shapes
    def test_stage_end_history_tampers_fail_coupled_stage_feedback_replay(self) -> None:
        key = "hydrologic_water_budget_history"

        def non_monotonic_elapsed(world: dict) -> None:
            history = world[key]
            self.set_field(
                history[0], "feedback_stage_id", history[-1]["feedback_stage_id"]
            )

        def dropped_endpoint(world: dict) -> None:
            history = world[key]
            self.assertEqual(len(history), 8)
            history.pop()

        self.assert_tampers_fail(
            FEEDBACK_REPLAY,
            [
                (
                    "history replaced by a scalar",
                    lambda world: self.set_field(world, key, 5),
                    (f"{key} must be a list of objects",),
                ),
                (
                    "record id that is not sequential",
                    lambda world: self.set_field(world[key][0], "id", 4),
                    (f"{key}[0] id is not sequential",),
                ),
                (
                    "non-integer feedback stage id",
                    lambda world: self.set_field(
                        world[key][0], "feedback_stage_id", "one"
                    ),
                    (f"{key}[0] feedback stage id is invalid",),
                ),
                (
                    "feedback stage id past the configured clock",
                    lambda world: self.set_field(
                        world[key][0], "feedback_stage_id", 99
                    ),
                    (f"{key}[0] lies outside the configured nominal clock",),
                ),
                (
                    "stage name that is not the feedback stage",
                    lambda world: self.set_field(
                        world[key][0], "stage", "erosion_iteration"
                    ),
                    (f"{key}[0] stage does not match its feedback stage",),
                ),
                (
                    "erosion iteration that is not the feedback stage",
                    lambda world: self.set_field(world[key][0], "erosion_iteration", 4),
                    (f"{key}[0] erosion iteration does not match its feedback stage",),
                ),
                (
                    "final stage id replayed first",
                    non_monotonic_elapsed,
                    (f"{key} nominal elapsed time is not monotonic",),
                ),
                (
                    "missing cryosphere endpoint",
                    dropped_endpoint,
                    (f"{key} does not cover every configured feedback-stage endpoint",),
                ),
            ],
        )

    def test_interval_history_tampers_fail_coupled_stage_feedback_replay(self) -> None:
        key = "hillslope_sediment_transport_history"

        def dropped_interval(world: dict) -> None:
            history = world["fluvial_sediment_routing_history"]
            self.assertEqual(len(history), 6)
            history.pop()

        self.assert_tampers_fail(
            FEEDBACK_REPLAY,
            [
                (
                    "interval history replaced by a scalar",
                    lambda world: self.set_field(world, key, "not-a-list"),
                    (f"{key} must be a list of objects",),
                ),
                (
                    "one fewer interval than erosion transitions",
                    dropped_interval,
                    (
                        "fluvial_sediment_routing_history length does not match "
                        "configured erosion transitions",
                    ),
                ),
                (
                    "interval id that is not sequential",
                    lambda world: self.set_field(world[key][0], "id", 4),
                    (f"{key}[0] id is not sequential",),
                ),
                (
                    "interval feedback-stage link that skips a transition",
                    lambda world: self.set_field(
                        world[key][0], "feedback_stage_id", 4
                    ),
                    (f"{key}[0] feedback-stage link is invalid",),
                ),
                (
                    "interval erosion iteration that skips a transition",
                    lambda world: self.set_field(world[key][0], "erosion_iteration", 4),
                    (f"{key}[0] erosion iteration is invalid",),
                ),
            ],
        )

    def test_motion_and_glacial_tampers_fail_feedback_replay(self) -> None:
        def extra_motion_step(world: dict) -> None:
            history = world["plate_motion_history"]
            self.assertEqual(len(history), 7)
            history.append(deepcopy(history[-1]))

        def emptied_glacial_history(world: dict) -> None:
            history = world["glacial_sediment_transport_history"]
            self.assertEqual(len(history), 1)
            history.clear()

        self.assert_tampers_fail(
            FEEDBACK_REPLAY,
            [
                (
                    "motion step past the configured clock",
                    extra_motion_step,
                    (
                        "plate_motion_history[7] lies outside the configured "
                        "nominal clock",
                    ),
                ),
                (
                    "motion id that is not sequential",
                    lambda world: self.set_field(
                        world["plate_motion_history"][1], "id", 5
                    ),
                    ("plate_motion_history[1] id is not sequential",),
                ),
                (
                    "motion stage name that is not an iteration",
                    lambda world: self.set_field(
                        world["plate_motion_history"][1],
                        "stage",
                        "initial_plate_domains",
                    ),
                    ("plate_motion_history[1] stage is invalid",),
                ),
                (
                    "motion erosion iteration that is not its index",
                    lambda world: self.set_field(
                        world["plate_motion_history"][1], "erosion_iteration", 9
                    ),
                    ("plate_motion_history[1] erosion iteration is invalid",),
                ),
                (
                    "glacial history replaced by a mapping",
                    lambda world: self.set_field(
                        world, "glacial_sediment_transport_history", {}
                    ),
                    ("glacial_sediment_transport_history must be a list of objects",),
                ),
                (
                    "glacial history without its final record",
                    emptied_glacial_history,
                    (
                        "glacial sediment history must contain one final cryosphere "
                        "record",
                    ),
                ),
                (
                    "glacial id that is not sequential",
                    lambda world: self.set_field(
                        world["glacial_sediment_transport_history"][0], "id", 3
                    ),
                    ("glacial_sediment_transport_history[0] id is not sequential",),
                ),
                (
                    "glacial record linked to the initial stage",
                    lambda world: self.set_field(
                        world["glacial_sediment_transport_history"][0],
                        "feedback_stage_id",
                        0,
                    ),
                    (
                        "glacial_sediment_transport_history[0] final cryosphere link "
                        "is invalid",
                    ),
                ),
            ],
        )

    # ------------------------------------------------------- feedback stages
    def test_feedback_step_tampers_fail_coupled_stage_feedback_replay(self) -> None:
        def extra_correction_pass(world: dict) -> None:
            step = world["earth_system_feedback_history"][0]
            self.set_field(
                step,
                "numeric_depression_correction_pass_count",
                step["numeric_depression_correction_pass_count"] + 2,
            )

        def unbalanced_land_water(world: dict) -> None:
            step = world["earth_system_feedback_history"][0]
            self.set_field(
                step, "land_cell_count", step["land_cell_count"] + 1
            )

        def too_many_rivers(world: dict) -> None:
            step = world["earth_system_feedback_history"][0]
            self.set_field(
                step, "river_cell_count", step["cell_count"] + 1
            )

        def extra_climate_recompute(world: dict) -> None:
            step = world["earth_system_feedback_history"][0]
            self.set_field(
                step, "climate_recompute_count", step["climate_recompute_count"] + 1
            )

        def regressing_deposition(world: dict) -> None:
            history = world["earth_system_feedback_history"]
            self.assertGreater(
                history[-2]["cumulative_sediment_deposition_volume_km3"], 1.0
            )
            self.set_field(
                history[-1], "cumulative_sediment_deposition_volume_km3", 0.0
            )

        def unclosed_sediment_mass(world: dict) -> None:
            final = world["earth_system_feedback_history"][-1]
            self.set_field(
                final,
                "cumulative_sediment_production_volume_km3",
                final["cumulative_sediment_production_volume_km3"] + 1.0e6,
            )

        self.assert_tampers_fail(
            FEEDBACK_REPLAY,
            [
                (
                    "step id that is not sequential",
                    lambda world: self.set_field(
                        world["earth_system_feedback_history"][0], "id", 7
                    ),
                    ("feedback step[0] id is not sequential",),
                ),
                (
                    "string standing in for a process flag",
                    lambda world: self.set_field(
                        world["earth_system_feedback_history"][0],
                        "crust_evolution_applied",
                        "false",
                    ),
                    ("feedback step[0] has non-boolean process flags",),
                ),
                (
                    "negative count field",
                    lambda world: self.set_field(
                        world["earth_system_feedback_history"][0],
                        "river_cell_count",
                        -1,
                    ),
                    ("feedback step[0] has invalid count fields",),
                ),
                (
                    "non-finite value field",
                    lambda world: self.set_field(
                        world["earth_system_feedback_history"][0],
                        "surface_area_km2",
                        float("nan"),
                    ),
                    ("feedback step[0] has non-finite numeric fields",),
                ),
                (
                    "initial step labelled as an erosion iteration",
                    lambda world: self.set_field(
                        world["earth_system_feedback_history"][0],
                        "stage",
                        "erosion_iteration",
                    ),
                    ("feedback step[0] stage is invalid",),
                ),
                (
                    "initial step claiming an erosion iteration index",
                    lambda world: self.set_field(
                        world["earth_system_feedback_history"][0],
                        "erosion_iteration",
                        5,
                    ),
                    ("feedback step[0] erosion_iteration is invalid",),
                ),
                (
                    "initial step linked to a later motion record",
                    lambda world: self.set_field(
                        world["earth_system_feedback_history"][0],
                        "plate_motion_history_id",
                        3,
                    ),
                    ("feedback step[0] plate motion link is invalid",),
                ),
                (
                    "initial step claiming erosion was applied",
                    lambda world: self.set_field(
                        world["earth_system_feedback_history"][0],
                        "erosion_applied",
                        True,
                    ),
                    ("feedback step[0] erosion_applied is inconsistent",),
                ),
                (
                    "recompute counters that disagree with each other",
                    extra_climate_recompute,
                    ("feedback step[0] recompute counts are inconsistent",),
                ),
                (
                    "recompute flag that denies its own counter",
                    lambda world: self.set_field(
                        world["earth_system_feedback_history"][0],
                        "sea_level_recomputed",
                        False,
                    ),
                    (
                        "feedback step[0] sea_level_recomputed does not mirror its "
                        "count",
                    ),
                ),
                (
                    "correction passes that do not explain the hydrology recomputes",
                    extra_correction_pass,
                    (
                        "feedback step[0] hydrology/correction pass counts are "
                        "inconsistent",
                    ),
                ),
                (
                    "land and water counts that do not close",
                    unbalanced_land_water,
                    ("feedback step[0] land/water counts do not close",),
                ),
                (
                    "more river cells than cells",
                    too_many_rivers,
                    ("feedback step[0] river count exceeds cells",),
                ),
                (
                    "initial step reporting a change from a previous stage",
                    lambda world: self.set_field(
                        world["earth_system_feedback_history"][0],
                        "mean_abs_elevation_change_m_from_previous_stage",
                        1.0,
                    ),
                    (
                        "initial feedback step "
                        "mean_abs_elevation_change_m_from_previous_stage must be zero",
                    ),
                ),
                (
                    "cumulative deposition that falls back to zero",
                    regressing_deposition,
                    ("feedback step[7] cumulative sediment regresses",),
                ),
                (
                    "cumulative production that no longer closes",
                    unclosed_sediment_mass,
                    ("feedback step[7] cumulative sediment mass does not close",),
                ),
                (
                    "negative cumulative sediment",
                    lambda world: self.set_field(
                        world["earth_system_feedback_history"][0],
                        "cumulative_sediment_production_volume_km3",
                        -1.0,
                    ),
                    ("feedback step[0] cumulative sediment is invalid",),
                ),
                (
                    "final cells missing an area used by the final replay",
                    lambda world: self.pop_field(world["cells"][0], "area_km2"),
                    ("final cells contain invalid replay fields",),
                ),
            ],
        )

    # ------------------------------------------------------ summary mirrors
    def test_non_numeric_stage_field_fails_summary_mirrors(self) -> None:
        def non_numeric_elevation_change(world: dict) -> None:
            step = world["earth_system_feedback_history"][1]
            self.assertTrue(step["erosion_applied"])
            self.set_field(
                step,
                "mean_abs_elevation_change_m_from_previous_stage",
                "not-a-number",
            )

        self.assert_tampers_fail(
            SUMMARY_MIRRORS,
            [
                (
                    "erosion stage with a non-numeric elevation change",
                    non_numeric_elevation_change,
                    ("feedback summary inputs are non-numeric",),
                ),
            ],
        )

    def test_non_mapping_world_is_reported_as_failed_checks(self) -> None:
        checks = validate_physics_replays("not-a-world")

        self.assertEqual(len(checks), 13)
        self.assertTrue(all(not check["passed"] for check in checks))
        self.assertEqual(
            _check(checks, *PLATE_AGGREGATE)["observed"]["cell_count"], 0
        )
