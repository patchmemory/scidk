/* Files & Datasets > Scans: read-only browser over the external scan index (GET only). */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  if (!$('gui-scans')) return;
  const base = window.SCIDK_BASE || '';
  const SERIES_MIN = 3;
  const st = {scans: null, shares: null, scan: null, path: null, next: 0, version: 0, rows: [], sort: null, open: new Set(),
              search: null, cursor: null};
  const fmt = (n) => {
    if (n == null) return '';
    const u = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']; let i = 0, v = Number(n);
    while (v >= 1000 && i < u.length - 1) { v /= 1000; i++; }
    return (i > 1 ? v.toFixed(i >= 4 ? 1 : (v < 10 ? 1 : 0)) : v.toFixed(0)) + ' ' + u[i];
  };
  const num = n => Number(n).toLocaleString();
  const short = n => n == null ? '' : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e4 ? Math.round(n / 1e3) + 'K' : num(n);
  const when = t => t ? new Date(t * 1000).toISOString().slice(0, 16).replace('T', ' ') : '';
  const el = (tag, text, attrs) => { const e = document.createElement(tag); if (text != null) e.textContent = text; Object.assign(e, attrs || {}); return e; };
  const btn = (text, onclick, title) => { const b = el('button', text); b.type = 'button'; b.onclick = onclick; if (title) b.title = title; return b; };
  async function get(url, params) {
    const response = await fetch(base + url + '?' + new URLSearchParams(params || {}));
    let data = {};
    try { data = await response.json(); } catch (e) { /* non-JSON error page */ }
    if (!response.ok) throw new Error(data.error || 'Service unavailable (' + response.status + ')');
    return data;
  }
  function status(text) { $('scans-status').textContent = text; }
  const flags = () => ({system: $('scans-system').checked ? '1' : '0'});

  /* ---- left panel: share -> scans, one total per share ---- */
  function scanButton(s, label) {
    const b = el('button'); b.type = 'button'; b.dataset.scanId = s.id; b.title = s.root;
    b.append(label || s.root);
    const meta = el('span', [s.date, s.files != null ? num(s.files) + ' files' : null, s.bytes ? fmt(s.bytes) : null,
      /^(complete|completed|committed)$/i.test(s.status || '') ? null : s.status].filter(Boolean).join(' · '), {className: 'scan-meta'});
    b.append(meta);
    b.onclick = () => open(s, s.root);
    return b;
  }

  function renderScans() {
    const list = $('scans-list'); list.replaceChildren();
    const byId = new Map(st.scans.map(s => [s.id, s]));
    st.shares.forEach(sh => {
      const primary = byId.get(sh.primary_id);
      const box = el('details', null, {open: !!primary && sh.files > 1000000});
      const sum = el('summary'); sum.append(el('span', sh.share),
        el('span', sh.files != null ? short(sh.files) + ' files' + (sh.date ? ' · ' + sh.date : '') : 'no complete scan', {className: 'meta', title: sh.files != null ? num(sh.files) + ' files' : ''}));
      box.append(sum);
      if (primary) {
        box.append(scanButton(primary));
        if (!sh.primary_is_full_root) box.append(el('p', 'No full-root scan of this share; showing its latest complete scan.', {className: 'meta'}));
      }
      if (sh.older_ids.length) {
        const older = el('details', null, {className: 'older'});
        older.append(el('summary', 'older / partial scans (' + sh.older_ids.length + ')'));
        sh.older_ids.forEach(id => { const s = byId.get(id); if (s) older.append(scanButton(s)); });
        box.append(older);
      }
      list.append(box);
    });
    const empty = st.scans.filter(s => s.files === 0).length;
    if (empty) list.append(el('p', empty + ' empty scans not listed.', {className: 'meta'}));
    markCurrent();
  }
  function markCurrent() {
    document.querySelectorAll('#scans-list button[data-scan-id]').forEach(b =>
      b.setAttribute('aria-current', String(!!st.scan && b.dataset.scanId === st.scan.id)));
  }

  function crumbs() {
    const nav = $('scans-crumbs'); nav.replaceChildren();
    const root = st.scan.root, rel = st.path.startsWith(root) ? st.path.slice(root.length).replace(/^\//, '') : '';
    const sep = root.endsWith('/') || root.endsWith(':') ? '' : '/';
    let acc = root;
    nav.append(btn(root, () => open(st.scan, root)));
    if (rel) rel.split('/').forEach(part => { acc = acc + (acc === root ? sep : '/') + part; const p = acc; nav.append(el('span', ' / '), btn(part, () => open(st.scan, p))); });
  }

  /* ---- listing: numbered series collapsed, sortable on the loaded page ---- */
  function items() {
    const searching = !!st.search;
    const counts = new Map();
    if (!searching) st.rows.forEach(e => { if (e.series) counts.set(e.series, (counts.get(e.series) || 0) + 1); });
    const out = [], groups = new Map();
    st.rows.forEach(e => {
      if (!searching && e.series && counts.get(e.series) >= SERIES_MIN) {
        let g = groups.get(e.series);
        if (!g) { g = {group: e.series, members: [], size: 0, modified: 0, name: e.series}; groups.set(e.series, g); out.push(g); }
        g.members.push(e); g.size += e.size || 0; g.modified = Math.max(g.modified, e.modified || 0);
      } else out.push({row: e, name: e.name, size: e.size || 0, modified: e.modified || 0});
    });
    if (st.sort) {
      const {key, dir} = st.sort;
      out.sort((a, b) => dir * (key === 'name' ? a.name.localeCompare(b.name, undefined, {numeric: true, sensitivity: 'base'}) : (a[key] - b[key])));
    }
    return out;
  }

  /* ---- collection picks: files and folders by (path, host); datasets by reference ---- */
  const hostLabel = () => 'files.db:' + ((st.scan && (st.scan.host || st.scan.share)) || (st.scan && st.scan.id) || 'scan');
  function pickFor(e) {
    const scan = st.scan, host = hostLabel(), isDir = e.type === 'folder';
    return window.CollectionBasket && window.CollectionBasket.checkbox(() => ({
      key: (isDir ? 'folder|' : 'file|') + host + '|' + e.path, kind: isDir ? 'folder' : 'file', label: e.name, title: e.path,
      size: isDir ? null : e.size,
      p: {path: e.path, name: e.name, host, scan_id: scan.id, size: isDir ? null : e.size},
    }), 'Select ' + e.name + ' for the collection');
  }
  function pickDataset(d) {
    const scan = st.scan;
    return window.CollectionBasket && window.CollectionBasket.checkbox(() => ({
      key: 'dataset|' + scan.id + '|' + d.root_path, kind: 'dataset', label: d.root_path.replace(/\/+$/, '').split('/').pop() || d.root_path,
      title: d.root_path, size: d.total_bytes, files: d.file_count, tag: d.pattern_name,
      p: {scan_id: scan.id, root_path: d.root_path, profile: d.pattern_name, file_count: d.file_count, bytes: d.total_bytes},
    }), 'Select dataset ' + d.root_path + ' for the collection');
  }

  function rowFor(e, member) {
    const tr = el('tr', null, {className: member ? 'member' : ''});
    const pick = el('td'); const cb = pickFor(e); if (cb) pick.append(cb);
    const name = el('td'); const isDir = e.type === 'folder';
    const rel = st.search && e.path.startsWith(st.path) ? e.path.slice(st.path.length).replace(/^\//, '').split('/').slice(0, -1).join('/') : '';
    if (isDir) name.append(btn('📁 ' + e.name, () => open(st.scan, e.path), e.path)); else name.append(el('span', '📄 ' + e.name, {title: e.path}));
    if (rel) name.append(el('span', rel, {className: 'where'}));
    tr.append(pick, name, el('td', e.type), el('td', isDir ? '' : fmt(e.size)), el('td', when(e.modified)), el('td', e.extension || ''));
    return tr;
  }

  function renderRows() {
    const body = $('scans-rows'); body.replaceChildren();
    const more = $('scans-more').hidden ? '' : '+';  // groups only cover the rows loaded so far
    items().forEach(it => {
      if (it.row) { body.append(rowFor(it.row)); return; }
      const open_ = st.open.has(it.group);
      const tr = el('tr'); const name = el('td');
      name.append(btn((open_ ? '▾ ' : '▸ ') + '📄 ' + it.group + ' · ' + num(it.members.length) + more + ' files · ' + fmt(it.size) + (more ? '+' : ''),
        () => { open_ ? st.open.delete(it.group) : st.open.add(it.group); renderRows(); }, 'Show or hide the ' + it.members.length + ' files in this series'));
      name.firstChild.setAttribute('aria-expanded', String(open_));
      tr.append(el('td'), name, el('td', 'series'), el('td', fmt(it.size)), el('td', when(it.modified)), el('td'));
      body.append(tr);
      if (open_) it.members.forEach(e => body.append(rowFor(e, true)));
    });
    document.querySelectorAll('#scans-table th[aria-sort]').forEach(th => {
      const k = th.querySelector('button').dataset.sort;
      th.setAttribute('aria-sort', st.sort && st.sort.key === k ? (st.sort.dir > 0 ? 'ascending' : 'descending') : 'none');
    });
  }
  document.querySelectorAll('#scans-table [data-sort]').forEach(b => {
    b.onclick = () => {
      const key = b.dataset.sort;
      st.sort = st.sort && st.sort.key === key ? (st.sort.dir > 0 ? {key, dir: -1} : null) : {key, dir: 1};
      renderRows();
    };
  });

  /* ---- opening a folder ---- */
  async function open(scan, path) {
    const version = ++st.version; st.scan = scan; st.path = path; st.next = 0; st.rows = []; st.search = null; st.cursor = null; st.open.clear();
    $('scans-rows').replaceChildren(); $('scans-more').hidden = true; $('scans-clear').hidden = true; $('scans-note').textContent = '';
    $('scans-datasets').textContent = 'Loading…'; markCurrent();
    crumbs(); status('Loading ' + path + '…');
    try {
      const [browse, sets] = await Promise.all([
        get('/api/external-index/browse', Object.assign({scan_id: scan.id, path}, flags())),
        get('/api/external-index/datasets', Object.assign({scan_id: scan.id, path, workspace: $('scans-workspace').checked ? '1' : '0'}, flags())),
      ]);
      if (version !== st.version) return;
      st.rows = browse.entries; st.next = browse.next_offset; $('scans-more').hidden = !browse.has_more; renderRows();
      status(browse.entries.length ? 'Read-only index · ' + path : 'Read-only index · ' + path + ' (empty folder)');
      renderDatasets(sets);
    } catch (error) { if (version === st.version) { status(error.message); $('scans-datasets').textContent = ''; } }
  }

  /* ---- recognized datasets: profile · files · size · confidence, then the folder name (wrapping) ---- */
  function renderDatasets(sets) {
    const box = $('scans-datasets'); box.replaceChildren();
    if (!sets.datasets.length) { box.textContent = 'No recognized datasets in this folder.'; return; }
    sets.datasets.forEach(d => {
      const where = d.root_path.slice(st.path.length).replace(/^\//, '') || '(this folder)';
      const count = d.file_count != null ? (d.file_count_is_minimum ? '≥ ' : '') + num(d.file_count) + ' files' : 'count pending';
      const size = d.total_bytes != null ? fmt(d.total_bytes) : 'size pending';
      const conf = d.confidence != null ? 'confidence ' + Number(d.confidence).toFixed(2) : null;
      const b = el('button'); b.type = 'button'; b.title = d.root_path + (d.status ? ' · ' + d.status : '');
      b.append(el('div', [d.pattern_name, count, size, conf].filter(Boolean).join(' · '), {className: 'ds-line'}), el('div', where, {className: 'ds-name'}));
      b.onclick = () => open(st.scan, d.root_path);
      const line = el('div', null, {className: 'ds-pick'}); const dcb = pickDataset(d);
      if (dcb) line.append(dcb);
      line.append(b); box.append(line);
    });
    if (sets.has_more) box.append(el('p', 'Showing the first ' + sets.datasets.length + '. Open a subfolder to narrow.'));
  }

  /* ---- search: this folder, or this folder and subfolders; 200 per page, 1 s budget ---- */
  async function runSearch(more) {
    if (!st.scan) { $('scans-note').textContent = 'Choose a scan and a folder first.'; return; }
    const q = $('scans-q').value.trim();
    if (!q) { $('scans-note').textContent = 'Enter a name to search for.'; return; }
    const version = more ? st.version : ++st.version;
    if (!more) { st.rows = []; st.cursor = null; st.next = 0; st.open.clear(); $('scans-rows').replaceChildren(); }
    st.search = {q}; $('scans-clear').hidden = false; $('scans-more').hidden = true;
    $('scans-note').textContent = 'Searching…';
    try {
      const r = await get('/api/external-index/search', Object.assign({scan_id: st.scan.id, path: st.path, q, mode: $('scans-mode').value,
        scope: $('scans-scope').value, cursor: more ? (st.cursor || '') : ''}, flags()));
      if (version !== st.version) return;
      st.rows = st.rows.concat(r.entries); st.cursor = r.next_cursor; $('scans-more').hidden = !r.has_more; renderRows();
      $('scans-note').textContent = r.message || (num(st.rows.length) + ' match' + (st.rows.length === 1 ? '' : 'es') + ' for "' + q + '" in ' +
        (r.scope === 'subtree' ? 'this folder and subfolders' : 'this folder') + (r.has_more ? ' (more available)' : ''));
    } catch (error) { if (version === st.version) $('scans-note').textContent = error.message; }
  }
  $('scans-add').onclick = () => {
    if (!window.CollectionBasket) return;
    const added = window.CollectionBasket.addChecked($('gui-scans'));
    $('scans-note').textContent = added ? added + ' added to the collection.' : 'Check rows or datasets first (or they are already in the collection).';
  };
  $('scans-search').onsubmit = ev => { ev.preventDefault(); runSearch(false); };
  $('scans-clear').onclick = () => { $('scans-q').value = ''; if (st.scan) open(st.scan, st.path); };

  $('scans-more').onclick = async () => {
    if (st.search) { runSearch(true); return; }
    const version = st.version;
    try {
      const browse = await get('/api/external-index/browse', Object.assign({scan_id: st.scan.id, path: st.path, offset: st.next}, flags()));
      if (version !== st.version) return;
      st.rows = st.rows.concat(browse.entries); st.next = browse.next_offset; $('scans-more').hidden = !browse.has_more; renderRows();
    } catch (error) { status(error.message); }
  };

  $('scans-system').onchange = () => { if (!st.scan) return; st.search ? runSearch(false) : open(st.scan, st.path); if (st.search) refreshDatasets(); };
  $('scans-workspace').onchange = () => { if (st.scan) refreshDatasets(); };
  async function refreshDatasets() {
    const version = st.version;
    try {
      const sets = await get('/api/external-index/datasets', Object.assign({scan_id: st.scan.id, path: st.path, workspace: $('scans-workspace').checked ? '1' : '0'}, flags()));
      if (version === st.version) renderDatasets(sets);
    } catch (error) { $('scans-datasets').textContent = error.message; }
  }

  $('gui-scans-tab').addEventListener('click', async () => {
    if (st.scans) return;
    status('Loading scans…');
    try {
      const data = await get('/api/external-index/scans');
      st.scans = data.scans; st.shares = data.shares;
      renderScans(); status('Read-only index · choose a share.');
    } catch (error) { status(error.message); }
  });
})();
