// links-core.js - Core functionality for Links page
// Excludes modal and import wizard functions (extracted separately)

// ===== Global State Variables =====
let currentLink = null;
let currentStep = 1;
let linkDefinitions = [];
let discoveredRelationships = []; // Discovered relationships from Neo4j
let availableLabels = [];
let lastFocusedIndex = -1; // For keyboard navigation
let currentFilter = 'active'; // Filter state: 'active', 'pending', 'available'

// Legacy wizardData (to be phased out)
let wizardData = {
  id: null,
  name: '',
  source_label: '',
  target_label: '',
  source_type: 'label',
  source_config: {},
  target_type: 'label',
  target_config: {},
  match_strategy: 'property',
  match_config: {},
  relationship_type: '',
  relationship_props: {}
};

// NEW: Triple Builder state (modal-based workflow)
const tripleBuilder = {
  source: { label: '', filters: [] },
  relationship: { type: '', properties: [], match_strategy: '', match_config: {} },
  target: { label: '', filters: [] },
  link_id: null,
  name: ''
};

// Snapshot for cancel functionality
let tripleBuilderSnapshot = null;

// State for discovered import workflow
let discoveredImportConfig = {
  rel: null,
  database: '',
  source: { label: '', uid_property: '', available_properties: [] },
  target: { label: '', uid_property: '', available_properties: [] },
  relationship: { type: '', available_properties: [], import_properties: true }
};

// Links navigation state (search, filters, sorting, grouping)
const linksNavState = {
  searchQuery: '',
  sourceLabel: '',
  targetLabel: '',
  relType: '',
  sortBy: 'name',
  groupByRelType: false,
  collapsedGroups: new Set(),
  seenGroups: new Set()  // Track which groups have been rendered before
};

// ===== Core Utility Functions =====

// Toast function
function showToast(message, type = 'info') {
  if (typeof window.toast === 'function') {
    window.toast(message, type, 3000);
  } else {
    console.log(`[${type}] ${message}`);
  }
}

// Helper to escape HTML (XSS protection)
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

// Fetch properties for a label from external database
async function fetchLabelProperties(label, database) {
  try {
    const response = await fetch(window.SCIDK_BASE + `/api/neo4j/label-properties`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ database: database, label: label })
    });
    const result = await response.json();

    if (result.status === 'success' && result.properties) {
      return result.properties;
    }
    return [];
  } catch (err) {
    console.error('Failed to fetch label properties:', err);
    return [];
  }
}

// Fetch relationship properties from external database
async function fetchRelationshipProperties(sourceLabel, relType, targetLabel, database) {
  try {
    const query = `MATCH (a:${sourceLabel})-[r:${relType}]->(b:${targetLabel}) RETURN keys(r) as props LIMIT 1`;
    const response = await fetch(window.SCIDK_BASE + `/api/neo4j/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ database: database, query: query })
    });
    const result = await response.json();

    if (result.status === 'success' && result.records && result.records.length > 0) {
      return result.records[0].props || [];
    }
    return [];
  } catch (err) {
    console.error('Failed to fetch relationship properties:', err);
    return [];
  }
}

// Highlight search matches with XSS protection
function highlightMatch(text, query) {
  if (!query || !text) return escapeHtml(text);

  const escapedText = escapeHtml(text);
  const escapedQuery = escapeHtml(query);

  // Escape regex special characters and create case-insensitive regex
  const regex = new RegExp(`(${escapedQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  return escapedText.replace(regex, '<mark style="background: #fef3c7; padding: 0 2px;">$1</mark>');
}

// Helper to format date/time from ISO string
function formatDateTime(isoString) {
  if (!isoString) return 'Never';
  try {
    const date = new Date(isoString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  } catch (e) {
    return isoString;
  }
}

// Helper to format last run timestamp
function formatLastRun(timestamp) {
  if (!timestamp) return 'Never';
  try {
    const date = new Date(timestamp * 1000); // Convert Unix timestamp to milliseconds
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  } catch (e) {
    return 'Never';
  }
}

// ===== Initialization & Core Management =====

// Main page initialization function
function loadLinksPage() {
  // Load groupByRelType preference from localStorage
  const savedGroupPref = localStorage.getItem('links_group_by_rel_type');
  if (savedGroupPref === 'true') {
    linksNavState.groupByRelType = true;
    const groupToggle = document.getElementById('group-by-toggle');
    if (groupToggle) groupToggle.checked = true;
  }

  loadAvailableLabels();
  loadLinkDefinitions();
  loadDiscoveredRelationships();
  initializeEventListeners();

  // Search input with debounce
  let searchDebounce;
  const searchInput = document.getElementById('links-search');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => {
        linksNavState.searchQuery = e.target.value;
        renderLinkList();
      }, 150);
    });
  }

  // Toggle advanced filters panel
  const toggleBtn = document.getElementById('toggle-advanced-filters');
  const advancedPanel = document.getElementById('advanced-filters');
  if (toggleBtn && advancedPanel) {
    toggleBtn.addEventListener('click', () => {
      const isHidden = advancedPanel.style.display === 'none';
      advancedPanel.style.display = isHidden ? 'block' : 'none';
      updateToggleButton();
    });
  }

  // Filter dropdowns - individual wiring for clarity
  const sourceFilter = document.getElementById('filter-source-label');
  if (sourceFilter) {
    sourceFilter.addEventListener('change', (e) => {
      linksNavState.sourceLabel = e.target.value;
      renderLinkList();
      updateToggleButton();
    });
  }

  const targetFilter = document.getElementById('filter-target-label');
  if (targetFilter) {
    targetFilter.addEventListener('change', (e) => {
      linksNavState.targetLabel = e.target.value;
      renderLinkList();
      updateToggleButton();
    });
  }

  const relTypeFilter = document.getElementById('filter-rel-type');
  if (relTypeFilter) {
    relTypeFilter.addEventListener('change', (e) => {
      linksNavState.relType = e.target.value;
      renderLinkList();
      updateToggleButton();
    });
  }

  const sortSelect = document.getElementById('sort-links');
  if (sortSelect) {
    sortSelect.addEventListener('change', (e) => {
      linksNavState.sortBy = e.target.value;
      renderLinkList();
    });
  }

  // Group by toggle
  const groupToggle = document.getElementById('group-by-toggle');
  if (groupToggle) {
    groupToggle.addEventListener('change', (e) => {
      linksNavState.groupByRelType = e.target.checked;
      localStorage.setItem('links_group_by_rel_type', e.target.checked);
      renderLinkList();
    });
  }

  // Global keyboard navigation handler
  document.addEventListener('keydown', handleGlobalKeydown);

  // Resizer functionality
  const resizer = document.getElementById('resizer');
  const leftPanel = document.getElementById('links-list');
  const container = document.querySelector('.links-container');

  let isResizing = false;

  resizer.addEventListener('mousedown', (e) => {
    isResizing = true;
    resizer.classList.add('resizing');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;

    const containerRect = container.getBoundingClientRect();
    const newWidth = e.clientX - containerRect.left;
    const minWidth = 200;
    const maxWidth = containerRect.width * 0.5;

    if (newWidth >= minWidth && newWidth <= maxWidth) {
      leftPanel.style.width = `${newWidth}px`;
    }
  });

  document.addEventListener('mouseup', () => {
    if (isResizing) {
      isResizing = false;
      resizer.classList.remove('resizing');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }
  });
}

// Initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', loadLinksPage);

function loadAvailableLabels() {
  fetch(window.SCIDK_BASE + '/api/links/available-labels')
    .then(r => r.json())
    .then(data => {
      if (data.status === 'success') {
        availableLabels = data.labels || [];
        // Labels are now populated dynamically in modals, not in static dropdowns
        populateLabelDropdowns(); // Keep for legacy support
      }
    })
    .catch(err => {
      console.error('Failed to load labels:', err);
      // Don't show toast error on page load - labels will still work
      availableLabels = [];
    });
}

function populateLabelDropdowns() {
  // Legacy function - kept for backward compatibility with openImportWizardForRelationship
  const sourceSelect = document.getElementById('source-label-select');
  const targetSelect = document.getElementById('target-label-select');

  if (sourceSelect && targetSelect) {
    const options = availableLabels.map(label => {
      const labelName = typeof label === 'string' ? label : label.name;
      return `<option value="${labelName}">${labelName}</option>`;
    }).join('');

    sourceSelect.innerHTML = '<option value="">Select a label...</option>' + options;
    targetSelect.innerHTML = '<option value="">Select a label...</option>' + options;
  }
}

function initializeEventListeners() {
  // Filter tabs
  document.querySelectorAll('.link-filter-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      // Update active state
      document.querySelectorAll('.link-filter-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      // Update filter and re-render
      currentFilter = tab.dataset.filter;
      renderLinkList();
    });
  });

  // Unified refresh button - refreshes all three tabs
  document.getElementById('btn-refresh-all').addEventListener('click', async () => {
    const refreshBtn = document.getElementById('btn-refresh-all');
    const refreshIcon = document.getElementById('refresh-icon');
    const refreshText = document.getElementById('refresh-text');

    // Show loading state
    refreshBtn.disabled = true;
    refreshIcon.style.animation = 'spin 1s linear infinite';
    refreshText.textContent = 'Refreshing...';

    try {
      showToast('Refreshing all tabs...', 'info');

      // Step 1: Verify Active links against primary graph
      try {
        const verifyResponse = await fetch(window.SCIDK_BASE + '/api/links/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        const verifyData = await verifyResponse.json();

        if (verifyData.status === 'success') {
          const staleCount = Object.values(verifyData.verified).filter(count => count === 0).length;
          if (staleCount > 0) {
            showToast(`Moved ${staleCount} stale link(s) to Pending`, 'info');
          }
        }
      } catch (err) {
        console.error('Failed to verify active links:', err);
      }

      // Step 2: Rescan external graphs for available relationships
      await loadDiscoveredRelationships();

      // Step 3: Reload all link definitions (promotion happens server-side)
      await loadLinkDefinitions();

      showToast('Refresh complete - all tabs updated', 'success');

      // Re-render current tab
      renderLinkList();

    } catch (err) {
      console.error('Refresh failed:', err);
      showToast('Refresh failed: ' + err.message, 'error');
    } finally {
      // Reset button state
      refreshBtn.disabled = false;
      refreshIcon.style.animation = '';
      refreshText.textContent = 'Refresh';
    }
  });

  // Dropdown toggle
  const dropdownBtn = document.getElementById('link-type-dropdown-btn');
  const dropdownMenu = document.getElementById('link-type-dropdown-menu');

  dropdownBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdownMenu.style.display = dropdownMenu.style.display === 'none' ? 'block' : 'none';
  });

  // Close dropdown when clicking outside
  document.addEventListener('click', (e) => {
    if (!dropdownBtn.contains(e.target) && !dropdownMenu.contains(e.target)) {
      dropdownMenu.style.display = 'none';
    }
  });

  // Wizard link option
  document.getElementById('menu-wizard-link').addEventListener('click', (e) => {
    e.preventDefault();
    dropdownMenu.style.display = 'none';
    resetWizard();
    showWizard();
  });

  // Script link option - redirect to Scripts page
  document.getElementById('menu-script-link').addEventListener('click', (e) => {
    e.preventDefault();
    dropdownMenu.style.display = 'none';
    window.location.href = window.SCIDK_BASE + '/scripts?new=link';
  });

  // Import link option - switch to Discovered tab
  document.getElementById('menu-import-link').addEventListener('click', (e) => {
    e.preventDefault();
    dropdownMenu.style.display = 'none';

    // Switch to Available filter tab
    currentFilter = 'available';
    renderLinkList();

    // Update tab styling
    document.querySelectorAll('.link-filter-tab').forEach(tab => {
      tab.classList.toggle('active', tab.dataset.filter === 'available');
    });

    showToast('Click on an available relationship to adopt it as a link definition', 'info');
  });

  // Wizard navigation buttons (if they exist - legacy support)
  const btnPrev = document.getElementById('btn-prev');
  const btnNext = document.getElementById('btn-next');
  if (btnPrev) btnPrev.addEventListener('click', () => navigateStep(-1));
  if (btnNext) btnNext.addEventListener('click', () => navigateStep(1));

  // Main action buttons (always present)
  const btnExecute = document.getElementById('btn-execute');
  const btnSaveDef = document.getElementById('btn-save-def');
  const btnDeleteDef = document.getElementById('btn-delete-def');

  if (btnExecute) btnExecute.addEventListener('click', executeLink);
  if (btnSaveDef) btnSaveDef.addEventListener('click', saveLinkDefinition);
  if (btnDeleteDef) btnDeleteDef.addEventListener('click', deleteLinkDefinition);

  // Label selection dropdowns (legacy - only used by old openImportWizardForRelationship)
  const sourceSelect = document.getElementById('source-label-select');
  const targetSelect = document.getElementById('target-label-select');
  if (sourceSelect) {
    sourceSelect.addEventListener('change', (e) => {
      wizardData.source_label = e.target.value;
      if (typeof updateVisualPattern === 'function') updateVisualPattern();
    });
  }
  if (targetSelect) {
    targetSelect.addEventListener('change', (e) => {
      wizardData.target_label = e.target.value;
      if (typeof updateVisualPattern === 'function') updateVisualPattern();
    });
  }

  // Match strategy buttons (legacy)
  document.querySelectorAll('.match-strategy-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.match-strategy-btn').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      wizardData.match_strategy = e.target.dataset.strategy;
      if (typeof showMatchConfig === 'function') showMatchConfig(wizardData.match_strategy);
    });
  });

  // Add relationship property button (legacy)
  const btnAddRelProp = document.getElementById('btn-add-rel-prop');
  if (btnAddRelProp && typeof addRelationshipProperty === 'function') {
    btnAddRelProp.addEventListener('click', addRelationshipProperty);
  }

  // Relationship type input (legacy)
  const relTypeInput = document.getElementById('rel-type');
  if (relTypeInput) {
    relTypeInput.addEventListener('input', (e) => {
      wizardData.relationship_type = e.target.value;
      if (typeof updateVisualPattern === 'function') updateVisualPattern();
    });
  }
}

function loadLinkDefinitions() {
  fetch(window.SCIDK_BASE + '/api/links')
    .then(r => r.json())
    .then(data => {
      if (data.status === 'success') {
        linkDefinitions = data.links || [];
        populateFilterDropdowns();
        renderLinkList();
      }
    })
    .catch(err => showToast('Failed to load link definitions', 'error'));
}

function loadDiscoveredRelationships() {
  fetch(window.SCIDK_BASE + '/api/links/discovered')
    .then(r => r.json())
    .then(data => {
      if (data.status === 'success') {
        discoveredRelationships = data.relationships || [];
        updateFilterTabCounts();
        // Re-render if currently viewing discovered tab
        if (currentFilter === 'discovered') {
          renderLinkList();
        }
      }
    })
    .catch(err => {
      // Silently fail - discovered relationships are optional
      console.warn('Failed to load discovered relationships:', err);
      discoveredRelationships = [];
      updateFilterTabCounts();
    });
}

// ===== Rendering Functions =====

function renderLinkList() {
  const container = document.getElementById('link-list');

  console.log('[Links] Tab data:', currentFilter, 'linkDefinitions:', linkDefinitions.map(l => ({id: l.id, name: l.name, status: l.status})));

  // Update filter tab counts
  updateFilterTabCounts();

  // Handle available (discovered) relationships with full filtering
  if (currentFilter === 'available') {
    renderDiscoveredRelationships(container);
    return;
  }

  // NEW FILTERING PIPELINE

  // 1. Start with all link definitions
  let validLinks = linkDefinitions.filter(link => link && link.id);

  // 2. Apply status tab filter (active/pending/available)
  // Active = relationships confirmed in primary graph (status = 'active')
  // Pending = in progress, modified, needs run (status = 'pending')
  // Available = drafts + discovered (status = 'draft' or null)
  if (currentFilter === 'active') {
    validLinks = validLinks.filter(link => link.status === 'active');
  } else if (currentFilter === 'pending') {
    validLinks = validLinks.filter(link => link.status === 'pending');
  } else if (currentFilter === 'available') {
    validLinks = validLinks.filter(link => link.status === 'draft' || !link.status);
  }

  // Total count for current tab (after tab filter, before search/other filters)
  const totalCount = validLinks.length;

  // 3. Apply search query
  if (linksNavState.searchQuery) {
    const query = linksNavState.searchQuery.toLowerCase();
    validLinks = validLinks.filter(link => {
      const searchFields = [
        link.name,
        link.source_label,
        link.target_label,
        link.relationship_type,
        link.description
      ].filter(Boolean).join(' ').toLowerCase();
      return searchFields.includes(query);
    });
  }

  // 4. Apply source label filter
  if (linksNavState.sourceLabel) {
    validLinks = validLinks.filter(l => l.source_label === linksNavState.sourceLabel);
  }

  // 5. Apply target label filter
  if (linksNavState.targetLabel) {
    validLinks = validLinks.filter(l => l.target_label === linksNavState.targetLabel);
  }

  // 6. Apply relationship type filter
  if (linksNavState.relType) {
    validLinks = validLinks.filter(l => l.relationship_type === linksNavState.relType);
  }

  // 7. Apply sort
  validLinks.sort((a, b) => {
    switch (linksNavState.sortBy) {
      case 'name': return (a.name || '').localeCompare(b.name || '');
      case 'source': return (a.source_label || '').localeCompare(b.source_label || '');
      case 'target': return (a.target_label || '').localeCompare(b.target_label || '');
      case 'rel_type': return (a.relationship_type || '').localeCompare(b.relationship_type || '');
      default: return 0;
    }
  });

  // Update result count
  updateResultCount(validLinks.length, totalCount);

  // 8-9. Group or render flat
  if (linksNavState.groupByRelType) {
    renderGroupedLinks(validLinks, container);
    return;
  }

  renderFlatLinks(validLinks, container);
}

function updateFilterTabCounts() {
  const validLinks = linkDefinitions.filter(link => link && link.id);
  const activeCount = validLinks.filter(l => l.status === 'active').length;
  const pendingCount = validLinks.filter(l => l.status === 'pending').length;
  const availableCount = discoveredRelationships.length;

  document.querySelector('[data-filter="active"]').textContent = `Active (${activeCount})`;
  document.querySelector('[data-filter="pending"]').textContent = `Pending (${pendingCount})`;
  document.querySelector('[data-filter="available"]').textContent = `Available (${availableCount})`;
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

// Render flat list of links
function renderFlatLinks(validLinks, container) {
  if (validLinks.length === 0) {
    const filterMsg = `No ${currentFilter} links`;
    container.innerHTML = `<div class="empty-state small">${filterMsg}</div>`;
    return;
  }

  const query = linksNavState.searchQuery;

  container.innerHTML = validLinks.map((link, index) => {
    const isActive = currentLink && currentLink.id === link.id;
    const isFocused = lastFocusedIndex === index;
    const classes = ['link-item', isActive && 'active', isFocused && 'focused'].filter(Boolean).join(' ');

    // Status badge (Active/Pending) with appropriate colors
    const status = link.status || 'pending';
    const statusColors = {
      'active': '#4caf50',    // Green
      'pending': '#ff9800',   // Yellow/Orange
      'available': '#999'     // Gray
    };
    const color = statusColors[status] || '#999';
    const statusBadge = `<span class="badge" style="background: ${color}; color: white; font-size: 0.7em; padding: 0.2em 0.4em; border-radius: 3px;">${status.toUpperCase()}</span>`;

    // Format badge (Cypher/Python) - moved to secondary position
    const format = link.type === 'script' ? 'Python' : 'Cypher';
    const formatBadge = `<span class="badge" style="background: #666; color: white; font-size: 0.65em; padding: 0.2em 0.4em; border-radius: 3px; margin-left: 0.25rem;">${format}</span>`;

    let descLine = '';
    if (link.type === 'wizard') {
      const sourceDisplay = link.source_label || link.source_type || '?';
      const targetDisplay = link.target_label || link.target_type || '?';
      const relDisplay = link.relationship_type || '?';
      descLine = query
        ? `${highlightMatch(sourceDisplay, query)} → ${highlightMatch(relDisplay, query)} → ${highlightMatch(targetDisplay, query)}`
        : `${escapeHtml(sourceDisplay)} → ${escapeHtml(relDisplay)} → ${escapeHtml(targetDisplay)}`;
    } else {
      const desc = link.description || 'Custom matching logic';
      descLine = query ? highlightMatch(desc, query) : escapeHtml(desc);
    }

    const linkName = query ? highlightMatch(link.name || 'Unnamed', query) : escapeHtml(link.name || 'Unnamed');

    // Action buttons based on link type
    let actionButtons = '';
    if (link.type === 'script') {
      actionButtons = `
        <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
          <button class="btn btn-sm btn-outline-primary btn-run-link" data-link-id="${link.id}" style="font-size: 0.75em;">
            Run
          </button>
          <button class="btn btn-sm btn-outline-secondary btn-view-script" data-link-id="${link.id}" style="font-size: 0.75em;">
            View Script
          </button>
        </div>
      `;
    } else {
      // Wizard type
      actionButtons = `
        <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
          <button class="btn btn-sm btn-outline-primary btn-run-link" data-link-id="${link.id}" style="font-size: 0.75em;">
            Run
          </button>
          <button class="btn btn-sm btn-outline-secondary btn-edit-link" data-link-id="${link.id}" style="font-size: 0.75em;">
            Edit
          </button>
        </div>
      `;
    }

    return `
      <div class="${classes}"
           data-link-id="${link.id}"
           data-link-type="${link.type || 'wizard'}"
           data-index="${index}"
           data-testid="link-item"
           tabindex="${isFocused ? '0' : '-1'}">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
          <strong style="font-size: 0.95em;">${linkName}</strong>
          <div>${statusBadge}${formatBadge}</div>
        </div>
        <div style="font-size: 0.85em; color: #666;">
          ${descLine}
        </div>
        ${actionButtons}
      </div>
    `;
  }).join('');

  // Attach button click handlers
  container.querySelectorAll('.btn-run-link').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const linkId = btn.dataset.linkId;
      runLinkDefinition(linkId);
    });
  });

  container.querySelectorAll('.btn-edit-link').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const linkId = btn.dataset.linkId;
      loadLinkDefinition(linkId);
    });
  });

  container.querySelectorAll('.btn-view-script').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const linkId = btn.dataset.linkId;
      // Navigate to Scripts page with script ID (which is the filename)
      window.location.href = `/scripts?script=${linkId}`;
    });
  });

  attachLinkClickHandlers(container);
}

// Render grouped links by relationship type
function renderGroupedLinks(validLinks, container) {
  if (validLinks.length === 0) {
    container.innerHTML = `<div class="empty-state small">No links match the current filters</div>`;
    return;
  }

  // Group by relationship type
  const grouped = {};
  validLinks.forEach(link => {
    const relType = link.relationship_type || 'Uncategorized';
    if (!grouped[relType]) grouped[relType] = [];
    grouped[relType].push(link);
  });

  // Sort groups by count descending
  const sortedGroups = Object.entries(grouped).sort((a, b) => b[1].length - a[1].length);

  const query = linksNavState.searchQuery;

  // Initialize collapsed state for new groups only (preserve user toggles)
  sortedGroups.forEach(([relType, links]) => {
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

  container.innerHTML = sortedGroups.map(([relType, links]) => {
    const isCollapsed = linksNavState.collapsedGroups.has(relType);
    const icon = isCollapsed ? '▶' : '▼';
    const collapsedClass = isCollapsed ? 'collapsed' : '';

    // Sort links within group by source then target
    links.sort((a, b) => {
      const sourceComp = (a.source_label || '').localeCompare(b.source_label || '');
      if (sourceComp !== 0) return sourceComp;
      return (a.target_label || '').localeCompare(b.target_label || '');
    });

    const linksHtml = links.map((link, index) => {
      const isActive = currentLink && currentLink.id === link.id;
      const classes = ['link-item', isActive && 'active'].filter(Boolean).join(' ');

      // Status badge (Active/Pending)
      const status = link.status || 'pending';
      const statusColors = {
        'active': '#4caf50',
        'pending': '#ff9800',
        'available': '#999'
      };
      const color = statusColors[status] || '#999';
      const statusBadge = `<span class="badge" style="background: ${color}; color: white; font-size: 0.7em; padding: 0.2em 0.4em; border-radius: 3px;">${status.toUpperCase()}</span>`;

      // Format badge (Cypher/Python)
      const format = link.type === 'script' ? 'Python' : 'Cypher';
      const formatBadge = `<span class="badge" style="background: #666; color: white; font-size: 0.65em; padding: 0.2em 0.4em; border-radius: 3px; margin-left: 0.25rem;">${format}</span>`;

      const sourceDisplay = link.source_label || link.source_type || '?';
      const targetDisplay = link.target_label || link.target_type || '?';
      const descLine = query
        ? `${highlightMatch(sourceDisplay, query)} → ${highlightMatch(targetDisplay, query)}`
        : `${escapeHtml(sourceDisplay)} → ${escapeHtml(targetDisplay)}`;

      const linkName = query ? highlightMatch(link.name || 'Unnamed', query) : escapeHtml(link.name || 'Unnamed');

      return `
        <div class="${classes}"
             data-link-id="${link.id}"
             data-link-type="${link.type || 'wizard'}"
             data-testid="link-item"
             style="padding: 0.5rem; margin-left: 1rem; border-left: 2px solid #e0e0e0;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
            <strong style="font-size: 0.9em;">${linkName}</strong>
            <div>${statusBadge}${formatBadge}</div>
          </div>
          <div style="font-size: 0.8em; color: #666;">
            ${descLine}
          </div>
        </div>
      `;
    }).join('');

    return `
      <div class="link-group">
        <div class="link-group-header" onclick="toggleGroup('${escapeHtml(relType)}')">
          <span>${icon} ${escapeHtml(relType)}</span>
          <span class="badge">${links.length}</span>
        </div>
        <div class="link-group-body ${collapsedClass}">
          ${linksHtml}
        </div>
      </div>
    `;
  }).join('');

  attachLinkClickHandlers(container);
}

// Attach click handlers to link items
function attachLinkClickHandlers(container) {
  container.querySelectorAll('.link-item').forEach(item => {
    item.addEventListener('click', () => {
      const linkId = item.dataset.linkId;
      const linkType = item.dataset.linkType;

      currentLink = linkDefinitions.find(l => l.id === linkId);

      container.querySelectorAll('.link-item').forEach(el => el.classList.remove('active'));
      item.classList.add('active');

      if (linkType === 'script') {
        openScriptLink(linkId);
      } else {
        loadLinkDefinition(linkId);
      }
    });
  });
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

// ===== Link Operations =====

function loadLinkDefinition(linkId) {
  console.log('[loadLinkDefinition] Loading link:', linkId);

  // Reset wizard panel to clean state (prevents state bleed)
  // Note: resetWizard() is defined below, called by import/discovery modules

  fetch(window.SCIDK_BASE + `/api/links/${linkId}`)
    .then(r => r.json())
    .then(data => {
      console.log('[loadLinkDefinition] Response:', JSON.stringify(data, null, 2));

      if (data.status === 'success') {
        currentLink = data.link;
        console.log('[loadLinkDefinition] Link loaded:', JSON.stringify(currentLink, null, 2));

        try {
          populateWizardFromLink(currentLink);
          showWizard();
        } catch (err) {
          console.error('[loadLinkDefinition] Error in populateWizardFromLink:', err);
          showToast(`Failed to populate wizard: ${err.message}`, 'error');
        }
      } else {
        console.error('[loadLinkDefinition] Failed to load link:', data);
        showToast(`Failed to load link: ${data.error || 'Unknown error'}`, 'error');
      }
    })
    .catch(err => {
      console.error('[loadLinkDefinition] Fetch error:', err);
      showToast('Failed to load link definition', 'error');
    });
}

// Handle script link selection - populate triple builder
function openScriptLink(scriptId) {
  // Find the script in linkDefinitions
  const scriptLink = linkDefinitions.find(l => l.id === scriptId && l.type === 'script');

  if (!scriptLink) {
    showToast('Script link not found', 'error');
    return;
  }

  currentLink = scriptLink;

  // Populate tripleBuilder with script link data
  tripleBuilder.link_id = scriptLink.id;
  tripleBuilder.name = scriptLink.name;

  // Extract source/target labels from script params if available
  tripleBuilder.source.label = scriptLink.source_label || '';
  tripleBuilder.source.filters = [];
  tripleBuilder.target.label = scriptLink.target_label || '';
  tripleBuilder.target.filters = [];

  // Set relationship info
  tripleBuilder.relationship.type = scriptLink.relationship_type || '';
  tripleBuilder.relationship.match_strategy = 'script'; // Special indicator for script-based
  tripleBuilder.relationship.match_config = {
    script_id: scriptLink.id,
    validation_status: scriptLink.validation_status,
    description: scriptLink.description
  };
  tripleBuilder.relationship.properties = [];

  // Populate link name
  const linkNameInput = document.getElementById('link-name');
  if (linkNameInput) {
    linkNameInput.value = scriptLink.name || '';
  }

  // Show wizard with script info banner
  const wizardTitle = document.getElementById('wizard-title');
  if (wizardTitle) {
    const statusEmoji = {
      'validated': '✅',
      'failed': '❌',
      'draft': '⚠️'
    }[scriptLink.validation_status || 'draft'] || '📝';

    wizardTitle.innerHTML = `
      <span style="background: #9c27b0; color: white; padding: 0.25em 0.75em; border-radius: 4px; font-size: 0.8em; margin-right: 0.5rem;">SCRIPT</span>
      ${scriptLink.name}
      <span style="font-size: 0.9em; margin-left: 0.5rem;">${statusEmoji} ${scriptLink.validation_status || 'draft'}</span>
    `;
  }

  // Add info banner about script-based link
  const mainTripleDisplay = document.getElementById('main-triple-display');
  if (mainTripleDisplay) {
    const existingBanner = mainTripleDisplay.parentElement.querySelector('.script-info-banner');
    if (existingBanner) existingBanner.remove();

    const banner = document.createElement('div');
    banner.className = 'script-info-banner';
    banner.style.cssText = 'background: #f0f7ff; border-left: 4px solid #9c27b0; padding: 1rem; margin-bottom: 1rem; border-radius: 4px;';
    banner.innerHTML = `
      <strong style="color: #7b1fa2;">💡 Script-Based Link</strong>
      <p style="margin: 0.5rem 0 0 0; font-size: 0.9em; color: #555;">
        This link uses custom Python code for matching logic.
        <a href="/scripts?script=${scriptLink.id}" style="color: #2196f3; text-decoration: underline;">Edit script</a> to change behavior.
        ${scriptLink.validation_status !== 'validated' ? '<br><strong style="color: #f57c00;">⚠️ Must validate script before execution</strong>' : ''}
      </p>
    `;
    mainTripleDisplay.parentElement.insertBefore(banner, mainTripleDisplay);
  }

  // Show delete button if exists
  const btnDeleteDef = document.getElementById('btn-delete-def');
  if (btnDeleteDef) {
    btnDeleteDef.style.display = 'inline-block';
  }

  // Show wizard
  showWizard();
}

function redirectToScript(scriptId) {
  // Deep link to Scripts page with this script open
  window.location.href = `/scripts?script=${scriptId}`;
}

function hideScriptLink() {
  // Placeholder function - modal close handled elsewhere
}

function populateWizardFromLink(link) {
  currentLink = link;

  // Branch early for Active links - show read-only panel instead of wizard
  if (link.status === 'active') {
    renderActiveLinkPanel(link);
    return;
  }

  // Populate tripleBuilder from link definition
  tripleBuilder.link_id = link.id;
  tripleBuilder.name = link.name;
  tripleBuilder.source.label = link.source_label || '';
  tripleBuilder.source.filters = link.source_filters || [];
  tripleBuilder.target.label = link.target_label || '';
  tripleBuilder.target.filters = link.target_filters || [];
  tripleBuilder.relationship.type = link.relationship_type || '';
  tripleBuilder.relationship.match_strategy = link.match_strategy || '';
  tripleBuilder.relationship.match_config = link.match_config || {};

  // Convert relationship_props object to properties array
  tripleBuilder.relationship.properties = [];
  if (link.relationship_props) {
    Object.entries(link.relationship_props).forEach(([name, value]) => {
      const type = (value && value.includes && (value.includes('source.') || value.includes('target.'))) ? 'calculated' : 'static';
      tripleBuilder.relationship.properties.push({ name, type, value });
    });
  }

  // Populate form fields
  const linkNameInput = document.getElementById('link-name');
  if (linkNameInput) {
    linkNameInput.value = link.name || '';
  }

  // Show delete button
  const btnDeleteDef = document.getElementById('btn-delete-def');
  if (btnDeleteDef) {
    btnDeleteDef.style.display = 'inline-block';
  }
}

function resetWizard() {
  currentLink = null;

  // Reset tripleBuilder state
  tripleBuilder.source = { label: '', filters: [] };
  tripleBuilder.relationship = { type: '', properties: [], match_strategy: '', match_config: {} };
  tripleBuilder.target = { label: '', filters: [] };
  tripleBuilder.link_id = null;
  tripleBuilder.name = '';

  // Reset form fields
  const linkNameInput = document.getElementById('link-name');
  if (linkNameInput) {
    linkNameInput.value = '';
  }

  // Ensure main-triple-display is visible (may have been hidden by Active link panel)
  const mainTripleDisplay = document.getElementById('main-triple-display');
  if (mainTripleDisplay) {
    mainTripleDisplay.style.display = 'block';
  }

  // Clear preview
  const previewContainer = document.getElementById('preview-container');
  if (previewContainer) {
    previewContainer.innerHTML = '<div class="empty-state small">Configure all three components to preview matches</div>';
  }

  // Hide delete button
  const btnDeleteDef = document.getElementById('btn-delete-def');
  if (btnDeleteDef) {
    btnDeleteDef.style.display = 'none';
  }

  // Remove script info banner if present
  const existingBanner = document.querySelector('.script-info-banner');
  if (existingBanner) {
    existingBanner.remove();
  }

  // Reset wizard title
  const wizardTitle = document.getElementById('wizard-title');
  if (wizardTitle) {
    wizardTitle.textContent = 'New Link Definition';
  }
}

function showWizard() {
  const linkWizard = document.getElementById('link-wizard');
  const wizardTitle = document.getElementById('wizard-title');

  if (linkWizard) {
    linkWizard.style.display = 'block';
  }
  if (wizardTitle) {
    wizardTitle.textContent = currentLink ? 'Edit Link Definition' : 'New Link Definition';
  }
}

function navigateStep(delta) {
  const newStep = currentStep + delta;
  if (newStep >= 1 && newStep <= 4) {
    navigateToStep(newStep);
  }
}

function navigateToStep(step) {
  currentStep = step;

  // Update step indicators
  document.querySelectorAll('.wizard-step').forEach((el, idx) => {
    const stepNum = idx + 1;
    el.classList.remove('active', 'completed');
    if (stepNum < step) {
      el.classList.add('completed');
      // Update step circle with visual summary
      updateStepSummary(stepNum);
    } else if (stepNum === step) {
      el.classList.add('active');
    }
  });

  // Update content visibility
  document.querySelectorAll('.wizard-step-content').forEach((el, idx) => {
    el.classList.toggle('active', idx + 1 === step);
  });

  // Update navigation buttons (3-step wizard - legacy, elements may not exist)
  const btnPrev = document.getElementById('btn-prev');
  const btnNext = document.getElementById('btn-next');
  const btnExecute = document.getElementById('btn-execute');
  if (btnPrev) btnPrev.style.display = step > 1 ? 'inline-block' : 'none';
  if (btnNext) btnNext.style.display = step < 3 ? 'inline-block' : 'none';
  if (btnExecute) btnExecute.style.display = step === 3 ? 'inline-block' : 'none';

  // Update visual pattern display when on Step 2
  if (step === 2) {
    updateVisualPattern();
  }
}

function updateStepSummary(stepNum) {
  const circle = document.querySelector(`[data-step="${stepNum}"] .wizard-step-circle`);
  const tooltip = document.querySelector(`[data-step="${stepNum}"] .wizard-step-tooltip`);

  if (stepNum === 1) {
    // Step 1: Show source label name (legacy - may not exist)
    const sourceSelect = document.getElementById('source-label-select');
    const sourceLabel = sourceSelect ? sourceSelect.value : tripleBuilder.source.label;
    if (sourceLabel) {
      if (circle) circle.textContent = sourceLabel;
      if (tooltip) tooltip.textContent = `Source: ${sourceLabel}`;
    }
  } else if (stepNum === 2) {
    // Step 2: Show match strategy icon
    const strategy = document.querySelector('.match-strategy-btn.active')?.dataset.strategy;
    const strategyIcons = {
      'property': '=',
      'fuzzy': '~',
      'table_import': '📊',
      'api_endpoint': '🔌',
      'table_import': '📥'
    };
    const strategyNames = {
      'property': 'Property Match',
      'fuzzy': 'Fuzzy Match',
      'table_import': 'Table Import',
      'api_endpoint': 'API Endpoint',
      'table_import': 'Data Import'
    };
    if (strategy) {
      circle.textContent = strategyIcons[strategy] || strategy;
      tooltip.textContent = `Match: ${strategyNames[strategy] || strategy}`;
    }
  } else if (stepNum === 3) {
    // Step 3: Show relationship type (legacy - may not exist)
    const relTypeInput = document.getElementById('rel-type');
    const relType = relTypeInput ? relTypeInput.value : tripleBuilder.relationship.type;
    if (relType) {
      if (circle) circle.textContent = relType.substring(0, 8);
      const targetSelect = document.getElementById('target-label-select');
      const targetLabel = targetSelect ? targetSelect.value : tripleBuilder.target.label;
      if (tooltip) tooltip.textContent = `${relType}${targetLabel ? ' → ' + targetLabel : ''}`;
    }
  }
}

function showMatchConfig(strategy) {
  document.querySelectorAll('.match-config').forEach(el => el.style.display = 'none');
  const matchEl = document.getElementById(`match-${strategy.replace('_', '-')}`);
  if (matchEl) {
    matchEl.style.display = 'block';
  }

  // If data_import, populate database dropdown
  if (strategy === 'table_import') {
    populateDataImportDatabases();
  }

  // Update visual pattern display for current strategy
  updateVisualPattern();
}

function populateDataImportDatabases() {
  const select = document.getElementById('data-import-source-db');

  // Get unique external databases from discovered relationships
  const externalDbs = discoveredRelationships
    .map(r => r.database)
    .filter((db, index, self) => db !== 'PRIMARY' && self.indexOf(db) === index);

  if (externalDbs.length === 0) {
    select.innerHTML = '<option value="">No external databases configured</option>';
  } else {
    select.innerHTML = '<option value="">Select external database...</option>' +
      externalDbs.map(db => `<option value="${db}">${db}</option>`).join('');
  }
}

function updateVisualPattern() {
  // Get current values (legacy - elements may not exist)
  const sourceSelect = document.getElementById('source-label-select');
  const targetSelect = document.getElementById('target-label-select');
  const relTypeInput = document.getElementById('rel-type');
  const sourceLabel = wizardData.source_label || (sourceSelect ? sourceSelect.value : '') || tripleBuilder.source.label || '-';
  const targetLabel = wizardData.target_label || (targetSelect ? targetSelect.value : '') || tripleBuilder.target.label || '-';
  const relType = wizardData.relationship_type || (relTypeInput ? relTypeInput.value : '') || tripleBuilder.relationship.type || '-';
  const strategy = wizardData.match_strategy || tripleBuilder.relationship.match_strategy;

  // Update visual pattern displays based on strategy
  if (strategy === 'table_import') {
    // Data import uses different ID naming convention
    const sourceEl = document.getElementById('data-import-source-label-display');
    const targetEl = document.getElementById('data-import-target-label-display');
    const relEl = document.getElementById('data-import-rel-type-display');

    if (sourceEl) sourceEl.textContent = sourceLabel;
    if (targetEl) targetEl.textContent = targetLabel;
    if (relEl) relEl.textContent = relType;

    // Show stats if available
    if (wizardData.match_config && wizardData.match_config.triple_count) {
      document.getElementById('data-import-stats').style.display = 'block';
      document.getElementById('data-import-count').textContent = wizardData.match_config.triple_count.toLocaleString();
      document.getElementById('data-import-method').textContent = 'Streaming batch import (10K per batch)';
    } else {
      document.getElementById('data-import-stats').style.display = 'none';
    }
  } else {
    // Other strategies use consistent naming
    const strategyPrefix = {
      'property': 'property',
      'fuzzy': 'fuzzy',
      'table_import': 'table',
      'api_endpoint': 'api'
    }[strategy];

    if (strategyPrefix) {
      const sourceEl = document.getElementById(`${strategyPrefix}-source-display`);
      const targetEl = document.getElementById(`${strategyPrefix}-target-display`);
      const relEl = document.getElementById(`${strategyPrefix}-rel-display`);

      if (sourceEl) sourceEl.textContent = sourceLabel;
      if (targetEl) targetEl.textContent = targetLabel;
      if (relEl) relEl.textContent = relType;
    }
  }
}

function addRelationshipProperty() {
  const container = document.getElementById('rel-props-container');
  const row = document.createElement('div');
  row.className = 'property-row';
  row.innerHTML = `
    <input type="text" class="form-control form-control-sm" placeholder="key" data-prop-key />
    <input type="text" class="form-control form-control-sm" placeholder="value" data-prop-value />
    <button class="btn btn-sm btn-outline-danger btn-sm-icon" onclick="this.parentElement.remove()">×</button>
  `;
  container.appendChild(row);
}

function renderRelationshipProps() {
  const container = document.getElementById('rel-props-container');
  container.innerHTML = '';
  Object.entries(wizardData.relationship_props || {}).forEach(([key, value]) => {
    const row = document.createElement('div');
    row.className = 'property-row';
    row.innerHTML = `
      <input type="text" class="form-control form-control-sm" value="${key}" data-prop-key />
      <input type="text" class="form-control form-control-sm" value="${value}" data-prop-value />
      <button class="btn btn-sm btn-outline-danger btn-sm-icon" onclick="this.parentElement.remove()">×</button>
    `;
    container.appendChild(row);
  });
}

function collectWizardData() {
  // Step 1: Source Label (legacy - elements may not exist)
  const linkNameInput = document.getElementById('link-name');
  const sourceSelect = document.getElementById('source-label-select');
  wizardData.name = linkNameInput ? linkNameInput.value.trim() : tripleBuilder.name;
  wizardData.source_label = sourceSelect ? sourceSelect.value.trim() : tripleBuilder.source.label;

  // Step 2: Match Strategy
  if (wizardData.match_strategy === 'property') {
    wizardData.match_config = {
      source_field: document.getElementById('match-source-field').value.trim(),
      target_field: document.getElementById('match-target-field').value.trim()
    };
  } else if (wizardData.match_strategy === 'fuzzy') {
    wizardData.match_config = {
      source_field: document.getElementById('fuzzy-source-field').value.trim(),
      target_field: document.getElementById('fuzzy-target-field').value.trim(),
      threshold: parseInt(document.getElementById('fuzzy-threshold').value) || 80
    };
  } else if (wizardData.match_strategy === 'table_import') {
    wizardData.match_config = {
      table_data: document.getElementById('table-data').value.trim()
    };
  } else if (wizardData.match_strategy === 'api_endpoint') {
    wizardData.match_config = {
      url: document.getElementById('api-url').value.trim(),
      json_path: document.getElementById('api-jsonpath').value.trim()
    };
  } else if (wizardData.match_strategy === 'table_import') {
    // Data import configuration - preserve existing match_config but update source_database
    wizardData.match_config = {
      ...wizardData.match_config,
      source_database: document.getElementById('data-import-source-db').value.trim()
    };
  }

  // Step 3: Target Label & Relationship (legacy - elements may not exist)
  const targetSelect = document.getElementById('target-label-select');
  const relTypeInput = document.getElementById('rel-type');
  wizardData.target_label = targetSelect ? targetSelect.value.trim() : tripleBuilder.target.label;
  wizardData.relationship_type = relTypeInput ? relTypeInput.value.trim() : tripleBuilder.relationship.type;

  const props = {};
  document.querySelectorAll('#rel-props-container .property-row').forEach(row => {
    const key = row.querySelector('[data-prop-key]').value.trim();
    const value = row.querySelector('[data-prop-value]').value.trim();
    if (key) {
      props[key] = value;
    }
  });
  wizardData.relationship_props = props;

  return wizardData;
}

function saveLinkDefinition() {
  const linkName = document.getElementById('link-name').value.trim();

  if (!linkName) {
    showToast('Link name is required', 'error');
    return;
  }

  if (!tripleBuilder.relationship.type) {
    showToast('Relationship type is required', 'error');
    return;
  }

  if (!tripleBuilder.source.label || !tripleBuilder.target.label) {
    showToast('Source and target labels are required', 'error');
    return;
  }

  if (!tripleBuilder.relationship.match_strategy) {
    showToast('Match strategy is required', 'error');
    return;
  }

  // Convert tripleBuilder state to API format
  const relationshipProps = {};
  tripleBuilder.relationship.properties.forEach(prop => {
    relationshipProps[prop.name] = prop.value;
  });

  const data = {
    id: tripleBuilder.link_id,
    name: linkName,
    source_label: tripleBuilder.source.label,
    source_filters: tripleBuilder.source.filters,
    target_label: tripleBuilder.target.label,
    target_filters: tripleBuilder.target.filters,
    relationship_type: tripleBuilder.relationship.type,
    match_strategy: tripleBuilder.relationship.match_strategy,
    match_config: tripleBuilder.relationship.match_config,
    relationship_props: relationshipProps
  };

  showToast('Saving link definition...', 'info');

  const method = tripleBuilder.link_id ? 'PUT' : 'POST';
  const url = tripleBuilder.link_id ? window.SCIDK_BASE + `/api/links/${tripleBuilder.link_id}` : window.SCIDK_BASE + '/api/links';

  fetch(url, {
    method: method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
    .then(async response => {
      const result = await response.json();

      if (!response.ok) {
        console.error('Backend rejected link definition:', result);
        console.error('Payload sent:', data);
        throw new Error(result.detail || result.error || `HTTP ${response.status}`);
      }

      return result;
    })
    .then(result => {
      if (result.status === 'success') {
        showToast('Link definition saved', 'success');
        tripleBuilder.link_id = result.link.id;
        currentLink = result.link;
        loadLinkDefinitions();
        document.getElementById('btn-delete-def').style.display = 'inline-block';
      } else {
        showToast(`Failed to save: ${result.error}`, 'error');
      }
    })
    .catch(err => {
      console.error('Save link error:', err);
      showToast(`Failed to save link definition: ${err.message}`, 'error');
    });
}

function deleteLinkDefinition() {
  if (!tripleBuilder.link_id) return;
  if (!confirm('Delete this link definition?')) return;

  fetch(window.SCIDK_BASE + `/api/links/${tripleBuilder.link_id}`, { method: 'DELETE' })
    .then(r => r.json())
    .then(result => {
      if (result.status === 'success') {
        showToast('Link definition deleted', 'success');
        loadLinkDefinitions();
        resetWizard();
        document.getElementById('link-wizard').style.display = 'none';
      } else {
        showToast(`Failed to delete: ${result.error}`, 'error');
      }
    })
    .catch(err => showToast('Failed to delete link definition', 'error'));
}

// ===== Execution Functions =====

function executeLink() {
  if (!tripleBuilder.link_id) {
    showToast('Please save the definition first', 'error');
    return;
  }

  if (!confirm('Execute this link workflow? This will create relationships in Neo4j.')) {
    return;
  }

  // Show progress indicator in preview container
  document.getElementById('preview-container').innerHTML = `
    <div style="padding: 2rem; text-align: center;">
      <div style="font-size: 2rem; margin-bottom: 1rem;">⚙️</div>
      <div style="font-weight: bold; margin-bottom: 0.5rem;">Starting execution...</div>
      <div id="task-progress-message" style="color: #666; font-size: 0.9rem;">Initializing...</div>
      <div id="task-progress-bar" style="width: 100%; height: 8px; background: #eee; border-radius: 4px; margin: 1rem 0; overflow: hidden;">
        <div id="task-progress-fill" style="width: 0%; height: 100%; background: #2196f3; transition: width 0.3s ease;"></div>
      </div>
      <div id="task-progress-stats" style="font-size: 0.85rem; color: #999;"></div>
    </div>
  `;

  fetch(window.SCIDK_BASE + `/api/links/${tripleBuilder.link_id}/execute`, { method: 'POST' })
    .then(r => r.json())
    .then(result => {
      if (result.status === 'success') {
        const taskId = result.job_id;  // This is actually the task_id from background task system
        pollTaskStatus(taskId);
      } else {
        document.getElementById('preview-container').innerHTML = `<div class="empty-state small" style="color: #f44336;">Execution failed: ${result.error}</div>`;
      }
    })
    .catch(err => {
      document.getElementById('preview-container').innerHTML = `<div class="empty-state small" style="color: #f44336;">Failed to start execution</div>`;
    });
}

// Global variable to track active regular task polling interval
let activeTaskPollingInterval = null;

function pollTaskStatus(taskId) {
  // Clear any existing polling interval to prevent multiple polls
  if (activeTaskPollingInterval) {
    clearInterval(activeTaskPollingInterval);
  }

  activeTaskPollingInterval = setInterval(() => {
    fetch(window.SCIDK_BASE + `/api/tasks/${taskId}`)
      .then(r => {
        if (r.status === 404) {
          clearInterval(activeTaskPollingInterval);
          activeTaskPollingInterval = null;
          console.log('[pollTaskStatus] Task not found (404), stopping poll');
          document.getElementById('preview-container').innerHTML = `<div class="empty-state small" style="color: #f44336;">Task not found (may have been deleted)</div>`;
          return null;
        }
        return r.json();
      })
      .then(task => {
        if (!task) return; // 404 case
        // Update progress UI
        const progressMsg = document.getElementById('task-progress-message');
        const progressFill = document.getElementById('task-progress-fill');
        const progressStats = document.getElementById('task-progress-stats');

        if (progressMsg) {
          progressMsg.textContent = task.status_message || 'Processing...';
        }

        if (progressFill && task.progress !== undefined) {
          progressFill.style.width = `${Math.round(task.progress * 100)}%`;
        }

        if (progressStats && task.processed && task.total) {
          progressStats.textContent = `${task.processed.toLocaleString()} / ${task.total.toLocaleString()} processed`;
        }

        // Check completion status
        if (task.status === 'completed') {
          clearInterval(activeTaskPollingInterval);
          activeTaskPollingInterval = null;
          const relCount = task.relationships_created || task.executed_count || 0;
          const relType = tripleBuilder.relationship.type || 'relationship';
          const propsCount = (tripleBuilder.relationship.properties || []).length;

          // Build detailed result message
          let resultMessage = `${relCount.toLocaleString()} ${relType} relationships created`;
          if (propsCount > 0) {
            resultMessage += ` with ${propsCount} ${propsCount === 1 ? 'property' : 'properties'} each`;
          }

          document.getElementById('preview-container').innerHTML = `
            <div style="padding: 2rem; text-align: center;">
              <div style="font-size: 3rem; color: #4caf50; margin-bottom: 1rem;">✓</div>
              <div style="font-weight: bold; font-size: 1.2rem; margin-bottom: 0.5rem;">Execution Complete!</div>
              <div style="color: #666;">${resultMessage}</div>
              ${task.status_message ? `<div style="margin-top: 1rem; font-size: 0.85rem; color: #999;">${task.status_message}</div>` : ''}
            </div>
          `;
          showToast(`Completed! ${resultMessage}`, 'success');
        } else if (task.status === 'error' || task.status === 'failed') {
          clearInterval(activeTaskPollingInterval);
          activeTaskPollingInterval = null;
          document.getElementById('preview-container').innerHTML = `
            <div style="padding: 2rem; text-align: center;">
              <div style="font-size: 3rem; color: #f44336; margin-bottom: 1rem;">✗</div>
              <div style="font-weight: bold; font-size: 1.2rem; margin-bottom: 0.5rem;">Execution Failed</div>
              <div style="color: #666; font-size: 0.9rem;">${task.error || 'Unknown error'}</div>
            </div>
          `;
          showToast(`Execution failed: ${task.error || 'Unknown error'}`, 'error');
        } else if (task.status === 'canceled') {
          clearInterval(activeTaskPollingInterval);
          activeTaskPollingInterval = null;
          document.getElementById('preview-container').innerHTML = `
            <div style="padding: 2rem; text-align: center;">
              <div style="font-size: 3rem; color: #ff9800; margin-bottom: 1rem;">⊘</div>
              <div style="font-weight: bold; font-size: 1.2rem;">Execution Canceled</div>
            </div>
          `;
          showToast('Execution canceled', 'info');
        }
      })
      .catch(err => {
        clearInterval(activeTaskPollingInterval);
        activeTaskPollingInterval = null;
        document.getElementById('preview-container').innerHTML = `<div class="empty-state small" style="color: #f44336;">Failed to poll status</div>`;
      });
  }, 1000);  // Poll every second for responsive progress updates
}

// Run a link definition by loading it into the wizard and executing it
function runLinkDefinition(linkId) {
  const link = linkDefinitions.find(l => l.id === linkId);
  if (!link) {
    showToast('Link not found', 'error');
    return;
  }

  // Load the link into the wizard
  if (link.type === 'script') {
    openScriptLink(linkId);
  } else {
    loadLinkDefinition(linkId);
  }

  // Execute after a short delay to let the wizard populate
  setTimeout(() => {
    if (link.type === 'script') {
      // Script execution handled by script-specific functions
      showToast('Script link execution - use Edit > Run from Scripts page', 'info');
    } else {
      executeLink();
    }
  }, 100);
}

// ===== Discovered Import Wizard =====

async function openImportWizardForRelationship(rel) {
  console.log('[Links] openImportWizardForRelationship called with:', rel);

  // Reset wizard panel to clean state (prevents state bleed)
  resetWizard();

  // Each rel now has exactly one database (no more merging)
  const database = rel.database;

  console.log('[Import] Opening wizard for:', database, rel.source_label, rel.rel_type, rel.target_label);

  // Initialize import configuration
  discoveredImportConfig.rel = rel;
  discoveredImportConfig.database = database;
  discoveredImportConfig.source.label = rel.source_label;
  discoveredImportConfig.target.label = rel.target_label;
  discoveredImportConfig.relationship.type = rel.rel_type;

  // Show wizard panel with title
  const wizardTitle = document.getElementById('wizard-title');
  if (wizardTitle) {
    wizardTitle.innerHTML = `
      <span style="background: #ff9800; color: white; padding: 0.25em 0.75em; border-radius: 4px; font-size: 0.8em; margin-right: 0.5rem;">IMPORT</span>
      ${rel.source_label} -[${rel.rel_type}]-> ${rel.target_label}
    `;
  }

  // Show wizard panel
  showWizard();

  // Hide Save Definition, Execute, and Delete buttons for discovered import workflow
  const btnSaveDef = document.getElementById('btn-save-def');
  const btnExecute = document.getElementById('btn-execute');
  const btnDeleteDef = document.getElementById('btn-delete-def');
  if (btnSaveDef) btnSaveDef.style.display = 'none';
  if (btnExecute) btnExecute.style.display = 'none';
  if (btnDeleteDef) btnDeleteDef.style.display = 'none';

  // Auto-populate link name
  const linkNameInput = document.getElementById('link-name');
  if (linkNameInput) {
    linkNameInput.value = `${rel.source_label} ${rel.rel_type} ${rel.target_label}`;
  }

  // Show loading state in triple display
  const mainTripleDisplay = document.getElementById('main-triple-display');
  if (mainTripleDisplay) {
    mainTripleDisplay.style.display = 'block'; // Ensure it's visible
    mainTripleDisplay.innerHTML = '<div style="text-align: center; padding: 2rem; color: #999;">Loading properties...</div>';
  }

  // Fetch properties for source, target, and relationship
  try {
    const [sourceProps, targetProps, relProps] = await Promise.all([
      fetchLabelProperties(rel.source_label, database),
      fetchLabelProperties(rel.target_label, database),
      fetchRelationshipProperties(database, rel.source_label, rel.rel_type, rel.target_label)
    ]);

    discoveredImportConfig.source.available_properties = sourceProps;
    discoveredImportConfig.target.available_properties = targetProps;
    discoveredImportConfig.relationship.available_properties = relProps;

    // Auto-detect UID properties (function defined in links-discovery.js)
    discoveredImportConfig.source.uid_property = autoDetectUidProperty(sourceProps);
    discoveredImportConfig.target.uid_property = autoDetectUidProperty(targetProps);

    // Show guidance toast based on auto-detection results
    const sourceUid = discoveredImportConfig.source.uid_property;
    const targetUid = discoveredImportConfig.target.uid_property;

    if (sourceUid && targetUid) {
      showToast(`Auto-selected UID properties: source.${sourceUid}, target.${targetUid}`, 'success');
    } else if (!sourceUid && !targetUid) {
      showToast('Please configure Source and Target UID properties', 'warning');
    } else if (!sourceUid) {
      showToast('Please configure Source UID property', 'warning');
    } else if (!targetUid) {
      showToast('Please configure Target UID property', 'warning');
    }

    // Update the clickable triple display (function defined in links-import.js)
    updateDiscoveredImportDisplay();
  } catch (err) {
    console.error('Failed to load properties:', err);
    showToast('Failed to load properties', 'error');
  }

  // Show empty preview - user must click "Load Preview" explicitly
  const previewContainer = document.getElementById('preview-container');
  if (previewContainer) {
    previewContainer.innerHTML = '<div class="empty-state small">Configure all three components to preview matches</div>';
  }
}

// ===== Keyboard Navigation =====

// Global keyboard navigation handler
function handleGlobalKeydown(e) {
  // Don't intercept if user is typing in an input/textarea/select
  const activeElement = document.activeElement;
  const isTyping = activeElement && (
    activeElement.tagName === 'INPUT' ||
    activeElement.tagName === 'TEXTAREA' ||
    activeElement.tagName === 'SELECT'
  );

  // Let buttons and links handle Enter/Space themselves, UNLESS we're actively navigating links
  if (activeElement && (activeElement.tagName === 'BUTTON' || activeElement.tagName === 'A') && (e.key === 'Enter' || e.key === ' ')) {
    if (e.key === 'Enter' && lastFocusedIndex >= 0 && lastFocusedIndex < linkDefinitions.length) {
      const focusIsInSidePanel = activeElement.closest('#link-list');
      if (focusIsInSidePanel) {
        e.preventDefault();
        const validLinks = linkDefinitions.filter(link => link && link.id);
        if (lastFocusedIndex < validLinks.length) {
          loadLinkDefinition(validLinks[lastFocusedIndex].id);
        }
        return;
      }
    }
    return;
  }

  // Escape key in wizard: return focus to side panel
  if (e.key === 'Escape' && !isTyping) {
    const isInWizard = activeElement && activeElement.closest('#link-wizard');
    if (isInWizard && lastFocusedIndex >= 0 && lastFocusedIndex < linkDefinitions.length) {
      e.preventDefault();
      returnFocusToSidePanel();
      return;
    }
  }

  // Escape key while typing in wizard: return focus to side panel
  if (e.key === 'Escape' && isTyping) {
    const isInWizard = activeElement && activeElement.closest('#link-wizard');
    if (isInWizard) {
      e.preventDefault();
      returnFocusToSidePanel();
      return;
    }
  }

  // Don't handle other keys if user is typing
  if (isTyping) return;

  // Handle navigation keys
  const validLinks = linkDefinitions.filter(link => link && link.id);

  switch(e.key) {
    case 'ArrowUp':
      e.preventDefault();
      navigateLinks(-1);
      break;
    case 'ArrowDown':
      e.preventDefault();
      navigateLinks(1);
      break;
    case 'Home':
      e.preventDefault();
      navigateToLink(0);
      break;
    case 'End':
      e.preventDefault();
      navigateToLink(validLinks.length - 1);
      break;
    case 'PageUp':
      e.preventDefault();
      navigateLinks(-10);
      break;
    case 'PageDown':
      e.preventDefault();
      navigateLinks(10);
      break;
    case 'Enter':
      if (lastFocusedIndex >= 0 && lastFocusedIndex < validLinks.length) {
        const focusInWizard = document.activeElement && document.activeElement.closest('#link-wizard');
        if (!focusInWizard) {
          e.preventDefault();
          loadLinkDefinition(validLinks[lastFocusedIndex].id);
        }
      }
      break;
  }
}

function navigateLinks(delta) {
  const validLinks = linkDefinitions.filter(link => link && link.id);
  if (validLinks.length === 0) return;

  let newIndex;
  if (lastFocusedIndex === -1) {
    newIndex = delta > 0 ? 0 : validLinks.length - 1;
  } else {
    newIndex = lastFocusedIndex + delta;
  }

  newIndex = Math.max(0, Math.min(validLinks.length - 1, newIndex));
  navigateToLink(newIndex);
}

function navigateToLink(index) {
  const validLinks = linkDefinitions.filter(link => link && link.id);
  if (index < 0 || index >= validLinks.length) return;

  lastFocusedIndex = index;
  renderLinkList();

  // Scroll into view
  const container = document.getElementById('link-list');
  const items = container.querySelectorAll('.link-item');
  if (items[index]) {
    items[index].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    items[index].focus();
  }
}

function returnFocusToSidePanel() {
  const container = document.getElementById('link-list');
  const items = container.querySelectorAll('.link-item');
  if (lastFocusedIndex >= 0 && lastFocusedIndex < items.length) {
    items[lastFocusedIndex].focus();
  }
}
