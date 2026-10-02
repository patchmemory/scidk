#!/usr/bin/env python3
"""
load_demo_graph.py — load the LwM demo study (data/) into Neo4j.

Every node it writes carries {demo_dataset, synthetic}; --wipe removes exactly
those nodes, without touching anything else in the graph. Safe to re-run
(MERGE throughout).

Schema (same shape scidk_annotate.py writes for real data):

  (Study)-[:INCLUDES]->(Subject)
  (Study)-[:USES_MODALITY]->(Modality)
  (Study)-[:HAS_DATA]->(ImagingSession)
  (ImagingSession)-[:OF_SUBJECT]->(Subject)
  (ImagingSession)-[:IMAGED_WITH]->(Modality)
  (ImagingSession)-[:HAS_MEASUREMENT]->(Measurement)
  (ImagingSession)-[:NEXT {gap_weeks}]->(ImagingSession)   same mouse + modality
  (Observation)-[:ABOUT]->(Study|Modality|Subject|ImagingSession)
  (Observation)-[:CONTRASTS]->(Modality)

Files on disk and instrument metadata (data/nodes.csv, data/links.csv; File/Folder
are the labels SciDK uses):

  (Study)-[:HAS_FOLDER]->(Folder)                 top folders on Dropbox and atwai
  (Folder)-[:CONTAINS]->(Folder|File)
  (ImagingSession)-[:STORED_IN]->(Folder|File)    where the acquired data is
  (ImagingSession|Subject)-[:HAS_DERIVED]->(Folder|File)   exports, ROIs, conversions
  (Folder|File)-[:COPY_OF]->(Folder|File)         duplicates point at the canonical copy
  (Measurement)-[:REPORTED_IN]->(File)            the results table a value came from
  (ImagingSession)-[:HAS_ACQUISITION]->(Acquisition)   each scan/series/image, with its
                                                  instrument parameters and timestamps
  (Acquisition)-[:ON_INSTRUMENT]->(Instrument)     scanner, serial, software, rate, time model
  (Modality)-[:USES_INSTRUMENT]->(Instrument)

Usage:
  python3 load_demo_graph.py --password ...            # load + verify
  python3 load_demo_graph.py --password ... --wipe     # remove demo, then load
  python3 load_demo_graph.py --password ... --wipe-only
  python3 load_demo_graph.py --dry-run                 # no connection; print plan

Connection defaults come from NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD /
NEO4J_DATABASE.
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

BATCH = 500


def read_data(d):
    d = Path(d)
    meta = json.loads((d / "study.json").read_text())
    with (d / "subjects.csv").open() as fh:
        subjects = list(csv.DictReader(fh))
    with (d / "sessions.csv").open() as fh:
        sessions = list(csv.DictReader(fh))
    with (d / "measurements.csv").open() as fh:
        measurements = list(csv.DictReader(fh))
    obs = json.loads((d / "observations.json").read_text())
    def typed(v):
        if v in ("True", "False"):
            return v == "True"
        for cast in (int, float):
            try:
                x = cast(v)
                return int(x) if cast is float and x.is_integer() and "e" not in v.lower() \
                    and "." in v and v.endswith(".0") else x
            except ValueError:
                pass
        return v

    files, flinks = [], []
    if (d / "nodes.csv").exists():
        with (d / "nodes.csv").open() as fh:
            for r in csv.DictReader(fh):
                files.append({k: (v if k in ("id", "kind", "path", "name", "subject", "serial",
                                              "scan_name", "click", "matrix", "fov_mm", "slices")
                                  else typed(v))
                              for k, v in r.items() if v not in ("", None)})
        with (d / "links.csv").open() as fh:
            flinks = list(csv.DictReader(fh))

    for i, s in enumerate(subjects):
        subjects[i] = s = {k: v for k, v in s.items() if v != ""}   # unknown fields stay unset
        if "age_at_inoculation_wk" in s:
            s["age_at_inoculation_wk"] = int(s["age_at_inoculation_wk"])
    for s in sessions:
        s["study_week"] = int(s["study_week"])
        s["params"] = json.loads(s.pop("params_json"))
        s.pop("folder", None)
    for m in measurements:
        m["value"] = float(m["value"])
        m["detected"] = m["detected"] == "True"
        m["id"] = f"{m['session_id']}:{m['kind']}"

    # NEXT chain: consecutive sessions per (subject, modality)
    chains = {}
    for s in sessions:
        chains.setdefault((s["subject"], s["modality"]), []).append(s)
    nexts = []
    for seq in chains.values():
        seq.sort(key=lambda x: x["study_week"])
        for a, b in zip(seq, seq[1:]):
            nexts.append({"a": a["id"], "b": b["id"],
                          "gap_weeks": b["study_week"] - a["study_week"]})
    return meta, subjects, sessions, measurements, obs, nexts, files, flinks


def statements(meta, subjects, sessions, measurements, obs, nexts, files=(), flinks=()):
    ds = meta["dataset"]
    study = meta["study"]
    tag = "n.demo_dataset = $ds, n.synthetic = $syn"
    out = []

    out.append(("study", f"""
        MERGE (n:Study {{id: $id}})
        SET n += $props, {tag}""",
        {"id": study["id"], "props": {k: v for k, v in study.items() if k != "id"}}, None))

    out.append(("modalities", f"""
        UNWIND $rows AS row
        MERGE (n:Modality {{name: row.name}})
        SET n += row, {tag}
        WITH n MATCH (st:Study {{id: $sid}})
        MERGE (st)-[:USES_MODALITY]->(n)""", {"sid": study["id"]}, meta["modalities"]))

    out.append(("subjects", f"""
        UNWIND $rows AS row
        MERGE (n:Subject {{id: row.id, study_id: row.study_id}})
        SET n += row, {tag}
        WITH n MATCH (st:Study {{id: $sid}})
        MERGE (st)-[:INCLUDES]->(n)""", {"sid": study["id"]}, subjects))

    out.append(("imaging sessions", f"""
        UNWIND $rows AS row
        MERGE (n:ImagingSession {{id: row.id}})
        SET n.modality = row.modality, n.study_week = row.study_week,
            n.acq_date = row.acq_date, n.root_path = row.root_path,
            n.pattern_name = row.pattern_name, {tag}
        SET n += row.params
        WITH n, row
        MATCH (st:Study {{id: $sid}})
        MATCH (su:Subject {{id: row.subject, study_id: $sid}})
        MATCH (mo:Modality {{name: row.modality}})
        MERGE (st)-[:HAS_DATA]->(n)
        MERGE (n)-[:OF_SUBJECT]->(su)
        MERGE (n)-[:IMAGED_WITH]->(mo)""", {"sid": study["id"]}, sessions))

    out.append(("measurements", f"""
        UNWIND $rows AS row
        MERGE (n:Measurement {{id: row.id}})
        SET n.kind = row.kind, n.value = row.value, n.unit = row.unit,
            n.method = row.method, n.detected = row.detected, {tag}
        WITH n, row
        MATCH (se:ImagingSession {{id: row.session_id}})
        MERGE (se)-[:HAS_MEASUREMENT]->(n)""", {}, measurements))

    out.append(("session timeline (NEXT)", """
        UNWIND $rows AS row
        MATCH (a:ImagingSession {id: row.a})
        MATCH (b:ImagingSession {id: row.b})
        MERGE (a)-[r:NEXT]->(b)
        SET r.gap_weeks = row.gap_weeks""", {}, nexts))

    obs_rows, about_rows = [], []
    for o in obs:
        props = {k: v for k, v in o.items() if k not in ("about", "contrasts")}
        obs_rows.append({"id": o["id"], "props": props, "contrasts": o.get("contrasts", [])})
        for t in o.get("about", []):
            about_rows.append({"obs": o["id"], "type": t["type"],
                               "key": "name" if t["type"] == "Modality" else "id",
                               "val": t["id"]})
    out.append(("observations", f"""
        UNWIND $rows AS row
        MERGE (n:Observation {{id: row.id}})
        SET n += row.props, {tag}""", {}, obs_rows))
    out.append(("observation targets (ABOUT)", """
        UNWIND $rows AS row
        MATCH (n:Observation {id: row.obs})
        MATCH (x)
        WHERE x.demo_dataset = $ds AND row.type IN labels(x) AND x[row.key] = row.val
        MERGE (n)-[:ABOUT]->(x)""", {}, about_rows))
    out.append(("observation contrasts", """
        UNWIND $rows AS row
        MATCH (n:Observation {id: row.id})
        UNWIND row.contrasts AS m
        MATCH (mo:Modality {name: m})
        MERGE (n)-[:CONTRASTS]->(mo)""", {}, [r for r in obs_rows if r["contrasts"]]))

    for kind in sorted({f["kind"] for f in files}):
        rows = [{"id": f["id"], "props": {k: v for k, v in f.items() if k not in ("id", "kind")}}
                for f in files if f["kind"] == kind]
        if rows:
            out.append((f"nodes: {kind}", f"""
        UNWIND $rows AS row
        MERGE (n:{kind} {{id: row.id}})
        SET n += row.props, {tag}""", {}, rows))
    groups = {}
    for l in flinks:
        groups.setdefault((l["src_label"], l["rel"], l["dst_label"]), []).append(
            {"src": l["src"], "dst": l["dst"]})
    key = lambda label: "name" if label == "Modality" else "id"     # how each label is keyed
    for (sl, rel, dl), rows in sorted(groups.items()):
        out.append((f"links {sl}-{rel}->{dl}", f"""
        UNWIND $rows AS row
        MATCH (a:{sl} {{{key(sl)}: row.src}})
        MATCH (b:{dl} {{{key(dl)}: row.dst}})
        MERGE (a)-[:{rel}]->(b)""", {}, rows))

    for q in out:
        q[2]["ds"] = ds
        q[2]["syn"] = bool(meta.get("synthetic", True))
    return out


INDEXES = [
    "CREATE INDEX lwm_session_id IF NOT EXISTS FOR (n:ImagingSession) ON (n.id)",
    "CREATE INDEX lwm_measurement_id IF NOT EXISTS FOR (n:Measurement) ON (n.id)",
    "CREATE INDEX lwm_subject_id IF NOT EXISTS FOR (n:Subject) ON (n.id)",
    "CREATE INDEX lwm_observation_id IF NOT EXISTS FOR (n:Observation) ON (n.id)",
    "CREATE INDEX lwm_file_id IF NOT EXISTS FOR (n:File) ON (n.id)",
    "CREATE INDEX lwm_folder_id IF NOT EXISTS FOR (n:Folder) ON (n.id)",
    "CREATE INDEX lwm_acquisition_id IF NOT EXISTS FOR (n:Acquisition) ON (n.id)",
    "CREATE INDEX lwm_instrument_id IF NOT EXISTS FOR (n:Instrument) ON (n.id)",
]

VERIFY = """
MATCH (n) WHERE n.demo_dataset = $ds
WITH labels(n)[0] AS label, count(*) AS n
RETURN label, n ORDER BY label"""

EXPECT_GAPS = """
MATCH (a:ImagingSession)-[r:NEXT]->(b)
WHERE r.gap_weeks > 1
RETURN a.modality AS modality, a.study_week AS last_before,
       b.study_week AS first_after, count(*) AS subjects
ORDER BY modality"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(Path(__file__).parent / "data"))
    ap.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    ap.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    ap.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD"))
    ap.add_argument("--database", default=os.environ.get("NEO4J_DATABASE"))
    ap.add_argument("--wipe", action="store_true", help="delete demo nodes before loading")
    ap.add_argument("--wipe-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = read_data(args.data)
    meta = data[0]
    stmts = statements(*data)
    print(f"{meta['dataset']} ({'synthetic' if meta.get('synthetic', True) else 'real values'}) from {args.data}")
    for name, _, _, rows in stmts:
        print(f"  {name:28s} {len(rows) if rows is not None else 1:>5} row(s)")
    if args.dry_run:
        return
    if not args.password:
        sys.exit("Need --password or NEO4J_PASSWORD")

    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    drv.verify_connectivity()
    kw = {"database": args.database} if args.database else {}
    with drv.session(**kw) as ses:
        if args.wipe or args.wipe_only:
            n = ses.run("MATCH (n {demo_dataset: $ds}) DETACH DELETE n "
                        "RETURN count(*) AS n", ds=meta["dataset"]).single()["n"]
            print(f"wiped {n} demo nodes")
            if args.wipe_only:
                return
        for ix in INDEXES:
            try:
                ses.run(ix).consume()
            except Exception as e:   # e.g. an existing constraint already covers it
                print(f"  (index skipped: {type(e).__name__})")
        for name, cy, params, rows in stmts:
            if rows is None:
                ses.run(cy, **params).consume()
                continue
            for i in range(0, len(rows), BATCH):
                ses.run(cy, rows=rows[i:i + BATCH], **params).consume()
        print("\nnode counts:")
        for r in ses.run(VERIFY, ds=meta["dataset"]):
            print(f"  {r['label']:16s} {r['n']:>5}")
        print("\ntimeline gaps found by the graph:")
        for r in ses.run(EXPECT_GAPS):
            print(f"  {r['modality']:8s} week {r['last_before']} -> {r['first_after']}"
                  f"  ({r['subjects']} mice)")
    drv.close()


if __name__ == "__main__":
    main()
