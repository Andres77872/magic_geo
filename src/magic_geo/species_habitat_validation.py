"""Independent prerequisites for the declared species habitat-support model.

Exact v2 archives retain their declared habitat/input scope. V3 additionally
replays the ten scalar scores, parent availability and connected candidate
coverage. These are empirical proxy checks, not universal species survival
limits. No producer eligibility helper or constant is imported at runtime.
"""
from __future__ import annotations

import math
from typing import Any

from .marine_distance_validation import require_marine_distance


_TERRESTRIAL_GUILDS = {
    "canopy_tree", "grassland_grazer", "desert_specialist",
    "alpine_tundra_specialist", "large_predator",
}
_MARINE_TYPES = {"ocean", "continental_shelf", "inland_sea"}
_AQUATIC_TYPES = _MARINE_TYPES | {"fresh_lake"}
_LEGACY_GUILDS = {"reef_builder", "wetland_amphibian", "mangrove_coastal_bird"}
_EXPECTED_MODEL = {
    "model": "heuristic_species_habitat_support_v2",
    "aquatic_selector": "is_water_or_is_lake_or_fishery_water_body_type",
    "terrestrial_guilds": sorted(_TERRESTRIAL_GUILDS),
    "marine_water_body_types": sorted(_MARINE_TYPES),
    "freshwater_water_body_types": ["fresh_lake"],
    "freshwater_river_policy": "is_river_on_non_aquatic_non_saline_land",
    "standing_water_fish_input_policy": "requires_current_climate_support_true_primary_and_derived_fishery_flags_and_finite_indices",
    "river_fishery_input_policy": "omit_fishery_term_regardless_upstream_numeric_diagnostic",
    "fishery_habitat_evidence": "upstream_numeric_diagnostic_not_consumed_river_resource",
    "unsupported_fish_score_policy": "numeric_zero_with_false_score_support_flag",
    "temperature_input_policy": "finite_numeric_annual_temperature_required_before_mutation",
    "productivity_input_policy": "absent_is_unavailable_present_requires_finite_numeric_before_mutation",
    "fish_temperature_proxy": "annual_air_temperature_c",
    "fish_temperature_support_c": {
        "freshwater_fish": {"lower_exclusive": -10.0, "upper_exclusive": 38.0},
        "marine_fish": {"lower_exclusive": -11.0, "upper_exclusive": 37.0},
    },
    "fish_temperature_support_policy": "positive_support_of_existing_guild_temperature_windows_not_species_survival_limits",
    "habitat_scope": "empirical_resident_habitat_not_species_survival_or_migration",
    "unmigrated_guild_policy": "reef_builder_wetland_amphibian_mangrove_coastal_bird_legacy_scores",
}


def _finite(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _index(value: Any) -> bool:
    return _finite(value) and 0.0 <= value <= 1.0


def _habitat(cell: dict[str, Any]) -> tuple[bool, bool, bool, bool]:
    water_type = cell.get("water_body_type", "land")
    marine = isinstance(water_type, str) and water_type in _MARINE_TYPES
    freshwater = water_type == "fresh_lake"
    aquatic = bool(cell.get("is_water", False)) or bool(cell.get("is_lake", False)) or (
        isinstance(water_type, str) and water_type in _AQUATIC_TYPES
    )
    river = bool(cell.get("is_river", False)) and not aquatic and water_type != "saline_basin"
    return aquatic, freshwater or river, marine, river


def _validate_v2(world: dict[str, Any]) -> list[str]:
    """Validate v2 prerequisites, preserving the absent-model legacy path."""
    if "species_ranges_model" not in world:
        return []
    model = world["species_ranges_model"]
    if not isinstance(model, dict) or model.keys() != _EXPECTED_MODEL.keys():
        return ["species habitat model metadata is missing fields, malformed, or unsupported"]
    errors = [f"species habitat model metadata has invalid {key}"
              for key, expected in _EXPECTED_MODEL.items()
              if type(model[key]) is not type(expected) or model[key] != expected]
    if errors:
        return errors

    cells = world.get("cells")
    if not isinstance(cells, list) or any(not isinstance(cell, dict) for cell in cells):
        return ["species habitat support requires a valid cell list"]
    cells_by_id: dict[int, dict[str, Any]] = {}
    aquatic_by_id: dict[int, bool] = {}
    allowed_by_id: dict[int, set[str]] = {}
    for cell in cells:
        cell_id = cell.get("id")
        if type(cell_id) is not int or cell_id < 0 or cell_id in cells_by_id:
            errors.append("species habitat support requires unique nonnegative integer cell IDs")
            continue
        cells_by_id[cell_id] = cell
        temperature = cell.get("temperature_c")
        annual_valid = _finite(temperature)
        if not annual_valid:
            errors.append(f"species habitat cell {cell_id}: annual temperature must be finite numeric input")
        for field in ("primary_productivity_index", "fishery_productivity_index"):
            if field in cell and not _finite(cell[field]):
                errors.append(f"species habitat cell {cell_id}: present {field} must be finite numeric input")
        aquatic, freshwater, marine, river = _habitat(cell)
        aquatic_by_id[cell_id] = aquatic
        # Recompute support from the raw annual input as well as exact upstream
        # flags. A forged True flag cannot authorize an out-of-domain sentinel.
        standing_inputs = (
            annual_valid and -16.0 < temperature < 44.0
            and cell.get("aquatic_primary_climate_supported") is True
            and cell.get("fishery_productivity_supported") is True
            and _index(cell.get("primary_productivity_index"))
            and _index(cell.get("fishery_productivity_index"))
        )
        freshwater_supported = freshwater and annual_valid and -10.0 < temperature < 38.0 and (
            annual_valid and _index(cell.get("primary_productivity_index")) if river else standing_inputs
        )
        marine_supported = marine and annual_valid and -11.0 < temperature < 37.0 and standing_inputs
        expected_flags = {
            "species_terrestrial_habitat_eligible": not aquatic,
            "species_freshwater_habitat_eligible": freshwater,
            "species_marine_habitat_eligible": marine,
            "species_freshwater_fish_score_supported": freshwater_supported,
            "species_marine_fish_score_supported": marine_supported,
        }
        for field, expected in expected_flags.items():
            if type(cell.get(field)) is not bool or cell[field] != expected:
                errors.append(f"species habitat cell {cell_id}: {field} mismatch")
        mode = "river_inapplicable_omitted" if river else "standing_water_required" if freshwater else "not_applicable"
        if cell.get("species_freshwater_fishery_input_mode") != mode:
            errors.append(f"species habitat cell {cell_id}: species_freshwater_fishery_input_mode mismatch")
        allowed = set(_LEGACY_GUILDS)
        if not aquatic:
            allowed.update(_TERRESTRIAL_GUILDS)
        if freshwater_supported:
            allowed.add("freshwater_fish")
        if marine_supported:
            allowed.add("marine_fish")
        allowed_by_id[cell_id] = allowed if annual_valid else set()
        dominant = cell.get("dominant_species_guild")
        if not isinstance(dominant, str) or (dominant != "none" and dominant not in allowed_by_id[cell_id]):
            errors.append(f"species habitat cell {cell_id}: dominant guild {dominant} lacks habitat or input support")

    records = world.get("species_range_records")
    if not isinstance(records, list):
        errors.append("species habitat support requires a valid range record list")
        return errors
    for record in records:
        if not isinstance(record, dict):
            errors.append("species habitat support requires valid range records")
            continue
        record_id, guild = record.get("id"), record.get("guild_type")
        ids = record.get("cell_ids")
        if not isinstance(ids, list) or not ids or any(type(i) is not int or i not in cells_by_id for i in ids):
            errors.append(f"species habitat range {record_id}: invalid member cell IDs")
            continue
        for cell_id in ids:
            if not isinstance(guild, str) or guild not in allowed_by_id[cell_id]:
                errors.append(f"species habitat range {record_id}: guild {guild} lacks habitat or input support at cell {cell_id}")
        evidence = record.get("habitat_evidence")
        water_fraction = sum(aquatic_by_id[i] for i in ids) / len(ids)
        if not isinstance(evidence, dict) or not _index(evidence.get("water_cell_fraction")) or abs(
            evidence["water_cell_fraction"] - water_fraction
        ) > 0.0000011:
            errors.append(f"species habitat range {record_id}: water_cell_fraction does not match shared aquatic selector")
    return errors


# Independent literal copy of the declared v3 contract, not a producer import.
_EXPECTED_V3_MODEL = {'model': 'heuristic_species_parent_support_v3',
 'parent_model': 'heuristic_ecosystem_climate_support_v4',
 'aquatic_selector': 'is_water_or_is_lake_or_fishery_water_body_type',
 'terrestrial_guilds': ['alpine_tundra_specialist',
                        'canopy_tree',
                        'desert_specialist',
                        'grassland_grazer',
                        'large_predator'],
 'marine_water_body_types': ['continental_shelf', 'inland_sea', 'ocean'],
 'freshwater_water_body_types': ['fresh_lake'],
 'freshwater_river_policy': 'is_river_on_non_aquatic_non_saline_land',
 'other_habitat_policy': 'reef_builder_wetland_amphibian_mangrove_coastal_bird_existing_unconditional_applicability',
 'temperature_source': 'annual_surface_air_climate_proxy',
 'own_temperature_support_c': {'canopy_tree': {'lower_exclusive': -6.0, 'upper_exclusive': 42.0},
                               'grassland_grazer': {'lower_exclusive': -6.0, 'upper_exclusive': 42.0},
                               'alpine_tundra_specialist': {'lower_exclusive': None, 'upper_exclusive': 8.0},
                               'wetland_amphibian': {'lower_exclusive': 11.0, 'upper_exclusive': 39.0},
                               'freshwater_fish': {'lower_exclusive': -10.0, 'upper_exclusive': 38.0},
                               'marine_fish': {'lower_exclusive': -11.0, 'upper_exclusive': 37.0},
                               'reef_builder': {'lower_exclusive': 11.0, 'upper_exclusive': 39.0},
                               'mangrove_coastal_bird': {'lower_exclusive': 11.0, 'upper_exclusive': 39.0}},
 'guilds_without_own_temperature_window': ['desert_specialist', 'large_predator'],
 'own_temperature_policy': 'positive_support_of_existing_guild_terms_not_survival_limits_or_habitat_absence',
 'score_parent_inputs': {'canopy_tree': ['primary', 'biomass', 'forest', 'disturbance'],
                         'grassland_grazer': ['primary', 'richness', 'biomass', 'disturbance'],
                         'desert_specialist': ['richness'],
                         'alpine_tundra_specialist': ['richness'],
                         'large_predator': ['richness', 'biomass', 'primary', 'disturbance'],
                         'wetland_amphibian': ['richness'],
                         'freshwater_fish': ['primary', 'standing_fishery_if_applicable'],
                         'marine_fish': ['primary', 'fishery'],
                         'reef_builder': ['reef_growth', 'fishery'],
                         'mangrove_coastal_bird': ['richness', 'disturbance']},
 'parent_input_policy': 'exact_true_availability_and_finite_numeric_unit_interval_supported_zero_valid',
 'aquatic_biomass_policy': 'known_structural_zero_for_common_descriptors_not_terrestrial_score_habitat',
 'river_fishery_input_policy': 'omit_standing_fishery_term_regardless_numeric_value_require_supported_primary',
 'reef_growth_input_policy': 'finite_numeric_unit_interval_upstream_reef_descriptor_no_new_habitat_claim',
 'confidence_inputs': ['primary', 'richness', 'disturbance', 'biome_confidence', 'wetland', 'reef_growth'],
 'endemism_inputs': ['disturbance', 'wetland', 'reef_growth'],
 'common_record_policy': 'requires_supported_primary_richness_disturbance_confidence_endemism_and_finite_common_descriptors',
 'record_evidence_policy': 'fishery_mean_only_when_all_members_consume_supported_fishery_forest_mean_only_for_canopy_tree',
 'unsupported_estimate_policy': 'numeric_zero_with_false_support_flag_not_species_absence',
 'composition_denominator': 'existing_habitat_applicability_only_own_temperature_reduces_support',
 'composition_status_policy': 'not_applicable_if_no_habitats_unavailable_if_no_supported_scores_complete_if_all_habitat_scores_supported_otherwise_partial',
 'dominance_policy': 'maximum_supported_score_only_none_below_0.25_or_unavailable',
 'range_policy': 'supported_score_at_least_0.46_and_supported_common_record_descriptors_connected_mesh_components',
 'summary_policy': 'all_cell_means_include_unavailable_zero_sentinels_with_support_and_composition_counts',
 'source_input_policy': 'finite_numeric_annual_and_present_numeric_descriptors_required_before_mutation_absent_biological_inputs_unavailable',
 'scope': 'empirical_resident_habitat_scores_not_population_survival_migration_or_global_habitability'}

_EXPECTED_V4_MODEL = {
    **_EXPECTED_V3_MODEL,
    "model": "heuristic_species_parent_support_v4",
    "parent_model": "heuristic_ecosystem_climate_support_v5",
    "source_input_policy": "explicit_finite_numeric_annual_and_consumed_descriptors_typed_habitat_categories_and_reciprocal_complete_graph_before_publication",
    "source_link_policy": "explicit_unique_natural_source_records_reciprocal_cell_membership_basin_ids_are_native_outlet_cells",
}

_V3_NUMERIC_INPUTS = (
    "primary_productivity_index", "fishery_productivity_index", "vegetation_biomass_index",
    "species_richness_index", "ecosystem_disturbance_pressure_index", "forest_growth_index",
    "reef_growth_index", "wetland_extent_index", "biome_confidence_index",
    "precipitation_mm_y", "seasonal_aridity_index", "soil_moisture_index",
    "wetland_hydrology_index", "river_channel_width_m", "river_channel_depth_m",
    "elevation_m", "ice_thickness_m", "permafrost_extent_index",
    "distance_to_marine_water_km", "area_km2", "lat_deg", "lon_deg",
)


def _v3_state(cell: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bool]]:
    aquatic, freshwater, marine, river = _habitat(cell)
    temperature = cell["temperature_c"]
    habitat = {guild: not aquatic for guild in _TERRESTRIAL_GUILDS}
    habitat.update(freshwater_fish=freshwater, marine_fish=marine,
                   reef_builder=True, wetland_amphibian=True, mangrove_coastal_bird=True)
    parents = {}
    for key, flag, source in (
        ("primary", "primary_productivity_supported", "primary_productivity_index"),
        ("biomass", "vegetation_biomass_supported", "vegetation_biomass_index"),
        ("forest", "forest_growth_supported", "forest_growth_index"),
        ("richness", "species_richness_supported", "species_richness_index"),
        ("disturbance", "ecosystem_disturbance_pressure_supported", "ecosystem_disturbance_pressure_index"),
        ("fishery", "fishery_productivity_supported", "fishery_productivity_index"),
    ):
        parents[key] = cell.get(flag) is True and _index(cell.get(source))
    parents["biomass"] = parents["biomass"] or (aquatic and _index(cell.get("vegetation_biomass_index")) and cell["vegetation_biomass_index"] == 0)
    for key, source in (("reef_growth", "reef_growth_index"), ("wetland", "wetland_extent_index"), ("biome_confidence", "biome_confidence_index")):
        parents[key] = _index(cell.get(source))
    parents["standing_fishery_if_applicable"] = river or parents["fishery"]
    fields = {
        "species_terrestrial_habitat_eligible": not aquatic,
        "species_freshwater_habitat_eligible": freshwater,
        "species_marine_habitat_eligible": marine,
        "species_freshwater_fishery_input_mode": "river_inapplicable_omitted" if river else "standing_water_required" if freshwater else "not_applicable",
    }
    for guild, dependencies in _EXPECTED_V3_MODEL["score_parent_inputs"].items():
        interval = _EXPECTED_V3_MODEL["own_temperature_support_c"].get(guild, {})
        lower, upper = interval.get("lower_exclusive"), interval.get("upper_exclusive")
        thermal = (lower is None or temperature > lower) and (upper is None or temperature < upper)
        fields[f"species_{guild}_score_supported"] = habitat[guild] and thermal and all(parents[key] for key in dependencies)
    fields["species_composition_confidence_supported"] = all(parents[key] for key in ("primary", "richness", "disturbance", "biome_confidence", "wetland", "reef_growth"))
    fields["species_endemism_supported"] = all(parents[key] for key in ("disturbance", "wetland", "reef_growth"))
    fields["species_record_descriptors_supported"] = fields["species_composition_confidence_supported"] and fields["species_endemism_supported"] and all(parents[key] for key in ("primary", "richness", "disturbance"))
    applicable = sum(habitat.values())
    supported = sum(fields[f"species_{guild}_score_supported"] for guild in habitat)
    fields["species_applicable_guild_count"] = applicable
    fields["species_supported_guild_count"] = supported
    fields["species_composition_status"] = "not_applicable" if not applicable else "unavailable" if not supported else "complete" if supported == applicable else "partial"
    return fields, habitat


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def _v3_scores(cell: dict[str, Any], support: dict[str, Any]) -> dict[str, float]:
    """Independent scalar score equations; no producer helper/constant import."""
    def value(key, default=0.0):
        return float(cell.get(key, default))
    def unit(key):
        return _bounded(value(key))
    t = value("temperature_c")
    biome = cell.get("biome", "unknown")
    water = cell.get("water_body_type", "land")
    p, b, r, d, f, fish = (unit(key) for key in (
        "primary_productivity_index", "vegetation_biomass_index", "species_richness_index",
        "ecosystem_disturbance_pressure_index", "forest_growth_index", "fishery_productivity_index"))
    a, m, wet, reef = (unit(key) for key in ("seasonal_aridity_index", "soil_moisture_index", "wetland_extent_index", "reef_growth_index"))
    ice = _bounded(value("ice_thickness_m") / 800.0)
    rain = max(0.0, value("precipitation_mm_y"))
    temperate, warm = _bounded(1.0 - abs(t - 18.0) / 24.0), _bounded(1.0 - abs(t - 25.0) / 14.0)
    forest = 0.24 if "forest" in str(biome) else 0.0
    grass = 0.24 if biome in ("savanna", "temperate_grassland", "mediterranean_scrub") else 0.0
    desert = 0.30 if biome in ("hot_desert", "cold_desert") else 0.0
    alpine = 0.28 if biome in ("tundra", "alpine", "ice_cap") else 0.0
    river = support["species_freshwater_fishery_input_mode"] == "river_inapplicable_omitted"
    freshwater = 0.30 if water == "fresh_lake" else 0.22 if river else 0.0
    amphibian_bonus = 0.30 if water in ("fresh_lake", "inland_sea") else 0.22 if bool(cell.get("is_river", False)) else 0.0
    marine = 0.30 if water in ("ocean", "continental_shelf", "inland_sea") else 0.0
    reef_bonus = 0.34 if str(cell.get("reef_type", "none")) != "none" else 0.0
    mangrove = 0.34 if cell.get("biome_ecotone_type", "none") == "mangrove" or cell.get("wetland_system_type", "") == "mangrove" else 0.0
    scores = {
        "canopy_tree": forest + p*.24 + b*.28 + f*.20 + m*.12 + temperate*.10 - d*.14 - a*.08 - ice*.26,
        "grassland_grazer": grass + p*.24 + r*.16 + _bounded(1.0-abs(a-.45)/.45)*.18 + temperate*.12 + _bounded(1.0-b)*.08 - d*.10 - ice*.22,
        "desert_specialist": desert + a*.28 + _bounded(1.0-m)*.16 + _bounded(1.0-rain/420.0)*.14 + r*.10 - ice*.22 - wet*.24,
        "alpine_tundra_specialist": alpine + _bounded((8.0-t)/22.0)*.22 + _bounded((value("elevation_m")-1200.0)/2600.0)*.18 + unit("permafrost_extent_index")*.18 + r*.12 - ice*.18,
        "wetland_amphibian": wet*.34 + unit("wetland_hydrology_index")*.18 + m*.12 + r*.14 + warm*.10 + amphibian_bonus*.18 - a*.10,
        "large_predator": r*.28 + b*.24 + p*.18 + _bounded(1.0-d)*.18 + forest*.10 + grass*.10 - ice*.26,
        "freshwater_fish": freshwater + (0.0 if river else fish*.30) + p*.12 + _bounded(value("river_channel_width_m")/180.0)*.14 + _bounded(value("river_channel_depth_m")/9.0)*.12 + _bounded(1.0-abs(t-14.0)/24.0)*.10 - ice*.22,
        "marine_fish": marine + fish*.42 + p*.14 + _bounded(1.0-abs(t-13.0)/24.0)*.10 + (.08 if water == "continental_shelf" else 0.0) - ice*.18,
        "reef_builder": reef_bonus + reef*.54 + fish*.10 + warm*.08 - ice*.22,
        "mangrove_coastal_bird": mangrove + wet*.22 + (0.0 if cell.get("marine_distance_status") == "no_marine_source" else _bounded(1.0-value("distance_to_marine_water_km",9999.0)/80.0))*.14 + r*.12 + warm*.12 + _bounded(rain/1600.0)*.10 - d*.08,
    }
    return {guild: round(_bounded(score), 6) if support[f"species_{guild}_score_supported"] else 0.0 for guild, score in scores.items()}


def _v3_descriptors(cell, cells_by_id, support):
    def unit(key):
        return _bounded(float(cell.get(key, 0.0)))
    confidence = _bounded(unit("biome_confidence_index")*.30 + unit("species_richness_index")*.22 + unit("primary_productivity_index")*.20 + max(unit("wetland_extent_index"),unit("reef_growth_index"))*.12 + (1.0-unit("ecosystem_disturbance_pressure_index"))*.16) if support["species_composition_confidence_supported"] else 0.0
    neighbors = [cells_by_id[i] for i in cell.get("neighbors", []) if i in cells_by_id]
    same = sum(n.get("biome", "unknown") == cell.get("biome", "unknown") for n in neighbors) / len(neighbors) if neighbors else 0.0
    island = {"islet":.42,"island":.34,"large_island":.24,"continental_island":.16}.get(str(cell.get("island_class", "mainland")),0.0)
    endemism = _bounded(island + (.22 if str(cell.get("biome_ecotone_type", "none")) != "none" else 0.0) + unit("reef_growth_index")*.16 + unit("wetland_extent_index")*.12 + _bounded((float(cell.get("elevation_m",0.0))-1500.0)/3000.0)*.14 + _bounded(1.0-same)*.24 - unit("ecosystem_disturbance_pressure_index")*.10) if support["species_endemism_supported"] else 0.0
    return confidence, endemism


def _close(observed, expected):
    return _finite(observed) and abs(observed - expected) <= 0.00000051


def _validate_v3(world, *, prescribed_natural=False):
    from .aquatic_climate_validation import validate_aquatic_climate_support
    model = world.get("ecosystem_dynamics_model")
    expected_parent = "heuristic_ecosystem_climate_support_v5" if prescribed_natural else "heuristic_ecosystem_climate_support_v4"
    if not isinstance(model, dict) or model.get("model") != expected_parent:
        return ["species parent support requires declared " + expected_parent] if prescribed_natural else ["species parent support requires declared ecosystem parent model v4"]
    errors = validate_aquatic_climate_support(world)
    if errors:
        return ["species parent support requires valid ecosystem parents: " + error for error in errors[:20]]
    try:
        marine_contract = require_marine_distance(world)
    except (TypeError, ValueError, KeyError, OverflowError, AttributeError) as error:
        return [("species parent: " + str(error))[:600]]
    cells = world["cells"]
    by_id = {cell["id"]:cell for cell in cells}
    for cell in cells:
        if not _finite(cell.get("temperature_c")):
            errors.append(f"species parent cell {cell['id']}: annual temperature must be finite numeric")
        for key in _V3_NUMERIC_INPUTS:
            if key == "distance_to_marine_water_km" and marine_contract:
                continue
            if key in cell and not _finite(cell[key]):
                errors.append(f"species parent cell {cell['id']}: present {key} must be finite numeric")
        neighbors = cell.get("neighbors", [])
        if not isinstance(neighbors, list) or any(type(i) is not int or i not in by_id for i in neighbors):
            errors.append(f"species parent cell {cell['id']}: invalid neighbor IDs")
    if errors:
        return errors[:64]
    expected_states, expected_scores, raw_descriptors = {}, {}, {}
    for cell in cells:
        cell_id = cell["id"]
        support, habitat = _v3_state(cell)
        expected_states[cell_id] = support
        scores = _v3_scores(cell, support)
        expected_scores[cell_id] = scores
        confidence, endemism = _v3_descriptors(cell, by_id, support)
        raw_descriptors[cell_id] = (confidence, endemism)
        for key, expected in support.items():
            if type(cell.get(key)) is not type(expected) or cell[key] != expected:
                errors.append(f"species parent cell {cell_id}: {key} mismatch")
        observed_scores = cell.get("species_guild_scores")
        if not isinstance(observed_scores, dict) or observed_scores.keys() != scores.keys():
            errors.append(f"species parent cell {cell_id}: species_guild_scores requires exact ten-guild coverage")
        else:
            for guild, score in scores.items():
                if not _close(observed_scores[guild], score):
                    errors.append(f"species parent cell {cell_id}: {guild} score mismatch")
        available = [(guild,score) for guild,score in scores.items() if support[f"species_{guild}_score_supported"]]
        guild, best = sorted(available,key=lambda item:(-item[1],item[0]))[0] if available else ("none",0.0)
        if best < .25:
            guild = "none"
        if cell.get("dominant_species_guild") != guild:
            errors.append(f"species parent cell {cell_id}: dominant guild mismatch")
        for field, expected in (("species_habitat_suitability_index",best), ("species_endemism_index",round(endemism,6)), ("species_composition_confidence_index",round(confidence,6))):
            if not _close(cell.get(field),expected):
                errors.append(f"species parent cell {cell_id}: {field} mismatch")
        richness = sum(score >= .46 for _,score in available)
        if type(cell.get("species_guild_richness_count")) is not int or cell["species_guild_richness_count"] != richness:
            errors.append(f"species parent cell {cell_id}: guild richness count mismatch")

    expected_groups = []
    for guild in sorted(_EXPECTED_V3_MODEL["score_parent_inputs"]):
        remaining = {i for i,support in expected_states.items() if support[f"species_{guild}_score_supported"] and support["species_record_descriptors_supported"] and expected_scores[i][guild] >= .46}
        while remaining:
            component = {min(remaining)}
            remaining -= component
            frontier = list(component)
            while frontier:
                i = frontier.pop(0)
                for j in by_id[i].get("neighbors",[]):
                    if j in remaining:
                        remaining.remove(j)
                        component.add(j)
                        frontier.append(j)
            expected_groups.append((guild,sorted(component)))
    records = world.get("species_range_records")
    if not isinstance(records,list):
        return [*errors,"species parent support requires a valid range record list"][:64]
    if len(records) != len(expected_groups):
        errors.append("species parent range coverage does not match supported candidate components")
    inverse = {i:[] for i in by_id}
    guild_counts, habitat_counts = {}, {}
    range_metrics = []
    fragmentation_by_cell = {i: 0.0 for i in by_id}
    habitat_classes = {"canopy_tree":"terrestrial","grassland_grazer":"terrestrial","desert_specialist":"arid","alpine_tundra_specialist":"alpine","large_predator":"terrestrial","freshwater_fish":"freshwater","marine_fish":"marine","reef_builder":"reef","wetland_amphibian":"wetland","mangrove_coastal_bird":"wetland"}
    for record_id,(guild,ids) in enumerate(expected_groups):
        for i in ids:
            inverse[i].append(record_id)
        guild_counts[guild] = guild_counts.get(guild,0)+1
        habitat_class = habitat_classes[guild]
        habitat_counts[habitat_class] = habitat_counts.get(habitat_class,0)+1
        def mean(key):
            return sum(float(by_id[i].get(key, 0.0)) for i in ids) / len(ids)
        edge_count = sum(len(by_id[i].get("neighbors", [])) for i in ids)
        external_count = sum(j not in ids for i in ids for j in by_id[i].get("neighbors", []))
        fragmentation = _bounded((external_count / edge_count if edge_count else 1.0) * .72 + .28 / len(ids))
        area = sum(max(0.0, float(by_id[i].get("area_km2", 0.0))) for i in ids)
        endemism = _bounded(sum(round(raw_descriptors[i][1], 6) for i in ids) / len(ids) * .72 + fragmentation * .18 + _bounded((800000.0 - area) / 800000.0) * .18)
        confidence = sum(round(raw_descriptors[i][0], 6) for i in ids) / len(ids)
        stress = _bounded(mean("ecosystem_disturbance_pressure_index") * .38 + fragmentation * .22 + (1.0 - confidence) * .22 + endemism * .18)
        range_metrics.append((area, endemism, stress))
        for i in ids:
            fragmentation_by_cell[i] = max(fragmentation_by_cell[i], round(fragmentation, 6))
        if record_id >= len(records):
            continue
        record = records[record_id]
        if not isinstance(record,dict):
            errors.append(f"species parent range {record_id}: malformed record")
            continue
        if type(record.get("id")) is not int or record["id"] != record_id or record.get("guild_type") != guild or record.get("cell_ids") != ids or any(type(i) is not int for i in record.get("cell_ids",[]) if isinstance(record.get("cell_ids"),list)):
            errors.append(f"species parent range {record_id}: guild/member/component identity mismatch")
            continue
        for field,source in (("mean_primary_productivity_index","primary_productivity_index"),("mean_species_richness_index","species_richness_index"),("mean_disturbance_pressure_index","ecosystem_disturbance_pressure_index"),("mean_composition_confidence_index","species_composition_confidence_index")):
            if not _close(record.get(field),round(mean(source),6)):
                errors.append(f"species parent range {record_id}: supported {field} mismatch")
        for field, expected in (
            ("range_fragmentation_index", fragmentation), ("endemism_index", endemism),
            ("conservation_stress_index", stress), ("area_km2", area),
            ("mean_habitat_suitability_index", sum(expected_scores[i][guild] for i in ids) / len(ids)),
            ("max_habitat_suitability_index", max(expected_scores[i][guild] for i in ids)),
        ):
            if not _close(record.get(field), round(expected, 6)):
                errors.append(f"species parent range {record_id}: {field} mismatch")
        if type(record.get("cell_count")) is not int or record["cell_count"] != len(ids) or record.get("habitat_class") != habitat_class:
            errors.append(f"species parent range {record_id}: habitat/member count mismatch")
        expected_evidence = {
            "mean_wetland_extent_index":round(mean("wetland_extent_index"),6),
            "mean_reef_growth_index":round(mean("reef_growth_index"),6),
            "river_cell_fraction":round(sum(bool(by_id[i].get("is_river",False)) for i in ids)/len(ids),6),
            "water_cell_fraction":round(sum(_habitat(by_id[i])[0] for i in ids)/len(ids),6),
            "coastal_cell_fraction":round(sum((by_id[i].get("marine_distance_status") != "no_marine_source" and float(by_id[i].get("distance_to_marine_water_km",9999))<=80) for i in ids)/len(ids),6),
        }
        if guild in ("marine_fish","reef_builder") or (guild == "freshwater_fish" and all(expected_states[i]["species_freshwater_fishery_input_mode"] == "standing_water_required" for i in ids)):
            expected_evidence["mean_fishery_productivity_index"] = round(mean("fishery_productivity_index"),6)
        if guild == "canopy_tree":
            expected_evidence["mean_forest_growth_index"] = round(mean("forest_growth_index"),6)
        evidence = record.get("habitat_evidence")
        if not isinstance(evidence,dict) or evidence.keys() != expected_evidence.keys() or any(not _close(evidence[key],val) for key,val in expected_evidence.items()):
            errors.append(f"species parent range {record_id}: consumed habitat evidence mismatch")
    for i, expected in inverse.items():
        if by_id[i].get("species_range_record_ids") != expected or not isinstance(by_id[i].get("species_range_record_ids"),list) or any(type(x) is not int for x in by_id[i].get("species_range_record_ids",[])):
            errors.append(f"species parent cell {i}: range inverse mismatch")
        if not _close(by_id[i].get("species_range_fragmentation_index"), fragmentation_by_cell[i]):
            errors.append(f"species parent cell {i}: range fragmentation mismatch")
    summary = world.get("summary", {})
    if not isinstance(summary, dict):
        return [*errors, "species parent support requires a summary object"][:64]
    support_counts = {guild:sum(state[f"species_{guild}_score_supported"] for state in expected_states.values()) for guild in sorted(_EXPECTED_V3_MODEL["score_parent_inputs"])}
    statuses = {}
    for state in expected_states.values():
        status=state["species_composition_status"]
        statuses[status]=statuses.get(status,0)+1
    expected_summary = {"species_score_supported_cell_counts":support_counts,"species_composition_status_counts":dict(sorted(statuses.items())),"species_range_record_count":len(expected_groups),"species_range_cell_count":sum(bool(ids) for ids in inverse.values()),"species_guild_type_counts":dict(sorted(guild_counts.items())),"species_habitat_class_counts":dict(sorted(habitat_counts.items()))}
    dominant_counts = {}
    suitability_sum = 0.0
    for i, scores in expected_scores.items():
        available = [(guild, score) for guild, score in scores.items() if expected_states[i][f"species_{guild}_score_supported"]]
        dominant, best = sorted(available, key=lambda item: (-item[1], item[0]))[0] if available else ("none", 0.0)
        if best < .25:
            dominant = "none"
        dominant_counts[dominant] = dominant_counts.get(dominant, 0) + 1
        suitability_sum += best
    expected_summary.update({
        "dominant_species_guild_counts": dict(sorted(dominant_counts.items())),
        "terrestrial_species_range_count": sum(habitat_counts.get(key, 0) for key in ("terrestrial", "arid", "alpine")),
        "aquatic_species_range_count": sum(habitat_counts.get(key, 0) for key in ("freshwater", "marine", "reef")),
        "wetland_species_range_count": habitat_counts.get("wetland", 0),
        "high_endemism_species_range_count": sum(endemism >= .60 for _, endemism, _ in range_metrics),
        "high_conservation_stress_species_range_count": sum(stress >= .60 for _, _, stress in range_metrics),
    })
    for flag in ("species_composition_confidence_supported","species_endemism_supported","species_record_descriptors_supported"):
        expected_summary[flag+"_cell_count"] = sum(state[flag] for state in expected_states.values())
    for key,expected in expected_summary.items():
        if not _same_structure(summary.get(key),expected):
            errors.append(f"species parent summary: {key} mismatch")
    for key, expected in (
        ("mean_species_habitat_suitability_index", suitability_sum / len(cells) if cells else 0.0),
        ("mean_species_composition_confidence_index", sum(pair[0] for pair in raw_descriptors.values()) / len(cells) if cells else 0.0),
        ("mean_species_endemism_index", sum(pair[1] for pair in raw_descriptors.values()) / len(cells) if cells else 0.0),
        ("species_range_total_area_km2", sum(round(area, 6) for area, _, _ in range_metrics)),
    ):
        if not _close(summary.get(key), round(expected, 6)):
            errors.append(f"species parent summary: {key} mismatch")
    return errors[:64]


def _same_structure(observed,expected):
    if type(observed) is not type(expected):
        return False
    if isinstance(expected,dict):
        return observed.keys()==expected.keys() and all(_same_structure(observed[k],v) for k,v in expected.items())
    if isinstance(expected,list):
        return len(observed)==len(expected) and all(_same_structure(a,b) for a,b in zip(observed,expected))
    return observed == expected


_V3_ONLY_DESCRIPTOR_FLAGS = (
    "species_composition_confidence_supported", "species_endemism_supported", "species_record_descriptors_supported",
)
_V3_ONLY_CELL_FIELDS = (
    *(f"species_{guild}_score_supported" for guild in sorted(_TERRESTRIAL_GUILDS | _LEGACY_GUILDS)),
    *_V3_ONLY_DESCRIPTOR_FLAGS, "species_applicable_guild_count", "species_supported_guild_count",
    "species_composition_status", "species_guild_scores",
)
_V3_ONLY_SUMMARY_FIELDS = (
    *(flag + "_cell_count" for flag in _V3_ONLY_DESCRIPTOR_FLAGS),
    "species_score_supported_cell_counts", "species_composition_status_counts",
)


def _validate_species_habitat_historical(world: dict[str,Any]) -> list[str]:
    """Validate exact v2 archives or independent v3 source/availability replay."""
    if not isinstance(world,dict):
        return ["species habitat support requires a world object"]
    model = world.get("species_ranges_model")
    if not isinstance(model, dict) or model.get("model") != "heuristic_species_parent_support_v3":
        cells = world.get("cells")
        summary = world.get("summary")
        if ((isinstance(cells, list) and any(isinstance(c, dict) and any(k in c for k in _V3_ONLY_CELL_FIELDS) for c in cells))
                or (isinstance(summary, dict) and any(k in summary for k in _V3_ONLY_SUMMARY_FIELDS))):
            return ["species parent availability fields require the exact species v3 declaration"]
    if "species_ranges_model" not in world:
        return []
    if isinstance(model,dict) and model.get("model") == "heuristic_species_parent_support_v3":
        if not _same_structure(model,_EXPECTED_V3_MODEL):
            return ["species parent model metadata is missing fields, malformed, or unsupported"]
        return _validate_v3(world)
    return _validate_v2(world)


PRESCRIBED_SPECIES_CELL_FIELDS = tuple(dict.fromkeys((
    *_V3_ONLY_CELL_FIELDS, "species_terrestrial_habitat_eligible",
    "species_freshwater_habitat_eligible", "species_marine_habitat_eligible",
    "species_freshwater_fish_score_supported", "species_marine_fish_score_supported",
    "species_freshwater_fishery_input_mode", "dominant_species_guild",
    "species_habitat_suitability_index", "species_endemism_index",
    "species_range_fragmentation_index", "species_composition_confidence_index",
    "species_guild_richness_count", "species_range_record_ids",
)))
PRESCRIBED_SPECIES_SUMMARY_FIELDS = (
    *_V3_ONLY_SUMMARY_FIELDS, "species_range_record_count", "species_range_cell_count",
    "terrestrial_species_range_count", "aquatic_species_range_count", "wetland_species_range_count",
    "high_endemism_species_range_count", "high_conservation_stress_species_range_count",
    "species_range_total_area_km2", "mean_species_habitat_suitability_index",
    "mean_species_endemism_index", "mean_species_composition_confidence_index",
    "species_guild_type_counts", "species_habitat_class_counts", "dominant_species_guild_counts",
)


def validate_prescribed_species_inputs(world):
    """Explicit sources at the species stage; E5 availability is independently audited.

    Annual temperature is finite here because range records publish climate
    envelopes. This prerequisite is distinct from E5's own unavailable-T policy.
    """
    from .aquatic_climate_validation import _EXPECTED_MODELS, validate_aquatic_climate_support
    def need(ok, message):
        if not ok:
            raise ValueError("prescribed natural species: " + message[:540])
    need(isinstance(world, dict), "world must be an object")
    need(_same_structure(world.get("ecosystem_dynamics_model"), _EXPECTED_MODELS["heuristic_ecosystem_climate_support_v5"]), "requires exact ecosystem v5 parent")
    errors = validate_aquatic_climate_support(world)
    need(not errors, "invalid ecosystem parent: " + (errors[0] if errors else ""))
    marine_contract = require_marine_distance(world)
    cells = world["cells"]
    by_id = {c["id"]: c for c in cells}
    for c in cells:
        cid = c["id"]
        for field in ("temperature_c", *_V3_NUMERIC_INPUTS):
            if field == "distance_to_marine_water_km" and marine_contract:
                continue
            need(_finite(c.get(field)), f"cell {cid}: explicit finite numeric {field} required")
        for field in ("is_water", "is_lake", "is_river"):
            need(type(c.get(field)) is bool, f"cell {cid}: explicit boolean {field} required")
        for field in ("biome", "water_body_type", "biome_ecotone_type", "island_class", "reef_type", "wetland_system_type"):
            need(isinstance(c.get(field), str) and bool(c[field].strip()), f"cell {cid}: explicit nonempty {field} required")
        for field in ("wetland_system_id", "reef_system_id", "aquifer_system_id", "basin_id"):
            need(type(c.get(field)) is int and c[field] >= -1, f"cell {cid}: explicit integer {field} >= -1 required")
        need(-90 <= c["lat_deg"] <= 90 and -180 <= c["lon_deg"] <= 180, f"cell {cid}: canonical latitude/longitude required")
        ns = c.get("neighbors")
        need(isinstance(ns, list) and all(type(i) is int and i in by_id and i != cid for i in ns) and len(ns) == len(set(ns)), f"cell {cid}: explicit complete unique nonself neighbors required")
    for c in cells:
        need(all(c["id"] in by_id[i]["neighbors"] for i in c["neighbors"]), f"cell {c['id']}: reciprocal neighbors required")
        need(c["basin_id"] == -1 or c["basin_id"] in by_id,
             f"cell {c['id']}: basin_id must resolve to a native outlet cell")
    for family, descriptor in (("wetland_systems", "wetland_system_id"),
                               ("reef_systems", "reef_system_id"),
                               ("aquifer_systems", "aquifer_system_id")):
        records = world.get(family)
        need(isinstance(records, list), f"explicit {family} source list required")
        sources = {}
        for record in records:
            need(isinstance(record, dict), f"{family}: source records must be objects")
            rid = record.get("id")
            need(type(rid) is int and rid >= 0 and rid not in sources,
                 f"{family}: unique nonnegative integer source IDs required")
            members = record.get("cell_ids")
            need(isinstance(members, list) and all(type(i) is int and i in by_id for i in members)
                 and len(members) == len(set(members)),
                 f"{family} record {rid}: explicit unique known cell_ids required")
            sources[rid] = set(members)
            need(all(by_id[i][descriptor] == rid for i in members),
                 f"{family} record {rid}: cell descriptor must match source membership")
        for c in cells:
            rid = c[descriptor]
            need(rid == -1 or (rid in sources and c["id"] in sources[rid]),
                 f"cell {c['id']}: {descriptor} must resolve to reciprocal {family} membership")


def validate_species_habitat_support(world: dict[str, Any]) -> list[str]:
    if not isinstance(world, dict):
        return ["species habitat support requires a world object"]
    model = world.get("species_ranges_model")
    parent = world.get("ecosystem_dynamics_model")
    new_own = isinstance(model, dict) and model.get("model") == "heuristic_species_parent_support_v4"
    new_parent = isinstance(parent, dict) and parent.get("model") == "heuristic_ecosystem_climate_support_v5"
    if new_own or new_parent:
        try:
            if not _same_structure(model, _EXPECTED_V4_MODEL):
                return ["prescribed natural species: exact species v4 declaration required"]
            validate_prescribed_species_inputs(world)
            errors = _validate_v3(world, prescribed_natural=True)
            if not errors:
                errors = _validate_prescribed_species_record_details(world)
            return [error[:600] for error in errors[:64]]
        except (TypeError, ValueError, KeyError, ArithmeticError, AttributeError) as error:
            return [("prescribed natural species: " + str(error))[:600]]
    return _validate_species_habitat_historical(world)



def _validate_prescribed_species_record_details(world):
    """Close the existing range descriptors as part of new atomic publication."""
    import math
    from collections import Counter
    by_id = {c["id"]: c for c in world["cells"]}
    roles = {"canopy_tree":"primary_producer", "grassland_grazer":"herbivore",
        "desert_specialist":"specialist_consumer", "alpine_tundra_specialist":"specialist_consumer",
        "large_predator":"apex_predator", "wetland_amphibian":"secondary_consumer",
        "freshwater_fish":"aquatic_consumer", "marine_fish":"aquatic_consumer",
        "reef_builder":"foundation_species", "mangrove_coastal_bird":"mobile_consumer"}
    fields = {"id", "guild_type", "habitat_class", "trophic_role", "cell_count", "cell_ids", "area_km2",
        "centroid_lat_deg", "centroid_lon_deg", "dominant_biome", "dominant_ecotone_type", "dominant_water_body_type",
        "mean_habitat_suitability_index", "max_habitat_suitability_index", "mean_species_richness_index",
        "mean_primary_productivity_index", "mean_disturbance_pressure_index", "mean_composition_confidence_index",
        "mean_temperature_c", "mean_precipitation_mm_y", "range_fragmentation_index", "endemism_index",
        "conservation_stress_index", "climate_envelope", "habitat_evidence", "wetland_system_ids",
        "reef_system_ids", "aquifer_system_ids", "river_basin_ids"}
    errors = []
    for record in world["species_range_records"]:
        rid = record["id"]
        if record.keys() != fields:
            errors.append(f"species parent range {rid}: exact record field coverage required")
            continue
        # Exact equality alone would accept inf == inf after overflowing a
        # sum of finite source values (for example the precipitation mean).
        pending = [record]
        finite_outputs = True
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
            elif isinstance(value, float) and not math.isfinite(value):
                finite_outputs = False
                break
        if not finite_outputs:
            errors.append(f"species parent range {rid}: finite record outputs required")
            continue
        cells = [by_id[i] for i in record["cell_ids"]]
        expected = {"trophic_role": roles[record["guild_type"]]}
        for key, source in (("dominant_biome", "biome"), ("dominant_ecotone_type", "biome_ecotone_type"), ("dominant_water_body_type", "water_body_type")):
            counts = Counter(c[source] for c in cells)
            expected[key] = min(counts, key=lambda x: (-counts[x], x))
        envelope = {}
        for source in ("temperature_c", "precipitation_mm_y"):
            values = [float(c[source]) if source == "temperature_c" else max(0.0, float(c[source])) for c in cells]
            envelope.update({"min_" + source: round(min(values), 6), "mean_" + source: round(sum(values)/len(values), 6), "max_" + source: round(max(values), 6)})
            expected["mean_" + source] = envelope["mean_" + source]
        expected["climate_envelope"] = envelope
        for key, source in (("wetland_system_ids", "wetland_system_id"), ("reef_system_ids", "reef_system_id"), ("aquifer_system_ids", "aquifer_system_id"), ("river_basin_ids", "basin_id")):
            expected[key] = sorted({c[source] for c in cells if c[source] >= 0})
        total = x = y = z = 0.0
        for c in cells:
            weight = max(0.0, float(c["area_km2"])) or 1.0
            lat, lon = math.radians(float(c["lat_deg"])), math.radians(float(c["lon_deg"]))
            cosine = math.cos(lat)
            x += math.cos(lon)*cosine*weight; y += math.sin(lon)*cosine*weight; z += math.sin(lat)*weight; total += weight
        if not all(math.isfinite(v) for v in (x, y, z, total)):
            errors.append(f"species parent range {rid}: unrepresentable centroid accumulation")
            continue
        expected["centroid_lon_deg"] = round(math.degrees(math.atan2(y/total, x/total)), 6)
        expected["centroid_lat_deg"] = round(math.degrees(math.atan2(z/total, math.hypot(x/total, y/total))), 6)
        for key, value in expected.items():
            if not _same_structure(record.get(key), value):
                errors.append(f"species parent range {rid}: {key} differs from source replay")
    return errors[:64]
