"""Annotate the actual native availability family without relabeling old worlds."""
from __future__ import annotations

from typing import Any, Callable

from .native_social_availability import (
    NATIVE_SOCIAL_MODEL, SOCIAL_MODEL_TYPES, exact_contract,
    require_native_social_availability, uses_native_social_availability,
)

_SELECTION = "causal_native_score_local_max_separated_settlement_selection_v3"
_POLITICAL = "causal_capital_barrier_partition_political_regions_v1"
_BORDER = "causal_adjacent_region_terrain_border_segments_v1"
_TRADE = "causal_route_endpoint_complement_trade_flows_v1"
_ROUTE = "causal_endpoint_barrier_ranked_route_network_v1"
_LANGUAGE = "causal_trade_union_family_lineage_phonology_v1"

SOCIAL_SOURCES = {
    "culture_region_model": {
        "source_settlement_model": _SELECTION,
        "source_political_region_model": _POLITICAL,
        "source_cultural_site_model": SOCIAL_MODEL_TYPES["cultural_site_model"],
        "source_trade_flow_model": _TRADE,
    },
    "cultural_site_model": {
        "source_settlement_model": _SELECTION,
        "source_culture_membership_model": "one_culture_per_political_region_in_record_order_v1",
        "source_political_region_model": _POLITICAL,
    },
    "population_region_model": {
        "source_settlement_model": _SELECTION,
        "source_culture_region_model": SOCIAL_MODEL_TYPES["culture_region_model"],
        "source_political_region_model": _POLITICAL,
        "source_route_network_model": _ROUTE,
    },
    "historical_event_model": {
        "source_culture_region_model": SOCIAL_MODEL_TYPES["culture_region_model"],
        "source_cultural_site_model": SOCIAL_MODEL_TYPES["cultural_site_model"],
        "source_language_region_model": _LANGUAGE,
        "source_political_region_model": _POLITICAL,
        "source_political_border_model": _BORDER,
        "source_trade_flow_model": _TRADE,
    },
    "conflict_model": {
        "source_population_region_model": SOCIAL_MODEL_TYPES["population_region_model"],
        "source_political_region_model": _POLITICAL,
        "source_political_border_model": _BORDER,
        "source_trade_flow_model": _TRADE,
    },
    "dynasty_model": {
        "source_population_region_model": SOCIAL_MODEL_TYPES["population_region_model"],
        "source_culture_region_model": SOCIAL_MODEL_TYPES["culture_region_model"],
        "source_historical_event_model": SOCIAL_MODEL_TYPES["historical_event_model"],
        "source_conflict_model": SOCIAL_MODEL_TYPES["conflict_model"],
    },
    "territorial_snapshot_model": {
        "geometry_radius_source": "planet_parameters.radius_km_native_geometry_parameter",
        "source_population_region_model": SOCIAL_MODEL_TYPES["population_region_model"],
        "source_culture_region_model": SOCIAL_MODEL_TYPES["culture_region_model"],
        "source_historical_event_model": SOCIAL_MODEL_TYPES["historical_event_model"],
        "source_conflict_model": SOCIAL_MODEL_TYPES["conflict_model"],
        "source_political_region_model": _POLITICAL,
    },
}

SOCIAL_AVAILABILITY_POLICIES = {
    "culture_region_model": "retain_independent_descriptors_null_incomplete_global_ruin_count_continuity_age",
    "cultural_site_model": "independent_sacred_selection_complete_actual_ruin_candidates_before_global_rank",
    "population_region_model": "unchanged_total_territory_denominator_complete_site_capacity_and_culture_population",
    "historical_event_model": "retain_independent_event_fields_with_family_coverage_and_complete_era_aggregates",
    "conflict_model": "complete_actual_border_pair_population_inputs_before_global_rank_cap",
    "dynasty_model": "available_region_lineages_with_explicit_incomplete_collection_coverage",
    "territorial_snapshot_model": "retain_unscaled_base_geometry_null_unavailable_historical_geometry_population",
}


def annotate_native_social_models(
    world: dict[str, Any], legacy_enricher: Callable[[dict[str, Any]], dict[str, Any]],
    owned_models: tuple[str, ...],
) -> dict[str, Any]:
    """Keep old declarations exact; stage all successor annotations before writes."""
    if not uses_native_social_availability(world):
        return legacy_enricher(world)
    require_native_social_availability(world)
    # Native serialization emits the complete social family before these four
    # Python annotation calls. Audit that family in a private annotation view so
    # the first call can validate every parent without publishing its siblings.
    from .cultural_geography import _legacy_enrich_world_with_cultural_geography_models
    from .historical_geography import _legacy_enrich_world_with_historical_geography_model
    from .civilization_geography import _legacy_enrich_world_with_civilization_geography_models
    from .territorial_geography import _legacy_enrich_world_with_territorial_geography_model
    from .cultural_geography_validation import validate_cultural_geography_replay
    from .historical_geography_validation import validate_historical_geography_replay
    from .civilization_geography_validation import validate_civilization_geography_replay
    from .territorial_geography_validation import validate_territorial_geography_replay

    staged = dict(world)
    staged["summary"] = dict(world["summary"])
    for annotate in (
        _legacy_enrich_world_with_cultural_geography_models,
        _legacy_enrich_world_with_historical_geography_model,
        _legacy_enrich_world_with_civilization_geography_models,
        _legacy_enrich_world_with_territorial_geography_model,
    ):
        annotate(staged)
    for key in (*SOCIAL_MODEL_TYPES, "language_region_model"):
        declaration = staged.get(key)
        if type(declaration) is not dict:
            raise ValueError("complete native social annotation inputs required")
        if key in SOCIAL_MODEL_TYPES:
            declaration = dict(declaration)
            declaration["model_type"] = SOCIAL_MODEL_TYPES[key]
            declaration["source_native_social_availability_model"] = NATIVE_SOCIAL_MODEL["model_type"]
            declaration["availability_policy"] = SOCIAL_AVAILABILITY_POLICIES[key]
            declaration.update(SOCIAL_SOURCES[key])
        # No implicit relabeling or silent repair of an old/malformed dictionary.
        if key in world and not exact_contract(world[key], declaration):
            raise ValueError("incompatible existing social annotation: " + key)
        if key in world["summary"] and world["summary"][key] != declaration["model_type"]:
            raise ValueError("incompatible existing social summary annotation: " + key)
        staged[key] = declaration
        staged["summary"][key] = declaration["model_type"]
    for validate in (
        validate_cultural_geography_replay,
        validate_historical_geography_replay,
        validate_civilization_geography_replay,
        validate_territorial_geography_replay,
    ):
        failures = validate(staged)
        if failures:
            raise ValueError("invalid native social source: " + "; ".join(failures))
    publication = {key: staged[key] for key in owned_models}
    world.update(publication)
    world["summary"].update({key: value["model_type"] for key, value in publication.items()})
    return world
