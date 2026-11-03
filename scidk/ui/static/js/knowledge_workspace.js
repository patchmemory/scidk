/* Governed views over shared SciDKGraph and Maps Canvas draft primitives. */
(function () {
  'use strict';
  // Sketch-only mode: the Knowledge → Sketch tab renders just the draft canvas. The governed-projection
  // controls this script also drives are absent there, so lookups fall back to detached stand-ins.
  const sketchOnly = document.getElementById('knowledge-workspace')?.dataset.kwMode === 'sketch';
  // Visual Sketch: the Knowledge -> Sketch tab has the connect/relationship panel and the ordinary inspector. The
  // governed workspace page keeps its original controls, so every visual handler below checks this flag.
  const visual = !!document.getElementById('kw-rel-panel');
  const stubs = new Map();
  const $ = id => document.getElementById(id) || (stubs.has(id) ? stubs.get(id) : (stubs.set(id, document.createElement('div')), stubs.get(id)));
  const base = window.SCIDK_BASE || '';
  const params = new URLSearchParams(location.search);
  const state = {domain: ['research', 'ontology', 'system'].includes(params.get('domain')) ? params.get('domain') : 'research',
    view: ['graph', 'entities', 'sketch'].includes(params.get('view')) ? params.get('view') : 'graph',
    selected: null, records: new Map(), version: 0, next: null, catalog: 'canonical'};
  const styles = [
    {selector: 'node[?provisional]', style: {label: 'data(displayLabel)', 'border-style': 'dashed', 'border-width': 3, 'border-color': '#e67e22', opacity: 0.65}},
    {selector: 'edge[?provisional]', style: {'line-style': 'dashed', 'line-color': '#e67e22'}},
    {selector: 'node.kw-connect-source', style: {'border-style': 'solid', 'border-width': 5, 'border-color': '#165dba', opacity: 1}},
    ...SciDKGraph.schemaStyles
  ];
  const graph = SciDKGraph.init($('kw-graph'), [], {additionalStyles: styles, maxZoom: 1.5, layout: {name: 'preset'}});
  const sketch = SciDKGraph.init($('kw-sketch'), [], {additionalStyles: styles, maxZoom: 1.5, layout: {name: 'preset'}});
  const notice = text => { $('kw-status').textContent = text; };
  let sketchMode = null, connectSource = null, draftSelected = null;
  const edgeId = e => 'projection-edge:' + JSON.stringify([e.source, e.type, e.target]);
  function reset() {
    sketchMode = null; connectSource = null; draftSelected = null; $('kw-draft-inspector').hidden = true; $('kw-connect').setAttribute('aria-pressed', 'false');
    if (visual) { setTool('select'); showInspector(null); }
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
    if (sketchOnly && (!response.ok || data.status !== 'success')) throw new Error('Saving and reopening private drafts is not available here. Your sketch still works on this page.');
    if (!response.ok || data.status !== 'success') throw new Error(response.status === 503 ? 'This Knowledge service is not connected. Ask an administrator to configure existing governed state and run POST /api/knowledge/readiness. See docs/demo/scidk-operational-startup.md.' : state.domain === 'research' ? 'Knowledge access was refused. Ask an administrator to check your research_browse purpose, Resource and evidence grants.' : 'Knowledge access is unavailable. Ask an administrator to check source grants and the approved provider.');
    return data.result;
  }
  function url() {
    if (sketchOnly) return;
    const query = new URLSearchParams({governed: '1', domain: state.domain, view: state.view});
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
  // ---- Visual Sketch tools (Knowledge -> Sketch tab) -------------------------------------------------------
  // Nothing here talks to the server except the existing private save/reopen; drafts are `provisional` canvas
  // elements, never graph writes. Type and relationship suggestions come from the existing schema labels API.
  const toolHelp = {
    select: 'Select and move: click a node or relationship to edit it, drag nodes to arrange them.',
    pan: 'Pan: drag the canvas to move around. Scroll or use + / \u2212 to zoom.',
    place: 'Add node: choose a type and name, then click an empty point on the canvas to place it.',
    connect: 'Connect nodes: click the source node, then the target node, then choose the relationship.'
  };
  let tool = 'select';
  const nameOf = element => element.data('displayLabel') || element.data('label') || element.id();
  function clearConnect() {
    connectSource = null; sketch.nodes().removeClass('kw-connect-source'); $('kw-rel-panel').hidden = true; pendingEdge = null;
    sketch.resize();   // showing/hiding a panel moves the canvas; re-measure so clicks map to the right point
  }
  let pendingEdge = null;
  function setTool(next) {
    tool = next; sketchMode = next === 'place' || next === 'connect' ? next : null; clearConnect();
    document.querySelectorAll('[data-tool]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.tool === next)));
    sketch.userPanningEnabled(next !== 'select'); sketch.boxSelectionEnabled(next === 'select');
    sketch.autoungrabify(next === 'pan' || next === 'connect');
    $('kw-add-panel').hidden = next !== 'place';
    $('kw-sketch').dataset.tool = next;
    $('kw-sketch-help').textContent = toolHelp[next];
    sketch.resize();
  }
  function showInspector(element) {
    draftSelected = element;
    const editable = !!element && !!element.data('provisional');
    $('kw-draft-inspector').hidden = !editable;
    $('kw-inspector-empty').hidden = !!element;
    $('kw-selection-title').textContent = element ? nameOf(element) : 'Nothing selected';
    $('kw-inspection').textContent = element ? JSON.stringify(element.data(), null, 2) : '';
    if (!element) return;
    $('kw-node-form').hidden = !element.isNode(); $('kw-edge-form').hidden = element.isNode();
    const properties = element.data('properties') || {};
    if (element.isNode()) {
      $('kw-edit-name').value = element.data('displayLabel') || '';
      $('kw-edit-type').value = element.data('label') || '';
      $('kw-edit-notes').value = properties.notes || '';
    } else {
      const source = sketch.getElementById(element.data('source')), target = sketch.getElementById(element.data('target'));
      $('kw-edge-from').textContent = source.length ? nameOf(source) : '(missing node)';
      $('kw-edge-to').textContent = target.length ? nameOf(target) : '(missing node)';
      $('kw-edit-rel').value = element.data('label') || '';
      $('kw-edit-edge-notes').value = properties.notes || '';
    }
  }
  function selectDraft(element) { sketch.elements().unselect(); element.select(); showInspector(element); }
  function applyDraftEdits() {
    const element = draftSelected;
    if (!element || !element.data('provisional')) return;
    if (element.isNode()) {
      const name = $('kw-edit-name').value.trim(), type = $('kw-edit-type').value.trim() || 'Concept';
      if (!name) return;
      element.data({displayLabel: name, label: type, baseLabel: type,
        properties: {...element.data('properties'), name, notes: $('kw-edit-notes').value}});
    } else {
      const type = $('kw-edit-rel').value.trim();
      if (!type) return;
      element.data({label: type, baseLabel: type, properties: {...element.data('properties'), notes: $('kw-edit-edge-notes').value}});
    }
    $('kw-selection-title').textContent = nameOf(element);
    $('kw-inspection').textContent = JSON.stringify(element.data(), null, 2);
  }
  function addTypeValue() {
    const chosen = $('kw-add-type').value;
    return chosen === '__free__' ? ($('kw-add-free').value.trim() || 'Concept') : (chosen || 'Concept');
  }
  function openRelationshipPanel(sourceId, targetId) {
    pendingEdge = {source: sourceId, target: targetId};
    $('kw-rel-from').textContent = nameOf(sketch.getElementById(sourceId));
    $('kw-rel-to').textContent = nameOf(sketch.getElementById(targetId));
    $('kw-rel-panel').hidden = false; sketch.resize(); $('kw-rel-type').focus(); $('kw-rel-type').select();
    $('kw-sketch-help').textContent = 'Choose or type the relationship, then create it.';
  }
  async function loadSchemaVocabulary() {
    // Existing schema entity types / relationship types where available; freeform always works.
    try {
      const response = await fetch(base + '/api/labels');
      if (!response.ok) return;
      const labels = (await response.json()).labels || [];
      const types = labels.map(label => label.name).filter(Boolean).sort();
      const relationships = [...new Set(labels.flatMap(label => (label.relationships || []).map(rel => rel.type)).filter(Boolean))].sort();
      const group = $('kw-add-schema-types'); group.replaceChildren(...types.map(type => new Option(type, type)));
      group.hidden = !types.length;
      $('kw-type-options').replaceChildren(...types.map(type => new Option(type)));
      $('kw-rel-options').replaceChildren(...relationships.map(type => new Option(type)));
    } catch (error) { /* offline or not permitted: freeform concepts and relationship names still work */ }
  }
  graph.on('tap', 'node,edge', event => inspect(event.target.data('record')));
  sketch.on('tap', 'node,edge', event => {
    const data = event.target.data();
    if (visual) {
      if (tool === 'connect' && event.target.isNode()) {
        if (!connectSource) {
          connectSource = data.id; event.target.addClass('kw-connect-source');
          $('kw-sketch-help').textContent = 'Source: ' + nameOf(event.target) + '. Now click the target node.';
        } else if (connectSource === data.id) {
          $('kw-sketch-help').textContent = 'Choose a different node as the target.';
        } else openRelationshipPanel(connectSource, data.id);
        return;
      }
      showInspector(event.target);
      return;
    }
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
  $('kw-place-node').onclick = () => {
    if (visual) { setTool(tool === 'place' ? 'select' : 'place'); if (tool === 'place') $('kw-add-name').focus(); return; }
    sketchMode = 'place'; connectSource = null; $('kw-connect').setAttribute('aria-pressed', 'false'); $('kw-sketch-help').textContent = 'Click an empty point on the canvas to place a private draft node.';
  };
  sketch.on('tap', event => {
    if (event.target !== sketch) return;
    if (visual) {
      if (tool === 'place') {
        const type = addTypeValue(), name = $('kw-add-name').value.trim() || type;
        const node = SciDKCanvas.provisionalNode(sketch, type, name);
        node.position = event.position; SciDKCanvas.add(sketch, node);
        $('kw-add-name').value = ''; selectDraft(sketch.getElementById(node.data.id));
        $('kw-sketch-help').textContent = 'Added "' + name + '". Rename it in the inspector, click again to add another, or choose Select / move.';
        notice('Draft added to your private sketch. Nothing was written to the knowledge graph.');
      } else if (tool === 'select') showInspector(null);
      return;
    }
    if (sketchMode !== 'place') return;
    const node = SciDKCanvas.provisionalNode(sketch, $('kw-draft-type').value.trim() || 'Concept', $('kw-draft-name').value.trim() || 'New concept');
    node.position = event.position; SciDKCanvas.add(sketch, node); sketchMode = null;
    $('kw-sketch-help').textContent = 'Node placed. Select it to edit its name in the inspector, or drag to arrange.';
  });
  $('kw-connect').onclick = () => {
    if (visual) { setTool(tool === 'connect' ? 'select' : 'connect'); return; }
    sketchMode = sketchMode === 'connect' ? null : 'connect'; connectSource = null; $('kw-connect').setAttribute('aria-pressed', String(sketchMode === 'connect')); $('kw-sketch-help').textContent = sketchMode ? 'Select the source node, then the destination node.' : 'Connection cancelled.';
  };
  $('kw-edit-apply').onclick = () => {
    if (visual) { applyDraftEdits(); return; }
    const name = $('kw-edit-name').value.trim();
    if (!name || !draftSelected?.isNode() || !draftSelected.data('provisional')) return;
    draftSelected.data({displayLabel: name, properties: {...draftSelected.data('properties'), name}});
    $('kw-inspection').textContent = JSON.stringify(draftSelected.data(), null, 2);
  };
  if (visual) {
    document.querySelectorAll('[data-tool]').forEach(button => {
      if (button.id !== 'kw-place-node' && button.id !== 'kw-connect') button.onclick = () => setTool(button.dataset.tool);
    });
    $('kw-add-type').onchange = () => { $('kw-add-free-wrap').hidden = $('kw-add-type').value !== '__free__'; };
    $('kw-add-center').onclick = () => {
      const type = addTypeValue(), name = $('kw-add-name').value.trim() || type;
      const node = SciDKCanvas.provisionalNode(sketch, type, name); SciDKCanvas.add(sketch, node);
      $('kw-add-name').value = ''; selectDraft(sketch.getElementById(node.data.id));
      notice('Draft added to your private sketch. Nothing was written to the knowledge graph.');
    };
    $('kw-add-done').onclick = () => setTool('select');
    $('kw-rel-create').onclick = () => {
      const label = $('kw-rel-type').value.trim();
      if (!pendingEdge) return;
      if (!label) { notice('Choose or type a relationship, for example RELATES_TO.'); return; }
      const edge = SciDKCanvas.provisionalEdge(pendingEdge.source, pendingEdge.target, label);
      SciDKCanvas.add(sketch, edge); clearConnect();
      selectDraft(sketch.getElementById(edge.data.id));
      $('kw-sketch-help').textContent = 'Relationship drafted. Edit it in the inspector, or connect another pair.';
      notice('Draft relationship added to your private sketch. Nothing was written to the knowledge graph.');
    };
    $('kw-rel-cancel').onclick = () => { clearConnect(); $('kw-sketch-help').textContent = toolHelp.connect; };
    $('kw-rel-type').onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); $('kw-rel-create').click(); } };
    ['kw-edit-name', 'kw-edit-type', 'kw-edit-notes', 'kw-edit-rel', 'kw-edit-edge-notes'].forEach(id => { $(id).oninput = applyDraftEdits; });
    $('kw-sk-remove').onclick = () => { SciDKCanvas.remove(sketch); showInspector(null); };
    $('kw-sk-arrange').onclick = () => {
      const edges = sketch.edges().length;
      sketch.layout({name: edges ? 'cose' : 'grid', animate: false, fit: true, padding: 50}).run();
      sketch.fit(undefined, 50); notice('Canvas arranged and fitted. Positions are saved with your private draft.');
    };
    $('kw-sk-fit').onclick = () => sketch.fit(undefined, 50);
    const zoom = factor => sketch.zoom({level: Math.min(1.5, Math.max(0.1, sketch.zoom() * factor)), renderedPosition: {x: sketch.width() / 2, y: sketch.height() / 2}});
    $('kw-sk-zoom-in').onclick = () => zoom(1.25); $('kw-sk-zoom-out').onclick = () => zoom(0.8);
    $('kw-sketch').addEventListener('keydown', event => {
      if (event.key === 'Escape') setTool('select');
    });
    // Panels above the canvas change height as the user works, which moves the canvas on the page. Re-measure at the
    // start of every pointer gesture so a click always lands on the point the user sees.
    $('kw-sketch').parentElement.addEventListener('mousedown', () => sketch.resize(), true);
    setTool('select');
    loadSchemaVocabulary();
  }
  async function changeDomain() {
    if (sketchOnly) { reset(); state.view = 'sketch'; layout(); return; }
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
  // Knowledge -> Sketch keeps its private draft in the user's existing canvas session (the same per-user record the
  // governed adapter uses for the research sketch), so it works without the governed knowledge service. Only draft
  // nodes and relationships are stored; nothing is written to the graph.
  const SKETCH_CONTEXT = 'knowledge:research:sketch';
  async function saveDraftSession(canvas) {
    const response = await fetch(base + '/api/canvas/session', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({context_id: SKETCH_CONTEXT, canvas})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.status !== 'ok') throw new Error('Your private draft could not be saved. Your sketch is still on this page.');
  }
  async function loadDraftSession() {
    const response = await fetch(base + '/api/canvas/session?context_id=' + encodeURIComponent(SKETCH_CONTEXT));
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.status !== 'ok') throw new Error('Your private draft could not be reopened.');
    return data.canvas || {};
  }
  async function save(kind) {
    const domain = state.domain, version = state.version;
    const canvas = kind === 'layout' ? {preset: $('kw-layout').value, view: state.view} :
      {elements: serialize(kind === 'sketch' ? sketch : graph, kind === 'sketch'), notes: kind === 'sketch' ? $('kw-notes').value : ''};
    try {
      if (visual && kind === 'sketch') {
        canvas.elements = canvas.elements.filter(element => element.data.provisional);
        await saveDraftSession(canvas);
        notice('Saved private sketch (' + canvas.elements.filter(e => e.group === 'nodes').length + ' nodes, ' +
          canvas.elements.filter(e => e.group === 'edges').length + ' relationships). It stays private; nothing was written to the knowledge graph.');
        return;
      }
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
      if (visual && kind === 'sketch') {
        const draft = await loadDraftSession();
        const nodes = (draft.elements || []).filter(e => e.group === 'nodes' && e.data?.provisional);
        const ids = new Set(nodes.map(e => e.data.id));
        const edges = (draft.elements || []).filter(e => e.group === 'edges' && e.data?.provisional && ids.has(e.data.source) && ids.has(e.data.target));
        if (version !== state.version) return;
        sketch.add([...nodes, ...edges]); $('kw-notes').value = draft.notes || ''; if (nodes.length) sketch.fit(undefined, 50);
        showInspector(null);
        notice(nodes.length ? 'Reopened private sketch (' + nodes.length + ' nodes, ' + edges.length + ' relationships).' : 'No private draft saved yet.');
        return;
      }
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
          label: element.data.provisional ? element.data.label : (element.data.reference && (records.get(element.data.reference)?.properties?.name || records.get(element.data.reference)?.name)) ||
            element.data.reference || element.data.displayLabel || element.data.label}}));
        sketch.add(elements); $('kw-notes').value = saved.notes || ''; sketch.fit();
        if (visual) showInspector(null);
      }
      notice('Reopened private ' + kind + '; all stored references were reauthorized.');
    } catch (error) { if (version === state.version) { reset(); notice(error.message); } }
  }
  $('kw-save-layout').onclick = () => save('layout');
  $('kw-save-graph').onclick = () => save('graph'); $('kw-load-graph').onclick = () => load('graph');
  $('kw-save-sketch').onclick = () => save('sketch'); $('kw-load-sketch').onclick = () => load('sketch');
  const initialId = sketchOnly ? null : params.get('id');
  changeDomain().then(async () => {
    if (initialId && state.domain === 'research') {
      await retrieve('expand', {id: initialId});
      const selected = state.records.get(initialId);
      if (selected && state.domain === 'research') await inspect(selected);
    } else if (state.domain === 'research' && state.view !== 'sketch') {
      await retrieve('search', {q: '', label: ''});
    }
  });
})();
