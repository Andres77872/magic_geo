"""Reef annotation controls: actual transport source and explicit link-only unit."""
from copy import deepcopy
import pytest

from magic_geo.reef_diagnostics import enrich_world_with_reef_diagnostics, _enrich_reef_stage
from magic_geo.reef_port_links_validation import validate_reef_port_links, PORTS3
from magic_geo import human_water_transport_validation as parent
from test_settlement_available_human_water import current


def test_actual_retained_transport_source_rebuilds_only_reef_owned_outputs(current):
    world=deepcopy(current)
    cells=list(world['cells']); summary=world['summary']
    before=deepcopy(world)
    enrich_world_with_reef_diagnostics(world)
    assert validate_reef_port_links(world)==[]
    assert world['cells']==cells and world['summary'] is summary
    assert all(a is b for a,b in zip(cells,world['cells']))
    after=deepcopy(world)
    enrich_world_with_reef_diagnostics(world)
    assert world==after
    for key in ('port_sites','routes','settlements','navigability_model','port_site_model'):
        assert world[key]==before[key]


def link_only_world():
    # Complete three-cell graph and declared port values, but no fabricated
    # climate certificate. The numerical parent audit is stubbed ONLY here.
    return dict(cells=[
        dict(id=0,neighbors=[1,2],is_water=True,is_lake=False,water_body_type='continental_shelf',
             temperature_c=26.,water_depth_m=20.,lat_deg=0.,lon_deg=0.,area_km2=1.,port_site_id=-1,port_site_selection_supported=True),
        dict(id=1,neighbors=[0],is_water=False,is_lake=False,temperature_c=20.,lat_deg=1.,lon_deg=0.,
             area_km2=1.,port_site_id=None,port_site_selection_supported=False),
        dict(id=2,neighbors=[0],is_water=False,is_lake=False,temperature_c=20.,lat_deg=0.,lon_deg=1.,
             area_km2=1.,port_site_id=0,port_site_selection_supported=True)],
        port_site_model={'model_type':PORTS3},port_sites=[{'id':0,'cell_id':2}],
        summary={'port_site_selection_complete':False})


def test_partial_link_ids_and_whole_source_coverage_do_not_gate_physical_reef(monkeypatch):
    monkeypatch.setattr(parent,'validate_versioned_port_sites',lambda world: [])
    world=link_only_world();legacy=deepcopy(world)
    legacy.pop('port_site_model');legacy['cells'][1]['port_site_id']=-1
    _enrich_reef_stage(legacy)
    enrich_world_with_reef_diagnostics(world)
    assert len(world['reef_systems'])==1
    reef=world['reef_systems'][0]
    assert reef['port_site_ids']==[0] and reef['port_site_links_complete'] is False
    assert world['summary']['reef_port_links_incomplete_system_count']==1
    assert world['summary']['reef_source_port_selection_complete'] is False
    assert validate_reef_port_links(world)==[]
    physical={k:v for k,v in reef.items() if k not in ('port_site_ids','port_site_links_complete')}
    assert physical=={k:v for k,v in legacy['reef_systems'][0].items() if k!='port_site_ids'}
    before=deepcopy(world)
    world['cells'][1]['port_site_selection_supported']=True
    world['cells'][1]['port_site_id']=-1
    world['summary']['port_site_selection_complete']=True
    enrich_world_with_reef_diagnostics(world)
    assert world['reef_systems'][0]['port_site_links_complete'] is True
    assert world['reef_systems'][0]['port_site_ids']==[0]
    assert world['cells'][0]['reef_growth_index']==before['cells'][0]['reef_growth_index']


@pytest.mark.parametrize('mutation', [
    lambda w:w['reef_systems'][0].update(port_site_links_complete=True),
    lambda w:w['reef_systems'][0].update(port_site_ids=[]),
    lambda w:w['reef_systems'][0].update(port_site_ids=[False]),
    lambda w:w['summary'].update(reef_port_links_incomplete_system_count=False),
    lambda w:w['reef_port_links_model'].update(source_port_site_model='old'),
    lambda w:w.pop('reef_port_links_model'),
])
def test_independent_annotation_replay_rejects_forged_coverage_and_ids(monkeypatch,mutation):
    monkeypatch.setattr(parent,'validate_versioned_port_sites',lambda world: [])
    world=link_only_world();enrich_world_with_reef_diagnostics(world);mutation(world)
    assert validate_reef_port_links(world)


def test_parent_or_private_stage_rejection_is_atomic(monkeypatch):
    world=link_only_world();before=deepcopy(world)
    monkeypatch.setattr(parent,'validate_versioned_port_sites',lambda world: ['invalid actual parent'])
    with pytest.raises(ValueError):enrich_world_with_reef_diagnostics(world)
    assert world==before
    monkeypatch.setattr(parent,'validate_versioned_port_sites',lambda world: [])
    world['cells'][0]['area_km2']='bad';before=deepcopy(world)
    with pytest.raises(ValueError):enrich_world_with_reef_diagnostics(world)
    assert world==before
