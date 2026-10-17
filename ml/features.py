"""Explicit link-quality feature vector definition and extraction."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from radio.link_quality import LinkQualitySummary, LinkQualityTracker

FEATURE_NAMES: tuple[str, ...] = (
    "delivery_ratio",
    "mean_latency_seconds",
    "retransmission_rate",
    "rssi_normalized",
    "snr_normalized",
    "recent_availability",
    "stability_score",
)


def _normalize_rssi(rssi_dbm: float | None) -> float:
    """Map RSSI in [-140, -40] dBm to [0.0, 1.0], defaulting to 0.5 when absent."""
    if rssi_dbm is None:
        return 0.5
    clamped = max(-140.0, min(-40.0, float(rssi_dbm)))
    return (clamped + 140.0) / 100.0


def _normalize_snr(snr_db: float | None) -> float:
    """Map SNR in [-20, 20] dB to [0.0, 1.0], defaulting to 0.5 when absent."""
    if snr_db is None:
        return 0.5
    clamped = max(-20.0, min(20.0, float(snr_db)))
    return (clamped + 20.0) / 40.0


@dataclass(frozen=True, slots=True)
class LinkFeatures:
    """Validated numerical features describing recent radio link behavior."""

    delivery_ratio: float
    mean_latency_seconds: float
    retransmission_rate: float
    rssi_normalized: float = 0.5
    snr_normalized: float = 0.5
    recent_availability: float = 1.0
    stability_score: float = 1.0

    def __post_init__(self) -> None:
        for field_name in (
            "delivery_ratio",
            "retransmission_rate",
            "rssi_normalized",
            "snr_normalized",
            "recent_availability",
            "stability_score",
        ):
            val = getattr(self, field_name)
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not isfinite(val):
                raise ValueError(f"{field_name} must be a finite number")
            if not 0.0 <= float(val) <= 1.0:
                raise ValueError(f"{field_name} must be within [0.0, 1.0]")
        if (
            isinstance(self.mean_latency_seconds, bool)
            or not isinstance(self.mean_latency_seconds, (int, float))
            or not isfinite(self.mean_latency_seconds)
            or self.mean_latency_seconds < 0.0
        ):
            raise ValueError("mean_latency_seconds must be finite and non-negative")

    def to_vector(self) -> tuple[float, float, float, float, float, float, float]:
        """Return features in the canonical order defined by FEATURE_NAMES."""
        return (
            float(self.delivery_ratio),
            float(self.mean_latency_seconds),
            float(self.retransmission_rate),
            float(self.rssi_normalized),
            float(self.snr_normalized),
            float(self.recent_availability),
            float(self.stability_score),
        )

    @classmethod
    def from_summary(cls, summary: LinkQualitySummary) -> LinkFeatures:
        """Convert a LinkQualitySummary into a normalized LinkFeatures instance."""
        if not isinstance(summary, LinkQualitySummary):
            raise TypeError("summary must be a LinkQualitySummary")
        return cls(
            delivery_ratio=summary.delivery_ratio,
            mean_latency_seconds=summary.mean_latency_seconds,
            retransmission_rate=summary.retransmission_rate,
            rssi_normalized=_normalize_rssi(summary.mean_rssi_dbm),
            snr_normalized=_normalize_snr(summary.mean_snr_db),
            recent_availability=summary.recent_availability,
            stability_score=summary.stability_score,
        )


def extract_link_features(
    tracker: LinkQualityTracker,
    first: str,
    second: str,
) -> LinkFeatures | None:
    """Extract normalized LinkFeatures for a link, or None if no observations exist."""
    if not isinstance(tracker, LinkQualityTracker):
        raise TypeError("tracker must be a LinkQualityTracker")
    summary = tracker.summary(first, second)
    if summary is None:
        return None
    return LinkFeatures.from_summary(summary)
