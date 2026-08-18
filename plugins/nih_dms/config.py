"""Configuration for the NIH DMS plan generator.

Everything the generator would otherwise hardcode lives here: which property
names count as PHI, which properties are worth reading as an assay or imaging
modality, which file formats map to which community standard, and the prose for
each sharing mode. Adjusting the plan for a new instrument or a new format is a
change to a table in this file, not to the code that walks the graph.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

# --------------------------------------------------------------- settings keys
#
# Read from ``scidk_settings.db`` via ``scidk.core.settings``. All optional: an
# unset key becomes a visible placeholder in the draft rather than a silent
# default, because a DMS plan that quietly names the wrong repository is worse
# than one that says "fill this in".

SETTING_PREFIX = 'publication.dms.'
SETTING_REPOSITORY = SETTING_PREFIX + 'repository'
SETTING_RETENTION_YEARS = SETTING_PREFIX + 'retention_years'
SETTING_SHARING_MODE = SETTING_PREFIX + 'sharing_mode'
SETTING_ACCESS_CONTACT = SETTING_PREFIX + 'access_contact'

#: Shown where a value has not been configured. Bracketed and upper-case so it
#: survives a copy into DMPTool and is impossible to miss on review. The token is
#: only the name — no explanatory text inside the brackets, so a reviewer can
#: find-and-replace ``[REPOSITORY_NAME]`` in one pass. What is missing and where
#: to set it is said in the prose around the placeholder instead.
REPOSITORY_PLACEHOLDER = '[REPOSITORY_NAME]'
RETENTION_PLACEHOLDER = '[RETENTION_PERIOD]'
CONTACT_PLACEHOLDER = '[DATA_ACCESS_CONTACT]'


# ------------------------------------------------------------ PHI detection
#
# Property names that indicate identifiable human-subject data. Compared on a
# canonical form (lower-cased, separators removed), so ``patient_id``,
# ``patientID`` and ``Patient Id`` all match the one entry. Add to this tuple to
# widen detection — `dob`, `ssn` and site-specific identifiers are the usual
# additions.

PHI_PROPERTY_NAMES: Tuple[str, ...] = (
    'patient_id',
    'subject_name',
    'patient_name',
    'mrn',
    'date_of_birth',
    'dob',
)


# ------------------------------------------------- modality / assay discovery
#
# Property names read as "what kind of measurement is this". The generator looks
# for these across every label in the graph and reports their distinct values, so
# the Standards section describes the modalities actually present rather than a
# guess.

MODALITY_PROPERTIES: Tuple[str, ...] = (
    'modality',
    'imaging_modality',
    'assay',
    'assay_type',
    'assay_title',
    # AIPT records the assay and the bench protocol on the DERIVED_FROM edge
    # between a Sample and its parent, not on a node — which is why modality
    # discovery reads relationship properties as well as node properties. On the
    # live graph these are the only properties that name a modality at all.
    'internal_assay_title',
    'protocol_title',
    'platform',
    'sequencing_platform',
    'instrument',
    'stain',
    'antibody',
    # Named here because the Standards section asks for "file_format / format"
    # explicitly; where a graph carries them they beat inferring from extensions.
    'file_format',
    'format',
)

#: Properties that describe *what kind of collection* a node is, scoped by label
#: so a name as generic as ``type`` is only read where it means something. On the
#: live AIPT graph ``Dataset.type`` holds ImageSequence / TIFFCollection /
#: CSVCollection, which is a Standards-relevant statement about structure.
COLLECTION_PROFILE_PROPERTIES: Dict[str, Tuple[str, ...]] = {
    'Dataset': ('type', 'profile'),
}


# ------------------------------------------------------- format -> standard
#
# Extension to (format name, the community standard that governs it). Where a
# vendor format has an open archival counterpart, the standard column says so —
# that is exactly the sentence a DMS reviewer is looking for.

FORMAT_STANDARDS: Dict[str, Tuple[str, str]] = {
    '.dcm': ('DICOM', 'DICOM (NEMA PS3 / ISO 12052)'),
    '.dicom': ('DICOM', 'DICOM (NEMA PS3 / ISO 12052)'),
    '.svs': ('Aperio whole-slide image', 'vendor format; OME-TIFF for archival release'),
    '.ndpi': ('Hamamatsu whole-slide image', 'vendor format; OME-TIFF for archival release'),
    '.scn': ('Leica whole-slide image', 'vendor format; OME-TIFF for archival release'),
    '.mrxs': ('3DHISTECH whole-slide image', 'vendor format; OME-TIFF for archival release'),
    '.czi': ('Zeiss microscopy image', 'vendor format; OME-TIFF for archival release'),
    '.lif': ('Leica microscopy image', 'vendor format; OME-TIFF for archival release'),
    '.nd2': ('Nikon microscopy image', 'vendor format; OME-TIFF for archival release'),
    '.tif': ('TIFF', 'TIFF 6.0; OME-TIFF where image metadata is required'),
    '.tiff': ('TIFF', 'TIFF 6.0; OME-TIFF where image metadata is required'),
    '.zarr': ('Zarr array', 'OME-NGFF (OME-Zarr)'),
    '.nii': ('NIfTI', 'NIfTI-1/2 (NITRC)'),
    '.gz': ('gzip-compressed', 'compression only; standard follows the inner format'),
    '.fastq': ('FASTQ', 'FASTQ (Cock et al. 2010)'),
    '.fq': ('FASTQ', 'FASTQ (Cock et al. 2010)'),
    '.bam': ('BAM', 'SAM/BAM/CRAM (GA4GH)'),
    '.cram': ('CRAM', 'SAM/BAM/CRAM (GA4GH)'),
    '.sam': ('SAM', 'SAM/BAM/CRAM (GA4GH)'),
    '.vcf': ('VCF', 'VCF (GA4GH)'),
    '.bed': ('BED', 'BED (UCSC)'),
    '.fcs': ('Flow cytometry data', 'FCS 3.1 (ISAC)'),
    '.mzml': ('Mass spectrometry data', 'mzML (HUPO-PSI)'),
    '.imzml': ('Imaging mass spectrometry data', 'imzML (HUPO-PSI)'),
    '.h5': ('HDF5', 'HDF5 (The HDF Group)'),
    '.hdf5': ('HDF5', 'HDF5 (The HDF Group)'),
    '.h5ad': ('AnnData', 'AnnData / HDF5'),
    '.csv': ('Delimited text', 'CSV on the Web (W3C); RFC 4180'),
    '.tsv': ('Delimited text', 'CSV on the Web (W3C); RFC 4180'),
    '.xlsx': ('Excel workbook', 'OOXML; export to CSV for archival release'),
    '.xls': ('Excel workbook', 'legacy binary; export to CSV for archival release'),
    '.json': ('JSON', 'RFC 8259'),
    '.jsonld': ('JSON-LD', 'JSON-LD 1.1 (W3C)'),
    '.xml': ('XML', 'XML 1.0 (W3C)'),
    '.pdf': ('PDF', 'PDF/A (ISO 19005) for archival release'),
    '.png': ('PNG', 'PNG (ISO 15948)'),
    '.jpg': ('JPEG', 'JPEG (ISO 10918)'),
    '.jpeg': ('JPEG', 'JPEG (ISO 10918)'),
    '.bmp': ('Windows bitmap', 'uncompressed bitmap; convert to OME-TIFF or PNG for release'),
    '.txt': ('Plain text', 'UTF-8 plain text'),
    '.md': ('Markdown', 'CommonMark'),
    '.py': ('Python source', 'analysis code; version-controlled'),
    '.r': ('R source', 'analysis code; version-controlled'),
    '.m': ('MATLAB source', 'analysis code; version-controlled'),
    '.ipynb': ('Jupyter notebook', 'nbformat; analysis code'),
    # Office and AV formats. Present in volume on the live graph as protocols,
    # result summaries and microscope session recordings, so the plan has to say
    # something about them rather than leave them unclassified.
    '.docx': ('Word document', 'OOXML; PDF/A for archival release'),
    '.doc': ('Word document', 'legacy binary; PDF/A for archival release'),
    '.pptx': ('PowerPoint presentation', 'OOXML; PDF/A for archival release'),
    '.mp4': ('MPEG-4 video', 'ISO/IEC 14496-14 (H.264/AAC)'),
    '.avi': ('AVI video', 'legacy container; transcode to MP4 for release'),
    '.zip': ('ZIP archive', 'container only; standard follows the contents'),
    # Instrument-written sidecars seen on the live graph. Named as vendor output
    # rather than guessed at, because a DMS reviewer reading "unclassified" for
    # 24,000 files will ask, and "vendor sidecar" is the true answer.
    '.vxml': ('Vendor XML sidecar', 'instrument-written metadata; XML 1.0'),
    '.mxml': ('Vendor XML sidecar', 'instrument-written metadata; XML 1.0'),
    '.pimg': ('Vendor image container', 'vendor format; OME-TIFF for archival release'),
    '.bimg': ('Vendor image container', 'vendor format; OME-TIFF for archival release'),
    '.3img': ('Vendor image container', 'vendor format; OME-TIFF for archival release'),
    '.paimg': ('Vendor image container', 'vendor format; OME-TIFF for archival release'),
    # Analysis intermediates. Called out as intermediates rather than data,
    # because a DMS reviewer treats "we will share our pickles" as a red flag —
    # these formats are not readable without the code that wrote them.
    '.mat': ('MATLAB data file', 'MAT-file v7.3 is HDF5-based; export to HDF5 or CSV for release'),
    '.b2nd': ('Blosc2 n-dimensional array', 'compressed array; export to HDF5 or Zarr for release'),
    '.pkl': ('Python pickle', 'not an archival format — version-specific and unsafe to load; '
                              'export to CSV, Parquet or HDF5 for release'),
    '.ijm': ('ImageJ macro', 'analysis code; version-controlled'),
    # Housekeeping. Named so that a reviewer sees they were considered and are not
    # scientific data, rather than seeing thousands of unexplained files.
    '.log': ('Instrument or process log', 'operational record; not scientific data'),
    '.bak': ('Backup copy', 'operational copy; excluded from release'),
    '.jar': ('Java archive', 'bundled software, not data; cite the tool and version instead'),
}

#: What the metadata itself conforms to. SciDK packages metadata as RO-Crate
#: (see ``scidk/rocrate_bridge.py``), which is a concrete answer to the "what
#: metadata standard" question the Standards section has to give.
METADATA_STANDARDS: Tuple[str, ...] = (
    'RO-Crate 1.1 (research object packaging, exported directly from SciDK)',
    'schema.org vocabulary for entity descriptions within each crate',
)


# ----------------------------------------------------------- sharing modes
#
# Keyed by the value of the ``publication.dms.sharing_mode`` setting. Prose is
# draft text for a human to edit, not a submission.

SHARING_MODES: Dict[str, str] = {
    'open': (
        'Data will be shared without access restrictions. De-identified data and '
        'accompanying metadata will be deposited in {repository} and made openly '
        'downloadable under a documented licence, with no registration or data use '
        'agreement required.'
    ),
    'controlled_access': (
        'Data will be shared through controlled access. De-identified data and '
        'accompanying metadata will be deposited in {repository}; requests will be '
        'reviewed by a Data Access Committee against the consent terms under which the '
        'data were collected, and approved requesters will execute a Data Use Agreement '
        'before transfer.'
    ),
    'registered_access': (
        'Data will be shared under registered access. De-identified data and metadata '
        'will be deposited in {repository}, and access will be granted to '
        'bona fide researchers who register and agree to documented terms of use.'
    ),
    'metadata_only': (
        'Metadata will be shared openly and the underlying data will be made available '
        'on request. A metadata-only record describing the collection will be published '
        'in {repository}; requests for the data themselves will be handled by '
        '{contact} under a Data Use Agreement.'
    ),
    'not_shared': (
        'Some data in this collection are not suitable for sharing. The justification '
        'for each exception, and the metadata that will be shared in its place, are '
        'described below. [EXPLAIN THE LIMITATION AND THE LEGAL OR CONSENT BASIS FOR IT.]'
    ),
}

#: Offered to the user when no mode is set, and listed in the draft so the choice
#: is visible rather than buried in a settings page.
SHARING_MODE_LABELS: Dict[str, str] = {
    'open': 'Open access',
    'controlled_access': 'Controlled access (Data Access Committee + DUA)',
    'registered_access': 'Registered access',
    'metadata_only': 'Metadata only, data on request',
    'not_shared': 'Not shared (justification required)',
}


# ----------------------------------------------------------------- limits
#
# Label counts are exact and nearly free: they come from Neo4j's count store via
# ``MATCH (n:Label) RETURN count(n)``, which reads a counter rather than the
# nodes.
#
# The format breakdown aggregates every :File node, which is a real scan. On the
# 5.1M-file AIPT graph that is ~4s — worth paying, because the alternative was
# tried and is misleading: a ``LIMIT 200000`` prefix of that graph reports .dcm
# as the second-commonest format and misses .bmp (897k files) and .nii (800 GB of
# NIfTI) entirely, because store order is not sample order. A plan is not allowed
# to be wrong about what data the lab holds.
#
# ``FILE_SAMPLE_LIMIT`` is therefore an opt-in escape hatch, not the default
# path: a deployment where the exact scan is too slow can pass ``sample_limit``
# to trade accuracy for latency, and the generated plan says in the text that it
# did so and that the result is a store-order prefix.

FILE_SAMPLE_LIMIT = 200_000
MAX_LABELS = 200
MAX_FORMATS = 30
DISTINCT_VALUE_LIMIT = 25
MAX_MODALITY_QUERIES = 12

#: NIH expects data to remain available for a defined period; this is only the
#: fallback shown when the setting is unset and the caller passed nothing.
DEFAULT_RETENTION_YEARS: Optional[int] = None


def canonical_property(name: str) -> str:
    """Fold a property name for comparison: lower-case, separators removed.

    ``Patient_ID``, ``patientId`` and ``patient id`` all canonicalize to
    ``patientid``, so one entry in :data:`PHI_PROPERTY_NAMES` covers the spellings
    a real graph mixes.
    """
    return ''.join(ch for ch in str(name).lower() if ch.isalnum())


#: Precomputed canonical forms of the PHI names, so detection is a set lookup.
PHI_CANONICAL = frozenset(canonical_property(name) for name in PHI_PROPERTY_NAMES)
