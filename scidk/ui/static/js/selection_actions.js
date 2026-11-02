/**
 * selection_actions.js — the one compact action bar for selected rows.
 *
 *   Add to collection · Create dataset · Interpret · Ask about this
 *
 * Shown only while one or more rows are selected in Files, Scans or Entities; an action that
 * does not apply to the current selection is left out rather than refused. Nothing here owns
 * behaviour — every button hands off to something that already exists:
 *
 *   Add to collection → window.CollectionBasket (Files: Collection.addSelectionToCollection)
 *   Create dataset    → the manual Dataset dialog (collection.js → POST /api/datasets/manual)
 *   Interpret         → opens the row in the inspector (document event `scidk:inspect`) and the
 *                       inspector runs the existing interpreter status/run calls
 *   Ask about this    → the existing chat surface, with the selection carried as scope
 *
 * Exposes window.SelectionActions.mount(host, opts) → {refresh, items}. Files and Scans mount
 * themselves when their host element is on the page; Entities mounts from labels.html.
 *
 * opts: {surface, getItems(), watch?: Element|Element[], ids?: {add,dataset,interpret,ask},
 *        onAdd?(items), onDataset?(items), count?: boolean}
 * item: {kind: 'file'|'folder'|'dataset'|'context', key, label, basketItem, record?, path?,
 *        manual?: boolean, entityRef?: string}
 */
;(function (global) {
  'use strict';
  const BASE = () => (typeof global.SCIDK_BASE !== 'undefined' ? global.SCIDK_BASE : '');
  const basket = () => global.CollectionBasket;
  const ASK_KEY = 'scidk.ask.scope.v1';
  const ASK_MAX = 50;

  function el(tag, text, attrs) {
    const e = document.createElement(tag);
    if (text != null) e.textContent = text;
    if (attrs) Object.assign(e, attrs);
    return e;
  }

  function _style() {
    if (document.getElementById('sa-style')) return;
    const s = el('style', `
.sa-wrap{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap}
.sa-bar{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap;padding:3px 0}
.sa-bar[hidden]{display:none}
.sa-bar .sa-count{font-size:12px;font-weight:600;color:#0a58ca;margin-right:2px}
.sa-bar button{font-size:12px;padding:2px 10px;border:1px solid #adb5bd;border-radius:4px;background:#fff;cursor:pointer}
.sa-bar button:hover{background:#e9ecef}
.sa-bar button.sa-primary{border-color:#0d6efd;color:#0a58ca}
.sa-status{font-size:11px;color:#495057}`);
    s.id = 'sa-style';
    document.head.appendChild(s);
  }

  // ── what each action means for a selection ───────────────────────────────
  const canCreateDataset = items => items.length > 0 && items.every(i => (i.kind === 'file' || i.kind === 'folder') && i.manual === true);
  const canInterpret = items => items.some(i => i.kind === 'file' || i.kind === 'folder' || i.kind === 'dataset');

  // The record the inspector opens: a File/folder row or a recognized Dataset from the Scans index.
  function _inspectDetail(items) {
    const first = items[0];
    const paths = [];
    items.forEach(i => {
      if (i.kind === 'file') paths.push(i.path);
      else if (i.kind === 'dataset' && i.record && i.record.root_path) paths.push(i.record.root_path);
    });
    return {
      kind: first.kind === 'dataset' ? 'scan-dataset' : 'file',
      key: first.key,
      record: Object.assign({name: first.label}, first.record || {}),
      tab: 'Interpret', interpret: true,
      scope: {count: items.length, paths: paths.length ? paths : (first.path ? [first.path] : [])},
    };
  }

  function _askUrl(items) {
    const ref = items.length === 1 && items[0].entityRef;
    if (ref && document.getElementById('shared-inspector')) {
      return BASE() + '/overview?' + new URLSearchParams({domain: 'research', id: ref});
    }
    try {
      global.sessionStorage.setItem(ASK_KEY, JSON.stringify({
        at: Date.now(), count: items.length,
        items: items.slice(0, ASK_MAX).map(i => ({kind: i.kind, key: i.key, label: i.label})),
      }));
    } catch (e) { /* private mode: the chat opens without the carried scope */ }
    return BASE() + '/chat?scope=selection';
  }

  // ── the bar ───────────────────────────────────────────────────────────────
  function mount(host, opts) {
    if (!host || host._saMounted) return host && host._saMounted;
    _style();
    const ids = Object.assign({}, opts.ids);
    const wrap = el('span', null, {className: 'sa-wrap'});
    const bar = el('span', null, {className: 'sa-bar', hidden: true});
    bar.setAttribute('role', 'toolbar'); bar.setAttribute('aria-label', 'Selection actions');
    bar.setAttribute('data-testid', 'selection-actions-bar');
    bar.setAttribute('data-surface', opts.surface);
    const count = el('span', '', {className: 'sa-count'});
    const mk = (key, text, title, primary) => {
      const b = el('button', text, {type: 'button', title, className: primary ? 'sa-primary' : ''});
      if (ids[key]) b.id = ids[key];
      b.setAttribute('data-testid', 'selection-action-' + key);
      b.setAttribute('data-action', key);
      return b;
    };
    const bAdd = mk('add', 'Add to collection', 'Add the selected rows to the shared Collection', true);
    const bDs = mk('dataset', 'Create dataset', 'Create a new manual Dataset (not a Collection) from the selected files and folders');
    const bInt = mk('interpret', 'Interpret', 'Open the selected row in the inspector and run the existing interpreters');
    const bAsk = mk('ask', 'Ask about this', 'Open the chat with the selection as scope');
    bar.append(...(opts.count === false ? [] : [count]), bAdd, bDs, bInt, bAsk);
    const status = el('span', '', {className: 'sa-status'});
    status.setAttribute('role', 'status'); status.setAttribute('data-testid', 'selection-actions-status');
    wrap.append(bar, status);
    host.appendChild(wrap);

    let current = [];
    const say = msg => {
      status.textContent = msg || '';
      if (msg && typeof global.setStatus === 'function' && opts.surface === 'files') global.setStatus(msg);
    };
    function refresh() {
      let items = [];
      try { items = (opts.getItems() || []).filter(Boolean); } catch (e) { items = []; }
      current = items;
      bar.hidden = items.length === 0;
      count.textContent = items.length + ' selected';
      bDs.hidden = !(opts.surface === 'files' && canCreateDataset(items));
      bInt.hidden = !canInterpret(items);
      bAsk.hidden = items.length === 0;
      if (items.length) status.textContent = status.textContent;   // keep the last message beside the bar
    }

    bAdd.onclick = () => {
      if (!current.length) return;
      const items = current.slice();
      if (opts.onAdd) { opts.onAdd(items); refresh(); return; }
      const n = basket().add(items.map(i => i.basketItem));
      if (opts.afterAdd) opts.afterAdd(items);
      basket().open();
      say(n ? n + ' added to the collection' : 'Already in the collection');
      refresh();
    };
    bDs.onclick = () => {
      if (!current.length) return;
      const items = current.slice();
      if (opts.onDataset) opts.onDataset(items);
    };
    bInt.onclick = () => {
      if (!current.length) return;
      const items = current.slice();
      if (document.getElementById('shared-inspector')) {
        document.dispatchEvent(new CustomEvent('scidk:inspect', {detail: _inspectDetail(items)}));
      } else if (global.Annotate && global.Annotate.open) {
        global.Annotate.open('interpret');          // no inspector on this page: the legacy drawer is the surface
      } else {
        say('Open the inspector to interpret this selection.');
      }
    };
    bAsk.onclick = () => {
      if (!current.length) return;
      global.location.assign(_askUrl(current.slice()));
    };

    let queued = false;
    const later = () => { if (queued) return; queued = true; (global.requestAnimationFrame || setTimeout)(() => { queued = false; refresh(); }); };
    const watch = [].concat(opts.watch || []).filter(Boolean);
    watch.forEach(w => {
      w.addEventListener('change', later, true);
      if (global.MutationObserver) new MutationObserver(later).observe(w, {childList: true, subtree: true});
    });
    document.addEventListener('scidk:selectionchange', later);
    document.addEventListener('scidk:collectionbasket', later);
    refresh();

    host._saMounted = {refresh, items: () => current.slice(), say};
    return host._saMounted;
  }

  // ── Files adapter: the checked rows, by id (full path) ───────────────────
  function _rowSize(id) {
    const tr = [...document.querySelectorAll('#file-list tr[data-id]')].find(r => r.dataset.id === id);
    return tr && tr.dataset.size ? Number(tr.dataset.size) : null;
  }
  function _filesItems() {
    const B = basket();
    const sel = global.selItems;
    if (!B || !sel || !sel.size) return [];
    return [...sel].map(id => {
      const it = B.fileItemFromId(id, _rowSize(id));
      return {
        kind: it.kind, key: id, label: it.label, basketItem: it, path: it.p.path, manual: true,
        record: Object.assign({}, it.p, {type: it.kind}),
      };
    });
  }
  function _mountFiles() {
    const host = document.getElementById('files-selection-actions');
    if (!host) return;
    mount(host, {
      surface: 'files', count: false, getItems: _filesItems,
      ids: {add: 'add-to-coll-btn', dataset: 'create-dataset-btn'},
      onAdd: items => {
        if (global.indexedContext) {   // an indexed Browse location: members already carry their scan reference
          const n = basket().add(items.map(i => i.basketItem));
          basket().open();
          host._saMounted && host._saMounted.say(n ? n + ' added to the collection' : 'Already in the collection');
          return;
        }
        if (global.Collection) global.Collection.addSelectionToCollection();
      },
      onDataset: items => {
        if (global.Collection) global.Collection.openManualDatasetDialog(items.map(i => Object.assign({kind: i.kind}, i.basketItem.p)));
      },
    });
  }

  // ── Scans adapter: checked rows / recognized datasets in the external index ──
  function _scansItems() {
    const root = document.getElementById('gui-scans');
    if (!root) return [];
    return [...root.querySelectorAll('input.coll-add-cb:checked')].map(b => {
      const it = b._makeItem && b._makeItem();
      if (!it) return null;
      const p = it.p || {};
      return {
        kind: it.kind, key: it.key, label: it.label, basketItem: it,
        path: it.kind === 'dataset' ? '' : p.path, manual: false,
        record: Object.assign({}, p, {type: it.kind, scan_index: true}),
      };
    }).filter(Boolean);
  }
  function _mountScans() {
    const host = document.getElementById('scans-selection-actions');
    const root = document.getElementById('gui-scans');
    if (!host || !root) return;
    mount(host, {
      surface: 'scans', getItems: _scansItems, ids: {add: 'scans-add'}, watch: root,
      onAdd: () => {
        const added = basket().addChecked(root);
        const note = document.getElementById('scans-note');
        const msg = added ? added + ' added to the collection.' : 'Already in the collection.';
        if (note) note.textContent = msg;
        host._saMounted && host._saMounted.say(msg);
      },
    });
  }

  function _auto() { _mountFiles(); _mountScans(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _auto); else _auto();

  global.SelectionActions = {mount, ASK_KEY};
})(window);
