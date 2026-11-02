/* Datasets workspace: the Datasets list and the Collections page.
 *
 * Datasets     the paged, searchable Dataset catalog (GET /api/datasets/catalog); Confirm and Edit write through
 *              POST /api/datasets/confirm and /api/datasets/metadata (graph MERGE / property updates only).
 * Collections  the saved :Collection list (GET /api/collections), one Collection's grouped members
 *              (GET /api/collections/<id>) and its sharing-plan draft (the existing nih_dms route).
 * Writes: the shared basket (one POST /api/collections) and the two Dataset routes above.
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
  /* One catalog, served a page at a time by GET /api/datasets/catalog: scan candidates (read-only evidence),
   * confirmed Datasets (graph :Dataset keyed by scan_id + root_path) and manual Datasets, already merged, searched,
   * filtered by state and sorted globally by displayed name on the server. Nothing is merged or sorted here.
   * Writes: POST /api/datasets/confirm (MERGE) and POST /api/datasets/metadata (name / description / profile override).
   * Every kind joins a Collection through the same :Dataset INCLUDES member shape. */
  const inspect = (key, record) => document.dispatchEvent(new CustomEvent('scidk:inspect', {detail: {kind: 'scan-dataset', key, record}}));
  const PAGE_SIZE = 50;
  const ds = {q: '', state: 'all', offset: 0, version: 0, page: [], timer: null, flash: ''};
  const JSON_HEADERS = {'Content-Type': 'application/json'};

  function datasetItem(d) {
    if (d.state === 'manual') {
      return {key: 'dataset|manual|' + d.dataset_id, kind: 'dataset', label: d.name, title: 'Manual dataset', size: d.total_bytes || null,
              files: d.file_count, tag: 'manual', p: {dataset_id: d.dataset_id, name: d.name}};
    }
    // By reference: the observed profile travels, never the human override.
    return {
      key: 'dataset|' + d.scan_id + '|' + d.root_path, kind: 'dataset', label: d.name, title: d.root_path,
      size: d.total_bytes, files: d.file_count, tag: d.profile || d.observed_profile,
      p: {scan_id: d.scan_id, root_path: d.root_path, profile: d.observed_profile, file_count: d.file_count, bytes: d.total_bytes},
    };
  }

  const STATE_TITLE = {
    candidate: 'Recognized in a scan; not yet confirmed as a Dataset in the graph',
    confirmed: 'Confirmed: a Dataset in the graph, keyed to its scan and root',
    manual: 'Created by hand from files and folders',
  };

  function profileBadge(d) {
    if (d.state === 'manual') return d.human_profile ? 'profile: ' + d.human_profile + ' (human)' : 'manual';
    if (d.human_profile) return 'profile: ' + d.human_profile + ' (human) · observed ' + (d.observed_profile || 'none');
    return d.observed_profile ? 'observed profile: ' + d.observed_profile : 'no recognized profile';
  }

  function datasetCard(d) {
    const card = el('article', null, {className: 'ds-card', tabIndex: -1});
    card.dataset.kind = d.state; card.dataset.key = d.key;
    const head = el('div', null, {className: 'ds-head'});
    const cb = basket() && basket().checkbox(() => datasetItem(d), 'Select dataset ' + d.name + ' for the collection');
    if (cb) head.append(cb);
    const open = el('button', d.name, {type: 'button', className: 'ds-name', title: 'Open details' + (d.root_path ? ': ' + d.root_path : '')});
    open.onclick = () => inspect(d.key, d);
    head.append(open, el('span', d.state, {className: 'ds-badge ds-state-' + d.state, title: STATE_TITLE[d.state]}));
    head.append(el('span', profileBadge(d), {className: 'ds-badge', title: 'Profile'}));
    card.append(head);
    if (d.description) card.append(el('div', d.description, {className: 'ds-meta'}));
    if (d.state === 'manual') {
      card.append(el('div', [num(d.file_count || 0) + ' files', num(d.folders || 0) + ' folders', d.total_bytes ? fmt(d.total_bytes) : 'size not recorded'].join(' · '), {className: 'ds-meta'}));
      card.append(el('div', 'Source: knowledge graph (manual Dataset); its files and folders stay where they are', {className: 'ds-meta ds-where'}));
      card.append(el('div', 'Provenance: created by hand' + (d.created_at ? ' · ' + stamp(d.created_at) : '') + ' · not a scan reference', {className: 'ds-meta ds-prov'}));
    } else {
      card.append(el('div', [d.file_count != null ? num(d.file_count) + ' files' : 'file count pending', d.total_bytes != null ? fmt(d.total_bytes) : 'size pending'].join(' · '), {className: 'ds-meta'}));
      card.append(el('div', 'Source: ' + ([d.host, d.share].filter(Boolean).join(' / ') || 'scan index') + ' · ' + d.root_path, {className: 'ds-meta ds-where'}));
      card.append(el('div', 'Provenance: scan ' + String(d.scan_id).slice(0, 8) + (d.scan_date ? ' (' + d.scan_date + ')' : '')
        + (d.in_index ? '' : ' · not in the connected scan index (or hidden by the workspace filter)')
        + ' · file rows stay in the scan index', {className: 'ds-meta ds-prov'}));
    }
    const act = el('div', null, {className: 'ds-actions'});
    if (d.state === 'candidate') {
      const confirm = el('button', 'Confirm dataset', {type: 'button', title: 'Add this Dataset to the graph so it can be named and described. The scan record is not changed.'});
      confirm.setAttribute('data-action', 'confirm-dataset');
      confirm.onclick = () => confirmDataset(d, confirm);
      act.append(confirm);
    }
    const add = el('button', 'Add to collection', {type: 'button', title: 'Add this Dataset to the Collection basket'});
    add.setAttribute('data-action', 'add-dataset');
    add.onclick = () => { const n = basket() && basket().add([datasetItem(d)]); basket() && basket().open(); say('datasets-status', n ? 'Added ' + d.name + ' to the Collection basket.' : d.name + ' is already in the Collection basket.'); };
    act.append(add);
    card.append(act);
    return card;
  }

  function syncUrl() {
    const params = new URLSearchParams({view: 'datasets'});
    if (ds.q) params.set('q', ds.q);
    if (ds.state !== 'all') params.set('state', ds.state);
    if (ds.offset) params.set('offset', String(ds.offset));
    history.replaceState(null, '', base + '/datasets?' + params);
  }

  function setPager(r) {
    const prev = r && r.prev_offset != null, next = r && r.next_offset != null;
    ['datasets-prev', 'datasets-prev-bottom'].forEach(id => { $(id).disabled = !prev; });
    ['datasets-next', 'datasets-next-bottom'].forEach(id => { $(id).disabled = !next; });
  }

  async function loadDatasets() {
    const version = ++ds.version;
    const params = new URLSearchParams({q: ds.q, state: ds.state, offset: String(ds.offset), limit: String(PAGE_SIZE),
                                        workspace: $('datasets-workspace-toggle').checked ? '1' : '0'});
    const r = await api('/api/datasets/catalog?' + params);
    if (version !== ds.version) return;     // a newer search superseded this answer
    const box = $('datasets-list'); box.replaceChildren();
    syncUrl();
    $('datasets-reset').hidden = !(ds.q || ds.state !== 'all');
    if (!r.ok) {
      say('datasets-status', (r.data && r.data.error) || ('The Dataset catalog is unavailable (' + r.status + ').'));
      say('datasets-count', ''); say('datasets-range', ''); setPager(null); ds.page = [];
      return;
    }
    const data = r.data;
    ds.page = data.datasets || [];
    say('datasets-status', [ds.flash].concat(data.notes || []).filter(Boolean).join(' '));
    const c = data.counts || {};
    say('datasets-count', num(data.total) + (data.total === 1 ? ' Dataset' : ' Datasets') + (ds.q ? ' matching “' + ds.q + '”' : '')
      + (ds.state !== 'all' ? ' · ' + ds.state : '') + ' — in this search: ' + num(c.all || 0) + ' all, ' + num(c.candidate || 0) + ' candidate, '
      + num(c.confirmed || 0) + ' confirmed, ' + num(c.manual || 0) + ' manual.');
    say('datasets-range', data.total ? 'Showing ' + num(data.first) + '–' + num(data.last) + ' of ' + num(data.total) : 'Showing 0');
    setPager(data);
    if (!ds.page.length && !(data.notes || []).length) {
      box.textContent = ds.q || ds.state !== 'all' ? 'No Datasets match this search and filter.'
        : 'No Datasets yet. Run a scan, or select files and folders in Browse and choose Create dataset.';
    }
    ds.page.forEach(d => box.append(datasetCard(d)));
    const want = new URLSearchParams(location.search).get('highlight');
    if (want) {
      const card = Array.from(box.querySelectorAll('.ds-card')).find(x => x.dataset.key === want);
      if (card) { card.classList.add('ds-highlight'); card.scrollIntoView({block: 'center'}); card.focus(); }
    }
  }

  const search = (patch) => { Object.assign(ds, patch, {flash: ''}); loadDatasets(); };

  /* ---- confirm and edit ---- */
  async function confirmDataset(d, button) {
    if (button) button.disabled = true;
    say('datasets-status', 'Confirming…');
    const r = await api('/api/datasets/confirm', {method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({scan_id: d.scan_id, root_path: d.root_path})});
    if (button) button.disabled = false;
    if (!r.ok) { const msg = (r.data && r.data.error) || ('Could not confirm (' + r.status + ').'); say('datasets-status', msg); say('ds-edit-status', msg); return; }
    const out = r.data;
    const fresh = Object.assign({}, d, {state: 'confirmed', name: out.name || d.name, description: out.description || d.description,
      human_profile: out.human_profile || d.human_profile, profile: out.human_profile || d.observed_profile});
    ds.flash = 'Confirmed ' + fresh.name + '. It is now a Dataset in the graph; you can edit its name and description.';
    say('datasets-status', ds.flash);
    inspect(fresh.key, fresh);
    loadDatasets();
  }

  async function saveMetadata(d, fields, button) {
    const body = Object.assign(d.state === 'manual' ? {dataset_id: d.dataset_id} : {scan_id: d.scan_id, root_path: d.root_path}, fields);
    button.disabled = true; say('ds-edit-status', 'Saving…');
    const r = await api('/api/datasets/metadata', {method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(body)});
    button.disabled = false;
    if (!r.ok) { say('ds-edit-status', (r.data && r.data.error) || ('Could not save (' + r.status + ').')); return; }
    const out = r.data;
    const fresh = Object.assign({}, d, {name: out.name || d.name, description: out.description, human_profile: out.human_profile,
      profile: out.human_profile || d.observed_profile, name_is_human: d.name_is_human || 'name' in fields});
    ds.flash = 'Saved ' + fresh.name + '.';
    say('datasets-status', ds.flash);
    inspect(fresh.key, fresh);
    loadDatasets();
  }

  const row = (box, label, value) => { if (value != null && value !== '') { const p = el('div'); p.append(el('strong', label + ': '), document.createTextNode(String(value))); box.append(p); } };

  function renderPanel(d) {
    const box = $('inspector-dataset-panel');
    if (!box) return;
    box.replaceChildren(); box.hidden = false; box.dataset.key = d.key; box.dataset.state = d.state;
    const state = el('p'); state.append(el('span', d.state, {className: 'ds-badge ds-state-' + d.state}), document.createTextNode(' ' + STATE_TITLE[d.state]));
    box.append(state);
    if (d.state !== 'manual') {
      const ev = el('div', null, {className: 'ds-evidence', id: 'ds-evidence'});
      ev.append(el('h3', 'Observed in the scan (read-only evidence)'));
      row(ev, 'Observed profile', d.observed_profile || 'none recognized');
      row(ev, 'Files', d.file_count != null ? num(d.file_count) : 'count pending');
      row(ev, 'Size', d.total_bytes != null ? fmt(d.total_bytes) : 'size pending');
      row(ev, 'Folder', d.root_path);
      row(ev, 'Source', [d.host, d.share].filter(Boolean).join(' / ') || 'scan index');
      row(ev, 'Scan', String(d.scan_id).slice(0, 8) + (d.scan_date ? ' · ' + d.scan_date : ''));
      ev.append(el('div', 'Scan records are never changed from here.', {className: 'ds-meta'}));
      box.append(ev);
    }
    const human = el('div', null, {className: 'ds-human', id: 'ds-human'});
    human.append(el('h3', d.state === 'candidate' ? 'Human metadata' : 'Human-confirmed metadata'));
    if (d.state === 'candidate') {
      human.append(el('p', 'Confirm this Dataset to add it to the graph. Then you can give it a name, a description and a corrected profile. Confirming keeps the scan evidence as it is.'));
      const confirm = el('button', 'Confirm dataset', {type: 'button', id: 'inspector-confirm-dataset'});
      confirm.setAttribute('data-action', 'confirm-dataset');
      confirm.onclick = () => confirmDataset(d, confirm);
      human.append(confirm);
    } else {
      const orig = {name: d.name || '', description: d.description || '', human_profile: d.human_profile || ''};
      const field = (id, label, tag, value, hint) => {
        const l = el('label', label, {htmlFor: id});
        const i = el(tag, null, {id, value: value});
        if (tag === 'textarea') i.rows = 3; else i.type = 'text';
        i.maxLength = tag === 'textarea' ? 4000 : 200;
        if (hint) i.placeholder = hint;
        human.append(l, i); return i;
      };
      const name = field('ds-edit-name', 'Display name', 'input', orig.name);
      const desc = field('ds-edit-description', 'Description', 'textarea', orig.description);
      const prof = field('ds-edit-profile', 'Profile / type (human override)', 'input', orig.human_profile,
        d.observed_profile ? 'Observed: ' + d.observed_profile : 'Optional');
      human.append(el('div', d.state === 'manual' ? 'A profile here is a human label; manual Datasets have no scan evidence.'
        : 'Leave the profile blank to keep the observed profile. A value here is a human override and never replaces the observed profile above.', {className: 'ds-meta'}));
      const save = el('button', 'Save changes', {type: 'button', id: 'ds-edit-save'});
      save.setAttribute('data-action', 'save-dataset');
      save.onclick = () => {
        const fields = {};
        if (name.value.trim() !== orig.name) fields.name = name.value;
        if (desc.value.trim() !== orig.description) fields.description = desc.value;
        if (prof.value.trim() !== orig.human_profile) fields.human_profile = prof.value;
        if (!Object.keys(fields).length) { say('ds-edit-status', 'Nothing changed.'); return; }
        saveMetadata(d, fields, save);
      };
      human.append(save, el('div', '', {id: 'ds-edit-status', className: 'ds-meta', role: 'status'}));
    }
    if (d.confirmed_at) human.append(el('div', 'Confirmed ' + stamp(d.confirmed_at) + (d.confirmed_by ? ' by ' + d.confirmed_by : ''), {className: 'ds-meta'}));
    if (d.human_edited_at) human.append(el('div', 'Last human edit ' + stamp(d.human_edited_at), {className: 'ds-meta'}));
    box.append(human);
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
    const url = new URLSearchParams(location.search);
    const want = url.get('highlight');
    ds.q = url.get('q') || (want ? want.split('|').slice(1).join('|') : '');
    ds.state = ['candidate', 'confirmed', 'manual'].includes(url.get('state')) ? url.get('state') : 'all';
    ds.offset = Math.max(0, parseInt(url.get('offset') || '0', 10) || 0);
    $('datasets-q').value = ds.q; $('datasets-state').value = ds.state;
    $('datasets-filter').onsubmit = e => { e.preventDefault(); search({q: $('datasets-q').value.trim(), offset: 0}); };
    $('datasets-q').oninput = () => { clearTimeout(ds.timer); ds.timer = setTimeout(() => search({q: $('datasets-q').value.trim(), offset: 0}), 350); };
    $('datasets-state').onchange = () => search({state: $('datasets-state').value, offset: 0});
    $('datasets-reset').onclick = () => { $('datasets-q').value = ''; $('datasets-state').value = 'all'; search({q: '', state: 'all', offset: 0}); };
    $('datasets-workspace-toggle').onchange = () => search({offset: 0});
    ['datasets-prev', 'datasets-prev-bottom'].forEach(id => { $(id).onclick = () => search({offset: Math.max(0, ds.offset - PAGE_SIZE)}); });
    ['datasets-next', 'datasets-next-bottom'].forEach(id => { $(id).onclick = () => search({offset: ds.offset + PAGE_SIZE}); });
    document.addEventListener('scidk:inspect', event => {
      const d = event.detail;
      if (d && d.kind === 'scan-dataset' && d.record && d.record.state) renderPanel(d.record);
      else if ($('inspector-dataset-panel')) $('inspector-dataset-panel').hidden = true;
    });
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
