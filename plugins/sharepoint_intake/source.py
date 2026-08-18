"""Locating, describing, and authorizing access to a SharePoint list export.

Everything about the *source* other than reading its rows. Row streaming is
:mod:`plugins.sharepoint_intake.ingest`; format parsing is
:mod:`plugins.sharepoint_intake.readers`.

A source is either a local path (what tests use) or an rclone remote path
(``remote:Site/Lists/Name.csv``). Nothing here imports Flask or Neo4j.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: Default timeout, in seconds, for a buffered read of a remote source.
DEFAULT_TIMEOUT_SEC = 120.0


def get_provider(provider: Optional[Any] = None) -> Any:
    """Return ``provider``, or a fresh ``RcloneProvider`` when none was given.

    ``cat``/``open`` only shell out to rclone, so no ``initialize()`` is needed.
    """
    if provider is not None:
        return provider
    from scidk.core.providers import RcloneProvider

    return RcloneProvider()


def is_local(source: str) -> bool:
    """True when ``source`` names an existing local file rather than a remote."""
    return bool(source) and os.path.isfile(source)


def describe(source: str, provider: Optional[Any] = None) -> Dict[str, Any]:
    """Describe the source without reading it (``os.stat`` / ``rclone lsjson``).

    Never raises: an unreachable listing yields a sparser dict, because this is
    descriptive detail for the UI, not a precondition for reading.
    """
    if is_local(source):
        stat = os.stat(source)
        return {"transport": "local", "name": os.path.basename(source),
                "size": stat.st_size, "modified": stat.st_mtime}
    meta: Dict[str, Any] = {"transport": "rclone", "name": str(source).rsplit("/", 1)[-1]}
    try:
        entries = get_provider(provider).list_files(source, recursive=False) or []
    except Exception as e:  # noqa: BLE001 - listing is best-effort metadata
        logger.debug("lsjson on %r failed: %s", source, e)
        return meta
    files = [e for e in entries if not e.get("IsDir")]
    if len(files) == 1:
        meta.update({"name": files[0].get("Name") or meta["name"],
                     "size": files[0].get("Size"), "modified": files[0].get("ModTime")})
    elif files:
        meta["candidates"] = [e.get("Name") for e in files]
    return meta


def verify_read(source: str, provider: Optional[Any] = None,
                timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> None:
    """Prove an authenticated read of the source's content is permitted.

    Reads the smallest possible slice of real content — distinct from a listing,
    which a credential may be allowed to see without being allowed to read rows.
    Raises on failure; returns None on success.
    """
    if is_local(source):
        with open(source, "rb") as fh:
            fh.read(1)
        return
    get_provider(provider).cat(source, max_bytes=1, timeout_sec=timeout_sec)


def detect_auth_method(source: str) -> Optional[str]:
    """Identify the credential type behind ``source`` via ``rclone config dump``.

    ``"rclone_oauth"`` for a remote holding a token, ``"rclone_basic"`` for one
    configured with static credentials, ``"local"`` for a plain path, and None
    when it cannot tell — an unknown auth method is not a failure to report.
    """
    if is_local(source):
        return "local"
    remote, separator, _path = str(source or "").partition(":")
    if not remote or not separator:
        return None
    try:
        import json, shutil, subprocess

        exe = shutil.which("rclone")
        if not exe:
            return None
        proc = subprocess.run([exe, "config", "dump"], capture_output=True, text=True, timeout=15)
        entry = (json.loads(proc.stdout or "{}") or {}).get(remote) or {}
    except Exception as e:  # noqa: BLE001 - identification is advisory only
        logger.debug("rclone config dump failed: %s", e)
        return None
    if not entry:
        return None
    return "rclone_oauth" if entry.get("token") else "rclone_basic"
