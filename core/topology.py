"""Weighted topology model used by the simulator and routing layer."""

from collections import defaultdict
from math import isfinite


class Topology:
    """Undirected graph of nodes and positive-cost links."""

    def __init__(self) -> None:
        self._links: dict[str, dict[str, float]] = defaultdict(dict)

    @property
    def nodes(self) -> frozenset[str]:
        return frozenset(self._links)

    def add_node(self, node_id: str) -> None:
        if not node_id.strip():
            raise ValueError("node_id must be non-empty")
        self._links.setdefault(node_id, {})

    def add_link(self, first: str, second: str, cost: float = 1.0) -> None:
        if not first.strip() or not second.strip() or first == second:
            raise ValueError("link endpoints must be distinct non-empty node IDs")
        if not isfinite(cost) or cost <= 0:
            raise ValueError("link cost must be finite and positive")
        self.add_node(first)
        self.add_node(second)
        self._links[first][second] = float(cost)
        self._links[second][first] = float(cost)

    def neighbors(self, node_id: str) -> dict[str, float]:
        """Return a copy of the node's neighbor-to-cost mapping."""
        return dict(self._links.get(node_id, {}))

    def has_link(self, first: str, second: str) -> bool:
        return second in self._links.get(first, {})
