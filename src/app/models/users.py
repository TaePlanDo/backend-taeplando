"""User accounts and persisted refresh-token sessions."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now
from app.models.enums import AuthMethod

if TYPE_CHECKING:
    from app.models.catalogs import Equipment, TrainingType
    from app.models.exercises import Exercise, TrainerExercise
    from app.models.training import TrainingGroup, TrainingPlan


class User(Base):
    """A trainer account that can own exercises, groups, and plans."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(auth_method = 'LOCAL' AND password_hash IS NOT NULL) "
            "OR (auth_method = 'GOOGLE' AND oauth_subject IS NOT NULL)",
            name="ck_users_auth_method_credentials",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    auth_method: Mapped[AuthMethod] = mapped_column(
        SqlEnum(AuthMethod, name="auth_method")
    )
    password_hash: Mapped[str | None] = mapped_column(String(255))
    oauth_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    owned_exercises: Mapped[list[Exercise]] = relationship(
        "Exercise", back_populates="owner"
    )
    trainer_exercises: Mapped[list[TrainerExercise]] = relationship(
        "TrainerExercise", back_populates="trainer"
    )
    owned_equipment: Mapped[list[Equipment]] = relationship(
        "Equipment", back_populates="owner"
    )
    owned_training_types: Mapped[list[TrainingType]] = relationship(
        "TrainingType", back_populates="owner"
    )
    training_groups: Mapped[list[TrainingGroup]] = relationship(
        "TrainingGroup", back_populates="trainer"
    )
    training_plans: Mapped[list[TrainingPlan]] = relationship(
        "TrainingPlan", back_populates="trainer"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    """A persisted hash for one user refresh-token session."""

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")
