"""Tests for packet and message framing validation and hop-limit constraints."""

import unittest

from core.message import Message
from core.packet import Packet


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
        with self.assertRaises(ValueError):
            Packet("m1", "a", "b", b"data", hop_limit=-1)
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

    def test_message_validation_rejects_non_text_and_blank_ids(self) -> None:
        with self.assertRaises(TypeError):
            Message("a", "b", 123)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            Message("a", "b", "hello", message_id="   ")


if __name__ == "__main__":
    unittest.main()
