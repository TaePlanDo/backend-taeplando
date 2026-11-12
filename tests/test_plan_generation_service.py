"""Coverage for asynchronous generation runner terminal states."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.models.enums import EquipmentRequirementMode
from app.schemas.plan_generation import PlanGenerationParameters
from app.services import plan_generation_service
from app.services.plan_generation_domain import (
    PlanExerciseCandidate,
    PlanExerciseSelection,
    PlanIndividual,
)
from app.services.plan_generation_errors import NoCandidateForSchemaPositionError

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


def test_generation_contexts_isolate_each_segment_and_keep_fitness_inputs() -> None:
    """Every algorithm receives one segment plus all form and group metadata."""
    parameters = PlanGenerationParameters(
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
        schema_items=[
            SimpleNamespace(position=2, segment_id=2, percentage=Decimal("25")),
            SimpleNamespace(position=1, segment_id=1, percentage=Decimal("75")),
        ],
    )
    job = SimpleNamespace(id=JOB_ID, deadline_at=datetime(2026, 11, 8, tzinfo=UTC))

    first_only = SimpleNamespace(default_duration_minutes=10, segment_ids=(1,))
    shared = SimpleNamespace(default_duration_minutes=10, segment_ids=(1, 2))
    second_only = SimpleNamespace(default_duration_minutes=10, segment_ids=(2,))
    contexts = plan_generation_service._generation_contexts(
        job, group, parameters, (first_only, shared, second_only)
    )

    assert [context.segment.position for context in contexts] == [1, 2]
    first, second = contexts
    assert first.participant_count == 12
    assert first.available_equipment_ids == tuple(
        sorted(parameters.available_equipment_ids)
    )
    assert first.preferred_training_type_id == parameters.training_type_id
    assert first.training_group_id == PLAN_ID
    assert first.training_group_name == "Jaworzyna gr. 1"
    assert (first.group_min_age, first.group_max_age) == (7, 14)
    assert first.group_duration_minutes == 60
    assert (first.segment_duration_minutes, second.segment_duration_minutes) == (45, 15)
    assert first.candidates == (first_only, shared)
    assert second.candidates == (shared, second_only)
    assert first.random_seed != second.random_seed


def test_generation_contexts_reject_a_segment_without_candidates() -> None:
    """Every independently generated segment must have a non-empty candidate pool."""
    parameters = PlanGenerationParameters(
        training_group_id=PLAN_ID,
        participant_count=12,
        available_equipment_ids=[],
    )
    group = SimpleNamespace(
        id=PLAN_ID,
        name="Jaworzyna gr. 1",
        min_age=7,
        max_age=14,
        duration_minutes=60,
        schema_items=[
            SimpleNamespace(position=1, segment_id=1, percentage=Decimal("50")),
            SimpleNamespace(position=2, segment_id=2, percentage=Decimal("50")),
        ],
    )
    job = SimpleNamespace(id=JOB_ID, deadline_at=datetime(2026, 11, 8, tzinfo=UTC))

    with pytest.raises(NoCandidateForSchemaPositionError, match="2"):
        plan_generation_service._generation_contexts(
            job,
            group,
            parameters,
            (
                SimpleNamespace(default_duration_minutes=10, segment_ids=(1,)),
                SimpleNamespace(default_duration_minutes=0, segment_ids=(2,)),
            ),
        )


def test_persisted_selection_uses_its_allocated_duration() -> None:
    """The generated plan snapshots the duration gene, not the source default."""
    candidate = PlanExerciseCandidate(
        trainer_exercise_id=PLAN_ID,
        exercise_id=PLAN_ID,
        exercise_version_id=None,
        min_age=7,
        max_age=14,
        min_participants=1,
        max_participants=20,
        default_duration_minutes=10,
        equipment_requirement_mode=EquipmentRequirementMode.ALL,
        equipment_ids=(),
        training_type_ids=(),
        segment_ids=(),
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
        recent_usage_distance=4,
    )
    selection = PlanExerciseSelection(
        schema_position=1,
        candidate=candidate,
        allocated_duration_minutes=7,
    )
    source = SimpleNamespace(
        id=candidate.trainer_exercise_id,
        exercise_id=candidate.exercise_id,
        source_version_id=None,
        exercise=SimpleNamespace(name="Ćwiczenie", description="Opis", image_url=None),
        min_age=7,
        max_age=14,
        min_participants=1,
        max_participants=20,
        duration_minutes=10,
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
        equipment=[],
        training_types=[],
        segments=[],
        source_version=None,
    )

    plan_exercise = plan_generation_service._plan_exercise(1, selection, source)

    assert plan_exercise.duration_minutes_snapshot == 7


def test_generate_plan_runs_one_strategy_call_per_schema_segment() -> None:
    """The runner dispatches isolated segment contexts before one final persist."""
    session = AsyncMock()
    group = SimpleNamespace(
        id=PLAN_ID,
        name="Jaworzyna gr. 1",
        min_age=7,
        max_age=14,
        duration_minutes=60,
        schema_items=[
            SimpleNamespace(position=2, segment_id=2, percentage=Decimal("25")),
            SimpleNamespace(position=1, segment_id=1, percentage=Decimal("75")),
        ],
    )
    job = SimpleNamespace(
        id=JOB_ID,
        trainer_id=PLAN_ID,
        training_group_id=PLAN_ID,
        participant_count=12,
        available_equipment_ids=[],
        training_type_id=None,
        deadline_at=datetime(2026, 11, 8, tzinfo=UTC),
    )
    first = PlanIndividual(selections=())
    second = PlanIndividual(selections=())
    persisted_plan = SimpleNamespace(id=PLAN_ID)
    with (
        patch(
            "app.services.plan_generation_service.plan_generation_parameters_service.validate_parameters",
            new=AsyncMock(return_value=SimpleNamespace(group=group)),
        ),
        patch(
            "app.services.plan_generation_service.plan_generation_candidates_service.prepare_candidates",
            new=AsyncMock(
                return_value=(
                    SimpleNamespace(default_duration_minutes=10, segment_ids=(1, 2)),
                )
            ),
        ),
        patch(
            "app.services.plan_generation_service._generate_segment",
            new=AsyncMock(side_effect=[first, second]),
        ) as generate_segment,
        patch(
            "app.services.plan_generation_service._persist_plan",
            new=AsyncMock(return_value=persisted_plan),
        ) as persist_plan,
    ):
        result = asyncio.run(
            plan_generation_service._generate_plan(
                session,
                job,
                best=plan_generation_service.BestSoFar(),
                strategy_factory=lambda _best: object(),
            )
        )

    assert result is persisted_plan
    assert [
        call.args[2].segment.position for call in generate_segment.await_args_list
    ] == [
        1,
        2,
    ]
    persist_plan.assert_awaited_once()


def test_generate_segment_creates_an_independent_strategy_instance() -> None:
    """Segment execution does not share mutable algorithm state with another run."""
    context = MagicMock()
    context.segment.position = 1
    context.segment_duration_minutes = 30
    context.candidates = ()
    context.random_seed = 7
    population = MagicMock()
    generated = PlanIndividual(selections=())
    best = plan_generation_service.BestSoFar()
    strategy = MagicMock()
    strategy.generate.return_value = generated
    strategy_factory = MagicMock(return_value=strategy)

    with patch(
        "app.services.plan_generation_service.build_initial_population",
        return_value=population,
    ) as build_population:
        result = asyncio.run(
            plan_generation_service._generate_segment(strategy_factory, best, context)
        )

    assert result is generated
    build_population.assert_called_once_with(context)
    strategy_factory.assert_called_once_with(best)
    strategy.generate.assert_called_once_with(context, population)


def test_merge_segment_individuals_restores_schema_order() -> None:
    """Parallel segment results become one persistable plan in schema order."""
    candidate = PlanExerciseCandidate(
        trainer_exercise_id=PLAN_ID,
        exercise_id=PLAN_ID,
        exercise_version_id=None,
        min_age=7,
        max_age=14,
        min_participants=1,
        max_participants=20,
        default_duration_minutes=10,
        equipment_requirement_mode=EquipmentRequirementMode.ALL,
        equipment_ids=(),
        training_type_ids=(),
        segment_ids=(1, 2),
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
        recent_usage_distance=4,
    )

    def selection(position: int) -> PlanExerciseSelection:
        return PlanExerciseSelection(
            schema_position=position,
            candidate=candidate,
            allocated_duration_minutes=10,
        )

    merged = plan_generation_service._merge_segment_individuals(
        (
            PlanIndividual(selections=(selection(2),)),
            PlanIndividual(selections=(selection(1),)),
        )
    )

    assert [item.schema_position for item in merged.selections] == [1, 2]


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

    generate_plan.assert_awaited_once_with(
        session,
        job,
        best=ANY,
        strategy_factory=plan_generation_service.GeneticPlanGenerationStrategy,
    )
    mark_succeeded.assert_awaited_once_with(session, JOB_ID, PLAN_ID)


def test_runner_marks_a_late_success_without_salvage_as_timed_out() -> None:
    """Without a salvaged BestSoFar snapshot, a late success becomes timed out."""

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
            "app.services.plan_generation_service._salvage_best_plan",
            new=AsyncMock(return_value=False),
        ) as salvage,
        patch(
            "app.services.plan_generation_service.jobs_db.mark_timed_out",
            new=AsyncMock(),
        ) as mark_timed_out,
    ):
        asyncio.run(plan_generation_service.run(JOB_ID))

    mark_succeeded.assert_awaited_once_with(session, JOB_ID, PLAN_ID)
    salvage.assert_awaited_once()
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


def test_runner_marks_a_timed_out_generation_without_salvage() -> None:
    """A timeout without a valid BestSoFar snapshot stays timed out."""

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
            "app.services.plan_generation_service._salvage_best_plan",
            new=AsyncMock(return_value=False),
        ) as salvage,
        patch(
            "app.services.plan_generation_service.jobs_db.mark_timed_out",
            new=AsyncMock(),
        ) as mark_timed_out,
    ):
        asyncio.run(plan_generation_service.run(JOB_ID))

    salvage.assert_awaited_once()
    mark_timed_out.assert_awaited_once_with(session, JOB_ID)


def test_runner_salvages_a_valid_best_after_timeout() -> None:
    """A hard cut still succeeds when BestSoFar holds a complete valid plan."""

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
            "app.services.plan_generation_service._salvage_best_plan",
            new=AsyncMock(return_value=True),
        ) as salvage,
        patch(
            "app.services.plan_generation_service.jobs_db.mark_timed_out",
            new=AsyncMock(),
        ) as mark_timed_out,
    ):
        asyncio.run(plan_generation_service.run(JOB_ID))

    salvage.assert_awaited_once()
    mark_timed_out.assert_not_awaited()
