"""The built-in local-file source behind Task B's file upload option.

Task B requires both connection options — an rclone remote path and a file
upload — to produce the same thing for the next step: a column list and a row
sample. That is why this implements the same ``DataSourcePlugin`` contract the
SharePoint plugin does rather than being a special case in the upload route.
"""
from __future__ import annotations

import os

import pytest

from scidk.pipeline.file_source import TabularFilePlugin, upload_dir
from scidk.pipeline.plugin_base import DataSourcePlugin


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "equipment.csv"
    path.write_text(
        "Asset ID,Name,Purchased\n"
        "A-1,Microscope,2024-01-05\n"
        "A-2,Centrifuge,2023-11-30\n"
        "A-3,Incubator,2022-06-01\n",
        encoding="utf-8",
    )
    return str(path)


def test_implements_the_plugin_contract():
    assert isinstance(TabularFilePlugin(), DataSourcePlugin)


def test_find_returns_columns_and_a_sample(csv_file):
    result = TabularFilePlugin().find({"source_path": csv_file})

    assert result["ok"] is True
    assert result["columns"] == ["Asset ID", "Name", "Purchased"]
    assert result["row_count"] == 3
    assert len(result["sample"]) == 3
    assert result["sample"][0]["Name"] == "Microscope"
    assert result["metadata"]["format"] == "delimited"


def test_sample_size_is_configurable(csv_file):
    result = TabularFilePlugin().find({"source_path": csv_file, "sample_rows": 1})
    assert len(result["sample"]) == 1
    assert result["row_count"] == 3, "sampling less does not stop the count"


def test_fetch_streams_every_row(csv_file):
    rows = list(TabularFilePlugin().fetch({"source_path": csv_file}))
    assert [r["Asset ID"] for r in rows] == ["A-1", "A-2", "A-3"]


def test_fetch_is_lazy(csv_file):
    stream = TabularFilePlugin().fetch({"source_path": csv_file})
    assert next(stream)["Asset ID"] == "A-1"
    stream.close()


def test_access_confirms_the_bytes_are_readable(csv_file):
    result = TabularFilePlugin().access({"source_path": csv_file})
    assert result == {"ok": True, "auth_method": "local", "error": None}


def test_a_missing_file_is_a_result_not_an_exception(tmp_path):
    result = TabularFilePlugin().find({"source_path": str(tmp_path / "nope.csv")})
    assert result["ok"] is False
    assert "does not exist" in result["error"]


def test_no_configured_path_is_a_result_not_an_exception():
    result = TabularFilePlugin().find({})
    assert result["ok"] is False and "No file configured" in result["error"]


def test_fetch_raises_eagerly_for_a_misconfiguration(tmp_path):
    """At the call site, not on first iteration, so the traceback points somewhere useful."""
    with pytest.raises(ValueError):
        TabularFilePlugin().fetch({"source_path": str(tmp_path / "nope.csv")})


def test_transform_library_is_empty_because_a_csv_cell_is_just_text():
    assert TabularFilePlugin().transform_library() == {}


# ------------------------------------------------------------- formats

def test_tsv_is_split_on_tabs(tmp_path):
    path = tmp_path / "x.tsv"
    path.write_text("A\tB\n1\t2\n", encoding="utf-8")
    result = TabularFilePlugin().find({"source_path": str(path)})
    assert result["columns"] == ["A", "B"]
    assert result["sample"][0] == {"A": "1", "B": "2"}


def test_excel_bom_and_header_whitespace(tmp_path):
    """Excel writes a BOM; SharePoint exports double-space some headers."""
    path = tmp_path / "x.csv"
    path.write_bytes("﻿PI  Archived,Other\nJane,1\n".encode("utf-8"))
    result = TabularFilePlugin().find({"source_path": str(path)})
    assert result["columns"] == ["PI Archived", "Other"]


def test_xlsx_round_trip(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "book.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Intake"
    sheet.append(["ID", "Name"])
    sheet.append(["p1", "Study one"])
    workbook.save(path)

    result = TabularFilePlugin().find({"source_path": str(path)})
    assert result["ok"] is True
    assert result["columns"] == ["ID", "Name"]
    assert result["sample"][0]["Name"] == "Study one"
    assert result["metadata"]["format"] == "excel"


def test_a_missing_worksheet_names_the_sheets_that_do_exist(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    path = tmp_path / "book.xlsx"
    workbook = openpyxl.Workbook()
    workbook.active.append(["A"])
    workbook.save(path)

    result = TabularFilePlugin().find({"source_path": str(path), "sheet": "Nope"})
    assert result["ok"] is False
    assert "Nope" in result["error"] and "Sheet" in result["error"]


# --------------------------------------------------------- ragged rows

def test_a_trailing_blank_line_is_not_a_row(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("A,B\n1,2\n\n", encoding="utf-8")
    assert TabularFilePlugin().find({"source_path": str(path)})["row_count"] == 1


def test_a_short_row_leaves_trailing_columns_absent(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("A,B,C\n1\n", encoding="utf-8")
    row = next(TabularFilePlugin().fetch({"source_path": str(path)}))
    assert row == {"A": "1", "B": None, "C": None}


def test_a_long_row_keeps_its_extra_values_rather_than_dropping_data(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("A\n1,2\n", encoding="utf-8")
    row = next(TabularFilePlugin().fetch({"source_path": str(path)}))
    assert row == {"A": "1", "column_2": "2"}


def test_an_unnamed_column_is_still_addressable(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("A,,C\n1,2,3\n", encoding="utf-8")
    result = TabularFilePlugin().find({"source_path": str(path)})
    assert result["columns"] == ["A", "column_2", "C"]


# ------------------------------------------------------------- base_dir

def test_base_dir_confines_an_uploaded_source(tmp_path):
    """A crafted source_path on an uploaded source must not become a file read."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    inside = uploads / "ok.csv"
    inside.write_text("A\n1\n", encoding="utf-8")
    outside = tmp_path / "secret.csv"
    outside.write_text("A\n2\n", encoding="utf-8")

    plugin = TabularFilePlugin(base_dir=str(uploads))
    assert plugin.find({"source_path": str(inside)})["ok"] is True

    blocked = plugin.find({"source_path": str(outside)})
    assert blocked["ok"] is False
    assert "outside the permitted directory" in blocked["error"]


def test_base_dir_is_not_defeated_by_a_prefix_that_merely_starts_the_same(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    sibling = tmp_path / "uploads-evil"
    sibling.mkdir()
    target = sibling / "x.csv"
    target.write_text("A\n1\n", encoding="utf-8")

    result = TabularFilePlugin(base_dir=str(uploads)).find({"source_path": str(target)})
    assert result["ok"] is False


def test_base_dir_is_not_defeated_by_dot_dot(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    outside = tmp_path / "secret.csv"
    outside.write_text("A\n1\n", encoding="utf-8")

    escape = str(uploads / ".." / "secret.csv")
    assert TabularFilePlugin(base_dir=str(uploads)).find({"source_path": escape})["ok"] is False


def test_no_base_dir_trusts_an_admin_configured_path(csv_file):
    assert TabularFilePlugin().find({"source_path": csv_file})["ok"] is True


# ------------------------------------------------------------ upload_dir

def test_upload_dir_prefers_app_config_then_env(monkeypatch, tmp_path):
    class FakeApp:
        config = {"SCIDK_PIPELINE_UPLOAD_DIR": str(tmp_path / "from_config")}

    monkeypatch.setenv("SCIDK_PIPELINE_UPLOAD_DIR", str(tmp_path / "from_env"))
    assert upload_dir(FakeApp()) == os.path.realpath(str(tmp_path / "from_config"))
    assert upload_dir(None) == os.path.realpath(str(tmp_path / "from_env"))


def test_upload_dir_creates_only_when_asked(monkeypatch, tmp_path):
    target = tmp_path / "uploads"
    monkeypatch.setenv("SCIDK_PIPELINE_UPLOAD_DIR", str(target))
    upload_dir(None)
    assert not target.exists()
    upload_dir(None, create=True)
    assert target.is_dir()
