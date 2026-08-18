/**
 * SciDK Graph Utilities
 *
 * Shared Cytoscape.js configuration and helper functions for graph visualization
 * across chat.html, map.html, and schema map templates.
 */

window.SciDKGraph = {

  /**
   * Default node stylesheet for SciDK graphs
   */
  defaultNodeStyle: {
    selector: 'node',
    style: {
      'background-color': '#4e79a7',
      'label': 'data(label)',
      'color': '#333',
      'text-valign': 'center',
      'text-halign': 'center',
      'font-size': '11px',
      'text-outline-width': 2,
      'text-outline-color': '#fff',
      'width': 30,
      'height': 30,
      'border-width': 2,
      'border-color': '#fff',
      'text-wrap': 'ellipsis',
      'text-max-width': '100px'
      // Note: cursor and :hover not supported in Cytoscape
    }
  },

  /**
   * Default edge stylesheet for SciDK graphs
   * Uses hardcoded colors (edges don't have data.color field)
   */
  defaultEdgeStyle: {
    selector: 'edge',
    style: {
      'width': 2,
      'line-color': '#94a3b8',          // hardcoded color, not data mapping
      'target-arrow-color': '#94a3b8',  // hardcoded color, not data mapping
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      'label': 'data(label)',
      'font-size': '9px',
      'text-rotation': 'autorotate',
      'text-margin-y': -10,
      'color': '#666',
      'text-background-color': '#fff',
      'text-background-opacity': 0.8,
      'text-background-padding': '2px'
    }
  },

  /**
   * Build default stylesheet with optional overrides
   * @param {Array} additionalStyles - Additional style objects to merge
   * @returns {Array} Complete stylesheet array
   */
  buildStylesheet: function(additionalStyles = []) {
    return [
      this.defaultNodeStyle,
      this.defaultEdgeStyle,
      ...additionalStyles
    ];
  },

  /**
   * Standard layout configurations
   */
  layouts: {
    cose: {
      name: 'cose',
      animate: true,
      animationDuration: 1000,
      nodeRepulsion: 8000,
      idealEdgeLength: 100,
      nodeOverlap: 20,
      padding: 30
    },
    cola: {
      name: 'cola',
      animate: true,
      maxSimulationTime: 4000,
      nodeSpacing: 50,
      edgeLength: 100,
      padding: 30
    },
    preset: {
      name: 'preset'
    },
    circle: {
      name: 'circle',
      animate: true,
      animationDuration: 1000,
      padding: 30
    }
  },

  /**
   * Initialize a Cytoscape instance with SciDK defaults
   * @param {HTMLElement} container - DOM element to render graph in
   * @param {Array} elements - Cytoscape elements {nodes, edges}
   * @param {Object} options - Override options {style, layout, zoom, etc.}
   * @returns {Object} Cytoscape instance
   */
  init: function(container, elements = [], options = {}) {
    const config = {
      container: container,
      elements: elements,
      style: options.style || this.buildStylesheet(options.additionalStyles || []),
      layout: options.layout || this.layouts.cose,
      wheelSensitivity: options.wheelSensitivity || 0.2,
      minZoom: options.minZoom || 0.3,
      maxZoom: options.maxZoom || 3
    };

    // Check if Cytoscape is loaded
    if (typeof cytoscape === 'undefined') {
      console.error('Cytoscape.js not loaded. Make sure to include the library script.');
      return null;
    }

    return cytoscape(config);
  },

  /**
   * Convert Neo4j schema data to Cytoscape elements
   * Handles two formats:
   * 1. API format (already wrapped): {nodes: [{data: {id, label, ...}}], edges: [{data: {id, source, target, ...}}]}
   * 2. Raw format: {nodes: [{label, count, color}], edges: [{source, target, label}]}
   * @param {Object} schemaData - Schema data from API
   * @returns {Array} Cytoscape elements array
   */
  schemaToElements: function(schemaData) {
    // Check if data is already in Cytoscape format (has nested 'data' property)
    const firstNode = (schemaData.nodes || [])[0];
    if (firstNode && firstNode.data) {
      // Already in Cytoscape format, ensure label field exists in data
      const nodes = (schemaData.nodes || []).map(n => ({
        data: {
          ...n.data,
          label: n.data.label || n.data.name || n.data.id  // ensure label exists
        }
      }));
      const edges = schemaData.edges || [];
      return [...nodes, ...edges];
    }

    // Raw format - needs wrapping
    const nodes = (schemaData.nodes || []).map(n => ({
      data: {
        id: n.id || n.label || n.name,
        label: n.label || n.name || n.id,  // ensure label field exists
        count: n.count || 0,
        color: n.color || '#4e79a7',
        description: n.description || ''
      }
    }));

    const edges = (schemaData.edges || []).map((e, idx) => ({
      data: {
        id: e.id || `edge-${idx}`,
        source: e.source,
        target: e.target,
        label: e.label || e.type || ''
      }
    }));

    return [...nodes, ...edges];
  },

  /**
   * Convert Neo4j query results to Cytoscape elements
   * Expects format: {nodes: [{id, labels, properties}], rels: [{id, type, startNode, endNode}]}
   * @param {Object} queryResults - Query results with nodes and rels
   * @returns {Array} Cytoscape elements array
   */
  queryResultsToElements: function(queryResults) {
    const nodes = (queryResults.nodes || []).map(n => {
      const nodeId = this._extractId(n.id);
      const label = n.labels && n.labels[0] ? n.labels[0] : 'Node';
      const props = n.properties || {};

      // Try to find a display name from common properties
      const displayLabel = props.name || props.title || props.id || nodeId;

      return {
        data: {
          id: nodeId,
          label: label,
          displayLabel: displayLabel,
          properties: props
        }
      };
    });

    // Build set of valid node IDs for edge validation
    const nodeIds = new Set(nodes.map(n => n.data.id));

    // Only create edges where both source and target nodes exist
    const edges = (queryResults.rels || [])
      .map(r => {
        const edgeId = this._extractId(r.id);
        // Use fallback chain for Neo4j field name variations
        const sourceId = this._extractId(r.start_node || r.start || r.startNode || r.startNodeElementId);
        const targetId = this._extractId(r.end_node || r.end || r.endNode || r.endNodeElementId);

        return {
          edgeId,
          sourceId,
          targetId,
          data: {
            id: 'e' + edgeId,  // Prefix edge IDs to prevent collision with node IDs
            source: sourceId,
            target: targetId,
            label: r.type || ''
          }
        };
      })
      .filter(e => {
        // Skip edges with missing source or target nodes
        if (!nodeIds.has(e.sourceId) || !nodeIds.has(e.targetId)) {
          console.warn(`Skipping edge ${e.edgeId}: missing node (source: ${e.sourceId}, target: ${e.targetId})`);
          return false;
        }
        return true;
      })
      .map(e => ({ data: e.data }));  // Return only the data part

    // Deduplicate edges by ID (undirected queries return each edge twice)
    const edgeMap = new Map();
    edges.forEach(e => {
      if (!edgeMap.has(e.data.id)) {
        edgeMap.set(e.data.id, e);
      }
    });
    const uniqueEdges = Array.from(edgeMap.values());

    return [...nodes, ...uniqueEdges];
  },

  /**
   * Extract ID from Neo4j Integer format {low, high} or plain value
   * IMPORTANT: Handles 0 correctly (0 is a valid ID, not falsy check)
   * @param {*} val - Neo4j Integer or plain number/string
   * @returns {string} String representation of ID
   */
  _extractId: function(val) {
    // Handle undefined/null first
    if (val === undefined || val === null) {
      return '';
    }
    // Handle Neo4j Integer format { low, high }
    if (typeof val === 'object' && 'low' in val) {
      return val.low.toString();
    }
    // Handle plain number (including 0) or string
    return val.toString();
  },

  /**
   * Domain-specific color palette for common node types
   */
  colors: {
    folder: '#4a90e2',
    file: '#7bc67e',
    sample: '#f5a623',
    scan: '#9b59b6',
    sampleType: '#e74c3c',
    default: '#95a5a6'
  },

  /**
   * Generate node color styles for domain-specific labels
   * @param {Object} colorMap - Map of label -> color (defaults to SciDKGraph.colors)
   * @returns {Array} Style objects for each label
   */
  buildLabelColorStyles: function(colorMap = this.colors) {
    return Object.entries(colorMap).map(([label, color]) => ({
      selector: `node[label="${label.charAt(0).toUpperCase() + label.slice(1)}"]`,
      style: {
        'background-color': color
      }
    }));
  },

  /**
   * Generate node size function based on count (logarithmic scale)
   * @param {number} minSize - Minimum node size in pixels
   * @param {number} maxSize - Maximum node size in pixels
   * @returns {Function} Cytoscape size function
   */
  nodeSizeByCount: function(minSize = 30, maxSize = 80) {
    return function(ele) {
      const count = ele.data('count') || 1;
      return Math.max(minSize, Math.min(maxSize, minSize + Math.log10(count + 1) * 15));
    };
  },

  // ===========================================================================
  // SCHEMA SPACE (Cycle 3B Task C)
  //
  // A canvas element is either an *instance* (a real Neo4j entity) or a *schema*
  // element (a label type / relationship type). `data._space` says which, per the
  // element conventions in the Maps Canvas vision section of dev/cycles.md.
  //
  // These helpers live here rather than in the schema canvas template because
  // map.html also has to render schema elements distinctly: a canvas session can
  // hold both, and a schema node that looked like an instance node would be
  // actively misleading — one describes a rule, the other is data.
  // ===========================================================================

  SPACE_SCHEMA: 'schema',
  SPACE_INSTANCE: 'instance',

  /**
   * Stylesheet entries for schema-space elements: dashed border, muted fill,
   * type-chip label. Merge into any canvas that can show them.
   *
   * The label is read from `data(schemaLabel)` rather than composed in the
   * stylesheet, because Cytoscape has no way to render the label line and the
   * property line at different weights — schemaLabelFor() builds the text.
   */
  schemaStyles: [
    {
      selector: 'node[_space = "schema"]',
      style: {
        'shape': 'round-rectangle',
        'background-color': '#eef2f7',
        'background-opacity': 1,
        'border-width': 2,
        'border-style': 'dashed',
        'border-color': '#64748b',
        'label': 'data(schemaLabel)',
        'color': '#1e293b',
        'text-outline-width': 0,
        'text-valign': 'center',
        'text-halign': 'center',
        'text-wrap': 'wrap',
        'text-max-width': '180px',
        'font-size': '11px',
        'width': 'label',
        'height': 'label',
        'padding': '10px'
      }
    },
    {
      // Selected schema node: keep the dashed border, brighten it.
      selector: 'node[_space = "schema"]:selected',
      style: {
        'border-color': '#2563eb',
        'border-width': 3,
        'background-color': '#e0ecff'
      }
    },
    {
      selector: 'edge[_space = "schema"]',
      style: {
        'width': 2,
        'line-style': 'dashed',
        'line-color': '#64748b',
        'target-arrow-color': '#64748b',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'label': 'data(type)',
        'font-size': '10px',
        'color': '#334155',
        'text-background-color': '#fff',
        'text-background-opacity': 0.9,
        'text-background-padding': '2px',
        'text-rotation': 'autorotate'
      }
    },
    {
      selector: 'edge[_space = "schema"]:selected',
      style: { 'line-color': '#2563eb', 'target-arrow-color': '#2563eb', 'width': 3 }
    }
  ],

  /**
   * The type-chip label text for a schema node: the label in Cypher notation,
   * then its property names, with the key property marked.
   * @param {Object} data - Node data ({label, properties, key_property})
   * @returns {string}
   */
  schemaLabelFor: function(data) {
    const label = data.label || data.baseLabel || '(unnamed)';
    const props = this._propertyNames(data.properties);
    const key = data.key_property;
    const chips = props.map(p => (p === key ? '🔑 ' + p : p));
    return ':' + label + (chips.length ? '\n' + chips.join(' · ') : '');
  },

  /**
   * Property *names* from either representation. A schema node's properties are
   * names (a list, or an Arrows name->type object); an instance node's are values
   * (a name->value object). Both arrive here.
   * @param {Object|Array} properties
   * @returns {Array<string>}
   */
  _propertyNames: function(properties) {
    if (Array.isArray(properties)) {
      return properties.map(p => (p && typeof p === 'object' ? p.name : p))
                       .filter(Boolean).map(String);
    }
    if (properties && typeof properties === 'object') return Object.keys(properties);
    return [];
  },

  /**
   * Convert an Arrows.app document into schema-space Cytoscape elements.
   *
   * Node ids are label-keyed (`schema-Person`) rather than carried over from the
   * Arrows document, per the element conventions: in schema space the label *is*
   * the identity, so two Arrows nodes captioned "Person" describe one label type.
   * Their properties are merged and the collision is reported, rather than
   * silently keeping one of them — an Arrows document that does this is usually a
   * modelling slip worth telling the user about. (Two Person *roles* from one row
   * are a column-mapping concern, not a schema one.)
   *
   * @param {Object} arrows - A validated Arrows document ({nodes, relationships})
   * @param {Object} options - {width, height} of the target viewport for
   *   position normalization; pass null positions to skip it.
   * @returns {{elements: Array, warnings: Array<string>}}
   */
  arrowsToElements: function(arrows, options = {}) {
    const doc = arrows || {};
    const warnings = [];
    const byLabel = {};      // label -> element def
    const idByArrowsId = {}; // arrows node id -> cytoscape id
    const order = [];

    (doc.nodes || []).forEach((node, index) => {
      const label = (node.labels && node.labels[0]) || node.caption;
      if (!label) { warnings.push(`Node ${index + 1} has no label and was skipped.`); return; }
      const cyId = this.schemaNodeId(label);
      idByArrowsId[String(node.id)] = cyId;

      if (byLabel[label]) {
        // Merge: same label, one schema node.
        const existing = byLabel[label].data;
        const merged = existing.properties.slice();
        this._propertyNames(node.properties).forEach(p => {
          if (merged.indexOf(p) === -1) merged.push(p);
        });
        existing.properties = merged;
        existing.key_property = existing.key_property || node.key_property || null;
        existing.schemaLabel = this.schemaLabelFor(existing);
        warnings.push(`Two nodes are labelled "${label}"; they were merged into one ` +
                      `schema node.`);
        return;
      }

      const data = {
        id: cyId,
        label: String(label),
        baseLabel: String(label),
        _space: this.SPACE_SCHEMA,
        properties: this._propertyNames(node.properties),
        key_property: node.key_property || null,
        description: node.description || '',
        // Kept so an export can preserve the Arrows type strings it came in with.
        propertyTypes: (node.properties && !Array.isArray(node.properties))
          ? Object.assign({}, node.properties) : {}
      };
      data.schemaLabel = this.schemaLabelFor(data);
      byLabel[label] = {
        group: 'nodes',
        data: data,
        position: node.position ? { x: Number(node.position.x) || 0,
                                    y: Number(node.position.y) || 0 } : undefined,
        grabbable: true
      };
      order.push(label);
    });

    const edges = [];
    const seenEdges = {};
    (doc.relationships || []).forEach((rel, index) => {
      const source = idByArrowsId[String(rel.fromId)];
      const target = idByArrowsId[String(rel.toId)];
      const type = rel.type;
      if (!source || !target || !type) {
        warnings.push(`Relationship ${index + 1} has an endpoint that is not on the ` +
                      `canvas and was skipped.`);
        return;
      }
      const id = this.schemaEdgeId(source, type, target);
      if (seenEdges[id]) return;  // the same triple twice is the same rule
      seenEdges[id] = true;
      edges.push({
        group: 'edges',
        data: { id: id, source: source, target: target, type: String(type),
                relationship: String(type), baseType: String(type),
                label: String(type), _space: this.SPACE_SCHEMA }
      });
    });

    const nodes = order.map(label => byLabel[label]);
    if (options.width && options.height) {
      this.normalizeSchemaPositions(nodes, options.width, options.height);
    }
    return { elements: nodes.concat(edges), warnings: warnings };
  },

  /**
   * Serialize a Cytoscape instance's schema elements back to an Arrows document.
   *
   * The inverse of arrowsToElements, so an imported schema exports to something
   * arrows.app opens, and a schema built from scratch exports the same way.
   * Instance elements are excluded: an Arrows document describes types.
   *
   * @param {Object} cy - Cytoscape instance
   * @returns {Object} {nodes, relationships} in Arrows format
   */
  elementsToArrows: function(cy) {
    if (!cy) return { nodes: [], relationships: [] };
    const arrowsIdOf = {};
    const nodes = [];

    cy.nodes().forEach((n, index) => {
      if (n.data('_space') !== this.SPACE_SCHEMA) return;
      const label = n.data('baseLabel') || n.data('label');
      if (!label) return;
      const arrowsId = 'n' + index;
      arrowsIdOf[n.id()] = arrowsId;

      const types = n.data('propertyTypes') || {};
      const properties = {};
      this._propertyNames(n.data('properties')).forEach(name => {
        properties[name] = types[name] || 'String';
      });

      const node = {
        id: arrowsId,
        position: { x: Math.round(n.position('x')), y: Math.round(n.position('y')) },
        caption: String(label),
        labels: [String(label)],
        properties: properties,
        style: {}
      };
      // SciDK extensions arrows.app ignores; see scidk/pipeline/schema_arrows.py.
      if (n.data('key_property')) node.key_property = n.data('key_property');
      if (n.data('description')) node.description = n.data('description');
      nodes.push(node);
    });

    const relationships = [];
    cy.edges().forEach((e, index) => {
      if (e.data('_space') !== this.SPACE_SCHEMA) return;
      const from = arrowsIdOf[e.data('source')];
      const to = arrowsIdOf[e.data('target')];
      const type = e.data('type') || e.data('relationship') || e.data('label');
      if (!from || !to || !type) return;
      relationships.push({
        id: 'r' + index, type: String(type), fromId: from, toId: to,
        properties: {}, style: {}
      });
    });

    return { nodes: nodes, relationships: relationships };
  },

  /** Stable, label-keyed id for a schema node. */
  schemaNodeId: function(label) { return 'schema-' + label; },

  /** Stable id for a schema edge, so the same triple is never added twice. */
  schemaEdgeId: function(sourceId, type, targetId) {
    return sourceId + '-' + type + '->' + targetId;
  },

  /**
   * Rescale imported positions into the target viewport, in place.
   *
   * Arrows.app lays out in its own coordinate space — origin anywhere, span from
   * a few hundred to tens of thousands of units. Dropped into Cytoscape unchanged
   * the graph can land entirely outside the visible extent, and because
   * SciDKGraph.init clamps minZoom, fit() cannot always pull it back. Rescaling
   * preserves the designed layout (uniform scale, so nothing is distorted) while
   * guaranteeing every node is reachable.
   *
   * @param {Array} nodes - Element defs with .position
   * @param {number} width - Viewport width in px
   * @param {number} height - Viewport height in px
   */
  normalizeSchemaPositions: function(nodes, width, height) {
    const placed = nodes.filter(n => n.position);
    if (placed.length < 2) {
      // One node, or none positioned: centre what there is.
      placed.forEach(n => { n.position = { x: width / 2, y: height / 2 }; });
      return;
    }
    const xs = placed.map(n => n.position.x);
    const ys = placed.map(n => n.position.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const spanX = maxX - minX, spanY = maxY - minY;

    // Room for the node boxes themselves, which the positions (centres) ignore.
    const margin = 90;
    const targetW = Math.max(width - margin * 2, 200);
    const targetH = Math.max(height - margin * 2, 200);
    const scale = Math.min(
      spanX > 0 ? targetW / spanX : Infinity,
      spanY > 0 ? targetH / spanY : Infinity,
      1.5  // never blow up a compact design
    );
    const offsetX = margin + (targetW - spanX * (scale === Infinity ? 0 : scale)) / 2;
    const offsetY = margin + (targetH - spanY * (scale === Infinity ? 0 : scale)) / 2;

    placed.forEach(n => {
      const s = (scale === Infinity) ? 1 : scale;
      n.position = {
        x: offsetX + (n.position.x - minX) * s,
        y: offsetY + (n.position.y - minY) * s
      };
    });
  },

  /**
   * Wait for Cytoscape library to load
   * @param {Function} callback - Function to call when loaded
   * @param {number} timeout - Max time to wait in ms (default 5000)
   */
  waitForLoad: function(callback, timeout = 5000) {
    const startTime = Date.now();
    const checkInterval = 100;

    const check = () => {
      if (typeof cytoscape !== 'undefined') {
        callback();
      } else if (Date.now() - startTime < timeout) {
        setTimeout(check, checkInterval);
      } else {
        console.error('Cytoscape.js failed to load within timeout');
      }
    };

    check();
  }
};
