"""Reproducible random packet-loss simulation scenario."""

from __future__ import annotations

from math import isfinite

from core.network import Network
from core.node import Node
from core.packet import Packet
from radio.simulator import RadioSimulator
from routing.failure_detector import FailureDetector
from routing.route_manager import RouteManager
from simulation.results import SimulationResult
from simulation.run_simulation import SimulationRunner
from transport.delivery_manager import DeliveryManager
from transport.retry_policy import RetryPolicy


def build_reference_mesh() -> Network:
    """Create a 5-node diamond mesh topology with a primary and backup path."""
    network = Network()
    for node_id in ("a", "b", "c", "d", "e"):
        network.add_node(Node(node_id))
    # Primary two-hop path: a -> b -> d (cost 2.0)
    network.add_link("a", "b", 1.0)
    network.add_link("b", "d", 1.0)
    # Backup two-hop path: a -> c -> d (cost 3.0)
    network.add_link("a", "c", 1.5)
    network.add_link("c", "d", 1.5)
    # Additional cross-link: b -> e -> d (cost 3.5)
    network.add_link("b", "e", 1.5)
    network.add_link("e", "d", 2.0)
    return network


def run_packet_loss_scenario(
    *,
    loss_probability: float = 0.25,
    message_count: int = 20,
    max_retries: int = 2,
    latency_range: tuple[float, float] = (0.05, 0.15),
    seed: int = 42,
) -> SimulationResult:
    """Run a seeded multi-hop packet-loss experiment over the reference mesh."""
    if not isfinite(loss_probability) or not 0.0 <= loss_probability <= 1.0:
        raise ValueError("loss_probability must be between 0.0 and 1.0")
    if not isinstance(message_count, int) or isinstance(message_count, bool) or message_count < 1:
        raise ValueError("message_count must be a positive integer")
    if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 0:
        raise ValueError("max_retries must be a non-negative integer")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")

    network = build_reference_mesh()
    radio = RadioSimulator(
        network,
        latency_range=latency_range,
        packet_loss_probability=loss_probability,
        seed=seed,
    )
    route_manager = RouteManager(
        network,
        failure_detector=FailureDetector(failure_threshold=max_retries + 2),
    )
    delivery = DeliveryManager(RetryPolicy(max_retries=max_retries))
    runner = SimulationRunner(
        network,
        radio,
        delivery=delivery,
        route_manager=route_manager,
    )
    packets = [
        Packet(f"loss-msg-{idx}", "a", "d", f"payload-{idx}".encode("utf-8"))
        for idx in range(1, message_count + 1)
    ]
    return runner.run(packets)
