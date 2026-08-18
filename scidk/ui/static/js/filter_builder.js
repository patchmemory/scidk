/**
 * FilterBuilder — reusable schema-aware filter component.
 *
 * Reads the live graph schema from /api/schema/labels,
 * /api/schema/relationship-types and /api/schema/property-types, and produces
 * a filter definition that the backend turns into parameterized Cypher
 * (scidk/services/filter_builder.py). No build step, no framework — loaded
 * with a plain <script> tag from base.html.
 *
 * Usage — the argument is a container *id*, not an element:
 *   const fb = new FilterBuilder('my-container', {
 *     onPreview: (count, cypher, error) => console.log(error || count + ' nodes'),
 *     onUse:     (filterDef) => doSomethingWith(filterDef),
 *     defaultLabel: 'Investigator',
 *     // Optional. Offer a value picker instead of a text box where the host
 *     // knows what values exist; return null to keep the text box.
 *     valueOptionsFor: async (label, property) => fetchValues(label, property),
 *     // Optional. Attach/tear down a select-enhancement library around the
 *     // renders that rebuild rows by assigning innerHTML.
 *     onRender:   (el) => enhanceSelectsIn(el),
 *     beforeWipe: (el) => destroySelectsIn(el),
 *   });
 *
 * getFilterDef() returns raw state; call validate() before submitting it.
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

    // Every option below defaults to a value that reproduces the component's
    // original behavior, so adding one never changes an existing consumer.
    this.options = {
      onPreview:    null,   // fn(count, cypher, error)
      onUse:        null,   // fn(filterDef)
      onSave:       null,   // fn(filterDef) — for "Save as dataset"
      defaultLabel: null,
      showSave:     false,
      // fn(label, property) → Promise<string[] | null>. A non-null array turns
      // the value control into a <select> over those values; null (or an
      // omitted callback) keeps the free-text <input>. Lets a host that knows
      // which values exist — an /…/property-values endpoint, say — offer them
      // instead of asking the user to guess a substring.
      valueOptionsFor: null,
      // fn(container) after a render settles, fn(container) before one is
      // wiped. The pair a select-enhancement library needs: this component
      // rebuilds its rows by assigning innerHTML, which silently orphans any
      // wrapper attached to the selects inside them.
      onRender:     null,
      beforeWipe:   null,
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

  /** Return the current filter definition as a plain JS object.
   *
   * Deliberately raw: what the controls hold, valid or not. Callers that are
   * about to submit should run {@link validate} first — filtering here would
   * mean the object a caller gets back does not round-trip through
   * loadFilterDef, and would drop a half-built block without saying so.
   */
  getFilterDef() {
    return { blocks: JSON.parse(JSON.stringify(this.blocks)) };
  }

  /** Check the current state against what the backend generator will accept.
   *
   * The two ways to reach a definition the backend rejects with 400 are a
   * block with no label (the default state of "+ Add block") and a condition
   * with no property (what "+ Add condition" produces on a label whose schema
   * fetch returned nothing). Both interpolate into Cypher, so both are
   * whitelisted server-side and fail there rather than matching nothing.
   *
   * @returns {{valid: boolean, errors: string[]}}
   */
  validate() {
    const errors = [];
    if (!this.blocks.length) errors.push('Add at least one block.');
    this.blocks.forEach((block, i) => {
      const where = this.blocks.length > 1 ? ` in block ${i + 1}` : '';
      if (!block.label) errors.push(`Select a label${where}.`);
      (block.conditions || []).forEach((cond, ci) => {
        if (!cond.property) {
          errors.push(`Condition ${ci + 1}${where} has no property.`);
        }
      });
    });
    return { valid: errors.length === 0, errors };
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
      const r = await fetch((window.SCIDK_BASE || '') + '/api/schema/labels');
      const d = await r.json();
      this.labelList = d.labels || [];
    } catch (e) { console.warn('FilterBuilder: could not load labels', e); }
  }

  async _loadRelTypes() {
    try {
      const r = await fetch((window.SCIDK_BASE || '') + '/api/schema/relationship-types');
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
    this._fireWipe(this._blocksEl);
    this._blocksEl.innerHTML = '';
    // Sequential, so blocks land in index order.
    for (let i = 0; i < this.blocks.length; i++) {
      await this._renderBlock(i);
    }
    this._fireRender(this._blocksEl);
  }

  /** Tell the host a subtree is about to be replaced, so it can tear down. */
  _fireWipe(el) {
    if (this.options.beforeWipe && el) {
      try { this.options.beforeWipe(el); }
      catch (e) { console.warn('FilterBuilder: beforeWipe threw', e); }
    }
  }

  /** Tell the host a subtree has settled, so it can enhance it. */
  _fireRender(el) {
    if (this.options.onRender && el) {
      try { this.options.onRender(el); }
      catch (e) { console.warn('FilterBuilder: onRender threw', e); }
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
    this._fireRender(el);
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
    // A label the graph does not (yet) carry is offered rather than discarded.
    // Dropping it left the select reading "Select label…" while the block kept
    // the invisible value, so getFilterDef() returned a label the user could
    // not see and the backend generated MATCH (n0:ThatLabel) — 200, zero rows,
    // no way to tell why. Offering it keeps the control and the state agreeing;
    // an empty result is then legible as "no such nodes", which is the truth.
    if (block.label && !this.labelList.includes(block.label)) {
      const opt = document.createElement('option');
      opt.value = block.label; opt.textContent = block.label;
      labelSel.appendChild(opt);
    }
    this.labelList.forEach(l => {
      const opt = document.createElement('option');
      opt.value = l; opt.textContent = l;
      if (block.label === l) opt.selected = true;
      labelSel.appendChild(opt);
    });
    labelSel.value = block.label || '';
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

    // Bumped on every refreshValue, so an in-flight valueOptionsFor resolving
    // after the operator or property changed knows its container is stale.
    let valueToken = 0;

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

      this._fireWipe(valueContainer);
      valueContainer.innerHTML = '';
      const token = ++valueToken;
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
          // If the host can enumerate this property's values, swap the free
          // text box for a picker over them once they arrive. The input goes
          // in first so the row stays usable while the callback is in flight,
          // and so a host that resolves null costs nothing but the call.
          this._offerValueOptions(block.label, propSel.value, cond, typed,
                                  valueContainer, () => token === valueToken);
        }
      } else {
        // The operator carries the whole condition; drop any stale value so it
        // is not sent to the backend.
        cond.value = null;
      }
      cond.operator = op;
      this._fireRender(valueContainer);
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

  /** Replace a condition's free-text value input with a picker, if the host
   *  can say which values exist for this (label, property).
   *
   *  No-op unless ``options.valueOptionsFor`` is set and resolves to a
   *  non-empty array. An empty array falls back to the input rather than
   *  rendering an empty <select>: "this property has no values" and "you may
   *  not type one" together leave the condition unfillable.
   *
   *  Single-value operators only. ``between`` keeps its two inputs — a range
   *  is a pair of bounds, not a choice from a list, and the bounds a user
   *  wants are routinely values no node carries.
   *
   *  @param {function(): boolean} isCurrent — false once a later render has
   *    taken the container over, in which case this resolution is discarded.
   */
  async _offerValueOptions(label, property, cond, typed, container, isCurrent) {
    if (!this.options.valueOptionsFor || !property) return;

    let values;
    try {
      values = await this.options.valueOptionsFor(label, property);
    } catch (e) {
      console.warn('FilterBuilder: valueOptionsFor threw', e);
      return;
    }
    if (!Array.isArray(values) || !values.length || !isCurrent()) return;

    const sel = document.createElement('select');
    sel.className = 'fb-select-sm';
    const blank = document.createElement('option');
    blank.value = ''; blank.textContent = 'Select a value…';
    sel.appendChild(blank);

    // A value already on the condition that the list does not carry is offered
    // rather than dropped — same rule as an off-schema label in
    // _makeBlockHeader: the control must not disagree with the state behind it.
    const current = (cond.value == null || Array.isArray(cond.value))
      ? '' : String(cond.value);
    if (current && !values.some(v => String(v) === current)) {
      const opt = document.createElement('option');
      opt.value = current; opt.textContent = current;
      sel.appendChild(opt);
    }
    values.forEach(v => {
      const opt = document.createElement('option');
      opt.value = String(v); opt.textContent = String(v);
      sel.appendChild(opt);
    });
    sel.value = current;
    // Through `typed` for the same reason the input is: Cypher never matches
    // the string "5" against the number 5.
    sel.onchange = () => { cond.value = typed(sel.value); };

    this._fireWipe(container);
    container.innerHTML = '';
    container.appendChild(sel);
    this._fireRender(container);
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
    if (container) {
      this._fireWipe(container);
      container.innerHTML = '';
    }
    this.blocks[blockIndex].conditions.forEach((_, ci) => {
      this._renderCondition(blockIndex, ci);
    });
    this._fireRender(container);
  }

  // -----------------------------------------------------------------------
  // Schema cache

  async _fetchProps(label) {
    if (this.schemaCache[label]) return;
    try {
      const r = await fetch((window.SCIDK_BASE || '')
        + `/api/schema/property-types?label=${encodeURIComponent(label)}`);
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
      const r = await fetch((window.SCIDK_BASE || '') + '/api/schema/filter-preview', {
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
      // On an error there is no count and no query, and the only surfacing was
      // a string in a span sized for "Preview: 3 nodes". Hand the host the
      // error text so it can put it somewhere a user will read.
      if (this.options.onPreview) {
        if (d.error) this.options.onPreview(undefined, undefined, d.error);
        else this.options.onPreview(d.total, d.cypher);
      }
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
