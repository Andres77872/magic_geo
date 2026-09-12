"""Regression evidence for prerequisite availability at enrichment boundaries."""

from copy import deepcopy
from unittest import TestCase

from support import worlds
from support.cryosphere_worlds import cached_cold_world_readonly

from magic_geo.api import generate_world
from magic_geo.geo_validation_subsystems import validate_natural_subsystems
from magic_geo.permafrost_diagnostics import enrich_world_with_permafrost_diagnostics


class EnrichmentPipelineTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = worlds.build_config(
            **{
                "mesh.cell_count": 128,
                "tectonics.plate_count": 8,
                "erosion.iterations": 1,
                "compute.backend": "cpu",
                "compute.threads": 1,
            }
        )
        cls.full_world = generate_world(cls.config)

    def test_omitting_cells_preserves_every_other_generated_field(self) -> None:
        compact_config = self.config.model_copy(deep=True)
        compact_config.output.include_cells = False

        compact = generate_world(compact_config)

        self.assertFalse(compact_config.output.include_cells)
        self.assertEqual(compact["cells"], [])
        self.assertTrue(self.full_world["cells"])
        self.assertEqual(
            compact,
            {**self.full_world, "cells": []},
        )
        self.assertTrue(compact["soil_profiles"])
        self.assertTrue(compact["resource_deposits"])

    def test_permafrost_regions_use_the_final_climate_frost_months(self) -> None:
        # This branch requires actual cold terrain. The generic seasonal
        # earthlike controls above no longer contain permafrost regions.
        for world in (cached_cold_world_readonly("full_world"), cached_cold_world_readonly()):
            with self.subTest(scope=world.get("generation_scope", "full_world")):
                cells_by_id = {cell["id"]: cell for cell in world["cells"]}
                self.assertTrue(world["permafrost_regions"])
                for region in world["permafrost_regions"]:
                    frost_months = [
                        sum(
                            temperature < 0.0
                            for temperature in cells_by_id[cell_id]["temperature_monthly_c"]
                        )
                        for cell_id in region["cell_ids"]
                    ]
                    self.assertGreater(sum(frost_months), 0)
                    self.assertEqual(
                        region["mean_frost_months"],
                        round(sum(frost_months) / len(frost_months), 6),
                    )

    def test_validation_rejects_permafrost_aggregates_from_missing_prerequisites(self) -> None:
        altered = deepcopy(cached_cold_world_readonly())
        altered["permafrost_regions"][0]["mean_frost_months"] = 0.0

        checks = validate_natural_subsystems(altered)

        check = next(
            check for check in checks
            if check["name"] == "permafrost_and_glacial_membership"
        )
        self.assertFalse(check["passed"])
        self.assertIn(
            "permafrost 0: mean_frost_months", check["observed"]["errors"]
        )

    def test_permafrost_uses_climate_when_biome_cache_is_absent_or_stale(self) -> None:
        base_cell = {
            "id": 0,
            "neighbors": [],
            "area_km2": 1.0,
            "lat_deg": 80.0,
            "temperature_c": -15.0,
            "temperature_monthly_c": [-15.0] * 12,
        }
        reference = {"cells": [base_cell.copy()]}
        enrich_world_with_permafrost_diagnostics(reference)
        self.assertEqual(reference["permafrost_regions"][0]["mean_frost_months"], 12.0)

        stale = {"cells": [{**base_cell, "frost_months": 0}]}
        enrich_world_with_permafrost_diagnostics(stale)
        self.assertEqual(stale["permafrost_regions"], reference["permafrost_regions"])
