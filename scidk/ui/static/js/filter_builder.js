/**
 * FilterBuilder — reusable schema-aware filter component.
 *
 * Reads the live graph schema from /api/schema/labels,
 * /api/schema/relationship-types and /api/schema/property-types, and produces
 * a filter definition that the backend turns into parameterized Cypher
 * (scidk/services/filter_builder.py). No build step, no framework — loaded
 * with a plain <script> tag from base.html.
 *
 * Usage:
 *   const fb = new FilterBuilder('my-container', {
 *     onPreview: (count, cypher) => console.log(count + ' nodes'),
 *     onUse:     (filterDef) => doSomethingWith(filterDef),
 *     defaultLabel: 'Investigator',
 *   });
 */

(function injectStyles() {
  if (document.getElementById('filter-builder-styles')) return;
  const s = document.createElement('style');
  s.id = 'filter-builder-styles';
  s.textContent = `
    .fb-block        { border:1px solid var(--border,#ddd); border-radius:6px;
                       padding:10px 12px; margin-bottom:8px; background:var(--bg-card,#fff); }
    .fb-block-header { display:flex; align-items:center; gap:8px; margin-bottom:6px; }
    .fb-via          { display:flex; align-items:center; gap:6px; font-size:.85em;
                       color:var(--text-muted,#666); margin-bottom:6px; }
    .fb-via-label    { font-weight:600; }
    .fb-condition-row{ display:flex; align-items:center; gap:6px; margin-bottom:4px; }
    .fb-actions      { display:flex; align-items:center; gap:8px; margin-top:10px; }
    .fb-preview-count{ font-size:.85em; color:var(--text-muted,#666); }
    .fb-select       { padding:3px 6px; border-radius:4px; border:1px solid #ccc; }
    .fb-select-sm    { padding:2px 4px; border-radius:4px; border:1px solid #ccc; font-size:.9em; }
    .fb-input-sm     { padding:2px 6px; border-radius:4px; border:1px solid #ccc;
                       width:140px; font-size:.9em; }
    .fb-input-xs     { padding:2px 4px; border-radius:4px; border:1px solid #ccc;
                       width:40px; font-size:.85em; text-align:center; }
    .fb-btn-primary  { padding:4px 12px; background:var(--accent,#2563eb);
                       color:#fff; border:none; border-radius:4px; cursor:pointer; }
    .fb-btn-secondary{ padding:4px 10px; background:var(--bg-btn,#f0f0f0);
                       border:1px solid #ccc; border-radius:4px; cursor:pointer; }
    .fb-btn-icon     { background:none; border:none; cursor:pointer;
                       color:var(--text-muted,#888); font-size:1.1em; }
    .fb-btn-link     { background:none; border:none; cursor:pointer;
                       color:var(--accent,#2563eb); font-size:.85em; padding:2px 0; }
    .fb-value-container { display:inline-flex; align-items:center; gap:4px; }
  `;
  document.head.appendChild(s);
})();

class FilterBuilder {

  static OPERATORS = {
    string: [
      {value: 'contains',     label: 'contains'},
      {value: 'not_contains', label: 'does not contain'},
      {value: 'equals',       label: '= equals'},
      {value: 'not_equals',   label: '≠ not equals'},
      {value: 'starts_with',  label: 'starts with'},
      {value: 'ends_with',    label: 'ends with'},
      {value: 'regex',        label: 'regex'},
      {value: 'is_null',      label: 'is missing'},
      {value: 'is_not_null',  label: 'is present'},
    ],
    number: [
      {value: 'equals',  label: '= equals'},
      {value: 'gt',      label: '> greater than'},
      {value: 'gte',     label: '≥ at least'},
      {value: 'lt',      label: '< less than'},
      {value: 'lte',     label: '≤ at most'},
      {value: 'between', label: 'between'},
    ],
    date: [
      {value: 'after',       label: 'after'},
      {value: 'before',      label: 'before'},
      {value: 'between',     label: 'between'},
      {value: 'is_null',     label: 'is missing'},
      {value: 'is_not_null', label: 'is present'},
    ],
    boolean: [
      {value: 'is_true',  label: 'is true'},
      {value: 'is_false', label: 'is false'},
    ],
    null: [
      {value: 'is_null',     label: 'is missing'},
      {value: 'is_not_null', label: 'is present'},
    ],
  };

  static NO_VALUE_OPS = new Set([
    'is_null', 'is_not_null', 'is_true', 'is_false'
  ]);

  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    if (!this.container) throw new Error(`FilterBuilder: #${containerId} not found`);

    this.options = {
      onPreview:    null,   // fn(count, cypher)
      onUse:        null,   // fn(filterDef)
      onSave:       null,   // fn(filterDef) — for "Save as dataset"
      defaultLabel: null,
      showSave:     false,
      ...options,
    };

    this.blocks      = [];   // [{label, match, conditions[], via?}]
    this.schemaCache = {};   // label → [PropertyInfo]
    this.labelList   = [];
    this.relTypeList = [];

    // Resolves once the initial schema fetch and first block have rendered,
    // so callers (and tests) can await a usable component.
    this.ready = this._init();
  }

  // -----------------------------------------------------------------------
  // Public

  /** Return the current filter definition as a plain JS object. */
  getFilterDef() {
    return { blocks: JSON.parse(JSON.stringify(this.blocks)) };
  }

  /** Pre-populate the builder from a saved filter definition. */
  async loadFilterDef(filterDef) {
    this.blocks = (filterDef && filterDef.blocks) || [];
    await Promise.all(
      this.blocks.filter(b => b.label).map(b => this._fetchProps(b.label))
    );
    await this._renderAll();
  }

  // -----------------------------------------------------------------------
  // Init

  async _init() {
    await Promise.all([this._loadLabels(), this._loadRelTypes()]);
    this._renderShell();
    await this._addBlock(this.options.defaultLabel || null);
  }

  async _loadLabels() {
    try {
      const r = await fetch('/api/schema/labels');
      const d = await r.json();
      this.labelList = d.labels || [];
    } catch (e) { console.warn('FilterBuilder: could not load labels', e); }
  }

  async _loadRelTypes() {
    try {
      const r = await fetch('/api/schema/relationship-types');
      const d = await r.json();
      this.relTypeList = d.relationship_types || [];
    } catch (e) { console.warn('FilterBuilder: could not load rel types', e); }
  }

  // -----------------------------------------------------------------------
  // Render

  _renderShell() {
    this.container.innerHTML = '';

    this._blocksEl = document.createElement('div');
    this._blocksEl.className = 'fb-blocks';
    this.container.appendChild(this._blocksEl);

    const actions = document.createElement('div');
    actions.className = 'fb-actions';

    // Listeners are attached directly rather than via inline onclick: inside an
    // inline handler `this` is the button, so a self-reference stashed on the
    // container would not be reachable.
    const addBtn = this._button('fb-btn-secondary', '+ Add block', () => this.addBlock());
    const previewBtn = this._button('fb-btn-secondary', 'Preview', () => this.preview());

    const spacer = document.createElement('span');
    spacer.style.flex = '1';

    this._previewEl = document.createElement('span');
    this._previewEl.className = 'fb-preview-count';

    actions.appendChild(addBtn);
    actions.appendChild(spacer);
    actions.appendChild(previewBtn);
    actions.appendChild(this._previewEl);
    if (this.options.showSave) {
      actions.appendChild(
        this._button('fb-btn-secondary', 'Save as dataset', () => this.save()));
    }
    if (this.options.onUse) {
      actions.appendChild(this._button('fb-btn-primary', 'Use', () => this.use()));
    }
    this.container.appendChild(actions);
  }

  _button(cls, text, handler) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = cls;
    b.textContent = text;
    b.addEventListener('click', handler);
    return b;
  }

  async _renderAll() {
    this._blocksEl.innerHTML = '';
    // Sequential, so blocks land in index order.
    for (let i = 0; i < this.blocks.length; i++) {
      await this._renderBlock(i);
    }
  }

  async _renderBlock(i) {
    const block = this.blocks[i];
    const isFirst = i === 0;

    const el = document.createElement('div');
    el.className = 'fb-block';
    el.dataset.blockIndex = i;

    if (!isFirst) el.appendChild(this._makeViaRow(i));
    el.appendChild(this._makeBlockHeader(i));

    const condContainer = document.createElement('div');
    condContainer.className = 'fb-conditions';
    condContainer.id = `fb-conds-${this._id()}-${i}`;
    el.appendChild(condContainer);

    const addCondBtn = this._button('fb-btn-link', '+ Add condition',
                                    () => this._addCondition(i));
    el.appendChild(addCondBtn);

    this._blocksEl.appendChild(el);

    if (block.label) {
      await this._fetchProps(block.label);
      block.conditions.forEach((_, ci) => this._renderCondition(i, ci));
    }
  }

  _makeViaRow(blockIndex) {
    const block = this.blocks[blockIndex];
    block.via = block.via || {type: this.relTypeList[0] || 'RELATES_TO',
                              min_hops: 1, max_hops: 1};

    const div = document.createElement('div');
    div.className = 'fb-via';

    const viaLabel = document.createElement('span');
    viaLabel.className = 'fb-via-label';
    viaLabel.textContent = '↳ relates via';

    const relSel = document.createElement('select');
    relSel.className = 'fb-select-sm';
    this.relTypeList.forEach(rt => {
      const opt = document.createElement('option');
      opt.value = rt; opt.textContent = rt;
      if (block.via.type === rt) opt.selected = true;
      relSel.appendChild(opt);
    });
    if (this.relTypeList.includes(block.via.type)) relSel.value = block.via.type;
    relSel.onchange = () => { block.via.type = relSel.value; };

    const hopInput = (key) => {
      const inp = document.createElement('input');
      inp.type = 'number'; inp.min = 1; inp.max = 9;
      inp.value = block.via[key] || 1;
      inp.className = 'fb-input-xs';
      inp.onchange = () => {
        const n = parseInt(inp.value, 10);
        block.via[key] = Number.isFinite(n) && n >= 1 ? n : 1;
        inp.value = block.via[key];
      };
      return inp;
    };

    div.appendChild(viaLabel);
    div.appendChild(relSel);
    div.appendChild(document.createTextNode(' hops: '));
    div.appendChild(hopInput('min_hops'));
    div.appendChild(document.createTextNode(' – '));
    div.appendChild(hopInput('max_hops'));

    return div;
  }

  _makeBlockHeader(i) {
    const block = this.blocks[i];
    const div = document.createElement('div');
    div.className = 'fb-block-header';

    const labelSel = document.createElement('select');
    labelSel.className = 'fb-select';
    const placeholder = document.createElement('option');
    placeholder.value = ''; placeholder.textContent = 'Select label…';
    labelSel.appendChild(placeholder);
    this.labelList.forEach(l => {
      const opt = document.createElement('option');
      opt.value = l; opt.textContent = l;
      if (block.label === l) opt.selected = true;
      labelSel.appendChild(opt);
    });
    labelSel.value = this.labelList.includes(block.label) ? block.label : '';
    labelSel.onchange = async () => {
      this.blocks[i].label = labelSel.value;
      this.blocks[i].conditions = [];
      if (labelSel.value) await this._fetchProps(labelSel.value);
      this._refreshConditions(i);
    };

    const matchSel = document.createElement('select');
    matchSel.className = 'fb-select-sm';
    ['ALL', 'ANY'].forEach(m => {
      const opt = document.createElement('option');
      opt.value = m; opt.textContent = m;
      if (block.match === m) opt.selected = true;
      matchSel.appendChild(opt);
    });
    matchSel.value = block.match === 'ANY' ? 'ANY' : 'ALL';
    matchSel.onchange = () => { this.blocks[i].match = matchSel.value; };

    const removeBtn = this._button('fb-btn-icon', '×', () => this._removeBlock(i));
    removeBtn.title = 'Remove block';
    removeBtn.style.display = i === 0 ? 'none' : '';

    div.appendChild(document.createTextNode('Label: '));
    div.appendChild(labelSel);
    div.appendChild(document.createTextNode(' Match: '));
    div.appendChild(matchSel);
    div.appendChild(removeBtn);

    return div;
  }

  _renderCondition(blockIndex, condIndex) {
    const block = this.blocks[blockIndex];
    const cond  = block.conditions[condIndex];
    const props = this.schemaCache[block.label] || [];

    const container = document.getElementById(
      `fb-conds-${this._id()}-${blockIndex}`
    );
    if (!container) return;

    const row = document.createElement('div');
    row.className = 'fb-condition-row';
    row.id = `fb-cond-${this._id()}-${blockIndex}-${condIndex}`;

    const propSel = document.createElement('select');
    propSel.className = 'fb-select-sm';
    props.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = p.name;
      opt.dataset.type = p.type;
      if (cond.property === p.name) opt.selected = true;
      propSel.appendChild(opt);
    });

    const opSel = document.createElement('select');
    opSel.className = 'fb-select-sm';

    const valueContainer = document.createElement('span');
    valueContainer.className = 'fb-value-container';

    const rmBtn = this._button('fb-btn-icon', '×',
                               () => this._removeCondition(blockIndex, condIndex));

    const refreshValue = () => {
      const op = opSel.value;
      const noVal = FilterBuilder.NO_VALUE_OPS.has(op);
      const isBetween = op === 'between';
      const propInfo = (this.schemaCache[block.label] || [])
        .find(p => p.name === propSel.value);
      const type = (propInfo && propInfo.type) || 'string';
      const inputType = (type === 'date') ? 'date'
                      : (type === 'number') ? 'number'
                      : 'text';

      // An <input> always reports a string. Send numbers as numbers: Cypher
      // compares 5 and 5.0 as equal, but never matches "5" against either.
      // Dates stay strings — the backend compares ISO strings directly.
      const typed = (raw) => {
        if (type !== 'number' || raw === '') return raw;
        const n = Number(raw);
        return Number.isFinite(n) ? n : raw;
      };

      valueContainer.innerHTML = '';
      if (!noVal) {
        if (isBetween) {
          const lo = document.createElement('input');
          lo.type = inputType; lo.className = 'fb-input-sm';
          lo.placeholder = 'from';
          lo.value = Array.isArray(cond.value) ? cond.value[0] : '';
          const hi = document.createElement('input');
          hi.type = inputType; hi.className = 'fb-input-sm';
          hi.placeholder = 'to';
          hi.value = Array.isArray(cond.value) ? cond.value[1] : '';
          const save = () => { cond.value = [typed(lo.value), typed(hi.value)]; };
          lo.onchange = save; hi.onchange = save;
          valueContainer.appendChild(lo);
          valueContainer.appendChild(document.createTextNode(' – '));
          valueContainer.appendChild(hi);
        } else {
          const inp = document.createElement('input');
          inp.type = inputType; inp.className = 'fb-input-sm';
          inp.value = Array.isArray(cond.value) ? '' : (cond.value == null ? '' : cond.value);
          inp.onchange = () => { cond.value = typed(inp.value); };
          valueContainer.appendChild(inp);
        }
      } else {
        // The operator carries the whole condition; drop any stale value so it
        // is not sent to the backend.
        cond.value = null;
      }
      cond.operator = op;
    };

    const refreshOps = (propInfo) => {
      const type = propInfo ? propInfo.type : 'string';
      const ops = FilterBuilder.OPERATORS[type] || FilterBuilder.OPERATORS.string;
      // The condition may carry an operator that does not apply to this
      // property's type (a fresh condition defaults to 'contains', a saved one
      // may predate a schema change) — fall back to the type's first operator.
      const chosen = ops.some(o => o.value === cond.operator)
        ? cond.operator : ops[0].value;
      opSel.innerHTML = '';
      ops.forEach(o => {
        const opt = document.createElement('option');
        opt.value = o.value; opt.textContent = o.label;
        if (o.value === chosen) opt.selected = true;
        opSel.appendChild(opt);
      });
      opSel.value = chosen;
      refreshValue();
    };

    propSel.onchange = () => {
      cond.property = propSel.value;
      refreshOps((this.schemaCache[block.label] || [])
        .find(p => p.name === propSel.value));
    };
    opSel.onchange = refreshValue;

    row.appendChild(propSel);
    row.appendChild(opSel);
    row.appendChild(valueContainer);
    row.appendChild(rmBtn);
    container.appendChild(row);

    const initProp = props.find(p => p.name === cond.property) || props[0];
    if (initProp) {
      cond.property = initProp.name;
      propSel.value = initProp.name;
      refreshOps(initProp);
    }
  }

  // -----------------------------------------------------------------------
  // State mutations

  async _addBlock(labelOverride = null) {
    const block = {
      label:      labelOverride || '',
      match:      'ALL',
      conditions: [],
    };
    if (this.blocks.length > 0) {
      block.via = {
        type: this.relTypeList[0] || 'RELATES_TO',
        min_hops: 1,
        max_hops: 1,
      };
    }
    this.blocks.push(block);
    await this._renderBlock(this.blocks.length - 1);
  }

  addBlock() { return this._addBlock(); }

  _removeBlock(i) {
    this.blocks.splice(i, 1);
    // The first block leads the MATCH path, so it can never carry a connector.
    if (this.blocks.length) delete this.blocks[0].via;
    return this._renderAll();
  }

  _addCondition(blockIndex) {
    const block = this.blocks[blockIndex];
    const props = this.schemaCache[block.label] || [];
    const firstProp = props[0];
    block.conditions.push({
      property: (firstProp && firstProp.name) || '',
      operator: 'contains',
      value: '',
    });
    // _renderCondition reconciles the operator with the property's actual type.
    this._renderCondition(blockIndex, block.conditions.length - 1);
  }

  _removeCondition(blockIndex, condIndex) {
    this.blocks[blockIndex].conditions.splice(condIndex, 1);
    this._refreshConditions(blockIndex);
  }

  _refreshConditions(blockIndex) {
    const container = document.getElementById(
      `fb-conds-${this._id()}-${blockIndex}`
    );
    if (container) container.innerHTML = '';
    this.blocks[blockIndex].conditions.forEach((_, ci) => {
      this._renderCondition(blockIndex, ci);
    });
  }

  // -----------------------------------------------------------------------
  // Schema cache

  async _fetchProps(label) {
    if (this.schemaCache[label]) return;
    try {
      const r = await fetch(
        `/api/schema/property-types?label=${encodeURIComponent(label)}`);
      const d = await r.json();
      this.schemaCache[label] = d.properties || [];
    } catch (e) {
      console.warn(`FilterBuilder: could not fetch props for ${label}`, e);
      this.schemaCache[label] = [];
    }
  }

  // -----------------------------------------------------------------------
  // Actions

  async preview() {
    const filterDef = this.getFilterDef();
    try {
      const r = await fetch('/api/schema/filter-preview', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(filterDef),
      });
      const d = await r.json();
      if (this._previewEl) {
        this._previewEl.textContent = d.error
          ? `Error: ${d.error}`
          : `Preview: ${d.total} node${d.total !== 1 ? 's' : ''}`;
      }
      if (this.options.onPreview) this.options.onPreview(d.total, d.cypher);
      return d;
    } catch (e) {
      if (this._previewEl) this._previewEl.textContent = 'Preview failed';
      return null;
    }
  }

  use() {
    if (this.options.onUse) this.options.onUse(this.getFilterDef());
  }

  save() {
    if (this.options.onSave) this.options.onSave(this.getFilterDef());
  }

  // -----------------------------------------------------------------------
  // Utilities

  _id() {
    if (!this._instanceId) {
      this._instanceId = Math.random().toString(36).slice(2, 8);
    }
    return this._instanceId;
  }
}

window.FilterBuilder = FilterBuilder;
