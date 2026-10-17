"""Failure detection for nodes and links based on consecutive hop outcomes."""

from __future__ import annotations


class FailureDetector:
    """Track consecutive transmission failures to isolate unresponsive links or nodes."""

    def __init__(self, *, failure_threshold: int = 2) -> None:
        if not isinstance(failure_threshold, int) or isinstance(failure_threshold, bool) or failure_threshold < 1:
            raise ValueError("failure_threshold must be a positive integer")
        self.failure_threshold = failure_threshold
        self._link_failures: dict[tuple[str, str], int] = {}
        self._failed_nodes: set[str] = set()

    @staticmethod
    def _link_key(first: str, second: str) -> tuple[str, str]:
        if not isinstance(first, str) or not first.strip() or not isinstance(second, str) or not second.strip():
            raise ValueError("link endpoints must be non-empty strings")
        if first == second:
            raise ValueError("link endpoints must be distinct")
        return (first, second) if first < second else (second, first)

    def record_hop_outcome(self, source: str, destination: str, *, delivered: bool) -> None:
        """Update consecutive failure count for a link after a transmission attempt."""
        if not isinstance(delivered, bool):
            raise TypeError("delivered must be a bool")
        key = self._link_key(source, destination)
        if delivered:
            self._link_failures.pop(key, None)
        else:
            self._link_failures[key] = self._link_failures.get(key, 0) + 1

    def mark_node_failed(self, node_id: str) -> None:
        """Explicitly mark a node as failed for route calculation."""
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        self._failed_nodes.add(node_id)

    def mark_node_recovered(self, node_id: str) -> None:
        """Clear a node's failed status and reset incident link failure counters."""
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        self._failed_nodes.discard(node_id)
        to_clear = [key for key in self._link_failures if node_id in key]
        for key in to_clear:
            del self._link_failures[key]

    def is_node_failed(self, node_id: str) -> bool:
        """Return True if the node has been marked failed."""
        return node_id in self._failed_nodes

    def is_link_failed(self, first: str, second: str) -> bool:
        """Return True if the link has reached the consecutive failure threshold."""
        key = self._link_key(first, second)
        return self._link_failures.get(key, 0) >= self.failure_threshold

    def consecutive_failures(self, first: str, second: str) -> int:
        """Return the current consecutive failure count for an undirected link."""
        key = self._link_key(first, second)
        return self._link_failures.get(key, 0)
