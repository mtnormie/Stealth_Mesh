#!/usr/bin/env bash
# Production eFuse Lock Script for ESP32-C3 (IRREVERSIBLE!)
# Enables Secure Boot v2, Flash Encryption (Release Mode), and permanently disables JTAG/ROM download readout.
set -euo pipefail

PORT="${1:-/dev/ttyACM0}"
SIGNING_KEY="${2:-secure_boot_signing_key.pem}"
FLASH_KEY="${3:-flash_encryption_key.bin}"

echo "WARNING: Burning eFuses on ${PORT} is IRREVERSIBLE."
echo "Make sure ${SIGNING_KEY} (RSA-3072) and ${FLASH_KEY} (256-bit) are backed up securely."
read -r -p "Type 'LOCK_NODE' to continue: " CONFIRM
if [[ "${CONFIRM}" != "LOCK_NODE" ]]; then
  echo "Aborted."
  exit 1
fi

if [[ ! -f "${SIGNING_KEY}" ]]; then
  espsecure.py generate_signing_key --version 2 "${SIGNING_KEY}"
fi
if [[ ! -f "${FLASH_KEY}" ]]; then
  espsecure.py generate_flash_encryption_key "${FLASH_KEY}"
fi

# 1. Burn Flash Encryption Key and enable XTS-AES-128 Flash Encryption
espefuse.py --port "${PORT}" burn_key BLOCK_KEY0 "${FLASH_KEY}" XTS_AES_128_KEY
# 2. Burn Secure Boot v2 RSA-3072 public key digest
espsecure.py digest_sbv2_public_key --keyfile "${SIGNING_KEY}" -o sbv2_digest.bin
espefuse.py --port "${PORT}" burn_key BLOCK_KEY1 sbv2_digest.bin SECURE_BOOT_DIGEST0
# 3. Enable Secure Boot v2, Flash Encryption, and disable JTAG/USB/UART download readout
espefuse.py --port "${PORT}" burn_efuse SECURE_BOOT_EN 1
espefuse.py --port "${PORT}" burn_efuse SPI_BOOT_CRYPT_CNT 7
espefuse.py --port "${PORT}" burn_efuse DIS_USB_JTAG 1
espefuse.py --port "${PORT}" burn_efuse DIS_PAD_JTAG 1
espefuse.py --port "${PORT}" burn_efuse DIS_DOWNLOAD_MODE 1
rm -f sbv2_digest.bin
echo "Hardware lock complete for ${PORT}."
