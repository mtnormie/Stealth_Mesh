"""Interactive mesh topology sandbox and live routing/simulation service."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
import random
import threading
import time

from core.network import Network
from core.node import Node
from core.packet import Packet
from ml.dataset import generate_synthetic_dataset, split_dataset_by_group
from ml.features import LinkFeatures
from ml.predict import MLLinkQualityPredictor
from ml.train import train_logistic_model
from monitoring.diagnostics import diagnose_network
from routing.dijkstra import path_cost, shortest_path
from routing.failure_detector import FailureDetector
from routing.route_manager import RouteManager
from transport.delivery_manager import DeliveryManager, DeliveryStatus
from transport.retry_policy import RetryPolicy

_MAX_NODES = 40


@dataclass(slots=True)
class LinkProfile:
    """Simulated physical-layer profile for an undirected link in the visualizer."""

    cost: float = 1.0
    loss_probability: float = 0.02
    latency_ms: float = 45.0
    rssi_dbm: float = -72.0
    snr_db: float = 9.5


def _validate_node_id(node_id: object) -> str:
    if not isinstance(node_id, str):
        raise ValueError("node_id must be a string")
    cleaned = node_id.strip()
    if not 1 <= len(cleaned) <= 16 or not all(ch.isalnum() or ch in ("_", "-") for ch in cleaned):
        raise ValueError("node_id must be 1..16 alphanumeric characters")
    return cleaned


def _validate_coord(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    clamped = max(20.0, min(980.0, float(value)))
    return round(clamped, 1)


class NetworkSandboxService:
    """Thread-safe interactive mesh topology, routing benchmark, and hop simulator."""

    def __init__(self, *, seed: int = 42) -> None:
        self._lock = threading.Lock()
        self._seed = seed
        self._rng = random.Random(seed)
        dataset = generate_synthetic_dataset(num_groups=24, samples_per_group=10, seed=seed)
        split = split_dataset_by_group(dataset, train_ratio=0.7, seed=seed)
        model = train_logistic_model(split.train, learning_rate=0.2, epochs=250, l2_penalty=0.01)
        self._predictor = MLLinkQualityPredictor(model=model)

        self._network = Network()
        self._positions: dict[str, tuple[float, float]] = {}
        self._link_profiles: dict[tuple[str, str], LinkProfile] = {}
        self._failure_detector = FailureDetector(failure_threshold=2)
        self._source = "N1"
        self._destination = "N6"
        self.reset_default_topology()

    @staticmethod
    def _edge_key(first: str, second: str) -> tuple[str, str]:
        return (first, second) if first < second else (second, first)

    def reset_default_topology(self) -> dict[str, object]:
        """Restore the default 6-node multi-path mesh topology."""
        with self._lock:
            self._network = Network()
            self._positions.clear()
            self._link_profiles.clear()
            self._failure_detector = FailureDetector(failure_threshold=2)

            default_nodes = [
                ("N1", 110.0, 260.0, True),
                ("N2", 330.0, 120.0, True),
                ("N3", 330.0, 400.0, True),
                ("N4", 600.0, 120.0, True),
                ("N5", 600.0, 400.0, True),
                ("N6", 830.0, 260.0, True),
            ]
            for node_id, x, y, available in default_nodes:
                self._network.add_node(Node(node_id, available=available))
                self._positions[node_id] = (x, y)

            # Upper path N1 -> N2 -> N4 -> N6 (low nominal cost, healthy)
            self._set_link_unlocked("N1", "N2", cost=1.0, loss_probability=0.02, latency_ms=40.0, rssi_dbm=-70.0, snr_db=10.0)
            self._set_link_unlocked("N2", "N4", cost=1.0, loss_probability=0.03, latency_ms=42.0, rssi_dbm=-72.0, snr_db=9.0)
            self._set_link_unlocked("N4", "N6", cost=1.0, loss_probability=0.02, latency_ms=40.0, rssi_dbm=-71.0, snr_db=9.5)

            # Lower path N1 -> N3 -> N5 -> N6 (alternative relay path)
            self._set_link_unlocked("N1", "N3", cost=1.2, loss_probability=0.03, latency_ms=48.0, rssi_dbm=-75.0, snr_db=8.5)
            self._set_link_unlocked("N3", "N5", cost=1.2, loss_probability=0.03, latency_ms=50.0, rssi_dbm=-76.0, snr_db=8.0)
            self._set_link_unlocked("N5", "N6", cost=1.2, loss_probability=0.03, latency_ms=48.0, rssi_dbm=-74.0, snr_db=8.5)

            # Cross links for mesh resilience
            self._set_link_unlocked("N2", "N3", cost=1.1, loss_probability=0.04, latency_ms=45.0, rssi_dbm=-78.0, snr_db=7.5)
            self._set_link_unlocked("N4", "N5", cost=1.1, loss_probability=0.04, latency_ms=45.0, rssi_dbm=-78.0, snr_db=7.5)
            self._set_link_unlocked("N2", "N5", cost=1.5, loss_probability=0.08, latency_ms=65.0, rssi_dbm=-86.0, snr_db=4.0)

            self._source = "N1"
            self._destination = "N6"
            return self._snapshot_unlocked()

    def clear_topology(self) -> dict[str, object]:
        """Remove all nodes and links so the user can build a mesh from scratch."""
        with self._lock:
            self._network = Network()
            self._positions.clear()
            self._link_profiles.clear()
            self._failure_detector = FailureDetector(failure_threshold=2)
            self._source = ""
            self._destination = ""
            return self._snapshot_unlocked()

    def add_node(
        self,
        node_id: str | None,
        x: float,
        y: float,
        *,
        auto_link_radius: float = 290.0,
    ) -> dict[str, object]:
        """Add a node at canvas coordinates (x, y) and optionally connect nearby nodes."""
        with self._lock:
            if len(self._network.nodes) >= _MAX_NODES:
                raise ValueError(f"maximum of {_MAX_NODES} nodes reached")
            px = _validate_coord(x, "x")
            py = _validate_coord(y, "y")

            if node_id is None or not str(node_id).strip():
                idx = 1
                while f"N{idx}" in self._network.nodes:
                    idx += 1
                clean_id = f"N{idx}"
            else:
                clean_id = _validate_node_id(node_id)
                if clean_id in self._network.nodes:
                    raise ValueError(f"node already exists: {clean_id}")

            self._network.add_node(Node(clean_id, available=True))
            self._positions[clean_id] = (px, py)

            if not isfinite(auto_link_radius) or auto_link_radius < 0.0:
                raise ValueError("auto_link_radius must be non-negative")

            if auto_link_radius > 0.0:
                for other_id, (ox, oy) in sorted(self._positions.items()):
                    if other_id == clean_id:
                        continue
                    dist = hypot(px - ox, py - oy)
                    if dist <= auto_link_radius:
                        cost = round(max(0.5, dist / 180.0), 2)
                        rssi = round(max(-120.0, -62.0 - (dist / auto_link_radius) * 32.0), 1)
                        snr = round(max(-10.0, 12.0 - (dist / auto_link_radius) * 14.0), 1)
                        loss = round(min(0.45, max(0.01, (dist / auto_link_radius) ** 2 * 0.08)), 3)
                        self._set_link_unlocked(
                            clean_id,
                            other_id,
                            cost=cost,
                            loss_probability=loss,
                            latency_ms=round(25.0 + dist * 0.12, 1),
                            rssi_dbm=rssi,
                            snr_db=snr,
                        )

            if not self._source or self._source not in self._network.nodes:
                self._source = clean_id
            elif not self._destination or self._destination not in self._network.nodes or self._destination == self._source:
                self._destination = clean_id

            return self._snapshot_unlocked()

    def toggle_node(self, node_id: str, *, available: bool | None = None) -> dict[str, object]:
        """Turn a node ON or OFF and recalculate routes immediately."""
        with self._lock:
            clean_id = _validate_node_id(node_id)
            if clean_id not in self._network.nodes:
                raise ValueError(f"unknown node: {clean_id}")
            node = self._network.nodes[clean_id]
            new_state = (not node.available) if available is None else bool(available)
            node.available = new_state
            if new_state:
                self._failure_detector.mark_node_recovered(clean_id)
            else:
                self._failure_detector.mark_node_failed(clean_id)
            return self._snapshot_unlocked()

    def move_node(self, node_id: str, x: float, y: float) -> dict[str, object]:
        """Update canvas coordinates of an existing node."""
        with self._lock:
            clean_id = _validate_node_id(node_id)
            if clean_id not in self._network.nodes:
                raise ValueError(f"unknown node: {clean_id}")
            px = _validate_coord(x, "x")
            py = _validate_coord(y, "y")
            self._positions[clean_id] = (px, py)
            return self._snapshot_unlocked()

    def set_link(
        self,
        first: str,
        second: str,
        *,
        cost: float = 1.0,
        loss_probability: float = 0.02,
        latency_ms: float = 45.0,
        rssi_dbm: float = -72.0,
        snr_db: float = 9.5,
    ) -> dict[str, object]:
        """Add or update an undirected radio link between two nodes."""
        with self._lock:
            u = _validate_node_id(first)
            v = _validate_node_id(second)
            if u == v:
                raise ValueError("cannot link a node to itself")
            if u not in self._network.nodes or v not in self._network.nodes:
                raise ValueError("both link endpoints must exist")
            self._set_link_unlocked(
                u,
                v,
                cost=cost,
                loss_probability=loss_probability,
                latency_ms=latency_ms,
                rssi_dbm=rssi_dbm,
                snr_db=snr_db,
            )
            return self._snapshot_unlocked()

    def remove_link(self, first: str, second: str) -> dict[str, object]:
        """Remove an undirected link between two nodes."""
        with self._lock:
            u = _validate_node_id(first)
            v = _validate_node_id(second)
            key = self._edge_key(u, v)
            self._link_profiles.pop(key, None)
            self._rebuild_topology_unlocked()
            return self._snapshot_unlocked()

    def set_endpoints(self, source: str, destination: str) -> dict[str, object]:
        """Update the selected source and destination nodes for route visualization."""
        with self._lock:
            u = _validate_node_id(source)
            v = _validate_node_id(destination)
            if u not in self._network.nodes or v not in self._network.nodes:
                raise ValueError("source and destination must be existing nodes")
            self._source = u
            self._destination = v
            return self._snapshot_unlocked()

    def simulate_packet(
        self,
        source: str,
        destination: str,
        *,
        routing_mode: str = "ml",
        max_retries: int = 2,
    ) -> dict[str, object]:
        """Compute route and simulate hop-by-hop packet delivery with timing metrics."""
        with self._lock:
            u = _validate_node_id(source)
            v = _validate_node_id(destination)
            if u not in self._network.nodes or v not in self._network.nodes:
                raise ValueError("source and destination must be existing nodes")
            if routing_mode not in ("ml", "static"):
                raise ValueError("routing_mode must be 'ml' or 'static'")
            if not isinstance(max_retries, int) or isinstance(max_retries, bool) or not 0 <= max_retries <= 5:
                raise ValueError("max_retries must be an integer between 0 and 5")

            self._source = u
            self._destination = v
            route_info = self._compute_routes_unlocked(u, v)
            chosen_route = (
                route_info["ml_route"] if routing_mode == "ml" else route_info["static_route"]
            )

            hop_trace: list[dict[str, object]] = []
            total_latency_ms = 0.0

            if not chosen_route:
                delivery_status = DeliveryStatus.FAILED.value
                total_attempts = 0
            elif len(chosen_route) == 1:
                delivery_status = DeliveryStatus.DELIVERED.value
                total_attempts = 0
            else:
                delivery_mgr = DeliveryManager(RetryPolicy(max_retries=max_retries))
                packet = Packet(f"sim-{int(time.time() * 1000)}", u, v, b"mesh-probe")

                def transmit_hop(src: str, dst: str) -> bool:
                    nonlocal total_latency_ms
                    key = self._edge_key(src, dst)
                    profile = self._link_profiles.get(key, LinkProfile())
                    hop_lat = round(profile.latency_ms * self._rng.uniform(0.9, 1.15), 2)
                    total_latency_ms += hop_lat
                    src_ok = self._network.nodes[src].available
                    dst_ok = self._network.nodes[dst].available
                    if not src_ok or not dst_ok:
                        delivered = False
                        reason = "node_unavailable"
                    elif not self._network.topology.has_link(src, dst):
                        delivered = False
                        reason = "no_link"
                    elif self._rng.random() < profile.loss_probability:
                        delivered = False
                        reason = "packet_loss"
                    else:
                        delivered = True
                        reason = "delivered"

                    self._failure_detector.record_hop_outcome(src, dst, delivered=delivered)
                    hop_trace.append(
                        {
                            "from": src,
                            "to": dst,
                            "delivered": delivered,
                            "reason": reason,
                            "latency_ms": hop_lat,
                            "rssi_dbm": profile.rssi_dbm,
                            "snr_db": profile.snr_db,
                        }
                    )
                    return delivered

                outcome = delivery_mgr.deliver(packet, chosen_route, transmit_hop)
                delivery_status = outcome.status.value
                total_attempts = outcome.attempts

            snapshot = self._snapshot_unlocked()
            snapshot["simulation"] = {
                "routing_mode": routing_mode,
                "selected_route": chosen_route,
                "status": delivery_status,
                "attempts": total_attempts,
                "total_latency_ms": round(total_latency_ms, 2),
                "hop_trace": hop_trace,
            }
            return snapshot

    def get_state(self) -> dict[str, object]:
        """Return current topology, diagnostics, and live routing metrics."""
        with self._lock:
            return self._snapshot_unlocked()

    def _set_link_unlocked(
        self,
        first: str,
        second: str,
        *,
        cost: float,
        loss_probability: float,
        latency_ms: float,
        rssi_dbm: float,
        snr_db: float,
    ) -> None:
        if not isfinite(cost) or not 0.1 <= cost <= 100.0:
            raise ValueError("cost must be between 0.1 and 100.0")
        if not isfinite(loss_probability) or not 0.0 <= loss_probability <= 1.0:
            raise ValueError("loss_probability must be between 0.0 and 1.0")
        if not isfinite(latency_ms) or not 1.0 <= latency_ms <= 5000.0:
            raise ValueError("latency_ms must be between 1.0 and 5000.0")
        if not isfinite(rssi_dbm) or not -140.0 <= rssi_dbm <= 0.0:
            raise ValueError("rssi_dbm must be between -140.0 and 0.0")
        if not isfinite(snr_db) or not -30.0 <= snr_db <= 30.0:
            raise ValueError("snr_db must be between -30.0 and 30.0")

        key = self._edge_key(first, second)
        self._link_profiles[key] = LinkProfile(
            cost=round(float(cost), 2),
            loss_probability=round(float(loss_probability), 3),
            latency_ms=round(float(latency_ms), 1),
            rssi_dbm=round(float(rssi_dbm), 1),
            snr_db=round(float(snr_db), 1),
        )
        self._network.add_link(first, second, float(cost))
        self._failure_detector.record_hop_outcome(first, second, delivered=True)

    def _rebuild_topology_unlocked(self) -> None:
        fresh = Network()
        for node_id, node in sorted(self._network.nodes.items()):
            fresh.add_node(Node(node_id, available=node.available))
        for (u, v), profile in sorted(self._link_profiles.items()):
            if u in fresh.nodes and v in fresh.nodes:
                fresh.add_link(u, v, profile.cost)
        self._network = fresh

    def _predict_link_quality_unlocked(self, first: str, second: str) -> float:
        key = self._edge_key(first, second)
        profile = self._link_profiles.get(key, LinkProfile())
        emp_delivery = max(0.0, min(1.0, 1.0 - profile.loss_probability))
        rssi_norm = max(0.0, min(1.0, (profile.rssi_dbm + 140.0) / 100.0))
        snr_norm = max(0.0, min(1.0, (profile.snr_db + 20.0) / 40.0))
        features = LinkFeatures(
            delivery_ratio=emp_delivery,
            mean_latency_seconds=profile.latency_ms / 1000.0,
            retransmission_rate=min(1.0, profile.loss_probability * 0.8),
            rssi_normalized=rssi_norm,
            snr_normalized=snr_norm,
            recent_availability=1.0 if not self._failure_detector.is_link_failed(first, second) else 0.0,
            stability_score=max(0.0, min(1.0, 1.0 - profile.loss_probability)),
        )
        return self._predictor.predict(features).probability

    def _compute_routes_unlocked(self, source: str, destination: str) -> dict[str, object]:
        if source not in self._network.nodes or destination not in self._network.nodes:
            return {
                "source": source,
                "destination": destination,
                "static_route": None,
                "static_cost": None,
                "static_compute_us": 0.0,
                "ml_route": None,
                "ml_cost": None,
                "ml_compute_us": 0.0,
                "estimated_end_to_end_delivery": 0.0,
                "estimated_latency_ms": 0.0,
            }

        # 1. Static Dijkstra over nominal topology (ignoring live node failures/RF quality)
        t0 = time.perf_counter()
        static_route = shortest_path(self._network.topology, source, destination)
        static_us = round((time.perf_counter() - t0) * 1_000_000.0, 2)
        static_cost = (
            round(path_cost(self._network.topology, static_route), 3)
            if static_route is not None
            else None
        )

        # 2. Failure-aware + ML link-quality RouteManager
        manager = RouteManager(
            self._network,
            failure_detector=self._failure_detector,
            link_quality_fn=self._predict_link_quality_unlocked,
            penalty_weight=2.5,
        )
        t1 = time.perf_counter()
        ml_route = manager.find_route(source, destination)
        ml_us = round((time.perf_counter() - t1) * 1_000_000.0, 2)
        ml_cost = (
            round(manager.route_cost(ml_route), 3)
            if ml_route is not None
            else None
        )

        e2e_prob = 1.0
        est_latency_ms = 0.0
        if ml_route and len(ml_route) > 1:
            for u, v in zip(ml_route, ml_route[1:]):
                key = self._edge_key(u, v)
                prof = self._link_profiles.get(key, LinkProfile())
                e2e_prob *= max(0.01, 1.0 - prof.loss_probability)
                est_latency_ms += prof.latency_ms
        elif not ml_route:
            e2e_prob = 0.0

        return {
            "source": source,
            "destination": destination,
            "static_route": static_route,
            "static_cost": static_cost,
            "static_compute_us": static_us,
            "ml_route": ml_route,
            "ml_cost": ml_cost,
            "ml_compute_us": ml_us,
            "estimated_end_to_end_delivery": round(e2e_prob, 4),
            "estimated_latency_ms": round(est_latency_ms, 1),
        }

    def _snapshot_unlocked(self) -> dict[str, object]:
        diag = diagnose_network(self._network, failure_detector=self._failure_detector)
        nodes_list = [
            {
                "node_id": node_id,
                "available": node.available,
                "x": self._positions.get(node_id, (100.0, 100.0))[0],
                "y": self._positions.get(node_id, (100.0, 100.0))[1],
            }
            for node_id, node in sorted(self._network.nodes.items())
        ]
        links_list = []
        for (u, v), prof in sorted(self._link_profiles.items()):
            ml_prob = round(self._predict_link_quality_unlocked(u, v), 3)
            links_list.append(
                {
                    "source": u,
                    "target": v,
                    "cost": prof.cost,
                    "loss_probability": prof.loss_probability,
                    "latency_ms": prof.latency_ms,
                    "rssi_dbm": prof.rssi_dbm,
                    "snr_db": prof.snr_db,
                    "ml_probability": ml_prob,
                    "failed": self._failure_detector.is_link_failed(u, v),
                }
            )

        routing = self._compute_routes_unlocked(self._source, self._destination)
        return {
            "nodes": nodes_list,
            "links": links_list,
            "diagnostics": {
                "total_nodes": diag.total_nodes,
                "available_nodes": diag.available_nodes,
                "unavailable_nodes": list(diag.unavailable_nodes),
                "isolated_nodes": list(diag.isolated_nodes),
                "active_link_count": diag.active_link_count,
            },
            "routing": routing,
        }
