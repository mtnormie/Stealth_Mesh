#include "stealth_mesh.h"
#include <string.h>
#include <mbedtls/gcm.h>

bool PacketHandler::isValidSafeId(const char* id_str, size_t max_len) {
    if (id_str == nullptr || id_str[0] == '\0') {
        return false;
    }
    size_t len = strnlen(id_str, max_len + 1);
    if (len == 0 || len > max_len) {
        return false;
    }
    for (size_t i = 0; i < len; ++i) {
        char c = id_str[i];
        bool ok = (c >= 'A' && c <= 'Z') ||
                  (c >= 'a' && c <= 'z') ||
                  (c >= '0' && c <= '9') ||
                  c == '-' || c == '_';
        if (!ok) {
            return false;
        }
    }
    return true;
}

static size_t buildFrameAad(const MeshFrame& frame, uint8_t* aad_buf, size_t max_aad) {
    size_t msg_len = strnlen(frame.message_id, SMSH_MAX_ID_LEN);
    size_t src_len = strnlen(frame.source, SMSH_MAX_ID_LEN);
    size_t dst_len = strnlen(frame.destination, SMSH_MAX_ID_LEN);
    size_t total = 1 + msg_len + 1 + src_len + 1 + dst_len;
    if (total > max_aad) {
        return 0;
    }
    size_t off = 0;
    aad_buf[off++] = frame.version;
    memcpy(aad_buf + off, frame.message_id, msg_len);
    off += msg_len;
    aad_buf[off++] = '|';
    memcpy(aad_buf + off, frame.source, src_len);
    off += src_len;
    aad_buf[off++] = '|';
    memcpy(aad_buf + off, frame.destination, dst_len);
    off += dst_len;
    return off;
}

bool PacketHandler::sealFramePayload(MeshFrame& frame, const uint8_t key[32], const uint8_t iv[12]) {
    if (key == nullptr || iv == nullptr) {
        return false;
    }
    // 12-byte IV + ciphertext + 16-byte GCM tag must fit in SMSH_MAX_PAYLOAD (160)
    if (frame.payload_len == 0 || frame.payload_len + 28 > SMSH_MAX_PAYLOAD) {
        return false;
    }
    uint8_t aad[128];
    size_t aad_len = buildFrameAad(frame, aad, sizeof(aad));
    if (aad_len == 0) {
        return false;
    }

    uint8_t plaintext[SMSH_MAX_PAYLOAD];
    uint16_t plain_len = frame.payload_len;
    memcpy(plaintext, frame.payload, plain_len);

    uint8_t ciphertext[SMSH_MAX_PAYLOAD];
    uint8_t tag[16];

    mbedtls_gcm_context gcm;
    mbedtls_gcm_init(&gcm);
    int rc = mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES, key, 256);
    if (rc == 0) {
        rc = mbedtls_gcm_crypt_and_tag(
            &gcm,
            MBEDTLS_GCM_ENCRYPT,
            plain_len,
            iv, 12,
            aad, aad_len,
            plaintext,
            ciphertext,
            16, tag
        );
    }
    mbedtls_gcm_free(&gcm);
    if (rc != 0) {
        return false;
    }

    memcpy(frame.payload, iv, 12);
    memcpy(frame.payload + 12, ciphertext, plain_len);
    memcpy(frame.payload + 12 + plain_len, tag, 16);
    frame.payload_len = plain_len + 28;
    return true;
}

bool PacketHandler::openFramePayload(MeshFrame& frame, const uint8_t key[32]) {
    if (key == nullptr || frame.payload_len <= 28 || frame.payload_len > SMSH_MAX_PAYLOAD) {
        return false;
    }
    uint8_t aad[128];
    size_t aad_len = buildFrameAad(frame, aad, sizeof(aad));
    if (aad_len == 0) {
        return false;
    }

    uint16_t cipher_len = frame.payload_len - 28;
    const uint8_t* iv = frame.payload;
    const uint8_t* ciphertext = frame.payload + 12;
    const uint8_t* tag = frame.payload + 12 + cipher_len;

    uint8_t plaintext[SMSH_MAX_PAYLOAD] = {};
    mbedtls_gcm_context gcm;
    mbedtls_gcm_init(&gcm);
    int rc = mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES, key, 256);
    if (rc == 0) {
        rc = mbedtls_gcm_auth_decrypt(
            &gcm,
            cipher_len,
            iv, 12,
            aad, aad_len,
            tag, 16,
            ciphertext,
            plaintext
        );
    }
    mbedtls_gcm_free(&gcm);
    if (rc != 0) {
        return false;
    }

    memset(frame.payload, 0, sizeof(frame.payload));
    memcpy(frame.payload, plaintext, cipher_len);
    frame.payload_len = cipher_len;
    return true;
}

uint32_t PacketHandler::computeCrc32(const uint8_t* data, size_t len) {
    uint32_t crc = 0xFFFFFFFFU;
    for (size_t i = 0; i < len; ++i) {
        crc ^= data[i];
        for (uint8_t bit = 0; bit < 8; ++bit) {
            uint32_t mask = -(crc & 1U);
            crc = (crc >> 1) ^ (0xEDB88320U & mask);
        }
    }
    return ~crc;
}

bool PacketHandler::encodeFrame(
    const MeshFrame& frame,
    uint8_t* out_buf,
    size_t max_len,
    size_t& out_len
) {
    size_t pkt_len = strnlen(frame.packet_id, SMSH_MAX_ID_LEN + 1);
    size_t msg_len = strnlen(frame.message_id, SMSH_MAX_ID_LEN + 1);
    size_t src_len = strnlen(frame.source, SMSH_MAX_ID_LEN + 1);
    size_t dst_len = strnlen(frame.destination, SMSH_MAX_ID_LEN + 1);

    if (!isValidSafeId(frame.packet_id, SMSH_MAX_ID_LEN) ||
        !isValidSafeId(frame.message_id, SMSH_MAX_ID_LEN) ||
        !isValidSafeId(frame.source, SMSH_MAX_ID_LEN) ||
        !isValidSafeId(frame.destination, SMSH_MAX_ID_LEN) ||
        frame.payload_len > SMSH_MAX_PAYLOAD) {
        return false;
    }

    size_t body_len = 12 + pkt_len + msg_len + src_len + dst_len + frame.payload_len;
    if (body_len + 4 > max_len) {
        return false;
    }

    memcpy(out_buf, SMSH_MAGIC, 4);
    out_buf[4] = frame.version;
    out_buf[5] = frame.hop_limit;
    out_buf[6] = (uint8_t)pkt_len;
    out_buf[7] = (uint8_t)msg_len;
    out_buf[8] = (uint8_t)src_len;
    out_buf[9] = (uint8_t)dst_len;
    out_buf[10] = (uint8_t)((frame.payload_len >> 8) & 0xFF);
    out_buf[11] = (uint8_t)(frame.payload_len & 0xFF);

    size_t offset = 12;
    memcpy(out_buf + offset, frame.packet_id, pkt_len);
    offset += pkt_len;
    memcpy(out_buf + offset, frame.message_id, msg_len);
    offset += msg_len;
    memcpy(out_buf + offset, frame.source, src_len);
    offset += src_len;
    memcpy(out_buf + offset, frame.destination, dst_len);
    offset += dst_len;
    if (frame.payload_len > 0) {
        memcpy(out_buf + offset, frame.payload, frame.payload_len);
        offset += frame.payload_len;
    }

    uint32_t crc = computeCrc32(out_buf, offset);
    out_buf[offset + 0] = (uint8_t)((crc >> 24) & 0xFF);
    out_buf[offset + 1] = (uint8_t)((crc >> 16) & 0xFF);
    out_buf[offset + 2] = (uint8_t)((crc >> 8) & 0xFF);
    out_buf[offset + 3] = (uint8_t)(crc & 0xFF);

    out_len = offset + 4;
    return true;
}

bool PacketHandler::decodeFrame(
    const uint8_t* raw,
    size_t raw_len,
    MeshFrame& out_frame
) {
    if (raw == nullptr || raw_len < 16) {
        return false;
    }
    if (memcmp(raw, SMSH_MAGIC, 4) != 0) {
        return false;
    }

    size_t body_len = raw_len - 4;
    uint32_t expected_crc =
        ((uint32_t)raw[body_len + 0] << 24) |
        ((uint32_t)raw[body_len + 1] << 16) |
        ((uint32_t)raw[body_len + 2] << 8)  |
        ((uint32_t)raw[body_len + 3]);
    if (computeCrc32(raw, body_len) != expected_crc) {
        return false;
    }

    uint8_t pkt_len = raw[6];
    uint8_t msg_len = raw[7];
    uint8_t src_len = raw[8];
    uint8_t dst_len = raw[9];
    uint16_t payload_len = ((uint16_t)raw[10] << 8) | raw[11];

    if (pkt_len == 0 || msg_len == 0 || src_len == 0 || dst_len == 0) {
        return false;
    }
    if (pkt_len > SMSH_MAX_ID_LEN || msg_len > SMSH_MAX_ID_LEN ||
        src_len > SMSH_MAX_ID_LEN || dst_len > SMSH_MAX_ID_LEN ||
        payload_len > SMSH_MAX_PAYLOAD) {
        return false;
    }
    if (12 + pkt_len + msg_len + src_len + dst_len + payload_len != body_len) {
        return false;
    }

    memset(&out_frame, 0, sizeof(MeshFrame));
    out_frame.version = raw[4];
    out_frame.hop_limit = raw[5];

    size_t offset = 12;
    memcpy(out_frame.packet_id, raw + offset, pkt_len);
    offset += pkt_len;
    memcpy(out_frame.message_id, raw + offset, msg_len);
    offset += msg_len;
    memcpy(out_frame.source, raw + offset, src_len);
    offset += src_len;
    memcpy(out_frame.destination, raw + offset, dst_len);
    offset += dst_len;
    if (payload_len > 0) {
        memcpy(out_frame.payload, raw + offset, payload_len);
    }
    out_frame.payload_len = payload_len;
    if (!isValidSafeId(out_frame.packet_id, SMSH_MAX_ID_LEN) ||
        !isValidSafeId(out_frame.message_id, SMSH_MAX_ID_LEN) ||
        !isValidSafeId(out_frame.source, SMSH_MAX_ID_LEN) ||
        !isValidSafeId(out_frame.destination, SMSH_MAX_ID_LEN)) {
        memset(&out_frame, 0, sizeof(MeshFrame));
        return false;
    }
    return true;
}

bool PacketHandler::isDuplicateAndRemember(const char* message_id) {
    if (message_id == nullptr || message_id[0] == '\0') {
        return true;
    }
    for (size_t i = 0; i < DEDUP_CAPACITY; ++i) {
        if (strncmp(seen_ids_[i], message_id, SMSH_MAX_ID_LEN) == 0) {
            return true;
        }
    }
    strncpy(seen_ids_[next_slot_], message_id, SMSH_MAX_ID_LEN);
    seen_ids_[next_slot_][SMSH_MAX_ID_LEN] = '\0';
    next_slot_ = (next_slot_ + 1) % DEDUP_CAPACITY;
    return false;
}
