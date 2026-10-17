"""Pure-Python L2-regularized logistic regression training for link quality."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import exp, isfinite, sqrt

from ml.dataset import LabeledLinkSample
from ml.features import FEATURE_NAMES, LinkFeatures


def _sigmoid(z: float) -> float:
    if z >= 0.0:
        ez = exp(-min(z, 60.0))
        return 1.0 / (1.0 + ez)
    ez = exp(max(z, -60.0))
    return ez / (1.0 + ez)


@dataclass(frozen=True, slots=True)
class LogisticLinkQualityModel:
    """Trained standardized logistic regression model for delivery probability."""

    weights: tuple[float, ...]
    bias: float
    feature_means: tuple[float, ...]
    feature_stds: tuple[float, ...]
    is_trained: bool = True

    def __post_init__(self) -> None:
        dim = len(FEATURE_NAMES)
        if len(self.weights) != dim or len(self.feature_means) != dim or len(self.feature_stds) != dim:
            raise ValueError(f"model vectors must have length {dim}")
        if not isfinite(self.bias):
            raise ValueError("bias must be finite")
        for vec_name, vec in (
            ("weights", self.weights),
            ("feature_means", self.feature_means),
            ("feature_stds", self.feature_stds),
        ):
            if any(not isfinite(v) for v in vec):
                raise ValueError(f"{vec_name} must contain only finite numbers")
        if any(s <= 0.0 for s in self.feature_stds):
            raise ValueError("feature_stds must be strictly positive")

    def predict_proba(self, features: LinkFeatures) -> float:
        """Return estimated probability of delivery in (0.0, 1.0)."""
        if not self.is_trained:
            raise RuntimeError("model is not trained")
        if not isinstance(features, LinkFeatures):
            raise TypeError("features must be a LinkFeatures instance")
        raw = features.to_vector()
        z = self.bias
        for x, mean, std, w in zip(raw, self.feature_means, self.feature_stds, self.weights):
            z += w * ((x - mean) / std)
        return _sigmoid(z)


def train_logistic_model(
    samples: Sequence[LabeledLinkSample],
    *,
    learning_rate: float = 0.15,
    epochs: int = 250,
    l2_penalty: float = 0.01,
) -> LogisticLinkQualityModel:
    """Fit a standardized L2-regularized logistic regression model deterministically."""
    if not samples or len(samples) < 4:
        raise ValueError("at least 4 training samples are required")
    if not isfinite(learning_rate) or learning_rate <= 0.0:
        raise ValueError("learning_rate must be finite and positive")
    if not isinstance(epochs, int) or isinstance(epochs, bool) or epochs < 1:
        raise ValueError("epochs must be a positive integer")
    if not isfinite(l2_penalty) or l2_penalty < 0.0:
        raise ValueError("l2_penalty must be finite and non-negative")

    for sample in samples:
        if not isinstance(sample, LabeledLinkSample):
            raise TypeError("samples must contain LabeledLinkSample instances")

    n = len(samples)
    dim = len(FEATURE_NAMES)
    raw_matrix = [sample.features.to_vector() for sample in samples]
    labels = [float(sample.label) for sample in samples]

    means: list[float] = []
    stds: list[float] = []
    for col in range(dim):
        col_vals = [row[col] for row in raw_matrix]
        mean_val = sum(col_vals) / n
        variance = sum((v - mean_val) ** 2 for v in col_vals) / n
        std_val = sqrt(variance) if variance > 1e-12 else 1.0
        means.append(mean_val)
        stds.append(std_val)

    standardized = [
        tuple((row[col] - means[col]) / stds[col] for col in range(dim))
        for row in raw_matrix
    ]

    weights = [0.0] * dim
    bias = 0.0

    for _ in range(epochs):
        grad_w = [0.0] * dim
        grad_b = 0.0
        for x_vec, y in zip(standardized, labels):
            z = bias + sum(w * x for w, x in zip(weights, x_vec))
            pred = _sigmoid(z)
            err = pred - y
            grad_b += err
            for col in range(dim):
                grad_w[col] += err * x_vec[col]

        bias -= learning_rate * (grad_b / n)
        for col in range(dim):
            reg_term = l2_penalty * weights[col]
            weights[col] -= learning_rate * ((grad_w[col] / n) + reg_term)

    return LogisticLinkQualityModel(
        weights=tuple(weights),
        bias=bias,
        feature_means=tuple(means),
        feature_stds=tuple(stds),
        is_trained=True,
    )
