"""Load a trainer's real exercise configurations without writing to the database."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.db.session import get_session_factory
from app.models.catalogs import Equipment, TrainingType
from app.models.enums import ExerciseScope, TrainerExerciseStatus
from app.models.exercises import TrainerExercise
from app.services.plan_generation_candidates_service import _candidate_for_source
from app.services.plan_generation_domain import PlanExerciseCandidate


@dataclass(frozen=True)
class Catalog:
    candidates: tuple[PlanExerciseCandidate, ...]
    names: dict[UUID, str]
    equipment: dict[str, UUID]
    types: dict[str, UUID]
    trainer_id: UUID


async def load_catalog(trainer_id: UUID | None) -> Catalog:
    async with get_session_factory()() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        ids = list(
            (
                await session.scalars(
                    select(TrainerExercise.trainer_id)
                    .where(TrainerExercise.status == TrainerExerciseStatus.ACTIVE)
                    .distinct()
                )
            ).all()
        )
        if trainer_id is None:
            if len(ids) != 1:
                raise ValueError(
                    "Podaj trainer_id w konfiguracji; aktywnych trenerów: "
                    + ", ".join(map(str, ids))
                )
            trainer_id = ids[0]
        sources = list(
            (
                await session.scalars(
                    select(TrainerExercise)
                    .where(
                        TrainerExercise.trainer_id == trainer_id,
                        TrainerExercise.status == TrainerExerciseStatus.ACTIVE,
                    )
                    .options(
                        selectinload(TrainerExercise.exercise),
                        selectinload(TrainerExercise.source_version),
                        selectinload(TrainerExercise.equipment),
                        selectinload(TrainerExercise.training_types),
                        selectinload(TrainerExercise.segments),
                    )
                    .order_by(TrainerExercise.id)
                )
            ).all()
        )
        sources = [
            s
            for s in sources
            if s.exercise.scope == ExerciseScope.GLOBAL
            or s.exercise.owner_user_id == trainer_id
        ]
        if not sources:
            raise ValueError("Brak aktywnych ćwiczeń wybranego trenera")
        equipment_rows = (
            await session.scalars(
                select(Equipment).where(
                    (Equipment.owner_user_id == trainer_id)
                    | (Equipment.owner_user_id.is_(None))
                )
            )
        ).all()
        type_rows = (
            await session.scalars(
                select(TrainingType).where(
                    (TrainingType.owner_user_id == trainer_id)
                    | (TrainingType.owner_user_id.is_(None))
                )
            )
        ).all()

        def by_name(rows: Sequence[Equipment | TrainingType]) -> dict[str, UUID]:
            result: dict[str, UUID] = {}
            for row in rows:
                if row.name in result:
                    raise ValueError(f"Niejednoznaczna nazwa w katalogu: {row.name}")
                result[row.name] = row.id
            return result

        candidates = []
        names = {}
        for source in sources:
            candidate = _candidate_for_source(
                source,
                {x.id for x in source.equipment},
                {x.id for x in source.segments},
                recent_usage_distance=4,
            )
            if candidate:
                candidates.append(candidate)
                names[candidate.trainer_exercise_id] = (
                    source.source_version or source.exercise
                ).name
        return Catalog(
            tuple(candidates),
            names,
            by_name(equipment_rows),
            by_name(type_rows),
            trainer_id,
        )
