"""Mesh node model."""

from dataclasses import dataclass


@dataclass(slots=True)
class Node:
    """A node participating in the simulated network."""

    node_id: str
    available: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.node_id, str):
            raise TypeError("node_id must be a string")
        if not self.node_id.strip():
            raise ValueError("node_id must be non-empty")
        if not isinstance(self.available, bool):
            raise TypeError("available must be a bool")
