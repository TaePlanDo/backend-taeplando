"""Shared builders for saved training-plan API and service tests."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.models.training import TrainingPlan, TrainingPlanExercise
from app.schemas.exercises import CatalogReference, TrainingSegmentResponse
from app.schemas.training_plans import (
    PlanDetail,
    PlanExerciseResponse,
    PlanListItem,
    PlanSchemaSnapshotItem,
)
from constants import TRAINER_ID

GROUP_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
OTHER_GROUP_ID = UUID("1ac590e1-2a46-4cb7-8944-803e364cc46b")
PLAN_ID = UUID("88fa8385-5b07-4346-9ddb-02806890ae4b")
OLDER_PLAN_ID = UUID("98fa8385-5b07-4346-9ddb-02806890ae4b")
PLAN_EXERCISE_ID = UUID("a8fa8385-5b07-4346-9ddb-02806890ae4b")
TRAINER_EXERCISE_ID = UUID("b8fa8385-5b07-4346-9ddb-02806890ae4b")
EXERCISE_ID = UUID("c8fa8385-5b07-4346-9ddb-02806890ae4b")
EXERCISE_VERSION_ID = UUID("d8fa8385-5b07-4346-9ddb-02806890ae4b")
EQUIPMENT_ID = UUID("410327de-b35a-4dcf-8b99-5249e159ce06")
OTHER_EQUIPMENT_ID = UUID("510327de-b35a-4dcf-8b99-5249e159ce06")
TRAINING_TYPE_ID = UUID("2894e3b8-d31a-42a3-89df-fbff1dfb1fb2")
OTHER_TRAINING_TYPE_ID = UUID("3894e3b8-d31a-42a3-89df-fbff1dfb1fb2")
GENERATED_AT = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
OLDER_GENERATED_AT = GENERATED_AT - timedelta(days=1)


def catalog_snapshot(
    item_id: UUID = EQUIPMENT_ID, *, name: str = "Tarcze"
) -> list[dict[str, str]]:
    return [{"id": str(item_id), "name": name}]


def schema_snapshot() -> list[dict[str, object]]:
    return [
        {
            "position": 1,
            "segment_id": 3,
            "code": "MAIN",
            "name": "Ćwiczenia",
            "percentage": 100,
        }
    ]


def plan_list_item(
    *,
    plan_id: UUID = PLAN_ID,
    group_id: UUID = GROUP_ID,
    generated_at: datetime = GENERATED_AT,
) -> PlanListItem:
    return PlanListItem(
        id=plan_id,
        training_group_id=group_id,
        name="Plan treningowy – Młodzież",
        participant_count=12,
        group_name_snapshot="Młodzież",
        group_min_age_snapshot=7,
        group_max_age_snapshot=14,
        training_duration_snapshot=60,
        available_equipment_snapshot=[CatalogReference(id=EQUIPMENT_ID, name="Tarcze")],
        training_types_snapshot=[CatalogReference(id=TRAINING_TYPE_ID, name="Kata")],
        schema_snapshot=[
            PlanSchemaSnapshotItem(
                position=1,
                segment_id=3,
                code="MAIN",
                name="Ćwiczenia",
                percentage=100.0,
            )
        ],
        generated_at=generated_at,
    )


def plan_detail() -> PlanDetail:
    base = plan_list_item()
    return PlanDetail(
        **base.model_dump(),
        exercises=[
            PlanExerciseResponse(
                id=PLAN_EXERCISE_ID,
                trainer_exercise_id=TRAINER_EXERCISE_ID,
                exercise_id=EXERCISE_ID,
                exercise_version_id=EXERCISE_VERSION_ID,
                position=1,
                schema_position=1,
                name_snapshot="Ap chagi",
                description_snapshot="Kopnięcie frontalne.",
                image_url_snapshot="https://example.com/ap-chagi.png",
                animation_url_snapshot="https://example.com/ap-chagi-animation.webp",
                image_url_light_snapshot="https://example.com/ap-chagi-light.png",
                animation_url_light_snapshot=(
                    "https://example.com/ap-chagi-animation-light.webp"
                ),
                min_age_snapshot=7,
                max_age_snapshot=14,
                min_participants_snapshot=2,
                max_participants_snapshot=20,
                duration_minutes_snapshot=10,
                physical_difficulty_snapshot=3,
                technical_difficulty_snapshot=4,
                upper_body_load_snapshot=2,
                lower_body_load_snapshot=5,
                core_load_snapshot=3,
                equipment_snapshot=[CatalogReference(id=EQUIPMENT_ID, name="Tarcze")],
                training_types_snapshot=[
                    CatalogReference(id=TRAINING_TYPE_ID, name="Kata")
                ],
                segments_snapshot=[
                    TrainingSegmentResponse(id=3, code="MAIN", name="Ćwiczenia")
                ],
            )
        ],
    )


def orm_plan(
    *,
    plan_id: UUID = PLAN_ID,
    group_id: UUID = GROUP_ID,
    generated_at: datetime = GENERATED_AT,
    with_exercises: bool = False,
) -> TrainingPlan:
    plan = TrainingPlan(
        id=plan_id,
        trainer_id=TRAINER_ID,
        training_group_id=group_id,
        participant_count=12,
        name="Plan treningowy – Młodzież",
        group_name_snapshot="Młodzież",
        group_min_age_snapshot=7,
        group_max_age_snapshot=14,
        training_duration_snapshot=60,
        available_equipment_snapshot=catalog_snapshot(),
        training_types_snapshot=catalog_snapshot(TRAINING_TYPE_ID, name="Kata"),
        schema_snapshot=schema_snapshot(),
        generated_at=generated_at,
    )
    if with_exercises:
        plan.exercises = [
            TrainingPlanExercise(
                id=PLAN_EXERCISE_ID,
                training_plan_id=plan_id,
                trainer_exercise_id=TRAINER_EXERCISE_ID,
                exercise_id=EXERCISE_ID,
                exercise_version_id=EXERCISE_VERSION_ID,
                position=2,
                schema_position=1,
                name_snapshot="Dollyo chagi",
                description_snapshot="Kopnięcie okrężne.",
                image_url_snapshot=None,
                animation_url_snapshot=None,
                image_url_light_snapshot=None,
                animation_url_light_snapshot=None,
                min_age_snapshot=8,
                max_age_snapshot=16,
                min_participants_snapshot=2,
                max_participants_snapshot=18,
                duration_minutes_snapshot=8,
                physical_difficulty_snapshot=2,
                technical_difficulty_snapshot=3,
                upper_body_load_snapshot=2,
                lower_body_load_snapshot=4,
                core_load_snapshot=3,
                equipment_snapshot=[],
                training_types_snapshot=[],
                segments_snapshot=[{"id": 3, "code": "MAIN", "name": "Ćwiczenia"}],
            ),
            TrainingPlanExercise(
                id=uuid4(),
                training_plan_id=plan_id,
                trainer_exercise_id=TRAINER_EXERCISE_ID,
                exercise_id=EXERCISE_ID,
                exercise_version_id=None,
                position=1,
                schema_position=1,
                name_snapshot="Ap chagi",
                description_snapshot="Kopnięcie frontalne.",
                image_url_snapshot="https://example.com/ap-chagi.png",
                animation_url_snapshot="https://example.com/ap-chagi-animation.webp",
                image_url_light_snapshot="https://example.com/ap-chagi-light.png",
                animation_url_light_snapshot=(
                    "https://example.com/ap-chagi-animation-light.webp"
                ),
                min_age_snapshot=7,
                max_age_snapshot=14,
                min_participants_snapshot=2,
                max_participants_snapshot=20,
                duration_minutes_snapshot=10,
                physical_difficulty_snapshot=3,
                technical_difficulty_snapshot=4,
                upper_body_load_snapshot=2,
                lower_body_load_snapshot=5,
                core_load_snapshot=3,
                equipment_snapshot=catalog_snapshot(),
                training_types_snapshot=catalog_snapshot(TRAINING_TYPE_ID, name="Kata"),
                segments_snapshot=[{"id": 3, "code": "MAIN", "name": "Ćwiczenia"}],
            ),
        ]
    else:
        plan.exercises = []
    return plan
