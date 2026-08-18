// ===== Relationship Index Table Functions =====

async function showRelationshipIndex(linkId, config) {
  /**
   * Display paginated relationship index with download options.
   * config can include:
   * - containerId: where to render (default: 'preview-container')
   * - source_label, rel_type, target_label, source_database (for discovered relationships)
   */
  const containerId = config?.containerId || 'preview-container';
  const container = document.getElementById(containerId);
  if (!container) return;

  // Initialize pagination state
  if (!window.relationshipIndexState) {
    window.relationshipIndexState = {};
  }

  const state = window.relationshipIndexState[containerId] = {
    linkId: linkId,
    config: config,
    page: 1,
    pageSize: 50,
    total: 0,
    rows: []
  };

  await loadRelationshipIndexPage(containerId);
}

async function loadRelationshipIndexPage(containerId) {
  const container = document.getElementById(containerId);
  const state = window.relationshipIndexState?.[containerId];
  if (!container || !state) return;

  // Show loading
  const indexContainer = document.getElementById(`relationship-index-${containerId}`) || container;
  indexContainer.innerHTML = `
    <div style="padding: 1rem;">
      <div style="font-size: 0.9em; color: #666;">Loading relationships...</div>
    </div>
  `;

  try {
    // Build query URL
    let url = `/api/links/${state.linkId}/index?page=${state.page}&page_size=${state.pageSize}`;

    // For discovered relationships, add query params
    if (state.config?.source_label) {
      url += `&source_label=${encodeURIComponent(state.config.source_label)}`;
      url += `&rel_type=${encodeURIComponent(state.config.rel_type)}`;
      url += `&target_label=${encodeURIComponent(state.config.target_label)}`;
      if (state.config.source_database) {
        url += `&source_database=${encodeURIComponent(state.config.source_database)}`;
      }
    }

    const response = await fetch(url);
    const data = await response.json();

    if (!response.ok || data.status === 'error') {
      throw new Error(data.error || 'Failed to load relationships');
    }

    state.total = data.total;
    state.rows = data.rows;

    // Render index panel
    renderRelationshipIndex(containerId);

  } catch (err) {
    console.error('Failed to load relationship index:', err);
    indexContainer.innerHTML = `
      <div style="padding: 1rem; background: #ffebee; border-radius: 4px;">
        <div style="color: #c62828; font-size: 0.9em;">Failed to load relationships: ${err.message}</div>
      </div>
    `;
  }
}

function renderRelationshipIndex(containerId) {
  const container = document.getElementById(containerId);
  const state = window.relationshipIndexState?.[containerId];
  if (!container || !state) return;

  const startIdx = (state.page - 1) * state.pageSize + 1;
  const endIdx = Math.min(state.page * state.pageSize, state.total);
  const hasPrev = state.page > 1;
  const hasNext = endIdx < state.total;

  // Show warning for large downloads
  const largeDatasetWarning = state.total > 10000 ? `
    <div style="padding: 0.75rem; background: #fff3cd; border-left: 3px solid #ffc107; border-radius: 4px; margin-bottom: 1rem; font-size: 0.85em;">
      ⚠ Large dataset (${state.total.toLocaleString()} rows) — downloads may take a moment
    </div>
  ` : '';

  // Extract up to 3 relationship properties from first row
  let relPropColumns = [];
  if (state.rows.length > 0 && state.rows[0].rel_props) {
    relPropColumns = Object.keys(state.rows[0].rel_props).slice(0, 3);
  }

  const html = `
    <div id="relationship-index-${containerId}" style="margin-top: 1.5rem; padding: 1rem; background: #f8f8f8; border-radius: 4px;">
      <h5 class="small" style="font-weight: bold; margin-bottom: 1rem;">View Relationships</h5>

      ${largeDatasetWarning}

      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;">
        <div style="font-size: 0.85em; color: #666;">
          Showing ${startIdx.toLocaleString()}-${endIdx.toLocaleString()} of ${state.total.toLocaleString()}
        </div>

        <div style="display: flex; gap: 0.5rem; align-items: center;">
          <button
            class="btn btn-sm btn-outline-secondary"
            onclick="prevRelationshipIndexPage('${containerId}')"
            ${!hasPrev ? 'disabled' : ''}>
            ← Prev
          </button>
          <span style="font-size: 0.85em; color: #666;">Page ${state.page}</span>
          <button
            class="btn btn-sm btn-outline-secondary"
            onclick="nextRelationshipIndexPage('${containerId}')"
            ${!hasNext ? 'disabled' : ''}>
            Next →
          </button>
        </div>

        <div style="display: flex; gap: 0.5rem;">
          <button
            class="btn btn-sm btn-outline-primary"
            onclick="downloadRelationshipIndex('${containerId}', 'csv')">
            Download CSV
          </button>
          <button
            class="btn btn-sm btn-outline-info"
            onclick="downloadRelationshipIndex('${containerId}', 'json')">
            Download JSON
          </button>
        </div>
      </div>

      <div style="overflow-x: auto; background: white; border-radius: 4px;">
        <table style="width: 100%; font-size: 0.85em; border-collapse: collapse;">
          <thead>
            <tr style="background: #f0f0f0; border-bottom: 2px solid #ddd;">
              <th style="padding: 0.5rem; text-align: left; font-weight: 600;">Source Node</th>
              <th style="padding: 0.5rem; text-align: left; font-weight: 600;">Relationship</th>
              <th style="padding: 0.5rem; text-align: left; font-weight: 600;">Target Node</th>
              ${relPropColumns.map(prop => `<th style="padding: 0.5rem; text-align: left; font-weight: 600;">${escapeHtml(prop)}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            ${state.rows.map(row => `
              <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 0.5rem; font-family: monospace; font-size: 0.85em; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(row.source_uid || '')}">${escapeHtml(truncateString(row.source_uid, 30))}</td>
                <td style="padding: 0.5rem; color: #666; text-align: center;">${state.config?.rel_type || '→'}</td>
                <td style="padding: 0.5rem; font-family: monospace; font-size: 0.85em; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(row.target_uid || '')}">${escapeHtml(truncateString(row.target_uid, 30))}</td>
                ${relPropColumns.map(prop => {
                  const value = row.rel_props?.[prop];
                  const displayValue = value !== null && value !== undefined ? String(value) : '';
                  return `<td style="padding: 0.5rem; font-size: 0.85em; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(displayValue)}">${escapeHtml(truncateString(displayValue, 20))}</td>`;
                }).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;

  container.innerHTML = html;
}

function truncateString(str, maxLength) {
  if (!str) return '';
  const s = String(str);
  return s.length > maxLength ? s.substring(0, maxLength) + '...' : s;
}

function prevRelationshipIndexPage(containerId) {
  const state = window.relationshipIndexState?.[containerId];
  if (!state || state.page <= 1) return;
  state.page--;
  loadRelationshipIndexPage(containerId);
}

function nextRelationshipIndexPage(containerId) {
  const state = window.relationshipIndexState?.[containerId];
  if (!state) return;
  const maxPage = Math.ceil(state.total / state.pageSize);
  if (state.page >= maxPage) return;
  state.page++;
  loadRelationshipIndexPage(containerId);
}

async function downloadRelationshipIndex(containerId, format) {
  const state = window.relationshipIndexState?.[containerId];
  if (!state) return;

  // Show warning for large datasets
  if (state.total > 10000) {
    const confirmed = confirm(`This will download ${state.total.toLocaleString()} rows. This may take a moment. Continue?`);
    if (!confirmed) return;
  }

  showToast(`Preparing ${format.toUpperCase()} download...`, 'info');

  try {
    // Fetch all pages
    const allRows = [];
    const totalPages = Math.ceil(state.total / 1000); // Fetch in chunks of 1000

    for (let page = 1; page <= totalPages; page++) {
      let url = `/api/links/${state.linkId}/index?page=${page}&page_size=1000`;

      if (state.config?.source_label) {
        url += `&source_label=${encodeURIComponent(state.config.source_label)}`;
        url += `&rel_type=${encodeURIComponent(state.config.rel_type)}`;
        url += `&target_label=${encodeURIComponent(state.config.target_label)}`;
        if (state.config.source_database) {
          url += `&source_database=${encodeURIComponent(state.config.source_database)}`;
        }
      }

      const response = await fetch(url);
      const data = await response.json();

      if (!response.ok || data.status === 'error') {
        throw new Error(data.error || 'Failed to fetch data');
      }

      allRows.push(...data.rows);
    }

    if (format === 'csv') {
      downloadAsCSV(allRows, state);
    } else if (format === 'json') {
      downloadAsJSON(allRows, state);
    }

    showToast(`Downloaded ${allRows.length.toLocaleString()} relationships as ${format.toUpperCase()}`, 'success');

  } catch (err) {
    console.error('Download failed:', err);
    showToast(`Download failed: ${err.message}`, 'error');
  }
}

function downloadAsCSV(rows, state) {
  // Collect all unique property keys
  const allPropKeys = new Set();
  rows.forEach(row => {
    if (row.rel_props) {
      Object.keys(row.rel_props).forEach(key => allPropKeys.add(key));
    }
  });
  const propKeys = Array.from(allPropKeys).sort();

  // Build CSV
  const headers = ['source_uid', 'relationship_type', 'target_uid', ...propKeys];
  const csvRows = [headers.join(',')];

  rows.forEach(row => {
    const relType = state.config?.rel_type || '';
    const values = [
      csvEscape(row.source_uid || ''),
      csvEscape(relType),
      csvEscape(row.target_uid || ''),
      ...propKeys.map(key => csvEscape(row.rel_props?.[key] !== undefined ? String(row.rel_props[key]) : ''))
    ];
    csvRows.push(values.join(','));
  });

  const csvContent = csvRows.join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `relationships_${state.linkId}_${Date.now()}.csv`;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

function csvEscape(value) {
  if (value === null || value === undefined) return '';
  const str = String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function downloadAsJSON(rows, state) {
  const jsonContent = JSON.stringify(rows, null, 2);
  const blob = new Blob([jsonContent], { type: 'application/json;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `relationships_${state.linkId}_${Date.now()}.json`;
  document.body.appendChild(a);
  a.click();
  window.URL.revokeObjectURL(url);
  document.body.removeChild(a);
}

// Old modal handlers removed - now using unified wizard workflow
