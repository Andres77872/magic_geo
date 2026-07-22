"""Public ``validate`` CLI violations for history, economy, and graphs.

The ``validate`` command accumulates every complaint into one list and flushes it
through a single gate at the end of the command, emitting one ``FAIL <message>``
line per complaint and exiting 1.  A healthy generated world therefore walks the
passing path through every check, and the reporting branches only run when a
record or a summary counter is deliberately broken.

Each case here takes the smallest canonical world that carries the record family
under test, breaks exactly one field, and pins the exact message the command is
supposed to emit.  Checks that live in the same gate and read independent fields
are broken together in one invocation; checks reached through a loop that stops
at its first offending record get one invocation each, because a second tamper
in the same loop would never be evaluated.

``small_smoke`` (256 cells) is the cheapest canonical world that actually
contains conflicts, campaign operations, borders and marriage alliances -- all of
which are empty at 128 cells -- so the whole file shares it.

Every case runs through :meth:`report_for`, which refuses a tamper that leaves the
world untouched and refuses an exit code that came from an exception rather than
from the command's own gate.
"""

from __future__ import annotations

import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Iterable
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.io import write_json

from support import worlds

from support.cli import assert_no_cli_crash
import pytest

# Exhaustive branch coverage of ``validate``: every case invokes the full CLI
# over a generated world. Deselect locally with -m "not slow".
pytestmark = pytest.mark.slow

#: The cheapest canonical world holding every record family exercised here.
WORLD_KEY = "small_smoke"

Tamper = Callable[[dict[str, Any]], Any]


def _flip(record: dict[str, Any], key: str) -> None:
    """Move a unit-interval field far enough to break a cross-record equality."""
    record[key] = 0.0 if float(record.get(key, 0.0)) > 0.5 else 1.0


def _shift(record: dict[str, Any], key: str) -> None:
    """Nudge a unit-interval field while keeping it inside ``[0, 1]``."""
    value = float(record.get(key, 0.0))
    record[key] = value - 0.3 if value > 0.5 else value + 0.3


def _set(family: str, key: str, value: Any) -> Tamper:
    """Overwrite ``key`` on the first record of ``family``."""

    def tamper(world: dict[str, Any]) -> None:
        world[family][0][key] = value

    return tamper


def _drop(family: str, key: str) -> Tamper:
    """Remove ``key`` from the first record of ``family``."""

    def tamper(world: dict[str, Any]) -> None:
        world[family][0].pop(key, None)

    return tamper


def _replace_ref(family: str, key: str) -> Tamper:
    """Point the first entry of a reference list at an id that does not exist.

    The list length is preserved so the accompanying ``*_count`` field still
    matches and the dangling-reference branch is the one that fires.
    """

    def tamper(world: dict[str, Any]) -> None:
        world[family][0][key][0] = 999999

    return tamper


def _set_step(family: str, key: str, value: Any) -> Tamper:
    """Overwrite ``key`` on the first step of the first record of ``family``."""

    def tamper(world: dict[str, Any]) -> None:
        world[family][0]["steps"][0][key] = value

    return tamper


#: ``int(summary[key])`` counters compared against a recomputed record count.
SUMMARY_COUNTS: tuple[tuple[str, str], ...] = (
    ("economy_history_count", "economy_history_count does not match economy_histories length"),
    ("economy_history_step_count", "economy_history_step_count does not match economy history steps"),
    (
        "high_military_burden_economy_step_count",
        "high_military_burden_economy_step_count does not match economy histories",
    ),
    ("logistics_network_count", "logistics_network_count does not match logistics_networks length"),
    ("market_exchange_count", "market_exchange_count does not match market_exchanges length"),
    (
        "route_capacity_constraint_count",
        "route_capacity_constraint_count does not match route_capacity_constraints length",
    ),
    ("market_clearing_record_count", "market_clearing_record_count does not match market_clearing_records length"),
    ("market_agent_order_count", "market_agent_order_count does not match market_agent_orders length"),
    ("market_price_iteration_count", "market_price_iteration_count does not match market_price_iterations length"),
    (
        "market_inventory_history_count",
        "market_inventory_history_count does not match market_inventory_histories length",
    ),
    ("campaign_movement_count", "campaign_movement_count does not match campaign_movements length"),
    ("campaign_path_segment_count", "campaign_path_segment_count does not match campaign_path_segments length"),
    ("campaign_front_history_count", "campaign_front_history_count does not match campaign_front_histories length"),
    ("tactical_engagement_count", "tactical_engagement_count does not match tactical_engagements length"),
    ("strategic_campaign_plan_count", "strategic_campaign_plan_count does not match strategic_campaign_plans length"),
    ("logistics_route_link_count", "logistics_route_link_count does not match logistics networks"),
    ("interregional_market_exchange_count", "interregional_market_exchange_count does not match market exchanges"),
    ("constrained_market_exchange_count", "constrained_market_exchange_count does not match market clearing records"),
    ("producer_market_order_count", "producer_market_order_count does not match market agent orders"),
    ("consumer_market_order_count", "consumer_market_order_count does not match market agent orders"),
    ("high_attrition_campaign_count", "high_attrition_campaign_count does not match campaign movements"),
    (
        "high_attrition_campaign_path_segment_count",
        "high_attrition_campaign_path_segment_count does not match campaign path segments",
    ),
    ("campaign_front_step_count", "campaign_front_step_count does not match campaign front histories"),
    ("tactical_engagement_step_count", "tactical_engagement_step_count does not match tactical engagements"),
    ("high_pressure_tactical_step_count", "high_pressure_tactical_step_count does not match tactical engagements"),
    ("strategic_decision_point_count", "strategic_decision_point_count does not match strategic campaign plans"),
    (
        "independent_counter_campaign_plan_count",
        "independent_counter_campaign_plan_count does not match strategic campaign plans",
    ),
    (
        "high_escalation_strategic_plan_count",
        "high_escalation_strategic_plan_count does not match strategic campaign plans",
    ),
    ("market_inventory_step_count", "market_inventory_step_count does not match market inventory histories"),
    (
        "high_inventory_stress_market_count",
        "high_inventory_stress_market_count does not match market inventory histories",
    ),
    ("household_cohort_count", "household_cohort_count does not match household_cohorts length"),
    ("firm_agent_count", "firm_agent_count does not match firm_agents length"),
    (
        "demographic_agent_history_count",
        "demographic_agent_history_count does not match demographic_agent_histories length",
    ),
    ("individual_agent_count", "individual_agent_count does not match individual_agents length"),
    ("individual_life_event_count", "individual_life_event_count does not match individual_life_events length"),
    ("demographic_agent_step_count", "demographic_agent_step_count does not match demographic agent histories"),
    ("high_vulnerability_household_count", "high_vulnerability_household_count does not match household cohorts"),
    ("individual_birth_event_count", "individual_birth_event_count does not match individual life events"),
    ("individual_death_event_count", "individual_death_event_count does not match individual life events"),
    ("individual_marriage_event_count", "individual_marriage_event_count does not match individual life events"),
    ("property_transfer_event_count", "property_transfer_event_count does not match individual life events"),
    ("dynasty_count", "dynasty_count does not match dynasties length"),
    ("dynastic_lineage_count", "dynastic_lineage_count does not match dynasty parent links"),
    ("dynasty_root_count", "dynasty_root_count does not match dynasty roots"),
    ("dynasty_successor_link_count", "dynasty_successor_link_count does not match dynasty successors"),
    ("max_dynasty_lineage_depth", "max_dynasty_lineage_depth does not match dynasties"),
    ("ruler_count", "ruler_count does not match rulers length"),
    ("named_ruler_dynasty_count", "named_ruler_dynasty_count does not match dynasties"),
    ("ruler_marriage_alliance_count", "ruler_marriage_alliance_count does not match marriage_alliances length"),
    ("cadet_branch_count", "cadet_branch_count does not match cadet_branches length"),
    ("married_ruler_count", "married_ruler_count does not match ruler spouse links"),
    ("max_ruler_lineage_depth", "max_ruler_lineage_depth does not match rulers"),
    ("territorial_snapshot_count", "territorial_snapshot_count does not match territorial_snapshots length"),
    ("snapshot_region_record_count", "snapshot_region_record_count does not match territorial snapshots"),
    ("snapshot_polygon_region_count", "snapshot_polygon_region_count does not match territorial snapshot regions"),
    (
        "territorial_cell_edge_boundary_segment_count",
        "territorial_cell_edge_boundary_segment_count does not match records",
    ),
    (
        "snapshot_region_with_cell_edge_boundary_count",
        "snapshot_region_with_cell_edge_boundary_count does not match snapshots",
    ),
    ("sacred_area_count", "sacred_area_count does not match sacred_areas length"),
    ("ruin_count", "ruin_count does not match ruins length"),
    ("border_segment_count", "border_segment_count does not match borders length"),
    ("plate_graph_node_count", "plate_graph_node_count does not match source records"),
    ("plate_graph_edge_count", "plate_graph_edge_count does not match plate adjacency pairs"),
    ("plate_graph_boundary_cell_edge_count", "plate_graph_boundary_cell_edge_count does not match cell adjacency edges"),
    ("plate_graph_component_count", "plate_graph_component_count does not match graph connectivity"),
    ("river_graph_edge_count", "river_graph_edge_count does not match river flow links"),
    ("river_graph_component_count", "river_graph_component_count does not match graph connectivity"),
    ("watershed_graph_edge_count", "watershed_graph_edge_count does not match watershed adjacency pairs"),
    (
        "watershed_graph_boundary_edge_count",
        "watershed_graph_boundary_edge_count does not match cell adjacency edges",
    ),
    ("watershed_graph_component_count", "watershed_graph_component_count does not match graph connectivity"),
    ("trade_route_graph_edge_count", "trade_route_graph_edge_count does not match routes"),
    (
        "interregional_trade_route_graph_edge_count",
        "interregional_trade_route_graph_edge_count does not match graph edges",
    ),
    ("trade_route_graph_component_count", "trade_route_graph_component_count does not match graph connectivity"),
    ("political_region_graph_edge_count", "political_region_graph_edge_count does not match graph edges"),
    (
        "political_region_graph_border_segment_count",
        "political_region_graph_border_segment_count does not match borders",
    ),
    ("political_region_graph_trade_edge_count", "political_region_graph_trade_edge_count does not match graph edges"),
    ("political_region_graph_component_count", "political_region_graph_component_count does not match graph connectivity"),
    ("geology_realism_check_count", "geology_realism_check_count does not match geology_realism_checks length"),
    ("geology_realism_pass_count", "geology_realism_pass_count does not match geology realism checks"),
    ("calibration_check_count", "calibration_check_count does not match calibration_checks length"),
    ("calibration_pass_count", "calibration_pass_count does not match calibration checks"),
)

#: ``float(summary[key])`` aggregates compared against a recomputed total or mean.
SUMMARY_AGGREGATES: tuple[tuple[str, str], ...] = (
    ("historical_final_gross_output_index", "historical_final_gross_output_index does not match economy histories"),
    ("historical_final_treasury_index", "historical_final_treasury_index does not match economy histories"),
    ("historical_total_tax_revenue_index", "historical_total_tax_revenue_index does not match economy histories"),
    ("historical_total_trade_revenue_index", "historical_total_trade_revenue_index does not match economy histories"),
    ("historical_total_war_cost_index", "historical_total_war_cost_index does not match economy histories"),
    (
        "historical_peak_army_capacity_population",
        "historical_peak_army_capacity_population does not match economy histories",
    ),
    ("mean_historical_prosperity_index", "mean_historical_prosperity_index does not match economy histories"),
    (
        "mean_historical_trade_dependency_index",
        "mean_historical_trade_dependency_index does not match economy histories",
    ),
    ("mean_historical_military_burden_index", "mean_historical_military_burden_index does not match economy histories"),
    ("total_market_exchange_volume_index", "total_market_exchange_volume_index does not match market exchanges"),
    (
        "total_market_requested_volume_index",
        "total_market_requested_volume_index does not match route capacity constraints",
    ),
    ("total_market_cleared_volume_index", "total_market_cleared_volume_index does not match route capacity constraints"),
    ("total_market_unmet_demand_index", "total_market_unmet_demand_index does not match route capacity constraints"),
    (
        "total_endogenous_market_supply_index",
        "total_endogenous_market_supply_index does not match market clearing records",
    ),
    (
        "total_endogenous_market_demand_index",
        "total_endogenous_market_demand_index does not match market clearing records",
    ),
    ("total_campaign_mobilized_population", "total_campaign_mobilized_population does not match campaign movements"),
    ("total_campaign_path_length_km", "total_campaign_path_length_km does not match campaign movements"),
    (
        "total_campaign_front_attrition_loss_population",
        "total_campaign_front_attrition_loss_population does not match campaign front histories",
    ),
    (
        "tactical_total_attrition_loss_population",
        "tactical_total_attrition_loss_population does not match tactical engagements",
    ),
    (
        "mean_logistics_transport_efficiency_index",
        "mean_logistics_transport_efficiency_index does not match logistics history",
    ),
    ("total_household_cohort_population", "total_household_cohort_population does not match household cohorts"),
    ("total_firm_employment_capacity", "total_firm_employment_capacity does not match firm agents"),
    (
        "total_property_transfer_value_index",
        "total_property_transfer_value_index does not match individual life events",
    ),
    ("mean_household_resilience_index", "mean_household_resilience_index does not match demographic agents"),
    ("mean_ruler_legitimacy_index", "mean_ruler_legitimacy_index does not match rulers"),
    ("mean_succession_crisis_risk", "mean_succession_crisis_risk does not match rulers"),
    ("mean_marriage_alliance_strength", "mean_marriage_alliance_strength does not match marriage alliances"),
    ("mean_cadet_branch_claim_strength", "mean_cadet_branch_claim_strength does not match cadet branches"),
    ("territorial_cell_edge_boundary_length_km", "territorial_cell_edge_boundary_length_km does not match records"),
    (
        "mean_snapshot_cell_edge_boundary_segment_count",
        "mean_snapshot_cell_edge_boundary_segment_count does not match snapshots",
    ),
    (
        "mean_snapshot_cell_edge_boundary_length_km",
        "mean_snapshot_cell_edge_boundary_length_km does not match snapshots",
    ),
    ("mean_snapshot_cell_edge_boundary_quality", "mean_snapshot_cell_edge_boundary_quality does not match snapshots"),
    ("river_graph_total_channel_length_km", "river_graph_total_channel_length_km does not match graph edges"),
    ("watershed_graph_total_boundary_length_km", "watershed_graph_total_boundary_length_km does not match graph edges"),
    ("trade_route_graph_total_volume_index", "trade_route_graph_total_volume_index does not match graph edges"),
    (
        "political_region_graph_total_border_length_km",
        "political_region_graph_total_border_length_km does not match graph edges",
    ),
    ("geology_realism_pass_fraction", "geology_realism_pass_fraction does not match checks"),
    ("mean_geology_realism_score", "mean_geology_realism_score does not match checks"),
    ("mountain_convergent_alignment", "mountain_convergent_alignment does not match geology realism check"),
)

#: Summary metrics that carry an explicit domain range independent of the records.
SUMMARY_RANGES: tuple[tuple[str, float, str], ...] = (
    ("mean_war_duration_years", -1.0, "mean_war_duration_years out of range"),
    ("total_mobilized_population", -1.0, "total_mobilized_population out of range"),
    ("mean_conflict_logistics_strain_index", 5.0, "mean_conflict_logistics_strain_index out of range"),
    ("mean_dynastic_continuity_index", 5.0, "mean_dynastic_continuity_index out of range"),
    ("mean_snapshot_geometry_quality", 5.0, "mean_snapshot_geometry_quality out of range"),
    ("calibration_pass_fraction", 5.0, "calibration_pass_fraction out of range"),
    ("mean_calibration_score", 5.0, "mean_calibration_score out of range"),
)

#: One representative member of each required summary-metric group.
SUMMARY_METRIC_GROUPS: tuple[tuple[str, str], ...] = (
    ("mean_war_duration_years", "conflict war summary metrics missing"),
    ("historical_final_gross_output_index", "economy history summary metrics missing"),
    ("logistics_route_link_count", "logistics history summary metrics missing"),
    ("total_household_cohort_population", "demographic agent summary metrics missing"),
    ("mean_dynastic_continuity_index", "dynastic continuity summary metric missing"),
    ("mean_snapshot_compactness_index", "territorial snapshot geometry summary metrics missing"),
    ("mean_snapshot_cell_edge_boundary_quality", "territorial cell-edge boundary summary metrics missing"),
    ("hypsometry_bimodality_index", "geology realism summary metrics missing"),
    ("calibration_pass_fraction", "calibration summary metrics missing"),
)

#: ``(family, field, message)`` for the record-schema guards, which only inspect
#: the first record of each family.
RECORD_SCHEMA_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("conflicts", "cause", "conflict fields missing"),
    ("logistics_networks", "chokepoint_exposure_index", "logistics network fields missing"),
    ("market_exchanges", "food_security_link_index", "market exchange fields missing"),
    ("route_capacity_constraints", "spoilage_loss_index", "route capacity constraint fields missing"),
    ("market_clearing_records", "consumer_welfare_index", "market clearing record fields missing"),
    ("market_agent_orders", "price_acceptance_index", "market agent order fields missing"),
    ("market_price_iterations", "excess_demand_index", "market price iteration fields missing"),
    ("market_inventory_histories", "target_inventory_index", "market inventory history fields missing"),
    ("campaign_movements", "contested_cell_id", "campaign movement fields missing"),
    ("campaign_path_segments", "water_crossing", "campaign path segment fields missing"),
    ("campaign_front_histories", "captured_cell_count", "campaign front history fields missing"),
    ("tactical_engagements", "contested_cell_id", "tactical engagement fields missing"),
    ("strategic_campaign_plans", "era_id", "strategic campaign plan fields missing"),
    ("household_cohorts", "fertility_rate_per_year", "household cohort fields missing"),
    ("firm_agents", "tax_contribution_index", "firm agent fields missing"),
    ("demographic_agent_histories", "mean_labor_participation_index", "demographic agent history fields missing"),
    ("individual_agents", "mobility_index", "individual agent fields missing"),
    ("individual_life_events", "demographic_pressure_index", "individual life event fields missing"),
    ("dynasties", "collapse_reason", "dynasty fields missing"),
    ("rulers", "military_prestige_index", "ruler fields missing"),
    ("marriage_alliances", "trade_pact_index", "marriage alliance fields missing"),
    ("cadet_branches", "cadet_legitimacy_index", "cadet branch fields missing"),
    ("geology_realism_checks", "evidence", "geology realism check fields missing"),
    ("calibration_checks", "score", "calibration check fields missing"),
)

def _economy_treasury_discontinuity(world: dict[str, Any]) -> None:
    """Break the treasury carry-over without disturbing the step's own balance.

    Both ends of the step move by the same amount, so the balance residual still
    reconciles and the check that fires is the one comparing the opening
    treasury with the previous step's closing treasury.
    """
    step = world["economy_histories"][0]["steps"][1]
    step["treasury_start_index"] = float(step["treasury_start_index"]) + 1000.0
    step["treasury_end_index"] = float(step["treasury_end_index"]) + 1000.0


CONFLICT_AND_ECONOMY_TAMPERS: tuple[tuple[str, Tamper, str], ...] = (
    ("negative war duration", _set("conflicts", "war_duration_years", -1.0), "conflict war diagnostics invalid"),
    ("casualty rate above one", _set("conflicts", "casualty_rate", 5.0), "conflict war diagnostics invalid"),
    (
        "one economy history short of the population histories",
        lambda world: world["economy_histories"].pop(),
        "economy_histories length does not match population_histories length",
    ),
    (
        "history political region dangling",
        _set("economy_histories", "region_id", 999999),
        "economy history fields invalid",
    ),
    ("history step era dangling", _set_step("economy_histories", "era_id", 999999), "economy history fields invalid"),
    ("history treasury carry-over broken", _economy_treasury_discontinuity, "economy history fields invalid"),
    (
        "negative step tax revenue",
        _set_step("economy_histories", "tax_revenue_index", -1.0),
        "economy history fields invalid",
    ),
    (
        "peak treasury above steps",
        _set("economy_histories", "peak_treasury_index", 1.0e9),
        "economy history fields invalid",
    ),
)

def _rehome_price_iteration(world: dict[str, Any]) -> None:
    """Attach the first price iteration to an exchange its clearing record disowns."""
    iteration = world["market_price_iterations"][0]
    current = int(iteration["market_exchange_id"])
    for market in world["market_exchanges"]:
        if int(market["id"]) != current:
            iteration["market_exchange_id"] = int(market["id"])
            return


LOGISTICS_RECORD_TAMPERS: tuple[tuple[str, Tamper], ...] = (
    ("network total_route_cost negative", _set("logistics_networks", "total_route_cost", -1.0)),
    ("network supply_capacity_index above one", _set("logistics_networks", "supply_capacity_index", 5.0)),
    ("network route reference dangling", _replace_ref("logistics_networks", "route_ids")),
    ("network trade flow reference dangling", _replace_ref("logistics_networks", "trade_flow_ids")),
    ("network border reference dangling", _replace_ref("logistics_networks", "border_ids")),
    (
        "network route distance total drifts",
        lambda world: world["logistics_networks"][0].__setitem__(
            "total_route_distance_km", float(world["logistics_networks"][0]["total_route_distance_km"]) * 2.0 + 1000.0
        ),
    ),
    ("exchange distance negative", _set("market_exchanges", "distance_km", -1.0)),
    ("exchange friction above one", _set("market_exchanges", "friction", 5.0)),
    (
        "exchange cleared plus unmet drifts from volume",
        lambda world: world["market_exchanges"][0].__setitem__(
            "cleared_volume_index", float(world["market_exchanges"][0]["cleared_volume_index"]) + 1.0
        ),
    ),
    ("constraint capacity negative", _set("route_capacity_constraints", "capacity_volume_index", -1.0)),
    ("constraint congestion above one", _set("route_capacity_constraints", "congestion_index", 5.0)),
    ("constraint exchange reference dangling", _replace_ref("route_capacity_constraints", "market_exchange_ids")),
    (
        "constraint requested volume drifts",
        lambda world: world["route_capacity_constraints"][0].__setitem__(
            "requested_volume_index", float(world["route_capacity_constraints"][0]["requested_volume_index"]) + 100.0
        ),
    ),
    ("clearing endogenous supply negative", _set("market_clearing_records", "endogenous_supply_index", -1.0)),
    ("clearing producer surplus above one", _set("market_clearing_records", "producer_surplus_index", 5.0)),
    (
        "clearing utilization disagrees with constraint",
        lambda world: _flip(world["market_clearing_records"][0], "route_utilization_index"),
    ),
    ("clearing order reference dangling", _replace_ref("market_clearing_records", "agent_order_ids")),
    ("clearing price iteration reference dangling", _replace_ref("market_clearing_records", "price_iteration_ids")),
    ("order agent_type unknown", _set("market_agent_orders", "agent_type", "bogus")),
    ("order good disagrees with clearing record", _set("market_agent_orders", "primary_good", "unobtainium")),
    ("order limit price above one", _set("market_agent_orders", "limit_price_index", 5.0)),
    ("price iteration index not positive", _set("market_price_iterations", "iteration_index", 0)),
    ("price iteration price above one", _set("market_price_iterations", "price_index", 5.0)),
    ("price iteration order reference dangling", _replace_ref("market_price_iterations", "order_ids")),
    ("inventory history good blank", _set("market_inventory_histories", "primary_good", "  ")),
    ("inventory history initial index above one", _set("market_inventory_histories", "initial_inventory_index", 5.0)),
    ("inventory step sequence out of order", _set_step("market_inventory_histories", "sequence_index", 99)),
    ("inventory step price above one", _set_step("market_inventory_histories", "price_index", 5.0)),
    (
        "inventory step target disagrees with history",
        lambda world: _shift(world["market_inventory_histories"][0]["steps"][0], "target_inventory_index"),
    ),
    (
        "inventory final index disagrees with last step",
        lambda world: _shift(world["market_inventory_histories"][0], "final_inventory_index"),
    ),
    (
        "two exchanges share one route",
        lambda world: world["market_exchanges"][0].__setitem__("route_id", world["market_exchanges"][1]["route_id"]),
    ),
    ("price iteration points at another exchange", _rehome_price_iteration),
)

def _scale_campaign_path(world: dict[str, Any]) -> None:
    """Double both length fields so they stay consistent with each other only.

    The per-segment distances no longer add up to the declared path length, which
    is a different branch from the distance/path-length cross-check.
    """
    campaign = world["campaign_movements"][0]
    campaign["distance_km"] = float(campaign["distance_km"]) * 2.0
    campaign["path_length_km"] = float(campaign["path_length_km"]) * 2.0


def _front_occupied_cell_dangling(world: dict[str, Any]) -> None:
    """Break an occupied cell that is not the step's own advancing front cell."""
    for history in world["campaign_front_histories"]:
        for step in history["steps"]:
            if len(step["occupied_cell_ids"]) > 1:
                step["occupied_cell_ids"][0] = 999999
                return


def _front_line_cell_dangling(world: dict[str, Any]) -> None:
    for history in world["campaign_front_histories"]:
        for step in history["steps"]:
            if step["front_line_cell_ids"]:
                step["front_line_cell_ids"][0] = 999999
                return


CAMPAIGN_RECORD_TAMPERS: tuple[tuple[str, Tamper], ...] = (
    ("campaign distance negative", _set("campaign_movements", "distance_km", -1.0)),
    ("campaign supply index above one", _set("campaign_movements", "supply_required_index", 5.0)),
    ("campaign path segment reference dangling", _replace_ref("campaign_movements", "path_segment_ids")),
    ("path segment distance negative", _set("campaign_path_segments", "distance_km", -1.0)),
    ("path segment terrain cost above one", _set("campaign_path_segments", "terrain_cost_index", 5.0)),
    ("front history route mode blank", _set("campaign_front_histories", "route_mode", "  ")),
    ("front step supply line negative", _set_step("campaign_front_histories", "supply_line_length_km", -1.0)),
    (
        "front mean supply integrity drifts",
        lambda world: _flip(world["campaign_front_histories"][0], "mean_supply_integrity_index"),
    ),
    ("tactical outcome blank", _set("tactical_engagements", "tactical_outcome", "  ")),
    ("tactical max pressure above one", _set("tactical_engagements", "max_front_pressure_index", 5.0)),
    ("tactical step attrition negative", _set_step("tactical_engagements", "attrition_loss_population", -1.0)),
    ("tactical step pressure above one", _set_step("tactical_engagements", "front_pressure_index", 5.0)),
    (
        "tactical mean counter maneuver drifts",
        lambda world: _flip(world["tactical_engagements"][0], "mean_counter_maneuver_index"),
    ),
    ("plan posture blank", _set("strategic_campaign_plans", "strategic_posture", "  ")),
    ("plan reserve fraction above one", _set("strategic_campaign_plans", "reserve_fraction", 5.0)),
    ("plan decisive cell dangling", _replace_ref("strategic_campaign_plans", "decisive_cell_ids")),
    (
        "plan decision phase blank",
        lambda world: world["strategic_campaign_plans"][0]["decision_points"][0].__setitem__("plan_phase", "  "),
    ),
    (
        "plan decision supply risk above one",
        lambda world: world["strategic_campaign_plans"][0]["decision_points"][0].__setitem__("supply_risk_index", 5.0),
    ),
    ("campaign path length disagrees with its segments", _scale_campaign_path),
    ("front step occupied cell dangling", _front_occupied_cell_dangling),
    ("front step front-line cell dangling", _front_line_cell_dangling),
)

def _rehome_life_event(world: dict[str, Any]) -> None:
    """Move an event to another real population region its person does not live in."""
    event = world["individual_life_events"][0]
    current = int(event["population_region_id"])
    for region in world["population_regions"]:
        if int(region["id"]) != current:
            event["population_region_id"] = int(region["id"])
            return


def _property_transfer_without_inheritance(world: dict[str, Any]) -> None:
    for event in world["individual_life_events"]:
        if event.get("event_type") == "property_transfer":
            event["inheritance_fraction"] = 0.0
            return


DEMOGRAPHIC_RECORD_TAMPERS: tuple[tuple[str, Tamper], ...] = (
    ("population region representative population negative", _set("population_regions", "representative_household_population", -1.0)),
    ("political region firm_agent_ids removed", _drop("political_regions", "firm_agent_ids")),
    ("political region firm count wrong", _set("political_regions", "firm_agent_count", 99)),
    ("cohort household count negative", _set("household_cohorts", "household_count", -1.0)),
    ("cohort income index above one", _set("household_cohorts", "income_index", 5.0)),
    ("firm output negative", _set("firm_agents", "output_index", -1.0)),
    ("firm wage index above one", _set("firm_agents", "wage_index", 5.0)),
    ("history final population negative", _set("demographic_agent_histories", "final_agent_population", -1.0)),
    ("history cohort membership emptied", _set("demographic_agent_histories", "household_cohort_ids", [])),
    ("history firm reference dangling", _set("demographic_agent_histories", "firm_agent_ids", [999999])),
    ("history step start population negative", _set_step("demographic_agent_histories", "start_population", -1.0)),
    ("history step migration index above one", _set_step("demographic_agent_histories", "migration_propensity_index", 5.0)),
    ("person role blank", _set("individual_agents", "role", "  ")),
    ("person spouse dangling", _set("individual_agents", "married_person_id", 999999)),
    ("person parent dangling", _set("individual_agents", "parent_person_ids", [999999])),
    ("person child dangling", _set("individual_agents", "child_person_ids", [999999])),
    (
        "person event dangling",
        lambda world: world["individual_agents"][0].update({"event_ids": [999999], "event_count": 1}),
    ),
    (
        "person event set disagrees with events",
        lambda world: world["individual_agents"][0].update({"event_ids": [], "event_count": 0}),
    ),
    ("life event type unknown", _set("individual_life_events", "event_type", "bogus")),
    ("life event population region disagrees with its person", _rehome_life_event),
    ("property transfer without inheritance", _property_transfer_without_inheritance),
)

def _dynasty_founder_is_not_a_root(world: dict[str, Any]) -> None:
    """Give the first dynasty a parent while leaving it as its own founder.

    The parent link itself is made consistent -- the parent lists the child -- so
    the branch that fires is the one requiring a founder to be a lineage root.
    """
    child, parent = world["dynasties"][0], world["dynasties"][1]
    child["parent_dynasty_id"] = int(parent["id"])
    parent["child_dynasty_ids"] = [int(child["id"])]
    parent["child_dynasty_count"] = 1


GENEALOGY_RECORD_TAMPERS: tuple[tuple[str, Tamper, str], ...] = (
    ("dynasty child count wrong", _set("dynasties", "child_dynasty_count", 99), "dynasty genealogy links invalid"),
    ("dynasty founder dangling", _set("dynasties", "founder_dynasty_id", 999999), "dynasty genealogy links invalid"),
    ("dynasty successor dangling", _set("dynasties", "successor_dynasty_id", 999999), "dynasty genealogy links invalid"),
    ("dynasty parent dangling", _set("dynasties", "parent_dynasty_id", 999999), "dynasty genealogy links invalid"),
    (
        "dynasty child reference dangling",
        lambda world: world["dynasties"][0].update({"child_dynasty_ids": [999999], "child_dynasty_count": 1}),
        "dynasty genealogy links invalid",
    ),
    (
        "dynasty continuity above one",
        _set("dynasties", "dynastic_continuity_index", 5.0),
        "dynasty genealogy links invalid",
    ),
    ("ruler name blank", _set("rulers", "name", "  "), "ruler genealogy links invalid"),
    ("ruler parent dangling", _set("rulers", "parent_ruler_id", 999999), "ruler genealogy links invalid"),
    ("ruler predecessor dangling", _set("rulers", "predecessor_ruler_id", 999999), "ruler genealogy links invalid"),
    ("ruler successor dangling", _set("rulers", "successor_ruler_id", 999999), "ruler genealogy links invalid"),
    ("ruler spouse dangling", _set("rulers", "spouse_ruler_id", 999999), "ruler genealogy links invalid"),
    ("ruler alliance dangling", _set("rulers", "marriage_alliance_id", 999999), "ruler genealogy links invalid"),
    ("ruler cadet branch dangling", _set("rulers", "cadet_branch_id", 999999), "ruler genealogy links invalid"),
    (
        "alliance trade pact above one",
        _set("marriage_alliances", "trade_pact_index", 5.0),
        "ruler genealogy links invalid",
    ),
    ("cadet claim strength above one", _set("cadet_branches", "claim_strength", 5.0), "ruler genealogy links invalid"),
    ("cadet heir dangling", _set("cadet_branches", "heir_ruler_ids", [999999]), "ruler genealogy links invalid"),
    ("dynasty ruler count wrong", _set("dynasties", "ruler_count", 99), "ruler genealogy links invalid"),
    ("dynasty founder ruler dangling", _set("dynasties", "founder_ruler_id", 999999), "ruler genealogy links invalid"),
    ("dynasty founder is not a lineage root", _dynasty_founder_is_not_a_root, "dynasty genealogy links invalid"),
)

def _boundary_edge_inside_one_region(world: dict[str, Any]) -> None:
    """Point the first boundary segment at an edge that crosses no border.

    The edge still resolves and both of its cells are still in the mesh, so the
    branch that fires is the one demanding two *different* political regions
    behind a boundary edge.
    """
    cells_by_id = {int(cell["id"]): cell for cell in world["cells"]}
    for edge in world["cell_adjacency_edges"]:
        cell_a = cells_by_id.get(int(edge.get("cell_a_id", -1)))
        cell_b = cells_by_id.get(int(edge.get("cell_b_id", -1)))
        if cell_a is None or cell_b is None:
            continue
        region_a = int(cell_a.get("political_region_id", -1))
        if region_a >= 0 and region_a == int(cell_b.get("political_region_id", -1)):
            world["territorial_boundary_segments"][0]["source_edge_id"] = int(edge["id"])
            return
    raise AssertionError("the fixture has no cell-adjacency edge inside a single region")


def _boundary_edge_endpoint_cell_dangling(world: dict[str, Any]) -> None:
    """Send one endpoint of the segment's own edge to a cell id the mesh lacks.

    The tamper lands on the edge rather than on the segment, which the co-asserted
    ``cell adjacency edge records invalid`` line witnesses.
    """
    source_edge_id = int(world["territorial_boundary_segments"][0]["source_edge_id"])
    for edge in world["cell_adjacency_edges"]:
        if int(edge.get("id", -1)) == source_edge_id:
            edge["cell_a_id"] = 999999
            return
    raise AssertionError("the first boundary segment does not name a real edge")


TERRITORIAL_RECORD_TAMPERS: tuple[tuple[str, Tamper, tuple[str, ...]], ...] = (
    (
        "snapshot region_count wrong",
        _set("territorial_snapshots", "region_count", 99),
        ("territorial snapshot region_count does not match nested regions",),
    ),
    (
        "snapshot region stability_index removed",
        lambda world: world["territorial_snapshots"][0]["regions"][0].pop("stability_index", None),
        ("territorial snapshot region fields missing",),
    ),
    (
        "boundary segment edge dangling",
        _set("territorial_boundary_segments", "source_edge_id", 999999),
        ("territorial boundary segment records invalid",),
    ),
    (
        "boundary segment length drifts",
        _set("territorial_boundary_segments", "length_km", 12345.0),
        ("territorial boundary segment records invalid",),
    ),
    (
        "boundary segment edge crosses no border",
        _boundary_edge_inside_one_region,
        ("territorial boundary segment records invalid",),
    ),
    (
        "boundary segment edge endpoint cell missing from the mesh",
        _boundary_edge_endpoint_cell_dangling,
        ("territorial boundary segment records invalid", "cell adjacency edge records invalid"),
    ),
    (
        "boundary segments not a list",
        lambda world: world.__setitem__("territorial_boundary_segments", {}),
        ("territorial_boundary_segments missing",),
    ),
    (
        "snapshot region boundary count wrong",
        lambda world: world["territorial_snapshots"][0]["regions"][0].__setitem__(
            "cell_edge_boundary_segment_count", 99
        ),
        ("territorial snapshot boundary fields invalid",),
    ),
)

GRAPH_RECORD_TAMPERS: tuple[tuple[str, Tamper, str], ...] = (
    ("plate graph not a mapping", lambda world: world.__setitem__("plate_graph", []), "plate_graph missing or invalid"),
    (
        "river graph nodes not a list",
        lambda world: world["river_graph"].__setitem__("nodes", "x"),
        "river_graph nodes or edges invalid",
    ),
    (
        "watershed graph node_count wrong",
        lambda world: world["watershed_graph"].__setitem__("node_count", 999),
        "watershed_graph count fields do not match records",
    ),
    (
        "plate graph edge without cell edges",
        lambda world: world["plate_graph"]["edges"][0].__setitem__("cell_edge_count", 0),
        "plate_graph records invalid",
    ),
    (
        "river graph edge target dangling",
        lambda world: world["river_graph"]["edges"][0].__setitem__("to_cell_id", 999999),
        "river_graph records invalid",
    ),
    (
        "watershed graph edge without boundary edges",
        lambda world: world["watershed_graph"]["edges"][0].__setitem__("boundary_edge_count", 0),
        "watershed_graph records invalid",
    ),
    (
        "trade route graph edge route dangling",
        lambda world: world["trade_route_graph"]["edges"][0].__setitem__("route_id", 999999),
        "trade_route_graph records invalid",
    ),
    (
        "political region graph edge region dangling",
        lambda world: world["political_region_graph"]["edges"][0].__setitem__("region_a", 999999),
        "political_region_graph records invalid",
    ),
)

GEOLOGY_RECORD_TAMPERS: tuple[tuple[str, Tamper, str], ...] = (
    ("target window inverted", _set("geology_realism_checks", "target_max", -1.0), "geology realism checks invalid"),
    ("value not numeric", _set("geology_realism_checks", "value", "abc"), "geology realism checks invalid"),
)


class ValidateHistoryAndGraphGateTest(TestCase):
    """Every reporting branch is proven against one shared, passing control run."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = TemporaryDirectory()
        cls.work_dir = Path(cls._directory.name)
        cls.baseline: dict[str, Any] = worlds.cached_world(WORLD_KEY)
        control_path = cls.work_dir / "control.json"
        write_json(control_path, cls.baseline)
        cls.control = CliRunner().invoke(app, ["validate", "--world", str(control_path)])

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()

    def assert_control_passes(self) -> None:
        """The untampered world must validate, or a failure below proves nothing."""
        assert_no_cli_crash(self, self.control)
        self.assertEqual(self.control.exit_code, 0, self.control.output)
        self.assertNotIn("FAIL", self.control.output)

    def report_for(self, tamper: Tamper) -> str:
        """Apply ``tamper`` to a private copy of the world and validate it.

        ``tamper`` has to change something -- a hardcoded value that happens to
        equal the generated one would be a silent no-op -- and the command has to
        fail through its own gate rather than crash.  A crash also exits 1 with an
        empty output under ``CliRunner``, so the exception itself is inspected:
        the gate raises ``typer.Exit``, which reaches the runner as ``SystemExit``,
        while anything else means the check blew up instead of reporting.
        """
        world = copy.deepcopy(self.baseline)
        tamper(world)
        self.assertNotEqual(world, self.baseline, "the tamper left the world unchanged")
        path = self.work_dir / "tampered.json"
        write_json(path, world)
        result = CliRunner().invoke(app, ["validate", "--world", str(path)])
        assert_no_cli_crash(self, result)
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIsInstance(
            result.exception,
            SystemExit,
            f"validate crashed instead of reporting: {result.exception!r}",
        )
        return result.output

    def assert_reports(self, tamper: Tamper, messages: Iterable[str]) -> None:
        self.assert_control_passes()
        output = self.report_for(tamper)
        for message in messages:
            self.assertIn(f"FAIL {message}", output)

    def test_control_world_validates_cleanly(self) -> None:
        self.assert_control_passes()
        self.assertIn("OK", self.control.output)

    def test_summary_record_counts_must_match_records(self) -> None:
        """Every ``*_count`` summary field is recomputed from its record family."""

        def tamper(world: dict[str, Any]) -> None:
            for key, _ in SUMMARY_COUNTS:
                world["summary"][key] = 987654

        self.assert_reports(tamper, [message for _, message in SUMMARY_COUNTS])

    def test_summary_aggregates_must_match_records(self) -> None:
        """Totals and means are recomputed and compared with a relative tolerance."""

        def tamper(world: dict[str, Any]) -> None:
            for key, _ in SUMMARY_AGGREGATES:
                world["summary"][key] = float(world["summary"].get(key, 0.0)) * 1.5 + 137.5

        self.assert_reports(tamper, [message for _, message in SUMMARY_AGGREGATES])

    def test_summary_metrics_must_stay_in_range(self) -> None:
        def tamper(world: dict[str, Any]) -> None:
            for key, value, _ in SUMMARY_RANGES:
                world["summary"][key] = value

        self.assert_reports(tamper, [message for _, _, message in SUMMARY_RANGES])

    def test_summary_metric_groups_must_be_present(self) -> None:
        """Dropping one member of a required metric group trips its presence gate."""

        def tamper(world: dict[str, Any]) -> None:
            for key, _ in SUMMARY_METRIC_GROUPS:
                world["summary"].pop(key, None)

        self.assert_reports(tamper, [message for _, message in SUMMARY_METRIC_GROUPS])

    def test_record_schema_fields_must_be_present(self) -> None:
        for family, field, message in RECORD_SCHEMA_FIELDS:
            with self.subTest(family=family, field=field):
                self.assert_reports(_drop(family, field), [message])

    def test_conflict_and_economy_history_records(self) -> None:
        for label, tamper, message in CONFLICT_AND_ECONOMY_TAMPERS:
            with self.subTest(case=label):
                self.assert_reports(tamper, [message])

    def test_logistics_and_market_records(self) -> None:
        for label, tamper in LOGISTICS_RECORD_TAMPERS:
            with self.subTest(case=label):
                self.assert_reports(tamper, ["logistics history records invalid"])

    def test_campaign_operation_records(self) -> None:
        for label, tamper in CAMPAIGN_RECORD_TAMPERS:
            with self.subTest(case=label):
                self.assert_reports(tamper, ["logistics history records invalid"])

    def test_demographic_agent_records(self) -> None:
        for label, tamper in DEMOGRAPHIC_RECORD_TAMPERS:
            with self.subTest(case=label):
                self.assert_reports(tamper, ["demographic agent records invalid"])

    def test_dynasty_and_ruler_genealogy_records(self) -> None:
        for label, tamper, message in GENEALOGY_RECORD_TAMPERS:
            with self.subTest(case=label):
                self.assert_reports(tamper, [message])

    def test_territorial_snapshot_and_boundary_records(self) -> None:
        for label, tamper, messages in TERRITORIAL_RECORD_TAMPERS:
            with self.subTest(case=label):
                self.assert_reports(tamper, messages)

    def test_snapshot_field_and_empty_region_list_branches_are_separated(self) -> None:
        """Two snapshot branches share one message, so pin what only one emits.

        ``territorial snapshot fields missing`` is appended both when a snapshot
        field is absent and when a world with political regions carries a snapshot
        with no regions.  Emptying the region list is the only one of the two that
        also breaks the nested region_count, which tells the branches apart.
        """
        self.assert_control_passes()

        missing_field = self.report_for(_drop("territorial_snapshots", "fragmentation_index"))
        self.assertIn("FAIL territorial snapshot fields missing", missing_field)
        self.assertNotIn("FAIL territorial snapshot region_count does not match nested regions", missing_field)

        no_regions = self.report_for(_set("territorial_snapshots", "regions", {}))
        self.assertIn("FAIL territorial snapshot fields missing", no_regions)
        self.assertIn("FAIL territorial snapshot region_count does not match nested regions", no_regions)

    def test_derived_graph_records(self) -> None:
        for label, tamper, message in GRAPH_RECORD_TAMPERS:
            with self.subTest(case=label):
                self.assert_reports(tamper, [message])

    def test_geology_realism_records(self) -> None:
        for label, tamper, message in GEOLOGY_RECORD_TAMPERS:
            with self.subTest(case=label):
                self.assert_reports(tamper, [message])
