"""Symmetric encryption for secrets stored in the database (IMAP passwords, etc.)."""

import base64
import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key = os.environ.get("IMAP_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("IMAP_ENCRYPTION_KEY is not set")
    return Fernet(key.encode())


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext string and return a base64-encoded ciphertext."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a ciphertext produced by encrypt_secret. Raises InvalidToken if tampered."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def is_encrypted(value: str) -> bool:
    """Heuristic: Fernet tokens start with 'gAAA' and are base64url-encoded."""
    try:
        decoded = base64.urlsafe_b64decode(value + "==")
        return decoded[:1] == b"\x80"
    except Exception:
        return False
