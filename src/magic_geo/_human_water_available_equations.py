"""Producer-only settlement-availability successors of the human water tail.

The historical scalar equations are reused only after their actual inputs are
known. This module is never imported by the independent numerical replay.
"""
from __future__ import annotations

from collections import Counter
import heapq
import math
from typing import Any


def _mean(values):
    return None if any(value is None for value in values) else round(sum(values) / len(values), 6)


def navigation(world, inputs):
    from . import navigability_diagnostics as old
    cells = world['cells']
    by_id = {cell['id']: cell for cell in cells}
    chokepoints = {row['cell_id']: row for row in world['marine_chokepoints']}
    max_flow = max(max(0.0, cell['flow_accumulation']) for cell in cells)
    raw = {}
    candidates = set()
    for cell in cells:
        cid = cell['id']
        applicable = not cell['is_water'] and bool(old._marine_neighbors(cell, by_id))
        available = not applicable or inputs[cid].available
        river = old._river_navigability(cell, max_flow)
        coastal = old._coastal_navigability(cell, by_id, chokepoints)
        harbor = old._harbor_suitability(cell, by_id, coastal) if available else None
        choke = old._transport_chokepoint(cell, coastal, chokepoints)
        overall = max(river, coastal, harbor, choke) if available else None
        classification = old._navigability_class(river, coastal, harbor, choke) if available else None
        raw[cid] = (river, coastal, harbor, choke, overall)
        cell.update(
            harbor_site_applicable=applicable,
            harbor_suitability_supported=available,
            navigability_supported=available,
            navigability_classification_supported=available,
            river_navigability_index=round(river, 6),
            coastal_navigability_index=round(coastal, 6),
            harbor_suitability_index=round(harbor, 6) if available else None,
            transport_chokepoint_index=round(choke, 6),
            navigability_index=round(overall, 6) if available else None,
            navigability_class=classification,
        )
        if available and overall >= old.NAVIGABLE_THRESHOLD:
            candidates.add(cid)
    complete = all(cell['navigability_supported'] for cell in cells)
    for cell in cells:
        cell['navigable_waterway_membership_complete'] = complete
        cell['navigable_waterway_id'] = -1 if complete else None
    records = old._waterway_records(
        old._connected_components(candidates, by_id),
        old._settlements_by_cell(world), old._routes_by_settlement(world),
    ) if complete else []
    summary = world['summary']
    summary.update(
        navigability_model=MODELS['navigation']['model_type'],
        navigable_cell_count=len(candidates) if complete else None,
        navigable_waterway_count=len(records),
        navigable_waterway_total_area_km2=round(sum(row['area_km2'] for row in records), 6) if complete else None,
        mean_river_navigability_index=_mean([values[0] for values in raw.values()]),
        mean_coastal_navigability_index=_mean([values[1] for values in raw.values()]),
        mean_harbor_suitability_index=_mean([values[2] for values in raw.values()]),
        mean_transport_chokepoint_index=_mean([values[3] for values in raw.values()]),
        mean_navigability_index=_mean([values[4] for values in raw.values()]),
        high_harbor_suitability_cell_count=sum(values[2] >= old.HIGH_HARBOR_THRESHOLD for values in raw.values()) if complete else None,
        transport_chokepoint_cell_count=sum(values[3] >= old.TRANSPORT_CHOKEPOINT_THRESHOLD for values in raw.values()),
        navigability_class_counts=dict(sorted(Counter(cell['navigability_class'] for cell in cells).items())) if complete else None,
        navigable_waterway_selection_complete=complete,
        navigability_estimates_complete=complete,
        harbor_site_applicable_cell_count=sum(cell['harbor_site_applicable'] for cell in cells),
        harbor_site_supported_cell_count=sum(cell['harbor_site_applicable'] and cell['harbor_suitability_supported'] for cell in cells),
        navigability_supported_cell_count=sum(cell['navigability_supported'] for cell in cells),
    )
    world['navigability_model'] = {**MODELS['navigation'], 'candidate_cell_count': len(candidates) if complete else None, 'waterway_count': len(records)}
    world['navigable_waterways'] = records


def ports(world, inputs):
    from . import port_sites as old
    cells = world['cells']
    by_id = {cell['id']: cell for cell in cells}
    chokepoints = {row['id']: row for row in world['marine_chokepoints']}
    settlements = old._settlements_by_cell(world)
    routes = old._routes_by_settlement(world)
    forced = {cid for cid, rows in settlements.items() if any(row['type'] == 'port' for row in rows)}
    max_flow = max(max(0.0, cell['flow_accumulation']) for cell in cells)
    waterway_complete = world['summary']['navigable_waterway_selection_complete']
    raw = {}
    selected = set()
    for cell in cells:
        cid = cell['id']
        marine = old._marine_neighbors(cell, by_id)
        coastal_land = not cell['is_water'] and bool(marine)
        bay_ok = not coastal_land or cell['harbor_suitability_supported']
        mouth_applicable = coastal_land and (cell['is_river'] or cell['landform'] in {'delta', 'floodplain', 'river_valley'})
        mouth_ok = not mouth_applicable or cell['harbor_suitability_supported']
        bay = old._protected_bay_index(cell, marine, by_id) if bay_ok else None
        mouth = old._river_mouth_index(cell, marine, max_flow) if mouth_ok else None
        strait = old._strait_access_index(cell, marine, chokepoints)
        suitability_ok = cell['is_water'] or (inputs[cid].available and cell['harbor_suitability_supported'] and bay_ok and mouth_ok)
        suitability = old._port_suitability(cell, bay, mouth, strait) if suitability_ok else None
        # The compared classification terms are required even if an earlier
        # priority would win; no partial class is published as a complete one.
        selection_ok = suitability_ok and bay_ok and mouth_ok and cell['harbor_suitability_supported']
        severe = cell['ice_thickness_m'] >= 80.0 or cell['biome'] == 'ice_cap'
        chosen = selection_ok and not cell['is_water'] and ((suitability >= old.PORT_SITE_THRESHOLD and not severe) or cid in forced)
        kind = old._site_type(bay, mouth, strait, cell['harbor_suitability_index'], suitability) if selection_ok else None
        cell.update(
            protected_bay_supported=bay_ok, river_mouth_port_supported=mouth_ok,
            port_suitability_supported=suitability_ok, port_site_selection_supported=selection_ok,
            protected_bay_index=round(bay, 6) if bay_ok else None,
            river_mouth_port_index=round(mouth, 6) if mouth_ok else None,
            strait_access_index=round(strait, 6),
            port_suitability_index=round(suitability, 6) if suitability_ok else None,
            port_site_id=-1 if selection_ok else None,
            port_site_type=(kind if chosen and kind != 'none' else 'none') if selection_ok else None,
        )
        if chosen:
            selected.add(cid)
        raw[cid] = (bay, mouth, strait, suitability)
    records = []
    for cid in sorted(selected):
        cell = by_id[cid]
        cell['port_site_id'] = len(records)
        if cell['port_site_type'] == 'none':
            cell['port_site_type'] = 'port_settlement'
        source_settlements = settlements.get(cid, [])
        sids = sorted(row['id'] for row in source_settlements)
        pids = sorted(row['id'] for row in source_settlements if row['type'] == 'port')
        marine = old._marine_neighbors(cell, by_id)
        severe = cell['ice_thickness_m'] >= 80.0 or cell['biome'] == 'ice_cap'
        records.append({
            'id': cell['port_site_id'], 'cell_id': cid, 'site_type': cell['port_site_type'],
            'area_km2': round(max(0.0, float(cell['area_km2'])), 6),
            'latitude_deg': round(float(cell['lat_deg']), 6), 'longitude_deg': round(float(cell['lon_deg']), 6),
            **{name: round(float(cell[name]), 6) for name in ('port_suitability_index', 'protected_bay_index', 'river_mouth_port_index', 'strait_access_index', 'harbor_suitability_index', 'navigability_index')},
            'settlement_ids': sids, 'port_settlement_ids': pids,
            'route_ids': sorted({rid for sid in sids for rid in routes.get(sid, set())}),
            'marine_region_ids': sorted({neighbor['marine_region_id'] for neighbor in marine if neighbor['marine_region_id'] >= 0}),
            'marine_chokepoint_ids': sorted({neighbor['marine_chokepoint_id'] for neighbor in marine if neighbor['marine_chokepoint_id'] >= 0}),
            'navigable_waterway_ids': old._waterway_ids_near_cell(cell, by_id) if waterway_complete else None,
            'navigable_waterway_links_complete': waterway_complete,
            **{name: cell[name] for name in ('landform', 'biome', 'water_body_type', 'is_river')},
            'selected_by_port_settlement': bool(pids),
            'selected_by_suitability': (cell['harbor_suitability_index'] >= .62 or cell['port_suitability_index'] >= old.PORT_SITE_THRESHOLD) and not severe,
        })
    complete = all(cell['port_site_selection_supported'] for cell in cells)
    kinds = Counter(row['site_type'] for row in records)
    summary = world['summary']
    summary.update(
        port_site_model=MODELS['ports']['model_type'], port_site_count=len(records),
        port_candidate_cell_count=len(selected) if complete else None,
        port_site_total_area_km2=round(sum(row['area_km2'] for row in records), 6),
        mean_protected_bay_index=_mean([values[0] for values in raw.values()]),
        mean_river_mouth_port_index=_mean([values[1] for values in raw.values()]),
        mean_strait_access_index=_mean([values[2] for values in raw.values()]),
        mean_port_suitability_index=_mean([values[3] for values in raw.values()]),
        mean_protected_bay_supported=all(cell['protected_bay_supported'] for cell in cells),
        mean_river_mouth_port_supported=all(cell['river_mouth_port_supported'] for cell in cells),
        mean_port_suitability_supported=all(cell['port_suitability_supported'] for cell in cells),
        port_settlement_count=sum(row['type'] == 'port' for rows in settlements.values() for row in rows),
        port_settlement_with_site_count=sum(row['type'] == 'port' and cid in selected for cid, rows in settlements.items() for row in rows),
        protected_bay_port_site_count=kinds.get('protected_bay_port', 0),
        river_mouth_port_site_count=kinds.get('river_mouth_port', 0),
        strait_port_site_count=kinds.get('strait_port', 0), port_site_type_counts=dict(sorted(kinds.items())),
        port_site_selection_complete=complete,
        port_site_applicable_cell_count=sum(not cell['is_water'] for cell in cells),
        port_site_supported_cell_count=sum(not cell['is_water'] and cell['port_site_selection_supported'] for cell in cells),
    )
    world['port_site_model'] = {**MODELS['ports'], 'candidate_cell_count': len(selected) if complete else None, 'site_count': len(records)}
    world['port_sites'] = records


def _movement_cost(current, neighbor, kind, by_id, radius):
    """Same cost equation, reading only the selected route branch's terms."""
    from . import route_corridors as old
    distance = old._cell_distance_km(current, neighbor, radius)
    body = neighbor['water_body_type']
    slope = old._clamp(abs(neighbor['elevation_m'] - current['elevation_m']) / 2000.0)
    ice = old._clamp(neighbor['ice_thickness_m'] / 320.0)
    aridity = old._clamp(neighbor['seasonal_aridity_index'])
    mountain = old._clamp((neighbor['elevation_m'] - 1000.0) / 2200.0)
    if kind == 'coastal_sea':
        support = max(neighbor['coastal_route_index'], neighbor['navigability_index'])
        water = .08 if body in old.MARINE_WATER_TYPES else .72 if old._is_coastal(neighbor, by_id) else 1.80
    elif kind == 'river_corridor':
        support = max(neighbor['river_valley_route_index'], neighbor['river_navigability_index'])
        water = 1.45 if body in old.MARINE_WATER_TYPES else .18 if neighbor['is_river'] else .42
    elif kind == 'mountain_pass':
        support = max(neighbor['mountain_pass_route_index'], neighbor['river_valley_route_index'] * .45)
        water = 1.70 if neighbor['is_water'] else .20
    else:
        support = max(neighbor['river_valley_route_index'] * .72, neighbor['coastal_route_index'] * .62, neighbor['oasis_route_index'] * .72, neighbor['mountain_pass_route_index'] * .46)
        water = 1.65 if body in old.MARINE_WATER_TYPES else .20 if neighbor['is_river'] else .34
    terrain = .64 + slope * .42 + ice * .55 + aridity * .18 + mountain * .20 + water - support * .50
    return distance * max(.12, terrain)


def _path(start, end, kind, by_id, radius):
    """None is unavailable; [] is known absent. Unknown edges are never skipped."""
    if start not in by_id or end not in by_id:
        return []
    if start == end:
        return [start]
    reached = {start}
    todo = [start]
    for cid in todo:
        for nid in by_id[cid]['neighbors']:
            if nid not in reached:
                reached.add(nid)
                todo.append(nid)
    if end not in reached:
        return []
    for cid in reached:
        cell = by_id[cid]
        for nid in cell['neighbors']:
            target = by_id[nid]
            if kind == 'coastal_sea':
                if not (target['coastal_route_supported'] and target['navigability_supported']):
                    return None
            elif kind not in {'river_corridor', 'mountain_pass'} and not target['coastal_route_supported']:
                return None
    queue = [(0.0, start)]
    best = {start: 0.0}
    previous = {}
    visited = set()
    while queue:
        cost, cid = heapq.heappop(queue)
        if cid in visited:
            continue
        visited.add(cid)
        if cid == end:
            break
        for nid in by_id[cid]['neighbors']:
            next_cost = cost + _movement_cost(by_id[cid], by_id[nid], kind, by_id, radius)
            if not math.isfinite(next_cost):
                raise ValueError('unrepresentable route cost')
            if next_cost < best.get(nid, float('inf')):
                best[nid] = next_cost
                previous[nid] = cid
                heapq.heappush(queue, (next_cost, nid))
    if end not in best:
        return []
    path = [end]
    while path[-1] != start:
        path.append(previous[path[-1]])
    return path[::-1]


def _corridor_record(number, route, path, by_id, settlements, radius, membership_complete):
    from . import route_corridors as old
    cells = [by_id[cid] for cid in path]
    diagnostics = route['route_corridor_diagnostics_supported']
    source, target = settlements[route['from']], settlements[route['to']]
    distance = old._path_length_km(path, by_id, radius)
    straight = max(.001, float(route['distance_km']))
    waterway_complete = all(cell['navigable_waterway_membership_complete'] for cell in cells)
    port_complete = all(cell['port_site_selection_supported'] for cell in cells)
    result = {
        'id': number, 'route_id': route['id'], 'route_type': route['type'],
        'corridor_type': route['route_corridor_type'],
        'from_settlement_id': route['from'], 'to_settlement_id': route['to'],
        'start_cell_id': source['cell_id'], 'end_cell_id': target['cell_id'],
        'cell_count': len(path), 'cell_ids': list(path),
        'path_length_km': round(distance, 6), 'straight_distance_km': round(straight, 6),
        'detour_ratio': round(distance / straight, 6),
        'mean_route_corridor_index': _mean([float(cell['route_corridor_index']) for cell in cells]) if membership_complete else None,
        'max_route_corridor_index': round(max(float(cell['route_corridor_index']) for cell in cells), 6) if membership_complete else None,
        'settlement_ids': sorted({route['from'], route['to']} - {-1}),
        'region_ids': sorted({source['region_id'], target['region_id']} - {-1}), 'route_ids': [route['id']],
        'navigable_waterway_ids': sorted({cell['navigable_waterway_id'] for cell in cells if cell['navigable_waterway_id'] >= 0}) if waterway_complete else None,
        'port_site_ids': sorted({cell['port_site_id'] for cell in cells if cell['port_site_id'] >= 0}) if port_complete else None,
        'route_path_supported': True, 'route_corridor_diagnostics_supported': diagnostics,
        'route_corridor_membership_complete': membership_complete,
        'navigable_waterway_links_complete': waterway_complete, 'port_site_links_complete': port_complete,
    }
    for name, prefix in (('mountain_pass', 'mountain_pass'), ('river_valley', 'river_valley'), ('coastal', 'coastal'), ('oasis', 'oasis')):
        values = [cell[name + '_route_index'] for cell in cells]
        result['mean_' + name + '_route_index'] = _mean(values)
        result[prefix + '_cell_count'] = sum(value >= .45 for value in values) if all(value is not None for value in values) else None
    result['named_feature_cell_count'] = sum(any(value >= .45 for value in old._feature_values(cell).values()) for cell in cells) if diagnostics else None
    return result


def corridors(world, inputs):
    from . import route_corridors as old
    cells = world['cells']
    by_id = {cell['id']: cell for cell in cells}
    settlements = {row['id']: row for row in world['settlements']}
    routes = {row['id']: row for row in world['routes']}
    oasis = {row['cell_id'] for row in settlements.values() if row['type'] == 'oasis'}
    max_flow = max(max(0.0, cell['flow_accumulation']) for cell in cells)
    radius = old.planet_radius_km(world)
    for cell in cells:
        marine = cell['water_body_type'] in old.MARINE_WATER_TYPES
        coast_branch = not marine and bool(old._marine_neighbors(cell, by_id))
        coast_ok = not coast_branch or (cell['harbor_suitability_supported'] and cell['port_suitability_supported'])
        cell.update(
            mountain_pass_route_index=round(old._mountain_pass_index(cell, by_id), 6),
            river_valley_route_index=round(old._river_valley_route_index(cell, max_flow), 6),
            coastal_route_index=round(old._coastal_route_index(cell, by_id), 6) if coast_ok else None,
            coastal_route_supported=coast_ok,
            oasis_route_index=round(old._oasis_route_index(cell, oasis), 6),
        )
    paths = {}
    for rid in sorted(routes):
        route = routes[rid]
        source, target = settlements.get(route['from']), settlements.get(route['to'])
        path = _path(source['cell_id'], target['cell_id'], route['type'], by_id, radius) if source is not None and target is not None else []
        paths[rid] = path
        diagnostics = path is not None and all(by_id[cid]['coastal_route_supported'] for cid in path)
        route.update(route_path_supported=path is not None, route_corridor_diagnostics_supported=diagnostics,
                     route_corridor_id=None if path is None else -1,
                     route_corridor_type=None if not diagnostics else 'none', path_cell_ids=path)
    path_complete = all(route['route_path_supported'] for route in routes.values())
    diagnostics_complete = all(route['route_corridor_diagnostics_supported'] for route in routes.values())
    membership_complete = path_complete and diagnostics_complete
    for cell in cells:
        cell.update(route_corridor_membership_complete=membership_complete,
                    route_corridor_index=0.0 if membership_complete else None,
                    route_corridor_type='none' if membership_complete else None,
                    route_corridor_id=-1 if membership_complete else None)
    records = []
    for rid in sorted(routes):
        route, path = routes[rid], paths[rid]
        if not path:
            continue
        number = len(records)
        path_cells = [by_id[cid] for cid in path]
        kind = old._primary_corridor_type(path_cells, route['type']) if route['route_corridor_diagnostics_supported'] else None
        route.update(route_corridor_id=number, route_corridor_type=kind)
        if membership_complete:
            for cell in path_cells:
                membership = old._clamp(.35 + max(old._feature_values(cell).values()) * .65)
                if membership >= float(cell['route_corridor_index']):
                    cell.update(route_corridor_index=round(membership, 6), route_corridor_type=kind, route_corridor_id=number)
        records.append(_corridor_record(number, route, path, by_id, settlements, radius, membership_complete))
    kinds = Counter(row['corridor_type'] for row in records) if diagnostics_complete else None
    summary = world['summary']
    summary.update(
        route_corridor_model=MODELS['corridors']['model_type'], route_corridor_count=len(records),
        route_corridor_cell_count=sum(cell['route_corridor_id'] >= 0 for cell in cells) if membership_complete else None,
        route_corridor_total_path_length_km=round(sum(row['path_length_km'] for row in records), 6) if path_complete else None,
        mean_route_corridor_index=_mean([float(cell['route_corridor_index']) for cell in cells]) if membership_complete else None,
        mean_mountain_pass_route_index=_mean([float(cell['mountain_pass_route_index']) for cell in cells]),
        mean_river_valley_route_index=_mean([float(cell['river_valley_route_index']) for cell in cells]),
        mean_coastal_route_index=_mean([cell['coastal_route_index'] for cell in cells]),
        mean_oasis_route_index=_mean([float(cell['oasis_route_index']) for cell in cells]),
        route_feature_coverage_index=(round(sum(row['named_feature_cell_count'] > 0 for row in records) / len(records), 6) if records else 1.0) if diagnostics_complete else None,
        mountain_pass_route_corridor_count=kinds.get('mountain_pass_corridor', 0) if diagnostics_complete else None,
        river_valley_route_corridor_count=kinds.get('river_valley_corridor', 0) if diagnostics_complete else None,
        coastal_route_corridor_count=kinds.get('coastal_corridor', 0) if diagnostics_complete else None,
        oasis_route_corridor_count=kinds.get('oasis_corridor', 0) if diagnostics_complete else None,
        route_corridor_type_counts=dict(sorted(kinds.items())) if diagnostics_complete else None,
        route_path_selection_complete=path_complete,
        route_corridor_diagnostics_complete=diagnostics_complete,
        route_corridor_membership_complete=membership_complete,
        coastal_route_estimates_complete=all(cell['coastal_route_supported'] for cell in cells),
        route_path_supported_count=sum(route['route_path_supported'] for route in routes.values()),
        route_corridor_diagnostics_supported_count=sum(route['route_corridor_diagnostics_supported'] for route in routes.values()),
    )
    world['route_corridor_model'] = {**MODELS['corridors'], 'planet_radius_km': radius, 'route_count': len(routes), 'corridor_count': len(records)}
    world['route_corridors'] = records


MODELS = {'corridors': {'availability_policy': 'null_unavailable_values_and_typed_flags_with_structural_zeros_v1',
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
