"""Availability successor controls: isolated Python stages, no native generation."""
from copy import deepcopy
from unittest.mock import patch
import pytest

from magic_geo import resource_dynamics as producer
from magic_geo.commodity_resources import enrich_world_with_commodity_occurrences
from magic_geo.biological_resource_validation import (
    biological_resource_parent_support, validate_biological_resources,
)
from magic_geo.resource_access_validation import RECORD_FIELDS, ACCESS_SUMMARY_FIELDS
from magic_geo.land_use_zones import enrich_world_with_land_use_zones
from magic_geo.land_use_availability_validation import validate_land_use_availability
from magic_geo.ore_genesis import enrich_world_with_ore_genesis, _build_ore_genesis
from magic_geo.ore_resource_availability_validation import (
    validate_ore_resource_availability, CELL_FIELDS, SUMMARY_FIELDS, TOP_FIELDS,
)
from magic_geo.worldbuilding_realism import enrich_world_with_worldbuilding_realism
from magic_geo.worldbuilding_fishery_validation import validate_worldbuilding_fishery_context
from support.settlement_economic_worlds import stage_world, deposits, commodities
from support.prescribed_resource_worlds import fresh_resource_inputs, retained_resource_world


@pytest.mark.parametrize('name',['earthlike_seed','verdant_hothouse','young_volcanic'])
def test_retained_selection_sources_material_equations_and_availability(name):
    world=stage_world(name); source=deepcopy(world); native=world['climate_energy_balance_records']
    old=deepcopy(world)
    producer._build_resource_deposits(old,fishery_support=biological_resource_parent_support(world))
    producer.enrich_world_with_resource_deposits(world)
    assert validate_biological_resources(world,include_commodities=False)==[]
    assert len(old['resource_deposits'])==len(world['resource_deposits'])
    for before,after in zip(old['resource_deposits'],world['resource_deposits']):
        for key,value in before.items():
            if key not in ('accessibility_index','economic_viability_index'):assert after[key]==value
        if after['accessibility_supported']:
            assert before['accessibility_index']==after['accessibility_index']
            assert before['economic_viability_index']==after['economic_viability_index']
        else:
            assert after['accessibility_index'] is None and after['economic_viability_index'] is None
            assert after['geographic_accessibility_baseline_index']==before['accessibility_index']
            assert after['geographic_economic_viability_baseline_index']==before['economic_viability_index']
    assert world['climate_energy_balance_records'] is native
    assert all(all(c[k]==v for k,v in prior.items()) for c,prior in zip(world['cells'],source['cells']))
    enrich_world_with_commodity_occurrences(world)
    assert validate_biological_resources(world)==[]
    for record in world['commodity_occurrences']:
        deposit=world['resource_deposits'][record['resource_deposit_id']]
        for key in ('accessibility_index','accessibility_supported','geographic_accessibility_baseline_index'):assert record[key]==deposit[key]
    before=deepcopy(world)
    producer.enrich_world_with_resource_deposits(world);enrich_world_with_commodity_occurrences(world)
    assert world==before


def test_actual_complete_geo_has_separate_geographic_baselines_and_same_materials():
    old=retained_resource_world('geo'); world=fresh_resource_inputs('geo')
    producer.enrich_world_with_resource_deposits(world);enrich_world_with_commodity_occurrences(world)
    assert validate_biological_resources(world)==[]
    assert (len(world['resource_deposits']),len(world['commodity_occurrences']))==(119,196)
    for before,after in zip(old['resource_deposits'],world['resource_deposits']):
        assert after['accessibility_index'] is None and after['economic_viability_index'] is None
        assert after['accessibility_supported'] is False and after['economic_viability_supported'] is False
        assert after['geographic_accessibility_baseline_index']==before['accessibility_index']
        assert after['geographic_economic_viability_baseline_index']==before['economic_viability_index']
        assert {k:v for k,v in after.items() if k not in (*RECORD_FIELDS,'accessibility_index','economic_viability_index')}=={k:v for k,v in before.items() if k not in ('accessibility_index','economic_viability_index')}
    for c in world['cells']:
        assert 'settlement_score' not in c and 'settlement_climate_supported' not in c
    for c in world['cells']:
        for key in CELL_FIELDS:c.pop(key,None)
    for key in SUMMARY_FIELDS:world['summary'].pop(key,None)
    for key in TOP_FIELDS:world.pop(key,None)
    enrich_world_with_ore_genesis(world)
    assert validate_ore_resource_availability(world)==[]
    assert all(r['mean_resource_viability_index'] is None for r in world['ore_genesis_systems'] if r['resource_deposit_ids'])


@pytest.mark.parametrize('name',['earthlike_seed','verdant_hothouse','young_volcanic'])
def test_mining_and_ore_complete_or_unavailable_without_changing_agriculture(name):
    world=deposits(name)
    old=deepcopy(world)
    for d in old['resource_deposits']:
        if not d['economic_viability_supported']:d['economic_viability_index']=d['geographic_economic_viability_baseline_index']
    _build_ore_genesis(old)
    enrich_world_with_ore_genesis(world)
    assert validate_ore_resource_availability(world)==[]
    extras={'mean_resource_viability_index','mean_resource_viability_supported','resource_viability_applicable_deposit_count','resource_viability_supported_deposit_count','mean_geographic_resource_viability_baseline_index'}
    for a,b in zip(old['ore_genesis_systems'],world['ore_genesis_systems']):
        assert {k:v for k,v in a.items() if k not in extras}=={k:v for k,v in b.items() if k not in extras}
    enrich_world_with_land_use_zones(world)
    assert validate_land_use_availability(world)==[]
    complete=world['summary']['mining_zone_selection_complete']
    assert complete is (name=='earthlike_seed')
    if not complete:
        assert world['mining_zones']==[] and world['summary']['mean_mining_potential_index'] is None
        assert any(c['mining_potential_index'] is None for c in world['cells'])
        assert all(c['mining_zone_id'] is None for c in world['cells'] if not c['mining_zone_membership_supported'])
    for c in world['cells']:
        if not c['mining_surface_applicable'] or c['resource'] not in {'volcanic_arc_metals','craton_iron_gold','placer_metals','sedimentary_fuels','evaporites','geothermal'}:
            assert c['mining_potential_index']==0.0 and c['mining_potential_supported'] is True
    before=deepcopy(world);enrich_world_with_land_use_zones(world);assert world==before


@pytest.mark.parametrize('key',list(RECORD_FIELDS)+['accessibility_index','economic_viability_index','reserve_potential_index','geologic_confidence_index','extraction_hazard_index','renewability_index'])
def test_independent_deposit_output_tamper(key):
    world=deposits('verdant_hothouse');record=world['resource_deposits'][0]
    record[key]=not record[key] if type(record[key]) is bool else .123456
    assert validate_biological_resources(world,include_commodities=False)


@pytest.mark.parametrize('key',ACCESS_SUMMARY_FIELDS)
def test_independent_summary_tamper(key):
    world=deposits('verdant_hothouse');world['summary'][key]=None
    assert validate_biological_resources(world,include_commodities=False)


@pytest.mark.parametrize('published',[False,True])
@pytest.mark.parametrize('mutation',[
    lambda w:w['cells'][0].pop('settlement_climate_supported'),
    lambda w:w['settlement_selection_model'].update(extra=True),
    lambda w:w['cells'][0].pop('resource'),
    lambda w:w['cells'][0].pop('boundary_transform'),
    lambda w:w.update(generation_scope='geo_only'),
])
def test_atomic_parent_refusal_first_and_repeated(published,mutation):
    world=deposits() if published else stage_world();mutation(world);before=deepcopy(world)
    with pytest.raises(ValueError):producer.enrich_world_with_resource_deposits(world)
    assert world==before


def test_tampered_producer_equation_rejected_before_publication():
    world=stage_world();before=deepcopy(world)
    with patch.object(producer,'_accessibility',return_value=.987654):
        with pytest.raises(ValueError):producer.enrich_world_with_resource_deposits(world)
    assert world==before


@pytest.mark.parametrize('family',['resource','commodity','ore','mining','worldbuilding'])
def test_missing_own_with_mirrors_and_old_child_no_auto_upgrade(family):
    world=commodities(); target={'resource':producer.enrich_world_with_resource_deposits,'commodity':enrich_world_with_commodity_occurrences,'ore':enrich_world_with_ore_genesis,'mining':enrich_world_with_land_use_zones,'worldbuilding':enrich_world_with_worldbuilding_realism}[family]
    key={'resource':'resource_deposit_model','commodity':'commodity_occurrence_model','ore':'ore_genesis_model','mining':'land_use_zone_model','worldbuilding':'worldbuilding_realism_model'}[family]
    if family not in ('resource','commodity'):target(world)
    del world[key];before=deepcopy(world)
    with pytest.raises(ValueError):target(world)
    assert world==before


def test_worldbuilding_new_parent_keeps_five_checks_and_rejects_tamper():
    world=commodities();enrich_world_with_worldbuilding_realism(world)
    assert world['worldbuilding_realism_model']['model_type'].endswith('_v4')
    assert len(world['worldbuilding_realism_checks'])==5
    assert validate_worldbuilding_fishery_context(world)==[]
    world['worldbuilding_realism_checks'][-1]['value']=.123
    assert validate_worldbuilding_fishery_context(world)


@pytest.mark.parametrize('mutation',[
    lambda w:w['summary'].update(mining_zone_selection_complete=True),
    lambda w:w['summary'].update(mining_input_supported_cell_count=0),
    lambda w:w['summary'].update(mean_mining_potential_index=0.0),
    lambda w:next(c for c in w['cells'] if c['mining_potential_index'] is None).update(mining_potential_index=0.0),
    lambda w:next(c for c in w['cells'] if not c['mining_zone_membership_supported']).update(mining_zone_id=-1),
    lambda w:w['cells'][0].update(mining_potential_supported=1),
    lambda w:w['cells'][0].update(agricultural_potential_index=.99999),
    lambda w:w['cells'][0].pop('neighbors'),
])
def test_mining_independent_unknown_graph_and_unchanged_agricultural_tamper(mutation):
    world=deposits('verdant_hothouse');enrich_world_with_land_use_zones(world);mutation(world)
    assert validate_land_use_availability(world)


@pytest.mark.parametrize('field',['mean_resource_viability_index','mean_geographic_resource_viability_baseline_index','mean_resource_viability_supported','resource_viability_applicable_deposit_count','resource_viability_supported_deposit_count','resource_deposit_ids'])
def test_ore_attachment_tamper(field):
    world=deposits('young_volcanic');enrich_world_with_ore_genesis(world)
    world['ore_genesis_systems'][0][field]=.123456 if world['ore_genesis_systems'][0][field] is None else None
    assert validate_ore_resource_availability(world)


@pytest.mark.parametrize('field',['accessibility_index','accessibility_supported','geographic_accessibility_baseline_index'])
def test_every_commodity_copied_access_field_is_independently_bound(field):
    world=commodities('verdant_hothouse');world['commodity_occurrences'][0][field]=.123456
    assert validate_biological_resources(world)


def test_empty_geo_resource_and_ore_outputs_have_explicit_conditional_zero_counts():
    from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
    world={'generation_scope':'geo_only','cells':[],'summary':{},'sedimentary_resource_systems':[]}
    enrich_world_with_ecosystem_dynamics(world)
    producer.enrich_world_with_resource_deposits(world);enrich_world_with_commodity_occurrences(world);enrich_world_with_ore_genesis(world)
    assert validate_biological_resources(world)==[] and validate_ore_resource_availability(world)==[]
    assert world['resource_deposits']==world['commodity_occurrences']==world['ore_genesis_systems']==[]
    assert world['summary']['resource_economic_viability_supported_deposit_count']==0
    assert world['summary']['mean_resource_economic_viability_index']==0.0


@pytest.mark.parametrize('family',['resource','commodity','ore','mining','worldbuilding'])
def test_exact_old_own_models_reject_new_parents_without_retagging(family):
    from magic_geo.biological_resource_validation import _DEPOSIT_V4, _COMMODITY_V2
    from magic_geo.ore_resource_availability_validation import BASE
    from magic_geo.land_use_availability_validation import _land_use_model, _POLICY
    from magic_geo.worldbuilding_fishery_validation import _V3
    world=commodities()
    target={'resource':producer.enrich_world_with_resource_deposits,'commodity':enrich_world_with_commodity_occurrences,'ore':enrich_world_with_ore_genesis,'mining':enrich_world_with_land_use_zones,'worldbuilding':enrich_world_with_worldbuilding_realism}[family]
    key={'resource':'resource_deposit_model','commodity':'commodity_occurrence_model','ore':'ore_genesis_model','mining':'land_use_zone_model','worldbuilding':'worldbuilding_realism_model'}[family]
    if family not in ('resource','commodity'):target(world)
    old={'resource':_DEPOSIT_V4,'commodity':_COMMODITY_V2,'ore':BASE,'mining':{**_land_use_model(),**_POLICY},'worldbuilding':_V3}[family]
    old=deepcopy(old)
    if 'flow_accumulation_scale' in world[key]:old['flow_accumulation_scale']=world[key]['flow_accumulation_scale']
    world[key]=old
    if family in ('mining','worldbuilding'):world['summary'][key]=old['model_type']
    before=deepcopy(world)
    with pytest.raises(ValueError):target(world)
    assert world==before


@pytest.mark.parametrize('family',['resource','commodity','ore'])
def test_new_economic_mirrors_cannot_hide_under_exact_historical_models(family):
    world=retained_resource_world('geo')
    if family=='resource':world['resource_deposits'][0]['accessibility_supported']=False
    elif family=='commodity':world['commodity_occurrences'][0]['accessibility_supported']=False
    else:world['ore_genesis_systems'][0]['mean_resource_viability_supported']=False
    before=deepcopy(world)
    fn={'resource':producer.enrich_world_with_resource_deposits,'commodity':enrich_world_with_commodity_occurrences,'ore':enrich_world_with_ore_genesis}[family]
    with pytest.raises(ValueError):fn(world)
    assert world==before
