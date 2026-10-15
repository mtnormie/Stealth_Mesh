"""Tests for queued and reliable in-memory delivery."""

import unittest

from core.packet import Packet
from transport.acknowledgements import AcknowledgementTracker
from transport.delivery_manager import DeliveryManager, DeliveryStatus
from transport.deduplication import Deduplicator
from transport.message_queue import MessageQueue
from transport.retry_policy import RetryPolicy


def packet(message_id: str = "message-1") -> Packet:
    return Packet(message_id, "a", "c", b"hello")


class DeliveryTests(unittest.TestCase):
    def test_queue_deduplicates_while_pending_and_is_fifo(self) -> None:
        queue = MessageQueue()
        first, second = packet(), packet("message-2")
        self.assertTrue(queue.enqueue(first))
        self.assertFalse(queue.enqueue(packet()))
        self.assertTrue(queue.enqueue(second))
        self.assertIs(queue.dequeue(), first)
        self.assertTrue(queue.enqueue(packet()))
        self.assertIs(queue.dequeue(), second)
        self.assertIsNotNone(queue.dequeue())
        self.assertIsNone(queue.dequeue())

    def test_retries_hop_until_success_and_acknowledges(self) -> None:
        acknowledgements = AcknowledgementTracker()
        manager = DeliveryManager(RetryPolicy(max_retries=2), acknowledgements=acknowledgements)
        outcomes = iter([False, True, True])
        calls: list[tuple[str, str]] = []

        def transmit(source: str, destination: str) -> bool:
            calls.append((source, destination))
            return next(outcomes)

        result = manager.deliver(packet(), ["a", "b", "c"], transmit)
        self.assertEqual(result.status, DeliveryStatus.DELIVERED)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(calls, [("a", "b"), ("a", "b"), ("b", "c")])
        self.assertTrue(acknowledgements.is_acknowledged("message-1"))

    def test_retry_exhaustion_is_bounded_and_can_be_retried_later(self) -> None:
        manager = DeliveryManager(RetryPolicy(max_retries=1))
        failed = manager.deliver(packet(), ["a", "c"], lambda _a, _b: False)
        self.assertEqual(failed.status, DeliveryStatus.FAILED)
        self.assertEqual(failed.attempts, 2)
        succeeded = manager.deliver(packet(), ["a", "c"], lambda _a, _b: True)
        self.assertEqual(succeeded.status, DeliveryStatus.DELIVERED)

    def test_duplicate_message_is_not_delivered_twice(self) -> None:
        manager = DeliveryManager(deduplicator=Deduplicator(capacity=2))
        calls = 0

        def transmit(_a: str, _b: str) -> bool:
            nonlocal calls
            calls += 1
            return True

        self.assertEqual(manager.deliver(packet(), ["a", "c"], transmit).status,
                         DeliveryStatus.DELIVERED)
        self.assertEqual(manager.deliver(packet(), ["a", "c"], transmit).status,
                         DeliveryStatus.DUPLICATE)
        self.assertEqual(calls, 1)

    def test_invalid_policy_and_route(self) -> None:
        with self.assertRaises(ValueError):
            RetryPolicy(max_retries=-1)
        with self.assertRaises(ValueError):
            Deduplicator(capacity=0)
        with self.assertRaises(ValueError):
            DeliveryManager().deliver(packet(), ["x", "c"], lambda _a, _b: True)


if __name__ == "__main__":
    unittest.main()
