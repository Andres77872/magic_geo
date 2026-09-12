"""Independent v3 replay; no producer equation or availability-helper imports.

Scalar laws below are preserved from the pre-existing independent human-water
oracle. Availability, coverage, expected records and comparisons are separate
from the owning producers. Historical v1/v2 replay remains byte-unchanged.
"""
from __future__ import annotations
import heapq
import math
from collections import Counter
from typing import Any
from .planet_parameters import planet_radius_km as configured_planet_radius_km


def _average(values):
    if any(value is None for value in values):
        return None
    return round(sum(values) / len(values), 6)


def _site_availability(world):
    """Independent source decision; never use producer's input-state helper."""
    from .cli.validators.settlement_climate import replay_settlement_climate
    from .cli.validators.settlement import _validate_settlement_selection, _validate_route_network
    _strict_site_shape(world)
    model, temperatures = replay_settlement_climate(world)
    if model != 'causal_native_score_local_max_separated_settlement_selection_v3' or temperatures is None:
        raise ValueError('settlement-v3 annual source required')
    cells = {cell['id']: cell for cell in world['cells']}
    if _validate_settlement_selection(world, world['summary'], cells) or _validate_route_network(world, world['summary'], cells):
        raise ValueError('independent settlement/route replay failed')
    result = {}
    for cid, cell in cells.items():
        if type(cell.get('is_lake')) is not bool or type(cell.get('is_water')) is not bool:
            raise ValueError('typed native water selectors required')
        value = cell.get('settlement_score')
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('finite native score required')
        water = cell['is_lake'] or cell['is_water']
        climate = -14 < temperatures[cid] < 48
        if (water or not climate) and value != 0:
            raise ValueError('native structural/unavailable zero mismatch')
        result[cid] = water or climate
    return result


def _strict_site_shape(world):
    """Typed source schema supplements the older numerical parent oracle.

    Constants/equations are checked by that independent oracle. These exact
    field/type sets close its historical coercions without a producer import.
    """
    def finite(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('finite typed native source number required')
    schemas = {
        'settlement_selection_model': {
            'string': 'model_type score_model candidate_model rank_model selection_model target_model type_model threshold_and_rank_semantics formula_replay_tolerance_model record_order model_limitation'.split(),
            'integer': 'target_cell_divisor target_minimum target_maximum selection_score_precision candidate_cell_count target_count settlement_count'.split(),
            'float': 'score_threshold minimum_separation_factor cold_biome_multiplier'.split(),
            'dict': 'score_weights hazard_weights landform_score_adjustments annual_climate_applicability'.split(),
        },
        'route_network_model': {
            'string': 'model_type source_settlement_model ranking_model barrier_model selection_model route_type_model record_order planet_radius_source model_limitation'.split(),
            'integer': 'links_per_settlement settlement_count route_count'.split(),
            'float': 'mountain_route_elevation_threshold_m mountain_route_convergence_threshold'.split(),
            'dict': 'barrier_parameters ranking_discounts'.split(),
        },
    }
    for key, schema in schemas.items():
        value = world.get(key)
        fields = {'deterministic'} | {field for names in schema.values() for field in names}
        if type(value) is not dict or value.keys() != fields or value.get('deterministic') is not True:
            raise ValueError('exact native parent declaration required: ' + key)
        for field in schema['string']:
            if type(value[field]) is not str:
                raise ValueError('typed native model string required')
        for field in schema['integer']:
            if type(value[field]) is not int or value[field] < 0:
                raise ValueError('typed native model integer required')
        for field in schema['float']:
            if type(value[field]) is not float or not math.isfinite(value[field]):
                raise ValueError('typed native model coefficient required')
        for field in schema['dict']:
            if type(value[field]) is not dict:
                raise ValueError('typed native model object required')
            if field != 'annual_climate_applicability' and any(type(item) is not float or not math.isfinite(item) for item in value[field].values()):
                raise ValueError('typed native nested coefficient required')
    summary = world['summary']
    precision = summary.get('output_float_precision')
    if type(precision) is not int or not 0 <= precision <= 8:
        raise ValueError('typed native output precision required')
    if type(summary.get('settlement_count')) is not int or summary['settlement_count'] != len(world['settlements']):
        raise ValueError('typed selected-settlement summary required')
    for cell in world['cells']:
        for key in ('is_water', 'is_lake', 'is_river', 'settlement_climate_supported'):
            if type(cell.get(key)) is not bool:
                raise ValueError('typed native settlement selector required')
        for key in ('settlement_score', 'settlement_climate_temperature_c', 'elevation_m', 'runoff_mm_y', 'precipitation_mm_y', 'ice_thickness_m', 'lat_deg', 'boundary_convergent', 'boundary_transform', 'boundary_divergent', 'crust_age_ma', 'sediment_thickness_m'):
            finite(cell.get(key))
        for key in ('lithology', 'crust_type', 'landform'):
            if type(cell.get(key)) is not str:
                raise ValueError('typed native settlement descriptor required')
        for key, size in (('position_3d', 3), ('temperature_monthly_c', 12), ('precipitation_monthly_mm', 12)):
            values = cell.get(key)
            if type(values) is not list or len(values) != size:
                raise ValueError('complete native settlement vector required')
            for value in values:
                finite(value)
    for row in world['settlements']:
        for key in ('score', 'fertility', 'lat_deg', 'lon_deg'):
            finite(row.get(key))
        for key in ('type', 'biome', 'resource', 'water_body_type'):
            if type(row.get(key)) is not str:
                raise ValueError('typed selected-site descriptor required')
        if type(row.get('is_river')) is not bool:
            raise ValueError('typed selected-site river flag required')
    for row in world['routes']:
        for key in ('cost', 'distance_km'):
            finite(row.get(key))


def _link_maps(world):
    settlements = {}
    routes = {}
    for row in world['settlements']:
        settlements.setdefault(row['cell_id'], []).append(row)
    for row in world['routes']:
        for key in ('from', 'to'):
            if row[key] >= 0:
                routes.setdefault(row[key], set()).add(row['id'])
    return settlements, routes


def expected_navigation(world, site_available):
    by_id = {cell['id']: cell for cell in world['cells']}
    math_ = _navigation_math(world)
    raw = {}
    expected = {}
    candidate_ids = set()
    for cid, cell in by_id.items():
        habitat = not cell['is_water'] and bool(math_['marine_neighbors'](cell))
        support = site_available[cid] if habitat else True
        river = math_['river_navigability'](cell)
        coast = math_['coastal_navigability'](cell)
        choke = math_['transport_chokepoint'](cell, coast)
        harbor = math_['harbor_suitability'](cell, coast) if support else None
        total = max(river, coast, harbor, choke) if support else None
        raw[cid] = [river, coast, harbor, choke, total]
        expected[cid] = {
            'harbor_site_applicable': habitat,
            'harbor_suitability_supported': support,
            'navigability_supported': support,
            'navigability_classification_supported': support,
            'river_navigability_index': round(river, 6),
            'coastal_navigability_index': round(coast, 6),
            'harbor_suitability_index': round(harbor, 6) if support else None,
            'transport_chokepoint_index': round(choke, 6),
            'navigability_index': round(total, 6) if support else None,
            'navigability_class': math_['classify'](river, coast, harbor, choke) if support else None,
        }
        if support and total >= .52:
            candidate_ids.add(cid)
    complete = all(row['navigability_supported'] for row in expected.values())
    for row in expected.values():
        row['navigable_waterway_membership_complete'] = complete
        row['navigable_waterway_id'] = -1 if complete else None
    groups = []
    remaining = candidate_ids.copy() if complete else set()
    while remaining:
        queue = [min(remaining)]
        remaining.remove(queue[0])
        for cid in queue:
            for nid in by_id[cid]['neighbors']:
                if nid in remaining:
                    queue.append(nid)
                    remaining.remove(nid)
        groups.append(sorted(queue))
    settlements, route_map = _link_maps(world)
    records = []
    for group in groups:
        idx = len(records)
        for cid in group:
            expected[cid]['navigable_waterway_id'] = idx
        classes = {expected[cid]['navigability_class'] for cid in group}
        kind = next((label for key, label in [('transport_chokepoint', 'transport_chokepoint'), ('river_mouth', 'river_mouth_corridor'), ('harbor', 'harbor_cluster'), ('river_corridor', 'river_corridor')] if key in classes), 'coastal_corridor')
        sids = sorted({row['id'] for cid in group for row in settlements.get(cid, [])})
        records.append({
            'id': idx, 'waterway_type': kind, 'cell_count': len(group), 'cell_ids': group,
            'area_km2': round(sum(max(0.0, float(by_id[cid]['area_km2'])) for cid in group), 6),
            'mean_navigability_index': _average([expected[cid]['navigability_index'] for cid in group]),
            'mean_river_navigability_index': _average([expected[cid]['river_navigability_index'] for cid in group]),
            'mean_coastal_navigability_index': _average([expected[cid]['coastal_navigability_index'] for cid in group]),
            'max_harbor_suitability_index': round(max(expected[cid]['harbor_suitability_index'] for cid in group), 6),
            'transport_chokepoint_cell_count': sum(expected[cid]['transport_chokepoint_index'] >= .55 for cid in group),
            'settlement_ids': sids,
            'route_ids': sorted({rid for sid in sids for rid in route_map.get(sid, set())}),
            'marine_region_ids': sorted({by_id[cid]['marine_region_id'] for cid in group if by_id[cid]['marine_region_id'] >= 0}),
            'watershed_ids': sorted({by_id[cid]['basin_id'] for cid in group if by_id[cid]['basin_id'] >= 0}),
        })
    summary = {
        'navigability_model': POLICIES['navigation']['model_type'],
        'navigable_cell_count': len(candidate_ids) if complete else None,
        'navigable_waterway_count': len(records),
        'navigable_waterway_total_area_km2': round(sum(row['area_km2'] for row in records), 6) if complete else None,
        'high_harbor_suitability_cell_count': sum(value[2] >= .62 for value in raw.values()) if complete else None,
        'transport_chokepoint_cell_count': sum(value[3] >= .55 for value in raw.values()),
        'navigability_class_counts': dict(sorted(Counter(row['navigability_class'] for row in expected.values()).items())) if complete else None,
        'navigable_waterway_selection_complete': complete, 'navigability_estimates_complete': complete,
        'harbor_site_applicable_cell_count': sum(row['harbor_site_applicable'] for row in expected.values()),
        'harbor_site_supported_cell_count': sum(row['harbor_site_applicable'] and row['harbor_suitability_supported'] for row in expected.values()),
        'navigability_supported_cell_count': sum(row['navigability_supported'] for row in expected.values()),
    }
    for pos, name in enumerate(('river_navigability', 'coastal_navigability', 'harbor_suitability', 'transport_chokepoint', 'navigability')):
        summary['mean_' + name + '_index'] = _average([value[pos] for value in raw.values()])
    return {'cell': expected, 'summary': summary, 'records': records, 'route': {},
            'dynamic': {'candidate_cell_count': len(candidate_ids) if complete else None, 'waterway_count': len(records)}}


def expected_ports(world, site_available):
    by_id = {cell['id']: cell for cell in world['cells']}
    math_ = _port_math(world)
    settlements, route_map = _link_maps(world)
    forced = {cid for cid, rows in settlements.items() if any(row['type'] == 'port' for row in rows)}
    expected, raw, chosen = {}, {}, set()
    for cid, cell in by_id.items():
        marine = math_['marine_neighbors'](cell)
        bay_uses_harbor = not cell['is_water'] and len(marine) > 0
        mouth_uses_harbor = bay_uses_harbor and (cell['is_river'] or cell['landform'] in {'delta', 'floodplain', 'river_valley'})
        bay_supported = not bay_uses_harbor or cell['harbor_suitability_supported']
        mouth_supported = not mouth_uses_harbor or cell['harbor_suitability_supported']
        estimate_supported = cell['is_water'] or (site_available[cid] and cell['harbor_suitability_supported'] and bay_supported and mouth_supported)
        selection_supported = estimate_supported and bay_supported and mouth_supported and cell['harbor_suitability_supported']
        bay = math_['protected_bay'](cell, marine) if bay_supported else None
        mouth = math_['river_mouth'](cell, marine) if mouth_supported else None
        strait = math_['strait_access'](cell, marine)
        score = math_['suitability'](cell, bay, mouth, strait) if estimate_supported else None
        raw[cid] = [bay, mouth, strait, score]
        ice = cell['ice_thickness_m'] >= 80 or cell['biome'] == 'ice_cap'
        selected = selection_supported and not cell['is_water'] and ((score >= .58 and not ice) or cid in forced)
        category = math_['site_type'](bay, mouth, strait, cell['harbor_suitability_index'], score) if selection_supported else None
        if selected:
            chosen.add(cid)
        expected[cid] = {
            'protected_bay_supported': bay_supported, 'river_mouth_port_supported': mouth_supported,
            'port_suitability_supported': estimate_supported, 'port_site_selection_supported': selection_supported,
            'protected_bay_index': round(bay, 6) if bay_supported else None,
            'river_mouth_port_index': round(mouth, 6) if mouth_supported else None,
            'strait_access_index': round(strait, 6),
            'port_suitability_index': round(score, 6) if estimate_supported else None,
            'port_site_id': -1 if selection_supported else None,
            'port_site_type': (category if selected and category != 'none' else 'none') if selection_supported else None,
        }
    records = []
    links_complete = world['summary']['navigable_waterway_selection_complete']
    for cid in sorted(chosen):
        expected[cid]['port_site_id'] = len(records)
        if expected[cid]['port_site_type'] == 'none':
            expected[cid]['port_site_type'] = 'port_settlement'
        cell = by_id[cid]
        own = expected[cid]
        marine = math_['marine_neighbors'](cell)
        sids = sorted(row['id'] for row in settlements.get(cid, []))
        pids = sorted(row['id'] for row in settlements.get(cid, []) if row['type'] == 'port')
        near = {cid, *cell['neighbors']}
        record = {
            'id': own['port_site_id'], 'cell_id': cid, 'site_type': own['port_site_type'],
            'area_km2': round(max(0.0, float(cell['area_km2'])), 6),
            'latitude_deg': round(float(cell['lat_deg']), 6), 'longitude_deg': round(float(cell['lon_deg']), 6),
            'port_suitability_index': own['port_suitability_index'], 'protected_bay_index': own['protected_bay_index'],
            'river_mouth_port_index': own['river_mouth_port_index'], 'strait_access_index': own['strait_access_index'],
            'harbor_suitability_index': round(float(cell['harbor_suitability_index']), 6),
            'navigability_index': round(float(cell['navigability_index']), 6),
            'settlement_ids': sids, 'port_settlement_ids': pids,
            'route_ids': sorted({rid for sid in sids for rid in route_map.get(sid, set())}),
            'marine_region_ids': sorted({row['marine_region_id'] for row in marine if row['marine_region_id'] >= 0}),
            'marine_chokepoint_ids': sorted({row['marine_chokepoint_id'] for row in marine if row['marine_chokepoint_id'] >= 0}),
            'navigable_waterway_ids': sorted({by_id[nid]['navigable_waterway_id'] for nid in near if by_id[nid]['navigable_waterway_id'] >= 0}) if links_complete else None,
            'navigable_waterway_links_complete': links_complete,
            'landform': cell['landform'], 'biome': cell['biome'], 'water_body_type': cell['water_body_type'], 'is_river': cell['is_river'],
            'selected_by_port_settlement': len(pids) > 0,
            'selected_by_suitability': (cell['harbor_suitability_index'] >= .62 or own['port_suitability_index'] >= .58) and not (cell['ice_thickness_m'] >= 80 or cell['biome'] == 'ice_cap'),
        }
        records.append(record)
    complete = all(row['port_site_selection_supported'] for row in expected.values())
    counts = Counter(row['site_type'] for row in records)
    summary = {
        'port_site_model': POLICIES['ports']['model_type'], 'port_site_count': len(records),
        'port_candidate_cell_count': len(chosen) if complete else None,
        'port_site_total_area_km2': round(sum(row['area_km2'] for row in records), 6),
        'port_settlement_count': sum(row['type'] == 'port' for row in world['settlements']),
        'port_settlement_with_site_count': sum(row['type'] == 'port' and row['cell_id'] in chosen for row in world['settlements']),
        'protected_bay_port_site_count': counts.get('protected_bay_port', 0),
        'river_mouth_port_site_count': counts.get('river_mouth_port', 0),
        'strait_port_site_count': counts.get('strait_port', 0), 'port_site_type_counts': dict(sorted(counts.items())),
        'port_site_selection_complete': complete,
        'port_site_applicable_cell_count': sum(not row['is_water'] for row in by_id.values()),
        'port_site_supported_cell_count': sum(not by_id[cid]['is_water'] and row['port_site_selection_supported'] for cid, row in expected.items()),
    }
    for pos, field in enumerate(('protected_bay', 'river_mouth_port', 'strait_access', 'port_suitability')):
        summary['mean_' + field + '_index'] = _average([values[pos] for values in raw.values()])
        if field != 'strait_access':
            summary['mean_' + field + '_supported'] = all(row[field + '_supported'] for row in expected.values())
    return {'cell': expected, 'summary': summary, 'records': records, 'route': {},
            'dynamic': {'candidate_cell_count': len(chosen) if complete else None, 'site_count': len(records)}}


def expected_corridors(world, site_available):
    by_id = {cell['id']: cell for cell in world['cells']}
    settlement = {row['id']: row for row in world['settlements']}
    route_by_id = {row['id']: row for row in world['routes']}
    features = {}
    math_ = _corridor_math(world, features)
    expected = {}
    for cid, cell in by_id.items():
        needs_local_harbor = cell['water_body_type'] not in NAVIGABILITY_MARINE_WATER_TYPES and len(math_['marine_neighbors'](cell)) > 0
        coast_known = not needs_local_harbor or (cell['harbor_suitability_supported'] and cell['port_suitability_supported'])
        features[cid] = {
            'mountain': round(math_['mountain_pass'](cell), 6),
            'river': round(math_['river_valley'](cell), 6),
            'coastal': round(math_['coastal'](cell), 6) if coast_known else None,
            'oasis': round(math_['oasis'](cell), 6),
        }
        expected[cid] = {
            'mountain_pass_route_index': features[cid]['mountain'],
            'river_valley_route_index': features[cid]['river'],
            'coastal_route_index': features[cid]['coastal'],
            'oasis_route_index': features[cid]['oasis'], 'coastal_route_supported': coast_known,
        }
    route_fields = {}
    for rid in sorted(route_by_id):
        route = route_by_id[rid]
        source, target = settlement.get(route['from']), settlement.get(route['to'])
        path = []
        if source is not None and target is not None and source['cell_id'] in by_id and target['cell_id'] in by_id:
            start, finish = source['cell_id'], target['cell_id']
            if start == finish:
                path = [start]
            else:
                reached, pending = set(), [start]
                while pending:
                    cid = pending.pop()
                    if cid in reached:
                        continue
                    reached.add(cid)
                    pending.extend(nid for nid in by_id[cid]['neighbors'] if nid not in reached)
                if finish in reached:
                    possible = True
                    edges = [(cid, nid) for cid in reached for nid in by_id[cid]['neighbors']]
                    for _, nid in edges:
                        if route['type'] == 'coastal_sea':
                            possible &= features[nid]['coastal'] is not None and by_id[nid]['navigability_supported']
                        elif route['type'] not in {'river_corridor', 'mountain_pass'}:
                            possible &= features[nid]['coastal'] is not None
                    if possible:
                        for a, b in edges:
                            cost = math_['movement_cost'](a, b, route['type'])
                            if not math.isfinite(cost) or cost <= 0:
                                raise ValueError('unrepresentable directed cost')
                        path = math_['shortest_path'](start, finish, route['type'])
                    else:
                        path = None
        supported = path is not None
        diagnostics = supported and all(features[cid]['coastal'] is not None for cid in path)
        route_fields[rid] = {
            'route_path_supported': supported, 'route_corridor_diagnostics_supported': diagnostics,
            'path_cell_ids': path, 'route_corridor_id': -1 if supported else None,
            'route_corridor_type': 'none' if diagnostics else None,
        }
    path_complete = all(row['route_path_supported'] for row in route_fields.values())
    diagnostics_complete = all(row['route_corridor_diagnostics_supported'] for row in route_fields.values())
    membership_complete = path_complete and diagnostics_complete
    for cid, values in features.items():
        values.update(corridor=0.0 if membership_complete else None, type='none' if membership_complete else None, corridor_id=-1 if membership_complete else None)
    records = []
    for rid in sorted(route_fields):
        fields, route = route_fields[rid], route_by_id[rid]
        path = fields['path_cell_ids']
        if not path:
            continue
        category = math_['corridor_type'](path, route['type']) if fields['route_corridor_diagnostics_supported'] else None
        number = len(records)
        fields.update(route_corridor_id=number, route_corridor_type=category)
        if membership_complete:
            for cid in path:
                membership = math_['clamp'](.35 + max(math_['feature_values'](cid).values()) * .65)
                if membership >= features[cid]['corridor']:
                    features[cid].update(corridor=round(membership, 6), type=category, corridor_id=number)
        path_length = sum((math_['distance_km'](by_id[a], by_id[b]) for a, b in zip(path, path[1:])), 0.0)
        straight = max(.001, float(route['distance_km']))
        source, target = settlement[route['from']], settlement[route['to']]
        waterways_known = all(by_id[cid]['navigable_waterway_membership_complete'] for cid in path)
        ports_known = all(by_id[cid]['port_site_selection_supported'] for cid in path)
        values = {name: [features[cid][name] for cid in path] for name in ('mountain', 'river', 'coastal', 'oasis', 'corridor')}
        record = {
            'id': number, 'route_id': rid, 'route_type': route['type'], 'corridor_type': category,
            'from_settlement_id': route['from'], 'to_settlement_id': route['to'],
            'start_cell_id': source['cell_id'], 'end_cell_id': target['cell_id'],
            'cell_count': len(path), 'cell_ids': list(path), 'path_length_km': round(path_length, 6),
            'straight_distance_km': round(straight, 6), 'detour_ratio': round(path_length / straight, 6),
            'mean_route_corridor_index': _average(values['corridor']),
            'max_route_corridor_index': round(max(values['corridor']), 6) if membership_complete else None,
            'named_feature_cell_count': sum(any(value >= .45 for value in math_['feature_values'](cid).values()) for cid in path) if fields['route_corridor_diagnostics_supported'] else None,
            'settlement_ids': sorted({route['from'], route['to']} - {-1}),
            'region_ids': sorted({source['region_id'], target['region_id']} - {-1}), 'route_ids': [rid],
            'navigable_waterway_ids': sorted({by_id[cid]['navigable_waterway_id'] for cid in path if by_id[cid]['navigable_waterway_id'] >= 0}) if waterways_known else None,
            'port_site_ids': sorted({by_id[cid]['port_site_id'] for cid in path if by_id[cid]['port_site_id'] >= 0}) if ports_known else None,
            'route_path_supported': True, 'route_corridor_diagnostics_supported': fields['route_corridor_diagnostics_supported'],
            'route_corridor_membership_complete': membership_complete,
            'navigable_waterway_links_complete': waterways_known, 'port_site_links_complete': ports_known,
        }
        for name, label in [('mountain', 'mountain_pass'), ('river', 'river_valley'), ('coastal', 'coastal'), ('oasis', 'oasis')]:
            record['mean_' + label + '_route_index'] = _average(values[name])
            count_label = label
            record[count_label + '_cell_count'] = sum(value >= .45 for value in values[name]) if all(value is not None for value in values[name]) else None
        records.append(record)
    for cid, values in features.items():
        expected[cid].update(route_corridor_index=values['corridor'], route_corridor_type=values['type'], route_corridor_id=values['corridor_id'], route_corridor_membership_complete=membership_complete)
    counts = Counter(row['corridor_type'] for row in records) if diagnostics_complete else None
    summary = {
        'route_corridor_model': POLICIES['corridors']['model_type'], 'route_corridor_count': len(records),
        'route_corridor_cell_count': sum(values['corridor_id'] >= 0 for values in features.values()) if membership_complete else None,
        'route_corridor_total_path_length_km': round(sum(row['path_length_km'] for row in records), 6) if path_complete else None,
        'mean_route_corridor_index': _average([row['corridor'] for row in features.values()]),
        'route_feature_coverage_index': (round(sum(row['named_feature_cell_count'] > 0 for row in records) / len(records), 6) if records else 1.0) if diagnostics_complete else None,
        'route_corridor_type_counts': dict(sorted(counts.items())) if diagnostics_complete else None,
        'route_path_selection_complete': path_complete, 'route_corridor_diagnostics_complete': diagnostics_complete,
        'route_corridor_membership_complete': membership_complete,
        'coastal_route_estimates_complete': all(row['coastal'] is not None for row in features.values()),
        'route_path_supported_count': sum(row['route_path_supported'] for row in route_fields.values()),
        'route_corridor_diagnostics_supported_count': sum(row['route_corridor_diagnostics_supported'] for row in route_fields.values()),
    }
    for name, label in [('mountain', 'mountain_pass'), ('river', 'river_valley'), ('coastal', 'coastal'), ('oasis', 'oasis')]:
        summary['mean_' + label + '_route_index'] = _average([row[name] for row in features.values()])
        summary[label + '_route_corridor_count'] = counts.get(label + '_corridor', 0) if diagnostics_complete else None
    return {'cell': expected, 'summary': summary, 'records': records, 'route': route_fields,
            'dynamic': {'planet_radius_km': configured_planet_radius_km(world), 'route_count': len(route_by_id), 'corridor_count': len(records)}}


def _compare(actual, expected, path):
    if type(actual) is not type(expected):
        raise ValueError(path + ': wrong exact value type')
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError(path + ': incorrect field coverage')
        for key in expected:
            _compare(actual[key], expected[key], path + '.' + key)
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(path + ': incorrect sequence coverage')
        for index, (a, b) in enumerate(zip(actual, expected)):
            _compare(a, b, path + '[' + str(index) + ']')
    elif isinstance(expected, float):
        if not math.isfinite(expected) or not math.isfinite(actual) or actual != expected:
            raise ValueError(path + ': numeric replay mismatch')
    elif actual != expected:
        raise ValueError(path + ': replay mismatch')


def audit_available_stage(world, stage):
    expected = {'navigation': expected_navigation, 'ports': expected_ports, 'corridors': expected_corridors}[stage](world, _site_availability(world))
    for family, key in (('cell', 'cells'), ('route', 'routes')):
        for row in world[key]:
            if row['id'] in expected[family]:
                subset = expected[family][row['id']]
                if any(name not in row for name in subset):
                    raise ValueError(f'{stage} missing {family} output')
                _compare({name: row[name] for name in subset}, subset, stage + '.' + family + '.' + str(row['id']))
    summary = expected['summary']
    if any(name not in world['summary'] for name in summary):
        raise ValueError(stage + ': missing summary output')
    _compare({name: world['summary'][name] for name in summary}, summary, stage + '.summary')
    family = {'navigation': 'navigable_waterways', 'ports': 'port_sites', 'corridors': 'route_corridors'}[stage]
    _compare(world.get(family), expected['records'], family)
    key = {'navigation': 'navigability_model', 'ports': 'port_site_model', 'corridors': 'route_corridor_model'}[stage]
    _compare(world[key], {**POLICIES[stage], **expected['dynamic']}, key)

AQUIFER_RESOURCE_MODEL = "finite_recharge_causal_aquifer_resources_v1"

RIVER_CHANNEL_MORPHOLOGY_MODEL = (
    "causal_flow_sediment_wetland_baseflow_channel_morphology_v1"
)

RIVER_CHANNEL_LOWLAND_FORMS = {
    "delta",
    "floodplain",
    "river_valley",
    "coastal_plain",
    "lacustrine_basin",
}

RIVER_HYDRAULICS_MODEL = "manning_blended_diagnostic_river_hydraulics_v1"

NAVIGABILITY_MODEL = "causal_channel_hydraulic_coastal_navigability_v1"

NAVIGABILITY_THRESHOLD = 0.52

NAVIGABILITY_HIGH_HARBOR_THRESHOLD = 0.62

NAVIGABILITY_TRANSPORT_CHOKEPOINT_THRESHOLD = 0.55

NAVIGABILITY_MARINE_WATER_TYPES = {
    "ocean",
    "continental_shelf",
    "inland_sea",
}

PORT_SITE_MODEL = "causal_navigability_coastal_port_site_selection_v1"

PORT_SITE_THRESHOLD = 0.58

PORT_PROTECTED_BAY_THRESHOLD = 0.55

PORT_RIVER_MOUTH_THRESHOLD = 0.50

PORT_STRAIT_ACCESS_THRESHOLD = 0.55

ROUTE_CORRIDOR_MODEL = "causal_feature_weighted_dijkstra_route_corridors_v1"

ROUTE_FEATURE_THRESHOLD = 0.45

ROUTE_MOUNTAIN_LANDFORMS = {
    "mountain",
    "mountain_range",
    "volcanic_arc",
    "highland",
    "ridge",
    "glacial_valley",
}

ROUTE_RIVER_VALLEY_LANDFORMS = {
    "delta",
    "floodplain",
    "river_valley",
    "alluvial_fan",
    "wetland",
}

ROUTE_DESERT_BIOMES = {
    "hot_desert",
    "cold_desert",
    "desert",
    "semi_arid_desert",
}


def _navigation_math(world, expected_by_id=None):
    cells_by_id = {cell['id']: cell for cell in world['cells']}
    max_flow = max(max(0.0, float(cell['flow_accumulation'])) for cell in world['cells'])
    chokepoint_by_cell = {row['cell_id']: row for row in world['marine_chokepoints']}
    chokepoint_by_id = {row['id']: row for row in world['marine_chokepoints']}

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def marine_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        neighbors: list[dict[str, Any]] = []
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        for raw_neighbor_id in raw_neighbors:
            neighbor = cells_by_id.get(int(raw_neighbor_id))
            if (
                neighbor is not None
                and str(neighbor.get("water_body_type", "land"))
                in NAVIGABILITY_MARINE_WATER_TYPES
            ):
                neighbors.append(neighbor)
        return neighbors

    def land_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        neighbors: list[dict[str, Any]] = []
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        for raw_neighbor_id in raw_neighbors:
            neighbor = cells_by_id.get(int(raw_neighbor_id))
            if neighbor is not None and not bool(neighbor.get("is_water", False)):
                neighbors.append(neighbor)
        return neighbors

    def river_navigability(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)) or not bool(
            cell.get("is_river", False)
        ):
            return 0.0
        flow = clamp(
            float(cell.get("flow_accumulation", 0.0)) / max(1.0, max_flow)
        )
        runoff = clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0)
        lowland = (
            0.22
            if str(cell.get("landform", "")) in RIVER_CHANNEL_LOWLAND_FORMS
            else 0.0
        )
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1800.0
        )
        sediment_load = clamp(
            float(cell.get("sediment_routing_load_m", 0.0)) / 2.0
        )
        channel_depth = clamp(
            float(cell.get("river_channel_depth_m", 0.0)) / 3.0
        )
        channel_width = clamp(
            float(cell.get("river_channel_width_m", 0.0)) / 80.0
        )
        hydraulic = clamp(
            float(cell.get("hydraulic_navigability_index", 0.0))
        )
        ice_penalty = clamp(
            float(cell.get("ice_thickness_m", 0.0)) / 350.0
        )
        aridity_penalty = (
            clamp(float(cell.get("seasonal_aridity_index", 0.0))) * 0.08
        )
        return clamp(
            flow * 0.24
            + runoff * 0.13
            + low_relief * 0.12
            + lowland
            + sediment_load * 0.06
            + channel_depth * 0.14
            + channel_width * 0.08
            + hydraulic * 0.17
            - ice_penalty * 0.24
            - aridity_penalty
        )

    def coastal_navigability(cell: dict[str, Any]) -> float:
        water_body = str(cell.get("water_body_type", "land"))
        if water_body in NAVIGABILITY_MARINE_WATER_TYPES:
            depth = clamp(float(cell.get("water_depth_m", 0.0)) / 180.0)
            shelf = (
                0.24
                if water_body in {"continental_shelf", "inland_sea"}
                else 0.08
            )
            land_contact = clamp(len(land_neighbors(cell)) / 4.0)
            constriction = clamp(
                float(
                    chokepoint_by_cell.get(
                        int(cell.get("id", -1)), {}
                    ).get("constriction_index", 0.0)
                )
            )
            return clamp(
                depth * 0.30
                + shelf
                + land_contact * 0.20
                + constriction * 0.26
            )

        adjacent_marine = marine_neighbors(cell)
        if not adjacent_marine:
            return 0.0
        neighbor_score = clamp(len(adjacent_marine) / 4.0)
        protected = (
            0.20
            if any(
                str(neighbor.get("water_body_type", ""))
                in {"continental_shelf", "inland_sea"}
                for neighbor in adjacent_marine
            )
            else 0.0
        )
        river_mouth = (
            0.22
            if bool(cell.get("is_river", False))
            or str(cell.get("landform", "")) == "delta"
            else 0.0
        )
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1200.0
        )
        return clamp(
            neighbor_score * 0.32 + protected + river_mouth + low_relief * 0.18
        )

    def harbor_suitability(
        cell: dict[str, Any], coastal: float
    ) -> float:
        if bool(cell.get("is_water", False)):
            return 0.0
        adjacent_marine = marine_neighbors(cell)
        if not adjacent_marine:
            return 0.0
        protected = (
            0.24
            if any(
                str(neighbor.get("water_body_type", ""))
                in {"continental_shelf", "inland_sea"}
                for neighbor in adjacent_marine
            )
            else 0.0
        )
        river_mouth = (
            0.18
            if bool(cell.get("is_river", False))
            or str(cell.get("landform", "")) == "delta"
            else 0.0
        )
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 900.0
        )
        settlement = clamp(float(cell.get("settlement_score", 0.0)))
        ice_penalty = clamp(
            float(cell.get("ice_thickness_m", 0.0)) / 300.0
        )
        return clamp(
            coastal * 0.32
            + protected
            + river_mouth
            + low_relief * 0.14
            + settlement * 0.18
            - ice_penalty * 0.22
        )

    def transport_chokepoint(
        cell: dict[str, Any], coastal: float
    ) -> float:
        chokepoint = chokepoint_by_cell.get(int(cell.get("id", -1)))
        if chokepoint is None:
            return 0.0
        constriction = clamp(float(chokepoint.get("constriction_index", 0.0)))
        return clamp(constriction * 0.72 + coastal * 0.28)

    def classify(
        river: float, coastal: float, harbor: float, chokepoint: float
    ) -> str:
        if chokepoint >= NAVIGABILITY_TRANSPORT_CHOKEPOINT_THRESHOLD:
            return "transport_chokepoint"
        if harbor >= NAVIGABILITY_HIGH_HARBOR_THRESHOLD:
            return "harbor"
        if river >= NAVIGABILITY_THRESHOLD and coastal >= NAVIGABILITY_THRESHOLD:
            return "river_mouth"
        if river >= NAVIGABILITY_THRESHOLD:
            return "river_corridor"
        if coastal >= NAVIGABILITY_THRESHOLD:
            return "coastal_corridor"
        return "non_navigable"

    return {'clamp': clamp, 'marine_neighbors': marine_neighbors, 'land_neighbors': land_neighbors, 'river_navigability': river_navigability, 'coastal_navigability': coastal_navigability, 'harbor_suitability': harbor_suitability, 'transport_chokepoint': transport_chokepoint, 'classify': classify}

def _port_math(world, expected_by_id=None):
    cells_by_id = {cell['id']: cell for cell in world['cells']}
    max_flow = max(max(0.0, float(cell['flow_accumulation'])) for cell in world['cells'])
    chokepoint_by_cell = {row['cell_id']: row for row in world['marine_chokepoints']}
    chokepoint_by_id = {row['id']: row for row in world['marine_chokepoints']}

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def marine_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        return [
            neighbor
            for raw_neighbor_id in raw_neighbors
            if (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None
            and str(neighbor.get("water_body_type", "land"))
            in NAVIGABILITY_MARINE_WATER_TYPES
        ]

    def land_neighbor_fraction(cell: dict[str, Any]) -> float:
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list) or not raw_neighbors:
            return 0.0
        valid = [
            neighbor
            for raw_neighbor_id in raw_neighbors
            if (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None
        ]
        if not valid:
            return 0.0
        return sum(not bool(neighbor.get("is_water", False)) for neighbor in valid) / len(valid)

    def protected_bay(
        cell: dict[str, Any], adjacent_marine: list[dict[str, Any]]
    ) -> float:
        if bool(cell.get("is_water", False)) or not adjacent_marine:
            return 0.0
        contact = clamp(len(adjacent_marine) / 3.0)
        protected = sum(
            str(neighbor.get("water_body_type", ""))
            in {"continental_shelf", "inland_sea"}
            for neighbor in adjacent_marine
        ) / len(adjacent_marine)
        enclosure = sum(
            land_neighbor_fraction(neighbor) for neighbor in adjacent_marine
        ) / len(adjacent_marine)
        shallow = sum(
            clamp(1.0 - float(neighbor.get("water_depth_m", 0.0)) / 260.0)
            for neighbor in adjacent_marine
        ) / len(adjacent_marine)
        harbor = clamp(float(cell.get("harbor_suitability_index", 0.0)))
        return clamp(
            contact * 0.20
            + protected * 0.25
            + enclosure * 0.25
            + shallow * 0.16
            + harbor * 0.14
        )

    def river_mouth(
        cell: dict[str, Any], adjacent_marine: list[dict[str, Any]]
    ) -> float:
        if bool(cell.get("is_water", False)) or not adjacent_marine:
            return 0.0
        landform = str(cell.get("landform", ""))
        if not bool(cell.get("is_river", False)) and landform not in {
            "delta",
            "floodplain",
            "river_valley",
        }:
            return 0.0
        flow = clamp(
            float(cell.get("flow_accumulation", 0.0)) / max(1.0, max_flow)
        )
        runoff = clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0)
        delta_bonus = (
            0.26
            if landform == "delta"
            else 0.12
            if landform in {"floodplain", "river_valley"}
            else 0.0
        )
        harbor = clamp(float(cell.get("harbor_suitability_index", 0.0)))
        return clamp(
            0.28 + flow * 0.22 + runoff * 0.14 + delta_bonus + harbor * 0.10
        )

    def strait_access(
        cell: dict[str, Any], adjacent_marine: list[dict[str, Any]]
    ) -> float:
        if bool(cell.get("is_water", False)) or not adjacent_marine:
            return 0.0
        best = 0.0
        for neighbor in adjacent_marine:
            chokepoint = chokepoint_by_id.get(
                int(neighbor.get("marine_chokepoint_id", -1))
            )
            if chokepoint is None:
                continue
            constriction = clamp(
                float(chokepoint.get("constriction_index", 0.0))
            )
            if str(chokepoint.get("type", "")) == "strait":
                constriction = max(constriction, 0.60)
            best = max(best, constriction)
        coastal = clamp(float(cell.get("coastal_navigability_index", 0.0)))
        return clamp(best * 0.76 + coastal * 0.24)

    def suitability(
        cell: dict[str, Any], bay: float, mouth: float, strait: float
    ) -> float:
        if bool(cell.get("is_water", False)):
            return 0.0
        harbor = clamp(float(cell.get("harbor_suitability_index", 0.0)))
        coastal = clamp(float(cell.get("coastal_navigability_index", 0.0)))
        settlement = clamp(float(cell.get("settlement_score", 0.0)))
        climate = clamp((float(cell.get("temperature_c", 0.0)) + 8.0) / 30.0)
        ice_penalty = clamp(float(cell.get("ice_thickness_m", 0.0)) / 220.0)
        relief_penalty = clamp(
            (abs(float(cell.get("elevation_m", 0.0))) - 1200.0) / 1800.0
        )
        base = max(harbor, bay, mouth, strait)
        return clamp(
            base * 0.40
            + bay * 0.16
            + mouth * 0.14
            + strait * 0.12
            + coastal * 0.06
            + settlement * 0.06
            + climate * 0.06
            - ice_penalty * 0.32
            - relief_penalty * 0.08
        )

    def site_type(
        bay: float, mouth: float, strait: float, harbor: float, score: float
    ) -> str:
        if strait >= PORT_STRAIT_ACCESS_THRESHOLD:
            return "strait_port"
        if mouth >= PORT_RIVER_MOUTH_THRESHOLD:
            return "river_mouth_port"
        if bay >= PORT_PROTECTED_BAY_THRESHOLD:
            return "protected_bay_port"
        if harbor >= NAVIGABILITY_HIGH_HARBOR_THRESHOLD:
            return "harbor_port"
        if score >= PORT_SITE_THRESHOLD:
            return "coastal_port"
        return "none"

    return {'clamp': clamp, 'marine_neighbors': marine_neighbors, 'land_neighbor_fraction': land_neighbor_fraction, 'protected_bay': protected_bay, 'river_mouth': river_mouth, 'strait_access': strait_access, 'suitability': suitability, 'site_type': site_type}

def _corridor_math(world, expected_by_id=None):
    cells_by_id = {cell['id']: cell for cell in world['cells']}
    max_flow = max(max(0.0, float(cell['flow_accumulation'])) for cell in world['cells'])
    chokepoint_by_cell = {row['cell_id']: row for row in world['marine_chokepoints']}
    chokepoint_by_id = {row['id']: row for row in world['marine_chokepoints']}
    radius_km = configured_planet_radius_km(world)
    oasis_settlement_cell_ids = {row['cell_id'] for row in world['settlements'] if row['type'] == 'oasis'}

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def distance_km(first: dict[str, Any], second: dict[str, Any]) -> float:
        first_lat = math.radians(float(first.get("lat_deg", 0.0)))
        first_lon = math.radians(float(first.get("lon_deg", 0.0)))
        second_lat = math.radians(float(second.get("lat_deg", 0.0)))
        second_lon = math.radians(float(second.get("lon_deg", 0.0)))
        delta_lat = second_lat - first_lat
        delta_lon = second_lon - first_lon
        sin_lat = math.sin(delta_lat * 0.5)
        sin_lon = math.sin(delta_lon * 0.5)
        haversine = (
            sin_lat * sin_lat
            + math.cos(first_lat) * math.cos(second_lat) * sin_lon * sin_lon
        )
        return max(
            0.001,
            radius_km
            * 2.0
            * math.asin(min(1.0, math.sqrt(max(0.0, haversine)))),
        )

    def marine_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        return [
            neighbor
            for raw_neighbor_id in raw_neighbors
            if (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None
            and str(neighbor.get("water_body_type", "land"))
            in NAVIGABILITY_MARINE_WATER_TYPES
        ]

    def land_neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        raw_neighbors = cell.get("neighbors", [])
        if not isinstance(raw_neighbors, list):
            raise ValueError("neighbors must be a list")
        return [
            neighbor
            for raw_neighbor_id in raw_neighbors
            if (neighbor := cells_by_id.get(int(raw_neighbor_id))) is not None
            and not bool(neighbor.get("is_water", False))
        ]

    def is_coastal(cell: dict[str, Any]) -> bool:
        return (
            str(cell.get("water_body_type", "land"))
            in NAVIGABILITY_MARINE_WATER_TYPES
            or bool(marine_neighbors(cell))
        )

    def mountain_pass(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)):
            return 0.0
        elevation = float(cell.get("elevation_m", 0.0))
        neighbors = land_neighbors(cell)
        if not neighbors:
            return 0.0
        elevations = [
            float(neighbor.get("elevation_m", 0.0)) for neighbor in neighbors
        ]
        high_neighbors = [value for value in elevations if value >= 900.0]
        landform = str(cell.get("landform", ""))
        context = max(
            clamp((max(elevations, default=elevation) - 700.0) / 2300.0),
            clamp(float(cell.get("boundary_convergent", 0.0)) * 1.9),
            0.68 if landform in ROUTE_MOUNTAIN_LANDFORMS else 0.0,
        )
        if context <= 0.05 and not high_neighbors:
            return 0.0
        high_mean = (
            sum(high_neighbors) / len(high_neighbors)
            if high_neighbors
            else max(elevations)
        )
        saddle_gap = clamp((high_mean - elevation + 260.0) / 1150.0)
        pass_elevation = clamp((elevation - 180.0) / 1700.0)
        relief_window = clamp((max(elevations) - min(elevations)) / 1900.0)
        ice_penalty = clamp(float(cell.get("ice_thickness_m", 0.0)) / 280.0)
        return clamp(
            context * 0.38
            + saddle_gap * 0.32
            + relief_window * 0.18
            + pass_elevation * 0.12
            - ice_penalty * 0.30
        )

    def river_valley(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)) and str(
            cell.get("water_body_type", "land")
        ) in NAVIGABILITY_MARINE_WATER_TYPES:
            return 0.0
        landform = str(cell.get("landform", ""))
        flow = clamp(
            float(cell.get("flow_accumulation", 0.0)) / max(1.0, max_flow)
        )
        runoff = clamp(float(cell.get("runoff_mm_y", 0.0)) / 850.0)
        river = 0.34 if bool(cell.get("is_river", False)) else 0.0
        valley = 0.28 if landform in ROUTE_RIVER_VALLEY_LANDFORMS else 0.0
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1900.0
        )
        navigability = clamp(
            float(cell.get("river_navigability_index", 0.0))
        )
        ice_penalty = clamp(float(cell.get("ice_thickness_m", 0.0)) / 260.0)
        return clamp(
            flow * 0.22
            + runoff * 0.14
            + river
            + valley
            + low_relief * 0.12
            + navigability * 0.16
            - ice_penalty * 0.24
        )

    def coastal(cell: dict[str, Any]) -> float:
        water_body = str(cell.get("water_body_type", "land"))
        adjacent_marine = marine_neighbors(cell)
        if water_body in NAVIGABILITY_MARINE_WATER_TYPES:
            land_contact = clamp(len(land_neighbors(cell)) / 4.0)
            shelf = (
                0.25
                if water_body in {"continental_shelf", "inland_sea"}
                else 0.10
            )
            navigability = clamp(
                float(cell.get("coastal_navigability_index", 0.0))
            )
            chokepoint = clamp(
                float(cell.get("transport_chokepoint_index", 0.0))
            )
            depth_access = clamp(
                1.0 - float(cell.get("water_depth_m", 0.0)) / 700.0
            )
            return clamp(
                shelf
                + land_contact * 0.22
                + navigability * 0.30
                + chokepoint * 0.18
                + depth_access * 0.15
            )
        if not adjacent_marine:
            return 0.0
        marine_contact = clamp(len(adjacent_marine) / 3.0)
        low_relief = clamp(
            1.0 - abs(float(cell.get("elevation_m", 0.0))) / 1200.0
        )
        harbor = clamp(float(cell.get("harbor_suitability_index", 0.0)))
        port = clamp(float(cell.get("port_suitability_index", 0.0)))
        navigability = clamp(
            float(cell.get("coastal_navigability_index", 0.0))
        )
        return clamp(
            marine_contact * 0.24
            + low_relief * 0.18
            + harbor * 0.20
            + port * 0.18
            + navigability * 0.20
        )

    def oasis(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)):
            return 0.0
        biome = str(cell.get("biome", ""))
        aridity = clamp(float(cell.get("seasonal_aridity_index", 0.0)))
        arid_context = max(
            aridity, 0.72 if biome in ROUTE_DESERT_BIOMES else 0.0
        )
        cell_id = int(cell.get("id", -1))
        if arid_context < 0.45 and cell_id not in oasis_settlement_cell_ids:
            return 0.0
        water_access = max(
            0.85 if bool(cell.get("is_river", False)) else 0.0,
            0.70 if bool(cell.get("is_lake", False)) else 0.0,
            clamp(float(cell.get("runoff_mm_y", 0.0)) / 220.0),
            clamp(float(cell.get("groundwater_recharge_mm_y", 0.0)) / 180.0),
            clamp(float(cell.get("aquifer_productivity_index", 0.0))),
            clamp(float(cell.get("soil_moisture_index", 0.0))),
        )
        fertility = clamp(float(cell.get("fertility", 0.0)))
        settlement = 0.25 if cell_id in oasis_settlement_cell_ids else 0.0
        return clamp(
            arid_context * 0.32
            + water_access * 0.43
            + fertility * 0.12
            + settlement
            - clamp(float(cell.get("ice_thickness_m", 0.0)) / 200.0)
        )

    def feature_values(cell_id: int) -> dict[str, float]:
        expected = expected_by_id[cell_id]
        return {
            "mountain_pass_corridor": float(expected["mountain"]),
            "river_valley_corridor": float(expected["river"]),
            "coastal_corridor": expected["coastal"],
            "oasis_corridor": float(expected["oasis"]),
        }

    def movement_cost(
        current_id: int, neighbor_id: int, route_type: str
    ) -> float:
        current = cells_by_id[current_id]
        neighbor = cells_by_id[neighbor_id]
        distance = distance_km(current, neighbor)
        water_body = str(neighbor.get("water_body_type", "land"))
        is_water = bool(neighbor.get("is_water", False))
        elevation_delta = abs(
            float(neighbor.get("elevation_m", 0.0))
            - float(current.get("elevation_m", 0.0))
        )
        slope = clamp(elevation_delta / 2000.0)
        ice = clamp(float(neighbor.get("ice_thickness_m", 0.0)) / 320.0)
        aridity = clamp(float(neighbor.get("seasonal_aridity_index", 0.0)))
        mountain = clamp(
            (float(neighbor.get("elevation_m", 0.0)) - 1000.0) / 2200.0
        )
        features = feature_values(neighbor_id)
        if route_type == "coastal_sea":
            support = max(
                features["coastal_corridor"],
                float(neighbor.get("navigability_index", 0.0)),
            )
            water_penalty = (
                0.08
                if water_body in NAVIGABILITY_MARINE_WATER_TYPES
                else 0.72
                if is_coastal(neighbor)
                else 1.80
            )
        elif route_type == "river_corridor":
            support = max(
                features["river_valley_corridor"],
                float(neighbor.get("river_navigability_index", 0.0)),
            )
            water_penalty = (
                1.45
                if water_body in NAVIGABILITY_MARINE_WATER_TYPES
                else 0.18
                if bool(neighbor.get("is_river", False))
                else 0.42
            )
        elif route_type == "mountain_pass":
            support = max(
                features["mountain_pass_corridor"],
                features["river_valley_corridor"] * 0.45,
            )
            water_penalty = 1.70 if is_water else 0.20
        else:
            support = max(
                features["river_valley_corridor"] * 0.72,
                features["coastal_corridor"] * 0.62,
                features["oasis_corridor"] * 0.72,
                features["mountain_pass_corridor"] * 0.46,
            )
            water_penalty = (
                1.65
                if water_body in NAVIGABILITY_MARINE_WATER_TYPES
                else 0.20
                if bool(neighbor.get("is_river", False))
                else 0.34
            )
        terrain = (
            0.64
            + slope * 0.42
            + ice * 0.55
            + aridity * 0.18
            + mountain * 0.20
            + water_penalty
            - support * 0.50
        )
        return distance * max(0.12, terrain)

    def shortest_path(start: int, end: int, route_type: str) -> list[int]:
        if start == end and start in cells_by_id:
            return [start]
        if start not in cells_by_id or end not in cells_by_id:
            return []
        queue: list[tuple[float, int]] = [(0.0, start)]
        best_cost = {start: 0.0}
        previous: dict[int, int] = {}
        visited: set[int] = set()
        while queue:
            cost, cell_id = heapq.heappop(queue)
            if cell_id in visited:
                continue
            visited.add(cell_id)
            if cell_id == end:
                break
            raw_neighbors = cells_by_id[cell_id].get("neighbors", [])
            if not isinstance(raw_neighbors, list):
                return []
            for raw_neighbor_id in raw_neighbors:
                neighbor_id = int(raw_neighbor_id)
                if neighbor_id not in cells_by_id:
                    continue
                next_cost = cost + movement_cost(
                    cell_id, neighbor_id, route_type
                )
                if next_cost < best_cost.get(neighbor_id, math.inf):
                    best_cost[neighbor_id] = next_cost
                    previous[neighbor_id] = cell_id
                    heapq.heappush(queue, (next_cost, neighbor_id))
        if end not in best_cost:
            return []
        path = [end]
        while path[-1] != start:
            parent = previous.get(path[-1])
            if parent is None:
                return []
            path.append(parent)
        return list(reversed(path))

    def corridor_type(path: list[int], route_type: str) -> str:
        counts = {
            name: sum(
                feature_values(cell_id)[name] >= ROUTE_FEATURE_THRESHOLD
                for cell_id in path
            )
            for name in (
                "mountain_pass_corridor",
                "river_valley_corridor",
                "coastal_corridor",
                "oasis_corridor",
            )
        }
        if route_type == "coastal_sea" and counts["coastal_corridor"] > 0:
            return "coastal_corridor"
        if route_type == "river_corridor" and counts["river_valley_corridor"] > 0:
            return "river_valley_corridor"
        if route_type == "mountain_pass" and counts["mountain_pass_corridor"] > 0:
            return "mountain_pass_corridor"
        best_type, best_count = sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )[0]
        return best_type if best_count > 0 else "overland_corridor"

    return {'clamp': clamp, 'distance_km': distance_km, 'marine_neighbors': marine_neighbors, 'land_neighbors': land_neighbors, 'is_coastal': is_coastal, 'mountain_pass': mountain_pass, 'river_valley': river_valley, 'coastal': coastal, 'oasis': oasis, 'feature_values': feature_values, 'movement_cost': movement_cost, 'shortest_path': shortest_path, 'corridor_type': corridor_type}

# Static policies are independently held, not imported from the producer.
POLICIES = {'corridors': {'availability_policy': 'null_unavailable_values_and_typed_flags_with_structural_zeros_v1',
               'cell_assignment_model': 'maximum_membership_with_later_route_winning_equal_ties_v1',
               'coastal_model': 'marine_or_coastal_contact_navigability_harbor_port_depth_relief_v1',
               'corridor_classification_model': 'route_type_preference_then_feature_count_lexical_tie_v1',
               'deterministic': True,
               'diagnostic_availability_policy': 'all_path_features_before_type_and_statistics',
               'domain': 'all_cells_with_one_path_per_valid_route',
               'feature_threshold': 0.45,
               'membership_availability_policy': 'all_routes_paths_and_diagnostics_before_global_cell_assignment',
               'model_limitation': 'diagnostic_static_corridors_without_capacity_congestion_seasonality_construction_cost_network_equilibrium_or_multimodal_scheduling',
               'model_type': 'causal_feature_weighted_dijkstra_route_corridors_v3',
               'mountain_pass_model': 'neighbor_saddle_convergence_landform_relief_elevation_ice_v1',
               'movement_cost_model': 'directed_distance_terrain_water_route_type_feature_support_v1',
               'oasis_model': 'aridity_water_recharge_aquifer_soil_fertility_settlement_ice_v1',
               'path_availability_policy': 'all_reachable_directed_cost_inputs_before_dijkstra',
               'path_model': 'strict_improvement_dijkstra_cost_then_cell_id_heap_v1',
               'record_order': 'ascending_route_id_for_valid_endpoints_and_paths',
               'river_valley_model': 'flow_runoff_river_landform_relief_navigability_ice_v1',
               'source_aquifer_model': 'natural_recharge_causal_aquifer_resources_v2',
               'source_input_policy': 'explicit_finite_typed_consumed_inputs_and_complete_links_v1',
               'source_navigability_model': 'causal_channel_hydraulic_coastal_navigability_v3',
               'source_port_model': 'causal_navigability_coastal_port_site_selection_v3',
               'source_route_network_model': 'causal_endpoint_barrier_ranked_route_network_v1',
               'source_settlement_model': 'causal_native_score_local_max_separated_settlement_selection_v3',
               'threshold_semantics': 'serialized_feature_indices',
               'upstream_link_policy': 'nullable_ids_unless_parent_membership_complete'},
 'navigation': {'availability_policy': 'null_unavailable_values_and_typed_flags_with_structural_zeros_v1',
                'classification_model': 'chokepoint_harbor_river_mouth_river_coastal_priority_v1',
                'coastal_model': 'marine_depth_shelf_land_contact_constriction_or_coastal_land_context_v1',
                'deterministic': True,
                'domain': 'all_cells',
                'flow_normalization_model': 'global_max_flow_accumulation_v1',
                'harbor_applicability': 'nonwater_with_marine_neighbor',
                'harbor_model': 'coastal_protection_river_mouth_relief_settlement_ice_v1',
                'high_harbor_threshold': 0.62,
                'link_model': 'component_cell_settlement_route_marine_region_watershed_links_v1',
                'model_limitation': 'diagnostic_transport_suitability_without_vessel_classes_seasonal_discharge_bathymetric_channels_or_route_cost_optimization',
                'model_type': 'causal_channel_hydraulic_coastal_navigability_v3',
                'navigable_threshold': 0.52,
                'overall_model': 'maximum_component_navigability_v1',
                'river_model': 'flow_runoff_lowland_relief_sediment_channel_hydraulic_ice_aridity_v1',
                'source_channel_model': 'causal_flow_sediment_wetland_baseflow_channel_morphology_v2',
                'source_hydraulics_model': 'manning_blended_diagnostic_river_hydraulics_v2',
                'source_input_policy': 'explicit_finite_typed_consumed_inputs_and_complete_links_v1',
                'source_settlement_model': 'causal_native_score_local_max_separated_settlement_selection_v3',
                'system_grouping_model': 'undirected_mesh_connected_raw_threshold_components_v1',
                'threshold_semantics': 'unrounded_pre_serialization_values',
                'transport_chokepoint_model': 'marine_constriction_and_coastal_navigability_v1',
                'transport_chokepoint_threshold': 0.55,
                'watershed_link_basis': 'native_cell_basin_ids_not_watershed_record_ids',
                'waterway_availability_policy': 'withhold_complete_components_unless_all_cell_estimates_supported',
                'whole_estimate_policy': 'require_every_compared_component'},
 'ports': {'availability_policy': 'null_unavailable_values_and_typed_flags_with_structural_zeros_v1',
           'classification_model': 'strait_river_mouth_protected_bay_harbor_coastal_priority_v1',
           'deterministic': True,
           'domain': 'all_cells_with_land_only_selection',
           'link_model': 'cell_settlement_route_marine_region_chokepoint_nearby_waterway_links_v1',
           'model_limitation': 'diagnostic_port_suitability_without_harbor_bathymetry_tides_waves_sedimentation_engineering_or_economic_optimization',
           'model_type': 'causal_navigability_coastal_port_site_selection_v3',
           'port_site_threshold': 0.58,
           'protected_bay_model': 'marine_contact_protected_water_enclosure_depth_harbor_v1',
           'protected_bay_threshold': 0.55,
           'record_order': 'ascending_candidate_cell_id',
           'river_mouth_model': 'river_landform_flow_runoff_delta_harbor_v1',
           'river_mouth_threshold': 0.5,
           'selection_availability_policy': 'cell_local_supported_selection_with_explicit_family_coverage',
           'selection_model': 'raw_suitability_without_severe_ice_or_port_settlement_override_v1',
           'source_input_policy': 'explicit_finite_typed_consumed_inputs_and_complete_links_v1',
           'source_navigability_model': 'causal_channel_hydraulic_coastal_navigability_v3',
           'source_settlement_model': 'causal_native_score_local_max_separated_settlement_selection_v3',
           'strait_access_model': 'adjacent_marine_chokepoint_constriction_and_coastal_access_v1',
           'strait_access_threshold': 0.55,
           'suitability_model': 'harbor_bay_river_strait_coastal_settlement_climate_ice_relief_v1',
           'threshold_semantics': 'unrounded_pre_serialization_values_except_record_flags_use_serialized_fields',
           'waterway_link_policy': 'nullable_ids_unless_parent_membership_complete'}}
