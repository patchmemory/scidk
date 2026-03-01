// ===== Discovery & Available Tab Functions =====

// Render discovered relationships (separate rendering path)
function renderDiscoveredRelationships(container) {
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

// Update result count indicator
function updateResultCount(shown, total) {
  const countEl = document.getElementById('result-count');
  if (!countEl) return;

  if (shown === total) {
    countEl.textContent = `Showing all ${total} link${total !== 1 ? 's' : ''}`;
  } else {
    countEl.textContent = `Showing ${shown} of ${total} links`;
  }
  countEl.style.display = total > 0 ? 'block' : 'none';
}

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
