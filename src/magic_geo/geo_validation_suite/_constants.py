"""Module-level constants shared by the submodules."""

from __future__ import annotations


GEO_VALIDATION_SUITE_SCHEMA_VERSION = 1


EMPIRICAL_TARGET_BUNDLE_SCHEMA_VERSION = 1


MAX_SCENARIO_COUNT = 64


COMPARISON_OPERATORS = {"lt", "le", "gt", "ge", "eq"}


SETON_SOURCE_ID = "seton_2020_oceanic_age"


SETON_SUPPLEMENTAL_NAME = "seton_2020_oceanic_crust_age_targets_v1"


SETON_SUPPLEMENTAL_TOOL = "scripts/derive_seton_oceanic_age_targets.py"


SETON_CDF_THRESHOLDS_MA = tuple(range(20, 201, 20))


CIVILIZATION_TOP_LEVEL_FIELDS = {
    "agricultural_zones",
    "borders",
    "cadet_branches",
    "campaign_front_histories",
    "campaign_movements",
    "campaign_operations_model",
    "campaign_path_segments",
    "conflict_model",
    "conflicts",
    "cultural_site_model",
    "culture_region_model",
    "cultures",
    "demographic_agent_histories",
    "demographic_agent_model",
    "dynasties",
    "dynasty_model",
    "economy_histories",
    "economy_history_model",
    "firm_agents",
    "historical_eras",
    "historical_event_model",
    "historical_events",
    "household_cohorts",
    "individual_agents",
    "individual_life_event_model",
    "individual_life_events",
    "land_use_zone_model",
    "language_region_model",
    "language_regions",
    "lexical_correspondences",
    "lexical_diffusion_histories",
    "logistics_exchange_model",
    "logistics_networks",
    "market_agent_orders",
    "market_clearing_model",
    "market_clearing_records",
    "market_exchanges",
    "market_inventory_histories",
    "market_price_iterations",
    "marriage_alliances",
    "mining_zones",
    "natural_frontier_model",
    "natural_frontiers",
    "navigability_model",
    "navigable_waterways",
    "phonological_histories",
    "phonological_rules",
    "phonology_history_model",
    "political_border_model",
    "political_region_graph",
    "political_region_model",
    "political_regions",
    "population_histories",
    "population_history_model",
    "population_region_model",
    "population_regions",
    "port_site_model",
    "port_sites",
    "route_capacity_constraints",
    "route_corridor_model",
    "route_corridors",
    "route_network_model",
    "routes",
    "ruins",
    "ruler_genealogy_model",
    "rulers",
    "sacred_areas",
    "settlement_selection_model",
    "settlements",
    "speaker_population_histories",
    "strategic_campaign_plans",
    "tactical_engagements",
    "territorial_boundary_segments",
    "territorial_snapshot_model",
    "territorial_snapshots",
    "trade_flow_model",
    "trade_flows",
    "trade_route_graph",
    "worldbuilding_realism_checks",
    "worldbuilding_realism_model",
}


CIVILIZATION_NESTED_FIELDS = {
    "agricultural_habitat_applicable",
    "agricultural_climate_supported",
    "agricultural_potential_supported",
    "mining_surface_applicable",
    "agricultural_potential_index",
    "agricultural_zone_id",
    "coastal_navigability_index",
    "coastal_route_index",
    "culture_region_id",
    "culture_region_ids",
    "harbor_suitability_index",
    "language_region_id",
    "language_region_ids",
    "market_value_index",
    "mining_potential_index",
    "mining_zone_id",
    "mountain_pass_route_index",
    "natural_frontier_id",
    "natural_frontier_index",
    "natural_frontier_type",
    "navigability_class",
    "navigability_index",
    "navigable_waterway_id",
    "oasis_route_index",
    "political_region_id",
    "political_region_ids",
    "population",
    "port_site_id",
    "port_site_ids",
    "port_site_type",
    "port_suitability_index",
    "river_mouth_port_index",
    "river_navigability_index",
    "river_valley_route_index",
    "route_corridor_id",
    "route_corridor_index",
    "route_corridor_type",
    "route_ids",
    "settlement_id",
    "settlement_ids",
    "settlement_score",
    "strait_access_index",
    "transport_chokepoint_index",
}
