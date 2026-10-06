"""Persist successful SQL generations to the ``sql_history`` table.

Temporary user strategy (until authentication is added): every
``sql_history`` row must satisfy the ``user_id -> users.id`` foreign key,
but no authenticated users exist yet. All generations are therefore
attributed to a single, clearly synthetic *system user* identified by
``SYSTEM_USER_ID``. The row is created on demand with an idempotent
upsert, so concurrent first requests are safe. When authentication is
added, replace ``SYSTEM_USER_ID`` with the authenticated user's id —
the only place that needs to change.
"""

import logging
import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.database import get_session_factory
from app.db.models import SqlHistory, User

logger = logging.getLogger(__name__)

#: Placeholder owner for all pre-authentication history rows.
SYSTEM_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


class HistoryPersistenceError(RuntimeError):
    """Raised when a generated query could not be saved to ``sql_history``."""


async def save_generation(*, question: str, schema: str, sql: str) -> None:
    """Save one successful generation to ``sql_history``.

    Writes the system-user bootstrap (if needed) and the history row in
    a single transaction using the existing async session factory.

    Args:
        question: The natural language question that produced the SQL.
        schema: The schema text the SQL was generated against.
        sql: The validated SQL query.

    Raises:
        HistoryPersistenceError: If the row could not be written. The
            original database error is chained as ``__cause__`` and is
            only logged server-side, never returned to API clients.
    """
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            # Ensure the system user exists; ON CONFLICT DO NOTHING makes
            # repeated (and concurrent) first requests safe.
            await session.execute(
                pg_insert(User).values(id=SYSTEM_USER_ID).on_conflict_do_nothing()
            )
            session.add(
                SqlHistory(
                    user_id=SYSTEM_USER_ID,
                    natural_language_query=question,
                    schema_text=schema,
                    generated_sql=sql,
                )
            )
            await session.commit()
    except Exception as exc:
        logger.exception("Failed to persist SQL generation to sql_history")
        raise HistoryPersistenceError(
            "could not save the generated SQL to history"
        ) from exc
