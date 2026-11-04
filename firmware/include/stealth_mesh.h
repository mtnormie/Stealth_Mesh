#ifndef STEALTH_MESH_H
#define STEALTH_MESH_H

#include <stdint.h>
#include <stddef.h>

// Exact pinout: ESP32-C3 SuperMini (U1) <-> HopeRF RFM95W-868S2 (SX1276, U2)
namespace StealthPins {
    constexpr int SPI_SCK   = 4;  // RFM95W Pin 4  (SCK)
    constexpr int SPI_MISO  = 5;  // RFM95W Pin 2  (MISO)
    constexpr int SPI_MOSI  = 6;  // RFM95W Pin 3  (MOSI)
    constexpr int LORA_NSS  = 7;  // RFM95W Pin 5  (NSS / CS)
    constexpr int LORA_RST  = 3;  // RFM95W Pin 6  (RESET)
    constexpr int LORA_DIO0 = 2;  // RFM95W Pin 14 (DIO0: RxDone / TxDone)
    constexpr int LORA_DIO2 = 1;  // RFM95W Pin 16 (DIO2: FhssChangeChannel)
    constexpr int LED_PIN   = 8;  // ESP32-C3 SuperMini onboard blue LED (active LOW)
    constexpr int BOOT_BTN  = 9;  // ESP32-C3 SuperMini BOOT button (GPIO9, active LOW)
}

// Binary Wire Frame Constants (matches core/packet.py)
constexpr uint8_t  SMSH_MAGIC[4]       = {'S', 'M', 'S', 'H'};
constexpr uint8_t  SMSH_VERSION        = 1;
constexpr size_t   SMSH_MAX_FRAME_SIZE = 250; // Fits within SX1276 256-byte FIFO
constexpr size_t   SMSH_MAX_ID_LEN     = 36;
constexpr size_t   SMSH_MAX_PAYLOAD    = 160;

struct MeshFrame {
    uint8_t  version;
    uint8_t  hop_limit;
    char     packet_id[SMSH_MAX_ID_LEN + 1];
    char     message_id[SMSH_MAX_ID_LEN + 1];
    char     source[SMSH_MAX_ID_LEN + 1];
    char     destination[SMSH_MAX_ID_LEN + 1];
    uint8_t  payload[SMSH_MAX_PAYLOAD];
    uint16_t payload_len;
    int16_t  last_rssi_dbm;
    float    last_snr_db;
};

// Radio Driver API (SX1276 SPI + Hardware FHSS)
class RadioDriver {
public:
    bool begin(bool enable_fhss = true, uint8_t hop_period_symbols = 5);
    uint8_t readChipVersion();
    uint8_t readHopPeriod();
    void setChannelByIndex(uint8_t channel_index);
    void setFrequencyHz(uint32_t freq_hz);
    void startReceive();
    bool transmitFrame(const uint8_t* data, size_t len, bool allow_tx = true);
    bool pollReceivedFrame(uint8_t* out_buf, size_t max_len, size_t& out_len, int16_t& rssi_dbm, float& snr_db);
    void handleFhssInterrupt();
    void sleep();
    void standby();

    uint32_t totalFhssHops() const { return total_fhss_hops_; }
    uint8_t  lastPacketHops() const { return last_packet_hops_; }
    bool     dio2PinVerified() const { return dio2_pin_verified_; }
    uint32_t currentFreqHz() const { return current_freq_hz_; }
    const char* lastHopTrace() const { return last_hop_trace_; }
    void setFhssSeed(uint8_t seed) { fhss_seed_ = seed & 0x07U; }

private:
    uint32_t total_fhss_hops_   = 0;
    uint8_t  last_packet_hops_  = 0;
    uint8_t  cur_packet_hops_   = 0;
    uint8_t  fhss_seed_         = 3;
    bool     dio2_pin_verified_ = false;
    uint32_t current_freq_hz_   = 868100000UL;
    char     last_hop_trace_[128] = "868.1";
};

// Packet Handler API (SMSH Binary Wire Format + AES-256-GCM + CRC-32 + Deduplication)
class PacketHandler {
public:
    static bool isValidSafeId(const char* id_str, size_t max_len);
    static uint32_t computeCrc32(const uint8_t* data, size_t len);
    static bool sealFramePayload(MeshFrame& frame, const uint8_t key[32], const uint8_t iv[12]);
    static bool openFramePayload(MeshFrame& frame, const uint8_t key[32]);
    static bool encodeFrame(const MeshFrame& frame, uint8_t* out_buf, size_t max_len, size_t& out_len);
    static bool decodeFrame(const uint8_t* raw, size_t raw_len, MeshFrame& out_frame);
    bool isDuplicateAndRemember(const char* message_id);
private:
    static constexpr size_t DEDUP_CAPACITY = 32;
    char seen_ids_[DEDUP_CAPACITY][SMSH_MAX_ID_LEN + 1] = {};
    size_t next_slot_ = 0;
};

// Bounded FIFO Message Queue for Embedded RAM
class EmbeddedMessageQueue {
public:
    bool enqueue(const MeshFrame& frame);
    bool dequeue(MeshFrame& out_frame);
    size_t size() const { return count_; }
private:
    static constexpr size_t CAPACITY = 16;
    MeshFrame ring_[CAPACITY] = {};
    size_t head_ = 0;
    size_t tail_ = 0;
    size_t count_ = 0;
};

// Power Manager API
class PowerManager {
public:
    void begin();
    void enterLightDutyCycle(RadioDriver& radio, uint32_t sleep_ms);
};

#endif // STEALTH_MESH_H
