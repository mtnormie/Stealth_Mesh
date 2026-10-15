"""Tests for reproducible integrated network simulations."""

import unittest

from core.network import Network
from core.node import Node
from core.packet import Packet
from monitoring.event_logger import EventLogger
from radio.simulator import RadioSimulator
from simulation.run_simulation import SimulationRunner
from transport.delivery_manager import DeliveryManager, RetryPolicy


class SimulationRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.network = Network()
        for node_id in "abcx":
            self.network.add_node(Node(node_id))
        self.network.add_link("a", "b", 1)
        self.network.add_link("b", "c", 1)

    def test_routes_delivers_and_collects_metrics_and_events(self) -> None:
        logger = EventLogger()
        radio = RadioSimulator(self.network, latency_range=(0.1, 0.1), seed=4)
        runner = SimulationRunner(self.network, radio, event_logger=logger)
        result = runner.run([Packet("m1", "a", "c", b"hi")])
        self.assertEqual(result.messages[0].route, ("a", "b", "c"))
        self.assertEqual(result.metrics.messages_delivered, 1)
        self.assertEqual(result.metrics.delivery_ratio, 1)
        self.assertAlmostEqual(result.metrics.modeled_latency_seconds, 0.2)
        self.assertEqual(logger.events[0].name, "message_delivery")
        self.assertEqual(logger.events[0].fields["status"], "delivered")

    def test_unreachable_and_failed_hops_are_recorded(self) -> None:
        runner = SimulationRunner(
            self.network,
            RadioSimulator(self.network, packet_loss_probability=1, seed=9),
            DeliveryManager(RetryPolicy(max_retries=1)),
        )
        result = runner.run([Packet("missing", "a", "x", b"hi"),
                             Packet("lost", "a", "c", b"hi")])
        self.assertIsNone(result.messages[0].route)
        self.assertEqual(result.messages[0].delivery.attempts, 0)
        self.assertEqual(result.messages[1].delivery.attempts, 2)
        self.assertEqual(result.metrics.messages_failed, 2)
        self.assertEqual(result.metrics.retransmissions, 1)

    def test_rejects_inconsistent_network_and_bad_metrics(self) -> None:
        other = Network()
        with self.assertRaises(ValueError):
            SimulationRunner(self.network, RadioSimulator(other))
        with self.assertRaises(ValueError):
            from monitoring.metrics import Metrics
            Metrics().record(delivered=False, attempts=-1, modeled_latency_seconds=0)


if __name__ == "__main__":
    unittest.main()
