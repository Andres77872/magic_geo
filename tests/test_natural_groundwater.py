"""Complete retained stage witnesses and independent source/output mutations."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pytest

import magic_geo.aquifer_resources as aquifer
import magic_geo.groundwater_flow as groundwater
from magic_geo.natural_groundwater_validation import (
    validate_natural_aquifer_resources, validate_natural_groundwater_flow,
)

DATA=Path(__file__).parent/'data/natural_groundwater'
MANIFEST=json.loads((DATA/'manifest.json').read_text())


def retained(name='full_world'):
    raw=(DATA/(name+'.json')).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==MANIFEST['fixtures'][name]['projection_sha256']
    w=json.loads(raw)
    assert len(w['cells'])==MANIFEST['fixtures'][name]['cell_count']==128
    return w


def upgrade(w):
    for key in ('aquifer_resource_model','groundwater_flow_model'):
        assert w[key]['model_type'].endswith('_v1')
        del w[key];del w['summary'][key]
    return w


def build(w):
    assert aquifer.enrich_world_with_aquifer_resources(w) is w
    assert validate_natural_aquifer_resources(w)==[]
    assert groundwater.enrich_world_with_groundwater_flow(w) is w
    assert validate_natural_groundwater_flow(w)==[]
    return w


def cell(**overrides):
    return {'id':0,'area_km2':10.0,'neighbors':[],'basin_id':0,'water_body_type':'land',
        'is_water':False,'is_lake':False,'is_river':False,'is_closed_basin':False,
        'lithology':'limestone','landform':'plain','sediment_thickness_m':1.0,
        'soil_drainage_index':.4,'soil_moisture_index':.6,'soil_salinity_index':.1,
        'seasonal_aridity_index':.2,'ice_thickness_m':0.0,'flow_accumulation':1000.0,
        'infiltration_mm_y':300.0,'elevation_m':500.0,'water_depth_m':0.0,
        'wetland_extent_index':0.0,'distance_to_marine_water_km':1000.0,**overrides}


def world(*cells):
    # This is the upstream source-budget mirror, never a producer output.
    valid=[c for c in cells if c['water_body_type'] not in {'ocean','continental_shelf','inland_sea'}
           and type(c['infiltration_mm_y']) in (int,float) and type(c['area_km2']) in (int,float)]
    try:
        source=sum(max(0.,c['infiltration_mm_y'])*c['area_km2']*1e-6 for c in valid)
    except OverflowError:
        source=math.inf
    return {'cells':list(cells),'summary':{'total_infiltration_km3_y':source}}


def strip_social(w):
    copy=deepcopy(w)
    for c in copy['cells']:
        for k in ('settlement_score','settlement_climate_supported','settlement_climate_temperature_c'):
            c.pop(k,None)
    return copy


@pytest.mark.parametrize('name',['full_world','geo_only'])
def test_actual_explicit_v1_outputs_are_exactly_preserved(name):
    w=retained(name);old=deepcopy(w)
    assert validate_natural_aquifer_resources(w)==validate_natural_groundwater_flow(w)==[]
    aquifer.enrich_world_with_aquifer_resources(w);groundwater.enrich_world_with_groundwater_flow(w)
    assert w==old


def test_actual_full_and_geo_natural_upgrade_are_identical_except_unused_social_field():
    full=build(upgrade(retained()));geo=build(upgrade(retained('geo_only')))
    natural_full=strip_social(full);natural_geo=strip_social(geo)
    # Existing deposit access/economic values have separate social inputs.
    # Batch1 preserves them exactly within each world; it does not migrate them.
    natural_full.pop('resource_deposits');natural_geo.pop('resource_deposits')
    assert natural_full==natural_geo
    assert full['aquifer_resource_model']['model_type']=='natural_recharge_causal_aquifer_resources_v2'
    assert full['groundwater_flow_model']['surface_water_selector']=='is_water_or_is_lake_or_fresh_lake_water_body_type'


def test_upgrade_preserves_all_material_recharge_storage_quality_and_source_inputs():
    w=upgrade(retained());before=deepcopy(w)
    cells=w['cells'];refs=list(cells);summary=w['summary'];deposits=w['resource_deposits'];climate=w['climate_model'];energy=w['climate_energy_model']
    build(w)
    assert w['cells'] is cells and all(c is original for c,original in zip(cells,refs))
    assert w['summary'] is summary and w['resource_deposits'] is deposits and deposits==before['resource_deposits']
    assert w['climate_model'] is climate and w['climate_energy_model'] is energy
    preserved=set(MANIFEST['retained_cell_fields'])-{
        'aquifer_extraction_risk_index','aquifer_productivity_index','aquifer_class','aquifer_system_id',
        'groundwater_hydraulic_head_m','groundwater_gradient_index','groundwater_lateral_flow_km3_y',
        'groundwater_lateral_inflow_km3_y','groundwater_available_volume_km3_y','groundwater_internal_lateral_outflow_km3_y',
        'groundwater_discharge_mm_y','groundwater_discharge_km3_y','groundwater_retained_storage_km3_y',
        'groundwater_flow_mass_balance_residual_km3_y','groundwater_flow_to_cell_id','groundwater_flow_regime',
        'groundwater_flow_system_id','spring_discharge_index','baseflow_support_index'}
    for a,b in zip(w['cells'],before['cells']):
        assert {k:a[k] for k in preserved if k in a}=={k:b[k] for k in preserved if k in b}
        assert 'aquifer_extraction_risk_index' not in a
    assert w['groundwater_recharge_model']==before['groundwater_recharge_model']
    assert not {'groundwater_stressed_cell_count','mean_aquifer_extraction_risk_index'}&summary.keys()
    for family in ('aquifer_systems','groundwater_flow_systems'):
        assert all('mean_aquifer_natural_limitation_index' in r and 'mean_aquifer_extraction_risk_index' not in r for r in w[family])
    once=deepcopy(w);build(w);assert w==once


@pytest.mark.parametrize('score',[None,False,0,1,.7,'unknown',[],{},math.inf,math.nan,1<<20000],
                         ids=['null','false','zero','one','fraction','string','list','dict','inf','nan','huge-int'])
def test_natural_outputs_never_read_or_coerce_social_suitability(score):
    w=world(cell(settlement_score=score));expected=build(world(cell()))
    build(w)
    assert strip_social(w)==expected


def test_natural_limitation_uses_raw_terms_not_clipped_or_rounded_legacy_risk():
    c=cell(seasonal_aridity_index=1.0,soil_salinity_index=1.0,ice_thickness_m=1600.,is_closed_basin=True,
           infiltration_mm_y=0.0,settlement_score=1.0)
    w=build(world(c))
    assert c['aquifer_natural_limitation_index']==1.0
    # Legacy risk is clipped to1. Subtracting .18 would fabricate .82.
    assert c['aquifer_natural_limitation_index']!=.82
    assert w['summary']['high_natural_limitation_aquifer_cell_count']==1


@pytest.mark.parametrize('water,is_water,is_lake,standing',[
    ('saline_basin',False,False,False),('saline_basin',False,True,True),
    ('fresh_lake',False,False,True),('fresh_lake',False,True,True),
    ('land',True,False,True),('land',False,False,False),
],ids=['dry-saline','wet-saline','fresh-type','fresh-lake','water-flag','land'])
def test_natural_surface_connection_requires_actual_standing_water(water,is_water,is_lake,standing):
    c=cell(water_body_type=water,is_water=is_water,is_lake=is_lake)
    w=build(world(c))
    assert groundwater._surface_connection_index(c,natural=True)==(.56 if standing else 0.)
    # Hold independently audited aquifer properties fixed: only the surface
    # selector changes diagnostic head; no salt-pan label is enough for water.
    no_surface=deepcopy(c);no_surface['water_body_type']='land';no_surface['is_lake']=no_surface['is_water']=False
    head_without=groundwater._hydraulic_head(no_surface,natural=True)
    expected_delta=37.8 if standing else 0.0
    assert c['groundwater_hydraulic_head_m']-head_without==pytest.approx(expected_delta,abs=1e-6)
    assert validate_natural_groundwater_flow(w)==[]


def test_dry_saline_old_surface_bonus_remains_only_in_explicit_v1():
    dry=cell(water_body_type='saline_basin')
    assert groundwater._surface_connection_index(dry)==.56
    assert groundwater._surface_connection_index(dry,natural=True)==0.


@pytest.mark.parametrize('water',['ocean','continental_shelf','inland_sea'])
def test_marine_domain_is_still_excluded(water):
    c=cell(water_body_type=water,is_water=True,elevation_m=-50.,water_depth_m=50.)
    build(world(c))
    assert c['aquifer_class']=='marine_excluded' and c['groundwater_flow_regime']=='excluded'
    assert c['aquifer_natural_limitation_index']==c['groundwater_discharge_km3_y']==c['groundwater_recharge_mm_y']==0.
    assert c['groundwater_hydraulic_head_m']==0. and c['aquifer_system_id']==-1


@pytest.mark.parametrize('area',[.5,4.0,1000.0])
def test_actual_positive_area_converts_recharge_and_closes_every_partition(area):
    a=cell(id=0,neighbors=[1],area_km2=area,elevation_m=900.)
    b=cell(id=1,neighbors=[0],area_km2=2.,elevation_m=100.)
    w=build(world(a,b))
    assert a['groundwater_recharge_km3_y']==round(a['groundwater_recharge_mm_y']*area*1e-6,6)
    assert a['groundwater_flow_to_cell_id']==1 and b['groundwater_flow_to_cell_id']==-1
    for c in (a,b):
        available=c['groundwater_recharge_km3_y']+c['groundwater_lateral_inflow_km3_y']
        assert c['groundwater_available_volume_km3_y']==pytest.approx(available,abs=2e-6)
        assert available==pytest.approx(c['groundwater_internal_lateral_outflow_km3_y']+c['groundwater_discharge_km3_y']+c['groundwater_retained_storage_km3_y'],abs=3e-6)
    assert a['groundwater_internal_lateral_outflow_km3_y']==b['groundwater_lateral_inflow_km3_y']


def test_receiver_equal_drop_tie_preserves_neighbor_order_and_descending_acyclicity():
    for neighbors,receiver in (([1,2],1),([2,1],2)):
        w=build(world(cell(neighbors=neighbors,elevation_m=900.),cell(id=1,neighbors=[0],elevation_m=100.),cell(id=2,neighbors=[0],elevation_m=100.)))
        assert w['cells'][0]['groundwater_flow_to_cell_id']==receiver
        assert all(c['groundwater_flow_to_cell_id']==-1 for c in w['cells'][1:])


def test_zero_recharge_has_no_fabricated_discharge_or_stored_stock():
    w=build(world(cell(infiltration_mm_y=0.)))
    c=w['cells'][0]
    assert c['groundwater_discharge_km3_y']==c['groundwater_retained_storage_km3_y']==0.
    assert w['groundwater_flow_model']['retained_storage_semantics']=='unadvanced_annual_recharge_partition_remainder_not_stored_water_stock'
    assert w['groundwater_flow_model']['human_withdrawals_modelled'] is False
    assert w['groundwater_flow_model']['transient_storage_modelled'] is False
    assert w['groundwater_flow_model']['darcy_flow_modelled'] is False


@pytest.mark.parametrize('key',['infiltration_mm_y','sediment_thickness_m','soil_moisture_index','soil_drainage_index',
    'soil_salinity_index','seasonal_aridity_index','ice_thickness_m','flow_accumulation','area_km2'])
@pytest.mark.parametrize('value',[None,False,'0',[],math.nan,math.inf,1<<20000],
                         ids=['null','bool','string','list','nan','inf','huge-int'])
def test_unusable_aquifer_source_rejects_atomically(key,value):
    w=world(cell(**{key:value}));before=deepcopy(w);refs=list(w['cells'])
    with pytest.raises(ValueError):aquifer.enrich_world_with_aquifer_resources(w)
    assert w==before and all(a is b for a,b in zip(w['cells'],refs))


@pytest.mark.parametrize('key',['elevation_m','water_depth_m','wetland_extent_index','distance_to_marine_water_km'])
@pytest.mark.parametrize('value',[None,True,'0',math.inf,1<<20000],ids=['null','bool','string','inf','huge-int'])
def test_unusable_flow_source_rejects_atomically_after_valid_aquifer(key,value):
    w=world(cell());aquifer.enrich_world_with_aquifer_resources(w);w['cells'][0][key]=value
    before=deepcopy(w)
    with pytest.raises(ValueError):groundwater.enrich_world_with_groundwater_flow(w)
    assert w==before


@pytest.mark.parametrize('root',[None,False,1,'world',[],[{}]])
def test_malformed_roots_return_one_diagnostic_and_producer_value_error(root):
    for audit,producer in ((validate_natural_aquifer_resources,aquifer.enrich_world_with_aquifer_resources),
                           (validate_natural_groundwater_flow,groundwater.enrich_world_with_groundwater_flow)):
        assert len(audit(root))==1
        with pytest.raises(ValueError):producer(root)


@pytest.mark.parametrize('mutation',[
    lambda w:w['cells'][0].update(neighbors=[999]),lambda w:w['cells'][0].update(neighbors=[0]),
    lambda w:w['cells'][0].update(neighbors=[1,1]),lambda w:w['cells'][1].update(id=0),
    lambda w:w['cells'][0].update(basin_id=999),lambda w:w['cells'][0].update(is_lake=None),
    lambda w:w['cells'][0].update(water_body_type=[]),lambda w:w.update(summary=None),
    lambda w:w['cells'][0].update(area_km2=0.0),lambda w:w['cells'][0].update(area_km2=-1.0),
])
def test_invalid_structural_graph_and_source_area_reject_before_mutation(mutation):
    w=world(cell(neighbors=[1]),cell(id=1,neighbors=[0]));mutation(w);before=deepcopy(w)
    with pytest.raises(ValueError):aquifer.enrich_world_with_aquifer_resources(w)
    assert w==before


@pytest.mark.parametrize('mutation',[
    lambda w:w['aquifer_resource_model'].update(model_type='unknown'),
    lambda w:w['aquifer_resource_model'].update(human_withdrawals_modelled=0),
    lambda w:w['aquifer_resource_model'].update(extra=True),lambda w:w.update(aquifer_resource_model=None),
    lambda w:w['summary'].pop('aquifer_resource_model'),lambda w:w.pop('aquifer_resource_model'),
    lambda w:w['groundwater_flow_model'].update(source_aquifer_model='wrong'),
    lambda w:w['groundwater_flow_model'].update(surface_water_selector='saline_basin'),
    lambda w:w['groundwater_recharge_model'].update(extra=True),
    lambda w:w['summary'].update(groundwater_flow_model='wrong'),
])
def test_partial_unknown_or_malformed_declared_models_reject_atomically(mutation):
    w=build(world(cell()));mutation(w);before=deepcopy(w)
    assert validate_natural_groundwater_flow(w)
    for producer in (aquifer.enrich_world_with_aquifer_resources,groundwater.enrich_world_with_groundwater_flow):
        with pytest.raises(ValueError):producer(w)
        assert w==before


def test_partial_archive_upgrade_cannot_mix_new_aquifer_with_declared_old_flow():
    w=retained();del w['aquifer_resource_model'];del w['summary']['aquifer_resource_model'];before=deepcopy(w)
    with pytest.raises(ValueError,match='versions must match'):aquifer.enrich_world_with_aquifer_resources(w)
    assert w==before


@pytest.mark.parametrize('key',['aquifer_natural_limitation_index','aquifer_productivity_index','aquifer_storage_index',
    'aquifer_quality_index','groundwater_recharge_fraction','groundwater_recharge_mm_y','groundwater_recharge_km3_y'])
def test_independent_aquifer_equation_replay_rejects_forged_values(key):
    w=build(world(cell()));w['cells'][0][key]+=.01
    assert validate_natural_aquifer_resources(w)
    before=deepcopy(w)
    with pytest.raises(ValueError):groundwater.enrich_world_with_groundwater_flow(w)
    assert w==before


@pytest.mark.parametrize('mutation',[
    lambda w:w['cells'][0].update(aquifer_extraction_risk_index=0.),
    lambda w:w['summary'].update(groundwater_stressed_cell_count=0),
    lambda w:w['summary'].update(mean_aquifer_extraction_risk_index=0.),
    lambda w:w['aquifer_systems'][0].update(mean_aquifer_extraction_risk_index=0.),
    lambda w:w['aquifer_systems'][0].update(stressed_cell_count=0),
    lambda w:w['aquifer_systems'][0].update(extra=0),
    lambda w:w['summary'].update(high_natural_limitation_aquifer_cell_count=1),
    lambda w:w['aquifer_systems'][0].update(high_natural_limitation_cell_count=1),
    lambda w:w['aquifer_systems'][0].update(cell_ids=[]),
    lambda w:w['aquifer_resource_model'].update(aquifer_cell_count=True),
])
def test_legacy_aliases_and_forged_aquifer_counts_records_are_not_accepted(mutation):
    w=build(world(cell()));mutation(w)
    assert validate_natural_aquifer_resources(w)


@pytest.mark.parametrize('key',['groundwater_hydraulic_head_m','groundwater_gradient_index','groundwater_lateral_flow_km3_y',
    'groundwater_lateral_inflow_km3_y','groundwater_available_volume_km3_y','groundwater_internal_lateral_outflow_km3_y',
    'groundwater_discharge_mm_y','groundwater_discharge_km3_y','groundwater_retained_storage_km3_y',
    'spring_discharge_index','baseflow_support_index'])
def test_independent_routing_rejects_forged_field_even_with_zero_reported_residual(key):
    w=build(world(cell(neighbors=[1],elevation_m=900.),cell(id=1,neighbors=[0],elevation_m=100.)))
    w['cells'][0][key]+=.01;w['cells'][0]['groundwater_flow_mass_balance_residual_km3_y']=0.
    assert validate_natural_groundwater_flow(w)


@pytest.mark.parametrize('mutation',[
    lambda w:w['cells'][0].update(groundwater_flow_to_cell_id=0),
    lambda w:w['cells'][0].update(groundwater_flow_system_id=-1),
    lambda w:w['groundwater_flow_systems'][0].update(aquifer_system_id=999),
    lambda w:w['groundwater_flow_systems'][0].update(outlet_cell_id=999),
    lambda w:w['groundwater_flow_systems'][0].update(cell_ids=[]),
    lambda w:w['groundwater_flow_systems'][0].update(mean_aquifer_natural_limitation_index=0),
    lambda w:w['groundwater_flow_systems'][0].update(terminal_cell_ids=[]),
    lambda w:w['summary'].update(groundwater_flow_cell_count=0),
    lambda w:w['summary'].update(mean_baseflow_support_index=0),
    lambda w:w['summary'].update(total_groundwater_flow_balance_residual_km3_y=0),
    lambda w:w['groundwater_flow_model'].update(total_retained_storage_volume_km3_y=0),
])
def test_complete_flow_record_counter_and_source_link_replay(mutation):
    w=build(world(cell()));mutation(w)
    assert validate_natural_groundwater_flow(w)


def test_derived_overflow_rejects_instead_of_clamping_an_infinite_head_drop():
    w=world(cell(neighbors=[1],elevation_m=1e308),cell(id=1,neighbors=[0],elevation_m=-1e308))
    aquifer.enrich_world_with_aquifer_resources(w);before=deepcopy(w)
    with pytest.raises(ValueError):groundwater.enrich_world_with_groundwater_flow(w)
    assert w==before


def test_recharge_area_product_overflow_rejects_before_any_publication():
    w=world(cell(area_km2=1e308,infiltration_mm_y=1e308));before=deepcopy(w)
    with pytest.raises(ValueError):aquifer.enrich_world_with_aquifer_resources(w)
    assert w==before


def test_independent_helper_does_not_call_the_producer_head_or_class_function(monkeypatch):
    w=world(cell());before=deepcopy(w)
    monkeypatch.setattr(aquifer,'_aquifer_class',lambda *args:'fabricated')
    with pytest.raises(ValueError):aquifer.enrich_world_with_aquifer_resources(w)
    assert w==before
    monkeypatch.undo();aquifer.enrich_world_with_aquifer_resources(w);before=deepcopy(w)
    original=groundwater._hydraulic_head
    monkeypatch.setattr(groundwater,'_hydraulic_head',lambda c,**kw:original(c,**kw)+1.)
    with pytest.raises(ValueError):groundwater.enrich_world_with_groundwater_flow(w)
    assert w==before


def test_empty_explicit_natural_stages_publish_valid_zero_coverage():
    w=build(world())
    assert w['aquifer_systems']==w['groundwater_flow_systems']==[]
    assert w['summary']['aquifer_cell_count']==w['summary']['groundwater_flow_cell_count']==0


@pytest.mark.parametrize('later_summary',[None,'stale',0.0,1e100,math.nan],ids=['null','text','zero','large','nan'])
def test_later_hydrology_summary_does_not_become_a_new_source_dependency(later_summary):
    expected=build(world(cell()))
    w=world(cell());w['summary']['total_infiltration_km3_y']=later_summary
    build(w)
    assert w['summary']['total_infiltration_km3_y'] is later_summary
    del w['summary']['total_infiltration_km3_y'];del expected['summary']['total_infiltration_km3_y']
    assert w==expected
    missing=world(cell());del missing['summary']['total_infiltration_km3_y'];build(missing)
    assert missing==expected


@pytest.mark.parametrize('raw,high',[(.6499998,False),(.65,True),(.6500002,True)])
def test_natural_limitation_counts_keep_declared_raw_summary_and_rounded_system_rules(raw,high):
    c=cell(infiltration_mm_y=0.,sediment_thickness_m=3.,seasonal_aridity_index=(raw-.358)/.30)
    w=build(world(c))
    assert c['aquifer_natural_limitation_index']==.65
    assert w['summary']['high_natural_limitation_aquifer_cell_count']==int(high)
    assert w['aquifer_systems'][0]['high_natural_limitation_cell_count']==1
    w['summary']['high_natural_limitation_aquifer_cell_count']=int(not high)
    assert validate_natural_aquifer_resources(w)


@pytest.mark.parametrize('raw,eligible',[(.1799998,False),(.18,True),(.1800002,True)])
def test_aquifer_system_eligibility_keeps_raw_productivity_threshold(raw,eligible):
    # Independent closed-form source selection at zero recharge. This does not
    # consume the producer's productivity or eligibility function.
    storage=.08+.30*.34-.2*.10
    quality=.80-.1*.50-.2*.08
    natural=.14+.2*.30+.20+.1*.18
    base=storage*.38+quality*.18-natural*.16
    flow=(raw-base)/.08*40_000_000.
    c=cell(lithology='granite',sediment_thickness_m=0.,soil_moisture_index=0.,infiltration_mm_y=0.,flow_accumulation=flow)
    w=build(world(c))
    assert c['aquifer_productivity_index']==.18
    assert bool(w['aquifer_systems']) is eligible
    assert c['aquifer_system_id']==(0 if eligible else -1)
    c['aquifer_system_id']=-1 if eligible else 0
    assert validate_natural_aquifer_resources(w)


@pytest.mark.parametrize('raw,major',[(.6599998,False),(.66,True),(.6600002,True)])
def test_fresh_aquifer_classification_keeps_raw_major_threshold(raw,major):
    storage=.08+.82*.34+.5*.26+.4*.12
    intercept=storage*.38+.85*.18-.14*.16
    recharge=(raw-intercept)/(.34/320.+.16*.18/360.)
    fraction=.08+.82*.45+.4*.18+.5*.12
    c=cell(sediment_thickness_m=1.5,soil_moisture_index=.4,seasonal_aridity_index=0.,soil_salinity_index=0.,
           infiltration_mm_y=recharge/fraction,flow_accumulation=0.)
    w=build(world(c))
    assert c['aquifer_productivity_index']==.66
    assert (c['aquifer_class']=='major_fresh_aquifer') is major
    c['aquifer_class']='local_fresh_aquifer' if major else 'major_fresh_aquifer'
    assert validate_natural_aquifer_resources(w)


@pytest.mark.parametrize('container,key',[
    ('groundwater_recharge_model','total_source_infiltration_volume_km3_y'),
    ('groundwater_recharge_model','total_groundwater_recharge_volume_km3_y'),
    ('groundwater_recharge_model','total_vadose_zone_retention_volume_km3_y'),
    ('summary','total_groundwater_recharge_source_infiltration_km3_y'),
    ('summary','total_vadose_zone_retention_km3_y'),
])
def test_actual_native_source_totals_do_not_inherit_legacy_relative_tolerance(container,key):
    w=build(upgrade(retained()));w[container][key]+=1.0
    assert validate_natural_aquifer_resources(w)


@pytest.mark.parametrize('key',['groundwater_recharge_fraction','vadose_zone_retention_mm_y','groundwater_recharge_source_infiltration_mm_y'])
def test_representable_single_display_quantum_aquifer_tamper_is_rejected(key):
    w=build(world(cell()));w['cells'][0][key]+=1e-6
    assert validate_natural_aquifer_resources(w)


@pytest.mark.parametrize('key',['groundwater_gradient_index','groundwater_lateral_flow_km3_y','groundwater_discharge_km3_y'])
def test_representable_single_display_quantum_flow_tamper_is_rejected(key):
    w=build(world(cell()));w['cells'][0][key]+=1e-6
    assert validate_natural_groundwater_flow(w)


@pytest.mark.parametrize('mutation',[
    lambda w:w['cells'][0].update(aquifer_natural_limitation_index=0.),
    lambda w:w['summary'].update(mean_aquifer_natural_limitation_index=0.),
    lambda w:w['summary'].update(high_natural_limitation_aquifer_cell_count=0),
    lambda w:w['aquifer_systems'][0].update(high_natural_limitation_cell_count=0),
    lambda w:w['groundwater_flow_systems'][0].update(mean_aquifer_natural_limitation_index=0.),
])
def test_new_natural_mirrors_cannot_be_smuggled_under_a_legacy_declaration(mutation):
    w=retained();mutation(w);before=deepcopy(w)
    assert validate_natural_aquifer_resources(w) and validate_natural_groundwater_flow(w)
    for producer in (aquifer.enrich_world_with_aquifer_resources,groundwater.enrich_world_with_groundwater_flow):
        with pytest.raises(ValueError,match='natural v2 mirrors'):producer(w)
        assert w==before
