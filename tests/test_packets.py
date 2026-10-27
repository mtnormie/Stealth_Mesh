"""Tests for packet/message validation, hop-limit constraints, and binary wire format."""

import unittest

from core.message import Message
from core.node import Node
from core.packet import Packet
from core.topology import Topology
from monitoring.metrics import Metrics


class PacketTests(unittest.TestCase):
    def test_packet_Rejects_whitespace_identifiers_and_invalid_fields(self) -> None:
        with self.assertRaises(ValueError):
            Packet("   ", "a", "b", b"data")
        with self.assertRaises(ValueError):
            Packet("m1", "a", "   ", b"data")
        with self.assertRaises(ValueError):
            Packet("m1", "a", "b", b"data", packet_id=" ")
        with self.assertRaises(TypeError):
            Packet("m1", "a", "b", "not-bytes")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Packet(None, "a", "b", b"data")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Packet("m1", "a", "b", b"data", hop_limit=True)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Packet("m1", "a", "b", b"data", version=True)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            Packet("m1", "a", "b", b"data", hop_limit=-1)
        with self.assertRaises(ValueError):
            Packet("m1", "a", "b", b"data", hop_limit=256)
        with self.assertRaises(ValueError):
            Packet("m1", "a", "b", b"data", version=0)

    def test_packet_immutability_and_multi_hop_forwarding(self) -> None:
        initial = Packet("m1", "node-a", "node-c", b"payload", hop_limit=2, version=1)
        hop1 = initial.forwarded()
        hop2 = hop1.forwarded()
        self.assertEqual(initial.hop_limit, 2)
        self.assertEqual(hop1.hop_limit, 1)
        self.assertEqual(hop2.hop_limit, 0)
        self.assertEqual(hop2.payload, b"payload")
        with self.assertRaises(ValueError):
            hop2.forwarded()

    def test_packet_binary_wire_format_roundtrip_and_crc32_verification(self) -> None:
        pkt = Packet(
            message_id="msg-001",
            source="N1",
            destination="N6",
            payload=b"\x01\x02encrypted-lora-frame\xff",
            hop_limit=7,
            packet_id="pkt-xyz",
            version=1,
        )
        wire = pkt.to_bytes()
        restored = Packet.from_bytes(wire)
        self.assertEqual(restored, pkt)

        # Flip 1 bit in the payload -> CRC-32 must reject
        corrupted = bytearray(wire)
        corrupted[-6] ^= 0x01
        with self.assertRaises(ValueError):
            Packet.from_bytes(bytes(corrupted))

        # Truncated frame -> rejected
        with self.assertRaises(ValueError):
            Packet.from_bytes(wire[:8])

        with self.assertRaises(TypeError):
            Packet.from_bytes("not-bytes")  # type: ignore[arg-type]

    def test_message_and_model_type_hardening(self) -> None:
        with self.assertRaises(TypeError):
            Message("a", "b", 123)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Message(123, "b", "hello")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            Message("a", "b", "hello", message_id="   ")
        with self.assertRaises(TypeError):
            Node("n1", available="yes")  # type: ignore[arg-type]

        topo = Topology()
        with self.assertRaises(TypeError):
            topo.add_link("a", "b", cost=True)  # type: ignore[arg-type]

        metrics = Metrics()
        with self.assertRaises(TypeError):
            metrics.record(delivered=True, attempts=True, modeled_latency_seconds=0.1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            metrics.record(delivered=True, attempts=1, modeled_latency_seconds=float("nan"))


if __name__ == "__main__":
    unittest.main()
