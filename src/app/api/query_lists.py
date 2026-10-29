"""Helpers for parsing comma-separated query-parameter lists."""

from collections.abc import Callable

from fastapi import HTTPException, status


def parse_csv[T](
    raw: str | None,
    *,
    field_name: str,
    parse_item: Callable[[str], T],
    item_label: str,
) -> list[T] | None:
    """Parse a CSV list; empty/omitted input means no filter."""
    if raw is None or not raw.strip():
        return None
    values: list[T] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            values.append(parse_item(token))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid {item_label} in {field_name}",
            ) from exc
    return values or None
