"""Shared validation and response models reused across endpoints."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field


def _normalize_non_blank(value: str) -> str:
    """Trim user-entered text and reject whitespace-only values."""
    normalized = value.strip()
    if not normalized:
        raise ValueError("Value cannot be blank")
    return normalized


Name = Annotated[
    str,
    Field(min_length=1, max_length=255),
    AfterValidator(_normalize_non_blank),
]

Description = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(_normalize_non_blank),
]


class PaginatedResponse[T](BaseModel):
    """A page of items with pagination metadata for list endpoints."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
