# Threat Model

Assets include message confidentiality, message integrity, node credentials, and availability of the mesh. Consider passive listeners, packet modification, replay, impersonation, node loss, and congestion. Authenticated encryption and replay protection address only some threats; they do not hide traffic patterns or guarantee availability. Cross-device key provisioning and physical hardware compromise remain open design concerns.

## Implemented Cryptographic Controls

- **Authenticated Encryption (`security/encryption.py`):** AES-256-GCM with fresh 96-bit random nonces (`os.urandom(12)`) and 128-bit authentication tags via `cryptography` (or OpenSSL `libcrypto` fallback), binding canonical header metadata as Associated Authenticated Data (AAD).
- **Key Derivation & Rotation (`security/key_manager.py`):** RFC 5869 `HKDF-SHA256` (`hkdf_sha256`, `derive_subkey`) separates encryption subkeys (`aes256-gcm-enc`) from sender authentication subkeys (`hmac-sha256-sender-auth`). `KeyManager` manages versioned in-memory group keyrings, rotation (`rotate_group_key`), bounded retention of recent key versions for in-flight packets, and explicit group revocation (`revoke_group`).
- **Message Integrity & Anti-Replay (`security/integrity.py`):** Constant-time `HMAC-SHA256` verification (`hmac.compare_digest`) and per-sender sliding-window replay protection (`ReplayWindow`). `ReplayWindow` separates read-only sequence validation (`can_accept`) from state commit (`record`) so forged unauthenticated packets with large sequence numbers cannot advance the window and cause a denial of service.
- **Sender Authentication Envelopes (`security/authentication.py`):** `SignedEnvelope` and `MessageAuthenticator` combine HKDF domain-separated subkeys, AES-256-GCM encryption, HMAC-SHA256 sender authentication, and sliding-window replay protection.

## Assumptions and Limitations

Keys and messages exist in memory inside the local Python process while in use; persistent hardware-backed key storage and asymmetric cross-device key exchange are not yet implemented. Single-use QR invitation tokens are held in process memory on loopback (`127.0.0.1`). Encryption and frequency hopping do not guarantee radio invisibility against spectrum analyzers or direction finding.
