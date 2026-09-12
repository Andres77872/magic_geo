// Exercise the real workbench handlers with controlled HTTP completion order.
// The small DOM stand-in keeps these race regressions independent of WebGL.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../src/magic_geo/debug_ui/app.js', import.meta.url), 'utf8')
  .replace(/^import .*;\n/gm, '')
  .replace(/main\(\)\.catch\([\s\S]*$/, '');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function element() {
  const children = [];
  const classes = new Set();
  let html = '';
  return {
    value: '', disabled: false, textContent: '', className: '',
    get innerHTML() { return html; },
    set innerHTML(value) { html = value; children.length = 0; },
    dataset: {}, children, options: children,
    classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name), contains: (name) => classes.has(name) },
    appendChild(child) { children.push(child); },
    querySelector() { return null; }, querySelectorAll() { return []; },
    checkValidity() { return true; }, focus() {},
  };
}

function seasonalSchema() {
  return {
    $id: 'urn:magic-geo:schema:world-config:v2',
    'x-magic-geo': {
      schema_version: 2,
      profiles: ['earthlike', 'smoke', 'dry'].map((name) => ({ name, description: `${name} physical inputs`, values: { config_version: 2 } })),
    },
    required: ['config_version'],
    properties: {
      config_version: { type: 'integer', const: 2, default: 2, description: 'Current configuration version.' },
      climate: { $ref: '#/$defs/Climate', description: 'Prescribed seasonal energy settings.' },
    },
    $defs: {
      Climate: { type: 'object', title: 'Climate defaults', properties: {
        reference_infrared_optical_depth: { type: 'number', default: 1, minimum: 0, description: 'Gray infrared opacity before greenhouse scaling.' },
        precipitation_scale: { type: 'number', minimum: 0, maximum: 10, default: 1 },
        months: { type: 'integer', const: 12, default: 12 },
      } },
    },
  };
}

function seasonalProfiles() {
  return { profiles: ['earthlike', 'smoke', 'dry'].map((name) => ({ name })), default: 'earthlike' };
}

test('marine distance inspector distinguishes absent source from real zero and undeclared null', () => {
  const app = workbench();
  app.context.cell = { marine_distance_status: 'no_marine_source' };
  assert.equal(app.run("formatInspectorValue(cell, 'distance_to_marine_water_km', null)"), 'No marine source (distance undefined)');
  app.context.cell = { marine_distance_status: 'reachable_marine' };
  assert.equal(app.run("formatInspectorValue(cell, 'distance_to_marine_water_km', 0)"), '0');
  app.context.cell = {};
  assert.equal(app.run("formatInspectorValue(cell, 'distance_to_marine_water_km', null)"), app.run('formatValue(null)'));
});

test('marine distance no-source legend and export guide do not invent a zero-to-one ramp', () => {
  const app = workbench();
  app.get('#legend-ramp').style = {};
  app.context.layer = { id: 'cells/distance_to_marine_water_km', source: 'cells', name: 'distance_to_marine_water_km', kind: 'numeric',
    marine_distance: { status_field: 'marine_distance_status', no_source_cell_count: 2 } };
  app.run('updateLegend(layer)');
  assert.equal(app.get('#legend-ramp').style.display, 'none');
  assert.equal(app.get('#legend-min').textContent, 'No marine source');
  assert.equal(app.get('#legend-max').textContent, '');
  app.context.snapshot = { layer: app.context.layer };
  app.context.doc = { unit: 'km' };
  app.context.summary = { total: 2, missingCount: 2, finiteCount: 0 };
  assert.equal(app.run('buildNumericCodex(snapshot, doc, summary)'), 'No marine source in this world. Distance is undefined, not zero. No numeric color scale is inferred.\n\nNeutral cells indicate the absence of a marine distance source, not missing rainfall or total humidity.');
});

test('marine distance display metadata rejects invalid counts and false layer associations', () => {
  const app = workbench();
  const layer = { id: 'cells/distance_to_marine_water_km', source: 'cells', name: 'distance_to_marine_water_km', kind: 'numeric',
    marine_distance: { status_field: 'marine_distance_status', no_source_cell_count: 2 } };
  const validate = (value) => {
    app.context.manifest = { world: { cell_count: 2 }, layers: [value] };
    app.run('validateDisplayMetadata(manifest)');
  };
  validate(layer);
  validate({ ...layer, marine_distance: { ...layer.marine_distance, no_source_cell_count: 0 }, stats: { min: 0, max: 100 } });
  for (const value of [-1, 3, true, null, 0]) {
    assert.throws(() => validate({ ...layer, marine_distance: { ...layer.marine_distance, no_source_cell_count: value } }), /marine distance/);
  }
  assert.throws(() => validate({ ...layer, id: 'cells/rainfall' }), /marine distance/);
  assert.throws(() => validate({ ...layer, stats: { min: 0, max: 1 } }), /marine distance/);
});

test('schema constraints display exact large integer text after JSON Number rounding', () => {
  const app = workbench();
  // Simulate the actual browser JSON boundary, not a BigInt-only fixture.
  app.context.schema = JSON.parse('{"properties":{"seed":{"type":"integer","maximum":18446744073709551615,"default":18446744073709551615,"const":18446744073709551615,"minimum":-18446744073709551615,"exclusiveMinimum":-18446744073709551615,"exclusiveMaximum":18446744073709551615,"x-magic-geo-integer-display":{"maximum":"18446744073709551615","default":"18446744073709551615","const":"18446744073709551615","minimum":"-18446744073709551615","exclusiveMinimum":"-18446744073709551615","exclusiveMaximum":"18446744073709551615"}}}}');
  assert.equal(String(app.context.schema.properties.seed.maximum), '18446744073709552000');
  app.state.schemaFields = app.run('flattenSchema(schema)');
  app.run('renderSchemaDocs()');
  const html = app.get('#schema-docs').innerHTML;
  for (const prefix of ['Maximum: ', 'Default: ', 'Fixed value: ', 'Less than: ']) assert.ok(html.includes(prefix + '18446744073709551615'));
  for (const prefix of ['Minimum: ', 'Greater than: ']) assert.ok(html.includes(prefix + '-18446744073709551615'));
  assert.doesNotMatch(html, /18446744073709552000/);
  app.context.field = { type: 'number' };
  assert.equal(app.run("schemaValueText(field, 'minimum', 1.23456789)"), '1.23456789');
});

test('malformed exact-integer text cannot become a false or unsafe schema constraint', () => {
  const app = workbench();
  for (const text of [undefined, '<img src=x>', '12', '1e20', '018446744073709551615', {}]) {
    app.context.field = { type: 'integer', maximum: Number('18446744073709551615'), exactIntegers: { maximum: text } };
    app.state.schemaFields = [app.context.field];
    app.run('renderSchemaDocs()');
    assert.match(app.get('#schema-docs').innerHTML, /Maximum: exact integer unavailable/);
    assert.doesNotMatch(app.get('#schema-docs').innerHTML, /18446744073709552000|<img/);
  }
});

test('validate and save use exact YAML text and never roundtrip a seed through response JSON', async () => {
  const app = workbench();
  const yaml = 'config_version: 2\nrun:\n  seed: 18446744073709551615 # retain this comment\n';
  app.get('#config-yaml').value = yaml;
  app.get('#config-name').value = 'max-seed.yaml';
  const calls = [];
  app.context.fetchJson = async (url, options) => {
    calls.push([url, options.body]);
    return { valid: true, path: 'runs/configs/max-seed.yaml', yaml: 'seed: 18446744073709552000', config: JSON.parse('{"run":{"seed":18446744073709551615}}') };
  };
  await app.run('validateConfig()');
  await app.run('saveConfig()');
  assert.equal(calls.length, 2);
  assert.ok(calls.every(([, body]) => body.yaml === yaml));
  assert.equal(app.get('#config-yaml').value, yaml);
  assert.equal(app.state.savedConfig.yaml, yaml);
  assert.equal(app.get('#config-generate').disabled, false);
});

test('schema reference shows root version, opacity constraints and ref sibling descriptions', () => {
  const app = workbench();
  app.context.schema = seasonalSchema();
  const fields = app.run('flattenSchema(schema)');
  assert.equal(fields.find((field) => field.path === 'config_version').constant, 2);
  assert.equal(fields.find((field) => field.path === 'climate').description, 'Prescribed seasonal energy settings.');
  assert.equal(fields.find((field) => field.path === 'climate.reference_infrared_optical_depth').minimum, 0);
  assert.equal(fields.some((field) => /base_temperature|lapse_rate/.test(field.path)), false);
  app.state.schemaFields = fields;
  app.run('renderSchemaDocs()');
  const html = app.get('#schema-docs').innerHTML;
  assert.match(html, /config_version/);
  assert.match(html, /Fixed value: 2/);
  assert.match(html, /Minimum: 0 \(inclusive\)/);
  assert.match(html, /Maximum: 10 \(inclusive\)/);
  assert.match(html, /Fixed value: 12/);
  app.run("renderSchemaDocs('opacity')");
  assert.match(app.get('#schema-docs').innerHTML, /climate.reference_infrared_optical_depth/);
  assert.doesNotMatch(app.get('#schema-docs').innerHTML, /config_version/);
  app.run("renderSchemaDocs('tau_ref')");
  assert.match(app.get('#schema-docs').innerHTML, /climate.reference_infrared_optical_depth/);
  assert.match(app.get('#schema-docs').innerHTML, /dimensionless/);
});

test('current schema and matching server profiles populate a versioned default template', async () => {
  const app = workbench();
  const calls = [];
  app.context.fetchJson = async (url) => {
    calls.push(url);
    if (url === '/api/config/schema') return seasonalSchema();
    if (url === '/api/config/profiles') return seasonalProfiles();
    return { profile: 'earthlike', config: { config_version: 2 }, yaml: 'config_version: 2\n' };
  };
  await app.run('loadConfigWorkbench()');
  assert.equal(app.get('#config-yaml').value, 'config_version: 2\n');
  assert.equal(app.get('#config-profile').options.length, 3);
  assert.equal(app.get('#config-profile').disabled, false);
  assert.equal(app.get('#config-reset').disabled, false);
  assert.match(app.get('#config-schema-status').textContent, /Schema 2/);
  assert.equal(calls.filter((url) => url.includes('/template')).length, 1);
});

test('unavailable or mismatched schema/profile metadata never invents a legacy fallback', async () => {
  for (const failure of ['schema', 'profiles', 'old-version', 'old-profile-values', 'missing-profile']) {
    const app = workbench();
    app.get('#config-yaml').value = 'my: edits';
    let templateCalls = 0;
    app.context.fetchJson = async (url) => {
      if (url.includes('/template')) { templateCalls += 1; throw new Error('must not load template'); }
      if (url.endsWith(failure)) throw new Error('Service unavailable');
      const schema = seasonalSchema();
      if (failure === 'old-version') schema['x-magic-geo'].schema_version = 1;
      if (failure === 'old-profile-values') delete schema['x-magic-geo'].profiles[0].values.config_version;
      const profiles = seasonalProfiles();
      if (failure === 'missing-profile') profiles.profiles.pop();
      return url.endsWith('/schema') ? schema : profiles;
    };
    await app.run('loadConfigWorkbench()');
    assert.equal(templateCalls, 0, failure);
    assert.equal(app.get('#config-profile').options.length, 0, failure);
    assert.equal(app.get('#config-reset').disabled, true, failure);
    assert.equal(app.state.configSchema, null, failure);
    assert.equal(app.get('#config-yaml').value, 'my: edits', failure);
    assert.match(app.get('#config-schema-status').textContent, /unavailable/, failure);
  }
});

test('obsolete or misidentified templates cannot replace YAML beside the current schema', async () => {
  for (const payload of [
    { profile: 'smoke', config: {}, yaml: 'climate:\n  base_temperature_c: 15' },
    { profile: 'smoke', config: { config_version: 1 }, yaml: 'config_version: 1' },
    { profile: 'smoke', config: { config_version: '2' }, yaml: 'config_version: 2' },
    { profile: 'earthlike', config: { config_version: 2 }, yaml: 'config_version: 2' },
    { profile: 'smoke', config: { config_version: 2 }, yaml: '' },
  ]) {
    const app = workbench();
    app.state.configSchema = seasonalSchema();
    app.get('#config-profile').value = 'smoke';
    app.get('#config-yaml').value = 'custom: yaml';
    app.context.fetchJson = async () => payload;
    await app.run('resetConfigTemplate()');
    assert.equal(app.get('#config-yaml').value, 'custom: yaml');
    assert.equal(app.get('#config-result').className, 'validation-result invalid');
    assert.match(app.get('#config-result').textContent, /does not match configuration schema 2/);
  }
});

test('profile loading keeps existing YAML and edits entered during initial loading', async () => {
  for (const existing of [false, true]) {
    const app = workbench();
    const loading = deferred();
    if (existing) app.get('#config-yaml').value = 'existing: yaml';
    let templateCalls = 0;
    app.context.fetchJson = async (url) => {
      if (url === '/api/config/schema') return loading.promise;
      if (url === '/api/config/profiles') return seasonalProfiles();
      templateCalls += 1;
      throw new Error('must not replace edits');
    };
    const operation = app.run('loadConfigWorkbench()');
    if (!existing) {
      app.get('#config-yaml').value = 'new: edits';
      app.run('configEdited()');
    }
    loading.resolve(seasonalSchema());
    await operation;
    assert.equal(templateCalls, 0);
    assert.equal(app.get('#config-yaml').value, existing ? 'existing: yaml' : 'new: edits');
    assert.equal(app.get('#config-reset').disabled, false);
  }
});

test('older schema loading success or failure cannot replace a newer workbench snapshot', async () => {
  for (const failed of [false, true]) {
    const app = workbench();
    app.get('#config-yaml').value = 'custom: yaml';
    const stale = deferred();
    app.context.fetchJson = async (url) => url.endsWith('/schema') ? stale.promise : seasonalProfiles();
    const first = app.run('loadConfigWorkbench()');
    app.context.fetchJson = async (url) => url.endsWith('/schema') ? seasonalSchema() : seasonalProfiles();
    await app.run('loadConfigWorkbench()');
    if (failed) stale.reject(new Error('stale load failure'));
    else { const schema = seasonalSchema(); schema['x-magic-geo'].schema_version = 1; stale.resolve(schema); }
    await first;
    assert.equal(app.state.configSchema['x-magic-geo'].schema_version, 2);
    assert.equal(app.get('#config-profile').options.length, 3);
    assert.equal(app.get('#config-reset').disabled, false);
    assert.match(app.get('#config-schema-status').textContent, /Schema 2/);
    assert.equal(app.get('#config-yaml').value, 'custom: yaml');
  }
});

test('reloading schema invalidates an older in-flight template without clearing YAML', async () => {
  const app = workbench();
  app.state.configSchema = seasonalSchema();
  app.get('#config-profile').value = 'smoke';
  app.get('#config-yaml').value = 'custom: yaml';
  const stale = deferred();
  app.context.fetchTemplate = () => stale.promise;
  const resetting = app.run('resetConfigTemplate()');
  app.context.fetchJson = async (url) => url.endsWith('/schema') ? seasonalSchema() : seasonalProfiles();
  await app.run('loadConfigWorkbench()');
  stale.resolve('config_version: 1');
  await resetting;
  assert.equal(app.get('#config-yaml').value, 'custom: yaml');
  assert.match(app.get('#config-result').textContent, /YAML was kept/);
});

test('migration error paths and guidance render escaped while the YAML stays unchanged', async () => {
  const app = workbench();
  const yaml = 'climate:\n  base_temperature_c: 15\n  lapse_rate_c_per_km: 6.5';
  app.get('#config-yaml').value = yaml;
  const error = new Error('invalid old configuration');
  error.payload = { detail: { issues: [
    { path: 'config_version', message: 'Add config_version: 2 explicitly.' },
    { path: 'climate.base_temperature_c', message: 'Choose reference_infrared_optical_depth explicitly; no equivalent conversion.' },
    { path: 'climate.lapse_rate_c_per_km', message: 'Obsolete <field>; no equivalent conversion.' },
  ] } };
  app.context.fetchJson = async () => { throw error; };
  assert.equal(await app.run('validateConfig()'), false);
  const html = app.get('#config-result').innerHTML;
  for (const name of ['config_version', 'climate.base_temperature_c', 'climate.lapse_rate_c_per_km', 'reference_infrared_optical_depth']) assert.match(html, new RegExp(name));
  assert.match(html, /&lt;field&gt;/);
  assert.match(html, /no equivalent conversion/);
  assert.equal(app.get('#config-yaml').value, yaml);
});

test('cancelling explicit reset preserves edited YAML without requesting a template', async () => {
  const app = workbench();
  app.get('#config-profile').value = 'smoke';
  app.get('#config-yaml').value = 'custom: yaml';
  app.run('configEdited()');
  app.context.window.confirm = () => false;
  app.context.fetchTemplate = () => { throw new Error('template request must not happen'); };
  await app.run('resetConfigTemplate()');
  assert.equal(app.get('#config-yaml').value, 'custom: yaml');
});

function workbench() {
  const nodes = new Map();
  const get = (id) => {
    if (!nodes.has(id)) nodes.set(id, element());
    return nodes.get(id);
  };
  const context = vm.createContext({
    THREE: { Vector2: class { constructor(x, y) { this.x = x; this.y = y; } } }, console, URL, URLSearchParams,
    document: { querySelector: get, createElement: element },
    window: { confirm: () => true },
    Option: class { constructor(text, value) { this.text = text; this.value = value; } },
  });
  vm.runInContext(source, context);
  const run = (code) => vm.runInContext(code, context);
  return { context, get, run, state: run('state') };
}

async function cacheSwitchWorkbench() {
  const app = workbench();
  app.state.status = { cache_dir: 'runs/first' };
  const worlds = ['first', 'second'].map(name => ({ cache_dir: `runs/${name}`, name, cell_count: 2 }));
  app.context.optionalJson = async () => ({ worlds });
  await app.run('refreshWorlds({ force: true })');
  // Isolate map/status loading from the two real selector handlers under test.
  app.context.beginCacheTransition = cacheDir => { app.state.status = { cache_dir: cacheDir }; };
  app.context.loadServerStatus = async () => app.state.status;
  return app;
}

test('world polling cannot reset or reenable a pending cache selection', async () => {
  const app = await cacheSwitchWorkbench();
  const selected = app.get('#world-select');
  const request = deferred();
  app.context.fetchJson = () => request.promise;
  selected.value = 'runs/second';
  const switching = app.run('switchWorld()');
  app.context.optionalJson = async () => ({ worlds: ['first', 'second', 'new-export'].map(name => ({ cache_dir: `runs/${name}`, name, cell_count: 2 })) });
  try {
    await app.run('refreshWorlds()');
    assert.equal(selected.disabled, true, 'changed world-list poll must not reenable a pending switch');
    assert.equal(selected.value, 'runs/second', 'pending destination must stay visible');
  } finally {
    request.resolve({});
    await switching;
  }
  assert.equal(selected.disabled, false);
});

test('an older world-list response cannot rewrite a pending cache selection', async () => {
  const app = await cacheSwitchWorkbench();
  const listing = deferred();
  const request = deferred();
  app.context.optionalJson = () => listing.promise;
  const polling = app.run('refreshWorlds()');
  app.context.fetchJson = () => request.promise;
  const selected = app.get('#world-select');
  selected.value = 'runs/second';
  const switching = app.run('switchWorld()');
  listing.resolve({ worlds: ['first', 'second', 'new-export'].map(name => ({ cache_dir: `runs/${name}`, name, cell_count: 2 })) });
  try {
    await polling;
    assert.equal(selected.disabled, true);
    assert.equal(selected.value, 'runs/second');
  } finally {
    request.resolve({});
    await switching;
  }
});

test('cache selection does not start a second mutation while the first is pending', async () => {
  const app = await cacheSwitchWorkbench();
  const request = deferred();
  const calls = [];
  app.context.fetchJson = (url, options) => { calls.push([url, options.body.cache_dir]); return request.promise; };
  const selected = app.get('#world-select');
  selected.value = 'runs/second';
  const switching = app.run('switchWorld()');
  selected.value = 'runs/third';
  const duplicate = app.run('switchWorld()');
  try {
    assert.deepEqual(calls, [['/api/worlds/select', 'runs/second']]);
  } finally {
    request.resolve({});
    await Promise.all([switching, duplicate]);
  }
});

test('failed cache selection restores the current option and releases controls', async () => {
  const app = await cacheSwitchWorkbench();
  const selected = app.get('#world-select');
  const request = deferred();
  app.context.fetchJson = () => request.promise;
  selected.value = 'runs/second';
  const switching = app.run('switchWorld()');
  request.reject(new Error('selection unavailable'));
  await switching;
  assert.equal(app.state.status.cache_dir, 'runs/first');
  assert.equal(selected.value, 'runs/first');
  assert.equal(selected.disabled, false);
  assert.equal(app.get('#cache-state').textContent, 'Switch failed');
});

test('completed cache selection allows a later independent selection', async () => {
  const app = await cacheSwitchWorkbench();
  const selected = app.get('#world-select');
  const calls = [];
  app.context.fetchJson = async (url, options) => { calls.push([url, options.body.cache_dir]); return {}; };
  selected.value = 'runs/second';
  await app.run('switchWorld()');
  assert.equal(selected.disabled, false);
  assert.equal(app.state.status.cache_dir, 'runs/second');
  selected.value = 'runs/first';
  await app.run('switchWorld()');
  assert.deepEqual(calls, [['/api/worlds/select', 'runs/second'], ['/api/worlds/select', 'runs/first']]);
  assert.equal(app.state.status.cache_dir, 'runs/first');
  assert.equal(selected.disabled, false);
});

test('backend refresh keeps the latest successful report after an older reply', async (t) => {
  for (const staleFails of [false, true]) {
    await t.test(staleFails ? 'older error' : 'older success', async () => {
      const app = workbench();
      const older = deferred();
      const newer = deferred();
      let calls = 0;
      app.context.fetchJson = (url) => {
        assert.equal(url, '/api/backend');
        return ++calls === 1 ? older.promise : newer.promise;
      };
      const first = app.run('loadBackend()');
      const second = app.run('loadBackend()');
      newer.resolve({ revision: 'current', capability: true });
      await second;
      const current = app.get('#backend-output').innerHTML;
      assert.match(current, /current/);
      if (staleFails) older.reject(new Error('old request failed'));
      else older.resolve({ revision: 'obsolete', capability: false });
      await first;
      assert.equal(calls, 2);
      assert.equal(app.get('#backend-output').innerHTML, current);
    });
  }
});

test('backend refresh keeps the latest error after an older reply', async (t) => {
  for (const staleFails of [false, true]) {
    await t.test(staleFails ? 'older error' : 'older success', async () => {
      const app = workbench();
      const older = deferred();
      const newer = deferred();
      let calls = 0;
      app.context.fetchJson = () => ++calls === 1 ? older.promise : newer.promise;
      const first = app.run('loadBackend()');
      const second = app.run('loadBackend()');
      newer.reject(new Error('current <failure>'));
      await second;
      const current = app.get('#backend-output').innerHTML;
      assert.match(current, /notice warning/);
      assert.match(current, /current &lt;failure&gt;/);
      if (staleFails) older.reject(new Error('old request failed'));
      else older.resolve({ revision: 'obsolete' });
      await first;
      assert.equal(app.get('#backend-output').innerHTML, current);
    });
  }
});

test('backend refresh stays loading until the newest request settles', async (t) => {
  for (const staleFails of [false, true]) {
    await t.test(staleFails ? 'older error' : 'older success', async () => {
      const app = workbench();
      const older = deferred();
      const newer = deferred();
      let calls = 0;
      app.context.fetchJson = () => ++calls === 1 ? older.promise : newer.promise;
      const first = app.run('loadBackend()');
      const second = app.run('loadBackend()');
      const loading = app.get('#backend-output').innerHTML;
      assert.match(loading, /Loading/);
      if (staleFails) older.reject(new Error('old request failed'));
      else older.resolve({ revision: 'obsolete' });
      await first;
      const afterOlder = app.get('#backend-output').innerHTML;
      newer.resolve({ revision: 'current' });
      await second;
      assert.equal(afterOlder, loading);
      assert.match(app.get('#backend-output').innerHTML, /current/);
    });
  }
});

function layerWorkbench() {
  const app = workbench();
  const prepare = (node) => {
    node.style = {};
    node.classList.toggle = (name, enabled) => {
      if (enabled) node.classList.add(name);
      else node.classList.remove(name);
    };
    node.setAttribute = (name, value) => { node[name] = value; };
    node.removeAttribute = (name) => { delete node[name]; };
    node.getContext = () => ({ fillRect() {} });
    node.width = 2;
    node.height = 1;
    return node;
  };
  const items = ['A', 'B', 'C'].map((id) => {
    const node = prepare(element());
    node.dataset.layerId = id;
    return node;
  });
  app.context.document.querySelector = (id) => prepare(app.get(id));
  app.context.document.querySelectorAll = () => items;
  app.context.window.setTimeout = () => 0;
  app.context.prefetchNeighborStages = () => {};
  app.context.updateDocsCard = (layer) => { app.docsLayer = layer?.id ?? null; };
  app.run(`
    state.cacheAvailable = true;
    state.cacheIdentity = 'world-revision';
    state.status = { cache_revision: 'revision' };
    state.cellCount = 1;
    state.mapReady = true;
    state.manifest = { world: { name: 'synthetic' }, mesh: { triangle_count: 1 } };
    state.hoverCell = 0;
    three.valueTexture = { image: { data: new Float32Array(1) } };
    three.fillMaterial = { uniforms: { uMin: {}, uMax: {}, uCategorical: {} } };
  `);
  app.context.layers = Object.fromEntries(['A', 'B', 'C'].map((id, index) => [id, {
    id, name: id, source: 'history', kind: 'numeric_stage', stage_count: 12,
    stats: { min: index * 10, max: (index + 1) * 10 },
  }]));
  app.snapshot = () => ({
    layer: app.state.activeLayer?.id ?? null,
    stage: app.state.stage, month: app.state.month,
    values: app.state.values ? Array.from(app.state.values) : null,
    texture: Array.from(app.run('three.valueTexture.image.data')),
    legend: app.get('#legend-title').textContent,
    docsLayer: app.docsLayer,
    hover: app.get('#map-hover').textContent,
    loading: app.state.layerLoading,
    exportCurrent: app.run('exportSnapshotMatchesState()'),
  });
  return app;
}

test('layer failure restores the last displayed slice across overlapping requests', async () => {
  for (const staleFails of [false, true]) {
    const app = layerWorkbench();
    app.context.fetchLayerValues = async () => new Float32Array([7]);
    await app.run('activateLayer(layers.A, { stage: 2, month: 4 })');
    const displayed = app.snapshot();
    const older = deferred();
    const latest = deferred();
    app.context.fetchLayerValues = (layer) => layer.id === 'B' ? older.promise : latest.promise;
    const pendingB = app.run('activateLayer(layers.B, { stage: 3, month: 5 })');
    const pendingC = app.run('activateLayer(layers.C, { stage: 4, month: 6 })');
    latest.reject(new Error('current layer failed'));
    await pendingC;
    const afterFailure = app.snapshot();
    if (staleFails) older.reject(new Error('superseded layer failed'));
    else older.resolve(new Float32Array([17]));
    await pendingB;
    assert.deepEqual(afterFailure, displayed);
    assert.deepEqual(app.snapshot(), displayed);
    assert.equal(app.get('#export-map-image').disabled, false);
  }
});

test('superseded layer failure cannot clear loading or replace a later successful slice', async () => {
  const app = layerWorkbench();
  app.context.fetchLayerValues = async () => new Float32Array([7]);
  await app.run('activateLayer(layers.A, { stage: 2, month: 4 })');
  const older = deferred();
  const latest = deferred();
  app.context.fetchLayerValues = (layer) => layer.id === 'B' ? older.promise : latest.promise;
  const pendingB = app.run('activateLayer(layers.B, { stage: 3, month: 5 })');
  const pendingC = app.run('activateLayer(layers.C, { stage: 4, month: 6 })');
  older.reject(new Error('superseded failure'));
  await pendingB;
  assert.equal(app.state.layerLoading, true);
  assert.equal(app.state.activeLayer.id, 'C');
  assert.equal(app.get('#export-map-image').disabled, true);
  latest.resolve(new Float32Array([27]));
  await pendingC;
  assert.deepEqual(app.snapshot(), {
    layer: 'C', stage: 4, month: 6, values: [27], texture: [27],
    legend: 'history / C', docsLayer: 'C', hover: 'history/C  ·  cell 0  ·  27',
    loading: false, exportCurrent: true,
  });
});

test('initial overlapping layer failures never label an uncommitted slice as displayed', async () => {
  const app = layerWorkbench();
  const older = deferred();
  const latest = deferred();
  app.context.fetchLayerValues = (layer) => layer.id === 'B' ? older.promise : latest.promise;
  const pendingB = app.run('activateLayer(layers.B, { stage: 3, month: 5 })');
  const pendingC = app.run('activateLayer(layers.C, { stage: 4, month: 6 })');
  latest.reject(new Error('current failure'));
  await pendingC;
  older.resolve(new Float32Array([17]));
  await pendingB;
  assert.equal(app.state.activeLayer, null);
  assert.equal(app.state.values, null);
  assert.equal(app.state.stage, 0);
  assert.equal(app.state.month, 0);
  assert.equal(app.state.layerLoading, false);
  assert.equal(app.get('#legend-title').textContent, 'no layer');
  assert.equal(app.get('#export-map-image').disabled, true);
});

function inspectorWorkbench() {
  const app = layerWorkbench();
  const listeners = new Map();
  const layerQuery = app.context.document.querySelector;
  app.context.document.querySelector = (id) => {
    const node = layerQuery(id);
    node.contains = () => false;
    node.addEventListener = (type, listener) => listeners.set(`${id}:${type}`, listener);
    node.click = () => listeners.get(`${id}:click`)?.();
    node.replaceChildren = () => { node.innerHTML = ''; };
    node.querySelector = (selector) => app.context.document.querySelector(`${id} ${selector}`);
    return node;
  };
  app.context.document.querySelectorAll = () => [];
  app.context.window.location = { href: 'http://localhost/' };
  app.context.window.addEventListener = () => {};
  app.context.AbortController = AbortController;
  app.context.cancelAnimationFrame = () => {};
  app.context.resizeRenderer = () => {};
  app.context.disposeMapScene = () => {};
  app.context.updatePager = () => {};
  app.run(`
    state.cellCount = 4;
    three.controls = { addEventListener() {} };
    three.renderer = { domElement: { addEventListener() {} } };
    wireMapEvents();
  `);
  app.get('#help-overlay').classList.add('hidden');
  return app;
}

for (const sameCell of [false, true]) {
  for (const staleFails of [false, true]) {
    test(`inspector ignores stale ${staleFails ? 'failure' : 'success'} for ${sameCell ? 'the same cell' : 'another cell'}`, async () => {
      const app = inspectorWorkbench();
      const older = deferred();
      const latest = deferred();
      let request = 0;
      app.context.fetchJson = () => (++request === 1 ? older.promise : latest.promise);
      const first = app.run('openInspector(1)');
      const second = app.run(`openInspector(${sameCell ? 1 : 2})`);
      latest.resolve({ cell: { diagnostic: 'current response' } });
      await second;
      const currentBody = app.get('#inspector-body').innerHTML;
      assert.match(currentBody, /current response/);
      if (staleFails) older.reject(new Error('obsolete error'));
      else older.resolve({ cell: { diagnostic: 'obsolete response' } });
      await first;
      assert.equal(app.get('#inspector-body').innerHTML, currentBody);
      assert.equal(app.get('#inspector-title').textContent, `Cell ${sameCell ? 1 : 2}`);
    });
  }
}

test('inspector latest failure remains visible when an older same-cell success arrives', async () => {
  const app = inspectorWorkbench();
  const older = deferred();
  const latest = deferred();
  let request = 0;
  app.context.fetchJson = () => (++request === 1 ? older.promise : latest.promise);
  const first = app.run('openInspector(1)');
  const second = app.run('openInspector(1)');
  latest.reject(new Error('current <failure>'));
  await second;
  const currentBody = app.get('#inspector-body').innerHTML;
  assert.match(currentBody, /current &lt;failure&gt;/);
  older.resolve({ cell: { diagnostic: 'obsolete response' } });
  await first;
  assert.equal(app.get('#inspector-body').innerHTML, currentBody);
});

test('inspector close invalidates a pending failure and same-cell reopen', async () => {
  const app = inspectorWorkbench();
  const closed = deferred();
  app.context.fetchJson = () => closed.promise;
  const pending = app.run('openInspector(1)');
  app.get('#inspector-close').click();
  const closedBody = app.get('#inspector-body').innerHTML;
  closed.reject(new Error('closed request error'));
  await pending;
  assert.equal(app.state.selectedCell, -1);
  assert.equal(app.get('#inspector').classList.contains('hidden'), true);
  assert.equal(app.get('#inspector-body').innerHTML, closedBody);
  app.context.fetchJson = async () => ({ cell: { diagnostic: 'reopened response' } });
  await app.run('openInspector(1)');
  assert.equal(app.get('#inspector').classList.contains('hidden'), false);
  assert.match(app.get('#inspector-body').innerHTML, /reopened response/);
});

test('inspector cache reset isolates an old failure from a reopened same-cell panel', async () => {
  const app = inspectorWorkbench();
  const oldCache = deferred();
  app.context.fetchJson = () => oldCache.promise;
  const pending = app.run('openInspector(1)');
  app.run('resetCacheDerivedState()');
  app.context.fetchJson = async () => ({ cell: { diagnostic: 'new cache response' } });
  await app.run('openInspector(1)');
  const currentBody = app.get('#inspector-body').innerHTML;
  oldCache.reject(new Error('old cache error'));
  await pending;
  assert.match(currentBody, /new cache response/);
  assert.equal(app.get('#inspector-body').innerHTML, currentBody);
});

test('inspector distinguishes unsupported productivity from supported and legacy zeros', () => {
  const app = workbench();
  app.context.cell = {
    aquatic_climate_proxy_applicable: true,
    aquatic_primary_climate_supported: false,
    fishery_climate_supported: true,
    fishery_productivity_supported: false,
  };
  assert.match(app.run("formatInspectorValue(cell, 'primary_productivity_index', 0)"), /^0 \(estimate unavailable: climate/);
  assert.match(app.run("formatInspectorValue(cell, 'fishery_productivity_index', 0)"), /primary productivity unsupported/);
  assert.equal(app.run("formatInspectorValue(cell, 'temperature_c', -18)"), '-18');
  app.context.cell.aquatic_primary_climate_supported = true;
  app.context.cell.fishery_productivity_supported = true;
  assert.equal(app.run("formatInspectorValue(cell, 'primary_productivity_index', 0)"), '0');
  assert.equal(app.run("formatInspectorValue(cell, 'fishery_productivity_index', 0)"), '0');
  app.context.cell = {};
  assert.equal(app.run("formatInspectorValue(cell, 'primary_productivity_index', 0)"), '0');
  assert.equal(app.run("formatInspectorValue(cell, 'fishery_productivity_index', 0)"), '0');
});

test('validation never marks edits made during its request as valid or invalid', async () => {
  for (const failed of [false, true]) {
    const app = workbench();
    const response = deferred();
    app.context.fetchJson = () => response.promise;
    app.get('#config-yaml').value = 'seed: 1';
    const validating = app.run('validateConfig()');
    app.get('#config-yaml').value = 'seed: [invalid';
    app.run('configEdited()');
    if (failed) response.reject(new Error('Old validation failed'));
    else response.resolve({ valid: true });
    await validating;
    assert.equal(app.get('#config-result').className, 'validation-result');
    assert.match(app.get('#config-result').textContent, /Configuration changed/);
    assert.equal(app.get('#config-validate').disabled, false);
  }
});

test('saving an earlier YAML snapshot reports remaining edits and disables generation', async () => {
  const app = workbench();
  const response = deferred();
  app.context.fetchJson = () => response.promise;
  app.get('#config-yaml').value = 'seed: 1';
  app.get('#config-name').value = 'custom';
  const saving = app.run('saveConfig()');
  app.get('#config-yaml').value = 'seed: 2';
  app.run('configEdited()');
  response.resolve({ path: 'runs/configs/custom.yaml' });
  await saving;
  assert.equal(app.state.savedConfig.yaml, 'seed: 1');
  assert.equal(app.get('#config-generate').disabled, true);
  assert.match(app.get('#config-saved-status').textContent, /Save the current edits/);
  assert.equal(app.get('#config-result').className, 'validation-result');
});

test('a template arriving after validation begins invalidates the older YAML result', async () => {
  const app = workbench();
  const template = deferred();
  const validation = deferred();
  app.get('#config-profile').value = 'smoke';
  app.get('#config-yaml').value = 'seed: 1';
  app.context.fetchTemplate = () => template.promise;
  app.context.fetchJson = () => validation.promise;
  const resetting = app.run('resetConfigTemplate()');
  const validating = app.run('validateConfig()');
  template.resolve('seed: 2');
  await resetting;
  validation.resolve({ valid: true });
  await validating;
  assert.equal(app.get('#config-yaml').value, 'seed: 2');
  assert.match(app.get('#config-result').textContent, /Loaded the smoke template/);
  assert.equal(app.get('#config-result').className, 'validation-result');
});

test('overwrite retries use the exact originally submitted name and YAML', async () => {
  const app = workbench();
  const requests = [];
  app.get('#config-yaml').value = 'seed: 1';
  app.get('#config-name').value = 'original';
  app.context.fetchJson = async (_url, options) => {
    requests.push(JSON.parse(JSON.stringify(options.body)));
    if (requests.length === 1) throw Object.assign(new Error('Exists'), { status: 409 });
    return { path: 'runs/configs/original.yaml' };
  };
  app.context.window.confirm = () => {
    app.get('#config-name').value = 'another';
    app.get('#config-yaml').value = 'seed: 2';
    app.run('configEdited()');
    return true;
  };
  await app.run('saveConfig()');
  assert.deepEqual(requests, [
    { yaml: 'seed: 1', name: 'original', force: false },
    { yaml: 'seed: 1', name: 'original', force: true },
  ]);
  assert.equal(app.get('#config-generate').disabled, true);
});

test('an obsolete save conflict does not open an overwrite prompt', async () => {
  const app = workbench();
  const response = deferred();
  app.context.fetchJson = () => response.promise;
  app.context.window.confirm = () => assert.fail('Stale overwrite prompt');
  const saving = app.run('saveConfig()');
  app.run('configEdited()');
  response.reject(Object.assign(new Error('Exists'), { status: 409 }));
  await saving;
  assert.equal(app.get('#config-save').disabled, false);
});

test('saved custom workspace configuration is passed to the generation form', async () => {
  const app = workbench();
  app.get('#config-name').value = 'climate-review';
  app.get('#config-yaml').value = 'seed: 42';
  app.context.fetchJson = async () => ({ path: 'runs/custom/configs/climate-review.yaml' });
  await app.run('saveConfig()');
  const configInput = element();
  app.get('#operation-fields').querySelector = () => configInput;
  app.context.renderOperationForm = () => {};
  app.context.setView = (name) => { app.state.activeView = name; };
  app.run('generateFromSavedConfig()');
  assert.equal(app.get('#operation-select').value, 'generate');
  assert.equal(configInput.value, 'runs/custom/configs/climate-review.yaml');
  assert.equal(app.state.activeView, 'operations');
});

test('numeric forms accept fractional API values and retain scientific integer notation', () => {
  const app = workbench();
  const submit = element();
  app.get('#operation-form').querySelector = () => submit;
  app.get('#operation-select').value = 'render';
  app.state.operations = [{ name: 'render', fields: [
    { name: 'contour_interval', kind: 'number', minimum: 50, default: 500 },
    { name: 'width', kind: 'integer', minimum: 320, default: 1600 },
  ] }];
  app.run('renderOperationForm()');
  const [interval, width] = app.get('#operation-fields').children.map((field) => field.children[1]);
  assert.equal(interval.step, 'any');
  assert.equal(width.step, '1');
  interval.value = '125.5';
  width.value = '1e3';
  app.get('#operation-fields').querySelectorAll = () => [interval, width];
  assert.deepEqual(JSON.parse(JSON.stringify(app.run('collectOperationArguments()'))), { contour_interval: 125.5, width: 1000 });
});

test('switching job detail hides cancellation until the selected job loads', async () => {
  const app = workbench();
  const response = deferred();
  app.state.selectedJobId = 'old';
  app.context.fetchJson = () => response.promise;
  app.context.renderJobs = () => {};
  app.context.renderJobDetail = () => {};
  const selecting = app.run('selectJob("new")');
  assert.equal(app.get('#job-cancel').classList.contains('hidden'), true);
  assert.match(app.get('#job-detail-title').textContent, /Loading job new/);
  response.resolve({ id: 'new', status: 'running' });
  await selecting;
});

test('submitting a new job leaves selection changes to the guarded detail loader', async () => {
  const app = workbench();
  const submit = element();
  app.get('#operation-form').querySelector = () => submit;
  app.get('#operation-select').value = 'generate';
  app.state.operations = [{ name: 'generate' }];
  app.state.selectedJobId = 'old';
  app.context.fetchJson = async () => ({ id: 'new' });
  app.context.refreshJobs = async () => assert.equal(app.state.selectedJobId, 'old');
  app.context.selectJob = async (id) => {
    assert.equal(app.state.selectedJobId, 'old');
    assert.equal(id, 'new');
    app.state.selectedJobId = id;
  };
  await app.run('submitOperation({preventDefault() {}})');
  assert.equal(app.state.selectedJobId, 'new');
  assert.equal(submit.disabled, false);
});

function jobActionWorkbench() {
  const app = workbench();
  const submit = element();
  app.get('#operation-form').querySelector = () => submit;
  app.get('#operation-select').value = 'generate';
  app.state.operations = [{ name: 'generate' }];
  app.context.document.createElement = () => Object.assign(element(), {
    setAttribute() {}, addEventListener() {},
  });
  const cancel = app.get('#job-cancel');
  cancel.classList.toggle = (name, enabled) => {
    if (enabled) cancel.classList.add(name);
    else cancel.classList.remove(name);
  };
  const post = deferred();
  const listing = deferred();
  const listStarted = deferred();
  const requests = [];
  app.context.fetchJson = (url, options = {}) => {
    requests.push([url, options.method || 'GET']);
    if (url === '/api/jobs' && options.method === 'POST') return post.promise;
    if (url === '/api/jobs') { listStarted.resolve(); return listing.promise; }
    return Promise.resolve({ id: url.split('/').at(-1), status: 'completed', logs: `Details ${url}` });
  };
  const snapshot = () => ({ id: app.state.selectedJobId,
    title: app.get('#job-detail-title').textContent, html: app.get('#job-detail').innerHTML });
  return { ...app, submit, post, listing, listStarted, requests, snapshot };
}

for (const pending of ['submission', 'list refresh']) {
  for (const selected of ['other', 'old']) {
    test(`job submission preserves a later ${selected} selection during ${pending}`, async () => {
      const app = jobActionWorkbench();
      await app.run('selectJob("old")');
      const submitting = app.run('submitOperation({preventDefault() {}})');
      if (pending === 'list refresh') {
        app.post.resolve({ id: 'created' });
        await app.listStarted.promise;
      }
      await app.run(`selectJob('${selected}')`);
      const current = app.snapshot();
      if (pending === 'submission') {
        app.post.resolve({ id: 'created' });
        await app.listStarted.promise;
      }
      app.listing.resolve({ jobs: ['old', 'other', 'created'].map((id) => ({ id, status: 'completed' })) });
      await submitting;
      assert.equal(app.state.operationSubmitting, false);
      assert.equal(app.submit.disabled, false);
      assert.match(app.get('#operation-result').textContent, /Started job created/);
      assert.equal(app.requests.filter(([, method]) => method === 'POST').length, 1);
      assert.deepEqual(app.snapshot(), current);
      assert.equal(app.requests.some(([url]) => url === '/api/jobs/created'), false);
    });
  }
}

test('job submission still reveals the new job after an automatic active-job refresh', async () => {
  const app = jobActionWorkbench();
  await app.run('selectJob("old")');
  const submitting = app.run('submitOperation({preventDefault() {}})');
  app.post.resolve({ id: 'created' });
  await app.listStarted.promise;
  app.listing.resolve({ jobs: [{ id: 'old', status: 'running' }, { id: 'created', status: 'queued' }] });
  await submitting;
  assert.equal(app.state.selectedJobId, 'created');
  assert.match(app.get('#job-detail-title').textContent, /created/);
  assert.equal(app.requests.filter(([url]) => url === '/api/jobs/old').length, 2);
  assert.equal(app.requests.filter(([url]) => url === '/api/jobs/created').length, 1);
  assert.equal(app.submit.disabled, false);
});

test('cancellation cannot select null after polling prunes the selected job', async () => {
  const app = workbench();
  const selected = [];
  app.state.selectedJobId = 'old';
  app.context.fetchJson = async (url) => assert.match(url, /\/old\/cancel$/);
  app.context.refreshJobs = async () => { app.state.selectedJobId = null; };
  app.context.selectJob = async (id) => selected.push(id);
  await app.run('cancelSelectedJob()');
  assert.deepEqual(selected, []);
  assert.equal(app.get('#job-cancel').disabled, false);
});

function meshFixture() {
  return {
    'positions.f32': new Float32Array(6 * 3).buffer,
    'cell_ids.u32': new Uint32Array([0, 0, 0, 1, 1, 1]).buffer,
    'indices.u32': new Uint32Array([0, 1, 2, 3, 4, 5]).buffer,
    'pos_equirect.f32': new Float32Array(6 * 2).buffer,
    'pos_mollweide.f32': new Float32Array(6 * 2).buffer,
  };
}

test('the map sizes values and reports world cells independently of polygon vertices', async () => {
  const app = workbench();
  class RenderObject {
    constructor(data) { this.image = { data }; this.position = { set() {} }; }
    setPixelRatio() {} add() {} setAttribute() {} setIndex() {}
  }
  for (const name of ['WebGLRenderer', 'Scene', 'Color', 'PerspectiveCamera', 'BufferGeometry', 'BufferAttribute', 'DataTexture', 'ShaderMaterial', 'Mesh', 'Vector4', 'WebGLRenderTarget']) {
    app.context.THREE[name] = RenderObject;
  }
  app.context.OrbitControls = RenderObject;
  app.context.resizeRenderer = () => {};
  app.context.window.location = { href: 'http://localhost/' };
  const fixture = meshFixture();
  app.context.fetchBuffer = async (url) => fixture[url.split('/').at(-1)];
  app.state.cellCount = 2;
  app.state.cacheAvailable = true;
  assert.equal(await app.run('buildScene(currentCacheContext())'), true);
  assert.equal(app.state.cellCount, 2);
  assert.equal(app.run('three.valueTexture.image.data.length'), 2);
});

test('malformed mesh references and vertex arrays are rejected before WebGL setup', () => {
  for (const change of [
    (fixture) => { fixture['cell_ids.u32'] = new Uint32Array([0, 0, 0, 2, 2, 2]).buffer; },
    (fixture) => { fixture['indices.u32'] = new Uint32Array([0, 1, 99]).buffer; },
    (fixture) => { fixture['pos_mollweide.f32'] = new Float32Array(2).buffer; },
  ]) {
    const app = workbench();
    const fixture = meshFixture();
    change(fixture);
    app.context.buffers = Object.values(fixture);
    assert.throws(() => app.run('decodeMeshBuffers(...buffers, 2)'), /cache mesh/);
  }
});

test('layer value count must match the world before it enters the shared cache', async () => {
  const app = workbench();
  app.state.cellCount = 2;
  app.state.cacheAvailable = true;
  app.context.fetchBuffer = async () => new Float32Array([1, 2, 3]).buffer;
  await assert.rejects(app.run('fetchLayerValues({id: "cells/elevation_m", kind: "numeric"}, 0, 0)'), /3 values; expected 2 cells/);
  assert.equal(app.state.layerCache.size, 0);
});

test('parent and fire availability displays unavailable without hiding supported or legacy zero', () => {
  const app = workbench();
  const fields = {
    primary_productivity_index: 'primary_productivity_supported',
    vegetation_biomass_index: 'vegetation_biomass_supported',
    forest_growth_index: 'forest_growth_supported',
    species_richness_index: 'species_richness_supported',
    wildfire_spread_risk_index: 'ecosystem_wildfire_spread_risk_supported',
    ecosystem_disturbance_pressure_index: 'ecosystem_disturbance_pressure_supported',
    vegetation_recovery_years: 'vegetation_recovery_supported',
    species_endemism_index: 'species_endemism_supported',
    species_composition_confidence_index: 'species_composition_confidence_supported',
    species_range_fragmentation_index: 'species_record_descriptors_supported',
    wildfire_fuel_continuity_index: 'wildfire_fuel_continuity_supported',
    wildfire_firebreak_index: 'wildfire_firebreak_supported',
    wildfire_ignition_potential_index: 'wildfire_ignition_potential_supported',
  };
  for (const [field, flag] of Object.entries(fields)) {
    app.context.field = field;
    app.context.cell = { [flag]: false };
    assert.equal(app.run('formatInspectorValue(cell, field, 0)'), 'Unavailable');
    app.context.cell[flag] = true;
    assert.equal(app.run('formatInspectorValue(cell, field, 0)'), '0');
    app.context.cell = {};
    assert.equal(app.run('formatInspectorValue(cell, field, 0)'), '0');
  }
});

test('species score coverage and record descriptors remain distinct in the actual inspector markup', () => {
  const app = workbench();
  app.context.cell = {
    species_composition_status: 'complete', species_applicable_guild_count: 4,
    species_supported_guild_count: 4, species_record_descriptors_supported: false,
    species_guild_scores: { marine_fish: 0, canopy_tree: 0 },
    species_marine_fish_score_supported: true, species_canopy_tree_score_supported: false,
  };
  const html = app.run('speciesAvailabilityMarkup(cell)');
  assert.match(html, /Score coverage: <strong>complete/);
  assert.match(html, /Range records unavailable/);
  assert.match(html, /marine fish<\/span><span class="v">0<\/span>/);
  assert.match(html, /canopy tree<\/span><span class="v">Unavailable<\/span>/);
  app.context.cell.species_composition_status = 'partial';
  assert.equal(app.run("formatInspectorValue(cell, 'species_guild_richness_count', 0)"), '0 (partial score coverage)');
  app.context.cell.species_supported_guild_count = 0;
  assert.equal(app.run("formatInspectorValue(cell, 'dominant_species_guild', 'none')"), 'Unavailable');
  app.context.cell = {};
  assert.equal(app.run('speciesAvailabilityMarkup(cell)'), '');
});

test('fire family UI shows unknown front coverage and scopes containment', () => {
  const app = workbench();
  app.context.rows = [
    { front_coverage_status: 'partial_unavailable_inputs' },
    { front_coverage_status: 'complete_for_examined_adjacency' },
  ];
  const markup = app.run("familyAvailabilityMarkup('wildfire_spread_histories', rows)");
  assert.match(markup, /1 of 2 histories/);
  assert.match(markup, /does not demonstrate physical containment/);
  assert.match(markup, /unmodeled edges and step coverage/);
  assert.match(markup, /steps column contains/);
  assert.match(markup, /Open raw JSON for untruncated details/);
  assert.doesNotMatch(markup, /Select Full nested records/);
  const scalarMarkup = app.run("familyAvailabilityMarkup('wildfire_spread_histories', rows, 'scalars')");
  assert.match(scalarMarkup, /1 of 2 histories/);
  assert.match(scalarMarkup, /Select Full nested records/);
  assert.doesNotMatch(scalarMarkup, /steps column contains/);
  app.context.rows = [{ containment_index: 0 }];
  assert.equal(app.run("familyAvailabilityMarkup('wildfire_spread_histories', rows)"), '');
});

test('an entirely unavailable layer shows no invented numeric legend range', () => {
  const app = workbench();
  app.get('#legend-ramp').style = {};
  for (const kind of ['numeric', 'categorical']) {
    app.context.layer = { source: 'cells', name: 'estimate', kind, categories: [], availability: { field: 'supported', unavailable_when: 'false' } };
    app.run('updateLegend(layer)');
    assert.equal(app.get('#legend-ramp').style.display, 'none');
    assert.equal(app.get('#legend-min').textContent, 'No available estimates');
    assert.equal(app.get('#legend-max').textContent, '');
  }
});

test('unavailable numeric export codex has no invented ramp and scopes masked ranges', () => {
  const app = workbench();
  app.context.doc = { unit: 'index', role: 'diagnostic' };
  app.context.snapshot = { layer: { name: 'primary_productivity_index', kind: 'numeric', availability: { field: 'primary_productivity_supported', unavailable_when: 'false' } }, values: [NaN] };
  app.context.summary = { total: 1, missingCount: 1, finiteCount: 0, min: null, max: null };
  const unavailable = app.run('buildNumericCodex(snapshot, doc, summary)');
  assert.match(unavailable, /No available estimates in this layer slice/);
  assert.match(unavailable, /Current slice: 0 finite cells; no available-value range/);
  assert.doesNotMatch(unavailable, /Viridis normalized|Encoded value|Scale position/);
  assert.match(unavailable, /\| 1 \| 100\.00% \|/);

  app.context.snapshot.layer.stats = { min: 0, max: 0, p2: 0, p98: 0 };
  app.context.snapshot.values = [NaN, 0, 0];
  app.context.summary = { total: 3, missingCount: 1, finiteCount: 2, min: 0, max: 0 };
  const masked = app.run('buildNumericCodex(snapshot, doc, summary)');
  assert.match(masked, /Complete layer\/time-axis available-value range: 0 index to 0 index/);
  assert.doesNotMatch(masked, /Complete layer\/time-axis raw range/);
  assert.match(masked, /Current slice: 2 finite cells/);
  assert.match(masked, /Viridis normalized/);

  delete app.context.snapshot.layer.availability;
  app.context.snapshot.layer.stats = { min: 0, max: 9.25, p2: 0, p98: 9.25 };
  assert.match(app.run('buildNumericCodex(snapshot, doc, summary)'), /Complete layer\/time-axis raw range: 0 index to 9\.25 index/);
});

function catalogWorkbench() {
  const app = workbench();
  const listeners = new Map();
  app.context.document.querySelector = (id) => {
    const node = app.get(id);
    node.classList.toggle = (name, enabled) => enabled
      ? node.classList.add(name) : node.classList.remove(name);
    node.setAttribute = (name, value) => { node[name] = value; };
    node.removeAttribute = (name) => { delete node[name]; };
    node.addEventListener = (type, listener) => {
      if (!listeners.has(id)) listeners.set(id, new Map());
      listeners.get(id).set(type, listener);
    };
    return node;
  };
  app.context.document.querySelectorAll = () => [];
  app.context.document.addEventListener = () => {};
  app.context.window.addEventListener = () => {};
  app.context.window.location = { href: 'http://viewer.test/' };
  app.context.optionalJson = async () => ({ worlds: [] });
  app.state.status = { cache_available: true, cache_dir: 'runs/first', cache_revision: 'revision-1' };
  app.state.cacheAvailable = true;
  app.state.cacheIdentity = app.run('cacheIdentityFor(state.status)');
  app.state.mapReady = true;
  app.state.catalog = { world: { cell_count: 2 }, layers: [], sections: ['first', 'second'] };
  app.get('#data-kind').value = 'sections';
  app.get('#data-resource').value = 'first';
  app.run('wireWorkbenchEvents()');
  app.dispatch = (id, type) => listeners.get(id).get(type)({ preventDefault() {} });
  app.dataSnapshot = () => ({
    output: app.get('#data-output').innerHTML,
    title: app.get('#data-title').textContent,
    raw: app.get('#data-raw-link').href,
    page: app.get('#data-page-label').textContent,
    loading: !app.get('#data-loading').classList.contains('hidden'),
  });
  return app;
}

test('family title and coverage help follow returned detail when the server falls back', async () => {
  const app = catalogWorkbench();
  app.get('#data-kind').value = 'families';
  app.get('#data-resource').value = 'wildfire_spread_histories';
  app.get('#family-detail').value = 'scalars';
  app.context.fetchJson = async () => ({ detail: 'full', total: 1,
    rows: [{ front_coverage_status: 'partial_unavailable_inputs', steps: [{ cell: 1 }] }] });
  await app.run('loadDataSelection()');
  assert.equal(app.get('#data-eyebrow').textContent, 'Full nested family');
  assert.match(app.dataSnapshot().output, /steps column contains/);
  assert.doesNotMatch(app.dataSnapshot().output, /Select Full nested records/);

  app.context.fetchJson = async () => ({ detail: 'scalars', total: 1,
    rows: [{ front_coverage_status: 'partial_unavailable_inputs' }] });
  await app.run('loadDataSelection()');
  assert.equal(app.get('#data-eyebrow').textContent, 'Scalar family view');
  assert.match(app.dataSnapshot().output, /Select Full nested records/);
  assert.doesNotMatch(app.dataSnapshot().output, /<th[^>]*>steps<\/th>/);
});

for (const resource of ['second', 'first']) {
  test(`catalog refresh failure preserves newer successful ${resource} selection`, async () => {
    const app = catalogWorkbench();
    app.context.fetchJson = async () => ({ retained: 'initial' });
    await app.run('loadDataSelection()');
    const catalog = deferred();
    app.context.fetchJson = (url) => url.startsWith('/api/catalog')
      ? catalog.promise : Promise.resolve({ retained: 'new selection' });
    const refreshing = app.dispatch('#data-refresh', 'click');
    app.get('#data-resource').value = resource;
    await app.dispatch('#data-resource', 'change');
    const displayed = app.dataSnapshot();
    assert.match(displayed.output, /new selection/);
    assert.equal(displayed.title, resource);
    assert.match(displayed.raw, /revision=revision-1/);
    catalog.reject(new Error('older catalog refresh failed'));
    await refreshing;
    assert.deepEqual(app.dataSnapshot(), displayed);
    assert.equal(app.state.catalogLoading, null);
  });
}

test('catalog refresh failure does not interrupt a newer pending data selection', async () => {
  const app = catalogWorkbench();
  app.context.fetchJson = async () => ({ retained: 'initial' });
  await app.run('loadDataSelection()');
  const displayed = app.dataSnapshot();
  const catalog = deferred();
  const data = deferred();
  app.context.fetchJson = (url) => url.startsWith('/api/catalog') ? catalog.promise : data.promise;
  const refreshing = app.dispatch('#data-refresh', 'click');
  app.get('#data-resource').value = 'second';
  const selecting = app.dispatch('#data-resource', 'change');
  try {
    assert.equal(app.dataSnapshot().loading, true);
    catalog.reject(new Error('older catalog refresh failed'));
    await refreshing;
    assert.equal(app.dataSnapshot().output, displayed.output);
    assert.equal(app.dataSnapshot().loading, true);
  } finally {
    data.resolve({ retained: 'latest data' });
    await selecting;
  }
  assert.match(app.dataSnapshot().output, /latest data/);
  assert.equal(app.dataSnapshot().loading, false);
});

test('catalog refresh current failure remains visible and a successful refresh recovers', async () => {
  const app = catalogWorkbench();
  app.context.fetchJson = async () => ({ retained: 'initial' });
  await app.run('loadDataSelection()');
  const catalog = deferred();
  app.context.fetchJson = () => catalog.promise;
  const refreshing = app.dispatch('#data-refresh', 'click');
  catalog.reject(new Error('<current catalog error>'));
  await refreshing;
  assert.match(app.dataSnapshot().output, /&lt;current catalog error&gt;/);
  assert.equal(app.state.catalogLoading, null);
  app.context.fetchJson = async (url) => url.startsWith('/api/catalog')
    ? app.state.catalog : { retained: 'recovered' };
  await app.dispatch('#data-refresh', 'click');
  assert.match(app.dataSnapshot().output, /recovered/);
  assert.equal(app.dataSnapshot().title, 'first');
  assert.equal(app.dataSnapshot().loading, false);
  assert.match(app.dataSnapshot().raw, /revision=revision-1/);
});

test('catalog refresh superseded by a newer catalog cannot replace its data', async () => {
  const app = catalogWorkbench();
  const older = deferred();
  app.context.fetchJson = () => older.promise;
  const staleRefresh = app.dispatch('#data-refresh', 'click');
  app.context.fetchJson = async (url) => url.startsWith('/api/catalog')
    ? app.state.catalog : { retained: 'latest catalog data' };
  await app.dispatch('#data-refresh', 'click');
  const displayed = app.dataSnapshot();
  older.reject(new Error('superseded catalog'));
  await staleRefresh;
  assert.deepEqual(app.dataSnapshot(), displayed);
});

test('catalog refresh from an old cache cannot replace the new cache data', async () => {
  const app = catalogWorkbench();
  const older = deferred();
  app.context.fetchJson = () => older.promise;
  const staleRefresh = app.dispatch('#data-refresh', 'click');
  // Model the cache epoch invalidation; mesh disposal is outside this data test.
  app.state.cacheEpoch += 1;
  app.state.status.cache_revision = 'revision-2';
  app.state.cacheIdentity = app.run('cacheIdentityFor(state.status)');
  app.context.fetchJson = async () => ({ retained: 'new cache data' });
  await app.dispatch('#data-resource', 'change');
  const displayed = app.dataSnapshot();
  older.reject(new Error('old cache catalog'));
  await staleRefresh;
  assert.deepEqual(app.dataSnapshot(), displayed);
  assert.match(displayed.raw, /revision=revision-2/);
});

test('catalog failure during initial status loading still reports the current error', async () => {
  const app = catalogWorkbench();
  app.state.catalog = null;
  const catalog = deferred();
  app.context.fetchJson = (url) => url === '/api/status'
    ? Promise.resolve(app.state.status) : catalog.promise;
  await app.run('loadServerStatus()');
  catalog.reject(new Error('initial catalog unavailable'));
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(app.dataSnapshot().output, /initial catalog unavailable/);
  assert.equal(app.state.catalogLoading, null);
});

function stageScrubWorkbench(monthly = false) {
  const app = layerWorkbench();
  const listeners = new Map();
  const timers = new Map();
  let nextTimer = 0;
  const query = app.context.document.querySelector;
  app.context.document.querySelector = (id) => {
    const node = query(id);
    node.addEventListener = (type, listener) => listeners.set(`${id}:${type}`, listener);
    return node;
  };
  app.context.document.querySelectorAll = () => [];
  app.context.window.addEventListener = () => {};
  app.context.window.setTimeout = (callback, delay) => {
    const id = ++nextTimer;
    timers.set(id, { callback, delay });
    return id;
  };
  app.context.window.clearTimeout = (id) => timers.delete(id);
  app.context.AbortController = AbortController;
  app.context.cancelAnimationFrame = () => {};
  app.run(`
    three.controls = { addEventListener() {} };
    three.renderer = { domElement: { addEventListener() {} } };
    wireMapEvents();
  `);
  if (monthly) app.context.layers.A.kind = 'numeric_monthly';
  app.calls = [];
  app.context.fetchLayerValues = async (layer, stage, month) => {
    const value = monthly ? month : stage;
    app.calls.push(value);
    return new Float32Array([value]);
  };
  app.dispatch = (id, type) => listeners.get(`${id}:${type}`)();
  app.scrub = (value) => {
    app.get('#stage-slider').value = String(value);
    app.dispatch('#stage-slider', 'input');
  };
  app.flushStageTimers = async () => {
    for (const [id, { callback, delay }] of [...timers]) {
      if (delay !== 120) continue;
      timers.delete(id);
      callback();
    }
    await new Promise((resolve) => setImmediate(resolve));
  };
  app.settle = () => new Promise((resolve) => setImmediate(resolve));
  return app;
}

for (const monthly of [false, true]) {
  test(`deferred ${monthly ? 'month' : 'stage'} scrub cannot replace a newer numeric selection`, async () => {
    const app = stageScrubWorkbench(monthly);
    await app.run('activateLayer(layers.A, { stage: 2, month: 2 })');
    app.calls.length = 0;
    app.scrub(8);
    app.get('#stage-number').value = '4';
    app.dispatch('#stage-number', 'change');
    await app.settle();
    const displayed = app.snapshot();
    assert.equal(monthly ? displayed.month : displayed.stage, 4);
    await app.flushStageTimers();
    assert.deepEqual(app.calls, [4]);
    assert.deepEqual(app.snapshot(), displayed);
    assert.equal(app.state.exportSnapshot[monthly ? 'month' : 'stage'], 4);
    assert.equal(app.get('#stage-label').textContent, monthly ? 'month 5' : 'stage_idx 4');
  });
}

test('deferred scrub cannot supersede a newer pending numeric layer request', async () => {
  const app = stageScrubWorkbench();
  await app.run('activateLayer(layers.A, { stage: 2 })');
  app.calls.length = 0;
  const pending = deferred();
  app.context.fetchLayerValues = (layer, stage) => {
    app.calls.push(stage);
    return stage === 4 ? pending.promise : Promise.resolve(new Float32Array([stage]));
  };
  app.scrub(8);
  app.get('#stage-number').value = '4';
  app.dispatch('#stage-number', 'change');
  try {
    await app.flushStageTimers();
    assert.deepEqual(app.calls, [4]);
    assert.equal(app.state.stage, 4);
    assert.equal(app.state.layerLoading, true);
    assert.equal(app.get('#export-map-image').disabled, true);
  } finally {
    pending.resolve(new Float32Array([4]));
    await app.settle();
  }
  assert.equal(app.state.exportSnapshot.stage, 4);
  assert.deepEqual(app.snapshot().texture, [4]);
});

test('deferred scrub cannot replace a newer stage arrow selection', async () => {
  const app = stageScrubWorkbench();
  await app.run('activateLayer(layers.A, { stage: 2 })');
  app.calls.length = 0;
  app.scrub(8);
  app.dispatch('#stage-fwd', 'click');
  await app.settle();
  await app.flushStageTimers();
  assert.deepEqual(app.calls, [3]);
  assert.equal(app.state.exportSnapshot.stage, 3);
  assert.deepEqual(app.snapshot().texture, [3]);
});

test('reselecting the same layer invalidates its earlier deferred scrub', async () => {
  const app = stageScrubWorkbench();
  await app.run('activateLayer(layers.A, { stage: 2 })');
  app.calls.length = 0;
  app.scrub(8);
  await app.run('activateLayer(layers.A)');
  await app.flushStageTimers();
  assert.deepEqual(app.calls, [2]);
  assert.equal(app.state.exportSnapshot.stage, 2);
});

test('current slider scrubs still coalesce and publish the latest requested slice', async () => {
  const app = stageScrubWorkbench();
  await app.run('activateLayer(layers.A, { stage: 2 })');
  app.calls.length = 0;
  app.scrub(8);
  app.scrub(9);
  assert.deepEqual(app.calls, []);
  await app.flushStageTimers();
  assert.deepEqual(app.calls, [9]);
  assert.equal(app.state.exportSnapshot.stage, 9);
  assert.deepEqual(app.snapshot().texture, [9]);
  assert.equal(app.snapshot().exportCurrent, true);
});

test('aborting map handlers cancels their deferred stage scrub', async () => {
  const app = stageScrubWorkbench();
  await app.run('activateLayer(layers.A, { stage: 2 })');
  app.calls.length = 0;
  app.scrub(8);
  app.run('state.mapEventController.abort()');
  await app.flushStageTimers();
  assert.deepEqual(app.calls, []);
  assert.equal(app.state.exportSnapshot.stage, 2);
});

async function ledgerInspectorWorkbench() {
  const app = inspectorWorkbench();
  app.context.layers.A.source = 'history';
  app.context.fetchLayerValues = async () => new Float32Array([7]);
  app.context.fetchJson = async () => ({ cell: {}, ledgers: {
    history: { fields: { runoff: [1, 2] } },
    other_history: { fields: { runoff: [3, 4] } },
  } });
  await app.run('activateLayer(layers.A, { stage: 0 })');
  await app.run('openInspector(1)');
  app.ledger = () => app.state.inspectorSparklines[0].node.innerHTML;
  app.run('updateInspectorStageMarkers()');
  return app;
}

test('committed stage selection refreshes open inspector markers without replacing its fields', async () => {
  const app = await ledgerInspectorWorkbench();
  assert.match(app.ledger(), /circle cx="0.0"/);
  const body = app.get('#inspector-body').innerHTML;
  const filter = app.get('#inspector-body #inspector-filter');
  filter.value = 'runoff';
  app.context.document.activeElement = filter;
  await app.run('activateLayer(layers.A, { stage: 1 })');
  assert.match(app.ledger(), /circle cx="290.0"/);
  assert.doesNotMatch(app.ledger(), /circle cx="0.0"/);
  assert.doesNotMatch(app.state.inspectorSparklines[1].node.innerHTML, /<circle/);
  assert.equal(app.get('#inspector-body').innerHTML, body);
  assert.equal(filter.value, 'runoff');
  assert.equal(app.context.document.activeElement, filter);
  assert.equal(app.state.exportSnapshot.stage, 1);
});

test('pending, refused and superseded stage requests cannot move inspector markers', async () => {
  const app = await ledgerInspectorWorkbench();
  const first = deferred();
  const second = deferred();
  let count = 0;
  app.context.fetchLayerValues = () => (++count === 1 ? first.promise : second.promise);
  const older = app.run('activateLayer(layers.A, { stage: 1 })');
  const latest = app.run('activateLayer(layers.A, { stage: 0 })');
  assert.match(app.ledger(), /circle cx="0.0"/);
  second.reject(new Error('latest refused'));
  await latest;
  first.resolve(new Float32Array([9]));
  await older;
  assert.match(app.ledger(), /circle cx="0.0"/);
  assert.equal(app.state.exportSnapshot.stage, 0);
});

test('inspector opened during stage loading labels the displayed slice until commit', async () => {
  const app = await ledgerInspectorWorkbench();
  const pending = deferred();
  app.context.fetchLayerValues = () => pending.promise;
  const loading = app.run('activateLayer(layers.A, { stage: 1 })');
  await app.run('openInspector(2)');
  assert.match(app.get('#inspector-body').innerHTML, /circle cx="0.0"/);
  assert.doesNotMatch(app.get('#inspector-body').innerHTML, /circle cx="290.0"/);
  pending.resolve(new Float32Array([8]));
  await loading;
  assert.match(app.ledger(), /circle cx="290.0"/);
});

test('monthly and static commits clear ledger markers even with a matching source name', async () => {
  for (const kind of ['numeric_monthly', 'numeric']) {
    const app = await ledgerInspectorWorkbench();
    app.context.layers.B.source = 'history';
    app.context.layers.B.kind = kind;
    await app.run('activateLayer(layers.B, { stage: 1, month: 11 })');
    assert.doesNotMatch(app.ledger(), /<circle/);
  }
});

test('inspector close and cache reset discard detached marker targets', async () => {
  for (const action of ["document.querySelector('#inspector-close').click()", 'resetCacheDerivedState()']) {
    const app = await ledgerInspectorWorkbench();
    const node = app.state.inspectorSparklines[0].node;
    const before = node.innerHTML;
    app.run(action);
    assert.equal(app.state.inspectorSparklines.length, 0);
    app.run('updateInspectorStageMarkers()');
    assert.equal(node.innerHTML, before);
  }
});
