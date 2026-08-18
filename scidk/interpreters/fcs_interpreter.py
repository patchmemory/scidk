"""Flow Cytometry Standard (FCS) file interpreter.

Reads the TEXT segment and nothing else — no event data, no dependency. FCS is
specified tightly enough that stdlib is sufficient:

* bytes 0–5   — version string, ``FCS3.1`` / ``FCS3.0`` / ``FCS2.0``
* bytes 6–9   — spaces
* bytes 10–17 — TEXT segment start offset, right-justified ASCII
* bytes 18–25 — TEXT segment end offset (inclusive)

The TEXT segment is ``<delim>KEY<delim>VALUE<delim>KEY<delim>VALUE…`` where the
delimiter is *whatever the first byte of the segment says it is*. It is
commonly ``\\x0c`` (form feed) on BD instruments and ``|`` or ``/`` elsewhere —
assuming a backslash, as most quick parsers do, silently yields one enormous
key. Reading byte 0 costs nothing and is what the spec requires.

Verified against FACSymphony A1 exports: 253 keywords, delimiter ``\\x0c``,
``$TOT`` zero-padded to 19 digits.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from .base import BaseInterpreter, InterpretationResult

#: The header is fixed-width; anything shorter cannot carry the offsets.
_HEADER_BYTES = 58

#: A malformed offset pair could otherwise ask for an unbounded read. Real TEXT
#: segments are a few KB; 8 MB is far past any plausible one.
_MAX_TEXT_BYTES = 8 * 1024 * 1024


class FCSInterpreter(BaseInterpreter):
    """File-level interpreter for one FCS acquisition."""

    id = 'fcs_interpreter'
    name = 'FCS Flow Cytometry Interpreter'
    version = '1.0.0'
    dispatch = 'file'
    extensions = ['.fcs']

    def interpret(self, path: Path, context: Optional[dict] = None) -> InterpretationResult:
        try:
            return self._parse(Path(path), context)
        except Exception as e:  # never raises — the contract is a stub instead
            return self._stub(Path(path), f"FCS parse failed: {type(e).__name__}: {e}")

    # -- parsing ------------------------------------------------------------
    def _parse(self, path: Path, context: Optional[dict] = None) -> InterpretationResult:
        with open(path, 'rb') as f:
            header = f.read(_HEADER_BYTES)
            if len(header) < _HEADER_BYTES:
                return self._stub(path, "File too short to be FCS")

            version = header[:6].decode('ascii', errors='replace').strip()
            if not version.startswith('FCS'):
                return self._stub(path, f"Not an FCS file (header: {version!r})")

            try:
                text_start = int(header[10:18].strip())
                text_end = int(header[18:26].strip())
            except ValueError:
                return self._stub(path, "FCS header carries no usable TEXT offsets")

            length = text_end - text_start + 1
            if text_start <= 0 or length <= 1:
                # Offsets of 0 mean the real ones live in $BEGINSTEXT, which is
                # itself inside the segment we cannot find. Files big enough to
                # need that are rare; say so rather than guess.
                return self._stub(path, "FCS TEXT segment offsets are empty or out of range")
            if length > _MAX_TEXT_BYTES:
                return self._stub(path, f"FCS TEXT segment implausibly large ({length} bytes)")

            f.seek(text_start)
            text_bytes = f.read(length)

        if not text_bytes:
            return self._stub(path, "FCS TEXT segment is empty")

        kv = self._parse_text_segment(text_bytes)
        if not kv:
            return self._stub(path, "FCS TEXT segment yielded no keywords")

        parameters = self._parameter_names(kv)

        props = {
            'source_path':      str(path),
            'fcs_version':      version,
            'cytometer':        kv.get('$CYT', ''),
            'sample_id':        kv.get('$SRC', ''),
            'acquisition_date': kv.get('$DATE', ''),
            'system':           kv.get('$SYS', ''),
            'total_events':     _as_int(kv.get('$TOT')),
            'parameter_count':  _as_int(kv.get('$PAR')) or len(parameters),
            # Neo4j can hold a list, but the property rankings and the CSV
            # exports downstream both read scalars; pipe-delimited matches how
            # the other interpreters store multi-values.
            'parameters':       '|'.join(parameters),
        }

        return InterpretationResult(
            node_type='FCSFile',
            node_label=f"FCS: {path.stem}",
            confidence='confirmed' if version.startswith('FCS3') else 'inferred',
            properties=props,
            provenance_edges=[{
                'type': 'METADATA_SOURCE',
                'from_label': 'FCSFile',
                'from_match': {'source_path': str(path)},
                'to_label': 'File',
                'to_match': self._file_match(path, context),
            }],
            raw_metadata=kv,
        )

    @staticmethod
    def _parse_text_segment(text_bytes: bytes) -> Dict[str, str]:
        """Split the delimiter-separated keyword/value run into a dict.

        latin-1 never raises on a byte sequence, which matters because vendors
        put degree signs and micro symbols in stain names with no declared
        encoding.
        """
        delimiter = chr(text_bytes[0])
        parts = text_bytes[1:].decode('latin-1').split(delimiter)
        kv: Dict[str, str] = {}
        for i in range(0, len(parts) - 1, 2):
            key = parts[i].strip().upper()
            if key:
                kv[key] = parts[i + 1].strip()
        return kv

    @staticmethod
    def _parameter_names(kv: Dict[str, str]) -> List[str]:
        """Detector names, ``$P1N``…``$PnN``.

        ``$PAR`` bounds the walk rather than "stop at the first gap": a file
        missing one ``$PnN`` in the middle would otherwise report a panel
        truncated at that point instead of one entry short.
        """
        declared = _as_int(kv.get('$PAR')) or 0
        upper = declared if declared > 0 else len(kv)
        names: List[str] = []
        for i in range(1, upper + 1):
            value = kv.get(f'$P{i}N')
            if value:
                names.append(value)
            elif declared <= 0:
                break
        return names


def _as_int(value: Optional[str]) -> Optional[int]:
    """FCS integers arrive zero-padded and occasionally blank."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
