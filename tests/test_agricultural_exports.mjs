import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source=readFileSync(new URL('../src/magic_geo/debug_ui/app.js',import.meta.url),'utf8')
  .replace(/^import .*;\n/gm,'').replace(/main\(\)\.catch\([\s\S]*$/,'');
const context=vm.createContext({THREE:{Vector2:class{constructor(x,y){this.x=x;this.y=y;}}},document:{},window:{},console});
vm.runInContext(source,context);
const run=(code)=>vm.runInContext(code,context);
const docsText=readFileSync(new URL('../src/magic_geo/debug_ui/layer_docs.js',import.meta.url),'utf8');
const {describeLayer}=await import('data:text/javascript;base64,'+Buffer.from(docsText).toString('base64'));

for(const [key,flag] of [['agricultural_potential_index','agricultural_potential_supported'],
                        ['mining_potential_index','mining_surface_applicable']]){
  test(`${key}: explicit false hides a sentinel; true zero and legacy zero remain visible`,()=>{
    context.key=key;
    for(const [support,expected] of [[false,'Unavailable'],[true,'0'],[undefined,'0']]){
      context.cell=support===undefined?{}:{[flag]:support};
      assert.equal(run('formatInspectorValue(cell,key,0)'),expected);
    }
  });
}
test('mining display does not consume agricultural climate or productivity support',()=>{
  context.cell={agricultural_climate_supported:false,agricultural_potential_supported:false,
    primary_productivity_supported:false,mining_surface_applicable:true};
  assert.equal(run('formatInspectorValue(cell,"mining_potential_index",0.75)'),'0.75');
});
test('inspector distinguishes thermal estimate limits from surface extraction scope',()=>{
  context.cell={agricultural_potential_index:0,mining_potential_index:0,
    agricultural_potential_supported:false,mining_surface_applicable:false};
  const text=run('landUseAvailabilityMarkup(cell)');
  assert.match(text,/Agriculture estimate unavailable/);
  assert.match(text,/does not establish crop failure/);
  assert.match(text,/Surface mining is not applicable to water-covered cells/);
  assert.match(text,/Geological deposits may still be present/);
});
test('supported zero and missing historical flags have distinct explanations',()=>{
  context.cell={agricultural_potential_index:0,mining_potential_index:0,
    agricultural_potential_supported:true,mining_surface_applicable:true};
  const text=run('landUseAvailabilityMarkup(cell)');
  assert.match(text,/supported zero is valid/);
  assert.match(text,/does not establish complete mining inputs or economic access/);
  context.cell={agricultural_potential_index:0,mining_potential_index:0};
  assert.match(run('landUseAvailabilityMarkup(cell)'),/availability is undeclared/);
  assert.match(run('landUseAvailabilityMarkup(cell)'),/surface applicability is undeclared/);
  assert.match(run('landUseAvailabilityMarkup(cell)'),/legacy value remains visible/);
});
test('absent land use does not add a panel or interpolate malformed flag content',()=>{
  for(const cell of [{},null,[],{temperature_c:20}]){
    context.cell=cell;assert.equal(run('landUseAvailabilityMarkup(cell)'),'');
  }
  context.cell={agricultural_potential_index:0,agricultural_potential_supported:'<img onerror=bad>'};
  assert.doesNotMatch(run('landUseAvailabilityMarkup(cell)'),/<img|onerror/);
});
for(const name of ['agricultural_habitat_applicable','agricultural_climate_supported',
                  'agricultural_potential_supported','mining_surface_applicable']){
  test(`${name} has explicit help`,()=>{
    const doc=describeLayer({id:'cells/'+name,name,source:'cells',kind:'categorical_bool',categories:['False','True']});
    assert.notEqual(doc.role,'measurement');assert.ok(doc.description.length>70);
    if(name==='agricultural_climate_supported')assert.match(doc.description,/-9 and 43 °C.*model limit/);
    if(name==='mining_surface_applicable')assert.match(doc.description,/does not certify complete mining inputs or economic access/);
  });
}

if(process.argv[2]){
  const input=JSON.parse(readFileSync(process.argv[2],'utf8'));
  for(const [key,missing] of [['agricultural_potential_index',[0,2]],['mining_potential_index',[0]]]){
    const layer=input.manifest.layers.find(x=>x.id==='cells/'+key);
    assert.equal(layer.availability.unavailable_when,'false');
    assert.equal(layer.unavailable_cell_count,missing.length);
    for(let i=0;i<input.cells.length;i++){
      context.cell=input.cells[i];context.key=key;context.value=context.cell[key];
      assert.equal(run('formatInspectorValue(cell,key,value)'),missing.includes(i)?'Unavailable':'0');
    }
  }
  console.log('exported agricultural and mining layers agree with inspector');
}
