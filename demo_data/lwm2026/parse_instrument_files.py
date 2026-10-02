#!/usr/bin/env python3
"""
parse_instrument_files.py: turn the instrument-file dumps in source_results/listings/
into tidy tables of acquisition parameters and timestamps.

  mct_rec_logs.txt.gz      SkyScan reconstruction logs (one per microCT scan), from
                           ssh bmc-lab6 'for f in ".../raw data/"*_Rec/*.log; do grep -H "=" "$f"; done'
  mri_method_acqp.txt.gz   ParaVision method/acqp key parameters, one block per scan
  atwai_mri_scan_logs.csv.gz  MrAcqReco.log times per scan folder (when each scan finished)
  ivis_clickinfo.txt.gz    Living Image ClickInfo.txt files, one per image sequence

Writes source_results/acq_microct.csv, acq_mri.csv, acq_ivis.csv.
"""
import gzip
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

L = Path("source_results/listings")
OUT = Path("source_results")


# ------------------------------------------------------------------ microCT
def parse_microct():
    rows = {}
    for line in gzip.open(L / "mct_rec_logs.txt.gz", "rt", errors="replace"):
        path, _, kv = line.rstrip("\n").partition(".log:")
        path += ".log"
        if path.endswith("_rectmp.log") or "=" not in kv:
            continue
        m = re.search(r"/wk(\d+)[-_](\d+)_Rec/", path)
        if not m:
            continue
        key, _, val = kv.partition("=")
        rows.setdefault(path, {"week": int(m.group(1)), "subject": f"M{m.group(2)}",
                               "log": path})[key.strip()] = val.strip()
    out = []
    for r in rows.values():
        start = datetime.strptime(re.sub(r"\s+", " ", r["Study Date and Time"]), "%d %b %Y %Hh:%Mm:%Ss")
        h, mi, s = map(int, re.findall(r"\d+", r["Scan duration"]))
        recon = datetime.strptime(re.sub(r"\s+", " ", r["Time and Date"]), "%b %d, %Y %H:%M:%S")
        num = lambda k: float(re.findall(r"[-\d.]+", r[k])[0]) if k in r else None
        out.append({
            "week": r["week"], "subject": r["subject"],
            "scan_start": start.isoformat(), "scan_duration_s": h * 3600 + mi * 60 + s,
            "recon_time": recon.isoformat(),
            "scanner": r.get("Scanner"), "serial": r.get("Instrument S/N"),
            "software_version": r.get("Software Version"),
            "source_kv": num("Source Voltage (kV)"), "source_ua": num("Source Current (uA)"),
            "filter": r.get("Filter"), "exposure_ms": num("Exposure (ms)"),
            "rotation_step_deg": num("Rotation Step (deg)"),
            "frame_averaging": r.get("Frame Averaging"), "camera_binning": r.get("Camera binning"),
            "projections": int(num("Number Of Files")),
            "voxel_um": num("Image Pixel Size (um)"),
            "dose_mouse_mgy": num("Dose estimation Mouse(mGy)"),
            "recon_program": f'{r.get("Reconstruction Program")} {r.get("Program Version", "").replace("Version: ", "")}',
            "recon_slices": int(num("Sections Count")),
            "recon_width_px": int(num("Result Image Width (pixels)")),
            "recon_height_px": int(num("Result Image Height (pixels)")),
            "smoothing": num("Smoothing"), "ring_artifact_correction": num("Ring Artifact Correction"),
            "beam_hardening_pct": num("Beam Hardening Correction (%)"),
            "scanner_data_dir": r.get("Data Directory"), "log": r["log"],
        })
    df = pd.DataFrame(out).sort_values(["week", "scan_start"], ignore_index=True)
    df.to_csv(OUT / "acq_microct.csv", index=False)
    return df


# ------------------------------------------------------------------ MRI
def mri_subject(name):
    m = re.match(r"<?(\d+)_", name or "")
    if not m:
        return None
    d = m.group(1)
    return f"M{d[2:]}" if len(d) == 4 and d.startswith("10") else f"M{d}"


def parse_mri():
    blocks, cur, key = [], None, None
    for line in gzip.open(L / "mri_method_acqp.txt.gz", "rt"):
        line = line.rstrip("\n")
        if line.startswith("=== "):
            cur = {"dir": line[4:].rstrip("/")}
            blocks.append(cur); key = None
        elif line.startswith("##$"):
            k, _, v = line[3:].partition("=")
            if v.startswith("( "):           # array: values on the next line
                key = k
            else:
                cur[k] = v.strip("<>"); key = None
        elif line == "--":
            key = None
        elif key and cur is not None:
            cur[key] = line.strip().strip("<>"); key = None

    logs = pd.read_csv(L / "atwai_mri_scan_logs.csv.gz")
    logs["scan_dir"] = logs.parent_path.str.replace(r"/pdata/\d+$", "", regex=True)
    end_time = logs.groupby("scan_dir").t.max()

    WK = {"20240122": 6, "20240129": 7, "20240205": 8, "20240212": 9, "20240216": 10,
          "20240226": 11, "20240304": 12, "20240311": 13, "20240318": 14}
    out = []
    for b in blocks:
        study, scan = b["dir"].split("/")[-2:]
        if not scan.isdigit():          # AdjProtocols and other non-scan folders
            continue
        f = lambda k: float(b[k].split()[0]) if k in b else None
        tr, na = f("PVM_RepetitionTime"), f("PVM_NAverages") or 1
        rare = f("PVM_RareFactor")
        matrix = [int(x) for x in b.get("PVM_Matrix", "").split()] or [None, None]
        res = [float(x) for x in b.get("PVM_SpatResol", "").split()] or [None]
        acq_s = round(tr * matrix[1] / (rare or 1) * na / 1000, 1) if tr and matrix[1] else None
        out.append({
            "week": WK.get(study[:8]), "study_folder": study, "scan": int(scan),
            "subject": mri_subject(b.get("ACQ_scan_name")),
            "scan_name": b.get("ACQ_scan_name"), "protocol": b.get("ACQ_protocol_name"),
            "method": (b.get("Method") or "").replace("Bruker:", ""),
            "tr_ms": round(tr, 1) if tr else None, "te_ms": f("PVM_EchoTime"),
            "effective_te_ms": f("EffectiveTE"), "rare_factor": rare, "averages": na,
            "matrix": "x".join(map(str, matrix)) if matrix[0] else None,
            "fov_mm": b.get("PVM_Fov", "").replace(" ", "x") or None,
            "in_plane_mm": res[0], "slice_mm": f("PVM_SliceThick"),
            "slices": b.get("PVM_SPackArrNSlices"), "orientation": b.get("PVM_SPackArrSliceOrient"),
            "acq_time_s_computed": acq_s,
            "scan_end": end_time.get(b["dir"]),
        })
    df = pd.DataFrame(out).sort_values(["week", "scan"], ignore_index=True)
    df.to_csv(OUT / "acq_mri.csv", index=False)
    return df


# ------------------------------------------------------------------ IVIS
IVIS_WEEKS = {"baseline 01222024": 6, "week7_IVIS": 7, "week8 IVIS": 8, "week9_IVIS": 9,
              "week10_IVIS": 10, "week11_IVIS": 11, "week 12_IVIS": 12, "week 13_IVIS": 13,
              "week14_IVIS": 14}


def parse_ivis():
    files = {}
    for line in gzip.open(L / "ivis_clickinfo.txt.gz", "rt", errors="replace"):
        path, _, rest = line.rstrip("\n").partition(".txt:")
        path += ".txt"
        files.setdefault(path, []).append(rest)
    out = []
    for path, lines in files.items():
        sec, info = None, {}
        for ln in lines:
            k, _, v = ln.partition(":")
            k, v = k.strip(), v.strip()
            if k.startswith("***"):
                sec = k.strip("* ").lower(); info.setdefault("click", v) if sec == "clicknumber" else None
                continue
            info[(sec, k)] = v
        lum = lambda k: info.get(("luminescent image", k))
        date, time = lum("Acquisition Date"), lum("Acquisition Time")
        if not date:
            continue
        when = datetime.strptime(f"{date} {time}", "%A, %B %d, %Y %H:%M:%S")
        folder = path.split("/")[1]
        seq = next((p for p in path.split("/") if p.startswith("SME")), None)
        out.append({
            "week": IVIS_WEEKS.get(folder), "folder": folder, "sequence": seq,
            "click": info.get("click"), "acquired": when.isoformat(),
            "exposure_s": float(lum("Luminescent Exposure (Seconds)") or "nan"),
            "binning": lum("Binning Factor"), "f_number": lum("f Number"),
            "fov_cm": lum("Field of View"), "emission_filter": lum("Emission filter"),
            "excitation_filter": lum("Excitation filter"),
            "ccd_temp_c": lum("Measured Temperature"),
            "system": info.get(("camera system info", "System Configuration")),
            "camera": info.get(("camera system info", "Camera Type")),
            "software": info.get(("clicknumber", "Living Image Version")) or
                        next((v for (s, k), v in info.items() if k == "Living Image Version"), None),
            "copy_of_week_12": folder == "week 13_IVIS",
            "path": path,
        })
    df = pd.DataFrame(out).sort_values(["acquired", "path"], ignore_index=True)
    df.to_csv(OUT / "acq_ivis.csv", index=False)
    return df


if __name__ == "__main__":
    ct, mr, iv = parse_microct(), parse_mri(), parse_ivis()
    print(f"microCT: {len(ct)} scans, weeks {sorted(ct.week.unique())}")
    print(f"MRI: {len(mr)} scans, {mr.subject.notna().sum()} assigned to a mouse")
    print(f"IVIS: {len(iv)} images ({iv.copy_of_week_12.sum()} in the week-13 copy)")
