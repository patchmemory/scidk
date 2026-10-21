"""The LwM demo fixture loads: stub tree, scanner-built files.db, study graph.

Fixtures come from tests/fixtures/demo/pytest_plugin.py. The live-Neo4j test runs only
when SCIDK_DEMO_NEO4J_URI points at a throwaway database (never the .env one).
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.fixtures.demo import demo_fixture as demo

MANIFEST = demo.read_csv(demo.MANIFEST)
FOLDERS = demo.read_csv(demo.FOLDERS)


def test_tree_matches_manifest():
    on_disk = {p.relative_to(demo.TREE).as_posix() for p in demo.TREE.rglob("*") if p.is_file()}
    assert on_disk == {r["path"] for r in MANIFEST}
    for r in MANIFEST:
        size = (demo.TREE / r["path"]).stat().st_size
        assert (size > 0) == (r["kind"] == "metadata"), r["path"]


def test_folder_totals_keep_the_real_listing():
    by_path = {r["path"]: r for r in FOLDERS}
    root = by_path["dropbox/MultiModal/LungTumor"]
    assert int(root["listed_files"]) == 49758          # dropbox_lungtumor_files.tsv
    assert int(root["listed_bytes"]) == 154258187836
    assert sum(1 for r in FOLDERS if r["source"] == "atwai" and r["listed_files"]) == 946 + 1128


def test_materialize_restores_folders_and_dates(demo_tree):
    for r in FOLDERS:
        assert (demo_tree / r["path"]).is_dir(), r["path"]
    clickinfo = next(r for r in MANIFEST if r["path"].endswith("ClickInfo.txt"))
    mtime = (demo_tree / clickinfo["path"]).stat().st_mtime
    assert datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%d") == clickinfo["listed_date"]


def test_scanner_builds_files_db(demo_tree, demo_files_db):
    db, scan_id = demo_files_db
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT status, root FROM scans WHERE id=?", (scan_id,)).fetchone() \
            == ("complete", str(Path(demo_tree).resolve()))
        paths = {Path(p).relative_to(Path(demo_tree).resolve()).as_posix() for (p,) in conn.execute(
            "SELECT path FROM files WHERE scan_id=? AND type='file'", (scan_id,))}
        assert paths == {r["path"] for r in MANIFEST}
        n_folders = conn.execute(
            "SELECT count(*) FROM files WHERE scan_id=? AND type='folder'", (scan_id,)).fetchone()[0]
        assert n_folders >= len(FOLDERS)
        # every ParaVision acquisition folder (method + acqp + fid) is recognised
        mri = conn.execute("SELECT count(*) FROM files WHERE scan_id=? AND type='folder' "
                           "AND interpreted_as='bruker_mri_interpreter'", (scan_id,)).fetchone()[0]
        assert mri == sum(1 for r in MANIFEST if r["path"].endswith("/fid"))


def test_study_graph_node_counts():
    assert demo.node_counts() == demo.EXPECTED_NODE_COUNTS


def test_study_graph_links_resolve():
    """Every link endpoint exists, so the loader's MATCH ... MERGE never silently drops one."""
    meta, subjects, sessions, measurements, obs, nexts, nodes, links = demo.graph_data()
    ids = {"Study": {meta["study"]["id"]}, "Modality": {m["name"] for m in meta["modalities"]},
           "Subject": {s["id"] for s in subjects}, "ImagingSession": {s["id"] for s in sessions},
           "Measurement": {m["id"] for m in measurements}, "Observation": {o["id"] for o in obs}}
    for n in nodes:
        ids.setdefault(n["kind"], set()).add(n["id"])
    for l in links:
        assert l["src"] in ids[l["src_label"]], l
        assert l["dst"] in ids[l["dst_label"]], l
    for s in sessions:
        assert s["subject"] in ids["Subject"] and s["modality"] in ids["Modality"]
    for m in measurements:
        assert m["session_id"] in ids["ImagingSession"]
    assert all(n["a"] in ids["ImagingSession"] and n["b"] in ids["ImagingSession"] for n in nexts)


@pytest.mark.skipif(not os.environ.get("SCIDK_DEMO_NEO4J_URI"),
                    reason="set SCIDK_DEMO_NEO4J_URI (+ _USER/_PASSWORD) to a throwaway Neo4j")
def test_study_graph_loads_into_neo4j():
    neo4j = pytest.importorskip("neo4j")
    drv = neo4j.GraphDatabase.driver(
        os.environ["SCIDK_DEMO_NEO4J_URI"],
        auth=(os.environ.get("SCIDK_DEMO_NEO4J_USER", "neo4j"),
              os.environ.get("SCIDK_DEMO_NEO4J_PASSWORD", "")))
    try:
        with drv.session() as ses:
            ses.run("MATCH (n {demo_dataset: 'LWM-DEMO-2026'}) DETACH DELETE n").consume()
            demo.load_into(ses)
            counts = {r["label"]: r["n"] for r in ses.run(
                "MATCH (n {demo_dataset: 'LWM-DEMO-2026'}) "
                "RETURN labels(n)[0] AS label, count(*) AS n")}
        assert counts == demo.EXPECTED_NODE_COUNTS
    finally:
        drv.close()
