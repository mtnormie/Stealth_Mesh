"""Seedable radio-link simulator for software experiments only."""

from dataclasses import dataclass
from math import isfinite
import random

from core.network import Network


@dataclass(frozen=True, slots=True)
class TransmissionResult:
    """Outcome of one simulated hop; latency is modeled, not wall-clock time."""

    delivered: bool
    latency_seconds: float
    reason: str


class RadioSimulator:
    """Simulate a network hop with configurable latency, loss, and availability."""

    def __init__(self, network: Network, *, latency_range: tuple[float, float] = (0.0, 0.0),
                 packet_loss_probability: float = 0.0, seed: int | None = None) -> None:
        low, high = latency_range
        if not isfinite(low) or not isfinite(high) or low < 0 or high < low:
            raise ValueError("latency_range must have finite values with 0 <= minimum <= maximum")
        if not isfinite(packet_loss_probability) or not 0.0 <= packet_loss_probability <= 1.0:
            raise ValueError("packet_loss_probability must be between 0 and 1")
        self.network = network
        self.latency_range = (float(low), float(high))
        self.packet_loss_probability = packet_loss_probability
        self._random = random.Random(seed)

    def transmit(self, source: str, destination: str) -> TransmissionResult:
        """Attempt a single direct hop and return its modeled outcome."""
        if source not in self.network.nodes or destination not in self.network.nodes:
            raise ValueError("source and destination must be registered nodes")
        latency = self._random.uniform(*self.latency_range)
        if not self.network.nodes[source].available or not self.network.nodes[destination].available:
            return TransmissionResult(False, latency, "node_unavailable")
        if not self.network.topology.has_link(source, destination):
            return TransmissionResult(False, latency, "no_link")
        if self._random.random() < self.packet_loss_probability:
            return TransmissionResult(False, latency, "packet_loss")
        return TransmissionResult(True, latency, "delivered")
