"""snapshot plan exercise display attributes

Revision ID: a1b2c3d4e5f6
Revises: 77a2a1a22fd8
Create Date: 2026-11-06 18:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "77a2a1a22fd8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PLANNING_COLUMNS = (
    "physical_difficulty_snapshot",
    "technical_difficulty_snapshot",
    "upper_body_load_snapshot",
    "lower_body_load_snapshot",
    "core_load_snapshot",
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "training_plan_exercises",
        sa.Column("image_url_snapshot", sa.Text(), nullable=True),
    )
    for column_name in _PLANNING_COLUMNS:
        op.add_column(
            "training_plan_exercises",
            sa.Column(
                column_name, sa.SmallInteger(), server_default="3", nullable=False
            ),
        )
        op.create_check_constraint(
            f"ck_plan_exercises_{column_name}",
            "training_plan_exercises",
            f"{column_name} BETWEEN 1 AND 5",
        )


def downgrade() -> None:
    """Downgrade schema."""
    for column_name in reversed(_PLANNING_COLUMNS):
        op.drop_constraint(
            f"ck_plan_exercises_{column_name}", "training_plan_exercises"
        )
        op.drop_column("training_plan_exercises", column_name)
    op.drop_column("training_plan_exercises", "image_url_snapshot")
