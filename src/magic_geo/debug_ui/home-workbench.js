// HomeWorkbench: the workbench's landing view. It summarizes the three-step
// workflow (configure → generate → explore) from live server state, lists the
// worlds in the workspace and offers example configurations as starting points.
//
// It only reads shared state; actions are delegated to injected services so the
// config, operation and cache controllers keep ownership of their requests.
export function createHomeWorkbench({ state, $, escapeHtml, icon, relativeTime, formatCount, hueFor, selectWorld, openExample, generateExample }) {
  const MAX_WORLDS = 12;

  function setMarkup(node, markup) {
    // Polling re-renders often; replacing identical markup would drop focus.
    if (node && node.innerHTML !== markup) node.innerHTML = markup;
  }

  function setText(selector, text) {
    const node = $(selector);
    if (node && node.textContent !== text) node.textContent = text;
  }

  function jobIsActive(job) {
    return ['pending', 'queued', 'running', 'cancelling', 'canceling'].includes(String(job?.status ?? '').toLowerCase());
  }

  function selectedWorld() {
    const dir = state.status?.cache_dir;
    return (state.worlds || []).find((world) => world.cache_dir === dir) || null;
  }

  function stepState(id, { done = false, active = false } = {}) {
    const node = $(id);
    node?.classList?.toggle('done', done);
    node?.classList?.toggle('active', active);
  }

  function renderSteps() {
    const configs = Array.isArray(state.configFiles) ? state.configFiles : [];
    const valid = configs.filter((file) => file.valid).length;
    const saved = state.savedConfig?.path;
    setText('[data-home="config-status"]', saved
      ? `Ready: ${saved}`
      : configs.length ? `${valid} valid configuration${valid === 1 ? '' : 's'} found` : 'No configuration yet — start from a profile.');
    stepState('#home-step-config', { done: Boolean(saved) });

    const jobs = Array.isArray(state.jobs) ? state.jobs : [];
    const active = jobs.find((job) => jobIsActive(job) && job.status !== 'queued') || jobs.find(jobIsActive);
    const lastGenerate = jobs.find((job) => job.operation === 'generate');
    let jobText = 'No jobs in this session yet.';
    if (active) {
      jobText = `${active.operation}: ${active.progress?.label || active.status}…`;
    } else if (lastGenerate) {
      const when = relativeTime(lastGenerate.finished_at || lastGenerate.created_at);
      jobText = `Last generation ${lastGenerate.status}${when ? ` · ${when}` : ''}`;
    } else if (jobs.length) {
      jobText = `${jobs.length} job${jobs.length === 1 ? '' : 's'} this session`;
    }
    setText('[data-home="job-status"]', jobText);
    stepState('#home-step-generate', { active: Boolean(active), done: !active && lastGenerate?.status === 'succeeded' });

    const world = selectedWorld();
    const manifest = state.manifest;
    let mapText = 'No world prepared yet.';
    if (state.cacheAvailable) {
      const name = manifest?.world?.name ?? world?.name ?? state.status?.cache_dir ?? 'world';
      const cells = manifest?.world?.cell_count ?? world?.cell_count;
      const layers = manifest?.layers?.length;
      mapText = [name, cells ? `${formatCount(cells)} cells` : null, layers ? `${formatCount(layers)} layers` : null].filter(Boolean).join(' · ');
    } else if (state.status?.cache_error) {
      mapText = 'The selected world could not be opened.';
    }
    setText('[data-home="map-status"]', mapText);
    stepState('#home-step-explore', { done: Boolean(state.cacheAvailable) });
    const openMap = $('#home-open-map');
    if (openMap) openMap.disabled = !state.cacheAvailable;
  }

  function renderWorlds() {
    const container = $('#home-worlds');
    if (!container) return;
    if (!Array.isArray(state.worlds)) {
      setMarkup(container, '<p class="muted">Loading worlds…</p>');
      return;
    }
    const query = String($('#home-world-filter')?.value || '').trim().toLowerCase();
    const current = state.status?.cache_dir;
    const worlds = [...state.worlds]
      .sort((a, b) => (b.cache_dir === current) - (a.cache_dir === current) || Number(b.modified_ns || 0) - Number(a.modified_ns || 0))
      .filter((world) => !query || `${world.name ?? ''} ${world.cache_dir ?? ''}`.toLowerCase().includes(query));
    if (!state.worlds.length) {
      setMarkup(container, `<div class="empty-inline">${icon('globe')}<p>No prepared worlds in this workspace yet. Create one with <strong>New world</strong> — it appears here when its browser map is ready.</p></div>`);
      return;
    }
    if (!worlds.length) {
      setMarkup(container, '<p class="muted">No worlds match this filter.</p>');
      return;
    }
    const rows = worlds.slice(0, MAX_WORLDS).map((world) => {
      const dir = String(world.cache_dir ?? world.id ?? '');
      const selected = dir === current;
      const updated = Number.isFinite(Number(world.modified_ns)) ? relativeTime(Number(world.modified_ns) / 1e6) : '';
      const meta = [
        Number.isFinite(Number(world.cell_count)) ? `${formatCount(world.cell_count)} cells` : null,
        world.generation_scope && world.generation_scope !== 'full' ? String(world.generation_scope).replaceAll('_', ' ') : null,
        updated ? `updated ${updated}` : null,
      ].filter(Boolean).join(' · ');
      const action = selected
        ? `<span class="tag">Showing</span><button type="button" class="small" data-home-open-map>${icon('globe')}Open map</button>`
        : `<button type="button" class="small" data-home-world="${escapeHtml(dir)}">Open</button>`;
      return `<div class="world-row${selected ? ' selected' : ''}">`
        + `<span class="world-avatar" style="--world-hue: hsl(${hueFor(world.name || dir)} 60% 45%)" aria-hidden="true"></span>`
        + `<div><strong>${escapeHtml(world.name ?? dir)}</strong><small>${escapeHtml(meta)}</small><small title="${escapeHtml(dir)}">${escapeHtml(dir)}</small></div>`
        + `<div class="button-row">${action}</div></div>`;
    });
    const more = worlds.length > MAX_WORLDS
      ? `<p class="world-list-more">${worlds.length - MAX_WORLDS} more — type to filter, or use the world picker in the header.</p>` : '';
    setMarkup(container, rows.join('') + more);
  }

  function renderExamples() {
    const container = $('#home-examples');
    if (!container) return;
    const configs = Array.isArray(state.configFiles) ? state.configFiles : null;
    if (!configs) {
      setMarkup(container, '<p class="muted">Loading examples…</p>');
      return;
    }
    const examples = configs
      .filter((file) => file.valid)
      .sort((a, b) => Number(/\/seeds\//.test(b.path)) - Number(/\/seeds\//.test(a.path)))
      .slice(0, 8);
    if (!examples.length) {
      setMarkup(container, '<p class="muted">No example configurations were found. Use <strong>New world</strong> to start from a profile.</p>');
      return;
    }
    setMarkup(container, examples.map((file) => {
      const title = String(file.world_name || file.name || file.path).replaceAll('_', ' ');
      return `<button type="button" class="example-card" data-home-example="${escapeHtml(file.path)}" title="Open ${escapeHtml(file.path)} in the editor">`
        + `<strong>${escapeHtml(title)}</strong><small>${escapeHtml(String(file.path).split('/').at(-1))}</small></button>`;
    }).join(''));
  }

  function renderSystem() {
    const container = $('#home-system');
    if (!container) return;
    const status = state.status || {};
    const backend = state.backend;
    const rows = [];
    rows.push(['Server', status.version ? `magic-geo ${status.version}` : (state.statusFailed ? 'Unreachable' : 'Connecting…')]);
    if (backend) {
      const threads = backend.openmp_enabled ? ` · ${backend.openmp_max_threads} threads` : '';
      rows.push(['Engine', `${String(backend.active_backend || backend.selected_backend || 'cpu').toUpperCase()} · ${backend.native_core || 'native'}${threads}`]);
      rows.push(['GPU', backend.cuda_available ? `CUDA · ${backend.cuda_device_name || 'available'}`
        : backend.opencl_available ? `OpenCL · ${backend.opencl_device_name || 'available'}` : 'None detected']);
    }
    if (status.workspace) rows.push(['Workspace', `<code>${escapeHtml(status.workspace)}</code>`]);
    rows.push(['API', '<a href="/api/docs" target="_blank" rel="noopener">OpenAPI docs ↗</a>']);
    setMarkup(container, rows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${value.startsWith('<') ? value : escapeHtml(value)}</dd>`).join(''));
  }

  function renderHome() {
    if (state.activeView !== 'home') return;
    renderSteps();
    renderWorlds();
    renderExamples();
    renderSystem();
  }

  function wireHome() {
    const view = $('#view-home');
    view?.addEventListener?.('click', (event) => {
      const world = event.target.closest?.('[data-home-world]');
      if (world) { void selectWorld(world.dataset.homeWorld, { openMap: true }); return; }
      if (event.target.closest?.('[data-home-open-map]')) { void selectWorld(state.status?.cache_dir, { openMap: true }); return; }
      const example = event.target.closest?.('[data-home-example]');
      if (example) { void openExample(example.dataset.homeExample); return; }
      const generate = event.target.closest?.('[data-home-generate]');
      if (generate) void generateExample(generate.dataset.homeGenerate);
    });
    $('#home-world-filter')?.addEventListener?.('input', renderWorlds);
  }

  return { renderHome, wireHome };
}
