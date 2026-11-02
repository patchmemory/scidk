/**
 * ask_scope.js — carries a selection into the existing chat page.
 *
 * "Ask about this" (selection_actions.js) stores the selected rows' kind/key/label in sessionStorage and
 * opens /chat?scope=selection. This shows what was carried and starts the message with the labels; the
 * user still writes and sends the question. Nothing is sent from here, and the stored scope is read once.
 */
;(function () {
  'use strict';
  const KEY = 'scidk.ask.scope.v1';
  const MAX_AGE_MS = 10 * 60 * 1000;
  function run() {
    if (new URLSearchParams(location.search).get('scope') !== 'selection') return;
    const form = document.getElementById('chat-form'), input = document.getElementById('chat-input');
    if (!form || !input) return;
    let scope = null;
    try { scope = JSON.parse(sessionStorage.getItem(KEY) || 'null'); sessionStorage.removeItem(KEY); } catch (e) { scope = null; }
    if (!scope || !Array.isArray(scope.items) || !scope.items.length || Date.now() - (scope.at || 0) > MAX_AGE_MS) return;
    const labels = scope.items.map(i => String(i.label || i.key)).slice(0, 10);
    const more = Math.max(0, (scope.count || scope.items.length) - labels.length);
    const banner = document.createElement('div');
    banner.id = 'ask-scope-banner';
    banner.setAttribute('data-testid', 'ask-scope-banner');
    banner.setAttribute('role', 'status');
    banner.style.cssText = 'font-size:12px;background:#e7f1ff;border:1px solid #b6d4fe;border-radius:6px;padding:6px 10px;margin-bottom:6px;';
    banner.textContent = 'Asking about ' + (scope.count || scope.items.length) + ' selected item(s): ' + labels.join(', ') + (more ? ' … and ' + more + ' more' : '');
    form.insertBefore(banner, form.firstChild);
    if (!input.value) input.value = 'About ' + labels.join(', ') + (more ? ' (and ' + more + ' more)' : '') + ': ';
    input.focus();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();
