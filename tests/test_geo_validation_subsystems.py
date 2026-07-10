from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from magic_geo.api import generate_geo_world
from magic_geo.config import WorldConfig, load_config
from magic_geo.geo_validation_subsystems import validate_natural_subsystems


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


class NaturalSubsystemValidationTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.world = generate_geo_world(_small_earth_config())

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
        self.assertEqual(altered["reef_systems"], [])
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
                lambda world: world["lake_overflow_histories"][0]["steps"][0].__setitem__(
                    "end_volume_km3",
                    world["lake_overflow_histories"][0]["steps"][0][
                        "end_volume_km3"
                    ]
                    + 10.0,
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
                altered = deepcopy(self.world)
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
            deposit["economic_viability_index"] = {"ignored": True}
            deposit["accessibility_index"] = float("nan")
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
