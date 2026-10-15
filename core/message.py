"""Validated application message model."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Message:
    """A text message addressed from one mesh node to another."""

    source: str
    destination: str
    body: str
    message_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.destination.strip():
            raise ValueError("source and destination must be non-empty")
        if not self.message_id.strip():
            raise ValueError("message_id must be non-empty")
        if not isinstance(self.body, str):
            raise TypeError("body must be text")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
