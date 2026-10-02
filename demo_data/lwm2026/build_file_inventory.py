#!/usr/bin/env python3
"""
build_file_inventory.py: turn the raw file listings in source_results/listings/
into source_results/file_inventory.csv, one row per folder or file worth showing
in the graph, mapped to modality / week / mouse and classified by role:

  raw       the canonical copy of acquired data
  copy      a duplicate of something raw (COPY_OF points at the canonical item)
  derived   produced from raw data (exports, ROIs, conversions, predictions)
  result    analysis spreadsheets / tables
  document  slides, photos, notes, code

Listings (made on ki-ed3g, see README):
  dropbox_lungtumor_files.tsv.gz  find . -type f -printf '%s\\t%TY-%Tm-%Td\\t%P\\n'  (in MultiModal/LungTumor)
  atwai_lung_folders.csv.gz       per-folder counts and bytes from the atwai scan index
  atwai_mri_scan_logs.csv.gz      Bruker MrAcqReco.log files on the study's MRI dates
"""
import re
from pathlib import Path

import pandas as pd

L = Path("source_results/listings")
DROPBOX = "Dropbox:MultiModal/LungTumor"
ATWAI = "/data0/core/atwai"
ROOTS = {
    "dropbox": (DROPBOX, "Dropbox", "MultiModal/LungTumor"),
    "anderson": (f"atwai:{ATWAI}/Anderson_Scott/Multimodal/MultiModal Lung tumor test", "atwai",
                 f"{ATWAI}/Anderson_Scott/Multimodal/MultiModal Lung tumor test"),
    "milton": (f"atwai:{ATWAI}/Milton_CornwallBrady/Protocol Development in vivo/MultiModal Lung tumor test",
               "atwai", f"{ATWAI}/Milton_CornwallBrady/Protocol Development in vivo/MultiModal Lung tumor test"),
    "archive": (f"atwai:{ATWAI}/archive/microct/longitudinal mouse lung tumors", "atwai",
                f"{ATWAI}/archive/microct/longitudinal mouse lung tumors"),
    "paravision": (f"atwai:{ATWAI}/huangw/2024", "atwai", f"{ATWAI}/huangw/2024"),
}
MRI_DATES = {"01-22-2024": 6, "01-29-2024": 7, "02-05-2024": 8, "02-12-2024": 9, "02-16-2024": 10,
             "02-26-2024": 11, "03-04-2024": 12, "03-11-2024": 13, "03-18-2024": 14}
IVIS_WEEKS = {"baseline 01222024": 6, "week7_IVIS": 7, "week8 IVIS": 8, "week9_IVIS": 9,
              "week10_IVIS": 10, "week11_IVIS": 11, "week 12_IVIS": 12, "week 13_IVIS": 13,
              "week14_IVIS": 14}
REC = re.compile(r"wk(\d+)[-_](\d+)_Rec$")

rows = []


def add(kind, root, rel, bytes_=None, files=None, role="raw", modality="", week=None,
        subject="", copy_of="", parent="", note=""):
    rid, loc, base = ROOTS[root]
    path = f"{base}/{rel}" if rel else base
    rows.append({"id": f"{loc}:{path}", "kind": kind, "location": loc, "path": path,
                 "name": rel.rstrip("/").split("/")[-1] if rel else base.split("/")[-1],
                 "bytes": bytes_, "files": files, "role": role, "modality": modality,
                 "week": week, "subject": f"M{subject}" if subject else "",
                 "copy_of": copy_of, "parent": parent or rid, "note": note})
    return f"{loc}:{path}"


for key in ROOTS:
    rid, loc, base = ROOTS[key]
    rows.append({"id": rid, "kind": "Folder", "location": loc, "path": base,
                 "name": base.split("/")[-1], "bytes": None, "files": None, "role": "root",
                 "modality": "", "week": None, "subject": "", "copy_of": "", "parent": "", "note": ""})

# ------------------------------------------------------------------ atwai
a = pd.read_csv(L / "atwai_lung_folders.csv.gz")
canon = {}
for _, r in a.iterrows():
    p = r.parent_path
    m = re.search(r"Anderson_Scott/.*/raw data/(wk\d+[-_]\d+_Rec)$", p)
    if m:
        w, s = REC.search(m.group(1)).groups()
        canon[(int(w), s)] = add("Folder", "anderson", f"raw data/{m.group(1)}", r.bytes, r.files,
                                 "raw", "microCT", int(w), s,
                                 note="SkyScan reconstruction (canonical copy)")
for _, r in a.iterrows():
    p = r.parent_path
    for root, pat in [("milton", r"MultiModal Lung tumor test/(wk\d+[-_]\d+_Rec)$"),
                      ("archive", r"longitudinal mouse lung tumors/(wk\d+[-_]\d+_Rec)$")]:
        m = re.search(pat, p) if root in p.lower() or (root == "milton" and "Milton" in p) else None
        if m:
            w, s = REC.search(m.group(1)).groups()
            add("Folder", root, m.group(1), r.bytes, r.files, "copy", "microCT", int(w), s,
                copy_of=canon.get((int(w), s), ""), note="copy of the reconstruction")
# archive NIfTI conversions + model predictions, aggregated per mouse-week
nif = a[a.parent_path.str.contains(r"archive/.*_Rec-Nifti")].copy()
nif["top"] = nif.parent_path.str.extract(r"longitudinal mouse lung tumors/(wk\d+[-_]\d+_Rec-Nifti)")[0]
for top, x in nif.dropna(subset=["top"]).groupby("top"):
    w, s = re.search(r"wk(\d+)[-_](\d+)_Rec-Nifti", top).groups()
    add("Folder", "archive", top, int(x.bytes.sum()), int(x.files.sum()), "derived", "microCT",
        int(w), s, note="NIfTI conversion with img/ and prediction/ (segmentation model output)")
# Anderson's processed data, per mouse
pro = a[a.parent_path.str.contains(r"Anderson_Scott/.*/processed data/Mouse \d+")].copy()
pro["mouse"] = pro.parent_path.str.extract(r"processed data/Mouse (\d+)")[0]
for s, x in pro.groupby("mouse"):
    add("Folder", "anderson", f"processed data/Mouse {s}", int(x.bytes.sum()), int(x.files.sum()),
        "derived", "microCT", None, s, note="analysis outputs (Anderson)")

# MRI acquisition sessions (ParaVision) from the scanner logs
logs = pd.read_csv(L / "atwai_mri_scan_logs.csv.gz")
logs["session"] = logs.parent_path.str.extract(
    r"huangw/2024/(\d{8}_\d{6}_AIPT_[^/]*multi[^/]*lung[^/]*)", flags=re.I)[0]
WK = {d.replace("-", "")[4:] + d.replace("-", "")[:4]: w for d, w in MRI_DATES.items()}
# folder sizes from the atwai scan index (atwai_mri_sizes.csv.gz, one row per directory)
sz = pd.read_csv(L / "atwai_mri_sizes.csv.gz")
sz["session"] = sz.parent_path.str.extract(r"huangw/2024/([^/]+)")[0]
sz = sz.groupby("session")[["files", "bytes"]].sum()
for sess, x in logs.dropna(subset=["session"]).groupby("session"):
    w = WK.get(sess[:8])
    b, n = (int(sz.loc[sess, "bytes"]), int(sz.loc[sess, "files"])) if sess in sz.index else (None, None)
    add("Folder", "paravision", sess, b, n, "raw", "MRI", w,
        note=f"ParaVision study folder (all mice that day), {len(x)} reconstructed scans")

# ------------------------------------------------------------------ Dropbox
f = pd.read_csv(L / "dropbox_lungtumor_files.tsv.gz", sep="\t", header=None,
                names=["size", "date", "path"])
parts = f.path.str.split("/")
top = parts.str[0]

# microCT reconstructions on Dropbox (weeks 6-11), per reconstruction folder
ct = f[top == "microCT"].copy()
ct["wkdir"], ct["recdir"] = ct.path.str.split("/").str[1], ct.path.str.split("/").str[2]
for (wkdir, recdir), x in ct.groupby(["wkdir", "recdir"]):
    w = int(re.search(r"wk(\d+)", wkdir).group(1))
    m = REC.search(recdir)
    if m:
        s = m.group(2)
        add("Folder", "dropbox", f"microCT/{wkdir}/{recdir}", int(x["size"].sum()), len(x), "copy",
            "microCT", w, s, copy_of=canon.get((w, s), ""), note="copy of the reconstruction")
    else:
        extra = re.search(r"wk\d+_(\d+)(B|_gut\d)_Rec$", recdir)
        add("Folder", "dropbox", f"microCT/{wkdir}/{recdir}", int(x["size"].sum()), len(x),
            "copy" if not extra else "raw", "microCT", w, extra.group(1) if extra else "",
            note=("extra scan of this mouse" if extra else
                  "copy named by cage and ear punch, not mouse ID"))

# MRI: dated folders (originals + exports), XNAT copy, Dragonfly
mri = f[top == "MRI"].copy()
mri["p1"], mri["p2"] = mri.path.str.split("/").str[1], mri.path.str.split("/").str[2]
mid = lambda name: (re.match(r"^(1013|\d{2})", name) or [None, None])[1]
dcm_by = {}
for _, r in mri[mri.p1.isin(MRI_DATES)].iterrows():
    s = mid(r.p2)
    s = "13" if s == "1013" else s
    w = MRI_DATES[r.p1]
    if r.p2.lower().endswith(".dcm"):
        i = add("File", "dropbox", r.path, r["size"], None, "raw", "MRI", w, s or "",
                note="original DICOM")
        if s:
            dcm_by.setdefault((w, s), i)
    else:
        add("File", "dropbox", r.path, r["size"], None, "derived", "MRI", w, s or "",
            note="exported image / overlay / ROI set")
for _, r in mri[mri.p1 == "XNAT"].iterrows():
    m = re.match(r"MRI/XNAT/mouse(\d+)/week(\d+)/", r.path)
    if m:
        s, w = m.group(1), int(m.group(2))
        add("File", "dropbox", r.path, r["size"], None, "copy", "MRI", w, s,
            copy_of=dcm_by.get((w, s), ""), note="XNAT copy")
for _, r in mri[mri.p1 == "DragonflyROIs"].iterrows():
    m = re.match(r"roi-(\d+)-week(\d+)", r.p2)
    add("File", "dropbox", r.path, r["size"], None, "derived", "MRI",
        int(m.group(2)) if m else None, m.group(1) if m else "", note="Dragonfly tumor ROI")
dfs = mri[mri.p1 == "DragonflySessions"]
for child, x in dfs.groupby("p2"):
    m = re.match(r"m(\d+)_wk?(\d+)", child) or re.match(r"(\d+)\.ORS", child)
    s = m.group(1) if m else ""
    w = int(m.group(2)) if m and m.re.pattern.startswith("m(") else None
    add("Folder" if (x.path.str.count("/") > 2).any() else "File", "dropbox",
        f"MRI/DragonflySessions/{child}", int(x["size"].sum()), len(x), "derived", "MRI", w, s,
        note="Dragonfly session" + (" slice stack" if w else ""))
for _, r in mri[mri.path.str.count("/") == 1].iterrows():
    add("File", "dropbox", r.path, r["size"], None,
        "result" if r.path.endswith(".xlsx") else "document", "MRI")

# IVIS: one folder per weekly session, Living Image sequences inside
iv = f[top == "IVIS"].copy()
iv["p1"], iv["p2"] = iv.path.str.split("/").str[1], iv.path.str.split("/").str[2]
week_folder = {}
for p1, x in iv.groupby("p1"):
    w = IVIS_WEEKS.get(p1)
    if w is None:
        add("Folder", "dropbox", f"IVIS/{p1}", int(x["size"].sum()), len(x), "derived", "IVIS",
            note="summary images")
        continue
    is_copy = p1 == "week 13_IVIS"
    week_folder[w] = add("Folder", "dropbox", f"IVIS/{p1}", int(x["size"].sum()), len(x),
                         "copy" if is_copy else "raw", "IVIS", w,
                         note=("contents identical to week 12; real week-13 images not found"
                               if is_copy else "weekly session, all cages"))
iv["seqdir"] = iv.path.str.extract(r"^(IVIS/[^/]+/(?:[^/]+/)*?SME\d+(?:_SEQ)?)/")[0]
for seqdir, x in iv.dropna(subset=["seqdir"]).groupby("seqdir"):
    p1, p2 = seqdir.split("/")[1], seqdir.split("/")[-1]
    w = IVIS_WEEKS.get(p1)
    add("Folder", "dropbox", seqdir, int(x["size"].sum()), len(x),
        "copy" if p1 == "week 13_IVIS" else "raw", "IVIS", w, parent=week_folder.get(w, ""),
        note=f"Living Image sequence {p2[3:7]}-{p2[7:9]}-{p2[9:11]} {p2[11:13]}:{p2[13:15]}")
# the week-13 folder (and every sequence in it) duplicates week 12
by_id = {r["id"]: r for r in rows}
for r in rows:
    if r["id"] == week_folder.get(13):
        r["copy_of"] = week_folder.get(12, "")
    elif "/IVIS/week 13_IVIS/SME" in r["id"]:
        twin = r["id"].replace("/week 13_IVIS/", "/week 12_IVIS/")
        r["copy_of"] = twin if twin in by_id else ""

# everything else at the top of the study folder
for t, x in f.groupby(top):
    if t in ("microCT", "MRI", "IVIS") or t.startswith("."):
        continue
    if (x.path.str.count("/") > 0).any():
        add("Folder", "dropbox", t, int(x["size"].sum()), len(x),
            "raw" if t == "filtered rotated CFT" else "document",
            "CFT" if t == "filtered rotated CFT" else "",
            note={"filtered rotated CFT": "cryofluorescence tomography, endpoint",
                  "zzz": "archived analysis"}.get(t, ""))
    else:
        add("File", "dropbox", t, int(x["size"].iloc[0]), None,
            "result" if t.endswith(".xlsx") else "document")

inv = pd.DataFrame(rows)
inv["nested"] = inv.parent.isin(set(week_folder.values()))
inv.to_csv("source_results/file_inventory.csv", index=False)
print(f"{len(inv)} items -> source_results/file_inventory.csv")
print(inv.groupby(["location", "role"]).agg(items=("id", "size"),
                                            GB=("bytes", lambda b: round(b.sum() / 1e9, 2))))
