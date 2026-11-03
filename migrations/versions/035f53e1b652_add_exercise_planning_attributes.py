"""add exercise planning attributes

Revision ID: 035f53e1b652
Revises: 70cec280aa2f
Create Date: 2026-11-03 22:28:56.262852

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "035f53e1b652"
down_revision: str | Sequence[str] | None = "70cec280aa2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

equipment_requirement_mode = sa.Enum("ALL", "ANY", name="equipment_requirement_mode")


def upgrade() -> None:
    """Upgrade schema."""
    equipment_requirement_mode.create(op.get_bind(), checkfirst=True)
    for table_name in ("exercise_versions", "trainer_exercises"):
        op.add_column(
            table_name,
            sa.Column(
                "equipment_requirement_mode",
                equipment_requirement_mode,
                server_default="ALL",
                nullable=False,
            ),
        )
        for column_name in (
            "physical_difficulty",
            "technical_difficulty",
            "upper_body_load",
            "lower_body_load",
            "core_load",
        ):
            op.add_column(
                table_name,
                sa.Column(
                    column_name, sa.SmallInteger(), server_default="3", nullable=False
                ),
            )
            op.create_check_constraint(
                f"ck_{table_name}_{column_name}",
                table_name,
                f"{column_name} BETWEEN 1 AND 5",
            )


def downgrade() -> None:
    """Downgrade schema."""
    for table_name in ("trainer_exercises", "exercise_versions"):
        for column_name in (
            "core_load",
            "lower_body_load",
            "upper_body_load",
            "technical_difficulty",
            "physical_difficulty",
        ):
            op.drop_constraint(f"ck_{table_name}_{column_name}", table_name)
            op.drop_column(table_name, column_name)
        op.drop_column(table_name, "equipment_requirement_mode")
    equipment_requirement_mode.drop(op.get_bind(), checkfirst=True)
