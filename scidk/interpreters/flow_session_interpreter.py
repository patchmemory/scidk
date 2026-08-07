"""Directory-level interpreter: a folder of ``.fcs`` files is one acquisition
session.

This is the first interpreter that reads *other interpreters' results* rather
than a file. It aggregates the ``FCSFile`` nodes the enrichment dispatcher
produced in pass 1 for the same directory, which is why it declares
``dispatch = 'directory'`` and why an empty ``sibling_interpretations`` yields a
stub rather than an empty session: a session node asserting zero files and no
panel would be worse than an explicit "nothing to aggregate yet".

The unit is the folder because that is the unit the instrument writes. A
FACSDiva run produces one directory per experiment, named by the operator, with
one ``.fcs`` per tube — the panel, the cytometer, and the date are properties of
the run, not of any single tube, and only become visible once the tubes are read
together.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .base import BaseInterpreter, InterpretationResult

#: Subject codes as they appear in folder names: M12, U29, R7.
_SUBJECT_CODE = re.compile(r'\b[A-Z]\d+\b')

#: An ISO-ish date anywhere in the folder name: 2022-10-07 or 2022_10_07.
_FOLDER_DATE = re.compile(r'\d{4}[-_]\d{2}[-_]\d{2}')


class FlowSessionInterpreter(BaseInterpreter):
    """Aggregates sibling ``FCSFile`` interpretations into one session node."""

    id = 'flow_session_interpreter'
    name = 'Flow Cytometry Session Interpreter'
    version = '1.0.0'
    dispatch = 'directory'
    extensions = []  # directory dispatch — can_handle is overridden

    def can_handle(self, path: Path, context: Optional[dict] = None) -> bool:
        try:
            return any(f.suffix.lower() == '.fcs' for f in Path(path).iterdir() if f.is_file())
        except Exception:
            return False

    def interpret(self, path: Path, context: Optional[dict] = None) -> InterpretationResult:
        try:
            return self._aggregate(Path(path), context or {})
        except Exception as e:
            return self._stub(Path(path), f"Flow session aggregation failed: {type(e).__name__}: {e}")

    def _aggregate(self, path: Path, context: dict) -> InterpretationResult:
        siblings = context.get('sibling_interpretations') or {}

        cytometers, parameters_seen, sample_ids, dates = set(), set(), set(), set()
        member_paths = []
        total_events = 0

        for result in siblings.values():
            if getattr(result, 'node_type', None) != 'FCSFile':
                continue
            props = result.properties
            member_paths.append(props.get('source_path', ''))
            if props.get('cytometer'):
                cytometers.add(props['cytometer'])
            if props.get('acquisition_date'):
                dates.add(props['acquisition_date'])
            if props.get('sample_id'):
                sample_ids.add(props['sample_id'])
            if props.get('total_events'):
                total_events += int(props['total_events'])
            for parameter in (props.get('parameters') or '').split('|'):
                if parameter:
                    parameters_seen.add(parameter)

        if not member_paths:
            return self._stub(path, "No FCSFile interpretations available for this directory")

        subject_ids = set(_SUBJECT_CODE.findall(path.name))
        folder_date = _FOLDER_DATE.search(path.name)
        # The folder name wins when it carries a date: it is what the operator
        # chose to call the session, whereas $DATE is per-tube and a run that
        # crosses midnight disagrees with itself.
        session_date = (
            folder_date.group(0).replace('_', '-') if folder_date
            else (sorted(dates)[0] if dates else '')
        )

        props = {
            'source_path':      str(path),
            'fcs_file_count':   len(member_paths),
            'cytometer':        '|'.join(sorted(cytometers)),
            'panel_parameters': '|'.join(sorted(parameters_seen)),
            'parameter_count':  len(parameters_seen),
            'total_events':     total_events,
            'session_date':     session_date,
            'subject_ids':      '|'.join(sorted(subject_ids | sample_ids)),
        }

        return InterpretationResult(
            node_type='FlowCytometrySession',
            node_label=f"Flow session: {path.name}",
            confidence='confirmed',
            properties=props,
            provenance_edges=[
                {
                    'type': 'DERIVED_FROM',
                    'from_label': 'FlowCytometrySession',
                    'from_match': {'source_path': str(path)},
                    'to_label': 'FCSFile',
                    'to_match': {'source_path': member},
                }
                for member in member_paths if member
            ],
        )
