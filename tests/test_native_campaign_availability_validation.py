"""Independent public campaign acceptance plus scoped retained equation controls."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import ast

import pytest
from support.native_campaign_worlds import campaign_public_world,campaign_source_world
from magic_geo.campaign_availability_validation import validate_campaign_availability,expected_campaign_publication,COLLECTIONS
from magic_geo.campaign_availability import campaign_records
from magic_geo.logistics_availability import networks_and_exchanges,enrich_available_logistics
from magic_geo.logistics_availability_validation import _matches


def identity(world):return json.dumps(world,sort_keys=True,allow_nan=False)

@pytest.fixture(scope='module',params=['healthy','mixed'])
def public(request):return campaign_public_world(request.param)


def test_public_source_complete_or_unavailable_replays_without_mutation(public):
    before=identity(public)
    assert validate_campaign_availability(public)==[]
    assert identity(public)==before
    repeat=deepcopy(public)
    assert enrich_available_logistics(repeat) is repeat
    assert identity(repeat)==before
    movement=public['campaign_operations_availability']['movement']
    if not movement['inference_available']:
        assert public['summary']['campaign_movement_count'] is None
        assert public['summary']['recorded_campaign_movement_count']==0

COMMON_MUTATIONS=[
    lambda w:w['campaign_operations_model'].update(deterministic=1),
    lambda w:w['campaign_operations_model'].update(source_logistics_exchange_model='old'),
    lambda w:w['campaign_operations_model'].update(extra=True),
    lambda w:w['summary'].update(campaign_operations_model='old'),
    lambda w:w['campaign_operations_availability']['movement'].update(inference_available=1),
    lambda w:w['campaign_operations_availability']['movement'].update(applicable_source_count=True),
    lambda w:w['campaign_operations_availability']['front'].update(available_source_count=999),
    lambda w:w['campaign_operations_availability']['tactical'].update(recorded_count=999),
    lambda w:w['campaign_operations_availability']['strategic'].update(unavailable_conflict_ids=[999]),
    lambda w:w['campaign_operations_availability'].update(extra={}),
    lambda w:w['campaign_operations_availability'].pop('front'),
    lambda w:w['summary'].update(campaign_movement_count=999),
    lambda w:w['summary'].update(recorded_campaign_movement_count=999),
    lambda w:w['summary'].update(total_campaign_mobilized_population=999.),
    lambda w:w['summary'].update(mean_campaign_travel_time_days=999.),
    lambda w:w['summary']['campaign_summary_availability'].update(campaign_movement_count=1),
    lambda w:w['summary']['campaign_summary_availability'].update(extra=False),
    lambda w:w['logistics_networks'][0].update(transport_efficiency_index=.777),
    lambda w:w['logistics_networks'][0]['estimate_availability'].update(army_capacity_population=1),
    lambda w:w['economy_histories'][0].update(peak_treasury_index=999.),
    lambda w:w['cells'][0].update(seasonal_aridity_index=True),
]
@pytest.mark.parametrize('mutate',COMMON_MUTATIONS)
def test_public_family_summary_source_and_nullable_types_reject(public,mutate):
    changed=deepcopy(public);mutate(changed)
    assert identity(changed)!=identity(public)
    before=identity(changed)
    assert validate_campaign_availability(changed)
    with pytest.raises(ValueError):enrich_available_logistics(changed)
    assert identity(changed)==before

@pytest.fixture(scope='module')
def healthy():return campaign_public_world('healthy')

RECORD_MUTATIONS=[
    lambda w:w['campaign_movements'][0].update(force_estimate=True),
    lambda w:w['campaign_movements'][0].update(path_length_km=999.),
    lambda w:w['campaign_movements'][0].update(operational_reach_index=None),
    lambda w:w['campaign_movements'][0].update(campaign_front_history_id=True),
    lambda w:w['campaign_movements'][0].update(campaign_front_history_available=1),
    lambda w:w['campaign_movements'][0]['estimate_availability'].update(path_length_km=1),
    lambda w:w['campaign_movements'][0]['path_cell_ids'].reverse(),
    lambda w:w['campaign_path_segments'][0].update(water_crossing=1),
    lambda w:w['campaign_path_segments'][0].update(supply_loss_index=None),
    lambda w:w['campaign_path_segments'][0]['estimate_availability'].update(supply_loss_index=False),
    lambda w:w['campaign_front_histories'][0].update(operations_estimate_available=1),
    lambda w:w['campaign_front_histories'][0]['steps'][0].update(occupation_control_index=.999),
    lambda w:w['campaign_front_histories'][0]['steps'][0].update(occupied_cell_count=True),
    lambda w:w['tactical_engagements'][0].update(operations_estimate_available=1),
    lambda w:w['tactical_engagements'][0]['steps'][0].update(front_pressure_index=.999),
    lambda w:w['strategic_campaign_plans'][0].update(operations_estimate_available=1),
    lambda w:w['strategic_campaign_plans'][0].update(plan_confidence_index=.999),
    lambda w:w['conflicts'][0].update(campaign_movement_id=True),
    lambda w:w['conflicts'][0].update(tactical_engagement_id=None),
    lambda w:w['conflicts'][0]['campaign_link_availability'].update(strategic_campaign_plan_id=1),
]
@pytest.mark.parametrize('mutate',RECORD_MUTATIONS)
def test_nonempty_actual_campaign_record_and_link_tampers(healthy,mutate):
    assert validate_campaign_availability(healthy)==[]
    changed=deepcopy(healthy);mutate(changed)
    assert identity(changed)!=identity(healthy)
    before=identity(changed)
    assert validate_campaign_availability(changed)
    assert identity(changed)==before

@pytest.fixture(scope='module')
def retained():
    root=Path(__file__).parent/'fixtures/legacy_human_water'
    entry=json.loads((root/'manifest.json').read_text())['small_smoke']
    raw=(root/entry['fixture']).read_bytes();assert hashlib.sha256(raw).hexdigest()==entry['fixture_gzip_sha256']
    data=gzip.decompress(raw);assert hashlib.sha256(data).hexdigest()==entry['world_sha256']
    return json.loads(data)


def scoped_inputs(retained):
    world=deepcopy(retained)
    # A declared stage projection only; not consumed by public source validators.
    world['native_social_availability']={'conflict_inference_available':True}
    for record in world['economy_histories']:
        for row in [record,*record['steps']]:
            row['estimate_availability']={key:True for key,value in row.items() if type(value) in (int,float)}
    return world


def replay_scoped(world,networks):
    before=identity(world);before_networks=identity(networks)
    actual=campaign_records(world,networks)
    expected=expected_campaign_publication(world,networks)
    assert identity(world)==before and identity(networks)==before_networks
    for key,records in zip(COLLECTIONS,expected[:5]):assert _matches(actual[key],records)
    for conflict in actual['conflicts']:assert _matches(conflict,expected[5][conflict['id']],exact_keys=False)
    assert _matches(actual['summary'],expected[6])
    assert actual['campaign_operations_availability']==expected[7]
    return actual

@pytest.mark.parametrize('side,field',[(None,None),('origin_region_id','army_capacity_population'),('origin_region_id','logistics_resilience_index'),('target_region_id','logistics_resilience_index')])
def test_scoped_nonempty_nullable_operations_have_exact_coverage_and_links(retained,side,field):
    world=scoped_inputs(retained)
    networks={r['region_id']:r for r in networks_and_exchanges(world)['logistics_networks']}
    baseline=replay_scoped(world,networks)
    if side is not None:
        rid=baseline['campaign_movements'][0][side]
        networks[rid][field]=None;networks[rid]['estimate_availability'][field]=False
    result=replay_scoped(world,networks)
    assert len(result['campaign_movements'])==len(baseline['campaign_movements'])
    for old,new in zip(baseline['campaign_movements'],result['campaign_movements']):
        for key in ('path_cell_ids','distance_km','travel_time_days','path_length_km','force_estimate'):assert old[key]==new[key]
    if side=='target_region_id':
        cid=baseline['campaign_movements'][0]['conflict_id']
        assert cid in result['campaign_operations_availability']['strategic']['unavailable_conflict_ids']
        conflict=next(c for c in result['conflicts'] if c['id']==cid)
        assert conflict['strategic_campaign_plan_id'] is None
        assert conflict['campaign_link_availability']['strategic_campaign_plan_id'] is False

@pytest.mark.parametrize('complete',[True,False])
def test_scoped_empty_parent_has_known_zero_only_with_complete_scope(retained,complete):
    world=scoped_inputs(retained);world['conflicts']=[]
    world['native_social_availability']['conflict_inference_available']=complete
    networks={r['region_id']:r for r in networks_and_exchanges(world)['logistics_networks']}
    result=replay_scoped(world,networks)
    assert all(result[key]==[] for key in COLLECTIONS)
    assert result['summary']['campaign_movement_count']==(0 if complete else None)
    assert result['summary']['recorded_campaign_movement_count']==0


def test_public_first_failure_keeps_source_and_unrelated_fields():
    world=campaign_source_world('mixed');world['cells'][0]['seasonal_aridity_index']=None
    before=identity(world)
    with pytest.raises(ValueError):enrich_available_logistics(world)
    assert identity(world)==before


def test_campaign_independent_source_has_no_producer_imports():
    path=Path(__file__).parents[1]/'src/magic_geo/campaign_availability_validation.py'
    imports={n.module for n in ast.walk(ast.parse(path.read_text())) if isinstance(n,ast.ImportFrom)}
    assert not imports & {'campaign_availability','logistics_availability','logistics_history'}
