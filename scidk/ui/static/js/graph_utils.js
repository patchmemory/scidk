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
