/* Opt-in shell: reuse services, never send metadata to a provider. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  if (!$('gui-files')) return;
  const base = window.SCIDK_BASE || '';
  const state = {tab: 'Files', inspectorTab: 'Metadata', selected: {}, expanded: false, version: 0};
  const browser = document.querySelector('.files-page');
  let closed = false;
  let returnFocus;
  function raw(value, parent) {
    if (value && typeof value === 'object') {
      const details = document.createElement('details'); details.open = true;
      const summary = document.createElement('summary'); summary.textContent = 'Nested metadata / raw JSON';
      const pre = document.createElement('pre'); pre.textContent = JSON.stringify(value, null, 2);
      details.append(summary, pre); parent.append(details);
    } else { const pre = document.createElement('pre'); pre.textContent = String(value ?? 'Not recorded'); parent.append(pre); }
  }
  async function json(url) {
    const response = await fetch(base + url);
    if (!response.ok) throw new Error('Service unavailable (' + response.status + ')');
    return response.json();
  }
  async function render() {
    const version = ++state.version;
    const selection = state.selected[state.tab];
    $('shared-inspector').hidden = !selection || closed;
    browser.classList.toggle('with-inspector', !!selection && !closed);
    $('gui-datasets').classList.toggle('with-inspector', !!selection && !closed);
    if (!selection) return;
    $('shared-inspector').classList.toggle('expanded', state.expanded);
    $('inspector-expand').textContent = state.expanded ? 'Restore docked inspector' : 'Expand';
    $('inspector-expand').setAttribute('aria-expanded', String(state.expanded));
    const record = selection.record;
    $('inspector-title').textContent = (selection.kind === 'dataset' ? 'Dataset: ' : 'File / folder: ') + (record.name || record.path || selection.key);
    $('dataset-sharing').hidden = selection.kind !== 'dataset';
    const knowledge = $('dataset-knowledge');
    if (knowledge) {
      knowledge.hidden = selection.kind !== 'dataset' || !record.entity_ref;
      knowledge.href = base + '/knowledge?domain=research&id=' + encodeURIComponent(record.entity_ref || '');
    }
    const review = $('dataset-review');
    if (review) {
      review.hidden = selection.kind !== 'dataset' || !record.entity_ref;
      review.href = base + '/review?domain=research&id=' + encodeURIComponent(record.entity_ref || '');
    }
    document.querySelectorAll('[data-inspector-tab]').forEach(b => {
      const active = b.dataset.inspectorTab === state.inspectorTab;
      b.setAttribute('aria-selected', String(active)); b.setAttribute('tabindex', active ? '0' : '-1');
    });
    $('inspector-content').setAttribute('aria-labelledby', 'inspector-tab-' + state.inspectorTab.toLowerCase());
    const content = $('inspector-content'); content.replaceChildren();
    if (state.inspectorTab === 'Metadata') raw(record, content);
    if (state.inspectorTab === 'Provenance') {
      raw({provider_id: record.provider_id, scan_id: record.scan_id, source: record.source,
        provenance: record.provenance, evidence: record.evidence}, content);
      const p = document.createElement('p'); p.textContent = 'Only stored provenance is shown. Acceptance and current support have not been established for this browser record.'; content.append(p);
    }
    if (state.inspectorTab === 'Annotations') {
      content.textContent = 'Loading annotations…';
      try {
        // Never issue an unfiltered annotations request when no stable identity exists.
        if (!selection.key) throw new Error('No annotation identity available');
        const data = await json('/api/annotations?file_id=' + encodeURIComponent(selection.key) + '&limit=100');
        if (version !== state.version) return;
        content.replaceChildren(); raw(data.items, content);
        const p = document.createElement('p'); p.textContent = 'Annotations use the stored object identity. Use the existing Annotate drawer for file attribution, collection and interpretation.'; content.append(p);
      } catch (error) { if (version === state.version) content.textContent = error.message; }
    }
  }
  function select(selection) {
    returnFocus = document.activeElement; closed = false; state.selected[state.tab] = selection;
    if ($('sharing-guide')) {
      $('sharing-guide').hidden = true; $('sharing-draft').textContent = '';
      $('sharing-status').textContent = ''; $('sharing-download').disabled = true;
      document.querySelectorAll('[data-sharing-field]').forEach(input => { input.value = ''; });
    }
    render();
  }
  function tab(name) {
    closed = false; state.tab = name;
    browser.hidden = name !== 'Files'; $('gui-datasets').hidden = name !== 'Datasets';
    $('gui-files-tab').setAttribute('aria-selected', String(name === 'Files'));
    $('gui-datasets-tab').setAttribute('aria-selected', String(name === 'Datasets'));
    $('gui-files-tab').setAttribute('tabindex', name === 'Files' ? '0' : '-1');
    $('gui-datasets-tab').setAttribute('tabindex', name === 'Datasets' ? '0' : '-1'); render();
  }
  $('gui-files-tab').onclick = () => tab('Files');
  $('gui-datasets-tab').onclick = () => tab('Datasets');
  function closeInspector() { closed = true; render(); returnFocus?.focus(); }
  $('inspector-close').onclick = closeInspector;
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !$('shared-inspector').hidden) {
      event.preventDefault(); closeInspector();
    }
  });
  $('inspector-expand').onclick = () => { state.expanded = !state.expanded; render(); };
  document.querySelectorAll('[data-inspector-tab]').forEach(b => b.onclick = () => { state.inspectorTab = b.dataset.inspectorTab; render(); });
  function keyboardTabs(buttons) {
    buttons.forEach((button, index) => { button.onkeydown = event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % buttons.length;
      if (event.key === 'ArrowLeft') next = (index + buttons.length - 1) % buttons.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = buttons.length - 1;
      if (next !== undefined) { event.preventDefault(); buttons[next].focus(); buttons[next].click(); }
    }; });
  }
  keyboardTabs([$('gui-files-tab'), $('gui-datasets-tab')]);
  keyboardTabs([...document.querySelectorAll('[data-inspector-tab]')]);
  document.addEventListener('scidk:inspect', event => { if (state.tab === 'Files') select(event.detail); });
  function items(records, parent, graph) {
    parent.replaceChildren();
    if (!records.length) { parent.textContent = 'No records found.'; return; }
    records.forEach(item => {
      const record = graph ? {...item.properties, name: item.name} : item;
      const key = graph ? item.element_id || item.id : item.id;
      const button = document.createElement('button'); button.textContent = record.name || record.path || key;
      button.onclick = () => select({kind: graph ? 'dataset' : 'file', key, record}); parent.append(button);
    });
  }
  let searchVersion = 0;
  $('dataset-search').onsubmit = async event => {
    event.preventDefault(); const version = ++searchVersion; $('dataset-results').textContent = 'Searching…';
    try {
      const data = await json('/api/canvas/nodes/search?label=Dataset&limit=100&q=' + encodeURIComponent($('dataset-query').value));
      if (version === searchVersion) items(data.results, $('dataset-results'), true);
    } catch (error) { if (version === searchVersion) $('dataset-results').textContent = error.message; }
  };
  json('/api/datasets').then(data => items(data, $('indexed-datasets'), false)).catch(error => { $('indexed-datasets').textContent = error.message; });
  if ($('sharing-start')) {
    let sharingVersion = 0;
    $('sharing-start').onclick = () => { $('sharing-guide').hidden = false; };
    document.querySelectorAll('[data-sharing-field]').forEach(input => input.oninput = () => {
      ++sharingVersion; $('sharing-download').disabled = true;
    });
    async function prepare(download) {
      const selected = state.selected.Datasets;
      // A Neo4j element ID/path is not a stable curation identity.
      const id = selected?.record.entity_ref;
      if (!id) { $('sharing-status').textContent = 'Unavailable: this dataset has no stable curation identity or authorized membership.'; return; }
      const version = ++sharingVersion;
      $('sharing-download').disabled = true;
      $('sharing-status').textContent = 'Checking dataset permissions and current support…';
      const fields = {};
      document.querySelectorAll('[data-sharing-field]').forEach(input => { fields[input.dataset.sharingField] = input.value; });
      try {
        const response = await fetch(base + '/api/plugins/nih_dms/datasets/' + encodeURIComponent(id) + '/prepare', {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({fields, download})
        });
        if (!response.ok) {
          const error = await response.json(); throw new Error(error.error || 'Dataset preparation unavailable.');
        }
        if (download) {
          const blob = await response.blob();
          if (version !== sharingVersion || selected !== state.selected.Datasets) return;
          const url = URL.createObjectURL(blob); const link = document.createElement('a');
          link.href = url; link.download = 'dataset-sharing-draft.zip'; link.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
          $('sharing-status').textContent = 'Read README.md and review the scripts before preparing a local copy.';
        } else {
          const data = await response.json();
          if (version !== sharingVersion || selected !== state.selected.Datasets) return;
          if (data.status !== 'success') throw new Error(data.error || 'Dataset preparation unavailable.');
          $('sharing-draft').textContent = data.markdown;
          $('sharing-status').textContent = data.notice;
          if (!data.package_ready) return;
        }
        $('sharing-download').disabled = false;
      } catch (error) {
        if (version === sharingVersion && selected === state.selected.Datasets) $('sharing-status').textContent = error.message;
      }
    }
    $('sharing-preview').onclick = () => prepare(false);
    $('sharing-download').onclick = () => prepare(true);
  }
})();
