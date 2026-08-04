/**
 * Drives the column mapping model (pipeline_mapping.js) under bare Node.
 *
 * The acceptance criterion for Task D is that what the mapping page emits passes
 * ``MappingEngine.validate()`` unmodified — a property of browser code. So the
 * browser code is what runs here, and the Python side feeds its output to the real
 * engine. A Python reimplementation of ``buildConfig`` could agree with itself and
 * disagree with the page, which is the failure this arrangement exists to prevent.
 * Same shape as ``schema_space_harness.js``.
 *
 * Usage: node mapping_model_harness.js <path to pipeline_mapping.js> < input.json
 *   input:  {schema, mapping, edits: [<edit>, ...]}
 *   output: {config, roles: [{id, label, form, keys, hasContent}], rels, orphanRels}
 *
 * An edit is one of:
 *   {op: 'assign',    role, property, column, transform}
 *   {op: 'key',       role, property}
 *   {op: 'optional',  role, value}
 *   {op: 'form',      role, value}            'properties' | 'source'
 *   {op: 'source',    role, column, transform, cardinality}
 *   {op: 'map',       role, entries: [{from, to}]}
 *   {op: 'addRole',   label}
 *   {op: 'rename',    role, name}
 *   {op: 'removeRole', role}
 *   {op: 'rel',       type, from, to, include}
 */
'use strict';

const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(process.argv[2], 'utf8');
const sandbox = { window: {}, console: console };
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const M = sandbox.window.PipelineMapping;

const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const state = M.buildState(input.schema, input.mapping);
const problems = [];

function roleById(id) {
  const found = state.roles.filter((r) => r.id === id)[0];
  if (!found) throw new Error(`no role called ${id}; have ` +
                             state.roles.map((r) => r.id).join(', '));
  return found;
}

function propOf(role, name) {
  const found = role.props.filter((p) => p.name === name)[0];
  if (!found) throw new Error(`role ${role.id} has no property ${name}`);
  return found;
}

(input.edits || []).forEach((edit) => {
  if (edit.op === 'assign') {
    const row = propOf(roleById(edit.role), edit.property);
    if ('column' in edit) row.column = edit.column;
    if ('transform' in edit) row.transform = edit.transform;
    return;
  }
  if (edit.op === 'key') {
    const role = roleById(edit.role);
    role.keys = edit.property
      ? [edit.property].concat(role.keys.slice(1).filter((k) => k !== edit.property))
      : [];
    return;
  }
  if (edit.op === 'optional') { roleById(edit.role).optional = !!edit.value; return; }
  if (edit.op === 'form') { roleById(edit.role).form = edit.value; return; }
  if (edit.op === 'source') {
    const role = roleById(edit.role);
    if ('column' in edit) role.sourceColumn = edit.column;
    if ('transform' in edit) role.sourceTransform = edit.transform;
    if ('cardinality' in edit) role.cardinality = edit.cardinality;
    return;
  }
  if (edit.op === 'map') { roleById(edit.role).propertyMap = edit.entries; return; }
  if (edit.op === 'addRole') {
    const declared = state.labels.filter((l) => l.label === edit.label)[0];
    state.roles.push(M.newRole(edit.label, declared ? declared.properties : [],
                               declared ? declared.key_property : null, state.roles));
    return;
  }
  if (edit.op === 'rename') {
    const problem = M.renameRole(state, roleById(edit.role), edit.name);
    if (problem) problems.push(problem);
    return;
  }
  if (edit.op === 'removeRole') { M.removeRole(state, roleById(edit.role)); return; }
  if (edit.op === 'rel') {
    const rel = state.rels.filter((r) => r.type === edit.type)[0];
    if (!rel) throw new Error(`no schema relationship of type ${edit.type}`);
    if ('from' in edit) rel.from = edit.from;
    if ('to' in edit) rel.to = edit.to;
    rel.include = 'include' in edit ? !!edit.include : true;
    return;
  }
  throw new Error(`unknown edit op ${edit.op}`);
});

process.stdout.write(JSON.stringify({
  config: M.buildConfig(state),
  problems: problems,
  labels: state.labels,
  roles: state.roles.map((r) => ({
    id: r.id, label: r.label, form: r.form, keys: r.keys, inSchema: r.inSchema,
    hasContent: M.roleHasContent(r),
    props: r.props.map((p) => ({ name: p.name, column: p.column,
                                 transform: p.transform, advanced: p.advanced })),
  })),
  rels: state.rels.map((r) => ({ type: r.type, fromLabel: r.fromLabel,
                                 toLabel: r.toLabel, from: r.from, to: r.to,
                                 include: r.include })),
  orphanRels: state.orphanRels,
  usage: M.columnUsage(state.roles),
}));
