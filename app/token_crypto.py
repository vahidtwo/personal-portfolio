"""Encryption at rest for the Sanjeh token (Fernet, key derived from SECRET_KEY with HKDF-SHA256).

Stored form: "enc1:" + Fernet token. Values without the prefix are legacy plaintext and are read as-is
(rollout: rows written before the migration). A value that cannot be decrypted (SECRET_KEY rotated or
data damaged) reads as None, so the app treats the car as not connected and asks the user to connect again;
the stored ciphertext is left untouched until the user enters a new token.
"""
from __future__ import annotations

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy.types import String, TypeDecorator

logger = logging.getLogger(__name__)

PREFIX = "enc1:"
_HKDF_INFO = b"daraiito sanjeh-token v1"
_cache: dict[str, Fernet] = {}


class TokenKeyMissing(RuntimeError):
    pass


def _fernet(secret_key: str | None = None) -> Fernet:
    secret = os.environ.get("SECRET_KEY", "") if secret_key is None else secret_key
    if not secret:
        raise TokenKeyMissing("SECRET_KEY is required to encrypt or decrypt the Sanjeh token")
    f = _cache.get(secret)
    if f is None:
        raw = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(secret.encode())
        f = _cache[secret] = Fernet(base64.urlsafe_b64encode(raw))
    return f


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def encrypt_token(plain: str, secret_key: str | None = None) -> str:
    if is_encrypted(plain):
        return plain
    return PREFIX + _fernet(secret_key).encrypt(plain.encode()).decode("ascii")


def decrypt_token(stored: str | None, secret_key: str | None = None) -> str | None:
    """Plaintext for a stored value; legacy plaintext passes through; unreadable -> None (never raises)."""
    if not stored:
        return stored
    if not is_encrypted(stored):
        return stored
    try:
        return _fernet(secret_key).decrypt(stored[len(PREFIX):].encode("ascii")).decode()
    except (InvalidToken, TokenKeyMissing, ValueError):
        logger.warning("Stored Sanjeh token cannot be decrypted (SECRET_KEY changed?); user must reconnect")
        return None


class EncryptedToken(TypeDecorator):
    """String column that is encrypted on write and decrypted on read. "" and NULL are stored as-is."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if not value:
            return value
        return encrypt_token(value)

    def process_result_value(self, value, dialect):
        return decrypt_token(value)
