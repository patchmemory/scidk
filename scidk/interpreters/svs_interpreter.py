"""Whole-slide image interpreter — Aperio ``.svs``, Hamamatsu ``.ndpi``,
Leica ``.scn``.

All three are TIFF containers with the vendor's metadata stuffed into the
first page's ``ImageDescription`` tag. ``tifffile`` is used to read *that tag
and nothing else*: a whole-slide image is routinely 1–3 GB of pyramidal JPEG
tiles, and touching pixel data would turn a metadata sweep over 82 slides into
an afternoon.

Aperio's description is pipe-delimited ``Key = Value`` after a free-text
header::

    Aperio Image Library v12.0.15
    85344x33906 [0,100 83664x33806] (240x240) JPEG/RGB Q=70|AppMag = 20|
    StripeWidth = 2032|ScanScope ID = SS7170|Filename = …|Date = 01/31/22|…

Those keys become node property names, and ``Neo4jClient.write_declared_nodes``
interpolates property *names* straight into Cypher (only values are
parameterised — see the note in ``services/neo4j_client.py``). The keys come
out of a file, so they are untrusted input on a path to raw Cypher:
:func:`_property_key` is what stands between the two. The leading header
segment alone would otherwise produce a "key" of
``aperio_image_library_v12.0.15_\\r\\n85344x33906_[0,100_…_q``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from .base import BaseInterpreter, InterpretationResult

#: A property name safe to interpolate into Cypher unquoted.
_SAFE_KEY = re.compile(r'^[a-z][a-z0-9_]{0,62}$')

#: Aperio's header line, e.g. "85344x33906 [0,100 83664x33806] (240x240)".
_DIMENSIONS = re.compile(r'(\d{3,})x(\d{3,})')

#: Trailing slide number in a filename: PY-18500-001, HCF-LM-17930-009.
_SLIDE_NUMBER = re.compile(r'[-_](\d{3})(?:\.|$)')


class SVSInterpreter(BaseInterpreter):
    """File-level interpreter for one whole-slide image."""

    id = 'svs_interpreter'
    name = 'Whole-Slide Image Interpreter'
    version = '1.0.0'
    dispatch = 'file'
    extensions = ['.svs', '.ndpi', '.scn']

    #: Staining inferred from the filename. Histology filenames encode it far
    #: more often than the scanner metadata does — the Aperio header has no
    #: stain field at all.
    _STAIN_PATTERNS = {
        'IHC': 'Immunohistochemistry',
        'IF':  'Immunofluorescence',
        'HNE': 'H&E',
        'H&E': 'H&E',
        'HE':  'H&E',
    }

    #: Vendor by extension. ``.svs`` is Aperio unless the description says
    #: otherwise, which it does not in practice.
    _VENDORS = {'.svs': 'Aperio', '.ndpi': 'Hamamatsu', '.scn': 'Leica'}

    def interpret(self, path: Path, context: Optional[dict] = None) -> InterpretationResult:
        try:
            return self._parse(Path(path), context)
        except ImportError as e:
            # tifffile is an optional dependency; absence is a deployment fact,
            # not a bad file, and must not take the enrichment run down.
            return self._stub(Path(path), f"tifffile not installed: {e}")
        except Exception as e:
            return self._stub(Path(path), f"SVS parse failed: {type(e).__name__}: {e}")

    # -- parsing ------------------------------------------------------------
    def _parse(self, path: Path, context: Optional[dict] = None) -> InterpretationResult:
        import tifffile

        with tifffile.TiffFile(path) as tif:
            description = (tif.pages[0].description or '') if tif.pages else ''

        suffix = path.suffix.lower()
        props: Dict[str, object] = {
            'source_path': str(path),
            'vendor': self._VENDORS.get(suffix, 'Unknown'),
        }

        parsed, dropped = self._parse_description(description)
        props.update(parsed)

        width, height = self._dimensions(description)
        if width and height:
            props.setdefault('image_width', width)
            props.setdefault('image_height', height)

        props['staining'] = self._staining(path.stem)

        slide_number = _SLIDE_NUMBER.search(path.name)
        if slide_number:
            props['slide_number'] = int(slide_number.group(1))

        warnings = []
        if dropped:
            warnings.append(
                f"{len(dropped)} metadata field(s) dropped — unusable as property names: "
                + ', '.join(sorted(dropped)[:5])
            )
        if not description:
            warnings.append("No ImageDescription tag on page 0")

        return InterpretationResult(
            node_type='HistologySlide',
            node_label=f"Slide: {path.stem}",
            confidence='confirmed' if 'Aperio' in description else 'inferred',
            properties=props,
            provenance_edges=[{
                'type': 'METADATA_SOURCE',
                'from_label': 'HistologySlide',
                'from_match': {'source_path': str(path)},
                'to_label': 'File',
                'to_match': self._file_match(path, context),
            }],
            warnings=warnings,
        )

    @classmethod
    def _parse_description(cls, description: str) -> Tuple[Dict[str, str], set]:
        """Pipe-delimited ``Key = Value`` pairs, with the keys made safe.

        Returns the usable pairs and the raw keys that were rejected, so the
        loss shows up as a warning rather than as silence.
        """
        props: Dict[str, str] = {}
        dropped = set()
        if not description:
            return props, dropped

        # [1:] skips the free-text header, which contains a bare "Q=70" and
        # would otherwise partition into a key made of the whole first line.
        for part in description.split('|')[1:]:
            if '=' not in part:
                continue
            raw_key, _, value = part.partition('=')
            key = _property_key(raw_key)
            if key is None:
                dropped.add(raw_key.strip()[:40])
                continue
            props[key] = value.strip()
        return props, dropped

    @staticmethod
    def _dimensions(description: str) -> Tuple[Optional[int], Optional[int]]:
        match = _DIMENSIONS.search(description or '')
        if not match:
            return None, None
        return int(match.group(1)), int(match.group(2))

    @classmethod
    def _staining(cls, stem: str) -> str:
        """Longest tag first, so an ``HNE`` filename is not read as ``HE``."""
        upper = stem.upper()
        for tag in sorted(cls._STAIN_PATTERNS, key=len, reverse=True):
            if tag in upper:
                return cls._STAIN_PATTERNS[tag]
        return 'Unknown'


def _property_key(raw: str) -> Optional[str]:
    """Normalise a vendor metadata key, or None if it cannot be made safe.

    ``ScanScope ID`` → ``scanscope_id``, ``AppMag`` → ``appmag``. Anything that
    does not reduce to a plain identifier is rejected rather than escaped: a
    field whose name is a paragraph of scanner banner text has no value as a
    graph property, and the alternative is putting arbitrary text into a
    ``SET n.<key> = $p`` clause.
    """
    key = re.sub(r'[^a-z0-9]+', '_', (raw or '').strip().lower()).strip('_')
    return key if _SAFE_KEY.match(key) else None
