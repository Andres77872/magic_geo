"""Independent typed contracts and replay for the versioned human water tail.

These are empirical navigation/port/corridor diagnostics. Matching natural
parents do not imply a vessel model, sustainable groundwater yield or survival.
"""
from __future__ import annotations

import math
from typing import Any

from .natural_channel_validation import (
    natural_downstream_model_version,
    validate_natural_river_hydraulics,
)
from .natural_groundwater_validation import (
    natural_groundwater_model_version,
    validate_natural_aquifer_resources,
)
from .planet_parameters import planet_radius_km


class HumanWaterTransportError(ValueError):
    """A malformed declaration, consumed source or replayed output."""


_KEYS = {'navigation': 'navigability_model', 'ports': 'port_site_model', 'corridors': 'route_corridor_model'}
_FAMILIES = {'navigation': 'navigable_waterways', 'ports': 'port_sites', 'corridors': 'route_corridors'}
_MARINE = {'ocean', 'continental_shelf', 'inland_sea'}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HumanWaterTransportError('human water transport: ' + message[:560])


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
    # Static constants retain their declared JSON types; bool is never a number.
    return type(actual) is type(expected) and actual == expected and (not isinstance(expected, float) or _finite(actual))


def _shape(world: Any) -> dict[int, dict[str, Any]]:
    _require(isinstance(world, dict), 'world must be an object')
    _require(world.get('generation_scope') != 'geo_only', 'human stages are inapplicable to declared geo_only output')
    _require(isinstance(world.get('summary', {}), dict), 'summary must be an object')
    cells = world.get('cells')
    _require(isinstance(cells, list) and bool(cells), 'nonempty cells required')
    result = {}
    for cell in cells:
        _require(isinstance(cell, dict), 'cells must contain objects')
        cid = cell.get('id')
        _require(type(cid) is int and cid >= 0 and cid not in result, 'cell IDs must be unique nonnegative integers')
        result[cid] = cell
    return result


def _declaration(world: dict[str, Any], stage: str, *, required: bool = False) -> int | None:
    key = _KEYS[stage]
    if key not in world:
        _require(not required, key + ' declaration required')
        _require(key not in world.get('summary', {}), key + ' summary lacks declaration')
        return None
    actual = world[key]
    _require(isinstance(actual, dict), key + ' must be an object')
    for version in (1, 2, 3):
        static = _POLICIES[stage][version]
        if actual.keys() != static.keys() | set(_DYNAMIC[stage]):
            continue
        if not all(_same(actual[k], v) for k, v in static.items()):
            continue
        for field in _DYNAMIC[stage]:
            value = actual[field]
            if version == 3 and field == 'candidate_cell_count' and value is None:
                continue
            if field.endswith('_count'):
                _require(type(value) is int and value >= 0, key + '.' + field + ' must be an exact nonnegative integer')
            else:
                _require(_finite(value) and value > 0, key + '.' + field + ' must be finite and positive')
        _require(world.get('summary', {}).get(key) == static['model_type'], key + ' summary identity mismatch')
        return version
    raise HumanWaterTransportError('human water transport: unknown or malformed ' + key)


def human_water_transport_model_version(world: Any, stage: str) -> int:
    """Use exact own/actual-parent declarations, never inferred numeric mirrors."""
    _require(type(stage) is str and stage in _KEYS, 'unknown stage')
    _shape(world)
    own = _declaration(world, stage)
    if stage == 'navigation':
        _require('river_hydraulics_model' in world and 'river_channel_morphology_model' in world, 'navigation requires channel and hydraulics declarations')
        parent = natural_downstream_model_version(world, 'hydraulics')
        settlement = world.get('settlement_selection_model')
        new_settlement = isinstance(settlement, dict) and settlement.get('model_type') == 'causal_native_score_local_max_separated_settlement_selection_v3'
        has_support = any('settlement_climate_supported' in cell or 'settlement_climate_temperature_c' in cell for cell in world['cells'])
        # Explicit historical own contracts retain their original declared
        # natural-parent scope; some retained archives already carry the old
        # isolated selection-v3 prototype. Only absent/current own dispatch
        # opts into the new availability equation family.
        if own not in (1, 2) and (new_settlement or has_support):
            _require(new_settlement and parent == 2, 'settlement-v3 requires its exact declaration and natural water-v2 parents')
            parent = 3
    elif stage == 'ports':
        parent = _declaration(world, 'navigation', required=True)
        _require(parent == human_water_transport_model_version(world, 'navigation'), 'navigation ancestry mismatch')
    else:
        parent = _declaration(world, 'ports', required=True)
        _require(parent == human_water_transport_model_version(world, 'ports'), 'port ancestry mismatch')
        _require(_declaration(world, 'navigation', required=True) == parent, 'corridor navigation version mismatch')
        _require('aquifer_resource_model' in world, 'corridors require aquifer declaration')
        _require(natural_groundwater_model_version(world, 'aquifer') == (2 if parent == 3 else parent), 'corridor aquifer version mismatch')
    _require(own is None or own == parent, stage + ' own and parent versions must match; deliberate upgrade must remove own and summary identities before recomputation')
    if parent != 3:
        additions = _AVAILABLE_ADDITIONS[stage]
        _require(not any(key in world.get('summary', {}) for key in additions['summary']), stage + ' historical declaration retains current availability summary')
        _require(not any(key in cell for cell in world['cells'] for key in additions['cell']), stage + ' historical declaration retains current availability fields')
        _require(not any(key in route for route in world.get('routes', []) if isinstance(route, dict) for key in additions['route']), stage + ' historical declaration retains current route availability')
    if parent == 3 and own is None:
        _require(_FAMILIES[stage] not in world, stage + ' absent declaration retains owned family; clear complete owned output before upgrade')
        fields = owned_fields(stage, 3)
        _require(not any(key in world.get('summary', {}) for key in fields['summary']), stage + ' absent declaration retains summary outputs')
        _require(not any(key in cell for cell in world['cells'] for key in fields['cell']), stage + ' absent declaration retains cell outputs')
        if fields['route']:
            _require(isinstance(world.get('routes'), list), 'routes required')
            _require(not any(key in route for route in world['routes'] if isinstance(route, dict) for key in fields['route']), stage + ' absent declaration retains route outputs')
    return parent if own is None else own


def _records(world: dict[str, Any], family: str) -> dict[int, dict[str, Any]]:
    rows = world.get(family)
    _require(isinstance(rows, list), family + ' must be a list')
    by_id = {}
    for row in rows:
        _require(isinstance(row, dict), family + ' must contain objects')
        rid = row.get('id')
        _require(type(rid) is int and rid >= 0 and rid not in by_id, family + ' IDs must be unique nonnegative integers')
        by_id[rid] = row
    return by_id


def _number(cell: dict[str, Any], *keys: str) -> None:
    for key in keys:
        _require(_finite(cell.get(key)), f"cell {cell['id']}: {key} must be finite numeric, not boolean")


def _string(cell: dict[str, Any], *keys: str) -> None:
    for key in keys:
        _require(type(cell.get(key)) is str and bool(cell[key]), f"cell {cell['id']}: {key} must be a nonempty string")


def _reference(value: Any, ids: dict[int, Any], path: str, *, sentinel: bool = True) -> None:
    _require(type(value) is int and (value in ids or (sentinel and value == -1)), path + ' must reference a known ID' + (' or -1' if sentinel else ''))


def _source_shape(world: dict[str, Any], stage: str, version: int = 2) -> None:
    cells = _shape(world)
    settlements = _records(world, 'settlements')
    routes = _records(world, 'routes')
    regions = _records(world, 'marine_regions')
    political = _records(world, 'political_regions')
    chokepoints = _records(world, 'marine_chokepoints')
    cp_cells = set()
    def numbers(cell, *keys):
        for key in keys:
            # Parent replay has already checked each new nullable value/flag.
            # Raw source descriptors never use this exception.
            if version == 3 and key in {'harbor_suitability_index', 'navigability_index', 'port_suitability_index'}:
                _require(key in cell, 'missing declared parent estimate ' + key)
                if cell[key] is None:
                    continue
            _number(cell, key)
    for rid, row in chokepoints.items():
        _reference(row.get('cell_id'), cells, f'marine_chokepoints[{rid}].cell_id', sentinel=False)
        _require(row['cell_id'] not in cp_cells, 'duplicate marine chokepoint source cell')
        cp_cells.add(row['cell_id'])
        _require(_finite(row.get('constriction_index')), 'marine chokepoint constriction must be finite')
        _require(type(row.get('type')) is str and bool(row['type']), 'marine chokepoint type required')
    for sid, row in settlements.items():
        # Missing-but-integer endpoint cells retain the historical route skip branch.
        _require(type(row.get('cell_id')) is int and row['cell_id'] >= -1, f'settlement {sid}: integer cell_id required')
        _require(type(row.get('type')) is str and bool(row['type']), f'settlement {sid}: type required')
        _reference(row.get('region_id'), political, f'settlement {sid}.region_id')
        if version == 3:
            _reference(row.get('cell_id'), cells, f'settlement {sid}.cell_id', sentinel=False)
    for rid, row in routes.items():
        for key in ('from', 'to'):
            _require(type(row.get(key)) is int and row[key] >= -1, f'route {rid}: integer {key} required')
            if version == 3:
                _reference(row[key], settlements, f'route {rid}.{key}', sentinel=False)
        _require(type(row.get('type')) is str and bool(row['type']), f'route {rid}: type required')
        if stage == 'corridors':
            _require(_finite(row.get('distance_km')), f'route {rid}: distance_km must be finite')
    for cid, cell in cells.items():
        _number(cell, 'area_km2', 'flow_accumulation', 'elevation_m')
        _require(cell['area_km2'] > 0, f'cell {cid}: positive area required')
        for key in ('is_water', 'is_river'):
            _require(type(cell.get(key)) is bool, f'cell {cid}: {key} must be boolean')
        _string(cell, 'water_body_type')
        neighbors = cell.get('neighbors')
        _require(isinstance(neighbors, list) and all(type(n) is int and n in cells for n in neighbors), f'cell {cid}: neighbors must reference known cells')
        _require(len(neighbors) == len(set(neighbors)) and cid not in neighbors, f'cell {cid}: duplicate/self neighbor')
        _require(all(isinstance(cells[n].get('neighbors'), list) and cid in cells[n]['neighbors'] for n in neighbors), f'cell {cid}: nonreciprocal neighbors')
        _require(all(_finite(cell['elevation_m'] - cells[n].get('elevation_m', math.nan)) for n in neighbors), f'cell {cid}: neighbor elevation difference unrepresentable')
        _reference(cell.get('marine_region_id'), regions, f'cell {cid}.marine_region_id')
        # Historical watershed_ids is the native basin/outlet-cell namespace.
        _reference(cell.get('basin_id'), cells, f'cell {cid}.basin_id')
        basin = cell['basin_id']
        if basin >= 0:
            outlet = cells[basin]
            _require(type(outlet.get('basin_id')) is int and outlet['basin_id'] == basin and type(outlet.get('flow_to')) is int and outlet['flow_to'] == -1, f'cell {cid}: basin_id must reference its native terminal outlet cell')
        _reference(cell.get('marine_chokepoint_id'), chokepoints, f'cell {cid}.marine_chokepoint_id')
        cp = cell['marine_chokepoint_id']
        if cp >= 0:
            _require(chokepoints[cp]['cell_id'] == cid, f'cell {cid}: marine chokepoint source mismatch')
        if cid in cp_cells:
            _require(cp >= 0, f'cell {cid}: marine chokepoint reverse link missing')
        marine = cell['water_body_type'] in _MARINE
        coastal = any(cells[n].get('water_body_type') in _MARINE for n in neighbors)
        if marine:
            _number(cell, 'water_depth_m')
        if stage == 'navigation':
            if not cell['is_water'] and cell['is_river']:
                _number(cell, 'runoff_mm_y', 'sediment_routing_load_m', 'river_channel_depth_m', 'river_channel_width_m', 'hydraulic_navigability_index', 'ice_thickness_m', 'seasonal_aridity_index')
                _string(cell, 'landform')
            if not marine and coastal:
                _string(cell, 'landform')
            if not cell['is_water'] and coastal:
                _number(cell, 'settlement_score', 'ice_thickness_m')
        elif stage == 'ports':
            numbers(cell, 'harbor_suitability_index', 'coastal_navigability_index', 'navigability_index', 'ice_thickness_m', 'lat_deg', 'lon_deg')
            _string(cell, 'biome', 'landform')
            if not cell['is_water']:
                _number(cell, 'settlement_score', 'temperature_c')
                if coastal and (cell['is_river'] or cell['landform'] in {'delta', 'floodplain', 'river_valley'}):
                    _number(cell, 'runoff_mm_y')
        else:
            numbers(cell, 'lat_deg', 'lon_deg', 'ice_thickness_m', 'seasonal_aridity_index', 'river_navigability_index', 'coastal_navigability_index', 'harbor_suitability_index', 'transport_chokepoint_index', 'navigability_index', 'port_suitability_index')
            _string(cell, 'landform')
            if not (cell['is_water'] and marine):
                _number(cell, 'runoff_mm_y')
            if not cell['is_water']:
                _require(type(cell.get('is_lake')) is bool, f'cell {cid}: is_lake must be boolean')
                _number(cell, 'boundary_convergent', 'fertility', 'groundwater_recharge_mm_y', 'aquifer_productivity_index', 'soil_moisture_index')
                _string(cell, 'biome')
        if stage != 'navigation':
            _require(-90 <= cell['lat_deg'] <= 90 and -180 <= cell['lon_deg'] <= 180, f'cell {cid}: invalid latitude/longitude')
    if stage == 'corridors':
        _require(_finite(2 * math.pi * planet_radius_km(world)), 'configured planet circumference unrepresentable')


def _preflight(world: Any, stage: str, audited: set[str]) -> int:
    version = human_water_transport_model_version(world, stage)
    if 'natural' not in audited:
        errors = validate_natural_river_hydraulics(world)
        _require(not errors, 'invalid natural hydraulic parent: ' + (errors[0] if errors else ''))
        audited.add('natural')
    if stage in ('ports', 'corridors') and 'navigation' not in audited:
        _audit(world, 'navigation', audited)
    if stage == 'corridors' and 'ports' not in audited:
        _audit(world, 'ports', audited)
    if stage == 'corridors' and 'aquifer' not in audited:
        errors = validate_natural_aquifer_resources(world)
        _require(not errors, 'invalid natural aquifer parent: ' + (errors[0] if errors else ''))
        audited.add('aquifer')
    _source_shape(world, stage, version)
    if version == 3 and 'settlement' not in audited:
        from ._human_water_availability_replay import _site_availability
        _site_availability(world)
        audited.add('settlement')
    return version


def validate_human_water_transport_inputs(world: Any, stage: str) -> int:
    """Read-only preflight before publication; raises a bounded ValueError."""
    try:
        return _preflight(world, stage, set())
    except HumanWaterTransportError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, ArithmeticError) as exc:
        raise HumanWaterTransportError('human water transport: invalid ' + stage + ' source (' + type(exc).__name__ + '): ' + str(exc)[:350]) from exc


def _typed_output(value: Any, key: str) -> None:
    if key.endswith('_ids'):
        _require(isinstance(value, list) and all(type(v) is int and v >= 0 for v in value), key + ' must contain nonnegative integer IDs')
    elif key == 'id' or key.endswith(('_id', '_count')):
        _require(type(value) is int and value >= (-1 if key.endswith('_id') else 0), key + ' must be an exact integer')
    elif key.endswith('_counts'):
        _require(isinstance(value, dict) and all(type(k) is str and type(v) is int and v >= 0 for k, v in value.items()), key + ' must contain exact counts')
    elif key.startswith(('selected_by_', 'is_')):
        _require(type(value) is bool, key + ' must be boolean')
    elif key.endswith(('_type', '_class', '_model')) or key in ('landform', 'biome'):
        _require(type(value) is str, key + ' must be a string')
    else:
        _require(_finite(value), key + ' must be finite numeric')


def _owned_shape(world: dict[str, Any], stage: str) -> None:
    _declaration(world, stage, required=True)
    for cell in world['cells']:
        for key in _OWNED[stage]['cell']:
            _require(key in cell, f"cell {cell['id']}: missing " + key)
            _typed_output(cell[key], key)
    summary = world['summary']
    for key in _OWNED[stage]['summary']:
        _require(key in summary, 'missing summary ' + key)
        _typed_output(summary[key], key)
    records = _records(world, _FAMILIES[stage])
    for index, row in enumerate(records.values()):
        _require(row['id'] == index, _FAMILIES[stage] + ' record IDs/order must be dense')
        _require(row.keys() == set(_RECORD_FIELDS[stage]), _FAMILIES[stage] + ' record fields mismatch')
        for key, value in row.items():
            _typed_output(value, key)
    if stage == 'corridors':
        for route in world['routes']:
            for key in _OWNED[stage]['route']:
                _require(key in route, 'route missing ' + key)
                _typed_output(route[key], key)


def _legacy_view(world: dict[str, Any], stage: str) -> dict[str, Any]:
    """Unpublished metadata-only view for an already audited exact contract.

    All numerical inputs/outputs remain the actual values. This is never sent
    to a producer or returned as a world; it only selects unchanged old math.
    """
    view = dict(world)
    view['summary'] = dict(world['summary'])
    key = _KEYS[stage]
    view[key] = {**_POLICIES[stage][1], **{k: world[key][k] for k in _DYNAMIC[stage]}}
    view['summary'][key] = _POLICIES[stage][1]['model_type']
    return view


def _audit(world: Any, stage: str, audited: set[str]) -> None:
    version = _preflight(world, stage, audited)
    if version == 3:
        _declaration(world, stage, required=True)
        from ._human_water_availability_replay import audit_available_stage
        audit_available_stage(world, stage)
        audited.add(stage)
        return
    _owned_shape(world, stage)
    from ._human_water_replay import _validate_navigability, _validate_port_sites, _validate_route_corridors
    replay = {'navigation': _validate_navigability, 'ports': _validate_port_sites, 'corridors': _validate_route_corridors}[stage]
    view = _legacy_view(world, stage)
    errors = replay(view, view['summary'], {c['id']: c for c in view['cells']})
    _require(not errors, stage + ': ' + (errors[0] if errors else 'causal replay invalid'))
    audited.add(stage)


def validate_human_water_transport(world: Any, stage: str = 'corridors') -> list[str]:
    """At most one actionable diagnostic; no world mutation or producer imports."""
    try:
        _require(type(stage) is str and stage in _KEYS, 'unknown stage')
        _audit(world, stage, set())
        return []
    except HumanWaterTransportError as exc:
        return [str(exc)[:600]]
    except (ValueError, TypeError, KeyError, OverflowError, ArithmeticError) as exc:
        return ['human water transport: malformed ' + stage + ' input or output (' + type(exc).__name__ + ')']


def validate_versioned_navigability(world: Any) -> list[str]:
    return validate_human_water_transport(world, 'navigation')


def validate_versioned_port_sites(world: Any) -> list[str]:
    return validate_human_water_transport(world, 'ports')


def validate_versioned_route_corridors(world: Any) -> list[str]:
    return validate_human_water_transport(world, 'corridors')


_POLICIES = {'navigation': {1: {'model_type': 'causal_channel_hydraulic_coastal_navigability_v1',
                    'source_channel_model': 'causal_flow_sediment_wetland_baseflow_channel_morphology_v1',
                    'source_hydraulics_model': 'manning_blended_diagnostic_river_hydraulics_v1',
                    'domain': 'all_cells',
                    'flow_normalization_model': 'global_max_flow_accumulation_v1',
                    'river_model': 'flow_runoff_lowland_relief_sediment_channel_hydraulic_ice_aridity_v1',
                    'coastal_model': 'marine_depth_shelf_land_contact_constriction_or_coastal_land_context_v1',
                    'harbor_model': 'coastal_protection_river_mouth_relief_settlement_ice_v1',
                    'transport_chokepoint_model': 'marine_constriction_and_coastal_navigability_v1',
                    'overall_model': 'maximum_component_navigability_v1',
                    'classification_model': 'chokepoint_harbor_river_mouth_river_coastal_priority_v1',
                    'system_grouping_model': 'undirected_mesh_connected_raw_threshold_components_v1',
                    'link_model': 'component_cell_settlement_route_marine_region_watershed_links_v1',
                    'navigable_threshold': 0.52,
                    'high_harbor_threshold': 0.62,
                    'transport_chokepoint_threshold': 0.55,
                    'threshold_semantics': 'unrounded_pre_serialization_values',
                    'deterministic': True,
                    'model_limitation': 'diagnostic_transport_suitability_without_vessel_classes_seasonal_discharge_bathymetric_channels_or_route_cost_optimization'},
                2: {'model_type': 'causal_channel_hydraulic_coastal_navigability_v2',
                    'source_channel_model': 'causal_flow_sediment_wetland_baseflow_channel_morphology_v2',
                    'source_hydraulics_model': 'manning_blended_diagnostic_river_hydraulics_v2',
                    'domain': 'all_cells',
                    'flow_normalization_model': 'global_max_flow_accumulation_v1',
                    'river_model': 'flow_runoff_lowland_relief_sediment_channel_hydraulic_ice_aridity_v1',
                    'coastal_model': 'marine_depth_shelf_land_contact_constriction_or_coastal_land_context_v1',
                    'harbor_model': 'coastal_protection_river_mouth_relief_settlement_ice_v1',
                    'transport_chokepoint_model': 'marine_constriction_and_coastal_navigability_v1',
                    'overall_model': 'maximum_component_navigability_v1',
                    'classification_model': 'chokepoint_harbor_river_mouth_river_coastal_priority_v1',
                    'system_grouping_model': 'undirected_mesh_connected_raw_threshold_components_v1',
                    'link_model': 'component_cell_settlement_route_marine_region_watershed_links_v1',
                    'navigable_threshold': 0.52,
                    'high_harbor_threshold': 0.62,
                    'transport_chokepoint_threshold': 0.55,
                    'threshold_semantics': 'unrounded_pre_serialization_values',
                    'deterministic': True,
                    'model_limitation': 'diagnostic_transport_suitability_without_vessel_classes_seasonal_discharge_bathymetric_channels_or_route_cost_optimization',
                    'watershed_link_basis': 'native_cell_basin_ids_not_watershed_record_ids'}},
 'ports': {1: {'model_type': 'causal_navigability_coastal_port_site_selection_v1',
               'source_navigability_model': 'causal_channel_hydraulic_coastal_navigability_v1',
               'domain': 'all_cells_with_land_only_selection',
               'protected_bay_model': 'marine_contact_protected_water_enclosure_depth_harbor_v1',
               'river_mouth_model': 'river_landform_flow_runoff_delta_harbor_v1',
               'strait_access_model': 'adjacent_marine_chokepoint_constriction_and_coastal_access_v1',
               'suitability_model': 'harbor_bay_river_strait_coastal_settlement_climate_ice_relief_v1',
               'classification_model': 'strait_river_mouth_protected_bay_harbor_coastal_priority_v1',
               'selection_model': 'raw_suitability_without_severe_ice_or_port_settlement_override_v1',
               'record_order': 'ascending_candidate_cell_id',
               'link_model': 'cell_settlement_route_marine_region_chokepoint_nearby_waterway_links_v1',
               'port_site_threshold': 0.58,
               'protected_bay_threshold': 0.55,
               'river_mouth_threshold': 0.5,
               'strait_access_threshold': 0.55,
               'threshold_semantics': 'unrounded_pre_serialization_values_except_record_flags_use_serialized_fields',
               'deterministic': True,
               'model_limitation': 'diagnostic_port_suitability_without_harbor_bathymetry_tides_waves_sedimentation_engineering_or_economic_optimization'},
           2: {'model_type': 'causal_navigability_coastal_port_site_selection_v2',
               'source_navigability_model': 'causal_channel_hydraulic_coastal_navigability_v2',
               'domain': 'all_cells_with_land_only_selection',
               'protected_bay_model': 'marine_contact_protected_water_enclosure_depth_harbor_v1',
               'river_mouth_model': 'river_landform_flow_runoff_delta_harbor_v1',
               'strait_access_model': 'adjacent_marine_chokepoint_constriction_and_coastal_access_v1',
               'suitability_model': 'harbor_bay_river_strait_coastal_settlement_climate_ice_relief_v1',
               'classification_model': 'strait_river_mouth_protected_bay_harbor_coastal_priority_v1',
               'selection_model': 'raw_suitability_without_severe_ice_or_port_settlement_override_v1',
               'record_order': 'ascending_candidate_cell_id',
               'link_model': 'cell_settlement_route_marine_region_chokepoint_nearby_waterway_links_v1',
               'port_site_threshold': 0.58,
               'protected_bay_threshold': 0.55,
               'river_mouth_threshold': 0.5,
               'strait_access_threshold': 0.55,
               'threshold_semantics': 'unrounded_pre_serialization_values_except_record_flags_use_serialized_fields',
               'deterministic': True,
               'model_limitation': 'diagnostic_port_suitability_without_harbor_bathymetry_tides_waves_sedimentation_engineering_or_economic_optimization'}},
 'corridors': {1: {'model_type': 'causal_feature_weighted_dijkstra_route_corridors_v1',
                   'source_navigability_model': 'causal_channel_hydraulic_coastal_navigability_v1',
                   'source_port_model': 'causal_navigability_coastal_port_site_selection_v1',
                   'source_aquifer_model': 'finite_recharge_causal_aquifer_resources_v1',
                   'domain': 'all_cells_with_one_path_per_valid_route',
                   'mountain_pass_model': 'neighbor_saddle_convergence_landform_relief_elevation_ice_v1',
                   'river_valley_model': 'flow_runoff_river_landform_relief_navigability_ice_v1',
                   'coastal_model': 'marine_or_coastal_contact_navigability_harbor_port_depth_relief_v1',
                   'oasis_model': 'aridity_water_recharge_aquifer_soil_fertility_settlement_ice_v1',
                   'movement_cost_model': 'directed_distance_terrain_water_route_type_feature_support_v1',
                   'path_model': 'strict_improvement_dijkstra_cost_then_cell_id_heap_v1',
                   'corridor_classification_model': 'route_type_preference_then_feature_count_lexical_tie_v1',
                   'cell_assignment_model': 'maximum_membership_with_later_route_winning_equal_ties_v1',
                   'record_order': 'ascending_route_id_for_valid_endpoints_and_paths',
                   'feature_threshold': 0.45,
                   'threshold_semantics': 'serialized_feature_indices',
                   'deterministic': True,
                   'model_limitation': 'diagnostic_static_corridors_without_capacity_congestion_seasonality_construction_cost_network_equilibrium_or_multimodal_scheduling'},
               2: {'model_type': 'causal_feature_weighted_dijkstra_route_corridors_v2',
                   'source_navigability_model': 'causal_channel_hydraulic_coastal_navigability_v2',
                   'source_port_model': 'causal_navigability_coastal_port_site_selection_v2',
                   'source_aquifer_model': 'natural_recharge_causal_aquifer_resources_v2',
                   'domain': 'all_cells_with_one_path_per_valid_route',
                   'mountain_pass_model': 'neighbor_saddle_convergence_landform_relief_elevation_ice_v1',
                   'river_valley_model': 'flow_runoff_river_landform_relief_navigability_ice_v1',
                   'coastal_model': 'marine_or_coastal_contact_navigability_harbor_port_depth_relief_v1',
                   'oasis_model': 'aridity_water_recharge_aquifer_soil_fertility_settlement_ice_v1',
                   'movement_cost_model': 'directed_distance_terrain_water_route_type_feature_support_v1',
                   'path_model': 'strict_improvement_dijkstra_cost_then_cell_id_heap_v1',
                   'corridor_classification_model': 'route_type_preference_then_feature_count_lexical_tie_v1',
                   'cell_assignment_model': 'maximum_membership_with_later_route_winning_equal_ties_v1',
                   'record_order': 'ascending_route_id_for_valid_endpoints_and_paths',
                   'feature_threshold': 0.45,
                   'threshold_semantics': 'serialized_feature_indices',
                   'deterministic': True,
                   'model_limitation': 'diagnostic_static_corridors_without_capacity_congestion_seasonality_construction_cost_network_equilibrium_or_multimodal_scheduling'}}}

_DYNAMIC = {'navigation': ['candidate_cell_count', 'waterway_count'], 'ports': ['candidate_cell_count', 'site_count'], 'corridors': ['route_count', 'corridor_count', 'planet_radius_km']}

_OWNED = {'navigation': {'cell': ['coastal_navigability_index',
                         'harbor_suitability_index',
                         'navigability_class',
                         'navigability_index',
                         'navigable_waterway_id',
                         'river_navigability_index',
                         'transport_chokepoint_index'],
                'route': [],
                'summary': ['high_harbor_suitability_cell_count',
                            'mean_coastal_navigability_index',
                            'mean_harbor_suitability_index',
                            'mean_navigability_index',
                            'mean_river_navigability_index',
                            'mean_transport_chokepoint_index',
                            'navigability_class_counts',
                            'navigability_model',
                            'navigable_cell_count',
                            'navigable_waterway_count',
                            'navigable_waterway_total_area_km2',
                            'transport_chokepoint_cell_count']},
 'ports': {'cell': ['port_site_id',
                    'port_site_type',
                    'port_suitability_index',
                    'protected_bay_index',
                    'river_mouth_port_index',
                    'strait_access_index'],
           'route': [],
           'summary': ['mean_port_suitability_index',
                       'mean_protected_bay_index',
                       'mean_river_mouth_port_index',
                       'mean_strait_access_index',
                       'port_candidate_cell_count',
                       'port_settlement_count',
                       'port_settlement_with_site_count',
                       'port_site_count',
                       'port_site_model',
                       'port_site_total_area_km2',
                       'port_site_type_counts',
                       'protected_bay_port_site_count',
                       'river_mouth_port_site_count',
                       'strait_port_site_count']},
 'corridors': {'cell': ['coastal_route_index',
                        'mountain_pass_route_index',
                        'oasis_route_index',
                        'river_valley_route_index',
                        'route_corridor_id',
                        'route_corridor_index',
                        'route_corridor_type'],
               'route': ['path_cell_ids',
                         'route_corridor_id',
                         'route_corridor_type'],
               'summary': ['coastal_route_corridor_count',
                           'mean_coastal_route_index',
                           'mean_mountain_pass_route_index',
                           'mean_oasis_route_index',
                           'mean_river_valley_route_index',
                           'mean_route_corridor_index',
                           'mountain_pass_route_corridor_count',
                           'oasis_route_corridor_count',
                           'river_valley_route_corridor_count',
                           'route_corridor_cell_count',
                           'route_corridor_count',
                           'route_corridor_model',
                           'route_corridor_total_path_length_km',
                           'route_corridor_type_counts',
                           'route_feature_coverage_index']}}

_RECORD_FIELDS = {'navigation': ['id',
                'waterway_type',
                'cell_count',
                'cell_ids',
                'area_km2',
                'mean_navigability_index',
                'mean_river_navigability_index',
                'mean_coastal_navigability_index',
                'max_harbor_suitability_index',
                'transport_chokepoint_cell_count',
                'settlement_ids',
                'route_ids',
                'marine_region_ids',
                'watershed_ids'],
 'ports': ['id',
           'cell_id',
           'site_type',
           'area_km2',
           'latitude_deg',
           'longitude_deg',
           'port_suitability_index',
           'protected_bay_index',
           'river_mouth_port_index',
           'strait_access_index',
           'harbor_suitability_index',
           'navigability_index',
           'settlement_ids',
           'port_settlement_ids',
           'route_ids',
           'marine_region_ids',
           'marine_chokepoint_ids',
           'navigable_waterway_ids',
           'landform',
           'biome',
           'water_body_type',
           'is_river',
           'selected_by_port_settlement',
           'selected_by_suitability'],
 'corridors': ['id',
               'route_id',
               'route_type',
               'corridor_type',
               'from_settlement_id',
               'to_settlement_id',
               'start_cell_id',
               'end_cell_id',
               'cell_count',
               'cell_ids',
               'path_length_km',
               'straight_distance_km',
               'detour_ratio',
               'mean_route_corridor_index',
               'max_route_corridor_index',
               'mean_mountain_pass_route_index',
               'mean_river_valley_route_index',
               'mean_coastal_route_index',
               'mean_oasis_route_index',
               'mountain_pass_cell_count',
               'river_valley_cell_count',
               'coastal_cell_count',
               'oasis_cell_count',
               'named_feature_cell_count',
               'settlement_ids',
               'region_ids',
               'route_ids',
               'navigable_waterway_ids',
               'port_site_ids']}


# The independent policies and equations never import producer modules.
from ._human_water_availability_replay import POLICIES as _AVAILABLE_POLICIES
for _stage, _policy in _AVAILABLE_POLICIES.items():
    _POLICIES[_stage][3] = _policy

_AVAILABLE_ADDITIONS = {
    'navigation': {
        'cell': ['harbor_site_applicable', 'harbor_suitability_supported', 'navigability_supported', 'navigability_classification_supported', 'navigable_waterway_membership_complete'],
        'route': [],
        'summary': ['navigable_waterway_selection_complete', 'navigability_estimates_complete', 'harbor_site_applicable_cell_count', 'harbor_site_supported_cell_count', 'navigability_supported_cell_count'],
    },
    'ports': {
        'cell': ['protected_bay_supported', 'river_mouth_port_supported', 'port_suitability_supported', 'port_site_selection_supported'],
        'route': [],
        'summary': ['mean_protected_bay_supported', 'mean_river_mouth_port_supported', 'mean_port_suitability_supported', 'port_site_selection_complete', 'port_site_applicable_cell_count', 'port_site_supported_cell_count'],
    },
    'corridors': {
        'cell': ['coastal_route_supported', 'route_corridor_membership_complete'],
        'route': ['route_path_supported', 'route_corridor_diagnostics_supported'],
        'summary': ['route_path_selection_complete', 'route_corridor_diagnostics_complete', 'route_corridor_membership_complete', 'coastal_route_estimates_complete', 'route_path_supported_count', 'route_corridor_diagnostics_supported_count'],
    },
}


def owned_fields(stage: str, version: int) -> dict[str, list[str]]:
    """Exact per-stage output ownership for publication and deliberate upgrades."""
    return {kind: fields + (_AVAILABLE_ADDITIONS[stage][kind] if version == 3 else []) for kind, fields in _OWNED[stage].items()}
