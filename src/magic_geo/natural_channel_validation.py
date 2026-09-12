"""Independent versioned natural-channel contracts and source replay.

This validates diagnostic equations and their actual aquifer/groundwater parents;
it does not claim a solved native drainage, bankfull frequency or transient flow.
"""
from __future__ import annotations

import math
from typing import Any

from .natural_groundwater_validation import (
    natural_groundwater_model_version,
    validate_natural_aquifer_resources,
    validate_natural_groundwater_flow,
)
from .planet_parameters import planet_radius_km, surface_gravity_m_s2


class NaturalChannelError(ValueError):
    """Malformed declaration, consumed source, or independently replayed output."""


def _require(condition: bool, path: str) -> None:
    if not condition:
        raise NaturalChannelError('natural channels: ' + path)


def _finite(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _same(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(_same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_same(a, b) for a, b in zip(actual, expected))
    if type(expected) in (int, float):
        return _finite(actual) and actual == expected
    return type(actual) is type(expected) and actual == expected


def _output_same(actual: Any, expected: Any) -> bool:
    """Fixed numerical replay allowance; counts and identifiers stay exact types."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(_output_same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_output_same(a, b) for a, b in zip(actual, expected))
    if type(expected) is int:
        return type(actual) is int and actual == expected
    if type(expected) is float:
        allowance = max(1e-10, 8 * math.ulp(expected))
        return _finite(actual) and _finite(expected) and math.isfinite(allowance) and abs(actual - expected) <= allowance
    return type(actual) is type(expected) and actual == expected


def _shape(world: Any) -> dict[int, dict[str, Any]]:
    _require(isinstance(world, dict), 'world must be an object')
    _require(isinstance(world.get('summary', {}), dict), 'summary must be an object')
    cells = world.get('cells')
    _require(isinstance(cells, list), 'cells must be a list')
    by_id = {}
    for cell in cells:
        _require(isinstance(cell, dict), 'cells must contain objects')
        cid = cell.get('id')
        _require(type(cid) is int and cid >= 0 and cid not in by_id, 'cell IDs must be unique nonnegative integers')
        by_id[cid] = cell
    return by_id


def _declaration(world: dict[str, Any], stage: str, *, required: bool = False) -> int | None:
    key = _KEYS[stage]
    summary = world.get('summary', {})
    if key not in world:
        _require(not required or stage == 'karst', key + ' declaration required')
        _require(key not in summary, key + ' summary identity lacks declaration')
        return None
    model = world[key]
    _require(isinstance(model, dict), key + ' must be an object')
    for version in (1, 2):
        policy = _POLICIES[stage][version]
        if not policy:
            continue
        if model.keys() != policy.keys() | set(_DYNAMIC[stage]):
            continue
        if not all(_same(model[k], value) for k, value in policy.items()):
            continue
        for field in _DYNAMIC[stage]:
            value = model[field]
            if field.endswith('_count'):
                _require(type(value) is int and value >= 0, key + '.' + field + ' must be a nonnegative integer')
            else:
                _require(_finite(value) and value > 0, key + '.' + field + ' must be finite positive numeric')
        _require(summary.get(key) == policy['model_type'], key + ' summary identity mismatch')
        return version
    raise NaturalChannelError('natural channels: unknown or malformed ' + key)


def natural_downstream_model_version(world: Any, stage: str) -> int:
    """Dispatch only from an exact known own/parent chain, never numeric mirrors."""
    _require(stage in _KEYS, 'unknown downstream stage')
    _shape(world)
    own = _declaration(world, stage)
    if stage == 'channel':
        _require('groundwater_flow_model' in world, 'channel requires groundwater declaration')
        parent = natural_groundwater_model_version(world, 'groundwater')
    elif stage == 'hydraulics':
        parent = _declaration(world, 'channel', required=True)
        _require(parent == natural_downstream_model_version(world, 'channel'), 'channel parent ancestry mismatch')
    else:
        _require('aquifer_resource_model' in world, 'karst requires aquifer declaration')
        parent = natural_groundwater_model_version(world, 'aquifer')
    _require(own is None or own == parent, stage + ' own and parent versions must match')
    return parent if own is None else own


def _parent_audit(world: dict[str, Any], stage: str) -> None:
    function = {'channel': validate_natural_groundwater_flow,
                'hydraulics': validate_natural_channel_morphology,
                'karst': validate_natural_aquifer_resources}[stage]
    errors = function(world)
    _require(not errors, stage + ' requires independently valid parent: ' + (errors[0] if errors else ''))


def _surface(cell: dict[str, Any]) -> Any:
    return cell.get('hydrologic_surface_elevation_m', cell.get('filled_elevation_m', cell.get('elevation_m')))


def _number_fields(cell: dict[str, Any], fields: tuple[str, ...]) -> None:
    for key in fields:
        _require(_finite(cell.get(key)), f"cell {cell['id']}: {key} must be finite numeric, not boolean")


def validate_natural_downstream_inputs(world: Any, stage: str) -> int:
    """Read-only preflight; matching parent is audited before any publication."""
    version = natural_downstream_model_version(world, stage)
    _parent_audit(world, stage)
    if version == 1:
        return version
    by_id = _shape(world)
    for cid, cell in by_id.items():
        _require(_finite(cell.get('area_km2')) and cell['area_km2'] > 0, f'cell {cid}: positive area required')
        _require(type(cell.get('is_water')) is bool, f'cell {cid}: is_water must be boolean')
        neighbors = cell.get('neighbors')
        _require(isinstance(neighbors, list) and all(type(n) is int and n in by_id for n in neighbors), f'cell {cid}: unknown or malformed neighbor')
        _require(len(neighbors) == len(set(neighbors)) and cid not in neighbors, f'cell {cid}: repeated/self neighbor')
        _require(all(isinstance(by_id[n].get('neighbors'), list) and cid in by_id[n]['neighbors'] for n in neighbors), f'cell {cid}: mesh neighbors must be reciprocal')
        if stage == 'karst':
            _number_fields(cell, ('elevation_m',))
            _require(isinstance(cell.get('water_body_type'), str) and bool(cell['water_body_type']), f'cell {cid}: water_body_type required')
            if not cell['is_water'] and cell['water_body_type'] not in {'ocean', 'continental_shelf', 'inland_sea'}:
                _number_fields(cell, ('precipitation_mm_y', 'runoff_mm_y', 'groundwater_recharge_mm_y',
                    'soil_moisture_index', 'soil_drainage_index', 'soil_profile_development_index', 'soil_ph',
                    'aquifer_productivity_index', 'aquifer_storage_index', 'seasonal_aridity_index',
                    'ice_thickness_m', 'temperature_c'))
                _require(isinstance(cell.get('lithology'), str) and bool(cell['lithology']), f'cell {cid}: lithology required')
                for n in neighbors:
                    _require(_finite(by_id[n].get('elevation_m')) and _finite(cell['elevation_m'] - by_id[n]['elevation_m']), f'cell {cid}: neighbor relief unrepresentable')
            continue
        _require(type(cell.get('is_river')) is bool, f'cell {cid}: is_river must be boolean')
        channel = cell['is_river'] and not cell['is_water']
        if stage == 'channel':
            _number_fields(cell, ('flow_accumulation', 'lat_deg', 'lon_deg'))
            _require(-90 <= cell['lat_deg'] <= 90 and -180 <= cell['lon_deg'] <= 180, f'cell {cid}: invalid geographic coordinates')
            _require(_finite(_surface(cell)), f'cell {cid}: selected conditioned elevation must be finite')
            target = cell.get('flow_to')
            _require(type(target) is int and (target == -1 or target in neighbors), f'cell {cid}: flow_to must be -1 or known adjacent cell')
            if target >= 0:
                _require(_finite(_surface(by_id[target])) and _finite(_surface(cell) - _surface(by_id[target])), f'cell {cid}: surface drop unrepresentable')
            if channel:
                _number_fields(cell, ('runoff_mm_y', 'sediment_deposition_m', 'sediment_thickness_m', 'wetland_extent_index', 'baseflow_support_index', 'seasonal_aridity_index', 'ice_thickness_m'))
                sediment = cell.get('fluvial_sediment_routed_outgoing_m', cell.get('sediment_export_m'))
                _require(_finite(sediment), f'cell {cid}: selected routed sediment must be finite')
                _require(_finite(sediment / 85 * .45 + cell['sediment_deposition_m'] / 18 * .35 + cell['sediment_thickness_m'] / 30 * .20), f'cell {cid}: sediment index arithmetic unrepresentable')
                _require(isinstance(cell.get('landform'), str) and bool(cell['landform']), f'cell {cid}: landform required')
        elif channel:
            _number_fields(cell, ('sediment_routing_load_m', 'wetland_extent_index', 'ice_thickness_m'))
    if stage == 'channel':
        radius = planet_radius_km(world)
        _require(_finite(2 * math.pi * radius), 'planet circumference unrepresentable')
    elif stage == 'hydraulics':
        _require(_finite(surface_gravity_m_s2(world)), 'configured gravity unrepresentable')
    return version


def _owned_shape(world: dict[str, Any], stage: str, version: int) -> None:
    for cell in world['cells']:
        for key in _OWNED[stage]['cell']:
            value = cell.get(key)
            if key.endswith('_id'):
                _require(type(value) is int and value >= -1, f"cell {cell['id']}: invalid {key}")
            elif key in ('channel_morphology_class', 'hydraulic_flow_regime'):
                _require(type(value) is str, f"cell {cell['id']}: invalid {key}")
            else:
                _require(_finite(value), f"cell {cell['id']}: invalid {key}")
    for key in _OWNED[stage]['world']:
        if key != _KEYS[stage]:
            _require(isinstance(world.get(key), list), key + ' must be a list')
    _require(_declaration(world, stage, required=True) == version, stage + ' published declaration missing or mismatched')


def _legacy_view(world: dict[str, Any], stage: str) -> dict[str, Any]:
    """Unpublished metadata view for unchanged independent v1 numerical formulas."""
    view = dict(world)
    view['summary'] = dict(world['summary'])
    for s in (('channel', 'hydraulics') if stage == 'hydraulics' else ('channel',)):
        key = _KEYS[s]
        view[key] = {**_POLICIES[s][1], **{k: world[key][k] for k in _DYNAMIC[s]}}
        view['summary'][key] = _POLICIES[s][1]['model_type']
    return view


def _audit(world: Any, stage: str) -> list[str]:
    try:
        version = validate_natural_downstream_inputs(world, stage)
        _owned_shape(world, stage, version)
        from ._natural_river_replay import _validate_river_channel_morphology, _validate_river_hydraulics
        replay = _validate_river_channel_morphology if stage == 'channel' else _validate_river_hydraulics
        view = _legacy_view(world, stage) if version == 2 else world
        errors = replay(view, view['summary'], {c['id']: c for c in view['cells']}, strict=version == 2)
        _require(not errors, errors[0] if errors else '')
        return []
    except (ValueError, TypeError, KeyError, OverflowError, ArithmeticError) as exc:
        if isinstance(exc, (NaturalChannelError, ValueError)):
            return [str(exc)[:600] or 'natural channels: invalid source or output']
        return ['natural channels: malformed ' + stage + ' input or output (' + type(exc).__name__ + ')']


def validate_natural_channel_morphology(world: Any) -> list[str]:
    return _audit(world, 'channel')


def validate_natural_river_hydraulics(world: Any) -> list[str]:
    return _audit(world, 'hydraulics')

_POLICIES = {'channel': {1: {'model_type': 'causal_flow_sediment_wetland_baseflow_channel_morphology_v1',
                 'domain': 'is_river_and_not_is_water_cells',
                 'flow_normalization_model': 'global_max_flow_accumulation_v1',
                 'runoff_normalization_mm_y': 2200.0,
                 'slope_model': 'downstream_conditioned_surface_drop_over_great_circle_distance_v1',
                 'slope_normalization': 0.028,
                 'sediment_model': 'routed_outgoing_deposition_and_mobile_thickness_v1',
                 'floodplain_model': 'lowland_slope_sediment_wetland_baseflow_index_v1',
                 'geometry_model': 'flow_runoff_floodplain_sediment_slope_baseflow_aridity_ice_v1',
                 'stream_power_model': 'discharge_slope_runoff_sediment_flow_index_v1',
                 'classification_model': 'ice_aridity_sediment_slope_depth_width_threshold_tree_v1',
                 'system_grouping_model': 'undirected_mesh_connected_channel_components_v1',
                 'system_length_model': 'internal_flow_to_great_circle_edges_v1',
                 'deterministic': True,
                 'model_limitation': 'empirical_diagnostic_channel_geometry_without_subcell_cross_sections_calibrated_bankfull_frequency_or_transient_morphodynamics'},
             2: {'model_type': 'causal_flow_sediment_wetland_baseflow_channel_morphology_v2',
                 'domain': 'is_river_and_not_is_water_cells',
                 'flow_normalization_model': 'global_max_flow_accumulation_v1',
                 'runoff_normalization_mm_y': 2200.0,
                 'slope_model': 'downstream_conditioned_surface_drop_over_great_circle_distance_v1',
                 'slope_normalization': 0.028,
                 'sediment_model': 'routed_outgoing_deposition_and_mobile_thickness_v1',
                 'floodplain_model': 'lowland_slope_sediment_wetland_baseflow_index_v1',
                 'geometry_model': 'flow_runoff_floodplain_sediment_slope_baseflow_aridity_ice_v1',
                 'stream_power_model': 'discharge_slope_runoff_sediment_flow_index_v1',
                 'classification_model': 'ice_aridity_sediment_slope_depth_width_threshold_tree_v1',
                 'system_grouping_model': 'undirected_mesh_connected_channel_components_v1',
                 'system_length_model': 'internal_flow_to_great_circle_edges_v1',
                 'deterministic': True,
                 'model_limitation': 'empirical_diagnostic_channel_geometry_without_subcell_cross_sections_calibrated_bankfull_frequency_or_transient_morphodynamics',
                 'source_groundwater_flow_model': 'descending_head_natural_recharge_partition_v2'}},
 'hydraulics': {1: {'model_type': 'manning_blended_diagnostic_river_hydraulics_v1',
                    'source_channel_model': 'causal_flow_sediment_wetland_baseflow_channel_morphology_v1',
                    'domain': 'is_river_and_not_is_water_cells',
                    'cross_section_model': 'rectangular_area_and_wetted_perimeter_v1',
                    'slope_model': 'channel_slope_index_times_0_028_with_1e_5_floor_v1',
                    'roughness_model': 'morphology_sediment_wetland_ice_bounded_manning_n_v1',
                    'velocity_model': '55_percent_discharge_plus_45_percent_manning_bounded_v1',
                    'froude_model': 'velocity_over_sqrt_gravity_times_depth_v1',
                    'shear_model': 'density_gravity_hydraulic_radius_slope_v1',
                    'capacity_model': 'cross_section_discharge_radius_velocity_index_v1',
                    'navigability_model': 'depth_width_velocity_froude_slope_ice_index_v1',
                    'regime_model': 'froude_velocity_shear_threshold_tree_v1',
                    'reach_model': 'one_reach_per_river_channel_system_v1',
                    'water_density_kg_m3': 1000.0,
                    'maximum_velocity_m_s': 12.0,
                    'hydraulic_navigability_threshold': 0.55,
                    'high_shear_stress_pa': 120.0,
                    'deterministic': True,
                    'model_limitation': 'steady_diagnostic_rectangular_hydraulics_without_solved_continuity_backwater_flood_frequency_or_transient_flow'},
                2: {'model_type': 'manning_blended_diagnostic_river_hydraulics_v2',
                    'source_channel_model': 'causal_flow_sediment_wetland_baseflow_channel_morphology_v2',
                    'domain': 'is_river_and_not_is_water_cells',
                    'cross_section_model': 'rectangular_area_and_wetted_perimeter_v1',
                    'slope_model': 'channel_slope_index_times_0_028_with_1e_5_floor_v1',
                    'roughness_model': 'morphology_sediment_wetland_ice_bounded_manning_n_v1',
                    'velocity_model': '55_percent_discharge_plus_45_percent_manning_bounded_v1',
                    'froude_model': 'velocity_over_sqrt_gravity_times_depth_v1',
                    'shear_model': 'density_gravity_hydraulic_radius_slope_v1',
                    'capacity_model': 'cross_section_discharge_radius_velocity_index_v1',
                    'navigability_model': 'depth_width_velocity_froude_slope_ice_index_v1',
                    'regime_model': 'froude_velocity_shear_threshold_tree_v1',
                    'reach_model': 'one_reach_per_river_channel_system_v1',
                    'water_density_kg_m3': 1000.0,
                    'maximum_velocity_m_s': 12.0,
                    'hydraulic_navigability_threshold': 0.55,
                    'high_shear_stress_pa': 120.0,
                    'deterministic': True,
                    'model_limitation': 'steady_diagnostic_rectangular_hydraulics_without_solved_continuity_backwater_flood_frequency_or_transient_flow'}},
 'karst': {1: {},
           2: {'model_type': 'carbonate_water_soil_aquifer_karst_diagnostics_v2',
               'source_aquifer_model': 'natural_recharge_causal_aquifer_resources_v2',
               'domain': 'non_is_water_and_non_marine_water_body_type_cells',
               'marine_water_body_types': ['continental_shelf',
                                           'inland_sea',
                                           'ocean'],
               'carbonate_model': 'lithology_with_soil_ph_acidity_bonus_v1',
               'water_solution_model': 'precipitation_runoff_recharge_soil_moisture_index_v1',
               'relief_model': 'maximum_neighbor_absolute_elevation_difference_over_1800m_v1',
               'potential_model': 'carbonate_water_relief_soil_aquifer_storage_temperature_aridity_ice_index_v1',
               'cave_model': 'karst_relief_aquifer_storage_soil_profile_index_v1',
               'subterranean_model': 'karst_aquifer_productivity_soil_drainage_relief_index_v1',
               'system_grouping_model': 'mesh_neighbor_components_raw_karst_threshold_v1',
               'minimum_system_karst_potential_index': 0.45,
               'system_means': 'arithmetic_means_of_six_decimal_cell_outputs',
               'summary_means': 'arithmetic_means_of_unrounded_cell_diagnostics',
               'deterministic': True,
               'model_limitation': 'empirical_carbonate_water_soil_aquifer_diagnostic_without_dissolution_kinetics_saturation_conduit_geometry_or_transient_flow'}}}
_DYNAMIC = {'channel': ['planet_radius_km', 'candidate_cell_count', 'system_count'], 'hydraulics': ['gravity_m_s2', 'candidate_cell_count', 'reach_count'], 'karst': ['candidate_cell_count', 'system_count']}
_OWNED = {'channel': {'cell': ['bankfull_discharge_m3_s', 'channel_morphology_class', 'channel_slope_index', 'floodplain_connectivity_index', 'river_channel_depth_m', 'river_channel_system_id', 'river_channel_width_m', 'stream_power_index'], 'world': ['river_channel_morphology_model', 'river_channel_systems'], 'summary': ['channel_morphology_class_counts', 'floodplain_connected_channel_cell_count', 'high_stream_power_channel_cell_count', 'mean_bankfull_discharge_m3_s', 'mean_channel_slope_index', 'mean_river_channel_depth_m', 'mean_river_channel_width_m', 'mean_stream_power_index', 'navigable_channel_depth_cell_count', 'river_channel_cell_count', 'river_channel_morphology_model', 'river_channel_system_count', 'total_river_channel_length_km']}, 'hydraulics': {'cell': ['bed_shear_stress_pa', 'channel_capacity_index', 'flow_velocity_m_s', 'froude_number', 'hydraulic_flow_regime', 'hydraulic_navigability_index', 'hydraulic_radius_m', 'manning_roughness_n', 'river_hydraulic_reach_id'], 'world': ['river_hydraulic_reaches', 'river_hydraulics_model'], 'summary': ['high_shear_stress_cell_count', 'hydraulic_flow_regime_counts', 'hydraulically_navigable_cell_count', 'mean_bed_shear_stress_pa', 'mean_channel_capacity_index', 'mean_flow_velocity_m_s', 'mean_froude_number', 'mean_hydraulic_navigability_index', 'mean_hydraulic_radius_m', 'mean_manning_roughness_n', 'river_hydraulic_cell_count', 'river_hydraulic_reach_count', 'river_hydraulics_model', 'supercritical_flow_cell_count']}, 'karst': {'cell': ['cave_development_index', 'karst_potential_index', 'karst_system_id', 'subterranean_drainage_fraction'], 'world': ['karst_systems'], 'summary': ['karst_cell_count', 'karst_system_count', 'limestone_karst_cell_fraction', 'mean_cave_development_index', 'mean_karst_potential_index', 'mean_subterranean_drainage_fraction']}}
_KEYS = {'channel': 'river_channel_morphology_model', 'hydraulics': 'river_hydraulics_model', 'karst': 'karst_diagnostics_model'}
