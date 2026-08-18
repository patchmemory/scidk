/**
 * annotate.js — Annotate drawer (Attribute / Collect / Interpret tabs)
 *
 * Extracted from the inline attribution script that used to live at the bottom
 * of datasets.html (MOD-1). The attribution behaviour is unchanged; what is new
 * is the drawer wrapper around it and the Collect and Interpret tabs.
 *
 * Exposes: window.Annotate
 *   .open(tab)                 — open the drawer, optionally on a given tab
 *   .setTab(tab)               — 'attribute' | 'collect' | 'interpret'
 *   .setCollectSource(src)     — 'selection' | 'collection'
 *   .createDataset()           — POST /api/datasets/collections
 *   .runInterpreters(mode)     — POST /api/interpreters/run
 *   .apply()                   — run the active tab's primary action
 *
 * That object is the module's entire surface. Every other function here is
 * private, including the attribution ones (runAttribution, runConfirm,
 * filterAttrAnchors, …): the panel reaches them through `data-annotate-action`
 * / `data-annotate-change` / `data-annotate-input` attributes and the delegated
 * listeners at the bottom of this file, so nothing has to be published onto
 * window for the markup to resolve it.
 *
 * Page state this module reads, when the page provides it:
 *   window.selItems     — Set of selected row ids (full paths)
 *   window.currentPath  — folder currently being browsed
 *   window.currentServer— provider id of the current drive, used as host
 */
;(function (global) {
  'use strict';

  const BASE = () => (typeof global.SCIDK_BASE !== 'undefined') ? global.SCIDK_BASE : '';

  // ── Attribution ────────────────────────────────────────────────────────
  // Pick an anchor node, score target nodes whose paths carry some spelling of
  // its name, confirm the good ones as edges of the chosen relationship type.
  // No label or relationship type is hardcoded here beyond the initial defaults:
  // labels come from /api/schema/labels, relationship types from the graph.

  const ATTR_DEFAULT_ANCHOR_LABEL = 'Investigator';
  const ATTR_DEFAULT_TARGET_LABEL = 'Folder';
  //: Above this many distinct values, a target condition keeps its text input
  //: instead of becoming a dropdown.
  const ATTR_VALUE_PICKER_MAX = 500;

  let _attrAnchors        = [];
  let _attrCandidates     = [];
  let _attrLabelsLoaded   = false;
  // The property-filtered subset of _attrAnchors, or null when no property filter
  // is active. Kept beside the full list rather than replacing it, so Clear can
  // restore every anchor without another round trip.
  let _attrAnchorFilter   = null;
  // The FilterBuilder driving the Target conditions section, or null before the
  // panel has been opened once. Torn down and rebuilt when the target label
  // changes — its conditions are keyed to that label's schema.
  let _attrTargetFB       = null;

  function _attrAnchorLabel() {
    const sel = document.getElementById('attr-anchor-label-sel');
    return (sel && sel.value) || ATTR_DEFAULT_ANCHOR_LABEL;
  }

  // The selected anchor is read from the control, never cached. Every path that
  // re-renders the listbox (property filter, name search, label change) assigns
  // .innerHTML, which fires no change event — a cached copy would survive the
  // re-render and confirm would then write edges from an anchor no longer on
  // screen. Reading .value makes that state unrepresentable: it is '' whenever
  // nothing is selected, including right after a re-render.
  function _attrCurrentAnchor() {
    const sel = document.getElementById('attr-anchor-sel');
    return sel ? sel.value : '';
  }

  function _attrTargetLabel() {
    const sel = document.getElementById('attr-target-label-sel');
    return (sel && sel.value) || ATTR_DEFAULT_TARGET_LABEL;
  }

  function _attrEsc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function _attrSetStatus(msg) {
    const el = document.getElementById('attr-status');
    if (el) el.textContent = msg;
  }

  // Load everything the Attribute tab needs. Kept under the old name because
  // nothing about it is drawer-specific, and it is still the single place that
  // decides what a freshly-opened Attribute tab shows.
  async function openAttributionPanel() {
    if (!_attrLabelsLoaded) await _loadSchemaLabels();
    if (_attrAnchors.length === 0) await _loadAnchors(_attrAnchorLabel());
    await _loadAnchorProperties();
    await _loadRelSuggestions();
    // After the labels, so the builder opens on the target label actually
    // selected rather than the hardcoded default.
    _initTargetFB();
  }

  // Build the Target conditions section. Idempotent — opening the panel a second
  // time keeps whatever the user had built.
  //
  // base.html loads filter_builder.js at the end of <body>, after this module,
  // so FilterBuilder does not exist at parse time. That is fine here because
  // every path in is user-triggered, but the guard stays: a panel that silently
  // loses one section beats a panel that throws.
  function _initTargetFB() {
    if (_attrTargetFB) return;
    const container = document.getElementById('attr-target-fb-container');
    if (!container || typeof FilterBuilder === 'undefined') return;
    // The constructor takes a container *id*, not an element.
    _attrTargetFB = new FilterBuilder('attr-target-fb-container', {
      defaultLabel: _attrTargetLabel(),
      showSave: false,
      onPreview: (count, cypher, err) => {
        if (err) _attrSetStatus('Filter error: ' + err);
      },
      // Restores the value picker the panel already gives the Anchor section: a
      // choice among values the graph holds, not a substring to guess at.
      // Falling back to null leaves FilterBuilder's own text input in place.
      valueOptionsFor: async (label, property) => {
        try {
          const qs = new URLSearchParams({
            // A misnomer in this position — the endpoint reads distinct values of
            // a property on nodes of a label, and here that label is the target.
            // The behaviour is exactly what is wanted; only the name is anchored.
            anchor_label: label,
            property_key: property,
          });
          const r = await fetch(BASE()
            + '/api/files/attribution/anchor-property-values?' + qs);
          const d = await r.json();
          if (!r.ok || !d.values || !d.values.length) return null;
          // A picker over thousands of options is not a picker. Past the cap,
          // fall back to the text box, which is the better control for a
          // high-cardinality property anyway.
          //
          // This caps the *rendering*, not the query: the endpoint has no LIMIT,
          // so it still scans the label and returns every distinct value first.
          // On a small anchor label that is what it was built for; on a target
          // label the size of :File it is expensive. Bounding it server-side is
          // the real fix and belongs with that endpoint.
          if (d.values.length > ATTR_VALUE_PICKER_MAX) return null;
          return d.values;
        } catch (e) { return null; }
      },
    });
  }

  // No closeAttributionPanel: the drawer's × and Cancel carry
  // [data-close-drawer], which drawers.js handles for every panel.

  // Offer every label the graph actually has, in both pickers, keeping the
  // defaults selectable even if the graph has no such label yet.
  async function _loadSchemaLabels() {
    const anchorSel = document.getElementById('attr-anchor-label-sel');
    const targetSel = document.getElementById('attr-target-label-sel');
    if (!anchorSel || !targetSel) return;
    try {
      const r = await fetch(BASE() + '/api/schema/labels');
      const d = await r.json();
      if (!r.ok) return;
      const labels = d.labels || [];
      [[anchorSel, _attrAnchorLabel()], [targetSel, _attrTargetLabel()]].forEach(([sel, current]) => {
        const opts = labels.includes(current) ? labels : [current].concat(labels);
        sel.innerHTML = opts.map(l =>
          `<option value="${_attrEsc(l)}"${l === current ? ' selected' : ''}>${_attrEsc(l)}</option>`
        ).join('');
      });
      _attrLabelsLoaded = true;
    } catch (e) {
      // Leave the default options in place — the panel still works without the list.
      console.warn('Could not load labels:', e);
    }
  }

  // Switching the anchor label invalidates the anchor list, any results below it,
  // the relationship suggestions (which depend on both labels), and the property
  // filter — the new label carries its own properties, so both the picker's
  // options and any filter built from the old ones are gone.
  async function onAnchorLabelChange() {
    _attrAnchors = [];
    _attrCandidates = [];
    _attrAnchorFilter = null;
    const search = document.getElementById('attr-search');
    if (search) search.value = '';
    const anchorSel = document.getElementById('attr-anchor-sel');
    if (anchorSel) anchorSel.innerHTML = '';
    const lbl = document.getElementById('attr-anchor-label');
    if (lbl) lbl.textContent = '';
    const results = document.getElementById('attr-results');
    if (results) results.style.display = 'none';
    const tbody = document.getElementById('attr-tbody');
    if (tbody) tbody.innerHTML = '';
    await _loadAnchors(_attrAnchorLabel());
    await _loadAnchorProperties();
    // After, not before: _loadAnchorProperties may keep the old property selected
    // if the new label shares it, and its values then have to come from the new
    // label's nodes. With no property kept this just empties the value picker.
    await _loadAnchorPropertyValues();
    await _loadRelSuggestions();
  }

  // The target label does not affect the anchor list, only the suggestions, any
  // results already on screen, and the target conditions — which are built
  // against the old label's properties and would generate predicates on keys the
  // new label may not carry. Rebuilt rather than relabelled, for the same reason
  // the anchor property filter is dropped in onAnchorLabelChange.
  async function onTargetLabelChange() {
    _attrCandidates = [];
    const results = document.getElementById('attr-results');
    if (results) results.style.display = 'none';
    const tbody = document.getElementById('attr-tbody');
    if (tbody) tbody.innerHTML = '';
    if (_attrTargetFB) {
      _attrTargetFB = null;
      const c = document.getElementById('attr-target-fb-container');
      if (c) c.innerHTML = '';
    }
    await _loadRelSuggestions();
    _initTargetFB();
  }

  // Target property predicates, read from the control at submit time rather than
  // cached — the same discipline as _attrCurrentAnchor, and for the same reason.
  //
  // An invalid definition (no label, or a condition with no property) sends
  // nothing: the backend would reject the whole request with a 400 that names an
  // identifier the user never typed. runAttribution says so rather than letting
  // an unfiltered result set pass for a filtered one.
  function _attrTargetConditions() {
    if (!_attrTargetFB) return [];
    const fb = _attrTargetFB;
    if (typeof fb.validate === 'function') {
      const v = fb.validate();
      if (!v.valid) return [];
    }
    const def = fb.getFilterDef();
    return (def.blocks && def.blocks[0] && def.blocks[0].conditions) || [];
  }

  // Whether the builder is holding something it refused to send, so the caller
  // can say so instead of quietly returning candidates that were never filtered.
  function _attrTargetConditionsDropped() {
    if (!_attrTargetFB || typeof _attrTargetFB.validate !== 'function') return false;
    if (_attrTargetFB.validate().valid) return false;
    const def = _attrTargetFB.getFilterDef();
    return !!(def.blocks && def.blocks[0]
              && (def.blocks[0].conditions || []).length);
  }

  async function _loadAnchors(anchorLabel) {
    _attrSetStatus('Loading anchors…');
    try {
      const r = await fetch(BASE() + '/api/files/attribution/anchors?anchor_label='
                            + encodeURIComponent(anchorLabel));
      const d = await r.json();
      if (!r.ok) { _attrSetStatus(d.error || `Error ${r.status}`); return; }
      _attrAnchors = d.anchors || [];
      _attrAnchorFilter = null;   // a fresh full list supersedes any property filter
      _renderAnchors(_attrAnchors);
      _attrSetStatus(_attrAnchors.length
        ? ''
        : `No named :${anchorLabel} nodes found in the graph.`);
    } catch (e) {
      _attrSetStatus('Could not load anchors: ' + e);
    }
  }

  // Which properties this label's nodes carry, commonest first. A failure here
  // leaves the picker with its placeholder — the panel still works without it.
  async function _loadAnchorProperties() {
    const sel = document.getElementById('attr-filter-prop-sel');
    if (!sel) return;
    const previous = sel.value;
    try {
      const r = await fetch(BASE()
        + '/api/files/attribution/anchor-properties?anchor_label='
        + encodeURIComponent(_attrAnchorLabel()));
      const d = await r.json();
      if (!r.ok) return;
      const props = d.properties || [];
      sel.innerHTML = '<option value="">Filter by property…</option>'
        + props.map(p => `<option value="${_attrEsc(p)}">${_attrEsc(p)}</option>`).join('');
      // Keep the user's choice selected if the new label happens to share it.
      if (previous && props.includes(previous)) sel.value = previous;
    } catch (e) {
      console.warn('Could not load anchor properties:', e);
    }
  }

  // Empty the value picker and lock it. Its options only mean anything for one
  // (label, property) pair, so anything that invalidates that pair comes through
  // here rather than leaving stale values selectable.
  function _attrResetValuePicker() {
    const sel = document.getElementById('attr-filter-val-sel');
    if (!sel) return;
    sel.innerHTML = '<option value="">Select a value…</option>';
    sel.disabled = true;
  }

  // Which values the chosen property actually takes on this label's nodes. Run
  // whenever the property changes, so the user picks from the graph instead of
  // guessing a substring. A failure leaves the picker disabled — the anchor list
  // is still there, unfiltered, which is the state the user came from.
  async function _loadAnchorPropertyValues() {
    const propSel = document.getElementById('attr-filter-prop-sel');
    const valSel  = document.getElementById('attr-filter-val-sel');
    if (!valSel) return;
    const prop = propSel ? propSel.value : '';

    _attrResetValuePicker();
    if (!prop) return;

    try {
      const qs = new URLSearchParams({
        anchor_label: _attrAnchorLabel(),
        property_key: prop,
      });
      const r = await fetch(BASE()
        + '/api/files/attribution/anchor-property-values?' + qs.toString());
      const d = await r.json();
      if (!r.ok) { console.warn('Could not load property values:', d.error); return; }
      const values = d.values || [];
      valSel.innerHTML = '<option value="">Select a value…</option>'
        + values.map(v => `<option value="${_attrEsc(v)}">${_attrEsc(v)}</option>`).join('');
      // Nothing to choose from stays locked, and says so rather than looking broken.
      valSel.disabled = (values.length === 0);
      if (values.length === 0) _attrSetStatus(`No values for ${prop} on :${_attrAnchorLabel()}.`);
    } catch (e) {
      console.warn('Could not load property values:', e);
    }
  }

  // Narrow the anchor list in the database, on any property those nodes carry.
  // Fired by the value picker's change event, so selecting is applying — the
  // value came from the graph, so there is nothing to confirm before running it.
  async function applyAnchorFilter() {
    const propEl = document.getElementById('attr-filter-prop-sel');
    const valEl  = document.getElementById('attr-filter-val-sel');
    const prop = propEl ? propEl.value : '';
    const val  = valEl ? valEl.value : '';
    if (!prop || !val) return;   // back on the placeholder — nothing to filter by
    _attrSetStatus('Filtering anchors…');
    try {
      const qs = new URLSearchParams({
        anchor_label:    _attrAnchorLabel(),
        filter_property: prop,
        filter_value:    val,
      });
      const r = await fetch(BASE()
        + '/api/files/attribution/anchors?' + qs.toString());
      const d = await r.json();
      if (!r.ok) { _attrSetStatus(d.error || `Error ${r.status}`); return; }
      _attrAnchorFilter = d.anchors || [];
      // Not _renderAnchors: the name search composes with the property filter,
      // so re-render through the search box rather than over it.
      filterAttrAnchors();
      _attrSetStatus(_attrAnchorFilter.length
        ? `${_attrAnchorFilter.length} anchor(s) matched ${prop} = "${val}"`
        : `No :${_attrAnchorLabel()} nodes with ${prop} = "${val}"`);
    } catch (e) {
      _attrSetStatus('Filter failed: ' + e);
    }
  }

  // Drop the property filter and the name search, back to every loaded anchor.
  function clearAnchorFilter() {
    _attrAnchorFilter = null;
    const propEl = document.getElementById('attr-filter-prop-sel');
    if (propEl) propEl.value = '';
    _attrResetValuePicker();
    const search = document.getElementById('attr-search');
    if (search) search.value = '';
    _renderAnchors(_attrAnchors);
    _attrSetStatus('');
  }

  // Suggestions are seeds for the label pair merged with what the graph already
  // uses between them. A custom value the user has typed stays put.
  async function _loadRelSuggestions() {
    const anchorLabel = _attrAnchorLabel();
    const targetLabel = _attrTargetLabel();
    if (!anchorLabel || !targetLabel) return;

    const sel = document.getElementById('attr-rel-select');
    if (!sel) return;
    try {
      const r = await fetch(
        BASE() + '/api/files/attribution/relationship-suggestions'
        + '?anchor_label=' + encodeURIComponent(anchorLabel)
        + '&target_label=' + encodeURIComponent(targetLabel));
      const d = await r.json();
      if (!r.ok) return;
      const suggestions = (d.suggestions && d.suggestions.length)
        ? d.suggestions : ['OWNS', 'RELATED_TO'];
      sel.innerHTML = suggestions.map(s =>
        `<option value="${_attrEsc(s)}">${_attrEsc(s)}</option>`
      ).join('');
    } catch (e) {
      console.warn('Could not load relationship suggestions:', e);
    }
  }

  // A non-empty custom field wins over the dropdown. Sent as typed, not
  // uppercased, so the server's validation is what the user sees.
  function _getRelationship() {
    const customEl = document.getElementById('attr-rel-custom');
    const custom = customEl ? customEl.value.trim() : '';
    if (custom) return custom;
    const sel = document.getElementById('attr-rel-select');
    return sel ? sel.value : '';
  }

  function toggleCustomRel() {
    const inp = document.getElementById('attr-rel-custom');
    if (!inp) return;
    const hidden = inp.style.display === 'none' || !inp.style.display;
    inp.style.display = hidden ? 'inline' : 'none';
    if (hidden) { inp.focus(); } else { inp.value = ''; }
    const toggle = document.getElementById('attr-rel-toggle');
    if (toggle) toggle.textContent = hidden ? 'use suggestion' : 'or type custom';
  }

  // The option value stays the bare name — that is what selectAttrAnchor, the
  // candidate search and confirm all key on. A filtered list also carries the
  // value that matched, shown in the label so filtering by email or lab says
  // *which* node is about to be picked.
  function _renderAnchors(list) {
    const sel = document.getElementById('attr-anchor-sel');
    if (!sel) return;
    sel.innerHTML = list.map(p => {
      const matched = p.matched_value;
      const shown = (matched === null || matched === undefined
                     || String(matched) === String(p.name))
        ? p.name
        : `${p.name} — ${matched}`;
      return `<option value="${_attrEsc(p.name)}">${_attrEsc(shown)}</option>`;
    }).join('');
    // Assigning .innerHTML leaves the listbox with nothing selected, so pick the
    // first option and render the span from it. The selection is then always
    // either a name that is on screen or nothing at all.
    selectAttrAnchor(list.length ? list[0].name : '');
  }

  // Name search runs over whatever the property filter left behind, so the two
  // narrow the list together. Called with no argument to re-render after the
  // property filter changes, reading the search box as it stands.
  function filterAttrAnchors(q) {
    const search = document.getElementById('attr-search');
    const raw = (q === undefined || q === null)
      ? (search ? search.value : '')
      : q;
    const needle = (raw || '').toLowerCase();
    const base = _attrAnchorFilter || _attrAnchors;
    _renderAnchors(needle
      ? base.filter(p => (p.name || '').toLowerCase().includes(needle))
      : base);
  }

  // Selection lives on the control; this only moves it and re-renders the span,
  // which is a pure view of the control's value.
  function selectAttrAnchor(name) {
    const sel = document.getElementById('attr-anchor-sel');
    if (sel) sel.value = name || '';
    const lbl = document.getElementById('attr-anchor-label');
    if (lbl) lbl.textContent = name ? '→ ' + name : '';
  }

  async function runAttribution() {
    const anchor = _attrCurrentAnchor();
    if (!anchor) { alert('Select an anchor first.'); return; }
    const labmatesEl = document.getElementById('attr-labmates');
    const labmates = labmatesEl ? labmatesEl.checked : true;
    const targetConditions = _attrTargetConditions();
    const droppedConditions = _attrTargetConditionsDropped();
    const btn = document.getElementById('attr-find-btn');

    if (btn) btn.disabled = true;
    _attrSetStatus('Searching…');
    try {
      const r = await fetch(BASE() + '/api/files/attribution/candidates', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          anchor_name: anchor,
          anchor_label: _attrAnchorLabel(),
          target_label: _attrTargetLabel(),
          include_labmates: labmates,
          target_conditions: targetConditions,
        }),
      });
      const d = await r.json();
      if (!r.ok) { _attrSetStatus(d.error || `Error ${r.status}`); return; }
      _attrCandidates = d.candidates || [];
      _renderAttrCandidates();
      _attrSetStatus(`${d.total} candidate${d.total !== 1 ? 's' : ''} found`
        + (droppedConditions
           ? ' — target conditions were incomplete and not applied'
           : ''));
      const msg = document.getElementById('attr-confirm-msg');
      if (msg) msg.textContent = '';
      const results = document.getElementById('attr-results');
      if (results) results.style.display = 'block';
    } catch (e) {
      _attrSetStatus('Search failed: ' + e);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function _renderAttrCandidates() {
    const BADGE = {
      HIGH: '<span style="background:#2a9d5c;color:#fff;padding:1px 6px;border-radius:3px;font-size:.8em;">HIGH</span>',
      MED:  '<span style="background:#e6a817;color:#fff;padding:1px 6px;border-radius:3px;font-size:.8em;">MED</span>',
      LOW:  '<span style="background:#888;color:#fff;padding:1px 6px;border-radius:3px;font-size:.8em;">LOW</span>',
    };
    const tbody = document.getElementById('attr-tbody');
    if (!tbody) return;
    tbody.innerHTML =
      _attrCandidates.map((c, i) => `
        <tr style="border-bottom:1px solid #eee;">
          <td><input type="checkbox" class="attr-cb" data-i="${i}"></td>
          <td>${BADGE[c.confidence] || _attrEsc(c.confidence)}</td>
          <td style="font-family:monospace; word-break:break-all;">${_attrEsc(c.path)}</td>
          <td>${_attrEsc(c.host_id)}</td>
          <td style="text-align:center;">${_attrEsc(c.relative_depth)}</td>
          <td style="color:#555;">${_attrEsc(c.reason)}</td>
        </tr>
      `).join('');
  }

  function attrSelectByConf(level) {
    document.querySelectorAll('.attr-cb').forEach(cb => {
      const c = _attrCandidates[parseInt(cb.dataset.i, 10)];
      if (c && c.confidence === level) cb.checked = true;
    });
  }

  function attrClearSel() {
    document.querySelectorAll('.attr-cb').forEach(cb => { cb.checked = false; });
  }

  async function runConfirm() {
    const paths = [...document.querySelectorAll('.attr-cb:checked')]
      .map(cb => (_attrCandidates[parseInt(cb.dataset.i, 10)] || {}).path)
      .filter(Boolean);
    if (!paths.length) { alert('Nothing selected.'); return; }

    const msg = document.getElementById('attr-confirm-msg');
    // Validated here rather than trusting that the search ran against this anchor:
    // this is the call that writes provenance edges, so it checks its own input.
    const anchor = _attrCurrentAnchor();
    if (!anchor) {
      if (msg) msg.textContent = 'No anchor selected — cannot write edges.';
      return;
    }

    const btn = document.getElementById('attr-confirm-btn');
    if (btn) btn.disabled = true;
    if (msg) msg.textContent = 'Writing…';
    try {
      const r = await fetch(BASE() + '/api/files/attribution/confirm', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          anchor_name: anchor,
          anchor_label: _attrAnchorLabel(),
          target_label: _attrTargetLabel(),
          target_paths: paths,
          relationship: _getRelationship(),
        }),
      });
      const d = await r.json();
      if (!r.ok) { if (msg) msg.textContent = d.error || `Error ${r.status}`; return; }
      if (msg) msg.textContent =
        `✓ ${d.written} written · ${d.skipped} already existed` +
        (d.errors && d.errors.length ? ` · ${d.errors.length} errors` : '');
      if (d.errors && d.errors.length) console.warn('Attribution errors:', d.errors);
    } catch (e) {
      if (msg) msg.textContent = 'Write failed: ' + e;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // ── Collect tab ────────────────────────────────────────────────────────
  // Two sources for the same action: whatever is ticked in the file table right
  // now, or the Collection, which survives navigation. The source is explicit
  // rather than inferred, because "nothing selected" and "empty collection" are
  // different problems and each deserves its own message.

  let _collectSource = 'selection';

  // A file entry the Dataset route can resolve: File nodes are keyed by
  // (path, host), so a bare basename is not enough. selItems holds full paths,
  // so split rather than guess.
  function _fileFromSelectionId(id) {
    const s = String(id || '');
    const cut = s.lastIndexOf('/');
    return {
      name: cut >= 0 ? s.slice(cut + 1) : s,
      path: cut >= 0 ? s.slice(0, cut) : (global.currentPath || ''),
      host: global.currentServer || '',
    };
  }

  function _collectFiles() {
    if (_collectSource === 'collection') {
      const items = (global.Collection ? global.Collection.items() : []) || [];
      return items.map(f => ({
        name: f.name,
        path: f.path || '',
        host: f.provider || global.currentServer || '',
      }));
    }
    const sel = global.selItems;
    if (!sel || !sel.size) return [];
    return [...sel].map(_fileFromSelectionId);
  }

  function setCollectSource(src) {
    _collectSource = (src === 'collection') ? 'collection' : 'selection';
    const selBtn  = document.getElementById('collect-src-sel');
    const collBtn = document.getElementById('collect-src-coll');
    if (selBtn)  selBtn.classList.toggle('active',  _collectSource === 'selection');
    if (collBtn) collBtn.classList.toggle('active', _collectSource === 'collection');
    _renderCollectScope();
  }

  function _renderCollectScope() {
    const note  = document.getElementById('collect-scope-note');
    const items = document.getElementById('collect-scope-items');
    const files = _collectFiles();
    if (note) {
      const lbl = note.querySelector('.sn-label');
      if (lbl) {
        lbl.textContent = _collectSource === 'collection'
          ? `From collection · ${files.length} file${files.length === 1 ? '' : 's'}`
          : `From selection · ${files.length} file${files.length === 1 ? '' : 's'}`;
      }
      note.classList.toggle('empty', files.length === 0);
    }
    if (items) items.textContent = files.length ? files.map(f => f.name).join(', ') : '—';
  }

  function _setCollectStatus(html, cls) {
    const el = document.getElementById('collect-status');
    if (!el) return;
    el.className = 'small mt-2' + (cls ? ' text-' + cls : '');
    el.innerHTML = html;
  }

  async function createDataset() {
    const nameEl = document.getElementById('collect-name');
    const name = nameEl ? nameEl.value.trim() : '';
    if (!name) { _setCollectStatus('Dataset name is required.', 'danger'); return; }
    const files = _collectFiles();
    if (!files.length) {
      _setCollectStatus(_collectSource === 'collection'
        ? 'The collection is empty.'
        : 'No files selected.', 'danger');
      return;
    }
    const modalityEl = document.getElementById('collect-modality');
    const descEl     = document.getElementById('collect-desc');
    const btn = document.getElementById('collect-create-btn');
    if (btn) btn.disabled = true;
    _setCollectStatus('Writing to the graph…');
    try {
      const r = await fetch(BASE() + '/api/datasets/collections', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          name,
          modality: modalityEl ? modalityEl.value : '',
          description: descEl ? descEl.value : '',
          files,
        }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { _setCollectStatus(_attrEsc(d.error || `Error ${r.status}`), 'danger'); return; }
      _setCollectStatus(
        `✓ Dataset "${_attrEsc(d.name || name)}" — ${d.files_linked || 0} file(s) linked`
        + (d.stubs_created ? `, ${d.stubs_created} stub node(s) created` : ''),
        'success');
    } catch (e) {
      _setCollectStatus('Write failed: ' + _attrEsc(e.message), 'danger');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // ── Interpret tab ──────────────────────────────────────────────────────

  // Full paths, because that is what the status and run routes resolve against.
  function _interpretPaths() {
    const sel = global.selItems;
    if (sel && sel.size) return [...sel];
    const items = (global.Collection ? global.Collection.items() : []) || [];
    return items.map(f => (f.path ? f.path + '/' : '') + f.name);
  }

  async function loadInterpreterStatus() {
    const list = document.getElementById('interp-status-list');
    const actions = document.getElementById('interp-actions');
    if (!list) return;
    const paths = _interpretPaths();
    if (!paths.length) {
      list.innerHTML = '<div class="small text-muted">Select files to see interpreter status.</div>';
      if (actions) actions.style.display = 'none';
      return;
    }
    list.innerHTML = '<div class="small text-muted">Loading…</div>';
    try {
      const qs = new URLSearchParams();
      paths.forEach(p => qs.append('paths[]', p));
      const r = await fetch(BASE() + '/api/interpreters/status?' + qs.toString());
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        list.innerHTML = `<div class="small text-danger">${_attrEsc(d.error || `Error ${r.status}`)}</div>`;
        if (actions) actions.style.display = 'none';
        return;
      }
      const interpreters = d.interpreters || [];
      if (!interpreters.length) {
        list.innerHTML = '<div class="small text-muted">No interpreter handles the selected files.</div>';
        if (actions) actions.style.display = 'none';
        return;
      }
      list.innerHTML = interpreters.map(it => {
        const files = it.files || {};
        const names = Object.keys(files);
        const ok = names.filter(n => files[n].status === 'ok').length;
        return `<div class="drawer-mi">
          <div class="drawer-mi-label">${_attrEsc(it.name)}${it.version ? ' <span class="text-muted">v' + _attrEsc(it.version) + '</span>' : ''}</div>
          <div class="drawer-mi-detail">${ok}/${names.length} interpreted${
            names.filter(n => files[n].status !== 'ok').length
              ? ' · missing: ' + names.filter(n => files[n].status !== 'ok').map(_attrEsc).join(', ')
              : ''}</div>
        </div>`;
      }).join('');
      // The panel markup hard-hides this row with !important, so removing the
      // inline rule is not enough — set the property with the same priority.
      if (actions) actions.style.setProperty('display', 'flex', 'important');
    } catch (e) {
      list.innerHTML = `<div class="small text-danger">Failed: ${_attrEsc(e.message)}</div>`;
      if (actions) actions.style.display = 'none';
    }
  }

  async function runInterpreters(mode) {
    const el = document.getElementById('interp-run-status');
    const paths = _interpretPaths();
    if (!paths.length) {
      if (el) el.innerHTML = '<span class="text-danger">No files selected.</span>';
      return;
    }
    if (el) el.innerHTML = '<span class="text-muted">Starting…</span>';
    try {
      const r = await fetch(BASE() + '/api/interpreters/run', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ paths, mode: mode === 'all' ? 'all' : 'missing_only' }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        if (el) el.innerHTML = `<span class="text-danger">${_attrEsc(d.error || `Error ${r.status}`)}</span>`;
        return;
      }
      if (el) el.innerHTML = `<span class="text-success">Started — task ${_attrEsc(d.task_id || '')}</span>`;
      if (typeof global.startTaskPoll === 'function') global.startTaskPoll();
    } catch (e) {
      if (el) el.innerHTML = `<span class="text-danger">${_attrEsc(e.message)}</span>`;
    }
  }

  // ── Drawer plumbing ────────────────────────────────────────────────────

  function setTab(tab) {
    const name = ['attribute', 'collect', 'interpret'].includes(tab) ? tab : 'attribute';
    document.querySelectorAll('[data-annotate-tab]').forEach(t =>
      t.classList.toggle('active', t.dataset.annotateTab === name));
    document.querySelectorAll('#annotate-drawer .sharing-tab-panel').forEach(p =>
      p.classList.toggle('active', p.id === `annotate-tab-${name}`));
    if (name === 'attribute') openAttributionPanel();
    if (name === 'collect')   _renderCollectScope();
    if (name === 'interpret') loadInterpreterStatus();
  }

  function _updateScopeLabel() {
    const el = document.getElementById('annotate-scope-label');
    if (!el) return;
    const sel = global.selItems;
    const n = sel ? sel.size : 0;
    const coll = global.Collection ? global.Collection.count() : 0;
    el.textContent = n
      ? `${n} selected`
      : (coll ? `${coll} in collection` : 'nothing selected');
  }

  function open(tab) {
    _updateScopeLabel();
    if (global.Drawers) global.Drawers.open('annotate-drawer');
    setTab(tab || _activeTab());
  }

  function _activeTab() {
    const active = document.querySelector('[data-annotate-tab].active');
    return active ? active.dataset.annotateTab : 'attribute';
  }

  // Apply runs whatever the visible tab's primary button runs. It exists so the
  // drawer footer means the same thing on every tab.
  function apply() {
    const tab = _activeTab();
    if (tab === 'collect')   return createDataset();
    if (tab === 'interpret') return runInterpreters('missing_only');
    return runConfirm();
  }

  // ── Event delegation ───────────────────────────────────────────────────
  //
  // The panel declares intent (`data-annotate-action="confirm"`) and this maps
  // it to a function. Inline on* attributes would work too, but only by
  // resolving against the global scope — which would mean publishing a dozen
  // private functions onto window purely so the markup could find them.
  //
  // Delegated from document rather than bound per element, so a tab whose
  // contents are re-rendered does not need rewiring.

  const ACTIONS = {
    'clear-filter':      clearAnchorFilter,
    'toggle-custom-rel': toggleCustomRel,
    'find-candidates':   runAttribution,
    'select-conf':       attrSelectByConf,       // arg: 'HIGH' | 'MED' | 'LOW'
    'clear-candidates':  attrClearSel,
    'confirm':           runConfirm,
    'collect-source':    setCollectSource,       // arg: 'selection' | 'collection'
    'create-dataset':    createDataset,
    'run-interpreters':  runInterpreters,        // arg: 'all' | 'missing_only'
    'apply':             apply,
  };

  const CHANGES = {
    'anchor-label':    onAnchorLabelChange,
    'target-label':    onTargetLabelChange,
    'filter-property': _loadAnchorPropertyValues,
    'filter-value':    applyAnchorFilter,
    'anchor':          el => selectAttrAnchor(el.value),
  };

  const INPUTS = {
    'anchor-search': el => filterAttrAnchors(el.value),
  };

  document.addEventListener('click', e => {
    const tab = e.target.closest('[data-annotate-tab]');
    if (tab) { setTab(tab.dataset.annotateTab); return; }

    const el = e.target.closest('[data-annotate-action]');
    if (!el) return;
    const handler = ACTIONS[el.dataset.annotateAction];
    if (!handler) return;
    // The custom-relationship toggle is an <a href="#">; without this the page
    // scrolls to the top every time it is clicked.
    e.preventDefault();
    handler(el.dataset.annotateArg);
  });

  document.addEventListener('change', e => {
    const el = e.target.closest('[data-annotate-change]');
    if (!el) return;
    const handler = CHANGES[el.dataset.annotateChange];
    if (handler) handler(el);
  });

  document.addEventListener('input', e => {
    const el = e.target.closest('[data-annotate-input]');
    if (!el) return;
    const handler = INPUTS[el.dataset.annotateInput];
    if (handler) handler(el);
  });

  // The toolbar button calls Annotate.open() inline, matching how the page
  // wires Scan and Share. No listener here — it would run open() twice, and
  // each run re-fetches the label, anchor and suggestion lists.

  // ── Public API ─────────────────────────────────────────────────────────
  global.Annotate = {
    open, setTab, setCollectSource, createDataset, runInterpreters, apply,
    loadInterpreterStatus,
  };

})(window);
