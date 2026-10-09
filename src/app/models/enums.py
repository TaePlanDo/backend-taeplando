"""Database enum values used by SQLAlchemy models."""

from enum import StrEnum


class AuthMethod(StrEnum):
    """Supported ways a user can authenticate."""

    LOCAL = "LOCAL"
    GOOGLE = "GOOGLE"


class ExerciseScope(StrEnum):
    """Visibility level of an exercise."""

    PRIVATE = "PRIVATE"
    GLOBAL = "GLOBAL"


class ExerciseVersionStatus(StrEnum):
    """Moderation state of a global exercise version."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"


class TrainerExerciseStatus(StrEnum):
    """Local availability of an exercise for a trainer."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    HIDDEN = "HIDDEN"


class CatalogVisibility(StrEnum):
    """Publication state of equipment and training-type catalog entries."""

    LOCAL = "LOCAL"
    PENDING = "PENDING"
    GLOBAL = "GLOBAL"
