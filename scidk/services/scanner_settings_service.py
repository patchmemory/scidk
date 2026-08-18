"""Scanner worker-budget settings, stored in scidk_settings.db.

Two knobs govern scan admission: how many I/O workers may be in flight across
all running scans, and how many scans may run at once. Both are read on every
POST /api/tasks, so the operator can retune a busy server without a restart.

Precedence is env → database → default. The environment wins because a
deployment that pins SCIDK_MAX_TOTAL_WORKERS should not be silently overridden
by someone clicking Save in the UI; the UI reflects that by rendering the field
read-only when an env var is active.

This lives in scidk_settings.db, not files.db, so the DDL belongs here in an
_ensure_table_exists() method following SavedMapsService — never in
migrations.py, which runs against every database in the test suite.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOTAL_WORKERS = 32
DEFAULT_MAX_CONCURRENT_SCANS = 4

ENV_MAX_TOTAL_WORKERS = 'SCIDK_MAX_TOTAL_WORKERS'
ENV_MAX_CONCURRENT_SCANS = 'SCIDK_MAX_CONCURRENT_SCANS'

# Bounds enforced on writes. 256 workers is already past the point where a CIFS
# mount stops rewarding more threads; the cap is there to stop a typo taking the
# server down.
LIMITS = {
    'max_total_workers': (1, 256),
    'max_concurrent_scans': (1, 16),
}

_DEFAULTS = {
    'max_total_workers': DEFAULT_MAX_TOTAL_WORKERS,
    'max_concurrent_scans': DEFAULT_MAX_CONCURRENT_SCANS,
}

_ENV_KEYS = {
    'max_total_workers': ENV_MAX_TOTAL_WORKERS,
    'max_concurrent_scans': ENV_MAX_CONCURRENT_SCANS,
}


def _ensure_scanner_settings_table(db_path: str) -> None:
    """Create the scanner_settings table if it is missing."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scanner_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()
        logger.debug("Ensured scanner_settings table exists")
    finally:
        conn.close()


def _read_db_values(db_path: str) -> Dict[str, int]:
    """Stored values, ignoring rows that are absent or unparseable."""
    out: Dict[str, int] = {}
    try:
        _ensure_scanner_settings_table(db_path)
        conn = sqlite3.connect(db_path)
        try:
            for key, value in conn.execute(
                "SELECT key, value FROM scanner_settings"
            ).fetchall() or []:
                if key in _DEFAULTS:
                    try:
                        out[key] = int(value)
                    except (TypeError, ValueError):
                        continue
        finally:
            conn.close()
    except Exception as e:
        logger.warning("Could not read scanner_settings from %s: %s", db_path, e)
    return out


def _env_value(key: str) -> Optional[int]:
    raw = os.environ.get(_ENV_KEYS[key])
    if raw is None or str(raw).strip() == '':
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        logger.warning("Ignoring non-integer %s=%r", _ENV_KEYS[key], raw)
        return None


def get_effective_settings(db_path: str) -> dict:
    """Resolve both knobs and say where each value came from.

    Returns the two values plus per-key provenance. ``source`` is the coarse
    answer the API contract asks for ('env' if either knob is pinned by the
    environment, else 'db' if either is stored, else 'default'); ``sources``
    and ``env_override`` give the per-key detail, which is what the UI needs to
    decide which single field to disable.
    """
    stored = _read_db_values(db_path)
    values: Dict[str, int] = {}
    sources: Dict[str, str] = {}
    for key, default in _DEFAULTS.items():
        env_val = _env_value(key)
        if env_val is not None:
            values[key], sources[key] = env_val, 'env'
        elif key in stored:
            values[key], sources[key] = stored[key], 'db'
        else:
            values[key], sources[key] = default, 'default'
    if 'env' in sources.values():
        overall = 'env'
    elif 'db' in sources.values():
        overall = 'db'
    else:
        overall = 'default'
    return {
        'max_total_workers': values['max_total_workers'],
        'max_concurrent_scans': values['max_concurrent_scans'],
        'source': overall,
        'sources': sources,
        'env_override': {k: (v == 'env') for k, v in sources.items()},
        'defaults': dict(_DEFAULTS),
        'limits': {k: {'min': lo, 'max': hi} for k, (lo, hi) in LIMITS.items()},
    }


def get_caps(db_path: str) -> Tuple[int, int]:
    """(max_total_workers, max_concurrent_scans) — the hot path for admission."""
    s = get_effective_settings(db_path)
    return int(s['max_total_workers']), int(s['max_concurrent_scans'])


def validate(key: str, value) -> int:
    """Coerce and range-check one setting. Raises ValueError with a UI-ready message."""
    lo, hi = LIMITS[key]
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be an integer between {lo} and {hi}")
    if not (lo <= ivalue <= hi):
        raise ValueError(f"{key} must be between {lo} and {hi}")
    return ivalue


def save_settings(db_path: str, max_total_workers=None,
                  max_concurrent_scans=None) -> dict:
    """Persist whichever knobs were supplied, then report the effective state.

    Writing a value that the environment overrides is allowed on purpose: the
    stored value becomes live as soon as the env var is removed. The response
    says which keys are currently being overridden so the caller can say so.
    """
    updates = {}
    if max_total_workers is not None:
        updates['max_total_workers'] = validate('max_total_workers', max_total_workers)
    if max_concurrent_scans is not None:
        updates['max_concurrent_scans'] = validate('max_concurrent_scans', max_concurrent_scans)
    if updates:
        _ensure_scanner_settings_table(db_path)
        conn = sqlite3.connect(db_path)
        try:
            conn.executemany(
                "INSERT INTO scanner_settings(key, value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                [(k, str(v)) for k, v in updates.items()],
            )
            conn.commit()
        finally:
            conn.close()
    result = get_effective_settings(db_path)
    result['saved'] = updates
    return result
