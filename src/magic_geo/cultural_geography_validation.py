from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any


CULTURE_REGION_MODEL = "causal_political_homeland_barrier_trade_culture_regions_v1"
LANGUAGE_REGION_MODEL = "causal_trade_union_family_lineage_phonology_v1"
CULTURAL_SITE_MODEL = "causal_terrain_culture_ranked_sacred_ruin_sites_v1"

BIOME_ORDER = [
    "ocean",
    "continental_shelf",
    "lake",
    "ice_cap",
    "tundra",
    "boreal_forest",
    "temperate_forest",
    "temperate_grassland",
    "mediterranean_scrub",
    "cold_desert",
    "hot_desert",
    "savanna",
    "tropical_seasonal_forest",
    "tropical_rainforest",
    "alpine",
    "wetland",
]
RESOURCE_ORDER = [
    "none",
    "volcanic_arc_metals",
    "craton_iron_gold",
    "sedimentary_fuels",
    "evaporites",
    "placer_metals",
    "geothermal",
    "fertile_alluvium",
    "coastal_fisheries",
]
FAMILY_ORDER = ["riverine", "coastal", "highland", "arid", "lowland", "frontier"]
BASE_INVENTORY = {
    "riverine": 27,
    "coastal": 31,
    "highland": 34,
    "arid": 24,
    "lowland": 29,
    "frontier": 30,
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _culture_model() -> dict[str, Any]:
    return {
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


def _language_model() -> dict[str, Any]:
    return {
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
        "base_phoneme_inventory_by_family": dict(BASE_INVENTORY),
        "phonology_model": "parent_inventory_inheritance_shift_isolation_contact_lineage_v1",
        "model_limitation": "diagnostic_language_union_and_single_generation_lineage_without_speaker_interaction_or_observed_linguistic_calibration",
    }


def _site_model() -> dict[str, Any]:
    return {
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


def _close(actual: Any, expected: float, tolerance: float) -> bool:
    try:
        return abs(float(actual) - expected) <= tolerance
    except (TypeError, ValueError):
        return False


def _native_dominant(counter: Counter[str], order: list[str], *, exclude_none: bool = False) -> str:
    best = "none" if exclude_none else order[0]
    best_count = -1
    for value in order:
        if exclude_none and value == "none":
            continue
        count = counter.get(value, 0)
        if count > best_count:
            best = value
            best_count = count
    return "none" if exclude_none and best_count <= 0 else best


def _culture_type(region: dict[str, Any]) -> str:
    region_type = str(region.get("type", ""))
    biome = str(region.get("dominant_biome", ""))
    resource = str(region.get("dominant_resource", "none"))
    if region_type == "maritime_league":
        return "maritime"
    if region_type == "river_realm":
        return "river_valley"
    if region_type == "mountain_march" or float(region.get("mean_elevation_m", 0.0)) > 1100.0:
        return "highland"
    if biome in {"cold_desert", "hot_desert"}:
        return "desert_oasis"
    if region_type == "mining_domain" or resource in {
        "volcanic_arc_metals",
        "craton_iron_gold",
        "placer_metals",
        "geothermal",
    }:
        return "mining_frontier"
    if biome in {"tundra", "boreal_forest"}:
        return "boreal_frontier"
    if biome in {"savanna", "tropical_seasonal_forest", "tropical_rainforest"}:
        return "forest_realm"
    return "agrarian_lowland"


def _family_for_culture(culture_type: str) -> str:
    return {
        "river_valley": "riverine",
        "maritime": "coastal",
        "highland": "highland",
        "desert_oasis": "arid",
        "agrarian_lowland": "lowland",
    }.get(culture_type, "frontier")


def _find(parent: list[int], value: int) -> int:
    root = value
    while parent[root] != root:
        root = parent[root]
    while parent[value] != value:
        next_value = parent[value]
        parent[value] = root
        value = next_value
    return root


def _union(parent: list[int], first: int, second: int) -> None:
    first_root = _find(parent, first)
    second_root = _find(parent, second)
    if first_root != second_root:
        parent[max(first_root, second_root)] = min(first_root, second_root)


def _local_relief(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    neighbor_ids = [int(value) for value in cell.get("neighbors", [])]
    if not neighbor_ids:
        return 0.0
    mean_neighbor = sum(float(cells_by_id[cell_id].get("elevation_m", 0.0)) for cell_id in neighbor_ids) / len(neighbor_ids)
    return max(0.0, float(cell.get("elevation_m", 0.0)) - mean_neighbor)


def _has_water_neighbor(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    return any(bool(cells_by_id[int(value)].get("is_water", False)) for value in cell.get("neighbors", []))


def _angular_distance(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_position = first.get("position_3d", [])
    second_position = second.get("position_3d", [])
    if not isinstance(first_position, list) or not isinstance(second_position, list) or len(first_position) != 3 or len(second_position) != 3:
        return math.inf
    dot = sum(float(first_position[index]) * float(second_position[index]) for index in range(3))
    return math.acos(max(-1.0, min(1.0, dot)))


def _sacred_significance(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    score = 0.0
    elevation = float(cell.get("elevation_m", 0.0))
    landform = str(cell.get("landform", ""))
    resource = str(cell.get("resource", "none"))
    water_body = str(cell.get("water_body_type", "land"))
    if elevation > 1700.0 or landform in {"mountain_belt", "glacial_valley"}:
        score += 0.34
    if bool(cell.get("is_river", False)) or bool(cell.get("is_lake", False)) or water_body in {"fresh_lake", "saline_basin"}:
        score += 0.18
    if resource == "geothermal" or landform == "volcanic_arc":
        score += 0.26
    if landform == "salt_flat" or bool(cell.get("is_closed_basin", False)):
        score += 0.22
    if float(cell.get("fertility", 0.0)) > 0.74 and float(cell.get("precipitation_mm_y", 0.0)) > 650.0:
        score += 0.16
    if _has_water_neighbor(cell, cells_by_id):
        score += 0.12
    score += 0.12 * _clamp(_local_relief(cell, cells_by_id) / 1700.0)
    return _clamp(score)


def _sacred_type(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> str:
    resource = str(cell.get("resource", "none"))
    landform = str(cell.get("landform", ""))
    biome = str(cell.get("biome", ""))
    water_body = str(cell.get("water_body_type", "land"))
    if resource == "geothermal" or landform == "volcanic_arc":
        return "volcanic_sanctuary"
    if float(cell.get("elevation_m", 0.0)) > 1700.0 or landform in {"mountain_belt", "glacial_valley"}:
        return "mountain_shrine"
    if bool(cell.get("is_river", False)) or bool(cell.get("is_lake", False)) or water_body in {"fresh_lake", "saline_basin"}:
        return "spring_oracle"
    if biome in {"boreal_forest", "temperate_forest", "tropical_rainforest", "wetland"}:
        return "sacred_grove"
    if biome in {"cold_desert", "hot_desert"} or landform == "salt_flat":
        return "desert_sanctuary"
    if _has_water_neighbor(cell, cells_by_id):
        return "ancestral_coast"
    return "sacred_grove"


def _ruin_significance(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    resource = str(cell.get("resource", "none"))
    biome = str(cell.get("biome", ""))
    landform = str(cell.get("landform", ""))
    water_body = str(cell.get("water_body_type", "land"))
    historical = 0.18 + 0.38 * float(cell.get("settlement_score", 0.0)) + 0.24 * float(cell.get("fertility", 0.0))
    if bool(cell.get("is_river", False)) or bool(cell.get("is_lake", False)) or _has_water_neighbor(cell, cells_by_id):
        historical += 0.14
    if resource in {
        "volcanic_arc_metals",
        "craton_iron_gold",
        "sedimentary_fuels",
        "evaporites",
        "placer_metals",
        "geothermal",
        "fertile_alluvium",
    }:
        historical += 0.16
    pressure = 0.0
    if biome in {"cold_desert", "hot_desert"} or float(cell.get("precipitation_mm_y", 0.0)) < 220.0:
        pressure += 0.24
    if float(cell.get("ice_thickness_m", 0.0)) > 20.0 or biome == "ice_cap":
        pressure += 0.22
    if water_body == "saline_basin" or landform == "salt_flat" or bool(cell.get("is_closed_basin", False)):
        pressure += 0.18
    pressure += 0.18 * _clamp(float(cell.get("boundary_convergent", 0.0)) + float(cell.get("boundary_transform", 0.0)))
    pressure += 0.12 * _clamp(_local_relief(cell, cells_by_id) / 1800.0)
    if float(cell.get("settlement_score", 0.0)) < 0.52:
        pressure += 0.10
    return _clamp(historical * (0.55 + pressure))


def _ruin_type(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> str:
    resource = str(cell.get("resource", "none"))
    biome = str(cell.get("biome", ""))
    landform = str(cell.get("landform", ""))
    if resource in {"volcanic_arc_metals", "craton_iron_gold", "placer_metals", "geothermal"}:
        return "abandoned_mine"
    if biome in {"cold_desert", "hot_desert"} or landform == "salt_flat":
        return "desert_outpost"
    if float(cell.get("elevation_m", 0.0)) > 1300.0 or landform in {"mountain_belt", "glacial_valley"}:
        return "mountain_fortress"
    if _has_water_neighbor(cell, cells_by_id):
        return "old_harbor"
    if float(cell.get("ice_thickness_m", 0.0)) > 20.0 or biome == "ice_cap":
        return "glacial_relic"
    return "ruined_city"


def _abandonment_reason(cell: dict[str, Any]) -> str:
    biome = str(cell.get("biome", ""))
    landform = str(cell.get("landform", ""))
    water_body = str(cell.get("water_body_type", "land"))
    if biome in {"cold_desert", "hot_desert"} or float(cell.get("precipitation_mm_y", 0.0)) < 220.0:
        return "aridity"
    if float(cell.get("boundary_convergent", 0.0)) + float(cell.get("boundary_transform", 0.0)) > 0.45:
        return "tectonic_hazard"
    if float(cell.get("ice_thickness_m", 0.0)) > 20.0 or biome == "ice_cap":
        return "glaciation"
    if water_body == "saline_basin" or landform == "salt_flat" or bool(cell.get("is_closed_basin", False)):
        return "salinization"
    if float(cell.get("settlement_score", 0.0)) < 0.48:
        return "trade_decline"
    return "frontier_isolation"


def _preservation(cell: dict[str, Any]) -> float:
    biome = str(cell.get("biome", ""))
    return _clamp(
        0.35
        + (0.20 if biome in {"cold_desert", "hot_desert"} else 0.0)
        + (0.20 if float(cell.get("ice_thickness_m", 0.0)) > 20.0 else 0.0)
        - (0.18 if float(cell.get("precipitation_mm_y", 0.0)) > 1200.0 else 0.0)
    )


def _culture_record_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    exact_keys = (
        "id",
        "language_region_id",
        "homeland_region_id",
        "type",
        "dominant_biome",
        "dominant_resource",
        "settlement_count",
        "sacred_area_count",
        "ruin_count",
        "settlement_ids",
    )
    if any(actual.get(key) != expected[key] for key in exact_keys):
        return False
    tolerances = {
        "area_km2": 0.2,
        "agricultural_area_km2": 0.2,
        "mining_area_km2": 0.2,
        "mean_fertility": 0.001,
        "mean_elevation_m": 0.1,
        "barrier_isolation": 0.002,
        "trade_contact_index": 0.002,
        "migration_pressure": 0.002,
        "continuity_index": 0.002,
        "estimated_age_years": 3.0,
    }
    return all(_close(actual.get(key), expected[key], tolerance) for key, tolerance in tolerances.items())


def _language_record_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    exact_keys = (
        "id",
        "parent_language_region_id",
        "family",
        "lineage_depth",
        "culture_count",
        "settlement_count",
        "culture_ids",
        "phoneme_inventory_size",
    )
    if any(actual.get(key) != expected[key] for key in exact_keys):
        return False
    tolerances = {
        "area_km2": 0.3,
        "barrier_isolation": 0.003,
        "trade_contact_index": 0.003,
        "divergence_age_years": 4.0,
        "change_rate": 0.003,
        "phonological_complexity": 0.004,
        "sound_shift_index": 0.004,
        "inherited_phonology_fraction": 0.004,
    }
    return all(_close(actual.get(key), expected[key], tolerance) for key, tolerance in tolerances.items())


def _site_record_matches(actual: dict[str, Any], expected: dict[str, Any], *, ruin: bool) -> bool:
    exact_keys = ["id", "cell_id", "culture_region_id", "language_region_id", "type"]
    if ruin:
        exact_keys.append("abandonment_reason")
    if any(actual.get(key) != expected[key] for key in exact_keys):
        return False
    numeric = {"significance": 0.003, "lat_deg": 0.001, "lon_deg": 0.001}
    if ruin:
        numeric["preservation_score"] = 0.001
    return all(_close(actual.get(key), expected[key], tolerance) for key, tolerance in numeric.items())


def _replay_valid(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary", {})
    cells = payload.get("cells", [])
    regions = payload.get("political_regions", [])
    borders = payload.get("borders", [])
    flows = payload.get("trade_flows", [])
    settlements = payload.get("settlements", [])
    actual_cultures = payload.get("cultures", [])
    actual_languages = payload.get("language_regions", [])
    actual_sacred = payload.get("sacred_areas", [])
    actual_ruins = payload.get("ruins", [])
    collections = (cells, regions, borders, flows, settlements, actual_cultures, actual_languages, actual_sacred, actual_ruins)
    if not isinstance(summary, dict) or not all(isinstance(value, list) for value in collections) or not cells:
        return False
    if (
        payload.get("culture_region_model") != _culture_model()
        or payload.get("language_region_model") != _language_model()
        or payload.get("cultural_site_model") != _site_model()
        or summary.get("culture_region_model") != CULTURE_REGION_MODEL
        or summary.get("language_region_model") != LANGUAGE_REGION_MODEL
        or summary.get("cultural_site_model") != CULTURAL_SITE_MODEL
    ):
        return False
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    if len(cells_by_id) != len(cells):
        return False
    region_to_culture: dict[int, int] = {}
    cultures: list[dict[str, Any]] = []
    for region in regions:
        culture_id = len(cultures)
        region_id = int(region.get("id", -1))
        region_to_culture[region_id] = culture_id
        cultures.append(
            {
                "id": culture_id,
                "language_region_id": -1,
                "homeland_region_id": region_id,
                "type": _culture_type(region),
                "dominant_biome": str(region.get("dominant_biome", "ocean")),
                "dominant_resource": str(region.get("dominant_resource", "none")),
                "settlement_count": int(region.get("settlement_count", 0)),
                "sacred_area_count": 0,
                "ruin_count": 0,
                "settlement_ids": [int(value) for value in region.get("settlement_ids", [])],
                "area_km2": 0.0,
                "agricultural_area_km2": 0.0,
                "mining_area_km2": 0.0,
                "mean_fertility": 0.0,
                "mean_elevation_m": 0.0,
                "barrier_isolation": 0.0,
                "trade_contact_index": 0.0,
                "migration_pressure": 0.0,
                "continuity_index": 0.0,
                "estimated_age_years": 0.0,
            }
        )
    expected_culture_by_cell: dict[int, int] = {}
    biome_counts = [Counter() for _ in cultures]
    resource_counts = [Counter() for _ in cultures]
    for cell_id, cell in cells_by_id.items():
        culture_id = -1
        if not bool(cell.get("is_water", False)):
            culture_id = region_to_culture.get(int(cell.get("political_region_id", -1)), -1)
        expected_culture_by_cell[cell_id] = culture_id
        if culture_id < 0:
            continue
        culture = cultures[culture_id]
        area = float(cell.get("area_km2", 0.0))
        culture["area_km2"] += area
        culture["mean_fertility"] += float(cell.get("fertility", 0.0)) * area
        culture["mean_elevation_m"] += float(cell.get("elevation_m", 0.0)) * area
        if (
            float(cell.get("fertility", 0.0)) > 0.62
            or str(cell.get("resource", "none")) == "fertile_alluvium"
            or str(cell.get("landform", "")) in {"floodplain", "delta"}
        ):
            culture["agricultural_area_km2"] += area
        if str(cell.get("resource", "none")) in {
            "volcanic_arc_metals",
            "craton_iron_gold",
            "placer_metals",
            "geothermal",
        }:
            culture["mining_area_km2"] += area
        biome_counts[culture_id][str(cell.get("biome", "ocean"))] += 1
        resource_counts[culture_id][str(cell.get("resource", "none"))] += 1

    barrier_sum = [0.0 for _ in cultures]
    border_length = [0.0 for _ in cultures]
    for border in borders:
        first = region_to_culture.get(int(border.get("region_a", -1)), -1)
        second = region_to_culture.get(int(border.get("region_b", -1)), -1)
        if first < 0 or second < 0 or first == second:
            continue
        length = float(border.get("length_km", 0.0))
        weighted = float(border.get("barrier_score", 0.0)) * length
        barrier_sum[first] += weighted
        barrier_sum[second] += weighted
        border_length[first] += length
        border_length[second] += length

    trade_volume = [0.0 for _ in cultures]
    parent = list(range(len(cultures)))
    for flow in flows:
        first = region_to_culture.get(int(flow.get("region_from", -1)), -1)
        second = region_to_culture.get(int(flow.get("region_to", -1)), -1)
        if first < 0 or second < 0:
            continue
        volume = float(flow.get("volume_index", 0.0))
        trade_volume[first] += volume
        trade_volume[second] += volume
        if first != second and volume >= 70.0 and float(flow.get("friction", 0.0)) <= 0.92:
            _union(parent, first, second)

    root_to_language: dict[int, int] = {}
    for culture in cultures:
        root = _find(parent, int(culture["id"]))
        if root not in root_to_language:
            root_to_language[root] = len(root_to_language)
        culture["language_region_id"] = root_to_language[root]

    languages: list[dict[str, Any]] = [
        {
            "id": language_id,
            "parent_language_region_id": -1,
            "family": "riverine",
            "lineage_depth": 0,
            "culture_count": 0,
            "settlement_count": 0,
            "culture_ids": [],
            "area_km2": 0.0,
            "barrier_isolation": 0.0,
            "trade_contact_index": 0.0,
            "divergence_age_years": 0.0,
            "change_rate": 0.0,
            "phoneme_inventory_size": 0,
            "phonological_complexity": 0.0,
            "sound_shift_index": 0.0,
            "inherited_phonology_fraction": 1.0,
        }
        for language_id in range(len(root_to_language))
    ]
    family_area = [defaultdict(float) for _ in languages]
    for culture in cultures:
        culture_id = int(culture["id"])
        area = float(culture["area_km2"])
        if area > 0.0:
            culture["mean_fertility"] /= area
            culture["mean_elevation_m"] /= area
        culture["barrier_isolation"] = barrier_sum[culture_id] / border_length[culture_id] if border_length[culture_id] else 0.0
        culture["trade_contact_index"] = _clamp(trade_volume[culture_id] / (100.0 * max(1, int(culture["settlement_count"]))))
        culture["dominant_biome"] = _native_dominant(biome_counts[culture_id], BIOME_ORDER)
        culture["dominant_resource"] = _native_dominant(resource_counts[culture_id], RESOURCE_ORDER, exclude_none=True)
        culture["migration_pressure"] = _clamp(
            0.18
            + 0.28 * (1.0 - float(culture["barrier_isolation"]))
            + 0.22 * float(culture["trade_contact_index"])
            + 0.16 * (1.0 - float(culture["mean_fertility"]))
            + 0.12 * _clamp(float(culture["mean_elevation_m"]) / 1800.0)
        )
        language = languages[int(culture["language_region_id"])]
        language["culture_count"] += 1
        language["settlement_count"] += int(culture["settlement_count"])
        language["area_km2"] += area
        language["barrier_isolation"] += float(culture["barrier_isolation"]) * area
        language["trade_contact_index"] += float(culture["trade_contact_index"]) * area
        language["culture_ids"].append(culture_id)
        family_area[int(language["id"])][_family_for_culture(str(culture["type"]))] += area

    for language in languages:
        area = float(language["area_km2"])
        if area > 0.0:
            language["barrier_isolation"] /= area
            language["trade_contact_index"] /= area
        language_id = int(language["id"])
        language["family"] = _native_dominant(Counter(family_area[language_id]), FAMILY_ORDER)

    by_family: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for language in languages:
        by_family[str(language["family"])].append((float(language["area_km2"]), int(language["id"])))
    for family in FAMILY_ORDER:
        members = sorted(by_family.get(family, []), key=lambda item: (-item[0], item[1]))
        if not members:
            continue
        root_language = members[0][1]
        for index, (_, language_id) in enumerate(members):
            language = languages[language_id]
            language["parent_language_region_id"] = -1 if index == 0 else root_language
            language["lineage_depth"] = 0 if index == 0 else 1
            language["change_rate"] = _clamp(
                0.16
                + 0.48 * float(language["barrier_isolation"])
                - 0.26 * float(language["trade_contact_index"])
                + 0.08 * min(1.0, float(language["culture_count"]) / 4.0)
            )
            if int(language["parent_language_region_id"]) < 0:
                language["divergence_age_years"] = max(
                    250.0,
                    min(
                        4200.0,
                        900.0
                        + 2100.0 * (1.0 - float(language["change_rate"]))
                        + 380.0 * float(language["barrier_isolation"]),
                    ),
                )
            else:
                language["divergence_age_years"] = max(
                    120.0,
                    min(
                        3200.0,
                        220.0
                        + 1700.0 * float(language["barrier_isolation"])
                        + 820.0 * (1.0 - float(language["trade_contact_index"])),
                    ),
                )
    if len(languages) > 1 and not any(int(language["parent_language_region_id"]) >= 0 for language in languages):
        root_language = max(range(len(languages)), key=lambda index: (float(languages[index]["area_km2"]), -index))
        for language in languages:
            if int(language["id"]) == root_language:
                continue
            language["parent_language_region_id"] = root_language
            language["lineage_depth"] = 1
            language["divergence_age_years"] = max(
                120.0,
                min(
                    3000.0,
                    280.0
                    + 1500.0 * float(language["barrier_isolation"])
                    + 680.0 * (1.0 - float(language["trade_contact_index"])),
                ),
            )
            language["change_rate"] = _clamp(float(language["change_rate"]) + 0.08)

    for language in languages:
        family = str(language["family"])
        base_inventory = BASE_INVENTORY[family]
        parent_id = int(language["parent_language_region_id"])
        if parent_id < 0:
            language["sound_shift_index"] = _clamp(0.04 + 0.16 * float(language["change_rate"]), 0.0, 0.28)
            language["inherited_phonology_fraction"] = 1.0
        else:
            language["sound_shift_index"] = _clamp(
                0.10
                + 0.42 * float(language["change_rate"])
                + 0.28 * _clamp(float(language["divergence_age_years"]) / 3200.0)
                + 0.18 * float(language["barrier_isolation"])
                - 0.14 * float(language["trade_contact_index"])
            )
            language["inherited_phonology_fraction"] = _clamp(1.0 - 0.78 * float(language["sound_shift_index"]))
        parent_inventory = base_inventory
        if parent_id >= 0 and int(languages[parent_id]["phoneme_inventory_size"]) > 0:
            parent_inventory = int(languages[parent_id]["phoneme_inventory_size"])
        innovation = (
            8.0 * float(language["sound_shift_index"])
            + 4.0 * float(language["barrier_isolation"])
            - 3.0 * float(language["trade_contact_index"])
            + 1.6 * float(language["lineage_depth"])
        )
        inventory_value = parent_inventory * (0.72 + 0.28 * float(language["inherited_phonology_fraction"])) + innovation
        language["phoneme_inventory_size"] = max(16, min(58, math.floor(inventory_value + 0.5)))
        language["phonological_complexity"] = _clamp(
            0.20
            + 0.44 * (float(language["phoneme_inventory_size"]) / 58.0)
            + 0.20 * float(language["barrier_isolation"])
            + 0.10 * float(language["sound_shift_index"])
            - 0.10 * float(language["trade_contact_index"])
            + 0.04 * float(language["lineage_depth"])
        )

    expected_language_by_cell = {
        cell_id: (int(cultures[culture_id]["language_region_id"]) if culture_id >= 0 else -1)
        for cell_id, culture_id in expected_culture_by_cell.items()
    }
    for cell_id, cell in cells_by_id.items():
        if (
            int(cell.get("culture_region_id", -2)) != expected_culture_by_cell[cell_id]
            or int(cell.get("language_region_id", -2)) != expected_language_by_cell[cell_id]
        ):
            return False
    for settlement in settlements:
        cell_id = int(settlement.get("cell_id", -1))
        if (
            int(settlement.get("culture_region_id", -2)) != expected_culture_by_cell.get(cell_id, -1)
            or int(settlement.get("language_region_id", -2)) != expected_language_by_cell.get(cell_id, -1)
        ):
            return False

    minimum_separation = 1.4 * math.sqrt(4.0 * math.pi / max(1, len(cells)))
    sacred_candidates = sorted(
        (
            (_sacred_significance(cell, cells_by_id), cell_id)
            for cell_id, cell in cells_by_id.items()
            if not bool(cell.get("is_water", False)) and expected_culture_by_cell[cell_id] >= 0
        ),
        key=lambda item: (-item[0], item[1]),
    )
    sacred_candidates = [item for item in sacred_candidates if item[0] >= 0.30]
    sacred_target = max(2, min(24, len(cultures) * 2))
    sacred_records: list[dict[str, Any]] = []
    for significance, cell_id in sacred_candidates:
        if any(_angular_distance(cells_by_id[cell_id], cells_by_id[int(record["cell_id"])]) < minimum_separation for record in sacred_records):
            continue
        cell = cells_by_id[cell_id]
        culture_id = expected_culture_by_cell[cell_id]
        sacred_records.append(
            {
                "id": len(sacred_records),
                "cell_id": cell_id,
                "culture_region_id": culture_id,
                "language_region_id": int(cultures[culture_id]["language_region_id"]),
                "type": _sacred_type(cell, cells_by_id),
                "significance": significance,
                "lat_deg": float(cell.get("lat_deg", 0.0)),
                "lon_deg": float(cell.get("lon_deg", 0.0)),
            }
        )
        cultures[culture_id]["sacred_area_count"] += 1
        if len(sacred_records) >= sacred_target:
            break

    settlement_cells = {int(settlement.get("cell_id", -1)) for settlement in settlements}
    ruin_candidates = sorted(
        (
            (_ruin_significance(cell, cells_by_id), cell_id)
            for cell_id, cell in cells_by_id.items()
            if not bool(cell.get("is_water", False))
            and expected_culture_by_cell[cell_id] >= 0
            and cell_id not in settlement_cells
        ),
        key=lambda item: (-item[0], item[1]),
    )
    ruin_candidates = [item for item in ruin_candidates if item[0] >= 0.32]
    ruin_target = max(2, min(32, len(cultures) + len(settlements) // 4))
    ruin_records: list[dict[str, Any]] = []
    for significance, cell_id in ruin_candidates:
        if any(_angular_distance(cells_by_id[cell_id], cells_by_id[int(record["cell_id"])]) < minimum_separation for record in ruin_records):
            continue
        cell = cells_by_id[cell_id]
        culture_id = expected_culture_by_cell[cell_id]
        ruin_records.append(
            {
                "id": len(ruin_records),
                "cell_id": cell_id,
                "culture_region_id": culture_id,
                "language_region_id": int(cultures[culture_id]["language_region_id"]),
                "type": _ruin_type(cell, cells_by_id),
                "abandonment_reason": _abandonment_reason(cell),
                "significance": significance,
                "preservation_score": _preservation(cell),
                "lat_deg": float(cell.get("lat_deg", 0.0)),
                "lon_deg": float(cell.get("lon_deg", 0.0)),
            }
        )
        cultures[culture_id]["ruin_count"] += 1
        if len(ruin_records) >= ruin_target:
            break

    for culture in cultures:
        culture["continuity_index"] = _clamp(
            0.30
            + 0.22 * float(culture["barrier_isolation"])
            + 0.18 * float(culture["mean_fertility"])
            + 0.10 * min(1.0, float(culture["settlement_count"]) / 6.0)
            + 0.10 * min(1.0, float(culture["sacred_area_count"]) / 3.0)
            - 0.16 * min(1.0, float(culture["ruin_count"]) / 4.0)
        )
        culture["estimated_age_years"] = max(
            120.0,
            min(
                4200.0,
                420.0
                + 1900.0 * float(culture["continuity_index"])
                + 520.0 * float(culture["barrier_isolation"])
                + 260.0 * min(1.0, float(culture["settlement_count"]) / 8.0),
            ),
        )

    if len(actual_cultures) != len(cultures) or any(
        not _culture_record_matches(actual, expected) for actual, expected in zip(actual_cultures, cultures, strict=True)
    ):
        return False
    if len(actual_languages) != len(languages) or any(
        not _language_record_matches(actual, expected) for actual, expected in zip(actual_languages, languages, strict=True)
    ):
        return False
    if len(actual_sacred) != len(sacred_records) or any(
        not _site_record_matches(actual, expected, ruin=False) for actual, expected in zip(actual_sacred, sacred_records, strict=True)
    ):
        return False
    if len(actual_ruins) != len(ruin_records) or any(
        not _site_record_matches(actual, expected, ruin=True) for actual, expected in zip(actual_ruins, ruin_records, strict=True)
    ):
        return False

    land_cells = sum(1 for cell in cells if not bool(cell.get("is_water", False)))
    expected_summary_counts = {
        "culture_region_count": len(cultures),
        "language_region_count": len(languages),
        "language_lineage_count": sum(1 for language in languages if int(language["parent_language_region_id"]) >= 0),
        "sacred_area_count": len(sacred_records),
        "ruin_count": len(ruin_records),
    }
    if any(int(summary.get(key, -1)) != value for key, value in expected_summary_counts.items()):
        return False
    expected_summary_values = {
        "mean_cultural_continuity": sum(float(culture["continuity_index"]) for culture in cultures) / len(cultures) if cultures else 0.0,
        "mean_language_change_rate": sum(float(language["change_rate"]) for language in languages) / len(languages) if languages else 0.0,
        "mean_phonological_complexity": sum(float(language["phonological_complexity"]) for language in languages) / len(languages) if languages else 0.0,
        "mean_sound_shift_index": sum(float(language["sound_shift_index"]) for language in languages) / len(languages) if languages else 0.0,
        "mean_inherited_phonology_fraction": sum(float(language["inherited_phonology_fraction"]) for language in languages) / len(languages) if languages else 0.0,
        "largest_culture_area_km2": max((float(culture["area_km2"]) for culture in cultures), default=0.0),
        "culturally_assigned_land_fraction": sum(1 for value in expected_culture_by_cell.values() if value >= 0) / land_cells if land_cells else 0.0,
    }
    return all(_close(summary.get(key), value, 0.005 if "area_km2" not in key else 0.5) for key, value in expected_summary_values.items())


def validate_cultural_geography_replay(payload: dict[str, Any]) -> list[str]:
    return [] if _replay_valid(payload) else ["cultural geography model or causal replay invalid"]
