"""add exercise planning attributes

Revision ID: 035f53e1b652
Revises: 70cec280aa2f
Create Date: 2026-11-03 22:28:56.262852

"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "035f53e1b652"
down_revision: str | Sequence[str] | None = "70cec280aa2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

equipment_requirement_mode = sa.Enum("ALL", "ANY", name="equipment_requirement_mode")

SYSTEM_TRAINING_SEGMENTS = (
    {"id": 1, "code": "WARMUP", "name": "Rozgrzewka"},
    {"id": 2, "code": "GAME", "name": "Zabawa"},
    {"id": 3, "code": "MAIN", "name": "Ćwiczenia"},
    {"id": 4, "code": "COOLDOWN", "name": "Rozciąganie"},
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

SYSTEM_TRAINING_TYPE_NAMESPACE = UUID("a1f8c50b-a3e1-4f4e-8ff0-3a02e5ec6a00")


def _training_type_rows() -> list[dict[str, object]]:
    created_at = datetime.now(UTC)
    return [
        {
            "id": uuid5(SYSTEM_TRAINING_TYPE_NAMESPACE, name.casefold()),
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
                sa.Column(
                    column_name, sa.SmallInteger(), server_default="3", nullable=False
                ),
            )
            op.create_check_constraint(
                f"ck_{table_name}_{column_name}",
                table_name,
                f"{column_name} BETWEEN 1 AND 5",
            )

    training_segments = sa.table(
        "training_segments",
        sa.column("id", sa.SmallInteger()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
    )
    insert_segments = postgresql.insert(training_segments).values(
        SYSTEM_TRAINING_SEGMENTS
    )
    op.execute(
        insert_segments.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "code": insert_segments.excluded.code,
                "name": insert_segments.excluded.name,
            },
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
                "LOCAL",
                "PENDING",
                "GLOBAL",
                name="catalog_visibility",
                create_type=False,
            ),
        ),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    obsolete_global_training_type_ids = sa.select(training_types.c.id).where(
        training_types.c.visibility == "GLOBAL",
        training_types.c.name.not_in(SYSTEM_TRAINING_TYPE_NAMES),
    )
    for association_table_name in (
        "trainer_exercise_training_types",
        "exercise_version_training_types",
    ):
        association_table = sa.table(
            association_table_name,
            sa.column("training_type_id", sa.Uuid(as_uuid=True)),
        )
        op.execute(
            sa.delete(association_table).where(
                association_table.c.training_type_id.in_(
                    obsolete_global_training_type_ids
                )
            )
        )
    op.execute(
        sa.delete(training_types).where(
            training_types.c.visibility == "GLOBAL",
            training_types.c.name.not_in(SYSTEM_TRAINING_TYPE_NAMES),
        )
    )
    for row in _training_type_rows():
        op.execute(
            postgresql.insert(training_types).values(**row).on_conflict_do_nothing()
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
