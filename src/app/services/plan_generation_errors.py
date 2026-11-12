"""Typed failures shared by plan-generation preparation and strategies."""

from typing import ClassVar


class PlanGenerationError(Exception):
    """Base error raised before a generated plan can be persisted."""

    error_code: ClassVar[str] = "GENERATION_ERROR"
    reason: str | None = None


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


class NoValidPlanError(PlanGenerationError):
    """Raised when evolution finishes without a structurally valid individual."""

    error_code = "NO_VALID_PLAN"

    def __init__(self) -> None:
        super().__init__("No valid training plan could be generated")


class InvalidGeneratedPlanError(PlanGenerationError):
    """Raised when a generated plan fails the pre-persist hard validation gate."""

    error_code = "INVALID_GENERATED_PLAN"

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason
        super().__init__("Generated plan does not meet requirements and was not saved.")
