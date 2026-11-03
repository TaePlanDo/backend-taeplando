"""Normalize the checked-in exercise catalog used by the development seed."""

from __future__ import annotations

from dataclasses import dataclass

from app.db.exercise_catalog_source import EXERCISE_SOURCE_ROWS
from app.db.training_catalog import SEGMENT_CODE_BY_NAME
from app.models.enums import EquipmentRequirementMode

_CANONICAL_EQUIPMENT_NAMES = {
    "balony": "Balony",
    "drabinka": "Drabinka koordynacyjna",
    "drabinka koordynacyjna": "Drabinka koordynacyjna",
    "drabinki": "Drabinka koordynacyjna",
    "gumy oporowe": "Gumy oporowe",
    "kaski": "Kaski",
    "materace": "Materace",
    "obręcze": "Obręcze",
    "packa": "Packi",
    "packi": "Packi",
    "pałki": "Pałki",
    "piłeczki": "Piłeczki",
    "piłki": "Piłki",
    "poduchy": "Poduchy",
    "płotki": "Płotki",
    "woreczki": "Woreczki",
    "znaczniki": "Znaczniki",
}


@dataclass(frozen=True)
class SeedExercise:
    """One source record ready to be inserted as a global exercise."""

    source_id: int
    name: str
    description: str
    min_age: int
    max_age: int
    min_participants: int
    max_participants: int
    duration_minutes: int
    physical_difficulty: int
    technical_difficulty: int
    upper_body_load: int
    lower_body_load: int
    core_load: int
    equipment_names: tuple[str, ...]
    equipment_requirement_mode: EquipmentRequirementMode
    training_type_names: tuple[str, ...]
    segment_codes: tuple[str, ...]


def _split(value: str, separator: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(separator) if part.strip())


def _equipment(value: str) -> tuple[tuple[str, ...], EquipmentRequirementMode]:
    if not value or value == "Brak":
        return (), EquipmentRequirementMode.ALL

    mode = (
        EquipmentRequirementMode.ANY
        if " lub " in value
        else EquipmentRequirementMode.ALL
    )
    names = tuple(
        _CANONICAL_EQUIPMENT_NAMES[part.casefold()]
        for part in _split(value.replace(" lub ", ","), ",")
    )
    return tuple(dict.fromkeys(names)), mode


def _number(
    value: str,
    column: str,
    source_id: str,
    *,
    default: int | None = None,
) -> int:
    value = value.strip()
    if value:
        return int(value)
    if default is not None:
        return default
    raise ValueError(f"Missing {column} for catalog exercise {source_id}")


def _row_to_exercise(row: tuple[str, ...]) -> SeedExercise:
    (
        source_id,
        name,
        description,
        min_age,
        max_age,
        equipment,
        min_participants,
        max_participants,
        duration_minutes,
        training_types,
        segments,
        physical_difficulty,
        technical_difficulty,
        upper_body_load,
        lower_body_load,
        core_load,
    ) = row
    equipment_names, equipment_requirement_mode = _equipment(equipment.strip())
    parsed_min_participants = _number(min_participants, "min_participants", source_id)
    return SeedExercise(
        source_id=_number(source_id, "source_id", source_id),
        name=name.strip(),
        description=description.strip(),
        min_age=_number(min_age, "min_age", source_id),
        max_age=_number(max_age, "max_age", source_id),
        min_participants=parsed_min_participants,
        max_participants=_number(
            max_participants,
            "max_participants",
            source_id,
            default=parsed_min_participants,
        ),
        duration_minutes=_number(duration_minutes, "duration_minutes", source_id),
        physical_difficulty=_number(
            physical_difficulty, "physical_difficulty", source_id
        ),
        technical_difficulty=_number(
            technical_difficulty, "technical_difficulty", source_id
        ),
        upper_body_load=_number(upper_body_load, "upper_body_load", source_id),
        lower_body_load=_number(lower_body_load, "lower_body_load", source_id),
        core_load=_number(core_load, "core_load", source_id),
        equipment_names=equipment_names,
        equipment_requirement_mode=equipment_requirement_mode,
        training_type_names=_split(training_types.strip(), "/"),
        segment_codes=tuple(
            SEGMENT_CODE_BY_NAME[name] for name in _split(segments.strip(), "/")
        ),
    )


def load_exercise_catalog() -> tuple[SeedExercise, ...]:
    """Return every source exercise embedded in application code."""

    exercises = tuple(_row_to_exercise(row) for row in EXERCISE_SOURCE_ROWS)
    if len({exercise.source_id for exercise in exercises}) != len(exercises):
        raise ValueError("Exercise catalog contains duplicate source IDs")
    return exercises


def equipment_names(exercises: tuple[SeedExercise, ...]) -> tuple[str, ...]:
    """Return the normalized, alphabetically ordered global equipment catalog."""

    return tuple(
        sorted({name for exercise in exercises for name in exercise.equipment_names})
    )


def training_type_names(exercises: tuple[SeedExercise, ...]) -> tuple[str, ...]:
    """Return the alphabetically ordered training-type catalog from the source data."""

    return tuple(
        sorted(
            {name for exercise in exercises for name in exercise.training_type_names}
        )
    )
