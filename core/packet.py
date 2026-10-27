"""Validated packet model, hop-limit handling, and binary wire format."""

from __future__ import annotations

from dataclasses import dataclass, field
import struct
from uuid import uuid4
import zlib

WIRE_MAGIC = b"SMSH"
MAX_WIRE_ID_BYTES = 128
MAX_WIRE_PAYLOAD_BYTES = 4096
_HEADER_STRUCT = struct.Struct("!4sBBBBBBH")
_CRC_STRUCT = struct.Struct("!I")


@dataclass(frozen=True, slots=True)
class Packet:
    """A transportable message payload with bounded forwarding metadata."""

    message_id: str
    source: str
    destination: str
    payload: bytes
    hop_limit: int = 16
    packet_id: str = field(default_factory=lambda: str(uuid4()))
    version: int = 1

    def __post_init__(self) -> None:
        for field_name, value in (
            ("message_id", self.message_id),
            ("packet_id", self.packet_id),
            ("source", self.source),
            ("destination", self.destination),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
            if not value.strip():
                raise ValueError("packet identifiers and endpoints must be non-empty")
        if not isinstance(self.payload, bytes):
            raise TypeError("payload must be bytes")
        if isinstance(self.hop_limit, bool) or not isinstance(self.hop_limit, int):
            raise TypeError("hop_limit must be an integer")
        if not 0 <= self.hop_limit <= 255:
            raise ValueError("hop_limit must be between 0 and 255")
        if isinstance(self.version, bool) or not isinstance(self.version, int):
            raise TypeError("version must be an integer")
        if not 1 <= self.version <= 255:
            raise ValueError("version must be between 1 and 255")

    def forwarded(self) -> Packet:
        """Return a copy for the next relay, decrementing the hop limit."""
        if self.hop_limit == 0:
            raise ValueError("packet hop limit exhausted")
        return Packet(
            self.message_id,
            self.source,
            self.destination,
            self.payload,
            self.hop_limit - 1,
            packet_id=self.packet_id,
            version=self.version,
        )

    def to_bytes(self) -> bytes:
        """Serialize the packet into a CRC-32 protected binary wire frame."""
        pkt_id_b = self.packet_id.encode("utf-8")
        msg_id_b = self.message_id.encode("utf-8")
        src_b = self.source.encode("utf-8")
        dst_b = self.destination.encode("utf-8")

        for name, encoded in (
            ("packet_id", pkt_id_b),
            ("message_id", msg_id_b),
            ("source", src_b),
            ("destination", dst_b),
        ):
            if len(encoded) > MAX_WIRE_ID_BYTES:
                raise ValueError(f"{name} exceeds {MAX_WIRE_ID_BYTES} UTF-8 bytes")

        if len(self.payload) > MAX_WIRE_PAYLOAD_BYTES:
            raise ValueError(f"payload exceeds {MAX_WIRE_PAYLOAD_BYTES} bytes")

        header = _HEADER_STRUCT.pack(
            WIRE_MAGIC,
            self.version,
            self.hop_limit,
            len(pkt_id_b),
            len(msg_id_b),
            len(src_b),
            len(dst_b),
            len(self.payload),
        )
        body = header + pkt_id_b + msg_id_b + src_b + dst_b + self.payload
        crc = zlib.crc32(body) & 0xFFFFFFFF
        return body + _CRC_STRUCT.pack(crc)

    @classmethod
    def from_bytes(cls, raw: bytes) -> Packet:
        """Deserialize and verify a CRC-32 protected binary wire frame."""
        if not isinstance(raw, bytes):
            raise TypeError("raw wire frame must be bytes")
        min_len = _HEADER_STRUCT.size + _CRC_STRUCT.size
        if len(raw) < min_len:
            raise ValueError("wire frame is truncated")

        body = raw[: -_CRC_STRUCT.size]
        (expected_crc,) = _CRC_STRUCT.unpack(raw[-_CRC_STRUCT.size :])
        actual_crc = zlib.crc32(body) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError("wire frame CRC-32 mismatch")

        (
            magic,
            version,
            hop_limit,
            pkt_len,
            msg_len,
            src_len,
            dst_len,
            payload_len,
        ) = _HEADER_STRUCT.unpack_from(body, 0)

        if magic != WIRE_MAGIC:
            raise ValueError("invalid wire frame magic")
        if any(length > MAX_WIRE_ID_BYTES for length in (pkt_len, msg_len, src_len, dst_len)):
            raise ValueError("wire frame identifier length exceeds limit")
        if payload_len > MAX_WIRE_PAYLOAD_BYTES:
            raise ValueError("wire frame payload length exceeds limit")

        expected_body_len = (
            _HEADER_STRUCT.size + pkt_len + msg_len + src_len + dst_len + payload_len
        )
        if len(body) != expected_body_len:
            raise ValueError("wire frame length mismatch")

        offset = _HEADER_STRUCT.size
        try:
            packet_id = body[offset : offset + pkt_len].decode("utf-8")
            offset += pkt_len
            message_id = body[offset : offset + msg_len].decode("utf-8")
            offset += msg_len
            source = body[offset : offset + src_len].decode("utf-8")
            offset += src_len
            destination = body[offset : offset + dst_len].decode("utf-8")
            offset += dst_len
        except UnicodeDecodeError as error:
            raise ValueError("wire frame contains invalid UTF-8 identifier") from error

        payload = body[offset : offset + payload_len]
        return cls(
            message_id=message_id,
            source=source,
            destination=destination,
            payload=payload,
            hop_limit=hop_limit,
            packet_id=packet_id,
            version=version,
        )
