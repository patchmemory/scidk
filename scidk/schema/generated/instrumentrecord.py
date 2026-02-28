# Auto-generated from instrument_record.yaml — DO NOT EDIT MANUALLY
# Regenerate with: scidk labels generate-stubs
# Label version: 1.0.0
# Content hash: 61a84ea4fb6e

from __future__ import annotations
from typing import Any, Optional
from scidk.schema.base import SciDKNode


class InstrumentRecord(SciDKNode):
    """
    Raw instrument parameters parsed from a hardware header or log file. Stores
    acquisition settings exactly as recorded by the instrument — voltage,
    current, exposure, rotation, reconstruction parameters, etc. Every parseable
    field is stored. Unknown fields are stored with raw_ prefix.

    Properties:
        source_file (str, required, key): Absolute path to the source header/log file
        instrument_model (str): Instrument model name from header
        instrument_manufacturer (str): Instrument manufacturer
        voltage_kv (float): Source voltage in kilovolts
        current_ua (float): Source current in microamps
        exposure_ms (float): Exposure time in milliseconds
        rotation_step_deg (float): Rotation step in degrees
        frame_averaging (int): Number of frames averaged per projection
        filter (str): Hardware filter e.g. Al 0.5mm
        reconstruction_software (str): Reconstruction software name and version
        reconstruction_algorithm (str): Reconstruction algorithm used
        smoothing (int): Smoothing parameter used in reconstruction
        ring_artifact_correction (int): Ring artifact correction parameter
        beam_hardening_correction (int): Beam hardening correction percentage
        metadata_complete (bool): False if some expected fields could not be parsed
        parser (str): Interpreter ID that produced this record e.g. bruker_skyscan_log

    Relationships:
        ← METADATA_SOURCE ← ImagingDataset

    Example:
        node = InstrumentRecord(source_file="example_id")
    """

    _label = 'InstrumentRecord'
    _key_property = 'source_file'
    _sanitization = {}
    _allowed_values = {}
    _required = ['source_file']

    source_file: str  # required, unique key
    instrument_model: Optional[str] = None
    instrument_manufacturer: Optional[str] = None
    voltage_kv: Optional[float] = None
    current_ua: Optional[float] = None
    exposure_ms: Optional[float] = None
    rotation_step_deg: Optional[float] = None
    frame_averaging: Optional[int] = None
    filter: Optional[str] = None
    reconstruction_software: Optional[str] = None
    reconstruction_algorithm: Optional[str] = None
    smoothing: Optional[int] = None
    ring_artifact_correction: Optional[int] = None
    beam_hardening_correction: Optional[int] = None
    metadata_complete: Optional[bool] = None
    parser: Optional[str] = None
