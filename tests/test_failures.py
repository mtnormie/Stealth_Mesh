"""Tests for reproducible integrated network simulations."""

import json
import tempfile
import unittest
from pathlib import Path

from core.network import Network
from core.node import Node
from core.packet import Packet
from monitoring.event_logger import EventLogger
from radio.simulator import RadioSimulator
from simulation.node_failures import run_node_failure_scenario
from simulation.packet_loss import run_packet_loss_scenario
from simulation.run_simulation import SimulationRunner
from simulation.scenarios import export_scenario_reports, run_named_scenario
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

    def test_reproducible_packet_loss_and_node_failure_scenarios(self) -> None:
        loss_a = run_packet_loss_scenario(loss_probability=0.3, message_count=15, max_retries=2, seed=77)
        loss_b = run_packet_loss_scenario(loss_probability=0.3, message_count=15, max_retries=2, seed=77)
        self.assertEqual(loss_a.metrics.messages_delivered, loss_b.metrics.messages_delivered)
        self.assertEqual(loss_a.metrics.retransmissions, loss_b.metrics.retransmissions)
        self.assertGreater(loss_a.metrics.messages_delivered, 0)

        failure_res = run_node_failure_scenario(pre_failure_messages=4, post_failure_messages=4, seed=77)
        self.assertEqual(failure_res.primary_route, ("a", "b", "d"))
        self.assertEqual(failure_res.recovery_route, ("a", "c", "d"))
        self.assertTrue(failure_res.route_recovered)
        self.assertEqual(failure_res.overall_delivery_ratio, 1.0)

    def test_named_scenarios_and_json_export(self) -> None:
        reports = [
            run_named_scenario("normal_operation", seed=11),
            run_named_scenario("random_packet_loss", seed=11),
            run_named_scenario("relay_node_failure", seed=11),
        ]
        self.assertEqual(reports[0].delivery_ratio, 1.0)
        self.assertEqual(reports[2].parameters["route_recovered"], True)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "summary.json"
            export_scenario_reports(reports, out_file)
            loaded = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(len(loaded["scenarios"]), 3)
            self.assertEqual(loaded["scenarios"][0]["scenario_name"], "normal_operation")

        with self.assertRaises(ValueError):
            run_named_scenario("unknown_scenario")


if __name__ == "__main__":
    unittest.main()
