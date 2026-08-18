/**
 * add_drive.js — Add Drive drawer (Local / Rclone tabs)
 * Exposes: window.AddDrive
 *   .open()             — open the drawer and load existing remotes
 *   .pickLocalPath(p)   — fill local path input
 *   .addLocal()         — POST /api/drives (local_fs)
 *   .addRclone()        — POST /api/drives (rclone)
 *   .onTypeChange()     — show/hide type-specific fields
 *   .authorize()        — OAuth flow
 *   .testConnection()   — test a named remote
 */
;(function(global) {
  'use strict';

  const BASE = () => (typeof window.SCIDK_BASE !== 'undefined') ? window.SCIDK_BASE : '';
  function esc(s) { return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function setStatus(elId, msg, ok=null) {
    const el = document.getElementById(elId); if (!el) return;
    el.innerHTML = ok === null ? `<span class="text-muted">${esc(msg)}</span>`
      : ok ? `<span class="text-success">${esc(msg)}</span>`
           : `<span class="text-danger">${esc(msg)}</span>`;
  }

  const RCLONE_FIELDS = {
    s3:      [['env_auth','Use environment auth (IAM)','checkbox'],['access_key_id','Access Key ID','text'],['secret_access_key','Secret Access Key','password'],['region','Region','text',{placeholder:'e.g. us-east-1'}],['endpoint','Endpoint (S3-compatible, optional)','text',{placeholder:'leave blank for AWS'}]],
    sftp:    [['host','Host','text',{placeholder:'sftp.example.com'}],['user','Username','text'],['pass','Password','password'],['port','Port','text',{placeholder:'22'}],['key_file','Private key path (optional)','text']],
    dropbox:[], drive:[], onedrive:[], box:[],
    other:   [['config','Rclone config block (paste from rclone config show)','textarea']],
  };
  const OAUTH_TYPES = new Set(['dropbox','drive','onedrive','box']);

  function open() {
    window.Drawers.open('add-drive-drawer');
    loadExisting();
  }

  function pickLocalPath(path) {
    const inp = document.getElementById('local-path');
    if (inp) inp.value = path;
    const lbl = document.getElementById('local-label');
    if (lbl && !lbl.value) lbl.value = path.split('/').filter(Boolean).pop() || path;
  }

  // Local browse button
  document.getElementById('local-browse-btn')?.addEventListener('click', async () => {
    const browser = document.getElementById('local-path-browser');
    const current = (document.getElementById('local-path')?.value || '/').trim();
    if (!browser) return;
    browser.style.display = 'block';
    browser.innerHTML = '<div class="small text-muted p-2">Loading…</div>';
    try {
      const r = await fetch(BASE() + '/api/drives/browse-local?path=' + encodeURIComponent(current));
      const d = await r.json();
      const entries = (d.entries || []).filter(e => e.type === 'dir');
      if (!entries.length) { browser.innerHTML = '<div class="small text-muted p-2">Empty or inaccessible</div>'; return; }
      browser.innerHTML = entries.map(e =>
        `<div class="drive-path-row d-flex align-items-center gap-2 p-1 rounded" style="cursor:pointer;font-size:11px;" data-path="${esc(e.path)}">
          <i class="ti ti-folder" aria-hidden="true" style="font-size:13px;color:#6c757d;flex-shrink:0;"></i>
          <span style="font-family:ui-monospace,monospace;">${esc(e.name)}</span>
          ${e.readable ? '' : '<span class="small text-muted">(no access)</span>'}
        </div>`
      ).join('');
      browser.querySelectorAll('.drive-path-row[data-path]').forEach(row => {
        row.addEventListener('mouseover', () => row.style.background = '#f0f5ff');
        row.addEventListener('mouseout',  () => row.style.background = '');
        row.addEventListener('click', () => {
          const inp = document.getElementById('local-path');
          if (inp) inp.value = row.dataset.path;
          const lbl = document.getElementById('local-label');
          if (lbl && !lbl.value) lbl.value = row.dataset.path.split('/').filter(Boolean).pop() || row.dataset.path;
          browser.style.display = 'none';
        });
      });
    } catch (e) { browser.innerHTML = `<div class="small text-danger p-2">Failed: ${esc(e.message)}</div>`; }
  });

  async function addLocal() {
    const path  = document.getElementById('local-path')?.value.trim() || '';
    const label = document.getElementById('local-label')?.value.trim() || path;
    if (!path) { setStatus('local-status', 'Path is required', false); return; }
    try {
      const r = await fetch(BASE() + '/api/drives', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'local_fs', path, label })
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok) {
        setStatus('local-status', `✓ Drive added — ${label}`, true);
        setTimeout(() => { window.Drawers.close(); if (typeof loadServers === 'function') loadServers(); }, 1200);
      } else { setStatus('local-status', d.error || `Error ${r.status}`, false); }
    } catch (e) { setStatus('local-status', e.message, false); }
  }

  function onTypeChange() {
    const type = document.getElementById('rclone-type')?.value || '';
    const fields = document.getElementById('rclone-fields');
    const oauth  = document.getElementById('rclone-oauth-block');
    if (!fields) return;
    const defs = RCLONE_FIELDS[type] || [];
    fields.innerHTML = defs.map(([id, label, inputType, attrs={}]) => {
      const ph = attrs.placeholder ? `placeholder="${esc(attrs.placeholder)}"` : '';
      if (inputType === 'checkbox')
        return `<div class="form-check mb-2"><input class="form-check-input" type="checkbox" id="rcl-${id}"><label class="form-check-label small" for="rcl-${id}">${esc(label)}</label></div>`;
      if (inputType === 'textarea')
        return `<div class="mb-2"><label class="form-label small fw-semibold">${esc(label)}</label><textarea class="form-control form-control-sm" id="rcl-${id}" rows="4" style="font-family:ui-monospace,monospace;font-size:11px;"></textarea></div>`;
      return `<div class="mb-2"><label class="form-label small fw-semibold" for="rcl-${id}">${esc(label)}</label><input type="${inputType}" class="form-control form-control-sm" id="rcl-${id}" ${ph} style="font-size:12px;"></div>`;
    }).join('');
    if (oauth) oauth.style.display = OAUTH_TYPES.has(type) ? 'block' : 'none';
  }

  // The server cannot run the OAuth handshake on the user's behalf — rclone
  // binds the callback listener to loopback on whichever machine starts it. The
  // endpoint answers with the command to run instead, which this shows.
  async function authorize() {
    const type = document.getElementById('rclone-type')?.value || '';
    const name = document.getElementById('rclone-name')?.value.trim() || type;
    const el = document.getElementById('rclone-auth-status');
    if (el) el.textContent = 'Checking…';
    try {
      const r = await fetch(BASE() + '/api/drives/rclone/oauth', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type, name })
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok) {
        if (el) el.innerHTML = `<span class="text-success">✓ Authorized — ${esc(d.remote || name)}</span>`;
        return;
      }
      if (el) {
        el.innerHTML = d.manual_command
          ? `Run on the SciDK host: <code style="font-size:11px;">${esc(d.manual_command)}</code>`
          : `<span class="text-danger">${esc(d.error || 'Authorization failed')}</span>`;
      }
      pollForRemote(name);
    } catch (e) { if (el) el.innerHTML = `<span class="text-danger">${esc(e.message)}</span>`; }
  }

  // Watch for the remote appearing in rclone's config while the user runs the
  // command in a terminal. Bounded, so a drawer left open does not poll forever.
  function pollForRemote(name, attempts = 40) {
    if (!name || attempts <= 0) return;
    setTimeout(async () => {
      try {
        const r = await fetch(BASE() + '/api/drives/rclone/oauth/status?name=' + encodeURIComponent(name));
        const d = await r.json().catch(() => ({}));
        if (d.status === 'ok') {
          const el = document.getElementById('rclone-auth-status');
          if (el) el.innerHTML = `<span class="text-success">✓ Remote "${esc(name)}" found — click Add Remote</span>`;
          return;
        }
      } catch { /* a transient failure is not a reason to stop watching */ }
      pollForRemote(name, attempts - 1);
    }, 3000);
  }

  async function addRclone() {
    const type = document.getElementById('rclone-type')?.value || '';
    const name = document.getElementById('rclone-name')?.value.trim() || '';
    if (!type) { setStatus('rclone-status', 'Choose a remote type', false); return; }
    if (!name) { setStatus('rclone-status', 'Remote name is required', false); return; }
    const params = {};
    (RCLONE_FIELDS[type] || []).forEach(([id,,inputType]) => {
      const el = document.getElementById('rcl-' + id);
      if (el) params[id] = inputType === 'checkbox' ? el.checked : el.value;
    });
    try {
      const r = await fetch(BASE() + '/api/drives', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'rclone', remote_type: type, name, params })
      });
      const d = await r.json().catch(() => ({}));
      if (r.ok) {
        setStatus('rclone-status', `✓ Remote "${name}" added`, true);
        setTimeout(() => { window.Drawers.close(); if (typeof loadServers === 'function') loadServers(); }, 1200);
      } else { setStatus('rclone-status', d.error || `Error ${r.status}`, false); }
    } catch (e) { setStatus('rclone-status', e.message, false); }
  }

  async function testConnection() {
    const name = document.getElementById('rclone-name')?.value.trim() || '';
    if (!name) { setStatus('rclone-status', 'Enter a remote name first', false); return; }
    setStatus('rclone-status', 'Testing…');
    try {
      const r = await fetch(BASE() + '/api/drives/test?name=' + encodeURIComponent(name));
      const d = await r.json().catch(() => ({}));
      setStatus('rclone-status', r.ok ? `✓ Connected — ${d.message || 'OK'}` : `✗ ${d.error || 'Connection failed'}`, r.ok);
    } catch (e) { setStatus('rclone-status', e.message, false); }
  }

  async function loadExisting() {
    const el = document.getElementById('rclone-existing');
    if (!el) return;
    try {
      const r = await fetch(BASE() + '/api/drives');
      const d = await r.json().catch(() => ({}));
      const remotes = (d.drives || []).filter(dr => dr.type === 'rclone');
      if (!remotes.length) { el.textContent = 'No rclone remotes configured yet.'; return; }
      el.innerHTML = remotes.map(rem =>
        `<div class="d-flex align-items-center gap-2 py-1 border-bottom" style="font-size:11px;">
          <i class="ti ti-cloud" aria-hidden="true" style="color:#6c757d;font-size:13px;flex-shrink:0;"></i>
          <span style="font-family:ui-monospace,monospace;flex:1;">${esc(rem.name)}</span>
          <span class="small text-muted">${esc(rem.remote_type || '')}</span>
        </div>`
      ).join('');
    } catch { el.textContent = 'Could not load existing remotes.'; }
  }

  // Tab switching
  document.addEventListener('click', e => {
    const tab = e.target.closest('[data-drive-tab]');
    if (!tab) return;
    document.querySelectorAll('[data-drive-tab]').forEach(t => t.classList.toggle('active', t === tab));
    document.querySelectorAll('#add-drive-drawer .sharing-tab-panel').forEach(p =>
      p.classList.toggle('active', p.id === `drive-tab-${tab.dataset.driveTab}`)
    );
  });

  // Add drive button in sidebar
  document.getElementById('add-drive-btn')?.addEventListener('click', open);

  global.AddDrive = { open, pickLocalPath, addLocal, onTypeChange, authorize, addRclone, testConnection };

})(window);
