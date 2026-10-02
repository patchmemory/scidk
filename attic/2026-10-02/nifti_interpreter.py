"""
NIfTI Neuroimaging Interpreter for SciDK.

Handles .nii and .nii.gz files — the standard neuroimaging format used by
FSL, FreeSurfer, SPM, ANTs, and most MRI/fMRI/DTI analysis pipelines.

Extracts:
  - Image dimensions and voxel sizes
  - NIfTI data type and intent code (BOLD, DTI, etc.)
  - BIDS path structure for scan type classification
  - Sidecar JSON metadata (TR, echo time, task name, etc.)
  - Affine / qform / sform details

Registered for:  .nii  .nii.gz
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseInterpreter, InterpretationResult

# ---------------------------------------------------------------------------
# NIfTI intent codes  (NIfTI-1 standard, Table 1)
# ---------------------------------------------------------------------------
_INTENT_CODES: Dict[int, str] = {
    0: "none",
    2: "correlation",
    3: "t_test",
    4: "f_test",
    5: "z_score",
    6: "chi_squared",
    1001: "estimate",
    1002: "label",
    1003: "neuronames",
    1004: "general_matrix",
    1005: "symmetric_matrix",
    1006: "displacement_vector",
    1007: "vector",
    1008: "pointset",
    1009: "triangle",
    1010: "quaternion",
    1011: "dimensionless",
    2001: "time_series",       # BOLD / fMRI
    2002: "node_index",
    2003: "rgb_vector",
    2004: "rgba_vector",
    2005: "shape",
}

# ---------------------------------------------------------------------------
# BIDS directory → scan type mapping
# ---------------------------------------------------------------------------
_BIDS_SCAN_TYPE: Dict[str, str] = {
    "func":   "BOLD_fMRI",
    "anat":   "structural_MRI",
    "dwi":    "diffusion_MRI",
    "fmap":   "fieldmap",
    "perf":   "perfusion",
    "meg":    "MEG",
    "eeg":    "EEG",
    "ieeg":   "iEEG",
    "pet":    "PET",
    "asl":    "arterial_spin_labeling",
    "mrs":    "spectroscopy",
    "micr":   "microscopy",
    "motion": "motion_capture",
}

_BIDS_SUB_RE = re.compile(r"(?:^|[/\\])(sub-[^/\\]+)", re.IGNORECASE)
_BIDS_SES_RE = re.compile(r"(?:^|[/\\])(ses-[^/\\]+)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# nibabel import — graceful fallback
# ---------------------------------------------------------------------------
try:
    import nibabel as nib  # type: ignore
    _NIBABEL_OK = True
except ImportError:
    _NIBABEL_OK = False


class NiftiInterpreter(BaseInterpreter):
    """
    Interpreter for NIfTI neuroimaging files (.nii / .nii.gz).

    NIfTI (Neuroimaging Informatics Technology Initiative) is the standard
    exchange format for MRI, fMRI, DTI, and functional neuroimaging data.
    Used by every major analysis toolkit: FSL, FreeSurfer, SPM, ANTs, MRtrix.

    Strategy:
      1. Use nibabel to read the header (memory-mapped — no full array load).
      2. Detect BIDS directory structure for scan type.
      3. Read sidecar .json if present (BIDS standard).
      4. Emit an ImagingDataset node with provenance edge back to the file.
    """

    id = "nifti"
    name = "NIfTI Neuroimaging Interpreter"
    version = "1.0.0"
    dispatch = "file"
    extensions = [".nii", ".gz"]   # .gz alone is registered; can_handle filters
    default_enabled = True

    # ------------------------------------------------------------------
    # can_handle: accept .nii or .nii.gz; reject plain .gz
    # ------------------------------------------------------------------
    def can_handle(self, path: Path, context: Optional[dict] = None) -> bool:
        name = path.name.lower()
        return name.endswith(".nii") or name.endswith(".nii.gz")

    # ------------------------------------------------------------------
    # interpret
    # ------------------------------------------------------------------
    def interpret(self, path: Path, context: Optional[dict] = None) -> InterpretationResult:
        if not path.exists():
            return self._stub(path, f"File not found: {path}")

        if not self.can_handle(path):
            return self._stub(path, f"Not a NIfTI file: {path.name}")

        try:
            header_data = self._read_header(path)
        except Exception as exc:
            return self._stub(path, f"nibabel header read failed: {exc}")

        bids = self._detect_bids(path)
        sidecar = self._read_sidecar(path)

        scan_type = bids.get("scan_type") or self._infer_scan_type(header_data)
        modality = self._infer_modality(scan_type, header_data, sidecar)

        props = self._build_properties(path, header_data, bids, sidecar, scan_type, modality)
        edges = self._build_edges(path, context)

        confidence = "confirmed" if header_data.get("_nibabel_ok") else "inferred"

        return InterpretationResult(
            node_type="ImagingDataset",
            node_label=f"{modality}: {path.name}",
            confidence=confidence,
            properties=props,
            provenance_edges=edges,
            warnings=header_data.get("_warnings", []),
            raw_metadata={**header_data, **sidecar},
        )

    # ------------------------------------------------------------------
    # Header reading (nibabel, header-only — no image array loaded)
    # ------------------------------------------------------------------
    def _read_header(self, path: Path) -> Dict[str, Any]:
        data: Dict[str, Any] = {"_warnings": [], "_nibabel_ok": False}

        if not _NIBABEL_OK:
            data["_warnings"].append(
                "nibabel not installed — install with: pip install nibabel"
            )
            # Fall back to minimal magic-byte stub so the file is still recorded
            data["nifti_version"] = self._sniff_version(path)
            return data

        try:
            img = nib.load(str(path), mmap=True)
            hdr = img.header
            data["_nibabel_ok"] = True
        except Exception as exc:
            data["_warnings"].append(f"nibabel.load error: {exc}")
            data["nifti_version"] = self._sniff_version(path)
            return data

        # Shape and voxel sizes
        shape = img.shape          # (x, y, z) or (x, y, z, t, ...)
        ndim = len(shape)
        data["dimensions"] = "x".join(str(s) for s in shape[:3]) if ndim >= 3 else "x".join(str(s) for s in shape)
        if ndim >= 4:
            data["n_volumes"] = shape[3]

        # Voxel sizes in mm (NIfTI stores in mm)
        try:
            zooms = hdr.get_zooms()
            if len(zooms) >= 3:
                vox = [float(zooms[i]) for i in range(3)]
                data["voxel_size_mm"] = vox
                data["voxel_size_um"] = [v * 1000 for v in vox]
            if len(zooms) >= 4 and zooms[3] > 0:
                data["tr_sec"] = float(zooms[3])          # repetition time (s)
        except Exception:
            pass

        # Data type
        try:
            data["dtype"] = str(img.get_data_dtype())
        except Exception:
            pass

        # Intent code
        try:
            intent = int(hdr.get("intent_code", 0))
            data["intent_code"] = intent
            data["intent_name"] = _INTENT_CODES.get(intent, f"unknown_{intent}")
        except Exception:
            pass

        # qform / sform (coordinate system)
        try:
            data["qform_code"] = int(hdr.get("qform_code", 0))
            data["sform_code"] = int(hdr.get("sform_code", 0))
        except Exception:
            pass

        # Description field (free text set by pipeline)
        try:
            desc = hdr.get("descrip", b"").tobytes().decode("utf-8", errors="ignore").strip("\x00").strip()
            if desc:
                data["description"] = desc
        except Exception:
            pass

        # NIfTI version
        try:
            if hasattr(hdr, "sizeof_hdr"):
                data["nifti_version"] = 2 if int(hdr.sizeof_hdr) == 540 else 1
        except Exception:
            data["nifti_version"] = 1

        return data

    # ------------------------------------------------------------------
    # BIDS path structure detection
    # ------------------------------------------------------------------
    def _detect_bids(self, path: Path) -> Dict[str, Any]:
        path_str = str(path)
        parts = [p.lower() for p in path.parts]
        bids: Dict[str, Any] = {}

        # BIDS datatype directories appear as direct parents of files
        for dtype, scan_type in _BIDS_SCAN_TYPE.items():
            if dtype in parts:
                bids["scan_type"] = scan_type
                bids["bids_datatype"] = dtype
                break

        # Subject / session
        sub_m = _BIDS_SUB_RE.search(path_str)
        if sub_m:
            bids["bids_subject"] = sub_m.group(1)
        ses_m = _BIDS_SES_RE.search(path_str)
        if ses_m:
            bids["bids_session"] = ses_m.group(1)

        # Task from filename: sub-01_task-rest_bold.nii.gz → "rest"
        task_m = re.search(r"_task-([^_]+)", path.name, re.IGNORECASE)
        if task_m:
            bids["bids_task"] = task_m.group(1)

        # Run from filename: _run-01_
        run_m = re.search(r"_run-(\d+)", path.name, re.IGNORECASE)
        if run_m:
            bids["bids_run"] = int(run_m.group(1))

        return bids

    # ------------------------------------------------------------------
    # Sidecar JSON (BIDS .json companion file)
    # ------------------------------------------------------------------
    def _read_sidecar(self, path: Path) -> Dict[str, Any]:
        # Resolve the sidecar path: strip .gz then .nii, add .json
        stem = path.name
        if stem.endswith(".nii.gz"):
            stem = stem[:-7]
        elif stem.endswith(".nii"):
            stem = stem[:-4]
        sidecar_path = path.parent / (stem + ".json")
        if not sidecar_path.exists():
            return {}
        try:
            with open(sidecar_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # Normalise the keys we care about
            out: Dict[str, Any] = {}
            for k, v in raw.items():
                out[k] = v
            return out
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Scan type from intent / TR when BIDS path is absent
    # ------------------------------------------------------------------
    def _infer_scan_type(self, hdr: Dict[str, Any]) -> str:
        intent = hdr.get("intent_code", 0)
        if intent == 2001 or hdr.get("n_volumes", 1) > 1:
            return "BOLD_fMRI"
        dims = hdr.get("dimensions", "")
        if hdr.get("n_volumes", 0) > 50:
            return "BOLD_fMRI"
        # Diffusion: TR often long; hard to detect without intent 1003
        return "structural_MRI"

    # ------------------------------------------------------------------
    # Modality string
    # ------------------------------------------------------------------
    def _infer_modality(self, scan_type: str, hdr: Dict[str, Any], sidecar: Dict[str, Any]) -> str:
        modality_map = {
            "BOLD_fMRI":          "fMRI",
            "structural_MRI":     "MRI",
            "diffusion_MRI":      "DTI/DWI",
            "fieldmap":           "MRI_fieldmap",
            "perfusion":          "ASL_perfusion",
            "PET":                "PET",
            "arterial_spin_labeling": "ASL",
        }
        if scan_type in modality_map:
            return modality_map[scan_type]
        # Sidecar override
        modality_from_sidecar = sidecar.get("Modality") or sidecar.get("modality")
        if modality_from_sidecar:
            return str(modality_from_sidecar)
        return "MRI"

    # ------------------------------------------------------------------
    # Assemble properties dict
    # ------------------------------------------------------------------
    def _build_properties(
        self,
        path: Path,
        hdr: Dict[str, Any],
        bids: Dict[str, Any],
        sidecar: Dict[str, Any],
        scan_type: str,
        modality: str,
    ) -> Dict[str, Any]:
        props: Dict[str, Any] = {
            "source_path": str(path),
            "file_name": path.name,
            "modality": modality,
            "scan_type": scan_type,
            "format": "NIfTI",
            "nifti_version": hdr.get("nifti_version"),
        }

        # Dimensions / voxel sizes
        if "dimensions" in hdr:
            props["dimensions"] = hdr["dimensions"]
        if "n_volumes" in hdr:
            props["n_volumes"] = hdr["n_volumes"]
        if "voxel_size_mm" in hdr:
            vox = hdr["voxel_size_mm"]
            props["voxel_size_mm"] = f"{vox[0]:.4f}x{vox[1]:.4f}x{vox[2]:.4f}"
            props["voxel_size_um"] = [v * 1000 for v in vox]
        if "dtype" in hdr:
            props["data_type"] = hdr["dtype"]
        if "intent_name" in hdr and hdr["intent_name"] != "none":
            props["intent"] = hdr["intent_name"]
        if "description" in hdr:
            props["nifti_description"] = hdr["description"]

        # MRI timing from header or sidecar
        tr = hdr.get("tr_sec") or sidecar.get("RepetitionTime")
        if tr:
            props["tr_sec"] = float(tr)
        te = sidecar.get("EchoTime")
        if te:
            props["te_sec"] = float(te)
        ti = sidecar.get("InversionTime")
        if ti:
            props["ti_sec"] = float(ti)
        flip = sidecar.get("FlipAngle")
        if flip:
            props["flip_angle_deg"] = float(flip)

        # Scanner info from sidecar
        for sidecar_key, prop_key in [
            ("Manufacturer",      "manufacturer"),
            ("ManufacturersModelName", "scanner_model"),
            ("MagneticFieldStrength", "field_strength_T"),
            ("InstitutionName",   "institution"),
            ("BodyPartExamined",  "body_part"),
            ("TaskName",          "task_name"),
            ("SliceTiming",       "slice_timing"),
        ]:
            val = sidecar.get(sidecar_key)
            if val is not None:
                props[prop_key] = val

        # BIDS metadata
        for k in ("bids_subject", "bids_session", "bids_task", "bids_run", "bids_datatype"):
            if k in bids:
                props[k] = bids[k]

        return props

    # ------------------------------------------------------------------
    # Provenance edges
    # ------------------------------------------------------------------
    def _build_edges(self, path: Path, context: Optional[dict]) -> List[Dict[str, Any]]:
        file_match = self._file_match(path, context)
        return [
            {
                "type": "DERIVED_FROM",
                "from_label": "ImagingDataset",
                "from_match": {"source_path": str(path)},
                "to_label": "File",
                "to_match": file_match,
            }
        ]

    # ------------------------------------------------------------------
    # Fallback: sniff NIfTI version from magic bytes (no nibabel needed)
    # ------------------------------------------------------------------
    @staticmethod
    def _sniff_version(path: Path) -> Optional[int]:
        """Read the first 4 bytes to detect NIfTI-1 (348) vs NIfTI-2 (540)."""
        try:
            import struct, gzip
            opener = gzip.open if path.name.endswith(".gz") else open
            with opener(str(path), "rb") as f:
                raw = f.read(4)
            (sizeof_hdr,) = struct.unpack("<i", raw)
            if sizeof_hdr == 348:
                return 1
            if sizeof_hdr == 540:
                return 2
        except Exception:
            pass
        return None
