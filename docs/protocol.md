# Protocol Notes

The protocol is an evolving research design. A packet should carry a protocol version, unique packet and message identifiers, source and destination identifiers, hop limit, payload, and integrity protection. Relays validate framing and hop limits before forwarding. Acknowledgements identify the message being acknowledged. Implementations must bound retries and reject duplicate deliveries.

## Current local prototype

The application encrypts each group message using AES-256-GCM with a fresh
96-bit nonce. The encrypted record contains the nonce and authenticated
ciphertext; message ID, group ID, sender label, and timestamp are supplied as
associated data, so changing those fields causes authentication to fail. The
32-byte group key and message records currently live only in process memory.

Invitations use random, URL-safe, single-use tokens that map to a group in the
same process. The local UI renders the invitation as a QR code. Opening it
prefills the token, and submitting the form consumes it. Restarting the app
discards groups, keys, messages, and outstanding invitations. This is an
application-level demo protocol, not a mesh wire format; cross-device key
delivery, membership authorization, replay policy, and radio transport remain
unimplemented.
