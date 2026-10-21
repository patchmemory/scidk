"""
The LwM demo fixture: a stub folder tree, its files.db from the real scanner, and the
study graph. See README.md in this folder; build_tree.py regenerates tree/ and graph/.

Nothing here connects to Neo4j unless a session is passed to load_into().
"""
import csv
import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
TREE = HERE / "tree"
GRAPH = HERE / "graph"
MANIFEST = HERE / "manifest.csv"
FOLDERS = HERE / "folders.csv"
SCANNER = REPO / "tools" / "scidk_scanner_opt.py"
LOADER = REPO / "demo_data" / "lwm2026" / "load_demo_graph.py"

# load_demo_graph.py README: expected node counts for the study graph
EXPECTED_NODE_COUNTS = {
    "ImagingSession": 318, "Measurement": 238, "Subject": 13, "Observation": 15,
    "Modality": 3, "Study": 1, "Folder": 615, "File": 386, "Acquisition": 427,
    "Instrument": 3, "Host": 5,
}


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def materialize(dest):
    """Copy tree/ to dest, recreate empty folders and apply the listed dates.

    git keeps neither empty folders nor mtimes, so scan this, not tree/ itself.
    Returns dest as a Path.
    """
    dest = Path(dest)
    shutil.copytree(TREE, dest, dirs_exist_ok=True)
    for row in read_csv(FOLDERS):
        (dest / row["path"]).mkdir(parents=True, exist_ok=True)
    for row in read_csv(MANIFEST):
        if row["listed_date"]:
            t = datetime.strptime(row["listed_date"], "%Y-%m-%d").replace(
                hour=12, tzinfo=timezone.utc).timestamp()
            os.utime(dest / row["path"], (t, t))
    return dest


def build_files_db(db_path, root):
    """Run the real CLI scanner over root, writing db_path. Returns the scan id."""
    subprocess.run(
        [sys.executable, str(SCANNER), str(root), "--db", str(db_path), "--no-hash", "--quiet"],
        check=True, capture_output=True, text=True, cwd=str(REPO))
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT id FROM scans ORDER BY started DESC LIMIT 1").fetchone()[0]


def _loader():
    spec = importlib.util.spec_from_file_location("load_demo_graph", LOADER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def graph_statements():
    """The Cypher statements load_demo_graph.py would run for graph/:
    a list of (name, cypher, params, rows)."""
    mod = _loader()
    return mod.statements(*mod.read_data(GRAPH))


def graph_data():
    """read_data(graph/) from load_demo_graph.py:
    (meta, subjects, sessions, measurements, observations, nexts, nodes, links)."""
    return _loader().read_data(GRAPH)


def node_counts():
    """Nodes per label the loader would create, counted from the data, not a database."""
    meta, subjects, sessions, measurements, obs, _, nodes, _ = graph_data()
    counts = Counter({"Study": 1, "Modality": len(meta["modalities"]),
                      "Subject": len(subjects), "ImagingSession": len(sessions),
                      "Measurement": len(measurements), "Observation": len(obs)})
    counts.update(n["kind"] for n in nodes)
    return dict(counts)


def load_into(session):
    """Load the study graph through an open neo4j session, as load_demo_graph.py does.

    Every node carries demo_dataset = 'LWM-DEMO-2026'. Only call this against a
    throwaway database.
    """
    mod = _loader()
    for ix in mod.INDEXES:
        session.run(ix).consume()
    for _, cy, params, rows in graph_statements():
        if rows is None:
            session.run(cy, **params).consume()
            continue
        for i in range(0, len(rows), mod.BATCH):
            session.run(cy, rows=rows[i:i + mod.BATCH], **params).consume()
