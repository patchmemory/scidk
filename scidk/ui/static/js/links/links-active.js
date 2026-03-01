// ===== Active Link Sync Status Functions =====

async function showSyncStatusForActiveImportLink(linkId, link) {
  const previewContainer = document.getElementById('preview-container');
  if (!previewContainer) return;

  // Show loading state
  previewContainer.innerHTML = `
    <div style="padding: 1rem;">
      <div style="font-size: 0.9em; color: #666;">Loading sync status...</div>
    </div>
  `;

  try {
    const response = await fetch(`/api/links/${linkId}/sync-status`);
    const data = await response.json();

    console.log(`[showSyncStatusForActiveImportLink] Link ${linkId} sync status:`, data);

    if (!response.ok || data.status === 'error') {
      throw new Error(data.error || 'Failed to fetch sync status');
    }

    if (!data.sync_supported) {
      // Non-import link (algorithmic/script) - skip Sync Status, but show index
      previewContainer.innerHTML = `
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

    previewContainer.innerHTML = `
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
      <div id="active-link-index-container"></div>
    `;

    // Show relationship index below sync status
    await showRelationshipIndex(linkId, {
      containerId: 'active-link-index-container',
      source_label: data.source_label || link.source_label,
      rel_type: data.rel_type || link.relationship_type,
      target_label: data.target_label || link.target_label,
      source_database: data.source_database || null
    });
  } catch (err) {
    console.error('Failed to fetch sync status:', err);
    previewContainer.innerHTML = `
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
    const response = await fetch('/api/links/discovered/import', {
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
let activePollingInterval = null;

// Poll discovered import task status
