"""Land-use display availability is distinct from values and mineral existence."""
from copy import deepcopy
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

import pyarrow.parquet as pq
import pytest

from magic_geo.debug_export import export_debug_cache
from magic_geo.debug_server import _DebugCache
from magic_geo.debug_map_export import _describe_layer, export_map_reference
from magic_geo.io import write_cells_csv, write_summary_markdown

FLAGS=('agricultural_habitat_applicable','agricultural_climate_supported',
       'agricultural_potential_supported','mining_surface_applicable')
COUNTERS=tuple(field+'_cell_count' for field in FLAGS)+(
    'agricultural_potential_supported_area_km2','unsupported_terrestrial_agricultural_cell_count')
AG='agricultural_potential_index'
MINING='mining_potential_index'
MODEL='causal_soil_climate_resource_connected_land_use_zones_v2'


def display_world():
    """Explicit mixed display records, not a claimed valid land-use model."""
    cells=[]
    for i in range(4):
        c={'id':i,'lat_deg':0.,'lon_deg':i*3.,'area_km2':1.,'elevation_m':0.,
           'position_3d':[1.,0.,0.], 'boundary_ring':[[0.,i*3.],[0.,i*3.+1.],[1.,i*3.]],
           AG:0.,MINING:0.,'resource':'placer_metals'}
        cells.append(c)
    # Unsupported wet cell, supported known-zero land, thermally unsupported
    # land with applicable mining, and legacy/undeclared display values.
    for c,flags in zip(cells,((False,False,False,False),(True,True,True,True),(True,False,False,True))):
        c.update(zip(FLAGS,flags))
    return {'name':'Mixed land-use display','cells':cells,'summary':{}}


def test_csv_appends_flags_preserving_raw_zero_and_legacy_absence(tmp_path):
    world=display_world(); before=deepcopy(world)
    target=tmp_path/'cells.csv';write_cells_csv(target,world)
    with target.open(newline='') as stream:
        reader=csv.DictReader(stream);rows=list(reader);columns=reader.fieldnames
    assert columns[446:450]==list(FLAGS)  # Historical 450-column prefix is preserved; successor fields append.
    assert columns[445]=='aquifer_natural_limitation_index'
    assert len(columns)==len(set(columns))
    for flag in FLAGS:
        assert [row[flag] for row in rows]==[str(c[flag]) if flag in c else '' for c in world['cells']]
    for field in (AG,MINING):assert [float(row[field]) for row in rows]==[0.,0.,0.,0.]
    assert [row['resource'] for row in rows]==['placer_metals']*4
    assert world==before


@pytest.mark.parametrize('field,support,missing',[(AG,FLAGS[2],[0,2]),(MINING,FLAGS[3],[0])])
def test_real_cache_masks_only_the_own_exact_flag_and_preserves_raw_inputs(tmp_path,field,support,missing):
    world=display_world();before=deepcopy(world)
    export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    raw=pq.read_table(tmp_path/'cache/tables/cells.parquet').to_pydict()
    assert raw[field]==[0.,0.,0.,0.]
    cache=_DebugCache(tmp_path/'cache')
    try:
        layer=cache.layers['cells/'+field]
        assert layer['availability']=={'field':support,'unavailable_when':'false'}
        assert layer['unavailable_cell_count']==len(missing)
        values=cache.layer_values(layer['id'],None,None)
        for i,value in enumerate(values):
            assert math.isnan(value) if i in missing else value==0.
        assert layer['stats']['min']==layer['stats']['max']==0.
        assert [cache.cell_record(i)['cell'][field] for i in range(4)]==[0.,0.,0.,0.]
        assert all(cache.cell_record(i)['cell']['resource']=='placer_metals' for i in range(4))
    finally:cache.close()
    assert world==before


@pytest.mark.parametrize('flag',FLAGS)
def test_flags_are_selectable_boolean_layers_with_undeclared_missing_category(tmp_path,flag):
    world=display_world()
    export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    cache=_DebugCache(tmp_path/'cache')
    try:
        layer=cache.layers['cells/'+flag]
        codes=cache.layer_values(layer['id'],None,None)
        assert [layer['categories'][int(code)] for code in codes[:3]]==[str(c[flag]) for c in world['cells'][:3]]
        assert math.isnan(codes[3])
        assert 'availability' not in layer
    finally:cache.close()


@pytest.mark.parametrize('field', [AG,MINING])
def test_all_unavailable_stays_selectable_without_fabricated_numeric_range(tmp_path,field):
    world=display_world();world['cells']=world['cells'][:1]
    manifest=export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    layer=next(layer for layer in manifest['layers'] if layer['id']=='cells/'+field)
    assert layer['unavailable_cell_count']==1 and 'stats' not in layer
    cache=_DebugCache(tmp_path/'cache')
    try:assert math.isnan(cache.layer_values(layer['id'],None,None)[0])
    finally:cache.close()


def test_unsupported_outliers_do_not_change_color_ranges_or_remove_mineral_data(tmp_path):
    world=display_world()
    world['cells'][0][AG]=99.;world['cells'][0][MINING]=88.
    world['cells'][2][AG]=77.;world['cells'][2][MINING]=.75
    before=deepcopy(world)
    manifest=export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    layers={layer['name']:layer for layer in manifest['layers']}
    assert layers[AG]['stats']['max']==0.
    assert layers[MINING]['stats']['max']==.75  # Own surface flag; no agriculture thermal gate.
    raw=pq.read_table(tmp_path/'cache/tables/cells.parquet').to_pydict()
    assert raw[AG]==[99.,0.,77.,0.] and raw[MINING]==[88.,0.,.75,0.]
    assert world==before


def test_pure_legacy_values_have_no_invented_availability_layer(tmp_path):
    world=display_world()
    for c in world['cells']:
        for flag in FLAGS:c.pop(flag,None)
    manifest=export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    for layer in manifest['layers']:
        if layer['name'] in (AG,MINING):
            assert 'availability' not in layer
            assert layer['stats']['min']==layer['stats']['max']==0.
    assert not set(FLAGS)&{layer['name'] for layer in manifest['layers']}


@pytest.mark.parametrize('version',[1,2])
def test_summary_counts_scope_and_legacy_absence_are_explicit(tmp_path,version):
    world=display_world()
    world['land_use_zone_model']={'model_type':MODEL[:-1]+str(version)}
    world['summary'].update(mean_agricultural_potential_index=0.,mean_mining_potential_index=.2)
    if version==2:world['summary'].update(zip(COUNTERS,(2,1,1,2,1.5,1)))
    before=deepcopy(world)
    target=tmp_path/'summary.md';write_summary_markdown(target,world);text=target.read_text()
    for field in COUNTERS:
        if version==2:assert f'`{field}`: {world["summary"][field]}' in text
        else:assert f'`{field}`:' not in text
    if version==2:
        assert 'All-cell means include unavailable zeros' in text
        assert 'not gated by agricultural temperature support' in text
        assert 'does not establish complete mining inputs or economic access' in text
        assert 'does not predict crop survival or yield' in text
    else:assert 'agricultural availability and mining surface applicability are undeclared' in text
    assert world==before


@pytest.mark.parametrize('field',[AG,MINING])
def test_map_codex_consumes_shared_mask_and_curated_scope(tmp_path,field):
    world=display_world();export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    result=export_map_reference(tmp_path/'cache',layer_id='cells/'+field,output=tmp_path/'map.png',
                                projection='equirect',width=64,height=32)
    assert result.image_path.read_bytes().startswith(b'\x89PNG')
    text=result.prompt_path.read_text()
    assert 'supported zero values remain visible' in text
    if field==AG:assert 'not crop survival or yield' in text
    else:assert 'does not establish complete mining inputs or economic access' in text
    layer={'id':'cells/'+field,'name':field,'source':'cells','kind':'numeric'}
    assert 'legacy' in _describe_layer(layer).description.lower()


def test_actual_exported_cells_and_layers_reach_the_js_inspector(tmp_path):
    if shutil.which('node') is None:pytest.skip('Node required for frontend replay')
    world=display_world();manifest=export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    cache=_DebugCache(tmp_path/'cache')
    try:cells=[cache.cell_record(i)['cell'] for i in range(4)]
    finally:cache.close()
    payload=tmp_path/'ui.json';payload.write_text(json.dumps({'manifest':manifest,'cells':cells}))
    script=Path(__file__).with_suffix('.mjs')
    run=subprocess.run(['node',str(script),str(payload)],capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stdout+run.stderr
    assert 'exported agricultural and mining layers agree with inspector' in run.stdout


@pytest.fixture(scope="module")
def retained_agricultural_versions():
    """Complete genuine native world; deliberate own-model upgrade only.

    The shared public-integration fixture is checked in and hash checked. This
    display test does not certify unreplayed human successors after the upgrade.
    """
    from magic_geo.land_use_zones import enrich_world_with_land_use_zones
    from magic_geo.land_use_availability_validation import validate_land_use_availability
    from magic_geo.native_climate_energy_validation import validate_native_climate_energy

    folder=Path(__file__).parent/'data/agricultural_public'
    manifest=json.loads((folder/'manifest.json').read_text())['full_world']
    packed=(folder/manifest['file']).read_bytes()
    assert hashlib.sha256(packed).hexdigest()==manifest['gzip_sha256']
    raw=gzip.decompress(packed)
    assert hashlib.sha256(raw).hexdigest()==manifest['source_sha256']
    original=json.loads(raw)
    assert len(original['cells'])==manifest['cell_count']==128
    assert original['land_use_zone_model']['model_type']==MODEL[:-1]+'1'
    assert validate_land_use_availability(original)==[]
    assert validate_native_climate_energy(original)==[]
    current=deepcopy(original)
    certificate_names=('climate_model','climate_energy_model','climate_energy_balance_records',
                       'climate_energy_forcing_intervals','climate_energy_transport_edges')
    owned_native={name:current[name] for name in certificate_names}
    deposits=current['resource_deposits']
    del current['land_use_zone_model']
    del current['summary']['land_use_zone_model']
    enrich_world_with_land_use_zones(current)
    assert validate_land_use_availability(current)==[]
    assert current['land_use_zone_model']['model_type']==MODEL
    assert all(current[name] is obj and obj==original[name] for name,obj in owned_native.items())
    assert current['resource_deposits'] is deposits and deposits==original['resource_deposits']
    return {1:original,2:current}


@pytest.mark.parametrize('version',[1,2])
def test_complete_retained_world_export_keeps_certificates_minerals_and_exact_availability(
        retained_agricultural_versions,version,tmp_path):
    world=retained_agricultural_versions[version];before=deepcopy(world)
    folder=tmp_path/'cache';manifest=export_debug_cache(world,folder,include_vtu=False)
    raw=pq.read_table(folder/'tables/cells.parquet').to_pydict()
    cache=_DebugCache(folder)
    try:
        for field,support in ((AG,FLAGS[2]),(MINING,FLAGS[3])):
            assert raw[field]==[c[field] for c in world['cells']]
            layer=cache.layers['cells/'+field]
            values=cache.layer_values(layer['id'],None,None)
            if version==2:
                assert layer['availability']=={'field':support,'unavailable_when':'false'}
                assert layer['unavailable_cell_count']==sum(c[support] is False for c in world['cells'])
            else:assert 'availability' not in layer
            for cell,value in zip(world['cells'],values):
                assert math.isnan(value) if cell.get(support) is False else value==cell[field]
        for flag in FLAGS:
            if version==2:
                assert raw[flag]==[c[flag] for c in world['cells']]
                assert 'cells/'+flag in cache.layers
            else:assert flag not in raw and 'cells/'+flag not in cache.layers
        for name in ('summary','land_use_zone_model','climate_model','climate_energy_model'):
            assert name in manifest['sections'] and cache.sections[name]==world[name]
        for name in ('agricultural_zones','mining_zones','resource_deposits','climate_energy_balance_records',
                     'climate_energy_forcing_intervals','climate_energy_transport_edges'):
            assert cache.family_rows(name,10000,0,'full')['rows']==world[name]
        for cell in world['cells']:
            for field in ('temperature_c','elevation_m','lat_deg','lon_deg','area_km2','resource'):
                assert raw[field][cell['id']]==cell[field]
    finally:cache.close()
    csv_path=tmp_path/'cells.csv';write_cells_csv(csv_path,world)
    with csv_path.open(newline='') as stream:rows=list(csv.DictReader(stream))
    for flag in FLAGS:
        assert [row[flag] for row in rows]==[str(c[flag]) if flag in c else '' for c in world['cells']]
    summary_path=tmp_path/'summary.md';write_summary_markdown(summary_path,world)
    summary=summary_path.read_text()
    for field in COUNTERS:
        if version==2:assert f'`{field}`: {world["summary"][field]}' in summary
        else:assert f'`{field}`:' not in summary
    assert world==before
