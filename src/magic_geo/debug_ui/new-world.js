// NewWorldDialog: a short guided path for occasional users — choose a profile,
// name the world, pick a seed and resolution — while experts keep the full YAML
// editor. The dialog renders YAML on the server from the profile plus explicit
// dotted overrides (POST /api/config/render), so the schema stays the single
// source of truth and no client-side YAML is invented.
export function createNewWorldDialog({
  state, $, fetchJson, escapeHtml, icon, toast,
  loadGeneratedConfig, adoptSavedConfig, refreshConfigFiles, startGeneration,
}) {
  const PROFILE_NOTES = {
    earthlike: 'Earth reference inputs · 4,096 cells',
    smoke: 'Tiny and fast · good for a first try',
    default: 'Neutral physical inputs',
  };
  const RESOLUTIONS = [
    { value: '', label: 'Profile default', hint: 'Keep the profile mesh' },
    { value: '512', label: 'Preview', hint: '512 cells · fastest' },
    { value: '2048', label: 'Draft', hint: '2,048 cells' },
    { value: '4096', label: 'Standard', hint: '4,096 cells' },
    { value: '16384', label: 'Detailed', hint: '16,384 cells · slow' },
  ];
  const ADVANCED_FIELDS = [
    'planet.radius_km', 'planet.axial_tilt_deg', 'planet.ocean_fraction_target', 'planet.day_length_hours',
    'tectonics.plate_count', 'climate.precipitation_scale', 'erosion.iterations', 'planet.stellar_luminosity',
  ];
  const NAME_IDEAS = ['aurora', 'basalt', 'cinder', 'delta', 'ember', 'fjord', 'gale', 'halcyon', 'isle', 'juniper', 'kelp', 'lumen', 'mistral', 'nimbus', 'onyx', 'pangea', 'quartz', 'rime', 'sirocco', 'tundra', 'umber', 'vale', 'willow', 'zephyr'];
  let busy = false;
  let wired = false;

  function dialog() { return $('#new-world-dialog'); }

  function randomSeed() {
    const values = new Uint32Array(1);
    globalThis.crypto?.getRandomValues?.(values);
    return (values[0] || Math.floor(Math.random() * 2 ** 31)) % 2147483647;
  }

  function slugify(value) {
    return String(value || '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9._-]+/g, '-').replace(/^[-._]+|[-._]+$/g, '').slice(0, 60);
  }

  function takenNames() {
    return new Set((state.configFiles || []).map((file) => String(file.name || '').replace(/\.ya?ml$/, '')));
  }

  function uniqueSlug(base) {
    const taken = takenNames();
    let slug = slugify(base) || 'world';
    if (!taken.has(slug)) return slug;
    for (let index = 2; index < 1000; index += 1) {
      if (!taken.has(`${slug}-${index}`)) return `${slug}-${index}`;
    }
    return `${slug}-${Date.now()}`;
  }

  function suggestedName() {
    const taken = takenNames();
    const pool = NAME_IDEAS.filter((name) => !taken.has(name));
    const list = pool.length ? pool : NAME_IDEAS;
    return list[Math.floor(Math.random() * list.length)];
  }

  function profiles() {
    const declared = state.configSchema?.['x-magic-geo']?.profiles;
    if (Array.isArray(declared) && declared.length) return declared.map((entry) => ({ name: entry.name, description: entry.description || '' }));
    return state.configProfiles || [];
  }

  async function ensureProfiles() {
    if (profiles().length) return;
    const payload = await fetchJson('/api/config/profiles');
    state.configProfiles = Array.isArray(payload?.profiles) ? payload.profiles : [];
    state.configDefaultProfile = payload?.default;
  }

  function schemaField(path) {
    return (state.schemaFields || []).find((field) => field.path === path) || null;
  }

  function renderProfiles(selected) {
    const list = profiles();
    const preferred = selected || state.configDefaultProfile || (list.some((item) => item.name === 'earthlike') ? 'earthlike' : list[0]?.name);
    $('#new-world-profiles').innerHTML = list.map((profile) => {
      const note = PROFILE_NOTES[profile.name];
      return `<label class="profile-card"><input type="radio" name="profile" value="${escapeHtml(profile.name)}"${profile.name === preferred ? ' checked' : ''}>`
        + `<strong>${escapeHtml(profile.name)}</strong>${note ? `<span>${escapeHtml(note)}</span>` : ''}`
        + `<span>${escapeHtml(profile.description)}</span></label>`;
    }).join('') || '<p class="muted">No profiles are available from the server.</p>';
  }

  function renderResolutions() {
    const field = schemaField('mesh.cell_count');
    const max = Number.isFinite(field?.maximum) ? field.maximum : Infinity;
    const min = Number.isFinite(field?.minimum) ? field.minimum : 0;
    $('#new-world-cells').innerHTML = RESOLUTIONS
      .filter((option) => !option.value || (Number(option.value) >= min && Number(option.value) <= max))
      .map((option, index) => `<label><input type="radio" name="cells" value="${option.value}"${index === 0 ? ' checked' : ''}>`
        + `${escapeHtml(option.label)}<small>${escapeHtml(option.hint)}</small></label>`).join('');
  }

  function renderAdvanced() {
    const container = $('#new-world-advanced');
    container.innerHTML = ADVANCED_FIELDS.map((path) => {
      const field = schemaField(path);
      if (!field) return '';
      const id = `new-world-${path.replace(/[^a-z0-9]+/gi, '-')}`;
      const integer = field.type === 'integer';
      const bounds = [
        Number.isFinite(field.minimum) ? `min="${field.minimum}"` : '',
        Number.isFinite(field.maximum) ? `max="${field.maximum}"` : '',
      ].join(' ');
      const range = [
        Number.isFinite(field.minimum) ? `≥ ${field.minimum}` : Number.isFinite(field.exclusiveMinimum) ? `> ${field.exclusiveMinimum}` : '',
        Number.isFinite(field.maximum) ? `≤ ${field.maximum}` : Number.isFinite(field.exclusiveMaximum) ? `< ${field.exclusiveMaximum}` : '',
      ].filter(Boolean).join(', ');
      const label = path.split('.').at(-1).replaceAll('_', ' ');
      return `<div class="form-field"><label for="${id}">${escapeHtml(label.charAt(0).toUpperCase() + label.slice(1))}</label>`
        + `<input id="${id}" type="number" data-override="${escapeHtml(path)}" data-integer="${integer}" step="${integer ? 1 : 'any'}" ${bounds} placeholder="Profile default" inputmode="decimal">`
        + `<span class="field-help">${escapeHtml(field.description || '')}${range ? ` (${escapeHtml(range)})` : ''}</span></div>`;
    }).join('');
    container.closest('details')?.classList.toggle('hidden', !container.innerHTML.trim());
  }

  function showResult(message, tone = '') {
    const result = $('#new-world-result');
    result.className = `validation-result ${tone}`.trim();
    result.innerHTML = message;
    result.classList.toggle('hidden', !message);
  }

  function setBusy(value) {
    busy = value;
    $('#new-world-create').disabled = value;
    $('#new-world-edit').disabled = value;
  }

  function collect() {
    const form = $('#new-world-form');
    const profile = form.querySelector('input[name="profile"]:checked')?.value;
    if (!profile) throw new Error('Choose a profile.');
    const nameInput = $('#new-world-name');
    const name = nameInput.value.trim();
    if (!name || !nameInput.checkValidity()) {
      nameInput.focus();
      throw new Error('Enter a world name that starts with a letter or digit (letters, digits, spaces, dot, dash and underscore).');
    }
    const seedText = $('#new-world-seed').value.trim();
    const seed = Number(seedText);
    if (!/^\d+$/.test(seedText) || !Number.isSafeInteger(seed)) {
      $('#new-world-seed').focus();
      throw new Error('Enter a whole-number seed up to 9007199254740991. Larger 64-bit seeds can be typed directly in the YAML editor.');
    }
    const overrides = { 'run.name': name, 'run.seed': seed };
    const cells = form.querySelector('input[name="cells"]:checked')?.value;
    if (cells) overrides['mesh.cell_count'] = Number(cells);
    for (const input of $('#new-world-advanced').querySelectorAll('input[data-override]')) {
      const raw = input.value.trim();
      if (!raw) continue;
      const value = Number(raw);
      if (!Number.isFinite(value) || (input.dataset.integer === 'true' && !Number.isSafeInteger(value))) {
        input.focus();
        throw new Error(`${input.dataset.override}: enter a ${input.dataset.integer === 'true' ? 'whole' : 'finite'} number.`);
      }
      overrides[input.dataset.override] = value;
    }
    return { profile, name, slug: uniqueSlug(name), overrides };
  }

  function errorMessage(error) {
    const detail = error?.payload?.detail;
    if (detail && typeof detail === 'object') {
      const issues = Array.isArray(detail.issues) ? detail.issues : [];
      const text = issues.map((issue) => `${Array.isArray(issue.loc) ? issue.loc.join('.') : issue.path ?? ''} ${issue.msg ?? issue.message ?? ''}`.trim()).filter(Boolean);
      return escapeHtml(text.length ? text.join('; ') : detail.message || JSON.stringify(detail));
    }
    return escapeHtml(error?.message || String(error));
  }

  async function render(values) {
    const payload = await fetchJson('/api/config/render', { method: 'POST', body: { profile: values.profile, overrides: values.overrides } });
    if (typeof payload?.yaml !== 'string' || !payload.yaml.trim()) throw new Error('The server returned an empty configuration.');
    return payload.yaml;
  }

  async function openInEditor() {
    if (busy) return;
    let values;
    try { values = collect(); } catch (error) { showResult(escapeHtml(error.message), 'invalid'); return; }
    setBusy(true);
    showResult('Preparing the configuration…');
    try {
      const yaml = await render(values);
      if (loadGeneratedConfig({ yaml, name: `${values.slug}.yaml`, profile: values.profile })) close();
      else showResult('Your current editor changes were kept.');
    } catch (error) {
      showResult(`<strong>The configuration could not be created.</strong> ${errorMessage(error)}`, 'invalid');
    } finally {
      setBusy(false);
    }
  }

  async function createAndGenerate(event) {
    event?.preventDefault?.();
    if (busy) return;
    let values;
    try { values = collect(); } catch (error) { showResult(escapeHtml(error.message), 'invalid'); return; }
    setBusy(true);
    showResult('Creating the configuration…');
    try {
      const yaml = await render(values);
      showResult('Saving…');
      const saved = await fetchJson('/api/config/save', { method: 'POST', body: { yaml, name: `${values.slug}.yaml`, force: false } });
      adoptSavedConfig(saved, yaml, values.profile);
      void refreshConfigFiles();
      close();
      await startGeneration({ config: saved.path, slug: values.slug, name: values.name });
    } catch (error) {
      const conflict = error?.status === 409;
      showResult(conflict
        ? `A configuration named <code>${escapeHtml(values.slug)}.yaml</code> already exists. Choose another world name.`
        : `<strong>The world could not be created.</strong> ${errorMessage(error)}`, 'invalid');
    } finally {
      setBusy(false);
    }
  }

  function close() {
    const node = dialog();
    if (node?.open) node.close();
  }

  function wire() {
    if (wired) return;
    wired = true;
    const node = dialog();
    $('#new-world-form').addEventListener('submit', createAndGenerate);
    $('#new-world-edit').addEventListener('click', openInEditor);
    $('#new-world-dice').addEventListener('click', () => { $('#new-world-seed').value = String(randomSeed()); });
    node.querySelectorAll('[data-close-dialog]').forEach((button) => button.addEventListener('click', close));
    node.addEventListener('click', (event) => { if (event.target === node) close(); });
  }

  async function open({ profile = null } = {}) {
    wire();
    const node = dialog();
    if (!node || node.open) return;
    showResult('');
    try {
      await ensureProfiles();
    } catch (error) {
      toast({ title: 'Profiles are unavailable', message: error.message || String(error), tone: 'error' });
      return;
    }
    renderProfiles(profile);
    renderResolutions();
    renderAdvanced();
    $('#new-world-name').value = suggestedName();
    $('#new-world-seed').value = String(randomSeed());
    node.showModal();
    $('#new-world-name').focus();
    $('#new-world-name').select();
  }

  return { open, close, slugify, uniqueSlug };
}
