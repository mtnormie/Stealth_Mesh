"""AES-256-GCM authenticated encryption helpers."""

from __future__ import annotations

import base64
import binascii
import ctypes
import ctypes.util
import os
from dataclasses import dataclass

try:
    from cryptography.exceptions import InvalidTag as _InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
except ModuleNotFoundError:  # pragma: no cover - fallback to system OpenSSL libcrypto
    _AESGCM = None
    _InvalidTag = None

KEY_SIZE = 32
NONCE_SIZE = 12
TAG_SIZE = 16
MIN_CIPHERTEXT_SIZE = TAG_SIZE

_EVP_CTRL_GCM_SET_IVLEN = 0x09
_EVP_CTRL_GCM_GET_TAG = 0x10
_EVP_CTRL_GCM_SET_TAG = 0x11


@dataclass(frozen=True, slots=True)
class EncryptedPayload:
    """Portable representation of an authenticated ciphertext."""

    nonce: bytes
    ciphertext: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.nonce, bytes) or not isinstance(self.ciphertext, bytes):
            raise TypeError("nonce and ciphertext must be bytes")
        if len(self.nonce) != NONCE_SIZE or len(self.ciphertext) < MIN_CIPHERTEXT_SIZE:
            raise ValueError("invalid encrypted payload size")

    def to_dict(self) -> dict[str, str]:
        """Serialize nonce and ciphertext as URL-safe Base64 strings."""
        return {
            "nonce": base64.urlsafe_b64encode(self.nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(self.ciphertext).decode("ascii"),
        }

    @classmethod
    def from_dict(cls, value: dict[str, str]) -> "EncryptedPayload":
        """Deserialize and validate an encrypted payload mapping."""
        if not isinstance(value, dict):
            raise TypeError("encrypted payload mapping must be a dict")
        try:
            raw_nonce = value["nonce"]
            raw_ciphertext = value["ciphertext"]
            if not isinstance(raw_nonce, str) or not isinstance(raw_ciphertext, str):
                raise TypeError("nonce and ciphertext encodings must be strings")
            nonce = base64.b64decode(raw_nonce, altchars=b"-_", validate=True)
            ciphertext = base64.b64decode(raw_ciphertext, altchars=b"-_", validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error) as error:
            raise ValueError("invalid encrypted payload encoding") from error
        return cls(nonce=nonce, ciphertext=ciphertext)


def encrypt(key: bytes, plaintext: bytes, associated_data: bytes = b"") -> EncryptedPayload:
    """Encrypt bytes with a fresh 96-bit nonce and AES-256-GCM."""
    _validate_key(key)
    if not isinstance(plaintext, bytes) or not isinstance(associated_data, bytes):
        raise TypeError("plaintext and associated_data must be bytes")
    nonce = os.urandom(NONCE_SIZE)
    if _AESGCM is not None:
        ciphertext = _AESGCM(key).encrypt(nonce, plaintext, associated_data)
    else:
        ciphertext = _openssl_aes256_gcm_encrypt(key, nonce, plaintext, associated_data)
    return EncryptedPayload(nonce, ciphertext)


def decrypt(key: bytes, payload: EncryptedPayload, associated_data: bytes = b"") -> bytes:
    """Authenticate and decrypt a payload; reject modified data and wrong keys."""
    _validate_key(key)
    if not isinstance(payload, EncryptedPayload):
        raise TypeError("payload must be an EncryptedPayload instance")
    if not isinstance(associated_data, bytes):
        raise TypeError("associated_data must be bytes")
    if _AESGCM is not None and _InvalidTag is not None:
        try:
            return _AESGCM(key).decrypt(payload.nonce, payload.ciphertext, associated_data)
        except _InvalidTag as error:
            raise ValueError("ciphertext authentication failed") from error
    return _openssl_aes256_gcm_decrypt(key, payload.nonce, payload.ciphertext, associated_data)


def _validate_key(key: bytes) -> None:
    if not isinstance(key, bytes) or len(key) != KEY_SIZE:
        raise ValueError("AES-256-GCM requires a 32-byte key")


def _load_libcrypto() -> ctypes.CDLL:
    library_name = ctypes.util.find_library("crypto")
    if not library_name:
        raise RuntimeError("Neither 'cryptography' package nor OpenSSL libcrypto is available")
    lib = ctypes.CDLL(library_name)
    lib.EVP_CIPHER_CTX_new.restype = ctypes.c_void_p
    lib.EVP_CIPHER_CTX_free.argtypes = [ctypes.c_void_p]
    lib.EVP_aes_256_gcm.restype = ctypes.c_void_p
    lib.EVP_EncryptInit_ex.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
    ]
    lib.EVP_EncryptUpdate.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p, ctypes.c_int,
    ]
    lib.EVP_EncryptFinal_ex.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int),
    ]
    lib.EVP_DecryptInit_ex.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
    ]
    lib.EVP_DecryptUpdate.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p, ctypes.c_int,
    ]
    lib.EVP_DecryptFinal_ex.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int),
    ]
    lib.EVP_CIPHER_CTX_ctrl.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
    ]
    return lib


_LIBCRYPTO: ctypes.CDLL | None = None


def _get_libcrypto() -> ctypes.CDLL:
    global _LIBCRYPTO
    if _LIBCRYPTO is None:
        _LIBCRYPTO = _load_libcrypto()
    return _LIBCRYPTO


def _openssl_aes256_gcm_encrypt(
    key: bytes, nonce: bytes, plaintext: bytes, associated_data: bytes
) -> bytes:
    lib = _get_libcrypto()
    ctx = lib.EVP_CIPHER_CTX_new()
    if not ctx:
        raise RuntimeError("EVP_CIPHER_CTX_new failed")
    try:
        if lib.EVP_EncryptInit_ex(ctx, lib.EVP_aes_256_gcm(), None, None, None) != 1:
            raise RuntimeError("EVP_EncryptInit_ex cipher init failed")
        if lib.EVP_CIPHER_CTX_ctrl(ctx, _EVP_CTRL_GCM_SET_IVLEN, len(nonce), None) != 1:
            raise RuntimeError("EVP_CTRL_GCM_SET_IVLEN failed")
        if lib.EVP_EncryptInit_ex(ctx, None, None, key, nonce) != 1:
            raise RuntimeError("EVP_EncryptInit_ex key/iv init failed")
        out_len = ctypes.c_int(0)
        if associated_data:
            if lib.EVP_EncryptUpdate(ctx, None, ctypes.byref(out_len), associated_data, len(associated_data)) != 1:
                raise RuntimeError("EVP_EncryptUpdate AAD failed")
        out_buf = ctypes.create_string_buffer(len(plaintext) + TAG_SIZE)
        total_len = 0
        if plaintext:
            if lib.EVP_EncryptUpdate(ctx, out_buf, ctypes.byref(out_len), plaintext, len(plaintext)) != 1:
                raise RuntimeError("EVP_EncryptUpdate plaintext failed")
            total_len += out_len.value
        final_buf = ctypes.create_string_buffer(TAG_SIZE)
        if lib.EVP_EncryptFinal_ex(ctx, final_buf, ctypes.byref(out_len)) != 1:
            raise RuntimeError("EVP_EncryptFinal_ex failed")
        tag_buf = ctypes.create_string_buffer(TAG_SIZE)
        if lib.EVP_CIPHER_CTX_ctrl(ctx, _EVP_CTRL_GCM_GET_TAG, TAG_SIZE, tag_buf) != 1:
            raise RuntimeError("EVP_CTRL_GCM_GET_TAG failed")
        return out_buf.raw[:total_len] + final_buf.raw[: out_len.value] + tag_buf.raw
    finally:
        lib.EVP_CIPHER_CTX_free(ctx)


def _openssl_aes256_gcm_decrypt(
    key: bytes, nonce: bytes, ciphertext_with_tag: bytes, associated_data: bytes
) -> bytes:
    if len(ciphertext_with_tag) < TAG_SIZE:
        raise ValueError("ciphertext authentication failed")
    ciphertext = ciphertext_with_tag[:-TAG_SIZE]
    tag = ciphertext_with_tag[-TAG_SIZE:]
    lib = _get_libcrypto()
    ctx = lib.EVP_CIPHER_CTX_new()
    if not ctx:
        raise RuntimeError("EVP_CIPHER_CTX_new failed")
    try:
        if lib.EVP_DecryptInit_ex(ctx, lib.EVP_aes_256_gcm(), None, None, None) != 1:
            raise RuntimeError("EVP_DecryptInit_ex cipher init failed")
        if lib.EVP_CIPHER_CTX_ctrl(ctx, _EVP_CTRL_GCM_SET_IVLEN, len(nonce), None) != 1:
            raise RuntimeError("EVP_CTRL_GCM_SET_IVLEN failed")
        if lib.EVP_DecryptInit_ex(ctx, None, None, key, nonce) != 1:
            raise RuntimeError("EVP_DecryptInit_ex key/iv init failed")
        out_len = ctypes.c_int(0)
        if associated_data:
            if lib.EVP_DecryptUpdate(ctx, None, ctypes.byref(out_len), associated_data, len(associated_data)) != 1:
                raise ValueError("ciphertext authentication failed")
        out_buf = ctypes.create_string_buffer(len(ciphertext) + TAG_SIZE)
        total_len = 0
        if ciphertext:
            if lib.EVP_DecryptUpdate(ctx, out_buf, ctypes.byref(out_len), ciphertext, len(ciphertext)) != 1:
                raise ValueError("ciphertext authentication failed")
            total_len += out_len.value
        tag_buf = ctypes.create_string_buffer(tag, TAG_SIZE)
        if lib.EVP_CIPHER_CTX_ctrl(ctx, _EVP_CTRL_GCM_SET_TAG, TAG_SIZE, tag_buf) != 1:
            raise ValueError("ciphertext authentication failed")
        final_buf = ctypes.create_string_buffer(TAG_SIZE)
        if lib.EVP_DecryptFinal_ex(ctx, final_buf, ctypes.byref(out_len)) != 1:
            raise ValueError("ciphertext authentication failed")
        return out_buf.raw[:total_len] + final_buf.raw[: out_len.value]
    finally:
        lib.EVP_CIPHER_CTX_free(ctx)
