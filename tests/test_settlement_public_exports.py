"""Display-only mixed inputs plus retained transport exports; no world creation."""
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import subprocess

import pyarrow.parquet as pq
import pyarrow as pa
import pytest

from magic_geo.debug_export import export_debug_cache
from magic_geo.debug_server import _DebugCache
from magic_geo.io import write_cells_csv, write_summary_markdown
from magic_geo.public_estimate_display import applicability_fields


def mixed_display():
    # A renderer fixture, not a fabricated scientific parent certificate.
    cells = []
    for i, (water, supported, value) in enumerate(((False, False, None), (False, True, 0.), (True, False, 0.), (False, True, .8))):
        cells.append(dict(id=i, lat_deg=0., lon_deg=float(i), area_km2=1.,
            boundary_ring=[[0., i], [0., i + .4], [.4, i]],
            is_water=water, is_lake=False, settlement_score=0. if value is None else value,
            settlement_climate_supported=supported, settlement_climate_temperature_c=90. if not supported else 15.,
            harbor_suitability_index=None, harbor_suitability_supported=False,
            mining_surface_applicable=not water, mining_potential_supported=water or supported,
            mining_potential_index=value))
    return dict(name='Scoped display controls', cells=cells,
        summary=dict(port_site_selection_complete=False, mean_resource_economic_viability_index=None,
                     navigability_supported_cell_count=2, mining_zone_selection_complete=False),
        port_sites=[], mining_zones=[],
        resource_deposits=[dict(id=i, accessibility_index=None, accessibility_supported=False,
                               economic_viability_index=None, economic_viability_supported=False,
                               reserve_potential_index=.7, geographic_accessibility_baseline_index=.4)
                           for i in range(2)],
        population_regions=[dict(id=i, estimated_population=None, population_estimate_available=False,
                                 carrying_capacity=0., capacity_estimate_available=True) for i in range(2)],
        population_histories=[dict(id=i, initial_population=None, estimate_availability={'initial_population': False}, steps=[])
                              for i in range(2)])


def test_mixed_raw_columns_layers_and_separate_surface_counts(tmp_path):
    world = mixed_display(); before = deepcopy(world)
    manifest = export_debug_cache(world, tmp_path, include_vtu=False)
    table = pq.read_table(tmp_path/'tables/cells.parquet').to_pydict()
    assert table['mining_potential_index'] == [None, 0., 0., .8]
    assert table['settlement_score'] == [0., 0., 0., .8]
    assert table['harbor_suitability_index'] == [None]*4
    cache = _DebugCache(tmp_path)
    try:
        for name in ('mining_potential_index', 'settlement_score'):
            layer = cache.layers['cells/'+name]
            assert layer['inapplicable_cell_count'] == layer['unavailable_cell_count'] == 1
            values = cache.layer_values(layer['id'], None, None)
            assert math.isnan(values[0]) and values[1] == 0. and math.isnan(values[2]) and values[3] == .8
            assert layer['stats']['min'] == 0. and layer['stats']['max'] == .8
        layer = cache.layers['cells/harbor_suitability_index']
        assert 'stats' not in layer and layer['unavailable_cell_count'] == 4
        assert all(math.isnan(value) for value in cache.layer_values(layer['id'], None, None))
        assert cache.cell_record(0)['cell']['mining_potential_index'] is None
        assert cache.cell_record(1)['cell']['mining_potential_index'] == 0.
        for family, field in (('resource_deposits','accessibility_index'),('population_regions','estimated_population'),('population_histories','initial_population')):
            payload = cache.family_rows(family, 10, 0, 'scalars')
            assert [row[field] for row in payload['rows']] == [None, None]
        history = cache.family_rows('population_histories',10,0,'scalars')['rows'][0]
        assert history['estimate_availability.initial_population'] is False
        for family in ('port_sites', 'mining_zones'):
            payload = cache.family_rows(family,10,0,'full')
            assert payload['rows'] == [] and payload['availability']['complete'] is False
    finally:
        cache.close()
    assert world == before


def test_all_null_declared_types_and_unknown_route_lists_survive_export(tmp_path):
    world = mixed_display()
    world['snapshot_region_display_controls'] = [dict(id=i, geometry_quality=None, geometry_estimate_available=False) for i in range(2)]
    for family, field in [('speaker_population_histories', 'high_contact_speaker_history'),
                          ('market_inventory_histories', 'high_inventory_stress')]:
        world[family] = [dict(id=i, **{field: None}, estimate_availability={field: False}) for i in range(2)]
    world['routes'] = [dict(id=i, route_corridor_id=None, route_path_supported=False,
                            route_corridor_type=None, route_corridor_diagnostics_supported=False,
                            path_cell_ids=None) for i in range(2)]
    manifest = export_debug_cache(world, tmp_path, include_vtu=False)
    for family, field, expected in [
        ('snapshot_region_display_controls', 'geometry_quality', pa.float64()),
        ('speaker_population_histories', 'high_contact_speaker_history', pa.bool_()),
        ('market_inventory_histories', 'high_inventory_stress', pa.bool_()),
        ('routes', 'route_corridor_id', pa.int64()),
    ]:
        entry = manifest['families'][family]
        table = pq.read_table(tmp_path/entry.get('scalars_parquet', entry.get('parquet')))
        assert table.schema.field(field).type == expected
        assert table[field].to_pylist() == [None, None]
    cache = _DebugCache(tmp_path)
    try:
        rows = cache.family_rows('routes', 10, 0, 'full')['rows']
        assert rows == world['routes']
        assert all('path_cell_ids' in row and row['path_cell_ids'] is None for row in rows)
    finally:
        cache.close()


def test_empty_market_families_retain_selection_and_field_specific_coverage(tmp_path):
    world = mixed_display()
    # These are presentation declarations only; no scientific replay is claimed.
    world['native_social_availability_model'] = {'model_type': 'native_settlement_source_complete_social_estimates_v1'}
    world['summary']['market_order_selection_complete'] = False
    families = ['market_agent_orders', 'route_capacity_constraints', 'market_clearing_records',
                'market_price_iterations', 'market_inventory_histories']
    world.update({family: [] for family in families})
    manifest = export_debug_cache(world, tmp_path, include_vtu=False)
    cache = _DebugCache(tmp_path)
    try:
        for family in families:
            assert manifest['families'][family]['kind'] == 'empty'
            payload = cache.family_rows(family, 10, 0, 'full')
            assert payload['rows'] == []
            if family == 'market_agent_orders':
                assert payload['availability']['complete'] is False
            else:
                assert payload['availability'] == {'complete': None, 'scope': 'field_specific_availability'}
    finally:
        cache.close()


@pytest.mark.parametrize('rule', [None, {}, {'kind':'unknown'}, {'kind':'native_exposed_land_v1','extra':0}, {'kind':'boolean_field_v1','field':'arbitrary'}])
def test_public_surface_descriptor_rejects_unrecognized_or_partial_rules(rule):
    with pytest.raises(ValueError): applicability_fields(rule)


@pytest.mark.parametrize('mutation', [
    lambda layer:layer['applicability'].update(extra=0),
    lambda layer:layer.update(inapplicable_cell_count=True),
    lambda layer:layer.update(unavailable_cell_count=5),
    lambda layer:layer.update(inapplicable_cell_count=3,unavailable_cell_count=2),
    lambda layer:layer['availability'].update(operator='or'),
])
def test_cache_rejects_forged_display_policy_and_count_metadata(tmp_path,mutation):
    export_debug_cache(mixed_display(),tmp_path,include_vtu=False)
    path=tmp_path/'manifest.json';manifest=json.loads(path.read_text())
    layer=next(row for row in manifest['layers'] if row['id']=='cells/mining_potential_index')
    mutation(layer);path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):_DebugCache(tmp_path)


def test_static_map_export_uses_the_actual_mask_and_separate_surface_legend(tmp_path):
    from magic_geo.debug_map_export import export_map_reference
    export_debug_cache(mixed_display(),tmp_path/'cache',include_vtu=False)
    result=export_map_reference(tmp_path/'cache',layer_id='cells/mining_potential_index',output=tmp_path/'map.png',projection='equirect',width=64,height=32)
    assert result.image_path.read_bytes().startswith(b'\x89PNG')
    text=result.prompt_path.read_text()
    assert '1 inapplicable cells and 1 unavailable estimates' in text
    assert 'supported zero values remain visible' in text
    result=export_map_reference(tmp_path/'cache',layer_id='cells/harbor_suitability_index',output=tmp_path/'empty.png',projection='equirect',width=64,height=32)
    assert 'No numeric color scale is inferred' in result.prompt_path.read_text()


def test_legacy_and_new_csv_are_distinct_with_schema_and_nullable_summary(tmp_path):
    world=mixed_display();world['cells'].append(dict(id=4,settlement_score=0.,mining_potential_index=0.))
    target=tmp_path/'cells.csv';write_cells_csv(target,world)
    rows=list(csv.DictReader(target.open()))
    assert [r['mining_potential_index'] for r in rows] == ['', '0.0', '0.0', '0.8', '0.0']
    assert [r['mining_potential_supported'] for r in rows] == ['False','True','True','True','']
    assert rows[2]['is_water']=='True' and rows[2]['settlement_climate_supported']=='False'
    schema=json.loads(target.with_suffix('.csv.schema.json').read_text())
    assert schema['schema']=='magic_geo_cell_csv_estimate_profile_v1'
    assert schema['boolean_lexical_values']=={'true':'True','false':'False'}
    assert 'raw JSON' in schema['empty_field_policy']
    write_summary_markdown(tmp_path/'summary.md',world)
    text=(tmp_path/'summary.md').read_text()
    assert '`mean_resource_economic_viability_index`: Unavailable' in text
    assert '`port_site_selection_complete`: False' in text


def test_actual_export_payload_reaches_js_inspector_table_family_and_codex(tmp_path):
    world=mixed_display();manifest=export_debug_cache(world,tmp_path,include_vtu=False)
    cache=_DebugCache(tmp_path)
    try:
        payload={'cells':[cache.cell_record(i)['cell'] for i in range(4)],
                 'layer':cache.layers['cells/mining_potential_index'],
                 'values':cache.layer_values('cells/mining_potential_index',None,None),
                 'family':cache.family_rows('port_sites',10,0,'full')}
    finally:cache.close()
    payload['values']=[None if math.isnan(v) else v for v in payload['values']]
    (tmp_path/'payload.json').write_text(json.dumps(payload))
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8').replace(/^import .*;\n/gm,'').replace(/main\(\)\.catch\([\s\S]*$/,'');
const payload=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const context={THREE:{Vector2:class{constructor(x,y){this.x=x;this.y=y;}}},payload,console,window:{},document:{querySelector:()=>({})}};
vm.createContext(context);vm.runInContext(source,context);
const run=code=>vm.runInContext(code,context);
assert.match(run("formatInspectorValue(payload.cells[0],'settlement_score',0)"),/Unavailable/);
assert.equal(run("formatInspectorValue(payload.cells[1],'settlement_score',0)"),'0');
assert.match(run("formatInspectorValue(payload.cells[2],'settlement_score',0)"),/0.*structural water.*not applicable/);
assert.equal(run("formatInspectorValue(payload.cells[0],'mining_potential_index',null)"),'Unavailable');
assert.match(run("formatInspectorValue(payload.cells[2],'mining_potential_index',0)"),/0.*not applicable/);
assert.match(run("familyAvailabilityMarkup('port_sites', [], 'full', payload.family.availability)"),/Selection incomplete/);
assert.match(run("tableMarkup([{estimated_population:null,population_estimate_available:false}])"),/Unavailable/);
assert.match(run("tableMarkup([{initial_population:null,'estimate_availability.initial_population':false}])"),/Unavailable/);
assert.match(run("familyAvailabilityMarkup('port_sites', [], 'full', {complete:true})"),/no records selected/);
assert.match(run("familyAvailabilityMarkup('port_sites', [], 'full', {complete:null})"),/undeclared/);
assert.doesNotThrow(()=>run("validateDisplayMetadata({world:{cell_count:4},layers:[payload.layer]})"));
assert.throws(()=>run("validateDisplayMetadata({world:{cell_count:4},layers:[{...payload.layer,unavailable_cell_count:true}]})"),/Invalid/);
assert.throws(()=>run("validateDisplayMetadata({world:{cell_count:4},layers:[{...payload.layer,applicability:{kind:'native_exposed_land_v1',extra:0}}]})"),/Invalid/);
assert.match(run("objectTableMarkup({estimated_world_population:null,native_social_summary_availability:{estimated_world_population:false}})"),/Unavailable/);
assert.equal(run("formatInspectorValue({route_path_supported:false},'route_corridor_id',null)"),'Unavailable');
assert.equal(run("formatInspectorValue({route_path_supported:true},'route_corridor_id',-1)"),'-1');
assert.equal(run("formatInspectorValue({route_path_supported:true},'route_corridor_id',0)"),'0');
assert.equal(run("formatInspectorValue({estimate_availability:{high_inventory_stress:true}},'high_inventory_stress',false)"),'false');
console.log('18 exported-payload JS controls passed');
'''
    source=Path(__file__).parents[1]/'src/magic_geo/debug_ui/app.js'
    result=subprocess.run(['node','-e',script,str(source),str(tmp_path/'payload.json')],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert '18 exported-payload' in result.stdout
