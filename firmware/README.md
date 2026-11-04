# Stealth Mesh Firmware (`ESP32-C3 SuperMini` + `RFM95W-868S2`)

Embedded C++ firmware for the physical Stealth Mesh node using **ESP32-C3 SuperMini** and **HopeRF RFM95W-868S2 (`SX1276`, 868 MHz)**.

## Features

- **`src/radio_driver.cpp`:** Direct SPI register driver for Semtech `SX1276` (`RegVersion == 0x12`), 8-channel 868 MHz ISM frequency table, RSSI/SNR telemetry, and hardware intra-packet **FHSS** (`RegHopPeriod = 0x24` + `DIO2` `FhssChangeChannel`). Defaults to **RX-only** on boot so the PA is protected if powered before the antenna is attached.
- **`src/packet_handler.cpp`:** Binary wire format (`SMSH` magic + `CRC-32`) matching `core/packet.py`, plus a 32-entry ring deduplicator and bounded hop-limit relay forwarding.
- **`src/message_queue.cpp`:** Bounded 16-slot FIFO frame queue in static RAM.
- **`src/main.cpp`:** Autonomous Wi-Fi Access Point (`StealthMesh-N-XXXX`, password `stealthmesh868`) serving an iPhone-ready PWA web messenger at `http://192.168.4.1` and USB-CDC JSON telemetry at `115200` baud.

## Building & Flashing (PlatformIO)

```bash
cd firmware
pio run -t upload
pio device monitor -b 115200
```
