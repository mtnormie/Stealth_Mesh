"""Counters and latency aggregates for prototype simulations."""

from dataclasses import dataclass


@dataclass(slots=True)
class Metrics:
    """Aggregate delivery outcomes, attempts, and modeled transmission latency."""

    messages_sent: int = 0
    messages_delivered: int = 0
    messages_failed: int = 0
    retransmissions: int = 0
    modeled_latency_seconds: float = 0.0

    @property
    def delivery_ratio(self) -> float:
        """Return delivered/sent, or zero before any messages are sent."""
        return self.messages_delivered / self.messages_sent if self.messages_sent else 0.0

    def record(self, *, delivered: bool, attempts: int, modeled_latency_seconds: float) -> None:
        """Record one message outcome and its transmission effort."""
        if attempts < 0 or modeled_latency_seconds < 0:
            raise ValueError("attempts and modeled latency cannot be negative")
        self.messages_sent += 1
        if delivered:
            self.messages_delivered += 1
        else:
            self.messages_failed += 1
        self.retransmissions += max(0, attempts - 1)
        self.modeled_latency_seconds += modeled_latency_seconds
