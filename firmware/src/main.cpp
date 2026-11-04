#include "stealth_mesh.h"
#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include <esp_wifi.h>
#include <esp_system.h>
#include <mbedtls/sha256.h>

static RadioDriver          g_radio;
static PacketHandler        g_packets;
static EmbeddedMessageQueue g_tx_queue;
static PowerManager         g_power;
static WebServer            g_server(80);
static Preferences          g_prefs;

static bool     g_radio_ok        = false;
static bool     g_ap_ok           = false;
static bool     g_tx_enabled      = true;
static uint32_t g_boot_epoch      = 1;
static uint32_t g_msg_counter     = 0;
static uint32_t g_tx_count        = 0;
static uint32_t g_rx_count        = 0;
static int16_t  g_last_rssi       = 0;
static float    g_last_snr        = 0.0f;
static uint32_t g_last_heartbeat  = 0;
static uint32_t g_last_client_ms  = 0;
static char     g_node_id[16]     = "N1";
static uint8_t  g_mesh_key[32]    = {};
static String   g_chat_history    = "[]";

static constexpr uint32_t WIFI_STEALTH_IDLE_MS = 600000UL; // Auto-disable 2.4 GHz AP after 10 min idle

static String escapeJsonString(const char* raw) {
    if (raw == nullptr) return String("");
    String out;
    out.reserve(strlen(raw) + 8);
    for (size_t i = 0; raw[i] != '\0' && i < SMSH_MAX_PAYLOAD; ++i) {
        unsigned char c = (unsigned char)raw[i];
        if (c < 0x20 || c == 0x7F) {
            out += ' ';
        } else if (c == '\\') {
            out += "\\\\";
        } else if (c == '"') {
            out += "\\\"";
        } else if (c == '<') {
            out += "\\u003c";
        } else if (c == '>') {
            out += "\\u003e";
        } else {
            out += (char)c;
        }
    }
    return out;
}

static void appendChatHistory(const char* sender, const char* text, bool mine) {
    String cleanSender = escapeJsonString(sender);
    String cleanBody = escapeJsonString(text);
    String entry = String("{\"sender\":\"") + cleanSender + "\",\"body\":\"" + cleanBody +
                   "\",\"mine\":" + (mine ? "true" : "false") + "}";
    if (g_chat_history == "[]") {
        g_chat_history = "[" + entry + "]";
    } else {
        if (g_chat_history.length() > 1800) {
            g_chat_history = "[" + entry + "]";
        } else {
            g_chat_history.remove(g_chat_history.length() - 1);
            g_chat_history += "," + entry + "]";
        }
    }
}

// Clean Messenger UI at "/" (Ukrainian & English, no admin/routing clutter)
static const char MESSENGER_HTML[] PROGMEM = R"rawliteral(
<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>Stealth Mesh</title>
<style>
*{box-sizing:border-box}html,body{height:100%;margin:0;background:#0b141a;color:#e9edef;font:15px -apple-system,system-ui,sans-serif;overflow:hidden}
.wrap{display:flex;flex-direction:column;height:100dvh;max-width:680px;margin:0 auto;background:#111b21}
header{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#202c33;border-bottom:1px solid #222e35}
.title{font-weight:700;font-size:1.05rem}.sub{font-size:.76rem;color:#00a884}
.lang-btn{background:#2a3942;border:0;color:#e9edef;padding:7px 11px;border-radius:8px;font-weight:600;cursor:pointer}
#msgs{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px;background:#0b141a}
.b{max-width:78%;padding:9px 13px;border-radius:14px;word-wrap:break-word;line-height:1.35}
.mine{align-self:flex-end;background:#005c4b;border-bottom-right-radius:4px}
.theirs{align-self:flex-start;background:#202c33;border-bottom-left-radius:4px}
.s{font-size:.75rem;font-weight:700;color:#38bdf8;margin-bottom:2px}
form{display:flex;gap:8px;padding:10px 14px;background:#202c33;border-top:1px solid #222e35}
input{flex:1;background:#2a3942;border:0;color:#fff;padding:12px 16px;border-radius:24px;font:inherit;outline:none}
button.send{width:44px;height:44px;border-radius:50%;background:#00a884;border:0;color:#fff;font-size:1.05rem;cursor:pointer}
</style></head><body>
<div class="wrap">
  <header>
    <div>
      <div class="title">Stealth Mesh</div>
      <div class="sub" id="sub">🔒 Захищений чат</div>
    </div>
    <button class="lang-btn" id="lbtn" onclick="toggleLang()">EN</button>
  </header>
  <div id="msgs"></div>
  <form onsubmit="sendMsg(event)">
    <input id="msg" placeholder="Написати повідомлення..." required>
    <button class="send" type="submit">➤</button>
  </form>
</div>
<script>
let lang=localStorage.getItem('sm_lang')||'uk';
function applyLang(){
  document.getElementById('sub').textContent=lang==='uk'?'🔒 Захищений чат':'🔒 Encrypted chat';
  document.getElementById('msg').placeholder=lang==='uk'?'Написати повідомлення...':'Write a message...';
  document.getElementById('lbtn').textContent=lang==='uk'?'EN':'УКР';
}
function toggleLang(){lang=lang==='uk'?'en':'uk';localStorage.setItem('sm_lang',lang);applyLang();}
async function poll(){
  try{
    const r=await fetch('/api/messages');const list=await r.json();
    const box=document.getElementById('msgs');box.innerHTML='';
    for(const m of list){
      const d=document.createElement('div');
      d.className='b '+(m.mine?'mine':'theirs');
      if(!m.mine){const s=document.createElement('div');s.className='s';s.textContent=m.sender;d.appendChild(s);}
      const t=document.createElement('div');t.textContent=m.body;d.appendChild(t);
      box.appendChild(d);
    }
    box.scrollTop=box.scrollHeight;
  }catch(e){}
}
async function sendMsg(e){
  e.preventDefault();
  const inp=document.getElementById('msg');const body=inp.value.trim();if(!body)return;
  inp.value='';
  await fetch('/api/send?dst=BROADCAST&msg='+encodeURIComponent(body),{method:'POST'});
  poll();
}
applyLang();setInterval(poll,2000);poll();
</script></body></html>
)rawliteral";

// Separate Admin Diagnostics UI at "/admin" (Ukrainian & English)
static const char ADMIN_HTML[] PROGMEM = R"rawliteral(
<!doctype html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stealth Mesh Admin</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#0d151c;color:#e9f0f4;font:15px system-ui,sans-serif;padding:18px;max-width:640px;margin:0 auto}
.card{background:#16232e;border:1px solid #2b3f4e;border-radius:14px;padding:16px;margin:12px 0}
.ok{color:#4df0b8;font-weight:700}.err{color:#ff6b6b;font-weight:700}
button,a{background:#203444;color:#7de2c3;border:1px solid #2e4b60;padding:8px 12px;border-radius:8px;text-decoration:none;cursor:pointer;font:600 .85rem inherit}
</style></head><body>
<div style="display:flex;justify-content:space-between;align-items:center">
  <h2 id="title" style="margin:0;color:#7de2c3">Адмін-модуль вузла</h2>
  <div style="display:flex;gap:8px">
    <a href="/" id="chat-link">← Месенджер</a>
    <button id="lbtn" onclick="toggleLang()">EN</button>
  </div>
</div>
<div class="card" id="status">...</div>
<script>
let lang=localStorage.getItem('sm_lang')||'uk';
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function toggleLang(){lang=lang==='uk'?'en':'uk';localStorage.setItem('sm_lang',lang);poll();}
async function poll(){
  document.getElementById('title').textContent=lang==='uk'?'Адмін-модуль вузла':'Node Admin Console';
  document.getElementById('chat-link').textContent=lang==='uk'?'← Месенджер':'← Messenger';
  document.getElementById('lbtn').textContent=lang==='uk'?'EN':'УКР';
    try{
    const r=await fetch('/api/status');const s=await r.json();
    document.getElementById('status').innerHTML=lang==='uk'
      ?`<div><b>ID вузла:</b> ${esc(s.node_id)}</div>`+
       `<div style="margin-top:6px"><b>Радіомодуль SX1276:</b> <span class="${s.radio_ok?'ok':'err'}">${s.radio_ok?'Активний ('+esc(s.chip_version)+')':'Помилка SPI ('+esc(s.chip_version)+')'}</span></div>`+
       `<div style="margin-top:6px"><b>Апаратний FHSS (RegHopPeriod=${esc(s.hop_period)}):</b> <span class="ok">УВІМКНЕНО</span> · <b>Пін DIO2 (GPIO1):</b> <span class="${s.dio2_ok?'ok':'err'}">${s.dio2_ok?'ПІДТВЕРДЖЕНО':'ОЧІКУЄ TX'}</span></div>`+
       `<div style="margin-top:6px"><b>Стрибків частоти за останній пакет:</b> <b>${esc(s.last_pkt_hops)}</b> (Всього: <b>${esc(s.total_hops)}</b>)</div>`+
       `<div style="margin-top:6px"><b>Траса частот пакета (МГц):</b> <code style="color:#7de2c3">${esc(s.hop_trace)} MHz</code></div>`+
       `<div style="margin-top:6px"><b>Шифрування ефіру:</b> <span class="ok">AES-256-GCM + AAD</span></div>`+
       `<div style="margin-top:6px"><b>Передано пакетів (TX):</b> ${esc(s.tx_count)} · <b>Прийнято (RX):</b> ${esc(s.rx_count)}</div>`+
       `<div style="margin-top:6px"><b>Останній RSSI / SNR:</b> ${esc(s.last_rssi)} dBm / ${esc(s.last_snr)} dB</div>`
      :`<div><b>Node ID:</b> ${esc(s.node_id)}</div>`+
       `<div style="margin-top:6px"><b>SX1276 Radio:</b> <span class="${s.radio_ok?'ok':'err'}">${s.radio_ok?'Active ('+esc(s.chip_version)+')':'SPI Error ('+esc(s.chip_version)+')'}</span></div>`+
       `<div style="margin-top:6px"><b>Hardware FHSS (RegHopPeriod=${esc(s.hop_period)}):</b> <span class="ok">ENABLED</span> · <b>DIO2 Pin (GPIO1):</b> <span class="${s.dio2_ok?'ok':'err'}">${s.dio2_ok?'VERIFIED':'WAITING TX'}</span></div>`+
       `<div style="margin-top:6px"><b>Frequency Hops (Last Packet):</b> <b>${esc(s.last_pkt_hops)}</b> (Total: <b>${esc(s.total_hops)}</b>)</div>`+
       `<div style="margin-top:6px"><b>Packet Hop Trace (MHz):</b> <code style="color:#7de2c3">${esc(s.hop_trace)} MHz</code></div>`+
       `<div style="margin-top:6px"><b>Over-the-Air Crypto:</b> <span class="ok">AES-256-GCM + AAD</span></div>`+
       `<div style="margin-top:6px"><b>Packets Sent (TX):</b> ${esc(s.tx_count)} · <b>Received (RX):</b> ${esc(s.rx_count)}</div>`+
       `<div style="margin-top:6px"><b>Last RSSI / SNR:</b> ${esc(s.last_rssi)} dBm / ${esc(s.last_snr)} dB</div>`;
  }catch(e){}
}
setInterval(poll,2000);poll();
</script></body></html>
)rawliteral";

static void startWiFiAccessPoint(const char* pass) {
    String ap_ssid = String("StealthMesh-") + String(g_node_id);
    WiFi.persistent(false);
    WiFi.disconnect(true);
    WiFi.mode(WIFI_AP);
    esp_wifi_set_protocol(WIFI_IF_AP, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N);
    esp_wifi_set_bandwidth(WIFI_IF_AP, WIFI_BW_HT20);
    WiFi.softAPConfig(
        IPAddress(192, 168, 4, 1),
        IPAddress(192, 168, 4, 1),
        IPAddress(255, 255, 255, 0)
    );
    g_ap_ok = WiFi.softAP(ap_ssid.c_str(), pass, 6, 0, 4);
    WiFi.setTxPower(WIFI_POWER_8_5dBm);
    g_last_client_ms = millis();
}

void setup() {
    Serial.begin(115200);
    g_power.begin();
    pinMode(StealthPins::BOOT_BTN, INPUT_PULLUP);

    uint64_t mac = ESP.getEfuseMac();
    snprintf(g_node_id, sizeof(g_node_id), "N-%04X", (uint16_t)(mac & 0xFFFF));

    // Load or initialize NVS provisioning parameters (boot epoch, mesh AES-256 key, AP passphrase)
    g_prefs.begin("stealthmesh", false);
    g_boot_epoch = g_prefs.getUInt("epoch", 0) + 1;
    g_prefs.putUInt("epoch", g_boot_epoch);

    if (g_prefs.getBytesLength("mkey") == 32) {
        g_prefs.getBytes("mkey", g_mesh_key, 32);
    } else {
        // Derive default group channel key via SHA-256 domain separation so NVS can rotate/override it
        const char* domain = "StealthMesh-v1-ChannelKey-868MHz";
        mbedtls_sha256((const unsigned char*)domain, strlen(domain), g_mesh_key, 0);
        g_prefs.putBytes("mkey", g_mesh_key, 32);
    }
    String ap_pass = g_prefs.getString("ap_pass", "stealthmesh868");
    g_prefs.end();

    g_radio.setFhssSeed(g_mesh_key[0] & 0x07U);
    g_radio_ok = g_radio.begin(true, 5);
    if (g_radio_ok) {
        g_radio.startReceive();
        digitalWrite(StealthPins::LED_PIN, LOW);
    }

    startWiFiAccessPoint(ap_pass.c_str());

    g_server.on("/", HTTP_GET, []() {
        g_server.send_P(200, "text/html; charset=utf-8", MESSENGER_HTML);
    });

    g_server.on("/admin", HTTP_GET, []() {
        g_server.send_P(200, "text/html; charset=utf-8", ADMIN_HTML);
    });

    g_server.on("/api/status", HTTP_GET, []() {
        char buf[512];
        uint8_t ver = g_radio.readChipVersion();
        snprintf(
            buf, sizeof(buf),
            "{\"node_id\":\"%s\",\"radio_ok\":%s,\"chip_version\":\"0x%02X\",\"tx_enabled\":%s,\"tx_count\":%lu,\"rx_count\":%lu,\"last_rssi\":%d,\"last_snr\":%.2f,\"hop_period\":%u,\"dio2_ok\":%s,\"last_pkt_hops\":%u,\"total_hops\":%lu,\"hop_trace\":\"%s\"}",
            g_node_id,
            (ver == 0x12) ? "true" : "false",
            ver,
            g_tx_enabled ? "true" : "false",
            (unsigned long)g_tx_count,
            (unsigned long)g_rx_count,
            (int)g_last_rssi,
            g_last_snr,
            (unsigned)g_radio.readHopPeriod(),
            g_radio.dio2PinVerified() ? "true" : "false",
            (unsigned)g_radio.lastPacketHops(),
            (unsigned long)g_radio.totalFhssHops(),
            g_radio.lastHopTrace()
        );
        g_server.send(200, "application/json", buf);
    });

    g_server.on("/api/messages", HTTP_GET, []() {
        g_server.send(200, "application/json; charset=utf-8", g_chat_history);
    });

    g_server.on("/api/send", HTTP_POST, []() {
        if (!g_server.hasArg("msg")) {
            g_server.send(400, "application/json", "{\"error\":\"missing msg\"}");
            return;
        }
        String msg = g_server.arg("msg");
        String dst = g_server.hasArg("dst") ? g_server.arg("dst") : "BROADCAST";
        if (!PacketHandler::isValidSafeId(dst.c_str(), SMSH_MAX_ID_LEN)) {
            g_server.send(400, "application/json", "{\"error\":\"invalid dst\"}");
            return;
        }

        MeshFrame frame = {};
        frame.version = SMSH_VERSION;
        frame.hop_limit = 6;
        ++g_msg_counter;
        uint16_t rnd16 = (uint16_t)(esp_random() & 0xFFFFU);
        snprintf(frame.packet_id, SMSH_MAX_ID_LEN, "%s-e%lu-%04X-p%lu", g_node_id, (unsigned long)g_boot_epoch, rnd16, (unsigned long)g_msg_counter);
        snprintf(frame.message_id, SMSH_MAX_ID_LEN, "%s-e%lu-%04X-m%lu", g_node_id, (unsigned long)g_boot_epoch, rnd16, (unsigned long)g_msg_counter);
        strncpy(frame.source, g_node_id, SMSH_MAX_ID_LEN);
        strncpy(frame.destination, dst.c_str(), SMSH_MAX_ID_LEN);

        size_t len = msg.length();
        // Reserve 28 bytes for 12-byte GCM IV + 16-byte GCM authentication tag and align on UTF-8 boundary
        size_t max_plain = SMSH_MAX_PAYLOAD - 28;
        if (len > max_plain) {
            len = max_plain;
            while (len > 0 && (((uint8_t)msg[len]) & 0xC0) == 0x80) {
                --len;
            }
        }
        if (len == 0) {
            g_server.send(400, "application/json", "{\"error\":\"empty msg\"}");
            return;
        }
        char plain_buf[SMSH_MAX_PAYLOAD + 1] = {};
        memcpy(plain_buf, msg.c_str(), len);
        memcpy(frame.payload, plain_buf, len);
        frame.payload_len = (uint16_t)len;

        uint8_t iv[12];
        esp_fill_random(iv, sizeof(iv));
        if (!PacketHandler::sealFramePayload(frame, g_mesh_key, iv)) {
            g_server.send(500, "application/json", "{\"error\":\"encryption failed\"}");
            return;
        }

        g_packets.isDuplicateAndRemember(frame.message_id);
        g_tx_queue.enqueue(frame);
        appendChatHistory(g_node_id, plain_buf, true);
        g_server.send(200, "application/json", "{\"queued\":true}");
    });

    g_server.on("/api/provision", HTTP_POST, []() {
        bool updated = false;
        g_prefs.begin("stealthmesh", false);
        if (g_server.hasArg("mesh_secret")) {
            String secret = g_server.arg("mesh_secret");
            if (secret.length() >= 8 && secret.length() <= 128) {
                mbedtls_sha256((const unsigned char*)secret.c_str(), secret.length(), g_mesh_key, 0);
                g_prefs.putBytes("mkey", g_mesh_key, 32);
                g_radio.setFhssSeed(g_mesh_key[0] & 0x07U);
                updated = true;
            }
        }
        if (g_server.hasArg("ap_pass")) {
            String new_pass = g_server.arg("ap_pass");
            if (new_pass.length() >= 8 && new_pass.length() <= 63) {
                g_prefs.putString("ap_pass", new_pass);
                updated = true;
            }
        }
        g_prefs.end();
        if (!updated) {
            g_server.send(400, "application/json", "{\"error\":\"provide valid mesh_secret or ap_pass (8..63 chars)\"}");
            return;
        }
        g_server.send(200, "application/json", "{\"provisioned\":true}");
    });

    g_server.begin();
}

void loop() {
    g_server.handleClient();

    // EMCON / 2.4 GHz Wi-Fi AP stealth auto-shutoff & BOOT button (GPIO9) toggle
    if (g_ap_ok && WiFi.softAPgetStationNum() > 0) {
        g_last_client_ms = millis();
    } else if (g_ap_ok && (millis() - g_last_client_ms >= WIFI_STEALTH_IDLE_MS)) {
        WiFi.softAPdisconnect(true);
        WiFi.mode(WIFI_OFF);
        g_ap_ok = false;
    }
    if (digitalRead(StealthPins::BOOT_BTN) == LOW) {
        delay(40);
        if (digitalRead(StealthPins::BOOT_BTN) == LOW) {
            if (!g_ap_ok) {
                g_prefs.begin("stealthmesh", true);
                String pass = g_prefs.getString("ap_pass", "stealthmesh868");
                g_prefs.end();
                startWiFiAccessPoint(pass.c_str());
            } else {
                WiFi.softAPdisconnect(true);
                WiFi.mode(WIFI_OFF);
                g_ap_ok = false;
            }
            while (digitalRead(StealthPins::BOOT_BTN) == LOW) {
                delay(10);
            }
        }
    }

    if (millis() - g_last_heartbeat >= 3000) {
        g_last_heartbeat = millis();
        uint8_t ver = g_radio.readChipVersion();
        g_radio_ok = (ver == 0x12);
        if (g_radio_ok) {
            Serial.printf(
                "[StealthMesh] Node: %s | SX1276: OK (0x%02X) | Wi-Fi AP(%s): StealthMesh-%s (%s, Clients:%d) | TX:%lu RX:%lu\n",
                g_node_id,
                ver,
                g_ap_ok ? "ON" : "ERR",
                g_node_id,
                WiFi.softAPIP().toString().c_str(),
                WiFi.softAPgetStationNum(),
                (unsigned long)g_tx_count,
                (unsigned long)g_rx_count
            );
        } else {
            Serial.printf(
                "[StealthMesh] WARNING: SX1276 SPI check failed (read 0x%02X, expected 0x12).\n",
                ver
            );
        }
    }

    if (!g_radio_ok) {
        return;
    }

    uint8_t raw_buf[SMSH_MAX_FRAME_SIZE];
    size_t raw_len = 0;
    int16_t rssi = 0;
    float snr = 0.0f;

    if (g_radio.pollReceivedFrame(raw_buf, sizeof(raw_buf), raw_len, rssi, snr)) {
        MeshFrame rx_frame;
        if (PacketHandler::decodeFrame(raw_buf, raw_len, rx_frame)) {
            // Ignore self-originated frames echoed back by neighboring relays
            if (strcmp(rx_frame.source, g_node_id) != 0) {
                MeshFrame decrypted_frame = rx_frame;
                // Authenticate and decrypt AES-256-GCM payload BEFORE updating deduplication cache or relaying
                if (PacketHandler::openFramePayload(decrypted_frame, g_mesh_key)) {
                    if (!g_packets.isDuplicateAndRemember(rx_frame.message_id)) {
                        ++g_rx_count;
                        g_last_rssi = rssi;
                        g_last_snr = snr;
                        char text_buf[SMSH_MAX_PAYLOAD + 1] = {};
                        memcpy(text_buf, decrypted_frame.payload, decrypted_frame.payload_len);
                        appendChatHistory(decrypted_frame.source, text_buf, false);

                        String safeMsg = escapeJsonString(text_buf);
                        Serial.printf(
                            "{\"event\":\"rx\",\"src\":\"%s\",\"dst\":\"%s\",\"id\":\"%s\",\"rssi\":%d,\"snr\":%.2f,\"msg\":\"%s\"}\n",
                            decrypted_frame.source, decrypted_frame.destination, decrypted_frame.message_id, (int)rssi, snr, safeMsg.c_str()
                        );
                        if (strcmp(rx_frame.destination, g_node_id) != 0 && rx_frame.hop_limit > 1) {
                            rx_frame.hop_limit -= 1;
                            delay(random(15, 55)); // Randomized relay jitter to prevent LoRa air collisions
                            g_tx_queue.enqueue(rx_frame);
                        }
                    }
                }
            }
        }
    }

    if (g_tx_enabled && g_tx_queue.size() > 0) {
        MeshFrame tx_frame;
        if (g_tx_queue.dequeue(tx_frame)) {
            uint8_t wire[SMSH_MAX_FRAME_SIZE];
            size_t wire_len = 0;
            if (PacketHandler::encodeFrame(tx_frame, wire, sizeof(wire), wire_len)) {
                digitalWrite(StealthPins::LED_PIN, HIGH);
                if (g_radio.transmitFrame(wire, wire_len, g_tx_enabled)) {
                    ++g_tx_count;
                    Serial.printf(
                        "{\"event\":\"tx_ok\",\"id\":\"%s\",\"bytes\":%u,\"fhss_hops\":%u,\"dio2_pin\":%s,\"trace\":\"%s MHz\"}\n",
                        tx_frame.message_id,
                        (unsigned)wire_len,
                        (unsigned)g_radio.lastPacketHops(),
                        g_radio.dio2PinVerified() ? "true" : "false",
                        g_radio.lastHopTrace()
                    );
                }
                digitalWrite(StealthPins::LED_PIN, LOW);
            }
        }
    }
}
