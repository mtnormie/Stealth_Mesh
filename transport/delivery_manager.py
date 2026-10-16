"""Bounded-retry, hop-by-hop message delivery coordinator."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from core.packet import Packet
from transport.acknowledgements import AcknowledgementTracker
from transport.deduplication import Deduplicator
from transport.retry_policy import RetryPolicy


class DeliveryStatus(str, Enum):
    """Outcome state of a message delivery attempt."""

    DELIVERED = "delivered"
    FAILED = "failed"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Final delivery state and count of attempted radio hops."""

    status: DeliveryStatus
    attempts: int

    def __post_init__(self) -> None:
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int) or self.attempts < 0:
            raise ValueError("attempts cannot be negative")


class DeliveryManager:
    """Deliver packets over a supplied route using an injected hop function.

    The hop callback returns true only when that hop was received. Destination
    acknowledgement is local simulated state, not a separate physical return
    transmission.
    """

    def __init__(
        self,
        retry_policy: RetryPolicy | None = None,
        deduplicator: Deduplicator | None = None,
        acknowledgements: AcknowledgementTracker | None = None,
    ) -> None:
        self.retry_policy = retry_policy or RetryPolicy()
        self.deduplicator = deduplicator or Deduplicator()
        self.acknowledgements = acknowledgements or AcknowledgementTracker()

    def deliver(
        self,
        packet: Packet,
        route: Sequence[str],
        transmit: Callable[[str, str], bool],
    ) -> DeliveryResult:
        """Attempt delivery over every adjacent pair in ``route``."""
        if not isinstance(packet, Packet):
            raise TypeError("packet must be a Packet instance")
        if len(route) < 1 or route[0] != packet.source or route[-1] != packet.destination:
            raise ValueError("route must start at source and end at destination")
        if self.deduplicator.contains(packet.message_id):
            return DeliveryResult(DeliveryStatus.DUPLICATE, 0)

        attempts = 0
        current_packet = packet
        for source, destination in zip(route, route[1:]):
            if current_packet.hop_limit == 0:
                return DeliveryResult(DeliveryStatus.FAILED, attempts)
            delivered = False
            for _ in range(self.retry_policy.max_attempts):
                attempts += 1
                if transmit(source, destination):
                    delivered = True
                    break
            if not delivered:
                return DeliveryResult(DeliveryStatus.FAILED, attempts)
            current_packet = current_packet.forwarded()

        self.deduplicator.remember(packet.message_id)
        self.acknowledgements.acknowledge(packet.message_id)
        return DeliveryResult(DeliveryStatus.DELIVERED, attempts)
