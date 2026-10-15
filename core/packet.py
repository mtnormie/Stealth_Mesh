"""Validated packet model and hop-limit handling."""

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Packet:
    """A transportable message payload with bounded forwarding metadata."""

    message_id: str
    source: str
    destination: str
    payload: bytes
    hop_limit: int = 16
    packet_id: str = field(default_factory=lambda: str(uuid4()))
    version: int = 1

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.message_id, self.packet_id, self.source, self.destination)):
            raise ValueError("packet identifiers and endpoints must be non-empty")
        if not isinstance(self.payload, bytes):
            raise TypeError("payload must be bytes")
        if self.hop_limit < 0:
            raise ValueError("hop_limit cannot be negative")
        if self.version < 1:
            raise ValueError("version must be positive")

    def forwarded(self) -> "Packet":
        """Return a copy for the next relay, decrementing the hop limit."""
        if self.hop_limit == 0:
            raise ValueError("packet hop limit exhausted")
        return Packet(self.message_id, self.source, self.destination, self.payload,
                      self.hop_limit - 1, packet_id=self.packet_id, version=self.version)
