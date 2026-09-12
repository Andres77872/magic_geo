"""Raw exports and rendered layers distinguish unavailable, zero and legacy."""
from copy import deepcopy
import csv
import json
import math

import pyarrow.parquet as pq
import pytest

from magic_geo.debug_export import export_debug_cache
from magic_geo.debug_server import _DebugCache
from magic_geo.io import write_cells_csv, write_summary_markdown

PARENT_FLAGS = (
    'terrestrial_primary_climate_supported', 'primary_productivity_supported',
    'vegetation_biomass_supported', 'forest_growth_supported', 'vegetation_succession_supported',
    'species_richness_supported', 'ecosystem_wildfire_spread_risk_supported',
    'ecosystem_disturbance_pressure_supported', 'vegetation_recovery_supported',
)
DESCRIPTORS = ('species_composition_confidence_supported', 'species_endemism_supported', 'species_record_descriptors_supported')
FIRE_FLAGS = ('wildfire_fuel_continuity_supported', 'wildfire_firebreak_supported', 'wildfire_ignition_potential_supported')
GUILDS = ('canopy_tree','grassland_grazer','desert_specialist','alpine_tundra_specialist','large_predator','wetland_amphibian','freshwater_fish','marine_fish','reef_builder','mangrove_coastal_bird')
VALUES = ('primary_productivity_index','vegetation_biomass_index','forest_growth_index','species_richness_index',
          'wildfire_spread_risk_index','ecosystem_disturbance_pressure_index','vegetation_recovery_years',
          'species_composition_confidence_index','species_endemism_index','species_range_fragmentation_index',
          'wildfire_fuel_continuity_index','wildfire_firebreak_index','wildfire_ignition_potential_index')


def display_world():
    """Controlled display inputs, not a claimed native or ecological certificate."""
    cells=[]
    for i,available in enumerate((False,True,None)):
        c={'id':i,'lat_deg':0.,'lon_deg':float(i)*2,'area_km2':1.,'elevation_m':0.,
           'position_3d':[1.,0.,0.], 'boundary_ring':[[0.,i*2.],[0.,i*2.+1.],[1.,i*2.]],
           **dict.fromkeys(VALUES,0.), 'species_habitat_suitability_index':0.,
           'species_guild_richness_count':0,'dominant_species_guild':'none',
           'species_guild_scores':dict.fromkeys(GUILDS,0.)}
        if available is not None:
            c.update(dict.fromkeys(PARENT_FLAGS+DESCRIPTORS+FIRE_FLAGS,available))
            c.update({f'species_{g}_score_supported':available for g in GUILDS})
            c.update(species_applicable_guild_count=8,species_supported_guild_count=8 if available else 0,
                     species_composition_status='complete' if available else 'unavailable')
        cells.append(c)
    return {'name':'Mixed ecology display','cells':cells,'summary':{}}


def test_csv_preserves_exact_availability_fields_and_json_score_dictionary(tmp_path):
    world=display_world();before=deepcopy(world)
    path=tmp_path/'cells.csv';write_cells_csv(path,world)
    with path.open(newline='') as file:
        reader=csv.DictReader(file);rows=list(reader);headers=reader.fieldnames
    assert len(headers)==len(set(headers))
    for key in PARENT_FLAGS+DESCRIPTORS+FIRE_FLAGS+tuple(f'species_{g}_score_supported' for g in GUILDS):
        assert [r[key] for r in rows]==['False','True','']
    for key in VALUES:
        assert [float(r[key]) for r in rows]==[0.,0.,0.]
    assert [r['species_composition_status'] for r in rows]==['unavailable','complete','']
    assert [json.loads(r['species_guild_scores']) for r in rows]==[c['species_guild_scores'] for c in world['cells']]
    assert world==before


def test_real_cache_keeps_raw_values_details_and_support_boolean_categories(tmp_path):
    world=display_world();before=deepcopy(world)
    manifest=export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    table=pq.read_table(tmp_path/'cache/tables/cells.parquet').to_pydict()
    cache=_DebugCache(tmp_path/'cache')
    try:
        for key in VALUES:
            assert table[key]==[0.,0.,0.]
        for key in PARENT_FLAGS+DESCRIPTORS+FIRE_FLAGS:
            layer=cache.layers['cells/'+key]
            codes=cache.layer_values(layer['id'],None,None)
            assert [layer['categories'][int(x)] for x in codes[:2]]==['False','True']
            assert math.isnan(codes[2])
        for g in GUILDS:
            key='species_guild_scores.'+g
            layer=cache.layers['cells/'+key]
            assert layer['derived_from']=={'field':'species_guild_scores','key':g}
            assert table[key]==[0.,0.,0.]
        assert cache.cell_record(0)['cell']['species_guild_scores']==world['cells'][0]['species_guild_scores']
    finally:
        cache.close()
    assert world==before


@pytest.mark.parametrize('key',VALUES+tuple('species_guild_scores.'+g for g in GUILDS)+('species_habitat_suitability_index','species_guild_richness_count','dominant_species_guild'))
def test_rendered_debug_layers_mask_only_explicitly_unavailable_values(tmp_path,key):
    world=display_world()
    export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    cache=_DebugCache(tmp_path/'cache')
    try:
        values=cache.layer_values('cells/'+key,None,None)
        assert math.isnan(values[0])
        assert values[1:]==[0.,0.]
        layer=cache.layers['cells/'+key]
        assert layer['unavailable_cell_count']==1
        if layer['kind']=='numeric': assert layer['stats']['min']==layer['stats']['max']==0.
    finally:
        cache.close()


def test_unavailable_outlier_is_excluded_from_color_range_without_changing_raw_source(tmp_path):
    world=display_world();world['cells'][0]['primary_productivity_index']=99.
    manifest=export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    layer=next(layer for layer in manifest['layers'] if layer['id']=='cells/primary_productivity_index')
    assert layer['stats']['min']==layer['stats']['max']==0.
    assert pq.read_table(tmp_path/'cache/tables/cells.parquet')['primary_productivity_index'].to_pylist()==[99.,0.,0.]


def test_summary_exposes_parent_score_and_front_coverage_without_species_absence_claim(tmp_path):
    world=display_world()
    world.update(ecosystem_dynamics_model={'model':'heuristic_ecosystem_climate_support_v4'},
                 species_ranges_model={'model':'heuristic_species_parent_support_v3'},
                 wildfire_disturbance_model={'model':'heuristic_wildfire_parent_availability_v4'})
    summary=world['summary']
    summary.update({f+'_cell_count':1 for f in PARENT_FLAGS+DESCRIPTORS+FIRE_FLAGS})
    summary.update(species_score_supported_cell_counts=dict.fromkeys(GUILDS,1),
                   species_composition_status_counts={'complete':1,'unavailable':1},
                   wildfire_unavailable_cell_count=1,wildfire_partial_front_history_count=1,
                   wildfire_unmodelled_adjacent_cell_count=2,wildfire_unmodelled_front_edge_count=3,
                   wildfire_supported_front_edge_count=4)
    path=tmp_path/'summary.md';write_summary_markdown(path,world);text=path.read_text()
    for key in summary: assert key in text
    assert 'complete score coverage can coexist with no range records' in text
    assert 'not evidence of physical containment' in text
    assert 'All-cell means include those zeros' in text


def test_current_producers_export_models_scores_and_full_partial_front_records(tmp_path):
    from pathlib import Path
    from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
    from magic_geo.species_ranges import enrich_world_with_species_ranges
    from magic_geo.wildfire_disturbance import enrich_world_with_wildfire_disturbance
    fixture=Path(__file__).parent/'fixtures/wildfire_parent_availability/supported_legacy_v2_world.json'
    world=json.loads(fixture.read_text())
    world['cells'][2]['temperature_c']=80.
    for cell in world['cells']:
        lon=cell['lon_deg']
        cell.update(boundary_ring=[[0.,lon],[0.,lon+.4],[.4,lon]],biome_confidence_index=.8,
                    reef_growth_index=0.,wetland_extent_index=0.)
    enrich_world_with_ecosystem_dynamics(world)
    enrich_world_with_species_ranges(world)
    enrich_world_with_wildfire_disturbance(world)
    before=deepcopy(world)
    manifest=export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    sections=json.loads((tmp_path/'cache/sections.json').read_text())
    for key in ('ecosystem_dynamics_model','species_ranges_model','wildfire_disturbance_model'):
        assert sections[key]==world[key]
    assert sections['summary']['species_composition_status_counts']==world['summary']['species_composition_status_counts']
    cache=_DebugCache(tmp_path/'cache')
    try:
        family=cache.family_rows('wildfire_spread_histories',limit=100,offset=0,detail='full')
        assert family['rows']==world['wildfire_spread_histories']
        history=family['rows'][0]
        assert history['front_coverage_status']=='partial_unavailable_inputs'
        assert history['unmodelled_front_edges']==[{'from_cell_id':0,'to_cell_id':1}]
        assert history['steps'][0]['unmodelled_front_edges']==history['unmodelled_front_edges']
        assert 'species_guild_scores.canopy_tree' in cache.cell_record(0)['cell']
    finally:
        cache.close()
    assert world==before


def test_all_unavailable_numeric_layers_remain_selectable_without_false_color_stats(tmp_path):
    world=display_world();world['cells']=world['cells'][:1]
    manifest=export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    layer=next(x for x in manifest['layers'] if x['id']=='cells/primary_productivity_index')
    assert 'stats' not in layer
    assert layer['unavailable_cell_count']==1
    cache=_DebugCache(tmp_path/'cache')
    try:
        assert math.isnan(cache.layer_values(layer['id'],None,None)[0])
    finally:
        cache.close()


def test_actual_exported_layer_metadata_and_raw_cells_reach_javascript_formatter(tmp_path):
    import shutil
    import subprocess
    from pathlib import Path
    if shutil.which('node') is None:
        pytest.skip('Node is required for actual frontend helper replay')
    world=display_world()
    manifest=export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    payload=tmp_path/'ui-input.json';payload.write_text(json.dumps({'manifest':manifest,'cells':world['cells']}))
    app=Path(__file__).parents[1]/'src/magic_geo/debug_ui/app.js'
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
const source=fs.readFileSync(process.argv[2],'utf8').replace(/^import .*;\n/gm,'').replace(/main\(\)\.catch\([\s\S]*$/,'');
const context=vm.createContext({THREE:{Vector2:class{constructor(x,y){this.x=x;this.y=y;}}},document:{},window:{},console});
vm.runInContext(source,context);
let checked=0;
for(const layer of input.manifest.layers.filter(x=>x.availability)){
  context.cell=input.cells[0];context.key=layer.name;context.value=layer.derived_from?context.cell[layer.derived_from.field][layer.derived_from.key]:context.cell[layer.name];
  assert.equal(vm.runInContext('formatInspectorValue(cell,key,value)',context),'Unavailable');
  for(const i of [1,2]){
    context.cell=input.cells[i];context.value=layer.derived_from?context.cell[layer.derived_from.field][layer.derived_from.key]:context.cell[layer.name];
    assert.equal(vm.runInContext('formatInspectorValue(cell,key,value)',context),layer.name==='dominant_species_guild'?'none':'0');
  }
  checked++;
}
assert.equal(checked,26);console.log('26 real exported layers agree with inspector availability');
'''
    run=subprocess.run(['node','-e',script,str(payload),str(app)],capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stdout+run.stderr
    assert '26 real exported layers' in run.stdout


def test_python_map_export_uses_the_same_unavailable_values_as_workbench(tmp_path):
    from magic_geo.debug_map_export import export_map_reference
    world=display_world()
    export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    result=export_map_reference(tmp_path/'cache',layer_id='cells/primary_productivity_index',
                                output=tmp_path/'map.png',projection='equirect',width=64,height=32)
    assert result.image_path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    text=result.prompt_path.read_text()
    assert 'Unavailable estimates use the missing-data color' in text
    assert 'supported zero values remain visible' in text
    # The exported legend counts the unknown cell separately from two real zeros.
    missing_row=next(line for line in text.splitlines() if line.startswith('| #292e36'))
    assert '| 1 |' in missing_row


def test_availability_count_includes_declared_unavailable_already_null_values(tmp_path):
    world=display_world()
    world['cells'][1]['primary_productivity_supported']=False
    world['cells'][1]['primary_productivity_index']=None
    manifest=export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    layer=next(x for x in manifest['layers'] if x['id']=='cells/primary_productivity_index')
    assert layer['unavailable_cell_count']==2
    assert layer['stats']['min']==layer['stats']['max']==0.


def test_all_unavailable_python_map_codex_has_only_an_unavailable_legend(tmp_path):
    from PIL import Image
    from magic_geo.debug_map_export import export_map_reference
    world=display_world();world['cells']=world['cells'][:1]
    world['cells'][0]['boundary_ring']=[[-40.,-80.],[-40.,80.],[40.,0.]]
    export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    result=export_map_reference(tmp_path/'cache',layer_id='cells/primary_productivity_index',
                                output=tmp_path/'unavailable.png',projection='equirect',width=64,height=32)
    assert result.image_path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    with Image.open(result.image_path) as image:
        pixels=image.convert('RGB').tobytes()
        colors=set(zip(pixels[0::3],pixels[1::3],pixels[2::3]))
    assert (41,46,54) in colors  # The unavailable region is actually rasterized.
    assert colors <= {(41,46,54),(16,20,26)}  # Missing data and background only.
    text=result.prompt_path.read_text()
    assert 'No available estimates in this layer slice' in text
    assert 'Current slice: 0 finite cells; no available-value range.' in text
    assert 'Viridis normalized over' not in text
    assert '| Encoded value | Scale position |' not in text
    missing_row=next(line for line in text.splitlines() if line.startswith('| #292e36'))
    assert '| 1 | 100.00% |' in missing_row


def test_masked_codex_range_is_available_values_while_raw_and_legacy_ranges_remain_distinct(tmp_path):
    from magic_geo.debug_map_export import build_color_codex
    world=display_world();world['cells'][0]['primary_productivity_index']=9.25
    export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    cache=_DebugCache(tmp_path/'cache')
    try:
        layer=cache.layers['cells/primary_productivity_index']
        values=cache.layer_values(layer['id'],None,None)
        text=build_color_codex(layer,values)
        assert 'Complete layer/time-axis available-value range: 0 index to 0 index.' in text
        assert 'Complete layer/time-axis raw range:' not in text
        assert 'Current slice: 2 finite cells' in text
        assert 'Viridis normalized over' in text  # Supported and legacy zeros remain visible.
        assert cache.cell_record(0)['cell']['primary_productivity_index']==9.25
        # The preexisting undeclared layer contract retains its old raw-range wording.
        legacy={k:v for k,v in layer.items() if k!='availability'}
        legacy['stats']={'min':0.,'max':9.25,'p2':0.,'p98':9.25}
        assert 'Complete layer/time-axis raw range: 0 index to 9.25 index.' in build_color_codex(legacy,[9.25,0.,0.])
    finally:
        cache.close()


@pytest.mark.parametrize('version', ['heuristic_ecosystem_climate_support_v3', 'heuristic_ecosystem_climate_support_v4'])
@pytest.mark.parametrize('unsupported_temperature', [-18., 80.])
def test_known_v3_and_current_v4_fishery_maps_use_derived_parent_support(tmp_path,version,unsupported_temperature):
    from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS, validate_aquatic_climate_support
    from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
    world=display_world()
    for cell,temperature in zip(world['cells'],[unsupported_temperature,18.,18.]):
        cell.update(temperature_c=temperature,is_water=True,is_lake=False,water_body_type='ocean')
    # These are explicitly historical v3/v4 display controls. The toy already
    # contains availability fields, so it is not an undeclared new E5 input.
    world['ecosystem_dynamics_model']=deepcopy(_EXPECTED_MODELS['heuristic_ecosystem_climate_support_v4'])
    enrich_world_with_ecosystem_dynamics(world)
    assert world['ecosystem_dynamics_model']==_EXPECTED_MODELS['heuristic_ecosystem_climate_support_v4']
    if version.endswith('_v3'):
        # On these aquatic inputs the v3 and v4 equations/support are identical.
        # Remove only the additive v4 fields to preserve the known v3 contract.
        for cell in world['cells']:
            for flag in PARENT_FLAGS:
                cell.pop(flag,None)
        for flag in PARENT_FLAGS:
            world['summary'].pop(flag+'_cell_count',None)
        world['ecosystem_dynamics_model']=deepcopy(_EXPECTED_MODELS[version])
    # A supplied supported zero is usable independently of whether a renewable
    # record clears that other producer's threshold. This tests display inputs.
    world['cells'][1]['fishery_productivity_index']=0.
    assert validate_aquatic_climate_support(world)==[]
    if unsupported_temperature==-18.:
        assert world['cells'][0]['fishery_climate_supported'] is True
        assert world['cells'][0]['fishery_productivity_supported'] is False
    before=deepcopy(world)
    export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    cache=_DebugCache(tmp_path/'cache')
    try:
        layer=cache.layers['cells/fishery_productivity_index']
        assert layer['availability']=={'field':'fishery_productivity_supported','unavailable_when':'false'}
        values=cache.layer_values(layer['id'],None,None)
        assert math.isnan(values[0]) and values[1]==0. and values[2]>0.
        assert layer['stats']['min']==0.
        assert cache.cell_record(0)['cell']['fishery_productivity_index']==0.
    finally:
        cache.close()
    assert world==before


def test_undeclared_legacy_fishery_map_keeps_its_zero_values(tmp_path):
    world=display_world()
    for cell in world['cells']:
        cell['fishery_productivity_index']=0.
    export_debug_cache(world,tmp_path/'cache',include_vtu=False)
    cache=_DebugCache(tmp_path/'cache')
    try:
        layer=cache.layers['cells/fishery_productivity_index']
        assert 'availability' not in layer
        assert cache.layer_values(layer['id'],None,None)==[0.,0.,0.]
    finally:
        cache.close()
