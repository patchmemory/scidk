"""Property-sharing preferences and the fail-closed legacy-result boundary.

Resource/principal/destination authority is in security.py; applied/current fact
serialization is in facts.py. A property mask alone can never authorize arbitrary
query output, including scalar/aggregate results, labels or withholding counts.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

RAW = 'raw'
HIDDEN = 'hidden'
#: Modes a user can set today. The roadmap's pseudonymized / simulated /
#: randomized are accepted in storage but filtered as hidden until built.
SETTABLE_MODES = (RAW, HIDDEN)

#: Keys the tool layer adds to serialized graph values; never filtered.
META_KEYS = frozenset({'_labels', '_type', '_id', '_start', '_end'})


@dataclass(frozen=True)
class SharingPolicy:
    #: (label, property) -> mode, for every non-raw setting.
    modes: Dict[Tuple[str, str], str] = field(default_factory=dict)
    withheld_sources: FrozenSet[str] = frozenset()

    @property
    def hidden_anywhere(self) -> Set[str]:
        return {prop for (_label, prop), mode in self.modes.items() if mode != RAW}

    def is_hidden(self, labels: Iterable[str], prop: str) -> bool:
        return any(self.modes.get((label, prop), RAW) != RAW for label in labels)

    @property
    def empty(self) -> bool:
        return not self.modes and not self.withheld_sources


# ── Storage ─────────────────────────────────────────────────────────────────

def _connect(settings_db: str) -> sqlite3.Connection:
    conn = sqlite3.connect(settings_db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS agent_sharing ("
        " label TEXT NOT NULL, property TEXT NOT NULL, mode TEXT NOT NULL,"
        " updated_at REAL, updated_by TEXT, PRIMARY KEY (label, property))")
    return conn


def load_policy(settings_db: Optional[str]) -> SharingPolicy:
    """The current policy. Raises if the settings DB can't be read: a tool that
    can't tell what is hidden must not answer as if nothing were."""
    if not settings_db:
        raise ValueError('Disclosure policy unavailable')
    from pathlib import Path
    conn = sqlite3.connect(Path(settings_db).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        rows = conn.execute("SELECT label, property, mode FROM agent_sharing").fetchall()
    finally:
        conn.close()
    return SharingPolicy(modes={(l, p): m for l, p, m in rows if m != RAW})


def list_modes(settings_db: str) -> List[Dict[str, Any]]:
    conn = _connect(settings_db)
    try:
        rows = conn.execute(
            "SELECT label, property, mode, updated_at, updated_by FROM agent_sharing "
            "ORDER BY label, property").fetchall()
    finally:
        conn.close()
    return [dict(zip(('label', 'property', 'mode', 'updated_at', 'updated_by'), r)) for r in rows]


def set_mode(settings_db: str, label: str, prop: str, mode: str, user: Optional[str] = None) -> None:
    if mode not in SETTABLE_MODES:
        raise ValueError(f"sharing_mode must be one of {', '.join(SETTABLE_MODES)}")
    conn = _connect(settings_db)
    try:
        if mode == RAW:
            conn.execute("DELETE FROM agent_sharing WHERE label=? AND property=?", (label, prop))
        else:
            conn.execute(
                "INSERT OR REPLACE INTO agent_sharing(label, property, mode, updated_at, updated_by) "
                "VALUES (?,?,?,?,?)", (label, prop, mode, time.time(), user))
        conn.commit()
    finally:
        conn.close()


def check_cypher(cypher: str, policy: SharingPolicy,
                 parameters: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Arbitrary Cypher cannot be authorized by post-query property masking."""
    from .security import REFUSAL
    return REFUSAL['error']


def filter_for_agent(result: Dict[str, Any], policy: SharingPolicy) -> Dict[str, Any]:
    """Refuse unproven arbitrary results; use the fixed FactDisclosure reader."""
    from .security import REFUSAL
    return dict(REFUSAL)
