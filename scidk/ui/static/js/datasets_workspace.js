/* Datasets workspace: the Datasets list and the Collections page.
 *
 * Datasets     recognized datasets (GET /api/external-index/datasets/all, read-only references keyed by
 *              scan_id + root_path) and manual datasets (GET /api/datasets/manual).
 * Collections  the saved :Collection list (GET /api/collections), one Collection's grouped members
 *              (GET /api/collections/<id>) and its sharing-plan draft (the existing nih_dms route).
 * Everything is read-only here except what the shared basket already does (one POST /api/collections).
 * No delete / remove / dissolve controls exist: graph writes are MERGE only.
 */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const root = $('gui-files');
  if (!root || !root.dataset.wsView || !$('gui-collections')) return;
  const view = root.dataset.wsView;
  const base = window.SCIDK_BASE || '';
  const basket = () => window.CollectionBasket;
  const num = n => Number(n).toLocaleString();
  const fmt = n => {
    if (n == null || isNaN(n)) return '';
    const u = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']; let i = 0, v = Number(n);
    while (v >= 1000 && i < u.length - 1) { v /= 1000; i++; }
    return (i === 0 ? v.toFixed(0) : v.toFixed(v < 10 ? 1 : 0)) + ' ' + u[i];
  };
  const stamp = ms => ms ? new Date(Number(ms)).toISOString().slice(0, 16).replace('T', ' ') : '';
  const el = (tag, text, attrs) => { const e = document.createElement(tag); if (text != null) e.textContent = text; Object.assign(e, attrs || {}); return e; };
  const link = (text, href, attrs) => el('a', text, Object.assign({href: base + href}, attrs || {}));
  const byName = (a, b) => String(a.name || '').localeCompare(String(b.name || ''), undefined, {sensitivity: 'base', numeric: true});
  async function api(url, opts) {
    const response = await fetch(base + url, opts);
    let data = {};
    try { data = await response.json(); } catch (e) { /* non-JSON error page */ }
    return {ok: response.ok, status: response.status, data};
  }
  const say = (id, text) => { if ($(id)) $(id).textContent = text || ''; };

  /* ===================== Datasets ===================== */
  /* One alphabetical list merging three sources, each row labelled candidate | confirmed | manual:
   *   scan index  GET /api/external-index/datasets/all   observed, profile-recognized candidates (read-only reference)
   *   graph       GET /api/datasets/graph                editable :Dataset objects (confirmed references and manual)
   * A candidate becomes confirmed when the graph already holds the Dataset keyed to the same (scan_id, root_path).
   * Every kind joins a Collection through the same :Dataset INCLUDES member shape. */
  const inspect = (key, record) => document.dispatchEvent(new CustomEvent('scidk:inspect', {detail: {kind: 'scan-dataset', key, record}}));

  function datasetItem(d) {
    if (d.state === 'manual') {
      return {key: 'dataset|manual|' + d.dataset_id, kind: 'dataset', label: d.name, title: 'Manual dataset', size: d.bytes || null,
              files: d.files, tag: 'manual', p: {dataset_id: d.dataset_id, name: d.name}};
    }
    return {
      key: 'dataset|' + d.scan_id + '|' + d.root_path, kind: 'dataset', label: d.name, title: d.root_path,
      size: d.total_bytes, files: d.file_count, tag: d.pattern_name,
      p: {scan_id: d.scan_id, root_path: d.root_path, profile: d.pattern_name, file_count: d.file_count, bytes: d.total_bytes},
    };
  }
  const baseName = path => (path || '').replace(/\/+$/, '').split('/').pop() || path || '';
  function merge(rec, graph) {
    const out = [], seen = new Set();
    const graphRef = new Map();
    graph.forEach(g => { if (g.scan_id && g.root_path) graphRef.set(g.scan_id + '|' + g.root_path, g); });
    rec.forEach(r => {
      const key = r.scan_id + '|' + r.root_path, g = graphRef.get(key);
      seen.add(key);
      out.push(Object.assign({}, r, {state: g ? 'confirmed' : 'candidate', name: (g && g.name) || r.name, dataset_id: g && g.id,
                                    description: g && g.description, key}));
    });
    graph.forEach(g => {
      if (g.source === 'manual' || !(g.scan_id && g.root_path)) {
        if (g.source !== 'manual') return;
        out.push({state: 'manual', dataset_id: g.id, name: g.name || '(unnamed)', description: g.description, files: g.files, folders: g.folders,
                  bytes: g.bytes, created_at: g.created_at, key: 'manual|' + g.id});
      } else if (!seen.has(g.scan_id + '|' + g.root_path)) {
        out.push({state: 'confirmed', dataset_id: g.id, scan_id: g.scan_id, root_path: g.root_path, name: g.name || baseName(g.root_path),
                  pattern_name: g.profile, file_count: g.file_count, total_bytes: g.dataset_bytes, description: g.description,
                  key: g.scan_id + '|' + g.root_path, not_in_index: true});
      }
    });
    return out.sort(byName);
  }

  const STATE_TITLE = {
    candidate: 'Recognized in a scan; not yet in the graph',
    confirmed: 'A Dataset in the graph, keyed to its scan and root',
    manual: 'Created by hand from files and folders',
  };

  function datasetCard(d) {
    const card = el('article', null, {className: 'ds-card', tabIndex: -1});
    card.dataset.kind = d.state; card.dataset.key = d.key;
    const head = el('div', null, {className: 'ds-head'});
    const cb = basket() && basket().checkbox(() => datasetItem(d), 'Select dataset ' + d.name + ' for the collection');
    if (cb) head.append(cb);
    const open = el('button', d.name, {type: 'button', className: 'ds-name', title: 'Open details' + (d.root_path ? ': ' + d.root_path : '')});
    open.onclick = () => inspect(d.key, d);
    head.append(open, el('span', d.state, {className: 'ds-badge ds-state-' + d.state, title: STATE_TITLE[d.state]}));
    head.append(el('span', d.state === 'manual' ? 'manual' : (d.pattern_name || 'no recognized profile'), {className: 'ds-badge', title: 'Profile'}));
    card.append(head);
    if (d.description) card.append(el('div', d.description, {className: 'ds-meta'}));
    if (d.state === 'manual') {
      card.append(el('div', [num(d.files || 0) + ' files', num(d.folders || 0) + ' folders', d.bytes ? fmt(d.bytes) : 'size not recorded'].join(' · '), {className: 'ds-meta'}));
      card.append(el('div', 'Source: knowledge graph (manual Dataset); its files and folders stay where they are', {className: 'ds-meta ds-where'}));
      card.append(el('div', 'Provenance: created by hand' + (d.created_at ? ' · ' + stamp(d.created_at) : '') + ' · not a scan reference', {className: 'ds-meta ds-prov'}));
    } else {
      card.append(el('div', [d.file_count != null ? num(d.file_count) + ' files' : 'file count pending', d.total_bytes != null ? fmt(d.total_bytes) : 'size pending'].join(' · '), {className: 'ds-meta'}));
      card.append(el('div', 'Source: ' + ([d.host, d.share].filter(Boolean).join(' / ') || 'scan index') + ' · ' + d.root_path, {className: 'ds-meta ds-where'}));
      card.append(el('div', 'Provenance: reference to scan ' + String(d.scan_id).slice(0, 8) + (d.scan_date ? ' (' + d.scan_date + ')' : '')
        + (d.not_in_index ? ' · not in the connected scan index' : ' · profile ' + (d.pattern_name || 'none')) + ' · file rows stay in the scan index', {className: 'ds-meta ds-prov'}));
    }
    const act = el('div', null, {className: 'ds-actions'});
    const add = el('button', 'Add to collection', {type: 'button', title: 'Add this Dataset to the Collection basket'});
    add.setAttribute('data-action', 'add-dataset');
    add.onclick = () => { const n = basket() && basket().add([datasetItem(d)]); basket() && basket().open(); say('datasets-status', n ? 'Added ' + d.name + ' to the Collection basket.' : d.name + ' is already in the Collection basket.'); };
    act.append(add);
    card.append(act);
    return card;
  }

  async function loadDatasets() {
    const params = new URLSearchParams({workspace: $('datasets-workspace-toggle').checked ? '1' : '0'});
    const [rec, graph] = await Promise.all([api('/api/external-index/datasets/all?' + params), api('/api/datasets/graph')]);
    const box = $('datasets-list'); box.replaceChildren();
    const notes = [];
    if (!rec.ok) notes.push('Scan-index candidates are unavailable: ' + ((rec.data && rec.data.error) || rec.status));
    if (!graph.ok) notes.push('Graph and manual Datasets are unavailable: ' + ((graph.data && graph.data.error) || graph.status));
    const list = merge(rec.ok ? (rec.data.datasets || []) : [], graph.ok ? (graph.data.datasets || []) : []);
    say('datasets-status', notes.join(' '));
    const counts = ['candidate', 'confirmed', 'manual'].map(k => num(list.filter(d => d.state === k).length) + ' ' + k);
    say('datasets-count', list.length ? num(list.length) + ' Datasets (' + counts.join(', ') + ')' + (rec.ok && rec.data.capped ? ' — the scan list is capped' : '') + '.' : '');
    if (!list.length && !notes.length) box.textContent = 'No Datasets yet. Run a scan, or select files and folders in Browse and choose Create dataset.';
    list.forEach(d => box.append(datasetCard(d)));
    const want = new URLSearchParams(location.search).get('highlight');
    if (want) {
      const card = Array.from(box.querySelectorAll('.ds-card')).find(c => c.dataset.key === want);
      if (card) { card.classList.add('ds-highlight'); card.scrollIntoView({block: 'center'}); card.focus(); }
    }
  }

  function mountDatasets() {
    const bar = el('div', null, {className: 'ds-toolbar'});
    const add = el('button', 'Add checked to collection', {type: 'button', id: 'datasets-add-checked'});
    add.setAttribute('data-action', 'add-checked');
    add.onclick = () => {
      const n = basket() ? basket().addChecked($('gui-datasets')) : 0;
      say('datasets-status', n ? 'Added ' + n + (n === 1 ? ' dataset' : ' datasets') + ' to the Collection basket.' : 'Tick one or more datasets first (or use a card’s own Add to collection).');
    };
    bar.append(add);
    $('datasets-selection-actions').append(bar);
    $('datasets-workspace-toggle').onchange = loadDatasets;
    loadDatasets();
  }

  /* ===================== Collections ===================== */
  let planReturn = null;

  function countsLine(c) {
    return [num(c.datasets || 0) + ' datasets', num(c.folders || 0) + ' folders', num(c.files || 0) + ' files', num(c.context_members || 0) + ' context'].join(' · ');
  }

  function collectionCard(c) {
    const card = el('article', null, {className: 'ds-card'});
    card.dataset.id = c.id;
    const head = el('div', null, {className: 'ds-head'});
    const name = el('button', c.name || '(unnamed)', {type: 'button', className: 'ds-name'});
    name.onclick = () => openCollection(c.id, true);
    head.append(name);
    card.append(head);
    if (c.description) card.append(el('div', c.description, {className: 'ds-meta'}));
    card.append(el('div', countsLine(c), {className: 'ds-meta'}));
    card.append(el('div', (c.bytes ? fmt(c.bytes) + ' known size' : 'No size recorded') + ' · folder contents are not enumerated'
      + (c.updated_at || c.created_at ? ' · ' + (c.updated_at ? 'updated ' + stamp(c.updated_at) : 'created ' + stamp(c.created_at)) : ''), {className: 'ds-meta'}));
    const act = el('div', null, {className: 'ds-actions'});
    const open = el('button', 'Open', {type: 'button'}); open.setAttribute('data-action', 'open-collection');
    open.onclick = () => openCollection(c.id, true);
    act.append(open); card.append(act);
    return card;
  }

  async function loadCollections() {
    const box = $('collections-list');
    const r = await api('/api/collections');
    box.replaceChildren();
    if (!r.ok) { box.textContent = (r.data && r.data.error) || ('Collections are unavailable (' + r.status + ').'); return; }
    const list = (r.data.collections || []).slice().sort(byName);
    if (!list.length) { box.textContent = 'No saved Collections yet. Add Datasets, Files or Folders to the Collection basket (lower right) and save it.'; return; }
    list.forEach(c => box.append(collectionCard(c)));
  }

  const GROUPS = [
    ['dataset', 'Datasets', 'datasets', '/datasets?view=datasets', 'Datasets tab'],
    ['folder', 'Folders', 'folders', '/datasets?view=browse', 'Browse'],
    ['file', 'Files', 'files', '/datasets?view=browse', 'Browse'],
    ['context', 'Context', 'context', '/knowledge?view=entities', 'Entities'],
  ];
  const MEMBER_ROWS = 50;

  function memberRow(kind, m) {
    const li = el('li');
    if (kind === 'dataset') {
      const name = m.name || (m.root_path || '').replace(/\/+$/, '').split('/').pop() || '(dataset)';
      const manual = m.source === 'manual' || (!m.scan_id && m.dataset_id);
      const hl = manual ? 'manual|' + m.dataset_id : m.scan_id + '|' + m.root_path;
      li.append(link(manual ? (m.name || '(manual dataset)') : name, '/datasets?view=datasets&highlight=' + encodeURIComponent(hl), {title: m.root_path || 'Manual dataset'}));
      li.append(el('span', ' ' + [manual ? 'manual' : m.profile, !manual && m.file_count != null ? num(m.file_count) + ' files' : null, m.bytes != null ? fmt(m.bytes) : 'size not recorded'].filter(Boolean).join(' · '), {className: 'ds-meta'}));
    } else if (kind === 'folder') {
      li.append(link(m.name || (m.path || '').split('/').pop() || m.path, '/datasets?view=browse', {title: m.path}));
      li.append(el('span', ' ' + (m.path || ''), {className: 'ds-meta'}));
    } else if (kind === 'file') {
      li.append(link(m.filename || (m.path || '').split('/').pop() || m.path, '/datasets?view=browse', {title: m.path}));
      li.append(el('span', ' ' + (m.size_bytes != null ? fmt(m.size_bytes) : 'size not recorded'), {className: 'ds-meta'}));
    } else {
      li.append(link((m.label || 'Node') + (m.display ? ': ' + m.display : ''), '/knowledge?view=entities', {title: 'Open in Knowledge → Entities'}));
      li.append(' ', link('Maps', '/knowledge?view=maps', {className: 'ds-meta'}));
    }
    return li;
  }

  function renderDetail(found) {
    const c = found.collection, members = found.members;
    const box = $('collection-detail'); box.replaceChildren();
    const back = el('button', '← All Collections', {type: 'button', id: 'collection-back'});
    back.onclick = () => showList(true);
    box.append(back);
    box.append(el('h3', c.name || '(unnamed)', {id: 'collection-detail-name'}));
    if (c.description) box.append(el('p', c.description, {id: 'collection-detail-description'}));
    const counts = {datasets: members.dataset.length, folders: members.folder.length, files: members.file.length, context_members: members.context.length};
    const known = members.dataset.reduce((a, m) => a + (Number(m.bytes) || 0), 0) + members.file.reduce((a, m) => a + (Number(m.size_bytes) || 0), 0);
    box.append(el('p', countsLine(counts) + ' · ' + (known ? fmt(known) + ' known size' : 'no size recorded')
      + (c.updated_at || c.created_at ? ' · ' + (c.updated_at ? 'updated ' + stamp(c.updated_at) : 'created ' + stamp(c.created_at)) : ''), {className: 'ds-meta', id: 'collection-detail-counts'}));
    box.append(el('p', 'Folders are included by reference. Their contents are not enumerated here, so folder members add no size and no file count to these totals.', {className: 'ds-meta', id: 'collection-folder-note'}));
    const act = el('div', null, {className: 'ds-actions'});
    const plan = el('button', 'Draft sharing plan', {type: 'button', id: 'collection-draft-plan'});
    plan.setAttribute('data-action', 'draft-plan');
    plan.onclick = () => draftPlan(c.id, c.name, plan);
    const active = el('button', 'Make active in basket', {type: 'button', title: 'Open this Collection in the shared basket to add more picks'});
    active.onclick = () => { basket() && basket().openSaved(c.id); basket() && basket().open(); };
    act.append(plan, active); box.append(act);
    box.append(el('p', 'A draft is for investigator review; it is not a compliance determination and covers this Collection only.', {className: 'ds-meta'}));
    GROUPS.forEach(([kind, label, countKey, href, where]) => {
      const rows = members[kind] || [];
      const section = el('section', null, {className: 'cd-group'});
      section.dataset.kind = kind;
      section.append(el('h4', label + ' (' + num(rows.length) + ')'));
      if (!rows.length) section.append(el('p', 'None.', {className: 'ds-meta'}));
      else {
        const ul = el('ul');
        rows.slice(0, MEMBER_ROWS).forEach(m => ul.append(memberRow(kind, m)));
        section.append(ul);
        if (rows.length > MEMBER_ROWS) section.append(el('p', '+ ' + num(rows.length - MEMBER_ROWS) + ' more (showing the first ' + MEMBER_ROWS + ').', {className: 'ds-meta'}));
        const more = el('p', 'Open in ', {className: 'ds-meta'}); more.append(link(where, href)); section.append(more);
      }
      box.append(section);
    });
  }

  function showList(push) {
    closePlan(true);
    $('collection-detail').hidden = true; $('collections-list').hidden = false;
    say('collections-status', '');
    if (push) history.pushState(null, '', base + '/datasets?view=collections');
  }

  async function openCollection(id, push) {
    say('collections-status', 'Opening…');
    const r = await api('/api/collections/' + encodeURIComponent(id));
    if (!r.ok || !r.data.collection) { say('collections-status', (r.data && r.data.error) || 'Collection not found.'); return; }
    say('collections-status', '');
    renderDetail(r.data);
    $('collections-list').hidden = true; $('collection-detail').hidden = false;
    if (push) history.pushState(null, '', base + '/datasets?view=collections&collection=' + encodeURIComponent(id));
  }

  /* ---- sharing plan: an in-page panel, Close button and Escape; the Collection stays where it is ---- */
  function closePlan(quiet) {
    const panel = $('collection-plan-panel');
    if (!panel || panel.hidden) return;
    panel.hidden = true;
    if (!quiet && planReturn && document.contains(planReturn)) planReturn.focus();
    planReturn = null;
  }

  async function draftPlan(id, name, opener) {
    const panel = $('collection-plan-panel');
    planReturn = opener || document.activeElement;
    $('collection-plan-title').textContent = 'Sharing plan draft' + (name ? ' · ' + name : '');
    $('collection-plan-out').textContent = '';
    say('collection-plan-status', 'Drafting the sharing plan…');
    panel.hidden = false;
    $('collection-plan-close').focus();
    const r = await api('/api/plugins/nih_dms/collections/' + encodeURIComponent(id) + '/draft_plan',
      {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fields: {}})});
    if (panel.hidden) return;
    if (!r.ok) { say('collection-plan-status', (r.data && r.data.error) || ('Error ' + r.status)); return; }
    $('collection-plan-out').textContent = r.data.markdown || '';
    say('collection-plan-status', 'Draft ready. Investigator review required; not a compliance determination.');
  }

  function mountCollections() {
    $('collection-plan-close').onclick = () => closePlan();
    $('collection-plan-copy').onclick = async () => {
      try { await navigator.clipboard.writeText($('collection-plan-out').textContent); say('collection-plan-status', 'Draft copied.'); }
      catch (e) { say('collection-plan-status', 'Copy failed — select the text and copy it by hand.'); }
    };
    document.addEventListener('keydown', event => {
      const panel = $('collection-plan-panel');
      if (event.key === 'Escape' && panel && !panel.hidden) { event.preventDefault(); closePlan(); }
    });
    const route = () => {
      const id = new URLSearchParams(location.search).get('collection');
      if (id) openCollection(id, false); else showList(false);
    };
    window.addEventListener('popstate', route);
    loadCollections().then(route);
  }

  if (view === 'datasets') mountDatasets();
  if (view === 'collections') mountCollections();
})();
