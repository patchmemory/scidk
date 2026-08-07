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
