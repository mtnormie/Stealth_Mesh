"""Link-quality observations and rolling link statistics."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class LinkObservation:
    """Single transmission observation on a directed or undirected radio link."""

    source: str
    destination: str
    delivered: bool
    latency_seconds: float
    attempts: int = 1
    rssi_dbm: float | None = None
    snr_db: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        if not isinstance(self.destination, str) or not self.destination.strip():
            raise ValueError("destination must be a non-empty string")
        if self.source == self.destination:
            raise ValueError("source and destination must be distinct")
        if not isinstance(self.delivered, bool):
            raise TypeError("delivered must be a bool")
        if not isfinite(self.latency_seconds) or self.latency_seconds < 0.0:
            raise ValueError("latency_seconds must be finite and non-negative")
        if not isinstance(self.attempts, int) or isinstance(self.attempts, bool) or self.attempts < 1:
            raise ValueError("attempts must be a positive integer")
        if self.rssi_dbm is not None and (not isfinite(self.rssi_dbm) or not -150.0 <= self.rssi_dbm <= 0.0):
            raise ValueError("rssi_dbm must be finite and within [-150.0, 0.0] dBm")
        if self.snr_db is not None and (not isfinite(self.snr_db) or not -40.0 <= self.snr_db <= 40.0):
            raise ValueError("snr_db must be finite and within [-40.0, 40.0] dB")


@dataclass(frozen=True, slots=True)
class LinkQualitySummary:
    """Aggregated link statistics over a sliding observation window."""

    sample_count: int
    delivery_ratio: float
    mean_latency_seconds: float
    retransmission_rate: float
    mean_rssi_dbm: float | None
    mean_snr_db: float | None
    recent_availability: float
    stability_score: float


class LinkQualityTracker:
    """Track rolling link observations for routing and ML feature extraction."""

    def __init__(self, *, window_size: int = 20) -> None:
        if not isinstance(window_size, int) or isinstance(window_size, bool) or window_size < 1:
            raise ValueError("window_size must be a positive integer")
        self.window_size = window_size
        self._history: dict[tuple[str, str], deque[LinkObservation]] = {}

    @staticmethod
    def _normalize_key(first: str, second: str) -> tuple[str, str]:
        if not isinstance(first, str) or not first.strip() or not isinstance(second, str) or not second.strip():
            raise ValueError("link endpoints must be non-empty strings")
        if first == second:
            raise ValueError("link endpoints must be distinct")
        return (first, second) if first < second else (second, first)

    def record(self, observation: LinkObservation) -> None:
        """Append a validated link observation to the sliding window."""
        if not isinstance(observation, LinkObservation):
            raise TypeError("observation must be a LinkObservation")
        key = self._normalize_key(observation.source, observation.destination)
        bucket = self._history.get(key)
        if bucket is None:
            bucket = deque(maxlen=self.window_size)
            self._history[key] = bucket
        bucket.append(observation)

    def observations(self, first: str, second: str) -> tuple[LinkObservation, ...]:
        """Return chronological observations for an undirected link."""
        key = self._normalize_key(first, second)
        bucket = self._history.get(key)
        return tuple(bucket) if bucket else ()

    def summary(self, first: str, second: str) -> LinkQualitySummary | None:
        """Compute rolling summary statistics for a link, or None if unobserved."""
        obs = self.observations(first, second)
        if not obs:
            return None
        n = len(obs)
        delivered_flags = [1.0 if item.delivered else 0.0 for item in obs]
        delivery_ratio = sum(delivered_flags) / n
        mean_latency = sum(item.latency_seconds for item in obs) / n
        total_attempts = sum(item.attempts for item in obs)
        total_retransmissions = sum(max(0, item.attempts - 1) for item in obs)
        retransmission_rate = total_retransmissions / total_attempts if total_attempts > 0 else 0.0

        rssi_values = [item.rssi_dbm for item in obs if item.rssi_dbm is not None]
        snr_values = [item.snr_db for item in obs if item.snr_db is not None]
        mean_rssi = sum(rssi_values) / len(rssi_values) if rssi_values else None
        mean_snr = sum(snr_values) / len(snr_values) if snr_values else None

        recent_slice = delivered_flags[-min(5, n):]
        recent_availability = sum(recent_slice) / len(recent_slice)

        # Bernoulli variance p*(1-p) scaled to [0, 1] where 1.0 is completely stable
        variance = sum((flag - delivery_ratio) ** 2 for flag in delivered_flags) / n
        stability_score = max(0.0, min(1.0, 1.0 - 4.0 * variance))

        return LinkQualitySummary(
            sample_count=n,
            delivery_ratio=delivery_ratio,
            mean_latency_seconds=mean_latency,
            retransmission_rate=retransmission_rate,
            mean_rssi_dbm=mean_rssi,
            mean_snr_db=mean_snr,
            recent_availability=recent_availability,
            stability_score=stability_score,
        )
