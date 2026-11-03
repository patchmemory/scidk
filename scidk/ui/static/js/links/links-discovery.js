// ===== Discovery & Available Tab Functions =====

// ===== Knowledge mode: a graph-first, read-only relationship viewer (shared partial, no second app) =====

function isKnowledgeMode() {
  return typeof window !== 'undefined' && !!window.LINKS_KNOWLEDGE_MODE;
}

let krSelectedType = null; // rel_type currently shown in the detail panel (null: overview)
let krDetailToken = 0;     // guards against stale async detail responses

function krBase() { return (typeof window !== 'undefined' && window.SCIDK_BASE) || ''; }
function krNum(n) { return Number(n || 0).toLocaleString(); }
function krQuote(name) { return '`' + String(name).replace(/`/g, '``') + '`'; }

function krShowPanel(html) {
  const panel = document.getElementById('kr-panel');
  if (!panel) return null;
  const wizard = document.getElementById('link-wizard');
  if (wizard) wizard.style.display = 'none';
  panel.style.display = '';
  panel.innerHTML = html;
  return panel;
}

function krNavLinks() {
  const base = krBase();
  return `<p class="small" data-testid="relationship-detail-links" style="margin-top: 1rem;">
    <a href="${base}/knowledge?view=entities" data-testid="relationships-to-entities">Browse these labels in Entities</a> ·
    <a href="${base}/knowledge?view=maps" data-testid="relationships-to-maps">Open Maps to see them on the graph</a></p>`;
}

// ----- Catalog data: one narrow primary-graph summary, cached per session and refreshed quietly -----
const KR_SUMMARY_CACHE_MAX_AGE_MS = 10 * 60 * 1000; // a stale-but-recent copy is shown at once while a fresh one loads
let krSummaryFingerprint = null;

function krCacheKey() { return 'scidk.relationships.summary:' + krBase(); }

function krReadSessionCache() {
  try {
    const stored = JSON.parse(window.sessionStorage.getItem(krCacheKey()) || 'null');
    if (stored && Array.isArray(stored.types) && Date.now() - Number(stored.saved_at || 0) <= KR_SUMMARY_CACHE_MAX_AGE_MS) return stored;
  } catch (e) { /* storage unavailable or corrupt: behave as if there is no cache */ }
  return null;
}

function krWriteSessionCache(summary) {
  try { window.sessionStorage.setItem(krCacheKey(), JSON.stringify({types: summary.types, generated_at: summary.generated_at, saved_at: Date.now()})); } catch (e) { /* ignore */ }
}

// The catalog rows the list renderer already understands: one row per source -> relationship -> target pattern.
function krRowsFromSummary(summary) {
  const rows = [];
  (summary.types || []).forEach(t => (t.patterns || []).forEach(p => rows.push({
    source_label: p.source_label, rel_type: t.rel_type, target_label: p.target_label,
    triple_count: Number(p.edge_count || 0), database: 'PRIMARY'
  })));
  return rows;
}

function krSetFreshness(text) {
  const el = document.getElementById('kr-freshness');
  if (el) el.textContent = text || '';
}

function krClock(epochSeconds) {
  const d = epochSeconds ? new Date(epochSeconds * 1000) : new Date();
  return d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'});
}

function krApplySummary(summary, quiet) {
  const rows = krRowsFromSummary(summary);
  const fingerprint = JSON.stringify(rows);
  const unchanged = discoveryState === 'ready' && fingerprint === krSummaryFingerprint;
  krSummaryFingerprint = fingerprint;
  discoveredRelationships = rows;
  discoveryState = 'ready';
  if (quiet && unchanged) return; // nothing new to draw; leave the list, scroll position and selection alone
  populateFilterDropdowns();
  renderLinkList();
}

// Load the Knowledge catalog. `refresh` (the Refresh button) forces a new query; otherwise a recent copy in this
// browser session is drawn immediately and then re-checked quietly in the background.
function loadKnowledgeSummary(refresh) {
  const cached = refresh ? null : krReadSessionCache();
  if (cached) {
    krApplySummary(cached, false);
    krSetFreshness('Showing the last result \u2014 updating\u2026');
  } else {
    discoveryState = 'loading';
    krSummaryFingerprint = null;
    krSetFreshness('');
    renderLinkList();
  }
  return fetch(krBase() + '/api/links/graph-summary' + (refresh ? '?refresh=1' : ''))
    .then(r => r.json().then(data => ({ok: r.ok, data})))
    .then(({ok, data}) => {
      if (!ok || data.status !== 'success') throw new Error(data.error || 'Summary failed');
      krWriteSessionCache(data);
      krApplySummary(data, !!cached);
      krSetFreshness(`Updated ${krClock(data.generated_at)}${data.cached ? ` (cached ${Math.round(data.age_seconds)}s ago)` : ''}`);
    })
    .catch(err => {
      console.warn('Failed to load relationship summary:', err);
      if (cached) { krSetFreshness('Showing the last result \u2014 could not update. Use Refresh to retry.'); return; }
      discoveredRelationships = [];
      discoveryState = 'error';
      populateFilterDropdowns();
      renderLinkList();
    });
}

// Shown whenever nothing is selected, so the right side is never an unexplained blank area.
function renderKnowledgeOverview() {
  const types = graphRelationshipTypes().slice().sort((a, b) => b.edge_count - a.edge_count);
  const total = types.reduce((n, t) => n + t.edge_count, 0);
  if (types.length === 0) {
    krShowPanel('<h3 style="margin-top:0">Relationships in graph</h3><div class="empty-state small" data-testid="active-empty">No relationships found in the current graph.</div>' + krNavLinks());
    return;
  }
  const top = types.slice(0, 8).map(t => `<tr><td><strong>${escapeHtml(t.rel_type)}</strong></td><td>${krNum(t.edge_count)}</td>
      <td>${[...t.sources.keys()].map(escapeHtml).join(', ')} &rarr; ${[...t.targets.keys()].map(escapeHtml).join(', ')}</td></tr>`).join('');
  krShowPanel(`<div data-testid="relationship-overview">
    <h3 style="margin-top:0">Relationships in graph</h3>
    <p>${krNum(types.length)} relationship type${types.length !== 1 ? 's' : ''} with ${krNum(total)} edges in the current graph. Pick a type on the left and choose <strong>View Details</strong> to see what it connects and a few examples.</p>
    <h4 class="small">Largest relationship types</h4>
    <table><thead><tr><th>Type</th><th>Edges</th><th>Source &rarr; target labels</th></tr></thead><tbody>${top}</tbody></table>
    ${krNavLinks()}</div>`);
}

function krOpenType(t, patternIndex) {
  document.querySelectorAll('#link-list [data-testid="active-relationship-type"]').forEach(el => {
    el.classList.toggle('active', el.dataset.relType === t.rel_type);
  });
  openKnowledgeRelationshipDetail(t, patternIndex || 0);
}

async function openKnowledgeRelationshipDetail(t, patternIndex) {
  const pattern = t.triples[patternIndex] || t.triples[0];
  if (!pattern) return;
  krSelectedType = t.rel_type;
  const token = ++krDetailToken;
  const src = pattern.source_label || '?';
  const tgt = pattern.target_label || '?';
  const others = t.triples.map((p, j) => ({p, j})).filter(x => x.j !== t.triples.indexOf(pattern));
  const otherHtml = others.length ? `<h4 class="small">Other ${escapeHtml(t.rel_type)} patterns</h4><ul>${others.map(({p, j}) =>
    `<li><button class="btn btn-sm btn-link kr-open-pattern" data-pattern-index="${j}">${escapeHtml(p.source_label || '?')} &rarr; ${escapeHtml(p.target_label || '?')}</button> <span style="color:#666">(${krNum(p.triple_count)} edges)</span></li>`).join('')}</ul>` : '';
  const query = `MATCH (a:${krQuote(src)})-[r:${krQuote(t.rel_type)}]->(b:${krQuote(tgt)})\nRETURN coalesce(a.name, a.title, a.filename, a.path, a.label) AS source_name, keys(r) AS rel_properties, coalesce(b.name, b.title, b.filename, b.path, b.label) AS target_name\nLIMIT 8`;

  const panel = krShowPanel(`<div data-testid="relationship-detail" data-rel-type="${escapeHtml(t.rel_type)}">
    <h3 style="margin-top:0">${escapeHtml(src)} &rarr; ${escapeHtml(t.rel_type)} &rarr; ${escapeHtml(tgt)}</h3>
    <div class="kr-triple" data-testid="relationship-summary">
      <span class="kr-node">${escapeHtml(src)}</span><span>&rarr;</span><span class="kr-rel">${escapeHtml(t.rel_type)}</span><span>&rarr;</span><span class="kr-node">${escapeHtml(tgt)}</span>
    </div>
    <p data-testid="relationship-counts"><strong>${krNum(pattern.triple_count)}</strong> edge${Number(pattern.triple_count) !== 1 ? 's' : ''} in this pattern${t.triples.length > 1 ? `; <strong>${krNum(t.edge_count)}</strong> across ${t.triples.length} patterns of ${escapeHtml(t.rel_type)}` : ''}.</p>
    <h4 class="small">Examples</h4>
    <div id="kr-examples" data-testid="relationship-examples"><div class="empty-state small" role="status">Loading examples&hellip;</div></div>
    ${otherHtml}
    ${krNavLinks()}
    <details data-testid="relationship-advanced"><summary>Advanced: read-only query</summary>
      <p class="small">The examples above come from this bounded, read-only query against the ${escapeHtml(pattern.database || 'PRIMARY')} graph.</p>
      <pre>${escapeHtml(query)}</pre>
    </details>
  </div>`);
  if (!panel) return;
  panel.querySelectorAll('.kr-open-pattern').forEach(btn => btn.addEventListener('click', () => openKnowledgeRelationshipDetail(t, parseInt(btn.dataset.patternIndex))));

  const box = panel.querySelector('#kr-examples');
  try {
    const response = await fetch(krBase() + '/api/neo4j/query', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({database: pattern.database || 'PRIMARY', query})
    });
    const result = await response.json();
    if (token !== krDetailToken) return;
    if (!response.ok || result.status === 'error') throw new Error(result.error || 'Query failed');
    const rows = result.records || [];
    if (!rows.length) { box.innerHTML = '<div class="empty-state small">No example edges found.</div>'; return; }
    const cell = (v, label) => v == null || v === '' ? `<em style="color:#888">(unnamed ${escapeHtml(label)})</em>` : escapeHtml(String(v));
    const get = (row, key, i) => Array.isArray(row) ? row[i] : row[key];
    box.innerHTML = `<table><thead><tr><th>${escapeHtml(src)}</th><th>${escapeHtml(t.rel_type)}</th><th>${escapeHtml(tgt)}</th></tr></thead><tbody>${rows.map(row => {
      const keys = get(row, 'rel_properties', 1) || [];
      return `<tr><td>${cell(get(row, 'source_name', 0), src)}</td><td>&rarr;${keys.length ? ` <span style="color:#666">(${keys.length} propert${keys.length !== 1 ? 'ies' : 'y'})</span>` : ''}</td><td>${cell(get(row, 'target_name', 2), tgt)}</td></tr>`;
    }).join('')}</tbody></table><p class="small" style="color:#666">Showing up to ${rows.length} representative edges.</p>`;
  } catch (err) {
    if (token !== krDetailToken) return;
    box.innerHTML = `<div class="empty-state small" role="alert">Could not load examples: ${escapeHtml(err.message)}</div>`;
  }
}

// ===== Active: relationship types present in the graph (graph-derived, read-only) =====

// One entry per relationship type in the current (primary) graph, aggregated from the triples returned by
// GET /api/links/discovered. Saved link definitions play no part in what is listed here.
function graphRelationshipTypes() {
  const byType = new Map();
  discoveredRelationships.forEach(rel => {
    if (!rel || !rel.rel_type) return;
    if (rel.database && rel.database !== 'PRIMARY') return;
    let entry = byType.get(rel.rel_type);
    if (!entry) {
      entry = { rel_type: rel.rel_type, edge_count: 0, sources: new Map(), targets: new Map(), triples: [] };
      byType.set(rel.rel_type, entry);
    }
    const n = Number(rel.triple_count || rel.count || 0);
    entry.edge_count += n;
    if (rel.source_label) entry.sources.set(rel.source_label, (entry.sources.get(rel.source_label) || 0) + n);
    if (rel.target_label) entry.targets.set(rel.target_label, (entry.targets.get(rel.target_label) || 0) + n);
    entry.triples.push(rel);
  });
  return [...byType.values()].map(entry => {
    entry.triples.sort((a, b) => Number(b.triple_count || 0) - Number(a.triple_count || 0));
    return entry;
  });
}

function renderActiveRelationshipTypes(container) {
  if (discoveryState === 'loading') {
    container.innerHTML = '<div class="empty-state small" data-testid="active-discovering" role="status">Discovering relationships\u2026</div>';
    const countEl = document.getElementById('result-count');
    if (countEl) countEl.style.display = 'none';
    if (isKnowledgeMode()) {
      krSelectedType = null; // the loading message replaces any open detail; the overview returns when discovery finishes
      krShowPanel('<div class="empty-state small" data-testid="kr-loading" role="status">Discovering relationships\u2026</div>');
    }
    return;
  }
  if (discoveryState === 'error') {
    container.innerHTML = '<div class="empty-state small" data-testid="active-discovery-error" role="alert">Could not discover relationships from the graph. Use Refresh to try again.</div>';
    if (isKnowledgeMode()) {
      krSelectedType = null;
      krShowPanel('<div class="empty-state small" role="alert">Could not discover relationships from the graph. Use Refresh to try again.</div>' + krNavLinks());
    }
    return;
  }

  const query = (linksNavState.searchQuery || '').toLowerCase();
  const all = graphRelationshipTypes();
  let types = all.filter(t => {
    if (query) {
      const haystack = [t.rel_type, ...t.sources.keys(), ...t.targets.keys()].join(' ').toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    if (linksNavState.sourceLabel && !t.sources.has(linksNavState.sourceLabel)) return false;
    if (linksNavState.targetLabel && !t.targets.has(linksNavState.targetLabel)) return false;
    if (linksNavState.relType && t.rel_type !== linksNavState.relType) return false;
    return true;
  });

  const first = m => [...m.keys()].sort()[0] || '';
  types.sort((a, b) => {
    switch (linksNavState.sortBy) {
      case 'source': return first(a.sources).localeCompare(first(b.sources));
      case 'target': return first(a.targets).localeCompare(first(b.targets));
      default: return a.rel_type.localeCompare(b.rel_type);
    }
  });

  updateResultCount(types.length, all.length, 'relationship type');

  const labelList = m => [...m.entries()].sort((a, b) => b[1] - a[1])
    .map(([label]) => `<span class="badge" style="background: #e3f2fd; color: #0d47a1; font-size: 0.8em; padding: 0.15em 0.4em; border-radius: 3px; margin-right: 0.25rem;">${escapeHtml(label)}</span>`).join('');
  const hl = text => query ? highlightMatch(text, query) : escapeHtml(text);

  let html;
  if (all.length === 0) {
    html = '<div class="empty-state small" data-testid="active-empty">No relationships found in the current graph.</div>';
  } else if (types.length === 0) {
    html = '<div class="empty-state small">No relationship types match your filters.</div>';
  } else {
    html = types.map((t, i) => {
      const patterns = t.triples.length > 1
        ? `<details style="margin-top: 0.35rem; font-size: 0.8em;"><summary>${t.triples.length} source \u2192 target patterns</summary>${t.triples.map((p, j) => `
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.15rem 0;">
              <span>${escapeHtml(p.source_label || '?')} \u2192 ${escapeHtml(p.target_label || '?')} <span style="color:#666">(${Number(p.triple_count || 0).toLocaleString()})</span></span>
              <button class="btn btn-sm btn-outline-secondary btn-view-active-pattern" data-type-index="${i}" data-pattern-index="${j}" style="font-size: 0.85em;">Details</button>
            </div>`).join('')}</details>`
        : '';
      return `
      <div class="link-item" data-testid="active-relationship-type" data-rel-type="${escapeHtml(t.rel_type)}"
           style="padding: 0.5rem; margin-bottom: 0.25rem; border-radius: 4px; border: 1px solid transparent;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
          <strong style="font-size: 0.95em;">${hl(t.rel_type)}</strong>
          <span class="badge" data-testid="active-edge-count" style="background: #4caf50; color: white; font-size: 0.7em; padding: 0.2em 0.4em; border-radius: 3px;">${t.edge_count.toLocaleString()} edge${t.edge_count !== 1 ? 's' : ''}</span>
        </div>
        <div style="font-size: 0.85em; color: #666;" data-testid="active-sources"><strong>From:</strong> ${labelList(t.sources)}</div>
        <div style="font-size: 0.85em; color: #666; margin-top: 0.15rem;" data-testid="active-targets"><strong>To:</strong> ${labelList(t.targets)}</div>
        ${patterns}
        <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
          <button class="btn btn-sm btn-outline-secondary btn-view-active-type" data-type-index="${i}" style="font-size: 0.75em;">View Details</button>
        </div>
      </div>`;
    }).join('');
  }

  // Saved link definitions are a secondary, compatibility-only view.
  const saved = isKnowledgeMode() ? [] : linkDefinitions.filter(l => l && l.id && l.status === 'active');
  if (saved.length > 0) {
    html += `<details data-testid="saved-definitions" style="margin-top: 0.75rem; font-size: 0.85em;"><summary>Saved definitions (${saved.length})</summary><div id="saved-definitions-list"></div></details>`;
  }
  container.innerHTML = html;

  container.querySelectorAll('.btn-view-active-type').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const t = types[parseInt(btn.dataset.typeIndex)];
      if (!t || !t.triples[0]) return;
      if (isKnowledgeMode()) krOpenType(t, 0); else openImportWizardForRelationship(t.triples[0]);
    });
  });
  container.querySelectorAll('.btn-view-active-pattern').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const t = types[parseInt(btn.dataset.typeIndex)];
      const idx = parseInt(btn.dataset.patternIndex);
      const rel = t && t.triples[idx];
      if (!rel) return;
      if (isKnowledgeMode()) krOpenType(t, idx); else openImportWizardForRelationship(rel);
    });
  });
  if (isKnowledgeMode()) {
    container.querySelectorAll('[data-testid="active-relationship-type"]').forEach((row, i) => {
      row.addEventListener('click', e => { if (!e.target.closest('button, summary, details, a') && types[i]) krOpenType(types[i], 0); });
    });
    const stillListed = krSelectedType && all.some(t => t.rel_type === krSelectedType);
    const builder = document.getElementById('link-wizard');
    const builderOpen = builder && builder.style.display !== 'none';
    if (!stillListed) {
      krSelectedType = null;
      if (!builderOpen) renderKnowledgeOverview();
    }
  }
  const savedContainer = container.querySelector('#saved-definitions-list');
  if (savedContainer) renderFlatLinks(saved, savedContainer);
}

function renderDiscoveredRelationships(container) {
  if (discoveryState === 'loading') {
    container.innerHTML = '<div class="empty-state small" data-testid="available-discovering" role="status">Discovering relationships\u2026</div>';
    return;
  }
  if (discoveredRelationships.length === 0) {
    container.innerHTML = `<div class="empty-state small">No discovered relationships. Connect to Neo4j databases to see existing relationships.</div>`;
    return;
  }

  // Apply filtering pipeline to discovered relationships
  let validRels = [...discoveredRelationships];
  const totalCount = validRels.length;

  // Apply search query
  if (linksNavState.searchQuery) {
    const query = linksNavState.searchQuery.toLowerCase();
    validRels = validRels.filter(rel => {
      const searchFields = [
        rel.source_label,
        rel.target_label,
        rel.rel_type,
        rel.database
      ].filter(Boolean).join(' ').toLowerCase();
      return searchFields.includes(query);
    });
  }

  // Apply source label filter
  if (linksNavState.sourceLabel) {
    validRels = validRels.filter(r => r.source_label === linksNavState.sourceLabel);
  }

  // Apply target label filter
  if (linksNavState.targetLabel) {
    validRels = validRels.filter(r => r.target_label === linksNavState.targetLabel);
  }

  // Apply relationship type filter
  if (linksNavState.relType) {
    validRels = validRels.filter(r => r.rel_type === linksNavState.relType);
  }

  // DO NOT deduplicate - show each database as a separate entry
  // The source database is critical context that must be preserved
  // If Sample-[DERIVED_FROM]->Sample exists in both NextSEEK-Dev and PRIMARY,
  // show them as two separate entries with different database badges

  // Apply sort
  validRels.sort((a, b) => {
    switch (linksNavState.sortBy) {
      case 'name': return `${a.source_label}-${a.rel_type}-${a.target_label}`.localeCompare(`${b.source_label}-${b.rel_type}-${b.target_label}`);
      case 'source': return (a.source_label || '').localeCompare(b.source_label || '');
      case 'target': return (a.target_label || '').localeCompare(b.target_label || '');
      case 'rel_type': return (a.rel_type || '').localeCompare(b.rel_type || '');
      default: return 0;
    }
  });

  // Update result count
  updateResultCount(validRels.length, totalCount);

  // Check if grouping is enabled
  if (linksNavState.groupByRelType) {
    renderGroupedDiscoveredRelationships(validRels, container);
    return;
  }

  // Render flat list with highlighting
  const query = linksNavState.searchQuery;

  if (validRels.length === 0) {
    container.innerHTML = `<div class="empty-state small">No discovered relationships match your filters.</div>`;
    return;
  }

  container.innerHTML = validRels.map((rel, index) => {
    // Badge for available status
    const statusBadge = '<span class="badge" style="background: #999; color: white; font-size: 0.7em; padding: 0.2em 0.4em; border-radius: 3px;">AVAILABLE</span>';

    // Show database badges - multiple databases may contain the same triple pattern
    const databases = rel.databases || [rel.database] || ['PRIMARY'];
    const databaseBadges = databases.map(db => {
      const databaseColor = db === 'PRIMARY' ? '#2196f3' : '#ff9800';
      return `<span class="badge" style="background: ${databaseColor}; color: white; font-size: 0.7em; padding: 0.2em 0.4em; border-radius: 3px; margin-left: 0.25rem;">${escapeHtml(db)}</span>`;
    }).join('');

    const countBadge = `<span class="badge" style="background: #4caf50; color: white; font-size: 0.7em; padding: 0.2em 0.4em; border-radius: 3px; margin-left: 0.25rem;">${rel.triple_count || rel.count || 0}</span>`;

    // Apply search highlighting
    const sourceDisplay = query ? highlightMatch(rel.source_label || '?', query) : escapeHtml(rel.source_label || '?');
    const relDisplay = query ? highlightMatch(rel.rel_type || '?', query) : escapeHtml(rel.rel_type || '?');
    const targetDisplay = query ? highlightMatch(rel.target_label || '?', query) : escapeHtml(rel.target_label || '?');

    // Name combines source, rel, target like wizard links
    const linkName = `${sourceDisplay} → ${targetDisplay}`;
    const descLine = `${sourceDisplay} → ${relDisplay} → ${targetDisplay}`;

    return `
      <div class="link-item"
           data-testid="discovered-item"
           style="padding: 0.5rem; margin-bottom: 0.25rem; cursor: pointer; border-radius: 4px; border: 1px solid transparent;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
          <strong style="font-size: 0.95em;">${linkName}</strong>
          <div>${statusBadge}${databaseBadges}${countBadge}</div>
        </div>
        <div style="font-size: 0.85em; color: #666;">
          ${descLine}
        </div>
        <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
          <button class="btn btn-sm btn-outline-primary btn-adopt-discovered" data-index="${index}" style="font-size: 0.75em;">
            Adopt as Definition
          </button>
          <button class="btn btn-sm btn-outline-secondary btn-view-discovered" data-index="${index}" style="font-size: 0.75em;">
            View Details
          </button>
        </div>
      </div>
    `;
  }).join('');

  // Add event listeners
  container.querySelectorAll('.btn-adopt-discovered').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const index = parseInt(btn.dataset.index);
      const rel = validRels[index];
      if (rel) adoptDiscoveredAsDefinition(rel);
    });
  });

  container.querySelectorAll('.btn-view-discovered').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const index = parseInt(btn.dataset.index);
      const rel = validRels[index];
      if (rel) openImportWizardForRelationship(rel);
    });
  });
}

// Render grouped discovered relationships by relationship type
function renderGroupedDiscoveredRelationships(validRels, container) {
  const query = linksNavState.searchQuery;

  // Group by rel_type
  const groups = {};
  validRels.forEach(rel => {
    const relType = rel.rel_type || 'UNKNOWN';
    if (!groups[relType]) groups[relType] = [];
    groups[relType].push(rel);
  });

  const sortedRelTypes = Object.keys(groups).sort();

  if (sortedRelTypes.length === 0) {
    container.innerHTML = `<div class="empty-state small">No discovered relationships match your filters.</div>`;
    return;
  }

  // Initialize collapsed state for new groups only (preserve user toggles)
  sortedRelTypes.forEach(relType => {
    const isNewGroup = !linksNavState.seenGroups.has(relType);

    if (isNewGroup) {
      // Mark as seen
      linksNavState.seenGroups.add(relType);

      // Start collapsed unless searching
      if (!query || !query.trim()) {
        linksNavState.collapsedGroups.add(relType);
      }
    }

    // If searching with results, temporarily expand all groups to show matches
    if (query && query.trim()) {
      linksNavState.collapsedGroups.delete(relType);
    }
  });

  container.innerHTML = sortedRelTypes.map(relType => {
    const rels = groups[relType];
    const isCollapsed = linksNavState.collapsedGroups.has(relType);
    const arrow = isCollapsed ? '▶' : '▼';

    const groupHeader = `
      <div class="link-group-header" data-rel-type="${escapeHtml(relType)}" style="background: #e3f2fd; padding: 0.5rem; margin-bottom: 0.5rem; cursor: pointer; font-weight: 500; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">
        <span>${arrow} ${escapeHtml(relType)} <span style="color: #666; font-weight: normal;">(${rels.length})</span></span>
      </div>
    `;

    if (isCollapsed) {
      return groupHeader;
    }

    const groupItems = rels.map((rel, relIndex) => {
      // Badge for available status
      const statusBadge = '<span class="badge" style="background: #999; color: white; font-size: 0.7em; padding: 0.2em 0.4em; border-radius: 3px;">AVAILABLE</span>';

      // Show database badges - multiple databases may contain the same triple pattern
      const databases = rel.databases || [rel.database] || ['PRIMARY'];
      const databaseBadges = databases.map(db => {
        const databaseColor = db === 'PRIMARY' ? '#2196f3' : '#ff9800';
        return `<span class="badge" style="background: ${databaseColor}; color: white; font-size: 0.7em; padding: 0.2em 0.4em; border-radius: 3px; margin-left: 0.25rem;">${escapeHtml(db)}</span>`;
      }).join('');
      const countBadge = `<span class="badge" style="background: #4caf50; color: white; font-size: 0.7em; padding: 0.2em 0.4em; border-radius: 3px; margin-left: 0.25rem;">${rel.triple_count || rel.count || 0}</span>`;

      const sourceDisplay = query ? highlightMatch(rel.source_label || '?', query) : escapeHtml(rel.source_label || '?');
      const relDisplay = query ? highlightMatch(rel.rel_type || '?', query) : escapeHtml(rel.rel_type || '?');
      const targetDisplay = query ? highlightMatch(rel.target_label || '?', query) : escapeHtml(rel.target_label || '?');

      // Name combines source and target
      const linkName = `${sourceDisplay} → ${targetDisplay}`;
      const descLine = `${sourceDisplay} → ${relDisplay} → ${targetDisplay}`;

      // Find index in validRels for event handlers
      const originalIndex = validRels.findIndex(r =>
        r.source_label === rel.source_label &&
        r.rel_type === rel.rel_type &&
        r.target_label === rel.target_label &&
        r.database === rel.database
      );

      return `
        <div class="link-item" data-testid="discovered-item" style="padding: 0.5rem; margin-bottom: 0.25rem; margin-left: 1rem; border-left: 2px solid #e0e0e0;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
            <strong style="font-size: 0.95em;">${linkName}</strong>
            <div>${statusBadge}${databaseBadges}${countBadge}</div>
          </div>
          <div style="font-size: 0.85em; color: #666;">
            ${descLine}
          </div>
          <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
            <button class="btn btn-sm btn-outline-primary btn-adopt-discovered" data-index="${originalIndex}" style="font-size: 0.75em;">
              Adopt as Definition
            </button>
            <button class="btn btn-sm btn-outline-secondary btn-view-discovered" data-index="${originalIndex}" style="font-size: 0.75em;">
              View Details
            </button>
          </div>
        </div>
      `;
    }).join('');

    return groupHeader + groupItems;
  }).join('');

  // Add event listeners for group headers
  container.querySelectorAll('.link-group-header').forEach(header => {
    header.addEventListener('click', () => {
      const relType = header.dataset.relType;
      if (linksNavState.collapsedGroups.has(relType)) {
        linksNavState.collapsedGroups.delete(relType);
      } else {
        linksNavState.collapsedGroups.add(relType);
      }
      renderLinkList();
    });
  });

  // Add event listeners for discovered items
  container.querySelectorAll('.btn-adopt-discovered').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const index = parseInt(btn.dataset.index);
      const rel = validRels[index];
      if (rel) adoptDiscoveredAsDefinition(rel);
    });
  });

  container.querySelectorAll('.btn-view-discovered').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const index = parseInt(btn.dataset.index);
      const rel = validRels[index];
      if (rel) openImportWizardForRelationship(rel);
    });
  });
}

// Adopt discovered relationship as a new link definition
function adoptDiscoveredAsDefinition(rel) {
  // Reset wizard to clean state
  resetWizard();

  // Populate tripleBuilder from discovered relationship
  tripleBuilder.source.label = rel.source_label || '';
  tripleBuilder.source.filters = [];
  tripleBuilder.target.label = rel.target_label || '';
  tripleBuilder.target.filters = [];
  tripleBuilder.relationship.type = rel.rel_type || '';
  tripleBuilder.relationship.match_strategy = ''; // User must configure
  tripleBuilder.relationship.match_config = {};
  tripleBuilder.relationship.properties = [];
  tripleBuilder.link_id = null;
  tripleBuilder.name = `${rel.source_label} → ${rel.target_label}`;

  // Update link name input
  const linkNameInput = document.getElementById('link-name');
  if (linkNameInput) {
    linkNameInput.value = tripleBuilder.name;
  }

  // Update visual display
  updateMainTripleDisplay();

  // Show wizard
  showWizard();

  showToast(`Adopted "${rel.source_label} → ${rel.rel_type} → ${rel.target_label}" as new link definition. Configure match strategy to proceed.`, 'success');
}

// Save discovered relationship as a new link definition
function saveDiscoveredAsDefinition(rel) {
  tripleBuilder.source.label = rel.source_label || '';
  tripleBuilder.target.label = rel.target_label || '';
  tripleBuilder.relationship.type = rel.rel_type || '';
  tripleBuilder.name = `${rel.source_label} → ${rel.target_label}`;

  // Update UI
  const linkNameInput = document.getElementById('link-name');
  if (linkNameInput) linkNameInput.value = tripleBuilder.name;

  updateMainTripleDisplay();
  showWizard();

  showToast('Link definition created. Configure match strategy to save.', 'info');
}

// Auto-detect UID property from a list of properties
function autoDetectUidProperty(properties) {
  if (!properties || properties.length === 0) return null;

  // Priority 1: Exact match for 'uid' (case-insensitive)
  const uidExact = properties.find(p => {
    const propName = typeof p === 'string' ? p : p.name;
    return propName.toLowerCase() === 'uid';
  });
  if (uidExact) return typeof uidExact === 'string' ? uidExact : uidExact.name;

  // Priority 2: Properties ending with '_id' or '_uid'
  const idSuffix = properties.find(p => {
    const propName = typeof p === 'string' ? p : p.name;
    return propName.toLowerCase().endsWith('_id') || propName.toLowerCase().endsWith('_uid');
  });
  if (idSuffix) return typeof idSuffix === 'string' ? idSuffix : idSuffix.name;

  // Priority 3: Properties containing 'id' or 'uid' (case-insensitive)
  const idContains = properties.find(p => {
    const propName = typeof p === 'string' ? p : p.name;
    const lower = propName.toLowerCase();
    return lower.includes('id') || lower.includes('uid');
  });
  if (idContains) return typeof idContains === 'string' ? idContains : idContains.name;

  // Priority 4: Common identifier property names
  const commonIds = ['name', 'title', 'label', 'key', 'code'];
  for (const commonId of commonIds) {
    const match = properties.find(p => {
      const propName = typeof p === 'string' ? p : p.name;
      return propName.toLowerCase() === commonId;
    });
    if (match) return typeof match === 'string' ? match : match.name;
  }

  // Fallback: First property
  return typeof properties[0] === 'string' ? properties[0] : properties[0].name;
}

// (updateResultCount lives in links-core.js; a second copy here would override it, as this file loads later.)

// Toggle group collapse state
function toggleGroup(relType) {
  if (linksNavState.collapsedGroups.has(relType)) {
    linksNavState.collapsedGroups.delete(relType);
  } else {
    linksNavState.collapsedGroups.add(relType);
  }
  renderLinkList();
}

// Clear advanced filters
function clearAdvancedFilters() {
  linksNavState.sourceLabel = '';
  linksNavState.targetLabel = '';
  linksNavState.relType = '';
  linksNavState.sortBy = 'name';

  // Reset UI
  document.getElementById('filter-source-label').value = '';
  document.getElementById('filter-target-label').value = '';
  document.getElementById('filter-rel-type').value = '';
  document.getElementById('sort-links').value = 'name';

  updateToggleButton();
  renderLinkList();
}

// Update advanced filters toggle button
function updateToggleButton() {
  const btn = document.getElementById('toggle-advanced-filters');
  if (!btn) return;

  const panel = document.getElementById('advanced-filters');
  const isOpen = panel && panel.style.display !== 'none';

  // Count active filters
  const activeCount = [
    linksNavState.sourceLabel,
    linksNavState.targetLabel,
    linksNavState.relType
  ].filter(Boolean).length;

  const arrow = isOpen ? '▲' : '▼';
  const filterText = activeCount > 0 ? ` (${activeCount} active)` : '';
  btn.textContent = `${arrow} Advanced Filters${filterText}`;
}

// Get active filter count
function getActiveFilterCount() {
  return [
    linksNavState.sourceLabel,
    linksNavState.targetLabel,
    linksNavState.relType
  ].filter(Boolean).length;
}

// (populateFilterDropdowns lives in links-core.js; a second copy here would override it, as this file loads later.)
