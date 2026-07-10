from __future__ import annotations

from typing import Any


HISTORICAL_EVENT_MODEL = "causal_region_culture_language_trade_site_timeline_v1"


def enrich_world_with_historical_geography_model(world: dict[str, Any]) -> dict[str, Any]:
    eras = world.get("historical_eras", [])
    events = world.get("historical_events", [])
    if not isinstance(eras, list) or not isinstance(events, list):
        return world

    world["historical_event_model"] = {
        "model_type": HISTORICAL_EVENT_MODEL,
        "deterministic": True,
        "era_model": "fixed_four_era_strict_year_bp_partition_v1",
        "eras": [
            {"id": 0, "dominant_process": "founding", "start_year_bp": 4200.0, "end_year_bp": 2400.0},
            {"id": 1, "dominant_process": "expansion", "start_year_bp": 2400.0, "end_year_bp": 1300.0},
            {"id": 2, "dominant_process": "fragmentation", "start_year_bp": 1300.0, "end_year_bp": 450.0},
            {"id": 3, "dominant_process": "integration", "start_year_bp": 450.0, "end_year_bp": 0.0},
        ],
        "state_foundation_model": "region_barrier_pressure_and_culture_age_v1",
        "state_foundation_parameters": {
            "base_pressure": 0.18,
            "region_barrier_weight": 0.32,
            "border_barrier_weight": 0.28,
            "small_region_pressure_bonus": 0.18,
            "small_region_settlement_maximum": 2,
            "base_year_bp": 380.0,
            "culture_age_weight": 0.72,
            "minimum_year_bp": 260.0,
            "maximum_year_bp": 3800.0,
        },
        "dynastic_change_model": "foundation_age_region_order_pressure_trade_or_isolation_trigger_v1",
        "dynastic_change_parameters": {
            "pressure_threshold": 0.34,
            "trade_contact_threshold": 0.55,
            "route_count_trigger": 0,
            "foundation_year_weight": 0.48,
            "region_order_year_step": 180.0,
            "minimum_year_bp": 180.0,
            "maximum_year_bp": 2100.0,
            "trade_pressure_weight": 0.18,
        },
        "migration_model": "culture_pressure_or_trade_trigger_same_language_contact_link_v1",
        "migration_parameters": {
            "migration_pressure_threshold": 0.42,
            "trade_contact_threshold": 0.28,
            "base_year_bp": 260.0,
            "migration_pressure_year_weight": 2100.0,
            "culture_order_year_step": 220.0,
            "minimum_year_bp": 120.0,
            "maximum_year_bp": 2600.0,
        },
        "language_split_model": "child_language_divergence_age_change_rate_v1",
        "language_split_minimum_year_bp": 80.0,
        "language_split_maximum_year_bp": 3400.0,
        "trade_boom_model": "top_volume_then_id_trade_flow_friction_timeline_v1",
        "trade_boom_maximum_events": 12,
        "trade_boom_parameters": {
            "base_year_bp": 140.0,
            "friction_year_weight": 820.0,
            "rank_year_step": 42.0,
            "minimum_year_bp": 70.0,
            "maximum_year_bp": 1300.0,
        },
        "sacred_founding_model": "first_twelve_ranked_sacred_sites_significance_timeline_v1",
        "sacred_founding_maximum_events": 12,
        "ruin_abandonment_model": "first_sixteen_ranked_ruins_significance_timeline_v1",
        "ruin_abandonment_maximum_events": 16,
        "event_order": "descending_raw_year_bp_then_native_event_enum_v1",
        "era_aggregate_model": "event_count_and_mean_pressure_continuity_v1",
        "model_limitation": "diagnostic_single-timeline_events_without_agent_causation_duration_uncertainty_or_observed_historical_calibration",
    }
    world.setdefault("summary", {})["historical_event_model"] = HISTORICAL_EVENT_MODEL
    return world
