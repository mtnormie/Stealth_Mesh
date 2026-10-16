"""Bounded in-memory duplicate message detection."""

from collections import OrderedDict


class Deduplicator:
    """Remember recently delivered IDs, evicting the oldest at capacity."""

    def __init__(self, capacity: int = 10_000) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._seen: OrderedDict[str, None] = OrderedDict()

    def already_seen(self, message_id: str) -> bool:
        """Return true for known IDs; remember new IDs and evict oldest if needed."""
        if self.contains(message_id):
            self._seen.move_to_end(message_id)
            return True
        self.remember(message_id)
        return False

    def contains(self, message_id: str) -> bool:
        """Check whether an ID is already in the recent-delivery window."""
        if not isinstance(message_id, str) or not message_id.strip():
            raise ValueError("message_id must be non-empty")
        return message_id in self._seen

    def remember(self, message_id: str) -> None:
        """Record a successfully delivered message ID."""
        if not isinstance(message_id, str) or not message_id.strip():
            raise ValueError("message_id must be non-empty")
        self._seen[message_id] = None
        self._seen.move_to_end(message_id)
        if len(self._seen) > self.capacity:
            self._seen.popitem(last=False)
