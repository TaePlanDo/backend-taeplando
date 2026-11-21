"""Verify media publication participates in a real PostgreSQL transaction."""

import asyncio
from uuid import uuid4

import pytest

from app.db.seed_identity import seed_id
from app.db.session import dispose_engine, get_session_factory
from app.media.database import save_urls
from app.media.manifest import MEDIA_URL_FILES, MediaEntry
from app.media.storage import MediaStorageSettings
from app.models.enums import AuthMethod, ExerciseScope, ExerciseVersionStatus
from app.models.exercises import Exercise, ExerciseVersion
from app.models.users import User


class AbortImport(Exception):
    """Simulate a failure after media updates, before their transaction commits."""


def test_media_urls_roll_back_with_caller_transaction():
    asyncio.run(_assert_media_rollback())


async def _assert_media_rollback():
    # Synthetic seed identities avoid collisions with a populated local catalogue.
    source = uuid4()
    entry = MediaEntry(source.int, "Media transaction test", f"{source.int}-test", {})
    settings = MediaStorageSettings(
        _env_file=None,
        s3_endpoint="https://s3.example.com",
        s3_bucket="media",
        s3_access_key_id="test-key",
        s3_secret_access_key="test-secret",
        public_base_url="https://cdn.example.com",
    )
    try:
        # Closing this uncommitted outer session also removes the test fixtures.
        async with get_session_factory()() as session:
            exercise = Exercise(
                id=seed_id("exercise", entry.source_id),
                owner=User(
                    email=f"media-{source}@example.test",
                    auth_method=AuthMethod.GOOGLE,
                    oauth_subject=f"media-{source}",
                ),
                scope=ExerciseScope.GLOBAL,
                name=entry.name,
                description="Media transaction test",
            )
            version = ExerciseVersion(
                id=seed_id("exercise-version", f"{entry.source_id}:1"),
                exercise=exercise,
                version_number=1,
                status=ExerciseVersionStatus.APPROVED,
                name=entry.name,
                description=exercise.description,
                min_age=1,
                max_age=99,
                min_participants=1,
                max_participants=20,
                duration_minutes=5,
            )
            exercise.latest_approved_version = version
            session.add(exercise)
            await session.flush()

            with pytest.raises(AbortImport):
                async with session.begin_nested():
                    assert await save_urls(session, [entry], settings) == 1
                    await session.refresh(exercise)
                    await session.refresh(version)
                    for field, filename in MEDIA_URL_FILES.items():
                        expected = settings.public_url(entry.key(filename))
                        assert getattr(exercise, field) == expected
                        assert getattr(version, field) == expected
                    raise AbortImport

            await session.refresh(exercise)
            await session.refresh(version)
            for field in MEDIA_URL_FILES:
                assert getattr(exercise, field) is None
                assert getattr(version, field) is None
    finally:
        await dispose_engine()
