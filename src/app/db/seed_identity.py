"""Stable identities shared by catalogue seeds and media imports."""

from uuid import UUID, uuid5

SEED_NAMESPACE = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a00")


def seed_id(kind: str, key: str | int) -> UUID:
    """Resolve a source catalogue key without depending on insertion order."""
    return uuid5(SEED_NAMESPACE, f"{kind}:{key}")
