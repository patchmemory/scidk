"""Streaming a SharePoint list export's rows.

The read path behind :mod:`plugins.sharepoint_intake.plugin`'s ``find()`` and
``fetch()``: bytes in, ``{column: value}`` dicts out, lazily. This module knows no
column names, no labels, no relationship types, and imports neither Flask nor
Neo4j.

The plugin's responsibility ends at the row stream. What the columns *mean* —
which become nodes, which become properties, which become relationships — lives
in a mapping config (``configs/aipt_intake_mapping.json``) and is applied by
:mod:`scidk.pipeline`, never here.

Locating and authorizing a source is :mod:`plugins.sharepoint_intake.source`;
parsing a format is :mod:`plugins.sharepoint_intake.readers`.
"""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple

from . import readers, source
from .source import DEFAULT_TIMEOUT_SEC

logger = logging.getLogger(__name__)

#: Rows :func:`scan_source` counts before giving up on an exact total, so
#: ``find()`` stays inside its 10s budget on an arbitrarily large list.
MAX_SCAN_ROWS = 100_000


def iter_lines(target: str, provider: Optional[Any] = None,
               timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> Iterator[str]:
    """Yield decoded text lines from ``target`` without buffering all of it.

    Local paths are read directly; remotes stream off the provider's ``open()``
    pipe. A provider that cannot stream falls back to a buffered ``cat()`` —
    correct but no longer lazy, hence the log line. ``timeout_sec`` applies only
    to that fallback; bounding a whole run is the Pipeline runner's job.
    """
    if source.is_local(target):
        with open(target, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
            yield from fh
        return
    provider = source.get_provider(provider)
    try:
        stream = provider.open(target)
    except (AttributeError, NotImplementedError):
        stream = None
    if stream is None:
        logger.debug("Provider %s cannot stream; buffering via cat", type(provider).__name__)
        payload = readers.decode_line(provider.cat(target, timeout_sec=timeout_sec))
        yield from io.StringIO(payload, newline="")
        return
    try:
        for raw in stream:
            yield readers.decode_line(raw)
    finally:
        try:
            stream.close()
        except Exception:  # noqa: BLE001 - closing a spent pipe is not an error
            pass


def open_rows(target: str, provider: Optional[Any] = None,
              timeout_sec: float = DEFAULT_TIMEOUT_SEC,
              sheet: Optional[str] = None) -> Tuple[List[str], Iterator[Dict[str, str]]]:
    """Return ``(columns, lazy row iterator)``, dispatching on the file extension.

    Reporting the columns separately means a header-only source still describes
    its schema, and lets ``find()`` describe a source it never fully reads.
    """
    if readers.is_excel(target):
        handle: Any = target
        if not source.is_local(target):
            handle = io.BytesIO(source.get_provider(provider).cat(target, timeout_sec=timeout_sec))
        return readers.excel_rows(handle, sheet=sheet)
    lines = iter_lines(target, provider=provider, timeout_sec=timeout_sec)
    return readers.delimited_rows(lines, delimiter=readers.delimiter_for(target))


def iter_rows(target: str, provider: Optional[Any] = None,
              timeout_sec: float = DEFAULT_TIMEOUT_SEC,
              sheet: Optional[str] = None) -> Iterator[Dict[str, str]]:
    """Stream ``target`` as raw ``{column: value}`` rows. No transforms applied."""
    _columns, rows = open_rows(target, provider=provider, timeout_sec=timeout_sec, sheet=sheet)
    yield from rows


def scan_source(target: str, provider: Optional[Any] = None,
                timeout_sec: float = DEFAULT_TIMEOUT_SEC, sample_rows: int = 3,
                max_scan_rows: int = MAX_SCAN_ROWS,
                sheet: Optional[str] = None) -> Dict[str, Any]:
    """One lazy pass returning ``{columns, sample, row_count, truncated}``.

    Retains only ``sample_rows`` rows, so memory stays flat however long the
    source is. Counting stops at ``max_scan_rows``, after which ``row_count`` is
    None and ``truncated`` is True rather than overrunning find()'s 10s budget.
    """
    columns, rows = open_rows(target, provider=provider, timeout_sec=timeout_sec, sheet=sheet)
    sample: List[Dict[str, str]] = []
    count = 0
    truncated = False
    for row in rows:
        if len(sample) < sample_rows:
            sample.append(dict(row))
        count += 1
        if count >= max_scan_rows:
            truncated = True
            break
    return {"columns": columns, "sample": sample,
            "row_count": None if truncated else count, "truncated": truncated}
