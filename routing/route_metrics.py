"""Route cost calculation combining base topology cost and link-quality estimates."""

from __future__ import annotations

from math import isfinite


def compute_link_cost(
    base_cost: float,
    estimated_delivery_probability: float | None = None,
    *,
    penalty_weight: float = 2.0,
    min_probability: float = 0.05,
) -> float:
    """Combine a positive base cost with an optional delivery probability estimate.

    When ``estimated_delivery_probability`` is ``None`` or outside ``[0.0, 1.0]``
    (or non-finite), the function safely falls back to ``base_cost`` so that an
    unavailable or invalid ML prediction never breaks routing.
    """
    if not isfinite(base_cost) or base_cost <= 0.0:
        raise ValueError("base_cost must be finite and positive")
    if not isfinite(penalty_weight) or penalty_weight < 0.0:
        raise ValueError("penalty_weight must be finite and non-negative")
    if not isfinite(min_probability) or not 0.0 < min_probability <= 1.0:
        raise ValueError("min_probability must be in (0.0, 1.0]")

    if estimated_delivery_probability is None:
        return float(base_cost)
    if isinstance(estimated_delivery_probability, bool) or not isinstance(
        estimated_delivery_probability, (int, float)
    ):
        return float(base_cost)
    if not isfinite(estimated_delivery_probability) or not 0.0 <= estimated_delivery_probability <= 1.0:
        return float(base_cost)

    clamped_prob = max(min_probability, float(estimated_delivery_probability))
    expected_transmissions_penalty = (1.0 / clamped_prob) - 1.0
    return float(base_cost) + penalty_weight * expected_transmissions_penalty
