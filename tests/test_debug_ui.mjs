// Exercise the real workbench handlers with controlled HTTP completion order.
// The small DOM stand-in keeps these race regressions independent of WebGL.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

// Helper modules import each other; the harness concatenates them in
// dependency order instead, so their import lines are dropped.
const uiSource = (name) => readFileSync(new URL(`../src/magic_geo/debug_ui/${name}.js`, import.meta.url), 'utf8')
  .replace(/^import .*;\n/gm, '').replace(/^export /gm, '');
const CONTROLLERS = [
  ['config-workbench', 'createConfigWorkbench'],
  ['operations-workbench', 'createOperationsWorkbench'],
  ['home-workbench', 'createHomeWorkbench'],
  ['command-palette', 'createCommandPalette'],
  ['new-world', 'createNewWorldDialog'],
];
const controllerSources = CONTROLLERS.map(([name]) => uiSource(name));
// Shared helper modules are imported by app.js; the harness provides them as
// the module scope would, so app.js never sees an undeclared import binding.
const helperSources = ['ui', 'layer_docs', 'palettes', 'colormaps', 'map-navigation'].map(uiSource);
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
    classList: { toggle: (name, force) => { const on = force ?? !classes.has(name); if (on) classes.add(name); else classes.delete(name); return on; }, add: (name) => classes.add(name), remove: (name) => classes.delete(name), contains: (name) => classes.has(name) },
    appendChild(child) { children.push(child); },
    querySelector() { return null; }, querySelectorAll() { return []; },
    attributes: {}, listeners: {},
    setAttribute(name, value) { this.attributes[name] = value; },
    addEventListener(name, action) { this.listeners[name] = action; },
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
  // Controllers have their own module scope. Missing imports must fail here
  // just as they do in a browser, rather than seeing app.js globals by accident.
  for (const [index, [, name]] of CONTROLLERS.entries()) {
    const moduleContext = vm.createContext({ document: context.document, window: context.window, Option: context.Option, URLSearchParams, console });
    context[name] = vm.runInContext(controllerSources[index] + `\n${name}`, moduleContext);
  }
  for (const helper of helperSources) vm.runInContext(helper, context);
  vm.runInContext(source, context);
  vm.runInContext('initializeWorkbenchControllers()', context);
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
  app.state.configSchema = seasonalSchema();
  app.context.fetchJson = (url) => url.startsWith('/api/config/template') ? template.promise : validation.promise;
  const resetting = app.run('resetConfigTemplate()');
  const validating = app.run('validateConfig()');
  template.resolve({ profile: 'smoke', yaml: 'seed: 2', config: { config_version: 2 } });
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
  app.get('#operation-result').dataset.jobId = 'previous-job';
  app.run('generateFromSavedConfig()');
  assert.equal(app.get('#operation-result').dataset.jobId, undefined);
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
      assert.match(app.get('#operation-result').textContent, /Job created completed/);
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
  for (const name of ['WebGLRenderer', 'Scene', 'Color', 'PerspectiveCamera', 'BufferGeometry', 'BufferAttribute', 'DataTexture', 'ShaderMaterial', 'Mesh', 'Vector4', 'WebGLRenderTarget', 'SphereGeometry']) {
    app.context.THREE[name] = RenderObject;
  }
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
  // A constant layer has one colour; the codex must not invent a 0-to-1 ramp.
  assert.match(masked, /Every finite cell in this layer has the value 0 index, drawn in a single color/);
  assert.doesNotMatch(masked, /normalized over|Scale position/);

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
    // Months are typed 1-12 like their label; stages by their 0-based index.
    app.get('#stage-number').value = monthly ? '5' : '4';
    app.dispatch('#stage-number', 'change');
    await app.settle();
    const displayed = app.snapshot();
    assert.equal(monthly ? displayed.month : displayed.stage, 4);
    await app.flushStageTimers();
    assert.deepEqual(app.calls, [4]);
    assert.deepEqual(app.snapshot(), displayed);
    assert.equal(app.state.exportSnapshot[monthly ? 'month' : 'stage'], 4);
    assert.equal(app.get('#stage-label').textContent, monthly ? 'month 5 · May' : 'stage_idx 4');
    assert.equal(app.get('#stage-number').value, monthly ? '5' : '4', 'the box and the label agree');
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

test('opening a config preserves exact YAML and enables generation without a redundant save', async () => {
  const app = workbench();
  const yaml = '# keep this\nconfig_version: 2\nrun:\n  seed: 18446744073709551615\n';
  app.context.fetchJson = async () => ({ path: '/external/configs/world.yaml', name: 'world.yaml', revision: 'r1', valid: true, yaml });
  await app.run("openConfigFile('/external/configs/world.yaml', {initial:true})");
  assert.equal(app.get('#config-yaml').value, yaml);
  assert.equal(app.get('#config-generate').disabled, false);
  assert.equal(app.state.savedConfig.path, '/external/configs/world.yaml');
  assert.equal(app.run('configHasUnsavedChanges()'), false);
  app.get('#config-yaml').value += '# editing\n';
  app.run('configEdited()');
  assert.equal(app.get('#config-generate').disabled, true);
  assert.equal(app.run('configHasUnsavedChanges()'), true);
});

test('config file response cannot replace edits made during loading', async () => {
  const app = workbench();
  const pending = deferred();
  app.context.fetchJson = () => pending.promise;
  const opening = app.run("openConfigFile('/external/world.yaml', {initial:true})");
  app.get('#config-yaml').value = 'local draft';
  app.run('configEdited()');
  pending.resolve({path: '/external/world.yaml', name: 'world.yaml', yaml:'server file', valid:true});
  await opening;
  assert.equal(app.get('#config-yaml').value, 'local draft');
  assert.equal(app.state.configSource, null);
});

test('competing config opens commit only the last selected file', async () => {
  const app = workbench();
  const first = deferred(), second = deferred();
  app.context.fetchJson = (url) => url.includes('first') ? first.promise : second.promise;
  const older = app.run("openConfigFile('/first.yaml', {initial:true})");
  const newer = app.run("openConfigFile('/second.yaml', {initial:true})");
  second.resolve({path:'/second.yaml', name:'second.yaml', yaml:'second', valid:true});
  await newer;
  first.resolve({path:'/first.yaml', name:'first.yaml', yaml:'first', valid:true});
  await older;
  assert.equal(app.get('#config-yaml').value, 'second');
  assert.equal(app.state.configSource.path, '/second.yaml');
});

test('save of an opened file sends its revision and never force-retries a stale source', async () => {
  const app = workbench();
  app.get('#config-name').value = 'world.yaml';
  app.get('#config-yaml').value = 'edited';
  app.state.configSource = {name:'world.yaml', path:'/external/world.yaml', revision:'old'};
  let calls = 0, prompts = 0;
  app.context.window.confirm = () => { prompts += 1; return true; };
  app.context.fetchJson = async (_url, options) => {
    calls += 1;
    assert.equal(options.body.path, '/external/world.yaml');
    assert.equal(options.body.revision, 'old');
    throw Object.assign(new Error('File changed on disk'), {status:409});
  };
  await app.run('saveConfig()');
  assert.equal(calls, 1);
  assert.equal(prompts, 0);
  assert.equal(app.get('#config-yaml').value, 'edited');
  assert.match(app.get('#config-result').textContent, /changed on disk/);
});

test('disabled cache options are omitted and invalid numeric inputs are rejected before submit', () => {
  const app = workbench();
  app.get('#operation-fields').querySelectorAll = () => [
    {name:'debug_output', value:'/old/cache', disabled:true, dataset:{valueType:'path'}},
    {name:'cells', value:'128', dataset:{valueType:'integer'}},
  ];
  assert.equal(JSON.stringify(app.run('collectOperationArguments()')), '{"cells":128}');
  app.get('#operation-fields').querySelectorAll = () => [
    {name:'cells', value:'1.5', dataset:{valueType:'integer'}},
  ];
  assert.throws(() => app.run('collectOperationArguments()'), /whole number/);
});

test('data resource filtering is recoverable when nothing matches', () => {
  const app = workbench();
  app.state.catalog = {families:{river_network:{row_count:12}, settlements:{row_count:3}}};
  app.get('#data-kind').value = 'families';
  app.get('#data-resource-search').value = 'river network';
  app.run('populateDataResources()');
  assert.equal(app.get('#data-resource').children.length, 1);
  assert.equal(app.get('#data-resource').children[0].value, 'river_network');
  app.get('#data-resource-search').value = 'absent';
  app.run('populateDataResources()');
  assert.equal(app.get('#data-resource').disabled, true);
  assert.equal(app.get('#data-resource-wrap').classList.contains('hidden'), false);
  app.get('#data-resource-search').value = '';
  app.run('populateDataResources()');
  assert.equal(app.get('#data-resource').disabled, false);
  assert.equal(app.get('#data-resource').children.length, 2);
});

test('generation shows measured stage work without inventing overall completion', () => {
  const app = workbench();
  app.context.job = { id: 'climate', operation: 'generate', status: 'running', elapsed_seconds: 91,
    phase_elapsed_seconds: 14, seconds_since_activity: 2,
    progress: { phase: 'climate', label: 'Calculating seasonal climate', detail: 'Climate cycle 3, month 7 of 12.', current: 7, total: 12 } };
  app.run('renderJobDetail(job)');
  const html = app.get('#job-detail').innerHTML;
  assert.match(html, /Calculating seasonal climate/);
  assert.match(html, /max="12" value="7"/);
  assert.match(html, /7 \/ 12 · current stage/);
  assert.match(html, /1m 31s/);
  assert.doesNotMatch(html, /NaN|58%/);
  app.context.job.progress = { label: 'Preparing map data' };
  app.run('renderJobDetail(job)');
  assert.match(app.get('#job-detail').innerHTML, /Overall percentage and finish time are not estimated/);
  assert.doesNotMatch(app.get('#job-detail').innerHTML, /value="0"/);
});

test('queue wait and stop acknowledgement use worker state', () => {
  const app = workbench();
  app.context.job = { id: 'waiting', operation: 'generate', status: 'queued', queue_position: 3, elapsed_seconds: 0, phase_elapsed_seconds: 72 };
  app.run('renderJobDetail(job)');
  assert.match(app.get('#job-detail').innerHTML, /Queue position 3/);
  assert.match(app.get('#job-detail').innerHTML, /1m 12s/);
  app.context.job = { ...app.context.job, status: 'running', cancel_requested: true, cancellable: false };
  app.run('renderJobDetail(job)');
  assert.match(app.get('#job-detail').innerHTML, /Waiting for the worker and its subprocesses to stop/);
  assert.equal(app.get('#job-cancel').disabled, true);
  assert.equal(app.get('#job-cancel').textContent, 'Stopping…');
});

test('map failure preserves the generated world and recovery uses its immutable snapshot', () => {
  const app = workbench();
  app.get('#operation-form').querySelector = () => element();
  app.state.operations = [{ name: 'export-debug' }];
  app.context.setView = () => {};
  app.context.job = { id: 'saved', operation: 'generate', status: 'failed', world_available: true,
    world_path: '/workspace/.web/artifacts/saved/world.json', error: 'Map export: unavailable dependency',
    artifacts: [{ name: 'output', available: true, path: '/workspace/world.json' }] };
  app.run('renderJobDetail(job)');
  assert.match(app.get('#job-detail').innerHTML, /World saved · browser map failed/);
  assert.match(app.get('#job-detail').innerHTML, /Map export: unavailable dependency/);
  assert.doesNotMatch(app.get('#job-detail').innerHTML, /<progress/);
  const action = app.get('#job-actions').children.find((button) => button.textContent === 'Prepare browser map');
  action.listeners.click();
  assert.equal(app.state.operationDrafts['export-debug'].world, app.context.job.world_path);
});

test('active detail updates preserve disclosure nodes and unchanged logs', () => {
  const app = workbench();
  app.context.job = { id: 'same', operation: 'generate', status: 'running', log: 'first output', progress: { label: 'Climate' } };
  app.run('renderJobDetail(job)');
  const root = app.get('#job-detail');
  const original = root.innerHTML;
  const status = element(), artifacts = element(), log = element(), meta = element();
  log.textContent = 'first output';
  root.querySelector = (selector) => ({ '.job-status-content': status, '.job-artifacts': artifacts, '.job-log': log, '.job-meta': meta })[selector] || null;
  app.context.job.progress = { label: 'Erosion', current: 2, total: 4 };
  app.run('renderJobDetail(job)');
  assert.equal(root.innerHTML, original, 'interactive disclosure subtree was not replaced');
  assert.match(status.innerHTML, /Erosion/);
  assert.equal(log.textContent, 'first output');
});

test('a slow job poll is coalesced and its response still updates the UI', async () => {
  const app = workbench();
  const reply = deferred();
  let calls = 0;
  app.context.fetchJson = () => { calls += 1; return reply.promise; };
  const first = app.run('refreshJobs()');
  const second = app.run('refreshJobs()');
  assert.equal(calls, 1);
  reply.resolve({ jobs: [{ id: 'finished', status: 'succeeded', operation: 'render' }] });
  await Promise.all([first, second]);
  assert.equal(app.state.jobs[0].id, 'finished');
  assert.equal(app.get('#jobs-poll-state').textContent, 'Live');
  assert.equal(app.state.jobsRefreshPending, null);
});

test('failed terminal detail refresh preserves the snapshot and recovers on next poll', async () => {
  const app = workbench();
  const job = { id: 'finished', operation: 'render', status: 'succeeded', log: 'saved' };
  let fail = false;
  app.context.fetchJson = async (url) => {
    if (url === '/api/jobs') return { jobs: [job] };
    if (fail) throw new Error('Temporary detail failure');
    return job;
  };
  await app.run('selectJob("finished")');
  const snapshot = app.get('#job-detail').innerHTML;
  fail = true;
  await app.run('selectJob("finished")');
  assert.equal(app.get('#job-detail').innerHTML, snapshot);
  assert.match(app.get('#job-connection').textContent, /Temporary detail failure/);
  fail = false;
  await app.run('refreshJobs()');
  assert.equal(app.state.jobDetailFailed, false);
  assert.equal(app.get('#job-connection').textContent, '');
});

test('reload discovers running work and retains visible background completion', async () => {
  const app = workbench();
  let job = { id: 'running', operation: 'generate', status: 'running', progress: { label: 'Calculating climate' } };
  app.context.fetchJson = async (url) => url === '/api/jobs' ? { jobs: [job] } : job;
  await app.run('refreshJobs()');
  assert.equal(app.state.selectedJobId, 'running');
  assert.match(app.get('#job-activity').textContent, /Calculating climate/);
  job = { ...job, status: 'succeeded', cache_dir: '/workspace/debug' };
  await app.run('refreshJobs()');
  assert.match(app.get('#job-activity').textContent, /Browser map ready/);
});

test('stage changes update job history without replacing its focused row', () => {
  const app = workbench();
  app.state.jobs = [{ id: 'stable', status: 'running', operation: 'generate', progress: { label: 'Climate' } }];
  app.run('renderJobs()');
  const row = app.get('#jobs-list').children[0];
  app.state.jobs[0].progress.label = 'Erosion';
  app.run('renderJobs()');
  assert.equal(app.get('#jobs-list').children[0], row);
  assert.match(row.innerHTML, /Erosion/);
  assert.match(row.attributes['aria-label'], /stable, Erosion/);
});

test('confirmed cancellation is terminal even when cancellation-requested remains true', () => {
  const app = workbench();
  app.context.job = { id: 'stopped', operation: 'generate', status: 'cancelled', cancel_requested: true, cancellable: false };
  app.run('renderJobDetail(job)');
  assert.match(app.get('#job-detail').innerHTML, /Job cancelled/);
  assert.doesNotMatch(app.get('#job-detail').innerHTML, /Stopping the job|Waiting for the worker and its subprocesses/);
  assert.equal(app.get('#job-cancel').classList.contains('hidden'), true);
});

test('persistent activity follows actual running work ahead of newer queued jobs', async () => {
  const app = workbench();
  const running = { id: 'older', operation: 'generate', status: 'running', progress: { label: 'Climate is running' } };
  app.context.fetchJson = async (url) => url === '/api/jobs'
    ? { jobs: [{ id: 'newer', status: 'queued', operation: 'generate' }, running] } : running;
  await app.run('refreshJobs()');
  assert.equal(app.state.selectedJobId, 'older');
  assert.match(app.get('#job-activity').textContent, /Climate is running/);
});

test('an older cancellation completion cannot enable another selected job cancellation', async () => {
  const app = workbench();
  const response = deferred();
  app.state.selectedJobId = 'old';
  const newer = { id: 'new', status: 'running', cancel_requested: true, cancellable: false };
  app.context.fetchJson = (url) => url.endsWith('/cancel') ? response.promise : Promise.resolve(url === '/api/jobs' ? { jobs: [newer] } : newer);
  const cancel = app.run('cancelSelectedJob()');
  app.state.selectedJobId = 'new';
  app.state.selectedJob = newer;
  app.get('#job-cancel').disabled = true;
  app.get('#job-cancel').textContent = 'Stopping…';
  response.resolve({ id: 'old', status: 'cancelled' });
  await cancel;
  assert.equal(app.get('#job-cancel').disabled, true);
  assert.equal(app.get('#job-cancel').textContent, 'Stopping…');
});

test('terminal map supersession refreshes the selected result and removes the stale map action', async () => {
  const app = workbench();
  let job = { id: 'older', operation: 'generate', status: 'succeeded', cache_dir: '/workspace/debug', world_available: true,
    artifacts: [{ name: 'output', path: '/workspace/world.json', available: true }] };
  app.context.fetchJson = async (url) => url === '/api/jobs' ? { jobs: [job] } : job;
  await app.run('selectJob("older")');
  assert.ok(app.get('#job-actions').children.some((button) => button.textContent === 'Open map'));
  job = { ...job, cache_dir: null, map_superseded: true };
  await app.run('refreshJobs()');
  assert.match(app.get('#job-detail').innerHTML, /newer job replaced the browser map/);
  assert.ok(!app.get('#job-actions').children.some((button) => button.textContent === 'Open map'));
  assert.ok(app.get('#job-actions').children.some((button) => button.textContent === 'Prepare browser map'));
});

test('cancelled output destinations cannot be mistaken for produced artifacts', () => {
  const app = workbench();
  app.context.job = { id: 'cancelled', operation: 'generate', status: 'cancelled', artifacts: [
    { name: 'output', path: '/workspace/world.json', kind: 'file', available: false },
    { name: 'debug_output', path: '/workspace/debug', kind: 'cache', available: false },
  ] };
  app.run('renderJobDetail(job)');
  assert.match(app.get('#job-detail').innerHTML, /No download produced by this job/);
  assert.match(app.get('#job-detail').innerHTML, /No browser map for this job/);
  app.context.job = { ...app.context.job, status: 'succeeded', cache_dir: '/workspace/debug' };
  app.run('renderJobDetail(job)');
  assert.match(app.get('#job-detail').innerHTML, /Available via Open map/);
});

// ---------------------------------------------------------------------------
// Workbench redesign: navigation, discovery and feedback helpers

test('layer topics group physical domains and labels keep units separate', () => {
  const app = workbench();
  const topic = (name, source = 'cells') => app.run(`layerTopic(${JSON.stringify({ name, source })})`);
  assert.equal(topic('elevation_m'), 'terrain');
  assert.equal(topic('precipitation_mm_y'), 'climate');
  assert.equal(topic('groundwater_recharge_mm_y'), 'water');
  assert.equal(topic('glacial_sediment_net_m'), 'ice');
  assert.equal(topic('ocean_current_temperature_c'), 'ocean');
  assert.equal(topic('settlement_score'), 'people');
  assert.equal(topic('precipitation_monthly_mm', 'cells_monthly'), 'climate');
  assert.equal(app.run("layerLabel({ name: 'precipitation_mm_y' })"), 'Precipitation');
  assert.equal(app.run("layerUnit({ name: 'precipitation_mm_y' })"), 'mm/year');
  assert.equal(app.run("layerLabel({ name: 'soil_ph' })"), 'Soil pH');
  assert.equal(app.run("layerLabel({ name: 'agricultural_potential_index' })"), 'Agricultural potential index');
  assert.equal(app.run("layerUnit({ name: 'agricultural_potential_index' })"), '');
});

test('categorical guide colors are semantic, unique per layer and stable for unlisted codes', () => {
  const app = workbench();
  const palette = app.run("categoryPalette(['ocean', 'hot_desert', 'forest', 'marine'])");
  assert.equal(palette[0], '#2c5d8f', 'ocean reads as water');
  assert.equal(palette[1], '#e3c58f', 'desert reads as dry land');
  assert.equal(new Set(palette).size, palette.length, 'marine must not reuse the ocean color');
  assert.equal(app.run("categoryColor(0, ['Af', 'BWh'])"), '#0000ff');
  assert.equal(app.run("categoryColor(1, ['Af', 'BWh'])"), '#ff0000');
  assert.equal(app.run("categoryColor(5, ['basalt', 'granite'])"), '#edc948');
  assert.equal(app.run("Array.from(categoryPaletteData(['ocean']).slice(0, 4)).join(',')"), '44,93,143,255');
});

test('command palette ranks direct matches first and limits noisy groups', () => {
  const app = workbench();
  app.state.manifest = { layers: [
    { id: 'cells/species_record_descriptors_supported', source: 'cells', name: 'species_record_descriptors_supported', kind: 'categorical' },
    { id: 'cells/precipitation_mm_y', source: 'cells', name: 'precipitation_mm_y', kind: 'numeric' },
    ...Array.from({ length: 60 }, (_, index) => ({ id: `cells/elevation_${index}`, source: 'cells', name: `elevation_${index}`, kind: 'numeric' })),
  ] };
  app.state.worlds = [{ cache_dir: 'runs/aurora/debug', name: 'aurora', cell_count: 512 }];
  const precip = app.run("commandPalette.search('precip')");
  assert.equal(precip[0].title, 'Precipitation');
  const elevation = app.run("commandPalette.search('elevation')");
  assert.ok(elevation.filter((item) => item.group === 'Layers').length <= 40);
  assert.equal(app.run("commandPalette.search('aurora')")[0].group, 'Worlds');
  const suggested = app.run("commandPalette.search('')");
  assert.ok(suggested.some((item) => item.title === 'New world from a profile…'));
  assert.ok(!suggested.some((item) => item.group === 'Layers'), 'an empty query shows actions, not 60 layers');
});

test('YAML highlighting escapes markup and colours keys, numbers and comments', () => {
  const app = workbench();
  const line = app.run(`configWorkbench.highlightYamlLine("  seed: 42 # <b>note</b>")`);
  assert.match(line, /<span class="tok-key">seed<\/span>/);
  assert.match(line, /<span class="tok-num">42<\/span>/);
  assert.match(line, /<span class="tok-com"># &lt;b&gt;note&lt;\/b&gt;<\/span>/);
  assert.doesNotMatch(line, /<b>/);
  assert.match(app.run(`configWorkbench.highlightYamlLine("name: 'a # not a comment'")`), /tok-str/);
  assert.doesNotMatch(app.run(`configWorkbench.highlightYamlLine("name: 'a # not a comment'")`), /tok-com/);
  assert.match(app.run(`configWorkbench.highlightYamlLine("preserve: true")`), /tok-bool/);
});

test('generation from a saved file gives each world its own untouched output folders', () => {
  const app = workbench();
  app.state.status = { workspace: 'runs', paths: { output_dir: 'runs' } };
  app.state.operations = [{ name: 'generate', fields: [
    { name: 'output', default: 'runs/world.json' }, { name: 'debug_output', default: 'runs/debug' },
  ] }];
  app.state.savedConfig = { path: 'runs/configs/aurora.yaml', yaml: 'x', name: 'aurora.yaml', valid: true };
  app.get('#config-generate').disabled = false;
  const inputs = { config: element(), output: element(), debug_output: element() };
  Object.entries(inputs).forEach(([name, input]) => { input.name = name; });
  inputs.output.value = 'runs/world.json';
  inputs.debug_output.value = 'custom/cache';
  app.get('#operation-fields').querySelectorAll = () => Object.values(inputs);
  app.get('#operation-fields').querySelector = (selector) => (selector === '[name="config"]' ? inputs.config : null);
  app.context.renderOperationForm = () => {};
  app.context.setView = (name) => { app.state.activeView = name; };
  app.run('generateFromSavedConfig()');
  assert.equal(inputs.config.value, 'runs/configs/aurora.yaml');
  assert.equal(inputs.output.value, 'runs/aurora/world.json');
  assert.equal(inputs.debug_output.value, 'custom/cache', 'a typed destination is never replaced');
});

test('view hashes carry shareable map state without leaking into other views', () => {
  const app = workbench();
  const parsed = app.run("parseViewHash('#map?layer=cells%2Fbiome&stage=3&month=7&proj=mollweide')");
  assert.equal(parsed.name, 'map');
  assert.deepEqual(JSON.parse(JSON.stringify(parsed.mapParams)), { layer: 'cells/biome', stage: 3, month: 6, projection: 'mollweide' });
  assert.equal(app.run("parseViewHash('#config').mapParams"), null);
  assert.equal(app.run("parseViewHash('#map?proj=spiral').mapParams"), null, 'unknown projections are ignored');
  app.state.activeLayer = { id: 'cells_monthly/temperature_monthly_c', kind: 'numeric_monthly' };
  app.state.month = 6;
  app.state.projection = 'equirect';
  assert.equal(app.run('mapUrlHash()'), '#map?layer=cells_monthly%2Ftemperature_monthly_c&month=7&proj=equirect');
});

test('job notifications fire only for transitions observed in this session', () => {
  const app = workbench();
  const toasts = [];
  app.context.toast = (options) => { toasts.push(options); return { dismiss() {} }; };
  app.state.operations = [{ name: 'generate', title: 'Generate world' }];
  app.state.worlds = [{ cache_dir: 'runs/aurora/debug', name: 'aurora' }];
  const running = [{ id: 'a', operation: 'generate', status: 'running', progress: { label: 'Solving climate' } }];
  app.run(`onJobsChanged(null, ${JSON.stringify(running)})`);
  assert.equal(toasts.length, 0, 'initial load never announces old results');
  assert.equal(app.context.document.title, 'Solving climate · magic-geo');
  app.run(`onJobsChanged(${JSON.stringify(running)}, ${JSON.stringify([{ ...running[0], status: 'succeeded', cache_dir: 'runs/aurora/debug' }])})`);
  assert.equal(toasts.length, 1);
  assert.equal(toasts[0].tone, 'success');
  assert.match(toasts[0].message, /aurora/);
  assert.equal(toasts[0].action.label, 'Open map');
  assert.equal(app.context.document.title, 'magic-geo workbench');
  app.run(`onJobsChanged(${JSON.stringify(running)}, ${JSON.stringify([{ ...running[0], status: 'failed', error: 'native core missing' }])})`);
  assert.equal(toasts[1].tone, 'error');
  assert.match(toasts[1].message, /native core missing/);
});

test('home lists the selected world first and explains an empty workspace', () => {
  const app = workbench();
  app.state.activeView = 'home';
  app.state.status = { cache_dir: 'runs/b/debug', version: '0.1.0', workspace: 'runs' };
  app.state.cacheAvailable = true;
  app.state.configFiles = [{ path: 'configs/seeds/aurora.yaml', name: 'aurora.yaml', world_name: 'aurora_realm', valid: true }];
  app.state.worlds = [
    { cache_dir: 'runs/a/debug', name: 'Older <world>', cell_count: 128, modified_ns: 2e18 },
    { cache_dir: 'runs/b/debug', name: 'Current', cell_count: 4096, modified_ns: 1e18 },
  ];
  app.run('renderHome()');
  const worlds = app.get('#home-worlds').innerHTML;
  assert.ok(worlds.indexOf('Current') < worlds.indexOf('Older'), 'the world on screen is listed first');
  assert.match(worlds, /Older &lt;world&gt;/);
  assert.match(worlds, /4,096 cells/);
  assert.match(app.get('#home-examples').innerHTML, /aurora realm/);
  assert.match(app.get('[data-home="map-status"]').textContent, /Current · 4,096 cells/);
  app.state.worlds = [];
  app.run('renderHome()');
  assert.match(app.get('#home-worlds').innerHTML, /No prepared worlds in this workspace yet/);
});

// ---------------------------------------------------------------------------
// World view: colour scales, navigation and map chrome

const colormapCases = JSON.parse(readFileSync(new URL('./fixtures/colormap_scale_cases.json', import.meta.url), 'utf8')).cases;

test('numeric layers resolve to the same scales and colours as the CLI export', () => {
  const app = workbench();
  assert.ok(colormapCases.length >= 8);
  for (const testCase of colormapCases) {
    app.context.testLayer = testCase.layer;
    const scale = app.run('numericScale(testLayer)');
    assert.equal(scale.mode, testCase.scale.mode, testCase.why);
    assert.equal(scale.colormap, testCase.scale.colormap, testCase.why);
    assert.ok(Math.abs(scale.lo - testCase.scale.lo) < 1e-9 && Math.abs(scale.hi - testCase.scale.hi) < 1e-9, testCase.why);
    for (const [value, color] of testCase.samples) {
      app.context.sampleValue = value;
      assert.equal(app.run('scaleHex(numericScale(testLayer), sampleValue)'), color, `${testCase.layer.name} at ${value}`);
    }
  }
  // The shader samples floor(t * 256); t = 1 must stay on the last texel.
  assert.equal(app.run('lutIndex(1)'), 255);
  assert.equal(app.run('lutIndex(0.5)'), 128);
  assert.equal(app.run('lutIndex(Number.NaN)'), 0);
});

test('legend ticks are nice numbers and a split scale always labels its pivot', () => {
  const app = workbench();
  assert.deepEqual(Array.from(app.run('niceTicks(0, 100, 5)')), [0, 20, 40, 60, 80, 100]);
  assert.deepEqual(Array.from(app.run('niceTicks(-0.3, 0.7, 5)')), [-0.2, 0, 0.2, 0.4, 0.6]);
  const terrain = app.run("numericScale({ name: 'elevation_m', kind: 'numeric', stats: { min: -9000, max: 7000, p2: -6000, p98: 3000 } })");
  app.context.terrain = terrain;
  const ticks = Array.from(app.run('scaleTicks(terrain, 5)'));
  assert.ok(ticks.includes(0), 'sea level is labelled');
  assert.equal(app.run('scalePosition(terrain, 0)'), 0.5);
  for (const t of [0, 0.25, 0.5, 0.75, 1]) {
    app.context.t = t;
    assert.ok(Math.abs(app.run('scalePosition(terrain, scaleValueAt(terrain, t))') - t) < 1e-12);
  }
  assert.match(app.run('scaleSummary(terrain)'), /Terrain · 2nd–98th percentile · split at 0/);
  app.state.scaleOptions = { colormap: 'viridis', range: 'full' };
  const full = app.run("numericScale({ name: 'elevation_m', kind: 'numeric', stats: { min: -9000, max: 7000, p2: -6000, p98: 3000 } }, state.scaleOptions)");
  assert.deepEqual([full.colormap, full.mode, full.lo, full.hi, full.clipLow, full.clipHigh], ['viridis', 'linear', -9000, 7000, false, false]);
});

test('map projections round-trip and fly-to follows van Wijk and Nuij', () => {
  const app = workbench();
  for (const projection of ['equirect', 'mollweide']) {
    for (const [lat, lon] of [[0, 0], [45, 90], [-60, -150], [89, 179], [-33.9, 151.2]]) {
      app.context.point = { lat, lon, projection };
      const back = app.run('(() => { const [x, y] = projectToPlane(point.lat, point.lon, point.projection); return unprojectFromPlane(x, y, point.projection); })()');
      assert.ok(Math.abs(back.lat - lat) < 1e-6 && Math.abs(back.lon - lon) < 1e-6, `${projection} ${lat},${lon}`);
    }
  }
  assert.equal(app.run('unprojectFromPlane(1.9, 0.9, "mollweide")'), null, 'corners outside the ellipse are off the map');
  assert.equal(app.run('wrapLongitude(190)'), -170);
  assert.equal(app.run('wrapLongitude(-540)'), -180);
  assert.ok(Math.abs(app.run('greatCircleAngle({ lat: 0, lon: 0 }, { lat: 0, lon: 90 })') - Math.PI / 2) < 1e-12);
  const middle = app.run('interpolateGreatCircle({ lat: 0, lon: 0 }, { lat: 0, lon: 90 })(0.5)');
  assert.ok(Math.abs(middle.lat) < 1e-9 && Math.abs(middle.lon - 45) < 1e-9);
  // The optimal path starts and ends exactly at the two views, and zooms out
  // in between when the pan is long relative to the view width.
  const path = app.run('zoomPath([0, 0, 1], [10, 0, 1])');
  assert.deepEqual(Array.from(path.at(0)).map((v) => Number(v.toFixed(9))), [0, 0, 1]);
  assert.deepEqual(Array.from(path.at(1)).map((v) => Number(v.toFixed(9))), [10, 0, 1]);
  assert.ok(path.at(0.5)[2] > 3, 'long pans rise to a wider view');
  const zoomOnly = app.run('zoomPath([0, 0, 1], [0, 0, 8])');
  assert.ok(Math.abs(zoomOnly.length - Math.log(8) / 1.42) < 1e-12);
  assert.equal(app.run('formatLatLon(12.345, -56.789, 2)'), '12.35° N, 56.79° W');
  assert.equal(app.run('formatLatLon(-0.001, 0, 1)'), '0.0°, 0.0°');
  assert.equal(app.run('niceDistance(734)'), 500);
  assert.equal(app.run('formatDistance(12500)'), '12,500 km');
  assert.equal(app.run('formatDistance(0.25)'), '250 m');
});

function navigatorHarness(app, { width = 800, height = 400, reduced = true } = {}) {
  const listeners = {};
  app.context.fakeElement = {
    getBoundingClientRect: () => ({ left: 0, top: 0, width, height }),
    addEventListener: (type, listener) => { listeners[type] = listener; },
    classList: { add() {}, remove() {} },
  };
  app.context.fakeCamera = {
    fov: 50, near: 0.1, far: 100, position: { set() {} }, up: { set() {} }, lookAt() {}, updateProjectionMatrix() {},
  };
  app.context.fakeMorph = { value: 0, proj2D: 0 };
  app.context.AbortController = AbortController;
  app.context.reduced = reduced;
  const nav = app.run('createMapNavigator({ element: fakeElement, camera: fakeCamera, getMorph: () => fakeMorph, cellCount: 4096, reducedMotion: () => reduced, now: () => 0 })');
  return { nav, listeners, morph: app.context.fakeMorph, width, height };
}

test('the navigator keeps the same place and scale across projections', () => {
  const app = workbench();
  const { nav, morph, width, height } = navigatorHarness(app);
  nav.setView({ lat: 35, lon: -120, span: 0.2 });
  nav.update();
  const centre = nav.screenToLatLon(width / 2, height / 2);
  assert.ok(Math.abs(centre.lat - 35) < 1e-6 && Math.abs(centre.lon + 120) < 1e-6, 'globe centre ray hits the view centre');
  // Scale bar maths: 0.2 rad over 400 px on a 6371 km planet ≈ 3.19 km/px.
  assert.ok(Math.abs(nav.kilometresPerPixel(6371) / ((0.2 * 6371) / height) - 1) < 0.02);
  for (const [projection, blend] of [['equirect', 0], ['mollweide', 1]]) {
    nav.setProjection(projection);
    Object.assign(morph, { value: 1, proj2D: blend });
    nav.update();
    const flat = nav.screenToLatLon(width / 2, height / 2);
    assert.ok(Math.abs(flat.lat - 35) < 1e-6 && Math.abs(flat.lon + 120) < 1e-6, `${projection} keeps the centre`);
    assert.ok(Math.abs(nav.view.span - 0.2) < 1e-12, `${projection} keeps the scale`);
  }
  // The centre maps back to the middle of the screen.
  const screen = nav.latLonToScreen(35, -120);
  assert.ok(screen.visible && Math.abs(screen.x - width / 2) < 1e-6 && Math.abs(screen.y - height / 2) < 1e-6);
});

test('keyboard and animated moves respect focus scope and reduced motion', () => {
  const app = workbench();
  const { nav, listeners } = navigatorHarness(app);
  nav.setView({ lat: 0, lon: 0, span: 1 });
  let prevented = false;
  const key = (value, extra = {}) => listeners.keydown({ key: value, shiftKey: false, preventDefault() { prevented = true; }, stopPropagation() {}, ...extra });
  key('+');
  nav.update();
  assert.ok(prevented, 'handled keys do not scroll the page');
  assert.ok(Math.abs(nav.view.span - 0.5) < 1e-12, '+ zooms in one level at once under reduced motion');
  key('-', { shiftKey: true });
  assert.ok(Math.abs(nav.view.span - 2) < 1e-12, 'shift doubles the zoom step');
  key('ArrowRight');
  assert.ok(nav.view.lon > 0 && Math.abs(nav.view.lat) < 1e-9, 'ArrowRight reveals the east');
  key('ArrowUp');
  assert.ok(nav.view.lat > 0, 'ArrowUp reveals the north');
  prevented = false;
  key('x');
  assert.equal(prevented, false, 'unbound keys fall through');
  nav.flyTo({ lat: 40, lon: 100, span: 0.3 });
  assert.deepEqual([nav.view.lat, nav.view.lon, Number(nav.view.span.toFixed(12))], [40, 100, 0.3]);
  nav.setView({ lat: 0, lon: 0, span: 1e-9 });
  assert.ok(nav.view.span >= nav.minSpan(), 'zoom stops before cells fill the screen many times over');
});

test('a fitted whole-world view refits when the map resizes, until the user moves it', () => {
  const app = workbench();
  let size = { width: 400, height: 400 };
  const { nav, listeners } = navigatorHarness(app);
  app.context.fakeElement.getBoundingClientRect = () => ({ left: 0, top: 0, ...size });
  nav.setView({ ...nav.home(), fit: true });
  const square = nav.view.span;
  size = { width: 1200, height: 400 };
  nav.resize();
  assert.ok(Math.abs(nav.view.span - nav.fitSpan()) < 1e-12 && nav.view.span !== square, 'refitted to the new shape');
  nav.setProjection('equirect', { animate: false });
  assert.ok(Math.abs(nav.view.span - nav.fitSpan('equirect')) < 1e-12, 'a whole-world globe becomes the whole flat map');
  listeners.keydown({ key: '+', shiftKey: false, preventDefault() {}, stopPropagation() {} });
  const zoomed = nav.view.span;
  size = { width: 600, height: 400 };
  nav.resize();
  assert.equal(nav.view.span, zoomed, 'a view the user chose is kept on resize');
});

test('map URLs carry the camera and overlays, and ignore malformed values', () => {
  const app = workbench();
  const parsed = app.run("parseViewHash('#map?layer=cells%2Felevation_m&show=cells,relief,bogus&at=35.00,-120.00,20.00')");
  const params = JSON.parse(JSON.stringify(parsed.mapParams));
  assert.deepEqual(params.show, ['cells', 'relief']);
  assert.equal(params.view.lat, 35);
  assert.equal(params.view.lon, -120);
  assert.ok(Math.abs(params.view.span - (20 * Math.PI) / 180) < 1e-12);
  for (const bad of ['at=95,0,10', 'at=0,0,-1', 'at=a,b,c', 'at=1,2']) {
    assert.equal(app.run(`parseViewHash('#map?${bad}').mapParams`), null, bad);
  }
  app.state.activeLayer = { id: 'cells/biome', kind: 'categorical' };
  app.state.overlays.wireframe = true;
  app.state.relief = true;
  app.run('three.controls = { view: { lat: -12.345, lon: 45.678, span: Math.PI / 6 } }');
  assert.equal(app.run('mapUrlHash()'), '#map?layer=cells%2Fbiome&show=cells%2Crelief&at=-12.35%2C45.68%2C30.00');
});

test('the command palette jumps to typed coordinates and cell numbers', () => {
  const app = workbench();
  app.state.mapReady = true;
  app.state.cellCount = 100;
  const titles = (query) => Array.from(app.run(`commandQueryItems(${JSON.stringify(query)})`)).map((item) => item.title);
  assert.deepEqual(titles('12.5 N, 40 W'), ['12.50° N, 40.00° W']);
  assert.deepEqual(titles('-33.9 151.2'), ['33.90° S, 151.20° E']);
  assert.deepEqual(titles('cell 42'), ['Cell 42']);
  assert.deepEqual(titles('42'), ['Cell 42']);
  assert.deepEqual(titles('cell 100'), [], 'cells beyond the world are not offered');
  assert.deepEqual(titles('95, 10'), [], 'latitudes beyond the poles are rejected');
  assert.deepEqual(titles('elevation'), []);
  app.state.mapReady = false;
  assert.deepEqual(titles('12, 40'), [], 'nothing to jump to without a map');
});

test('hover readouts show units, class names and identifiers honestly', () => {
  const app = workbench();
  app.context.numeric = { id: 'cells/temperature_c', source: 'cells', name: 'temperature_c', kind: 'numeric', stats: { min: -30, max: 30, p2: -25, p98: 25 } };
  app.context.classes = { id: 'cells/biome', source: 'cells', name: 'biome', kind: 'categorical', categories: ['ocean', 'desert'] };
  app.context.ids = { id: 'cells/plate_id', source: 'cells', name: 'plate_id', kind: 'numeric', stats: { min: 0, max: 13, p2: 0, p98: 13 } };
  assert.equal(app.run('hoverValueText(numeric, 12.5)'), '12.5 °C');
  assert.equal(app.run('hoverValueText(numeric, 3.0e38)'), '—');
  assert.equal(app.run('hoverValueText(classes, 1)'), 'desert');
  assert.equal(app.run('hoverValueText(classes, -1)'), 'no data');
  app.run('state.activeLayer = ids; state.scale = numericScale(ids)');
  assert.equal(app.run('hoverValueText(ids, 7)'), 'id 7');
  assert.equal(app.run('hoverValueText(ids, -1)'), 'none (−1)');
  // Coordinates are shown to the precision the mesh supports.
  app.state.cellCount = 4096;
  assert.equal(app.run('coordinateDigits()'), 1);
  app.state.cellCount = 163842;
  assert.equal(app.run('coordinateDigits()'), 2);
});
