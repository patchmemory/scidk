/* Shared Maps Canvas draft primitives. No persistence, network or graph commit. */
window.SciDKCanvas = {
  provisionalNode(cy, label, name) {
    const ext = cy.extent();
    return {
      group: 'nodes', data: {id: 'prov-' + Math.random().toString(36).slice(2, 10), label, baseLabel: label,
        displayLabel: name, properties: {name}, provisional: true},
      position: {x: (ext.x1 + ext.x2) / 2 + (Math.random() - 0.5) * 120,
        y: (ext.y1 + ext.y2) / 2 + (Math.random() - 0.5) * 120}, grabbable: true
    };
  },
  add(cy, definition, undo) { if (undo) undo.do('add', definition); else cy.add(definition); },
  remove(cy, undo) {
    const selected = cy.$(':selected');
    if (selected.nonempty()) { if (undo) undo.do('remove', selected); else selected.remove(); }
  },
  provisionalEdge(source, target, label) {
    return {group: 'edges', data: {id: 'prov-' + Math.random().toString(36).slice(2, 10), source, target,
      label, baseLabel: label, provisional: true}};
  }
};
