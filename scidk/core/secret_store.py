"""Encryption at rest for per-user secrets (LLM API keys).

The other Fernet users here (alert_manager, plugin_settings) fall back to a key
generated per process when SCIDK_ENCRYPTION_KEY is unset, so anything they
encrypt is unreadable after a restart. Stored API keys can't work that way, so
this module keeps the key in a file beside the settings DB (mode 0600) when the
env var is unset. A copy of the settings DB alone (a backup, an export) holds
only ciphertext.
"""
from __future__ import annotations

import os
import threading
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

_lock = threading.Lock()


def _key_path(settings_db: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(settings_db)), '.scidk_secret.key')


def _fernet(settings_db: str) -> Fernet:
    env = os.environ.get('SCIDK_ENCRYPTION_KEY')
    if env:
        return Fernet(env.encode())
    path = _key_path(settings_db)
    with _lock:
        if not os.path.exists(path):
            key = Fernet.generate_key()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(key)
        with open(path, 'rb') as f:
            return Fernet(f.read().strip())


def encrypt(settings_db: str, plaintext: str) -> str:
    return _fernet(settings_db).encrypt(plaintext.encode()).decode()


def decrypt(settings_db: str, token: Optional[str]) -> Optional[str]:
    """None if there's nothing stored or it can't be decrypted (key changed)."""
    if not token:
        return None
    try:
        return _fernet(settings_db).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def hint(secret: Optional[str]) -> Optional[str]:
    """What the browser may see of a stored key: ``sk-…abcd``."""
    if not secret:
        return None
    head = secret.split('-')[0] + '-' if '-' in secret[:8] else secret[:3]
    return f"{head}…{secret[-4:]}"
