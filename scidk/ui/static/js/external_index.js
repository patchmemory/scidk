/* Files & Datasets > Scans: read-only browser over the external scan index (GET only). */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  if (!$('gui-scans')) return;
  const base = window.SCIDK_BASE || '';
  const st = {scans: null, scan: null, path: null, next: 0, version: 0};
  const fmt = (n) => {
    if (n == null) return '';
    const u = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']; let i = 0, v = Number(n);
    while (v >= 1000 && i < u.length - 1) { v /= 1000; i++; }
    return (i > 1 ? v.toFixed(i >= 4 ? 1 : 0) : v.toFixed(0)) + ' ' + u[i];
  };
  const num = n => n == null ? '–' : Number(n).toLocaleString();
  const when = t => t ? new Date(t * 1000).toISOString().slice(0, 16).replace('T', ' ') : '';
  const el = (tag, text, attrs) => { const e = document.createElement(tag); if (text != null) e.textContent = text; Object.assign(e, attrs || {}); return e; };
  async function get(url, params) {
    const response = await fetch(base + url + '?' + new URLSearchParams(params || {}));
    let data = {};
    try { data = await response.json(); } catch (e) { /* non-JSON error page */ }
    if (!response.ok) throw new Error(data.error || 'Service unavailable (' + response.status + ')');
    return data;
  }
  function status(text) { $('scans-status').textContent = text; }

  function renderScans() {
    const list = $('scans-list'); list.replaceChildren();
    const groups = new Map(); let hidden = 0;
    for (const s of st.scans) {
      if (s.files === 0) { hidden++; continue; }
      if (!groups.has(s.share)) groups.set(s.share, []);
      groups.get(s.share).push(s);
    }
    const total = g => g.reduce((a, s) => a + (s.files || 0), 0);
    [...groups.entries()].sort((a, b) => total(b[1]) - total(a[1])).forEach(([share, scans]) => {
      scans.sort((a, b) => (b.files || 0) - (a.files || 0));
      const bytes = scans.reduce((a, s) => a + (s.bytes || 0), 0);
      const box = el('details', null, {open: scans.some(s => s.files > 1000000)});
      box.append(el('summary', share + ' · ' + num(total(scans)) + ' files' + (bytes ? ' · ' + fmt(bytes) : '')));
      scans.forEach(s => {
        const b = el('button', (s.host ? s.host + ' ' : '') + s.root + ' — ' + num(s.files) + ' files' + (s.bytes ? ', ' + fmt(s.bytes) : '') + ' (' + s.status + ')');
        b.type = 'button'; b.style.display = 'block'; b.style.textAlign = 'left'; b.style.margin = '2px 0';
        b.dataset.scanId = s.id; b.onclick = () => open(s, s.root);
        box.append(b);
      });
      list.append(box);
    });
    if (hidden) list.append(el('p', hidden + ' empty scans not listed.'));
  }

  function crumbs() {
    const nav = $('scans-crumbs'); nav.replaceChildren();
    const root = st.scan.root, rel = st.path.startsWith(root) ? st.path.slice(root.length).replace(/^\//, '') : '';
    const sep = root.endsWith('/') || root.endsWith(':') ? '' : '/';
    let acc = root;
    const link = (label, path) => { const b = el('button', label); b.type = 'button'; b.onclick = () => open(st.scan, path); return b; };
    nav.append(link(root, root));
    if (rel) rel.split('/').forEach(part => { acc = acc + (acc === root ? sep : '/') + part; nav.append(el('span', ' / '), link(part, acc)); });
  }

  function addRows(entries) {
    const rows = $('scans-rows');
    entries.forEach(e => {
      const tr = el('tr');
      const name = el('td'); const isDir = e.type === 'folder';
      if (isDir) { const b = el('button', '📁 ' + e.name); b.type = 'button'; b.onclick = () => open(st.scan, e.path); name.append(b); }
      else name.textContent = '📄 ' + e.name;
      tr.append(name, el('td', e.type), el('td', isDir ? '' : fmt(e.size)), el('td', when(e.modified)), el('td', e.extension || ''));
      rows.append(tr);
    });
  }

  async function open(scan, path) {
    const version = ++st.version; st.scan = scan; st.path = path; st.next = 0;
    $('scans-rows').replaceChildren(); $('scans-more').hidden = true; $('scans-datasets').textContent = 'Loading…';
    crumbs(); status('Loading ' + path + '…');
    try {
      const [browse, sets] = await Promise.all([
        get('/api/external-index/browse', {scan_id: scan.id, path}),
        get('/api/external-index/datasets', {scan_id: scan.id, path}),
      ]);
      if (version !== st.version) return;
      addRows(browse.entries); st.next = browse.next_offset; $('scans-more').hidden = !browse.has_more;
      status(browse.entries.length ? 'Read-only index · ' + path : 'Read-only index · ' + path + ' (empty folder)');
      renderDatasets(sets);
    } catch (error) { if (version === st.version) { status(error.message); $('scans-datasets').textContent = ''; } }
  }

  function renderDatasets(sets) {
    const box = $('scans-datasets'); box.replaceChildren();
    if (!sets.datasets.length) { box.textContent = 'No recognized datasets in this folder.'; return; }
    sets.datasets.forEach(d => {
      const where = d.root_path.slice(st.path.length).replace(/^\//, '') || '(this folder)';
      const b = el('button', d.pattern_name + ' — ' + num(d.file_count) + ' files, ' + fmt(d.total_bytes) + ' · ' + d.status +
        (d.confidence != null ? ' (' + Number(d.confidence).toFixed(2) + ')' : '') + '\n' + where);
      b.type = 'button'; b.style.display = 'block'; b.style.textAlign = 'left'; b.style.margin = '3px 0'; b.style.whiteSpace = 'pre-wrap';
      b.title = d.root_path; b.onclick = () => open(st.scan, d.root_path);
      box.append(b);
    });
    if (sets.has_more) box.append(el('p', 'Showing the first ' + sets.datasets.length + '. Open a subfolder to narrow.'));
  }

  $('scans-more').onclick = async () => {
    const version = st.version;
    try {
      const browse = await get('/api/external-index/browse', {scan_id: st.scan.id, path: st.path, offset: st.next});
      if (version !== st.version) return;
      addRows(browse.entries); st.next = browse.next_offset; $('scans-more').hidden = !browse.has_more;
    } catch (error) { status(error.message); }
  };

  $('gui-scans-tab').addEventListener('click', async () => {
    if (st.scans) return;
    status('Loading scans…');
    try {
      st.scans = (await get('/api/external-index/scans')).scans;
      renderScans(); status('Read-only index · choose a scan.');
    } catch (error) { status(error.message); }
  });
})();
