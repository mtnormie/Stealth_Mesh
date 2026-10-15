# Threat Model

Assets include message confidentiality, message integrity, node credentials, and availability of the mesh. Consider passive listeners, packet modification, replay, impersonation, node loss, and congestion. Authenticated encryption and replay protection address only some threats; they do not hide traffic patterns or guarantee availability. Key provisioning, revocation, and physical compromise remain open design concerns.

The initial app prototype uses the maintained `cryptography` package's
AES-256-GCM implementation. It generates random 32-byte group keys and fresh
96-bit nonces, and authenticates message metadata as associated data. Keys and
messages exist in plaintext in the local Python process while being used;
there is no secure persistence, identity authentication, key rotation, or
membership access control yet. Single-use invitation tokens are held in memory
and only prevent repeated redemption through that same running process. The
web server binds to loopback (`127.0.0.1`) and does not expose a remote service.
The QR flow therefore demonstrates local invitation handling, not secure key
provisioning between mesh devices.
