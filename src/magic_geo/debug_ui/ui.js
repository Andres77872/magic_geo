// Shared presentation helpers: icons, toasts, theme and safe local storage.
//
// This module has no import-time side effects. It is loaded by the browser as an
// ES module and by the Node test harness as plain script text, so every browser
// API is reached lazily and guarded.

const STORAGE_PREFIX = 'magic-geo.';

export function storageGet(key, fallback = null) {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_PREFIX + key);
    return raw === null || raw === undefined ? fallback : JSON.parse(raw);
  } catch (_) {
    return fallback;
  }
}

export function storageSet(key, value) {
  try {
    globalThis.localStorage?.setItem(STORAGE_PREFIX + key, JSON.stringify(value));
  } catch (_) {
    // Private windows and blocked storage keep working without persistence.
  }
}

// Inline reference to a symbol in the page's SVG sprite.
export function icon(name, className = '') {
  return `<svg class="icon${className ? ` ${className}` : ''}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

function escapeText(text) {
  return String(text ?? '').replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

// ---------------------------------------------------------------------------
// Theme

export function currentTheme() {
  return globalThis.document?.documentElement?.dataset?.theme === 'light' ? 'light' : 'dark';
}

export function applyTheme(theme, { persist = true } = {}) {
  const root = globalThis.document?.documentElement;
  if (!root) return;
  const next = theme === 'light' ? 'light' : 'dark';
  root.dataset.theme = next;
  if (persist) storageSet('theme', next);
  const toggle = globalThis.document.querySelector?.('#theme-toggle');
  if (toggle?.setAttribute) {
    const label = next === 'light' ? 'Switch to dark theme' : 'Switch to light theme';
    toggle.setAttribute('aria-label', label);
    toggle.title = label;
  }
}

export function toggleTheme() {
  applyTheme(currentTheme() === 'light' ? 'dark' : 'light');
}

// ---------------------------------------------------------------------------
// Toasts: transient system messages. A toast with an action stays until the
// person dismisses it or uses the action; plain confirmations fade on their own.

const TOAST_ICONS = { success: 'check-circle', error: 'alert', warning: 'alert', info: 'info' };

export function toast({ title, message = '', tone = 'info', action = null, timeout } = {}) {
  const doc = globalThis.document;
  const region = doc?.querySelector?.('#toast-region');
  if (!region || typeof doc.createElement !== 'function') return null;
  const node = doc.createElement('div');
  node.className = `toast ${tone}`;
  node.setAttribute?.('role', tone === 'error' ? 'alert' : 'status');
  node.innerHTML = `${icon(TOAST_ICONS[tone] || 'info')}<div><strong>${escapeText(title)}</strong>`
    + `${message ? `<p>${escapeText(message)}</p>` : ''}`
    + `${action ? `<div class="button-row"><button type="button" class="small primary" data-toast-action>${escapeText(action.label)}</button></div>` : ''}</div>`
    + `<button type="button" class="icon-button" data-toast-close aria-label="Dismiss notification">${icon('x')}</button>`;
  let timer = 0;
  const dismiss = () => {
    if (timer && typeof globalThis.clearTimeout === 'function') globalThis.clearTimeout(timer);
    if (!node.isConnected) return;
    node.classList?.add('leaving');
    const remove = () => node.remove?.();
    if (typeof globalThis.setTimeout === 'function') globalThis.setTimeout(remove, 190);
    else remove();
  };
  node.querySelector?.('[data-toast-close]')?.addEventListener('click', dismiss);
  node.querySelector?.('[data-toast-action]')?.addEventListener('click', () => {
    dismiss();
    action?.onClick?.();
  });
  region.appendChild(node);
  // Keep at most four visible; the oldest yields first.
  while (region.children?.length > 4) region.children[0].remove?.();
  const lifetime = timeout ?? (action ? 0 : tone === 'error' ? 9000 : 5000);
  if (lifetime > 0 && typeof globalThis.setTimeout === 'function') timer = globalThis.setTimeout(dismiss, lifetime);
  return { dismiss };
}

// ---------------------------------------------------------------------------
// Formatting

export function relativeTime(value, now = Date.now()) {
  const time = typeof value === 'number' ? value : Date.parse(value);
  if (!Number.isFinite(time)) return '';
  const seconds = Math.round((now - time) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return 'just now';
  const units = [['minute', 60], ['hour', 3600], ['day', 86400], ['week', 604800], ['month', 2629800], ['year', 31557600]];
  let unit = 'minute';
  let size = 60;
  for (const [name, span] of units) {
    if (abs >= span) { unit = name; size = span; }
  }
  const count = Math.max(1, Math.round(abs / size));
  const label = `${count} ${unit}${count === 1 ? '' : 's'}`;
  return seconds >= 0 ? `${label} ago` : `in ${label}`;
}

export function formatCount(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return number.toLocaleString('en-US');
}

// Stable hue from a string, used for world avatars.
export function hueFor(text) {
  let hash = 0;
  for (const char of String(text ?? '')) hash = (hash * 31 + char.codePointAt(0)) >>> 0;
  return hash % 360;
}

export function isMacPlatform() {
  const platform = globalThis.navigator?.userAgentData?.platform || globalThis.navigator?.platform || '';
  return /mac|iphone|ipad/i.test(platform);
}

export function prefersReducedMotion() {
  try {
    return Boolean(globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
  } catch (_) {
    return false;
  }
}
