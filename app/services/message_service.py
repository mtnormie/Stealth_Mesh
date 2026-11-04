"""Mesh-routed encrypted group messaging service."""

from __future__ import annotations

from app.services.group_service import GroupService
from app.services.status_service import NetworkSandboxService
from core.packet import Packet


class MeshMessageService:
    """Bridge encrypted group messaging with binary framing and mesh route simulation."""

    def __init__(
        self,
        group_service: GroupService,
        sandbox_service: NetworkSandboxService,
    ) -> None:
        if not isinstance(group_service, GroupService):
            raise TypeError("group_service must be a GroupService")
        if not isinstance(sandbox_service, NetworkSandboxService):
            raise TypeError("sandbox_service must be a NetworkSandboxService")
        self.groups = group_service
        self.sandbox = sandbox_service

    def dispatch_group_message(
        self,
        group_id: str,
        sender: str,
        body: str,
        *,
        source_node: str | None = None,
        destination_node: str | None = None,
        routing_mode: str = "ml",
    ) -> dict[str, object]:
        """Encrypt a group message, pack it into a binary SMSH frame, and route over the mesh."""
        record = self.groups.send_message(group_id, sender, body)
        state = self.sandbox.get_state()
        routing_info = state.get("routing", {})
        default_src = str(routing_info.get("source") or "N1")  # type: ignore[union-attr]
        default_dst = str(routing_info.get("destination") or "N6")  # type: ignore[union-attr]

        src = (source_node or default_src).strip()
        dst = (destination_node or default_dst).strip()

        encrypted_wire_payload = self.groups.get_encrypted_wire_bytes(group_id, record["id"])

        wire_packet = Packet(
            message_id=record["id"],
            source=src if src else "N1",
            destination=dst if dst else "N6",
            payload=encrypted_wire_payload,
            hop_limit=8,
        )
        wire_bytes = wire_packet.to_bytes()

        nodes = state.get("nodes", [])
        known_ids = {n["node_id"] for n in nodes} if isinstance(nodes, list) else set()
        if src in known_ids and dst in known_ids:
            sim = self.sandbox.simulate_packet(src, dst, routing_mode=routing_mode).get("simulation", {})
        else:
            sim = {
                "routing_mode": routing_mode,
                "selected_route": [src, dst],
                "status": "delivered",
                "attempts": 1,
                "total_latency_ms": 0.0,
            }

        return {
            **record,
            "wire_bytes": len(wire_bytes),
            "mesh_delivery": sim,
        }
