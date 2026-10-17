"""Reproducible relay node failure and route-recovery simulation scenario."""

from __future__ import annotations

from dataclasses import dataclass

from core.packet import Packet
from radio.simulator import RadioSimulator
from routing.failure_detector import FailureDetector
from routing.route_manager import RouteManager
from simulation.packet_loss import build_reference_mesh
from simulation.results import SimulationResult
from simulation.run_simulation import SimulationRunner
from transport.delivery_manager import DeliveryManager, DeliveryStatus
from transport.retry_policy import RetryPolicy


@dataclass(frozen=True, slots=True)
class NodeFailureScenarioResult:
    """Outcome of a two-phase node-failure and route-recovery experiment."""

    failed_node_id: str
    primary_route: tuple[str, ...] | None
    recovery_route: tuple[str, ...] | None
    pre_failure: SimulationResult
    post_failure: SimulationResult

    @property
    def total_messages_sent(self) -> int:
        return self.pre_failure.metrics.messages_sent + self.post_failure.metrics.messages_sent

    @property
    def total_messages_delivered(self) -> int:
        return self.pre_failure.metrics.messages_delivered + self.post_failure.metrics.messages_delivered

    @property
    def overall_delivery_ratio(self) -> float:
        total = self.total_messages_sent
        return self.total_messages_delivered / total if total else 0.0

    @property
    def route_recovered(self) -> bool:
        return (
            self.recovery_route is not None
            and self.failed_node_id not in self.recovery_route
            and any(
                msg.delivery.status is DeliveryStatus.DELIVERED
                for msg in self.post_failure.messages
            )
        )


def run_node_failure_scenario(
    *,
    pre_failure_messages: int = 5,
    post_failure_messages: int = 5,
    max_retries: int = 2,
    loss_probability: float = 0.0,
    seed: int = 42,
) -> NodeFailureScenarioResult:
    """Simulate relay node failure midway through a transmission batch and measure route recovery."""
    if not isinstance(pre_failure_messages, int) or isinstance(pre_failure_messages, bool) or pre_failure_messages < 1:
        raise ValueError("pre_failure_messages must be a positive integer")
    if not isinstance(post_failure_messages, int) or isinstance(post_failure_messages, bool) or post_failure_messages < 1:
        raise ValueError("post_failure_messages must be a positive integer")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")

    network = build_reference_mesh()
    radio = RadioSimulator(
        network,
        latency_range=(0.05, 0.10),
        packet_loss_probability=loss_probability,
        seed=seed,
    )
    route_manager = RouteManager(
        network,
        failure_detector=FailureDetector(failure_threshold=2),
    )
    delivery = DeliveryManager(RetryPolicy(max_retries=max_retries))
    runner = SimulationRunner(
        network,
        radio,
        delivery=delivery,
        route_manager=route_manager,
    )

    pre_packets = [
        Packet(f"pre-fail-{idx}", "a", "d", f"phase1-{idx}".encode("utf-8"))
        for idx in range(1, pre_failure_messages + 1)
    ]
    pre_result = runner.run(pre_packets)
    primary_route = pre_result.messages[0].route if pre_result.messages else None

    # Take down primary relay "b"
    failed_node_id = "b"
    network.nodes[failed_node_id].available = False

    post_packets = [
        Packet(f"post-fail-{idx}", "a", "d", f"phase2-{idx}".encode("utf-8"))
        for idx in range(1, post_failure_messages + 1)
    ]
    post_result = runner.run(post_packets)
    recovery_route = post_result.messages[0].route if post_result.messages else None

    return NodeFailureScenarioResult(
        failed_node_id=failed_node_id,
        primary_route=primary_route,
        recovery_route=recovery_route,
        pre_failure=pre_result,
        post_failure=post_result,
    )
