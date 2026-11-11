"""Coverage for trainer saved-plan list, detail, filters, and delete."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.db import training_plans as training_plans_db
from app.db.training_plans import PlanPage
from app.models.training import TrainingPlan, TrainingPlanExercise
from app.schemas.common import PaginatedResponse
from app.schemas.exercises import CatalogReference, TrainingSegmentResponse
from app.schemas.training_plans import (
    EMPTY_TRAINING_PLAN_LIST_FILTERS,
    PlanDetail,
    PlanExerciseResponse,
    PlanListItem,
    PlanSchemaSnapshotItem,
    TrainingPlanListFilters,
)
from app.services import training_plan_service
from app.services.training_plan_service import PlanNotFoundError
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


def _catalog_snapshot(
    item_id: UUID = EQUIPMENT_ID, *, name: str = "Tarcze"
) -> list[dict[str, str]]:
    return [{"id": str(item_id), "name": name}]


def _schema_snapshot() -> list[dict[str, object]]:
    return [
        {
            "position": 1,
            "segment_id": 3,
            "code": "MAIN",
            "name": "Ćwiczenia",
            "percentage": 100,
        }
    ]


def _plan_list_item(
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


def _plan_detail() -> PlanDetail:
    base = _plan_list_item()
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


def _orm_plan(
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
        available_equipment_snapshot=_catalog_snapshot(),
        training_types_snapshot=_catalog_snapshot(TRAINING_TYPE_ID, name="Kata"),
        schema_snapshot=_schema_snapshot(),
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
                equipment_snapshot=_catalog_snapshot(),
                training_types_snapshot=_catalog_snapshot(
                    TRAINING_TYPE_ID, name="Kata"
                ),
                segments_snapshot=[{"id": 3, "code": "MAIN", "name": "Ćwiczenia"}],
            ),
        ]
    else:
        plan.exercises = []
    return plan


def test_list_plans_requires_authentication(client) -> None:
    """Saved plans are trainer-scoped and reject anonymous access."""
    response = client.get("/training-plans")

    assert response.status_code == 401


def test_list_plans_returns_one_page_newest_first(
    client, authenticated_trainer
) -> None:
    """The list endpoint returns the service page without inventing sort options."""
    newer = _plan_list_item()
    older = _plan_list_item(plan_id=OLDER_PLAN_ID, generated_at=OLDER_GENERATED_AT)
    page = PaginatedResponse(
        items=[newer, older],
        total=2,
        page=1,
        page_size=20,
        total_pages=1,
    )
    with patch(
        "app.api.training_plans.training_plan_service.list_plans",
        new=AsyncMock(return_value=page),
    ) as list_plans:
        response = client.get("/training-plans")

    assert response.status_code == 200
    assert response.json() == {
        "items": [item.model_dump(mode="json") for item in page.items],
        "total": 2,
        "page": 1,
        "page_size": 20,
        "total_pages": 1,
    }
    list_plans.assert_awaited_once_with(
        ANY,
        TRAINER_ID,
        filters=EMPTY_TRAINING_PLAN_LIST_FILTERS,
        page=1,
        page_size=20,
    )


def test_list_plans_forwards_combined_filters(client, authenticated_trainer) -> None:
    """Parse and forward every supported list filter to the service."""
    empty = PaginatedResponse(items=[], total=0, page=1, page_size=20, total_pages=1)
    with patch(
        "app.api.training_plans.training_plan_service.list_plans",
        new=AsyncMock(return_value=empty),
    ) as list_plans:
        response = client.get(
            "/training-plans"
            f"?name=m%C5%82odzie%C5%BC"
            f"&min_age=6&max_age=16"
            f"&min_participants=8&max_participants=20"
            f"&min_duration=45&max_duration=90"
            f"&equipment_ids={EQUIPMENT_ID},{OTHER_EQUIPMENT_ID}"
            f"&training_type_ids={TRAINING_TYPE_ID}"
            f"&training_group_ids={GROUP_ID},{OTHER_GROUP_ID}"
            f"&page=1&page_size=2"
        )

    assert response.status_code == 200
    list_plans.assert_awaited_once_with(
        ANY,
        TRAINER_ID,
        filters=TrainingPlanListFilters(
            name="młodzież",
            min_age=6,
            max_age=16,
            min_participants=8,
            max_participants=20,
            min_duration=45,
            max_duration=90,
            equipment_ids=[EQUIPMENT_ID, OTHER_EQUIPMENT_ID],
            training_type_ids=[TRAINING_TYPE_ID],
            training_group_ids=[GROUP_ID, OTHER_GROUP_ID],
        ),
        page=1,
        page_size=2,
    )


@pytest.mark.parametrize(
    "query",
    [
        "min_age=15&max_age=14",
        "min_participants=10&max_participants=2",
        "min_duration=90&max_duration=45",
    ],
)
def test_list_plans_rejects_inverted_ranges(
    client, authenticated_trainer, query: str
) -> None:
    """Reject impossible inclusive filter ranges before hitting the service."""
    response = client.get(f"/training-plans?{query}")

    assert response.status_code == 422


def test_list_plans_rejects_invalid_equipment_csv(
    client, authenticated_trainer
) -> None:
    """Reject malformed UUID lists instead of silently ignoring them."""
    response = client.get("/training-plans?equipment_ids=not-a-uuid")

    assert response.status_code == 422


def test_get_plan_returns_detail(client, authenticated_trainer) -> None:
    """Detail includes the ordered exercise snapshots for one owned plan."""
    detail = _plan_detail()
    with patch(
        "app.api.training_plans.training_plan_service.get_plan",
        new=AsyncMock(return_value=detail),
    ) as get_plan:
        response = client.get(f"/training-plans/{PLAN_ID}")

    assert response.status_code == 200
    assert response.json() == detail.model_dump(mode="json")
    get_plan.assert_awaited_once_with(ANY, TRAINER_ID, PLAN_ID)


def test_get_plan_returns_not_found_for_foreign_or_missing(
    client, authenticated_trainer
) -> None:
    """Missing and foreign plans share one 404 response."""
    with patch(
        "app.api.training_plans.training_plan_service.get_plan",
        new=AsyncMock(side_effect=PlanNotFoundError),
    ):
        response = client.get(f"/training-plans/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Plan not found"}


def test_delete_plan_returns_no_content(client, authenticated_trainer) -> None:
    """Delete succeeds with an empty 204 body."""
    with patch(
        "app.api.training_plans.training_plan_service.delete_plan",
        new=AsyncMock(),
    ) as delete_plan:
        response = client.delete(f"/training-plans/{PLAN_ID}")

    assert response.status_code == 204
    assert response.content == b""
    delete_plan.assert_awaited_once_with(ANY, TRAINER_ID, PLAN_ID)


def test_delete_plan_returns_not_found_for_foreign_or_missing(
    client, authenticated_trainer
) -> None:
    """Delete uses the same not-found outcome as get."""
    with patch(
        "app.api.training_plans.training_plan_service.delete_plan",
        new=AsyncMock(side_effect=PlanNotFoundError),
    ):
        response = client.delete(f"/training-plans/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Plan not found"}


def test_list_plans_service_maps_items_and_forwards_pagination() -> None:
    """The service maps ORM rows and preserves the requested page metadata."""
    session = AsyncMock()
    plan = _orm_plan()
    with patch(
        "app.services.training_plan_service.training_plans_db.list_for_trainer",
        new=AsyncMock(return_value=PlanPage(items=[plan], total=25)),
    ) as list_for_trainer:
        page = asyncio.run(
            training_plan_service.list_plans(
                session,
                TRAINER_ID,
                filters=EMPTY_TRAINING_PLAN_LIST_FILTERS,
                page=3,
                page_size=10,
            )
        )

    assert page == PaginatedResponse(
        items=[_plan_list_item()],
        total=25,
        page=3,
        page_size=10,
        total_pages=3,
    )
    list_for_trainer.assert_awaited_once_with(
        session,
        TRAINER_ID,
        filters=EMPTY_TRAINING_PLAN_LIST_FILTERS,
        offset=20,
        limit=10,
    )


def test_get_plan_service_orders_exercises_by_position() -> None:
    """Detail responses sort plan exercises by position ascending."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ):
        detail = asyncio.run(
            training_plan_service.get_plan(session, TRAINER_ID, PLAN_ID)
        )

    assert [exercise.position for exercise in detail.exercises] == [1, 2]
    assert detail.exercises[0].name_snapshot == "Ap chagi"
    assert detail.exercises[0].image_url_snapshot == "https://example.com/ap-chagi.png"
    assert detail.exercises[0].physical_difficulty_snapshot == 3
    assert detail.exercises[0].lower_body_load_snapshot == 5
    assert detail.exercises[1].name_snapshot == "Dollyo chagi"
    assert detail.exercises[1].image_url_snapshot is None


def test_get_plan_service_raises_for_missing_plan() -> None:
    """Service callers receive PlanNotFoundError for absent ownership."""
    session = AsyncMock()
    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(PlanNotFoundError):
            asyncio.run(training_plan_service.get_plan(session, TRAINER_ID, PLAN_ID))


def test_delete_plan_service_deletes_owned_plan() -> None:
    """Delete reuses the owned-plan loader, removes the plan, and commits."""
    session = AsyncMock()
    plan = _orm_plan()
    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ):
        asyncio.run(training_plan_service.delete_plan(session, TRAINER_ID, PLAN_ID))

    session.delete.assert_awaited_once_with(plan)
    session.commit.assert_awaited_once()


def test_delete_plan_service_raises_for_missing_plan() -> None:
    """Delete refuses missing or foreign plans without writing."""
    session = AsyncMock()
    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(PlanNotFoundError):
            asyncio.run(training_plan_service.delete_plan(session, TRAINER_ID, PLAN_ID))

    session.delete.assert_not_called()
    session.commit.assert_not_called()


def test_list_recent_group_exercise_ids_returns_newest_first_tuples() -> None:
    """Plan ids then projected exercise ids, grouped newest-first."""
    newer_plan_id = PLAN_ID
    older_plan_id = OLDER_PLAN_ID
    session = AsyncMock()
    session.scalars = AsyncMock(return_value=[newer_plan_id, older_plan_id])
    rows = MagicMock()
    rows.all.return_value = [
        (newer_plan_id, TRAINER_EXERCISE_ID),
        (older_plan_id, EXERCISE_ID),
        (older_plan_id, EQUIPMENT_ID),
    ]
    session.execute = AsyncMock(return_value=rows)

    plans = asyncio.run(
        training_plans_db.list_recent_group_exercise_ids(
            session, TRAINER_ID, GROUP_ID, limit=3
        )
    )

    assert plans == [
        (TRAINER_EXERCISE_ID,),
        (EXERCISE_ID, EQUIPMENT_ID),
    ]
    plan_ids_sql = str(session.scalars.await_args.args[0]).lower()
    assert "training_group_id" in plan_ids_sql
    assert "order by training_plans.generated_at desc" in plan_ids_sql
    assert "limit" in plan_ids_sql
    exercises_sql = str(session.execute.await_args.args[0]).lower()
    assert "trainer_exercise_id" in exercises_sql
    assert "training_plan_id" in exercises_sql


def test_list_for_trainer_returns_page_and_total_in_one_query() -> None:
    """A single statement returns both the page and the windowed total."""
    session = AsyncMock()
    plan = _orm_plan()
    result = MagicMock()
    result.all.return_value = [(plan, 7)]
    session.execute = AsyncMock(return_value=result)

    page = asyncio.run(
        training_plans_db.list_for_trainer(
            session,
            TRAINER_ID,
            filters=EMPTY_TRAINING_PLAN_LIST_FILTERS,
            offset=0,
            limit=20,
        )
    )

    assert page.items == [plan]
    assert page.total == 7
    session.execute.assert_awaited_once()
    statement = str(session.execute.await_args.args[0]).lower()
    assert "over ()" in statement
    assert "order by training_plans.generated_at desc" in statement
    assert "training_plans.id desc" in statement


def test_list_for_trainer_empty_first_page_reports_zero_total_without_recount() -> None:
    """An empty first page means nothing matches, so no second query is needed."""
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    page = asyncio.run(
        training_plans_db.list_for_trainer(
            session, TRAINER_ID, filters=EMPTY_TRAINING_PLAN_LIST_FILTERS
        )
    )

    assert page.items == []
    assert page.total == 0
    session.execute.assert_awaited_once()


def test_list_for_trainer_out_of_range_page_still_reports_the_real_total() -> None:
    """A page past the end has no rows to carry the window count, so recount."""
    session = AsyncMock()
    empty_page = MagicMock()
    empty_page.all.return_value = []
    count = MagicMock()
    count.scalar_one.return_value = 5
    session.execute = AsyncMock(side_effect=[empty_page, count])

    page = asyncio.run(
        training_plans_db.list_for_trainer(
            session,
            TRAINER_ID,
            filters=EMPTY_TRAINING_PLAN_LIST_FILTERS,
            offset=16,
            limit=2,
        )
    )

    assert page.items == []
    assert page.total == 5
    assert session.execute.await_count == 2


def test_list_for_trainer_applies_all_filter_predicates() -> None:
    """Compile the list query and assert every filter reaches SQL."""
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    asyncio.run(
        training_plans_db.list_for_trainer(
            session,
            TRAINER_ID,
            filters=TrainingPlanListFilters(
                name="młodzież",
                min_age=6,
                max_age=16,
                min_participants=8,
                max_participants=20,
                min_duration=45,
                max_duration=90,
                equipment_ids=[EQUIPMENT_ID, OTHER_EQUIPMENT_ID],
                training_type_ids=[TRAINING_TYPE_ID],
                training_group_ids=[GROUP_ID],
            ),
            offset=0,
            limit=2,
        )
    )

    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled).lower()
    params = " ".join(str(value).lower() for value in compiled.params.values())
    assert "training_plans.trainer_id" in sql
    assert "training_plans.name ilike" in sql
    assert "group_max_age_snapshot" in sql
    assert "group_min_age_snapshot" in sql
    assert "participant_count" in sql
    assert "training_duration_snapshot" in sql
    assert "available_equipment_snapshot" in sql
    assert "training_types_snapshot" in sql
    assert "training_group_id" in sql
    assert "limit" in sql
    assert "6" in params
    assert "16" in params
    assert "8" in params
    assert "20" in params
    assert "45" in params
    assert "90" in params
    assert str(EQUIPMENT_ID).lower() in params
    assert str(OTHER_EQUIPMENT_ID).lower() in params
    assert str(TRAINING_TYPE_ID).lower() in params
    assert str(GROUP_ID).lower() in params


def test_get_for_trainer_scopes_by_owner() -> None:
    """Detail lookup always constrains both plan id and trainer id."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    result = MagicMock()
    result.scalar_one_or_none.return_value = plan
    session.execute = AsyncMock(return_value=result)

    found = asyncio.run(training_plans_db.get_for_trainer(session, TRAINER_ID, PLAN_ID))

    assert found is plan
    statement = str(session.execute.await_args.args[0]).lower()
    assert "training_plans.id" in statement
    assert "training_plans.trainer_id" in statement
