// ===== Discovered Import Functions =====

// Load instances table for discovered relationship import
async function loadDiscoveredInstances() {
  const config = discoveredImportConfig;
  const rel = config.rel;
  const database = config.database;

  // Read current values from config (already updated by save functions)
  const sourceUid = config.source.uid_property;
  const targetUid = config.target.uid_property;

  console.log('[Links] loadDiscoveredInstances - validation check:', {
    sourceUid,
    targetUid,
    source_label: config.source.label,
    target_label: config.target.label
  });

  if (!sourceUid && !targetUid) {
    showToast('Please configure Source and Target UID properties', 'error');
    return;
  } else if (!sourceUid) {
    showToast('Please configure Source UID property', 'error');
    return;
  } else if (!targetUid) {
    showToast('Please configure Target UID property', 'error');
    return;
  }

  const previewContainer = document.getElementById('preview-container');
  if (previewContainer) {
    previewContainer.innerHTML = '<div style="text-align: center; padding: 2rem; color: #999;">Loading instances...</div>';
  }

  // Build optimized query that returns only scalar values needed for display
  // Use coalesce to handle missing properties and fall back to toString(id(node))
  const query = `
    MATCH (a:${config.source.label})-[r:${config.relationship.type}]->(b:${config.target.label})
    RETURN
      coalesce(a.${sourceUid}, toString(id(a))) as source_uid,
      coalesce(a.name, a.title, a.${sourceUid}, toString(id(a))) as source_display,
      type(r) as rel_type,
      size(keys(r)) as rel_prop_count,
      coalesce(b.${targetUid}, toString(id(b))) as target_uid,
      coalesce(b.name, b.title, b.${targetUid}, toString(id(b))) as target_display
    LIMIT 10
  `;

  try {
    const response = await fetch(`/api/neo4j/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ database: database, query: query })
    });

    const result = await response.json();

    if (!response.ok || result.status === 'error') {
      throw new Error(result.error || 'Query failed');
    }

    // Display the instances in a table with import buttons
    const records = result.records || [];

    if (records.length === 0) {
      previewContainer.innerHTML = '<div class="empty-state small">No instances found</div>';
      return;
    }

    // Show action buttons for Pending/Available links
    let actionButtonsHtml = `
      <div style="margin-top: 1rem; margin-bottom: 1rem;">
        <div style="display: flex; gap: 0.5rem;">
          <button class="btn btn-sm btn-outline-info" onclick="previewDiscoveredImport()">Preview Import</button>
          <button class="btn btn-sm btn-success" onclick="executeDiscoveredImport()" id="btn-execute-discovered-import">Import to Primary Graph</button>
        </div>
      </div>
    `;

    previewContainer.innerHTML = actionButtonsHtml + '<div id="pending-available-index-container"></div>';

    // Show full paginated relationship index instead of 10-row sample
    await showRelationshipIndex(currentLink?.id || 'discovered', {
      containerId: 'pending-available-index-container',
      source_label: config.source.label,
      rel_type: config.relationship.type,
      target_label: config.target.label,
      source_database: database
    });
  } catch (err) {
    console.error('Failed to fetch instances:', err);
    if (previewContainer) {
      previewContainer.innerHTML = `<div class="empty-state small" style="color: #f44336;">Failed to load instances: ${escapeHtml(err.message)}</div>`;
    }
  }
}


// ===== Discovered Import Configuration =====
function getDiscoveredSourceImportModal() {
  const config = discoveredImportConfig.source;
  const properties = config.available_properties;

  return `
    <div class="form-group">
      <label class="form-label small">Source Label (read-only)</label>
      <input type="text" class="form-control form-control-sm" value="${escapeHtml(config.label)}" disabled>
    </div>

    <div class="form-group" style="margin-top: 1rem;">
      <label class="form-label small">Unique ID Property</label>
      <small class="small text-muted" style="display: block; margin-bottom: 0.5rem;">
        Select the property to use as unique identifier for merging nodes
      </small>
      <select id="modal-source-uid" class="form-control form-control-sm">
        ${properties.length === 0 ? '<option value="">No properties available</option>' : ''}
        ${properties.map(p => {
          const propName = typeof p === 'string' ? p : p.name;
          const isSelected = config.uid_property === propName;
          return `<option value="${propName}" ${isSelected ? 'selected' : ''}>${propName}</option>`;
        }).join('')}
      </select>
    </div>

    <div class="alert alert-info" style="margin-top: 1rem; font-size: 0.85em;">
      ℹ️ <strong>Stub Node Import:</strong> Only the unique ID property will be imported to create lightweight stub nodes.
      Full node enrichment with all properties happens later via the Labels page.
    </div>

    <div style="margin-top: 1.5rem; text-align: right; padding-top: 1rem; border-top: 1px solid #eee;">
      <button class="btn btn-sm btn-outline-secondary" onclick="closeModal(true)">Cancel</button>
      <button class="btn btn-sm btn-primary" onclick="saveDiscoveredSourceConfig()">Apply</button>
    </div>
  `;
}

function getDiscoveredTargetImportModal() {
  const config = discoveredImportConfig.target;
  const properties = config.available_properties;

  return `
    <div class="form-group">
      <label class="form-label small">Target Label (read-only)</label>
      <input type="text" class="form-control form-control-sm" value="${escapeHtml(config.label)}" disabled>
    </div>

    <div class="form-group" style="margin-top: 1rem;">
      <label class="form-label small">Unique ID Property</label>
      <small class="small text-muted" style="display: block; margin-bottom: 0.5rem;">
        Select the property to use as unique identifier for merging nodes
      </small>
      <select id="modal-target-uid" class="form-control form-control-sm">
        ${properties.length === 0 ? '<option value="">No properties available</option>' : ''}
        ${properties.map(p => {
          const propName = typeof p === 'string' ? p : p.name;
          const isSelected = config.uid_property === propName;
          return `<option value="${propName}" ${isSelected ? 'selected' : ''}>${propName}</option>`;
        }).join('')}
      </select>
    </div>

    <div class="alert alert-info" style="margin-top: 1rem; font-size: 0.85em;">
      ℹ️ <strong>Stub Node Import:</strong> Only the unique ID property will be imported to create lightweight stub nodes.
      Full node enrichment with all properties happens later via the Labels page.
    </div>

    <div style="margin-top: 1.5rem; text-align: right; padding-top: 1rem; border-top: 1px solid #eee;">
      <button class="btn btn-sm btn-outline-secondary" onclick="closeModal(true)">Cancel</button>
      <button class="btn btn-sm btn-primary" onclick="saveDiscoveredTargetConfig()">Apply</button>
    </div>
  `;
}

function getDiscoveredRelationshipImportModal() {
  const config = discoveredImportConfig.relationship;
  const properties = config.available_properties;

  return `
    <div class="form-group">
      <label class="form-label small">Relationship Type (read-only)</label>
      <input type="text" class="form-control form-control-sm" value="${escapeHtml(config.type)}" disabled>
    </div>

    <div class="form-group" style="margin-top: 1rem;">
      <label class="form-label small">Import Relationship Properties</label>
      <small class="small text-muted" style="display: block; margin-bottom: 0.5rem;">
        ${properties.length > 0 ? `Found ${properties.length} properties on this relationship type` : 'No properties found on this relationship type'}
      </small>
      <label style="display: flex; align-items: center; gap: 0.5rem; font-weight: normal;">
        <input type="checkbox" id="modal-rel-import-props" ${config.import_properties ? 'checked' : ''}>
        Import all relationship properties
      </label>
      ${properties.length > 0 ? `
        <div style="margin-top: 0.5rem; padding: 0.5rem; background: #f9f9f9; border-radius: 4px; font-size: 0.85em;">
          Properties: ${properties.map(p => `<code>${escapeHtml(p)}</code>`).join(', ')}
        </div>
      ` : ''}
    </div>

    <div style="margin-top: 1.5rem; text-align: right; padding-top: 1rem; border-top: 1px solid #eee;">
      <button class="btn btn-sm btn-outline-secondary" onclick="closeModal(true)">Cancel</button>
      <button class="btn btn-sm btn-primary" onclick="saveDiscoveredRelationshipConfig()">Apply</button>
    </div>
  `;
}

function saveDiscoveredSourceConfig() {
  const uidSelect = document.getElementById('modal-source-uid');
  if (uidSelect) {
    discoveredImportConfig.source.uid_property = uidSelect.value;
  }
  closeModal();
  updateDiscoveredImportDisplay();
  showToast(`Source UID: ${discoveredImportConfig.source.uid_property}`, 'success');
}

function saveDiscoveredTargetConfig() {
  const uidSelect = document.getElementById('modal-target-uid');
  if (uidSelect) {
    discoveredImportConfig.target.uid_property = uidSelect.value;
  }
  closeModal();
  updateDiscoveredImportDisplay();
  showToast(`Target UID: ${discoveredImportConfig.target.uid_property}`, 'success');
}

function saveDiscoveredRelationshipConfig() {
  const importPropsCheckbox = document.getElementById('modal-rel-import-props');
  if (importPropsCheckbox) {
    discoveredImportConfig.relationship.import_properties = importPropsCheckbox.checked;
  }
  closeModal();
  updateDiscoveredImportDisplay();
  showToast('Relationship configuration saved', 'success');
}

function updateDiscoveredImportDisplay() {
  // Update the visual triple display to show configuration status
  const mainTripleDisplay = document.getElementById('main-triple-display');
  if (!mainTripleDisplay || !discoveredImportConfig.rel) return;

  const sourceConfigured = discoveredImportConfig.source.uid_property ? 'configured' : '';
  const targetConfigured = discoveredImportConfig.target.uid_property ? 'configured' : '';
  const relConfigured = 'configured'; // Always configured since it's just a toggle

  mainTripleDisplay.innerHTML = `
    <div style="padding: 1.5rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; color: white;">
      <div style="display: flex; align-items: center; justify-content: center; gap: 1.5rem; font-size: 1rem; font-weight: 500;">
        <div class="visual-triple-node clickable ${sourceConfigured}" onclick="configureDiscoveredSource()"
             style="padding: 0.75rem 1.25rem; background: rgba(255,255,255,0.2); border-radius: 6px; backdrop-filter: blur(10px); min-width: 120px; text-align: center; cursor: pointer; transition: transform 0.2s;">
          <div style="font-size: 0.7rem; opacity: 0.9; margin-bottom: 0.25rem; text-transform: uppercase;">Source</div>
          <div style="font-size: 1.1rem; font-weight: 500;">${escapeHtml(discoveredImportConfig.source.label)}</div>
          ${discoveredImportConfig.source.uid_property ? `<div style="font-size: 0.75rem; opacity: 0.8; margin-top: 0.25rem;">UID: ${escapeHtml(discoveredImportConfig.source.uid_property)}</div>` : '<div style="font-size: 0.75rem; opacity: 0.8; margin-top: 0.25rem;">Click to configure</div>'}
        </div>
        <div style="font-size: 1.5rem;">→</div>
        <div class="visual-triple-node clickable ${relConfigured}" onclick="configureDiscoveredRelationship()"
             style="padding: 0.75rem 1.25rem; background: rgba(255,255,255,0.2); border-radius: 6px; backdrop-filter: blur(10px); min-width: 120px; text-align: center; cursor: pointer; transition: transform 0.2s;">
          <div style="font-size: 0.7rem; opacity: 0.9; margin-bottom: 0.25rem; text-transform: uppercase;">Relationship</div>
          <div style="font-size: 1.1rem; font-weight: 500;">${escapeHtml(discoveredImportConfig.relationship.type)}</div>
          <div style="font-size: 0.75rem; opacity: 0.8; margin-top: 0.25rem;">${discoveredImportConfig.relationship.import_properties ? 'With properties' : 'No properties'}</div>
        </div>
        <div style="font-size: 1.5rem;">→</div>
        <div class="visual-triple-node clickable ${targetConfigured}" onclick="configureDiscoveredTarget()"
             style="padding: 0.75rem 1.25rem; background: rgba(255,255,255,0.2); border-radius: 6px; backdrop-filter: blur(10px); min-width: 120px; text-align: center; cursor: pointer; transition: transform 0.2s;">
          <div style="font-size: 0.7rem; opacity: 0.9; margin-bottom: 0.25rem; text-transform: uppercase;">Target</div>
          <div style="font-size: 1.1rem; font-weight: 500;">${escapeHtml(discoveredImportConfig.target.label)}</div>
          ${discoveredImportConfig.target.uid_property ? `<div style="font-size: 0.75rem; opacity: 0.8; margin-top: 0.25rem;">UID: ${escapeHtml(discoveredImportConfig.target.uid_property)}</div>` : '<div style="font-size: 0.75rem; opacity: 0.8; margin-top: 0.25rem;">Click to configure</div>'}
        </div>
      </div>
    </div>
  `;
}

function configureDiscoveredSource() {
  openModal('Configure Source Node', getDiscoveredSourceImportModal());
}

function configureDiscoveredTarget() {
  openModal('Configure Target Node', getDiscoveredTargetImportModal());
}

function configureDiscoveredRelationship() {
  openModal('Configure Relationship', getDiscoveredRelationshipImportModal());
}

// Preview discovered import (dry run)
async function previewDiscoveredImport() {
  const config = discoveredImportConfig;

  if (!config.source.uid_property || !config.target.uid_property) {
    showToast('Please configure source and target UID properties first', 'error');
    return;
  }

  showToast('Generating preview...', 'info');

  try {
    const response = await fetch(window.SCIDK_BASE + '/api/links/discovered/import/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_label: config.source.label,
        target_label: config.target.label,
        rel_type: config.relationship.type,
        source_database: config.database,
        source_uid_property: config.source.uid_property,
        target_uid_property: config.target.uid_property,
        import_rel_properties: config.relationship.import_properties
      })
    });

    const result = await response.json();

    if (!response.ok || result.status === 'error') {
      throw new Error(result.error || 'Preview failed');
    }

    // Display preview results
    const previewContainer = document.getElementById('preview-container');
    const preview = result.preview || {};

    previewContainer.innerHTML = `
      <div style="background: #e3f2fd; border-left: 4px solid #2196f3; padding: 1rem; border-radius: 4px; margin-bottom: 1rem;">
        <h5 style="margin: 0 0 0.5rem 0;">Import Preview (Dry Run)</h5>
        <div style="font-size: 0.9em;">
          <div><strong>Total Relationships:</strong> ${preview.total_relationships || 0}</div>
          <div><strong>Source Nodes:</strong> ${preview.source_nodes_to_create || 0} new + ${preview.source_nodes_to_merge || 0} existing</div>
          <div><strong>Target Nodes:</strong> ${preview.target_nodes_to_create || 0} new + ${preview.target_nodes_to_merge || 0} existing</div>
          <div><strong>Relationships:</strong> ${preview.relationships_to_create || 0} to create</div>
          ${config.relationship.import_properties ? `<div><strong>Relationship Properties:</strong> ${preview.rel_property_count || 0} properties per relationship</div>` : ''}
        </div>
        <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid rgba(33,150,243,0.3);">
          <button class="btn btn-sm btn-success" onclick="executeDiscoveredImport()">✓ Proceed with Import</button>
          <button class="btn btn-sm btn-outline-secondary" onclick="openImportWizardForRelationship(discoveredImportConfig.rel)" style="margin-left: 0.5rem;">Cancel</button>
        </div>
      </div>
    `;

    showToast('Preview generated successfully', 'success');
  } catch (err) {
    console.error('Preview failed:', err);
    showToast(`Preview failed: ${err.message}`, 'error');
  }
}

// Execute discovered import
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
    const response = await fetch(`/api/links/${linkId}/job-status`);
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

// Poll discovered import task status
function pollDiscoveredImportStatus(taskId, config) {
  console.log('[pollDiscoveredImportStatus] Starting polling for task:', taskId);

  // Clear any existing polling interval to prevent multiple polls
  if (activePollingInterval) {
    console.log('[pollDiscoveredImportStatus] Clearing existing polling interval');
    clearInterval(activePollingInterval);
  }

  activePollingInterval = setInterval(() => {
    fetch(`/api/tasks/${taskId}`)
      .then(r => {
        if (r.status === 404) {
          clearInterval(activePollingInterval);
          activePollingInterval = null;
          console.log('[pollDiscoveredImportStatus] Task not found (404), stopping poll');
          document.getElementById('preview-container').innerHTML = `<div class="empty-state small" style="color: #f44336;">Task not found (may have been deleted)</div>`;
          return null;
        }
        return r.json();
      })
      .then(task => {
        if (!task) return; // 404 case
        console.log('[pollDiscoveredImportStatus] Task update:', task);

        // Update progress UI
        const progressMsg = document.getElementById('task-progress-message');
        const progressFill = document.getElementById('task-progress-fill');
        const progressStats = document.getElementById('task-progress-stats');

        console.log('[pollDiscoveredImportStatus] UI elements:', {
          progressMsg: !!progressMsg,
          progressFill: !!progressFill,
          progressStats: !!progressStats
        });

        if (progressMsg) {
          progressMsg.textContent = task.status_message || 'Processing...';
        }

        if (progressFill && task.progress !== undefined) {
          progressFill.style.width = `${Math.round(task.progress * 100)}%`;
        }

        if (progressStats && task.processed && task.total) {
          progressStats.textContent = `${task.processed.toLocaleString()} / ${task.total.toLocaleString()} relationships`;
        }

        // Check completion status
        if (task.status === 'completed') {
          clearInterval(activePollingInterval);
          activePollingInterval = null;
          const relCount = task.relationships_created || 0;
          const sourceCreated = task.source_nodes_created || 0;
          const targetCreated = task.target_nodes_created || 0;

          document.getElementById('preview-container').innerHTML = `
            <div style="background: #e8f5e9; border-left: 4px solid #4caf50; padding: 1rem; border-radius: 4px; margin-bottom: 1rem;">
              <h5 style="margin: 0 0 0.5rem 0;">✓ Import Complete!</h5>
              <div style="font-size: 0.9em;">
                <div><strong>Relationships:</strong> ${relCount.toLocaleString()} imported</div>
                <div><strong>Nodes:</strong> ${sourceCreated} ${config.source.label} + ${targetCreated} ${config.target.label} created</div>
              </div>
              <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid rgba(76,175,80,0.3); font-size: 0.85em; color: #4caf50;">
                ✓ Link Definition saved — find it in the Active tab to rerun this import later
              </div>
              <div style="margin-top: 0.5rem; font-size: 0.85em; color: #666;">
                Next: Visit <a href="/labels">Labels page</a> to enrich nodes with full properties
              </div>
            </div>
          `;
          showToast(`Import complete! ${relCount.toLocaleString()} relationships created`, 'success');

          // Refresh link definitions to show the new/updated definition
          loadLinkDefinitions();

          // If we're viewing an Active import link, refresh the sync status to show updated counts
          if (currentLink && currentLink.id && task.link_def_id === currentLink.id) {
            setTimeout(() => {
              showSyncStatusForActiveImportLink(currentLink.id, currentLink);
            }, 1000); // Brief delay to ensure database is updated
          }
        } else if (task.status === 'canceled' || task.status === 'cancelled') {
          clearInterval(activePollingInterval);
          activePollingInterval = null;
          document.getElementById('preview-container').innerHTML = `
            <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 1rem; border-radius: 4px; margin-bottom: 1rem;">
              <h5 style="margin: 0 0 0.5rem 0;">Import Cancelled</h5>
              <div style="font-size: 0.9em; color: #666; margin-bottom: 0.75rem;">
                The import was stopped before completion.
              </div>
              <button class="btn btn-sm btn-success" onclick="previewDiscoveredImport()">Load Preview</button>
              <button class="btn btn-sm btn-outline-secondary" onclick="executeDiscoveredImport()" style="margin-left: 0.5rem;">Proceed with Import</button>
            </div>
          `;
          showToast('Import cancelled', 'info');
        } else if (task.status === 'error' || task.status === 'failed') {
          clearInterval(activePollingInterval);
          activePollingInterval = null;
          document.getElementById('preview-container').innerHTML = `
            <div style="padding: 2rem; text-align: center;">
              <div style="font-size: 3rem; color: #f44336; margin-bottom: 1rem;">✗</div>
              <div style="font-weight: bold; font-size: 1.2rem; margin-bottom: 0.5rem;">Import Failed</div>
              <div style="color: #666; font-size: 0.9rem;">${task.error || 'Unknown error'}</div>
            </div>
          `;
          showToast(`Import failed: ${task.error || 'Unknown error'}`, 'error');
        }
      })
      .catch(err => {
        clearInterval(activePollingInterval);
        activePollingInterval = null;
        document.getElementById('preview-container').innerHTML = `<div class="empty-state small" style="color: #f44336;">Failed to poll import status</div>`;
      });
  }, 2000);  // Poll every 2 seconds
}

// Cancel discovered import
async function cancelDiscoveredImport(taskId) {
  if (!confirm('Are you sure you want to cancel this import?')) {
    return;
  }

  try {
    const response = await fetch(`/api/tasks/${taskId}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });

    if (!response.ok) {
      throw new Error('Failed to cancel import');
    }

    showToast('Cancelling import...', 'info');

    // Disable the cancel button
    const cancelBtn = document.getElementById('btn-cancel-import');
    if (cancelBtn) {
      cancelBtn.disabled = true;
      cancelBtn.textContent = 'Cancelling...';
    }
  } catch (err) {
    console.error('Failed to cancel import:', err);
    showToast(`Failed to cancel: ${err.message}`, 'error');
  }
}

// CSV Export/Import Functions for Human Validation
