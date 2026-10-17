"""Link-quality prediction with deterministic baseline and automatic fallback."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ml.features import LinkFeatures
from ml.train import LogisticLinkQualityModel


@dataclass(frozen=True, slots=True)
class PredictionResult:
    """Link delivery probability estimate with explicit fallback provenance."""

    probability: float
    used_fallback: bool
    reason: str

    def __post_init__(self) -> None:
        if not isfinite(self.probability) or not 0.0 <= self.probability <= 1.0:
            raise ValueError("probability must be finite and within [0.0, 1.0]")


class BaselineLinkEstimator:
    """Simple deterministic non-ML baseline using historical delivery ratio."""

    def predict_proba(self, features: LinkFeatures) -> float:
        if not isinstance(features, LinkFeatures):
            raise TypeError("features must be a LinkFeatures instance")
        # Weighted combination of empirical delivery ratio (70%) and recent availability (30%)
        score = 0.7 * features.delivery_ratio + 0.3 * features.recent_availability
        return max(0.01, min(0.99, score))


class MLLinkQualityPredictor:
    """Predict link delivery probability with guaranteed fallback to baseline."""

    def __init__(
        self,
        model: LogisticLinkQualityModel | None = None,
        *,
        baseline: BaselineLinkEstimator | None = None,
        default_probability: float = 0.5,
    ) -> None:
        if not isfinite(default_probability) or not 0.0 < default_probability <= 1.0:
            raise ValueError("default_probability must be in (0.0, 1.0]")
        self.model = model
        self.baseline = baseline or BaselineLinkEstimator()
        self.default_probability = float(default_probability)

    def predict(self, features: LinkFeatures | None) -> PredictionResult:
        """Return a validated PredictionResult, falling back safely when needed."""
        if features is None or not isinstance(features, LinkFeatures):
            return PredictionResult(
                probability=self.default_probability,
                used_fallback=True,
                reason="missing_or_invalid_features",
            )

        if self.model is None or not getattr(self.model, "is_trained", False):
            return PredictionResult(
                probability=self.baseline.predict_proba(features),
                used_fallback=True,
                reason="model_unavailable_or_untrained",
            )

        try:
            prob = float(self.model.predict_proba(features))
        except Exception:
            return PredictionResult(
                probability=self.baseline.predict_proba(features),
                used_fallback=True,
                reason="model_inference_error",
            )

        if not isfinite(prob) or not 0.0 <= prob <= 1.0:
            return PredictionResult(
                probability=self.baseline.predict_proba(features),
                used_fallback=True,
                reason="invalid_model_output",
            )

        return PredictionResult(
            probability=prob,
            used_fallback=False,
            reason="ml_model",
        )
