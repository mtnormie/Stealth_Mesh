"""Run messages over the software network simulator."""

from __future__ import annotations

from collections.abc import Iterable

from core.network import Network
from core.packet import Packet
from monitoring.event_logger import EventLogger
from radio.simulator import RadioSimulator
from routing.dijkstra import shortest_path
from simulation.results import MessageRun, SimulationResult
from transport.delivery_manager import DeliveryManager, DeliveryResult, DeliveryStatus


class SimulationRunner:
    """Combine deterministic routing, simulated radio, and transport delivery."""

    def __init__(
        self,
        network: Network,
        radio: RadioSimulator,
        delivery: DeliveryManager | None = None,
        event_logger: EventLogger | None = None,
    ) -> None:
        if radio.network is not network:
            raise ValueError("radio simulator must use the supplied network")
        self.network = network
        self.radio = radio
        self.delivery = delivery or DeliveryManager()
        self.event_logger = event_logger or EventLogger()

    def run(self, packets: Iterable[Packet]) -> SimulationResult:
        """Route and deliver packets, returning per-message outcomes and metrics."""
        result = SimulationResult()
        for packet in packets:
            if not isinstance(packet, Packet):
                raise TypeError("packets must contain Packet instances")
            route = shortest_path(self.network.topology, packet.source, packet.destination)
            modeled_latency = 0.0
            if route is None:
                outcome = DeliveryResult(DeliveryStatus.FAILED, 0)
            else:
                def transmit(source: str, destination: str) -> bool:
                    nonlocal modeled_latency
                    transmission = self.radio.transmit(source, destination)
                    modeled_latency += transmission.latency_seconds
                    return transmission.delivered

                outcome = self.delivery.deliver(packet, route, transmit)

            delivered = outcome.status is DeliveryStatus.DELIVERED
            result.metrics.record(
                delivered=delivered,
                attempts=outcome.attempts,
                modeled_latency_seconds=modeled_latency,
            )
            message_run = MessageRun(
                packet.message_id,
                tuple(route) if route is not None else None,
                outcome,
                modeled_latency,
            )
            result.messages.append(message_run)
            self.event_logger.log(
                "message_delivery",
                message_id=packet.message_id,
                status=outcome.status.value,
                attempts=outcome.attempts,
                route=message_run.route,
                modeled_latency_seconds=modeled_latency,
            )
        return result
