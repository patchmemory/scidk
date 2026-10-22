/**
 * collection.js — Collection object for SciDK Files page
 *
 * The Collection is a persistent cross-folder accumulation of files
 * that survives navigation. It is the source of truth for Share,
 * Annotate (Collect tab), and Save as Dataset.
 *
 * Exposes: window.Collection
 *   .add(files)          — add [{name, path, provider_id, root_id, scan_id, type}]
 *   .entryFromId(id)     — a selection id (full path) as a collection entry
 *   .payload(f)          — an entry as the Dataset / sweep routes expect it
 *   .remove(name)        — remove by filename
 *   .clear()             — discard all (with confirm)
 *   .items()             — returns current array (readonly copy)
 *   .count()             — number of files
 *   .open()              — open the floating panel
 *   .close()             — close the floating panel
 *   .toggle()            — toggle panel
 *   .sweep()             — check Dataset completeness via API
 *   .saveAsDataset()     — POST /api/datasets/collections
 *   .exportFileList()    — download .txt of paths
 *
 * Keyboard:
 *   Shift+Alt+C  — toggle panel (global)
 *   Ctrl+D       — save as Dataset (when panel is open)
 */
;(function(global) {
  'use strict';

  const BASE = () => (typeof window.SCIDK_BASE !== 'undefined') ? window.SCIDK_BASE : '';

  // ── State ──
  let _items = [];
  let _panelOpen = false;
  let _saveMenuOpen = false;
  let _toastTimer = null;

  // ── Toast ──
  function toast(msg, ms=2500) {
    const el = document.getElementById('coll-toast');
    if (!el) return;
    el.textContent = msg; el.style.display = 'block';
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => el.style.display = 'none', ms);
  }

  // ── Core collection operations ──
  function add(files) {
    let added = 0;
    (Array.isArray(files) ? files : [files]).forEach(f => {
      if (!_items.find(x => x.name === f.name && x.path === f.path)) {
        _items.push(f); added++;
      }
    });
    if (added) { _updatePill(); _updateHighlights(); if (_panelOpen) _render(); }
    return added;
  }

  function remove(name) {
    _items = _items.filter(f => f.name !== name);
    _updatePill(); _updateHighlights(); if (_panelOpen) _render();
  }

  function clear(skipConfirm=false) {
    if (!skipConfirm && _items.length && !confirm('Discard the entire collection? This cannot be undone.')) return;
    _items = [];
    _updatePill(); close(); _updateHighlights();
    toast('Collection discarded');
  }

  function items() { return [..._items]; }
  function count() { return _items.length; }

  // ── Panel open/close ──
  function open() {
    const panel = document.getElementById('coll-panel');
    if (!panel) return;
    panel.classList.add('open'); _panelOpen = true;
    _render(); sweep();
  }
  function close() {
    const panel = document.getElementById('coll-panel');
    if (!panel) return;
    panel.classList.remove('open'); _panelOpen = false;
    _closeSaveMenu();
  }
  function toggle() { _panelOpen ? close() : open(); }

  // ── Pill ──
  // Every change to _items passes through here, so it is also where the
  // change is announced (the Annotate drawer re-renders its scope on it).
  function _updatePill() {
    document.dispatchEvent(new CustomEvent('scidk:collectionchange', { detail: { size: _items.length } }));
    const pill = document.getElementById('coll-pill');
    const count_el = document.getElementById('coll-count');
    const meta = document.getElementById('cp-meta');
    const n = _items.length;
    const label = n + ' file' + (n !== 1 ? 's' : '');
    if (count_el) count_el.textContent = label;
    if (meta) meta.textContent = label;
    if (pill) pill.classList.toggle('visible', n > 0);
  }

  // ── Row highlights in file table ──
  function _updateHighlights() {
    const names = new Set(_items.map(f => f.name));
    document.querySelectorAll('#file-list tr[data-name]').forEach(tr => {
      tr.classList.toggle('in-coll', names.has(tr.dataset.name));
    });
  }

  // ── Render panel ──
  function _render() {
    const list = document.getElementById('coll-item-list');
    const empty = document.getElementById('coll-empty');
    const group = document.getElementById('coll-group');
    const groupPath = document.getElementById('coll-group-path');
    const groupCount = document.getElementById('coll-group-count');
    if (!list) return;
    if (!_items.length) {
      if (group) group.style.display = 'none';
      if (empty) empty.style.display = 'block'; return;
    }
    if (group) group.style.display = '';
    if (empty) empty.style.display = 'none';
    const firstPath = _items[0]?.path || '';
    if (groupPath) groupPath.textContent = firstPath;
    if (groupCount) groupCount.textContent = _items.length + ' files';
    list.innerHTML = _items.map((f, i) =>
      `<div class="coll-item">
        <i class="ti ti-file" aria-hidden="true" style="font-size:13px;color:#6c757d;flex-shrink:0;"></i>
        <div class="ci-info"><div class="ci-name">${_esc(f.name)}</div><div class="ci-path">${_esc(f.path)}</div></div>
        <button class="ci-rm" data-coll-idx="${i}" aria-label="Remove ${_esc(f.name)}">×</button>
      </div>`
    ).join('');
    list.querySelectorAll('.ci-rm[data-coll-idx]').forEach(btn => {
      btn.addEventListener('click', () => {
        _items.splice(+btn.dataset.collIdx, 1);
        _updatePill(); _render(); _updateHighlights();
      });
    });
  }

  // ── Sweep — Dataset completeness ──
  async function sweep() {
    const el = document.getElementById('coll-sweep');
    if (!el || !_items.length) { if (el) el.style.display='none'; return; }
    try {
      const r = await fetch(BASE() + '/api/collections/sweep', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // (path, host) pairs, where path is the file's own full path — not the
        // folder it sits in, and not its basename. That is the composite key
        // File nodes carry, so it is the only form the sweep can match on the
        // index; a basename is ambiguous across the graph and unindexed.
        body: JSON.stringify({ files: _items.map(payload) })
      });
      if (!r.ok) { el.style.display='none'; return; }
      const d = await r.json();
      if (!d.gaps?.length) { el.style.display='none'; return; }
      const gap = d.gaps[0];
      const lbl = document.getElementById('sweep-label');
      const det = document.getElementById('sweep-detail');
      if (lbl) lbl.textContent = `Dataset "${gap.dataset_name}" is incomplete`;
      if (det) det.innerHTML = `You have ${gap.present} of ${gap.total} files.<br>Missing: ${gap.missing.map(m=>`<code style="font-size:10px;">${_esc(m)}</code>`).join(', ')}`;
      el.style.display = 'flex';
      el._gap = gap;
    } catch { el.style.display='none'; }
  }

  // ── Save as Dataset ──
  async function saveAsDataset() {
    if (!_items.length) { toast('Collection is empty'); return; }
    const name = prompt('Dataset name:', '');
    if (!name?.trim()) { toast('Name required to create a Dataset'); return; }
    try {
      // Same entries the sweep sends; the server derives the host.
      const body = { name: name.trim(), files: _items.map(payload) };
      const post = () => fetch(BASE() + '/api/datasets/collections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      let r = await post();
      let d = await r.json().catch(() => ({}));
      // The name is taken: never merge without asking.
      if (r.status === 409 && d.exists) {
        if (!confirm(`A Dataset named "${body.name}" already exists with ${d.members} file(s). Add these files to it?`)) {
          toast('Not saved'); return;
        }
        body.add_to_existing = true;
        r = await post();
        d = await r.json().catch(() => ({}));
      }
      if (r.ok) {
        toast(`Dataset "${body.name}" ${d.created === false ? 'updated' : 'created'} — ${d.files_linked || 0} files linked`
          + (d.problems && d.problems.length ? ` · ${d.problems.length} skipped` : ''));
        close();
      } else { toast('Failed: ' + (d.error || r.status)); }
    } catch (e) { toast('Error: ' + e.message); }
  }

  // ── Export file list ──
  function exportFileList() {
    const lines = _items.map(_fullPath).join('\n');
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(new Blob([lines], {type:'text/plain'})),
      download: 'scidk-collection.txt'
    });
    a.click(); URL.revokeObjectURL(a.href);
    toast('File list downloaded as scidk-collection.txt');
  }

  // ── Save-as menu ──
  function _openSaveMenu() {
    const menu = document.getElementById('saveas-menu');
    const btn  = document.getElementById('saveas-btn');
    if (!menu || !btn) return;
    // The panel's transform makes position:fixed relative to the panel, and
    // its overflow clips; opened upward from the top of the page the menu
    // landed off-screen. Moved to <body> it positions against the viewport.
    if (menu.parentElement !== document.body) document.body.appendChild(menu);
    const rect = btn.getBoundingClientRect();
    menu.classList.add('open'); _saveMenuOpen = true;
    const h = menu.offsetHeight, w = menu.offsetWidth;
    const below = rect.bottom + 5;
    menu.style.bottom = 'auto';
    menu.style.top  = (below + h <= window.innerHeight ? below : Math.max(5, rect.top - h - 5)) + 'px';
    menu.style.left = Math.max(5, Math.min(rect.left, window.innerWidth - w - 5)) + 'px';
  }
  function _closeSaveMenu() {
    document.getElementById('saveas-menu')?.classList.remove('open');
    _saveMenuOpen = false;
  }

  // ── Utility ──
  // A collection item stores the folder in `path` and the basename in `name`.
  // Anything addressing a File node needs the two joined.
  function _fullPath(f) {
    const dir = (f.path || '').replace(/\/+$/, '');
    if (!dir) return f.name || '';
    return dir.endsWith('/' + f.name) || dir === f.name ? dir : dir + '/' + f.name;
  }

  // Where an entry lives. The server turns provider_id + root_id (or, in Index
  // view, the scan) into the host label commit wrote, so a collected file lands
  // on the committed (path, host) node. Sending the provider id as the host
  // matched nothing and created stub nodes beside the real files.
  function entryFromId(id) {
    const s = String(id || '');
    const cut = s.lastIndexOf('/');
    const types = global.itemTypes;
    return {
      name: cut >= 0 ? s.slice(cut + 1) : s,
      path: cut >= 0 ? s.slice(0, cut) : (global.currentPath || ''),
      provider_id: global.currentServer || '',
      root_id: global.currentRoot || '',
      scan_id: global.mode === 'snapshot' ? (global.activeScanId || '') : '',
      type: (types && types.get(s)) || 'file',
    };
  }

  function payload(f) {
    return {
      name: f.name, path: _fullPath(f), type: f.type || 'file',
      provider_id: f.provider_id || '', root_id: f.root_id || '', scan_id: f.scan_id || '',
    };
  }

  function _esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── DOM wiring (called after DOMContentLoaded) ──
  function _wire() {
    // Pill
    document.getElementById('coll-pill')?.addEventListener('click', e => {
      if (e.target.closest('#coll-pill-discard')) return;
      toggle();
    });
    document.getElementById('coll-pill-discard')?.addEventListener('click', e => {
      e.stopPropagation(); clear();
    });
    document.getElementById('cp-close')?.addEventListener('click', close);
    document.getElementById('coll-discard-btn')?.addEventListener('click', () => clear());

    // Save-as
    document.getElementById('saveas-btn')?.addEventListener('click', e => {
      e.stopPropagation(); _saveMenuOpen ? _closeSaveMenu() : _openSaveMenu();
    });
    document.addEventListener('click', e => {
      // The menu lives on <body> (see _openSaveMenu), outside saveas-wrap.
      if (document.getElementById('saveas-menu')?.contains(e.target)) {
        if (e.target.closest('.saveas-item')) _closeSaveMenu();
        return;
      }
      if (!document.getElementById('saveas-wrap')?.contains(e.target)) _closeSaveMenu();
    });
    document.getElementById('save-dataset-btn')?.addEventListener('click', saveAsDataset);
    document.getElementById('save-filelist-btn')?.addEventListener('click', () => { _closeSaveMenu(); exportFileList(); });
    document.getElementById('save-rocrate-btn')?.addEventListener('click', () => {
      _closeSaveMenu(); close();
      if (typeof SharePanel !== 'undefined') { SharePanel.open(); SharePanel.setTab('rocrate'); }
    });
    document.getElementById('save-copy-btn')?.addEventListener('click', () => {
      _closeSaveMenu(); toast('Copy to folder — not yet implemented');
    });

    // Share
    document.getElementById('coll-share-btn')?.addEventListener('click', () => {
      close();
      if (typeof SharePanel !== 'undefined') SharePanel.open();
    });

    // Sweep
    document.getElementById('sweep-inc-btn')?.addEventListener('click', () => {
      const el = document.getElementById('coll-sweep');
      const gap = el?._gap;
      if (!gap) return;
      let added = 0;
      (gap.missing || []).forEach(name => {
        if (!_items.find(f => f.name === name)) {
          _items.push({ name, path: gap.path || '', provider: '' }); added++;
        }
      });
      el.style.display = 'none';
      _updatePill(); _render(); _updateHighlights();
      if (added) toast(added + ' missing file' + (added !== 1 ? 's' : '') + ' added');
    });
    document.getElementById('sweep-ign-btn')?.addEventListener('click', () => {
      document.getElementById('coll-sweep').style.display = 'none';
    });

    // Add to collection from selection bar
    document.getElementById('add-to-coll-btn')?.addEventListener('click', () => {
      if (typeof selItems === 'undefined' || !selItems.size) { toast('No files selected'); return; }
      const files = [...selItems].map(entryFromId);
      const added = add(files);
      if (added) {
        selItems.clear();
        document.querySelectorAll('#file-list .row-cb').forEach(cb => cb.checked = false);
        if (typeof updateSelUI === 'function') updateSelUI();
        toast(added + ' file' + (added !== 1 ? 's' : '') + ' added to collection');
      } else { toast('All selected files already in collection'); }
    });

    // Keyboard
    document.addEventListener('keydown', e => {
      // Shift+Alt+C — toggle panel
      const a = document.activeElement;
      const typing = a && (a.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName));
      if (!typing && e.shiftKey && e.altKey && (e.key === 'C' || e.key === 'c' || e.key === 'ç')) {
        e.preventDefault(); toggle(); return;
      }
      // Ctrl+D — save as Dataset (only when panel open)
      if ((e.ctrlKey || e.metaKey) && e.key === 'd' && _panelOpen) {
        e.preventDefault(); saveAsDataset(); return;
      }
      // Escape stack
      if (e.key === 'Escape') {
        if (_saveMenuOpen) { _closeSaveMenu(); return; }
        if (_panelOpen)    { close(); return; }
      }
    });

    _updatePill();
    _updateHighlights();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _wire);
  else _wire();

  global.Collection = { add, remove, clear, items, count, open, close, toggle, sweep, saveAsDataset, exportFileList, entryFromId, payload };

})(window);
