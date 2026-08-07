"""Format-recognition tables shared by the scanners and the SciDK package.

Data only — no logic. ``tools/scidk_scanner.py`` and
``tools/scidk_scanner_opt.py`` each held their own copy of these three tables,
which meant every new interpreter had to be added twice and the two drifted in
practice. Both now import from here, with an inline fallback for running a
scanner on a machine that has the script but not the installed package.

The scanners are the only consumers today, but these belong in the package
rather than in ``tools/``: they describe what SciDK can interpret, which is a
property of the interpreters, not of the walker.
"""
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────
# Known interpreter coverage (SciDK built-ins)
# Update this list as new interpreters are added
# ─────────────────────────────────────────────
# Values must match the `id` class attribute of an interpreter in
# scidk/interpreters/, as listed in scidk/interpreters/__init__.py:INTERPRETERS.
# Print the current ids and the extensions they really claim with:
#     python -c "from scidk.interpreters import INTERPRETERS; \
#                [print(i.id, i.extensions) for i in INTERPRETERS]"
# A value that matches no registry id is written into files.interpreted_as and
# then resolves to nothing downstream — a silent no-op, not an error.
#
# None means "no interpreter reads this": the extension is recognised, so magic
# sniffing is skipped, but the file is counted as a gap rather than as covered.
KNOWN_INTERPRETERS: Dict[str, Optional[str]] = {
    # extension (lowercase, with dot) → interpreter id
    ".csv":      "csv",
    ".tsv":      "csv",              # over-claim: CsvInterpreter.extensions is ['.csv']
    ".xlsx":     "xlsx",
    ".xls":      "xlsx",             # over-claim: XlsxInterpreter is ['.xlsx', '.xlsm']
    ".json":     "json",
    ".jsonl":    "json",             # over-claim: JsonInterpreter is ['.json']
    ".yaml":     "yaml",
    ".yml":      "yaml",
    ".ipynb":    "ipynb",
    ".dcm":      "dicom_bioformats",
    ".dicom":    "dicom_bioformats",
    ".tif":      "ome_tiff",         # over-claim: OMETiffInterpreter is ['.ome.tif', '.ome.tiff']
    ".tiff":     "ome_tiff",         # over-claim: as above
    ".h5":       None,               # hdf5_interpreter: specced, not yet implemented
    ".hdf5":     None,               # hdf5_interpreter: specced, not yet implemented
    ".nc":       None,               # netcdf_interpreter: specced, not yet implemented
    ".nc4":      None,               # netcdf_interpreter: specced, not yet implemented
    ".rdf":      None,               # rdf_interpreter: specced, not yet implemented
    ".ttl":      None,               # rdf_interpreter: specced, not yet implemented
    ".owl":      None,               # owl_interpreter: specced, not yet implemented
    ".py":       "python_code",
    # Add entries here as new interpreters land in scidk/interpreters/
    # Registered but unlisted here: txt (.txt), bruker_skyscan_log (.log).
}

# ─────────────────────────────────────────────
# Magic byte signatures for format identification
# Used when extension is ambiguous or missing
# ─────────────────────────────────────────────
MAGIC_SIGNATURES: List[Tuple[bytes, str, Optional[str]]] = [
    # (prefix_bytes, format_label, interpreter_hint)
    # A None hint means the format is identifiable but no interpreter reads it.
    (b"\x89HDF",           "hdf5",        None),  # hdf5_interpreter not implemented
    (b"CDF\x01",           "netcdf3",     None),  # netcdf_interpreter not implemented
    (b"CDF\x02",           "netcdf3_64",  None),  # netcdf_interpreter not implemented
    (b"\x89PNG",           "png",         None),
    (b"\xff\xd8\xff",      "jpeg",        None),
    (b"GIF8",              "gif",         None),
    (b"II\x2a\x00",        "tiff_le",     "ome_tiff"),
    (b"MM\x00\x2a",        "tiff_be",     "ome_tiff"),
    (b"DICM",              "dicom",       "dicom_bioformats"),        # offset 128
    (b"PK\x03\x04",        "zip_based",   None),                      # xlsx, docx, jar…
    (b"%PDF",              "pdf",         None),
    (b"{\n",               "json_likely", "json"),
    (b"{\"",               "json_likely", "json"),
    (b"[\n",               "json_likely", "json"),
    (b"[{",                "json_likely", "json"),
    (b"@HD\t",             "sam",         None),
    (b"BAM\x01",           "bam",         None),
    (b"##fileformat=VCF",  "vcf",         None),
    (b"@SQUAWK",           "fastq_likely",None),
    (b"BZh",               "bz2",         None),
    (b"\x1f\x8b",          "gzip",        None),
    (b"FCS3.",             "fcs",         None),                       # flow cytometry
    (b"FCS2.",             "fcs",         None),
    (b"\x89\x48\x44\x46",  "hdf5",        None),  # hdf5_interpreter not implemented
    (b"SIMPLE  =",         "fits",        None),                       # FITS astronomy/bio
    (b"#\n# ",             "r_data",      None),
]

# Directory structure patterns → instrument/pipeline recognition
DIRECTORY_PATTERNS: List[Tuple[List[str], str]] = [
    # (required_filenames_in_dir, pattern_label)
    (["barcodes.tsv", "features.tsv", "matrix.mtx"],  "10x_genomics_mtx"),
    (["barcodes.tsv.gz", "features.tsv.gz", "matrix.mtx.gz"], "10x_genomics_mtx_gz"),
    (["proteinGroups.txt", "peptides.txt"],            "maxquant_output"),
    (["summary.txt", "Parameters.txt"],                "maxquant_run"),
    (["acqp", "method", "fid"],                        "bruker_mri"),
    (["acqp", "method", "ser"],                        "bruker_mri"),
    (["2dseq"],                                        "bruker_processed"),
    (["OME", "metadata.xml"],                          "ome_tiff_dir"),
    (["DICOMDIR"],                                     "dicom_dir"),
    (["subject", "ses-", "anat"],                      "bids_dataset"),   # partial match
    (["dataset_description.json", "participants.tsv"], "bids_root"),
    (["Manifest.xml"],                                 "tcga_manifest"),
    (["clinical_data.txt", "mutations.txt"],           "tcga_export"),
]

# Directory pattern → the interpreter id written to the folder row's
# interpreted_as. A matched pattern used to go only into the folder's
# extra_json, where nothing downstream looks, so a directory-level interpreter
# had no trigger path at all.
#
# Most values below name interpreters that do not exist yet, which is
# deliberate: the pattern is what the scanner can actually detect, and the id
# records what would read it. Unlike KNOWN_INTERPRETERS, an unresolvable value
# here costs nothing today because no directory dispatch consumes it — but the
# same rule applies once one does, so keep these in step with the registry as
# the interpreters land. A pattern with no entry falls back to its own name.
#
# bruker_microct_dataset is the one registered directory-capable interpreter
# (extensions = [], triggered by structure), and no pattern currently detects
# the Bruker SkyScan layout it wants; adding one is a separate change.
DIRECTORY_PATTERN_INTERPRETERS: Dict[str, Optional[str]] = {
    "10x_genomics_mtx":      "mtx_interpreter",        # not yet implemented
    "10x_genomics_mtx_gz":   "mtx_interpreter",        # not yet implemented
    "maxquant_output":       "maxquant_interpreter",   # not yet implemented
    "maxquant_run":          "maxquant_interpreter",   # not yet implemented
    "bruker_mri":            "bruker_mri_interpreter", # not yet implemented
    "bruker_processed":      "bruker_mri_interpreter", # not yet implemented
    "ome_tiff_dir":          "ome_tiff",               # registered
    "dicom_dir":             "dicom_bioformats",       # registered
    "bids_dataset":          "bids_interpreter",       # not yet implemented
    "bids_root":             "bids_interpreter",       # not yet implemented
    "tcga_manifest":         "tcga_interpreter",       # not yet implemented
    "tcga_export":           "tcga_interpreter",       # not yet implemented
}


def interpreter_for_dir_pattern(pattern: Optional[str]) -> Optional[str]:
    """Interpreter id for a matched directory pattern, or the pattern itself.

    Falling back to the pattern name keeps a newly added DIRECTORY_PATTERNS
    entry visible in interpreted_as without also requiring a mapping entry.
    """
    if not pattern:
        return None
    return DIRECTORY_PATTERN_INTERPRETERS.get(pattern, pattern)
