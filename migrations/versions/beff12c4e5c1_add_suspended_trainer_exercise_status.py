"""add suspended trainer exercise status

Revision ID: beff12c4e5c1
Revises: a1b2c3d4e5f6
Create Date: 2026-11-08 13:39:09.318500

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "beff12c4e5c1"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TYPE trainer_exercise_status RENAME VALUE 'HIDDEN' TO 'SUSPENDED'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "ALTER TYPE trainer_exercise_status RENAME VALUE 'SUSPENDED' TO 'HIDDEN'"
    )
