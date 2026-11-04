#include "stealth_mesh.h"
#include <Arduino.h>
#include <SPI.h>

// Semtech SX1276 LoRa Register Map
namespace SX1276Reg {
    constexpr uint8_t FIFO                 = 0x00;
    constexpr uint8_t OP_MODE              = 0x01;
    constexpr uint8_t FRF_MSB              = 0x06;
    constexpr uint8_t FRF_MID              = 0x07;
    constexpr uint8_t FRF_LSB              = 0x08;
    constexpr uint8_t PA_CONFIG            = 0x09;
    constexpr uint8_t LNA                  = 0x0C;
    constexpr uint8_t FIFO_ADDR_PTR        = 0x0D;
    constexpr uint8_t FIFO_TX_BASE_ADDR    = 0x0E;
    constexpr uint8_t FIFO_RX_BASE_ADDR    = 0x0F;
    constexpr uint8_t FIFO_RX_CURRENT_ADDR = 0x10;
    constexpr uint8_t IRQ_FLAGS_MASK       = 0x11;
    constexpr uint8_t IRQ_FLAGS            = 0x12;
    constexpr uint8_t RX_NB_BYTES          = 0x13;
    constexpr uint8_t PKT_SNR_VALUE        = 0x19;
    constexpr uint8_t PKT_RSSI_VALUE       = 0x1A;
    constexpr uint8_t MODEM_CONFIG_1       = 0x1D;
    constexpr uint8_t MODEM_CONFIG_2       = 0x1E;
    constexpr uint8_t PREAMBLE_MSB         = 0x20;
    constexpr uint8_t PREAMBLE_LSB         = 0x21;
    constexpr uint8_t PAYLOAD_LENGTH       = 0x22;
    constexpr uint8_t HOP_PERIOD           = 0x24;
    constexpr uint8_t MODEM_CONFIG_3       = 0x26;
    constexpr uint8_t SYNC_WORD            = 0x39;
    constexpr uint8_t DIO_MAPPING_1        = 0x40;
    constexpr uint8_t VERSION              = 0x42;
    constexpr uint8_t PA_DAC               = 0x4D;
    constexpr uint8_t HOP_CHANNEL          = 0x1C;

    // LoRa OpModes
    constexpr uint8_t MODE_LORA_SLEEP      = 0x80;
    constexpr uint8_t MODE_LORA_STDBY      = 0x81;
    constexpr uint8_t MODE_LORA_TX         = 0x83;
    constexpr uint8_t MODE_LORA_RX_CONT    = 0x85;

    // IRQ Flags
    constexpr uint8_t IRQ_RX_DONE          = 0x40;
    constexpr uint8_t IRQ_PAYLOAD_CRC_ERR  = 0x20;
    constexpr uint8_t IRQ_TX_DONE          = 0x08;
    constexpr uint8_t IRQ_FHSS_CHANGE      = 0x02;
}

// 8 European 868 MHz ISM FHSS channels (Hz)
static constexpr uint32_t FHSS_CHANNELS_HZ[8] = {
    868100000UL, 868300000UL, 868500000UL, 867100000UL,
    867300000UL, 867500000UL, 867700000UL, 867900000UL
};

static volatile bool g_dio2_irq_pending = false;

static void IRAM_ATTR onDio2FhssRise() {
    g_dio2_irq_pending = true;
}

static uint8_t writeReg(uint8_t reg, uint8_t val) {
    digitalWrite(StealthPins::LORA_NSS, LOW);
    SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    SPI.transfer(reg | 0x80);
    uint8_t prev = SPI.transfer(val);
    SPI.endTransaction();
    digitalWrite(StealthPins::LORA_NSS, HIGH);
    return prev;
}

static uint8_t readReg(uint8_t reg) {
    digitalWrite(StealthPins::LORA_NSS, LOW);
    SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    SPI.transfer(reg & 0x7F);
    uint8_t val = SPI.transfer(0x00);
    SPI.endTransaction();
    digitalWrite(StealthPins::LORA_NSS, HIGH);
    return val;
}

uint8_t RadioDriver::readChipVersion() {
    return readReg(SX1276Reg::VERSION);
}

uint8_t RadioDriver::readHopPeriod() {
    return readReg(SX1276Reg::HOP_PERIOD);
}

void RadioDriver::setFrequencyHz(uint32_t freq_hz) {
    current_freq_hz_ = freq_hz;
    uint64_t frf = ((uint64_t)freq_hz << 19) / 32000000ULL;
    writeReg(SX1276Reg::FRF_MSB, (uint8_t)(frf >> 16));
    writeReg(SX1276Reg::FRF_MID, (uint8_t)(frf >> 8));
    writeReg(SX1276Reg::FRF_LSB, (uint8_t)(frf >> 0));
}

void RadioDriver::setChannelByIndex(uint8_t channel_index) {
    setFrequencyHz(FHSS_CHANNELS_HZ[channel_index & 0x07]);
}

bool RadioDriver::begin(bool enable_fhss, uint8_t hop_period_symbols) {
    pinMode(StealthPins::LORA_NSS, OUTPUT);
    digitalWrite(StealthPins::LORA_NSS, HIGH);
    pinMode(StealthPins::LORA_RST, OUTPUT);
    pinMode(StealthPins::LORA_DIO0, INPUT);
    pinMode(StealthPins::LORA_DIO2, INPUT);
    attachInterrupt(digitalPinToInterrupt(StealthPins::LORA_DIO2), onDio2FhssRise, RISING);

    SPI.begin(StealthPins::SPI_SCK, StealthPins::SPI_MISO, StealthPins::SPI_MOSI, StealthPins::LORA_NSS);

    // Hardware reset pulse on RFM95W Pin 6 (RESET -> GPIO3)
    digitalWrite(StealthPins::LORA_RST, LOW);
    delay(10);
    digitalWrite(StealthPins::LORA_RST, HIGH);
    delay(10);

    uint8_t version = readChipVersion();
    if (version != 0x12) {
        return false; // SX1276 must return 0x12
    }

    sleep();
    setChannelByIndex(0);

    writeReg(SX1276Reg::FIFO_TX_BASE_ADDR, 0x00);
    writeReg(SX1276Reg::FIFO_RX_BASE_ADDR, 0x00);
    writeReg(SX1276Reg::LNA, readReg(SX1276Reg::LNA) | 0x03); // LNA boost
    // BW=125kHz, CR=4/5, Explicit header
    writeReg(SX1276Reg::MODEM_CONFIG_1, 0x72);
    // SF9, CRC on
    writeReg(SX1276Reg::MODEM_CONFIG_2, 0x94);
    // LowDataRateOptimize + AGC auto on
    writeReg(SX1276Reg::MODEM_CONFIG_3, 0x04);
    writeReg(SX1276Reg::PREAMBLE_MSB, 0x00);
    writeReg(SX1276Reg::PREAMBLE_LSB, 0x0C); // 12-symbol preamble for FHSS sync
    writeReg(SX1276Reg::SYNC_WORD, 0x2B);    // Private Stealth Mesh sync word

    // PA_BOOST +17 dBm safe continuous output
    writeReg(SX1276Reg::PA_CONFIG, 0x8F);
    writeReg(SX1276Reg::PA_DAC, 0x84);

    // Hardware intra-packet FHSS configuration (RegHopPeriod + DIO2 FhssChangeChannel)
    writeReg(SX1276Reg::HOP_PERIOD, enable_fhss ? hop_period_symbols : 0x00);
    writeReg(SX1276Reg::DIO_MAPPING_1, 0x00); // DIO0=RxDone/TxDone, DIO2=FhssChangeChannel

    standby();
    return true;
}

void RadioDriver::handleFhssInterrupt() {
    if (!g_dio2_irq_pending && digitalRead(StealthPins::LORA_DIO2) == LOW) {
        uint8_t quick_irq = readReg(SX1276Reg::IRQ_FLAGS);
        if (!(quick_irq & SX1276Reg::IRQ_FHSS_CHANGE)) {
            return;
        }
    }
    uint8_t irq = readReg(SX1276Reg::IRQ_FLAGS);
    if (irq & SX1276Reg::IRQ_FHSS_CHANGE) {
        if (g_dio2_irq_pending || digitalRead(StealthPins::LORA_DIO2) == HIGH) {
            dio2_pin_verified_ = true;
        }
        g_dio2_irq_pending = false;
        uint8_t hop_ch = readReg(SX1276Reg::HOP_CHANNEL) & 0x3F;
        // Affine bijection over Z_8 (gcd(5, 8) == 1) keyed by fhss_seed_ spreads hops across all 8 channels
        uint8_t idx = (uint8_t)((hop_ch * 5U + fhss_seed_) & 0x07U);
        setChannelByIndex(idx);
        ++total_fhss_hops_;
        ++cur_packet_hops_;

        char step[16];
        uint32_t mhz_x10 = FHSS_CHANNELS_HZ[idx] / 100000UL;
        snprintf(step, sizeof(step), "->%lu.%lu", (unsigned long)(mhz_x10 / 10), (unsigned long)(mhz_x10 % 10));
        if (strlen(last_hop_trace_) + strlen(step) + 1 < sizeof(last_hop_trace_)) {
            strcat(last_hop_trace_, step);
        }
        writeReg(SX1276Reg::IRQ_FLAGS, SX1276Reg::IRQ_FHSS_CHANGE);
    }
}

void RadioDriver::startReceive() {
    standby();
    setChannelByIndex(fhss_seed_ & 0x07U);
    writeReg(SX1276Reg::IRQ_FLAGS, 0xFF);
    writeReg(SX1276Reg::FIFO_ADDR_PTR, 0x00);
    writeReg(SX1276Reg::OP_MODE, SX1276Reg::MODE_LORA_RX_CONT);
}

bool RadioDriver::transmitFrame(const uint8_t* data, size_t len, bool allow_tx) {
    if (!allow_tx || data == nullptr || len == 0 || len > SMSH_MAX_FRAME_SIZE) {
        return false;
    }
    standby();
    uint8_t start_idx = fhss_seed_ & 0x07U;
    setChannelByIndex(start_idx);
    cur_packet_hops_ = 0;
    uint32_t start_mhz_x10 = FHSS_CHANNELS_HZ[start_idx] / 100000UL;
    snprintf(last_hop_trace_, sizeof(last_hop_trace_), "%lu.%lu", (unsigned long)(start_mhz_x10 / 10), (unsigned long)(start_mhz_x10 % 10));
    writeReg(SX1276Reg::IRQ_FLAGS, 0xFF);
    writeReg(SX1276Reg::FIFO_ADDR_PTR, 0x00);

    digitalWrite(StealthPins::LORA_NSS, LOW);
    SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    SPI.transfer(SX1276Reg::FIFO | 0x80);
    for (size_t i = 0; i < len; ++i) {
        SPI.transfer(data[i]);
    }
    SPI.endTransaction();
    digitalWrite(StealthPins::LORA_NSS, HIGH);

    writeReg(SX1276Reg::PAYLOAD_LENGTH, (uint8_t)len);
    writeReg(SX1276Reg::OP_MODE, SX1276Reg::MODE_LORA_TX);

    uint32_t start_ms = millis();
    while ((millis() - start_ms) < 2500) {
        handleFhssInterrupt();
        uint8_t irq = readReg(SX1276Reg::IRQ_FLAGS);
        if (irq & SX1276Reg::IRQ_TX_DONE) {
            last_packet_hops_ = cur_packet_hops_;
            writeReg(SX1276Reg::IRQ_FLAGS, 0xFF);
            startReceive();
            return true;
        }
        delayMicroseconds(250);
    }
    startReceive();
    return false;
}

bool RadioDriver::pollReceivedFrame(
    uint8_t* out_buf,
    size_t max_len,
    size_t& out_len,
    int16_t& rssi_dbm,
    float& snr_db
) {
    handleFhssInterrupt();
    uint8_t irq = readReg(SX1276Reg::IRQ_FLAGS);
    if (!(irq & SX1276Reg::IRQ_RX_DONE)) {
        return false;
    }
    bool crc_err = (irq & SX1276Reg::IRQ_PAYLOAD_CRC_ERR) != 0;
    uint8_t rx_len = readReg(SX1276Reg::RX_NB_BYTES);
    uint8_t rx_addr = readReg(SX1276Reg::FIFO_RX_CURRENT_ADDR);
    writeReg(SX1276Reg::FIFO_ADDR_PTR, rx_addr);

    if (crc_err || rx_len == 0 || rx_len > max_len) {
        writeReg(SX1276Reg::IRQ_FLAGS, 0xFF);
        return false;
    }

    digitalWrite(StealthPins::LORA_NSS, LOW);
    SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    SPI.transfer(SX1276Reg::FIFO & 0x7F);
    for (uint8_t i = 0; i < rx_len; ++i) {
        out_buf[i] = SPI.transfer(0x00);
    }
    SPI.endTransaction();
    digitalWrite(StealthPins::LORA_NSS, HIGH);

    int8_t raw_snr = (int8_t)readReg(SX1276Reg::PKT_SNR_VALUE);
    snr_db = raw_snr * 0.25f;
    rssi_dbm = -157 + (int16_t)readReg(SX1276Reg::PKT_RSSI_VALUE);
    out_len = rx_len;

    writeReg(SX1276Reg::IRQ_FLAGS, 0xFF);
    return true;
}

void RadioDriver::sleep() {
    writeReg(SX1276Reg::OP_MODE, SX1276Reg::MODE_LORA_SLEEP);
}

void RadioDriver::standby() {
    writeReg(SX1276Reg::OP_MODE, SX1276Reg::MODE_LORA_STDBY);
}
