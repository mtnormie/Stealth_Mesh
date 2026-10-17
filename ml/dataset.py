"""Dataset schema, synthetic data generation, and leakage-resistant splits."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite
import random

from ml.features import LinkFeatures


@dataclass(frozen=True, slots=True)
class LabeledLinkSample:
    """Supervised training/evaluation sample with target delivery label in {0, 1}.

    ``group_id`` identifies the link episode or physical pair so dataset splits
    can isolate groups and prevent data leakage between training and evaluation.
    """

    features: LinkFeatures
    label: int
    group_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.features, LinkFeatures):
            raise TypeError("features must be a LinkFeatures instance")
        if isinstance(self.label, bool) or not isinstance(self.label, int) or self.label not in (0, 1):
            raise ValueError("label must be an integer 0 or 1")
        if not isinstance(self.group_id, str) or not self.group_id.strip():
            raise ValueError("group_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    """Disjoint training and evaluation datasets verified against group leakage."""

    train: tuple[LabeledLinkSample, ...]
    evaluation: tuple[LabeledLinkSample, ...]

    def __post_init__(self) -> None:
        if not self.train or not self.evaluation:
            raise ValueError("both train and evaluation splits must be non-empty")
        train_groups = {sample.group_id for sample in self.train}
        eval_groups = {sample.group_id for sample in self.evaluation}
        overlap = train_groups & eval_groups
        if overlap:
            raise ValueError(f"data leakage detected: overlapping group_ids {sorted(overlap)}")


def split_dataset_by_group(
    samples: Sequence[LabeledLinkSample],
    *,
    train_ratio: float = 0.7,
    seed: int = 42,
) -> DatasetSplit:
    """Partition samples by ``group_id`` so no group spans both train and evaluation."""
    if not samples:
        raise ValueError("samples must not be empty")
    if not isfinite(train_ratio) or not 0.1 <= train_ratio <= 0.9:
        raise ValueError("train_ratio must be between 0.1 and 0.9")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")

    for item in samples:
        if not isinstance(item, LabeledLinkSample):
            raise TypeError("all samples must be LabeledLinkSample instances")

    groups = sorted({item.group_id for item in samples})
    if len(groups) < 2:
        raise ValueError("at least 2 distinct group_ids are required for a group-isolated split")

    rng = random.Random(seed)
    rng.shuffle(groups)
    cutoff = max(1, min(len(groups) - 1, round(len(groups) * train_ratio)))
    train_groups = set(groups[:cutoff])

    train_samples = tuple(item for item in samples if item.group_id in train_groups)
    eval_samples = tuple(item for item in samples if item.group_id not in train_groups)
    return DatasetSplit(train=train_samples, evaluation=eval_samples)


def generate_synthetic_dataset(
    *,
    num_groups: int = 24,
    samples_per_group: int = 10,
    seed: int = 42,
) -> tuple[LabeledLinkSample, ...]:
    """Generate a reproducible dataset of link regimes (healthy, noisy, degraded)."""
    if not isinstance(num_groups, int) or isinstance(num_groups, bool) or num_groups < 2:
        raise ValueError("num_groups must be an integer >= 2")
    if not isinstance(samples_per_group, int) or isinstance(samples_per_group, bool) or samples_per_group < 1:
        raise ValueError("samples_per_group must be a positive integer")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")

    rng = random.Random(seed)
    dataset: list[LabeledLinkSample] = []

    for group_idx in range(num_groups):
        group_id = f"link_episode_{group_idx:03d}"
        # True latent quality of this link episode
        base_quality = rng.uniform(0.1, 0.95)
        for _ in range(samples_per_group):
            delivery_ratio = max(0.0, min(1.0, base_quality + rng.uniform(-0.12, 0.12)))
            recent_availability = max(0.0, min(1.0, base_quality + rng.uniform(-0.15, 0.15)))
            retransmission_rate = max(0.0, min(1.0, (1.0 - base_quality) * 0.7 + rng.uniform(-0.08, 0.08)))
            rssi_norm = max(0.0, min(1.0, base_quality * 0.85 + rng.uniform(-0.1, 0.1)))
            snr_norm = max(0.0, min(1.0, base_quality * 0.8 + rng.uniform(-0.1, 0.1)))
            stability = max(0.0, min(1.0, 1.0 - abs(0.5 - base_quality) * 0.5 + rng.uniform(-0.1, 0.1)))
            latency = max(0.01, (1.1 - base_quality) * 0.35 + rng.uniform(0.0, 0.08))

            # True next-packet delivery probability depends on both historical ratio and radio SNR/RSSI/stability
            true_prob = max(
                0.02,
                min(
                    0.98,
                    0.35 * delivery_ratio
                    + 0.25 * rssi_norm
                    + 0.20 * snr_norm
                    + 0.15 * recent_availability
                    - 0.15 * retransmission_rate
                    + 0.05 * stability,
                ),
            )
            label = 1 if rng.random() < true_prob else 0
            features = LinkFeatures(
                delivery_ratio=delivery_ratio,
                mean_latency_seconds=latency,
                retransmission_rate=retransmission_rate,
                rssi_normalized=rssi_norm,
                snr_normalized=snr_norm,
                recent_availability=recent_availability,
                stability_score=stability,
            )
            dataset.append(LabeledLinkSample(features=features, label=label, group_id=group_id))

    return tuple(dataset)
