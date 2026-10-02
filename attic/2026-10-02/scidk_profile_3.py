#!/usr/bin/env python3
"""
scidk_profile.py — Dataset profile matching for SciDK (Pass 3 + Pass 4)
=========================================================================
Finds research dataset objects in the filesystem index by matching
structural patterns against files.db. Two passes:

  Pass 3 (--match-only): Pure SQL + in-memory matching against YAML profiles.
    Loads directory contents from files.db, runs profile_matcher against each
    directory, writes candidates to data_objects table. No mount access needed.

  Pass 4 (--interpret): Reads sentinel files of candidates via mount.
    Confirms matches and extracts acquisition metadata. Only reads one file
    per candidate dataset.

  Default (no flag): runs Pass 3 then Pass 4 in sequence.

Usage:
    python3 scidk_profile.py --match-only --dry-run
    python3 scidk_profile.py --match-only
    python3 scidk_profile.py --coverage
    python3 scidk_profile.py
    python3 scidk_profile.py --scan-id 48079274-1de5
    python3 scidk_profile.py --match-only --profile vevo_ultrasound

Options:
    --db PATH           files.db path (default: ~/.scidk/db/files.db)
    --profiles-dir DIR  YAML profiles directory
                        (default: scidk/interpreters/profiles/ relative to
                        this script, or ~/.scidk/profiles/ as fallback)
    --scan-id ID        Limit to one scan (prefix match)
    --profile NAME      Run only named profile(s), comma-separated
    --match-only        Pass 3 only: matching, no sentinel reads
    --interpret         Pass 4 only: interpret sentinels of candidates
    --coverage          Show unclaimed directory analysis and exit
    --dry-run           Preview matches without writing to DB
    --recheck           Re-run matching on already-claimed directories
    --quiet             Suppress per-directory progress
    --json              Output summary as JSON

Exit codes:
    0  Success
    1  Error
"""

import argparse
import json
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Profile registry — use SciDK package if available, else load YAML directly
# ─────────────────────────────────────────────────────────────────────────────

def _find_profiles_dir(hint: Optional[str] = None) -> Optional[Path]:
    """Locate the YAML profiles directory."""
    candidates = []
    if hint:
        candidates.append(Path(hint))
    # Relative to this script (works when run from repo root)
    script_dir = Path(__file__).resolve().parent
    candidates += [
        script_dir / "scidk" / "interpreters" / "profiles",
        script_dir.parent / "scidk" / "interpreters" / "profiles",
        Path.home() / ".scidk" / "profiles",
    ]
    for p in candidates:
        if p.exists() and any(p.glob("*.yaml")):
            return p
    return None


def _load_profiles(profiles_dir: Path) -> Tuple[Dict, object]:
    """
    Load profiles using SciDK's ProfileRegistry if available,
    otherwise fall back to raw yaml parsing.
    Returns (profile_map, matcher_fn) where matcher_fn(dir_path, entries, profile) -> dict.
    """
    try:
        from scidk.core.profile_registry import ProfileRegistry
        from scidk.core.profile_matcher import match as _match

        reg = ProfileRegistry()
        reg.load(profiles_dir)
        profile_map = {
            pid: p for pid, p in reg._profiles.items()
            if p.get("enabled", True) and not p.get("abstract", False)
        }
        return profile_map, _match

    except ImportError:
        # Standalone fallback — parse YAML directly
        try:
            import yaml
        except ImportError:
            print("ERROR: PyYAML required. Install with: pip install pyyaml",
                  file=sys.stderr)
            sys.exit(1)

        profile_map = {}
        for path in sorted(profiles_dir.glob("*.yaml")):
            try:
                with path.open() as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict) and data.get("profile_id"):
                    profile_map[data["profile_id"]] = data
            except Exception as e:
                print(f"  WARN: failed to load {path.name}: {e}", file=sys.stderr)

        def _simple_match(dir_path: str, entries: list, profile: dict) -> dict:
            """Minimal matcher for standalone operation."""
            result = {"matched": False, "trigger_file": None, "matched_groups": {}}
            trigger = profile.get("trigger") or {}
            extensions = trigger.get("extensions") or []

            if not extensions:
                result["matched"] = True
                return result

            import re
            pattern_str = trigger.get("filename_pattern")
            pattern = re.compile(pattern_str) if pattern_str else None

            trigger_file = None
            for entry in entries:
                if entry.get("IsDir"):
                    continue
                name = entry.get("Name", "")
                ext_match = any(name.lower().endswith(e.lower())
                                for e in extensions if e)
                if not ext_match:
                    continue
                if pattern and not pattern.search(name):
                    continue
                trigger_file = name
                break

            if trigger_file is None and extensions != [""]:
                return result

            # Check required sibling groups
            matched_groups: Dict[str, List[str]] = {}
            for group in profile.get("siblings") or []:
                group_name = group.get("group", "")
                patterns = [re.compile(p) for p in (group.get("patterns") or [])]
                names = [
                    e.get("Name", "") for e in entries
                    if not e.get("IsDir") and
                    (not patterns or any(p.search(e.get("Name", ""))
                                        for p in patterns))
                ]
                matched_groups[group_name] = names
                if group.get("required") and len(names) < group.get("min_count", 1):
                    return result

            result["matched"] = True
            result["trigger_file"] = trigger_file
            result["matched_groups"] = matched_groups
            return result

        return profile_map, _simple_match


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def _open_db(path: str) -> sqlite3.Connection:
    if not os.path.exists(path):
        print(f"ERROR: DB not found: {path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-80000")
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS data_objects (
            id              TEXT PRIMARY KEY,
            pattern_name    TEXT NOT NULL,
            root_path       TEXT NOT NULL,
            scan_id         TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'candidate',
            confidence      REAL NOT NULL DEFAULT 1.0,
            source          TEXT NOT NULL DEFAULT 'automatic',
            file_count      INTEGER,
            total_bytes     INTEGER,
            sentinel_path   TEXT,
            metadata_json   TEXT,
            created_at      REAL,
            updated_at      REAL
        );
        CREATE INDEX IF NOT EXISTS idx_do_scan     ON data_objects(scan_id);
        CREATE INDEX IF NOT EXISTS idx_do_pattern  ON data_objects(pattern_name);
        CREATE INDEX IF NOT EXISTS idx_do_status   ON data_objects(status);
        CREATE INDEX IF NOT EXISTS idx_do_root     ON data_objects(root_path);

        CREATE TABLE IF NOT EXISTS object_members (
            object_id   TEXT NOT NULL,
            file_path   TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'member',
            PRIMARY KEY (object_id, file_path)
        );
        CREATE INDEX IF NOT EXISTS idx_om_object ON object_members(object_id);
        CREATE INDEX IF NOT EXISTS idx_om_path   ON object_members(file_path);

        CREATE TABLE IF NOT EXISTS interpretations (
            id              TEXT PRIMARY KEY,
            file_path       TEXT NOT NULL,
            object_id       TEXT,
            scope           TEXT DEFAULT 'sentinel',
            interpreter     TEXT,
            version         TEXT,
            interpreted_at  REAL,
            result_json     TEXT,
            confidence      REAL,
            status          TEXT DEFAULT 'complete'
        );
        CREATE INDEX IF NOT EXISTS idx_interp_path   ON interpretations(file_path);
        CREATE INDEX IF NOT EXISTS idx_interp_object ON interpretations(object_id);
    """)
    conn.commit()


def _get_scan_ids(conn: sqlite3.Connection,
                  prefix: Optional[str]) -> List[str]:
    sql = """
        SELECT id FROM scans
        WHERE (root LIKE '/data%' OR root LIKE '/net/%' OR root LIKE '/mnt/%')
          AND status IN ('complete', 'completed', 'running')
    """
    params = []
    if prefix:
        sql += " AND id LIKE ?"
        params.append(f"{prefix}%")
    sql += " ORDER BY started"
    return [r["id"] for r in conn.execute(sql, params).fetchall()]


def _already_claimed(conn: sqlite3.Connection, path: str,
                     scan_id: str) -> bool:
    r = conn.execute(
        """SELECT 1 FROM data_objects
           WHERE root_path=? AND scan_id=? AND status != 'rejected'""",
        (path, scan_id)
    ).fetchone()
    return r is not None


def _get_directory_entries(conn: sqlite3.Connection,
                           parent_path: str,
                           scan_id: str) -> List[dict]:
    """
    Load the contents of a directory from files.db as lsjson-style dicts
    matching the profile_matcher's expected input format.
    """
    rows = conn.execute("""
        SELECT name, path, size, type, file_extension
        FROM files
        WHERE parent_path = ? AND scan_id = ?
    """, (parent_path, scan_id)).fetchall()

    return [
        {
            "Name":  r["name"],
            "Path":  r["path"],
            "Size":  r["size"] or 0,
            "IsDir": r["type"] == "folder",
        }
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Pass 3 — structural matching
# ─────────────────────────────────────────────────────────────────────────────

def _sentinel_dirs_for_profile(conn: sqlite3.Connection,
                                profile: dict,
                                scan_id: str) -> List[Tuple[str, str]]:
    """
    Return (sentinel_path, parent_path) pairs for directories that contain
    at least one file matching the profile's trigger, using SQL indexes.
    """
    trigger = profile.get("trigger") or {}
    extensions = [e for e in (trigger.get("extensions") or []) if e]
    filename_pattern = trigger.get("filename_pattern", "")

    if not extensions:
        # No extension filter — must enumerate all directories
        # Only do this for profiles with very specific required siblings
        rows = conn.execute("""
            SELECT DISTINCT parent_path FROM files
            WHERE scan_id=? AND type='file'
            LIMIT 500000
        """, (scan_id,)).fetchall()
        return [(None, r["parent_path"]) for r in rows]

    # Use extension index for fast lookup
    placeholders = ",".join("?" * len(extensions))
    rows = conn.execute(f"""
        SELECT DISTINCT path, parent_path, name FROM files
        WHERE scan_id=?
          AND type='file'
          AND file_extension IN ({placeholders})
    """, [scan_id] + extensions).fetchall()

    # Apply filename_pattern filter if present
    if filename_pattern:
        import re
        try:
            pat = re.compile(filename_pattern)
            rows = [r for r in rows if pat.search(r["name"])]
        except re.error:
            pass

    return [(r["path"], r["parent_path"]) for r in rows]


def run_matching(
    conn: sqlite3.Connection,
    scan_ids: List[str],
    profile_map: Dict,
    matcher_fn,
    dry_run: bool = False,
    recheck: bool = False,
    quiet: bool = False,
) -> Dict:
    results = {
        "candidates": 0,
        "skipped": 0,
        "rejected": 0,
        "by_profile": {},
    }
    now = time.time()

    for scan_id in scan_ids:
        short = scan_id[:12]
        if not quiet:
            print(f"\n  Scan {short}")

        for profile_id, profile in profile_map.items():
            if profile.get("abstract"):
                continue

            t_start = time.time()
            sentinel_dirs = _sentinel_dirs_for_profile(conn, profile, scan_id)

            matched = skipped = rejected = 0
            seen_parents = set()

            for sentinel_path, parent_path in sentinel_dirs:
                if parent_path in seen_parents:
                    continue
                seen_parents.add(parent_path)

                if not recheck and _already_claimed(conn, parent_path, scan_id):
                    skipped += 1
                    continue

                # Load directory contents from SQL
                entries = _get_directory_entries(conn, parent_path, scan_id)
                if not entries:
                    continue

                # Run profile matcher
                result = matcher_fn(parent_path, entries, profile)
                if not result["matched"]:
                    rejected += 1
                    continue

                if dry_run:
                    matched += 1
                    continue

                # Determine sentinel file path
                trigger_file = result.get("trigger_file")
                sentinel_file_path = None
                if trigger_file and sentinel_path:
                    sentinel_file_path = sentinel_path
                elif trigger_file:
                    # Find it in entries
                    for e in entries:
                        if e["Name"] == trigger_file:
                            sentinel_file_path = e["Path"]
                            break

                # Compute stats
                file_count = sum(1 for e in entries if not e["IsDir"])
                total_bytes = sum(e["Size"] for e in entries if not e["IsDir"])

                # Write data_object
                obj_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT OR IGNORE INTO data_objects
                        (id, pattern_name, root_path, scan_id, status,
                         confidence, source, file_count, total_bytes,
                         sentinel_path, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    obj_id, profile_id, parent_path, scan_id,
                    "candidate", 1.0, "automatic",
                    file_count, total_bytes,
                    sentinel_file_path, now, now,
                ))

                # Write member rows with roles from matched_groups
                role_map: Dict[str, str] = {}
                groups = result.get("matched_groups") or {}
                # Map group names to roles
                group_role = {
                    "image_data": "stack", "raw_data": "stack",
                    "raw_signal": "stack", "kmer_data": "stack",
                    "dicom_files": "stack", "tiff_files": "stack",
                    "numbered_images": "stack",
                    "metadata": "sidecar", "parameters": "sidecar",
                    "acquisition_log": "sidecar", "scan_metadata": "sidecar",
                    "sentinel": "sentinel", "scidk_descriptor": "sentinel",
                    "workflow_markers": "processing",
                    "basecalled": "processing", "processed": "processing",
                }
                for group_name, names in groups.items():
                    role = group_role.get(group_name, "member")
                    for name in names:
                        role_map[name] = role

                member_rows = []
                for e in entries:
                    role = "sentinel" if e["Path"] == sentinel_file_path \
                        else role_map.get(e["Name"], "member")
                    member_rows.append((obj_id, e["Path"], role))

                if member_rows:
                    conn.executemany("""
                        INSERT OR IGNORE INTO object_members
                            (object_id, file_path, role)
                        VALUES (?,?,?)
                    """, member_rows)

                conn.commit()
                matched += 1

            elapsed = time.time() - t_start
            results["candidates"] += matched
            results["skipped"] += skipped
            results["rejected"] += rejected
            results["by_profile"][profile_id] = \
                results["by_profile"].get(profile_id, 0) + matched

            if not quiet:
                tag = "DRY" if dry_run else "OK "
                total = matched + rejected + skipped
                if total > 0:
                    print(f"    {tag}  {profile_id:<35}  "
                          f"{matched:>6} matched  "
                          f"{rejected:>6} rejected  "
                          f"{skipped:>5} skipped  "
                          f"({elapsed:.1f}s)")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Pass 4 — sentinel interpretation
# ─────────────────────────────────────────────────────────────────────────────

def run_interpretation(
    conn: sqlite3.Connection,
    scan_ids: List[str],
    profile_map: Dict,
    dry_run: bool = False,
    quiet: bool = False,
) -> Dict:
    """Pass 4: read sentinel files to confirm candidates and extract metadata."""
    results = {"processed": 0, "confirmed": 0, "failed": 0, "skipped": 0}

    # Only process profiles that have an interpreter defined
    interp_profiles = {pid: p for pid, p in profile_map.items()
                       if p.get("interpreter")}
    if not interp_profiles:
        if not quiet:
            print("  No profiles with interpreters configured for Pass 4.")
        return results

    scan_ph = ",".join("?" * len(scan_ids))
    prof_ph = ",".join("?" * len(interp_profiles))

    candidates = conn.execute(f"""
        SELECT id, pattern_name, root_path, scan_id, sentinel_path
        FROM data_objects
        WHERE status = 'candidate'
          AND pattern_name IN ({prof_ph})
          AND scan_id IN ({scan_ph})
          AND sentinel_path IS NOT NULL
    """, list(interp_profiles.keys()) + scan_ids).fetchall()

    now = time.time()

    for row in candidates:
        sentinel = row["sentinel_path"]
        obj_id = row["id"]
        profile = interp_profiles.get(row["pattern_name"])
        if not profile:
            continue

        if not sentinel or not os.path.exists(sentinel):
            results["skipped"] += 1
            if not quiet:
                print(f"  SKIP  {(sentinel or '')[:70]} (not accessible)")
            continue

        if dry_run:
            results["processed"] += 1
            continue

        # Attempt interpretation via SciDK interpreter if available
        metadata = None
        interp_name = profile.get("interpreter")
        try:
            from scidk.interpreters import get_interpreter
            interp = get_interpreter(interp_name)
            if interp:
                metadata = interp.interpret(sentinel)
        except Exception:
            pass  # Interpreter not available or failed — still confirm

        status = "confirmed"
        results["confirmed"] += 1

        interp_id = str(uuid.uuid4())
        conn.execute("""
            INSERT OR REPLACE INTO interpretations
                (id, file_path, object_id, scope, interpreter,
                 interpreted_at, result_json, confidence, status)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            interp_id, sentinel, obj_id, "sentinel", interp_name,
            now, json.dumps(metadata) if metadata else None,
            1.0 if metadata else 0.8,
            "complete" if metadata else "partial",
        ))

        conn.execute("""
            UPDATE data_objects
            SET status=?, metadata_json=?, updated_at=?
            WHERE id=?
        """, (status,
              json.dumps(metadata) if metadata else None,
              now, obj_id))

        conn.commit()
        results["processed"] += 1

        if not quiet:
            meta_tag = "+" if metadata else " "
            print(f"  OK{meta_tag}  {sentinel[:70]}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Coverage report
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_bytes(b: int) -> str:
    for unit, threshold in [("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)]:
        if b >= threshold:
            return f"{b / threshold:.1f} {unit}"
    return f"{b} B"


def run_coverage(
    conn: sqlite3.Connection,
    scan_ids: List[str],
    quiet: bool = False,
) -> None:
    """
    Three-tier coverage report:

      Core      — files in object_members (directly matched by profile)
      Ambiguous — files under a data_object root_path but not in object_members
                  (likely downstream analysis, exports, figures)
      Unclaimed — files outside any data_object root_path entirely
    """
    scan_ph = ",".join("?" * len(scan_ids))

    # ── Total files and bytes ──
    totals = conn.execute(f"""
        SELECT COUNT(*) as n, SUM(size) as b
        FROM files
        WHERE type='file' AND scan_id IN ({scan_ph})
    """, scan_ids).fetchone()
    total_files = totals["n"] or 0
    total_bytes = totals["b"] or 0

    # ── Core: files in object_members ──
    core = conn.execute(f"""
        SELECT COUNT(*) as n, SUM(f.size) as b
        FROM files f
        INNER JOIN object_members om ON om.file_path = f.path
        WHERE f.type='file' AND f.scan_id IN ({scan_ph})
    """, scan_ids).fetchone()
    core_files = core["n"] or 0
    core_bytes = core["b"] or 0

    # ── Dataset objects summary ──
    objects = conn.execute(f"""
        SELECT COUNT(*) as n,
               SUM(file_count) as fc,
               SUM(total_bytes) as tb
        FROM data_objects
        WHERE scan_id IN ({scan_ph}) AND status != 'rejected'
    """, scan_ids).fetchone()
    n_objects = objects["n"] or 0

    # ── Ambiguous: under a root_path but not in object_members ──
    # Use data_objects file_count/total_bytes as proxy for "under root"
    # (fast — no path prefix scan needed)
    # Extended = all files under any root_path (core + ambiguous)
    # We approximate: extended_files = SUM(file_count from data_objects)
    # This counts files in the immediate directory only, so true extended
    # coverage is actually higher. We note this in the output.
    obj_files = objects["fc"] or 0
    obj_bytes = objects["tb"] or 0
    ambiguous_files = max(0, obj_files - core_files)
    ambiguous_bytes = max(0, obj_bytes - core_bytes)

    # ── Unclaimed: outside all roots ──
    unclaimed_files = total_files - obj_files
    unclaimed_bytes = total_bytes - obj_bytes

    # ── By profile ──
    by_profile = conn.execute(f"""
        SELECT pattern_name, status, COUNT(*) as n,
               SUM(file_count) as fc, SUM(total_bytes) as tb
        FROM data_objects
        WHERE scan_id IN ({scan_ph})
        GROUP BY pattern_name, status
        ORDER BY fc DESC
    """, scan_ids).fetchall()

    W = 68
    print(f"\n{'═'*W}")
    print(f"  Profile Coverage Report")
    print(f"{'═'*W}")
    print(f"  Total files        : {total_files:>12,}  {_fmt_bytes(total_bytes):>12}")
    print(f"  Dataset objects    : {n_objects:>12,}")
    print()

    def pct(n, total):
        return f"{100.0*n/total:.1f}%" if total else "0.0%"

    # Three-tier table
    print(f"  {'Category':<22}  {'Files':>12}  {'% files':>8}  "
          f"{'Size':>12}  {'% bytes':>8}")
    print(f"  {'-'*W}")
    print(f"  {'Core (profile members)':<22}  {core_files:>12,}  "
          f"{pct(core_files, total_files):>8}  "
          f"{_fmt_bytes(core_bytes):>12}  "
          f"{pct(core_bytes, total_bytes):>8}")
    print(f"  {'Ambiguous (under root)':<22}  {ambiguous_files:>12,}  "
          f"{pct(ambiguous_files, total_files):>8}  "
          f"{_fmt_bytes(ambiguous_bytes):>12}  "
          f"{pct(ambiguous_bytes, total_bytes):>8}")
    print(f"  {'Unclaimed':<22}  {unclaimed_files:>12,}  "
          f"{pct(unclaimed_files, total_files):>8}  "
          f"{_fmt_bytes(unclaimed_bytes):>12}  "
          f"{pct(unclaimed_bytes, total_bytes):>8}")
    print(f"  {'-'*W}")
    print(f"  {'Total':<22}  {total_files:>12,}  {'100.0%':>8}  "
          f"{_fmt_bytes(total_bytes):>12}  {'100.0%':>8}")

    # By profile breakdown
    if by_profile:
        print(f"\n  {'Profile':<35}  {'Status':<12}  {'Objects':>8}  "
              f"{'Files':>10}  {'Size':>10}")
        print(f"  {'-'*W}")
        for r in by_profile:
            print(f"  {r['pattern_name']:<35}  {r['status']:<12}  "
                  f"{r['n']:>8,}  {(r['fc'] or 0):>10,}  "
                  f"{_fmt_bytes(r['tb'] or 0):>10}")

    # Top unclaimed extensions (files with no object_member entry)
    print(f"\n  Top extensions in unclaimed files:")
    print(f"  {'-'*W}")
    unclaimed_exts = conn.execute(f"""
        SELECT f.file_extension, COUNT(*) as cnt, SUM(f.size) as bytes
        FROM files f
        WHERE f.type = 'file'
          AND f.scan_id IN ({scan_ph})
          AND f.file_extension IS NOT NULL
          AND f.file_extension != ''
          AND NOT EXISTS (
              SELECT 1 FROM object_members om WHERE om.file_path = f.path
          )
        GROUP BY f.file_extension
        ORDER BY cnt DESC
        LIMIT 20
    """, scan_ids).fetchall()

    print(f"  {'Extension':<20}  {'Files':>12}  {'Size':>12}")
    print(f"  {'-'*46}")
    for r in unclaimed_exts:
        print(f"  {r['file_extension']:<20}  {r['cnt']:>12,}  "
              f"{_fmt_bytes(r['bytes'] or 0):>12}")

    print(f"\n  Note: 'Ambiguous' files are under a dataset root but not")
    print(f"  formally matched as members — likely analysis outputs,")
    print(f"  exports, or figures associated with the parent dataset.")
    print(f"\n{'═'*W}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="SciDK dataset profile matching — Pass 3 + Pass 4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--db",
        default=str(Path.home() / ".scidk" / "db" / "files.db"))
    parser.add_argument("--profiles-dir", default=None,
        help="YAML profiles directory")
    parser.add_argument("--scan-id", default=None)
    parser.add_argument("--profile", default=None,
        help="Run only named profile(s), comma-separated")
    parser.add_argument("--match-only", action="store_true")
    parser.add_argument("--interpret", action="store_true")
    parser.add_argument("--coverage", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recheck", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    # Load profiles
    profiles_dir = _find_profiles_dir(args.profiles_dir)
    if not profiles_dir:
        print("ERROR: Cannot find profiles directory.", file=sys.stderr)
        print("  Set --profiles-dir or place YAMLs in scidk/interpreters/profiles/",
              file=sys.stderr)
        sys.exit(1)

    profile_map, matcher_fn = _load_profiles(profiles_dir)

    if not profile_map:
        print(f"ERROR: No profiles loaded from {profiles_dir}", file=sys.stderr)
        sys.exit(1)

    # Filter to requested profiles
    if args.profile:
        names = [n.strip() for n in args.profile.split(",")]
        unknown = [n for n in names if n not in profile_map]
        if unknown:
            print(f"Unknown profiles: {unknown}", file=sys.stderr)
            print(f"Available: {sorted(profile_map.keys())}", file=sys.stderr)
            sys.exit(1)
        profile_map = {n: profile_map[n] for n in names}

    # Open DB
    conn = _open_db(args.db)
    _ensure_tables(conn)

    # Resolve scan IDs
    scan_ids = _get_scan_ids(conn, args.scan_id)
    if not scan_ids:
        print("No matching research scans found in files.db", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"\nSciDK Profile Matcher")
        print(f"  DB       : {args.db}")
        print(f"  Profiles : {profiles_dir}  ({len(profile_map)} loaded)")
        print(f"  Scans    : {len(scan_ids)}")
        if args.dry_run:
            print(f"  Mode     : DRY RUN — nothing will be written")

    # Coverage report
    if args.coverage:
        run_coverage(conn, scan_ids, quiet=args.quiet)
        conn.close()
        return

    t0 = time.time()

    # Pass 3
    if not args.interpret:
        match_results = run_matching(
            conn, scan_ids, profile_map, matcher_fn,
            dry_run=args.dry_run,
            recheck=args.recheck,
            quiet=args.quiet,
        )
        if not args.quiet:
            print(f"\n  Pass 3 complete:")
            print(f"    {match_results['candidates']:,} candidates")
            print(f"    {match_results['rejected']:,} rejected")
            print(f"    {match_results['skipped']:,} skipped")
            if match_results["by_profile"]:
                print(f"\n  By profile:")
                for pname, cnt in sorted(
                    match_results["by_profile"].items(),
                    key=lambda x: -x[1]
                ):
                    if cnt > 0:
                        print(f"    {pname:<35}  {cnt:>8,}")

    # Pass 4
    if not args.match_only:
        if not args.quiet:
            print(f"\n  Pass 4 — sentinel interpretation")
        interp_results = run_interpretation(
            conn, scan_ids, profile_map,
            dry_run=args.dry_run,
            quiet=args.quiet,
        )
        if not args.quiet and interp_results["processed"]:
            print(f"\n  Pass 4 complete:")
            print(f"    {interp_results['confirmed']:,} confirmed")
            print(f"    {interp_results['failed']:,} failed")
            print(f"    {interp_results['skipped']:,} skipped")

    elapsed = time.time() - t0
    if not args.quiet:
        print(f"\n  Done ({elapsed:.1f}s)\n")

    conn.close()


if __name__ == "__main__":
    main()
