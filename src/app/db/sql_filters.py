"""Shared SQLAlchemy predicates used by list queries."""

from sqlalchemy import ColumnElement, SQLColumnExpression


def ilike_contains(column: SQLColumnExpression[str], value: str) -> ColumnElement[bool]:
    """Case-insensitive substring match with LIKE metacharacters escaped."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")
