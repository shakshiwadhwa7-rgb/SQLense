"""Persist Practice Mode results to ``practice_questions`` / ``practice_attempts``.

Temporary user strategy (until authentication is added): every
``practice_attempts`` row must satisfy ``user_id -> users.id``, so attempts
are attributed to the same synthetic *system user* defined in
``app.services.history`` (``SYSTEM_USER_ID``) and bootstrapped with the
same idempotent upsert. When authentication is added, replace
``SYSTEM_USER_ID`` with the authenticated user's id — the only place that
needs to change.

Note: ``practice_questions`` has no ``user_id`` column (frozen schema),
so question rows carry no user attribution.
"""

import logging
import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.database import get_session_factory
from app.db.models import PracticeAttempt, PracticeQuestion, User
from app.services.history import SYSTEM_USER_ID

logger = logging.getLogger(__name__)


class PracticePersistenceError(RuntimeError):
    """Raised when a practice question or attempt could not be saved."""


async def save_practice_question(
    *,
    question: str,
    schema: str,
    reference_sql: str,
    difficulty: str,
    topic: str,
) -> uuid.UUID:
    """Save one generated practice question; returns the stored row's id.

    Writes the question row in a single transaction using the existing
    async session factory. Called only after question generation and
    reference-SQL validation have succeeded.

    Args:
        question: The generated practice question text.
        schema: The schema text the question applies to.
        reference_sql: The validated reference solution.
        difficulty: The requested difficulty level.
        topic: The requested topic.

    Returns:
        The id of the stored ``practice_questions`` row.

    Raises:
        PracticePersistenceError: If the row could not be written. The
            original database error is chained as ``__cause__`` and is
            only logged server-side, never returned to API clients.
    """
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            row = PracticeQuestion(
                # Explicit id so the stored id is available to return
                # immediately after a successful commit.
                id=uuid.uuid4(),
                question=question,
                schema_text=schema,
                reference_sql=reference_sql,
                difficulty=difficulty,
                topic=topic,
            )
            session.add(row)
            await session.commit()
            return row.id
    except Exception as exc:
        logger.exception("Failed to persist practice question to practice_questions")
        raise PracticePersistenceError(
            "could not save the practice question"
        ) from exc


async def save_practice_attempt(
    *,
    question_id: uuid.UUID | None,
    submitted_sql: str,
    correct: bool,
    feedback: str,
) -> None:
    """Save one evaluation attempt against a stored practice question.

    Writes the system-user bootstrap (if needed) and the attempt row in
    a single transaction using the existing async session factory.
    Called only after evaluation has produced its result.

    ``practice_attempts.question_id`` is a NOT NULL foreign key, so an
    attempt can only be recorded when the caller supplies the
    ``practice_questions`` id returned by ``/practice/generate``. When
    ``question_id`` is absent (ad-hoc question, pre-contract clients),
    no attempt is recorded and no database call is made.

    Args:
        question_id: The stored question this attempt answers, or None.
        submitted_sql: The learner's submitted SQL (never executed).
        correct: Whether evaluation judged the submission correct.
        feedback: The evaluation feedback shown to the learner.

    Raises:
        PracticePersistenceError: If the row could not be written. The
            original database error is chained as ``__cause__`` and is
            only logged server-side, never returned to API clients.
    """
    if question_id is None:
        logger.debug("Practice attempt not persisted: no question_id supplied")
        return

    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            # Ensure the system user exists; ON CONFLICT DO NOTHING makes
            # repeated (and concurrent) first requests safe.
            await session.execute(
                pg_insert(User).values(id=SYSTEM_USER_ID).on_conflict_do_nothing()
            )
            session.add(
                PracticeAttempt(
                    user_id=SYSTEM_USER_ID,
                    question_id=question_id,
                    submitted_sql=submitted_sql,
                    is_correct=correct,
                    feedback=feedback,
                )
            )
            await session.commit()
    except Exception as exc:
        logger.exception("Failed to persist practice attempt to practice_attempts")
        raise PracticePersistenceError(
            "could not save the practice attempt"
        ) from exc
