/**
 * share_panel.js — Share drawer (RO-Crate + DMS Plan tabs)
 * Exposes: window.SharePanel
 *   .open()              — open on current tab
 *   .setTab(name)        — 'rocrate' | 'dms'
 *   .buildRocrate(clear) — build and optionally clear collection
 *   .openDMSBuilder()    — close share, open DMS full drawer
 *   .quickDraft()        — generate quick DMS draft
 */
;(function(global) {
  'use strict';

  const BASE = () => (typeof window.SCIDK_BASE !== 'undefined') ? window.SCIDK_BASE : '';
  function esc(s) { return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  let _rocScope = 'collection';
  let _dmsScope = 'collection';
  let _dmsQrUrl = null;

  function open() {
    _refreshScopeNotes();
    window.Drawers.open('sharing-drawer');
  }

  function setTab(name) {
    document.querySelectorAll('[data-share-tab]').forEach(t => t.classList.toggle('active', t.dataset.shareTab === name));
    document.querySelectorAll('#sharing-drawer .sharing-tab-panel').forEach(p => p.classList.toggle('active', p.id === `share-tab-${name}`));
    _refreshScopeNotes();
  }

  function _scopeItems(scope) {
    if (scope === 'collection') {
      const items = typeof Collection !== 'undefined' ? Collection.items() : [];
      return { label: `Collection · ${items.length} files`, items: items.map(f => f.name).join(', ') || '—' };
    }
    if (scope === 'selection') {
      const sel = typeof selItems !== 'undefined' ? [...selItems] : [];
      return { label: `Selection · ${sel.length} files`, items: sel.map(id => id.split('/').pop()).join(', ') || '—' };
    }
    if (scope === 'whole') return { label: 'Whole graph', items: 'All data indexed in the knowledge graph' };
    return { label: 'From graph', items: 'Search for Datasets, Folders, or Files above' };
  }

  function _refreshScopeNotes() {
    const roc = _scopeItems(_rocScope);
    const dms = _scopeItems(_dmsScope);
    const rNote = document.getElementById('roc-scope-note');
    if (rNote) { rNote.querySelector('.sn-label').textContent = roc.label; rNote.querySelector('.sn-items').textContent = roc.items; rNote.classList.toggle('empty', typeof Collection !== 'undefined' && _rocScope === 'collection' && !Collection.count()); }
    const dNote = document.getElementById('dms-scope-note');
    if (dNote) { dNote.querySelector('.sn-label').textContent = dms.label; dNote.querySelector('.sn-items').textContent = dms.items; }
    document.getElementById('roc-graph-search')?.style && (document.getElementById('roc-graph-search').style.display = _rocScope === 'graph' ? '' : 'none');
  }

  // Scope tab clicks
  document.addEventListener('click', e => {
    const btn = e.target.closest('[data-roc-scope]');
    if (btn) {
      _rocScope = btn.dataset.rocScope;
      document.querySelectorAll('[data-roc-scope]').forEach(b => b.classList.toggle('active', b === btn));
      _refreshScopeNotes(); return;
    }
    const dbtn = e.target.closest('[data-dms-scope]');
    if (dbtn) {
      _dmsScope = dbtn.dataset.dmsScope;
      document.querySelectorAll('[data-dms-scope]').forEach(b => b.classList.toggle('active', b === dbtn));
      _refreshScopeNotes(); return;
    }
    const tab = e.target.closest('[data-share-tab]');
    if (tab) { setTab(tab.dataset.shareTab); }
  });

  // License "Other"
  document.getElementById('rocrate-license')?.addEventListener('change', e => {
    const other = document.getElementById('rocrate-license-other');
    if (other) other.style.display = e.target.value === '__other__' ? '' : 'none';
  });

  async function buildRocrate(clearAfter=false) {
    const paths = _resolveScope(_rocScope);
    if (!paths.length) { alert('No files in scope. Select files or add to Collection first.'); return; }
    const lic = document.getElementById('rocrate-license')?.value === '__other__'
      ? (document.getElementById('rocrate-license-other')?.value || 'Custom')
      : (document.getElementById('rocrate-license')?.value || 'CC BY 4.0');
    const btn = document.getElementById('rocrate-build-btn');
    if (btn) btn.disabled = true;
    const res = document.getElementById('rocrate-result');
    if (res) res.innerHTML = '<span class="text-muted">Building…</span>';
    try {
      const r = await fetch(BASE() + '/api/rocrate/build', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paths,
          name: document.getElementById('rocrate-name')?.value.trim() || 'SciDK collection',
          license: lic,
          include_files: document.getElementById('rocrate-include-files')?.checked ?? true,
        })
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.status === 'ok') {
        if (res) res.innerHTML = `<span class="text-success">Built ${d.entities} entities.</span> <a href="${BASE()}${d.download_url}" download="${d.filename}">Download ${d.filename}</a>`;
        if (clearAfter && typeof Collection !== 'undefined') Collection.clear(true);
      } else { if (res) res.innerHTML = `<span class="text-danger">${esc(d.error || 'Build failed')}</span>`; }
    } catch (e) { if (res) res.innerHTML = `<span class="text-danger">${esc(e.message)}</span>`; }
    finally { if (btn) btn.disabled = false; }
  }

  function openDMSBuilder() {
    window.Drawers.close();
    setTimeout(() => { if (typeof DMS !== 'undefined') DMS.open(); }, 220);
  }

  async function quickDraft() {
    const btn = document.querySelector('#share-tab-dms .btn-outline-primary');
    const status = document.getElementById('dms-quick-status');
    const result = document.getElementById('dms-quick-result');
    const phi    = document.getElementById('dms-quick-phi');
    if (btn) btn.disabled = true;
    if (result) result.style.display = 'none';
    if (phi)    phi.style.display = 'none';
    if (status) status.textContent = 'Reading the graph…';
    try {
      const r = await fetch(BASE() + '/api/plugins/nih_dms/draft_plan?format=json');
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.status === 'ok') {
        const ta = document.getElementById('dms-quick-textarea');
        if (ta) ta.value = d.markdown || '';
        if (d.summary?.phi_detected && phi) {
          phi.textContent = '⚠ Potentially identifiable data detected — see Element 1 and 5 in the draft.';
          phi.style.display = '';
        }
        if (status) status.textContent = 'Draft generated from the live graph.';
        if (_dmsQrUrl) URL.revokeObjectURL(_dmsQrUrl);
        _dmsQrUrl = URL.createObjectURL(new Blob([d.markdown || ''], {type:'text/markdown'}));
        const dl = document.getElementById('dms-quick-download');
        if (dl) { dl.href = _dmsQrUrl; dl.download = d.filename || 'nih-dms-plan-draft.md'; }
        if (result) result.style.display = '';
      } else {
        if (status) status.innerHTML = `<span class="text-danger">${esc(d.error || `Error ${r.status}`)}</span>`;
      }
    } catch (e) { if (status) status.innerHTML = `<span class="text-danger">${esc(e.message)}</span>`; }
    finally { if (btn) btn.disabled = false; }
  }

  function _resolveScope(scope) {
    if (scope === 'collection' && typeof Collection !== 'undefined') {
      return Collection.items().map(f => (f.path ? f.path + '/' : '') + f.name);
    }
    if (scope === 'selection' && typeof selItems !== 'undefined') return [...selItems];
    return [];
  }

  // Copy button for quick draft
  document.getElementById('dms-quick-copy')?.addEventListener('click', async () => {
    const ta = document.getElementById('dms-quick-textarea');
    const btn = document.getElementById('dms-quick-copy');
    try { await navigator.clipboard.writeText(ta?.value || ''); if (btn) btn.textContent = 'Copied'; }
    catch { if (ta) ta.select(); if (btn) btn.textContent = 'Ctrl+C'; }
    setTimeout(() => { if (btn) btn.textContent = 'Copy'; }, 2000);
  });

  // Toolbar button
  document.getElementById('sharing-btn')?.addEventListener('click', () => { _refreshScopeNotes(); open(); });

  global.SharePanel = { open, setTab, buildRocrate, openDMSBuilder, quickDraft };

})(window);
