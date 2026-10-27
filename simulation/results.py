"""Result records for a reproducible simulation run."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from monitoring.metrics import Metrics
from transport.delivery_manager import DeliveryResult


@dataclass(frozen=True, slots=True)
class MessageRun:
    """Outcome and route selected for one message."""

    message_id: str
    route: tuple[str, ...] | None
    delivery: DeliveryResult
    modeled_latency_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.message_id, str) or not self.message_id.strip():
            raise ValueError("message_id must be non-empty")
        if (
            isinstance(self.modeled_latency_seconds, bool)
            or not isinstance(self.modeled_latency_seconds, (int, float))
            or not isfinite(self.modeled_latency_seconds)
            or self.modeled_latency_seconds < 0
        ):
            raise ValueError("modeled_latency_seconds must be finite and non-negative")


@dataclass(slots=True)
class SimulationResult:
    """Ordered message outcomes and aggregate metrics."""

    messages: list[MessageRun] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)
