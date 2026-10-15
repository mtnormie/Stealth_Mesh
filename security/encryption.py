"""AES-256-GCM authenticated encryption helpers."""

from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_SIZE = 32
NONCE_SIZE = 12


@dataclass(frozen=True, slots=True)
class EncryptedPayload:
    """Portable representation of an authenticated ciphertext."""

    nonce: bytes
    ciphertext: bytes

    def to_dict(self) -> dict[str, str]:
        return {
            "nonce": base64.urlsafe_b64encode(self.nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(self.ciphertext).decode("ascii"),
        }

    @classmethod
    def from_dict(cls, value: dict[str, str]) -> "EncryptedPayload":
        try:
            nonce = base64.b64decode(value["nonce"], altchars=b"-_", validate=True)
            ciphertext = base64.b64decode(value["ciphertext"], altchars=b"-_", validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error) as error:
            raise ValueError("invalid encrypted payload encoding") from error
        if len(nonce) != NONCE_SIZE or len(ciphertext) < 16:
            raise ValueError("invalid encrypted payload size")
        return cls(nonce=nonce, ciphertext=ciphertext)


def encrypt(key: bytes, plaintext: bytes, associated_data: bytes = b"") -> EncryptedPayload:
    """Encrypt bytes with a fresh 96-bit nonce and AES-256-GCM."""
    _validate_key(key)
    if not isinstance(plaintext, bytes) or not isinstance(associated_data, bytes):
        raise TypeError("plaintext and associated_data must be bytes")
    nonce = os.urandom(NONCE_SIZE)
    return EncryptedPayload(nonce, AESGCM(key).encrypt(nonce, plaintext, associated_data))


def decrypt(key: bytes, payload: EncryptedPayload, associated_data: bytes = b"") -> bytes:
    """Authenticate and decrypt a payload; reject modified data and wrong keys."""
    _validate_key(key)
    if not isinstance(associated_data, bytes):
        raise TypeError("associated_data must be bytes")
    try:
        return AESGCM(key).decrypt(payload.nonce, payload.ciphertext, associated_data)
    except InvalidTag as error:
        raise ValueError("ciphertext authentication failed") from error


def _validate_key(key: bytes) -> None:
    if not isinstance(key, bytes) or len(key) != KEY_SIZE:
        raise ValueError("AES-256-GCM requires a 32-byte key")
