"""Imaging interpreters and the enrichment dispatcher.

Everything here runs without a live Neo4j and without real instrument files:
the FCS fixture is a byte-exact minimal FCS3.1 file built in ``tmp_path``, and
the slide interpretations are constructed directly rather than read off a 2 GB
pyramidal TIFF. The dispatcher tests use a fake graph, for the reason recorded
in ``tests/pipeline/conftest.py`` — ``scidk/app.py`` calls ``load_dotenv()`` at
import, so a test that reaches ``get_neo4j_params`` in a full-suite run gets
real credentials for the developer's graph and will write to it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scidk.core.scanner_formats import (
    KNOWN_INTERPRETERS,
    detect_directory_pattern,
    interpreter_for_dir_pattern,
)
from scidk.interpreters.base import BaseInterpreter, InterpretationResult
from scidk.interpreters.fcs_interpreter import FCSInterpreter
from scidk.interpreters.flow_session_interpreter import FlowSessionInterpreter
from scidk.interpreters.histology_session_interpreter import HistologySessionInterpreter
from scidk.interpreters.registry import get_interpreter_by_id, list_interpreter_ids
from scidk.interpreters.svs_interpreter import SVSInterpreter, _property_key


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _write_fcs(path: Path, keywords: dict, version: str = 'FCS3.1',
               delimiter: str = '\x0c') -> Path:
    """Write a minimal but structurally valid FCS file.

    The header is fixed-width by specification: 6 bytes of version, 4 spaces,
    then four 8-byte right-justified ASCII offsets (TEXT begin/end, DATA
    begin/end), then two more for ANALYSIS — 58 bytes in all. The default
    delimiter is form feed because that is what BD instruments actually emit,
    and a parser that assumes a backslash passes on fabricated files and fails
    on real ones.
    """
    # <delim>KEY<delim>VALUE<delim>KEY<delim>VALUE<delim>
    parts = []
    for key, value in keywords.items():
        parts.append(str(key))
        parts.append(str(value))
    text = delimiter + delimiter.join(parts) + delimiter

    text_start = 58
    text_bytes = text.encode('latin-1')
    text_end = text_start + len(text_bytes) - 1

    header = (
        version.ljust(6)[:6].encode('ascii')
        + b'    '
        + str(text_start).rjust(8).encode('ascii')
        + str(text_end).rjust(8).encode('ascii')
        + b'       0' + b'       0'   # DATA begin/end
        + b'       0' + b'       0'   # ANALYSIS begin/end
    )
    assert len(header) == 58, len(header)

    path.write_bytes(header + text_bytes)
    return path


_FCS_KEYWORDS = {
    '$TOT': '0000000000000000500',   # zero-padded, as FACSDiva writes it
    '$PAR': '3',
    '$CYT': 'FACSAria',
    '$SRC': 'U29',
    '$DATE': '07-OCT-2022',
    '$SYS': 'Windows NT',
    '$P1N': 'FSC-A',
    '$P2N': 'SSC-A',
    '$P3N': 'PE-A',
}


def _slide(source_path: str, **overrides) -> InterpretationResult:
    props = {
        'source_path': source_path,
        'vendor': 'Aperio',
        'staining': 'H&E',
        'appmag': '20',
        'scanscope_id': 'SS7170',
        'date': '01/31/22',
    }
    props.update(overrides)
    return InterpretationResult(
        node_type='HistologySlide',
        node_label=f'Slide: {Path(source_path).stem}',
        confidence='confirmed',
        properties=props,
        provenance_edges=[],
    )


# ─────────────────────────────────────────────────────────────────────────────
# BaseInterpreter / InterpretationResult
# ─────────────────────────────────────────────────────────────────────────────

class TestInterpretationResult:
    def test_legacy_dict_has_the_four_keys_the_pipeline_reads(self):
        result = InterpretationResult(
            node_type='FCSFile', node_label='x', confidence='confirmed',
            properties={'source_path': '/a/b.fcs', 'cytometer': 'Aria'},
            provenance_edges=[{'type': 'METADATA_SOURCE'}],
        )
        legacy = result.to_legacy_dict()
        assert legacy['status'] == 'success'
        assert legacy['data']['cytometer'] == 'Aria'
        assert legacy['nodes'][0]['label'] == 'FCSFile'
        assert legacy['nodes'][0]['key_property'] == 'source_path'
        # write_declared_nodes rejects a declaration whose key_property is not
        # also a key in properties.
        assert 'source_path' in legacy['nodes'][0]['properties']
        assert legacy['relationships'] == [{'type': 'METADATA_SOURCE'}]

    def test_reads_like_a_dict_for_the_pre_abc_call_sites(self):
        """filesystem.py and scans_service.py call result.get('status')."""
        result = InterpretationResult(
            node_type='FCSFile', node_label='x', confidence='inferred',
            properties={'source_path': '/a'}, provenance_edges=[],
        )
        assert result.get('status') == 'success'
        assert result.get('nodes') and result.get('relationships') == []
        assert result['data']['source_path'] == '/a'
        assert result.get('missing', 'fallback') == 'fallback'

    def test_stub_declares_no_node_and_reports_error_status(self):
        stub = FCSInterpreter()._stub(Path('/a/b.fcs'), 'because')
        assert stub.confidence == 'stub'
        legacy = stub.to_legacy_dict()
        assert legacy['status'] == 'error'
        assert legacy['nodes'] == []
        # The reason has to survive build_payload, which keeps only data.
        assert legacy['data']['warnings'] == ['because']

    def test_payload_survives_the_shared_persistence_envelope(self):
        from scidk.core.interpreter_persistence import build_payload

        result = InterpretationResult(
            node_type='FCSFile', node_label='x', confidence='confirmed',
            properties={'source_path': '/a'},
            provenance_edges=[{'type': 'METADATA_SOURCE'}],
        )
        payload = build_payload(result.to_legacy_dict(), '1.0.0')
        assert payload['nodes'] and payload['relationships']
        json.dumps(payload, default=str)  # must be storable


class TestBaseInterpreter:
    def test_cannot_instantiate_without_interpret(self):
        class Incomplete(BaseInterpreter):
            id = 'incomplete'

        with pytest.raises(TypeError):
            Incomplete()

    def test_can_handle_defaults_to_extension_and_never_raises(self):
        assert FCSInterpreter().can_handle(Path('/a/b.FCS')) is True
        assert FCSInterpreter().can_handle(Path('/a/b.txt')) is False
        assert FCSInterpreter().can_handle(None) is False


# ─────────────────────────────────────────────────────────────────────────────
# FCS
# ─────────────────────────────────────────────────────────────────────────────

class TestFCSInterpreter:
    def test_parses_header(self, tmp_path):
        path = _write_fcs(tmp_path / 'Specimen_001_A1.fcs', _FCS_KEYWORDS)
        result = FCSInterpreter().interpret(path)

        assert result.node_type == 'FCSFile'
        assert result.confidence == 'confirmed'
        assert result.warnings == []
        props = result.properties
        assert props['fcs_version'] == 'FCS3.1'
        assert props['cytometer'] == 'FACSAria'
        assert props['sample_id'] == 'U29'
        assert props['acquisition_date'] == '07-OCT-2022'
        assert props['total_events'] == 500          # leading zeros stripped
        assert props['parameter_count'] == 3
        assert props['parameters'] == 'FSC-A|SSC-A|PE-A'

    def test_declares_a_metadata_source_edge_to_the_file_node(self, tmp_path):
        path = _write_fcs(tmp_path / 'a.fcs', _FCS_KEYWORDS)
        edge = FCSInterpreter().interpret(path).provenance_edges[0]
        assert edge['type'] == 'METADATA_SOURCE'
        assert edge['from_label'] == 'FCSFile'
        assert edge['to_label'] == 'File'
        assert edge['to_match'] == {'path': str(path)}

    def test_context_host_qualifies_the_file_match(self, tmp_path):
        """:File's only index is the composite (path, host); matching on path
        alone is a full label scan — 3.72s against 5.5M nodes vs 0.01s."""
        path = _write_fcs(tmp_path / 'a.fcs', _FCS_KEYWORDS)
        edge = FCSInterpreter().interpret(path, {'host': 'mounted:/mnt/server'}).provenance_edges[0]
        assert edge['to_match'] == {'path': str(path), 'host': 'mounted:/mnt/server'}

    @pytest.mark.parametrize('delimiter', ['\x0c', '|', '/', '\\'])
    def test_honours_whatever_delimiter_the_segment_declares(self, tmp_path, delimiter):
        path = _write_fcs(tmp_path / 'a.fcs', _FCS_KEYWORDS, delimiter=delimiter)
        assert FCSInterpreter().interpret(path).properties['cytometer'] == 'FACSAria'

    def test_fcs2_is_inferred_not_confirmed(self, tmp_path):
        path = _write_fcs(tmp_path / 'a.fcs', _FCS_KEYWORDS, version='FCS2.0')
        assert FCSInterpreter().interpret(path).confidence == 'inferred'

    def test_par_bounds_the_panel_walk_past_a_gap(self, tmp_path):
        """A missing $P2N must cost one parameter, not the whole tail."""
        keywords = dict(_FCS_KEYWORDS)
        del keywords['$P2N']
        path = _write_fcs(tmp_path / 'a.fcs', keywords)
        props = FCSInterpreter().interpret(path).properties
        assert props['parameters'] == 'FSC-A|PE-A'
        assert props['parameter_count'] == 3        # $PAR is authoritative

    @pytest.mark.parametrize('content', [
        b'',
        b'short',
        b'NOTFCS' + b' ' * 52,
        b'FCS3.1' + b'    ' + b'  bogus ' + b'  bogus ' + b'0' * 32,
    ])
    def test_bad_input_stubs_rather_than_raising(self, tmp_path, content):
        path = tmp_path / 'bad.fcs'
        path.write_bytes(content)
        result = FCSInterpreter().interpret(path)
        assert result.confidence == 'stub'
        assert result.warnings

    def test_missing_file_stubs(self, tmp_path):
        result = FCSInterpreter().interpret(tmp_path / 'nope.fcs')
        assert result.confidence == 'stub'


# ─────────────────────────────────────────────────────────────────────────────
# SVS
# ─────────────────────────────────────────────────────────────────────────────

class TestSVSInterpreter:
    def test_parses_a_real_aperio_description(self):
        description = (
            'Aperio Image Library v12.0.15 \r\n85344x33906 [0,100 83664x33806] '
            '(240x240) JPEG/RGB Q=70|AppMag = 20|StripeWidth = 2032|'
            'ScanScope ID = SS7170|Date = 01/31/22|MPP = 0.5040'
        )
        props, dropped = SVSInterpreter._parse_description(description)
        assert props['appmag'] == '20'
        assert props['scanscope_id'] == 'SS7170'
        assert props['mpp'] == '0.5040'
        assert dropped == set()
        assert SVSInterpreter._dimensions(description) == (85344, 33906)

    def test_the_banner_segment_never_becomes_a_property_name(self):
        """Property KEY names go raw into Cypher (services/neo4j_client.py)."""
        props, _ = SVSInterpreter._parse_description(
            'Aperio Image Library v12.0.15 \r\n85344x33906 JPEG/RGB Q=70|AppMag = 20'
        )
        assert list(props) == ['appmag']

    @pytest.mark.parametrize('raw,expected', [
        ('AppMag', 'appmag'),
        ('ScanScope ID', 'scanscope_id'),
        ('Time Zone', 'time_zone'),
        ('  Focus Offset  ', 'focus_offset'),
        ('123abc', None),          # must start with a letter
        ('', None),
        ('!!!', None),
        ('`backtick`', 'backtick'),
        ('a' * 80, None),          # too long to be a sensible property name
    ])
    def test_property_key_sanitisation(self, raw, expected):
        assert _property_key(raw) == expected

    @pytest.mark.parametrize('raw', [
        'n.x = 1 WITH n MATCH (m) DETACH DELETE m //',
        'a` = 1 SET n.b',
        'x$y{z}',
    ])
    def test_cypher_metacharacters_cannot_survive_into_a_key(self, raw):
        """The guard neutralises rather than escapes: whatever comes back is a
        plain identifier, so `SET n.<key> = $p` cannot be broken out of."""
        from scidk.interpreters.svs_interpreter import _SAFE_KEY

        key = _property_key(raw)
        assert key is None or _SAFE_KEY.match(key)

    def test_unusable_keys_are_reported_not_silently_dropped(self):
        props, dropped = SVSInterpreter._parse_description('hdr|9lives = x|AppMag = 20')
        assert props == {'appmag': '20'}
        assert dropped == {'9lives'}

    @pytest.mark.parametrize('stem,expected', [
        ('PY-18500-001_IHC', 'Immunohistochemistry'),
        ('slide_HNE_04', 'H&E'),          # longest tag first: not read as 'HE'
        ('slide-HE-04', 'H&E'),
        ('sample_IF_2', 'Immunofluorescence'),
        ('HCF-LM-17930-009', 'Unknown'),
    ])
    def test_staining_from_filename(self, stem, expected):
        assert SVSInterpreter._staining(stem) == expected

    def test_non_tiff_stubs_rather_than_raising(self, tmp_path):
        path = tmp_path / '._resource_fork.svs'
        path.write_bytes(b'\x00\x05\x16\x07not a tiff')
        result = SVSInterpreter().interpret(path)
        assert result.confidence == 'stub'
        assert result.warnings

    def test_missing_tifffile_stubs_with_a_named_warning(self, tmp_path, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def _no_tifffile(name, *args, **kwargs):
            if name == 'tifffile':
                raise ImportError("No module named 'tifffile'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, '__import__', _no_tifffile)
        result = SVSInterpreter().interpret(tmp_path / 'x.svs')
        assert result.confidence == 'stub'
        assert 'tifffile not installed' in result.warnings[0]


# ─────────────────────────────────────────────────────────────────────────────
# Session interpreters
# ─────────────────────────────────────────────────────────────────────────────

class TestFlowSessionInterpreter:
    def test_aggregates_sibling_fcs_interpretations(self, tmp_path):
        directory = tmp_path / 'Panel_A_2022-10-07_U29'
        directory.mkdir()
        siblings = {}
        for index, (cytometer, events, panel) in enumerate([
            ('FACSAria', 500, 'FSC-A|SSC-A|PE-A'),
            ('FACSAria', 250, 'FSC-A|SSC-A|APC-A'),
        ]):
            name = f'tube_{index}.fcs'
            siblings[name] = InterpretationResult(
                node_type='FCSFile', node_label=name, confidence='confirmed',
                properties={
                    'source_path': str(directory / name),
                    'cytometer': cytometer, 'total_events': events,
                    'parameters': panel, 'sample_id': 'U29',
                    'acquisition_date': '07-OCT-2022',
                },
                provenance_edges=[],
            )

        result = FlowSessionInterpreter().interpret(
            directory, {'sibling_interpretations': siblings})

        assert result.node_type == 'FlowCytometrySession'
        props = result.properties
        assert props['fcs_file_count'] == 2
        assert props['total_events'] == 750
        assert props['cytometer'] == 'FACSAria'          # deduplicated
        assert props['panel_parameters'] == 'APC-A|FSC-A|PE-A|SSC-A'
        assert props['parameter_count'] == 4             # union, not sum
        assert props['session_date'] == '2022-10-07'     # from the folder name
        assert 'U29' in props['subject_ids']

    def test_declares_one_derived_from_edge_per_member(self, tmp_path):
        directory = tmp_path / 'session'
        directory.mkdir()
        siblings = {
            f't{i}.fcs': InterpretationResult(
                node_type='FCSFile', node_label=f't{i}', confidence='confirmed',
                properties={'source_path': str(directory / f't{i}.fcs')},
                provenance_edges=[],
            ) for i in range(3)
        }
        edges = FlowSessionInterpreter().interpret(
            directory, {'sibling_interpretations': siblings}).provenance_edges

        assert len(edges) == 3
        for edge in edges:
            # write_declared_nodes MATCHes both ends by key property; an edge
            # with no to_match matches every FCSFile in the graph.
            assert edge['type'] == 'DERIVED_FROM'
            assert edge['from_match'] == {'source_path': str(directory)}
            assert set(edge['to_match']) == {'source_path'}

    def test_no_siblings_yields_a_stub_not_an_empty_session(self, tmp_path):
        result = FlowSessionInterpreter().interpret(tmp_path, {'sibling_interpretations': {}})
        assert result.confidence == 'stub'
        assert result.to_legacy_dict()['nodes'] == []

    def test_ignores_siblings_of_other_types(self, tmp_path):
        result = FlowSessionInterpreter().interpret(tmp_path, {
            'sibling_interpretations': {'a.svs': _slide('/x/a.svs')},
        })
        assert result.confidence == 'stub'

    def test_can_handle_detects_fcs_in_the_directory(self, tmp_path):
        assert FlowSessionInterpreter().can_handle(tmp_path) is False
        (tmp_path / 'a.FCS').write_bytes(b'')
        assert FlowSessionInterpreter().can_handle(tmp_path) is True
        assert FlowSessionInterpreter().can_handle(tmp_path / 'nonexistent') is False


class TestHistologySessionInterpreter:
    def test_aggregates_slides(self, tmp_path):
        directory = tmp_path / 'Histology_PY'
        directory.mkdir()
        siblings = {
            'a.svs': _slide(str(directory / 'a.svs'), staining='H&E', date='01/31/22'),
            'b.svs': _slide(str(directory / 'b.svs'), staining='Immunohistochemistry',
                            date='02/01/22', appmag='40'),
        }

        result = HistologySessionInterpreter().interpret(
            directory, {'sibling_interpretations': siblings})

        assert result.node_type == 'HistologySession'
        props = result.properties
        assert props['slide_count'] == 2
        assert props['staining_protocols'] == 'H&E|Immunohistochemistry'
        assert props['scanner_ids'] == 'SS7170'
        assert props['magnifications'] == '20|40'
        assert props['scan_date_first'] == '01/31/22'
        assert props['scan_date_last'] == '02/01/22'
        assert len(result.provenance_edges) == 2

    def test_unknown_staining_is_not_aggregated_as_a_protocol(self, tmp_path):
        result = HistologySessionInterpreter().interpret(tmp_path, {
            'sibling_interpretations': {'a.svs': _slide('/x/a.svs', staining='Unknown')},
        })
        assert result.properties['staining_protocols'] == ''
        assert result.properties['slide_count'] == 1

    def test_no_siblings_yields_a_stub(self, tmp_path):
        result = HistologySessionInterpreter().interpret(tmp_path, {})
        assert result.confidence == 'stub'

    def test_can_handle_detects_each_slide_extension(self, tmp_path):
        assert HistologySessionInterpreter().can_handle(tmp_path) is False
        (tmp_path / 'a.ndpi').write_bytes(b'')
        assert HistologySessionInterpreter().can_handle(tmp_path) is True


# ─────────────────────────────────────────────────────────────────────────────
# Format tables and registry
# ─────────────────────────────────────────────────────────────────────────────

class TestScannerFormats:
    @pytest.mark.parametrize('extension,interpreter_id', [
        ('.fcs', 'fcs_interpreter'),
        ('.svs', 'svs_interpreter'),
        ('.ndpi', 'svs_interpreter'),
        ('.scn', 'svs_interpreter'),
        ('.pzfx', None),
    ])
    def test_imaging_extensions_are_registered(self, extension, interpreter_id):
        assert KNOWN_INTERPRETERS[extension] == interpreter_id

    def test_every_named_interpreter_id_resolves(self):
        """A KNOWN_INTERPRETERS value matching no registry id is a silent no-op
        written into files.interpreted_as — catch the typo here instead."""
        unresolved = {
            interpreter_id for interpreter_id in KNOWN_INTERPRETERS.values()
            if interpreter_id and get_interpreter_by_id(interpreter_id) is None
        }
        assert unresolved == set()

    @pytest.mark.parametrize('children,expected', [
        (['a.fcs'], 'flow_cytometry_session'),
        (['a.FCS', 'b.fcs'], 'flow_cytometry_session'),
        (['a.svs'], 'histology_session'),
        (['a.ndpi'], 'histology_session'),
        (['a.scn'], 'histology_session'),
        (['notes.txt'], None),
        ([], None),
    ])
    def test_extension_directory_patterns(self, children, expected):
        assert detect_directory_pattern(children) == expected

    def test_exact_filename_patterns_still_win(self):
        children = ['barcodes.tsv', 'features.tsv', 'matrix.mtx', 'stray.fcs']
        assert detect_directory_pattern(children) == '10x_genomics_mtx'

    def test_existing_pattern_behaviour_is_unchanged(self):
        assert detect_directory_pattern(['DICOMDIR']) == 'dicom_dir'
        assert detect_directory_pattern(['acqp', 'method', 'fid']) == 'bruker_mri'
        assert detect_directory_pattern(['ACQP', 'Method', 'FID']) == 'bruker_mri'
        # The partial-BIDS entry matches by prefix.
        assert detect_directory_pattern(['subject', 'ses-01', 'anat']) == 'bids_dataset'

    def test_session_patterns_map_to_the_session_interpreters(self):
        assert interpreter_for_dir_pattern('flow_cytometry_session') == 'flow_session_interpreter'
        assert interpreter_for_dir_pattern('histology_session') == 'histology_session_interpreter'
        assert interpreter_for_dir_pattern(None) is None

    def test_both_scanners_agree_with_the_package_tables(self):
        """The scanners carry inline fallback copies for standalone runs."""
        import importlib.util

        for script in ('tools/scidk_scanner.py', 'tools/scidk_scanner_opt.py'):
            spec = importlib.util.spec_from_file_location(f'_scan_{Path(script).stem}', script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            assert module._detect_dir_pattern(['a.fcs']) == 'flow_cytometry_session'
            assert module._detect_dir_pattern(['a.svs']) == 'histology_session'
            assert module._detect_interpreter('.svs', None, None) == 'svs_interpreter'
            assert module._detect_interpreter('.fcs', None, None) == 'fcs_interpreter'


class TestInterpreterRegistry:
    def test_new_interpreters_resolve_by_id(self):
        for interpreter_id in ('fcs_interpreter', 'svs_interpreter',
                               'flow_session_interpreter', 'histology_session_interpreter'):
            assert get_interpreter_by_id(interpreter_id) is not None
            assert interpreter_id in list_interpreter_ids()

    def test_directory_interpreters_declare_directory_dispatch(self):
        for interpreter_id in ('flow_session_interpreter', 'histology_session_interpreter'):
            assert get_interpreter_by_id(interpreter_id).dispatch == 'directory'
        for interpreter_id in ('fcs_interpreter', 'svs_interpreter'):
            assert get_interpreter_by_id(interpreter_id).dispatch == 'file'

    def test_unknown_id_is_none_not_an_error(self):
        assert get_interpreter_by_id('mtx_interpreter') is None
        assert get_interpreter_by_id(None) is None

    def test_app_registry_reaches_directory_interpreters_by_id(self):
        """extensions == [] used to mean registered nowhere at all."""
        from scidk.core.registry import InterpreterRegistry
        from scidk.interpreters import register_all

        registry = InterpreterRegistry()
        register_all(registry)
        assert registry.get_by_id('flow_session_interpreter') is not None
        assert registry.get_by_id('bruker_microct_dataset') is not None

    def test_file_scan_selection_never_picks_a_directory_interpreter(self):
        from scidk.core.registry import InterpreterRegistry
        from scidk.interpreters import register_all

        registry = InterpreterRegistry()
        register_all(registry)
        selected = registry.select_for_dataset({'path': '/a/b.fcs', 'extension': '.fcs'})
        assert [i.id for i in selected] == ['fcs_interpreter']


# ─────────────────────────────────────────────────────────────────────────────
# Enrichment dispatcher
# ─────────────────────────────────────────────────────────────────────────────

class FakeGraph:
    """Records what the dispatcher would write. No ``_session``, so the
    already-enriched lookup degrades to "everything is work", which is the
    behaviour under an unreachable graph."""

    def __init__(self):
        self.interpretations = []

    def add_interpretation(self, checksum, interpreter_id, payload, file_path=None, host=None):
        self.interpretations.append({
            'checksum': checksum, 'interpreter_id': interpreter_id,
            'payload': payload, 'file_path': file_path, 'host': host,
        })


class FakeClient:
    def __init__(self):
        self.nodes = []
        self.relationships = []

    def write_declared_nodes(self, nodes, relationships):
        self.nodes.extend(nodes)
        self.relationships.extend(relationships)
        return {'written_nodes': len(nodes), 'written_relationships': len(relationships), 'errors': []}

    def close(self):
        pass


@pytest.fixture
def enrichment_db(tmp_path, monkeypatch):
    """A files.db with one scan and whatever rows a test adds."""
    import sqlite3

    from scidk.core import path_index_sqlite as pix

    monkeypatch.setenv('SCIDK_DB_PATH', str(tmp_path / 'files.db'))
    conn = sqlite3.connect(str(tmp_path / 'files.db'))
    pix.init_db(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS scans ("
        "id TEXT PRIMARY KEY, root TEXT, started REAL, completed REAL, "
        "status TEXT, extra_json TEXT)"
    )
    conn.execute(
        "INSERT INTO scans(id, root, extra_json) VALUES(?,?,?)",
        ('scan1', str(tmp_path), json.dumps({'host_id': 'local:testhost'})),
    )
    conn.commit()
    yield conn
    conn.close()


def _insert_file(conn, path: Path, scan_id='scan1', interpreted_as=None,
                 row_type='file', remote=None):
    conn.execute(
        "INSERT INTO files(path, parent_path, name, depth, type, size, "
        "file_extension, hash, remote, scan_id, interpreted_as) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (str(path), str(path.parent), path.name, len(path.parts), row_type, 0,
         path.suffix.lower(), f'hash-{path.name}', remote, scan_id, interpreted_as),
    )
    conn.commit()


@pytest.fixture
def fake_backends(monkeypatch):
    from scidk.services import enrichment_service

    graph, client = FakeGraph(), FakeClient()
    monkeypatch.setattr(enrichment_service, '_get_graph', lambda: graph)
    monkeypatch.setattr(enrichment_service, '_get_client', lambda _graph: client)
    return graph, client


class TestEnrichmentDispatcher:
    def test_two_passes_produce_file_and_session_nodes(self, tmp_path, enrichment_db, fake_backends):
        from scidk.services.enrichment_service import run_enrichment

        graph, client = fake_backends
        directory = tmp_path / 'Panel_A_2022-10-07_U29'
        directory.mkdir()
        for name in ('tube_a.fcs', 'tube_b.fcs'):
            _write_fcs(directory / name, _FCS_KEYWORDS)
            _insert_file(enrichment_db, directory / name)
        _insert_file(enrichment_db, directory, row_type='folder')

        result = run_enrichment(interpreter_id='fcs_interpreter', limit=10,
                                scan_id='scan1', db_conn=enrichment_db)

        assert result['files_processed'] == 2
        assert result['directories_processed'] == 1
        assert result['errors'] == []
        assert set(result['interpreters_used']) == {'fcs_interpreter', 'flow_session_interpreter'}

        labels = [n['label'] for n in client.nodes]
        assert labels.count('FCSFile') == 2
        assert labels.count('FlowCytometrySession') == 1

        # The session node knows about both tubes.
        session = next(n for n in client.nodes if n['label'] == 'FlowCytometrySession')
        assert session['properties']['fcs_file_count'] == 2
        assert session['properties']['total_events'] == 1000

        derived = [r for r in client.relationships if r['type'] == 'DERIVED_FROM']
        assert len(derived) == 2

    def test_host_comes_from_files_remote(self, tmp_path, enrichment_db, fake_backends):
        """:File is keyed on (path, host) and only the composite index exists,
        so every write has to carry the host."""
        from scidk.services.enrichment_service import run_enrichment

        graph, _client = fake_backends
        path = _write_fcs(tmp_path / 'a.fcs', _FCS_KEYWORDS)
        _insert_file(enrichment_db, path, remote='local:testhost')

        run_enrichment(limit=10, scan_id='scan1', db_conn=enrichment_db)

        recorded = next(i for i in graph.interpretations if i['file_path'] == str(path))
        assert recorded['host'] == 'local:testhost'
        assert recorded['checksum'] == 'hash-a.fcs'
        # …and it reaches the interpreter, so the provenance edge can MATCH
        # :File on the indexed (path, host) key rather than scanning.
        edge = recorded['payload']['relationships'][0]
        assert edge['to_match'] == {'path': str(path), 'host': 'local:testhost'}

    def test_find_work_does_not_join_scans(self):
        """The join was there only for the host, and cost a join against a
        27M-row table — for a column one of the two real scans lacks."""
        import inspect as _inspect

        from scidk.services.enrichment_service import _find_work

        source = _inspect.getsource(_find_work)
        assert 'JOIN scans' not in source
        assert 'FROM files f ' in source
        assert "COALESCE(f.remote, '')" in source

    def test_finds_work_by_extension_when_interpreted_as_is_null(self, tmp_path, enrichment_db, fake_backends):
        """The 27M-row index has interpreted_as unset on every row."""
        from scidk.services.enrichment_service import run_enrichment

        path = _write_fcs(tmp_path / 'a.fcs', _FCS_KEYWORDS)
        _insert_file(enrichment_db, path, interpreted_as=None)

        assert run_enrichment(interpreter_id='fcs_interpreter', limit=10,
                              db_conn=enrichment_db)['files_processed'] == 1

    def test_interpreted_as_wins_over_the_extension_table(self, tmp_path, enrichment_db, fake_backends):
        """A scanner magic-byte match on an extensionless file must be honoured."""
        from scidk.services.enrichment_service import run_enrichment

        _graph, client = fake_backends
        path = _write_fcs(tmp_path / 'no_extension', _FCS_KEYWORDS)
        _insert_file(enrichment_db, path, interpreted_as='fcs_interpreter')

        result = run_enrichment(limit=10, scan_id='scan1', db_conn=enrichment_db)
        assert result['files_processed'] == 1
        assert client.nodes[0]['label'] == 'FCSFile'

    def test_writes_the_interpretation_payload_back_to_sqlite(self, tmp_path, enrichment_db, fake_backends):
        from scidk.services.enrichment_service import run_enrichment

        path = _write_fcs(tmp_path / 'a.fcs', _FCS_KEYWORDS)
        _insert_file(enrichment_db, path)

        run_enrichment(limit=10, scan_id='scan1', db_conn=enrichment_db)

        interpreted_as, payload_json = enrichment_db.execute(
            "SELECT interpreted_as, interpretation_json FROM files WHERE path = ?",
            (str(path),)).fetchone()
        assert interpreted_as == 'fcs_interpreter'
        payload = json.loads(payload_json)
        assert payload['nodes'][0]['label'] == 'FCSFile'
        assert payload['data']['cytometer'] == 'FACSAria'

    def test_directory_row_is_persisted_despite_being_type_folder(self, tmp_path, enrichment_db, fake_backends):
        """persist_interpretation defaults to type='file' and would match none."""
        from scidk.services.enrichment_service import run_enrichment

        directory = tmp_path / 'session'
        directory.mkdir()
        _write_fcs(directory / 'a.fcs', _FCS_KEYWORDS)
        _insert_file(enrichment_db, directory / 'a.fcs')
        _insert_file(enrichment_db, directory, row_type='folder')

        run_enrichment(limit=10, scan_id='scan1', db_conn=enrichment_db)

        row = enrichment_db.execute(
            "SELECT interpreted_as FROM files WHERE path = ? AND type = 'folder'",
            (str(directory),)).fetchone()
        assert row[0] == 'flow_session_interpreter'

    def test_an_unreadable_file_does_not_abandon_the_batch(self, tmp_path, enrichment_db, fake_backends):
        from scidk.services.enrichment_service import run_enrichment

        _graph, client = fake_backends
        directory = tmp_path / 'session'
        directory.mkdir()
        _write_fcs(directory / 'good.fcs', _FCS_KEYWORDS)
        (directory / 'broken.fcs').write_bytes(b'garbage')
        for name in ('good.fcs', 'broken.fcs'):
            _insert_file(enrichment_db, directory / name)

        result = run_enrichment(limit=10, scan_id='scan1', db_conn=enrichment_db)

        assert result['files_processed'] == 2       # both attempted
        assert any('broken.fcs' in w for w in result['warnings'])
        assert result['errors'] == []
        # …but only the readable one declared a node.
        assert [n['label'] for n in client.nodes].count('FCSFile') == 1

    def test_a_directory_with_no_pattern_is_examined_but_not_processed(self, tmp_path, enrichment_db, fake_backends):
        from scidk.services.enrichment_service import run_enrichment

        path = tmp_path / 'a.py'
        path.write_text('x = 1\n')
        _insert_file(enrichment_db, path, interpreted_as='python_code')

        result = run_enrichment(limit=10, scan_id='scan1', db_conn=enrichment_db)
        assert result['files_processed'] == 1
        assert result['directories_examined'] == 1
        assert result['directories_processed'] == 0

    def test_pre_abc_interpreters_still_run(self, tmp_path, enrichment_db, fake_backends):
        """The eleven interpreters written before the ABC are
        interpret(self, file_path) and return a plain dict. Calling every
        interpreter with a context argument would make all of them
        unenrichable."""
        from scidk.services.enrichment_service import run_enrichment

        graph, _client = fake_backends
        path = tmp_path / 'a.py'
        path.write_text('def f():\n    return 1\n')
        _insert_file(enrichment_db, path, interpreted_as='python_code')

        result = run_enrichment(limit=10, scan_id='scan1', db_conn=enrichment_db)
        assert result['files_processed'] == 1
        assert result['errors'] == []

        recorded = next(i for i in graph.interpretations if i['file_path'] == str(path))
        assert recorded['interpreter_id'] == 'python_code'
        assert recorded['payload']['status'] == 'success'

        stored = enrichment_db.execute(
            "SELECT interpreted_as FROM files WHERE path = ?", (str(path),)).fetchone()
        assert stored[0] == 'python_code'

    def test_invoke_picks_the_right_arity(self, tmp_path):
        from scidk.services.enrichment_service import _invoke

        seen = {}

        class Legacy:
            def interpret(self, file_path):
                seen['legacy'] = True
                return {'status': 'success', 'data': {}}

        class Modern:
            def interpret(self, path, context=None):
                seen['context'] = context
                return {'status': 'success', 'data': {}}

        _invoke(Legacy(), tmp_path, {'host': 'h'})
        _invoke(Modern(), tmp_path, {'host': 'h'})
        assert seen['legacy'] is True
        assert seen['context'] == {'host': 'h'}

    def test_rows_naming_an_unimplemented_interpreter_are_counted_not_dropped(
            self, tmp_path, enrichment_db, fake_backends):
        from scidk.services.enrichment_service import run_enrichment

        path = tmp_path / 'x.mtx'
        path.write_text('')
        _insert_file(enrichment_db, path, interpreted_as='mtx_interpreter')

        result = run_enrichment(limit=10, scan_id='scan1', db_conn=enrichment_db)
        assert result['files_processed'] == 0
        assert result['files_skipped_no_interpreter'] == 1

    def test_limit_is_respected(self, tmp_path, enrichment_db, fake_backends):
        from scidk.services.enrichment_service import run_enrichment

        for index in range(5):
            path = _write_fcs(tmp_path / f'f{index}.fcs', _FCS_KEYWORDS)
            _insert_file(enrichment_db, path)

        assert run_enrichment(limit=2, scan_id='scan1',
                              db_conn=enrichment_db)['files_processed'] == 2

    def test_scan_id_filter_excludes_other_scans(self, tmp_path, enrichment_db, fake_backends):
        from scidk.services.enrichment_service import run_enrichment

        enrichment_db.execute("INSERT INTO scans(id, root, extra_json) VALUES('scan2','/x','{}')")
        _insert_file(enrichment_db, _write_fcs(tmp_path / 'a.fcs', _FCS_KEYWORDS), scan_id='scan1')
        _insert_file(enrichment_db, _write_fcs(tmp_path / 'b.fcs', _FCS_KEYWORDS), scan_id='scan2')

        assert run_enrichment(limit=10, scan_id='scan2',
                              db_conn=enrichment_db)['files_processed'] == 1

    def test_extensions_for_maps_only_implemented_interpreters(self):
        from scidk.services.enrichment_service import _extensions_for

        assert _extensions_for('svs_interpreter') == ['.ndpi', '.scn', '.svs']
        assert '.pzfx' not in _extensions_for(None)   # None value = a gap, not work
        assert '.fcs' in _extensions_for(None)

    @pytest.mark.parametrize('remote,expected', [
        ('mounted:/mnt/server', 'mounted:/mnt/server'),
        ('  ', ''),
        (None, ''),
    ])
    def test_row_host_reads_files_remote(self, remote, expected):
        from scidk.services.enrichment_service import _row_host

        assert _row_host(remote) == expected

    def test_host_survives_a_missing_scans_row(self, tmp_path, enrichment_db, fake_backends):
        """One of the two scans holding the imaging files has no scans row, so
        a join against scans would yield nothing; files.remote carries the host
        per row and is what the composite File index needs."""
        from scidk.services.enrichment_service import run_enrichment

        graph, _client = fake_backends
        path = _write_fcs(tmp_path / 'a.fcs', _FCS_KEYWORDS)
        _insert_file(enrichment_db, path, scan_id='orphan', remote='mounted:/mnt/server')

        run_enrichment(limit=10, db_conn=enrichment_db)

        recorded = next(i for i in graph.interpretations if i['file_path'] == str(path))
        assert recorded['host'] == 'mounted:/mnt/server'
        assert recorded['payload']['relationships'][0]['to_match']['host'] == 'mounted:/mnt/server'

    def test_directory_pass_takes_the_first_non_empty_sibling_host(self, tmp_path, enrichment_db, fake_backends):
        from scidk.services.enrichment_service import run_enrichment

        graph, _client = fake_backends
        directory = tmp_path / 'session'
        directory.mkdir()
        # The row with no remote is first; the directory must not inherit ''.
        _write_fcs(directory / 'a.fcs', _FCS_KEYWORDS)
        _write_fcs(directory / 'b.fcs', _FCS_KEYWORDS)
        _insert_file(enrichment_db, directory / 'a.fcs', remote=None)
        _insert_file(enrichment_db, directory / 'b.fcs', remote='mounted:/mnt/server')

        run_enrichment(limit=10, db_conn=enrichment_db)

        recorded = next(i for i in graph.interpretations if i['file_path'] == str(directory))
        assert recorded['host'] == 'mounted:/mnt/server'


class TestFilesIndexes:
    """The indexes that make enrichment usable, and where they are allowed to live."""

    _WANTED = {'idx_files_ext_lower', 'idx_files_interpreted_as', 'idx_files_path'}

    @staticmethod
    def _file_indexes(conn):
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='files' "
            "AND name NOT LIKE 'sqlite_%'")}

    def test_init_db_creates_them(self, tmp_path):
        import sqlite3

        from scidk.core import path_index_sqlite as pix

        conn = sqlite3.connect(str(tmp_path / 'files.db'))
        pix.init_db(conn)
        assert self._WANTED <= self._file_indexes(conn)

    def test_migrate_does_not_require_a_files_table(self, tmp_path):
        """migrate() also runs against scidk_settings.db and every per-test
        database, neither of which has a files table. Creating an index on it
        there raised out of migrate() and took 86 unrelated tests with it."""
        import sqlite3

        from scidk.core import migrations

        conn = sqlite3.connect(str(tmp_path / 'settings.db'))
        assert migrations.migrate(conn) >= 26           # must not raise
        assert self._file_indexes(conn) == set()

    def test_indexes_survive_migrate_before_init_db(self, tmp_path):
        """scans_service calls migrate() on a bare pix.connect() before
        init_db(). A migration guarded on "does files exist yet" would skip,
        record the version, and leave the indexes permanently uncreated."""
        import sqlite3

        from scidk.core import migrations, path_index_sqlite as pix

        conn = sqlite3.connect(str(tmp_path / 'files.db'))
        migrations.migrate(conn)
        pix.init_db(conn)
        assert self._WANTED <= self._file_indexes(conn)

    def test_find_work_plans_an_indexed_search(self, tmp_path):
        """Both arms of the OR must be indexed or SQLite falls back to a scan."""
        import sqlite3

        from scidk.core import path_index_sqlite as pix

        conn = sqlite3.connect(str(tmp_path / 'files.db'))
        pix.init_db(conn)
        plan = ' '.join(row[-1] for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT path FROM files f WHERE f.type='file' "
            "AND (f.interpreted_as = 'fcs_interpreter' "
            "     OR lower(f.file_extension) IN ('.fcs')) LIMIT 20"))
        assert 'idx_files_ext_lower' in plan
        assert 'idx_files_interpreted_as' in plan
        assert 'SCAN' not in plan


class TestEnrichmentRoute:
    def test_run_is_admin_only_and_not_gated_on_a_nonexistent_staff_role(self):
        """@require_role('staff') would 403 everyone; auth_users allows only
        ('admin', 'user') and require_role is a flat membership test."""
        from scidk.web.routes.api_enrichment import _RUN_ROLES

        assert _RUN_ROLES == ('admin',)
        assert 'staff' not in _RUN_ROLES

    def test_blueprint_exposes_both_routes(self):
        from flask import Flask

        from scidk.web.routes import api_enrichment

        app = Flask(__name__)
        app.register_blueprint(api_enrichment.bp)
        rules = {r.rule: sorted(r.methods & {'GET', 'POST'}) for r in app.url_map.iter_rules()}
        assert rules['/api/enrichment/run'] == ['POST']
        assert rules['/api/enrichment/interpreters'] == ['GET']

    def test_register_blueprints_includes_enrichment(self):
        """register_blueprints() in web/routes/__init__.py is what app.py calls
        — importing the module is not the same as being wired in."""
        import inspect as _inspect

        from scidk.web.routes import register_blueprints

        source = _inspect.getsource(register_blueprints)
        assert 'api_enrichment.bp' in source
