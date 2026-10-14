# Protocol Notes

The protocol is an evolving research design. A packet should carry a protocol version, unique packet and message identifiers, source and destination identifiers, hop limit, payload, and integrity protection. Relays validate framing and hop limits before forwarding. Acknowledgements identify the message being acknowledged. Implementations must bound retries and reject duplicate deliveries.

No wire format is standardized yet; document compatibility changes before implementation.
