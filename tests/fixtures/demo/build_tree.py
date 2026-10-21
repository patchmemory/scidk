#!/usr/bin/env python3
"""
build_tree.py — regenerate the LwM demo fixture from demo_data/lwm2026/.

Writes, next to this file:

  tree/dropbox/MultiModal/LungTumor/...   Dropbox study folder (every listed path)
  tree/atwai/...                          atwai folders (microCT copies, analysis, MRI)
  manifest.csv                            one row per file in tree/: where it came from
  folders.csv                             every folder, with the file count and bytes
                                          the real listing reported for it
  graph/                                  copy of demo_data/lwm2026/data (the study graph)

Files are empty placeholders, except the small metadata files whose contents are in
the listings (kind = metadata): microCT reconstruction logs, IVIS ClickInfo, and
ParaVision method/acqp. Those are rebuilt from grep output, so they hold only the
lines the grep matched (key=value lines for SkyScan logs, key: value for ClickInfo).

Two reductions keep it small enough to commit; both are recorded in manifest.csv:
  - Numbered image series (reconstruction slices, raw projections) longer than
    SERIES_MAX keep their first SERIES_HEAD and last file. SERIES_HEAD stays >= 5 so the
    bruker_microct_rec profile (min_count: 5) still matches.
  - atwai listings give file counts per folder, not names. Only files with known names
    are created there: the reconstruction logs, slices named from each log's
    Filename Prefix / First Section / Last Section (kind = inferred), and ParaVision
    method/acqp plus an inferred fid per acquisition.

Real sizes and dates live in manifest.csv / folders.csv; tests/fixtures/demo/demo_fixture.py
applies the dates and recreates empty folders (git keeps neither) before scanning.

Usage:  python tests/fixtures/demo/build_tree.py     (deletes and rebuilds tree/)
"""
import csv
import gzip
import re
import shutil
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SRC = REPO / "demo_data" / "lwm2026"
LISTINGS = SRC / "source_results" / "listings"
TREE = HERE / "tree"

DROPBOX_ROOT = "dropbox/MultiModal/LungTumor"
ATWAI_PREFIX = "/data0/core/atwai/"

SERIES_MAX = 8
SERIES_HEAD = 5
SERIES_RE = re.compile(r"^(.*?)(\d{4,})(\.[A-Za-z]+)$")


def atwai_rel(path):
    path = path.rstrip("/")
    assert path.startswith(ATWAI_PREFIX), path
    return "atwai/" + path[len(ATWAI_PREFIX):]


def read_gz(name):
    with gzip.open(LISTINGS / name, "rt", encoding="utf-8", errors="replace") as fh:
        return fh.read().splitlines()


def cap_series(names):
    """Return (kept, dropped_count) for one folder's file names."""
    series = defaultdict(list)
    for n in names:
        m = SERIES_RE.match(n)
        if m:
            series[(m.group(1), m.group(3).lower())].append(n)
    drop = set()
    for members in series.values():
        if len(members) > SERIES_MAX:
            members.sort()
            drop.update(members[SERIES_HEAD:-1])
    return [n for n in names if n not in drop], len(drop)


def dropbox(files, folders):
    by_dir = defaultdict(list)
    for line in read_gz("dropbox_lungtumor_files.tsv.gz"):
        size, date, rel = line.split("\t")
        d, _, name = rel.rpartition("/")
        by_dir[d].append((name, int(size), date))

    clickinfo = defaultdict(list)
    for line in read_gz("ivis_clickinfo.txt.gz"):
        path, sep, rest = line.partition(".txt:")
        if sep:
            clickinfo[path + ".txt"].append(rest)

    for d, entries in by_dir.items():
        meta = {n: (s, dt) for n, s, dt in entries}
        kept, _ = cap_series([n for n, _, _ in entries])
        for name in kept:
            rel = f"{d}/{name}" if d else name
            size, date = meta[name]
            body = clickinfo.get(rel)
            files[f"{DROPBOX_ROOT}/{rel}"] = {
                "source": "dropbox", "kind": "metadata" if body else "placeholder",
                "listed_bytes": size, "listed_date": date,
                "content": "\n".join(body) + "\n" if body else ""}

    # folder totals from the full listing, every ancestor included
    for d, entries in by_dir.items():
        parts = d.split("/") if d else []
        for i in range(len(parts) + 1):
            key = "/".join([DROPBOX_ROOT] + parts[:i])
            f = folders[key]
            f["source"] = "dropbox"
            f["listed_files"] = f.get("listed_files", 0) + len(entries)
            f["listed_bytes"] = f.get("listed_bytes", 0) + sum(s for _, s, _ in entries)


def atwai(files, folders):
    for name in ("atwai_lung_folders.csv.gz", "atwai_mri_sizes.csv.gz"):
        for r in csv.DictReader(read_gz(name)):
            folders[atwai_rel(r["parent_path"])].update(
                source="atwai", listed_files=int(r["files"]), listed_bytes=int(r["bytes"]))

    # SkyScan reconstruction logs, and the slices they describe
    logs = defaultdict(list)
    for line in read_gz("mct_rec_logs.txt.gz"):
        path, sep, rest = line.partition(".log:")
        if sep:
            logs[path + ".log"].append(rest)
    for path, lines in logs.items():
        rel = atwai_rel(path)
        files[rel] = {"source": "atwai", "kind": "metadata",
                      "content": "\n".join(lines) + "\n"}
        kv = defaultdict(list)
        for ln in lines:
            k, _, v = ln.partition("=")
            kv[k.strip()].append(v.strip())
        prefixes = [p for p in kv.get("Filename Prefix", []) if p.lower().endswith("_rec")]
        try:
            first, last = int(kv["First Section"][0]), int(kv["Last Section"][0])
            width = int(kv.get("Filename Index Length", ["8"])[-1])
        except (KeyError, ValueError, IndexError):
            continue
        if not prefixes:
            continue
        ext = "." + kv.get("Result File Type", ["tif"])[0].lower()
        idx = list(range(first, min(first + SERIES_HEAD, last + 1)))
        if last not in idx:
            idx.append(last)
        folder = rel.rpartition("/")[0]
        for i in idx:
            files[f"{folder}/{prefixes[-1]}{i:0{width}d}{ext}"] = {
                "source": "atwai", "kind": "inferred", "content": ""}

    # ParaVision: method/acqp excerpts per acquisition folder (grep -A output)
    section, target = None, "method"
    parts = defaultdict(lambda: {"method": [], "acqp": []})
    for line in read_gz("mri_method_acqp.txt.gz"):
        if line.startswith("=== "):
            section = atwai_rel(line[4:])
            continue
        if section is None or line == "--":
            continue
        if line.startswith("##"):
            target = "acqp" if line.startswith("##$ACQ_") else "method"
        parts[section][target].append(line)
    for folder, p in parts.items():
        for name in ("method", "acqp"):
            if p[name]:
                files[f"{folder}/{name}"] = {"source": "atwai", "kind": "metadata",
                                             "content": "\n".join(p[name]) + "\n"}
        files[f"{folder}/fid"] = {"source": "atwai", "kind": "inferred", "content": ""}


def main():
    files, folders = {}, defaultdict(dict)
    dropbox(files, folders)
    atwai(files, folders)

    if TREE.exists():
        shutil.rmtree(TREE)
    for rel, f in sorted(files.items()):
        p = TREE / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f["content"], encoding="utf-8")

    # every folder that holds a stub file is listed too, even if no listing named it
    for rel in files:
        parts = rel.split("/")
        for i in range(2, len(parts)):
            folders["/".join(parts[:i])].setdefault("source", parts[0])

    with (HERE / "manifest.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "source", "kind", "listed_bytes", "listed_date"])
        for rel, f in sorted(files.items()):
            w.writerow([rel, f["source"], f["kind"], f.get("listed_bytes", ""),
                        f.get("listed_date", "")])
    with (HERE / "folders.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["path", "source", "listed_files", "listed_bytes"])
        for rel, f in sorted(folders.items()):
            w.writerow([rel, f["source"], f.get("listed_files", ""), f.get("listed_bytes", "")])

    graph = HERE / "graph"
    if graph.exists():
        shutil.rmtree(graph)
    shutil.copytree(SRC / "data", graph)

    kinds = defaultdict(int)
    for f in files.values():
        kinds[f["kind"]] += 1
    print(f"tree/: {len(files)} files ({dict(kinds)}), {len(folders)} folders")


if __name__ == "__main__":
    main()
