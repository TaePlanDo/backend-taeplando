"""Queue, execute, persist, and report asynchronous training-plan generation."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import exercises as exercises_db
from app.db import plan_generation_jobs as jobs_db
from app.db.session import get_session_factory
from app.models.catalogs import Equipment, TrainingType
from app.models.exercises import TrainerExercise
from app.models.plan_generation import PlanGenerationJob
from app.models.training import TrainingGroup, TrainingPlan, TrainingPlanExercise
from app.schemas.plan_generation import (
    PlanGenerationAccepted,
    PlanGenerationParameters,
    PlanGenerationStatusResponse,
)
from app.services import (
    plan_generation_candidates_service,
    plan_generation_parameters_service,
)
from app.services.plan_generation_domain import (
    GenerationContext,
    GenerationSchemaItem,
    PlanExerciseCandidate,
    PlanExerciseSelection,
    PlanIndividual,
)
from app.services.plan_generation_errors import PlanGenerationError
from app.services.plan_generation_population_service import build_initial_population
from app.services.plan_generation_strategies import (
    PlanGenerationStrategy,
    RandomPlanGenerationStrategy,
)


async def enqueue(
    session: AsyncSession, trainer_id: UUID, parameters: PlanGenerationParameters
) -> PlanGenerationAccepted:
    """Persist a validated request and return its public job handle."""
    job = await jobs_db.create(
        session,
        trainer_id,
        training_group_id=parameters.training_group_id,
        participant_count=parameters.participant_count,
        available_equipment_ids=parameters.available_equipment_ids,
        training_type_id=parameters.training_type_id,
        timeout_seconds=get_settings().plan_generation_timeout_seconds,
    )
    return _accepted(job)


async def get_status(
    session: AsyncSession, trainer_id: UUID, job_id: UUID
) -> PlanGenerationStatusResponse | None:
    """Return the current outcome without exposing jobs owned by another trainer."""
    job = await jobs_db.get_for_trainer(session, trainer_id, job_id)
    if job is None:
        return None
    return PlanGenerationStatusResponse(
        **_accepted(job).model_dump(),
        plan_id=job.plan_id,
        error_code=job.error_code,
        error_message=job.error_message,
    )


async def run(job_id: UUID) -> None:
    """Run one queued job after its HTTP response has been sent."""
    async with get_session_factory()() as session:
        job = await jobs_db.claim(session, job_id)
        if job is None:
            return

        try:
            timeout_seconds = max(
                (job.deadline_at - datetime.now(UTC)).total_seconds(), 0
            )
            async with asyncio.timeout(timeout_seconds):
                plan = await _generate_plan(
                    session, job, strategy=RandomPlanGenerationStrategy()
                )
                if not await jobs_db.mark_succeeded(session, job.id, plan.id):
                    await jobs_db.mark_timed_out(session, job.id)
        except TimeoutError:
            await session.rollback()
            await jobs_db.mark_timed_out(session, job_id)
        except PlanGenerationError as exc:
            await session.rollback()
            await _mark_failure(
                session,
                job_id,
                code=exc.error_code,
                message=str(exc),
            )
        except Exception:
            await session.rollback()
            await _mark_failure(
                session,
                job_id,
                code=PlanGenerationError.error_code,
                message="Plan generation failed",
            )


async def _mark_failure(
    session: AsyncSession, job_id: UUID, *, code: str, message: str
) -> None:
    """Record a normal failure, or the timeout that won the terminal-state race."""
    if not await jobs_db.mark_failed(session, job_id, code=code, message=message):
        await jobs_db.mark_timed_out(session, job_id)


async def _generate_plan(
    session: AsyncSession,
    job: PlanGenerationJob,
    *,
    strategy: PlanGenerationStrategy,
) -> TrainingPlan:
    """Build and persist a plan while keeping the strategy free of I/O."""
    parameters = PlanGenerationParameters(
        training_group_id=job.training_group_id,
        participant_count=job.participant_count,
        available_equipment_ids=[UUID(item) for item in job.available_equipment_ids],
        training_type_id=job.training_type_id,
    )
    try:
        validated_input = await plan_generation_parameters_service.validate_parameters(
            session, job.trainer_id, parameters
        )
    except (
        plan_generation_parameters_service.InvalidPlanGenerationParametersError
    ) as exc:
        raise PlanGenerationError(
            "Generation parameters are no longer available"
        ) from exc
    group = validated_input.group

    candidates = await plan_generation_candidates_service.prepare_candidates(
        session, job.trainer_id, group, parameters
    )
    context = _generation_context(job, group, parameters, candidates)
    population = await asyncio.to_thread(build_initial_population, context)
    generated = await asyncio.to_thread(strategy.generate, context, population)
    return await _persist_plan(session, job, validated_input, parameters, generated)


def _generation_context(
    job: PlanGenerationJob,
    group: TrainingGroup,
    parameters: PlanGenerationParameters,
    candidates: list[PlanExerciseCandidate],
) -> GenerationContext:
    """Adapt database-backed preparation into the strategy's immutable contract."""
    schema = tuple(
        GenerationSchemaItem(
            position=item.position,
            segment_id=item.segment_id,
            percentage=item.percentage,
        )
        for item in sorted(group.schema_items, key=lambda item: item.position)
    )
    return GenerationContext(
        participant_count=parameters.participant_count,
        available_equipment_ids=tuple(sorted(parameters.available_equipment_ids)),
        preferred_training_type_id=parameters.training_type_id,
        training_group_id=group.id,
        training_group_name=group.name,
        group_min_age=group.min_age,
        group_max_age=group.max_age,
        group_duration_minutes=group.duration_minutes,
        deadline_at=job.deadline_at,
        schema=schema,
        candidate_pool=plan_generation_candidates_service.build_candidate_pool(
            schema, candidates
        ),
        random_seed=job.id.int,
    )


async def _persist_plan(
    session: AsyncSession,
    job: PlanGenerationJob,
    validated_input: plan_generation_parameters_service.ValidatedPlanGenerationInput,
    parameters: PlanGenerationParameters,
    generated: PlanIndividual,
) -> TrainingPlan:
    """Write immutable plan snapshots from the strategy's selected candidates."""
    group = validated_input.group
    selected_sources = await exercises_db.list_sources_for_generated_plan(
        session,
        job.trainer_id,
        {item.candidate.trainer_exercise_id for item in generated.selections},
    )
    if len(selected_sources) != len(
        {item.candidate.trainer_exercise_id for item in generated.selections}
    ):
        raise PlanGenerationError("A selected exercise is no longer available")

    plan = TrainingPlan(
        trainer_id=job.trainer_id,
        training_group_id=group.id,
        participant_count=parameters.participant_count,
        name=f"Plan treningowy – {group.name}",
        group_name_snapshot=group.name,
        group_min_age_snapshot=group.min_age,
        group_max_age_snapshot=group.max_age,
        training_duration_snapshot=group.duration_minutes,
        available_equipment_snapshot=_catalog_snapshot(validated_input.equipment),
        training_types_snapshot=_catalog_snapshot(validated_input.training_types),
        schema_snapshot=_schema_snapshot(group),
    )
    plan.exercises = [
        _plan_exercise(
            position, item, selected_sources[item.candidate.trainer_exercise_id]
        )
        for position, item in enumerate(
            sorted(generated.selections, key=lambda item: item.schema_position),
            start=1,
        )
    ]
    session.add(plan)
    await session.flush()
    return plan


def _plan_exercise(
    position: int,
    selected: PlanExerciseSelection,
    source: TrainerExercise,
) -> TrainingPlanExercise:
    """Create one immutable exercise occurrence from a selected configuration."""
    details = source.source_version or source.exercise
    return TrainingPlanExercise(
        trainer_exercise_id=source.id,
        exercise_id=source.exercise_id,
        exercise_version_id=source.source_version_id,
        position=position,
        schema_position=selected.schema_position,
        name_snapshot=details.name,
        description_snapshot=details.description,
        image_url_snapshot=details.image_url,
        min_age_snapshot=source.min_age,
        max_age_snapshot=source.max_age,
        min_participants_snapshot=source.min_participants,
        max_participants_snapshot=source.max_participants,
        duration_minutes_snapshot=selected.allocated_duration_minutes,
        physical_difficulty_snapshot=source.physical_difficulty,
        technical_difficulty_snapshot=source.technical_difficulty,
        upper_body_load_snapshot=source.upper_body_load,
        lower_body_load_snapshot=source.lower_body_load,
        core_load_snapshot=source.core_load,
        equipment_snapshot=_catalog_snapshot(source.equipment),
        training_types_snapshot=_catalog_snapshot(source.training_types),
        segments_snapshot=[
            {"id": segment.id, "code": segment.code, "name": segment.name}
            for segment in sorted(source.segments, key=lambda segment: segment.id)
        ],
    )


def _accepted(job: PlanGenerationJob) -> PlanGenerationAccepted:
    return PlanGenerationAccepted(id=job.id, status=job.status)


def _catalog_snapshot(
    items: Sequence[Equipment | TrainingType],
) -> list[dict[str, str]]:
    return [
        {"id": str(item.id), "name": item.name}
        for item in sorted(items, key=lambda item: (item.name, item.id))
    ]


def _schema_snapshot(group: TrainingGroup) -> list[dict[str, object]]:
    return [
        {
            "position": item.position,
            "segment_id": item.segment_id,
            "code": item.segment.code,
            "name": item.segment.name,
            "percentage": float(item.percentage),
        }
        for item in sorted(group.schema_items, key=lambda item: item.position)
    ]
