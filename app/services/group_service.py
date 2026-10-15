"""In-memory encrypted group messaging and one-time invitations."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from security.encryption import EncryptedPayload, decrypt, encrypt
from security.key_manager import generate_group_key, generate_invitation_token


@dataclass(slots=True)
class Group:
    group_id: str
    name: str
    key: bytes
    messages: list[dict[str, str]] = field(default_factory=list)


class GroupService:
    """Minimal in-process group service for the local prototype UI."""

    def __init__(self) -> None:
        self._groups: dict[str, Group] = {}
        self._invitations: dict[str, str] = {}
        self._lock = threading.RLock()

    def create_group(self, name: str) -> dict[str, str]:
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError("group name must contain 1 to 80 characters")
        group_id = str(uuid4())
        with self._lock:
            self._groups[group_id] = Group(group_id, name, generate_group_key())
        return {"group_id": group_id, "name": name}

    def create_invitation(self, group_id: str, app_url: str) -> dict[str, str]:
        with self._lock:
            if group_id not in self._groups:
                raise KeyError("group not found")
            token = generate_invitation_token()
            self._invitations[token] = group_id
            url = f"{app_url.rstrip('/')}?join={token}"
            return {"token": token, "url": url}

    def join_group(self, token: str) -> dict[str, str]:
        with self._lock:
            group_id = self._invitations.pop(token, None)
            if group_id is None:
                raise ValueError("invitation is invalid or has already been used")
            group = self._groups[group_id]
            return {"group_id": group_id, "name": group.name}

    def send_message(self, group_id: str, sender: str, body: str) -> dict[str, str]:
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
            metadata = {"id": message_id, "group_id": group_id, "sender": sender, "created_at": created_at}
            aad = _associated_data(metadata)
            encrypted = encrypt(group.key, json.dumps({"body": body}).encode(), aad)
            record = {**metadata, **encrypted.to_dict()}
            group.messages.append(record)
            return self._present(group.key, record)

    def list_messages(self, group_id: str) -> list[dict[str, str]]:
        with self._lock:
            group = self._groups.get(group_id)
            if group is None:
                raise KeyError("group not found")
            return [self._present(group.key, record) for record in group.messages]

    def list_groups(self) -> list[dict[str, str]]:
        with self._lock:
            return [{"group_id": item.group_id, "name": item.name} for item in self._groups.values()]

    @staticmethod
    def _present(key: bytes, record: dict[str, str]) -> dict[str, str]:
        metadata = {name: record[name] for name in ("id", "group_id", "sender", "created_at")}
        cleartext = decrypt(key, EncryptedPayload.from_dict(record), _associated_data(metadata))
        return {**metadata, "body": json.loads(cleartext)["body"]}


def _associated_data(metadata: dict[str, str]) -> bytes:
    return json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
