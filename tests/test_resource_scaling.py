from __future__ import annotations

from unittest import TestCase

from magic_geo.ore_genesis import (
    _cell_indices as ore_cell_indices,
    _flow_accumulation_scale as ore_flow_scale,
    enrich_world_with_ore_genesis,
)
from magic_geo.resource_dynamics import (
    _confidence as resource_confidence,
    _flow_accumulation_scale as resource_flow_scale,
    _reserve_potential,
    enrich_world_with_resource_deposits,
)


class NaturalResourceScalingTests(TestCase):
    def test_flow_scale_is_the_positive_cell_p95(self) -> None:
        cells = [
            {"flow_accumulation": float(value)} for value in range(1, 101)
        ]
        cells.extend(
            [
                {"flow_accumulation": 0.0},
                {"flow_accumulation": -5.0},
            ]
        )

        self.assertEqual(resource_flow_scale(cells), 95.0)
        self.assertEqual(ore_flow_scale(cells), 95.0)

    def test_placer_resource_evidence_is_scale_invariant_and_not_saturated(
        self,
    ) -> None:
        base = {
            "resource": "placer_metals",
            "flow_accumulation": 25.0,
            "is_river": True,
            "sediment_thickness_m": 0.8,
            "boundary_convergent": 0.2,
            "fertility": 0.4,
            "landform": "river_valley",
            "crust_type": "accreted_terrane",
            "crust_age_ma": 600.0,
        }
        larger_units = {**base, "flow_accumulation": 25_000_000.0}

        reserve = _reserve_potential("placer_metals", base, 100.0)
        scaled_reserve = _reserve_potential(
            "placer_metals", larger_units, 100_000_000.0
        )
        confidence = resource_confidence(
            "placer_metals", base, reserve, 100.0
        )
        scaled_confidence = resource_confidence(
            "placer_metals",
            larger_units,
            scaled_reserve,
            100_000_000.0,
        )
        high_flow = _reserve_potential(
            "placer_metals", {**base, "flow_accumulation": 100.0}, 100.0
        )

        self.assertAlmostEqual(reserve, scaled_reserve)
        self.assertAlmostEqual(confidence, scaled_confidence)
        self.assertLess(reserve, high_flow)

    def test_ore_placer_index_uses_the_same_dimensionless_flow_ratio(self) -> None:
        base = {
            "resource": "placer_metals",
            "flow_accumulation": 30.0,
            "is_river": True,
            "sediment_thickness_m": 1.0,
            "boundary_convergent": 0.15,
            "boundary_divergent": 0.0,
            "boundary_transform": 0.05,
            "tectonic_zone_strength": 0.2,
            "volcanic_potential_index": 0.1,
            "fault_slip_rate_index": 0.2,
            "seismic_hazard_index": 0.15,
            "crust_age_ma": 500.0,
            "crust_thickness_km": 32.0,
            "elevation_m": 100.0,
            "filled_elevation_m": 100.0,
            "lithology": "sandstone",
            "landform": "river_valley",
            "crust_type": "sedimentary_basin",
            "boundary_type": "convergent",
        }
        larger_units = {**base, "flow_accumulation": 30_000_000.0}

        first = ore_cell_indices(base, 120.0)
        second = ore_cell_indices(larger_units, 120_000_000.0)
        high = ore_cell_indices(
            {**base, "flow_accumulation": 120.0}, 120.0
        )

        self.assertEqual(first, second)
        self.assertLess(first["placer"], high["placer"])
        self.assertLess(first["ore"], high["ore"])

    def test_complete_resource_enrichers_are_flow_unit_invariant(self) -> None:
        def generated(scale: float) -> dict:
            cells = [
                {
                    "id": index,
                    "neighbors": [],
                    "area_km2": 10.0,
                    "lat_deg": float(index - 50),
                    "lon_deg": float(index),
                    "resource": "placer_metals",
                    "flow_accumulation": float(index + 1) * scale,
                    "is_river": True,
                    "sediment_thickness_m": 1.0,
                    "boundary_convergent": 0.15,
                    "boundary_divergent": 0.0,
                    "boundary_transform": 0.05,
                    "tectonic_zone_strength": 0.2,
                    "volcanic_potential_index": 0.1,
                    "fault_slip_rate_index": 0.2,
                    "seismic_hazard_index": 0.15,
                    "crust_age_ma": 500.0,
                    "crust_thickness_km": 32.0,
                    "elevation_m": 100.0,
                    "filled_elevation_m": 100.0,
                    "lithology": "sandstone",
                    "landform": "river_valley",
                    "crust_type": "sedimentary_basin",
                    "boundary_type": "convergent",
                }
                for index in range(100)
            ]
            world = {"cells": cells, "summary": {}}
            enrich_world_with_resource_deposits(world)
            enrich_world_with_ore_genesis(world)
            return world

        base = generated(1.0)
        changed_units = generated(1_000_000.0)

        self.assertEqual(
            changed_units["resource_deposit_model"][
                "flow_accumulation_scale"
            ],
            base["resource_deposit_model"]["flow_accumulation_scale"]
            * 1_000_000.0,
        )
        for first, second in zip(
            base["resource_deposits"],
            changed_units["resource_deposits"],
            strict=True,
        ):
            for field in (
                "reserve_potential_index",
                "geologic_confidence_index",
                "economic_viability_index",
            ):
                self.assertEqual(first[field], second[field])
        for first, second in zip(
            base["cells"], changed_units["cells"], strict=True
        ):
            for field in (
                "ore_genesis_potential_index",
                "hydrothermal_alteration_index",
                "metallogenic_fertility_index",
                "ore_structural_control_index",
                "placer_concentration_index",
            ):
                self.assertEqual(first[field], second[field])
