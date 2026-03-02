# Auto-generated from sample.yaml — DO NOT EDIT MANUALLY
# Regenerate with: scidk labels generate-stubs
# Label version: 1.0.0
# Content hash: e1244570bbe1

from __future__ import annotations
from typing import Any, Optional
from scidk.schema.base import SciDKNode


class Sample(SciDKNode):
    """
    A biological sample that was acquired, processed, or analyzed. Used to link
    imaging datasets, experimental results, and metadata about the physical
    specimen.

    Properties:
        sample_id (str, required, key): Lab-assigned sample identifier
        donor_age (int): Age of donor at time of sample collection — binned to 10-unit ranges (years)
        donor_name (str): Donor full name — NEVER stored in graph — ⚠️  REDACTED — never written to graph
        diagnosis (str): Clinical diagnosis — encoded to ICD-10 vocabulary
        institution (str): Source institution — one-way hashed before storage
        species (str): Organism species
        tissue_type (str): Tissue or organ type
        collection_date (str): Date sample was collected (YYYY-MM-DD) — rounded to reduce precision before storage
        notes (str): Free text notes — stored as-is, avoid PII

    Relationships:
        PART_OF → Study
        ← SUBJECT_OF ← ImagingDataset

    Example:
        node = Sample(sample_id="example_id")
        # donor_age is binned to range before storage e.g. 45 → "40-50 years"
    """

    _label = 'Sample'
    _key_property = 'sample_id'
    _sanitization = {'donor_age': {'rule': 'bin', 'bin_size': 10, 'units': 'years'}, 'donor_name': {'rule': 'redact'}, 'diagnosis': {'rule': 'encode', 'vocabulary': 'ICD-10', 'fallback': 'hash', 'case_sensitive': False}, 'institution': {'rule': 'hash', 'preserve_linkability': True}, 'collection_date': {'rule': 'truncate', 'decimal_places': 0}}
    _allowed_values = {'species': ['Homo sapiens', 'Mus musculus', 'Rattus norvegicus', 'Drosophila melanogaster', 'Danio rerio', 'Caenorhabditis elegans']}
    _required = ['sample_id']

    sample_id: str  # required, unique key
    donor_age: Optional[int] = None  # sanitize: bin
    donor_name: Optional[str] = None  # sanitize: redact
    diagnosis: Optional[str] = None  # sanitize: encode
    institution: Optional[str] = None  # sanitize: hash
    species: Optional[str] = None  # allowed: ['Homo sapiens', 'Mus musculus', 'Rattus norvegicus'...+3]
    tissue_type: Optional[str] = None
    collection_date: Optional[str] = None  # sanitize: truncate
    notes: Optional[str] = None
