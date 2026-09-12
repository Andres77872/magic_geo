"""Independent v2 culture/site/language replay over actual available native inputs.

The unchanged scalar/geometry helpers and physical replay equations come from
our independent v1 validator. This module constructs its own expected records;
it never fills null outputs or relabels a payload to invoke a legacy validator.
"""
from __future__ import annotations
import math
from collections import Counter, defaultdict
from typing import Any
from .native_social_availability import require_native_social_availability
from .cultural_geography_validation import (
    BIOME_ORDER, RESOURCE_ORDER, FAMILY_ORDER, BASE_INVENTORY, _clamp,
    _culture_type, _native_dominant, _union, _find, _family_for_culture,
    _sacred_significance, _angular_distance, _sacred_type,
    _ruin_significance, _ruin_type, _abandonment_reason, _preservation,
)

# Literal independent expected contracts. No producer metadata/math import.
EXPECTED_MODELS = {'cultural_site_model': {'abandonment_reason_model': 'aridity_tectonic_glaciation_salinization_trade_frontier_priority_v1',
                         'availability_policy': 'independent_sacred_selection_complete_actual_ruin_candidates_before_global_rank',
                         'candidate_order': 'descending_raw_significance_then_cell_id_v1',
                         'deterministic': True,
                         'minimum_angular_separation_model': '1_4_sqrt_4pi_div_cell_count_radians_v1',
                         'model_limitation': 'ranked_diagnostic_sites_without_settlement_lifecycle_archaeology_or_temporal_land_use',
                         'model_type': 'causal_terrain_culture_ranked_sacred_ruin_sites_v2',
                         'preservation_model': 'base_desert_ice_minus_high_precipitation_v1',
                         'ruin_candidate_threshold': 0.32,
                         'ruin_significance_model': 'settlement_fertility_water_resource_times_abandonment_pressure_v1',
                         'ruin_target_model': 'clamp_culture_count_plus_floor_settlement_count_div_4_2_32_v1',
                         'ruin_type_model': 'mine_desert_mountain_harbor_glacial_city_priority_v1',
                         'sacred_candidate_threshold': 0.3,
                         'sacred_significance_model': 'terrain_water_geothermal_desert_fertility_coast_relief_weighted_index_v1',
                         'sacred_target_model': 'clamp_two_per_culture_2_24_v1',
                         'sacred_type_model': 'volcanic_mountain_water_grove_desert_coast_priority_v1',
                         'source_culture_membership_model': 'one_culture_per_political_region_in_record_order_v1',
                         'source_fertility_serialization_decimals': 8,
                         'source_native_social_availability_model': 'native_settlement_source_complete_social_estimates_v1',
                         'source_political_region_model': 'causal_capital_barrier_partition_political_regions_v1',
                         'source_settlement_model': 'causal_native_score_local_max_separated_settlement_selection_v3'},
 'culture_region_model': {'age_model': 'continuity_barrier_settlement_bounded_estimated_age_v1',
                          'age_parameters': {'barrier_years': 520.0,
                                             'base_years': 420.0,
                                             'continuity_years': 1900.0,
                                             'maximum_years': 4200.0,
                                             'minimum_years': 120.0,
                                             'settlement_scale': 8.0,
                                             'settlement_years': 260.0},
                          'agricultural_area_model': 'fertility_or_alluvial_resource_or_floodplain_delta_v1',
                          'agricultural_fertility_threshold': 0.62,
                          'agricultural_fertility_threshold_semantics': 'raw_strict_greater_than_v1',
                          'availability_policy': 'retain_independent_descriptors_null_incomplete_global_ruin_count_continuity_age',
                          'barrier_isolation_model': 'border_length_weighted_mean_barrier_score_v1',
                          'cell_assignment_model': 'nonwater_political_region_to_homeland_culture_v1',
                          'continuity_model': 'barrier_fertility_settlement_sacred_ruin_weighted_index_v1',
                          'continuity_parameters': {'barrier_weight': 0.22,
                                                    'base': 0.3,
                                                    'fertility_weight': 0.18,
                                                    'ruin_penalty_weight': 0.16,
                                                    'ruin_scale': 4.0,
                                                    'sacred_area_scale': 3.0,
                                                    'sacred_area_weight': 0.1,
                                                    'settlement_scale': 6.0,
                                                    'settlement_weight': 0.1},
                          'culture_type_model': 'maritime_river_mountain_desert_mining_boreal_forest_agrarian_priority_v1',
                          'deterministic': True,
                          'dominant_field_model': 'count_then_native_enum_order_with_nonzero_resource_v1',
                          'homeland_model': 'one_culture_per_political_region_in_record_order_v1',
                          'migration_pressure_model': 'barrier_trade_fertility_elevation_weighted_index_v1',
                          'migration_pressure_parameters': {'base': 0.18,
                                                            'elevation_scale_m': 1800.0,
                                                            'elevation_weight': 0.12,
                                                            'fertility_deficit_weight': 0.16,
                                                            'permeability_weight': 0.28,
                                                            'trade_weight': 0.22},
                          'mining_area_model': 'metal_placer_or_geothermal_resource_cells_v1',
                          'model_limitation': 'static_political_homelands_without_cultural_diffusion_identity_change_or_population_feedback',
                          'model_type': 'causal_political_homeland_barrier_trade_culture_regions_v2',
                          'mountain_mean_elevation_threshold_m': 1100.0,
                          'source_cultural_site_model': 'causal_terrain_culture_ranked_sacred_ruin_sites_v2',
                          'source_fertility_serialization_decimals': 8,
                          'source_native_social_availability_model': 'native_settlement_source_complete_social_estimates_v1',
                          'source_political_region_model': 'causal_capital_barrier_partition_political_regions_v1',
                          'source_settlement_model': 'causal_native_score_local_max_separated_settlement_selection_v3',
                          'source_trade_flow_model': 'causal_route_endpoint_complement_trade_flows_v1',
                          'trade_contact_model': 'incident_trade_volume_per_100_per_settlement_capped_v1'},
 'language_region_model': {'base_phoneme_inventory_by_family': {'arid': 24,
                                                                'coastal': 31,
                                                                'frontier': 30,
                                                                'highland': 34,
                                                                'lowland': 29,
                                                                'riverine': 27},
                           'change_rate_model': 'barrier_trade_culture_count_weighted_index_v1',
                           'child_divergence_model': 'barrier_plus_inverse_trade_bounded_years_v1',
                           'deterministic': True,
                           'fallback_child_change_rate_bonus': 0.08,
                           'family_model': 'culture_type_family_area_dominance_native_enum_tie_v1',
                           'lineage_model': 'largest_area_family_root_then_global_largest_fallback_v1',
                           'model_limitation': 'diagnostic_language_union_and_single_generation_lineage_without_speaker_interaction_or_observed_linguistic_calibration',
                           'model_type': 'causal_trade_union_family_lineage_phonology_v1',
                           'phonology_model': 'parent_inventory_inheritance_shift_isolation_contact_lineage_v1',
                           'record_order': 'union_root_first_culture_order_v1',
                           'root_divergence_model': 'inverse_change_rate_plus_barrier_bounded_years_v1',
                           'union_friction_maximum': 0.92,
                           'union_model': 'minimum_root_union_on_high_volume_low_friction_interregional_trade_v1',
                           'union_volume_threshold': 70.0}}


def exact(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(exact(actual[k], v) for k, v in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def number(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("finite nonboolean replay number required")
    return float(value)


def close(actual: Any, expected: float, tolerance: float) -> bool:
    return abs(number(actual) - expected) <= tolerance


def record_matches(actual: dict[str, Any], expected: dict[str, Any], tolerances: dict[str, float]) -> bool:
    if type(actual) is not dict:
        return False
    for key, value in expected.items():
        if key not in actual:
            return False
        if key in tolerances and value is not None:
            if not close(actual[key], value, tolerances[key]):
                return False
        elif not exact(actual[key], value):
            return False
    return True


CULTURE_TOLERANCES = {
    "area_km2": .2, "agricultural_area_km2": .2, "mining_area_km2": .2,
    "mean_fertility": .001, "mean_elevation_m": .1, "barrier_isolation": .002,
    "trade_contact_index": .002, "migration_pressure": .002,
    "continuity_index": .002, "estimated_age_years": 3.,
}
LANGUAGE_TOLERANCES = {
    "area_km2": .3, "barrier_isolation": .003, "trade_contact_index": .003,
    "divergence_age_years": 4., "change_rate": .003,
    "phonological_complexity": .004, "sound_shift_index": .004,
    "inherited_phonology_fraction": .004,
}
SITE_TOLERANCES = {"significance": .003, "lat_deg": .001, "lon_deg": .001, "preservation_score": .001}


def strict_sources(payload: dict[str, Any]) -> None:
    # Required consumed fields only; unrelated later-layer additions are allowed.
    schemas = {
        "cells": (("id", "political_region_id", "culture_region_id", "language_region_id"),
                  ("area_km2", "fertility", "elevation_m", "lat_deg", "lon_deg", "precipitation_mm_y", "ice_thickness_m", "boundary_convergent", "boundary_transform", "settlement_score"),
                  ("biome", "resource", "landform", "water_body_type"), ("is_water", "is_lake", "is_river", "is_closed_basin", "settlement_climate_supported")),
        "political_regions": (("id", "capital_settlement_id", "settlement_count", "route_count"), ("mean_elevation_m", "barrier_pressure"), ("type", "dominant_biome", "dominant_resource"), ()),
        "settlements": (("id", "cell_id", "region_id", "culture_region_id", "language_region_id"), (), (), ()),
        "borders": (("id", "region_a", "region_b"), ("length_km", "barrier_score"), (), ()),
        "trade_flows": (("id", "region_from", "region_to", "from", "to"), ("volume_index", "friction"), (), ()),
    }
    for collection, (integers, numbers, strings, booleans) in schemas.items():
        rows = payload.get(collection)
        if type(rows) is not list:
            raise ValueError("complete replay sources required: " + collection)
        for index, row in enumerate(rows):
            if type(row) is not dict or type(row.get("id")) is not int or row["id"] != index:
                raise ValueError("indexed replay sources required: " + collection)
            if any(type(row.get(key)) is not int for key in integers):
                raise ValueError("typed replay integer source required")
            for key in numbers:
                number(row.get(key))
            if any(type(row.get(key)) is not str for key in strings) or any(type(row.get(key)) is not bool for key in booleans):
                raise ValueError("typed replay descriptor source required")
    for region in payload["political_regions"]:
        ids = region.get("settlement_ids")
        if type(ids) is not list or any(type(i) is not int or i not in range(len(payload["settlements"])) for i in ids):
            raise ValueError("typed regional settlement membership required")
    for cell in payload["cells"]:
        if cell["area_km2"] < 0 or cell["biome"] not in BIOME_ORDER or cell["resource"] not in RESOURCE_ORDER:
            raise ValueError("invalid native source area/enum")


def _replay_valid(payload: dict[str, Any]) -> bool:
    require_native_social_availability(payload)
    for key, expected in EXPECTED_MODELS.items():
        if not exact(payload.get(key), expected) or payload["summary"].get(key) != expected["model_type"]:
            return False
    return cultural_equations_valid(payload)


def cultural_equations_valid(payload: dict[str, Any]) -> bool:
    """Scoped stage-equation comparison; public validation also requires source headers.

    Used for retained native stage fixtures with prescribed political/site inputs.
    This is not an entry point for declaring a complete public world valid.
    """
    envelope = payload["native_social_availability"]
    strict_sources(payload)
    summary = payload["summary"]
    cells, regions, borders, flows, settlements = (payload[k] for k in ("cells", "political_regions", "borders", "trade_flows", "settlements"))
    actual_cultures, actual_languages, actual_sacred, actual_ruins = (payload[k] for k in ("cultures", "language_regions", "sacred_areas", "ruins"))
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
    eligible_ruins = [cell for cell_id, cell in cells_by_id.items()
        if not cell["is_water"] and expected_culture_by_cell[cell_id] >= 0 and cell_id not in settlement_cells]
    unavailable_ids = sorted(cell["id"] for cell in eligible_ruins if not (cell["is_lake"] or cell["settlement_climate_supported"]))
    complete_ruins = not unavailable_ids
    local_candidates = Counter(expected_culture_by_cell[cell["id"]] for cell in eligible_ruins)
    local_supported = Counter(expected_culture_by_cell[cell["id"]] for cell in eligible_ruins if cell["id"] not in unavailable_ids)
    expected_coverage = {"ruin_inference_available": complete_ruins,
        "ruin_candidate_cell_count": len(eligible_ruins),
        "ruin_supported_candidate_cell_count": len(eligible_ruins)-len(unavailable_ids),
        "ruin_unavailable_cell_ids": unavailable_ids}
    if any(not exact(envelope[key], value) for key, value in expected_coverage.items()):
        return False
    ruin_candidates = sorted(
        (
            (_ruin_significance(cell, cells_by_id), cell_id)
            for cell_id, cell in cells_by_id.items()
            if complete_ruins and not bool(cell.get("is_water", False))
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
        culture_id = culture["id"]
        available = complete_ruins or local_candidates[culture_id] == 0
        culture.update(ruin_candidate_cell_count=local_candidates[culture_id],
            ruin_supported_candidate_cell_count=local_supported[culture_id],
            recorded_ruin_count=culture["ruin_count"], ruin_count_available=available,
            continuity_estimate_available=available)
        if not available:
            culture["ruin_count"] = culture["continuity_index"] = culture["estimated_age_years"] = None
            continue
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
        not record_matches(actual, expected, CULTURE_TOLERANCES) for actual, expected in zip(actual_cultures, cultures, strict=True)
    ):
        return False
    if len(actual_languages) != len(languages) or any(
        not record_matches(actual, expected, LANGUAGE_TOLERANCES) for actual, expected in zip(actual_languages, languages, strict=True)
    ):
        return False
    if len(actual_sacred) != len(sacred_records) or any(
        not record_matches(actual, expected, SITE_TOLERANCES) for actual, expected in zip(actual_sacred, sacred_records, strict=True)
    ):
        return False
    if len(actual_ruins) != len(ruin_records) or any(
        not record_matches(actual, expected, SITE_TOLERANCES) for actual, expected in zip(actual_ruins, ruin_records, strict=True)
    ):
        return False

    land_cells = sum(1 for cell in cells if not bool(cell.get("is_water", False)))
    expected_summary_counts = {
        "culture_region_count": len(cultures),
        "language_region_count": len(languages),
        "language_lineage_count": sum(1 for language in languages if int(language["parent_language_region_id"]) >= 0),
        "sacred_area_count": len(sacred_records),
        "ruin_count": len(ruin_records) if complete_ruins else None,
        "recorded_ruin_count": len(ruin_records),
        "available_culture_continuity_count": sum(c["continuity_estimate_available"] for c in cultures),
    }
    if any(not exact(summary.get(key), value) for key, value in expected_summary_counts.items()):
        return False
    expected_summary_values = {
        "mean_cultural_continuity": sum(culture["continuity_index"] for culture in cultures) / len(cultures) if cultures and all(c["continuity_estimate_available"] for c in cultures) else None,
        "mean_language_change_rate": sum(float(language["change_rate"]) for language in languages) / len(languages) if languages else 0.0,
        "mean_phonological_complexity": sum(float(language["phonological_complexity"]) for language in languages) / len(languages) if languages else 0.0,
        "mean_sound_shift_index": sum(float(language["sound_shift_index"]) for language in languages) / len(languages) if languages else 0.0,
        "mean_inherited_phonology_fraction": sum(float(language["inherited_phonology_fraction"]) for language in languages) / len(languages) if languages else 0.0,
        "largest_culture_area_km2": max((float(culture["area_km2"]) for culture in cultures), default=0.0),
        "culturally_assigned_land_fraction": sum(1 for value in expected_culture_by_cell.values() if value >= 0) / land_cells if land_cells else 0.0,
    }
    if any(not (exact(summary.get(key), None) if value is None else close(summary.get(key), value, .005 if "area_km2" not in key else .5)) for key, value in expected_summary_values.items()):
        return False
    flags = summary.get("native_social_summary_availability")
    return type(flags) is dict and exact(flags.get("ruin_count"), complete_ruins) and exact(flags.get("mean_cultural_continuity"), bool(cultures) and all(c["continuity_estimate_available"] for c in cultures))



def validate_native_cultural_availability(payload: dict[str, Any]) -> list[str]:
    try:
        valid = _replay_valid(payload)
    except (IndexError, KeyError, TypeError, ValueError, OverflowError):
        valid = False
    return [] if valid else ["native cultural availability model or causal replay invalid"]
