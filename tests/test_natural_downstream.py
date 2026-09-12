from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

import pytest

from magic_geo.aquifer_resources import enrich_world_with_aquifer_resources as aquifer
from magic_geo.groundwater_flow import enrich_world_with_groundwater_flow as groundwater
import magic_geo.river_channel_morphology as channel_module
import magic_geo.river_hydraulics as hydraulic_module
import magic_geo.karst_diagnostics as karst_module
from magic_geo.natural_channel_validation import (
    natural_downstream_model_version, validate_natural_channel_morphology,
    validate_natural_river_hydraulics,
)
from magic_geo.natural_karst_validation import validate_natural_karst_diagnostics


DATA=Path(__file__).with_name('data')/'natural_downstream'
PRODUCERS={'channel':channel_module.enrich_world_with_river_channel_morphology,
           'hydraulics':hydraulic_module.enrich_world_with_river_hydraulics,
           'karst':karst_module.enrich_world_with_karst_diagnostics}
AUDITS={'channel':validate_natural_channel_morphology,'hydraulics':validate_natural_river_hydraulics,
        'karst':validate_natural_karst_diagnostics}
KEYS={'channel':'river_channel_morphology_model','hydraulics':'river_hydraulics_model','karst':'karst_diagnostics_model'}
OWNED={
 'channel':('bankfull_discharge_m3_s','channel_morphology_class','channel_slope_index','floodplain_connectivity_index','river_channel_depth_m','river_channel_system_id','river_channel_width_m','stream_power_index'),
 'hydraulics':('bed_shear_stress_pa','channel_capacity_index','flow_velocity_m_s','froude_number','hydraulic_flow_regime','hydraulic_navigability_index','hydraulic_radius_m','manning_roughness_n','river_hydraulic_reach_id'),
 'karst':('cave_development_index','karst_potential_index','karst_system_id','subterranean_drainage_fraction')}
FAMILIES={'channel':'river_channel_systems','hydraulics':'river_hydraulic_reaches','karst':'karst_systems'}


def encoded(world):
    return json.dumps(world,sort_keys=True)


@lru_cache
def _historical(name):
    raw=(DATA/(name+'.json')).read_bytes()
    manifest=json.loads((DATA/'manifest.json').read_text())
    assert hashlib.sha256(raw).hexdigest()==manifest['fixtures'][name]['projection_sha256']
    return json.loads(raw)


def historical(name='full_world'):
    return deepcopy(_historical(name))


def upgrade(world):
    for key in ('aquifer_resource_model','groundwater_flow_model','river_channel_morphology_model','river_hydraulics_model','karst_diagnostics_model'):
        world.pop(key,None);world['summary'].pop(key,None)
    return rebuild(world)


def rebuild(world):
    aquifer(world);groundwater(world)
    for producer in PRODUCERS.values():producer(world)
    return world


@lru_cache
def _current(name):
    return upgrade(historical(name))


def current(name='full_world'):
    return deepcopy(_current(name))


@pytest.mark.parametrize('name',['full_world','geo_only','continental_realm','glasswind_desert'])
def test_actual_old_exact_and_new_audited_idempotent(name):
    world=historical(name);before=encoded(world)
    for audit in AUDITS.values():assert audit(world)==[]
    for producer in PRODUCERS.values():producer(world)
    assert encoded(world)==before
    assert 'karst_diagnostics_model' not in world and 'karst_diagnostics_model' not in world['summary']
    world=current(name)
    for stage,audit in AUDITS.items():
        assert natural_downstream_model_version(world,stage)==2
        assert audit(world)==[]
    before=encoded(world);rebuild(world);assert encoded(world)==before


def test_actual_component_branches_are_nonvacuous():
    continent=current('continental_realm');dry=current('glasswind_desert');normal=current()
    assert len(continent['river_channel_systems'])==6
    assert len(continent['river_hydraulic_reaches'])==6
    assert len(continent['karst_systems'])==8
    assert dry['river_channel_systems']==dry['river_hydraulic_reaches']==[]
    assert len(dry['karst_systems'])==3
    assert normal['karst_systems']==[]


def test_natural_full_geo_downstream_fields_and_records_match_exactly():
    full=current('full_world');geo=current('geo_only')
    for stage,fields in OWNED.items():
        assert [{k:c[k] for k in fields} for c in full['cells']]==[{k:c[k] for k in fields} for c in geo['cells']]
        assert full[FAMILIES[stage]]==geo[FAMILIES[stage]]
        assert full[KEYS[stage]]==geo[KEYS[stage]]


@pytest.mark.parametrize('stage',PRODUCERS)
def test_owned_publication_preserves_source_and_object_identity(stage):
    world=current('continental_realm');before=deepcopy(world)
    identities=[id(c) for c in world['cells']]
    summary_id=id(world['summary']);cells_id=id(world['cells'])
    resource_id=id(world['resource_deposits'])
    parent_id=id(world['aquifer_resource_model']);groundwater_id=id(world['groundwater_flow_model'])
    PRODUCERS[stage](world)
    assert world==before
    assert identities==[id(c) for c in world['cells']]
    assert (id(world['summary']),id(world['cells']),id(world['resource_deposits']),id(world['aquifer_resource_model']),id(world['groundwater_flow_model']))==(summary_id,cells_id,resource_id,parent_id,groundwater_id)


@pytest.mark.parametrize('value',[None,True,'ignored',[],{},float('nan'),float('inf'),10**400,-10,1e200])
def test_social_score_cannot_change_natural_diagnostics(value):
    world=current();before=current()
    for c in world['cells']:c['settlement_score']=value
    rebuild(world)
    for stage,fields in OWNED.items():
        assert [{k:c[k] for k in fields} for c in world['cells']]==[{k:c[k] for k in fields} for c in before['cells']]
        assert world[FAMILIES[stage]]==before[FAMILIES[stage]]
    assert all(c['settlement_score'] is value for c in world['cells'])


@pytest.mark.parametrize('stage',PRODUCERS)
@pytest.mark.parametrize('root',[None,[],0,True,'world'])
def test_malformed_roots_produce_bounded_diagnostic_and_value_error(stage,root):
    errors=AUDITS[stage](root)
    assert len(errors)==1 and len(errors[0])<=600
    with pytest.raises(ValueError):PRODUCERS[stage](root)


@pytest.mark.parametrize('stage',PRODUCERS)
@pytest.mark.parametrize('mutation',['own_none','own_unknown','own_extra','summary_missing','summary_wrong','own_missing','dynamic_bool','dynamic_float'])
def test_malformed_or_partial_own_envelopes_fail_before_mutation(stage,mutation):
    world=current();key=KEYS[stage]
    if mutation=='own_none':world[key]=None
    elif mutation=='own_unknown':world[key]['model_type']='unknown'
    elif mutation=='own_extra':world[key]['made_up']=True
    elif mutation=='summary_missing':del world['summary'][key]
    elif mutation=='summary_wrong':world['summary'][key]='unknown'
    elif mutation=='own_missing':del world[key]
    elif mutation=='dynamic_bool':world[key]['candidate_cell_count']=True
    else:world[key]['candidate_cell_count']=float(world[key]['candidate_cell_count'])
    before=encoded(world)
    assert AUDITS[stage](world)
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


@pytest.mark.parametrize('stage',PRODUCERS)
def test_clearing_both_own_keys_rebuilds_current_from_known_parent(stage):
    world=current();expected=deepcopy(world);key=KEYS[stage]
    del world[key];del world['summary'][key]
    PRODUCERS[stage](world)
    assert world==expected


@pytest.mark.parametrize('stage',PRODUCERS)
def test_old_own_under_new_parent_rejects(stage):
    world=current();old=historical();key=KEYS[stage]
    if stage=='karst':
        world[key]['model_type']='carbonate_water_soil_aquifer_karst_diagnostics_v1'
        world['summary'][key]=world[key]['model_type']
    else:
        world[key]=old[key];world['summary'][key]=old['summary'][key]
    before=encoded(world)
    assert AUDITS[stage](world)
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


@pytest.mark.parametrize('stage,parent_key',[('channel','groundwater_flow_model'),('hydraulics','river_channel_morphology_model'),('karst','aquifer_resource_model')])
def test_no_parent_default_even_when_own_is_known(stage,parent_key):
    world=current();del world[parent_key];world['summary'].pop(parent_key)
    before=encoded(world)
    assert AUDITS[stage](world)
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


@pytest.mark.parametrize('stage,field',[('channel','baseflow_support_index'),('hydraulics','river_channel_width_m'),('karst','aquifer_productivity_index')])
def test_parent_numbers_cannot_be_forged_under_matching_names(stage,field):
    world=current();cell=next(c for c in world['cells'] if c['is_river'] and not c['is_water'])
    cell[field]+=.01;before=encoded(world)
    assert AUDITS[stage](world)
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


@pytest.mark.parametrize('stage,field',[('channel','flow_to'),('channel','fluvial_sediment_routed_outgoing_m'),('hydraulics','sediment_routing_load_m'),('karst','soil_ph')])
@pytest.mark.parametrize('value',[None,True,'bad',[],{},float('nan'),float('inf'),10**400])
def test_present_consumed_malformed_input_rejects_atomically(stage,field,value):
    world=current();cell=next(c for c in world['cells'] if c['is_river'] and not c['is_water'])
    cell[field]=value;before=encoded(world)
    assert AUDITS[stage](world)
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


@pytest.mark.parametrize('stage',PRODUCERS)
@pytest.mark.parametrize('mutation',['neighbor_unknown','neighbor_self','neighbor_duplicate','duplicate_id','summary_list'])
def test_consumed_graph_and_root_mapping_rejection(stage,mutation):
    world=current();cell=world['cells'][0]
    if mutation=='neighbor_unknown':cell['neighbors'].append(999999)
    elif mutation=='neighbor_self':cell['neighbors'].append(cell['id'])
    elif mutation=='neighbor_duplicate':cell['neighbors'].append(cell['neighbors'][0])
    elif mutation=='duplicate_id':world['cells'][1]['id']=cell['id']
    else:world['summary']=[]
    before=encoded(world)
    assert AUDITS[stage](world)
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


@pytest.mark.parametrize('stage',PRODUCERS)
@pytest.mark.parametrize('mutation',['record_unknown','record_drop','record_duplicate','record_extra','record_bool_count','record_none','cell_string_id','cell_missing','cell_quantum','summary_count'])
def test_records_fields_and_counters_are_independently_replayed(stage,mutation):
    world=current('continental_realm');records=world[FAMILIES[stage]];record=records[0]
    cid=record['cell_ids'][0];cell=next(c for c in world['cells'] if c['id']==cid)
    numeric=next(k for k in OWNED[stage] if not k.endswith('_id') and type(cell[k]) is float)
    link=next(k for k in OWNED[stage] if k.endswith('_id'))
    if mutation=='record_unknown':record['cell_ids'][0]=999999
    elif mutation=='record_drop':records.pop()
    elif mutation=='record_duplicate':records.append(deepcopy(record))
    elif mutation=='record_extra':record['invented_source']=1
    elif mutation=='record_bool_count':record['cell_count']=True
    elif mutation=='record_none':records[0]=None
    elif mutation=='cell_string_id':cell[link]=str(cell[link])
    elif mutation=='cell_missing':del cell[numeric]
    elif mutation=='cell_quantum':cell[numeric]+=1e-6
    else:world[KEYS[stage]]['candidate_cell_count']+=1
    assert AUDITS[stage](world)


@pytest.mark.parametrize('stage',PRODUCERS)
def test_current_rebuild_replaces_stale_owned_values(stage):
    world=current('continental_realm');expected=deepcopy(world)
    for cell in world['cells']:
        for key in OWNED[stage]:cell[key]='stale'
    world[FAMILIES[stage]]=[]
    PRODUCERS[stage](world)
    assert world==expected


@pytest.mark.parametrize('stage',PRODUCERS)
def test_changed_producer_equation_is_detected_before_commit(stage,monkeypatch):
    world=current();before=encoded(world)
    if stage=='channel':monkeypatch.setattr(channel_module,'_channel_class',lambda *args:'invented_channel')
    elif stage=='hydraulics':monkeypatch.setattr(hydraulic_module,'_manning_roughness',lambda *args:.08)
    else:monkeypatch.setattr(karst_module,'_karst_components',lambda *args:(.5,.5,.5))
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


def test_karst_source_replay_rejects_forged_consistent_aggregates():
    world=current('continental_realm');record=world['karst_systems'][0]
    cells={c['id']:c for c in world['cells']}
    for cid in record['cell_ids']:cells[cid]['subterranean_drainage_fraction']+=.01
    record['mean_subterranean_drainage_fraction']=round(sum(cells[cid]['subterranean_drainage_fraction'] for cid in record['cell_ids'])/len(record['cell_ids']),6)
    world['summary']['mean_subterranean_drainage_fraction']=round(sum(c['subterranean_drainage_fraction'] for c in cells.values())/len(cells),6)
    assert validate_natural_karst_diagnostics(world)


def test_karst_has_only_direct_aquifer_dependency():
    world=current('continental_realm');expected=deepcopy(world['karst_systems'])
    for key in list(world):
        if key.startswith('groundwater_flow') or key.startswith('river_'):world.pop(key)
    for key in list(world['summary']):
        if key.startswith('groundwater_flow') or key.startswith('river_'):world['summary'].pop(key)
    assert validate_natural_karst_diagnostics(world)==[]
    PRODUCERS['karst'](world)
    assert world['karst_systems']==expected


def test_raw_ice_classification_boundary_keeps_its_existing_equation():
    world=current();cid=next(c['id'] for c in world['cells'] if c['is_river'] and not c['is_water'])
    results=[]
    for ice in (126-1e-9,126,126+1e-9):
        changed=deepcopy(world);cell=next(c for c in changed['cells'] if c['id']==cid)
        cell['ice_thickness_m']=ice;rebuild(changed)
        assert validate_natural_channel_morphology(changed)==[]
        results.append(cell['channel_morphology_class'])
    assert results[0]!='glacial_outwash_channel'
    assert results[1:]==['glacial_outwash_channel','glacial_outwash_channel']


def test_configured_gravity_scales_froude_and_shear_without_geometry_changes():
    earth=current();low=deepcopy(earth);low['planet_parameters']['gravity_g']*=.25
    PRODUCERS['hydraulics'](low)
    assert low['river_channel_systems']==earth['river_channel_systems']
    cid=next(c['id'] for c in earth['cells'] if c['is_river'] and c['bed_shear_stress_pa']>0)
    a=next(c for c in earth['cells'] if c['id']==cid);b=next(c for c in low['cells'] if c['id']==cid)
    assert b['froude_number']==pytest.approx(2*a['froude_number'],abs=1.1e-6)
    assert b['bed_shear_stress_pa']==pytest.approx(.25*a['bed_shear_stress_pa'],abs=1.1e-6)
    assert validate_natural_river_hydraulics(low)==[]


@pytest.mark.parametrize('stage',PRODUCERS)
def test_explicit_unknown_declaration_cannot_hide_behind_empty_cells(stage):
    world={'cells':[],'summary':{},KEYS[stage]:{'model_type':'unknown'}}
    before=encoded(world)
    assert AUDITS[stage](world)
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


def test_valid_empty_parent_chain_publishes_exact_zero_models():
    world={'cells':[],'summary':{},'planet_parameters':{'radius_km':6371.0,'gravity_g':1.0}}
    rebuild(world)
    for stage,audit in AUDITS.items():
        assert audit(world)==[]
        assert world[FAMILIES[stage]]==[]
        assert world[KEYS[stage]]['candidate_cell_count']==0


@pytest.mark.parametrize('stage',PRODUCERS)
def test_independent_metadata_does_not_follow_producer_constants(stage,monkeypatch):
    module={'channel':channel_module,'hydraulics':hydraulic_module,'karst':karst_module}[stage]
    world=current();before=encoded(world)
    monkeypatch.setitem(module.NATURAL_MODEL,'model_type','invented')
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


@pytest.mark.parametrize('stage',PRODUCERS)
def test_one_way_mesh_cannot_claim_undirected_components(stage):
    world=current();cell=world['cells'][0];neighbor=next(c for c in world['cells'] if c['id']==cell['neighbors'][0])
    neighbor['neighbors'].remove(cell['id'])
    # Rebuild actual upstream values so rejection cannot rely on stale parent
    # numbers. Batch1 permits directed input links; these component models do not.
    aquifer(world);groundwater(world)
    before=encoded(world)
    assert AUDITS[stage](world)
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


@pytest.mark.parametrize('stage',PRODUCERS)
def test_finite_sources_with_unrepresentable_derived_arithmetic_reject(stage):
    world=current();cell=next(c for c in world['cells'] if c['is_river'] and not c['is_water'])
    if stage=='channel':
        target=next(c for c in world['cells'] if c['id']==cell['flow_to'])
        cell['hydrologic_surface_elevation_m']=1e308
        target['hydrologic_surface_elevation_m']=-1e308
    elif stage=='hydraulics':
        world['planet_parameters']['gravity_g']=1e307
    else:
        neighbor=next(c for c in world['cells'] if c['id']==cell['neighbors'][0])
        cell['elevation_m']=1e308;neighbor['elevation_m']=-1e308
    before=encoded(world)
    assert AUDITS[stage](world)
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


def test_missing_selected_fallback_input_does_not_override_valid_alternative():
    world=current();cell=next(c for c in world['cells'] if c['is_river'] and not c['is_water'])
    expected=deepcopy(world['river_channel_systems'])
    cell['sediment_export_m']=cell.pop('fluvial_sediment_routed_outgoing_m')
    cell['filled_elevation_m']=cell.pop('hydrologic_surface_elevation_m')
    PRODUCERS['channel'](world)
    assert world['river_channel_systems']==expected
    assert validate_natural_channel_morphology(world)==[]


@pytest.mark.parametrize('stage',PRODUCERS)
def test_parent_model_type_and_dynamic_metadata_cannot_be_forged(stage):
    world=current();key={'channel':'groundwater_flow_model','hydraulics':'river_channel_morphology_model','karst':'aquifer_resource_model'}[stage]
    world[key]['model_type']='unknown';before=encoded(world)
    assert AUDITS[stage](world)
    with pytest.raises(ValueError):PRODUCERS[stage](world)
    assert encoded(world)==before


@pytest.mark.parametrize('stage',PRODUCERS)
def test_unchanged_equations_retain_all_historical_non_natural_parent_sources(stage):
    before=historical('continental_realm');world=current('continental_realm')
    fields={'channel':('flow_accumulation','runoff_mm_y','hydrologic_surface_elevation_m','fluvial_sediment_routed_outgoing_m','sediment_thickness_m','wetland_extent_index'),
            'hydraulics':('sediment_routing_load_m','wetland_extent_index','ice_thickness_m'),
            'karst':('aquifer_storage_index','groundwater_recharge_mm_y','soil_ph','soil_profile_development_index','soil_moisture_index','precipitation_mm_y','temperature_c')}[stage]
    assert [{k:c[k] for k in fields} for c in world['cells']]==[{k:c[k] for k in fields} for c in before['cells']]
    if stage=='karst':
        assert [c['karst_potential_index'] for c in world['cells']]==[c['karst_potential_index'] for c in before['cells']]
        assert [c['cave_development_index'] for c in world['cells']]==[c['cave_development_index'] for c in before['cells']]


def test_raw_shear_summary_threshold_and_rounded_reach_count_remain_distinct():
    original=current('continental_realm')
    target=next(c for c in original['cells'] if c['is_river'] and not c['is_water'] and c['bed_shear_stress_pa']>0)
    width=target['river_channel_width_m'];depth=target['river_channel_depth_m']
    radius=max(.001,width*depth)/max(.001,width+2*depth)
    slope=max(.00001,target['channel_slope_index']*.028)
    reference=120/(1000*9.80665*radius*slope)
    results=[]
    for multiplier in (1-1e-9,1,1+1e-9):
        world=deepcopy(original);world['planet_parameters']['gravity_g']=reference*multiplier
        PRODUCERS['hydraulics'](world)
        assert validate_natural_river_hydraulics(world)==[]
        source=next(c for c in world['cells'] if c['id']==target['id'])
        assert source['bed_shear_stress_pa']==120.0
        # Independent raw calculation uses the exported channel parent values.
        gravity=world['planet_parameters']['gravity_g']*9.80665
        count=0
        for c in world['cells']:
            if c['is_river'] and not c['is_water']:
                area=max(.001,c['river_channel_width_m']*c['river_channel_depth_m'])
                perimeter=max(.001,c['river_channel_width_m']+2*c['river_channel_depth_m'])
                raw=1000*gravity*(area/perimeter)*max(.00001,c['channel_slope_index']*.028)
                count+=raw>=120
        assert world['summary']['high_shear_stress_cell_count']==count
        results.append(world)
    assert results[0]['summary']['high_shear_stress_cell_count']<results[-1]['summary']['high_shear_stress_cell_count']
    sid=target['river_channel_system_id']
    assert results[0]['river_hydraulic_reaches'][sid]['high_shear_stress_cell_count']==results[-1]['river_hydraulic_reaches'][sid]['high_shear_stress_cell_count']
    altered=deepcopy(results[0]);altered['summary']['high_shear_stress_cell_count']=results[-1]['summary']['high_shear_stress_cell_count']
    assert validate_natural_river_hydraulics(altered)
    altered=deepcopy(results[0]);altered['river_hydraulic_reaches'][sid]['high_shear_stress_cell_count']-=1
    assert validate_natural_river_hydraulics(altered)


def test_zero_length_measure_accepts_json_integer_or_float_while_counts_remain_integers():
    world=current('glasswind_desert')
    for value in (0,0.0):
        world['summary']['total_river_channel_length_km']=value
        assert validate_natural_channel_morphology(world)==[]
    world['summary']['river_channel_cell_count']=0.0
    assert validate_natural_channel_morphology(world)
