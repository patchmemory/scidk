/**
 * dms.js — DMS Plan builder drawer
 *
 * Extracted from the inline "Generate DMS Plan Draft" block that used to live
 * in datasets.html. Behaviour is unchanged; the panel is now a drawer.
 *
 * Exposes: window.DMS
 *   .open()      — open the drawer and generate a draft
 *   .close()     — close the drawer, releasing the download blob
 *   .generate()  — regenerate without touching the drawer's open state
 *
 * Asks the plugin for markdown generated from the whole graph — no selection
 * involved — and shows it in a textarea to copy into DMPTool. Requesting JSON
 * rather than raw markdown gets the summary alongside it, which is what makes
 * the "N entity types, N files" line and the PHI flag possible without
 * re-parsing the document in the browser.
 */
;(function (global) {
  'use strict';

  const BASE = () => (typeof global.SCIDK_BASE !== 'undefined') ? global.SCIDK_BASE : '';

  let _objectUrl = null;

  const $ = id => document.getElementById(id);

  function _humanBytes(bytes) {
    const units = ['bytes', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
    let size = Number(bytes) || 0;
    for (let i = 0; i < units.length; i++) {
      if (size < 1024 || i === units.length - 1) {
        return i === 0 ? `${Math.round(size)} bytes` : `${size.toFixed(2)} ${units[i]}`;
      }
      size /= 1024;
    }
    return `${size} bytes`;
  }

  function _revokeUrl() {
    if (_objectUrl) {
      URL.revokeObjectURL(_objectUrl);
      _objectUrl = null;
    }
  }

  async function generate() {
    const btn      = $('dms-plan-btn');
    const markdown = $('dms-markdown');
    const summary  = $('dms-summary');
    const status   = $('dms-status');
    const phi      = $('dms-phi');
    const download = $('dms-download');
    if (!markdown) return;

    if (phi) phi.style.display = 'none';
    if (summary) summary.textContent = '';
    if (status) status.innerHTML = '<span class="text-muted">Reading the graph… '
      + 'on a large index this takes a few seconds.</span>';
    markdown.value = '';

    let prevLabel = '';
    if (btn) { btn.disabled = true; prevLabel = btn.textContent; btn.textContent = 'Generating…'; }

    try {
      const r = await fetch(BASE() + '/api/plugins/nih_dms/draft_plan?format=json');
      const j = await r.json().catch(() => ({}));

      if (r.ok && j.status === 'ok') {
        markdown.value = j.markdown || '';

        const s = j.summary || {};
        const parts = [
          `${(s.entity_types || 0).toLocaleString()} entity types`,
          `${(s.records || 0).toLocaleString()} records`,
        ];
        if (s.files) {
          parts.push(`${s.files.toLocaleString()} files`);
          parts.push(_humanBytes(s.bytes));
        }
        if (s.formats) parts.push(`${s.formats} formats`);
        if (s.modalities && s.modalities.length) {
          parts.push(`${s.modalities.length} modality source(s)`);
        }
        if (summary) summary.textContent = `— from ${parts.join(', ')}`;

        if (s.phi_detected && phi) {
          const props = (s.phi_properties || []).map(p => `<code>${p}</code>`).join(', ');
          phi.innerHTML = '⚠ <strong>Potentially identifiable data detected.</strong> '
            + `Property names matched: ${props}. See the Identifiability note in Element 1 `
            + 'and the privacy subsection in Element 5 — neither can be left as a placeholder.';
          phi.style.display = 'block';
        }

        const notes = (s.warnings || []).length
          ? ` ${s.warnings.length} note(s) are recorded at the top of the draft.`
          : '';
        if (status) status.innerHTML = '<span class="text-success">Draft generated from the live '
          + `graph.</span>${notes}`;

        _revokeUrl();
        _objectUrl = URL.createObjectURL(
          new Blob([markdown.value], { type: 'text/markdown' }));
        if (download) {
          download.href = _objectUrl;
          download.download = j.filename || 'nih-dms-plan-draft.md';
        }
      } else {
        // A missing or unreachable graph is reported, never papered over with a
        // placeholder plan — that is the whole point of the route's 503.
        if (status) status.innerHTML = `<span class="text-danger">${
          j.error || ('Could not generate a draft (' + r.status + ')')}</span>`;
      }
    } catch (err) {
      if (status) status.innerHTML =
        `<span class="text-danger">Could not generate a draft: ${err.message}</span>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = prevLabel; }
    }
  }

  function open() {
    if (global.Drawers) global.Drawers.open('dms-panel');
    const markdown = $('dms-markdown');
    // Regenerating on every open would re-read the whole graph for a draft the
    // user may already have in front of them.
    if (markdown && !markdown.value) generate();
  }

  function close() {
    if (global.Drawers) global.Drawers.close();
    // The blob backs the download link; holding it after close would leak.
    _revokeUrl();
    const download = $('dms-download');
    if (download) download.removeAttribute('href');
  }

  // ── Wiring ───────────────────────────────────────────────────────────
  $('dms-plan-btn')?.addEventListener('click', generate);
  $('dms-close')?.addEventListener('click', () => { _revokeUrl(); $('dms-download')?.removeAttribute('href'); });

  $('dms-copy')?.addEventListener('click', async () => {
    const markdown = $('dms-markdown');
    const copy = $('dms-copy');
    if (!markdown || !markdown.value) return;
    const prev = copy.textContent;
    try {
      await navigator.clipboard.writeText(markdown.value);
      copy.textContent = 'Copied';
    } catch (err) {
      // Clipboard access needs a secure context; selecting the text is a
      // workable fallback and tells the user what to do next.
      markdown.focus();
      markdown.select();
      copy.textContent = 'Press Ctrl+C';
    }
    setTimeout(() => { copy.textContent = prev; }, 2000);
  });

  global.DMS = { open, close, generate };

})(window);
