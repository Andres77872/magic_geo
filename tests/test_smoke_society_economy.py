"""Population, economy, markets, and dynasties assertions for the generated world.

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


class SmokeSocietyEconomyTests(TestCase):
    def test_speaker_population_histories(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertAlmostEqual(
            summary["mean_speaker_allophonic_variation_index"],
            sum(history["mean_allophonic_variation_index"] for history in world["speaker_population_histories"])
            / len(world["speaker_population_histories"]),
            delta=0.0001,
        )
        self.assertAlmostEqual(
            summary["total_estimated_speaker_population"],
            sum(history["estimated_speaker_population"] for history in world["speaker_population_histories"]),
            delta=0.001,
        )
        self.assertEqual(
            summary["high_contact_speaker_history_count"],
            sum(1 for history in world["speaker_population_histories"] if history["high_contact_speaker_history"]),
        )
        self.assertEqual(summary["population_region_count"], len(world["population_regions"]))
        self.assertIn("estimated_world_population", summary)
        self.assertGreater(summary["estimated_world_population"], 0.0)
        self.assertIn("mean_population_pressure", summary)
        self.assertEqual(summary["population_history_count"], len(world["population_histories"]))
        self.assertEqual(len(world["population_histories"]), len(world["population_regions"]))
        self.assertEqual(
            summary["population_history_step_count"],
            sum(history["time_step_count"] for history in world["population_histories"]),
        )
        self.assertAlmostEqual(
            summary["historical_final_population"],
            sum(history["final_population"] for history in world["population_histories"]),
            delta=max(1.0, summary["historical_final_population"] * 0.0001),
        )
        self.assertGreaterEqual(summary["historical_peak_population_pressure"], 0.0)
        self.assertGreaterEqual(summary["max_population_decline_fraction"], 0.0)
        self.assertEqual(summary["economy_history_count"], len(world["economy_histories"]))
        self.assertEqual(len(world["economy_histories"]), len(world["population_histories"]))
        self.assertEqual(
            summary["economy_history_step_count"],
            sum(history["time_step_count"] for history in world["economy_histories"]),
        )
        self.assertAlmostEqual(
            summary["historical_final_gross_output_index"],
            sum(history["final_gross_output_index"] for history in world["economy_histories"]),
            delta=max(0.001, summary["historical_final_gross_output_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["historical_final_treasury_index"],
            sum(history["final_treasury_index"] for history in world["economy_histories"]),
            delta=max(0.001, summary["historical_final_treasury_index"] * 0.0001),
        )
        self.assertGreaterEqual(summary["historical_total_tax_revenue_index"], 0.0)
        self.assertGreaterEqual(summary["historical_total_trade_revenue_index"], 0.0)
        self.assertGreaterEqual(summary["historical_total_war_cost_index"], 0.0)
        self.assertGreaterEqual(summary["historical_peak_army_capacity_population"], 0.0)
        self.assertGreaterEqual(summary["mean_historical_prosperity_index"], 0.0)
        self.assertLessEqual(summary["mean_historical_prosperity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_historical_trade_dependency_index"], 0.0)
        self.assertLessEqual(summary["mean_historical_trade_dependency_index"], 1.0)
        self.assertGreaterEqual(summary["mean_historical_military_burden_index"], 0.0)
        self.assertLessEqual(summary["mean_historical_military_burden_index"], 1.0)
        self.assertEqual(
            summary["high_military_burden_economy_step_count"],
            sum(
                1
                for history in world["economy_histories"]
                for step in history["steps"]
                if step["military_burden_index"] >= 0.65
            ),
        )
        self.assertEqual(summary["household_cohort_count"], len(world["household_cohorts"]))
        self.assertEqual(summary["household_cohort_count"], sum(region["household_cohort_count"] for region in world["population_regions"]))
        self.assertEqual(summary["firm_agent_count"], len(world["firm_agents"]))
        self.assertEqual(summary["firm_agent_count"], sum(region["firm_agent_count"] for region in world["political_regions"]))
    def test_demographic_agent_histories(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertEqual(summary["demographic_agent_history_count"], len(world["demographic_agent_histories"]))
        self.assertEqual(summary["demographic_agent_history_count"], len(world["population_regions"]))
        self.assertEqual(
            summary["demographic_agent_step_count"],
            sum(history["step_count"] for history in world["demographic_agent_histories"]),
        )
        self.assertEqual(summary["individual_agent_count"], len(world["individual_agents"]))
        self.assertEqual(
            summary["individual_agent_count"],
            sum(region["individual_agent_count"] for region in world["population_regions"]),
        )
        self.assertEqual(summary["individual_life_event_count"], len(world["individual_life_events"]))
        self.assertEqual(
            summary["individual_life_event_count"],
            sum(person["event_count"] for person in world["individual_agents"]),
        )
        self.assertEqual(
            summary["individual_birth_event_count"],
            sum(1 for event in world["individual_life_events"] if event["event_type"] == "birth"),
        )
        self.assertEqual(
            summary["individual_death_event_count"],
            sum(1 for event in world["individual_life_events"] if event["event_type"] == "death"),
        )
        self.assertEqual(
            summary["individual_marriage_event_count"],
            sum(1 for event in world["individual_life_events"] if event["event_type"] == "marriage"),
        )
        self.assertEqual(
            summary["property_transfer_event_count"],
            sum(1 for event in world["individual_life_events"] if event["event_type"] == "property_transfer"),
        )
        self.assertAlmostEqual(
            summary["total_household_cohort_population"],
            sum(cohort["population"] for cohort in world["household_cohorts"]),
            delta=max(1.0, summary["total_household_cohort_population"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_firm_employment_capacity"],
            sum(firm["employment_capacity"] for firm in world["firm_agents"]),
            delta=max(1.0, summary["total_firm_employment_capacity"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_property_transfer_value_index"],
            sum(event["property_value_index"] for event in world["individual_life_events"] if event["event_type"] == "property_transfer"),
            delta=max(0.001, summary["total_property_transfer_value_index"] * 0.0001),
        )
        self.assertGreaterEqual(summary["mean_household_resilience_index"], 0.0)
        self.assertLessEqual(summary["mean_household_resilience_index"], 1.0)
        self.assertGreaterEqual(summary["mean_household_migration_propensity_index"], 0.0)
        self.assertLessEqual(summary["mean_household_migration_propensity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_household_consumption_pressure_index"], 0.0)
        self.assertLessEqual(summary["mean_household_consumption_pressure_index"], 1.0)
        self.assertGreaterEqual(summary["mean_firm_productivity_index"], 0.0)
        self.assertLessEqual(summary["mean_firm_productivity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_firm_market_dependency_index"], 0.0)
        self.assertLessEqual(summary["mean_firm_market_dependency_index"], 1.0)
        self.assertGreaterEqual(summary["mean_firm_supply_chain_risk_index"], 0.0)
        self.assertLessEqual(summary["mean_firm_supply_chain_risk_index"], 1.0)
        self.assertGreaterEqual(summary["mean_demographic_vulnerability_index"], 0.0)
        self.assertLessEqual(summary["mean_demographic_vulnerability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_individual_lifespan_years"], 0.0)
        self.assertEqual(
            summary["high_vulnerability_household_count"],
            sum(1 for cohort in world["household_cohorts"] if cohort["vulnerability_index"] >= 0.65),
        )
        self.assertEqual(summary["conflict_count"], len(world["conflicts"]))
        self.assertIn("high_intensity_conflict_count", summary)
        self.assertEqual(
            summary["high_intensity_conflict_count"],
            sum(1 for conflict in world["conflicts"] if conflict["intensity"] >= 0.65),
        )
        self.assertIn("mean_conflict_intensity", summary)
        self.assertIn("mean_war_duration_years", summary)
        self.assertGreaterEqual(summary["mean_war_duration_years"], 0.0)
        self.assertIn("total_mobilized_population", summary)
        self.assertGreaterEqual(summary["total_mobilized_population"], 0.0)
        self.assertIn("mean_conflict_logistics_strain_index", summary)
        self.assertGreaterEqual(summary["mean_conflict_logistics_strain_index"], 0.0)
        self.assertLessEqual(summary["mean_conflict_logistics_strain_index"], 1.0)
        self.assertIn("mean_conflict_economic_disruption_index", summary)
        self.assertGreaterEqual(summary["mean_conflict_economic_disruption_index"], 0.0)
        self.assertLessEqual(summary["mean_conflict_economic_disruption_index"], 1.0)
        self.assertIn("high_economic_disruption_conflict_count", summary)
        self.assertEqual(
            summary["high_economic_disruption_conflict_count"],
            sum(1 for conflict in world["conflicts"] if conflict["economic_disruption_index"] >= 0.65),
        )
        self.assertIn("mean_conflict_casualty_rate", summary)
        self.assertGreaterEqual(summary["mean_conflict_casualty_rate"], 0.0)
        self.assertLessEqual(summary["mean_conflict_casualty_rate"], 1.0)
        self.assertIn("max_conflict_casualty_rate", summary)
        self.assertGreaterEqual(summary["max_conflict_casualty_rate"], 0.0)
        self.assertLessEqual(summary["max_conflict_casualty_rate"], 1.0)
        self.assertEqual(summary["logistics_network_count"], len(world["logistics_networks"]))
        self.assertEqual(summary["logistics_network_count"], len(world["political_regions"]))
        self.assertEqual(
            summary["logistics_route_link_count"],
            sum(network["route_count"] for network in world["logistics_networks"]),
        )
        self.assertEqual(summary["market_exchange_count"], len(world["market_exchanges"]))
        self.assertEqual(summary["market_exchange_count"], len(world["trade_flows"]))
        self.assertEqual(
            summary["interregional_market_exchange_count"],
            sum(1 for market in world["market_exchanges"] if market["interregional"]),
        )
        self.assertEqual(summary["route_capacity_constraint_count"], len(world["route_capacity_constraints"]))
    def test_market_exchanges(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertEqual(
            summary["route_capacity_constraint_count"],
            len({market["route_id"] for market in world["market_exchanges"]}),
        )
        self.assertEqual(summary["market_clearing_record_count"], len(world["market_clearing_records"]))
        self.assertEqual(summary["market_clearing_record_count"], len(world["market_exchanges"]))
        self.assertEqual(summary["market_agent_order_count"], len(world["market_agent_orders"]))
        self.assertEqual(
            summary["market_agent_order_count"],
            sum(record["agent_order_count"] for record in world["market_clearing_records"]),
        )
        self.assertEqual(summary["market_price_iteration_count"], len(world["market_price_iterations"]))
        self.assertEqual(
            summary["market_price_iteration_count"],
            sum(record["price_iteration_count"] for record in world["market_clearing_records"]),
        )
        self.assertEqual(summary["market_inventory_history_count"], len(world["market_inventory_histories"]))
        self.assertEqual(summary["market_inventory_history_count"], len(world["market_clearing_records"]))
        self.assertEqual(
            summary["market_inventory_step_count"],
            sum(history["step_count"] for history in world["market_inventory_histories"]),
        )
        self.assertEqual(
            summary["constrained_market_exchange_count"],
            sum(1 for record in world["market_clearing_records"] if record["unmet_demand_index"] > 0.0),
        )
        self.assertEqual(
            summary["producer_market_order_count"],
            sum(1 for order in world["market_agent_orders"] if order["order_side"] == "supply"),
        )
        self.assertEqual(
            summary["consumer_market_order_count"],
            sum(1 for order in world["market_agent_orders"] if order["order_side"] == "demand"),
        )
        self.assertEqual(summary["campaign_movement_count"], len(world["campaign_movements"]))
        self.assertEqual(summary["campaign_path_segment_count"], len(world["campaign_path_segments"]))
        self.assertEqual(
            summary["campaign_path_segment_count"],
            sum(campaign["path_segment_count"] for campaign in world["campaign_movements"]),
        )
        self.assertEqual(summary["campaign_front_history_count"], len(world["campaign_front_histories"]))
        self.assertEqual(summary["campaign_front_history_count"], len(world["campaign_movements"]))
        self.assertEqual(
            summary["campaign_front_step_count"],
            sum(history["step_count"] for history in world["campaign_front_histories"]),
        )
        self.assertEqual(summary["tactical_engagement_count"], len(world["tactical_engagements"]))
        self.assertEqual(summary["tactical_engagement_count"], len(world["campaign_movements"]))
        self.assertEqual(
            summary["tactical_engagement_step_count"],
            sum(engagement["step_count"] for engagement in world["tactical_engagements"]),
        )
        self.assertEqual(summary["strategic_campaign_plan_count"], len(world["strategic_campaign_plans"]))
        self.assertEqual(summary["strategic_campaign_plan_count"], len(world["campaign_movements"]))
        self.assertEqual(
            summary["strategic_decision_point_count"],
            sum(plan["decision_point_count"] for plan in world["strategic_campaign_plans"]),
        )
        cells_by_id = {int(cell["id"]): cell for cell in world["cells"]}
        for campaign in world["campaign_movements"]:
            path_cell_ids = [int(cell_id) for cell_id in campaign["path_cell_ids"]]
            self.assertNotEqual(campaign["origin_cell_id"], campaign["target_cell_id"])
            self.assertGreaterEqual(len(path_cell_ids), 2)
            self.assertEqual(campaign["path_segment_count"], len(path_cell_ids) - 1)
            self.assertEqual(len(path_cell_ids), len(set(path_cell_ids)))
            for first_id, second_id in zip(path_cell_ids, path_cell_ids[1:]):
                self.assertIn(second_id, {int(neighbor_id) for neighbor_id in cells_by_id[first_id]["neighbors"]})
        self.assertAlmostEqual(
            summary["total_market_exchange_volume_index"],
            sum(market["volume_index"] for market in world["market_exchanges"]),
            delta=max(0.001, summary["total_market_exchange_volume_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_market_requested_volume_index"],
            sum(constraint["requested_volume_index"] for constraint in world["route_capacity_constraints"]),
            delta=max(0.001, summary["total_market_requested_volume_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_market_cleared_volume_index"],
            sum(constraint["cleared_volume_index"] for constraint in world["route_capacity_constraints"]),
            delta=max(0.001, summary["total_market_cleared_volume_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_market_unmet_demand_index"],
            sum(constraint["unmet_volume_index"] for constraint in world["route_capacity_constraints"]),
            delta=max(0.001, summary["total_market_unmet_demand_index"] * 0.0001),
        )
    def test_market_clearing_records(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertAlmostEqual(
            summary["total_endogenous_market_supply_index"],
            sum(record["endogenous_supply_index"] for record in world["market_clearing_records"]),
            delta=max(0.001, summary["total_endogenous_market_supply_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_endogenous_market_demand_index"],
            sum(record["endogenous_demand_index"] for record in world["market_clearing_records"]),
            delta=max(0.001, summary["total_endogenous_market_demand_index"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_campaign_mobilized_population"],
            sum(campaign["force_estimate"] for campaign in world["campaign_movements"]),
            delta=max(1.0, summary["total_campaign_mobilized_population"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_campaign_path_length_km"],
            sum(campaign["path_length_km"] for campaign in world["campaign_movements"]),
            delta=max(0.001, summary["total_campaign_path_length_km"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["total_campaign_front_attrition_loss_population"],
            sum(
                step["attrition_loss_population"]
                for history in world["campaign_front_histories"]
                for step in history["steps"]
            ),
            delta=max(1.0, summary["total_campaign_front_attrition_loss_population"] * 0.0001),
        )
        self.assertAlmostEqual(
            summary["tactical_total_attrition_loss_population"],
            sum(engagement["total_attrition_loss_population"] for engagement in world["tactical_engagements"]),
            delta=max(1.0, summary["tactical_total_attrition_loss_population"] * 0.0001),
        )
        self.assertGreaterEqual(summary["mean_logistics_transport_efficiency_index"], 0.0)
        self.assertLessEqual(summary["mean_logistics_transport_efficiency_index"], 1.0)
        self.assertGreaterEqual(summary["mean_logistics_resilience_index"], 0.0)
        self.assertLessEqual(summary["mean_logistics_resilience_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_access_index"], 0.0)
        self.assertLessEqual(summary["mean_market_access_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_disruption_risk_index"], 0.0)
        self.assertLessEqual(summary["mean_market_disruption_risk_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_clearance_fraction"], 0.0)
        self.assertLessEqual(summary["mean_market_clearance_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_route_capacity_utilization_index"], 0.0)
        self.assertLessEqual(summary["mean_route_capacity_utilization_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_price_adjustment_index"], 0.0)
        self.assertLessEqual(summary["mean_market_price_adjustment_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_rationing_index"], 0.0)
        self.assertLessEqual(summary["mean_market_rationing_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_equilibrium_residual_index"], 0.0)
        self.assertLessEqual(summary["mean_market_equilibrium_residual_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_inventory_gap_index"], 0.0)
        self.assertLessEqual(summary["mean_market_inventory_gap_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_learning_rate_index"], 0.0)
        self.assertLessEqual(summary["mean_market_learning_rate_index"], 1.0)
        self.assertGreaterEqual(summary["mean_market_inventory_pressure_index"], 0.0)
        self.assertLessEqual(summary["mean_market_inventory_pressure_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_travel_time_days"], 0.0)
        self.assertGreaterEqual(summary["mean_campaign_attrition_risk_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_attrition_risk_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_operational_reach_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_operational_reach_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_path_length_km"], 0.0)
        self.assertGreaterEqual(summary["mean_campaign_path_terrain_cost_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_path_terrain_cost_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_path_supply_loss_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_path_supply_loss_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_path_attrition_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_path_attrition_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_front_supply_integrity_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_front_supply_integrity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_campaign_front_control_index"], 0.0)
        self.assertLessEqual(summary["mean_campaign_front_control_index"], 1.0)
        self.assertGreaterEqual(summary["mean_tactical_counter_maneuver_index"], 0.0)
        self.assertLessEqual(summary["mean_tactical_counter_maneuver_index"], 1.0)
        self.assertGreaterEqual(summary["mean_tactical_front_pressure_index"], 0.0)
        self.assertLessEqual(summary["mean_tactical_front_pressure_index"], 1.0)
        self.assertGreaterEqual(summary["mean_tactical_supply_contest_index"], 0.0)
        self.assertLessEqual(summary["mean_tactical_supply_contest_index"], 1.0)
        self.assertGreaterEqual(summary["mean_counter_campaign_viability_index"], 0.0)
        self.assertLessEqual(summary["mean_counter_campaign_viability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_strategic_plan_confidence_index"], 0.0)
        self.assertLessEqual(summary["mean_strategic_plan_confidence_index"], 1.0)
        self.assertGreaterEqual(summary["mean_strategic_force_reserve_fraction"], 0.0)
        self.assertLessEqual(summary["mean_strategic_force_reserve_fraction"], 1.0)
        self.assertEqual(
            summary["high_attrition_campaign_count"],
            sum(1 for campaign in world["campaign_movements"] if campaign["attrition_risk_index"] >= 0.65),
        )
        self.assertEqual(
            summary["high_attrition_campaign_path_segment_count"],
            sum(1 for segment in world["campaign_path_segments"] if segment["attrition_index"] >= 0.65),
        )
        self.assertEqual(
            summary["high_pressure_tactical_step_count"],
            sum(
                1
                for engagement in world["tactical_engagements"]
                for step in engagement["steps"]
                if step["front_pressure_index"] >= 0.65
            ),
        )
        self.assertEqual(
            summary["independent_counter_campaign_plan_count"],
            sum(1 for plan in world["strategic_campaign_plans"] if plan["independent_counter_campaign_planned"]),
        )
        self.assertEqual(
            summary["high_escalation_strategic_plan_count"],
            sum(1 for plan in world["strategic_campaign_plans"] if plan["escalation_risk_index"] >= 0.65),
        )
        self.assertEqual(
            summary["high_inventory_stress_market_count"],
            sum(1 for history in world["market_inventory_histories"] if history["high_inventory_stress"]),
        )
        self.assertEqual(summary["dynasty_count"], len(world["dynasties"]))
        self.assertGreater(summary["dynasty_count"], 0)
        self.assertIn("dynastic_lineage_count", summary)
        self.assertEqual(
            summary["dynastic_lineage_count"],
            sum(1 for dynasty in world["dynasties"] if dynasty["parent_dynasty_id"] >= 0),
        )
        self.assertIn("dynasty_root_count", summary)
        self.assertEqual(
            summary["dynasty_root_count"],
            sum(1 for dynasty in world["dynasties"] if dynasty["parent_dynasty_id"] < 0),
        )
        self.assertIn("dynasty_successor_link_count", summary)
        self.assertEqual(
            summary["dynasty_successor_link_count"],
            sum(1 for dynasty in world["dynasties"] if dynasty["successor_dynasty_id"] >= 0),
        )
        self.assertIn("max_dynasty_lineage_depth", summary)
        self.assertEqual(
            summary["max_dynasty_lineage_depth"],
            max((dynasty["lineage_depth"] for dynasty in world["dynasties"]), default=0),
        )
        self.assertIn("mean_dynastic_continuity_index", summary)
        self.assertGreaterEqual(summary["mean_dynastic_continuity_index"], 0.0)
        self.assertLessEqual(summary["mean_dynastic_continuity_index"], 1.0)
        self.assertEqual(summary["ruler_count"], len(world["rulers"]))
        self.assertGreater(summary["ruler_count"], 0)
        self.assertEqual(
            summary["named_ruler_dynasty_count"],
            sum(1 for dynasty in world["dynasties"] if dynasty["ruler_count"] > 0),
        )
        self.assertEqual(summary["ruler_marriage_alliance_count"], len(world["marriage_alliances"]))
        self.assertEqual(summary["cadet_branch_count"], len(world["cadet_branches"]))
        self.assertEqual(
            summary["married_ruler_count"],
            sum(1 for ruler in world["rulers"] if ruler["spouse_ruler_id"] >= 0),
        )
        self.assertEqual(
            summary["max_ruler_lineage_depth"],
            max((ruler["ruler_lineage_depth"] for ruler in world["rulers"]), default=0),
        )
        self.assertGreaterEqual(summary["mean_ruler_legitimacy_index"], 0.0)
        self.assertLessEqual(summary["mean_ruler_legitimacy_index"], 1.0)
        self.assertGreaterEqual(summary["mean_succession_crisis_risk"], 0.0)
        self.assertLessEqual(summary["mean_succession_crisis_risk"], 1.0)
        self.assertGreaterEqual(summary["mean_marriage_alliance_strength"], 0.0)
        self.assertLessEqual(summary["mean_marriage_alliance_strength"], 1.0)
        self.assertGreaterEqual(summary["mean_cadet_branch_claim_strength"], 0.0)
        self.assertLessEqual(summary["mean_cadet_branch_claim_strength"], 1.0)
        self.assertAlmostEqual(
            summary["mean_ruler_legitimacy_index"],
            sum(ruler["legitimacy_index"] for ruler in world["rulers"]) / len(world["rulers"]),
            delta=0.0001,
        )
        self.assertAlmostEqual(
            summary["mean_succession_crisis_risk"],
            sum(ruler["succession_crisis_risk"] for ruler in world["rulers"]) / len(world["rulers"]),
            delta=0.0001,
        )
        if world["marriage_alliances"]:
            self.assertAlmostEqual(
                summary["mean_marriage_alliance_strength"],
                sum(alliance["alliance_strength"] for alliance in world["marriage_alliances"]) / len(world["marriage_alliances"]),
                delta=0.0001,
            )
        if world["cadet_branches"]:
            self.assertAlmostEqual(
                summary["mean_cadet_branch_claim_strength"],
                sum(branch["claim_strength"] for branch in world["cadet_branches"]) / len(world["cadet_branches"]),
                delta=0.0001,
            )
        self.assertEqual(summary["territorial_snapshot_count"], len(world["territorial_snapshots"]))
        self.assertGreater(summary["territorial_snapshot_count"], 0)
        self.assertEqual(
            summary["snapshot_region_record_count"],
            sum(len(snapshot["regions"]) for snapshot in world["territorial_snapshots"]),
        )
        self.assertEqual(
            summary["snapshot_polygon_region_count"],
            sum(
                1
                for snapshot in world["territorial_snapshots"]
                for region in snapshot["regions"]
                if region["dissolved_polygon_area_km2"] > 0.0
            ),
        )
        self.assertIn("mean_snapshot_fragmentation_index", summary)
        self.assertIn("mean_snapshot_polygon_area_error_fraction", summary)
        self.assertIn("mean_snapshot_compactness_index", summary)
        self.assertIn("mean_snapshot_geometry_quality", summary)
        self.assertGreaterEqual(summary["mean_snapshot_geometry_quality"], 0.0)
        self.assertLessEqual(summary["mean_snapshot_geometry_quality"], 1.0)
        self.assertIn("mean_snapshot_boundary_perimeter_km", summary)
        self.assertEqual(
            summary["territorial_cell_edge_boundary_segment_count"],
            len(world["territorial_boundary_segments"]),
        )
        self.assertAlmostEqual(
            summary["territorial_cell_edge_boundary_length_km"],
            sum(segment["length_km"] for segment in world["territorial_boundary_segments"]),
            delta=max(0.001, summary["territorial_cell_edge_boundary_length_km"] * 0.0001),
        )
        self.assertEqual(
            summary["snapshot_region_with_cell_edge_boundary_count"],
            sum(
                1
                for snapshot in world["territorial_snapshots"]
                for region in snapshot["regions"]
                if region["cell_edge_boundary_segment_count"] > 0
            ),
        )
        self.assertGreaterEqual(summary["mean_snapshot_cell_edge_boundary_segment_count"], 0.0)
        self.assertGreaterEqual(summary["mean_snapshot_cell_edge_boundary_length_km"], 0.0)
        self.assertGreaterEqual(summary["mean_snapshot_cell_edge_boundary_quality"], 0.0)
        self.assertLessEqual(summary["mean_snapshot_cell_edge_boundary_quality"], 1.0)
    def test_speaker_population_histories_2(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        first_language = world["language_regions"][0]
        first_speaker_history = world["speaker_population_histories"][0]
        self.assertIn("language_region_id", first_speaker_history)
        self.assertIn("parent_language_region_id", first_speaker_history)
        self.assertIn("population_region_id", first_speaker_history)
        self.assertIn("population_region_ids", first_speaker_history)
        self.assertIn("population_region_count", first_speaker_history)
        self.assertIn("phonological_history_id", first_speaker_history)
        self.assertIn("lexical_diffusion_history_id", first_speaker_history)
        self.assertIn("initial_speaker_population", first_speaker_history)
        self.assertIn("final_speaker_population", first_speaker_history)
        self.assertIn("estimated_speaker_population", first_speaker_history)
        self.assertIn("mean_allophonic_variation_index", first_speaker_history)
        self.assertIn("mean_syllable_pressure_index", first_speaker_history)
        self.assertIn("mean_speaker_contact_index", first_speaker_history)
        self.assertIn("mean_population_adoption_index", first_speaker_history)
        self.assertIn("mean_phonetic_reduction_index", first_speaker_history)
        self.assertIn("mean_lexical_diffusion_pressure_index", first_speaker_history)
        self.assertIn("high_contact_speaker_history", first_speaker_history)
        self.assertIn("steps", first_speaker_history)
        self.assertEqual(first_language["speaker_population_history_id"], first_speaker_history["id"])
        self.assertEqual(first_speaker_history["language_region_id"], first_language["id"])
        self.assertEqual(first_speaker_history["phonological_history_id"], first_language["phonological_history_id"])
        self.assertEqual(first_speaker_history["lexical_diffusion_history_id"], first_language["lexical_diffusion_history_id"])
        self.assertEqual(first_speaker_history["population_region_count"], len(first_speaker_history["population_region_ids"]))
        if first_speaker_history["population_region_ids"]:
            self.assertIn(first_speaker_history["population_region_id"], first_speaker_history["population_region_ids"])
        self.assertEqual(first_speaker_history["step_count"], len(first_speaker_history["steps"]))
        self.assertGreaterEqual(first_speaker_history["initial_speaker_population"], 0.0)
        self.assertGreaterEqual(first_speaker_history["final_speaker_population"], 0.0)
        self.assertGreaterEqual(first_speaker_history["estimated_speaker_population"], 0.0)
        self.assertAlmostEqual(
            first_speaker_history["final_speaker_population"],
            first_speaker_history["estimated_speaker_population"],
            delta=0.001,
        )
        self.assertGreaterEqual(first_speaker_history["mean_allophonic_variation_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_allophonic_variation_index"], 1.0)
        self.assertGreaterEqual(first_speaker_history["mean_syllable_pressure_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_syllable_pressure_index"], 1.0)
        self.assertGreaterEqual(first_speaker_history["mean_speaker_contact_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_speaker_contact_index"], 1.0)
        self.assertGreaterEqual(first_speaker_history["mean_population_adoption_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_population_adoption_index"], 1.0)
        self.assertGreaterEqual(first_speaker_history["mean_phonetic_reduction_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_phonetic_reduction_index"], 1.0)
        self.assertGreaterEqual(first_speaker_history["mean_lexical_diffusion_pressure_index"], 0.0)
        self.assertLessEqual(first_speaker_history["mean_lexical_diffusion_pressure_index"], 1.0)
        self.assertIsInstance(first_speaker_history["high_contact_speaker_history"], bool)
        for index, step in enumerate(first_speaker_history["steps"]):
            self.assertEqual(step["stage_index"], index + 1)
            self.assertIn("era_id", step)
            self.assertGreaterEqual(step["start_year_bp"], step["end_year_bp"])
            self.assertGreaterEqual(step["speaker_population"], 0.0)
            self.assertGreaterEqual(step["speaker_fraction_index"], 0.0)
            self.assertLessEqual(step["speaker_fraction_index"], 1.0)
            self.assertGreaterEqual(step["allophonic_variation_index"], 0.0)
            self.assertLessEqual(step["allophonic_variation_index"], 1.0)
            self.assertGreaterEqual(step["syllable_pressure_index"], 0.0)
            self.assertLessEqual(step["syllable_pressure_index"], 1.0)
            self.assertGreaterEqual(step["phonetic_reduction_index"], 0.0)
            self.assertLessEqual(step["phonetic_reduction_index"], 1.0)
            self.assertGreaterEqual(step["contact_pressure_index"], 0.0)
            self.assertLessEqual(step["contact_pressure_index"], 1.0)
            self.assertGreaterEqual(step["lexical_diffusion_pressure_index"], 0.0)
            self.assertLessEqual(step["lexical_diffusion_pressure_index"], 1.0)
            self.assertGreaterEqual(step["population_adoption_index"], 0.0)
            self.assertLessEqual(step["population_adoption_index"], 1.0)
            self.assertGreaterEqual(step["register_divergence_index"], 0.0)
            self.assertLessEqual(step["register_divergence_index"], 1.0)
            self.assertGreaterEqual(step["pronunciation_regularization_index"], 0.0)
            self.assertLessEqual(step["pronunciation_regularization_index"], 1.0)
        self.assertAlmostEqual(
            first_speaker_history["steps"][-1]["speaker_population"],
            first_speaker_history["final_speaker_population"],
            delta=max(0.001, first_speaker_history["final_speaker_population"] * 0.000001),
        )
    def test_population_regions(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        first_population = world["population_regions"][0]
        self.assertIn("region_id", first_population)
        self.assertIn("estimated_population", first_population)
        self.assertIn("carrying_capacity", first_population)
        self.assertIn("water_security_index", first_population)
        self.assertIn("growth_rate_per_year", first_population)
        self.assertIn("population_pressure", first_population)
        self.assertIn("household_cohort_ids", first_population)
        self.assertIn("household_cohort_count", first_population)
        self.assertIn("representative_household_population", first_population)
        self.assertIn("demographic_agent_history_id", first_population)
        self.assertIn("individual_agent_ids", first_population)
        self.assertIn("individual_agent_count", first_population)
        self.assertEqual(first_population["household_cohort_count"], len(first_population["household_cohort_ids"]))
        self.assertEqual(first_population["individual_agent_count"], len(first_population["individual_agent_ids"]))
        self.assertGreaterEqual(first_population["representative_household_population"], 0.0)

        first_population_history = world["population_histories"][0]
        self.assertIn("population_region_id", first_population_history)
        self.assertIn("region_id", first_population_history)
        self.assertIn("time_step_count", first_population_history)
        self.assertIn("final_population", first_population_history)
        self.assertIn("peak_pressure_index", first_population_history)
        self.assertEqual(first_population_history["time_step_count"], len(world["historical_eras"]))
        self.assertEqual(len(first_population_history["steps"]), len(world["historical_eras"]))
        previous_end = None
        for index, step in enumerate(first_population_history["steps"]):
            self.assertEqual(step["era_id"], world["historical_eras"][index]["id"])
            self.assertIn("start_population", step)
            self.assertIn("end_population", step)
            self.assertIn("population_change", step)
            self.assertIn("migration_delta", step)
            self.assertIn("conflict_loss", step)
            self.assertIn("carrying_capacity_used_fraction", step)
            self.assertGreaterEqual(step["start_population"], 0.0)
            self.assertGreaterEqual(step["end_population"], 0.0)
            self.assertAlmostEqual(
                step["population_change"],
                step["end_population"] - step["start_population"],
                delta=max(1.0, step["end_population"] * 0.0001),
            )
            if previous_end is not None:
                self.assertAlmostEqual(step["start_population"], previous_end, delta=max(1.0, previous_end * 0.0001))
            previous_end = step["end_population"]
        self.assertAlmostEqual(
            first_population_history["final_population"],
            first_population_history["steps"][-1]["end_population"],
            delta=max(1.0, first_population_history["final_population"] * 0.0001),
        )
    def test_household_cohorts(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        first_household = world["household_cohorts"][0]
        self.assertIn("population_region_id", first_household)
        self.assertIn("region_id", first_household)
        self.assertIn("cohort_type", first_household)
        self.assertIn("population", first_household)
        self.assertIn("household_count", first_household)
        self.assertIn("average_household_size", first_household)
        self.assertIn("income_index", first_household)
        self.assertIn("consumption_pressure_index", first_household)
        self.assertIn("vulnerability_index", first_household)
        self.assertIn("migration_propensity_index", first_household)
        self.assertIn("fertility_rate_per_year", first_household)
        self.assertIn("mortality_risk_index", first_household)
        self.assertIn("labor_participation_index", first_household)
        self.assertGreaterEqual(first_household["population"], 0.0)
        self.assertGreaterEqual(first_household["household_count"], 0.0)
        self.assertGreater(first_household["average_household_size"], 0.0)
        self.assertAlmostEqual(
            first_household["household_count"] * first_household["average_household_size"],
            first_household["population"],
            delta=max(1.0, first_household["population"] * 0.0001),
        )
        for key in (
            "income_index",
            "consumption_pressure_index",
            "vulnerability_index",
            "migration_propensity_index",
            "mortality_risk_index",
            "labor_participation_index",
        ):
            self.assertGreaterEqual(first_household[key], 0.0)
            self.assertLessEqual(first_household[key], 1.0)
        self.assertGreaterEqual(first_household["fertility_rate_per_year"], 0.0)

        first_economy_history = world["economy_histories"][0]
        self.assertIn("region_id", first_economy_history)
        self.assertIn("dominant_resource", first_economy_history)
        self.assertIn("time_step_count", first_economy_history)
        self.assertIn("final_gross_output_index", first_economy_history)
        self.assertIn("final_treasury_index", first_economy_history)
        self.assertIn("max_army_capacity_population", first_economy_history)
        self.assertEqual(first_economy_history["time_step_count"], len(world["historical_eras"]))
        self.assertEqual(len(first_economy_history["steps"]), len(world["historical_eras"]))
        previous_treasury = None
        for index, step in enumerate(first_economy_history["steps"]):
            self.assertEqual(step["era_id"], world["historical_eras"][index]["id"])
            self.assertGreaterEqual(step["population"], 0.0)
            self.assertGreaterEqual(step["gross_output_index"], 0.0)
            self.assertGreaterEqual(step["agricultural_output_index"], 0.0)
            self.assertGreaterEqual(step["resource_output_index"], 0.0)
            self.assertGreaterEqual(step["trade_output_index"], 0.0)
            self.assertGreaterEqual(step["urban_services_index"], 0.0)
            self.assertGreaterEqual(step["tax_revenue_index"], 0.0)
            self.assertGreaterEqual(step["trade_revenue_index"], 0.0)
            self.assertGreaterEqual(step["administration_cost_index"], 0.0)
            self.assertGreaterEqual(step["army_maintenance_cost_index"], 0.0)
            self.assertGreaterEqual(step["war_cost_index"], 0.0)
            self.assertGreaterEqual(step["treasury_end_index"], 0.0)
            self.assertGreaterEqual(step["army_capacity_population"], 0.0)
            self.assertGreaterEqual(step["mobilized_force_population"], 0.0)
            self.assertGreaterEqual(step["prosperity_index"], 0.0)
            self.assertLessEqual(step["prosperity_index"], 1.0)
            self.assertGreaterEqual(step["food_security_index"], 0.0)
            self.assertLessEqual(step["food_security_index"], 1.0)
            self.assertGreaterEqual(step["trade_dependency_index"], 0.0)
            self.assertLessEqual(step["trade_dependency_index"], 1.0)
            self.assertGreaterEqual(step["military_burden_index"], 0.0)
            self.assertLessEqual(step["military_burden_index"], 1.0)
            self.assertAlmostEqual(
                step["treasury_start_index"]
                + step["tax_revenue_index"]
                + step["trade_revenue_index"]
                + step["insolvency_adjustment_index"]
                - step["administration_cost_index"]
                - step["army_maintenance_cost_index"]
                - step["war_cost_index"]
                - step["treasury_end_index"],
                step["balance_residual_index"],
                delta=0.001,
            )
            self.assertAlmostEqual(step["balance_residual_index"], 0.0, delta=0.001)
            if previous_treasury is not None:
                self.assertAlmostEqual(
                    step["treasury_start_index"],
                    previous_treasury,
                    delta=max(0.001, previous_treasury * 0.0001),
                )
            previous_treasury = step["treasury_end_index"]
        self.assertAlmostEqual(
            first_economy_history["final_gross_output_index"],
            first_economy_history["steps"][-1]["gross_output_index"],
            delta=max(0.001, first_economy_history["final_gross_output_index"] * 0.0001),
        )
    def test_firm_agents(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        first_firm = world["firm_agents"][0]
        self.assertIn("region_id", first_firm)
        self.assertIn("population_region_id", first_firm)
        self.assertIn("settlement_id", first_firm)
        self.assertIn("sector", first_firm)
        self.assertIn("output_index", first_firm)
        self.assertIn("employment_capacity", first_firm)
        self.assertIn("wage_index", first_firm)
        self.assertIn("productivity_index", first_firm)
        self.assertIn("market_dependency_index", first_firm)
        self.assertIn("capital_stock_index", first_firm)
        self.assertIn("supply_chain_risk_index", first_firm)
        self.assertIn("tax_contribution_index", first_firm)
        self.assertGreaterEqual(first_firm["output_index"], 0.0)
        self.assertGreaterEqual(first_firm["employment_capacity"], 0.0)
        self.assertGreaterEqual(first_firm["tax_contribution_index"], 0.0)
        for key in (
            "wage_index",
            "productivity_index",
            "market_dependency_index",
            "capital_stock_index",
            "supply_chain_risk_index",
        ):
            self.assertGreaterEqual(first_firm[key], 0.0)
            self.assertLessEqual(first_firm[key], 1.0)

        first_agent_history = world["demographic_agent_histories"][0]
        self.assertIn("population_region_id", first_agent_history)
        self.assertIn("region_id", first_agent_history)
        self.assertIn("household_cohort_ids", first_agent_history)
        self.assertIn("firm_agent_ids", first_agent_history)
        self.assertIn("final_agent_population", first_agent_history)
        self.assertIn("mean_labor_participation_index", first_agent_history)
        self.assertEqual(first_agent_history["step_count"], len(first_agent_history["steps"]))
        self.assertGreaterEqual(first_agent_history["final_agent_population"], 0.0)
        self.assertGreaterEqual(first_agent_history["mean_labor_participation_index"], 0.0)
        self.assertLessEqual(first_agent_history["mean_labor_participation_index"], 1.0)
        for index, step in enumerate(first_agent_history["steps"]):
            self.assertEqual(step["stage_index"], index + 1)
            self.assertIn("era_id", step)
            self.assertGreaterEqual(step["start_year_bp"], step["end_year_bp"])
            self.assertGreaterEqual(step["start_population"], 0.0)
            self.assertGreaterEqual(step["end_population"], 0.0)
            self.assertGreaterEqual(step["working_population"], 0.0)
            self.assertGreaterEqual(step["dependent_population"], 0.0)
            self.assertAlmostEqual(
                step["working_population"] + step["dependent_population"],
                step["end_population"],
                delta=max(1.0, step["end_population"] * 0.0001),
            )
            for key in (
                "migration_propensity_index",
                "consumption_pressure_index",
                "vulnerability_index",
                "labor_participation_index",
            ):
                self.assertGreaterEqual(step[key], 0.0)
                self.assertLessEqual(step[key], 1.0)

        first_individual = world["individual_agents"][0]
        self.assertIn("population_region_id", first_individual)
        self.assertIn("region_id", first_individual)
        self.assertIn("household_cohort_id", first_individual)
        self.assertIn("culture_region_id", first_individual)
        self.assertIn("language_region_id", first_individual)
        self.assertIn("name", first_individual)
        self.assertIn("role", first_individual)
        self.assertIn("birth_year_bp", first_individual)
        self.assertIn("death_year_bp", first_individual)
        self.assertIn("lifespan_years", first_individual)
        self.assertIn("married_person_id", first_individual)
        self.assertIn("parent_person_ids", first_individual)
        self.assertIn("child_person_ids", first_individual)
        self.assertIn("property_value_index", first_individual)
        self.assertIn("mobility_index", first_individual)
        self.assertIn("vulnerability_index", first_individual)
        self.assertIn("event_ids", first_individual)
        self.assertIn("event_count", first_individual)
        self.assertTrue(first_individual["name"])
        self.assertTrue(first_individual["role"])
        self.assertGreaterEqual(first_individual["birth_year_bp"], first_individual["death_year_bp"])
        self.assertAlmostEqual(
            first_individual["lifespan_years"],
            first_individual["birth_year_bp"] - first_individual["death_year_bp"],
            delta=max(0.001, first_individual["lifespan_years"] * 0.0001),
        )
        self.assertEqual(first_individual["event_count"], len(first_individual["event_ids"]))
        self.assertGreaterEqual(first_individual["property_value_index"], 0.0)
        self.assertGreaterEqual(first_individual["mobility_index"], 0.0)
        self.assertLessEqual(first_individual["mobility_index"], 1.0)
        self.assertGreaterEqual(first_individual["vulnerability_index"], 0.0)
        self.assertLessEqual(first_individual["vulnerability_index"], 1.0)

        first_life_event = world["individual_life_events"][0]
        self.assertIn("person_id", first_life_event)
        self.assertIn("related_person_id", first_life_event)
        self.assertIn("population_region_id", first_life_event)
        self.assertIn("region_id", first_life_event)
        self.assertIn("household_cohort_id", first_life_event)
        self.assertIn("era_id", first_life_event)
        self.assertIn("event_type", first_life_event)
        self.assertIn("year_bp", first_life_event)
        self.assertIn("property_value_index", first_life_event)
        self.assertIn("demographic_pressure_index", first_life_event)
        self.assertIn("mortality_risk_index", first_life_event)
        self.assertIn("inheritance_fraction", first_life_event)
        self.assertIn(first_life_event["event_type"], {"birth", "death", "marriage", "property_transfer"})
        self.assertEqual(first_life_event["person_id"], first_individual["id"])
        self.assertGreaterEqual(first_life_event["year_bp"], 0.0)
        self.assertGreaterEqual(first_life_event["property_value_index"], 0.0)
        self.assertGreaterEqual(first_life_event["demographic_pressure_index"], 0.0)
        self.assertLessEqual(first_life_event["demographic_pressure_index"], 1.0)
        self.assertGreaterEqual(first_life_event["mortality_risk_index"], 0.0)
        self.assertLessEqual(first_life_event["mortality_risk_index"], 1.0)
        self.assertGreaterEqual(first_life_event["inheritance_fraction"], 0.0)
        self.assertLessEqual(first_life_event["inheritance_fraction"], 1.0)

        if world["conflicts"]:
            first_conflict = world["conflicts"][0]
            self.assertIn("era_id", first_conflict)
            self.assertIn("region_a", first_conflict)
            self.assertIn("region_b", first_conflict)
            self.assertIn("cause", first_conflict)
            self.assertIn("outcome", first_conflict)
            self.assertIn("intensity", first_conflict)
            self.assertIn("war_duration_years", first_conflict)
            self.assertIn("region_a_force_estimate", first_conflict)
            self.assertIn("region_b_force_estimate", first_conflict)
            self.assertIn("mobilized_population", first_conflict)
            self.assertIn("casualty_rate", first_conflict)
            self.assertIn("logistics_strain_index", first_conflict)
            self.assertIn("economic_disruption_index", first_conflict)
            self.assertIn("estimated_casualties", first_conflict)
            self.assertGreaterEqual(first_conflict["war_duration_years"], 0.0)
            self.assertGreaterEqual(first_conflict["mobilized_population"], 0.0)
            self.assertGreaterEqual(first_conflict["casualty_rate"], 0.0)
            self.assertLessEqual(first_conflict["casualty_rate"], 1.0)
            self.assertGreaterEqual(first_conflict["logistics_strain_index"], 0.0)
            self.assertLessEqual(first_conflict["logistics_strain_index"], 1.0)
            self.assertGreaterEqual(first_conflict["economic_disruption_index"], 0.0)
            self.assertLessEqual(first_conflict["economic_disruption_index"], 1.0)

        first_dynasty = world["dynasties"][0]
        self.assertIn("region_id", first_dynasty)
        self.assertIn("parent_dynasty_id", first_dynasty)
        self.assertIn("founder_dynasty_id", first_dynasty)
        self.assertIn("successor_dynasty_id", first_dynasty)
        self.assertIn("collapse_reason", first_dynasty)
        self.assertIn("lineage_depth", first_dynasty)
        self.assertIn("child_dynasty_count", first_dynasty)
        self.assertIn("child_dynasty_ids", first_dynasty)
        self.assertIn("duration_years", first_dynasty)
        self.assertIn("legitimacy_index", first_dynasty)
        self.assertIn("succession_pressure", first_dynasty)
        self.assertIn("dynastic_continuity_index", first_dynasty)
        self.assertIn("founder_ruler_id", first_dynasty)
        self.assertIn("ruler_count", first_dynasty)
        self.assertIn("marriage_alliance_count", first_dynasty)
        self.assertIn("cadet_branch_count", first_dynasty)
        self.assertEqual(first_dynasty["founder_dynasty_id"], first_dynasty["id"])
        self.assertEqual(first_dynasty["child_dynasty_count"], len(first_dynasty["child_dynasty_ids"]))
        self.assertGreaterEqual(first_dynasty["dynastic_continuity_index"], 0.0)
        self.assertLessEqual(first_dynasty["dynastic_continuity_index"], 1.0)

        first_ruler = world["rulers"][0]
        self.assertIn("dynasty_id", first_ruler)
        self.assertIn("name", first_ruler)
        self.assertIn("regnal_number", first_ruler)
        self.assertIn("parent_ruler_id", first_ruler)
        self.assertIn("predecessor_ruler_id", first_ruler)
        self.assertIn("successor_ruler_id", first_ruler)
        self.assertIn("spouse_ruler_id", first_ruler)
        self.assertIn("marriage_alliance_id", first_ruler)
        self.assertIn("cadet_branch_id", first_ruler)
        self.assertIn("birth_year_bp", first_ruler)
        self.assertIn("reign_start_year_bp", first_ruler)
        self.assertIn("reign_end_year_bp", first_ruler)
        self.assertIn("reign_length_years", first_ruler)
        self.assertIn("ruler_lineage_depth", first_ruler)
        self.assertIn("legitimacy_index", first_ruler)
        self.assertIn("succession_claim_strength", first_ruler)
        self.assertIn("military_prestige_index", first_ruler)
        self.assertIn("economic_patronage_index", first_ruler)
        self.assertIn("succession_crisis_risk", first_ruler)
        self.assertGreater(first_ruler["regnal_number"], 0)
        self.assertGreaterEqual(first_ruler["reign_start_year_bp"], first_ruler["reign_end_year_bp"])
        self.assertAlmostEqual(
            first_ruler["reign_length_years"],
            first_ruler["reign_start_year_bp"] - first_ruler["reign_end_year_bp"],
            delta=0.001,
        )
        self.assertGreaterEqual(first_ruler["legitimacy_index"], 0.0)
        self.assertLessEqual(first_ruler["legitimacy_index"], 1.0)
        self.assertGreaterEqual(first_ruler["succession_claim_strength"], 0.0)
        self.assertLessEqual(first_ruler["succession_claim_strength"], 1.0)
        self.assertGreaterEqual(first_ruler["military_prestige_index"], 0.0)
        self.assertLessEqual(first_ruler["military_prestige_index"], 1.0)
        self.assertGreaterEqual(first_ruler["economic_patronage_index"], 0.0)
        self.assertLessEqual(first_ruler["economic_patronage_index"], 1.0)
        self.assertGreaterEqual(first_ruler["succession_crisis_risk"], 0.0)
        self.assertLessEqual(first_ruler["succession_crisis_risk"], 1.0)

        if world["marriage_alliances"]:
            first_alliance = world["marriage_alliances"][0]
            self.assertIn("dynasty_a_id", first_alliance)
            self.assertIn("dynasty_b_id", first_alliance)
            self.assertIn("ruler_a_id", first_alliance)
            self.assertIn("ruler_b_id", first_alliance)
            self.assertIn("region_a_id", first_alliance)
            self.assertIn("region_b_id", first_alliance)
            self.assertIn("alliance_year_bp", first_alliance)
            self.assertIn("alliance_strength", first_alliance)
            self.assertIn("trade_pact_index", first_alliance)
            self.assertIn("succession_dispute_risk", first_alliance)
            self.assertGreaterEqual(first_alliance["alliance_strength"], 0.0)
            self.assertLessEqual(first_alliance["alliance_strength"], 1.0)
            self.assertGreaterEqual(first_alliance["trade_pact_index"], 0.0)
            self.assertLessEqual(first_alliance["trade_pact_index"], 1.0)
            self.assertGreaterEqual(first_alliance["succession_dispute_risk"], 0.0)
            self.assertLessEqual(first_alliance["succession_dispute_risk"], 1.0)

        if world["cadet_branches"]:
            first_branch = world["cadet_branches"][0]
            self.assertIn("dynasty_id", first_branch)
            self.assertIn("parent_dynasty_id", first_branch)
            self.assertIn("founder_ruler_id", first_branch)
            self.assertIn("heir_ruler_ids", first_branch)
            self.assertIn("branch_start_year_bp", first_branch)
            self.assertIn("branch_end_year_bp", first_branch)
            self.assertIn("claim_strength", first_branch)
            self.assertIn("cadet_legitimacy_index", first_branch)
            self.assertGreaterEqual(first_branch["branch_start_year_bp"], first_branch["branch_end_year_bp"])
            self.assertGreaterEqual(first_branch["claim_strength"], 0.0)
            self.assertLessEqual(first_branch["claim_strength"], 1.0)
            self.assertGreaterEqual(first_branch["cadet_legitimacy_index"], 0.0)
            self.assertLessEqual(first_branch["cadet_legitimacy_index"], 1.0)

        first_snapshot = world["territorial_snapshots"][0]
        self.assertIn("era_id", first_snapshot)
        self.assertIn("dominant_process", first_snapshot)
        self.assertIn("assigned_land_fraction", first_snapshot)
        self.assertIn("fragmentation_index", first_snapshot)
        self.assertEqual(first_snapshot["region_count"], len(first_snapshot["regions"]))
        self.assertGreater(first_snapshot["region_count"], 0)
        self.assertIn("boundary_cell_ids", first_snapshot["regions"][0])
        self.assertIn("boundary_ring", first_snapshot["regions"][0])
        self.assertIn("crosses_antimeridian", first_snapshot["regions"][0])
        self.assertIn("boundary_perimeter_km", first_snapshot["regions"][0])
        self.assertIn("dissolved_polygon_area_km2", first_snapshot["regions"][0])
        self.assertIn("polygon_area_error_fraction", first_snapshot["regions"][0])
        self.assertIn("compactness_index", first_snapshot["regions"][0])
        self.assertIn("geometry_quality", first_snapshot["regions"][0])
        self.assertIn("stability_index", first_snapshot["regions"][0])
        self.assertIn("estimated_population", first_snapshot["regions"][0])
        self.assertIn("cell_edge_boundary_segment_ids", first_snapshot["regions"][0])
        self.assertIn("cell_edge_boundary_segment_count", first_snapshot["regions"][0])
        self.assertIn("cell_edge_boundary_length_km", first_snapshot["regions"][0])
        self.assertIn("mean_cell_edge_boundary_segment_quality", first_snapshot["regions"][0])
        self.assertIn("neighbor_region_ids", first_snapshot["regions"][0])
        self.assertIn("cell_edge_dissolved_area_km2", first_snapshot["regions"][0])
        self.assertEqual(
            first_snapshot["regions"][0]["cell_edge_boundary_segment_count"],
            len(first_snapshot["regions"][0]["cell_edge_boundary_segment_ids"]),
        )
        self.assertGreaterEqual(first_snapshot["regions"][0]["cell_edge_boundary_length_km"], 0.0)
        self.assertGreaterEqual(first_snapshot["regions"][0]["mean_cell_edge_boundary_segment_quality"], 0.0)
        self.assertLessEqual(first_snapshot["regions"][0]["mean_cell_edge_boundary_segment_quality"], 1.0)
        self.assertGreaterEqual(first_snapshot["regions"][0]["cell_edge_dissolved_area_km2"], 0.0)

        if world["territorial_boundary_segments"]:
            first_territorial_segment = world["territorial_boundary_segments"][0]
            self.assertEqual(first_territorial_segment["id"], 0)
            self.assertIn("source_edge_id", first_territorial_segment)
            self.assertIn("region_a_id", first_territorial_segment)
            self.assertIn("region_b_id", first_territorial_segment)
            self.assertIn("length_km", first_territorial_segment)
            self.assertIn("boundary_segment_quality", first_territorial_segment)
            self.assertIn("natural_boundary", first_territorial_segment)
            self.assertGreater(first_territorial_segment["length_km"], 0.0)
            self.assertGreaterEqual(first_territorial_segment["boundary_segment_quality"], 0.0)
            self.assertLessEqual(first_territorial_segment["boundary_segment_quality"], 1.0)

        if world["borders"]:
            first_border = world["borders"][0]
            self.assertIn("region_a", first_border)
            self.assertIn("region_b", first_border)
            self.assertIn("type", first_border)
            self.assertIn("length_km", first_border)

        if world["sacred_areas"]:
            first_site = world["sacred_areas"][0]
            self.assertIn("culture_region_id", first_site)
            self.assertIn("language_region_id", first_site)
            self.assertIn("type", first_site)
            self.assertIn("significance", first_site)

        if world["ruins"]:
            first_ruin = world["ruins"][0]
            self.assertIn("culture_region_id", first_ruin)
            self.assertIn("language_region_id", first_ruin)
            self.assertIn("type", first_ruin)
            self.assertIn("abandonment_reason", first_ruin)
            self.assertIn("preservation_score", first_ruin)

        if world["trade_flows"]:
            first_trade = world["trade_flows"][0]
            self.assertIn("route_id", first_trade)
            self.assertIn("primary_good", first_trade)
            self.assertIn("volume_index", first_trade)
            self.assertIn("friction", first_trade)
            self.assertIn("interregional", first_trade)

        first_plate_graph_node = world["plate_graph"]["nodes"][0]
        self.assertIn("plate_id", first_plate_graph_node)
        self.assertIn("degree", first_plate_graph_node)
        self.assertIn("edge_ids", first_plate_graph_node)
        if world["plate_graph"]["edges"]:
            first_plate_graph_edge = world["plate_graph"]["edges"][0]
            self.assertIn("plate_a", first_plate_graph_edge)
            self.assertIn("plate_b", first_plate_graph_edge)
            self.assertIn("cell_edge_count", first_plate_graph_edge)
            self.assertIn("dominant_boundary_type", first_plate_graph_edge)

        if world["river_graph"]["nodes"]:
            first_river_graph_node = world["river_graph"]["nodes"][0]
            self.assertIn("cell_id", first_river_graph_node)
            self.assertIn("flow_to_cell_id", first_river_graph_node)
            self.assertIn("upstream_cell_ids", first_river_graph_node)
        if world["river_graph"]["edges"]:
            first_river_graph_edge = world["river_graph"]["edges"][0]
            self.assertIn("from_cell_id", first_river_graph_edge)
            self.assertIn("to_cell_id", first_river_graph_edge)
            self.assertIn("length_km", first_river_graph_edge)

        first_watershed_graph_node = world["watershed_graph"]["nodes"][0]
        self.assertIn("watershed_id", first_watershed_graph_node)
        self.assertIn("basin_id", first_watershed_graph_node)
        self.assertIn("edge_ids", first_watershed_graph_node)
        if world["watershed_graph"]["edges"]:
            first_watershed_graph_edge = world["watershed_graph"]["edges"][0]
            self.assertIn("watershed_a", first_watershed_graph_edge)
            self.assertIn("watershed_b", first_watershed_graph_edge)
            self.assertIn("boundary_edge_count", first_watershed_graph_edge)

        first_trade_graph_node = world["trade_route_graph"]["nodes"][0]
        self.assertIn("settlement_id", first_trade_graph_node)
        self.assertIn("region_id", first_trade_graph_node)
        self.assertIn("edge_ids", first_trade_graph_node)
        if world["trade_route_graph"]["edges"]:
            first_trade_graph_edge = world["trade_route_graph"]["edges"][0]
            self.assertIn("route_id", first_trade_graph_edge)
            self.assertIn("trade_flow_id", first_trade_graph_edge)
            self.assertIn("route_corridor_id", first_trade_graph_edge)
            self.assertIn("volume_index", first_trade_graph_edge)

        first_political_graph_node = world["political_region_graph"]["nodes"][0]
        self.assertIn("region_id", first_political_graph_node)
        self.assertIn("capital_settlement_id", first_political_graph_node)
        self.assertIn("edge_ids", first_political_graph_node)
        if world["political_region_graph"]["edges"]:
            first_political_graph_edge = world["political_region_graph"]["edges"][0]
            self.assertIn("region_a", first_political_graph_edge)
            self.assertIn("region_b", first_political_graph_edge)
            self.assertIn("border_ids", first_political_graph_edge)
            self.assertIn("trade_flow_ids", first_political_graph_edge)
    def test_logistics_networks(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        first_logistics = world["logistics_networks"][0]
        self.assertIn("region_id", first_logistics)
        self.assertIn("route_ids", first_logistics)
        self.assertIn("trade_flow_ids", first_logistics)
        self.assertIn("border_ids", first_logistics)
        self.assertIn("total_route_distance_km", first_logistics)
        self.assertIn("total_trade_volume_index", first_logistics)
        self.assertIn("supply_capacity_index", first_logistics)
        self.assertIn("transport_efficiency_index", first_logistics)
        self.assertIn("logistics_resilience_index", first_logistics)
        self.assertIn("chokepoint_exposure_index", first_logistics)
        self.assertEqual(first_logistics["route_count"], len(first_logistics["route_ids"]))
        self.assertEqual(first_logistics["trade_flow_count"], len(first_logistics["trade_flow_ids"]))
        self.assertEqual(first_logistics["border_count"], len(first_logistics["border_ids"]))
        self.assertGreaterEqual(first_logistics["total_route_distance_km"], 0.0)
        self.assertGreaterEqual(first_logistics["total_trade_volume_index"], 0.0)
        self.assertGreaterEqual(first_logistics["supply_capacity_index"], 0.0)
        self.assertLessEqual(first_logistics["supply_capacity_index"], 1.0)
        self.assertGreaterEqual(first_logistics["transport_efficiency_index"], 0.0)
        self.assertLessEqual(first_logistics["transport_efficiency_index"], 1.0)
        self.assertGreaterEqual(first_logistics["logistics_resilience_index"], 0.0)
        self.assertLessEqual(first_logistics["logistics_resilience_index"], 1.0)
        self.assertGreaterEqual(first_logistics["chokepoint_exposure_index"], 0.0)
        self.assertLessEqual(first_logistics["chokepoint_exposure_index"], 1.0)

        if world["market_exchanges"]:
            first_market = world["market_exchanges"][0]
            self.assertIn("trade_flow_id", first_market)
            self.assertIn("route_id", first_market)
            self.assertIn("region_from", first_market)
            self.assertIn("region_to", first_market)
            self.assertIn("supply_index", first_market)
            self.assertIn("demand_index", first_market)
            self.assertIn("price_spread_index", first_market)
            self.assertIn("market_access_index", first_market)
            self.assertIn("tax_revenue_index", first_market)
            self.assertIn("food_security_link_index", first_market)
            self.assertIn("disruption_risk_index", first_market)
            self.assertIn("market_clearing_record_id", first_market)
            self.assertIn("cleared_volume_index", first_market)
            self.assertIn("unmet_demand_index", first_market)
            self.assertIn("clearance_fraction", first_market)
            self.assertGreaterEqual(first_market["volume_index"], 0.0)
            self.assertGreaterEqual(first_market["tax_revenue_index"], 0.0)
            self.assertGreaterEqual(first_market["cleared_volume_index"], 0.0)
            self.assertGreaterEqual(first_market["unmet_demand_index"], 0.0)
            for key in (
                "supply_index",
                "demand_index",
                "price_spread_index",
                "market_access_index",
                "food_security_link_index",
                "disruption_risk_index",
                "clearance_fraction",
            ):
                self.assertGreaterEqual(first_market[key], 0.0)
                self.assertLessEqual(first_market[key], 1.0)

            self.assertTrue(world["route_capacity_constraints"])
            first_constraint = world["route_capacity_constraints"][0]
            self.assertIn("route_id", first_constraint)
            self.assertIn("route_type", first_constraint)
            self.assertIn("market_exchange_ids", first_constraint)
            self.assertIn("market_exchange_count", first_constraint)
            self.assertIn("requested_volume_index", first_constraint)
            self.assertIn("capacity_volume_index", first_constraint)
            self.assertIn("cleared_volume_index", first_constraint)
            self.assertIn("unmet_volume_index", first_constraint)
            self.assertIn("utilization_index", first_constraint)
            self.assertIn("congestion_index", first_constraint)
            self.assertIn("shortage_index", first_constraint)
            self.assertIn("spoilage_loss_index", first_constraint)
            self.assertEqual(first_constraint["market_exchange_count"], len(first_constraint["market_exchange_ids"]))
            self.assertGreaterEqual(first_constraint["requested_volume_index"], 0.0)
            self.assertGreaterEqual(first_constraint["capacity_volume_index"], 0.0)
            self.assertGreaterEqual(first_constraint["cleared_volume_index"], 0.0)
            self.assertGreaterEqual(first_constraint["unmet_volume_index"], 0.0)
            self.assertAlmostEqual(
                first_constraint["cleared_volume_index"] + first_constraint["unmet_volume_index"],
                first_constraint["requested_volume_index"],
                delta=max(0.001, first_constraint["requested_volume_index"] * 0.0001),
            )
            for key in ("utilization_index", "congestion_index", "shortage_index", "spoilage_loss_index"):
                self.assertGreaterEqual(first_constraint[key], 0.0)
                self.assertLessEqual(first_constraint[key], 1.0)
            constraint_route = next(route for route in world["routes"] if route["id"] == first_constraint["route_id"])
            self.assertEqual(constraint_route["route_capacity_constraint_id"], first_constraint["id"])
            self.assertIn("market_capacity_volume_index", constraint_route)
            self.assertIn("market_capacity_utilization_index", constraint_route)

            self.assertTrue(world["market_clearing_records"])
            first_clearing = world["market_clearing_records"][0]
            self.assertIn("market_exchange_id", first_clearing)
            self.assertIn("trade_flow_id", first_clearing)
            self.assertIn("route_id", first_clearing)
            self.assertIn("route_capacity_constraint_id", first_clearing)
            self.assertIn("primary_good", first_clearing)
            self.assertIn("requested_volume_index", first_clearing)
            self.assertIn("cleared_volume_index", first_clearing)
            self.assertIn("unmet_demand_index", first_clearing)
            self.assertIn("clearance_fraction", first_clearing)
            self.assertIn("route_utilization_index", first_clearing)
            self.assertIn("price_adjustment_index", first_clearing)
            self.assertIn("rationing_index", first_clearing)
            self.assertIn("producer_surplus_index", first_clearing)
            self.assertIn("consumer_welfare_index", first_clearing)
            self.assertIn("agent_order_ids", first_clearing)
            self.assertIn("agent_order_count", first_clearing)
            self.assertIn("price_iteration_ids", first_clearing)
            self.assertIn("price_iteration_count", first_clearing)
            self.assertIn("endogenous_supply_index", first_clearing)
            self.assertIn("endogenous_demand_index", first_clearing)
            self.assertIn("equilibrium_price_index", first_clearing)
            self.assertIn("price_residual_index", first_clearing)
            self.assertGreaterEqual(first_clearing["requested_volume_index"], 0.0)
            self.assertGreaterEqual(first_clearing["cleared_volume_index"], 0.0)
            self.assertGreaterEqual(first_clearing["unmet_demand_index"], 0.0)
            self.assertGreaterEqual(first_clearing["endogenous_supply_index"], 0.0)
            self.assertGreaterEqual(first_clearing["endogenous_demand_index"], 0.0)
            self.assertEqual(first_clearing["agent_order_count"], len(first_clearing["agent_order_ids"]))
            self.assertEqual(first_clearing["price_iteration_count"], len(first_clearing["price_iteration_ids"]))
            self.assertAlmostEqual(
                first_clearing["cleared_volume_index"] + first_clearing["unmet_demand_index"],
                first_clearing["requested_volume_index"],
                delta=max(0.001, first_clearing["requested_volume_index"] * 0.0001),
            )
            for key in (
                "clearance_fraction",
                "route_utilization_index",
                "price_adjustment_index",
                "rationing_index",
                "producer_surplus_index",
                "consumer_welfare_index",
                "equilibrium_price_index",
                "price_residual_index",
            ):
                self.assertGreaterEqual(first_clearing[key], 0.0)
                self.assertLessEqual(first_clearing[key], 1.0)
            clearing_market = next(
                market for market in world["market_exchanges"] if market["id"] == first_clearing["market_exchange_id"]
            )
            self.assertEqual(clearing_market["market_clearing_record_id"], first_clearing["id"])
            self.assertEqual(clearing_market["route_id"], first_clearing["route_id"])
            self.assertAlmostEqual(
                clearing_market["cleared_volume_index"],
                first_clearing["cleared_volume_index"],
                delta=max(0.001, first_clearing["cleared_volume_index"] * 0.0001),
            )
            self.assertTrue(world["market_agent_orders"])
            first_order = next(
                order for order in world["market_agent_orders"] if order["id"] in first_clearing["agent_order_ids"]
            )
            self.assertIn("agent_type", first_order)
            self.assertIn("order_side", first_order)
            self.assertIn("order_kind", first_order)
            self.assertIn("limit_price_index", first_order)
            self.assertIn("price_acceptance_index", first_order)
            self.assertIn("rationing_index", first_order)
            self.assertIn("inventory_change_index", first_order)
            self.assertEqual(first_order["market_exchange_id"], first_clearing["market_exchange_id"])
            self.assertEqual(first_order["market_clearing_record_id"], first_clearing["id"])
            self.assertIn(first_order["agent_type"], {"firm", "household_cohort", "state"})
            self.assertIn(first_order["order_side"], {"supply", "demand"})
            self.assertGreaterEqual(first_order["requested_volume_index"], 0.0)
            self.assertGreaterEqual(first_order["cleared_volume_index"], 0.0)
            self.assertLessEqual(first_order["cleared_volume_index"], first_order["requested_volume_index"] + 0.001)
            self.assertGreaterEqual(first_order["inventory_change_index"], -1.0)
            self.assertLessEqual(first_order["inventory_change_index"], 1.0)
            for key in ("limit_price_index", "price_acceptance_index", "rationing_index"):
                self.assertGreaterEqual(first_order[key], 0.0)
                self.assertLessEqual(first_order[key], 1.0)

            self.assertTrue(world["market_price_iterations"])
            first_iteration = next(
                iteration
                for iteration in world["market_price_iterations"]
                if iteration["id"] in first_clearing["price_iteration_ids"]
            )
            self.assertEqual(first_iteration["market_exchange_id"], first_clearing["market_exchange_id"])
            self.assertEqual(first_iteration["market_clearing_record_id"], first_clearing["id"])
            self.assertGreater(first_iteration["iteration_index"], 0)
            self.assertEqual(first_iteration["order_count"], len(first_iteration["order_ids"]))
            self.assertGreaterEqual(first_iteration["supply_volume_index"], 0.0)
            self.assertGreaterEqual(first_iteration["demand_volume_index"], 0.0)
            self.assertAlmostEqual(
                first_iteration["demand_volume_index"] - first_iteration["supply_volume_index"],
                first_iteration["imbalance_index"],
                delta=max(0.001, abs(first_iteration["imbalance_index"]) * 0.0001),
            )
            for order_id in first_iteration["order_ids"]:
                self.assertIn(order_id, first_clearing["agent_order_ids"])
            for key in ("price_index", "excess_demand_index", "price_adjustment_index"):
                self.assertGreaterEqual(first_iteration[key], 0.0)
                self.assertLessEqual(first_iteration[key], 1.0)

            self.assertTrue(world["market_inventory_histories"])
            first_inventory = next(
                history
                for history in world["market_inventory_histories"]
                if history["id"] == first_clearing["market_inventory_history_id"]
            )
            self.assertIn("initial_inventory_index", first_inventory)
            self.assertIn("target_inventory_index", first_inventory)
            self.assertIn("final_inventory_index", first_inventory)
            self.assertIn("inventory_gap_index", first_inventory)
            self.assertIn("learning_rate_index", first_inventory)
            self.assertIn("mean_inventory_pressure_index", first_inventory)
            self.assertIn("mean_price_expectation_index", first_inventory)
            self.assertIn("mean_supply_response_index", first_inventory)
            self.assertIn("mean_demand_adjustment_index", first_inventory)
            self.assertIn("high_inventory_stress", first_inventory)
            self.assertIn("steps", first_inventory)
            self.assertEqual(first_inventory["market_clearing_record_id"], first_clearing["id"])
            self.assertEqual(first_inventory["market_exchange_id"], first_clearing["market_exchange_id"])
            self.assertEqual(first_inventory["route_id"], first_clearing["route_id"])
            self.assertEqual(first_inventory["step_count"], len(first_inventory["steps"]))
            self.assertEqual(first_inventory["step_count"], first_clearing["price_iteration_count"])
            self.assertAlmostEqual(
                first_inventory["inventory_gap_index"],
                abs(first_inventory["final_inventory_index"] - first_inventory["target_inventory_index"]),
                delta=0.001,
            )
            self.assertIsInstance(first_inventory["high_inventory_stress"], bool)
            for key in (
                "initial_inventory_index",
                "target_inventory_index",
                "final_inventory_index",
                "inventory_gap_index",
                "learning_rate_index",
                "mean_inventory_pressure_index",
                "mean_price_expectation_index",
                "mean_supply_response_index",
                "mean_demand_adjustment_index",
            ):
                self.assertGreaterEqual(first_inventory[key], 0.0)
                self.assertLessEqual(first_inventory[key], 1.0)
            first_inventory_step = first_inventory["steps"][0]
            self.assertIn("price_iteration_id", first_inventory_step)
            self.assertIn("inventory_index", first_inventory_step)
            self.assertIn("target_inventory_index", first_inventory_step)
            self.assertIn("inventory_gap_index", first_inventory_step)
            self.assertIn("supply_response_index", first_inventory_step)
            self.assertIn("demand_adjustment_index", first_inventory_step)
            self.assertIn("learning_rate_index", first_inventory_step)
            self.assertIn("producer_expectation_index", first_inventory_step)
            self.assertIn("consumer_expectation_index", first_inventory_step)
            self.assertIn("rationing_memory_index", first_inventory_step)
            self.assertIn("clearance_memory_index", first_inventory_step)
            self.assertEqual(first_inventory_step["sequence_index"], 0)
            self.assertEqual(first_inventory_step["price_iteration_id"], first_clearing["price_iteration_ids"][0])
            self.assertAlmostEqual(
                first_inventory_step["inventory_gap_index"],
                abs(first_inventory_step["inventory_index"] - first_inventory_step["target_inventory_index"]),
                delta=0.001,
            )
            for key in (
                "price_index",
                "inventory_index",
                "target_inventory_index",
                "inventory_gap_index",
                "supply_response_index",
                "demand_adjustment_index",
                "learning_rate_index",
                "producer_expectation_index",
                "consumer_expectation_index",
                "rationing_memory_index",
                "clearance_memory_index",
            ):
                self.assertGreaterEqual(first_inventory_step[key], 0.0)
                self.assertLessEqual(first_inventory_step[key], 1.0)

        if world["campaign_movements"]:
            first_campaign = world["campaign_movements"][0]
            self.assertIn("conflict_id", first_campaign)
            self.assertIn("origin_region_id", first_campaign)
            self.assertIn("target_region_id", first_campaign)
            self.assertIn("origin_cell_id", first_campaign)
            self.assertIn("target_cell_id", first_campaign)
            self.assertIn("route_id", first_campaign)
            self.assertIn("border_id", first_campaign)
            self.assertIn("path_cell_ids", first_campaign)
            self.assertIn("path_segment_ids", first_campaign)
            self.assertIn("path_length_km", first_campaign)
            self.assertIn("path_terrain_cost_index", first_campaign)
            self.assertIn("path_supply_loss_index", first_campaign)
            self.assertIn("path_attrition_index", first_campaign)
            self.assertIn("campaign_front_history_id", first_campaign)
            self.assertIn("travel_time_days", first_campaign)
            self.assertIn("force_estimate", first_campaign)
            self.assertIn("supply_required_index", first_campaign)
            self.assertIn("attrition_risk_index", first_campaign)
            self.assertIn("operational_reach_index", first_campaign)
            self.assertIn("campaign_success_index", first_campaign)
            self.assertGreaterEqual(first_campaign["start_year_bp"], first_campaign["end_year_bp"])
            self.assertGreater(first_campaign["distance_km"], 0.0)
            self.assertGreater(first_campaign["path_length_km"], 0.0)
            self.assertAlmostEqual(
                first_campaign["distance_km"],
                first_campaign["path_length_km"],
                delta=max(0.001, first_campaign["path_length_km"] * 0.0001),
            )
            self.assertEqual(first_campaign["path_cell_count"], len(first_campaign["path_cell_ids"]))
            self.assertEqual(first_campaign["path_segment_count"], len(first_campaign["path_segment_ids"]))
            self.assertEqual(first_campaign["path_segment_count"], max(0, first_campaign["path_cell_count"] - 1))
            self.assertEqual(first_campaign["path_cell_ids"][0], first_campaign["origin_cell_id"])
            self.assertEqual(first_campaign["path_cell_ids"][-1], first_campaign["target_cell_id"])
            self.assertGreater(first_campaign["travel_time_days"], 0.0)
            self.assertGreaterEqual(first_campaign["force_estimate"], 0.0)
            for key in (
                "supply_required_index",
                "attrition_risk_index",
                "logistics_strain_index",
                "operational_reach_index",
                "campaign_success_index",
                "path_terrain_cost_index",
                "path_supply_loss_index",
                "path_attrition_index",
            ):
                self.assertGreaterEqual(first_campaign[key], 0.0)
                self.assertLessEqual(first_campaign[key], 1.0)
            self.assertTrue(world["campaign_path_segments"])
            first_segment = world["campaign_path_segments"][0]
            self.assertIn("campaign_movement_id", first_segment)
            self.assertIn("sequence_index", first_segment)
            self.assertIn("from_cell_id", first_segment)
            self.assertIn("to_cell_id", first_segment)
            self.assertIn("route_mode", first_segment)
            self.assertIn("distance_km", first_segment)
            self.assertIn("elapsed_days", first_segment)
            self.assertIn("terrain_cost_index", first_segment)
            self.assertIn("barrier_cost_index", first_segment)
            self.assertIn("supply_loss_index", first_segment)
            self.assertIn("attrition_index", first_segment)
            self.assertIn("elevation_gain_m", first_segment)
            self.assertIn("water_crossing", first_segment)
            self.assertEqual(first_segment["campaign_movement_id"], first_campaign["id"])
            self.assertEqual(first_segment["sequence_index"], 0)
            self.assertEqual(first_segment["from_cell_id"], first_campaign["path_cell_ids"][0])
            self.assertEqual(first_segment["to_cell_id"], first_campaign["path_cell_ids"][1])
            self.assertGreater(first_segment["distance_km"], 0.0)
            self.assertGreater(first_segment["elapsed_days"], 0.0)
            self.assertGreaterEqual(first_segment["elevation_gain_m"], 0.0)
            for key in ("terrain_cost_index", "barrier_cost_index", "supply_loss_index", "attrition_index"):
                self.assertGreaterEqual(first_segment[key], 0.0)
                self.assertLessEqual(first_segment[key], 1.0)

            self.assertTrue(world["campaign_front_histories"])
            first_front = world["campaign_front_histories"][0]
            self.assertIn("campaign_movement_id", first_front)
            self.assertIn("conflict_id", first_front)
            self.assertIn("attacking_force_initial", first_front)
            self.assertIn("defending_force_initial", first_front)
            self.assertIn("final_attacking_force_estimate", first_front)
            self.assertIn("final_defending_force_estimate", first_front)
            self.assertIn("path_cell_ids", first_front)
            self.assertIn("path_segment_ids", first_front)
            self.assertIn("step_count", first_front)
            self.assertIn("captured_cell_count", first_front)
            self.assertIn("final_occupied_cell_id", first_front)
            self.assertIn("max_supply_line_length_km", first_front)
            self.assertIn("mean_supply_integrity_index", first_front)
            self.assertIn("mean_occupation_control_index", first_front)
            self.assertIn("outcome_projection", first_front)
            self.assertIn("steps", first_front)
            self.assertEqual(first_campaign["campaign_front_history_id"], first_front["id"])
            self.assertEqual(first_front["campaign_movement_id"], first_campaign["id"])
            self.assertEqual(first_front["path_cell_ids"], first_campaign["path_cell_ids"])
            self.assertEqual(first_front["path_segment_ids"], first_campaign["path_segment_ids"])
            self.assertEqual(first_front["step_count"], len(first_front["steps"]))
            self.assertEqual(first_front["captured_cell_count"], len(first_front["path_cell_ids"]))
            self.assertEqual(first_front["final_occupied_cell_id"], first_front["path_cell_ids"][-1])
            self.assertGreaterEqual(first_front["attacking_force_initial"], first_front["final_attacking_force_estimate"])
            self.assertGreaterEqual(first_front["defending_force_initial"], first_front["final_defending_force_estimate"])
            self.assertGreaterEqual(first_front["max_supply_line_length_km"], 0.0)
            self.assertGreaterEqual(first_front["mean_supply_integrity_index"], 0.0)
            self.assertLessEqual(first_front["mean_supply_integrity_index"], 1.0)
            self.assertGreaterEqual(first_front["mean_occupation_control_index"], 0.0)
            self.assertLessEqual(first_front["mean_occupation_control_index"], 1.0)
            first_front_step = first_front["steps"][0]
            self.assertIn("sequence_index", first_front_step)
            self.assertIn("cell_id", first_front_step)
            self.assertIn("days_elapsed", first_front_step)
            self.assertIn("occupied_cell_ids", first_front_step)
            self.assertIn("occupied_cell_count", first_front_step)
            self.assertIn("front_line_cell_ids", first_front_step)
            self.assertIn("front_line_cell_count", first_front_step)
            self.assertIn("supply_line_length_km", first_front_step)
            self.assertIn("supply_integrity_index", first_front_step)
            self.assertIn("attacking_force_estimate", first_front_step)
            self.assertIn("defending_force_estimate", first_front_step)
            self.assertIn("attrition_loss_population", first_front_step)
            self.assertIn("local_attrition_index", first_front_step)
            self.assertIn("occupation_control_index", first_front_step)
            self.assertIn("front_width_index", first_front_step)
            self.assertIn("contested", first_front_step)
            self.assertEqual(first_front_step["sequence_index"], 0)
            self.assertEqual(first_front_step["cell_id"], first_front["path_cell_ids"][0])
            self.assertEqual(first_front_step["occupied_cell_count"], len(first_front_step["occupied_cell_ids"]))
            self.assertEqual(first_front_step["front_line_cell_count"], len(first_front_step["front_line_cell_ids"]))
            self.assertGreaterEqual(first_front_step["days_elapsed"], 0.0)
            self.assertGreaterEqual(first_front_step["supply_line_length_km"], 0.0)
            self.assertGreaterEqual(first_front_step["attrition_loss_population"], 0.0)
            for key in ("supply_integrity_index", "local_attrition_index", "occupation_control_index", "front_width_index"):
                self.assertGreaterEqual(first_front_step[key], 0.0)
                self.assertLessEqual(first_front_step[key], 1.0)

            self.assertTrue(world["tactical_engagements"])
            first_engagement = world["tactical_engagements"][0]
            self.assertIn("conflict_id", first_engagement)
            self.assertIn("campaign_movement_id", first_engagement)
            self.assertIn("campaign_front_history_id", first_engagement)
            self.assertIn("region_a", first_engagement)
            self.assertIn("region_b", first_engagement)
            self.assertIn("battle_cell_ids", first_engagement)
            self.assertIn("step_count", first_engagement)
            self.assertIn("steps", first_engagement)
            self.assertIn("tactical_outcome", first_engagement)
            self.assertIn("max_front_pressure_index", first_engagement)
            self.assertIn("mean_counter_maneuver_index", first_engagement)
            self.assertIn("mean_supply_contest_index", first_engagement)
            self.assertIn("total_attrition_loss_population", first_engagement)
            self.assertEqual(first_engagement["campaign_movement_id"], first_campaign["id"])
            self.assertEqual(first_engagement["campaign_front_history_id"], first_front["id"])
            self.assertEqual(first_engagement["battle_cell_ids"], first_campaign["path_cell_ids"])
            self.assertEqual(first_engagement["battle_cell_count"], len(first_engagement["battle_cell_ids"]))
            self.assertEqual(first_engagement["step_count"], len(first_engagement["steps"]))
            self.assertGreaterEqual(first_engagement["initial_region_a_force"], first_engagement["final_region_a_force"])
            self.assertGreaterEqual(first_engagement["initial_region_b_force"], first_engagement["final_region_b_force"])
            self.assertGreaterEqual(first_engagement["total_attrition_loss_population"], 0.0)
            for key in ("max_front_pressure_index", "mean_counter_maneuver_index", "mean_supply_contest_index"):
                self.assertGreaterEqual(first_engagement[key], 0.0)
                self.assertLessEqual(first_engagement[key], 1.0)
            first_tactical_step = first_engagement["steps"][0]
            self.assertIn("region_a_force_estimate", first_tactical_step)
            self.assertIn("region_b_force_estimate", first_tactical_step)
            self.assertIn("region_a_supply_integrity_index", first_tactical_step)
            self.assertIn("region_b_supply_integrity_index", first_tactical_step)
            self.assertIn("front_pressure_index", first_tactical_step)
            self.assertIn("counter_maneuver_index", first_tactical_step)
            self.assertIn("supply_contest_index", first_tactical_step)
            self.assertIn("encirclement_risk_index", first_tactical_step)
            self.assertIn("withdrawal_pressure_index", first_tactical_step)
            self.assertIn("control_region_id", first_tactical_step)
            self.assertIn("control_balance_index", first_tactical_step)
            self.assertEqual(first_tactical_step["sequence_index"], 0)
            self.assertEqual(first_tactical_step["cell_id"], first_engagement["battle_cell_ids"][0])
            self.assertIn(first_tactical_step["control_region_id"], {first_engagement["region_a"], first_engagement["region_b"]})
            self.assertGreaterEqual(first_tactical_step["region_a_force_estimate"], 0.0)
            self.assertGreaterEqual(first_tactical_step["region_b_force_estimate"], 0.0)
            self.assertGreaterEqual(first_tactical_step["attrition_loss_population"], 0.0)
            for key in (
                "region_a_supply_integrity_index",
                "region_b_supply_integrity_index",
                "front_pressure_index",
                "counter_maneuver_index",
                "supply_contest_index",
                "encirclement_risk_index",
                "withdrawal_pressure_index",
                "control_balance_index",
            ):
                self.assertGreaterEqual(first_tactical_step[key], 0.0)
                self.assertLessEqual(first_tactical_step[key], 1.0)

            self.assertTrue(world["strategic_campaign_plans"])
            first_plan = world["strategic_campaign_plans"][0]
            self.assertIn("conflict_id", first_plan)
            self.assertIn("campaign_movement_id", first_plan)
            self.assertIn("campaign_front_history_id", first_plan)
            self.assertIn("tactical_engagement_id", first_plan)
            self.assertIn("primary_region_id", first_plan)
            self.assertIn("counter_region_id", first_plan)
            self.assertIn("primary_axis_cell_ids", first_plan)
            self.assertIn("counter_axis_cell_ids", first_plan)
            self.assertIn("decisive_cell_ids", first_plan)
            self.assertIn("decision_points", first_plan)
            self.assertEqual(first_plan["campaign_movement_id"], first_campaign["id"])
            self.assertEqual(first_plan["campaign_front_history_id"], first_front["id"])
            self.assertEqual(first_plan["tactical_engagement_id"], first_engagement["id"])
            self.assertEqual(first_plan["primary_axis_cell_ids"], first_campaign["path_cell_ids"])
            self.assertEqual(first_plan["counter_axis_cell_ids"], list(reversed(first_campaign["path_cell_ids"])))
            self.assertEqual(first_plan["primary_axis_cell_count"], len(first_plan["primary_axis_cell_ids"]))
            self.assertEqual(first_plan["counter_axis_cell_count"], len(first_plan["counter_axis_cell_ids"]))
            self.assertEqual(first_plan["decisive_cell_count"], len(first_plan["decisive_cell_ids"]))
            self.assertEqual(first_plan["decision_point_count"], len(first_plan["decision_points"]))
            self.assertGreaterEqual(first_plan["primary_force_allocation_population"], 0.0)
            self.assertGreaterEqual(first_plan["counter_force_allocation_population"], 0.0)
            self.assertGreaterEqual(first_plan["reserve_force_population"], 0.0)
            self.assertGreaterEqual(first_plan["expected_campaign_duration_days"], 0.0)
            self.assertGreaterEqual(first_plan["counter_mobilization_days"], 0.0)
            self.assertTrue(first_plan["strategic_posture"])
            self.assertIsInstance(first_plan["independent_counter_campaign_planned"], bool)
            for key in (
                "reserve_fraction",
                "primary_logistics_score",
                "counter_logistics_score",
                "counter_campaign_viability_index",
                "strategic_initiative_index",
                "escalation_risk_index",
                "operational_complexity_index",
                "plan_confidence_index",
            ):
                self.assertGreaterEqual(first_plan[key], 0.0)
                self.assertLessEqual(first_plan[key], 1.0)
            first_decision = first_plan["decision_points"][0]
            self.assertIn("path_index", first_decision)
            self.assertIn("plan_phase", first_decision)
            self.assertIn("trigger_pressure_index", first_decision)
            self.assertIn("counter_maneuver_priority_index", first_decision)
            self.assertIn("supply_risk_index", first_decision)
            self.assertEqual(first_decision["sequence_index"], 0)
            self.assertEqual(first_decision["cell_id"], first_plan["primary_axis_cell_ids"][first_decision["path_index"]])
            self.assertTrue(first_decision["plan_phase"])
            for key in ("trigger_pressure_index", "counter_maneuver_priority_index", "supply_risk_index"):
                self.assertGreaterEqual(first_decision[key], 0.0)
                self.assertLessEqual(first_decision[key], 1.0)
    def test_society_economy_models_declare_their_documented_identities(self) -> None:
        """Every society/economy replay names its documented model and emits records.

        The record-by-record tamper coverage for these replays lives in the
        module that owns each validator -- ``test_civilization_geography_validation``,
        ``test_territorial_geography_validation``, ``test_history_economy_validation``,
        ``test_demographic_agents_validation``, ``test_dynasty_genealogy_validation``,
        ``test_logistics_exchange_validation``, ``test_logistics_history`` and
        ``test_market_clearing_validation``. Those call the validators directly, so
        they can name the field that diverged instead of collapsing to one CLI
        verdict line, and they assert the undone tamper replays clean again. This
        test only pins the model identities and the presence of the record families
        those modules assume.
        """

        world = worlds.cached_world_readonly("mid_512")

        for model_key, model_type in (
            (
                "population_region_model",
                "causal_area_weighted_capacity_occupancy_population_regions_v1",
            ),
            (
                "conflict_model",
                "causal_border_pair_pressure_trade_conflict_selection_v1",
            ),
            (
                "dynasty_model",
                "causal_foundation_continuity_pressure_dynasty_lineages_v1",
            ),
            (
                "territorial_snapshot_model",
                "causal_era_scaled_spherical_region_territorial_snapshots_v1",
            ),
            (
                "population_history_model",
                "causal_era_snapshot_logistic_migration_conflict_population_history_v1",
            ),
            (
                "economy_history_model",
                "causal_population_trade_conflict_treasury_economy_history_v1",
            ),
            (
                "demographic_agent_model",
                "causal_population_economy_logistics_household_firm_demographic_history_v1",
            ),
            (
                "individual_life_event_model",
                "causal_household_firm_era_sampled_individual_life_event_graph_v1",
            ),
            (
                "ruler_genealogy_model",
                "causal_dynasty_economy_conflict_named_ruler_alliance_cadet_genealogy_v1",
            ),
            (
                "logistics_exchange_model",
                "causal_region_route_trade_economy_logistics_exchange_v1",
            ),
            (
                "campaign_operations_model",
                "causal_conflict_cell_path_front_tactical_strategic_campaign_operations_v1",
            ),
            (
                "market_clearing_model",
                "causal_route_capacity_agent_orders_price_iteration_inventory_learning_market_clearing_v1",
            ),
        ):
            with self.subTest(model=model_key):
                self.assertEqual(world[model_key]["model_type"], model_type)

        for family in (
            "population_regions",
            "conflicts",
            "dynasties",
            "population_histories",
            "economy_histories",
            "household_cohorts",
            "firm_agents",
            "demographic_agent_histories",
            "individual_agents",
            "individual_life_events",
            "rulers",
            "marriage_alliances",
            "cadet_branches",
            "logistics_networks",
            "market_exchanges",
            "campaign_movements",
            "campaign_path_segments",
            "campaign_front_histories",
            "tactical_engagements",
            "strategic_campaign_plans",
            "route_capacity_constraints",
            "market_clearing_records",
            "market_agent_orders",
            "market_price_iterations",
            "market_inventory_histories",
        ):
            with self.subTest(family=family):
                self.assertTrue(world[family], family)

        self.assertEqual(len(world["territorial_snapshots"]), 4)
        self.assertTrue(world["territorial_snapshots"][0]["regions"])

    def test_validate_reports_every_society_economy_replay_verdict(self) -> None:
        """``validate`` reaches and reports all eight society/economy replays.

        Wiring is the one claim the dedicated validator modules cannot make: they
        call the validators directly and never go through the public command. One
        tamper per verdict, applied to a single payload and reported by a single
        pass, is all that claim needs -- repeating the tamper tables through the
        CLI would re-prove, far more slowly and far less precisely, what those
        modules already prove field by field.
        """

        world = worlds.cached_world("mid_512")
        runner = CliRunner()

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"

            def validate_current() -> Result:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            control = validate_current()
            assert_no_cli_crash(self, control, command="validate")
            self.assertEqual(control.exit_code, 0, control.output)

            world["population_regions"][0]["estimated_population"] *= 1.01
            world["territorial_snapshots"][0]["regions"][0]["boundary_cell_ids"][0] += 1
            world["population_histories"][0]["steps"][0]["end_population"] += 1.0
            world["household_cohorts"][0]["vulnerability_index"] += 0.01
            world["rulers"][0]["legitimacy_index"] += 0.01
            world["logistics_networks"][0]["transport_efficiency_index"] += 0.01
            world["campaign_path_segments"][0]["attrition_index"] += 0.01
            world["route_capacity_constraints"][0]["capacity_volume_index"] += 0.01

            result = validate_current()

        assert_no_cli_crash(self, result, command="validate")
        self.assertEqual(result.exit_code, 1, result.output)
        for message in (
            "population, conflict, or dynasty model causal replay invalid",
            "territorial snapshot model or causal replay invalid",
            "population or economy history model causal replay invalid",
            "demographic agent or individual life-event causal replay invalid",
            "ruler genealogy model or causal replay invalid",
            "logistics exchange model or causal replay invalid",
            "campaign operations model or causal replay invalid",
            "market clearing model or causal replay invalid",
        ):
            with self.subTest(message=message):
                self.assertIn(message, result.output)
