#!/usr/bin/env python3
"""
generate_demo_data.py: builds data/ for the facility's multimodal lung-tumor
protocol-development study (Learning with Machines demo, Oct 5, 2026).

Real:
  * structure, from the study folders and the atwai scan index: 13 mice in 5
    cages, imaging weeks 6-14 (Jan 22 - Mar 19, 2024), acquisition dates,
    missing weeks and dropouts
  * measurement values, read from the analysis results in source_results/:
      microCT  aerated lung, % of total lung volume (falls as tumor grows)
      MRI      tumor ROI size in pixels (Dragonfly)
      IVIS     total flux (p/s), supine plus prone/left/right views, 4 mice
Placeholders (marked in the data):
  * acquisition parameters (until instrument headers are parsed)
  * which mouse ID sits in which cage, sex and age

Outputs (default ./data): study.json, subjects.csv, sessions.csv
(params_json = acquisition metadata), measurements.csv, observations.json.
Optional --tree DIR writes a scannable placeholder file tree.
"""
import argparse
import csv
import json
import math
import os
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


DATASET = "LWM-DEMO-2026"
STUDY_ID = "AIPT-LUNG-MULTIMODAL-2024"
START = date(2023, 12, 11)         # week 0, inferred: week 6 = Mon Jan 22, 2024
WEEKS = list(range(6, 15))         # imaging weeks 6..14

# Real mouse IDs. Cage sizes are real (week-7 microCT folders: A1 B4 C4 D2 E2,
# with ear punches); which ID sits in which cage is a PLACEHOLDER until
# LungTumorMouseID.xlsx is read.
MICE = [  # id, cage (placeholder), ear punch (placeholder pairing)
    ("10", "A", "none"),
    ("11", "B", "1L1R"), ("12", "B", "1Left"), ("13", "B", "2Left"), ("14", "B", "none"),
    ("15", "C", "1LR0"), ("17", "C", "L1"), ("18", "C", "L2R1"), ("19", "C", "L2"),
    ("67", "D", "left"), ("68", "D", "none"),
    ("69", "E", "left"), ("75", "E", "none"),
]

# Real acquisition dates per modality and study week (folder names, IVIS
# sequence timestamps, atwai reconstruction times).
DATES = {
    "MRI": {6: "2024-01-22", 7: "2024-01-29", 8: "2024-02-05", 9: "2024-02-12",
            10: "2024-02-16", 11: "2024-02-26", 12: "2024-03-04", 13: "2024-03-11",
            14: "2024-03-18"},
    "microCT": {6: "2024-01-22", 7: "2024-01-29", 8: "2024-02-05", 9: "2024-02-12",
                10: "2024-02-20", 11: "2024-02-26", 13: "2024-03-12", 14: "2024-03-18"},
    "IVIS": {6: "2024-01-22", 7: "2024-01-29", 8: "2024-02-05", 9: "2024-02-13",
             10: "2024-02-20", 11: "2024-02-29", 12: "2024-03-05", 13: "2024-03-12",
             14: "2024-03-19"},
}
IVIS_DATE_UNCONFIRMED = {13}                     # week-13 IVIS date is a guess
IVIS_FILE = "IVISlungdata042024_all_animals.csv"
LAST_WEEK = {"75": 11}                          # leaves the study after week 11
# Real reconstruction slice counts from the atwai index (other weeks simulated)
MCT_SLICES = {13: {"10": 694, "11": 696, "12": 692, "13": 614, "14": 680, "15": 707,
                   "17": 648, "18": 708, "19": 608, "67": 637, "68": 627, "69": 605},
              14: {m: 670 for m in ("10", "11", "12", "13", "14", "15", "17", "18",
                                    "19", "67", "68", "69")}}


MODALITIES = [
    {"name": "IVIS", "code": "IVIS",
     "instrument": "PerkinElmer IVIS Spectrum",
     "readout": "Bioluminescence, thoracic ROI total flux (p/s); supine, prone, left, right views",
     "pattern_name": "ivis_session", "folder": "IVIS"},
    {"name": "microCT", "code": "MCT",
     "instrument": "Bruker SkyScan 1276",
     "readout": "Aerated lung, % of total lung volume (falls as tumor grows)",
     "pattern_name": "bruker_skyscan_scan", "folder": "microCT"},
    {"name": "MRI", "code": "MRI",
     "instrument": "Bruker BioSpec (model TBD)",
     "readout": "Tumor ROI size, pixels (Dragonfly segmentation)",
     "pattern_name": "bruker_paravision_mr", "folder": "MRI"},
]

STUDY = {
    "id": STUDY_ID,
    "title": "Multimodal monitoring of mouse lung tumors (protocol development)",
    "facility": "Koch Institute Animal Imaging & Preclinical Testing core",
    "purpose": "Protocol development: compare MRI, microCT and IVIS for tracking lung tumor burden",
    "species": "Mus musculus",
    "strain": "TBD",
    "model": "Lung tumor model with luciferase reporter (details TBD)",
    "cac_protocol": "TBD",
    "acquisition": "Milton (protocol development, microCT)",
    "analysis": "Anderson (tumor segmentation, 2025)",
    "start_date": START.isoformat(),
    "imaging_weeks": "6-14",
    "imaging_start": "2024-01-22",
    "imaging_end": "2024-03-19",
    "endpoint": "Lung tumor burden over time",
    "source_folders": ("atwai: Milton_CornwallBrady/Protocol Development in vivo/"
                       "MultiModal Lung tumor test (microCT recon); Anderson_Scott/Multimodal/"
                       "MultiModal Lung tumor test (raw + processed); Dropbox MultiModal/LungTumor"),
    "note": ("Structure and measurement values are real (analysis results in "
             "source_results/). Acquisition parameters, cage/ID pairing, sex and age "
             "are placeholders."),
}


def present(mod, w, m):
    if w not in DATES[mod] or w > LAST_WEEK.get(m, 99):
        return False
    if mod == "MRI" and w == 10:
        return m == "13"
    return True


# ------------------------------------------------------------ real results
def _num(x):
    x = (x or "").strip()
    if not x or x.upper() == "NA":
        return None
    return float(x)


def read_results(d):
    """Analysis results as delivered -> {(modality, mouse, week): [(kind, value, unit, method)]}."""
    d = Path(d)
    out = {}

    def add(mod, m, w, *rec):
        out.setdefault((mod, m, w), []).append(rec)

    # microCT: aerated lung, % of total lung volume (falls as tumor grows)
    with (d / "aerated_vol_uCT.csv").open() as fh:
        r = csv.reader(fh)
        weeks = [int(h[2:]) for h in next(r)[1:]]
        for row in r:
            m = row[0].split()[-1]
            for w, v in zip(weeks, row[1:]):
                if _num(v) is not None:
                    add("microCT", m, w, "aerated_lung_pct", _num(v), "% of total lung volume",
                        "aerated-lung segmentation (Anderson)")

    # MRI: tumor ROI size in pixels (voxel size needed to convert to mm3)
    with (d / "pixel_count_MRI.csv").open() as fh:
        r = csv.reader(fh)
        weeks = [int(h[2:]) for h in next(r)[1:]]
        for row in r:
            m = row[0].split()[-1]
            for w, v in zip(weeks, row[1:]):
                if _num(v) is not None:
                    add("MRI", m, w, "tumor_pixel_count", int(_num(v)), "pixels",
                        "tumor ROI segmentation in Dragonfly (Anderson)")

    # IVIS: one block per view in the left-hand columns; first block of each view only
    views, view, header, rows = {}, None, None, list(csv.reader((d / IVIS_FILE).open()))
    for row in rows:
        c0 = row[0].strip().lower() if row else ""
        if c0 in ("supine", "prone", "left", "right", "% change"):
            view, header = (None if c0 in views or c0 == "% change" else c0), None
            continue
        if view is None:
            continue
        cells = row[:10]
        if header is None:
            if any(c.strip().isdigit() for c in cells[1:]):
                header = {i: int(c) for i, c in enumerate(cells) if i and c.strip().isdigit()}
            continue
        if not cells[0].strip():
            views[view] = True
            view = None
            continue
        for i, w in header.items():
            v = _num(cells[i]) if i < len(cells) else None
            if v is not None:
                kind = "total_flux" if view == "supine" else f"total_flux_{view}"
                add("IVIS", cells[0].strip(), w, kind, v, "p/s",
                    f"thoracic ROI, {view} view (Living Image)")
    return out


def simulate(seed, results_dir):
    """Build subjects/sessions from the study structure; measurements from the real results."""
    results = read_results(results_dir)
    subjects, sessions, measurements = [], [], []
    CONTROLS = {"M67", "M68", "M69", "M75"}       # uninjected controls (study team, Oct 2026)
    for m, cage, punch in MICE:
        sid = f"M{m}"
        subjects.append({
            "id": sid, "study_id": STUDY_ID, "sex": "", "cage": cage, "ear_tag": punch,
            "group": "control (not injected)" if sid in CONTROLS else "USGI tumor injection",
            "age_at_inoculation_wk": "",
            "placeholder_fields": "cage and ear_tag pairing; sex and age unknown",
        })
        for mod in MODALITIES:
            name = mod["name"]
            for w in WEEKS:
                if not present(name, w, m):
                    continue
                sess_id = f"LWM-{mod['code']}-{sid}-W{w:02d}"
                if name == "microCT":
                    params = {"values_source": "voxel size from SkyScan reconstruction log (week 13); rest placeholder",
                              "scanner": "SkyScan 1276", "reconstruction": "NRecon",
                              "voxel_um": 36.9}
                    if w in MCT_SLICES and m in MCT_SLICES[w]:
                        params["recon_slices"] = MCT_SLICES[w][m]
                elif name == "MRI":
                    params = {"values_source": "resolution from ParaVision method (week 13); rest placeholder",
                              "sequence": ("T1 and T2, axial and coronal (extra series)" if w == 10
                                           else "T2-weighted (TBD)"),
                              "matrix": "256x256", "in_plane_mm": 0.15625, "slice_mm": 0.5}
                else:
                    params = {"values_source": "placeholder (replace with ClickInfo.txt)",
                              "imaged_as": f"cage {cage}", "software": "Living Image"}
                    if w in IVIS_DATE_UNCONFIRMED:
                        params["acq_date_note"] = "date not confirmed: week-13 folder is a copy of week 12"
                sessions.append({
                    "id": sess_id, "subject": sid, "modality": name,
                    "study_week": w, "acq_date": DATES[name][w],
                    "pattern_name": mod["pattern_name"],
                    "folder": f"{mod['folder']}/wk{w}/{sid}",
                    "params_json": json.dumps(params, sort_keys=True),
                })
                for kind, val, unit, method in results.pop((name, m, w), []):
                    measurements.append({
                        "session_id": sess_id, "kind": kind, "value": val,
                        "unit": unit, "method": method, "detected": True,
                    })
    if results:   # a result with no matching imaging session means the structure is wrong
        raise SystemExit(f"results without a session: {sorted(results)[:10]}")
    return subjects, sessions, measurements


def observations(sessions, measurements):
    S = {"type": "Study", "id": STUDY_ID}
    mod = lambda n: {"type": "Modality", "id": n}
    sub = lambda m: {"type": "Subject", "id": f"M{m}"}
    return [
        {"id": "OBS-GAP-MRI-W10", "kind": "data_gap", "modality": "MRI", "weeks": [10],
         "text": "No MRI in week 10 except mouse 13, which was scanned early (Fri Feb 16) "
                 "with extra T1/T2 axial and coronal series; that scan was not segmented.",
         "reason": "MRI specialist on vacation that week",
         "author": "Study team", "about": [S, mod("MRI")]},
        {"id": "OBS-GAP-MCT-W12", "kind": "data_gap", "modality": "microCT", "weeks": [12],
         "text": "No microCT in week 12 for any mouse; the atwai index shows no "
                 "reconstruction activity at all Mar 1-7, 2024.",
         "reason": "microCT specialist on vacation that week",
         "author": "Study team", "about": [S, mod("microCT")]},
        {"id": "OBS-CONTROLS", "kind": "study_design",
         "text": "Mice 67, 68, 69 and 75 are uninjected controls; the other 9 mice received the USGI "
                 "tumor injection. Controls were imaged on every modality but not analyzed on MRI or IVIS, "
                 "and are excluded from the take rate.",
         "author": "Study team", "about": [S] + [sub(m) for m in ("67", "68", "69", "75")]},
        {"id": "OBS-EXIT-M75", "kind": "early_exit", "subject": "M75", "weeks": [11],
         "text": "Mouse 75 (an uninjected control) has no imaging after week 11 on any modality.",
         "reason": "control; reason for exit not recorded", "author": "Data curation",
         "about": [S, sub("75")]},
        {"id": "OBS-MRI-ANALYZED", "kind": "analysis_coverage", "modality": "MRI",
         "text": "MRI tumor size was measured for 8 mice (10, 11, 12, 13, 14, 15, 17, 19). "
                 "Mouse 15 has only week 6; mice 17 and 19 start at week 8; 18, 67, 68, 69 "
                 "and 75 were imaged but not segmented. Values are reported as pixel counts but are voxels summed "
                 "over slices; each session's ParaVision voxel size (0.0122 mm3) converts them to mm3.",
         "author": "Data curation",
         "about": [S, mod("MRI")] + [sub(m) for m in ("15", "18", "67", "68", "69", "75")]},
        {"id": "OBS-IVIS-ANALYZED", "kind": "analysis_coverage", "modality": "IVIS",
         "text": "IVIS flux was quantified for 4 mice only (10, 13, 14, 15), in up to four "
                 "views: supine (weeks 6-14), left and right (9-14), prone (11-14). Mouse 13 "
                 "has no supine week 14.",
         "author": "Data curation",
         "about": [S, mod("IVIS")] + [sub(m) for m in ("10", "13", "14", "15")]},
        {"id": "OBS-IVIS-W13-FOLDER", "kind": "provenance", "modality": "IVIS", "weeks": [13],
         "text": "The Dropbox week-13 IVIS folder is a copy of week 12 (same Mar 5 sequences), "
                 "but the analysis sheet has distinct week-13 values, so the week-13 images "
                 "are misfiled or stored elsewhere.",
         "author": "Data curation", "about": [S, mod("IVIS")]},
        {"id": "OBS-MCT-INVERSE", "kind": "measurement_note", "modality": "microCT",
         "text": "microCT reports aerated lung as % of total lung volume, which falls as tumor "
                 "grows. Mice 13, 17, 10 and 12 drop from ~80% to 11-40% by week 14; 18, 67, "
                 "68 and 69 stay near 80%.",
         "author": "Anderson (analysis)", "about": [mod("microCT")]},
        {"id": "OBS-IVIS-DISCORDANCE", "kind": "modality_discordance", "modality": "IVIS",
         "compared_to": ["microCT", "MRI"],
         "text": ("IVIS separates high (10, 13) from low (14, 15) burden like microCT and MRI, "
                  "but orders them differently: mouse 10 is brightest on IVIS while mouse 13 "
                  "has the most tumor on MRI and microCT. Flux is a single-view, 2D signal."),
         "possible_causes": ("depth attenuation in lung; luciferin uptake timing; "
                             "necrotic tumor cores; view dependence"),
         "author": "Anderson (analysis summary)",
         "about": [S, mod("IVIS")], "contrasts": ["microCT", "MRI"]},
        {"id": "OBS-MCT-W14-RECON", "kind": "protocol_change", "modality": "microCT", "weeks": [14],
         "text": "Every week-14 reconstruction has exactly 667 slices (SkyScan logs), unlike every "
                 "earlier week (493-720); a fixed reconstruction range was used that week.",
         "author": "Data curation (instrument logs)", "about": [mod("microCT")]},
        {"id": "OBS-MCT-EXPOSURE", "kind": "protocol_change", "modality": "microCT", "weeks": [8],
         "text": "microCT exposure changed from 127 ms (weeks 6-7) to 139 ms (week 8 onward); "
                 "voltage (100 kV), current (200 uA), filter (Al 0.5 mm) and voxel size (36.9 um) "
                 "stayed fixed.",
         "author": "Data curation (instrument logs)", "about": [mod("microCT")]},
        {"id": "OBS-MCT-DOSE", "kind": "measurement_note", "modality": "microCT",
         "text": "The scanner estimates about 434 mGy per scan for a mouse, about 3.5 Gy over the "
                 "8 weekly scans; worth weighing in longitudinal designs, since radiation can "
                 "affect tumor growth.",
         "author": "Data curation (instrument logs)", "about": [S, mod("microCT")]},
        {"id": "OBS-MRI-W12-SLICES", "kind": "protocol_change", "modality": "MRI", "weeks": [12],
         "text": "In week 12 most T2 axial series used 40 slices (20 mm coverage) and TR 4000 ms, "
                 "instead of 46 slices (23 mm) and TR 4379 ms in every other week; large tumors "
                 "could extend past the covered region.",
         "author": "Data curation (instrument logs)", "about": [mod("MRI")]},
        {"id": "OBS-IVIS-EXPOSURE", "kind": "protocol_change", "modality": "IVIS", "weeks": [12, 14],
         "text": "IVIS used 60 s exposures through week 11, then shorter ones (20-25 s in week 12, "
                 "0.75-60 s in week 14), consistent with bright tumors saturating the camera. "
                 "Flux is exposure-normalized, but late images are not acquired the same way.",
         "author": "Data curation (instrument logs)", "about": [mod("IVIS")]},
        {"id": "OBS-MCT-STORAGE", "kind": "provenance", "modality": "microCT",
         "text": ("Only reconstructions are on atwai (no SkyScan projections). Identical "
                  "copies sit in Milton's protocol-development folder, Anderson's raw data "
                  "folder and the facility archive; the Dropbox copy stops at week 11."),
         "author": "Data curation", "about": [S, mod("microCT")]},
    ]


# ------------------------------------------------------------ instrument files
FACILITY_RATE = {"microCT": 137.81, "MRI": 275.63, "IVIS": 144.38}     # $/hour
MICE_IDS = {f"M{m}" for m, _, _ in MICE}


def _clean(d):
    return {k: (v.item() if hasattr(v, "item") else v) for k, v in d.items()
            if v is not None and not (isinstance(v, float) and math.isnan(v))}


def instrument_metadata(sessions, acq_dir="source_results"):
    """Real acquisition parameters and timing onto each session, plus Acquisition and
    Instrument nodes and their links. Returns (nodes, links)."""
    d = Path(acq_dir)
    ct = pd.read_csv(d / "acq_microct.csv")
    mr = pd.read_csv(d / "acq_mri.csv")
    iv = pd.read_csv(d / "acq_ivis.csv")
    iv = iv[~iv.copy_of_week_12]
    mr.loc[~mr.subject.isin(MICE_IDS), "subject"] = None        # planning / UTE scans
    by_id = {se["id"]: se for se in sessions}
    CODE = {"microCT": "MCT", "MRI": "MRI", "IVIS": "IVIS"}
    sid = lambda mod, m, w: f"LWM-{CODE[mod]}-M{m}-W{int(w):02d}"
    nodes, links = [], []
    link = lambda sl, a, rel, dl, b: links.append(
        {"src_label": sl, "src": a, "rel": rel, "dst_label": dl, "dst": b})

    def set_params(se_id, params):
        if se_id in by_id:
            by_id[se_id]["params_json"] = json.dumps(_clean(params), sort_keys=True, default=str)

    # ---- microCT: one scan per mouse-week, parameters straight from the SkyScan log
    ct["start"] = pd.to_datetime(ct.scan_start)
    ct = ct.sort_values(["week", "start"])
    ct["slot_min"] = ct.groupby("week").start.diff().shift(-1).dt.total_seconds() / 60
    for r in ct.itertuples():
        a_id = f"acq:microCT:{r.subject}:W{r.week:02d}"
        props = {k: getattr(r, k) for k in (
            "scan_start", "scan_duration_s", "recon_time", "source_kv", "source_ua", "filter",
            "exposure_ms", "rotation_step_deg", "frame_averaging", "camera_binning", "projections",
            "voxel_um", "dose_mouse_mgy", "recon_program", "recon_slices", "recon_width_px",
            "recon_height_px", "smoothing", "ring_artifact_correction", "beam_hardening_pct",
            "scanner_data_dir", "log")}
        nodes.append({"id": a_id, "kind": "Acquisition", "modality": "microCT", "week": r.week,
                      "subject": r.subject, "name": f"{r.subject} week {r.week} microCT scan",
                      **_clean(props)})
        se = sid("microCT", r.subject[1:], r.week)
        link("ImagingSession", se, "HAS_ACQUISITION", "Acquisition", a_id)
        link("Acquisition", a_id, "ON_INSTRUMENT", "Instrument", "instrument:microCT")
        link("Acquisition", a_id, "WRITTEN_ON", "Host", "host:microct-pc")
        set_params(se, {"values_source": "SkyScan reconstruction log", **props,
                        "acq_start": r.scan_start,
                        "acq_end": (r.start + pd.Timedelta(seconds=r.scan_duration_s)).isoformat(),
                        "slot_min": round(r.slot_min, 1) if pd.notna(r.slot_min) else None})

    # ---- MRI: several series per mouse; time each from the scan-log timestamps
    mr["end"] = pd.to_datetime(mr.scan_end)
    mr["study_start"] = pd.to_datetime(mr.study_folder.str[:15], format="%Y%m%d_%H%M%S")
    mr = mr.sort_values(["week", "end"])
    mr["prev_end"] = mr.groupby("week").end.shift(1).fillna(mr.study_start)
    mr["minutes"] = (mr.end - mr.prev_end).dt.total_seconds() / 60
    pv = lambda study: f"atwai:/data0/core/atwai/huangw/2024/{study}"
    for r in mr.itertuples():
        a_id = f"acq:MRI:{r.study_folder}:{r.scan}"
        props = {k: getattr(r, k) for k in (
            "scan", "scan_name", "protocol", "method", "tr_ms", "te_ms", "rare_factor", "averages",
            "matrix", "fov_mm", "in_plane_mm", "slice_mm", "slices", "orientation",
            "acq_time_s_computed", "scan_end")}
        nodes.append({"id": a_id, "kind": "Acquisition", "modality": "MRI", "week": r.week,
                      "subject": r.subject, "name": r.scan_name, "minutes": round(r.minutes, 1),
                      **_clean(props)})
        link("Acquisition", a_id, "ON_INSTRUMENT", "Instrument", "instrument:MRI")
        link("Acquisition", a_id, "STORED_IN", "Folder", pv(r.study_folder))
        if isinstance(r.subject, str):
            link("ImagingSession", sid("MRI", r.subject[1:], r.week), "HAS_ACQUISITION",
                 "Acquisition", a_id)
    for (w, m), x in mr[mr.subject.notna()].groupby(["week", "subject"]):
        t2 = x[x.protocol.str.contains("T2", na=False) & x.orientation.str.startswith("axial", na=False)]
        main_series = (t2 if len(t2) else x).iloc[0]
        set_params(sid("MRI", m[1:], w), {
            "values_source": "ParaVision method/acqp; times from scan logs",
            "series": len(x), "main_series": main_series.scan_name,
            "sequence": main_series.method, "tr_ms": main_series.tr_ms, "te_ms": main_series.te_ms,
            "rare_factor": main_series.rare_factor, "averages": main_series.averages,
            "matrix": main_series.matrix, "fov_mm": main_series.fov_mm,
            "in_plane_mm": main_series.in_plane_mm, "slice_mm": main_series.slice_mm,
            "slices": main_series.slices,
            "voxel_mm3": round(main_series.in_plane_mm ** 2 * main_series.slice_mm, 5),
            "acq_time_s_computed": main_series.acq_time_s_computed,
            "acq_start": x.prev_end.min().isoformat(), "acq_end": x.end.max().isoformat(),
            "slot_min": round(x.minutes.sum(), 1), "study_folder": main_series.study_folder})

    # ---- IVIS: whole-cohort images (no animal labels); timing per weekly session
    iv["t"] = pd.to_datetime(iv.acquired)
    for r in iv.itertuples():
        a_id = f"acq:IVIS:{r.click}"
        props = {k: getattr(r, k) for k in (
            "click", "acquired", "exposure_s", "binning", "f_number", "fov_cm",
            "emission_filter", "excitation_filter", "ccd_temp_c")}
        nodes.append({"id": a_id, "kind": "Acquisition", "modality": "IVIS", "week": r.week,
                      "name": f"IVIS image {r.click}", **_clean(props)})
        link("Acquisition", a_id, "ON_INSTRUMENT", "Instrument", "instrument:IVIS")
        seqdir = r.path[: r.path.index(r.sequence) + len(r.sequence)]
        link("Acquisition", a_id, "STORED_IN", "Folder", f"Dropbox:MultiModal/LungTumor/{seqdir}")
    for w, x in iv.groupby("week"):
        params = {"values_source": "Living Image ClickInfo (cohort images, no animal labels)",
                  "images": len(x), "acq_start": x.t.min().isoformat(),
                  "acq_end": x.t.max().isoformat(),
                  "session_min": round((x.t.max() - x.t.min()).total_seconds() / 60, 1)
                                 if x.t.dt.date.nunique() == 1 else None,
                  "exposures_s": ", ".join(f"{e:g}" for e in sorted(x.exposure_s.unique())),
                  "binning": "/".join(sorted(x.binning.astype(str).unique())),
                  "f_number": "/".join(sorted(x.f_number.astype(str).unique())),
                  "fov_cm": "/".join(sorted(x.fov_cm.astype(str).unique()))}
        for se in sessions:
            if se["modality"] == "IVIS" and se["study_week"] == w:
                set_params(se["id"], params)

    for se in sessions:
        if se["modality"] == "IVIS" and se["study_week"] not in set(iv.week):
            set_params(se["id"], {"values_source": "no ClickInfo: the week-13 IVIS folder is a copy "
                                                   "of week 12; real week-13 images not found"})

    # ---- instruments, with the measured time model and the facility rate
    full = mr[mr.subject.notna()].groupby(["week", "subject"]).minutes.sum()
    iv_sessions = iv.groupby(iv.t.dt.date).t.agg(lambda t: (t.max() - t.min()).total_seconds() / 60)
    first = lambda col: col.dropna().iloc[0] if col.notna().any() else None
    instruments = [
        {"id": "instrument:microCT", "modality": "microCT", "name": f"{first(ct.scanner)}",
         "model": "Bruker SkyScan 1276", "serial": first(ct.serial),
         "software": f"SkyScan {first(ct.software_version)}; {first(ct.recon_program)}",
         "setup_min": 10, "mice_per_acq": 1,
         "min_per_acq": round(float(ct.slot_min.median()), 1),
         "time_source": "median gap between consecutive scan starts (SkyScan logs); setup estimated",
         "rate_per_hour": FACILITY_RATE["microCT"]},
        {"id": "instrument:MRI", "modality": "MRI", "name": "Bruker BioSpec",
         "model": "Bruker BioSpec (ParaVision)", "software": "ParaVision",
         "setup_min": 15, "mice_per_acq": 1,
         "min_per_acq": round(float(full.median()), 1),
         "time_source": "median scanner minutes per mouse (scan logs, all series); setup estimated",
         "rate_per_hour": FACILITY_RATE["MRI"]},
        {"id": "instrument:IVIS", "modality": "IVIS", "name": first(iv.system),
         "model": first(iv.system), "camera": first(iv.camera), "software": first(iv.software),
         "setup_min": 15, "mice_per_acq": 5,
         "min_per_acq": round(float((iv_sessions.median() - 15) / 3), 1),
         "time_source": "median weekly session length (ClickInfo times) less 15 min luciferin uptake, "
                        "over 3 cage groups",
         "rate_per_hour": FACILITY_RATE["IVIS"]},
    ]
    for ins in instruments:
        nodes.append({"kind": "Instrument", **_clean(ins)})
        link("Modality", ins["modality"], "USES_INSTRUMENT", "Instrument", ins["id"])
    link("Instrument", "instrument:microCT", "WRITES_TO", "Host", "host:microct-pc")
    link("Instrument", "instrument:MRI", "WRITES_TO", "Host", "host:bmc-lab6")
    return nodes, links


# ------------------------------------------------------------ files on disk
RESULT_FILES = {   # which results table each modality's measurements came from
    "microCT": "aerated_vol_uCT.csv", "MRI": "pixel_count_MRI.csv",
    "IVIS": IVIS_FILE,
}
REPO_RESULTS = "repo:demo_data/lwm2026/source_results"
# Machines that hold or produced this study's data (from the listings and instrument logs)
HOSTS = [
    {"id": "host:bmc-lab6", "name": "bmc-lab6", "role": "file server",
     "note": "serves the facility share atwai at /data0/core/atwai"},
    {"id": "host:dropbox", "name": "Dropbox (MIT)", "role": "cloud storage",
     "note": "synced folder AIPT/Imaging/MultiModal/LungTumor"},
    {"id": "host:ki-ed3g", "name": "ki-ed3g", "role": "workstation",
     "note": "Dropbox synced at /mnt/data/cloud/Dropbox (MIT); runs the atwai scan index"},
    {"id": "host:microct-pc", "name": "MICROCT", "role": "instrument PC",
     "note": "SkyScan 1276 acquisition and reconstruction PC; writes to D:\\Results"},
    {"id": "host:repo", "name": "GitHub (science_data_kit)", "role": "code repository",
     "note": "analysis results as delivered, versioned with this demo"},
]
HOST_OF = {"Dropbox": "host:dropbox", "atwai": "host:bmc-lab6", "repo": "host:repo"}


def build_files(inventory, sessions, measurements):
    """File/Folder nodes from the inventory, plus the links that tie them to the study."""
    inv = pd.read_csv(inventory, dtype={"subject": str})
    inv = inv.astype(object).where(inv.notna(), None)
    inv["host"] = inv.location.map(lambda l: HOST_OF[l].split(":", 1)[1])
    nodes = inv.drop(columns=["copy_of", "parent"]).to_dict("records")
    for mod, fname in RESULT_FILES.items():
        nodes.append({"id": f"{REPO_RESULTS}/{fname}", "kind": "File", "location": "repo",
                      "path": f"demo_data/lwm2026/source_results/{fname}", "name": fname,
                      "role": "result", "modality": mod, "host": "repo",
                      "note": "analysis results as delivered (the values in this graph)"})
    nodes += [{"kind": "Host", **h} for h in HOSTS]
    links = []
    link = lambda sl, s, rel, dl, d: links.append(
        {"src_label": sl, "src": s, "rel": rel, "dst_label": dl, "dst": d})
    kind = dict(zip(inv.id, inv.kind))

    for r in inv.itertuples():
        if r.role == "root":
            link("Study", STUDY_ID, "HAS_FOLDER", r.kind, r.id)
            link(r.kind, r.id, "ON_HOST", "Host", HOST_OF[r.location])
        if r.parent:
            link(kind[r.parent], r.parent, "CONTAINS", r.kind, r.id)
        if r.copy_of:
            link(r.kind, r.id, "COPY_OF", kind[r.copy_of], r.copy_of)
        if r.role == "derived" and r.subject and r.week is None:
            link("Subject", r.subject, "HAS_DERIVED", r.kind, r.id)

    raw = inv[inv.role == "raw"]
    der = inv[(inv.role == "derived") & inv.week.notna() & inv.subject.notna()]
    for se in sessions:
        w, m, mod = se["study_week"], se["subject"], se["modality"]
        hits = raw[(raw.modality == mod) & (raw.week == w) &
                   ((raw.subject == m) | (raw.subject.isna() & ~raw.nested.astype(bool)))]
        for r in hits.itertuples():
            link("ImagingSession", se["id"], "STORED_IN", r.kind, r.id)
        for r in der[(der.modality == mod) & (der.week == w) & (der.subject == m)].itertuples():
            link("ImagingSession", se["id"], "HAS_DERIVED", r.kind, r.id)
    for me in measurements:
        mod = next(x["modality"] for x in sessions if x["id"] == me["session_id"])
        link("Measurement", f"{me['session_id']}:{me['kind']}", "REPORTED_IN", "File",
             f"{REPO_RESULTS}/{RESULT_FILES[mod]}")
    for mod, fname in RESULT_FILES.items():
        link("File", f"{REPO_RESULTS}/{fname}", "ON_HOST", "Host", "host:repo")
    link("Host", "host:dropbox", "SYNCED_TO", "Host", "host:ki-ed3g")
    link("File", f"{REPO_RESULTS}/{IVIS_FILE}", "EXPORTED_FROM", "File",
         "Dropbox:MultiModal/LungTumor/IVISlungdata042024.xlsx")
    return nodes, links


# ---------------------------------------------------------------- file tree
def write_tree(root, subjects, sessions, measurements, obs):
    root = Path(root) / "LWM_demo_lung"
    by_sess = {}
    for m in measurements:
        by_sess.setdefault(m["session_id"], {})[m["kind"]] = m

    def touch(p, text=""):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    touch(root / "README_SIMULATED.txt",
          "Synthetic placeholder files for a teaching demo. Image files are empty.\n")
    for s in sessions:
        d = root / s["folder"]
        p = json.loads(s["params_json"])
        stamp = f"{s['subject']}_W{s['study_week']:02d}"
        if s["modality"] == "IVIS":
            touch(d / "ClickInfo.txt", "\n".join([
                "*** ClickNumber: " + s["id"],
                f"*** User: {p['operator']}",
                f"Acquisition Date: {s['acq_date']}",
                f"Animal Number: {s['subject']}",
                "*** Luminescent Image",
                f"Exposure Time: {p['exposure_s']}",
                f"Binning Factor: {p['binning']}",
                f"f Number: {p['f_stop']}",
                f"Field of View: {p['field_of_view']}",
                f"Emission filter: {p['emission_filter']}",
                "*** Comments",
                f"Luciferin: {p['luciferin_dose']}, t+{p['minutes_post_luciferin']} min",
                ""]))
            for f in ("luminescent.TIF", "photograph.TIF", "readbiasonly.TIF"):
                touch(d / f)
        elif s["modality"] == "microCT":
            touch(d / f"{stamp}.log", "\n".join([
                "[System]", "Scanner=SkyScan1276",
                "[Acquisition]",
                f"Study Date and Time={s['acq_date']}",
                f"Source Voltage (kV)={p['source_voltage_kv']}",
                f"Source Current (uA)={p['source_current_ua']}",
                f"Image Pixel Size (um)={p['image_pixel_size_um']}",
                f"Filter={p['filter']}",
                f"Rotation Step (deg)={p['rotation_step_deg']}",
                f"Frame Averaging=ON ({p['frame_averaging']})",
                f"Gating={p['gating']}",
                "[User]", f"Operator={p['operator']}", ""]))
            rec = d / f"{stamp}_rec"
            touch(rec / f"{stamp}_rec.log", f"[Reconstruction]\nProgram={p['reconstruction']}\n")
            for k in (100, 101, 102):
                touch(rec / f"{stamp}_rec{k:08d}.png")
        else:
            n = d / "5"
            touch(n / "method", "\n".join([
                f"##$Method=<Bruker:{p['sequence']}>",
                f"##$PVM_RepetitionTime={p['tr_ms']}",
                f"##$PVM_EchoTime={p['te_ms']}",
                f"##$PVM_RareFactor={p['rare_factor']}",
                f"##$PVM_SliceThick={p['slice_thickness_mm']}",
                f"##$PVM_NAverages={p['averages']}", ""]))
            touch(n / "acqp", f"##$ACQ_sw_version=<{p['software']}>\n")
            touch(n / "pdata" / "1" / "2dseq")
            touch(d / "subject", f"##$SUBJECT_id=<{s['subject']}>\n"
                                 f"##$SUBJECT_study_name=<{STUDY_ID}>\n")

    # Analyst outputs, the way they tend to exist: one CSV per modality
    for mod, kind, fname in [("microCT", "aerated_lung_pct", "microCT_aerated_lung_pct.csv"),
                             ("MRI", "tumor_pixel_count", "MRI_tumor_pixel_counts.csv"),
                             ("IVIS", "total_flux", "IVIS_thoracic_ROI_flux.csv")]:
        rows = [(s["subject"], s["study_week"], by_sess[s["id"]][kind]["value"])
                for s in sessions
                if s["modality"] == mod and kind in by_sess.get(s["id"], {})]
        p = root / "analysis" / fname
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["mouse", "week", kind])
            w.writerows(rows)

    touch(root / "notes" / "imaging_log.txt", "\n".join(
        [f"- {o['id']}: {o['text']}" + (f" Reason: {o['reason']}" if o.get("reason") else "")
         for o in obs]) + "\n")
    return root


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data")
    ap.add_argument("--seed", type=int, default=20261005)
    ap.add_argument("--path-prefix", default="/data0/core/atwai/LWM_demo_lung")  # placeholder paths
    ap.add_argument("--tree", default=None, help="also write placeholder file tree here")
    ap.add_argument("--results", default="source_results", help="folder with the analysis CSVs")
    ap.add_argument("--inventory", default="source_results/file_inventory.csv",
                    help="file inventory from build_file_inventory.py")
    args = ap.parse_args()

    subjects, sessions, measurements = simulate(args.seed, args.results)
    # real acquisition parameters and timing replace the placeholders on each session
    inodes, ilinks = instrument_metadata(sessions)
    obs = observations(sessions, measurements)
    for s in sessions:
        s["root_path"] = f"{args.path_prefix.rstrip('/')}/{s['folder']}"

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "study.json").write_text(json.dumps(
        {"dataset": DATASET, "synthetic": False, "placeholders": "acquisition parameters, cage/ID pairing, sex, age",
         "study": STUDY,
         "modalities": [{k: v for k, v in m.items() if k not in ("code", "day_offset", "folder")}
                        for m in MODALITIES]}, indent=2))
    for name, rows in [("subjects.csv", subjects), ("sessions.csv", sessions),
                       ("measurements.csv", measurements)]:
        with (out / name).open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    (out / "observations.json").write_text(json.dumps(obs, indent=2))
    if Path(args.inventory).exists():
        fnodes, flinks = build_files(args.inventory, sessions, measurements)
        pd.DataFrame(fnodes + inodes).to_csv(out / "nodes.csv", index=False)
        pd.DataFrame(flinks + ilinks).to_csv(out / "links.csv", index=False)
        for old in ("files.csv", "file_links.csv"):
            (out / old).unlink(missing_ok=True)
        print(f"files on disk: {sum(n['kind'] in ('File', 'Folder') for n in fnodes)} File/Folder nodes; instruments: "
              f"{sum(n['kind'] == 'Acquisition' for n in inodes)} acquisitions, "
              f"{sum(n['kind'] == 'Instrument' for n in inodes)} instruments; "
              f"{len(flinks) + len(ilinks)} links")

    print(f"{DATASET}: {len(subjects)} subjects, {len(sessions)} sessions, "
          f"{len(measurements)} measurements, {len(obs)} observations -> {out}/")
    if args.tree:
        r = write_tree(args.tree, subjects, sessions, measurements, obs)
        n = sum(1 for _ in r.rglob("*") if _.is_file())
        print(f"placeholder file tree: {n} files under {r}")


if __name__ == "__main__":
    main()
