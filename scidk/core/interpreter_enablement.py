"""Interpreter enablement logic for computing which interpreters should be active.

This module handles the complex precedence rules:
1. CLI environment variables (SCIDK_ENABLE_INTERPRETERS, SCIDK_DISABLE_INTERPRETERS)
2. Global saved settings (from InterpreterSettings database)
3. Interpreter defaults (default_enabled attribute)
"""

import os
from pathlib import Path
from typing import Set, Tuple, Dict, Any, Optional


def compute_enabled_interpreters(
    registry,
    app_extensions: Dict[str, Any]
) -> Tuple[Set[str], str, Optional[Any]]:
    """Compute effective interpreter enablement with CLI > settings > defaults precedence.

    Args:
        registry: InterpreterRegistry instance with by_id dict
        app_extensions: app.extensions dict for storing unknown_env warnings

    Returns:
        tuple: (enabled_set, source, settings_instance)
        - enabled_set: Set of interpreter IDs that should be enabled
        - source: 'cli' | 'global' | 'default' (where the config came from)
        - settings_instance: InterpreterSettings object or None
    """
    # Check if we're in testing environment (disable persistent settings)
    testing_env = bool(os.environ.get('PYTEST_CURRENT_TEST')) or bool(os.environ.get('SCIDK_DISABLE_SETTINGS'))

    # Load settings instance (unless testing)
    settings = None
    if not testing_env:
        try:
            from .settings import InterpreterSettings
            settings = InterpreterSettings(db_path=str(Path(os.getcwd()) / 'scidk_settings.db'))
        except Exception:
            settings = None

    # Compute defaults from interpreter attributes (fallback True)
    all_ids = list(registry.by_id.keys())
    default_enabled_ids = set([
        iid for iid in all_ids
        if bool(getattr(registry.by_id[iid], 'default_enabled', True))
    ])

    # Parse CLI overrides (case-insensitive)
    en_raw = [s.strip() for s in (os.environ.get('SCIDK_ENABLE_INTERPRETERS') or '').split(',') if s.strip()]
    dis_raw = [s.strip() for s in (os.environ.get('SCIDK_DISABLE_INTERPRETERS') or '').split(',') if s.strip()]
    en_list = [s.lower() for s in en_raw]
    dis_list = [s.lower() for s in dis_raw]

    source = 'default'

    if en_list or dis_list:
        # CLI overrides present
        known_ids = set(all_ids)
        unknown_en = [x for x in en_list if x not in known_ids]
        unknown_dis = [x for x in dis_list if x not in known_ids]

        # Start from defaults; remove DISABLE; add ENABLE; ENABLE wins on conflicts
        enabled_set = set(default_enabled_ids)
        for d in dis_list:
            if d in known_ids:
                enabled_set.discard(d)
        for e in en_list:
            if e in known_ids:
                enabled_set.add(e)

        source = 'cli'

        # Store unknown IDs for /api/interpreters to warn about
        # Do NOT persist CLI-derived sets to settings to avoid masking user intentions
        try:
            _ist = app_extensions.setdefault('scidk', {}).setdefault('interpreters', {})
            _ist['unknown_env'] = {'enable': unknown_en, 'disable': unknown_dis}
        except Exception:
            pass
    else:
        # No CLI overrides; try loading from saved settings
        loaded = set()
        try:
            if settings:
                loaded = set(settings.load_enabled_interpreters())
        except Exception:
            loaded = set()

        if loaded:
            enabled_set = set(loaded)
            source = 'global'
        else:
            enabled_set = set(default_enabled_ids)
            source = 'default'

    # Apply to registry
    try:
        registry.enabled_interpreters = set(enabled_set)
    except Exception:
        pass

    return enabled_set, source, settings
