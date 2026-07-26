"""Ore, petroleum, commodities, and land use assertions for the generated world.

Split out of the former single-method smoke test: each method re-derives
what it needs from the shared world, so they no longer depend on order.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from click.testing import Result
from typer.testing import CliRunner

from magic_geo.cli import app

from support import worlds
from support.cli import assert_no_cli_crash


class SmokeResourcesTests(TestCase):
    def test_resource_deposits(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        resource_cells = [cell for cell in world["cells"] if cell["resource"] != "none"]
        self.assertEqual(summary["resource_deposit_count"], len(world["resource_deposits"]))
        self.assertEqual(summary["resource_deposit_count"], len(resource_cells))
        self.assertEqual(
            sum(summary["resource_deposit_class_counts"].values()),
            summary["resource_deposit_count"],
        )
        self.assertEqual(
            summary["metal_resource_deposit_count"],
            sum(1 for deposit in world["resource_deposits"] if deposit["deposit_class"] == "metal"),
        )
        self.assertEqual(
            summary["energy_resource_deposit_count"],
            sum(1 for deposit in world["resource_deposits"] if deposit["deposit_class"] == "energy"),
        )
        self.assertEqual(
            summary["agricultural_resource_deposit_count"],
            sum(1 for deposit in world["resource_deposits"] if deposit["deposit_class"] == "bioproductive"),
        )
        self.assertEqual(
            summary["high_viability_resource_deposit_count"],
            sum(1 for deposit in world["resource_deposits"] if deposit["economic_viability_index"] >= 0.65),
        )
        self.assertGreaterEqual(summary["resource_deposit_total_area_km2"], 0.0)
        self.assertGreaterEqual(summary["mean_resource_reserve_potential_index"], 0.0)
        self.assertLessEqual(summary["mean_resource_reserve_potential_index"], 1.0)
        self.assertGreaterEqual(summary["mean_resource_economic_viability_index"], 0.0)
        self.assertLessEqual(summary["mean_resource_economic_viability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_resource_geologic_confidence_index"], 0.0)
        self.assertLessEqual(summary["mean_resource_geologic_confidence_index"], 1.0)
        if world["resource_deposits"]:
            self.assertAlmostEqual(
                summary["mean_resource_reserve_potential_index"],
                sum(deposit["reserve_potential_index"] for deposit in world["resource_deposits"])
                / len(world["resource_deposits"]),
                delta=0.001,
            )
            self.assertAlmostEqual(
                summary["resource_deposit_total_area_km2"],
                sum(deposit["area_km2"] for deposit in world["resource_deposits"]),
                delta=max(0.001, summary["resource_deposit_total_area_km2"] * 0.0001),
            )
        ore_type_counts: dict[str, int] = {}
        for system in world["ore_genesis_systems"]:
            ore_type_counts[system["system_type"]] = ore_type_counts.get(system["system_type"], 0) + 1
        self.assertEqual(summary["ore_genesis_system_count"], len(world["ore_genesis_systems"]))
        self.assertEqual(summary["ore_genesis_system_type_counts"], dict(sorted(ore_type_counts.items())))
        self.assertEqual(sum(summary["ore_genesis_system_type_counts"].values()), summary["ore_genesis_system_count"])
        self.assertEqual(
            summary["ore_genesis_cell_count"],
            len({cell_id for system in world["ore_genesis_systems"] for cell_id in system["cell_ids"]}),
        )
        ore_resources = {"volcanic_arc_metals", "craton_iron_gold", "placer_metals", "geothermal"}
        self.assertEqual(
            summary["ore_resource_deposit_count"],
            sum(1 for deposit in world["resource_deposits"] if deposit["resource"] in ore_resources),
        )
        self.assertEqual(
            summary["high_ore_genesis_potential_cell_count"],
            sum(1 for cell in world["cells"] if cell["ore_genesis_potential_index"] >= 0.50),
        )
        self.assertEqual(
            summary["high_hydrothermal_alteration_cell_count"],
            sum(1 for cell in world["cells"] if cell["hydrothermal_alteration_index"] >= 0.34),
        )
        self.assertEqual(
            summary["high_metallogenic_fertility_cell_count"],
            sum(1 for cell in world["cells"] if cell["metallogenic_fertility_index"] >= 0.42),
        )
        self.assertEqual(
            summary["high_placer_concentration_cell_count"],
            sum(1 for cell in world["cells"] if cell["placer_concentration_index"] >= 0.32),
        )
        self.assertAlmostEqual(
            summary["ore_genesis_total_area_km2"],
            sum(system["area_km2"] for system in world["ore_genesis_systems"]),
            delta=max(0.001, summary["ore_genesis_total_area_km2"] * 0.0001),
        )
        for key in (
            "mean_ore_genesis_potential_index",
            "mean_hydrothermal_alteration_index",
            "mean_metallogenic_fertility_index",
            "mean_ore_structural_control_index",
            "mean_placer_concentration_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertAlmostEqual(
            summary["mean_ore_genesis_potential_index"],
            sum(cell["ore_genesis_potential_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        sedimentary_resource_type_counts: dict[str, int] = {}
    def test_petroleum_migration_systems(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        petroleum_migration_type_counts: dict[str, int] = {}
        for system in world["petroleum_migration_systems"]:
            petroleum_migration_type_counts[system["system_type"]] = (
                petroleum_migration_type_counts.get(system["system_type"], 0) + 1
            )
        self.assertEqual(summary["petroleum_migration_system_count"], len(world["petroleum_migration_systems"]))
        self.assertEqual(
            summary["petroleum_migration_system_type_counts"],
            dict(sorted(petroleum_migration_type_counts.items())),
        )
        self.assertEqual(
            sum(summary["petroleum_migration_system_type_counts"].values()),
            summary["petroleum_migration_system_count"],
        )
        self.assertEqual(
            summary["petroleum_migration_cell_count"],
            len({cell_id for system in world["petroleum_migration_systems"] for cell_id in system["cell_ids"]}),
        )
        self.assertEqual(
            summary["petroleum_source_rock_cell_count"],
            sum(1 for cell in world["cells"] if cell["petroleum_source_rock_index"] >= 0.42),
        )
        self.assertEqual(
            summary["petroleum_mature_source_cell_count"],
            sum(
                1
                for cell in world["cells"]
                if cell["petroleum_source_rock_index"] >= 0.42 and cell["petroleum_maturation_index"] >= 0.42
            ),
        )
        self.assertEqual(
            summary["petroleum_trap_cell_count"],
            sum(1 for cell in world["cells"] if cell["petroleum_trap_integrity_index"] >= 0.34),
        )
        self.assertEqual(
            summary["high_petroleum_accumulation_cell_count"],
            sum(1 for cell in world["cells"] if cell["petroleum_accumulation_index"] >= 0.50),
        )
        self.assertAlmostEqual(
            summary["petroleum_migration_total_area_km2"],
            sum(system["area_km2"] for system in world["petroleum_migration_systems"]),
            delta=max(0.001, summary["petroleum_migration_total_area_km2"] * 0.0001),
        )
        for key in (
            "mean_petroleum_source_rock_index",
            "mean_petroleum_maturation_index",
            "mean_petroleum_migration_path_index",
            "mean_petroleum_trap_integrity_index",
            "mean_petroleum_accumulation_index",
        ):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        self.assertAlmostEqual(
            summary["mean_petroleum_accumulation_index"],
            sum(cell["petroleum_accumulation_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        allowed_commodities_by_resource = {
            "volcanic_arc_metals": {"copper", "gold", "silver", "sulfide_ore"},
            "craton_iron_gold": {"iron", "gold", "diamond"},
            "sedimentary_fuels": {"coal", "petroleum", "natural_gas"},
            "evaporites": {"salt", "gypsum", "potash"},
            "placer_metals": {"placer_gold", "tin"},
            "geothermal": {"geothermal_heat", "sulfur", "obsidian"},
            "fertile_alluvium": {"fertile_soils"},
            "coastal_fisheries": {"fishery_biomass"},
        }
        commodity_type_counts: dict[str, int] = {}
        commodity_group_counts: dict[str, int] = {}
        for occurrence in world["commodity_occurrences"]:
            commodity_type_counts[occurrence["commodity"]] = commodity_type_counts.get(occurrence["commodity"], 0) + 1
            commodity_group_counts[occurrence["commodity_group"]] = (
                commodity_group_counts.get(occurrence["commodity_group"], 0) + 1
            )
        self.assertEqual(summary["commodity_occurrence_count"], len(world["commodity_occurrences"]))
        self.assertEqual(
            summary["commodity_occurrence_count"],
            sum(len(allowed_commodities_by_resource.get(deposit["resource"], set())) for deposit in world["resource_deposits"]),
        )
        self.assertEqual(summary["commodity_occurrence_type_counts"], dict(sorted(commodity_type_counts.items())))
        self.assertEqual(summary["commodity_occurrence_group_counts"], dict(sorted(commodity_group_counts.items())))
        self.assertEqual(sum(summary["commodity_occurrence_type_counts"].values()), summary["commodity_occurrence_count"])
        self.assertEqual(sum(summary["commodity_occurrence_group_counts"].values()), summary["commodity_occurrence_count"])
        self.assertEqual(
            summary["metallic_commodity_occurrence_count"],
            sum(commodity_group_counts.get(group, 0) for group in ("base_metal", "ferrous_metal", "precious_metal")),
        )
        self.assertEqual(summary["fuel_commodity_occurrence_count"], commodity_group_counts.get("fuel", 0))
        self.assertEqual(
            summary["industrial_mineral_commodity_occurrence_count"],
            commodity_group_counts.get("industrial_mineral", 0),
        )
        self.assertEqual(summary["gemstone_commodity_occurrence_count"], commodity_group_counts.get("gemstone", 0))
        self.assertEqual(summary["geothermal_commodity_occurrence_count"], commodity_group_counts.get("geothermal", 0))
        self.assertEqual(
            summary["bioproductive_commodity_occurrence_count"],
            commodity_group_counts.get("agricultural", 0) + commodity_group_counts.get("fishery", 0),
        )
        self.assertEqual(
            summary["high_potential_commodity_occurrence_count"],
            sum(1 for occurrence in world["commodity_occurrences"] if occurrence["occurrence_potential_index"] >= 0.62),
        )
        self.assertAlmostEqual(
            summary["commodity_occurrence_total_area_km2"],
            sum(occurrence["area_km2"] for occurrence in world["commodity_occurrences"]),
            delta=max(0.001, summary["commodity_occurrence_total_area_km2"] * 0.0001),
        )
        for key in ("mean_commodity_occurrence_potential_index", "mean_commodity_occurrence_confidence_index"):
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        if world["commodity_occurrences"]:
            self.assertAlmostEqual(
                summary["mean_commodity_occurrence_potential_index"],
                sum(occurrence["occurrence_potential_index"] for occurrence in world["commodity_occurrences"])
                / len(world["commodity_occurrences"]),
                delta=0.001,
            )
        agricultural_candidate_ids = {
            cell["id"] for cell in world["cells"] if cell["agricultural_potential_index"] >= 0.58
        }
        mining_candidate_ids = {cell["id"] for cell in world["cells"] if cell["mining_potential_index"] >= 0.52}
        self.assertEqual(summary["agricultural_zone_count"], len(world["agricultural_zones"]))
        self.assertEqual(summary["mining_zone_count"], len(world["mining_zones"]))
        self.assertEqual(summary["agricultural_zone_cell_count"], len(agricultural_candidate_ids))
        self.assertEqual(summary["mining_zone_cell_count"], len(mining_candidate_ids))
        self.assertEqual(
            {cell_id for zone in world["agricultural_zones"] for cell_id in zone["cell_ids"]},
            agricultural_candidate_ids,
        )
        self.assertEqual(
            {cell_id for zone in world["mining_zones"] for cell_id in zone["cell_ids"]},
            mining_candidate_ids,
        )
        self.assertAlmostEqual(
            summary["agricultural_zone_total_area_km2"],
            sum(zone["area_km2"] for zone in world["agricultural_zones"]),
            delta=max(0.001, summary["agricultural_zone_total_area_km2"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["mining_zone_total_area_km2"],
            sum(zone["area_km2"] for zone in world["mining_zones"]),
            delta=max(0.001, summary["mining_zone_total_area_km2"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["mean_agricultural_potential_index"],
            sum(cell["agricultural_potential_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        self.assertAlmostEqual(
            summary["mean_mining_potential_index"],
            sum(cell["mining_potential_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        natural_frontier_candidate_ids = {
            cell["id"] for cell in world["cells"] if cell["natural_frontier_index"] >= 0.45
        }
        self.assertEqual(summary["natural_frontier_count"], len(world["natural_frontiers"]))
        self.assertEqual(summary["natural_frontier_cell_count"], len(natural_frontier_candidate_ids))
        self.assertEqual(
            {cell_id for frontier in world["natural_frontiers"] for cell_id in frontier["cell_ids"]},
            natural_frontier_candidate_ids,
        )
        self.assertEqual(
            summary["natural_frontier_border_segment_count"],
            sum(frontier["border_segment_count"] for frontier in world["natural_frontiers"]),
        )
        self.assertAlmostEqual(
            summary["natural_frontier_total_area_km2"],
            sum(frontier["area_km2"] for frontier in world["natural_frontiers"]),
            delta=max(0.001, summary["natural_frontier_total_area_km2"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["natural_frontier_total_length_km"],
            sum(frontier["total_border_length_km"] for frontier in world["natural_frontiers"]),
            delta=max(0.001, summary["natural_frontier_total_length_km"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["mean_natural_frontier_index"],
            sum(cell["natural_frontier_index"] for cell in world["cells"]) / len(world["cells"]),
            delta=0.001,
        )
        self.assertEqual(sum(summary["natural_frontier_type_counts"].values()), summary["natural_frontier_count"])
        for key in (
            "mountain_frontier_count",
            "river_frontier_count",
            "desert_frontier_count",
            "coastal_frontier_count",
            "ice_frontier_count",
            "dense_forest_frontier_count",
            "wetland_frontier_count",
        ):
            self.assertIn(key, summary)
        self.assertEqual(summary["worldbuilding_realism_check_count"], len(world["worldbuilding_realism_checks"]))
        self.assertGreaterEqual(summary["worldbuilding_realism_check_count"], 5)
        self.assertEqual(
            summary["worldbuilding_realism_pass_count"],
            sum(1 for check in world["worldbuilding_realism_checks"] if check["passed"]),
        )
        self.assertGreaterEqual(summary["worldbuilding_realism_pass_fraction"], 0.0)
        self.assertLessEqual(summary["worldbuilding_realism_pass_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_worldbuilding_realism_score"], 0.0)
        self.assertLessEqual(summary["mean_worldbuilding_realism_score"], 1.0)
        for key in [
            "large_settlement_water_access_index",
            "route_barrier_avoidance_index",
            "political_region_connectivity_index",
            "natural_border_alignment_index",
            "resource_geology_dependency_index",
        ]:
            self.assertIn(key, summary)
            self.assertGreaterEqual(summary[key], 0.0)
            self.assertLessEqual(summary[key], 1.0)
        worldbuilding_check_names = {check["name"] for check in world["worldbuilding_realism_checks"]}
        self.assertTrue(
            {
                "large_settlement_water_access",
                "route_barrier_avoidance",
                "political_region_connectivity",
                "natural_border_alignment",
                "resource_geology_dependency",
            }.issubset(worldbuilding_check_names)
        )
        first_worldbuilding_check = world["worldbuilding_realism_checks"][0]
        self.assertEqual(first_worldbuilding_check["domain"], "worldbuilding")
        self.assertIn("evidence", first_worldbuilding_check)
        self.assertGreaterEqual(first_worldbuilding_check["score"], 0.0)
        self.assertLessEqual(first_worldbuilding_check["score"], 1.0)
        self.assertEqual(summary["settlement_count"], len(world["settlements"]))
        self.assertEqual(summary["route_count"], len(world["routes"]))
        self.assertEqual(summary["trade_flow_count"], len(world["trade_flows"]))
        self.assertIn("trade_total_volume_index", summary)
        self.assertIn("interregional_trade_fraction", summary)
        self.assertIn("mean_trade_friction", summary)
        self.assertEqual(summary["political_region_count"], len(world["political_regions"]))
        self.assertGreater(summary["political_region_count"], 0)
        self.assertEqual(summary["plate_graph_node_count"], len(world["plate_graph"]["nodes"]))
        self.assertEqual(summary["plate_graph_node_count"], len(world["plates"]))
        self.assertEqual(summary["plate_graph_edge_count"], len(world["plate_graph"]["edges"]))
        self.assertEqual(summary["plate_graph_boundary_cell_edge_count"], world["plate_graph"]["boundary_cell_edge_count"])
        self.assertEqual(summary["river_graph_node_count"], len(world["river_graph"]["nodes"]))
        self.assertEqual(
            summary["river_graph_node_count"],
            sum(1 for cell in world["cells"] if cell["is_river"]),
        )
        self.assertEqual(summary["river_graph_edge_count"], len(world["river_graph"]["edges"]))
        self.assertAlmostEqual(
            summary["river_graph_total_channel_length_km"],
            sum(edge["length_km"] for edge in world["river_graph"]["edges"]),
            delta=max(0.001, summary["river_graph_total_channel_length_km"] * 0.0001),
        )
        self.assertEqual(summary["watershed_graph_node_count"], len(world["watershed_graph"]["nodes"]))
        self.assertEqual(summary["watershed_graph_node_count"], len(world["watersheds"]))
        self.assertEqual(summary["watershed_graph_edge_count"], len(world["watershed_graph"]["edges"]))
        self.assertEqual(summary["watershed_graph_boundary_edge_count"], world["watershed_graph"]["boundary_edge_count"])
        self.assertEqual(summary["trade_route_graph_node_count"], len(world["trade_route_graph"]["nodes"]))
        self.assertEqual(summary["trade_route_graph_node_count"], len(world["settlements"]))
        self.assertEqual(summary["trade_route_graph_edge_count"], len(world["trade_route_graph"]["edges"]))
        self.assertEqual(summary["trade_route_graph_edge_count"], len(world["routes"]))
        self.assertEqual(
            summary["interregional_trade_route_graph_edge_count"],
            sum(1 for edge in world["trade_route_graph"]["edges"] if edge["interregional"]),
        )
        self.assertAlmostEqual(
            summary["trade_route_graph_total_volume_index"],
            sum(edge["volume_index"] for edge in world["trade_route_graph"]["edges"]),
            delta=max(0.001, summary["trade_route_graph_total_volume_index"] * 0.0001),
        )
        self.assertEqual(summary["political_region_graph_node_count"], len(world["political_region_graph"]["nodes"]))
        self.assertEqual(summary["political_region_graph_node_count"], len(world["political_regions"]))
        self.assertEqual(summary["political_region_graph_edge_count"], len(world["political_region_graph"]["edges"]))
        self.assertEqual(summary["political_region_graph_border_segment_count"], len(world["borders"]))
        self.assertEqual(
            summary["political_region_graph_trade_edge_count"],
            sum(1 for edge in world["political_region_graph"]["edges"] if edge["trade_flow_ids"]),
        )
    def test_petroleum_migration_systems_2(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        first_cell = world["cells"][0]
        if world["petroleum_migration_systems"]:
            first_petroleum = world["petroleum_migration_systems"][0]
            cells_by_id = {cell["id"]: cell for cell in world["cells"]}
            sedimentary_systems_by_id = {system["id"]: system for system in world["sedimentary_resource_systems"]}
            self.assertEqual(first_petroleum["id"], 0)
            self.assertIn(first_petroleum["sedimentary_resource_system_id"], sedimentary_systems_by_id)
            source_system = sedimentary_systems_by_id[first_petroleum["sedimentary_resource_system_id"]]
            self.assertEqual(first_petroleum["basin_id"], source_system["basin_id"])
            self.assertIn(
                first_petroleum["system_type"],
                {
                    "oil_migration_fairway",
                    "gas_migration_fairway",
                    "mixed_hydrocarbon_fairway",
                    "immature_source_basin",
                    "breached_trap_complex",
                },
            )
            self.assertEqual(first_petroleum["cell_count"], len(first_petroleum["cell_ids"]))
            self.assertGreater(first_petroleum["cell_count"], 0)
            self.assertTrue(set(first_petroleum["source_cell_ids"]).issubset(first_petroleum["cell_ids"]))
            self.assertTrue(set(first_petroleum["migration_cell_ids"]).issubset(first_petroleum["cell_ids"]))
            self.assertTrue(set(first_petroleum["reservoir_cell_ids"]).issubset(first_petroleum["cell_ids"]))
            self.assertTrue(set(first_petroleum["seal_cell_ids"]).issubset(first_petroleum["cell_ids"]))
            self.assertTrue(set(first_petroleum["trap_cell_ids"]).issubset(first_petroleum["cell_ids"]))
            self.assertEqual(first_petroleum["path_step_count"], len(first_petroleum["migration_steps"]))
            self.assertGreater(first_petroleum["path_step_count"], 0)
            for key in (
                "mean_source_rock_index",
                "mean_maturation_index",
                "mean_migration_path_index",
                "mean_reservoir_quality_index",
                "mean_seal_quality_index",
                "mean_trap_integrity_index",
                "mean_accumulation_index",
                "petroleum_potential_index",
                "gas_potential_index",
                "migration_efficiency_index",
                "leakage_risk_index",
                "confidence_index",
            ):
                self.assertGreaterEqual(first_petroleum[key], 0.0)
                self.assertLessEqual(first_petroleum[key], 1.0)
            first_petroleum_step = first_petroleum["migration_steps"][0]
            self.assertEqual(first_petroleum_step["step_index"], 0)
            self.assertEqual(first_petroleum_step["path_cell_ids"][0], first_petroleum_step["source_cell_id"])
            self.assertEqual(first_petroleum_step["path_cell_ids"][-1], first_petroleum_step["target_trap_cell_id"])
            self.assertEqual(first_petroleum_step["path_length_cell_count"], len(first_petroleum_step["path_cell_ids"]))
            self.assertGreaterEqual(first_petroleum_step["migration_distance_km"], 0.0)
            for key in (
                "mean_path_migration_index",
                "mean_path_trap_integrity_index",
                "hydrocarbon_charge_index",
                "leakage_risk_index",
                "accumulation_probability_index",
            ):
                self.assertGreaterEqual(first_petroleum_step[key], 0.0)
                self.assertLessEqual(first_petroleum_step[key], 1.0)
            petroleum_cell = cells_by_id[first_petroleum["cell_ids"][0]]
            self.assertEqual(petroleum_cell["petroleum_system_id"], first_petroleum["id"])
        if world["commodity_occurrences"]:
            first_commodity = world["commodity_occurrences"][0]
            deposits_by_id = {deposit["id"]: deposit for deposit in world["resource_deposits"]}
            cells_by_id = {cell["id"]: cell for cell in world["cells"]}
            source_deposit = deposits_by_id[first_commodity["resource_deposit_id"]]
            source_cell = cells_by_id[first_commodity["cell_id"]]
            self.assertEqual(first_commodity["id"], 0)
            self.assertEqual(first_commodity["cell_id"], source_deposit["cell_id"])
            self.assertEqual(first_commodity["source_resource"], source_deposit["resource"])
            self.assertEqual(first_commodity["host_crust_type"], source_deposit["host_crust_type"])
            self.assertEqual(first_commodity["host_lithology"], source_deposit["host_lithology"])
            self.assertEqual(first_commodity["landform"], source_deposit["landform"])
            self.assertEqual(first_commodity["basin_id"], source_deposit["basin_id"])
            self.assertAlmostEqual(first_commodity["area_km2"], source_deposit["area_km2"], delta=0.001)
            self.assertTrue(first_commodity["commodity"])
            self.assertTrue(first_commodity["commodity_group"])
            for key in (
                "occurrence_potential_index",
                "market_value_index",
                "accessibility_index",
                "extraction_hazard_index",
                "geologic_confidence_index",
            ):
                self.assertGreaterEqual(first_commodity[key], 0.0)
                self.assertLessEqual(first_commodity[key], 1.0)
            commodity_evidence = first_commodity["formation_evidence"]
            self.assertEqual(commodity_evidence["boundary_type"], source_cell["boundary_type"])
            self.assertIn("crust_age_ma", commodity_evidence)
            self.assertIn("sediment_thickness_m", commodity_evidence)
            self.assertIn("flow_accumulation", commodity_evidence)
            self.assertIn("salinity_index", commodity_evidence)
        for key in (
            "agricultural_potential_index",
            "mining_potential_index",
            "agricultural_zone_id",
            "mining_zone_id",
        ):
            self.assertIn(key, first_cell)
        self.assertGreaterEqual(first_cell["agricultural_potential_index"], 0.0)
        self.assertLessEqual(first_cell["agricultural_potential_index"], 1.0)
        self.assertGreaterEqual(first_cell["mining_potential_index"], 0.0)
        self.assertLessEqual(first_cell["mining_potential_index"], 1.0)
        self.assertGreaterEqual(first_cell["agricultural_zone_id"], -1)
        self.assertGreaterEqual(first_cell["mining_zone_id"], -1)
        if first_cell["is_water"]:
            self.assertEqual(first_cell["agricultural_potential_index"], 0.0)
            self.assertEqual(first_cell["mining_potential_index"], 0.0)
            self.assertEqual(first_cell["agricultural_zone_id"], -1)
            self.assertEqual(first_cell["mining_zone_id"], -1)
        if world["agricultural_zones"]:
            first_agricultural_zone = world["agricultural_zones"][0]
            self.assertEqual(first_agricultural_zone["id"], 0)
            self.assertEqual(first_agricultural_zone["zone_type"], "agricultural")
            self.assertGreater(first_agricultural_zone["cell_count"], 0)
            self.assertEqual(first_agricultural_zone["cell_count"], len(first_agricultural_zone["cell_ids"]))
            self.assertGreaterEqual(first_agricultural_zone["area_km2"], 0.0)
            self.assertGreaterEqual(first_agricultural_zone["mean_potential_index"], 0.58)
            self.assertLessEqual(first_agricultural_zone["mean_potential_index"], 1.0)
            self.assertGreaterEqual(first_agricultural_zone["mean_fertility_index"], 0.0)
            self.assertLessEqual(first_agricultural_zone["mean_fertility_index"], 1.0)
            self.assertTrue(first_agricultural_zone["dominant_landform"])
            self.assertTrue(first_agricultural_zone["dominant_biome"])
            self.assertIn("settlement_ids", first_agricultural_zone)
            self.assertIn("route_ids", first_agricultural_zone)
            self.assertIn("resource_deposit_ids", first_agricultural_zone)
        if world["mining_zones"]:
            first_mining_zone = world["mining_zones"][0]
            self.assertEqual(first_mining_zone["id"], 0)
            self.assertEqual(first_mining_zone["zone_type"], "mining")
            self.assertGreater(first_mining_zone["cell_count"], 0)
            self.assertEqual(first_mining_zone["cell_count"], len(first_mining_zone["cell_ids"]))
            self.assertGreaterEqual(first_mining_zone["area_km2"], 0.0)
            self.assertGreaterEqual(first_mining_zone["mean_potential_index"], 0.52)
            self.assertLessEqual(first_mining_zone["mean_potential_index"], 1.0)
            self.assertGreaterEqual(first_mining_zone["mean_fertility_index"], 0.0)
            self.assertLessEqual(first_mining_zone["mean_fertility_index"], 1.0)
            self.assertTrue(first_mining_zone["dominant_resource"])
            self.assertTrue(first_mining_zone["dominant_landform"])
            self.assertIn("settlement_ids", first_mining_zone)
            self.assertIn("route_ids", first_mining_zone)
            self.assertIn("resource_deposit_ids", first_mining_zone)
        for key in (
            "natural_frontier_index",
            "natural_frontier_type",
            "natural_frontier_id",
        ):
            self.assertIn(key, first_cell)
        self.assertGreaterEqual(first_cell["natural_frontier_index"], 0.0)
        self.assertLessEqual(first_cell["natural_frontier_index"], 1.0)
        self.assertGreaterEqual(first_cell["natural_frontier_id"], -1)
        if first_cell["natural_frontier_id"] == -1:
            self.assertEqual(first_cell["natural_frontier_index"], 0.0)
            self.assertEqual(first_cell["natural_frontier_type"], "none")
        else:
            self.assertGreaterEqual(first_cell["natural_frontier_index"], 0.45)
            self.assertNotEqual(first_cell["natural_frontier_type"], "none")
        if world["natural_frontiers"]:
            first_frontier = world["natural_frontiers"][0]
            self.assertEqual(first_frontier["id"], 0)
            self.assertTrue(first_frontier["frontier_type"])
            self.assertNotEqual(first_frontier["frontier_type"], "none")
            self.assertGreater(first_frontier["cell_count"], 0)
            self.assertEqual(first_frontier["cell_count"], len(first_frontier["cell_ids"]))
            self.assertEqual(first_frontier["border_segment_count"], len(first_frontier["border_ids"]))
            self.assertGreater(first_frontier["border_segment_count"], 0)
            self.assertGreaterEqual(first_frontier["area_km2"], 0.0)
            self.assertGreaterEqual(first_frontier["total_border_length_km"], 0.0)
            self.assertGreaterEqual(first_frontier["mean_barrier_score"], 0.0)
            self.assertLessEqual(first_frontier["mean_barrier_score"], 1.0)
            self.assertGreaterEqual(first_frontier["mean_frontier_index"], 0.45)
            self.assertLessEqual(first_frontier["mean_frontier_index"], 1.0)
            self.assertTrue(first_frontier["dominant_landform"])
            self.assertTrue(first_frontier["dominant_biome"])
            self.assertIn("region_ids", first_frontier)
            self.assertIn("settlement_ids", first_frontier)
            self.assertIn("route_ids", first_frontier)
            self.assertEqual(first_frontier["route_crossing_count"], len(first_frontier["route_ids"]))
            self.assertIn("navigable_waterway_ids", first_frontier)
        self.assertIn("wind_east", first_cell)
        self.assertIn("wind_north", first_cell)
        self.assertIn("wind_monthly_east", first_cell)
        self.assertIn("wind_monthly_north", first_cell)
        self.assertIn("mean_seasonal_wind_speed", first_cell)
        self.assertIn("seasonal_wind_reversal_index", first_cell)
        self.assertIn("atmospheric_cell", first_cell)
        self.assertIn("surface_pressure_anomaly_hpa", first_cell)
        self.assertIn("vertical_velocity_index", first_cell)
        self.assertIn("wind_divergence_index", first_cell)
        self.assertEqual(len(first_cell["wind_monthly_east"]), 12)
        self.assertEqual(len(first_cell["wind_monthly_north"]), 12)
        for east, north in zip(first_cell["wind_monthly_east"], first_cell["wind_monthly_north"]):
            self.assertGreaterEqual(east, -1.0)
            self.assertLessEqual(east, 1.0)
            self.assertGreaterEqual(north, -1.0)
            self.assertLessEqual(north, 1.0)
        self.assertGreaterEqual(first_cell["mean_seasonal_wind_speed"], 0.0)
        self.assertLessEqual(first_cell["mean_seasonal_wind_speed"], 1.5)
        self.assertGreaterEqual(first_cell["seasonal_wind_reversal_index"], 0.0)
        self.assertLessEqual(first_cell["seasonal_wind_reversal_index"], 1.0)
        self.assertGreaterEqual(first_cell["surface_pressure_anomaly_hpa"], -22.0)
        self.assertLessEqual(first_cell["surface_pressure_anomaly_hpa"], 22.0)
        self.assertGreaterEqual(first_cell["vertical_velocity_index"], -1.0)
        self.assertLessEqual(first_cell["vertical_velocity_index"], 1.0)
        self.assertGreaterEqual(first_cell["wind_divergence_index"], -1.0)
        self.assertLessEqual(first_cell["wind_divergence_index"], 1.0)
        self.assertIn("ocean_current_east", first_cell)
        self.assertIn("ocean_current_north", first_cell)
        self.assertIn("ocean_current_temperature_c", first_cell)
        self.assertIn("ocean_current_moisture_factor", first_cell)
        for key in (
            "ocean_current_speed_index",
            "ocean_current_poleward_index",
            "ocean_heat_transport_index",
            "ocean_current_transport_alignment",
            "ocean_current_transport_target_cell_id",
            "ocean_current_transport_distance_km",
            "ocean_current_convergence_index",
            "ocean_upwelling_index",
            "ocean_current_regime",
            "ocean_current_system_id",
        ):
            self.assertIn(key, first_cell)
        self.assertGreaterEqual(first_cell["ocean_current_speed_index"], 0.0)
        self.assertGreaterEqual(first_cell["ocean_current_poleward_index"], -1.0)
        self.assertLessEqual(first_cell["ocean_current_poleward_index"], 1.0)
        self.assertGreaterEqual(first_cell["ocean_heat_transport_index"], -1.0)
        self.assertLessEqual(first_cell["ocean_heat_transport_index"], 1.0)
        self.assertGreaterEqual(first_cell["ocean_current_transport_alignment"], 0.0)
        self.assertLessEqual(first_cell["ocean_current_transport_alignment"], 1.0)
        self.assertGreaterEqual(first_cell["ocean_current_transport_target_cell_id"], -1)
        self.assertGreaterEqual(first_cell["ocean_current_transport_distance_km"], 0.0)
        self.assertGreaterEqual(first_cell["ocean_current_convergence_index"], -1.0)
        self.assertLessEqual(first_cell["ocean_current_convergence_index"], 1.0)
        self.assertGreaterEqual(first_cell["ocean_upwelling_index"], 0.0)
        self.assertLessEqual(first_cell["ocean_upwelling_index"], 1.0)
        self.assertIn(first_cell["ocean_current_regime"], summary["ocean_current_regime_counts"])
        if first_cell["water_body_type"] in {"ocean", "continental_shelf", "inland_sea"}:
            self.assertGreaterEqual(first_cell["ocean_current_system_id"], 0)
            if first_cell["ocean_current_transport_target_cell_id"] >= 0:
                self.assertIn(first_cell["ocean_current_transport_target_cell_id"], first_cell["neighbors"])
        else:
            self.assertEqual(first_cell["ocean_current_regime"], "non_marine")
            self.assertEqual(first_cell["ocean_current_system_id"], -1)
        self.assertIn("humidity_transport_index", first_cell)
        self.assertIn("upwind_ocean_fetch_km", first_cell)
        self.assertIn("advected_moisture_factor", first_cell)
        self.assertIn("distance_to_marine_water_km", first_cell)
        self.assertIn("continentality_index", first_cell)
        self.assertIn("oceanic_humidity_availability_index", first_cell)
        self.assertIn("marine_influence_class", first_cell)
        self.assertIn("climate_continentality_region_id", first_cell)
        self.assertGreaterEqual(first_cell["distance_to_marine_water_km"], 0.0)
        self.assertGreaterEqual(first_cell["continentality_index"], 0.0)
        self.assertLessEqual(first_cell["continentality_index"], 1.0)
        self.assertGreaterEqual(first_cell["oceanic_humidity_availability_index"], 0.0)
        self.assertLessEqual(first_cell["oceanic_humidity_availability_index"], 1.0)
        self.assertIn(first_cell["marine_influence_class"], {"marine", "coastal", "maritime_influenced", "interior", "continental_core"})
        self.assertIn("orographic_factor", first_cell)
        self.assertIn("rain_shadow_factor", first_cell)
        self.assertIn("vapor_evaporation_mm_y", first_cell)
        self.assertIn("moisture_convergence_mm_y", first_cell)
        self.assertIn("orographic_rainout_mm_y", first_cell)
        self.assertIn("precipitation_recycling_fraction", first_cell)
        self.assertIn("vapor_deficit_mm_y", first_cell)
        self.assertIn("vapor_budget_residual_mm_y", first_cell)
        self.assertIn("seasonal_precipitation_range_mm", first_cell)
        self.assertIn("seasonal_aridity_index", first_cell)
        self.assertIn("cell_monsoon_index", first_cell)
        self.assertIn("seasonal_humidity_regime", first_cell)
        self.assertGreaterEqual(first_cell["seasonal_precipitation_range_mm"], 0.0)
        self.assertGreaterEqual(first_cell["seasonal_aridity_index"], 0.0)
        self.assertLessEqual(first_cell["seasonal_aridity_index"], 1.0)
        self.assertGreaterEqual(first_cell["cell_monsoon_index"], 0.0)
        self.assertLessEqual(first_cell["cell_monsoon_index"], 1.0)
        for key in (
            "top_of_atmosphere_insolation_w_m2",
            "seasonal_insolation_range_w_m2",
            "orbital_insolation_variability_index",
            "peak_seasonal_insolation_w_m2",
            "low_seasonal_insolation_w_m2",
            "surface_albedo_index",
            "surface_albedo_regime",
            "absorbed_shortwave_w_m2",
            "outgoing_longwave_w_m2",
            "greenhouse_trapping_w_m2",
            "net_radiative_balance_w_m2",
            "no_greenhouse_equilibrium_temperature_c",
            "radiative_equilibrium_temperature_c",
            "energy_balance_residual_c",
            "climate_energy_stress_index",
        ):
            self.assertIn(key, first_cell)
        self.assertGreater(first_cell["top_of_atmosphere_insolation_w_m2"], 0.0)
        self.assertGreaterEqual(first_cell["seasonal_insolation_range_w_m2"], 0.0)
        self.assertGreaterEqual(first_cell["orbital_insolation_variability_index"], 0.0)
        self.assertLessEqual(first_cell["orbital_insolation_variability_index"], 1.0)
        self.assertGreaterEqual(first_cell["peak_seasonal_insolation_w_m2"], first_cell["low_seasonal_insolation_w_m2"])
        self.assertGreaterEqual(first_cell["low_seasonal_insolation_w_m2"], 0.0)
        self.assertGreaterEqual(first_cell["surface_albedo_index"], 0.0)
        self.assertLessEqual(first_cell["surface_albedo_index"], 1.0)
        self.assertGreaterEqual(first_cell["absorbed_shortwave_w_m2"], 0.0)
        self.assertGreater(first_cell["outgoing_longwave_w_m2"], 0.0)
        self.assertGreaterEqual(first_cell["greenhouse_trapping_w_m2"], 0.0)
        self.assertGreaterEqual(first_cell["climate_energy_stress_index"], 0.0)
        self.assertLessEqual(first_cell["climate_energy_stress_index"], 1.0)
        self.assertIn("ice_thickness_m", first_cell)
        self.assertIn("ice_sheet_id", first_cell)
        self.assertIn("glacier_flow_to", first_cell)
        self.assertIn("ice_surface_mass_balance_m_y", first_cell)
        self.assertIn("basal_sliding_index", first_cell)
        self.assertIn("ice_velocity_m_y", first_cell)
        self.assertGreaterEqual(first_cell["basal_sliding_index"], 0.0)
        self.assertLessEqual(first_cell["basal_sliding_index"], 1.0)
        self.assertGreaterEqual(first_cell["ice_velocity_m_y"], 0.0)
        self.assertIn("glacial_erosion_m", first_cell)
        self.assertIn("glacial_sediment_production_m", first_cell)
        self.assertIn("glacial_sediment_deposition_m", first_cell)
        self.assertIn("glacial_sediment_net_m", first_cell)
        self.assertIn("glacial_sediment_outgoing_transfer_count", first_cell)
        self.assertIn("glacial_sediment_incoming_transfer_count", first_cell)
        self.assertIn("moraine_deposition_m", first_cell)
        self.assertIn("deglaciation_age_ka", first_cell)
        self.assertIn("ice_flowline_flux_km3_y", first_cell)
        self.assertIn("ice_flowline_driving_stress_kpa", first_cell)
        self.assertIn("ice_flowline_strain_heating_index", first_cell)
        self.assertIn("ice_flowline_path_count", first_cell)
        self.assertIn("permafrost_extent_index", first_cell)
        self.assertIn("active_layer_depth_m", first_cell)
        self.assertIn("ground_ice_content_index", first_cell)
        self.assertIn("permafrost_class", first_cell)
        self.assertIn("permafrost_region_id", first_cell)
        self.assertIn("glacial_landform_index", first_cell)
        self.assertIn("glacial_erosion_intensity_index", first_cell)
        self.assertIn("glacial_deposition_index", first_cell)
        self.assertIn("glacial_meltwater_index", first_cell)
        self.assertIn("glacial_landform_type", first_cell)
        self.assertIn("glacial_landform_system_id", first_cell)
        self.assertGreaterEqual(first_cell["ice_flowline_flux_km3_y"], 0.0)
        self.assertGreaterEqual(first_cell["ice_flowline_driving_stress_kpa"], 0.0)
        self.assertGreaterEqual(first_cell["ice_flowline_strain_heating_index"], 0.0)
        self.assertLessEqual(first_cell["ice_flowline_strain_heating_index"], 1.0)
        self.assertGreaterEqual(first_cell["ice_flowline_path_count"], 0)
        self.assertGreaterEqual(first_cell["permafrost_extent_index"], 0.0)
        self.assertLessEqual(first_cell["permafrost_extent_index"], 1.0)
        self.assertGreaterEqual(first_cell["active_layer_depth_m"], 0.0)
        self.assertLessEqual(first_cell["active_layer_depth_m"], 4.5)
        self.assertGreaterEqual(first_cell["ground_ice_content_index"], 0.0)
        self.assertLessEqual(first_cell["ground_ice_content_index"], 1.0)
        self.assertTrue(first_cell["permafrost_class"])
        self.assertGreaterEqual(first_cell["permafrost_region_id"], -1)
        for key in (
            "glacial_landform_index",
            "glacial_erosion_intensity_index",
            "glacial_deposition_index",
            "glacial_meltwater_index",
        ):
            self.assertGreaterEqual(first_cell[key], 0.0)
            self.assertLessEqual(first_cell[key], 1.0)
        self.assertIn(
            first_cell["glacial_landform_type"],
            {"none", "ice_cap", "mountain_glacier", "fjord", "glacial_valley", "glacial_lake", "moraine"},
        )
        self.assertGreaterEqual(first_cell["glacial_landform_system_id"], -1)
    def test_validate_reports_every_land_use_and_realism_replay_verdict(self) -> None:
        """``validate`` reaches and reports the land-use, frontier and realism replays.

        The field-by-field tamper coverage for all three lives in
        ``test_human_geography_validation``, which calls the validators directly
        against the 128-cell replay world. Wiring into the public command is the
        one claim that module cannot make, and one tamper per verdict in a single
        pass is all it needs.
        """

        world = worlds.cached_world("mid_512")

        for model_key, model_type in (
            (
                "land_use_zone_model",
                "causal_soil_climate_resource_connected_land_use_zones_v1",
            ),
            (
                "natural_frontier_model",
                "causal_border_terrain_connected_natural_frontiers_v1",
            ),
            (
                "worldbuilding_realism_model",
                "causal_upstream_evidence_worldbuilding_realism_checks_v1",
            ),
        ):
            with self.subTest(model=model_key):
                self.assertEqual(world[model_key]["model_type"], model_type)
        for family in ("agricultural_zones", "mining_zones", "natural_frontiers"):
            with self.subTest(family=family):
                self.assertTrue(world[family], family)
        self.assertEqual(len(world["worldbuilding_realism_checks"]), 5)

        runner = CliRunner()
        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"

            def validate_current() -> Result:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            control = validate_current()
            assert_no_cli_crash(self, control, command="validate")
            self.assertEqual(control.exit_code, 0, control.output)

            world["land_use_zone_model"]["agricultural_threshold"] += 0.01
            world["natural_frontier_model"]["frontier_index_parameters"][
                "border_weight"
            ] += 0.01
            world["worldbuilding_realism_model"][
                "water_access_runoff_threshold_mm_y"
            ] += 1.0

            result = validate_current()

        assert_no_cli_crash(self, result, command="validate")
        self.assertEqual(result.exit_code, 1, result.output)
        for message in (
            "land use zone model or causal replay invalid",
            "natural frontier model or causal replay invalid",
            "worldbuilding realism model or causal replay invalid",
        ):
            with self.subTest(message=message):
                self.assertIn(message, result.output)
