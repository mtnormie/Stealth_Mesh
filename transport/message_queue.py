"""In-memory FIFO queue for pending messages."""

from collections import deque

from core.packet import Packet


class MessageQueue:
    """Small in-memory queue; persistence is intentionally not provided."""

    def __init__(self) -> None:
        self._items: deque[Packet] = deque()
        self._message_ids: set[str] = set()

    def enqueue(self, packet: Packet) -> bool:
        """Add a packet unless that message is already queued; return whether added."""
        if not isinstance(packet, Packet):
            raise TypeError("packet must be a Packet instance")
        if packet.message_id in self._message_ids:
            return False
        self._items.append(packet)
        self._message_ids.add(packet.message_id)
        return True

    def dequeue(self) -> Packet | None:
        """Remove the next packet and permit its message ID to be enqueued again."""
        if not self._items:
            return None
        packet = self._items.popleft()
        self._message_ids.remove(packet.message_id)
        return packet

    def __len__(self) -> int:
        return len(self._items)
