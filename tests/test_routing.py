"""Tests for deterministic baseline routing."""

import unittest

from core.network import Network
from core.node import Node
from routing.dijkstra import path_cost, shortest_path


class DijkstraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = Network()
        for node_id in "abcde":
            self.network.add_node(Node(node_id))

    def test_selects_lowest_cost_route(self) -> None:
        self.network.add_link("a", "b", 2)
        self.network.add_link("b", "d", 2)
        self.network.add_link("a", "c", 1)
        self.network.add_link("c", "d", 1)
        self.network.add_link("a", "d", 8)
        route = shortest_path(self.network.topology, "a", "d")
        self.assertEqual(route, ["a", "c", "d"])
        self.assertEqual(path_cost(self.network.topology, route), 2)

    def test_tie_is_deterministic(self) -> None:
        self.network.add_link("a", "c", 1)
        self.network.add_link("c", "d", 1)
        self.network.add_link("a", "b", 1)
        self.network.add_link("b", "d", 1)
        self.assertEqual(shortest_path(self.network.topology, "a", "d"), ["a", "b", "d"])

    def test_source_destination_unreachable_and_unknown(self) -> None:
        self.network.add_link("a", "b")
        self.assertEqual(shortest_path(self.network.topology, "a", "a"), ["a"])
        self.assertIsNone(shortest_path(self.network.topology, "a", "e"))
        with self.assertRaises(ValueError):
            shortest_path(self.network.topology, "missing", "a")

    def test_path_cost_rejects_invalid_paths(self) -> None:
        self.network.add_link("a", "b", 3)
        self.assertEqual(path_cost(self.network.topology, ["a", "b"]), 3)
        with self.assertRaises(ValueError):
            path_cost(self.network.topology, [])
        with self.assertRaises(ValueError):
            path_cost(self.network.topology, ["a", "c"])


if __name__ == "__main__":
    unittest.main()
