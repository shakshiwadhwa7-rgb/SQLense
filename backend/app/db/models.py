"""SQLAlchemy 2.x declarative models for SQLense."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all SQLense models."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sql_history: Mapped[list["SqlHistory"]] = relationship(back_populates="user")
    practice_attempts: Mapped[list["PracticeAttempt"]] = relationship(
        back_populates="user"
    )


class SqlHistory(Base):
    __tablename__ = "sql_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    natural_language_query: Mapped[str] = mapped_column(Text)
    schema_text: Mapped[str] = mapped_column(Text)
    generated_sql: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped["User"] = relationship(back_populates="sql_history")


class PracticeQuestion(Base):
    __tablename__ = "practice_questions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question: Mapped[str] = mapped_column(Text)
    schema_text: Mapped[str] = mapped_column(Text)
    reference_sql: Mapped[str] = mapped_column(Text)
    difficulty: Mapped[str] = mapped_column(String(50), index=True)
    topic: Mapped[str] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    attempts: Mapped[list["PracticeAttempt"]] = relationship(
        back_populates="question"
    )


class PracticeAttempt(Base):
    __tablename__ = "practice_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("practice_questions.id"), index=True
    )
    submitted_sql: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="practice_attempts")
    question: Mapped["PracticeQuestion"] = relationship(back_populates="attempts")
