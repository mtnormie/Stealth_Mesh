"""Abstract radio interface separating routing/transport from physical transceivers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from radio.simulator import TransmissionResult


@runtime_checkable
class RadioInterface(Protocol):
    """Protocol implemented by software radio simulators and future hardware drivers."""

    def transmit(self, source: str, destination: str) -> TransmissionResult:
        """Attempt a single direct hop from source to destination."""
        ...
