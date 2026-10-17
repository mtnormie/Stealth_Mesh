"""Radio operating states and LoRa modulation parameter validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class RadioMode(str, Enum):
    """Operating state of a simulated or hardware radio transceiver."""

    IDLE = "idle"
    RX = "rx"
    TX = "tx"
    SLEEP = "sleep"


@dataclass(frozen=True, slots=True)
class LoRaModulationConfig:
    """Validated LoRa physical-layer configuration (defaults to EU868 ISM band)."""

    frequency_mhz: float = 868.1
    spreading_factor: int = 7
    bandwidth_khz: float = 125.0
    coding_rate: int = 5
    tx_power_dbm: int = 14

    def __post_init__(self) -> None:
        if not isfinite(self.frequency_mhz) or not 137.0 <= self.frequency_mhz <= 1020.0:
            raise ValueError("frequency_mhz must be between 137.0 and 1020.0 MHz")
        if (
            isinstance(self.spreading_factor, bool)
            or not isinstance(self.spreading_factor, int)
            or not 6 <= self.spreading_factor <= 12
        ):
            raise ValueError("spreading_factor must be an integer in [6, 12]")
        if self.bandwidth_khz not in (7.8, 10.4, 15.6, 20.8, 31.25, 41.7, 62.5, 125.0, 250.0, 500.0):
            raise ValueError("bandwidth_khz must be a standard LoRa bandwidth")
        if (
            isinstance(self.coding_rate, bool)
            or not isinstance(self.coding_rate, int)
            or not 5 <= self.coding_rate <= 8
        ):
            raise ValueError("coding_rate denominator must be an integer in [5, 8] (4/5..4/8)")
        if (
            isinstance(self.tx_power_dbm, bool)
            or not isinstance(self.tx_power_dbm, int)
            or not -9 <= self.tx_power_dbm <= 22
        ):
            raise ValueError("tx_power_dbm must be an integer in [-9, 22] dBm")
