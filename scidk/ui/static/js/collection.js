/**
 * collection.js — Files page selection actions over the shared Collection control.
 *
 * There is exactly one collection UI: window.CollectionBasket (collection_basket.js,
 * loaded by base.html), mounted in the Files toolbar at #files-collection-slot.
 * This module keeps no list of its own. It does two things for the Files table:
 *
 *   1. "Add to collection"            — selected rows → shared basket entries
 *                                       (path + provider/root/scan identity; folders stay
 *                                       Folder references, never enumerated).
 *   2. "Create dataset from selection…" — a compact dialog (name required, description
 *                                       optional) → POST /api/datasets/manual, which
 *                                       creates a NEW manual :Dataset. Never a Collection,
 *                                       never an update to a recognized Dataset.
 *
 * It also highlights rows already picked, and exposes `window.Collection` as a thin
 * compatibility adapter over the basket (no state of its own):
 *   .items() .count() .add(entries) .remove(name) .clear() .open() .close() .toggle()
 *   .entryFromId(id) .payload(f)
 *
 * Keyboard: Shift+Alt+C toggles the collection panel.
 */
;(function (global) {
  'use strict';

  const BASE = () => (typeof global.SCIDK_BASE !== 'undefined') ? global.SCIDK_BASE : '';
  const basket = () => global.CollectionBasket;

  function _say(msg, cls) {
    if (typeof global.setStatus === 'function') global.setStatus(msg, cls || '');
  }

  // ── entries ──
  function _dirOf(path) {
    const s = String(path || '');
    const cut = s.lastIndexOf('/');
    return cut > 0 ? s.slice(0, cut) : '';
  }

  // A Files selection id (full path) as an entry: folder in `path`, basename in `name`.
  function entryFromId(id) {
    const it = basket().fileItemFromId(id);
    return {
      name: it.p.name, path: _dirOf(it.p.path), provider_id: it.p.provider_id,
      root_id: it.p.root_id, scan_id: it.p.scan_id, type: it.kind === 'folder' ? 'folder' : 'file',
    };
  }

  function _fullPath(f) {
    const dir = (f.path || '').replace(/\/+$/, '');
    if (!dir) return f.name || '';
    return dir.endsWith('/' + f.name) || dir === f.name ? dir : dir + '/' + f.name;
  }

  function payload(f) {
    return {
      name: f.name, path: _fullPath(f), type: f.type || 'file',
      provider_id: f.provider_id || '', root_id: f.root_id || '', scan_id: f.scan_id || '',
    };
  }

  function _rowSize(id) {
    const tr = [...document.querySelectorAll('#file-list tr[data-id]')].find(r => r.dataset.id === id);
    return tr && tr.dataset.size ? Number(tr.dataset.size) : null;
  }

  function _selectedIds() {
    return global.selItems ? [...global.selItems] : [];
  }

  function _clearSelection() {
    if (global.selItems) global.selItems.clear();
    document.querySelectorAll('#file-list .row-cb').forEach(cb => { cb.checked = false; });
    if (typeof global.updateSelUI === 'function') global.updateSelUI();
  }

  // ── thin adapter over the shared basket ──
  function items() {
    return basket().items().filter(x => x.kind === 'file' || x.kind === 'folder').map(x => ({
      name: x.p.name, path: _dirOf(x.p.path), type: x.kind,
      provider_id: x.p.provider_id || '', root_id: x.p.root_id || '', scan_id: x.p.scan_id || '', size: x.p.size,
    }));
  }
  function count() { return items().length; }
  function add(entries) {
    return basket().add((Array.isArray(entries) ? entries : [entries]).map(f => basket().fileItemFromId(_fullPath(f), f.size)));
  }
  function remove(name) {
    basket().items().filter(x => (x.kind === 'file' || x.kind === 'folder') && x.p.name === name).forEach(x => basket().remove(x.key));
  }
  function clear() { basket().clear(); }

  // ── row highlights ──
  function _updateHighlights() {
    if (!basket()) return;
    const keys = new Set(basket().items().map(x => x.key));
    document.querySelectorAll('#file-list tr[data-id]').forEach(tr => {
      tr.classList.toggle('in-coll', keys.has(basket().fileItemFromId(tr.dataset.id).key));
    });
  }

  // ── Add to collection ──
  function addSelectionToCollection() {
    const ids = _selectedIds();
    if (!ids.length) { _say('No files selected'); return; }
    const picked = ids.map(id => basket().fileItemFromId(id, _rowSize(id)));
    const n = basket().add(picked);
    _clearSelection();
    basket().open();
    _updateHighlights();
    _say(n ? n + ' added to the collection' : 'Already in the collection');
  }

  // ── Create dataset from selection… ──
  function _closeDialog() { document.getElementById('manual-ds-overlay')?.remove(); }

  function openManualDatasetDialog() {
    const ids = _selectedIds();
    if (!ids.length) { _say('No files selected'); return; }
    const members = ids.map(id => {
      const it = basket().fileItemFromId(id, _rowSize(id));
      return Object.assign({kind: it.kind}, it.p);
    });
    const nFolders = members.filter(m => m.kind === 'folder').length;
    const nFiles = members.length - nFolders;
    _closeDialog();

    const overlay = document.createElement('div');
    overlay.id = 'manual-ds-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:1300;display:flex;align-items:center;justify-content:center;';
    const box = document.createElement('div');
    box.id = 'manual-ds-dialog';
    box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', 'Create dataset from selection');
    box.setAttribute('data-testid', 'manual-dataset-dialog');
    box.style.cssText = 'background:#fff;border-radius:8px;padding:16px;width:380px;max-width:92vw;box-shadow:0 8px 28px rgba(0,0,0,.25);font-size:13px;';

    const h = document.createElement('div');
    h.textContent = 'Create dataset from selection';
    h.style.cssText = 'font-weight:600;font-size:14px;margin-bottom:4px;';
    const note = document.createElement('div');
    note.style.cssText = 'color:#6c757d;font-size:11px;margin-bottom:8px;';
    note.textContent = 'A new manual Dataset of ' + nFiles + ' file' + (nFiles === 1 ? '' : 's') + ' and ' + nFolders +
      ' folder' + (nFolders === 1 ? '' : 's') + '. It is not a Collection, and it does not change any recognized dataset.';
    const name = document.createElement('input');
    name.type = 'text'; name.id = 'manual-ds-name'; name.className = 'form-control form-control-sm mb-2';
    name.placeholder = 'Dataset name (required)'; name.maxLength = 200;
    name.setAttribute('aria-label', 'Dataset name');
    const desc = document.createElement('textarea');
    desc.id = 'manual-ds-desc'; desc.className = 'form-control form-control-sm mb-2'; desc.rows = 2;
    desc.placeholder = 'Description (optional)';
    desc.setAttribute('aria-label', 'Dataset description');
    const status = document.createElement('div');
    status.id = 'manual-ds-status'; status.setAttribute('role', 'status');
    status.style.cssText = 'font-size:11px;color:#6c757d;min-height:16px;margin-bottom:6px;';
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:6px;justify-content:flex-end;';
    const cancel = document.createElement('button');
    cancel.type = 'button'; cancel.id = 'manual-ds-cancel'; cancel.className = 'btn btn-sm btn-outline-secondary'; cancel.textContent = 'Cancel';
    const create = document.createElement('button');
    create.type = 'button'; create.id = 'manual-ds-create'; create.className = 'btn btn-sm btn-primary'; create.textContent = 'Create dataset';
    row.append(cancel, create);
    box.append(h, note, name, desc, status, row);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    name.focus();

    cancel.onclick = _closeDialog;
    overlay.addEventListener('mousedown', e => { if (e.target === overlay) _closeDialog(); });
    box.addEventListener('keydown', e => { if (e.key === 'Escape') _closeDialog(); });
    create.onclick = async () => {
      const nm = name.value.trim();
      if (!nm) { status.textContent = 'A dataset name is required.'; status.style.color = '#dc3545'; name.focus(); return; }
      create.disabled = true;
      status.style.color = '#6c757d'; status.textContent = 'Creating…';
      try {
        const r = await fetch(BASE() + '/api/datasets/manual', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({name: nm, description: desc.value.trim(), members}),
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) { status.style.color = '#dc3545'; status.textContent = d.error || ('Error ' + r.status); create.disabled = false; return; }
        const l = d.linked || {};
        _say('Dataset "' + (d.name || nm) + '" created — ' + (l.file || 0) + ' file(s), ' + (l.folder || 0) + ' folder(s) linked', 'success');
        document.dispatchEvent(new CustomEvent('scidk:manualdataset', {detail: d}));
        _closeDialog();
        _clearSelection();
      } catch (e) {
        status.style.color = '#dc3545'; status.textContent = 'Failed: ' + e.message; create.disabled = false;
      }
    };
  }

  // ── DOM wiring ──
  function _wire() {
    document.getElementById('add-to-coll-btn')?.addEventListener('click', addSelectionToCollection);
    document.getElementById('create-dataset-btn')?.addEventListener('click', openManualDatasetDialog);
    document.addEventListener('scidk:collectionbasket', _updateHighlights);
    document.addEventListener('keydown', e => {
      const a = document.activeElement;
      const typing = a && (a.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName));
      if (!typing && e.shiftKey && e.altKey && (e.key === 'C' || e.key === 'c' || e.key === 'ç')) {
        e.preventDefault(); basket().toggle();
      }
    });
    _updateHighlights();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _wire);
  else _wire();

  // Compatibility adapter only: no list of its own.
  global.Collection = {
    items, count, add, remove, clear, entryFromId, payload, _updateHighlights,
    open: () => basket().open(), close: () => basket().close(), toggle: () => basket().toggle(),
  };

})(window);
