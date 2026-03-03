import sqlite3
import json
from datetime import datetime
from typing import Set, Dict, Optional
import os
import base64


class InterpreterSettings:
    """Minimal settings persistence for interpreter toggles using SQLite.
    If DB is unavailable, caller can ignore persistence errors.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = sqlite3.connect(db_path)
        self.db.execute('PRAGMA journal_mode=WAL;')
        self.init_tables()

    def init_tables(self):
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS interpreter_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.db.commit()

    def save_enabled_interpreters(self, enabled_set: Set[str]):
        payload = json.dumps(sorted(list(enabled_set)))
        from datetime import timezone
        now = datetime.now(tz=timezone.utc).isoformat()
        self.db.execute(
            "INSERT OR REPLACE INTO interpreter_settings(key, value, updated_at) VALUES (?, ?, ?)",
            ("enabled_interpreters", payload, now),
        )
        self.db.commit()

    def load_enabled_interpreters(self) -> Set[str]:
        try:
            cur = self.db.execute(
                "SELECT value FROM interpreter_settings WHERE key = 'enabled_interpreters'"
            )
            row = cur.fetchone()
            if row and row[0]:
                data = json.loads(row[0])
                return set(data)
        except Exception:
            return set()
        return set()


# Global settings helpers (use same table as InterpreterSettings)
def _get_db_path() -> str:
    """Get path to settings database."""
    return os.environ.get('SCIDK_DB_PATH', os.path.join(os.getcwd(), 'scidk.db'))


# ========== Password Encryption Helpers ==========

_encryption_key_cache = None

def _get_encryption_key() -> bytes:
    """Get or generate encryption key for password storage.

    Priority:
    1. SCIDK_SECRET_KEY environment variable
    2. Key stored in database under '_encryption_key'
    3. Generate new key and store in database

    Returns:
        32-byte encryption key for Fernet
    """
    global _encryption_key_cache

    if _encryption_key_cache is not None:
        return _encryption_key_cache

    # Try environment variable first
    env_key = os.environ.get('SCIDK_SECRET_KEY', '').strip()
    if env_key:
        try:
            # Expect base64-encoded key
            key = base64.urlsafe_b64decode(env_key)
            if len(key) == 32:
                _encryption_key_cache = key
                return key
        except Exception:
            pass

    # Try loading from database
    try:
        db_path = _get_db_path()
        db = sqlite3.connect(db_path)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS interpreter_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur = db.execute("SELECT value FROM interpreter_settings WHERE key = '_encryption_key'")
        row = cur.fetchone()
        if row and row[0]:
            key = base64.urlsafe_b64decode(row[0])
            if len(key) == 32:
                _encryption_key_cache = key
                db.close()
                return key
    except Exception:
        pass

    # Generate new key and store it
    try:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()  # Returns 32-byte key

        # Store in database
        db_path = _get_db_path()
        db = sqlite3.connect(db_path)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS interpreter_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        from datetime import timezone
        now = datetime.now(tz=timezone.utc).isoformat()
        db.execute(
            "INSERT OR REPLACE INTO interpreter_settings(key, value, updated_at) VALUES (?, ?, ?)",
            ("_encryption_key", base64.urlsafe_b64encode(key).decode('ascii'), now),
        )
        db.commit()
        db.close()

        _encryption_key_cache = key
        return key
    except Exception as e:
        # Fallback: return a deterministic key based on db path (not ideal but better than nothing)
        import hashlib
        fallback = hashlib.sha256(f"scidk-fallback-{_get_db_path()}".encode()).digest()
        _encryption_key_cache = fallback
        return fallback


def _is_encrypted(value: str) -> bool:
    """Check if a value is already encrypted (Fernet token format).

    Fernet tokens are base64-encoded and start with a version byte.

    Args:
        value: String to check

    Returns:
        True if value appears to be a Fernet token
    """
    if not value:
        return False

    try:
        # Fernet tokens are base64-encoded with specific format
        # They start with version byte (0x80) and have minimum length
        decoded = base64.urlsafe_b64decode(value)
        # Fernet tokens are at least 57 bytes
        if len(decoded) >= 57 and decoded[0] == 0x80:
            return True
    except Exception:
        pass

    return False


def _encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext value using Fernet symmetric encryption.

    Args:
        plaintext: String to encrypt

    Returns:
        Base64-encoded encrypted token
    """
    if not plaintext:
        return plaintext

    try:
        from cryptography.fernet import Fernet
        key = _get_encryption_key()
        f = Fernet(key)
        encrypted = f.encrypt(plaintext.encode('utf-8'))
        return encrypted.decode('ascii')
    except Exception as e:
        # Log but don't fail - return plaintext as fallback
        # In production, this should log to proper logger
        import sys
        print(f"Warning: Failed to encrypt value: {e}", file=sys.stderr)
        return plaintext


def _decrypt_value(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted value.

    Args:
        encrypted: Base64-encoded Fernet token

    Returns:
        Decrypted plaintext string
    """
    if not encrypted:
        return encrypted

    # If not encrypted, return as-is
    if not _is_encrypted(encrypted):
        return encrypted

    try:
        from cryptography.fernet import Fernet
        key = _get_encryption_key()
        f = Fernet(key)
        decrypted = f.decrypt(encrypted.encode('ascii'))
        return decrypted.decode('utf-8')
    except Exception as e:
        # Log but return original - might be corrupt or wrong key
        import sys
        print(f"Warning: Failed to decrypt value: {e}", file=sys.stderr)
        return encrypted


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a setting value from the database.

    Auto-decrypts values for password keys. Handles migration from plaintext
    to encrypted passwords transparently.

    Args:
        key: Setting key
        default: Default value if key not found

    Returns:
        Setting value (decrypted if password key), or default if not found
    """
    try:
        db_path = _get_db_path()
        db = sqlite3.connect(db_path)
        cur = db.execute(
            "SELECT value FROM interpreter_settings WHERE key = ?",
            (key,)
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            value = row[0]

            # Auto-decrypt password keys
            is_password_key = 'password' in key.lower()
            if is_password_key and value:
                # Check if already encrypted
                if _is_encrypted(value):
                    # Decrypt it
                    value = _decrypt_value(value)
                else:
                    # Migrate: encrypt plaintext password on first read
                    try:
                        encrypted = _encrypt_value(value)
                        from datetime import timezone
                        now = datetime.now(tz=timezone.utc).isoformat()
                        db.execute(
                            "INSERT OR REPLACE INTO interpreter_settings(key, value, updated_at) VALUES (?, ?, ?)",
                            (key, encrypted, now),
                        )
                        db.commit()
                    except Exception as e:
                        # Log warning but continue with plaintext
                        import sys
                        print(f"Warning: Failed to migrate password key {key} to encrypted: {e}", file=sys.stderr)

            db.close()
            return value
    except Exception:
        pass
    return default


def set_setting(key: str, value: str):
    """Set a setting value in the database.

    Auto-encrypts values for password keys before storage.

    Args:
        key: Setting key
        value: Setting value (will be encrypted if password key)
    """
    db_path = _get_db_path()
    db = sqlite3.connect(db_path)
    # Ensure table exists
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS interpreter_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Auto-encrypt password keys
    is_password_key = 'password' in key.lower()
    if is_password_key and value:
        # Only encrypt if not already encrypted
        if not _is_encrypted(value):
            value = _encrypt_value(value)

    from datetime import timezone
    now = datetime.now(tz=timezone.utc).isoformat()
    db.execute(
        "INSERT OR REPLACE INTO interpreter_settings(key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, now),
    )
    db.commit()
    db.close()


def get_settings_by_prefix(prefix: str) -> Dict[str, str]:
    """Get all settings with a given prefix.

    Args:
        prefix: Key prefix to filter by

    Returns:
        Dict mapping keys to values
    """
    try:
        db_path = _get_db_path()
        db = sqlite3.connect(db_path)
        cur = db.execute(
            "SELECT key, value FROM interpreter_settings WHERE key LIKE ?",
            (prefix + '%',)
        )
        results = {row[0]: row[1] for row in cur.fetchall()}
        db.close()
        return results
    except Exception:
        return {}
