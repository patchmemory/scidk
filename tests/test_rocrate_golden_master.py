"""Golden masters for the canvas RO-Crate export (Cycle 7, Task A).

``generate_rocrate_export()`` shipped in canvas Push 4 with no test of its own,
and Cycle 7 turns it into a thin wrapper over ``scidk.rocrate_bridge``. This file
pins its output *byte for byte* before that refactor, so the bridge has to prove
it produces the same document rather than merely a plausible one.

Each fixture pair in ``tests/fixtures/rocrate/`` is one snapshot and the exact
JSON text the export produced for it:

``empty``
    No nodes, no edges. A root Dataset with an empty ``hasPart`` is a valid
    crate, and "valid but empty" is the answer, not an error.
``provisional_only``
    Nothing committed yet, so every ``@id`` is the generated ``#<uuid5>`` form —
    which is what makes re-exporting a canvas stable. Also covers all three edge
    mappings (``CONTAINS``/``ATTACHED_TO``/other), a node with no name, and an
    edge pointing off-canvas.
``multi_parent``
    The case RO-Crate exists to handle: one child in two parents' ``hasPart``,
    and absent from the root's, because it is not top level.
``mixed``
    Committed nodes (Neo4j ``element_id`` as ``@id``) beside provisional ones in
    one crate.
``schema_space``
    A ``_space: "schema"`` element must not reach the crate at all: its
    ``properties`` is a list of names, so it used to raise on ``.items()``.

Regenerating: these files are the record of pre-refactor behaviour. If a change
is *meant* to alter the output, rewrite them in the same commit and say why in
the message — do not regenerate to make a red test go green.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).with_name('fixtures') / 'rocrate'

#: Fixture stems, so a missing pair fails loudly instead of silently reducing
#: coverage the way a bare glob would.
CASES = ['empty', 'mixed', 'multi_parent', 'provisional_only', 'schema_space']


def load_case(name: str):
    payload = json.loads((FIXTURES / f'{name}.snapshot.json').read_text(encoding='utf-8'))
    expected = (FIXTURES / f'{name}.expected.json').read_text(encoding='utf-8')
    return payload['snapshot'], payload['layer_name'], expected


@pytest.mark.parametrize('name', CASES)
def test_canvas_export_output_is_unchanged(name):
    from scidk.services.canvas_service import generate_rocrate_export

    snapshot, layer_name, expected = load_case(name)

    assert generate_rocrate_export(snapshot, layer_name) + '\n' == expected


@pytest.mark.parametrize('name', CASES)
def test_every_golden_master_is_a_valid_crate(name):
    """The fixtures are RO-Crate 1.1, not just some JSON we happened to emit."""
    _, layer_name, expected = load_case(name)
    doc = json.loads(expected)

    assert doc['@context'] == 'https://w3id.org/ro/crate/1.1/context'
    graph = doc['@graph']

    descriptor = graph[0]
    assert descriptor['@id'] == 'ro-crate-metadata.json'
    assert descriptor['@type'] == 'CreativeWork'
    assert descriptor['conformsTo'] == {'@id': 'https://w3id.org/ro/crate/1.1'}
    assert descriptor['about'] == {'@id': './'}

    root = graph[1]
    assert root['@id'] == './'
    assert root['@type'] == 'Dataset'
    assert root['name'] == layer_name

    # Every reference resolves to an entity in the same graph. A dangling @id is
    # the failure mode a hand-rolled serializer has, so it is worth asserting.
    ids = {entity['@id'] for entity in graph}
    for entity in graph:
        for key in ('hasPart', 'mentions', 'relation'):
            for ref in entity.get(key) or []:
                assert ref['@id'] in ids, f'{name}: dangling {key} -> {ref["@id"]}'


def test_multi_parent_child_belongs_to_both_parents():
    """Named separately because it is the property the whole format buys us."""
    _, _, expected = load_case('multi_parent')
    graph = json.loads(expected)['@graph']
    by_id = {entity['@id']: entity for entity in graph}

    child = '4:aipt:12'
    parents = [
        entity['@id'] for entity in graph
        if any(ref['@id'] == child for ref in entity.get('hasPart') or [])
    ]
    assert parents == ['4:aipt:10', '4:aipt:11']
    # ...and it is not top level, so the root does not list it.
    assert all(ref['@id'] != child for ref in by_id['./']['hasPart'])


def test_the_schema_element_never_becomes_an_entity():
    _, _, expected = load_case('schema_space')

    assert 'schema-Sample' not in expected
    assert 'treatment' not in expected
