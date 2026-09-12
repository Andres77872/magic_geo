"""Portable isolated-stage tests; no native generation or full-world claims."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pytest

from magic_geo.land_use_zones import enrich_world_with_land_use_zones
from magic_geo.land_use_availability_validation import validate_land_use_availability

DATA=Path(__file__).parent/'data'
ACTUAL=json.loads((DATA/'agricultural_actual_inputs.json').read_text())
OLD=json.loads((DATA/'land_use_v1_outputs.json').read_text())
NUMERIC=('fertility','soil_depth_m','soil_moisture_index','soil_salinity_index','soil_erodibility_index',
         'erosion_rate','growing_season_months','runoff_mm_y','groundwater_recharge_mm_y','ice_thickness_m','seasonal_aridity_index')


def cell(**overrides):
    return {'id':0,'area_km2':1.0,'neighbors':[],'temperature_c':17.0,'is_water':False,'is_lake':False,
        'water_body_type':'land','resource':'none','biome':'temperate_forest','landform':'floodplain','is_river':False,
        'fertility':1.0,'soil_depth_m':3.2,'soil_moisture_index':1.0,'soil_salinity_index':0.0,
        'soil_erodibility_index':0.0,'erosion_rate':0.0,'growing_season_months':10.0,'runoff_mm_y':650.0,
        'groundwater_recharge_mm_y':300.0,'ice_thickness_m':0.0,'seasonal_aridity_index':0.0,**overrides}


def world(*cells, **extra):
    return {'cells':list(cells),'summary':{},'resource_deposits':[],'settlements':[],'routes':[],**extra}


def build(payload):
    assert enrich_world_with_land_use_zones(payload) is payload
    assert validate_land_use_availability(payload)==[]
    return payload


@pytest.mark.parametrize('temperature,supported',[(-100.,False),(-16.,False),(-9.,False),
    (math.nextafter(-9.,math.inf),True),(17.,True),(math.nextafter(43.,-math.inf),True),(43.,False),(52.,False),(100.,False)])
def test_own_open_annual_proxy_domain_preserves_positive_interior(temperature,supported):
    payload=build(world(cell(temperature_c=temperature)))
    c=payload['cells'][0]
    assert c['agricultural_habitat_applicable'] is True
    assert c['agricultural_climate_supported'] is c['agricultural_potential_supported'] is supported
    assert c['agricultural_potential_index']==float(supported)
    assert bool(payload['agricultural_zones']) is supported
    assert c['mining_surface_applicable'] is True


@pytest.mark.parametrize('value',[None,True,'17',[],{},math.nan,math.inf,-math.inf,1<<20000],
                         ids=['null','bool','string','list','object','nan','infinity','negative-infinity','overflowing-int'])
def test_invalid_annual_input_is_unavailable_without_coercion(value):
    payload=build(world(cell(temperature_c=value)))
    c=payload['cells'][0]
    assert not c['agricultural_climate_supported'] and not c['agricultural_potential_supported']
    assert c['agricultural_potential_index']==0. and c['agricultural_zone_id']==-1
    assert payload['agricultural_zones']==[]


@pytest.mark.parametrize('key',NUMERIC)
@pytest.mark.parametrize('value',[None,True,'0',[],math.nan,math.inf,1<<20000],
                         ids=['null','bool','string','list','nan','infinity','overflowing-int'])
def test_present_unusable_agricultural_descriptor_is_unavailable(key,value):
    payload=build(world(cell(**{key:value})))
    c=payload['cells'][0]
    assert c['agricultural_climate_supported'] is True
    assert not c['agricultural_potential_supported']
    assert c['agricultural_potential_index']==0. and payload['agricultural_zones']==[]


@pytest.mark.parametrize('key',(*NUMERIC,'temperature_c','is_river','landform','biome'))
def test_absent_descriptor_is_not_known_zero(key):
    c=cell();del c[key]
    payload=build(world(c))
    assert not c['agricultural_potential_supported']
    assert payload['agricultural_zones']==[]


@pytest.mark.parametrize('key,value',[('is_river',0),('is_river','false'),('landform',None),('landform',[]),('biome',False),('biome','')])
def test_malformed_categorical_agriculture_inputs_are_unavailable(key,value):
    payload=build(world(cell(**{key:value})))
    assert not payload['cells'][0]['agricultural_potential_supported']


@pytest.mark.parametrize('water,water_flag,lake_flag,expected_land',[
    ('ocean',True,False,False),('continental_shelf',False,False,False),('inland_sea',False,False,False),
    ('fresh_lake',False,True,False),('fresh_lake',False,False,False),('saline_basin',False,True,False),
    ('saline_basin',False,False,True),('land',False,False,True)])
def test_same_habitat_selector_excludes_aquatic_agriculture_and_exposed_mining(water,water_flag,lake_flag,expected_land):
    deposit={'id':7,'cell_id':0,'resource':'evaporites','reserve_potential_index':1.,'economic_viability_index':1.,
             'geologic_confidence_index':1.,'accessibility_index':1.,'extraction_hazard_index':0.}
    payload=world(cell(resource='evaporites',water_body_type=water,is_water=water_flag,is_lake=lake_flag),resource_deposits=[deposit])
    original=deepcopy(deposit)
    build(payload)
    c=payload['cells'][0]
    assert c['agricultural_habitat_applicable'] is c['mining_surface_applicable'] is expected_land
    assert bool(payload['agricultural_zones']) is bool(payload['mining_zones']) is expected_land
    assert payload['resource_deposits'][0] is deposit and deposit==original
    if not expected_land:
        assert c['mining_potential_index']==c['agricultural_potential_index']==0.


def test_supported_zero_is_available_and_has_no_zone():
    payload=build(world(cell(fertility=0.,soil_depth_m=0.,soil_moisture_index=0.,growing_season_months=0.,runoff_mm_y=0.,
        groundwater_recharge_mm_y=0.,landform='plain',biome='steppe',soil_salinity_index=1.,ice_thickness_m=400.,seasonal_aridity_index=1.)))
    c=payload['cells'][0]
    assert c['agricultural_potential_supported'] is True
    assert c['agricultural_potential_index']==0. and c['agricultural_zone_id']==-1
    assert payload['summary']['agricultural_potential_supported_cell_count']==1


def test_ecosystem_and_species_flags_do_not_gate_unconsumed_agriculture_inputs():
    payload=build(world(cell(primary_productivity_index=0.,primary_productivity_supported=False,
        vegetation_biomass_supported=False,forest_growth_supported=False,species_richness_supported=False)))
    assert payload['cells'][0]['agricultural_potential_index']==1.
    assert payload['cells'][0]['agricultural_potential_supported'] is True


@pytest.mark.parametrize('temperature',[-100.,100.,None])
def test_mining_has_no_agricultural_or_primary_temperature_gate(temperature):
    payload=world(cell(temperature_c=temperature,resource='placer_metals'),resource_deposits=[{
        'id':0,'cell_id':0,'reserve_potential_index':1.,'economic_viability_index':1.,'geologic_confidence_index':1.,'accessibility_index':1.,'extraction_hazard_index':0.}])
    build(payload)
    assert not payload['cells'][0]['agricultural_potential_supported']
    assert payload['cells'][0]['mining_surface_applicable'] is True
    assert payload['cells'][0]['mining_potential_index']==.82
    assert len(payload['mining_zones'])==1


@pytest.mark.parametrize('case',ACTUAL['cases'],ids=lambda c:c['name'])
def test_actual_archived_inputs_use_complete_consumed_graph_projections(case):
    raw=json.dumps(case['cell'],sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    assert hashlib.sha256(raw).hexdigest()==case['canonical_cell_sha256']
    fixture=ACTUAL['projections'][case['projection']]
    payload=deepcopy(fixture['world'])
    encoded=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    assert hashlib.sha256(encoded).hexdigest()==fixture['canonical_projection_sha256']
    assert len(payload['cells'])==fixture['source_cell_count']==(162 if case['projection']=='continental_realm' else 128)
    assert set(fixture['canonical_full_cell_sha256_by_id'])=={str(c['id']) for c in payload['cells']}
    c=next(c for c in payload['cells'] if c['id']==case['cell']['id'])
    assert fixture['canonical_full_cell_sha256_by_id'][str(c['id'])]==case['canonical_cell_sha256']
    assert c=={k:case['cell'][k] for k in ACTUAL['retained_cell_fields'] if k in case['cell']}
    deposits=payload['resource_deposits']
    snapshot=deepcopy(deposits)
    build(payload)
    assert deposits==snapshot and payload['resource_deposits'] is deposits
    for key in ('temperature_c','resource','fertility','soil_depth_m','water_body_type','is_lake','is_water'):
        assert c.get(key)==case['cell'].get(key)
    if case['name'] in ('hot_land','cold_land','hot_placer_material'):
        assert c['agricultural_habitat_applicable'] and not c['agricultural_potential_supported']
    elif case['name'] in ('fresh_lake','saline_lake_mineral'):
        assert not c['agricultural_habitat_applicable'] and not c['mining_surface_applicable']
    else:
        assert c['agricultural_potential_supported']


def test_exact_declared_v1_output_and_independent_replay_are_preserved():
    payload=deepcopy(OLD['input'])
    assert enrich_world_with_land_use_zones(payload) is payload
    assert payload==OLD['output']
    assert validate_land_use_availability(payload)==[]


def test_explicit_archive_upgrade_changes_only_owned_diagnostics():
    payload=deepcopy(OLD['output'])
    del payload['land_use_zone_model'];del payload['summary']['land_use_zone_model']
    originals=deepcopy(payload['resource_deposits'])
    build(payload)
    assert payload['resource_deposits']==originals
    assert payload['cells'][0]['agricultural_potential_supported'] is False
    assert payload['cells'][1]['agricultural_habitat_applicable'] is False
    assert payload['cells'][2]['mining_surface_applicable'] is False


@pytest.mark.parametrize('mutation',[
    lambda w:w.__setitem__('land_use_zone_model',None),lambda w:w.__setitem__('land_use_zone_model',{}),
    lambda w:w['land_use_zone_model'].__setitem__('model_type','unknown'),
    lambda w:w['land_use_zone_model'].__setitem__('agricultural_minimum_temperature_c',-16.),
    lambda w:w['land_use_zone_model'].__setitem__('extra',True),
    lambda w:w['summary'].__setitem__('land_use_zone_model','unknown'),
    lambda w:w['summary'].pop('land_use_zone_model'),lambda w:w.pop('land_use_zone_model'),
    lambda w:w.__setitem__('summary',None),lambda w:w['cells'][1].__setitem__('id',False),
    lambda w:w['cells'][1].__setitem__('area_km2',math.inf),lambda w:w['cells'][1].__setitem__('neighbors',[{}]),
    lambda w:w['cells'][1].__setitem__('resource',[]),lambda w:w['cells'][1].__setitem__('is_lake',None),
])
def test_malformed_envelopes_and_structural_inputs_reject_atomically(mutation):
    payload=build(world(cell(),cell(id=1)))
    mutation(payload);snapshot=deepcopy(payload);refs=list(payload['cells'])
    assert validate_land_use_availability(payload)
    with pytest.raises(ValueError):enrich_world_with_land_use_zones(payload)
    assert payload==snapshot and all(a is b for a,b in zip(refs,payload['cells']))


@pytest.mark.parametrize('root',[None,False,1,'world',[],[{}]])
def test_malformed_roots_are_diagnostics_and_producer_errors(root):
    assert validate_land_use_availability(root)
    with pytest.raises(ValueError):enrich_world_with_land_use_zones(root)


@pytest.mark.parametrize('declared',[False,True],ids=['new-input','declared-v2'])
@pytest.mark.parametrize('mutation,message',[
    (lambda w:w['cells'][0].update(neighbors=[999]),'unknown cell'),
    (lambda w:w['cells'][0].update(neighbors=[1,1]),'unique'),
    (lambda w:w['cells'][0].update(neighbors=[0]),'itself'),
    (lambda w:w.update(settlements=[{'id':5,'cell_id':999}]),'unknown cell'),
    (lambda w:w.update(resource_deposits=[{'id':4,'cell_id':999}]),'unknown cell'),
    (lambda w:w.update(settlements=[{'id':5,'cell_id':0}],routes=[{'id':3,'from':5,'to':999}]),'unknown settlement'),
],ids=['dangling-neighbor','repeated-neighbor','self-neighbor','settlement-cell','deposit-cell','route-settlement'])
def test_consumed_links_reject_atomically_for_new_and_reenriched_v2(declared,mutation,message):
    payload=world(cell(neighbors=[1]),cell(id=1,neighbors=[0]))
    if declared:
        build(payload)
    mutation(payload)
    snapshot=deepcopy(payload);cells=payload['cells'];refs=list(cells);summary=payload['summary']
    if declared:
        errors=validate_land_use_availability(payload)
        assert len(errors)==1 and message in errors[0]
    with pytest.raises(ValueError,match=message):
        enrich_world_with_land_use_zones(payload)
    assert payload==snapshot and payload['cells'] is cells and payload['summary'] is summary
    assert all(actual is original for actual,original in zip(cells,refs))


def test_stale_outputs_are_rebuilt_idempotently_without_replacing_native_objects():
    payload=build(world(cell(),cell(id=1,temperature_c=80.,area_km2=3.)))
    opaque={'test':'opaque object, not a certificate'};payload['climate_energy_model']=opaque
    summary=payload['summary'];refs=list(payload['cells'])
    for c in payload['cells']:
        c['agricultural_potential_supported']=not c['agricultural_potential_supported']
        c['agricultural_potential_index']=.123456;c['agricultural_zone_id']=99
    summary['agricultural_potential_supported_cell_count']=999
    build(payload);once=deepcopy(payload);build(payload)
    assert payload==once and payload['climate_energy_model'] is opaque and payload['summary'] is summary
    assert all(a is b for a,b in zip(refs,payload['cells']))
    assert summary['agricultural_potential_supported_area_km2']==1.
    assert summary['mean_agricultural_potential_index']==.5


@pytest.mark.parametrize('mutation',[
    lambda w:w['cells'][0].__setitem__('agricultural_potential_supported',False),
    lambda w:w['cells'][0].__setitem__('agricultural_habitat_applicable',False),
    lambda w:w['cells'][0].__setitem__('agricultural_climate_supported',False),
    lambda w:w['cells'][0].__setitem__('mining_surface_applicable',False),
    lambda w:w['cells'][0].__setitem__('agricultural_potential_index',.9),
    lambda w:w['cells'][0].__setitem__('agricultural_zone_id',-1),
    lambda w:w['agricultural_zones'][0].__setitem__('cell_ids',[]),
    lambda w:w['agricultural_zones'][0].__setitem__('mean_potential_index',.9),
    lambda w:w['agricultural_zones'][0].__setitem__('mean_fertility_index',.9),
    lambda w:w['agricultural_zones'][0].__setitem__('resource_deposit_ids',[99]),
    lambda w:w['summary'].__setitem__('agricultural_potential_supported_cell_count',True),
    lambda w:w['summary'].__setitem__('agricultural_potential_supported_area_km2',0.),
    lambda w:w['summary'].__setitem__('unsupported_terrestrial_agricultural_cell_count',1),
])
def test_independent_validator_rejects_owned_output_and_source_coverage_forgery(mutation):
    payload=build(world(cell()));mutation(payload);before=deepcopy(payload)
    assert validate_land_use_availability(payload)
    assert payload==before


def test_empty_new_model_has_complete_zero_counts():
    payload=build(world())
    assert payload['agricultural_zones']==payload['mining_zones']==[]
    assert payload['summary']['agricultural_potential_supported_cell_count']==0
    assert payload['summary']['mining_surface_applicable_cell_count']==0


@pytest.mark.parametrize('raw_potential,eligible',[(.5799998,False),(.58,True),(.5800002,True)])
def test_agricultural_candidates_use_raw_threshold_before_rounding(raw_potential,eligible):
    c=cell(fertility=1.,soil_moisture_index=1.,soil_depth_m=(raw_potential-.56)/.14*3.2,
        landform='plain',biome='steppe',growing_season_months=0.,runoff_mm_y=0.,groundwater_recharge_mm_y=0.)
    payload=build(world(c))
    assert c['agricultural_potential_supported']
    assert c['agricultural_potential_index']==.58
    assert bool(payload['agricultural_zones']) is eligible
    assert c['agricultural_zone_id']==(0 if eligible else -1)
    # A payload selected from the rounded .58 would incorrectly include the
    # below-threshold cell; the independent replay must reject that membership.
    c['agricultural_zone_id']=-1 if eligible else 0
    assert validate_land_use_availability(payload)


@pytest.mark.parametrize('raw_potential,eligible',[(.5199998,False),(.52,True),(.5200002,True)])
def test_mining_candidates_keep_their_own_raw_threshold(raw_potential,eligible):
    deposit={'id':0,'cell_id':0,'reserve_potential_index':1.,'economic_viability_index':.5,
             'geologic_confidence_index':.5,'accessibility_index':.25+(raw_potential-.52)/.12,'extraction_hazard_index':0.}
    payload=build(world(cell(resource='placer_metals',temperature_c=80.),resource_deposits=[deposit]))
    c=payload['cells'][0]
    assert not c['agricultural_potential_supported'] and c['mining_surface_applicable']
    assert c['mining_potential_index']==.52
    assert bool(payload['mining_zones']) is eligible
    c['mining_zone_id']=-1 if eligible else 0
    assert validate_land_use_availability(payload)


def test_components_and_all_existing_links_rebuild_around_unavailable_candidates():
    zero=cell(id=3,area_km2=8.,resource='evaporites',fertility=0.,soil_depth_m=0.,soil_moisture_index=0.,
        growing_season_months=0.,runoff_mm_y=0.,groundwater_recharge_mm_y=0.,landform='plain',biome='steppe',
        soil_salinity_index=1.,ice_thickness_m=400.,seasonal_aridity_index=1.)
    payload=world(cell(id=2,area_km2=4.,neighbors=[1]),cell(id=0,neighbors=[1],resource='fertile_alluvium'),
        cell(id=1,area_km2=2.,neighbors=[0,2],temperature_c=80.),zero,
        resource_deposits=[{'id':11,'cell_id':0,'resource':'fertile_alluvium'},
            {'id':31,'cell_id':3,'resource':'evaporites','reserve_potential_index':1.,'economic_viability_index':1.,
             'geologic_confidence_index':1.,'accessibility_index':1.,'extraction_hazard_index':0.}],
        settlements=[{'id':7,'cell_id':0},{'id':4,'cell_id':2}],routes=[{'id':9,'from':7,'to':4}])
    deposits=deepcopy(payload['resource_deposits'])
    build(payload)
    zones=payload['agricultural_zones']
    assert [r['id'] for r in zones]==[0,1]
    assert [r['cell_ids'] for r in zones]==[[0],[2]]
    assert [r['settlement_ids'] for r in zones]==[[7],[4]]
    assert [r['route_ids'] for r in zones]==[[9],[9]]
    assert [r['resource_deposit_ids'] for r in zones]==[[11],[]]
    assert payload['mining_zones'][0]['resource_deposit_ids']==[31]
    assert payload['summary']['agricultural_potential_supported_cell_count']==3
    assert payload['summary']['agricultural_potential_supported_area_km2']==13.
    assert payload['summary']['mean_agricultural_potential_index']==.5
    assert payload['summary']['mining_surface_applicable_cell_count']==4
    assert payload['resource_deposits']==deposits
    for key in ('route_ids','settlement_ids','resource_deposit_ids'):
        previous=zones[0][key];zones[0][key]=[]
        assert validate_land_use_availability(payload),key
        zones[0][key]=previous
        assert validate_land_use_availability(payload)==[]
    payload['cells'][2]['temperature_c']=17.
    assert validate_land_use_availability(payload)
    build(payload)
    assert payload['agricultural_zones'][0]['cell_ids']==[0,1,2]
    assert payload['agricultural_zones'][0]['settlement_ids']==[4,7]
    assert payload['agricultural_zones'][0]['route_ids']==[9]


def test_independent_eligibility_is_not_the_producers_support_helper(monkeypatch):
    import magic_geo.land_use_zones as producer
    payload=world(cell(temperature_c=80.));before=deepcopy(payload)
    monkeypatch.setattr(producer,'_agricultural_availability',lambda cell:(True,True,True,True))
    with pytest.raises(ValueError):enrich_world_with_land_use_zones(payload)
    assert payload==before


def test_independent_numerical_replay_rejects_a_changed_producer_equation(monkeypatch):
    import magic_geo.land_use_zones as producer
    payload=world(cell());before=deepcopy(payload)
    monkeypatch.setattr(producer,'_agricultural_potential',lambda cell:.6)
    with pytest.raises(ValueError):enrich_world_with_land_use_zones(payload)
    assert payload==before


def test_finite_source_area_overflow_rejects_before_publication():
    payload=world(cell(area_km2=1e308,neighbors=[1]),cell(id=1,area_km2=1e308,neighbors=[0]))
    before=deepcopy(payload)
    with pytest.raises(ValueError):enrich_world_with_land_use_zones(payload)
    assert payload==before


@pytest.mark.parametrize('family',['cells','resource_deposits','settlements','routes'])
@pytest.mark.parametrize('value',[None,[],1,'record'])
def test_legacy_malformed_record_items_return_diagnostics(family,value):
    payload=deepcopy(OLD['output']);payload[family]=[value]
    assert validate_land_use_availability(payload)
