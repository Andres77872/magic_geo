import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
const text=readFileSync(new URL('../src/magic_geo/debug_ui/layer_docs.js',import.meta.url),'utf8');
const {describeLayer}=await import('data:text/javascript;base64,'+Buffer.from(text).toString('base64'));
function doc(name,extra={}) { return describeLayer({id:'cells/'+name,name,source:'cells',kind:'numeric',stats:{min:0,max:.2,p2:0,p98:.2},...extra}); }
for (const [name,expected] of [
 ['aquifer_natural_limitation_index',/Natural limitation proxy.*Independent of settlement.*structural zero/],
 ['groundwater_hydraulic_head_m',/Diagnostic hydraulic head.*No Darcy/],
 ['aquifer_productivity_index',/diagnostic.*no measured or sustainable yield/],
 ['baseflow_support_index',/Annual diagnostic.*Dry-season flow reliability is unresolved/],
 ['groundwater_retained_storage_km3_y',/annual recharge-partition remainder.*not a stored-water stock/],
 ['aquifer_extraction_risk_index',/Historical v1.*settlement suitability.*absent in natural v2/],
]) test(name,()=>assert.match(doc(name).description,expected));
test('remainder unit is annual flow and known zero stats are retained',()=>{
 const result=doc('groundwater_retained_storage_km3_y');assert.equal(result.unit,'km³/year');assert.equal(result.stats.min,'0');
});
test('existing ecology availability explanation is unaffected',()=>{
 assert.match(doc('primary_productivity_index',{availability:{field:'primary_productivity_supported',unavailable_when:'false'}}).notes.join(' '),/Supported zero values remain visible/);
});
