"""Portable retained-world contracts plus explicitly scoped equation controls."""
from copy import deepcopy
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from magic_geo.navigability_diagnostics import enrich_world_with_navigability_diagnostics
from magic_geo.port_sites import enrich_world_with_port_sites
from magic_geo.route_corridors import enrich_world_with_route_corridors
from magic_geo.human_water_transport_validation import (
    HumanWaterTransportError,
    validate_human_water_transport,
    validate_versioned_navigability,
    validate_versioned_port_sites,
    validate_versioned_route_corridors,
    _POLICIES,
    _DYNAMIC,
)

DATA=Path(__file__).parent/'data/human_water_transport'
STAGES=[('navigation','navigability_model',enrich_world_with_navigability_diagnostics),('ports','port_site_model',enrich_world_with_port_sites),('corridors','route_corridor_model',enrich_world_with_route_corridors)]
NATURAL_KEYS=('planet_parameters','climate_model','climate_energy_model','climate_energy_balance_records','climate_energy_orbit_forcing','climate_energy_transport','aquifer_resource_model','aquifer_systems','groundwater_recharge_model','groundwater_flow_model','groundwater_flow_systems','river_channel_morphology_model','river_channel_systems','river_hydraulics_model','river_hydraulic_reaches','karst_diagnostics_model','karst_systems')


def load(name):
    manifest=json.loads((DATA/'manifest.json').read_text())[name]
    assert hashlib.sha256((DATA/manifest['config_file']).read_bytes()).hexdigest()==manifest['config_sha256']
    raw=(DATA/(name+'.json.gz')).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==manifest['fixture_sha256']
    decoded=gzip.decompress(raw)
    assert hashlib.sha256(decoded).hexdigest()==manifest['uncompressed_sha256']
    return json.loads(decoded)


def upgrade(world):
    # This module preserves the historical human-v2 numerical contract. The
    # retained physical fixture already has the earlier selection-v3 prototype;
    # absent human identities now deliberately select the new human-v3 family.
    # Declare the intended historical equation family before recomputation,
    # retaining the same fixture values and every original numerical assertion.
    for stage,key,producer in STAGES:
        world[key]={**_POLICIES[stage][2],**{name:world[key][name] for name in _DYNAMIC[stage]}}
        world['summary'][key]=_POLICIES[stage][2]['model_type']
        producer(world)
    return world


@pytest.fixture(scope='module')
def controls():
    return {'legacy':load('legacy_full'),'natural':upgrade(load('natural_parents_full'))}


def atomic_failure(world,producer):
    before=deepcopy(world)
    objects={key:value for key,value in world.items() if isinstance(value,(dict,list))}
    cell_objects=list(world.get('cells',[]))
    with pytest.raises(HumanWaterTransportError):producer(world)
    assert world==before
    assert all(world[key] is value for key,value in objects.items())
    assert all(a is b for a,b in zip(world.get('cells',[]),cell_objects))


@pytest.mark.parametrize('stage',[None,[],{},False,'unknown'])
def test_unknown_stage_returns_one_bounded_error_without_inspecting_world(stage):
    assert validate_human_water_transport(None,stage)==['human water transport: unknown stage']


@pytest.mark.parametrize('version',['legacy','natural'])
def test_genuine_control_exact_replay_and_parent_identity_retention(controls,version):
    world=deepcopy(controls[version]);before=deepcopy(world)
    objects={key:world[key] for key in NATURAL_KEYS if key in world}
    replaced={key for _,key,_ in STAGES}|{'navigable_waterways','port_sites','route_corridors'}
    unowned_root={key:value for key,value in world.items() if isinstance(value,(dict,list)) and key not in replaced}
    # Native geometry, orbit samples, ecology arrays and other nested cell inputs
    # must retain their identities as well as equality.
    nested_cell_inputs=[{k:v for k,v in c.items() if isinstance(v,(list,dict))} for c in world['cells']]
    nested_route_inputs=[{k:v for k,v in r.items() if isinstance(v,(list,dict)) and k!='path_cell_ids'} for r in world['routes']]
    cell_list=world['cells'];cell_objects=list(cell_list);route_list=world['routes'];route_objects=list(route_list)
    route_unowned=[{k:v for k,v in r.items() if k not in {'route_corridor_id','route_corridor_type','path_cell_ids'}} for r in route_list]
    for stage,key,producer in STAGES:
        assert validate_human_water_transport(world,stage)==[]
        assert producer(world) is world
        assert validate_human_water_transport(world,stage)==[]
    assert world==before  # Exact historical parity and current idempotence.
    assert all(world[key] is value for key,value in objects.items())
    assert all(world[key] is value for key,value in unowned_root.items())
    assert world['cells'] is cell_list and all(a is b for a,b in zip(world['cells'],cell_objects))
    assert all(cell[k] is v for cell,fields in zip(world['cells'],nested_cell_inputs) for k,v in fields.items())
    assert world['routes'] is route_list and all(a is b for a,b in zip(world['routes'],route_objects))
    assert all(route[k] is v for route,fields in zip(world['routes'],nested_route_inputs) for k,v in fields.items())
    assert [{k:v for k,v in r.items() if k not in {'route_corridor_id','route_corridor_type','path_cell_ids'}} for r in route_list]==route_unowned
    assert len(world['settlements'])==4 and len(world['routes'])==5
    assert [len(world[k]) for k in ('navigable_waterways','port_sites','route_corridors')]==[2,4,5]


def test_v2_requires_recomputation_and_declares_actual_source_namespace(controls):
    original=load('natural_parents_full')
    atomic_failure(original,enrich_world_with_navigability_diagnostics)
    actual=controls['natural']
    assert actual['navigability_model']['watershed_link_basis']=='native_cell_basin_ids_not_watershed_record_ids'
    assert 'watershed_link_basis' not in controls['legacy']['navigability_model']
    assert all(actual[key]['model_type'].endswith('_v2') for _,key,_ in STAGES)
    cells={c['id']:c for c in actual['cells']}
    record_ids={r['id'] for r in actual['watersheds']}
    assert any(b not in record_ids for w in actual['navigable_waterways'] for b in w['watershed_ids'])
    for waterway in actual['navigable_waterways']:
        assert waterway['watershed_ids']==sorted({cells[c]['basin_id'] for c in waterway['cell_ids'] if cells[c]['basin_id']>=0})
        assert all(cells[b]['flow_to']==-1 and cells[b]['basin_id']==b for b in waterway['watershed_ids'])
    assert sum(a['river_navigability_index']!=b['river_navigability_index'] for a,b in zip(original['cells'],actual['cells']))==3
    assert sum(a['oasis_route_index']!=b['oasis_route_index'] for a,b in zip(original['cells'],actual['cells']))==4
    assert [r['path_cell_ids'] for r in original['routes']]==[r['path_cell_ids'] for r in actual['routes']]


@pytest.mark.parametrize('stage,key,producer',STAGES)
@pytest.mark.parametrize('bad',['unknown','partial','extra','boolean_count','nan_threshold','wrong_summary','wrong_parent'])
def test_declared_contract_errors_reject_before_any_mutation(controls,stage,key,producer,bad):
    world=deepcopy(controls['natural'])
    if bad=='unknown':world[key]['model_type']='unknown_v9'
    elif bad=='partial':del world['summary'][key]
    elif bad=='extra':world[key]['undeclared_policy']=True
    elif bad=='boolean_count':world[key][next(k for k in world[key] if k.endswith('_count'))]=True
    elif bad=='nan_threshold':world[key][next(k for k in world[key] if k.endswith('_threshold'))]=math.nan
    elif bad=='wrong_summary':world['summary'][key]='wrong'
    else:
        parent={'navigation':'river_channel_morphology_model','ports':'navigability_model','corridors':'aquifer_resource_model'}[stage]
        world[parent]['model_type']='unknown_parent'
    assert validate_human_water_transport(world,stage)
    atomic_failure(world,producer)


@pytest.mark.parametrize('stage,key,producer',STAGES)
@pytest.mark.parametrize('bad',['own_without_cells','summary_only','missing_parent','malformed_parent'])
def test_partial_envelopes_never_fallback_to_old_stage(controls,stage,key,producer,bad):
    world=deepcopy(controls['natural'])
    if bad=='own_without_cells':world['cells']=[]
    elif bad=='summary_only':del world[key]
    else:
        parent={'navigation':'river_hydraulics_model','ports':'navigability_model','corridors':'port_site_model'}[stage]
        if bad=='missing_parent':del world[parent]
        else:world[parent]=[]
    atomic_failure(world,producer)


@pytest.mark.parametrize('bad',['duplicate_cell','duplicate_route','duplicate_settlement','duplicate_chokepoint','unknown_neighbor','nonreciprocal_neighbor','unknown_basin','nonterminal_basin','chokepoint_reverse','infinite_area','unknown_marine_region'])
def test_source_graph_and_finite_guards_are_independent(controls,bad):
    world=deepcopy(controls['natural'])
    if bad.startswith('duplicate_'):
        family={'duplicate_cell':'cells','duplicate_route':'routes','duplicate_settlement':'settlements','duplicate_chokepoint':'marine_chokepoints'}[bad]
        world[family].append(deepcopy(world[family][0]))
    elif bad=='unknown_neighbor':world['cells'][0]['neighbors'].append(999999)
    elif bad=='nonreciprocal_neighbor':world['cells'][0]['neighbors'].pop()
    elif bad=='unknown_basin':world['cells'][0]['basin_id']=999999
    elif bad=='nonterminal_basin':world['cells'][0]['basin_id']=0
    elif bad=='chokepoint_reverse':
        cell=next(c for c in world['cells'] if c['marine_chokepoint_id']>=0);cell['marine_chokepoint_id']=-1
    elif bad=='infinite_area':world['cells'][-1]['area_km2']=math.inf
    else:world['cells'][0]['marine_region_id']=999999
    assert validate_versioned_navigability(world)
    atomic_failure(world,enrich_world_with_navigability_diagnostics)


@pytest.mark.parametrize('field',['river_channel_width_m','hydraulic_navigability_index','aquifer_productivity_index'])
def test_finite_parent_scalar_tamper_is_not_hidden_by_unchanged_metadata(controls,field):
    world=deepcopy(controls['natural'])
    cell=next(c for c in world['cells'] if c['is_river'] and not c['is_water'])
    cell[field]+=.03
    assert validate_versioned_route_corridors(world)
    atomic_failure(world,enrich_world_with_route_corridors)


@pytest.mark.parametrize('stage,key,producer',STAGES)
@pytest.mark.parametrize('bad',[None,'invalid',math.nan,math.inf,True])
def test_later_consumed_field_error_is_atomic(controls,stage,key,producer,bad):
    world=deepcopy(controls['natural'])
    # Coordinate is directly consumed by ports/corridors; elevation by navigation.
    field='elevation_m' if stage=='navigation' else 'lat_deg'
    world['cells'][-1][field]=bad
    atomic_failure(world,producer)


@pytest.mark.parametrize('stage,key,producer',STAGES)
def test_late_publication_failure_keeps_all_original_objects(controls,stage,key,producer,monkeypatch):
    world=deepcopy(controls['natural'])
    import magic_geo._human_water_publication as publication
    # Inject failure after equations have staged their complete output.
    monkeypatch.setattr(publication,'validate_human_water_transport',lambda *args:['deliberate independent replay failure'])
    atomic_failure(world,producer)


@pytest.mark.parametrize('stage,key,producer',STAGES)
def test_record_scalar_and_link_tamper_rejects(controls,stage,key,producer):
    family={'navigation':'navigable_waterways','ports':'port_sites','corridors':'route_corridors'}[stage]
    for field,value in [('id',True),('route_ids',[999999]),('cell_ids',[999999]) if stage!='ports' else ('cell_id',999999)]:
        world=deepcopy(controls['natural']);world[family][0][field]=value
        before=deepcopy(world)
        assert validate_human_water_transport(world,stage)
        assert world==before


@pytest.mark.parametrize('stage,key,producer',STAGES)
def test_geo_only_never_publishes_human_stages(stage,key,producer):
    world=load('natural_geo')
    assert world['generation_scope']=='geo_only'
    assert all(key not in world for _,key,_ in STAGES)
    atomic_failure(world,producer)


@pytest.mark.parametrize('mode',['missing_settlement','missing_cell'])
def test_scoped_invalid_endpoint_retains_skip_sentinel_without_claiming_full_world(controls,mode):
    # Downstream-only controlled human inputs; native settlement replay is not claimed.
    world=deepcopy(controls['natural'])
    if mode=='missing_settlement':world['routes'][0]['from']=999999
    else:
        source=world['routes'][0]['from'];next(s for s in world['settlements'] if s['id']==source)['cell_id']=999999
    upgrade(world)
    route=world['routes'][0]
    assert (route['route_corridor_id'],route['route_corridor_type'],route['path_cell_ids'])==(-1,'none',[])
    assert validate_versioned_route_corridors(world)==[]


def test_scoped_navigation_raw_threshold_does_not_use_serialized_rounding():
    # Unpublished equation-stage control; deliberately no parent/full-world claim.
    from magic_geo.navigability_diagnostics import _enrich_legacy_equations
    for epsilon,expected_count in [(-4e-7,0),(4e-7,1)]:
        cells=[{'id':0,'is_water':True,'water_body_type':'ocean','water_depth_m':(.52+epsilon-.08-.15)*180/.30,'neighbors':[1,2,3]}]
        cells.extend({'id':i,'is_water':False,'water_body_type':'land','neighbors':[0]} for i in (1,2,3))
        world={'cells':cells,'settlements':[],'routes':[]}
        _enrich_legacy_equations(world)
        assert cells[0]['navigability_index']==.52
        assert world['summary']['navigable_cell_count']==expected_count
        assert (cells[0]['navigable_waterway_id']>=0)==bool(expected_count)


def test_scoped_symmetric_route_tie_uses_smallest_cell_id_and_skip_no_path():
    # Equal-cost, geometric four-node diamond; isolated routing equation only.
    from magic_geo.route_corridors import _shortest_route_path
    cells={0:{'id':0,'lat_deg':0.,'lon_deg':0.,'neighbors':[2,1]},1:{'id':1,'lat_deg':1.,'lon_deg':1.,'neighbors':[0,3]},2:{'id':2,'lat_deg':-1.,'lon_deg':1.,'neighbors':[0,3]},3:{'id':3,'lat_deg':0.,'lon_deg':2.,'neighbors':[1,2]}}
    assert _shortest_route_path(0,3,'overland',cells,6371.)==[0,1,3]
    cells[1]['neighbors']=[0];cells[2]['neighbors']=[0];cells[3]['neighbors']=[]
    assert _shortest_route_path(0,3,'overland',cells,6371.)==[]
