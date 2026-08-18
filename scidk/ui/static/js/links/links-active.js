// ===== Active Link Rendering Functions =====

async function renderActiveLinkPanel(link) {
  console.log('[renderActiveLinkPanel] Rendering Active link:', link);

  // Show wizard panel
  showWizard();

  // Set wizard title
  const wizardTitle = document.getElementById('wizard-title');
  if (wizardTitle) {
    wizardTitle.textContent = 'Active Link';
  }

  // Get containers
  const mainTripleDisplay = document.getElementById('main-triple-display');
  const linkNameContainer = document.querySelector('.form-group');
  const previewExecuteSection = document.getElementById('preview-execute-section');
  const previewContainer = document.getElementById('preview-container');

  // Hide wizard step navigation and standard triple builder
  if (mainTripleDisplay) {
    mainTripleDisplay.style.display = 'none';
  }

  // Hide link name input
  if (linkNameContainer) {
    linkNameContainer.style.display = 'none';
  }

  // Show preview section but replace content
  if (previewExecuteSection) {
    previewExecuteSection.style.display = 'block';
  }

  // Parse match_config
  const matchConfig = typeof link.match_config === 'string'
    ? JSON.parse(link.match_config || '{}')
    : (link.match_config || {});

  const isImportLink = !!matchConfig.source_database;
  const sourceLabel = link.source_label || '';
  const targetLabel = link.target_label || '';
  const relType = link.relationship_type || '';

  // Build read-only triple display with UID selectors
  const panelHtml = `
    <div id="active-link-triple-container" style="margin-bottom: 2rem;">
      <div style="display: flex; align-items: center; gap: 1rem; padding: 1rem; background: #f5f7fa; border-radius: 6px; margin-bottom: 1.5rem;">
        <span style="padding: 0.5rem 1rem; background: #2196f3; color: white; border-radius: 4px; font-weight: 500;">${escapeHtml(sourceLabel)}</span>
        <span style="color: #666;">→</span>
        <span style="padding: 0.5rem 1rem; background: #ff9800; color: white; border-radius: 4px; font-weight: 500;">${escapeHtml(relType)}</span>
        <span style="color: #666;">→</span>
        <span style="padding: 0.5rem 1rem; background: #4caf50; color: white; border-radius: 4px; font-weight: 500;">${escapeHtml(targetLabel)}</span>
      </div>

      <div style="background: white; padding: 1.5rem; border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 1.5rem;">
        <h5 style="margin: 0 0 1rem 0; color: #333;">UID Properties (for future sync matching)</h5>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
          <div>
            <label class="form-label small" style="font-weight: 500;">Source UID:</label>
            <select id="active-source-uid" class="form-control form-control-sm" onchange="updateActiveLinkUIDProperty('source', this.value)">
              <option value="">Loading...</option>
            </select>
          </div>
          <div>
            <label class="form-label small" style="font-weight: 500;">Target UID:</label>
            <select id="active-target-uid" class="form-control form-control-sm" onchange="updateActiveLinkUIDProperty('target', this.value)">
              <option value="">Loading...</option>
            </select>
          </div>
        </div>
      </div>
    </div>
    <div id="active-link-sync-container"></div>
  `;

  if (previewContainer) {
    previewContainer.innerHTML = panelHtml;
  }

  // Load UID property dropdowns
  await loadUIDPropertyOptions(link);

  // Show button controls
  updateActiveLinkButtons(link);

  // Show sync status and index
  if (isImportLink) {
    await showSyncStatusForActiveImportLink(link.id, link);
  } else {
    // Algorithmic/script link - show basic info and index
    if (previewContainer) {
      previewContainer.innerHTML += `
        <div style="margin-top: 1.5rem;" id="active-link-info-container"></div>
      `;

      const infoContainer = document.getElementById('active-link-info-container');
      if (infoContainer) {
        infoContainer.innerHTML = `
          <div style="padding: 1.5rem; background: #f5f5f5; border-radius: 6px; margin-bottom: 1.5rem;">
            <h5 style="margin: 0 0 0.75rem 0; color: #333;">Algorithmic Link</h5>
            <div style="font-size: 0.9em; color: #666; margin-bottom: 1rem;">
              <div>Last run: ${formatLastRun(link.updated_at)}</div>
            </div>
          </div>
          <div id="active-link-index-container"></div>
        `;
      }
    }

    await showRelationshipIndex(link.id, {
      containerId: 'active-link-index-container',
      source_label: sourceLabel,
      rel_type: relType,
      target_label: targetLabel,
      source_database: null
    });
  }
}

async function loadUIDPropertyOptions(link) {
  const sourceUidSelect = document.getElementById('active-source-uid');
  const targetUidSelect = document.getElementById('active-target-uid');

  if (!sourceUidSelect || !targetUidSelect) return;

  const matchConfig = typeof link.match_config === 'string'
    ? JSON.parse(link.match_config || '{}')
    : (link.match_config || {});

  const sourceLabel = link.source_label;
  const targetLabel = link.target_label;

  try {
    // Fetch source properties
    const sourceResponse = await fetch(window.SCIDK_BASE + '/api/neo4j/label-properties', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ database: 'PRIMARY', label: sourceLabel })
    });
    const sourceData = await sourceResponse.json();

    if (sourceData.status === 'success' && sourceData.properties) {
      // Determine which value to select: stored value > auto-detect > none
      const storedSourceUid = matchConfig.source_uid_property;
      const selectedSourceUid = storedSourceUid || autoDetectUidProperty(sourceData.properties);

      sourceUidSelect.innerHTML = sourceData.properties.map(prop =>
        `<option value="${escapeHtml(prop)}" ${prop === selectedSourceUid ? 'selected' : ''}>${escapeHtml(prop)}</option>`
      ).join('');
    }

    // Fetch target properties
    const targetResponse = await fetch(window.SCIDK_BASE + '/api/neo4j/label-properties', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ database: 'PRIMARY', label: targetLabel })
    });
    const targetData = await targetResponse.json();

    if (targetData.status === 'success' && targetData.properties) {
      // Determine which value to select: stored value > auto-detect > none
      const storedTargetUid = matchConfig.target_uid_property;
      const selectedTargetUid = storedTargetUid || autoDetectUidProperty(targetData.properties);

      targetUidSelect.innerHTML = targetData.properties.map(prop =>
        `<option value="${escapeHtml(prop)}" ${prop === selectedTargetUid ? 'selected' : ''}>${escapeHtml(prop)}</option>`
      ).join('');
    }
  } catch (err) {
    console.error('Failed to load UID properties:', err);
    sourceUidSelect.innerHTML = '<option value="">Error loading properties</option>';
    targetUidSelect.innerHTML = '<option value="">Error loading properties</option>';
  }
}

async function updateActiveLinkUIDProperty(side, value) {
  if (!currentLink) return;

  // Update match_config with new UID property
  const matchConfig = typeof currentLink.match_config === 'string'
    ? JSON.parse(currentLink.match_config || '{}')
    : (currentLink.match_config || {});

  if (side === 'source') {
    matchConfig.source_uid_property = value;
  } else {
    matchConfig.target_uid_property = value;
  }

  // Save link definition with updated match_config
  try {
    const response = await fetch(window.SCIDK_BASE + '/api/links', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: currentLink.id,
        name: currentLink.name,
        source_label: currentLink.source_label,
        target_label: currentLink.target_label,
        relationship_type: currentLink.relationship_type,
        match_strategy: currentLink.match_strategy,
        match_config: matchConfig,
        source_config: currentLink.source_config || {},
        target_config: currentLink.target_config || {},
        relationship_props: currentLink.relationship_props || {},
        status: currentLink.status
      })
    });

    const result = await response.json();

    if (result.status === 'success') {
      showToast(`${side === 'source' ? 'Source' : 'Target'} UID property updated to ${value}`, 'success');
      currentLink.match_config = matchConfig;

      // Refresh the relationship index table to show values for the new UID
      await loadRelationshipIndexPage('active-link-index-container');
    } else {
      showToast(`Failed to update UID property: ${result.error}`, 'error');
    }
  } catch (err) {
    console.error('Failed to update UID property:', err);
    showToast('Failed to update UID property', 'error');
  }
}

function updateActiveLinkButtons(link) {
  // Show only Delete and Refresh buttons
  const btnSaveDef = document.getElementById('btn-save-def');
  const btnExecute = document.getElementById('btn-execute');
  const btnDeleteDef = document.getElementById('btn-delete-def');
  const btnExportCsv = document.getElementById('btn-export-csv');
  const btnImportCsv = document.getElementById('btn-import-csv');

  if (btnSaveDef) btnSaveDef.style.display = 'none';
  if (btnExecute) {
    btnExecute.style.display = 'inline-block';
    btnExecute.textContent = 'Refresh';
    btnExecute.disabled = false;
    // Override the global executeLink() handler with refreshActiveLink()
    btnExecute.onclick = () => refreshActiveLink();
  }
  if (btnDeleteDef) btnDeleteDef.style.display = 'inline-block';
  if (btnExportCsv) btnExportCsv.style.display = 'none';
  if (btnImportCsv) btnImportCsv.style.display = 'none';
}

// Refresh active link panel without requiring save
async function refreshActiveLink() {
  if (!currentLink) {
    showToast('No active link to refresh', 'error');
    return;
  }

  showToast('Refreshing...', 'info');

  try {
    // Reload the link from the backend to get latest state
    const response = await fetch(window.SCIDK_BASE + `/api/links/${currentLink.id}`);
    const data = await response.json();

    if (data.status === 'success') {
      currentLink = data.link;
      await renderActiveLinkPanel(currentLink);
      showToast('Refreshed successfully', 'success');
    } else {
      showToast(`Failed to refresh: ${data.error}`, 'error');
    }
  } catch (err) {
    console.error('Failed to refresh active link:', err);
    showToast('Failed to refresh link', 'error');
  }
}

// ===== Active Link Sync Status Functions =====

async function showSyncStatusForActiveImportLink(linkId, link) {
  const syncContainer = document.getElementById('active-link-sync-container');
  if (!syncContainer) return;

  // Show loading state
  syncContainer.innerHTML = `
    <div style="padding: 1rem;">
      <div style="font-size: 0.9em; color: #666;">Loading sync status...</div>
    </div>
  `;

  try {
    const response = await fetch(window.SCIDK_BASE + `/api/links/${linkId}/sync-status`);
    const data = await response.json();

    console.log(`[showSyncStatusForActiveImportLink] Link ${linkId} sync status:`, data);

    if (!response.ok || data.status === 'error') {
      throw new Error(data.error || 'Failed to fetch sync status');
    }

    if (!data.sync_supported) {
      // Non-import link (algorithmic/script) - skip Sync Status, but show index
      syncContainer.innerHTML = `
        <div style="padding: 1.5rem; background: #f5f5f5; border-radius: 6px; margin-bottom: 1.5rem;">
          <h5 style="margin: 0 0 0.75rem 0; color: #333;">Algorithmic Link</h5>
          <div style="font-size: 0.9em; color: #666; margin-bottom: 1rem;">
            <div>Last run: ${formatLastRun(currentLink.updated_at)}</div>
          </div>
          <button class="btn btn-sm btn-primary" onclick="executeLink()">Re-run</button>
          <button class="btn btn-sm btn-outline-secondary" style="margin-left: 0.5rem;" onclick="loadLinkDefinition('${linkId}')">View Definition</button>
        </div>
        <div id="active-link-index-container"></div>
      `;

      // Show relationship index below algorithmic link info
      await showRelationshipIndex(linkId, {
        containerId: 'active-link-index-container',
        source_label: link.source_label,
        rel_type: link.relationship_type,
        target_label: link.target_label,
        source_database: null
      });
      return;
    }

    // Import link - show sync status
    const lastSyncedAt = data.last_synced_at;
    const primaryCount = data.primary_count || 0;
    const currentSourceCount = data.current_source_count || 0;
    const newSinceSync = data.new_since_sync || 0;
    const sourceDatabase = data.source_database || 'Unknown';

    // Show "unknown" if there's data in primary but no sync timestamp
    let lastSyncedStr;
    if (lastSyncedAt) {
      lastSyncedStr = formatDateTime(lastSyncedAt);
    } else if (primaryCount > 0) {
      lastSyncedStr = 'unknown (relationships exist in primary)';
    } else {
      lastSyncedStr = 'Not yet synced';
    }

    const syncStatusColor = newSinceSync === 0 ? '#4caf50' : '#ff9800';
    const syncStatusIcon = newSinceSync === 0 ? '✓' : '⚠';
    const syncStatusText = newSinceSync === 0 ? 'Up to date' : `${newSinceSync.toLocaleString()} new since last sync`;

    syncContainer.innerHTML = `
      <div style="padding: 1.5rem; background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%); border-radius: 6px;">
        <h5 style="margin: 0 0 1rem 0; color: #333; display: flex; align-items: center; gap: 0.5rem;">
          <span style="color: ${syncStatusColor};">${syncStatusIcon}</span>
          Sync Status
        </h5>

        <div style="background: white; padding: 1rem; border-radius: 4px; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
          <div style="font-size: 0.9em; color: #666; margin-bottom: 0.75rem;">
            <div style="margin-bottom: 0.5rem;"><strong>Last synced:</strong> ${lastSyncedStr}</div>
            <div style="margin-bottom: 0.5rem;"><strong>${primaryCount.toLocaleString()} relationships</strong> in primary</div>
          </div>

          <div style="border-top: 1px solid #e0e0e0; padding-top: 0.75rem; margin-top: 0.75rem;">
            <div style="font-size: 0.85em; color: #888; margin-bottom: 0.25rem;">Source: ${escapeHtml(sourceDatabase)}</div>
            <div style="font-size: 0.9em; color: #444;">
              <strong>Current count:</strong> ${currentSourceCount.toLocaleString()}
              ${newSinceSync > 0 ? `<span style="color: ${syncStatusColor}; font-weight: 500;">(${newSinceSync.toLocaleString()} new)</span>` : `<span style="color: ${syncStatusColor};">✓</span>`}
            </div>
          </div>
        </div>

        <div style="display: flex; gap: 0.5rem;">
          <button class="btn btn-sm btn-primary" onclick="executeLink()" ${newSinceSync === 0 ? 'disabled' : ''}>
            Sync Now ${newSinceSync > 0 ? `(+${newSinceSync.toLocaleString()})` : ''}
          </button>
          <button class="btn btn-sm btn-outline-secondary" onclick="showSyncDetails('${linkId}')">
            View Details
          </button>
        </div>
      </div>

      <!-- Enrich Relationships Section -->
      <div id="enrich-section" style="padding: 1.5rem; background: #fff9e6; border: 1px solid #ffd54f; border-radius: 6px; margin-top: 1.5rem;">
        <h5 style="margin: 0 0 0.75rem 0; color: #333; font-size: 1.1rem; font-weight: 500;">Enrich Relationships</h5>
        <div id="enrich-properties-loading" style="font-size: 0.9em; color: #666;">Loading properties...</div>
      </div>

      <div id="active-link-index-container"></div>
    `;

    // Load and render property selection UI
    await renderEnrichPropertiesUI(linkId, data.source_database, link);

    // Show relationship index below sync status - always query PRIMARY for Active links
    await showRelationshipIndex(linkId, {
      containerId: 'active-link-index-container',
      source_label: data.source_label || link.source_label,
      rel_type: data.rel_type || link.relationship_type,
      target_label: data.target_label || link.target_label,
      source_database: null  // Force PRIMARY - Active links show what's in primary graph
    });
  } catch (err) {
    console.error('Failed to fetch sync status:', err);
    syncContainer.innerHTML = `
      <div style="padding: 1rem; background: #ffebee; border-radius: 4px; margin-bottom: 1.5rem;">
        <div style="color: #c62828; font-size: 0.9em;">Failed to load sync status: ${err.message}</div>
      </div>
      <div id="active-link-index-container"></div>
    `;

    // Still show relationship index even if sync status fails
    try {
      await showRelationshipIndex(linkId, {
        containerId: 'active-link-index-container',
        source_label: link.source_label,
        rel_type: link.relationship_type,
        target_label: link.target_label,
        source_database: null
      });
    } catch (indexErr) {
      console.error('Failed to show relationship index:', indexErr);
    }
  }
}

// Show sync details (can be expanded later)
function showSyncDetails(linkId) {
  // For now, just show the link definition details
  showToast('Sync details view - coming soon', 'info');
}

async function executeDiscoveredImport() {
  const config = discoveredImportConfig;

  if (!config.source.uid_property || !config.target.uid_property) {
    showToast('Please configure source and target UID properties first', 'error');
    return;
  }

  // Confirmation dialog
  const confirmed = confirm(
    `Import ${config.rel.count || '?'} relationships from ${config.database}?\n\n` +
    `This will create stub nodes with only UID properties:\n` +
    `- Source: ${config.source.label}.${config.source.uid_property}\n` +
    `- Target: ${config.target.label}.${config.target.uid_property}\n\n` +
    `Relationships will ${config.relationship.import_properties ? 'include' : 'exclude'} properties.`
  );

  if (!confirmed) return;

  const executeBtn = document.getElementById('btn-execute-discovered-import');
  if (executeBtn) {
    executeBtn.disabled = true;
    executeBtn.textContent = 'Importing...';
  }

  showToast('Starting import...', 'info');

  try {
    const response = await fetch(window.SCIDK_BASE + '/api/links/discovered/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_label: config.source.label,
        target_label: config.target.label,
        rel_type: config.relationship.type,
        source_database: config.database,
        source_uid_property: config.source.uid_property,
        target_uid_property: config.target.uid_property,
        import_rel_properties: config.relationship.import_properties,
        batch_size: 5000  // Optimal for Neo4j UNWIND performance
      })
    });

    const result = await response.json();

    if (!response.ok || result.status === 'error') {
      throw new Error(result.error || 'Import failed');
    }

    // Show progress UI and start polling
    const taskId = result.task_id;
    console.log('[executeDiscoveredImport] Got task_id:', taskId);

    const previewContainer = document.getElementById('preview-container');
    console.log('[executeDiscoveredImport] preview-container element:', previewContainer);

    if (previewContainer) {
      previewContainer.innerHTML = `
        <div style="padding: 1.5rem;">
          <div id="task-progress-message" style="margin-bottom: 1rem; font-weight: 500;">Initializing import...</div>
          <div style="background: #e0e0e0; border-radius: 4px; height: 24px; overflow: hidden; margin-bottom: 0.5rem;">
            <div id="task-progress-fill" style="background: #4caf50; height: 100%; width: 0%; transition: width 0.3s ease;"></div>
          </div>
          <div id="task-progress-stats" style="font-size: 0.85em; color: #666; margin-bottom: 0.75rem;"></div>
          <button id="btn-cancel-import" class="btn btn-sm btn-outline-danger" onclick="cancelDiscoveredImport('${taskId}')">Cancel Import</button>
        </div>
      `;
    } else {
      console.error('[executeDiscoveredImport] preview-container not found!');
    }

    showToast('Import started - tracking progress...', 'info');
    console.log('[executeDiscoveredImport] Starting polling for task:', taskId);
    pollDiscoveredImportStatus(taskId, config);
  } catch (err) {
    console.error('Import failed to start:', err);
    showToast(`Import failed: ${err.message}`, 'error');

    if (executeBtn) {
      executeBtn.disabled = false;
      executeBtn.textContent = 'Import to Primary Graph';
    }
  }
}

// Check if there's a running job for this link and resume progress tracking
async function checkAndResumeRunningJob(linkId) {
  try {
    const response = await fetch(window.SCIDK_BASE + `/api/links/${linkId}/job-status`);
    const data = await response.json();

    if (data.running && data.task_id) {
      console.log('[checkAndResumeRunningJob] Found running job:', data.task_id);

      // Show progress UI
      const previewContainer = document.getElementById('preview-container');
      if (previewContainer) {
        previewContainer.innerHTML = `
          <div style="padding: 1.5rem;">
            <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 1rem; border-radius: 4px; margin-bottom: 1rem;">
              <strong>Import in progress</strong> — resuming progress tracking...
            </div>
            <div id="task-progress-message" style="margin-bottom: 1rem; font-weight: 500;">${data.progress.status_message || 'Processing...'}</div>
            <div style="background: #e0e0e0; border-radius: 4px; height: 24px; overflow: hidden; margin-bottom: 0.5rem;">
              <div id="task-progress-fill" style="background: #4caf50; height: 100%; width: ${Math.round(data.progress.progress * 100)}%; transition: width 0.3s ease;"></div>
            </div>
            <div id="task-progress-stats" style="font-size: 0.85em; color: #666; margin-bottom: 0.75rem;">
              ${data.progress.processed ? `${data.progress.processed.toLocaleString()} / ${data.progress.total.toLocaleString()} relationships` : ''}
            </div>
            <button id="btn-cancel-import" class="btn btn-sm btn-outline-danger" onclick="cancelDiscoveredImport('${data.task_id}')">Cancel Import</button>
          </div>
        `;
      }

      // Get config from link's match_config for the completion handler
      const config = {
        source: { label: currentLink.source_label },
        target: { label: currentLink.target_label }
      };

      // Start polling
      showToast('Resuming import progress tracking...', 'info');
      pollDiscoveredImportStatus(data.task_id, config);
    }
  } catch (err) {
    console.error('[checkAndResumeRunningJob] Error:', err);
    // Silent fail - not critical
  }
}

// Global variable to track active polling interval
let activePollingInterval = null;

// ===== Relationship Enrichment Functions =====

// Global to store selected properties for enrichment
let enrichPropertiesSelection = {
  linkId: null,
  properties: [],
  selectedProps: new Set()
};

async function fetchRelationshipProperties(sourceDatabase, sourceLabel, relType, targetLabel) {
  console.log('[fetchRelationshipProperties] Fetching properties for:', {sourceDatabase, sourceLabel, relType, targetLabel});

  try {
    const response = await fetch(window.SCIDK_BASE + '/api/neo4j/relationship-properties', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        database: sourceDatabase,
        source_label: sourceLabel,
        rel_type: relType,
        target_label: targetLabel
      })
    });

    const data = await response.json();

    if (data.status === 'success' && data.properties) {
      return data.properties; // Array of {name, type}
    } else {
      console.error('[fetchRelationshipProperties] Failed:', data.error);
      return [];
    }
  } catch (err) {
    console.error('[fetchRelationshipProperties] Error:', err);
    return [];
  }
}

async function renderEnrichPropertiesUI(linkId, sourceDatabase, link) {
  const enrichSection = document.getElementById('enrich-properties-loading');
  if (!enrichSection) return;

  // Fetch relationship properties from source database
  const properties = await fetchRelationshipProperties(
    sourceDatabase,
    link.source_label,
    link.relationship_type,
    link.target_label
  );

  if (properties.length === 0) {
    enrichSection.innerHTML = `<div style="font-size: 0.9em; color: #999;">No properties found on relationships in source database.</div>`;
    return;
  }

  // Initialize selection with all properties selected
  enrichPropertiesSelection.linkId = linkId;
  enrichPropertiesSelection.properties = properties;
  enrichPropertiesSelection.selectedProps = new Set(properties.map(p => p.name));

  // Render property list
  const propertyRows = properties.map(prop => `
    <div style="display: flex; align-items: center; padding: 0.35rem 0; font-size: 0.9em;">
      <input type="checkbox"
             id="enrich-prop-${escapeHtml(prop.name)}"
             checked
             onchange="toggleEnrichProperty('${escapeHtml(prop.name)}')"
             style="margin-right: 0.5rem;" />
      <label for="enrich-prop-${escapeHtml(prop.name)}" style="flex: 1; cursor: pointer; margin: 0;">
        ${escapeHtml(prop.name)}
      </label>
      <span style="color: #888; font-size: 0.85em;">${escapeHtml(prop.type)}</span>
    </div>
  `).join('');

  const selectedCount = enrichPropertiesSelection.selectedProps.size;
  const totalCount = properties.length;

  enrichSection.innerHTML = `
    <div id="enrich-property-list" style="margin-bottom: 0.75rem; max-height: 200px; overflow-y: auto;">
      ${propertyRows}
    </div>
    <div style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.85em; color: #666; margin-bottom: 0.75rem;">
      <span id="enrich-selection-count">${selectedCount} of ${totalCount} selected</span>
      <button class="btn btn-sm btn-link" style="padding: 0; font-size: 0.85em;" onclick="selectAllEnrichProperties()">Select All</button>
      <button class="btn btn-sm btn-link" style="padding: 0; font-size: 0.85em;" onclick="clearAllEnrichProperties()">Clear</button>
    </div>
    <button id="btn-enrich-selected" class="btn btn-sm btn-warning" onclick="enrichSelectedRelationships('${linkId}')">
      Enrich Selected
    </button>
  `;
}

function toggleEnrichProperty(propName) {
  if (enrichPropertiesSelection.selectedProps.has(propName)) {
    enrichPropertiesSelection.selectedProps.delete(propName);
  } else {
    enrichPropertiesSelection.selectedProps.add(propName);
  }
  updateEnrichSelectionCount();
}

function selectAllEnrichProperties() {
  enrichPropertiesSelection.selectedProps = new Set(enrichPropertiesSelection.properties.map(p => p.name));
  enrichPropertiesSelection.properties.forEach(prop => {
    const checkbox = document.getElementById(`enrich-prop-${prop.name}`);
    if (checkbox) checkbox.checked = true;
  });
  updateEnrichSelectionCount();
}

function clearAllEnrichProperties() {
  enrichPropertiesSelection.selectedProps.clear();
  enrichPropertiesSelection.properties.forEach(prop => {
    const checkbox = document.getElementById(`enrich-prop-${prop.name}`);
    if (checkbox) checkbox.checked = false;
  });
  updateEnrichSelectionCount();
}

function updateEnrichSelectionCount() {
  const countElem = document.getElementById('enrich-selection-count');
  if (countElem) {
    const selectedCount = enrichPropertiesSelection.selectedProps.size;
    const totalCount = enrichPropertiesSelection.properties.length;
    countElem.textContent = `${selectedCount} of ${totalCount} selected`;
  }
}

async function enrichSelectedRelationships(linkId) {
  console.log('[enrichSelectedRelationships] Starting enrichment for link:', linkId);

  const selectedProps = Array.from(enrichPropertiesSelection.selectedProps);

  if (selectedProps.length === 0) {
    showToast('Please select at least one property to enrich', 'error');
    return;
  }

  const confirmed = confirm(
    `Enrich ${selectedProps.length} selected propert${selectedProps.length === 1 ? 'y' : 'ies'} from source database?\n\n` +
    'This will update properties on existing relationships in primary ' +
    'without creating new nodes or relationships.'
  );

  if (!confirmed) return;

  const enrichBtn = document.getElementById('btn-enrich-selected');
  if (enrichBtn) {
    enrichBtn.disabled = true;
    enrichBtn.textContent = 'Enriching...';
  }

  showToast('Starting enrichment...', 'info');

  try {
    // Pass empty properties array if all are selected (use SET r +=)
    const allSelected = selectedProps.length === enrichPropertiesSelection.properties.length;
    const propertiesToSend = allSelected ? [] : selectedProps;

    const response = await fetch(window.SCIDK_BASE + `/api/links/${linkId}/enrich`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        batch_size: 1000,
        properties: propertiesToSend
      })
    });

    const result = await response.json();

    if (!response.ok || result.status === 'error') {
      throw new Error(result.error || 'Enrichment failed');
    }

    const taskId = result.task_id;
    console.log('[enrichSelectedRelationships] Got task_id:', taskId);

    // Show progress UI
    const enrichSection = document.getElementById('enrich-section');
    if (enrichSection) {
      enrichSection.innerHTML = `
        <h5 style="margin: 0 0 0.75rem 0; color: #333; font-size: 1.1rem; font-weight: 500;">Enriching Relationships</h5>
        <div id="enrich-progress-message" style="margin-bottom: 1rem; font-weight: 500;">Initializing enrichment...</div>
        <div style="background: #e0e0e0; border-radius: 4px; height: 24px; overflow: hidden; margin-bottom: 0.5rem;">
          <div id="enrich-progress-fill" style="background: #ff9800; height: 100%; width: 0%; transition: width 0.3s ease;"></div>
        </div>
        <div id="enrich-progress-stats" style="font-size: 0.85em; color: #666; margin-bottom: 0.75rem;"></div>
        <button id="btn-cancel-enrich" class="btn btn-sm btn-outline-danger" onclick="cancelEnrichment('${taskId}')">Cancel</button>
      `;
    }

    showToast('Enrichment started - tracking progress...', 'info');
    pollEnrichmentStatus(taskId, linkId);
  } catch (err) {
    console.error('Enrichment failed to start:', err);
    showToast(`Enrichment failed: ${err.message}`, 'error');

    if (enrichBtn) {
      enrichBtn.disabled = false;
      enrichBtn.textContent = 'Enrich Selected';
    }
  }
}

function pollEnrichmentStatus(taskId, linkId) {
  console.log('[pollEnrichmentStatus] Starting polling for task:', taskId);

  // Clear any existing polling interval
  if (activePollingInterval) {
    clearInterval(activePollingInterval);
  }

  activePollingInterval = setInterval(async () => {
    try {
      const response = await fetch(window.SCIDK_BASE + `/api/tasks/${taskId}`);
      const task = await response.json();

      console.log('[pollEnrichmentStatus] Task status:', task);

      // Update progress UI
      const progressFill = document.getElementById('enrich-progress-fill');
      const progressMessage = document.getElementById('enrich-progress-message');
      const progressStats = document.getElementById('enrich-progress-stats');

      if (progressFill && task.progress !== undefined) {
        const progressPercent = Math.round(task.progress * 100);
        progressFill.style.width = `${progressPercent}%`;
      }

      if (progressMessage && task.status_message) {
        progressMessage.textContent = task.status_message;
      }

      if (progressStats && task.processed !== undefined && task.total !== undefined) {
        progressStats.textContent = `${task.processed.toLocaleString()} / ${task.total.toLocaleString()} relationships processed`;
      }

      // Check if completed
      if (task.status === 'completed') {
        clearInterval(activePollingInterval);
        activePollingInterval = null;

        showToast(`Enrichment complete! ${task.relationships_enriched || 0} relationships enriched.`, 'success');

        // Reload the Active link panel to show updated status
        setTimeout(() => {
          if (currentLink && currentLink.id === linkId) {
            showSyncStatusForActiveImportLink(linkId, currentLink);
          }
        }, 1000);
      } else if (task.status === 'error' || task.status === 'failed') {
        clearInterval(activePollingInterval);
        activePollingInterval = null;

        showToast(`Enrichment failed: ${task.error || 'Unknown error'}`, 'error');

        // Show error in UI
        if (progressMessage) {
          progressMessage.innerHTML = `<span style="color: #f44336;">✗ Enrichment failed: ${task.error || 'Unknown error'}</span>`;
        }
      }
    } catch (err) {
      console.error('[pollEnrichmentStatus] Polling error:', err);
      clearInterval(activePollingInterval);
      activePollingInterval = null;
      showToast('Failed to poll enrichment status', 'error');
    }
  }, 2000);  // Poll every 2 seconds
}

async function cancelEnrichment(taskId) {
  if (!confirm('Are you sure you want to cancel enrichment?')) {
    return;
  }

  try {
    const response = await fetch(window.SCIDK_BASE + `/api/tasks/${taskId}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });

    if (response.ok) {
      showToast('Enrichment cancelled', 'info');

      if (activePollingInterval) {
        clearInterval(activePollingInterval);
        activePollingInterval = null;
      }

      // Reload the panel
      if (currentLink) {
        showSyncStatusForActiveImportLink(currentLink.id, currentLink);
      }
    }
  } catch (err) {
    console.error('Failed to cancel enrichment:', err);
    showToast('Failed to cancel enrichment', 'error');
  }
}

// Poll discovered import task status
