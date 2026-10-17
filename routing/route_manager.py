"""Adaptive route manager integrating Dijkstra, failure detection, and link quality."""

from __future__ import annotations

from core.network import Network
from routing.dijkstra import path_cost, shortest_path
from routing.failure_detector import FailureDetector
from routing.graph import LinkQualityCallback, build_effective_topology


class RouteManager:
    """Manage route calculation and failover across available nodes and links."""

    def __init__(
        self,
        network: Network,
        *,
        failure_detector: FailureDetector | None = None,
        link_quality_fn: LinkQualityCallback | None = None,
        penalty_weight: float = 2.0,
    ) -> None:
        if not isinstance(network, Network):
            raise TypeError("network must be a Network instance")
        self.network = network
        self.failure_detector = failure_detector or FailureDetector()
        self.link_quality_fn = link_quality_fn
        self.penalty_weight = penalty_weight

    def find_route(self, source: str, destination: str) -> list[str] | None:
        """Compute the lowest-cost active route between two registered nodes."""
        if source not in self.network.nodes or destination not in self.network.nodes:
            raise ValueError("source and destination must be registered nodes")
        effective = build_effective_topology(
            self.network,
            failure_detector=self.failure_detector,
            link_quality_fn=self.link_quality_fn,
            penalty_weight=self.penalty_weight,
        )
        if source not in effective.nodes or destination not in effective.nodes:
            return None
        return shortest_path(effective, source, destination)

    def route_cost(self, path: list[str]) -> float:
        """Compute the effective cost of a path in the current active topology."""
        effective = build_effective_topology(
            self.network,
            failure_detector=self.failure_detector,
            link_quality_fn=self.link_quality_fn,
            penalty_weight=self.penalty_weight,
        )
        return path_cost(effective, path)
