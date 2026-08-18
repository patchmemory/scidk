"""Pure matching logic for dataset profiles.

Given a profile dict and a list of lsjson-style entries for a single directory,
decide whether the directory matches the profile. No I/O — callers supply the
already-enumerated entries.

Each entry is a dict shaped like rclone ``lsjson`` output::

    {"Name": "img001.tif", "Path": "scan/img001.tif", "Size": 1024, "IsDir": false}

TODO (deferred, see docs/interpreter-match-profiles.md):
  - confidence scoring
  - template substitution in graph properties
  - size constraints on trigger/sibling matches
  - directory ``name_pattern`` triggers
  - ``child_profiles`` composition
  - inheritance chain validation (merging parent trigger/siblings)
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional


def _entry_name(entry: dict) -> str:
    return entry.get("Name") or entry.get("Path") or ""


def _is_dir(entry: dict) -> bool:
    return bool(entry.get("IsDir"))


def _matches_extensions(name: str, extensions: List[str]) -> bool:
    lname = name.lower()
    return any(lname.endswith(ext.lower()) for ext in extensions)


def match(dir_path: str, entries: List[dict], profile: dict) -> dict:
    """Match a directory's entries against a profile.

    Returns ``{matched: bool, trigger_file: str|None, matched_groups: dict}``
    where ``matched_groups`` maps each satisfied sibling group name to the list
    of entry names that matched it.
    """
    result = {"matched": False, "trigger_file": None, "matched_groups": {}}

    trigger = profile.get("trigger") or {}
    extensions = trigger.get("extensions") or []
    filename_pattern = trigger.get("filename_pattern")

    # 1. Empty trigger extensions — match any directory (file_collection base case).
    if not extensions:
        result["matched"] = True
        # Still record any sibling groups that happen to be satisfied.
        result["matched_groups"] = _match_sibling_groups(entries, profile)
        return result

    # 2. Trigger check — at least one entry matches both extension and pattern.
    pattern = re.compile(filename_pattern) if filename_pattern else None
    trigger_file: Optional[str] = None
    for entry in entries:
        if _is_dir(entry):
            continue
        name = _entry_name(entry)
        if not _matches_extensions(name, extensions):
            continue
        if pattern is not None and not pattern.search(name):
            continue
        trigger_file = name
        break

    if trigger_file is None:
        return result  # no trigger found -> not matched

    # 3. Required sibling groups.
    matched_groups = _match_sibling_groups(entries, profile)
    for group in profile.get("siblings") or []:
        if not group.get("required"):
            continue
        group_name = group.get("group")
        min_count = group.get("min_count", 1)
        count = len(matched_groups.get(group_name, []))
        if count < min_count:
            return result  # a required group is unsatisfied -> not matched

    # 4. Trigger found AND all required groups satisfied.
    result["matched"] = True
    result["trigger_file"] = trigger_file
    result["matched_groups"] = matched_groups
    return result


def _match_sibling_groups(entries: List[dict], profile: dict) -> Dict[str, List[str]]:
    """For each sibling group, collect the entry names matching any of its patterns."""
    matched_groups: Dict[str, List[str]] = {}
    for group in profile.get("siblings") or []:
        group_name = group.get("group")
        if not group_name:
            continue
        group_type = group.get("type", "file")
        patterns = [re.compile(p) for p in (group.get("patterns") or [])]

        names: List[str] = []
        for entry in entries:
            is_dir = _is_dir(entry)
            if group_type == "file" and is_dir:
                continue
            if group_type == "dir" and not is_dir:
                continue
            name = _entry_name(entry)
            if patterns and not any(p.search(name) for p in patterns):
                continue
            names.append(name)
        matched_groups[group_name] = names
    return matched_groups
