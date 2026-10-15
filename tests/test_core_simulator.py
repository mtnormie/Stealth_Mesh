"""Tests for core models and the deterministic radio simulator."""

import unittest
from datetime import datetime

from core.message import Message
from core.network import Network
from core.node import Node
from core.packet import Packet
from radio.simulator import RadioSimulator


def sample_network() -> Network:
    network = Network()
    network.add_node(Node("a"))
    network.add_node(Node("b"))
    network.add_link("a", "b")
    return network


class CoreModelTests(unittest.TestCase):
    def test_message_defaults_and_validation(self) -> None:
        message = Message("a", "b", "hello")
        self.assertTrue(message.message_id)
        self.assertIsNotNone(message.created_at.tzinfo)
        with self.assertRaises(ValueError):
            Message("", "b", "hello")
        with self.assertRaises(ValueError):
            Message("a", "b", "hello", created_at=datetime(2024, 1, 1))

    def test_packet_forwarding_decrements_hop_limit(self) -> None:
        packet = Packet("m", "a", "b", b"hello", hop_limit=2)
        forwarded = packet.forwarded()
        self.assertEqual(forwarded.hop_limit, 1)
        self.assertEqual(forwarded.packet_id, packet.packet_id)
        with self.assertRaises(ValueError):
            Packet("m", "a", "b", b"hello", hop_limit=0).forwarded()

    def test_duplicate_nodes_and_invalid_links_are_rejected(self) -> None:
        network = sample_network()
        with self.assertRaises(ValueError):
            network.add_node(Node("a"))
        with self.assertRaises(ValueError):
            network.add_link("a", "missing")


class RadioSimulatorTests(unittest.TestCase):
    def test_success_and_seeded_latency(self) -> None:
        first = RadioSimulator(sample_network(), latency_range=(0.2, 0.8), seed=17)
        second = RadioSimulator(sample_network(), latency_range=(0.2, 0.8), seed=17)
        result = first.transmit("a", "b")
        self.assertTrue(result.delivered)
        self.assertEqual(result.reason, "delivered")
        self.assertEqual(result, second.transmit("a", "b"))
        self.assertGreaterEqual(result.latency_seconds, 0.2)
        self.assertLessEqual(result.latency_seconds, 0.8)

    def test_loss_unavailability_and_missing_link(self) -> None:
        network = sample_network()
        self.assertEqual(RadioSimulator(network, packet_loss_probability=1).transmit("a", "b").reason,
                         "packet_loss")
        network.nodes["b"].available = False
        self.assertEqual(RadioSimulator(network).transmit("a", "b").reason, "node_unavailable")
        network.nodes["b"].available = True
        self.assertEqual(RadioSimulator(network).transmit("b", "a").reason, "delivered")
        network.add_node(Node("c"))
        self.assertEqual(RadioSimulator(network).transmit("a", "c").reason, "no_link")

    def test_invalid_simulator_configuration(self) -> None:
        network = sample_network()
        with self.assertRaises(ValueError):
            RadioSimulator(network, latency_range=(2, 1))
        with self.assertRaises(ValueError):
            RadioSimulator(network, latency_range=(0, float("inf")))
        with self.assertRaises(ValueError):
            RadioSimulator(network, packet_loss_probability=1.1)
        with self.assertRaises(ValueError):
            network.topology.add_link("a", "b", float("nan"))
        with self.assertRaises(ValueError):
            RadioSimulator(network).transmit("missing", "b")


if __name__ == "__main__":
    unittest.main()
