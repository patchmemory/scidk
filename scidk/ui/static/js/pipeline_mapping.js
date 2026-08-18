/**
 * The column mapping model — Cycle 3B Task D.
 *
 * Everything between "a schema and a stored mapping config" and "the mapping config
 * to save" lives here, with no DOM: `pipeline_mapping.html` owns rendering and
 * events, this owns the format. The split exists because of what the definition of
 * done actually asks for — that the page's output pass
 * `MappingEngine.validate()` unmodified — which is a property of *this* code. Kept
 * in the template it could only be checked by driving a browser; here it runs under
 * Node against the real engine (`tests/pipeline/mapping_model_harness.js`), the same
 * arrangement `graph_utils.js` has for the Arrows conversion.
 *
 * The format is `scidk/pipeline/mapping_schema.json`. Three of its properties shape
 * everything below:
 *
 * * A node mapping's `id` is a *role*. Two entries may share a `label`, and
 *   `relationship_mappings` reference entries by id — that is how one row produces
 *   both a PI and a submitter Person.
 * * The merge key is a property name, not a column. The key column is whichever
 *   column is assigned to the key property.
 * * `properties` and `source`/`property_map` are mutually exclusive forms
 *   (`oneOf`), so emitting a block means choosing one and deleting the other.
 *
 * **Nothing it cannot express is dropped.** A stored config carries things this page
 * has no field for — `row_filter`, `options`, `vocabulary_check`, a property
 * `fallback`, a transform reading the whole row instead of a column. Every one of
 * them round-trips: `buildConfig` starts from the stored object and replaces only
 * the two arrays it owns, and a property row it cannot represent is emitted exactly
 * as it came in. Opening the AIPT reference config and saving it again has to be a
 * no-op, or the page is a way to lose a deployment's configuration.
 */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.PipelineMapping = api;
}(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  /** A node mapping id, per mapping_schema.json. Looser than a Cypher identifier:
   *  it is never interpolated into a query, only matched against endpoints. */
  const ROLE_ID = /^[A-Za-z0-9_][A-Za-z0-9_.\-]*$/;

  /** The only config format version there is. */
  const VERSION = '1.0';

  /** Transform return kinds that need the source/property_map form rather than a
   *  single property: an object cannot be written into one Neo4j property. */
  const OBJECT_RETURNS = ['object', 'object_list'];

  let uidCounter = 0;

  // --------------------------------------------------------------- the schema

  /** Schema labels in document order, with the properties each declares. */
  function schemaLabels(schema) {
    const out = [];
    const seen = {};
    ((schema || {}).nodes || []).forEach(function (node) {
      const label = (node.labels || [])[0] || node.caption;
      if (!label || seen[label]) return;
      seen[label] = true;
      out.push({
        label: label,
        properties: Object.keys(node.properties || {}),
        key_property: node.key_property || null,
      });
    });
    return out;
  }

  /**
   * Schema relationships as (fromLabel, type, toLabel) triples.
   *
   * The index is part of the key so two edges that differ only in their Arrows ids
   * stay two rows. In schema space the label is the identity, so such a pair is
   * already a duplicate declaration — but silently collapsing them here would make
   * one of the user's edges vanish from the panel.
   */
  function schemaEdges(schema) {
    const byId = {};
    ((schema || {}).nodes || []).forEach(function (node) {
      byId[node.id] = (node.labels || [])[0] || node.caption;
    });
    return ((schema || {}).relationships || []).map(function (rel, index) {
      return {
        key: byId[rel.fromId] + '|' + rel.type + '|' + byId[rel.toId] + '|' + index,
        type: rel.type,
        fromLabel: byId[rel.fromId],
        toLabel: byId[rel.toId],
      };
    }).filter(function (edge) {
      return edge.fromLabel && edge.toLabel && edge.type;
    });
  }

  // ------------------------------------------------- mapping -> edit state

  /**
   * An empty role block for a label.
   *
   * The first role of a label is named after it, lowercased. A second one gets a
   * numbered name the user is expected to replace, because that name is what a
   * relationship points at — `person_2` says nothing, `pi` says which relationship
   * it should have.
   */
  function newRole(label, properties, keyProperty, existingRoles) {
    const taken = (existingRoles || []).map(function (r) { return r.id; });
    let id = String(label || 'role').toLowerCase();
    let n = 2;
    while (taken.indexOf(id) !== -1) { id = String(label).toLowerCase() + '_' + n; n += 1; }
    return {
      uid: 'role-' + (uidCounter += 1),
      id: id,
      label: label,
      form: 'properties',
      optional: false,
      keys: keyProperty ? [keyProperty] : [],
      cardinality: 'one',
      sourceColumn: '',
      sourceTransform: '',
      propertyMap: (properties || []).map(function (p) { return { from: p, to: p }; }),
      props: (properties || []).map(function (name) {
        return { name: name, column: '', transform: '', raw: null, advanced: false };
      }),
      schemaProperties: (properties || []).slice(),
      inSchema: true,
      raw: {},
    };
  }

  /** Build an editable role block from a stored `node_mappings` entry. */
  function roleFromMapping(entry, labels) {
    const label = String(entry.label || '');
    const declared = (labels || []).filter(function (l) { return l.label === label; })[0];
    const schemaProperties = declared ? declared.properties.slice() : [];
    const keys = Array.isArray(entry.key_property) ? entry.key_property.slice()
               : entry.key_property ? [String(entry.key_property)] : [];

    const stored = {};
    (entry.properties || []).forEach(function (spec) {
      if (spec && spec.name) stored[String(spec.name)] = spec;
    });
    const propertyMap = Object.keys(entry.property_map || {}).map(function (from) {
      return { from: from, to: String(entry.property_map[from]) };
    });

    // Every property name this block is about: the schema's, plus anything the
    // stored mapping names that the schema does not. The second half matters — a
    // schema edited after the mapping was written must not silently drop an
    // assignment to a property it no longer declares.
    const names = schemaProperties.slice();
    Object.keys(stored).forEach(function (n) {
      if (names.indexOf(n) === -1) names.push(n);
    });
    keys.forEach(function (k) { if (names.indexOf(k) === -1) names.push(k); });

    return {
      uid: 'role-' + (uidCounter += 1),
      id: String(entry.id || label.toLowerCase()),
      label: label,
      form: entry.source ? 'source' : 'properties',
      optional: !!entry.optional,
      keys: keys,
      cardinality: entry.cardinality === 'many' ? 'many' : 'one',
      sourceColumn: (entry.source || {}).column || '',
      sourceTransform: (entry.source || {}).transform || '',
      propertyMap: propertyMap.length ? propertyMap
                 : schemaProperties.map(function (p) { return { from: p, to: p }; }),
      props: names.map(function (name) {
        const spec = stored[name] || null;
        // A property with a transform and no column is the transform_args form —
        // `sp_colresolution` choosing between a _sp and an _orig column. This page
        // has no field for it (it is the out-of-scope column_resolution case), so
        // the row is shown as it is and emitted back byte for byte.
        return {
          name: name,
          column: spec ? (spec.column || '') : '',
          transform: spec ? (spec.transform || '') : '',
          raw: spec,
          advanced: !!(spec && !spec.column && spec.transform),
        };
      }),
      schemaProperties: schemaProperties,
      inSchema: !!declared,
      raw: entry,
    };
  }

  /**
   * The whole edit state for one source.
   *
   * Args:
   *   schema: the source's Arrows document (`schema_json`).
   *   mapping: the stored mapping config (`mapping_json`), or null.
   *
   * Returns:
   *   `{config, labels, edges, roles, rels, orphanRels}`. `config` is the stored
   *   object, kept whole so `buildConfig` can preserve what this page never edits.
   */
  function buildState(schema, mapping) {
    const config = mapping && typeof mapping === 'object' ? mapping : {};
    const labels = schemaLabels(schema);
    const edges = schemaEdges(schema);

    const roles = (config.node_mappings || [])
      .filter(function (entry) { return entry && typeof entry === 'object'; })
      .map(function (entry) { return roleFromMapping(entry, labels); });

    // A schema label with no role yet gets an empty one, so every target the schema
    // declares is visible as something to map rather than something to discover.
    labels.forEach(function (declared) {
      const has = roles.some(function (r) { return r.label === declared.label; });
      if (!has) {
        roles.push(newRole(declared.label, declared.properties,
                           declared.key_property, roles));
      }
    });

    const byId = {};
    roles.forEach(function (r) { byId[r.id] = r; });
    const stored = (config.relationship_mappings || [])
      .filter(function (rel) { return rel && typeof rel === 'object'; });
    const claimed = [];

    const rels = edges.map(function (edge) {
      const match = stored.filter(function (rel, index) {
        if (claimed.indexOf(index) !== -1) return false;
        const from = byId[rel.from];
        const to = byId[rel.to];
        return rel.type === edge.type && from && to
            && from.label === edge.fromLabel && to.label === edge.toLabel;
      })[0];
      if (match) claimed.push(stored.indexOf(match));
      return {
        key: edge.key,
        type: edge.type,
        fromLabel: edge.fromLabel,
        toLabel: edge.toLabel,
        include: !!match,
        from: match ? match.from : '',
        to: match ? match.to : '',
        raw: match || null,
      };
    });

    const state = {
      config: config,
      labels: labels,
      edges: edges,
      roles: roles,
      rels: rels,
      // A relationship the schema no longer describes is kept, not deleted: the
      // schema may have been edited after the mapping was written, and dropping it
      // silently would change what a run produces without saying so.
      orphanRels: stored.filter(function (rel, index) {
        return claimed.indexOf(index) === -1;
      }),
    };
    rels.forEach(function (rel) { autoSelectRoles(state, rel); });
    return state;
  }

  function rolesOf(state, label) {
    return state.roles.filter(function (r) { return r.label === label; });
  }

  /** Fill in either end that has exactly one candidate — nothing to choose. */
  function autoSelectRoles(state, rel) {
    const from = rolesOf(state, rel.fromLabel);
    const to = rolesOf(state, rel.toLabel);
    if (!rel.from && from.length === 1) rel.from = from[0].id;
    if (!rel.to && to.length === 1) rel.to = to[0].id;
  }

  // ------------------------------------------------- edit state -> mapping

  /** Whether a role block has anything worth storing. */
  function roleHasContent(role) {
    if (role.form === 'source') return !!role.sourceColumn;
    return role.props.some(function (p) { return p.advanced || p.column || p.transform; });
  }

  /**
   * One role block as a `node_mappings` entry.
   *
   * Emitted even when incomplete — a role with columns but no key produces an entry
   * the engine rejects, and that is the point: saving is allowed at any time, and
   * the validation report is where the user is told what is missing. Dropping the
   * block instead would lose the work and make the page look finished.
   */
  function emitRole(role) {
    const out = Object.assign({}, role.raw || {});
    out.id = role.id;
    out.label = role.label;
    delete out.properties;
    delete out.source;
    delete out.property_map;
    if (role.optional) out.optional = true; else delete out.optional;

    let declared = [];
    if (role.form === 'source') {
      const source = Object.assign({}, (role.raw || {}).source || {});
      source.column = role.sourceColumn;
      if (role.sourceTransform) source.transform = role.sourceTransform;
      else delete source.transform;
      out.source = source;
      out.property_map = {};
      role.propertyMap.forEach(function (entry) {
        if (entry.from && entry.to) out.property_map[entry.from] = entry.to;
      });
      // 'one' is the default, so it is only written when it was already written —
      // adding it to a config that omitted it would make reopening and saving a
      // stored mapping a change rather than a no-op.
      if (role.cardinality === 'many') out.cardinality = 'many';
      else if (!(role.raw || {}).cardinality) delete out.cardinality;
      else out.cardinality = 'one';
      declared = Object.keys(out.property_map).map(function (k) {
        return out.property_map[k];
      });
    } else {
      const properties = [];
      role.props.forEach(function (row) {
        if (row.advanced) { if (row.raw) properties.push(row.raw); return; }
        if (!row.column && !row.transform) return;
        const spec = Object.assign({}, row.raw || {});
        spec.name = row.name;
        if (row.column) spec.column = row.column; else delete spec.column;
        if (row.transform) spec.transform = row.transform; else delete spec.transform;
        properties.push(spec);
      });
      if (properties.length) out.properties = properties;
      // 'many' requires the source form: a column-per-property mapping can only
      // ever produce one node per row, and the schema rejects the combination. An
      // explicit 'one' from the stored config is left alone — not wrong, just the
      // default written out.
      if (out.cardinality === 'many') out.cardinality = 'one';
      declared = properties.map(function (p) { return p.name; });
    }

    // The key, and anything else naming a property, filtered to what this block
    // still declares — otherwise a property the user unassigned leaves behind a
    // key_property or skip_when_all_empty entry the engine rejects for naming
    // something that is no longer there.
    const keys = role.keys.filter(function (k) { return declared.indexOf(k) !== -1; });
    if (keys.length > 1) out.key_property = keys;
    else if (keys.length === 1) out.key_property = keys[0];
    else delete out.key_property;

    if (Array.isArray(out.skip_when_all_empty)) {
      const kept = out.skip_when_all_empty.filter(function (n) {
        return declared.indexOf(n) !== -1;
      });
      if (kept.length) out.skip_when_all_empty = kept;
      else delete out.skip_when_all_empty;
    }
    return out;
  }

  /**
   * The mapping config this state describes, ready for
   * `PUT /api/pipeline/sources/<id>/mapping`.
   *
   * Starts from the stored config and replaces only `node_mappings` and
   * `relationship_mappings`, so `options`, `row_filter`, `vocabulary_check`,
   * `source` and every `notes` in a hand-written config survive a save made here.
   */
  function buildConfig(state) {
    const config = Object.assign({}, state.config || {});
    config.version = config.version || VERSION;
    config.node_mappings = state.roles.filter(roleHasContent).map(emitRole);

    const known = {};
    config.node_mappings.forEach(function (entry) { known[entry.id] = true; });
    const rels = state.rels
      .filter(function (rel) { return rel.include && rel.from && rel.to; })
      .map(function (rel) {
        return Object.assign({}, rel.raw || {},
                             { type: rel.type, from: rel.from, to: rel.to });
      })
      .concat(state.orphanRels)
      // An endpoint whose role produced no node mapping would be a validation error
      // naming a node that is not declared. The relationship is simply not emitted;
      // the panel shows it as not yet mapped.
      .filter(function (rel) { return known[rel.from] && known[rel.to]; });
    if (rels.length) config.relationship_mappings = rels;
    else delete config.relationship_mappings;
    return config;
  }

  /** Where each column is used, as `column -> ["role.property", ...]`. */
  function columnUsage(roles) {
    const usage = {};
    function note(column, where) {
      if (!column) return;
      (usage[column] = usage[column] || []).push(where);
    }
    (roles || []).forEach(function (role) {
      if (role.form === 'source') {
        note(role.sourceColumn, role.id + ' (source)');
        return;
      }
      role.props.forEach(function (row) { note(row.column, role.id + '.' + row.name); });
    });
    return usage;
  }

  /**
   * Rename a role, moving every relationship endpoint that pointed at it.
   *
   * Returns a problem string, or null on success. Relationships reference a node
   * mapping by id, so a rename that did not carry them would silently break every
   * relationship the role was an endpoint of.
   */
  function renameRole(state, role, name) {
    if (!ROLE_ID.test(name)) {
      return '“' + name + '” is not a usable role name — letters, digits, dot, dash '
           + 'and underscore, and it cannot start with a dot or a dash.';
    }
    const clash = state.roles.some(function (r) { return r !== role && r.id === name; });
    if (clash) {
      return 'Another role is already called “' + name + '”. Relationships point at a '
           + 'role by name, so two roles cannot share one.';
    }
    const previous = role.id;
    role.id = name;
    state.rels.concat(state.orphanRels).forEach(function (rel) {
      if (rel.from === previous) rel.from = name;
      if (rel.to === previous) rel.to = name;
    });
    return null;
  }

  /** Remove a role, unhooking any relationship that used it as an endpoint. */
  function removeRole(state, role) {
    if (rolesOf(state, role.label).length <= 1) return false;
    state.roles = state.roles.filter(function (r) { return r !== role; });
    state.rels.forEach(function (rel) {
      if (rel.from === role.id) { rel.from = ''; rel.include = false; }
      if (rel.to === role.id) { rel.to = ''; rel.include = false; }
    });
    state.rels.forEach(function (rel) { autoSelectRoles(state, rel); });
    return true;
  }

  return {
    OBJECT_RETURNS: OBJECT_RETURNS,
    ROLE_ID: ROLE_ID,
    VERSION: VERSION,
    autoSelectRoles: autoSelectRoles,
    buildConfig: buildConfig,
    buildState: buildState,
    columnUsage: columnUsage,
    emitRole: emitRole,
    newRole: newRole,
    removeRole: removeRole,
    renameRole: renameRole,
    roleFromMapping: roleFromMapping,
    roleHasContent: roleHasContent,
    rolesOf: rolesOf,
    schemaEdges: schemaEdges,
    schemaLabels: schemaLabels,
  };
}));
