/* Governed views over shared SciDKGraph and Maps Canvas draft primitives. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const base = window.SCIDK_BASE || '';
  const params = new URLSearchParams(location.search);
  const state = {domain: ['research', 'ontology', 'system'].includes(params.get('domain')) ? params.get('domain') : 'research',
    view: ['graph', 'entities', 'sketch'].includes(params.get('view')) ? params.get('view') : 'graph',
    selected: null, records: new Map(), version: 0, next: null, catalog: 'canonical'};
  const styles = [
    {selector: 'node[?provisional]', style: {label: 'data(displayLabel)', 'border-style': 'dashed', 'border-width': 3, 'border-color': '#e67e22', opacity: 0.65}},
    {selector: 'edge[?provisional]', style: {'line-style': 'dashed', 'line-color': '#e67e22'}},
    ...SciDKGraph.schemaStyles
  ];
  const graph = SciDKGraph.init($('kw-graph'), [], {additionalStyles: styles, maxZoom: 1.5, layout: {name: 'preset'}});
  const sketch = SciDKGraph.init($('kw-sketch'), [], {additionalStyles: styles, maxZoom: 1.5, layout: {name: 'preset'}});
  const notice = text => { $('kw-status').textContent = text; };
  let sketchMode = null, connectSource = null, draftSelected = null;
  const edgeId = e => 'projection-edge:' + JSON.stringify([e.source, e.type, e.target]);
  function reset() {
    sketchMode = null; connectSource = null; draftSelected = null; $('kw-draft-inspector').hidden = true; $('kw-connect').setAttribute('aria-pressed', 'false');
    ++state.version; state.records.clear(); state.selected = null; state.next = null;
    graph.elements().remove(); sketch.elements().remove(); $('kw-notes').value = '';
    $('kw-inspection').textContent = ''; $('kw-selection-title').textContent = 'Nothing selected'; $('kw-trust').textContent = 'Select an authorized record.';
    $('kw-entities').replaceChildren(); $('kw-next').hidden = true;
    $('kw-blockers').hidden = true; $('kw-blockers').textContent = '';
    $('kw-edge-filter').replaceChildren(new Option('All relationships', ''));
    $('kw-ask-link').href = base + '/overview'; $('kw-review-link').href = base + '/review';
  }
  async function api(operation, body, domain = state.domain) {
    const response = await fetch(base + '/api/knowledge/' + domain + '/' + operation, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok || data.status !== 'success') throw new Error(response.status === 503 ? 'This Knowledge service is not connected. Ask an administrator to connect the workspace.' : 'Knowledge access is unavailable. Ask an administrator to check source grants and the approved provider.');
    return data.result;
  }
  function url() {
    const query = new URLSearchParams({domain: state.domain, view: state.view});
    if (state.selected?.id && !state.selected.id.startsWith('projection-edge:')) query.set('id', state.selected.id);
    history.replaceState(null, '', location.pathname + '?' + query.toString());
  }
  function layout() {
    const preset = $('kw-layout').value;
    $('kw-panes').dataset.layout = preset;
    ['graph', 'entities', 'sketch'].forEach(view => {
      const visible = preset === 'three' || view === state.view || (preset === 'split' &&
        view === (state.view === 'graph' ? 'entities' : 'graph'));
      $('kw-' + view + '-pane').hidden = !visible;
      $('kw-tab-' + view).setAttribute('aria-selected', String(view === state.view));
      $('kw-tab-' + view).tabIndex = view === state.view ? 0 : -1;
    });
    requestAnimationFrame(() => { graph.resize(); sketch.resize(); }); url();
  }
  function renderEntities() {
    const parent = $('kw-entities'); parent.replaceChildren();
    for (const record of state.records.values()) {
      if (record.source) continue;
      const button = document.createElement('button');
      button.textContent = (record.properties?.name || record.name || record.type) + ' · ' + record.id;
      button.onclick = () => inspect(record); parent.append(button);
    }
    if (!parent.children.length) parent.textContent = 'No permitted records in this result. This is not a global count.';
    $('kw-next').hidden = state.next === null;
  }
  function ingest(result, merge = false) {
    if (!merge) { state.records.clear(); graph.elements().remove(); }
    const nodes = result.nodes || [], edges = result.edges || [];
    for (const entry of nodes) {
      const record = {...entry, ...(result.version ? {projectionVersion: result.version} : {})};
      const id = record.id;
      state.records.set(id, record);
      const data = {id, label: String(record.properties?.name || record.name || id), record};
      const existing = graph.getElementById(id);
      if (existing.length) existing.data(data); else graph.add({group: 'nodes', data});
    }
    for (const edge of edges) {
      const id = edge.id || edgeId(edge); const record = {...edge, id};
      if (!graph.getElementById(edge.source).length || !graph.getElementById(edge.target).length) continue;
      state.records.set(id, record);
      if (!graph.getElementById(id).length) graph.add({group: 'edges', data: {id, source: edge.source, target: edge.target, label: edge.type, record}});
    }
    const values = [...new Set([...state.records.values()].filter(r => r.source).map(r => r.type))].sort();
    $('kw-edge-filter').replaceChildren(new Option('All relationships', ''), ...values.map(value => new Option(value, value)));
    const blockers = result.metadata?.blockers || [];
    $('kw-blockers').hidden = !blockers.length;
    $('kw-blockers').textContent = blockers.length ? 'Ontology catalog is not authoritative. Unresolved conflicts: ' + JSON.stringify(blockers) : '';
    const warnings = result.warnings || [];
    if (warnings.length) {
      $('kw-blockers').hidden = false; $('kw-blockers').textContent += ' Source freshness warnings: ' + JSON.stringify(warnings);
    }
    state.next = result.next_offset ?? null;
    renderEntities();
    graph.layout({name: $('kw-algorithm').value, animate: false, randomize: false}).run();
  }
  async function retrieve(operation, body, merge = false) {
    const version = ++state.version;
    state.selected = null; $('kw-inspection').textContent = '';
    notice('Checking current support and source permissions…');
    try {
      const result = await api(operation, body);
      if (version !== state.version) return;
      ingest(result, merge); notice(result.nodes?.length ? 'Select a record to inspect its sources and current support.' : 'No permitted matches. Try another name or ask an administrator to check source access.');
    } catch (error) { if (version === state.version) { reset(); notice(error.message); } }
  }
  async function inspect(record) {
    const version = ++state.version;
    state.selected = null; $('kw-inspection').textContent = ''; $('kw-trust').textContent = 'Rechecking selected record…';
    try {
      const result = await api(state.domain === 'research' ? 'inspect' : 'context',
        state.domain === 'research' ? {id: record.id} : {id: record.source || record.id, catalog: record.catalog || state.catalog});
      if (version !== state.version) return;
      const fresh = record.source ? (result.edges || []).find(e => (e.id || edgeId(e)) === record.id) :
        (result.nodes || []).find(n => n.id === record.id);
      if (!fresh) throw new Error('Selected record is not available in the current authorized context.');
      // Refresh existing labels/previews too: a property may have become hidden
      // while the node itself remains permitted.
      for (const node of result.nodes || []) {
        const element = graph.getElementById(node.id);
        if (element.length) {
          const current = {...node, ...(result.version ? {projectionVersion: result.version} : {})};
          state.records.set(node.id, current);
          element.data({record: current, label: String(node.properties?.name || node.name || node.id)});
        }
      }
      renderEntities();
      state.selected = {...fresh, id: record.id, ...(result.version ? {projectionVersion: result.version} : {}),
        ...(state.domain === 'ontology' ? {catalog: record.catalog || state.catalog} : {})};
      $('kw-trust').textContent = state.domain === 'research' ?
        (fresh.curation_status === 'legacy/unreviewed' ? 'Legacy / unreviewed. Graph presence does not establish acceptance or application.' :
          'Accepted and applied; epistemic status is recorded separately in support.') :
        'Generated projection; inspect source revisions, hashes, freshness and catalog authority. This is not a reviewed research assertion.';
      $('kw-selection-title').textContent = state.selected.properties?.name || state.selected.name || state.selected.type || 'Selected knowledge';
      $('kw-inspection').textContent = JSON.stringify(state.selected, null, 2);
      $('kw-ask-link').href = base + '/overview?' + new URLSearchParams({domain: state.domain, id: record.id});
      $('kw-review-link').href = base + '/review?domain=' + state.domain + '&id=' + encodeURIComponent(record.id);
      url();
    } catch (error) { if (version === state.version) { reset(); notice(error.message); } }
  }
  graph.on('tap', 'node,edge', event => inspect(event.target.data('record')));
  sketch.on('tap', 'node,edge', event => {
    const data = event.target.data();
    draftSelected = event.target; $('kw-selection-title').textContent = data.displayLabel || data.label || 'Selected draft';
    $('kw-draft-inspector').hidden = !data.provisional || !event.target.isNode();
    $('kw-edit-name').value = data.displayLabel || '';
    if (sketchMode === 'connect' && event.target.isNode()) {
      if (!connectSource) { connectSource = data.id; $('kw-sketch-help').textContent = 'Now select the destination node.'; }
      else if (connectSource !== data.id) {
        SciDKCanvas.add(sketch, SciDKCanvas.provisionalEdge(connectSource, data.id, $('kw-edge-type').value.trim() || 'RELATES_TO'));
        connectSource = null; sketchMode = null; $('kw-connect').setAttribute('aria-pressed', 'false');
        $('kw-sketch-help').textContent = 'Draft connection created. Save your private draft to keep it.';
      }
      return;
    }
    if (data.reference) {
      inspect({id: data.reference, source: data.source, catalog: data.catalog});
    } else {
      $('kw-trust').textContent = 'Private user-authored draft. Marker is planning intent, not an actual submission or review state.';
      $('kw-inspection').textContent = JSON.stringify(data, null, 2);
    }
    $('kw-edge-source').value = data.id;
  });
  $('kw-place-node').onclick = () => { sketchMode = 'place'; connectSource = null; $('kw-connect').setAttribute('aria-pressed', 'false'); $('kw-sketch-help').textContent = 'Click an empty point on the canvas to place a private draft node.'; };
  sketch.on('tap', event => {
    if (event.target !== sketch || sketchMode !== 'place') return;
    const node = SciDKCanvas.provisionalNode(sketch, $('kw-draft-type').value.trim() || 'Concept', $('kw-draft-name').value.trim() || 'New concept');
    node.position = event.position; SciDKCanvas.add(sketch, node); sketchMode = null;
    $('kw-sketch-help').textContent = 'Node placed. Select it to edit its name in the inspector, or drag to arrange.';
  });
  $('kw-connect').onclick = () => { sketchMode = sketchMode === 'connect' ? null : 'connect'; connectSource = null; $('kw-connect').setAttribute('aria-pressed', String(sketchMode === 'connect')); $('kw-sketch-help').textContent = sketchMode ? 'Select the source node, then the destination node.' : 'Connection cancelled.'; };
  $('kw-edit-apply').onclick = () => {
    const name = $('kw-edit-name').value.trim();
    if (!name || !draftSelected?.isNode() || !draftSelected.data('provisional')) return;
    draftSelected.data({displayLabel: name, properties: {...draftSelected.data('properties'), name}});
    $('kw-inspection').textContent = JSON.stringify(draftSelected.data(), null, 2);
  };
  async function changeDomain() {
    reset(); state.domain = $('kw-domain').value; state.catalog = 'canonical';
    $('kw-search-form').hidden = state.domain !== 'research';
    $('kw-context-form').hidden = state.domain === 'research';
    $('kw-catalog-label').hidden = state.domain !== 'ontology';
    $('kw-context-id').value = state.domain === 'system' ? 'workflow:csv-import' : 'ontology:catalog';
    const version = state.version;
    try {
      const prefs = await api('load', {kind: 'layout'});
      if (version !== state.version) return;
      $('kw-layout').value = prefs.preset || 'single';
      if (!params.has('view')) state.view = prefs.view || 'graph';
      layout();
    } catch (error) { if (version === state.version) { layout(); notice(error.message); } }
    if (version !== state.version) return;
    if (state.domain !== 'research') await retrieve('context', {id: $('kw-context-id').value, catalog: state.catalog});
  }
  $('kw-domain').value = state.domain;
  $('kw-domain').onchange = changeDomain;
  ['graph', 'entities', 'sketch'].forEach((view, index, views) => {
    $('kw-tab-' + view).onclick = () => { state.view = view; layout(); };
    $('kw-tab-' + view).onkeydown = event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % 3;
      if (event.key === 'ArrowLeft') next = (index + 2) % 3;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = 2;
      if (next !== undefined) { event.preventDefault(); $('kw-tab-' + views[next]).focus(); $('kw-tab-' + views[next]).click(); }
    };
  });
  $('kw-layout').onchange = layout;
  const resize = new ResizeObserver(() => { graph.resize(); sketch.resize(); });
  resize.observe($('kw-graph')); resize.observe($('kw-sketch'));
  $('kw-search-form').onsubmit = event => { event.preventDefault(); retrieve('search', {q: $('kw-search').value, label: $('kw-label').value}); };
  $('kw-next').onclick = () => retrieve('search', {q: $('kw-search').value, label: $('kw-label').value, offset: state.next});
  $('kw-context-form').onsubmit = event => { event.preventDefault(); state.catalog = $('kw-catalog').value; retrieve('context', {id: $('kw-context-id').value, catalog: state.catalog}); };
  $('kw-expand').onclick = () => {
    if (!state.selected || state.selected.source) { notice('Select a node first.'); return; }
    retrieve(state.domain === 'research' ? 'expand' : 'context', state.domain === 'research' ?
      {id: state.selected.id} : {id: state.selected.id, catalog: state.catalog}, true);
  };
  $('kw-fit').onclick = () => graph.fit();
  $('kw-apply-layout').onclick = () => graph.layout({name: $('kw-algorithm').value, animate: false, randomize: false}).run();
  $('kw-edge-filter').onchange = () => graph.edges().forEach(e => e.style('display', !$('kw-edge-filter').value || e.data('record').type === $('kw-edge-filter').value ? 'element' : 'none'));
  $('kw-color').oninput = () => graph.nodes(':selected').style('background-color', $('kw-color').value);
  $('kw-show-entities').onclick = () => { state.view = 'entities'; layout(); };
  $('kw-show-graph').onclick = () => { state.view = 'graph'; layout(); };
  $('kw-add-node').onclick = () => {
    const name = $('kw-draft-name').value.trim() || 'New concept', type = $('kw-draft-type').value.trim();
    if (!name || !type) { notice('Enter a draft name and type.'); return; }
    SciDKCanvas.add(sketch, SciDKCanvas.provisionalNode(sketch, type, name));
    sketch.fit(); notice('Draft added privately; no assertion or graph fact was created.');
  };
  $('kw-add-edge').onclick = () => {
    const source = $('kw-edge-source').value, target = $('kw-edge-target').value, label = $('kw-edge-type').value.trim();
    if (!sketch.getElementById(source).isNode() || !sketch.getElementById(target).isNode() || !label) { notice('Choose two existing draft/reference node IDs and a relationship type.'); return; }
    SciDKCanvas.add(sketch, SciDKCanvas.provisionalEdge(source, target, label));
  };
  $('kw-remove-draft').onclick = () => SciDKCanvas.remove(sketch);
  $('kw-arrange-draft').onclick = () => { sketch.layout({name: 'grid', animate: false}).run(); sketch.fit(undefined, 50); };
  $('kw-set-marker').onclick = () => sketch.elements(':selected').filter(e => e.data('provisional')).data('marker', $('kw-marker').value);
  $('kw-add-reference').onclick = async () => {
    if (!state.selected || state.selected.source) { notice('Select an authorized knowledge node first.'); return; }
    const record = state.selected, version = state.version;
    await inspect(record);
    if (!state.selected || state.selected.id !== record.id || state.version !== version + 1) return;
    if (!sketch.getElementById(record.id).length) sketch.add({group: 'nodes', data: {id: record.id, reference: record.id,
      ...(state.domain !== 'research' ? {reference_version: state.selected.projectionVersion} : {}),
      catalog: state.selected.catalog || state.catalog,
      label: String(state.selected.properties?.name || state.selected.name || state.selected.type || state.selected.id)}});
    sketch.fit(); notice('Stable reference added. Its metadata will be reauthorized when reopened.');
  };
  function serialize(cy, draft) {
    return cy.elements().filter(element => draft || state.domain === 'research' || element.isNode()).map(element => {
      const data = element.data();
      const safe = draft && data.provisional ? {...data} : {id: data.id, reference: data.reference || data.id};
      if (state.domain === 'ontology' && !data.provisional) safe.catalog = data.catalog || state.catalog;
      if (state.domain !== 'research' && !data.provisional) safe.reference_version = data.reference_version || data.record?.projectionVersion;
      delete safe.record;
      if (element.isEdge()) { safe.source = data.source; safe.target = data.target; }
      const result = {group: element.isNode() ? 'nodes' : 'edges', data: safe, position: element.position()};
      if (element.isNode()) {
        const rgb = element.style('background-color').match(/\d+/g);
        if (rgb?.length >= 3) result.color = '#' + rgb.slice(0, 3).map(n => Number(n).toString(16).padStart(2, '0')).join('');
      }
      return result;
    });
  }
  async function save(kind) {
    const domain = state.domain, version = state.version;
    const canvas = kind === 'layout' ? {preset: $('kw-layout').value, view: state.view} :
      {elements: serialize(kind === 'sketch' ? sketch : graph, kind === 'sketch'), notes: kind === 'sketch' ? $('kw-notes').value : ''};
    try {
      await api('save', {kind, canvas}, domain);
      if (domain === state.domain && version === state.version) notice('Saved private ' + kind + ' using existing Canvas session storage.');
    } catch (error) { if (domain === state.domain) notice(error.message); }
  }
  async function load(kind) {
    const version = ++state.version, domain = state.domain;
    $('kw-inspection').textContent = ''; state.selected = null;
    if (kind === 'sketch') { sketch.elements().remove(); $('kw-notes').value = ''; }
    else { graph.elements().remove(); state.records.clear(); renderEntities(); }
    try {
      const saved = await api('load', {kind}, domain);
      const records = new Map(), references = new Map();
      for (const element of saved.elements || []) {
        if (element.data.reference) {
          const result = await api(domain === 'research' ? 'inspect' : 'context',
            domain === 'research' ? {id: element.data.reference} : {id: element.data.reference, catalog: element.data.catalog || state.catalog}, domain);
          if (domain !== 'research' && result.version !== element.data.reference_version) throw new Error('Saved source version is no longer available under current authorization.');
          for (const node of result.nodes || []) records.set(node.id, {...node,
            ...(result.version ? {projectionVersion: result.version} : {}),
            ...(domain === 'ontology' ? {catalog: element.data.catalog || state.catalog} : {})});
          for (const edge of result.edges || []) references.set(edge.id || edgeId(edge), edge);
        }
      }
      if (version !== state.version || domain !== state.domain) return;
      if (kind === 'graph') {
        const wanted = new Set((saved.elements || []).filter(e => e.group === 'nodes').map(e => e.data.id));
        ingest({nodes: [...records.values()].filter(n => wanted.has(n.id)),
          edges: [...references.values()].filter(e => wanted.has(e.source) && wanted.has(e.target))});
        for (const element of saved.elements || []) {
          const entry = graph.getElementById(element.data.id); entry.position(element.position);
          if (element.color) entry.style('background-color', element.color);
        }
      } else {
        const elements = (saved.elements || []).map(element => ({...element, data: {...element.data,
          label: (element.data.reference && (records.get(element.data.reference)?.properties?.name || records.get(element.data.reference)?.name)) ||
            element.data.reference || element.data.displayLabel || element.data.label}}));
        sketch.add(elements); $('kw-notes').value = saved.notes || ''; sketch.fit();
      }
      notice('Reopened private ' + kind + '; all stored references were reauthorized.');
    } catch (error) { if (version === state.version) { reset(); notice(error.message); } }
  }
  $('kw-save-layout').onclick = () => save('layout');
  $('kw-save-graph').onclick = () => save('graph'); $('kw-load-graph').onclick = () => load('graph');
  $('kw-save-sketch').onclick = () => save('sketch'); $('kw-load-sketch').onclick = () => load('sketch');
  const initialId = params.get('id');
  changeDomain().then(async () => {
    if (initialId && state.domain === 'research') {
      await retrieve('expand', {id: initialId});
      const selected = state.records.get(initialId);
      if (selected && state.domain === 'research') await inspect(selected);
    }
  });
})();
