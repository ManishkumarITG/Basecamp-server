"""Random, human-friendly code generation for Class IDs and invitation codes."""

import secrets

# Uppercase letters + digits, minus easily confused characters (0/O, 1/I/L).
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_code(length: int = 8) -> str:
    """Return a cryptographically-random code drawn from a non-ambiguous alphabet."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def generate_otp(length: int = 6) -> str:
    """Return a numeric one-time passcode (for email verification / reset)."""
    return "".join(secrets.choice("0123456789") for _ in range(length))
