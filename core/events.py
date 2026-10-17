"""Domain events for mesh topology changes and packet transmission lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class EventType(str, Enum):
    """Standard domain event categories in Stealth Mesh."""

    MESSAGE_QUEUED = "message_queued"
    PACKET_TRANSMITTED = "packet_transmitted"
    MESSAGE_DELIVERED = "message_delivered"
    MESSAGE_FAILED = "message_failed"
    NODE_STATUS_CHANGED = "node_status_changed"
    ROUTE_RECALCULATED = "route_recalculated"


@dataclass(frozen=True, slots=True)
class NetworkEvent:
    """Immutable domain event record with UTC timestamp and validated metadata."""

    event_type: EventType
    source_node: str
    details: dict[str, str | int | float | bool] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, EventType):
            raise TypeError("event_type must be an EventType enum member")
        if not isinstance(self.source_node, str) or not self.source_node.strip():
            raise ValueError("source_node must be a non-empty string")
        if not isinstance(self.details, dict):
            raise TypeError("details must be a dictionary")
