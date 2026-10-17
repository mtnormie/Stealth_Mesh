"""Effective routing graph builder filtering unavailable nodes and failed links."""

from __future__ import annotations

from collections.abc import Callable

from core.network import Network
from core.topology import Topology
from routing.failure_detector import FailureDetector
from routing.route_metrics import compute_link_cost

LinkQualityCallback = Callable[[str, str], float | None]


def build_effective_topology(
    network: Network,
    *,
    failure_detector: FailureDetector | None = None,
    link_quality_fn: LinkQualityCallback | None = None,
    penalty_weight: float = 2.0,
) -> Topology:
    """Construct a Topology containing only available nodes and healthy links.

    If ``link_quality_fn`` is provided, each active link's weight is adjusted using
    :func:`routing.route_metrics.compute_link_cost`. Invalid or missing quality
    estimates automatically fall back to the static topology link cost.
    """
    if not isinstance(network, Network):
        raise TypeError("network must be a Network instance")

    effective = Topology()
    available_nodes: set[str] = set()
    for node_id, node in sorted(network.nodes.items()):
        if not node.available:
            continue
        if failure_detector is not None and failure_detector.is_node_failed(node_id):
            continue
        effective.add_node(node_id)
        available_nodes.add(node_id)

    seen_pairs: set[tuple[str, str]] = set()
    for first in sorted(available_nodes):
        for second, base_cost in sorted(network.topology.neighbors(first).items()):
            if second not in available_nodes:
                continue
            pair = (first, second) if first < second else (second, first)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            if failure_detector is not None and failure_detector.is_link_failed(first, second):
                continue
            quality: float | None = None
            if link_quality_fn is not None:
                try:
                    quality = link_quality_fn(first, second)
                except Exception:
                    quality = None
            cost = compute_link_cost(
                base_cost,
                quality,
                penalty_weight=penalty_weight,
            )
            effective.add_link(first, second, cost)

    return effective
