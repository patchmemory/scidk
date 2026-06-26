"""Registry for dataset match profiles.

Loads profile YAML files, resolves their `inherits` chains, and computes an
inheritance depth for each (a profile with no parent has depth 0). Profiles are
exposed shallowest-first so that base profiles are considered before the more
specialized ones that inherit from them.

This module performs loading/ordering only — matching logic lives in
``scidk.core.profile_matcher``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class ProfileRegistry:
    def __init__(self) -> None:
        # profile_id -> profile dict (with computed '_depth')
        self._profiles: Dict[str, dict] = {}

    def load(self, profiles_dir: Path) -> None:
        """Load all ``*.yaml`` profiles from ``profiles_dir``.

        Resolves the ``inherits`` chain for each profile and stores the computed
        inheritance depth on the profile under the ``_depth`` key.
        """
        profiles_dir = Path(profiles_dir)
        self._profiles = {}

        if not profiles_dir.exists():
            logger.warning("Profiles directory does not exist: %s", profiles_dir)
            return

        for path in sorted(profiles_dir.glob("*.yaml")):
            try:
                with path.open() as f:
                    data = yaml.safe_load(f)
            except Exception:
                logger.exception("Failed to load profile YAML: %s", path)
                continue

            if not isinstance(data, dict):
                logger.warning("Profile YAML did not parse to a mapping: %s", path)
                continue

            profile_id = data.get("profile_id")
            if not profile_id:
                logger.warning("Profile YAML missing profile_id: %s", path)
                continue

            self._profiles[profile_id] = data

        # Compute inheritance depth for each profile once all are loaded.
        for profile in self._profiles.values():
            profile["_depth"] = self._compute_depth(profile)

    def _compute_depth(self, profile: dict) -> int:
        """Walk the ``inherits`` chain and count parents (no parent = 0)."""
        depth = 0
        seen = set()
        current = profile
        while True:
            parent_id = current.get("inherits")
            if not parent_id:
                break
            if parent_id in seen:
                logger.warning(
                    "Cyclic inherits chain detected at profile_id=%s", parent_id
                )
                break
            seen.add(parent_id)
            parent = self._profiles.get(parent_id)
            if parent is None:
                logger.warning(
                    "Profile %r inherits from unknown profile %r",
                    current.get("profile_id"),
                    parent_id,
                )
                break
            depth += 1
            current = parent
        return depth

    def ordered_profiles(self) -> List[dict]:
        """Return profiles shallowest-first (base profiles before specialized)."""
        return sorted(
            self._profiles.values(),
            key=lambda p: (p.get("_depth", 0), p.get("profile_id", "")),
        )

    def get(self, profile_id: str) -> Optional[dict]:
        return self._profiles.get(profile_id)
