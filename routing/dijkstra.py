"""Deterministic weighted Dijkstra shortest-path routing."""

from __future__ import annotations

import heapq
from collections.abc import Sequence
from itertools import count

from core.topology import Topology


def shortest_path(topology: Topology, source: str, destination: str) -> list[str] | None:
    """Return the minimum-cost path, or ``None`` if the destination is unreachable.

    Unknown endpoints are treated as invalid caller input and raise ``ValueError``.
    Equal-cost alternatives are resolved by lexical path order for reproducibility.
    """
    if source not in topology.nodes or destination not in topology.nodes:
        raise ValueError("source and destination must exist in the topology")

    serial = count()
    initial_path = (source,)
    pending: list[tuple[float, tuple[str, ...], int]] = [(0.0, initial_path, next(serial))]
    best: dict[str, tuple[float, tuple[str, ...]]] = {source: (0.0, initial_path)}

    while pending:
        distance, path, _ = heapq.heappop(pending)
        node = path[-1]
        if node == destination:
            return list(path)
        if (distance, path) > best.get(node, (float("inf"), ())):
            continue
        for neighbor, weight in sorted(topology.neighbors(node).items()):
            if neighbor in path:
                continue
            candidate = (distance + weight, (*path, neighbor))
            if neighbor not in best or candidate < best[neighbor]:
                best[neighbor] = candidate
                heapq.heappush(pending, (candidate[0], candidate[1], next(serial)))

    return None


def path_cost(topology: Topology, path: Sequence[str]) -> float:
    """Return the sum of link costs for a valid path."""
    if not path:
        raise ValueError("path must contain at least one node")
    if len(path) == 1:
        if path[0] not in topology.nodes:
            raise ValueError(f"unknown node in path: {path[0]}")
        return 0.0

    total = 0.0
    for first, second in zip(path, path[1:]):
        weight = topology.neighbors(first).get(second)
        if weight is None:
            raise ValueError(f"path contains a missing link: {first} -> {second}")
        total += weight
    return total
