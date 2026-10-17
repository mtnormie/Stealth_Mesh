"""Tests for ML link-quality feature extraction, dataset splitting, training, fallback, and routing."""

from __future__ import annotations

import unittest

from experiments.compare_algorithms import compare_routing_algorithms
from ml.dataset import (
    DatasetSplit,
    LabeledLinkSample,
    generate_synthetic_dataset,
    split_dataset_by_group,
)
from ml.evaluate import compare_ml_with_baseline
from ml.features import LinkFeatures, extract_link_features
from ml.predict import BaselineLinkEstimator, MLLinkQualityPredictor
from ml.train import LogisticLinkQualityModel, train_logistic_model
from radio.link_quality import LinkObservation, LinkQualityTracker


class MLLinkQualityTests(unittest.TestCase):
    def test_feature_extraction_and_validation(self) -> None:
        tracker = LinkQualityTracker(window_size=5)
        self.assertIsNone(extract_link_features(tracker, "a", "b"))

        tracker.record(LinkObservation("a", "b", True, 0.05, attempts=1, rssi_dbm=-70.0, snr_db=10.0))
        tracker.record(LinkObservation("a", "b", True, 0.07, attempts=1, rssi_dbm=-72.0, snr_db=9.0))
        features = extract_link_features(tracker, "a", "b")
        self.assertIsNotNone(features)
        assert features is not None
        vec = features.to_vector()
        self.assertEqual(len(vec), 7)
        self.assertAlmostEqual(features.delivery_ratio, 1.0)

        with self.assertRaises(ValueError):
            LinkFeatures(delivery_ratio=1.5, mean_latency_seconds=0.1, retransmission_rate=0.0)
        with self.assertRaises(ValueError):
            LinkFeatures(delivery_ratio=0.8, mean_latency_seconds=-0.1, retransmission_rate=0.0)

    def test_group_split_prevents_data_leakage(self) -> None:
        dataset = generate_synthetic_dataset(num_groups=10, samples_per_group=5, seed=12)
        split = split_dataset_by_group(dataset, train_ratio=0.7, seed=12)
        train_groups = {s.group_id for s in split.train}
        eval_groups = {s.group_id for s in split.evaluation}
        self.assertTrue(train_groups.isdisjoint(eval_groups))

        # Explicitly constructing a split with overlapping group_ids must raise ValueError
        overlapping_sample = LabeledLinkSample(split.train[0].features, 1, split.train[0].group_id)
        with self.assertRaises(ValueError):
            DatasetSplit(train=split.train, evaluation=(overlapping_sample,))

    def test_logistic_model_training_and_fallback_behavior(self) -> None:
        dataset = generate_synthetic_dataset(num_groups=20, samples_per_group=8, seed=99)
        split = split_dataset_by_group(dataset, train_ratio=0.7, seed=99)
        model = train_logistic_model(split.train, learning_rate=0.2, epochs=250)
        predictor = MLLinkQualityPredictor(model=model)

        sample_features = split.evaluation[0].features
        pred = predictor.predict(sample_features)
        self.assertFalse(pred.used_fallback)
        self.assertEqual(pred.reason, "ml_model")
        self.assertGreater(pred.probability, 0.0)
        self.assertLess(pred.probability, 1.0)

        # Fallback when model is None
        fallback_predictor = MLLinkQualityPredictor(model=None)
        fb_res = fallback_predictor.predict(sample_features)
        self.assertTrue(fb_res.used_fallback)
        self.assertEqual(fb_res.reason, "model_unavailable_or_untrained")

        # Fallback when model is marked untrained
        untrained = LogisticLinkQualityModel(
            weights=model.weights,
            bias=model.bias,
            feature_means=model.feature_means,
            feature_stds=model.feature_stds,
            is_trained=False,
        )
        untrained_pred = MLLinkQualityPredictor(model=untrained).predict(sample_features)
        self.assertTrue(untrained_pred.used_fallback)
        self.assertEqual(untrained_pred.reason, "model_unavailable_or_untrained")

        # Fallback when features are missing
        missing_pred = predictor.predict(None)
        self.assertTrue(missing_pred.used_fallback)
        self.assertEqual(missing_pred.reason, "missing_or_invalid_features")

    def test_ml_outperforms_static_routing_on_degraded_rf_link(self) -> None:
        report = compare_routing_algorithms(message_count=30, max_retries=1, seed=42)
        # Static Dijkstra picks nominal low-cost path a -> b -> d despite heavy RF loss on (a, b)
        self.assertEqual(report.baseline_routing.selected_route, ("a", "b", "d"))
        # ML-assisted routing penalizes noisy link (a, b) and selects healthier path a -> c -> d
        self.assertEqual(report.ml_routing.selected_route, ("a", "c", "d"))
        self.assertGreater(report.ml_routing.delivery_ratio, report.baseline_routing.delivery_ratio)
        self.assertLess(report.ml_routing.modeled_latency_seconds, report.baseline_routing.modeled_latency_seconds)


if __name__ == "__main__":
    unittest.main()
