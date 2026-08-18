/**
 * scan_panel.js — Scan drawer (Scan + History tabs)
 * Exposes: window.ScanPanel
 *   .open()              — open drawer on Scan tab
 *   .openHistory(path)   — open drawer on History tab, load path history
 *   .startScan()         — start a scan with current settings
 *   .rescan()            — rescan with same config as active scan
 */
;(function(global) {
  'use strict';

  const BASE = () => (typeof window.SCIDK_BASE !== 'undefined') ? window.SCIDK_BASE : '';
  function esc(s) { return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function setStatus(msg, ok=null) {
    const el = document.getElementById('scan-start-status');
    if (!el) return;
    el.innerHTML = ok === null ? `<span class="text-muted">${esc(msg)}</span>`
      : ok ? `<span class="text-success">${esc(msg)}</span>`
           : `<span class="text-danger">${esc(msg)}</span>`;
  }

  function _setTab(name) {
    document.querySelectorAll('[data-scan-tab]').forEach(t => t.classList.toggle('active', t.dataset.scanTab === name));
    document.querySelectorAll('#scan-drawer .sharing-tab-panel').forEach(p => p.classList.toggle('active', p.id === `scan-tab-${name}`));
  }

  function open() {
    _updateScope();
    _setTab('scan');
    window.Drawers.open('scan-drawer');
  }

  function openHistory(path) {
    _setTab('history');
    window.Drawers.open('scan-drawer');
    loadHistory(path || (typeof currentPath !== 'undefined' ? currentPath : ''));
  }

  function _updateScope() {
    const el = document.getElementById('scan-drawer-scope');
    if (!el) return;
    const path = typeof currentPath !== 'undefined' ? currentPath : '';
    const server = typeof currentServer !== 'undefined' ? currentServer : '';
    el.textContent = [server, path].filter(Boolean).join('/') || 'no drive selected';
  }

  async function startScan() {
    const scope  = document.getElementById('scan-scope-sel')?.value || 'folder';
    const depth  = document.getElementById('scan-depth-sel')?.value || '0';
    const interp = document.getElementById('scan-opt-interpret')?.checked;
    const fast   = document.getElementById('scan-opt-fast-list')?.checked;
    const commit = document.getElementById('scan-opt-commit')?.checked;
    const pats   = document.getElementById('scan-patterns')?.value.trim() || '';

    if (typeof currentServer === 'undefined' || !currentServer) {
      setStatus('No drive selected', false); return;
    }

    const btn = document.getElementById('scan-start-btn');
    if (btn) btn.disabled = true;
    setStatus('Starting…');

    try {
      const body = {
        type: 'scan',
        provider_id: currentServer,
        root_id: typeof currentRoot !== 'undefined' ? currentRoot : currentServer,
        path: typeof currentPath !== 'undefined' ? currentPath : '',
        recursive: depth === '0',
        run_interpreters: interp,
        fast_list: fast,
        commit_after: commit,
        patterns: pats ? pats.split(',').map(s => s.trim()).filter(Boolean) : [],
      };
      if (scope === 'selected' && typeof selItems !== 'undefined' && selItems.size) {
        body.selected_paths = [...selItems];
      }
      const r = await fetch(BASE() + '/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (r.status === 202) {
        setStatus('Scan started', true);
        if (typeof startTaskPoll === 'function') startTaskPoll();
        setTimeout(() => window.Drawers.close(), 1500);
      } else {
        const d = await r.json().catch(() => ({}));
        setStatus(d.error || `Error ${r.status}`, false);
      }
    } catch (e) { setStatus(e.message, false); }
    finally { if (btn) btn.disabled = false; }
  }

  async function loadHistory(path) {
    const el = document.getElementById('scan-history-list');
    if (!el) return;
    el.innerHTML = '<div class="small text-muted">Loading…</div>';
    try {
      const r = await fetch(BASE() + '/api/scans/history?path=' + encodeURIComponent(path));
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      const events = d.events || [];
      if (!events.length) { el.innerHTML = '<div class="small text-muted">No history for this path.</div>'; return; }
      const dotClass = { interpreted:'interp', scanned:'scan', changed:'change', first_seen:'scan' };
      el.innerHTML = '<div class="tl">' + events.map(ev =>
        `<div class="tl-item">
          <div class="tl-dot ${dotClass[ev.type] || 'scan'}"></div>
          <div>
            <div class="tl-label">${esc(_label(ev.type))}</div>
            <div class="tl-meta">${ev.timestamp ? new Date(ev.timestamp*1000).toLocaleString() : ''}${ev.interpreter ? ' · ' + esc(ev.interpreter) + (ev.version ? ' v' + esc(ev.version) : '') : ''}${ev.scan_id ? ' · scan #' + esc(ev.scan_id.slice(0,6)) : ''}</div>
            ${ev.detail ? `<div class="tl-detail">${esc(ev.detail)}</div>` : ''}
          </div>
        </div>`
      ).join('') + '</div>';
    } catch (e) { el.innerHTML = `<div class="small text-danger">Failed: ${esc(e.message)}</div>`; }
  }

  function _label(type) {
    return { interpreted:'Interpreted', scanned:'Scanned', changed:'File changed', first_seen:'First scanned' }[type] || type;
  }

  async function rescan() {
    if (typeof activeScanId === 'undefined' || !activeScanId) {
      alert('No active scan selected.'); return;
    }
    if (!confirm('Re-scan with same config?')) return;
    try {
      const r = await fetch(BASE() + `/api/scans/${activeScanId}/rescan`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }
      });
      if (r.ok) {
        setStatus('Rescan started', true);
        if (typeof startTaskPoll === 'function') startTaskPoll();
      } else { setStatus('Rescan failed', false); }
    } catch (e) { setStatus(e.message, false); }
  }

  // Tab switching
  document.addEventListener('click', e => {
    const tab = e.target.closest('[data-scan-tab]');
    if (!tab) return;
    _setTab(tab.dataset.scanTab);
    if (tab.dataset.scanTab === 'history') {
      loadHistory(typeof currentPath !== 'undefined' ? currentPath : '');
    }
  });

  // History button in sidebar header
  document.getElementById('history-btn')?.addEventListener('click', () => openHistory());

  global.ScanPanel = { open, openHistory, startScan, rescan, loadHistory };

})(window);
