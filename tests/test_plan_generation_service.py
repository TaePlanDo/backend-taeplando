"""Coverage for asynchronous generation runner terminal states."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch
from uuid import UUID

from app.services import plan_generation_service
from app.services.plan_generation_strategies import NoCandidateForSchemaPositionError

JOB_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
PLAN_ID = UUID("1ac590e1-2a46-4cb7-8944-803e364cc46b")


@asynccontextmanager
async def _session_context(session):
    yield session


def _factory(session):
    return lambda: _session_context(session)


def _job():
    return SimpleNamespace(
        id=JOB_ID,
        deadline_at=datetime.now(UTC) + timedelta(seconds=10),
    )


def test_generation_context_contains_all_form_and_group_fitness_inputs() -> None:
    """Fitness and evolution receive request values plus the current group profile."""
    parameters = plan_generation_service.PlanGenerationParameters(
        training_group_id=PLAN_ID,
        participant_count=12,
        available_equipment_ids=[
            UUID("2ac590e1-2a46-4cb7-8944-803e364cc46b"),
            UUID("1ac590e1-2a46-4cb7-8944-803e364cc46b"),
        ],
        training_type_id=UUID("3ac590e1-2a46-4cb7-8944-803e364cc46b"),
    )
    group = SimpleNamespace(
        id=PLAN_ID,
        name="Jaworzyna gr. 1",
        min_age=7,
        max_age=14,
        duration_minutes=60,
        schema_items=[],
    )
    job = SimpleNamespace(id=JOB_ID, deadline_at=datetime(2026, 11, 8, tzinfo=UTC))

    context = plan_generation_service._generation_context(job, group, parameters, [])

    assert context.participant_count == 12
    assert context.available_equipment_ids == tuple(
        sorted(parameters.available_equipment_ids)
    )
    assert context.preferred_training_type_id == parameters.training_type_id
    assert context.training_group_id == PLAN_ID
    assert context.training_group_name == "Jaworzyna gr. 1"
    assert (context.group_min_age, context.group_max_age) == (7, 14)
    assert context.group_duration_minutes == 60


def test_runner_marks_a_persisted_plan_as_succeeded() -> None:
    """Runner owns persistence and success status, not the generation strategy."""

    session = AsyncMock()
    job = _job()
    with (
        patch(
            "app.services.plan_generation_service.get_session_factory",
            return_value=_factory(session),
        ),
        patch(
            "app.services.plan_generation_service.jobs_db.claim",
            new=AsyncMock(return_value=job),
        ),
        patch(
            "app.services.plan_generation_service._generate_plan",
            new=AsyncMock(return_value=SimpleNamespace(id=PLAN_ID)),
        ) as generate_plan,
        patch(
            "app.services.plan_generation_service.jobs_db.mark_succeeded",
            new=AsyncMock(),
        ) as mark_succeeded,
    ):
        asyncio.run(plan_generation_service.run(JOB_ID))

    generate_plan.assert_awaited_once_with(session, job, strategy=ANY)
    mark_succeeded.assert_awaited_once_with(session, JOB_ID, PLAN_ID)


def test_runner_marks_a_late_success_as_timed_out() -> None:
    """A plan flushed after the deadline is rolled back and never becomes success."""

    session = AsyncMock()
    with (
        patch(
            "app.services.plan_generation_service.get_session_factory",
            return_value=_factory(session),
        ),
        patch(
            "app.services.plan_generation_service.jobs_db.claim",
            new=AsyncMock(return_value=_job()),
        ),
        patch(
            "app.services.plan_generation_service._generate_plan",
            new=AsyncMock(return_value=SimpleNamespace(id=PLAN_ID)),
        ),
        patch(
            "app.services.plan_generation_service.jobs_db.mark_succeeded",
            new=AsyncMock(return_value=False),
        ) as mark_succeeded,
        patch(
            "app.services.plan_generation_service.jobs_db.mark_timed_out",
            new=AsyncMock(),
        ) as mark_timed_out,
    ):
        asyncio.run(plan_generation_service.run(JOB_ID))

    mark_succeeded.assert_awaited_once_with(session, JOB_ID, PLAN_ID)
    mark_timed_out.assert_awaited_once_with(session, JOB_ID)


def test_runner_marks_missing_candidates_as_a_failed_job() -> None:
    """A typed strategy error becomes a pollable terminal failure."""

    session = AsyncMock()
    with (
        patch(
            "app.services.plan_generation_service.get_session_factory",
            return_value=_factory(session),
        ),
        patch(
            "app.services.plan_generation_service.jobs_db.claim",
            new=AsyncMock(return_value=_job()),
        ),
        patch(
            "app.services.plan_generation_service._generate_plan",
            new=AsyncMock(side_effect=NoCandidateForSchemaPositionError(3)),
        ),
        patch(
            "app.services.plan_generation_service.jobs_db.mark_failed",
            new=AsyncMock(),
        ) as mark_failed,
    ):
        asyncio.run(plan_generation_service.run(JOB_ID))

    session.rollback.assert_awaited_once()
    mark_failed.assert_awaited_once_with(
        session,
        JOB_ID,
        code="NO_CANDIDATE",
        message="No exercise can fill schema position 3",
    )


def test_runner_marks_a_timed_out_generation() -> None:
    """A timeout never exposes a partially persisted plan as successful."""

    session = AsyncMock()
    with (
        patch(
            "app.services.plan_generation_service.get_session_factory",
            return_value=_factory(session),
        ),
        patch(
            "app.services.plan_generation_service.jobs_db.claim",
            new=AsyncMock(return_value=_job()),
        ),
        patch(
            "app.services.plan_generation_service._generate_plan",
            new=AsyncMock(side_effect=TimeoutError),
        ),
        patch(
            "app.services.plan_generation_service.jobs_db.mark_timed_out",
            new=AsyncMock(),
        ) as mark_timed_out,
    ):
        asyncio.run(plan_generation_service.run(JOB_ID))

    mark_timed_out.assert_awaited_once_with(session, JOB_ID)
