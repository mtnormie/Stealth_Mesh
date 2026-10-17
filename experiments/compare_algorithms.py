"""Compare deterministic baseline routing against ML-assisted link-quality routing."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
import time

from core.network import Network
from core.node import Node
from core.packet import Packet
from ml.dataset import generate_synthetic_dataset, split_dataset_by_group
from ml.evaluate import EstimatorComparison, compare_ml_with_baseline
from ml.features import extract_link_features
from ml.predict import MLLinkQualityPredictor
from ml.train import train_logistic_model
from radio.link_quality import LinkObservation, LinkQualityTracker
from routing.dijkstra import shortest_path
from routing.route_manager import RouteManager
from transport.delivery_manager import DeliveryManager, DeliveryStatus
from transport.retry_policy import RetryPolicy


@dataclass(frozen=True, slots=True)
class RoutingExperimentMetrics:
    """Performance metrics for one routing strategy on the heterogeneous-link testbed."""

    strategy_name: str
    messages_sent: int
    messages_delivered: int
    delivery_ratio: float
    retransmissions: int
    modeled_latency_seconds: float
    computation_time_seconds: float
    selected_route: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class AlgorithmComparisonReport:
    """Full comparison report between static baseline and ML-assisted routing."""

    seed: int
    estimator_comparison: EstimatorComparison
    baseline_routing: RoutingExperimentMetrics
    ml_routing: RoutingExperimentMetrics

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "estimator_evaluation": {
                "sample_count": self.estimator_comparison.ml_metrics.sample_count,
                "ml_accuracy": round(self.estimator_comparison.ml_metrics.accuracy, 4),
                "ml_brier_score": round(self.estimator_comparison.ml_metrics.brier_score, 4),
                "baseline_accuracy": round(self.estimator_comparison.baseline_metrics.accuracy, 4),
                "baseline_brier_score": round(self.estimator_comparison.baseline_metrics.brier_score, 4),
                "brier_improvement": round(self.estimator_comparison.brier_improvement, 4),
            },
            "baseline_routing": {
                "delivery_ratio": round(self.baseline_routing.delivery_ratio, 4),
                "messages_delivered": self.baseline_routing.messages_delivered,
                "retransmissions": self.baseline_routing.retransmissions,
                "modeled_latency_seconds": round(self.baseline_routing.modeled_latency_seconds, 4),
                "computation_time_seconds": round(self.baseline_routing.computation_time_seconds, 6),
                "selected_route": list(self.baseline_routing.selected_route or ()),
            },
            "ml_routing": {
                "delivery_ratio": round(self.ml_routing.delivery_ratio, 4),
                "messages_delivered": self.ml_routing.messages_delivered,
                "retransmissions": self.ml_routing.retransmissions,
                "modeled_latency_seconds": round(self.ml_routing.modeled_latency_seconds, 4),
                "computation_time_seconds": round(self.ml_routing.computation_time_seconds, 6),
                "selected_route": list(self.ml_routing.selected_route or ()),
            },
        }


def _build_heterogeneous_mesh() -> tuple[Network, dict[tuple[str, str], tuple[float, float, float, float]]]:
    """Create a 4-node diamond network where the nominally cheaper path is RF-degraded.

    Link profile tuple: ``(loss_prob, latency_s, rssi_dbm, snr_db)``.
    """
    network = Network()
    for node_id in ("a", "b", "c", "d"):
        network.add_node(Node(node_id))
    # Nominal base cost prefers a -> b -> d (2.0) over a -> c -> d (2.6)
    network.add_link("a", "b", 1.0)
    network.add_link("b", "d", 1.0)
    network.add_link("a", "c", 1.3)
    network.add_link("c", "d", 1.3)

    link_profiles: dict[tuple[str, str], tuple[float, float, float, float]] = {
        ("a", "b"): (0.65, 0.25, -118.0, -11.0),  # Degraded noisy link
        ("b", "d"): (0.10, 0.08, -82.0, 5.0),
        ("a", "c"): (0.04, 0.06, -70.0, 10.0),    # Healthy link
        ("c", "d"): (0.04, 0.06, -72.0, 9.5),     # Healthy link
    }
    return network, link_profiles


def _seed_link_observations(
    tracker: LinkQualityTracker,
    link_profiles: dict[tuple[str, str], tuple[float, float, float, float]],
    *,
    warmup_samples: int = 10,
    seed: int = 42,
) -> None:
    rng = random.Random(seed)
    for (u, v), (loss_prob, latency_s, rssi_dbm, snr_db) in sorted(link_profiles.items()):
        for _ in range(warmup_samples):
            delivered = rng.random() >= loss_prob
            attempts = 1 if delivered else 2
            tracker.record(
                LinkObservation(
                    source=u,
                    destination=v,
                    delivered=delivered,
                    latency_seconds=latency_s,
                    attempts=attempts,
                    rssi_dbm=rssi_dbm + rng.uniform(-2.0, 2.0),
                    snr_db=snr_db + rng.uniform(-1.0, 1.0),
                )
            )


def compare_routing_algorithms(
    *,
    message_count: int = 30,
    max_retries: int = 1,
    seed: int = 42,
) -> AlgorithmComparisonReport:
    """Train ML link-quality model on leakage-free split and compare routing performance."""
    if not isinstance(message_count, int) or isinstance(message_count, bool) or message_count < 1:
        raise ValueError("message_count must be a positive integer")
    if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 0:
        raise ValueError("max_retries must be a non-negative integer")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")

    # 1. Train and evaluate ML model on group-disjoint synthetic dataset
    dataset = generate_synthetic_dataset(num_groups=30, samples_per_group=10, seed=seed)
    split = split_dataset_by_group(dataset, train_ratio=0.7, seed=seed)
    model = train_logistic_model(split.train, learning_rate=0.2, epochs=300, l2_penalty=0.01)
    predictor = MLLinkQualityPredictor(model=model)
    estimator_comparison = compare_ml_with_baseline(split.evaluation, predictor)

    # 2. Evaluate Static Baseline vs ML-Assisted Routing on the heterogeneous testbed
    network, link_profiles = _build_heterogeneous_mesh()
    tracker = LinkQualityTracker(window_size=15)
    _seed_link_observations(tracker, link_profiles, warmup_samples=10, seed=seed)

    def _run_strategy(*, use_ml: bool) -> RoutingExperimentMetrics:
        rng = random.Random(seed + 100)
        delivery_mgr = DeliveryManager(RetryPolicy(max_retries=max_retries))

        def link_quality_cb(u: str, v: str) -> float | None:
            features = extract_link_features(tracker, u, v)
            return predictor.predict(features).probability

        route_mgr = RouteManager(
            network,
            link_quality_fn=link_quality_cb if use_ml else None,
            penalty_weight=2.5,
        )

        delivered_count = 0
        retransmissions = 0
        total_latency = 0.0
        selected_route: tuple[str, ...] | None = None

        t0 = time.perf_counter()
        for idx in range(1, message_count + 1):
            pkt = Packet(f"cmp-{idx}", "a", "d", b"probe")
            if use_ml:
                route = route_mgr.find_route("a", "d")
            else:
                route = shortest_path(network.topology, "a", "d")
            if route is not None and selected_route is None:
                selected_route = tuple(route)

            if route is None:
                continue

            msg_latency = 0.0

            def hop_tx(src: str, dst: str) -> bool:
                nonlocal msg_latency
                key = (src, dst) if (src, dst) in link_profiles else (dst, src)
                loss_prob, lat_s, _, _ = link_profiles[key]
                msg_latency += lat_s
                return rng.random() >= loss_prob

            outcome = delivery_mgr.deliver(pkt, route, hop_tx)
            if outcome.status is DeliveryStatus.DELIVERED:
                delivered_count += 1
            retransmissions += max(0, outcome.attempts - (len(route) - 1))
            total_latency += msg_latency
        elapsed = time.perf_counter() - t0

        return RoutingExperimentMetrics(
            strategy_name="ml_assisted" if use_ml else "static_dijkstra",
            messages_sent=message_count,
            messages_delivered=delivered_count,
            delivery_ratio=delivered_count / message_count,
            retransmissions=retransmissions,
            modeled_latency_seconds=total_latency,
            computation_time_seconds=elapsed,
            selected_route=selected_route,
        )

    baseline_metrics = _run_strategy(use_ml=False)
    ml_metrics = _run_strategy(use_ml=True)

    return AlgorithmComparisonReport(
        seed=seed,
        estimator_comparison=estimator_comparison,
        baseline_routing=baseline_metrics,
        ml_routing=ml_metrics,
    )


def main(output_path: str | Path | None = None) -> AlgorithmComparisonReport:
    """Run the reproducible baseline-vs-ML comparison and optionally save JSON output."""
    report = compare_routing_algorithms(message_count=30, max_retries=1, seed=42)
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    summary = main()
    print(json.dumps(summary.to_dict(), indent=2))
