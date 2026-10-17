"""Evaluation metrics comparing ML link-quality predictions against a baseline."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import log
import time

from ml.dataset import LabeledLinkSample
from ml.predict import BaselineLinkEstimator, MLLinkQualityPredictor


@dataclass(frozen=True, slots=True)
class ModelEvaluationMetrics:
    """Held-out evaluation metrics for a link-quality estimator."""

    sample_count: int
    accuracy: float
    brier_score: float
    log_loss: float
    fallback_count: int
    inference_time_seconds: float


@dataclass(frozen=True, slots=True)
class EstimatorComparison:
    """Side-by-side comparison of ML estimator and non-ML baseline on held-out data."""

    ml_metrics: ModelEvaluationMetrics
    baseline_metrics: ModelEvaluationMetrics

    @property
    def brier_improvement(self) -> float:
        """Positive value indicates ML achieved a lower (better) Brier score than baseline."""
        return self.baseline_metrics.brier_score - self.ml_metrics.brier_score


def evaluate_predictor(
    samples: Sequence[LabeledLinkSample],
    predictor: MLLinkQualityPredictor,
) -> ModelEvaluationMetrics:
    """Evaluate a predictor on a held-out sequence of LabeledLinkSample items."""
    if not samples:
        raise ValueError("samples must not be empty")
    if not isinstance(predictor, MLLinkQualityPredictor):
        raise TypeError("predictor must be an MLLinkQualityPredictor")

    correct = 0
    brier_sum = 0.0
    logloss_sum = 0.0
    fallbacks = 0
    eps = 1e-12

    start = time.perf_counter()
    for sample in samples:
        if not isinstance(sample, LabeledLinkSample):
            raise TypeError("samples must contain LabeledLinkSample instances")
        res = predictor.predict(sample.features)
        if res.used_fallback:
            fallbacks += 1
        p = max(eps, min(1.0 - eps, res.probability))
        y = sample.label
        predicted_label = 1 if p >= 0.5 else 0
        if predicted_label == y:
            correct += 1
        brier_sum += (p - y) ** 2
        logloss_sum += -(y * log(p) + (1 - y) * log(1.0 - p))
    elapsed = time.perf_counter() - start

    n = len(samples)
    return ModelEvaluationMetrics(
        sample_count=n,
        accuracy=correct / n,
        brier_score=brier_sum / n,
        log_loss=logloss_sum / n,
        fallback_count=fallbacks,
        inference_time_seconds=elapsed,
    )


def compare_ml_with_baseline(
    evaluation_samples: Sequence[LabeledLinkSample],
    ml_predictor: MLLinkQualityPredictor,
    *,
    baseline: BaselineLinkEstimator | None = None,
) -> EstimatorComparison:
    """Compare a trained ML predictor with the non-ML baseline on held-out samples."""
    baseline_predictor = MLLinkQualityPredictor(model=None, baseline=baseline)
    ml_metrics = evaluate_predictor(evaluation_samples, ml_predictor)
    base_metrics = evaluate_predictor(evaluation_samples, baseline_predictor)
    return EstimatorComparison(ml_metrics=ml_metrics, baseline_metrics=base_metrics)
