"""Standalone & WebSerial/Localhost Tactical Mobile App UI for Stealth Mesh (Ukrainian & English, Zero Wi-Fi, USB-C OTG)."""

from __future__ import annotations

MOBILE_APP_HTML = r"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="theme-color" content="#080a0f">
<title>Stealth Mesh</title>
<style>
  :root {
    --bg: #080a0f;
    --card: #0e1118;
    --card2: #161b28;
    --border: rgba(125, 211, 252, 0.12);
    --accent: #7dd3fc;
    --accent-bright: #38bdf8;
    --violet: #7c3aed;
    --bubble-out: linear-gradient(135deg, #6d28d9 0%, #4f46e5 55%, #0284c7 100%);
    --accent-dim: rgba(124, 58, 237, 0.22);
    --warn: #f59e0b;
    --danger: #ef4444;
    --text: #f1f5f9;
    --muted: #8b95a8;
  }
  body.nvg-mode {
    --bg: #050000;
    --card: #0e0202;
    --card2: #180404;
    --border: #3a0909;
    --accent: #dc2626;
    --accent-bright: #ef4444;
    --violet: #991b1b;
    --bubble-out: linear-gradient(135deg, #7f1d1d 0%, #991b1b 100%);
    --accent-dim: rgba(220, 38, 38, 0.18);
    --warn: #b91c1c;
    --danger: #ef4444;
    --text: #f87171;
    --muted: #991b1b;
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html, body {
    margin: 0; padding: 0; height: 100%; width: 100%;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    overflow: hidden;
  }
  .app-shell {
    display: flex; flex-direction: column; height: 100dvh; max-width: 600px; margin: 0 auto;
    border-left: 1px solid var(--border); border-right: 1px solid var(--border);
    background: radial-gradient(circle at 15% 15%, rgba(124, 58, 237, 0.08) 0%, transparent 50%),
                radial-gradient(circle at 85% 85%, rgba(56, 189, 248, 0.07) 0%, transparent 50%),
                var(--bg);
  }
  .top-bar {
    background: var(--card); border-bottom: 1px solid var(--border);
    padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; flex-shrink: 0;
  }
  .top-row {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
  }
  .brand {
    display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 15px; letter-spacing: 0.01em;
  }
  .status-dot {
    width: 10px; height: 10px; border-radius: 50%; background: var(--warn);
    box-shadow: 0 0 8px var(--warn); flex-shrink: 0;
  }
  .status-dot.ok {
    background: var(--accent-bright); box-shadow: 0 0 10px var(--accent-bright);
  }
  .emcon-pill {
    font-size: 10px; font-weight: 600; padding: 3px 8px; border-radius: 999px;
    background: rgba(125, 211, 252, 0.10); color: var(--accent); border: 1px solid var(--border);
  }
  .usb-btn {
    width: 100%; padding: 10px 14px; border-radius: 12px; font-size: 13px; font-weight: 700;
    border: none; background: var(--bubble-out); color: #fff;
    cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px;
    box-shadow: 0 2px 12px rgba(124, 58, 237, 0.28);
  }
  .usb-btn.connected {
    background: var(--card2); border: 1px solid var(--border); color: var(--accent);
    font-weight: 600; padding: 7px 12px; font-size: 12px; box-shadow: none;
  }
  .identity-row {
    display: grid; grid-template-columns: 1fr 1fr auto; gap: 6px; align-items: center; font-size: 12px;
  }
  .identity-box {
    min-width: 0; height: 36px; display: flex; align-items: center; gap: 6px; background: var(--card2);
    border: 1px solid var(--border); border-radius: 10px; padding: 0 10px;
  }
  .identity-box label { color: var(--muted); font-size: 11px; white-space: nowrap; }
  .identity-box input, .identity-box select {
    background: transparent; border: none; color: var(--text); font-weight: 600;
    font-size: 13px; width: 100%; min-width: 0; outline: none;
  }
  .icon-btn {
    height: 36px; background: var(--card2); border: 1px solid var(--border); color: var(--text);
    border-radius: 10px; padding: 0 10px; font-size: 12px; font-weight: 600; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center;
  }
  .neighbors-strip {
    display: none; align-items: center; gap: 6px; overflow-x: auto; padding: 6px 12px;
    background: var(--card); border-bottom: 1px solid var(--border); flex-shrink: 0;
    scrollbar-width: none;
  }
  .neighbor-chip {
    font-size: 11px; padding: 4px 10px; border-radius: 999px; white-space: nowrap;
    background: var(--card2); border: 1px solid var(--border); color: var(--text); cursor: pointer;
  }
  .neighbor-chip.active {
    border-color: var(--accent-bright); background: rgba(56, 189, 248, 0.14); color: var(--accent); font-weight: 700;
  }
  .chat-feed {
    flex: 1; overflow-y: auto; padding: 14px 12px; display: flex; flex-direction: column; gap: 8px;
  }
  .empty-hint {
    margin: auto; text-align: center; color: var(--muted); font-size: 13px; max-width: 310px; line-height: 1.5;
    padding: 18px; border: 1px solid var(--border); border-radius: 18px; background: var(--card);
  }
  .msg-bubble {
    max-width: 82%; padding: 9px 13px; border-radius: 18px; font-size: 15px; line-height: 1.38;
    background: var(--card2); border: 1px solid rgba(255,255,255,0.06); align-self: flex-start;
    border-bottom-left-radius: 5px; word-break: break-word; box-shadow: 0 2px 8px rgba(0,0,0,0.24);
  }
  .msg-bubble.mine {
    align-self: flex-end; background: var(--bubble-out); border-color: transparent;
    color: #fff; border-bottom-left-radius: 18px; border-bottom-right-radius: 5px;
  }
  .msg-header {
    display: flex; justify-content: space-between; gap: 10px; font-size: 11px;
    color: var(--accent); margin-bottom: 3px; font-weight: 700;
  }
  .msg-bubble.mine .msg-header { color: rgba(255,255,255,0.85); }
  .msg-meta {
    margin-top: 4px; font-size: 10px; color: rgba(241,245,249,0.62); text-align: right;
  }
  .quick-bar {
    display: flex; gap: 6px; overflow-x: auto; padding: 8px 10px;
    background: var(--card); border-top: 1px solid var(--border); flex-shrink: 0;
    scrollbar-width: none;
  }
  .quick-btn {
    white-space: nowrap; padding: 7px 12px; border-radius: 999px; font-size: 12px; font-weight: 600;
    background: var(--card2); border: 1px solid var(--border); color: var(--text); cursor: pointer;
    flex-shrink: 0;
  }
  .quick-btn:active { transform: scale(0.97); border-color: var(--accent-bright); }
  .quick-btn.sos {
    background: rgba(239, 68, 68, 0.16); border-color: var(--danger); color: #fca5a5;
  }
  .composer {
    display: flex; gap: 8px; padding: 10px 12px calc(10px + env(safe-area-inset-bottom));
    background: var(--card); border-top: 1px solid var(--border); flex-shrink: 0; align-items: center;
  }
  .composer input {
    flex: 1; padding: 11px 16px; border-radius: 22px; border: 1px solid var(--border);
    background: var(--card2); color: var(--text); font-size: 15px; outline: none;
  }
  .composer input:focus { border-color: var(--accent-bright); }
  .send-btn {
    width: 42px; height: 42px; border-radius: 50%; border: none; background: var(--bubble-out);
    color: #fff; font-size: 16px; font-weight: 700; cursor: pointer; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 2px 12px rgba(124, 58, 237, 0.35);
  }
  .modal-backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.78); display: none;
    align-items: center; justify-content: center; padding: 16px; z-index: 50;
  }
  .modal-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 14px;
    padding: 16px; width: 100%; max-width: 360px; display: flex; flex-direction: column; gap: 12px;
  }
</style>
</head>
<body>
<div class="app-shell">
  <!-- TOP STATUS HEADER -->
  <div class="top-bar">
    <div class="top-row">
      <div class="brand">
        <span id="usbDot" class="status-dot"></span>
        <span>STEALTH MESH</span>
      </div>
      <div style="display:flex; gap:5px; align-items:center;">
        <span id="emconPill" class="emcon-pill">🛡️ 0 мВт Wi-Fi/BT</span>
        <button id="langBtn" class="icon-btn" onclick="toggleLang()" title="Змінити мову / Switch language">🇺🇦 UA</button>
        <button id="nvgBtn" class="icon-btn" onclick="toggleNvgMode()" title="Нічний режим ПНБ / Night Vision Mode">🌙 ПНБ</button>
        <button class="icon-btn" onclick="openKeyModal()" title="Ключ шифрування / Group Key">🔑</button>
      </div>
    </div>

    <button id="usbConnectBtn" class="usb-btn" onclick="connectUsbNode()">
      🔌 ПІДКЛЮЧИТИ НОДУ ПО КАБЕЛЮ USB-C
    </button>

    <div class="identity-row">
      <div class="identity-box">
        <label id="lblCallsign">Позивний:</label>
        <input id="callsignInput" type="text" value="Боєць-1" maxlength="24" onchange="saveCallsign()">
      </div>
      <div class="identity-box">
        <label id="lblTarget">Кому:</label>
        <select id="targetSelect">
          <option id="optBroadcast" value="BROADCAST">Усім у групі</option>
        </select>
      </div>
      <button class="icon-btn" onclick="sendRadarPulse()" title="Короткий імпульс 0.05с / 0.05s Discovery Pulse">📡</button>
    </div>
  </div>

  <!-- DISCOVERED NEIGHBORS / RELAYS -->
  <div id="neighborsStrip" class="neighbors-strip">
    <span id="neighborsWaitText" style="font-size:11px; color:var(--muted);">Пасивний ефір 868 МГц: очікування пакетів...</span>
  </div>

  <!-- CHAT MESSAGES FEED -->
  <div id="chatFeed" class="chat-feed">
    <div id="emptyHint" class="empty-hint"></div>
  </div>

  <!-- 1-TAP TACTICAL PRESETS (ZERO TYPING REQUIRED IN COMBAT) -->
  <div id="quickBar" class="quick-bar"></div>

  <!-- TEXT COMPOSER -->
  <form class="composer" onsubmit="handleFormSubmit(event)">
    <input id="msgInput" type="text" placeholder="Повідомлення в ефір..." autocomplete="off">
    <button type="submit" class="send-btn">➤</button>
  </form>
</div>

<!-- MODAL: GROUP AES-256 KEY -->
<div id="keyModal" class="modal-backdrop">
  <div class="modal-card">
    <div id="modalTitle" style="font-weight:800; font-size:15px;">🔑 Ключ шифрування групи (AES-256)</div>
    <div id="modalDesc" style="font-size:12px; color:var(--muted); line-height:1.4;">
      Введіть спільну секретну фразу підрозділу (мінімум 8 символів). Нода тримає ключ лише в RAM (без запису у Flash), а смартфон шифрує його через Android StrongBox/Keystore.
    </div>
    <input id="secretInput" type="password" placeholder="Секретна фраза підрозділу..." style="padding:11px; border-radius:8px; border:1px solid var(--border); background:var(--bg); color:var(--text); font-size:14px;">
    <div style="display:flex; gap:8px; justify-content:space-between; align-items:center;">
      <button id="btnDuressWipe" type="button" class="icon-btn" style="border-color:var(--danger); color:#fca5a5;" onclick="triggerDuressPanic()">🗑 Стерти</button>
      <div style="display:flex; gap:8px;">
        <button id="btnCancelKey" type="button" class="icon-btn" onclick="closeKeyModal()">Скасувати</button>
        <button id="btnSaveKey" type="button" class="icon-btn" style="background:var(--bubble-out); color:#fff; border:none;" onclick="saveGroupSecret()">Активувати</button>
      </div>
    </div>
  </div>
</div>

<script>
  const I18N = {
    uk: {
      langBadge: "🇺🇦 UA",
      nvgBadge: "🌙 ПНБ",
      emconPill: "🛡️ 0 мВт Wi-Fi/BT",
      usbConnect: "🔌 ПІДКЛЮЧИТИ НОДУ ПО КАБЕЛЮ USB-C",
      usbConnectedDefault: "НОДУ ПІДКЛЮЧЕНО ПО USB-C · ЕФІР 868 МГц ГОТОВИЙ",
      usbConnectedNative: "USB-C OTG ПІДКЛЮЧЕНО (ANDROID NATIVE)",
      usbConnectedWeb: "USB-C КАБЕЛЬ ПІДКЛЮЧЕНО · 868 МГц FHSS",
      usbBridgePrefix: "USB-C МІСТ",
      usbActivePrefix: "USB-C АКТИВНИЙ",
      neighborsLabel: "Сусідів",
      relaysLabel: "Ретрансляцій",
      lblCallsign: "Позивний:",
      defaultCallsign: "Боєць-1",
      lblTarget: "Кому:",
      optBroadcast: "Усім у групі",
      allChip: "📢 Усім",
      hopsUnit: "стриб.",
      directLink: "прямий",
      passiveWait: "Пасивний ефір 868 МГц: очікування пакетів...",
      emptyHintHtml: "<b>Режим повного радіомовчання (0 мВт)</b><br><br>1. Переконайтеся, що телефон в <b>Авіарежимі</b>.<br>2. Підключіть кабель <b>USB Type-C</b> від ноди.<br>3. Натисніть швидку кнопку нижче або введіть текст — нода сама зашифрує та передасть його стрибком по 16 частотах.",
      msgPlaceholder: "Повідомлення в ефір...",
      youSuffix: " (Ви)",
      sentMeta: "⚡ Відправлено по LoRa FHSS (16 частот) → ",
      sentBridgeMeta: "⚡ Передано через USB-C міст → 868 МГц FHSS",
      rxRelayPrefix: "Через ",
      rxRelayMid: " ретрансл. · ",
      rxDirectPrefix: "Прямий ефір · ",
      rxLocalMeta: "Локальний радіоефір 868 МГц · ",
      delivered: "доставлено",
      alertNoNode: "Ноду не знайдено. Перевірте, що кабель USB Type-C щільно вставлений у телефон та плату ESP32-C3.",
      alertConnectFirst: "Спочатку підключіть ноду кабелем USB Type-C (натисніть зелену кнопку зверху)!",
      alertUseUsb: "Для прямого підключення по кабелю USB-C використовуйте застосунок Stealth Mesh APK або Chrome на Android.",
      alertKeySaved: "Ключ шифрування підрозділу записано в ноду (FHSS канал #",
      alertKeySynced: "Ключ шифрування синхронізовано з нодою по USB-C.",
      alertKeyShort: "Секретна фраза має містити щонайменше 8 символів.",
      modalTitle: "🔑 Ключ шифрування групи (AES-256)",
      modalDesc: "Введіть спільну секретну фразу підрозділу (мінімум 8 символів). Нода збереже ключ у флеш-пам'яті та синхронізує сітку стрибків частот FHSS.",
      secretPlaceholder: "Секретна фраза підрозділу...",
      btnCancel: "Скасувати",
      btnSave: "Зберегти в ноду",
      quickPresets: [
        { label: "🟢 На позиції", text: "🟢 На позиції, обстановка спокійна", sos: false },
        { label: "🚨 Потрібна допомога (300)", text: "🚨 ТЕРМІНОВО: Потрібна допомога / евакуація 300", sos: true },
        { label: "⚡ Працює РЕБ", text: "⚡ Фіксую роботу РЕБ / завади в секторі", sos: false },
        { label: "👀 Рух / БПЛА", text: "👀 Бачу рух противника / БПЛА в секторі", sos: false },
        { label: "📍 Перекличка", text: "📍 Перекличка: підтвердіть прийом", sos: false },
        { label: "✅ Прийняв", text: "✅ Прийняв, виконую", sos: false }
      ]
    },
    en: {
      langBadge: "🇬🇧 EN",
      nvgBadge: "🌙 NVG",
      emconPill: "🛡️ 0 mW Wi-Fi/BT",
      usbConnect: "🔌 CONNECT NODE VIA USB-C CABLE",
      usbConnectedDefault: "NODE CONNECTED VIA USB-C · 868 MHz READY",
      usbConnectedNative: "USB-C OTG CONNECTED (ANDROID NATIVE)",
      usbConnectedWeb: "USB-C CABLE CONNECTED · 868 MHz FHSS",
      usbBridgePrefix: "USB-C BRIDGE",
      usbActivePrefix: "USB-C ACTIVE",
      neighborsLabel: "Neighbors",
      relaysLabel: "Relays",
      lblCallsign: "Callsign:",
      defaultCallsign: "Fighter-1",
      lblTarget: "To:",
      optBroadcast: "All in group",
      allChip: "📢 All",
      hopsUnit: "hops",
      directLink: "direct",
      passiveWait: "Passive 868 MHz airwaves: waiting for packets...",
      emptyHintHtml: "<b>Total Radio Silence Mode (0 mW)</b><br><br>1. Keep phone in <b>Airplane Mode</b>.<br>2. Plug in the <b>USB Type-C</b> cable from the node.<br>3. Tap a quick report button below or type a message — the node encrypts and bursts it across 16 FHSS channels.",
      msgPlaceholder: "Message to tactical mesh...",
      youSuffix: " (You)",
      sentMeta: "⚡ Burst via LoRa FHSS (16 ch) → ",
      sentBridgeMeta: "⚡ Sent via USB-C bridge → 868 MHz FHSS",
      rxRelayPrefix: "Via ",
      rxRelayMid: " relays · ",
      rxDirectPrefix: "Direct RF · ",
      rxLocalMeta: "868 MHz Tactical Mesh · ",
      delivered: "delivered",
      alertNoNode: "Node not detected. Check that the USB Type-C cable is firmly plugged into both the phone and ESP32-C3 board.",
      alertConnectFirst: "Connect the node via USB Type-C cable first (tap the green button at the top)!",
      alertUseUsb: "For direct USB-C cable connection, use the Stealth Mesh APK app or Chrome on Android.",
      alertKeySaved: "Unit encryption key provisioned to node (FHSS seed #",
      alertKeySynced: "Encryption key synchronized with node over USB-C.",
      alertKeyShort: "Passphrase must be at least 8 characters long.",
      modalTitle: "🔑 Group Encryption Key (AES-256)",
      modalDesc: "Enter the shared unit passphrase (min 8 chars). The node stores the key in NVS flash and synchronizes the 16-channel FHSS hopping sequence.",
      secretPlaceholder: "Shared unit passphrase...",
      btnCancel: "Cancel",
      btnSave: "Save to node",
      quickPresets: [
        { label: "🟢 In Position", text: "🟢 In position, sector clear", sos: false },
        { label: "🚨 Need CASEVAC (300)", text: "🚨 URGENT: Need assistance / CASEVAC (300)", sos: true },
        { label: "⚡ EW Jamming", text: "⚡ Detecting active EW jamming in sector", sos: false },
        { label: "👀 Contact / UAV", text: "👀 Visual on enemy movement / UAV in sector", sos: false },
        { label: "📍 Radio Check", text: "📍 Radio check: confirm copy", sos: false },
        { label: "✅ Wilco", text: "✅ Copy that, executing", sos: false }
      ]
    }
  };

  let currentLang = localStorage.getItem("smsh_lang") === "en" ? "en" : "uk";
  let transportMode = "none"; // "android_native" | "webserial" | "server"
  let isUsbConnected = false;
  let lastUsbSubtitle = "";
  let serialPort = null;
  let serialBuffer = "";
  let renderedIds = new Set();
  let knownNeighbors = {};

  function t(key) {
    return (I18N[currentLang] && I18N[currentLang][key]) || I18N.uk[key] || key;
  }

  function applyLanguage() {
    document.documentElement.lang = currentLang;
    document.getElementById("langBtn").textContent = t("langBadge");
    document.getElementById("nvgBtn").textContent = t("nvgBadge");
    document.getElementById("emconPill").textContent = t("emconPill");
    document.getElementById("lblCallsign").textContent = t("lblCallsign");
    document.getElementById("lblTarget").textContent = t("lblTarget");
    document.getElementById("optBroadcast").textContent = t("optBroadcast");
    document.getElementById("emptyHint").innerHTML = t("emptyHintHtml");
    document.getElementById("msgInput").placeholder = t("msgPlaceholder");
    document.getElementById("modalTitle").textContent = t("modalTitle");
    document.getElementById("modalDesc").textContent = t("modalDesc");
    document.getElementById("secretInput").placeholder = t("secretPlaceholder");
    document.getElementById("btnCancelKey").textContent = t("btnCancel");
    document.getElementById("btnSaveKey").textContent = t("btnSave");

    const csInput = document.getElementById("callsignInput");
    if (!localStorage.getItem("smsh_callsign")) {
      csInput.value = t("defaultCallsign");
    }

    // Render quick preset buttons
    const qBar = document.getElementById("quickBar");
    qBar.innerHTML = "";
    t("quickPresets").forEach(preset => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "quick-btn" + (preset.sos ? " sos" : "");
      btn.textContent = preset.label;
      btn.onclick = () => sendQuick(preset.text);
      qBar.appendChild(btn);
    });

    setUsbConnectedUi(isUsbConnected, lastUsbSubtitle);
    updateNeighborsUi([]);
  }

  function toggleLang() {
    currentLang = currentLang === "uk" ? "en" : "uk";
    localStorage.setItem("smsh_lang", currentLang);
    applyLanguage();
  }

  const savedCallsign = localStorage.getItem("smsh_callsign");
  if (savedCallsign) {
    document.getElementById("callsignInput").value = savedCallsign;
  }
  if (localStorage.getItem("smsh_nvg") === "1") {
    document.body.classList.add("nvg-mode");
  }

  function toggleNvgMode() {
    document.body.classList.toggle("nvg-mode");
    localStorage.setItem("smsh_nvg", document.body.classList.contains("nvg-mode") ? "1" : "0");
  }

  function saveCallsign() {
    const val = (document.getElementById("callsignInput").value || t("defaultCallsign")).trim();
    localStorage.setItem("smsh_callsign", val);
    sendRawUsbCommand("CALLSIGN|" + val);
  }

  function setUsbConnectedUi(connected, subtitle) {
    isUsbConnected = connected;
    if (subtitle !== undefined) lastUsbSubtitle = subtitle;
    const dot = document.getElementById("usbDot");
    const btn = document.getElementById("usbConnectBtn");
    if (connected) {
      dot.classList.add("ok");
      btn.classList.add("connected");
      btn.textContent = "✅ " + (lastUsbSubtitle || t("usbConnectedDefault"));
    } else {
      dot.classList.remove("ok");
      btn.classList.remove("connected");
      btn.textContent = t("usbConnect");
    }
  }

  async function connectUsbNode() {
    if (window.AndroidUsbBridge && typeof window.AndroidUsbBridge.connectUsb === "function") {
      const ok = window.AndroidUsbBridge.connectUsb();
      if (ok) {
        transportMode = "android_native";
        setUsbConnectedUi(true, t("usbConnectedNative"));
        sendRawUsbCommand("STATUS");
        return;
      }
    }

    if ("serial" in navigator) {
      try {
        serialPort = await navigator.serial.requestPort();
        await serialPort.open({ baudRate: 115200 });
        transportMode = "webserial";
        setUsbConnectedUi(true, t("usbConnectedWeb"));
        readWebSerialLoop();
        await sendRawUsbCommand("CALLSIGN|" + (document.getElementById("callsignInput").value || t("defaultCallsign")).trim());
        await sendRawUsbCommand("STATUS");
        return;
      } catch (err) {
        console.warn("WebSerial open cancelled or failed, checking localhost bridge:", err);
      }
    }

    try {
      const res = await fetch("/api/hardware/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ serial_port: "" })
      });
      const data = await res.json();
      if (data && data.serial_connected) {
        transportMode = "server";
        setUsbConnectedUi(true, t("usbBridgePrefix") + " (" + (data.serial_port || "USB") + ") · 868 MHz FHSS");
      } else {
        alert(t("alertNoNode"));
      }
    } catch (e) {
      alert(t("alertUseUsb"));
    }
  }

  async function readWebSerialLoop() {
    const decoder = new TextDecoder();
    while (serialPort && serialPort.readable) {
      const reader = serialPort.readable.getReader();
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          if (value) {
            serialBuffer += decoder.decode(value, { stream: true });
            let nl;
            while ((nl = serialBuffer.indexOf("\n")) !== -1) {
              const line = serialBuffer.slice(0, nl).trim();
              serialBuffer = serialBuffer.slice(nl + 1);
              if (line) handleIncomingSerialLine(line);
            }
          }
        }
      } catch (e) {
        break;
      } finally {
        reader.releaseLock();
      }
    }
    setUsbConnectedUi(false, "");
  }

  window.onNativeUsbLine = function(line) {
    handleIncomingSerialLine(line);
  };

  function handleIncomingSerialLine(line) {
    if (!line.startsWith("{")) return;
    try {
      const evt = JSON.parse(line);
      if (evt.event === "status") {
        if (evt.callsign && !localStorage.getItem("smsh_callsign")) {
          document.getElementById("callsignInput").value = evt.callsign;
        }
        setUsbConnectedUi(
          true,
          t("usbActivePrefix") + " · " + t("neighborsLabel") + ": " + (evt.neighbors_online || 0) + " · " + t("relaysLabel") + ": " + (evt.relay_count || 0)
        );
        if (Array.isArray(evt.neighbors)) {
          updateNeighborsUi(evt.neighbors);
        }
      } else if (evt.event === "rx") {
        const sender = evt.sender || evt.src || "Node";
        const body = evt.body || evt.msg || "";
        const hops = evt.hops || 1;
        const rssi = evt.rssi || -75;
        const snr = evt.snr || 5.0;
        const msgId = evt.msg_id || evt.id || (sender + "-" + Date.now());
        if (evt.dst !== "BEACON" && !body.startsWith("BCN|")) {
          appendMessageBubble({
            id: msgId,
            sender: sender,
            body: body,
            mine: false,
            meta: (hops > 1 ? t("rxRelayPrefix") + hops + t("rxRelayMid") : t("rxDirectPrefix")) + rssi + " dBm (SNR " + snr + " dB)"
          });
        }
      } else if (evt.event === "provisioned") {
        alert(t("alertKeySaved") + evt.fhss_seed + ").");
      }
    } catch (e) {}
  }

  function updateNeighborsUi(neighbors) {
    const strip = document.getElementById("neighborsStrip");
    const select = document.getElementById("targetSelect");
    const currentTarget = select ? select.value : "BROADCAST";

    neighbors.forEach(n => {
      if (n && n.node_id) knownNeighbors[n.node_id] = n;
    });

    const ids = Object.keys(knownNeighbors);
    if (ids.length === 0) {
      strip.style.display = "none";
      return;
    }

    strip.style.display = "flex";
    strip.innerHTML = "";
    const allChip = document.createElement("span");
    allChip.className = "neighbor-chip" + (currentTarget === "BROADCAST" ? " active" : "");
    allChip.textContent = t("allChip") + " (" + ids.length + ")";
    allChip.onclick = () => { select.value = "BROADCAST"; updateNeighborsUi([]); };
    strip.appendChild(allChip);

    select.innerHTML = '<option id="optBroadcast" value="BROADCAST">' + t("optBroadcast") + '</option>';
    ids.forEach(id => {
      const n = knownNeighbors[id];
      const hops = n.hops || 1;
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id + " (" + hops + " " + t("hopsUnit") + ")";
      select.appendChild(opt);

      const chip = document.createElement("span");
      chip.className = "neighbor-chip" + (currentTarget === id ? " active" : "");
      chip.textContent = "📡 " + id + " · " + (hops > 1 ? hops + " " + t("hopsUnit") : t("directLink")) + " (" + n.rssi + " dBm)";
      chip.onclick = () => { select.value = id; updateNeighborsUi([]); };
      strip.appendChild(chip);
    });
    if (currentTarget && (currentTarget === "BROADCAST" || knownNeighbors[currentTarget])) {
      select.value = currentTarget;
    }
  }

  async function sendRawUsbCommand(cmdLine) {
    const payload = cmdLine.trim() + "\n";
    if (transportMode === "android_native" && window.AndroidUsbBridge) {
      window.AndroidUsbBridge.sendLine(payload);
      return true;
    }
    if (transportMode === "webserial" && serialPort && serialPort.writable) {
      const writer = serialPort.writable.getWriter();
      try {
        await writer.write(new TextEncoder().encode(payload));
        return true;
      } finally {
        writer.releaseLock();
      }
    }
    return false;
  }

  async function transmitTacticalMessage(text) {
    const cleanText = (text || "").trim().replace(/\|/g, "/");
    if (!cleanText) return;
    const callsign = (document.getElementById("callsignInput").value || t("defaultCallsign")).trim().replace(/\|/g, "-");
    const target = document.getElementById("targetSelect").value || "BROADCAST";
    localStorage.setItem("smsh_callsign", callsign);

    if (transportMode === "android_native" || transportMode === "webserial") {
      const cmd = "SEND|mesh-default|" + callsign + "|" + target + "|" + cleanText;
      const ok = await sendRawUsbCommand(cmd);
      if (ok) {
        appendMessageBubble({
          id: "local-" + Date.now(),
          sender: callsign + t("youSuffix"),
          body: cleanText,
          mine: true,
          meta: t("sentMeta") + (target === "BROADCAST" ? t("optBroadcast") : target)
        });
        return;
      }
    }

    try {
      const res = await fetch("/api/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          group_id: "mesh-default",
          sender: callsign,
          body: cleanText
        })
      });
      if (res.ok) {
        appendMessageBubble({
          id: "local-" + Date.now(),
          sender: callsign + t("youSuffix"),
          body: cleanText,
          mine: true,
          meta: t("sentBridgeMeta")
        });
        return;
      }
    } catch (e) {}

    alert(t("alertConnectFirst"));
  }

  function sendQuick(presetText) {
    transmitTacticalMessage(presetText);
  }

  function handleFormSubmit(e) {
    e.preventDefault();
    const input = document.getElementById("msgInput");
    const text = input.value;
    if (!text.trim()) return;
    input.value = "";
    transmitTacticalMessage(text);
  }

  async function sendRadarPulse() {
    if (await sendRawUsbCommand("PING")) return;
    try {
      await fetch("/api/hardware/beacon", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
    } catch (e) {}
  }

  function openKeyModal() {
    document.getElementById("keyModal").style.display = "flex";
  }
  function closeKeyModal() {
    document.getElementById("keyModal").style.display = "none";
  }
  async function saveGroupSecret() {
    const sec = (document.getElementById("secretInput").value || "").trim();
    if (sec.length < 8) {
      alert(t("alertKeyShort"));
      return;
    }
    if (window.AndroidUsbBridge && typeof window.AndroidUsbBridge.storeSecret === "function") {
      window.AndroidUsbBridge.storeSecret(sec);
    }
    if (await sendRawUsbCommand("SECRET|" + sec)) {
      closeKeyModal();
      return;
    }
    try {
      await fetch("/api/hardware/secret", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ secret: sec })
      });
      closeKeyModal();
      alert(t("alertKeySynced"));
    } catch (e) {
      alert(t("alertConnectFirst"));
    }
  }

  async function triggerDuressPanic() {
    if (window.AndroidUsbBridge && typeof window.AndroidUsbBridge.wipeSecrets === "function") {
      window.AndroidUsbBridge.wipeSecrets();
    } else {
      await sendRawUsbCommand("WIPE");
    }
    localStorage.clear();
    renderedIds.clear();
    document.getElementById("secretInput").value = "";
    document.getElementById("chatFeed").innerHTML = '<div id="emptyHint" class="empty-hint"></div>';
    applyLanguage();
    closeKeyModal();
  }

  function appendMessageBubble(msg) {
    if (msg.id && renderedIds.has(msg.id)) return;
    if (msg.id) renderedIds.add(msg.id);

    const hint = document.getElementById("emptyHint");
    if (hint) hint.style.display = "none";

    const feed = document.getElementById("chatFeed");
    const div = document.createElement("div");
    div.className = "msg-bubble" + (msg.mine ? " mine" : "");

    const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const hdr = document.createElement("div");
    hdr.className = "msg-header";
    hdr.innerHTML = "<span></span><span></span>";
    hdr.children[0].textContent = msg.sender;
    hdr.children[1].textContent = timeStr;

    const body = document.createElement("div");
    body.textContent = msg.body;

    const meta = document.createElement("div");
    meta.className = "msg-meta";
    meta.textContent = msg.meta || "";

    div.appendChild(hdr);
    div.appendChild(body);
    div.appendChild(meta);
    feed.appendChild(div);
    feed.scrollTop = feed.scrollHeight;
  }

  window.addEventListener("DOMContentLoaded", async () => {
    applyLanguage();

    if (window.AndroidUsbBridge && typeof window.AndroidUsbBridge.isConnected === "function") {
      if (window.AndroidUsbBridge.isConnected()) {
        transportMode = "android_native";
        setUsbConnectedUi(true, t("usbConnectedNative"));
        sendRawUsbCommand("STATUS");
      }
      return;
    }

    setInterval(async () => {
      if (transportMode === "webserial" || transportMode === "android_native") return;
      try {
        const res = await fetch("/api/hardware/status");
        if (!res.ok) return;
        const st = await res.json();
        if (st && st.serial_connected) {
          transportMode = "server";
          setUsbConnectedUi(
            true,
            t("usbBridgePrefix") + " (" + (st.serial_port || "USB") + ") · " + t("neighborsLabel") + ": " + ((st.neighbors || []).length)
          );
          if (Array.isArray(st.neighbors)) updateNeighborsUi(st.neighbors);
        }
        const mRes = await fetch("/api/messages?group_id=mesh-default");
        if (mRes.ok) {
          const msgs = await mRes.json();
          const myCallsign = (document.getElementById("callsignInput").value || t("defaultCallsign")).trim();
          (Array.isArray(msgs) ? msgs : []).forEach(m => {
            if (m.sender === myCallsign) return;
            appendMessageBubble({
              id: m.message_id,
              sender: m.sender,
              body: m.body || m.text || "",
              mine: false,
              meta: t("rxLocalMeta") + (m.delivery_status || m.status || t("delivered"))
            });
          });
        }
      } catch (e) {}
    }, 1500);
  });
</script>
</body>
</html>
"""
