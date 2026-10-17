# Hardware Notes

The radio interface is intentionally hardware agnostic. Record transceiver, antenna, frequency configuration, regional constraints, firmware version, power source, and measured range for every physical experiment. Validate operation under applicable spectrum rules.

## Planned Experimental Target: ESP32-C3 SuperMini + 868 MHz LoRa

Physical hardware integration is currently **planned** (software simulation is used for all current tests). When building experimental 2-node prototypes in the European `EU868` (868.0–868.6 MHz) ISM band:

- **Microcontroller:** `ESP32-C3 SuperMini` (32-bit RISC-V @ 160 MHz, 400 KB SRAM, 4 MB Flash, 3.3 V logic, hardware AES-256/SHA accelerator).
- **Important electrical constraint:** Always connect a tuned **868 MHz antenna** (SMA or IPEX/U.FL dipole) before powering the LoRa transceiver. Never supply 5 V to LoRa logic or power pins (`VCC = 3.3V`).

### Reference Pinout A: SPI Transceiver (`SX1262` / `SX1276`, e.g., `Ra-01SH`, `Ra-01H`, `RFM95W`)

| LoRa Pin | ESP32-C3 SuperMini Pin | Role |
|---|---|---|
| `VCC` / `3.3V` | `3V3` | 3.3 V power supply |
| `GND` | `GND` | Common ground |
| `SCK` | `GPIO4` | SPI clock |
| `MISO` | `GPIO5` | SPI MISO |
| `MOSI` | `GPIO6` | SPI MOSI |
| `NSS` / `CS` | `GPIO7` | SPI chip select |
| `RST` | `GPIO3` | Transceiver hardware reset |
| `DIO0` / `DIO1` | `GPIO2` | Packet TX/RX interrupt |
| `BUSY` (`SX1262` only) | `GPIO1` | Transceiver busy status |

### Reference Pinout B: UART Transceiver (`LLCC68`, e.g., `Ebyte E220-900T22D` DIP 2.54 mm)

| E220-900T22D Pin | ESP32-C3 SuperMini Pin | Role |
|---|---|---|
| `VCC` | `3V3` | 3.3 V – 5 V power supply |
| `GND` | `GND` | Common ground |
| `TXD` | `GPIO20` (`RX`) | UART receive from module |
| `RXD` | `GPIO21` (`TX`) | UART transmit to module |
| `AUX` | `GPIO2` | Module busy / wake indicator |
| `M0`, `M1` | `GPIO3`, `GPIO4` (or `GND` for normal mode) | Operating mode selection |
