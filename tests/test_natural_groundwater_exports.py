"""Retained stage projections and exact display contracts; no native generation."""
from copy import deepcopy
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

import pyarrow.parquet as pq
import pytest

from magic_geo.aquifer_resources import enrich_world_with_aquifer_resources
from magic_geo.groundwater_flow import enrich_world_with_groundwater_flow
from magic_geo.natural_groundwater_validation import validate_natural_groundwater_flow
from magic_geo.debug_export import export_debug_cache
from magic_geo.debug_map_export import _describe_layer, export_map_reference
from magic_geo.debug_server import _DebugCache
from magic_geo.io import write_cells_csv, write_summary_markdown

DATA=Path(__file__).parent/'data'
N='aquifer_natural_limitation_index'
R='aquifer_extraction_risk_index'


def retained_world(version):
    root=DATA/'natural_groundwater'
    manifest=json.loads((root/'manifest.json').read_text())['fixtures']['full_world']
    raw=(root/'full_world.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==manifest['projection_sha256']
    world=json.loads(raw)
    geometry=json.loads((DATA/'natural_groundwater_export_geometry.json').read_text())
    assert geometry['source_sha256']==manifest['uncompressed_sha256']
    assert len(geometry['cells'])==len(world['cells'])==128
    for cell,shape in zip(world['cells'],geometry['cells']):
        assert cell['id']==shape['id']
        cell.update(shape)
    if version==2:
        for field in ('aquifer_resource_model','groundwater_flow_model'):
            del world[field];del world['summary'][field]
        enrich_world_with_aquifer_resources(world)
        enrich_world_with_groundwater_flow(world)
    assert validate_natural_groundwater_flow(world)==[]
    return world


@pytest.fixture(scope='module')
def versions():
    return {v:retained_world(v) for v in (1,2)}


@pytest.mark.parametrize('version',[1,2])
def test_csv_preserves_declared_natural_or_historical_risk_without_aliasing(versions,version,tmp_path):
    world=versions[version];before=deepcopy(world)
    target=tmp_path/'cells.csv';write_cells_csv(target,world)
    with target.open(newline='') as stream:
        reader=csv.DictReader(stream);rows=list(reader);columns=reader.fieldnames
    assert columns[-5]==N and len(columns)==len(set(columns))
    assert columns[-4:]==['agricultural_habitat_applicable','agricultural_climate_supported',
                          'agricultural_potential_supported','mining_surface_applicable']
    actual=N if version==2 else R;absent=R if version==2 else N
    assert [float(row[actual]) for row in rows]==[c[actual] for c in world['cells']]
    assert all(row[absent]=='' for row in rows)
    assert world==before


@pytest.mark.parametrize('version',[1,2])
def test_summary_exports_new_counters_or_original_risk_only_when_present(versions,version,tmp_path):
    world=versions[version];before=deepcopy(world)
    target=tmp_path/'summary.md';write_summary_markdown(target,world);text=target.read_text()
    expected=('mean_'+N,'high_natural_limitation_aquifer_cell_count') if version==2 else ('mean_'+R,'groundwater_stressed_cell_count')
    absent=('mean_'+R,'groundwater_stressed_cell_count') if version==2 else ('mean_'+N,'high_natural_limitation_aquifer_cell_count')
    for key in expected:assert f'`{key}`: {world["summary"][key]}' in text
    for key in absent:assert f'`{key}`:' not in text
    assert world==before


@pytest.mark.parametrize('version',[1,2])
def test_actual_debug_cache_preserves_raw_models_records_and_layer_fields(versions,version,tmp_path):
    world=versions[version];before=deepcopy(world)
    folder=tmp_path/'cache';manifest=export_debug_cache(world,folder,include_vtu=False)
    cells=pq.read_table(folder/'tables/cells.parquet').to_pydict()
    field=N if version==2 else R;absent=R if version==2 else N
    assert cells[field]==[c[field] for c in world['cells']]
    assert absent not in cells
    assert field in [entry['name'] for entry in manifest['cells']['fields']]
    layers={layer['id']:layer for layer in manifest['layers']}
    assert 'cells/'+field in layers and 'cells/'+absent not in layers
    assert 'availability' not in layers['cells/'+field]
    assert layers['cells/'+field]['stats']['min']==0.0  # Declared marine structural zero remains visible.
    sections=json.loads((folder/'sections.json').read_text())
    for name in ('summary','aquifer_resource_model','groundwater_recharge_model','groundwater_flow_model'):
        assert sections[name]==world[name]
        assert name in manifest['sections']
    cache=_DebugCache(folder)
    try:
        assert cache.layer_values('cells/'+field,None,None)==[c[field] for c in world['cells']]
        for name in ('aquifer_systems','groundwater_flow_systems'):
            assert cache.family_rows(name,1000,0,'full')['rows']==world[name]
        for cell in world['cells']:
            observed=cache.cell_record(cell['id'])['cell']
            assert observed[field]==cell[field]
            assert absent not in observed
    finally:cache.close()
    assert world==before


def test_mixed_display_absence_known_zero_and_ecology_masks_remain_distinct(tmp_path):
    # Deliberately mixed display records, not a model-valid groundwater envelope.
    fields=[{N:0.0,R:.4},{N:.2},{R:0.0},{}]
    world={'cells':[{'id':i,'lat_deg':0.,'lon_deg':i*2.,'primary_productivity_index':0.,**f} for i,f in enumerate(fields)],'summary':{}}
    world['cells'][0]['primary_productivity_supported']=False
    world['cells'][1]['primary_productivity_supported']=True
    target=tmp_path/'cells.csv';write_cells_csv(target,world)
    with target.open(newline='') as stream:rows=list(csv.DictReader(stream))
    assert [r[N] for r in rows]==['0.0','0.2','','']
    assert [r[R] for r in rows]==['0.4','','0.0','']
    export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    raw=pq.read_table(tmp_path/'cache/tables/cells.parquet').to_pydict()
    assert raw[N]==[0.,.2,None,None] and raw[R]==[.4,None,0.,None]
    cache=_DebugCache(tmp_path/'cache')
    try:
        n=cache.layer_values('cells/'+N,None,None);r=cache.layer_values('cells/'+R,None,None)
        assert n[:2]==[0.,.2] and all(math.isnan(v) for v in n[2:])
        assert r[0]==.4 and r[2]==0. and math.isnan(r[1]) and math.isnan(r[3])
        ecological=cache.layer_values('cells/primary_productivity_index',None,None)
        assert math.isnan(ecological[0]) and ecological[1:]==[0.,0.,0.]
    finally:cache.close()


@pytest.mark.parametrize('declared',[False,True])
def test_karst_model_declaration_is_exported_exactly_only_when_present(versions,declared,tmp_path):
    # Export-only metadata fixture; this does not certify the pending downstream stage.
    world=deepcopy(versions[2])
    name='karst_diagnostics_model'
    if declared:
        world[name]={'model':'carbonate_water_soil_aquifer_karst_diagnostics_v2'}
        world['summary'][name]=world[name]['model']
    else:
        world.pop(name,None);world['summary'].pop(name,None)
    before=deepcopy(world)
    target=tmp_path/'summary.md';write_summary_markdown(target,world)
    manifest=export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    sections=json.loads((tmp_path/'cache/sections.json').read_text())
    if declared:
        assert f'`{name}`: {world[name]["model"]}' in target.read_text()
        assert sections[name]==world[name] and name in manifest['sections']
    else:
        assert f'`{name}`:' not in target.read_text()
        assert name not in sections and name not in manifest['sections']
    assert world==before


@pytest.mark.parametrize('field,phrases',[
    (N,('Natural limitation proxy','Independent of settlement','structural zero')),
    ('groundwater_hydraulic_head_m',('Diagnostic hydraulic head','No Darcy')),
    ('aquifer_productivity_index',('diagnostic','no measured or sustainable yield')),
    ('baseflow_support_index',('Annual diagnostic','Dry-season flow reliability is unresolved')),
    ('groundwater_retained_storage_km3_y',('annual recharge-partition remainder','not a stored-water stock')),
    (R,('Historical v1','settlement suitability','absent in natural v2')),
])
def test_actual_png_and_markdown_use_the_same_scientifically_scoped_docs(versions,field,phrases,tmp_path):
    world=versions[1 if field==R else 2]
    folder=tmp_path/'cache';export_debug_cache(world,folder,include_vtu=False)
    result=export_map_reference(folder,layer_id='cells/'+field,output=tmp_path/'map.png',projection='equirect',width=128,height=64)
    assert result.image_path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    text=result.prompt_path.read_text()
    for phrase in phrases:assert phrase in text
    if field=='groundwater_retained_storage_km3_y':assert 'km³/year' in text


def test_javascript_describes_actual_groundwater_fields(tmp_path):
    node=shutil.which('node')
    if node is None:pytest.skip('Node.js needed for JavaScript documentation check')
    result=subprocess.run([node,str(Path(__file__).with_suffix('.mjs'))],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
