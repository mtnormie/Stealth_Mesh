"""Sender authentication, domain-separated AEAD+HMAC envelopes, and anti-replay."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import json

from security.encryption import EncryptedPayload, decrypt, encrypt
from security.integrity import HMAC_SIZE, ReplayWindow, compute_hmac, verify_hmac
from security.key_manager import derive_subkey


@dataclass(frozen=True, slots=True)
class SignedEnvelope:
    """Authenticated, replay-protected encrypted message envelope."""

    group_id: str
    sender: str
    sequence: int
    key_version: int
    payload: EncryptedPayload
    signature: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.group_id, str) or not self.group_id.strip():
            raise ValueError("group_id must be a non-empty string")
        if not isinstance(self.sender, str) or not self.sender.strip():
            raise ValueError("sender must be a non-empty string")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        if isinstance(self.key_version, bool) or not isinstance(self.key_version, int) or self.key_version < 1:
            raise ValueError("key_version must be a positive integer")
        if not isinstance(self.payload, EncryptedPayload):
            raise TypeError("payload must be an EncryptedPayload")
        if not isinstance(self.signature, bytes) or len(self.signature) != HMAC_SIZE:
            raise ValueError("signature must be a 32-byte HMAC-SHA256 tag")

    def canonical_aad(self) -> bytes:
        """Return deterministic associated data binding header fields to ciphertext."""
        header = {
            "group_id": self.group_id,
            "key_version": self.key_version,
            "sender": self.sender,
            "sequence": self.sequence,
        }
        return json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def signing_input(self) -> bytes:
        """Return canonical byte sequence covered by the sender HMAC signature."""
        aad = self.canonical_aad()
        return aad + b"|" + self.payload.nonce + b"|" + self.payload.ciphertext

    def to_dict(self) -> dict[str, object]:
        """Serialize the envelope to a JSON-compatible dictionary."""
        return {
            "group_id": self.group_id,
            "sender": self.sender,
            "sequence": self.sequence,
            "key_version": self.key_version,
            "nonce": base64.urlsafe_b64encode(self.payload.nonce).decode("ascii"),
            "ciphertext": base64.urlsafe_b64encode(self.payload.ciphertext).decode("ascii"),
            "signature": base64.urlsafe_b64encode(self.signature).decode("ascii"),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SignedEnvelope:
        """Deserialize and validate a SignedEnvelope dictionary."""
        if not isinstance(data, dict):
            raise TypeError("envelope data must be a dict")
        try:
            group_id = data["group_id"]
            sender = data["sender"]
            sequence = data["sequence"]
            key_version = data["key_version"]
            raw_sig = data["signature"]
            raw_nonce = data["nonce"]
            raw_ct = data["ciphertext"]
            if (
                not isinstance(group_id, str)
                or not isinstance(sender, str)
                or not isinstance(raw_sig, str)
                or not isinstance(raw_nonce, str)
                or not isinstance(raw_ct, str)
            ):
                raise TypeError("string fields required")
            if isinstance(sequence, bool) or not isinstance(sequence, int):
                raise TypeError("sequence must be an int")
            if isinstance(key_version, bool) or not isinstance(key_version, int):
                raise TypeError("key_version must be an int")
            payload = EncryptedPayload.from_dict(
                {
                    "nonce": raw_nonce,
                    "ciphertext": raw_ct,
                }
            )
            signature = base64.b64decode(raw_sig, altchars=b"-_", validate=True)
        except (KeyError, TypeError, ValueError, binascii.Error) as error:
            raise ValueError("invalid signed envelope format") from error
        return cls(
            group_id=group_id,
            sender=sender,
            sequence=sequence,
            key_version=key_version,
            payload=payload,
            signature=signature,
        )


class MessageAuthenticator:
    """ Seal and open group messages with HKDF subkeys, HMAC sender auth, and anti-replay."""

    def __init__(self, replay_window: ReplayWindow | None = None) -> None:
        self.replay_window = replay_window or ReplayWindow()

    @staticmethod
    def _derive_keys(
        master_key: bytes,
        group_id: str,
        sender: str,
        key_version: int,
    ) -> tuple[bytes, bytes]:
        ctx = f"{group_id}:{key_version}".encode("utf-8")
        sender_ctx = f"{group_id}:{key_version}:{sender}".encode("utf-8")
        enc_key = derive_subkey(master_key, "aes256-gcm-enc", context=ctx)
        auth_key = derive_subkey(master_key, "hmac-sha256-sender-auth", context=sender_ctx)
        return enc_key, auth_key

    def seal(
        self,
        master_key: bytes,
        *,
        group_id: str,
        sender: str,
        sequence: int,
        plaintext: bytes,
        key_version: int = 1,
    ) -> SignedEnvelope:
        """Encrypt and sign a message using domain-separated HKDF subkeys."""
        if not isinstance(plaintext, bytes):
            raise TypeError("plaintext must be bytes")
        if not isinstance(group_id, str) or not group_id.strip():
            raise ValueError("group_id must be a non-empty string")
        if not isinstance(sender, str) or not sender.strip():
            raise ValueError("sender must be a non-empty string")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("sequence must be a positive integer")
        if isinstance(key_version, bool) or not isinstance(key_version, int) or key_version < 1:
            raise ValueError("key_version must be a positive integer")

        enc_key, auth_key = self._derive_keys(master_key, group_id, sender, key_version)
        header = {
            "group_id": group_id,
            "key_version": key_version,
            "sender": sender,
            "sequence": sequence,
        }
        aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
        encrypted = encrypt(enc_key, plaintext, aad)
        signing_input = aad + b"|" + encrypted.nonce + b"|" + encrypted.ciphertext
        signature = compute_hmac(auth_key, signing_input)
        return SignedEnvelope(
            group_id=group_id,
            sender=sender,
            sequence=sequence,
            key_version=key_version,
            payload=encrypted,
            signature=signature,
        )

    def open(self, master_key: bytes, envelope: SignedEnvelope) -> bytes:
        """Verify sender HMAC, check anti-replay window, decrypt, and commit sequence."""
        if not isinstance(envelope, SignedEnvelope):
            raise TypeError("envelope must be a SignedEnvelope")

        replay_scope = f"{envelope.group_id}:{envelope.sender}"
        if not self.replay_window.can_accept(replay_scope, envelope.sequence):
            raise ValueError("replayed or stale message sequence rejected")

        enc_key, auth_key = self._derive_keys(
            master_key,
            envelope.group_id,
            envelope.sender,
            envelope.key_version,
        )
        if not verify_hmac(auth_key, envelope.signing_input(), envelope.signature):
            raise ValueError("sender authentication failed")

        plaintext = decrypt(enc_key, envelope.payload, envelope.canonical_aad())
        if not self.replay_window.record(replay_scope, envelope.sequence):
            raise ValueError("replayed or stale message sequence rejected")
        return plaintext
