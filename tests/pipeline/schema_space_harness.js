/**
 * Exercises the schema-space bridge in graph_utils.js under bare Node.
 *
 * The Arrows <-> Cytoscape conversion is where round-trip fidelity actually
 * lives, and it is browser code — so it is tested by running it, not by a Python
 * reimplementation that could agree with itself while disagreeing with the page.
 *
 * Usage: node schema_space_harness.js <path to graph_utils.js> < input.json
 *   input:  {arrows: <arrows document>, options: {width, height}}
 *   output: {elements, warnings, arrows}
 */
'use strict';

const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(process.argv[2], 'utf8');
const sandbox = { window: {}, console: console };
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const G = sandbox.window.SciDKGraph;

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const converted = G.arrowsToElements(input.arrows, input.options || {});

// Minimal Cytoscape stand-in: just enough of the collection API for
// elementsToArrows, which only ever reads ids, data and positions.
function collection(items) {
  return { forEach: (fn) => items.forEach((el, i) => fn(el, i)) };
}

function wrap(def) {
  return {
    id: () => def.data.id,
    data: (key) => def.data[key],
    position: (axis) => (def.position ? def.position[axis] : 0),
  };
}

const cy = {
  nodes: () => collection(converted.elements.filter((e) => e.group === 'nodes').map(wrap)),
  edges: () => collection(converted.elements.filter((e) => e.group === 'edges').map(wrap)),
};

process.stdout.write(JSON.stringify({
  elements: converted.elements,
  warnings: converted.warnings,
  arrows: G.elementsToArrows(cy),
}));
