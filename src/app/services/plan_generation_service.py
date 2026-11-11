"""Queue, execute, persist, and report asynchronous training-plan generation."""

import asyncio
import logging
import time
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
from app.services.plan_generation_best import BestSoFar
from app.services.plan_generation_domain import (
    GenerationContext,
    GenerationSchemaItem,
    PlanExerciseCandidate,
    PlanExerciseSelection,
    PlanIndividual,
)
from app.services.plan_generation_errors import (
    NoCandidateForSchemaPositionError,
    PlanGenerationError,
)
from app.services.plan_generation_evolution import evolve
from app.services.plan_generation_population_service import (
    allocate_segment_durations,
    build_initial_population,
)

logger = logging.getLogger(__name__)


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
    logger.info("job %s: starting", job_id)
    async with get_session_factory()() as session:
        job = await jobs_db.claim(session, job_id)
        if job is None:
            logger.info(
                "job %s: not claimed (missing, already running, or expired)", job_id
            )
            return

        timeout_seconds = max((job.deadline_at - datetime.now(UTC)).total_seconds(), 0)
        logger.info(
            "job %s: claimed; timeout_seconds=%.2f deadline_at=%s",
            job.id,
            timeout_seconds,
            job.deadline_at.isoformat(),
        )

        best = BestSoFar()
        failure: tuple[str, str] | None = None
        started_at = time.perf_counter()
        try:
            async with asyncio.timeout(timeout_seconds):
                plan = await _generate_plan(session, job, best=best)
                if await jobs_db.mark_succeeded(session, job.id, plan.id):
                    logger.info("job %s: succeeded plan_id=%s", job.id, plan.id)
                    return
                logger.info(
                    "job %s: mark_succeeded lost the deadline race",
                    job.id,
                )
                await session.rollback()
        except TimeoutError:
            logger.info("job %s: hard timeout", job_id)
            await session.rollback()
        except PlanGenerationError as exc:
            logger.info(
                "job %s: generation error code=%s message=%s",
                job_id,
                exc.error_code,
                exc,
            )
            await session.rollback()
            failure = (exc.error_code, str(exc))
        except Exception:
            logger.exception("job %s: unexpected failure", job_id)
            await session.rollback()
            failure = (PlanGenerationError.error_code, "Plan generation failed")
        finally:
            logger.info(
                "job %s: total_duration_seconds=%.3f",
                job.id,
                time.perf_counter() - started_at,
            )

        await _finish_with_salvage(session, job, best, failure=failure)


async def _finish_with_salvage(
    session: AsyncSession,
    job: PlanGenerationJob,
    best: BestSoFar,
    *,
    failure: tuple[str, str] | None,
) -> None:
    """Prefer BestSoFar salvage; otherwise time out or record the captured failure."""
    if await _salvage_best_plan(session, job, best):
        return
    if failure is None:
        await jobs_db.mark_timed_out(session, job.id)
        logger.info("job %s: timed out (no salvageable plan)", job.id)
        return
    await _mark_failure(session, job.id, code=failure[0], message=failure[1])
    logger.info("job %s: failed code=%s", job.id, failure[0])


async def _mark_failure(
    session: AsyncSession, job_id: UUID, *, code: str, message: str
) -> None:
    """Record a normal failure, or the timeout that won the terminal-state race."""
    if not await jobs_db.mark_failed(session, job_id, code=code, message=message):
        await jobs_db.mark_timed_out(session, job_id)


async def _salvage_best_plan(
    session: AsyncSession,
    job: PlanGenerationJob,
    best: BestSoFar,
) -> bool:
    """Persist a structurally complete BestSoFar snapshot after a hard cut."""
    snapshot = best.snapshot()
    if snapshot is None:
        logger.info("job %s: salvage skipped (BestSoFar incomplete)", job.id)
        return False
    logger.info(
        "job %s: salvaging BestSoFar with %d selections",
        job.id,
        len(snapshot.selections),
    )
    try:
        parameters, validated_input = await _validated_job_input(session, job)
        plan = await _persist_plan(session, job, validated_input, parameters, snapshot)
    except Exception:
        logger.exception("job %s: salvage persist failed", job.id)
        await session.rollback()
        return False
    succeeded = await jobs_db.mark_succeeded_after_timeout(session, job.id, plan.id)
    if succeeded:
        logger.info("job %s: succeeded via salvage plan_id=%s", job.id, plan.id)
    else:
        logger.info(
            "job %s: salvage mark_succeeded_after_timeout lost the race", job.id
        )
    return succeeded


def _parameters_from_job(job: PlanGenerationJob) -> PlanGenerationParameters:
    return PlanGenerationParameters(
        training_group_id=job.training_group_id,
        participant_count=job.participant_count,
        available_equipment_ids=[UUID(item) for item in job.available_equipment_ids],
        training_type_id=job.training_type_id,
    )


async def _validated_job_input(
    session: AsyncSession, job: PlanGenerationJob
) -> tuple[
    PlanGenerationParameters,
    plan_generation_parameters_service.ValidatedPlanGenerationInput,
]:
    parameters = _parameters_from_job(job)
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
    return parameters, validated_input


async def _generate_plan(
    session: AsyncSession,
    job: PlanGenerationJob,
    *,
    best: BestSoFar,
) -> TrainingPlan:
    """Build and persist a plan while keeping the strategy free of I/O."""
    logger.info("job %s: validating parameters", job.id)
    parameters, validated_input = await _validated_job_input(session, job)
    group = validated_input.group
    logger.info(
        "job %s: parameters ok group=%s duration=%dmin schema_items=%d",
        job.id,
        group.name,
        group.duration_minutes,
        len(group.schema_items),
    )

    logger.info("job %s: preparing candidates", job.id)
    candidates = await plan_generation_candidates_service.prepare_candidates(
        session, job.trainer_id, group, parameters
    )
    logger.info("job %s: prepared %d candidates", job.id, len(candidates))
    contexts = _generation_contexts(job, group, parameters, candidates)
    best.set_required_positions(tuple(context.segment.position for context in contexts))
    logger.info(
        "job %s: evolving %d segments in parallel positions=%s",
        job.id,
        len(contexts),
        [context.segment.position for context in contexts],
    )
    generated = _merge_segment_individuals(
        await asyncio.gather(
            *(_generate_segment(best, context) for context in contexts)
        )
    )
    logger.info(
        "job %s: merged plan with %d selections; persisting",
        job.id,
        len(generated.selections),
    )
    return await _persist_plan(session, job, validated_input, parameters, generated)


async def _generate_segment(
    best: BestSoFar, context: GenerationContext
) -> PlanIndividual:
    """Build and generate one segment in its own worker-thread invocation."""
    return await asyncio.to_thread(_generate_segment_sync, best, context)


def _generate_segment_sync(
    best: BestSoFar, context: GenerationContext
) -> PlanIndividual:
    """Build one segment's population and evolve it.

    Share only BestSoFar across threads.
    """
    position = context.segment.position
    logger.info(
        "segment %s: start duration=%dmin candidates=%d seed=%s",
        position,
        context.segment_duration_minutes,
        len(context.candidates),
        context.random_seed,
    )
    population = build_initial_population(context)
    logger.info(
        "segment %s: initial population size=%d",
        position,
        len(population.individuals),
    )
    generated = evolve(context, population, best=best)
    total_minutes = sum(
        selection.allocated_duration_minutes for selection in generated.selections
    )
    logger.info(
        "segment %s: done selections=%d total_minutes=%d",
        position,
        len(generated.selections),
        total_minutes,
    )
    return generated


def _generation_contexts(
    job: PlanGenerationJob,
    group: TrainingGroup,
    parameters: PlanGenerationParameters,
    candidates: Sequence[PlanExerciseCandidate],
) -> tuple[GenerationContext, ...]:
    """Adapt every schema segment into an isolated immutable algorithm contract."""
    schema = tuple(
        GenerationSchemaItem(
            position=item.position,
            segment_id=item.segment_id,
            percentage=item.percentage,
        )
        for item in sorted(group.schema_items, key=lambda item: item.position)
    )
    segment_durations = allocate_segment_durations(group.duration_minutes, schema)
    return tuple(
        _segment_context(
            job,
            group,
            parameters,
            schema_item,
            segment_durations[schema_item.position],
            candidates,
        )
        for schema_item in schema
    )


def _segment_context(
    job: PlanGenerationJob,
    group: TrainingGroup,
    parameters: PlanGenerationParameters,
    segment: GenerationSchemaItem,
    segment_duration_minutes: int,
    candidates: Sequence[PlanExerciseCandidate],
) -> GenerationContext:
    """Build one segment's context and enforce its hard candidate constraint."""
    segment_candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.default_duration_minutes > 0
        and segment.segment_id in candidate.segment_ids
    )
    if not segment_candidates:
        raise NoCandidateForSchemaPositionError(segment.position)
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
        segment=segment,
        segment_duration_minutes=segment_duration_minutes,
        candidates=segment_candidates,
        random_seed=job.id.int ^ segment.position,
    )


def _merge_segment_individuals(
    segments: Sequence[PlanIndividual],
) -> PlanIndividual:
    """Restore one plan from independently generated segment selections."""
    return PlanIndividual(
        selections=tuple(
            sorted(
                (selection for segment in segments for selection in segment.selections),
                key=lambda selection: selection.schema_position,
            )
        )
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
