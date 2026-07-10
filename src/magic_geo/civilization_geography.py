from __future__ import annotations

from typing import Any


POPULATION_REGION_MODEL = "causal_area_weighted_capacity_occupancy_population_regions_v1"
CONFLICT_MODEL = "causal_border_pair_pressure_trade_conflict_selection_v1"
DYNASTY_MODEL = "causal_foundation_continuity_pressure_dynasty_lineages_v1"


def enrich_world_with_civilization_geography_models(world: dict[str, Any]) -> dict[str, Any]:
    populations = world.get("population_regions", [])
    conflicts = world.get("conflicts", [])
    if not isinstance(populations, list) or not isinstance(conflicts, list):
        return world

    world["population_region_model"] = {
        "model_type": POPULATION_REGION_MODEL,
        "deterministic": True,
        "membership_model": "nonwater_political_region_cells_v1",
        "water_security_model": "runoff_river_lake_water_neighbor_saline_penalty_v1",
        "climate_suitability_model": "temperature_precipitation_ice_bounded_index_v1",
        "hazard_mortality_model": "tectonic_local_relief_ice_bounded_index_v1",
        "density_capacity_model": "fertility_water_climate_and_site_strength_v1",
        "density_capacity_parameters": {
            "base_people_per_km2": 1.5,
            "agricultural_weight": 64.0,
            "site_strength_weight": 12.0,
            "minimum_people_per_km2": 0.2,
            "maximum_people_per_km2": 90.0,
        },
        "urbanization_model": "settlement_route_and_site_strength_v1",
        "occupancy_model": "continuity_urbanization_routes_hazard_v1",
        "growth_model": "agriculture_water_pressure_hazard_bounded_rate_v1",
        "migration_balance_model": "one_half_minus_culture_migration_pressure_v1",
        "model_limitation": "static_diagnostic_capacity_and_occupancy_without_age_structure_land_use_feedback_disease_or_observed_demographic_calibration",
    }
    world["conflict_model"] = {
        "model_type": CONFLICT_MODEL,
        "deterministic": True,
        "candidate_model": "highest_score_border_per_sorted_region_pair_v1",
        "minimum_candidate_score": 0.24,
        "maximum_conflicts_per_region": 2,
        "cause_model": "water_fertility_resource_trade_then_nonopen_border_priority_v1",
        "resource_pressure_if_present": 0.72,
        "trade_chokepoint_model": "interregional_pair_flow_volume_times_friction_plus_hard_border_v1",
        "hard_border_trade_bonus": 0.34,
        "intensity_model": "population_border_resource_water_trade_weighted_index_v1",
        "candidate_score_fertility_weight": 0.08,
        "record_order": "descending_raw_candidate_score_then_region_pair_v1",
        "contested_cell_model": "border_cell_a_if_intensity_at_least_one_half_else_cell_b_v1",
        "chronology_model": "intensity_candidate_map_size_duration_and_era_v1",
        "war_diagnostics_model": "population_route_urbanization_logistics_mobilization_casualty_disruption_v1",
        "outcome_model": "exhaustion_stalemate_border_shift_or_force_advantage_v1",
        "model_limitation": "one_diagnostic_conflict_per_adjacent_region_pair_without_strategy_diplomacy_uncertainty_or_observed_war_calibration",
    }
    world["dynasty_model"] = {
        "model_type": DYNASTY_MODEL,
        "deterministic": True,
        "foundation_model": "oldest_state_foundation_event_per_region_v1",
        "succession_pressure_model": "population_conflict_route_and_culture_continuity_v1",
        "dynasty_count_thresholds": [0.36, 0.66],
        "lineage_model": "contiguous_region_chain_with_root_parent_child_successor_links_v1",
        "duration_model": "equal_foundation_year_partition_by_region_dynasty_count_v1",
        "legitimacy_model": "continuity_settlement_succession_and_conflict_v1",
        "dynastic_continuity_model": "legitimacy_duration_and_inverse_succession_pressure_v1",
        "collapse_reason_model": "continuity_conflict_migration_resource_trade_then_succession_priority_v1",
        "model_limitation": "single_linear_dynasty_chain_per_region_without_person_level_succession_branch_competition_or_observed_genealogy_calibration",
    }
    summary = world.setdefault("summary", {})
    summary["population_region_model"] = POPULATION_REGION_MODEL
    summary["conflict_model"] = CONFLICT_MODEL
    summary["dynasty_model"] = DYNASTY_MODEL
    return world
