"""Interactive browser-based Mesh Routing Visualizer and Topology Sandbox."""

from __future__ import annotations

NETWORK_VIEW_HTML = """<!doctype html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stealth Mesh — Routing Visualizer</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0d151c;color:#e9f0f4;font:15px/1.45 system-ui,-apple-system,sans-serif}
header{display:flex;justify-content:space-between;align-items:center;padding:14px 24px;background:#142029;border-bottom:1px solid #2b3f4e}
.brand{display:flex;align-items:center;gap:18px}
h1{margin:0;font-size:1.35rem;color:#7de2c3}
nav{display:flex;gap:10px}
nav a{color:#cfe0ea;text-decoration:none;padding:8px 14px;border-radius:8px;border:1px solid #354c5c;background:#192834;font-weight:500}
nav a.active{background:#147d68;border-color:#22a88d;color:#fff}
.layout{display:grid;grid-template-columns:1fr 360px;gap:18px;max-width:1360px;margin:18px auto;padding:0 18px}
@media(max-width:1024px){.layout{grid-template-columns:1fr}}
.card{background:#16232d;border:1px solid #2d4252;border-radius:14px;padding:16px}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center}
button,select,input{font:inherit;padding:8px 12px;border-radius:8px;border:1px solid #415a6b;background:#0f1922;color:#e9f0f4}
button{background:#1d313f;cursor:pointer;transition:background .15s}
button:hover{background:#284356}
button.primary{background:#147d68;border-color:#1ea388;color:#fff;font-weight:600}
button.primary:hover{background:#19997f}
button.mode-btn.active{background:#2563eb;border-color:#60a5fa;color:#fff;font-weight:600}
button.danger{background:#7f1d1d;border-color:#b91c1c}
#canvas-wrap{position:relative;border:1px solid #314859;border-radius:12px;overflow:hidden;background:radial-gradient(circle at 50% 50%,#152532 0%,#0c141b 100%)}
canvas{display:block;width:100%;height:540px;cursor:pointer}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:.85rem;color:#b2c5d1}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:5px;vertical-align:middle}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0}
.stat{background:#101a22;border:1px solid #283b49;border-radius:10px;padding:10px}
.stat .label{font-size:.78rem;color:#9ab0be;text-transform:uppercase;letter-spacing:.04em}
.stat .val{font-size:1.18rem;font-weight:700;color:#7de2c3;margin-top:3px}
.route-box{background:#101a22;border:1px solid #283b49;border-radius:10px;padding:11px;margin:10px 0;font-size:.92rem}
.route-path{font-family:ui-monospace,monospace;font-weight:700;color:#7de2c3;word-break:break-all}
.route-path.static{color:#fbbf24}
#hop-log{max-height:195px;overflow-y:auto;background:#0c1319;border:1px solid #263846;border-radius:8px;padding:10px;font-family:ui-monospace,monospace;font-size:.83rem}
.log-item{padding:4px 0;border-bottom:1px solid #1c2b36}
.ok{color:#4ade80}.fail{color:#f87171}.warn{color:#fbbf24}
.hint{font-size:.85rem;color:#9ab0be;margin:6px 0 0}
</style>
</head>
<body>
<header>
  <div class="brand">
    <h1>Stealth Mesh</h1>
    <nav>
      <a href="/" data-en="Encrypted Group Chat">Груповий чат (AES-256-GCM)</a>
      <a href="/network" class="active" data-en="Routing Visualizer">Візуалізатор маршрутизації</a>
    </nav>
  </div>
  <button id="lang-btn">English</button>
</header>

<div class="layout">
  <section class="card">
    <div class="toolbar">
      <button class="mode-btn active" id="mode-toggle" data-en="Mode: Toggle Node ON/OFF (Click) & Drag">Режим: Увімк/Вимк вузол (клік) або перетягування</button>
      <button class="mode-btn" id="mode-add-node" data-en="Mode: Add Node (Click Canvas)">+ Додати вузол (клік по полю)</button>
      <button class="mode-btn" id="mode-link" data-en="Mode: Connect / Degrade Link (Click 2 Nodes)">З’єднати / Погіршити лінк (2 вузли)</button>
      <button id="btn-reset" data-en="Reset 6-Node Mesh">Скинути (6 вузлів)</button>
      <button id="btn-clear" class="danger" data-en="Clear All">Очистити поле</button>
    </div>

    <div id="canvas-wrap">
      <canvas id="mesh-canvas" width="960" height="540"></canvas>
    </div>

    <div class="legend">
      <span><i class="dot" style="background:#22c55e"></i><span data-en="Node ON (Available)">Вузол УВІМК (активний)</span></span>
      <span><i class="dot" style="background:#ef4444"></i><span data-en="Node OFF (Failed/Offline)">Вузол ВИМК (відмова)</span></span>
      <span><i class="dot" style="background:#7de2c3"></i><span data-en="Active ML / Failover Route">Активний маршрут (ML + Failover)</span></span>
      <span><i class="dot" style="background:#fbbf24"></i><span data-en="Static Dijkstra Route">Статичний маршрут Дейкстри</span></span>
      <span><i class="dot" style="background:#f97316"></i><span data-en="Noisy RF Link (High Loss)">Зашумлений радіоканал (втрати)</span></span>
    </div>
    <p class="hint" id="mode-hint" data-en="Tip: Click any node to turn it ON or OFF and watch instant route failover, or drag nodes to move them.">Підказка: клікни на будь-який вузол, щоб ВИМКНУТИ або УВІМКНУТИ його і побачити миттєвий обхід маршруту, або перетягни вузол мишкою.</p>
  </section>

  <aside class="card">
    <h2 style="margin:0 0 12px;font-size:1.15rem;color:#7de2c3" data-en="Routing Control & Speed">Керування маршрутизацією</h2>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
      <label><span class="hint" data-en="Source">Відправник</span><br><select id="sel-src" style="width:100%"></select></label>
      <label><span class="hint" data-en="Destination">Отримувач</span><br><select id="sel-dst" style="width:100%"></select></label>
    </div>

    <div style="margin-bottom:12px">
      <label><span class="hint" data-en="Packet Routing Algorithm">Алгоритм для відправки пакета</span><br>
        <select id="sel-algo" style="width:100%;margin-top:4px">
          <option value="ml" data-en="ML-Assisted + Failure-Aware (RouteManager)">ML-маршрутизація + Обхід відмов (RouteManager)</option>
          <option value="static" data-en="Static Dijkstra (Baseline Topology)">Статичний алгоритм Дейкстри (Baseline)</option>
        </select>
      </label>
    </div>

    <button class="primary" id="btn-send" style="width:100%;padding:11px" data-en="Send Test Packet (Animate Hops)">Надіслати пакет (анімація по хопах)</button>

    <div class="stat-grid">
      <div class="stat">
        <div class="label" data-en="Route Compute Time">Час розрахунку</div>
        <div class="val" id="st-time">0 µs</div>
      </div>
      <div class="stat">
        <div class="label" data-en="Expected Delivery">Ймовірність доставки</div>
        <div class="val" id="st-prob">100%</div>
      </div>
      <div class="stat">
        <div class="label" data-en="Modeled Latency">Очікувана затримка</div>
        <div class="val" id="st-lat">0 ms</div>
      </div>
      <div class="stat">
        <div class="label" data-en="Active Nodes / Links">Активні вузли / лінки</div>
        <div class="val" id="st-nodes">0 / 0</div>
      </div>
    </div>

    <div class="route-box">
      <div class="hint" data-en="Adaptive ML + Failover Route:">Адаптивний маршрут (ML + Failover):</div>
      <div class="route-path" id="rt-ml">—</div>
      <div class="hint" style="margin-top:8px" data-en="Static Baseline Dijkstra Route:">Статичний маршрут Дейкстри (без обходу відмов):</div>
      <div class="route-path static" id="rt-static">—</div>
    </div>

    <h3 style="margin:12px 0 6px;font-size:.95rem" data-en="Live Hop-by-Hop Transmission Log">Журнал передачі пакета по хопах</h3>
    <div id="hop-log"><div class="hint" data-en="Click 'Send Test Packet' or toggle nodes...">Натисніть «Надіслати пакет» або перемикайте вузли...</div></div>
  </aside>
</div>

<script>
let lang = localStorage.getItem('stealth-mesh-language') || 'uk';
document.querySelectorAll('[data-en]').forEach(el => { el.dataset.uk = el.textContent; });
function applyLang() {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-en]').forEach(el => {
    el.textContent = lang === 'en' ? el.dataset.en : el.dataset.uk;
  });
  document.getElementById('lang-btn').textContent = lang === 'uk' ? 'English' : 'Українська';
}
document.getElementById('lang-btn').onclick = () => {
  lang = lang === 'uk' ? 'en' : 'uk';
  localStorage.setItem('stealth-mesh-language', lang);
  applyLang();
  renderCanvas();
};
applyLang();

const canvas = document.getElementById('mesh-canvas');
const ctx = canvas.getContext('2d');
let state = { nodes: [], links: [], diagnostics: {}, routing: {} };
let mode = 'toggle'; // 'toggle' | 'add-node' | 'link'
let draggingNode = null;
let dragMoved = false;
let selectedFirstNode = null;
let packetAnim = null;

async function api(path, body) {
  const res = await fetch(path, body ? {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  } : {});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Request error');
  return data;
}

function setMode(newMode) {
  mode = newMode;
  selectedFirstNode = null;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  if (newMode === 'toggle') document.getElementById('mode-toggle').classList.add('active');
  if (newMode === 'add-node') document.getElementById('mode-add-node').classList.add('active');
  if (newMode === 'link') document.getElementById('mode-link').classList.add('active');
  renderCanvas();
}

document.getElementById('mode-toggle').onclick = () => setMode('toggle');
document.getElementById('mode-add-node').onclick = () => setMode('add-node');
document.getElementById('mode-link').onclick = () => setMode('link');

function syncSelectors() {
  const srcSel = document.getElementById('sel-src');
  const dstSel = document.getElementById('sel-dst');
  const prevSrc = state.routing.source || srcSel.value;
  const prevDst = state.routing.destination || dstSel.value;
  srcSel.replaceChildren();
  dstSel.replaceChildren();
  for (const n of state.nodes) {
    srcSel.add(new Option(n.node_id + (n.available ? '' : ' (OFF)'), n.node_id));
    dstSel.add(new Option(n.node_id + (n.available ? '' : ' (OFF)'), n.node_id));
  }
  if (prevSrc && state.nodes.some(n => n.node_id === prevSrc)) srcSel.value = prevSrc;
  if (prevDst && state.nodes.some(n => n.node_id === prevDst)) dstSel.value = prevDst;
}

function updateStats(s) {
  state = s;
  syncSelectors();
  const r = s.routing || {};
  const d = s.diagnostics || {};
  const algo = document.getElementById('sel-algo').value;
  const computeUs = algo === 'ml' ? (r.ml_compute_us ?? 0) : (r.static_compute_us ?? 0);
  document.getElementById('st-time').textContent = `${computeUs} µs`;
  document.getElementById('st-prob').textContent = `${Math.round((r.estimated_end_to_end_delivery ?? 0) * 100)}%`;
  document.getElementById('st-lat').textContent = `${r.estimated_latency_ms ?? 0} ms`;
  document.getElementById('st-nodes').textContent = `${d.available_nodes ?? 0}/${d.total_nodes ?? 0} · ${d.active_link_count ?? 0}L`;

  document.getElementById('rt-ml').textContent = r.ml_route ? `${r.ml_route.join(' → ')} (cost ${r.ml_cost}, ${r.ml_compute_us} µs)` : (lang === 'en' ? 'No active path' : 'Маршрут недоступний');
  document.getElementById('rt-static').textContent = r.static_route ? `${r.static_route.join(' → ')} (cost ${r.static_cost}, ${r.static_compute_us} µs)` : (lang === 'en' ? 'No path' : 'Немає шляху');
  renderCanvas();
}

function logEvent(html) {
  const box = document.getElementById('hop-log');
  const div = document.createElement('div');
  div.className = 'log-item';
  div.innerHTML = html;
  box.prepend(div);
}

function getCanvasCoords(evt) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  return {
    x: (evt.clientX - rect.left) * scaleX,
    y: (evt.clientY - rect.top) * scaleY
  };
}

function findNodeAt(x, y) {
  for (let i = state.nodes.length - 1; i >= 0; i--) {
    const n = state.nodes[i];
    if (Math.hypot(n.x - x, n.y - y) <= 26) return n;
  }
  return null;
}

canvas.addEventListener('mousedown', e => {
  const pt = getCanvasCoords(e);
  const hit = findNodeAt(pt.x, pt.y);
  if (mode === 'toggle' && hit) {
    draggingNode = hit;
    dragMoved = false;
  }
});

canvas.addEventListener('mousemove', e => {
  if (!draggingNode) return;
  const pt = getCanvasCoords(e);
  if (Math.hypot(pt.x - draggingNode.x, pt.y - draggingNode.y) > 5) {
    dragMoved = true;
    draggingNode.x = Math.max(25, Math.min(canvas.width - 25, pt.x));
    draggingNode.y = Math.max(25, Math.min(canvas.height - 25, pt.y));
    renderCanvas();
  }
});

window.addEventListener('mouseup', async () => {
  if (!draggingNode) return;
  const node = draggingNode;
  const moved = dragMoved;
  draggingNode = null;
  if (moved) {
    const s = await api('/api/network/node/move', { node_id: node.node_id, x: node.x, y: node.y });
    updateStats(s);
  } else {
    const s = await api('/api/network/node/toggle', { node_id: node.node_id });
    updateStats(s);
    const updated = s.nodes.find(n => n.node_id === node.node_id);
    const statusTxt = updated && updated.available
      ? `<span class="ok">ON</span>`
      : `<span class="fail">OFF</span>`;
    const newRoute = s.routing.ml_route ? s.routing.ml_route.join(' → ') : 'NONE';
    logEvent(`[Node ${node.node_id} → ${statusTxt}] Recalculated in <b>${s.routing.ml_compute_us} µs</b>: ${newRoute}`);
  }
});

canvas.addEventListener('click', async e => {
  const pt = getCanvasCoords(e);
  const hit = findNodeAt(pt.x, pt.y);

  if (mode === 'add-node' && !hit) {
    const s = await api('/api/network/node/add', { x: pt.x, y: pt.y, auto_link_radius: 290 });
    updateStats(s);
    const added = s.nodes[s.nodes.length - 1];
    logEvent(`<span class="ok">[+ Node ${added.node_id}]</span> Added at (${Math.round(pt.x)}, ${Math.round(pt.y)}) — route computed in <b>${s.routing.ml_compute_us} µs</b>`);
  } else if (mode === 'link' && hit) {
    if (!selectedFirstNode) {
      selectedFirstNode = hit.node_id;
      renderCanvas();
    } else if (selectedFirstNode === hit.node_id) {
      selectedFirstNode = null;
      renderCanvas();
    } else {
      const u = selectedFirstNode, v = hit.node_id;
      selectedFirstNode = null;
      const existing = state.links.find(l => (l.source === u && l.target === v) || (l.source === v && l.target === u));
      if (!existing) {
        const s = await api('/api/network/link/set', { first: u, second: v, cost: 1.0, loss_probability: 0.02, latency_ms: 42, rssi_dbm: -71, snr_db: 9.5 });
        updateStats(s);
        logEvent(`<span class="ok">[Link ${u} ↔ ${v}]</span> Connected (Healthy, loss 2%)`);
      } else if (existing.loss_probability < 0.25) {
        const s = await api('/api/network/link/set', { first: u, second: v, cost: existing.cost, loss_probability: 0.60, latency_ms: 190, rssi_dbm: -118, snr_db: -11 });
        updateStats(s);
        logEvent(`<span class="warn">[Link ${u} ↔ ${v}]</span> Degraded RF (loss 60%, RSSI -118 dBm) — ML rerouted to: <b>${(s.routing.ml_route || []).join(' → ')}</b>`);
      } else {
        const s = await api('/api/network/link/remove', { first: u, second: v });
        updateStats(s);
        logEvent(`<span class="fail">[Link ${u} ↔ ${v}]</span> Removed`);
      }
    }
  }
});

document.getElementById('sel-src').onchange = async e => {
  const dst = document.getElementById('sel-dst').value;
  if (e.target.value && dst) updateStats(await api('/api/network/endpoints', { source: e.target.value, destination: dst }));
};
document.getElementById('sel-dst').onchange = async e => {
  const src = document.getElementById('sel-src').value;
  if (src && e.target.value) updateStats(await api('/api/network/endpoints', { source: src, destination: e.target.value }));
};
document.getElementById('sel-algo').onchange = () => updateStats(state);

document.getElementById('btn-reset').onclick = async () => {
  const s = await api('/api/network/reset', {});
  updateStats(s);
  logEvent(`<span class="ok">[Reset]</span> Restored 6-node reference mesh topology.`);
};

document.getElementById('btn-clear').onclick = async () => {
  const s = await api('/api/network/clear', {});
  updateStats(s);
  setMode('add-node');
  logEvent(`<span class="warn">[Cleared]</span> Canvas cleared. Click anywhere on the canvas to place nodes!`);
};

document.getElementById('btn-send').onclick = async () => {
  const src = document.getElementById('sel-src').value;
  const dst = document.getElementById('sel-dst').value;
  const algo = document.getElementById('sel-algo').value;
  if (!src || !dst) return;
  const s = await api('/api/network/simulate', { source: src, destination: dst, routing_mode: algo });
  updateStats(s);
  const sim = s.simulation;
  if (!sim || !sim.hop_trace || sim.hop_trace.length === 0) {
    logEvent(`<span class="fail">[Send ${src} → ${dst}]</span> Failed: no active route available.`);
    return;
  }
  animateHops(sim);
};

function animateHops(sim) {
  const nodeMap = Object.fromEntries(state.nodes.map(n => [n.node_id, n]));
  let idx = 0;
  function nextHop() {
    if (idx >= sim.hop_trace.length) {
      packetAnim = null;
      renderCanvas();
      const badge = sim.status === 'delivered'
        ? `<span class="ok">DELIVERED</span>`
        : `<span class="fail">FAILED</span>`;
      logEvent(`<b>[Result ${ badge }]</b> Route: ${(sim.selected_route || []).join(' → ')} | Attempts: ${sim.attempts} | Total latency: ${sim.total_latency_ms} ms`);
      return;
    }
    const hop = sim.hop_trace[idx++];
    const u = nodeMap[hop.from], v = nodeMap[hop.to];
    if (!u || !v) { nextHop(); return; }
    const hopBadge = hop.delivered
      ? `<span class="ok">OK (${hop.latency_ms} ms, RSSI ${hop.rssi_dbm} dBm)</span>`
      : `<span class="fail">FAIL: ${hop.reason}</span>`;
    logEvent(`Hop ${idx}: <b>${hop.from} → ${hop.to}</b> ${hopBadge}`);

    const duration = 380;
    const start = performance.now();
    function step(now) {
      const t = Math.min(1, (now - start) / duration);
      packetAnim = {
        x: u.x + (v.x - u.x) * t,
        y: u.y + (v.y - u.y) * t,
        ok: hop.delivered
      };
      renderCanvas();
      if (t < 1) requestAnimationFrame(step);
      else setTimeout(nextHop, 90);
    }
    requestAnimationFrame(step);
  }
  nextHop();
}

function isEdgeInPath(u, v, path) {
  if (!path || path.length < 2) return false;
  for (let i = 0; i < path.length - 1; i++) {
    if ((path[i] === u && path[i + 1] === v) || (path[i] === v && path[i + 1] === u)) return true;
  }
  return false;
}

function renderCanvas() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const nodeMap = Object.fromEntries(state.nodes.map(n => [n.node_id, n]));
  const mlRoute = (state.routing && state.routing.ml_route) || [];
  const staticRoute = (state.routing && state.routing.static_route) || [];

  // Draw links
  for (const link of state.links) {
    const u = nodeMap[link.source], v = nodeMap[link.target];
    if (!u || !v) continue;
    const inMl = isEdgeInPath(link.source, link.target, mlRoute);
    const inStatic = isEdgeInPath(link.source, link.target, staticRoute);
    const noisy = link.loss_probability >= 0.25;

    // Static route dashed comparison line if different from ML route
    if (inStatic && !inMl) {
      ctx.save();
      ctx.beginPath();
      ctx.setLineDash([7, 6]);
      ctx.moveTo(u.x, u.y);
      ctx.lineTo(v.x, v.y);
      ctx.strokeStyle = '#fbbf24';
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.restore();
    }

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(u.x, u.y);
    ctx.lineTo(v.x, v.y);
    if (inMl) {
      ctx.strokeStyle = '#7de2c3';
      ctx.lineWidth = 5;
      ctx.shadowColor = '#7de2c3';
      ctx.shadowBlur = 12;
    } else if (noisy) {
      ctx.strokeStyle = '#f97316';
      ctx.lineWidth = 2.5;
      ctx.setLineDash([4, 4]);
    } else {
      ctx.strokeStyle = '#355066';
      ctx.lineWidth = 2;
    }
    ctx.stroke();
    ctx.restore();

    // Link label at midpoint
    const mx = (u.x + v.x) / 2, my = (u.y + v.y) / 2;
    ctx.fillStyle = '#0d1720cc';
    ctx.fillRect(mx - 38, my - 11, 76, 20);
    ctx.fillStyle = noisy ? '#fdba74' : (inMl ? '#7de2c3' : '#9fb6c6');
    ctx.font = '11px ui-monospace, monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`c:${link.cost} P:${Math.round(link.ml_probability * 100)}%`, mx, my);
  }

  // Draw nodes
  for (const n of state.nodes) {
    const isSrc = state.routing && state.routing.source === n.node_id;
    const isDst = state.routing && state.routing.destination === n.node_id;
    const isSelected = selectedFirstNode === n.node_id;

    ctx.save();
    ctx.beginPath();
    ctx.arc(n.x, n.y, 24, 0, Math.PI * 2);
    ctx.fillStyle = n.available ? '#132a38' : '#2d161b';
    ctx.fill();
    ctx.lineWidth = isSrc || isDst || isSelected ? 4 : 3;
    ctx.strokeStyle = isSelected ? '#60a5fa' : (n.available ? '#22c55e' : '#ef4444');
    ctx.stroke();

    // Source / Destination outer badge
    if (isSrc || isDst) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, 30, 0, Math.PI * 2);
      ctx.strokeStyle = isSrc ? '#38bdf8' : '#c084fc';
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 3]);
      ctx.stroke();
    }

    ctx.fillStyle = n.available ? '#f1f5f9' : '#fca5a5';
    ctx.font = 'bold 13px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(n.node_id, n.x, n.y - 3);

    ctx.font = '10px system-ui, sans-serif';
    ctx.fillStyle = n.available ? '#4ade80' : '#f87171';
    ctx.fillText(n.available ? (isSrc ? 'SRC' : (isDst ? 'DST' : 'ON')) : 'OFF', n.x, n.y + 11);
    ctx.restore();
  }

  // Draw animated packet pulse
  if (packetAnim) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(packetAnim.x, packetAnim.y, 9, 0, Math.PI * 2);
    ctx.fillStyle = packetAnim.ok ? '#4ade80' : '#ef4444';
    ctx.shadowColor = packetAnim.ok ? '#4ade80' : '#ef4444';
    ctx.shadowBlur = 16;
    ctx.fill();
    ctx.restore();
  }
}

api('/api/network/state').then(updateStats).catch(err => console.error(err));
</script>
</body>
</html>
"""
