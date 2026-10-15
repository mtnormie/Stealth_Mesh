"""In-memory structured event log for reproducible simulation inspection."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    """A named event and its structured fields."""

    name: str
    fields: dict[str, Any]


class EventLogger:
    """Collect structured events in order; persistence/export can be added later."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def log(self, name: str, **fields: Any) -> None:
        if not name.strip():
            raise ValueError("event name must be non-empty")
        self.events.append(Event(name, dict(fields)))
