"""Filesystem provider initialization.

This module handles the initialization of all filesystem providers
(local_fs, mounted_fs, rclone) based on environment configuration.
"""

import os


def initialize_fs_providers(app):
    """Initialize and register all filesystem providers.

    Args:
        app: Flask application instance

    Returns:
        FsProviderRegistry with all providers registered
    """
    from ..core.providers import (
        ProviderRegistry as FsProviderRegistry,
        LocalFSProvider,
        MountedFSProvider,
        RcloneProvider
    )

    # Parse enabled providers from environment
    prov_enabled = [
        p.strip()
        for p in (os.environ.get('SCIDK_PROVIDERS', 'local_fs,mounted_fs').split(','))
        if p.strip()
    ]

    # Ensure rclone provider is always available for listremotes validation
    if 'rclone' not in prov_enabled:
        prov_enabled.append('rclone')

    # Create registry with enabled providers
    fs_providers = FsProviderRegistry(enabled=prov_enabled)

    # Initialize and register all providers
    p_local = LocalFSProvider()
    p_local.initialize(app, {})
    fs_providers.register(p_local)

    p_mounted = MountedFSProvider()
    p_mounted.initialize(app, {})
    fs_providers.register(p_mounted)

    p_rclone = RcloneProvider()
    p_rclone.initialize(app, {})
    fs_providers.register(p_rclone)

    return fs_providers
