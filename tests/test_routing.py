"""Tests for deterministic baseline routing."""

import unittest

from app.services.status_service import NetworkSandboxService
from core.network import Network
from core.node import Node
from monitoring.jammer_locator import LinkTelemetrySample, locate_interference
from radio.link_quality import LinkObservation, LinkQualityTracker
from routing.dijkstra import path_cost, shortest_path
from routing.failure_detector import FailureDetector
from routing.route_manager import RouteManager
from routing.route_metrics import compute_link_cost


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

    def test_route_manager_reroutes_around_unavailable_nodes_and_failed_links(self) -> None:
        self.network.add_link("a", "b", 1.0)
        self.network.add_link("b", "d", 1.0)
        self.network.add_link("a", "c", 2.0)
        self.network.add_link("c", "d", 2.0)

        detector = FailureDetector(failure_threshold=2)
        manager = RouteManager(self.network, failure_detector=detector)
        self.assertEqual(manager.find_route("a", "d"), ["a", "b", "d"])

        # Two consecutive failures on link (a, b) trigger failover to a -> c -> d
        detector.record_hop_outcome("a", "b", delivered=False)
        self.assertFalse(detector.is_link_failed("a", "b"))
        detector.record_hop_outcome("a", "b", delivered=False)
        self.assertTrue(detector.is_link_failed("a", "b"))
        self.assertEqual(manager.find_route("a", "d"), ["a", "c", "d"])

        # Recovery restores primary route
        detector.record_hop_outcome("a", "b", delivered=True)
        self.assertEqual(manager.find_route("a", "d"), ["a", "b", "d"])

        # Unavailable node b also forces route via c
        self.network.nodes["b"].available = False
        self.assertEqual(manager.find_route("a", "d"), ["a", "c", "d"])

    def test_route_metrics_and_link_quality_fallback(self) -> None:
        self.assertAlmostEqual(compute_link_cost(1.0, 1.0, penalty_weight=2.0), 1.0)
        self.assertAlmostEqual(compute_link_cost(1.0, 0.5, penalty_weight=2.0), 3.0)
        # Fallback when prediction is None or invalid
        self.assertAlmostEqual(compute_link_cost(1.5, None), 1.5)
        self.assertAlmostEqual(compute_link_cost(1.5, -0.2), 1.5)
        self.assertAlmostEqual(compute_link_cost(1.5, 1.8), 1.5)

        tracker = LinkQualityTracker(window_size=4)
        tracker.record(LinkObservation("a", "b", True, 0.05, attempts=1, rssi_dbm=-75.0, snr_db=8.0))
        tracker.record(LinkObservation("b", "a", False, 0.15, attempts=2, rssi_dbm=-95.0, snr_db=-2.0))
        summary = tracker.summary("a", "b")
        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.sample_count, 2)
        self.assertAlmostEqual(summary.delivery_ratio, 0.5)
        self.assertAlmostEqual(summary.mean_rssi_dbm, -85.0)

    def test_network_sandbox_service_toggle_add_and_simulate(self) -> None:
        sandbox = NetworkSandboxService(seed=42)
        state = sandbox.get_state()
        routing = state["routing"]
        self.assertEqual(routing["ml_route"], ["N1", "N2", "N4", "N6"])
        self.assertGreaterEqual(routing["ml_compute_us"], 0.0)

        # Turn off N2 -> route immediately fails over to N1 -> N3 -> N5 -> N6
        toggled = sandbox.toggle_node("N2", available=False)
        self.assertEqual(toggled["routing"]["ml_route"], ["N1", "N3", "N5", "N6"])
        # Single offline node with clean adjacent links is classified as node_offline, not ew_radio_dome
        self.assertEqual(toggled["jammer"]["interference_type"], "node_offline")
        self.assertFalse(toggled["jammer"]["detected"])

        # Add a new node N7 and simulate packet delivery
        added = sandbox.add_node("N7", 450.0, 260.0, auto_link_radius=300.0)
        self.assertEqual(added["diagnostics"]["total_nodes"], 7)
        sim = sandbox.simulate_packet("N1", "N6", routing_mode="ml")
        self.assertIn("simulation", sim)
        self.assertGreater(len(sim["simulation"]["hop_trace"]), 0)

    def test_jammer_locator_distinguishes_natural_obstacle_from_ew_radio_dome(self) -> None:
        positions = {
            "a": (100.0, 200.0),
            "b": (300.0, 100.0),
            "c": (300.0, 300.0),
            "d": (500.0, 200.0),
        }
        # 1. Single weak-RSSI link -> classified as natural_obstacle
        natural_samples = [
            LinkTelemetrySample("a", "b", loss_probability=0.18, rssi_dbm=-108.0, snr_db=2.8),
            LinkTelemetrySample("b", "d", loss_probability=0.02, rssi_dbm=-71.0, snr_db=9.5),
            LinkTelemetrySample("a", "c", loss_probability=0.02, rssi_dbm=-72.0, snr_db=9.0),
            LinkTelemetrySample("c", "d", loss_probability=0.02, rssi_dbm=-72.0, snr_db=9.0),
        ]
        nat_report = locate_interference(self.network, positions, natural_samples)
        self.assertTrue(nat_report.detected)
        self.assertEqual(nat_report.interference_type, "natural_obstacle")
        self.assertAlmostEqual(nat_report.estimated_x or 0.0, 200.0, delta=5.0)
        self.assertAlmostEqual(nat_report.estimated_y or 0.0, 150.0, delta=5.0)

        # 2. Active EW radio dome in sandbox near upper relay N2 (330, 120)
        sandbox = NetworkSandboxService(seed=42)
        jammed_state = sandbox.simulate_jammer(335.0, 125.0, radius=190.0)
        jammer = jammed_state["jammer"]
        self.assertTrue(jammer["detected"])
        self.assertEqual(jammer["interference_type"], "ew_radio_dome")
        self.assertIsNotNone(jammer["estimated_x"])
        self.assertIsNotNone(jammer["estimated_y"])
        # Triangulated epicenter lies in the upper region near N2/N4
        self.assertLess(jammer["estimated_y"], 250.0)
        self.assertGreaterEqual(jammer["estimated_radius"], 95.0)
        # Adaptive ML + Failover router diverts via the lower path N1 -> N3 -> N5 -> N6
        self.assertEqual(jammed_state["routing"]["ml_route"], ["N1", "N3", "N5", "N6"])


if __name__ == "__main__":
    unittest.main()
