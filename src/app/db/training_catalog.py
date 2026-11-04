"""Fixed system dictionaries shared by source parsing and database seeding."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemTrainingSegment:
    """One immutable training segment used by every group schema."""

    id: int
    code: str
    name: str


SYSTEM_TRAINING_SEGMENTS = (
    SystemTrainingSegment(1, "WARMUP", "Rozgrzewka"),
    SystemTrainingSegment(2, "GAME", "Zabawa"),
    SystemTrainingSegment(3, "MAIN", "Ćwiczenia"),
    SystemTrainingSegment(4, "COOLDOWN", "Rozciąganie"),
)

SEGMENT_CODE_BY_NAME = {
    segment.name: segment.code for segment in SYSTEM_TRAINING_SEGMENTS
}
