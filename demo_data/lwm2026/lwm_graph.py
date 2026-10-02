"""
lwm_graph.py — tiny helper for the LwM workshop notebook.

    g = connect()            # Neo4j if NEO4J_PASSWORD is set, else offline CSVs
    g.show("coverage")       # print the Cypher behind a question
    df = g.run("coverage")   # answer it as a pandas DataFrame

Every named question has a Cypher query (what runs against the knowledge
graph) and an offline pandas equivalent over the same data files, so the
notebook still works on a laptop with no database.
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"

CYPHER = {
    "node_counts": """
MATCH (n) WHERE n.demo_dataset IS NOT NULL
WITH labels(n)[0] AS label
RETURN label, count(*) AS nodes
ORDER BY nodes DESC""",

    "relationship_counts": """
MATCH (a)-[r]->(b)
WHERE a.demo_dataset IS NOT NULL AND b.demo_dataset IS NOT NULL
RETURN labels(a)[0] AS from_label, type(r) AS relationship,
       labels(b)[0] AS to_label, count(*) AS n
ORDER BY n DESC""",

    "study": """
MATCH (st:Study)
RETURN properties(st) AS study""",

    "modalities": """
MATCH (:Study)-[:USES_MODALITY]->(m:Modality)
RETURN m.name AS modality, m.instrument AS instrument, m.readout AS readout
ORDER BY modality""",

    "subjects": """
MATCH (:Study)-[:INCLUDES]->(s:Subject)
OPTIONAL MATCH (s)<-[:OF_SUBJECT]-(se:ImagingSession)
RETURN s.id AS subject, s.sex AS sex, s.cage AS cage,
       s.age_at_inoculation_wk AS age_wk, count(se) AS sessions
ORDER BY subject""",

    "coverage": """
MATCH (se:ImagingSession)-[:OF_SUBJECT]->(s:Subject)
RETURN se.modality AS modality, se.study_week AS week,
       count(DISTINCT s) AS mice_imaged
ORDER BY modality, week""",

    "session_coverage": """
// Every imaging session: was it measured, are its files on disk, and did the instrument log it?
MATCH (se:ImagingSession)-[:OF_SUBJECT]->(su:Subject)
OPTIONAL MATCH (se)-[:HAS_MEASUREMENT]->(m:Measurement)
WITH se, su, count(m) AS measurements
OPTIONAL MATCH (se)-[:STORED_IN]->(f)
WITH se, su, measurements, count(f) AS stored_items
OPTIONAL MATCH (se)-[:HAS_ACQUISITION]->(a:Acquisition)
RETURN su.id AS subject, se.modality AS modality, se.study_week AS week, se.acq_date AS acq_date,
       measurements, stored_items, count(a) AS acquisitions
ORDER BY modality, subject, week""",

    "gaps": """
// A gap is a NEXT step between two sessions of the same mouse and modality
// that skips one or more weeks. Then ask: does anyone explain it?
MATCH (a:ImagingSession)-[r:NEXT]->(b:ImagingSession)
WHERE r.gap_weeks > 1
WITH a.modality AS modality, a.study_week AS last_before,
     b.study_week AS first_after, count(*) AS mice_affected
OPTIONAL MATCH (o:Observation {kind: 'data_gap'})
               -[:ABOUT]->(:Modality {name: modality})
WHERE any(w IN o.weeks WHERE last_before < w < first_after)
RETURN modality, last_before, first_after, mice_affected,
       o.id AS explained_by, o.reason AS reason
ORDER BY modality, last_before""",

    "observations": """
MATCH (o:Observation)-[:ABOUT]->(x)
WITH o, collect(labels(x)[0] + ':' +
                coalesce(x.id, x.name)) AS about
OPTIONAL MATCH (o)-[:CONTRASTS]->(c:Modality)
RETURN o.id AS id, o.kind AS kind, o.modality AS modality, o.text AS text,
       about, collect(c.name) AS contrasts_with
ORDER BY kind, id""",

    "sessions": """
MATCH (se:ImagingSession)-[:OF_SUBJECT]->(s:Subject)
RETURN se.id AS session, s.id AS subject, se.modality AS modality,
       se.study_week AS week, se.acq_date AS acq_date,
       se.root_path AS root_path, properties(se) AS props
ORDER BY modality, subject, week""",

    "dataset_summary": """
// The whole dataset in one call: per modality, what was imaged, what was
// measured, over which weeks, and how many curator notes are attached.
MATCH (st:Study)-[:HAS_DATA]->(se:ImagingSession)
      -[:IMAGED_WITH]->(mo:Modality)
MATCH (se)-[:OF_SUBJECT]->(su:Subject)
OPTIONAL MATCH (se)-[:HAS_MEASUREMENT]->(m:Measurement)
WITH mo, count(DISTINCT se) AS sessions, count(DISTINCT su) AS mice_imaged,
     count(DISTINCT CASE WHEN m IS NOT NULL THEN su END) AS mice_measured,
     count(m) AS measurements, collect(DISTINCT m.kind) AS kinds,
     collect(DISTINCT se.study_week) AS weeks,
     min(se.acq_date) AS first_scan, max(se.acq_date) AS last_scan
OPTIONAL MATCH (o:Observation)-[:ABOUT]->(mo)
RETURN mo.name AS modality, mice_imaged, mice_measured, sessions, measurements,
       size(weeks) AS weeks_imaged, first_scan, last_scan, kinds, count(o) AS notes
ORDER BY modality""",
    "session_files": """
// Every imaging session and the files or folders that hold its data
MATCH (se:ImagingSession)-[:OF_SUBJECT]->(su:Subject)
MATCH (se)-[r:STORED_IN|HAS_DERIVED]->(f)
OPTIONAL MATCH (c)-[:COPY_OF]->(f)
RETURN su.id AS subject, se.modality AS modality, se.study_week AS week,
       type(r) AS link, labels(f)[0] AS node, f.role AS role, f.location AS location,
       f.path AS path, f.bytes AS bytes, count(c) AS copies
ORDER BY subject, week, modality, link, path""",
    "storage_by_location": """
// What is stored where, by role (folders nested inside others are not double-counted)
MATCH (f) WHERE (f:File OR f:Folder) AND f.demo_dataset IS NOT NULL
      AND f.bytes IS NOT NULL AND coalesce(f.nested, false) = false
RETURN f.location AS location, f.role AS role, count(*) AS items,
       round(sum(f.bytes) / 1e9, 2) AS GB
ORDER BY location, role""",
    "storage_by_modality": """
// The same storage, by modality (folders nested inside others are not double-counted)
MATCH (f) WHERE (f:File OR f:Folder) AND f.demo_dataset IS NOT NULL
      AND f.bytes IS NOT NULL AND coalesce(f.nested, false) = false
RETURN f.location AS location, coalesce(f.modality, '') AS modality, count(*) AS items,
       round(sum(f.bytes) / 1e9, 2) AS GB
ORDER BY location, modality""",
    "result_files": """
// Results tables and other study documents, as named on disk
MATCH (f:File) WHERE f.demo_dataset IS NOT NULL AND f.role IN ['result', 'document']
RETURN f.name AS name, f.role AS role, f.location AS location
ORDER BY role, name""",
    "session_hosts": """
// Which machines hold each session's data: the canonical copy and every copy of it
MATCH (se:ImagingSession)-[:STORED_IN]->(f)
OPTIONAL MATCH (c)-[:COPY_OF]->(f)
WITH se, f, collect(c) AS cs
UNWIND [f] + cs AS item
WITH se, collect(DISTINCT item.host) AS hosts, count(DISTINCT item) AS stored_items
MATCH (se)-[:OF_SUBJECT]->(su:Subject)
RETURN su.id AS subject, se.modality AS modality, se.study_week AS week, hosts, stored_items
ORDER BY modality, week, subject""",
    "hosts": """
// The machines that hold or produced this study's data
MATCH (h:Host)
OPTIONAL MATCH (h)<-[:ON_HOST]-(root)
OPTIONAL MATCH (h)-[:SYNCED_TO]->(m:Host)
RETURN h.name AS host, h.role AS role, h.note AS note,
       collect(DISTINCT root.path) AS top_folders, collect(DISTINCT m.name) AS synced_to
ORDER BY role, host""",
    "instruments": """
// Each modality's instrument, with the facility rate and the time model
MATCH (mo:Modality)-[:USES_INSTRUMENT]->(i:Instrument)
RETURN mo.name AS modality, properties(i) AS props
ORDER BY modality""",
    "acquisitions": """
// Every scan, series or image, with its instrument parameters and timestamps
MATCH (a:Acquisition)-[:ON_INSTRUMENT]->(i:Instrument)
OPTIONAL MATCH (se:ImagingSession)-[:HAS_ACQUISITION]->(a)
RETURN a.modality AS modality, a.subject AS subject, a.week AS week,
       se.id AS session, properties(a) AS props
ORDER BY modality, week, subject""",
    "measurements": """
MATCH (s:Subject)<-[:OF_SUBJECT]-(se:ImagingSession)
      -[:HAS_MEASUREMENT]->(m:Measurement)
RETURN s.id AS subject, se.modality AS modality, se.study_week AS week,
       m.kind AS kind, m.value AS value, m.unit AS unit, m.detected AS detected,
       se.id AS session
ORDER BY modality, subject, week""",
}

SESSION_CORE = {"id", "modality", "study_week", "acq_date", "root_path",
                "pattern_name", "demo_dataset", "synthetic"}


class _Offline:
    """Answers the same questions from the CSV/JSON files."""
    backend = "offline (data/ CSV files)"

    def __init__(self, data=DATA):
        d = Path(data)
        self.meta = json.loads((d / "study.json").read_text())
        self.subjects = pd.read_csv(d / "subjects.csv")
        self.sessions = pd.read_csv(d / "sessions.csv")
        self.meas = pd.read_csv(d / "measurements.csv")
        self.obs = json.loads((d / "observations.json").read_text())
        self.nodes = pd.read_csv(d / "nodes.csv", dtype={"subject": str}) \
            if (d / "nodes.csv").exists() else None
        self.flinks = pd.read_csv(d / "links.csv") if (d / "links.csv").exists() else None
        self.files = (self.nodes[self.nodes.kind.isin(["File", "Folder"])]
                      if self.nodes is not None else None)

    def _nexts(self):
        s = self.sessions.sort_values(["subject", "modality", "study_week"])
        s = s.assign(next_week=s.groupby(["subject", "modality"]).study_week.shift(-1))
        return s.dropna(subset=["next_week"]).assign(
            gap_weeks=lambda x: x.next_week - x.study_week)

    def query(self, name):
        s, m = self.sessions, self.meas
        if name == "node_counts":
            return pd.DataFrame({
                "label": ["Measurement", "ImagingSession", "Subject", "Observation",
                          "Modality", "Study"],
                "nodes": [len(m), len(s), len(self.subjects), len(self.obs),
                          len(self.meta["modalities"]), 1]})
        if name == "relationship_counts":
            con = sum(len(o.get("contrasts", [])) for o in self.obs)
            rows = [("ImagingSession", "HAS_MEASUREMENT", "Measurement", len(m)),
                    ("Study", "HAS_DATA", "ImagingSession", len(s)),
                    ("ImagingSession", "OF_SUBJECT", "Subject", len(s)),
                    ("ImagingSession", "IMAGED_WITH", "Modality", len(s)),
                    ("ImagingSession", "NEXT", "ImagingSession", len(self._nexts())),
                    ("Study", "INCLUDES", "Subject", len(self.subjects)),
                    *[("Observation", "ABOUT", t, n) for t, n in pd.Series(
                        [t["type"] for o in self.obs for t in o.get("about", [])]
                    ).value_counts().items()],
                    ("Study", "USES_MODALITY", "Modality", len(self.meta["modalities"])),
                    ("Observation", "CONTRASTS", "Modality", con)]
            return pd.DataFrame(rows, columns=["from_label", "relationship", "to_label", "n"]
                                ).sort_values(["n", "relationship", "to_label"],
                                              ascending=[False, True, True], ignore_index=True)
        if name == "study":
            return pd.DataFrame({"study": [self.meta["study"]]})
        if name == "modalities":
            return pd.DataFrame(self.meta["modalities"])[["name", "instrument", "readout"]] \
                .rename(columns={"name": "modality"}).sort_values("modality", ignore_index=True)
        if name == "subjects":
            n = s.groupby("subject").size().rename("sessions")
            return self.subjects.rename(columns={"id": "subject",
                                                 "age_at_inoculation_wk": "age_wk"}) \
                [["subject", "sex", "cage", "age_wk"]].join(n, on="subject")
        if name == "coverage":
            return s.groupby(["modality", "study_week"]).subject.nunique() \
                .rename("mice_imaged").reset_index().rename(columns={"study_week": "week"})
        if name == "session_coverage":
            l = self.flinks
            cnt = lambda rel: l[l.rel == rel].groupby("src").size()
            out = s[["id", "subject", "modality", "study_week", "acq_date"]].rename(
                columns={"study_week": "week"})
            out["measurements"] = out.id.map(m.groupby("session_id").size()).fillna(0).astype(int)
            out["stored_items"] = out.id.map(cnt("STORED_IN")).fillna(0).astype(int)
            out["acquisitions"] = out.id.map(cnt("HAS_ACQUISITION")).fillna(0).astype(int)
            return out.drop(columns="id").sort_values(["modality", "subject", "week"], ignore_index=True)
        if name == "gaps":
            g = self._nexts().query("gap_weeks > 1").groupby(
                ["modality", "study_week", "next_week"]).size().rename("mice_affected") \
                .reset_index().rename(columns={"study_week": "last_before",
                                               "next_week": "first_after"})
            g["first_after"] = g.first_after.astype(int)
            def explain(r):
                for o in self.obs:
                    if o["kind"] == "data_gap" and o.get("modality") == r.modality and \
                            any(r.last_before < w < r.first_after for w in o.get("weeks", [])):
                        return pd.Series({"explained_by": o["id"], "reason": o.get("reason")})
                return pd.Series({"explained_by": None, "reason": None})
            return pd.concat([g, g.apply(explain, axis=1)], axis=1)
        if name == "observations":
            return pd.DataFrame([{
                "id": o["id"], "kind": o["kind"], "modality": o.get("modality"),
                "text": o["text"],
                "about": [f"{t['type']}:{t['id']}" for t in o.get("about", [])],
                "contrasts_with": o.get("contrasts", [])} for o in self.obs]
            ).sort_values(["kind", "id"], ignore_index=True)
        if name == "sessions":
            out = s.rename(columns={"id": "session", "study_week": "week"})
            out["props"] = out.params_json.map(json.loads)
            return out[["session", "subject", "modality", "week", "acq_date",
                        "root_path", "props"]]
        if name == "dataset_summary":
            j = s.merge(m, left_on="id", right_on="session_id", how="left")
            notes = pd.Series([o.get("modality") for o in self.obs
                               for t in o.get("about", []) if t["type"] == "Modality"]
                              ).value_counts()
            rows = []
            for mod, x in j.groupby("modality"):
                rows.append({
                    "modality": mod, "mice_imaged": x.subject.nunique(),
                    "mice_measured": x.loc[x.kind.notna(), "subject"].nunique(),
                    "sessions": x.id.nunique(), "measurements": int(x.kind.notna().sum()),
                    "weeks_imaged": x.study_week.nunique(),
                    "first_scan": x.acq_date.min(), "last_scan": x.acq_date.max(),
                    "kinds": sorted(x.kind.dropna().unique().tolist()),
                    "notes": int(notes.get(mod, 0))})
            return pd.DataFrame(rows)
        if name == "session_files":
            l, f = self.flinks, self.files
            sl = l[l.rel.isin(["STORED_IN", "HAS_DERIVED"]) & (l.src_label == "ImagingSession")]
            copies = l[l.rel == "COPY_OF"].groupby("dst").size()
            j = sl.merge(s, left_on="src", right_on="id").merge(
                f, left_on="dst", right_on="id", suffixes=("", "_f"))
            out = pd.DataFrame({
                "subject": j.subject_x if "subject_x" in j else j.subject,
                "modality": j.modality_x if "modality_x" in j else j.modality,
                "week": j.study_week, "link": j.rel, "node": j.kind, "role": j.role,
                "location": j.location, "path": j.path, "bytes": j.bytes,
                "copies": j.dst.map(copies).fillna(0).astype(int)})
            return out.sort_values(["subject", "week", "modality", "link", "path"],
                                   ignore_index=True)
        if name == "storage_by_location":
            f = self.files[self.files.bytes.notna() & ~self.files.nested.fillna(False).astype(bool)]
            return (f.groupby(["location", "role"]).agg(items=("id", "size"), GB=("bytes", "sum"))
                    .assign(GB=lambda x: (x.GB / 1e9).round(2)).reset_index())
        if name == "storage_by_modality":
            f = self.files[self.files.bytes.notna() & ~self.files.nested.fillna(False).astype(bool)]
            return (f.assign(modality=f.modality.fillna("")).groupby(["location", "modality"])
                    .agg(items=("id", "size"), GB=("bytes", "sum"))
                    .assign(GB=lambda x: (x.GB / 1e9).round(2)).reset_index())
        if name == "result_files":
            f = self.files[(self.files.kind == "File") & self.files.role.isin(["result", "document"])]
            return f[["name", "role", "location"]].sort_values(["role", "name"], ignore_index=True)
        if name == "session_hosts":
            l, n = self.flinks, self.nodes.set_index("id")
            st = l[(l.rel == "STORED_IN") & (l.src_label == "ImagingSession")]
            cp = l[l.rel == "COPY_OF"]
            rows = []
            for se, x in st.groupby("src"):
                items = set(x.dst) | set(cp[cp.dst.isin(x.dst)].src)
                rows.append({"session": se, "hosts": sorted(set(n.loc[list(items), "host"].dropna())),
                             "stored_items": len(items)})
            out = pd.DataFrame(rows).merge(s[["id", "subject", "modality", "study_week"]],
                                           left_on="session", right_on="id")
            return out.rename(columns={"study_week": "week"})[
                ["subject", "modality", "week", "hosts", "stored_items"]].sort_values(
                ["modality", "week", "subject"], ignore_index=True)
        if name == "hosts":
            h = self.nodes[self.nodes.kind == "Host"]
            l = self.flinks
            roots = l[l.rel == "ON_HOST"].merge(self.nodes[["id", "path"]], left_on="src", right_on="id")
            sync = l[l.rel == "SYNCED_TO"]
            return pd.DataFrame({
                "host": h.name.values, "role": h.role.values, "note": h.note.values,
                "top_folders": [sorted(roots.loc[roots.dst == i, "path"]) for i in h.id],
                "synced_to": [sorted(self.nodes.set_index("id").loc[sync.loc[sync.src == i, "dst"], "name"])
                              for i in h.id]}).sort_values(["role", "host"], ignore_index=True)
        if name in ("instruments", "acquisitions"):
            kind = "Instrument" if name == "instruments" else "Acquisition"
            x = self.nodes[self.nodes.kind == kind]
            props = [{k: v for k, v in r.items() if pd.notna(v) and k != "kind"}
                     for r in x.to_dict("records")]
            if name == "instruments":
                return pd.DataFrame({"modality": x.modality.values, "props": props}
                                    ).sort_values("modality", ignore_index=True)
            l = self.flinks[self.flinks.rel == "HAS_ACQUISITION"].set_index("dst").src
            return pd.DataFrame({"modality": x.modality.values, "subject": x.subject.values,
                                 "week": x.week.values, "session": x.id.map(l).values,
                                 "props": props}
                                ).sort_values(["modality", "week", "subject"], ignore_index=True)
        if name == "measurements":
            j = m.merge(s, left_on="session_id", right_on="id")
            return j.rename(columns={"study_week": "week", "session_id": "session"})[
                ["subject", "modality", "week", "kind", "value", "unit", "detected", "session"]]
        raise KeyError(name)


class _Neo4j:
    def __init__(self, uri, user, password, database=None):
        import logging
        from neo4j import GraphDatabase
        logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)   # hide query-planner hints
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.driver.verify_connectivity()
        self.database = database
        self.backend = f"Neo4j at {uri}"

    def cypher(self, query, params=None):
        kw = {"database": self.database} if self.database else {}
        with self.driver.session(**kw) as ses:
            res = ses.run(query, params or {})
            keys = list(res.keys())
            rows = [r.values() for r in res]
        return pd.DataFrame(rows, columns=keys)

    def query(self, name):
        df = self.cypher(CYPHER[name])
        if name == "sessions":   # keep only acquisition parameters in props
            df["props"] = df.props.map(
                lambda p: {k: v for k, v in p.items() if k not in SESSION_CORE})
        return df


class Graph:
    def __init__(self, impl):
        self._impl = impl
        self.backend = impl.backend

    @property
    def live(self):
        """True when connected to Neo4j, False when answering from the bundled files."""
        return hasattr(self._impl, "cypher")

    def queries(self):
        """The names of every built-in question."""
        return sorted(CYPHER)

    def show(self, name):
        print(CYPHER[name].strip())

    def run(self, name):
        return self._impl.query(name)

    def cypher(self, query, params=None):
        """Run your own Cypher (Neo4j backend only). Pass parameters as a dict."""
        if not hasattr(self._impl, "cypher"):
            raise RuntimeError("Custom Cypher needs the Neo4j backend "
                               "(set NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD).")
        return self._impl.cypher(query, params)


def _load_env_file(path):
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def connect(uri=None, user=None, password=None, database=None, offline=False, env_file=None, ask=None):
    """Connect to the study's knowledge graph, or fall back to the bundled CSV files.

    Connection settings come from, in order: the arguments; the environment variables
    NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD; a neo4j.env file next to the notebook (KEY=VALUE
    lines); and, in Google Colab, a prompt for the address and password the presenter shares.
    """
    if not offline and not (password or os.environ.get("NEO4J_PASSWORD")):
        f = Path(env_file or os.environ.get("NEO4J_ENV_FILE", "neo4j.env"))
        if f.exists():
            _load_env_file(f)
            print(f"Connection settings read from {f.resolve()}")
        elif ask if ask is not None else "google.colab" in sys.modules:
            from getpass import getpass
            addr = input("Neo4j address (blank = offline): ").strip()
            if addr:
                os.environ["NEO4J_URI"] = addr if "://" in addr else f"bolt://{addr}"
                os.environ["NEO4J_USER"] = input("Neo4j user [neo4j]: ").strip() or "neo4j"
                os.environ["NEO4J_PASSWORD"] = getpass("Neo4j password: ")
        else:
            print(f"No connection settings (no NEO4J_PASSWORD, no {f.name}).")
    uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = user or os.environ.get("NEO4J_USER", "neo4j")
    password = password or os.environ.get("NEO4J_PASSWORD")
    database = database or os.environ.get("NEO4J_DATABASE")
    if not offline and password:
        try:
            g = Graph(_Neo4j(uri, user, password, database))
            print(f"Connected: {g.backend}")
            return g
        except ModuleNotFoundError:
            print(f"The neo4j driver isn't installed in this kernel's Python ({sys.executable}).\n"
                  "Run  %pip install neo4j  in a cell, restart the kernel, and run setup again. "
                  "Using offline data for now.")
        except Exception as e:  # fall back rather than stall a workshop
            print(f"Neo4j unavailable ({type(e).__name__}: {e}); using offline data.")
    g = Graph(_Offline())
    print(f"Using {g.backend}")
    return g
