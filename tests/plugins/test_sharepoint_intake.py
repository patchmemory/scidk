"""Contract tests for the SharePoint plugin (Cycle 3, Task D).

Covers only the four ``DataSourcePlugin`` methods — ``find()``, ``access()``,
``fetch()``, ``transform_library()``. Nothing here touches column→node mapping,
Neo4j writes, or scheduling: those moved to ``scidk/pipeline/`` and belong to
Pipeline tests (Cycle 3B). Transform behaviour has its own file,
``test_sharepoint_transforms.py``; template registration has
``test_sharepoint_registration.py``.

**No live SharePoint list is exercised here.** Everything runs against a local
CSV fixture and a fake rclone provider that mirrors the real interface
(``cat`` / ``open`` / ``list_files``). That is enough to pin the *structure* of
every result and the laziness of ``fetch()``, and it is what lets these tests run
offline. Two definition-of-done items are structural here and still need a live
list to confirm in the deployment:

  * ``find()`` completing in <10s against a real SharePoint list;
  * ``access()`` against genuinely valid vs. expired rclone credentials — the
    credential-rejection path is exercised with a provider that refuses to read
    object content, which is the same code path a real 403 takes.
"""
from pathlib import Path

import pytest

from plugins.sharepoint_intake import get_plugin
from plugins.sharepoint_intake.plugin import SharePointPlugin
from scidk.pipeline.plugin_base import DataSourcePlugin

FIXTURE = Path(__file__).parent / "fixtures" / "sharepoint_intake_sample.csv"


# --------------------------------------------------------------------------- #
# Test doubles — mirror the RcloneProvider surface the plugin actually uses    #
# --------------------------------------------------------------------------- #
class FakeRcloneProvider:
    """Fake rclone provider over an in-memory list of text lines.

    Records what was asked of it and, critically, how many lines have actually
    been pulled off the stream — that counter is how the laziness of ``fetch()``
    is observed rather than assumed.

    Args:
        lines: Source lines, newline-terminated, header first.
        allow_cat: When False, ``cat()`` raises the way a credential scoped to
            listing metadata does. ``open()`` and ``list_files()`` still work,
            which is what makes ``access()`` distinguishable from ``find()``.
    """

    def __init__(self, lines, allow_cat=True):
        self._chunks = [line.encode("utf-8") for line in lines]
        self.allow_cat = allow_cat
        self.lines_read = 0
        self.cat_calls = []
        self.list_calls = []
        self.open_calls = []

    @property
    def blob(self):
        return b"".join(self._chunks)

    def open(self, target):
        self.open_calls.append(target)
        owner = self

        class _Stream:
            def __init__(self):
                self._it = iter(owner._chunks)

            def __iter__(self):
                return self

            def __next__(self):
                chunk = next(self._it)
                owner.lines_read += 1
                return chunk

            def close(self):
                pass

        return _Stream()

    def cat(self, target, max_bytes=None, timeout_sec=60.0):
        self.cat_calls.append((target, max_bytes, timeout_sec))
        if not self.allow_cat:
            raise RuntimeError("403: credential may list but not read object content")
        blob = self.blob
        return blob[:max_bytes] if max_bytes is not None else blob

    def list_files(self, target, recursive=True, fast_list=False, max_depth=None):
        self.list_calls.append(target)
        return [{"Name": "intake_list.csv", "Size": len(self.blob), "IsDir": False,
                 "ModTime": "2026-07-30T12:00:00Z"}]


class BufferedOnlyProvider:
    """Provider with no ``open()`` at all — exercises the buffered ``cat`` path.

    Deliberately not a subclass: the point is the *absence* of the attribute,
    which is what a non-streaming provider actually looks like.
    """

    def __init__(self, lines):
        self._blob = "".join(lines).encode("utf-8")
        self.cat_calls = []
        self.lines_read = 0

    def cat(self, target, max_bytes=None, timeout_sec=60.0):
        self.cat_calls.append((target, max_bytes, timeout_sec))
        return self._blob[:max_bytes] if max_bytes is not None else self._blob

    def list_files(self, target, recursive=True, fast_list=False, max_depth=None):
        return []


class UnreachableProvider:
    """Provider whose target does not exist, however it is asked for."""

    def open(self, target):
        raise RuntimeError("directory not found")

    def cat(self, target, max_bytes=None, timeout_sec=60.0):
        raise RuntimeError("directory not found")

    def list_files(self, target, recursive=True, fast_list=False, max_depth=None):
        raise RuntimeError("directory not found")


def csv_lines(row_count, columns=("Col A", "Col B", "Col C")):
    """Build ``row_count`` data rows plus a header, as newline-terminated lines."""
    yield ",".join(columns) + "\n"
    for i in range(row_count):
        yield ",".join(f"r{i}c{n}" for n in range(len(columns))) + "\n"


@pytest.fixture
def no_configured_fallback(monkeypatch):
    """Ensure no persisted setting or env var leaks in as a source."""
    monkeypatch.setattr(
        "plugins.sharepoint_intake.plugin.cfg.get_config_value",
        lambda *a, **k: None,
    )


@pytest.fixture
def stub_auth_method(monkeypatch):
    """Pin the reported auth method instead of shelling out to rclone.

    ``detect_auth_method`` runs ``rclone config dump``; for a fake remote that is
    a subprocess call whose answer is always None. Stubbing it keeps these tests
    offline and lets them assert that whatever it reports reaches the caller.
    """
    monkeypatch.setattr(
        "plugins.sharepoint_intake.source.detect_auth_method",
        lambda target: "rclone_oauth",
    )


# --------------------------------------------------------------------------- #
# The contract itself                                                         #
# --------------------------------------------------------------------------- #
class TestContract:
    def test_plugin_implements_the_base_class(self):
        assert issubclass(SharePointPlugin, DataSourcePlugin)
        assert isinstance(get_plugin(), DataSourcePlugin)

    def test_declares_its_identity_and_source_types(self):
        assert SharePointPlugin.name == "sharepoint"
        assert SharePointPlugin.display_name == "SharePoint Lists"
        assert SharePointPlugin.source_types == ["sharepoint_list", "sharepoint_library"]

    def test_all_four_methods_are_implemented(self):
        plugin = get_plugin()
        for method in ("find", "access", "fetch", "transform_library"):
            assert callable(getattr(plugin, method))


# --------------------------------------------------------------------------- #
# find() — FAIR: Findable                                                     #
# --------------------------------------------------------------------------- #
class TestFind:
    def test_reports_columns_row_count_and_a_three_row_sample(self):
        result = get_plugin().find({"source_path": str(FIXTURE)})

        assert result["ok"] is True
        assert result["error"] is None
        assert result["row_count"] == 4
        assert len(result["sample"]) == 3
        assert result["columns"][:3] == ["CACProtocol", "ShortDescription", "RecordSource"]
        assert len(result["columns"]) == 17

    def test_sample_rows_are_keyed_by_column(self):
        sample = get_plugin().find({"source_path": str(FIXTURE)})["sample"]
        assert sample[0]["CACProtocol"] == "CAC-001"
        assert sample[0]["ImagingModalities"] == "MRI;PET"
        assert set(sample[0]) == set(get_plugin().find({"source_path": str(FIXTURE)})["columns"])

    def test_metadata_describes_the_source(self):
        meta = get_plugin().find({"source_path": str(FIXTURE)})["metadata"]
        assert meta["transport"] == "local"
        assert meta["source_path"] == str(FIXTURE)
        assert meta["name"] == FIXTURE.name
        assert meta["size"] > 0

    def test_sample_size_is_configurable(self):
        result = get_plugin().find({"source_path": str(FIXTURE), "sample_rows": 1})
        assert len(result["sample"]) == 1
        assert result["row_count"] == 4  # counting is unaffected by sample size

    def test_remote_source_uses_lsjson_for_metadata(self):
        provider = FakeRcloneProvider(csv_lines(2))
        result = SharePointPlugin(provider=provider).find({"source_path": "sp:intake/list.csv"})

        assert result["ok"] is True
        assert result["row_count"] == 2
        assert result["metadata"]["transport"] == "rclone"
        assert result["metadata"]["name"] == "intake_list.csv"
        assert provider.list_calls == ["sp:intake/list.csv"]

    def test_row_count_is_none_and_flagged_when_counting_is_capped(self):
        result = get_plugin().find({"source_path": str(FIXTURE), "max_scan_rows": 2})

        assert result["ok"] is True
        assert result["row_count"] is None
        assert result["metadata"]["row_count_truncated"] is True
        assert result["columns"]  # the schema is still reported
        assert len(result["sample"]) == 2  # what it did read is still returned

    def test_junk_knobs_fall_back_to_defaults_rather_than_failing(self):
        result = get_plugin().find(
            {"source_path": str(FIXTURE), "sample_rows": "three", "max_scan_rows": None})
        assert result["ok"] is True
        assert len(result["sample"]) == 3
        assert result["row_count"] == 4

    def test_headers_with_doubled_spaces_are_normalized(self):
        provider = FakeRcloneProvider(["PI  Archived,Other\n", "a,b\n"])
        result = SharePointPlugin(provider=provider).find({"source_path": "sp:x.csv"})
        assert result["columns"] == ["PI Archived", "Other"]

    def test_unreachable_source_is_a_result_not_an_exception(self):
        result = SharePointPlugin(provider=UnreachableProvider()).find(
            {"source_path": "sp:missing/list.csv"})

        assert result["ok"] is False
        assert "not found" in result["error"]
        assert result["columns"] == [] and result["sample"] == []
        assert result["row_count"] is None

    def test_missing_source_reports_how_to_configure_one(self, no_configured_fallback):
        result = get_plugin().find({})
        assert result["ok"] is False
        assert "source_path" in result["error"]

    def test_keeps_memory_flat_on_a_long_list(self):
        # 5000 rows, sample of 3: the sample is what bounds memory, not the list.
        provider = FakeRcloneProvider(csv_lines(5000))
        result = SharePointPlugin(provider=provider).find({"source_path": "sp:big.csv"})
        assert result["row_count"] == 5000
        assert len(result["sample"]) == 3


# --------------------------------------------------------------------------- #
# access() — FAIR: Accessible                                                 #
# --------------------------------------------------------------------------- #
class TestAccess:
    def test_ok_for_a_readable_local_source(self):
        result = get_plugin().access({"source_path": str(FIXTURE)})
        assert result == {"ok": True, "auth_method": "local", "error": None}

    def test_ok_for_a_readable_remote_and_reads_only_one_byte(self, stub_auth_method):
        provider = FakeRcloneProvider(csv_lines(100))
        result = SharePointPlugin(provider=provider).access({"source_path": "sp:intake/list.csv"})

        assert result == {"ok": True, "auth_method": "rclone_oauth", "error": None}
        assert provider.cat_calls == [("sp:intake/list.csv", 1, 120.0)]

    def test_rejected_credential_is_a_result_not_an_exception(self, stub_auth_method):
        provider = FakeRcloneProvider(csv_lines(3), allow_cat=False)
        result = SharePointPlugin(provider=provider).access({"source_path": "sp:intake/list.csv"})

        assert result["ok"] is False
        assert "403" in result["error"]
        # The auth method is still reported: knowing which credential was refused
        # is exactly what makes the failure actionable.
        assert result["auth_method"] == "rclone_oauth"

    def test_unknown_auth_method_does_not_block_a_verdict(self):
        # detect_auth_method returns None for an unrecognized remote; that is not
        # itself a failure, so access() still reports ok.
        provider = FakeRcloneProvider(csv_lines(2))
        result = SharePointPlugin(provider=provider).access({"source_path": "notaremote:x.csv"})
        assert result["ok"] is True
        assert result["auth_method"] is None

    def test_is_distinct_from_find(self):
        # A credential that may list and stream metadata but not read object
        # content: find() succeeds, access() does not. This is the whole reason
        # the two methods exist separately.
        provider = FakeRcloneProvider(csv_lines(3), allow_cat=False)
        plugin = SharePointPlugin(provider=provider)

        assert plugin.find({"source_path": "sp:intake/list.csv"})["ok"] is True
        assert plugin.access({"source_path": "sp:intake/list.csv"})["ok"] is False

    def test_missing_source_reports_how_to_configure_one(self, no_configured_fallback):
        result = get_plugin().access({})
        assert result["ok"] is False
        assert result["auth_method"] is None
        assert "source_path" in result["error"]


# --------------------------------------------------------------------------- #
# fetch() — FAIR: Interoperable                                               #
# --------------------------------------------------------------------------- #
class TestFetch:
    def test_yields_every_row_keyed_by_column(self):
        rows = list(get_plugin().fetch({"source_path": str(FIXTURE)}))
        assert len(rows) == 4
        assert rows[0]["CACProtocol"] == "CAC-001"
        assert rows[1]["RecordSource"] == "Drupal"

    def test_values_are_raw_with_no_transforms_applied(self):
        rows = list(get_plugin().fetch({"source_path": str(FIXTURE)}))

        # Multi-choice stays a delimited string; the Pipeline splits it later.
        assert rows[0]["ImagingModalities"] == "MRI;PET"
        # A people column stays RFC 5322 text, unparsed.
        assert rows[0]["PI Archived"] == "Dr Pat Kim <pat@mit.edu>"
        # No boolean coercion, and no case normalization of an address.
        assert rows[0]["HasLargeAttachment"] == "false"
        assert rows[1]["UserEmail_orig"] == "John@Old.edu"
        assert all(isinstance(v, str) for v in rows[0].values())

    def test_is_lazy_and_does_not_load_the_full_list(self):
        # N+1 rows on the wire; take one and confirm the rest were never pulled.
        provider = FakeRcloneProvider(csv_lines(1000))
        rows = SharePointPlugin(provider=provider).fetch({"source_path": "sp:big.csv"})

        first = next(rows)
        assert first["Col A"] == "r0c0"
        assert provider.lines_read < 10, "fetch() buffered the list instead of streaming it"

        for _ in range(2):
            next(rows)
        assert provider.lines_read < 12

        # Draining it does read everything — laziness, not truncation.
        assert sum(1 for _ in rows) == 997
        assert provider.lines_read == 1001

    def test_returns_an_iterator_rather_than_a_materialized_list(self):
        provider = FakeRcloneProvider(csv_lines(50))
        rows = SharePointPlugin(provider=provider).fetch({"source_path": "sp:x.csv"})
        assert iter(rows) is iter(rows)
        assert not isinstance(rows, (list, tuple))

    def test_falls_back_to_a_buffered_read_when_the_provider_cannot_stream(self):
        provider = BufferedOnlyProvider(csv_lines(3))
        rows = list(SharePointPlugin(provider=provider).fetch({"source_path": "sp:x.csv"}))

        assert len(rows) == 3
        assert provider.cat_calls  # took the documented non-lazy path
        assert provider.lines_read == 0

    def test_blank_lines_are_skipped(self):
        provider = FakeRcloneProvider(["A,B\n", "1,2\n", "\n", ",\n", "3,4\n"])
        rows = list(SharePointPlugin(provider=provider).fetch({"source_path": "sp:x.csv"}))
        assert rows == [{"A": "1", "B": "2"}, {"A": "3", "B": "4"}]

    def test_tab_delimited_source_is_detected_by_extension(self):
        provider = FakeRcloneProvider(["A\tB\n", "1\t2\n"])
        rows = list(SharePointPlugin(provider=provider).fetch({"source_path": "sp:x.tsv"}))
        assert rows == [{"A": "1", "B": "2"}]

    def test_quoted_field_spanning_newlines_parses_as_one_value(self):
        provider = FakeRcloneProvider(['A,B\n', '"line one\n', 'line two",2\n'])
        rows = list(SharePointPlugin(provider=provider).fetch({"source_path": "sp:x.csv"}))
        assert rows == [{"A": "line one\nline two", "B": "2"}]

    def test_missing_source_raises_eagerly(self, no_configured_fallback):
        # Raised on the call, not on first iteration, so the misconfiguration
        # surfaces where it was made.
        with pytest.raises(ValueError, match="source_path"):
            get_plugin().fetch({})

    def test_accepts_the_legacy_source_keys(self):
        for key in ("source_path", "source", "file_path"):
            rows = list(get_plugin().fetch({key: str(FIXTURE)}))
            assert len(rows) == 4, f"key {key!r} was not honoured"

    def test_configured_setting_is_used_when_no_instance_key_is_given(self, monkeypatch):
        monkeypatch.setattr(
            "plugins.sharepoint_intake.plugin.cfg.get_config_value",
            lambda *a, **k: str(FIXTURE),
        )
        assert len(list(get_plugin().fetch({}))) == 4


# --------------------------------------------------------------------------- #
# transform_library() — FAIR: Reproducible                                    #
# --------------------------------------------------------------------------- #
class TestTransformLibrary:
    def test_publishes_the_six_sharepoint_transforms(self):
        # Behaviour of each transform lives in test_sharepoint_transforms.py;
        # what the contract guarantees is the shape of the library.
        library = get_plugin().transform_library()
        assert set(library) == {
            "parse_rfc5322", "parse_rfc5322_list", "sp_multiselect",
            "sp_date", "sp_yesno", "sp_colresolution",
        }
        assert all(callable(fn) for fn in library.values())
