// ConfigWorkbench: owns the view lifecycle and its async request ordering.
export function createConfigWorkbench({ state, $, fetchJson, escapeHtml, displayCell, downloadBlob, setView, renderOperationForm }) {
  const HIGHLIGHT_LIMIT = 250000;

  // Lightweight YAML token colouring for the editor overlay. The textarea stays
  // the only source of truth; this function never changes its text.
  function highlightYamlLine(line) {
    let comment = '';
    let body = line;
    let quote = null;
    for (let index = 0; index < line.length; index += 1) {
      const char = line[index];
      if (quote) { if (char === quote) quote = null; continue; }
      if (char === '"' || char === "'") { quote = char; continue; }
      if (char === '#' && (index === 0 || /\s/.test(line[index - 1]))) {
        comment = line.slice(index);
        body = line.slice(0, index);
        break;
      }
    }
    const value = (text) => {
      const trimmed = text.trim();
      if (!trimmed) return escapeHtml(text);
      const lead = text.slice(0, text.indexOf(trimmed));
      const tail = text.slice(text.indexOf(trimmed) + trimmed.length);
      let cls = 'tok-str';
      if (/^[-+]?(\d[\d_]*\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(trimmed)) cls = 'tok-num';
      else if (/^(true|false|null|yes|no|on|off|~)$/i.test(trimmed)) cls = 'tok-bool';
      return `${escapeHtml(lead)}<span class="${cls}">${escapeHtml(trimmed)}</span>${escapeHtml(tail)}`;
    };
    let markup;
    const keyMatch = body.match(/^(\s*(?:-\s+)?)([^\s:#'"][^:#]*?|"[^"]*"|'[^']*')(:)(\s.*|$)/);
    if (keyMatch) {
      markup = `${escapeHtml(keyMatch[1])}<span class="tok-key">${escapeHtml(keyMatch[2])}</span>${keyMatch[3]}${value(keyMatch[4])}`;
    } else {
      const item = body.match(/^(\s*-\s+)(.*)$/);
      markup = item ? `${escapeHtml(item[1])}${value(item[2])}` : value(body);
    }
    return markup + (comment ? `<span class="tok-com">${escapeHtml(comment)}</span>` : '');
  }

  function syncEditorDecorations() {
    const editor = $('#config-yaml');
    const text = String(editor.value ?? '');
    const gutter = $('#config-gutter');
    const highlight = $('#config-highlight');
    const lines = text.split('\n');
    const container = editor.closest?.('.code-editor');
    const plain = text.length > HIGHLIGHT_LIMIT;
    container?.classList?.toggle('plain', plain);
    if (gutter) {
      const numbers = lines.map((_, index) => index + 1).join('\n');
      if (gutter.textContent !== numbers) gutter.textContent = numbers;
    }
    if (highlight && !plain) {
      // A trailing space keeps the overlay as tall as a textarea ending in a newline.
      highlight.innerHTML = lines.map(highlightYamlLine).join('\n') + (text.endsWith('\n') ? ' ' : '');
    }
    syncEditorScroll();
  }

  function syncEditorScroll() {
    const editor = $('#config-yaml');
    const highlight = $('#config-highlight');
    const gutter = $('#config-gutter');
    if (highlight) { highlight.scrollTop = editor.scrollTop; highlight.scrollLeft = editor.scrollLeft; }
    if (gutter) gutter.scrollTop = editor.scrollTop;
  }

  function updateConfigStepper() {
    const steps = document.querySelectorAll?.('[data-config-step]') || [];
    const result = $('#config-result').className || '';
    const hasYaml = Boolean($('#config-yaml').value);
    const saved = !$('#config-generate').disabled;
    const done = {
      open: hasYaml,
      validate: saved || /\bvalid\b/.test(result),
      save: saved,
      generate: false,
    };
    let currentAssigned = false;
    for (const step of steps) {
      const name = step.dataset.configStep;
      const complete = Boolean(done[name]);
      step.classList.toggle('done', complete);
      const current = !complete && !currentAssigned;
      step.classList.toggle('current', current);
      if (current) { currentAssigned = true; step.setAttribute('aria-current', 'step'); } else step.removeAttribute('aria-current');
    }
  }

  function configHasUnsavedChanges() {
    return Boolean($('#config-yaml').value) && $('#config-yaml').value !== state.configBaseline;
  }

  async function refreshConfigFiles({ initial = false } = {}) {
    const request = ++state.configFilesRequest;
    const editorRevision = state.configEditRevision;
    const editorAtStart = $('#config-yaml').value;
    const select = $('#config-file');
    const previous = select.value;
    $('#config-files-refresh').disabled = true;
    try {
      const catalog = await fetchJson('/api/config/files');
      if (request !== state.configFilesRequest) return true;
      if (!catalog || !Array.isArray(catalog.configs)) return false;
      state.configFiles = catalog.configs;
      state.configSaveDirectory = catalog.save_directory;
      select.innerHTML = '';
      select.appendChild(new Option('Choose a configuration…', ''));
      for (const file of catalog.configs) {
        const label = `${file.world_name || file.name} · ${file.path}${file.valid ? '' : ' · needs repair'}`;
        select.appendChild(new Option(label, file.path));
      }
      select.value = catalog.configs.some((file) => file.path === previous) ? previous : catalog.default || '';
      $('#config-open').disabled = !catalog.configs.length;
      $('#config-path-options').innerHTML = catalog.configs.filter((file) => file.valid)
        .map((file) => `<option value="${escapeHtml(file.path)}">${escapeHtml(file.world_name || file.name)}</option>`).join('');
      $('#config-discovery-status').textContent = catalog.error ||
        `${catalog.configs.length} configuration${catalog.configs.length === 1 ? '' : 's'} · Searched ${(catalog.search_directories || []).join(', ')}`;
      updateSavedConfigControls();
      if (initial && state.configEditRevision === editorRevision && $('#config-yaml').value === editorAtStart) {
        if (catalog.error) {
          $('#config-result').className = 'validation-result invalid';
          $('#config-result').textContent = catalog.error;
          return true;
        }
        if (catalog.default) {
          await openConfigFile(catalog.default, { initial: true });
          return true;
        }
      }
      return !initial;
    } catch (error) {
      if (request !== state.configFilesRequest) return true;
      $('#config-discovery-status').textContent = `File discovery failed: ${error.message}. Refresh files to retry.`;
      return !initial;
    } finally {
      if (request === state.configFilesRequest) $('#config-files-refresh').disabled = false;
    }
  }

  async function openConfigFile(path, { initial = false } = {}) {
    if (!path) return;
    if (!initial && configHasUnsavedChanges() && !window.confirm('Discard unsaved YAML edits and open the selected file?')) return;
    const request = ++state.configFileRequest;
    const editRevision = state.configEditRevision;
    const editorValue = $('#config-yaml').value;
    const nameValue = $('#config-name').value;
    state.configTemplateRequest += 1;
    const resultRequest = ++state.configResultRequest;
    $('#config-result').className = 'validation-result';
    $('#config-result').textContent = `Opening ${path}…`;
    try {
      const file = await fetchJson(`/api/config/file?path=${encodeURIComponent(path)}`);
      if (request !== state.configFileRequest) return;
      if (state.configEditRevision !== editRevision || $('#config-yaml').value !== editorValue || $('#config-name').value !== nameValue) {
        if (resultRequest === state.configResultRequest) $('#config-result').textContent = 'Your edits were kept. Open the file again when you are ready.';
        return;
      }
      $('#config-yaml').value = file.yaml;
      $('#config-name').value = file.name;
      syncEditorDecorations();
      state.configSource = { path: file.path, name: file.name, revision: file.revision };
      state.configBaseline = file.yaml;
      state.savedConfig = { ...file };
      state.configEditRevision = 0;
      state.configResultRequest += 1;
      updateSavedConfigControls();
      $('#config-result').className = `validation-result ${file.valid ? 'valid' : 'invalid'}`;
      $('#config-result').innerHTML = file.valid ? `Opened ${escapeHtml(file.path)}. Ready to generate or edit.`
        : `<strong>This configuration needs repair.</strong><ul>${validationErrorMarkup(file.error)}</ul>`;
      updateConfigStepper();
    } catch (error) {
      if (request !== state.configFileRequest || resultRequest !== state.configResultRequest) return;
      $('#config-result').className = 'validation-result invalid';
      $('#config-result').textContent = `${error.message}. Your current YAML was kept.`;
    }
  }

  async function fetchTemplate(profile) {
    const version = state.configSchema?.['x-magic-geo']?.schema_version;
    if (version !== 2) throw new Error('The current configuration schema is unavailable. Reload the workbench before resetting a profile.');
    const payload = await fetchJson(`/api/config/template?${new URLSearchParams({ profile })}`);
    if (payload?.profile !== profile || payload?.config?.config_version !== version
        || typeof payload?.yaml !== 'string' || !payload.yaml.trim()) {
      throw new Error('The profile template does not match configuration schema 2. Reload the workbench; your YAML has been kept.');
    }
    return payload.yaml;
  }

  function normalizeProfiles(payload) {
    const source = Array.isArray(payload) ? payload : payload?.profiles ?? payload ?? [];
    if (Array.isArray(source)) return source.map((entry) => (
      typeof entry === 'string' ? { id: entry, label: entry } : {
        id: String(entry.id ?? entry.name ?? entry.profile),
        label: String(entry.label ?? entry.title ?? entry.name ?? entry.id),
      }
    )).filter((entry) => entry.id && entry.id !== 'undefined');
    if (source && typeof source === 'object') return Object.entries(source).map(([id, entry]) => ({
      id,
      label: typeof entry === 'string' ? entry : entry?.label ?? entry?.title ?? id,
    }));
    return [];
  }

  function resolveSchemaNode(node, root) {
    if (!node?.$ref || !node.$ref.startsWith('#/')) return node || {};
    const resolved = node.$ref.slice(2).split('/').reduce((value, part) => value?.[part.replace(/~1/g, '/').replace(/~0/g, '~')], root);
    if (!resolved) return node;
    const { $ref, ...overrides } = node;
    return { ...resolved, ...overrides };
  }

  function flattenSchema(schema) {
    const fields = [];
    const seen = new Set();
    function visit(rawNode, path, required = new Set(), depth = 0) {
      const node = resolveSchemaNode(rawNode, schema);
      if (!node || depth > 12) return;
      const properties = node.properties || {};
      const nodeRequired = new Set(node.required || []);
      for (const [name, rawChild] of Object.entries(properties)) {
        const child = resolveSchemaNode(rawChild, schema);
        const fieldPath = path ? `${path}.${name}` : name;
        const key = `${fieldPath}:${child?.title || ''}`;
        if (seen.has(key)) continue;
        seen.add(key);
        let type = child.type;
        if (!type && child.anyOf) type = child.anyOf.map((entry) => resolveSchemaNode(entry, schema).type).filter(Boolean).join(' | ');
        if (!type && child.$ref) type = child.$ref.split('/').at(-1);
        fields.push({
          path: fieldPath,
          type: type || (child.properties ? 'object' : 'value'),
          required: nodeRequired.has(name) || required.has(name),
          description: child.description || child.title || '',
          help: fieldPath === 'climate.reference_infrared_optical_depth'
            ? 'Infrared opacity (tau_ref), a dimensionless column parameter. The seasonal energy budget determines temperature.' : '',
          default: child.default,
          enum: child.enum,
          constant: child.const,
          minimum: child.minimum,
          maximum: child.maximum,
          exclusiveMinimum: child.exclusiveMinimum,
          exclusiveMaximum: child.exclusiveMaximum,
          exactIntegers: child['x-magic-geo-integer-display'],
        });
        if (child.properties || child.$ref) visit(child, fieldPath, nodeRequired, depth + 1);
        const item = child.items ? resolveSchemaNode(child.items, schema) : null;
        if (item?.properties) visit(item, `${fieldPath}[]`, new Set(item.required || []), depth + 1);
      }
    }
    visit(schema, '');
    return fields;
  }

  function schemaValueText(field, key, value) {
    const exact = field.exactIntegers?.[key];
    if (typeof value === 'number' && Number.isInteger(value) && !Number.isSafeInteger(value)) {
      if (typeof exact === 'string' && /^-?(0|[1-9]\d*)$/.test(exact) && Number(exact) === value) return exact;
      if (field.type === 'integer' || exact !== undefined) return 'exact integer unavailable';
    }
    return key === 'default' || key === 'const' ? displayCell(value) : String(value);
  }

  function renderSchemaDocs(query = '') {
    const needle = query.trim().toLowerCase();
    const matches = state.schemaFields.filter((field) => !needle || `${field.path} ${field.type} ${field.description} ${field.help || ''}`.toLowerCase().includes(needle));
    $('#schema-docs').innerHTML = matches.map((field) => {
      const defaultText = field.default !== undefined ? `Default: ${schemaValueText(field, 'default', field.default)}` : '';
      const enumText = field.enum ? `Choices: ${field.enum.join(', ')}` : '';
      const constraints = [
        field.constant !== undefined ? `Fixed value: ${schemaValueText(field, 'const', field.constant)}` : '',
        field.minimum !== undefined ? `Minimum: ${schemaValueText(field, 'minimum', field.minimum)} (inclusive)` : '',
        field.maximum !== undefined ? `Maximum: ${schemaValueText(field, 'maximum', field.maximum)} (inclusive)` : '',
        field.exclusiveMinimum !== undefined ? `Greater than: ${schemaValueText(field, 'exclusiveMinimum', field.exclusiveMinimum)}` : '',
        field.exclusiveMaximum !== undefined ? `Less than: ${schemaValueText(field, 'exclusiveMaximum', field.exclusiveMaximum)}` : '',
      ];
      return `<article class="schema-field"><div><code>${escapeHtml(field.path)}</code><span class="schema-meta">${escapeHtml(field.type)}${field.required ? ' · required' : ''}</span></div>`
        + `<p>${escapeHtml(field.description || 'No field description provided.')}</p>`
        + (field.help ? `<p>${escapeHtml(field.help)}</p>` : '')
        + `<small>${escapeHtml([defaultText, enumText, ...constraints].filter(Boolean).join(' · '))}</small></article>`;
    }).join('') || '<p class="muted">No schema fields match this filter.</p>';
  }

  async function resetConfigTemplate() {
    const profile = $('#config-profile').value;
    if (!profile) return;
    if (state.configEditRevision > 0
        && !window.confirm('Replace the current YAML with the profile template?')) return;
    const requestId = ++state.configTemplateRequest;
    const resultRequest = ++state.configResultRequest;
    const editor = $('#config-yaml');
    const editRevision = state.configEditRevision;
    const editorValue = editor.value;
    $('#config-result').className = 'validation-result';
    $('#config-result').textContent = `Loading ${profile} template…`;
    try {
      const template = await fetchTemplate(profile);
      if (requestId !== state.configTemplateRequest || $('#config-profile').value !== profile) return;
      if (state.configEditRevision !== editRevision || editor.value !== editorValue) {
        if (resultRequest === state.configResultRequest) {
          $('#config-result').textContent = `The ${profile} template was not applied because the YAML changed while it loaded. Choose Reset from profile to replace it.`;
        }
        return;
      }
      editor.value = template;
      syncEditorDecorations();
      state.configSource = null;
      state.configBaseline = template;
      state.savedConfig = null;
      state.configFileRequest += 1;
      state.configEditRevision = 0;
      // Applying a template changes the editor even if validation or saving was
      // started while it loaded. Those earlier YAML results are now obsolete.
      state.configResultRequest += 1;
      updateSavedConfigControls();
      $('#config-result').className = 'validation-result';
      $('#config-result').textContent = `Loaded the ${profile} template. Validate after making changes.`;
    } catch (error) {
      if (requestId !== state.configTemplateRequest || resultRequest !== state.configResultRequest || $('#config-profile').value !== profile) return;
      $('#config-result').className = 'validation-result invalid';
      $('#config-result').textContent = error.message || String(error);
    }
  }

  function validationErrorMarkup(payload) {
    const detail = payload?.detail ?? payload?.errors ?? payload ?? [];
    const errors = (!Array.isArray(detail) && Array.isArray(detail?.issues) && detail.issues.length)
      ? detail.issues : detail;
    const list = Array.isArray(errors) ? errors : [errors];
    return list.filter(Boolean).map((error) => {
      if (typeof error === 'string') return `<li>${escapeHtml(error)}</li>`;
      const location = Array.isArray(error.loc) ? error.loc.join('.')
        : Array.isArray(error.location) ? error.location.join('.')
          : error.path ?? error.field ?? '';
      const sourceLocation = error.line !== undefined
        ? `${error.source ?? 'YAML'}:${error.line}${error.column !== undefined ? `:${error.column}` : ''}` : '';
      const prefix = [sourceLocation, location].filter(Boolean).join(' · ');
      return `<li>${prefix ? `<code>${escapeHtml(prefix)}</code>: ` : ''}${escapeHtml(error.msg ?? error.message ?? JSON.stringify(error))}</li>`;
    }).join('');
  }

  async function validateConfig() {
    const result = $('#config-result');
    const button = $('#config-validate');
    const requestId = ++state.configResultRequest;
    const yaml = $('#config-yaml').value;
    button.disabled = true;
    result.className = 'validation-result';
    result.textContent = 'Validating…';
    try {
      const payload = await fetchJson('/api/config/validate', { method: 'POST', body: { yaml } });
      if (requestId !== state.configResultRequest || yaml !== $('#config-yaml').value) return false;
      const valid = payload?.valid ?? payload?.ok ?? payload?.errors?.length === 0;
      result.className = `validation-result ${valid ? 'valid' : 'invalid'}`;
      result.innerHTML = valid
        ? `✓ ${escapeHtml(payload?.message ?? 'Configuration is valid.')}`
        : `<strong>Configuration is not valid.</strong><ul>${validationErrorMarkup(payload)}</ul>`;
      updateConfigStepper();
      return valid;
    } catch (error) {
      if (requestId !== state.configResultRequest || yaml !== $('#config-yaml').value) return false;
      const detail = error.payload?.detail;
      result.className = 'validation-result invalid';
      result.innerHTML = detail
        ? `<strong>Configuration is not valid.</strong><ul>${validationErrorMarkup({ detail })}</ul>`
        : escapeHtml(error.message || String(error));
      return false;
    } finally {
      button.disabled = false;
    }
  }

  function configNameRaw() {
    return $('#config-name').value.trim() || 'world';
  }

  function configFilename() {
    const safe = configNameRaw().replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[-.]+/, '') || 'world';
    return safe.endsWith('.yaml') || safe.endsWith('.yml') ? safe : `${safe}.yaml`;
  }

  function downloadConfig() {
    downloadBlob(new Blob([$('#config-yaml').value], { type: 'text/yaml;charset=utf-8' }), configFilename());
  }

  function updateSavedConfigControls() {
    const saved = state.savedConfig;
    const current = saved && saved.valid !== false && saved.yaml === $('#config-yaml').value && saved.name === configNameRaw();
    $('#config-generate').disabled = !current;
    const source = state.configSource;
    const destination = source && source.name === configFilename() ? source.path
      : `${state.configSaveDirectory || 'runs/configs'}/${configFilename()}`;
    $('#config-source').textContent = `${source ? `Opened ${source.path} · ` : ''}Save to ${destination}`;
    $('#config-source').title = $('#config-source').textContent;
    $('#config-saved-status').textContent = saved
      ? `Saved ${saved.path}.${current ? ' Ready to generate.' : ' Save the current edits to generate them.'}`
      : 'Save a configuration to use it in generation.';
    updateConfigStepper();
  }

  function configEdited(yamlChanged = true) {
    if (yamlChanged) {
      state.configEditRevision += 1;
      syncEditorDecorations();
    }
    state.configResultRequest += 1;
    $('#config-result').className = 'validation-result';
    $('#config-result').textContent = 'Configuration changed. Validate to check the current YAML.';
    updateSavedConfigControls();
  }

  // Give each world its own output and browser-map directory so generating a
  // new world never replaces the one currently open. Only untouched catalog
  // defaults are rewritten; a destination the person typed is always kept.
  function worldOutputDefaults(configPath) {
    const generate = (state.operations || []).find((entry) => entry.name === 'generate');
    const fields = Object.fromEntries((generate?.fields || []).map((field) => [field.name, field.default]));
    const stem = String(configPath || '').split('/').at(-1).replace(/\.ya?ml$/i, '')
      .replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[-._]+/, '');
    const base = state.status?.paths?.output_dir || state.status?.workspace;
    if (!stem || !base) return null;
    return {
      defaults: { output: fields.output, debug_output: fields.debug_output },
      values: { output: `${base}/${stem}/world.json`, debug_output: `${base}/${stem}/debug` },
    };
  }

  function generateFromSavedConfig() {
    if (!state.savedConfig || $('#config-generate').disabled) return;
    $('#operation-select').value = 'generate';
    renderOperationForm();
    const destinations = worldOutputDefaults(state.savedConfig.path);
    if (destinations) {
      for (const input of $('#operation-fields').querySelectorAll('[name]')) {
        const name = input.name;
        if (!(name in destinations.values)) continue;
        if (!input.value || input.value === String(destinations.defaults[name] ?? '')) input.value = destinations.values[name];
      }
    }
    const config = $('#operation-fields').querySelector('[name="config"]');
    if (!config) return;
    config.value = state.savedConfig.path;
    delete $('#operation-result').dataset.jobId;
    setView('operations');
    config.focus();
    $('#operation-result').textContent = `Using ${state.savedConfig.path}. Outputs go to a folder named after the file; review the settings, then choose Generate world.`;
  }

  // Load server-rendered YAML (from the New world dialog) as an unsaved file.
  function loadGeneratedConfig({ yaml, name, profile }) {
    if (configHasUnsavedChanges() && !window.confirm('Replace the unsaved YAML in the editor with the new world?')) return false;
    state.configFileRequest += 1;
    state.configTemplateRequest += 1;
    state.configResultRequest += 1;
    $('#config-yaml').value = yaml;
    $('#config-name').value = name;
    if (profile && [...($('#config-profile').options || [])].some((option) => option.value === profile)) $('#config-profile').value = profile;
    state.configSource = null;
    state.savedConfig = null;
    state.configBaseline = '';
    state.configEditRevision = 1;
    syncEditorDecorations();
    updateSavedConfigControls();
    $('#config-result').className = 'validation-result valid';
    $('#config-result').textContent = `Created from the ${profile} profile. Review it, then save and generate.`;
    updateConfigStepper();
    setView('config');
    return true;
  }

  // Adopt a file the New world dialog already saved through /api/config/save.
  function adoptSavedConfig(payload, yaml, profile) {
    state.configFileRequest += 1;
    state.configTemplateRequest += 1;
    state.configResultRequest += 1;
    const name = payload?.name || String(payload?.path || 'world.yaml').split('/').at(-1);
    $('#config-yaml').value = yaml;
    $('#config-name').value = name;
    if (profile && [...($('#config-profile').options || [])].some((option) => option.value === profile)) $('#config-profile').value = profile;
    state.configSource = { path: payload.path, name, revision: payload.revision };
    state.savedConfig = { yaml, name, path: payload.path, valid: true };
    state.configBaseline = yaml;
    state.configEditRevision = 0;
    syncEditorDecorations();
    updateSavedConfigControls();
    $('#config-result').className = 'validation-result valid';
    $('#config-result').textContent = `Saved ${payload.path}.`;
    updateConfigStepper();
  }

  async function saveConfig() {
    if (state.configSaving) return false;
    const result = $('#config-result');
    const nameInput = $('#config-name');
    if (!nameInput.checkValidity()) {
      nameInput.reportValidity();
      return;
    }
    const button = $('#config-save');
    const requestId = ++state.configResultRequest;
    // Retries must save exactly the name and text whose overwrite was reviewed.
    const snapshot = { yaml: $('#config-yaml').value, name: configNameRaw() };
    const source = state.configSource?.name === configFilename() ? state.configSource : null;
    const fileRequest = state.configFileRequest;
    state.configSaving = true;
    $('#config-save-generate').disabled = true;
    button.disabled = true;
    result.className = 'validation-result';
    result.textContent = 'Saving…';
    const submit = async (force) => fetchJson('/api/config/save', {
      method: 'POST',
      body: {
        ...snapshot,
        ...(source ? { path: source.path, revision: source.revision } : {}),
        force,
      },
    });
    const showSaved = (payload, replaced = false) => {
      if (fileRequest !== state.configFileRequest) return;
      if (payload?.path) {
        state.savedConfig = { ...snapshot, path: payload.path, valid: true };
        state.configSource = { path: payload.path, name: payload.name || (snapshot.name.endsWith('.yaml') || snapshot.name.endsWith('.yml') ? snapshot.name : `${snapshot.name}.yaml`), revision: payload.revision };
        state.configBaseline = snapshot.yaml;
      }
      updateSavedConfigControls();
      if (requestId !== state.configResultRequest) return;
      result.className = 'validation-result valid';
      result.textContent = `${replaced ? 'Replaced' : 'Saved'} ${payload?.path ?? snapshot.name}.`;
    };
    try {
      const payload = await submit(false);
      showSaved(payload);
      void refreshConfigFiles();
      return true;
    } catch (error) {
      if (requestId !== state.configResultRequest) return;
      if (!source && error.status === 409 && window.confirm(`The configuration "${snapshot.name}" already exists. Replace it with the submitted YAML?`)) {
        try {
          const payload = await submit(true);
          showSaved(payload, true);
          void refreshConfigFiles();
          return true;
        } catch (overwriteError) {
          error = overwriteError;
        }
      }
      if (requestId !== state.configResultRequest) return;
      result.className = 'validation-result invalid';
      result.textContent = error.message || String(error);
    } finally {
      button.disabled = false;
      state.configSaving = false;
      $('#config-save-generate').disabled = false;
    }
  }

  async function loadConfigWorkbench() {
    const requestId = ++state.configWorkbenchRequest;
    state.configTemplateRequest += 1;
    const editRevisionAtStart = state.configEditRevision;
    const resultRequestAtStart = state.configResultRequest;
    const editorValueAtStart = $('#config-yaml').value;
    const select = $('#config-profile');
    const previousProfile = select.value;
    select.disabled = true;
    $('#config-reset').disabled = true;
    state.configSchema = null;
    state.schemaFields = [];
    select.innerHTML = '';
    $('#config-schema-status').textContent = 'Loading the current configuration schema…';
    $('#schema-docs').innerHTML = '';
    try {
      const [schemaPayload, profilePayload] = await Promise.all([
        fetchJson('/api/config/schema'),
        fetchJson('/api/config/profiles'),
      ]);
      if (requestId !== state.configWorkbenchRequest) return;
      const schema = schemaPayload?.schema ?? schemaPayload;
      const metadata = schema?.['x-magic-geo'];
      const profiles = normalizeProfiles(profilePayload);
      const declaredProfiles = metadata?.profiles;
      if (metadata?.schema_version !== 2 || schema?.properties?.config_version?.const !== 2
          || !Array.isArray(declaredProfiles) || !declaredProfiles.length
          || declaredProfiles.some((profile) => profile?.values?.config_version !== 2)
          || !profiles.length || new Set(profiles.map((profile) => profile.id)).size !== profiles.length
          || profiles.length !== declaredProfiles.length
          || profiles.some((profile) => !declaredProfiles.some((entry) => entry.name === profile.id))
          || !profiles.some((profile) => profile.id === profilePayload?.default)) {
        throw new Error('Configuration schema and profiles must declare the current version 2. Reload the workbench; your YAML has been kept.');
      }
      state.configSchema = schema;
      state.schemaFields = flattenSchema(schema);
      renderSchemaDocs($('#schema-search').value);
      for (const profile of profiles) {
        const option = document.createElement('option');
        option.value = profile.id;
        option.textContent = profile.label;
        option.title = declaredProfiles.find((entry) => entry.name === profile.id)?.description || '';
        select.appendChild(option);
      }
      select.value = profiles.some((profile) => profile.id === previousProfile) ? previousProfile : profilePayload.default;
      select.disabled = false;
      $('#config-reset').disabled = false;
      $('#config-schema-status').textContent = 'Schema 2 · Seasonal energy model · config_version: 2 is required.';
      if (!editorValueAtStart && state.configEditRevision === editRevisionAtStart
          && $('#config-yaml').value === editorValueAtStart && state.configResultRequest === resultRequestAtStart) {
        if (!await refreshConfigFiles({ initial: true })) await resetConfigTemplate();
      } else if (state.configResultRequest === resultRequestAtStart) {
        $('#config-result').textContent = 'Profiles loaded. Your YAML was kept; use Reset from profile to replace it.';
      }
    } catch (error) {
      if (requestId !== state.configWorkbenchRequest) return;
      $('#config-schema-status').textContent = 'Current schema and profiles are unavailable.';
      $('#schema-docs').innerHTML = `<div class="notice warning">${escapeHtml(error.message || String(error))}</div>`;
      if (state.configResultRequest === resultRequestAtStart) {
        $('#config-result').className = 'validation-result invalid';
        $('#config-result').textContent = 'Profile loading failed. Your YAML was kept; validation, saving and downloading remain available.';
      }
    }
  }


  return { syncEditorDecorations, syncEditorScroll, updateConfigStepper, loadGeneratedConfig, adoptSavedConfig, worldOutputDefaults, highlightYamlLine, configHasUnsavedChanges, refreshConfigFiles, openConfigFile, fetchTemplate, normalizeProfiles, resolveSchemaNode, flattenSchema, schemaValueText, renderSchemaDocs, resetConfigTemplate, validationErrorMarkup, validateConfig, configNameRaw, configFilename, downloadConfig, updateSavedConfigControls, configEdited, generateFromSavedConfig, saveConfig, loadConfigWorkbench };
}
