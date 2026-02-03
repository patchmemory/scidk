"""Channel-based feature flag defaults configuration.

This module applies channel-based defaults (stable, dev, beta) for feature flags
when environment variables are not explicitly set. It also handles soft-disabling
of rclone provider when the binary is not available.
"""

import os
import shutil


def apply_channel_defaults():
    """Apply channel-based defaults for feature flags when unset.

    Channels: stable (default), dev, beta.
    Explicit env values always win; we only set defaults if unset.

    Also soft-disable rclone provider by removing it from SCIDK_PROVIDERS
    if rclone binary is missing, unless SCIDK_FORCE_RCLONE is truthy.
    Only perform soft-disable when SCIDK_PROVIDERS was not explicitly set by user.
    """
    ch = (os.environ.get('SCIDK_CHANNEL') or 'stable').strip().lower()
    had_prov_env = 'SCIDK_PROVIDERS' in os.environ

    def setdefault_env(name: str, value: str):
        """Set environment variable only if not already set."""
        if os.environ.get(name) is None:
            os.environ[name] = value

    if ch in ('dev', 'beta'):
        # Providers default: include rclone
        if os.environ.get('SCIDK_PROVIDERS') is None:
            os.environ['SCIDK_PROVIDERS'] = 'local_fs,mounted_fs,rclone'

        # Mounts UI
        setdefault_env('SCIDK_RCLONE_MOUNTS', '1')

        # Files viewer mode
        setdefault_env('SCIDK_FILES_VIEWER', 'rocrate')

        # File index work in progress
        setdefault_env('SCIDK_FEATURE_FILE_INDEX', '1')

    # Soft rclone detection: remove if missing and not forced,
    # but only when we set providers implicitly
    if not had_prov_env:
        prov_env = os.environ.get('SCIDK_PROVIDERS')
        if prov_env:
            prov_list = [p.strip() for p in prov_env.split(',') if p.strip()]
            if 'rclone' in prov_list and not shutil.which('rclone'):
                force = (os.environ.get('SCIDK_FORCE_RCLONE') or '').strip().lower() in (
                    '1', 'true', 'yes', 'y', 'on'
                )
                if not force:
                    prov_list = [p for p in prov_list if p != 'rclone']
                    os.environ['SCIDK_PROVIDERS'] = ','.join(prov_list)

    # Record effective channel for UI/debug
    os.environ.setdefault('SCIDK_CHANNEL', ch or 'stable')

    # Default: commit to graph should read from index unless explicitly disabled
    if os.environ.get('SCIDK_COMMIT_FROM_INDEX') is None:
        os.environ['SCIDK_COMMIT_FROM_INDEX'] = '1'
