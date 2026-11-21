"""Bind catalogue media only to verified, deterministic seed identities."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_identity import seed_id
from app.media.manifest import MEDIA_URL_FILES, MediaEntry
from app.media.storage import MediaStorageSettings
from app.models.enums import ExerciseScope, ExerciseVersionStatus
from app.models.exercises import Exercise, ExerciseVersion


async def load_targets(
    session: AsyncSession, entries: list[MediaEntry], *, lock: bool = False
) -> dict[int, tuple[UUID, ...]]:
    """Reject an unseeded database or conflicting catalogue before uploads."""
    by_id = {seed_id("exercise", e.source_id): e for e in entries if e.source_id}
    query = select(Exercise).where(Exercise.id.in_(by_id))
    version_query = select(ExerciseVersion).where(
        ExerciseVersion.exercise_id.in_(by_id)
    )
    if lock:
        query = query.with_for_update()
        version_query = version_query.with_for_update()
    exercises = {e.id: e for e in await session.scalars(query)}
    versions = list(await session.scalars(version_query))
    if set(exercises) != set(by_id):
        raise ValueError("Database catalogue is incomplete; run seed-system-data first")
    targets: dict[int, tuple[UUID, ...]] = {}
    for exercise_id, entry in by_id.items():
        exercise = exercises[exercise_id]
        seeded_versions = [
            v
            for v in versions
            if v.exercise_id == exercise_id
            and v.id
            == seed_id("exercise-version", f"{entry.source_id}:{v.version_number}")
            and v.status == ExerciseVersionStatus.APPROVED
            and v.name == entry.name
        ]
        if (
            exercise.scope != ExerciseScope.GLOBAL
            or exercise.name != entry.name
            or exercise.latest_approved_version_id
            not in {v.id for v in seeded_versions}
        ):
            raise ValueError(
                f"Database catalogue mismatch for source {entry.source_id}"
            )
        targets[entry.source_id] = tuple(v.id for v in seeded_versions)
    return targets


async def save_urls(
    session: AsyncSession, entries: list[MediaEntry], settings: MediaStorageSettings
) -> int:
    """Write uploaded media URLs in the caller's transaction.

    Recheck and lock targets after the network work. Historical plan snapshots and
    non-seeded moderation versions retain their original contents.
    """
    targets = await load_targets(session, entries, lock=True)
    for entry in entries:
        if not entry.source_id:
            continue
        values = {
            field: settings.public_url(entry.key(filename))
            for field, filename in MEDIA_URL_FILES.items()
        }
        await session.execute(
            update(Exercise)
            .where(Exercise.id == seed_id("exercise", entry.source_id))
            .values(**values)
        )
        await session.execute(
            update(ExerciseVersion)
            .where(ExerciseVersion.id.in_(targets[entry.source_id]))
            .values(**values)
        )
    return len(targets)
