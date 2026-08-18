// ===== Triple Builder Wizard Modal Functions =====
// Modal helper functions
function openModal(title, contentHtml) {
  // Save snapshot before opening modal (deep copy)
  tripleBuilderSnapshot = JSON.parse(JSON.stringify(tripleBuilder));

  document.getElementById('modal-container').innerHTML = `
    <h4 style="margin: 0 0 1rem 0;">${title}</h4>
    ${contentHtml}
  `;
  document.getElementById('modal-overlay').style.display = 'block';
}

function closeModal(revert = false) {
  if (revert && tripleBuilderSnapshot) {
    // Restore from snapshot
    Object.assign(tripleBuilder, JSON.parse(JSON.stringify(tripleBuilderSnapshot)));
  }
  tripleBuilderSnapshot = null;
  document.getElementById('modal-overlay').style.display = 'none';
  updateMainTripleDisplay();
}

// Update main visual triple display
function updateMainTripleDisplay() {
  const sourceNode = document.getElementById('source-node-btn');
  const relNode = document.getElementById('relationship-node-btn');
  const targetNode = document.getElementById('target-node-btn');

  if (!sourceNode || !relNode || !targetNode) return;

  // Update source
  if (tripleBuilder.source.label) {
    sourceNode.querySelector('.visual-triple-node-value').textContent = tripleBuilder.source.label;
    sourceNode.classList.add('configured');
  } else {
    sourceNode.querySelector('.visual-triple-node-value').textContent = 'Click to configure';
    sourceNode.classList.remove('configured');
  }

  // Update relationship
  if (tripleBuilder.relationship.type) {
    const displayText = tripleBuilder.relationship.match_strategy === 'script'
      ? `${tripleBuilder.relationship.type} (Script)`
      : tripleBuilder.relationship.type;
    relNode.querySelector('.visual-triple-node-value').textContent = displayText;
    relNode.classList.add('configured');
  } else {
    relNode.querySelector('.visual-triple-node-value').textContent = 'Click to configure';
    relNode.classList.remove('configured');
  }

  // Update target
  if (tripleBuilder.target.label) {
    targetNode.querySelector('.visual-triple-node-value').textContent = tripleBuilder.target.label;
    targetNode.classList.add('configured');
  } else {
    targetNode.querySelector('.visual-triple-node-value').textContent = 'Click to configure';
    targetNode.classList.remove('configured');
  }

  // Enable/disable buttons based on configuration
  const allConfigured = tripleBuilder.source.label &&
                        tripleBuilder.relationship.type &&
                        tripleBuilder.relationship.match_strategy &&
                        tripleBuilder.target.label;

  const btnExecute = document.getElementById('btn-execute');
  const btnSaveDef = document.getElementById('btn-save-def');
  const btnExportCsv = document.getElementById('btn-export-csv');
  const btnImportCsv = document.getElementById('btn-import-csv');

  if (btnExecute) btnExecute.disabled = !allConfigured;
  if (btnSaveDef) btnSaveDef.disabled = !allConfigured;

  // Show CSV buttons only for fuzzy/contains strategies that need human validation
  const needsValidation = ['fuzzy', 'contains'].includes(tripleBuilder.relationship.match_strategy);
  if (btnExportCsv) btnExportCsv.style.display = (needsValidation && tripleBuilder.link_id) ? 'inline-block' : 'none';
  if (btnImportCsv) btnImportCsv.style.display = (needsValidation && tripleBuilder.link_id) ? 'inline-block' : 'none';
}

// Source Modal Functions
function getSourceModalContent() {
  // Get available properties for selected label
  const selectedLabel = tripleBuilder.source.label;
  const labelObj = availableLabels.find(l => (typeof l === 'string' ? l : l.name) === selectedLabel);
  const properties = labelObj && labelObj.properties ? labelObj.properties : [];

  return `
    <div class="form-group">
      <label class="form-label small">Label</label>
      <select id="modal-source-label" class="form-control form-control-sm" onchange="updateSourceModalOnLabelChange()">
        <option value="">Select a label...</option>
        ${availableLabels.map(l => {
          const labelName = typeof l === 'string' ? l : l.name;
          return `<option value="${labelName}" ${tripleBuilder.source.label === labelName ? 'selected' : ''}>${labelName}</option>`;
        }).join('')}
      </select>
    </div>

    <div class="form-group">
      <label class="form-label small">Property Filters (optional)</label>
      <small class="small text-muted" style="display: block; margin-bottom: 0.5rem;">
        Filter which nodes participate in this relationship
        ${selectedLabel && properties.length > 0 ? ` — Available properties from <strong>${selectedLabel}</strong>` : ''}
      </small>
      <div id="modal-source-filters">
        ${tripleBuilder.source.filters.map((f, i) => {
          // Build property dropdown if label is selected and has properties
          const propertyInput = properties.length > 0 ? `
            <select class="form-control form-control-sm" data-filter-key="${i}" onchange="loadPropertyValuesForSource(${i}, this.value)" style="flex: 1;">
              <option value="">Select property...</option>
              ${properties.map(p => {
                const propName = typeof p === 'string' ? p : p.name;
                return `<option value="${propName}" ${f.key === propName ? 'selected' : ''}>${propName}</option>`;
              }).join('')}
            </select>
          ` : `
            <input type="text" class="form-control form-control-sm" placeholder="property" value="${f.key}" data-filter-key="${i}" style="flex: 1;">
          `;

          return `
            <div class="property-row" style="margin-bottom: 0.5rem; display: flex; gap: 0.25rem;">
              ${propertyInput}
              <input type="text" class="form-control form-control-sm" placeholder="value" value="${f.value}" data-filter-value="${i}" list="source-values-${i}" style="flex: 1;">
              <datalist id="source-values-${i}"></datalist>
              <button class="btn btn-sm btn-outline-danger" onclick="removeSourceFilter(${i})">×</button>
            </div>
          `;
        }).join('')}
      </div>
      <button class="btn btn-sm btn-outline-primary" onclick="addSourceFilter()" style="margin-top: 0.5rem;">+ Add Filter</button>
    </div>

    <div style="margin-top: 1.5rem; text-align: right; padding-top: 1rem; border-top: 1px solid #eee;">
      <button class="btn btn-sm btn-outline-secondary" onclick="closeModal(true)">Cancel</button>
      <button class="btn btn-sm btn-primary" onclick="saveSourceConfig()">Apply</button>
    </div>
  `;
}

function updateSourceModalOnLabelChange() {
  const labelSelect = document.getElementById('modal-source-label');
  if (labelSelect) {
    tripleBuilder.source.label = labelSelect.value;
    // Re-render modal to show properties for the new label
    openModal('Configure Source Node', getSourceModalContent());
  }
}

async function loadPropertyValuesForSource(filterIndex, propertyName) {
  if (!propertyName || !tripleBuilder.source.label) return;

  const datalist = document.getElementById(`source-values-${filterIndex}`);
  if (!datalist) return;

  try {
    const response = await fetch(window.SCIDK_BASE + `/api/labels/${tripleBuilder.source.label}/property-values/${propertyName}?limit=50`);
    const data = await response.json();

    if (data.status === 'success' && data.values) {
      datalist.innerHTML = data.values.map(v => `<option value="${v}">`).join('');
    }
  } catch (error) {
    console.warn('Failed to load property values:', error);
  }
}

function addSourceFilter() {
  tripleBuilder.source.filters.push({ key: '', value: '' });
  openModal('Configure Source Node', getSourceModalContent());
}

function removeSourceFilter(index) {
  tripleBuilder.source.filters.splice(index, 1);
  openModal('Configure Source Node', getSourceModalContent());
}

function saveSourceConfig() {
  const label = document.getElementById('modal-source-label').value;
  const filters = [];

  document.querySelectorAll('[data-filter-key]').forEach(el => {
    const index = el.dataset.filterKey;
    const key = el.value;
    const value = document.querySelector(`[data-filter-value="${index}"]`).value;
    if (key && value) {
      filters.push({ key, value });
    }
  });

  tripleBuilder.source.label = label;
  tripleBuilder.source.filters = filters;

  closeModal();
  showToast(`Source configured: ${label}`, 'success');
}

// Target Modal Functions
function getTargetModalContent() {
  // Get available properties for selected label
  const selectedLabel = tripleBuilder.target.label;
  const labelObj = availableLabels.find(l => (typeof l === 'string' ? l : l.name) === selectedLabel);
  const properties = labelObj && labelObj.properties ? labelObj.properties : [];

  return `
    <div class="form-group">
      <label class="form-label small">Label</label>
      <select id="modal-target-label" class="form-control form-control-sm" onchange="updateTargetModalOnLabelChange()">
        <option value="">Select a label...</option>
        ${availableLabels.map(l => {
          const labelName = typeof l === 'string' ? l : l.name;
          return `<option value="${labelName}" ${tripleBuilder.target.label === labelName ? 'selected' : ''}>${labelName}</option>`;
        }).join('')}
      </select>
    </div>

    <div class="form-group">
      <label class="form-label small">Property Filters (optional)</label>
      <small class="small text-muted" style="display: block; margin-bottom: 0.5rem;">
        Filter which nodes participate
        ${selectedLabel && properties.length > 0 ? ` — Available properties from <strong>${selectedLabel}</strong>` : ''}
      </small>
      <div id="modal-target-filters">
        ${tripleBuilder.target.filters.map((f, i) => {
          // Show dropdown if properties available, else text input
          const propertyInput = properties.length > 0 ? `
            <select class="form-control form-control-sm" data-filter-key="${i}" onchange="loadPropertyValuesForTarget(${i}, this.value)" style="flex: 1;">
              <option value="">Select property...</option>
              ${properties.map(p => {
                const propName = typeof p === 'string' ? p : p.name;
                return `<option value="${propName}" ${f.key === propName ? 'selected' : ''}>${propName}</option>`;
              }).join('')}
            </select>
          ` : `
            <input type="text" class="form-control form-control-sm" placeholder="property" value="${f.key}" data-filter-key="${i}" style="flex: 1;">
          `;

          return `
            <div class="property-row" style="margin-bottom: 0.5rem;">
              ${propertyInput}
              <input type="text" class="form-control form-control-sm" placeholder="value" value="${f.value}" data-filter-value="${i}" list="target-values-${i}" style="flex: 1;">
              <datalist id="target-values-${i}"></datalist>
              <button class="btn btn-sm btn-outline-danger" onclick="removeTargetFilter(${i})">×</button>
            </div>
          `;
        }).join('')}
      </div>
      <button class="btn btn-sm btn-outline-primary" onclick="addTargetFilter()" style="margin-top: 0.5rem;">+ Add Filter</button>
    </div>

    <div style="margin-top: 1.5rem; text-align: right; padding-top: 1rem; border-top: 1px solid #eee;">
      <button class="btn btn-sm btn-outline-secondary" onclick="closeModal(true)">Cancel</button>
      <button class="btn btn-sm btn-primary" onclick="saveTargetConfig()">Apply</button>
    </div>
  `;
}

function updateTargetModalOnLabelChange() {
  const labelSelect = document.getElementById('modal-target-label');
  if (labelSelect) {
    tripleBuilder.target.label = labelSelect.value;
    // Re-render modal to show properties for the new label
    openModal('Configure Target Node', getTargetModalContent());
  }
}

async function loadPropertyValuesForTarget(filterIndex, propertyName) {
  if (!propertyName || !tripleBuilder.target.label) return;

  const datalist = document.getElementById(`target-values-${filterIndex}`);
  if (!datalist) return;

  try {
    const response = await fetch(window.SCIDK_BASE + `/api/labels/${tripleBuilder.target.label}/property-values/${propertyName}?limit=50`);
    const data = await response.json();

    if (data.status === 'success' && data.values) {
      datalist.innerHTML = data.values.map(v => `<option value="${v}">`).join('');
    }
  } catch (error) {
    console.warn('Failed to load property values:', error);
  }
}

function addTargetFilter() {
  tripleBuilder.target.filters.push({ key: '', value: '' });
  openModal('Configure Target Node', getTargetModalContent());
}

function removeTargetFilter(index) {
  tripleBuilder.target.filters.splice(index, 1);
  openModal('Configure Target Node', getTargetModalContent());
}

function saveTargetConfig() {
  const label = document.getElementById('modal-target-label').value;
  const filters = [];

  document.querySelectorAll('[data-filter-key]').forEach(el => {
    const index = el.dataset.filterKey;
    const key = el.value;
    const value = document.querySelector(`[data-filter-value="${index}"]`).value;
    if (key && value) {
      filters.push({ key, value });
    }
  });

  tripleBuilder.target.label = label;
  tripleBuilder.target.filters = filters;

  closeModal();
  showToast(`Target configured: ${label}`, 'success');
}

// Relationship Modal Functions
function getRelationshipModalContent() {
  // Get available properties from source and target labels
  const sourceLabel = tripleBuilder.source.label;
  const targetLabel = tripleBuilder.target.label;
  const sourceLabelObj = availableLabels.find(l => (typeof l === 'string' ? l : l.name) === sourceLabel);
  const targetLabelObj = availableLabels.find(l => (typeof l === 'string' ? l : l.name) === targetLabel);
  const sourceProps = sourceLabelObj && sourceLabelObj.properties ? sourceLabelObj.properties : [];
  const targetProps = targetLabelObj && targetLabelObj.properties ? targetLabelObj.properties : [];

  return `
    <div class="form-group">
      <label class="form-label small">Relationship Type</label>
      <input id="modal-rel-type" type="text" class="form-control form-control-sm"
             placeholder="e.g., DERIVED_FROM, AUTHORED"
             value="${tripleBuilder.relationship.type}">
    </div>

    <div class="form-group">
      <label class="form-label small">Match Strategy</label>
      <small class="small text-muted" style="display: block; margin-bottom: 0.5rem;">
        How should source and target nodes be connected?
      </small>
      <select id="modal-match-strategy" class="form-control form-control-sm" onchange="showMatchConfigInModal(this.value)">
        <option value="">Select strategy...</option>
        <option value="property" ${tripleBuilder.relationship.match_strategy === 'property' ? 'selected' : ''}>Exact Property Match</option>
        <option value="fuzzy" ${tripleBuilder.relationship.match_strategy === 'fuzzy' ? 'selected' : ''}>Fuzzy Match</option>
        <option value="contains" ${tripleBuilder.relationship.match_strategy === 'contains' ? 'selected' : ''}>CONTAINS</option>
        <option value="list_expansion" ${tripleBuilder.relationship.match_strategy === 'list_expansion' ? 'selected' : ''}>List Expansion (UID Arrays)</option>
        <option value="table_import" ${tripleBuilder.relationship.match_strategy === 'table_import' ? 'selected' : ''}>Table Import (CSV)</option>
        <option value="api_endpoint" ${tripleBuilder.relationship.match_strategy === 'api_endpoint' ? 'selected' : ''}>API Endpoint</option>
        <option value="table_import" ${tripleBuilder.relationship.match_strategy === 'table_import' ? 'selected' : ''}>Data Import (External Graph)</option>
      </select>
    </div>

    <div id="modal-match-config"></div>

    <div class="form-group">
      <label class="form-label small">Relationship Properties (optional)</label>
      ${sourceLabel || targetLabel ? `
        <small class="small text-muted" style="display: block; margin-bottom: 0.5rem;">
          ${sourceLabel && sourceProps.length > 0 ? `Source (${sourceLabel}): ${sourceProps.map(p => typeof p === 'string' ? p : p.name).join(', ')}` : ''}
          ${targetLabel && targetProps.length > 0 ? (sourceLabel && sourceProps.length > 0 ? '<br>' : '') + `Target (${targetLabel}): ${targetProps.map(p => typeof p === 'string' ? p : p.name).join(', ')}` : ''}
        </small>
      ` : ''}
      <div id="modal-rel-props">
        ${tripleBuilder.relationship.properties.map((p, i) => `
          <div class="property-row" style="margin-bottom: 0.5rem;">
            <input type="text" class="form-control form-control-sm" placeholder="name" value="${p.name}" data-prop-name="${i}" style="flex: 1;">
            <select class="form-control form-control-sm" data-prop-type="${i}" style="width: 120px;">
              <option value="static" ${p.type === 'static' ? 'selected' : ''}>Static</option>
              <option value="calculated" ${p.type === 'calculated' ? 'selected' : ''}>Calculated</option>
            </select>
            <input type="text" class="form-control form-control-sm" placeholder="value or source.field" value="${p.value}" data-prop-value="${i}" style="flex: 1;">
            <button class="btn btn-sm btn-outline-danger" onclick="removeRelProperty(${i})">×</button>
          </div>
        `).join('')}
      </div>
      <button class="btn btn-sm btn-outline-primary" onclick="addRelProperty()" style="margin-top: 0.5rem;">+ Add Property</button>
      <small class="small text-muted" style="display: block; margin-top: 0.5rem;">
        Static: fixed value. Calculated: use source.field or target.field syntax
      </small>
    </div>

    <div style="margin-top: 1.5rem; text-align: right; padding-top: 1rem; border-top: 1px solid #eee;">
      <button class="btn btn-sm btn-outline-secondary" onclick="closeModal(true)">Cancel</button>
      <button class="btn btn-sm btn-primary" onclick="saveRelationshipConfig()">Apply</button>
    </div>
  `;
}

function showMatchConfigInModal(strategy) {
  const container = document.getElementById('modal-match-config');
  if (!container) return;

  // Get available properties from source and target labels
  const sourceLabel = tripleBuilder.source.label;
  const targetLabel = tripleBuilder.target.label;
  const sourceLabelObj = availableLabels.find(l => (typeof l === 'string' ? l : l.name) === sourceLabel);
  const targetLabelObj = availableLabels.find(l => (typeof l === 'string' ? l : l.name) === targetLabel);
  const sourceProps = sourceLabelObj && sourceLabelObj.properties ? sourceLabelObj.properties : [];
  const targetProps = targetLabelObj && targetLabelObj.properties ? targetLabelObj.properties : [];

  if (strategy === 'property') {
    const sourceFieldInput = sourceProps.length > 0 ? `
      <select id="modal-property-source-field" class="form-control form-control-sm">
        <option value="">Select source property...</option>
        ${sourceProps.map(p => {
          const propName = typeof p === 'string' ? p : p.name;
          const isSelected = tripleBuilder.relationship.match_config.source_field === propName;
          return `<option value="${propName}" ${isSelected ? 'selected' : ''}>${propName}</option>`;
        }).join('')}
      </select>
    ` : `
      <input id="modal-property-source-field" type="text" class="form-control form-control-sm"
             placeholder="Source field (e.g., email)"
             value="${tripleBuilder.relationship.match_config.source_field || ''}">
    `;

    const targetFieldInput = targetProps.length > 0 ? `
      <select id="modal-property-target-field" class="form-control form-control-sm">
        <option value="">Select target property...</option>
        ${targetProps.map(p => {
          const propName = typeof p === 'string' ? p : p.name;
          const isSelected = tripleBuilder.relationship.match_config.target_field === propName;
          return `<option value="${propName}" ${isSelected ? 'selected' : ''}>${propName}</option>`;
        }).join('')}
      </select>
    ` : `
      <input id="modal-property-target-field" type="text" class="form-control form-control-sm"
             placeholder="Target field (e.g., author_email)"
             value="${tripleBuilder.relationship.match_config.target_field || ''}">
    `;

    container.innerHTML = `
      <div class="form-group" style="padding: 1rem; background: #f8f8f8; border-radius: 4px;">
        <label class="form-label small">Property Match Configuration</label>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.5rem;">
          <div>${sourceFieldInput}</div>
          <div>${targetFieldInput}</div>
        </div>
      </div>
    `;
  } else if (strategy === 'fuzzy') {
    const sourceFieldInput = sourceProps.length > 0 ? `
      <select id="modal-fuzzy-source-field" class="form-control form-control-sm">
        <option value="">Select source property...</option>
        ${sourceProps.map(p => {
          const propName = typeof p === 'string' ? p : p.name;
          const isSelected = tripleBuilder.relationship.match_config.source_field === propName;
          return `<option value="${propName}" ${isSelected ? 'selected' : ''}>${propName}</option>`;
        }).join('')}
      </select>
    ` : `
      <input id="modal-fuzzy-source-field" type="text" class="form-control form-control-sm"
             placeholder="Source field"
             value="${tripleBuilder.relationship.match_config.source_field || ''}">
    `;

    const targetFieldInput = targetProps.length > 0 ? `
      <select id="modal-fuzzy-target-field" class="form-control form-control-sm">
        <option value="">Select target property...</option>
        ${targetProps.map(p => {
          const propName = typeof p === 'string' ? p : p.name;
          const isSelected = tripleBuilder.relationship.match_config.target_field === propName;
          return `<option value="${propName}" ${isSelected ? 'selected' : ''}>${propName}</option>`;
        }).join('')}
      </select>
    ` : `
      <input id="modal-fuzzy-target-field" type="text" class="form-control form-control-sm"
             placeholder="Target field"
             value="${tripleBuilder.relationship.match_config.target_field || ''}">
    `;

    container.innerHTML = `
      <div class="form-group" style="padding: 1rem; background: #f8f8f8; border-radius: 4px;">
        <label class="form-label small">Fuzzy Match Configuration</label>
        <div style="display: grid; grid-template-columns: 1fr 1fr 100px; gap: 0.5rem; margin-top: 0.5rem;">
          ${sourceFieldInput}
          ${targetFieldInput}
          <input id="modal-fuzzy-threshold" type="number" class="form-control form-control-sm"
                 placeholder="80" min="0" max="100"
                 value="${tripleBuilder.relationship.match_config.threshold || 80}">
        </div>
      </div>
    `;
  } else if (strategy === 'contains') {
    const sourceFieldInput = sourceProps.length > 0 ? `
      <select id="modal-contains-source-field" class="form-control form-control-sm">
        <option value="">Select source property...</option>
        ${sourceProps.map(p => {
          const propName = typeof p === 'string' ? p : p.name;
          const isSelected = tripleBuilder.relationship.match_config.source_field === propName;
          return `<option value="${propName}" ${isSelected ? 'selected' : ''}>${propName}</option>`;
        }).join('')}
      </select>
    ` : `
      <input id="modal-contains-source-field" type="text" class="form-control form-control-sm"
             placeholder="Source field"
             value="${tripleBuilder.relationship.match_config.source_field || ''}">
    `;

    const targetFieldInput = targetProps.length > 0 ? `
      <select id="modal-contains-target-field" class="form-control form-control-sm">
        <option value="">Select target property...</option>
        ${targetProps.map(p => {
          const propName = typeof p === 'string' ? p : p.name;
          const isSelected = tripleBuilder.relationship.match_config.target_field === propName;
          return `<option value="${propName}" ${isSelected ? 'selected' : ''}>${propName}</option>`;
        }).join('')}
      </select>
    ` : `
      <input id="modal-contains-target-field" type="text" class="form-control form-control-sm"
             placeholder="Target field"
             value="${tripleBuilder.relationship.match_config.target_field || ''}">
    `;

    container.innerHTML = `
      <div class="form-group" style="padding: 1rem; background: #f8f8f8; border-radius: 4px;">
        <label class="form-label small">CONTAINS Match Configuration</label>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.5rem;">
          ${sourceFieldInput}
          ${targetFieldInput}
        </div>
      </div>
    `;
  } else if (strategy === 'list_expansion') {
    const sourceFieldInput = sourceProps.length > 0 ? `
      <select id="modal-list-source-field" class="form-control form-control-sm">
        <option value="">Select source list property...</option>
        ${sourceProps.map(p => {
          const propName = typeof p === 'string' ? p : p.name;
          const isSelected = tripleBuilder.relationship.match_config.source_field === propName;
          return `<option value="${propName}" ${isSelected ? 'selected' : ''}>${propName}</option>`;
        }).join('')}
      </select>
    ` : `
      <input id="modal-list-source-field" type="text" class="form-control form-control-sm"
             placeholder="Source list property (e.g., parent_ids)"
             value="${tripleBuilder.relationship.match_config.source_field || ''}">
    `;

    const targetFieldInput = targetProps.length > 0 ? `
      <select id="modal-list-target-field" class="form-control form-control-sm">
        <option value="">Select target ID property...</option>
        ${targetProps.map(p => {
          const propName = typeof p === 'string' ? p : p.name;
          const isSelected = tripleBuilder.relationship.match_config.target_field === propName;
          return `<option value="${propName}" ${isSelected ? 'selected' : ''}>${propName}</option>`;
        }).join('')}
      </select>
    ` : `
      <input id="modal-list-target-field" type="text" class="form-control form-control-sm"
             placeholder="Target ID field (e.g., uid)"
             value="${tripleBuilder.relationship.match_config.target_field || ''}">
    `;

    container.innerHTML = `
      <div class="form-group" style="padding: 1rem; background: #f8f8f8; border-radius: 4px;">
        <label class="form-label small">List Expansion Configuration</label>
        <small class="small text-muted" style="display: block; margin-bottom: 0.5rem;">
          Expand a list/array property on source nodes and match each value to target nodes
        </small>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-top: 0.5rem;">
          <div>
            <label class="form-label small">Source List Property</label>
            ${sourceFieldInput}
          </div>
          <div>
            <label class="form-label small">Target Match Property</label>
            ${targetFieldInput}
          </div>
        </div>
      </div>
    `;
  } else if (strategy === 'table_import') {
    container.innerHTML = `
      <div class="form-group" style="padding: 1rem; background: #f8f8f8; border-radius: 4px;">
        <label class="form-label small">CSV/TSV Data</label>
        <textarea id="modal-table-data" class="form-control form-control-sm" rows="6"
                  placeholder="name,email,role\nAlice,alice@ex.com,author">${tripleBuilder.relationship.match_config.table_data || ''}</textarea>
      </div>
    `;
  } else if (strategy === 'api_endpoint') {
    container.innerHTML = `
      <div class="form-group" style="padding: 1rem; background: #f8f8f8; border-radius: 4px;">
        <label class="form-label small">API Configuration</label>
        <input id="modal-api-url" type="text" class="form-control form-control-sm"
               placeholder="https://api.example.com/users" style="margin-top: 0.5rem;"
               value="${tripleBuilder.relationship.match_config.api_url || ''}">
        <input id="modal-api-jsonpath" type="text" class="form-control form-control-sm"
               placeholder="JSONPath (optional, e.g., $.data.users[*])" style="margin-top: 0.5rem;"
               value="${tripleBuilder.relationship.match_config.api_jsonpath || ''}">
      </div>
    `;
  } else if (strategy === 'table_import') {
    const externalDbs = [...new Set(discoveredRelationships
      .map(r => r.database)
      .filter(db => db !== 'PRIMARY'))];

    container.innerHTML = `
      <div class="form-group" style="padding: 1rem; background: #f8f8f8; border-radius: 4px;">
        <label class="form-label small">Source Database</label>
        <select id="modal-data-import-db" class="form-control form-control-sm" style="margin-top: 0.5rem;">
          <option value="">Select external database...</option>
          ${externalDbs.map(db => `<option value="${db}" ${tripleBuilder.relationship.match_config.source_database === db ? 'selected' : ''}>${db}</option>`).join('')}
        </select>
      </div>
    `;
  } else {
    container.innerHTML = '';
  }
}

function addRelProperty() {
  tripleBuilder.relationship.properties.push({ name: '', type: 'static', value: '' });
  openModal('Configure Relationship', getRelationshipModalContent());
  showMatchConfigInModal(tripleBuilder.relationship.match_strategy);
}

function removeRelProperty(index) {
  tripleBuilder.relationship.properties.splice(index, 1);
  openModal('Configure Relationship', getRelationshipModalContent());
  showMatchConfigInModal(tripleBuilder.relationship.match_strategy);
}

function saveRelationshipConfig() {
  const relType = document.getElementById('modal-rel-type').value;
  const matchStrategy = document.getElementById('modal-match-strategy').value;

  // Collect properties
  const properties = [];
  document.querySelectorAll('[data-prop-name]').forEach(el => {
    const index = el.dataset.propName;
    const name = el.value;
    const type = document.querySelector(`[data-prop-type="${index}"]`)?.value;
    const value = document.querySelector(`[data-prop-value="${index}"]`)?.value;
    if (name && value) {
      properties.push({ name, type, value });
    }
  });

  // Collect match config based on strategy
  let matchConfig = {};
  if (matchStrategy === 'property') {
    matchConfig = {
      source_field: document.getElementById('modal-property-source-field')?.value || '',
      target_field: document.getElementById('modal-property-target-field')?.value || ''
    };
  } else if (matchStrategy === 'fuzzy') {
    matchConfig = {
      source_field: document.getElementById('modal-fuzzy-source-field')?.value || '',
      target_field: document.getElementById('modal-fuzzy-target-field')?.value || '',
      threshold: parseInt(document.getElementById('modal-fuzzy-threshold')?.value || '80')
    };
  } else if (matchStrategy === 'contains') {
    matchConfig = {
      source_field: document.getElementById('modal-contains-source-field')?.value || '',
      target_field: document.getElementById('modal-contains-target-field')?.value || ''
    };
  } else if (matchStrategy === 'list_expansion') {
    matchConfig = {
      source_field: document.getElementById('modal-list-source-field')?.value || '',
      target_field: document.getElementById('modal-list-target-field')?.value || ''
    };
  } else if (matchStrategy === 'table_import') {
    matchConfig = {
      table_data: document.getElementById('modal-table-data')?.value || ''
    };
  } else if (matchStrategy === 'api_endpoint') {
    matchConfig = {
      api_url: document.getElementById('modal-api-url')?.value || '',
      api_jsonpath: document.getElementById('modal-api-jsonpath')?.value || ''
    };
  } else if (matchStrategy === 'table_import') {
    matchConfig = {
      source_database: document.getElementById('modal-data-import-db')?.value || ''
    };
  }

  tripleBuilder.relationship.type = relType;
  tripleBuilder.relationship.match_strategy = matchStrategy;
  tripleBuilder.relationship.match_config = matchConfig;
  tripleBuilder.relationship.properties = properties;

  closeModal();
  showToast(`Relationship configured: ${relType} (${matchStrategy})`, 'success');
}
function loadPreview() {
  // Check if we're in discovered import mode
  if (discoveredImportConfig.rel) {
    loadDiscoveredInstances();
    return;
  }

  const linkName = document.getElementById('link-name').value.trim();

  if (!linkName || !tripleBuilder.relationship.type || !tripleBuilder.source.label || !tripleBuilder.target.label) {
    showToast('Please complete all required fields', 'error');
    return;
  }

  // Convert tripleBuilder to API format
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

  // Save first if new
  const savePromise = tripleBuilder.link_id ? Promise.resolve({ link: data }) :
    fetch(window.SCIDK_BASE + '/api/links', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).then(r => r.json());

  document.getElementById('preview-loading').style.display = 'inline';

  savePromise
    .then(saveResult => {
      if (!saveResult || !saveResult.link || !saveResult.link.id) {
        throw new Error('Failed to save link definition');
      }
      const linkId = saveResult.link.id;
      tripleBuilder.link_id = linkId;

      return fetch(window.SCIDK_BASE + `/api/links/${linkId}/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ limit: 10 })
      });
    })
    .then(r => r.json())
    .then(result => {
      document.getElementById('preview-loading').style.display = 'none';

      if (result.status === 'success') {
        renderPreview(result.matches || []);
      } else {
        showToast(`Preview failed: ${result.error}`, 'error');
      }
    })
    .catch(err => {
      document.getElementById('preview-loading').style.display = 'none';
      showToast('Failed to load preview', 'error');
    });
}

function renderPreview(matches) {
  const container = document.getElementById('preview-container');

  if (matches.length === 0) {
    container.innerHTML = '<div class="empty-state small">No matches found</div>';
    return;
  }

  container.innerHTML = `
    <div class="small" style="margin-bottom: 0.5rem; font-weight: 500;">
      Sample Matches (${matches.length}):
    </div>
    <div class="match-preview">
      ${matches.map(match => {
        const source = match.source || {};
        const target = match.target || {};
        return `
          <div class="match-item">
            <div><strong>Source:</strong> ${JSON.stringify(source).substring(0, 100)}...</div>
            <div><strong>Target:</strong> ${JSON.stringify(target).substring(0, 100)}...</div>
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function exportMatchesCsv() {
  if (!tripleBuilder.link_id) {
    showToast('Please save the definition first', 'error');
    return;
  }

  showToast('Exporting matches to CSV...', 'info');

  fetch(window.SCIDK_BASE + `/api/links/${tripleBuilder.link_id}/export-csv`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ limit: 1000 })
  })
    .then(response => {
      if (!response.ok) throw new Error('Export failed');
      return response.blob();
    })
    .then(blob => {
      // Download the CSV file
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `matches_${tripleBuilder.link_id}_${Date.now()}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      showToast('CSV exported! Review and mark validated=yes for valid matches', 'success');
    })
    .catch(err => {
      console.error('CSV export failed:', err);
      showToast('Failed to export CSV', 'error');
    });
}

function importValidatedCsv(file) {
  if (!tripleBuilder.link_id) {
    showToast('Please save the definition first', 'error');
    return;
  }

  if (!file || !file.name.endsWith('.csv')) {
    showToast('Please select a valid CSV file', 'error');
    return;
  }

  showToast('Importing validated matches...', 'info');

  const formData = new FormData();
  formData.append('file', file);

  fetch(window.SCIDK_BASE + `/api/links/${tripleBuilder.link_id}/import-csv`, {
    method: 'POST',
    body: formData
  })
    .then(r => r.json())
    .then(result => {
      if (result.status === 'success') {
        showToast(`Created ${result.relationships_created} relationships from ${result.rows_validated} validated matches (${result.rows_processed} total rows)`, 'success');

        // Refresh preview to show created relationships
        loadPreview();
      } else {
        showToast(`Import failed: ${result.error}`, 'error');
      }
    })
    .catch(err => {
      console.error('CSV import failed:', err);
      showToast('Failed to import CSV', 'error');
    });
}

