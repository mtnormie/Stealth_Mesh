"""Network composition for nodes and their link topology."""

from core.node import Node
from core.topology import Topology


class Network:
    """A set of nodes and their simulated connectivity."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.topology = Topology()

    def add_node(self, node: Node) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"node already exists: {node.node_id}")
        self.nodes[node.node_id] = node
        self.topology.add_node(node.node_id)

    def add_link(self, first: str, second: str, cost: float = 1.0) -> None:
        if first not in self.nodes or second not in self.nodes:
            raise ValueError("both link endpoints must be registered nodes")
        self.topology.add_link(first, second, cost)
