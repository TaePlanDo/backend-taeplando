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


class NoDurationForSchemaPositionError(PlanGenerationError):
    """Raised when a schema position has no whole minute to allocate."""

    error_code = "INVALID_SCHEMA_DURATION"

    def __init__(self, schema_position: int) -> None:
        self.schema_position = schema_position
        super().__init__(
            f"Schema position {schema_position} has no whole minute to allocate"
        )


class InvalidSchemaPercentageTotalError(PlanGenerationError):
    """Raised when persisted schema percentages cannot define a whole plan."""

    error_code = "INVALID_SCHEMA_PERCENTAGES"

    def __init__(self) -> None:
        super().__init__("Schema percentages must sum to 100")
