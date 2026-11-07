"""Typed failures shared by plan-generation preparation and strategies."""

from typing import ClassVar


class PlanGenerationError(Exception):
    """Base error raised before a generated plan can be persisted."""

    error_code: ClassVar[str] = "GENERATION_ERROR"


class NoCandidateForSchemaPositionError(PlanGenerationError):
    """Raised when no valid exercise can fill one schema position."""

    error_code = "NO_CANDIDATE"

    def __init__(self, schema_position: int) -> None:
        self.schema_position = schema_position
        super().__init__(f"No exercise can fill schema position {schema_position}")
