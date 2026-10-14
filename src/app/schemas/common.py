"""Shared response models reused across endpoints."""

from pydantic import BaseModel


class PaginatedResponse[T](BaseModel):
    """A page of items with pagination metadata for list endpoints."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
