"""Light/dark media survives API writes, list projections and legacy edits."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.db.exercises import ExerciseConfiguration, ExercisePage, ListedExercise
from app.models.enums import ExerciseScope, TrainerExerciseStatus

MEDIA = {
    "image_url": "https://cdn.example.com/thumb-dark.webp",
    "animation_url": "https://cdn.example.com/anim-dark.webp",
    "image_url_light": "https://cdn.example.com/thumb-light.webp",
    "animation_url_light": "https://cdn.example.com/anim-light.webp",
}


def payload(**media):
    return {
        "name": "Ap chagi",
        "description": "Kopnięcie frontalne.",
        "duration_minutes": 10,
        "min_age": 1,
        "max_age": 99,
        "min_participants": 1,
        "max_participants": 99,
        "equipment_ids": [],
        "training_type_ids": [str(uuid4())],
        "segment_ids": [3],
        **media,
    }


def test_create_update_and_legacy_edits(client, authenticated_trainer, db_session):
    def assign_ids():
        for model in db_session.add_all.call_args.args[0]:
            model.id = uuid4()

    db_session.commit.side_effect = assign_ids
    with patch(
        "app.db.exercises.resolve_configuration",
        new=AsyncMock(return_value=ExerciseConfiguration([], [], [])),
    ):
        response = client.post("/exercises", json=payload(**MEDIA))
        assert response.status_code == 201
        assert {field: response.json()[field] for field in MEDIA} == MEDIA
        exercise, configuration = db_session.add_all.call_args.args[0]
        with patch(
            "app.db.exercises.get_private_for_trainer",
            new=AsyncMock(return_value=(exercise, configuration)),
        ):
            db_session.commit.side_effect = None
            legacy = client.put(f"/exercises/{exercise.id}", json=payload())
            assert legacy.status_code == 200
            assert {field: legacy.json()[field] for field in MEDIA} == MEDIA
            cleared = client.put(
                f"/exercises/{exercise.id}",
                json=payload(
                    image_url=None,
                    animation_url=None,
                    image_url_light=None,
                    animation_url_light=None,
                ),
            )
            assert cleared.status_code == 200
            assert all(cleared.json()[field] is None for field in MEDIA)


@pytest.mark.parametrize("field", MEDIA)
def test_media_url_validation(client, authenticated_trainer, field):
    response = client.post("/exercises", json=payload(**{field: "not-a-url"}))
    assert response.status_code == 422


def test_list_serializes_both_themes_for_private_and_global(
    client, authenticated_trainer
):
    items = [
        ListedExercise(
            id=uuid4(),
            owner_user_id=uuid4(),
            scope=scope,
            name="Ap chagi",
            description="Description",
            min_age=1,
            max_age=99,
            min_participants=1,
            max_participants=99,
            duration_minutes=10,
            status=TrainerExerciseStatus.ACTIVE,
            equipment_requirement_mode="ALL",
            physical_difficulty=3,
            technical_difficulty=3,
            upper_body_load=3,
            lower_body_load=3,
            core_load=3,
            version_id=None,
            **MEDIA,
        )
        for scope in (ExerciseScope.PRIVATE, ExerciseScope.GLOBAL)
    ]
    with (
        patch(
            "app.db.exercises.list_available_to_trainer",
            new=AsyncMock(return_value=ExercisePage(items, 2)),
        ),
        patch(
            "app.db.exercises.list_configurations",
            new=AsyncMock(
                return_value={
                    item.id: ExerciseConfiguration([], [], []) for item in items
                }
            ),
        ),
    ):
        response = client.get("/exercises")
    assert response.status_code == 200
    for item in response.json()["items"]:
        assert {field: item[field] for field in MEDIA} == MEDIA
