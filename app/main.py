"""Run the Stealth Mesh prototype web & iPhone PWA interface."""

from __future__ import annotations

from collections import OrderedDict, deque
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import math
import os
import re
import secrets
import socket
import threading
import time
from urllib.parse import parse_qs, urlparse

from app.services.group_service import GroupService
from app.services.message_service import MeshMessageService
from app.services.status_service import NetworkSandboxService
from app.ui.chat_view import CHAT_VIEW_HTML
from app.ui.mobile_app_view import MOBILE_APP_HTML
from app.ui.network_view import NETWORK_VIEW_HTML
from app.ui.settings_view import APP_ICON_SVG, PWA_MANIFEST_JSON, detect_lan_ip, render_qr_svg
from radio.hardware_bridge import HardwareNodeBridge

_SERVICE = GroupService()
_SERVICE.ensure_group("mesh-default", "Тактичний ефір Mesh (868 МГц)")
_SANDBOX = NetworkSandboxService()
_HW_BRIDGE = HardwareNodeBridge(_SERVICE, _SANDBOX)
_MESH_MESSAGES = MeshMessageService(_SERVICE, _SANDBOX, _HW_BRIDGE)

_HOST_RE = re.compile(r"^([A-Za-z0-9._-]+)(?::(\d{1,5}))?$")
_DEFAULT_ADMIN_TOKEN = secrets.token_urlsafe(24)
_RATE_LOCK = threading.Lock()
_POST_HISTORY: OrderedDict[str, deque[float]] = OrderedDict()
_RATE_LIMIT_MAX_POSTS = 60
_RATE_LIMIT_WINDOW_SEC = 10.0


def _check_rate_limit(client_ip: str) -> bool:
    now = time.monotonic()
    with _RATE_LOCK:
        bucket = _POST_HISTORY.get(client_ip)
        if bucket is None:
            while len(_POST_HISTORY) >= 512:
                _POST_HISTORY.popitem(last=False)
            bucket = deque()
            _POST_HISTORY[client_ip] = bucket
        else:
            _POST_HISTORY.move_to_end(client_ip)
        while bucket and (now - bucket[0]) > _RATE_LIMIT_WINDOW_SEC:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT_MAX_POSTS:
            return False
        bucket.append(now)
        return True


class _BoundedHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with daemon threads and bounded concurrency."""

    allow_reuse_address = True
    daemon_threads = True
    _concurrency_sem = threading.BoundedSemaphore(32)

    def process_request(self, request: object, client_address: object) -> None:
        if not self._concurrency_sem.acquire(blocking=False):
            self.close_request(request)  # type: ignore[arg-type]
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request: object, client_address: object) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._concurrency_sem.release()


class _Handler(BaseHTTPRequestHandler):
    server_version = "StealthMesh/0.2"
    timeout = 5.0

    def _is_loopback(self) -> bool:
        client_ip = str(self.client_address[0]) if self.client_address else ""
        return client_ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1")

    def _is_admin_authorized(self) -> bool:
        env_token = os.environ.get("STEALTH_MESH_ADMIN_TOKEN", "").strip()
        if not env_token and self._is_loopback():
            return True
        expected = env_token or _DEFAULT_ADMIN_TOKEN
        auth_hdr = self.headers.get("Authorization", "").strip()
        token = auth_hdr[7:].strip() if auth_hdr.lower().startswith("bearer ") else self.headers.get("X-Admin-Token", "").strip()
        return bool(token) and hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8"))

    def _is_group_authorized(self, group_id: str) -> bool:
        group_token = self.headers.get("X-Group-Token", "").strip()
        if group_token:
            return _SERVICE.verify_member_token(group_id, group_token)
        return self._is_loopback()

    def _base_url(self) -> str:
        lan_ip = detect_lan_ip()
        bind_port = int(os.environ.get("STEALTH_MESH_PORT", "8765"))
        host_hdr = self.headers.get("Host", "").strip()
        match = _HOST_RE.match(host_hdr)
        if match:
            host_only = match.group(1)
            allowed_hosts = {lan_ip, "192.168.4.1"}
            if host_only in allowed_hosts:
                return f"http://{host_hdr}/"
        return f"http://{lan_ip}:{bind_port}/"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                self._send(200, CHAT_VIEW_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/mobile":
                self._send(200, MOBILE_APP_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path in ("/presentation", "/slides"):
                pres_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    "docs",
                    "isef_ukraine",
                    "3_Prezentatsiya_Stealth_Mesh_12_Slaydiv.html",
                )
                if not os.path.isfile(pres_path):
                    self._json(404, {"error": "presentation file not found"})
                    return
                with open(pres_path, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif parsed.path == "/download/mobile-app":
                payload = MOBILE_APP_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="StealthMesh_Phone_App.html"')
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            elif parsed.path == "/download/apk":
                apk_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mobile_app", "StealthMesh_Tactical_UA_EN.apk")
                if not os.path.isfile(apk_path):
                    self._json(404, {"error": "APK file not built yet"})
                    return
                with open(apk_path, "rb") as f:
                    apk_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.android.package-archive")
                self.send_header("Content-Disposition", 'attachment; filename="StealthMesh_Tactical_UA_EN.apk"')
                self.send_header("Content-Length", str(len(apk_bytes)))
                self.end_headers()
                self.wfile.write(apk_bytes)
            elif parsed.path == "/manifest.json":
                self._send(
                    200,
                    PWA_MANIFEST_JSON.encode("utf-8"),
                    "application/manifest+json; charset=utf-8",
                )
            elif parsed.path == "/icon.svg":
                self._send(200, APP_ICON_SVG.encode("utf-8"), "image/svg+xml; charset=utf-8")
            elif parsed.path in ("/admin", "/network"):
                if not self._is_admin_authorized():
                    self._json(401, {"error": "admin authorization required"})
                    return
                self._send(200, NETWORK_VIEW_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/api/network/state":
                if not self._is_admin_authorized():
                    self._json(401, {"error": "admin authorization required"})
                    return
                state_payload = dict(_SANDBOX.get_state())
                state_payload["hardware"] = _HW_BRIDGE.get_state() if hasattr(_HW_BRIDGE, "get_state") else _HW_BRIDGE.get_status()
                self._json(200, state_payload)
            elif parsed.path in ("/api/hardware/status", "/api/status"):
                self._json(200, _HW_BRIDGE.get_status())
            elif parsed.path == "/api/neighbors":
                self._json(200, _HW_BRIDGE.get_status().get("neighbors", []))
            elif parsed.path == "/api/groups":
                all_groups = _SERVICE.list_groups()
                raw_tokens = self.headers.get("X-Group-Tokens", "").strip()
                if raw_tokens or not self._is_loopback():
                    token_map: dict[str, str] = {}
                    for pair in raw_tokens.split(","):
                        if ":" in pair:
                            k, v = pair.split(":", 1)
                            token_map[k.strip()] = v.strip()
                    visible = [
                        g for g in all_groups
                        if _SERVICE.verify_member_token(g["group_id"], token_map.get(g["group_id"]))
                    ]
                    self._json(200, visible)
                else:
                    self._json(200, all_groups)
            elif parsed.path == "/api/messages":
                gid = query.get("group_id", [""])[0]
                if not self._is_group_authorized(gid):
                    self._json(403, {"error": "group membership token required"})
                    return
                self._json(200, _SERVICE.list_messages(gid))
            elif parsed.path == "/qr":
                data = query.get("data", [""])[0]
                if not data or len(data) > 2048:
                    raise ValueError("invalid QR content")
                try:
                    import qrcode  # type: ignore[import-not-found]

                    image = qrcode.make(data)
                    buffer = BytesIO()
                    image.save(buffer, format="PNG")
                    self._send(200, buffer.getvalue(), "image/png")
                except ImportError:
                    svg = render_qr_svg(data)
                    self._send(200, svg.encode("utf-8"), "image/svg+xml; charset=utf-8")
            else:
                self._json(404, {"error": "not found"})
        except (KeyError, ValueError, TypeError) as error:
            self._json(400, {"error": str(error)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        client_ip = str(self.client_address[0]) if self.client_address else "unknown"
        if not _check_rate_limit(client_ip):
            self._json(429, {"error": "rate limit exceeded"})
            return

        sec_fetch_site = self.headers.get("Sec-Fetch-Site", "").strip().lower()
        if sec_fetch_site and sec_fetch_site not in ("same-origin", "none"):
            self._json(403, {"error": "cross-origin POST forbidden"})
            return

        origin_hdr = self.headers.get("Origin", "").strip()
        host_hdr = self.headers.get("Host", "").strip()
        if origin_hdr and host_hdr:
            parsed_origin = urlparse(origin_hdr)
            if parsed_origin.netloc and parsed_origin.netloc.lower() != host_hdr.lower():
                self._json(403, {"error": "origin mismatch"})
                return

        if path.startswith("/api/network/") or path in (
            "/api/groups/rotate",
            "/api/groups/quarantine",
            "/api/groups/quarantine/release",
            "/api/hardware/connect",
            "/api/hardware/beacon",
            "/api/beacon",
        ):
            if not self._is_admin_authorized():
                self._json(401, {"error": "admin authorization required"})
                return

        try:
            data = self._read_json()
            if path == "/api/groups":
                result: object = _SERVICE.create_group(_require_str(data, "name"))
            elif path == "/api/groups/rotate":
                purge = data.get("purge_previous", False)
                if not isinstance(purge, bool):
                    raise TypeError("purge_previous must be a boolean")
                result = _SERVICE.rotate_group_key(_require_str(data, "group_id"), purge_previous=purge)
            elif path == "/api/groups/quarantine":
                challenge = data.get("challenge")
                if challenge is not None and not isinstance(challenge, str):
                    raise TypeError("challenge must be a string or null")
                reason = data.get("reason", "MIA")
                if not isinstance(reason, str):
                    raise TypeError("reason must be a string")
                rotate_key = data.get("rotate_key", True)
                if not isinstance(rotate_key, bool):
                    raise TypeError("rotate_key must be a boolean")
                result = _SERVICE.quarantine_member(
                    _require_str(data, "group_id"),
                    _require_str(data, "member_id"),
                    reason=reason,
                    challenge=challenge,
                    rotate_key=rotate_key,
                )
            elif path == "/api/groups/quarantine/release":
                resp = data.get("challenge_response")
                if resp is not None and not isinstance(resp, str):
                    raise TypeError("challenge_response must be a string or null")
                result = _SERVICE.release_quarantine(
                    _require_str(data, "group_id"),
                    _require_str(data, "member_id"),
                    challenge_response=resp,
                )
            elif path == "/api/groups/heartbeat":
                gid = _require_str(data, "group_id")
                if not (self._is_admin_authorized() or self._is_group_authorized(gid)):
                    self._json(403, {"error": "group membership token required"})
                    return
                raw_ttl = data.get("ttl_seconds")
                ttl = _require_float(data, "ttl_seconds", 21600.0) if raw_ttl is not None else None
                result = _SERVICE.heartbeat(gid, ttl_seconds=ttl)
            elif path == "/api/groups/duress":
                gid = _require_str(data, "group_id")
                if not (self._is_admin_authorized() or self._is_group_authorized(gid)):
                    self._json(403, {"error": "group membership token required"})
                    return
                result = _SERVICE.trigger_duress_wipe(gid)
            elif path == "/api/invitations":
                gid = _require_str(data, "group_id")
                if not self._is_group_authorized(gid):
                    self._json(403, {"error": "group membership token required"})
                    return
                result = _SERVICE.create_invitation(
                    gid,
                    self._base_url(),
                )
            elif path == "/api/join":
                result = _SERVICE.join_group(_require_str(data, "token"))
            elif path == "/api/messages":
                gid = _require_str(data, "group_id")
                if not self._is_group_authorized(gid):
                    self._json(403, {"error": "group membership token required"})
                    return
                result = _MESH_MESSAGES.dispatch_group_message(
                    gid,
                    _require_str(data, "sender"),
                    _require_str(data, "body"),
                )
            elif path == "/api/network/node/add":
                raw_node_id = data.get("node_id")
                if raw_node_id is not None and not isinstance(raw_node_id, str):
                    raise TypeError("node_id must be a string or null")
                result = _SANDBOX.add_node(
                    raw_node_id,
                    _require_float(data, "x", 200.0),
                    _require_float(data, "y", 200.0),
                    auto_link_radius=_require_float(data, "auto_link_radius", 290.0),
                )
            elif path == "/api/network/node/toggle":
                avail = data.get("available")
                if avail is not None and not isinstance(avail, bool):
                    raise TypeError("available must be a boolean or null")
                result = _SANDBOX.toggle_node(
                    _require_str(data, "node_id"),
                    available=avail,
                )
            elif path == "/api/network/node/move":
                result = _SANDBOX.move_node(
                    _require_str(data, "node_id"),
                    _require_float(data, "x", 100.0),
                    _require_float(data, "y", 100.0),
                )
            elif path == "/api/network/link/set":
                result = _SANDBOX.set_link(
                    _require_str(data, "first"),
                    _require_str(data, "second"),
                    cost=_require_float(data, "cost", 1.0),
                    loss_probability=_require_float(data, "loss_probability", 0.02),
                    latency_ms=_require_float(data, "latency_ms", 45.0),
                    rssi_dbm=_require_float(data, "rssi_dbm", -72.0),
                    snr_db=_require_float(data, "snr_db", 9.5),
                )
            elif path == "/api/network/link/remove":
                result = _SANDBOX.remove_link(_require_str(data, "first"), _require_str(data, "second"))
            elif path == "/api/network/endpoints":
                result = _SANDBOX.set_endpoints(_require_str(data, "source"), _require_str(data, "destination"))
            elif path == "/api/network/reset":
                result = _SANDBOX.reset_default_topology()
            elif path == "/api/network/clear":
                result = _SANDBOX.clear_topology()
            elif path == "/api/network/simulate":
                result = _SANDBOX.simulate_packet(
                    _require_str(data, "source"),
                    _require_str(data, "destination"),
                    routing_mode=_require_str(data, "routing_mode", default="ml"),
                )
            elif path == "/api/network/jammer":
                result = _SANDBOX.simulate_jammer(
                    _require_float(data, "x", 350.0),
                    _require_float(data, "y", 200.0),
                    radius=_require_float(data, "radius", 195.0),
                )
            elif path == "/api/hardware/connect":
                serial_port = data.get("serial_port")
                http_node_url = data.get("http_node_url")
                if serial_port is not None and not isinstance(serial_port, str):
                    raise TypeError("serial_port must be a string")
                if http_node_url is not None and not isinstance(http_node_url, str):
                    raise TypeError("http_node_url must be a string")
                result = _HW_BRIDGE.configure_connection(
                    serial_port=serial_port,
                    http_node_url=http_node_url,
                )
            elif path in ("/api/hardware/beacon", "/api/beacon"):
                result = {"beacon_queued": _HW_BRIDGE.trigger_beacon()}
            else:
                self._json(404, {"error": "not found"})
                return
            self._json(200, result)
        except PermissionError as error:
            self._json(403, {"error": str(error)})
        except socket.timeout:
            self._json(408, {"error": "request timeout"})
        except (KeyError, ValueError, TypeError, OverflowError, RecursionError, json.JSONDecodeError) as error:
            self._json(400, {"error": str(error)})

    def _read_json(self) -> dict[str, object]:
        content_type = self.headers.get("Content-Type", "").strip().lower()
        if not content_type.startswith("application/json"):
            raise ValueError("Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        if length <= 0 or length > 8192:
            raise ValueError("invalid request size")
        def _reject_nonfinite(token: str) -> object:
            raise ValueError(f"non-finite JSON constant not allowed: {token}")
        value = json.loads(self.rfile.read(length), parse_constant=_reject_nonfinite)
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        return value

    def _json(self, status: int, value: object) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def _require_str(data: dict[str, object], key: str, *, default: str | None = None) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _require_float(data: dict[str, object], key: str, default: float) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{key} must be a finite number")
    return result


def main() -> None:
    """Start the web interface (defaults to 127.0.0.1:8765 for safe loopback-only access)."""
    _HW_BRIDGE.start()
    bind_host = os.environ.get("STEALTH_MESH_HOST", "127.0.0.1")
    bind_port = int(os.environ.get("STEALTH_MESH_PORT", "8765"))
    lan_ip = detect_lan_ip()
    print(f"Stealth Mesh Messenger (Local):  http://127.0.0.1:{bind_port}/")
    print(f"Stealth Mesh Admin Console:      http://127.0.0.1:{bind_port}/admin")
    if lan_ip != "127.0.0.1":
        print(f"Stealth Mesh Messenger (iPhone): http://{lan_ip}:{bind_port}/")
    with _BoundedHTTPServer((bind_host, bind_port), _Handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            _HW_BRIDGE.stop()
            print("\nStopping Stealth Mesh UI.")


if __name__ == "__main__":
    main()
