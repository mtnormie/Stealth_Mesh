#include "stealth_mesh.h"
#include <Arduino.h>
#include <WiFi.h>
#include <Preferences.h>
#include <esp_wifi.h>
#include <esp_system.h>
#include <mbedtls/sha256.h>
#include <mbedtls/pkcs5.h>
#include <mbedtls/platform_util.h>

static RadioDriver          g_radio;
static PacketHandler        g_packets;
static EmbeddedMessageQueue g_tx_queue;
static PowerManager         g_power;
static Preferences          g_prefs;

static bool     g_radio_ok        = false;
static bool     g_tx_enabled      = true;
static uint32_t g_boot_epoch      = 1;
static uint32_t g_msg_counter     = 0;
static uint32_t g_tx_count        = 0;
static uint32_t g_rx_count        = 0;
static uint32_t g_relay_count     = 0;
static int16_t  g_last_rssi       = 0;
static float    g_last_snr        = 0.0f;
static uint32_t g_last_heartbeat  = 0;
static char     g_node_id[16]     = "N-0000"; // Ephemeral rotating callsign (never leaks hardware MAC)
static char     g_callsign[32]    = "Боєць-1"; // Fighter callsign stored in NVS flash for zero-command sending
static uint8_t  g_mesh_key[32]    = {}; // RAM-only stateless session key (never persisted to Flash)
static bool     g_key_provisioned = false;
static uint32_t g_boot_btn_pressed_at = 0;

static void wipeSessionKeys(const char* reason) {
    mbedtls_platform_zeroize(g_mesh_key, sizeof(g_mesh_key));
    g_key_provisioned = false;
    g_radio.setFhssSeed(0);
    g_prefs.begin("stealthmesh", false);
    g_prefs.remove("mkey");
    g_prefs.end();
    Serial.printf("{\"event\":\"wiped\",\"reason\":\"%s\",\"stateless_ram_only\":true}\n",
                  reason ? reason : "manual");
}

static constexpr uint32_t NEIGHBOR_EXPIRE_MS = 180000UL; // Keep passive neighbor records for 3 min

// Live Passive Neighbor Table (populated strictly from received traffic — zero background transmissions!)
static NeighborEntry g_neighbors[SMSH_MAX_NEIGHBORS] = {};
static char          g_serial_line[384]             = {};
static size_t        g_serial_pos                   = 0;

static String escapeJsonString(const char* raw, size_t max_chars = 160) {
    if (raw == nullptr) return String("");
    String out;
    out.reserve(strlen(raw) + 8);
    for (size_t i = 0; raw[i] != '\0' && i < max_chars; ++i) {
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

static void rotateEphemeralNodeId() {
    // Generate a random ephemeral tactical ID so enemy SIGINT cannot correlate a static hardware MAC
    uint16_t ephem = (uint16_t)(esp_random() & 0xFFFFU);
    snprintf(g_node_id, sizeof(g_node_id), "N-%04X", ephem);
}

static void recordNeighbor(const char* node_id, int16_t rssi, float snr, uint8_t hops) {
    if (node_id == nullptr || node_id[0] == '\0' || strcmp(node_id, g_node_id) == 0) {
        return;
    }
    uint32_t now = millis();
    int free_slot = -1;
    int oldest_slot = 0;
    uint32_t oldest_ms = now;

    for (size_t i = 0; i < SMSH_MAX_NEIGHBORS; ++i) {
        if (g_neighbors[i].active && strncmp(g_neighbors[i].node_id, node_id, SMSH_MAX_ID_LEN) == 0) {
            g_neighbors[i].last_rssi_dbm = rssi;
            g_neighbors[i].last_snr_db = snr;
            g_neighbors[i].hops = hops;
            g_neighbors[i].rx_packets += 1;
            g_neighbors[i].last_seen_ms = now;
            return;
        }
        if (!g_neighbors[i].active && free_slot < 0) {
            free_slot = (int)i;
        }
        if (g_neighbors[i].active && g_neighbors[i].last_seen_ms <= oldest_ms) {
            oldest_ms = g_neighbors[i].last_seen_ms;
            oldest_slot = (int)i;
        }
    }

    int slot = (free_slot >= 0) ? free_slot : oldest_slot;
    g_neighbors[slot].active = true;
    strncpy(g_neighbors[slot].node_id, node_id, SMSH_MAX_ID_LEN);
    g_neighbors[slot].node_id[SMSH_MAX_ID_LEN] = '\0';
    g_neighbors[slot].last_rssi_dbm = rssi;
    g_neighbors[slot].last_snr_db = snr;
    g_neighbors[slot].hops = hops;
    g_neighbors[slot].rx_packets = 1;
    g_neighbors[slot].last_seen_ms = now;
}

static size_t countActiveNeighbors() {
    uint32_t now = millis();
    size_t count = 0;
    for (size_t i = 0; i < SMSH_MAX_NEIGHBORS; ++i) {
        if (g_neighbors[i].active && (now - g_neighbors[i].last_seen_ms <= NEIGHBOR_EXPIRE_MS)) {
            ++count;
        }
    }
    return count;
}

static String buildNeighborsJson() {
    uint32_t now = millis();
    String out = "[";
    bool first = true;
    for (size_t i = 0; i < SMSH_MAX_NEIGHBORS; ++i) {
        if (!g_neighbors[i].active) continue;
        uint32_t age_ms = now - g_neighbors[i].last_seen_ms;
        if (age_ms > NEIGHBOR_EXPIRE_MS) continue;
        if (!first) out += ",";
        first = false;
        char item[192];
        snprintf(
            item, sizeof(item),
            "{\"node_id\":\"%s\",\"rssi\":%d,\"snr\":%.2f,\"hops\":%u,\"rx_packets\":%lu,\"age_sec\":%lu}",
            g_neighbors[i].node_id,
            (int)g_neighbors[i].last_rssi_dbm,
            g_neighbors[i].last_snr_db,
            (unsigned)g_neighbors[i].hops,
            (unsigned long)g_neighbors[i].rx_packets,
            (unsigned long)(age_ms / 1000UL)
        );
        out += item;
    }
    out += "]";
    return out;
}

// Pack group_id + sender + body into encrypted wire payload ("G|<group_id>|<sender>|<body>")
static size_t packEnvelope(
    const char* group_id,
    const char* sender,
    const char* body,
    char* out_buf,
    size_t max_len
) {
    const char* gid = (group_id && group_id[0]) ? group_id : "mesh-default";
    const char* snd = (sender && sender[0]) ? sender : g_node_id;
    int written = snprintf(out_buf, max_len, "G|%s|%s|%s", gid, snd, body ? body : "");
    if (written < 0) return 0;
    size_t len = (size_t)written;
    if (len >= max_len) {
        len = max_len - 1;
        while (len > 0 && (((uint8_t)out_buf[len]) & 0xC0) == 0x80) {
            --len;
        }
        out_buf[len] = '\0';
    }
    return len;
}

// Unpack decrypted wire payload ("G|<group_id>|<sender>|<body>" or plain text fallback)
static void unpackEnvelope(
    const char* raw_text,
    char* out_group,
    size_t group_cap,
    char* out_sender,
    size_t sender_cap,
    char* out_body,
    size_t body_cap,
    const char* fallback_sender
) {
    strncpy(out_group, "mesh-default", group_cap - 1);
    out_group[group_cap - 1] = '\0';
    strncpy(out_sender, fallback_sender ? fallback_sender : "Node", sender_cap - 1);
    out_sender[sender_cap - 1] = '\0';
    out_body[0] = '\0';

    if (raw_text == nullptr) return;
    if (strncmp(raw_text, "G|", 2) == 0) {
        const char* p1 = raw_text + 2;
        const char* p2 = strchr(p1, '|');
        if (p2 != nullptr) {
            size_t glen = (size_t)(p2 - p1);
            if (glen > 0 && glen < group_cap) {
                memcpy(out_group, p1, glen);
                out_group[glen] = '\0';
            }
            const char* p3 = strchr(p2 + 1, '|');
            if (p3 != nullptr) {
                size_t slen = (size_t)(p3 - (p2 + 1));
                if (slen > 0 && slen < sender_cap) {
                    memcpy(out_sender, p2 + 1, slen);
                    out_sender[slen] = '\0';
                }
                strncpy(out_body, p3 + 1, body_cap - 1);
                out_body[body_cap - 1] = '\0';
                return;
            }
        }
    }
    strncpy(out_body, raw_text, body_cap - 1);
    out_body[body_cap - 1] = '\0';
}

static bool queueEncryptedLoRaMessage(
    const char* group_id,
    const char* sender,
    const char* dst_node,
    const char* body_text,
    uint8_t hop_limit = SMSH_DEFAULT_HOPS
) {
    const char* dst = (dst_node && dst_node[0]) ? dst_node : "BROADCAST";
    if (!PacketHandler::isValidSafeId(dst, SMSH_MAX_ID_LEN)) {
        return false;
    }

    char envelope[SMSH_MAX_PAYLOAD + 1] = {};
    size_t max_plain = SMSH_MAX_PAYLOAD - 28; // Reserve 12B IV + 16B GCM Tag
    size_t env_len = packEnvelope(group_id, sender, body_text, envelope, max_plain + 1);
    if (env_len == 0) {
        return false;
    }

    // Rotate ephemeral source ID on each outgoing transmission so SIGINT cannot track a fixed node ID
    rotateEphemeralNodeId();

    MeshFrame frame = {};
    frame.version = SMSH_VERSION;
    frame.hop_limit = hop_limit;
    ++g_msg_counter;
    uint16_t rnd16 = (uint16_t)(esp_random() & 0xFFFFU);
    snprintf(frame.packet_id, SMSH_MAX_ID_LEN, "P-%04X-%lu", rnd16, (unsigned long)g_msg_counter);
    snprintf(frame.message_id, SMSH_MAX_ID_LEN, "M-%04X-%lu", rnd16, (unsigned long)g_msg_counter);
    strncpy(frame.source, g_node_id, SMSH_MAX_ID_LEN);
    strncpy(frame.destination, dst, SMSH_MAX_ID_LEN);
    memcpy(frame.payload, envelope, env_len);
    frame.payload_len = (uint16_t)env_len;

    if (!g_key_provisioned) {
        return false;
    }

    uint8_t iv[12];
    esp_fill_random(iv, sizeof(iv));
    if (!PacketHandler::sealFramePayload(frame, g_mesh_key, iv)) {
        return false;
    }

    g_packets.isDuplicateAndRemember(frame.message_id);
    return g_tx_queue.enqueue(frame);
}

static void enqueueOneShotDiscoveryPing() {
    rotateEphemeralNodeId();
    MeshFrame frame = {};
    frame.version = SMSH_VERSION;
    frame.hop_limit = 3;
    ++g_msg_counter;
    uint16_t rnd16 = (uint16_t)(esp_random() & 0xFFFFU);
    snprintf(frame.packet_id, SMSH_MAX_ID_LEN, "B-%04X-%lu", rnd16, (unsigned long)g_msg_counter);
    snprintf(frame.message_id, SMSH_MAX_ID_LEN, "B-%04X-%lu", rnd16, (unsigned long)g_msg_counter);
    strncpy(frame.source, g_node_id, SMSH_MAX_ID_LEN);
    strncpy(frame.destination, "BEACON", SMSH_MAX_ID_LEN);

    char bpayload[64];
    int blen = snprintf(bpayload, sizeof(bpayload), "BCN|%s|%u", g_node_id, (unsigned)countActiveNeighbors());
    if (blen <= 0) return;
    memcpy(frame.payload, bpayload, (size_t)blen);
    frame.payload_len = (uint16_t)blen;

    if (!g_key_provisioned) {
        return;
    }

    uint8_t iv[12];
    esp_fill_random(iv, sizeof(iv));
    if (PacketHandler::sealFramePayload(frame, g_mesh_key, iv)) {
        g_packets.isDuplicateAndRemember(frame.message_id);
        g_tx_queue.enqueue(frame);
    }
}

static void emitStatusJson() {
    uint8_t ver = g_radio.readChipVersion();
    String safe_callsign = escapeJsonString(g_callsign, 30);
    Serial.printf(
        "{\"event\":\"status\",\"node_id\":\"%s\",\"callsign\":\"%s\",\"wifi\":\"HARD_DISABLED_0mW\",\"bt\":\"HARD_DISABLED_0mW\",\"key_provisioned\":%s,\"stateless_ram_only\":true,\"radio_ok\":%s,\"chip_version\":\"0x%02X\",\"tx_enabled\":%s,\"tx_count\":%lu,\"rx_count\":%lu,\"relay_count\":%lu,\"neighbors_online\":%u,\"last_rssi\":%d,\"last_snr\":%.2f,\"hop_period\":%u,\"dio2_ok\":%s,\"last_pkt_hops\":%u,\"total_hops\":%lu,\"hop_trace\":\"%s\",\"neighbors\":%s}\n",
        g_node_id,
        safe_callsign.c_str(),
        g_key_provisioned ? "true" : "false",
        (ver == 0x12) ? "true" : "false",
        ver,
        g_tx_enabled ? "true" : "false",
        (unsigned long)g_tx_count,
        (unsigned long)g_rx_count,
        (unsigned long)g_relay_count,
        (unsigned)countActiveNeighbors(),
        (int)g_last_rssi,
        g_last_snr,
        (unsigned)g_radio.readHopPeriod(),
        g_radio.dio2PinVerified() ? "true" : "false",
        (unsigned)g_radio.lastPacketHops(),
        (unsigned long)g_radio.totalFhssHops(),
        g_radio.lastHopTrace(),
        buildNeighborsJson().c_str()
    );
}

// Handle Wired USB Type-C Serial commands from Laptop / Android Phone (Zero Wi-Fi / Zero BT)
static void pollUsbSerialCommands() {
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == '\r') continue;
        if (c == '\n') {
            g_serial_line[g_serial_pos] = '\0';
            if (g_serial_pos > 0) {
                if (strncmp(g_serial_line, "SEND|", 5) == 0) {
                    // Format: SEND|<group_id>|<sender>|<dst>|<body>
                    char* p1 = g_serial_line + 5;
                    char* p2 = strchr(p1, '|');
                    if (p2) {
                        *p2 = '\0';
                        char* p3 = strchr(p2 + 1, '|');
                        if (p3) {
                            *p3 = '\0';
                            char* p4 = strchr(p3 + 1, '|');
                            if (p4) {
                                *p4 = '\0';
                                queueEncryptedLoRaMessage(p1, p2 + 1, p3 + 1, p4 + 1);
                            }
                        }
                    }
                } else if (strncmp(g_serial_line, "CALLSIGN|", 9) == 0) {
                    const char* cs = g_serial_line + 9;
                    size_t cslen = strlen(cs);
                    if (cslen >= 1 && cslen < sizeof(g_callsign)) {
                        strncpy(g_callsign, cs, sizeof(g_callsign) - 1);
                        g_callsign[sizeof(g_callsign) - 1] = '\0';
                        g_prefs.begin("stealthmesh", false);
                        g_prefs.putString("callsign", g_callsign);
                        g_prefs.end();
                        emitStatusJson();
                    }
                } else if (strcmp(g_serial_line, "BEACON") == 0 || strcmp(g_serial_line, "PING") == 0) {
                    enqueueOneShotDiscoveryPing();
                } else if (strcmp(g_serial_line, "STATUS") == 0 || strcmp(g_serial_line, "NEIGHBORS") == 0) {
                    emitStatusJson();
                } else if (strcmp(g_serial_line, "WIPE") == 0 || strcmp(g_serial_line, "DURESS_WIPE") == 0) {
                    wipeSessionKeys("usb_duress_wipe");
                } else if (strncmp(g_serial_line, "SECRET|", 7) == 0) {
                    const char* sec = g_serial_line + 7;
                    size_t slen = strlen(sec);
                    if (slen >= 8 && slen <= 128) {
                        // Stateless RAM-only key provisioning via PBKDF2-HMAC-SHA256 (10,000 rounds, domain salt)
                        static const unsigned char kSalt[] = "StealthMesh-v2-PBKDF2-868MHz";
                        if (mbedtls_pkcs5_pbkdf2_hmac_ext(
                                MBEDTLS_MD_SHA256,
                                (const unsigned char*)sec, slen,
                                kSalt, sizeof(kSalt) - 1,
                                10000,
                                sizeof(g_mesh_key),
                                g_mesh_key) == 0) {
                            g_key_provisioned = true;
                            g_radio.setFhssSeed(g_mesh_key[0] & 0x0FU);
                            Serial.printf("{\"event\":\"provisioned\",\"stateless_ram_only\":true,\"kdf\":\"pbkdf2_sha256\",\"fhss_seed\":%u}\n",
                                          (unsigned)(g_mesh_key[0] & 0x0FU));
                        }
                    }
                } else {
                    // Zero-command fallback: any plain text line from a phone is automatically encrypted & transmitted!
                    queueEncryptedLoRaMessage("mesh-default", g_callsign, "BROADCAST", g_serial_line);
                }
            }
            g_serial_pos = 0;
        } else if (g_serial_pos + 1 < sizeof(g_serial_line)) {
            g_serial_line[g_serial_pos++] = c;
        }
    }
}

void setup() {
    Serial.begin(115200);
    g_power.begin();
    pinMode(StealthPins::BOOT_BTN, INPUT_PULLUP);

    // HARD-KILL ALL 2.4 GHz RADIOS (Wi-Fi & Bluetooth permanently OFF — 0.00 mW emission!)
    WiFi.persistent(false);
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    esp_wifi_stop();
    esp_wifi_deinit();
    btStop();

    rotateEphemeralNodeId();

    // Load non-sensitive NVS metadata and scrub any legacy key entries (Stateless RAM-only node)
    g_prefs.begin("stealthmesh", false);
    g_boot_epoch = g_prefs.getUInt("epoch", 0) + 1;
    g_prefs.putUInt("epoch", g_boot_epoch);
    g_prefs.remove("mkey");
    String saved_cs = g_prefs.getString("callsign", "Боєць-1");
    strncpy(g_callsign, saved_cs.c_str(), sizeof(g_callsign) - 1);
    g_callsign[sizeof(g_callsign) - 1] = '\0';
    g_prefs.end();

    mbedtls_platform_zeroize(g_mesh_key, sizeof(g_mesh_key));
    g_key_provisioned = false;
    g_radio.setFhssSeed(0);
    g_radio_ok = g_radio.begin(true, 5);
    if (g_radio_ok) {
        // Enter 100% passive silent LoRa receive mode (0 mW RF output until user explicitly sends a packet)
        g_radio.startReceive();
        digitalWrite(StealthPins::LED_PIN, HIGH); // Keep onboard LED OFF (active LOW) for visual stealth
    }
}

void loop() {
    pollUsbSerialCommands();

    // Hardware Panic Wipe: holding BOOT (GPIO9) for 2+ seconds zeroes RAM session keys immediately
    if (digitalRead(StealthPins::BOOT_BTN) == LOW) {
        if (g_boot_btn_pressed_at == 0) {
            g_boot_btn_pressed_at = millis();
        } else if (millis() - g_boot_btn_pressed_at >= 2000UL && g_key_provisioned) {
            wipeSessionKeys("boot_button_panic");
        }
    } else {
        g_boot_btn_pressed_at = 0;
    }

    // Periodic status heartbeat strictly over wired USB Serial (ZERO RF emission)
    if (millis() - g_last_heartbeat >= 3000) {
        g_last_heartbeat = millis();
        uint8_t ver = g_radio.readChipVersion();
        g_radio_ok = (ver == 0x12);
        emitStatusJson();
    }

    if (!g_radio_ok) {
        return;
    }

    // Passive LoRa 868 MHz Receive & Multi-Hop Relay
    uint8_t raw_buf[SMSH_MAX_FRAME_SIZE];
    size_t raw_len = 0;
    int16_t rssi = 0;
    float snr = 0.0f;

    if (g_radio.pollReceivedFrame(raw_buf, sizeof(raw_buf), raw_len, rssi, snr)) {
        MeshFrame rx_frame;
        if (g_key_provisioned && PacketHandler::decodeFrame(raw_buf, raw_len, rx_frame)) {
            if (strcmp(rx_frame.source, g_node_id) != 0) {
                MeshFrame decrypted_frame = rx_frame;
                // Authenticate and decrypt AES-256-GCM payload BEFORE updating deduplication cache or relaying
                if (PacketHandler::openFramePayload(decrypted_frame, g_mesh_key)) {
                    if (!g_packets.isDuplicateAndRemember(rx_frame.message_id)) {
                        ++g_rx_count;
                        g_last_rssi = rssi;
                        g_last_snr = snr;

                        bool is_beacon = (strcmp(rx_frame.destination, "BEACON") == 0);
                        uint8_t initial_hops = is_beacon ? 3 : SMSH_DEFAULT_HOPS;
                        uint8_t hops_taken = (rx_frame.hop_limit <= initial_hops)
                            ? (uint8_t)(initial_hops - rx_frame.hop_limit + 1)
                            : 1;

                        recordNeighbor(decrypted_frame.source, rssi, snr, hops_taken);

                        if (is_beacon) {
                            Serial.printf(
                                "{\"event\":\"beacon\",\"src\":\"%s\",\"hops\":%u,\"rssi\":%d,\"snr\":%.2f}\n",
                                decrypted_frame.source,
                                (unsigned)hops_taken,
                                (int)rssi,
                                snr
                            );
                        } else {
                            char text_buf[SMSH_MAX_PAYLOAD + 1] = {};
                            memcpy(text_buf, decrypted_frame.payload, decrypted_frame.payload_len);

                            char msg_group[24] = {};
                            char msg_sender[32] = {};
                            char msg_body[132] = {};
                            unpackEnvelope(
                                text_buf,
                                msg_group, sizeof(msg_group),
                                msg_sender, sizeof(msg_sender),
                                msg_body, sizeof(msg_body),
                                decrypted_frame.source
                            );

                            String safeGroup = escapeJsonString(msg_group, 24);
                            String safeSender = escapeJsonString(msg_sender, 32);
                            String safeMsg = escapeJsonString(msg_body, 132);
                            Serial.printf(
                                "{\"event\":\"rx\",\"src\":\"%s\",\"dst\":\"%s\",\"group\":\"%s\",\"sender\":\"%s\",\"id\":\"%s\",\"hops\":%u,\"rssi\":%d,\"snr\":%.2f,\"msg\":\"%s\"}\n",
                                decrypted_frame.source,
                                decrypted_frame.destination,
                                safeGroup.c_str(),
                                safeSender.c_str(),
                                decrypted_frame.message_id,
                                (unsigned)hops_taken,
                                (int)rssi,
                                snr,
                                safeMsg.c_str()
                            );
                        }

                        // Multi-Hop Relay: forward any broadcast or packet addressed to another node
                        if (strcmp(rx_frame.destination, g_node_id) != 0 && rx_frame.hop_limit > 1) {
                            rx_frame.hop_limit -= 1;
                            delay(random(15, 55)); // Randomized relay jitter to prevent LoRa air collisions
                            if (g_tx_queue.enqueue(rx_frame)) {
                                ++g_relay_count;
                            }
                        }
                    }
                }
            }
        }
    }

    // Transmit queued frame in an ultra-short 16-channel FHSS burst, then immediately return to passive RX
    if (g_tx_enabled && g_tx_queue.size() > 0) {
        MeshFrame tx_frame;
        if (g_tx_queue.dequeue(tx_frame)) {
            uint8_t wire[SMSH_MAX_FRAME_SIZE];
            size_t wire_len = 0;
            if (PacketHandler::encodeFrame(tx_frame, wire, sizeof(wire), wire_len)) {
                if (g_radio.transmitFrame(wire, wire_len, g_tx_enabled)) {
                    ++g_tx_count;
                    Serial.printf(
                        "{\"event\":\"tx_ok\",\"id\":\"%s\",\"dst\":\"%s\",\"bytes\":%u,\"fhss_hops\":%u,\"dio2_pin\":%s,\"trace\":\"%s MHz\"}\n",
                        tx_frame.message_id,
                        tx_frame.destination,
                        (unsigned)wire_len,
                        (unsigned)g_radio.lastPacketHops(),
                        g_radio.dio2PinVerified() ? "true" : "false",
                        g_radio.lastHopTrace()
                    );
                }
            }
        }
    }
}
