"""In-memory acknowledgement tracking."""


class AcknowledgementTracker:
    """Track message IDs confirmed by the destination."""

    def __init__(self) -> None:
        self._acknowledged: set[str] = set()

    def acknowledge(self, message_id: str) -> None:
        """Record that a message ID has been confirmed by its destination."""
        if not isinstance(message_id, str) or not message_id.strip():
            raise ValueError("message_id must be non-empty")
        self._acknowledged.add(message_id)

    def is_acknowledged(self, message_id: str) -> bool:
        """Return whether the given message ID has been acknowledged."""
        if not isinstance(message_id, str) or not message_id.strip():
            raise ValueError("message_id must be non-empty")
        return message_id in self._acknowledged
