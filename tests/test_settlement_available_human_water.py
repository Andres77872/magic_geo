"""Retained full-source transport plus explicitly scoped equation/graph controls.

No native generation. Mixed graph controls exercise consumer equations only;
they do not fabricate an accepted climate certificate or native settlement run.
"""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_human_water_transport import load
from test_settlement_climate_support import ARCHIVES, enrich as enrich_site_metadata
from magic_geo import navigability_diagnostics as nav
from magic_geo import port_sites as port
from magic_geo import route_corridors as corridor
from magic_geo import _human_water_available_equations as equations
from magic_geo import _human_water_availability_replay as oracle
from magic_geo.human_water_transport_validation import (
    HumanWaterTransportError, _OWNED, _POLICIES, _DYNAMIC,
    owned_fields, validate_human_water_transport,
)
from magic_geo.human_water_validation_dispatch import validate_public_human_water_transport

STAGES = [('navigation', 'navigability_model', 'navigable_waterways', nav.enrich_world_with_navigability_diagnostics),
          ('ports', 'port_site_model', 'port_sites', port.enrich_world_with_port_sites),
          ('corridors', 'route_corridor_model', 'route_corridors', corridor.enrich_world_with_route_corridors)]


def clear_transport(world):
    for stage, key, family, _ in STAGES:
        world.pop(key, None)
        world.pop(family, None)
        fields = owned_fields(stage, 3)
        for cell in world['cells']:
            for name in fields['cell']:
                cell.pop(name, None)
        for route in world['routes']:
            for name in fields['route']:
                route.pop(name, None)
        for name in fields['summary']:
            world['summary'].pop(name, None)
    return world


@pytest.fixture(scope='module')
def current():
    world = clear_transport(load('natural_parents_full'))
    for stage, _, _, producer in STAGES:
        producer(world)
        assert validate_human_water_transport(world, stage) == []
    return world


def test_actual_current_parent_chain_and_unowned_identity(current):
    world = deepcopy(current)
    before = deepcopy(world)
    top = {key: value for key, value in world.items() if isinstance(value, (dict, list)) and key not in {row[1] for row in STAGES} | {row[2] for row in STAGES}}
    cells, routes = list(world['cells']), list(world['routes'])
    nested = [{key: value for key, value in cell.items() if isinstance(value, (list, dict))} for cell in cells]
    for stage, key, _, producer in STAGES:
        assert producer(world) is world
        assert world[key]['model_type'].endswith('_v3')
        assert validate_human_water_transport(world, stage) == []
    assert world == before
    assert all(world[key] is value for key, value in top.items())
    assert all(a is b for a, b in zip(world['cells'], cells))
    assert all(a is b for a, b in zip(world['routes'], routes))
    assert all(cell[key] is value for cell, fields in zip(cells, nested) for key, value in fields.items())


@pytest.mark.parametrize('name', list(ARCHIVES))
def test_independent_site_view_on_actual_retained_hot_and_mixed_stage_inputs(name):
    # These retained inputs have accepted seasonal sources and isolated native
    # site/route outputs. This checks that boundary only, not a new water chain.
    world = enrich_site_metadata(deepcopy(ARCHIVES[name]['seasonal_supported_selection']))
    before = deepcopy(world)
    view = oracle._site_availability(world)
    assert view == {cell['id']: cell['is_water'] or cell['is_lake'] or cell['settlement_climate_supported'] for cell in world['cells']}
    if name == 'earthlike_seed':
        zeros = {(cell['is_water'] or cell['is_lake'], view[cell['id']]) for cell in world['cells'] if cell['settlement_score'] == 0}
        assert zeros == {(True, True), (False, True), (False, False)}
    assert world == before


def test_supported_actual_values_equal_independently_validated_historical_math(current):
    old = load('natural_parents_full')
    # Explicitly scoped numerical comparison on the same actual complete
    # inputs. Private historical equations are followed by their independent
    # historical oracle, never claimed as an untouched historical archive.
    for stage, key, family, _ in STAGES:
        {'navigation': nav, 'ports': port, 'corridors': corridor}[stage]._enrich_legacy_equations(old)
        old[key] = {**_POLICIES[stage][2], **{name: old[key][name] for name in _DYNAMIC[stage]}}
        old['summary'][key] = _POLICIES[stage][2]['model_type']
        assert validate_human_water_transport(old, stage) == []
        for a, b in zip(old['cells'], current['cells']):
            assert {name: a[name] for name in _OWNED[stage]['cell']} == {name: b[name] for name in _OWNED[stage]['cell']}
        for a, b in zip(old['routes'], current['routes']):
            assert {name: a[name] for name in _OWNED[stage]['route']} == {name: b[name] for name in _OWNED[stage]['route']}
        assert len(old[family]) == len(current[family])
        for a, b in zip(old[family], current[family]):
            assert a == {name: b[name] for name in a}
        for name in _OWNED[stage]['summary']:
            if name != key:
                assert old['summary'][name] == current['summary'][name]
    assert validate_public_human_water_transport(old, natural_water=True) == (True, [])
    assert validate_public_human_water_transport(current, natural_water=True) == (True, [])


def test_explicit_actual_historical_own_contract_remains_historical():
    world = load('legacy_full')
    before = deepcopy(world)
    for stage, key, _, producer in STAGES:
        assert validate_human_water_transport(world, stage) == []
        producer(world)
        assert world[key]['model_type'].endswith('_v1')
    assert world == before
    assert validate_public_human_water_transport(world, natural_water=False) == (False, [])


@pytest.mark.parametrize('stage,key,family,producer', STAGES)
def test_new_availability_mirrors_cannot_hide_under_historical_own(stage, key, family, producer):
    world = load('legacy_full')
    added = set(owned_fields(stage, 3)['cell']) - set(_OWNED[stage]['cell'])
    world['cells'][0][next(iter(added))] = True
    before = deepcopy(world)
    assert validate_human_water_transport(world, stage)
    with pytest.raises(HumanWaterTransportError):
        producer(world)
    assert world == before


@pytest.mark.parametrize('stage,key,family,producer', STAGES)
@pytest.mark.parametrize('root', [None, [], True])
def test_malformed_root_returns_diagnostic_and_producer_valueerror(stage, key, family, producer, root):
    assert validate_human_water_transport(root, stage)
    assert validate_public_human_water_transport(root, natural_water=True)[1]
    with pytest.raises(ValueError):
        producer(root)


@pytest.mark.parametrize('stage,key,family,producer', STAGES)
def test_absent_own_cannot_keep_old_owned_mirrors(current, stage, key, family, producer):
    world = deepcopy(current)
    world.pop(key)
    world['summary'].pop(key)
    before = deepcopy(world)
    with pytest.raises(HumanWaterTransportError):
        producer(world)
    assert world == before


@pytest.mark.parametrize('change', [
    lambda w: w['navigability_model'].update(candidate_cell_count=True),
    lambda w: w['navigability_model'].update(source_settlement_model='unknown'),
    lambda w: w['settlement_selection_model'].update(target_minimum=8.0),
    lambda w: w['settlement_selection_model'].update(extra=True),
    lambda w: w['route_network_model'].update(links_per_settlement=2.0),
    lambda w: w['cells'][0].update(harbor_suitability_supported=0),
    lambda w: w['cells'][0].update(navigability_index=None),
    lambda w: w['cells'][0].update(navigable_waterway_id=999),
    lambda w: w['cells'][0].pop('settlement_climate_supported'),
    lambda w: w['cells'][0].pop('runoff_mm_y'),
    lambda w: w['cells'][0].update(neighbors=[True]),
    lambda w: w['summary'].update(navigable_waterway_selection_complete=False),
])
def test_independent_source_and_output_mutations_are_rejected(current, change):
    world = deepcopy(current)
    change(world)
    assert validate_human_water_transport(world, 'navigation')


@pytest.mark.parametrize('change', [
    lambda w: w.pop('settlement_selection_model'),
    lambda w: w['settlement_selection_model'].update(extra=True),
    lambda w: w['cells'][0].pop('is_lake'),
    lambda w: w['cells'][0].update(temperature_c=False),
    lambda w: w['routes'][0].update(to=999),
])
def test_new_source_rejection_is_atomic(current, change):
    world = deepcopy(current)
    change(world)
    before = deepcopy(world)
    with pytest.raises(HumanWaterTransportError):
        port.enrich_world_with_port_sites(world)
    assert world == before


@pytest.mark.parametrize('stage,change', [
    ('ports', lambda w: w['cells'][0].update(port_site_selection_supported=1)),
    ('ports', lambda w: w['summary'].update(port_site_selection_complete=False)),
    ('ports', lambda w: w['summary'].update(port_candidate_cell_count=None)),
    ('ports', lambda w: w['port_sites'][0].update(navigable_waterway_links_complete=False)),
    ('ports', lambda w: w['port_sites'][0].update(navigable_waterway_ids=None)),
    ('ports', lambda w: w['port_sites'][0].update(port_suitability_index=.123456)),
    ('corridors', lambda w: w['routes'][0].update(route_path_supported=1)),
    ('corridors', lambda w: w['routes'][0].update(path_cell_ids=None)),
    ('corridors', lambda w: w['route_corridors'][0].update(path_length_km=.123456)),
    ('corridors', lambda w: w['route_corridors'][0].update(port_site_links_complete=False)),
    ('corridors', lambda w: w['summary'].update(route_path_supported_count=True)),
    ('corridors', lambda w: w['summary'].update(route_corridor_membership_complete=False)),
])
def test_independent_parent_record_coverage_and_numeric_mutations(current, stage, change):
    world = deepcopy(current)
    change(world)
    assert validate_human_water_transport(world, stage)


def test_independent_replay_blocks_mutated_producer_scalar_before_commit(current, monkeypatch):
    world = deepcopy(current)
    before = deepcopy(world)
    original = nav._harbor_suitability
    monkeypatch.setattr(nav, '_harbor_suitability', lambda *args: original(*args) + .01)
    with pytest.raises(HumanWaterTransportError):
        nav.enrich_world_with_navigability_diagnostics(world)
    assert world == before


def graph(unknown=True):
    cells = []
    adjacency = [[1, 2, 3], [0, 3], [0], [0, 1]]
    for cid, neighbors in enumerate(adjacency):
        water = cid == 1
        cells.append(dict(id=cid, neighbors=neighbors, is_water=water, is_lake=False,
                          is_river=cid != 1, water_body_type='continental_shelf' if water else 'land',
                          area_km2=1., flow_accumulation=1., runoff_mm_y=100., elevation_m=0.,
                          water_depth_m=20. if water else 0., landform='delta', biome='grassland',
                          sediment_routing_load_m=0., river_channel_depth_m=1., river_channel_width_m=1.,
                          hydraulic_navigability_index=.2, ice_thickness_m=0., seasonal_aridity_index=.2,
                          settlement_score=0. if cid in (0, 1, 2) else .8,
                          settlement_climate_supported=cid != 1 and not (cid == 0 and unknown),
                          temperature_c=20., lat_deg=0., lon_deg=float(cid),
                          marine_region_id=0, basin_id=-1, marine_chokepoint_id=-1,
                          boundary_convergent=0., fertility=.2, groundwater_recharge_mm_y=0.,
                          aquifer_productivity_index=0., soil_moisture_index=0.))
    world = dict(cells=cells, summary={}, marine_chokepoints=[],
                 settlements=[dict(id=0, cell_id=2, type='farming', region_id=0), dict(id=1, cell_id=3, type='port', region_id=0)],
                 routes=[dict(id=0, **{'from': 0, 'to': 1}, type='river_corridor', distance_km=100.),
                         dict(id=1, **{'from': 0, 'to': 1}, type='overland', distance_km=100.)],
                 planet_parameters={'radius_km': 6371.})
    states = {cid: SimpleNamespace(available=cid != 0 or not unknown) for cid in range(4)}
    return world, states


def check_equations(world, states, stage):
    getattr(equations, {'navigation': 'navigation', 'ports': 'ports', 'corridors': 'corridors'}[stage])(world, states)
    expected = getattr(oracle, 'expected_' + {'navigation': 'navigation', 'ports': 'ports', 'corridors': 'corridors'}[stage])(world, {cid: value.available for cid, value in states.items()})
    for family, key in [('cell', 'cells'), ('route', 'routes')]:
        for row in world[key]:
            if row['id'] in expected[family]:
                part = expected[family][row['id']]
                oracle._compare({name: row[name] for name in part}, part, stage)
    oracle._compare({name: world['summary'][name] for name in expected['summary']}, expected['summary'], stage)
    family = {'navigation': 'navigable_waterways', 'ports': 'port_sites', 'corridors': 'route_corridors'}[stage]
    oracle._compare(world[family], expected['records'], stage)
    return expected


def test_mixed_graph_preserves_known_physics_and_partial_local_ports():
    world, states = graph()
    check_equations(world, states, 'navigation')
    assert world['cells'][0]['harbor_suitability_index'] is None
    assert world['cells'][1]['harbor_suitability_index'] == 0
    assert world['cells'][1]['harbor_suitability_supported'] is True
    assert world['cells'][2]['harbor_suitability_index'] == 0
    assert world['cells'][2]['harbor_suitability_supported'] is True
    assert world['navigable_waterways'] == [] and world['summary']['navigable_waterway_selection_complete'] is False
    assert all(cell['navigable_waterway_id'] is None for cell in world['cells'])
    check_equations(world, states, 'ports')
    assert world['cells'][0]['port_suitability_index'] is None
    assert world['cells'][0]['port_site_id'] is None
    assert world['summary']['port_site_selection_complete'] is False
    assert world['port_sites'] and all(row['cell_id'] != 0 for row in world['port_sites'])
    assert all(row['navigable_waterway_ids'] is None and row['navigable_waterway_links_complete'] is False for row in world['port_sites'])
    check_equations(world, states, 'corridors')
    assert world['routes'][0]['route_path_supported'] is True
    assert 0 in world['routes'][0]['path_cell_ids']
    assert world['routes'][0]['route_corridor_diagnostics_supported'] is False
    assert world['routes'][1]['route_path_supported'] is False and world['routes'][1]['path_cell_ids'] is None
    assert all(cell['route_corridor_index'] is None for cell in world['cells'])
    assert world['route_corridors'][0]['path_length_km'] > 0
    assert world['route_corridors'][0]['mean_coastal_route_index'] is None


def test_no_unavailable_competitor_is_skipped_even_when_direct_known_edge_exists():
    world, states = graph()
    world['cells'][2]['neighbors'].append(3)
    world['cells'][3]['neighbors'].append(2)
    for stage in ('navigation', 'ports', 'corridors'):
        check_equations(world, states, stage)
    assert world['routes'][1]['path_cell_ids'] is None


def test_unknown_disconnected_component_does_not_invent_path_dependency():
    world, states = graph()
    world['cells'][0]['neighbors'] = [1]
    world['cells'][1]['neighbors'] = [0]
    world['cells'][2]['neighbors'] = [3]
    world['cells'][3]['neighbors'] = [2]
    for stage in ('navigation', 'ports', 'corridors'):
        check_equations(world, states, stage)
    assert world['routes'][1]['path_cell_ids'] == [2, 3]
    assert world['routes'][1]['route_path_supported'] is True


@pytest.mark.parametrize('same_endpoint', [False, True])
def test_disconnected_and_same_endpoint_paths_are_known_without_unknown_edge_cost(same_endpoint):
    world, states = graph()
    world['cells'][2]['neighbors'] = []
    world['cells'][0]['neighbors'].remove(2)
    if same_endpoint:
        world['routes'][1]['to'] = world['routes'][1]['from']
    for stage in ('navigation', 'ports', 'corridors'):
        check_equations(world, states, stage)
    assert world['routes'][1]['route_path_supported'] is True
    assert world['routes'][1]['path_cell_ids'] == ([2] if same_endpoint else [])


def test_supported_zero_and_support_rebuild_are_idempotent():
    world, states = graph()
    for stage in ('navigation', 'ports', 'corridors'):
        check_equations(world, states, stage)
    states[0].available = True
    world['cells'][0]['settlement_climate_supported'] = True
    for stage in ('navigation', 'ports', 'corridors'):
        check_equations(world, states, stage)
    assert all(cell['navigability_supported'] for cell in world['cells'])
    assert world['summary']['route_path_selection_complete'] is True
    before = deepcopy(world)
    for stage in ('navigation', 'ports', 'corridors'):
        check_equations(world, states, stage)
    assert world == before
