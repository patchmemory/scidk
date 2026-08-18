/**
 * drawers.js — shared drawer manager for all SciDK side panels
 *
 * Exposes: window.Drawers
 *   .open(id)   — open a drawer by element id, closing any currently open one
 *   .close()    — close the active drawer
 *   .active()   — returns the currently open drawer id, or null
 *
 * Usage:
 *   window.Drawers.open('annotate-drawer');
 *   window.Drawers.close();
 *
 * Any element with [data-close-drawer] inside a drawer closes it on click.
 * Escape key closes the active drawer (or save-as menu if open first).
 * Backdrop click closes the active drawer.
 */
;(function(global) {
  'use strict';

  const backdrop = document.getElementById('drawer-backdrop');
  let _active = null;

  function open(id) {
    if (_active && _active !== id) {
      const prev = document.getElementById(_active);
      if (prev) prev.classList.remove('open');
    }
    const el = document.getElementById(id);
    if (!el) { console.warn('Drawers.open: no element with id', id); return; }
    el.classList.add('open');
    if (backdrop) backdrop.classList.add('open');
    _active = id;
  }

  function close() {
    if (_active) {
      const el = document.getElementById(_active);
      if (el) el.classList.remove('open');
      _active = null;
    }
    if (backdrop) backdrop.classList.remove('open');
  }

  function active() { return _active; }

  // Backdrop click
  if (backdrop) backdrop.addEventListener('click', close);

  // [data-close-drawer] buttons — delegate from document
  document.addEventListener('click', e => {
    if (e.target.closest('[data-close-drawer]')) close();
  });

  // Escape key — collected by each panel's own handler for ordering,
  // but fall through closes the active drawer
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && _active) close();
  });

  global.Drawers = { open, close, active };

})(window);
