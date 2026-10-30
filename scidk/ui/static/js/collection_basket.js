/**
 * collection_basket.js — the one collection control, on every page.
 *
 * A collection is its own level (datasets, files, folders AND context nodes),
 * picked from lists: Files rows, Scans rows and recognized datasets, and
 * Knowledge → Entities rows. Unsaved picks are kept in localStorage so they
 * survive moving between those pages, then saved as one :Collection. A saved
 * collection can be opened again: its stored members are shown read-only,
 * apart from the removable unsaved picks.
 *
 * Mounting: on the Files page `#files-collection-slot` hosts the control inline
 * in the toolbar and the panel drops below it. Everywhere else it is the fixed
 * lower-right pill.
 *
 * Exposes: window.CollectionBasket
 *   .add(items)     — items: [{kind, key, label, size?, files?, p: {...member fields}}]
 *   .remove(key) / .clear() / .items() / .has(key) / .open() / .close() / .toggle()
 *   .fileItemFromId(id, size) — a Files row id as a basket item (path + provider/root/scan)
 *   .openSaved(id) / .opened() — open a saved collection / read what is open
 * Fires `scidk:collectionbasket` on document whenever the picks or the opened
 * collection change.
 *
 * Nothing here deletes anything: Save is one POST that MERGEs the collection.
 */
;(function (global) {
  'use strict';
  const KEY = 'scidk.collection.draft.v1';
  const OPEN_KEY = 'scidk.collection.opened.v1';
  const KINDS = [['dataset', 'Datasets'], ['folder', 'Folders'], ['file', 'Files'], ['context', 'Context']];
  const SHOW_ROWS = 50;
  const BASE = () => (typeof global.SCIDK_BASE !== 'undefined' ? global.SCIDK_BASE : '');

  let _items = [];
  try { _items = JSON.parse(global.localStorage.getItem(KEY) || '[]') || []; } catch (e) { _items = []; }
  // The saved collection currently opened: {id, name, description, total, members|null}.
  let _opened = null;
  try {
    const o = JSON.parse(global.localStorage.getItem(OPEN_KEY) || 'null');
    if (o && o.id) _opened = {id: o.id, name: o.name || '', description: o.description || '', total: o.total || 0, members: null};
  } catch (e) { _opened = null; }
  let _form = {name: '', desc: ''};   // survives re-renders
  let _statusText = '';
  let _plan = '';
  let _planMeta = null;               // {id, name}
  let _view = 'main';                 // 'main' | 'plan'
  let _list = [];

  const fmt = (n) => {
    if (n == null || isNaN(n)) return '';
    const u = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']; let i = 0, v = Number(n);
    while (v >= 1000 && i < u.length - 1) { v /= 1000; i++; }
    return (i === 0 ? v.toFixed(0) : v.toFixed(v < 10 ? 1 : 0)) + ' ' + u[i];
  };
  const num = (n) => Number(n).toLocaleString();
  const $ = (id) => document.getElementById(id);
  function el(tag, text, attrs) {
    const e = document.createElement(tag);
    if (text != null) e.textContent = text;
    if (attrs) Object.assign(e, attrs);
    return e;
  }

  function _notify() {
    document.dispatchEvent(new CustomEvent('scidk:collectionbasket', {detail: {size: _items.length, opened: _opened && _opened.id}}));
  }
  function _persist() {
    try { global.localStorage.setItem(KEY, JSON.stringify(_items)); } catch (e) { /* private mode */ }
    _notify();
    _render();
  }
  function _persistOpened() {
    try {
      if (_opened) global.localStorage.setItem(OPEN_KEY, JSON.stringify({id: _opened.id, name: _opened.name, description: _opened.description, total: _openedTotal()}));
      else global.localStorage.removeItem(OPEN_KEY);
    } catch (e) { /* private mode */ }
    _notify();
    _render();
  }

  function add(items) {
    let added = 0;
    (Array.isArray(items) ? items : [items]).forEach(it => {
      if (!it || !it.key || !it.kind) return;
      if (!_items.some(x => x.key === it.key)) { _items.push(it); added++; }
    });
    if (added) _persist();
    return added;
  }
  function remove(key) { _items = _items.filter(x => x.key !== key); _persist(); }
  function clear() { _items = []; _persist(); }
  function has(key) { return _items.some(x => x.key === key); }
  function items() { return _items.slice(); }
  function opened() { return _opened ? {id: _opened.id, name: _opened.name} : null; }

  // A Files row id (its full path) as a basket entry. Keeps the provider/root/scan
  // identity the server needs to place it on the committed (path, host) node.
  // A folder stays a Folder reference: its descendants are never enumerated here.
  function fileItemFromId(id, size) {
    const s = String(id || '');
    const cut = s.lastIndexOf('/');
    const types = global.itemTypes;
    const name = cut >= 0 ? s.slice(cut + 1) : s;
    const provider_id = global.currentServer || '';
    const root_id = global.currentRoot || '';
    const scan_id = global.mode === 'snapshot' ? (global.activeScanId || '') : '';
    const isDir = ((types && types.get && types.get(s)) || 'file') === 'folder';
    const sz = (isDir || size == null || size === '' || isNaN(size)) ? null : Number(size);
    return {
      key: (isDir ? 'folder|' : 'file|') + provider_id + '|' + root_id + '|' + scan_id + '|' + s,
      kind: isDir ? 'folder' : 'file', label: name, title: s, size: sz,
      p: {path: s, name, provider_id, root_id, scan_id, size: sz},
    };
  }

  // ── labels ───────────────────────────────────────────────────────────
  function _openedTotal() {
    if (!_opened) return 0;
    if (_opened.members) return KINDS.reduce((a, [k]) => a + (_opened.members[k] || []).length, 0);
    return Number(_opened.total) || 0;
  }
  function _pillLabel() {
    const n = _items.length;
    const picks = n + (n === 1 ? ' pick' : ' picks');
    if (_opened) {
      const m = _openedTotal();
      return 'Collection: ' + (_opened.name || 'saved') + ' · ' + m + (m === 1 ? ' member' : ' members') + (n ? ' + ' + picks : '');
    }
    return 'Collection · ' + picks;
  }

  // ── panel ────────────────────────────────────────────────────────────
  function _build() {
    if ($('cb-pill') || !document.body || /\/login\/?$/.test(global.location.pathname)) return;
    const style = el('style', `
#cb-pill{position:fixed;right:16px;bottom:16px;z-index:1200;padding:6px 12px;border-radius:16px;border:1px solid #b6d4fe;background:#e7f1ff;color:#0a58ca;font:600 12px system-ui,sans-serif;cursor:pointer;max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#cb-panel{position:fixed;right:16px;bottom:56px;width:420px;max-height:75vh;overflow:auto;z-index:1200;background:#fff;border:1px solid #adb5bd;border-radius:8px;box-shadow:0 6px 24px rgba(0,0,0,.2);font:13px system-ui,sans-serif;padding:12px;display:none}
#files-collection-slot.cb-docked{position:relative;display:inline-flex;align-items:center}
#files-collection-slot.cb-docked #cb-pill{position:static;height:28px;padding:0 12px;max-width:340px}
#files-collection-slot.cb-docked #cb-panel{position:fixed;right:auto;bottom:auto;width:440px;max-width:calc(100vw - 16px)}
#cb-panel.open{display:block}
#cb-panel h3{margin:0 0 6px;font-size:14px;display:flex;align-items:center;gap:6px} #cb-panel h3 span{flex:1}
#cb-panel h4{margin:10px 0 2px;font-size:12px}
#cb-panel .cb-row{display:flex;gap:6px;align-items:center;padding:1px 0;font-size:12px}
#cb-panel .cb-row span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#cb-panel input[type=text],#cb-panel textarea{width:100%;box-sizing:border-box;margin:2px 0}
#cb-panel pre{white-space:pre-wrap;max-height:55vh;overflow:auto;background:#f8f9fa;padding:6px;font-size:11px}
#cb-panel .cb-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
#cb-panel .cb-meta{color:#555;font-size:11px}
#cb-panel .cb-section{border-top:1px solid #dee2e6;margin-top:10px;padding-top:6px}
#cb-panel .cb-stored{background:#f4f8f4;border:1px solid #cfe3cf;border-radius:6px;padding:6px 8px;margin-top:8px}
#cb-panel .cb-picks{background:#fffaf0;border:1px solid #f1dfb0;border-radius:6px;padding:6px 8px;margin-top:8px}
#cb-panel .cb-card{border:1px solid #dee2e6;border-radius:6px;padding:6px 8px;margin-top:6px}
#cb-panel .cb-card.is-open{border-color:#0a58ca;background:#f1f6ff}
#cb-panel .cb-card .cb-name{font-weight:600;font-size:12px}
.coll-add-cb{margin-right:6px}`);
    document.head.appendChild(style);
    const pill = el('button', '', {id: 'cb-pill', type: 'button', title: 'Collection panel'});
    pill.setAttribute('data-testid', 'collection-basket-pill');
    pill.onclick = toggle;
    const panel = el('div', null, {id: 'cb-panel'});
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', 'Collection');
    panel.setAttribute('data-testid', 'collection-basket-panel');
    const slot = $('files-collection-slot');
    if (slot) { slot.classList.add('cb-docked'); slot.append(pill, panel); }
    else document.body.append(pill, panel);
    _render();
  }

  function isOpen() { const p = $('cb-panel'); return !!(p && p.classList.contains('open')); }

  // Docked on Files: anchor the panel just below the toolbar control, but position it
  // against the viewport (fixed) so the Files container's overflow can't clip it.
  function _place() {
    const slot = $('files-collection-slot'), p = $('cb-panel');
    if (!slot || !p || !slot.classList.contains('cb-docked')) return;
    const r = slot.getBoundingClientRect();
    const width = Math.min(440, global.innerWidth - 16);
    const left = Math.max(8, Math.min(r.left, global.innerWidth - width - 8));
    const top = r.bottom + 6;
    p.style.left = left + 'px';
    p.style.top = top + 'px';
    p.style.maxHeight = Math.max(200, global.innerHeight - top - 12) + 'px';
  }
  global.addEventListener('resize', () => { if (isOpen()) _place(); });

  function open() {
    _build();
    const p = $('cb-panel'); if (!p) return;
    p.classList.add('open');
    _place();
    _loadSaved();
    if (_opened && !_opened.members) openSaved(_opened.id, true);
  }
  function close() { const p = $('cb-panel'); if (p) p.classList.remove('open'); }
  function toggle() { isOpen() ? close() : open(); }

  function _status(text) { _statusText = text || ''; const s = $('cb-status'); if (s) s.textContent = _statusText; }

  function _kindRow(x, removable) {
    const row = el('div', null, {className: 'cb-row'});
    row.append(el('span', (x.tag ? x.tag + ' · ' : '') + x.label, {title: x.title || x.label}),
      el('span', x.size ? fmt(x.size) : '', {style: 'flex:0 0 auto;color:#555'}));
    if (removable) {
      const rm = el('button', '×', {type: 'button', title: 'Remove from unsaved picks'});
      rm.setAttribute('aria-label', 'Remove ' + x.label + ' from picks');
      rm.onclick = () => remove(x.key); row.append(rm);
    }
    return row;
  }

  function _renderPicks(into) {
    const box = el('div', null, {id: 'cb-summary', className: 'cb-picks'});
    box.setAttribute('data-testid', 'collection-picks');
    box.append(el('div', 'Unsaved picks · ' + _items.length + ' (local, removable)', {style: 'font-weight:600;font-size:12px'}));
    KINDS.forEach(([kind, title]) => {
      const rows = _items.filter(x => x.kind === kind);
      if (!rows.length) return;
      const bytes = rows.reduce((a, x) => a + (Number(x.size) || 0), 0);
      const files = rows.reduce((a, x) => a + (Number(x.files) || 0), 0);
      let detail = '';
      if (kind === 'context') {
        const byLabel = {};
        rows.forEach(x => { const l = (x.p && x.p.label) || '?'; byLabel[l] = (byLabel[l] || 0) + 1; });
        detail = ' (' + Object.keys(byLabel).sort().map(l => l + ' ' + byLabel[l]).join(', ') + ')';
      }
      const h = el('h4', title + ' · ' + rows.length + detail + (bytes ? ' · ' + fmt(bytes) : '') + (files ? ' · ' + num(files) + ' files' : ''));
      h.setAttribute('data-kind', kind); h.setAttribute('data-count', String(rows.length));
      box.append(h);
      rows.forEach(x => box.append(_kindRow(x, true)));
    });
    if (!_items.length) box.append(el('div', 'Nothing picked yet. Pick Files, Scans or Entities rows, then add them here.', {className: 'cb-meta'}));
    into.append(box);
  }

  function _storedLabel(kind, m) {
    if (kind === 'dataset') {
      const bits = [m.profile, m.file_count != null ? num(m.file_count) + ' files' : '', m.bytes ? fmt(m.bytes) : ''].filter(Boolean);
      return (m.name || m.root_path || '(dataset)') + (bits.length ? ' · ' + bits.join(' · ') : '');
    }
    if (kind === 'folder') return m.name || m.path || '(folder)';
    if (kind === 'file') return (m.filename || m.path || '(file)') + (m.size_bytes ? ' · ' + fmt(m.size_bytes) : '');
    return (m.label || '?') + (m.display ? ' · ' + m.display : '');
  }

  function _renderStored(into) {
    const box = el('div', null, {id: 'cb-stored', className: 'cb-stored'});
    box.setAttribute('data-testid', 'collection-stored');
    box.append(el('div', 'Stored in “' + (_opened.name || 'collection') + '” · ' + _openedTotal() + ' (read-only)', {style: 'font-weight:600;font-size:12px'}));
    if (_opened.description) box.append(el('div', _opened.description, {className: 'cb-meta'}));
    if (!_opened.members) { box.append(el('div', 'Loading stored members…', {className: 'cb-meta'})); into.append(box); return; }
    let any = false;
    KINDS.forEach(([kind, title]) => {
      const rows = _opened.members[kind] || [];
      if (!rows.length) return;
      any = true;
      const h = el('h4', title + ' · ' + rows.length);
      h.setAttribute('data-kind', kind); h.setAttribute('data-count', String(rows.length));
      box.append(h);
      rows.slice(0, SHOW_ROWS).forEach(m => {
        const row = el('div', null, {className: 'cb-row'});
        row.append(el('span', _storedLabel(kind, m), {title: m.path || m.root_path || m.id || ''}));
        box.append(row);
      });
      if (rows.length > SHOW_ROWS) box.append(el('div', '… and ' + (rows.length - SHOW_ROWS) + ' more', {className: 'cb-meta'}));
    });
    if (!any) box.append(el('div', 'This collection has no stored members.', {className: 'cb-meta'}));
    into.append(box);
  }

  function _renderSavedList(into) {
    into.append(el('h4', 'Saved collections'));
    const list = el('div', null, {id: 'cb-saved-list'});
    if (!_list.length) list.append(el('div', 'No saved collections.', {className: 'cb-meta'}));
    _list.forEach(c => {
      const card = el('div', null, {className: 'cb-card' + (_opened && _opened.id === c.id ? ' is-open' : '')});
      card.setAttribute('data-collection-id', c.id);
      card.append(el('div', c.name || '(unnamed)', {className: 'cb-name'}));
      if (c.description) card.append(el('div', c.description, {className: 'cb-meta'}));
      const counts = KINDS.map(([k, t]) => [t, c[k === 'dataset' ? 'datasets' : k === 'folder' ? 'folders' : k === 'file' ? 'files' : 'context_members']])
        .filter(([, n]) => n).map(([t, n]) => t.toLowerCase() + ' ' + n);
      card.append(el('div', (c.members || 0) + ' member' + (c.members === 1 ? '' : 's') + (counts.length ? ' · ' + counts.join(', ') : ''), {className: 'cb-meta'}));
      const act = el('div', null, {className: 'cb-actions'});
      const o = el('button', 'Open', {type: 'button'}); o.setAttribute('data-action', 'open-collection'); o.onclick = () => openSaved(c.id);
      const p = el('button', 'Draft sharing plan', {type: 'button'}); p.setAttribute('data-action', 'draft-plan'); p.onclick = () => _draftPlan(c.id, c.name);
      act.append(o, p); card.append(act); list.append(card);
    });
    into.append(list);
  }

  function _renderMain(panel) {
    const head = el('h3');
    head.append(el('span', 'Collection'));
    const x = el('button', '×', {type: 'button', id: 'cb-close', title: 'Close panel'}); x.setAttribute('aria-label', 'Close collection panel'); x.onclick = close;
    head.append(x); panel.append(head);
    panel.append(el('div', 'Pick datasets, folders, files and context records from Files, Scans and Entities, then save them as one collection.', {className: 'cb-meta'}));

    if (_opened) {
      const bar = el('div', null, {className: 'cb-actions'});
      const cl = el('button', 'Close collection', {id: 'cb-detach', type: 'button', title: 'Stop viewing this saved collection (nothing is deleted)'});
      cl.onclick = () => { _opened = null; _persistOpened(); };
      bar.append(cl); panel.append(bar);
      _renderStored(panel);
    }
    _renderPicks(panel);

    const sec = el('div', null, {className: 'cb-section'});
    const actions = el('div', null, {className: 'cb-actions'});
    if (_opened) {
      const addTo = el('button', 'Add ' + _items.length + ' pick' + (_items.length === 1 ? '' : 's') + ' to “' + (_opened.name || 'collection') + '”', {id: 'cb-add-to-opened', type: 'button'});
      addTo.disabled = !_items.length; addTo.onclick = _addToOpened;
      actions.append(addTo);
      sec.append(el('div', 'Or save the picks as a new collection:', {className: 'cb-meta'}));
    }
    const name = el('input', null, {id: 'cb-name', type: 'text', placeholder: 'Collection name', maxLength: 200, value: _form.name});
    name.setAttribute('aria-label', 'Collection name'); name.oninput = () => { _form.name = name.value; };
    const desc = el('textarea', null, {id: 'cb-desc', rows: 2, placeholder: 'Description (purpose: sharing, analysis…)', value: _form.desc});
    desc.setAttribute('aria-label', 'Collection description'); desc.oninput = () => { _form.desc = desc.value; };
    const save = el('button', 'Save collection', {id: 'cb-save', type: 'button'}); save.onclick = _save;
    const clr = el('button', 'Clear picks', {id: 'cb-clear', type: 'button'}); clr.onclick = clear;
    actions.append(save, clr);
    sec.append(name, desc, actions, el('div', _statusText, {id: 'cb-status', className: 'cb-meta', role: 'status'}));
    panel.append(sec);
    _renderSavedList(panel);
  }

  function _renderPlan(panel) {
    const head = el('h3');
    head.append(el('span', 'Sharing plan draft' + (_planMeta && _planMeta.name ? ' · ' + _planMeta.name : '')));
    panel.append(head);
    panel.append(el('div', 'Investigator review required; not a compliance determination. Covers this collection only.', {className: 'cb-meta'}));
    const actions = el('div', null, {className: 'cb-actions'});
    const copy = el('button', 'Copy draft', {id: 'cb-plan-copy', type: 'button'}); copy.onclick = _copyPlan;
    const closeBtn = el('button', 'Close', {id: 'cb-plan-close', type: 'button'}); closeBtn.onclick = _closePlan;
    actions.append(copy, closeBtn); panel.append(actions);
    panel.append(el('div', _statusText, {id: 'cb-status', className: 'cb-meta', role: 'status'}));
    panel.append(el('pre', _plan, {id: 'cb-plan-out'}));
  }

  function _render() {
    const pill = $('cb-pill'), panel = $('cb-panel');
    if (!pill || !panel) return;
    pill.textContent = _pillLabel();
    pill.title = 'Collection panel';
    panel.replaceChildren();
    if (_view === 'plan') _renderPlan(panel); else _renderMain(panel);
    if (isOpen()) _place();
  }

  async function _json(url, opts) {
    const r = await fetch(BASE() + url, opts);
    let d = {}; try { d = await r.json(); } catch (e) { /* non-JSON */ }
    return {ok: r.ok, status: r.status, d};
  }

  async function _loadSaved() {
    try {
      const {d} = await _json('/api/collections');
      _list = d.collections || [];
    } catch (e) { _list = []; }
    if (_view === 'main') _render();
  }

  // Open a saved collection: fetch its stored members and show them (read-only).
  async function openSaved(id, quiet) {
    if (!id) return;
    if (!quiet) _status('Opening…');
    let r;
    try { r = await _json('/api/collections/' + encodeURIComponent(id)); } catch (e) { r = {ok: false, status: 0, d: {error: String(e)}}; }
    if (!r.ok) {
      _status(r.d.error || ('Error ' + r.status));
      if (r.status === 404) { _opened = null; _persistOpened(); }
      else _render();
      return;
    }
    const c = r.d.collection || {};
    _opened = {id: c.id || id, name: c.name || '', description: c.description || '', total: 0, members: r.d.members || {}};
    _opened.total = _openedTotal();
    _status(quiet ? '' : 'Opened “' + _opened.name + '”: ' + _opened.total + ' stored member(s).');
    _view = 'main';
    _persistOpened();
    if (!isOpen()) open();
  }

  function _members() {
    return _items.map(x => Object.assign({kind: x.kind}, x.p || {}));
  }

  async function _post(body) {
    const post = () => _json('/api/collections', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    return post();
  }

  function _summaryOf(r, name) {
    const l = r.d.linked || {};
    return 'Saved "' + name + '": ' + (l.dataset || 0) + ' dataset(s), ' + (l.folder || 0) + ' folder(s), ' + (l.file || 0) +
      ' file(s), ' + (l.context || 0) + ' context record(s).' + (r.d.problems && r.d.problems.length ? ' Skipped: ' + r.d.problems.length : '');
  }

  async function _save() {
    const name = (_form.name || '').trim();
    if (!name) { _status('Give the collection a name.'); return; }
    if (!_items.length) { _status('Pick something first.'); return; }
    _status('Saving…');
    const body = {name, description: _form.desc || '', members: _members()};
    let r = await _post(body);
    if (r.status === 409 && r.d.exists) {
      if (!confirm('A collection named "' + name + '" already exists with ' + r.d.members + ' member(s). Add these to it?')) { _status('Not saved.'); return; }
      body.add_to_existing = true; r = await _post(body);
    }
    if (!r.ok) { _status(r.d.error || ('Error ' + r.status)); return; }
    const msg = _summaryOf(r, name);
    // The picks are stored now: they leave the unsaved list and show as stored members.
    _items = []; _form = {name: '', desc: ''};
    try { global.localStorage.setItem(KEY, JSON.stringify(_items)); } catch (e) { /* private mode */ }
    await _loadSaved();
    await openSaved(r.d.collection_id, true);
    _status(msg);
  }

  async function _addToOpened() {
    if (!_opened || !_items.length) return;
    if (!confirm('Add ' + _items.length + ' pick(s) to "' + _opened.name + '"? Members are only added; nothing is removed.')) { _status('Not added.'); return; }
    _status('Adding…');
    const r = await _post({name: _opened.name, add_to_existing: true, members: _members()});
    if (!r.ok) { _status(r.d.error || ('Error ' + r.status)); return; }
    const msg = _summaryOf(r, _opened.name);
    _items = [];
    try { global.localStorage.setItem(KEY, JSON.stringify(_items)); } catch (e) { /* private mode */ }
    await _loadSaved();
    await openSaved(r.d.collection_id, true);
    _status(msg);
  }

  async function _draftPlan(id, name) {
    if (!id) { _status('Save or open a collection first.'); return; }
    _status('Drafting the sharing plan…');
    const r = await _json('/api/plugins/nih_dms/collections/' + encodeURIComponent(id) + '/draft_plan',
      {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fields: {}})});
    if (!r.ok) { _status(r.d.error || ('Error ' + r.status)); return; }
    _plan = r.d.markdown || '';
    _planMeta = {id, name: name || (r.d.summary && r.d.summary.name) || ''};
    _view = 'plan';
    _status('Draft ready. Investigator review required; not a compliance determination.');
    _render();
  }

  function _closePlan() { _view = 'main'; _status(''); _render(); }

  async function _copyPlan() {
    let ok = false;
    try { await global.navigator.clipboard.writeText(_plan); ok = true; } catch (e) { /* fall through */ }
    if (!ok) {
      try {
        const t = el('textarea', _plan, {style: 'position:fixed;left:-9999px'});
        document.body.append(t); t.select(); ok = document.execCommand('copy'); t.remove();
      } catch (e) { ok = false; }
    }
    _status(ok ? 'Draft copied.' : 'Copy failed — select the text and copy it by hand.');
  }

  // Row checkbox helper for list pages: a checkbox bound to one item factory.
  function checkbox(makeItem, label) {
    const cb = el('input', null, {type: 'checkbox', className: 'coll-add-cb'});
    cb.setAttribute('aria-label', label || 'Select for collection');
    cb._makeItem = makeItem;
    return cb;
  }
  // Add every checked box under `root` (and uncheck it). Returns how many were new.
  function addChecked(root) {
    const boxes = Array.from((root || document).querySelectorAll('input.coll-add-cb:checked'));
    const made = boxes.map(b => b._makeItem && b._makeItem()).filter(Boolean);
    const added = add(made);
    boxes.forEach(b => { b.checked = false; });
    open();
    return added;
  }

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && _view === 'plan' && isOpen()) _closePlan();
  });

  global.CollectionBasket = {add, remove, clear, items, has, open, close, toggle, checkbox, addChecked, fmt,
                             fileItemFromId, openSaved, opened};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _build); else _build();
})(window);
