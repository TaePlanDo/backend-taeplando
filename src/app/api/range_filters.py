"""Shared validation for inclusive list-query ranges."""

from fastapi import HTTPException, status


def reject_inverted_range(
    min_value: int | None, max_value: int | None, *, label: str
) -> None:
    """Reject impossible inclusive filter ranges when both bounds are set."""
    if min_value is not None and max_value is not None and min_value > max_value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"min_{label} must be less than or equal to max_{label}",
        )
