"""In-memory encrypted group messaging, key rotation, and one-time invitations."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hmac
import json
import threading
import time
from uuid import uuid4

from security.authentication import MessageAuthenticator, SignedEnvelope
from security.diia_military_auth import AuthStatus, OperatorAuthPass
from security.encryption import EncryptedPayload, decrypt, encrypt
from security.key_manager import DeadMansSwitch, KeyManager, generate_invitation_token

MAX_GROUPS = 256
MAX_MESSAGES_PER_GROUP = 1000
MAX_INVITATIONS = 1024
MAX_MEMBER_TOKENS_PER_GROUP = 1024


@dataclass(slots=True)
class Group:
    """In-memory group state holding its metadata and encrypted message records."""

    group_id: str
    name: str
    key: bytes
    key_version: int = 1
    next_sequence: int = 1
    member_tokens: OrderedDict[str, None] = field(default_factory=OrderedDict)
    messages: list[dict[str, object]] = field(default_factory=list)
    quarantined_members: dict[str, dict[str, str]] = field(default_factory=dict)


class GroupService:
    """Minimal in-process group service for the local prototype UI."""

    def __init__(
        self,
        *,
        max_groups: int = MAX_GROUPS,
        max_messages_per_group: int = MAX_MESSAGES_PER_GROUP,
        max_invitations: int = MAX_INVITATIONS,
        max_retained_key_versions: int = 8,
        require_operator_auth: bool = False,
    ) -> None:
        if min(max_groups, max_messages_per_group, max_invitations, max_retained_key_versions) < 1:
            raise ValueError("service capacity limits must be positive")
        self._max_groups = max_groups
        self._max_messages_per_group = max_messages_per_group
        self._max_invitations = max_invitations
        self._require_operator_auth = bool(require_operator_auth)
        self._groups: dict[str, Group] = {}
        self._key_manager = KeyManager(max_retained_versions=max_retained_key_versions)
        self._dead_mans_switch = DeadMansSwitch()
        self._authenticator = MessageAuthenticator()
        self._invitations: OrderedDict[str, str] = OrderedDict()
        self._operator_passes: dict[str, OperatorAuthPass] = {}
        self._seen_external_ids: OrderedDict[str, None] = OrderedDict()
        self._lock = threading.RLock()

    def register_operator_pass(self, auth_pass: OperatorAuthPass) -> dict[str, object]:
        """Register a verified Diia + Military ID onboarding pass for operator gating."""
        if auth_pass.status != AuthStatus.VERIFIED:
            raise PermissionError("operator pass must be verified")
        with self._lock:
            self._operator_passes[auth_pass.pass_id] = auth_pass
            return {
                "pass_id": auth_pass.pass_id,
                "unit_code": auth_pass.unit_code,
                "expires_at": auth_pass.expires_at,
                "verified": True,
            }

    def verify_operator_pass(self, pass_id: str | None, *, now: float | None = None) -> bool:
        """Return True if an operator holds a non-expired Diia + Military ID pass."""
        if not isinstance(pass_id, str) or not pass_id.strip():
            return False
        ts = time.time() if now is None else float(now)
        with self._lock:
            entry = self._operator_passes.get(pass_id.strip())
            if entry is None or entry.status != AuthStatus.VERIFIED:
                return False
            if ts > entry.expires_at:
                self._operator_passes.pop(pass_id.strip(), None)
                return False
            return True

    def ensure_group(self, group_id: str, name: str) -> dict[str, str]:
        """Ensure a named group with a deterministic group_id exists (e.g. default LoRa mesh channel)."""
        group_id = group_id.strip()
        name = name.strip() or group_id
        with self._lock:
            existing = self._groups.get(group_id)
            if existing is not None:
                first_tok = next(iter(existing.member_tokens.keys()), "")
                return {"group_id": existing.group_id, "name": existing.name, "member_token": first_tok}
            versioned = self._key_manager.register_group(group_id)
            member_token = generate_invitation_token()
            tokens: OrderedDict[str, None] = OrderedDict()
            tokens[member_token] = None
            self._groups[group_id] = Group(
                group_id=group_id,
                name=name[:80],
                key=versioned.key,
                key_version=versioned.version,
                member_tokens=tokens,
            )
            self._dead_mans_switch.arm(group_id)
            return {"group_id": group_id, "name": name[:80], "member_token": member_token}

    def ingest_remote_message(
        self,
        group_id: str,
        sender: str,
        body: str,
        *,
        external_id: str | None = None,
        source_node: str | None = None,
        rssi: int | None = None,
        snr: float | None = None,
        hops: int = 1,
    ) -> dict[str, object] | None:
        """Ingest a message received over physical LoRa radio from a neighboring or relay node."""
        gid = (group_id or "mesh-default").strip() or "mesh-default"
        snd = (sender or source_node or "Node").strip()[:80] or "Node"
        txt = (body or "").strip()[:4000]
        if not txt:
            return None
        with self._lock:
            if external_id:
                if external_id in self._seen_external_ids:
                    return None
                self._seen_external_ids[external_id] = None
                while len(self._seen_external_ids) > 512:
                    self._seen_external_ids.popitem(last=False)
            self.ensure_group(gid, "Тактичний ефір Mesh (868 МГц)" if gid == "mesh-default" else f"Радіогрупа {gid}")
            res = self.send_message(gid, snd, txt)
            group = self._groups[gid]
            if group.messages:
                last = group.messages[-1]
                if source_node:
                    last["source_node"] = str(source_node)
                if rssi is not None:
                    last["rssi"] = int(rssi)
                if snr is not None:
                    last["snr"] = float(snr)
                last["hops"] = max(1, int(hops))
            return res

    def create_group(self, name: str, *, operator_pass_id: str | None = None) -> dict[str, str]:
        if self._require_operator_auth and not self.verify_operator_pass(operator_pass_id):
            raise PermissionError("Diia + Military ID operator pass required")
        if not isinstance(name, str):
            raise TypeError("group name must be a string")
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError("group name must contain 1 to 80 characters")
        group_id = str(uuid4())
        with self._lock:
            if len(self._groups) >= self._max_groups:
                raise ValueError("maximum number of groups reached")
            versioned = self._key_manager.register_group(group_id)
            member_token = generate_invitation_token()
            tokens: OrderedDict[str, None] = OrderedDict()
            tokens[member_token] = None
            self._groups[group_id] = Group(
                group_id=group_id,
                name=name,
                key=versioned.key,
                key_version=versioned.version,
                member_tokens=tokens,
            )
            self._dead_mans_switch.arm(group_id)
        return {"group_id": group_id, "name": name, "member_token": member_token}

    def rotate_group_key(self, group_id: str, *, purge_previous: bool = False) -> dict[str, object]:
        """Rotate the active encryption key for a group while optionally purging old keys."""
        if not isinstance(group_id, str):
            raise TypeError("group_id must be a string")
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise KeyError("group not found")
            # Decode existing messages before rotation so none become unreadable if an old key is evicted
            decoded = [
                (record, self._present(group_id, record)["body"])
                for record in group.messages
            ]
            versioned = self._key_manager.rotate_group_key(group_id, purge_previous=purge_previous)
            group.key = versioned.key
            group.key_version = versioned.version
            for record, body_text in decoded:
                ver = int(record.get("key_version", 1))  # type: ignore[arg-type]
                try:
                    self._key_manager.get_key(group_id, ver)
                except KeyError:
                    metadata = {name: str(record[name]) for name in ("id", "group_id", "sender", "created_at")}
                    re_enc = encrypt(group.key, json.dumps({"body": body_text}).encode(), _associated_data(metadata))
                    seq = group.next_sequence
                    group.next_sequence += 1
                    re_env = self._authenticator.seal(
                        group.key,
                        group_id=group_id,
                        sender=metadata["sender"],
                        sequence=seq,
                        plaintext=json.dumps(
                            {"id": metadata["id"], "body": body_text, "created_at": metadata["created_at"]}
                        ).encode("utf-8"),
                        key_version=group.key_version,
                    )
                    record["sequence"] = seq
                    record["key_version"] = group.key_version
                    record["nonce"] = re_enc.to_dict()["nonce"]
                    record["ciphertext"] = re_enc.to_dict()["ciphertext"]
                    record["signed_envelope"] = re_env.to_dict()
            return {"group_id": group_id, "key_version": versioned.version, "purged_previous": purge_previous}

    def quarantine_member(
        self,
        group_id: str,
        member_id: str,
        *,
        reason: str = "MIA",
        challenge: str | None = None,
        rotate_key: bool = True,
    ) -> dict[str, object]:
        """Isolate a missing/captured member and optionally rotate & purge old group keys."""
        if not isinstance(group_id, str) or not isinstance(member_id, str):
            raise TypeError("group_id and member_id must be strings")
        mid = member_id.strip()
        if not mid:
            raise ValueError("member_id must be non-empty")
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise KeyError("group not found")
            group.quarantined_members[mid] = {
                "reason": (reason or "MIA").strip()[:64],
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
                "challenge": (challenge or "").strip()[:128],
            }
            if rotate_key:
                rot = self.rotate_group_key(group_id, purge_previous=True)
                key_ver = rot["key_version"]
            else:
                key_ver = group.key_version
            return {
                "group_id": group_id,
                "member_id": mid,
                "quarantined": True,
                "reason": group.quarantined_members[mid]["reason"],
                "key_version": key_ver,
            }

    def release_quarantine(
        self,
        group_id: str,
        member_id: str,
        *,
        challenge_response: str | None = None,
    ) -> dict[str, object]:
        """Verify challenge-response (if set) and restore a quarantined member."""
        if not isinstance(group_id, str) or not isinstance(member_id, str):
            raise TypeError("group_id and member_id must be strings")
        mid = member_id.strip()
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise KeyError("group not found")
            entry = group.quarantined_members.get(mid)
            if entry is None:
                return {"group_id": group_id, "member_id": mid, "quarantined": False}
            expected = entry.get("challenge", "")
            if expected:
                provided = (challenge_response or "").strip()
                if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
                    raise PermissionError("challenge-response verification failed")
            del group.quarantined_members[mid]
            return {"group_id": group_id, "member_id": mid, "quarantined": False, "verified": True}

    def heartbeat(
        self,
        group_id: str,
        *,
        ttl_seconds: float | None = None,
        now: float | None = None,
    ) -> dict[str, object]:
        """Confirm operator liveness or arm a new Dead Man's Switch TTL."""
        with self._lock:
            if group_id not in self._groups:
                raise KeyError("group not found")
            if ttl_seconds is not None:
                return self._dead_mans_switch.arm(group_id, ttl_seconds=ttl_seconds, now=now)
            return self._dead_mans_switch.heartbeat(group_id, now=now)

    def dead_mans_switch_status(self, group_id: str, *, now: float | None = None) -> dict[str, object]:
        """Check Dead Man's Switch and enforce key wipe if expired."""
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise KeyError("group not found")
            if self._dead_mans_switch.check_and_enforce(self._key_manager, group_id, now=now):
                group.key = b"\x00" * 32
                group.messages.clear()
            return self._dead_mans_switch.status(group_id, now=now)

    def trigger_duress_wipe(self, group_id: str) -> dict[str, object]:
        """Erase active keys, message history, and member tokens for a group from RAM."""
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise KeyError("group not found")
            group.key = b"\x00" * 32
            group.messages.clear()
            group.member_tokens.clear()
            return self._dead_mans_switch.trigger_duress_wipe(self._key_manager, group_id)

    def create_invitation(self, group_id: str, app_url: str) -> dict[str, str]:
        if not isinstance(group_id, str) or not isinstance(app_url, str):
            raise TypeError("group_id and app_url must be strings")
        app_url = app_url.strip()
        if not app_url:
            raise ValueError("app_url must be non-empty")
        with self._lock:
            if group_id not in self._groups:
                raise KeyError("group not found")
            token = generate_invitation_token()
            self._invitations[token] = group_id
            while len(self._invitations) > self._max_invitations:
                self._invitations.popitem(last=False)
            url = f"{app_url.rstrip('/')}/#join={token}"
            return {"token": token, "url": url}

    def join_group(self, token: str) -> dict[str, str]:
        if not isinstance(token, str):
            raise TypeError("token must be a string")
        token = token.strip()
        with self._lock:
            group_id = self._invitations.pop(token, None)
            if group_id is None or group_id not in self._groups:
                raise ValueError("invitation is invalid or has already been used")
            group = self._groups[group_id]
            member_token = generate_invitation_token()
            group.member_tokens[member_token] = None
            while len(group.member_tokens) > MAX_MEMBER_TOKENS_PER_GROUP:
                group.member_tokens.popitem(last=False)
            return {"group_id": group_id, "name": group.name, "member_token": member_token}

    def verify_member_token(self, group_id: str, member_token: str | None) -> bool:
        """Verify that a client holds a valid membership capability token for the group."""
        if not isinstance(group_id, str):
            return False
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                return False
            if group_id == "mesh-default":
                return True
            if not isinstance(member_token, str) or not member_token.strip():
                return False
            candidate = member_token.strip().encode("utf-8")
            return any(hmac.compare_digest(candidate, tok.encode("utf-8")) for tok in group.member_tokens)

    def send_message(
        self,
        group_id: str,
        sender: str,
        body: str,
        *,
        operator_pass_id: str | None = None,
    ) -> dict[str, str]:
        if self._require_operator_auth and not self.verify_operator_pass(operator_pass_id):
            raise PermissionError("Diia + Military ID operator pass required")
        if not isinstance(group_id, str) or not isinstance(sender, str) or not isinstance(body, str):
            raise TypeError("group_id, sender, and body must be strings")
        sender, body = sender.strip(), body.strip()
        if not sender or len(sender) > 80:
            raise ValueError("sender must contain 1 to 80 characters")
        if not body or len(body) > 4000:
            raise ValueError("message must contain 1 to 4000 characters")
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise KeyError("group not found")
            if self._dead_mans_switch.check_and_enforce(self._key_manager, group_id):
                group.key = b"\x00" * 32
                group.messages.clear()
                raise PermissionError("session keys wiped by Dead Man's Switch; SOS-only mode active")
            message_id = str(uuid4())
            created_at = datetime.now(timezone.utc).isoformat()
            metadata = {
                "id": message_id,
                "group_id": group_id,
                "sender": sender,
                "created_at": created_at,
            }
            aad = _associated_data(metadata)
            encrypted = encrypt(group.key, json.dumps({"body": body}).encode(), aad)
            seq = group.next_sequence
            group.next_sequence += 1
            wire_envelope: SignedEnvelope = self._authenticator.seal(
                group.key,
                group_id=group_id,
                sender=sender,
                sequence=seq,
                plaintext=json.dumps({"id": message_id, "body": body, "created_at": created_at}).encode("utf-8"),
                key_version=group.key_version,
            )
            record: dict[str, object] = {
                **metadata,
                "sequence": seq,
                "key_version": group.key_version,
                "quarantined": sender in group.quarantined_members,
                **encrypted.to_dict(),
                "signed_envelope": wire_envelope.to_dict(),
            }
            group.messages.append(record)
            if len(group.messages) > self._max_messages_per_group:
                del group.messages[0]
            return self._present(group_id, record)

    def get_encrypted_wire_bytes(self, group_id: str, message_id: str) -> bytes:
        """Return the encrypted and HMAC-signed wire envelope bytes for over-the-air transmission."""
        if not isinstance(group_id, str) or not isinstance(message_id, str):
            raise TypeError("group_id and message_id must be strings")
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise KeyError("group not found")
            for record in reversed(group.messages):
                if record.get("id") == message_id:
                    env_dict = record.get("signed_envelope")
                    if isinstance(env_dict, dict):
                        return json.dumps(env_dict, separators=(",", ":"), sort_keys=True).encode("utf-8")
            raise KeyError("message not found")

    def list_messages(self, group_id: str) -> list[dict[str, str]]:
        if not isinstance(group_id, str):
            raise TypeError("group_id must be a string")
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise KeyError("group not found")
            if self._dead_mans_switch.check_and_enforce(self._key_manager, group_id):
                group.key = b"\x00" * 32
                group.messages.clear()
                return []
            return [self._present(group_id, record) for record in group.messages]

    def list_groups(self) -> list[dict[str, str]]:
        with self._lock:
            return [{"group_id": item.group_id, "name": item.name} for item in self._groups.values()]

    def _present(self, group_id: str, record: dict[str, object]) -> dict[str, str]:
        metadata = {name: str(record[name]) for name in ("id", "group_id", "sender", "created_at")}
        raw_version = record.get("key_version", 1)
        version = int(raw_version) if isinstance(raw_version, int) and not isinstance(raw_version, bool) else 1
        key = self._key_manager.get_key(group_id, version)
        payload = EncryptedPayload.from_dict(
            {
                "nonce": str(record["nonce"]),
                "ciphertext": str(record["ciphertext"]),
            }
        )
        cleartext = decrypt(key, payload, _associated_data(metadata))
        out: dict[str, object] = {**metadata, "body": json.loads(cleartext)["body"]}
        if record.get("quarantined"):
            out["quarantined"] = True
            out["trust_status"] = "quarantined_mia"
        for extra_key in ("source_node", "rssi", "snr", "hops"):
            if extra_key in record:
                out[extra_key] = record[extra_key]
        return out  # type: ignore[return-value]


def _associated_data(metadata: dict[str, str]) -> bytes:
    return json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
