// OperationsWorkbench: owns the view lifecycle and its async request ordering.
export function createOperationsWorkbench({ state, $, fetchJson, optionalJson, escapeHtml, formatValue, displayCell, jsonText, setView, beginCacheTransition, loadServerStatus, onJobsChanged = () => {} }) {
  const QUICK_OPERATIONS = ['generate', 'validate-geo', 'render', 'export-debug'];

  function operationTitle(name) {
    return state.operations.find((entry) => entry.name === name)?.title ?? name ?? 'job';
  }

  function prepareOperation(name, values) {
    // Save the outgoing draft before installing a reviewed job's settings.
    if (state.renderedOperation) {
      state.operationDrafts[state.renderedOperation] = Object.fromEntries(
        [...$('#operation-fields').querySelectorAll('[name]')].map((input) => [input.name, input.value])
      );
    }
    state.renderedOperation = null;
    delete $('#operation-result').dataset.jobId;
    state.operationDrafts[name] = Object.fromEntries(Object.entries(values).map(([key, value]) => [key,
      Array.isArray(value) ? value.join('\n') : String(value)]));
    $('#operation-select').value = name;
    renderOperationForm();
    setView('operations');
    $('#operation-select').focus();
    $('#operation-result').textContent = 'Settings prepared. Review the inputs and destinations before starting.';
  }

  function renderJobActions(job) {
    const actions = $('#job-actions');
    const signature = JSON.stringify([job.id, jobStatus(job), job.cache_dir, job.world_path, job.artifacts]);
    if (state.jobActionsSignature === signature) return;
    state.jobActionsSignature = signature;
    actions.innerHTML = '';
    if (jobIsActive(job)) return;
    const add = (label, action) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      if (label === 'Open map' || label === 'Prepare browser map') button.className = 'primary';
      button.addEventListener('click', action);
      actions.appendChild(button);
    };
    if (job.cache_dir) add('Open map', async () => {
      try {
        await fetchJson('/api/worlds/select', { method: 'POST', body: { cache_dir: job.cache_dir } });
        beginCacheTransition(job.cache_dir);
        await loadServerStatus();
        setView('map');
      } catch (error) { $('#operation-result').textContent = `Unable to open this map: ${error.message}`; }
    });
    const world = job.operation === 'generate' && job.artifacts?.find((item) => item.name === 'output' && item.available);
    if (world) {
      const worldPath = job.world_path || world.path;
      if (!job.cache_dir) add('Prepare browser map', () => prepareOperation('export-debug', { world: worldPath }));
      add('Validate world', () => prepareOperation('validate-geo', { world: worldPath }));
      add('Render map', () => prepareOperation('render', { world: worldPath }));
    }
    add('Reuse settings', () => prepareOperation(job.operation, job.arguments || {}));
  }

  function normalizeOperations(payload) {
    const source = Array.isArray(payload) ? payload : payload?.operations ?? payload ?? [];
    if (Array.isArray(source)) return source.map((entry) => (
      typeof entry === 'string' ? { name: entry, title: entry } : {
        ...entry,
        name: String(entry.name ?? entry.id ?? entry.operation),
        title: String(entry.title ?? entry.label ?? entry.name ?? entry.id ?? entry.operation),
      }
    )).filter((entry) => entry.name && entry.name !== 'undefined');
    if (source && typeof source === 'object') return Object.entries(source).map(([name, entry]) => ({
      ...(typeof entry === 'object' ? entry : {}), name,
      title: typeof entry === 'string' ? entry : entry?.title ?? entry?.label ?? name,
    }));
    return [];
  }

  function operationArguments(operation) {
    const schema = operation?.arguments ?? operation?.parameters ?? operation?.options ?? operation?.fields ?? operation?.schema ?? {};
    if (Array.isArray(schema)) return schema.map((argument) => ({
      ...argument,
      name: String(argument.name ?? argument.id ?? argument.key),
      type: argument.type ?? argument.kind ?? 'string',
      required: Boolean(argument.required),
    }));
    const properties = schema.properties ?? schema;
    const required = new Set(schema.required || operation?.required || []);
    if (!properties || typeof properties !== 'object') return [];
    return Object.entries(properties).map(([name, descriptor]) => ({
      ...(descriptor && typeof descriptor === 'object' ? descriptor : { type: descriptor }),
      name,
      type: descriptor?.type ?? descriptor?.kind ?? 'string',
      required: required.has(name) || Boolean(descriptor?.required),
    }));
  }

  function renderOperationForm() {
    const operation = state.operations.find((entry) => entry.name === $('#operation-select').value);
    const unavailable = operation && operation.available === false;
    $('#operation-description').textContent = `${operation?.description ?? operation?.help ?? 'No description supplied.'}${unavailable ? ` This operation is unavailable${operation.dependency ? ` until ${operation.dependency} is installed` : ''}.` : ''}`;
    const submit = $('#operation-form').querySelector('button[type="submit"]');
    submit.disabled = state.operationSubmitting || !operation || unavailable;
    submit.textContent = operation?.name === 'generate' ? 'Generate world' : 'Start job';
    const fields = $('#operation-fields');
    if (state.renderedOperation) {
      state.operationDrafts[state.renderedOperation] = Object.fromEntries(
        [...fields.querySelectorAll('[name]')].map((input) => [input.name, input.value])
      );
    }
    state.renderedOperation = operation?.name;
    const draft = state.operationDrafts[operation?.name] || {};
    fields.innerHTML = '';
    const advanced = document.createElement('details');
    advanced.className = 'operation-advanced';
    const summary = document.createElement('summary');
    summary.textContent = 'Output options & advanced settings';
    advanced.appendChild(summary);
    const advancedFields = document.createElement('div');
    advancedFields.className = 'operation-field-grid';
    advanced.appendChild(advancedFields);
    for (const argument of operationArguments(operation)) {
      const wrapper = document.createElement('div');
      wrapper.className = `operation-field ${['object', 'array', 'path_list'].includes(argument.type) ? 'full' : ''}`;
      const id = `operation-arg-${argument.name.replace(/[^A-Za-z0-9_-]/g, '-')}`;
      const label = document.createElement('label');
      label.htmlFor = id;
      label.innerHTML = `${escapeHtml(argument.label ?? argument.title ?? argument.name)}${argument.required ? ' <small>required</small>' : ''}`;
      wrapper.appendChild(label);
      const choices = argument.enum ?? argument.choices;
      let input;
      if (Array.isArray(choices)) {
        input = document.createElement('select');
        if (!argument.required) input.appendChild(new Option('—', ''));
        choices.forEach((choice) => input.appendChild(new Option(String(choice), String(choice))));
      } else if (argument.type === 'boolean' || typeof argument.default === 'boolean') {
        input = document.createElement('select');
        input.appendChild(new Option('Default', ''));
        input.appendChild(new Option('Yes', 'true'));
        input.appendChild(new Option('No', 'false'));
      } else if (argument.type === 'object' || argument.type === 'array' || argument.type === 'path_list') {
        input = document.createElement('textarea');
        input.placeholder = argument.type === 'path_list' ? 'One path per line' : argument.type === 'array' ? '["value"]' : '{"key": "value"}';
      } else {
        input = document.createElement('input');
        input.type = ['integer', 'number'].includes(argument.type) ? 'number' : 'text';
        if (argument.type === 'integer') input.step = '1';
        if (argument.type === 'number') input.step = 'any';
        if (argument.minimum !== undefined) input.min = String(argument.minimum);
        if (argument.maximum !== undefined) input.max = String(argument.maximum);
        input.placeholder = argument.placeholder ?? '';
      }
      if (argument.type === 'path' && argument.name === 'config') input.setAttribute('list', 'config-path-options');
      input.id = id;
      input.name = argument.name;
      input.dataset.valueType = argument.type ?? typeof argument.default ?? 'string';
      input.required = Boolean(argument.required);
      if (argument.default !== undefined && argument.default !== null) {
        input.value = typeof argument.default === 'object' ? JSON.stringify(argument.default, null, 2) : String(argument.default);
      }
      if (Object.hasOwn(draft, argument.name)) input.value = draft[argument.name];
      wrapper.appendChild(input);
      if (argument.description ?? argument.help) {
        const help = document.createElement('span');
        help.className = 'field-help';
        help.id = `${id}-help`;
        input.setAttribute('aria-describedby', help.id);
        help.textContent = argument.description ?? argument.help;
        wrapper.appendChild(help);
      }
      if (argument.depends_on) wrapper.dataset.dependsOn = argument.depends_on;
      (argument.group === 'advanced' ? advancedFields : fields).appendChild(wrapper);
    }
    if (advancedFields.children.length) fields.appendChild(advanced);
    updateOperationDependencies();
  }

  function updateOperationDependencies() {
    const fields = $('#operation-fields');
    for (const wrapper of fields.querySelectorAll('[data-depends-on]')) {
      const controller = fields.querySelector(`[name="${wrapper.dataset.dependsOn}"]`);
      const enabled = controller?.value !== 'false';
      wrapper.hidden = !enabled;
      wrapper.querySelectorAll('[name]').forEach((input) => { input.disabled = !enabled; });
    }
  }

  function collectOperationArguments() {
    const argumentsObject = {};
    for (const input of $('#operation-fields').querySelectorAll('[name]')) {
      if (input.disabled) continue;
      const raw = input.value.trim();
      if (!raw) continue;
      const type = input.dataset.valueType;
      if (type === 'integer') argumentsObject[input.name] = Number(raw);
      else if (type === 'number') argumentsObject[input.name] = Number(raw);
      else if (type === 'boolean') argumentsObject[input.name] = raw === 'true';
      else if (type === 'array' || type === 'object') {
        try {
          argumentsObject[input.name] = JSON.parse(raw);
        } catch (error) {
          throw new Error(`${input.name}: invalid JSON — ${error.message}`);
        }
      }
      else if (type === 'path_list') argumentsObject[input.name] = raw.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
      else argumentsObject[input.name] = raw;
      if (type === 'integer' && !Number.isSafeInteger(argumentsObject[input.name])) throw new Error(`${input.name}: enter a whole number within the supported range.`);
      if (type === 'number' && !Number.isFinite(argumentsObject[input.name])) throw new Error(`${input.name}: enter a finite number.`);
    }
    return argumentsObject;
  }

  async function submitOperation(event) {
    event.preventDefault();
    if (state.operationSubmitting) return;
    const result = $('#operation-result');
    const submitButton = $('#operation-form').querySelector('button[type="submit"]');
    const selectionRequest = state.jobSelectionRequest;
    state.operationSubmitting = true;
    submitButton.disabled = true;
    result.textContent = 'Starting job…';
    try {
      const payload = await fetchJson('/api/jobs', {
        method: 'POST',
        body: { operation: $('#operation-select').value, arguments: collectOperationArguments() },
      });
      const submittedJobId = String(payload?.id ?? payload?.job_id ?? '');
      result.dataset.jobId = submittedJobId;
      result.textContent = `Queued job ${submittedJobId}. It will start when the worker is available.`;
      await refreshJobs();
      if (submittedJobId && selectionRequest === state.jobSelectionRequest) {
        await selectJob(submittedJobId, { automatic: true });
        if (state.selectedJobId === submittedJobId && selectionRequest === state.jobSelectionRequest) {
          $('#job-detail-title').focus({ preventScroll: true });
          $('#job-detail-title').scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
        }
      }
    } catch (error) {
      delete result.dataset.jobId;
      result.innerHTML = `<div class="notice warning">The job could not be started. ${escapeHtml(error.message || String(error))}</div>`;
    } finally {
      state.operationSubmitting = false;
      const operation = state.operations.find((entry) => entry.name === $('#operation-select').value);
      submitButton.disabled = !operation || operation.available === false;
    }
  }

  function normalizeJobs(payload) {
    const jobs = Array.isArray(payload) ? payload : payload?.jobs ?? [];
    return jobs.map((job) => ({ ...job, id: String(job.id ?? job.job_id) }));
  }

  function jobStatus(job) {
    return String(job?.status ?? job?.state ?? 'unknown').toLowerCase();
  }

  function jobIsActive(job) {
    return ['pending', 'queued', 'running', 'cancelling', 'canceling'].includes(jobStatus(job));
  }

  function duration(seconds) {
    if (!Number.isFinite(seconds)) return '—';
    const value = Math.max(0, Math.floor(seconds));
    if (value < 60) return `${value}s`;
    if (value < 3600) return `${Math.floor(value / 60)}m ${value % 60}s`;
    return `${Math.floor(value / 3600)}h ${Math.floor(value % 3600 / 60)}m`;
  }

  function jobPresentation(job) {
    const status = jobStatus(job);
    const progress = job.progress && typeof job.progress === 'object' ? job.progress : {};
    const world = job.world_available || (job.operation === 'generate' && job.artifacts?.some((item) => item.name === 'output' && item.available));
    let title = progress.label || (status === 'running' ? 'Worker is starting' : status);
    let detail = progress.detail || '';
    if (status === 'queued' || status === 'pending') {
      title = 'Waiting for the worker';
      detail = job.queue_position > 1 ? `Queue position ${job.queue_position}. Jobs run one at a time.` : 'Next in line. Starts when the worker is available.';
    } else if (jobIsActive(job) && job.cancel_requested) {
      title = 'Stopping the job…';
      detail = 'Cancellation requested. Waiting for the worker and its subprocesses to stop.';
    } else if (status === 'failed') {
      title = world ? 'World saved · browser map failed' : 'Job failed';
      detail = world ? 'Your generated world is available. Prepare its browser map from the saved output without generating it again.' : detail || 'The job stopped before completion. Review the error and reuse its settings to try again.';
    } else if (status === 'cancelled') {
      title = world ? 'Stopped · generated world saved' : 'Job cancelled';
      detail = world ? 'The saved world is available below. Browser preparation did not finish.' : 'The worker has stopped. You can reuse the submitted settings.';
    } else if (['succeeded', 'completed'].includes(status)) {
      title = job.cache_dir ? 'Browser map ready' : world ? 'World generated and saved' : 'Job complete';
      detail = job.cache_dir ? 'Open the map to explore the result.' : world ? 'Download the world below, or prepare its browser map from this output.' : 'Results and available downloads are below.';
      if (job.map_superseded) detail = 'A newer job replaced the browser map at this destination. The saved world is unchanged; prepare its browser map again to explore this result.';
    }
    return { status, progress, title, detail, world };
  }

  function renderActivity() {
    const button = $('#job-activity');
    if (!button) return;
    const job = state.jobs.find((item) => jobIsActive(item) && jobStatus(item) !== 'queued')
      || state.jobs.find(jobIsActive) || state.jobs.find((item) => item.id === state.activityJobId);
    button.classList.toggle('hidden', !job);
    if (!job) return;
    state.activityJobId = job.id;
    const info = jobPresentation(job);
    const title = `${operationTitle(job.operation ?? 'Job')} · ${info.title}${state.jobsOffline || state.jobDetailFailed ? ' · Updates disconnected' : ''}`;
    if (button.textContent !== title) button.textContent = title;
    button.title = `Show job ${job.id}`;
    // A finished job stays visible as a shortcut to its result, without the
    // pulsing "working" indicator.
    const status = jobStatus(job);
    button.classList.toggle('finished', !jobIsActive(job));
    button.classList.toggle('failed', status === 'failed');
  }

  function renderJobs() {
    const list = $('#jobs-list');
    // Re-rendering replaces every row node, so skip it while the visible
    // selection/id/status shape is unchanged: polling must not drop keyboard
    // focus or swap a node out from under a click.
    if (!state.jobs.length) {
      list.innerHTML = '<p class="muted">No jobs have been submitted.</p>';
      return;
    }
    const ids = state.jobs.map((job) => job.id).join('|');
    if (state.jobsSignature !== ids) list.innerHTML = '';
    state.jobsSignature = ids;
    for (const job of state.jobs) {
      let button = [...list.children].find((item) => item.dataset.jobId === job.id);
      const fresh = !button;
      if (!button) button = document.createElement('button');
      button.dataset.jobId = job.id;
      button.type = 'button';
      const isSelected = state.selectedJobId === job.id;
      button.className = `job-row ${isSelected ? 'active' : ''}`;
      const operation = operationTitle(job.operation ?? job.name);
      const status = jobStatus(job);
      // Concise accessible name; the grid layout stays purely visual.
      const info = jobPresentation(job);
      button.setAttribute('aria-label', `${operation}, ${job.id}, ${info.title}`);
      button.setAttribute('aria-current', isSelected ? 'true' : 'false');
      const markup = `<strong>${escapeHtml(operation)} · ${escapeHtml(job.id)}</strong><span class="state-pill ${escapeHtml(status)}">${escapeHtml(jobIsActive(job) && job.cancel_requested ? 'stopping' : status)}</span>`
        + `<small class="job-row-phase">${escapeHtml(info.title)}</small><small>${duration(job.elapsed_seconds)}</small>`;
      if (button.innerHTML !== markup) button.innerHTML = markup;
      if (fresh) {
        button.addEventListener('click', () => selectJob(job.id));
        list.appendChild(button);
      }
    }
  }

  function artifactMarkup(artifacts, jobId, job = {}) {
    const list = Array.isArray(artifacts) ? artifacts : artifacts && typeof artifacts === 'object'
      ? Object.entries(artifacts).map(([name, value]) => (typeof value === 'object' ? { name, ...value } : { name, path: value }))
      : [];
    if (!list.length) return '';
    return '<div class="artifact-list"><p class="eyebrow">Artifacts</p>' + list.map((artifact, index) => {
      const name = artifact.name ?? artifact.label ?? artifact.path ?? 'artifact';
      const url = artifact.url ?? artifact.download_url ?? artifact.href
        ?? (artifact.available && jobId ? `/api/jobs/${encodeURIComponent(jobId)}/artifacts/${index}` : null);
      // Only allow same-origin paths and http(s) URLs: escapeHtml neutralizes
      // markup in the href but not a javascript: scheme from server data.
      if (url && (/^\//.test(url) || /^https?:\/\//i.test(url))) {
        return `<a href="${escapeHtml(url)}" download>${escapeHtml(name)} ↓</a>`;
      }
      const availability = jobIsActive(job) ? 'Destination · pending'
        : artifact.kind === 'cache' ? job.cache_dir ? 'Available via Open map' : 'No browser map for this job'
          : 'No download produced by this job';
      return `<div class="catalog-item"><strong>${escapeHtml(name)}</strong><small>${escapeHtml(availability)}</small><small>${escapeHtml(artifact.path ?? artifact.kind ?? '')}</small></div>`;
    }).join('') + '</div>';
  }

  function renderJobDetail(job) {
    if (!job) return;
    const { status, progress, title, detail, world } = jobPresentation(job);
    state.selectedJob = job;
    renderJobActions(job);
    $('#job-detail-title').textContent = `${job.operation ?? job.name ?? 'Job'} · ${job.id ?? job.job_id}`;
    const active = jobIsActive(job);
    const bounded = active && !job.cancel_requested && Number.isFinite(progress.current)
      && Number.isFinite(progress.total) && progress.total > 0 && progress.current >= 0 && progress.current <= progress.total;
    const progressMarkup = bounded
      ? `<progress class="job-progress" aria-label="${escapeHtml(progress.label || 'Current stage')}" max="${progress.total}" value="${progress.current}"></progress><p class="job-count">${progress.current} / ${progress.total} · current stage</p>`
      : active && status !== 'queued' && !job.cancel_requested
        ? '<progress class="job-progress" aria-label="Current stage in progress"></progress>' : '';
    const elapsed = duration(status === 'queued' ? job.phase_elapsed_seconds : job.elapsed_seconds);
    const timing = `<dl class="job-timing"><div><dt>${status === 'queued' ? 'Waiting' : 'Elapsed'}</dt><dd>${elapsed}</dd></div>`
      + (active && status !== 'queued' ? `<div><dt>In this stage</dt><dd>${duration(job.phase_elapsed_seconds)}</dd></div><div><dt>Last worker output</dt><dd>${duration(job.seconds_since_activity)} ago</dd></div>` : '') + '</dl>';
    const lifecycle = job.operation === 'generate'
      ? `<ol class="job-lifecycle" aria-label="Generation workflow"><li class="${world ? 'done' : status === 'running' ? 'current' : ''}">Generate world${world ? '<span class="sr-only"> (done)</span>' : ''}</li><li class="${job.cache_dir ? 'done' : world && active ? 'current' : ''}">${job.arguments?.open_in_web === false ? 'Browser map optional' : 'Prepare browser map'}${job.cache_dir ? '<span class="sr-only"> (done)</span>' : ''}</li><li class="${job.cache_dir ? 'done' : ''}">Explore</li></ol>` : '';
    const waiting = active && status !== 'queued' && !bounded && !job.cancel_requested
      ? '<p class="muted job-estimate">Working on the stage above. Overall percentage and finish time are not estimated.</p>' : '';
    const statusMarkup = `<div class="job-stage"><span class="state-pill ${escapeHtml(status)}">${escapeHtml(active && job.cancel_requested ? 'stopping' : status)}</span><h3>${escapeHtml(title)}</h3><p>${escapeHtml(detail)}</p></div>`
      + progressMarkup + timing + waiting + lifecycle
      + (job.error ? `<div class="notice warning job-error"><strong>Error</strong><p>${escapeHtml(status === 'failed' && progress.detail ? progress.detail : job.error)}</p></div>` : '')
      + (active && job.cancellable === false && !job.cancel_requested ? '<p class="muted">Finishing publication. Cancellation is unavailable during this final step.</p>' : '');
    const logs = String(Array.isArray(job.logs) ? job.logs.join('\n') : job.logs ?? job.log ?? job.message ?? '');
    const meta = [['Created', job.created_at], ['Started', job.started_at], ['Finished', job.finished_at ?? job.completed_at], ['Exit code', job.exit_code]]
      .filter(([, value]) => value !== undefined && value !== null && value !== '');
    const argumentsMarkup = `<details class="job-arguments"><summary>Submitted settings &amp; timestamps</summary><dl class="job-meta">${meta.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(displayCell(value))}</dd>`).join('')}</dl><pre class="json-block">${escapeHtml(jsonText(job.arguments ?? {}))}</pre></details>`;
    const artifacts = artifactMarkup(job.artifacts ?? job.outputs, job.id ?? job.job_id, job);
    const root = $('#job-detail');
    const existing = root.querySelector('.job-status-content');
    const logText = logs || 'Waiting for the first worker output. Stage updates will appear above.';
    if (!existing || root.dataset.jobId !== String(job.id)) {
      root.dataset.jobId = String(job.id);
      root.innerHTML = `<div class="job-status-content">${statusMarkup}</div><div class="job-artifacts">${artifacts}</div>`
        + argumentsMarkup + `<details class="job-log-details"><summary>Technical log</summary><p class="muted">Scroll up to pause following new output. Only the most recent log output is retained.</p><pre class="job-log" tabindex="0" aria-label="Worker output">${escapeHtml(logText)}</pre></details>`;
    } else {
      if (existing.innerHTML !== statusMarkup) existing.innerHTML = statusMarkup;
      const artifactNode = root.querySelector('.job-artifacts');
      if (artifactNode.innerHTML !== artifacts) artifactNode.innerHTML = artifacts;
      const log = root.querySelector('.job-log');
      if (log.textContent !== logText) log.textContent = logText;
      const metaNode = root.querySelector('.job-meta');
      const newMeta = meta.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(displayCell(value))}</dd>`).join('');
      if (metaNode.innerHTML !== newMeta) metaNode.innerHTML = newMeta;
    }
    const announcement = $('#job-announcement');
    if (announcement && announcement.textContent !== title) announcement.textContent = title;
    const cancel = $('#job-cancel');
    cancel.classList.toggle('hidden', !active);
    cancel.disabled = Boolean(job.cancel_requested || job.cancellable === false);
    cancel.textContent = job.cancel_requested ? 'Stopping…' : 'Cancel job';
  }

  async function selectJob(id, { preserveScroll = false, automatic = false } = {}) {
    if (!automatic) state.jobSelectionRequest += 1;
    const changingJob = state.selectedJobId !== String(id);
    state.selectedJobId = String(id);
    const requestId = ++state.jobDetailRequest;
    const oldLog = $('#job-detail').querySelector('.job-log');
    const oldScroll = oldLog?.scrollTop ?? 0;
    const wasAtBottom = oldLog ? oldLog.scrollHeight - oldLog.clientHeight - oldScroll < 8 : true;
    if (changingJob) {
      state.selectedJobStatus = null;
      state.selectedJob = null;
      state.jobActionsSignature = null;
      $('#job-actions').innerHTML = '';
      $('#job-cancel').classList.add('hidden');
      $('#job-detail-title').textContent = `Loading job ${id}…`;
      $('#job-detail').textContent = 'Loading job details…';
    }
    renderJobs();
    try {
      const job = await fetchJson(`/api/jobs/${encodeURIComponent(id)}`);
      if (requestId !== state.jobDetailRequest || state.selectedJobId !== String(id)) return;
      state.jobDetailFailed = false;
      $('#job-connection').textContent = '';
      renderActivity();
      state.selectedJobStatus = jobStatus(job);
      renderJobDetail({ ...job, id: String(job.id ?? job.job_id ?? id) });
      if (preserveScroll) {
        const newLog = $('#job-detail').querySelector('.job-log');
        if (newLog) newLog.scrollTop = wasAtBottom ? newLog.scrollHeight : oldScroll;
      }
    } catch (error) {
      if (requestId !== state.jobDetailRequest || state.selectedJobId !== String(id)) return;
      state.jobDetailFailed = true;
      $('#job-connection').textContent = `Job updates disconnected. Showing the last received state; retrying automatically. ${error.message || String(error)}`;
      $('#jobs-poll-state').textContent = 'Updates delayed';
      $('#jobs-poll-state').className = 'state-pill failed';
      renderActivity();
    }
  }

  function refreshJobs() {
    // Reuse the pending poll instead of invalidating it every 2.5 seconds.
    if (state.jobsRefreshPending) return state.jobsRefreshPending;
    const pending = refreshJobsOnce();
    state.jobsRefreshPending = pending;
    return pending.finally(() => { if (state.jobsRefreshPending === pending) state.jobsRefreshPending = null; });
  }

  async function refreshJobsOnce() {
    const requestId = ++state.jobListRequest;
    let payload;
    try {
      payload = await fetchJson('/api/jobs');
    } catch (error) {
      if (requestId === state.jobListRequest) {
        $('#jobs-poll-state').className = 'state-pill failed';
        $('#jobs-poll-state').textContent = 'Offline';
        $('#jobs-poll-state').title = error.message || String(error);
        state.jobsOffline = true;
        $('#job-connection').textContent = 'Connection lost. Showing the last received state; reconnecting automatically. Jobs may still be running on the server.';
        renderActivity();
      }
      return;
    }
    if (requestId !== state.jobListRequest) return;
    const previousJobs = state.jobsLoaded ? state.jobs : null;
    $('#jobs-poll-state').className = 'state-pill available';
    $('#jobs-poll-state').textContent = 'Live';
    $('#jobs-poll-state').title = '';
    state.jobsOffline = false;
    if (!state.jobDetailFailed) $('#job-connection').textContent = '';
    state.jobs = normalizeJobs(payload);
    state.jobsLoaded = true;
    try {
      onJobsChanged(previousJobs, state.jobs);
    } catch (error) {
      console.warn(error);
    }
    renderActivity();
    const submission = $('#operation-result');
    const submitted = state.jobs.find((job) => job.id === submission.dataset.jobId);
    if (submitted) {
      const status = jobStatus(submitted);
      submission.textContent = status === 'queued' ? `Queued job ${submitted.id}. ${jobPresentation(submitted).detail}`
        : status === 'running' ? `Job ${submitted.id}: ${jobPresentation(submitted).title}.`
          : `Job ${submitted.id} ${status}. Review its results below.`;
    }
    renderJobs();
    if (state.selectedJobId) {
      const selected = state.jobs.find((job) => job.id === state.selectedJobId);
      if (!selected) {
        // The job vanished server-side (restart or pruning); drop the stale
        // detail view instead of offering a Cancel button that would 404.
        state.selectedJobId = null;
        state.selectedJobStatus = null;
        state.selectedJob = null;
        $('#job-actions').innerHTML = '';
        $('#job-detail-title').textContent = 'No job selected';
        $('#job-detail').innerHTML = '<div class="notice warning">The selected job is no longer available — it was removed from the server.</div>';
        $('#job-cancel').classList.add('hidden');
        state.jobsSignature = null;
        renderJobs();
      } else if (jobIsActive(selected) || jobStatus(selected) !== state.selectedJobStatus || state.jobDetailFailed
        || selected.cache_dir !== state.selectedJob?.cache_dir || selected.map_superseded !== state.selectedJob?.map_superseded) {
        await selectJob(selected.id, { preserveScroll: true, automatic: true });
      }
    } else if (!state.operationSubmitting) {
      const active = state.jobs.find((item) => jobIsActive(item) && jobStatus(item) !== 'queued') || state.jobs.find(jobIsActive);
      if (active) await selectJob(active.id, { automatic: true });
    }
  }

  async function cancelSelectedJob() {
    if (!state.selectedJobId) return;
    const jobId = state.selectedJobId;
    const button = $('#job-cancel');
    button.disabled = true;
    button.textContent = 'Requesting stop…';
    try {
      const job = await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
      if (job?.id && state.selectedJobId === jobId) renderJobDetail(job);
      await refreshJobs();
      if (state.selectedJobId === jobId) await selectJob(jobId, { automatic: true });
    } catch (error) {
      if (state.selectedJobId === jobId) {
        $('#job-connection').textContent = `Cancellation could not be confirmed. ${error.message || String(error)}`;
      }
    } finally {
      if (state.selectedJobId === jobId || !state.selectedJobId) {
        const selected = state.selectedJobId === jobId ? state.selectedJob : null;
        button.disabled = Boolean(selected?.cancel_requested || selected?.cancellable === false);
        button.textContent = selected?.cancel_requested ? 'Stopping…' : 'Cancel job';
      }
    }
  }

  function renderQuickOperations() {
    const container = $('#operation-quick');
    if (!container) return;
    const current = $('#operation-select').value;
    container.innerHTML = QUICK_OPERATIONS
      .map((name) => state.operations.find((entry) => entry.name === name))
      .filter(Boolean)
      .map((operation) => `<button type="button" class="chip${operation.name === current ? ' active' : ''}" data-quick-operation="${escapeHtml(operation.name)}" aria-pressed="${operation.name === current}">${escapeHtml(operation.title)}</button>`)
      .join('');
  }

  function chooseOperation(name) {
    const select = $('#operation-select');
    if (!state.operations.some((entry) => entry.name === name)) return;
    select.value = name;
    renderOperationForm();
    renderQuickOperations();
  }

  async function loadOperations() {
    const payload = await optionalJson('/api/operations');
    state.operations = normalizeOperations(payload);
    const select = $('#operation-select');
    select.innerHTML = '';
    for (const operation of state.operations) {
      const option = document.createElement('option');
      option.value = operation.name;
      option.textContent = operation.title;
      select.appendChild(option);
    }
    if (!state.operations.length) {
      select.appendChild(new Option('No operations available', ''));
      $('#operation-form').querySelector('button[type="submit"]').disabled = true;
    }
    renderQuickOperations();
    renderOperationForm();
    await refreshJobs();
  }


  return { renderQuickOperations, chooseOperation, operationTitle, jobPresentation, prepareOperation, renderJobActions, normalizeOperations, operationArguments, renderOperationForm, updateOperationDependencies, collectOperationArguments, submitOperation, normalizeJobs, jobStatus, jobIsActive, renderJobs, artifactMarkup, renderJobDetail, selectJob, refreshJobs, cancelSelectedJob, loadOperations };
}
