/**
 * inspector_actions.js — what the inspector does for the selected File, folder or Dataset.
 *
 *   who(content, selection, version, isCurrent)  — Annotations tab: "Who / which project is this?"
 *       Ranked Investigator / Lab / Study suggestions for the selected path, confirmed in one click.
 *       Reuses the existing anchor-matching routes (GET /api/files/attribution/anchors,
 *       POST .../candidates, POST .../confirm); the server does the ranking evidence and the MERGE.
 *       The advanced Attribute controls are behind "More options" (#inspector-more-options).
 *   interpret(content, selection, isCurrent)     — Interpret tab: status for the selected paths and the
 *       existing interpreter run, through Annotate.interpretStatus / Annotate.startInterpretRun
 *       (annotate.js), so no interpreter logic lives here.
 *
 * Loaded by gui/files_inspector.html after gui_slice.js, which calls window.InspectorActions.
 */
;(function (global) {
  'use strict';
  const BASE = () => (typeof global.SCIDK_BASE !== 'undefined' ? global.SCIDK_BASE : '');
  const WHO_LABELS = ['Investigator', 'Lab', 'Study'];
  const TARGET_LABEL = 'Folder';
  const CONF = {HIGH: 3, MED: 2, LOW: 1};
  const PER_LABEL = 4, VERIFY_MAX = 8, SHOW_MAX = 5;

  function el(tag, text, attrs) {
    const e = document.createElement(tag);
    if (text != null) e.textContent = text;
    if (attrs) Object.assign(e, attrs);
    return e;
  }
  const tid = (e, id) => { e.setAttribute('data-testid', id); return e; };

  async function api(url, opts) {
    const r = await fetch(BASE() + url, opts);
    let d = {};
    try { d = await r.json(); } catch (e) { /* non-JSON */ }
    return {ok: r.ok, status: r.status, d};
  }
  const post = (url, body) => api(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});

  // ── Who / which project is this? ─────────────────────────────────────────
  function _targetFolder(selection) {
    const rec = selection.record || {};
    const path = String(selection.key || rec.path || '').replace(/\/+$/, '');
    const isFolder = rec.type === 'folder';
    if (isFolder) return path;
    const cut = path.lastIndexOf('/');
    return cut > 0 ? path.slice(0, cut) : path;
  }

  const _tokens = s => String(s || '').toLowerCase().split(/[^a-z0-9]+/).filter(t => t.length >= 3);

  // Anchors whose name appears in the path, best first. Cheap pre-filter only: the candidates route decides.
  function _rank(anchors, pathTokens) {
    return anchors.map(a => {
      const t = _tokens(a.name);
      const hit = t.filter(x => pathTokens.has(x)).length;
      return {name: a.name, score: t.length ? hit / t.length : 0};
    }).filter(a => a.score > 0).sort((a, b) => b.score - a.score);
  }

  const _covers = (candidatePath, target) => {
    const c = String(candidatePath || '').replace(/\/+$/, '');
    return !!c && (c === target || target.startsWith(c + '/'));
  };

  async function _suggestions(selection, say) {
    const target = _targetFolder(selection);
    if (!target) return {items: [], note: 'This object has no path to match.'};
    say('Looking for likely matches…');
    let labels = WHO_LABELS.slice();
    const known = await api('/api/schema/labels');
    if (known.ok && Array.isArray(known.d.labels)) {
      const have = labels.filter(l => known.d.labels.includes(l));
      if (have.length) labels = have;
    }
    const pathTokens = new Set(_tokens(target));
    const picked = [];
    let unavailable = '';
    for (const label of labels) {
      const r = await api('/api/files/attribution/anchors?anchor_label=' + encodeURIComponent(label));
      if (!r.ok) { unavailable = r.d.error || ('Error ' + r.status); continue; }
      _rank(r.d.anchors || [], pathTokens).slice(0, PER_LABEL).forEach(a => picked.push(Object.assign({label}, a)));
    }
    if (!picked.length) return {items: [], note: unavailable ? 'Could not look up matches: ' + unavailable : 'No likely match found.'};
    const checked = await Promise.all(picked.slice(0, VERIFY_MAX).map(async a => {
      const r = await post('/api/files/attribution/candidates', {
        anchor_name: a.name, anchor_label: a.label, target_label: TARGET_LABEL, include_labmates: false,
      });
      if (!r.ok) return null;
      const hits = (r.d.candidates || []).filter(c => _covers(c.path, target))
        .sort((x, y) => (CONF[y.confidence] || 0) - (CONF[x.confidence] || 0) || (x.relative_depth || 0) - (y.relative_depth || 0));
      const c = hits[0];
      return c ? {name: a.name, label: a.label, score: a.score, confidence: c.confidence, reason: c.reason, path: c.path} : null;
    }));
    const items = checked.filter(Boolean)
      .sort((x, y) => (CONF[y.confidence] || 0) - (CONF[x.confidence] || 0) || y.score - x.score)
      .slice(0, SHOW_MAX);
    return {items, note: items.length ? '' : 'No likely match found. Use More options to search by hand.'};
  }

  async function _confirm(item, button, out) {
    button.disabled = true;
    out.textContent = 'Saving…';
    const rel = await api('/api/files/attribution/relationship-suggestions?anchor_label=' + encodeURIComponent(item.label) +
      '&target_label=' + encodeURIComponent(TARGET_LABEL));
    const relationship = (rel.ok && rel.d.suggestions && rel.d.suggestions[0]) || 'OWNS';
    const r = await post('/api/files/attribution/confirm', {
      anchor_name: item.name, anchor_label: item.label, target_label: TARGET_LABEL,
      target_paths: [item.path], relationship,
    });
    if (!r.ok) { out.textContent = r.d.error || ('Error ' + r.status); button.disabled = false; return; }
    out.textContent = '✓ Linked to ' + item.name + ' (' + item.label + '): ' + (r.d.written || 0) + ' written, ' + (r.d.skipped || 0) + ' already existed.';
  }

  function who(content, selection, version, isCurrent) {
    const box = tid(el('section', null, {id: 'inspector-who'}), 'inspector-who');
    box.setAttribute('aria-label', 'Who or which project is this?');
    const start = tid(el('button', 'Who / which project is this?', {type: 'button', id: 'who-start'}), 'who-start');
    const out = tid(el('div', '', {id: 'who-status'}), 'who-status');
    out.setAttribute('role', 'status'); out.setAttribute('aria-live', 'polite');
    const list = tid(el('ul', null, {id: 'who-suggestions'}), 'who-suggestions');
    box.append(el('h3', 'Who / which project'), el('p', 'Suggests the investigator, lab or study this location belongs to. Confirming adds one link; nothing is removed.'), start, out, list);
    content.append(box);
    start.onclick = async () => {
      start.disabled = true; list.replaceChildren();
      try {
        const res = await _suggestions(selection, msg => { if (isCurrent()) out.textContent = msg; });
        if (!isCurrent()) return;
        out.textContent = res.note || (res.items.length + ' likely match' + (res.items.length === 1 ? '' : 'es') + ':');
        res.items.forEach(item => {
          const li = el('li', null, {className: 'who-item'});
          li.setAttribute('data-testid', 'who-suggestion');
          li.append(el('strong', item.name), el('span', ' · ' + item.label + ' · ' + item.confidence + ' — ' + (item.reason || '') + ' '));
          const ok = tid(el('button', 'Confirm', {type: 'button'}), 'who-confirm');
          ok.setAttribute('aria-label', 'Confirm ' + item.name + ' as ' + item.label);
          ok.onclick = () => _confirm(item, ok, out);
          li.append(ok); list.append(li);
        });
      } catch (e) { if (isCurrent()) out.textContent = 'Could not look up matches: ' + e.message; }
      finally { start.disabled = false; }
    };
  }

  // ── Interpret ────────────────────────────────────────────────────────────
  function _paths(selection) {
    const sc = selection.scope;
    if (sc && Array.isArray(sc.paths) && sc.paths.length) return sc.paths.filter(Boolean);
    const rec = selection.record || {};
    if (selection.kind === 'scan-dataset') return rec.root_path ? [rec.root_path] : [];
    const p = selection.key || rec.path;
    return p ? [p] : [];
  }

  function interpret(content, selection, isCurrent) {
    const A = global.Annotate;
    const box = tid(el('section', null, {id: 'inspector-interpret'}), 'inspector-interpret');
    const statusEl = tid(el('div', 'Loading interpreter status…', {id: 'interpret-status'}), 'interpret-status');
    const runEl = tid(el('div', '', {id: 'interpret-run-status'}), 'interpret-run-status');
    runEl.setAttribute('role', 'status'); runEl.setAttribute('aria-live', 'polite');
    const bar = el('div');
    const missing = tid(el('button', 'Run missing only', {type: 'button', id: 'interpret-run-missing', hidden: true}), 'interpret-run-missing');
    const all = tid(el('button', 'Re-run all', {type: 'button', id: 'interpret-run-all', hidden: true}), 'interpret-run-all');
    bar.append(missing, all);
    box.append(el('p', 'Runs the existing interpreters over the selected files to read their structure; it does not change the files.'), statusEl, bar, runEl);
    content.append(box);
    if (!A || !A.interpretStatus) { statusEl.textContent = 'Interpretation is unavailable on this page.'; return; }

    const paths = _paths(selection);
    const say = html => { if (isCurrent()) runEl.innerHTML = html; };
    const run = mode => A.startInterpretRun(paths, mode, say, load);
    missing.onclick = () => run('missing_only');
    all.onclick = () => run('all');

    async function load() {
      if (!isCurrent()) return;
      if (!paths.length) { statusEl.textContent = 'This object has no path to interpret.'; return; }
      let st;
      try { st = await A.interpretStatus(paths); } catch (e) { st = {ok: false, error: e.message, interpreters: [], unknown: []}; }
      if (!isCurrent()) return;
      if (!st.ok) { statusEl.textContent = st.error; return; }
      statusEl.replaceChildren();
      const lines = [];
      if (st.interpreters.length) { const d = el('div'); d.innerHTML = A.interpretStatusHtml(st.interpreters); statusEl.append(d); }
      else lines.push('No interpreter handles the selected files.');
      if (st.unknown.length) lines.push(st.unknown.length + ' of ' + paths.length + ' path(s) are not in SciDK\'s own file index (not scanned here), so there is nothing to interpret for them yet.');
      lines.forEach(t => statusEl.append(el('p', t)));
      const anyMissing = st.interpreters.some(it => Object.values(it.files || {}).some(f => f.status !== 'ok'));
      const anyKnown = st.interpreters.length > 0;
      missing.hidden = !anyKnown; all.hidden = !anyKnown;
      // The selection bar's "Interpret" asks for the run once; opening the tab by hand only shows status.
      if (selection.interpret) {
        selection.interpret = false;
        if (anyMissing) run('missing_only');
        else if (anyKnown) say('<span class="text-muted">Already interpreted.</span>');
      }
    }
    load();
  }

  // ── "More options": the advanced Attribute controls ──────────────────────
  function _wireMore() {
    const more = document.getElementById('inspector-more-options');
    if (more && !more._wired) {
      more._wired = true;
      more.addEventListener('toggle', () => {
        if (more.open && global.Annotate && global.Annotate.openAttribution && document.getElementById('inspector-attribute-controls')) {
          global.Annotate.openAttribution();
        }
      });
    }
    document.addEventListener('click', e => {
      if (e.target.closest('[data-annotate-open-legacy]') && global.Annotate) global.Annotate.open('attribute');
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _wireMore); else _wireMore();

  global.InspectorActions = {who, interpret};
})(window);
