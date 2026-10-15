"""Small key-generation helpers; key persistence is intentionally out of scope."""

import secrets

GROUP_KEY_SIZE = 32


def generate_group_key() -> bytes:
    """Return a cryptographically random 256-bit group key."""
    return secrets.token_bytes(GROUP_KEY_SIZE)


def generate_invitation_token() -> str:
    """Return a high-entropy, URL-safe, single-use invitation token."""
    return secrets.token_urlsafe(32)
