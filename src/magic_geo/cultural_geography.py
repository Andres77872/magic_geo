from __future__ import annotations

from typing import Any


CULTURE_REGION_MODEL = "causal_political_homeland_barrier_trade_culture_regions_v1"
LANGUAGE_REGION_MODEL = "causal_trade_union_family_lineage_phonology_v1"
CULTURAL_SITE_MODEL = "causal_terrain_culture_ranked_sacred_ruin_sites_v1"


def _legacy_enrich_world_with_cultural_geography_models(world: dict[str, Any]) -> dict[str, Any]:
    cultures = world.get("cultures", [])
    languages = world.get("language_regions", [])
    sacred_areas = world.get("sacred_areas", [])
    ruins = world.get("ruins", [])
    if not all(isinstance(value, list) for value in (cultures, languages, sacred_areas, ruins)):
        return world

    world["culture_region_model"] = {
        "model_type": CULTURE_REGION_MODEL,
        "deterministic": True,
        "homeland_model": "one_culture_per_political_region_in_record_order_v1",
        "cell_assignment_model": "nonwater_political_region_to_homeland_culture_v1",
        "culture_type_model": "maritime_river_mountain_desert_mining_boreal_forest_agrarian_priority_v1",
        "mountain_mean_elevation_threshold_m": 1100.0,
        "agricultural_area_model": "fertility_or_alluvial_resource_or_floodplain_delta_v1",
        "agricultural_fertility_threshold": 0.62,
        "agricultural_fertility_threshold_semantics": "raw_strict_greater_than_v1",
        "source_fertility_serialization_decimals": 8,
        "mining_area_model": "metal_placer_or_geothermal_resource_cells_v1",
        "barrier_isolation_model": "border_length_weighted_mean_barrier_score_v1",
        "trade_contact_model": "incident_trade_volume_per_100_per_settlement_capped_v1",
        "migration_pressure_model": "barrier_trade_fertility_elevation_weighted_index_v1",
        "migration_pressure_parameters": {
            "base": 0.18,
            "permeability_weight": 0.28,
            "trade_weight": 0.22,
            "fertility_deficit_weight": 0.16,
            "elevation_weight": 0.12,
            "elevation_scale_m": 1800.0,
        },
        "continuity_model": "barrier_fertility_settlement_sacred_ruin_weighted_index_v1",
        "continuity_parameters": {
            "base": 0.30,
            "barrier_weight": 0.22,
            "fertility_weight": 0.18,
            "settlement_weight": 0.10,
            "settlement_scale": 6.0,
            "sacred_area_weight": 0.10,
            "sacred_area_scale": 3.0,
            "ruin_penalty_weight": 0.16,
            "ruin_scale": 4.0,
        },
        "age_model": "continuity_barrier_settlement_bounded_estimated_age_v1",
        "age_parameters": {
            "base_years": 420.0,
            "continuity_years": 1900.0,
            "barrier_years": 520.0,
            "settlement_years": 260.0,
            "settlement_scale": 8.0,
            "minimum_years": 120.0,
            "maximum_years": 4200.0,
        },
        "dominant_field_model": "count_then_native_enum_order_with_nonzero_resource_v1",
        "model_limitation": "static_political_homelands_without_cultural_diffusion_identity_change_or_population_feedback",
    }
    world["language_region_model"] = {
        "model_type": LANGUAGE_REGION_MODEL,
        "deterministic": True,
        "union_model": "minimum_root_union_on_high_volume_low_friction_interregional_trade_v1",
        "union_volume_threshold": 70.0,
        "union_friction_maximum": 0.92,
        "record_order": "union_root_first_culture_order_v1",
        "family_model": "culture_type_family_area_dominance_native_enum_tie_v1",
        "lineage_model": "largest_area_family_root_then_global_largest_fallback_v1",
        "change_rate_model": "barrier_trade_culture_count_weighted_index_v1",
        "root_divergence_model": "inverse_change_rate_plus_barrier_bounded_years_v1",
        "child_divergence_model": "barrier_plus_inverse_trade_bounded_years_v1",
        "fallback_child_change_rate_bonus": 0.08,
        "base_phoneme_inventory_by_family": {
            "riverine": 27,
            "coastal": 31,
            "highland": 34,
            "arid": 24,
            "lowland": 29,
            "frontier": 30,
        },
        "phonology_model": "parent_inventory_inheritance_shift_isolation_contact_lineage_v1",
        "model_limitation": "diagnostic_language_union_and_single_generation_lineage_without_speaker_interaction_or_observed_linguistic_calibration",
    }
    world["cultural_site_model"] = {
        "model_type": CULTURAL_SITE_MODEL,
        "deterministic": True,
        "sacred_candidate_threshold": 0.30,
        "sacred_target_model": "clamp_two_per_culture_2_24_v1",
        "ruin_candidate_threshold": 0.32,
        "source_fertility_serialization_decimals": 8,
        "ruin_target_model": "clamp_culture_count_plus_floor_settlement_count_div_4_2_32_v1",
        "minimum_angular_separation_model": "1_4_sqrt_4pi_div_cell_count_radians_v1",
        "candidate_order": "descending_raw_significance_then_cell_id_v1",
        "sacred_significance_model": "terrain_water_geothermal_desert_fertility_coast_relief_weighted_index_v1",
        "sacred_type_model": "volcanic_mountain_water_grove_desert_coast_priority_v1",
        "ruin_significance_model": "settlement_fertility_water_resource_times_abandonment_pressure_v1",
        "ruin_type_model": "mine_desert_mountain_harbor_glacial_city_priority_v1",
        "abandonment_reason_model": "aridity_tectonic_glaciation_salinization_trade_frontier_priority_v1",
        "preservation_model": "base_desert_ice_minus_high_precipitation_v1",
        "model_limitation": "ranked_diagnostic_sites_without_settlement_lifecycle_archaeology_or_temporal_land_use",
    }
    summary = world.setdefault("summary", {})
    summary["culture_region_model"] = CULTURE_REGION_MODEL
    summary["language_region_model"] = LANGUAGE_REGION_MODEL
    summary["cultural_site_model"] = CULTURAL_SITE_MODEL
    return world


def enrich_world_with_cultural_geography_models(world: dict[str, Any]) -> dict[str, Any]:
    from .native_social_models import annotate_native_social_models

    return annotate_native_social_models(
        world, _legacy_enrich_world_with_cultural_geography_models, ('culture_region_model', 'language_region_model', 'cultural_site_model'),
    )
