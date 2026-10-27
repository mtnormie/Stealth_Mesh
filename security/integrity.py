"""HMAC-SHA256 message integrity and sliding-window anti-replay protection."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import hmac

HMAC_SIZE = 32
MIN_KEY_SIZE = 16


def compute_hmac(key: bytes, data: bytes) -> bytes:
    """Compute a 32-byte HMAC-SHA256 authentication tag."""
    if not isinstance(key, bytes) or not isinstance(data, bytes):
        raise TypeError("key and data must be bytes")
    if len(key) < MIN_KEY_SIZE:
        raise ValueError(f"HMAC key must be at least {MIN_KEY_SIZE} bytes")
    return hmac.new(key, data, hashlib.sha256).digest()


def verify_hmac(key: bytes, data: bytes, signature: bytes) -> bool:
    """Verify an HMAC-SHA256 tag in constant time."""
    if not isinstance(key, bytes) or not isinstance(data, bytes) or not isinstance(signature, bytes):
        raise TypeError("key, data, and signature must be bytes")
    if len(key) < MIN_KEY_SIZE or len(signature) != HMAC_SIZE:
        return False
    expected = hmac.new(key, data, hashlib.sha256).digest()
    return hmac.compare_digest(expected, signature)


class ReplayWindow:
    """Per-sender sliding bitmask anti-replay tracker (RFC 6479 style).

    Crucially separates ``can_accept`` (read-only pre-check) from ``record``
    (state update after cryptographic verification) so unauthenticated packets
    with forged high sequence numbers cannot advance the window and cause DoS.
    """

    def __init__(self, *, window_size: int = 64, max_senders: int = 1024) -> None:
        if isinstance(window_size, bool) or not isinstance(window_size, int) or window_size < 1:
            raise ValueError("window_size must be a positive integer")
        if isinstance(max_senders, bool) or not isinstance(max_senders, int) or max_senders < 1:
            raise ValueError("max_senders must be a positive integer")
        self.window_size = window_size
        self.max_senders = max_senders
        # Maps sender_id -> (highest_sequence, bitmask_of_seen_offsets)
        self._state: OrderedDict[str, tuple[int, int]] = OrderedDict()

    @staticmethod
    def _validate_inputs(sender: str, sequence: int) -> str:
        if not isinstance(sender, str) or not sender.strip():
            raise ValueError("sender must be a non-empty string")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("sequence must be a positive integer (>= 1)")
        return sender.strip()

    def can_accept(self, sender: str, sequence: int) -> bool:
        """Return True if (sender, sequence) is fresh and within the replay window."""
        clean_sender = self._validate_inputs(sender, sequence)
        entry = self._state.get(clean_sender)
        if entry is None:
            return True
        highest, bitmap = entry
        if sequence > highest:
            return True
        offset = highest - sequence
        if offset >= self.window_size:
            return False
        return (bitmap & (1 << offset)) == 0

    def record(self, sender: str, sequence: int) -> bool:
        """Commit a verified (sender, sequence) to the sliding window.

        Returns True if accepted and recorded, or False if it is a replay/stale.
        """
        clean_sender = self._validate_inputs(sender, sequence)
        if not self.can_accept(clean_sender, sequence):
            return False

        mask_limit = (1 << self.window_size) - 1
        entry = self._state.get(clean_sender)
        if entry is None:
            self._state[clean_sender] = (sequence, 1)
            self._state.move_to_end(clean_sender)
            while len(self._state) > self.max_senders:
                self._state.popitem(last=False)
            return True

        highest, bitmap = entry
        if sequence > highest:
            shift = sequence - highest
            if shift >= self.window_size:
                new_bitmap = 1
            else:
                new_bitmap = ((bitmap << shift) | 1) & mask_limit
            self._state[clean_sender] = (sequence, new_bitmap)
        else:
            offset = highest - sequence
            self._state[clean_sender] = (highest, bitmap | (1 << offset))

        self._state.move_to_end(clean_sender)
        return True
