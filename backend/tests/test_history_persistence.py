"""Tests for persisting successful SQL generations to sql_history.

All database access is mocked — no Supabase connection is made and no
Groq API calls are performed.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.main import app
from app.db.models import SqlHistory
from app.services.history import (
    SYSTEM_USER_ID,
    HistoryPersistenceError,
    save_generation,
)

client = TestClient(app)

QUESTION = "Find all employees in the Sales department."
SCHEMA = "employee(emp_id INT, name VARCHAR, department VARCHAR, salary INT)"
SQL = "SELECT emp_id, name FROM employee WHERE department = 'Sales';"
REQUEST_JSON = {"question": QUESTION, "schema": SCHEMA}


def _mock_session() -> MagicMock:
    """Build an AsyncMock-backed session double."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session


def _session_factory(session: MagicMock) -> MagicMock:
    """Build a factory whose call() supports ``async with``."""
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=context)


def _groq_client_returning(sql: str) -> MagicMock:
    """Build a mocked Groq client that returns the given SQL."""
    mock_response = MagicMock()
    mock_response.choices[0].message.content = sql
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


# --- save_generation (service level, mocked session) ----------------------


def test_save_generation_writes_history_row():
    """A successful save bootstraps the system user and inserts the row."""
    session = _mock_session()
    factory = _session_factory(session)

    with patch("app.services.history.get_session_factory", return_value=factory):
        asyncio.run(save_generation(question=QUESTION, schema=SCHEMA, sql=SQL))

    # System-user bootstrap ran as an idempotent upsert.
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    rendered = str(statement.compile(dialect=postgresql.dialect()))
    assert "INSERT INTO users" in rendered
    assert "ON CONFLICT DO NOTHING" in rendered

    # Exactly one history row with the expected stored values.
    session.add.assert_called_once()
    row = session.add.call_args.args[0]
    assert isinstance(row, SqlHistory)
    assert row.user_id == SYSTEM_USER_ID
    assert row.natural_language_query == QUESTION
    assert row.schema_text == SCHEMA
    assert row.generated_sql == SQL

    session.commit.assert_awaited_once()


def test_save_generation_wraps_database_failure():
    """Database errors surface as HistoryPersistenceError, never silently."""
    session = _mock_session()
    session.execute.side_effect = RuntimeError("connection refused")
    factory = _session_factory(session)

    with patch("app.services.history.get_session_factory", return_value=factory):
        with pytest.raises(HistoryPersistenceError) as excinfo:
            asyncio.run(save_generation(question=QUESTION, schema=SCHEMA, sql=SQL))

    # Original error is chained, nothing is committed, no row is added.
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


# --- /api/v1/sql/generate (endpoint level, mocked Groq + persistence) -----


def test_generate_success_persists_history():
    """After generation + validation succeed, the row is saved exactly once."""
    save_mock = AsyncMock()

    with (
        patch(
            "app.services.sql_generator._get_client",
            return_value=_groq_client_returning(SQL),
        ),
        patch("app.api.routes.sql.save_generation", save_mock),
    ):
        response = client.post("/api/v1/sql/generate", json=REQUEST_JSON)

    assert response.status_code == 200
    assert response.json()["sql"] == SQL
    save_mock.assert_awaited_once_with(question=QUESTION, schema=SCHEMA, sql=SQL)


def test_generate_validation_failure_does_not_persist():
    """Non-read-only SQL fails validation -> 400 and nothing is saved."""
    save_mock = AsyncMock()

    with (
        patch(
            "app.services.sql_generator._get_client",
            return_value=_groq_client_returning("DELETE FROM employee"),
        ),
        patch("app.api.routes.sql.save_generation", save_mock),
    ):
        response = client.post("/api/v1/sql/generate", json=REQUEST_JSON)

    assert response.status_code == 400
    save_mock.assert_not_awaited()


def test_generate_groq_failure_does_not_persist():
    """Generation failure -> 502 and nothing is saved."""
    save_mock = AsyncMock()
    failing_client = MagicMock()
    failing_client.chat.completions.create.side_effect = Exception("API Error")

    with (
        patch(
            "app.services.sql_generator._get_client",
            return_value=failing_client,
        ),
        patch("app.api.routes.sql.save_generation", save_mock),
    ):
        response = client.post("/api/v1/sql/generate", json=REQUEST_JSON)

    assert response.status_code == 502
    save_mock.assert_not_awaited()


def test_generate_persistence_failure_returns_500():
    """A database failure during save must not report success."""
    save_mock = AsyncMock(
        side_effect=HistoryPersistenceError("could not save the generated SQL")
    )

    with (
        patch(
            "app.services.sql_generator._get_client",
            return_value=_groq_client_returning(SQL),
        ),
        patch("app.api.routes.sql.save_generation", save_mock),
    ):
        response = client.post("/api/v1/sql/generate", json=REQUEST_JSON)

    assert response.status_code == 500
    # Generic detail: no SQL, URLs, or credentials are exposed.
    assert response.json()["detail"] == (
        "Failed to persist the generated SQL history"
    )
