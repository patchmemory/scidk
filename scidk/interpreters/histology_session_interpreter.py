"""Directory-level interpreter: a folder of whole-slide images is one scanning
session.

The twin of :mod:`scidk.interpreters.flow_session_interpreter` — same
two-pass contract, same "stub rather than an empty session" rule. What differs
is what is worth rolling up. A slide-scanner session's interesting facts are
which stains were run, which scanner ran them, at what magnification, and over
what span of dates: a tray of 30 slides scanned across two days on one
ScanScope is one session, and the date *range* is the honest summary of it
where a single date would not be.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import BaseInterpreter, InterpretationResult

_SLIDE_EXTENSIONS = {'.svs', '.ndpi', '.scn'}


class HistologySessionInterpreter(BaseInterpreter):
    """Aggregates sibling ``HistologySlide`` interpretations into a session."""

    id = 'histology_session_interpreter'
    name = 'Histology Session Interpreter'
    version = '1.0.0'
    dispatch = 'directory'
    extensions = []  # directory dispatch — can_handle is overridden

    def can_handle(self, path: Path, context: Optional[dict] = None) -> bool:
        try:
            return any(
                f.suffix.lower() in _SLIDE_EXTENSIONS
                for f in Path(path).iterdir() if f.is_file()
            )
        except Exception:
            return False

    def interpret(self, path: Path, context: Optional[dict] = None) -> InterpretationResult:
        try:
            return self._aggregate(Path(path), context or {})
        except Exception as e:
            return self._stub(Path(path), f"Histology session aggregation failed: {type(e).__name__}: {e}")

    def _aggregate(self, path: Path, context: dict) -> InterpretationResult:
        siblings = context.get('sibling_interpretations') or {}

        stains, scanners, magnifications, vendors = set(), set(), set(), set()
        member_paths, scan_dates = [], []

        for result in siblings.values():
            if getattr(result, 'node_type', None) != 'HistologySlide':
                continue
            props = result.properties
            member_paths.append(props.get('source_path', ''))
            if props.get('staining') and props['staining'] != 'Unknown':
                stains.add(props['staining'])
            if props.get('scanscope_id'):
                scanners.add(str(props['scanscope_id']))
            if props.get('appmag'):
                magnifications.add(str(props['appmag']))
            if props.get('vendor'):
                vendors.add(str(props['vendor']))
            if props.get('date'):
                scan_dates.append(str(props['date']))

        if not member_paths:
            return self._stub(path, "No HistologySlide interpretations available for this directory")

        props = {
            'source_path':        str(path),
            'slide_count':        len(member_paths),
            'staining_protocols': '|'.join(sorted(stains)),
            'scanner_ids':        '|'.join(sorted(scanners)),
            'vendors':            '|'.join(sorted(vendors)),
            'magnifications':     '|'.join(sorted(magnifications)),
            # Aperio writes MM/DD/YY, so these sort lexically by month. Kept as
            # first/last *seen* rather than min/max to avoid implying an
            # ordering the format does not support; normalising the date is a
            # separate change with its own ambiguity (02/03/22).
            'scan_date_first':    scan_dates[0] if scan_dates else '',
            'scan_date_last':     scan_dates[-1] if scan_dates else '',
        }

        return InterpretationResult(
            node_type='HistologySession',
            node_label=f"Histology session: {path.name}",
            confidence='confirmed',
            properties=props,
            provenance_edges=[
                {
                    'type': 'DERIVED_FROM',
                    'from_label': 'HistologySession',
                    'from_match': {'source_path': str(path)},
                    'to_label': 'HistologySlide',
                    'to_match': {'source_path': member},
                }
                for member in member_paths if member
            ],
        )
