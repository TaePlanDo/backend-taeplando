"""Load the checked-in exercise catalog used by the development seed."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from app.models.enums import EquipmentRequirementMode

CATALOG_PATH = Path(__file__).with_name("data") / "exercise_catalog.csv"

SEGMENT_CODE_BY_NAME = {
    "Rozgrzewka": "WARMUP",
    "Zabawa": "GAME",
    "Ćwiczenia": "MAIN",
    "Rozciąganie": "COOLDOWN",
}

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


def _number(row: dict[str, str], column: str, *, default: int | None = None) -> int:
    value = row[column].strip()
    if value:
        return int(value)
    if default is not None:
        return default
    raise ValueError(f"Missing {column} for catalog exercise {row['source_id']}")


def _row_to_exercise(row: dict[str, str]) -> SeedExercise:
    equipment_names, equipment_requirement_mode = _equipment(row["equipment"].strip())
    min_participants = _number(row, "min_participants")
    return SeedExercise(
        source_id=_number(row, "source_id"),
        name=row["name"].strip(),
        description=row["description"].strip(),
        min_age=_number(row, "min_age"),
        max_age=_number(row, "max_age"),
        min_participants=min_participants,
        max_participants=_number(row, "max_participants", default=min_participants),
        duration_minutes=_number(row, "duration_minutes"),
        physical_difficulty=_number(row, "physical_difficulty"),
        technical_difficulty=_number(row, "technical_difficulty"),
        upper_body_load=_number(row, "upper_body_load"),
        lower_body_load=_number(row, "lower_body_load"),
        core_load=_number(row, "core_load"),
        equipment_names=equipment_names,
        equipment_requirement_mode=equipment_requirement_mode,
        training_type_names=_split(row["training_types"].strip(), "/"),
        segment_codes=tuple(
            SEGMENT_CODE_BY_NAME[name] for name in _split(row["segments"].strip(), "/")
        ),
    )


@cache
def load_exercise_catalog() -> tuple[SeedExercise, ...]:
    """Return every source exercise and reject duplicate catalog IDs."""

    with CATALOG_PATH.open(encoding="utf-8", newline="") as catalog_file:
        exercises = tuple(_row_to_exercise(row) for row in csv.DictReader(catalog_file))
    if len({exercise.source_id for exercise in exercises}) != len(exercises):
        raise ValueError("Exercise catalog contains duplicate source IDs")
    return exercises


def equipment_names(exercises: tuple[SeedExercise, ...]) -> tuple[str, ...]:
    """Return the normalized, alphabetically ordered global equipment catalog."""

    return tuple(
        sorted({name for exercise in exercises for name in exercise.equipment_names})
    )
