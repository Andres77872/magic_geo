// CommandPalette: keyboard-first search across views, actions, layers, worlds,
// configurations and jobs. Implemented as an ARIA combobox in a modal <dialog>:
// focus stays in the input while arrow keys move the active option.
export function createCommandPalette({ $, escapeHtml, icon, getItems, getQueryItems = () => [] }) {
  const GROUP_LIMITS = { Layers: 40, Worlds: 12, Configurations: 12, Jobs: 8, Places: 12 };
  let items = [];
  let results = [];
  let active = 0;
  let opener = null;

  function dialog() { return $('#command-palette'); }

  function isOpen() { return Boolean(dialog()?.open); }

  // Subsequence match with bonuses for prefix, word starts and contiguous runs.
  function score(text, query) {
    const haystack = text.toLowerCase();
    if (!query) return 1;
    const direct = haystack.indexOf(query);
    if (direct === 0) return 1000 - haystack.length;
    if (direct > 0) {
      const boundary = /[\s/_.\-·]/.test(haystack[direct - 1]);
      return (boundary ? 800 : 600) - direct - haystack.length * 0.1;
    }
    let position = -1;
    let total = 0;
    let run = 0;
    for (const char of query) {
      const next = haystack.indexOf(char, position + 1);
      if (next < 0) return -1;
      run = next === position + 1 ? run + 1 : 0;
      const boundary = next === 0 || /[\s/_.\-·]/.test(haystack[next - 1]);
      total += 5 + run * 4 + (boundary ? 8 : 0) - Math.min(next - position, 10) * 0.5;
      position = next;
    }
    return Math.max(1, total);
  }

  function matchItem(item, query) {
    if (!query) return item.suggested ? 1 : -1;
    const words = query.split(/\s+/).filter(Boolean);
    let total = 0;
    for (const word of words) {
      const best = Math.max(score(item.title, word) * 1.2, score(item.keywords || '', word), score(item.hint || '', word) * 0.6);
      if (best <= 0) return -1;
      total += best;
    }
    return total + (item.boost || 0);
  }

  function highlight(title, query) {
    const word = query.split(/\s+/).find(Boolean);
    if (!word) return escapeHtml(title);
    const index = title.toLowerCase().indexOf(word.toLowerCase());
    if (index < 0) return escapeHtml(title);
    return `${escapeHtml(title.slice(0, index))}<mark>${escapeHtml(title.slice(index, index + word.length))}</mark>${escapeHtml(title.slice(index + word.length))}`;
  }

  function search(query) {
    const needle = query.trim().toLowerCase();
    // Items built from the query itself (coordinates, a cell number) always
    // match and lead the results.
    const direct = (getQueryItems(query.trim()) || []).map((item) => ({ item, score: Infinity }));
    const scored = direct.concat(items
      .map((item) => ({ item, score: matchItem(item, needle) }))
      .filter((entry) => entry.score > 0)
      .sort((a, b) => b.score - a.score));
    const counts = {};
    const limited = [];
    for (const entry of scored) {
      const group = entry.item.group;
      counts[group] = (counts[group] || 0) + 1;
      if (counts[group] <= (GROUP_LIMITS[group] ?? 20)) limited.push(entry.item);
    }
    // Group in a stable order, keeping each group's best matches first.
    const order = [];
    for (const item of limited) if (!order.includes(item.group)) order.push(item.group);
    return order.flatMap((group) => limited.filter((item) => item.group === group));
  }

  function render(query) {
    const container = $('#command-results');
    results = search(query);
    active = Math.min(active, Math.max(0, results.length - 1));
    if (!results.length) {
      container.innerHTML = `<div class="command-empty">No matches for “${escapeHtml(query.trim())}”. Try a layer name like <code>elevation</code>, a world, or an action like <code>generate</code>.</div>`;
      $('#command-input').removeAttribute('aria-activedescendant');
      return;
    }
    let group = null;
    const parts = [];
    results.forEach((item, index) => {
      if (item.group !== group) {
        group = item.group;
        parts.push(`<div class="command-group" role="presentation">${escapeHtml(group)}</div>`);
      }
      parts.push(`<div class="command-item" role="option" id="command-option-${index}" data-index="${index}" aria-selected="${index === active}">`
        + `${icon(item.icon || 'arrow-right')}<span class="command-item-text"><span class="command-item-title">${highlight(item.title, query)}</span>`
        + `${item.hint ? `<span class="command-item-hint">${escapeHtml(item.hint)}</span>` : ''}</span>`
        + `${item.shortcut ? `<kbd>${escapeHtml(item.shortcut)}</kbd>` : ''}</div>`);
    });
    container.innerHTML = parts.join('');
    syncActive();
  }

  function syncActive() {
    const container = $('#command-results');
    container.querySelectorAll('.command-item').forEach((node) => {
      node.setAttribute('aria-selected', String(Number(node.dataset.index) === active));
    });
    const current = container.querySelector(`#command-option-${active}`);
    if (current) {
      $('#command-input').setAttribute('aria-activedescendant', current.id);
      current.scrollIntoView({ block: 'nearest' });
    }
  }

  function move(delta) {
    if (!results.length) return;
    active = (active + delta + results.length) % results.length;
    syncActive();
  }

  function run(index = active) {
    const item = results[index];
    if (!item) return;
    close({ restoreFocus: false });
    try {
      const outcome = item.run();
      if (outcome && typeof outcome.catch === 'function') outcome.catch((error) => console.error(error));
    } catch (error) {
      console.error(error);
    }
  }

  function open(query = '') {
    const node = dialog();
    if (!node || node.open) return;
    opener = document.activeElement;
    items = getItems();
    active = 0;
    const input = $('#command-input');
    input.value = query;
    render(query);
    node.showModal();
    input.focus();
    input.select();
  }

  function close({ restoreFocus = true } = {}) {
    const node = dialog();
    if (!node?.open) return;
    node.close();
    if (restoreFocus && opener instanceof HTMLElement && document.contains(opener)) opener.focus();
    opener = null;
  }

  function toggle() {
    if (isOpen()) close();
    else open();
  }

  function wire() {
    const input = $('#command-input');
    input.addEventListener('input', () => { active = 0; render(input.value); });
    input.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown') { event.preventDefault(); move(1); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); move(-1); }
      else if (event.key === 'Home' && event.ctrlKey) { event.preventDefault(); active = 0; syncActive(); }
      else if (event.key === 'End' && event.ctrlKey) { event.preventDefault(); active = results.length - 1; syncActive(); }
      else if (event.key === 'Enter') { event.preventDefault(); run(); }
    });
    const list = $('#command-results');
    list.addEventListener('click', (event) => {
      const option = event.target.closest('.command-item');
      if (option) run(Number(option.dataset.index));
    });
    list.addEventListener('mousemove', (event) => {
      const option = event.target.closest('.command-item');
      if (option && Number(option.dataset.index) !== active) {
        active = Number(option.dataset.index);
        syncActive();
      }
    });
    const node = dialog();
    // Clicking the backdrop (the dialog box itself, outside its content) closes it.
    node.addEventListener('click', (event) => { if (event.target === node) close(); });
    node.addEventListener('cancel', (event) => { event.preventDefault(); close(); });
  }

  return { open, close, toggle, isOpen, wire, search: (query) => { items = getItems(); return search(query); } };
}
