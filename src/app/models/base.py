"""Shared SQLAlchemy declarative base and timestamp helpers."""

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class shared by every SQLAlchemy model."""


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)
