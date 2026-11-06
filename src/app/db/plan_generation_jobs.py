"""Database operations for asynchronous training-plan generation jobs."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utc_now
from app.models.enums import PlanGenerationJobStatus
from app.models.plan_generation import PlanGenerationJob


async def create(
    session: AsyncSession,
    trainer_id: UUID,
    *,
    training_group_id: UUID,
    participant_count: int,
    available_equipment_ids: list[UUID],
    training_type_id: UUID | None,
    timeout_seconds: int,
) -> PlanGenerationJob:
    """Persist one accepted request before its background runner starts."""
    now = utc_now()
    job = PlanGenerationJob(
        trainer_id=trainer_id,
        training_group_id=training_group_id,
        participant_count=participant_count,
        available_equipment_ids=[str(item) for item in available_equipment_ids],
        training_type_id=training_type_id,
        status=PlanGenerationJobStatus.QUEUED,
        deadline_at=now + timedelta(seconds=timeout_seconds),
    )
    session.add(job)
    await session.commit()
    return job


async def get_for_trainer(
    session: AsyncSession, trainer_id: UUID, job_id: UUID
) -> PlanGenerationJob | None:
    """Return a trainer-owned job, expiring stale active jobs on read."""
    result = await session.execute(
        select(PlanGenerationJob).where(
            PlanGenerationJob.id == job_id,
            PlanGenerationJob.trainer_id == trainer_id,
        )
    )
    job = result.scalar_one_or_none()
    if job is not None and _is_expired(job):
        await mark_timed_out(session, job.id)
        await session.refresh(job)
    return job


async def claim(session: AsyncSession, job_id: UUID) -> PlanGenerationJob | None:
    """Move a queued job to running exactly once."""
    now = utc_now()
    result = await session.execute(
        update(PlanGenerationJob)
        .where(
            PlanGenerationJob.id == job_id,
            PlanGenerationJob.status == PlanGenerationJobStatus.QUEUED,
            PlanGenerationJob.deadline_at > now,
        )
        .values(status=PlanGenerationJobStatus.RUNNING, started_at=now)
        .returning(PlanGenerationJob)
    )
    job = result.scalar_one_or_none()
    if job is not None:
        await session.commit()
        return job

    await mark_timed_out(session, job_id)
    return None


async def mark_succeeded(session: AsyncSession, job_id: UUID, plan_id: UUID) -> bool:
    """Atomically save a successful job only while its deadline remains valid."""
    now = utc_now()
    result = await session.execute(
        update(PlanGenerationJob)
        .where(
            PlanGenerationJob.id == job_id,
            PlanGenerationJob.status == PlanGenerationJobStatus.RUNNING,
            PlanGenerationJob.deadline_at > now,
        )
        .values(
            status=PlanGenerationJobStatus.SUCCEEDED,
            plan_id=plan_id,
            finished_at=now,
        )
        .returning(PlanGenerationJob.id)
    )
    if result.scalar_one_or_none() is None:
        await session.rollback()
        return False
    await session.commit()
    return True


async def mark_failed(
    session: AsyncSession,
    job_id: UUID,
    *,
    code: str,
    message: str,
) -> bool:
    """Atomically persist a failure while the running job has time remaining."""
    now = utc_now()
    result = await session.execute(
        update(PlanGenerationJob)
        .where(
            PlanGenerationJob.id == job_id,
            PlanGenerationJob.status == PlanGenerationJobStatus.RUNNING,
            PlanGenerationJob.deadline_at > now,
        )
        .values(
            status=PlanGenerationJobStatus.FAILED,
            error_code=code,
            error_message=message,
            finished_at=now,
        )
        .returning(PlanGenerationJob.id)
    )
    if result.scalar_one_or_none() is None:
        return False
    await session.commit()
    return True


async def mark_timed_out(session: AsyncSession, job_id: UUID) -> None:
    """Mark an active job as timed out only after its persisted deadline."""
    now = utc_now()
    result = await session.execute(
        update(PlanGenerationJob)
        .where(
            PlanGenerationJob.id == job_id,
            PlanGenerationJob.status.in_(_ACTIVE_STATUSES),
            PlanGenerationJob.deadline_at <= now,
        )
        .values(
            status=PlanGenerationJobStatus.TIMED_OUT,
            error_code="TIMEOUT",
            error_message="Plan generation exceeded its time limit",
            finished_at=now,
        )
        .returning(PlanGenerationJob.id)
    )
    if result.scalar_one_or_none() is not None:
        await session.commit()


_TERMINAL_STATUSES = {
    PlanGenerationJobStatus.SUCCEEDED,
    PlanGenerationJobStatus.FAILED,
    PlanGenerationJobStatus.TIMED_OUT,
}

_ACTIVE_STATUSES = {
    PlanGenerationJobStatus.QUEUED,
    PlanGenerationJobStatus.RUNNING,
}


def _is_expired(job: PlanGenerationJob) -> bool:
    return job.status not in _TERMINAL_STATUSES and job.deadline_at <= utc_now()
