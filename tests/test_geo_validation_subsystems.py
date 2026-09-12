from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.api import generate_geo_world
from magic_geo.config import WorldConfig, load_config
from magic_geo.geo_validation_subsystems import validate_natural_subsystems
from support.cryosphere_worlds import cached_cold_world_readonly


def _small_earth_config() -> WorldConfig:
    data = load_config(Path("configs/earthlike_seed.yaml")).model_dump(
        mode="python"
    )
    data["mesh"]["cell_count"] = 128
    data["tectonics"]["plate_count"] = 8
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    return WorldConfig.model_validate(data)


_GENERATED_WORLD: dict | None = None


def _shared_world() -> dict:
    """The generated geo world, built at most once per process.

    Callers must treat the return value as read-only and deep copy before
    mutating it.
    """

    global _GENERATED_WORLD
    if _GENERATED_WORLD is None:
        _GENERATED_WORLD = generate_geo_world(_small_earth_config())
    return _GENERATED_WORLD


def _check(checks: list[dict], domain: str, name: str) -> dict:
    return next(
        check
        for check in checks
        if check["domain"] == domain and check["name"] == name
    )


def _check_errors(check: dict) -> list[str]:
    """Every diagnostic string a check reported in ``observed``."""

    observed = check["observed"]
    if isinstance(observed, list):
        return [str(entry) for entry in observed]
    if isinstance(observed, dict):
        entries: list[str] = []
        for value in observed.values():
            if isinstance(value, list):
                entries.extend(str(entry) for entry in value)
        return entries
    return [str(observed)]


def _failed_names(checks: list[dict]) -> set[str]:
    return {
        f"{check['domain']}/{check['name']}"
        for check in checks
        if check["status"] == "failed"
    }


def _cells_by_id(world: dict) -> dict[int, dict]:
    return {cell["id"]: cell for cell in world["cells"]}


class NaturalSubsystemValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = _shared_world()

    def test_generated_earth_passes_broad_natural_subsystem_validation(self) -> None:
        checks = validate_natural_subsystems(self.world)

        self.assertEqual(len(checks), 38)
        self.assertTrue(all(check["passed"] for check in checks))
        self.assertEqual([check["id"] for check in checks], list(range(len(checks))))
        self.assertTrue(
            {
                "geometry_indices",
                "seasonal_climate",
                "coastal_marine_landmass",
                "soils_and_ecotones",
                "ocean_circulation",
                "tectonic_zones_faults",
                "lakes_watersheds",
                "river_evolution_channels",
                "sequence_stratigraphy",
                "cryosphere_permafrost_glacial",
                "aquifers_wetlands_karst",
                "ecosystems_reefs_species_wildfire",
                "geologic_resources",
            }.issubset({check["domain"] for check in checks})
        )
        required_shape = {
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
        }
        self.assertTrue(all(set(check) == required_shape for check in checks))

    def test_lake_overflow_pressure_replays_on_native_zero_to_fifty_scale(
        self,
    ) -> None:
        altered = deepcopy(self.world)
        basin = altered["lake_basins"][0]
        basin["overflows"] = True
        basin["storage_capacity_km3"] = 2.0
        basin["annual_runoff_km3"] = 6.0
        basin["overflow_index"] = 3.0

        check = _check(
            validate_natural_subsystems(altered),
            "lakes_watersheds",
            "lake_basin_membership_and_storage",
        )
        self.assertTrue(check["passed"], check["observed"])

        altered["lake_basins"][0]["overflow_index"] = 2.5
        check = _check(
            validate_natural_subsystems(altered),
            "lakes_watersheds",
            "lake_basin_membership_and_storage",
        )
        self.assertFalse(check["passed"])
        self.assertIn("basin 0: overflow_index replay", check["observed"])

    def test_lake_surface_cannot_be_reclassified_by_downstream_layers(self) -> None:
        lake = next(cell for cell in self.world["cells"] if cell["is_lake"])
        target = "lake_basin_membership_and_storage"
        clean = _check(validate_natural_subsystems(self.world), "lakes_watersheds", target)
        self.assertTrue(clean["passed"], clean["observed"])
        changes = {
            "biome": "wetland",
            "soil_type": "alluvial",
            "soil_depth_m": 1.0,
            "fertility": 0.8,
            "settlement_score": 0.8,
            "landform": "salt_flat",
            "water_body_type": (
                "saline_basin" if lake["water_body_type"] == "fresh_lake" else "fresh_lake"
            ),
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                altered = deepcopy(self.world)
                altered["cells"][lake["id"]][field] = value
                check = _check(
                    validate_natural_subsystems(altered), "lakes_watersheds", target
                )
                self.assertFalse(check["passed"], check["observed"])

    def test_soil_history_uses_natural_stages_without_fake_years(self) -> None:
        model = self.world["soil_pedogenesis_model"]
        feedback = self.world["earth_system_feedback_history"]

        self.assertEqual(model["time_basis"], "natural_simulation_stage")
        self.assertEqual(model["stage_source"], "earth_system_feedback_history")
        self.assertEqual(model["stage_count"], len(feedback))
        self.assertFalse(model["physical_time_resolved"])
        self.assertTrue(model["linked_nominal_time_coordinate_available"])
        self.assertFalse(model["nominal_time_calibrated"])
        self.assertFalse(model["state_mutation_evidence"])
        for history in self.world["soil_profile_histories"]:
            self.assertEqual(history["step_count"], len(feedback))
            for index, (step, source) in enumerate(
                zip(history["steps"], feedback, strict=True)
            ):
                self.assertEqual(step["time_basis"], "natural_simulation_stage")
                self.assertFalse(step["physical_time_resolved"])
                self.assertIsNone(step["start_year_bp"])
                self.assertIsNone(step["end_year_bp"])
                self.assertEqual(step["natural_stage_id"], source["id"])
                self.assertEqual(step["natural_stage_name"], source["stage"])
                self.assertEqual(step["start_model_step"], index)
                self.assertEqual(step["end_model_step"], index + 1)
                self.assertTrue(step["nominal_time_link_available"])
                self.assertFalse(step["nominal_time_calibrated"])
                for field in (
                    "nominal_time_basis",
                    "nominal_time_source_parameter",
                    "nominal_interval_start_ma",
                    "nominal_interval_end_ma",
                    "nominal_interval_duration_ma",
                ):
                    self.assertEqual(step[field], source[field])
                if source["nominal_interval_duration_ma"] == 0.0:
                    self.assertEqual(step["start_depth_m"], step["end_depth_m"])
                    self.assertEqual(step["soil_production_m"], 0.0)
                    self.assertEqual(step["erosion_loss_m"], 0.0)
                    self.assertEqual(step["pedogenic_flux_index"], 0.0)

    def test_soil_natural_stage_provenance_mutation_is_rejected(self) -> None:
        mutations = (
            ("natural_stage_id", 999),
            ("nominal_time_basis", "tampered"),
            ("nominal_interval_start_ma", 999.0),
            ("nominal_interval_end_ma", 999.0),
            ("nominal_interval_duration_ma", 999.0),
        )
        for field, value in mutations:
            altered = deepcopy(self.world)
            altered["soil_profile_histories"][0]["steps"][0][field] = value

            check = _check(
                validate_natural_subsystems(altered),
                "soils_and_ecotones",
                "soil_profile_horizon_history_links",
            )

            with self.subTest(field=field):
                self.assertEqual(check["status"], "failed")
                self.assertTrue(
                    any(
                        "natural time provenance" in error
                        for error in check["observed"]["errors"]
                    )
                )

    def test_soil_flux_and_history_total_mutations_are_rejected(self) -> None:
        altered = deepcopy(self.world)
        history = altered["soil_profile_histories"][0]
        history["steps"][0]["soil_production_m"] = -999.0
        history["steps"][0]["erosion_loss_m"] = -999.0
        history["total_soil_production_m"] = -999.0
        history["total_erosion_loss_m"] = -999.0
        altered["summary"]["total_soil_production_m"] = -999.0
        altered["summary"]["total_soil_erosion_loss_m"] = -999.0

        check = _check(
            validate_natural_subsystems(altered),
            "soils_and_ecotones",
            "soil_profile_horizon_history_links",
        )

        self.assertEqual(check["status"], "failed")
        self.assertTrue(
            any(
                "production/erosion" in error
                for error in check["observed"]["errors"]
            )
        )

    def test_geometry_climate_coastal_soil_and_ecotone_mutations_are_rejected(
        self,
    ) -> None:
        ecotone_cell_id = self.world["biome_ecotone_regions"][0]["cell_ids"][0]
        cases = (
            (
                "mesh tile aggregate",
                "geometry_indices",
                "mesh_lod_membership_and_summaries",
                lambda world: world["mesh_lod"]["tiles"][0].__setitem__(
                    "cell_count", world["mesh_lod"]["tiles"][0]["cell_count"] + 1
                ),
            ),
            (
                "classification count",
                "seasonal_climate",
                "classification_and_continentality_sources",
                lambda world: world["climate_classification"].__setitem__(
                    "classified_cell_count", len(world["cells"]) - 1
                ),
            ),
            (
                "coastal source",
                "coastal_marine_landmass",
                "coastal_feature_and_chokepoint_sources",
                lambda world: world["coastal_features"][0].__setitem__(
                    "cell_id", len(world["cells"]) + 1
                ),
            ),
            (
                "soil horizon source",
                "soils_and_ecotones",
                "soil_profile_horizon_history_links",
                lambda world: world["soil_horizons"][0].__setitem__(
                    "soil_profile_id", 9999
                ),
            ),
            (
                "ecotone inverse",
                "soils_and_ecotones",
                "biome_ecotone_membership_and_ranges",
                lambda world: world["cells"][ecotone_cell_id].__setitem__(
                    "biome_ecotone_region_id", -1
                ),
            ),
        )
        for label, domain, check_name, mutate in cases:
            with self.subTest(label=label):
                altered = deepcopy(self.world)
                mutate(altered)

                check = _check(
                    validate_natural_subsystems(altered), domain, check_name
                )

                self.assertEqual(check["status"], "failed")

    def test_missing_even_empty_stage_registry_is_rejected(self) -> None:
        altered = deepcopy(self.world)
        self.assertIn("reef_systems", altered)
        altered.pop("reef_systems")

        check = _check(
            validate_natural_subsystems(altered),
            "ecosystems_reefs_species_wildfire",
            "reef_membership_sources_and_ranges",
        )

        self.assertEqual(check["status"], "failed")

    def test_malformed_ocean_tectonic_lake_and_river_sources_are_rejected(
        self,
    ) -> None:
        cases = (
            (
                "ocean edge",
                "ocean_circulation",
                "transport_source_links_and_ranges",
                lambda world: world["ocean_current_transport_edges"][0].__setitem__(
                    "target_cell_id", len(world["cells"]) + 50
                ),
            ),
            (
                "tectonic cell mirror",
                "tectonic_zones_faults",
                "zone_membership_sources_and_ranges",
                lambda world: world["cells"][
                    world["collision_zones"][0]["cell_ids"][0]
                ].__setitem__("collision_zone_id", -1),
            ),
            (
                "lake volume closure",
                "lakes_watersheds",
                "lake_overflow_history_conservation",
                lambda world: world["summary"].__setitem__(
                    "lake_overflow_history_count",
                    int(world["summary"]["lake_overflow_history_count"]) + 1,
                ),
            ),
            (
                "hydraulic reach source",
                "river_evolution_channels",
                "hydraulic_reach_source_links_and_ranges",
                lambda world: world["river_hydraulic_reaches"][0].__setitem__(
                    "river_channel_system_id", 9999
                ),
            ),
        )
        for label, domain, check_name, mutate in cases:
            with self.subTest(label=label):
                altered = deepcopy(self.world)
                mutate(altered)

                check = _check(
                    validate_natural_subsystems(altered), domain, check_name
                )

                self.assertEqual(check["status"], "failed")

    def test_malformed_sequence_cryosphere_and_water_systems_are_rejected(
        self,
    ) -> None:
        cases = (
            (
                "sequence bound",
                "sequence_stratigraphy",
                "source_links_steps_and_aggregates",
                lambda world: world["sequence_stratigraphy_histories"][0][
                    "steps"
                ][0].__setitem__("flooding_index", 1.5),
            ),
            (
                "ice continuity",
                "cryosphere_permafrost_glacial",
                "ice_sheet_history_conservation",
                lambda world: world["ice_sheet_histories"][0]["steps"][1].__setitem__(
                    "start_volume_km3",
                    world["ice_sheet_histories"][0]["steps"][1][
                        "start_volume_km3"
                    ]
                    + 3.0,
                ),
            ),
            (
                "aquifer count",
                "aquifers_wetlands_karst",
                "aquifer_membership_models_and_ranges",
                lambda world: world["aquifer_systems"][0].__setitem__(
                    "cell_count", world["aquifer_systems"][0]["cell_count"] + 1
                ),
            ),
        )
        for label, domain, check_name, mutate in cases:
            with self.subTest(label=label):
                source = cached_cold_world_readonly() if label == "ice continuity" else self.world
                altered = deepcopy(source)
                mutate(altered)

                check = _check(
                    validate_natural_subsystems(altered), domain, check_name
                )

                self.assertEqual(check["status"], "failed")

    def test_malformed_ecosystem_and_resource_source_links_are_rejected(
        self,
    ) -> None:
        species_cell_id = self.world["species_range_records"][0]["cell_ids"][0]
        species_record_id = self.world["species_range_records"][0]["id"]
        cases = (
            (
                "species inverse",
                "ecosystems_reefs_species_wildfire",
                "species_range_inverse_links_and_envelopes",
                lambda world: world["cells"][species_cell_id][
                    "species_range_record_ids"
                ].remove(species_record_id),
            ),
            (
                "commodity source",
                "geologic_resources",
                "commodity_occurrence_deposit_links",
                lambda world: world["commodity_occurrences"][0].__setitem__(
                    "resource_deposit_id", 99999
                ),
            ),
            (
                "resource flow normalization",
                "geologic_resources",
                "resource_deposit_sources_and_ranges",
                lambda world: world["resource_deposit_model"].__setitem__(
                    "flow_accumulation_scale", 40.0
                ),
            ),
            (
                "resource reserve replay",
                "geologic_resources",
                "resource_deposit_sources_and_ranges",
                lambda world: world["resource_deposits"][0].__setitem__(
                    "reserve_potential_index",
                    0.0
                    if world["resource_deposits"][0][
                        "reserve_potential_index"
                    ]
                    > 0.1
                    else 1.0,
                ),
            ),
            (
                "resource accessibility replay",
                "geologic_resources",
                "resource_deposit_sources_and_ranges",
                lambda world: world["resource_deposits"][0].__setitem__(
                    "accessibility_index", -999.0
                ),
            ),
            (
                "resource economic viability replay",
                "geologic_resources",
                "resource_deposit_sources_and_ranges",
                lambda world: world["resource_deposits"][0].__setitem__(
                    "economic_viability_index", -999.0
                ),
            ),
            (
                "ore cell replay",
                "geologic_resources",
                "ore_system_membership_and_formation_sources",
                lambda world: world["cells"][0].__setitem__(
                    "ore_genesis_potential_index",
                    0.0
                    if world["cells"][0]["ore_genesis_potential_index"] > 0.1
                    else 1.0,
                ),
            ),
            (
                "ore confidence replay",
                "geologic_resources",
                "ore_system_membership_and_formation_sources",
                lambda world: world["ore_genesis_systems"][0].__setitem__(
                    "ore_genesis_confidence_index",
                    0.0
                    if world["ore_genesis_systems"][0][
                        "ore_genesis_confidence_index"
                    ]
                    > 0.1
                    else 1.0,
                ),
            ),
            (
                "ore formation step replay",
                "geologic_resources",
                "ore_system_membership_and_formation_sources",
                lambda world: world["ore_genesis_systems"][0][
                    "formation_steps"
                ][0].__setitem__(
                    "mean_process_intensity_index",
                    0.0
                    if world["ore_genesis_systems"][0]["formation_steps"][0][
                        "mean_process_intensity_index"
                    ]
                    > 0.1
                    else 1.0,
                ),
            ),
            (
                "petroleum path",
                "geologic_resources",
                "petroleum_migration_source_paths",
                lambda world: world["petroleum_migration_systems"][0][
                    "migration_steps"
                ][0]["path_cell_ids"].append(len(world["cells"]) + 1),
            ),
        )
        for label, domain, check_name, mutate in cases:
            with self.subTest(label=label):
                altered = deepcopy(self.world)
                mutate(altered)

                check = _check(
                    validate_natural_subsystems(altered), domain, check_name
                )

                self.assertEqual(check["status"], "failed")

    def test_civilization_fields_do_not_affect_subsystem_checks(self) -> None:
        baseline = validate_natural_subsystems(self.world)
        altered = deepcopy(self.world)
        altered["settlements"] = [{"id": 0, "population": 1_000_000_000}]
        altered["political_regions"] = {"malformed": "and ignored"}
        altered["summary"]["settlement_count"] = 9999
        for cell in altered["cells"]:
            cell["population"] = {"malformed": True}
            cell["political_region_id"] = 42
            cell["culture_region_id"] = 84
        for deposit in altered["resource_deposits"]:
            deposit["political_region_id"] = 42
            deposit["culture_region_id"] = 84
        for occurrence in altered["commodity_occurrences"]:
            occurrence["political_region_id"] = 42
            occurrence["culture_region_id"] = 84
            occurrence["market_value_index"] = {"ignored": True}
            occurrence["accessibility_index"] = float("nan")
        for reef in altered["reef_systems"]:
            reef["settlement_ids"] = [9999]
            reef["port_site_ids"] = [9999]

        self.assertEqual(validate_natural_subsystems(altered), baseline)

    def test_malformed_payload_does_not_raise(self) -> None:
        checks = validate_natural_subsystems({"cells": [], "summary": []})

        self.assertTrue(any(not check["passed"] for check in checks))
        self.assertTrue(all(check["status"] in {"passed", "failed", "not_applicable"} for check in checks))


class NaturalSubsystemFailureModeTests(TestCase):
    """One tampered subsystem must flip exactly the checks that describe it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.world = _shared_world()

    def _assert_failure(
        self,
        mutate,
        target: str,
        errors: tuple[str, ...],
        also_failed: tuple[str, ...] = (),
        cascade: dict[str, tuple[str, ...]] | None = None,
        *,
        world: dict | None = None,
    ) -> None:
        altered = deepcopy(self.world if world is None else world)
        mutate(altered)
        checks = validate_natural_subsystems(altered)

        domain, name = target.split("/")
        check = _check(checks, domain, name)
        self.assertEqual(check["status"], "failed", check["message"])
        self.assertFalse(check["passed"])
        observed = _check_errors(check)
        for expected in errors:
            self.assertIn(expected, observed)
        self.assertEqual(_failed_names(checks), {target, *also_failed})
        for cascaded, cascaded_errors in (cascade or {}).items():
            self.assertIn(cascaded, also_failed)
            cascade_domain, cascade_name = cascaded.split("/")
            cascade_observed = _check_errors(
                _check(checks, cascade_domain, cascade_name)
            )
            for expected in cascaded_errors:
                self.assertIn(expected, cascade_observed)

    def _run_cases(self, cases, *, world=None) -> None:
        for label, mutate, target, errors, *rest in cases:
            with self.subTest(case=label):
                self._assert_failure(
                    mutate,
                    target,
                    errors,
                    rest[0] if rest else (),
                    rest[1] if len(rest) > 1 else None,
                    world=world,
                )

    def _run_cold_cases(self, cases) -> None:
        world = cached_cold_world_readonly()
        # Availability of an actual cold branch is part of the control, not a
        # synthetic temperature change on an existing energy certificate.
        self.assertFalse(_failed_names(validate_natural_subsystems(world)))
        self._run_cases(cases, world=world)

    # ---- ocean circulation --------------------------------------------

    def test_ocean_current_system_membership_mutations_are_rejected(self) -> None:
        systems = self.world["ocean_current_systems"]
        mirror_cell_id = systems[0]["cell_ids"][1]
        land_cell_id = systems[0]["cell_ids"][2]
        marine_region_id = _cells_by_id(self.world)[land_cell_id][
            "marine_region_id"
        ]

        def invalid_cells(world: dict) -> None:
            world["ocean_current_systems"][0]["cell_ids"] = [
                len(world["cells"]) + 5
            ]

        def broken_aggregates(world: dict) -> None:
            records = world["ocean_current_systems"]
            records[1]["cell_ids"] = list(records[1]["cell_ids"]) + [
                records[0]["cell_ids"][0]
            ]
            records[0]["cell_count"] += 1
            records[0]["area_km2"] += 1.0e6
            cells = _cells_by_id(world)
            cells[mirror_cell_id]["ocean_current_system_id"] = 15
            cells[land_cell_id]["water_body_type"] = "land"

        self._run_cases(
            (
                (
                    "invalid cell ids",
                    invalid_cells,
                    "ocean_circulation/system_membership_and_aggregates",
                    (
                        "system 0: invalid cell_ids",
                        "system membership does not invert cell assignments",
                    ),
                    ("ocean_circulation/cell_values_and_summary_mirrors",),
                    {
                        "ocean_circulation/cell_values_and_summary_mirrors": (
                            "ocean_current_cell_count",
                        )
                    },
                ),
                (
                    "membership aggregates",
                    broken_aggregates,
                    "ocean_circulation/system_membership_and_aggregates",
                    (
                        "system 0: cell_count",
                        "system 0: area",
                        f"system 0: cell mirror {mirror_cell_id}",
                        f"system 0: non-marine cell {land_cell_id}",
                        "system 1: overlapping membership",
                    ),
                    (
                        "coastal_marine_landmass/land_marine_shelf_partitions",
                        "ocean_circulation/transport_source_links_and_ranges",
                        "ecosystems_reefs_species_wildfire/succession_and_renewable_sources",
                        "ecosystems_reefs_species_wildfire/species_range_inverse_links_and_envelopes",
                        "ecosystems_reefs_species_wildfire/reef_membership_sources_and_ranges",
                    ),
                    {
                        "coastal_marine_landmass/land_marine_shelf_partitions": (
                            f"marine_region {marine_region_id}:"
                            f" cell mirror {land_cell_id}",
                        ),
                        # Relabeling a fishery source as land also invalidates
                        # its retained support flags and derived estimate.
                        "ecosystems_reefs_species_wildfire/succession_and_renewable_sources": (
                            f"aquatic climate support cell {land_cell_id}: fishery_climate_supported mismatch",
                            f"aquatic climate support cell {land_cell_id}: fishery_productivity_supported mismatch",
                        ),
                        "ecosystems_reefs_species_wildfire/species_range_inverse_links_and_envelopes": (
                            f"species habitat cell {land_cell_id}: species_marine_habitat_eligible mismatch",
                            f"species habitat cell {land_cell_id}: species_marine_fish_score_supported mismatch",
                            f"species habitat cell {land_cell_id}: dominant guild marine_fish lacks habitat or input support",
                        ),
                        # Native reef growth consumes this marine selector;
                        # changing it invalidates the retained growth estimate.
                        "ecosystems_reefs_species_wildfire/reef_membership_sources_and_ranges": (
                            f"reef native cell {land_cell_id}: growth must omit bleaching without renormalizing weights",
                        ),
                    },
                ),
            )
        )

    def test_ocean_transport_edge_and_cell_diagnostics_are_rejected(self) -> None:
        def broken_edge(world: dict) -> None:
            cells = _cells_by_id(world)
            edge = world["ocean_current_transport_edges"][0]
            source = cells[edge["source_cell_id"]]
            distant_id = next(
                cell["id"]
                for cell in world["cells"]
                if cell["id"] not in source["neighbors"]
                and cell["id"] != source["id"]
                and cell["ocean_current_system_id"] >= 0
                and cell["ocean_current_system_id"] != edge["target_system_id"]
            )
            edge["target_cell_id"] = distant_id
            edge["source_system_id"] = 99
            edge["alignment"] = 2.0
            edge["upwelling_index"] = 1.5
            edge["current_speed_index"] = -1.0

        def missing_endpoint(world: dict) -> None:
            world["ocean_current_transport_edges"][0]["source_cell_id"] = 9999

        def unbounded_cell_index(world: dict) -> None:
            world["cells"][0]["ocean_upwelling_index"] = 5.0

        self._run_cases(
            (
                (
                    "unknown endpoint cell",
                    missing_endpoint,
                    "ocean_circulation/transport_source_links_and_ranges",
                    ("edge 0: invalid endpoint",),
                ),
                (
                    "transport edge",
                    broken_edge,
                    "ocean_circulation/transport_source_links_and_ranges",
                    (
                        "edge 0: target is not adjacent",
                        "edge 0: source target mirror",
                        "edge 0: source system",
                        "edge 0: target system",
                        "edge 0: unknown system",
                        "edge 0: alignment",
                        "edge 0: current_speed_index",
                        "edge 0: upwelling_index",
                    ),
                ),
                (
                    "cell upwelling range",
                    unbounded_cell_index,
                    "ocean_circulation/cell_values_and_summary_mirrors",
                    ("cell 0: ocean_upwelling_index",),
                ),
            )
        )

    # ---- geometry indices ---------------------------------------------

    def test_mesh_lod_tile_cell_and_level_mutations_are_rejected(self) -> None:
        # Dropping cell 0 out of its LOD ancestry must also unbalance the
        # per-level aggregate of every tile that used to contain it.
        orphaned_tile_errors = tuple(
            f"tile ({level}, {tile_id}): membership aggregate"
            for level, tile_id in enumerate(
                self.world["cells"][0]["mesh_lod_tile_ids"]
            )
        )
        self.assertEqual(len(orphaned_tile_errors), 4)

        def broken_tiles(world: dict) -> None:
            tiles = world["mesh_lod"]["tiles"]
            tiles[1]["tile_id"] = tiles[0]["tile_id"]
            tiles[2]["cell_count"] = 0
            tiles[3]["representative_cell_id"] = 9999

        def broken_cell_ancestry(world: dict) -> None:
            world["cells"][0]["mesh_lod_tile_ids"] = []
            world["cells"][1]["mesh_lod_finest_tile_id"] = 999
            world["cells"][2]["mesh_lod_tile_ids"][0] = 999

        def broken_levels(world: dict) -> None:
            world["mesh_lod"]["level_summaries"][0]["cell_count"] = 5
            world["mesh_lod"]["level_summaries"].pop()

        target = "geometry_indices/mesh_lod_membership_and_summaries"
        self._run_cases(
            (
                (
                    "tile records",
                    broken_tiles,
                    target,
                    (
                        "duplicate/invalid tile (0, 0)",
                        "tile (0, 2): area/count",
                        "tile (0, 3): representative",
                    ),
                ),
                (
                    "cell ancestry",
                    broken_cell_ancestry,
                    target,
                    (
                        "cell 0: LOD ancestry",
                        "cell 1: finest tile",
                        "cell 2: unknown tile (0, 999)",
                        *orphaned_tile_errors,
                    ),
                ),
                (
                    "level summaries",
                    broken_levels,
                    target,
                    (
                        "level summary coverage",
                        "level 0: summary",
                        "mesh_lod_level_count",
                    ),
                ),
            )
        )

    def test_spherical_index_bucket_mutations_are_rejected(self) -> None:
        def duplicate_pixel_ids(world: dict) -> None:
            pixels = world["spherical_spatial_index"]["healpix_like_pixels"]
            pixels[1]["pixel_id"] = pixels[0]["pixel_id"]

        def broken_cell_links(world: dict) -> None:
            world["cells"][0]["healpix_like_pixel_id"] = 9999
            world["cells"][1]["healpix_like_nside"] = 99

        def broken_aggregates(world: dict) -> None:
            spatial = world["spherical_spatial_index"]
            spatial["healpix_like_pixels"][0]["cell_count"] += 1
            spatial["s2_like_cells"][0]["area_km2"] += 100.0

        target = "geometry_indices/spherical_index_membership_and_summaries"
        self._run_cases(
            (
                (
                    "duplicate pixel ids",
                    duplicate_pixel_ids,
                    target,
                    ("duplicate occupied spatial IDs",),
                ),
                (
                    "cell bucket links",
                    broken_cell_links,
                    target,
                    (
                        "cell 0: unknown spatial bucket",
                        "cell 1: index resolution mirror",
                    ),
                ),
                (
                    "bucket aggregates",
                    broken_aggregates,
                    target,
                    (
                        "HEALPix-like bucket 0: aggregate",
                        "S2-like bucket 0: aggregate",
                    ),
                ),
            )
        )

    # ---- seasonal climate ---------------------------------------------

    def test_seasonal_history_grouping_and_step_mutations_are_rejected(self) -> None:
        def unknown_group(world: dict) -> None:
            world["climate_seasonal_histories"][0]["atmospheric_cell"] = (
                "unknown_group"
            )

        def missing_month(world: dict) -> None:
            world["climate_seasonal_histories"][0]["steps"].pop()

        def broken_steps(world: dict) -> None:
            steps = world["climate_seasonal_histories"][0]["steps"]
            steps[0]["month"] = 5
            steps[1]["end_humidity_storage_mm"] = -1.0
            steps[3]["precipitation_mm"] = -1.0
            steps[4]["drying_risk"] = 2.0

        def broken_aggregates(world: dict) -> None:
            history = world["climate_seasonal_histories"][0]
            history["annual_precipitation_mm"] += 5.0
            history["monsoon_index"] = 2.0

        target = "seasonal_climate/seasonal_history_grouping_and_aggregates"
        self._run_cases(
            (
                (
                    "atmospheric group",
                    unknown_group,
                    target,
                    (
                        "history 0: atmospheric group",
                        "history 0: cell_count",
                        "seasonal atmospheric group coverage",
                    ),
                ),
                (
                    "monthly coverage",
                    missing_month,
                    target,
                    (
                        "history 0: monthly steps",
                        "climate_seasonal_step_count",
                        "climate_seasonal_total_precipitation_mm",
                        "climate_seasonal_total_evaporation_mm",
                    ),
                ),
                (
                    "step values",
                    broken_steps,
                    target,
                    (
                        "history 0: month sequence",
                        "history 0: humidity storage 1",
                        "history 0: storage continuity 2",
                        "history 0: precipitation_mm 3",
                        "history 0: drying_risk 4",
                        "climate_seasonal_total_precipitation_mm",
                    ),
                ),
                (
                    "annual aggregates",
                    broken_aggregates,
                    target,
                    (
                        "history 0: annual_precipitation_mm",
                        "history 0: monsoon_index",
                    ),
                ),
            )
        )

    def test_classification_and_continentality_mutations_are_rejected(self) -> None:
        regions = self.world["climate_continentality_regions"]
        mirror_cell_id = regions[0]["cell_ids"][1]

        def unknown_class(world: dict) -> None:
            world["cells"][0]["climate_class"] = "ZZZ"

        def invalid_region_cells(world: dict) -> None:
            world["climate_continentality_regions"][0]["cell_ids"] = [9999]

        def broken_region_aggregates(world: dict) -> None:
            records = world["climate_continentality_regions"]
            records[1]["cell_ids"] = list(records[1]["cell_ids"]) + [
                records[0]["cell_ids"][0]
            ]
            records[0]["cell_count"] += 1
            records[0]["mean_continentality_index"] = 2.0
            records[0]["mean_precipitation_mm_y"] = -1.0
            _cells_by_id(world)[mirror_cell_id][
                "climate_continentality_region_id"
            ] = 99

        target = "seasonal_climate/classification_and_continentality_sources"
        self._run_cases(
            (
                (
                    "class outside legend",
                    unknown_class,
                    target,
                    (
                        "cell class absent from legend",
                        "classification counts",
                        "classification summary mirrors",
                    ),
                ),
                (
                    "region cell sources",
                    invalid_region_cells,
                    target,
                    ("region 0: cells", "continentality assignment inverse"),
                ),
                (
                    "region aggregates",
                    broken_region_aggregates,
                    target,
                    (
                        "region 0: count/area",
                        f"region 0: cell mirror {mirror_cell_id}",
                        "region 0: mean_continentality_index",
                        "region 0: mean_precipitation_mm_y",
                        "region 1: overlap",
                    ),
                ),
            )
        )

    # ---- coastal / marine / landmass ----------------------------------

    def test_landmass_partition_mutations_are_rejected(self) -> None:
        mirror_cell_id = self.world["landmasses"][0]["cell_ids"][1]

        def invalid_cells(world: dict) -> None:
            world["landmasses"][0]["cell_ids"] = [9999]

        def broken_aggregates(world: dict) -> None:
            masses = world["landmasses"]
            masses[1]["cell_ids"] = list(masses[1]["cell_ids"]) + [
                masses[0]["cell_ids"][0]
            ]
            masses[0]["cell_count"] += 1
            masses[0]["area_km2"] += 1.0e6
            masses[0]["centroid_lat_deg"] = "north"
            _cells_by_id(world)[mirror_cell_id]["landmass_id"] = 1

        target = "coastal_marine_landmass/land_marine_shelf_partitions"
        self._run_cases(
            (
                (
                    "invalid cell ids",
                    invalid_cells,
                    target,
                    ("landmass 0: cell_ids", "landmass: assignment inverse"),
                ),
                (
                    "partition aggregates",
                    broken_aggregates,
                    target,
                    (
                        "landmass 0: count/area",
                        f"landmass 0: cell mirror {mirror_cell_id}",
                        "landmass 0: centroid_lat_deg",
                        "landmass 1: overlap",
                    ),
                ),
            )
        )

    def test_coastal_feature_and_chokepoint_value_mutations_are_rejected(self) -> None:
        def broken_feature(world: dict) -> None:
            feature = world["coastal_features"][0]
            feature["lat_deg"] = "north"
            feature["wave_energy_index"] = 2.0
            feature["length_km"] = -1.0

        def broken_chokepoint(world: dict) -> None:
            chokepoint = world["marine_chokepoints"][0]
            chokepoint["marine_region_id"] = 99
            chokepoint["adjacent_landmass_ids"] = [99]
            chokepoint["constriction_index"] = 2.0

        target = "coastal_marine_landmass/coastal_feature_and_chokepoint_sources"
        self._run_cases(
            (
                (
                    "coastal feature",
                    broken_feature,
                    target,
                    (
                        "coastal_feature 0: coordinates",
                        "feature 0: wave_energy_index",
                        "feature 0: length/migration",
                    ),
                ),
                (
                    "marine chokepoint",
                    broken_chokepoint,
                    target,
                    (
                        "chokepoint 0: marine region",
                        "chokepoint 0: landmasses",
                        "chokepoint 0: geometry",
                    ),
                ),
            )
        )

    # ---- tectonics ------------------------------------------------------

    def test_tectonic_zone_source_mutations_are_rejected(self) -> None:
        def invalid_zone_cells(world: dict) -> None:
            world["collision_zones"][0]["cell_ids"] = [9999]

        def broken_zone_sources(world: dict) -> None:
            zone = world["subduction_zones"][0]
            zone["boundary_edge_ids"] = [999999]
            zone["cell_count"] += 1
            zone["area_km2"] += 1.0e6
            zone["representative_cell_id"] = 9999
            zone["plate_ids"] = [99]
            zone["mean_zone_strength"] = 2.0

        target = "tectonic_zones_faults/zone_membership_sources_and_ranges"
        self._run_cases(
            (
                (
                    "collision zone cells",
                    invalid_zone_cells,
                    target,
                    ("collision 0: cell_ids",),
                    ("tectonic_zones_faults/zone_registry_structure",),
                ),
                (
                    "subduction zone sources",
                    broken_zone_sources,
                    target,
                    (
                        "subduction 0: boundary_edge_ids",
                        "subduction 0: counts",
                        "subduction 0: area",
                        "subduction 0: representative",
                        "subduction 0: plates",
                        "subduction 0: mean_zone_strength",
                    ),
                ),
            )
        )

    def test_fault_system_mutations_are_rejected(self) -> None:
        fault_cell_id = self.world["fault_systems"][0]["cell_ids"][0]

        def unstable_ids(world: dict) -> None:
            world["fault_systems"][0]["id"] = 5

        def invalid_cells(world: dict) -> None:
            world["fault_systems"][0]["cell_ids"] = [9999]

        def broken_values(world: dict) -> None:
            fault = world["fault_systems"][0]
            fault["boundary_edge_ids"] = [999999]
            fault["cell_count"] += 1
            fault["area_km2"] += 1.0e6
            fault["mean_fault_slip_rate_index"] = 2.0
            fault["mean_earthquake_recurrence_interval_y"] = -1.0

        def overlapping_faults(world: dict) -> None:
            world["fault_systems"].append(dict(world["fault_systems"][0], id=1))

        target = "tectonic_zones_faults/fault_system_membership_and_summary"
        self._run_cases(
            (
                (
                    "non-sequential ids",
                    unstable_ids,
                    target,
                    (
                        "fault IDs are not sequential",
                        f"fault 5: cell mirror {fault_cell_id}",
                    ),
                ),
                (
                    "invalid cell ids",
                    invalid_cells,
                    target,
                    (
                        "fault 0: cell_ids",
                        "fault membership does not invert cell assignments",
                        "fault_system_cell_count",
                    ),
                ),
                (
                    "aggregate values",
                    broken_values,
                    target,
                    (
                        "fault 0: boundary edges",
                        "fault 0: counts",
                        "fault 0: area",
                        "fault 0: mean_fault_slip_rate_index",
                        "fault 0: recurrence",
                    ),
                ),
                (
                    "overlapping membership",
                    overlapping_faults,
                    target,
                    ("fault 1: overlapping cells", "fault_system_count"),
                ),
            )
        )

    # ---- soils and ecotones --------------------------------------------

    def test_soil_profile_source_link_mutations_are_rejected(self) -> None:
        def wrong_time_basis(world: dict) -> None:
            world["soil_pedogenesis_model"]["time_basis"] = "calendar_years"

        def invalid_profile_cell(world: dict) -> None:
            world["soil_profiles"][0]["cell_id"] = 9999

        def broken_cell_mirror(world: dict) -> None:
            profile = world["soil_profiles"][0]
            _cells_by_id(world)[profile["cell_id"]]["soil_profile_id"] = 44

        def broken_horizon_sources(world: dict) -> None:
            world["soil_profiles"][0]["horizon_count"] = 99

        def broken_history_source(world: dict) -> None:
            world["soil_profiles"][0]["soil_profile_history_id"] = 9999

        def broken_history_mirror(world: dict) -> None:
            world["soil_profile_histories"][0]["cell_id"] = 9999

        target = "soils_and_ecotones/soil_profile_horizon_history_links"
        self._run_cases(
            (
                (
                    "pedogenesis time basis",
                    wrong_time_basis,
                    target,
                    (
                        "geo-only soil history must use the natural stage ledger",
                        "soil_pedogenesis_time_basis",
                    ),
                ),
                (
                    "profile cell source",
                    invalid_profile_cell,
                    target,
                    (
                        "profile 0: cell source/duplicate",
                        "soil profile assignment inverse",
                        "orphan/duplicate soil horizon or history",
                    ),
                ),
                (
                    "profile cell mirror",
                    broken_cell_mirror,
                    target,
                    ("profile 0: cell mirror",),
                ),
                (
                    "horizon sources",
                    broken_horizon_sources,
                    target,
                    (
                        "profile 0: horizon sources",
                        "orphan/duplicate soil horizon or history",
                    ),
                ),
                (
                    "history source",
                    broken_history_source,
                    target,
                    (
                        "profile 0: history source/duplicate",
                        "orphan/duplicate soil horizon or history",
                    ),
                ),
                (
                    "history mirror",
                    broken_history_mirror,
                    target,
                    ("profile 0: history mirror/steps",),
                ),
            )
        )

    def test_soil_horizon_and_history_value_mutations_are_rejected(self) -> None:
        first_horizon = self.world["soil_horizons"][0]
        horizon_mirror_error = (
            f"profile {first_horizon['soil_profile_id']}:"
            f" horizon mirror {first_horizon['id']}"
        )

        def broken_horizon_order(world: dict) -> None:
            world["soil_horizons"][0]["sequence_index"] += 5

        def broken_horizon_values(world: dict) -> None:
            horizon = world["soil_horizons"][0]
            horizon["bottom_depth_m"] += 1.0
            horizon["sand_fraction"] = 0.9
            horizon["salinity_index"] = 2.0

        def broken_profile_values(world: dict) -> None:
            profile = world["soil_profiles"][0]
            profile["total_depth_m"] += 1.0
            profile["moisture_index"] = 2.0

        def missing_natural_stage(world: dict) -> None:
            history = world["soil_profile_histories"][0]
            history["steps"].pop()
            history["step_count"] = len(history["steps"])

        def negative_step_depth(world: dict) -> None:
            world["soil_profile_histories"][0]["steps"][0]["start_depth_m"] = -1.0

        def discontinuous_steps(world: dict) -> None:
            world["soil_profile_histories"][0]["steps"][1]["start_depth_m"] += 1.0

        def unbounded_step_index(world: dict) -> None:
            world["soil_profile_histories"][0]["steps"][0][
                "erosion_pressure_index"
            ] = 2.0

        def broken_history_mean(world: dict) -> None:
            world["soil_profile_histories"][0]["mean_weathering_index"] += 0.1

        def flipped_erosion_flag(world: dict) -> None:
            history = world["soil_profile_histories"][0]
            history["high_erosion_pressure"] = not history["high_erosion_pressure"]

        target = "soils_and_ecotones/soil_profile_horizon_history_links"
        self._run_cases(
            (
                (
                    "horizon sequence mirror",
                    broken_horizon_order,
                    target,
                    (horizon_mirror_error,),
                ),
                (
                    "horizon values",
                    broken_horizon_values,
                    target,
                    (
                        "profile 0: horizon depths 0",
                        "profile 0: texture fractions 0",
                        "profile 0: salinity_index 0",
                    ),
                ),
                (
                    "profile values",
                    broken_profile_values,
                    target,
                    (
                        "profile 0: total depth",
                        "profile 0: moisture_index",
                        "profile 0: history depth/flux totals",
                    ),
                ),
                (
                    "natural stage coverage",
                    missing_natural_stage,
                    target,
                    (
                        "profile 0: natural stage coverage",
                        "soil_pedogenesis_step_count",
                    ),
                ),
                (
                    "negative step depth",
                    negative_step_depth,
                    target,
                    (
                        "profile 0: history depths 0",
                        "profile 0: production/erosion 0",
                        # step 0 replays a zero-duration natural stage, so its
                        # start and end depth must stay identical
                        "profile 0: zero-duration soil change 0",
                    ),
                ),
                (
                    "step discontinuity",
                    discontinuous_steps,
                    target,
                    (
                        "profile 0: history continuity 1",
                        "profile 0: production/erosion 1",
                    ),
                ),
                (
                    "step index range",
                    unbounded_step_index,
                    target,
                    ("profile 0: erosion_pressure_index 0",),
                ),
                (
                    "history mean",
                    broken_history_mean,
                    target,
                    ("profile 0: history mean mean_weathering_index",),
                ),
                (
                    "high erosion mirror",
                    flipped_erosion_flag,
                    target,
                    ("profile 0: high erosion mirror",),
                ),
            )
        )

    def test_biome_ecotone_region_mutations_are_rejected(self) -> None:
        stolen_cell_id = self.world["biome_ecotone_regions"][0]["cell_ids"][0]

        def invalid_cells(world: dict) -> None:
            world["biome_ecotone_regions"][0]["cell_ids"] = [9999]

        def broken_aggregates(world: dict) -> None:
            regions = world["biome_ecotone_regions"]
            regions[1]["cell_ids"] = list(regions[1]["cell_ids"]) + [
                regions[0]["cell_ids"][0]
            ]
            regions[0]["cell_count"] += 1
            regions[0]["mean_ecotone_confidence"] = 2.0
            regions[0]["mean_precipitation_mm_y"] = -1.0
            regions[0]["mean_temperature_c"] = "warm"

        target = "soils_and_ecotones/biome_ecotone_membership_and_ranges"
        self._run_cases(
            (
                (
                    "invalid cell ids",
                    invalid_cells,
                    target,
                    ("ecotone 0: cells", "ecotone assignment inverse"),
                ),
                (
                    "region aggregates",
                    broken_aggregates,
                    target,
                    (
                        "ecotone 0: count/area",
                        "ecotone 0: confidence",
                        "ecotone 0: climate values",
                        "ecotone 1: overlap",
                        "ecotone 1: count/area",
                        f"ecotone 1: cell mirror {stolen_cell_id}",
                    ),
                ),
            )
        )

    # ---- lakes and watersheds ------------------------------------------

    def test_lake_basin_membership_and_storage_mutations_are_rejected(self) -> None:
        def broken_aggregates(world: dict) -> None:
            basin = world["lake_basins"][0]
            basin["cell_count"] += 1
            basin["area_km2"] += 1.0e6
            basin["overflow_path_cell_ids"] = [0, 60]
            basin["outlet_cell_id"] = 9999
            basin["mean_water_depth_m"] = -1.0
            basin["avulsion_risk"] = 2.0
            basin["fill_fraction"] = 3.0
            basin["lake_cell_count"] = 9999

        def broken_overflow_flag(world: dict) -> None:
            basin = world["lake_basins"][0]
            basin["overflows"] = "yes"
            basin["overflow_index"] = 99.0

        target = "lakes_watersheds/lake_basin_membership_and_storage"
        self._run_cases(
            (
                (
                    "basin aggregates",
                    broken_aggregates,
                    target,
                    (
                        "basin 0: cell_count",
                        "basin 0: area",
                        "basin 0: overflow path",
                        "basin 0: outlet_cell_id",
                        "basin 0: mean_water_depth_m",
                        "basin 0: avulsion_risk",
                        "basin 0: fill_fraction",
                        "basin 0: lake_cell_count",
                    ),
                ),
                (
                    "overflow flag and index",
                    broken_overflow_flag,
                    target,
                    (
                        "basin 0: overflows",
                        "basin 0: overflow_index",
                        "basin 0: overflow_index replay",
                    ),
                ),
            )
        )

    def test_lake_overflow_history_and_channel_mutations_are_rejected(self) -> None:
        def unknown_basin(world: dict) -> None:
            world["lake_overflow_histories"][0]["lake_basin_id"] = 99

        def broken_steps(world: dict) -> None:
            history = world["lake_overflow_histories"][0]
            history["time_step_count"] += 1
            history["steps"][0]["inflow_km3"] = -1.0
            history["steps"][2]["end_volume_km3"] += 100.0
            history["steps"][4]["fill_fraction"] = 2.0

        def broken_totals(world: dict) -> None:
            history = world["lake_overflow_histories"][0]
            history["total_inflow_km3"] += 1.0
            history["total_spill_km3"] += 1.0
            history["total_sink_loss_km3"] += 1.0

        def malformed_channel(world: dict) -> None:
            world["lake_overflow_channel_histories"].append(
                {
                    "id": 0,
                    "lake_basin_id": 99,
                    "overflow_path_cell_ids": [0],
                    "steps": "not-a-list",
                    "time_step_count": 3,
                    "channel_segment_count": 7,
                }
            )

        target = "lakes_watersheds/lake_overflow_history_conservation"
        self._run_cases(
            (
                (
                    "unknown basin source",
                    unknown_basin,
                    target,
                    ("history 0: structure/source",),
                ),
                (
                    "step conservation",
                    broken_steps,
                    target,
                    (
                        "history 0: step counts",
                        "history 0: nonfinite/negative step 0",
                        "history 0: volume closure 2",
                        "history 0: discontinuity 3",
                        "history 0: bounded step indices 4",
                        "history 0: inflow aggregate",
                    ),
                ),
                (
                    "history totals",
                    broken_totals,
                    target,
                    (
                        "history 0: inflow aggregate",
                        "history 0: spill aggregate",
                        "history 0: sink aggregate",
                    ),
                ),
                (
                    "malformed channel record",
                    malformed_channel,
                    target,
                    (
                        "channel 0: source/path",
                        "channel 0: steps",
                        "channel 0: segment_count",
                        "lake_overflow_channel_history_count",
                    ),
                ),
            )
        )

    def test_watershed_topology_mutations_are_rejected(self) -> None:
        def duplicate_basin(world: dict) -> None:
            world["watersheds"][1]["basin_id"] = world["watersheds"][0]["basin_id"]

        def broken_aggregates(world: dict) -> None:
            watershed = world["watersheds"][0]
            watershed["cell_count"] += 1
            watershed["area_km2"] += 1.0e6
            watershed["main_channel_cell_ids"] = [9999]
            watershed["neighbor_watershed_ids"] = [0]
            watershed["main_channel_length_km"] = -1.0
            watershed["compactness_index"] = 2.0

        def asymmetric_neighbor(world: dict) -> None:
            watersheds = world["watersheds"]
            neighbor_id = watersheds[0]["neighbor_watershed_ids"][0]
            watersheds[neighbor_id]["neighbor_watershed_ids"] = [
                other
                for other in watersheds[neighbor_id]["neighbor_watershed_ids"]
                if other != 0
            ]

        neighbor_id = self.world["watersheds"][0]["neighbor_watershed_ids"][0]
        target = "lakes_watersheds/watershed_internal_topology_and_aggregates"
        self._run_cases(
            (
                (
                    "duplicate basin id",
                    duplicate_basin,
                    target,
                    (
                        "duplicate watershed basin IDs",
                        "watershed 1: cell_count",
                        "watershed 1: area",
                    ),
                ),
                (
                    "topology aggregates",
                    broken_aggregates,
                    target,
                    (
                        "watershed 0: cell_count",
                        "watershed 0: area",
                        "watershed 0: main-channel membership",
                        "watershed 0: main-channel path",
                        "watershed 0: neighbors",
                        "watershed 0: main_channel_length_km",
                        "watershed 0: compactness_index",
                        "watershed_main_channel_count",
                    ),
                ),
                (
                    "asymmetric neighbor",
                    asymmetric_neighbor,
                    target,
                    (f"watershed 0: asymmetric neighbor {neighbor_id}",),
                ),
            )
        )

    # ---- rivers ---------------------------------------------------------

    def test_river_evolution_event_and_history_mutations_are_rejected(self) -> None:
        def broken_event(world: dict) -> None:
            event = world["river_network_evolution_events"][0]
            event["source_cell_id"] = 9999
            event["risk"] = 2.0
            event["type"] = "bogus"

        def unknown_event_source(world: dict) -> None:
            world["river_reorganization_histories"][0][
                "river_network_evolution_event_id"
            ] = 99

        def broken_history(world: dict) -> None:
            history = world["river_reorganization_histories"][0]
            history["source_cell_id"] = 9999
            history["step_count"] += 1
            history["projected_flow_to_cell_id"] = 9999
            history["steps"][0]["channelization_index"] = 2.0
            history["steps"][0]["elapsed_years"] = -1.0

        target = "river_evolution_channels/evolution_event_history_links"
        self._run_cases(
            (
                (
                    "event values",
                    broken_event,
                    target,
                    (
                        "event 0: source_cell_id",
                        "event 0: risk/flow",
                        "event 0: type",
                        "history 0: event source mirror",
                    ),
                ),
                (
                    "unknown event source",
                    unknown_event_source,
                    target,
                    (
                        "history 0: event/steps",
                        "events and histories are not one-to-one",
                    ),
                ),
                (
                    "history values",
                    broken_history,
                    target,
                    (
                        "history 0: event source mirror",
                        "history 0: step_count",
                        "history 0: projected target",
                        "history 0: channelization_index step 0",
                        "history 0: elapsed_years step 0",
                    ),
                ),
            )
        )

    def test_river_channel_and_hydraulic_reach_mutations_are_rejected(self) -> None:
        channel_mirror_id = self.world["river_channel_systems"][0]["cell_ids"][1]
        reach_mirror_id = self.world["river_hydraulic_reaches"][0]["cell_ids"][0]
        # Clearing ``is_river`` on a channel cell is not just a mirror break:
        # placer/ore genesis and deposit accessibility are replayed from that
        # flag, as is freshwater fish habitat, so the derived registries must
        # disagree on that exact cell.
        channel_deposit_ids = [
            deposit["id"]
            for deposit in self.world["resource_deposits"]
            if deposit["cell_id"] == channel_mirror_id
        ]
        self.assertEqual(len(channel_deposit_ids), 1)
        channel_deposit_id = channel_deposit_ids[0]

        def invalid_channel_cells(world: dict) -> None:
            world["river_channel_systems"][0]["cell_ids"] = [9999]

        def broken_channel_aggregates(world: dict) -> None:
            systems = world["river_channel_systems"]
            systems[1]["cell_ids"] = list(systems[1]["cell_ids"]) + [
                systems[0]["cell_ids"][0]
            ]
            systems[0]["cell_count"] += 1
            systems[0]["area_km2"] += 1.0e6
            systems[0]["source_cell_id"] = 9999
            systems[0]["length_km"] = -1.0
            systems[0]["mean_floodplain_connectivity_index"] = 2.0
            _cells_by_id(world)[channel_mirror_id]["is_river"] = False

        def invalid_reach_cells(world: dict) -> None:
            world["river_hydraulic_reaches"][0]["cell_ids"] = [9999]

        def broken_reach_aggregates(world: dict) -> None:
            reaches = world["river_hydraulic_reaches"]
            reaches[1]["cell_ids"] = list(reaches[1]["cell_ids"]) + [
                reaches[0]["cell_ids"][0]
            ]
            reaches[0]["cell_count"] += 1
            reaches[0]["area_km2"] += 1.0e6
            reaches[0]["length_km"] = -1.0
            reaches[0]["mean_channel_capacity_index"] = 2.0
            _cells_by_id(world)[reach_mirror_id]["river_hydraulic_reach_id"] = 2

        channels = "river_evolution_channels/channel_system_membership_and_geometry"
        reaches = "river_evolution_channels/hydraulic_reach_source_links_and_ranges"
        self._run_cases(
            (
                (
                    "channel cell sources",
                    invalid_channel_cells,
                    channels,
                    (
                        "channel 0: cell_ids",
                        "channel membership does not invert cell assignments",
                        "river_channel_cell_count",
                    ),
                ),
                (
                    "channel aggregates",
                    broken_channel_aggregates,
                    channels,
                    (
                        "channel 0: count/area",
                        "channel 0: source/outlet",
                        f"channel 0: cell mirror {channel_mirror_id}",
                        "channel 0: length_km",
                        "channel 0: floodplain connectivity",
                        "channel 1: overlap",
                        "total_river_channel_length_km",
                    ),
                    (
                        "geologic_resources/resource_deposit_sources_and_ranges",
                        "geologic_resources/ore_system_membership_and_formation_sources",
                        "ecosystems_reefs_species_wildfire/species_range_inverse_links_and_envelopes",
                    ),
                    {
                        "geologic_resources/resource_deposit_sources_and_ranges": (
                            f"deposit {channel_deposit_id}:"
                            " accessibility_index replay",
                            f"deposit {channel_deposit_id}:"
                            " economic_viability_index replay",
                        ),
                        "geologic_resources/ore_system_membership_and_formation_sources": (
                            f"cell {channel_mirror_id}:"
                            " ore_genesis_potential_index replay",
                            f"cell {channel_mirror_id}:"
                            " placer_concentration_index replay",
                            "ore 0: mean_placer_concentration_index replay",
                        ),
                        "ecosystems_reefs_species_wildfire/species_range_inverse_links_and_envelopes": (
                            f"species habitat cell {channel_mirror_id}: species_freshwater_habitat_eligible mismatch",
                            f"species habitat cell {channel_mirror_id}: species_freshwater_fish_score_supported mismatch",
                            f"species habitat cell {channel_mirror_id}: species_freshwater_fishery_input_mode mismatch",
                        ),
                    },
                ),
                (
                    "reach cell sources",
                    invalid_reach_cells,
                    reaches,
                    (
                        "reach 0: cell_ids",
                        "reach membership does not invert cell assignments",
                        "river_hydraulic_cell_count",
                    ),
                ),
                (
                    "reach aggregates",
                    broken_reach_aggregates,
                    reaches,
                    (
                        "reach 0: count/area",
                        f"reach 0: cell mirror {reach_mirror_id}",
                        "reach 0: length_km",
                        "reach 0: mean_channel_capacity_index",
                        "reach 1: overlap",
                        "reach 1: channel source",
                    ),
                ),
            )
        )

    # ---- sequence stratigraphy -----------------------------------------

    def test_sequence_stratigraphy_mutations_are_rejected(self) -> None:
        def unknown_column(world: dict) -> None:
            world["sequence_stratigraphy_histories"][0][
                "stratigraphic_column_id"
            ] = 999

        def broken_basin_source(world: dict) -> None:
            history = world["sequence_stratigraphy_histories"][0]
            column_id = history["stratigraphic_column_id"]
            for column in world["stratigraphic_columns"]:
                if column["id"] == column_id:
                    column["basin_id"] = 999
            history["time_step_count"] += 1

        def broken_step_categories(world: dict) -> None:
            step = world["sequence_stratigraphy_histories"][0]["steps"][0]
            step["sequence_surface"] = "bogus"
            step["systems_tract"] = "bogus"
            step["shoreline_trajectory"] = "bogus"
            step["start_age_ma"] = -1.0

        def broken_aggregates(world: dict) -> None:
            history = world["sequence_stratigraphy_histories"][0]
            history["sequence_event_count"] += 1
            history["sequence_boundary_count"] += 1
            history["systems_tract_counts"] = {}

        target = "sequence_stratigraphy/source_links_steps_and_aggregates"
        self._run_cases(
            (
                (
                    "unknown column source",
                    unknown_column,
                    target,
                    (
                        "history 0: source/steps",
                        "sequence_stratigraphy_step_count",
                        "sequence_stratigraphy_event_count",
                        "sequence_boundary_count",
                        "maximum_flooding_surface_count",
                        "regressive_surface_count",
                        "systems_tract_counts",
                        "shoreline_trajectory_counts",
                    ),
                ),
                (
                    "basin source coverage",
                    broken_basin_source,
                    target,
                    (
                        "history 0: basin source",
                        "history 0: step count/source coverage",
                    ),
                    ("geologic_resources/sedimentary_system_source_chain",),
                ),
                (
                    "step categories",
                    broken_step_categories,
                    target,
                    (
                        "history 0: surface 0",
                        "history 0: tract 0",
                        "history 0: trajectory 0",
                        "history 0: start_age_ma 0",
                        "history 0: reversed age 0",
                        "history 0: categorical aggregates",
                        "sequence_boundary_count",
                        "systems_tract_counts",
                        "shoreline_trajectory_counts",
                    ),
                ),
                (
                    "categorical aggregates",
                    broken_aggregates,
                    target,
                    (
                        "history 0: event_count",
                        "history 0: sequence_boundary_count",
                        "history 0: categorical aggregates",
                    ),
                ),
            )
        )

    # ---- cryosphere -----------------------------------------------------

    def test_ice_sheet_history_conservation_mutations_are_rejected(self) -> None:
        def unknown_sheet(world: dict) -> None:
            world["ice_sheet_histories"][0]["ice_sheet_id"] = 99

        def broken_steps(world: dict) -> None:
            history = world["ice_sheet_histories"][0]
            history["time_step_count"] += 1
            history["steps"][0]["surface_balance_km3"] = "n/a"
            history["steps"][1]["start_area_km2"] = -1.0
            history["steps"][2]["end_volume_km3"] += 1.0e6
            history["steps"][3]["basal_sliding_index"] = 2.0

        def broken_totals(world: dict) -> None:
            history = world["ice_sheet_histories"][0]
            history["initial_volume_km3"] += 1.0e6
            history["total_surface_balance_km3"] += 1.0e6

        target = "cryosphere_permafrost_glacial/ice_sheet_history_conservation"
        self._run_cold_cases(
            (
                (
                    "unknown sheet source",
                    unknown_sheet,
                    target,
                    (
                        "history 0: source/steps",
                        "ice sheet/history coverage",
                    ),
                ),
                (
                    "step conservation",
                    broken_steps,
                    target,
                    (
                        "history 0: step_count",
                        "history 0: nonfinite step 0",
                        "history 0: negative physical value 1",
                        "history 0: volume closure 2",
                        "history 0: discontinuity 3",
                        "history 0: bounded indices 3",
                    ),
                ),
                (
                    "endpoint totals",
                    broken_totals,
                    target,
                    (
                        "history 0: endpoint aggregates",
                        "history 0: total_surface_balance_km3",
                    ),
                ),
            )
        )

    def test_ice_stability_and_flowline_mutations_are_rejected(self) -> None:
        def broken_stability(world: dict) -> None:
            stability = world["ice_sheet_stability_histories"][0]
            stability["ice_sheet_id"] = 99
            stability["mean_stability_index"] = 2.0
            stability["steps"][0]["balance_deficit_index"] = 2.0

        def broken_stability_steps(world: dict) -> None:
            world["ice_sheet_stability_histories"][0]["time_step_count"] += 1

        def broken_flowline_path(world: dict) -> None:
            flowline = world["ice_flowline_histories"][0]
            flowline["flowline_cell_ids"] = [9999]
            flowline["ice_sheet_id"] = 99

        def broken_flowline_steps(world: dict) -> None:
            world["ice_flowline_histories"][0]["time_step_count"] += 1

        def broken_flowline_values(world: dict) -> None:
            flowline = world["ice_flowline_histories"][0]
            flowline["steps"][0]["cell_id"] = 9999
            flowline["steps"][1]["accumulation_flux_km3_y"] = -1.0
            flowline["steps"][1]["balance_residual_km3_y"] = 1.0
            flowline["steps"][1]["basal_sliding_index"] = 2.0

        target = "cryosphere_permafrost_glacial/stability_and_flowline_sources"
        self._run_cold_cases(
            (
                (
                    "stability sources",
                    broken_stability,
                    target,
                    (
                        "stability histories do not cover source sheets",
                        "stability 0: mean_stability_index",
                        "stability 0: balance_deficit_index 0",
                    ),
                ),
                (
                    "stability step count",
                    broken_stability_steps,
                    target,
                    ("stability 0: steps",),
                ),
                (
                    "flowline path",
                    broken_flowline_path,
                    target,
                    (
                        "flowline 0: path",
                        "flowline 0: source",
                        "flowline 0: step/path cells",
                    ),
                ),
                (
                    "flowline step count",
                    broken_flowline_steps,
                    target,
                    ("flowline 0: steps",),
                ),
                (
                    "flowline flux values",
                    broken_flowline_values,
                    target,
                    (
                        "flowline 0: step/path cells",
                        "flowline 0: flux values 1",
                        "flowline 0: balance residual 1",
                        "flowline 0: basal_sliding_index 1",
                    ),
                ),
            )
        )

    def test_permafrost_and_glacial_membership_mutations_are_rejected(self) -> None:
        mirror_cell_id = cached_cold_world_readonly()["permafrost_regions"][0]["cell_ids"][1]

        def invalid_cells(world: dict) -> None:
            world["permafrost_regions"][0]["cell_ids"] = [9999]

        def broken_aggregates(world: dict) -> None:
            regions = world["permafrost_regions"]
            regions[1]["cell_ids"] = list(regions[1]["cell_ids"]) + [
                regions[0]["cell_ids"][0]
            ]
            regions[0]["cell_count"] += 1
            regions[0]["area_km2"] += 1.0e6
            _cells_by_id(world)[mirror_cell_id]["permafrost_region_id"] = 1

        def unbounded_cell_values(world: dict) -> None:
            world["cells"][0]["ground_ice_content_index"] = 2.0
            world["cells"][0]["active_layer_depth_m"] = -1.0

        target = "cryosphere_permafrost_glacial/permafrost_and_glacial_membership"
        self._run_cold_cases(
            (
                (
                    "invalid cell ids",
                    invalid_cells,
                    target,
                    ("permafrost 0: cell_ids", "permafrost: assignment inverse"),
                ),
                (
                    "region aggregates",
                    broken_aggregates,
                    target,
                    (
                        "permafrost 0: count/area",
                        f"permafrost 0: cell mirror {mirror_cell_id}",
                        "permafrost 1: overlap",
                    ),
                ),
                (
                    "cell diagnostics",
                    unbounded_cell_values,
                    target,
                    (
                        "cell 0: ground_ice_content_index",
                        "cell 0: active_layer_depth_m",
                    ),
                ),
            )
        )

    # ---- aquifers, wetlands, karst --------------------------------------

    def test_aquifer_membership_mutations_are_rejected(self) -> None:
        mirror_cell_id = self.world["aquifer_systems"][0]["cell_ids"][1]
        stolen_cell_id = self.world["aquifer_systems"][0]["cell_ids"][0]

        def invalid_cells(world: dict) -> None:
            world["aquifer_systems"][0]["cell_ids"] = [9999]

        def broken_aggregates(world: dict) -> None:
            systems = world["aquifer_systems"]
            systems[1]["cell_ids"] = list(systems[1]["cell_ids"]) + [
                systems[0]["cell_ids"][0]
            ]
            systems[0]["basin_id"] = 999
            systems[0]["mean_aquifer_storage_index"] = 2.0
            systems[0]["mean_groundwater_recharge_mm_y"] = -1.0
            _cells_by_id(world)[mirror_cell_id]["aquifer_system_id"] = 1

        def unbounded_cell_values(world: dict) -> None:
            world["cells"][0]["aquifer_quality_index"] = 2.0
            world["cells"][0]["groundwater_recharge_mm_y"] = -1.0

        target = "aquifers_wetlands_karst/aquifer_membership_models_and_ranges"
        self._run_cases(
            (
                (
                    "invalid cell ids",
                    invalid_cells,
                    target,
                    ("aquifer 0: cell_ids", "aquifer assignment inverse"),
                ),
                (
                    "system aggregates",
                    broken_aggregates,
                    target,
                    (
                        "aquifer 0: basin source",
                        f"aquifer 0: cell mirror {mirror_cell_id}",
                        "aquifer 0: mean_aquifer_storage_index",
                        "aquifer 0: mean_groundwater_recharge_mm_y",
                        "aquifer 1: overlap",
                        "aquifer 1: count/area",
                        f"aquifer 1: cell mirror {stolen_cell_id}",
                    ),
                ),
                (
                    "cell diagnostics",
                    unbounded_cell_values,
                    target,
                    (
                        "cell 0: aquifer_quality_index",
                        "cell 0: groundwater_recharge_mm_y",
                    ),
                ),
            )
        )

    def test_wetland_and_karst_source_mutations_are_rejected(self) -> None:
        mirror_cell_id = self.world["wetland_systems"][0]["cell_ids"][0]

        def invalid_cells(world: dict) -> None:
            world["wetland_systems"][0]["cell_ids"] = [9999]

        def broken_aggregates(world: dict) -> None:
            systems = world["wetland_systems"]
            systems[1]["cell_ids"] = list(systems[1]["cell_ids"]) + [
                systems[0]["cell_ids"][0]
            ]
            systems[0]["cell_count"] += 1
            systems[0]["linked_watershed_ids"] = [999]
            _cells_by_id(world)[mirror_cell_id]["wetland_system_id"] = 3

        def orphan_karst_record(world: dict) -> None:
            cell = world["cells"][0]
            world["karst_systems"].append(
                {
                    "id": 0,
                    "cell_ids": [cell["id"]],
                    "cell_count": 1,
                    "area_km2": cell["area_km2"],
                    "aquifer_system_ids": [999],
                }
            )

        def unbounded_cell_values(world: dict) -> None:
            world["cells"][0]["cave_development_index"] = 2.0

        target = "aquifers_wetlands_karst/wetland_karst_membership_and_sources"
        self._run_cases(
            (
                (
                    "invalid cell ids",
                    invalid_cells,
                    target,
                    ("wetland 0: cell_ids", "wetland: assignment inverse"),
                ),
                (
                    "system aggregates",
                    broken_aggregates,
                    target,
                    (
                        "wetland 0: count/area",
                        f"wetland 0: cell mirror {mirror_cell_id}",
                        "wetland 0: watersheds",
                        "wetland 1: overlap",
                    ),
                ),
                (
                    "orphan karst record",
                    orphan_karst_record,
                    target,
                    (
                        "karst 0: cell mirror 0",
                        "karst 0: aquifers",
                        "karst: assignment inverse",
                        "karst_system_count",
                    ),
                ),
                (
                    "cell diagnostics",
                    unbounded_cell_values,
                    target,
                    ("cell 0: cave_development_index",),
                ),
            )
        )

    # ---- ecosystems ------------------------------------------------------

    def test_succession_and_renewable_resource_mutations_are_rejected(self) -> None:
        def invalid_succession_cell(world: dict) -> None:
            world["vegetation_succession_histories"][0]["cell_id"] = 9999

        def broken_succession_values(world: dict) -> None:
            history = world["vegetation_succession_histories"][0]
            history["step_count"] += 1
            history["steps"][0]["biomass_index"] = 2.0
            history["steps"][0]["years_since_start"] = -1.0

        def broken_renewable(world: dict) -> None:
            record = world["renewable_resource_records"][0]
            record["resource_type"] = "bogus"
            record["productivity_index"] = 2.0
            record["regeneration_years"] = 0

        def unbounded_cell_values(world: dict) -> None:
            world["cells"][0]["species_richness_index"] = 2.0

        target = "ecosystems_reefs_species_wildfire/succession_and_renewable_sources"
        self._run_cases(
            (
                (
                    "succession cell source",
                    invalid_succession_cell,
                    target,
                    ("succession 0: source/steps",),
                ),
                (
                    "succession values",
                    broken_succession_values,
                    target,
                    (
                        "succession 0: step/endpoints",
                        "succession 0: biomass_index 0",
                        "succession 0: years 0",
                    ),
                ),
                (
                    "renewable record",
                    broken_renewable,
                    target,
                    (
                        "renewable 0: source/type",
                        "renewable 0: productivity_index",
                        "renewable 0: regeneration",
                    ),
                ),
                (
                    "cell diagnostics",
                    unbounded_cell_values,
                    target,
                    ("cell 0: species_richness_index",),
                ),
            )
        )

    def test_injected_reef_registry_records_are_rejected(self) -> None:
        self.assertEqual(self.world["reef_systems"], [])

        def overlapping_reefs(world: dict) -> None:
            cell = world["cells"][0]
            world["reef_systems"].extend(
                [
                    {
                        "id": 0,
                        "cell_ids": [cell["id"]],
                        "cell_count": 5,
                        "area_km2": 1.0,
                        "fishery_resource_record_ids": [9999],
                        "mean_reef_growth_index": 2.0,
                        "mean_reef_sediment_stress_index": 0.5,
                        "mean_reef_wave_exposure_index": 0.5,
                        "mean_reef_island_support_index": 0.5,
                        "mean_reef_bleaching_risk_index": 0.5,
                    },
                    {
                        "id": 1,
                        "cell_ids": [cell["id"]],
                        "cell_count": 1,
                        "area_km2": cell["area_km2"],
                        "fishery_resource_record_ids": [],
                        "mean_reef_growth_index": 0.5,
                        "mean_reef_sediment_stress_index": 0.5,
                        "mean_reef_wave_exposure_index": 0.5,
                        "mean_reef_island_support_index": 0.5,
                        "mean_reef_bleaching_risk_index": 0.5,
                    },
                ]
            )

        def invalid_reef_cells(world: dict) -> None:
            world["reef_systems"].append(
                {
                    "id": 0,
                    "cell_ids": [9999],
                    "cell_count": 1,
                    "area_km2": 1.0,
                    "fishery_resource_record_ids": [],
                }
            )

        def unbounded_cell_values(world: dict) -> None:
            world["cells"][0]["reef_growth_index"] = 2.0

        target = "ecosystems_reefs_species_wildfire/reef_membership_sources_and_ranges"
        self._run_cases(
            (
                (
                    "overlapping reef records",
                    overlapping_reefs,
                    target,
                    (
                        "reef 0: count/area",
                        "reef 0: cell mirror 0",
                        "reef 0: fishery sources",
                        "reef 0: mean_reef_growth_index",
                        "reef 1: overlap",
                        "reef assignment inverse",
                        "reef_system_count",
                        "reef_cell_count",
                        "reef_total_area_km2",
                    ),
                ),
                (
                    "invalid reef cells",
                    invalid_reef_cells,
                    target,
                    (
                        "reef 0: cell_ids",
                        "reef_system_count",
                        "reef_total_area_km2",
                    ),
                ),
                (
                    "cell diagnostics",
                    unbounded_cell_values,
                    target,
                    ("cell 0: reef_growth_index",),
                ),
            )
        )

    def test_species_range_source_and_envelope_mutations_are_rejected(self) -> None:
        def invalid_cells(world: dict) -> None:
            world["species_range_records"][0]["cell_ids"] = [9999]

        def broken_links(world: dict) -> None:
            record = world["species_range_records"][0]
            record["cell_count"] += 1
            record["wetland_system_ids"] = [999]
            record["endemism_index"] = 2.0

        def non_list_habitat_ids(world: dict) -> None:
            world["species_range_records"][0]["reef_system_ids"] = "none"

        def non_integer_habitat_ids(world: dict) -> None:
            world["species_range_records"][0]["wetland_system_ids"] = ["one"]

        def malformed_envelope(world: dict) -> None:
            world["species_range_records"][0]["climate_envelope"] = {
                "min_temperature_c": 1.0
            }

        def unordered_envelope(world: dict) -> None:
            world["species_range_records"][0]["climate_envelope"][
                "mean_temperature_c"
            ] = 999.0

        target = (
            "ecosystems_reefs_species_wildfire/"
            "species_range_inverse_links_and_envelopes"
        )
        self._run_cases(
            (
                (
                    "invalid cell ids",
                    invalid_cells,
                    target,
                    (
                        "range 0: cell_ids",
                        "cell 0: species inverse",
                        "species_range_cell_count",
                    ),
                ),
                (
                    "habitat links",
                    broken_links,
                    target,
                    (
                        "range 0: count/area",
                        "range 0: wetland_system_ids",
                        "range 0: endemism_index",
                    ),
                ),
                (
                    "habitat ids not a list",
                    non_list_habitat_ids,
                    target,
                    ("range 0: reef_system_ids",),
                ),
                (
                    "habitat ids not integers",
                    non_integer_habitat_ids,
                    target,
                    ("range 0: wetland_system_ids",),
                ),
                (
                    "malformed climate envelope",
                    malformed_envelope,
                    target,
                    ("range 0: climate envelope",),
                ),
                (
                    "unordered climate envelope",
                    unordered_envelope,
                    target,
                    ("range 0: climate envelope order",),
                ),
            )
        )

    def test_wildfire_spread_history_mutations_are_rejected(self) -> None:
        wildfire_cell_id = self.world["wildfire_spread_histories"][0]["cell_ids"][0]

        def invalid_ignition(world: dict) -> None:
            world["wildfire_spread_histories"][0]["ignition_cell_id"] = 9999

        def broken_counts(world: dict) -> None:
            history = world["wildfire_spread_histories"][0]
            history["cell_count"] += 1
            history["spread_step_count"] += 1

        def broken_steps(world: dict) -> None:
            history = world["wildfire_spread_histories"][0]
            history["steps"][0]["active_front_cell_ids"] = [9999]
            history["steps"][1]["cumulative_burned_cell_count"] = 0
            history["steps"][2]["containment_index"] = 2.0
            history["steps"][3]["burned_area_km2"] = -1.0
            history["mean_firebreak_index"] = 2.0

        def broken_inverse(world: dict) -> None:
            history = world["wildfire_spread_histories"][0]
            _cells_by_id(world)[history["cell_ids"][0]][
                "wildfire_spread_history_ids"
            ] = []

        target = "ecosystems_reefs_species_wildfire/wildfire_inverse_links_and_steps"
        self._run_cases(
            (
                (
                    "ignition source",
                    invalid_ignition,
                    target,
                    (
                        "wildfire 0: cells/ignition",
                        f"cell {wildfire_cell_id}: wildfire inverse",
                        "wildfire_disturbance_cell_count",
                    ),
                ),
                (
                    "record counts",
                    broken_counts,
                    target,
                    ("wildfire 0: count/area", "wildfire 0: steps"),
                ),
                (
                    "spread steps",
                    broken_steps,
                    target,
                    (
                        "wildfire 0: step cells 0",
                        "wildfire 0: cumulative count 1",
                        "wildfire 0: containment_index 2",
                        "wildfire 0: burned area 3",
                        "wildfire 0: mean_firebreak_index",
                    ),
                ),
                (
                    "cell inverse",
                    broken_inverse,
                    target,
                    (f"cell {wildfire_cell_id}: wildfire inverse",),
                ),
            )
        )

    # ---- geologic resources ----------------------------------------------

    def test_resource_deposit_source_mutations_are_rejected(self) -> None:
        def invalid_cell(world: dict) -> None:
            world["resource_deposits"][0]["cell_id"] = 9999

        def broken_mirrors(world: dict) -> None:
            deposit = world["resource_deposits"][0]
            deposit["resource"] = "unobtainium"
            deposit["area_km2"] += 1.0e6
            deposit["renewability_index"] = 2.0
            deposit["formation_evidence"] = "none"

        target = "geologic_resources/resource_deposit_sources_and_ranges"
        self._run_cases(
            (
                (
                    "deposit cell source",
                    invalid_cell,
                    target,
                    ("deposit 0: cell source",),
                    (
                        "geologic_resources/sedimentary_system_source_chain",
                        "geologic_resources/commodity_occurrence_deposit_links",
                    ),
                ),
                (
                    "deposit mirrors",
                    broken_mirrors,
                    target,
                    (
                        "deposit 0: resource mirror",
                        "deposit 0: renewability_index replay",
                        "deposit 0: area source",
                        "deposit 0: renewability_index",
                        "deposit 0: formation evidence/resource",
                        "resource_deposit_total_area_km2",
                    ),
                    ("geologic_resources/commodity_occurrence_deposit_links",),
                ),
            )
        )

    def test_ore_system_source_and_formation_mutations_are_rejected(self) -> None:
        ore_system = self.world["ore_genesis_systems"][0]
        mirror_cell_id = ore_system["cell_ids"][1]
        member_cells = set(ore_system["cell_ids"])
        foreign_cell_id = next(
            cell["id"] for cell in self.world["cells"] if cell["id"] not in member_cells
        )
        foreign_deposit_id = next(
            deposit["id"]
            for deposit in self.world["resource_deposits"]
            if deposit["cell_id"] not in member_cells
        )

        def invalid_cells(world: dict) -> None:
            world["ore_genesis_systems"][0]["cell_ids"] = [9999]

        def overlapping_systems(world: dict) -> None:
            world["ore_genesis_systems"].append(
                dict(world["ore_genesis_systems"][0], id=1)
            )

        def broken_sources(world: dict) -> None:
            system = world["ore_genesis_systems"][0]
            system["cell_count"] += 1
            system["area_km2"] += 1.0e6
            system["resource_deposit_ids"] = list(
                system["resource_deposit_ids"]
            ) + [foreign_deposit_id]
            system["representative_cell_id"] = 9999
            system["fault_system_ids"] = [999]
            system["mean_ore_genesis_potential_index"] = 2.0
            system["mean_resource_viability_index"] = 2.0
            _cells_by_id(world)[mirror_cell_id]["ore_genesis_system_id"] = 7

        def broken_step_count(world: dict) -> None:
            world["ore_genesis_systems"][0]["formation_step_count"] += 1

        def broken_step_sources(world: dict) -> None:
            steps = world["ore_genesis_systems"][0]["formation_steps"]
            steps[0]["active_cell_ids"] = [foreign_cell_id]
            steps[1]["linked_resource_deposit_ids"] = [foreign_deposit_id]
            steps[2]["mean_ore_genesis_potential_index"] = 2.0

        target = "geologic_resources/ore_system_membership_and_formation_sources"
        self._run_cases(
            (
                (
                    "invalid cell ids",
                    invalid_cells,
                    target,
                    (
                        "ore 0: cell_ids",
                        "ore assignment inverse",
                        "ore_genesis_cell_count",
                    ),
                ),
                (
                    "overlapping systems",
                    overlapping_systems,
                    target,
                    (
                        "ore 1: overlap",
                        "ore_genesis_system_count",
                        "ore_genesis_total_area_km2",
                    ),
                ),
                (
                    "system sources",
                    broken_sources,
                    target,
                    (
                        "ore 0: count/area",
                        "ore 0: deposit sources",
                        "ore 0: representative",
                        "ore 0: fault_system_ids",
                        f"ore 0: cell mirror {mirror_cell_id}",
                        "ore 0: mean_ore_genesis_potential_index",
                        "ore 0: mean_resource_viability_index",
                        # the stored aggregates no longer match a replay of
                        # magic_geo.ore_genesis over the same cells
                        "ore 0: mean_ore_genesis_potential_index replay",
                        "ore 0: mean_resource_viability_index replay",
                        "ore 0: ore_genesis_confidence_index replay",
                        "ore_genesis_total_area_km2",
                    ),
                ),
                (
                    "formation step count",
                    broken_step_count,
                    target,
                    ("ore 0: formation steps",),
                ),
                (
                    "formation step sources",
                    broken_step_sources,
                    target,
                    (
                        "ore 0: step cells 0",
                        "ore 0: step replay 0",
                        "ore 0: step deposits 1",
                        "ore 0: step replay 1",
                        "ore 0: step values 2",
                        "ore 0: step replay 2",
                    ),
                ),
            )
        )

    def test_sedimentary_and_petroleum_chain_mutations_are_rejected(self) -> None:
        petroleum_mirror_id = self.world["petroleum_migration_systems"][0][
            "cell_ids"
        ][1]
        petroleum_member_cells = set(
            self.world["petroleum_migration_systems"][0]["cell_ids"]
        )
        foreign_cell_id = next(
            cell["id"]
            for cell in self.world["cells"]
            if cell["id"] not in petroleum_member_cells
        )

        def invalid_sedimentary_cells(world: dict) -> None:
            world["sedimentary_resource_systems"][0]["cell_ids"] = [9999]

        def broken_sedimentary_sources(world: dict) -> None:
            system = world["sedimentary_resource_systems"][0]
            system["stratigraphic_column_id"] = 999
            system["cell_count"] += 1
            system["area_km2"] += 1.0e6
            system["resource_deposit_ids"] = [9999]
            system["source_rock_index"] = 2.0
            system["depositional_age_ma"] = -1.0

        def mismatched_basin(world: dict) -> None:
            world["sedimentary_resource_systems"][0]["basin_id"] = 999

        def invalid_petroleum_cells(world: dict) -> None:
            world["petroleum_migration_systems"][0]["cell_ids"] = [9999]

        def overlapping_petroleum(world: dict) -> None:
            systems = world["petroleum_migration_systems"]
            systems[1]["cell_ids"] = list(systems[1]["cell_ids"]) + [
                systems[0]["cell_ids"][0]
            ]

        def unknown_source_system(world: dict) -> None:
            world["petroleum_migration_systems"][0][
                "sedimentary_resource_system_id"
            ] = 999

        def broken_petroleum_sources(world: dict) -> None:
            system = world["petroleum_migration_systems"][0]
            system["basin_id"] = 999
            system["cell_count"] += 1
            system["area_km2"] += 1.0e6
            system["trap_cell_ids"] = [9999]
            system["mean_source_rock_index"] = 2.0
            _cells_by_id(world)[petroleum_mirror_id]["petroleum_system_id"] = 6

        def broken_migration_steps(world: dict) -> None:
            world["petroleum_migration_systems"][0]["path_step_count"] += 1

        def broken_migration_path(world: dict) -> None:
            step = world["petroleum_migration_systems"][0]["migration_steps"][0]
            step["path_cell_ids"] = [
                step["path_cell_ids"][0],
                foreign_cell_id,
            ]

        def reversed_migration_path(world: dict) -> None:
            step = world["petroleum_migration_systems"][0]["migration_steps"][0]
            step["path_cell_ids"] = list(reversed(step["path_cell_ids"]))

        def broken_migration_values(world: dict) -> None:
            step = world["petroleum_migration_systems"][0]["migration_steps"][0]
            step["hydrocarbon_charge_index"] = 2.0
            step["migration_distance_km"] = -1.0

        sedimentary = "geologic_resources/sedimentary_system_source_chain"
        petroleum = "geologic_resources/petroleum_migration_source_paths"
        self._run_cases(
            (
                (
                    "sedimentary cell sources",
                    invalid_sedimentary_cells,
                    sedimentary,
                    (
                        "sedimentary 0: cells",
                        "sedimentary_resource_system_cell_count",
                    ),
                ),
                (
                    "sedimentary source chain",
                    broken_sedimentary_sources,
                    sedimentary,
                    (
                        "sedimentary 0: basin/column/history source",
                        "sedimentary 0: count/area",
                        "sedimentary 0: deposits",
                        "sedimentary 0: source_rock_index",
                        "sedimentary 0: depositional_age_ma",
                        "sedimentary_resource_system_total_area_km2",
                    ),
                    (petroleum,),
                    {
                        petroleum: (
                            "petroleum 0: stratigraphic_column_id source mirror",
                        )
                    },
                ),
                (
                    "sedimentary basin mismatch",
                    mismatched_basin,
                    sedimentary,
                    ("sedimentary 0: basin source mismatch",),
                    (petroleum,),
                ),
                (
                    "petroleum cell sources",
                    invalid_petroleum_cells,
                    petroleum,
                    (
                        "petroleum 0: cells",
                        "petroleum assignment inverse",
                        "petroleum_migration_cell_count",
                    ),
                ),
                (
                    "petroleum overlap",
                    overlapping_petroleum,
                    petroleum,
                    ("petroleum 1: overlap", "petroleum 1: count/area"),
                ),
                (
                    "petroleum source system",
                    unknown_source_system,
                    petroleum,
                    ("petroleum 0: source system",),
                ),
                (
                    "petroleum source mirrors",
                    broken_petroleum_sources,
                    petroleum,
                    (
                        "petroleum 0: basin_id source mirror",
                        "petroleum 0: count/area",
                        "petroleum 0: trap_cell_ids",
                        f"petroleum 0: cell mirror {petroleum_mirror_id}",
                        "petroleum 0: mean_source_rock_index",
                        "petroleum_migration_total_area_km2",
                    ),
                ),
                (
                    "petroleum migration step count",
                    broken_migration_steps,
                    petroleum,
                    ("petroleum 0: migration steps",),
                ),
                (
                    "petroleum path leaves the system",
                    broken_migration_path,
                    petroleum,
                    ("petroleum 0: path 0", "petroleum 0: path endpoints 0"),
                ),
                (
                    "petroleum path endpoints",
                    reversed_migration_path,
                    petroleum,
                    ("petroleum 0: path endpoints 0",),
                ),
                (
                    "petroleum migration values",
                    broken_migration_values,
                    petroleum,
                    (
                        "petroleum 0: hydrocarbon_charge_index 0",
                        "petroleum 0: distance 0",
                    ),
                ),
            )
        )

    def test_commodity_occurrence_mirror_mutations_are_rejected(self) -> None:
        def orphan_deposit_source(world: dict) -> None:
            world["commodity_occurrences"][0]["resource_deposit_id"] = 9999

        def broken_mirrors(world: dict) -> None:
            occurrence = world["commodity_occurrences"][0]
            occurrence["cell_id"] = 9999
            occurrence["source_resource"] = "unobtainium"
            occurrence["area_km2"] += 1.0e6
            occurrence["occurrence_potential_index"] = 2.0

        self._run_cases(
            (
                (
                    "unknown deposit source",
                    orphan_deposit_source,
                    "geologic_resources/commodity_occurrence_deposit_links",
                    ("occurrence 0: deposit source",),
                ),
                (
                    "occurrence mirrors",
                    broken_mirrors,
                    "geologic_resources/commodity_occurrence_deposit_links",
                    (
                        "occurrence 0: cell_id mirror",
                        "occurrence 0: formation mirror",
                        "occurrence 0: area mirror",
                        "occurrence 0: occurrence_potential_index",
                        "commodity_occurrence_total_area_km2",
                    ),
                ),
            )
        )

    # ---- validator boundaries -------------------------------------------

    def test_non_object_world_root_reports_only_the_root_check(self) -> None:
        checks = validate_natural_subsystems(None)

        self.assertEqual(len(checks), 1)
        self.assertEqual(
            {key: checks[0][key] for key in ("domain", "name", "status", "observed")},
            {
                "domain": "natural_pipeline",
                "name": "world_root",
                "status": "failed",
                "observed": "NoneType",
            },
        )
        self.assertEqual(
            checks[0]["message"],
            "Natural subsystem validation requires an object world root.",
        )

    def test_validator_exceptions_are_reported_as_failed_completion_checks(
        self,
    ) -> None:
        def unknown_watershed_neighbor(world: dict) -> None:
            world["watersheds"][0]["neighbor_watershed_ids"] = [999]

        def unknown_ore_deposit(world: dict) -> None:
            world["ore_genesis_systems"][0]["resource_deposit_ids"] = [9999]

        cases = (
            ("watershed neighbor", unknown_watershed_neighbor, "lakes_watersheds", "IndexError", "list index out of range"),
            ("ore deposit", unknown_ore_deposit, "geologic_resources", "KeyError", "9999"),
        )
        for label, mutate, domain, exception_name, observed in cases:
            with self.subTest(case=label):
                altered = deepcopy(self.world)
                mutate(altered)

                checks = validate_natural_subsystems(altered)

                check = _check(checks, domain, "validator_completed")
                self.assertEqual(check["status"], "failed")
                self.assertEqual(
                    check["message"],
                    "Subsystem validation could not safely inspect malformed"
                    f" data: {exception_name}.",
                )
                self.assertEqual(check["observed"], observed)
                self.assertEqual(
                    [item["name"] for item in checks if item["domain"] == domain],
                    ["validator_completed"],
                )
                self.assertEqual(_failed_names(checks), {f"{domain}/validator_completed"})
