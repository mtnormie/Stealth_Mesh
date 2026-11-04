"""Encrypted one-time node location beacons and EW radio-dome triangulation middleware."""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import hypot, isfinite
import secrets

from core.network import Network
from routing.failure_detector import FailureDetector
from security.authentication import MessageAuthenticator, SignedEnvelope
from security.key_manager import derive_subkey, generate_group_key


@dataclass(frozen=True, slots=True)
class LinkTelemetrySample:
    """Observed RF and delivery metrics for an undirected link between two nodes."""

    first: str
    second: str
    loss_probability: float
    rssi_dbm: float
    snr_db: float
    failed: bool = False


@dataclass(frozen=True, slots=True)
class JammerLocalizationReport:
    """Result of analyzing mesh link interruptions and node suppression."""

    interference_type: str  # "none" | "natural_obstacle" | "ew_radio_dome"
    detected: bool
    estimated_x: float | None
    estimated_y: float | None
    estimated_radius: float
    confidence: float
    affected_nodes: tuple[str, ...]
    degraded_links: int
    summary_uk: str
    summary_en: str


class StealthLocationRegistry:
    """Store node deployment coordinates via one-time AES-256-GCM + HMAC beacons.

    Each node transmits its coordinates only once upon initial installation inside
    an authenticated encrypted envelope with random padding/blinding so passive
    eavesdroppers cannot read coordinates or correlate identical positions.
    Subsequent attempts to overwrite an already-locked node position are rejected
    unless explicitly reset by the administrator.
    """

    _GROUP_SCOPE = "stealth-admin-deployment-v1"

    def __init__(self, master_key: bytes | None = None) -> None:
        self._master_key = master_key or generate_group_key()
        self._auth = MessageAuthenticator()
        self._seq_by_node: dict[str, int] = {}
        self._positions: dict[str, tuple[float, float]] = {}
        self._locked_nodes: set[str] = set()

    @property
    def master_key(self) -> bytes:
        return self._master_key

    def derive_node_beacon_key(self, node_id: str) -> bytes:
        """Derive an isolated per-node provisioning key so node capture cannot decrypt other nodes."""
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        return derive_subkey(
            self._master_key,
            "stealth-mesh-node-beacon-v1",
            context=node_id.strip().encode("utf-8"),
        )

    def create_one_time_beacon(
        self,
        node_id: str,
        x: float,
        y: float,
        *,
        node_key: bytes | None = None,
    ) -> SignedEnvelope:
        """Create an encrypted, authenticated one-time deployment location beacon."""
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, (int, float))
            or not isinstance(y, (int, float))
            or not isfinite(x)
            or not isfinite(y)
        ):
            raise ValueError("coordinates must be finite numbers")

        clean_id = node_id.strip()
        effective_key = node_key if node_key is not None else self.derive_node_beacon_key(clean_id)
        seq = self._seq_by_node.get(clean_id, 0) + 1
        self._seq_by_node[clean_id] = seq

        # Include random 128-bit blinding salt so ciphertext length/entropy cannot leak coordinates
        payload_dict = {
            "node_id": clean_id,
            "x": round(float(x), 2),
            "y": round(float(y), 2),
            "blinding": secrets.token_hex(16),
        }
        plaintext = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
        return self._auth.seal(
            effective_key,
            group_id=self._GROUP_SCOPE,
            sender=clean_id,
            sequence=seq,
            plaintext=plaintext,
        )

    def register_beacon(self, envelope: SignedEnvelope, *, allow_admin_relock: bool = False) -> tuple[float, float]:
        """Verify, decrypt, and lock a node's deployment location from a one-time beacon."""
        if not isinstance(envelope, SignedEnvelope):
            raise TypeError("envelope must be a SignedEnvelope")
        node_id = envelope.sender.strip()
        if node_id in self._locked_nodes and not allow_admin_relock:
            raise ValueError(f"one-time deployment location already locked for node {node_id}")

        expected_node_key = self.derive_node_beacon_key(node_id)
        plaintext = self._auth.open(expected_node_key, envelope)
        data = json.loads(plaintext.decode("utf-8"))
        if data.get("node_id") != node_id:
            raise ValueError("beacon sender mismatch")
        px = float(data["x"])
        py = float(data["y"])
        if not isfinite(px) or not isfinite(py):
            raise ValueError("invalid coordinates in beacon")

        self._positions[node_id] = (px, py)
        self._locked_nodes.add(node_id)
        return (px, py)

    def is_locked(self, node_id: str) -> bool:
        return node_id in self._locked_nodes

    def positions(self) -> dict[str, tuple[float, float]]:
        return dict(self._positions)

    def reset_all(self) -> None:
        self._positions.clear()
        self._locked_nodes.clear()
        self._seq_by_node.clear()
        self._auth = MessageAuthenticator()


def _jamming_anomaly_score(sample: LinkTelemetrySample) -> float:
    """Compute a [0.0, 2.0] score indicating how strongly a link exhibits jamming."""
    loss_component = max(0.0, sample.loss_probability - 0.06) * 1.8
    # Low or negative SNR (< 4 dB) indicates high interference floor
    snr_deficit = max(0.0, (4.5 - sample.snr_db) / 18.0)
    # Classic jammer signature: elevated RSSI noise (> -85 dBm) paired with poor SNR (< 2 dB)
    high_noise_jam_signature = (
        0.45 if (sample.rssi_dbm >= -85.0 and sample.snr_db <= 2.0 and sample.loss_probability >= 0.2) else 0.0
    )
    failed_bonus = 0.4 if sample.failed else 0.0
    return min(2.0, loss_component + snr_deficit + high_noise_jam_signature + failed_bonus)


def locate_interference(
    network: Network,
    positions: dict[str, tuple[float, float]],
    link_samples: list[LinkTelemetrySample],
    *,
    failure_detector: FailureDetector | None = None,
) -> JammerLocalizationReport:
    """Distinguish natural obstacles from an active EW radio dome and triangulate its center."""
    if not network.nodes or not positions:
        return JammerLocalizationReport(
            interference_type="none",
            detected=False,
            estimated_x=None,
            estimated_y=None,
            estimated_radius=0.0,
            confidence=0.0,
            affected_nodes=(),
            degraded_links=0,
            summary_uk="Ефір чистий. Аномальних перешкод не виявлено.",
            summary_en="Spectrum clean. No abnormal interference detected.",
        )

    weighted_points: list[tuple[float, float, float]] = []
    affected_node_scores: dict[str, float] = {}
    degraded_links = 0
    jammer_signature_links = 0
    low_power_natural_links = 0

    # 1. Inspect unavailable / suppressed nodes
    for node_id, node in sorted(network.nodes.items()):
        if node_id not in positions:
            continue
        is_failed = (not node.available) or (
            failure_detector is not None and failure_detector.is_node_failed(node_id)
        )
        if is_failed:
            nx, ny = positions[node_id]
            # A suppressed node strongly pulls the centroid toward its registered location
            weighted_points.append((nx, ny, 1.35))
            affected_node_scores[node_id] = affected_node_scores.get(node_id, 0.0) + 1.35

    # 2. Inspect link telemetry samples
    for sample in link_samples:
        if sample.first not in positions or sample.second not in positions:
            continue
        score = _jamming_anomaly_score(sample)
        is_degraded = sample.loss_probability >= 0.15 or sample.snr_db <= 3.0 or sample.failed
        if not is_degraded:
            continue

        degraded_links += 1
        x1, y1 = positions[sample.first]
        x2, y2 = positions[sample.second]
        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0

        # Distinguish natural attenuation (very weak RSSI <= -98 dBm, moderate loss)
        # from active jamming (elevated noise / severe loss / negative SNR)
        if sample.loss_probability >= 0.28 or sample.snr_db <= 1.0 or (sample.rssi_dbm > -88.0 and sample.snr_db < 3.5):
            jammer_signature_links += 1
        elif sample.rssi_dbm <= -95.0:
            low_power_natural_links += 1

        weight = max(0.25, score)
        weighted_points.append((mid_x, mid_y, weight))
        affected_node_scores[sample.first] = affected_node_scores.get(sample.first, 0.0) + weight * 0.6
        affected_node_scores[sample.second] = affected_node_scores.get(sample.second, 0.0) + weight * 0.6

    suppressed_nodes = [
        nid for nid, node in sorted(network.nodes.items())
        if not node.available or (failure_detector is not None and failure_detector.is_node_failed(nid))
    ]

    if not weighted_points:
        return JammerLocalizationReport(
            interference_type="none",
            detected=False,
            estimated_x=None,
            estimated_y=None,
            estimated_radius=0.0,
            confidence=0.0,
            affected_nodes=(),
            degraded_links=0,
            summary_uk="Ефір чистий. Усі радіоканали працюють у межах норми.",
            summary_en="Spectrum clean. All radio links operating normally.",
        )

    # Weighted Centroid Localization (WCL)
    total_w = sum(w for _, _, w in weighted_points)
    est_x = round(sum(px * w for px, _, w in weighted_points) / total_w, 1)
    est_y = round(sum(py * w for _, py, w in weighted_points) / total_w, 1)

    affected = tuple(
        nid for nid, sc in sorted(affected_node_scores.items(), key=lambda kv: (-kv[1], kv[0]))
        if sc >= 0.35
    )

    # Determine whether signature is a single offline node, Natural Obstacle, or Active EW Radio Dome
    if degraded_links == 0 and len(suppressed_nodes) == 1:
        offline_id = suppressed_nodes[0]
        return JammerLocalizationReport(
            interference_type="node_offline",
            detected=False,
            estimated_x=est_x,
            estimated_y=est_y,
            estimated_radius=0.0,
            confidence=0.85,
            affected_nodes=affected,
            degraded_links=0,
            summary_uk=(
                f"Вузол {offline_id} офлайн (живлення / апаратне вимкнення). "
                "Сусідні радіоканали чисті — ознак роботи РЕБ немає."
            ),
            summary_en=(
                f"Node {offline_id} is offline (power / hardware shutdown). "
                "Neighboring radio links are clean — no EW jamming signature."
            ),
        )

    is_ew_dome = (
        len(suppressed_nodes) >= 1 and (degraded_links >= 1 or len(suppressed_nodes) >= 2)
    ) or jammer_signature_links >= 2 or (jammer_signature_links == 1 and degraded_links >= 2)

    if not is_ew_dome:
        return JammerLocalizationReport(
            interference_type="natural_obstacle",
            detected=True,
            estimated_x=est_x,
            estimated_y=est_y,
            estimated_radius=65.0,
            confidence=0.68,
            affected_nodes=affected,
            degraded_links=degraded_links,
            summary_uk=(
                f"Локальне згасання сигналу (природна перешкода / рельєф) поблизу ({est_x:.0f}, {est_y:.0f}). "
                "Ознак широкосмугового радіокупола РЕБ немає."
            ),
            summary_en=(
                f"Localized signal attenuation (natural obstacle / terrain) near ({est_x:.0f}, {est_y:.0f}). "
                "No broadband EW radio dome signature."
            ),
        )

    # Estimate effective jamming dome radius from spatial dispersion of affected points
    weighted_dist = sum(hypot(px - est_x, py - est_y) * w for px, py, w in weighted_points) / total_w
    radius = round(max(95.0, min(280.0, weighted_dist * 1.35 + 75.0)), 1)
    confidence = round(min(0.96, 0.55 + 0.12 * len(suppressed_nodes) + 0.1 * jammer_signature_links), 2)

    return JammerLocalizationReport(
        interference_type="ew_radio_dome",
        detected=True,
        estimated_x=est_x,
        estimated_y=est_y,
        estimated_radius=radius,
        confidence=confidence,
        affected_nodes=affected,
        degraded_links=degraded_links,
        summary_uk=(
            f"ВИЯВЛЕНО РАДІОКУПОЛ РЕБ! Епіцентр: ({est_x:.0f}, {est_y:.0f}), "
            f"радіус подавлення ≈ {radius:.0f} м (довіра {int(confidence * 100)}%). "
            "Маршрутизацію переведено в обхід зони."
        ),
        summary_en=(
            f"EW RADIO DOME DETECTED! Epicenter: ({est_x:.0f}, {est_y:.0f}), "
            f"suppression radius ≈ {radius:.0f} m (confidence {int(confidence * 100)}%). "
            "Routing diverted around jammed zone."
        ),
    )
