"""In-memory encrypted group messaging, key rotation, and one-time invitations."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import threading
from uuid import uuid4

from security.encryption import EncryptedPayload, decrypt, encrypt
from security.key_manager import KeyManager, generate_invitation_token

MAX_GROUPS = 256
MAX_MESSAGES_PER_GROUP = 1000
MAX_INVITATIONS = 1024


@dataclass(slots=True)
class Group:
    """In-memory group state holding its metadata and encrypted message records."""

    group_id: str
    name: str
    key: bytes
    key_version: int = 1
    messages: list[dict[str, object]] = field(default_factory=list)


class GroupService:
    """Minimal in-process group service for the local prototype UI."""

    def __init__(
        self,
        *,
        max_groups: int = MAX_GROUPS,
        max_messages_per_group: int = MAX_MESSAGES_PER_GROUP,
        max_invitations: int = MAX_INVITATIONS,
        max_retained_key_versions: int = 8,
    ) -> None:
        if min(max_groups, max_messages_per_group, max_invitations, max_retained_key_versions) < 1:
            raise ValueError("service capacity limits must be positive")
        self._max_groups = max_groups
        self._max_messages_per_group = max_messages_per_group
        self._max_invitations = max_invitations
        self._groups: dict[str, Group] = {}
        self._key_manager = KeyManager(max_retained_versions=max_retained_key_versions)
        self._invitations: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.RLock()

    def create_group(self, name: str) -> dict[str, str]:
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
            self._groups[group_id] = Group(
                group_id=group_id,
                name=name,
                key=versioned.key,
                key_version=versioned.version,
            )
        return {"group_id": group_id, "name": name}

    def rotate_group_key(self, group_id: str) -> dict[str, object]:
        """Rotate the active encryption key for a group while retaining recent versions."""
        if not isinstance(group_id, str):
            raise TypeError("group_id must be a string")
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise KeyError("group not found")
            versioned = self._key_manager.rotate_group_key(group_id)
            group.key = versioned.key
            group.key_version = versioned.version
            return {"group_id": group_id, "key_version": versioned.version}

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
            url = f"{app_url.rstrip('/')}?join={token}"
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
            return {"group_id": group_id, "name": group.name}

    def send_message(self, group_id: str, sender: str, body: str) -> dict[str, str]:
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
            record: dict[str, object] = {
                **metadata,
                "key_version": group.key_version,
                **encrypted.to_dict(),
            }
            group.messages.append(record)
            if len(group.messages) > self._max_messages_per_group:
                del group.messages[0]
            return self._present(group_id, record)

    def list_messages(self, group_id: str) -> list[dict[str, str]]:
        if not isinstance(group_id, str):
            raise TypeError("group_id must be a string")
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise KeyError("group not found")
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
        return {**metadata, "body": json.loads(cleartext)["body"]}


def _associated_data(metadata: dict[str, str]) -> bytes:
    return json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
