"""add exercise planning attributes

Revision ID: 035f53e1b652
Revises: 70cec280aa2f
Create Date: 2026-11-03 22:28:56.262852

"""
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '035f53e1b652'
down_revision: Union[str, Sequence[str], None] = '70cec280aa2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

equipment_requirement_mode = sa.Enum(
    "ALL", "ANY", name="equipment_requirement_mode"
)

SYSTEM_TRAINING_TYPE_NAMES = (
    "Celność",
    "Core",
    "Dystans",
    "Kondycja",
    "Koordynacja",
    "Mobilność",
    "Mobilność – Dynamiczne",
    "Mobilność – Statyczne",
    "Moc",
    "Obrona",
    "Ogólnorozwojowy",
    "Pamięć",
    "Reakcja",
    "Równowaga",
    "Siła",
    "Siła grzbietu",
    "Stabilizacja",
    "Szybkość",
    "Taktyka",
    "Technika",
    "Układy formalne",
    "Walka",
    "Wytrzymałość",
    "Zabawa",
)


def _training_type_rows() -> list[dict[str, object]]:
    created_at = datetime.now(timezone.utc)
    return [
        {
            "id": uuid5(NAMESPACE_URL, f"taeplando/training-type/{name.casefold()}"),
            "owner_user_id": None,
            "name": name,
            "visibility": "GLOBAL",
            "created_at": created_at,
        }
        for name in SYSTEM_TRAINING_TYPE_NAMES
    ]


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
                sa.Column(column_name, sa.SmallInteger(), server_default="3", nullable=False),
            )
            op.create_check_constraint(
                f"ck_{table_name}_{column_name}",
                table_name,
                f"{column_name} BETWEEN 1 AND 5",
            )

    op.execute(
        sa.text(
            """
            UPDATE training_segments
            SET name = CASE id
                WHEN 1 THEN 'Rozgrzewka'
                WHEN 2 THEN 'Zabawa'
                WHEN 3 THEN 'Ćwiczenia'
                WHEN 4 THEN 'Rozciąganie'
            END
            WHERE id IN (1, 2, 3, 4)
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE training_types
            SET name = CASE name
                WHEN 'Poomsae' THEN 'Układy formalne'
                WHEN 'Walka sportowa' THEN 'Walka'
            END
            WHERE visibility = 'GLOBAL'
              AND name IN ('Poomsae', 'Walka sportowa')
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM trainer_exercise_training_types
            WHERE training_type_id IN (
                SELECT id FROM training_types
                WHERE visibility = 'GLOBAL' AND name = 'Samoobrona'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM exercise_version_training_types
            WHERE training_type_id IN (
                SELECT id FROM training_types
                WHERE visibility = 'GLOBAL' AND name = 'Samoobrona'
            )
            """
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM training_types WHERE visibility = 'GLOBAL' AND name = 'Samoobrona'"
        )
    )
    training_types = sa.table(
        "training_types",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("owner_user_id", sa.Uuid(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column(
            "visibility",
            postgresql.ENUM(
                "LOCAL", "PENDING", "GLOBAL", name="catalog_visibility", create_type=False
            ),
        ),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    for row in _training_type_rows():
        op.execute(postgresql.insert(training_types).values(**row).on_conflict_do_nothing())


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
