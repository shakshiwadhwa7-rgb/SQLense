"""Tests for persisting practice questions and attempts.

All database access is mocked — no Supabase connection is made and no
Groq API calls are performed.
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.db.models import PracticeAttempt, PracticeQuestion
from app.main import app
from app.services.history import SYSTEM_USER_ID
from app.services.practice_persistence import (
    PracticePersistenceError,
    save_practice_attempt,
    save_practice_question,
)

client = TestClient(app)

TOPIC = "JOINs"
DIFFICULTY = "medium"
SCHEMA = "employee(emp_id INT, name VARCHAR, department VARCHAR, salary INT)"
QUESTION = "Which employees earn more than 1000?"
REF_SQL = "SELECT name FROM employee WHERE salary > 1000"
GENERATE_JSON = {"topic": TOPIC, "difficulty": DIFFICULTY, "schema": SCHEMA}
EVALUATE_JSON = {
    "question": QUESTION,
    "schema": SCHEMA,
    "user_sql": REF_SQL,
}


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


def _groq_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = text
    return resp


def _practice_json(question: str, reference_sql: str) -> MagicMock:
    """Build a mocked Groq response carrying structured practice output."""
    return _groq_response(
        json.dumps({"question": question, "reference_sql": reference_sql})
    )


# --- save_practice_question (service level, mocked session) ----------------


def test_save_practice_question_writes_row():
    """A successful save inserts one question row and returns its id."""
    session = _mock_session()
    factory = _session_factory(session)

    with patch(
        "app.services.practice_persistence.get_session_factory", return_value=factory
    ):
        row_id = asyncio.run(
            save_practice_question(
                question=QUESTION,
                schema=SCHEMA,
                reference_sql=REF_SQL,
                difficulty=DIFFICULTY,
                topic=TOPIC,
            )
        )

    assert isinstance(row_id, uuid.UUID)

    # practice_questions has no user_id column -> no system-user bootstrap.
    session.execute.assert_not_awaited()

    session.add.assert_called_once()
    row = session.add.call_args.args[0]
    assert isinstance(row, PracticeQuestion)
    assert row.question == QUESTION
    assert row.schema_text == SCHEMA
    assert row.reference_sql == REF_SQL
    assert row.difficulty == DIFFICULTY
    assert row.topic == TOPIC
    assert row.id == row_id

    session.commit.assert_awaited_once()


def test_save_practice_question_wraps_database_failure():
    """Database errors surface as PracticePersistenceError, never silently."""
    session = _mock_session()
    session.commit.side_effect = RuntimeError("connection refused")
    factory = _session_factory(session)

    with patch(
        "app.services.practice_persistence.get_session_factory", return_value=factory
    ):
        with pytest.raises(PracticePersistenceError) as excinfo:
            asyncio.run(
                save_practice_question(
                    question=QUESTION,
                    schema=SCHEMA,
                    reference_sql=REF_SQL,
                    difficulty=DIFFICULTY,
                    topic=TOPIC,
                )
            )

    # Original error is chained for server-side logging.
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    session.commit.assert_awaited_once()


# --- save_practice_attempt (service level, mocked session) -----------------


def test_save_practice_attempt_writes_row():
    """A successful save bootstraps the system user and inserts the attempt."""
    session = _mock_session()
    factory = _session_factory(session)
    question_id = uuid.uuid4()

    with patch(
        "app.services.practice_persistence.get_session_factory", return_value=factory
    ):
        asyncio.run(
            save_practice_attempt(
                question_id=question_id,
                submitted_sql=REF_SQL,
                correct=True,
                feedback="Correct!",
            )
        )

    # System-user bootstrap ran as an idempotent upsert.
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    rendered = str(statement.compile(dialect=postgresql.dialect()))
    assert "INSERT INTO users" in rendered
    assert "ON CONFLICT DO NOTHING" in rendered

    session.add.assert_called_once()
    row = session.add.call_args.args[0]
    assert isinstance(row, PracticeAttempt)
    assert row.user_id == SYSTEM_USER_ID
    assert row.question_id == question_id
    assert row.submitted_sql == REF_SQL
    assert row.is_correct is True
    assert row.feedback == "Correct!"

    session.commit.assert_awaited_once()


def test_save_practice_attempt_without_question_id_skips_persistence():
    """No stored question -> no attempt row and no database call at all."""
    factory = MagicMock()

    with patch(
        "app.services.practice_persistence.get_session_factory", return_value=factory
    ):
        asyncio.run(
            save_practice_attempt(
                question_id=None,
                submitted_sql=REF_SQL,
                correct=True,
                feedback="Correct!",
            )
        )

    factory.assert_not_called()


def test_save_practice_attempt_wraps_database_failure():
    """Database errors surface as PracticePersistenceError, never silently."""
    session = _mock_session()
    session.execute.side_effect = RuntimeError("connection refused")
    factory = _session_factory(session)

    with patch(
        "app.services.practice_persistence.get_session_factory", return_value=factory
    ):
        with pytest.raises(PracticePersistenceError) as excinfo:
            asyncio.run(
                save_practice_attempt(
                    question_id=uuid.uuid4(),
                    submitted_sql=REF_SQL,
                    correct=True,
                    feedback="Correct!",
                )
            )

    # Original error is chained, nothing is committed, no row is added.
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


# --- /api/v1/practice/generate (endpoint level, mocked Groq + persistence) -


def test_generate_success_persists_question():
    """After the one-call generation + validation, the question is saved once."""
    stored_id = uuid.uuid4()
    save_mock = AsyncMock(return_value=stored_id)

    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.api.routes.practice.save_practice_question", save_mock),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _practice_json(
            QUESTION, REF_SQL
        )
        mock_get_client.return_value = mock_client

        response = client.post("/api/v1/practice/generate", json=GENERATE_JSON)

    assert response.status_code == 200
    assert response.json()["question_id"] == str(stored_id)
    # Exactly one Groq call for the combined question + reference output.
    assert mock_client.chat.completions.create.call_count == 1
    # Persistence happens exactly once, after successful validation.
    save_mock.assert_awaited_once_with(
        question=QUESTION,
        schema=SCHEMA,
        reference_sql=REF_SQL,
        difficulty=DIFFICULTY,
        topic=TOPIC,
    )


def test_generate_groq_failure_does_not_persist():
    """Generation failure -> 502 and nothing is saved."""
    save_mock = AsyncMock()
    failing_client = MagicMock()
    failing_client.chat.completions.create.side_effect = Exception("API Error")

    with (
        patch(
            "app.services.sql_generator._get_client", return_value=failing_client
        ),
        patch("app.api.routes.practice.save_practice_question", save_mock),
    ):
        response = client.post("/api/v1/practice/generate", json=GENERATE_JSON)

    assert response.status_code == 502
    save_mock.assert_not_awaited()


def test_generate_invalid_reference_does_not_persist():
    """Reference SQL failing validation -> 502 and nothing is saved."""
    save_mock = AsyncMock()

    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.api.routes.practice.save_practice_question", save_mock),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _practice_json(
            QUESTION, "DROP TABLE employee"
        )
        mock_get_client.return_value = mock_client

        response = client.post("/api/v1/practice/generate", json=GENERATE_JSON)

    assert response.status_code == 502
    save_mock.assert_not_awaited()


def test_generate_malformed_output_does_not_persist():
    """Malformed structured output -> 502 and nothing is saved."""
    save_mock = AsyncMock()

    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.api.routes.practice.save_practice_question", save_mock),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _groq_response(
            "definitely not JSON"
        )
        mock_get_client.return_value = mock_client

        response = client.post("/api/v1/practice/generate", json=GENERATE_JSON)

    assert response.status_code == 502
    save_mock.assert_not_awaited()


def test_generate_persistence_failure_returns_500():
    """A database failure during save must not report success."""
    save_mock = AsyncMock(
        side_effect=PracticePersistenceError("could not save the practice question")
    )

    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.api.routes.practice.save_practice_question", save_mock),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _practice_json(
            QUESTION, REF_SQL
        )
        mock_get_client.return_value = mock_client

        response = client.post("/api/v1/practice/generate", json=GENERATE_JSON)

    assert response.status_code == 500
    # Generic detail: no SQL, URLs, or credentials are exposed.
    assert response.json()["detail"] == "Failed to persist the practice question"


# --- /api/v1/practice/evaluate (endpoint level, mocked Groq + persistence) -


def test_evaluate_success_persists_attempt():
    """After evaluation succeeds, the attempt is saved against its question."""
    question_id = uuid.uuid4()
    save_mock = AsyncMock()
    request_json = {**EVALUATE_JSON, "question_id": str(question_id)}

    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.api.routes.practice.save_practice_attempt", save_mock),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _groq_response(REF_SQL)
        mock_get_client.return_value = mock_client

        response = client.post("/api/v1/practice/evaluate", json=request_json)

    assert response.status_code == 200
    assert response.json()["correct"] is True
    save_mock.assert_awaited_once_with(
        question_id=question_id,
        submitted_sql=REF_SQL,
        correct=True,
        feedback=response.json()["feedback"],
    )


def test_evaluate_failure_does_not_persist():
    """Evaluation failure (invalid reference SQL) -> 502, nothing saved."""
    save_mock = AsyncMock()

    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.api.routes.practice.save_practice_attempt", save_mock),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _groq_response(
            "DROP TABLE employee"
        )
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/evaluate",
            json={**EVALUATE_JSON, "question_id": str(uuid.uuid4())},
        )

    assert response.status_code == 502
    save_mock.assert_not_awaited()


def test_evaluate_persistence_failure_returns_500():
    """A database failure during save must not report success."""
    save_mock = AsyncMock(
        side_effect=PracticePersistenceError("could not save the practice attempt")
    )

    with (
        patch("app.services.sql_generator._get_client") as mock_get_client,
        patch("app.api.routes.practice.save_practice_attempt", save_mock),
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _groq_response(REF_SQL)
        mock_get_client.return_value = mock_client

        response = client.post(
            "/api/v1/practice/evaluate",
            json={**EVALUATE_JSON, "question_id": str(uuid.uuid4())},
        )

    assert response.status_code == 500
    # Generic detail: no SQL, URLs, or credentials are exposed.
    assert response.json()["detail"] == "Failed to persist the practice attempt"
