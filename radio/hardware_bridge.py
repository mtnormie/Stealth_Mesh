"""Live hardware bridge between the localhost Python server and physical ESP32-C3 LoRa nodes."""

from __future__ import annotations

import glob
import ipaddress
import json
import os
import re
import select
import threading
import time
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.services.group_service import GroupService
from app.services.status_service import NetworkSandboxService

_SAFE_SERIAL_RE = re.compile(r"^(/dev/tty(?:ACM|USB|S)\d+|/dev/cu\.[A-Za-z0-9._-]+|COM\d+)$")
_CTRL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f|]")


def _validate_serial_port(raw_port: str) -> str:
    cleaned = raw_port.strip()
    if not cleaned:
        return ""
    if not _SAFE_SERIAL_RE.match(cleaned):
        raise ValueError("invalid serial port device path")
    return cleaned


def _validate_http_node_url(raw_url: str) -> str:
    cleaned = raw_url.strip().rstrip("/")
    if not cleaned:
        return ""
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "http://" + cleaned
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("invalid http_node_url")
    if parsed.username or parsed.password:
        raise ValueError("credentials not allowed in http_node_url")
    host = parsed.hostname.lower()
    if host != "localhost":
        try:
            ip = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("http_node_url must target localhost or a private LAN IP") from exc
        if ip.is_link_local or (not ip.is_loopback and not ip.is_private):
            raise ValueError("http_node_url cannot target link-local or public IP addresses")
    return f"{parsed.scheme}://{parsed.netloc}"


def _sanitize_serial_field(value: str, fallback: str, max_len: int) -> str:
    cleaned = _CTRL_CHARS_RE.sub(" ", value or "").strip()
    return (cleaned or fallback)[:max_len]


def _configure_posix_serial(fd: int) -> None:
    """Configure an open POSIX tty file descriptor for 115200 8N1 raw non-blocking I/O."""
    try:
        import termios  # POSIX standard library

        attrs = termios.tcgetattr(fd)
        baud = getattr(termios, "B115200", termios.B9600)
        attrs[0] = 0  # iflag
        attrs[1] = 0  # oflag
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # cflag
        attrs[3] = 0  # lflag
        attrs[4] = baud  # ispeed
        attrs[5] = baud  # ospeed
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except Exception:
        pass


class HardwareNodeBridge:
    """Bridge localhost Messenger & Admin Console with physical ESP32-C3 + SX1276 nodes (USB Serial or HTTP)."""

    def __init__(
        self,
        group_service: GroupService,
        sandbox_service: NetworkSandboxService,
        *,
        serial_port: str | None = None,
        http_node_url: str | None = None,
    ) -> None:
        self.groups = group_service
        self.sandbox = sandbox_service
        self._lock = threading.RLock()
        self._serial_port = (serial_port or os.environ.get("STEALTH_MESH_SERIAL", "")).strip()
        self._http_node_url = (http_node_url or os.environ.get("STEALTH_MESH_NODE_URL", "")).strip().rstrip("/")
        self._serial_fd: int | None = None
        self._active_transport: str = "disconnected"
        self._gateway_node_id: str = ""
        self._radio_ok: bool = False
        self._tx_count: int = 0
        self._rx_count: int = 0
        self._relay_count: int = 0
        self._last_hop_trace: str = ""
        self._neighbors: dict[str, dict[str, object]] = {}
        self._running: bool = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the background listener thread for USB Serial and HTTP node synchronization."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._worker_loop, name="StealthMeshHwBridge", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the background listener thread and close any open serial descriptor."""
        with self._lock:
            self._running = False
            self._close_serial()

    def configure_connection(
        self,
        *,
        serial_port: str | None = None,
        http_node_url: str | None = None,
    ) -> dict[str, object]:
        """Update the target USB serial port or HTTP node URL (e.g. http://192.168.4.1) at runtime."""
        with self._lock:
            if serial_port is not None:
                self._serial_port = _validate_serial_port(serial_port)
                self._close_serial()
            if http_node_url is not None:
                self._http_node_url = _validate_http_node_url(http_node_url)
        return self.get_status()

    def get_status(self) -> dict[str, object]:
        """Return current hardware bridge connection state and discovered physical LoRa neighbors."""
        now = time.time()
        with self._lock:
            active_neighbors = [
                {
                    **info,
                    "age_sec": max(0, int(now - float(info.get("updated_at", now)))),
                }
                for info in self._neighbors.values()
                if (now - float(info.get("updated_at", 0.0))) <= 120.0
            ]
            return {
                "connected": self._active_transport != "disconnected",
                "transport": self._active_transport,
                "serial_port": self._serial_port or self._auto_find_serial_port() or "",
                "http_node_url": self._http_node_url,
                "gateway_node_id": self._gateway_node_id or "LOCAL-SIM",
                "radio_ok": self._radio_ok,
                "tx_count": self._tx_count,
                "rx_count": self._rx_count,
                "relay_count": self._relay_count,
                "last_hop_trace": self._last_hop_trace,
                "neighbors": active_neighbors,
            }

    def trigger_beacon(self) -> bool:
        """Request the connected physical ESP32-C3 node to broadcast a LoRa discovery beacon."""
        with self._lock:
            if self._serial_fd is not None:
                try:
                    os.write(self._serial_fd, b"BEACON\n")
                    return True
                except OSError:
                    self._close_serial()
            target_url = self._http_node_url
        if target_url:
            try:
                req = Request(f"{target_url}/api/beacon", data=b"", method="POST")
                with urlopen(req, timeout=1.5) as resp:
                    return resp.status == 200
            except Exception:
                return False
        return False

    def send_over_lora(
        self,
        group_id: str,
        sender: str,
        body: str,
        destination: str = "BROADCAST",
    ) -> bool:
        """Transmit a message over physical 868 MHz LoRa if a hardware node is connected via USB or HTTP."""
        clean_gid = _sanitize_serial_field(group_id, "mesh-default", 24)
        clean_snd = _sanitize_serial_field(sender, "User", 28)
        clean_dst = _sanitize_serial_field(destination, "BROADCAST", 32)
        clean_body = _CTRL_CHARS_RE.sub(" ", body or "").strip()[:120]
        if not clean_body:
            return False

        with self._lock:
            if self._serial_fd is not None:
                line = f"SEND|{clean_gid}|{clean_snd}|{clean_dst}|{clean_body}\n"
                try:
                    os.write(self._serial_fd, line.encode("utf-8"))
                    self._tx_count += 1
                    return True
                except OSError:
                    self._close_serial()
            target_url = self._http_node_url

        if target_url:
            try:
                payload = json.dumps(
                    {
                        "group_id": clean_gid,
                        "sender": clean_snd,
                        "destination": clean_dst,
                        "body": clean_body,
                    }
                ).encode("utf-8")
                req = Request(
                    f"{target_url}/api/messages",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        with self._lock:
                            self._tx_count += 1
                        return True
            except Exception:
                return False
        return False

    def _auto_find_serial_port(self) -> str | None:
        if self._serial_port and os.path.exists(self._serial_port):
            return self._serial_port
        patterns = ("/dev/ttyACM*", "/dev/ttyUSB*", "/dev/cu.usbmodem*", "/dev/cu.usbserial*")
        for pat in patterns:
            matches = sorted(glob.glob(pat))
            if matches:
                return matches[0]
        return None

    def _close_serial(self) -> None:
        if self._serial_fd is not None:
            try:
                os.close(self._serial_fd)
            except OSError:
                pass
            self._serial_fd = None
        if self._active_transport == "usb-serial":
            self._active_transport = "disconnected"

    def _try_open_serial(self) -> bool:
        if self._serial_fd is not None:
            return True
        port = self._auto_find_serial_port()
        if not port:
            return False
        try:
            fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            _configure_posix_serial(fd)
            self._serial_fd = fd
            self._serial_port = port
            self._active_transport = "usb-serial"
            return True
        except OSError:
            return False

    def _handle_serial_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        if line.startswith("[StealthMesh] Node:"):
            parts = line.split()
            if len(parts) >= 3:
                with self._lock:
                    self._gateway_node_id = parts[2].strip()
                    self._radio_ok = "SX1276: OK" in line
            return

        if not line.startswith("{"):
            return
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            return
        if not isinstance(ev, dict):
            return

        kind = str(ev.get("event", ""))
        if kind == "status":
            with self._lock:
                self._gateway_node_id = str(ev.get("node_id", self._gateway_node_id or "Node"))
                self._radio_ok = bool(ev.get("radio_ok", False))
                self._tx_count = int(ev.get("tx_count", self._tx_count))
                self._rx_count = int(ev.get("rx_count", self._rx_count))
                self._relay_count = int(ev.get("relay_count", self._relay_count))
                self._last_hop_trace = str(ev.get("hop_trace", self._last_hop_trace))
            nbrs = ev.get("neighbors")
            if isinstance(nbrs, list):
                for n in nbrs:
                    if isinstance(n, dict) and n.get("node_id"):
                        self._record_neighbor_and_topology(
                            str(n["node_id"]),
                            int(n.get("rssi", -75)),
                            float(n.get("snr", 8.0)),
                            int(n.get("hops", 1)),
                        )
        elif kind == "tx_ok":
            with self._lock:
                self._radio_ok = True
                self._last_hop_trace = str(ev.get("trace", ""))
        elif kind == "beacon":
            src = str(ev.get("src", "")).strip()
            rssi = int(ev.get("rssi", -75))
            snr = float(ev.get("snr", 8.0))
            hops = int(ev.get("hops", 1))
            if src:
                self._record_neighbor_and_topology(src, rssi, snr, hops)
        elif kind == "rx":
            src = str(ev.get("src", "")).strip()
            gid = str(ev.get("group", "mesh-default")).strip() or "mesh-default"
            sender = str(ev.get("sender", src or "Node")).strip()
            msg_id = str(ev.get("id", "")).strip()
            body = str(ev.get("msg", "")).strip()
            rssi = int(ev.get("rssi", -75))
            snr = float(ev.get("snr", 8.0))
            hops = int(ev.get("hops", 1))
            with self._lock:
                self._rx_count += 1
            if src:
                self._record_neighbor_and_topology(src, rssi, snr, hops)
            if body:
                self.groups.ingest_remote_message(
                    gid,
                    sender,
                    body,
                    external_id=msg_id or None,
                    source_node=src or None,
                    rssi=rssi,
                    snr=snr,
                    hops=hops,
                )

    def _record_neighbor_and_topology(self, node_id: str, rssi: int, snr: float, hops: int) -> None:
        now = time.time()
        with self._lock:
            prev = self._neighbors.get(node_id, {})
            rx_pkts = int(prev.get("rx_packets", 0)) + 1  # type: ignore[arg-type]
            self._neighbors[node_id] = {
                "node_id": node_id,
                "rssi": rssi,
                "snr": snr,
                "hops": max(1, hops),
                "rx_packets": rx_pkts,
                "updated_at": now,
            }
            gw = self._gateway_node_id or "N1"

        try:
            state = self.sandbox.get_state()
            nodes = state.get("nodes", [])
            known_ids = {n["node_id"] for n in nodes} if isinstance(nodes, list) else set()
            if gw not in known_ids:
                self.sandbox.add_node(gw, 140.0, 220.0)
            if node_id not in known_ids:
                idx = len(known_ids)
                self.sandbox.add_node(node_id, 280.0 + (idx % 3) * 140.0, 120.0 + (idx // 3) * 140.0)
            loss = max(0.01, min(0.65, (abs(rssi) - 65.0) / 120.0)) if rssi < -65 else 0.01
            self.sandbox.set_link(
                gw,
                node_id,
                cost=float(max(1, hops)),
                loss_probability=round(loss, 3),
                latency_ms=42.0 * max(1, hops),
                rssi_dbm=float(rssi),
                snr_db=float(snr),
            )
        except Exception:
            pass

    def _poll_http_node(self, base_url: str) -> None:
        try:
            with urlopen(f"{base_url}/api/status", timeout=1.5) as resp:
                st = json.loads(resp.read().decode("utf-8"))
            with urlopen(f"{base_url}/api/neighbors", timeout=1.5) as resp:
                nbrs = json.loads(resp.read().decode("utf-8"))
            with urlopen(f"{base_url}/api/messages", timeout=1.5) as resp:
                msgs = json.loads(resp.read().decode("utf-8"))

            with self._lock:
                self._active_transport = "wifi-http"
                self._gateway_node_id = str(st.get("node_id", "Node"))
                self._radio_ok = bool(st.get("radio_ok", False))
                self._tx_count = int(st.get("tx_count", 0))
                self._rx_count = int(st.get("rx_count", 0))
                self._relay_count = int(st.get("relay_count", 0))
                self._last_hop_trace = str(st.get("hop_trace", ""))

            if isinstance(nbrs, list):
                for n in nbrs:
                    if isinstance(n, dict) and n.get("node_id"):
                        self._record_neighbor_and_topology(
                            str(n["node_id"]),
                            int(n.get("rssi", -75)),
                            float(n.get("snr", 8.0)),
                            int(n.get("hops", 1)),
                        )
            if isinstance(msgs, list):
                for m in msgs:
                    if isinstance(m, dict) and not m.get("mine", False):
                        self.groups.ingest_remote_message(
                            str(m.get("group_id") or "mesh-default"),
                            str(m.get("sender") or m.get("source_node") or "Node"),
                            str(m.get("body") or ""),
                            external_id=str(m.get("id") or ""),
                            source_node=str(m.get("source_node") or ""),
                            rssi=int(m.get("rssi", -75)) if m.get("rssi") else None,
                            snr=float(m.get("snr", 8.0)) if m.get("snr") else None,
                            hops=int(m.get("hops", 1)),
                        )
        except (URLError, TimeoutError, ValueError, OSError):
            with self._lock:
                if self._active_transport == "wifi-http":
                    self._active_transport = "disconnected"

    def _worker_loop(self) -> None:
        serial_buf = b""
        last_http_poll = 0.0
        while self._running:
            has_serial = self._try_open_serial()
            if has_serial and self._serial_fd is not None:
                try:
                    rlist, _, _ = select.select([self._serial_fd], [], [], 0.25)
                    if rlist:
                        chunk = os.read(self._serial_fd, 512)
                        if not chunk:
                            self._close_serial()
                        else:
                            serial_buf += chunk
                            while b"\n" in serial_buf:
                                raw_line, serial_buf = serial_buf.split(b"\n", 1)
                                self._handle_serial_line(raw_line.decode("utf-8", errors="replace"))
                except OSError:
                    self._close_serial()
                continue

            now = time.monotonic()
            with self._lock:
                target_url = self._http_node_url
            if target_url and (now - last_http_poll >= 2.0):
                last_http_poll = now
                self._poll_http_node(target_url)
            else:
                time.sleep(0.5)
