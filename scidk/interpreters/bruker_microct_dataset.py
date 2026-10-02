"""
Bruker MicroCT Complete Dataset Interpreter

Interprets Bruker SkyScan microCT dataset folders in any of the configurations
that appear in practice:

  Config A — Full dataset (raw + reconstruction archived together):
    ScanName/
    ├── ScanName_.log               # raw acquisition log
    ├── ScanName_00000001.tif       # raw projection TIFF stack
    └── ScanName_Rec/               # reconstruction output
        ├── AnyName_rec.log         # reconstruction log (may differ from folder name)
        ├── AnyName_rec00000001.tif # reconstructed TIFF stack
        └── (optional) AnyName_rectmp.log

  Config B — Rec-only (most common in practice; raw never archived or deleted):
    ScanName_Rec/                   # this directory IS the dataset root
    ├── AnyName_rec.log             # reconstruction log (name may differ from folder)
    ├── AnyName_rectmp.log          # optional in-progress temp log (ignored)
    └── AnyName_rec00000001.tif

  Config C — Rec + NIfTI sibling:
    ScanName_Rec/
    ├── AnyName_rec.log
    └── ...
    ScanName_Rec-Nifti/             # or Rec-nii-*, Rec-NIfTI, etc.
    ├── segmentation.nii.gz
    └── img/
        └── predictions/

  Config D — Log-only stub (no TIFFs survived):
    ScanName/
    └── ScanName_.log               # produce minimal node from log metadata only

Key design decisions vs. the original:
  - TIFF stacks are discovered by *.tif glob, not by matching the log stem.
    Log file names frequently differ from their containing folder (e.g.
    wk6-10_Rec/ contains MM010_rec.log).
  - _rectmp.log is explicitly deprioritised; _rec.log is preferred.
  - can_handle() is implemented so the directory dispatcher can route correctly.
  - NIfTI sibling directory is found by pattern matching on the parent, not
    only inside the dataset dir.
  - dataset_id is derived from the directory name, not the log stem, so the
    graph key is stable regardless of log naming.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Bruker SkyScan log key aliases — different firmware versions use different
# names for the same field.
# ---------------------------------------------------------------------------
_VOXEL_KEYS = [
    'Image Pixel Size (um)',
    'Voxel size (um)',
    'Pixel Size (um)',
    'Pixel size (um)',
    'Reconstructed Pixel Size (um)',
]

_DATE_KEYS = [
    'Study Date and Time',
    'Acquisition Date and Time',
    'Date and Time',
    'Scan date',
]

_SCANNER_KEYS = [
    'Scanner',
    'System',
    'Device',
]

_INSTRUMENT_PARAM_MAP = {
    'Source Voltage (kV)':   'voltage_kv',
    'Source Current (uA)':   'current_ua',
    'Exposure (ms)':         'exposure_ms',
    'Rotation Step (deg)':   'rotation_step_deg',
    'Camera Pixel Size (um)': 'camera_pixel_size_um',
    'Filter':                'filter',
    'Reconstruction Program': 'reconstruction_software',
    'Number Of Rows':        '_rows',       # used for dimensions, not stored directly
    'Number Of Columns':     '_cols',
    'Depth (bits)':          'bit_depth',
}


class BrukerMicroCtDatasetInterpreter:
    """
    Composite interpreter for Bruker SkyScan microCT dataset folders.

    Triggered at directory level by the enrichment dispatcher when can_handle()
    returns True. Produces ImagingDataset, InstrumentRecord, and FileSet nodes.
    """

    id = "bruker_microct_dataset"
    name = "Bruker MicroCT Dataset"
    version = "2.0.0"
    dispatch = "directory"
    extensions = []          # directory-dispatch; no extension matching
    default_enabled = True

    # ------------------------------------------------------------------
    # can_handle  — called by the enrichment dispatcher
    # ------------------------------------------------------------------
    def can_handle(self, path: Path, context: Optional[dict] = None) -> bool:
        """
        True for any directory that looks like a Bruker microCT dataset.

        Matches:
          - Directories whose name ends in _Rec, _rec, Rec (Config B, most common)
          - Directories containing a *.log file that is NOT itself a _rec.log
            (Config A full dataset root)
          - Directories containing a *_rec.log (rec-only root without _Rec suffix)
        """
        try:
            if not path.is_dir():
                return False
            name = path.name
            # Config B: folder name ends in _Rec / _rec / Rec
            if name.endswith('_Rec') or name.endswith('_rec') or name == 'Rec':
                return True
            # Config A / D: folder contains a raw acquisition log
            acq_logs = [
                f for f in path.glob('*.log')
                if not f.stem.endswith('_rec') and not f.stem.endswith('_rectmp')
            ]
            if acq_logs:
                return True
            # Also match if the folder contains a _rec.log directly (unusual layout)
            rec_logs = list(path.glob('*_rec.log'))
            if rec_logs:
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # interpret
    # ------------------------------------------------------------------
    def interpret(self, file_path: Path, context: Optional[dict] = None) -> Dict[str, Any]:
        """
        Interpret a Bruker microCT dataset directory.

        file_path may be:
          - The dataset root (Config A/D): contains raw .log + optional TIFFs
          - A *_Rec directory (Config B): contains *_rec.log + recon TIFFs
          - A .log file: parent is treated as dataset root (legacy call path)
        """
        try:
            # --- Resolve directory and log file(s) ---
            if file_path.is_file() and file_path.suffix == '.log':
                dataset_dir = file_path.parent
            elif file_path.is_dir():
                dataset_dir = file_path
            else:
                return self._error(f'Path must be a directory or .log file: {file_path}')

            is_rec_dir = (
                dataset_dir.name.endswith('_Rec') or
                dataset_dir.name.endswith('_rec') or
                dataset_dir.name == 'Rec'
            )

            # Stable dataset id from directory name (not log stem — they may differ)
            dataset_id = dataset_dir.name
            dataset_path = str(dataset_dir.resolve())

            nodes: List[Dict[str, Any]] = []
            relationships: List[Dict[str, Any]] = []

            # ----------------------------------------------------------
            # 1. Find and parse log files
            # ----------------------------------------------------------
            acq_log, rec_log = self._find_logs(dataset_dir, is_rec_dir)

            # Primary metadata comes from whichever log we have
            # rec_log preferred for reconstruction metadata; acq_log for raw params
            primary_meta = self._parse_log_file(rec_log or acq_log) if (rec_log or acq_log) else {}

            # ----------------------------------------------------------
            # 2. ImagingDataset node
            # ----------------------------------------------------------
            imaging_props: Dict[str, Any] = {
                'path': dataset_path,
                'dataset_id': dataset_id,
                'modality': 'microCT',
                'instrument_vendor': 'Bruker',
                'dataset_config': 'rec_only' if is_rec_dir else 'full',
            }

            voxel = self._first_value(primary_meta, _VOXEL_KEYS)
            if voxel is not None:
                imaging_props['voxel_size_um'] = self._to_float(voxel)

            acq_date = self._first_value(primary_meta, _DATE_KEYS)
            if acq_date:
                imaging_props['acquisition_date'] = acq_date

            scanner = self._first_value(primary_meta, _SCANNER_KEYS)
            if scanner:
                imaging_props['instrument'] = scanner

            nodes.append({
                'label': 'ImagingDataset',
                'key_property': 'path',
                'properties': imaging_props,
            })

            # ----------------------------------------------------------
            # 3. InstrumentRecord node (from whichever log has the params)
            # ----------------------------------------------------------
            log_for_instrument = acq_log or rec_log
            if log_for_instrument and primary_meta:
                instrument_props: Dict[str, Any] = {
                    'source_file': str(log_for_instrument.resolve()),
                    'instrument_type': 'Bruker SkyScan microCT',
                }
                rows = cols = None
                for log_key, prop_name in _INSTRUMENT_PARAM_MAP.items():
                    val = primary_meta.get(log_key)
                    if val is None:
                        continue
                    if prop_name == '_rows':
                        rows = self._to_int(val)
                    elif prop_name == '_cols':
                        cols = self._to_int(val)
                    elif log_key == 'Filter' or log_key == 'Reconstruction Program':
                        instrument_props[prop_name] = val
                    else:
                        instrument_props[prop_name] = self._to_float(val)

                if rows and cols:
                    instrument_props['sensor_dimensions'] = f'{cols}x{rows}'

                nodes.append({
                    'label': 'InstrumentRecord',
                    'key_property': 'source_file',
                    'properties': instrument_props,
                })
                relationships.append({
                    'type': 'METADATA_SOURCE',
                    'from_label': 'ImagingDataset',
                    'from_match': {'path': dataset_path},
                    'to_label': 'InstrumentRecord',
                    'to_match': {'source_file': str(log_for_instrument.resolve())},
                })

            # ----------------------------------------------------------
            # 4. Raw TIFF stack (Config A only — not present in rec-only)
            # ----------------------------------------------------------
            raw_tiff_count = 0
            if not is_rec_dir:
                raw_tiffs = sorted(f for f in dataset_dir.glob('*.tif')
                                   if f.is_file())
                raw_tiff_count = len(raw_tiffs)
                if raw_tiffs:
                    raw_props: Dict[str, Any] = {
                        'id': f'{dataset_id}_raw',
                        'stage': 'raw',
                        'file_count': raw_tiff_count,
                        'format': 'TIFF',
                        'pattern': '*.tif',
                        'path': dataset_path,
                        'first_file': raw_tiffs[0].name,
                        'last_file': raw_tiffs[-1].name,
                    }
                    if primary_meta.get('Number Of Rows') and primary_meta.get('Number Of Columns'):
                        r = self._to_int(primary_meta['Number Of Rows'])
                        c = self._to_int(primary_meta['Number Of Columns'])
                        if r and c:
                            raw_props['dimensions'] = f'{c}x{r}'
                    if primary_meta.get('Depth (bits)'):
                        raw_props['bit_depth'] = self._to_int(primary_meta['Depth (bits)'])

                    nodes.append({
                        'label': 'FileSet',
                        'key_property': 'id',
                        'properties': raw_props,
                    })
                    relationships.append({
                        'type': 'RAW_DATA',
                        'from_label': 'ImagingDataset',
                        'from_match': {'path': dataset_path},
                        'to_label': 'FileSet',
                        'to_match': {'id': f'{dataset_id}_raw'},
                    })

            # ----------------------------------------------------------
            # 5. Reconstructed TIFF stack
            #    - Config B: TIFFs are in dataset_dir itself
            #    - Config A: TIFFs are in a *_Rec subdirectory
            # ----------------------------------------------------------
            rec_tiff_count = 0
            if is_rec_dir:
                rec_tiff_dir = dataset_dir
            else:
                rec_tiff_dir = self._find_rec_subdir(dataset_dir)

            if rec_tiff_dir:
                rec_tiffs = sorted(f for f in rec_tiff_dir.glob('*.tif')
                                   if f.is_file())
                rec_tiff_count = len(rec_tiffs)
                if rec_tiffs:
                    rec_props: Dict[str, Any] = {
                        'id': f'{dataset_id}_reconstructed',
                        'stage': 'reconstructed',
                        'file_count': rec_tiff_count,
                        'format': 'TIFF',
                        'pattern': '*.tif',
                        'path': str(rec_tiff_dir.resolve()),
                        'first_file': rec_tiffs[0].name,
                        'last_file': rec_tiffs[-1].name,
                    }
                    nodes.append({
                        'label': 'FileSet',
                        'key_property': 'id',
                        'properties': rec_props,
                    })
                    relationships.append({
                        'type': 'RECONSTRUCTED',
                        'from_label': 'ImagingDataset',
                        'from_match': {'path': dataset_path},
                        'to_label': 'FileSet',
                        'to_match': {'id': f'{dataset_id}_reconstructed'},
                    })

            # ----------------------------------------------------------
            # 6. NIfTI / analysis outputs
            #    Look for sibling directories matching *Rec-Nifti*, *Rec-nii*,
            #    *Rec-NIfTI*, etc., as well as a nested img/predictions/ tree.
            # ----------------------------------------------------------
            nifti_count = 0
            nifti_dir = self._find_nifti_dir(dataset_dir, is_rec_dir)
            if nifti_dir:
                nifti_files = (
                    list(nifti_dir.rglob('*.nii')) +
                    list(nifti_dir.rglob('*.nii.gz'))
                )
                nifti_count = len(nifti_files)
                if nifti_files:
                    analysis_props: Dict[str, Any] = {
                        'id': f'{dataset_id}_analysis',
                        'stage': 'analysis',
                        'file_count': nifti_count,
                        'format': 'NIfTI',
                        'path': str(nifti_dir.resolve()),
                        'files': [f.name for f in sorted(nifti_files)],
                    }
                    nodes.append({
                        'label': 'FileSet',
                        'key_property': 'id',
                        'properties': analysis_props,
                    })
                    relationships.append({
                        'type': 'ANALYSIS',
                        'from_label': 'ImagingDataset',
                        'from_match': {'path': dataset_path},
                        'to_label': 'FileSet',
                        'to_match': {'id': f'{dataset_id}_analysis'},
                    })

            # ----------------------------------------------------------
            # 7. Summary data
            # ----------------------------------------------------------
            data: Dict[str, Any] = {
                'dataset_id': dataset_id,
                'dataset_path': dataset_path,
                'dataset_config': imaging_props['dataset_config'],
                'voxel_size_um': imaging_props.get('voxel_size_um'),
                'acquisition_date': imaging_props.get('acquisition_date'),
                'stages': {
                    'raw': raw_tiff_count,
                    'reconstructed': rec_tiff_count,
                    'analysis': nifti_count,
                },
                'total_files': raw_tiff_count + rec_tiff_count + nifti_count,
                'node_count': len(nodes),
                'relationship_count': len(relationships),
                'logs_found': {
                    'acquisition': str(acq_log) if acq_log else None,
                    'reconstruction': str(rec_log) if rec_log else None,
                },
            }

            return {
                'status': 'success',
                'data': data,
                'nodes': nodes,
                'relationships': relationships,
            }

        except Exception as exc:
            return self._error(f'{type(exc).__name__}: {exc}')

    # ------------------------------------------------------------------
    # Log discovery
    # ------------------------------------------------------------------
    def _find_logs(
        self, directory: Path, is_rec_dir: bool
    ) -> tuple[Optional[Path], Optional[Path]]:
        """
        Return (acq_log, rec_log) for a dataset directory.

        Rules:
          - *_rec.log   → reconstruction log
          - *_rectmp.log → ignored (in-progress temp file)
          - anything else → acquisition log
          - If this IS a _Rec dir, all .log files are reconstruction logs;
            there is no acquisition log here (it's in the parent, if at all).
        """
        all_logs = list(directory.glob('*.log'))
        rec_logs = [f for f in all_logs if f.stem.endswith('_rec')]
        tmp_logs = {f for f in all_logs if f.stem.endswith('_rectmp')}
        acq_logs = [f for f in all_logs
                    if f not in rec_logs and f not in tmp_logs]

        rec_log = rec_logs[0] if rec_logs else None
        acq_log = None if is_rec_dir else (acq_logs[0] if acq_logs else None)

        # If we're in a rec dir and found no *_rec.log, fall back to any log
        # (some exports omit the _rec suffix)
        if is_rec_dir and rec_log is None:
            non_tmp = [f for f in all_logs if f not in tmp_logs]
            rec_log = non_tmp[0] if non_tmp else None

        return acq_log, rec_log

    # ------------------------------------------------------------------
    # Subdirectory discovery
    # ------------------------------------------------------------------
    def _find_rec_subdir(self, dataset_dir: Path) -> Optional[Path]:
        """Find the *_Rec reconstruction subdirectory inside a full dataset dir."""
        for child in dataset_dir.iterdir():
            if not child.is_dir():
                continue
            n = child.name
            if n.endswith('_Rec') or n.endswith('_rec') or n == 'Rec':
                return child
        return None

    def _find_nifti_dir(self, dataset_dir: Path, is_rec_dir: bool) -> Optional[Path]:
        """
        Find the NIfTI output directory.

        Search order:
          1. Sibling of dataset_dir matching *Rec-Nifti*, *Rec-nii*, *Rec-NIfTI*
             (Config B/C: the _Rec-Nifti dir sits next to the _Rec dir)
          2. Subdirectory of dataset_dir matching same patterns
          3. Subdirectory named 'img' (some pipelines drop NIfTIs there)
        """
        search_root = dataset_dir.parent if is_rec_dir else dataset_dir
        stem = dataset_dir.name  # e.g. "wk6-10_Rec" → look for "wk6-10_Rec-Nifti"

        # Sibling search (most common for Config B)
        _nifti_suffixes = ('-Nifti', '-nii', '-NIfTI', '-Nifti', '_Nifti',
                           '-nifti', '_nifti', '-NII', '_NII')
        for suffix in _nifti_suffixes:
            candidate = search_root / (stem + suffix)
            if candidate.is_dir():
                return candidate
            # Also try wildcard: stem without _Rec + suffix
            base = stem[:-4] if stem.endswith('_Rec') else stem
            candidate2 = search_root / (base + suffix)
            if candidate2.is_dir():
                return candidate2

        # Subdirectory search
        for child in dataset_dir.iterdir():
            if not child.is_dir():
                continue
            cn = child.name.lower()
            if 'nifti' in cn or 'nii' in cn:
                return child
            if cn == 'img':
                return child

        return None

    # ------------------------------------------------------------------
    # Log parsing
    # ------------------------------------------------------------------
    def _parse_log_file(self, log_path: Path) -> Dict[str, str]:
        """Parse Bruker SkyScan log file (INI-style key=value, section headers ignored)."""
        parsed: Dict[str, str] = {}
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('['):
                        continue
                    if '=' in line:
                        key, _, value = line.partition('=')
                    elif '\t' in line:
                        key, _, value = line.partition('\t')
                    else:
                        continue
                    parsed[key.strip()] = value.strip()
        except Exception:
            pass
        return parsed

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _first_value(meta: Dict[str, str], keys: List[str]) -> Optional[str]:
        """Return the first non-empty value found for any of the given keys."""
        for k in keys:
            v = meta.get(k)
            if v:
                return v
        return None

    @staticmethod
    def _to_float(value: Any) -> Any:
        try:
            return float(value)
        except (ValueError, TypeError):
            return value

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _error(msg: str) -> Dict[str, Any]:
        return {'status': 'error', 'data': {'error': msg}}
