"""Run the local Stealth Mesh prototype web interface."""

from __future__ import annotations

import json
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import parse_qs, urlparse

from app.services.group_service import GroupService
from app.services.status_service import NetworkSandboxService
from app.ui.network_view import NETWORK_VIEW_HTML

_SERVICE = GroupService()
_SANDBOX = NetworkSandboxService()

_PAGE = """<!doctype html>
<html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stealth Mesh</title><style>
*{box-sizing:border-box}body{margin:0;background:#101820;color:#e9f0f4;font:16px system-ui,sans-serif}
main{max-width:850px;margin:32px auto;padding:20px}.card{background:#1b2934;border:1px solid #334957;border-radius:14px;padding:20px;margin:16px 0}
header{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
h1{margin:0;color:#7de2c3}input,select,button{font:inherit;padding:11px;border-radius:8px;border:1px solid #536977;background:#101820;color:inherit}
button{background:#147d68;border:0;cursor:pointer}form{display:flex;gap:8px;margin:10px 0}form input{flex:1}#messages{height:300px;overflow:auto;border:1px solid #334957;border-radius:8px;padding:12px}
.msg{padding:8px 0;border-bottom:1px solid #334957;overflow-wrap:anywhere}.muted{color:#aab9c2;font-size:.9em}#qr{max-width:210px;background:white;padding:8px}
.navlink{color:#7de2c3;text-decoration:none;padding:9px 14px;border:1px solid #22a88d;border-radius:8px;background:#152c36;font-weight:600}
</style></head><body><main><header><h1>Stealth Mesh</h1><div style="display:flex;gap:10px;align-items:center"><a class="navlink" href="/network" data-en="Open Routing Visualizer">Візуалізатор маршрутизації →</a><button id="language">English</button></div></header><p class="muted" data-en="Local prototype for AES-256-GCM encrypted group messaging.">Локальний прототип групового обміну повідомленнями з AES-256-GCM.</p>
<section class="card"><h2 data-en="Groups">Групи</h2><form id="create"><input name="name" placeholder="Назва нової групи" data-placeholder-en="New group name" maxlength="80" required><button data-en="Create">Створити</button></form>
<form id="join"><input name="token" placeholder="Одноразовий код запрошення" data-placeholder-en="One-time invitation code" required><button data-en="Join">Приєднатися</button></form><select id="groups"><option value="" data-en="Choose a group">Виберіть групу</option></select>
<button id="invite" data-en="Create QR invitation">Створити QR-запрошення</button><div id="invitation"></div></section>
<section class="card"><h2 data-en="Messages">Повідомлення</h2><label><span data-en="Your name">Ваше ім’я</span> <input id="sender" value="Учасник" maxlength="80"></label><div id="messages"></div>
<form id="send"><input name="body" placeholder="Повідомлення" data-placeholder-en="Message" maxlength="4000" required><button data-en="Send">Надіслати</button></form></section>
<p class="muted" data-en="Groups and data are stored in this process memory. QR invitations can be used once and work only while this app instance is running.">Дані та групи зберігаються в пам’яті цього процесу. QR-запрошення одноразове й діє лише поки запущено цей екземпляр.</p>
<script>
let language=localStorage.getItem('stealth-mesh-language')||'uk';
function applyLanguage(){document.documentElement.lang=language;document.querySelectorAll('[data-en]').forEach(e=>{if(language==='en')e.textContent=e.dataset.en;else e.textContent=e.dataset.uk||e.dataset.original||e.textContent});document.querySelectorAll('[data-placeholder-en]').forEach(e=>{if(!e.dataset.placeholderUk)e.dataset.placeholderUk=e.placeholder;e.placeholder=language==='en'?e.dataset.placeholderEn:e.dataset.placeholderUk});document.querySelector('#language').textContent=language==='uk'?'English':'Українська';document.querySelector('#invitation').replaceChildren()}
document.querySelectorAll('[data-en]').forEach(e=>e.dataset.uk=e.textContent);document.querySelector('#language').onclick=()=>{language=language==='uk'?'en':'uk';localStorage.setItem('stealth-mesh-language',language);applyLanguage()};
const api=async(path,data)=>{const r=await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});const j=await r.json();if(!r.ok)throw Error(j.error||'Помилка запиту');return j};
const groups=document.querySelector('#groups'),messages=document.querySelector('#messages');let active='';
function showError(e){alert(language==='uk'?({'group not found':'Групу не знайдено.','invitation is invalid or has already been used':'Запрошення недійсне або вже використане.','group name must contain 1 to 80 characters':'Назва групи має містити від 1 до 80 символів.','sender must contain 1 to 80 characters':'Ім’я має містити від 1 до 80 символів.','message must contain 1 to 4000 characters':'Повідомлення має містити від 1 до 4000 символів.'}[e.message]||'Сталася помилка.'):({'group not found':'Group not found.','invitation is invalid or has already been used':'Invitation is invalid or has already been used.','group name must contain 1 to 80 characters':'Group name must contain 1 to 80 characters.','sender must contain 1 to 80 characters':'Name must contain 1 to 80 characters.','message must contain 1 to 4000 characters':'Message must contain 1 to 4000 characters.'}[e.message]||'Request failed.'))}
async function refreshGroups(selectId){const list=await api('/api/groups');groups.replaceChildren(new Option(language==='uk'?'Виберіть групу':'Choose a group',''));for(const g of list)groups.add(new Option(g.name,g.group_id));if(selectId)groups.value=selectId;active=groups.value;await refreshMessages()}
async function refreshMessages(){active=groups.value;messages.replaceChildren();if(!active)return;for(const m of await api('/api/messages?group_id='+encodeURIComponent(active))){const row=document.createElement('div');row.className='msg';row.textContent=`${m.created_at} · ${m.sender}: ${m.body}`;messages.append(row)}messages.scrollTop=messages.scrollHeight}
document.querySelector('#create').onsubmit=async e=>{e.preventDefault();try{const g=await api('/api/groups',{name:e.target.name.value});e.target.reset();await refreshGroups(g.group_id)}catch(x){showError(x)}};
document.querySelector('#join').onsubmit=async e=>{e.preventDefault();try{const g=await api('/api/join',{token:e.target.token.value.trim()});e.target.reset();await refreshGroups(g.group_id)}catch(x){showError(x)}};
groups.onchange=refreshMessages;
document.querySelector('#invite').onclick=async()=>{try{if(!groups.value)throw Error(language==='uk'?'Спочатку виберіть групу.':'Choose a group first.');const v=await api('/api/invitations',{group_id:groups.value});const box=document.querySelector('#invitation');const p1=document.createElement('p');p1.textContent=language==='uk'?'Одноразовий код: ':'One-time code: ';const code=document.createElement('code');code.textContent=v.token;p1.append(code);const img=document.createElement('img');img.id='qr';img.alt=language==='uk'?'QR-запрошення':'QR invitation';img.src='/qr?data='+encodeURIComponent(v.url);const p2=document.createElement('p');p2.className='muted';p2.textContent=language==='uk'?'Відскануйте QR-код, щоб відкрити запрошення в цьому екземплярі застосунку.':'Scan the QR code to open the invitation in this app instance.';box.replaceChildren(p1,img,p2)}catch(x){showError(x)}};
document.querySelector('#send').onsubmit=async e=>{e.preventDefault();try{if(!groups.value)throw Error(language==='uk'?'Виберіть групу перед надсиланням.':'Choose a group before sending.');await api('/api/messages',{group_id:groups.value,sender:document.querySelector('#sender').value,body:e.target.body.value});e.target.reset();await refreshMessages()}catch(x){showError(x)}};
applyLanguage();
const params=new URLSearchParams(location.search);if(params.has('join')){document.querySelector('#join [name=token]').value=params.get('join');history.replaceState({},'',location.pathname)}
refreshGroups().catch(showError);setInterval(()=>refreshMessages().catch(()=>{}),3000);
</script></main></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "StealthMesh/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                self._send(200, _PAGE.encode(), "text/html; charset=utf-8")
            elif parsed.path == "/network":
                self._send(200, NETWORK_VIEW_HTML.encode(), "text/html; charset=utf-8")
            elif parsed.path == "/api/network/state":
                self._json(200, _SANDBOX.get_state())
            elif parsed.path == "/api/groups":
                self._json(200, _SERVICE.list_groups())
            elif parsed.path == "/api/messages":
                self._json(200, _SERVICE.list_messages(query.get("group_id", [""])[0]))
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
                    svg = (
                        '<svg xmlns="http://www.w3.org/2000/svg" width="210" height="80">'
                        '<rect width="100%" height="100%" fill="#fff"/>'
                        '<text x="10" y="35" fill="#101820" font-size="11" font-family="monospace">'
                        f"{escape(data[:32])}</text>"
                        '<text x="10" y="55" fill="#101820" font-size="11" font-family="monospace">'
                        f"{escape(data[32:64])}</text></svg>"
                    )
                    self._send(200, svg.encode("utf-8"), "image/svg+xml; charset=utf-8")
            else:
                self._json(404, {"error": "not found"})
        except (KeyError, ValueError, TypeError) as error:
            self._json(400, {"error": str(error)})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            data = self._read_json()
            if path == "/api/groups":
                result: object = _SERVICE.create_group(_require_str(data, "name"))
            elif path == "/api/invitations":
                result = _SERVICE.create_invitation(_require_str(data, "group_id"), "http://127.0.0.1:8765/")
            elif path == "/api/join":
                result = _SERVICE.join_group(_require_str(data, "token"))
            elif path == "/api/messages":
                result = _SERVICE.send_message(
                    _require_str(data, "group_id"),
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
            else:
                self._json(404, {"error": "not found"})
                return
            self._json(200, result)
        except (KeyError, ValueError, TypeError, OverflowError, RecursionError, json.JSONDecodeError) as error:
            self._json(400, {"error": str(error)})

    def _read_json(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        if length <= 0 or length > 8192:
            raise ValueError("invalid request size")
        value = json.loads(self.rfile.read(length))
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
    return float(value)


def main() -> None:
    """Start the interface on localhost; no network listener is exposed."""
    address = ("127.0.0.1", 8765)
    print(f"Stealth Mesh UI: http://{address[0]}:{address[1]}")
    with ThreadingHTTPServer(address, _Handler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping Stealth Mesh UI.")


if __name__ == "__main__":
    main()
