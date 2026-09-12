"""Actual retained full/geo chain exports; never invokes native generation."""
from copy import deepcopy
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess

import pyarrow.parquet as pq
import pytest

from magic_geo.debug_export import export_debug_cache
from magic_geo.debug_server import _DebugCache
from magic_geo.io import write_cells_csv, write_json, write_summary_markdown
from support.prescribed_natural_public_worlds import (
    current_world_readonly, archived_world, OWNERSHIP,
)

MODEL_FIELDS = ("ecosystem_dynamics_model", "species_ranges_model", "wildfire_disturbance_model")
NATIVE_FIELDS = ("climate_model", "climate_energy_model", "climate_energy_balance_records",
                 "climate_energy_forcing_intervals", "climate_energy_transport_edges")
CHILD_FIELDS = tuple(dict.fromkeys(k for stage in ("ecosystem", "species", "fire")
                                 for k in OWNERSHIP[stage]["cell_fields"]))
SUMMARY_FIELDS = tuple(dict.fromkeys(k for stage in ("ecosystem", "species", "fire")
                                   for k in OWNERSHIP[stage]["summary_fields"]))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@pytest.fixture(scope="module", params=[("current", "full"), ("current", "geo"), ("historical", "full")])
def retained_export(request, tmp_path_factory):
    version, scope = request.param
    source = current_world_readonly(scope) if version == "current" else archived_world(scope)
    before = canonical(source)
    out = tmp_path_factory.mktemp(version + "-" + scope)
    write_json(out / "world.json", source)
    write_cells_csv(out / "cells.csv", source)
    write_summary_markdown(out / "summary.md", source)
    manifest = export_debug_cache(source, out / "cache", include_vtu=False)
    assert canonical(source) == before
    assert json.loads((out / "world.json").read_text()) == source
    (out / "source-identity.json").write_text(json.dumps({
        "version": version, "scope": scope,
        "canonical_world_sha256": hashlib.sha256(before).hexdigest(),
        "models": {k: source[k] for k in MODEL_FIELDS},
        "cell_count": len(source["cells"]),
        "layer_count": len(manifest["layers"]),
        "native_sha256": {k: hashlib.sha256(canonical(source[k])).hexdigest() for k in NATIVE_FIELDS},
    }, indent=2) + "\n")
    return version, scope, source, out, manifest


def test_actual_csv_and_parquet_preserve_owned_false_zero_and_scores(retained_export):
    _, _, source, out, _ = retained_export
    with (out / "cells.csv").open(newline="") as file:
        reader = csv.DictReader(file)
        rows, fields = list(reader), reader.fieldnames
    assert len(fields) == len(set(fields))
    assert set(CHILD_FIELDS).issubset(fields)
    table = pq.read_table(out / "cache/tables/cells.parquet").to_pydict()
    for index, cell in enumerate(source["cells"]):
        for field in CHILD_FIELDS:
            value = cell[field]
            if isinstance(value, (dict, list)):
                assert json.loads(rows[index][field]) == value
            elif type(value) is bool:
                assert rows[index][field] == str(value)
                assert table[field][index] is value
            elif isinstance(value, (int, float)):
                assert float(rows[index][field]) == value
                assert table[field][index] == value
            else:
                assert rows[index][field] == value
                assert table[field][index] == value
        for guild, value in cell["species_guild_scores"].items():
            assert table["species_guild_scores." + guild][index] == value


def test_actual_cache_preserves_models_full_records_and_native_sections(retained_export):
    _, _, source, out, _ = retained_export
    sections = json.loads((out / "cache/sections.json").read_text())
    for key in MODEL_FIELDS + ("climate_model", "climate_energy_model"):
        assert sections[key] == source[key]
    for key in SUMMARY_FIELDS:
        assert sections["summary"][key] == source["summary"][key]
    cache = _DebugCache(out / "cache")
    try:
        for family in ("species_range_records", "wildfire_spread_histories",
                       "climate_energy_balance_records", "climate_energy_forcing_intervals",
                       "climate_energy_transport_edges"):
            rows = cache.family_rows(family, limit=10000, offset=0, detail="full")
            assert rows["rows"] == source[family]
        for i in (0, len(source["cells"]) - 1):
            cell = cache.cell_record(source["cells"][i]["id"])["cell"]
            assert {k: cell[k] for k in CHILD_FIELDS} == {k: source["cells"][i][k] for k in CHILD_FIELDS}
    finally:
        cache.close()


def test_actual_layer_masks_match_raw_flags_and_keep_supported_zero(retained_export):
    _, _, source, out, manifest = retained_export
    cache = _DebugCache(out / "cache")
    report = {}
    try:
        for layer in manifest["layers"]:
            if layer["source"] != "cells" or "availability" not in layer:
                continue
            field, rule = layer["availability"]["field"], layer["availability"]["unavailable_when"]
            expected_missing = [i for i, c in enumerate(source["cells"])
                                if (c.get(field) is False if rule == "false"
                                    else type(c.get(field)) is int and c[field] == 0)]
            values = cache.layer_values(layer["id"], None, None)
            assert layer.get("unavailable_cell_count", 0) == len(expected_missing)
            assert [i for i, value in enumerate(values) if math.isnan(value)] == expected_missing
            zeros = sum(value == 0.0 for value in values if math.isfinite(value))
            report[layer["id"]] = {"unavailable": len(expected_missing), "visible_zero": zeros}
        assert report and any(v["unavailable"] for v in report.values())
        assert any(v["visible_zero"] for v in report.values())
    finally:
        cache.close()
    (out / "layer-availability.json").write_text(json.dumps(report, indent=2) + "\n")


def test_actual_summary_distinguishes_activity_scope_from_coverage(retained_export):
    version, _, _, out, _ = retained_export
    text = (out / "summary.md").read_text()
    assert "complete score coverage can coexist with no range records" in text
    assert "not evidence of physical containment" in text
    assert "All-cell means include those zeros" in text
    assert ("Ecosystem activity scope:" in text) == (version == "current")
    assert ("Wildfire activity scope:" in text) == (version == "current")
    if version == "current":
        assert "Human activity is outside this scenario" in text
        assert "not a calibrated ignition frequency" in text


def test_actual_exported_values_reach_direct_node_inspector(retained_export):
    _, _, source, out, manifest = retained_export
    payload = out / "node-input.json"
    payload.write_text(json.dumps({"manifest": manifest, "cells": source["cells"],
                                  "histories": source["wildfire_spread_histories"]}))
    app = Path(__file__).parents[1] / "src/magic_geo/debug_ui/app.js"
    script = r'''
(async()=>{
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
const source=fs.readFileSync(process.argv[2],'utf8').replace(/^import .*;\n/gm,'').replace(/main\(\)\.catch\([\s\S]*$/,'');
const ctx=vm.createContext({THREE:{Vector2:class{constructor(x,y){this.x=x;this.y=y;}}},document:{},window:{},console});vm.runInContext(source,ctx);
let checked=0,unavailable=0,zero=0;
for(const layer of input.manifest.layers.filter(x=>x.source==='cells'&&x.availability)) {
  for(const cell of input.cells){
    const flag=cell[layer.availability.field],missing=layer.availability.unavailable_when==='false'?flag===false:flag===0;
    ctx.cell=cell;ctx.key=layer.name;ctx.value=layer.derived_from?cell[layer.derived_from.field][layer.derived_from.key]:cell[layer.name];
    const text=vm.runInContext('formatInspectorValue(cell,key,value)',ctx);
    if(missing){assert.match(text,/unavailable/i);unavailable++;}
    else {assert.doesNotMatch(text,/unavailable/i);if(ctx.value===0){assert.match(text,/^0(?:$| \(partial score coverage\)$)/);zero++;}}
    checked++;
  }
}
assert.ok(unavailable>0&&zero>0);
ctx.cell=input.cells[0];assert.match(vm.runInContext('speciesAvailabilityMarkup(cell)',ctx),/habitat-applicable guilds/);
ctx.histories=input.histories;const text=vm.runInContext('familyAvailabilityMarkup("wildfire_spread_histories",histories,"full")',ctx);
assert.match(text,/does not demonstrate physical containment/);
const docs=fs.readFileSync(process.argv[3],'utf8');
const {describeLayer}=await import('data:text/javascript;base64,'+Buffer.from(docs).toString('base64'));
for(const name of ['ecosystem_disturbance_pressure_index','wildfire_ignition_potential_index']){
  const doc=describeLayer({id:'cells/'+name,name,source:'cells',kind:'numeric'});
  assert.match(doc.description,/prescribed natural/i);
  assert.match(doc.description,/historical models include/i);
}
console.log(JSON.stringify({checked,unavailable,visible_zero:zero,scope:'direct helper execution, no browser interaction'}));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run(["node", "-e", script, str(payload), str(app), str(app.with_name("layer_docs.js"))], text=True, capture_output=True, timeout=20)
    (out / "node-result.txt").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_e4_e5_keep_same_support_declarations_without_overwriting_changed_values():
    old, new = archived_world(), current_world_readonly()
    flags = [key for key in CHILD_FIELDS if all(type(c[key]) is bool for c in old["cells"])]
    assert flags
    for field in flags:
        assert [c[field] for c in old["cells"]] == [c[field] for c in new["cells"]]
    assert any(a["ecosystem_disturbance_pressure_index"] != b["ecosystem_disturbance_pressure_index"]
               for a, b in zip(old["cells"], new["cells"]))
