import os
import shutil

def apply_channel_defaults() -> None:
    """Apply channel-based defaults for feature flags when unset.
    Channels: stable (default), dev, beta.
    Explicit env values always win; we only set defaults if unset.
    Also soft-disable rclone provider by removing it from SCIDK_PROVIDERS if rclone binary is missing,
    unless SCIDK_FORCE_RCLONE is truthy. Only perform soft-disable when SCIDK_PROVIDERS was not explicitly set by user.
    """
    def setdefault_env(name: str, value: str):
        if os.environ.get(name) is None:
            os.environ[name] = value

    channel = (os.environ.get('SCIDK_CHANNEL') or 'stable').strip().lower()

    # Defaults by channel (can be overridden by explicit env)
    if channel == 'dev':
        setdefault_env('SCIDK_FILES_VIEWER', 'rocrate')
        setdefault_env('SCIDK_FEATURE_FILE_INDEX', '1')
        setdefault_env('SCIDK_COMMIT_FROM_INDEX', '1')
        if os.environ.get('SCIDK_PROVIDERS') is None:
            os.environ['SCIDK_PROVIDERS'] = 'local_fs,mounted_fs,rclone'
    elif channel == 'beta':
        setdefault_env('SCIDK_COMMIT_FROM_INDEX', '1')
    else:
        # stable defaults
        setdefault_env('SCIDK_COMMIT_FROM_INDEX', '1')

    # Soft-disable rclone provider if binary missing and providers not explicitly set
    providers_env_explicit = ('SCIDK_PROVIDERS' in os.environ)
    if not providers_env_explicit:
        rclone_exists = shutil.which('rclone') is not None
        prov = [p.strip() for p in (os.environ.get('SCIDK_PROVIDERS', 'local_fs,mounted_fs,rclone').split(',')) if p.strip()]
        if not rclone_exists and 'rclone' in prov and not (os.environ.get('SCIDK_FORCE_RCLONE') or '').strip().lower() in ('1','true','yes','y','on'):
            prov = [p for p in prov if p != 'rclone']
            os.environ['SCIDK_PROVIDERS'] = ','.join(prov)

    # Record effective channel for UI/debug
    os.environ.setdefault('SCIDK_CHANNEL', channel or 'stable')
