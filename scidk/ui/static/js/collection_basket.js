/**
 * collection_basket.js — the one collection panel, on every page.
 *
 * A collection is its own level (datasets, files, folders AND context nodes),
 * picked from lists: Files rows, Scans rows and recognized datasets, and
 * Knowledge → Entities rows. Picks are kept in localStorage so they survive
 * moving between those pages, then saved as one :Collection.
 *
 * Exposes: window.CollectionBasket
 *   .add(items)     — items: [{kind, key, label, size?, files?, p: {...member fields}}]
 *   .remove(key) / .clear() / .items() / .has(key) / .open() / .close()
 * Fires `scidk:collectionbasket` on document whenever the picks change.
 *
 * Nothing here deletes anything: Save is one POST that MERGEs the collection.
 */
;(function (global) {
  'use strict';
  const KEY = 'scidk.collection.draft.v1';
  const KINDS = [['dataset', 'Datasets'], ['folder', 'Folders'], ['file', 'Files'], ['context', 'Context']];
  const BASE = () => (typeof global.SCIDK_BASE !== 'undefined' ? global.SCIDK_BASE : '');

  let _items = [];
  try { _items = JSON.parse(global.localStorage.getItem(KEY) || '[]') || []; } catch (e) { _items = []; }
  let _saved = null;       // {id, name} of the collection just saved or picked
  let _plan = '';

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

  function _persist() {
    try { global.localStorage.setItem(KEY, JSON.stringify(_items)); } catch (e) { /* private mode */ }
    document.dispatchEvent(new CustomEvent('scidk:collectionbasket', {detail: {size: _items.length}}));
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

  // ── panel ────────────────────────────────────────────────────────────
  function _build() {
    if ($('cb-pill') || /\/login\/?$/.test(global.location.pathname)) return;
    const style = el('style', `
#cb-pill{position:fixed;right:16px;bottom:16px;z-index:1200;padding:6px 12px;border-radius:16px;border:1px solid #b6d4fe;background:#e7f1ff;color:#0a58ca;font:600 12px system-ui,sans-serif;cursor:pointer}
#cb-panel{position:fixed;right:16px;bottom:56px;width:420px;max-height:75vh;overflow:auto;z-index:1200;background:#fff;border:1px solid #adb5bd;border-radius:8px;box-shadow:0 6px 24px rgba(0,0,0,.2);font:13px system-ui,sans-serif;padding:12px;display:none}
#cb-panel.open{display:block}
#cb-panel h3{margin:0 0 6px;font-size:14px} #cb-panel h4{margin:10px 0 2px;font-size:12px}
#cb-panel .cb-row{display:flex;gap:6px;align-items:center;padding:1px 0;font-size:12px}
#cb-panel .cb-row span{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#cb-panel input[type=text],#cb-panel textarea,#cb-panel select{width:100%;box-sizing:border-box;margin:2px 0}
#cb-panel pre{white-space:pre-wrap;max-height:260px;overflow:auto;background:#f8f9fa;padding:6px;font-size:11px}
#cb-panel .cb-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
#cb-panel .cb-meta{color:#555;font-size:11px}
.coll-add-cb{margin-right:6px}`);
    document.head.appendChild(style);
    const pill = el('button', '', {id: 'cb-pill', type: 'button', title: 'Collection panel'});
    pill.setAttribute('data-testid', 'collection-basket-pill');
    pill.onclick = () => ($('cb-panel').classList.contains('open') ? close() : open());
    const panel = el('div', null, {id: 'cb-panel'});
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-label', 'Collection');
    panel.setAttribute('data-testid', 'collection-basket-panel');
    document.body.append(pill, panel);
    _render();
  }

  function open() { _build(); if ($('cb-panel')) { $('cb-panel').classList.add('open'); _loadSaved(); } }
  function close() { const p = $('cb-panel'); if (p) p.classList.remove('open'); }

  function _render() {
    const pill = $('cb-pill'), panel = $('cb-panel');
    if (!pill || !panel) return;
    pill.textContent = 'Collection (' + _items.length + ')';
    panel.replaceChildren();
    panel.append(el('h3', 'Collection'));
    panel.append(el('div', 'Pick datasets, folders, files and context records from Files, Scans and Entities, then save them as one collection.', {className: 'cb-meta'}));

    const summary = el('div', null, {id: 'cb-summary'});
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
      summary.append(h);
      rows.forEach(x => {
        const row = el('div', null, {className: 'cb-row'});
        row.append(el('span', (x.tag ? x.tag + ' · ' : '') + x.label, {title: x.title || x.label}),
          el('span', x.size ? fmt(x.size) : '', {style: 'flex:0 0 auto;color:#555'}));
        const rm = el('button', '×', {type: 'button', title: 'Remove from collection'}); rm.onclick = () => remove(x.key);
        row.append(rm); summary.append(row);
      });
    });
    if (!_items.length) summary.append(el('div', 'Nothing picked yet.', {className: 'cb-meta'}));
    panel.append(summary);

    const name = el('input', null, {id: 'cb-name', type: 'text', placeholder: 'Collection name', maxLength: 200});
    name.setAttribute('aria-label', 'Collection name');
    const desc = el('textarea', null, {id: 'cb-desc', rows: 2, placeholder: 'Description (purpose: sharing, analysis…)'});
    desc.setAttribute('aria-label', 'Collection description');
    const save = el('button', 'Save collection', {id: 'cb-save', type: 'button'}); save.onclick = _save;
    const clr = el('button', 'Clear picks', {id: 'cb-clear', type: 'button'}); clr.onclick = clear;
    const actions = el('div', null, {className: 'cb-actions'}); actions.append(save, clr);
    panel.append(name, desc, actions, el('div', '', {id: 'cb-status', className: 'cb-meta', role: 'status'}));

    panel.append(el('h4', 'Saved collections'));
    const sel = el('select', null, {id: 'cb-saved'}); sel.setAttribute('aria-label', 'Saved collections');
    sel.append(el('option', 'Loading…', {value: ''}));
    const plan = el('button', 'Draft sharing plan', {id: 'cb-plan', type: 'button'}); plan.onclick = _draftPlan;
    panel.append(sel, el('div', null, {className: 'cb-actions'}));
    panel.lastChild.append(plan);
    panel.append(el('pre', _plan, {id: 'cb-plan-out', hidden: !_plan}));
    if (_list.length || _saved) _fillSaved(sel);
  }

  function _status(text) { const s = $('cb-status'); if (s) s.textContent = text; }

  async function _json(url, opts) {
    const r = await fetch(BASE() + url, opts);
    let d = {}; try { d = await r.json(); } catch (e) { /* non-JSON */ }
    return {ok: r.ok, status: r.status, d};
  }

  let _list = [];
  async function _loadSaved() {
    try {
      const {d} = await _json('/api/collections');
      _list = d.collections || [];
    } catch (e) { _list = []; }
    const sel = $('cb-saved'); if (sel) _fillSaved(sel);
  }
  function _fillSaved(sel) {
    sel.replaceChildren();
    if (!_list.length) { sel.append(el('option', 'No saved collections', {value: ''})); return; }
    _list.forEach(c => sel.append(el('option', c.name + ' (' + c.members + ' members)', {value: c.id})));
    if (_saved && _list.some(c => c.id === _saved.id)) sel.value = _saved.id;
  }

  function _members() {
    return _items.map(x => Object.assign({kind: x.kind}, x.p || {}));
  }

  async function _save() {
    const name = ($('cb-name').value || '').trim();
    if (!name) { _status('Give the collection a name.'); return; }
    if (!_items.length) { _status('Pick something first.'); return; }
    _status('Saving…');
    const body = {name, description: $('cb-desc').value || '', members: _members()};
    const post = () => _json('/api/collections', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    let r = await post();
    if (r.status === 409 && r.d.exists) {
      if (!confirm('A collection named "' + name + '" already exists with ' + r.d.members + ' member(s). Add these to it?')) { _status('Not saved.'); return; }
      body.add_to_existing = true; r = await post();
    }
    if (!r.ok) { _status(r.d.error || ('Error ' + r.status)); return; }
    const l = r.d.linked || {};
    _saved = {id: r.d.collection_id, name};
    _status('Saved "' + name + '": ' + (l.dataset || 0) + ' dataset(s), ' + (l.folder || 0) + ' folder(s), ' + (l.file || 0) +
      ' file(s), ' + (l.context || 0) + ' context record(s).' + (r.d.problems && r.d.problems.length ? ' Skipped: ' + r.d.problems.length : ''));
    await _loadSaved();
    const sel = $('cb-saved'); if (sel && _saved) sel.value = _saved.id;
  }

  async function _draftPlan() {
    const sel = $('cb-saved'); const id = sel && sel.value;
    if (!id) { _status('Save or choose a collection first.'); return; }
    _status('Drafting the sharing plan…');
    const r = await _json('/api/plugins/nih_dms/collections/' + encodeURIComponent(id) + '/draft_plan',
      {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fields: {}})});
    if (!r.ok) { _status(r.d.error || ('Error ' + r.status)); return; }
    _plan = r.d.markdown || '';
    _saved = {id, name: (r.d.summary && r.d.summary.name) || ''};
    _status('Draft ready. Investigator review required; not a compliance determination.');
    const out = $('cb-plan-out'); if (out) { out.textContent = _plan; out.hidden = false; }
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
    _build(); if ($('cb-panel')) { $('cb-panel').classList.add('open'); _loadSaved(); }
    return added;
  }

  global.CollectionBasket = {add, remove, clear, items, has, open, close, checkbox, addChecked, fmt};
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _build); else _build();
})(window);
