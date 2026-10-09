"""Seed the fixed system data required by the application."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TypedDict

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import dispose_engine, get_session_factory
from app.models.catalogs import TrainingSegment


class TrainingSegmentSeed(TypedDict):
    """One immutable entry of the system training-segment dictionary."""

    id: int
    code: str
    name: str


SYSTEM_TRAINING_SEGMENTS: Sequence[TrainingSegmentSeed] = (
    {"id": 1, "code": "WARMUP", "name": "Rozgrzewka"},
    {"id": 2, "code": "GAME", "name": "Zabawa"},
    {"id": 3, "code": "MAIN", "name": "Część główna"},
    {"id": 4, "code": "COOLDOWN", "name": "Wyciszenie"},
)


async def seed_training_segments(session: AsyncSession) -> None:
    """Insert or restore the fixed training-segment dictionary."""

    statement = insert(TrainingSegment).values(list(SYSTEM_TRAINING_SEGMENTS))
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[TrainingSegment.id],
            set_={
                "code": statement.excluded.code,
                "name": statement.excluded.name,
            },
        )
    )


async def seed_system_data() -> None:
    """Apply all system seed data in one transaction."""

    async with get_session_factory()() as session:
        async with session.begin():
            await seed_training_segments(session)


async def run_seed_command() -> None:
    """Run the seed and close its database resources on the same event loop."""

    try:
        await seed_system_data()
    finally:
        await dispose_engine()


def main() -> None:
    """Run the system-data seed command."""

    asyncio.run(run_seed_command())


if __name__ == "__main__":
    main()
