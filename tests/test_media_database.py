"""Only verified catalogue exercises and their seeded versions receive URLs."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects.postgresql import dialect

from app.db.seed_identity import seed_id
from app.media.database import load_targets, save_urls
from app.media.manifest import MediaEntry
from app.media.storage import MediaStorageSettings
from app.models.enums import ExerciseScope, ExerciseVersionStatus
from app.models.exercises import Exercise, ExerciseVersion


@pytest.fixture
def db_case():
    entry = MediaEntry(1, "Bieg", "1-bieg", {})
    exercise_id = seed_id("exercise", 1)
    version_id = seed_id("exercise-version", "1:1")
    exercise = Exercise(
        id=exercise_id,
        name="Bieg",
        scope=ExerciseScope.GLOBAL,
        latest_approved_version_id=version_id,
    )
    version = ExerciseVersion(
        id=version_id,
        exercise_id=exercise_id,
        name="Bieg",
        status=ExerciseVersionStatus.APPROVED,
        version_number=1,
    )
    session = AsyncMock()
    session.scalars.side_effect = [[exercise], [version]]
    return entry, exercise, version, session


def test_targets_validate_exact_seeded_identities(db_case):
    entry, _, version, session = db_case
    assert asyncio.run(load_targets(session, [entry])) == {1: (version.id,)}


@pytest.mark.parametrize("conflict", ["private", "name", "version", "missing"])
def test_conflicting_catalogue_fails_before_mutation(db_case, conflict):
    entry, exercise, version, session = db_case
    if conflict == "private":
        exercise.scope = ExerciseScope.PRIVATE
    elif conflict == "name":
        exercise.name = "Other exercise"
    elif conflict == "version":
        version.status = ExerciseVersionStatus.PENDING
    else:
        session.scalars.side_effect = [[], []]
    with pytest.raises(ValueError):
        asyncio.run(load_targets(session, [entry]))
    session.execute.assert_not_called()
    session.commit.assert_not_called()


def test_urls_written_to_exercise_and_version_without_committing_caller_transaction(
    db_case,
):
    entry, exercise, version, session = db_case
    settings = MediaStorageSettings(
        _env_file=None,
        s3_endpoint="https://s3.example.com",
        s3_bucket="media",
        s3_access_key_id="key",
        s3_secret_access_key="secret",
        public_base_url="https://cdn.example.com",
    )
    assert (
        asyncio.run(
            save_urls(
                session, [MediaEntry(0, "Placeholder", "0-empty", {}), entry], settings
            )
        )
        == 1
    )
    statements = [call.args[0] for call in session.execute.call_args_list]
    assert len(statements) == 2
    for statement in statements:
        params = statement.compile(dialect=dialect()).params
        assert (
            params["image_url"] == "https://cdn.example.com/exercises/1/thumb-dark.webp"
        )
        assert (
            params["animation_url"]
            == "https://cdn.example.com/exercises/1/anim-dark.webp"
        )
        assert (
            params["image_url_light"]
            == "https://cdn.example.com/exercises/1/thumb-light.webp"
        )
        assert (
            params["animation_url_light"]
            == "https://cdn.example.com/exercises/1/anim-light.webp"
        )
    assert statements[0].compile().params["id_1"] == exercise.id
    assert statements[1].compile().params["id_1"] == [version.id]
    assert all(
        query.args[0]._for_update_arg is not None
        for query in session.scalars.call_args_list
    )
    session.commit.assert_not_called()
