"""Deployment configuration for the SharePoint Intake plugin.

Where to find the list — and nothing about what is in it. Field mappings,
controlled vocabularies, node labels, and relationship types are *not* here: they
live in a mapping config JSON under ``configs/`` and are applied by
:mod:`scidk.pipeline`. ``configs/aipt_intake_mapping.json`` is the reference
mapping for the AIPT deployment.

Runtime values follow the standard SciDK precedence: persisted setting, then
environment variable, then default.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Settings keys (read via scidk.core.settings.get_setting, with env fallback).
# ---------------------------------------------------------------------------

#: rclone path (or local path) to the SharePoint list export.
SETTING_SYNC_REMOTE = "sharepoint_intake_sync_remote"

#: rclone path to the controlled-vocabulary list. Read by the Pipeline's
#: vocabulary check, not by the plugin — the plugin does not validate values.
SETTING_VOCAB_PATH = "sharepoint_intake_vocab_path"

ENV_SYNC_REMOTE = "SCIDK_SHAREPOINT_INTAKE_SYNC_REMOTE"
ENV_VOCAB_PATH = "SCIDK_SHAREPOINT_INTAKE_VOCAB_PATH"

#: Directory holding this plugin's mapping configs.
MAPPING_CONFIG_DIR = Path(__file__).resolve().parent / "configs"

#: Reference mapping for the AIPT deployment.
REFERENCE_MAPPING = "aipt_intake_mapping.json"


def get_config_value(setting_key: str, env_key: str, default: Optional[str] = None) -> Optional[str]:
    """Resolve a config value: SQLite setting first, then env var, then default.

    Mirrors the established SciDK precedence (persisted settings override env).
    Safe to call outside a Flask app context.
    """
    try:
        from scidk.core.settings import get_setting

        val = get_setting(setting_key)
        if val:
            return val
    except Exception:  # noqa: BLE001 - settings DB is optional (CLI / tests)
        pass
    return os.environ.get(env_key, default)


def mapping_config_path(name: str = REFERENCE_MAPPING) -> Path:
    """Absolute path to a mapping config shipped with this plugin.

    Returns the path only. Reading and interpreting a mapping config is the
    Pipeline's job — the plugin never parses one.
    """
    return MAPPING_CONFIG_DIR / name
