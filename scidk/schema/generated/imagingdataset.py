# Auto-generated from imaging_dataset.yaml — DO NOT EDIT MANUALLY
# Regenerate with: scidk labels generate-stubs
# Label version: 1.0.0
# Content hash: 014b09aa5bed

from __future__ import annotations
from typing import Any, Optional
from scidk.schema.base import SciDKNode


class ImagingDataset(SciDKNode):
    """
    A scientific imaging acquisition event and its derived processing stages.
    Represents a microCT scan, MRI acquisition, fluorescence microscopy session,
    or similar. The primary entity for imaging research data — files are
    artifacts linked to this entity, not individually meaningful graph nodes.

    Properties:
        path (str, required, key): Absolute path to the dataset root directory
        modality (str, required): Imaging modality
        voxel_size_um (float): Isotropic voxel size in micrometers — most critical spatial parameter
        voxel_size_x_um (float): Voxel size X dimension in micrometers (for anisotropic data)
        voxel_size_y_um (float): Voxel size Y dimension in micrometers (for anisotropic data)
        voxel_size_z_um (float): Voxel size Z dimension in micrometers (for anisotropic data)
        acquisition_date (str): Date of acquisition (YYYY-MM-DD)
        instrument (str): Instrument model name e.g. Bruker SkyScan 1272
        file_count (int): Total number of files in the dataset
        metadata_complete (bool): False if interpreter could not parse all expected metadata fields
        stack_id (str): SciDK stack ID linking this dataset to its scan history
        notes (str): Free text notes

    Relationships:
        METADATA_SOURCE → InstrumentRecord
        RAW_DATA → FileSet
        RECONSTRUCTED → FileSet
        ANALYSIS → FileSet
        SUBJECT → Sample
        PART_OF → Study
        DERIVED_FROM → File

    Example:
        node = ImagingDataset(path="example_id")
    """

    _label = 'ImagingDataset'
    _key_property = 'path'
    _sanitization = {}
    _allowed_values = {'modality': ['microCT', 'MRI', 'fMRI', 'PET', 'CT', 'fluorescence', 'confocal', 'brightfield', 'electron', 'other']}
    _required = ['path', 'modality']

    path: str  # required, unique key
    modality: Optional[str] = None  # required, allowed: ['microCT', 'MRI', 'fMRI'...+7]
    voxel_size_um: Optional[float] = None
    voxel_size_x_um: Optional[float] = None
    voxel_size_y_um: Optional[float] = None
    voxel_size_z_um: Optional[float] = None
    acquisition_date: Optional[str] = None
    instrument: Optional[str] = None
    file_count: Optional[int] = None
    metadata_complete: Optional[bool] = None
    stack_id: Optional[str] = None
    notes: Optional[str] = None
