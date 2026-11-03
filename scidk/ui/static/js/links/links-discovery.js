// ===== Discovery & Available Tab Functions =====

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
    return;
  }
  if (discoveryState === 'error') {
    container.innerHTML = '<div class="empty-state small" data-testid="active-discovery-error" role="alert">Could not discover relationships from the graph. Use Refresh to try again.</div>';
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
  const saved = linkDefinitions.filter(l => l && l.id && l.status === 'active');
  if (saved.length > 0) {
    html += `<details data-testid="saved-definitions" style="margin-top: 0.75rem; font-size: 0.85em;"><summary>Saved definitions (${saved.length})</summary><div id="saved-definitions-list"></div></details>`;
  }
  container.innerHTML = html;

  container.querySelectorAll('.btn-view-active-type').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const t = types[parseInt(btn.dataset.typeIndex)];
      if (t && t.triples[0]) openImportWizardForRelationship(t.triples[0]);
    });
  });
  container.querySelectorAll('.btn-view-active-pattern').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const t = types[parseInt(btn.dataset.typeIndex)];
      const rel = t && t.triples[parseInt(btn.dataset.patternIndex)];
      if (rel) openImportWizardForRelationship(rel);
    });
  });
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

// Populate filter dropdowns from link definitions
function populateFilterDropdowns() {
  const sourceLabels = [...new Set(linkDefinitions.map(l => l.source_label).filter(Boolean))].sort();
  const targetLabels = [...new Set(linkDefinitions.map(l => l.target_label).filter(Boolean))].sort();
  const relTypes = [...new Set(linkDefinitions.map(l => l.relationship_type).filter(Boolean))].sort();

  const sourceSelect = document.getElementById('filter-source-label');
  const targetSelect = document.getElementById('filter-target-label');
  const relSelect = document.getElementById('filter-rel-type');

  if (sourceSelect) {
    sourceSelect.innerHTML = '<option value="">Any source label</option>' +
      sourceLabels.map(label => `<option value="${escapeHtml(label)}">${escapeHtml(label)}</option>`).join('');
  }

  if (targetSelect) {
    targetSelect.innerHTML = '<option value="">Any target label</option>' +
      targetLabels.map(label => `<option value="${escapeHtml(label)}">${escapeHtml(label)}</option>`).join('');
  }

  if (relSelect) {
    relSelect.innerHTML = '<option value="">Any relationship type</option>' +
      relTypes.map(type => `<option value="${escapeHtml(type)}">${escapeHtml(type)}</option>`).join('');
  }
}
