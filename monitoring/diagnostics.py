"""Network health diagnostics for nodes, links, and topology connectivity."""

from __future__ import annotations

from dataclasses import dataclass

from core.network import Network
from routing.failure_detector import FailureDetector
from routing.graph import build_effective_topology


@dataclass(frozen=True, slots=True)
class NetworkHealthReport:
    """Snapshot of node availability, active links, and isolated nodes."""

    total_nodes: int
    available_nodes: int
    unavailable_nodes: tuple[str, ...]
    isolated_nodes: tuple[str, ...]
    active_link_count: int


def diagnose_network(
    network: Network,
    *,
    failure_detector: FailureDetector | None = None,
) -> NetworkHealthReport:
    """Inspect a Network and its effective topology to report health and isolation."""
    if not isinstance(network, Network):
        raise TypeError("network must be a Network instance")

    effective = build_effective_topology(network, failure_detector=failure_detector)
    total_nodes = len(network.nodes)
    available_nodes = len(effective.nodes)
    unavailable = tuple(sorted(set(network.nodes) - set(effective.nodes)))

    isolated: list[str] = []
    edge_double_count = 0
    for node_id in sorted(effective.nodes):
        deg = len(effective.neighbors(node_id))
        edge_double_count += deg
        if deg == 0:
            isolated.append(node_id)

    return NetworkHealthReport(
        total_nodes=total_nodes,
        available_nodes=available_nodes,
        unavailable_nodes=unavailable,
        isolated_nodes=tuple(isolated),
        active_link_count=edge_double_count // 2,
    )
