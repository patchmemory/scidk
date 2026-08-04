"""The NIH DMS plan generator (Cycle 7, Task C).

Three things carry most of the risk, and each gets direct tests.

**The plan must never be fiction.** The whole point of generating rather than
templating is that the numbers are real, so an unreachable graph has to produce an
error and not a plausible-looking document. There are tests that no plan comes
back when Neo4j is absent, and that the error says what to do about it.

**PHI detection must fire.** A missed identifier warning is the expensive failure:
it puts a claim in a grant application that nobody checked. Detection is tested
from both sources (live property names and the curated schema layer), across
spelling variants, and — separately — that a key-store-only match is reported as
the weaker signal it is rather than as live PHI.

**Access must degrade honestly.** ``label_profile.sharing_modes`` does not exist
until Cycle 9 Task A, so the generator has to tell "column not there yet" apart
from "there and empty", and say something useful in both cases.

The fake graph answers the module's real Cypher over a small node/relationship
list rather than returning canned rows, so a mistake in a query — a predicate that
matches the wrong thing, an aggregate over the wrong scope — fails here.
"""
from __future__ import annotations

import json
import re
import sqlite3

import pytest

from plugins.nih_dms import config as cfg
from plugins.nih_dms import routes as dms_routes
from plugins.nih_dms.generator import human_bytes, render_plan
from plugins.nih_dms.graph_facts import GraphUnavailable, collect_facts
from scidk.app import create_app
from scidk.services.schema_intelligence import ensure_schema_intelligence_tables

# --------------------------------------------------------------- fake graph

#: A small imaging collection: two labels with files, a sample, and an assay
#: recorded on the relationship — the shape the AIPT graph actually has.
NODES = [
    {'labels': ['File'], 'properties': {
        'path': '/data/s1/img_001.dcm', 'extension': '.DCM',
        'size_bytes': 2048, 'mime_type': 'application/dicom'}},
    {'labels': ['File'], 'properties': {
        'path': '/data/s1/img_002.dcm', 'extension': '.dcm',
        'size_bytes': 1024, 'mime_type': 'application/dicom'}},
    {'labels': ['File'], 'properties': {
        'path': '/data/s1/notes.txt', 'extension': '.txt', 'size_bytes': 512}},
    {'labels': ['File'], 'properties': {
        'path': '/data/s1/blob.qqq', 'extension': '.qqq', 'size_bytes': 64}},
    {'labels': ['Folder'], 'properties': {'path': '/data/s1'}},
    {'labels': ['Sample'], 'properties': {'uuid': 's1', 'modality': 'Histology'}},
    {'labels': ['Sample'], 'properties': {'uuid': 's2', 'modality': 'Flow cytometry'}},
    {'labels': ['Dataset'], 'properties': {'name': 'run A', 'type': 'ImageSequence'}},
]

RELATIONSHIPS = [
    {'type': 'CONTAINS', 'properties': {}},
    {'type': 'CONTAINS', 'properties': {}},
    {'type': 'DERIVED_FROM', 'properties': {'internal_assay_title': 'Imaging Analysis'}},
    {'type': 'DERIVED_FROM', 'properties': {'internal_assay_title': 'Genome Alignment'}},
]


class FakeGraph:
    """Answers the fact collector's Cypher over ``nodes`` / ``relationships``.

    Deliberately not a stub that returns fixed rows per call: it parses the label,
    property and aggregate out of each query and computes the answer, so the
    queries are under test too.
    """

    def __init__(self, nodes=NODES, relationships=RELATIONSHIPS,
                 property_keys=None, fail_on=()):
        self.nodes = [dict(n) for n in nodes]
        self.relationships = [dict(r) for r in relationships]
        #: Override the key store; defaults to every key in use. Set it explicitly
        #: to model a key whose last node was deleted.
        self._property_keys = property_keys
        #: Substrings whose matching query should raise, to exercise degradation.
        self.fail_on = tuple(fail_on)
        self.queries: list[str] = []
        self.closed = False

    # ---- helpers

    def close(self):
        self.closed = True

    def _keys(self):
        if self._property_keys is not None:
            return list(self._property_keys)
        keys: list[str] = []
        for item in self.nodes + self.relationships:
            for key in item['properties']:
                if key not in keys:
                    keys.append(key)
        return keys

    def _nodes_with_label(self, label):
        return [n for n in self.nodes if label in n['labels']]

    @staticmethod
    def _group(pairs):
        """``[(value, ...)] -> [{'v': value, 'c': count}]``, commonest first."""
        counts: dict = {}
        for value in pairs:
            counts[value] = counts.get(value, 0) + 1
        return [
            {'v': value, 'c': count}
            for value, count in sorted(counts.items(), key=lambda kv: (-kv[1], str(kv[0])))
        ]

    # ---- the query interface the collector uses

    def execute_read(self, query, parameters=None):
        self.queries.append(query)
        for fragment in self.fail_on:
            if fragment in query:
                raise RuntimeError(f'simulated failure for {fragment}')

        if query.strip() == 'RETURN 1 AS ok':
            return [{'ok': 1}]

        if 'db.labels()' in query:
            labels: list[str] = []
            for node in self.nodes:
                for label in node['labels']:
                    if label not in labels:
                        labels.append(label)
            return [{'label': label} for label in labels]

        if 'db.relationshipTypes()' in query:
            types: list[str] = []
            for rel in self.relationships:
                if rel['type'] not in types:
                    types.append(rel['type'])
            return [{'relationshipType': t} for t in types]

        if 'db.propertyKeys()' in query:
            return [{'propertyKey': key} for key in self._keys()]

        if 'db.schema.nodeTypeProperties()' in query:
            rows = []
            for node in self.nodes:
                for key in node['properties']:
                    row = {'nodeLabels': list(node['labels']), 'propertyName': key}
                    if row not in rows:
                        rows.append(row)
            return rows

        if 'db.schema.relTypeProperties()' in query:
            rows = []
            for rel in self.relationships:
                for key in rel['properties']:
                    row = {'relType': f":`{rel['type']}`", 'propertyName': key}
                    if row not in rows:
                        rows.append(row)
            return rows

        # Count store: MATCH (n:`Label`) RETURN count(n) AS c
        match = re.search(r'MATCH \(n:`(\w+)`\) RETURN count\(n\)', query)
        if match:
            return [{'c': len(self._nodes_with_label(match.group(1)))}]

        # Count store: MATCH ()-[r:`TYPE`]->() RETURN count(r) AS c
        match = re.search(r'MATCH \(\)-\[r:`(\w+)`\]->\(\) RETURN count\(r\)', query)
        if match:
            rel_type = match.group(1)
            return [{'c': len([r for r in self.relationships if r['type'] == rel_type])}]

        # The single file scan, grouped by (extension, mime_type).
        if 'AS ext' in query and 'AS mime' in query:
            files = self._nodes_with_label('File')
            limit = re.search(r'LIMIT (\d+)', query)
            if limit:
                files = files[:int(limit.group(1))]
            groups: dict = {}
            for node in files:
                props = node['properties']
                key = (str(props.get('extension') or '').lower(), props.get('mime_type'))
                entry = groups.setdefault(key, [0, 0])
                entry[0] += 1
                entry[1] += int(props.get('size_bytes') or 0)
            return [
                {'ext': ext, 'mime': mime, 'c': count, 'b': size}
                for (ext, mime), (count, size) in groups.items()
            ]

        # Distinct values of a relationship property.
        match = re.search(r'MATCH \(\)-\[x:`(\w+)`\]->\(\).*x\.`(\w+)`', query, re.S)
        if match:
            rel_type, prop = match.group(1), match.group(2)
            return self._group([
                r['properties'][prop] for r in self.relationships
                if r['type'] == rel_type and r['properties'].get(prop) is not None
            ])

        # Distinct values of a node property.
        match = re.search(r'MATCH \(x:`(\w+)`\).*x\.`(\w+)`', query, re.S)
        if match:
            label, prop = match.group(1), match.group(2)
            return self._group([
                n['properties'][prop] for n in self._nodes_with_label(label)
                if n['properties'].get(prop) is not None
            ])

        raise AssertionError(f'unexpected query: {query}')


# ------------------------------------------------------------- SQLite fixture


@pytest.fixture
def settings_db(tmp_path):
    """A real ``scidk_settings.db`` with the Schema Intelligence tables."""
    conn = sqlite3.connect(str(tmp_path / 'settings.db'))
    ensure_schema_intelligence_tables(conn)
    yield conn
    conn.close()


def add_profile(conn, label, always=None, never=None, sharing=None):
    """Insert a ``label_profile`` row, adding ``sharing_modes`` if asked for.

    The column arrives in Cycle 9 Task A, so a test that wants it has to create it
    — which is exactly the state the generator has to cope with either way.
    """
    if sharing is not None:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(label_profile)')}
        if 'sharing_modes' not in columns:
            conn.execute('ALTER TABLE label_profile ADD COLUMN sharing_modes TEXT')

    conn.execute(
        'INSERT INTO label_profile (label_name, always_include, never_include) VALUES (?, ?, ?)',
        (label, json.dumps(always) if always else None,
         json.dumps(never) if never else None),
    )
    if sharing is not None:
        conn.execute('UPDATE label_profile SET sharing_modes = ? WHERE label_name = ?',
                     (json.dumps(sharing), label))
    conn.commit()


def plan(graph=None, conn=None, **kwargs):
    """Collect facts and render, in one step."""
    facts = collect_facts(graph if graph is not None else FakeGraph(), conn, **kwargs)
    return render_plan(facts, generated_at='2026-08-04 00:00 UTC')


# ============================================================ real data only


def test_no_graph_is_an_error_not_an_empty_plan():
    """The one thing this plugin must never do is invent a plan."""
    with pytest.raises(GraphUnavailable) as excinfo:
        collect_facts(None)

    assert 'Settings' in str(excinfo.value)


def test_an_unreachable_graph_is_an_error_not_an_empty_plan():
    class Broken:
        def execute_read(self, query, parameters=None):
            raise RuntimeError('connection refused')

    with pytest.raises(GraphUnavailable) as excinfo:
        collect_facts(Broken())

    assert 'connection refused' in str(excinfo.value)


def test_the_plan_reports_real_counts_from_the_graph():
    facts = collect_facts(FakeGraph())

    assert dict(facts.label_counts) == {
        'File': 4, 'Folder': 1, 'Sample': 2, 'Dataset': 1}
    assert dict(facts.relationship_counts) == {'CONTAINS': 2, 'DERIVED_FROM': 2}
    assert facts.file_count == 4
    assert facts.file_bytes == 2048 + 1024 + 512 + 64

    text = render_plan(facts, generated_at='2026-08-04 00:00 UTC')
    # Every one of those numbers reaches the document.
    assert '| `File` | 4 |' in text
    assert '| `Sample` | 2 |' in text
    assert '`CONTAINS` (2)' in text
    assert '3.56 KiB' in text  # 3648 bytes


def test_extensions_are_folded_to_one_format_regardless_of_case():
    """``.DCM`` and ``.dcm`` are the same format; counting them apart overstates."""
    facts = collect_facts(FakeGraph())

    dicom = [row for row in facts.formats if row.extension == '.dcm']
    assert len(dicom) == 1
    assert dicom[0].count == 2
    assert dicom[0].bytes == 3072
    assert dicom[0].format_name == 'DICOM'
    assert '.DCM' not in {row.extension for row in facts.formats}


def test_an_unknown_extension_is_flagged_not_guessed_at():
    text = plan()

    assert '`.qqq`' in text
    assert 'not in SciDK\'s format registry' in text


def test_totals_cover_every_file_not_only_the_reported_formats(monkeypatch):
    """The byte and file totals are sums over all groups, not the top-N subtotal.

    Regression guard: computing them from the truncated format list would silently
    understate how much data the lab holds, which is the number a reviewer reads
    first.
    """
    monkeypatch.setattr(cfg, 'MAX_FORMATS', 1)
    facts = collect_facts(FakeGraph())

    assert len(facts.formats) == 1
    assert facts.formats_truncated is True
    assert facts.file_count == 4                       # not 2
    assert facts.file_bytes == 2048 + 1024 + 512 + 64  # not 3072


def test_mime_coverage_is_reported_from_the_aggregate_not_the_top_values():
    facts = collect_facts(FakeGraph())

    # Two of the four files declare a media type.
    assert facts.mime_known == 2
    assert facts.mime_types == (('application/dicom', 2),)


# ==================================================================== PHI


PHI_NODES = NODES + [
    {'labels': ['Subject'], 'properties': {
        'patient_id': 'MRN-0001', 'name': 'anon'}},
]


def test_phi_flag_fires_on_a_live_property_name():
    facts = collect_facts(FakeGraph(nodes=PHI_NODES))

    assert facts.has_phi is True
    assert [(h.property_name, h.location, h.evidence) for h in facts.confirmed_phi_hits] == [
        ('patient_id', 'Subject', 'graph')]

    text = render_plan(facts, generated_at='2026-08-04 00:00 UTC')
    assert 'Potentially identifiable data detected' in text
    assert '`patient_id` — on Subject' in text
    assert '45 CFR 164.514' in text          # the de-identification standard
    assert 'Data Access Committee' in text
    # Element 5 must also refuse to be left blank.
    assert 'This subsection cannot be left as a placeholder' in text


@pytest.mark.parametrize('spelling', [
    'patient_id', 'patientId', 'PatientID', 'Patient Id',
    'subject_name', 'patient_name', 'mrn', 'MRN',
    'date_of_birth', 'dateOfBirth', 'dob', 'DOB',
])
def test_phi_detection_survives_the_spellings_a_real_graph_mixes(spelling):
    nodes = [{'labels': ['Subject'], 'properties': {spelling: 'x'}}]

    facts = collect_facts(FakeGraph(nodes=nodes, relationships=[]))

    assert facts.has_phi is True, f'{spelling} was not detected'
    assert facts.confirmed_phi_hits[0].property_name == spelling


def test_phi_flag_fires_from_the_curated_schema_layer(settings_db):
    """A property named in ``label_profile`` counts even if the node scan is thin."""
    add_profile(settings_db, 'Subject', always=['patient_name', 'age'])

    facts = collect_facts(FakeGraph(), settings_db)

    assert facts.has_phi is True
    hit = facts.confirmed_phi_hits[0]
    assert hit.property_name == 'patient_name'
    assert hit.evidence == 'label_profile'

    text = render_plan(facts, generated_at='2026-08-04 00:00 UTC')
    assert 'Potentially identifiable data detected' in text
    assert '`patient_name` — on schema layer' in text


def test_a_phi_property_on_a_relationship_is_detected():
    rels = [{'type': 'TREATED', 'properties': {'mrn': '123'}}]

    facts = collect_facts(FakeGraph(relationships=rels))

    assert [h.location for h in facts.confirmed_phi_hits] == ['[:TREATED] relationship']


def test_a_key_store_only_match_is_the_weaker_signal_not_live_phi():
    """A key whose last node was deleted must not read as identifiers held now."""
    graph = FakeGraph(property_keys=['path', 'extension', 'size_bytes', 'patient_id'])

    facts = collect_facts(graph)

    assert facts.has_phi is True             # still worth surfacing
    assert facts.confirmed_phi_hits == ()    # but not as live data
    assert facts.phi_hits[0].evidence == 'property_key_store'

    text = render_plan(facts, generated_at='2026-08-04 00:00 UTC')
    assert 'property key store' in text
    assert 'has since\nbeen deleted' in text or 'has since been deleted' in text
    # The prescriptive consequences belong to confirmed PHI only.
    assert '45 CFR 164.514' not in text


def test_a_clean_scan_does_not_claim_the_data_are_deidentified():
    """The absence of a match is not a finding, and the plan has to say so."""
    text = plan()

    assert 'Potentially identifiable data detected' not in text
    assert 'This is not a finding that the data are de-identified' in text
    assert 'IRB' in text


def test_phi_detection_reads_a_configurable_list():
    """Widening detection is a config change, not a code change."""
    assert 'dob' in cfg.PHI_PROPERTY_NAMES
    for name in cfg.PHI_PROPERTY_NAMES:
        assert cfg.canonical_property(name) in cfg.PHI_CANONICAL


# =============================================================== modalities


def test_modalities_come_from_the_graph_including_relationship_properties():
    """AIPT records the assay on an edge, so edge properties have to be read."""
    facts = collect_facts(FakeGraph(), deep=True)

    sources = {finding.source for finding in facts.modalities}
    assert 'DERIVED_FROM.internal_assay_title' in sources
    assert 'Sample.modality' in sources

    text = render_plan(facts, generated_at='2026-08-04 00:00 UTC')
    assert 'Imaging Analysis' in text
    assert 'Genome Alignment' in text
    assert 'Histology' in text


def test_no_modality_property_produces_a_prompt_not_invented_prose():
    nodes = [{'labels': ['File'], 'properties': {'extension': '.txt', 'size_bytes': 1}}]

    text = plan(FakeGraph(nodes=nodes, relationships=[]))

    assert 'No property naming a measurement modality or assay was found' in text
    assert '[NAME THE IMAGING MODALITIES' in text


def test_collection_profiles_survive_the_node_schema_shortcut():
    """``Dataset.type`` is config-scoped, so it must not depend on schema discovery.

    Regression guard: when the shortcut skips the per-label property scan, the
    dataset structure statement was silently lost.
    """
    facts = collect_facts(FakeGraph())

    assert facts.collection_profiles, 'Dataset.type was dropped'
    assert facts.collection_profiles[0].source == 'Dataset.type'
    assert 'ImageSequence' in render_plan(facts, generated_at='2026-08-04 00:00 UTC')


def test_the_expensive_node_scan_is_skipped_when_it_cannot_help():
    """Relationships explaining every candidate means no per-label scan is needed."""
    nodes = [{'labels': ['File'], 'properties': {'extension': '.txt', 'size_bytes': 1}}]
    graph = FakeGraph(nodes=nodes)

    collect_facts(graph)

    assert not any('nodeTypeProperties' in q for q in graph.queries)


def test_deep_forces_the_node_scan():
    graph = FakeGraph()

    collect_facts(graph, deep=True)

    assert any('nodeTypeProperties' in q for q in graph.queries)


def test_phi_candidates_always_force_the_node_scan():
    """The shortcut may cost completeness of the modality list, never a PHI warning."""
    graph = FakeGraph(nodes=PHI_NODES)

    collect_facts(graph)

    assert any('nodeTypeProperties' in q for q in graph.queries)


def test_nothing_worth_looking_for_skips_both_schema_procedures():
    nodes = [{'labels': ['File'], 'properties': {'extension': '.txt', 'size_bytes': 1}}]
    graph = FakeGraph(nodes=nodes, relationships=[])

    collect_facts(graph)

    assert not any('db.schema' in q for q in graph.queries)


# ================================================================== access


def test_per_property_sharing_modes_drive_the_access_section(settings_db):
    add_profile(settings_db, 'Subject', sharing={
        'patient_id': 'hidden', 'age': 'pseudonymized', 'diagnosis': 'raw'})

    facts = collect_facts(FakeGraph(), settings_db)

    assert facts.sharing_modes_supported is True
    assert facts.sharing_modes['Subject']['patient_id'] == 'hidden'

    text = render_plan(facts, generated_at='2026-08-04 00:00 UTC')
    assert 'sharing modes recorded in this instance\'s schema layer' in text
    assert '| `Subject` | `patient_id` | withheld from all releases |' in text
    assert '| `Subject` | `age` | replaced with a study-specific code before release |' in text
    assert '| `Subject` | `diagnosis` | released as recorded |' in text
    assert '**Withheld properties.** `Subject.patient_id`' in text
    # A property under a sharing mode is also a curated property name, so PHI
    # detection sees it.
    assert facts.has_phi is True


def test_a_missing_sharing_modes_column_is_tolerated(settings_db):
    """The column arrives in Cycle 9 Task A; until then this must not raise."""
    add_profile(settings_db, 'File', never=['_imported_stub'])

    facts = collect_facts(FakeGraph(), settings_db)

    assert facts.sharing_modes_supported is False
    assert facts.sharing_modes == {}
    assert facts.profiled_labels == ('File',)

    text = render_plan(facts, generated_at='2026-08-04 00:00 UTC')
    assert 'No sharing terms have been defined' in text
    # Worded for a UI that does not have the feature yet.
    assert 'once per-property sharing modes are available' in text


def test_a_configured_sharing_mode_produces_prose(settings_db):
    settings = {
        cfg.SETTING_SHARING_MODE: 'controlled_access',
        cfg.SETTING_REPOSITORY: 'dbGaP',
    }
    facts = collect_facts(FakeGraph(), settings_db,
                          setting_getter=lambda key, default=None: settings.get(key, default))

    text = render_plan(facts, generated_at='2026-08-04 00:00 UTC')
    assert 'Data will be shared through controlled access' in text
    assert 'deposited in dbGaP' in text
    assert 'Data Use Agreement' in text
    assert 'No sharing terms have been defined' not in text


def test_metadata_only_mode_flags_a_missing_contact(settings_db):
    settings = {cfg.SETTING_SHARING_MODE: 'metadata_only'}
    facts = collect_facts(FakeGraph(), settings_db,
                          setting_getter=lambda key, default=None: settings.get(key, default))

    text = render_plan(facts, generated_at='2026-08-04 00:00 UTC')
    assert cfg.CONTACT_PLACEHOLDER in text
    assert cfg.SETTING_ACCESS_CONTACT in text


def test_an_unrecognised_sharing_mode_asks_rather_than_guesses(settings_db):
    settings = {cfg.SETTING_SHARING_MODE: 'whatever_i_typed'}
    facts = collect_facts(FakeGraph(), settings_db,
                          setting_getter=lambda key, default=None: settings.get(key, default))

    assert facts.sharing_mode is None
    assert any('whatever_i_typed' in w for w in facts.warnings)
    assert 'No sharing terms have been defined' in render_plan(facts)


def test_no_settings_leaves_findable_placeholders():
    text = plan()

    for placeholder in (cfg.REPOSITORY_PLACEHOLDER, cfg.RETENTION_PLACEHOLDER):
        assert placeholder in text
    # The task block names these exact tokens so a reviewer can search for them.
    assert '[REPOSITORY_NAME]' in text
    assert '[RETENTION_PERIOD]' in text
    # And the draft says where to set them instead of only bracketing them.
    assert cfg.SETTING_REPOSITORY in text
    assert cfg.SETTING_RETENTION_YEARS in text


def test_configured_values_replace_the_placeholders():
    settings = {
        cfg.SETTING_REPOSITORY: 'The Cancer Imaging Archive',
        cfg.SETTING_RETENTION_YEARS: '10 years',
    }
    text = plan(setting_getter=lambda key, default=None: settings.get(key, default))

    assert 'The Cancer Imaging Archive' in text
    assert '10 years' in text
    assert '[REPOSITORY_NAME]' not in text
    assert '[RETENTION_PERIOD]' not in text


# ================================================================ markdown


def test_the_four_required_sections_are_present():
    text = plan()

    for heading in (
        '## Element 1: Data Type',
        '## Element 3: Standards',
        '## Element 4: Data Preservation, Access, and Associated Timelines',
        '## Element 5: Access, Distribution, or Reuse Considerations',
    ):
        assert heading in text


def test_the_ungenerated_elements_are_named_rather_than_silently_omitted():
    text = plan()

    assert 'Element 2: Related Tools, Software and/or Code' in text
    assert 'Element 6: Oversight of Data Management and Sharing' in text


def test_ro_crate_is_named_as_the_packaging_format():
    """Task A put RO-Crate in the codebase; Standards has to say so."""
    text = plan()

    assert 'RO-Crate' in text
    assert 'ro-crate-metadata.json' in text
    assert 'schema.org' in text
    assert any('RO-Crate' in standard for standard in cfg.METADATA_STANDARDS)


def test_the_output_is_markdown_a_researcher_can_paste():
    text = plan()

    assert text.startswith('# Data Management and Sharing Plan')
    assert text.endswith('\n')
    assert '\n\n\n' not in text          # no runs of blank lines
    assert '| --- |' in text             # tables are real markdown tables
    assert '- ' in text                  # and so are the bullet lists
    # Every table row has a consistent cell count.
    for line in text.splitlines():
        if line.startswith('|'):
            assert line.rstrip().endswith('|'), line


def test_placeholders_are_bracketed_and_findable():
    """The draft tells the reader to search for '[', so that has to work."""
    text = plan()

    assert re.search(r'\[[A-Z_][A-Z0-9 _/—,.\'-]+\]', text)
    assert "search this document for `[`" in text


def test_no_nested_emphasis_breaks_the_no_extension_label():
    """``*(no extension)*`` inside an italic run renders as literal asterisks."""
    nodes = [{'labels': ['File'], 'properties': {'extension': None, 'size_bytes': 5}}]

    text = plan(FakeGraph(nodes=nodes, relationships=[]))

    assert '*(no extension)*' in text                  # fine in a table cell
    assert 'registry: (no extension).' in text         # plain inside the italics
    assert '(*(no extension)*)' not in text


def test_a_draft_is_labelled_a_draft():
    text = plan()

    assert 'This is a generated draft, not a submission' in text
    assert 'Draft' in text.splitlines()[0]


def test_an_empty_graph_says_so_instead_of_describing_nothing():
    text = plan(FakeGraph(nodes=[], relationships=[]))

    assert 'holds no nodes' in text
    assert '## Element 3: Standards' in text  # the rest of the document still renders


def test_a_graph_with_no_files_still_produces_a_plan():
    nodes = [{'labels': ['Sample'], 'properties': {'uuid': 's1', 'modality': 'Histology'}}]

    facts = collect_facts(FakeGraph(nodes=nodes, relationships=[]), deep=True)

    assert facts.file_count == 0
    assert any('no :File nodes' in w for w in facts.warnings)
    text = render_plan(facts, generated_at='2026-08-04 00:00 UTC')
    assert 'No file-level index has been committed' in text
    assert 'Histology' in text


def test_a_sampled_run_says_it_was_sampled():
    """A prefix of the store is not a random sample, and the plan must not imply it is."""
    facts = collect_facts(FakeGraph(), sample_limit=2)

    assert facts.format_sample_limit == 2
    assert facts.file_count == 2  # the fake honoured the LIMIT

    text = render_plan(facts, generated_at='2026-08-04 00:00 UTC')
    assert 'Sampled, not exhaustive' in text
    assert 'store order is not sample order' in text


def test_an_exact_run_makes_no_sampling_claim():
    assert 'Sampled, not exhaustive' not in plan()


def test_human_bytes_reads_the_way_a_reviewer_expects():
    assert human_bytes(0) == '0 bytes'
    assert human_bytes(512) == '512 bytes'
    assert human_bytes(2048) == '2.00 KiB'
    assert human_bytes(8076257245704) == '7.35 TiB'
    assert human_bytes(None) == '0 bytes'
    assert human_bytes(-5) == '0 bytes'


def test_generation_is_reproducible_for_the_same_facts():
    facts = collect_facts(FakeGraph())

    assert render_plan(facts, '2026-08-04 00:00 UTC') == render_plan(facts, '2026-08-04 00:00 UTC')


# ============================================================== degradation


def test_a_failed_schema_read_degrades_the_plan_instead_of_failing_it():
    """``db.schema.*`` needs privileges a read-only role may not have."""
    graph = FakeGraph(nodes=PHI_NODES, fail_on=('nodeTypeProperties',))

    facts = collect_facts(graph)

    assert facts.label_counts                                  # the plan still has content
    assert any('node property schema' in w for w in facts.warnings)
    assert 'Element 1: Data Type' in render_plan(facts)


def test_an_unreadable_schema_layer_is_a_note_not_a_crash(tmp_path):
    """A settings DB with no label_profile table must not stop generation."""
    conn = sqlite3.connect(str(tmp_path / 'bare.db'))
    try:
        facts = collect_facts(FakeGraph(), conn)
    finally:
        conn.close()

    assert any('label_profile' in w for w in facts.warnings)
    assert 'Element 1: Data Type' in render_plan(facts)


def test_malformed_sharing_modes_json_is_reported_not_swallowed(settings_db):
    settings_db.execute('ALTER TABLE label_profile ADD COLUMN sharing_modes TEXT')
    settings_db.execute(
        "INSERT INTO label_profile (label_name, sharing_modes) VALUES ('Subject', '{oops')")
    settings_db.commit()

    facts = collect_facts(FakeGraph(), settings_db)

    assert facts.sharing_modes == {}
    assert any('not valid JSON' in w for w in facts.warnings)


def test_a_label_name_that_could_inject_cypher_is_refused():
    """Identifiers are interpolated, not parameterized, so they are validated."""
    from plugins.nih_dms.graph_facts import _safe_ident

    assert _safe_ident('File') == 'File'
    assert _safe_ident('Sample_2') == 'Sample_2'
    for hostile in ('a` MATCH (x) DETACH DELETE x //', 'a b', '1abc', '', None, 'a-b'):
        assert _safe_ident(hostile) is None


def test_a_hostile_label_is_skipped_rather_than_interpolated():
    class Hostile(FakeGraph):
        def execute_read(self, query, parameters=None):
            if 'db.labels()' in query:
                self.queries.append(query)
                return [{'label': 'File'}, {'label': 'x` DETACH DELETE n //'}]
            return super().execute_read(query, parameters)

    graph = Hostile()
    facts = collect_facts(graph)

    assert [label for label, _ in facts.label_counts] == ['File']
    assert not any('DETACH DELETE' in q for q in graph.queries)


# =================================================================== route


@pytest.fixture
def app(tmp_path, monkeypatch):
    """An app whose schema layer is this test's, so no real instance is touched.

    ``monkeypatch.setenv`` rather than assigning ``os.environ`` directly: the
    session-scoped fixture in ``tests/conftest.py`` points ``SCIDK_SETTINGS_DB`` at
    a shared test database, and popping the variable in teardown left every later
    test resolving the *real* ``scidk_settings.db`` — where auth is enabled — which
    turned 16 unrelated tests red. monkeypatch restores the previous value.
    """
    settings_db = str(tmp_path / 'settings.db')
    monkeypatch.setenv('SCIDK_SETTINGS_DB', settings_db)
    application = create_app()
    application.config['TESTING'] = True
    application.config['SCIDK_SETTINGS_DB'] = settings_db
    return application


@pytest.fixture
def client(app, monkeypatch):
    """A client whose route reads the fake graph instead of a real Neo4j."""
    graph = FakeGraph()
    monkeypatch.setattr(dms_routes, '_neo4j_client', lambda: graph)
    test_client = app.test_client()
    test_client.graph = graph
    return test_client


def test_the_route_returns_markdown(client):
    resp = client.get('/api/plugins/nih_dms/draft_plan')

    assert resp.status_code == 200
    assert resp.headers['Content-Type'].startswith('text/markdown')
    body = resp.get_data(as_text=True)
    assert body.startswith('# Data Management and Sharing Plan')
    assert '## Element 3: Standards' in body
    # Generated from the fake graph's real counts.
    assert '| `File` | 4 |' in body


def test_the_route_can_return_json_with_a_summary(client):
    resp = client.get('/api/plugins/nih_dms/draft_plan?format=json')

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'ok'
    assert body['summary']['files'] == 4
    assert body['summary']['records'] == 8
    assert body['summary']['phi_detected'] is False
    assert 'DERIVED_FROM.internal_assay_title' in body['summary']['modalities']
    assert body['markdown'].startswith('# Data Management')


def test_the_route_reports_phi_in_its_summary(app, monkeypatch):
    monkeypatch.setattr(dms_routes, '_neo4j_client', lambda: FakeGraph(nodes=PHI_NODES))

    body = app.test_client().get(
        '/api/plugins/nih_dms/draft_plan?format=json').get_json()

    assert body['summary']['phi_detected'] is True
    assert body['summary']['phi_properties'] == ['patient_id']


def test_the_route_can_serve_a_download(client):
    resp = client.get('/api/plugins/nih_dms/draft_plan?download=1')

    assert resp.status_code == 200
    assert dms_routes.DOWNLOAD_FILENAME in resp.headers['Content-Disposition']


def test_the_route_honours_sample_limit(client):
    body = client.get(
        '/api/plugins/nih_dms/draft_plan?format=json&sample_limit=2').get_json()

    assert body['summary']['sampled'] == 2
    assert 'Sampled, not exhaustive' in body['markdown']


def test_a_junk_sample_limit_is_ignored_rather_than_a_500(client):
    body = client.get(
        '/api/plugins/nih_dms/draft_plan?format=json&sample_limit=abc').get_json()

    assert body['summary']['sampled'] is None
    assert body['summary']['files'] == 4


def test_the_route_closes_the_graph_connection(client):
    client.get('/api/plugins/nih_dms/draft_plan')

    assert client.graph.closed is True


def test_no_graph_is_a_503_and_not_a_placeholder_plan(app, monkeypatch):
    """The failure this plugin exists to avoid: prose that looks generated."""
    def unavailable():
        raise GraphUnavailable('No Neo4j connection is configured. Settings → Connections.')

    monkeypatch.setattr(dms_routes, '_neo4j_client', unavailable)
    test_client = app.test_client()

    markdown_resp = test_client.get('/api/plugins/nih_dms/draft_plan')
    assert markdown_resp.status_code == 503
    body = markdown_resp.get_data(as_text=True)
    assert 'not generated' in body
    assert 'Settings' in body
    # No section of a plan is present to be mistaken for one.
    assert 'Element 1' not in body
    assert 'RO-Crate' not in body

    json_resp = test_client.get('/api/plugins/nih_dms/draft_plan?format=json')
    assert json_resp.status_code == 503
    assert json_resp.get_json()['code'] == 'neo4j_unavailable'


def test_a_failed_label_read_is_an_error_not_an_empty_looking_plan(app, monkeypatch):
    """A graph that cannot list its labels is unusable, not empty.

    Regression guard: this read used to degrade like the others, which produced a
    200 and a plan saying "the graph holds no nodes" — about a graph holding
    millions. Every section derives from the label list, so it raises instead.
    """
    class Exploding(FakeGraph):
        def execute_read(self, query, parameters=None):
            if 'db.labels()' in query:
                raise MemoryError('boom')
            return super().execute_read(query, parameters)

    monkeypatch.setattr(dms_routes, '_neo4j_client', lambda: Exploding())

    resp = app.test_client().get('/api/plugins/nih_dms/draft_plan?format=json')

    assert resp.status_code == 503
    body = resp.get_json()
    assert body['code'] == 'neo4j_unavailable'
    assert 'label list' in body['error']
    assert 'markdown' not in body


def test_an_unexpected_failure_is_a_500_not_a_half_plan(app, monkeypatch):
    """Anything that is not a graph problem still must not emit a partial document."""
    monkeypatch.setattr(dms_routes, '_neo4j_client', lambda: FakeGraph())
    monkeypatch.setattr(dms_routes, 'render_plan',
                        lambda *a, **k: (_ for _ in ()).throw(TypeError('bad template')))

    resp = app.test_client().get('/api/plugins/nih_dms/draft_plan?format=json')

    assert resp.status_code == 500
    assert resp.get_json()['code'] == 'generation_failed'
    assert 'bad template' in resp.get_json()['error']


def test_the_config_route_describes_what_the_generator_looks_for(client):
    body = client.get('/api/plugins/nih_dms/config').get_json()

    assert 'patient_id' in body['phi_property_names']
    assert 'controlled_access' in body['sharing_modes']
    assert body['known_formats'] > 30


# ------------------------------------------------------------------- roles


def test_the_route_is_open_to_both_real_roles_and_no_others():
    """There is no 'staff' role, so requiring it would 403 everyone.

    ``auth_users`` constrains role to ``('admin', 'user')`` and ``require_role``
    is a flat membership test, not a hierarchy. The same mistake shipped once in
    Cycle 2 Task E; this pins the roles the route actually accepts.
    """
    assert dms_routes._PLAN_ROLES == ('admin', 'user')
    assert 'staff' not in dms_routes._PLAN_ROLES


def test_the_plugin_registers_its_routes():
    from plugins.nih_dms import register_plugin

    application = create_app()
    metadata = register_plugin(application)  # idempotent: already loaded at startup

    assert metadata['name'] == 'NIH DMS Plan Generator'
    rules = {str(rule) for rule in application.url_map.iter_rules()}
    assert '/api/plugins/nih_dms/draft_plan' in rules
