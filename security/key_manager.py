"""Key generation, RFC 5869 HKDF-SHA256 derivation, and in-memory key rotation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
import threading
import time

GROUP_KEY_SIZE = 32
INVITATION_TOKEN_BYTES = 32
_SHA256_DIGEST_SIZE = 32
_MAX_HKDF_LEN = 255 * _SHA256_DIGEST_SIZE


def generate_group_key() -> bytes:
    """Return a cryptographically random 256-bit group key."""
    return secrets.token_bytes(GROUP_KEY_SIZE)


def generate_invitation_token() -> str:
    """Return a high-entropy, URL-safe, single-use invitation token."""
    return secrets.token_urlsafe(INVITATION_TOKEN_BYTES)


def hkdf_sha256(
    ikm: bytes,
    *,
    salt: bytes = b"",
    info: bytes = b"",
    length: int = GROUP_KEY_SIZE,
) -> bytes:
    """Derive keying material using RFC 5869 HKDF-SHA256."""
    if not isinstance(ikm, bytes) or not isinstance(salt, bytes) or not isinstance(info, bytes):
        raise TypeError("ikm, salt, and info must be bytes")
    if not ikm:
        raise ValueError("input keying material (ikm) must be non-empty")
    if isinstance(length, bool) or not isinstance(length, int) or not 1 <= length <= _MAX_HKDF_LEN:
        raise ValueError(f"length must be an integer between 1 and {_MAX_HKDF_LEN}")

    actual_salt = salt if salt else b"\x00" * _SHA256_DIGEST_SIZE
    prk = hmac.new(actual_salt, ikm, hashlib.sha256).digest()

    blocks: list[bytes] = []
    previous = b""
    counter = 1
    while sum(len(b) for b in blocks) < length:
        previous = hmac.new(prk, previous + info + bytes([counter]), hashlib.sha256).digest()
        blocks.append(previous)
        counter += 1
    return b"".join(blocks)[:length]


def derive_subkey(master_key: bytes, purpose: str, *, context: bytes = b"") -> bytes:
    """Derive a domain-separated 256-bit subkey from a 32-byte master key."""
    if not isinstance(master_key, bytes) or len(master_key) != GROUP_KEY_SIZE:
        raise ValueError("master_key must be 32 bytes")
    if not isinstance(purpose, str) or not purpose.strip():
        raise ValueError("purpose must be a non-empty string")
    if not isinstance(context, bytes):
        raise TypeError("context must be bytes")
    info = b"stealth-mesh-v1|" + purpose.strip().encode("utf-8") + b"|" + context
    return hkdf_sha256(master_key, info=info, length=GROUP_KEY_SIZE)


@dataclass(frozen=True, slots=True)
class VersionedKey:
    """A group master key tagged with its monotonic version number."""

    group_id: str
    version: int
    key: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.group_id, str) or not self.group_id.strip():
            raise ValueError("group_id must be a non-empty string")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if not isinstance(self.key, bytes) or len(self.key) != GROUP_KEY_SIZE:
            raise ValueError("key must be 32 bytes")


class KeyManager:
    """Manage versioned group keys, rotation, and bounded historical key retention."""

    def __init__(self, *, max_retained_versions: int = 4) -> None:
        if (
            isinstance(max_retained_versions, bool)
            or not isinstance(max_retained_versions, int)
            or max_retained_versions < 1
        ):
            raise ValueError("max_retained_versions must be a positive integer")
        self._max_retained = max_retained_versions
        self._keyrings: dict[str, dict[int, bytes]] = {}
        self._active_version: dict[str, int] = {}
        self._lock = threading.RLock()

    def register_group(self, group_id: str, initial_key: bytes | None = None) -> VersionedKey:
        """Initialize a group's keyring at version 1."""
        if not isinstance(group_id, str) or not group_id.strip():
            raise ValueError("group_id must be a non-empty string")
        key = generate_group_key() if initial_key is None else initial_key
        entry = VersionedKey(group_id=group_id, version=1, key=key)
        with self._lock:
            if group_id in self._keyrings:
                raise ValueError(f"group already registered: {group_id}")
            self._keyrings[group_id] = {1: entry.key}
            self._active_version[group_id] = 1
        return entry

    def rotate_group_key(
        self,
        group_id: str,
        new_key: bytes | None = None,
        *,
        purge_previous: bool = False,
    ) -> VersionedKey:
        """Advance the active key version for a group.

        When ``purge_previous`` is True (e.g. MIA / node capture quarantine),
        all prior key versions are immediately erased from memory.
        """
        if not isinstance(group_id, str) or not group_id.strip():
            raise ValueError("group_id must be a non-empty string")
        key = generate_group_key() if new_key is None else new_key
        with self._lock:
            if group_id not in self._keyrings:
                raise KeyError(f"unknown group: {group_id}")
            next_version = self._active_version[group_id] + 1
            entry = VersionedKey(group_id=group_id, version=next_version, key=key)
            ring = self._keyrings[group_id]
            if purge_previous:
                ring.clear()
            ring[next_version] = entry.key
            self._active_version[group_id] = next_version
            while len(ring) > self._max_retained:
                oldest = min(ring)
                del ring[oldest]
            return entry

    def active_key(self, group_id: str) -> VersionedKey:
        """Return the current active VersionedKey for a group."""
        with self._lock:
            if group_id not in self._keyrings:
                raise KeyError(f"unknown group: {group_id}")
            version = self._active_version[group_id]
            return VersionedKey(group_id=group_id, version=version, key=self._keyrings[group_id][version])

    def get_key(self, group_id: str, version: int) -> bytes:
        """Return a specific key version for decrypting in-flight messages."""
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("version must be a positive integer")
        with self._lock:
            ring = self._keyrings.get(group_id)
            if ring is None:
                raise KeyError(f"unknown group: {group_id}")
            key = ring.get(version)
            if key is None:
                raise KeyError(f"key version {version} not available for group {group_id}")
            return key

    def revoke_group(self, group_id: str) -> None:
        """Remove all key versions for a group from memory."""
        with self._lock:
            self._keyrings.pop(group_id, None)
            self._active_version.pop(group_id, None)


class DeadMansSwitch:
    """Automatic session-key wipe timer and duress wipe for MIA / capture protection."""

    def __init__(self, default_ttl_seconds: float = 21600.0) -> None:
        if isinstance(default_ttl_seconds, bool) or default_ttl_seconds <= 0:
            raise ValueError("default_ttl_seconds must be positive")
        self._default_ttl = float(default_ttl_seconds)
        self._sessions: dict[str, dict[str, float | bool]] = {}
        self._lock = threading.RLock()

    def arm(
        self,
        group_id: str,
        ttl_seconds: float | None = None,
        *,
        now: float | None = None,
    ) -> dict[str, object]:
        """Arm or reset the Dead Man's Switch timer for a group session."""
        if not isinstance(group_id, str) or not group_id.strip():
            raise ValueError("group_id must be a non-empty string")
        ttl = self._default_ttl if ttl_seconds is None else float(ttl_seconds)
        if isinstance(ttl_seconds, bool) or ttl <= 0:
            raise ValueError("ttl_seconds must be positive")
        ts = time.monotonic() if now is None else float(now)
        with self._lock:
            self._sessions[group_id] = {
                "last_heartbeat": ts,
                "ttl_seconds": ttl,
                "sos_only_mode": False,
                "duress_wiped": False,
            }
            return self.status(group_id, now=ts)

    def heartbeat(self, group_id: str, *, now: float | None = None) -> dict[str, object]:
        """Confirm operator liveness and reset the Dead Man's Switch countdown."""
        ts = time.monotonic() if now is None else float(now)
        with self._lock:
            session = self._sessions.get(group_id)
            if session is None:
                return self.arm(group_id, now=ts)
            if session["sos_only_mode"] or session["duress_wiped"]:
                raise PermissionError("session keys wiped; re-authentication required")
            session["last_heartbeat"] = ts
            return self.status(group_id, now=ts)

    def status(self, group_id: str, *, now: float | None = None) -> dict[str, object]:
        """Return current timer state, remaining seconds, and SOS-only mode status."""
        ts = time.monotonic() if now is None else float(now)
        with self._lock:
            session = self._sessions.get(group_id)
            if session is None:
                return {
                    "armed": False,
                    "expired": False,
                    "remaining_seconds": 0.0,
                    "sos_only_mode": False,
                    "duress_wiped": False,
                }
            elapsed = max(0.0, ts - float(session["last_heartbeat"]))
            ttl = float(session["ttl_seconds"])
            remaining = max(0.0, ttl - elapsed)
            expired = bool(session["sos_only_mode"] or remaining <= 0.0)
            return {
                "armed": True,
                "expired": expired,
                "remaining_seconds": round(remaining, 2),
                "ttl_seconds": ttl,
                "sos_only_mode": bool(session["sos_only_mode"]),
                "duress_wiped": bool(session["duress_wiped"]),
            }

    def check_and_enforce(
        self,
        key_manager: KeyManager,
        group_id: str,
        *,
        now: float | None = None,
    ) -> bool:
        """Wipe group keys from KeyManager if the Dead Man's Switch has expired."""
        ts = time.monotonic() if now is None else float(now)
        with self._lock:
            session = self._sessions.get(group_id)
            if session is None:
                return False
            elapsed = max(0.0, ts - float(session["last_heartbeat"]))
            if elapsed >= float(session["ttl_seconds"]) and not session["sos_only_mode"]:
                session["sos_only_mode"] = True
                key_manager.revoke_group(group_id)
                return True
            return bool(session["sos_only_mode"])

    def trigger_duress_wipe(self, key_manager: KeyManager, group_id: str) -> dict[str, object]:
        """Immediately erase all group keys from memory (Duress PIN / panic action)."""
        with self._lock:
            key_manager.revoke_group(group_id)
            self._sessions[group_id] = {
                "last_heartbeat": time.monotonic(),
                "ttl_seconds": self._default_ttl,
                "sos_only_mode": True,
                "duress_wiped": True,
            }
            return {"group_id": group_id, "duress_wiped": True, "sos_only_mode": True}
